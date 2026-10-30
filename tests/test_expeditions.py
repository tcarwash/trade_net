"""The solo expedition state machine is physical, persistent, and replay-safe."""

import unittest

from tradenet.engine import Game, GameError


class ExpeditionTests(unittest.TestCase):
    @staticmethod
    def dock(game, port):
        game.ship["location"] = port
        game._bind_ship()

    def test_authored_missions_and_older_save_migration(self):
        game = Game.new(13)
        self.assertEqual(set(game.expeditions), {"expedition-relief", "expedition-beacon",
                                                 "expedition-embers", "expedition-archive",
                                                 "expedition-blackwake"})
        old_save = game.to_dict()
        del old_save["expeditions"]
        migrated = Game.from_dict(old_save)
        self.assertEqual(set(migrated.expeditions), set(game.expeditions))
        self.assertEqual(migrated.to_dict(), Game.from_dict(migrated.to_dict()).to_dict())

        old_two = game.to_dict()
        old_two["expeditions"] = {name: game.expeditions[name]
                                  for name in ("expedition-relief", "expedition-beacon")}
        old_two["expeditions"]["expedition-relief"]["status"] = "completed"
        restored = Game.from_dict(old_two)
        self.assertEqual(restored.expeditions["expedition-relief"]["status"], "completed")
        self.assertEqual(set(restored.expeditions), set(game.expeditions))

    def test_relief_mission_requires_market_cargo_and_a_choice(self):
        game = Game.new(8)
        mission_id = "expedition-relief"
        first = game.command("exp-start", "accept_expedition", expedition_id=mission_id)
        self.assertEqual(first["next"]["port"], "Aurora")
        with self.assertRaises(GameError):
            game.command("exp-second", "accept_expedition", expedition_id="expedition-beacon")
        with self.assertRaises(GameError):
            game.command("exp-too-soon", "advance_expedition", expedition_id=mission_id)
        self.dock(game, "Aurora")
        with self.assertRaises(GameError):
            game.command("exp-no-stock", "advance_expedition", expedition_id=mission_id)
        game.command("exp-buy", "buy", good="medicine", amount=3)
        game.command("exp-load", "advance_expedition", expedition_id=mission_id)
        self.assertEqual(game.expeditions[mission_id]["stage"], 1)
        self.dock(game, "Bastion")
        with self.assertRaises(GameError):
            game.command("exp-no-choice", "advance_expedition", expedition_id=mission_id)
        before_stock = game.ports["Bastion"]["stock"]["medicine"]
        before_reputation = game.factions["scientists"]
        choice = game.command("exp-choice", "advance_expedition",
                              expedition_id=mission_id, choice="clinic")
        self.assertEqual(choice["next"]["port"], "Haven")
        self.assertEqual(game.cargo["medicine"], 0)
        self.assertEqual(game.ports["Bastion"]["stock"]["medicine"], before_stock + 3)
        self.assertEqual(game.factions["scientists"], before_reputation)
        self.assertEqual(game.command("exp-choice", "advance_expedition",
                                      expedition_id=mission_id, choice="clinic"), choice)
        self.dock(game, "Haven")
        credits = game.credits
        completed = game.command("exp-finish", "advance_expedition", expedition_id=mission_id)
        self.assertTrue(completed["completed"])
        self.assertEqual(completed["reward"], 470 + 90 + 100)
        self.assertEqual(game.credits, credits + completed["reward"])
        self.assertEqual(game.factions["scientists"], before_reputation + 3)
        self.assertEqual(game.command("exp-finish", "advance_expedition",
                                      expedition_id=mission_id), completed)
        with self.assertRaises(GameError):
            game.command("exp-double", "advance_expedition", expedition_id=mission_id)
        self.assertEqual(Game.from_dict(game.to_dict()).to_dict(), game.to_dict())

    def test_alternate_choice_and_overdue_completion(self):
        game = Game.new(4)
        mission_id = "expedition-beacon"
        game.command("beacon-start", "accept_expedition", expedition_id=mission_id)
        self.dock(game, "Prospect")
        game.command("ore", "buy", good="ore", amount=2)
        prior_miners = game.factions["miners"]
        game.command("ore-loaded", "advance_expedition", expedition_id=mission_id)
        self.dock(game, "Eidolon")
        game.command("salvaged", "advance_expedition",
                     expedition_id=mission_id, choice="salvage")
        self.dock(game, "Haven")
        game.command("long-pause", "wait", ticks=60)
        completed = game.command("report", "advance_expedition", expedition_id=mission_id)
        self.assertEqual(completed["reward"], 560 + 120)
        self.assertEqual(game.factions["miners"], prior_miners + 3)
        self.assertEqual(game.expeditions[mission_id]["choice"], "salvage")

    def test_abandon_preserves_cargo_and_can_restart(self):
        game = Game.new(6)
        mission_id = "expedition-relief"
        game.command("start", "accept_expedition", expedition_id=mission_id)
        self.dock(game, "Aurora")
        game.command("buy", "buy", good="medicine", amount=3)
        game.command("stage", "advance_expedition", expedition_id=mission_id)
        cancelled = game.command("abandon", "abandon_expedition", expedition_id=mission_id)
        self.assertEqual(cancelled["status"], "offered")
        self.assertEqual(game.cargo["medicine"], 3)
        self.assertEqual(game.expeditions[mission_id]["stage"], 0)
        with self.assertRaises(GameError):
            game.command("restart-remote", "accept_expedition", expedition_id=mission_id)
        self.dock(game, "Haven")
        game.command("restart", "accept_expedition", expedition_id=mission_id)
        self.assertEqual(game.expeditions[mission_id]["stage"], 0)


if __name__ == "__main__":
    unittest.main()
