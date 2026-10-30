# Transmission weight classes and global economy time

## Three information loads

The shipping manifest is always meaningful. A heavier class conveys additional information learned from the destination's **next hop**, with source/via/epoch/provenance included so a receiver can judge age and trust.

| Class | Contents | Intended gameplay |
| --- | --- | --- |
| **Light** | Transaction ID and hash of agreed terms | Fast, robust freight order |
| **Medium** | Light plus a second-hop ore stock/production hint | Identify promising mineral routes |
| **Heavy** | Medium plus the second-hop commodity market prices | Long-range arbitrage and market intelligence |

No class pads to a minimum byte count. Light uses compact JSON for compatibility with the current prototype. Medium/heavy use the compact `TN1` typed-item envelope with only real data items. Frame sizes and time depend on the actual serialized bytes, current Data2G mode and channel conditions. Sending a heavy bulletin may legitimately require additional airtime.

Second-hop intel must already exist in a cache of received observations. If none is available, medium/heavy are unavailable rather than fabricated. The current demo seeds an explicitly labeled **simulated** market bulletin from a third galaxy and gives it a source, reporting intermediary and observed epoch. Real RF operation must use received reports, not the demo's synthetic market source.

Future rewards should be tied to *new, accepted, still-useful data* (e.g. a previously unknown market revision), with per-origin/revision deduplication. Repeatedly sending the same info should not generate new XP. Operators can inspect the byte count and payload types before a live transmission.

## UTC economy epochs

Each galaxy derives its economy epoch from a common wall-clock boundary:

```
epoch_id = floor(Unix_UTC_seconds / 300)
```

Default: **one economy tick every five minutes**, on UTC `:00`, `:05`, `:10`, etc. Every galaxy stores its last processed absolute epoch and catches up elapsed epochs after restarting or reconnecting. Market stock production/consumption is deterministic, so bulk catch-up reproduces the same state as applying each missed tick sequentially. It is not tied to receiving RF frames or pressing a button.

Different galaxies need not have identical *relative* tick counters or markets; they share the same **absolute epoch ID**. Market bulletins should include that epoch so remote players can distinguish fresh prices from stale data. A receiving station must never overwrite newer intelligence with an older epoch or consider a reporter's claim authenticated solely because it arrived over RF.

Clock drift: synchronize station computers with NTP or another trusted time source. A system clock moving backward never rewinds the game. Huge forward clock jumps can cause irreversible catch-up; operators should correct clocks before running persistent sessions. Eventually, multi-station protocol rules should bound acceptable timestamp skew and use receipt/revision sequencing rather than wall time alone for financial settlement.

The current radio simulator's **communication windows** remain manually advanced for reproducible packet-loss testing. Real Data2G transport will operate asynchronously in real elapsed time, while the economy follows the fixed UTC epoch schedule.
