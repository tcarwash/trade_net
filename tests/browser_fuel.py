"""Run: uv run --with playwright python tests/browser_fuel.py."""
import sys
import unittest
from playwright.sync_api import expect
from browser_smoke import CockpitBrowserTests


class FuelBrowserTests(CockpitBrowserTests):
    def test_server_quotes_drive_preview_and_actual_flight(self):
        page = self.page
        state = page.request.get(self.url + '/api/state').json()
        destination = next(port for port, quote in state['route_fuel'].items()
                           if quote['kind'] == 'charted' and
                           port != state['asteroid_field']['blocked_port'])
        page.evaluate("destination=>{el('destination').value=destination;updateRouteQuote()}", destination)
        fuel = state['route_fuel'][destination]['fuel_cost']
        expect(page.locator('#routeQuote')).to_contain_text(f'{fuel} tank fuel')
        expect(page.locator('#routeQuote')).to_contain_text(f'{40-fuel} after arrival')
        expect(page.locator('#routeQuote')).to_contain_text('Return reserve')
        expect(page.locator('#routeQuote')).to_contain_text('2 base fuel')
        self.assertEqual(state['refuel_prices']['Haven'], 5)
        self.assertEqual(state['prices']['Haven']['fuel']['buy'], 22)
        result = page.evaluate("destination=>command('travel',{destination})", destination)
        self.assertIsNotNone(result, page.locator('#feedback').text_content())
        self.assertEqual(result['fuel_cost'], fuel)
        self.assertEqual(page.evaluate('state.game.ship.fuel'), 40-fuel)
        expect(page.locator('#routeQuote')).to_contain_text(f'Haven → {destination}')


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([
        FuelBrowserTests('test_server_quotes_drive_preview_and_actual_flight')]))
    sys.exit(not result.wasSuccessful())
