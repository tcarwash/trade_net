"""Persistent physical mods, settlement projects, and explicit plotted courses."""
import time
import unittest
from copy import deepcopy
from unittest.mock import patch
from tradenet import Game, GameError
from tradenet.progression import MODULES, PROJECTS
from tests.test_pirate_rewards import pirate_game


class ModuleTests(unittest.TestCase):
    def setUp(self):
        self.g = Game.new(42)
        self.g.credits = 20000

    def recover(self, template='pilgrims_lantern'):
        return self.g._recover_module(template,'test wreck')['id']

    def test_install_store_transfer_and_reload_preserve_individual_identity(self):
        g = self.g
        module_id = self.recover()
        self.assertEqual(g.cargo_used(), 1)
        g.command('fit','install_module',module_id=module_id)
        self.assertEqual(g.cargo_used(), 2)
        self.assertEqual(g.module_effects()['discovery_bonus'],40)
        g.command('remove','uninstall_module',module_id=module_id)
        self.assertEqual(g.cargo_used(),0)
        self.assertEqual(g.module_effects(),{})
        active = g.active_ship_id
        other = g.command('buy','purchase_ship',tier=0)['ship_id']
        g.command('transfer','install_module',module_id=module_id,ship_id=other)
        self.assertEqual(g.active_ship_id,active)
        self.assertEqual(g.module_effects(other)['fuel_saving'],1)
        self.assertEqual(g.module_inventory[module_id]['ship_id'],other)
        saved = Game.from_dict(g.to_dict())
        self.assertEqual(saved.module_inventory,g.module_inventory)
        self.assertEqual(saved.module_effects(other),g.module_effects(other))
        with self.assertRaises(GameError):
            saved._recover_module('pilgrims_lantern','second wreck')

    def test_remote_lockers_and_inflight_work_are_rejected(self):
        g=self.g
        module_id=self.recover()
        g.command('store','uninstall_module',module_id=module_id)
        g.ship['location']='Kepler';g._bind_ship()
        with self.assertRaisesRegex(GameError,'locker'):
            g.command('remote','install_module',module_id=module_id)
        g.ship['location']='Haven';g._bind_ship()
        g.ship['destination']='Kepler'
        with self.assertRaisesRegex(GameError,'transit'):
            g.command('flying','install_module',module_id=module_id)

    def test_slots_and_space_are_enforced_without_losing_items(self):
        g=self.g
        for index,template in enumerate(('economizer','bulkhead','salvage_rig')):
            module_id=self.recover(template)
            g.command(f'fit-{index}','install_module',module_id=module_id)
        module_id=self.recover('mercy_of_dawn')
        with self.assertRaisesRegex(GameError,'at most 3'):
            g.command('fourth','install_module',module_id=module_id)
        self.assertEqual(g.module_inventory[module_id]['status'],'stowed')
        other=Game.new(42);module=other._recover_module('last_word','wreck')
        other.cargo['ore']=28
        with self.assertRaisesRegex(GameError,'cargo space'):
            other.command('full','install_module',module_id=module['id'])
        self.assertEqual(other.module_inventory[module['id']]['status'],'stowed')

    def test_standard_equipment_can_be_uninstalled_and_reused(self):
        g=self.g
        g.command('buy','buy_equipment',item='scanner')
        module=g.command('store','uninstall_equipment',item='scanner')
        self.assertNotIn('scanner',g.ship['equipment'])
        other=g.command('ship','purchase_ship',tier=0)['ship_id']
        g.command('fit','install_module',module_id=module['module_id'],ship_id=other)
        self.assertIn('scanner',g.fleet[other]['equipment'])
        self.assertNotIn('scanner',g.ship['equipment'])
        g.command('select','select_ship',ship_id=other)
        g.command('store-again','uninstall_equipment',item='scanner')
        self.assertEqual(len(g.module_inventory),1)

    def test_abilities_affect_fuel_combat_repairs_and_discoveries(self):
        g=self.g
        module_id=self.recover('pilgrims_lantern')
        with patch.object(Game,'blocked_port',return_value=''):
            before=g.travel_fuel_quote('Haven','Kepler')['fuel_cost']
            g.command('fit','install_module',module_id=module_id)
            self.assertEqual(g.travel_fuel_quote('Haven','Kepler')['fuel_cost'],before-1)
        mercy=self.recover('mercy_of_dawn');g.command('mercy','install_module',module_id=mercy)
        g.ship['condition']=50
        self.assertEqual(g._repair_cost(g.active_ship_id),80)
        pirate=pirate_game(strength=4)
        # Fit while docked, then restore the test intercept.
        encounter=deepcopy(pirate.ship['flight_encounter'])
        pirate.ship['destination']=None;pirate.ship.pop('flight_encounter')
        weapon=pirate._recover_module('last_word','wreck')
        pirate.command('fit','install_module',module_id=weapon['id'])
        pirate.ship.update(destination='Kepler',arrival_at=None,flight_encounter=encounter)
        result=pirate.command('fight','resolve_transit_encounter',choice='fight')
        self.assertTrue(result['route_cleared'])

    def test_unique_drops_are_not_reserved_twice_and_cannot_be_rerolled(self):
        g=self.g
        first=g.module_drop('wreck',unique=True)
        self.assertEqual(first,g.module_drop('wreck',unique=True))
        g.ship['flight_encounters']=[{'choices':[{'module_template':first}]}]
        self.assertNotEqual(first,g.module_drop('other',unique=True))
        self.recover(first)
        g.ship['flight_encounters']=[]
        self.assertNotEqual(first,g.module_drop('third',unique=True))


class SettlementTests(unittest.TestCase):
    def setUp(self):
        self.g=Game.new(42)
        self.g.ship['location']='Prospect';self.g._bind_ship()
        self.g.visited_ports.append('Prospect')
        self.g.observe_markets()
        self.g._reveal_encounter('Prospect')

    def test_partial_deliveries_and_permanent_growth_rewards(self):
        g=self.g
        original=g.price('Prospect','food','buy')
        g.cargo['food']=3
        g.command('partial','supply_settlement',port='Prospect',quantities={'food':3},level=0)
        self.assertEqual(g.settlement_quote('Prospect')['delivered'],{'food':3})
        for level,project in enumerate(PROJECTS):
            quote=g.settlement_quote('Prospect')
            amounts={good:n-quote['delivered'].get(good,0) for good,n in project['requirements'].items()}
            g.cargo.update(amounts)
            result=g.command(f'project-{level}','supply_settlement',port='Prospect',quantities=amounts,level=level)
            self.assertTrue(result['completed'])
            self.assertEqual(result['level'],level+1)
            if level==0:self.assertEqual(g.price('Prospect','food','buy'),max(1,original*97//100))
            if level==2:
                self.assertIn('shipyard',g.ports['Prospect']['services'])
                self.assertEqual(g.module_inventory[result['module']['id']]['status'],'stored')
                self.assertEqual(g.module_inventory[result['module']['id']]['port'],'Prospect')
        self.assertTrue(g.settlement_quote('Prospect')['complete'])
        restored=Game.from_dict(g.to_dict())
        self.assertEqual(restored.settlement_progress,g.settlement_progress)
        self.assertIn('shipyard',restored.ports['Prospect']['services'])
        self.assertEqual(restored.ports['Prospect']['production'],g.ports['Prospect']['production'])

    def test_wrong_location_stale_level_and_invalid_deliveries_rollback(self):
        g=self.g
        for port,quantity,level in [('Haven',{'food':1},0),('Prospect',{'food':7},0),
                                    ('Prospect',{'food':True},0),('Prospect',{'food':1},1)]:
            before=g.to_dict()
            with self.assertRaises(GameError):
                g.command('invalid','supply_settlement',port=port,quantities=quantity,level=level)
            self.assertEqual(g.to_dict(),before)


class RoutePlannerTests(unittest.TestCase):
    def test_network_and_direct_courses_have_different_paths_and_costs(self):
        g=Game.new(42)
        for site in g.ports.values():
            if site.get('map_gate'):site['map_gate']['unlocked']=True
        with patch.object(Game,'blocked_port',return_value=''):
            network=g.plan_route('Haven','Drift','network')
            direct=g.plan_route('Haven','Drift','direct')
        self.assertEqual(network['path'],['Haven','Kepler','Drift'])
        self.assertEqual(direct['path'],['Haven','Drift'])
        self.assertEqual(network['fuel'],sum(leg['fuel'] for leg in network['legs']))
        self.assertEqual(direct['fuel'],g.travel_fuel_quote('Haven','Drift')['fuel_cost'])
        g.command('plot','plot_route',origin='Haven',destination='Drift',mode='network')
        restored=Game.from_dict(g.to_dict())
        self.assertEqual(restored.ship['planned_route'],g.ship['planned_route'])
        with patch.object(Game,'blocked_port',return_value=''):
            first=g.command('leg','follow_route')
        self.assertEqual(first['destination'],'Kepler')
        g.ship['flight_encounters']=[]
        g.ship['arrival_at']=time.time()-1
        g._all_arrivals()
        with patch.object(Game,'blocked_port',return_value=''):
            second=g.command('next','follow_route')
        self.assertEqual(second['destination'],'Drift')

    def test_direct_departure_and_arbitrary_origin_preview(self):
        g=Game.new(42)
        for site in g.ports.values():
            if site.get('map_gate'):site['map_gate']['unlocked']=True
        plan=g.command('other','plot_route',origin='Kepler',destination='Vesper',mode='direct')
        self.assertEqual(plan['path'],['Kepler','Vesper'])
        with self.assertRaises(GameError):g.command('wrong','follow_route')
        g.command('here','plot_route',origin='Haven',destination='Drift',mode='direct')
        result=g.command('go','follow_route')
        self.assertEqual(result['destination'],'Drift')
