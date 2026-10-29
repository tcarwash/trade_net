import tempfile
import unittest
from pathlib import Path

from tradenet import Game, GameError


class EconomyTests(unittest.TestCase):
    def test_seed_reproducible_and_specialized(self):
        a, b = Game.new(42), Game.new(42)
        self.assertEqual(a.to_dict(), b.to_dict())
        self.assertIn(a.specialization, ("aether", "iridium", "mycelium"))
        self.assertGreaterEqual(a.ports["Kepler"]["stock"][a.specialization], 90)

    def test_conserved_stock_and_credits(self):
        game = Game.new(5)
        good = "food"
        stock = game.ports[game.location]["stock"][good]
        before = game.credits
        buy = game.command("b1", "buy", good=good, amount=3)
        self.assertEqual(game.cargo[good], 3)
        self.assertEqual(game.ports[game.location]["stock"][good], stock - 3)
        self.assertEqual(game.credits, before - buy["total"])
        game.command("s1", "sell", good=good, amount=3)
        self.assertEqual(game.cargo[good], 0)
        self.assertEqual(game.ports[game.location]["stock"][good], stock)
        self.assertLess(game.credits, before)

    def test_atomic_rejection(self):
        game = Game.new()
        prior = game.to_dict()
        with self.assertRaises(GameError):
            game.command("bad", "buy", good="aether", amount=100)
        self.assertEqual(game.to_dict(), prior)

    def test_duplicate_idempotent_and_conflict_rejected(self):
        game = Game.new()
        first = game.command("same", "buy", good="food", amount=1)
        saved = game.to_dict()
        self.assertEqual(game.command("same", "buy", good="food", amount=1), first)
        self.assertEqual(game.to_dict(), saved)
        with self.assertRaises(GameError):
            game.command("same", "buy", good="ore", amount=1)

    def test_travel_wait_save_reload(self):
        game = Game.new(12)
        trip = game.command("t1", "travel", destination="Kepler")
        self.assertEqual(game.ship["destination"], "Kepler")
        game.command("w1", "wait", ticks=trip["arrival_tick"])
        self.assertEqual(game.location, "Kepler")
        self.assertIsNone(game.ship["destination"])
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "save.json"
            game.save(file)
            self.assertEqual(Game.load(file).to_dict(), game.to_dict())

    def test_cargo_capacity_and_invalid_wait(self):
        game = Game.new()
        with self.assertRaises(GameError):
            game.command("over", "buy", good="food", amount=31)
        with self.assertRaises(GameError):
            game.command("negative-time", "wait", ticks=-2)

    def test_refuel_uses_port_stock_and_credits(self):
        game = Game.new()
        game.command("trip", "travel", destination="Kepler")
        game.command("arrive", "wait", ticks=3)
        before = game.ports["Kepler"]["stock"]["fuel"]
        old_fuel = game.ship["fuel"]
        old_credits = game.credits
        result = game.command("fill", "refuel", amount=2)
        self.assertEqual(game.ship["fuel"], old_fuel + 2)
        self.assertEqual(game.ports["Kepler"]["stock"]["fuel"], before - 2)
        self.assertEqual(game.credits, old_credits - result["cost"])


if __name__ == "__main__":
    unittest.main()
