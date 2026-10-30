"""Guard the core browser anchors that previously caused a render crash."""

import unittest
from html.parser import HTMLParser
from pathlib import Path


class _Ids(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        self.ids.update(value for name, value in attrs if name == "id")


class BrowserUIContractTests(unittest.TestCase):
    def test_required_gameplay_anchors_exist(self):
        html = (Path(__file__).resolve().parents[1] /
                "tradenet" / "web" / "index.html").read_text()
        parser = _Ids()
        parser.feed(html)
        self.assertTrue({"galaxy", "transportStatus", "detail", "feedback",
                         "goods", "destination", "fleetForm", "tradeForm",
                         "contracts", "log", "exchangeForm", "debugToggle",
                         "guideText"}.issubset(parser.ids))
        self.assertIn("drawShipOverlay(s,positions)", html)
        self.assertIn("updateRouteQuote()", html)


if __name__ == "__main__":
    unittest.main()
