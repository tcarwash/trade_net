"""Dependency-free local preview web server. Never transmits RF."""

from __future__ import annotations

import argparse
import hashlib
import json
import threading
import time
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .engine import Game, GameError, GOODS
from .network import Network
from .contracts import seed_offers, dispatch, manifest_payload
from .federation import Federation
from .mail import MailNetwork
from .modems import TIERS
from . import modems

WEB = Path(__file__).with_name("web")
MODEM_CATALOG = Path(__file__).with_name("modem-modes.json")


class App:
    def __init__(self, save: Path, seed: int, callsign: str):
        self.save = save
        try:
            self.modem_catalog = json.loads(MODEM_CATALOG.read_text(encoding="utf-8"))
            if not isinstance(self.modem_catalog, dict):
                raise ValueError("modem catalog must be an envelope")
        except (OSError, ValueError):
            self.modem_catalog = {"modes": [], "provenance": "unavailable"}
        self.net_save = save.with_suffix(".network.json")
        self.game = Game.load(save) if save.exists() else Game.new(seed)
        self.net = (Network.from_dict(json.loads(self.net_save.read_text()))
                    if self.net_save.exists() else Network(callsign))
        self.federation_save = save.with_suffix(".federation.json")
        self.federation = (Federation.load(self.federation_save)
                           if self.federation_save.exists()
                           else Federation.demo(local_id=callsign, seed=seed))
        self.federation.network = self.net
        self.mail_save = save.with_suffix(".mail.json")
        self.mail = (MailNetwork.load(self.mail_save)
                     if self.mail_save.exists() else MailNetwork())
        for station in self.federation.worlds:
            self.mail.add_station(station)
            if station != self.net.local_id:
                world = self.federation.worlds[station]
                self.game.galaxies.setdefault(station, {"name": world.name,
                    "specialization": world.specialization, "ports": deepcopy(world.ports)})
        self._sync_discovered_galaxies()
        self._recover_voyages()
        self._sync_voyages()
        if not self.federation.trades:
            local, remote = list(self.federation.worlds)
            self.federation.propose("DEMO-001", local, remote,
                                    self.federation.worlds[local].specialization,
                                    2, 220, payload_bytes=1024)
        self.lock = threading.RLock()
        seed_offers(self.game)
        for contract in self.game.contracts.values():
            contract["payload_bytes"] = len(manifest_payload(contract))
        self.persist()
        self.sync_clock()

    def _sync_discovered_galaxies(self):
        """Direct stations get local NPC models, never remote ledger authority."""
        for station, peer in sorted(self.net.peers.items()):
            if station == self.net.local_id or peer.get("kind") != "direct":
                continue
            if station not in self.game.galaxies:
                seed = int.from_bytes(hashlib.sha256(station.encode("utf-8")).digest(), "big")
                world = Game.new(seed, name=f"{station} Galaxy")
                self.game.galaxies.setdefault(station, {"name": world.name,
                    "specialization": world.specialization, "ports": deepcopy(world.ports)})
            if station not in self.mail.stations:
                self.mail.add_station(station)

    def _voyage_route(self, voyage):
        return [self.net.local_id if key == "home" else key
                for key in (voyage["origin_galaxy"], voyage["galaxy"])]

    def _recover_voyages(self):
        """The ship's durable departure is the outbox source of truth."""
        for ship in self.game.fleet.values():
            voyage = ship.get("voyage")
            if not voyage or voyage["id"] in self.mail.messages:
                continue
            manifest = ship.setdefault("voyage_manifest", {"type": "voyage", **voyage,
                "ship_id": ship["id"], "cargo": deepcopy(ship["cargo"])})
            tier = TIERS[ship.get("modem_tier", 0)]
            self.mail.enqueue(voyage["id"], self._voyage_route(voyage),
                json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode(),
                frames_per_tick=ship.get("frames_per_tick", tier["frames_per_tick"]),
                # Mail models the three existing transport tiers; a named hull
                # can throttle its frames without claiming a real PHY mode.
                bandwidth_hz=tier["max_bandwidth_hz"])

    def _sync_voyages(self):
        changes = []
        for ship in list(self.game.fleet.values()):
            voyage = ship.get("voyage")
            if voyage and self.mail.messages.get(voyage["id"], {}).get("status") == "acknowledged":
                changes.append(self.game.complete_voyage(voyage["id"]))
                ship.pop("voyage_manifest", None)
        return changes

    def _navigation(self):
        self._sync_discovered_galaxies()
        direct = {station for station, peer in self.net.peers.items()
                  if peer.get("kind") == "direct" and station != self.net.local_id}
        neighbors = {station: {} for station in direct}
        parents = {station: set() for station, peer in self.net.peers.items()
                   if peer.get("kind") == "reported" and station != self.net.local_id}
        # Only explicit advertisements establish second-hop provenance. Do not
        # infer a mesh from the peer list, observed links, or the demo worlds.
        for _, link in sorted(self.net.links.items()):
            parent, target = link.get("reported_by"), link.get("destination")
            if (link.get("kind") != "reported" or parent not in direct or
                    link.get("source") != parent or
                    not target or target in (parent, self.net.local_id)):
                continue
            kind = "direct" if target in direct else "reported"
            neighbors[parent][target] = {"id": target, "kind": kind,
                "reported_by": parent, "goodput_bps": link.get("goodput_bps", 0),
                "provenance": "reported"}
            if kind == "reported":
                parents.setdefault(target, set()).add(parent)
        galaxies = {}
        for key, world in self.game.galaxies.items():
            kind = ("home" if key == "home" else
                    "demo" if key in self.federation.worlds else "direct")
            galaxies[key] = {"name": world["name"], "specialization": world["specialization"],
                "ports": list(world["ports"]), "simulated": True,
                "station_id": self.net.local_id if key == "home" else key,
                "kind": kind, "provenance": "demo" if kind == "demo" else "local_model",
                "reported_neighbors": [neighbors[key][station]
                    for station in sorted(neighbors.get(key, {}))]}
        voyages = {}
        for ship_id, ship in self.game.fleet.items():
            voyage = ship.get("voyage")
            if not voyage:
                continue
            message = self.mail.messages.get(voyage["id"], {})
            status = message.get("status", "queued")
            count = max(1, (len(message.get("payload_hex", "")) // 2 + self.mail.frame_bytes - 1) // self.mail.frame_bytes)
            progress = min(49, int(50 * len(message.get("received_parts", [])) / count))
            if status == "delivered":
                status, progress = "awaiting_ack", 75
            ack = self.mail.messages.get("ack:" + voyage["id"], {})
            if status == "expired" or ack.get("status") == "expired":
                status = "pending_reconciliation"
            voyages[ship_id] = {**voyage, "status": status, "progress": progress,
                "online": all(self.mail.stations[p]["online"] for p in self._voyage_route(voyage))}
        return {"current_galaxy": self.game.ship.get("galaxy", "home"),
            "home_id": self.net.local_id,
            "galaxies": galaxies, "voyages": voyages,
            "reported_stations": [{"id": station, "reported_by": sorted(parents[station]),
                "kind": "reported", "travelable": False} for station in sorted(parents)
                if station not in self.game.galaxies]}

    def sync_clock(self, now=None):
        """All local/remote worlds share absolute UTC tick boundaries."""
        now = time.time() if now is None else now
        first = self.game.clock_epoch is None or any(w.clock_epoch is None for w in self.federation.worlds.values())
        results = {"local": self.game.sync_utc(now)}
        for station, world in self.federation.worlds.items():
            results[station] = world.sync_utc(now)
        # One simulation opportunity per economy tick, not per browser poll.
        # Bound offline work so a years-old save cannot stall the web server.
        for _ in range(min(results["local"]["advanced"], 500)):
            if not any(s.get("voyage") for s in self.game.fleet.values()):
                break
            self._recover_voyages()
            self.mail.step(loss=.15, budget_frames=16)
            self._sync_voyages()
            self.federation.sync_mail(self.mail)
        if first or any(r["advanced"] for r in results.values()):
            self.persist()
        return results

    def persist(self):
        self.game.save(self.save)
        temporary = self.net_save.with_suffix(self.net_save.suffix + ".tmp")
        temporary.write_text(json.dumps(self.net.to_dict(), indent=2) + "\n")
        temporary.replace(self.net_save)
        self.federation.save(self.federation_save)
        self.mail.save(self.mail_save)

    def state(self):
        self._sync_discovered_galaxies()
        self.sync_clock()
        return {"game": self.game.to_dict(), "network": self.net.to_dict(),
                "navigation": self._navigation(),
                "ship_classes": deepcopy(list(getattr(modems, "SHIPS", ()))),
                "modem_catalog": deepcopy(self.modem_catalog),
                "federation": self.federation.to_dict(),
                "mail": self.mail.to_dict(),
                "clock": {"epoch": self.game.clock_epoch,
                          "tick_seconds": self.game.tick_seconds,
                          "next_boundary_utc": (self.game.clock_epoch + 1) * self.game.tick_seconds},
                "goods": GOODS,
                "prices": {port: {good: {"buy": self.game.price(port, good, "buy"),
                                            "sell": self.game.price(port, good, "sell")}
                                  for good in GOODS} for port in self.game.ports}}

    def execute(self, request):
        action = request.get("action")
        if action == "simulate":
            result = self.net.simulate(str(request["peer"]), int(request["bytes"]),
                                       float(request.get("loss", .15)),
                                       neighbors=request.get("neighbors", []))
            self._sync_discovered_galaxies()
        elif action == "discover":
            self.net.discover(str(request["peer"]), request.get("neighbors", []))
            self._sync_discovered_galaxies()
            result = {"discovered": request["peer"]}
        elif action == "dispatch_contract":
            result = dispatch(self.game, self.net, str(request["contract_id"]),
                              route=request.get("route"),
                              loss=float(request.get("loss", .15)))
        elif action == "exchange_reserve":
            result = self.federation.reserve(str(request["trade_id"]))
        elif action == "exchange_dispatch":
            result = self.federation.dispatch(str(request["trade_id"]),
                                              loss=float(request.get("loss", .15)),
                                              route=request.get("route"))
        elif action == "exchange_settle":
            result = self.federation.settle(str(request["trade_id"]))
        elif action == "exchange_cancel":
            result = self.federation.cancel(str(request["trade_id"]))
        elif action == "exchange_queue":
            result = self.federation.queue_trade(self.mail, str(request["trade_id"]),
                                                 route=request.get("route"),
                                                 weight=str(request.get("weight", "light")),
                                                 ship_id=request.get("ship_id"))
        elif action == "exchange_modem_upgrade":
            seller = next(iter(self.federation.worlds.values()))
            result = seller.command(str(request["id"]), "buy_ship")
        elif action == "exchange_purchase_ship":
            seller = next(iter(self.federation.worlds.values()))
            result = seller.command(str(request["id"]), "purchase_ship",
                                    tier=int(request.get("tier", 0)))
        elif action == "exchange_hard_mode":
            seller = next(iter(self.federation.worlds.values()))
            result = seller.command(str(request["id"]), "set_hard_mode", enabled=True)
        elif action == "mail_step":
            events = self.mail.step(loss=float(request.get("loss", .15)),
                                    budget_frames=int(request.get("budget_frames", 16)))
            result = {"mail_events": events,
                      "voyage_changes": self._sync_voyages(),
                      "trade_changes": self.federation.sync_mail(self.mail)}
        elif action == "mail_station":
            station = str(request["station"])
            self.mail.set_online(station, bool(request["online"]))
            result = {"station": station, "online": self.mail.stations[station]["online"]}
        elif action == "sync_clock":
            result = self.sync_clock()
        elif action == "wait":
            raise GameError("manual economy ticks are disabled in real-time web mode")
        elif action == "jump":
            command_id = str(request["id"])
            # Validate before any mutation, then settle old clock time before
            # launch: an idle browser must not spend pre-launch ticks on RF.
            Game.from_dict(self.game.to_dict()).command(command_id, "jump",
                **request.get("args", {}), voyage_id="voyage:" + command_id)
            self.sync_clock()
            result = self.game.command(command_id, "jump", **request.get("args", {}),
                                       voyage_id="voyage:" + command_id)
            # Persist departure before enqueue: restart can rebuild its outbox.
            self.game.save(self.save)
            self._recover_voyages()
        else:
            result = self.game.command(str(request["id"]), str(action),
                                       **request.get("args", {}))
        self.persist()
        return result


def serve(host="127.0.0.1", port=8765, save="galaxy.json", seed=42, callsign="AG7SU"):
    app = App(Path(save), seed, callsign)

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
                      "/ships.svg": ("ships.svg", "image/svg+xml")}
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
            except (ValueError, GameError, KeyError, TypeError) as exc:
                self.respond(400, {"error": str(exc)})

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Trade Net preview: http://{host}:{port} (simulator only)")
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
    args = parser.parse_args()
    serve(**vars(args))


if __name__ == "__main__":
    main()
