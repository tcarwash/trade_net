"""Radio navigation shows heard stations, not invented playable worlds."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tradenet import radio_exchange
from tradenet.engine import GameError
from tradenet.web import App


class NavigationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "galaxy.json"
        self.clock = patch("tradenet.web.time.time", return_value=1_800_000_000)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.app = App(self.path, 42, "AG7SU")

    def test_home_is_a_playable_local_galaxy_without_fake_partners(self):
        navigation = self.app.state()["navigation"]
        self.assertEqual(navigation["home_id"], "AG7SU")
        self.assertEqual(navigation["current_galaxy"], "home")
        self.assertEqual(set(navigation["galaxies"]), {"home"})
        self.assertEqual(navigation["galaxies"]["home"]["kind"], "home")
        self.assertEqual(navigation["voyages"], {})

    def test_contact_observation_registers_a_station_without_fake_markets(self):
        home_before = self.app.game.ports["Haven"]["stock"].copy()
        self.app.radio_resources["K7OR"] = {"richness": "iridium", "observed_at": 100}
        navigation = self.app.state()["navigation"]
        station = navigation["galaxies"]["K7OR"]
        self.assertEqual(station["kind"], "direct")
        self.assertEqual(station["provenance"], "heard_over_radio")
        self.assertFalse(station["simulated"])
        self.assertEqual(station["ports"], [])
        self.assertEqual(self.app.game.galaxies["K7OR"]["ports"], {})
        self.assertEqual(self.app.game.ports["Haven"]["stock"], home_before)
        self.app.persist()
        restored = App(self.path, 42, "AG7SU")
        self.assertIn("K7OR", restored.state()["navigation"]["galaxies"])

    def test_second_hop_is_only_a_reported_station(self):
        self.app.radio_resources.update({
            "K7OR": {"richness": "iridium", "observed_at": 100},
            "W1XYZ": {"richness": "platinum", "via": "K7OR", "observed_at": 100},
        })
        nav = self.app.state()["navigation"]
        self.assertIn("K7OR", nav["galaxies"])
        self.assertNotIn("W1XYZ", nav["galaxies"])
        self.assertEqual(nav["reported_stations"][0]["id"], "W1XYZ")
        self.assertFalse(nav["reported_stations"][0]["travelable"])
        self.assertEqual(nav["galaxies"]["K7OR"]["reported_neighbors"][0]["id"], "W1XYZ")
        self.assertNotIn("W1XYZ", self.app.game.galaxies)

    def test_overheard_radio_message_is_intelligence_not_verified_contact(self):
        message = radio_exchange.encode_message({"v": 1, "t": "contact", "i": "overheard-1",
            "f": "W1AAA", "d": "W2BBB", "x": "iridium", "n": [], "c": []})
        before_credits = self.app.game.credits
        for frame in radio_exchange.frames(message):
            self.assertIsNone(self.app._handle_received_frame(frame))
        self.assertEqual(self.app.game.credits, before_credits)
        self.assertNotIn("W1AAA", self.app.radio_contacts)
        self.assertIn("W1AAA", self.app.radio_resources)

    def test_disabled_simulated_radio_and_jump_cannot_modify_save(self):
        before = self.app.game.credits
        with self.assertRaises(GameError):
            self.app.execute({"action": "simulate", "peer": "N0FAKE", "bytes": 32})
        with self.assertRaises(GameError):
            self.app.execute({"id": "jump", "action": "jump",
                "args": {"galaxy": "N0FAKE", "destination": "Haven"}})
        self.assertEqual(self.app.game.credits, before)
        self.assertNotIn("N0FAKE", self.app.state()["navigation"]["galaxies"])


if __name__ == "__main__":
    unittest.main()
