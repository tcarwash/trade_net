"""Run: uv run --with playwright python tests/browser_market.py."""
import sys
import unittest
from playwright.sync_api import expect
from browser_smoke import CockpitBrowserTests


class MarketBrowserTests(CockpitBrowserTests):
    def test_staged_market(self):
        page = self.page
        page.evaluate("marketDialog.showModal()")
        food = page.locator('[data-market-quantity="food"]')
        ore = page.locator('[data-market-quantity="ore"]')
        expect(page.locator('#acceptDeal')).to_be_disabled()
        food.fill('2')
        ore.fill('1')
        expect(page.locator('#dealStatus')).to_contain_text('2 commodities selected')
        expect(page.locator('#acceptDeal')).to_be_enabled()
        page.locator('#marketHeading').click()
        page.evaluate('refresh()')
        expect(ore).to_have_value('1')
        page.locator('#acceptDeal').click()
        expect(page.locator('#feedback')).to_contain_text('Trade accepted')
        expect(food).to_have_value('0')
        self.assertEqual(page.evaluate('state.game.cargo.food'), 2)
        self.assertEqual(page.evaluate('state.game.cargo.ore'), 1)
        food.fill('-1')
        ore.fill('2')
        expect(page.locator('#dealStatus')).to_contain_text('2 commodities selected')
        page.locator('#acceptDeal').click()
        expect(food).to_have_value('0')
        self.assertEqual(page.evaluate('state.game.cargo.food'), 1)
        self.assertEqual(page.evaluate('state.game.cargo.ore'), 3)
        food.fill('-2')
        expect(page.locator('#acceptDeal')).to_be_disabled()
        expect(food).to_have_attribute('aria-invalid', 'true')
        food.fill('1.5')
        expect(page.locator('#acceptDeal')).to_be_disabled()
        page.locator('#resetDeal').click()
        page.locator('#marketSearch').fill('medicine')
        expect(page.locator('#market tr:visible')).to_have_count(1)
        page.locator('#marketSearch').fill('')
        food.fill('3')
        ore.fill('-1')
        page.locator('#marketSearch').focus()
        page.screenshot(path='/tmp/tradenet-market-desktop.png')
        for width in (1024, 768, 390, 320):
            page.set_viewport_size({'width': width, 'height': 900})
            self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
            expect(page.locator('#acceptDeal')).to_be_in_viewport()
            expect(page.locator('#market tr:visible')).to_have_count(7)
        page.set_viewport_size({'width':390,'height':900})
        page.screenshot(path='/tmp/tradenet-market-mobile.png')
        page.locator('#resetDeal').click()
        page.get_by_role('button', name='Buy one food', exact=True).click()
        expect(food).to_have_value('1')
        page.locator('#acceptDeal').click()
        expect(food).to_have_value('0')
        self.assertEqual(page.evaluate('state.game.cargo.food'), 2)
        page.locator('#marketDialog .modal-close').click()
        page.evaluate('marketDialog.showModal()')
        expect(food).to_have_value('0')


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([
        MarketBrowserTests('test_staged_market')]))
    sys.exit(not result.wasSuccessful())
