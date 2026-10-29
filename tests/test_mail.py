import tempfile
import unittest
from pathlib import Path

from tradenet.mail import MailError, MailNetwork


class MailTests(unittest.TestCase):
    def setUp(self):
        self.mail = MailNetwork()
        for name in ("AG7SU", "RELAY", "K7OR"):
            self.mail.add_station(name)

    def run_until(self, predicate, limit=100):
        for _ in range(limit):
            if predicate():
                return
            self.mail.step(loss=0, budget_frames=5)
        self.fail("message did not reach expected state")

    def test_forward_and_reverse_ack(self):
        self.mail.enqueue("shipment-1", ["AG7SU", "RELAY", "K7OR"], b"manifest" * 50)
        self.run_until(lambda: self.mail.messages["shipment-1"]["status"] == "acknowledged")
        self.assertEqual(len(self.mail.inbox["K7OR"]), 1)
        self.assertEqual(self.mail.messages["ack:shipment-1"]["status"], "delivered")
        self.assertEqual(self.mail.messages["shipment-1"]["receipt_id"], "ack:shipment-1")

    def test_offline_relay_holds_custody_through_restart(self):
        self.mail.enqueue("shipment-2", ["AG7SU", "RELAY", "K7OR"], b"cargo")
        self.mail.set_online("K7OR", False)
        self.mail.step(loss=0)
        self.assertEqual(self.mail.messages["shipment-2"]["hop"], 1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mail.json"
            self.mail.save(path)
            self.mail = MailNetwork.load(path)
            for _ in range(5):
                self.mail.step(loss=0)
            self.assertEqual(self.mail.messages["shipment-2"]["hop"], 1)
            self.mail.set_online("K7OR", True)
            self.run_until(lambda: self.mail.messages["shipment-2"]["status"] == "acknowledged")

    def test_sender_offline_after_delivery_can_receive_delayed_ack(self):
        self.mail.enqueue("shipment-3", ["AG7SU", "K7OR"], b"manifest")
        self.mail.step(loss=0)
        self.assertEqual(self.mail.messages["shipment-3"]["status"], "delivered")
        self.mail.set_online("AG7SU", False)
        self.mail.step(loss=0)
        self.assertEqual(self.mail.messages["shipment-3"]["status"], "delivered")
        self.mail.set_online("AG7SU", True)
        self.run_until(lambda: self.mail.messages["shipment-3"]["status"] == "acknowledged")

    def test_all_loss_then_recover(self):
        self.mail.enqueue("shipment-4", ["AG7SU", "K7OR"], b"manifest" * 100)
        for _ in range(5):
            self.mail.step(loss=1, budget_frames=16)
        self.assertEqual(len(self.mail.inbox["K7OR"]), 0)
        self.assertGreater(self.mail.messages["shipment-4"]["frames_lost"], 0)
        self.run_until(lambda: self.mail.messages["shipment-4"]["status"] == "acknowledged")
        self.assertEqual(len(self.mail.inbox["K7OR"]), 1)

    def test_duplicate_enqueue_is_idempotent(self):
        a = self.mail.enqueue("same", ["AG7SU", "K7OR"], b"abc")
        self.assertIs(self.mail.enqueue("same", ["AG7SU", "K7OR"], b"abc"), a)
        with self.assertRaises(MailError):
            self.mail.enqueue("same", ["AG7SU", "K7OR"], b"different")

    def test_offline_until_expiry(self):
        self.mail.set_online("K7OR", False)
        self.mail.enqueue("expire", ["AG7SU", "K7OR"], b"abc", ttl=2)
        for _ in range(4):
            self.mail.step(loss=0)
        self.assertEqual(self.mail.messages["expire"]["status"], "expired")
        self.assertEqual(len(self.mail.inbox["K7OR"]), 0)

    def test_modem_capacity_controls_simulated_progress(self):
        slow = MailNetwork()
        fast = MailNetwork()
        for net in (slow, fast):
            net.add_station("AG7SU")
            net.add_station("K7OR")
        slow.enqueue("slow", ["AG7SU", "K7OR"], b"x" * 1024,
                     frames_per_tick=2, bandwidth_hz=500)
        fast.enqueue("fast", ["AG7SU", "K7OR"], b"x" * 1024,
                     frames_per_tick=16, bandwidth_hz=2400)
        slow.step(loss=0, budget_frames=64)
        fast.step(loss=0, budget_frames=64)
        self.assertEqual(slow.messages["slow"]["status"], "transmitting")
        self.assertEqual(fast.messages["fast"]["status"], "delivered")


if __name__ == "__main__":
    unittest.main()
