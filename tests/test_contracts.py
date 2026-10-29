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

    def test_web_app_persists_contract_and_network(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "galaxy.json"
            app = App(path, 42, "AG7SU")
            c = next(c for c in app.game.contracts.values() if c["good"] == "food")
            app.execute({"action": "buy", "id": "buy", "args": {"good": "food", "amount": c["quantity"]}})
            app.execute({"action": "accept_contract", "id": "accept", "args": {"contract_id": c["id"]}})
            app.execute({"action": "dispatch_contract", "contract_id": c["id"], "loss": 0})
            loaded = App(path, 42, "AG7SU")
            self.assertEqual(loaded.game.contracts[c["id"]]["status"], "settled")
            self.assertIn("AG7SU->" + c["destination"], loaded.net.links)


if __name__ == "__main__":
    unittest.main()
