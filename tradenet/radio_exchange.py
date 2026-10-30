"""Compact, duplicate-safe radio exchange messages and receiver-side demand."""

from __future__ import annotations

import json
import base64
import hashlib
import math
from copy import deepcopy

from .engine import Game, GOODS, RARE
from .rigctld import CONTRACT_BANDS

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
        number = serial
        serial += 1
        contract = {"id": contract_id, "issuer": station, "good": good,
                    "quantity": quantity, "status": "open"}
        # Three rotating offers: simple, a larger two-resource long haul, and
        # a band-specific run. Long-haul inventory can accumulate over days.
        if number % 3 == 2:
            other = next(g for g in GOODS if g != good and g not in RARE)
            contract["quantity"] = min(20, max(quantity + 4, 8))
            contract["requirements"] = {
                good: contract["quantity"], other: 4 + number % 4}
            contract["kind"] = "longhaul"
        elif number % 3 == 0:
            contract["band"] = CONTRACT_BANDS[(number // 3 - 1) % len(CONTRACT_BANDS)]
        contracts.append(contract)
        occupied.add((good, "open"))
    return contracts, serial


def wire_contracts(contracts: list[dict], limit=3):
    return [[item["id"], item["good"], item["quantity"]] +
            ([item.get("band", "")] if item.get("requirements") else
             [item["band"]] if item.get("band") in CONTRACT_BANDS else []) +
            ([[[good, amount] for good, amount in item["requirements"].items()]]
             if item.get("requirements") else [])
            for item in contracts if item.get("status", "open") == "open"][:limit]


def read_contracts(items, issuer: str):
    result = []
    if not isinstance(items, list):
        return result
    for item in items[:8]:
        if (not isinstance(item, list) or len(item) not in (3, 4, 5) or
                not isinstance(item[0], str) or not 1 <= len(item[0]) <= 32 or
                item[1] not in GOODS or type(item[2]) is not int or not 1 <= item[2] <= 10000 or
                (len(item) >= 4 and item[3] not in (*CONTRACT_BANDS, ""))):
            continue
        contract = {"id": item[0], "issuer": issuer, "good": item[1],
                    "quantity": item[2], "status": "open"}
        if len(item) >= 4 and item[3]:
            contract["band"] = item[3]
        if len(item) == 5:
            terms = item[4]
            if (not isinstance(terms, list) or not 2 <= len(terms) <= 4 or
                    any(not isinstance(term, list) or len(term) != 2 or
                        term[0] not in GOODS or type(term[1]) is not int or
                        not 1 <= term[1] <= 100 for term in terms)):
                continue
            requirements = dict(terms)
            if (len(requirements) != len(terms) or
                    requirements.get(item[1]) != item[2]):
                continue
            contract["requirements"] = requirements
            contract["kind"] = "longhaul"
        result.append(contract)
    return result


def contract_requirements(contract: dict) -> dict[str, int]:
    """Normalize legacy single-commodity and long-haul freight manifests."""
    return contract.get("requirements") or {contract["good"]: contract["quantity"]}
