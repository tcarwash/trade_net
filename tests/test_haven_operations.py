"""Buildable Haven operations preserve physical imports and local-only rewards."""

import unittest

from tradenet.engine import Game, GameError
from tradenet.modems import SHIPS


class HavenOperationsTests(unittest.TestCase):
    @staticmethod
    def dock(game, port):
        game.ship["location"] = port
        game._bind_ship()

    @staticmethod
    def build_logistics(game):
        game.credits += 2000
        game.cargo["medicine"] = 2
        game.ship.setdefault("export_cargo", {})["medicine"] = 2
        return game.command("build-exchange", "upgrade_haven", facility="logistics")

    def test_new_facilities_still_require_imported_cargo_and_persist(self):
        game = Game.new(3)
        for facility in ("shipyard", "logistics", "liaison"):
            self.assertEqual(game.haven_facilities[facility], 0)
        quote = game.haven_upgrade_quote("logistics")
        self.assertEqual((quote["good"], quote["quantity"]), ("medicine", 2))
        game.credits += 2000
        game.cargo["medicine"] = 2
        with self.assertRaises(GameError):
            game.command("invalid-build", "upgrade_haven", facility="logistics")
        self.assertEqual(game.haven_facilities["logistics"], 0)
        game.ship.setdefault("export_cargo", {})["medicine"] = 2
        result = game.command("build-exchange", "upgrade_haven", facility="logistics")
        self.assertEqual(result["level"], 1)
        self.assertEqual(game.cargo["medicine"], 0)
        self.assertEqual(game.ship["export_cargo"]["medicine"], 0)
        self.assertEqual(len(game.haven_orders), 1)
        self.assertEqual(Game.from_dict(game.to_dict()).haven_facilities["logistics"], 1)

    def test_haven_requisition_consumes_multiple_warehouse_resources_once(self):
        game = Game.new(8)
        self.build_logistics(game)
        order = next(iter(game.haven_orders.values()))
        self.assertEqual(order["source"], "local_simulation")
        self.assertEqual(len(order["requirements"]), 2)
        self.assertEqual(order["deadline"], game.tick + 2016)
        with self.assertRaises(GameError):
            game.command("too-soon", "fulfill_haven_order", order_id=order["id"])
        for i, (good, quantity) in enumerate(order["requirements"].items()):
            source = next(port for port, market in game.ports.items() if port != "Haven"
                          and market["stock"][good] >= quantity)
            self.dock(game, source)
            game.command(f"buy-{i}", "buy", good=good, amount=quantity)
            self.dock(game, "Haven")
            game.command(f"unload-{i}", "unload_export", good=good, amount=quantity)
            self.assertEqual(game.export_warehouse[good], quantity)
        previous = game.credits
        reward = game.command("deliver", "fulfill_haven_order", order_id=order["id"])
        self.assertEqual(reward["reward"], order["reward"])
        self.assertEqual(game.credits, previous + order["reward"])
        self.assertEqual(game.haven_orders[order["id"]]["status"], "fulfilled")
        for good in order["requirements"]:
            self.assertEqual(game.export_warehouse[good], 0)
        self.assertEqual(game.command("deliver", "fulfill_haven_order", order_id=order["id"]), reward)
        with self.assertRaises(GameError):
            game.command("double-deliver", "fulfill_haven_order", order_id=order["id"])
        self.assertEqual(len(game.haven_orders), 1)
        game.command("next-post", "wait", ticks=48)
        self.assertEqual(len(game.haven_orders), 2)

    def test_long_offline_period_does_not_backfill_hundreds_of_requisitions(self):
        game = Game.new(6)
        self.build_logistics(game)
        first_id = next(iter(game.haven_orders))
        saved = game.to_dict()
        for field in ("haven_orders", "next_haven_order_number", "next_haven_order_tick"):
            saved.pop(field)
        migrated = Game.from_dict(saved)
        self.assertEqual(len(migrated.haven_orders), 1)
        migrated.clock_epoch = 10_000
        migrated.sync_utc((10_000 + 10_000) * migrated.tick_seconds)
        self.assertEqual(sum(o["status"] == "open" for o in migrated.haven_orders.values()), 1)
        self.assertLessEqual(len(migrated.haven_orders), 12)
        game.tick = game.haven_orders[first_id]["deadline"] + 1
        game._refresh_haven_orders()
        self.assertEqual(game.haven_orders[first_id]["status"], "expired")
        self.assertEqual(sum(o["status"] == "open" for o in game.haven_orders.values()), 1)

    def test_shipyard_discounts_new_ships_only_at_haven(self):
        game = Game.new(2)
        game.credits += 20000
        game.haven_facilities["shipyard"] = 2
        hull = SHIPS[0]
        local = game.command("buy-at-haven", "purchase_ship", class_id=hull["id"])
        self.assertEqual(local["cost"], hull["cost"] * 80 // 100)
        self.assertEqual(local["discount_percent"], 20)
        self.dock(game, "Kepler")
        remote = game.command("buy-away", "purchase_ship", class_id=hull["id"])
        self.assertEqual(remote["cost"], hull["cost"])
        self.assertEqual(remote["discount_percent"], 0)

    def test_cargo_exchange_second_level_requires_three_goods(self):
        game = Game.new(11)
        self.build_logistics(game)
        game.haven_facilities["logistics"] = 2
        game.command("next-contract", "wait", ticks=48)
        for order in game.haven_orders.values():
            order["status"] = "fulfilled"
        game._refresh_haven_orders()
        second = game.haven_orders["haven-order-00002"]
        self.assertEqual(len(second["requirements"]), 3)
        self.assertEqual(second["source"], "local_simulation")

    def test_cargo_exchange_improves_local_haven_freight_not_radio(self):
        game = Game.new(7)
        game.haven_facilities["logistics"] = 2
        game.local_jobs["haven-test"] = {
            "id": "haven-test", "origin": "Prospect", "destination": "Haven",
            "good": "food", "quantity": 2, "reward": 150,
            "status": "open", "deadline": game.tick + 30}
        game.cargo["food"] = 2
        result = game.command("deliver-test", "deliver_local", job_id="haven-test")
        self.assertEqual(result["reward"], 180)

    def test_liaison_shortens_captain_lot_cooldown(self):
        game = Game.new(5)
        captain = game.npc_captains["mara-venn"]
        captain["relationship"] = 2
        self.dock(game, captain["location"])
        game.credits += 1000
        game.haven_facilities["liaison"] = 2
        purchase = game.command("lot", "buy_captain_deal", npc_id=captain["id"], amount=1)
        self.assertEqual(purchase["next_tick"], game.tick + 16)
        self.assertFalse(game.captain_deal_quote(captain["id"])["available"])
        game.command("cooldown", "wait", ticks=16)
        self.assertTrue(game.captain_deal_quote(captain["id"])["available"])

    def test_requisition_is_local_and_never_creates_a_radio_contact(self):
        from tests.test_radio_flow import station

        app = station("W1HAVEN", 9)
        self.build_logistics(app.game)
        order = next(iter(app.game.haven_orders.values()))
        for good, quantity in order["requirements"].items():
            app.game.export_warehouse[good] = quantity
        result = app.execute({"id": "station-supply", "action": "fulfill_haven_order",
                              "args": {"order_id": order["id"]}})
        self.assertEqual(result["source"], "local_simulation")
        self.assertEqual(app.radio_transmissions, {})
        self.assertEqual(app.radio_contacts, {})
        self.assertEqual(app.radio_reservations, {})


if __name__ == "__main__":
    unittest.main()
