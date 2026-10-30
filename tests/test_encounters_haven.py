"""Discovery choices and headquarters construction use persistent physical goods."""

import time
import unittest

from tradenet.engine import ENCOUNTER_SITES, Game, GameError, HAVEN_FACILITIES


class EncountersAndHavenTests(unittest.TestCase):
    @staticmethod
    def dock(game, port):
        game.ship["location"] = port
        game._bind_ship()

    def test_first_arrival_opens_a_site_once_and_save_load_keeps_it(self):
        game = Game.new(17)
        self.assertEqual(game.encounters, {})
        game.ship["destination"] = "Kepler"
        game.ship["arrival_at"] = time.time() - 1
        game._all_arrivals()
        self.assertEqual(game.location, "Kepler")
        self.assertEqual(game.encounters["Kepler"]["status"], "open")
        self.assertEqual(game.encounters["Kepler"]["title"], "The Drifting Tug")
        game._all_arrivals()
        self.assertEqual(sum(row["action"] == "discover_site" for row in game.journal), 1)
        saved = Game.from_dict(game.to_dict())
        self.assertEqual(saved.encounters, game.encounters)

    def test_older_save_migrates_discoveries_and_facility_levels(self):
        old = Game.new(5).to_dict()
        del old["haven_facilities"]
        del old["encounters"]
        old["visited_ports"].append("Drift")
        migrated = Game.from_dict(old)
        self.assertEqual(set(migrated.haven_facilities), set(HAVEN_FACILITIES))
        self.assertEqual(migrated.encounters["Drift"]["status"], "open")
        self.assertEqual(Game.from_dict(migrated.to_dict()).to_dict(), migrated.to_dict())

    def test_all_remote_ports_have_an_encounter_with_a_safe_choice(self):
        self.assertEqual(set(ENCOUNTER_SITES), set(Game.new(3).ports) - {"Haven"})
        for site in ENCOUNTER_SITES.values():
            self.assertTrue(any(not any(key in option for key in ("fuel", "hull", "cargo"))
                                for option in site["choices"]))

    def test_encounter_consumes_supplies_pays_once_and_records_choice(self):
        game = Game.new(11)
        self.dock(game, "Vesper")
        game._reveal_encounter("Vesper")
        game.cargo["medicine"] = 2
        game.ship["export_cargo"]["medicine"] = 2
        before_stock = game.ports["Vesper"]["stock"]["medicine"]
        credits = game.credits
        faction = game.factions["scientists"]
        with self.assertRaises(GameError):
            game.command("wrong-port", "resolve_encounter", port="Kepler", choice="tow")
        result = game.command("quarantine", "resolve_encounter", port="Vesper", choice="treat")
        self.assertEqual(result["reward"], 210)
        self.assertEqual(game.credits, credits + 210)
        self.assertEqual(game.cargo["medicine"], 0)
        self.assertEqual(game.ship["export_cargo"]["medicine"], 0)
        self.assertEqual(game.ports["Vesper"]["stock"]["medicine"], before_stock + 2)
        self.assertEqual(game.factions["scientists"], faction + 3)
        self.assertEqual(game.command("quarantine", "resolve_encounter", port="Vesper", choice="treat"), result)
        with self.assertRaises(GameError):
            game.command("double", "resolve_encounter", port="Vesper", choice="scan")
        self.assertEqual(game.encounters["Vesper"]["choice"], "treat")
        self.assertEqual(Game.from_dict(game.to_dict()).encounters, game.encounters)

    def test_encounter_hull_fuel_and_salvage_constraints(self):
        game = Game.new(2)
        self.dock(game, "Drift")
        game._reveal_encounter("Drift")
        game.ship["condition"] = 13
        original = (game.ship["condition"], game.credits, dict(game.cargo),
                    game.encounters["Drift"]["status"])
        with self.assertRaises(GameError):
            game.command("not-safe", "resolve_encounter", port="Drift", choice="board")
        self.assertEqual((game.ship["condition"], game.credits, dict(game.cargo),
                          game.encounters["Drift"]["status"]), original)
        game.ship["condition"] = 100
        game.cargo["ore"] = game.ship["capacity"]
        with self.assertRaises(GameError):
            game.command("no-hold", "resolve_encounter", port="Drift", choice="board")
        self.assertEqual(game.encounters["Drift"]["status"], "open")
        game.cargo["ore"] = 0
        found = game.command("salvage", "resolve_encounter", port="Drift", choice="board")
        self.assertEqual(game.cargo["iridium"], 1)
        self.assertEqual(game.ship["condition"], 93)
        self.assertEqual(found["salvage"], {"iridium": 1})

    def test_haven_upgrade_requires_imported_goods_and_is_replay_safe(self):
        game = Game.new(9)
        with self.assertRaises(GameError):
            game.command("no-import", "upgrade_haven", facility="repair_bay")
        self.assertEqual(game.haven_facilities["repair_bay"], 0)
        game.cargo["ore"] = 3  # Haven stock is not eligible construction material.
        with self.assertRaises(GameError):
            game.command("home-ore", "upgrade_haven", facility="repair_bay")
        game.ship["export_cargo"]["ore"] = 3
        credits = game.credits
        built = game.command("build-repair", "upgrade_haven", facility="repair_bay")
        self.assertEqual(built["level"], 1)
        self.assertEqual(game.credits, credits - 240)
        self.assertEqual(game.cargo["ore"], 0)
        self.assertEqual(game.ship["export_cargo"]["ore"], 0)
        self.assertEqual(game.command("build-repair", "upgrade_haven", facility="repair_bay"), built)
        self.assertEqual(game.haven_facilities["repair_bay"], 1)
        self.assertEqual(Game.from_dict(game.to_dict()).haven_facilities, game.haven_facilities)
        game.ship["condition"] = 80
        self.assertEqual(game.command("repair", "repair")["cost"], 34)

    def test_storage_capacity_upgrade_and_location_requirement(self):
        game = Game.new(6)
        game.export_warehouse["food"] = 59
        game.cargo["food"] = 2
        game.ship["export_cargo"]["food"] = 2
        with self.assertRaises(GameError):
            game.command("full", "unload_export", good="food", amount=2)
        self.assertEqual(game.cargo["food"], 2)
        game.cargo["ore"] = 2
        game.ship["export_cargo"]["ore"] = 2
        self.dock(game, "Kepler")
        with self.assertRaises(GameError):
            game.command("remote-build", "upgrade_haven", facility="warehouse")
        self.dock(game, "Haven")
        game.command("storage", "upgrade_haven", facility="warehouse")
        self.assertEqual(game.haven_warehouse_capacity(), 100)
        game.command("now-fits", "unload_export", good="food", amount=2)
        self.assertEqual(game.export_warehouse["food"], 61)

    def test_intelligence_bonus_and_upgrade_limit(self):
        game = Game.new(12)
        game.haven_facilities["intelligence"] = 2
        self.dock(game, "Kepler")
        game._reveal_encounter("Kepler")
        result = game.command("tow", "resolve_encounter", port="Kepler", choice="log")
        self.assertEqual(result["reward"], 62)  # 50 * 1.25, rounded down
        self.dock(game, "Haven")
        with self.assertRaises(GameError):
            game.command("too-far", "upgrade_haven", facility="intelligence")

    def test_web_state_exposes_construction_quotes_without_rf_activity(self):
        from tests.test_radio_flow import station

        app = station("W1HQ", 9)
        app.radio_listener_status = "starting"
        app.radio_pending_replies = {}
        app.modem_catalog = {}
        app.game.clock_epoch = 6_000_000
        app.sync_clock = lambda: None
        before = app.state()
        self.assertEqual(before["haven_warehouse_capacity"], 60)
        self.assertEqual(before["haven_upgrades"]["repair_bay"]["credits"], 240)
        self.assertEqual(before["radio_transmissions"], [])
        app.game.haven_facilities["warehouse"] = 1
        after = app.state()
        self.assertEqual(after["haven_warehouse_capacity"], 100)
        self.assertEqual(after["haven_upgrades"]["warehouse"]["level"], 1)
        self.assertEqual(after["haven_upgrades"]["warehouse"]["quantity"], 4)


if __name__ == "__main__":
    unittest.main()
