"""Dependency-free local preview web server. Never transmits RF."""

from __future__ import annotations

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .engine import Game, GameError, GOODS
from .network import Network
from .contracts import seed_offers, dispatch, manifest_payload
from .federation import Federation
from .mail import MailNetwork

WEB = Path(__file__).with_name("web")


class App:
    def __init__(self, save: Path, seed: int, callsign: str):
        self.save = save
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

    def sync_clock(self, now=None):
        """All local/remote worlds share absolute UTC tick boundaries."""
        now = time.time() if now is None else now
        first = self.game.clock_epoch is None or any(w.clock_epoch is None for w in self.federation.worlds.values())
        results = {"local": self.game.sync_utc(now)}
        for station, world in self.federation.worlds.items():
            results[station] = world.sync_utc(now)
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
        self.sync_clock()
        return {"game": self.game.to_dict(), "network": self.net.to_dict(),
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
        elif action == "discover":
            self.net.discover(str(request["peer"]), request.get("neighbors", []))
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
                                                 weight=str(request.get("weight", "light")))
        elif action == "exchange_modem_upgrade":
            seller = next(iter(self.federation.worlds.values()))
            result = seller.command(str(request["id"]), "buy_ship")
        elif action == "mail_step":
            events = self.mail.step(loss=float(request.get("loss", .15)),
                                    budget_frames=int(request.get("budget_frames", 16)))
            result = {"mail_events": events,
                      "trade_changes": self.federation.sync_mail(self.mail)}
        elif action == "mail_station":
            station = str(request["station"])
            self.mail.set_online(station, bool(request["online"]))
            result = {"station": station, "online": self.mail.stations[station]["online"]}
        elif action == "sync_clock":
            result = self.sync_clock()
        elif action == "wait":
            raise GameError("manual economy ticks are disabled in real-time web mode")
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
            if self.path not in ("/", "/index.html"):
                self.send_error(404)
                return
            data = (WEB / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
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
