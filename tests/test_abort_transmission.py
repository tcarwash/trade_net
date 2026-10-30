"""Single-authority simulator cancellation; no modem or distributed settlement."""
import hashlib
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from tradenet.engine import GameError
from tradenet.mail import MailError, MailNetwork
from tradenet.web import App


class MailCancelTests(unittest.TestCase):
    def test_cancel_stops_data_and_returning_ack_idempotently(self):
        for status in ("queued", "transmitting", "delivered", "expired"):
            with self.subTest(status=status):
                mail = MailNetwork()
                mail.add_station("A")
                mail.add_station("B")
                message = mail.enqueue("trip", ["A", "B"], b"manifest")
                mail.step(loss=0)
                message["status"] = status
                mail.cancel("trip")
                self.assertEqual(message["status"], "aborted")
                self.assertEqual(mail.messages["ack:trip"]["status"], "aborted")
                before = deepcopy(mail.to_dict())
                mail.cancel("trip")
                self.assertEqual(mail.to_dict(), before)
                for _ in range(10):
                    mail.step(loss=0)
                self.assertEqual(mail.attempts, before["attempts"])
                self.assertEqual(message["status"], "aborted")


class AbortTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "game.json"
        self.app = App(self.path, 42, "AG7SU")

    def jump(self, identity="trip", galaxy="SIM-K7OR", destination="Kepler"):
        return self.app.execute({"id": identity, "action": "jump",
            "args": {"galaxy": galaxy, "destination": destination}})

    def abort(self, identity="abort", **extra):
        return self.app.execute({"id": identity, "action": "abort_transmission", **extra})

    def test_early_abort_returns_same_ship_without_refunds_or_later_arrival(self):
        self.app.game.command("load", "buy", good="food", amount=2)
        before = deepcopy(self.app.game.ship)
        credits = self.app.game.credits
        self.jump()
        result = self.abort()
        self.assertEqual(result, {"voyage_id": "voyage:trip", "ship_id": "ship-1",
            "damage": 0, "condition": 100, "destroyed": False, "returned_to": "Haven",
            "origin_galaxy": "home", "penalty_applied": False})
        self.assertEqual(self.abort(), result)
        self.assertEqual(self.app.game.ship["cargo"], before["cargo"])
        self.assertEqual(self.app.game.credits, credits)
        self.assertEqual(self.app.game.ship["fuel"], before["fuel"] - 10)
        for key in ("voyage", "voyage_manifest", "radio_mission"):
            self.assertNotIn(key, self.app.game.ship)
        attempts = self.app.mail.attempts
        for _ in range(20):
            self.app.execute({"action": "mail_step", "loss": 0})
        self.app.sync_clock((self.app.game.clock_epoch + 100) * 300)
        self.assertEqual(self.app.mail.attempts, attempts)
        self.assertEqual(self.app.game.ship["galaxy"], "home")
        self.assertEqual(self.app.game.ship["location"], "Haven")
        self.assertEqual(self.app.mail.messages["voyage:trip"]["status"], "aborted")
        self.app = App(self.path, 42, "AG7SU")
        self.assertEqual(self.abort(), result)

    def four_frames(self):
        message = self.app.mail.messages[self.app.game.ship["voyage"]["id"]]
        # A real manifest, with whitespace padding, still hashes correctly.
        payload = bytes.fromhex(message["payload_hex"]).ljust(4 * self.app.mail.frame_bytes, b" ")
        self.assertLessEqual(len(payload), 4 * self.app.mail.frame_bytes)
        message["payload_hex"] = payload.hex()
        message["sha256"] = hashlib.sha256(payload).hexdigest()
        return message


if __name__ == "__main__":
    unittest.main()
