"""Guard the core browser anchors that previously caused a render crash."""

import unittest
import json
from html.parser import HTMLParser
from pathlib import Path


class _Ids(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        self.ids.update(value for name, value in attrs if name == "id")


class BrowserUIContractTests(unittest.TestCase):
    @staticmethod
    def browser_html():
        return (Path(__file__).resolve().parents[1] /
                "tradenet" / "web" / "index.html").read_text()

    def test_required_gameplay_anchors_exist(self):
        html = self.browser_html()
        parser = _Ids()
        parser.feed(html)
        self.assertTrue({"galaxy", "transportStatus", "detail", "feedback",
                         "goods", "destination", "fleetForm", "tradeForm",
                         "contracts", "log", "exchangeForm", "debugToggle",
                         "guideText"}.issubset(parser.ids))
        self.assertIn("drawShipOverlay(s,positions)", html)
        self.assertIn("updateRouteQuote()", html)

    def test_mobile_game_shell_and_action_feedback(self):
        html = self.browser_html()
        parser = _Ids()
        parser.feed(html)
        self.assertTrue({"objectiveBrief", "objectiveAction", "flightProgress",
                         "saveIndicator", "tabCommand", "tabFleet", "tabContracts",
                         "tabComms"}.issubset(parser.ids))
        for marker in ("@media(max-width:760px)", "@media(max-width:600px)",
                       "safe-area-inset-bottom", "data-label", "currentContractsFilter",
                       "role','listitem", "centerLocalMap", "aria-valuenow",
                       "nextActionCommand='complete_story'", "nextActionCommand='deliver_vip'",
                       "nextActionCommand='deliver_local'", "prefers-reduced-motion"):
            with self.subTest(marker=marker):
                self.assertIn(marker, html)

    def test_installable_mobile_asset_contract(self):
        root = Path(__file__).resolve().parents[1] / "tradenet" / "web"
        manifest = json.loads((root / "manifest.webmanifest").read_text())
        self.assertEqual(manifest["display"], "standalone")
        self.assertEqual(manifest["start_url"], "/")
        for icon in manifest["icons"]:
            self.assertTrue((root / icon["src"].lstrip("/")).is_file(), icon)
        self.assertIn('rel="manifest"', self.browser_html())
        self.assertTrue((root / "apple-touch-icon.png").is_file())


if __name__ == "__main__":
    unittest.main()
