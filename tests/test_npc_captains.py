"""Named local captains move finite goods and remember expedition choices."""

import unittest

from tradenet.engine import Game, GameError, NPC_CAPTAINS, NPC_INTERVAL


class NpcCaptainTests(unittest.TestCase):
    @staticmethod
    def dock(game, port):
        game.ship["location"] = port
        game._bind_ship()

    def test_four_persistent_captains_with_local_only_identity(self):
        a, b = Game.new(42), Game.new(42)
        self.assertEqual(a.npc_captains, b.npc_captains)
        self.assertEqual(set(a.npc_captains), {captain["id"] for captain in NPC_CAPTAINS})
        self.assertEqual(len(a.npc_shipments), 0)
        self.assertTrue(all("callsign" not in npc for npc in a.npc_captains.values()))
        old = a.to_dict()
        old.pop("npc_captains")
        old.pop("npc_shipments")
        self.assertEqual(set(Game.from_dict(old).npc_captains), set(a.npc_captains))

    def test_capital_and_stock_are_not_created_by_npc_hauls(self):
        game = Game.new(8)
        for captain in game.npc_captains.values():
            good = captain["good"]
            for port in captain["route"]:
                game.ports[port]["production"][good] = 0
                game.ports[port]["consumption"][good] = 0
        captain = game.npc_captains["mara-venn"]
        start = captain["location"]
        other = next(port for port in captain["route"] if port != start)
        total = game.ports[start]["stock"]["food"] + game.ports[other]["stock"]["food"]
        credits = game.credits
        game.command("market-6", "wait", ticks=NPC_INTERVAL)
        current = game.npc_captains["mara-venn"]
        self.assertEqual(current["location"], other)
        self.assertEqual(game.ports[start]["stock"]["food"] + game.ports[other]["stock"]["food"], total)
        self.assertEqual(game.credits, credits)
        self.assertEqual(current["runs"], 1)
        report = next(report for report in game.npc_shipments if report["npc_id"] == "mara-venn")
        self.assertEqual(report["origin"], start)
        self.assertEqual(report["destination"], other)
        self.assertEqual(report["quantity"], min(4, total))

    def test_long_offline_catchup_is_bounded_and_save_stable(self):
        game = Game.new(15)
        game.clock_epoch = 10_000
        game.sync_utc((10_000 + 200_000) * game.tick_seconds)
        self.assertEqual(game.tick, 200_000)
        self.assertLessEqual(len(game.npc_shipments), 24)
        self.assertTrue(all(captain["runs"] <= 24 for captain in game.npc_captains.values()))
        self.assertTrue(all(0 <= qty <= 300 for port in game.ports.values()
                            for qty in port["stock"].values()))
        restored = Game.from_dict(game.to_dict())
        self.assertEqual(restored.npc_captains, game.npc_captains)
        self.assertEqual(restored.npc_shipments, game.npc_shipments)

    def test_faction_arc_grants_named_relationship_and_local_market_deal(self):
        game = Game.new(18)
        expedition_id = "expedition-embers"
        game.command("start-embers", "accept_expedition", expedition_id=expedition_id)
        self.dock(game, "Prospect")
        game.cargo["ore"] = 4
        game.command("load-embers", "advance_expedition", expedition_id=expedition_id)
        self.dock(game, "Cinder")
        game.command("choose-miners", "advance_expedition",
                     expedition_id=expedition_id, choice="miners")
        self.dock(game, "Haven")
        completed = game.command("report-embers", "advance_expedition", expedition_id=expedition_id)
        self.assertEqual(completed["relationship_delta"], 3)
        self.assertEqual(completed["captain"], "Rin Kestrel")
        self.assertEqual(game.npc_captains["rin-kestrel"]["relationship"], 3)
        self.assertEqual(game.factions["miners"], 4)
        self.assertEqual(game.command("report-embers", "advance_expedition",
                                      expedition_id=expedition_id), completed)
        port = game.npc_captains["rin-kestrel"]["location"]
        ally_price = game.price(port, "ore", "buy")
        game.npc_captains["rin-kestrel"]["relationship"] = 0
        neutral_price = game.price(port, "ore", "buy")
        self.assertLess(ally_price, neutral_price)

    def test_rival_choice_increases_local_prices_and_cannot_be_repeated(self):
        game = Game.new(3)
        expedition_id = "expedition-blackwake"
        game.command("start-rook", "accept_expedition", expedition_id=expedition_id)
        self.dock(game, "Kepler")
        game.cargo["fuel"] = 4
        game.command("load-rook", "advance_expedition", expedition_id=expedition_id)
        self.dock(game, "Drift")
        game.command("choose-patrol", "advance_expedition",
                     expedition_id=expedition_id, choice="patrol")
        self.dock(game, "Haven")
        completed = game.command("report-rook", "advance_expedition", expedition_id=expedition_id)
        self.assertEqual(completed["relationship_delta"], -3)
        self.assertEqual(game.npc_captains["sable-rook"]["relationship"], -3)
        port = game.npc_captains["sable-rook"]["location"]
        hostile = game.price(port, "fuel", "buy")
        game.npc_captains["sable-rook"]["relationship"] = 0
        neutral = game.price(port, "fuel", "buy")
        self.assertGreater(hostile, neutral)
        with self.assertRaises(GameError):
            game.command("again-rook", "advance_expedition", expedition_id=expedition_id)


if __name__ == "__main__":
    unittest.main()
