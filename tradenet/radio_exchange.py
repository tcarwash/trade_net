"""Compact, duplicate-safe radio exchange messages and receiver-side demand."""

from __future__ import annotations

import json
import base64
import hashlib
import math
from copy import deepcopy

from .engine import Game, GOODS, RARE

MAX_FRAME_BYTES = 200
MAX_MESSAGE_BYTES = 4096
MAX_PARTS = 64


def encode(message: dict) -> bytes:
    payload = json.dumps(message, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if not 1 <= len(payload) <= MAX_FRAME_BYTES:
        raise ValueError("radio message exceeds the 200-byte frame limit")
    return payload


def encode_message(message: dict) -> bytes:
    """Encode one complete application message before radio fragmentation."""
    payload = json.dumps(message, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if not 1 <= len(payload) <= MAX_MESSAGE_BYTES:
        raise ValueError("radio message exceeds the 4096-byte application limit")
    return payload


def frames(payload: bytes) -> list[bytes]:
    """Split a complete message into independently bounded Data2G frames."""
    if not 1 <= len(payload) <= MAX_MESSAGE_BYTES:
        raise ValueError("radio message size is invalid")
    if len(payload) <= MAX_FRAME_BYTES:
        return [payload]
    message = decode(payload)
    if not message or not all(isinstance(message.get(key), str)
                              for key in ("i", "f", "d")):
        raise ValueError("multipart message needs an id and station addresses")
    digest = hashlib.sha256(payload).hexdigest()[:16]
    for chunk_size in range(120, 15, -1):
        count = math.ceil(len(payload) / chunk_size)
        if count > MAX_PARTS:
            continue
        result = []
        try:
            for index in range(count):
                chunk = payload[index * chunk_size:(index + 1) * chunk_size]
                result.append(encode({"v": 1, "t": "part", "f": message["f"],
                    "d": message["d"], "i": message["i"], "k": index,
                    "m": count, "h": digest,
                    "b": base64.b64encode(chunk).decode("ascii")}))
        except ValueError:
            continue
        return result
    raise ValueError("station addresses leave no room for multipart data")


def decode(payload: bytes) -> dict | None:
    if not 1 <= len(payload) <= MAX_MESSAGE_BYTES:
        return None
    try:
        message = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    return message if isinstance(message, dict) and message.get("v") == 1 else None


def profile(game: Game) -> dict:
    haven = game.ports["Haven"]
    producer = game.ports["Kepler"]
    return {"richness": game.specialization,
            "stock": [haven["stock"][good] for good in RARE],
            "production": [producer["production"][good] for good in RARE]}


def generate_contracts(game: Game, station: str, serial: int = 1,
                       existing: list[dict] | None = None, count: int = 3):
    """Generate hub demand from local inventories and replenishment rates."""
    contracts = deepcopy(existing or [])
    for item in contracts:
        suffix = item.get("id", "").rsplit("C", 1)[-1]
        if suffix.isdigit():
            serial = max(serial, int(suffix) + 1)
    occupied = {(item.get("good"), item.get("status", "open"))
                for item in contracts if item.get("status", "open") == "open"}
    while sum(item.get("status", "open") == "open" for item in contracts) < count:
        candidates = []
        for good in GOODS:
            if (good, "open") in occupied:
                continue
            stock = game.ports["Haven"]["stock"][good]
            target = 8 if good in RARE else 24
            shortage = max(0, target - stock)
            if shortage:
                candidates.append((shortage / target, shortage, good))
        if not candidates:
            candidates = [(1 - game.ports["Haven"]["stock"][good] / 300,
                           1, good) for good in GOODS if (good, "open") not in occupied]
        if not candidates:
            break
        _, shortage, good = max(candidates)
        quantity = min(5 if good in RARE else 10, max(1, shortage))
        contract_id = f"{station}-C{serial:04d}"
        serial += 1
        contracts.append({"id": contract_id, "issuer": station, "good": good,
                          "quantity": quantity, "status": "open"})
        occupied.add((good, "open"))
    return contracts, serial


def wire_contracts(contracts: list[dict], limit=3):
    return [[item["id"], item["good"], item["quantity"]]
            for item in contracts if item.get("status", "open") == "open"][:limit]


def read_contracts(items, issuer: str):
    result = []
    if not isinstance(items, list):
        return result
    for item in items[:8]:
        if (not isinstance(item, list) or len(item) != 3 or
                not isinstance(item[0], str) or not 1 <= len(item[0]) <= 32 or
                item[1] not in GOODS or type(item[2]) is not int or not 1 <= item[2] <= 10000):
            continue
        result.append({"id": item[0], "issuer": issuer, "good": item[1],
                       "quantity": item[2], "status": "open"})
    return result
