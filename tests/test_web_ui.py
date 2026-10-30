"""Guard the core browser anchors that previously caused a render crash."""

import unittest
import json
from html.parser import HTMLParser
from pathlib import Path


class _Ids(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        self.ids.update(value for name, value in attrs if name == "id")


class BrowserUIContractTests(unittest.TestCase):
    @staticmethod
    def browser_html():
        return (Path(__file__).resolve().parents[1] /
                "tradenet" / "web" / "index.html").read_text()

    def test_required_gameplay_anchors_exist(self):
        html = self.browser_html()
        parser = _Ids()
        parser.feed(html)
        self.assertTrue({"galaxy", "transportStatus", "detail", "feedback",
                         "goods", "destination", "fleetForm", "tradeForm",
                         "contracts", "log", "exchangeForm", "debugToggle",
                         "guideText"}.issubset(parser.ids))
        self.assertIn("drawShipOverlay(s,positions)", html)
        self.assertIn("updateRouteQuote()", html)

    def test_mobile_game_shell_and_action_feedback(self):
        html = self.browser_html()
        parser = _Ids()
        parser.feed(html)
        self.assertTrue({"objectiveBrief", "objectiveAction", "flightProgress",
                         "saveIndicator", "tabCommand", "tabFleet", "tabContracts",
                         "tabComms"}.issubset(parser.ids))
        for marker in ("@media(max-width:760px)", "@media(max-width:600px)",
                       "safe-area-inset-bottom", "data-label", "currentContractsFilter",
                       "role','listitem", "centerLocalMap", "aria-valuenow",
                       "nextActionCommand='complete_story'", "nextActionCommand='deliver_vip'",
                       "nextActionCommand='deliver_local'", "prefers-reduced-motion"):
            with self.subTest(marker=marker):
                self.assertIn(marker, html)

    def test_installable_mobile_asset_contract(self):
        root = Path(__file__).resolve().parents[1] / "tradenet" / "web"
        manifest = json.loads((root / "manifest.webmanifest").read_text())
        self.assertEqual(manifest["display"], "standalone")
        self.assertEqual(manifest["start_url"], "/")
        for icon in manifest["icons"]:
            self.assertTrue((root / icon["src"].lstrip("/")).is_file(), icon)
        self.assertIn('rel="manifest"', self.browser_html())
        self.assertTrue((root / "apple-touch-icon.png").is_file())

    def test_milestone_dialog_and_first_trade_coach(self):
        html = self.browser_html()
        parser = _Ids()
        parser.feed(html)
        self.assertTrue({"momentDialog", "momentArt", "momentTitle", "momentDescription",
                         "momentReward", "momentContinue", "momentClose", "guideNext",
                         "guideProgress"}.issubset(parser.ids))
        for marker in ("dialog.showModal()", "scanGameplayMoments()", "seenJournal.add(entry.id)",
                       "if(!momentsReady)", "previous==='awaiting_ack'",
                       "entry.action==='deliver_vip'", "entry.action==='explore'",
                       "entry.action==='complete_story'", "guideStep===1",
                       "guideStep===2", "guideStep===3", "guideStep===4",
                       "guideStep===5", "sessionStorage.setItem('trade-net-guide-step'",
                       "prefers-reduced-motion:reduce"):
            with self.subTest(marker=marker):
                self.assertIn(marker, html)

    def test_simulated_dispatch_is_visually_distinct_from_live_radio(self):
        html = self.browser_html()
        parser = _Ids()
        parser.feed(html)
        self.assertTrue({"sectorNews", "newsAction", "newsTitle"}.issubset(parser.ids))
        for marker in ("◇ Local dispatch", "○ Unverified RF", "◉ Verified RF", "renderDispatchSignals()",
                       "renderSectorNews()", "showDispatchJob(", "dispatch_signals",
                       "dispatch:'◇ SECTOR DISPATCH'", "state.radio_contacts?.[id]?'◉ ':'○ '"):
            with self.subTest(marker=marker):
                self.assertIn(marker, html)
        # Fictional contacts navigate only to local contracts. The single live
        # transmit call is in the separate operator exchange form.
        dispatch_ui = html.split("function renderDispatchSignals(){", 1)[1].split("function renderContracts(){", 1)[0]
        self.assertNotIn("radio_transmit", dispatch_ui)
        self.assertNotIn("/api/action", dispatch_ui)

    def test_expedition_cards_stage_choices_and_event_modals(self):
        html = self.browser_html()
        for marker in ("function renderExpeditions(){", "expedition-stages",
                       "expedition-actions", "mission.stages[mission.stage]",
                       "mission.status==='accepted'", "choice:choice.id",
                       "command('accept_expedition'", "command('advance_expedition'",
                       "command('abandon_expedition'", "EXPEDITION COMPLETED",
                       "EXPEDITION MILESTONE", "Confirm abandon · keep cargo"):
            with self.subTest(marker=marker):
                self.assertIn(marker, html)

    def test_rig_band_passport_and_longhaul_progress(self):
        html = self.browser_html()
        for marker in ("id=\"rigBadge\"", "bandPassport", "radio_bands_seen",
                       "rig.frequency_hz/1e6", "Tune rig to ",
                       "bandReady", "c.requirements||{[c.good]:c.quantity}",
                       "LONG-HAUL MANIFEST", "stockpile over multiple sessions"):
            with self.subTest(marker=marker):
                self.assertIn(marker, html)

    def test_interactive_exploration_and_haven_construction(self):
        html = self.browser_html()
        for marker in ("function renderEncounter(){", "function renderDiscoveryJournal(){",
                       "function renderHaven(){", "encounterPanel", "discoveryJournal",
                       "havenPanel", "encounter-choices", "haven-grid",
                       "command('resolve_encounter'", "command('upgrade_haven'",
                       "state.haven_upgrades", "state.haven_warehouse_capacity",
                       "entry.action==='discover_site'", "entry.action==='resolve_encounter'",
                       "entry.action==='upgrade_haven'", "renderEncounter();renderDiscoveryJournal();renderLocalEncounters();renderHaven()"):
            with self.subTest(marker=marker):
                self.assertIn(marker, html)

    def test_recurring_npc_captains_have_local_map_and_expedition_affordances(self):
        html = self.browser_html()
        for marker in ("function renderNpcTraffic(){", "npcTraffic", "npc-board",
                       "npc-diamond", "npc-target", "state.game.npc_captains",
                       "g.npc_shipments", "mission.issuer_npc", "◇ LOCAL ACTIVITY",
                       "renderLocalEncounters();renderHaven();renderNpcTraffic();renderExchange()",
                       "captain.relationship>0?'FRIENDLY PRICE'"):
            with self.subTest(marker=marker):
                self.assertIn(marker, html)

    def test_living_galaxy_rivals_followups_and_local_encounter_choices(self):
        html = self.browser_html()
        for marker in ("renderLocalEncounters()", "function renderLocalEncounters(){",
                       "localEncountersPanel", "g.local_encounters", "◇ Passing opportunities",
                       "command('resolve_local_encounter'", "◇ RIVAL FREIGHT",
                       "◇ FACTION FOLLOW-UP", "entry.action==='followup_available'",
                       "entry.action==='npc_claim'", "entry.action==='resolve_local_encounter'",
                       "Math.max(0,job.deadline-g.tick)"):
            with self.subTest(marker=marker):
                self.assertIn(marker, html)

    def test_captain_consequences_are_visible_and_actionable(self):
        html = self.browser_html()
        for marker in ("state.captain_deal_quotes", "◇ PRIVATE LOT",
                       "command('buy_captain_deal'", "command('request_sector_aid'",
                       "command('deliver_local',{job_id:job.id,resolution:'reconcile'})",
                       "entry.action==='request_sector_aid'", "entry.action==='buy_captain_deal'",
                       "signal.hostile_captain", "job.aid_by", "Build trust · +3 relation"):
            with self.subTest(marker=marker):
                self.assertIn(marker, html)

    def test_persistent_faction_stories_have_choices_and_nemesis_feedback(self):
        html = self.browser_html()
        for marker in ("renderFactionStorylines()", "function renderFactionStorylines(){",
                       "factionStorylinesPanel", "g.faction_storylines", "g.faction_perks",
                       "g.captain_nemeses", "◇ ALLIANCE OFFER", "◇ RIVAL ULTIMATUM",
                       "command('resolve_faction_storyline'", "entry.action==='faction_storyline_offered'",
                       "entry.action==='resolve_faction_storyline'", "plotExpeditionWaypoint(scene.port)"):
            with self.subTest(marker=marker):
                self.assertIn(marker, html)

    def test_haven_operations_include_procurement_and_local_unloading(self):
        html = self.browser_html()
        for marker in ("◇ Headquarters operations", "Cargo Exchange requisitions",
                       "g.haven_orders", "g.next_haven_order_tick",
                       "command('fulfill_haven_order'", "command('unload_export'",
                       "state.haven_warehouse_capacity", "function shipyardPrice(base)",
                       "shipyardPrice(ship.cost)", "havenReward=job.destination==='Haven'",
                       "entry.action==='fulfill_haven_order'", "Interactive Haven headquarters layout",
                       "campus-site", "campus-levels", "haven-facility-", "SELECT TO BUILD",
                       "Source ${good}", "g.price_memory?.[good]?.lowest_buy"):
            with self.subTest(marker=marker):
                self.assertIn(marker, html)

    def test_fleet_crew_management_is_visible_and_state_driven(self):
        html = self.browser_html()
        for marker in ("function renderFleetOperations(){", "renderFleetOperations();renderFleetAutomation();map()",
                       "state.crew_candidates", "state.crew_roles", "crewForShip(",
                       "fleet-roster-grid", "recruit-list", "crew-list",
                       "command('hire_crew'", "command('assign_crew'",
                       "command('unassign_crew'", "command('rename_ship'",
                       "command('transfer_cargo'", "entry.action==='hire_crew'"):
            with self.subTest(marker=marker):
                self.assertIn(marker, html)

    def test_fleet_autopilot_is_visible_separate_from_real_radio(self):
        html = self.browser_html()
        for marker in ("function renderFleetAutomation(){", "auto-route-grid",
                       "command('start_auto_route'", "command('pause_auto_route'",
                       "command('resume_auto_route'", "command('approve_auto_leg'",
                       "command('stop_auto_route'", "AUTOPILOT REQUESTS ORDERS",
                       "radio jumps always need a captain", "intergalactic radio · manual"):
            with self.subTest(marker=marker):
                self.assertIn(marker.lower(), html.lower())


if __name__ == "__main__":
    unittest.main()
