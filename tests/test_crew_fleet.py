"""Player-owned crews and fleet logistics are durable, local gameplay."""

import unittest
from copy import deepcopy

from tradenet.engine import Game, GameError


class CrewFleetTests(unittest.TestCase):
    @staticmethod
    def add_crew(game, role, *, ship_id=None, level=1, xp=0):
        ident = f"crew-{len(game.crew_roster) + 1}"
        game.crew_roster[ident] = {
            "id": ident, "name": f"Test {role.title()}", "role": role,
            "level": level, "xp": xp,
            "ship_id": ship_id or game.active_ship_id,
            "location": game.location, "origin": "Haven",
        }
        return ident

    def test_recruitment_is_deterministic_and_persists_without_duplicate_hires(self):
        game = Game.new(15)
        candidate = game.crew_candidates()[0]
        self.assertEqual(candidate, Game.new(15).crew_candidates()[0])
        starting_credits = game.credits
        hire = game.command("hire", "hire_crew", candidate_id=candidate["id"])
        self.assertEqual(game.credits, starting_credits - candidate["cost"])
        self.assertEqual(hire["ship_id"], game.active_ship_id)
        self.assertNotIn(candidate["id"], [c["id"] for c in game.crew_candidates()])
        self.assertEqual(game.command("hire", "hire_crew", candidate_id=candidate["id"]), hire)
        with self.assertRaises(GameError):
            game.command("duplicate", "hire_crew", candidate_id=candidate["id"])
        loaded = Game.from_dict(game.to_dict())
        self.assertEqual(loaded.crew_roster, game.crew_roster)
        self.assertEqual(loaded.recruited_candidates, game.recruited_candidates)
        self.assertEqual(len(loaded.crew_candidates()), 2)

    def test_recruit_at_correct_port_and_offers_cycle(self):
        game = Game.new(2)
        haven_offer = game.crew_candidates()[0]
        game.ship["location"] = "Kepler"
        game._bind_ship()
        with self.assertRaises(GameError):
            game.command("wrong-port", "hire_crew", candidate_id=haven_offer["id"])
        game.tick = 144
        self.assertNotIn(haven_offer["id"], [c["id"] for c in game.crew_candidates("Haven")])

    def test_pilot_engineer_reduce_fuel_wear_and_gain_experience(self):
        plain, staffed = Game.new(3), Game.new(3)
        for game in (plain, staffed):
            game.blocked_port = lambda: "Eidolon"
        pilot = self.add_crew(staffed, "pilot", level=2)
        engineer = self.add_crew(staffed, "engineer", level=2)
        basic = plain.command("go", "travel", destination="Kepler")
        enhanced = staffed.command("go", "travel", destination="Kepler")
        self.assertEqual(enhanced["fuel_cost"], max(1, basic["fuel_cost"] - 2))
        self.assertLessEqual(enhanced["travel_seconds"], basic["travel_seconds"])
        self.assertGreater(staffed.ship["condition"], plain.ship["condition"])
        self.assertEqual(staffed.crew_roster[pilot]["xp"], 1)
        self.assertEqual(staffed.crew_roster[engineer]["xp"], 1)
        staffed.award_crew_experience(staffed.active_ship_id, "pilot", 8)
        self.assertEqual(staffed.crew_roster[pilot]["level"], 3)

    def test_broker_bonus_stacks_with_haven_local_freight_only(self):
        game = Game.new(7)
        crew_id = self.add_crew(game, "broker", level=2)
        game.haven_facilities["logistics"] = 1
        game.local_jobs["crew-haven"] = {
            "id": "crew-haven", "origin": "Kepler", "destination": "Haven",
            "good": "food", "quantity": 2, "reward": 100,
            "status": "open", "deadline": game.tick + 40,
        }
        game.cargo["food"] = 2
        result = game.command("deliver", "deliver_local", job_id="crew-haven")
        self.assertEqual(result["reward"], 121)
        self.assertEqual(game.crew_roster[crew_id]["xp"], 2)

    def test_crew_transfer_requires_colocation_and_role_slots(self):
        game = Game.new(9)
        game.credits += 2000
        second = game.command("buy-ship", "purchase_ship", tier=1)["ship_id"]
        pilot = self.add_crew(game, "pilot")
        transferred = game.command("move-pilot", "assign_crew", crew_id=pilot, ship_id=second)
        self.assertEqual(transferred["ship_id"], second)
        self.assertIsNone(game.crew_member("ship-1", "pilot"))
        with self.assertRaises(GameError):
            game.command("duplicate-role", "assign_crew", crew_id=pilot, ship_id=second)
        moved = game.command("disembark", "unassign_crew", crew_id=pilot)
        self.assertEqual(moved["port"], "Haven")
        self.assertIsNone(game.crew_roster[pilot]["ship_id"])
        game.fleet[second]["location"] = "Kepler"
        with self.assertRaises(GameError):
            game.command("remote-crew", "assign_crew", crew_id=pilot, ship_id=second)

    def test_crew_roles_and_berths_cannot_be_duplicated(self):
        game = Game.new(9)
        game.credits += 2000
        second = game.command("buy-ship", "purchase_ship", tier=0)["ship_id"]
        pilot = self.add_crew(game, "pilot")
        another_pilot = self.add_crew(game, "pilot", ship_id=second)
        with self.assertRaises(GameError):
            game.command("same-role", "assign_crew", crew_id=another_pilot,
                         ship_id=game.active_ship_id)
        self.add_crew(game, "engineer")
        broker = self.add_crew(game, "broker", ship_id=second)
        with self.assertRaises(GameError):
            game.command("full-ship", "assign_crew", crew_id=broker,
                         ship_id=game.active_ship_id)
        self.assertEqual(game.crew_roster[pilot]["ship_id"], game.active_ship_id)

    def test_reserve_crew_cannot_teleport_between_identically_named_ports(self):
        game = Game.new(12)
        game.credits += 2000
        other_ship = game.command("buy-ship", "purchase_ship", tier=1)["ship_id"]
        reserve = self.add_crew(game, "broker")
        game.crew_roster[reserve].update(ship_id=None, location="Haven", galaxy="home")
        game.galaxies["other"] = deepcopy(game.galaxies["home"])
        game.fleet[other_ship]["galaxy"] = "other"
        game.command("switch", "select_ship", ship_id=other_ship)
        with self.assertRaises(GameError):
            game.command("no-teleport", "assign_crew", crew_id=reserve,
                         ship_id=other_ship)
        self.assertEqual(game.crew_roster[reserve]["galaxy"], "home")

    def test_cargo_transfer_keeps_import_provenance_and_obeys_capacity(self):
        game = Game.new(10)
        game.credits += 2000
        target = game.command("new-ship", "purchase_ship", tier=1)["ship_id"]
        game.cargo["food"] = 5
        game.ship["export_cargo"]["food"] = 3
        move = game.command("move-2", "transfer_cargo", source_id="ship-1",
                            destination_id=target, good="food", amount=2)
        self.assertEqual(move["imported"], 2)
        self.assertEqual(game.fleet["ship-1"]["cargo"]["food"], 3)
        self.assertEqual(game.fleet["ship-1"]["export_cargo"]["food"], 1)
        self.assertEqual(game.fleet[target]["export_cargo"]["food"], 2)
        with self.assertRaises(GameError):
            game.command("too-many", "transfer_cargo", source_id="ship-1",
                         destination_id=target, good="food", amount=30)
        game.fleet[target]["location"] = "Kepler"
        with self.assertRaises(GameError):
            game.command("apart", "transfer_cargo", source_id="ship-1",
                         destination_id=target, good="food", amount=1)

    def test_signal_officer_reduces_actual_radio_failure_hull_penalty(self):
        game = Game.new(5)
        game.hard_mode = True
        ship_id = game.active_ship_id
        game.ship["condition"] = 7
        self.add_crew(game, "signal", level=2)
        saved = game.to_dict()
        result = game.damage_ship(ship_id, 10, "Haven")
        self.assertFalse(result["destroyed"])
        self.assertEqual(result["damage_prevented"], 4)
        self.assertEqual(game.fleet[ship_id]["condition"], 1)
        unstaffed = Game.from_dict(saved)
        unstaffed.crew_roster.clear()
        self.assertTrue(unstaffed.damage_ship(ship_id, 10, "Haven")["destroyed"])

    def test_rename_ship_and_loss_do_not_orphan_crew(self):
        game = Game.new(7)
        crew_id = self.add_crew(game, "engineer")
        receipt = game.command("rename", "rename_ship", ship_id=game.active_ship_id,
                               name="The Unreasonable Profit")
        self.assertEqual(receipt["name"], "The Unreasonable Profit")
        with self.assertRaises(GameError):
            game.command("bad-rename", "rename_ship", ship_id=game.active_ship_id, name="\n")
        game.hard_mode = True
        game.ship["condition"] = 1
        game.damage_ship(game.active_ship_id, 10, "Haven")
        self.assertIsNone(game.crew_roster[crew_id]["ship_id"])
        self.assertEqual(game.crew_roster[crew_id]["location"], "Haven")
        self.assertEqual(Game.from_dict(game.to_dict()).crew_roster[crew_id]["location"], "Haven")


if __name__ == "__main__":
    unittest.main()
