"""Mail cancellation and current radio timeout recovery."""
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
    def test_abort_radio_mission_stops_retries_and_unlocks_ship(self):
        ship = self.app.game.ship
        job = {"id": "radio-active", "message_id": "contact-1", "purpose": "contact",
               "status": "awaiting_ack", "ship_id": ship["id"], "destination": "K7OR",
               "timeout_at": 9999999999, "payload_hash": "abcd"}
        self.app.radio_transmissions[job["id"]] = job
        ship["radio_mission"] = job["id"]
        result = self.app.execute({"action": "abort_radio_mission", "job_id": job["id"]})
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(job["status"], "cancelled")
        self.assertNotIn("radio_mission", ship)
        self.assertEqual(ship["condition"], 100)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "game.json"
        self.app = App(self.path, 42, "AG7SU")

    def test_expired_radio_job_damages_ship_and_persists_no_fake_receipt(self):
        original = self.app.game.ship["condition"]
        job = {"id": "radio-timeout", "message_id": "contact-1", "purpose": "contact",
               "status": "awaiting_ack", "ship_id": self.app.game.ship["id"],
               "origin": "Haven", "destination": "K7OR", "timeout_at": 100}
        self.app.radio_transmissions[job["id"]] = job
        self.app.game.ship["radio_mission"] = job["id"]
        self.app._expire_radio_transmissions(101)
        self.assertEqual(job["status"], "failed")
        self.assertEqual(self.app.game.ship["condition"], original - 10)
        self.assertFalse(self.app.radio_contacts)
        restored = App(self.path, 42, "AG7SU")
        self.assertEqual(restored.radio_transmissions[job["id"]]["status"], "failed")
        self.assertEqual(restored.game.ship["condition"], original - 10)

    def test_waiting_radio_job_with_payload_schedules_bounded_retry(self):
        job = {"id": "radio-retry", "message_id": "contact-1", "purpose": "contact",
               "status": "awaiting_ack", "ship_id": self.app.game.ship["id"],
               "origin": "Haven", "destination": "K7OR", "timeout_at": 100,
               "payload_hex": "0102", "timeout_seconds": 180, "auto_retry_count": 0}
        self.app.radio_transmissions[job["id"]] = job
        initial_condition = self.app.game.ship["condition"]
        self.app._expire_radio_transmissions(101)
        self.assertEqual(job["status"], "awaiting_ack")
        self.assertGreater(job["retry_due_at"], 101)
        self.assertEqual(self.app.game.ship["condition"], initial_condition)


if __name__ == "__main__":
    unittest.main()
