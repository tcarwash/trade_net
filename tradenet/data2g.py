"""Conservative Data2G TCP/KISS adapter for operator-run on-air trials.

Probe/listen are receive-only. Transmission requires an explicit interactive
confirmation every invocation. This is not an unattended radio scheduler.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import socket
from dataclasses import dataclass
from pathlib import Path

from .modems import eligible_modes

FEND, FESC, TFEND, TFESC = 0xC0, 0xDB, 0xDC, 0xDD


class Data2GError(ValueError):
    pass


def kiss_encode(port: int, payload: bytes, command: int = 0) -> bytes:
    if not 0 <= port <= 15 or command not in (0, 12):
        raise Data2GError("invalid KISS port/command")
    body = bytes([(port << 4) | command]) + payload
    return bytes([FEND]) + body.replace(bytes([FESC]), bytes([FESC, TFESC])).replace(
        bytes([FEND]), bytes([FESC, TFEND])) + bytes([FEND])


def kiss_decode(data: bytes) -> tuple[int, int, bytes]:
    if len(data) < 3 or data[0] != FEND or data[-1] != FEND:
        raise Data2GError("invalid KISS frame")
    out = bytearray()
    body = data[1:-1]
    i = 0
    while i < len(body):
        value = body[i]
        if value == FESC:
            i += 1
            if i >= len(body) or body[i] not in (TFEND, TFESC):
                raise Data2GError("invalid KISS escape")
            value = FEND if body[i] == TFEND else FESC
        elif value == FEND:
            raise Data2GError("unescaped KISS delimiter")
        out.append(value)
        i += 1
    if not out:
        raise Data2GError("empty KISS frame")
    return out[0] >> 4, out[0] & 15, bytes(out[1:])


@dataclass(frozen=True)
class Mode:
    mode_id: str
    bandwidth_hz: int
    bytes_per_codeword: int
    max_codewords: int
    seconds_min: float
    seconds_max: float

    @classmethod
    def parse(cls, line: str):
        words = line.split()
        if len(words) != 7 or words[0] != "MODE":
            raise Data2GError("invalid MODES response")
        try:
            mode = cls(words[1], int(words[2]), int(words[3]), int(words[4]),
                       float(words[5]), float(words[6]))
        except ValueError as exc:
            raise Data2GError("invalid numeric mode fields") from exc
        if mode.bandwidth_hz <= 0 or mode.bytes_per_codeword <= 0 or mode.max_codewords <= 0:
            raise Data2GError("invalid mode capacity")
        return mode


class Data2GClient:
    def __init__(self, host="127.0.0.1", command_port=8300, kiss_port=8100, timeout=5):
        self.host, self.command_port, self.kiss_port = host, command_port, kiss_port
        self.timeout = timeout
        self.command_socket = self.kiss_socket = self.reader = None
        self.group_port = None

    def __enter__(self):
        self.command_socket = socket.create_connection((self.host, self.command_port), self.timeout)
        self.command_socket.settimeout(self.timeout)
        self.reader = self.command_socket.makefile("rb")
        self.kiss_socket = socket.create_connection((self.host, self.kiss_port), self.timeout)
        self.kiss_socket.settimeout(self.timeout)
        return self

    def __exit__(self, *_):
        if self.reader:
            self.reader.close()
        for sock in (self.command_socket, self.kiss_socket):
            if sock:
                sock.close()

    def command(self, value: str) -> list[str]:
        if not self.command_socket or not self.reader or "\r" in value or "\n" in value:
            raise Data2GError("invalid command connection")
        self.command_socket.sendall((value + "\r").encode("ascii"))
        result = []
        for _ in range(512):
            line = self.reader.readline()
            if not line:
                raise Data2GError("Data2G command port closed")
            item = line.decode("ascii", errors="replace").strip()
            if item == "OK":
                return result
            if item == "WRONG":
                raise Data2GError(f"Data2G rejected {value.split()[0]}")
            result.append(item)
            # BCAST OPEN returns its port rather than an OK on some hosts.
            if value.startswith("BCAST OPEN ") and item.startswith("BCAST PORT "):
                return result
        raise Data2GError("Data2G command response exceeded limit")

    def modes(self):
        return [Mode.parse(line) for line in self.command("MODES") if line.startswith("MODE ")]

    def open_group(self, group="TRADENET", callsign="AG7SU"):
        if not (group.isascii() and group.isalnum() and 1 <= len(group) <= 10):
            raise Data2GError("invalid group name")
        if not callsign or len(callsign) > 10 or not all(c.isalnum() or c in "-/" for c in callsign):
            raise Data2GError("invalid callsign")
        lines = self.command(f"BCAST OPEN {group} FROM {callsign}")
        port_lines = [s for s in lines if s.startswith("BCAST PORT ")]
        if len(port_lines) != 1:
            raise Data2GError("BCAST OPEN did not provide a port")
        self.group_port = int(port_lines[0].split()[-1])
        if not 1 <= self.group_port <= 15:
            raise Data2GError("invalid group port")
        return self.group_port

    def select_mode(self, mode_id: str, ship_tier: int):
        if self.group_port is None:
            raise Data2GError("open the group first")
        available = [vars(m) for m in self.modes()]
        if mode_id not in {m["mode_id"] for m in eligible_modes(available, ship_tier)}:
            raise Data2GError("mode unavailable or exceeds ship bandwidth ceiling")
        self.command(f"BCAST MODE {self.group_port} {mode_id}")

    def receive(self) -> tuple[int, int, bytes]:
        """Read one checked KISS frame. Does not transmit."""
        if not self.kiss_socket:
            raise Data2GError("KISS port not connected")
        in_frame = False
        buffer = bytearray()
        while True:
            chunk = self.kiss_socket.recv(1)
            if not chunk:
                raise Data2GError("KISS port closed")
            value = chunk[0]
            if value == FEND:
                if in_frame and buffer:
                    return kiss_decode(bytes([FEND]) + buffer + bytes([FEND]))
                in_frame = True
                buffer.clear()
            elif in_frame:
                buffer.append(value)
                if len(buffer) > 65536:
                    raise Data2GError("oversized KISS frame")

    def send_once(self, payload: bytes, approved: bool):
        """One KISS frame; approval must come from the interactive CLI."""
        if not approved or self.group_port is None or not self.kiss_socket:
            raise Data2GError("transmission not authorized")
        if not 1 <= len(payload) <= 200:
            raise Data2GError("on-air trial limited to 1..200 payload bytes")
        self.kiss_socket.sendall(kiss_encode(self.group_port, payload))


def main():
    parser = argparse.ArgumentParser(description="Trade Net Data2G on-air test harness")
    parser.add_argument("action", choices=("probe", "listen", "send"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--command-port", type=int, default=8300)
    parser.add_argument("--kiss-port", type=int, default=8100)
    parser.add_argument("--callsign", default="AG7SU")
    parser.add_argument("--group", default="TRADENET")
    parser.add_argument("--ship-tier", type=int, default=0, choices=(0, 1, 2))
    parser.add_argument("--mode", help="exact Data2G advertised mode ID for transmission")
    parser.add_argument("--file", type=Path, help="UTF-8/opaque payload for send action")
    parser.add_argument("--enable-transmit", action="store_true")
    args = parser.parse_args()

    if args.action == "send":
        if not args.enable_transmit or not args.mode or not args.file:
            parser.error("send requires --enable-transmit, --mode, and --file")
        payload = args.file.read_bytes()
        if not 1 <= len(payload) <= 200:
            parser.error("test payload must be 1..200 bytes; no padding or automatic fragmentation")
        digest = hashlib.sha256(payload).hexdigest()[:12]
        print(f"REAL RF TRANSMISSION: {len(payload)} bytes, SHA256 {digest}, group {args.group}")
        confirmation = input(f"Type 'TX {len(payload)} {digest}' to authorize this one frame: ")
        if confirmation != f"TX {len(payload)} {digest}":
            raise SystemExit("Transmission cancelled")
    with Data2GClient(args.host, args.command_port, args.kiss_port) as modem:
        modes = modem.modes()
        if args.action == "probe":
            print(json.dumps([vars(m) for m in modes], indent=2))
            return
        port = modem.open_group(args.group, args.callsign)
        print(f"Group {args.group} opened on KISS port {port}")
        if args.action == "send":
            modem.select_mode(args.mode, args.ship_tier)
            modem.send_once(payload, approved=True)
            print("Frame queued to Data2G; this is NOT a receiver acknowledgment")
            return
        print("Receive-only: Ctrl-C to stop. No application transmissions are scheduled.")
        try:
            while True:
                port, command, payload = modem.receive()
                if port == modem.group_port and command == 0:
                    print(f"RX {len(payload)} B sha256={hashlib.sha256(payload).hexdigest()[:12]} hex={payload.hex()}")
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
