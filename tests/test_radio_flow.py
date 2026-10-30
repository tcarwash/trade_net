"""Two independent station ledgers exchanging bounded application frames."""

import hashlib
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tradenet.engine import Game, BASE_PRICE, GameError
from tradenet.network import Network
from tradenet import radio_exchange
from tradenet.web import App


def station(callsign, seed):
    app = App.__new__(App)
    app.callsign = callsign
    app.game = Game.new(seed)
    app.net = Network(callsign)
    app.lock = threading.RLock()
    app.radio_contacts = {}
    app.radio_contracts = {}
    app.radio_resources = {}
    app.radio_reservations = {}
    app.radio_processed = {}
    app.radio_assemblies = {}
    app.radio_transmissions = {}
    app.radio_inbox = []
    app.data2g = ("127.0.0.1", 8300, 8100, "TRADENET")
    app.persist = lambda: None
    app._ensure_radio_contracts()
    return app


def receive(receiver, payload):
    reply = None
    for frame in radio_exchange.frames(payload):
        reply = receiver._handle_received_frame(frame) or reply
    return reply


def outgoing(app, payload, purpose, destination, contract_id=""):
    message = radio_exchange.decode(payload)
    app.radio_transmissions[message["i"]] = {
        "id": message["i"], "message_id": message["i"],
        "payload_hash": hashlib.sha256(payload).hexdigest()[:16],
        "purpose": purpose, "destination": destination, "contract_id": contract_id,
        "status": "awaiting_ack", "ship_id": app.game.ship["id"]}


class RadioFlowTests(unittest.TestCase):
    def test_radio_reservation_requires_imported_warehouse_goods(self):
        alice = station('W1AAA', 11)
        alice.radio_contacts['W2BBB'] = 1
        contract = {'id': 'W2BBB-C001', 'issuer': 'W2BBB', 'good': 'food',
                    'quantity': 3, 'status': 'open'}
        alice.radio_contracts['W2BBB'] = [contract]
        alice.game.ports['Haven']['stock']['food'] = 200
        request = {'action': 'exchange_reserve', 'station': 'W2BBB', 'contract_id': contract['id']}
        with self.assertRaises(GameError):
            alice.execute(request)
        alice.game.export_warehouse['food'] = 3
        alice.execute(request)
        self.assertEqual(alice.game.export_warehouse['food'], 0)
        alice._release_radio_reservation({'contract_id': contract['id']})
        self.assertEqual(alice.game.export_warehouse['food'], 3)

    def test_contact_delivery_and_replay_across_two_stations(self):
        alice, bob = station("W1AAA", 11), station("W2BBB", 22)
        contact = radio_exchange.encode_message({
            "v": 1, "t": "contact", "i": "first-contact", "f": alice.callsign,
            "d": bob.callsign, **alice._radio_wire_profile(),
            "c": radio_exchange.wire_contracts(alice.radio_contracts[alice.callsign]),
            "n": []})
        outgoing(alice, contact, "contact", bob.callsign)
        contact_frames = radio_exchange.frames(contact)
        self.assertTrue(all(len(frame) <= 200 for frame in contact_frames))
        before = bob.game.credits
        for frame in contact_frames[:-1]:
            self.assertIsNone(bob._handle_received_frame(frame))
        self.assertEqual(bob.game.credits, before)
        reply = bob._handle_received_frame(contact_frames[-1])
        self.assertIsNotNone(reply)
        self.assertGreater(bob.game.credits, before)
        receive(alice, reply)
        self.assertIn(bob.callsign, alice.radio_contacts)
        self.assertGreater(alice.game.credits, 80)
        self.assertTrue(alice.radio_contracts[bob.callsign])

        request = next(c for c in bob.radio_contracts[bob.callsign]
                       if c["status"] == "open")
        good, quantity = request["good"], request["quantity"]
        alice.game.export_warehouse[good] = quantity
        alice.execute({"action": "exchange_reserve", "station": bob.callsign,
                       "contract_id": request["id"]})
        credits_before_delivery = alice.game.credits
        alice.radio_resources["W3CCC"] = {"richness": "iridium",
            "stock": [1, 2, 3], "production": [2, 3, 4], "observed_at": 100}
        alice.radio_contracts["W3CCC"] = [{"id": "W3CCC-C001", "good": "ore",
            "quantity": 3, "status": "open"}]
        delivery = radio_exchange.encode_message({
            "v": 1, "t": "delivery", "i": alice.radio_reservations[request["id"]]["message_id"],
            "f": alice.callsign, "d": bob.callsign, "c": request["id"],
            "g": good, "q": quantity,
            "n": alice._radio_neighbors(exclude=bob.callsign, detail=True)})
        outgoing(alice, delivery, "delivery", bob.callsign, request["id"])
        stock_before = bob.game.ports["Haven"]["stock"][good]
        credit_before = bob.game.credits
        delivery_reply = receive(bob, delivery)
        self.assertIsNotNone(delivery_reply)
        self.assertEqual(bob.game.ports["Haven"]["stock"][good], stock_before + quantity)
        self.assertGreater(bob.game.credits, credit_before)
        self.assertEqual(bob.radio_resources["W3CCC"]["via"], alice.callsign)
        self.assertEqual(bob.radio_resources["W3CCC"]["stock"], [1, 2, 3])
        self.assertEqual(receive(bob, delivery), delivery_reply)
        self.assertEqual(bob.game.ports["Haven"]["stock"][good], stock_before + quantity)
        receive(alice, delivery_reply)
        self.assertEqual(alice.radio_transmissions[radio_exchange.decode(delivery)["i"]]["status"], "delivered")
        expected_reward = min(1500, 100 + 2 * BASE_PRICE[good] * quantity)
        self.assertEqual(alice.game.credits, credits_before_delivery + expected_reward)
        receive(alice, delivery_reply)
        self.assertEqual(alice.game.credits, credits_before_delivery + expected_reward)
        self.assertNotIn(request["id"], alice.radio_reservations)
        self.assertTrue(any(c["status"] == "open" and c["id"] != request["id"]
                            for c in alice.radio_contracts[bob.callsign]))

    def test_unmatched_ack_does_not_create_contact_or_credit(self):
        app = station("W1AAA", 11)
        fake = radio_exchange.encode_message({"v": 1, "t": "contact_ack", "i": "fake",
            "f": "W2BBB", "d": app.callsign, "r": "unknown", "h": "0" * 16,
            "cr": 25, "x": "iridium"})
        before = app.game.credits
        self.assertIsNone(receive(app, fake))
        self.assertEqual(app.game.credits, before)
        self.assertNotIn("W2BBB", app.radio_contacts)

    def test_lost_contact_reply_can_be_retried_without_double_reward(self):
        alice, bob = station("W1AAA", 11), station("W2BBB", 22)
        def contact(message_id):
            return radio_exchange.encode_message({"v": 1, "t": "contact",
                "i": message_id, "f": alice.callsign, "d": bob.callsign,
                **alice._radio_wire_profile(),
                "c": radio_exchange.wire_contracts(alice.radio_contracts[alice.callsign]),
                "n": []})
        first = contact("first-lost")
        initial = bob.game.credits
        self.assertIsNotNone(receive(bob, first))
        after_first = bob.game.credits
        self.assertGreater(after_first, initial)
        retry = contact("new-attempt")
        outgoing(alice, retry, "contact", bob.callsign)
        reply = receive(bob, retry)
        self.assertEqual(bob.game.credits, after_first)
        self.assertIsNotNone(reply)
        receive(alice, reply)
        self.assertIn(bob.callsign, alice.radio_contacts)
        self.assertGreater(alice.game.credits, 80)

    def test_delivery_retry_reuses_exact_staged_payload(self):
        alice = station("W1AAA", 11)
        alice.radio_contacts["W2BBB"] = 1
        contract = {"id": "W2BBB-C0001", "issuer": "W2BBB", "good": "ore",
                    "quantity": 5, "status": "open"}
        alice.radio_contracts["W2BBB"] = [contract]
        alice.game.export_warehouse["ore"] = 5
        alice.execute({"action": "exchange_reserve", "station": "W2BBB",
                       "contract_id": contract["id"]})
        alice.radio_resources["W3CCC"] = {"richness": "iridium", "stock": [1, 2, 3],
                                           "production": [3, 2, 1], "observed_at": 1}
        mode = SimpleNamespace(mode_id="n4-16qam-r1/3", bandwidth_hz=200,
            bytes_per_codeword=76, max_codewords=12, seconds_max=42)
        alice._send_radio_frames = lambda *args: None
        with patch("tradenet.web.Data2GClient") as client:
            modem = client.return_value.__enter__.return_value
            modem.modes.return_value = [mode]
            request = {"action": "radio_transmit", "purpose": "delivery",
                       "station": "W2BBB", "contract_id": contract["id"],
                       "mode_id": mode.mode_id}
            alice.execute(request)
            original = alice.radio_reservations[contract["id"]]["payload_hex"]
            job = next(iter(alice.radio_transmissions.values()))
            job["status"] = "failed"
            alice.game.ship.pop("radio_mission", None)
            alice.radio_resources["W3CCC"]["stock"] = [99, 99, 99]
            alice.execute(request)
        self.assertEqual(alice.radio_reservations[contract["id"]]["payload_hex"], original)
        self.assertEqual(len(alice.radio_transmissions), 1)
        self.assertEqual(next(iter(alice.radio_transmissions.values()))["retry_count"], 1)

    def test_overheard_contact_is_gossip_without_settlement(self):
        listener = station("W3CCC", 33)
        sender = station("W1AAA", 11)
        message = radio_exchange.encode_message({"v": 1, "t": "contact",
            "i": "for-someone-else", "f": sender.callsign, "d": "W2BBB",
            **sender._radio_wire_profile(),
            "c": radio_exchange.wire_contracts(sender.radio_contracts[sender.callsign]),
            "n": []})
        before = listener.game.credits
        self.assertIsNone(receive(listener, message))
        self.assertEqual(listener.game.credits, before)
        self.assertNotIn(sender.callsign, listener.radio_contacts)
        self.assertIn(sender.callsign, listener.radio_resources)
        self.assertTrue(listener.radio_contracts[sender.callsign])


if __name__ == "__main__":
    unittest.main()
