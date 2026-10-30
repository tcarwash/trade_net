import tempfile
import unittest
from pathlib import Path

from tradenet import GameError
from tradenet.federation import Federation
from tradenet.mail import MailNetwork
from tradenet.payloads import decode as decode_bundle


class FederationTests(unittest.TestCase):
    def setUp(self):
        self.f = Federation.demo()
        self.seller, self.buyer = list(self.f.worlds)
        self.good = self.f.worlds[self.seller].specialization
        # The isolated federation simulator now requires a synchronized hub
        # contract before reserving. This is not a real RF receipt.
        link = ":".join(sorted((self.seller, self.buyer)))
        self.f.contract_syncs[link] = {"status": "synchronized", "source": "test_fixture"}

    def propose(self, trade_id="T1", quantity=2):
        return self.f.propose(trade_id, self.seller, self.buyer,
                              self.good, quantity, 220, payload_bytes=1024)

    def test_distinct_specialized_galaxies(self):
        self.assertNotEqual(self.f.worlds[self.seller].specialization,
                            self.f.worlds[self.buyer].specialization)

    def test_reservation_is_conservative_and_idempotent(self):
        self.propose()
        seller, buyer = self.f.worlds[self.seller], self.f.worlds[self.buyer]
        starting_stock, starting_money = seller.ports["Haven"]["stock"][self.good], buyer.credits
        self.f.reserve("T1")
        self.f.reserve("T1")
        self.assertEqual(seller.ports["Haven"]["stock"][self.good], starting_stock - 2)
        self.assertEqual(buyer.credits, starting_money)
        self.assertEqual(buyer.incoming_reserved, 0)

    def test_failed_delivery_then_receipt_and_exactly_once_settlement(self):
        t = self.propose()
        self.f.reserve("T1")
        seller, buyer = self.f.worlds[self.seller], self.f.worlds[self.buyer]
        before = seller.credits
        buyer_before = buyer.ports["Haven"]["stock"][self.good]
        fail = self.f.dispatch("T1", loss=1)
        self.assertFalse(fail["delivered"])
        self.assertEqual(t["custody"], self.seller)
        with self.assertRaises(GameError):
            self.f.settle("T1")
        success = self.f.dispatch("T1", loss=0)
        self.assertTrue(success["delivered"])
        self.assertEqual(t["status"], "delivered")
        receipt = t["receipt"]
        with self.assertRaises(GameError):
            self.f.settle("T1", {**receipt, "terms_hash": "wrong"})
        first = self.f.settle("T1")
        second = self.f.settle("T1")
        self.assertEqual(first, second)
        self.assertEqual(seller.credits, before + first["seller_credits"])
        self.assertEqual(buyer.ports["Haven"]["stock"][self.good], buyer_before + 2)
        self.assertEqual(buyer.incoming_reserved, 0)

    def test_courier_hops_dont_mint_inventory(self):
        t = self.propose()
        self.f.reserve("T1")
        starting_stock = self.f.worlds[self.buyer].ports["Haven"]["stock"][self.good]
        route = [self.seller, "SIM-RELAY", self.buyer]
        self.f.dispatch("T1", route=route, loss=0)
        self.assertEqual(t["custody"], "SIM-RELAY")
        self.assertEqual(self.f.worlds[self.buyer].cargo[self.good], 0)
        self.f.dispatch("T1", loss=0)
        self.assertEqual(t["custody"], self.buyer)
        self.assertEqual(self.f.worlds[self.buyer].cargo[self.good], 0)
        self.f.settle("T1")
        self.assertEqual(self.f.worlds[self.buyer].ports["Haven"]["stock"][self.good], starting_stock + 2)
        self.assertNotIn(self.buyer, self.f.network.peers)

    def test_cancel_restores_escrow(self):
        self.propose()
        seller, buyer = self.f.worlds[self.seller], self.f.worlds[self.buyer]
        before = (seller.ports["Haven"]["stock"][self.good], buyer.credits)
        self.f.reserve("T1")
        self.f.cancel("T1")
        self.assertEqual((seller.ports["Haven"]["stock"][self.good], buyer.credits), before)
        self.assertEqual(buyer.incoming_reserved, 0)

    def test_receiving_hub_does_not_reserve_an_unrelated_ship_hold(self):
        self.propose(quantity=6)
        self.f.reserve("T1")
        buyer = self.f.worlds[self.buyer]
        self.assertEqual(buyer.incoming_reserved, 0)
        self.assertEqual(buyer.cargo[self.good], 0)
        self.assertEqual(self.f.trades["T1"]["seller_hold"], "Haven")

    def test_save_and_restart_before_settlement(self):
        self.propose()
        self.f.reserve("T1")
        self.f.dispatch("T1", loss=0)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "federation.json"
            self.f.save(path)
            other = Federation.load(path)
            self.assertEqual(other.trades, self.f.trades)
            self.assertEqual(other.events, self.f.events)
            for peer in self.f.worlds:
                self.assertEqual(other.worlds[peer].ports, self.f.worlds[peer].ports)
                self.assertEqual(other.worlds[peer].credits, self.f.worlds[peer].credits)
            other.settle("T1")
            other.save(path)
            final = Federation.load(path)
            self.assertEqual(final.trades["T1"]["status"], "settled")
            self.assertEqual(final.settle("T1"), other.trades["T1"]["settlement"])

    def test_duplicate_trade_id_must_have_same_terms(self):
        self.propose()
        self.propose()
        with self.assertRaises(GameError):
            self.propose(quantity=3)

    def test_isolated_simulator_is_not_an_app_federation(self):
        from tradenet.web import App
        with tempfile.TemporaryDirectory() as directory:
            app = App(Path(directory) / "galaxy.json", 42, "AG7SU")
            self.assertFalse(hasattr(app, "federation"))
            with self.assertRaises(GameError):
                app.execute({"action": "exchange_dispatch", "trade_id": "T1"})

    def test_async_queue_and_late_reverse_ack(self):
        self.propose()
        self.f.reserve("T1")
        starting_stock = self.f.worlds[self.buyer].ports["Haven"]["stock"][self.good]
        mail = MailNetwork()
        self.f.queue_trade(mail, "T1", [self.seller, "RELAY", self.buyer])
        mail.set_online(self.buyer, False)
        for _ in range(10):
            mail.step(loss=0, budget_frames=64)
            self.f.sync_mail(mail)
        self.assertEqual(self.f.trades["T1"]["status"], "queued")
        self.assertEqual(mail.messages["trade:T1"]["hop"], 1)
        mail.set_online(self.buyer, True)
        for _ in range(30):
            mail.step(loss=0, budget_frames=64)
            self.f.sync_mail(mail)
            if self.f.trades["T1"]["status"] == "settled":
                break
        self.assertEqual(self.f.trades["T1"]["status"], "settled")
        self.assertEqual(self.f.worlds[self.buyer].ports["Haven"]["stock"][self.good], starting_stock + 2)

    def test_ship_modem_upgrade_gates_mail_capacity(self):
        self.propose()
        self.f.reserve("T1")
        seller = self.f.worlds[self.seller]
        seller.command("upgrade-modem", "upgrade_modem")
        mail = MailNetwork()
        msg = self.f.queue_trade(mail, "T1")
        self.assertEqual(msg["bandwidth_hz"], 1200)
        self.assertEqual(msg["frames_per_tick"], 6)

    def test_isolated_async_exchange_survives_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "federation.json"
            mail = MailNetwork()
            self.propose()
            self.f.reserve("T1")
            self.f.queue_trade(mail, "T1", route=[self.seller, "SIM-RELAY", self.buyer])
            mail.set_online(self.buyer, False)
            for _ in range(5):
                mail.step(loss=0, budget_frames=64)
                self.f.sync_mail(mail)
            self.f.save(path)
            restored = Federation.load(path)
            self.assertEqual(restored.trades["T1"]["status"], "queued")
            mail.set_online(self.buyer, True)
            for _ in range(30):
                mail.step(loss=0, budget_frames=64)
                restored.sync_mail(mail)
                if restored.trades["T1"]["status"] == "settled":
                    break
            self.assertEqual(restored.trades["T1"]["status"], "settled")
            restored.save(path)
            self.assertEqual(Federation.load(path).trades["T1"]["status"], "settled")

    def test_three_useful_load_classes_increase_real_content(self):
        t = self.propose()
        a = self.f.trade_payload(t, "light", self.f.reports)
        b = self.f.trade_payload(t, "medium", self.f.reports)
        c = self.f.trade_payload(t, "heavy", self.f.reports)
        self.assertLess(len(a), len(b))
        self.assertLess(len(b), len(c))
        self.assertEqual([item.kind for item in decode_bundle(b)], ["trade", "neighbors"])
        self.assertEqual([item.kind for item in decode_bundle(c)], ["trade", "neighbors", "contracts", "market"])
        self.assertIn(b"ore_stock", b)
        self.assertIn(b"prices", c)
        self.assertNotIn(b"padding", c)

    def test_missing_second_hop_report_rejects_medium(self):
        t = self.propose()
        with self.assertRaises(GameError):
            self.f.trade_payload(t, "medium", {})

    def test_mission_uses_selected_ship_and_releases_after_ack(self):
        self.propose()
        self.f.reserve("T1")
        seller = self.f.worlds[self.seller]
        bought = seller.command("extra", "purchase_ship", tier=2)
        ship_id = bought["ship_id"]
        mail = MailNetwork()
        msg = self.f.queue_trade(mail, "T1", ship_id=ship_id)
        self.assertEqual(msg["bandwidth_hz"], 2400)
        self.assertEqual(self.f.trades["T1"]["ship_id"], ship_id)
        for _ in range(20):
            mail.step(loss=0, budget_frames=64)
            self.f.sync_mail(mail)
            if self.f.trades["T1"]["status"] == "settled":
                break
        self.assertEqual(self.f.trades["T1"]["status"], "settled")
        self.assertNotIn("radio_mission", seller.fleet[ship_id])

    def test_failed_mission_returns_damaged_ship_and_hard_mode_destroys(self):
        for hard in (False, True):
            f = Federation.demo()
            seller, buyer = list(f.worlds)
            good = f.worlds[seller].specialization
            f.contract_syncs[":".join(sorted((seller, buyer)))] = {
                "status": "synchronized", "source": "test_fixture"}
            f.propose("FAIL", seller, buyer, good, 1, 100)
            f.reserve("FAIL")
            world = f.worlds[seller]
            if hard:
                world.command("hard", "set_hard_mode", enabled=True)
            ship_id = world.active_ship_id
            world.fleet[ship_id]["condition"] = 20
            mail = MailNetwork()
            msg = f.queue_trade(mail, "FAIL")
            msg["ttl"] = 1
            mail.step(loss=1)
            mail.step(loss=1)
            changes = f.sync_mail(mail)
            self.assertEqual(f.trades["FAIL"]["status"], "reconcile_required")
            self.assertIsNone(changes[0]["ship_result"])
            self.assertIn(ship_id, world.fleet)
            self.assertEqual(world.fleet[ship_id]["condition"], 20)


if __name__ == "__main__":
    unittest.main()
