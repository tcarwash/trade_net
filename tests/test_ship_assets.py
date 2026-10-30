"""Dependency-free contract for the editable, externally reusable ship vectors."""
import re
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET


ASSET = Path(__file__).resolve().parents[1] / "tradenet/web/ships.svg"
NS = "{http://www.w3.org/2000/svg}"
SHIPS = ("wayfarer", "scout", "courier", "express", "wisp", "hauler")
NUMBER = r"-?(?:\d+(?:\.\d*)?|\.\d+)"


class ShipAssetContractTests(unittest.TestCase):
    def test_reusable_safe_distinct_bounded_ship_sheet(self):
        self.assertTrue(ASSET.is_file(), "Ship sprite sheet must exist")
        text = ASSET.read_text()
        self.assertNotIn("<!", text, "No entities, external DTDs or hidden markup")
        root = ET.fromstring(text)
        self.assertEqual(root.tag, NS + "svg")
        self.assertEqual(root.get("viewBox"), "0 0 576 112")
        self.assertEqual(root.get("width"), "576")
        self.assertEqual(root.get("height"), "112")
        elements = list(root.iter())
        ids = [e.get("id") for e in elements if e.get("id")]
        self.assertEqual(len(ids), len(set(ids)), "IDs must be globally unique")
        by_id = {e.get("id"): e for e in elements if e.get("id")}
        symbols = root.findall(NS + "symbol")
        self.assertEqual({s.get("id") for s in symbols}, set(SHIPS))
        self.assertEqual(len(symbols), 6)
        allowed = {"svg", "defs", "symbol", "title", "desc", "g", "path",
                   "linearGradient", "radialGradient", "stop", "use"}
        for element in elements:
            self.assertIn(element.tag.removeprefix(NS), allowed)
            for attr, value in element.attrib.items():
                self.assertFalse(attr.lower().startswith("on"))
                self.assertNotIn("style", attr)
                if attr.endswith("href"):
                    self.assertTrue(value.startswith("#"), "References stay local")
                    self.assertIn(value[1:], by_id)
                for reference in re.findall(r"url\(([^)]+)\)", value):
                    self.assertTrue(reference.startswith("#"))
                    self.assertIn(reference[1:], by_id)
        gradients = [e for e in elements if e.tag.endswith("Gradient")]
        self.assertGreaterEqual(len(gradients), 4)
        for gradient in gradients:
            self.assertTrue(gradient.get("id", "").startswith("tn-ship-"))
        hulls = []
        for symbol in symbols:
            with self.subTest(ship=symbol.get("id")):
                self.assertEqual(symbol.get("viewBox"), "0 0 96 112")
                self.assertIsNotNone(symbol.find(NS + "title"))
                paths = symbol.findall(".//" + NS + "path")
                self.assertGreaterEqual(len(paths), 9, "Hull, canopy, plating, engines")
                hull = next(p for p in paths if p.get("data-part") == "hull")
                hulls.append(hull.get("d"))
                self.assertTrue(any(p.get("data-part") == "canopy" for p in paths))
                self.assertTrue(any(p.get("data-part") == "exhaust" for p in paths))
                for path in paths:
                    # Only absolute polynomial paths: the control-point convex hull
                    # bounds the complete curve, including the exhaust tips.
                    d = path.get("d", "")
                    self.assertRegex(d, r"^M")
                    self.assertFalse(re.sub(NUMBER + r"|[MLCQZ ,\s]", "", d))
                    coordinates = [float(n) for n in re.findall(NUMBER, d)]
                    self.assertEqual(len(coordinates) % 2, 0)
                    self.assertTrue(all(6 <= x <= 90 for x in coordinates[::2]))
                    self.assertTrue(all(6 <= y <= 106 for y in coordinates[1::2]))
                    self.assertLessEqual(float(path.get("stroke-width", "1")), 2)
                    self.assertIsNone(path.get("transform"))
                self.assertFalse(symbol.findall(".//" + NS + "g"),
                                 "Untransformed paths preserve bounded geometry")
        self.assertEqual(len(set(hulls)), 6, "Every class needs its own silhouette")
        previews = root.findall(NS + "use")
        self.assertEqual([p.get("href") for p in previews], ["#" + s for s in SHIPS])
        self.assertEqual([p.get("x") for p in previews],
                         ["0", "96", "192", "288", "384", "480"])
        for preview in previews:
            self.assertEqual(preview.get("width"), "96")
            self.assertEqual(preview.get("height"), "112")
            self.assertEqual(preview.get("y"), "0")


if __name__ == "__main__":
    unittest.main()
