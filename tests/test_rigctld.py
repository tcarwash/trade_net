"""Rig telemetry stays read-only, and band rewards are bounded."""

import unittest
from unittest.mock import patch

from tradenet import rigctld
from tradenet.engine import GameError
from tests.test_radio_flow import station


class RigTests(unittest.TestCase):
    def test_read_frequency_issues_only_read_command(self):
        commands = []

        class Rig:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def settimeout(self, timeout):
                self.timeout = timeout

            def sendall(self, data):
                commands.append(data)

            def recv(self, count):
                return b"14074000\n"

        with patch("tradenet.rigctld.socket.create_connection", return_value=Rig()):
            self.assertEqual(rigctld.read_frequency("127.0.0.1", 4532), 14074000)
        self.assertEqual(commands, [b"f\n"])
        self.assertEqual(rigctld.band_for_frequency(14074000), "20m")
        self.assertIsNone(rigctld.band_for_frequency(12345678))

    def test_band_sightings_reward_once_and_save(self):
        app = station("W1AAA", 4)
        old = app.game.credits
        app._record_rig_frequency(14074000)
        app._record_rig_frequency(14100000)
        self.assertEqual(app.game.radio_bands_seen, ["20m"])
        self.assertEqual(app.game.credits, old + 60)
        self.assertEqual(app.rig_status["band"], "20m")
        app._record_rig_frequency(7074000)
        self.assertEqual(app.game.radio_bands_seen, ["20m", "40m"])
        self.assertEqual(app.game.credits, old + 120)
        self.assertEqual(sum(x["action"] == "discover_radio_band"
                             for x in app.game.journal), 2)

    def test_band_contract_refuses_to_send_until_rig_matches(self):
        app = station("W1AAA", 4)
        app.rigctld = ("127.0.0.1", 4532)
        app.radio_contacts["W2BBB"] = 1
        app.radio_contracts["W2BBB"] = [{
            "id": "W2BBB-C0003", "issuer": "W2BBB", "good": "ore",
            "quantity": 2, "band": "20m", "status": "open"}]
        app.game.export_warehouse["ore"] = 2
        app.execute({"action": "exchange_reserve", "station": "W2BBB",
                     "contract_id": "W2BBB-C0003"})
        request = {"action": "radio_transmit", "purpose": "delivery",
                   "station": "W2BBB", "contract_id": "W2BBB-C0003",
                   "mode_id": "sample-mode"}
        with patch("tradenet.web.rigctld.read_frequency", return_value=7074000):
            with self.assertRaisesRegex(GameError, "requires 20m"):
                app.execute(request)
        self.assertEqual(app.radio_transmissions, {})
        self.assertIn("W2BBB-C0003", app.radio_reservations)
        with patch("tradenet.web.rigctld.read_frequency", return_value=14074000):
            app._verify_contract_band("20m")
        with (patch("tradenet.web.rigctld.read_frequency", return_value=7074000),
              patch("tradenet.web.Data2GClient") as modem):
            with self.assertRaisesRegex(GameError, "requires 20m"):
                app._send_recovery_payload(b"test", required_band="20m")
            modem.assert_not_called()


if __name__ == "__main__":
    unittest.main()
