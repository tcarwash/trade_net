"""Current local starship voyages and the supported web API boundary."""

import json
import tempfile
import unittest
from copy import deepcopy
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import tradenet.web as web
from tradenet.engine import Game, GameError
from tradenet.modems import SHIPS
from tradenet.web import App


def clear_destination(game):
    return next(port for port in game.ports
                if port != game.location and port != game.blocked_port())


class LocalVoyageTests(unittest.TestCase):
    def test_named_ship_classes_keep_distinct_modem_and_cargo_capabilities(self):
        classes = {h["max_bandwidth_hz"]: h for h in SHIPS}
        self.assertEqual(set(classes), {200, 500, 1200, 2300, 2400})
        for bandwidth, hull in classes.items():
            with self.subTest(bandwidth=bandwidth):
                game = Game.new()
                purchased = game.command("new-hull", "purchase_ship", class_id=hull["id"])
                ship = game.fleet[purchased["ship_id"]]
                self.assertEqual(ship["max_bandwidth_hz"], bandwidth)
                self.assertEqual(ship["class_id"], hull["id"])
                self.assertEqual(purchased["class"], hull["name"])
                self.assertTrue(ship["sprite"])
                self.assertGreater(ship["capacity"], 0)
                before = (game.credits, len(game.fleet))
                with self.assertRaises(GameError):
                    game.command("invalid-hull", "purchase_ship", class_id="nonexistent")
                self.assertEqual((game.credits, len(game.fleet)), before)

    def test_upgrading_active_hull_preserves_cargo(self):
        game = Game.new()
        bought = game.command("wisp", "purchase_ship", class_id="wisp200")
        game.command("select", "select_ship", ship_id=bought["ship_id"])
        game.command("buy", "buy", good="food", amount=1)
        cargo = deepcopy(game.cargo)
        game.command("upgrade", "buy_ship")
        self.assertEqual(game.ship["class_id"], "courier1200")
        self.assertEqual(game.ship["max_bandwidth_hz"], 1200)
        self.assertEqual(game.cargo, cargo)

    def test_local_departure_consumes_fuel_and_requires_arrival(self):
        game = Game.new(41)
        destination = clear_destination(game)
        original_fuel = game.ship["fuel"]
        result = game.command("fly", "travel", destination=destination)
        self.assertLess(game.ship["fuel"], original_fuel)
        self.assertEqual(game.location, "Haven")
        self.assertGreater(result["arrival_at"], 0)
        with self.assertRaises(GameError):
            game.command("buy-in-flight", "buy", good="food", amount=1)
        game.ship["arrival_at"] = 0
        game._all_arrivals()
        self.assertEqual(game.location, destination)
        self.assertIsNone(game.ship["destination"])

    def test_other_ship_arrival_does_not_switch_selected_ship(self):
        game = Game.new(41)
        other_id = game.command("another", "purchase_ship", class_id="wisp200")["ship_id"]
        destination = clear_destination(game)
        game.command("depart", "travel", destination=destination)
        game.command("select-other", "select_ship", ship_id=other_id)
        game.fleet["ship-1"]["arrival_at"] = 0
        game._all_arrivals()
        self.assertEqual(game.active_ship_id, other_id)
        self.assertEqual(game.fleet["ship-1"]["location"], destination)
        self.assertEqual(game.location, "Haven")

    def test_asteroid_block_and_hazard_outcomes_are_explicit(self):
        game = Game.new(41)
        blocked = game.blocked_port()
        with self.assertRaisesRegex(GameError, "Asteroid field"):
            game.command("blocked", "travel", destination=blocked)
        alternative = clear_destination(game)
        risk = game.route_risk("Haven", alternative)
        flight = game.command("safe-route", "travel", destination=alternative)
        self.assertEqual(flight["hazard"]["kind"], risk["kind"])
        self.assertGreaterEqual(flight["hazard_damage"], 0)

    def test_save_load_preserves_ship_in_transit_and_local_market(self):
        game = Game.new(41)
        destination = clear_destination(game)
        game.command("depart", "travel", destination=destination)
        restored = Game.from_dict(game.to_dict())
        self.assertEqual(restored.ship["destination"], destination)
        self.assertEqual(restored.ship["arrival_at"], game.ship["arrival_at"])
        self.assertEqual(restored.ports, game.ports)
        restored.ship["arrival_at"] = 0
        restored._all_arrivals()
        self.assertEqual(restored.location, destination)


class WebVoyageTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "game.json"
        self.app = App(self.path, 42, "AG7SU")

    def test_web_rejects_simulated_intergalactic_jump(self):
        before = self.app.game.ship["location"]
        with self.assertRaises(GameError):
            self.app.execute({"id": "jump", "action": "jump",
                "args": {"galaxy": "SIM-K7OR", "destination": "Haven"}})
        self.assertEqual(self.app.game.ship["location"], before)

    def test_web_local_travel_and_restart(self):
        destination = clear_destination(self.app.game)
        result = self.app.execute({"id": "flight", "action": "travel",
            "args": {"destination": destination}})
        self.assertEqual(result["destination"], destination)
        self.app = App(self.path, 42, "AG7SU")
        self.assertEqual(self.app.game.ship["destination"], destination)
        self.assertEqual(self.app.state()["navigation"]["current_galaxy"], "home")

    def test_svg_asset_is_served_but_private_files_are_not(self):
        assets = Path(self.path.parent) / "assets"
        assets.mkdir()
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><symbol id="scout"/></svg>'
        (assets / "ships.svg").write_bytes(svg)
        ready = Event()
        servers = []

        def server_factory(address, handler):
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            servers.append(server)
            ready.set()
            return server

        with patch.object(web, "WEB", assets), patch.object(web, "ThreadingHTTPServer", server_factory):
            worker = Thread(target=web.serve, kwargs={"save": str(self.path)}, daemon=True)
            worker.start()
            self.assertTrue(ready.wait(5))
            server = servers[0]
            root = f"http://127.0.0.1:{server.server_port}"
            try:
                with urlopen(root + "/ships.svg", timeout=5) as response:
                    self.assertEqual(response.headers["Content-Type"], "image/svg+xml")
                    self.assertEqual(response.read(), svg)
                with urlopen(root + "/api/state", timeout=5) as response:
                    self.assertEqual(json.load(response)["navigation"]["home_id"], "AG7SU")
                destination = clear_destination(self.app.game)
                request = Request(root + "/api/action", data=json.dumps({
                    "id": "http-flight", "action": "travel",
                    "args": {"destination": destination}}).encode(),
                    headers={"Content-Type": "application/json"}, method="POST")
                with urlopen(request, timeout=5) as response:
                    self.assertEqual(json.load(response)["result"]["destination"], destination)
                for path in ("/engine.py", "/../engine.py", "/ships.svg/extra"):
                    with self.assertRaises(HTTPError) as caught:
                        urlopen(root + path, timeout=5)
                    self.assertEqual(caught.exception.code, 404)
            finally:
                server.shutdown()
                worker.join(5)


if __name__ == "__main__":
    unittest.main()
