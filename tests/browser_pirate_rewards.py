"""Run: uv run --with playwright python tests/browser_pirate_rewards.py."""
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.request import urlopen
from playwright.sync_api import expect
from browser_smoke import CockpitBrowserTests, ROOT
sys.path.insert(0, str(ROOT))
from test_pirate_rewards import pirate_game


class PirateRewardBrowserTests(CockpitBrowserTests):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tradenet-pirates-')
        self.addCleanup(self.temp.cleanup)
        game = pirate_game()
        if self._testMethodName.endswith('full_hold'):
            game.cargo['ore'] = game.ship['capacity']
        game.save(Path(self.temp.name) / 'galaxy.json')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        self.url = f'http://127.0.0.1:{port}'
        self.server = subprocess.Popen(
            [sys.executable, '-m', 'tradenet.web', '--port', str(port),
             '--save', str(Path(self.temp.name) / 'galaxy.json')],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.stop_server)
        for _ in range(100):
            try:
                urlopen(self.url + '/api/state', timeout=1).close()
                break
            except OSError:
                time.sleep(.05)
        else:
            raise RuntimeError('Preview server did not start')
        self.page = self.browser.new_page(viewport={'width': 1440, 'height': 1000})
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.goto(self.url)
        expect(self.page.locator('#credits')).not_to_have_text('—')

    def test_collect_after_reload(self):
        page = self.page
        dialog = page.locator('.raider-dialog')
        expect(dialog).to_be_visible()
        before = page.evaluate('state.game.credits')
        dialog.get_by_role('button', name='Fire weapons · engage').click()
        expect(dialog.get_by_role('heading', name='Claim your salvage')).to_be_visible()
        credits = page.evaluate('state.game.credits')
        self.assertTrue(60 <= credits-before <= 120)
        expect(dialog).to_contain_text('bounty paid')
        self.assertEqual(page.evaluate('Object.values(state.game.cargo).reduce((a,b)=>a+b,0)'), 0)
        page.reload()
        expect(dialog.get_by_role('heading', name='Claim your salvage')).to_be_visible()
        self.assertEqual(page.evaluate('state.game.credits'), credits)
        page.set_viewport_size({'width': 390, 'height': 900})
        page.screenshot(path='/tmp/tradenet-pirate-salvage.png')
        dialog.get_by_role('button', name='Recover salvage', exact=True).click()
        expect(dialog).not_to_be_visible()
        cargo = page.evaluate('Object.values(state.game.cargo).reduce((a,b)=>a+b,0)')
        self.assertTrue(1 <= cargo <= 3)
        self.assertEqual(page.evaluate('state.game.credits'), credits)
        expect(page.locator('#feedback')).to_contain_text('recovered')

    def test_leave_with_full_hold(self):
        page = self.page
        dialog = page.locator('.raider-dialog')
        dialog.get_by_role('button', name='Fire weapons · engage').click()
        expect(dialog.get_by_role('heading', name='Claim your salvage')).to_be_visible()
        expect(dialog.get_by_role('button', name='Recover salvage', exact=False)).to_be_disabled()
        credits = page.evaluate('state.game.credits')
        dialog.get_by_role('button', name='Leave salvage & continue').click()
        expect(dialog).not_to_be_visible()
        self.assertEqual(page.evaluate('state.game.cargo.ore'), 30)
        self.assertEqual(page.evaluate('state.game.credits'), credits)


if __name__ == '__main__':
    suite = unittest.TestSuite(PirateRewardBrowserTests(name) for name in
                              ('test_collect_after_reload', 'test_leave_with_full_hold'))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(not result.wasSuccessful())
