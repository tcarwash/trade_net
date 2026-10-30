# Trade Net

*A local-first space trading game with optional amateur-radio logistics.*

Build a fleet, explore your own galaxy, buy low and sell high, and fulfill freight contracts. When you connect with another operator, their station can become a node in your trade network. Link quality, frame loss, and relay routes become part of the game instead of just transport details.

**Status:** playable solo browser prototype. Radio exchanges and the Data2G interface remain experimental. Local simulated dispatches never transmit, but the separate operator-controlled radio buttons **do send through Data2G** when configured and approved.

## Play locally

Requires **Python 3.10+**, with no third-party dependencies.

```sh
python -m tradenet.web --callsign AG7SU --seed 42
```

Open **http://127.0.0.1:8765**.

Optionally read your radio's frequency from Hamlib rigctld (usually TCP 4532):

```sh
python -m tradenet.web --callsign AG7SU --rigctld-host 127.0.0.1 --rigctld-port 4532
```

Trade Net only sends rigctld's read-frequency command; it cannot retune or key your rig. The header displays the current frequency and band. Your **band passport** rewards a first observation of each band with 60 credits, once per save, without transmitting. Some real-radio contracts ask for a specific band; these are checked against rigctld again before manual send and retry. Band classification is for gameplay, not an authorization to transmit.

On a phone, the command deck becomes a full-width layout with a thumb-friendly bottom navigation bar, swipeable sector chart, and individual commodity price cards. The highlighted objective at the top points to your next useful action; when you've met the requirements, it can complete a chapter or turn in cargo/passengers directly. The contract board filters freight, VIP, and radio deliveries. Actual local flight progress is visible both on the chart and on a progress bar; orders are automatically saved by the local game server. Mobile home-screen icons and an app manifest are included for browsers that support adding local web apps to the home screen. Access from another device requires making the server reachable from that device; installation support depends on a trusted origin (typically HTTPS or localhost). Offline play is **not** supported: the interface requires its game server.

The **optional guided run** teaches the first real freight loop—review a contract, load its cargo, plot a flight, and collect the delivery payment. It remembers your current step in the browser tab and advances when you actually complete each action. Milestone dialogs celebrate arrivals, newly charted ports, story chapters, VIP and freight payouts, new ships, and radio acknowledgments; danger and lost-radio outcomes receive their own clear warnings. Existing saved-game history is not replayed as a wall of pop-ups on login.

1. Open **Contracts** and choose a local freight job. The board gives a delivery destination, quantity, deadline, and guaranteed payout.
2. Buy the requested goods (the suggested pickup is a route hint, not a restriction), select the destination on the map, and dispatch your ship.
3. Deliver the cargo from the contract board when docked, or sell speculative cargo at higher-demand markets.
4. Buy more ships, upgrade their holds or modem class, and expand your routes.

**Your export base is Haven.** To fulfill a real partner's radio contract, buy the requested goods at another starport, carry them back to Haven aboard a ship, and use **Fleet → Haven headquarters → Unload** (also available in Comms) to put them in the export warehouse. Then prepare the partner contract and transmit from Haven. Buying goods at Haven itself does not create eligible export cargo; its ordinary market stock is separate from your warehouse. Failed/rejected deliveries return reserved goods to that warehouse for a retry.

Some radio contracts are **long-haul manifests** requesting two resource types and larger quantities. Stockpile those goods at Haven over multiple game sessions, then reserve the entire manifest and make a single radio delivery when the next contact is available. Supplies remain safely in the export warehouse between sessions; a partial manifest cannot be transmitted as a completed delivery. Radio contract offers do not currently expire while you gather goods.

**The listening station stays at Haven even when the fleet does not.** The receiver can accept direct, correctly addressed Data2G contact and freight frames, acknowledge them and credit incoming cargo to Haven while every vessel is traveling or docked elsewhere. A ship at Haven is required only for *outgoing cargo expeditions* and their reserved exports, not for listening. A compact **◉ station beacon** can advertise your callsign, one galaxy-wide resource abundance and optionally one open station contract in roughly 11–20 bytes (15 bytes for `AG7SU` plus a contract). Previewing shows the binary packet locally without transmission. **Broadcast once** deliberately sends one packet via the currently selected *live* Data2G mode; there is no scheduled auto-transmit. A received beacon is an unverified advertisement, not a verified contact or a credit award. This is a Trade Net packet inspired by WSPR's compact-beacon idea, **not an interoperable WSPR signal**. The UI uses ◇ for local/simulated activity and ◉ for real-radio controls and received signals.

The economy advances in shared five-minute UTC ticks, including when you're away. Each ship has independent cargo, fuel, condition, location, and upgrades. Optional **hard mode** offers better selling prices but permanently destroys ships reduced to zero condition.

**Fleet & crew operations** are in Fleet command. Name your vessels, select any ship even while another is traveling, and transfer goods between two ships docked at the same starport; imported-cargo provenance remains attached during transfers. Local starports offer three rotating crew candidates every 144 economy ticks. Hire a specialist for a one-time fee, then assign or reassign them when ships meet at a port. Each ship has two to four crew berths based on its tier and can carry one of each role:

- **Pilot:** saves one fuel per level on local flights; experienced pilots shorten journey time.
- **Engineer:** reduces route damage and discounts repairs.
- **Broker:** increases payouts for ◇ local freight deliveries, stacking with the Haven Cargo Exchange.
- **Signal officer:** prevents some hull damage after a genuinely failed radio transfer, and gains experience only from verified ◉ partner-delivery acknowledgments.

Crew accumulate experience from relevant missions and improve up to level three. They persist in saves, and survive the loss of a ship in hard mode as unassigned crew back at its origin. Recruiting, transfers, and other management controls are strictly local game actions; none transmits.

**Automated local fleet logistics:** Fleet → Fleet logistics lets you commission a specific docked, empty ship for up to 20 repeat runs. **Merchant trade** buys from one home-galaxy port and sells at another for local profit. **Stock Haven** buys outside Haven, carries physical imports home, and unloads them into the export warehouse for later radio deliveries or base requisitions. **Dispatch an idle vessel** assigns an available ship without switching your active command. Each ship retains its own run count, costs, margins or import totals; it spends real credits, fuel and hull condition and earns normal flight experience. Discoveries, blocked approaches, gas, pirates, rare cargo, missing supplies, inadequate fuel and warehouse capacity pause the operation for a decision. Risky legs require separate authorization. Ships with no assignment and an empty hold gather at Haven by themselves when the corridor is clear; the selected vessel, passenger missions and loaded ships are never commandeered. The ◇ automation controls never call the radio modem or queue intergalactic traffic: ◉ partner contacts and shipments remain operator-driven.

**Standing fleet orders:** Fleet → Fleet dispatch doctrine turns one-off supply runs into a persistent procurement plan. Choose a resource, a starport **you have actually visited**, a target quantity in Haven's export warehouse, and units to collect per run. Spare idle ships begin local supply runs as needed; quantities already in transit count toward the target. Set a minimum **fleet credit reserve** so automatic purchases and optional maintenance never spend your last credits. The planner pauses for danger, blocked routes, rare freight, missing stock, and insufficient funds just like manual fleet automation. A completed order stays configured and replenishes the warehouse when stock is subsequently consumed. Set a target to zero to remove it. With only the starter ship, buy another vessel before expecting unattended dispatch—the selected ship is never commandeered.

**Vessel policies and captains:** Every ship can independently opt out of automatic gathering at Haven and opt into automatic servicing while docked at Haven. Choose hull condition and fuel percentage thresholds; repairs and refueling use actual credits and Haven fuel-market stock, respecting the fleet-wide credit reserve. Designate an *already assigned* crew specialist as captain of a docked vessel. They retain their pilot, engineering, broker or signal role, gain command XP from successful automated runs and eventually reduce their own vessel's repair costs. Assigning a captain does not grant any unattended radio transmission authority. Both policies and captain progress persist across saves.

The local galaxy now contains **ten starports** with distinct production specializations and roles. First visits reveal their character and award 90 exploration credits per new destination. Older five-port saves gain the new locations while preserving existing market stock. The market remembers the lowest buy and highest sell quote you have actually observed for each commodity while docked. The market-intel column shows the remembered port and its price difference from your current quote; those quotes are historical, not guaranteed live offers.

Space isn't empty: the asteroid field circles the central sector, blocking direct arrivals at one starport for 90 seconds before moving to the next. Ionized gas clouds damage hulls, while pirate interceptions cause damage and a capped credit toll. The route preview warns you about conditions before you launch, and better ship tiers mitigate hazard damage. Route hazards are deterministic for a given route and economy interval, not rerolled randomly on every button press.

The **Contracts** board also offers VIP passenger missions: navigate to the pickup port, board a diplomat, medic, survey captain, or trade delegate on a specific ship, and reach the requested destination for a bonus. Each ship carries at most one VIP; you can cancel a passenger mission without destroying your ship. Freight, VIP transport, exploration, and radio logistics all share the same fleet and credits.

**Frontier Dispatch** now adds a deterministic sector incident every eight economy ticks. Each incident affects the actual buy/sell prices of one commodity at a starport and issues a time-limited local relief or supply contract. Follow the news bulletin or the ◇ dispatch signal in Comms to find the job. These fictional dispatch signals are local game activity only; **◉** marks real radio contacts and their operator-controlled Data2G actions. The two ledgers are separate, so browsing or fulfilling a dispatch job never transmits RF.

**Frontier expeditions** are longer single-player missions on the Contracts screen. Start at Haven, source the requested goods through ordinary markets, fly to the mission waypoint, make a choice that changes faction reputation and payout, then return to headquarters. The first two expeditions are *The Long Night* and *Echoes of Eidolon*. Mission progress persists in saves; you may abandon and retry without losing cargo, and returning late only forfeits the punctuality bonus. No radio or online contact is required.

Three more expeditions add recurring characters and faction choices: *Embers Under Cinder* puts miner rescue against station security, *The Quiet Archive* weighs science against frontier clinics, and *The Blackwake Accord* pits a smuggler's truce against patrol enforcement. Your decisions change named captains' relationships with you as well as faction standing. All five expeditions are available on a new or migrated save, and completed missions stay completed.

**Local NPC traffic** makes the economy less static. Four named captains—Mara Venn, Rin Kestrel, Dr. Lysa Quell, and Sable Rook—carry finite cargo along their own two-port routes. Their shipments actually remove stock at the originating port and add it at the destination, so profitable prices can change while you are elsewhere. The Flight deck shows ◇ markers for these local simulated ships, a captain roster, and recent shipment reports. You can plot a course to meet a captain. Help a captain in their expedition and their specialty commodity is discounted while they are docked at that port (2% per relationship point); antagonize them and you pay a corresponding surcharge. NPC traffic is bounded on long offline catch-up and never creates an RF transmission or a fake verified contact.

**Rival freight** adds an optional race against those captains. When a ◇ rival posting appears on the Contracts board, buy its goods and deliver before the named NPC claims the shipment. Winning pays the posted credits and improves your relationship; waiting beyond its deadline lets the captain claim it. These offers do not displace the normal three-job freight board. Completing a captain's faction expedition also schedules a personal follow-up delivery about an in-game hour later. A friendly favor has a longer delivery window; a rival challenge pays more for more cargo under a tighter deadline. If you were away for days, a pending follow-up becomes available when you return, with a fresh deadline rather than an automatic failure.

**Captain consequences** deepen those relationships. At relationship +2, a captain offers a private lot of their specialty resource from their actual starport stock every 24 economy ticks; buy it when you meet them, with a separate cooldown per captain. Trusted captains can also spend a point of goodwill to extend an active local sector dispatch by four ticks and improve its payout by 20%. A hostile captain instead puts extra pressure on future emergency dispatches involving their commodity, increasing both urgency and risk pay. Follow-up contracts have two resolutions: collect full freight pay and gain +1 relationship, or take half the credits in exchange for +3 relationship and +2 of that captain's faction standing. These are all ◇ local gameplay choices; they do not send Data2G frames or generate radio contacts.

**Faction storylines** unlock when a named captain reaches relationship +3 (alliance) or -3 (feud). Each captain leaves a one-time, persistent decision at a fixed rendezvous port, so you can return later without chasing their moving ship. Build an alliance by importing two units of their specialty cargo and paying 160 credits to unlock a fleet-wide perk, or take an immediate cash advance and forgo the perk. In a feud, deliver cargo and pay to reconcile, or take a payout and make that captain a lasting nemesis with more frequent, tighter rival freight races. Mara's trade charter expands her private lots to five units and lowers food buying costs; Rin's reinforced plating reduces gas and pirate damage; Lysa's survey uplink increases first-visit exploration rewards; Sable's pirate codes cut pirate tolls in half. The Captain Storylines board shows unresolved choices, requirements and permanent results. All consequences are saved locally and remain distinct from ◉ radio operations.

**Passing local encounters** give the galaxy something to do after its one-time discoveries. A rotating opportunity appears at a different port every 12 economy ticks, offering decisions such as aiding stranded passengers, recovering a survey drone, salvaging cargo, or joining a patrol. Visit the port, choose an outcome on the Flight deck, and pay its actual fuel, cargo or hull cost. The Contracts screen tracks the currently available locations and deadlines. Repeatable encounters and ◇ NPC postings are **local simulation only**; the distinct ◉ Data2G actions in Comms remain the only operator-driven transmissions.

**Discovery encounters** now give you a decision when you first reach any of the nine starports beyond Haven. You might tow stranded crew using fuel, bring medical supplies to an isolated lab, risk hull damage to salvage rare materials, or file a safer survey report for a smaller reward. The Flight deck shows the available choices with their costs and payouts; the Contracts screen tracks open and resolved discoveries and can plot a course back to an unfinished site. Each encounter can only pay out once, and its outcome and faction reputation persist after loading a save.

**Haven headquarters construction** is in the Fleet screen. The interactive development district shows your growing base: choose any building to jump to its construction controls. Build permanent advantages by importing ore, medicine, or food from another starport and spending that cargo plus credits on one of six facilities:

- **Repair bay:** 15% cheaper hull repairs per level (three levels).
- **Export warehouse:** starts at 60 units and gains 40 storage units per level (three levels).
- **Intelligence office:** reveals port identities and route hazards at level one; adds 25% to discovery encounter credit payouts at level two.
- **Shipyard gantry:** 10% off new ship purchases per level while docked at Haven (two levels).
- **Cargo exchange:** posts week-long, multi-resource **◇ local** Haven requisitions fulfilled from imported warehouse stock (two resources at level one, three at level two). Each level also increases the payout for ordinary local freight delivered to Haven by 10% (two levels).
- **Faction liaison:** shortens trusted captains' private-lot restock cooldown from 24 to 20 and then 16 economy ticks (two levels).

Construction materials must still be **aboard the active ship** when you upgrade, not already unloaded into the export warehouse. Cargo Exchange requisitions work the opposite way: unload your imports into the warehouse, then fulfill the full manifest at Haven for credits and Traders reputation. These local requisitions never transmit, and the same warehouse stock can instead be reserved for real **◉ radio** partner contracts. Upgrades and requisition progress persist between sessions; all six facilities work without radio access.

### Frontier campaign, fog of war, and outfitting

- **Fog of war:** unexplored ports appear as unidentified signals, with their name and economic role concealed until visited. A ship-mounted scanner can identify distant ports and preview corridor hazards in advance. Known market prices are still only the quotes you actually observed while docked.
- **Frontier Signal campaign:** a four-chapter introductory quest takes you from Kepler's signal to Aurora's medical relief, Eidolon's silent observatory, and a final return to Haven. Chapters require you to be at the objective location; the clinic also consumes two medicine from the active ship.
- **Discovery sites:** first visits reveal one-time supply caches, navigation beacons, or trade outposts and pay additional exploration rewards, alongside the new choose-your-response encounters. Discovery and encounter rewards cannot be repeated by revisiting a port.
- **Faction reputation:** traders improve sell prices, explorers increase discovery earnings, diplomats improve VIP rewards, and security experience reduces fighting damage. Miners and scientists earn standing through relevant commodities and improve ore/medicine buying prices; a pirate-underworld reputation reduces future tolls. Reputation persists with the save.
- **Ship outfitting:** scanner (220 cr), shield (350 cr), navigator (420 cr), and defense system (380 cr) are purchased separately for individual ships. Shields reduce gas damage, navigators can bypass asteroid blockades for extra fuel, and defense systems improve combat outcomes.
- **Pirate decisions:** choose **pay**, **evade**, or **fight** before launching. Paying costs credits, evading burns additional fuel, and fighting risks greater hull damage without defenses while building security reputation. All choices are applied by the economic engine, with no real RF traffic generated by these local encounters.

The **Debug** toggle exposes the radio/network simulator and two-galaxy exchange laboratory. The comms journal stays visible during normal play.

### Command-line engine

```sh
python -m tradenet --seed 42 --save my-galaxy.json
```

The CLI is a smaller engine preview with commands such as `status`, `market`, `buy food 3`, `travel Kepler`, and `wait 3`.

### Run tests

```sh
python -m unittest discover -s tests -v
```

## How radio trading works

- **Personal galaxies:** each player has an independently seeded economy and an abundant rare resource.
- **Discovered network:** direct contacts appear as measured links; second-hop advertisements are marked as reported, not verified.
- **Real freight:** after direct first contact, a station can fulfill the partner's single- or multi-resource request, with persisted staging, limited retries and application receipts. The ship-on-link animation reflects frame progress.
- **Multi-hop discovery is not multi-hop delivery:** stations relay information about other stations, but cargo custody and forwarding through an intermediary are not implemented. Only direct, acknowledged deliveries settle a contract; see the [single-player roadmap](docs/SINGLE-PLAYER-ROADMAP.md) for the relay-custody design.
- **Three useful payload classes:** **Light** carries transaction data; **Medium** adds second-hop ore information; **Heavy** adds second-hop market prices. No synthetic padding is added.
- **Ship tiers:** Scout (500 Hz), Courier (1,200 Hz), and Express (2,400 Hz) have different simulated transmission capabilities. The chosen mission ship determines its tier.
- **Mission risk:** an outbound message that expires before delivery damages its assigned ship, which returns to its origin. Hard mode can make that loss permanent. Ambiguous transactions remain pending reconciliation.
- **Premium RF freight:** a verified partner delivery pays `100 + 2 × base value of requested cargo` credits, capped at 1,500 for single-resource freight and 3,000 for long-haul manifests. The payout is calculated from locally staged goods after a matching application receipt—not from a peer's untrusted credit claim. Local freight remains a lower-stakes path to earning capital and outfitting ships.

The long-term goal is for actual on-air transfer success, throughput, and network topology to shape the gameplay. Today's partner exchange uses real Data2G messages and per-station ledgers, while the separate ◇ sector dispatch is simulated. Cryptographic RF identity and multi-hop custody are not yet implemented.

## Documentation

| Guide | Contents |
|---|---|
| [Game design](docs/GAME-DESIGN.md) | World, economy, and progression ideas |
| [Roadmap](docs/ROADMAP.md) | Implemented milestones and next steps |
| [Single-player roadmap](docs/SINGLE-PLAYER-ROADMAP.md) | Living galaxy, incident missions, Haven upgrades, NPCs, and radio/simulator boundaries |
| [Protocol](docs/PROTOCOL.md) | Message, receipt, and routing design |
| [Traffic classes & time](docs/TRAFFIC-CLASSES-AND-TIME.md) | Useful payload classes and UTC epochs |
| [Data2G integration](docs/DATA2G-INTEGRATION.md) | Planned direct modem integration |
| [On-air testing](docs/ON-AIR-TESTING.md) | Guarded experimental testing workflow |

Trade Net is related to [PixelQSO](https://github.com/tcarwash/pixelqso) and [radio-arcade](https://github.com/tcarwash/radio-arcade), but remains a standalone game. Real RF transmission requires explicit operator approval, appropriate station identification, and regulatory review. There is no real-money economy or incentive to send meaningless traffic.

---

*In memory of Sir Patrick Stewart (1940–2026).*

> “It is possible to commit no mistakes and still lose. That is not weakness; that is life.”
>
> — Jean-Luc Picard, *Star Trek: The Next Generation* ([StarTrek.com](https://www.startrek.com/get-to-know))
