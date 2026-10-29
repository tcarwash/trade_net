"""Offline RF-network simulator and provenance-aware peer graph.

No transmissions occur here. A later radio-arcade adapter can supply real
transfer observations without changing the galaxy/economy reducer.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass, field


@dataclass
class Network:
    local_id: str = "AG7SU"
    peers: dict = field(default_factory=dict)
    links: dict = field(default_factory=dict)
    transfers: list = field(default_factory=list)
    sequence: int = 0

    def __post_init__(self):
        self.peers.setdefault(self.local_id, {"kind": "home", "last_seen": 0})

    def to_dict(self):
        return {"local_id": self.local_id, "peers": self.peers,
                "links": self.links, "transfers": self.transfers,
                "sequence": self.sequence}

    @classmethod
    def from_dict(cls, data):
        return cls(**data)

    def discover(self, peer: str, neighbors: list[dict] | None = None):
        """A confirmed direct peer can optionally advertise bounded next hops."""
        if not peer or peer == self.local_id or len(peer) > 32:
            raise ValueError("invalid peer")
        self.peers[peer] = {"kind": "direct", "last_seen": self.sequence}
        seen = set()
        for item in (neighbors or [])[:8]:
            target = item.get("peer", "")
            if (not isinstance(target, str) or not target or len(target) > 32
                    or target in (peer, self.local_id) or target in seen):
                continue
            seen.add(target)
            self.peers.setdefault(target, {"kind": "reported", "last_seen": self.sequence})
            key = self._key(peer, target)
            if self.links.get(key, {}).get("kind") != "observed":
                self.links[key] = {"source": peer, "destination": target,
                                   "kind": "reported", "reported_by": peer,
                                   "goodput_bps": max(0, min(100000, int(item.get("goodput_bps", 0)))),
                                   "sequence": self.sequence}

    @staticmethod
    def _key(src, dst):
        return f"{src}->{dst}"

    def record(self, source: str, destination: str, unique_bytes: int,
               elapsed_seconds: float, delivered: bool, attempted_frames: int,
               lost_frames: int, mode: str = "simulated"):
        if (not source or not destination or source == destination or
                unique_bytes < 0 or elapsed_seconds <= 0 or
                attempted_frames < 1 or not 0 <= lost_frames <= attempted_frames):
            raise ValueError("invalid transfer observation")
        self.sequence += 1
        record = {"id": self.sequence, "source": source, "destination": destination,
                  "unique_bytes": unique_bytes if delivered else 0,
                  "elapsed_seconds": round(elapsed_seconds, 3),
                  "delivered": bool(delivered), "frames": attempted_frames,
                  "lost_frames": lost_frames, "mode": mode}
        self.transfers.append(record)
        self.transfers = self.transfers[-300:]
        # A failed attempt isn't verified discovery. Preserve previously
        # discovered endpoints, and upgrade on success only.
        if delivered and (source == self.local_id or destination == self.local_id):
            peer = destination if source == self.local_id else source
            self.peers[peer] = {"kind": "direct", "last_seen": self.sequence}
        key = self._key(source, destination)
        samples = [t for t in self.transfers if self._key(t["source"], t["destination"]) == key][-20:]
        success = sum(t["delivered"] for t in samples)
        seconds = sum(t["elapsed_seconds"] for t in samples)
        bytes_done = sum(t["unique_bytes"] for t in samples)
        self.links[key] = {"source": source, "destination": destination,
                           "kind": "observed" if success else "attempted",
                           "goodput_bps": round(bytes_done / seconds, 2),
                           "completion": round(success / len(samples), 3),
                           "samples": len(samples), "sequence": self.sequence,
                           "mode": mode}
        return record

    def simulate(self, peer: str, payload_bytes: int, loss: float = .15,
                 frame_bytes: int = 64, bitrate: int = 150,
                 max_rounds: int = 4, neighbors: list | None = None):
        """Seeded fragment/retry model. Each unique fragment is required once.

        Returns honest delivered vs failed transfer; retransmitted bytes do not
        increase useful throughput. The model intentionally has no RF adapter.
        """
        if not isinstance(payload_bytes, int) or not 1 <= payload_bytes <= 65536:
            raise ValueError("payload must be 1..65536 bytes")
        if not 0 <= loss <= 1 or not 16 <= frame_bytes <= 4096 or bitrate <= 0:
            raise ValueError("invalid channel settings")
        if not 1 <= max_rounds <= 20:
            raise ValueError("invalid retry budget")
        if not peer or peer == self.local_id:
            raise ValueError("invalid destination")
        total = math.ceil(payload_bytes / frame_bytes)
        remaining = set(range(total))
        attempted = lost = 0
        # Reproducible on persisted sequence and parameters; a repeat run
        # naturally differs once the journal advances.
        key = f"{self.local_id}:{peer}:{self.sequence}:{payload_bytes}:{loss}:{frame_bytes}"
        rng = random.Random(int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big"))
        for _ in range(max_rounds):
            for frame in sorted(remaining):
                attempted += 1
                if rng.random() >= loss:
                    remaining.remove(frame)
                else:
                    lost += 1
            if not remaining:
                break
        # Include a small fixed per-round turn/ACK cost.
        elapsed = attempted * (frame_bytes * 8 / bitrate + .25) + max_rounds * .5
        success = not remaining
        result = self.record(self.local_id, peer, payload_bytes, elapsed,
                             success, attempted, lost)
        result.update({"missing_frames": len(remaining),
                       "bytes_on_air_estimate": attempted * frame_bytes,
                       "goodput_bps": round(payload_bytes / elapsed, 2) if success else 0})
        if success:
            self.discover(peer, neighbors)
        return result

    def export_json(self):
        return json.dumps(self.to_dict(), separators=(",", ":"))
