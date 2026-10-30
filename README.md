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

On a phone, the command deck becomes a full-width layout with a thumb-friendly bottom navigation bar, swipeable sector chart, and individual commodity price cards. The highlighted objective at the top points to your next useful action; when you've met the requirements, it can complete a chapter or turn in cargo/passengers directly. The contract board filters freight, VIP, and radio deliveries. Actual local flight progress is visible both on the chart and on a progress bar; orders are automatically saved by the local game server. Mobile home-screen icons and an app manifest are included for browsers that support adding local web apps to the home screen. Access from another device requires making the server reachable from that device; installation support depends on a trusted origin (typically HTTPS or localhost). Offline play is **not** supported: the interface requires its game server.

1. Open **Contracts** and choose a local freight job. The board gives a delivery destination, quantity, deadline, and guaranteed payout.
2. Buy the requested goods (the suggested pickup is a route hint, not a restriction), select the destination on the map, and dispatch your ship.
3. Deliver the cargo from the contract board when docked, or sell speculative cargo at higher-demand markets.
4. Buy more ships, upgrade their holds or modem class, and expand your routes.

**Your export base is Haven.** To fulfill a real partner's radio contract, buy the requested goods at another starport, carry them back to Haven aboard a ship, and use **Comms → Unload all imported cargo** to put them in the export warehouse. Then prepare the partner contract and transmit from Haven. Buying goods at Haven itself does not create eligible export cargo; its ordinary market stock is separate from your warehouse. Failed/rejected deliveries return reserved goods to that warehouse for a retry.

The economy advances in shared five-minute UTC ticks, including when you're away. Each ship has independent cargo, fuel, condition, location, and upgrades. Optional **hard mode** offers better selling prices but permanently destroys ships reduced to zero condition.

The local galaxy now contains **ten starports** with distinct production specializations and roles. First visits reveal their character and award 90 exploration credits per new destination. Older five-port saves gain the new locations while preserving existing market stock. The market remembers the lowest buy and highest sell quote you have actually observed for each commodity while docked. The market-intel column shows the remembered port and its price difference from your current quote; those quotes are historical, not guaranteed live offers.

Space isn't empty: the asteroid field circles the central sector, blocking direct arrivals at one starport for 90 seconds before moving to the next. Ionized gas clouds damage hulls, while pirate interceptions cause damage and a capped credit toll. The route preview warns you about conditions before you launch, and better ship tiers mitigate hazard damage. Route hazards are deterministic for a given route and economy interval, not rerolled randomly on every button press.

The **Contracts** board also offers VIP passenger missions: navigate to the pickup port, board a diplomat, medic, survey captain, or trade delegate on a specific ship, and reach the requested destination for a bonus. Each ship carries at most one VIP; you can cancel a passenger mission without destroying your ship. Freight, VIP transport, exploration, and radio logistics all share the same fleet and credits.

### Frontier campaign, fog of war, and outfitting

- **Fog of war:** unexplored ports appear as unidentified signals, with their name and economic role concealed until visited. A ship-mounted scanner can identify distant ports and preview corridor hazards in advance. Known market prices are still only the quotes you actually observed while docked.
- **Frontier Signal campaign:** a four-chapter introductory quest takes you from Kepler's signal to Aurora's medical relief, Eidolon's silent observatory, and a final return to Haven. Chapters require you to be at the objective location; the clinic also consumes two medicine from the active ship.
- **Discovery sites:** first visits reveal one-time supply caches, navigation beacons, or trade outposts and pay additional exploration rewards. Discovery rewards cannot be repeated by revisiting a port.
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
- **Real freight:** trade messages can move through store-and-forward routes with custody tracking, retries, and acknowledgments. The simulated ship's movement along a link reflects frame progress.
- **Three useful payload classes:** **Light** carries transaction data; **Medium** adds second-hop ore information; **Heavy** adds second-hop market prices. No synthetic padding is added.
- **Ship tiers:** Scout (500 Hz), Courier (1,200 Hz), and Express (2,400 Hz) have different simulated transmission capabilities. The chosen mission ship determines its tier.
- **Mission risk:** an outbound message that expires before delivery damages its assigned ship, which returns to its origin. Hard mode can make that loss permanent. Ambiguous transactions remain pending reconciliation.
- **Premium RF freight:** a verified partner delivery pays `min(1500, 100 + 2 × base value of requested cargo)` credits to the sending station, in addition to exploration/contact rewards. The payout is calculated from the locally staged contract after a matching application receipt—not from a peer's untrusted credit claim. Local freight provides a lower-stakes path to earning capital and outfitting radio-capable ships.

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
