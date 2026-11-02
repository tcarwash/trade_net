"""Fuel supports trading loops and exploration without depending on map spacing."""
import unittest
from unittest.mock import patch
from tradenet import Game, GameError


class FuelBalanceTests(unittest.TestCase):
    def setUp(self):
        self.game = Game.new(42)

    def test_linked_hops_cost_two_even_on_long_map_links(self):
        g = self.game
        with patch.object(Game, 'blocked_port', return_value=''):
            for origin in g.ports:
                for destination in g._route_neighbors(origin):
                    quote = g.travel_fuel_quote(origin, destination)
                    self.assertEqual(quote['fuel_cost'], 2, (origin, destination))
            g.ports['Drift']['distance'] = 10000
            self.assertEqual(g.travel_fuel_quote('Kepler', 'Drift')['fuel_cost'], 2)

    def test_crossings_are_affordable_and_preserve_return_reserve(self):
        g = self.game
        with patch.object(Game, 'blocked_port', return_value=''):
            for origin in g.ports:
                for destination in g.ports:
                    if origin == destination:
                        continue
                    quote = g.travel_fuel_quote(origin, destination)
                    self.assertLessEqual(quote['fuel_cost'], 8)
                    self.assertLessEqual(quote['fuel_cost'] + quote['return_fuel'], 16)
            self.assertEqual(g.travel_fuel_quote('Haven', 'Eidolon')['fuel_cost'], 5)

    def test_actual_flight_matches_quote_and_works_with_two_fuel(self):
        g = self.game
        g.ship['fuel'] = 2
        with patch.object(Game, 'blocked_port', return_value=''):
            quote = g.travel_fuel_quote('Haven', 'Kepler')
            receipt = g.command('depart', 'travel', destination='Kepler')
        self.assertEqual(receipt['fuel_cost'], quote['fuel_cost'])
        self.assertEqual(g.ship['fuel'], 0)

    def test_asteroid_bypass_is_one_extra_and_still_requires_navigator(self):
        g = self.game
        with patch.object(Game, 'blocked_port', return_value='Kepler'):
            self.assertEqual(g.travel_fuel_quote('Haven', 'Kepler')['fuel_cost'], 3)
            with self.assertRaisesRegex(GameError, 'Asteroid'):
                g.command('blocked', 'travel', destination='Kepler')
            g.ship['equipment'].append('navigator')
            receipt = g.command('bypass', 'travel', destination='Kepler')
        self.assertEqual(receipt['fuel_cost'], 3)

    def test_tank_service_is_affordable_without_changing_cargo_prices(self):
        g = self.game
        cargo_price = g.price('Haven', 'fuel', 'buy')
        unit = g.refuel_unit_price('Haven')
        self.assertEqual(unit, (cargo_price + 4) // 5)
        g.ship['fuel'] -= 4
        g.credits = unit * 4
        result = g.command('refill', 'refuel', amount=4)
        self.assertEqual(result['cost'], unit * 4)
        self.assertEqual(g.credits, 0)
        self.assertEqual(g.ship['fuel'], 40)

    def test_emergency_refuel_is_double_tank_service_price(self):
        g = self.game
        g.ship['fuel'] = 0
        g.ports['Haven']['stock']['fuel'] = 0
        unit = g.refuel_unit_price('Haven')
        result = g.command('reserve', 'emergency_refuel', amount=2)
        self.assertEqual(result['cost'], unit * 4)

    def test_old_save_keeps_tank_and_uses_new_balance(self):
        self.game.ship['fuel'] = 13
        restored = Game.from_dict(self.game.to_dict())
        self.assertEqual(restored.ship['fuel'], 13)
        self.assertEqual(restored.ship['max_fuel'], 40)
        with patch.object(Game, 'blocked_port', return_value=''):
            self.assertEqual(restored.travel_fuel_quote('Haven', 'Eidolon')['fuel_cost'], 5)
