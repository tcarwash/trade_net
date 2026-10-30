"""Compact Data2G advertisements never silently key a transmitter or grant credit."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tradenet import radio_exchange
from tradenet.web import App
from tests.test_radio_flow import station


class CompactBeaconTests(unittest.TestCase):
    def test_beacon_with_contract_fits_in_fifteen_bytes(self):
        contract = {"id": "AG7SU-C0012", "good": "ore", "quantity": 14, "status": "open"}
        payload = radio_exchange.encode_beacon("ag7su", "food", 499, contract)
        self.assertEqual(len(payload), 15)
        decoded = radio_exchange.decode_beacon(payload)
        self.assertEqual(decoded["callsign"], "AG7SU")
        self.assertEqual(decoded["good"], "food")
        self.assertEqual(decoded["abundance"], 255)
        self.assertEqual(decoded["contract"]["id"], contract["id"])
        self.assertEqual(decoded["contract"]["quantity"], 14)

    def test_bad_beacons_are_discarded_without_exceptions(self):
        payload = radio_exchange.encode_beacon("AG7SU", "food", 2)
        damaged = bytearray(payload)
        damaged[-2] ^= 0x1
        self.assertIsNone(radio_exchange.decode_beacon(bytes(damaged)))
        self.assertIsNone(radio_exchange.decode_beacon(b"TN"))
        self.assertIsNone(radio_exchange.decode_beacon(b"{}"))
        with self.assertRaises(ValueError):
            radio_exchange.encode_beacon("AG7SU", "food", 1, {"id": 42, "good": "ore", "quantity": 2})

    def test_passive_beacon_reception_does_not_create_contact_or_credits(self):
        receiver = station("W2BBB", 22)
        receiver.game.ship["location"] = "Kepler"
        receiver.game._bind_ship()
        before = receiver.game.credits
        payload = radio_exchange.encode_beacon("AG7SU", "ore", 33,
                    {"id": "AG7SU-C0012", "good": "food", "quantity": 4, "status": "open"})
        self.assertIsNone(receiver._handle_received_frame(payload))
        self.assertEqual(receiver.game.credits, before)
        self.assertEqual(receiver.radio_contacts, {})
        self.assertEqual(receiver.radio_beacons["AG7SU"]["abundance"], 33)
        self.assertFalse(receiver.radio_beacons["AG7SU"]["verified"])
        self.assertEqual(receiver.radio_inbox[-1]["type"], "beacon")
        self.assertIsNone(receiver._handle_received_frame(payload))
        self.assertEqual(len(receiver.radio_inbox), 1)

    def test_preview_is_local_and_broadcast_is_an_explicit_data2g_action(self):
        sender = station("AG7SU", 11)
        selected_ship = sender.game.ship
        selected_ship["location"] = "Kepler"
        sender.game._bind_ship()
        with patch("tradenet.web.Data2GClient") as modem_type:
            preview = sender.execute({"action": "radio_beacon_preview", "good": "food"})
        self.assertEqual(preview["status"], "preview")
        self.assertLessEqual(preview["bytes"], 20)
        modem_type.assert_not_called()
        sent = []
        sender._send_radio_frames = lambda modem, payload, mode, tier: sent.append((payload, mode, tier))
        mode = SimpleNamespace(mode_id="n4-quiet", bandwidth_hz=200,
                               bytes_per_codeword=32, max_codewords=1)
        with patch("tradenet.web.Data2GClient") as modem_type:
            modem_type.return_value.__enter__.return_value.modes.return_value = [mode]
            result = sender.execute({"action": "radio_beacon_transmit", "good": "food",
                                     "mode_id": "n4-quiet"})
            modem_type.return_value.__enter__.return_value.open_group.assert_called_once()
        self.assertEqual(result["status"], "sent")
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][1:], ("n4-quiet", 0))
        self.assertEqual(radio_exchange.decode_beacon(sent[0][0])["callsign"], "AG7SU")
        self.assertEqual(sender.game.ship["location"], "Kepler")


if __name__ == "__main__":
    unittest.main()
