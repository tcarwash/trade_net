"""Real browser UX checks. Run: uv run --with playwright python tests/browser_smoke.py.

Install Chromium once with: uv run --with playwright playwright install chromium.
Set TRADENET_BROWSER=firefox for Firefox; TRADENET_SCREENSHOT_DIR for snapshots.
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
        cls.browser = getattr(cls.playwright, os.environ.get("TRADENET_BROWSER", "chromium")).launch()

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
        expect(page.locator('#debugToggle')).to_have_attribute('aria-pressed', 'true')
        expect(page.locator("#exchangeForm")).not_to_be_visible()  # Comms owns radio UI.
        page.locator("#debugToggle").click()
        expect(page.locator("#exchangeForm")).not_to_be_visible()
        page.get_by_role('tab', name='Comms', exact=True).click()
        expect(page.locator("#exchangeForm")).to_be_visible()
        page.get_by_role('tab', name='Flight deck', exact=True).click()
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

    def test_haven_supply_planner_dispatches_idle_ship(self):
        page = self.page
        page.get_by_role('tab', name='Fleet', exact=True).click()
        expect(page.locator('#fleetAutomation')).to_be_visible()
        page.locator('#autoRouteKind').select_option('supply')
        expect(page.locator('#autoDestination')).to_have_value('Haven')
        expect(page.locator('#autoDestination')).to_be_disabled()
        page.locator('#autoOrigin').select_option('Kepler')
        page.locator('#autoQuantity').fill('2')
        page.locator('#autoRuns').fill('1')
        expect(page.get_by_role('button', name='Dispatch an idle vessel')).to_be_enabled()
        page.get_by_role('button', name='Dispatch an idle vessel').click()
        expect(page.locator('#fleetAutomation .auto-route-card')).to_have_count(1)
        expect(page.locator('#fleetAutomation .auto-route-card')).to_contain_text('Haven procurement')
        expect(page.locator('#feedback')).to_contain_text('Haven procurement route commissioned')
        self.snapshot('fleet-supply-desktop')

    def test_persistent_fleet_doctrine_policy_and_mobile_layout(self):
        page = self.page
        page.get_by_role('tab', name='Fleet', exact=True).click()
        expect(page.locator('#fleetDoctrine')).to_be_visible()
        expect(page.locator('#doctrineSaveTarget')).to_be_disabled()  # Scout a source first.
        page.locator('#doctrineReserve').fill('500')
        page.locator('#doctrineSaveReserve').click()
        expect(page.locator('#feedback')).to_contain_text('protects 500 credits')
        page.locator('#doctrineReturn').uncheck()
        page.locator('#doctrineService').check()
        page.locator('#doctrineRepair').fill('55')
        page.locator('#doctrineFuel').fill('40')
        page.locator('#doctrineSavePolicy').click()
        expect(page.locator('#feedback')).to_contain_text('service and home-port orders updated')
        state = page.request.get(self.url + '/api/state').json()['game']
        self.assertEqual(state['fleet_credit_reserve'], 500)
        self.assertEqual(state['ship']['fleet_policy']['repair_below'], 55)
        self.assertFalse(state['ship']['fleet_policy']['return_to_haven'])
        page.set_viewport_size({'width': 390, 'height': 844})
        self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        self.snapshot('fleet-doctrine-mobile')

    def test_beacon_preview_and_mobile_comms_are_rf_safe(self):
        page = self.page
        page.get_by_role('tab', name='Comms', exact=True).click()
        expect(page.locator('#beaconPanel')).to_be_visible()
        expect(page.locator('#beaconSend')).to_be_disabled()
        page.locator('#beaconGood').select_option('food')
        page.locator('#beaconPreviewButton').click()
        expect(page.locator('#beaconQuote')).to_contain_text('bytes')
        expect(page.locator('#feedback')).to_contain_text('Nothing transmitted')
        page.evaluate("""() => {state.radio_beacons={AG7SU:{callsign:'AG7SU',good:'ore',abundance:5,contract:{id:'AG7SU-C0001',good:'food',quantity:2},observed_at:Date.now()/1000,verified:false}};renderBeacon()}""")
        expect(page.locator('#beaconHeard .beacon-sighting')).to_have_count(1)
        self.snapshot('beacon-desktop')
        page.set_viewport_size({'width': 390, 'height': 844})
        self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        expect(page.locator('#beaconPanel')).to_be_visible()
        self.snapshot('beacon-mobile')

    def snapshot(self, name):
        directory = os.environ.get('TRADENET_SCREENSHOT_DIR')
        if directory:
            Path(directory).mkdir(parents=True, exist_ok=True)
            self.page.screenshot(path=str(Path(directory) / (name + '.png')), full_page=True)

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
        expect(page.locator('#momentDialog')).to_be_visible()
        page.locator('#momentContinue').click()
        snapshot = page.request.get(self.url + '/api/state').json()
        bought = next(ship for ship in snapshot['game']['fleet'].values() if ship.get('class_id') == 'wisp200')
        page.locator('#shipPicker').select_option(bought['id'])
        expect(page.locator('#activeShipSprite use')).to_have_attribute('href', '/ships.svg#wisp')
        sprite_response = page.request.get(self.url + '/ships.svg')
        self.assertTrue(sprite_response.ok)
        self.assertIn('image/svg+xml', sprite_response.headers['content-type'])

    def test_route_selection_is_visible_and_survives_refresh(self):
        page = self.page
        snapshot = page.request.get(self.url + '/api/state').json()
        destination = next(port for port in snapshot['game']['ports']
                           if port not in ('Haven', snapshot['asteroid_field']['blocked_port']))
        planet = page.locator(f'.planet-target[data-port="{destination}"]')
        planet.focus()
        planet.press("Enter")
        expect(planet).to_have_attribute("aria-pressed", "true")
        expect(page.locator("#destination")).to_have_value(destination)
        expect(page.locator("#routeQuote")).to_contain_text("fuel")
        page.evaluate("refresh()")
        expect(page.locator("#destination")).to_have_value(destination)
        expect(page.locator(f'.planet-target[data-port="{destination}"]')).to_have_attribute("aria-pressed", "true")
        page.get_by_role('button', name=f'Travel to {destination}', exact=True).click()
        expect(page.locator("#transportStatus")).to_contain_text("en route")
        expect(page.locator('#flightForm [value="travel"]')).to_be_disabled()
        expect(page.locator("#routeQuote")).to_contain_text("Arriving")
        expect(page.locator('#tradeForm [value="buy"]')).to_be_disabled()

    def test_radio_navigation_has_no_fictitious_jump_destination(self):
        page = self.page
        options = page.locator('#destination option').evaluate_all('(nodes) => nodes.map(n=>n.value)')
        self.assertTrue(options)
        self.assertFalse(any(option.startswith('jump:') for option in options))
        response = page.request.post(self.url + '/api/action', data={
            'id': 'unsupported-jump', 'action': 'jump',
            'args': {'galaxy': 'SIM-K7OR', 'destination': 'Haven'}})
        self.assertEqual(response.status, 400)
        state = page.request.get(self.url + '/api/state').json()
        self.assertEqual(state['navigation']['current_galaxy'], 'home')
        self.assertEqual(state['navigation']['voyages'], {})


    def test_click_ship_then_destination_then_travel(self):
        page = self.page
        state = page.request.get(self.url + '/api/state').json()
        destination = next(port for port in state['game']['ports']
                           if port not in ('Haven', state['asteroid_field']['blocked_port']))
        bought = page.request.post(self.url + '/api/action', data={
            'id': 'extra-scout', 'action': 'purchase_ship', 'args': {'class_id': 'scout500'}}).json()['result']
        page.evaluate('refresh()')
        expect(page.locator('#momentDialog')).to_be_visible()
        page.locator('#momentContinue').click()
        ship = page.get_by_role('button', name=f"Select ship Scout ({bought['ship_id']})", exact=True)
        ship.click()
        expect(ship).to_have_attribute('aria-pressed', 'true')
        expect(page.locator('#selectedShipSummary')).to_contain_text('Scout')
        page.locator('#destination').select_option(destination)
        travel = page.get_by_role('button', name=f'Travel to {destination}', exact=True)
        expect(travel).to_be_visible()
        travel.hover()
        expect(travel.locator('.travel-hover')).to_be_visible()
        expect(travel.locator('.travel-hover')).to_have_text('make it so')
        travel.click()
        expect(page.locator('#transportStatus')).to_contain_text('en route')
        snapshot = page.request.get(self.url + '/api/state').json()
        self.assertEqual(snapshot['game']['fleet'][bought['ship_id']]['destination'], destination)
        self.assertIsNone(snapshot['game']['fleet']['ship-1']['destination'])

    def test_radio_map_and_comms_do_not_offer_remote_ship_travel(self):
        page = self.page
        page.locator('#galaxyView').click()
        expect(page.locator('#galaxyView')).to_have_attribute('aria-pressed', 'true')
        self.assertFalse(page.locator('#destination option').evaluate_all(
            '(nodes) => nodes.some(n => n.value.startsWith("jump:"))'))
        page.get_by_role('tab', name='Comms', exact=True).click()
        expect(page.locator('#exchangePanel')).to_be_visible()
        expect(page.locator('#beaconPreviewButton')).to_be_enabled()
        expect(page.locator('#beaconSend')).to_be_disabled()

    def test_new_ship_event_uses_a_dismissible_moment_dialog(self):
        page = self.page
        page.get_by_role('tab', name='Fleet', exact=True).click()
        page.get_by_text('Shipyard & upgrades', exact=True).click()
        page.locator('#shipClass').select_option('wisp200')
        page.locator('#purchaseShip').click()
        dialog = page.locator('#momentDialog')
        expect(dialog).to_be_visible()
        expect(dialog.locator('#momentTitle')).to_contain_text('Wisp')
        expect(dialog.locator('#momentCategory')).to_contain_text('SHIP COMMISSIONED')
        self.snapshot('ship-commissioned-event')
        dialog.locator('#momentContinue').click()
        expect(dialog).not_to_be_visible()

    def test_mobile_map_keeps_local_touch_targets_large(self):
        page = self.page
        page.set_viewport_size({'width': 390, 'height': 844})
        planet = page.locator('.planet-target[data-port="Kepler"]')
        bounds = planet.bounding_box()
        self.assertGreaterEqual(bounds['width'], 40)
        self.assertGreaterEqual(bounds['height'], 40)
        self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))

if __name__ == "__main__":
    unittest.main(verbosity=2)
