"""Durable, simulation-only store-and-forward message layer.

No sockets, modems, or PTT are used. It models fragmentation, custody, offline
stations and application ACKs so a future radio adapter has testable semantics.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path


class MailError(ValueError):
    pass


@dataclass
class MailNetwork:
    stations: dict = field(default_factory=dict)
    messages: dict = field(default_factory=dict)
    inbox: dict = field(default_factory=dict)
    events: list = field(default_factory=list)
    tick: int = 0
    attempts: int = 0
    frame_bytes: int = 64
    schema_version: int = 1

    def add_station(self, station: str, online=True):
        if not station or len(station) > 32:
            raise MailError("invalid station ID")
        self.stations.setdefault(station, {"online": bool(online)})
        self.inbox.setdefault(station, {})

    def set_online(self, station: str, online: bool):
        if station not in self.stations:
            raise MailError("unknown station")
        self.stations[station]["online"] = bool(online)

    def enqueue(self, message_id: str, route: list[str], payload: bytes,
                priority: int = 1, ttl: int = 500, frames_per_tick: int = 4,
                bandwidth_hz: int = 500):
        if not isinstance(payload, bytes) or not 1 <= len(payload) <= 65536:
            raise MailError("payload must be 1..65536 bytes")
        if (not isinstance(route, list) or not 2 <= len(route) <= 8 or
                len(route) != len(set(route)) or
                any(p not in self.stations for p in route)):
            raise MailError("route must contain 2..8 distinct registered stations")
        if not message_id or len(message_id) > 128 or not 0 <= priority <= 3 or not 1 <= ttl <= 100000:
            raise MailError("invalid message options")
        if not 1 <= frames_per_tick <= 64 or bandwidth_hz not in (500, 1200, 2400):
            raise MailError("invalid simulated modem capability")
        digest = hashlib.sha256(payload).hexdigest()
        if message_id in self.messages:
            previous = self.messages[message_id]
            if (previous["sha256"] != digest or previous["route"] != route or
                    previous["priority"] != priority or
                    previous["bandwidth_hz"] != bandwidth_hz):
                raise MailError("message ID reused with different content")
            return previous
        message = {"id": message_id, "type": "data", "route": route[:],
                   "payload_hex": payload.hex(), "sha256": digest,
                   "priority": priority, "created": self.tick, "ttl": ttl,
                   "frames_per_tick": frames_per_tick, "bandwidth_hz": bandwidth_hz,
                   "hop": 0, "received_parts": [], "status": "queued",
                   "frames_attempted": 0, "frames_lost": 0,
                   "receipt_id": None}
        self.messages[message_id] = message
        self.events.append({"tick": self.tick, "event": "queued", "id": message_id})
        return message

    def step(self, loss=.15, budget_frames=8):
        """Advance logical time; process at most budget_frames transmissions.

        ACK packets traverse the reverse route and are themselves subject to
        loss/outages. Only a delivered ACK marks the sender's original message
        acknowledged; a final recipient stores its delivery independently.
        """
        if not 0 <= loss <= 1 or type(budget_frames) is not int or not 1 <= budget_frames <= 1024:
            raise MailError("invalid channel options")
        self.tick += 1
        events = []
        pending = sorted(self.messages.values(), key=lambda m: (-m["priority"], m["created"], m["id"]))
        for m in pending:
            if budget_frames <= 0:
                break
            if m["status"] in ("acknowledged", "delivered", "expired"):
                continue
            if self.tick - m["created"] > m["ttl"]:
                m["status"] = "expired"
                events.append({"event": "expired", "id": m["id"]})
                continue
            src, dst = m["route"][m["hop"]:m["hop"] + 2]
            if not self.stations[src]["online"] or not self.stations[dst]["online"]:
                continue
            size = len(m["payload_hex"]) // 2
            count = math.ceil(size / self.frame_bytes)
            complete = set(m["received_parts"])
            sent_this_message = 0
            for part in range(count):
                if part in complete or budget_frames <= 0 or sent_this_message >= m.get("frames_per_tick", 4):
                    continue
                self.attempts += 1
                sent_this_message += 1
                budget_frames -= 1
                m["frames_attempted"] += 1
                seed = f"{m['id']}:{m['hop']}:{part}:{self.attempts}"
                roll = random.Random(int.from_bytes(hashlib.sha256(seed.encode()).digest()[:8], "big")).random()
                if roll < loss:
                    m["frames_lost"] += 1
                else:
                    complete.add(part)
            m["received_parts"] = sorted(complete)
            if len(complete) != count:
                m["status"] = "transmitting"
                continue
            m["hop"] += 1
            m["received_parts"] = []
            m["status"] = "queued"
            events.append({"event": "custody", "id": m["id"], "at": dst})
            if m["hop"] == len(m["route"]) - 1:
                if hashlib.sha256(bytes.fromhex(m["payload_hex"])).hexdigest() != m["sha256"]:
                    raise MailError("stored payload integrity failure")
                m["status"] = "delivered"
                if m["type"] == "data":
                    self.inbox[dst].setdefault(m["id"], {"sha256": m["sha256"],
                                                          "payload_hex": m["payload_hex"],
                                                          "received_tick": self.tick})
                    self._queue_ack(m)
                else:
                    original = self.messages.get(m["for_id"])
                    if original and original["sha256"] == m["for_hash"]:
                        original["status"] = "acknowledged"
                        original["receipt_id"] = m["id"]
                        events.append({"event": "acknowledged", "id": original["id"]})
        for event in events:
            self.events.append({"tick": self.tick, **event})
        self.events = self.events[-500:]
        return events

    def _queue_ack(self, message):
        ack_id = "ack:" + message["id"]
        if ack_id in self.messages:
            return
        route = list(reversed(message["route"]))
        payload = json.dumps({"id": message["id"], "hash": message["sha256"]},
                             separators=(",", ":")).encode()
        self.messages[ack_id] = {"id": ack_id, "type": "ack", "for_id": message["id"],
                                 "for_hash": message["sha256"], "route": route,
                                 "payload_hex": payload.hex(),
                                 "sha256": hashlib.sha256(payload).hexdigest(),
                                 "priority": 3, "created": self.tick,
                                 "frames_per_tick": 4, "bandwidth_hz": 500,
                                 "ttl": message["ttl"], "hop": 0,
                                 "received_parts": [], "status": "queued",
                                 "frames_attempted": 0, "frames_lost": 0,
                                 "receipt_id": None}

    def to_dict(self):
        return {"stations": self.stations, "messages": self.messages,
                "inbox": self.inbox, "events": self.events, "tick": self.tick,
                "attempts": self.attempts, "frame_bytes": self.frame_bytes,
                "schema_version": self.schema_version}

    @classmethod
    def from_dict(cls, data):
        if data.get("schema_version") != 1:
            raise MailError("unsupported mail state version")
        return cls(**data)

    def save(self, path):
        path = Path(path)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(self.to_dict(), indent=2) + "\n")
        temp.replace(path)

    @classmethod
    def load(cls, path):
        return cls.from_dict(json.loads(Path(path).read_text()))
