import io
import socket
import threading
import unittest
from contextlib import contextmanager
from unittest.mock import Mock

from tradenet.data2g import Data2GClient, Data2GError, Mode, kiss_decode, kiss_encode


@contextmanager
def command_host(chunks):
    """Real TCP host: only MODES is accepted; no RF-facing commands exist."""
    commands, errors = [], []
    stop = threading.Event()
    with socket.socket() as command, socket.socket() as kiss:
        for listener in (command, kiss):
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            listener.settimeout(2)

        def serve():
            try:
                with command.accept()[0] as connection, kiss.accept()[0] as data:
                    connection.settimeout(2)
                    stream = connection.makefile("rb")
                    with stream:
                        while not stop.is_set():
                            request = bytearray()
                            while not request.endswith(b"\r"):
                                byte = stream.read(1)
                                if not byte:
                                    return
                                request.extend(byte)
                            commands.append(bytes(request))
                            if request != b"MODES\r":
                                raise AssertionError(f"unexpected command: {request!r}")
                            for chunk in chunks:
                                connection.sendall(chunk)
                            # Keep the socket open: CR-only must not need EOF.
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as exc:
                errors.append(exc)

        worker = threading.Thread(target=serve, daemon=True)
        worker.start()
        try:
            yield command.getsockname()[1], kiss.getsockname()[1], commands
        finally:
            stop.set()
            worker.join(3)
            if worker.is_alive():
                raise AssertionError("fixture thread did not stop")
            if errors:
                raise errors[0]


class Data2GTests(unittest.TestCase):
    def test_modes_over_real_socket_accept_fragmented_line_endings(self):
        for ending in (b"\r", b"\n", b"\r\n"):
            with self.subTest(ending=ending):
                response = b"MODE n4 200 12 8 1.00 4.00" + ending + b"OK" + ending
                chunks = [response[i:i + 1] for i in range(len(response))]
                with command_host(chunks) as (port, kiss_port, commands):
                    with Data2GClient(command_port=port, kiss_port=kiss_port, timeout=.3) as client:
                        for _ in range(2):
                            self.assertEqual(client.modes(), [Mode("n4", 200, 12, 8, 1., 4.)])
                    self.assertEqual(commands, [b"MODES\r", b"MODES\r"])

    def test_command_response_limits(self):
        for response in (b"x" * 4097 + b"\rOK\r", b"\r" * 65537 + b"OK\r",
                         b"NOTICE\r" * 512 + b"OK\r"):
            with self.subTest(size=len(response)):
                client = Data2GClient()
                client.command_socket = Mock()
                client.reader = io.BytesIO(response)
                with self.assertRaisesRegex(Data2GError, "exceeded limit"):
                    client.command("MODES")

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
