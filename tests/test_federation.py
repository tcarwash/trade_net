import tempfile
import unittest
from pathlib import Path

from tradenet import GameError
from tradenet.federation import Federation
from tradenet.web import App
from tradenet.mail import MailNetwork
from tradenet.payloads import decode as decode_bundle


class FederationTests(unittest.TestCase):
    def setUp(self):
        self.f = Federation.demo()
        self.seller, self.buyer = list(self.f.worlds)
        self.good = self.f.worlds[self.seller].specialization

    def propose(self, trade_id="T1", quantity=2):
        return self.f.propose(trade_id, self.seller, self.buyer,
                              self.good, quantity, 220, payload_bytes=1024)

    def test_distinct_specialized_galaxies(self):
        self.assertNotEqual(self.f.worlds[self.seller].specialization,
                            self.f.worlds[self.buyer].specialization)

    def test_reservation_is_conservative_and_idempotent(self):
        self.propose()
        seller, buyer = self.f.worlds[self.seller], self.f.worlds[self.buyer]
        starting_stock, starting_money = seller.cargo[self.good], buyer.credits
        self.f.reserve("T1")
        self.f.reserve("T1")
        self.assertEqual(seller.cargo[self.good], starting_stock - 2)
        self.assertEqual(buyer.credits, starting_money - 440)
        self.assertEqual(buyer.incoming_reserved, 2)

    def test_failed_delivery_then_receipt_and_exactly_once_settlement(self):
        t = self.propose()
        self.f.reserve("T1")
        seller, buyer = self.f.worlds[self.seller], self.f.worlds[self.buyer]
        before = seller.credits
        fail = self.f.dispatch("T1", loss=1)
        self.assertFalse(fail["delivered"])
        self.assertEqual(t["custody"], self.seller)
        with self.assertRaises(GameError):
            self.f.settle("T1")
        success = self.f.dispatch("T1", loss=0)
        self.assertTrue(success["delivered"])
        self.assertEqual(t["status"], "delivered")
        receipt = t["receipt"]
        with self.assertRaises(GameError):
            self.f.settle("T1", {**receipt, "terms_hash": "wrong"})
        first = self.f.settle("T1")
        second = self.f.settle("T1")
        self.assertEqual(first, second)
        self.assertEqual(seller.credits, before + 440)
        self.assertEqual(buyer.cargo[self.good], 2)
        self.assertEqual(buyer.incoming_reserved, 0)

    def test_courier_hops_dont_mint_inventory(self):
        t = self.propose()
        self.f.reserve("T1")
        route = [self.seller, "SIM-RELAY", self.buyer]
        self.f.dispatch("T1", route=route, loss=0)
        self.assertEqual(t["custody"], "SIM-RELAY")
        self.assertEqual(self.f.worlds[self.buyer].cargo[self.good], 0)
        self.f.dispatch("T1", loss=0)
        self.assertEqual(t["custody"], self.buyer)
        self.assertEqual(self.f.worlds[self.buyer].cargo[self.good], 0)
        self.f.settle("T1")
        self.assertEqual(self.f.worlds[self.buyer].cargo[self.good], 2)
        self.assertNotIn(self.buyer, self.f.network.peers)

    def test_cancel_restores_escrow(self):
        self.propose()
        seller, buyer = self.f.worlds[self.seller], self.f.worlds[self.buyer]
        before = (seller.cargo[self.good], buyer.credits)
        self.f.reserve("T1")
        self.f.cancel("T1")
        self.assertEqual((seller.cargo[self.good], buyer.credits), before)
        self.assertEqual(buyer.incoming_reserved, 0)

    def test_incoming_capacity_cannot_be_overbooked(self):
        self.propose(quantity=6)
        self.f.reserve("T1")
        buyer = self.f.worlds[self.buyer]
        self.assertEqual(buyer.incoming_reserved, 6)
        with self.assertRaises(GameError):
            buyer.command("overfill", "buy", good="food", amount=25)

    def test_save_and_restart_before_settlement(self):
        self.propose()
        self.f.reserve("T1")
        self.f.dispatch("T1", loss=0)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "federation.json"
            self.f.save(path)
            other = Federation.load(path)
            self.assertEqual(other.to_dict(), self.f.to_dict())
            other.settle("T1")
            other.save(path)
            final = Federation.load(path)
            self.assertEqual(final.trades["T1"]["status"], "settled")
            self.assertEqual(final.settle("T1"), other.trades["T1"]["settlement"])

    def test_duplicate_trade_id_must_have_same_terms(self):
        self.propose()
        self.propose()
        with self.assertRaises(GameError):
            self.propose(quantity=3)

    def test_browser_demo_end_to_end_persists(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "galaxy.json"
            app = App(path, 42, "AG7SU")
            t = app.federation.trades["DEMO-001"]
            app.execute({"action": "exchange_reserve", "trade_id": t["id"]})
            app.execute({"action": "exchange_dispatch", "trade_id": t["id"], "loss": 0})
            receipt = app.execute({"action": "exchange_settle", "trade_id": t["id"]})
            restarted = App(path, 42, "AG7SU")
            self.assertEqual(restarted.federation.trades[t["id"]]["status"], "settled")
            self.assertEqual(restarted.execute({"action": "exchange_settle", "trade_id": t["id"]}), receipt)

    def test_async_queue_and_late_reverse_ack(self):
        self.propose()
        self.f.reserve("T1")
        mail = MailNetwork()
        self.f.queue_trade(mail, "T1", [self.seller, "RELAY", self.buyer])
        mail.set_online(self.buyer, False)
        for _ in range(10):
            mail.step(loss=0, budget_frames=64)
            self.f.sync_mail(mail)
        self.assertEqual(self.f.trades["T1"]["status"], "queued")
        self.assertEqual(mail.messages["trade:T1"]["hop"], 1)
        mail.set_online(self.buyer, True)
        for _ in range(30):
            mail.step(loss=0, budget_frames=64)
            self.f.sync_mail(mail)
            if self.f.trades["T1"]["status"] == "delivered":
                break
        self.assertEqual(self.f.trades["T1"]["status"], "delivered")
        self.f.settle("T1")
        self.assertEqual(self.f.worlds[self.buyer].cargo[self.good], 2)

    def test_ship_modem_upgrade_gates_mail_capacity(self):
        self.propose()
        self.f.reserve("T1")
        seller = self.f.worlds[self.seller]
        seller.command("upgrade-modem", "upgrade_modem")
        mail = MailNetwork()
        msg = self.f.queue_trade(mail, "T1")
        self.assertEqual(msg["bandwidth_hz"], 1200)
        self.assertEqual(msg["frames_per_tick"], 6)

    def test_web_async_exchange_survives_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "galaxy.json"
            app = App(path, 42, "AG7SU")
            trade_id = "DEMO-001"
            app.execute({"action": "exchange_reserve", "trade_id": trade_id})
            app.execute({"action": "exchange_queue", "trade_id": trade_id,
                         "route": ["AG7SU", "SIM-RELAY", "SIM-K7OR"]})
            app.execute({"action": "mail_station", "station": "SIM-K7OR", "online": False})
            for _ in range(5):
                app.execute({"action": "mail_step", "loss": 0, "budget_frames": 64})
            app = App(path, 42, "AG7SU")
            self.assertEqual(app.federation.trades[trade_id]["status"], "queued")
            app.execute({"action": "mail_station", "station": "SIM-K7OR", "online": True})
            for _ in range(30):
                app.execute({"action": "mail_step", "loss": 0, "budget_frames": 64})
                if app.federation.trades[trade_id]["status"] == "delivered":
                    break
            self.assertEqual(app.federation.trades[trade_id]["status"], "delivered")
            app.execute({"action": "exchange_settle", "trade_id": trade_id})
            self.assertEqual(App(path, 42, "AG7SU").federation.trades[trade_id]["status"], "settled")

    def test_three_useful_load_classes_increase_real_content(self):
        t = self.propose()
        a = self.f.trade_payload(t, "light", self.f.reports)
        b = self.f.trade_payload(t, "medium", self.f.reports)
        c = self.f.trade_payload(t, "heavy", self.f.reports)
        self.assertLess(len(a), len(b))
        self.assertLess(len(b), len(c))
        self.assertEqual([item.kind for item in decode_bundle(b)], ["trade", "neighbors"])
        self.assertEqual([item.kind for item in decode_bundle(c)], ["trade", "neighbors", "market"])
        self.assertIn(b"ore_stock", b)
        self.assertIn(b"prices", c)
        self.assertNotIn(b"padding", c)

    def test_missing_second_hop_report_rejects_medium(self):
        t = self.propose()
        with self.assertRaises(GameError):
            self.f.trade_payload(t, "medium", {})


if __name__ == "__main__":
    unittest.main()
