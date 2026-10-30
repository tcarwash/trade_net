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
                       "job.kind==='dispatch'", "state.radio_contacts?.[id]?'◉ ':'○ '"):
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
                       "entry.action==='upgrade_haven'", "renderEncounter();renderDiscoveryJournal();renderHaven()"):
            with self.subTest(marker=marker):
                self.assertIn(marker, html)

    def test_recurring_npc_captains_have_local_map_and_expedition_affordances(self):
        html = self.browser_html()
        for marker in ("function renderNpcTraffic(){", "npcTraffic", "npc-board",
                       "npc-diamond", "npc-target", "state.game.npc_captains",
                       "g.npc_shipments", "mission.issuer_npc", "◇ LOCAL ACTIVITY",
                       "renderHaven();renderNpcTraffic();renderExchange()",
                       "captain.relationship>0?'FRIENDLY PRICE'"):
            with self.subTest(marker=marker):
                self.assertIn(marker, html)


if __name__ == "__main__":
    unittest.main()
