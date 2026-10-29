# Trade Net — Game Design (Draft)

## Player fantasy

You are the operator of a remote frontier starport. Your home galaxy contains AI markets, production chains, contracts, ships, upgrades, and exploration. When you communicate with another radio operator, their starport becomes a new point on the map. Trading reveals their advertised neighbors and eventually a living, imperfect network of human-operated trade corridors.

The real RF network is the game's **information and logistics layer**, not the fictional spatial geometry. A station 500 km away can be a close fictional neighbor; ship travel time depends on the game map, while order/manifest delivery time depends on actual RF.

## Three intertwined loops

### Solo economy (always available)
1. Acquire resources from local producers and NPC starports.
2. Build infrastructure: cargo storage, refineries, shipyards, comms offices.
3. Purchase, fit, fuel, maintain and dispatch individual ships.
4. Accept demand-driven contracts, diversify routes, and expand the galaxy.
5. Advance time using bounded, deterministic market ticks, including offline catch-up caps.

### Social discovery
1. Exchange a valid invitation/trade with another station.
2. Add a **directly observed** starport node, with callsign, optional nickname, contact time, and provenance.
3. Exchange a small, capped adjacency digest: top next hops, link statistics, timestamps, sequence, TTL.
4. Add reported neighbors as **unconfirmed** nodes/edges, distinguished visually from direct links.
5. Direct contact upgrades a node/edge to measured status. Reports decay and expire without becoming asserted facts.

### Real logistics
1. Create a job: trade order, market bulletin, courier parcel, survey, or emergency-style priority exercise.
2. Choose recipient, priority, size, due time, and optional relay route.
3. Reserve game resources in a durable outbox and transmit fragments when the operator permits.
4. Recipients acknowledge integrity and, separately, application acceptance.
5. A single authority per galaxy settles inventory-affecting transactions; courier stations may forward messages without owning goods.

## Galaxy map

Nodes:
- Home port: authoritative local game state.
- NPC port: simulated local economic actor.
- Direct RF peer: confirmed communication, observed link metrics.
- Reported RF peer: learned through an adjacency advertisement, no independent verification.
- Stale peer: historical, whose observed metrics have aged out.

Edges:
- **Observed**: successful transfers with actual direction and sample timestamps.
- **Reported**: neighbor says it can contact another neighbor; show reporter and age.
- **Route**: chosen multi-hop message path, never misrepresented as a direct path.

Edge width represents an exponentially smoothed **application goodput** (verified unique bytes divided by elapsed transfer time including retries); edge color represents completion ratio and data freshness; opacity or a confidence mark represents sample count. Show numerical goodput in bytes/s, successful/attempted transfers, retry overhead, and last observation on hover. Track A→B and B→A separately. Never use a single raw SNR metric as the whole link-strength claim.

For short transfers, fixed overhead dominates: show both goodput and median setup latency. Use bounded sample windows (e.g. most recent 20 completed/failed sessions, configurable) and a min-sample confidence warning. Exclude synthetic traffic from live RF stats. Offer local opt-out of topology sharing.

## Transport attrition, with explicit integrity

Proposed model: a shipment is a **manifest and game contract**, not physical goods teleported by a decoded frame. RF losses cause:
- **Airtime/fuel-equivalent courier cost:** every attempt consumes a configurable, modest in-game communication budget or operational time.
- **Delay and deadline risk:** retries, partial reception and store-and-forward handoffs may miss a market window.
- **Wear on fictional courier equipment:** a bounded simulation cost on attempts, not retroactive inventory corruption.
- **Insurance and priority choices:** insure a valuable order against deadline failure; or pay extra for expedited handling.

No randomized loss of *accepted inventory* from a packet checksum failure. A partial message stays incomplete; duplicate frames only fill holes; an expired order releases escrow under host rules. A mission that asks for a large archive can deliberately require 10–100+ frames and award completion only after integrity verification. Low-bandwidth HF makes compression, FEC, packet sizing, and relay planning meaningful, while rewarding useful delivery instead of repeated bytes.

## Mission examples

| Contract | Traffic shape | Skill taught |
| --- | --- | --- |
| Medical manifest | Tiny priority order, ACK, settlement | Clear addressing and priority |
| Relay rescue | Store and forward a third-party parcel | Custody and routing |
| Star chart survey | Long, segmented dataset | Fragment recovery and integrity |
| Blackout market | Work from stale bulletin, later reconcile | Delayed information |
| Convoy dispatch | Several short sequenced orders | Ordering and duplicate suppression |
| Lost colony | Discover a peer through a next-hop digest | Network reconnaissance |
| Supply chain | Multiple settlements across NPC and peer markets | Planning and accounting |

Emergency-traffic-inspired missions remain fictional and clearly labeled; the game must not interfere with or masquerade as real emergency traffic. A prominent operator pause/stop control and a priority policy favor real-world operating requirements.

## Economy

Begin with 4 goods: food, ore, fuel, medicine. Each port has production, consumption, stock and treasury. Price follows bounded inventory pressure around a base price; publish price revision and expiry. The simulation uses fixed integer units, deterministic tick order, and no floating-point ledger balances. Avoid exploitable buy/sell oscillation: transaction fees/spreads, stock constraints, and bounded price movement.

Ships have hull ID, cargo capacity, speed, range, fuel tank, condition and owner. Only one starter ship is needed for MVP, but the schema should allow fleets, maintenance, construction, fitting and multiple simultaneous routes. Starport structures unlock storage, manufacturing, repair and dispatch slots.

## Persistence and worlds

Each player starts an independent galaxy with a stable world ID, seed, rules version, and local authority. Optional multiplayer sessions can share an explicitly hosted world with one authoritative ledger. Cross-galaxy trade is initially **message exchange with bilateral game contracts**, not globally synchronized credits. Each side settles its own economy against signed/recorded contract receipts; if a peer disappears, escrow expires by published rules. Do not assume federation or double-spend resistance across unrelated worlds.

An AI trader can trade through the same commands as a human, with deterministic decision budgets and visibility limits. NPCs cannot forge RF evidence or unlock human-contact achievements.

## UI concept

Main views: Galaxy Map, Market, Fleet, Starport, Contracts, Comms, Ledger.

The **Comms** page is the central differentiator: outbox/inbox, custody queue, received fragments, pending ACKs, selected route, airtime estimate, transport health, and priority. The Galaxy Map emphasizes discovered nodes and direct-versus-reported edges; players can select a node to see markets, latest contact, observed throughput and advertised next hops.

## Progression

Reward unique useful tasks: first verified peer trade, first completed relay, first long-form integrity transfer, five distinct ports, first delayed settlement, and reliable service under constraints. Repeat deliveries can earn game credits as contracts demand, but do not endlessly award global XP by raw bytes or transmission count.

## Open questions

- In offline solo mode, should human peer nodes be visible as historical landmarks after disconnect? Recommendation: yes.
- Should the fictional market support market speculation/shorting? Defer.
- Should relay operators charge in-game fees? Yes, small capped fees after successful destination receipt.
- Should the game simulate station-to-station quality if radio is disconnected? Yes, but visibly label it simulation and keep stats separate.
- Should players be able to export/import galaxies? Yes, versioned save bundles with identity and replay protection.
