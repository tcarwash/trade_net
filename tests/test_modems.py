import unittest

from tradenet.modems import eligible_modes


class ModemTests(unittest.TestCase):
    def test_modes_are_filtered_from_advertisements(self):
        modes = [{"mode_id": "narrow", "bandwidth_hz": 500},
                 {"mode_id": "middle", "bandwidth_hz": 1200},
                 {"mode_id": "wide", "bandwidth_hz": 2400},
                 {"mode_id": "bad", "bandwidth_hz": None}]
        self.assertEqual([m["mode_id"] for m in eligible_modes(modes, 0)], ["narrow"])
        self.assertEqual([m["mode_id"] for m in eligible_modes(modes, 1)], ["narrow", "middle"])
        self.assertEqual([m["mode_id"] for m in eligible_modes(modes, 2)], ["narrow", "middle", "wide"])


if __name__ == "__main__":
    unittest.main()
