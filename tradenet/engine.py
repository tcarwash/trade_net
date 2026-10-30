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
PORT_NAMES = ("Haven", "Kepler", "Vesper", "Prospect", "Meridian",
              "Cinder", "Aurora", "Drift", "Bastion", "Eidolon")
PORT_ROLES = ("Home hub", "Refinery", "Research enclave", "Mining colony",
              "Trade exchange", "Industrial furnace", "Medical sanctuary",
              "Salvage outpost", "Fortress station", "Frontier observatory")
EQUIPMENT = {"scanner": 220, "shield": 350, "navigator": 420, "defense": 380}
INCIDENT_INTERVAL = 8  # Shared economy ticks; no wall-clock-only randomness.
SECTOR_INCIDENTS = (
    ("Medical emergency", "Aurora", "Vesper", "medicine",
     "A clinic supply convoy is overdue. Medical shipments are urgently needed."),
    ("Foundry shutdown", "Cinder", "Prospect", "ore",
     "An industrial failure has halted local ore processing. Repairs need raw materials."),
    ("Station rationing", "Bastion", "Haven", "food",
     "Security crews have imposed rationing after a supply ship missed its arrival."),
    ("Fuel shortage", "Drift", "Kepler", "fuel",
     "Salvage traffic has drained the depot's fuel reserves."),
    ("Research rush", "Vesper", "Aurora", "medicine",
     "A breakthrough has drawn researchers and exhausted the laboratory's supplies."),
    ("Trade festival", "Meridian", "Haven", "food",
     "The exchange is hosting a major festival and buying provisions at a premium."),
)
EXPEDITION_TEMPLATES = (
    {"id": "expedition-relief", "title": "The Long Night",
     "description": "A storm has stranded Bastion's medical crews. Gather supplies, choose who receives them, and report back to Haven.",
     "reward": 470, "stages": [
         {"port": "Aurora", "kind": "load", "title": "Secure emergency medicine",
          "description": "Purchase 3 medicine at Aurora and keep it aboard your ship.",
          "good": "medicine", "quantity": 3},
         {"port": "Bastion", "kind": "deliver_choice", "title": "Triage at Bastion",
          "description": "Deliver all 3 medicine and decide who gets priority.",
          "good": "medicine", "quantity": 3, "choices": [
              {"id": "clinic", "label": "Help the field clinic",
               "description": "+90 cr, +3 scientists standing", "bonus": 90,
               "faction": "scientists", "reputation": 3},
              {"id": "evacuation", "label": "Aid the evacuation",
               "description": "+60 cr, +3 diplomats standing", "bonus": 60,
               "faction": "diplomats", "reputation": 3}]},
         {"port": "Haven", "kind": "finish", "title": "Debrief at Haven",
          "description": "Return to your headquarters to collect the mission reward."}]},
    {"id": "expedition-beacon", "title": "Echoes of Eidolon",
     "description": "An ancient relay near Eidolon has fallen silent. Source repair materials, investigate, and decide what to recover.",
     "reward": 560, "stages": [
         {"port": "Prospect", "kind": "load", "title": "Source relay materials",
          "description": "Purchase 2 ore at Prospect for the damaged relay.",
          "good": "ore", "quantity": 2},
         {"port": "Eidolon", "kind": "deliver_choice", "title": "The silent relay",
          "description": "Use the 2 ore to stabilize the site, then make a discovery choice.",
          "good": "ore", "quantity": 2, "choices": [
              {"id": "restore", "label": "Restore the relay",
               "description": "+40 cr, +3 explorers standing", "bonus": 40,
               "faction": "explorers", "reputation": 3},
              {"id": "salvage", "label": "Claim the salvage",
               "description": "+120 cr, +3 miners standing", "bonus": 120,
               "faction": "miners", "reputation": 3}]},
         {"port": "Haven", "kind": "finish", "title": "File the expedition report",
          "description": "Return to Haven with the relay's findings."}]},
)


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
    local_jobs: dict = field(default_factory=dict)
    next_job_number: int = 1
    export_warehouse: dict = field(default_factory=dict)
    price_memory: dict = field(default_factory=dict)
    visited_ports: list[str] = field(default_factory=lambda: ["Haven"])
    vip_jobs: dict = field(default_factory=dict)
    next_vip_number: int = 1
    factions: dict = field(default_factory=dict)
    story_stage: int = 0
    discoveries: dict = field(default_factory=dict)
    sector_events: list[dict] = field(default_factory=list)
    expeditions: dict = field(default_factory=dict)
    radio_bands_seen: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.galaxies:
            self.galaxies = {"home": {"name": self.name,
                "specialization": self.specialization, "ports": self.ports}}
        # Expand older five-port saves without touching their existing markets.
        if self.ports and self.galaxies.get("home", {}).get("ports"):
            missing = [p for p in PORT_NAMES if p not in self.galaxies["home"]["ports"]]
            if missing:
                expanded = Game.new(self.seed)
                for port in missing:
                    self.galaxies["home"]["ports"][port] = deepcopy(expanded.ports[port])
            for i, port in enumerate(PORT_NAMES):
                self.galaxies["home"]["ports"][port].setdefault("role", PORT_ROLES[i])
        # Migrate version-one single-ship saves without changing their schema.
        if not self.fleet and self.active_ship_id:
            self.ship.setdefault("location", self.location)
            self.ship.setdefault("cargo", self.cargo)
            self.ship.setdefault("id", self.active_ship_id)
            self.fleet = {self.active_ship_id: self.ship}
        for ship in self.fleet.values():
            ship.setdefault("galaxy", "home")
            ship.setdefault("export_cargo", {})
            ship.setdefault("equipment", [])
        for faction in ("traders", "explorers", "diplomats", "security",
                        "miners", "scientists", "pirates"):
            self.factions.setdefault(faction, 0)
        if self.active_ship_id not in self.fleet:
            self.active_ship_id = next(iter(self.fleet), "")
        if self.active_ship_id:
            self._bind_ship()
        if not self.local_jobs:
            self._replenish_local_jobs()
        self._replenish_vip_jobs()
        self._refresh_sector_events()
        if not self.expeditions:
            self.expeditions = {template["id"]: {**deepcopy(template), "status": "offered",
                "stage": 0, "bonus": 0, "choice": None, "accepted_tick": None}
                for template in EXPEDITION_TEMPLATES}
        self.observe_markets()

    def _refresh_sector_events(self):
        """One seeded, actionable bulletin per economy cycle, with no RF side effects.

        Catch-up creates only the current incident; old unseen incidents are not
        backfilled as dozens of expired quests when a save is reopened.
        """
        cycle = self.tick // INCIDENT_INTERVAL
        if any(event["cycle"] == cycle for event in self.sector_events):
            return
        title, port, origin, good, description = SECTOR_INCIDENTS[(self.seed + cycle) % len(SECTOR_INCIDENTS)]
        quantity = 3 + (self.seed + cycle) % 3
        event_id = f"dispatch-{cycle:05d}"
        deadline = (cycle + 1) * INCIDENT_INTERVAL - 1
        reward = BASE_PRICE[good] * quantity * 3
        event = {"id": event_id, "cycle": cycle, "title": title,
                 "port": port, "origin": origin, "good": good,
                 "description": description, "start_tick": cycle * INCIDENT_INTERVAL,
                 "end_tick": deadline + 1, "quantity": quantity,
                 "reward": reward, "job_id": event_id,
                 "source": "simulated"}
        self.sector_events.append(event)
        self.sector_events = self.sector_events[-12:]
        # Local dispatch contracts use the ordinary cargo, deadline and payout
        # pathway. They never enter the Data2G radio contract ledger.
        if event_id not in self.local_jobs:
            self.local_jobs[event_id] = {"id": event_id, "origin": origin,
                "destination": port, "good": good, "quantity": quantity,
                "reward": reward, "status": "open", "deadline": deadline,
                "kind": "dispatch", "event_id": event_id}
        # Dispatch displaces a routine posting rather than expanding the
        # board indefinitely. Keep the normal three-job choice budget.
        open_jobs = [job for job in self.local_jobs.values() if job["status"] == "open"]
        for job in reversed(open_jobs):
            if len(open_jobs) <= 3:
                break
            if job.get("kind") != "dispatch":
                job["status"] = "superseded"
                open_jobs.remove(job)

    def active_sector_events(self) -> list[dict]:
        return [event for event in self.sector_events
                if event["start_tick"] <= self.tick < event["end_tick"]]

    def _accept_expedition(self, expedition_id: str) -> dict:
        self._available()
        mission = self.expeditions.get(expedition_id)
        if not mission or mission["status"] != "offered":
            raise GameError("expedition is not available")
        if self.ship.get("galaxy", "home") != "home" or self.location != "Haven":
            raise GameError("accept expeditions at Haven headquarters")
        if any(other["status"] == "accepted" for other in self.expeditions.values()):
            raise GameError("finish or abandon your current expedition first")
        mission["status"] = "accepted"
        mission["accepted_tick"] = self.tick
        mission["stage"] = 0
        mission["bonus"] = 0
        mission["choice"] = None
        return {"expedition_id": expedition_id, "title": mission["title"],
                "next": deepcopy(mission["stages"][0])}

    def _advance_expedition(self, expedition_id: str, choice: str | None = None) -> dict:
        self._available()
        mission = self.expeditions.get(expedition_id)
        if not mission or mission["status"] != "accepted":
            raise GameError("expedition is not active")
        if self.ship.get("galaxy", "home") != "home":
            raise GameError("return to your home galaxy for this expedition")
        stage = mission["stages"][mission["stage"]]
        if self.location != stage["port"]:
            raise GameError(f"travel to {stage['port']} for this expedition step")
        kind = stage["kind"]
        if kind == "load":
            if choice is not None:
                raise GameError("this step does not require a choice")
            if self.cargo[stage["good"]] < stage["quantity"]:
                raise GameError(f"load {stage['quantity']} {stage['good']} before proceeding")
        elif kind == "deliver_choice":
            option = next((entry for entry in stage["choices"] if entry["id"] == choice), None)
            if option is None:
                raise GameError("choose one of the available expedition outcomes")
            if self.cargo[stage["good"]] < stage["quantity"]:
                raise GameError(f"deliver {stage['quantity']} {stage['good']} to proceed")
            self.cargo[stage["good"]] -= stage["quantity"]
            self.ship.setdefault("export_cargo", {})[stage["good"]] = max(
                0, self.ship["export_cargo"].get(stage["good"], 0) - stage["quantity"])
            self.ports[self.location]["stock"][stage["good"]] += stage["quantity"]
            mission["bonus"] += option["bonus"]
            mission["choice"] = choice
        elif kind == "finish":
            if choice is not None:
                raise GameError("this step does not require a choice")
            # An overdue expedition can still be completed; only the prompt
            # return bonus is forfeited. Offline play must not strand cargo.
            punctual = self.tick - mission["accepted_tick"] <= 48
            reward = mission["reward"] + mission["bonus"] + (100 if punctual else 0)
            choice_stage = next((step for step in mission["stages"]
                                 if step["kind"] == "deliver_choice"), None)
            if choice_stage:
                chosen = next((item for item in choice_stage["choices"]
                               if item["id"] == mission["choice"]), None)
                if chosen:
                    self.factions[chosen["faction"]] += chosen["reputation"]
            self.credits += reward
            self.factions["traders"] += 2
            mission["status"] = "completed"
            mission["completed_tick"] = self.tick
            mission["payout"] = reward
            return {"expedition_id": expedition_id, "title": mission["title"],
                    "stage_title": stage["title"], "completed": True,
                    "reward": reward, "choice": mission["choice"]}
        else:
            raise GameError("unsupported expedition step")
        mission["stage"] += 1
        return {"expedition_id": expedition_id, "title": mission["title"],
                "stage_title": stage["title"], "completed": False,
                "choice": choice, "next": deepcopy(mission["stages"][mission["stage"]])}

    def _abandon_expedition(self, expedition_id: str) -> dict:
        mission = self.expeditions.get(expedition_id)
        if not mission or mission["status"] != "accepted":
            raise GameError("expedition is not active")
        # Any cargo already purchased stays with the player. Reputation and
        # payout settle at the debrief, so restarting cannot farm them.
        mission.update(status="offered", stage=0, bonus=0, choice=None,
                       accepted_tick=None)
        return {"expedition_id": expedition_id, "status": "offered",
                "title": mission["title"]}

    def _replenish_vip_jobs(self):
        for job in self.vip_jobs.values():
            if job["status"] == "open" and self.tick > job["deadline"]:
                job["status"] = "expired"
        while sum(j["status"] == "open" for j in self.vip_jobs.values()) < 2:
            n = self.next_vip_number
            self.next_vip_number += 1
            ports = list(self.ports)
            if len(ports) < 2:
                break
            origin = ports[(n * 3) % len(ports)]
            destination = ports[(n * 3 + 4) % len(ports)]
            if origin == destination:
                destination = ports[(n * 3 + 1) % len(ports)]
            names = ("Diplomatic envoy", "Medical specialist", "Survey captain", "Trade delegate")
            self.vip_jobs[f"vip-{n:04d}"] = {"id": f"vip-{n:04d}",
                "title": names[(n-1) % len(names)], "origin": origin,
                "destination": destination, "reward": 240 + (n % 4) * 65,
                "faction": ("diplomats", "scientists", "explorers", "traders")[(n-1) % 4],
                "deadline": self.tick + 48, "status": "open"}

    def _accept_vip(self, job_id: str) -> dict:
        self._available()
        job = self.vip_jobs.get(job_id)
        if not job or job["status"] != "open" or self.tick > job["deadline"]:
            raise GameError("VIP mission is unavailable or expired")
        if self.location != job["origin"]:
            raise GameError(f"pick up the passenger at {job['origin']}")
        if self.ship.get("vip_job"):
            raise GameError("ship already carries a VIP passenger")
        job["status"] = "aboard"
        job["ship_id"] = self.active_ship_id
        self.ship["vip_job"] = job_id
        self._replenish_vip_jobs()
        return {"job_id": job_id, "destination": job["destination"], "title": job["title"]}

    def _deliver_vip(self, job_id: str) -> dict:
        self._available()
        job = self.vip_jobs.get(job_id)
        if (not job or job["status"] != "aboard" or
                job.get("ship_id") != self.active_ship_id or self.ship.get("vip_job") != job_id):
            raise GameError("VIP is not aboard this ship")
        if self.location != job["destination"]:
            raise GameError(f"take the passenger to {job['destination']}")
        if self.tick > job["deadline"]:
            raise GameError("VIP mission expired; return the passenger to dispatch")
        self.ship.pop("vip_job", None)
        job["status"] = "delivered"
        payout = job["reward"] + min(100, self.factions["diplomats"] * 10)
        self.credits += payout
        self.factions["diplomats"] += 2
        if job.get("faction") in self.factions and job["faction"] != "diplomats":
            self.factions[job["faction"]] += 2
        return {"job_id": job_id, "reward": payout, "title": job["title"]}

    def _buy_equipment(self, item: str) -> dict:
        self._available()
        if item not in EQUIPMENT:
            raise GameError("unknown ship equipment")
        if item in self.ship.setdefault("equipment", []):
            raise GameError("ship already has this equipment")
        if self.credits < EQUIPMENT[item]:
            raise GameError("insufficient credits for equipment")
        self.credits -= EQUIPMENT[item]
        self.ship["equipment"].append(item)
        return {"item": item, "cost": EQUIPMENT[item], "ship_id": self.active_ship_id}

    def story_objective(self) -> dict:
        stages = (
            ("First Signal", "Visit Kepler to investigate a frontier transmission.", "Kepler", 130),
            ("Medical Relief", "Deliver 2 medicine to Aurora's clinic.", "Aurora", 300),
            ("The Silent Observatory", "Explore Eidolon to recover a lost survey beacon.", "Eidolon", 350),
            ("Return to Haven", "Bring the recovered beacon data home to Haven.", "Haven", 500))
        if self.story_stage >= len(stages):
            return {"title": "Frontier Signal Complete", "description": "The frontier is open. Continue trading, exploring, and connecting stations.", "complete": True}
        title, description, port, reward = stages[self.story_stage]
        return {"title": title, "description": description, "port": port,
                "reward": reward, "stage": self.story_stage, "complete": False}

    def _complete_story(self) -> dict:
        self._available()
        objective = self.story_objective()
        if objective["complete"]:
            raise GameError("frontier story already completed")
        if self.location != objective["port"]:
            raise GameError(f"story objective requires visiting {objective['port']}")
        if self.story_stage == 1:
            if self.cargo["medicine"] < 2:
                raise GameError("bring 2 medicine for the clinic")
            self.cargo["medicine"] -= 2
            eligible = self.ship.setdefault("export_cargo", {})
            eligible["medicine"] = max(0, eligible.get("medicine", 0) - 2)
        self.credits += objective["reward"]
        self.factions["explorers"] += 2
        self.story_stage += 1
        return {"title": objective["title"], "reward": objective["reward"],
                "next": self.story_objective()}

    def _cancel_vip(self, job_id: str) -> dict:
        self._available()
        job = self.vip_jobs.get(job_id)
        if not job or job["status"] != "aboard" or self.ship.get("vip_job") != job_id:
            raise GameError("VIP is not aboard this ship")
        self.ship.pop("vip_job", None)
        job["status"] = "cancelled"
        return {"job_id": job_id, "status": "cancelled"}

    def route_risk(self, origin: str, destination: str) -> dict:
        """Deterministic, previewable terrain for each route and market tick."""
        if origin not in self.ports or destination not in self.ports:
            raise GameError("invalid route")
        a, b = sorted((list(self.ports).index(origin), list(self.ports).index(destination)))
        distance = abs(self.ports[origin]["distance"] - self.ports[destination]["distance"])
        signature = (a * 19 + b * 31 + self.seed + self.tick // 3) % 11
        if distance >= 3 and signature in (0, 1, 2, 3):
            return {"kind": "gas", "label": "Ionized gas cloud", "damage": 4 + distance // 2}
        if distance >= 2 and signature in (4, 5, 6):
            return {"kind": "pirates", "label": "Pirate interception", "damage": 3 + distance // 3}
        return {"kind": "clear", "label": "Clear corridor", "damage": 0}

    def blocked_port(self, now: float | None = None) -> str:
        """The predictable field moves to the next port every 90 seconds."""
        now = time.time() if now is None else now
        return PORT_NAMES[(self.seed + math.floor(now / 90)) % len(PORT_NAMES)]

    def observe_markets(self) -> None:
        """Remember best actual dockside quotes, not omniscient future prices."""
        for ship in self.fleet.values():
            if ship.get("destination") or ship.get("galaxy", "home") != "home":
                continue
            port = ship.get("location")
            if port not in self.ports:
                continue
            for good in GOODS:
                memory = self.price_memory.setdefault(good, {})
                for action, key, better in (("buy", "lowest_buy", min),
                                            ("sell", "highest_sell", max)):
                    quote = self.price(port, good, action)
                    prior = memory.get(key)
                    if prior is None or better(quote, prior["price"]) == quote:
                        memory[key] = {"port": port, "price": quote, "tick": self.tick}

    def _replenish_local_jobs(self):
        """Keep a small deterministic board of real, one-time freight demand."""
        for job in self.local_jobs.values():
            if job["status"] == "open" and self.tick > job["deadline"]:
                job["status"] = "expired"
        if len(self.local_jobs) > 100:
            history = [key for key, job in self.local_jobs.items() if job["status"] != "open"]
            for key in history[:len(self.local_jobs) - 100]:
                del self.local_jobs[key]
        open_jobs = sum(job["status"] == "open" for job in self.local_jobs.values())
        ports = list(self.ports)
        while open_jobs < 3 and ports:
            number = self.next_job_number
            self.next_job_number += 1
            origin = ports[(number - 1) % len(ports)]
            destination = ports[(number + 1) % len(ports)]
            good = ("food", "ore", "medicine", "fuel")[(number - 1) % 4]
            quantity = 2 + number % 4
            distance = abs(self.ports[origin]["distance"] - self.ports[destination]["distance"])
            reward = max(70, BASE_PRICE[good] * quantity * (150 + distance * 8) // 100)
            job_id = f"local-{number:04d}"
            self.local_jobs[job_id] = {"id": job_id, "origin": origin,
                "destination": destination, "good": good, "quantity": quantity,
                "reward": reward, "status": "open", "deadline": self.tick + 48}
            open_jobs += 1

    def _deliver_local(self, job_id: str) -> dict:
        self._available()
        job = self.local_jobs.get(job_id)
        if not job or job["status"] != "open":
            raise GameError("freight job is no longer available")
        if self.tick > job["deadline"]:
            raise GameError("freight job expired")
        if self.location != job["destination"]:
            raise GameError(f"deliver at {job['destination']}")
        if self.cargo[job["good"]] < job["quantity"]:
            raise GameError("load the requested freight before delivery")
        self.cargo[job["good"]] -= job["quantity"]
        eligible = self.ship.setdefault("export_cargo", {})
        eligible[job["good"]] = max(0, eligible.get(job["good"], 0) - job["quantity"])
        self.ports[self.location]["stock"][job["good"]] += job["quantity"]
        self.credits += job["reward"]
        self.factions["traders"] += 1
        job["status"] = "delivered"
        job["completed_tick"] = self.tick
        self._replenish_local_jobs()
        return {"job_id": job_id, "reward": job["reward"], "credits": self.credits}

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
                    ship.pop("departed_at", None)
                    ship.pop("travel_seconds", None)
                    ship.pop("origin_port", None)
                    if ship.get("galaxy", "home") == "home" and ship["location"] not in self.visited_ports:
                        self.visited_ports.append(ship["location"])
                        explore_bonus = 90 + min(100, self.factions["explorers"] * 10)
                        self.credits += explore_bonus
                        self.factions["explorers"] += 1
                        index = list(self.ports).index(ship["location"])
                        if index % 3 == 1:
                            find = {"title": "Abandoned supply cache", "reward": 110 + index * 10}
                        elif index % 3 == 2:
                            find = {"title": "Ancient navigation beacon", "reward": 60 + index * 10}
                        else:
                            find = {"title": "Uncharted trade outpost", "reward": 80 + index * 10}
                        self.discoveries[ship["location"]] = find
                        self.credits += find["reward"]
                        self.journal.append({"id": "explore-" + ship["location"],
                            "tick": self.tick, "action": "explore",
                            "result": {"port": ship["location"], "reward": explore_bonus + find["reward"],
                                       "discovery": find["title"]}})
        if self.active_ship_id:
            self._bind_ship()
        self.observe_markets()

    def _select_ship(self, ship_id: str) -> dict:
        if ship_id not in self.fleet:
            raise GameError("unknown ship")
        self.active_ship_id = ship_id
        self._bind_ship()
        self.observe_markets()
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
            passenger = ship.get("vip_job")
            if passenger in self.vip_jobs:
                self.vip_jobs[passenger]["status"] = "lost"
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
            elif i >= 5:
                focus = ("ore", "medicine", "fuel", "food", specialty)[(i-5) % 5]
                stock[focus] = 85
                production[focus] = 4
                consumption[focus] = 0
            ports[port] = {"stock": stock, "production": production,
                           "consumption": consumption,
                           "distance": abs(i - 0) * 2 + (1 if i else 0),
                           "role": PORT_ROLES[i]}
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
        if any(event["port"] == port and event["good"] == good
               for event in self.active_sector_events()):
            midpoint = midpoint * 150 // 100
        multiplier = 110 if action == "buy" else ((104 if self.hard_mode else 90) + min(10, self.factions.get("traders", 0) // 2))
        if action == "buy" and good in ("ore", "medicine"):
            faction = "miners" if good == "ore" else "scientists"
            multiplier -= min(8, self.factions.get(faction, 0) // 2)
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
            elif action == "deliver_local":
                result = self._deliver_local(**kwargs)
            elif action == "unload_export":
                result = self._unload_export(**kwargs)
            elif action == "accept_vip":
                result = self._accept_vip(**kwargs)
            elif action == "deliver_vip":
                result = self._deliver_vip(**kwargs)
            elif action == "cancel_vip":
                result = self._cancel_vip(**kwargs)
            elif action == "buy_equipment":
                result = self._buy_equipment(**kwargs)
            elif action == "complete_story":
                result = self._complete_story()
            elif action == "accept_expedition":
                result = self._accept_expedition(**kwargs)
            elif action == "advance_expedition":
                result = self._advance_expedition(**kwargs)
            elif action == "abandon_expedition":
                result = self._abandon_expedition(**kwargs)
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
            if good == "ore" and self.location in ("Prospect", "Cinder"):
                self.factions["miners"] += 1
            if good == "medicine" and self.location in ("Vesper", "Aurora"):
                self.factions["scientists"] += 1
            if self.location != "Haven":
                eligible = self.ship.setdefault("export_cargo", {})
                eligible[good] = eligible.get(good, 0) + amount
        else:
            if self.cargo[good] < amount:
                raise GameError("insufficient cargo")
            self.cargo[good] -= amount
            stock[good] += amount
            self.credits += total
            eligible = self.ship.setdefault("export_cargo", {})
            eligible[good] = max(0, eligible.get(good, 0) - amount)
        return {"action": action, "good": good, "amount": amount,
                "unit_price": unit, "total": total, "credits": self.credits}

    def _unload_export(self, good: str, amount: int) -> dict:
        self._available()
        if self.location != "Haven":
            raise GameError("return to Haven to unload export freight")
        if good not in GOODS or type(amount) is not int or amount <= 0:
            raise GameError("choose a valid good and positive quantity")
        eligible = self.ship.setdefault("export_cargo", {})
        if amount > self.cargo.get(good, 0) or amount > eligible.get(good, 0):
            raise GameError("export freight must have been purchased outside Haven")
        self.cargo[good] -= amount
        eligible[good] -= amount
        self.export_warehouse[good] = self.export_warehouse.get(good, 0) + amount
        return {"good": good, "amount": amount,
                "warehouse": self.export_warehouse[good]}

    def _travel(self, destination: str, pirate_stance: str = "pay") -> dict:
        self._available()
        if destination not in self.ports or destination == self.location:
            raise GameError("invalid destination")
        if pirate_stance not in ("pay", "evade", "fight"):
            raise GameError("invalid pirate strategy")
        equipment = self.ship.get("equipment", [])
        blocked = destination == self.blocked_port()
        if blocked and "navigator" not in equipment:
            raise GameError(f"Asteroid field blocks the direct approach to {destination}; wait for the field to orbit onward")
        distance = abs(self.ports[destination]["distance"] -
                       self.ports[self.location]["distance"])
        risk = self.route_risk(self.location, destination)
        fuel_cost = max(2, distance * 2) + (4 if blocked else 0) + (4 if risk["kind"] == "pirates" and pirate_stance == "evade" else 0)
        if fuel_cost > self.ship["fuel"]:
            raise GameError("insufficient ship fuel")
        if self.ship["condition"] < 10:
            raise GameError("repair ship before traveling")
        self.ship["fuel"] -= fuel_cost
        mitigation = max(0, int(self.ship.get("modem_tier", 0)) * 2)
        if risk["kind"] == "gas" and "shield" in equipment:
            mitigation += 6
        if risk["kind"] == "pirates":
            if pirate_stance == "evade":
                mitigation += 2
                risk = {**risk, "outcome": "Evaded pirates using extra fuel"}
            elif pirate_stance == "fight":
                mitigation += (7 if "defense" in equipment else 0) + min(5, self.factions.get("security", 0) // 3)
                risk = {**risk, "damage": risk["damage"] + (0 if "defense" in equipment else 5),
                        "outcome": "Pirates repelled" if "defense" in equipment else "Hard-fought escape"}
                self.factions["security"] += 1
        hazard_damage = max(0, risk["damage"] - mitigation)
        self.ship["condition"] = max(0, self.ship["condition"] - max(1, distance) - hazard_damage)
        if risk["kind"] == "pirates" and pirate_stance == "pay":
            # A capped pirate toll makes a dangerous route matter without
            # deleting a reserved cargo manifest or creating a dead-end.
            toll = min(self.credits, max(0, 10 + distance * 3 - self.factions.get("pirates", 0) * 2))
            self.credits -= toll
            risk = {**risk, "toll": toll}
            self.factions["pirates"] += 1
        if blocked:
            risk = {**risk, "navigator_bypass": True}
        speed = max(1, int(self.ship.get("speed", 1)))
        travel_seconds = min(10, max(1, math.ceil(distance * 2 / speed)))
        arrival_at = time.time() + travel_seconds
        self.ship["destination"] = destination
        self.ship["arrival_tick"] = None
        self.ship["arrival_at"] = arrival_at
        self.ship["departed_at"] = arrival_at - travel_seconds
        self.ship["travel_seconds"] = travel_seconds
        self.ship["origin_port"] = self.location
        return {"destination": destination, "arrival_tick": self.tick,
                "arrival_at": arrival_at, "fuel_cost": fuel_cost,
                "travel_seconds": travel_seconds, "hazard": risk,
                "hazard_damage": hazard_damage}

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
            self._refresh_sector_events()
        self._replenish_local_jobs()
        self.observe_markets()
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
            self._refresh_sector_events()
            self._replenish_local_jobs()
            self.observe_markets()
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
