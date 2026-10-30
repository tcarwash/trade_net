"""Authored faction arcs unlock durable perks or recurring rivals, never RF."""

import unittest
from unittest.mock import patch

from tradenet.engine import Game, GameError, NPC_INTERVAL


class FactionStorylineTests(unittest.TestCase):
    @staticmethod
    def dock(game, port):
        game.ship["location"] = port
        game._bind_ship()

    @staticmethod
    def unlock(game, npc_id, relationship):
        game.npc_captains[npc_id]["relationship"] = relationship
        game._refresh_faction_storylines()
        return game.faction_storylines[npc_id]

    def test_ally_arc_costs_real_cargo_and_grants_permanent_perk_once(self):
        game = Game.new(11)
        scene = self.unlock(game, "rin-kestrel", 3)
        self.assertEqual(scene["alignment"], "ally")
        self.assertEqual(scene["port"], "Prospect")
        self.assertEqual(scene["status"], "offered")
        with self.assertRaises(GameError):
            game.command("not-there", "resolve_faction_storyline",
                         npc_id="rin-kestrel", choice="charter")
        self.dock(game, "Prospect")
        game.cargo["ore"] = 2
        game.credits += 500
        start_credits, start_stock = game.credits, game.ports["Prospect"]["stock"]["ore"]
        result = game.command("pact", "resolve_faction_storyline",
                              npc_id="rin-kestrel", choice="charter")
        self.assertEqual(result["credits_delta"], -160)
        self.assertEqual(game.credits, start_credits - 160)
        self.assertEqual(game.cargo["ore"], 0)
        self.assertEqual(game.ports["Prospect"]["stock"]["ore"], start_stock + 2)
        self.assertEqual(game.npc_captains["rin-kestrel"]["relationship"], 4)
        self.assertIn("reinforced_plating", game.faction_perks)
        self.assertEqual(game.faction_storylines["rin-kestrel"]["status"], "resolved")
        self.assertEqual(game.command("pact", "resolve_faction_storyline",
                                      npc_id="rin-kestrel", choice="charter"), result)
        with self.assertRaises(GameError):
            game.command("farm-pact", "resolve_faction_storyline",
                         npc_id="rin-kestrel", choice="charter")
        reloaded = Game.from_dict(game.to_dict())
        self.assertEqual(reloaded.faction_perks, ["reinforced_plating"])
        self.assertEqual(len(reloaded.faction_storylines), 1)

    def test_alternative_ally_choice_pays_but_declines_perk(self):
        game = Game.new(3)
        scene = self.unlock(game, "mara-venn", 3)
        self.dock(game, scene["port"])
        before = game.credits
        result = game.command("advance", "resolve_faction_storyline",
                              npc_id="mara-venn", choice="cashout")
        self.assertEqual(game.credits, before + 180)
        self.assertEqual(result["choice"], "cashout")
        self.assertNotIn("trade_charter", game.faction_perks)
        self.assertEqual(game.npc_captains["mara-venn"]["relationship"], 2)

    def test_existing_saves_migrate_and_completed_expeditions_offer_stories(self):
        game = Game.new(3)
        saved = game.to_dict()
        for field in ("faction_storylines", "faction_perks", "captain_nemeses"):
            saved.pop(field)
        game = Game.from_dict(saved)
        self.assertEqual(game.faction_storylines, {})
        self.assertEqual(game.faction_perks, [])
        game.command("start", "accept_expedition", expedition_id="expedition-blackwake")
        self.dock(game, "Kepler")
        game.cargo["fuel"] = 4
        game.command("load", "advance_expedition", expedition_id="expedition-blackwake")
        self.dock(game, "Drift")
        game.command("choose", "advance_expedition", expedition_id="expedition-blackwake", choice="patrol")
        self.dock(game, "Haven")
        game.command("complete", "advance_expedition", expedition_id="expedition-blackwake")
        scene = game.faction_storylines["sable-rook"]
        self.assertEqual(scene["alignment"], "rival")
        self.assertEqual(scene["status"], "offered")
        self.assertEqual(sum(e["action"] == "faction_storyline_offered" for e in game.journal), 1)
        self.assertEqual(len(Game.from_dict(game.to_dict()).faction_storylines), 1)

    def test_vendetta_is_durable_and_generates_faster_rival_freight(self):
        game = Game.new(9)
        scene = self.unlock(game, "sable-rook", -3)
        self.dock(game, scene["port"])
        result = game.command("vendetta", "resolve_faction_storyline",
                              npc_id="sable-rook", choice="defy")
        self.assertTrue(result["nemesis"])
        self.assertIn("sable-rook", game.captain_nemeses)
        self.assertEqual(game.npc_captains["sable-rook"]["relationship"], -4)
        # Isolate the nemesis schedule from the other captains' open races.
        game.npc_captains = {"sable-rook": game.npc_captains["sable-rook"]}
        game.command("advance-nemesis", "wait", ticks=NPC_INTERVAL * 12)
        rival_jobs = [job for job in game.local_jobs.values()
                      if job.get("kind") == "rival" and job.get("npc_id") == "sable-rook"]
        self.assertTrue(rival_jobs)
        for job in rival_jobs:
            cycle = int(job["id"].rsplit("-", 1)[1])
            self.assertEqual(job["deadline"], cycle * NPC_INTERVAL - 1 + NPC_INTERVAL)
            self.assertIn("Vendetta", job["title"])
        self.assertIn("sable-rook", Game.from_dict(game.to_dict()).captain_nemeses)

    def test_truce_rehabilitates_relationship_without_creating_a_nemesis(self):
        game = Game.new(2)
        scene = self.unlock(game, "sable-rook", -3)
        self.dock(game, scene["port"])
        game.cargo["fuel"] = 2
        result = game.command("truce", "resolve_faction_storyline",
                              npc_id="sable-rook", choice="truce")
        self.assertFalse(result["nemesis"])
        self.assertEqual(game.npc_captains["sable-rook"]["relationship"], 0)
        self.assertNotIn("sable-rook", game.captain_nemeses)

    def test_perks_change_existing_economy_and_exploration_rules(self):
        market = Game.new(12)
        quote_before = market.captain_deal_quote("mara-venn")
        price_before = market.price("Meridian", "food", "buy")
        market.faction_perks.append("trade_charter")
        quote_after = market.captain_deal_quote("mara-venn")
        self.assertEqual(quote_before["max_quantity"], 3)
        self.assertEqual(quote_after["max_quantity"], 5)
        self.assertLess(market.price("Meridian", "food", "buy"), price_before)

        original = Game.new(19)
        survey = Game.from_dict(original.to_dict())
        survey.faction_perks.append("survey_uplink")
        for game in (original, survey):
            game.ship["destination"] = "Prospect"
            game.ship["arrival_at"] = 0
        credits_before = original.credits
        original._all_arrivals()
        survey._all_arrivals()
        self.assertEqual(survey.credits - original.credits, 45)
        self.assertGreater(original.credits, credits_before)

        # Both defensive perks work with the existing route damage/toll rules.
        base = Game.new(6)
        pair = next((a, b) for a in base.ports for b in base.ports
                    if a != b and base.route_risk(a, b)["kind"] == "pirates")
        regular, protected = Game.new(6), Game.new(6)
        for game in (regular, protected):
            self.dock(game, pair[0])
        protected.faction_perks.extend(("reinforced_plating", "pirate_codes"))
        with patch.object(Game, "blocked_port", return_value=pair[0]):
            normal = regular.command("fly", "travel", destination=pair[1], pirate_stance="pay")
            reduced = protected.command("fly", "travel", destination=pair[1], pirate_stance="pay")
        self.assertLessEqual(reduced["hazard_damage"], normal["hazard_damage"])
        self.assertEqual(reduced["hazard"]["toll"], normal["hazard"]["toll"] // 2)

    def test_web_storyline_action_has_no_radio_side_effects(self):
        from tests.test_radio_flow import station

        app = station("W1STORY", 5)
        scene = self.unlock(app.game, "mara-venn", 3)
        self.dock(app.game, scene["port"])
        outcome = app.execute({"id": "faction-cash", "action": "resolve_faction_storyline",
                               "args": {"npc_id": "mara-venn", "choice": "cashout"}})
        self.assertEqual(outcome["choice"], "cashout")
        self.assertEqual(app.radio_transmissions, {})
        self.assertEqual(app.radio_contacts, {})
        self.assertEqual(app.radio_reservations, {})


if __name__ == "__main__":
    unittest.main()
