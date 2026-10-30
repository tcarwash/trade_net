import unittest

from tradenet import modems
from tradenet.modems import eligible_modes


class ModemTests(unittest.TestCase):
    def test_buyable_ship_catalog_preserves_tiers(self):
        self.assertIsInstance(modems.SHIPS, tuple)
        self.assertEqual([(s['id'], s['tier'], s['cost'], s['max_bandwidth_hz'],
                           s['frames_per_tick'], s['speed'], s['capacity']) for s in modems.SHIPS],
                         [('wisp200', 0, 200, 200, 1, 1, 16),
                          ('scout500', 0, 350, 500, 2, 1, 30),
                          ('courier1200', 1, 900, 1200, 6, 2, 40),
                          ('hauler2300', 2, 1400, 2300, 10, 2, 60),
                          ('express2400', 2, 1800, 2400, 16, 3, 30)])
        for ship in modems.SHIPS:
            self.assertTrue(ship['name'])
            self.assertTrue(ship['description'])
            self.assertEqual(ship['sprite'], ship['id'].rstrip('0123456789'))
        self.assertEqual(modems.TIERS, (
            {'name': 'Scout', 'max_bandwidth_hz': 500, 'frames_per_tick': 2, 'upgrade_cost': 0},
            {'name': 'Courier', 'max_bandwidth_hz': 1200, 'frames_per_tick': 6, 'upgrade_cost': 500},
            {'name': 'Express', 'max_bandwidth_hz': 2400, 'frames_per_tick': 16, 'upgrade_cost': 1200},
        ))

    def test_ship_modes_use_class_ceiling_family_and_exclude_control(self):
        advertised = [
            {'mode_id': 'n4-qpsk-r1/2', 'bandwidth_hz': 200},
            {'mode_id': 'other200', 'bandwidth_hz': 200},
            {'mode_id': 'n40-not-n4', 'bandwidth_hz': 200},
            {'mode_id': 'n4-ACK-2f', 'bandwidth_hz': 200},
            {'mode_id': 'fsk8r50-r1/2', 'bandwidth_hz': 500},
            {'mode_id': 'n10-qpsk-r1/2', 'bandwidth_hz': 500},
            {'mode_id': 'qpsk-r1/2', 'bandwidth_hz': 1200},
            {'mode_id': 'fsk32r62-r1/2', 'bandwidth_hz': 2300},
            {'mode_id': 'nonfsk', 'bandwidth_hz': 2300},
            {'mode_id': 'w48-qpsk-r1/2', 'bandwidth_hz': 2400},
            {'mode_id': 'fsk-too-wide', 'bandwidth_hz': 2400},
            {'mode_id': 'too-wide', 'bandwidth_hz': 2500},
            {'mode_id': '', 'bandwidth_hz': 200},
            {'mode_id': None, 'bandwidth_hz': 200},
            {'mode_id': 'bad', 'bandwidth_hz': None},
            {'mode_id': 'boolean', 'bandwidth_hz': True},
            {'mode_id': 'zero', 'bandwidth_hz': 0},
        ]
        expected = {
            'wisp200': [0], 'scout500': [0, 1, 2, 4, 5], 'courier1200': [0, 1, 2, 4, 5, 6],
            'hauler2300': [4, 7], 'express2400': [0, 1, 2, 4, 5, 6, 7, 8, 9, 10],
        }
        for class_id, indices in expected.items():
            with self.subTest(class_id=class_id):
                self.assertEqual(modems.eligible_ship_modes(advertised, class_id),
                                 [advertised[i] for i in indices])
        for invalid in ('wayfarer', 'Wisp', 'unknown', '', None, 0, []):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, 'invalid ship class'):
                    modems.eligible_ship_modes(advertised, invalid)

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
