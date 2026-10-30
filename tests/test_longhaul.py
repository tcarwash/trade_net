"""Long-haul manifests assemble over time and settle atomically over radio."""

import unittest

from tradenet import radio_exchange
from tradenet.engine import BASE_PRICE, Game, GameError
from tests.test_radio_flow import outgoing, receive, station


class LongHaulTests(unittest.TestCase):
    def test_wire_supports_legacy_band_and_multi_resource_offers(self):
        app = station("W1AAA", 10)
        contracts = app.radio_contracts["W1AAA"]
        self.assertTrue(any(c.get("kind") == "longhaul" for c in contracts))
        self.assertTrue(any(c.get("band") for c in contracts))
        wire = radio_exchange.wire_contracts(contracts)
        parsed = radio_exchange.read_contracts(wire, "W1AAA")
        self.assertEqual([c.get("requirements") for c in parsed],
                         [c.get("requirements") for c in contracts])
        self.assertEqual([c.get("band") for c in parsed],
                         [c.get("band") for c in contracts])
        self.assertEqual(len(radio_exchange.read_contracts([["old-C1", "food", 3]], "OLD")), 1)
        self.assertEqual(radio_exchange.read_contracts([
            ["bad-C2", "food", 2, "", [["food", 2], ["ore", -4]]]], "OLD"), [])

    def test_partial_warehouse_stockpiling_then_atomic_delivery(self):
        alice, bob = station("W1AAA", 12), station("W2BBB", 15)
        alice.radio_contacts[bob.callsign] = 1
        bob.radio_contacts[alice.callsign] = 1
        published = radio_exchange.wire_contracts(bob.radio_contracts[bob.callsign])
        alice.radio_contracts[bob.callsign] = radio_exchange.read_contracts(published, bob.callsign)
        contract = next(c for c in alice.radio_contracts[bob.callsign] if c.get("requirements"))
        goods = contract["requirements"]
        requested = {"action": "exchange_reserve", "station": bob.callsign,
                     "contract_id": contract["id"]}
        first = next(iter(goods))
        alice.game.export_warehouse[first] = goods[first]
        alice.game = Game.from_dict(alice.game.to_dict())  # Save/reload between expeditions.
        with self.assertRaisesRegex(GameError, "Complete the Haven export manifest"):
            alice.execute(requested)
        self.assertEqual(alice.game.export_warehouse[first], goods[first])
        second = next(g for g in goods if g != first)
        alice.game.export_warehouse[second] = goods[second]
        reservation = alice.execute(requested)
        self.assertEqual(reservation["goods"], goods)
        self.assertEqual(alice.game.export_warehouse[first], 0)
        self.assertEqual(alice.game.export_warehouse[second], 0)
        message = {"v": 1, "t": "delivery", "i": alice.radio_reservations[contract["id"]]["message_id"],
            "f": alice.callsign, "d": bob.callsign, "c": contract["id"],
            "g": contract["good"], "q": contract["quantity"],
            "m": [[good, qty] for good, qty in goods.items()], "n": []}
        payload = radio_exchange.encode_message(message)
        outgoing(alice, payload, "delivery", bob.callsign, contract["id"])
        old_credits = alice.game.credits
        old_stock = {good: bob.game.ports["Haven"]["stock"][good] for good in goods}
        receipt = receive(bob, payload)
        self.assertIsNotNone(receipt)
        self.assertTrue(radio_exchange.decode(receipt)["ok"])
        for good, qty in goods.items():
            self.assertEqual(bob.game.ports["Haven"]["stock"][good], old_stock[good] + qty)
        self.assertEqual(receive(bob, payload), receipt)
        receive(alice, receipt)
        expected = min(3000, 100 + 2 * sum(BASE_PRICE[g] * qty for g, qty in goods.items()))
        self.assertEqual(alice.game.credits, old_credits + expected)
        self.assertNotIn(contract["id"], alice.radio_reservations)
        receive(alice, receipt)
        self.assertEqual(alice.game.credits, old_credits + expected)

    def test_receiver_rejects_incomplete_manifest_without_stock_credit(self):
        alice, bob = station("W1AAA", 12), station("W2BBB", 15)
        bob.radio_contacts[alice.callsign] = 1
        contract = next(c for c in bob.radio_contracts[bob.callsign] if c.get("requirements"))
        goods = contract["requirements"]
        message = {"v": 1, "t": "delivery", "i": "incomplete-0001", "f": alice.callsign,
                   "d": bob.callsign, "c": contract["id"], "g": contract["good"],
                   "q": contract["quantity"], "m": [[contract["good"], contract["quantity"]]], "n": []}
        old_stock = {good: bob.game.ports["Haven"]["stock"][good] for good in goods}
        receipt = receive(bob, radio_exchange.encode_message(message))
        self.assertFalse(radio_exchange.decode(receipt)["ok"])
        for good in goods:
            self.assertEqual(bob.game.ports["Haven"]["stock"][good], old_stock[good])


if __name__ == "__main__":
    unittest.main()
