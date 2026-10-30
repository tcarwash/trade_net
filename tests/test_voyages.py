"""Same captain, real destination markets, simulated custody and reverse ACKs."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from threading import Event, Thread
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import json

import tradenet.web as web

from tradenet.engine import Game, GameError
from tradenet.web import App


class GalaxyTests(unittest.TestCase):
    def test_class_upgrade_updates_hull_capabilities_and_keeps_cargo(self):
        game = Game.new()
        bought = game.command('wisp', 'purchase_ship', class_id='wisp200')
        game.command('select', 'select_ship', ship_id=bought['ship_id'])
        game.command('load', 'buy', good='food', amount=1)
        cargo = deepcopy(game.cargo)
        game.command('faster', 'buy_ship')
        self.assertEqual(game.ship['class_id'], 'courier1200')
        self.assertEqual(game.ship['sprite'], 'courier')
        self.assertEqual(game.ship['max_bandwidth_hz'], 1200)
        self.assertEqual(game.ship['frames_per_tick'], 6)
        self.assertEqual(game.ship['capacity'], 40)
        self.assertEqual(game.cargo, cargo)

    def test_class_purchase_receipt_names_the_actual_hull(self):
        from tradenet.modems import SHIPS
        hull = SHIPS[0]
        game = Game.new()
        receipt = game.command("hull", "purchase_ship", class_id=hull["id"])
        self.assertEqual(receipt["class"], hull["name"])

    def test_completed_voyage_identity_cannot_be_reused_for_a_new_departure(self):
        game = self.galaxy_game()
        game.command("out", "jump", galaxy="SIM-K7OR", destination="Haven", voyage_id="unique")
        game.complete_voyage("unique")
        before = game.to_dict()
        with self.assertRaises(GameError):
            game.command("back", "jump", galaxy="home", destination="Haven", voyage_id="unique")
        self.assertEqual(game.to_dict(), before)

    def test_purchase_named_classes_preserves_explicit_hull_capabilities(self):
        from tradenet.modems import SHIPS
        ids = {hull["max_bandwidth_hz"]: hull["id"] for hull in SHIPS}
        classes = [
            (ids[200], 0, 200, 1, 1, 16, 200),
            (ids[500], 0, 350, 2, 1, 30, 500),
            (ids[1200], 1, 900, 6, 2, 40, 1200),
            (ids[2300], 2, 1400, 10, 2, 60, 2300),
            (ids[2400], 2, 1800, 16, 3, 30, 2400),
        ]
        for class_id, tier, cost, frames, speed, capacity, bandwidth in classes:
            with self.subTest(class_id=class_id):
                game = Game.new()
                result = game.command("purchase", "purchase_ship", class_id=class_id)
                ship = game.fleet[result["ship_id"]]
                self.assertEqual(ship["class_id"], class_id)
                self.assertEqual(result["class"], ship["name"])
                self.assertEqual(ship["modem_tier"], tier)
                self.assertEqual(ship["frames_per_tick"], frames)
                self.assertEqual(ship["max_bandwidth_hz"], bandwidth)
                self.assertEqual(ship["speed"], speed)
                self.assertEqual(ship["capacity"], capacity)
                self.assertTrue(ship["sprite"])
                self.assertEqual(game.credits, 1800 - cost)
                before = game.to_dict()
                with self.assertRaises(GameError):
                    game.command("unknown", "purchase_ship", class_id="missing")
                self.assertEqual(game.to_dict(), before)

    def galaxy_game(self):
        game = Game.new(41)
        remote = Game.new(99, "Remote")
        game.galaxies["SIM-K7OR"] = {"name": remote.name,
            "specialization": remote.specialization, "ports": deepcopy(remote.ports)}
        return game

    def test_jump_retains_captain_until_trusted_completion(self):
        game = self.galaxy_game()
        game.command("cargo", "buy", good="food", amount=2)
        cargo, credits = deepcopy(game.cargo), game.credits
        args = dict(galaxy="SIM-K7OR", destination="Haven", voyage_id="voyage:one")
        result = game.command("one", "jump", **args)
        self.assertEqual(game.ship["fuel"], 30)
        self.assertEqual(game.ship["galaxy"], "home")
        self.assertEqual(game.command("one", "jump", **args), result)
        self.assertEqual(game.ship["fuel"], 30)
        self.assertEqual(game.ship["radio_mission"], "voyage:one")
        for action, kwargs in [("buy", dict(good="food", amount=1)),
                               ("travel", dict(destination="Kepler"))]:
            with self.assertRaises(GameError):
                game.command(action, action, **kwargs)
        game = Game.from_dict(game.to_dict())
        game.complete_voyage("voyage:one")
        game.complete_voyage("voyage:one")
        self.assertEqual(game.ship["galaxy"], "SIM-K7OR")
        self.assertEqual(game.active_ship_id, "ship-1")
        self.assertEqual(game.cargo, cargo)
        self.assertEqual(game.credits, credits)
        self.assertNotIn("radio_mission", game.ship)
        self.assertNotIn("voyage", game.ship)
        self.assertEqual(game.name, "Remote")
        stock = game.ports["Haven"]["stock"]["food"]
        game.command("remote-buy", "buy", good="food", amount=1)
        self.assertEqual(game.galaxies["SIM-K7OR"]["ports"]["Haven"]["stock"]["food"], stock - 1)
        game.command("return", "jump", galaxy="home", destination="Kepler", voyage_id="voyage:back")
        game.complete_voyage("voyage:back")
        self.assertEqual((game.ship["galaxy"], game.location), ("home", "Kepler"))

    def test_invalid_jumps_are_atomic(self):
        for args, change in [
            (dict(galaxy="missing"), {}), (dict(galaxy="home"), {}),
            (dict(destination="missing"), {}), (dict(voyage_id="x" * 129), {}),
            ({}, {"fuel": 9}), ({}, {"condition": 9}),
            ({}, {"destination": "Kepler"}), ({}, {"radio_mission": "lab"}),
        ]:
            game = self.galaxy_game()
            game.ship.update(change)
            before = game.to_dict()
            options = dict(galaxy="SIM-K7OR", destination="Haven", voyage_id="voyage:one")
            options.update(args)
            with self.assertRaises(GameError):
                game.command("bad", "jump", **options)
            self.assertEqual(game.to_dict(), before)
        game = self.galaxy_game()
        game.incoming_reserved = 1
        with self.assertRaises(GameError):
            game.command("reserved", "jump", galaxy="SIM-K7OR", destination="Haven", voyage_id="v")

    def test_all_galaxy_markets_tick_once_even_when_inactive(self):
        game = self.galaxy_game()
        for galaxy in game.galaxies.values():
            port = galaxy["ports"]["Haven"]
            port["stock"]["food"] = 20
            port["production"]["food"] = 2
            port["consumption"]["food"] = 0
        game.command("wait", "wait", ticks=1)
        for galaxy in game.galaxies.values():
            self.assertEqual(galaxy["ports"]["Haven"]["stock"]["food"], 22)
        game.sync_utc(1_800_000_000)
        game.sync_utc(1_800_000_600)
        for galaxy in game.galaxies.values():
            self.assertEqual(galaxy["ports"]["Haven"]["stock"]["food"], 26)

    def test_legacy_migration_market_binding_and_roundtrip(self):
        legacy = Game.new(41).to_dict()
        legacy.pop("galaxies", None)
        for ship in legacy["fleet"].values():
            ship.pop("galaxy", None)
        game = Game.from_dict(legacy)
        self.assertEqual(game.ship["galaxy"], "home")
        self.assertEqual(game.galaxies["home"]["ports"], legacy["ports"])
        remote = Game.new(99, "Remote")
        game.galaxies["SIM-K7OR"] = {"name": remote.name,
            "specialization": remote.specialization, "ports": deepcopy(remote.ports)}
        game.command("second", "purchase_ship")
        game.fleet["ship-2"]["galaxy"] = "SIM-K7OR"
        game.command("select", "select_ship", ship_id="ship-2")
        self.assertEqual(game.name, "Remote")
        self.assertIs(game.ports, game.galaxies["SIM-K7OR"]["ports"])
        game.command("buy", "buy", good="food", amount=1)
        self.assertEqual(game.galaxies["home"]["ports"], legacy["ports"])
        restored = Game.from_dict(game.to_dict())
        self.assertEqual(restored.to_dict(), game.to_dict())
        self.assertIs(restored.ports, restored.galaxies["SIM-K7OR"]["ports"])
        restored.command("home", "select_ship", ship_id="ship-1")
        self.assertEqual(restored.name, legacy["name"])
        self.assertEqual(restored.cargo["food"], 0)


class AppVoyageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "game.json"
        self.app = App(self.path, 42, "AG7SU")

    def jump(self, command_id="trip", galaxy="SIM-K7OR", destination="Haven"):
        return self.app.execute({"id": command_id, "action": "jump",
            "args": {"galaxy": galaxy, "destination": destination}})

    def step(self, loss=0):
        return self.app.execute({"action": "mail_step", "loss": loss, "budget_frames": 64})

    def finish(self):
        for _ in range(40):
            self.step()
            if not self.app.game.ship.get("voyage"):
                return
        self.fail("voyage never arrived")

    def test_same_ship_offline_restart_outbox_recovery_and_return(self):
        navigation = self.app.state()["navigation"]
        self.assertEqual(navigation["current_galaxy"], "home")
        self.assertEqual(navigation["home_id"], "AG7SU")
        self.assertTrue(navigation["galaxies"]["SIM-K7OR"]["simulated"])
        self.assertIn("Haven", navigation["galaxies"]["SIM-K7OR"]["ports"])
        self.app.game.command("load", "buy", good="food", amount=2)
        credits = self.app.game.credits
        self.app.mail.set_online("SIM-K7OR", False)
        self.jump()
        self.jump()
        self.assertEqual(self.app.game.ship["fuel"], 30)
        message = self.app.mail.messages["voyage:trip"]
        payload = bytes.fromhex(message["payload_hex"]).decode()
        self.assertIn('"food":2', payload)
        self.assertIn('"ship_id":"ship-1"', payload)
        self.assertEqual(message["frames_per_tick"], 2)
        self.assertEqual(message["route"], ["AG7SU", "SIM-K7OR"])
        self.step()
        self.assertEqual(self.app.game.ship["galaxy"], "home")
        self.assertFalse(self.app.state()["navigation"]["voyages"]["ship-1"]["online"])
        # Crash window: durable departure but missing mail outbox entry.
        del self.app.mail.messages["voyage:trip"]
        self.app.persist()
        self.app = App(self.path, 42, "AG7SU")
        self.assertIn("voyage:trip", self.app.mail.messages)
        self.assertEqual(self.app.game.ship["fuel"], 30)
        self.app.mail.set_online("SIM-K7OR", True)
        self.finish()
        self.assertEqual(self.app.game.ship["galaxy"], "SIM-K7OR")
        self.assertEqual(self.app.game.cargo["food"], 2)
        self.assertEqual(self.app.game.credits, credits)
        self.assertEqual(self.app.game.active_ship_id, "ship-1")
        self.assertEqual(self.app.state()["navigation"]["voyages"], {})
        self.jump("back", "home", "Kepler")
        self.assertEqual(self.app.mail.messages["voyage:back"]["route"], ["SIM-K7OR", "AG7SU"])
        self.finish()
        self.assertEqual(self.app.game.location, "Kepler")
        self.assertEqual(self.app.game.ship["galaxy"], "home")
        self.assertEqual(set(self.app.net.peers), {"AG7SU"})
        self.assertEqual(self.app.net.transfers, [])

    def test_utc_ticks_automatically_progress_active_voyage_with_bounded_catchup(self):
        self.jump()
        epoch = self.app.game.clock_epoch
        before = self.app.mail.tick
        self.app.sync_clock((epoch + 1) * 300)
        self.assertEqual(self.app.mail.tick, before + 1)
        self.app.sync_clock((epoch + 1) * 300)
        self.assertEqual(self.app.mail.tick, before + 1)
        for tick in range(2, 30):
            self.app.sync_clock((epoch + tick) * 300)
        self.assertEqual(self.app.game.ship["galaxy"], "SIM-K7OR")
        self.jump("return", "home")
        self.app.mail.set_online("AG7SU", False)
        before = self.app.mail.tick
        self.app.sync_clock((epoch + 1_000_000) * 300)
        self.assertLessEqual(self.app.mail.tick - before, 500)
        self.assertEqual(self.app.game.ship["galaxy"], "SIM-K7OR")


    def test_lost_ack_and_expiry_never_invent_arrival_or_refund(self):
        self.jump()
        message = self.app.mail.messages["voyage:trip"]
        for _ in range(20):
            self.step()
            if message["status"] == "delivered":
                break
        self.assertEqual(message["status"], "delivered")
        self.step(loss=1)
        self.assertEqual(self.app.game.ship["galaxy"], "home")
        self.assertEqual(self.app.state()["navigation"]["voyages"]["ship-1"]["status"], "awaiting_ack")
        ack = self.app.mail.messages["ack:voyage:trip"]
        ack["ttl"] = 1
        self.app.mail.set_online("AG7SU", False)
        self.step()
        self.step()
        self.assertEqual(ack["status"], "expired")
        self.assertEqual(self.app.state()["navigation"]["voyages"]["ship-1"]["status"], "pending_reconciliation")
        self.app = App(self.path, 42, "AG7SU")
        self.assertEqual(self.app.game.ship["fuel"], 30)
        self.assertEqual(self.app.game.ship["galaxy"], "home")
        with self.assertRaises(GameError):
            self.app.execute({"id": "cheat", "action": "complete_voyage", "args": {"voyage_id": "voyage:trip"}})

    def test_outbound_expiry_keeps_ship_locked(self):
        self.jump()
        self.app.mail.set_online("SIM-K7OR", False)
        self.app.mail.messages["voyage:trip"]["ttl"] = 1
        self.step()
        self.step()
        self.assertEqual(self.app.game.ship["galaxy"], "home")
        self.assertEqual(self.app.game.ship["fuel"], 30)
        self.assertIn("radio_mission", self.app.game.ship)
        self.assertEqual(self.app.state()["navigation"]["voyages"]["ship-1"]["status"], "pending_reconciliation")

    def test_new_departure_cannot_spend_ticks_from_before_its_launch(self):
        epoch = self.app.game.clock_epoch
        self.app.game.clock_epoch -= 20
        with patch.object(web.time, "time", return_value=epoch * 300):
            self.jump()
            state = self.app.state()
        self.assertEqual(state["game"]["ship"]["galaxy"], "home")
        self.assertEqual(self.app.mail.tick, 0)

    def test_invalid_web_jump_leaves_all_state_unchanged(self):
        for command_id, args in [("x" * 122, {"galaxy": "SIM-K7OR", "destination": "Haven"}),
                                 ("bad", {"galaxy": "unknown", "destination": "Haven"})]:
            before = deepcopy(self.app.state())
            with self.assertRaises(GameError):
                self.app.execute({"id": command_id, "action": "jump", "args": args})
            self.assertEqual(self.app.state(), before)

    def test_mode_catalog_loads_once_and_missing_file_is_graceful(self):
        catalog_path = Path(self.directory.name) / "modes.json"
        catalog = {"provenance": "test-fixture", "modes": [{"mode_id": "fixture200", "bandwidth_hz": 200}]}
        catalog_path.write_text(json.dumps(catalog))
        with patch.object(web, "MODEM_CATALOG", catalog_path, create=True):
            self.app = App(self.path, 42, "AG7SU")
            self.assertEqual(self.app.state()["modem_catalog"], catalog)
            catalog_path.unlink()
            self.assertEqual(self.app.state()["modem_catalog"], catalog)
            self.app = App(self.path, 42, "AG7SU")
            self.assertEqual(self.app.state()["modem_catalog"]["modes"], [])

    def test_named_classes_publish_and_bound_simulated_voyage_envelopes(self):
        from tradenet.modems import SHIPS
        envelopes = {200: (1, 500), 500: (2, 500), 1200: (6, 1200), 2300: (10, 2400), 2400: (16, 2400)}
        expected = {hull["id"]: envelopes[hull["max_bandwidth_hz"]] for hull in SHIPS}
        self.assertEqual(len(expected), 5)
        self.assertEqual({item["id"] for item in self.app.state()["ship_classes"]}, set(expected))
        for class_id, (frames, bandwidth) in expected.items():
            with self.subTest(class_id=class_id):
                self.app.game.credits = 10000
                ship_id = self.app.game.command("buy-" + class_id, "purchase_ship", class_id=class_id)["ship_id"]
                self.app.game.command("select-" + class_id, "select_ship", ship_id=ship_id)
                self.jump(class_id)
                message = self.app.mail.messages["voyage:" + class_id]
                self.assertEqual(message["frames_per_tick"], frames)
                self.assertEqual(message["bandwidth_hz"], bandwidth)
                self.assertEqual(self.app.game.ship["galaxy"], "home")

    def test_inactive_ship_arrives_without_switching_other_ships_markets(self):
        self.app.game.command("second", "purchase_ship")
        self.jump()
        self.app.game.command("select-second", "select_ship", ship_id="ship-2")
        for _ in range(20):
            self.step()
        self.assertEqual(self.app.game.active_ship_id, "ship-2")
        self.assertEqual(self.app.game.ship["galaxy"], "home")
        self.assertEqual(self.app.game.fleet["ship-1"]["galaxy"], "SIM-K7OR")
        self.app.game.command("select-first", "select_ship", ship_id="ship-1")
        self.assertIs(self.app.game.ports, self.app.game.galaxies["SIM-K7OR"]["ports"])
        self.app.game.command("remote-new", "purchase_ship")
        self.assertEqual(self.app.game.fleet["ship-3"]["galaxy"], "SIM-K7OR")
        self.app.persist()
        self.app = App(self.path, 42, "AG7SU")
        self.assertEqual(self.app.game.ship["galaxy"], "SIM-K7OR")
        self.assertNotEqual(self.app.game.specialization, self.app.game.galaxies["home"]["specialization"])
        self.assertIsNot(self.app.game.ports, self.app.federation.worlds["SIM-K7OR"].ports)

    def test_exact_svg_http_route_and_navigation_endpoint(self):
        assets = Path(self.directory.name) / "assets"
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
                    self.assertEqual(int(response.headers["Content-Length"]), len(svg))
                    self.assertEqual(response.read(), svg)
                with urlopen(root + "/api/state", timeout=5) as response:
                    self.assertIn("navigation", json.load(response))
                request = Request(root + "/api/action", data=json.dumps({"id": "http-trip",
                    "action": "jump", "args": {"galaxy": "SIM-K7OR", "destination": "Haven"}}).encode(),
                    headers={"Content-Type": "application/json"}, method="POST")
                with urlopen(request, timeout=5) as response:
                    result = json.load(response)
                    self.assertEqual(result["result"]["id"], "voyage:http-trip")
                    self.assertEqual(result["state"]["navigation"]["voyages"]["ship-1"]["destination"], "Haven")
                for path in ("/engine.py", "/../engine.py", "/ships.svg/extra"):
                    with self.assertRaises(HTTPError) as caught:
                        urlopen(root + path, timeout=5)
                    self.assertEqual(caught.exception.code, 404)
            finally:
                server.shutdown()
                worker.join(5)


if __name__ == "__main__":
    unittest.main()
