"""Compact useful-data bundling; no padding, filler or artificial traffic."""

from __future__ import annotations

from dataclasses import dataclass


TYPES = {"trade": 1, "market": 2, "neighbors": 3, "custody": 4,
         "fragment_request": 5, "status": 6}
REVERSE = {value: name for name, value in TYPES.items()}
MAGIC = b"TN1"


@dataclass(frozen=True)
class Item:
    kind: str
    data: bytes


def encode(items: list[Item], max_bytes: int = 65536) -> bytes:
    """Each item must be an actual application datum, independently useful.

    One-byte type and two-byte length per item; no synthetic bytes. If even one
    item would exceed the explicitly authorized budget, reject the bundle.
    """
    if not items or len(items) > 32 or not 1 <= max_bytes <= 65536:
        raise ValueError("invalid bundle limits")
    out = bytearray(MAGIC)
    for item in items:
        if item.kind not in TYPES or not isinstance(item.data, bytes) or not 1 <= len(item.data) <= 65530:
            raise ValueError("invalid useful payload item")
        out.append(TYPES[item.kind])
        out.extend(len(item.data).to_bytes(2, "big"))
        out.extend(item.data)
        if len(out) > max_bytes:
            raise ValueError("bundle exceeds authorized byte budget")
    return bytes(out)


def decode(blob: bytes) -> list[Item]:
    if not blob.startswith(MAGIC):
        raise ValueError("not a Trade Net bundle")
    cursor, items = len(MAGIC), []
    while cursor < len(blob):
        if cursor + 3 > len(blob):
            raise ValueError("truncated item")
        kind = REVERSE.get(blob[cursor])
        size = int.from_bytes(blob[cursor + 1:cursor + 3], "big")
        cursor += 3
        if not kind or size < 1 or cursor + size > len(blob):
            raise ValueError("invalid item framing")
        items.append(Item(kind, blob[cursor:cursor + size]))
        cursor += size
        if len(items) > 32:
            raise ValueError("too many items")
    if not items:
        raise ValueError("empty bundle")
    return items
