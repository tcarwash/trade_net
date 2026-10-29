# Trade Net

**Working title; project name is not final.**

Trade Net is a mostly-solo space trading and logistics game in which real amateur-radio data exchanges discover other players' starports, create trade routes, and carry asynchronous trade orders. It is also a recreational practice environment for message priority, acknowledgments, custody transfer, store-and-forward routing, and emergency-traffic-style logistics.

The fictional economy remains playable locally. Radio is an optional, meaningful multiplayer layer—not a requirement to start playing.

## Core promise

- **Your own galaxy:** build starports, operate ships, and trade with simulated ports without waiting for another operator.
- **Discover people by trading:** a verified on-air interaction creates or updates a real-station node in your galaxy.
- **Learn their neighbors:** compact, timestamped next-hop advertisements reveal a *reported* network, distinct from links you directly measured.
- **Earn a route, don't assume one:** edge quality summarizes observed goodput, completion ratio, age, and sample confidence.
- **Packets matter:** retries, frame loss, finite airtime, priority traffic, and relay custody are logistical costs. Inventory cannot be minted or silently erased by duplicate or lost frames.
- **Occasional long transmissions:** small control messages dominate, but some missions deliberately require multi-frame, high-volume transfers.

## Documents

- [Game design](docs/GAME-DESIGN.md): economy, ships, missions, discovery, transport attrition, and solo-to-RF progression.
- [Protocol and architecture](docs/PROTOCOL.md): deterministic ledger, message states, routing advertisements, receipts, reliability metrics, and transport adapter boundaries.
- [Implementation plan](docs/ROADMAP.md): milestones, tests, and first playable vertical slice.

## Intended relationship to existing projects

- **PixelQSO:** independent card-collection gamification and verified-transfer achievements; share ideas and, eventually, a generic evidence/event contract rather than depend on its UI.
- **radio-arcade:** intended RF transport integration. The adapter API will be determined from the actual library; no concrete API is assumed yet.
- **Data2G:** possible lower-level modem/host behind an adapter; game rules must not depend on a particular modem.

## Status

Design scaffolding only. There is no implemented engine, radio adapter, playable client, or RF protocol here yet.

## Design guardrails

Local-first; explicitly permissioned transmissions; inspectable/unobscured game messages; no real-money economy; no reward for raw spam traffic; duplicate-safe transactions; bounded packet/airtime budgets; versioned, forwards-compatible messages; honest separation of measured and reported data.

Amateur-radio regulatory compliance needs jurisdiction-specific review before real on-air use.
