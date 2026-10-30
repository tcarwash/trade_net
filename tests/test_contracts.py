import unittest
import tempfile
from pathlib import Path

from tradenet import Game, GameError
from tradenet.contracts import dispatch, seed_offers
from tradenet.network import Network
from tradenet.web import App


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.game = Game.new(42)
        seed_offers(self.game)
        self.net = Network("AG7SU")

    def offer(self, good="food"):
        return next(c for c in self.game.contracts.values() if c["good"] == good)

    def load(self, c):
        self.game.command("buy-" + c["id"], "buy", good=c["good"], amount=c["quantity"])
        self.game.command("accept-" + c["id"], "accept_contract", contract_id=c["id"])

    def test_offer_generation_stable(self):
        other = Game.new(42)
        seed_offers(other)
        self.assertEqual(self.game.contracts, other.contracts)
        seed_offers(self.game)
        self.assertEqual(len(self.game.contracts), 5)

    def test_contract_requires_reserved_cargo(self):
        c = self.offer()
        with self.assertRaises(GameError):
            self.game.command("empty", "accept_contract", contract_id=c["id"])
        self.load(c)
        self.assertEqual(self.game.cargo[c["good"]], 0)
        self.assertEqual(self.game.contracts[c["id"]]["status"], "reserved")

    def test_direct_settlement_exactly_once(self):
        c = self.offer()
        self.load(c)
        old = self.game.credits
        result = dispatch(self.game, self.net, c["id"], loss=0)
        self.assertEqual(result["status"], "settled")
        self.assertEqual(self.game.credits, old + c["reward"])
        with self.assertRaises(GameError):
            dispatch(self.game, self.net, c["id"], loss=0)
        self.assertEqual(self.game.credits, old + c["reward"])

    def test_failed_hop_retains_custody_then_retries(self):
        c = self.offer()
        self.load(c)
        start = self.game.credits
        failed = dispatch(self.game, self.net, c["id"], loss=1)
        self.assertEqual(failed["status"], "in_transit")
        self.assertEqual(failed["custody"], "AG7SU")
        self.assertEqual(self.game.credits, start)
        succeeded = dispatch(self.game, self.net, c["id"], loss=0)
        self.assertEqual(succeeded["status"], "settled")
        self.assertEqual(self.game.credits, start + c["reward"])

    def test_multi_hop_custody_without_false_direct_contact(self):
        c = self.offer()
        self.load(c)
        route = ["AG7SU", "SIM-RELAY", c["destination"]]
        first = dispatch(self.game, self.net, c["id"], route=route, loss=0)
        self.assertEqual(first["custody"], "SIM-RELAY")
        self.assertEqual(c["status"], "in_transit")
        last = dispatch(self.game, self.net, c["id"], loss=0)
        self.assertEqual(last["status"], "settled")
        self.assertNotIn(c["destination"], self.net.peers)
        self.assertIn("SIM-RELAY", self.net.peers)

    def test_cancel_refunds_undispatched_escrow(self):
        c = self.offer()
        self.load(c)
        self.game.command("cancel", "cancel_contract", contract_id=c["id"])
        self.assertEqual(self.game.cargo[c["good"]], c["quantity"])
        self.assertEqual(c["status"], "cancelled")

    def test_web_app_persists_current_local_contracts_and_fleet_orders(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "galaxy.json"
            app = App(path, 42, "AG7SU")
            initial_jobs = list(app.game.local_jobs)
            app.execute({"action": "set_fleet_reserve", "id": "reserve", "args": {"credits": 750}})
            loaded = App(path, 42, "AG7SU")
            self.assertEqual(loaded.game.fleet_credit_reserve, 750)
            self.assertEqual(list(loaded.game.local_jobs), initial_jobs)
            self.assertEqual(loaded.callsign, "AG7SU")


if __name__ == "__main__":
    unittest.main()
