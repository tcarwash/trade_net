"""Local fleet autopilot handles trade runs without silently using RF transport."""

import time
import unittest
from unittest.mock import patch

from tradenet.engine import Game, GameError, RARE


CLEAR = {"kind": "clear", "label": "Clear corridor", "damage": 0}
PIRATES = {"kind": "pirates", "label": "Pirate ambush", "damage": 9}


class FleetAutomationTests(unittest.TestCase):
    def setUp(self):
        self.game = Game.new(11)
        self.game.credits = 10000
        self.blocked = patch.object(Game, "blocked_port", return_value="Eidolon")
        self.risk = patch.object(Game, "route_risk", return_value=CLEAR)
        self.blocked.start()
        self.risk.start()
        self.addCleanup(self.blocked.stop)
        self.addCleanup(self.risk.stop)

    def start(self, *, ship_id="ship-1", good="food", runs=2, source="Haven", destination="Kepler"):
        return self.game.command(f"start-{ship_id}-{good}", "start_auto_route", ship_id=ship_id,
                                 origin=source, destination=destination,
                                 good=good, quantity=2, max_runs=runs)

    def arrive(self, ship_id="ship-1"):
        ship = self.game.fleet[ship_id]
        self.assertIsNotNone(ship["destination"], "the route must be in transit")
        ship["arrival_at"] = time.time() - 1
        self.game._all_arrivals()

    def test_live_market_trade_and_multiple_runs_with_discovery_interruption(self):
        initial_stock = self.game.galaxies["home"]["ports"]["Haven"]["stock"]["food"]
        start = self.start()
        self.assertEqual(start["route"]["status"], "running")
        self.assertEqual(self.game.ship["cargo"]["food"], 2)
        self.assertEqual(self.game.galaxies["home"]["ports"]["Haven"]["stock"]["food"], initial_stock - 2)
        self.arrive()
        self.assertEqual(self.game.ship["auto_route"]["pause_code"], "discovery")
        self.assertEqual(self.game.ship["cargo"]["food"], 2)
        self.game.command("resume-discovery", "resume_auto_route", ship_id="ship-1")
        route = self.game.ship["auto_route"]
        self.assertEqual(route["completed_runs"], 1)
        self.assertEqual(self.game.ship["cargo"]["food"], 0)
        self.assertEqual(route["profit"], route["earned"] - route["spent"])

        self.game.tick += 1
        self.game._all_arrivals()  # Leaves Kepler for Haven after the throttle tick.
        self.arrive()             # Arrives at Haven, reloads, heads to Kepler.
        self.arrive()             # Arrives at already-discovered Kepler and sells.
        self.assertEqual(route["status"], "completed")
        self.assertEqual(route["completed_runs"], 2)
        self.assertEqual(route["profit"], route["earned"] - route["spent"])
        self.assertEqual(len([j for j in self.game.journal if j["action"] == "auto_route_delivery"]), 2)
        self.assertFalse(self.game.ship.get("radio_mission"))
        self.assertEqual(len([j for j in self.game.journal if j["action"] == "jump"]), 0)

    def test_route_quotes_remember_only_docked_market_observations(self):
        self.assertIn("Haven", self.game.price_memory["food"]["by_port"])
        self.assertNotIn("Kepler", self.game.price_memory["food"]["by_port"])
        self.start(runs=1)
        self.assertNotIn("Kepler", self.game.price_memory["food"]["by_port"])
        self.arrive()
        self.assertIn("Kepler", self.game.price_memory["food"]["by_port"])
        self.assertEqual(self.game.price_memory["food"]["by_port"]["Kepler"]["tick"], self.game.tick)

    def test_idle_ship_stockpiles_imports_at_haven_without_transmitting(self):
        second = self.game.command("commission", "purchase_ship", tier=0)["ship_id"]
        original = self.game.active_ship_id
        source_stock = self.game.galaxies["home"]["ports"]["Kepler"]["stock"]["food"]
        receipt = self.game.command("procure", "dispatch_haven_supply", origin="Kepler",
                                    good="food", quantity=2, max_runs=1)
        self.assertEqual(receipt["ship_id"], second)
        self.assertEqual(self.game.active_ship_id, original)
        self.arrive(second)
        self.assertEqual(self.game.fleet[second]["auto_route"]["pause_code"], "discovery")
        self.game.command("resume-procure", "resume_auto_route", ship_id=second)
        self.assertEqual(self.game.fleet[second]["cargo"]["food"], 2)
        self.arrive(second)
        route = self.game.fleet[second]["auto_route"]
        self.assertEqual(route["status"], "completed")
        self.assertEqual(route["delivered"], 2)
        self.assertEqual(self.game.export_warehouse["food"], 2)
        self.assertEqual(self.game.fleet[second]["export_cargo"]["food"], 0)
        self.assertEqual(self.game.galaxies["home"]["ports"]["Kepler"]["stock"]["food"], source_stock - 2)
        self.assertFalse(self.game.fleet[second].get("radio_mission"))
        self.assertFalse(any(j["action"] == "jump" for j in self.game.journal))

    def test_haven_procurement_pauses_before_buying_when_warehouse_is_full(self):
        self.game.ship["location"] = "Kepler"
        self.game._bind_ship()
        self.game.export_warehouse["ore"] = self.game.haven_warehouse_capacity()
        before_credits = self.game.credits
        route = self.game.command("procure", "dispatch_haven_supply", origin="Kepler",
                                  good="food", quantity=3, max_runs=2)["route"]
        self.assertEqual(route["pause_code"], "warehouse")
        self.assertEqual(self.game.credits, before_credits)
        self.assertEqual(self.game.ship["cargo"]["food"], 0)

    def test_unassigned_idle_vessel_returns_to_haven_without_stealing_control(self):
        second = self.game.command("commission", "purchase_ship", tier=0)["ship_id"]
        ship = self.game.fleet[second]
        ship["location"] = "Kepler"
        selected = self.game.active_ship_id
        self.game._all_arrivals()
        self.assertEqual(ship["destination"], "Haven")
        self.assertEqual(self.game.active_ship_id, selected)
        self.assertEqual(self.game.ship["location"], "Haven")
        self.assertTrue(any(entry["action"] == "idle_ship_return" for entry in self.game.journal))
        self.arrive(second)
        self.assertEqual(ship["location"], "Haven")
        self.assertIsNone(ship["destination"])

    def test_idle_fleet_gathering_does_not_override_cargo_or_danger(self):
        second = self.game.command("commission", "purchase_ship", tier=0)["ship_id"]
        ship = self.game.fleet[second]
        ship["location"] = "Kepler"
        ship["cargo"]["food"] = 1
        self.game._all_arrivals()
        self.assertIsNone(ship["destination"])
        ship["cargo"]["food"] = 0
        with patch.object(Game, "route_risk", return_value=PIRATES):
            self.game._all_arrivals()
        self.assertIsNone(ship["destination"])

    def test_hazard_pauses_before_spending_fuel_then_explicit_stance_approves(self):
        with patch.object(Game, "route_risk", return_value=PIRATES):
            start = self.start()
            route = self.game.ship["auto_route"]
            self.assertEqual(start["route"]["pause_code"], "hazard")
            self.assertIsNone(self.game.ship["destination"])
            fuel = self.game.ship["fuel"]
            with self.assertRaises(GameError):
                self.game.command("resume-unsafe", "resume_auto_route", ship_id="ship-1")
            # A failed command restores the saved game without any travel.
            self.assertEqual(self.game.ship["fuel"], fuel)
            approved = self.game.command("approve-pirate", "approve_auto_leg", ship_id="ship-1", pirate_stance="evade")
            self.assertEqual(approved["route"]["status"], "running")
            self.assertEqual(self.game.ship["destination"], "Kepler")
            self.assertLess(self.game.ship["fuel"], fuel)

    def test_rare_freight_needs_approval_each_load(self):
        good = sorted(RARE)[0]
        self.game.galaxies["home"]["ports"]["Haven"]["stock"][good] = 50
        result = self.start(good=good, runs=2)
        self.assertEqual(result["route"]["pause_code"], "special_cargo")
        self.assertEqual(self.game.ship["cargo"][good], 0)
        self.game.command("approve-special", "approve_auto_leg", ship_id="ship-1")
        self.assertEqual(self.game.ship["cargo"][good], 2)
        self.assertEqual(self.game.ship["destination"], "Kepler")

    def test_automation_runs_on_inactive_ship_without_stealing_selection(self):
        new_ship = self.game.command("purchase", "purchase_ship", tier=0)["ship_id"]
        current = self.game.active_ship_id
        start = self.start(ship_id=new_ship, runs=1)
        self.assertEqual(start["route"]["status"], "running")
        self.assertEqual(self.game.active_ship_id, current)
        self.assertEqual(self.game.location, "Haven")
        self.assertEqual(self.game.ship, self.game.fleet[current])
        self.assertEqual(self.game.fleet[new_ship]["cargo"]["food"], 2)
        self.arrive(new_ship)
        self.assertEqual(self.game.active_ship_id, current)
        self.assertEqual(self.game.fleet[new_ship]["auto_route"]["pause_code"], "discovery")

    def test_manual_commands_cannot_disrupt_automatic_cargo_and_stop_keeps_it(self):
        self.start(runs=1)
        with self.assertRaises(GameError):
            self.game.command("manual-buy", "buy", good="ore", amount=1)
        with self.assertRaises(GameError):
            self.game.command("manual-travel", "travel", destination="Vesper")
        self.game.command("stop", "stop_auto_route", ship_id="ship-1")
        self.assertEqual(self.game.ship["auto_route"]["status"], "stopped")
        self.assertEqual(self.game.ship["cargo"]["food"], 2)

    def test_insufficient_supplies_pause_and_allow_recovery(self):
        self.game.galaxies["home"]["ports"]["Haven"]["stock"]["food"] = 0
        result = self.start()
        self.assertEqual(result["route"]["pause_code"], "supply")
        self.assertEqual(self.game.ship["cargo"]["food"], 0)
        self.game.galaxies["home"]["ports"]["Haven"]["stock"]["food"] = 10
        resumed = self.game.command("resume", "resume_auto_route", ship_id="ship-1")
        self.assertEqual(resumed["route"]["status"], "running")
        self.assertEqual(self.game.ship["cargo"]["food"], 2)

    def test_repair_and_refuel_only_while_paused(self):
        self.start()
        self.game.ship["condition"] = 88
        with self.assertRaises(GameError):
            self.game.command("repair-running", "repair")
        self.game.command("pause", "pause_auto_route", ship_id="ship-1")
        self.game.ship["destination"] = None
        self.game.ship["arrival_at"] = None
        self.game.command("repair-paused", "repair")
        self.assertEqual(self.game.ship["condition"], 100)

    def test_routes_are_durable_and_journal_ids_do_not_repeat(self):
        self.start(runs=1)
        self.game.command("pause", "pause_auto_route", ship_id="ship-1")
        loaded = Game.from_dict(self.game.to_dict())
        self.assertEqual(loaded.ship["auto_route"], self.game.ship["auto_route"])
        loaded.command("stop", "stop_auto_route", ship_id="ship-1")
        loaded.ship["destination"] = None
        loaded.ship.pop("arrival_at", None)
        loaded.ship["cargo"]["food"] = 0
        loaded.command("again", "start_auto_route", ship_id="ship-1", origin="Haven",
                       destination="Kepler", good="food", quantity=1, max_runs=1)
        ids = [entry["id"] for entry in loaded.journal]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
