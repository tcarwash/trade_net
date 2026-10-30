# Trade Net — Architecture and Wire Protocol

The local Data2G adapter now carries compact version 1 station-exchange frames.
The broader game transport and inter-galaxy voyage concepts below remain
separate from that live radio exchange.

## Station exchange v1

Frames are compact UTF-8 JSON and limited to 200 bytes. A complete application
message may contain up to 4096 bytes and is split into at most 64 bounded
`part` frames when necessary. Each part has the sender, destination, message
ID, part index/count, and the complete message hash. The receiver stores
partial messages, rejects conflicting parts, checks the complete hash, then
applies the message once. Incomplete messages do not change inventory or
credits. After 90 seconds without another part, the receiver can send up to
three bounded `repair` requests naming the missing part indices as a bitmap.
The sender checks the original message ID, hash, destination and part count
against its saved transmission before resending only those parts. Every
complete message has `v:1`,
a unique message id `i`, sender `f`, and destination `d`. `contact` sends the
sender's resource profile, open contracts, and optional neighbor summaries.
The receiver credits its station once, applies the sender's information, and
returns `contact_ack` with its own profile and contracts. Both stations own
their own economy and contract book.

After contact, `delivery` carries a contract ID and an exact inventory
manifest. A legacy delivery uses `g` (good) and `q` (quantity); a long-haul
delivery additionally includes `m`, a list of `[good, quantity]` entries.
The receiving station checks the entire manifest against its own open
contract and accepts all goods atomically; incomplete manifests are rejected
without stock changes. It then creates replacement demand from its current
stock and sends `delivery_ack`. The sender calculates a bounded reward from
its own previously staged goods after the matching ACK (never from a peer's
arbitrary credit claim), marks the old contract fulfilled, and stores the
replacement contract. Repeated message ids return the saved receipt without
crediting or adding stock again. Frames not addressed to the station are kept
as gossip; advertised neighbor richness and contracts may be cached. Larger
deliveries include available second-hop stock, production and contract reports.
The sender only forwards reports it actually received, with observation time
and reporting station retained in the receiver's cache.

Contract advertisements are backward compatible: legacy offers remain
`[id, good, quantity]`, band-limited ones append the requested band as a
fourth field, and long-haul offers use five fields with an empty-band
placeholder and a two-or-more-resource manifest. Older peers ignore offers
whose format they do not understand; at least one simple offer remains on
each refreshed three-contract board. Warehouse inventory persists between
days, and an entire manifest is reserved together only when the operator
prepares the delivery.

When configured with `--rigctld-host` (and optional `--rigctld-port`), the
server sends only the read-frequency `f` request to Hamlib rigctld. The
observed band is displayed and first-time bands earn one bounded discovery
bonus each. For a band-limited contract the *sending client* checks the rig's
current band again immediately before both manual transmission and recovery
retries. It does not tune the rig, key PTT, or prove the physical transmit
band to the recipient. Band names are gameplay classifications, not operating
privileges or a regulatory band plan.

Neighbor reports currently support two-hop **discovery only**. True
multi-hop cargo custody, operator acceptance, forwarding and final settlement
are future protocol work; a report about a neighbor is not a delivery route.

Credit awards are based on the bytes received, capped at 25 credits per frame.
Receipts carry the reward for their reply bytes. The receiver persists pending
receipts before sending and retries modem submission with bounded backoff. If
the application receipt is lost, the sender retries the exact saved message
up to two times after its response deadline; duplicate processing returns the
original receipt without paying twice. A final timeout damages the local ship.
Staged goods remain reserved for a later manual retry, while a confirmed
rejection returns them. The receiver does not require a delivery setup action.

Radio sends use four callsign-offset send windows in a repeating 12-second UTC
period, with one local transmitter lock for manual sends and automatic replies.
This spreads starts across stations; it cannot guarantee a clear channel or
prevent overlap during long physical transmissions. Data2G still controls its
own channel access. A sender marks success only after a matching application
receipt with the original message ID, hash, destination and reply type.

## Components

- **Core engine:** deterministic commands/reducer, economy ticks, ships and starports; no dependency on UI or modem.
- **Journal and ledger:** durable append-only commands, deduplication keys, resulting state snapshots, replay/migrations.
- **Transport abstraction:** send/receive opaque bounded envelopes; fake lossy transport first, then radio-arcade adapter.
- **Reliable delivery:** segmentation/reassembly, integrity verification, retries, app receipts, outbox/relay custody.
- **Discovery and metrics:** adjacency digests, measured directional links, stale/report provenance.
- **UI:** state projections, no direct mutation of ledger.
- **AI agents:** submit validated game commands, not privileged state mutations.

## End-to-end state machine

```text
DRAFT -> RESERVED -> QUEUED -> SENDING -> TRANSFER_VERIFIED
                                  |                 |
                                  v                 v
                              RETRY_WAIT       DELIVERY_ACKED
                                                    |
                                                    v
                                              APP_ACCEPTED
                                                    |
                                                    v
                                                SETTLED
```

Failure/expiry may branch from any pending state to REJECTED/EXPIRED, with idempotent reserve release. TRANSFER_VERIFIED on receiver and DELIVERY_ACKED on sender are different observations. An acknowledgment is not settlement.

## Suggested compact envelope

```text
version | type | flags | message_id | source_id | destination_id
world_id | created_epoch | ttl | payload_length | payload_hash | payload
```

All fields have explicit byte limits and canonical serialization. Prefer CBOR or fixed binary framing after measuring overhead. For fragmentation, use a bounded chunk header with message ID, part index/count, chunk hash/check, and total hash. The actual modem may already fragment; avoid redundant layers until the adapter's framing and maximum payload are known.

Message classes: HELLO, PEER_DIGEST, MARKET_BULLETIN, ORDER, CUSTODY_ACK, DELIVERY_ACK, APP_RESULT, SETTLEMENT, FRAGMENT_REQUEST. Size budgets to be benchmarked against real radio-arcade/Data2G payload capacities. HELLO and digests should be small; longer payloads explicit mission choices.

Receipts bind original ID, content digest, receiving identity, result, receiver nonce, and logical timestamp, with optional signing. The signature mechanism is pluggable; it must not encrypt or conceal message meaning. Callsign identification, disclosure and allowed signaling require an amateur-regulatory review.

## Discovery/privacy

A HELLO may exchange protocol versions, world ID, optional nickname and public capabilities. A PEER_DIGEST has a strict max entry count (e.g. eight), per-entry peer identifier, directional rate estimate, success fraction, last-seen age bucket, provenance and expiry; never include private frequencies, location or full logs by default. A learned next-hop advertisement is a *claim*, not direct proof.

Reject malformed/oversized/expired digests, ignore self-links, cap traversal depth and graph size, deduplicate sequence numbers, and age out stale route information. Allow users to disable gossip or selectively hide neighbors.

## Link estimators

Session record:
```json
{
  "peer": "EXAMPLE",
  "direction": "outbound",
  "transport": "rf",
  "started_ms": 0,
  "ended_ms": 120000,
  "verified_unique_payload_bytes": 4096,
  "attempted_air_bytes": 6400,
  "frames_sent": 14,
  "frames_lost_or_unacked": 4,
  "delivery_acknowledged": true
}
```

Goodput = verified unique payload bytes / wall-clock transfer seconds. Count retry overhead only in the denominator, not the unique-byte numerator. Track completion ratio over attempted sessions (including failures), median latency, protocol overhead, and confidence/sample count. For received-only sessions, receiver cannot infer all sender retry airtime; mark estimates accordingly. Use bounded, recent smoothing and aging rather than all-time averages.

**Do not equate frame loss with physical cargo loss.** A lost chunk is a transport event; game attrition is a visible, deterministic function of airtime, retries, deadline and explicit insurance/contract policies.

## Transaction integrity

Every inventory-affecting command has world ID, actor, monotonic/nonce command ID, base revision and expiration. An authority accepts a command at most once and produces deterministic result plus new ledger revision. Reserve escrow before dispatch; settle only with a unique acceptance result. A duplicate receives the original receipt. A late/replayed/reordered command cannot issue extra resources.

There is one authority per hosted world. Independent personal galaxies have separate ledgers; cross-galaxy economic effects require each world's explicit contract settlement and compensation/expiry rules. Cryptographic signatures provide attribution only insofar as keys are trusted. They do not prove the RF route.

## Radio-arcade adapter

Proposed engine-facing interface (pseudocode, **not a claim about radio-arcade's current API**):

```python
class Transport:
    async def send(self, destination: str, payload: bytes, priority: int) -> str: ...
    async def receive(self) -> AsyncIterator[ReceivedFrame]: ...
    def capabilities(self) -> TransportCapabilities: ...
    def request_cancel(self, local_send_id: str) -> None: ...
```

Capabilities include max payload, supported addressing/broadcast, ACK behavior, duplex constraints, estimated airtime, and operator PTT control. Start with simulated in-memory transport, loss/reordering/duplication injection, then build an adapter using *verified* library APIs.

Never automatically retransmit without configured duty-cycle, airtime and operator controls. Game priorities cannot override actual emergency traffic or legal operating requirements.

## Security and validation

Untrusted packets must not trigger arbitrary execution, file access, automatic PTT, or unbounded allocations. Validate lengths before allocation; maintain bounded outbox/inbox/relay storage, reject unrecognized versions safely, and use message TTL and per-peer rate limits. Store received raw hashes and decoded metadata for audit, with configurable privacy/retention. Tests must include hostile lengths, forgery, conflicting snapshots, clock skew, duplication, reordering, loss and restart during settlement.
