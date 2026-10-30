"""Persistent captain relationships have real, local economic consequences."""

import unittest

from tradenet.engine import Game, GameError, INCIDENT_INTERVAL, SECTOR_INCIDENTS


class FactionConsequenceTests(unittest.TestCase):
    @staticmethod
    def dock(game, port):
        game.ship["location"] = port
        game._bind_ship()

    def test_private_lot_requires_trust_and_moves_real_stock_once(self):
        game = Game.new(4)
        captain = game.npc_captains["mara-venn"]
        locked = game.captain_deal_quote(captain["id"])
        self.assertFalse(locked["available"])
        captain["relationship"] = 2
        quote = game.captain_deal_quote(captain["id"])
        self.assertTrue(quote["available"])
        self.assertGreaterEqual(quote["unit_price"], game.price(quote["port"], quote["good"], "sell") + 1)
        stock_before = game.ports[quote["port"]]["stock"][quote["good"]]
        with self.assertRaises(GameError):
            game.command("off-port", "buy_captain_deal", npc_id=captain["id"], amount=2)
        self.dock(game, quote["port"])
        game.credits += 2000
        before = game.credits
        result = game.command("private-lot", "buy_captain_deal", npc_id=captain["id"], amount=2)
        self.assertEqual(result["total"], 2 * quote["unit_price"])
        self.assertEqual(game.credits, before - result["total"])
        self.assertEqual(game.cargo[quote["good"]], 2)
        self.assertEqual(game.ports[quote["port"]]["stock"][quote["good"]], stock_before - 2)
        self.assertEqual(game.ship["export_cargo"][quote["good"]], 2)
        self.assertLess(game.price(quote["port"], quote["good"], "sell"), quote["unit_price"])
        self.assertEqual(game.command("private-lot", "buy_captain_deal", npc_id=captain["id"], amount=2), result)
        with self.assertRaises(GameError):
            game.command("buy-again", "buy_captain_deal", npc_id=captain["id"], amount=1)
        self.assertEqual(Game.from_dict(game.to_dict()).captain_deals[captain["id"]], game.tick)

    def test_private_lots_cannot_be_immediately_flipped_for_profit(self):
        for seed in range(12):
            game = Game.new(seed)
            for captain in game.npc_captains.values():
                captain["relationship"] = 2
                quote = game.captain_deal_quote(captain["id"])
                stock = game.ports[quote["port"]]["stock"][quote["good"]]
                projected_sell = game.price(
                    quote["port"], quote["good"], "sell",
                    stock_override=stock - quote["max_quantity"])
                with self.subTest(seed=seed, captain=captain["id"]):
                    self.assertGreater(quote["unit_price"], projected_sell)

    def test_sector_support_spends_goodwill_and_changes_one_live_contract(self):
        game = Game.new(5)
        captain = game.npc_captains["mara-venn"]
        captain["relationship"] = 3
        event = game.active_sector_events()[0]
        job = game.local_jobs[event["id"]]
        old_reward, old_deadline = job["reward"], job["deadline"]
        with self.assertRaises(GameError):
            game.command("wrong-port", "request_sector_aid", event_id=event["id"], npc_id=captain["id"])
        captain = game.npc_captains["mara-venn"]
        event = game.active_sector_events()[0]
        job = game.local_jobs[event["id"]]
        self.dock(game, captain["location"])
        result = game.command("call-favor", "request_sector_aid", event_id=event["id"], npc_id=captain["id"])
        self.assertGreater(result["bonus"], 0)
        self.assertEqual(job["reward"], old_reward + result["bonus"])
        self.assertEqual(job["deadline"], old_deadline + 4)
        self.assertEqual(event["reward"], job["reward"])
        self.assertEqual(event["end_tick"], job["deadline"] + 1)
        self.assertEqual(captain["relationship"], 2)
        self.assertEqual(game.command("call-favor", "request_sector_aid",
                                      event_id=event["id"], npc_id=captain["id"]), result)
        with self.assertRaises(GameError):
            game.command("repeat-favor", "request_sector_aid", event_id=event["id"], npc_id=captain["id"])

    def test_hostile_captain_changes_future_incident_without_retroactive_edits(self):
        seed = 5
        good = SECTOR_INCIDENTS[(seed + 1) % len(SECTOR_INCIDENTS)][3]
        ordinary = Game.new(seed)
        threatened = Game.new(seed)
        captain = next(c for c in threatened.npc_captains.values() if c["good"] == good)
        captain["relationship"] = -3
        threatened.command("advance", "wait", ticks=INCIDENT_INTERVAL)
        ordinary.command("advance", "wait", ticks=INCIDENT_INTERVAL)
        event_id = "dispatch-00001"
        self.assertEqual(threatened.local_jobs[event_id]["reward"],
                         ordinary.local_jobs[event_id]["reward"] * 125 // 100)
        self.assertEqual(threatened.local_jobs[event_id]["deadline"],
                         ordinary.local_jobs[event_id]["deadline"] - 1)
        self.assertEqual(next(e for e in threatened.sector_events if e["id"] == event_id)["hostile_captain"],
                         captain["id"])

    def test_followup_can_choose_profit_or_reconciliation(self):
        def prepared():
            game = Game.new(8)
            game.faction_followups["trust-test"] = {
                "expedition_id": "trust-test", "npc_id": "sable-rook", "status": "pending",
                "friendly": False, "due_tick": game.tick,
                "title": "A Challenge from Sable Rook", "description": "Tense fuel shipment."}
            game._advance_faction_followups()
            job = game.local_jobs["followup-trust-test"]
            game.cargo[job["good"]] = job["quantity"]
            return game, job

        peaceful, job = prepared()
        reward = job["reward"]
        credits, pirates = peaceful.credits, peaceful.factions["pirates"]
        result = peaceful.command("peace", "deliver_local", job_id=job["id"], resolution="reconcile")
        self.assertEqual(result["reward"], reward // 2)
        self.assertEqual(peaceful.credits, credits + reward // 2)
        self.assertEqual(peaceful.npc_captains["sable-rook"]["relationship"], 3)
        self.assertEqual(peaceful.factions["pirates"], pirates + 2)
        self.assertEqual(peaceful.faction_followups["trust-test"]["resolution"], "reconcile")
        self.assertEqual(peaceful.command("peace", "deliver_local", job_id=job["id"], resolution="reconcile"), result)

        commercial, second_job = prepared()
        result = commercial.command("profit", "deliver_local", job_id=second_job["id"])
        self.assertEqual(result["reward"], reward)
        self.assertEqual(commercial.npc_captains["sable-rook"]["relationship"], 1)
        self.assertEqual(commercial.faction_followups["trust-test"]["resolution"], "commercial")

    def test_web_actions_leave_radio_ledgers_untouched(self):
        from tests.test_radio_flow import station

        app = station("W1FACTION", 6)
        captain = app.game.npc_captains["mara-venn"]
        captain["relationship"] = 3
        self.dock(app.game, captain["location"])
        app.execute({"id": "captain-favor", "action": "request_sector_aid",
                     "args": {"event_id": app.game.active_sector_events()[0]["id"],
                              "npc_id": captain["id"]}})
        app.execute({"id": "captain-lot", "action": "buy_captain_deal",
                     "args": {"npc_id": captain["id"], "amount": 1}})
        self.assertGreater(app.game.captain_deal_quote(captain["id"])["next_tick"], app.game.tick)
        self.assertEqual(app.radio_transmissions, {})
        self.assertEqual(app.radio_contacts, {})
        self.assertEqual(app.radio_reservations, {})


if __name__ == "__main__":
    unittest.main()
