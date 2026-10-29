# Trade Net — Implementation Roadmap

## Milestone 0: Working repository and decisions

- [x] Establish vision and separation of game/radio layers.
- [x] Document economy, discovery, topology metrics and transport attrition.
- [ ] Inspect actual `tcarwash/radio-arcade` library API once accessible; record version/commit and feasible frame sizes.
- [ ] Choose implementation language and client stack. Suggested: Python engine for rapid integration, with a desktop/web-capable client later.
- [ ] Define explicit RF airtime budget and operating controls.

## Milestone 1: Solo playable vertical slice

- [ ] Deterministic world seed and state schema.
- [ ] Four-goods market with stock, demand, bounded prices and ticks.
- [ ] Individual ship, cargo hold, fuel, travel times and trade commands.
- [ ] Three NPC starports with distinct economic specialization.
- [ ] Save/load/replay journal, schema migration and command deduplication.
- [ ] Minimal interface: galaxy, market, ship, orders, event log.
- [ ] Unit/property tests for nonnegative stock, conserved transfers and deterministic replay.

**Done when:** An offline player can buy, dispatch, sell, and earn enough to upgrade a ship, close/reopen the app, and get identical state.

## Milestone 2: Two-station simulated logistics

- [ ] Two independent worlds with distinct economies.
- [ ] Outbox/inbox, messages, ACKs, acceptance, settlement and expiry.
- [ ] Deterministic simulated transport with loss, delay, duplication, partition and reordering.
- [ ] Escrow/unreserve and idempotent application.
- [ ] Game contract requiring a multipart long transmission.
- [ ] Stateful AI that uses the same command pathway as players.

**Done when:** Both players can make a bilateral trade despite intermittent communication and repeated messages, without duplicate resources or inconsistent settlement.

## Milestone 3: Discovery and route map

- [ ] Direct peers created only after verified contact.
- [ ] Compact neighbor digest with hop limit, provenance and expiration.
- [ ] Distinguish reported from confirmed nodes and links.
- [ ] Directional goodput, completion rate, latency, confidence and age.
- [ ] Optional relay custody and destination ACK.
- [ ] Topology-sharing privacy toggle.

**Done when:** A learns about C from B, sees A–B measured and B–C reported, and can later validate C directly. Lost/stale links visibly decay.

## Milestone 4: RF adapter

- [ ] Verify radio-arcade APIs and supported frame payload budget.
- [ ] Implement capability-aware adapter and binary envelope.
- [ ] Integrate operator-controlled transmit queue, airtime estimate and duty limits.
- [ ] Cross-version compatibility tests, real modem loopback, then low-power controlled on-air trials.
- [ ] Review amateur identification, content transparency and automatic station-control requirements.

**Done when:** Two operators complete small order and long multipart mission via RF, and simulator results are not falsely mixed with observed RF metrics.

## Milestone 5: Richer game

- [ ] Starport upgrades, factories, shipyards, multiple ships and maintenance.
- [ ] Market bulletins, relays, delivery fees, insurance and priority scheduling.
- [ ] Exploration/procedural sectors and unique mission artifacts.
- [ ] Collectible achievements / optional PixelQSO cross-app event export.
- [ ] Robust AI traders, seasons, hosted galaxy handoff and optional federation research.

## First engineering tasks

1. Write a typed, versioned world-state schema and pure command reducer.
2. Build an event-journal replay test before the first UI.
3. Implement one trade and one ship move with conserved inventories and integer credit balances.
4. Add a seeded fake transport and two-world message test.
5. Verify the real radio-arcade API before designing binary framing.

## Non-goals for MVP

Global persistent MMO, distributed consensus, real-money trade, competitive tamper-proof leaderboards, encrypted on-air content, autonomous RF transmission, network-wide route flooding, realistic orbital physics, or a giant universe before the single-port loop is fun.
