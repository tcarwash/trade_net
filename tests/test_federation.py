import tempfile
import unittest
from pathlib import Path

from tradenet import GameError
from tradenet.federation import Federation
from tradenet.web import App


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


if __name__ == "__main__":
    unittest.main()
