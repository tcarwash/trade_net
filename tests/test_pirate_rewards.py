"""A route-clear bounty pays once; optional wreckage survives save/reload."""
import time
import unittest
from copy import deepcopy
from unittest.mock import patch
from tradenet import Game, GameError


def pirate_game(seed=42, strength=1):
    g = Game.new(seed)
    now = time.time()
    g.ship.update(destination='Kepler', arrival_at=None, departed_at=now - 2,
                  travel_seconds=6, fuel=30)
    g.ship['flight_encounter'] = dict(
        id='pirate-test', kind='pirates', status='pending', source='transit',
        title='Pirate Intercept', description='Test intercept', progress=.4,
        pirate_key='Haven|Kepler', strength=strength, distance=3,
        risk={'damage': 1}, origin='Haven', destination='Kepler',
        elapsed_seconds=2, remaining_seconds=4, trigger_at=now,
        choices=[{'id':'fight','label':'Fight'},{'id':'evade','label':'Evade'},
                 {'id':'pay','label':'Pay toll'}])
    g.pirate_groups['Haven|Kepler'] = strength
    return g


class PirateRewardsTests(unittest.TestCase):
    def clear(self, g):
        return g.command('fight', 'resolve_transit_encounter', choice='fight')

    def test_bounty_paid_once_and_cargo_requires_explicit_collection(self):
        g = pirate_game()
        credits, cargo = g.credits, deepcopy(g.cargo)
        result = self.clear(g)
        self.assertTrue(result['route_cleared'])
        self.assertTrue(result['salvage_pending'])
        self.assertTrue(60 <= result['bounty'] <= 120)
        self.assertEqual(g.credits, credits + result['bounty'])
        self.assertEqual(g.cargo, cargo)
        self.assertIsNone(g.ship['arrival_at'])
        self.assertEqual(self.clear(g), result)
        self.assertEqual(g.credits, credits + result['bounty'])
        with self.assertRaises(GameError):
            g.command('fight-again', 'resolve_transit_encounter', choice='fight')
        loot = deepcopy(g.ship['flight_encounter']['choices'][0]['loot'])
        g.command('collect', 'resolve_transit_encounter', choice='collect')
        for good, quantity in loot.items():
            self.assertEqual(g.cargo[good], quantity)
        self.assertNotIn('flight_encounter', g.ship)
        self.assertIsNotNone(g.ship['arrival_at'])
        before = g.to_dict()
        with self.assertRaises(GameError):
            g.command('collect-twice', 'resolve_transit_encounter', choice='collect')
        self.assertEqual(g.to_dict(), before)

    def test_full_hold_can_leave_and_keeps_bounty(self):
        g = pirate_game()
        g.cargo['ore'] = g.ship['capacity']
        result = self.clear(g)
        credits = g.credits
        with self.assertRaisesRegex(GameError, 'cargo space'):
            g.command('too-full', 'resolve_transit_encounter', choice='collect')
        g.command('leave', 'resolve_transit_encounter', choice='leave')
        self.assertEqual(g.credits, credits)
        self.assertEqual(g.cargo['ore'], g.ship['capacity'])
        self.assertGreater(result['bounty'], 0)
        self.assertNotIn('flight_encounter', g.ship)

    def test_reload_preserves_offer_and_declining_does_not_load_goods(self):
        g = pirate_game()
        self.clear(g)
        offer, credits = deepcopy(g.ship['flight_encounter']), g.credits
        restored = Game.from_dict(g.to_dict())
        self.assertEqual(restored.ship['flight_encounter'], offer)
        restored.command('leave', 'resolve_transit_encounter', choice='leave')
        self.assertEqual(sum(restored.cargo.values()), 0)
        self.assertEqual(restored.credits, credits)

    def test_partial_fight_pay_and_evade_do_not_award_bounties(self):
        for choice in ('fight', 'pay', 'evade'):
            with self.subTest(choice=choice):
                g = pirate_game(strength=10)
                credits = g.credits
                result = g.command('choice', 'resolve_transit_encounter', choice=choice)
                self.assertFalse(result['route_cleared'])
                self.assertFalse(result.get('salvage_pending'))
                self.assertNotIn('bounty', result)
                self.assertLessEqual(g.credits, credits)

    def test_already_cleared_group_does_not_pay_again(self):
        g = pirate_game(strength=0)
        credits = g.credits
        result = self.clear(g)
        self.assertFalse(result.get('salvage_pending'))
        self.assertEqual(g.credits, credits)

    def test_generated_drops_are_small_and_fuel_recovery_is_capped(self):
        saw_fuel = False
        for seed in range(20):
            g = pirate_game(seed)
            self.clear(g)
            offer = g.ship['flight_encounter']
            self.assertLessEqual(sum(offer['choices'][0]['loot'].values()), 3)
            if any(option['id'] == 'fuel_only' for option in offer['choices']):
                saw_fuel = True
                g.ship['fuel'] = g.ship['max_fuel'] - 1
                g.cargo['ore'] = g.ship['capacity']
                result = g.command('fuel', 'resolve_transit_encounter', choice='fuel_only')
                self.assertEqual(result['tank_fuel'], 1)
                self.assertEqual(g.ship['fuel'], g.ship['max_fuel'])
                self.assertEqual(g.cargo['ore'], g.ship['capacity'])
        self.assertTrue(saw_fuel)

    def test_reserved_space_blocks_pickup_but_not_declining(self):
        g = pirate_game()
        self.clear(g)
        g.incoming_reserved = g.ship['capacity']
        with self.assertRaisesRegex(GameError, 'cargo space'):
            g.command('reserved', 'resolve_transit_encounter', choice='collect')
        g.command('leave', 'resolve_transit_encounter', choice='leave')
        self.assertEqual(sum(g.cargo.values()), 0)

    def test_later_encounters_shift_by_combat_and_salvage_pause(self):
        g = pirate_game()
        start = g.ship['flight_encounter']['trigger_at']
        g.ship['flight_encounters'] = [{'kind':'derelict', 'trigger_at':start+50}]
        with patch('tradenet.engine.time.time', return_value=start+5):
            self.clear(g)
        self.assertEqual(g.ship['flight_encounters'][0]['trigger_at'], start+55)
        with patch('tradenet.engine.time.time', return_value=start+15):
            g.command('leave', 'resolve_transit_encounter', choice='leave')
        self.assertEqual(g.ship['flight_encounters'][0]['trigger_at'], start+65)
        self.assertEqual(g.ship['arrival_at'], start+19)

    def test_reserved_space_and_low_hull_do_not_trap_leave_choice(self):
        g = pirate_game()
        self.clear(g)
        g.cargo['ore'] = g.ship['capacity']
        g.ship['condition'] = 0
        g.command('leave', 'resolve_transit_encounter', choice='leave')
        self.assertNotIn('flight_encounter', g.ship)
