"""Combat remains paused until victory, escape, payment, or defeat."""
import unittest
from unittest.mock import patch
from tradenet import Game, GameError
from tests.test_pirate_rewards import pirate_game


class CombatTurnTests(unittest.TestCase):
    def test_multiple_fights_then_victory_and_salvage(self):
        g=pirate_game(strength=3)
        credits=g.credits
        for turn in (1,2):
            result=g.command(f'fight-{turn}','resolve_transit_encounter',choice='fight')
            self.assertTrue(result['combat_pending'])
            self.assertEqual(result['strength_remaining'],3-turn)
            self.assertIsNone(g.ship['arrival_at'])
            self.assertEqual(g.ship['flight_encounter']['round'],turn)
            self.assertEqual(g.credits,credits)
        restored=Game.from_dict(g.to_dict())
        result=restored.command('final','resolve_transit_encounter',choice='fight')
        self.assertTrue(result['salvage_pending'])
        self.assertEqual(restored.ship['flight_encounter']['kind'],'pirate_salvage')
        self.assertGreater(restored.credits,credits)

    def test_failed_flee_can_be_followed_by_successful_flee(self):
        g=pirate_game(strength=5)
        fuel=g.ship['fuel']
        with patch('tradenet.engine.random.Random') as rng:
            rng.return_value.randrange.return_value=99
            result=g.command('fail','resolve_transit_encounter',choice='evade')
        self.assertTrue(result['combat_pending'])
        self.assertEqual(g.ship['fuel'],fuel-2)
        self.assertIsNone(g.ship['arrival_at'])
        with patch('tradenet.engine.random.Random') as rng:
            rng.return_value.randrange.return_value=0
            result=g.command('escape','resolve_transit_encounter',choice='evade')
        self.assertFalse(result.get('combat_pending',False))
        self.assertNotIn('flight_encounter',g.ship)
        self.assertIsNotNone(g.ship['arrival_at'])
        self.assertEqual(g.ship['fuel'],fuel-4)

    def test_can_pay_after_inconclusive_fight_and_insufficient_money_is_rejected(self):
        g=pirate_game(strength=10)
        g.command('fight','resolve_transit_encounter',choice='fight')
        toll=g.combat_quote()['toll']
        g.credits=toll-1
        with self.assertRaisesRegex(GameError,'insufficient funds'):
            g.command('broke','resolve_transit_encounter',choice='pay')
        self.assertEqual(g.ship['flight_encounter']['round'],1)
        g.credits=toll
        result=g.command('pay','resolve_transit_encounter',choice='pay')
        self.assertEqual(g.credits,0)
        self.assertEqual(result['toll'],toll)
        self.assertEqual(result['hazard_damage'],0)
        self.assertNotIn('flight_encounter',g.ship)

    def test_defeat_ends_combat_and_respects_hard_mode(self):
        for hard in (False,True):
            with self.subTest(hard_mode=hard):
                g=pirate_game(strength=10);g.hard_mode=hard
                g.ship['condition']=1
                result=g.command('fight','resolve_transit_encounter',choice='fight')
                self.assertTrue(result['defeated'])
                self.assertEqual(result['destroyed'],hard)
                if hard:self.assertEqual(g.fleet,{})
                else:
                    self.assertEqual(g.ship['condition'],10)
                    self.assertEqual(g.ship['location'],'Haven')
                    self.assertNotIn('flight_encounter',g.ship)
                    self.assertIsNone(g.ship['destination'])

    def test_replaying_a_round_does_not_repeat_damage(self):
        g=pirate_game(strength=10)
        result=g.command('round','resolve_transit_encounter',choice='fight')
        hull=g.ship['condition']
        self.assertEqual(g.command('round','resolve_transit_encounter',choice='fight'),result)
        self.assertEqual(g.ship['condition'],hull)
        self.assertEqual(g.ship['flight_encounter']['round'],1)
