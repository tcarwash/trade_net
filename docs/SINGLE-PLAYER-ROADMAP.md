# Trade Net — Living Galaxy & Single-Player Roadmap

This is the gameplay roadmap for turning Trade Net from a playable trading prototype
into a complete solo space-trading adventure. It complements the earlier
[technical roadmap](ROADMAP.md) and the [radio protocol](PROTOCOL.md).

## Design pillars

1. **A complete solo game.** Every important progression loop works with no radio,
   modem, another player, or network service. RF creates special opportunities;
   it is never required to finish the story or build a successful fleet.
2. **Events change the world.** Bulletins move real market prices, create real
   demand, and eventually alter access, route risk, and NPC behavior. Nothing is
   merely a decorative popup.
3. **A captain's decisions persist.** Contracts, discoveries, fleet, factions,
   relationships, facilities, and history survive save/load and offline ticks.
4. **Short missions grow into expeditions.** A five-minute trade can become a
   multistop relief convoy, rescue, investigation, or faction choice.
5. **Radio is special and honest.** Fictional traffic and real operator traffic
   never share an ambiguous affordance or accidentally cross the transmit path.

## Signal language and safety boundary

Use a small, consistent glyph legend—no paragraph-long warnings on every card.

| Glyph | Meaning | Behavior |
|---|---|---|
| **◇** amber diamond | Simulated/local dispatch or fictional station | Local game events only; never invokes Data2G |
| **◉** cyan target | Direct RF operator/contact | User explicitly chooses a Data2G transmit action |
| **○** outlined circle | Reported, unverified RF station | Intel only; no verified delivery action |
| **✦** star | Local discovery/anomaly | Ship expedition or local choice |

The legend should be visible once in Comms and available by tooltip on the map.
There is **no background simulated RF emission** and no automatic real-RF
transmission initiated by a fictional signal. A local fake contact must never
be inserted into `radio_contacts`, the RF resource ledger, the live contract
book, or the on-air neighbor digest. Keep local dispatch read-only in the web
state (`transport: local_simulation`, `transmit: false`) and process its jobs
through the normal local freight engine.

Any future practice-radio mode must use an explicit simulator transport,
separate namespace/ledger and unmistakably different visual icon. Actual
transmit controls stay operator-driven; existing listen/receipt behavior is
unchanged. Avoid granting rewards for meaningless RF volume or padding frames.

## Phase 1 — Sector incidents and dispatch (current slice)

**Player loop:** hear news → find a supplier → compare historic quotes → run
the shipment → collect payment before the incident resolves.

- [x] Deterministic sector bulletin per economy cycle, saved with game state.
- [x] Active incident modifies actual buy/sell prices at its affected market.
- [x] Incident generates a standard, fulfillable local freight contract.
- [x] News card and ◇ dispatch cards, separate from ◉ real-radio controls.
- [x] Incidents expire and offline catch-up skips stale unseen bulletins.
- [ ] Add more incident templates: strikes, pirate embargo, refugee flight,
      research grant, rescue alert and solar storm.
- [ ] Add regional demand indicators to price-memory comparisons and a clear
      before/after explanation in the sector-news dialog.
- [ ] Test market balance across varied seeds and long offline catch-up.

**Done when:** two seeds generate distinguishable crises, the same seed and
tick reproduce the same headline and price movement, a player can complete a
dispatch contract without Data2G, and expired effects are removed.

## Phase 2 — Multi-stage expeditions and encounters

- [x] First two authored three-leg expeditions: **The Long Night** (medical
      relief) and **Echoes of Eidolon** (relay restoration or salvage).
- [x] Three more branching three-leg faction expeditions: **Embers Under
      Cinder** (miners versus security), **The Quiet Archive** (science
      versus diplomacy), and **The Blackwake Accord** (pirates versus patrols).
- [x] Accept at Haven, secure actual purchased cargo, deliver it, make a
      consequential faction choice, and return to Haven for payout.
- [x] Saved progress, command replay protection, voluntary abandonment with
      cargo retained, and a soft quick-return bonus rather than offline failure.
- [x] Touch-friendly mission cards, waypoint progress, and stage/finish modals.
- [x] Nine port-specific, one-time discovery encounters with multiple outcomes,
      actual fuel/hull/cargo costs, credit and faction rewards, and salvage.
- [x] Discovery journal, dockside choice cards, and milestone dialogs with
      persistent outcomes and replay-safe commands.
- [x] Four recurring local encounter templates rotate among starports, with
      safe and riskier choices, real costs/rewards and expiry. Only the current
      incident is materialized on a long offline return.
- [ ] Add a typed mission state machine: offered → accepted → steps →
      completed/failed/abandoned, with reward escrow and idempotent steps.
      (The first expedition state machine is implemented; richer failure and
      escrow rules remain.)
- [ ] Expand to 12–20 encounter cards, including repeatable rare events and
      event chains (the first nine port-specific choices are implemented).
- [ ] Add chain templates: medical convoy, missing ship, rare-material hunt,
      diplomatic escort, investigation, supply rescue and urgent relay.
      (The first rescue and investigation storylines are playable.)
- [x] Show a compact mission journal with map waypoints and step progress.
- [ ] Avoid hard failure traps: players may decline, abandon, or recover from
      deadlines, ship loss and unavailable stock.

**Done when:** a three-stop relief mission survives save/reload and uses the
same physical cargo and travel commands as the economy.

## Phase 3 — Haven headquarters

- [x] Bounded Haven export warehouse capacity (60 units initially, +40 per
      warehouse level), with existing physical ship-to-base unloading.
- [x] Repair bay (three levels), export warehouse (three levels) and
      intelligence office (two levels), with a visible construction board.
- [x] Shipyard gantry (two levels), Cargo Exchange (two levels), and faction
      liaison (two levels), with clear Haven-only savings and progression perks.
- [x] Construction consumes credits and previously imported ore/medicine/food from
      the active ship. Haven-bought cargo cannot masquerade as imports.
- [x] The repair bay discounts repair bills; intelligence level one charts
      port names and scans corridor hazards, and level two increases encounter
      earnings without sending radio frames.
- [x] Cargo Exchange generates persistent multi-resource local requisitions,
      funded only by imported warehouse stock, with distinct ◇ local rewards;
      its levels also boost local freight pay for deliveries to Haven.
- [x] Shipyard discounts new ships bought at Haven; liaison accelerates
      trusted captain private-lot availability.
- [x] Responsive, interactive development-district overview reflects each
      facility's built and upgraded state and jumps to construction details.
- [ ] Add storage fees and operating costs, expedition center and radio
      observatory facilities.
- [ ] Add more mission types, freely arranged base customization, and services at
      higher facility levels.
- [ ] Create a bespoke illustrated base scene and extended management screen.

**Done when:** the player has compelling permanent goals beyond a bank balance.

## Phase 4 — Exploration sites and salvage

- [ ] Discoverable derelicts, gas-cloud pockets, ancient relays, asteroid mines
      and hidden settlements between starports.
- [x] Existing fog of war and scanner route intel now connect to nine
      persistent, optional encounter choices with real resource trade-offs.
- [x] Cargo salvage (ore, iridium, mycelium) from risky discovery choices.
- [x] An exploration log distinguishes open and resolved discovery sites and
      can plot courses back to unresolved sites.
- [ ] Independent between-port encounter locations, richer artifact stories,
      unique equipment and a ship-loss memorial.

**Done when:** scanning and visiting an uncharted location leads to a decision,
not just a discovery payout.

## Phase 5 — NPC captains and factions

- [x] Four recurring named captains with stable ships, trade specialties,
      deterministic routes and persistent relationship scores.
- [x] NPCs physically transfer bounded commodity quantities between local
      starports every six ticks; those changes affect real market pricing,
      while never touching radio contacts or issuing Data2G frames.
- [x] Three authored captain-specific faction expeditions with branching
      outcomes; choices persist and alter both standing and the captain's
      personal relationship toward the player.
- [x] Friendly captains offer a limited local buying discount on their
      commodity; hostile captains charge a surcharge at their current port.
- [x] Local map diamonds, traffic ticker, captain cards and contract-giver
      attribution help players plan around these moving opportunities.
- [x] Rival freight postings permit the player to beat an NPC captain to a
      delivery; unfulfilled postings are claimed by the rival after a deadline.
      Winning improves the named relationship and pays a real local contract.
- [x] Relationship expedition outcomes schedule a one-time follow-up freight
      opportunity after 12 economy ticks. Returning from a long absence
      activates it with a fresh deadline instead of silently losing it.
- [x] A trust-2 captain unlocks a limited private commodity lot at their
      current port, drawn from the actual market and renewed after 24 ticks.
      The lot is credit-paid, stock-limited and does not mint cargo.
- [x] Captains with trust-2 can be asked once per active sector dispatch for
      emergency help. Spending one relationship point increases the contract
      reward and grants four extra ticks. Hostile captains affect future
      commodity-matched dispatches with hazard premiums and tight deadlines.
- [x] Follow-up freight resolves commercially for the entire payout or as a
      reconciliation for half payment, +3 relationship and +2 faction standing.
- [x] At +3/-3 relationship, each captain unlocks a one-time authored alliance
      or feud story at a permanent rendezvous port. Choices spend physical
      cargo/credits, grant different permanent outcomes and survive reloads.
- [x] Four fleet-wide faction perks: Mara's trade charter expands private food
      lots and lowers food prices; Rin's foundry plating mitigates route damage;
      Lysa's survey uplink increases first-visit exploration rewards; Sable's
      passage codes halve pirate tolls.
- [x] A defied rival becomes a persistent nemesis: more frequent competing
      freight, shortened deadlines and higher bounty pay. A truce repairs the
      relationship without generating a nemesis.
- [ ] Multi-chapter faction dialogue, new equipment models and staffed bases,
      faction-specific embargoes and multiple authored finales.
- [ ] More rescuees and branching quest chains with special equipment and
      authored endings.

**Done when:** players recognize NPCs and see consequences of helping or
antagonizing them in subsequent encounters.

## Phase 6 — Fleet roles, crew and expedition planning

- [x] Multiple separately commanded ships with persistent holds, condition,
      destinations and upgrades; human-readable custom ship names.
- [x] Same-port ship-to-ship cargo transfers that preserve imported provenance.
- [x] Three deterministic rotating crew offers per starport, hiring fees,
      dockside reassignment and per-hull berth limits (two to four).
- [x] Four active specialist roles: pilot (fuel/speed), engineer (damage/repair),
      broker (local contract payouts) and signal officer (real-RF failure hull
      mitigation). Bounded skills and mission-driven XP persist across saves.
- [x] Signal officer experience requires a genuinely verified partner delivery;
      fictional ◇ contracts do not award radio skill or transmit frames.
- [ ] Escort, security, science and navigator specializations, crew side quests,
      retirement and unique recruit traits.
- [ ] Multi-leg expedition planner with estimated profit, fuel and risks.
- [ ] Opt-in automation of routine local routes. Player decisions interrupt
      automation for hazards, special cargo and encounters.
- [ ] Never automate actual RF transmissions without a separate reviewed
      operating policy and explicit operator controls.

**Done when:** a player can manage several ships without repetitive micromanagement.

## Phase 7 — Campaign, legacy and endgame

- [ ] Expand Frontier Signal into authored chapters that introduce other loops.
- [ ] Captain's Legacy: unique ports, discoveries, contracts, people rescued,
      faction milestones, meaningful radio contacts and lost ships.
- [ ] Achievement collection and expedition archive with no grind-only goals.
- [ ] Optional sandbox continuation after the main campaign.

**Done when:** a solo player has a satisfying story arc and enduring free-play.

## Phase 8 — Radio frontier

- [x] Optional read-only Hamlib rigctld frequency polling and persisted band
      passport (+60 credits once per newly observed band; no PTT or tuning).
- [x] Some contracts request a specific band; manual dispatch and automated
      recovery re-check the tuned frequency before sending their frames.
- [x] Persistent two-resource long-haul manifests that can be stocked at Haven
      across multiple sessions, reserved atomically, and settled on one ACK.
- [ ] Local-only practice contacts and simulated neighbor discovery behind a
      **◇** simulation adapter; keep them out of live federation state.
- [ ] Distinct **◉** verified contacts, **○** hearsay, RF signal metrics and
      explicit operator-approved transmit queue.
- [ ] Special cross-galaxy relief contracts and cooperative expeditions; no
      pay-to-win or dependence on a successful on-air session.
- [ ] Frame budgets, interference-safe retry policies, full receipts, link
      restoration, and identity/authentication before broad deployment.

### Store-and-forward, multi-hop freight (not yet implemented)

Current second-hop reports are **discovery intelligence**, not authority to
deliver to a remote galaxy through an intermediate station. Do not allow a
direct-only delivery to claim a multi-hop settlement.

- [ ] A route manifest names the origin, destination, ordered/interchangeable
      relay operators, every resource, a deadline window measured in days, and
      the destination's acceptance conditions.
- [ ] A relay must explicitly accept custody before a sender is cleared, and
      the receiver keeps a persistent inventory of in-transit manifests.
- [ ] Each hop issues a content-bound receipt with stable shipment ID and hop
      sequence. Replays cannot advance custody twice or duplicate inventory.
- [ ] The final destination issues the settlement receipt; only then is the
      agreed premium paid. Interrupted routes retain their last verified
      custodian and can be resumed days later.
- [ ] Expiry, refusal, return-to-sender and relay fees need explicit policy;
      operator-chosen windows must prevent unattended RF sends.
- [ ] Route hints from gossip are unverified until the next operator accepts
      the manifest. An observed neighbor is never a proxy for its permission.

**Done when:** the game stays fun offline and every real transmission is an
intentional, legible operator action.

## Cross-cutting quality gates

- Engine unit tests: deterministic seed/tick, persistence, no double payout,
  expired opportunities, nonnegative stocks and bounded credit effects.
- UI tests: keyboard, touch, dialog dismissal, narrow screens, reduced motion,
  connection loss/retry and fresh-save onboarding.
- Radio tests: fake signals cannot call modem APIs; live calls require the
  established Data2G pathway and normal operator permissions.
- Economy playtests: 10-minute onboarding, 1-hour midgame, and multi-day
  offline return with no dead ends.

The current solo vertical slice includes incidents, multi-stage expeditions,
one-time and repeating dockside encounters, six upgradable Haven facilities,
warehouse-backed local requisitions, recruitable ship crews and co-located
fleet cargo transfers,
recurring local NPC haulers, rival contracts and delayed faction follow-ups.
One-time alliance/feud arcs, four permanent fleet perks and named recurring
nemeses now provide lasting consequences. Their shipments, missions and market
offers remain entirely inside the saved game. Multi-chapter faction dialogue,
multi-hop freight custody and simulator radio contacts remain future milestones,
not implied by a reported link.
