# Trade Net — Implementation Roadmap

For the current gameplay-first plan, including sector incidents, mission
chains, Haven upgrades, exploration, NPC captains, and **◇ simulated / ◉ real**
radio presentation, see the [single-player roadmap](SINGLE-PLAYER-ROADMAP.md).

## Milestone 0: Working repository and decisions

- [x] Establish vision and separation of game/radio layers.
- [x] Document economy, discovery, topology metrics and transport attrition.
- [x] Select direct Data2G integration over radio-arcade; record capability and ship-tier contract in `DATA2G-INTEGRATION.md`.
- [ ] Verify concrete installed Data2G host/KISS interfaces and frame-size limits before writing the live adapter.
- [ ] Choose implementation language and client stack. Suggested: Python engine for rapid integration, with a desktop/web-capable client later.
- [ ] Define explicit RF airtime budget and operating controls.

## Milestone 1: Solo playable vertical slice

- [x] Deterministic world seed and state schema (v1).
- [x] Seven-goods market with stock, production/consumption, bounded prices and ticks.
- [x] Individual starter ship, cargo hold, fuel, travel times and trade commands.
- [x] Five NPC starports and one abundant rare-resource specialization per galaxy.
- [ ] Full event-reducer replay and schema migration (save/load and command deduplication exist).
- [x] Minimal browser interface: galaxy, market, ship, contracts, comms log.
- [ ] Unit/property tests for nonnegative stock, conserved transfers and deterministic replay.

**Done when:** An offline player can buy, dispatch, sell, and earn enough to upgrade a ship, close/reopen the app, and get identical state.

## Milestone 2: Two-station simulated logistics

- [x] Two independent simulated worlds with distinct rare-resource economies, escrow, and one-process bilateral settlement.
- [ ] Actual distributed bilateral reconciliation across independent peers after partitions/restarts.
- [x] Persisted simulated store-and-forward queue, multipart reassembly, offline custody, and reverse-path application ACKs.
- [ ] Independently persisted peer-to-peer outbox/inbox, signed ACKs, remote acceptance and multi-authority settlement.
- [x] Seeded simulated fragment loss/retry and per-hop custody; delay is modeled through airtime ticks.
- [x] Local NPC contract escrow, cancellation, idempotent destination settlement.
- [x] AI-generated NPC freight contracts with compact, meaningful manifests.
- [x] Three information-weight classes with sourced second-hop ore/market data and no artificial padding.
- [x] Fixed five-minute UTC economic epochs with deterministic offline catch-up in the browser.
- [ ] Stateful autonomous AI that uses the same command pathway as players.

**Done when:** Both players can make a bilateral trade despite intermittent communication and repeated messages, without duplicate resources or inconsistent settlement.

## Milestone 3: Discovery and route map

- [x] Direct peers created after completed simulated transfer (not yet RF verified).
- [ ] Compact on-air neighbor digest and robust expiration; local capped reports work.
- [x] Distinguish reported from confirmed nodes and links.
- [x] Directional goodput, completion rate, sample count and observation sequence.
- [x] Simulated relay custody, destination settlement and retries (no signed receipts yet).
- [ ] Topology-sharing privacy toggle.

**Done when:** A learns about C from B, sees A–B measured and B–C reported, and can later validate C directly. Lost/stale links visibly decay.

## Milestone 4: RF adapter

- [x] Inspect Data2G host/KISS reference documentation and implement a guarded, single-frame probe/listen/send harness.
- [ ] Validate actual port behavior and payload budget with a live Data2G host/dummy load.
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
