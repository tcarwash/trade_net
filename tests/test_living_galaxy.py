"""Rival freight and repeatable local events are durable and strictly local."""

import unittest

from tradenet.engine import ENCOUNTER_INTERVAL, Game, GameError, NPC_INTERVAL


class LivingGalaxyTests(unittest.TestCase):
    @staticmethod
    def dock(game, port):
        game.ship["location"] = port
        game._bind_ship()

    def test_repeatable_encounter_requires_a_docked_choice_and_never_double_pays(self):
        game = Game.new(12)
        self.assertEqual(len(game.local_encounters), 1)
        event = next(iter(game.local_encounters.values()))
        self.assertEqual(event["source"], "local_simulation")
        choice = next(option for option in event["choices"] if not any(
            key in option for key in ("fuel", "hull", "cargo")))
        with self.assertRaises(GameError):
            game.command("wrong-port", "resolve_local_encounter",
                         incident_id=event["id"], choice=choice["id"])
        self.dock(game, event["port"])
        before = game.credits
        result = game.command("event", "resolve_local_encounter",
                              incident_id=event["id"], choice=choice["id"])
        self.assertEqual(game.credits, before + result["reward"])
        self.assertTrue(result["recurring"])
        self.assertEqual(game.command("event", "resolve_local_encounter",
                                      incident_id=event["id"], choice=choice["id"]), result)
        with self.assertRaises(GameError):
            game.command("event-repeat", "resolve_local_encounter",
                         incident_id=event["id"], choice=choice["id"])
        game.command("next-cycle", "wait", ticks=ENCOUNTER_INTERVAL)
        self.assertGreaterEqual(len(game.local_encounters), 2)
        self.assertEqual(game.local_encounters[event["id"]]["status"], "resolved")

    def test_old_encounter_expires_but_offline_catchup_does_not_backfill(self):
        game = Game.new(5)
        first = next(iter(game.local_encounters.values()))["id"]
        game.command("go", "wait", ticks=ENCOUNTER_INTERVAL * 3)
        self.assertEqual(game.local_encounters[first]["status"], "expired")
        self.assertEqual(len(game.local_encounters), 4)
        saved = game.to_dict()
        saved.pop("local_encounters")
        migrated = Game.from_dict(saved)
        self.assertEqual(len(migrated.local_encounters), 1)
        self.assertEqual(next(iter(migrated.local_encounters.values()))["start_tick"], 36)
        migrated.clock_epoch = 1_000
        migrated.sync_utc((1_000 + 2_000) * migrated.tick_seconds)
        self.assertLessEqual(len(migrated.local_encounters), 16)
        self.assertEqual(sum(x["status"] == "open" for x in migrated.local_encounters.values()), 1)

    def test_npc_can_claim_a_contract_and_player_can_win_a_different_one(self):
        game = Game.new(9)
        game.command("tick5", "wait", ticks=5)
        job = next(j for j in game.local_jobs.values() if j.get("kind") == "rival" and j["status"] == "open")
        self.assertTrue(job["id"].startswith("rival-"))
        self.assertGreater(job["deadline"], game.tick)
        captain = game.npc_captains[job["npc_id"]]
        self.dock(game, job["destination"])
        game.cargo[job["good"]] = job["quantity"]
        prior = captain["relationship"]
        won = game.command("race", "deliver_local", job_id=job["id"])
        self.assertEqual(won["kind"], "rival")
        self.assertEqual(won["captain"], captain["name"])
        self.assertEqual(captain["relationship"], prior + 1)
        self.assertEqual(game.command("race", "deliver_local", job_id=job["id"]), won)

        fresh = Game.new(9)
        fresh.command("wait19", "wait", ticks=19)
        claimed = [j for j in fresh.local_jobs.values() if j.get("kind") == "rival" and j["status"] == "claimed"]
        self.assertTrue(claimed)
        job_id = claimed[0]["id"]
        claims = [e for e in fresh.journal if e["action"] == "npc_claim" and e["result"]["job_id"] == job_id]
        self.assertEqual(len(claims), 1)
        fresh.command("wait-another", "wait", ticks=NPC_INTERVAL)
        self.assertEqual(len([e for e in fresh.journal if e["action"] == "npc_claim" and
                              e["result"]["job_id"] == job_id]), 1)

    def test_faction_followup_arrives_later_and_can_be_delivered(self):
        game = Game.new(3)
        mission = "expedition-blackwake"
        game.command("start", "accept_expedition", expedition_id=mission)
        self.dock(game, "Kepler")
        game.cargo["fuel"] = 4
        game.command("load", "advance_expedition", expedition_id=mission)
        self.dock(game, "Drift")
        game.command("choice", "advance_expedition", expedition_id=mission, choice="patrol")
        self.dock(game, "Haven")
        game.command("finish", "advance_expedition", expedition_id=mission)
        followup = game.faction_followups[mission]
        self.assertEqual(followup["status"], "pending")
        self.assertEqual(followup["due_tick"], game.tick + 12)
        self.assertFalse(followup["friendly"])
        game.command("return", "wait", ticks=13)
        followup = game.faction_followups[mission]
        self.assertEqual(followup["status"], "available")
        job = game.local_jobs[followup["job_id"]]
        self.assertEqual(job["destination"], "Haven")
        self.assertEqual(job["kind"], "followup")
        self.assertEqual(job["quantity"], 3)
        self.assertEqual(job["deadline"], game.tick + 30)
        game.cargo[job["good"]] = job["quantity"]
        reward = game.command("reconcile", "deliver_local", job_id=job["id"])
        self.assertEqual(reward["kind"], "followup")
        self.assertEqual(game.faction_followups[mission]["status"], "completed")
        self.assertEqual(Game.from_dict(game.to_dict()).faction_followups, game.faction_followups)

    def test_friendly_followup_gives_a_more_generous_delivery_window(self):
        game = Game.new(17)
        game.faction_followups["old-favor"] = {
            "expedition_id": "old-favor", "npc_id": "mara-venn", "status": "pending",
            "due_tick": game.tick, "friendly": True,
            "title": "A Favor from Mara Venn", "description": "Priority provisions."}
        game._advance_faction_followups()
        job = game.local_jobs["followup-old-favor"]
        self.assertEqual(job["quantity"], 2)
        self.assertEqual(job["deadline"], game.tick + 48)

    def test_web_local_encounter_never_enters_radio_ledgers(self):
        from tests.test_radio_flow import station

        app = station("W1LOCAL", 12)
        event = next(iter(app.game.local_encounters.values()))
        option = next(option for option in event["choices"] if not any(
            key in option for key in ("fuel", "hull", "cargo")))
        self.dock(app.game, event["port"])
        result = app.execute({"id": "solo-encounter", "action": "resolve_local_encounter",
                              "args": {"incident_id": event["id"], "choice": option["id"]}})
        self.assertTrue(result["recurring"])
        self.assertEqual(app.radio_transmissions, {})
        self.assertEqual(app.radio_contacts, {})
        self.assertEqual(app.radio_reservations, {})


if __name__ == "__main__":
    unittest.main()
