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
ARTIFACT_CATALOG = (
    {"category": "echo", "name": "Relay echo crystal", "rarity": "common", "base_value": 180},
    {"category": "chart", "name": "Precursor star chart", "rarity": "uncommon", "base_value": 260},
    {"category": "glyph", "name": "Engraved signal glyph", "rarity": "uncommon", "base_value": 340},
    {"category": "seed", "name": "Vacuum-grown seed", "rarity": "rare", "base_value": 460},
    {"category": "lattice", "name": "Voidglass lattice", "rarity": "rare", "base_value": 580},
    {"category": "memory", "name": "Mnemonic star core", "rarity": "relic", "base_value": 750},
)
ARTIFACT_TYPES = {item["category"]: item for item in ARTIFACT_CATALOG}
BASE_PRICE = {"food": 12, "ore": 20, "fuel": 20, "medicine": 46,
              "aether": 180, "iridium": 220, "mycelium": 160}
LOAN_PLANS = {
    "emergency": {"name": "Emergency advance", "principal": 300,
                  "interest_percent": 10, "installments": 6, "interval_ticks": 4},
    "frontier": {"name": "Frontier expansion loan", "principal": 900,
                 "interest_percent": 18, "installments": 9, "interval_ticks": 8},
}
PORT_NAMES = ("Haven", "Kepler", "Vesper", "Prospect", "Meridian",
              "Cinder", "Aurora", "Drift", "Bastion", "Eidolon")
PORT_ROLES = ("Home hub", "Refinery", "Research enclave", "Mining colony",
              "Trade exchange", "Industrial furnace", "Medical sanctuary",
              "Salvage outpost", "Fortress station", "Frontier observatory")
EQUIPMENT = {"scanner": 220, "shield": 350, "navigator": 420, "defense": 380}
CREW_ROLES = {
    "pilot": {"name": "Pilot", "effect": "Save 1 fuel per skill level on local flights; veterans fly faster"},
    "engineer": {"name": "Engineer", "effect": "Reduce local flight damage and repair costs"},
    "broker": {"name": "Broker", "effect": "Earn 5% more on local freight per skill level"},
    "signal": {"name": "Signal officer", "effect": "Protect hull during failed real RF transfers; train on confirmed deliveries"},
}
CREW_NAMES = ("Ari Vale", "Nia Soren", "Jax Moreno", "Elara Quinn",
              "Ren Osei", "Mira Sol", "Tavi Reyes", "Sera Moss",
              "Kai Mercer", "Lyra Chen", "Dax Imani", "Noor Venn")
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
FACTION_STORYLINES = {
    "mara-venn": {"ally": "The Meridian Trade Compact", "rival": "Meridian's Closed Doors",
                  "perk": "trade_charter", "perk_name": "Independent trade charter",
                  "description": "Mara offers access to her independent cargo network."},
    "rin-kestrel": {"ally": "The Prospect Foundry Pact", "rival": "The Foundry Debt",
                    "perk": "reinforced_plating", "perk_name": "Foundry-reinforced plating",
                    "description": "Rin's foundry can harden your fleet for dangerous routes."},
    "lysa-quell": {"ally": "The Aurora Survey Initiative", "rival": "Quell's Ethics Hearing",
                   "perk": "survey_uplink", "perk_name": "Survey uplink",
                   "description": "Quell can share her research team's frontier discoveries."},
    "sable-rook": {"ally": "Blackwake Safe Passage", "rival": "The Blackwake Vendetta",
                    "perk": "pirate_codes", "perk_name": "Blackwake passage codes",
                    "description": "Rook knows which pirate patrols to avoid and which to pay."},
}
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
    "shipyard": {"name": "Shipyard gantry", "max_level": 2, "credits": 480,
                 "good": "ore", "quantity": 4,
                 "effect": "10% cheaper new ships at Haven per level"},
    "logistics": {"name": "Cargo exchange", "max_level": 2, "credits": 340,
                  "good": "medicine", "quantity": 2,
                  "effect": "Unlock multi-resource Haven requisitions; +10% Haven freight pay per level"},
    "liaison": {"name": "Faction liaison", "max_level": 2, "credits": 300,
                "good": "food", "quantity": 3,
                "effect": "Private captain lots refresh four ticks sooner per level"},
    "fuel_works": {"name": "Rare-fuel synthesis works", "max_level": 2, "credits": 650,
                   "resources": "signature_pair_a", "quantity": 2,
                   "effect": "+2 fuel production at Haven per level"},
    "survey_archive": {"name": "Interstellar survey archive", "max_level": 2, "credits": 700,
                       "resources": "signature_pair_b", "quantity": 2,
                       "effect": "+25% first-visit discovery credits per level"},
    "interstellar_relay": {"name": "Interstellar relay array", "max_level": 1, "credits": 2400,
                            "resources": tuple(RARE), "quantity": 6,
                            "effect": "+25% payout on verified cross-galaxy cargo deliveries"},
    "grand_archive": {"name": "Haven Grand Archive", "max_level": 1, "credits": 2800,
                      "resources": tuple(RARE), "quantity": 4, "archive_required": 10,
                      "effect": "+50 cr for each new starport discovered; completes the artifact gallery"},
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
    loan: dict | None = None
    bankruptcy_notice: dict | None = None
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
    artifact_inventory: dict = field(default_factory=dict)
    artifact_history: dict = field(default_factory=dict)
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
    dockside_work_tick: int = -1
    faction_storylines: dict = field(default_factory=dict)
    faction_perks: list[str] = field(default_factory=list)
    captain_nemeses: list[str] = field(default_factory=list)
    haven_orders: dict = field(default_factory=dict)
    next_haven_order_number: int = 1
    next_haven_order_tick: int = 0
    crew_roster: dict = field(default_factory=dict)
    recruited_candidates: list[str] = field(default_factory=list)
    next_crew_number: int = 1
    warehouse_targets: dict = field(default_factory=dict)
    fleet_credit_reserve: int = 350
    next_warehouse_dispatch_tick: int = 0

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
        self._initialize_starport_graph()
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
            ship.setdefault("fleet_policy", {"return_to_haven": True, "auto_service": False,
                          "repair_below": 65, "fuel_below": 35})
            ship.setdefault("captain_id", None)
        # Crew are recorded once on the roster, not duplicated inside each
        # ship. Recover marooned assignments from older or damaged saves.
        for crew in self.crew_roster.values():
            if crew.get("ship_id") in self.fleet:
                crew["galaxy"] = self.fleet[crew["ship_id"]].get("galaxy", "home")
            else:
                crew["ship_id"] = None
                crew.setdefault("location", "Haven")
                crew.setdefault("galaxy", "home")
        for ship in self.fleet.values():
            if not any(crew.get("ship_id") == ship["id"] for cid, crew in self.crew_roster.items()
                       if cid == ship.get("captain_id")):
                ship["captain_id"] = None
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
        self._refresh_haven_orders()
        # New authored expeditions appear in existing saves without resetting
        # completed or in-progress missions from earlier releases.
        for template in EXPEDITION_TEMPLATES:
            self.expeditions.setdefault(template["id"], {
                **deepcopy(template), "status": "offered", "stage": 0,
                "bonus": 0, "choice": None, "accepted_tick": None})
        self._refresh_faction_storylines()
        for port in self.visited_ports:
            self._reveal_encounter(port)
        # Existing saves may already have reached the old chart's outer edge.
        for port in list(self.visited_ports):
            if port in self.galaxies.get("home", {}).get("ports", {}):
                self._expand_starport_frontier(port)
        self._enforce_open_delivery_shortages()
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
        self._enforce_open_delivery_shortages()

    def _enforce_open_delivery_shortages(self) -> None:
        """Keep posted freight demand larger than stock at its destination."""
        limits = {}
        for job in self.local_jobs.values():
            if job.get("status") != "open":
                continue
            destination, good, quantity = (job.get("destination"), job.get("good"),
                                           job.get("quantity"))
            home_ports = self.galaxies.get("home", {}).get("ports", {})
            if (destination not in home_ports or good not in GOODS or
                    type(quantity) is not int or quantity < 1):
                continue
            key = (destination, good)
            limits[key] = min(limits.get(key, quantity), quantity)
        for (destination, good), quantity in limits.items():
            stock = home_ports[destination]["stock"]
            stock[good] = min(stock[good], quantity - 1)

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

    def _refresh_haven_orders(self) -> None:
        """Post one persistent warehouse procurement job, without RF traffic.

        Offline catch-up expires stale orders but creates only one fresh job,
        rather than backfilling hundreds of unattended procurement cycles.
        """
        for order in self.haven_orders.values():
            if order["status"] == "open" and self.tick > order["deadline"]:
                order["status"] = "expired"
        if self.haven_facilities.get("logistics", 0) < 1:
            return
        if self.tick < self.next_haven_order_tick or any(
                order["status"] == "open" for order in self.haven_orders.values()):
            return
        number = self.next_haven_order_number
        self.next_haven_order_number += 1
        goods = ("food", "ore", "medicine", "fuel", "iridium", "mycelium")
        indexes = [(self.seed + number) % len(goods),
                   (self.seed + number + 2) % len(goods)]
        if self.haven_facilities["logistics"] >= 2:
            indexes.append((self.seed + number + 4) % len(goods))
        requirements = {goods[i]: (1 if goods[i] in ("iridium", "mycelium") else 2 + (number + i) % 2)
                        for i in indexes}
        reward = 250 + sum(BASE_PRICE[good] * amount * 3 for good, amount in requirements.items())
        key = f"haven-order-{number:05d}"
        self.haven_orders[key] = {"id": key, "title": "Haven Station Requisition",
                                  "description": "Import supplies from other worlds and stage them in Haven's warehouse.",
                                  "requirements": requirements, "reward": reward,
                                  "start_tick": self.tick, "deadline": self.tick + 2016,
                                  "status": "open", "source": "local_simulation"}
        self.next_haven_order_tick = self.tick + 48
        if len(self.haven_orders) > 12:
            for key in list(self.haven_orders)[:-12]:
                if self.haven_orders[key]["status"] != "open":
                    del self.haven_orders[key]

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
        self._enforce_open_delivery_shortages()

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
                nemesis = captain["id"] in self.captain_nemeses
                interval = 2 if nemesis else 4
                if (quantity >= 2 and cycle % interval == captain["phase"] % interval
                        and departure_tick >= self.tick - NPC_INTERVAL
                        and open_rivals < 2 and origin_stock[good] >= 2):
                    count = min(3, origin_stock[good])
                    job_id = f"rival-{captain['id']}-{cycle}"
                    self.local_jobs.setdefault(job_id, {
                        "id": job_id, "kind": "rival", "npc_id": captain["id"],
                        "title": ("Vendetta run: " if nemesis else "Race ") + f"{captain['name']} to {destination}",
                        "description": f"Move {good} before {captain['vessel']} claims the contract."
                                       + (" Your feud makes this a priority interception." if nemesis else ""),
                        "origin": origin, "destination": destination,
                        "good": good, "quantity": count,
                        "reward": BASE_PRICE[good] * count * 3 + (180 if nemesis else 80),
                        "deadline": departure_tick + NPC_INTERVAL * (1 if nemesis else 2),
                        "status": "open"})
            captain["last_cycle"] = target_cycle
        self.npc_shipments = self.npc_shipments[-24:]

    def _refresh_faction_storylines(self) -> None:
        """Latch the first trust or feud threshold into an authored choice."""
        for captain in self.npc_captains.values():
            if captain["id"] in self.faction_storylines or abs(captain["relationship"]) < 3:
                continue
            template = FACTION_STORYLINES.get(captain["id"])
            if not template:
                continue
            allied = captain["relationship"] >= 3
            good = captain["good"]
            if allied:
                choices = [
                    {"id": "charter", "label": "Forge the alliance",
                     "description": f"2 {good} and 160 cr → {template['perk_name']}, +2 {captain['faction']} standing",
                     "cargo": {good: 2}, "credits_cost": 160, "relationship": 1,
                     "standing": 2, "perk": template["perk"]},
                    {"id": "cashout", "label": "Take the advance instead",
                     "description": "No cargo → +180 cr, -1 relationship, +1 faction standing",
                     "reward": 180, "relationship": -1, "standing": 1},
                ]
            else:
                choices = [
                    {"id": "truce", "label": "Settle the dispute",
                     "description": f"2 {good} and 120 cr → +3 relationship, +2 {captain['faction']} standing",
                     "cargo": {good: 2}, "credits_cost": 120, "relationship": 3,
                     "standing": 2},
                    {"id": "defy", "label": "Declare a vendetta",
                     "description": "+180 cr now; this captain posts more frequent, tighter rival races",
                     "reward": 180, "relationship": -1, "nemesis": True},
                ]
            scene = {"npc_id": captain["id"], "captain": captain["name"],
                     "title": template["ally"] if allied else template["rival"],
                     "description": template["description"] if allied else
                                    f"{captain['name']} challenges you over the breakdown of your last deal.",
                     "port": captain["route"][0], "alignment": "ally" if allied else "rival",
                     "status": "offered", "opened_tick": self.tick, "choices": choices}
            self.faction_storylines[captain["id"]] = scene
            self.journal.append({"id": "faction-story-" + captain["id"], "tick": self.tick,
                                 "action": "faction_storyline_offered",
                                 "result": {"title": scene["title"], "captain": captain["name"],
                                            "port": scene["port"], "alignment": scene["alignment"]}})

    def _resolve_faction_storyline(self, npc_id: str, choice: str) -> dict:
        self._available()
        scene = self.faction_storylines.get(npc_id)
        if not scene or scene["status"] != "offered":
            raise GameError("this captain's storyline is no longer available")
        if self.ship.get("galaxy", "home") != "home" or self.location != scene["port"]:
            raise GameError(f"meet at {scene['port']} to resolve this storyline")
        option = next((item for item in scene["choices"] if item["id"] == choice), None)
        if not option:
            raise GameError("choose a valid faction outcome")
        cost = option.get("credits_cost", 0)
        if self.credits < cost:
            raise GameError("insufficient credits for this faction outcome")
        for good, quantity in option.get("cargo", {}).items():
            if self.cargo.get(good, 0) < quantity:
                raise GameError(f"load {quantity} {good} before choosing this outcome")
        for good, quantity in option.get("cargo", {}).items():
            self.cargo[good] -= quantity
            eligible = self.ship.setdefault("export_cargo", {})
            eligible[good] = max(0, eligible.get(good, 0) - quantity)
            self.ports[self.location]["stock"][good] += quantity
        reward = option.get("reward", 0)
        self.credits += reward - cost
        captain = self.npc_captains[npc_id]
        captain["relationship"] = max(-5, min(5, captain["relationship"] + option["relationship"]))
        self.factions[captain["faction"]] += option.get("standing", 0)
        perk = option.get("perk")
        if perk and perk not in self.faction_perks:
            self.faction_perks.append(perk)
        if option.get("nemesis") and npc_id not in self.captain_nemeses:
            self.captain_nemeses.append(npc_id)
        scene.update(status="resolved", outcome=choice, resolved_tick=self.tick)
        return {"npc_id": npc_id, "captain": captain["name"], "title": scene["title"],
                "choice": choice, "outcome": option["label"], "credits_delta": reward - cost,
                "cargo_spent": deepcopy(option.get("cargo", {})),
                "relationship": captain["relationship"], "standing": option.get("standing", 0),
                "faction": captain["faction"], "perk": perk, "nemesis": bool(option.get("nemesis"))}

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
        # reserved units are removed, not the pre-purchase market.
        lot_size = 5 if "trade_charter" in self.faction_perks and npc_id == "mara-venn" else 3
        floor = (self.price(port, good, "sell", stock_override=max(0, stock - lot_size)) + 1
                 if at_home else 0)
        unit = max(floor, normal * 85 // 100)
        cooldown = 24 - 4 * self.haven_facilities.get("liaison", 0)
        next_tick = self.captain_deals.get(npc_id, -cooldown) + cooldown
        return {"npc_id": npc_id, "captain": captain["name"], "port": port,
                "good": good, "unit_price": unit, "normal_price": normal,
                "max_quantity": min(lot_size, stock), "next_tick": next_tick,
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
            raise GameError("choose a positive amount within the available lot")
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
        cooldown = 24 - 4 * self.haven_facilities.get("liaison", 0)
        return {"captain": quote["captain"], "npc_id": npc_id,
                "good": good, "amount": amount, "unit_price": quote["unit_price"],
                "total": total, "next_tick": self.tick + cooldown}

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

    def _collect_frontier_artifact(self, port: str) -> dict | None:
        """Award one deterministic, unique collectible for a first discovery."""
        if port in self.artifact_history or port not in self.ports:
            return self.artifact_inventory.get(port)
        index = list(self.ports).index(port)
        template = ARTIFACT_CATALOG[(self.seed + index * 5) % len(ARTIFACT_CATALOG)]
        artifact = {**template, "id": port,
            "title": f"{template['name']} · {port}", "source_port": port,
            "signature": self.specialization, "found_tick": self.tick,
            "status": "held"}
        self.artifact_inventory[port] = deepcopy(artifact)
        self.artifact_history[port] = deepcopy(artifact)
        return artifact

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
        resource_rule = template.get("resources")
        if resource_rule == "signature_pair_a":
            signature_index = RARE.index(self.specialization)
            base_requirements = {self.specialization: template["quantity"],
                                 RARE[(signature_index + 1) % len(RARE)]: template["quantity"]}
        elif resource_rule == "signature_pair_b":
            signature_index = RARE.index(self.specialization)
            base_requirements = {self.specialization: template["quantity"],
                                 RARE[(signature_index + 2) % len(RARE)]: template["quantity"]}
        elif resource_rule:
            base_requirements = {good: template["quantity"] for good in resource_rule}
        else:
            base_requirements = {template["good"]: template["quantity"]}
        requirements = {good: amount * (level + 1)
                        for good, amount in base_requirements.items()}
        primary_good = next(iter(requirements))
        return {"facility": facility, "name": template["name"], "level": level,
                "max_level": template["max_level"], "effect": template["effect"],
                "credits": template["credits"] * (level + 1),
                "good": primary_good, "quantity": requirements[primary_good],
                "requirements": requirements,
                "archive_required": template.get("archive_required", 0),
                "archive_count": len(self.artifact_history)}

    def _upgrade_haven(self, facility: str) -> dict:
        self._available()
        if self.ship.get("galaxy", "home") != "home" or self.location != "Haven":
            raise GameError("return to Haven to expand headquarters")
        quote = self.haven_upgrade_quote(facility)
        if quote["level"] >= quote["max_level"]:
            raise GameError("facility already at maximum level")
        if len(self.artifact_history) < quote["archive_required"]:
            raise GameError(f"catalog {quote['archive_required']} frontier artifacts before building this project")
        if self.credits < quote["credits"]:
            raise GameError("insufficient credits for this headquarters upgrade")
        requirements = quote["requirements"]
        for good, amount in requirements.items():
            if (self.cargo.get(good, 0) < amount or
                    self.ship.get("export_cargo", {}).get(good, 0) < amount):
                raise GameError(f"import {amount} {good} from a different starport to build this facility")
        for good, amount in requirements.items():
            self.cargo[good] -= amount
            self.ship["export_cargo"][good] -= amount
        self.credits -= quote["credits"]
        self.haven_facilities[facility] = quote["level"] + 1
        if facility == "logistics":
            self._refresh_haven_orders()
        elif facility == "fuel_works":
            self.ports["Haven"]["production"]["fuel"] += 2
        return {"facility": facility, "name": quote["name"],
                "level": self.haven_facilities[facility], "credits_spent": quote["credits"],
                "good": quote["good"], "quantity": quote["quantity"],
                "requirements": requirements, "effect": quote["effect"]}

    def _fulfill_haven_order(self, order_id: str) -> dict:
        self._available()
        if self.ship.get("galaxy", "home") != "home" or self.location != "Haven":
            raise GameError("return to Haven to fulfill its station requisitions")
        order = self.haven_orders.get(order_id)
        if not order or order["status"] != "open" or self.tick > order["deadline"]:
            raise GameError("this Haven requisition is no longer available")
        for good, amount in order["requirements"].items():
            if self.export_warehouse.get(good, 0) < amount:
                raise GameError(f"import and unload {amount} {good} into the Haven warehouse")
        for good, amount in order["requirements"].items():
            self.export_warehouse[good] -= amount
        self.credits += order["reward"]
        self.factions["traders"] += 2
        order.update(status="fulfilled", completed_tick=self.tick)
        self._refresh_haven_orders()
        return {"order_id": order_id, "reward": order["reward"],
                "requirements": deepcopy(order["requirements"]),
                "warehouse": deepcopy(self.export_warehouse), "credits": self.credits,
                "source": "local_simulation"}

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
            self._refresh_faction_storylines()
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
            if (job["status"] == "open" and job.get("kind") != "frontier_gate" and
                    self.tick > job["deadline"]):
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

    def _dockside_shift(self) -> dict:
        self._available(maintenance=True)
        if self.dockside_work_tick == self.tick:
            raise GameError("dockside shift already completed this economy tick")
        payout = 75
        self.credits += payout
        self.dockside_work_tick = self.tick
        return {"credits": payout, "balance": self.credits, "next_shift_tick": self.tick + 1}

    def loan_quote(self, plan: str) -> dict:
        terms = LOAN_PLANS.get(plan)
        if not terms:
            raise GameError("unknown loan plan")
        total = terms["principal"] * (100 + terms["interest_percent"]) // 100
        base, remainder = divmod(total, terms["installments"])
        return {"plan": plan, **terms, "total_repayment": total,
                "first_payment": base + (1 if remainder else 0)}

    def _take_loan(self, plan: str) -> dict:
        self._available(maintenance=True)
        if self.loan and self.loan.get("balance", 0) > 0:
            raise GameError("repay your current loan before taking another")
        quote = self.loan_quote(plan)
        terms = LOAN_PLANS[plan]
        base, remainder = divmod(quote["total_repayment"], terms["installments"])
        self.credits += terms["principal"]
        self.bankruptcy_notice = None
        self.loan = {"plan": plan, "name": terms["name"],
            "principal": terms["principal"], "interest": quote["total_repayment"] - terms["principal"],
            "interest_percent": terms["interest_percent"], "balance": quote["total_repayment"],
            "installments_total": terms["installments"],
            "installments_remaining": terms["installments"],
            "installment_base": base, "extra_installments": remainder,
            "due_payment": quote["first_payment"], "interval_ticks": terms["interval_ticks"],
            "next_due_tick": self.tick + terms["interval_ticks"], "payments_made": 0,
            "missed_payments": 0, "collateral_ship_id": self.active_ship_id}
        return {"plan": plan, "name": terms["name"], "principal": terms["principal"],
                "interest": self.loan["interest"], "total_repayment": self.loan["balance"],
                "payment": self.loan["due_payment"],
                "interval_ticks": self.loan["interval_ticks"], "credits": self.credits}

    def _service_loan(self) -> int:
        """Collect due installments and repossess collateral after repeated defaults."""
        paid_total = 0
        while self.loan and self.loan.get("balance", 0) > 0 and self.tick >= self.loan["next_due_tick"]:
            if self.credits < self.loan["due_payment"]:
                self.loan["missed_payments"] += 1
                if self.loan["missed_payments"] >= 3:
                    self._declare_loan_bankruptcy()
                    break
                self.loan["next_due_tick"] += self.loan["interval_ticks"]
                continue
            payment = self.loan["due_payment"]
            self.credits -= payment
            self.loan["balance"] -= payment
            paid_total += payment
            self.loan["missed_payments"] = 0
            self.loan["payments_made"] += 1
            self.loan["installments_remaining"] -= 1
            if self.loan["balance"] <= 0:
                self.loan = None
                break
            self.loan["due_payment"] = self.loan["installment_base"] + int(
                self.loan["payments_made"] < self.loan["extra_installments"])
            self.loan["next_due_tick"] += self.loan["interval_ticks"]
        return paid_total

    def _declare_loan_bankruptcy(self) -> None:
        loan = self.loan
        if not loan:
            return
        collateral_id = loan.get("collateral_ship_id")
        collateral = self.fleet.get(collateral_id)
        debt = loan["balance"]
        sale_value = 0
        if collateral:
            class_id = collateral.get("class_id")
            if class_id:
                from .modems import SHIPS
                hull_cost = next((item["cost"] for item in SHIPS if item["id"] == class_id), 350)
            else:
                hull_cost = (350, 900, 1800)[min(2, collateral.get("modem_tier", 0))]
            sale_value = max(1, hull_cost // 2)
            vip_job = collateral.get("vip_job")
            if vip_job in self.vip_jobs:
                self.vip_jobs[vip_job]["status"] = "lost"
            for crew in self.crew_roster.values():
                if crew.get("ship_id") == collateral_id:
                    crew.update(ship_id=None, location=collateral.get("location", "Haven"),
                                galaxy=collateral.get("galaxy", "home"))
            self.fleet.pop(collateral_id, None)
        forgiven = max(0, debt - sale_value)
        recovered = min(debt, sale_value)
        self.credits += max(0, sale_value - debt)
        replacement = False
        if collateral_id == self.active_ship_id:
            if self.fleet:
                self.active_ship_id = next(iter(self.fleet))
            else:
                ship_id = f"ship-{self.next_ship_number}"
                self.next_ship_number += 1
                self.fleet[ship_id] = {"id": ship_id, "name": "Wayfarer",
                    "capacity": 30, "fuel": 40, "max_fuel": 40, "condition": 100,
                    "destination": None, "arrival_tick": None, "modem_tier": 0,
                    "speed": 1, "location": "Haven", "galaxy": "home",
                    "export_cargo": {}, "equipment": [], "captain_id": None,
                    "fleet_policy": {"return_to_haven": True, "auto_service": False,
                                      "repair_below": 65, "fuel_below": 35},
                    "cargo": {good: 0 for good in GOODS}}
                self.active_ship_id = ship_id
                replacement = True
        self.loan = None
        self._bind_ship()
        self.bankruptcy_notice = {"collateral_ship": collateral.get("name", "Ship") if collateral else "Ship",
            "recovered": recovered, "forgiven": forgiven, "replacement": replacement,
            "tick": self.tick}
        self.journal.append({"id": f"bankruptcy-{self.tick}-{collateral_id or 'lost'}",
            "tick": self.tick, "action": "loan_bankruptcy", "result": deepcopy(self.bankruptcy_notice)})

    def _sell_equipment(self, item: str) -> dict:
        self._available(maintenance=True)
        if item not in EQUIPMENT or item not in self.ship.get("equipment", []):
            raise GameError("this ship does not have that equipment installed")
        self.ship["equipment"].remove(item)
        payout = max(1, EQUIPMENT[item] // 2)
        self.credits += payout
        return {"item": item, "credits": payout, "ship_id": self.active_ship_id}

    def _sell_ship(self, ship_id: str) -> dict:
        ship = self.fleet.get(ship_id)
        if not ship:
            raise GameError("unknown ship")
        if len(self.fleet) <= 1:
            raise GameError("keep at least one ship in your fleet")
        if ship_id == self.active_ship_id:
            raise GameError("select another ship before selling this one")
        if ship.get("destination") or ship.get("radio_mission") or ship.get("auto_route", {}).get("status") in ("running", "paused"):
            raise GameError("stop the ship's current assignment before selling it")
        if any(ship.get("cargo", {}).values()) or any(ship.get("export_cargo", {}).values()):
            raise GameError("unload the ship's cargo before selling it")
        if any(crew.get("ship_id") == ship_id for crew in self.crew_roster.values()):
            raise GameError("reassign the ship's crew before selling it")
        class_id = ship.get("class_id")
        if class_id:
            from .modems import SHIPS
            hull_cost = next((item["cost"] for item in SHIPS if item["id"] == class_id), 350)
        else:
            hull_cost = (350, 900, 1800)[min(2, ship.get("modem_tier", 0))]
        payout = max(1, hull_cost // 2)
        self.credits += payout
        del self.fleet[ship_id]
        return {"ship_id": ship_id, "name": ship.get("name", "Ship"), "credits": payout}

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
        """The asteroid belt blocks one outbound Haven route for two game ticks."""
        destinations = tuple(port for port in self.ports if port != "Haven")
        return destinations[(self.seed + self.tick // 2) % len(destinations)]

    def route_parent(self, destination: str) -> str | None:
        """Return the charted parent node for a local starport."""
        if destination == "Haven" or destination not in self.ports:
            return None
        return self.ports[destination].get("map_parent")

    def route_connected(self, origin: str, destination: str) -> bool:
        return self.route_parent(destination) == origin or self.route_parent(origin) == destination

    def route_status(self, origin: str, destination: str) -> dict:
        """Describe whether the charted tree has an open path between ports."""
        if origin not in self.ports or destination not in self.ports:
            return {"reachable": False, "open": False, "path": [],
                    "reason": "No charted path connects these starports."}
        def ancestors(port):
            chain = []
            seen = set()
            while port and port in self.ports and port not in seen:
                seen.add(port)
                chain.append(port)
                port = self.route_parent(port)
            return chain
        origin_chain, destination_chain = ancestors(origin), ancestors(destination)
        common = next((port for port in origin_chain if port in destination_chain), None)
        if common is None:
            return {"reachable": False, "open": False, "path": [],
                    "reason": "No charted path connects these starports."}
        path = origin_chain[:origin_chain.index(common) + 1]
        path.extend(reversed(destination_chain[:destination_chain.index(common)]))
        for first, second in zip(path, path[1:]):
            if self.route_parent(second) == first:
                child = second
            elif self.route_parent(first) == second:
                child = first
            else:
                return {"reachable": False, "open": False, "path": path,
                        "reason": "No charted corridor connects these starports."}
            gate = self.ports[child].get("map_gate") or {}
            if not gate or gate.get("unlocked"):
                continue
            kind = gate.get("kind")
            if kind == "reputation":
                faction = gate.get("faction", "explorers")
                required = int(gate.get("required", 0))
                current = int(self.factions.get(faction, 0))
                if current >= required:
                    gate["unlocked"] = True
                    continue
                reason = f"Requires {required} {faction} reputation (you have {current})."
            elif kind == "contract":
                job = self.local_jobs.get(gate.get("contract_id"), {})
                if job.get("status") == "delivered":
                    gate["unlocked"] = True
                    continue
                reason = gate.get("description", "Complete the frontier delivery contract.")
            else:
                reason = "This corridor is sealed by an unknown condition."
            return {"reachable": True, "open": False, "path": path,
                    "blocked_by": child, "reason": reason}
        return {"reachable": True, "open": True, "path": path, "reason": "Charted corridor is open."}

    def _initialize_starport_graph(self) -> None:
        """Migrate the original sector chart to persistent parent/edge metadata."""
        home = self.galaxies.get("home", {}).get("ports", {})
        if "Haven" not in home:
            return
        parents = {"Kepler": "Haven", "Vesper": "Haven", "Prospect": "Haven",
                   "Meridian": "Kepler", "Cinder": "Vesper", "Aurora": "Prospect",
                   "Drift": "Kepler", "Bastion": "Meridian", "Eidolon": "Cinder"}
        angles = {"Haven": 0, "Kepler": -math.pi / 2, "Vesper": math.pi / 6,
                  "Prospect": 5 * math.pi / 6, "Meridian": -math.pi / 2 - .35,
                  "Cinder": math.pi / 6, "Aurora": 5 * math.pi / 6,
                  "Drift": -math.pi / 2 + .35,
                  "Bastion": -math.pi / 2 - .35, "Eidolon": math.pi / 6}
        for port in home.values():
            port.setdefault("map_neighbors", [])
        for name, port in home.items():
            if name == "Haven":
                port.setdefault("map_parent", None)
                port.setdefault("map_depth", 0)
                port.setdefault("map_angle", 0)
            elif name in parents:
                parent = parents[name]
                port.setdefault("map_parent", parent)
                port.setdefault("map_depth", home[parent].get("map_depth", 0) + 1)
                port.setdefault("map_angle", angles[name])
                if parent not in port["map_neighbors"]:
                    port["map_neighbors"].append(parent)
                if name not in home[parent]["map_neighbors"]:
                    home[parent]["map_neighbors"].append(name)
            elif "map_parent" not in port:
                parent = "Eidolon"
                port.update(map_parent=parent, map_depth=home[parent]["map_depth"] + 1,
                            map_angle=home[parent]["map_angle"] + .35)
                if parent not in port["map_neighbors"]:
                    port["map_neighbors"].append(parent)
                if name not in home[parent]["map_neighbors"]:
                    home[parent]["map_neighbors"].append(name)

    def _expand_starport_frontier(self, discovered: str) -> int:
        """Grow a branching, sometimes gated frontier from a reached leaf."""
        ports = self.galaxies["home"]["ports"]
        parent = ports.get(discovered)
        if not parent:
            return 0
        children = [node for node in parent.get("map_neighbors", [])
                    if node != parent.get("map_parent")]
        if children:
            return 0
        rng = random.Random(self.seed * 1_000_003 + len(ports) * 97)
        shape = rng.random()
        child_count = 0 if shape < .14 else 1 if shape < .38 else 2
        if child_count == 0:
            parent["frontier_dead_end"] = True
            return 0
        prefixes = ("Aster", "Nacre", "Vela", "Kestrel", "Sagan", "Tern",
                    "Caldera", "Peregrine", "Orison", "Lumen", "Rook", "Morrow")
        suffixes = ("Reach", "Crossing", "Horizon", "Drift", "Spur", "Relay",
                    "Outpost", "Basin", "Gate", "Haven", "Wake", "Point")
        roles = ("Frontier refinery", "Survey settlement", "Mining habitat",
                 "Trade waypoint", "Research station", "Agricultural outpost")
        signature = self.galaxies["home"].get("specialization", self.specialization)
        parent_depth = int(parent.get("map_depth", 0))
        parent_angle = float(parent.get("map_angle", 0))
        index = len(ports) - len(PORT_NAMES) + 1
        offsets = (-.34, .34)[:child_count]
        gate_child = (rng.randrange(child_count) if parent_depth >= 2 and child_count == 2
                      and rng.random() < .48 else None)
        gate_kind = rng.choice(("reputation", "contract")) if gate_child is not None else None
        for child_number, offset in enumerate(offsets):
            name = f"{rng.choice(prefixes)} {rng.choice(suffixes)}-{index:03d}"
            while name in ports:
                index += 1
                name = f"{rng.choice(prefixes)} {rng.choice(suffixes)}-{index:03d}"
            stock = {good: rng.randint(14, 42) for good in GOODS}
            production = {good: rng.randint(0, 2) for good in GOODS}
            consumption = {good: rng.randint(0, 2) for good in GOODS}
            for rare in RARE:
                stock[rare] = rng.randint(0, 3)
                production[rare] = 0
                consumption[rare] = 1 if rng.random() < .45 else 0
            if rng.random() < .35:
                stock[signature] = rng.randint(12, 30)
                production[signature] = rng.randint(1, 3)
                consumption[signature] = 0
            child = {"stock": stock, "production": production,
                "consumption": consumption, "distance": int(parent.get("distance", 0)) + 2,
                "role": rng.choice(roles), "map_parent": discovered,
                "map_depth": parent_depth + 1, "map_angle": parent_angle + offset,
                "map_neighbors": [discovered]}
            if child_number == gate_child and gate_kind == "reputation":
                child["map_gate"] = {"kind": "reputation", "faction": "explorers",
                                     "required": min(8, max(2, parent_depth)),
                                     "unlocked": False}
            elif child_number == gate_child and gate_kind == "contract":
                gate_id = f"frontier-gate-{index:04d}"
                origin = parent.get("map_parent") or discovered
                good = max(("food", "ore", "fuel", "medicine"),
                           key=lambda item: ports[origin]["stock"].get(item, 0))
                self.local_jobs[gate_id] = {"id": gate_id, "kind": "frontier_gate",
                    "title": f"Clear the {name} corridor", "origin": origin,
                    "destination": discovered, "good": good, "quantity": 2,
                    "reward": 220 + parent_depth * 40, "status": "open",
                    "deadline": self.tick + 999_999_999,
                    "description": f"Deliver 2 {good} to {discovered} to open the corridor to {name}."}
                child["map_gate"] = {"kind": "contract", "contract_id": gate_id,
                    "unlocked": False,
                    "description": f"Complete the delivery contract at {discovered}."}
            ports[name] = child
            parent.setdefault("map_neighbors", []).append(name)
            index += 1
        return child_count

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
                memory.setdefault("by_port", {})[port] = {
                    "buy": self.price(port, good, "buy"),
                    "sell": self.price(port, good, "sell"), "tick": self.tick}
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
        open_jobs = sum(job["status"] == "open" and job.get("kind") not in ("rival", "followup", "frontier_gate")
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
        self._enforce_open_delivery_shortages()

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
        pay = job["reward"]
        if job["destination"] == "Haven":
            pay = pay * (100 + 10 * self.haven_facilities.get("logistics", 0)) // 100
        broker = self.crew_member(self.active_ship_id, "broker")
        if broker:
            pay = pay * (100 + 5 * broker["level"]) // 100
        payout = pay if resolution == "commercial" else pay // 2
        self.credits += payout
        self.factions["traders"] += 1
        if resolution == "reconcile":
            self.factions[self.npc_captains[job["npc_id"]]["faction"]] += 2
        job["status"] = "delivered"
        job["completed_tick"] = self.tick
        job["resolution"] = resolution
        for port in self.galaxies.get("home", {}).get("ports", {}).values():
            gate = port.get("map_gate", {})
            if gate.get("contract_id") == job_id:
                gate["unlocked"] = True
        captain = self.npc_captains.get(job.get("npc_id"))
        if captain and job.get("kind") in ("rival", "followup"):
            captain["relationship"] = max(-5, min(5, captain["relationship"] +
                                                   (3 if resolution == "reconcile" else 1)))
        if job.get("kind") == "followup":
            for followup in self.faction_followups.values():
                if followup.get("job_id") == job_id:
                    followup.update(status="completed", resolution=resolution)
        self._refresh_faction_storylines()
        self._replenish_local_jobs()
        self.award_crew_experience(self.active_ship_id, "broker", 2)
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
                    first_visit = ship.get("galaxy", "home") == "home" and ship["destination"] not in self.visited_ports
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
                        self._expand_starport_frontier(ship["location"])
                        artifact = self._collect_frontier_artifact(ship["location"])
                        explore_bonus = 90 + min(100, self.factions["explorers"] * 10)
                        explore_bonus += 50 * self.haven_facilities.get("grand_archive", 0)
                        if "survey_uplink" in self.faction_perks:
                            explore_bonus += 45
                        self.factions["explorers"] += 1
                        index = list(self.ports).index(ship["location"])
                        if index % 3 == 1:
                            find = {"title": "Abandoned supply cache", "reward": 110 + index * 10}
                        elif index % 3 == 2:
                            find = {"title": "Ancient navigation beacon", "reward": 60 + index * 10}
                        else:
                            find = {"title": "Uncharted trade outpost", "reward": 80 + index * 10}
                        self.discoveries[ship["location"]] = find
                        discovery_reward = (explore_bonus + find["reward"]) * (
                            100 + 25 * self.haven_facilities.get("survey_archive", 0)) // 100
                        self.credits += discovery_reward
                        self.journal.append({"id": "explore-" + ship["location"],
                            "tick": self.tick, "action": "explore",
                            "result": {"port": ship["location"], "reward": discovery_reward,
                                       "discovery": find["title"],
                                       "artifact": artifact["title"] if artifact else None}})
                    route = ship.get("auto_route")
                    if route and route.get("status") == "running" and first_visit:
                        self._pause_auto_route(ship, "discovery", "New starport discovered: inspect the site before continuing")
        if self.active_ship_id:
            self._bind_ship()
        self.observe_markets()
        self._advance_auto_routes()
        self._service_idle_fleet()
        self._advance_warehouse_targets()
        self._gather_idle_ships()

    def _select_ship(self, ship_id: str) -> dict:
        if ship_id not in self.fleet:
            raise GameError("unknown ship")
        self.active_ship_id = ship_id
        self._bind_ship()
        self.observe_markets()
        return {"active_ship_id": ship_id, "location": self.location}

    @staticmethod
    def crew_capacity(ship: dict) -> int:
        return 2 + min(2, max(0, int(ship.get("modem_tier", 0))))

    def crew_member(self, ship_id: str, role: str) -> dict | None:
        return next((person for person in self.crew_roster.values()
                     if person.get("ship_id") == ship_id and person["role"] == role), None)

    def crew_candidates(self, port: str | None = None) -> list[dict]:
        """Repeatable, deterministic dockside hiring board; no RF presence."""
        if port is None and self.ship.get("galaxy", "home") != "home":
            return []
        port = self.location if port is None else port
        if port not in self.ports:
            return []
        index, cycle = list(self.ports).index(port), self.tick // 144
        roles = tuple(CREW_ROLES)
        offers = []
        for slot in range(3):
            role = roles[(self.seed + index * 3 + cycle + slot) % len(roles)]
            level = 1 + (self.seed + index + cycle + slot) % 2
            name = CREW_NAMES[(self.seed * 3 + index * 5 + cycle * 2 + slot) % len(CREW_NAMES)]
            candidate_id = f"candidate-{index}-{cycle}-{slot}"
            if candidate_id not in self.recruited_candidates:
                offers.append({"id": candidate_id, "name": name, "role": role,
                               "level": level, "cost": 120 + level * 85,
                               "port": port, "source": "local_simulation"})
        return offers

    def _docked_ship(self, ship_id: str) -> dict:
        ship = self.fleet.get(ship_id)
        if not ship or ship.get("destination") or ship.get("radio_mission") or ship.get("voyage"):
            raise GameError("choose a docked ship that is not on a mission")
        return ship

    def _hire_crew(self, candidate_id: str) -> dict:
        self._available()
        person = next((candidate for candidate in self.crew_candidates()
                       if candidate["id"] == candidate_id), None)
        if not person:
            raise GameError("recruit is not available at your current port")
        if len(self.crew_roster) >= 30:
            raise GameError("crew roster is full")
        if self.credits < person["cost"]:
            raise GameError("not enough credits to hire this specialist")
        self.credits -= person["cost"]
        crew_id = f"crew-{self.next_crew_number}"
        self.next_crew_number += 1
        assigned = (len([c for c in self.crew_roster.values()
                         if c.get("ship_id") == self.active_ship_id]) < self.crew_capacity(self.ship)
                    and self.crew_member(self.active_ship_id, person["role"]) is None)
        self.crew_roster[crew_id] = {"id": crew_id, "name": person["name"],
                                     "role": person["role"], "level": person["level"],
                                     "xp": 0, "ship_id": self.active_ship_id if assigned else None,
                                     "location": self.location, "galaxy": self.ship.get("galaxy", "home"),
                                     "origin": self.location}
        self.recruited_candidates.append(candidate_id)
        return {"crew_id": crew_id, "name": person["name"], "role": person["role"],
                "level": person["level"], "cost": person["cost"],
                "ship_id": self.active_ship_id if assigned else None, "source": "local_simulation"}

    def _assign_crew(self, crew_id: str, ship_id: str) -> dict:
        crew = self.crew_roster.get(crew_id)
        if not crew:
            raise GameError("unknown crew member")
        destination = self._docked_ship(ship_id)
        if destination.get("auto_route", {}).get("status") in ("running", "paused"):
            raise GameError("stop the trade autopilot before changing its crew")
        if destination["location"] != self.location or destination.get("galaxy", "home") != self.ship.get("galaxy", "home"):
            raise GameError("meet the target ship at the current starport")
        source_id = crew.get("ship_id")
        if source_id == ship_id:
            raise GameError("crew member already assigned to this ship")
        if source_id:
            source = self._docked_ship(source_id)
            if source.get("auto_route", {}).get("status") in ("running", "paused"):
                raise GameError("stop the trade autopilot before transferring its crew")
            if source["location"] != destination["location"] or source.get("galaxy", "home") != destination.get("galaxy", "home"):
                raise GameError("both ships must be docked together to transfer crew")
        elif (crew.get("location") != destination["location"] or
              crew.get("galaxy", "home") != destination.get("galaxy", "home")):
            raise GameError("recruit is waiting at another starport")
        if self.crew_member(ship_id, crew["role"]):
            raise GameError("ship already has that specialist role")
        if sum(c.get("ship_id") == ship_id for c in self.crew_roster.values()) >= self.crew_capacity(destination):
            raise GameError("ship crew berths are full")
        if source_id and self.fleet[source_id].get("captain_id") == crew_id:
            self.fleet[source_id]["captain_id"] = None
        crew.update(ship_id=ship_id, location=destination["location"],
                    galaxy=destination.get("galaxy", "home"))
        return {"crew_id": crew_id, "name": crew["name"], "ship_id": ship_id,
                "role": crew["role"]}

    def _unassign_crew(self, crew_id: str) -> dict:
        crew = self.crew_roster.get(crew_id)
        if not crew or not crew.get("ship_id"):
            raise GameError("crew member is not assigned")
        ship = self._docked_ship(crew["ship_id"])
        if ship.get("auto_route", {}).get("status") in ("running", "paused"):
            raise GameError("stop the trade autopilot before disembarking its crew")
        if ship["location"] != self.location or ship.get("galaxy", "home") != self.ship.get("galaxy", "home"):
            raise GameError("meet the ship at its starport to disembark crew")
        former_ship = crew["ship_id"]
        if ship.get("captain_id") == crew_id:
            ship["captain_id"] = None
        crew.update(ship_id=None, location=ship["location"],
                    galaxy=ship.get("galaxy", "home"))
        return {"crew_id": crew_id, "name": crew["name"],
                "port": ship["location"], "former_ship_id": former_ship}

    def _designate_captain(self, ship_id: str, crew_id: str = "") -> dict:
        """Promote one specialist already aboard, keeping their existing role."""
        ship = self._docked_ship(ship_id)
        if ship.get("auto_route", {}).get("status") in ("running", "paused"):
            raise GameError("finish or stop the route before changing its captain")
        if crew_id:
            crew = self.crew_roster.get(crew_id)
            if not crew or crew.get("ship_id") != ship_id:
                raise GameError("captain must already serve aboard this ship")
            crew.setdefault("command_xp", 0)
            crew.setdefault("command_level", 1)
        ship["captain_id"] = crew_id or None
        return {"ship_id": ship_id, "crew_id": crew_id,
                "captain": self.crew_roster[crew_id]["name"] if crew_id else None,
                "source": "local_simulation"}

    def _set_fleet_policy(self, ship_id: str, return_to_haven: bool,
                          auto_service: bool, repair_below: int,
                          fuel_below: int) -> dict:
        ship = self.fleet.get(ship_id)
        if ship is None:
            raise GameError("unknown ship")
        if (type(return_to_haven) is not bool or type(auto_service) is not bool or
                type(repair_below) is not int or type(fuel_below) is not int or
                not 10 <= repair_below <= 90 or not 10 <= fuel_below <= 90):
            raise GameError("choose valid fleet service settings (10–90% thresholds)")
        policy = {"return_to_haven": return_to_haven,
                  "auto_service": auto_service, "repair_below": repair_below,
                  "fuel_below": fuel_below}
        ship["fleet_policy"] = policy
        return {"ship_id": ship_id, "policy": deepcopy(policy), "source": "local_simulation"}

    def _set_fleet_reserve(self, credits: int) -> dict:
        if type(credits) is not int or not 0 <= credits <= 100000:
            raise GameError("fleet credit reserve must be 0–100000 credits")
        self.fleet_credit_reserve = credits
        return {"credits": credits, "source": "local_simulation"}

    def _set_warehouse_target(self, good: str, target: int, source: str,
                              quantity: int = 3) -> dict:
        """Persistent standing order. Target zero removes it entirely."""
        if good not in GOODS or type(target) is not int or target < 0:
            raise GameError("choose a valid resource and nonnegative target")
        if (source not in self.galaxies["home"]["ports"] or source == "Haven" or
                type(quantity) is not int or not 1 <= quantity <= 100):
            raise GameError("source must be a non-Haven starport; quantity must be 1–100")
        other = sum(item["target"] for name, item in self.warehouse_targets.items() if name != good)
        if target + other > self.haven_warehouse_capacity():
            raise GameError("warehouse targets exceed available total storage; upgrade Haven first")
        if target:
            self.warehouse_targets[good] = {"target": target, "source": source,
                                           "quantity": quantity}
        else:
            self.warehouse_targets.pop(good, None)
        self._advance_warehouse_targets()
        return {"good": good, "target": target, "source": source,
                "quantity": quantity, "source_type": "local_simulation"}

    def _rename_ship(self, ship_id: str, name: str) -> dict:
        if ship_id not in self.fleet or not isinstance(name, str):
            raise GameError("choose a valid ship and name")
        name = name.strip()
        if not 2 <= len(name) <= 28 or not name.isprintable():
            raise GameError("ship name must be 2–28 printable characters")
        self.fleet[ship_id]["name"] = name
        return {"ship_id": ship_id, "name": name}

    def _transfer_cargo(self, source_id: str, destination_id: str, good: str, amount: int) -> dict:
        if source_id == destination_id or good not in GOODS or type(amount) is not int or amount <= 0:
            raise GameError("choose two ships and a positive cargo amount")
        source, target = self._docked_ship(source_id), self._docked_ship(destination_id)
        if any(ship.get("auto_route", {}).get("status") in ("running", "paused") for ship in (source, target)):
            raise GameError("stop trade autopilot before transferring its cargo")
        if (source["location"] != target["location"] or source.get("galaxy", "home") != target.get("galaxy", "home")
                or source["location"] != self.location or source.get("galaxy", "home") != self.ship.get("galaxy", "home")):
            raise GameError("both ships must be docked together at the current port")
        if source["cargo"].get(good, 0) < amount:
            raise GameError("source hold lacks that cargo")
        if sum(target["cargo"].values()) + amount > target["capacity"]:
            raise GameError("destination hold has insufficient space")
        eligible = min(amount, source.get("export_cargo", {}).get(good, 0))
        source["cargo"][good] -= amount
        target["cargo"][good] = target["cargo"].get(good, 0) + amount
        source.setdefault("export_cargo", {})[good] = source.get("export_cargo", {}).get(good, 0) - eligible
        target.setdefault("export_cargo", {})[good] = target.get("export_cargo", {}).get(good, 0) + eligible
        return {"source_id": source_id, "destination_id": destination_id,
                "good": good, "amount": amount, "imported": eligible}

    def _route_event(self, ship: dict, action: str, **details) -> None:
        route = ship["auto_route"]
        route["event_number"] = route.get("event_number", 0) + 1
        self.journal.append({"id": f"auto-{ship['id']}-{route['serial']}-{route['event_number']}",
                             "tick": self.tick, "action": action,
                             "result": {"ship_id": ship["id"], "ship": ship["name"], **details}})

    def _pause_auto_route(self, ship: dict, code: str, reason: str) -> None:
        route = ship["auto_route"]
        if route["status"] != "paused" or route.get("pause_code") != code:
            route.update(status="paused", pause_code=code, pause_reason=reason)
            self._route_event(ship, "auto_route_paused", code=code, reason=reason)

    def _with_auto_ship(self, ship_id: str, operation):
        """Temporarily bind a non-active ship without changing the player's selection."""
        previous_id = self.active_ship_id
        had_auto = "_auto_working" in self.__dict__
        previous_auto = getattr(self, "_auto_working", False)
        try:
            self.active_ship_id = ship_id
            self._bind_ship()
            self._auto_working = True
            return operation()
        finally:
            if had_auto:
                self._auto_working = previous_auto
            else:
                self.__dict__.pop("_auto_working", None)
            self.active_ship_id = previous_id
            if previous_id in self.fleet:
                self._bind_ship()

    def _advance_auto_ship(self, ship_id: str) -> None:
        ship = self.fleet[ship_id]
        route = ship.get("auto_route")
        if not route or route["status"] != "running" or ship.get("destination") or ship.get("radio_mission"):
            return
        if ship.get("galaxy", "home") != "home":
            self._pause_auto_route(ship, "mission", "Only the home galaxy supports local trade autopilot")
            return
        if self.tick < route.get("next_tick", 0):
            return
        # Each wake can complete an arrival, buy or sell, and launch one leg.
        # It cannot silently perform many profitable runs during offline catch-up.
        for _ in range(3):
            stage = route["stage"]
            if stage in ("to_origin", "to_destination"):
                port = route["origin"] if stage == "to_origin" else route["destination"]
                if ship["location"] == port:
                    route["stage"] = "buy" if stage == "to_origin" else "sell"
                    continue
                def depart():
                    risk = self.route_risk(self.location, port)
                    if self.blocked_port() == port:
                        self._pause_auto_route(ship, "blocked", f"Asteroid field obstructs {port}; try again when it moves")
                        return
                    if risk["kind"] != "clear":
                        self._pause_auto_route(ship, "hazard", f"{risk['label']} ahead on the approach to {port}")
                        return
                    try:
                        receipt = self._travel(port)
                        route["last_event"] = f"Departed for {port} · {receipt['fuel_cost']} fuel"
                    except GameError as exc:
                        self._pause_auto_route(ship, "service", str(exc))
                self._with_auto_ship(ship_id, depart)
                return
            if stage == "buy":
                if (route.get("kind") == "supply" and
                        self.haven_warehouse_capacity() - sum(self.export_warehouse.values()) < route["quantity"]):
                    self._pause_auto_route(ship, "warehouse", "Haven export warehouse needs more space before the next collection")
                    return
                if (route.get("standing_target") and self.credits -
                        self.price(ship["location"], route["good"], "buy") * route["quantity"] < self.fleet_credit_reserve):
                    self._pause_auto_route(ship, "budget", "Fleet credit reserve protects the next purchase")
                    return
                if route["good"] in RARE and not route.get("special_approved"):
                    self._pause_auto_route(ship, "special_cargo", f"Rare {route['good']} requires captain approval before purchasing")
                    return
                if any(ship["cargo"].values()):
                    self._pause_auto_route(ship, "cargo", "The ship has other cargo aboard; clear its hold before continuing")
                    return
                try:
                    receipt = self._with_auto_ship(ship_id, lambda: self._trade("buy", route["good"], route["quantity"]))
                except GameError as exc:
                    self._pause_auto_route(ship, "supply", str(exc))
                    return
                route["purchase_cost"] = receipt["total"]
                route["spent"] += receipt["total"]
                route["stage"] = "to_destination"
                route["special_approved"] = False
                route["last_event"] = f"Loaded {route['quantity']} {route['good']} at {route['origin']}"
                continue
            if stage == "sell":
                if ship["cargo"].get(route["good"], 0) < route["quantity"]:
                    self._pause_auto_route(ship, "cargo", "The planned consignment is missing; inspect the hold")
                    return
                if route.get("kind") == "supply":
                    try:
                        receipt = self._with_auto_ship(ship_id, lambda: self._unload_export(route["good"], route["quantity"]))
                    except GameError as exc:
                        self._pause_auto_route(ship, "warehouse", str(exc))
                        return
                    route["delivered"] = route.get("delivered", 0) + route["quantity"]
                    route["last_event"] = f"Stockpiled {route['quantity']} {route['good']} at Haven · {receipt['warehouse']} stored"
                    self._route_event(ship, "auto_route_stockpiled", good=route["good"],
                                      quantity=route["quantity"], warehouse=receipt["warehouse"],
                                      delivered=route["delivered"])
                else:
                    receipt = self._with_auto_ship(ship_id, lambda: self._trade("sell", route["good"], route["quantity"]))
                    profit = receipt["total"] - route["purchase_cost"]
                    route["earned"] += receipt["total"]
                    route["profit"] += profit
                    route["last_event"] = f"Sold at {route['destination']} · {profit:+} cr net (before fuel/repairs)"
                    self._route_event(ship, "auto_route_delivery", good=route["good"],
                                      quantity=route["quantity"], profit=profit,
                                      completed_runs=route["completed_runs"] + 1)
                route["completed_runs"] += 1
                captain = self.crew_roster.get(ship.get("captain_id"))
                if captain and captain.get("ship_id") == ship_id:
                    captain["command_xp"] = captain.get("command_xp", 0) + 1
                    previous = captain.get("command_level", 1)
                    captain["command_level"] = min(3, 1 + (captain["command_xp"] >= 3) + (captain["command_xp"] >= 9))
                    if captain["command_level"] > previous:
                        self._route_event(ship, "captain_promoted", captain=captain["name"],
                                          command_level=captain["command_level"])
                if route["completed_runs"] >= route["max_runs"]:
                    route["status"] = "completed"
                    self._route_event(ship, "auto_route_completed", runs=route["completed_runs"],
                                      profit=route["profit"], delivered=route.get("delivered", 0),
                                      kind=route.get("kind", "trade"))
                    return
                route["stage"] = "to_origin"
                route["next_tick"] = self.tick + 1
                return

    def _advance_auto_routes(self) -> None:
        for ship_id in list(self.fleet):
            if ship_id in self.fleet:
                self._advance_auto_ship(ship_id)

    def _service_idle_fleet(self) -> None:
        """Optional base maintenance using actual stocks, prices and a cash floor."""
        for ship_id, ship in self.fleet.items():
            policy = ship.get("fleet_policy", {})
            if (not policy.get("auto_service") or ship.get("galaxy", "home") != "home"
                    or ship.get("location") != "Haven" or ship.get("destination")
                    or ship.get("radio_mission") or ship.get("vip_job")
                    or ship.get("auto_route", {}).get("status") in ("running", "paused")):
                continue
            if ship["condition"] <= policy.get("repair_below", 65):
                cost = self._repair_cost(ship_id)
                if cost > 0 and self.credits - cost >= self.fleet_credit_reserve:
                    result = self._with_auto_ship(ship_id, self._repair)
                    self.journal.append({"id": f"service-repair-{ship_id}-{self.tick}-{len(self.journal)}",
                                         "tick": self.tick, "action": "fleet_auto_repair",
                                         "result": {"ship_id": ship_id, "cost": result["cost"]}})
            if ship["fuel"] * 100 <= ship["max_fuel"] * policy.get("fuel_below", 35):
                unit_price = self.price("Haven", "fuel", "buy")
                affordable = max(0, (self.credits - self.fleet_credit_reserve) // max(1, unit_price))
                quantity = min(ship["max_fuel"] - ship["fuel"],
                               self.galaxies["home"]["ports"]["Haven"]["stock"]["fuel"], affordable)
                if quantity > 0:
                    result = self._with_auto_ship(ship_id, lambda: self._refuel(quantity))
                    self.journal.append({"id": f"service-fuel-{ship_id}-{self.tick}-{len(self.journal)}",
                                         "tick": self.tick, "action": "fleet_auto_refuel",
                                         "result": {"ship_id": ship_id, "amount": result["amount"],
                                                    "cost": result["cost"]}})

    def _advance_warehouse_targets(self) -> None:
        """Issue at most one new bounded supply order per economy tick."""
        if self.tick < self.next_warehouse_dispatch_tick:
            return
        for good, policy in sorted(self.warehouse_targets.items()):
            source, target = policy["source"], policy["target"]
            pending = sum(route["quantity"] for ship in self.fleet.values()
                          if (route := ship.get("auto_route", {})).get("standing_target") == good
                          and route.get("status") in ("running", "paused"))
            needed = target - self.export_warehouse.get(good, 0) - pending
            if needed <= 0 or self.credits <= self.fleet_credit_reserve:
                continue
            quote = self.price_memory.get(good, {}).get("by_port", {}).get(source, {}).get("buy")
            if type(quote) is not int or quote < 1:
                continue  # Standing orders require a known market, not omniscience.
            idle = [ship for ship in self.fleet.values()
                    if (ship["id"] != self.active_ship_id and ship.get("galaxy", "home") == "home"
                        and not ship.get("destination") and not ship.get("radio_mission")
                        and not ship.get("vip_job") and not ship.get("voyage")
                        and not any(ship["cargo"].values())
                        and ship.get("auto_route", {}).get("status") not in ("running", "paused")
                        and ship.get("condition", 0) >= 10)]
            idle.sort(key=lambda ship: (not bool(ship.get("captain_id")),
                                         ship["location"] != source, -ship["condition"], ship["id"]))
            for ship in idle:
                quantity = min(needed, policy["quantity"], ship["capacity"],
                               self.haven_warehouse_capacity() - sum(self.export_warehouse.values()) - pending)
                if quantity < 1 or quote * quantity > self.credits - self.fleet_credit_reserve:
                    continue
                try:
                    self._start_auto_route(ship["id"], source, "Haven", good, quantity,
                                           max_runs=1, kind="supply", standing_target=good)
                except GameError:
                    continue
                self.next_warehouse_dispatch_tick = self.tick + 1
                return

    def _gather_idle_ships(self) -> None:
        """Park unused, unselected home-galaxy vessels at Haven when safe.

        No radio traffic is involved. We never take over the selected vessel,
        interrupt an assignment, or commit to a hazardous approach unaided.
        """
        for ship_id, ship in self.fleet.items():
            if (ship_id == self.active_ship_id or not ship.get("fleet_policy", {}).get("return_to_haven", True)
                    or ship.get("galaxy", "home") != "home"
                    or ship.get("location") == "Haven" or ship.get("destination")
                    or ship.get("radio_mission") or ship.get("vip_job")
                    or ship.get("voyage") or any(ship["cargo"].values())
                    or ship.get("auto_route", {}).get("status") in ("running", "paused")
                    or ship.get("condition", 0) < 10 or self.blocked_port() == "Haven"
                    or self.route_risk(ship["location"], "Haven")["kind"] != "clear"):
                continue
            try:
                receipt = self._with_auto_ship(ship_id, lambda: self._travel("Haven"))
            except GameError:
                continue  # Wait for fuel, repairs, or a safer corridor.
            self.journal.append({"id": f"idle-home-{ship_id}-{self.tick}-{len(self.journal)}",
                                 "tick": self.tick, "action": "idle_ship_return",
                                 "result": {"ship_id": ship_id, "ship": ship["name"],
                                            "origin": ship["location"],
                                            "destination": "Haven", "fuel_cost": receipt["fuel_cost"]}})

    def _start_auto_route(self, ship_id: str, origin: str, destination: str,
                          good: str, quantity: int, max_runs: int = 3,
                          kind: str = "trade", standing_target: str = "") -> dict:
        ship = self._docked_ship(ship_id)
        if (origin not in self.galaxies["home"]["ports"] or
                destination not in self.galaxies["home"]["ports"] or origin == destination or
                good not in GOODS or type(quantity) is not int or quantity < 1 or
                type(max_runs) is not int or not 1 <= max_runs <= 20):
            raise GameError("choose two different home ports, valid freight, and 1–20 runs")
        if ship.get("galaxy", "home") != "home" or ship.get("vip_job") or any(ship["cargo"].values()):
            raise GameError("autopilot needs an empty ship docked in the home galaxy with no passenger")
        if kind not in ("trade", "supply") or (kind == "supply" and (origin == "Haven" or destination != "Haven")):
            raise GameError("Haven procurement must source imports outside Haven and return to the export warehouse")
        if quantity > ship["capacity"]:
            raise GameError("consignment exceeds this ship's hold")
        if ship.get("auto_route", {}).get("status") in ("running", "paused"):
            raise GameError("stop the current route before planning another")
        ship["auto_route_serial"] = ship.get("auto_route_serial", 0) + 1
        ship["auto_route"] = {"origin": origin, "destination": destination, "good": good,
            "kind": kind, "delivered": 0, "standing_target": standing_target,
            "quantity": quantity, "max_runs": max_runs, "completed_runs": 0,
            "spent": 0, "earned": 0, "profit": 0, "purchase_cost": 0,
            "status": "running", "stage": "to_origin", "created_tick": self.tick,
            "serial": ship["auto_route_serial"],
            "next_tick": self.tick, "event_number": 0, "special_approved": False,
            "pause_code": "", "pause_reason": "", "last_event": "Route commissioned"}
        self._advance_auto_ship(ship_id)
        return {"ship_id": ship_id, "route": deepcopy(ship["auto_route"]),
                "source": "local_simulation"}

    def _dispatch_haven_supply(self, origin: str, good: str, quantity: int = 3,
                               max_runs: int = 3) -> dict:
        """Commission one genuinely idle hull, favoring ships not under direct command."""
        if (origin not in self.galaxies["home"]["ports"] or origin == "Haven" or
                good not in GOODS or type(quantity) is not int or quantity < 1 or
                type(max_runs) is not int or not 1 <= max_runs <= 20):
            raise GameError("choose a source outside Haven, valid freight and 1–20 collection runs")
        idle = [ship for ship in self.fleet.values()
                if ship.get("galaxy", "home") == "home" and not ship.get("destination")
                and not ship.get("radio_mission") and not ship.get("voyage") and not ship.get("vip_job")
                and not any(ship["cargo"].values())
                and ship.get("auto_route", {}).get("status") not in ("running", "paused")
                and ship.get("capacity", 0) >= quantity]
        if not idle:
            raise GameError("no idle home-galaxy vessel with an empty hold and enough capacity")
        idle.sort(key=lambda ship: (ship["id"] == self.active_ship_id,
                                    ship["location"] != origin, -ship["condition"], -ship["fuel"], ship["id"]))
        return self._start_auto_route(idle[0]["id"], origin, "Haven", good,
                                      quantity, max_runs, kind="supply")

    def _pause_auto_route_command(self, ship_id: str) -> dict:
        ship = self.fleet.get(ship_id)
        if not ship or ship.get("auto_route", {}).get("status") != "running":
            raise GameError("no running local route on that ship")
        self._pause_auto_route(ship, "manual", "Paused by captain")
        return {"ship_id": ship_id, "status": "paused"}

    def _resume_auto_route(self, ship_id: str) -> dict:
        ship = self.fleet.get(ship_id)
        if not ship or ship.get("auto_route", {}).get("status") != "paused":
            raise GameError("no paused local route on that ship")
        if ship["auto_route"].get("pause_code") in ("hazard", "special_cargo"):
            raise GameError("approve the hazard or special shipment explicitly before resuming")
        ship["auto_route"].update(status="running", pause_code="", pause_reason="")
        self._advance_auto_ship(ship_id)
        return {"ship_id": ship_id, "route": deepcopy(ship["auto_route"])}

    def _approve_auto_leg(self, ship_id: str, pirate_stance: str = "pay") -> dict:
        ship = self.fleet.get(ship_id)
        route = ship.get("auto_route", {}) if ship else {}
        if route.get("status") != "paused" or route.get("pause_code") not in ("hazard", "special_cargo"):
            raise GameError("no hazardous leg or special cargo is awaiting authorization")
        if route["pause_code"] == "special_cargo":
            route.update(status="running", pause_code="", pause_reason="", special_approved=True)
            self._advance_auto_ship(ship_id)
        else:
            if pirate_stance not in ("pay", "evade", "fight"):
                raise GameError("choose pay, evade, or fight")
            port = route["origin"] if route["stage"] == "to_origin" else route["destination"]
            receipt = self._with_auto_ship(ship_id, lambda: self._travel(port, pirate_stance=pirate_stance))
            route.update(status="running", pause_code="", pause_reason="",
                         last_event=f"Captain approved {port} approach · {receipt['hazard_damage']} hull hazard damage")
        return {"ship_id": ship_id, "route": deepcopy(route), "source": "local_simulation"}

    def _stop_auto_route(self, ship_id: str) -> dict:
        ship = self.fleet.get(ship_id)
        if not ship or ship.get("auto_route", {}).get("status") not in ("running", "paused"):
            raise GameError("no active local route to stop")
        ship["auto_route"].update(status="stopped", pause_code="", pause_reason="",
                                   last_event="Captain ended the route; onboard cargo was retained")
        return {"ship_id": ship_id, "route": deepcopy(ship["auto_route"])}

    def award_crew_experience(self, ship_id: str, role: str, amount: int) -> dict | None:
        """Earn skills only from completed game events or verified RF receipts."""
        crew = self.crew_member(ship_id, role)
        if not crew:
            return None
        crew["xp"] = max(0, crew.get("xp", 0)) + amount
        crew["level"] = max(crew["level"], 3 if crew["xp"] >= 9 else 2 if crew["xp"] >= 3 else 1)
        return {"crew_id": crew["id"], "level": crew["level"], "xp": crew["xp"]}

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
        base_cost = hull["cost"] if hull else (350, 900, 1800)[tier]
        discount = (10 * self.haven_facilities.get("shipyard", 0)
                    if self.location == "Haven" and self.ship.get("galaxy", "home") == "home" else 0)
        cost = max(1, base_cost * (100 - discount) // 100)
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
                               "export_cargo": {}, "equipment": [],
                               "captain_id": None,
                               "fleet_policy": {"return_to_haven": True,
                                                "auto_service": False,
                                                "repair_below": 65,
                                                "fuel_below": 35},
                               "cargo": {g: 0 for g in GOODS}}
        if hull:
            self.fleet[ship_id].update({key: hull[key] for key in
                ("name", "capacity", "speed", "frames_per_tick", "max_bandwidth_hz", "sprite", "description")})
            self.fleet[ship_id]["class_id"] = hull["id"]
        if not self.active_ship_id:
            self.active_ship_id = ship_id
            self._bind_ship()
        return {"ship_id": ship_id, "class": self.fleet[ship_id]["name"],
                "cost": cost, "base_cost": base_cost, "discount_percent": discount}

    def damage_ship(self, ship_id: str, amount: int, origin: str) -> dict:
        """Failed RF mission: return home damaged, or lose ship in hard mode."""
        if ship_id not in self.fleet or origin not in self.ports or amount <= 0:
            raise GameError("invalid mission damage")
        ship = self.fleet[ship_id]
        officer = self.crew_member(ship_id, "signal")
        prevented = min(amount - 1, officer["level"] * 2) if officer else 0
        amount -= prevented
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
            for crew in self.crew_roster.values():
                if crew.get("ship_id") == ship_id:
                    crew.update(ship_id=None, location=origin,
                                galaxy=ship.get("galaxy", "home"))
            del self.fleet[ship_id]
            if self.active_ship_id == ship_id:
                self.active_ship_id = next(iter(self.fleet), "")
        if self.active_ship_id:
            self._bind_ship()
        return {"ship_id": ship_id, "damage": amount, "damage_prevented": prevented,
                "destroyed": destroyed,
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
                stock[rare] = rng.randint(0, 3)
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
            # Haven is the dependable refueling hub, even when its seeded
            # market roll would otherwise make fuel a net shortage.
            if i == 0:
                stock["fuel"] = max(40, stock["fuel"])
                production["fuel"] = max(3, production["fuel"])
                consumption["fuel"] = min(2, consumption["fuel"])
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
        if good == "fuel":
            # Fuel remains sensitive to supply, but its swings are narrower
            # because it gates basic movement rather than cargo trading.
            pressure = max(65, min(160, 150 - stock))
        else:
            pressure = max(50, min(200, 150 - stock))
        midpoint = max(1, BASE_PRICE[good] * pressure // 100)
        if good in RARE:
            # The active galaxy's signature is its export strength. Keep that
            # resource comparatively affordable while non-signature rares
            # carry a scarcity premium that rewards importing from elsewhere.
            identity = 75 if good == self.specialization else 125
            midpoint = max(1, midpoint * identity // 100)
        if any(event["port"] == port and event["good"] == good
               for event in self.active_sector_events()):
            midpoint = midpoint * 150 // 100
        multiplier = 110 if action == "buy" else ((104 if self.hard_mode else 90) + min(10, self.factions.get("traders", 0) // 2))
        if action == "buy" and good in ("ore", "medicine"):
            faction = "miners" if good == "ore" else "scientists"
            multiplier -= min(8, self.factions.get(faction, 0) // 2)
        if action == "buy" and good == "food" and "trade_charter" in self.faction_perks:
            multiplier -= 5
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

    def _available(self, *, maintenance: bool = False) -> None:
        if not self.active_ship_id:
            raise GameError("no surviving ship; purchase a replacement to continue")
        if self.ship["destination"] is not None:
            raise GameError("ship is in transit")
        if self.ship.get("radio_mission"):
            raise GameError("ship is assigned to a radio mission")
        route_status = self.ship.get("auto_route", {}).get("status")
        if (route_status in ("running", "paused") and not getattr(self, "_auto_working", False)
                and not (maintenance and route_status == "paused")):
            raise GameError("pause the trade autopilot for repairs and refueling, or stop it to command this ship manually")

    def cargo_used(self) -> int:
        return sum(self.cargo.values())

    def command(self, command_id: str, action: str, **kwargs) -> dict:
        """Execute once. Repeated IDs return their original result without side effects."""
        # Doctrine changes must take effect before the next unattended action.
        # In particular, an opt-out must not dispatch an idle ship home while
        # the player is in the act of disabling that behavior.
        if action not in ("set_fleet_policy", "set_fleet_reserve",
                          "set_warehouse_target", "designate_captain"):
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
            elif action == "emergency_refuel":
                result = self._emergency_refuel(**kwargs)
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
            elif action == "rename_ship":
                result = self._rename_ship(**kwargs)
            elif action == "transfer_cargo":
                result = self._transfer_cargo(**kwargs)
            elif action == "start_auto_route":
                result = self._start_auto_route(**kwargs)
            elif action == "dispatch_haven_supply":
                result = self._dispatch_haven_supply(**kwargs)
            elif action == "set_warehouse_target":
                result = self._set_warehouse_target(**kwargs)
            elif action == "set_fleet_reserve":
                result = self._set_fleet_reserve(**kwargs)
            elif action == "set_fleet_policy":
                result = self._set_fleet_policy(**kwargs)
            elif action == "designate_captain":
                result = self._designate_captain(**kwargs)
            elif action == "pause_auto_route":
                result = self._pause_auto_route_command(**kwargs)
            elif action == "resume_auto_route":
                result = self._resume_auto_route(**kwargs)
            elif action == "approve_auto_leg":
                result = self._approve_auto_leg(**kwargs)
            elif action == "stop_auto_route":
                result = self._stop_auto_route(**kwargs)
            elif action == "hire_crew":
                result = self._hire_crew(**kwargs)
            elif action == "assign_crew":
                result = self._assign_crew(**kwargs)
            elif action == "unassign_crew":
                result = self._unassign_crew(**kwargs)
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
            elif action == "resolve_faction_storyline":
                result = self._resolve_faction_storyline(**kwargs)
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
            elif action == "dockside_shift":
                result = self._dockside_shift()
            elif action == "take_loan":
                result = self._take_loan(**kwargs)
            elif action == "sell_equipment":
                result = self._sell_equipment(**kwargs)
            elif action == "sell_ship":
                result = self._sell_ship(**kwargs)
            elif action == "sell_hold_upgrade":
                result = self._sell_hold_upgrade()
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
            elif action == "fulfill_haven_order":
                result = self._fulfill_haven_order(**kwargs)
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
        self._enforce_open_delivery_shortages()
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
            self._enforce_open_delivery_shortages()
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
        corridor = self.route_status(self.location, destination)
        if not corridor["reachable"]:
            raise GameError(corridor["reason"])
        if not corridor["open"]:
            raise GameError("Corridor blocked: " + corridor["reason"])
        if pirate_stance not in ("pay", "evade", "fight"):
            raise GameError("invalid pirate strategy")
        equipment = self.ship.get("equipment", [])
        blocked = destination == self.blocked_port()
        if blocked and "navigator" not in equipment:
            raise GameError(f"Asteroid field blocks the direct approach to {destination}; wait for the field to orbit onward")
        distance = abs(self.ports[destination]["distance"] -
                       self.ports[self.location]["distance"])
        risk = self.route_risk(self.location, destination)
        # Distances are already expressed in map hops; charge one unit per
        # hop, with charted routes retaining their half-cost advantage.
        base_fuel = max(1, distance)
        fuel_cost = (max(1, base_fuel // 2) if self.route_connected(self.location, destination)
                     else base_fuel)
        fuel_cost += (4 if blocked else 0) + (2 if risk["kind"] == "pirates" and pirate_stance == "evade" else 0)
        pilot = self.crew_member(self.active_ship_id, "pilot")
        engineer = self.crew_member(self.active_ship_id, "engineer")
        if pilot:
            fuel_cost = max(1, fuel_cost - pilot["level"])
        if fuel_cost > self.ship["fuel"]:
            raise GameError("insufficient ship fuel")
        if self.ship["condition"] < 10:
            raise GameError("repair ship before traveling")
        self.ship["fuel"] -= fuel_cost
        mitigation = max(0, int(self.ship.get("modem_tier", 0)) * 2)
        if risk["kind"] == "gas" and "shield" in equipment:
            mitigation += 6
        if risk["kind"] != "clear" and "reinforced_plating" in self.faction_perks:
            mitigation += 3
        if engineer:
            mitigation += engineer["level"] * 2
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
        wear = max(1, distance - (engineer["level"] if engineer else 0))
        self.ship["condition"] = max(0, self.ship["condition"] - wear - hazard_damage)
        if risk["kind"] == "pirates" and pirate_stance == "pay":
            # A capped pirate toll makes a dangerous route matter without
            # deleting a reserved cargo manifest or creating a dead-end.
            toll = min(self.credits, max(0, 10 + distance * 3 - self.factions.get("pirates", 0) * 2))
            if "pirate_codes" in self.faction_perks:
                toll //= 2
            self.credits -= toll
            risk = {**risk, "toll": toll}
            self.factions["pirates"] += 1
        if blocked:
            risk = {**risk, "navigator_bypass": True}
        speed = max(1, int(self.ship.get("speed", 1)) + (1 if pilot and pilot["level"] >= 2 else 0))
        travel_seconds = min(10, max(1, math.ceil(distance * 2 / speed)))
        arrival_at = time.time() + travel_seconds
        self.ship["destination"] = destination
        self.ship["arrival_tick"] = None
        self.ship["arrival_at"] = arrival_at
        self.ship["departed_at"] = arrival_at - travel_seconds
        self.ship["travel_seconds"] = travel_seconds
        self.ship["origin_port"] = self.location
        self.award_crew_experience(self.active_ship_id, "pilot", 1)
        self.award_crew_experience(self.active_ship_id, "engineer", 1)
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
            self._service_loan()
        self._replenish_local_jobs()
        self._advance_faction_followups()
        self._refresh_haven_orders()
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
            self._refresh_haven_orders()
            self.observe_markets()
            self._service_loan()
        return {"epoch": self.clock_epoch, "advanced": elapsed, "tick": self.tick}

    def _repair_cost(self, ship_id: str) -> int:
        ship = self.fleet[ship_id]
        engineer = self.crew_member(ship_id, "engineer")
        captain = self.crew_roster.get(ship.get("captain_id"))
        discount_percent = min(90, 15 * self.haven_facilities.get("repair_bay", 0) +
                               (5 * engineer["level"] if engineer else 0) +
                               (5 * max(0, captain.get("command_level", 1) - 1) if captain else 0))
        return math.ceil((100 - ship["condition"]) * 2 * (100 - discount_percent) / 100)

    def _repair(self) -> dict:
        self._available(maintenance=True)
        cost = self._repair_cost(self.active_ship_id)
        if self.credits < cost:
            raise GameError("insufficient credits")
        self.credits -= cost
        self.ship["condition"] = 100
        return {"cost": cost, "condition": 100}

    def _refuel(self, amount: int) -> dict:
        self._available(maintenance=True)
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

    def _emergency_refuel(self, amount: int) -> dict:
        """Buy reserve fuel at a dock when local market stock is exhausted."""
        self._available(maintenance=True)
        if type(amount) is not int or amount <= 0 or self.ship["fuel"] + amount > self.ship["max_fuel"]:
            raise GameError("emergency fuel amount exceeds tank capacity")
        if self.ports[self.location]["stock"]["fuel"] > 0:
            raise GameError("use the regular refuel service while station fuel is available")
        cost = self.price(self.location, "fuel", "buy") * amount * 2
        if self.credits < cost:
            raise GameError("insufficient credits for emergency reserve fuel")
        self.credits -= cost
        self.ship["fuel"] += amount
        return {"amount": amount, "cost": cost, "fuel": self.ship["fuel"], "emergency": True}

    def _upgrade(self) -> dict:
        self._available()
        cost = 400 + self.ship["capacity"] * 10
        if self.credits < cost:
            raise GameError("insufficient credits")
        self.credits -= cost
        self.ship["capacity"] += 10
        return {"cost": cost, "capacity": self.ship["capacity"]}

    def _sell_hold_upgrade(self) -> dict:
        self._available(maintenance=True)
        if self.ship["capacity"] <= 30:
            raise GameError("no cargo hold upgrade to sell")
        if self.cargo_used() > self.ship["capacity"] - 10:
            raise GameError("unload cargo before reducing hold capacity")
        cost = 400 + (self.ship["capacity"] - 10) * 10
        payout = max(1, cost // 2)
        self.ship["capacity"] -= 10
        self.credits += payout
        return {"credits": payout, "capacity": self.ship["capacity"]}

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
        return deepcopy({key: value for key, value in self.__dict__.items()
                         if key != "_auto_working"})

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
