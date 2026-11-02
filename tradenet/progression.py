"""Physical ship modifications and permanent settlement supply projects."""
from copy import deepcopy
import random
import time

MODULES = {
    'economizer': dict(name='Reclaimed drive coils', rarity='salvaged', space=2,
        description='Save 1 tank fuel per flight. Occupies 2 cargo.', effects={'fuel_saving':1}),
    'bulkhead': dict(name='Patchwork bulwark', rarity='salvaged', space=2,
        description='Absorb 2 extra hull damage in encounters. Occupies 2 cargo.', effects={'armor':2}),
    'salvage_rig': dict(name='Magnetic recovery rig', rarity='salvaged', space=2,
        description='Find 1 additional common cargo unit in cleared pirate wrecks. Occupies 2 cargo.', effects={'salvage_bonus':1}),
    'pilgrims_lantern': dict(name="Pilgrim’s Lantern", rarity='unique', space=2, signature=True,
        description='Packed signature attracts raiders. Save 1 fuel per flight and earn 40 extra credits on first discoveries. Occupies 2 cargo.',
        effects={'fuel_saving':1, 'discovery_bonus':40}),
    'last_word': dict(name='The Last Word', rarity='unique', space=3, signature=True,
        description='Packed signature attracts raiders. Deal 3 extra damage to pirate groups; evasion exposes you to 2 extra hull damage. Occupies 3 cargo.',
        effects={'weapon_power':3, 'evade_penalty':2}),
    'mercy_of_dawn': dict(name='Mercy of Dawn', rarity='unique', space=2,
        description='Absorb 4 extra hull damage and reduce repair bills by 20 percentage points. Occupies 2 cargo.',
        effects={'armor':4, 'repair_discount':20}),
    'magpies_promise': dict(name="Magpie’s Promise", rarity='unique', space=2, signature=True,
        description='Packed signature attracts raiders. Find 2 extra common cargo units in pirate wrecks and earn 20 extra bounty credits. Occupies 2 cargo.',
        effects={'salvage_bonus':2, 'bounty_bonus':20}),
}
PROJECTS = (
    dict(name='Secure the supply line', requirements={'food':6, 'medicine':2}, reward=150,
         effect='Permanent 3% local buying discount; settlement becomes Established.'),
    dict(name='Build the production district', requirements={'ore':8, 'fuel':4}, reward=240,
         effect='Local specialty production increases by 1 per economy tick; settlement becomes Growing.'),
    dict(name='Open the frontier shipyard', requirements={'ore':10, 'medicine':5}, reward=350,
         effect='Unlock a local shipyard and recover a named unique mod while supplies last; settlement becomes Thriving.'),
)
SETTLEMENT_STAGES = ('Frontier', 'Established', 'Growing', 'Thriving')


def fail(message):
    from .engine import GameError
    raise GameError(message)


class Progression:
    def module_effects(self, ship_id=None):
        ship_id = ship_id or self.active_ship_id
        totals = {}
        for module in self.module_inventory.values():
            if module.get('ship_id') == ship_id and module['status'] == 'installed':
                for key, amount in MODULES.get(module['template'], {}).get('effects', {}).items():
                    totals[key] = totals.get(key, 0) + amount
        return totals

    def module_cargo_used(self, ship_id):
        return sum(1 if m['status'] == 'stowed' else MODULES[m['template']]['space']
                   for m in self.module_inventory.values()
                   if m.get('ship_id') == ship_id and m['status'] in ('installed','stowed')
                   and m['template'] in MODULES)

    def module_drop(self, source, *, unique=False):
        """Roll once into a persistent offer; pending uniques cannot be offered twice."""
        reserved = set(self.unique_module_history)
        for ship in self.fleet.values():
            events = [ship.get('flight_encounter', {})] + ship.get('flight_encounters', [])
            for event in events:
                reserved.update(option.get('module_template') for option in event.get('choices', []))
        pool = [key for key, template in MODULES.items()
                if (template['rarity'] == 'unique') == unique and key not in reserved]
        if not pool:
            return None
        return random.Random(f'{self.seed}:module:{source}').choice(pool)

    def _recover_module(self, template, source):
        if template not in MODULES:
            fail('unknown recovered module')
        if MODULES[template]['rarity'] == 'unique':
            if template in self.unique_module_history:
                fail('this unique module has already been recovered')
            self.unique_module_history.append(template)
        module_id = f'module-{self.next_module_number}'
        self.next_module_number += 1
        module = dict(id=module_id, template=template, status='stowed', ship_id=self.active_ship_id,
                      port=None, galaxy=self.ship.get('galaxy','home'), source=source, found_tick=self.tick)
        self.module_inventory[module_id] = module
        return deepcopy(module)

    def _module_dock(self):
        self._available()
        if self.ship.get('class_id') == 'carrier':
            fail('fit modifications to a flight vessel')
        self._require_service('shipyard')

    def _install_module(self, module_id, ship_id=None):
        if ship_id is not None and ship_id != self.active_ship_id:
            if ship_id not in self.fleet:
                fail('unknown target vessel')
            target = self.fleet[ship_id]
            if target.get('location') != self.location or target.get('galaxy') != self.ship.get('galaxy'):
                fail('both vessels must be at the same port')
            self._module_dock()
            original = self.active_ship_id
            try:
                self.active_ship_id = ship_id
                self._bind_ship()
                return self._install_module(module_id)
            finally:
                self.active_ship_id = original
                self._bind_ship()
        self._module_dock()
        module = self.module_inventory.get(module_id)
        if not module or module['status'] not in ('stored','stowed'):
            fail('this module is not available to install')
        if module['status'] == 'stowed':
            if module.get('ship_id') != self.active_ship_id:
                fail('unload the module into a port locker before another ship can use it')
        elif module.get('port') != self.location or module.get('galaxy') != self.ship.get('galaxy','home'):
            fail('travel to the port locker holding this module')
        template = module['template']
        if template.startswith('standard:'):
            from .engine import EQUIPMENT, EQUIPMENT_CARGO_SPACE
            item = template.split(':',1)[1]
            if item not in EQUIPMENT or (item != 'weapons' and item in self.ship['equipment']):
                fail('this system is already installed')
            space = EQUIPMENT_CARGO_SPACE.get(item, 0)
        else:
            if sum(m.get('ship_id') == self.active_ship_id and m['status'] == 'installed'
                   and m['template'] in MODULES for m in self.module_inventory.values()) >= 3:
                fail('a vessel can fit at most 3 salvaged modifications')
            space = MODULES[template]['space']
        released = 1 if module['status'] == 'stowed' else 0
        if self.cargo_used() + self.incoming_reserved + space - released > self.ship['capacity']:
            fail('not enough cargo space to fit this modification')
        if template.startswith('standard:'):
            self.ship['equipment'].append(item)
        module.update(status='installed', ship_id=self.active_ship_id, port=None)
        return {'module_id':module_id, 'name':self.module_name(template), 'ship_id':self.active_ship_id}

    def _uninstall_module(self, module_id):
        self._module_dock()
        module = self.module_inventory.get(module_id)
        if not module or module.get('ship_id') != self.active_ship_id or module['status'] not in ('installed','stowed'):
            fail('this vessel does not carry that module')
        if module['status'] == 'installed' and module['template'].startswith('standard:'):
            if module['template'] == 'standard:life_support' and self.ports[self.location].get('atmosphere') in ('toxic','corrosive'):
                fail('keep life support fitted until you leave this hostile world')
            self.ship['equipment'].remove(module['template'].split(':',1)[1])
        module.update(status='stored', ship_id=None, port=self.location,
                      galaxy=self.ship.get('galaxy','home'))
        return {'module_id':module_id, 'name':self.module_name(module['template']), 'port':self.location}

    def _uninstall_equipment(self, item):
        self._module_dock()
        if item not in self.ship['equipment']:
            fail('this equipment is not installed')
        if item == 'life_support' and self.ports[self.location].get('atmosphere') in ('toxic','corrosive'):
            fail('keep life support fitted until you leave this hostile world')
        existing = next((m for m in self.module_inventory.values()
                         if m['template'] == 'standard:'+item and m.get('ship_id') == self.active_ship_id
                         and m['status'] == 'installed'), None)
        if existing:
            return self._uninstall_module(existing['id'])
        self.ship['equipment'].remove(item)
        module_id = f'module-{self.next_module_number}'
        self.next_module_number += 1
        self.module_inventory[module_id] = dict(id=module_id, template='standard:'+item,
            status='stored', ship_id=None, port=self.location, galaxy=self.ship.get('galaxy','home'),
            source='Purchased equipment', found_tick=self.tick)
        return {'module_id':module_id,'name':self.module_name('standard:'+item),'port':self.location}

    @staticmethod
    def module_name(template):
        return MODULES.get(template, {}).get('name', template.replace('standard:','').replace('_',' ').title())

    def settlement_quote(self, port):
        site = self.ports.get(port, {})
        if port == 'Haven' or site.get('entity_type') != 'planet':
            return None
        progress = self.settlement_progress.get(port, {'level':0,'delivered':{}})
        level = progress['level']
        quote = dict(port=port, level=level, stage=SETTLEMENT_STAGES[level],
                     delivered=deepcopy(progress.get('delivered',{})), complete=level>=len(PROJECTS))
        if level < len(PROJECTS):
            quote.update(deepcopy(PROJECTS[level]))
        return quote

    def _supply_settlement(self, port, quantities, level):
        self._available()
        if self.ship.get('galaxy','home') != 'home' or port != self.location:
            fail('dock at the settlement to deliver supplies')
        quote = self.settlement_quote(port)
        if not quote or quote['complete'] or type(level) is not int or level != quote['level']:
            fail('settlement project changed; review the current requirements')
        if not isinstance(quantities,dict) or not quantities:
            fail('select supplies for this project')
        progress = self.settlement_progress.setdefault(port, {'level':0, 'delivered':{}})
        for good, amount in quantities.items():
            remaining = quote['requirements'].get(good,0) - progress['delivered'].get(good,0)
            if type(amount) is not int or not 0 < amount <= remaining:
                fail('deliver positive whole quantities within the remaining project requirements')
            if self.cargo.get(good,0) < amount:
                fail('not enough project supplies aboard')
        for good, amount in quantities.items():
            self.cargo[good] -= amount
            self.ship.setdefault('export_cargo',{})[good] = max(0,self.ship.get('export_cargo',{}).get(good,0)-amount)
            progress['delivered'][good] = progress['delivered'].get(good,0) + amount
        completed = all(progress['delivered'].get(good,0) >= amount
                        for good, amount in quote['requirements'].items())
        reward, module = 0, None
        if completed:
            progress.update(level=level+1, delivered={})
            reward = quote['reward']
            self.credits += reward
            self.factions['traders'] += 2
            if level == 1:
                focus = max(self.ports[port]['production'], key=self.ports[port]['production'].get)
                self.ports[port]['production'][focus] += 1
                progress['specialty'] = focus
            if level == 2:
                services = self.ports[port].setdefault('services',[])
                if 'shipyard' not in services:
                    services.append('shipyard')
                template = self.module_drop('settlement:'+port, unique=True)
                if template:
                    # The reward waits in a local locker, even when the hold is full.
                    module = self._recover_module(template, 'Settlement project: '+port)
                    self.module_inventory[module['id']].update(status='stored',ship_id=None,port=port)
                    module = deepcopy(self.module_inventory[module['id']])
        return dict(port=port, completed=completed, reward=reward, level=progress['level'],
                    stage=SETTLEMENT_STAGES[progress['level']], module=module,
                    delivered=deepcopy(progress['delivered']))

    def plan_route(self, origin, destination, mode='network'):
        if mode not in ('network','direct') or origin == destination:
            fail('choose different ports and a network or direct route')
        corridor = self.route_status(origin,destination)
        if not corridor['reachable']:
            fail(corridor['reason'])
        path = corridor['path'] if mode == 'network' else [origin,destination]
        legs = []
        for first, second in zip(path,path[1:]):
            quote = self.travel_fuel_quote(first,second)
            blocked = self.route_connected(first,second) and self.asteroid_field_blocks(first,second)
            legs.append(dict(origin=first,destination=second,fuel=quote['fuel_cost'],
                             hazard=self.route_risk(first,second), asteroid_blocked=blocked))
        return dict(origin=origin,destination=destination,mode=mode,path=path,legs=legs,
                    fuel=sum(leg['fuel'] for leg in legs),open=corridor['open'],reason=corridor['reason'])

    def _plot_route(self, origin, destination, mode='network'):
        if not self.active_ship_id:
            fail('select a ship to plot its route')
        plan = self.plan_route(origin,destination,mode)
        self.ship['planned_route'] = deepcopy(plan)
        return plan

    def _follow_route(self):
        plan = self.ship.get('planned_route')
        if not plan or self.location not in plan['path']:
            fail('travel to the plotted origin or plot a new route from here')
        index = plan['path'].index(self.location)
        if index == len(plan['path'])-1:
            fail('this route is already complete')
        return self._travel(plan['path'][index+1])

    def _cancel_plotted_route(self):
        self.ship.pop('planned_route',None)
        return {'cancelled':True}


    def pursuit_sources(self, ship):
        sources = []
        passenger = self.vip_jobs.get(ship.get('vip_job'), {})
        if passenger.get('status') == 'aboard' and passenger.get('pursuit_risk'):
            sources.append({'kind':'vip', 'name':passenger['title'], 'jettisonable':False})
        for module in self.module_inventory.values():
            if (module.get('ship_id') == ship['id'] and module['status'] == 'stowed'
                    and MODULES.get(module['template'],{}).get('signature')):
                sources.append({'kind':'module','id':module['id'],
                    'name':MODULES[module['template']]['name'],'jettisonable':True})
        return sources

    def _update_pursuit(self, ship, now):
        sources = self.pursuit_sources(ship)
        if not sources:
            ship.pop('pursuit',None)
            return
        ship.pop('pursuit_notice',None)
        pursuit = ship.setdefault('pursuit',dict(progress=0.0,last_update=now,cooldown_until=0,contacts=0))
        pursuit['sources'] = sources
        # Do not turn an offline return, or an open decision dialog, into an ambush.
        elapsed = min(5.0,max(0.0,now-pursuit['last_update']))
        pursuit['last_update'] = now
        if ship.get('flight_encounter',{}).get('status') == 'pending' or now < pursuit.get('cooldown_until',0):
            return
        airborne = bool(ship.get('destination')) and not ship.get('radio_mission')
        pursuit['progress'] = min(1.0 if airborne else .75,
            pursuit['progress']+elapsed/(60 if airborne else 120))
        arrival = ship.get('arrival_at')
        if not airborne or pursuit['progress'] < 1 or arrival is None or now >= arrival:
            return
        pursuit['contacts'] += 1
        key = f"pursuit:{ship['id']}:{pursuit['contacts']}"
        strength = 6 + min(4,len(sources))
        self.pirate_groups[key] = strength
        duration = ship.get('travel_seconds') or 1
        progress = min(.99,max(.01,(now-(ship.get('departed_at') or now))/duration))
        ship['flight_encounter'] = dict(
            id=key, kind='pirates', title='Pursuing raiders intercepted you',
            description='Raiders followed the signature of '+', '.join(s['name'] for s in sources)+'.',
            status='pending', source='transit', pursuit=True, pirate_key=key,
            strength=strength, distance=2, risk={'kind':'pirates','damage':4},
            origin=ship['location'],destination=ship['destination'],progress=progress,
            elapsed_seconds=max(0.0,now-(ship.get('departed_at') or now)),
            remaining_seconds=max(0.0,arrival-now),trigger_at=now,
            choices=[{'id':'fight','label':'Fight'},{'id':'evade','label':'Evade','fuel':2},
                     {'id':'pay','label':'Pay toll'}])
        ship['arrival_at'] = None
        pursuit.update(progress=0.0,cooldown_until=now+90)

    def _jettison_module(self, module_id):
        if not self.active_ship_id:
            fail('select a surviving vessel')
        module = self.module_inventory.get(module_id)
        if not module or module.get('ship_id') != self.active_ship_id or module['status'] != 'stowed':
            fail('only packed modifications aboard this vessel can be jettisoned')
        name = self.module_name(module['template'])
        module.update(status='jettisoned', ship_id=None, port=None)
        sources = self.pursuit_sources(self.ship)
        if sources:
            pursuit = self.ship.get('pursuit')
            if pursuit:
                pursuit['progress'] *= .5
                pursuit['sources'] = sources
                pursuit['last_update'] = time.time()
            outcome = 'Signature reduced; the remaining VIP or cargo still attracts raiders.'
        else:
            self.ship.pop('pursuit',None)
            outcome = 'Attracting signature lost; pursuing raiders break off.'
        if self.ship.get('flight_encounter',{}).get('pursuit'):
            outcome += ' The current interception must still be resolved.'
        self.ship['pursuit_notice'] = outcome
        return dict(module_id=module_id,name=name,outcome=outcome)

    def _initialize_hub_gates(self):
        """Two starter approaches, with the other early forks opened by supply quests."""
        if self.hub_gates_version >= 1:
            return
        home = self.galaxies.get('home',{}).get('ports',{})
        visited = set(self.visited_ports)
        visited.update(ship.get('location') for ship in self.fleet.values())
        visited.update(ship.get('destination') for ship in self.fleet.values())
        for node,good,quantity,reward in (('Prospect','food',4,100),('Meridian','ore',3,130),('Drift','medicine',2,160)):
            if node not in home:
                continue
            # Preserve access already earned in an existing galaxy, including
            # ships currently travelling beyond the new checkpoint.
            unlocked = False
            for known in visited:
                cursor,seen = known,set()
                while cursor in home and cursor not in seen:
                    if cursor == node:
                        unlocked = True
                        break
                    seen.add(cursor);cursor=home[cursor].get('map_parent')
            key='hub-clearance-'+node.lower()
            existing=home[node].get('map_gate',{})
            unlocked = unlocked or bool(existing.get('unlocked'))
            self.local_jobs.setdefault(key,dict(id=key,kind='frontier_gate',
                title='Open the '+node+' branch',origin='Kepler',destination='Haven',
                good=good,quantity=quantity,reward=reward,
                status='delivered' if unlocked else 'open',deadline=self.tick+999_999_999,
                description=f'Deliver {quantity} {good} to Haven dispatch to chart and secure the approach to {node}. Permanently unlocks this branch.'))
            unlocked = unlocked or self.local_jobs[key]['status']=='delivered'
            home[node]['map_gate']=dict(kind='contract',contract_id=key,unlocked=unlocked,
                description=f'Haven dispatch: deliver {quantity} {good} to open the {node} branch.')
        self.hub_gates_version=1

    def combat_quote(self):
        encounter = self.ship.get('flight_encounter',{})
        if encounter.get('kind') != 'pirates' or encounter.get('status') != 'pending':
            return None
        weapons = self.ship.get('equipment',[]).count('weapons')
        effects = self.module_effects()
        pilot = self.crew_member(self.active_ship_id,'pilot')
        escape = max(15,min(90,65 + (pilot['level']*10 if pilot else 0)
                           - weapons*8-effects.get('evade_penalty',0)*10))
        toll = max(5,10+int(encounter.get('distance',1))*3-self.factions.get('pirates',0)*2)
        if 'pirate_codes' in self.faction_perks:
            toll=max(1,toll//2)
        return dict(escape_chance=escape,toll=toll,attack=1+weapons*2+effects.get('weapon_power',0),
                    round=int(encounter.get('round',0))+1)

    def _combat_defeat(self, encounter, damage, strength):
        ship,ship_id = self.ship,self.active_ship_id
        origin = encounter.get('origin',self.location)
        destination = ship.get('destination')
        # Use the established ship-loss/crew/VIP rules at zero hull.
        ship['condition']=1
        recovery = self.damage_ship(ship_id,1,origin)
        for key in ('flight_encounter','flight_encounters','arrival_at','departed_at','travel_seconds'):
            ship.pop(key,None)
        if not recovery['destroyed']:
            ship['condition']=10
            if ship.get('pursuit'):
                ship['pursuit'].update(progress=0,cooldown_until=time.time()+180)
            outcome='Ship disabled; rescue tug returned you to '+origin+' with 10 hull. Repair before taking another risk.'
        else:
            for module in self.module_inventory.values():
                if module.get('ship_id')==ship_id:
                    module.update(status='lost',ship_id=None)
            outcome='Ship lost in combat.'
        return dict(title=encounter['title'],outcome=outcome,strength_remaining=strength,
                    route_cleared=False,hazard_damage=damage,toll=0,destination=destination,
                    combat_pending=False,defeated=True,destroyed=recovery['destroyed'])

    def _repair_gate_contracts(self):
        """Every locked contract gate must retain an actionable quest."""
        home=self.galaxies.get('home',{}).get('ports',{})
        for name,site in home.items():
            gate=site.get('map_gate',{})
            if gate.get('kind')!='contract' or gate.get('unlocked'):
                continue
            key=gate.get('contract_id')
            if not key:
                key='repair-gate-'+name
                gate['contract_id']=key
            job=self.local_jobs.get(key)
            if job and job.get('status')=='delivered':
                gate['unlocked']=True
                continue
            if not job:
                destination=site.get('map_parent') or 'Haven'
                origin=home.get(destination,{}).get('map_parent') or 'Haven'
                if origin==destination:
                    origin='Kepler' if destination=='Haven' else 'Haven'
                self.local_jobs[key]=job=dict(id=key,kind='frontier_gate',
                    title='Open the '+name+' corridor',origin=origin,destination=destination,
                    good='ore',quantity=2,reward=200+int(site.get('map_depth',1))*40,status='open')
            if job.get('status') != 'open' or job.get('deadline',0) <= self.tick:
                job['deadline'] = self.tick+999_999_999
            job.update(kind='frontier_gate',status='open')
            gate['description']=f"Deliver {job['quantity']} {job['good']} to {job['destination']} · contract: {job['title']}."
            job['description']=f"Deliver {job['quantity']} {job['good']} to {job['destination']} to permanently open the approach to {name}. This quest does not expire."
