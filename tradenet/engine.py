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
NPC_INTERVAL = 6  # A captain's route advances every 30 in-game minutes.
ENCOUNTER_INTERVAL = 12  # A new local opportunity every in-game hour.
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
    {"id": "expedition-embers", "title": "Embers Under Cinder", "issuer_npc": "rin-kestrel",
     "description": "Rin Kestrel's miners are trapped beneath the Cinder foundry. Carry supports, choose who gets the last rescue shuttle, and report back.",
     "reward": 610, "stages": [
         {"port": "Prospect", "kind": "load", "title": "Gather structural supports",
          "description": "Buy 4 ore from Prospect for the collapsing tunnels.", "good": "ore", "quantity": 4},
         {"port": "Cinder", "kind": "deliver_choice", "title": "The miners' last lift",
          "description": "Deliver 4 ore to Cinder and decide which rescue receives priority.",
          "good": "ore", "quantity": 4, "choices": [
              {"id": "miners", "label": "Save the trapped miners", "description": "+110 cr, +4 miners; Rin remembers your help",
               "bonus": 110, "faction": "miners", "reputation": 4, "relationship": 3},
              {"id": "security", "label": "Secure the station crew", "description": "+170 cr, +3 security; Rin resents the delay",
               "bonus": 170, "faction": "security", "reputation": 3, "relationship": -2}]},
         {"port": "Haven", "kind": "finish", "title": "File the rescue report",
          "description": "Return to Haven to record the rescue and collect your fee."}]},
    {"id": "expedition-archive", "title": "The Quiet Archive", "issuer_npc": "lysa-quell",
     "description": "Dr. Lysa Quell needs a medical courier for an isolated observatory. The archive's discovery could help science—or its neighbors.",
     "reward": 680, "stages": [
         {"port": "Aurora", "kind": "load", "title": "Prepare the quarantine kit",
          "description": "Purchase 3 medicine at Aurora for the observatory crew.", "good": "medicine", "quantity": 3},
         {"port": "Eidolon", "kind": "deliver_choice", "title": "The observatory's secret",
          "description": "Deliver the medicine and decide where Quell's findings go.",
          "good": "medicine", "quantity": 3, "choices": [
              {"id": "publish", "label": "Publish the research", "description": "+80 cr, +4 scientists; Lysa trusts you",
               "bonus": 80, "faction": "scientists", "reputation": 4, "relationship": 3},
              {"id": "share", "label": "Share with the frontier clinics", "description": "+120 cr, +3 diplomats; Lysa loses exclusive access",
               "bonus": 120, "faction": "diplomats", "reputation": 3, "relationship": -1}]},
         {"port": "Haven", "kind": "finish", "title": "Present the archive report",
          "description": "Debrief at Haven and record the fate of the findings."}]},
    {"id": "expedition-blackwake", "title": "The Blackwake Accord", "issuer_npc": "sable-rook",
     "description": "Sable Rook has intercepted a failing fuel shipment near Drift. You can negotiate with the raiders—or bring the patrols in.",
     "reward": 590, "stages": [
         {"port": "Kepler", "kind": "load", "title": "Acquire emergency fuel",
          "description": "Purchase 4 fuel units at Kepler to stabilize the stricken convoy.", "good": "fuel", "quantity": 4},
         {"port": "Drift", "kind": "deliver_choice", "title": "A dangerous bargain",
          "description": "Deliver the fuel and decide whose terms the convoy will follow.",
          "good": "fuel", "quantity": 4, "choices": [
              {"id": "accord", "label": "Strike a truce with Rook", "description": "+120 cr, +4 pirates; Sable becomes an ally",
               "bonus": 120, "faction": "pirates", "reputation": 4, "relationship": 3},
              {"id": "patrol", "label": "Call in the patrols", "description": "+180 cr, +4 security; Sable becomes a rival",
               "bonus": 180, "faction": "security", "reputation": 4, "relationship": -3}]},
         {"port": "Haven", "kind": "finish", "title": "Register the accord",
          "description": "Return to Haven with the outcome of the blockade."}]},
)
NPC_CAPTAINS = (
    {"id": "mara-venn", "name": "Mara Venn", "vessel": "Blue Lantern", "faction": "traders",
     "good": "food", "route": ["Meridian", "Bastion"], "quantity": 4, "phase": 0,
     "description": "Independent provisioner competing for the fortress station's supply contracts."},
    {"id": "rin-kestrel", "name": "Rin Kestrel", "vessel": "Copper Finch", "faction": "miners",
     "good": "ore", "route": ["Prospect", "Cinder"], "quantity": 3, "phase": 2,
     "description": "A mining captain with old debts at the Cinder foundry."},
    {"id": "lysa-quell", "name": "Dr. Lysa Quell", "vessel": "Morning Glass", "faction": "scientists",
     "good": "medicine", "route": ["Aurora", "Eidolon"], "quantity": 2, "phase": 4,
     "description": "A research courier carrying fragile samples to the frontier observatory."},
    {"id": "sable-rook", "name": "Sable Rook", "vessel": "Blackwake", "faction": "pirates",
     "good": "fuel", "route": ["Kepler", "Drift"], "quantity": 3, "phase": 1,
     "description": "A contraband runner whose deals shift fuel prices along the salvage corridor."},
)
HAVEN_FACILITIES = {
    "repair_bay": {"name": "Repair bay", "max_level": 3, "credits": 240,
                   "good": "ore", "quantity": 3,
                   "effect": "15% less hull repair cost per level"},
    "warehouse": {"name": "Export warehouse", "max_level": 3, "credits": 200,
                  "good": "ore", "quantity": 2,
                  "effect": "+40 units of export storage per level"},
    "intelligence": {"name": "Intelligence office", "max_level": 2, "credits": 330,
                     "good": "medicine", "quantity": 2,
                     "effect": "Level 1 charts ports and reveals route hazards; level 2 raises encounter payouts"},
}
ENCOUNTER_SITES = {
    "Kepler": {"title": "The Drifting Tug", "description": "A silent cargo tug is transmitting a weak distress beacon.",
        "choices": [
            {"id": "tow", "label": "Tow the crew to safety", "description": "2 fuel → +145 cr, +2 diplomats",
             "fuel": 2, "credits": 145, "faction": "diplomats", "standing": 2},
            {"id": "log", "label": "Log its coordinates", "description": "No cost → +50 cr, +1 explorers",
             "credits": 50, "faction": "explorers", "standing": 1}]},
    "Vesper": {"title": "The Glasshouse Quarantine", "description": "A research habitat has quarantined its greenhouse after a mysterious blight.",
        "choices": [
            {"id": "treat", "label": "Supply the researchers", "description": "2 medicine → +210 cr, +3 scientists",
             "cargo": {"medicine": 2}, "credits": 210, "faction": "scientists", "standing": 3},
            {"id": "scan", "label": "Record the blight", "description": "No cost → +55 cr, +1 explorers",
             "credits": 55, "faction": "explorers", "standing": 1}]},
    "Prospect": {"title": "The Hollow Seam", "description": "A mining shaft opens onto a strange, unmapped cavern.",
        "choices": [
            {"id": "descend", "label": "Risk a deep salvage dive", "description": "6 hull → +100 cr, 2 ore, +2 miners",
             "hull": 6, "credits": 100, "loot": {"ore": 2}, "faction": "miners", "standing": 2},
            {"id": "chart", "label": "Survey from orbit", "description": "No cost → +55 cr, +1 explorers",
             "credits": 55, "faction": "explorers", "standing": 1}]},
    "Meridian": {"title": "The Vanishing Convoy", "description": "Merchant escorts report cargo disappearing along a profitable trade lane.",
        "choices": [
            {"id": "escort", "label": "Escort the next freighter", "description": "2 fuel → +175 cr, +2 security",
             "fuel": 2, "credits": 175, "faction": "security", "standing": 2},
            {"id": "lead", "label": "Sell the trade-lane report", "description": "No cost → +65 cr, +1 traders",
             "credits": 65, "faction": "traders", "standing": 1}]},
    "Cinder": {"title": "Cooling Tower Seven", "description": "A furnace station has lost coolant and its operators need immediate help.",
        "choices": [
            {"id": "cool", "label": "Divert emergency fuel", "description": "3 ship fuel → +190 cr, +2 miners",
             "fuel": 3, "credits": 190, "faction": "miners", "standing": 2},
            {"id": "warn", "label": "Broadcast a local hazard warning", "description": "No cost → +55 cr, +1 security",
             "credits": 55, "faction": "security", "standing": 1}]},
    "Aurora": {"title": "The Shelter Convoy", "description": "A remote clinic is sheltering more passengers than its food stores can support.",
        "choices": [
            {"id": "feed", "label": "Feed the evacuees", "description": "2 food → +180 cr, +3 diplomats",
             "cargo": {"food": 2}, "credits": 180, "faction": "diplomats", "standing": 3},
            {"id": "diagnose", "label": "Study the storm front", "description": "No cost → +60 cr, +1 scientists",
             "credits": 60, "faction": "scientists", "standing": 1}]},
    "Drift": {"title": "Derelict in the Haze", "description": "A wreck drifts out of the ion cloud with its cargo hold still sealed.",
        "choices": [
            {"id": "board", "label": "Board the derelict", "description": "7 hull → +170 cr, 1 iridium, +2 explorers",
             "hull": 7, "credits": 170, "loot": {"iridium": 1}, "faction": "explorers", "standing": 2},
            {"id": "record", "label": "Record its last position", "description": "No cost → +50 cr, +1 explorers",
             "credits": 50, "faction": "explorers", "standing": 1}]},
    "Bastion": {"title": "Refugees at the Gate", "description": "Station security cannot supply a newly arrived refugee flotilla.",
        "choices": [
            {"id": "rations", "label": "Donate emergency rations", "description": "3 food → +230 cr, +3 diplomats",
             "cargo": {"food": 3}, "credits": 230, "faction": "diplomats", "standing": 3},
            {"id": "patrol", "label": "Patrol the approach", "description": "2 fuel → +130 cr, +2 security",
             "fuel": 2, "credits": 130, "faction": "security", "standing": 2},
            {"id": "refer", "label": "Refer them to aid groups", "description": "No cost → +40 cr, +1 diplomats",
             "credits": 40, "faction": "diplomats", "standing": 1}]},
    "Eidolon": {"title": "The Memory Vault", "description": "An ancient observatory contains a sealed biological archive.",
        "choices": [
            {"id": "recover", "label": "Open the vault carefully", "description": "5 hull → +180 cr, 1 mycelium, +2 scientists",
             "hull": 5, "credits": 180, "loot": {"mycelium": 1}, "faction": "scientists", "standing": 2},
            {"id": "catalog", "label": "Document the markings", "description": "No cost → +80 cr, +1 explorers",
             "credits": 80, "faction": "explorers", "standing": 1}]},
}
LOCAL_ENCOUNTER_TEMPLATES = (
    {"title": "Emergency Shelter", "description": "A passing family ship needs food and a safe berth.",
     "choices": [
         {"id": "feed", "label": "Share 2 food", "description": "2 food → +130 cr, +2 diplomats",
          "cargo": {"food": 2}, "credits": 130, "faction": "diplomats", "standing": 2},
         {"id": "relay", "label": "Forward their distress report", "description": "No cost → +30 cr, +1 explorers",
          "credits": 30, "faction": "explorers", "standing": 1}]},
    {"title": "Survey Drone Adrift", "description": "A mapping drone is tumbling toward the navigation lane.",
     "choices": [
         {"id": "recover", "label": "Recover the drone", "description": "2 ship fuel → +115 cr, +2 scientists",
          "fuel": 2, "credits": 115, "faction": "scientists", "standing": 2},
         {"id": "record", "label": "Record its position", "description": "No cost → +25 cr, +1 explorers",
          "credits": 25, "faction": "explorers", "standing": 1}]},
    {"title": "Scattered Salvage", "description": "An asteroid has shattered a cargo container in the approach corridor.",
     "choices": [
         {"id": "salvage", "label": "Risk a salvage sortie", "description": "4 hull → +70 cr, 1 ore, +2 miners",
          "hull": 4, "loot": {"ore": 1}, "credits": 70, "faction": "miners", "standing": 2},
         {"id": "report", "label": "Report the debris", "description": "No cost → +25 cr, +1 security",
          "credits": 25, "faction": "security", "standing": 1}]},
    {"title": "Unscheduled Patrol", "description": "Port controllers request help tracing a suspicious freighter.",
     "choices": [
         {"id": "escort", "label": "Burn fuel for a patrol", "description": "2 ship fuel → +120 cr, +2 security",
          "fuel": 2, "credits": 120, "faction": "security", "standing": 2},
         {"id": "log", "label": "File an observation", "description": "No cost → +30 cr, +1 traders",
          "credits": 30, "faction": "traders", "standing": 1}]},
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
    haven_facilities: dict[str, int] = field(default_factory=dict)
    encounters: dict = field(default_factory=dict)
    npc_captains: dict = field(default_factory=dict)
    npc_shipments: list[dict] = field(default_factory=list)
    local_encounters: dict = field(default_factory=dict)
    faction_followups: dict = field(default_factory=dict)
    captain_deals: dict = field(default_factory=dict)

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
        for facility in HAVEN_FACILITIES:
            self.haven_facilities.setdefault(facility, 0)
        for template in NPC_CAPTAINS:
            cycle = (self.tick + template["phase"]) // NPC_INTERVAL
            self.npc_captains.setdefault(template["id"], {
                **deepcopy(template), "location": template["route"][cycle % 2],
                "last_cycle": cycle, "relationship": 0, "runs": 0,
                "total_delivered": 0})
        if self.active_ship_id not in self.fleet:
            self.active_ship_id = next(iter(self.fleet), "")
        if self.active_ship_id:
            self._bind_ship()
        if not self.local_jobs:
            self._replenish_local_jobs()
        self._replenish_vip_jobs()
        self._refresh_sector_events()
        self._refresh_local_encounters()
        # New authored expeditions appear in existing saves without resetting
        # completed or in-progress missions from earlier releases.
        for template in EXPEDITION_TEMPLATES:
            self.expeditions.setdefault(template["id"], {
                **deepcopy(template), "status": "offered", "stage": 0,
                "bonus": 0, "choice": None, "accepted_tick": None})
        for port in self.visited_ports:
            self._reveal_encounter(port)
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
        hostile = next((captain for captain in self.npc_captains.values()
                        if captain["good"] == good and captain["relationship"] <= -2), None)
        if hostile:
            # A rival controls the supply lane. The deadline is tighter, but
            # the posted reward includes a real disruption premium.
            reward = reward * 125 // 100
            deadline = max(self.tick + 2, deadline - 1)
        event = {"id": event_id, "cycle": cycle, "title": title,
                 "port": port, "origin": origin, "good": good,
                 "description": description, "start_tick": cycle * INCIDENT_INTERVAL,
                 "end_tick": deadline + 1, "quantity": quantity,
                 "reward": reward, "job_id": event_id,
                 "source": "simulated", "hostile_captain": hostile["id"] if hostile else None}
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
        open_jobs = [job for job in self.local_jobs.values()
                     if job["status"] == "open" and job.get("kind") not in ("rival", "followup")]
        for job in reversed(open_jobs):
            if len(open_jobs) <= 3:
                break
            if job.get("kind") != "dispatch":
                job["status"] = "superseded"
                open_jobs.remove(job)

    def active_sector_events(self) -> list[dict]:
        return [event for event in self.sector_events
                if event["start_tick"] <= self.tick < event["end_tick"]]

    def _refresh_local_encounters(self):
        """One repeatable local decision per cycle, without radio traffic."""
        for event in self.local_encounters.values():
            if event["status"] == "open" and self.tick > event["deadline"]:
                event["status"] = "expired"
        cycle = self.tick // ENCOUNTER_INTERVAL
        event_id = f"local-encounter-{cycle:06d}"
        if event_id not in self.local_encounters:
            template = deepcopy(LOCAL_ENCOUNTER_TEMPLATES[(self.seed + cycle) % len(LOCAL_ENCOUNTER_TEMPLATES)])
            port = PORT_NAMES[1 + ((self.seed * 3 + cycle * 5) % (len(PORT_NAMES) - 1))]
            self.local_encounters[event_id] = {
                **template, "id": event_id, "port": port, "status": "open",
                "start_tick": cycle * ENCOUNTER_INTERVAL,
                "deadline": (cycle + 1) * ENCOUNTER_INTERVAL + 6,
                "source": "local_simulation"}
        if len(self.local_encounters) > 16:
            for key in list(self.local_encounters)[:-16]:
                del self.local_encounters[key]

    def _advance_faction_followups(self):
        """A completed relationship arc offers one later, playable consequence."""
        for followup in self.faction_followups.values():
            if followup["status"] != "pending" or self.tick < followup["due_tick"]:
                continue
            captain = self.npc_captains[followup["npc_id"]]
            good = captain["good"]
            job_id = "followup-" + followup["expedition_id"]
            friendly = followup.get("friendly", True)
            quantity = 2 if friendly else 3
            self.local_jobs[job_id] = {
                "id": job_id, "kind": "followup", "npc_id": captain["id"],
                "title": followup["title"], "description": followup["description"],
                "origin": captain["location"], "destination": "Haven", "good": good,
                "quantity": quantity, "reward": (210 if friendly else 340) + BASE_PRICE[good] * quantity,
                "deadline": self.tick + (48 if friendly else 30), "status": "open"}
            followup.update(status="available", job_id=job_id, activated_tick=self.tick)
            self.journal.append({"id": "followup-ready-" + followup["expedition_id"],
                "tick": self.tick, "action": "followup_available",
                "result": {"title": followup["title"], "captain": captain["name"],
                           "origin": captain["location"], "good": good}})

    def _advance_npc_captains(self):
        """Advance named local haulers; stock is transferred, never generated.

        When opening a long-idle save, cap the number of simulated shipments so
        months of unattended play do not exhaust markets or flood history.
        Their final positions still follow the deterministic shared tick.
        """
        for captain in self.npc_captains.values():
            route = captain["route"]
            target_cycle = (self.tick + captain["phase"]) // NPC_INTERVAL
            current_cycle = captain["last_cycle"]
            if target_cycle <= current_cycle:
                continue
            # Only replay the latest 24 movements after a long absence.
            start_cycle = max(current_cycle, target_cycle - 24)
            captain["location"] = route[start_cycle % 2]
            for cycle in range(start_cycle + 1, target_cycle + 1):
                origin, destination = captain["location"], route[cycle % 2]
                origin_stock = self.galaxies["home"]["ports"][origin]["stock"]
                destination_stock = self.galaxies["home"]["ports"][destination]["stock"]
                good = captain["good"]
                quantity = min(captain["quantity"], origin_stock[good],
                               max(0, 300 - destination_stock[good]))
                origin_stock[good] -= quantity
                destination_stock[good] += quantity
                captain["location"] = destination
                captain["runs"] += 1
                captain["total_delivered"] += quantity
                self.npc_shipments.append({"id": captain["id"] + "-" + str(cycle),
                    "npc_id": captain["id"], "name": captain["name"],
                    "tick": cycle * NPC_INTERVAL - captain["phase"],
                    "origin": origin, "destination": destination,
                    "good": good, "quantity": quantity})
                # A nearby operator can beat a captain to the delivery, but
                # has two full movement cycles to assemble the same cargo.
                departure_tick = cycle * NPC_INTERVAL - captain["phase"]
                open_rivals = sum(j["status"] == "open" and j.get("kind") == "rival"
                                  for j in self.local_jobs.values())
                if (quantity >= 2 and cycle % 4 == captain["phase"] % 4
                        and departure_tick >= self.tick - NPC_INTERVAL
                        and open_rivals < 2 and origin_stock[good] >= 2):
                    count = min(3, origin_stock[good])
                    job_id = f"rival-{captain['id']}-{cycle}"
                    self.local_jobs.setdefault(job_id, {
                        "id": job_id, "kind": "rival", "npc_id": captain["id"],
                        "title": f"Race {captain['name']} to {destination}",
                        "description": f"Move {good} before {captain['vessel']} claims the contract.",
                        "origin": origin, "destination": destination,
                        "good": good, "quantity": count,
                        "reward": BASE_PRICE[good] * count * 3 + 80,
                        "deadline": departure_tick + NPC_INTERVAL * 2,
                        "status": "open"})
            captain["last_cycle"] = target_cycle
        self.npc_shipments = self.npc_shipments[-24:]

    def captain_deal_quote(self, npc_id: str) -> dict:
        """A relationship-gated lot drawn from existing port stock."""
        captain = self.npc_captains.get(npc_id)
        if not captain:
            raise GameError("unknown captain")
        port, good = captain["location"], captain["good"]
        at_home = self.ship.get("galaxy", "home") == "home"
        stock = self.galaxies["home"]["ports"][port]["stock"][good]
        normal = self.price(port, good, "buy") if at_home else 0
        # A private lot must never be immediately profitable to sell back at
        # the same port. Price the future sale against the stock AFTER all
        # three reserved units are removed, not the pre-purchase market.
        floor = (self.price(port, good, "sell", stock_override=max(0, stock - 3)) + 1
                 if at_home else 0)
        unit = max(floor, normal * 85 // 100)
        next_tick = self.captain_deals.get(npc_id, -24) + 24
        return {"npc_id": npc_id, "captain": captain["name"], "port": port,
                "good": good, "unit_price": unit, "normal_price": normal,
                "max_quantity": min(3, stock), "next_tick": next_tick,
                "available": at_home and captain["relationship"] >= 2
                and self.tick >= next_tick and stock > 0}

    def _buy_captain_deal(self, npc_id: str, amount: int) -> dict:
        self._available()
        quote = self.captain_deal_quote(npc_id)
        if self.ship.get("galaxy", "home") != "home" or self.location != quote["port"]:
            raise GameError("meet the captain at their current starport")
        if not quote["available"]:
            raise GameError("private lot unavailable; improve your relationship or wait for restock")
        if type(amount) is not int or not 1 <= amount <= quote["max_quantity"]:
            raise GameError("choose one to three units from the available lot")
        total = quote["unit_price"] * amount
        if self.credits < total:
            raise GameError("insufficient credits")
        if self.cargo_used() + self.incoming_reserved + amount > self.ship["capacity"]:
            raise GameError("cargo hold full")
        good = quote["good"]
        self.ports[self.location]["stock"][good] -= amount
        self.cargo[good] += amount
        self.credits -= total
        self.ship.setdefault("export_cargo", {})[good] = (
            self.ship["export_cargo"].get(good, 0) + (amount if self.location != "Haven" else 0))
        self.captain_deals[npc_id] = self.tick
        return {"captain": quote["captain"], "npc_id": npc_id,
                "good": good, "amount": amount, "unit_price": quote["unit_price"],
                "total": total, "next_tick": self.tick + 24}

    def _request_sector_aid(self, event_id: str, npc_id: str) -> dict:
        """Spend one point of goodwill to improve an active local dispatch."""
        self._available()
        if self.ship.get("galaxy", "home") != "home":
            raise GameError("sector aid is only available in your home galaxy")
        event = next((item for item in self.active_sector_events()
                      if item["id"] == event_id), None)
        job = self.local_jobs.get(event_id)
        captain = self.npc_captains.get(npc_id)
        if not event or not job or job["status"] != "open":
            raise GameError("this sector dispatch is no longer active")
        if event.get("aid_by"):
            raise GameError("this dispatch already has captain support")
        if not captain or captain["relationship"] < 2:
            raise GameError("earn the captain's trust before requesting aid")
        if self.location != captain["location"]:
            raise GameError("meet the captain at their current starport")
        captain["relationship"] -= 1
        bonus = max(1, job["reward"] // 5)
        job["reward"] += bonus
        job["deadline"] += 4
        job["aid_by"] = captain["id"]
        event.update(aid_by=captain["id"], reward=job["reward"],
                     end_tick=max(event["end_tick"], job["deadline"] + 1))
        return {"event_id": event_id, "captain": captain["name"],
                "bonus": bonus, "reward": job["reward"],
                "deadline": job["deadline"], "relationship": captain["relationship"]}

    def _reveal_encounter(self, port: str) -> bool:
        if port not in ENCOUNTER_SITES or port in self.encounters:
            return False
        self.encounters[port] = {**deepcopy(ENCOUNTER_SITES[port]),
                                 "port": port, "status": "open",
                                 "discovered_tick": self.tick}
        return True

    def _resolve_encounter(self, port: str, choice: str) -> dict:
        """A site resolves exactly once, with physical ship costs and rewards."""
        self._available()
        encounter = self.encounters.get(port)
        if self.ship.get("galaxy", "home") != "home" or self.location != port:
            raise GameError("dock at the encounter's starport")
        if not encounter or encounter["status"] != "open":
            raise GameError("this discovery has already been resolved")
        option = next((c for c in encounter["choices"] if c["id"] == choice), None)
        if option is None:
            raise GameError("choose a valid encounter outcome")
        outcome = self._apply_encounter_option(encounter, option)
        encounter.update(status="resolved", choice=choice, resolved_tick=self.tick)
        return outcome

    def _resolve_local_encounter(self, incident_id: str, choice: str) -> dict:
        self._available()
        event = self.local_encounters.get(incident_id)
        if not event or event["status"] != "open" or self.tick > event["deadline"]:
            raise GameError("this local encounter is no longer available")
        if self.ship.get("galaxy", "home") != "home" or self.location != event["port"]:
            raise GameError("dock at the encounter's starport")
        option = next((c for c in event["choices"] if c["id"] == choice), None)
        if option is None:
            raise GameError("choose a valid encounter outcome")
        outcome = self._apply_encounter_option(event, option)
        event.update(status="resolved", choice=choice, resolved_tick=self.tick)
        return {**outcome, "incident_id": incident_id, "recurring": True}

    def _apply_encounter_option(self, encounter: dict, option: dict) -> dict:
        fuel_cost, hull_cost = option.get("fuel", 0), option.get("hull", 0)
        spent = option.get("cargo", {})
        loot = option.get("loot", {})
        if self.ship["fuel"] < fuel_cost:
            raise GameError("insufficient fuel for that encounter choice")
        if self.ship["condition"] - hull_cost < 10:
            raise GameError("repair your ship before risking that salvage operation")
        if any(self.cargo.get(good, 0) < count for good, count in spent.items()):
            raise GameError("load the requested supplies before choosing this outcome")
        if self.cargo_used() - sum(spent.values()) + sum(loot.values()) > self.ship["capacity"]:
            raise GameError("free cargo space before collecting this salvage")
        self.ship["fuel"] -= fuel_cost
        self.ship["condition"] -= hull_cost
        for good, count in spent.items():
            self.cargo[good] -= count
            self.ship.setdefault("export_cargo", {})[good] = max(
                0, self.ship["export_cargo"].get(good, 0) - count)
            self.ports[encounter["port"]]["stock"][good] += count
        for good, count in loot.items():
            self.cargo[good] += count
        payout = option["credits"]
        if self.haven_facilities.get("intelligence", 0) >= 2:
            payout = payout * 125 // 100
        self.credits += payout
        self.factions[option["faction"]] += option["standing"]
        return {"port": encounter["port"], "title": encounter["title"],
                "outcome": option["label"], "reward": payout,
                "fuel_spent": fuel_cost, "hull_spent": hull_cost,
                "cargo_spent": deepcopy(spent), "salvage": deepcopy(loot),
                "faction": option["faction"], "standing": option["standing"]}

    def haven_warehouse_capacity(self) -> int:
        return 60 + 40 * self.haven_facilities.get("warehouse", 0)

    def haven_upgrade_quote(self, facility: str) -> dict:
        template = HAVEN_FACILITIES.get(facility)
        if not template:
            raise GameError("unknown Haven facility")
        level = self.haven_facilities.get(facility, 0)
        return {"facility": facility, "name": template["name"], "level": level,
                "max_level": template["max_level"], "effect": template["effect"],
                "credits": template["credits"] * (level + 1),
                "good": template["good"], "quantity": template["quantity"] * (level + 1)}

    def _upgrade_haven(self, facility: str) -> dict:
        self._available()
        if self.ship.get("galaxy", "home") != "home" or self.location != "Haven":
            raise GameError("return to Haven to expand headquarters")
        quote = self.haven_upgrade_quote(facility)
        if quote["level"] >= quote["max_level"]:
            raise GameError("facility already at maximum level")
        if self.credits < quote["credits"]:
            raise GameError("insufficient credits for this headquarters upgrade")
        good, amount = quote["good"], quote["quantity"]
        if (self.cargo.get(good, 0) < amount or
                self.ship.get("export_cargo", {}).get(good, 0) < amount):
            raise GameError(f"import {amount} {good} from a different starport to build this facility")
        self.cargo[good] -= amount
        self.ship["export_cargo"][good] -= amount
        self.credits -= quote["credits"]
        self.haven_facilities[facility] = quote["level"] + 1
        return {"facility": facility, "name": quote["name"],
                "level": self.haven_facilities[facility], "credits_spent": quote["credits"],
                "good": good, "quantity": amount, "effect": quote["effect"]}

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
            chosen = None
            if choice_stage:
                chosen = next((item for item in choice_stage["choices"]
                               if item["id"] == mission["choice"]), None)
                if chosen:
                    self.factions[chosen["faction"]] += chosen["reputation"]
            captain = self.npc_captains.get(mission.get("issuer_npc"))
            relationship_delta = chosen.get("relationship", 0) if chosen else 0
            if captain:
                captain["relationship"] = max(-5, min(5, captain["relationship"] + relationship_delta))
            self.credits += reward
            self.factions["traders"] += 2
            mission["status"] = "completed"
            mission["completed_tick"] = self.tick
            mission["payout"] = reward
            if captain and mission["id"] not in self.faction_followups:
                aligned = relationship_delta > 0
                self.faction_followups[mission["id"]] = {
                    "expedition_id": mission["id"], "npc_id": captain["id"],
                    "status": "pending", "due_tick": self.tick + 12, "friendly": aligned,
                    "title": ("A Favor from " if aligned else "A Challenge from ") + captain["name"],
                    "description": ("Your help earned a priority freight offer." if aligned else
                                    "Your rival demands that you prove yourself on a difficult delivery.")}
            return {"expedition_id": expedition_id, "title": mission["title"],
                    "stage_title": stage["title"], "completed": True,
                    "reward": reward, "choice": mission["choice"],
                    "captain": captain["name"] if captain else None,
                    "relationship_delta": relationship_delta if captain else 0,
                    "relationship": captain["relationship"] if captain else None}
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
                job["status"] = "claimed" if job.get("kind") == "rival" else "expired"
                if job.get("kind") == "rival":
                    captain = self.npc_captains.get(job["npc_id"])
                    self.journal.append({"id": "npc-claim-" + job["id"],
                        "tick": self.tick, "action": "npc_claim",
                        "result": {"job_id": job["id"], "captain": captain["name"] if captain else "A rival",
                                   "good": job["good"], "destination": job["destination"]}})
                elif job.get("kind") == "followup":
                    for followup in self.faction_followups.values():
                        if followup.get("job_id") == job["id"]:
                            followup["status"] = "expired"
        if len(self.local_jobs) > 100:
            history = [key for key, job in self.local_jobs.items() if job["status"] != "open"]
            for key in history[:len(self.local_jobs) - 100]:
                del self.local_jobs[key]
        open_jobs = sum(job["status"] == "open" and job.get("kind") not in ("rival", "followup")
                        for job in self.local_jobs.values())
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

    def _deliver_local(self, job_id: str, resolution: str = "commercial") -> dict:
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
        if resolution not in ("commercial", "reconcile") or (
                resolution == "reconcile" and job.get("kind") != "followup"):
            raise GameError("choose a valid faction follow-up resolution")
        self.cargo[job["good"]] -= job["quantity"]
        eligible = self.ship.setdefault("export_cargo", {})
        eligible[job["good"]] = max(0, eligible.get(job["good"], 0) - job["quantity"])
        self.ports[self.location]["stock"][job["good"]] += job["quantity"]
        payout = job["reward"] if resolution == "commercial" else job["reward"] // 2
        self.credits += payout
        self.factions["traders"] += 1
        if resolution == "reconcile":
            self.factions[self.npc_captains[job["npc_id"]]["faction"]] += 2
        job["status"] = "delivered"
        job["completed_tick"] = self.tick
        job["resolution"] = resolution
        captain = self.npc_captains.get(job.get("npc_id"))
        if captain and job.get("kind") in ("rival", "followup"):
            captain["relationship"] = max(-5, min(5, captain["relationship"] +
                                                   (3 if resolution == "reconcile" else 1)))
        if job.get("kind") == "followup":
            for followup in self.faction_followups.values():
                if followup.get("job_id") == job_id:
                    followup.update(status="completed", resolution=resolution)
        self._replenish_local_jobs()
        return {"job_id": job_id, "reward": payout, "credits": self.credits,
                "captain": captain["name"] if captain else None,
                "kind": job.get("kind"), "resolution": resolution}

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
                    if ship.get("galaxy", "home") == "home" and self._reveal_encounter(ship["location"]):
                        encounter = self.encounters[ship["location"]]
                        self.journal.append({"id": "site-" + ship["location"],
                            "tick": self.tick, "action": "discover_site",
                            "result": {"port": ship["location"], "title": encounter["title"]}})
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

    def price(self, port: str, good: str, action: str,
              *, stock_override: int | None = None) -> int:
        self._check_port_good(port, good)
        if action not in ("buy", "sell"):
            raise GameError("action must be buy or sell")
        stock = self.ports[port]["stock"][good] if stock_override is None else stock_override
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
        # A recurring captain offers a modest local deal (or surcharge) on
        # their own commodity, depending on your completed expedition choice.
        if action == "buy":
            for captain in self.npc_captains.values():
                if captain["location"] == port and captain["good"] == good:
                    multiplier -= 2 * captain["relationship"]
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
            elif action == "buy_captain_deal":
                result = self._buy_captain_deal(**kwargs)
            elif action == "request_sector_aid":
                result = self._request_sector_aid(**kwargs)
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
            elif action == "resolve_encounter":
                result = self._resolve_encounter(**kwargs)
            elif action == "resolve_local_encounter":
                result = self._resolve_local_encounter(**kwargs)
            elif action == "upgrade_haven":
                result = self._upgrade_haven(**kwargs)
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
        if sum(self.export_warehouse.values()) + amount > self.haven_warehouse_capacity():
            raise GameError("Haven export warehouse is full; expand its storage or reserve goods for delivery")
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
            self._advance_npc_captains()
            self._refresh_sector_events()
            self._refresh_local_encounters()
        self._replenish_local_jobs()
        self._advance_faction_followups()
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
            self._advance_npc_captains()
            self.clock_epoch = epoch
            self._refresh_sector_events()
            self._refresh_local_encounters()
            self._replenish_local_jobs()
            self._advance_faction_followups()
            self.observe_markets()
        return {"epoch": self.clock_epoch, "advanced": elapsed, "tick": self.tick}

    def _repair(self) -> dict:
        self._available()
        discount_percent = 15 * self.haven_facilities.get("repair_bay", 0)
        cost = math.ceil((100 - self.ship["condition"]) * 2 * (100 - discount_percent) / 100)
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
