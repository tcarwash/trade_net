"""Two-galaxy simulated commerce with durable, duplicate-safe settlement.

This module is deliberately a *single-process simulation coordinator*. It is
not yet a distributed atomic-commit protocol and cannot prove RF carriage.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from .contracts import simulate_hop
from .engine import Game, GameError, RARE
from .network import Network
from .mail import MailNetwork
from .modems import TIERS


def canonical_hash(value: dict) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


@dataclass
class Federation:
    worlds: dict[str, Game]
    network: Network
    trades: dict = field(default_factory=dict)
    events: list = field(default_factory=list)
    schema_version: int = 1

    @classmethod
    def demo(cls, local_id="AG7SU", remote_id="SIM-K7OR", seed=42):
        if not local_id or not remote_id or local_id == remote_id:
            raise GameError("distinct galaxy IDs required")
        a = Game.new(seed, local_id + " Galaxy")
        b_seed = seed + 1
        b = Game.new(b_seed, remote_id + " Galaxy")
        while b.specialization == a.specialization:
            b_seed += 1
            b = Game.new(b_seed, remote_id + " Galaxy")
        # Demo starting stock is transferred from the local Kepler producer to
        # the player's ship. Never silently duplicate world resources.
        source = a.ports["Kepler"]["stock"]
        source[a.specialization] -= 6
        a.cargo[a.specialization] += 6
        return cls({local_id: a, remote_id: b}, Network(local_id))

    def propose(self, trade_id: str, seller: str, buyer: str, good: str,
                quantity: int, unit_price: int, deadline: int = 100,
                payload_bytes: int = 0):
        terms = {"id": trade_id, "seller": seller, "buyer": buyer,
                 "good": good, "quantity": quantity, "unit_price": unit_price,
                 "deadline": deadline, "payload_bytes": payload_bytes}
        if trade_id in self.trades:
            old = self.trades[trade_id]
            if any(old[k] != value for k, value in terms.items()):
                raise GameError("trade ID reused with different terms")
            return old
        if (not trade_id or len(trade_id) > 128 or seller == buyer or
                seller not in self.worlds or buyer not in self.worlds or
                good not in RARE or type(quantity) is not int or quantity <= 0 or
                type(unit_price) is not int or unit_price <= 0 or
                not 0 <= payload_bytes <= 65536 or deadline <= 0):
            raise GameError("invalid bilateral trade terms")
        trade = {**terms, "hash": canonical_hash(terms), "status": "offered",
                 "route": [], "hop_index": 0, "custody": None,
                 "attempts": 0, "receipt": None, "settlement": None}
        self.trades[trade_id] = trade
        self.events.append({"trade": trade_id, "event": "offered"})
        return trade

    def reserve(self, trade_id: str):
        t = self._trade(trade_id)
        if t["status"] == "reserved":
            return t
        if t["status"] != "offered":
            raise GameError("trade cannot be reserved")
        seller, buyer = self.worlds[t["seller"]], self.worlds[t["buyer"]]
        due = t["quantity"] * t["unit_price"]
        if seller.cargo[t["good"]] < t["quantity"]:
            raise GameError("seller cargo is insufficient")
        if buyer.credits < due:
            raise GameError("buyer credit balance is insufficient")
        if buyer.cargo_used() + buyer.incoming_reserved + t["quantity"] > buyer.ship["capacity"]:
            raise GameError("buyer cargo hold lacks capacity")
        seller.cargo[t["good"]] -= t["quantity"]
        buyer.credits -= due
        buyer.incoming_reserved += t["quantity"]
        t["status"] = "reserved"
        t["custody"] = t["seller"]
        self.events.append({"trade": trade_id, "event": "reserved", "escrow_credits": due})
        return t

    def dispatch(self, trade_id: str, loss=.15, route=None):
        t = self._trade(trade_id)
        if t["status"] not in ("reserved", "in_transit"):
            raise GameError("trade cannot be dispatched")
        if t["status"] == "reserved":
            route = route or [t["seller"], t["buyer"]]
            if (not isinstance(route, list) or not 2 <= len(route) <= 6 or
                    route[0] != t["seller"] or route[-1] != t["buyer"] or
                    len(route) != len(set(route)) or
                    any(not isinstance(p, str) or not 1 <= len(p) <= 32 for p in route)):
                raise GameError("invalid custody route")
            t["route"] = route[:]
            t["hop_index"] = 0
            t["status"] = "in_transit"
        src, dst = t["route"][t["hop_index"]:t["hop_index"] + 2]
        payload_length = len(self.trade_payload(t))
        observation = simulate_hop(self.network, src, dst, payload_length, float(loss))
        t["attempts"] += 1
        if observation["delivered"]:
            t["hop_index"] += 1
            t["custody"] = dst
            if dst == t["buyer"]:
                # Receipt binds canonical terms; it is not a cryptographic
                # signature or evidence that RF was used.
                t["receipt"] = {"trade_id": trade_id, "terms_hash": t["hash"],
                                "receiver": dst, "accepted": True,
                                "receipt_id": canonical_hash({"trade": trade_id, "hash": t["hash"], "to": dst})}
                t["status"] = "delivered"
        event = {"trade": trade_id, "event": "hop", "from": src,
                 "to": dst, "delivered": observation["delivered"],
                 "frames": observation["frames"], "lost": observation["lost_frames"],
                 "custody": t["custody"]}
        self.events.append(event)
        return event

    def queue_trade(self, mail: MailNetwork, trade_id: str, route=None):
        """Queue terms for asynchronous, receipt-confirmed delivery."""
        t = self._trade(trade_id)
        if t["status"] == "queued":
            return mail.messages["trade:" + trade_id]
        if t["status"] != "reserved":
            raise GameError("reserve the trade before queueing")
        route = route or [t["seller"], t["buyer"]]
        if (not isinstance(route, list) or not 2 <= len(route) <= 8 or
                route[0] != t["seller"] or route[-1] != t["buyer"] or
                len(route) != len(set(route))):
            raise GameError("invalid store-and-forward route")
        for station in route:
            mail.add_station(station)
        payload = self.trade_payload(t)
        tier = TIERS[self.worlds[t["seller"]].ship.get("modem_tier", 0)]
        msg = mail.enqueue("trade:" + trade_id, route, payload, priority=2,
                           frames_per_tick=tier["frames_per_tick"],
                           bandwidth_hz=tier["max_bandwidth_hz"])
        t["route"] = route[:]
        t["status"] = "queued"
        t["custody"] = t["seller"]
        self.events.append({"trade": trade_id, "event": "queued"})
        return msg

    @staticmethod
    def trade_payload(trade: dict) -> bytes:
        """Only actual trade metadata; never synthetic bytes for game difficulty."""
        return json.dumps({"trade": trade["id"], "terms_hash": trade["hash"]},
                          sort_keys=True, separators=(",", ":")).encode()

    def sync_mail(self, mail: MailNetwork):
        """Only an end-to-end returned ACK permits application settlement."""
        changes = []
        for t in self.trades.values():
            if t["status"] != "queued":
                continue
            msg = mail.messages.get("trade:" + t["id"])
            if not msg:
                continue
            t["custody"] = msg["route"][msg["hop"]]
            if msg["status"] == "acknowledged":
                t["status"] = "delivered"
                t["receipt"] = {"trade_id": t["id"], "terms_hash": t["hash"],
                                "receiver": t["buyer"], "accepted": True,
                                "receipt_id": msg["receipt_id"]}
                changes.append({"trade": t["id"], "status": "delivered"})
            elif msg["status"] == "expired":
                # Retain escrow for explicit reconciliation; automatic refund
                # would risk duplicate settlement after delayed delivery.
                t["status"] = "reconcile_required"
                changes.append({"trade": t["id"], "status": "reconcile_required"})
        self.events.extend(changes)
        return changes

    def settle(self, trade_id: str, receipt: dict | None = None):
        t = self._trade(trade_id)
        if t["status"] == "settled":
            return t["settlement"]
        if t["status"] != "delivered" or not t["receipt"]:
            raise GameError("destination has not acknowledged delivery")
        supplied = receipt or t["receipt"]
        if supplied != t["receipt"] or supplied["terms_hash"] != t["hash"]:
            raise GameError("receipt does not match trade")
        seller, buyer = self.worlds[t["seller"]], self.worlds[t["buyer"]]
        quantity, due = t["quantity"], t["quantity"] * t["unit_price"]
        # Both worlds are owned by this simulation coordinator. Applying the
        # two deltas here is atomic in memory and saved as one JSON bundle.
        buyer.cargo[t["good"]] += quantity
        buyer.incoming_reserved -= quantity
        seller.credits += due
        t["status"] = "settled"
        t["settlement"] = {"trade_id": trade_id, "receipt_id": supplied["receipt_id"],
                           "quantity": quantity, "credits": due,
                           "ledger_hash": canonical_hash({"trade": t["hash"], "receipt": supplied})}
        self.events.append({"trade": trade_id, "event": "settled"})
        return t["settlement"]

    def cancel(self, trade_id: str):
        t = self._trade(trade_id)
        if t["status"] != "reserved":
            raise GameError("only undispatched trades can be cancelled")
        self.worlds[t["seller"]].cargo[t["good"]] += t["quantity"]
        self.worlds[t["buyer"]].credits += t["quantity"] * t["unit_price"]
        self.worlds[t["buyer"]].incoming_reserved -= t["quantity"]
        t["status"] = "cancelled"
        self.events.append({"trade": trade_id, "event": "cancelled"})

    def _trade(self, trade_id):
        if trade_id not in self.trades:
            raise GameError("unknown trade")
        return self.trades[trade_id]

    def to_dict(self):
        return {"schema_version": self.schema_version,
                "worlds": {name: world.to_dict() for name, world in self.worlds.items()},
                "network": self.network.to_dict(), "trades": self.trades,
                "events": self.events}

    @classmethod
    def from_dict(cls, data):
        if data.get("schema_version") != 1:
            raise GameError("unsupported federation version")
        return cls({name: Game.from_dict(world) for name, world in data["worlds"].items()},
                   Network.from_dict(data["network"]), data["trades"], data["events"])

    def save(self, path):
        path = Path(path)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.to_dict(), indent=2) + "\n")
        temporary.replace(path)

    @classmethod
    def load(cls, path):
        return cls.from_dict(json.loads(Path(path).read_text()))
