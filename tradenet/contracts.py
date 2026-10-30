"""Simulated NPC contracts and custody-safe store-and-forward dispatch.

This prototype settles against the player's own local authority. It does not
claim cross-galaxy atomic settlement or verified RF delivery.
"""

from __future__ import annotations

import json
import math
import random

from .engine import BASE_PRICE, Game, GameError, RARE
from .network import Network


NPC_DESTINATIONS = ("SIM-K7OR", "SIM-W7ABC", "SIM-N0XYZ")


def seed_offers(game: Game) -> None:
    """Stable demand-driven offers; existing contracts never regenerate."""
    if game.contracts:
        return
    rng = random.Random(game.seed ^ 0xD1A1)
    goods = (game.specialization, "food", "medicine", "ore", "fuel")
    for i, good in enumerate(goods):
        qty = 2 + rng.randrange(3) if good in RARE else 4 + rng.randrange(7)
        # Reward covers the purchase cost plus a premium for successful
        # delivery, with larger rare-goods contracts paying more.
        reward = qty * BASE_PRICE[good] * (175 if good in RARE else 145) // 100
        cid = f"NPC-{game.seed}-{i+1}"
        game.contracts[cid] = {"id": cid, "issuer": "NPC authority",
                               "destination": NPC_DESTINATIONS[i % len(NPC_DESTINATIONS)],
                               "good": good, "quantity": qty, "reward": reward,
                               "deadline": game.tick + 100 + i * 15,
                               "status": "offered", "custody": None,
                               "route": [], "hop_index": 0, "attempts": 0,
                               "origin_id": None,
                               "delivery_id": None, "settled": False,
                               "payload_bytes": 0}
        game.contracts[cid]["payload_bytes"] = len(manifest_payload(game.contracts[cid]))


def manifest_payload(contract: dict) -> bytes:
    return json.dumps({"contract": contract["id"], "good": contract["good"],
                       "quantity": contract["quantity"], "destination": contract["destination"]},
                      separators=(",", ":")).encode()


def dispatch(game: Game, net: Network, contract_id: str, route: list[str] | None = None,
             loss: float = .15) -> dict:
    """Advance one custody hop with explicit retry on failure.

    A parcel remains with the current custodian after a failed hop. Destination
    receipt, acceptance and local ledger settlement happen once, not once per
    frame or retry. No resource is minted by retransmission.
    """
    c = game.contracts.get(contract_id)
    if not c or c["status"] not in ("reserved", "in_transit"):
        raise GameError("contract is not reserved or in transit")
    if game.tick > c["deadline"]:
        # Keep escrow intact for explicit expiry/return handling.
        c["status"] = "expired"
        return {"contract_id": contract_id, "status": "expired", "custody": c["custody"]}
    if c["status"] == "reserved":
        if route is None:
            route = [net.local_id, c["destination"]]
        if (not isinstance(route, list) or len(route) < 2 or len(route) > 6 or
                route[0] != net.local_id or route[-1] != c["destination"] or
                len(route) != len(set(route)) or
                any(not isinstance(p, str) or not 1 <= len(p) <= 32 for p in route)):
            raise GameError("route must start locally and end at contract destination")
        c["route"] = route[:]
        c["origin_id"] = net.local_id
        c["hop_index"] = 0
        c["custody"] = route[0]
        c["status"] = "in_transit"
    src = c["route"][c["hop_index"]]
    dst = c["route"][c["hop_index"] + 1]
    # The same deterministic simulator is used for all hops. Intermediate hop
    # observations are NOT a direct local RF contact or discovery event.
    # Measure the compact manifest's actual bytes, not an invented mission size.
    manifest = manifest_payload(c)
    result = simulate_hop(net, src, dst, len(manifest), loss)
    c["attempts"] += 1
    # Simulation airtime advances the economy and may exhaust a deadline.
    game._wait(ticks=min(100, max(1, math.ceil(result["elapsed_seconds"] / 60))))
    if result["delivered"]:
        c["hop_index"] += 1
        c["custody"] = dst
        if dst == c["destination"]:
            c["delivery_id"] = f"{contract_id}:{dst}:delivered"
            if game.tick > c["deadline"]:
                c["status"] = "expired"
            else:
                c["status"] = "settled"
                c["settled"] = True
                game.credits += c["reward"]
        else:
            c["status"] = "in_transit"
    if game.tick > c["deadline"] and not c["settled"]:
        c["status"] = "expired"
    return {"contract_id": contract_id, "status": c["status"],
            "custody": c["custody"], "hop": f"{src}->{dst}",
            "attempt": c["attempts"], "delivered": result["delivered"],
            "frames_lost": result["lost_frames"],
            "frames_attempted": result["frames"],
            "remaining_hops": len(c["route"]) - 1 - c["hop_index"],
            "payout": c["reward"] if c["settled"] else 0}


def simulate_hop(net: Network, src: str, dst: str, payload_bytes: int,
                 loss: float) -> dict:
    """A bounded simulated transfer from any custodian to its next hop."""
    if not 0 <= loss <= 1:
        raise ValueError("loss must be between 0 and 1")
    import hashlib
    frame_size = 64
    frame_count = (payload_bytes + frame_size - 1) // frame_size
    remaining = set(range(frame_count))
    attempted = lost = 0
    seed = int.from_bytes(hashlib.sha256(
        f"{src}:{dst}:{net.sequence}:{payload_bytes}:{loss}".encode()).digest()[:8], "big")
    rng = random.Random(seed)
    for _ in range(4):
        for index in sorted(remaining):
            attempted += 1
            if rng.random() < loss:
                lost += 1
            else:
                remaining.remove(index)
        if not remaining:
            break
    elapsed = attempted * (64 * 8 / 150 + .25) + 2
    succeeded = not remaining
    record = net.record(src, dst, payload_bytes, elapsed, succeeded, attempted, lost)
    if succeeded and src == net.local_id:
        net.discover(dst)
    return record
