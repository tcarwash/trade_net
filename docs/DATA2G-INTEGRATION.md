# Direct Data2G integration plan

Trade Net integrates directly with **Data2G**, not through radio-arcade. The initial `tradenet.data2g` command/KISS harness supports receive-only probing and manually authorized single-frame sends; it is not yet wired to the autonomous game mail queue. See [on-air test checklist](ON-AIR-TESTING.md).

Data2G supports both connected hybrid-ARQ sessions and non-connected broadcast groups through its extended host/KISS interfaces, and offers narrowband (500 Hz) through wide (2400 Hz) operation. Consult the actual installed Data2G host's capabilities at runtime. Source: [Data2G README](https://github.com/arodland/Data2G#readme) and [architecture documentation](https://github.com/arodland/Data2G/blob/master/docs/ARCHITECTURE.md).

## Ship class determines the game ceiling

| Ship class | Simulated travel speed | Max eligible Data2G bandwidth | Simulated frames/window |
| --- | ---: | ---: | ---: |
| Scout / Wayfarer | 1 | 500 Hz | 2 |
| Courier | 2 | 1200 Hz | 6 |
| Express | 3 | 2400 Hz | 16 |

The normal shipyard also has named hulls, independent of the legacy tier
indices used by the test harness:

| Hull | Cost (cr) | Cargo | Speed | Eligible bandwidth ceiling | Simulated frames/window |
| --- | ---: | ---: | ---: | ---: | ---: |
| Wisp | 200 | 16 | 1 | 200 Hz, N4 family | 1 |
| Scout | 350 | 30 | 1 | 500 Hz | 2 |
| Courier | 900 | 40 | 2 | 1200 Hz | 6 |
| Hauler | 1400 | 60 | 2 | 2300 Hz, FSK family | 10 |
| Express | 1800 | 30 | 3 | 2400 Hz | 16 |

`tradenet/modem-modes.json` is a timestamped, read-only `MODES` observation
from the local Data2G host (command port 8300, KISS 8100). It is a capability
snapshot, not a current link-status report. The shipyard displays its eligible
data modes; control-only ACK modes are excluded. `eligible_ship_modes` applies
each hull's ceiling and family restrictions. No mode is selected or transmitted
by viewing or purchasing a ship. The mail simulator retains its three legacy
bandwidth labels, throttling named hulls by their own frame budgets; it does
not emulate a specific advertised PHY mode or its real airtime.

Refresh the observation manually with the receive-only probe:

```sh
python -m tradenet.data2g probe --command-port 8300 --kiss-port 8100
```

The command parser accepts CR-only, LF, and CRLF replies, including fragmented
responses. The running game loads the saved observation once at startup; the
probe prints the current list but does not overwrite that observation file.

## Normal intergalactic travel

The Flight deck's destination menu includes both local starports and other
galaxies. A departure reserves the current ship for a meaningful voyage
manifest in the durable mail outbox, costing ten fuel exactly once. Receipt
confirmation moves that same ship and its cargo into the destination galaxy's
markets. It does not transfer ownership to the lab's separate federation ledger.
Crossings progress automatically on economy ticks; the debug radio-window
control remains available for deterministic tests. Offline stations pause
progress, and a missing/expired ACK never invents an arrival. Expired voyages
remain pending reconciliation; a player-facing reconciliation workflow is not
implemented yet. All of this remains simulated—no game action initiates RF.

Purchasing a faster ship unlocks a wider set of *eligible* modem choices. This is a gameplay entitlement, not a claim that the RF link can sustain that speed. The adapter intersects the entitlement with Data2G's **actually advertised** modes and current station/operator bandwidth configuration. If no wider mode is available, the ship can still operate using a narrower one. Data2G retains channel-aware rate selection in connected mode.

The simulator currently models the difference as a per-logical-window frame budget; the numbers are gameplay balancing parameters, **not actual Data2G throughput specifications**. Frame size, FEC overhead, setup airtime, retries and available submodes must be measured on real Data2G builds before assigning on-air costs.

## Suggested integration layers

1. Attach to a separately running Data2G host. The initial harness does not start or configure the radio itself. Never assume internal Python APIs are stable.
2. Negotiate host capabilities and list available supported modes/bandwidths.
3. Build out the operator-controlled queue interface after validating the implemented single-frame `send_once`, `receive`, `modes` and `open_group` calls against a live host. Add `cancel`, `connection_status`, and explicit transmit queue permissions later.
4. Connected ARQ is the first choice for addressed trade/receipt exchanges; non-connected groups can carry compact market bulletins and peer discovery if appropriate. Avoid double-retransmitting at both Data2G ARQ and application levels.
5. Keep Trade Net's application message IDs, hashes, TTL, custody, and settlement receipts even if Data2G provides link-level delivery.
6. Add on-air station ID, transmit limits, payload inspection and bandplan/operating safeguards before real use.

## Critical distinction

Data2G's link ACK says an RF payload was received. Trade Net's application ACK says the destination reconstructed and accepted a particular message hash. A **trade settlement receipt** says an authority accepted an inventory transfer. They must remain different events, especially across relays and offline peers.

## Initial verification tasks

- Confirm Data2G host command syntax and KISS port framing in the version we integrate.
- Decide addressed connected mode versus extended broadcast for discovery; both may be used.
- Capture host-advertised mode IDs and bandwidth as data, without hardcoding invented IDs.
- Benchmark 128-byte control messages and 1–64 KiB multipart shipments in simulated and real channels.
- Ensure manual operator transmit permission, queue pausing, and retry budgets.
