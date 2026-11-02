"""Run: uv run --with playwright python tests/browser_combat.py."""
import sys
import unittest
from playwright.sync_api import expect
from browser_smoke import CockpitBrowserTests, ROOT
sys.path.insert(0,str(ROOT))
from test_pirate_rewards import pirate_game


class CombatBrowserTests(CockpitBrowserTests):
    def make_initial_game(self):
        g=pirate_game(seed=43 if 'flee' in self._testMethodName else 42,strength=3)
        if 'defeat' in self._testMethodName:
            g.hard_mode=True;g.ship['condition']=1
        return g

    def test_fight_multiple_turns_and_reload(self):
        page=self.page;dialog=page.locator('.raider-dialog')
        dialog.get_by_role('button',name='Fire weapons · engage').click()
        expect(dialog).to_contain_text('Turn 2')
        expect(dialog).to_contain_text('2 strength')
        expect(dialog.get_by_role('button',name='Continue flight')).not_to_be_visible()
        page.reload()
        expect(dialog).to_contain_text('Turn 2')
        dialog.get_by_role('button',name='Fire weapons · engage').click()
        expect(dialog).to_contain_text('Turn 3')
        self.assertAlmostEqual(dialog.locator('.raider-meter').evaluate('e=>parseFloat(e.style.width)'),100/3,places=2)
        page.screenshot(path='/tmp/tradenet-combat-turns.png')
        dialog.get_by_role('button',name='Fire weapons · engage').click()
        expect(dialog.get_by_role('heading',name='Claim your salvage')).to_be_visible()
        dialog.get_by_role('button',name='Leave salvage & continue').click()
        expect(dialog).not_to_be_visible()

    def test_failed_flee_offers_choices_again(self):
        page=self.page;dialog=page.locator('.raider-dialog')
        dialog.get_by_role('button',name='Break contact · evade',exact=False).click()
        expect(dialog).to_contain_text('Escape failed')
        expect(dialog).to_contain_text('Turn 2')
        expect(dialog.get_by_role('button',name='Fire weapons · engage')).to_be_enabled()
        dialog.get_by_role('button',name='Pay toll',exact=False).click()
        expect(dialog).to_contain_text('Pirate toll paid')
        expect(dialog.get_by_role('button',name='Continue flight')).to_be_visible()

    def test_hard_mode_defeat_ends_encounter(self):
        page=self.page;dialog=page.locator('.raider-dialog')
        console_errors=[]
        page.on('console',lambda message:console_errors.append(message.text) if message.type=='error' else None)
        dialog.get_by_role('button',name='Fire weapons · engage').click()
        expect(dialog.get_by_role('heading',name='Vessel disabled')).to_be_visible()
        expect(dialog).to_contain_text('Ship lost')
        self.assertEqual(page.evaluate('Object.keys(state.game.fleet).length'),0)
        self.assertEqual(console_errors,[])


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(CombatBrowserTests(name) for name in
        ('test_fight_multiple_turns_and_reload','test_failed_flee_offers_choices_again','test_hard_mode_defeat_ends_encounter')))
    sys.exit(not result.wasSuccessful())
