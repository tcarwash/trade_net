"""Run: uv run --with playwright python tests/browser_progression.py."""
import sys
import unittest
from playwright.sync_api import expect
from browser_smoke import CockpitBrowserTests, ROOT
sys.path.insert(0,str(ROOT))
from tradenet import Game


class ProgressionBrowserTests(CockpitBrowserTests):
    def make_initial_game(self):
        g=Game.new(42);g.credits=20000
        g.command('other','purchase_ship',tier=0)
        other=next(sid for sid in g.fleet if sid!=g.active_ship_id)
        g.command('name','rename_ship',ship_id=other,name='Second Light')
        g.ship['equipment'].append('scanner')
        g.visited_ports=list(g.ports)
        if 'gate_contract' not in self._testMethodName:
            for site in g.ports.values():
                if site.get('map_gate'):site['map_gate']['unlocked']=True
        module=g._recover_module('pilgrims_lantern','test wreck')
        if 'settlement' in self._testMethodName:
            g.ship['location']='Prospect';g._bind_ship();g.observe_markets()
            g.cargo.update(food=6,medicine=2)
        return g

    def test_mod_refit_transfer_and_reload(self):
        page=self.page
        page.evaluate("openShipyardAt('Haven');selectShipyardTab('outfit')")
        card=page.locator('[data-module-id="module-1"]')
        expect(card).to_contain_text('Pilgrim’s Lantern')
        expect(card).to_contain_text('STOWED')
        card.get_by_role('button',name='Install modification').click()
        expect(card).to_contain_text('INSTALLED')
        card.get_by_role('button',name='Uninstall to port locker').click()
        expect(card).to_contain_text('STORED')
        other=page.evaluate("Object.keys(state.game.fleet).find(id=>id!==state.game.active_ship_id)")
        card.get_by_role('combobox').select_option(other)
        card.get_by_role('button',name='Install modification').click()
        expect(card).to_contain_text('INSTALLED · Second Light')
        self.assertEqual(page.evaluate("state.game.module_inventory['module-1'].ship_id"),other)
        page.reload()
        page.wait_for_function('state !== null')
        page.evaluate("openShipyardAt('Haven');selectShipyardTab('outfit')")
        expect(card).to_contain_text('INSTALLED · Second Light')
        page.set_viewport_size({'width':390,'height':900})
        page.screenshot(path='/tmp/tradenet-unique-mods.png')
        self.assertTrue(page.evaluate('document.documentElement.scrollWidth<=innerWidth'))

    def test_gate_contract_link_and_filter(self):
        page=self.page
        page.evaluate("showPlanetInfo('Prospect',true)")
        page.locator('#routeQuote').get_by_role('button',name='View unlocking contract').click()
        expect(page.locator('#planetDialog')).not_to_be_visible()
        expect(page.locator('[data-job-id="hub-clearance-prospect"]')).to_be_visible()
        expect(page.locator('#contractFilters [data-filter="gates"]')).to_have_attribute('aria-pressed','true')
        expect(page.locator('#contractFilters [data-filter="gates"]')).to_contain_text('Route unlocks')
        self.assertEqual(page.locator('#contracts [data-kind="frontier_gate"]:visible').count(),3)
        self.assertEqual(page.locator('#contracts [data-kind="freight"]:visible').count(),0)

    def test_pursuit_warning_and_jettison(self):
        page=self.page
        warning=page.locator('#pursuitWarning')
        expect(warning).to_be_visible()
        expect(warning).to_contain_text('Pilgrim’s Lantern')
        expect(warning).to_contain_text('Closing pressure')
        self.assertEqual(page.locator('.pursuit-marker').count(),1)
        page.screenshot(path='/tmp/tradenet-pursuit.png')
        warning.get_by_role('button',name='Jettison Pilgrim’s Lantern permanently').click()
        expect(page.locator('#feedback')).to_contain_text('jettisoned permanently')
        self.assertEqual(page.evaluate("state.game.module_inventory['module-1'].status"),'jettisoned')
        self.assertEqual(page.locator('.pursuit-marker').count(),0)
        expect(warning).to_contain_text('break off')

    def test_settlement_supply_project(self):
        page=self.page
        page.get_by_role('tab',name='Contracts',exact=True).click()
        project=page.locator('[data-settlement="Prospect"]')
        expect(project).to_contain_text('Frontier')
        project.get_by_role('button',name='Deliver 6 food, 2 medicine').click()
        expect(project).to_contain_text('Established')
        expect(project).to_contain_text('Build the production district')
        self.assertEqual(page.evaluate('state.game.settlement_progress.Prospect.level'),1)
        page.reload()
        page.get_by_role('tab',name='Contracts',exact=True).click()
        expect(project).to_contain_text('Established')

    def test_network_and_direct_route_planning(self):
        page=self.page
        page.locator('#plotCourse').click()
        page.locator('#routeOrigin').select_option('Haven')
        page.locator('#routeDestination').select_option('Drift')
        page.locator('#routeMode').select_option('network')
        page.locator('#previewCourse').click()
        expect(page.locator('#coursePreview')).to_contain_text('Haven → Kepler → Drift')
        expect(page.locator('#coursePreview')).to_contain_text('2 flights')
        page.locator('#saveCourse').click()
        expect(page.locator('#plottedCourse')).to_contain_text('NETWORK COURSE')
        self.assertEqual(page.locator('.planned-course').count(),2)
        page.reload()
        expect(page.locator('#plottedCourse')).to_contain_text('Haven → Kepler → Drift')
        page.locator('#plotCourse').click()
        page.locator('#routeDestination').select_option('Drift')
        page.locator('#routeMode').select_option('direct')
        page.locator('#previewCourse').click()
        expect(page.locator('#coursePreview')).to_contain_text('1 flight')
        page.set_viewport_size({'width':390,'height':900})
        page.screenshot(path='/tmp/tradenet-route-planner.png')
        self.assertTrue(page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
        page.locator('#saveCourse').click()
        expect(page.locator('#plottedCourse')).to_contain_text('DIRECT COURSE')
        self.assertEqual(page.locator('.planned-course').count(),1)
        page.locator('#plottedCourse').get_by_role('button',name='Clear course').click()
        expect(page.locator('#plottedCourse')).not_to_be_visible()


if __name__=='__main__':
    suite=unittest.TestSuite(ProgressionBrowserTests(name) for name in
        ('test_mod_refit_transfer_and_reload','test_settlement_supply_project','test_network_and_direct_route_planning','test_pursuit_warning_and_jettison','test_gate_contract_link_and_filter'))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(not result.wasSuccessful())
