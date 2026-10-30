"""Persistent multi-vessel policies must not spend beyond guardrails or touch RF."""

import time
import unittest
from unittest.mock import patch

from tradenet.engine import Game, GameError


CLEAR = {"kind": "clear", "label": "Clear corridor", "damage": 0}


class FleetDoctrineTests(unittest.TestCase):
    def setUp(self):
        self.game = Game.new(31)
        self.game.credits = 10000
        self.game.command("ship", "purchase_ship", tier=0)
        self.extra_id = next(sid for sid in self.game.fleet if sid != self.game.active_ship_id)
        self.game.visited_ports.append("Kepler")
        self.game.ship["location"] = "Kepler"
        self.game._bind_ship()
        self.game.observe_markets()
        self.game.ship["location"] = "Haven"
        self.game._bind_ship()
        self.block = patch.object(Game, "blocked_port", return_value="Eidolon")
        self.risk = patch.object(Game, "route_risk", return_value=CLEAR)
        self.block.start()
        self.risk.start()
        self.addCleanup(self.block.stop)
        self.addCleanup(self.risk.stop)

    def arrive(self):
        ship = self.game.fleet[self.extra_id]
        self.assertIsNotNone(ship["destination"])
        ship["arrival_at"] = time.time() - 1
        self.game._all_arrivals()

    def test_standing_warehouse_target_dispatches_non_selected_ship_and_stops_at_goal(self):
        active = self.game.active_ship_id
        result = self.game.command("target", "set_warehouse_target", good="food", source="Kepler",
                                   target=4, quantity=2)
        self.assertEqual(result["target"], 4)
        self.assertEqual(self.game.active_ship_id, active)
        self.assertEqual(self.game.fleet[self.extra_id]["auto_route"]["standing_target"], "food")
        self.arrive()
        self.arrive()
        self.assertEqual(self.game.export_warehouse["food"], 2)
        self.game.tick += 1
        self.game._all_arrivals()
        self.arrive()
        self.arrive()
        self.assertEqual(self.game.export_warehouse["food"], 4)
        self.game.tick += 1
        self.game._all_arrivals()
        self.assertEqual(self.game.fleet[self.extra_id]["auto_route"]["status"], "completed")
        self.assertIsNone(self.game.fleet[self.extra_id]["destination"])
        self.assertEqual(Game.from_dict(self.game.to_dict()).warehouse_targets["food"]["target"], 4)
        self.assertFalse(any(j["action"] == "jump" for j in self.game.journal))

    def test_budget_and_source_discovery_guard_automated_purchase(self):
        self.game.price_memory["food"]["by_port"].pop("Kepler", None)
        self.game.command("target", "set_warehouse_target", good="food", source="Kepler",
                          target=4, quantity=2)
        self.assertFalse(self.game.fleet[self.extra_id].get("auto_route"))
        self.game.command("reserve", "set_fleet_reserve", credits=9999)
        self.game.ship["location"] = "Kepler"
        self.game._bind_ship()
        self.game.observe_markets()
        self.game.ship["location"] = "Haven"
        self.game._bind_ship()
        self.game.tick += 1
        self.game._all_arrivals()
        self.assertFalse(self.game.fleet[self.extra_id].get("auto_route"))
        self.game.command("reserve2", "set_fleet_reserve", credits=350)
        self.game._all_arrivals()
        self.assertEqual(self.game.fleet[self.extra_id]["auto_route"]["standing_target"], "food")

    def test_service_policy_respects_floor_and_never_changes_selected_ship(self):
        ship = self.game.fleet[self.extra_id]
        ship["condition"] = 40
        ship["fuel"] = 4
        self.game.command("policy", "set_fleet_policy", ship_id=self.extra_id,
                          return_to_haven=True, auto_service=True,
                          repair_below=60, fuel_below=35)
        selected = self.game.active_ship_id
        self.game._all_arrivals()
        self.assertEqual(ship["condition"], 100)
        self.assertGreater(ship["fuel"], 4)
        self.assertEqual(self.game.active_ship_id, selected)
        self.assertTrue(any(j["action"] == "fleet_auto_repair" for j in self.game.journal))
        self.assertTrue(any(j["action"] == "fleet_auto_refuel" for j in self.game.journal))
        self.game.command("tight-budget", "set_fleet_reserve", credits=self.game.credits)
        ship["condition"] = 30
        self.game._all_arrivals()
        self.assertEqual(ship["condition"], 30)

    def test_assigned_captain_gains_command_experience_and_unassign_clears_role(self):
        self.game.command("select", "select_ship", ship_id=self.extra_id)
        candidate = self.game.crew_candidates()[0]
        crew_id = self.game.command("hire", "hire_crew", candidate_id=candidate["id"])["crew_id"]
        promoted = self.game.command("captain", "designate_captain", ship_id=self.extra_id, crew_id=crew_id)
        self.assertEqual(promoted["captain"], candidate["name"])
        route = self.game.command("route", "start_auto_route", ship_id=self.extra_id,
                                  origin="Haven", destination="Kepler", good="food",
                                  quantity=1, max_runs=1)
        self.assertEqual(route["route"]["status"], "running")
        self.arrive()
        self.assertEqual(self.game.crew_roster[crew_id]["command_xp"], 1)
        self.game.command("disembark", "unassign_crew", crew_id=crew_id)
        self.assertIsNone(self.game.fleet[self.extra_id]["captain_id"])

    def test_policy_validation_and_warehouse_capacity_are_atomic(self):
        snapshot = self.game.to_dict()
        with self.assertRaises(GameError):
            self.game.command("bad-policy", "set_fleet_policy", ship_id=self.extra_id,
                              return_to_haven="yes", auto_service=True,
                              repair_below=50, fuel_below=50)
        with self.assertRaises(GameError):
            self.game.command("bad-target", "set_warehouse_target", good="food",
                              source="Kepler", target=self.game.haven_warehouse_capacity() + 1)
        self.assertEqual(self.game.warehouse_targets, snapshot["warehouse_targets"])

    def test_idle_gather_is_opt_out_and_never_overrides_selected_ship(self):
        ship = self.game.fleet[self.extra_id]
        ship["location"] = "Kepler"
        self.game.command("opt-out", "set_fleet_policy", ship_id=self.extra_id,
                          return_to_haven=False, auto_service=False,
                          repair_below=65, fuel_below=35)
        self.game._all_arrivals()
        self.assertEqual(ship["location"], "Kepler")
        self.assertIsNone(ship.get("destination"))
        self.game.command("opt-in", "set_fleet_policy", ship_id=self.extra_id,
                          return_to_haven=True, auto_service=False,
                          repair_below=65, fuel_below=35)
        self.game._all_arrivals()
        self.assertEqual(ship["destination"], "Haven")
        self.assertEqual(self.game.active_ship_id, "ship-1")

    def test_new_ship_receives_independent_persistent_defaults(self):
        ship = self.game.fleet[self.extra_id]
        self.assertIsNone(ship["captain_id"])
        self.assertEqual(ship["fleet_policy"]["repair_below"], 65)
        self.game.command("reserve", "set_fleet_reserve", credits=1250)
        self.game.command("policy", "set_fleet_policy", ship_id=self.extra_id,
                          return_to_haven=False, auto_service=True,
                          repair_below=50, fuel_below=25)
        other = Game.from_dict(self.game.to_dict())
        self.assertEqual(other.fleet_credit_reserve, 1250)
        self.assertFalse(other.fleet[self.extra_id]["fleet_policy"]["return_to_haven"])
        self.assertTrue(other.fleet[self.extra_id]["fleet_policy"]["auto_service"])
        self.assertTrue(other.fleet[other.active_ship_id]["fleet_policy"]["return_to_haven"])


if __name__ == "__main__":
    unittest.main()
