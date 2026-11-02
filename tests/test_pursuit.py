"""Cargo and passenger pursuit is visible, bounded, and can be mitigated."""
import time
import unittest
from unittest.mock import patch
from tradenet import Game, GameError


class PursuitTests(unittest.TestCase):
    def test_packed_unique_attracts_raiders_and_shipyard_fitting_shields_it(self):
        g=Game.new(42)
        module=g._recover_module('pilgrims_lantern','wreck')
        g._all_arrivals()
        self.assertEqual(g.ship['pursuit']['sources'][0]['id'],module['id'])
        g.command('fit','install_module',module_id=module['id'])
        g._all_arrivals()
        self.assertNotIn('pursuit',g.ship)

    def test_pressure_closes_slowly_and_station_prevents_interception(self):
        g=Game.new(42)
        g._recover_module('last_word','wreck')
        now=time.time();g._update_pursuit(g.ship,now)
        for step in range(1,31):g._update_pursuit(g.ship,now+5*step)
        self.assertEqual(g.ship['pursuit']['progress'],.75)
        self.assertNotIn('flight_encounter',g.ship)
        self.assertIsNone(g.ship['destination'])

    def test_inflight_pursuit_produces_real_intercept_and_cooldown(self):
        g=Game.new(42);g._recover_module('last_word','wreck')
        now=time.time();g._update_pursuit(g.ship,now)
        g.ship.update(destination='Kepler',arrival_at=now+100,departed_at=now,travel_seconds=100)
        for step in range(1,14):g._update_pursuit(g.ship,now+step*5)
        self.assertTrue(g.ship['flight_encounter']['pursuit'])
        self.assertEqual(g.ship['flight_encounter']['status'],'pending')
        self.assertIsNone(g.ship['arrival_at'])
        result=g.command('pay','resolve_transit_encounter',choice='pay')
        self.assertGreater(result['toll'],0)
        self.assertGreater(g.ship['pursuit']['cooldown_until'],time.time())

    def test_jettison_frees_hold_breaks_pursuit_and_prevents_unique_recovery(self):
        g=Game.new(42);module=g._recover_module('last_word','wreck')
        g._all_arrivals();self.assertEqual(g.cargo_used(),1)
        g.ship.update(destination='Kepler',arrival_at=time.time()+100,departed_at=time.time(),travel_seconds=100)
        result=g.command('drop','jettison_module',module_id=module['id'])
        self.assertIn('break off',result['outcome'])
        self.assertNotIn('pursuit',g.ship)
        self.assertEqual(g.cargo_used(),0)
        self.assertEqual(g.module_inventory[module['id']]['status'],'jettisoned')
        self.assertEqual(g.command('drop','jettison_module',module_id=module['id']),result)
        with self.assertRaises(GameError):g.command('twice','jettison_module',module_id=module['id'])
        with self.assertRaises(GameError):g._recover_module('last_word','another wreck')

    def test_vip_warning_and_remaining_passenger_pursuit_cannot_be_jettisoned(self):
        g=Game.new(42)
        job=next(job for job in g.vip_jobs.values() if job['pursuit_risk'])
        g.ship['location']=job['origin'];g._bind_ship()
        g.command('board','accept_vip',job_id=job['id'])
        module=g._recover_module('last_word','wreck')
        g._all_arrivals()
        self.assertEqual(len(g.ship['pursuit']['sources']),2)
        g.command('drop','jettison_module',module_id=module['id'])
        self.assertEqual(g.ship['vip_job'],job['id'])
        self.assertEqual(g.ship['pursuit']['sources'][0]['kind'],'vip')
        with self.assertRaises(GameError):g.command('no-passenger-drop','jettison_module',module_id=job['id'])

    def test_installed_and_other_ships_modules_cannot_be_jettisoned(self):
        g=Game.new(42);g.credits=10000
        module=g._recover_module('last_word','wreck')
        g.command('fit','install_module',module_id=module['id'])
        with self.assertRaises(GameError):g.command('drop-fitted','jettison_module',module_id=module['id'])

    def test_offline_time_and_pending_decisions_do_not_create_instant_ambush(self):
        g=Game.new(42);g._recover_module('last_word','wreck')
        now=time.time();g._update_pursuit(g.ship,now)
        g.ship.update(destination='Kepler',arrival_at=now+90000,departed_at=now,travel_seconds=90000)
        g._update_pursuit(g.ship,now+86400)
        self.assertLess(g.ship['pursuit']['progress'],.1)
        g.ship['flight_encounter']={'status':'pending'}
        progress=g.ship['pursuit']['progress']
        g._update_pursuit(g.ship,now+86405)
        self.assertEqual(g.ship['pursuit']['progress'],progress)
        restored=Game.from_dict(g.to_dict())
        self.assertEqual(restored.ship['pursuit'],g.ship['pursuit'])
