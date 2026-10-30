# Trade Net

**Working title; project name is not final.**

Trade Net is a mostly-solo space trading and logistics game in which real amateur-radio data exchanges discover other players' starports, create trade routes, and carry asynchronous trade orders. It is also a recreational practice environment for message priority, acknowledgments, custody transfer, store-and-forward routing, and emergency-traffic-style logistics.

The fictional economy remains playable locally. Radio is an optional, meaningful multiplayer layer—not a requirement to start playing.

## Core promise

The browser's normal view focuses on flying between planets, trading cargo,
fulfilling contracts, and watching radio freight progress across discovered
station links. A ship marker identifies the current planet; dispatching it
briefly animates departure and arrival. Queued radio freight draws a ship on
the active link, advancing only as payload frames are successfully received
(lost frames and retries delay it). The comms journal remains visible, while
protocol simulators and diagnostics are tucked behind **Debug**. The preview
still simulates radio; it does not key a transmitter.

The browser playability pass places **Map + Market** first, followed by Fleet,
Comms, and Contracts. First-run guidance gives the basic trading loop; clicking
a planet chooses the destination, and a route quote shows fuel, travel ticks,
and real-time minutes. Market rows can be selected directly, and the quote
shows cargo, cost, and best known sale price. Contract cards show missing
cargo and link to the relevant market selection. Inputs retain their values
when the 30-second state refresh runs; unavailable actions are disabled, with
human-readable success/error messages above the game. Debug-only mechanics
remain available with the toggle.

### Owned fleet and mission risk

Ships are individually purchased: Scout (350 credits / 500 Hz), Courier
(900 / 1200 Hz), and Express (1800 / 2400 Hz). Each retains its own location,
cargo, fuel, condition, and upgrades. Choose the active ship in Fleet dispatch;
radio exchange missions also select a particular available ship, whose modem
tier controls the simulated frame budget and supported bandwidth. The older
"Buy faster ship" control upgrades an existing selected vessel.

A queued radio shipment assigns the chosen vessel to that mission until an
end-to-end ACK arrives. If the *outbound payload expires before delivery*, the
ship is damaged and returned to its departure port; escrow stays pending
reconciliation to avoid double-spending after a possible delayed receipt.
Individual frame loss is retried and does not itself cause damage. In optional,
irreversible hard mode, ships reaching zero condition are destroyed; hard mode
also raises NPC sell proceeds by approximately 15%. Normal mode permits repair
of ships at zero condition. Ship loss never silently mints replacement cargo.

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
- **Data2G:** intended direct RF host integration through its supported KISS/host interfaces. Game rules remain transport-independent.
- **radio-arcade:** a related project, but not the planned transport dependency for Trade Net.

## Status

An initial **solo Python engine and interactive CLI** are implemented. There is no radio adapter, graphical client, or on-air protocol yet.

### Try the prototype

Requires Python 3.10+; no third-party packages:

```sh
python -m tradenet --seed 42 --save my-galaxy.json
python -m unittest discover -s tests -v
```

Try `status`, `market`, `buy food 3`, `travel Kepler`, `wait 3`, and `sell food 3`. Each seed deterministically chooses an abundant rare resource (`aether`, `iridium`, or `mycelium`). Commands are durably journaled and deduplicated by ID. This is an intentionally small backend preview, not yet a complete game.

### Graphical local preview

```sh
python -m tradenet.web --callsign AG7SU --seed 42
# Open http://127.0.0.1:8765
```

This dependency-free browser UI shows the economy, ship controls, and a galaxy map. The radio simulator breaks payloads into 64-byte frames, injects configurable loss, retries incomplete transfers, measures verified goodput, and discovers the destination plus its advertised next hops. Direct/observed versus reported/unverified links are distinct. **It never transmits RF.** Simulation history is saved next to the galaxy file in `galaxy.network.json`.

### AI contracts and simulated couriers

The browser also includes an AI demand board. Each seeded galaxy gets five stable NPC shipping contracts. Purchase the listed cargo at a market, **reserve** it for a contract, then **dispatch** it directly or through a comma-separated sequence of simulated courier callsigns. Each click advances one hop: frame losses may require another attempt while the parcel stays with its current custodian. Every transfer consumes simulated time; the deadline and payout matter. Destination settlement is idempotent and produces the credit reward once. Reserved-but-undispatched cargo can be cancelled through the engine API.

These are **local NPC authority contracts**, not cross-galaxy synchronized trades. The real-radio adapter, independent remote ledgers, negotiated contracts, signed custody receipts, and relay fee payments remain future work. No on-air transmission is initiated by this UI.

### Two-galaxy exchange lab

The preview now has a separate **Intergalactic Exchange Laboratory**. It creates two seeded galaxies with *different* abundant rare resources and a starter export offer. Click **Reserve both sides**, **Forward / retry**, then **Settle receipt**. Optionally add a relay callsign and increase frame loss; each click advances a single custody hop, so a failed hop can be retried. The seller's goods and buyer's credits enter escrow, incoming cargo space is reserved, and a destination delivery receipt is required before either ledger receives the exchanged value. Duplicate settlement has no additional effect. The two worlds, network observations, and receipts are saved in `galaxy.federation.json` as one bundle.

For a more realistic asynchronous demonstration, click **Reserve both sides**, **Queue async freight**, and repeatedly **Advance radio window**. Toggle the destination offline to watch a relay retain custody. Once it returns, the queued fragments complete and an application ACK travels the reverse route. Only then can you settle. The persistent queue and inbox are saved in `galaxy.mail.json`. Buying a faster ship unlocks a wider simulated modem tier and more frames per window; see [direct Data2G integration plan](docs/DATA2G-INTEGRATION.md).

**Important:** this is a *single-process two-world simulator*, not distributed settlement between independent radios. The receipt is hash-bound but not signed, and on-air carriage is not proven. Real peers will need independent durable outboxes, reconciliation after partition, a recovery/cancellation protocol, a trust model, and a **direct Data2G adapter**.

### Experimental Data2G on-air harness

A conservative direct Data2G command/KISS adapter is available for **receive-only capability probing and explicitly approved single-frame transmissions**. It does not automatically send game traffic, relay mail, or claim a remote receipt. Start with [the on-air test checklist](docs/ON-AIR-TESTING.md). Useful payload bundling is described there; synthetic padding has been removed from contract and trade messages.

### Freight weight classes and UTC ticks

Async exchange offers three information loads: **light** (bare transaction), **medium** (second-hop ore richness hint), and **heavy** (second-hop market prices). Medium/heavy data must come from an existing, provenance-labeled report; the demo seeds a simulated report. No transmission gets filler bytes to reach a target size.

In the browser, all galaxies advance their economy on the same **five-minute UTC boundaries**, including deterministic catch-up after being offline. Refreshing the page or selecting **Sync UTC clock** displays the current epoch. The separate radio-window simulator remains manual for controlled loss experiments. See [traffic classes and time synchronization](docs/TRAFFIC-CLASSES-AND-TIME.md).

## Design guardrails

Local-first; explicitly permissioned transmissions; inspectable/unobscured game messages; no real-money economy; no reward for raw spam traffic; duplicate-safe transactions; bounded packet/airtime budgets; versioned, forwards-compatible messages; honest separation of measured and reported data.

Amateur-radio regulatory compliance needs jurisdiction-specific review before real on-air use.
