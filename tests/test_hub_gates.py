"""Progression checkpoints belong near Haven and must never strand an old fleet."""
import unittest
from unittest.mock import patch
from tradenet import Game, GameError


class HubGateTests(unittest.TestCase):
    def test_two_open_approaches_and_other_early_forks_have_reachable_quests(self):
        g=Game.new(42)
        self.assertTrue(g.route_status('Haven','Kepler')['open'])
        self.assertTrue(g.route_status('Haven','Vesper')['open'])
        for node in ('Prospect','Meridian','Drift'):
            status=g.route_status('Haven',node)
            self.assertFalse(status['open'])
            self.assertLessEqual(g.ports[node]['map_depth'],2)
            job=g.local_jobs[g.ports[node]['map_gate']['contract_id']]
            self.assertEqual(job['destination'],'Haven')
            self.assertTrue(g.route_status('Haven',job['origin'])['open'])
        normal=[job for job in g.local_jobs.values() if job['status']=='open' and job.get('kind') not in ('frontier_gate','dispatch')]
        self.assertEqual(len(normal),2)
        for job in normal:self.assertTrue(g.route_status('Haven',job['destination'])['open'])

    def test_gate_contract_unlocks_both_route_modes_and_cannot_pay_twice(self):
        g=Game.new(42)
        for mode in ('network','direct'):
            g.command('plot-'+mode,'plot_route',origin='Haven',destination='Prospect',mode=mode)
            with self.assertRaisesRegex(GameError,'Corridor blocked'):
                g.command('blocked-'+mode,'follow_route')
        job=g.local_jobs['hub-clearance-prospect']
        g.cargo[job['good']]=job['quantity']
        g.command('clear','deliver_local',job_id=job['id'])
        self.assertTrue(g.route_status('Haven','Prospect')['open'])
        with self.assertRaises(GameError):g.command('twice','deliver_local',job_id=job['id'])
        restored=Game.from_dict(g.to_dict())
        self.assertTrue(restored.route_status('Haven','Prospect')['open'])
        with patch.object(Game,'blocked_port',return_value=''):
            result=g.command('depart','travel',destination='Prospect')
        self.assertEqual(result['destination'],'Prospect')

    def test_superseded_and_missing_contracts_are_repaired_and_protected(self):
        g=Game.new(42)
        g.local_jobs['hub-clearance-drift']['status']='superseded'
        del g.local_jobs['hub-clearance-prospect']
        restored=Game.from_dict(g.to_dict())
        for node in ('Drift','Prospect'):
            key=restored.ports[node]['map_gate']['contract_id']
            self.assertEqual(restored.local_jobs[key]['status'],'open')
        restored.tick+=8
        restored._refresh_sector_events()
        for node in ('Drift','Prospect','Meridian'):
            key=restored.ports[node]['map_gate']['contract_id']
            self.assertEqual(restored.local_jobs[key]['status'],'open')
        self.assertFalse(restored.route_status('Haven','Drift')['open'])

    def test_carrier_shortcut_does_not_bypass_a_contract_checkpoint(self):
        g=Game.new(42)
        g.ports['carrier:test']={'entity_type':'carrier','map_neighbors':['Haven','Prospect']}
        g.ports['Haven']['map_neighbors'].append('carrier:test')
        g.ports['Prospect']['map_neighbors'].append('carrier:test')
        status=g.route_status('Haven','Prospect')
        self.assertFalse(status['open'])
        self.assertEqual(status['blocked_by'],'Prospect')

    def test_legacy_visits_and_inflight_destination_keep_their_branches(self):
        g=Game.new(42)
        data=g.to_dict();data.pop('hub_gates_version')
        for name in ('Prospect','Meridian','Drift'):data['ports'][name].pop('map_gate',None)
        for key in list(data['local_jobs']):
            if key.startswith('hub-clearance-'):del data['local_jobs'][key]
        data['visited_ports'].append('Aurora')
        data['fleet'][data['active_ship_id']]['destination']='Bastion'
        data['fleet'][data['active_ship_id']]['arrival_at']=9999999999
        restored=Game.from_dict(data)
        self.assertTrue(restored.route_status('Haven','Prospect')['open'])
        self.assertTrue(restored.route_status('Haven','Meridian')['open'])
        self.assertFalse(restored.route_status('Haven','Drift')['open'])
