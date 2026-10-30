import io
import unittest
from unittest.mock import Mock

from tradenet.data2g import Data2GClient, Data2GError, Mode, kiss_decode, kiss_encode


class Data2GTests(unittest.TestCase):
    def test_kiss_escapes_round_trip(self):
        raw = b"abc\xc0\xdb\x00"
        port, command, decoded = kiss_decode(kiss_encode(3, raw))
        self.assertEqual((port, command, decoded), (3, 0, raw))

    def test_rejects_invalid_kiss(self):
        with self.assertRaises(Data2GError):
            kiss_decode(b"\xc0\x00\xdb\x99\xc0")

    def test_modes_parsed_from_documented_format(self):
        mode = Mode.parse("MODE qpsk 1200 32 20 1.20 9.40")
        self.assertEqual(mode.bandwidth_hz, 1200)

    def test_probe_and_mode_gate(self):
        client = Data2GClient()
        client.command_socket = Mock()
        client.reader = io.BytesIO(b"MODE narrow 500 20 15 1.00 5.00\r\n"
                                   b"MODE wide 2400 40 20 1.00 5.00\r\nOK\r\n"
                                   b"MODE narrow 500 20 15 1.00 5.00\r\n"
                                   b"MODE wide 2400 40 20 1.00 5.00\r\nOK\r\n")
        modes = client.modes()
        self.assertEqual(len(modes), 2)
        client.group_port = 1
        with self.assertRaises(Data2GError):
            client.select_mode("wide", 0)

    def test_tx_is_denied_without_approval(self):
        client = Data2GClient()
        client.group_port = 1
        client.kiss_socket = Mock()
        with self.assertRaises(Data2GError):
            client.send_once(b"test", approved=False)
        client.kiss_socket.sendall.assert_not_called()

    def test_tx_cannot_exceed_trial_limit(self):
        client = Data2GClient()
        client.group_port = 1
        client.kiss_socket = Mock()
        with self.assertRaises(Data2GError):
            client.send_once(b"x" * 201, approved=True)
        client.kiss_socket.sendall.assert_not_called()


if __name__ == "__main__":
    unittest.main()
