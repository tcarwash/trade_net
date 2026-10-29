"""Simple local-first command-line preview of Trade Net."""

import argparse
from pathlib import Path

from .engine import Game, GameError, GOODS, PORT_NAMES


def main() -> None:
    parser = argparse.ArgumentParser(description="Trade Net solo prototype")
    parser.add_argument("--save", default="galaxy.json", help="local save file")
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    path = Path(args.save)
    game = Game.load(path) if path.exists() else Game.new(args.seed)
    print(f"Welcome to {game.name} — rare resource: {game.specialization}")
    print("Commands: status, market, buy GOOD QTY, sell GOOD QTY, travel PORT, wait [TICKS], refuel QTY, repair, upgrade, quit")
    command_counter = len(game.journal)
    while True:
        try:
            parts = input("trade-net> ").strip().split()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not parts:
            continue
        verb, *values = parts
        if verb in ("quit", "exit"):
            break
        try:
            if verb == "status":
                print(f"Tick {game.tick} | {game.location} | {game.credits} cr | cargo {game.cargo_used()}/{game.ship['capacity']}")
                print(f"Ship {game.ship['name']}: fuel {game.ship['fuel']}, condition {game.ship['condition']}, destination {game.ship['destination']}")
                print("Cargo:", {k: v for k, v in game.cargo.items() if v})
                print("Ports:", ", ".join(PORT_NAMES))
                continue
            if verb == "market":
                for good in GOODS:
                    stock = game.ports[game.location]["stock"][good]
                    print(f"{good:10s} stock={stock:3d} buy={game.price(game.location, good, 'buy'):4d} sell={game.price(game.location, good, 'sell'):4d}")
                continue
            if verb in ("buy", "sell") and len(values) == 2:
                params = {"good": values[0], "amount": int(values[1])}
            elif verb == "travel" and len(values) == 1:
                params = {"destination": values[0]}
            elif verb == "wait" and len(values) <= 1:
                params = {"ticks": int(values[0]) if values else 1}
            elif verb == "refuel" and len(values) == 1:
                params = {"amount": int(values[0])}
            elif verb in ("repair", "upgrade") and not values:
                params = {}
            else:
                print("Invalid command or argument count")
                continue
            command_counter += 1
            result = game.command(f"local-{command_counter}", verb, **params)
            game.save(path)
            print(result)
        except (GameError, ValueError) as exc:
            print("Error:", exc)
    game.save(path)
    print(f"Saved {path}")


if __name__ == "__main__":
    main()
