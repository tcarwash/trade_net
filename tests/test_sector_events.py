"""Living-galaxy incidents must affect real solo gameplay, never the radio path."""

import unittest

from tradenet.engine import Game, GameError, INCIDENT_INTERVAL


class SectorIncidentTests(unittest.TestCase):
    def test_deterministic_seed_and_real_market_demand(self):
        a, b = Game.new(42), Game.new(42)
        self.assertEqual(a.sector_events, b.sector_events)
        self.assertEqual(a.local_jobs, b.local_jobs)
        event = a.active_sector_events()[0]
        premium = a.price(event["port"], event["good"], "sell")
        a.sector_events.clear()  # Baseline market with no active incident.
        ordinary = a.price(event["port"], event["good"], "sell")
        self.assertGreater(premium, ordinary)
        self.assertEqual(event["source"], "simulated")

    def test_dispatch_job_uses_real_cargo_and_only_pays_once(self):
        game = Game.new(12)
        event = game.active_sector_events()[0]
        job = game.local_jobs[event["job_id"]]
        self.assertEqual(job["kind"], "dispatch")
        self.assertEqual(job["deadline"], event["end_tick"] - 1)
        game.ship["cargo"][job["good"]] = job["quantity"]
        game.ship["location"] = job["destination"]
        game._bind_ship()
        old_credits = game.credits
        result = game.command("dispatch-delivery", "deliver_local", job_id=job["id"])
        self.assertEqual(result["reward"], event["reward"])
        self.assertEqual(game.credits, old_credits + event["reward"])
        self.assertEqual(game.cargo[job["good"]], 0)
        self.assertEqual(game.command("dispatch-delivery", "deliver_local", job_id=job["id"]), result)
        with self.assertRaises(GameError):
            game.command("try-again", "deliver_local", job_id=job["id"])

    def test_expiration_rotation_and_offline_catchup(self):
        game = Game.new(23)
        first = game.active_sector_events()[0]
        game.command("next-cycle", "wait", ticks=INCIDENT_INTERVAL)
        self.assertNotIn(first, game.active_sector_events())
        self.assertEqual(game.local_jobs[first["job_id"]]["status"], "expired")
        self.assertEqual(len(game.active_sector_events()), 1)
        restored = Game.from_dict(game.to_dict())
        self.assertEqual(restored.to_dict(), game.to_dict())
        restored.sync_utc(1_800_000_000)
        restored.sync_utc(1_800_000_000 + 100 * INCIDENT_INTERVAL * 300)
        self.assertEqual(len(restored.active_sector_events()), 1)
        self.assertLessEqual(len(restored.sector_events), 12)
        self.assertEqual(restored.active_sector_events()[0]["cycle"], restored.tick // INCIDENT_INTERVAL)

    def test_api_projects_separate_nontransmitting_dispatch_signals(self):
        from tests.test_radio_flow import station
        app = station("W1AAA", 9)
        app.radio_listener_status = "starting"
        app.radio_pending_replies = {}
        app.modem_catalog = {}
        app.game.clock_epoch = 6_000_000
        app.sync_clock = lambda: None
        state = app.state()
        self.assertTrue(state["dispatch_signals"])
        self.assertEqual(state["radio_transmissions"], [])
        self.assertEqual(state["radio_contacts"], {})
        self.assertTrue(all(signal["transport"] == "local_simulation" and
                            signal["transmit"] is False for signal in state["dispatch_signals"]))


if __name__ == "__main__":
    unittest.main()
