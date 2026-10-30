"""Small deterministic economic core, deliberately independent of radio and UI."""

from __future__ import annotations

import json
import math
import time
import random
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from .modems import TIERS


GOODS = ("food", "ore", "fuel", "medicine", "aether", "iridium", "mycelium")
RARE = ("aether", "iridium", "mycelium")
BASE_PRICE = {"food": 12, "ore": 20, "fuel": 28, "medicine": 46,
              "aether": 180, "iridium": 220, "mycelium": 160}
PORT_NAMES = ("Haven", "Kepler", "Vesper", "Prospect", "Meridian")


class GameError(ValueError):
    """A command is invalid without modifying game state."""


@dataclass
class Game:
    seed: int
    name: str
    tick: int = 0
    credits: int = 1800
    location: str = "Haven"
    cargo: dict[str, int] = field(default_factory=dict)
    ports: dict = field(default_factory=dict)
    ship: dict = field(default_factory=dict)
    journal: list[dict] = field(default_factory=list)
    completed_commands: dict = field(default_factory=dict)
    schema_version: int = 1
    specialization: str = ""
    contracts: dict = field(default_factory=dict)
    incoming_reserved: int = 0
    clock_epoch: int | None = None
    tick_seconds: int = 300

    @classmethod
    def new(cls, seed: int = 1, name: str = "Home Galaxy") -> "Game":
        rng = random.Random(seed)
        specialty = RARE[rng.randrange(len(RARE))]
        ports = {}
        for i, port in enumerate(PORT_NAMES):
            stock = {good: rng.randint(12, 45) for good in GOODS}
            production = {good: rng.randint(0, 2) for good in GOODS}
            consumption = {good: rng.randint(0, 2) for good in GOODS}
            for rare in RARE:
                stock[rare] = rng.randint(0, 5)
                production[rare] = 0
                consumption[rare] = 1 if rng.random() < .45 else 0
            # The galaxy's signature resource is plentiful at its producer,
            # but other rare goods remain attainable via NPC markets.
            if i == 1:
                stock[specialty] = 90
                production[specialty] = 5
            elif i == 3:
                stock[specialty] = 18
                production[specialty] = 2
            ports[port] = {"stock": stock, "production": production,
                           "consumption": consumption,
                           "distance": abs(i - 0) * 2 + (1 if i else 0)}
        return cls(seed=seed, name=name, specialization=specialty, ports=ports,
                   cargo={g: 0 for g in GOODS},
                   ship={"name": "Wayfarer", "capacity": 30, "fuel": 40,
                         "max_fuel": 40, "condition": 100, "destination": None,
                         "arrival_tick": None, "modem_tier": 0, "speed": 1})

    def price(self, port: str, good: str, action: str) -> int:
        self._check_port_good(port, good)
        if action not in ("buy", "sell"):
            raise GameError("action must be buy or sell")
        stock = self.ports[port]["stock"][good]
        # Scarcity raises prices, supply depresses them. Narrow spread blocks
        # buying and immediately reselling for a profit in the same port.
        pressure = max(50, min(200, 150 - stock))
        midpoint = max(1, BASE_PRICE[good] * pressure // 100)
        return max(1, midpoint * (110 if action == "buy" else 90) // 100)

    def _check_port_good(self, port: str, good: str) -> None:
        if port not in self.ports:
            raise GameError(f"unknown port: {port}")
        if good not in GOODS:
            raise GameError(f"unknown good: {good}")

    def _available(self) -> None:
        if self.ship["destination"] is not None:
            raise GameError("ship is in transit")

    def cargo_used(self) -> int:
        return sum(self.cargo.values())

    def command(self, command_id: str, action: str, **kwargs) -> dict:
        """Execute once. Repeated IDs return their original result without side effects."""
        if not command_id or len(command_id) > 128:
            raise GameError("command_id must contain 1-128 characters")
        if command_id in self.completed_commands:
            previous = self.completed_commands[command_id]
            if previous["action"] != action or previous["args"] != kwargs:
                raise GameError("command ID reused with different parameters")
            return deepcopy(previous["result"])
        snapshot = self.to_dict()
        try:
            if action == "buy":
                result = self._trade("buy", **kwargs)
            elif action == "sell":
                result = self._trade("sell", **kwargs)
            elif action == "travel":
                result = self._travel(**kwargs)
            elif action == "wait":
                result = self._wait(**kwargs)
            elif action == "repair":
                result = self._repair()
            elif action == "refuel":
                result = self._refuel(**kwargs)
            elif action == "upgrade":
                result = self._upgrade()
            elif action == "upgrade_modem":
                result = self._buy_ship()
            elif action == "buy_ship":
                result = self._buy_ship()
            elif action == "accept_contract":
                result = self._accept_contract(**kwargs)
            elif action == "cancel_contract":
                result = self._cancel_contract(**kwargs)
            elif action == "reclaim_contract":
                result = self._reclaim_contract(**kwargs)
            else:
                raise GameError(f"unknown action: {action}")
        except (GameError, TypeError, KeyError) as exc:
            self.__dict__.update(Game.from_dict(snapshot).__dict__)
            raise GameError(str(exc)) from exc
        self.completed_commands[command_id] = {"action": action, "args": kwargs,
                                                "result": deepcopy(result)}
        self.journal.append({"id": command_id, "tick": self.tick,
                             "action": action, "args": deepcopy(kwargs),
                             "result": deepcopy(result)})
        return result

    def _trade(self, action: str, good: str, amount: int) -> dict:
        self._available()
        self._check_port_good(self.location, good)
        if type(amount) is not int or amount <= 0 or amount > 10000:
            raise GameError("amount must be a positive integer <= 10000")
        stock = self.ports[self.location]["stock"]
        unit = self.price(self.location, good, action)
        total = unit * amount
        if action == "buy":
            if stock[good] < amount:
                raise GameError("insufficient port stock")
            if self.credits < total:
                raise GameError("insufficient credits")
            if self.cargo_used() + self.incoming_reserved + amount > self.ship["capacity"]:
                raise GameError("cargo hold full")
            stock[good] -= amount
            self.cargo[good] += amount
            self.credits -= total
        else:
            if self.cargo[good] < amount:
                raise GameError("insufficient cargo")
            self.cargo[good] -= amount
            stock[good] += amount
            self.credits += total
        return {"action": action, "good": good, "amount": amount,
                "unit_price": unit, "total": total, "credits": self.credits}

    def _travel(self, destination: str) -> dict:
        self._available()
        if destination not in self.ports or destination == self.location:
            raise GameError("invalid destination")
        distance = abs(self.ports[destination]["distance"] -
                       self.ports[self.location]["distance"])
        fuel_cost = max(2, distance * 2)
        if fuel_cost > self.ship["fuel"]:
            raise GameError("insufficient ship fuel")
        if self.ship["condition"] < 10:
            raise GameError("repair ship before traveling")
        self.ship["fuel"] -= fuel_cost
        self.ship["condition"] = max(0, self.ship["condition"] - max(1, distance))
        self.ship["destination"] = destination
        self.ship["arrival_tick"] = self.tick + max(1, math.ceil(distance / self.ship.get("speed", 1)))
        return {"destination": destination, "arrival_tick": self.ship["arrival_tick"],
                "fuel_cost": fuel_cost}

    def _wait(self, ticks: int = 1) -> dict:
        if type(ticks) is not int or not 1 <= ticks <= 100:
            raise GameError("wait must be 1-100 ticks")
        for _ in range(ticks):
            self.tick += 1
            for port in self.ports.values():
                for good in GOODS:
                    port["stock"][good] = max(0, min(300,
                        port["stock"][good] + port["production"][good] -
                        port["consumption"][good]))
            if (self.ship["destination"] is not None and
                    self.tick >= self.ship["arrival_tick"]):
                self.location = self.ship["destination"]
                self.ship["destination"] = None
                self.ship["arrival_tick"] = None
        return {"tick": self.tick, "location": self.location,
                "in_transit": self.ship["destination"] is not None}

    def sync_utc(self, now: float | None = None) -> dict:
        """Advance to a common UTC epoch boundary, including offline catch-up.

        Markets are linear with per-tick clamping, so bulk advance gives the
        same stock result as a loop over every missed tick. No clock rollback.
        """
        now = time.time() if now is None else now
        epoch = math.floor(now / self.tick_seconds)
        if self.clock_epoch is None:
            self.clock_epoch = epoch
            return {"epoch": epoch, "advanced": 0, "tick": self.tick}
        elapsed = max(0, epoch - self.clock_epoch)
        if elapsed:
            for port in self.ports.values():
                for good in GOODS:
                    delta = port["production"][good] - port["consumption"][good]
                    port["stock"][good] = max(0, min(300, port["stock"][good] + elapsed * delta))
            self.tick += elapsed
            if (self.ship["destination"] is not None and
                    self.tick >= self.ship["arrival_tick"]):
                self.location = self.ship["destination"]
                self.ship["destination"] = None
                self.ship["arrival_tick"] = None
            self.clock_epoch = epoch
        return {"epoch": self.clock_epoch, "advanced": elapsed, "tick": self.tick}

    def _repair(self) -> dict:
        self._available()
        cost = (100 - self.ship["condition"]) * 2
        if self.credits < cost:
            raise GameError("insufficient credits")
        self.credits -= cost
        self.ship["condition"] = 100
        return {"cost": cost, "condition": 100}

    def _refuel(self, amount: int) -> dict:
        self._available()
        if type(amount) is not int or amount <= 0:
            raise GameError("fuel amount must be a positive integer")
        if self.ship["fuel"] + amount > self.ship["max_fuel"]:
            raise GameError("ship fuel tank capacity exceeded")
        stock = self.ports[self.location]["stock"]
        if stock["fuel"] < amount:
            raise GameError("insufficient port fuel")
        cost = self.price(self.location, "fuel", "buy") * amount
        if self.credits < cost:
            raise GameError("insufficient credits")
        stock["fuel"] -= amount
        self.ship["fuel"] += amount
        self.credits -= cost
        return {"amount": amount, "cost": cost, "fuel": self.ship["fuel"]}

    def _upgrade(self) -> dict:
        self._available()
        cost = 400 + self.ship["capacity"] * 10
        if self.credits < cost:
            raise GameError("insufficient credits")
        self.credits -= cost
        self.ship["capacity"] += 10
        return {"cost": cost, "capacity": self.ship["capacity"]}

    def _buy_ship(self) -> dict:
        self._available()
        tier = self.ship.get("modem_tier", 0)
        if tier >= len(TIERS) - 1:
            raise GameError("fastest ship class already owned")
        next_tier = TIERS[tier + 1]
        cost = next_tier["upgrade_cost"]
        if self.credits < cost:
            raise GameError("insufficient credits for faster ship")
        self.credits -= cost
        self.ship["modem_tier"] = tier + 1
        self.ship["speed"] = tier + 2
        self.ship["name"] = next_tier["name"]
        return {"cost": cost, "ship": next_tier["name"],
                "speed": self.ship["speed"],
                "max_bandwidth_hz": next_tier["max_bandwidth_hz"]}

    def _accept_contract(self, contract_id: str) -> dict:
        self._available()
        c = self.contracts.get(contract_id)
        if not c or c["status"] != "offered":
            raise GameError("contract is not available")
        if self.tick > c["deadline"]:
            raise GameError("contract offer has expired")
        if self.cargo[c["good"]] < c["quantity"]:
            raise GameError("load the required cargo before accepting")
        self.cargo[c["good"]] -= c["quantity"]
        c["status"] = "reserved"
        c["custody"] = self.location
        return {"contract_id": contract_id, "status": "reserved",
                "reserved": {c["good"]: c["quantity"]}}

    def _cancel_contract(self, contract_id: str) -> dict:
        c = self.contracts.get(contract_id)
        if not c or c["status"] != "reserved":
            raise GameError("only undispatched reservations can be cancelled")
        if self.cargo_used() + c["quantity"] > self.ship["capacity"]:
            raise GameError("insufficient cargo space to return reservation")
        self.cargo[c["good"]] += c["quantity"]
        c["status"] = "cancelled"
        c["custody"] = None
        return {"contract_id": contract_id, "status": "cancelled"}

    def _reclaim_contract(self, contract_id: str) -> dict:
        c = self.contracts.get(contract_id)
        if not c or c["status"] != "expired" or c["custody"] != c.get("origin_id"):
            raise GameError("expired cargo is not available for local recovery")
        if self.cargo_used() + c["quantity"] > self.ship["capacity"]:
            raise GameError("insufficient hold space")
        self.cargo[c["good"]] += c["quantity"]
        c["status"] = "reclaimed"
        return {"contract_id": contract_id, "status": "reclaimed"}

    def to_dict(self) -> dict:
        return deepcopy(self.__dict__)

    @classmethod
    def from_dict(cls, data: dict) -> "Game":
        if data.get("schema_version") != 1:
            raise GameError("unsupported save version")
        return cls(**deepcopy(data))

    def save(self, path: str | Path) -> None:
        path = Path(path)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)

    @classmethod
    def load(cls, path: str | Path) -> "Game":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
