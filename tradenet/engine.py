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
    fleet: dict = field(default_factory=dict)
    active_ship_id: str = "ship-1"
    next_ship_number: int = 2
    hard_mode: bool = False
    galaxies: dict = field(default_factory=dict)
    radio_state: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.galaxies:
            self.galaxies = {"home": {"name": self.name,
                "specialization": self.specialization, "ports": self.ports}}
        # Migrate version-one single-ship saves without changing their schema.
        if not self.fleet and self.active_ship_id:
            self.ship.setdefault("location", self.location)
            self.ship.setdefault("cargo", self.cargo)
            self.ship.setdefault("id", self.active_ship_id)
            self.fleet = {self.active_ship_id: self.ship}
        for ship in self.fleet.values():
            ship.setdefault("galaxy", "home")
        if self.active_ship_id not in self.fleet:
            self.active_ship_id = next(iter(self.fleet), "")
        if self.active_ship_id:
            self._bind_ship()

    def _bind_ship(self):
        self.ship = self.fleet[self.active_ship_id]
        self.location = self.ship["location"]
        self.cargo = self.ship["cargo"]
        galaxy = self.galaxies[self.ship["galaxy"]]
        self.name = galaxy["name"]
        self.specialization = galaxy["specialization"]
        self.ports = galaxy["ports"]

    def _all_arrivals(self):
        for ship in self.fleet.values():
            if ship.get("destination") is not None:
                arrival_at = ship.get("arrival_at")
                arrived = (time.time() >= arrival_at if arrival_at is not None else
                           self.tick >= (ship.get("arrival_tick") or self.tick + 1))
                if arrived:
                    ship["location"] = ship.pop("destination")
                    ship["destination"] = None
                    ship["arrival_tick"] = None
                    ship.pop("arrival_at", None)
        if self.active_ship_id:
            self._bind_ship()

    def _select_ship(self, ship_id: str) -> dict:
        if ship_id not in self.fleet:
            raise GameError("unknown ship")
        self.active_ship_id = ship_id
        self._bind_ship()
        return {"active_ship_id": ship_id, "location": self.location}

    def _purchase_ship(self, tier: int = 0, class_id: str | None = None) -> dict:
        hull = None
        if class_id is not None:
            from .modems import SHIPS
            hull = next((item for item in SHIPS if item["id"] == class_id), None)
            if hull is None:
                raise GameError("unknown ship class")
            tier = hull["tier"]
        if type(tier) is not int or not 0 <= tier < len(TIERS):
            raise GameError("invalid ship class")
        cost = hull["cost"] if hull else (350, 900, 1800)[tier]
        if self.credits < cost:
            raise GameError("insufficient credits for ship")
        self.credits -= cost
        ship_id = f"ship-{self.next_ship_number}"
        self.next_ship_number += 1
        self.fleet[ship_id] = {"id": ship_id, "name": TIERS[tier]["name"],
                               "capacity": 30, "fuel": 40, "max_fuel": 40,
                               "condition": 100, "destination": None,
                               "arrival_tick": None, "modem_tier": tier,
                               "speed": tier + 1, "location": self.location,
                               "galaxy": self.ship.get("galaxy", "home"),
                               "cargo": {g: 0 for g in GOODS}}
        if hull:
            self.fleet[ship_id].update({key: hull[key] for key in
                ("name", "capacity", "speed", "frames_per_tick", "max_bandwidth_hz", "sprite", "description")})
            self.fleet[ship_id]["class_id"] = hull["id"]
        if not self.active_ship_id:
            self.active_ship_id = ship_id
            self._bind_ship()
        return {"ship_id": ship_id, "class": self.fleet[ship_id]["name"], "cost": cost}

    def damage_ship(self, ship_id: str, amount: int, origin: str) -> dict:
        """Failed RF mission: return home damaged, or lose ship in hard mode."""
        if ship_id not in self.fleet or origin not in self.ports or amount <= 0:
            raise GameError("invalid mission damage")
        ship = self.fleet[ship_id]
        ship["condition"] = max(0, ship["condition"] - amount)
        ship["location"] = origin
        ship.pop("radio_mission", None)
        ship["destination"] = None
        ship["arrival_tick"] = None
        destroyed = self.hard_mode and ship["condition"] == 0
        if destroyed:
            del self.fleet[ship_id]
            if self.active_ship_id == ship_id:
                self.active_ship_id = next(iter(self.fleet), "")
        if self.active_ship_id:
            self._bind_ship()
        return {"ship_id": ship_id, "damage": amount, "destroyed": destroyed,
                "condition": 0 if destroyed else ship["condition"], "returned_to": origin}

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
        multiplier = 110 if action == "buy" else (104 if self.hard_mode else 90)
        return max(1, midpoint * multiplier // 100)

    def _check_port_good(self, port: str, good: str) -> None:
        if port not in self.ports:
            raise GameError(f"unknown port: {port}")
        if good not in GOODS:
            raise GameError(f"unknown good: {good}")

    def _available(self) -> None:
        if not self.active_ship_id:
            raise GameError("no surviving ship; purchase a replacement to continue")
        if self.ship["destination"] is not None:
            raise GameError("ship is in transit")
        if self.ship.get("radio_mission"):
            raise GameError("ship is assigned to a radio mission")

    def cargo_used(self) -> int:
        return sum(self.cargo.values())

    def command(self, command_id: str, action: str, **kwargs) -> dict:
        """Execute once. Repeated IDs return their original result without side effects."""
        self._all_arrivals()
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
            elif action == "jump":
                result = self._jump(**kwargs)
            elif action == "abort_transmission":
                result = self._abort_transmission(**kwargs)
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
            elif action == "purchase_ship":
                result = self._purchase_ship(**kwargs)
            elif action == "select_ship":
                result = self._select_ship(**kwargs)
            elif action == "set_hard_mode":
                result = self._set_hard_mode(**kwargs)
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
        speed = max(1, int(self.ship.get("speed", 1)))
        travel_seconds = min(10, max(1, math.ceil(distance * 2 / speed)))
        arrival_at = time.time() + travel_seconds
        self.ship["destination"] = destination
        self.ship["arrival_tick"] = None
        self.ship["arrival_at"] = arrival_at
        return {"destination": destination, "arrival_tick": self.tick,
                "arrival_at": arrival_at, "fuel_cost": fuel_cost,
                "travel_seconds": travel_seconds}

    def _jump(self, galaxy: str, destination: str, voyage_id: str) -> dict:
        self._available()
        if (not isinstance(voyage_id, str) or not 1 <= len(voyage_id) <= 128 or
                any(s.get("voyage", {}).get("id") == voyage_id for s in self.fleet.values()) or
                any(c["action"] == "jump" and c["args"].get("voyage_id") == voyage_id
                    for c in self.completed_commands.values())):
            raise GameError("invalid or duplicate voyage ID")
        if (galaxy not in self.galaxies or galaxy == self.ship["galaxy"] or
                destination not in self.galaxies[galaxy]["ports"]):
            raise GameError("invalid galaxy destination")
        if self.incoming_reserved:
            raise GameError("incoming cargo reservation prevents departure")
        if self.ship["fuel"] < 10:
            raise GameError("insufficient ship fuel")
        if self.ship["condition"] < 10:
            raise GameError("repair ship before traveling")
        voyage = {"id": voyage_id, "origin_galaxy": self.ship["galaxy"],
                  "origin": self.location, "galaxy": galaxy, "destination": destination}
        self.ship["fuel"] -= 10
        self.ship["radio_mission"] = voyage_id
        self.ship["voyage"] = voyage
        return {**voyage, "fuel_cost": 10}

    def _abort_transmission(self, voyage_id: str, damage: int) -> dict:
        """Trusted simulator coordinator supplies voyage identity and penalty."""
        voyage = self.ship.get("voyage") if self.active_ship_id else None
        if not voyage or voyage["id"] != voyage_id or type(damage) is not int or damage not in (0, 10):
            raise GameError("invalid active voyage abort")
        ship = self.ship
        ship_id = self.active_ship_id
        origin, galaxy = voyage["origin"], voyage["origin_galaxy"]
        if galaxy not in self.galaxies or origin not in self.galaxies[galaxy]["ports"]:
            raise GameError("invalid voyage origin")
        ship["galaxy"] = galaxy
        ship["location"] = origin
        ship.pop("voyage", None)
        ship.pop("voyage_manifest", None)
        ship.pop("radio_mission", None)
        ship["destination"] = None
        ship["arrival_tick"] = None
        self._bind_ship()
        if damage:
            result = self.damage_ship(ship_id, damage, origin)
        else:
            result = {"ship_id": ship_id, "damage": 0, "condition": ship["condition"],
                      "destroyed": False, "returned_to": origin}
        return {**result, "voyage_id": voyage_id, "origin_galaxy": galaxy,
                "penalty_applied": bool(damage)}

    def complete_voyage(self, voyage_id: str) -> dict | None:
        """Trusted coordinator boundary: call only after the manifest's ACK.

        Deliberately not a command; browser callers cannot invent an arrival.
        Replayed completion is harmless, including for an inactive ship.
        """
        for ship in self.fleet.values():
            voyage = ship.get("voyage")
            if voyage and voyage["id"] == voyage_id:
                ship["galaxy"] = voyage["galaxy"]
                ship["location"] = voyage["destination"]
                del ship["voyage"]
                ship.pop("radio_mission", None)
                if ship["id"] == self.active_ship_id:
                    self._bind_ship()
                return {"ship_id": ship["id"], **voyage}
        return None

    def _set_hard_mode(self, enabled: bool) -> dict:
        if type(enabled) is not bool:
            raise GameError("hard mode must be a boolean")
        if self.hard_mode and not enabled:
            raise GameError("hard mode cannot be disabled after activation")
        self.hard_mode = enabled
        return {"hard_mode": enabled, "sell_bonus_percent": 15 if enabled else 0}

    def _wait(self, ticks: int = 1) -> dict:
        if type(ticks) is not int or not 1 <= ticks <= 100:
            raise GameError("wait must be 1-100 ticks")
        for _ in range(ticks):
            self.tick += 1
            for port in self._market_ports():
                for good in GOODS:
                    port["stock"][good] = max(0, min(300,
                        port["stock"][good] + port["production"][good] -
                        port["consumption"][good]))
            self._all_arrivals()
        return {"tick": self.tick, "location": self.location,
                "in_transit": self.ship["destination"] is not None}

    def _market_ports(self):
        for galaxy in self.galaxies.values():
            yield from galaxy["ports"].values()

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
            for port in self._market_ports():
                for good in GOODS:
                    delta = port["production"][good] - port["consumption"][good]
                    port["stock"][good] = max(0, min(300, port["stock"][good] + elapsed * delta))
            self.tick += elapsed
            self._all_arrivals()
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
        from .modems import SHIPS
        hull = next(item for item in SHIPS if item["name"] == next_tier["name"])
        self.ship.update({key: hull[key] for key in
            ("speed", "frames_per_tick", "max_bandwidth_hz", "sprite", "description")})
        self.ship["class_id"] = hull["id"]
        self.ship["capacity"] = max(self.ship["capacity"], hull["capacity"])
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
