"""Real Chromium UX checks. Run: uv run --with playwright python tests/browser_smoke.py.

Install Chromium once with: uv run --with playwright playwright install chromium
The server uses a disposable save; existing galaxies are never changed.
"""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.request import urlopen

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


class CockpitBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tradenet-ui-", dir=os.environ.get("TMPDIR"))
        self.addCleanup(self.temp.cleanup)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        self.url = f"http://127.0.0.1:{port}"
        self.server = subprocess.Popen(
            [sys.executable, "-m", "tradenet.web", "--port", str(port),
             "--save", str(Path(self.temp.name) / "galaxy.json")],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.stop_server)
        for _ in range(100):
            try:
                with urlopen(self.url + "/api/state", timeout=1):
                    break
            except OSError:
                time.sleep(.05)
        else:
            raise RuntimeError("Preview server did not start")
        self.page = self.browser.new_page(viewport={"width": 1440, "height": 1000})
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.goto(self.url)
        expect(self.page.locator("#credits")).not_to_have_text("—")

    def stop_server(self):
        self.server.terminate()
        self.server.wait(timeout=5)

    def tearDown(self):
        self.page.close()
        self.assertEqual(self.errors, [])

    def test_command_deck_navigation_and_responsive_layout(self):
        page = self.page
        expect(page.get_by_role("navigation", name="Command deck")).to_be_visible()
        expect(page.get_by_role("heading", name="Sector overview")).to_be_visible()
        expect(page.locator('#fleetPanel')).not_to_be_visible()
        expect(page.locator('#contractsPanel')).not_to_be_visible()
        page.get_by_role("tab", name="Contracts", exact=True).click()
        expect(page.locator("#contractsPanel")).to_be_in_viewport()
        expect(page.locator('#mapPanel')).not_to_be_visible()
        page.get_by_role('tab', name='Flight deck', exact=True).click()
        page.locator("#debugToggle").click()
        expect(page.locator("#exchangeForm")).to_be_visible()
        page.locator("#debugToggle").click()
        expect(page.locator("#exchangeForm")).not_to_be_visible()
        tab = page.get_by_role('tab', name='Flight deck', exact=True)
        tab.focus()
        tab.press('ArrowRight')
        expect(page.get_by_role('tab', name='Fleet', exact=True)).to_have_attribute('aria-selected', 'true')
        expect(page.locator('#fleetPanel')).to_be_visible()
        page.get_by_role('tab', name='Fleet', exact=True).press('Home')
        expect(page.locator('#mapPanel')).to_be_visible()
        for width in (1440, 1024, 768, 390, 320):
            page.set_viewport_size({"width": width, "height": 900})
            self.assertTrue(page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth"), f"Overflow at {width}px")
        page.emulate_media(reduced_motion="reduce")
        self.assertEqual(page.locator(".node").first.evaluate(
            "e => getComputedStyle(e).animationName"), "none")

    def test_market_limits_maximum_and_keyboard_selection(self):
        page = self.page
        row = page.locator("#market tr").first
        row.focus()
        row.press("Enter")
        expect(row).to_have_attribute("aria-selected", "true")
        amount = page.locator('#tradeForm input[name="amount"]')
        amount.fill("10000")
        expect(page.locator('#tradeForm [value="buy"]')).to_be_disabled()
        expect(page.locator("#tradeQuote")).to_contain_text("Not enough")
        amount.fill("1.5")
        expect(page.locator('#tradeForm [value="buy"]')).to_be_disabled()
        expect(page.locator("#tradeQuote")).to_contain_text("whole number")
        page.get_by_role("button", name="Max affordable").click()
        self.assertGreater(int(amount.input_value()), 0)
        expect(page.locator('#tradeForm [value="buy"]')).to_be_enabled()
        amount.fill("1")
        page.locator('#tradeForm [value="buy"]').click()
        expect(page.locator("#feedback")).to_contain_text("Bought 1")
        expect(page.locator('#tradeForm [value="sell"]')).to_be_enabled()
        page.locator('#tradeForm [value="sell"]').click()
        expect(page.locator("#feedback")).to_contain_text("Sold 1")
        expect(page.locator('#tradeForm [value="sell"]')).to_be_disabled()

    def test_quotes_input_and_focus_survive_background_refresh(self):
        page = self.page
        page.locator('#goods').select_option('ore')
        amount = page.locator('#tradeForm input[name="amount"]')
        amount.fill('3')
        amount.focus()
        page.evaluate('refresh()')
        expect(amount).to_have_value('3')
        expect(amount).to_be_focused()
        expect(page.locator('#goods')).to_have_value('ore')
        page.locator('#plotSale').click()
        expect(page.locator('#routeQuote')).to_contain_text('fuel')
        expect(page.locator('#destination')).to_be_focused()

    def test_late_refresh_cannot_revert_a_completed_trade(self):
        page = self.page
        stale = page.request.get(self.url + '/api/state').json()
        held = []
        page.route('**/api/state', lambda route: held.append(route))
        page.evaluate('void refresh()')
        page.wait_for_timeout(100)
        self.assertEqual(len(held), 1)
        page.locator('#tradeForm [value="buy"]').click()
        expect(page.locator('#feedback')).to_contain_text('Bought 1')
        balance = page.locator('#credits').inner_text()
        with page.expect_response('**/api/state'):
            held[0].fulfill(json=stale)
        page.wait_for_timeout(100)
        expect(page.locator('#credits')).to_have_text(balance)
        page.locator('#tradeForm [value="sell"]').click()
        expect(page.locator('#feedback')).to_contain_text('Sold 1')

    def test_full_tank_and_pristine_hull_disable_unnecessary_maintenance(self):
        expect(self.page.locator('#fleetForm [value="refuel"]')).to_be_disabled()
        expect(self.page.locator('#fleetForm [value="repair"]')).to_be_disabled()

    def test_failed_order_is_visible_and_does_not_change_balance(self):
        page = self.page
        before = page.request.get(self.url + '/api/state').json()['game']['credits']
        page.evaluate("command('buy', {good:'food',amount:10000})")
        expect(page.locator('#feedback')).to_have_class('feedback error')
        expect(page.locator('#log')).to_contain_text('ERROR')
        after = page.request.get(self.url + '/api/state').json()['game']['credits']
        self.assertEqual(before, after)

    def test_ship_sprites_and_shipyard_selection(self):
        page = self.page
        page.get_by_role('tab', name='Fleet', exact=True).click()
        expect(page.locator('#activeShipSprite use')).to_have_attribute('href', '/ships.svg#wayfarer')
        page.get_by_text('Shipyard & upgrades', exact=True).click()
        expect(page.locator('#shipClass option')).to_have_count(5)
        page.locator('#shipClass').select_option('wisp200')
        expect(page.locator('#shipPreview use')).to_have_attribute('href', '/ships.svg#wisp')
        expect(page.locator('#shipSpecs')).to_contain_text('200 Hz')
        page.locator('#purchaseShip').click()
        expect(page.locator('#feedback')).to_contain_text('Purchased Wisp')
        snapshot = page.request.get(self.url + '/api/state').json()
        bought = next(ship for ship in snapshot['game']['fleet'].values() if ship.get('class_id') == 'wisp200')
        page.locator('#shipPicker').select_option(bought['id'])
        expect(page.locator('#activeShipSprite use')).to_have_attribute('href', '/ships.svg#wisp')
        sprite_response = page.request.get(self.url + '/ships.svg')
        self.assertTrue(sprite_response.ok)
        self.assertIn('image/svg+xml', sprite_response.headers['content-type'])

    def test_route_selection_is_visible_and_survives_refresh(self):
        page = self.page
        planet = page.get_by_role("button", name="Choose planet Kepler", exact=True)
        planet.focus()
        planet.press("Enter")
        expect(planet).to_have_attribute("aria-pressed", "true")
        expect(page.locator("#destination")).to_have_value("Kepler")
        expect(page.locator("#routeQuote")).to_contain_text("fuel")
        page.evaluate("refresh()")
        expect(page.locator("#destination")).to_have_value("Kepler")
        expect(page.get_by_role("button", name="Choose planet Kepler", exact=True)).to_have_attribute("aria-pressed", "true")
        page.get_by_role('button', name='Travel to Kepler', exact=True).click()
        expect(page.locator("#transportStatus")).to_contain_text("en route")
        expect(page.locator('#flightForm [value="travel"]')).to_be_disabled()
        expect(page.locator("#routeQuote")).to_contain_text("Arrival")
        expect(page.locator('#tradeForm [value="buy"]')).to_be_disabled()

    def test_intergalactic_trip_uses_normal_fleet_and_arrives_in_new_market(self):
        page = self.page
        start = page.request.get(self.url + '/api/state').json()
        ship_id = start['game']['active_ship_id']
        credits = start['game']['credits']
        page.locator('#destination').select_option('jump:SIM-K7OR', timeout=1000)
        expect(page.locator('#routeQuote')).to_contain_text('10 fuel')
        expect(page.get_by_role('button', name='Choose galaxy SIM-K7OR', exact=True)).to_have_attribute('aria-pressed', 'true')
        galaxy_node = page.get_by_role('button', name='Choose galaxy SIM-K7OR', exact=True)
        galaxy_node.focus()
        page.evaluate('refresh()')
        expect(galaxy_node).to_be_focused()
        page.locator('#flightForm [value="travel"]').click()
        expect(page.locator('#transportStatus')).to_contain_text('Crossing')
        expect(page.locator('#tradeForm [value="buy"]')).to_be_disabled()
        # Deterministic simulator windows, not required during normal gameplay.
        for _ in range(20):
            response = page.request.post(self.url + '/api/action', data={'action': 'mail_step', 'loss': 0, 'budget_frames': 64})
            self.assertTrue(response.ok)
            snapshot = response.json()['state']
            if snapshot['navigation']['current_galaxy'] == 'SIM-K7OR':
                break
        self.assertEqual(snapshot['navigation']['current_galaxy'], 'SIM-K7OR')
        page.evaluate('refresh()')
        expect(page.locator('#name')).to_have_text('SIM-K7OR Galaxy')
        self.assertEqual(snapshot['game']['active_ship_id'], ship_id)
        self.assertEqual(snapshot['game']['credits'], credits)
        expect(page.locator('#market tr')).to_have_count(7)
        page.locator('#destination').select_option('jump:home')
        page.locator('#flightForm [value="travel"]').click()
        for _ in range(20):
            snapshot = page.request.post(self.url + '/api/action', data={'action': 'mail_step', 'loss': 0, 'budget_frames': 64}).json()['state']
            if snapshot['navigation']['current_galaxy'] == 'home':
                break
        self.assertEqual(snapshot['navigation']['current_galaxy'], 'home')


    def test_click_ship_then_destination_then_travel(self):
        page = self.page
        bought = page.request.post(self.url + '/api/action', data={
            'id': 'extra-scout', 'action': 'purchase_ship', 'args': {'class_id': 'scout500'}}).json()['result']
        page.evaluate('refresh()')
        ship = page.get_by_role('button', name=f"Select ship Scout ({bought['ship_id']})", exact=True)
        ship.click()
        expect(ship).to_have_attribute('aria-pressed', 'true')
        expect(page.locator('#selectedShipSummary')).to_contain_text('Scout')
        page.get_by_role('button', name='Choose planet Kepler', exact=True).click()
        travel = page.get_by_role('button', name='Travel to Kepler', exact=True)
        expect(travel).to_be_visible()
        travel.hover()
        expect(travel.locator('.travel-hover')).to_be_visible()
        expect(travel.locator('.travel-hover')).to_have_text('make it so')
        travel.click()
        expect(page.locator('#transportStatus')).to_contain_text('en route')
        snapshot = page.request.get(self.url + '/api/state').json()
        self.assertEqual(snapshot['game']['fleet'][bought['ship_id']]['destination'], 'Kepler')
        self.assertIsNone(snapshot['game']['fleet']['ship-1']['destination'])

    def test_direct_galaxies_are_outside_local_boundary_with_reported_neighbors(self):
        page = self.page
        response = page.request.post(self.url + '/api/action', data={
            'action': 'discover', 'peer': 'K7DIRECT', 'neighbors': [
                {'peer': 'W7SECOND', 'goodput_bps': 35}, {'peer': 'N0SECOND', 'goodput_bps': 20}]})
        self.assertTrue(response.ok)
        page.evaluate('refresh()')
        direct = page.get_by_role('button', name='Choose galaxy K7DIRECT', exact=True)
        expect(direct).to_be_visible()
        boundary = page.locator('#localGalaxyBoundary').bounding_box()
        direct_box = direct.bounding_box()
        self.assertGreater(direct_box['x'], boundary['x'] + boundary['width'])
        for station in ('W7SECOND', 'N0SECOND'):
            neighbor = page.locator(f'[data-reported-station="{station}"][data-reported-by="K7DIRECT"]')
            expect(neighbor).to_be_visible()
            expect(neighbor).to_have_attribute('aria-label', f'Reported station {station} via K7DIRECT')
        self.assertEqual(page.locator('.local-world [data-radio-station]').count(), 0)
        direct.click()
        expect(page.get_by_role('button', name='Travel to K7DIRECT Galaxy', exact=True)).to_be_enabled()

    def test_abort_transmission_early_returns_ship_without_extra_penalty(self):
        page = self.page
        page.locator('#destination').select_option('jump:SIM-K7OR')
        page.locator('#travelButton').click()
        abort = page.get_by_role('button', name='Abort transmission', exact=True)
        expect(abort).to_be_visible()
        expect(page.locator('#abortHint')).to_contain_text('No extra penalty')
        abort.click()
        expect(page.locator('#feedback')).to_contain_text('Transmission aborted')
        snapshot = page.request.get(self.url + '/api/state').json()
        self.assertEqual(snapshot['game']['ship']['condition'], 100)
        self.assertEqual(snapshot['game']['ship']['fuel'], 30)
        self.assertEqual(snapshot['game']['ship']['galaxy'], 'home')
        self.assertNotIn('voyage', snapshot['game']['ship'])
        expect(abort).not_to_be_visible()
        expect(page.locator('#travelButton')).to_be_enabled()

    def test_abort_transmission_late_displays_and_confirms_hull_penalty(self):
        page = self.page
        page.locator('#destination').select_option('jump:SIM-K7OR')
        page.locator('#travelButton').click()
        for _ in range(10):
            snapshot = page.request.post(self.url + '/api/action', data={
                'action': 'mail_step', 'loss': 0, 'budget_frames': 64}).json()['state']
            voyage = snapshot['navigation']['voyages'].get('ship-1')
            if voyage and voyage.get('abort_penalty', 0) > 0:
                break
        self.assertEqual(voyage['abort_penalty'], 10)
        page.evaluate('refresh()')
        expect(page.locator('#abortHint')).to_contain_text('10 hull')
        dialogs = []
        def confirm_abort(dialog):
            dialogs.append(dialog.message)
            dialog.accept()
        page.once('dialog', confirm_abort)
        page.get_by_role('button', name='Abort transmission', exact=True).click()
        expect(page.locator('#feedback')).to_contain_text('Transmission aborted')
        self.assertIn('10 hull', dialogs[0])
        snapshot = page.request.get(self.url + '/api/state').json()
        self.assertEqual(snapshot['game']['ship']['condition'], 90)
        self.assertNotIn('voyage', snapshot['game']['ship'])

    def test_promoted_reported_station_selects_its_direct_galaxy(self):
        page = self.page
        page.request.post(self.url + '/api/action', data={
            'action': 'discover', 'peer': 'N0PARENT', 'neighbors': [{'peer': 'N0CHILD'}]})
        page.request.post(self.url + '/api/action', data={'action': 'discover', 'peer': 'N0CHILD'})
        page.evaluate('refresh()')
        page.locator('[data-reported-station="N0CHILD"][data-reported-by="N0PARENT"]').click()
        expect(page.locator('#destination')).to_have_value('jump:N0CHILD')
        expect(page.get_by_role('button', name='Travel to N0CHILD Galaxy', exact=True)).to_be_enabled()

    def test_mobile_map_keeps_touch_targets_large_as_galaxies_are_discovered(self):
        page = self.page
        page.set_viewport_size({'width': 390, 'height': 844})
        for station in ('N0PARENT', 'N0CHILD', 'N0ONE', 'N0TWO', 'N0THREE', 'N0FOUR', 'N0FIVE', 'N0SIX'):
            response = page.request.post(self.url + '/api/action', data={'action': 'discover', 'peer': station})
            self.assertTrue(response.ok)
        page.evaluate('refresh()')
        planet = page.get_by_role('button', name='Choose planet Kepler', exact=True)
        bounds = planet.bounding_box()
        self.assertGreaterEqual(bounds['width'], 40)
        self.assertGreaterEqual(bounds['height'], 40)
        self.assertTrue(page.locator('.map').evaluate('node => node.scrollHeight > node.clientHeight'))
        self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))

if __name__ == "__main__":
    unittest.main(verbosity=2)
