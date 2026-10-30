"""Direct station galaxies are local models; advertisements are topology only."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tradenet.engine import Game, GameError
from tradenet.mail import MailNetwork
from tradenet.web import App


class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "game.json"
        # Keep economy boundaries out of discovery/conservation assertions.
        self.clock = patch("tradenet.web.time.time", return_value=1_800_000_000)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.app = App(self.path, 42, "AG7SU")

    def discover(self, peer, neighbors=()):
        return self.app.execute({"action": "discover", "peer": peer,
                                 "neighbors": list(neighbors)})

    def test_discovery_creates_stable_local_market_without_minting_captain_assets(self):
        self.app.game.command("load", "buy", good="food", amount=2)
        before = self.app.game.to_dict()
        self.discover("N0ONE")
        self.assertIn("N0ONE", self.app.game.galaxies)
        world = deepcopy(self.app.game.galaxies["N0ONE"])
        modeled = Game.new(int.from_bytes(hashlib.sha256(b"N0ONE").digest(), "big"))
        self.assertEqual(world["ports"], modeled.ports)
        self.assertEqual(world["specialization"], modeled.specialization)
        after = self.app.game.to_dict()
        for key in before:
            if key != "galaxies":
                self.assertEqual(after[key], before[key], key)
        self.assertIn("N0ONE", self.app.mail.stations)
        self.assertNotIn("N0ONE", self.app.federation.worlds)
        self.assertEqual(self.app.net.transfers, [])
        self.discover("N0ONE")
        self.assertEqual(self.app.game.galaxies["N0ONE"], world)
        self.assertEqual(json.loads(self.path.read_text())["galaxies"]["N0ONE"], world)
        self.app = App(self.path, 999, "AG7SU")
        self.assertEqual(self.app.game.galaxies["N0ONE"], world)
        self.assertIn("N0ONE", self.app.mail.stations)

    def test_simulated_first_hop_with_two_neighbors_is_travelable_after_reverse_ack(self):
        self.app.game.command("cargo", "buy", good="food", amount=2)
        cargo, credits = deepcopy(self.app.game.cargo), self.app.game.credits
        transfer = self.app.execute({"action": "simulate", "peer": "N0SIM", "bytes": 128,
            "loss": 0, "neighbors": [{"peer": "N0LEFT"}, {"peer": "N0RIGHT"}]})
        self.assertTrue(transfer["delivered"])
        nav = self.app.state()["navigation"]
        self.assertEqual([item["id"] for item in nav["galaxies"]["N0SIM"]["reported_neighbors"]],
                         ["N0LEFT", "N0RIGHT"])
        self.app.execute({"id": "trip", "action": "jump",
            "args": {"galaxy": "N0SIM", "destination": "Haven"}})
        message = self.app.mail.messages["voyage:trip"]
        self.assertEqual(message["route"], ["AG7SU", "N0SIM"])
        for _ in range(40):
            self.app.execute({"action": "mail_step", "loss": 0, "budget_frames": 64})
            if message["status"] == "delivered":
                break
        self.assertEqual(message["status"], "delivered")
        self.assertEqual(self.app.game.ship["galaxy"], "home")
        self.assertIn("ack:voyage:trip", self.app.mail.messages)
        for _ in range(40):
            self.app.execute({"action": "mail_step", "loss": 0, "budget_frames": 64})
            if message["status"] == "acknowledged":
                break
        self.assertEqual(message["status"], "acknowledged")
        self.assertEqual(self.app.game.ship["galaxy"], "N0SIM")
        self.assertEqual(self.app.game.cargo, cargo)
        self.assertEqual(self.app.game.credits, credits)
        self.assertNotIn("voyage", self.app.game.ship)

    def test_failed_simulation_and_reported_jump_do_not_create_galaxies(self):
        self.discover("N0ONE", [{"peer": "N0NEXT"}])
        before = deepcopy(self.app.game.to_dict())
        result = self.app.execute({"action": "simulate", "peer": "N0FAIL", "bytes": 64,
            "loss": 1, "neighbors": [{"peer": "N0FAKE"}]})
        self.assertFalse(result["delivered"])
        self.assertEqual(self.app.game.to_dict(), before)
        self.assertNotIn("N0FAIL", self.app.mail.stations)
        self.assertNotIn("N0FAKE", self.app.net.peers)
        state = deepcopy(self.app.state())
        with self.assertRaises(GameError):
            self.app.execute({"id": "bad-hop", "action": "jump",
                "args": {"galaxy": "N0NEXT", "destination": "Haven"}})
        self.assertEqual(self.app.state(), state)

    def test_promotion_reuses_station_identity_and_preserves_existing_galaxy(self):
        self.discover("N0ONE", [{"peer": "N0NEXT", "goodput_bps": 4}])
        self.assertNotIn("N0NEXT", self.app.game.galaxies)
        self.assertEqual(self.app.state()["navigation"]["reported_stations"][0]["id"], "N0NEXT")
        self.discover("N0NEXT")
        world = self.app.game.galaxies["N0NEXT"]
        world["ports"]["Haven"]["stock"]["food"] = 123
        nav = self.app.state()["navigation"]
        self.assertEqual(nav["reported_stations"], [])
        self.assertEqual(nav["galaxies"]["N0ONE"]["reported_neighbors"][0], {
            "id": "N0NEXT", "kind": "direct", "reported_by": "N0ONE",
            "goodput_bps": 4, "provenance": "reported"})
        self.discover("N0NEXT")
        self.assertIs(self.app.game.galaxies["N0NEXT"], world)
        self.assertEqual(world["ports"]["Haven"]["stock"]["food"], 123)
        self.assertEqual(set(nav["galaxies"]), {"home", "SIM-K7OR", "N0ONE", "N0NEXT"})

    def test_startup_restores_known_direct_models_and_preserves_saved_markets_and_offline_state(self):
        self.discover("N0KEEP")
        self.app.game.galaxies["N0KEEP"]["ports"]["Haven"]["stock"]["food"] = 123
        self.app.mail.set_online("N0KEEP", False)
        # A legacy network save can predate playable station galaxies.
        self.app.net.discover("N0BOOT", [{"peer": "N0REPORT"}])
        before = deepcopy(self.app.game.galaxies)
        self.app.persist()
        with patch.object(MailNetwork, "add_station", autospec=True,
                          side_effect=MailNetwork.add_station) as register:
            self.app = App(self.path, 999, "AG7SU")
        for station, world in before.items():
            self.assertEqual(self.app.game.galaxies[station], world)
        self.assertIn("N0BOOT", self.app.game.galaxies)
        self.assertEqual([call.args[1] for call in register.call_args_list].count("N0BOOT"), 1)
        self.assertFalse(self.app.mail.stations["N0KEEP"]["online"])
        self.assertNotIn("N0REPORT", self.app.game.galaxies)
        self.assertEqual(json.loads(self.path.read_text())["galaxies"], self.app.game.galaxies)

    def test_exact_station_id_models_do_not_depend_on_home_seed_or_discovery_order(self):
        self.discover("N0ONE")
        self.discover("n0one")
        worlds = deepcopy(self.app.game.galaxies)
        other = App(Path(self.directory.name) / "other.json", 831, "OTHER")
        for peer in ("n0one", "N0ONE"):
            other.execute({"action": "discover", "peer": peer})
            self.assertEqual(other.game.galaxies[peer], worlds[peer])
        self.assertNotEqual(worlds["N0ONE"]["ports"], worlds["n0one"]["ports"])

    def test_state_syncs_network_discovery_before_serializing_game(self):
        self.app.net.discover("N0LIVE", [{"peer": "N0NEXT"}])
        state = self.app.state()
        self.assertIn("N0LIVE", state["navigation"]["galaxies"])
        self.assertIn("N0LIVE", state["game"]["galaxies"])
        self.assertIn("N0LIVE", state["mail"]["stations"])
        self.assertNotIn("N0NEXT", state["game"]["galaxies"])

    def test_only_direct_parent_advertisements_create_neighbor_topology(self):
        self.discover("N0ONE")
        self.app.net.peers["AG7SU"]["kind"] = "direct"
        self.app.net.peers["N0REPORT"] = {"kind": "reported"}
        for key, source, reporter in [
            ("home", "AG7SU", "AG7SU"),
            ("secondhop", "N0REPORT", "N0REPORT"),
            ("unattributed", "N0ONE", None),
            ("mismatch", "AG7SU", "N0ONE"),
        ]:
            self.app.net.links[key] = {"source": source, "destination": "N0GHOST",
                "kind": "reported", "reported_by": reporter, "goodput_bps": 1}
        nav = self.app.state()["navigation"]
        self.assertEqual(nav["galaxies"]["N0ONE"]["reported_neighbors"], [])
        self.assertNotIn("AG7SU", nav["galaxies"])
        self.assertNotIn("N0GHOST", [item["id"] for item in nav["reported_stations"]])

    def test_navigation_exposes_parented_reports_without_playable_second_hops(self):
        self.discover("N0ONE", [
            {"peer": "N0ZED", "goodput_bps": 12},
            {"peer": "N0TWO", "goodput_bps": 9},
            {"peer": "N0ONE"}, {"peer": "AG7SU"},
        ])
        self.discover("N0TWO", [{"peer": "N0ZED", "goodput_bps": 17}])
        # Duplicate edge metadata must not duplicate identities. Unattributed
        # and observed edges cannot fabricate parent advertisements.
        self.app.net.links["duplicate"] = deepcopy(self.app.net.links["N0ONE->N0ZED"])
        self.app.net.peers["ORPHAN"] = {"kind": "reported"}
        self.app.net.links["observed"] = {"source": "N0ONE", "destination": "ORPHAN",
            "kind": "observed", "reported_by": "N0ONE", "goodput_bps": 100}
        before = deepcopy(self.app.net.to_dict())
        nav = self.app.state()["navigation"]
        self.assertEqual(nav["galaxies"]["home"].get("kind"), "home")
        self.assertEqual(nav["galaxies"]["home"]["station_id"], "AG7SU")
        self.assertEqual(nav["galaxies"]["home"]["provenance"], "local_model")
        self.assertEqual(nav["galaxies"]["home"]["reported_neighbors"], [])
        demo = nav["galaxies"]["SIM-K7OR"]
        self.assertEqual((demo["kind"], demo["provenance"]), ("demo", "demo"))
        self.assertNotIn("SIM-K7OR", self.app.net.peers)
        direct = nav["galaxies"]["N0ONE"]
        self.assertEqual((direct["kind"], direct["station_id"], direct["provenance"]),
                         ("direct", "N0ONE", "local_model"))
        self.assertTrue(direct["simulated"])
        self.assertEqual(direct["reported_neighbors"], [
            {"id": "N0TWO", "kind": "direct", "reported_by": "N0ONE",
             "goodput_bps": 9, "provenance": "reported"},
            {"id": "N0ZED", "kind": "reported", "reported_by": "N0ONE",
             "goodput_bps": 12, "provenance": "reported"},
        ])
        self.assertEqual(nav["galaxies"]["N0TWO"]["reported_neighbors"], [
            {"id": "N0ZED", "kind": "reported", "reported_by": "N0TWO",
             "goodput_bps": 17, "provenance": "reported"}])
        self.assertEqual(nav["reported_stations"], [
            {"id": "N0ZED", "kind": "reported", "reported_by": ["N0ONE", "N0TWO"],
             "travelable": False},
            {"id": "ORPHAN", "kind": "reported", "reported_by": [], "travelable": False},
        ])
        self.assertNotIn("N0ZED", nav["galaxies"])
        self.assertNotIn("N0ZED", self.app.mail.stations)
        self.assertEqual(self.app.net.to_dict(), before)


if __name__ == "__main__":
    unittest.main()
