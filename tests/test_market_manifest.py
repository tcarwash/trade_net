"""Mixed market deals settle completely, or leave the account untouched."""
import unittest
from tradenet import Game, GameError


class MarketManifestTests(unittest.TestCase):
    def setUp(self):
        self.game = Game.new(42)

    def trade(self, command_id, quantities, **overrides):
        g = self.game
        args = dict(quantities=quantities, port=g.location, ship_id=g.active_ship_id,
                    prices={good: g.price(g.location, good, 'buy' if n > 0 else 'sell')
                            for good, n in quantities.items()})
        args.update(overrides)
        return g.command(command_id, 'trade_manifest', **args)

    def test_sales_release_credits_and_hold_space_and_retry_is_idempotent(self):
        g = self.game
        g.cargo['medicine'] = g.ship['capacity']
        g.credits = 0
        quantities = {'food': 1, 'medicine': -1}
        args = dict(quantities=quantities, port=g.location, ship_id=g.active_ship_id,
                    prices={'food': g.price(g.location, 'food', 'buy'),
                            'medicine': g.price(g.location, 'medicine', 'sell')})
        result = g.command('mixed', 'trade_manifest', **args)
        self.assertEqual(g.cargo['food'], 1)
        self.assertEqual(g.cargo_used(), g.ship['capacity'])
        self.assertEqual(g.credits, -result['net_cost'])
        before = g.to_dict()
        self.assertEqual(g.command('mixed', 'trade_manifest', **args), result)
        self.assertEqual(g.to_dict(), before)

    def test_failed_purchase_rolls_back_prior_sale(self):
        g = self.game
        g.cargo['medicine'] = 2
        before = g.to_dict()
        with self.assertRaises(GameError):
            self.trade('bad', {'medicine': -1, 'food': 10000})
        self.assertEqual(g.to_dict(), before)

    def test_invalid_stale_and_wrong_context_deals_are_rejected(self):
        for quantities, overrides in [({'food': 1.5}, {}), ({'food': True}, {}),
                                      ({'food': 1}, {'port': 'Kepler'}),
                                      ({'food': 1}, {'ship_id': 'other'}),
                                      ({'food': 1}, {'prices': {'food': 0}})]:
            with self.subTest(quantities=quantities, overrides=overrides):
                before = self.game.to_dict()
                with self.assertRaises(GameError):
                    self.trade('invalid', quantities, **overrides)
                self.assertEqual(self.game.to_dict(), before)
