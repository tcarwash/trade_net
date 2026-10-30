# Trade Net on-air testing checklist

**Status:** Trade Net's web Comms path now sends and receives application messages through Data2G. The command-line tool below remains a separate single-frame diagnostic. A two-station RF run is still required to verify modem and on-air interoperability. Never use this software for actual emergency traffic.

## Traffic rule

No synthetic padding, filler, or arbitrary bytes to farm transfer achievements. Real application data may legitimately make a transmission longer. Examples: a requested market bulletin, signed trade terms, verified custody receipt, relevant route/neighbor advertisement, missing-fragment request, or station capabilities. A transmission containing optional data must show the operator the types and byte counts before sending.

Do not invent status chatter merely to increase score. Reward completion of useful transfers and successful delivery, not raw byte count. Duplicate retransmissions have zero content reward.

`tradenet.payloads` supports explicitly typed useful-data bundles with a compact 3-byte envelope prefix and 3-byte header per item. It never pads. Future opportunistic bundling can place additional useful items into existing Data2G codeword capacity, but only when the adapter knows the current mode's actual frame budget. Payloads that increase airtime are allowed when their content has gameplay value and the operator authorizes them.

## Before connecting a transmitter

1. Install a compatible Data2G host and verify audio/radio/PTT settings separately. The game does not configure the rig.
2. Check band privileges, regional band plan, occupied frequency, station ID, digital emission bandwidth, and your local automatic-control obligations. Use a dummy load or a contained test path before radiating.
3. Ensure no competing application owns the Data2G command/KISS ports (default TCP 8300 and 8100).
4. Keep Data2G's own transmit behavior under operator control; the Trade Net harness never starts Data2G or keys PTT directly.
5. Coordinate a second station running the same group/protocol. The receiver should run the receive-only harness.

## Receive-only and capability probe

```sh
python -m tradenet.data2g probe --host 127.0.0.1
python -m tradenet.data2g listen --callsign AG7SU --group TRADENET
```

`probe` requests `MODES` from Data2G; `listen` opens the named KISS broadcast group and prints checked frame bytes, their length, and digest. Neither operation transmits an application frame. This does **not** guarantee that Data2G itself has no other autonomous transmissions configured; check its station configuration.

## Deliberate single-frame transmit test

Prepare a small plain-text application payload (1–200 bytes) with your preferred editor. No opaque or encrypted content is necessary. First inspect what will go on air and choose an exact `mode_id` from the `probe` output, within the ship-tier bandwidth ceiling.

```sh
python -m tradenet.data2g send --callsign AG7SU --group TRADENET \
  --ship-tier 0 --mode YOUR_ADVERTISED_500HZ_MODE \
  --file /path/to/your-small-test-payload.txt --enable-transmit
```

The CLI prints the **actual file byte count and SHA-256 prefix**, then requires typing an exact one-time confirmation. It sends exactly those bytes once to Data2G's KISS queue. There is no automatic repeat, invented data, or payload expansion. The Data2G modem may add its normal framing/FEC and schedule the physical burst.

**Important:** Data2G's KISS ACKMODE means a frame was transmitted, *not* received. The initial harness does not request ACKMODE or claim remote receipt. Confirm the destination decoded the matching hash using the second station's receive log. Full application ACK/receipt integration is a later milestone.

## Go/no-go test matrix

| Test | Current state |
| --- | --- |
| KISS encode/decode escapes | Automated unit tests |
| Parse `MODES` and filter ship tiers | Automated unit tests |
| Deny unauthorized send | Automated unit tests |
| Reject oversized single-frame test | Automated unit tests |
| Receive-only group listener | Implemented, requires live host validation |
| One manually authorized TX frame | Implemented, requires dummy-load then live validation |
| Matching remote app receipt and station-local settlement | Implemented in web Comms; two-station RF run pending |
| Multipart application message and retry | Implemented in web Comms; two-station RF run pending |
| Relay custody | Outside the direct station exchange flow |

Start with a no-PTT receive-only test, then dummy-load single-frame send, then a coordinated low-duty on-air exchange. The web receiver can automatically send application receipts after receiving a complete addressed message; run it only with an appropriate Data2G transmit setup.
