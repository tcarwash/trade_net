# Trade Net

*A local-first space trading game with optional amateur-radio logistics.*

Build a fleet, explore your own galaxy, buy low and sell high, and fulfill freight contracts. When you connect with another operator, their station can become a node in your trade network. Link quality, frame loss, and relay routes become part of the game instead of just transport details.

**Status:** playable solo browser prototype. Radio exchanges, cross-galaxy settlement, and the Data2G interface are still experimental; the browser simulator does **not** transmit RF.

## Play locally

Requires **Python 3.10+**, with no third-party dependencies.

```sh
python -m tradenet.web --callsign AG7SU --seed 42
```

Open **http://127.0.0.1:8765**.

1. Buy cargo at the current planet's market.
2. Select a destination on the galaxy map and dispatch your ship.
3. Sell where demand is higher, or reserve cargo for a freight contract.
4. Buy more ships, upgrade their holds or modem class, and expand your routes.

The economy advances in shared five-minute UTC ticks, including when you're away. Each ship has independent cargo, fuel, condition, location, and upgrades. Optional **hard mode** offers better selling prices but permanently destroys ships reduced to zero condition.

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
- **Real freight:** trade messages can move through store-and-forward routes with custody tracking, retries, and acknowledgments. The simulated ship's movement along a link reflects frame progress.
- **Three useful payload classes:** **Light** carries transaction data; **Medium** adds second-hop ore information; **Heavy** adds second-hop market prices. No synthetic padding is added.
- **Ship tiers:** Scout (500 Hz), Courier (1,200 Hz), and Express (2,400 Hz) have different simulated transmission capabilities. The chosen mission ship determines its tier.
- **Mission risk:** an outbound message that expires before delivery damages its assigned ship, which returns to its origin. Hard mode can make that loss permanent. Ambiguous transactions remain pending reconciliation.

The long-term goal is for actual on-air transfer success, throughput, and network topology to shape the gameplay. For now, the browser's mail system and cross-galaxy exchange are local simulations—not independent RF-connected ledgers or cryptographically authenticated receipts.

## Documentation

| Guide | Contents |
|---|---|
| [Game design](docs/GAME-DESIGN.md) | World, economy, and progression ideas |
| [Roadmap](docs/ROADMAP.md) | Implemented milestones and next steps |
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
