"""Read-only Hamlib rigctld frequency monitor.

Only the single-letter get-frequency command (f) is ever sent. This module
never changes frequency, selects a VFO, keys PTT, or transmits a radio frame.
"""

from __future__ import annotations

import math
import socket

# Classification for gameplay, not a band-plan or transmit authorization.
# Actual allocations and operator privileges vary by region and license.
BAND_RANGES = (
    ("160m", 1_800_000, 2_000_000),
    ("80m", 3_500_000, 4_000_000),
    ("60m", 5_330_000, 5_410_000),
    ("40m", 7_000_000, 7_300_000),
    ("30m", 10_100_000, 10_150_000),
    ("20m", 14_000_000, 14_350_000),
    ("17m", 18_068_000, 18_168_000),
    ("15m", 21_000_000, 21_450_000),
    ("12m", 24_890_000, 24_990_000),
    ("10m", 28_000_000, 29_700_000),
    ("6m", 50_000_000, 54_000_000),
    ("2m", 144_000_000, 148_000_000),
    ("70cm", 420_000_000, 450_000_000),
)
CONTRACT_BANDS = ("20m", "40m", "15m")


def band_for_frequency(hz: int) -> str | None:
    for name, low, high in BAND_RANGES:
        if low <= hz <= high:
            return name
    return None


def read_frequency(host: str, port: int = 4532, timeout: float = 0.8) -> int:
    """Ask rigctld for its current frequency in Hz, without any rig mutations."""
    with socket.create_connection((host, port), timeout=timeout) as connection:
        connection.settimeout(timeout)
        connection.sendall(b"f\n")
        data = bytearray()
        while b"\n" not in data and len(data) < 128:
            chunk = connection.recv(128 - len(data))
            if not chunk:
                break
            data.extend(chunk)
    line = bytes(data).split(b"\n", 1)[0].strip()
    if line.startswith(b"RPRT ") or not line:
        raise ValueError("rigctld could not return a frequency")
    try:
        frequency = float(line.decode("ascii"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("invalid rigctld frequency response") from exc
    if not math.isfinite(frequency) or not 0 < frequency <= 1_000_000_000:
        raise ValueError("rigctld frequency is out of range")
    return round(frequency)
