"""Local Trade Net command server with operator-approved Data2G sends."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import logging
import math
import re
import socket
import threading
import time
import uuid
import zlib
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .engine import Game, GameError, GOODS, RARE, BASE_PRICE, HAVEN_FACILITIES, CREW_ROLES, LOAN_PLANS, ARTIFACT_CATALOG, ARTIFACT_TYPES, EQUIPMENT_CARGO_SPACE
from .network import Network
from . import modems
from .data2g import Data2GClient, Data2GError
from . import radio_exchange
from . import rigctld

WEB = Path(__file__).with_name("web")
MODEM_CATALOG = Path(__file__).with_name("modem-modes.json")
PART_IDLE_SECONDS = 90
MAX_REPAIR_REQUESTS = 3
MAX_AUTO_RETRIES = 2
MAX_REPLY_ATTEMPTS = 5


class App:
    def __init__(self, save: Path, seed: int, callsign: str, data2g_host="127.0.0.1",
                 command_port=8300, kiss_port=8100, group="TRADENET",
                 rigctld_host=None, rigctld_port=4532):
        self.callsign = callsign
        self.data2g = (data2g_host, command_port, kiss_port, group)
        self.rigctld = (rigctld_host, rigctld_port) if rigctld_host else None
        self.rig_status = {"status": "connecting" if self.rigctld else "disabled",
                           "frequency_hz": None, "band": None, "updated_at": None}
        self.save = save
        self.save_id = hashlib.sha256(str(save.resolve()).encode("utf-8")).hexdigest()[:16]
        self.radio_save = save.with_suffix(".radio.json")
        self.radio_contacts = {}
        self.radio_contracts = {}
        self.radio_resources = {}
        self.radio_reservations = {}
        self.radio_processed = {}
        self.radio_assemblies = {}
        self.radio_pending_replies = {}
        self.radio_beacons = {}
        self.beacon_last_tx = None
        try:
            saved_radio = json.loads(self.radio_save.read_text(encoding="utf-8"))
            if isinstance(saved_radio, dict) and "transmissions" in saved_radio:
                self.radio_transmissions = saved_radio.get("transmissions", {})
                self.radio_inbox = saved_radio.get("inbox", [])
                self.radio_contacts = saved_radio.get("contacts", {})
                self.radio_contracts = saved_radio.get("contracts", {})
                self.radio_resources = saved_radio.get("resources", {})
                self.radio_reservations = saved_radio.get("reservations", {})
                self.radio_processed = saved_radio.get("processed", {})
                self.radio_assemblies = saved_radio.get("assemblies", {})
                self.radio_pending_replies = saved_radio.get("pending_replies", {})
                self.radio_beacons = saved_radio.get("beacons", {})
                self.beacon_last_tx = saved_radio.get("beacon_last_tx")
            else:
                self.radio_transmissions = saved_radio if isinstance(saved_radio, dict) else {}
                self.radio_inbox = []
                self.radio_contacts = {}
                self.radio_contracts = {}
                self.radio_resources = {}
                self.radio_reservations = {}
                self.radio_processed = {}
                self.radio_assemblies = {}
                self.radio_pending_replies = {}
        except (OSError, ValueError):
            self.radio_transmissions = {}
            self.radio_inbox = []
        self.radio_listener_status = "starting"
        try:
            self.modem_catalog = json.loads(MODEM_CATALOG.read_text(encoding="utf-8"))
            if not isinstance(self.modem_catalog, dict):
                raise ValueError("modem catalog must be an envelope")
        except (OSError, ValueError):
            self.modem_catalog = {"modes": [], "provenance": "unavailable"}
        self.net_save = save.with_suffix(".network.json")
        if save.exists():
            saved_game = json.loads(save.read_text(encoding="utf-8"))
            saved_galaxies = saved_game.get("galaxies", {})
            for station in list(saved_galaxies):
                if station != "home" and (station not in self.radio_resources or
                                           self.radio_resources[station].get("via")):
                    saved_galaxies.pop(station, None)
            for ship in [saved_game.get("ship", {}),
                         *saved_game.get("fleet", {}).values()]:
                if ship.get("galaxy") not in saved_galaxies:
                    ship["galaxy"] = "home"
            self.game = Game.from_dict(saved_game)
        else:
            self.game = Game.new(seed)
        if isinstance(self.game.radio_state, dict):
            self.radio_transmissions = self.game.radio_state.get("transmissions", self.radio_transmissions)
            self.radio_inbox = self.game.radio_state.get("inbox", self.radio_inbox)
            self.radio_contacts = self.game.radio_state.get("contacts", self.radio_contacts)
            self.radio_contracts = self.game.radio_state.get("contracts", self.radio_contracts)
            self.radio_resources = self.game.radio_state.get("resources", self.radio_resources)
            self.radio_reservations = self.game.radio_state.get("reservations", self.radio_reservations)
            self.radio_processed = self.game.radio_state.get("processed", self.radio_processed)
            self.radio_assemblies = self.game.radio_state.get("assemblies", self.radio_assemblies)
            self.radio_pending_replies = self.game.radio_state.get("pending_replies", self.radio_pending_replies)
            self.radio_beacons = self.game.radio_state.get("beacons", self.radio_beacons)
            self.beacon_last_tx = self.game.radio_state.get("beacon_last_tx", self.beacon_last_tx)
        for station in list(self.game.galaxies):
            if station != "home" and (station not in self.radio_resources or
                                       self.radio_resources[station].get("via")):
                self.game.galaxies.pop(station, None)
        # Older demo saves placed ships in shared simulated galaxies. Cross-station
        # travel no longer exists, so return those ships to the local galaxy.
        for ship in self.game.fleet.values():
            if ship.get("galaxy") not in self.game.galaxies:
                ship["galaxy"] = "home"
        if self.game.active_ship_id:
            self.game._bind_ship()
        self.net = (Network.from_dict(json.loads(self.net_save.read_text()))
                    if self.net_save.exists() else Network(callsign))
        self._sync_discovered_galaxies()
        self.lock = threading.RLock()
        # Legacy NPC freight records remain in old saves for recovery, but the
        # live web API no longer offers or dispatches fabricated remote jobs.
        self._ensure_radio_contracts()
        self.tx_lock = threading.Lock()
        self.persist()
        self.sync_clock()
        self.radio_listener = threading.Thread(target=self._listen_for_frames,
                                              name="tradenet-radio-listener", daemon=True)
        self.radio_listener.start()
        self.radio_recovery = threading.Thread(target=self._run_radio_recovery,
                                               name="tradenet-radio-recovery", daemon=True)
        self.radio_recovery.start()
        if self.rigctld:
            self.rig_monitor = threading.Thread(target=self._poll_rig_frequency,
                                                name="tradenet-rigctld-monitor", daemon=True)
            self.rig_monitor.start()

    def _poll_rig_frequency(self):
        """Rig telemetry is read-only; a band sighting earns one bounded bonus."""
        while True:
            try:
                frequency = rigctld.read_frequency(*self.rigctld)
                self._record_rig_frequency(frequency)
            except (OSError, ValueError) as exc:
                with self.lock:
                    self.rig_status = {"status": "offline", "frequency_hz": None,
                                       "band": None, "updated_at": None,
                                       "error": str(exc)[:120]}
            time.sleep(3)

    def _record_rig_frequency(self, frequency):
        band = rigctld.band_for_frequency(frequency)
        with self.lock:
            self.rig_status = {"status": "online", "frequency_hz": frequency,
                               "band": band, "updated_at": time.time()}
            if band and band not in self.game.radio_bands_seen:
                self.game.radio_bands_seen.append(band)
                self.game.credits += 60
                self.game.factions["explorers"] += 1
                self.game.journal.append({"id": "rig-band-" + band,
                    "tick": self.game.tick, "action": "discover_radio_band",
                    "result": {"band": band, "reward": 60}})
                self.persist()

    def _verify_contract_band(self, required_band):
        if not required_band:
            return
        if not getattr(self, "rigctld", None):
            raise GameError(f"{required_band} contract: connect rigctld to verify the tuned band.")
        try:
            frequency = rigctld.read_frequency(*self.rigctld)
        except (OSError, ValueError) as exc:
            raise GameError("Rig frequency unavailable; band-limited delivery cannot transmit.") from exc
        if rigctld.band_for_frequency(frequency) != required_band:
            raise GameError(f"Contract requires {required_band}; tune your rig before sending.")

    def _listen_for_frames(self):
        """Continuously receive group frames; classify addressed traffic and gossip."""
        host, command_port, kiss_port, group = self.data2g
        while True:
            try:
                with Data2GClient(host, command_port, kiss_port, timeout=5) as modem:
                    port = modem.open_group(group, self.callsign)
                    with self.lock:
                        self.radio_listener_status = "listening"
                    while True:
                        try:
                            frame_port, command, payload = modem.receive()
                        except socket.timeout:
                            continue
                        if frame_port != port or command != 0:
                            continue
                        self._handle_received_frame(payload)
            except (Data2GError, OSError, ValueError):
                with self.lock:
                    self.radio_listener_status = "reconnecting"
                time.sleep(5)

    def _send_radio_frames(self, modem, payload, mode_id, tier):
        """Use a shared local transmitter lock and station-offset send window."""
        packets = radio_exchange.frames(payload)
        with self.tx_lock:
            # Callsign offsets spread independent stations within a short UTC
            # window. Data2G remains responsible for its own channel access.
            slot = zlib.crc32(self.callsign.encode("ascii")) % 4
            phase = time.time() % 12
            target = slot * 3
            delay = (target - phase) % 12
            if delay > .05:
                time.sleep(delay)
            modem.select_mode(mode_id, tier)
            for packet in packets:
                modem.send_once(packet, approved=True)
        return packets

    def _send_recovery_payload(self, payload, mode_id=None, indices=None, required_band=None):
        """Queue a saved message or selected parts without holding the game lock."""
        self._verify_contract_band(required_band)
        host, command_port, kiss_port, group = self.data2g
        packets = radio_exchange.frames(payload)
        if indices is not None:
            packets = [packets[index] for index in indices]
        with Data2GClient(host, command_port, kiss_port) as modem:
            modem.open_group(group, self.callsign)
            available = [vars(mode) for mode in modem.modes()]
            with self.lock:
                modes = self._eligible_radio_modes(available)
                tier = int(self.game.ship.get("modem_tier", 0))
            needed = max(map(len, packets))
            mode = next((item for item in modes if item["mode_id"] == mode_id and
                         item["bytes_per_codeword"] * item["max_codewords"] >= needed), None)
            if mode is None:
                mode = next((item for item in modes if
                             item["bytes_per_codeword"] * item["max_codewords"] >= needed), None)
            if mode is None:
                raise Data2GError("no eligible mode can carry the recovery frame")
            with self.tx_lock:
                slot = zlib.crc32(self.callsign.encode("ascii")) % 4
                delay = (slot * 3 - time.time() % 12) % 12
                if delay > .05:
                    time.sleep(delay)
                modem.select_mode(mode["mode_id"], tier)
                for packet in packets:
                    modem.send_once(packet, approved=True)

    def _queue_radio_reply(self, reply):
        if not hasattr(self, "radio_pending_replies"):
            self.radio_pending_replies = {}
        key = hashlib.sha256(reply).hexdigest()[:16]
        prior = self.radio_pending_replies.get(key, {})
        self.radio_pending_replies[key] = {"payload_hex": reply.hex(),
            "attempts": prior.get("attempts", 0), "due_at": time.time(),
            "created_at": prior.get("created_at", time.time())}
        self.radio_pending_replies = dict(list(self.radio_pending_replies.items())[-100:])

    def _run_radio_recovery(self):
        while True:
            try:
                work = self._next_radio_recovery_work()
                if work is None:
                    time.sleep(2)
                    continue
                kind, key, payload, mode_id, indices, required_band = work
                try:
                    self._send_recovery_payload(payload, mode_id, indices, required_band)
                    error = None
                except (Data2GError, GameError, OSError, ValueError, IndexError) as exc:
                    error = str(exc)
                with self.lock:
                    self._finish_radio_recovery_work(kind, key, error, indices)
            except Exception:
                logging.exception("radio recovery worker failed")
                time.sleep(5)

    def _next_radio_recovery_work(self):
        with self.lock:
            now = time.time()
            self._expire_radio_transmissions(now)
            for key, item in list(self.radio_pending_replies.items()):
                if item.get("due_at", 0) > now:
                    continue
                if item.get("attempts", 0) >= MAX_REPLY_ATTEMPTS:
                    self.radio_pending_replies.pop(key, None)
                    self.persist()
                    continue
                item["attempts"] = item.get("attempts", 0) + 1
                item["due_at"] = now + 15 * 2 ** (item["attempts"] - 1)
                self.persist()
                return "reply", key, bytes.fromhex(item["payload_hex"]), None, None, None
            for key, assembly in list(self.radio_assemblies.items()):
                if (assembly.get("destination") != self.callsign or
                        assembly.get("repair_attempts", 0) >= MAX_REPAIR_REQUESTS or
                        now - assembly.get("updated_at", now) < PART_IDLE_SECONDS or
                        now < assembly.get("repair_due_at", 0)):
                    continue
                count = assembly["count"]
                missing = sum(1 << i for i in range(count)
                              if str(i) not in assembly["parts"])
                if not missing:
                    continue
                sender, msg_id = key.split("/", 1)
                try:
                    payload = radio_exchange.encode({"v": 1, "t": "repair",
                        "i": uuid.uuid4().hex[:16], "f": self.callsign,
                        "d": sender, "r": msg_id, "h": assembly["digest"],
                        "m": count, "b": f"{missing:0{(count + 3) // 4}x}"})
                except ValueError:
                    continue
                assembly["repair_attempts"] = assembly.get("repair_attempts", 0) + 1
                assembly["repair_due_at"] = now + PART_IDLE_SECONDS * assembly["repair_attempts"]
                self.persist()
                return "repair_request", key, payload, None, None, None
            for key, job in self.radio_transmissions.items():
                if job.get("status") != "awaiting_ack":
                    continue
                indices = job.get("repair_indices")
                if indices and now >= job.get("repair_send_due_at", 0):
                    if job.get("repair_send_attempts", 0) >= MAX_REPAIR_REQUESTS:
                        job.pop("repair_indices", None)
                        self.persist()
                        continue
                    job.pop("repair_indices", None)
                    job["repair_send_attempts"] = job.get("repair_send_attempts", 0) + 1
                    payload = bytes.fromhex(job["payload_hex"])
                    self.persist()
                    return "repair_parts", key, payload, job.get("mode_id"), indices, job.get("band")
                if job.get("retry_due_at", now + 1) <= now and job.get("payload_hex"):
                    job.pop("retry_due_at", None)
                    job["auto_retry_count"] = job.get("auto_retry_count", 0) + 1
                    job["timeout_at"] = now + job.get("timeout_seconds", 180) + 20
                    self.persist()
                    return "retry", key, bytes.fromhex(job["payload_hex"]), job.get("mode_id"), None, job.get("band")
        return None

    def _finish_radio_recovery_work(self, kind, key, error, indices):
        now = time.time()
        if kind == "reply":
            item = self.radio_pending_replies.get(key)
            if item:
                if error is None or item["attempts"] >= MAX_REPLY_ATTEMPTS:
                    self.radio_pending_replies.pop(key, None)
        elif kind == "repair_request":
            assembly = self.radio_assemblies.get(key)
            if assembly and error:
                assembly["repair_due_at"] = now + 30 * assembly["repair_attempts"]
        else:
            job = self.radio_transmissions.get(key)
            if job and job.get("status") == "awaiting_ack":
                if kind == "repair_parts" and error:
                    job["repair_indices"] = sorted(set(indices or []) |
                                                   set(job.get("repair_indices", [])))
                    job["repair_send_due_at"] = now + 30 * job["repair_send_attempts"]
                elif kind == "repair_parts":
                    job["repair_send_attempts"] = 0
                if kind == "retry" and error:
                    job["timeout_at"] = now + 30
                if error:
                    job["recovery_error"] = error
                else:
                    job.pop("recovery_error", None)
        self.persist()

    def _ensure_radio_contracts(self):
        contracts, serial = radio_exchange.generate_contracts(
            self.game, self.callsign, existing=self.radio_contracts.get(self.callsign, []))
        self.radio_contracts[self.callsign] = contracts
        self.radio_contract_serial = serial

    def _eligible_radio_modes(self, advertised):
        ship = self.game.ship
        tier = int(ship.get("modem_tier", 0))
        modes = modems.unlocked_modes(
            [mode for mode in modems.eligible_modes(advertised, tier)
             if "ack" not in mode["mode_id"].lower()],
            self.game.radio_unlocks)
        class_id = ship.get("class_id")
        if class_id:
            modes = modems.eligible_ship_modes(modes, class_id)
        return modes

    def _radio_profile(self):
        return radio_exchange.profile(self.game)

    def _radio_wire_profile(self):
        profile = self._radio_profile()
        return {"x": profile["richness"], "s": profile["stock"], "p": profile["production"]}

    def _radio_neighbors(self, exclude=None, limit=3, detail=False):
        neighbors = []
        for station, profile in sorted(self.radio_resources.items()):
            if station in (self.callsign, exclude) or profile.get("via"):
                continue
            summary = {"f": station, "x": profile.get("richness"),
                       "c": radio_exchange.wire_contracts(
                           self.radio_contracts.get(station, []), 3 if detail else 1)}
            if detail:
                summary["s"] = profile.get("stock", [])
                summary["p"] = profile.get("production", [])
                summary["e"] = int(profile.get("observed_at") or 0)
            neighbors.append(summary)
            if len(neighbors) >= limit:
                break
        return neighbors

    def _radio_reward(self, byte_count):
        reward = max(1, min(25, math.ceil(byte_count / 64)))
        self.game.credits += reward
        return reward

    def _handle_received_frame(self, payload):
        if not 1 <= len(payload) <= radio_exchange.MAX_FRAME_BYTES:
            return None
        beacon = radio_exchange.decode_beacon(payload)
        if beacon:
            self._record_radio_beacon(beacon, payload)
            return None
        frame = radio_exchange.decode(payload)
        if not frame:
            return None
        if frame.get("t") == "repair":
            self._handle_repair_request(frame)
            return None
        if frame.get("t") == "part":
            return self._receive_part(frame)
        return self._handle_radio_message(payload)

    def _record_radio_beacon(self, beacon: dict, payload: bytes) -> None:
        """Passive station intel only: no contact, credits or automatic replies."""
        sender = beacon["callsign"]
        if sender == self.callsign or not self._valid_station(sender):
            return
        with self.lock:
            heard = getattr(self, "radio_beacons", {})
            digest = hashlib.sha256(payload).hexdigest()[:16]
            old = heard.get(sender)
            entry = {**beacon, "digest": digest, "observed_at": time.time(),
                     "verified": False, "source": "radio"}
            heard[sender] = entry
            self.radio_beacons = dict(list(heard.items())[-100:])
            if not old or old.get("digest") != digest:
                self.radio_inbox.append({"digest": digest, "received_at": entry["observed_at"],
                    "from": sender, "to": "group", "type": "beacon",
                    "outcome": "station advertisement", "bytes": len(payload),
                    "details": f"Galaxy signature: {beacon['good']}",
                    "offers": [beacon["contract"]] if beacon.get("contract") else []})
                self.radio_inbox = self.radio_inbox[-100:]
            self.persist()

    def _beacon_payload(self, good: str, contract_id: str = "") -> tuple[bytes, dict]:
        self._ensure_radio_contracts()
        # A beacon identifies the galaxy's defining abundance, not live stock.
        good = self.game.specialization
        if good not in RARE:
            raise GameError("this galaxy has no valid abundance signature")
        contract = None
        if contract_id:
            contract = next((c for c in self.radio_contracts.get(self.callsign, [])
                             if c["id"] == contract_id and c.get("status", "open") == "open"), None)
            if not contract:
                raise GameError("choose an open station contract for the beacon")
        # 255 means signature resource; the beacon makes no inventory claim.
        abundance = 255
        try:
            payload = radio_exchange.encode_beacon(self.callsign, good, abundance, contract)
        except ValueError as exc:
            raise GameError(str(exc)) from exc
        return payload, radio_exchange.decode_beacon(payload)

    def _handle_repair_request(self, frame):
        """Accept a bounded missing-part request only from the intended peer."""
        sender, msg_id, digest = frame.get("f"), frame.get("r"), frame.get("h")
        if (frame.get("d") != self.callsign or not self._valid_station(sender) or
                not isinstance(msg_id, str) or not 1 <= len(msg_id) <= 32 or
                not isinstance(digest, str) or len(digest) != 16):
            return
        with self.lock:
            job = next((item for item in self.radio_transmissions.values()
                        if item.get("message_id") == msg_id and
                           item.get("destination") == sender and
                           item.get("payload_hash") == digest and
                           item.get("status") == "awaiting_ack" and
                           item.get("payload_hex")), None)
            if job is None:
                return
            if job.get("repair_requests_seen", 0) >= MAX_REPAIR_REQUESTS:
                return
            count = len(radio_exchange.frames(bytes.fromhex(job["payload_hex"])))
            bitmap = frame.get("b")
            if (frame.get("m") != count or count <= 1 or
                    not isinstance(bitmap, str) or len(bitmap) != (count + 3) // 4 or
                    any(c not in "0123456789abcdef" for c in bitmap)):
                return
            bits = int(bitmap, 16)
            if not bits or bits >> count:
                return
            requested = [index for index in range(count) if bits & (1 << index)]
            job["repair_requests_seen"] = job.get("repair_requests_seen", 0) + 1
            job["repair_indices"] = sorted(set(job.get("repair_indices", [])) |
                                           set(requested))
            self.persist()

    def _receive_part(self, frame):
        sender, destination, msg_id = (frame.get(key) for key in ("f", "d", "i"))
        index, count, digest, encoded = (frame.get(key) for key in ("k", "m", "h", "b"))
        if (not self._valid_station(sender) or sender == self.callsign or
                not isinstance(destination, str) or not self._valid_station(destination) or
                not isinstance(msg_id, str) or not 1 <= len(msg_id) <= 32 or
                type(index) is not int or type(count) is not int or
                not 0 <= index < count <= radio_exchange.MAX_PARTS or
                not isinstance(digest, str) or len(digest) != 16 or
                any(c not in "0123456789abcdef" for c in digest) or
                not isinstance(encoded, str) or len(encoded) > 180):
            return None
        try:
            part = base64.b64decode(encoded, validate=True)
        except (ValueError, base64.binascii.Error):
            return None
        if not 1 <= len(part) <= 120:
            return None
        key = f"{sender}/{msg_id}"
        with self.lock:
            done = self.radio_processed.get(key)
            if done:
                if (index == count - 1 and done.get("digest") == digest and
                        done.get("reply_hex")):
                    reply = bytes.fromhex(done["reply_hex"])
                    self._queue_radio_reply(reply)
                    self.persist()
                    return reply
                return None
            now = time.time()
            self.radio_assemblies = {k: v for k, v in self.radio_assemblies.items()
                if now - v.get("updated_at", now) < 900}
            assembly = self.radio_assemblies.get(key)
            if assembly and (assembly["digest"] != digest or assembly["count"] != count or
                             assembly["destination"] != destination):
                return None
            if not assembly:
                assembly = {"digest": digest, "count": count, "destination": destination,
                            "parts": {}, "updated_at": now}
                self.radio_assemblies[key] = assembly
                self.radio_assemblies = dict(list(self.radio_assemblies.items())[-64:])
            previous = assembly["parts"].get(str(index))
            if previous and previous != encoded:
                return None
            assembly["parts"][str(index)] = encoded
            assembly["updated_at"] = now
            if len(assembly["parts"]) != count:
                self.persist()
                return None
            message = b"".join(base64.b64decode(assembly["parts"][str(i)])
                               for i in range(count))
            self.radio_assemblies.pop(key, None)
            parsed = radio_exchange.decode(message)
            if (len(message) > radio_exchange.MAX_MESSAGE_BYTES or
                    hashlib.sha256(message).hexdigest()[:16] != digest or
                    not parsed or parsed.get("f") != sender or
                    parsed.get("d") != destination or parsed.get("i") != msg_id or
                    parsed.get("t") == "part"):
                self.persist()
                return None
            return self._handle_radio_message(message)

    def _handle_radio_message(self, payload):
        envelope = radio_exchange.decode(payload)
        if not envelope:
            return None
        digest = hashlib.sha256(payload).hexdigest()[:16]
        sender = envelope.get("f")
        destination = envelope.get("d")
        kind = envelope.get("t")
        with self.lock:
            if not self._valid_station(sender) or sender == self.callsign:
                return None
            if kind not in ("contact", "contact_ack", "delivery", "delivery_ack", "gossip"):
                return None
            if not isinstance(destination, str) or destination not in ("*", self.callsign) and not self._valid_station(destination):
                return None
            if (kind in ("contact_ack", "delivery_ack") and
                    destination in ("*", self.callsign) and
                    not self._matching_radio_job(envelope)):
                return None
            msg_id = envelope.get("i")
            if not isinstance(msg_id, str) or not 1 <= len(msg_id) <= 32:
                return None
            ledger_id = f"{sender}/{msg_id}"
            processed = self.radio_processed.get(ledger_id)
            if processed:
                if processed.get("digest") != digest:
                    return None
                if processed.get("reply_hex"):
                    reply = bytes.fromhex(processed["reply_hex"])
                    self._queue_radio_reply(reply)
                    self.persist()
                    return reply
                return None
            addressed = destination in ("*", self.callsign)
            neighbors = envelope.get("n", [])
            if not isinstance(neighbors, list):
                neighbors = []
            richness = envelope.get("x")
            peer_contracts = radio_exchange.read_contracts(envelope.get("c", []), sender)
            profile = {"richness": richness, "stock": envelope.get("s", []),
                       "production": envelope.get("p", []), "observed_at": time.time()}
            self.radio_resources[sender] = profile
            had_contact = sender in self.radio_contacts
            first_contact = addressed and kind == "contact" and not had_contact
            if addressed and kind == "contact":
                self.radio_contacts.setdefault(sender, time.time())
            try:
                normalized = []
                for item in neighbors[:8]:
                    if isinstance(item, dict):
                        station = item.get("f")
                        if self._valid_station(station) and station not in (sender, self.callsign):
                            normalized.append((station, item.get("x"), item.get("s", []),
                                               item.get("p", []), item.get("c", []), item.get("e", 0)))
                    elif isinstance(item, list) and len(item) > 1 and self._valid_station(item[0]):
                        terms = [item[2]] if len(item) > 2 and item[2] else []
                        normalized.append((item[0], item[1], [], [], terms, 0))
                advertised = [{"peer": n[0]} for n in normalized]
                self.net.discover(sender, advertised)
                for station, rich, stock, production, terms, observed in normalized:
                    if rich not in ("aether", "iridium", "mycelium"):
                        continue
                    self.net.peers.setdefault(station, {})["specialization"] = rich
                    existing = self.radio_resources.get(station, {})
                    if (not existing or existing.get("via")) and (not existing or
                            type(observed) is not int or observed >= existing.get("observed_at", 0)):
                        self.radio_resources[station] = {"richness": rich, "stock": stock,
                            "production": production, "via": sender,
                            "observed_at": observed if type(observed) is int and observed > 0 else time.time()}
                        extra_contracts = radio_exchange.read_contracts(terms, station)
                        if extra_contracts:
                            self.radio_contracts[station] = extra_contracts
            except (ValueError, TypeError, AttributeError):
                pass
            self._sync_discovered_galaxies()
            if richness in ("aether", "iridium", "mycelium"):
                self.game.galaxies[sender]["specialization"] = richness
            if peer_contracts and kind == "contact":
                self.radio_contracts[sender] = peer_contracts
            elif peer_contracts and not addressed and not had_contact and kind in ("contact_ack", "delivery_ack"):
                self.radio_contracts[sender] = peer_contracts
            reply = None
            reward = 0
            if addressed and kind == "contact":
                self._ensure_radio_contracts()
                if first_contact:
                    reward = self._radio_reward(len(payload))
                reply_msg = {"v": 1, "t": "contact_ack", "i": "a" + uuid.uuid4().hex[:12],
                    "r": msg_id, "h": hashlib.sha256(payload).hexdigest()[:16],
                    "f": self.callsign, "d": sender, "cr": 0,
                    **self._radio_wire_profile(),
                    "c": radio_exchange.wire_contracts(self.radio_contracts[self.callsign]),
                    "n": self._radio_neighbors(exclude=sender)}
                try:
                    reply_msg["cr"] = max(1, min(25, math.ceil(len(radio_exchange.encode_message(reply_msg)) / 64)))
                    reply = radio_exchange.encode_message(reply_msg)
                except ValueError:
                    reply_msg["c"] = []
                    reply = radio_exchange.encode_message(reply_msg)
            elif addressed and kind == "delivery" and destination == self.callsign:
                contract_id, good, quantity = envelope.get("c"), envelope.get("g"), envelope.get("q")
                if envelope.get("gift") is True:
                    accepted = bool(had_contact and good in GOODS and type(quantity) is int
                        and 0 < quantity <= 10000)
                    if accepted:
                        self.game.ports["Haven"]["stock"][good] += quantity
                        reward = self._radio_reward(len(payload))
                    replacement = []
                elif good == "artifact":
                    artifact = envelope.get("a")
                    category = artifact.get("category") if isinstance(artifact, dict) else None
                    artifact_id = artifact.get("id") if isinstance(artifact, dict) else None
                    artifact_key = f"{sender}/{artifact_id}" if isinstance(artifact_id, str) else ""
                    valid_artifact = (isinstance(category, str) and category in ARTIFACT_TYPES and isinstance(artifact_id, str)
                        and 1 <= len(artifact_id) <= 64 and isinstance(artifact.get("title"), str)
                        and isinstance(artifact.get("source_port"), str))
                    price = ARTIFACT_TYPES[category]["base_value"] if valid_artifact else 0
                    accepted = bool(had_contact and quantity == 1 and valid_artifact
                        and artifact_key not in self.game.artifact_inventory and self.game.credits >= price)
                    if accepted:
                        self.game.credits -= price
                        received = {**deepcopy(artifact), **ARTIFACT_TYPES[category],
                            "id": artifact_key, "acquired_from": sender, "status": "held"}
                        self.game.artifact_inventory[artifact_key] = received
                        self.game.artifact_history[artifact_key] = deepcopy(received)
                        reward = self._radio_reward(len(payload))
                    replacement = []
                    if accepted:
                        self._ensure_radio_contracts()
                        replacement = [c for c in self.radio_contracts[self.callsign]
                            if c.get("status") == "open"][:1]
                else:
                    local_contracts = self.radio_contracts.get(self.callsign, [])
                    old_ids = {c.get("id") for c in local_contracts}
                    local = next((c for c in local_contracts
                        if c["id"] == contract_id and c.get("status", "open") == "open"), None)
                    accepted = bool(had_contact and local and good == local["good"] and quantity == local["quantity"]
                                and type(quantity) is int and 0 < quantity <= 10000)
                    if accepted and local.get("requirements"):
                        manifest = envelope.get("m")
                        accepted = bool(isinstance(manifest, list) and
                            len(manifest) == len(local["requirements"]) and
                            all(isinstance(term, list) and len(term) == 2 and
                                isinstance(term[0], str) and type(term[1]) is int
                                for term in manifest) and
                            dict((term[0], term[1]) for term in manifest) ==
                            radio_exchange.contract_requirements(local))
                    replacement = []
                    if accepted:
                        for resource, amount in radio_exchange.contract_requirements(local).items():
                            self.game.ports["Haven"]["stock"][resource] += amount
                        local["status"] = "fulfilled"
                        self._ensure_radio_contracts()
                        replacement = [c for c in self.radio_contracts[self.callsign]
                            if c["id"] not in old_ids and c.get("status", "open") == "open"][:1]
                        reward = self._radio_reward(len(payload))
                reply_msg = {"v": 1, "t": "delivery_ack", "i": "a" + uuid.uuid4().hex[:12],
                    "r": msg_id, "h": hashlib.sha256(payload).hexdigest()[:16],
                    "f": self.callsign, "d": sender, "ok": accepted, "cr": 0,
                    **self._radio_wire_profile(),
                    "c": radio_exchange.wire_contracts(replacement),
                    "n": self._radio_neighbors(exclude=sender)}
                try:
                    reply_msg["cr"] = (max(1, min(25, math.ceil(len(radio_exchange.encode_message(reply_msg)) / 64)))
                                       if accepted else 0)
                    reply = radio_exchange.encode_message(reply_msg)
                except ValueError:
                    reply_msg["c"] = []
                    reply = radio_exchange.encode_message(reply_msg)
            elif addressed and kind in ("contact_ack", "delivery_ack"):
                self._apply_radio_ack(envelope, payload)
            elif addressed and kind not in ("gossip",):
                return None
            outcome = ("gossip" if not addressed else
                       "delivery accepted" if kind == "delivery" and reply and accepted else
                       "delivery rejected" if kind == "delivery" and reply else
                       "contract data" if kind == "contact" else "radio receipt")
            details = (f'{envelope.get("q")} {envelope.get("g")} trade'
                       if kind == "delivery" and envelope.get("g") == "artifact" else
                       f'{envelope.get("q")} {envelope.get("g")} delivery'
                       if kind == "delivery" else
                       f'{len(peer_contracts)} contract terms' if kind == "contact" else "")
            self.radio_inbox.append({"digest": digest, "received_at": time.time(),
                "from": sender, "to": destination or "group",
                "type": kind or "unrecognized frame", "outcome": outcome,
                "bytes": len(payload), "details": details,
                "offers": radio_exchange.wire_contracts(peer_contracts)})
            self.radio_inbox = self.radio_inbox[-100:]
            self.radio_processed[ledger_id] = {"digest": digest,
                "reply_hex": reply.hex() if reply else "", "kind": kind}
            self.radio_processed = dict(list(self.radio_processed.items())[-500:])
            if reply:
                self._queue_radio_reply(reply)
            self.persist()
            return reply

    @staticmethod
    def _valid_station(station):
        return (isinstance(station, str) and 1 <= len(station) <= 32 and station.isascii()
                and all(c.isalnum() or c in "-/" for c in station))

    def _matching_radio_job(self, envelope):
        job = next((item for item in self.radio_transmissions.values()
                    if item.get("message_id") == envelope.get("r")), None)
        expected_type = ("contact_ack" if job and job.get("purpose") == "contact"
                         else "delivery_ack")
        if (not job or job.get("status") not in ("awaiting_ack", "failed", "cancelled") or
                envelope.get("t") != expected_type or
                envelope.get("h") != job.get("payload_hash") or
                envelope.get("d") != self.callsign or
                envelope.get("f") != job.get("destination")):
            return None
        return job

    def _apply_radio_ack(self, envelope, payload):
        job = self._matching_radio_job(envelope)
        if not job:
            return
        if envelope.get("ok", True):
            reward_value = envelope.get("cr", 0)
            reward = reward_value if type(reward_value) is int else 0
            # A verified, contracted RF delivery is the premium career path.
            # Compute the settlement locally from reserved goods; never trust
            # an arbitrary credit amount advertised in a received ACK.
            if job.get("purpose") == "delivery":
                reservation = self.radio_reservations.get(job.get("contract_id"))
                if reservation:
                    goods = reservation.get("goods") or {
                        reservation["good"]: reservation["quantity"]}
                    base_reward = min(3000 if len(goods) > 1 else 1500,
                        100 + sum(BASE_PRICE[resource] * count * 2
                                  for resource, count in goods.items()))
                    relay_level = self.game.haven_facilities.get("interstellar_relay", 0)
                    job["reward"] = base_reward * (100 + 25 * relay_level) // 100
                    self.game.credits += job["reward"]
            elif job.get("purpose") == "artifact_trade":
                reservation = self.radio_reservations.get(job.get("contract_id"))
                artifact = reservation.get("artifact", {}) if reservation else {}
                catalog = ARTIFACT_TYPES.get(artifact.get("category"))
                if reservation and catalog:
                    job["reward"] = catalog["base_value"]
                    self.game.credits += job["reward"]
            else:
                job["reward"] = max(0, min(25, reward,
                                            math.ceil(len(payload) / 64)))
                self.game.credits += job["reward"]
            self.radio_contacts.setdefault(envelope["f"], time.time())
            contracts = radio_exchange.read_contracts(envelope.get("c", []), envelope["f"])
            if job.get("purpose") == "delivery":
                remote_contracts = self.radio_contracts.setdefault(envelope["f"], [])
                for existing in remote_contracts:
                    if existing["id"] == job.get("contract_id"):
                        existing["status"] = "fulfilled"
                known_ids = {c["id"] for c in remote_contracts}
                remote_contracts.extend(c for c in contracts if c["id"] not in known_ids)
            elif contracts:
                self.radio_contracts[envelope["f"]] = contracts
            self.radio_resources[envelope["f"]] = {"richness": envelope.get("x"),
                "stock": envelope.get("s", []), "production": envelope.get("p", [])}
            if job.get("purpose") in ("delivery", "artifact_trade", "resource_gift"):
                reservation = self.radio_reservations.pop(job.get("contract_id"), None)
                if reservation:
                    job["settlement"] = ("fulfilled" if job.get("purpose") == "delivery" else
                                          "donated" if job.get("purpose") == "resource_gift" else "artifact sold")
                    if job.get("purpose") == "artifact_trade":
                        artifact_id = reservation.get("artifact", {}).get("id")
                        self.game.artifact_inventory.pop(artifact_id, None)
                        if artifact_id in self.game.artifact_history:
                            self.game.artifact_history[artifact_id]["status"] = "traded"
                # Only a verified partner ACK develops the signal officer;
                # simulated sector traffic never grants real-radio experience.
                self.game.award_crew_experience(job.get("ship_id"), "signal", 2)
            job["status"] = "delivered"
            job["completed_at"] = time.time()
        else:
            self._release_radio_reservation(job)
            job["status"] = "rejected"
            job["failure"] = "Receiver rejected the delivery; cargo was returned."
        ship = self.game.fleet.get(job.get("ship_id"), {})
        if ship.get("radio_mission") == job.get("id"):
            ship.pop("radio_mission", None)

    def _release_radio_reservation(self, job):
        reservation = self.radio_reservations.pop(job.get("contract_id"), None)
        if reservation:
            if reservation.get("purpose") == "artifact_trade":
                artifact = deepcopy(reservation.get("artifact", {}))
                if artifact.get("id"):
                    artifact["status"] = "held"
                    self.game.artifact_inventory[artifact["id"]] = artifact
                    if artifact["id"] in self.game.artifact_history:
                        self.game.artifact_history[artifact["id"]]["status"] = "held"
                return
            stock = self.game.export_warehouse
            for resource, amount in (reservation.get("goods") or
                    {reservation["good"]: reservation["quantity"]}).items():
                stock[resource] = stock.get(resource, 0) + amount

    def _sync_discovered_galaxies(self):
        """Direct stations get local NPC models, never remote ledger authority."""
        for station, profile in sorted(self.radio_resources.items()):
            if station == self.net.local_id or profile.get("via"):
                continue
            if station not in self.game.galaxies:
                self.game.galaxies[station] = {"name": f"{station} Galaxy",
                    "specialization": profile.get("richness", "unknown"), "ports": {}}
    def _navigation(self):
        self._sync_discovered_galaxies()
        direct = {station for station, profile in self.radio_resources.items()
                  if station != self.callsign and not profile.get("via")}
        neighbors = {station: {} for station in direct}
        parents = {}
        for target, profile in sorted(self.radio_resources.items()):
            parent = profile.get("via")
            if not parent or parent not in direct or target in (parent, self.callsign):
                continue
            kind = "direct" if target in direct else "reported"
            neighbors[parent][target] = {"id": target, "kind": kind,
                "reported_by": parent, "goodput_bps": 0,
                "provenance": "reported", "specialization": profile.get("richness")}
            if kind == "reported":
                parents.setdefault(target, set()).add(parent)
        galaxies = {}
        for key, world in self.game.galaxies.items():
            kind = "home" if key == "home" else "direct" if key in direct else None
            if key != "home" and kind is None:
                continue
            galaxies[key] = {"name": world["name"], "specialization": world["specialization"],
                "ports": [], "simulated": False,
                "station_id": self.net.local_id if key == "home" else key,
                "kind": kind, "provenance": "heard_over_radio" if kind == "direct" else "local",
                "reported_neighbors": [neighbors[key][station]
                    for station in sorted(neighbors.get(key, {}))]}
        return {"current_galaxy": self.game.ship.get("galaxy", "home"),
            "home_id": self.net.local_id,
            "galaxies": galaxies, "voyages": {},
            "reported_stations": [{"id": station, "reported_by": sorted(parents[station]),
                "kind": "reported", "travelable": False} for station in sorted(parents)
                if station not in self.game.galaxies]}

    def sync_clock(self, now=None):
        """Advance the local economy clock and radio deadlines."""
        now = time.time() if now is None else now
        self._expire_radio_transmissions(now)
        first = self.game.clock_epoch is None
        results = {"local": self.game.sync_utc(now)}
        local_arrival_due = any(ship.get("destination") and ship.get("arrival_at") is not None
                                and now >= ship["arrival_at"]
                                for ship in self.game.fleet.values())
        transit_encounter_due = any(ship.get("destination") and ship.get("flight_encounters") and
            ship["flight_encounters"][0].get("status") == "scheduled" and
            now >= ship["flight_encounters"][0].get("trigger_at", float("inf"))
            for ship in self.game.fleet.values())
        if local_arrival_due or transit_encounter_due:
            self.game._all_arrivals()
        if first or results["local"]["advanced"]:
            self.persist()
        elif local_arrival_due or transit_encounter_due:
            self.persist()
        return results

    def persist(self):
        radio_state = {"transmissions": self.radio_transmissions,
            "inbox": self.radio_inbox, "contacts": self.radio_contacts,
            "contracts": self.radio_contracts, "resources": self.radio_resources,
            "reservations": self.radio_reservations, "processed": self.radio_processed,
            "assemblies": self.radio_assemblies}
        radio_state["beacons"] = getattr(self, "radio_beacons", {})
        radio_state["beacon_last_tx"] = getattr(self, "beacon_last_tx", None)
        if self.radio_pending_replies:
            radio_state["pending_replies"] = self.radio_pending_replies
        self.game.radio_state = radio_state
        self.game.save(self.save)
        temporary = self.net_save.with_suffix(self.net_save.suffix + ".tmp")
        temporary.write_text(json.dumps(self.net.to_dict(), indent=2) + "\n")
        temporary.replace(self.net_save)

        temporary_radio = self.radio_save.with_suffix(self.radio_save.suffix + ".tmp")
        temporary_radio.write_text(json.dumps(radio_state, indent=2) + "\n")
        temporary_radio.replace(self.radio_save)

    def _expire_radio_transmissions(self, now=None):
        now = time.time() if now is None else now
        changed = False
        for job in self.radio_transmissions.values():
            if job.get("status") != "awaiting_ack" or now < job.get("timeout_at", now):
                continue
            if job.get("retry_due_at"):
                continue
            if (job.get("payload_hex") and
                    job.get("auto_retry_count", 0) < MAX_AUTO_RETRIES):
                delay = 15 * (job.get("auto_retry_count", 0) + 1)
                job["retry_due_at"] = now + delay
                job["timeout_at"] = now + delay + job.get("timeout_seconds", 180)
                job["recovery_error"] = "Waiting for a receipt; retransmission scheduled."
                changed = True
                continue
            job["status"] = "failed"
            job["failed_at"] = now
            ship_id = job.get("ship_id")
            if ship_id in self.game.fleet:
                job["ship_result"] = self.game.damage_ship(ship_id, 10, job["origin"])
            job["failure"] = "No receiver acknowledgment before timeout."
            changed = True
        if changed:
            self.persist()

    def state(self):
        self._sync_discovered_galaxies()
        self.sync_clock()
        game_state = self.game.to_dict()
        game_state["contracts"] = {}  # Archived simulated NPC freight is not live demand.
        game_state.pop("radio_state", None)  # Radio ledgers have their own bounded projection.
        return {"game": game_state, "save_id": self.save_id, "network": {"local_id": self.callsign},
                "equipment_cargo_space": EQUIPMENT_CARGO_SPACE,
                "navigation": self._navigation(),
                "ship_classes": deepcopy(list(getattr(modems, "SHIPS", ()))),
                "story_objective": self.game.story_objective(),
                "haven_upgrades": {key: self.game.haven_upgrade_quote(key)
                                   for key in HAVEN_FACILITIES},
                "loan_plans": {key: self.game.loan_quote(key) for key in LOAN_PLANS},
                "haven_warehouse_capacity": self.game.haven_warehouse_capacity(),
                "crew_candidates": self.game.crew_candidates(),
                "crew_roles": deepcopy(CREW_ROLES),
                "captain_deal_quotes": {key: self.game.captain_deal_quote(key)
                                        for key in self.game.npc_captains},
                # Fictional sector signals are a local gameplay projection;
                # never pass these through the Data2G send/receive path.
                "dispatch_signals": [{**deepcopy(event), "transport": "local_simulation",
                    "transmit": False} for event in self.game.active_sector_events()],
                "modem_catalog": deepcopy(self.modem_catalog),
                "radio_unlocks": list(self.game.radio_unlocks),
                "radio_profiles": ([{"id": profile, "label": label}
                    for profile, label in modems.SURVEY_BEACON_PROFILES] + [
                    {"id": profile, "label": profile.upper().replace("-", " · ")}
                    for profile in modems.STARTING_RADIO_PROFILES]),
                "radio_mode_profiles": {mode.get("mode_id"): modems.radio_profile_key(mode)
                    for mode in self.modem_catalog.get("modes", [])
                    if mode.get("mode_id")},
                "radio_transmissions": [{**{key: deepcopy(value) for key, value in job.items()
                                            if key not in ("payload_hex", "repair_indices")},
                    "remaining_seconds": max(0, math.ceil(job["timeout_at"] - time.time()))
                    if job.get("status") == "awaiting_ack" else 0}
                    for job in self.radio_transmissions.values()],
                "radio_inbox": deepcopy(self.radio_inbox[-20:]),
                "radio_beacons": deepcopy(getattr(self, "radio_beacons", {})),
                "beacon_last_tx": deepcopy(getattr(self, "beacon_last_tx", None)),
                "radio_contacts": deepcopy(self.radio_contacts),
                "radio_contracts": deepcopy(self.radio_contracts),
                "radio_resources": deepcopy(self.radio_resources),
                "radio_reservations": deepcopy(self.radio_reservations),
                "artifact_catalog": deepcopy(ARTIFACT_CATALOG),
                "radio_listener_status": self.radio_listener_status,
                "rig": deepcopy(getattr(self, "rig_status", {
                    "status": "disabled", "frequency_hz": None, "band": None})),
                "radio_pending_receipts": len(self.radio_pending_replies),
                "clock": {"epoch": self.game.clock_epoch,
                          "tick_seconds": self.game.tick_seconds,
                          "next_boundary_utc": (self.game.clock_epoch + 1) * self.game.tick_seconds},
                "asteroid_field": {"blocked_port": self.game.blocked_port(),
                    "seconds_remaining": max(1, int((self.game.tick_seconds * (2 - self.game.tick % 2)) - (time.time() % self.game.tick_seconds)))},
                "route_parents": {port: self.game.route_parent(port)
                                  for port in self.game.ports if port != "Haven"},
                "route_gates": {port: self.game.route_status(self.game.ports[port].get("map_parent"), port)
                                for port in self.game.ports if self.game.ports[port].get("map_parent")},
                "route_paths": {port: self.game.route_status(self.game.location, port)
                                for port in self.game.ports if port != self.game.location},
                "route_hazards": {port: self.game.route_risk(self.game.location, port)
                                  for port in self.game.ports if port != self.game.location},
                "chart_hazards": {port: self.game.route_risk(self.game.ports[port].get("map_parent"), port)
                                  for port in self.game.ports if self.game.ports[port].get("map_parent")},
                "carrier_hazards": {f"{carrier}|{planet}": self.game.route_risk(carrier, planet)
                    for carrier, site in self.game.ports.items()
                    if site.get("entity_type") == "carrier"
                    for planet in site.get("linked_planets", [])},
                "goods": GOODS,
                "rare_goods": sorted(RARE),
                "prices": {port: {good: {"buy": self.game.price(port, good, "buy"),
                                            "sell": self.game.price(port, good, "sell")}
                                  for good in GOODS} for port in self.game.ports}}

    def execute(self, request):
        action = request.get("action")
        if action in ("radio_beacon_preview", "radio_beacon_transmit"):
            good = str(request.get("good", ""))
            contract_id = str(request.get("contract_id", ""))
            payload, decoded = self._beacon_payload(good, contract_id)
            if action == "radio_beacon_preview":
                result = {**decoded, "payload_hex": payload.hex(), "status": "preview"}
            else:
                mode_id = str(request.get("mode_id", ""))
                if not re.fullmatch(r"[A-Za-z0-9._+/-]{1,64}", mode_id):
                    raise GameError("choose an eligible live Data2G mode")
                host, command_port, kiss_port, group = self.data2g
                with Data2GClient(host, command_port, kiss_port) as modem:
                    modem.open_group(group, self.callsign)
                    available = [vars(mode) for mode in modem.modes()]
                    modes = self._eligible_radio_modes(available)
                    selected = next((mode for mode in modes if mode["mode_id"] == mode_id), None)
                    if (not selected or selected["bytes_per_codeword"] *
                            selected["max_codewords"] < len(payload)):
                        raise GameError("selected mode cannot carry this compact beacon")
                    self._send_radio_frames(modem, payload, mode_id,
                                            int(self.game.ship.get("modem_tier", 0)))
                self.beacon_last_tx = {"sent_at": time.time(), "good": good,
                                       "contract_id": contract_id, "bytes": len(payload)}
                result = {**decoded, "status": "sent", "mode_id": mode_id}
        elif action == "radio_status":
            host, command_port, kiss_port, group = self.data2g
            with Data2GClient(host, command_port, kiss_port) as modem:
                advertised = [vars(mode) for mode in modem.modes()]
            modes = self._eligible_radio_modes(advertised)
            result = {"connected": True, "host": host, "group": group, "modes": modes}
        elif action == "abort_radio_mission":
            job_id = str(request.get("job_id", ""))
            job = self.radio_transmissions.get(job_id)
            if not job or job.get("status") != "awaiting_ack":
                raise GameError("there is no active radio mission to abort")
            job["status"] = "cancelled"
            job["cancelled_at"] = time.time()
            job["recovery_error"] = "Retries stopped by captain; frames already sent may still receive a reply."
            ship = self.game.fleet.get(job.get("ship_id"), {})
            if ship.get("radio_mission") == job_id:
                ship.pop("radio_mission", None)
            result = {"job_id": job_id, "status": "cancelled",
                      "late_receipt_possible": True,
                      "cargo_reserved": bool(job.get("purpose") in ("delivery", "artifact_trade", "resource_gift") and
                                              job.get("contract_id") in self.radio_reservations)}
        elif action in ("radio_preview", "radio_transmit"):
            station = str(request.get("station", ""))
            contract_id = str(request.get("contract_id", ""))
            purpose = str(request.get("purpose", "contact" if station not in self.radio_contacts else "delivery"))
            self._ensure_radio_contracts()
            reservation = self.radio_reservations.get(contract_id)
            if purpose == "contact":
                if not self._valid_station(station) or len(station) > 10 or station == self.callsign:
                    raise GameError("Enter another station's valid callsign for first contact.")
                if station in self.radio_contacts:
                    raise GameError("First contact is already complete for this station.")
                message = {"v": 1, "t": "contact", "i": uuid.uuid4().hex[:16],
                    "f": self.callsign, "d": station, **self._radio_wire_profile(),
                    "c": radio_exchange.wire_contracts(self.radio_contracts[self.callsign]),
                    "n": self._radio_neighbors(exclude=station)}
            elif purpose == "delivery":
                contract = next((c for c in self.radio_contracts.get(station, [])
                                 if c["id"] == contract_id and c.get("status", "open") == "open"), None)
                if station not in self.radio_contacts or not contract:
                    raise GameError("Complete first contact and select an active partner contract.")
                if not reservation or reservation.get("station") != station:
                    raise GameError("Prepare the requested goods before transmitting.")
                message = {"v": 1, "t": "delivery", "i": reservation["message_id"],
                    "f": self.callsign, "d": station, "c": contract_id,
                    "g": contract["good"], "q": contract["quantity"],
                    "n": self._radio_neighbors(exclude=station,
                        limit=8 if contract["quantity"] >= 5 else 1,
                        detail=contract["quantity"] >= 5)}
                if contract.get("requirements"):
                    message["m"] = [[good, count] for good, count in
                                    radio_exchange.contract_requirements(contract).items()]
            elif purpose == "artifact_trade":
                if (station not in self.radio_contacts or not reservation or
                        reservation.get("purpose") != "artifact_trade" or
                        reservation.get("station") != station):
                    raise GameError("Reserve an artifact for this contacted station first.")
                artifact = reservation["artifact"]
                message = {"v": 1, "t": "delivery", "i": reservation["message_id"],
                    "f": self.callsign, "d": station, "c": contract_id,
                    "g": "artifact", "q": 1, "a": artifact,
                    "n": self._radio_neighbors(exclude=station)}
            elif purpose == "resource_gift":
                if (station not in self.radio_contacts or not reservation or
                        reservation.get("purpose") != "resource_gift" or
                        reservation.get("station") != station):
                    raise GameError("Reserve a resource donation for this contacted station first.")
                message = {"v": 1, "t": "delivery", "i": reservation["message_id"],
                    "f": self.callsign, "d": station, "c": contract_id,
                    "g": reservation["good"], "q": reservation["quantity"],
                    "gift": True, "n": self._radio_neighbors(exclude=station)}
            else:
                raise GameError("Choose first contact or a contracted delivery.")
            if purpose == "delivery" and reservation.get("payload_hex"):
                try:
                    payload = bytes.fromhex(reservation["payload_hex"])
                except ValueError as exc:
                    raise GameError("The staged radio message is damaged.") from exc
                cached = radio_exchange.decode(payload)
                if (not cached or cached.get("i") != reservation["message_id"] or
                        cached.get("d") != station or cached.get("c") != contract_id or
                        cached.get("t") != "delivery"):
                    raise GameError("The staged radio message does not match this contract.")
                message = cached
            else:
                payload = radio_exchange.encode_message(message)
            packets = radio_exchange.frames(payload)
            digest = hashlib.sha256(payload).hexdigest()[:12]
            mode_id = str(request.get("mode_id", ""))
            if not re.fullmatch(r"[A-Za-z0-9._+/-]{1,64}", mode_id):
                raise GameError("Choose a valid live modem mode.")
            if action == "radio_preview":
                result = {"bytes": len(payload), "digest": digest, "mode_id": mode_id,
                          "payload": payload.decode("utf-8"), "frames": len(packets),
                          "contract_id": contract_id,
                          "purpose": purpose}
            else:
                ship = self.game.ship
                if (not self.game.active_ship_id or ship.get("condition", 0) < 10 or
                        ship.get("radio_mission")):
                    raise GameError("Select a ready ship with at least 10 condition and no active transmission.")
                if ship.get("destination"):
                    raise GameError("Wait for the selected ship to dock before transmitting.")
                if purpose in ("delivery", "artifact_trade", "resource_gift"):
                    if ship.get("location") != "Haven":
                        raise GameError("Radio cargo deliveries depart from your Haven home base.")
                if purpose == "delivery":
                    self._verify_contract_band(contract.get("band"))
                if purpose == "delivery" and not reservation.get("payload_hex"):
                    reservation["payload_hex"] = payload.hex()
                    self.persist()
                host, command_port, kiss_port, group = self.data2g
                with Data2GClient(host, command_port, kiss_port) as modem:
                    modem.open_group(group, self.callsign)
                    available = [vars(mode) for mode in modem.modes()]
                    selected = next((mode for mode in self._eligible_radio_modes(available)
                                     if mode["mode_id"] == mode_id), None)
                    if selected is None:
                        raise GameError("That mode is no longer advertised by Data2G.")
                    capacity = selected["bytes_per_codeword"] * selected["max_codewords"]
                    if any(len(packet) > capacity for packet in packets):
                        raise GameError("Choose a mode that can carry these radio frames.")
                    self._send_radio_frames(modem, payload, mode_id,
                                            int(self.game.ship.get("modem_tier", 0)))
                ship = self.game.ship
                prior_job = next((j for j in self.radio_transmissions.values()
                                  if j.get("message_id") == message["i"] and
                                  j.get("status") == "failed"), None)
                job_id = prior_job["id"] if prior_job else "radio-" + uuid.uuid4().hex[:12]
                airtime = sum(math.ceil(len(packet) / selected["bytes_per_codeword"])
                              * selected["seconds_max"] for packet in packets)
                timeout_seconds = max(180, math.ceil(airtime * 2 + 90))
                started = time.time()
                ship["radio_mission"] = job_id
                job = {"id": job_id, "message_id": message["i"], "contract_id": contract_id,
                       "payload_hash": hashlib.sha256(payload).hexdigest()[:16], "purpose": purpose,
                       "payload_hex": payload.hex(), "auto_retry_count": 0,
                       "mode_id": mode_id, "ship_id": ship["id"],
                       "band": contract.get("band") if purpose == "delivery" else None,
                       "origin": ship["location"],
                       "destination": station,
                       "bytes": len(payload), "frames": len(packets),
                       "intel_reports": len(message.get("n", [])),
                       "digest": digest, "status": "awaiting_ack",
                       "started_at": started, "timeout_at": started + timeout_seconds,
                       "timeout_seconds": timeout_seconds}
                if prior_job:
                    job["retry_count"] = int(prior_job.get("retry_count", 0)) + 1
                self.radio_transmissions[job_id] = job
                result = {"bytes": len(payload), "digest": digest, "mode_id": mode_id,
                          "frames": len(packets),
                          "status": "queued_to_modem", "purpose": purpose,
                          "receiver_acknowledged": False, "job_id": job_id,
                          "timeout_seconds": timeout_seconds}
        elif action == "simulate":
            raise GameError("Simulated radio transfers are disabled. Use a live Data2G frame.")
        elif action == "exchange_reserve":
            station, contract_id = str(request.get("station", "")), str(request.get("contract_id", ""))
            contract = next((c for c in self.radio_contracts.get(station, [])
                             if c["id"] == contract_id and c.get("status", "open") == "open"), None)
            if station not in self.radio_contacts or not contract:
                raise GameError("Complete first contact and choose an active partner contract.")
            if contract_id in self.radio_reservations:
                raise GameError("This contract already has goods reserved.")
            if self.game.ship.get("location") != "Haven" or self.game.ship.get("destination"):
                raise GameError("Return to Haven to prepare a radio delivery.")
            goods = radio_exchange.contract_requirements(contract)
            if any(self.game.export_warehouse.get(good, 0) < quantity
                   for good, quantity in goods.items()):
                missing = [f"{good} {self.game.export_warehouse.get(good, 0)}/{quantity}"
                           for good, quantity in goods.items()
                           if self.game.export_warehouse.get(good, 0) < quantity]
                raise GameError("Complete the Haven export manifest first: " + ", ".join(missing))
            for good, quantity in goods.items():
                self.game.export_warehouse[good] -= quantity
            self.radio_reservations[contract_id] = {"station": station,
                "good": contract["good"], "quantity": contract["quantity"],
                "goods": deepcopy(goods), "message_id": uuid.uuid4().hex[:16],
                "prepared_at": time.time()}
            result = {"contract_id": contract_id, "goods": deepcopy(goods), "status": "reserved"}
        elif action == "radio_artifact_reserve":
            station = str(request.get("station", ""))
            artifact_id = str(request.get("artifact_id", ""))
            artifact = self.game.artifact_inventory.get(artifact_id)
            if station not in self.radio_contacts:
                raise GameError("Complete first contact before trading artifacts.")
            if not artifact or artifact.get("status") != "held":
                raise GameError("That artifact is not available to trade.")
            if self.game.ship.get("location") != "Haven" or self.game.ship.get("destination"):
                raise GameError("Return to Haven to prepare an artifact trade.")
            reservation_id = f"artifact:{station}:{artifact_id}"
            if reservation_id in self.radio_reservations:
                raise GameError("This artifact already has a pending reservation.")
            self.game.artifact_inventory.pop(artifact_id)
            artifact["status"] = "reserved"
            self.game.artifact_history[artifact_id]["status"] = "reserved"
            self.radio_reservations[reservation_id] = {"station": station,
                "purpose": "artifact_trade", "artifact": deepcopy(artifact),
                "message_id": uuid.uuid4().hex[:16], "prepared_at": time.time()}
            result = {"contract_id": reservation_id, "title": artifact["title"],
                "base_value": artifact["base_value"], "status": "reserved"}
        elif action == "radio_gift_reserve":
            station = str(request.get("station", ""))
            good = str(request.get("good", ""))
            amount = request.get("amount")
            if station not in self.radio_contacts:
                raise GameError("Complete first contact before sending a charitable delivery.")
            if good not in GOODS or type(amount) is not int or amount < 1 or amount > 10000:
                raise GameError("Choose a valid resource and quantity to donate.")
            if self.game.location != "Haven" or self.game.ship.get("destination"):
                raise GameError("Return to Haven to prepare a charitable delivery.")
            if self.game.export_warehouse.get(good, 0) < amount:
                raise GameError("Stage the donated resource in the Haven export warehouse first.")
            reservation_id = f"gift:{station}:{uuid.uuid4().hex[:8]}"
            self.game.export_warehouse[good] -= amount
            self.radio_reservations[reservation_id] = {"station": station,
                "purpose": "resource_gift", "good": good, "quantity": amount,
                "message_id": uuid.uuid4().hex[:16], "prepared_at": time.time()}
            result = {"contract_id": reservation_id, "good": good,
                "quantity": amount, "status": "reserved"}
        elif action in ("discover", "dispatch_contract", "accept_contract",
                        "cancel_contract", "reclaim_contract",
                        "exchange_dispatch", "exchange_settle", "exchange_cancel",
                        "exchange_queue", "exchange_modem_upgrade",
                        "exchange_purchase_ship", "exchange_hard_mode", "mail_station"):
            raise GameError("Shared-world simulated trade has been removed. Use an exchanged station contract in Comms.")
        elif action == "sync_clock":
            result = self.sync_clock()
        elif action == "wait":
            raise GameError("manual economy ticks are disabled in real-time web mode")
        elif action == "jump":
            raise GameError("Ships travel only within their galaxy. Use Comms for partner-station deliveries.")
        else:
            result = self.game.command(str(request["id"]), str(action),
                                       **request.get("args", {}))
        self.persist()
        return result


def serve(host="127.0.0.1", port=8765, save="galaxy.json", seed=42, callsign="AG7SU",
          data2g_host="127.0.0.1", command_port=8300, kiss_port=8100, group="TRADENET",
          rigctld_host=None, rigctld_port=4532):
    app = App(Path(save), seed, callsign, data2g_host, command_port, kiss_port,
              group, rigctld_host, rigctld_port)

    class Handler(BaseHTTPRequestHandler):
        def respond(self, status, obj):
            data = json.dumps(obj).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/api/state":
                with app.lock:
                    self.respond(200, app.state())
                return
            assets = {"/": ("index.html", "text/html; charset=utf-8"),
                      "/index.html": ("index.html", "text/html; charset=utf-8"),
                      "/ships.svg": ("ships.svg", "image/svg+xml"),
                      "/icon.svg": ("icon.svg", "image/svg+xml"),
                      "/icon-192.png": ("icon-192.png", "image/png"),
                      "/icon-512.png": ("icon-512.png", "image/png"),
                      "/apple-touch-icon.png": ("apple-touch-icon.png", "image/png"),
                      "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json")}
            planet_sprites = ("temperate", "desert", "ringed", "ice", "volcanic", "lush")
            assets.update({f"/assets/planets/{name}-{variant}.png":
                           (f"assets/planets/{name}-{variant}.png", "image/png")
                           for name in planet_sprites for variant in range(16)})
            if self.path not in assets:
                self.send_error(404)
                return
            filename, content_type = assets[self.path]
            try:
                data = (WEB / filename).read_bytes()
            except FileNotFoundError:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if self.path != "/api/action":
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 32768:
                    raise ValueError("invalid request size")
                request = json.loads(self.rfile.read(length))
                with app.lock:
                    result = app.execute(request)
                    self.respond(200, {"result": result, "state": app.state()})
            except (ValueError, GameError, Data2GError, OSError, KeyError, TypeError) as exc:
                self.respond(400, {"error": str(exc)})

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Trade Net command deck: http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--save", default="galaxy.json")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--callsign", default="AG7SU")
    parser.add_argument("--data2g-host", default="127.0.0.1")
    parser.add_argument("--command-port", type=int, default=8300)
    parser.add_argument("--kiss-port", type=int, default=8100)
    parser.add_argument("--group", default="TRADENET")
    parser.add_argument("--rigctld-host", help="Hamlib rigctld hostname/IP (read-only, optional)")
    parser.add_argument("--rigctld-port", type=int, default=4532)
    args = parser.parse_args()
    serve(**vars(args))


if __name__ == "__main__":
    main()
