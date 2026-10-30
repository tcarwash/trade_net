"""Two-galaxy simulated commerce with durable, duplicate-safe settlement.

This module is deliberately a *single-process simulation coordinator*. It is
not yet a distributed atomic-commit protocol and cannot prove RF carriage.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from .contracts import simulate_hop
from .engine import Game, GameError, RARE
from .network import Network
from .mail import MailNetwork
from .modems import TIERS
from .payloads import Item, encode as encode_bundle


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
    reports: dict = field(default_factory=dict)
    contract_syncs: dict = field(default_factory=dict)

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
        # This cached second-hop bulletin is explicitly simulated, drawn from
        # another seeded world's real market model, not made-up filler bytes.
        third = Game.new(b_seed + 1, "SIM-W7ABC Galaxy")
        second_hop = "SIM-W7ABC"
        report = {"source": second_hop, "via": remote_id,
                  "observed_epoch": int(time.time() // 300),
                  "provenance": "simulated",
                  "specialization": third.specialization,
                  "specialty_stock": third.ports["Kepler"]["stock"][third.specialization],
                  "specialty_production": third.ports["Kepler"]["production"][third.specialization],
                  "ore_stock": third.ports["Kepler"]["stock"]["ore"],
                  "ore_production": third.ports["Kepler"]["production"]["ore"],
                  "market": {good: third.price("Kepler", good, "sell")
                             for good in ("food", "ore", "fuel", "medicine", *RARE)}}
        report["contracts"] = [{"id": f"{second_hop}-KEPLER-001",
                                "seller_hub": second_hop, "delivery_hub": remote_id,
                                "good": third.specialization,
                                "quantity": min(2, third.ports["Kepler"]["stock"][third.specialization]),
                                "unit_value": third.price("Kepler", third.specialization, "sell")
                                }]
        for world in (a, b):
            source_stock = world.ports["Kepler"]["stock"]
            moved = min(6, source_stock[world.specialization])
            source_stock[world.specialization] -= moved
            world.ports["Haven"]["stock"][world.specialization] += moved
        return cls({local_id: a, remote_id: b}, Network(local_id),
                   reports={second_hop: report})

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
        link_key = ":".join(sorted((t["seller"], t["buyer"])))
        if self.contract_syncs.get(link_key, {}).get("status") != "synchronized":
            raise GameError("synchronize hub contracts before reserving delivery cargo")
        seller = self.worlds[t["seller"]]
        stock = seller.ports["Haven"]["stock"]
        if stock.get(t["good"], 0) < t["quantity"]:
            missing = t["quantity"] - stock.get(t["good"], 0)
            for port, state in seller.ports.items():
                if port == "Haven" or missing <= 0:
                    continue
                moved = min(missing, state["stock"].get(t["good"], 0))
                state["stock"][t["good"]] -= moved
                stock[t["good"]] += moved
                missing -= moved
            if missing:
                moved = min(missing, seller.cargo.get(t["good"], 0))
                seller.cargo[t["good"]] -= moved
                stock[t["good"]] += moved
                missing -= moved
            if missing:
                raise GameError("origin hub stock is insufficient")
        stock[t["good"]] -= t["quantity"]
        t["seller_hold"] = "Haven"
        t["status"] = "reserved"
        t["custody"] = t["seller"]
        self.events.append({"trade": trade_id, "event": "reserved", "escrow_credits": 0})
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

    def queue_trade(self, mail: MailNetwork, trade_id: str, route=None, weight="light",
                    ship_id=None):
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
        payload = self.trade_payload(t, weight, self.reports)
        seller = self.worlds[t["seller"]]
        ship_id = ship_id or seller.active_ship_id
        if ship_id not in seller.fleet:
            raise GameError("unknown mission ship")
        vessel = seller.fleet[ship_id]
        tier = TIERS[vessel.get("modem_tier", 0)]
        msg = mail.enqueue("trade:" + trade_id, route, payload, priority=2,
                           frames_per_tick=tier["frames_per_tick"],
                           bandwidth_hz=tier["max_bandwidth_hz"])
        t["route"] = route[:]
        t["weight"] = weight
        t["transmitted_bytes"] = len(payload)
        t["ship_id"] = ship_id
        t["mission_origin"] = vessel["location"]
        t["status"] = "queued"
        t["custody"] = t["seller"]
        self.events.append({"trade": trade_id, "event": "queued"})
        return msg

    @staticmethod
    def trade_payload(trade: dict, weight="light", reports=None) -> bytes:
        """Three real-information weights, never zero padding.

        A heavier class requires a cached second-hop report; never invent one.
        Report source, via and age remain visible to the receiver.
        """
        core = json.dumps({"trade": trade["id"], "terms_hash": trade["hash"]},
                          sort_keys=True, separators=(",", ":")).encode()
        if weight == "light":
            return core
        if weight not in ("medium", "heavy"):
            raise GameError("unknown transmission weight")
        reports = reports or {}
        report = next((r for r in reports.values() if r["via"] == trade["buyer"]), None)
        if not report:
            raise GameError("no second-hop intelligence available for heavier load")
        provenance = {"source": report["source"], "via": report["via"],
                      "epoch": report["observed_epoch"],
                      "provenance": report["provenance"]}
        hint = {**provenance, "specialization": report.get("specialization"),
                "specialty_stock": report.get("specialty_stock"),
                "specialty_production": report.get("specialty_production"),
                "ore_stock": report["ore_stock"],
                "ore_production": report["ore_production"]}
        items = [Item("trade", core), Item("neighbors", json.dumps(hint, separators=(",", ":")).encode())]
        if weight == "heavy":
            contracts = report.get("contracts", [])
            items.append(Item("contracts", json.dumps({**provenance, "offers": contracts},
                                                         separators=(",", ":")).encode()))
            items.append(Item("market", json.dumps({**provenance, "prices": report["market"]},
                                                   separators=(",", ":")).encode()))
        return encode_bundle(items)

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
                self.settle(t["id"])
                changes[-1]["status"] = "settled"
            elif msg["status"] == "expired":
                # Retain escrow for explicit reconciliation; automatic refund
                # would risk duplicate settlement after delayed delivery.
                t["status"] = "reconcile_required"
                changes.append({"trade": t["id"], "status": "reconcile_required",
                                "ship_result": None})
        for key, sync in self.contract_syncs.items():
            if sync.get("status") != "queued":
                continue
            message = mail.messages.get(sync["message_id"], {})
            if message.get("status") == "acknowledged":
                left, right = (self.worlds[x] for x in sync["route"])
                useful = min(512, max(1, sync["bytes"]))
                reward = min(25, max(1, (useful + 63) // 64))
                left.credits += reward
                right.credits += reward
                sync.update(status="synchronized", useful_bytes=useful,
                            reward_per_hub=reward, receipt_id=message["receipt_id"])
                changes.append({"contracts": key, "status": "synchronized",
                                "reward_per_hub": reward})
            elif message.get("status") == "expired":
                sync["status"] = "retry_available"
                changes.append({"contracts": key, "status": "retry_available"})
        self.events.extend(changes)
        return changes

    def queue_contract_sync(self, mail: MailNetwork, route=None):
        """Exchange the participating hubs' actual delivery offers."""
        route = route or list(self.worlds)
        if (not isinstance(route, list) or len(route) != 2 or
                route[0] not in self.worlds or route[1] not in self.worlds or
                route[0] == route[1]):
            raise GameError("contract sync needs two participating hubs")
        key = ":".join(sorted(route))
        sync = self.contract_syncs.get(key)
        if sync and sync.get("status") in ("queued", "synchronized"):
            return mail.messages[sync["message_id"]]
        offers = [{"id": t["id"], "seller": t["seller"], "receiver": t["buyer"],
                   "good": t["good"], "quantity": t["quantity"],
                   "unit_value": t["unit_price"]}
                  for t in self.trades.values() if t["status"] in ("offered", "reserved")]
        payload = encode_bundle([Item("contracts", json.dumps(
            {"hubs": route, "offers": offers}, sort_keys=True,
            separators=(",", ":")).encode())])
        for station in route:
            mail.add_station(station)
        attempt = (sync or {}).get("attempts", 0) + 1
        message_id = f"contracts:{key}:{attempt}"
        mail.enqueue(message_id, route, payload, priority=2)
        self.contract_syncs[key] = {"status": "queued", "message_id": message_id,
                                    "route": route[:], "bytes": len(payload),
                                    "attempts": attempt}
        return mail.messages[message_id]

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
        quantity = t["quantity"]
        # Both worlds are owned by this simulation coordinator. Applying the
        # two deltas here is atomic in memory and saved as one JSON bundle.
        buyer.ports["Haven"]["stock"][t["good"]] += quantity
        useful_bytes = max(1, min(512, int(t.get("transmitted_bytes", 1))))
        reward = min(25, max(1, (useful_bytes + 63) // 64))
        seller.credits += reward
        buyer.credits += reward
        t["status"] = "settled"
        t["settlement"] = {"trade_id": trade_id, "receipt_id": supplied["receipt_id"],
                           "quantity": quantity, "goods_delivered_to": "Haven",
                           "seller_credits": reward, "receiver_credits": reward,
                           "useful_bytes": useful_bytes,
                           "ledger_hash": canonical_hash({"trade": t["hash"], "receipt": supplied})}
        self.events.append({"trade": trade_id, "event": "settled"})
        return t["settlement"]

    def cancel(self, trade_id: str):
        t = self._trade(trade_id)
        if t["status"] != "reserved":
            raise GameError("only undispatched trades can be cancelled")
        seller = self.worlds[t["seller"]]
        seller.ports["Haven"]["stock"][t["good"]] += t["quantity"]
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
                "events": self.events, "reports": self.reports,
                "contract_syncs": self.contract_syncs}

    @classmethod
    def from_dict(cls, data):
        if data.get("schema_version") != 1:
            raise GameError("unsupported federation version")
        instance = cls({name: Game.from_dict(world) for name, world in data["worlds"].items()},
                   Network.from_dict(data["network"]), data["trades"], data["events"],
                   reports=data.get("reports", {}),
                   contract_syncs=data.get("contract_syncs", {}))
        # Migrate offered demo parcels from the previous ship-cargo model into
        # their source hub stock without changing total inventory.
        for trade in instance.trades.values():
            if trade.get("status") != "offered" or trade.get("seller_hold"):
                continue
            seller = instance.worlds[trade["seller"]]
            amount = min(trade["quantity"], seller.cargo.get(trade["good"], 0))
            seller.cargo[trade["good"]] -= amount
            seller.ports["Haven"]["stock"][trade["good"]] += amount
            trade["seller_hold"] = "Haven"
        if not instance.reports and len(instance.worlds) >= 2:
            remote_id = list(instance.worlds)[-1]
            remote = instance.worlds[remote_id]
            third = Game.new(int(remote.to_dict().get("seed", 42)) + 1,
                             "SIM-W7ABC Galaxy")
            source = "SIM-W7ABC"
            rare = third.specialization
            instance.reports[source] = {
                "source": source, "via": remote_id,
                "observed_epoch": int(time.time() // 300), "provenance": "simulated",
                "specialization": rare,
                "specialty_stock": third.ports["Kepler"]["stock"][rare],
                "specialty_production": third.ports["Kepler"]["production"][rare],
                "ore_stock": third.ports["Kepler"]["stock"]["ore"],
                "ore_production": third.ports["Kepler"]["production"]["ore"],
                "market": {good: third.price("Kepler", good, "sell")
                           for good in ("food", "ore", "fuel", "medicine", *RARE)},
                "contracts": [{"id": f"{source}-KEPLER-001", "seller_hub": source,
                               "delivery_hub": remote_id, "good": rare,
                               "quantity": min(2, third.ports["Kepler"]["stock"][rare]),
                               "unit_value": third.price("Kepler", rare, "sell")}]
            }
        return instance

    def save(self, path):
        path = Path(path)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.to_dict(), indent=2) + "\n")
        temporary.replace(path)

    @classmethod
    def load(cls, path):
        return cls.from_dict(json.loads(Path(path).read_text()))
