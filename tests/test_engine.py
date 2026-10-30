import tempfile
import unittest
from pathlib import Path

from tradenet import Game, GameError


class EconomyTests(unittest.TestCase):
    def test_faction_standings_affect_market_prices(self):
        game = Game.new(42)
        before_sell = game.price('Haven', 'food', 'sell')
        before_ore = game.price('Haven', 'ore', 'buy')
        game.factions['traders'] = 20
        game.factions['miners'] = 20
        self.assertGreaterEqual(game.price('Haven', 'food', 'sell'), before_sell)
        self.assertLessEqual(game.price('Haven', 'ore', 'buy'), before_ore)
        self.assertEqual(Game.from_dict(game.to_dict()).factions['miners'], 20)

    def test_story_chapters_require_objectives_and_remain_idempotent(self):
        game = Game.new(42)
        with self.assertRaises(GameError):
            game.command('too-soon', 'complete_story')
        game.ship['location'] = 'Kepler'
        game._bind_ship()
        first = game.command('chapter-1', 'complete_story')
        self.assertEqual(first['next']['port'], 'Aurora')
        game.ship['location'] = 'Aurora'
        game._bind_ship()
        with self.assertRaises(GameError):
            game.command('no-medicine', 'complete_story')
        game.cargo['medicine'] = 2
        second = game.command('chapter-2', 'complete_story')
        self.assertEqual(second['next']['port'], 'Eidolon')
        self.assertEqual(game.cargo['medicine'], 0)
        self.assertEqual(game.command('chapter-2', 'complete_story'), second)
        self.assertEqual(Game.from_dict(game.to_dict()).story_stage, 2)

    def test_equipment_and_pirate_choices(self):
        from unittest.mock import patch
        game = Game.new(42)
        bought = game.command('scanner', 'buy_equipment', item='scanner')
        self.assertEqual(bought['cost'], 220)
        with self.assertRaises(GameError):
            game.command('scanner-twice', 'buy_equipment', item='scanner')
        with self.assertRaises(GameError):
            game.command('bad-gear', 'buy_equipment', item='nuclear')
        route = next((p for p in game.ports if p != 'Haven' and game.route_risk('Haven', p)['kind'] == 'pirates'), None)
        if route is not None:
            with patch.object(game, 'blocked_port', return_value='Haven'):
                before = game.credits
                result = game.command('evade-pirates', 'travel', destination=route, pirate_stance='evade')
            self.assertEqual(result['hazard']['kind'], 'pirates')
            self.assertNotIn('toll', result['hazard'])
            self.assertEqual(game.credits, before)

    def test_expanded_galaxy_exploration_and_save_migration(self):
        from unittest.mock import patch
        game = Game.new(42)
        self.assertEqual(len(game.ports), 10)
        self.assertEqual(game.visited_ports, ['Haven'])
        legacy = game.to_dict()
        for port in list(legacy['ports'])[5:]:
            legacy['ports'].pop(port)
            legacy['galaxies']['home']['ports'].pop(port, None)
        restored = Game.from_dict(legacy)
        self.assertEqual(len(restored.ports), 10)
        with patch.object(game, 'blocked_port', return_value='Eidolon'):
            game.command('explore-trip', 'travel', destination='Kepler')
        game.ship['arrival_at'] = 0
        previous = game.credits
        game._all_arrivals()
        reward = game.journal[-1]['result']['reward']
        self.assertGreater(reward, 90)
        self.assertEqual(game.credits, previous + reward)
        self.assertIn('Kepler', game.visited_ports)
        game._all_arrivals()
        self.assertEqual(game.credits, previous + reward)

    def test_vip_passengers_are_ship_specific_and_pay_once(self):
        game = Game.new(42)
        job = next(iter(game.vip_jobs.values()))
        game.ship['location'] = job['origin']
        game._bind_ship()
        picked = game.command('board', 'accept_vip', job_id=job['id'])
        self.assertEqual(picked['destination'], job['destination'])
        with self.assertRaises(GameError):
            game.command('double-board', 'accept_vip', job_id=job['id'])
        with self.assertRaises(GameError):
            game.command('early-drop', 'deliver_vip', job_id=job['id'])
        game.ship['location'] = job['destination']
        game._bind_ship()
        credits = game.credits
        result = game.command('drop', 'deliver_vip', job_id=job['id'])
        self.assertEqual(game.credits, credits + result['reward'])
        self.assertEqual(game.command('drop', 'deliver_vip', job_id=job['id']), result)
        with self.assertRaises(GameError):
            game.command('double-drop', 'deliver_vip', job_id=job['id'])

    def test_hazards_are_predictable_and_damage_is_accounted(self):
        from unittest.mock import patch
        game = Game.new(42)
        destination = 'Drift'
        risk = game.route_risk('Haven', destination)
        with patch.object(game, 'blocked_port', return_value='Eidolon'):
            before = game.ship['condition']
            result = game.command('danger', 'travel', destination=destination)
        self.assertEqual(result['hazard']['kind'], risk['kind'])
        distance = abs(game.ports['Haven']['distance']-game.ports[destination]['distance'])
        self.assertEqual(before-game.ship['condition'], max(1,distance)+result['hazard_damage'])

    def test_market_intel_remembers_dockside_best_quotes(self):
        game = Game.new(42)
        self.assertEqual(game.price_memory['food']['lowest_buy']['port'], 'Haven')
        game.ship['location'] = 'Kepler'
        game._bind_ship()
        game.ports['Kepler']['stock']['food'] = 200
        game.observe_markets()
        self.assertEqual(game.price_memory['food']['lowest_buy']['port'], 'Kepler')
        remembered = game.price_memory['food']['lowest_buy']['price']
        game.ports['Kepler']['stock']['food'] = 0
        game.observe_markets()
        self.assertEqual(game.price_memory['food']['lowest_buy']['price'], remembered)
        self.assertEqual(Game.from_dict(game.to_dict()).price_memory['food']['lowest_buy']['price'], remembered)

    def test_orbiting_asteroid_field_blocks_one_destination(self):
        from unittest.mock import patch
        game = Game.new(42)
        with patch('tradenet.engine.time.time', return_value=9000):
            blocked = game.blocked_port()
            self.assertNotEqual(game.blocked_port(9090), blocked)
            if blocked != game.location:
                with self.assertRaisesRegex(GameError, 'Asteroid field'):
                    game.command('blocked', 'travel', destination=blocked)
            safe = next(port for port in game.ports if port not in (game.location, blocked))
            self.assertEqual(game.command('safe', 'travel', destination=safe)['destination'], safe)

    def test_export_freight_must_be_imported_to_haven(self):
        game = Game.new(42)
        game.command('home-buy', 'buy', good='food', amount=2)
        with self.assertRaises(GameError):
            game.command('home-export', 'unload_export', good='food', amount=2)
        game.ship['location'] = 'Kepler'
        game._bind_ship()
        game.command('foreign-buy', 'buy', good='food', amount=3)
        with self.assertRaises(GameError):
            game.command('away-export', 'unload_export', good='food', amount=3)
        game.ship['location'] = 'Haven'
        game._bind_ship()
        result = game.command('import', 'unload_export', good='food', amount=3)
        self.assertEqual(result['warehouse'], 3)
        self.assertEqual(game.cargo['food'], 2)
        self.assertEqual(game.ship['export_cargo']['food'], 0)
        self.assertEqual(Game.from_dict(game.to_dict()).export_warehouse['food'], 3)

    def test_local_freight_requires_delivery_and_replenishes_board(self):
        game = Game.new(42)
        self.assertEqual(len([j for j in game.local_jobs.values() if j['status'] == 'open']), 3)
        job = next(iter(game.local_jobs.values()))
        with self.assertRaises(GameError):
            game.command('premature', 'deliver_local', job_id=job['id'])
        game.cargo[job['good']] = job['quantity']
        game.ship['location'] = job['destination']
        game._bind_ship()
        before = game.credits
        delivered = game.command('delivery', 'deliver_local', job_id=job['id'])
        self.assertEqual(delivered['reward'], job['reward'])
        self.assertEqual(game.credits, before + job['reward'])
        self.assertEqual(game.cargo[job['good']], 0)
        self.assertEqual(len([j for j in game.local_jobs.values() if j['status'] == 'open']), 3)
        self.assertEqual(game.command('delivery', 'deliver_local', job_id=job['id']), delivered)
        with self.assertRaises(GameError):
            game.command('double-pay', 'deliver_local', job_id=job['id'])

    def test_seed_reproducible_and_specialized(self):
        a, b = Game.new(42), Game.new(42)
        self.assertEqual(a.to_dict(), b.to_dict())
        self.assertIn(a.specialization, ("aether", "iridium", "mycelium"))
        self.assertGreaterEqual(a.ports["Kepler"]["stock"][a.specialization], 90)

    def test_conserved_stock_and_credits(self):
        game = Game.new(5)
        good = "food"
        stock = game.ports[game.location]["stock"][good]
        before = game.credits
        buy = game.command("b1", "buy", good=good, amount=3)
        self.assertEqual(game.cargo[good], 3)
        self.assertEqual(game.ports[game.location]["stock"][good], stock - 3)
        self.assertEqual(game.credits, before - buy["total"])
        game.command("s1", "sell", good=good, amount=3)
        self.assertEqual(game.cargo[good], 0)
        self.assertEqual(game.ports[game.location]["stock"][good], stock)
        self.assertLess(game.credits, before)

    def test_atomic_rejection(self):
        game = Game.new()
        prior = game.to_dict()
        with self.assertRaises(GameError):
            game.command("bad", "buy", good="aether", amount=100)
        self.assertEqual(game.to_dict(), prior)

    def test_duplicate_idempotent_and_conflict_rejected(self):
        game = Game.new()
        first = game.command("same", "buy", good="food", amount=1)
        saved = game.to_dict()
        self.assertEqual(game.command("same", "buy", good="food", amount=1), first)
        self.assertEqual(game.to_dict(), saved)
        with self.assertRaises(GameError):
            game.command("same", "buy", good="ore", amount=1)

    def test_travel_wait_save_reload(self):
        game = Game.new(12)
        trip = game.command("t1", "travel", destination="Kepler")
        self.assertEqual(game.ship["destination"], "Kepler")
        game.command("w1", "wait", ticks=trip["arrival_tick"])
        self.assertEqual(game.location, "Kepler")
        self.assertIsNone(game.ship["destination"])
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "save.json"
            game.save(file)
            self.assertEqual(Game.load(file).to_dict(), game.to_dict())

    def test_cargo_capacity_and_invalid_wait(self):
        game = Game.new()
        with self.assertRaises(GameError):
            game.command("over", "buy", good="food", amount=31)
        with self.assertRaises(GameError):
            game.command("negative-time", "wait", ticks=-2)

    def test_refuel_uses_port_stock_and_credits(self):
        game = Game.new()
        game.command("trip", "travel", destination="Kepler")
        game.command("arrive", "wait", ticks=3)
        before = game.ports["Kepler"]["stock"]["fuel"]
        old_fuel = game.ship["fuel"]
        old_credits = game.credits
        result = game.command("fill", "refuel", amount=2)
        self.assertEqual(game.ship["fuel"], old_fuel + 2)
        self.assertEqual(game.ports["Kepler"]["stock"]["fuel"], before - 2)
        self.assertEqual(game.credits, old_credits - result["cost"])

    def test_faster_ship_shortens_travel_and_unlocks_bandwidth(self):
        slow = Game.new(9)
        fast = Game.new(9)
        upgrade = fast.command("ship", "buy_ship")
        self.assertEqual(upgrade["max_bandwidth_hz"], 1200)
        self.assertEqual(fast.ship["speed"], 2)
        slow_eta = slow.command("slow", "travel", destination="Meridian")["arrival_tick"]
        fast_eta = fast.command("fast", "travel", destination="Meridian")["arrival_tick"]
        self.assertLess(fast_eta, slow_eta)

    def test_real_time_utc_epoch_catchup(self):
        a, b = Game.new(11), Game.new(11)
        base = 1_800_000_000  # exact five-minute UTC boundary
        self.assertEqual(a.sync_utc(base)["advanced"], 0)
        b.sync_utc(base)
        for _ in range(12):
            b.command(f"manual-{_}", "wait", ticks=1)
        result = a.sync_utc(base + 12 * 300)
        self.assertEqual(result["advanced"], 12)
        self.assertEqual(a.tick, b.tick)
        self.assertEqual({p: x["stock"] for p, x in a.ports.items()},
                         {p: x["stock"] for p, x in b.ports.items()})
        self.assertEqual(a.sync_utc(base + 11 * 300)["advanced"], 0)

    def test_individual_fleet_inventory_and_persistence(self):
        game = Game.new(14)
        first = game.active_ship_id
        game.command("load", "buy", good="food", amount=1)
        bought = game.command("buy-second", "purchase_ship", tier=1)
        second = bought["ship_id"]
        self.assertEqual(game.fleet[second]["modem_tier"], 1)
        game.command("switch", "select_ship", ship_id=second)
        self.assertEqual(game.cargo["food"], 0)
        game.command("voyage", "travel", destination="Kepler")
        game.command("switch-back", "select_ship", ship_id=first)
        self.assertEqual(game.location, "Haven")
        self.assertEqual(game.cargo["food"], 1)
        game.command("tick", "wait", ticks=3)
        self.assertEqual(game.fleet[second]["location"], "Kepler")
        reloaded = Game.from_dict(game.to_dict())
        self.assertEqual(reloaded.fleet[second]["location"], "Kepler")
        reloaded.command("select-again", "select_ship", ship_id=second)
        self.assertEqual(reloaded.location, "Kepler")

    def test_legacy_single_ship_save_migrates(self):
        old = Game.new(3).to_dict()
        for key in ("fleet", "active_ship_id", "next_ship_number", "hard_mode"):
            old.pop(key)
        for key in ("location", "cargo", "id"):
            old["ship"].pop(key, None)
        game = Game.from_dict(old)
        self.assertEqual(len(game.fleet), 1)
        self.assertEqual(game.location, "Haven")
        self.assertIs(game.ship, game.fleet[game.active_ship_id])

    def test_hard_mode_buff_and_irreversible_permadeath(self):
        easy, hard = Game.new(8), Game.new(8)
        hard.command("hard", "set_hard_mode", enabled=True)
        self.assertGreater(hard.price("Haven", "ore", "sell"),
                           easy.price("Haven", "ore", "sell"))
        with self.assertRaises(GameError):
            hard.command("no-back", "set_hard_mode", enabled=False)
        easy.damage_ship(easy.active_ship_id, 100, "Haven")
        self.assertEqual(len(easy.fleet), 1)
        result = hard.damage_ship(hard.active_ship_id, 100, "Haven")
        self.assertTrue(result["destroyed"])
        self.assertFalse(hard.fleet)
        hard.credits = 1000
        hard.command("replacement", "purchase_ship", tier=0)
        self.assertEqual(len(hard.fleet), 1)


if __name__ == "__main__":
    unittest.main()
