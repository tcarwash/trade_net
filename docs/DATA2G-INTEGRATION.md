# Direct Data2G integration plan

Trade Net will integrate directly with **Data2G**, not route through radio-arcade. This is the intended adapter contract; no live RF adapter is implemented yet.

Data2G supports both connected hybrid-ARQ sessions and non-connected broadcast groups through its extended host/KISS interfaces, and offers narrowband (500 Hz) through wide (2400 Hz) operation. Consult the actual installed Data2G host's capabilities at runtime. Source: [Data2G README](https://github.com/arodland/Data2G#readme) and [architecture documentation](https://github.com/arodland/Data2G/blob/master/docs/ARCHITECTURE.md).

## Ship class determines the game ceiling

| Ship class | Simulated travel speed | Max eligible Data2G bandwidth | Simulated frames/window |
| --- | ---: | ---: | ---: |
| Scout / Wayfarer | 1 | 500 Hz | 2 |
| Courier | 2 | 1200 Hz | 6 |
| Express | 3 | 2400 Hz | 16 |

Purchasing a faster ship unlocks a wider set of *eligible* modem choices. This is a gameplay entitlement, not a claim that the RF link can sustain that speed. The adapter intersects the entitlement with Data2G's **actually advertised** modes and current station/operator bandwidth configuration. If no wider mode is available, the ship can still operate using a narrower one. Data2G retains channel-aware rate selection in connected mode.

The simulator currently models the difference as a per-logical-window frame budget; the numbers are gameplay balancing parameters, **not actual Data2G throughput specifications**. Frame size, FEC overhead, setup airtime, retries and available submodes must be measured on real Data2G builds before assigning on-air costs.

## Suggested integration layers

1. Start the existing Data2G host via its supported command interface or attach to a separately running host. Never assume internal Python APIs are stable.
2. Negotiate host capabilities and list available supported modes/bandwidths.
3. Expose an operator-controlled queue interface: `send_frame`, `receive_frame`, `cancel`, `capabilities`, `connection_status`, with no automatic PTT unless enabled.
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
