"""Dependency-free local preview web server. Never transmits RF."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .engine import Game, GameError, GOODS
from .network import Network

WEB = Path(__file__).with_name("web")


class App:
    def __init__(self, save: Path, seed: int, callsign: str):
        self.save = save
        self.net_save = save.with_suffix(".network.json")
        self.game = Game.load(save) if save.exists() else Game.new(seed)
        self.net = (Network.from_dict(json.loads(self.net_save.read_text()))
                    if self.net_save.exists() else Network(callsign))

    def persist(self):
        self.game.save(self.save)
        temporary = self.net_save.with_suffix(self.net_save.suffix + ".tmp")
        temporary.write_text(json.dumps(self.net.to_dict(), indent=2) + "\n")
        temporary.replace(self.net_save)

    def state(self):
        return {"game": self.game.to_dict(), "network": self.net.to_dict(),
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
