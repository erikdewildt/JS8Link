# JS8Link ARQ/1

JS8Link ARQ/1 provides optional application-level delivery confirmation for directed JS8Call
messages. It does not modify JS8Call itself. Best-effort delivery remains the default for messages
sent without confirmed delivery.

## Wire format

The protocol metadata is an ASCII suffix appended to the JS8Call payload. JS8Call adds its own
visual end-of-transmission diamond (`♢`) after the complete payload.

```
<human payload> ~<version><opcode><message-id>
```

### Fields

| Token        | Description                                                                                                                                      |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `~`          | Protocol delimiter — marks the start of JS8Link metadata.                                                                                        |
| `version`    | Single decimal digit. Current version is `1`.                                                                                                    |
| `opcode`     | `D` for a data message, `A` for an acknowledgement.                                                                                              |
| `message-id` | Six characters from **Crockford Base32** (`0-9 A-H J-K M-N P-T V-Z`). Upper- or lowercase accepted on receipt; always uppercase on transmission. |

### ACK format

An acknowledgement has no human payload — it is a bare protocol suffix. A callsign prefix may be
present for readability but is not required by the parser.

```
~1A7Q2M9C
```

```
PA3ABC ~1A7Q2M9C
```

### Data format

The human-readable payload is separated from the suffix by a single space.

```
DF7ET HELLO ERIK ~1D7Q2M9C
```

On the wire via the JS8Call API, the complete transmission looks like:

```python
tx.set_text("DF7ET HELLO ERIK ~1D7Q2M9C")
tx.send_message()
```

The receiving JS8Call instance delivers a `RX.DIRECTED` event whose `value` or `TEXT` field
contains the full payload including the suffix. The parser strips the suffix and returns the
human text and message ID.

## Delivery state machine

### Sender

```
                 ┌──────────────┐
   send_message() │ transmitting │
                 └──────┬───────┘
                        │ TX.SEND_MESSAGE
                        ▼
                 ┌──────────────┐
                 │ awaiting_ack │◄────────────── retry ──────┐
                 └──────┬───────┘                            │
                        │                                    │
           ┌────────────┼────────────┐                       │
           │            │            │                       │
      ACK received  timeout      TX error              ┌─────┴──────┐
           │       (deadline)  (transient)             │  retrying  │
           ▼            │            │                 └────────────┘
     ┌──────────┐       │            │                       ▲
     │ delivered│       ▼            ▼                       │
     └──────────┘  ┌─────────┐  ┌──────────┐    attempts < max_attempts
                   │  failed  │  │ backoff  │                │
                   └─────────┘  │ +15 sec  │                │
                                └──────────┘                │
                                                            │
                                              attempts >= max_attempts
                                                            │
                                                            ▼
                                                     ┌──────────┐
                                                     │  failed  │
                                                     └──────────┘
```

- The sender enforces **at most one in-flight confirmed delivery per peer** (HTTP 409 if violated).
- Status `transmitting` means the text was queued in JS8Call but the `TX.FRAME` event has not yet been observed.
- After `TX.FRAME`, status moves to `awaiting_ack` and a deadline is set.
- If the deadline expires, the message is **retransmitted** with the **same message ID**.
- After `max_attempts` (default 3) without an ACK, the delivery is marked `failed`.
- Reception of an `RX.DIRECTED` event with opcode `A` and matching `(callsign, protocol_id)` marks the delivery `delivered`.

### Receiver

- On first receipt of a data message with a valid suffix, the receiver:
  1. Stores the message in `received_messages` with `delivery_mode = "confirmed"`.
  2. Creates an `arq_receipts` record keyed by `(callsign, protocol_version, protocol_id)`.
  3. Transmits an acknowledgement.
- On **duplicate** receipt (matching `arq_receipts` row):
  1. Increments `duplicate_count`.
  2. Transmits an acknowledgement again — the sender may have missed the first ACK.
  3. Does **not** create a new `received_message` row.
- Duplicate detection prevents the same confirmed message from appearing multiple times in the UI.

## Acknowledgement timeouts

Timeouts are chosen per JS8Call speed mode so that a complete transmit cycle plus network
latency can elapse before a retry is scheduled.

| Mode   | Timeout (seconds) |
| ------ | ----------------- |
| Turbo  | 45                |
| Fast   | 45                |
| Normal | 60                |
| Slow   | 120               |
| JS8 40 | 150               |
| JS8 60 | 210               |

If JS8Call is disconnected during a deadline window, the deadline is extended by 15 seconds
on each scheduler poll to avoid premature failure.

## Retry scheduler

A background task (`arq_retry_scheduler`) polls the `transmitted_messages` table for expired
acknowledgement deadlines:

- **Poll interval**: starts at 1 second, grows exponentially to a maximum of 30 seconds when idle.
- **Retry**: re-encodes the original text with the same protocol ID and re-queues via the JS8Call API.
- **Failure**: after `max_attempts` (3), sets `delivery_status = "failed"` with `last_error = "No acknowledgement received"`.
- **Disconnected**: if JS8Call is not connected when a deadline expires, the deadline is pushed forward by 15 seconds.

## Transmission serialisation

JS8Call can only handle one transmission request at a time. To prevent interleaving, the
`transmit_js8_text()` helper serialises transmissions:

- **Per-peer lock**: for confirmed (ARQ) messages, a lock is keyed on the destination callsign.
  This prevents retries and new messages to the same peer from overlapping.
- **Global fallback**: best-effort messages and messages without a target callsign share a single
  global lock so they cannot collide with any ARQ transmission.

## Database schema

### `transmitted_messages` (ARQ columns)

| Column            | Type          | Description                                                           |
| ----------------- | ------------- | --------------------------------------------------------------------- |
| `delivery_mode`   | `VARCHAR(24)` | `"best_effort"` or `"confirmed"`                                      |
| `protocol_id`     | `VARCHAR(16)` | Six-character message ID, indexed                                     |
| `delivery_status` | `VARCHAR(32)` | `transmitting` / `awaiting_ack` / `retrying` / `delivered` / `failed` |
| `attempts`        | `INTEGER`     | Number of transmit attempts (including initial)                       |
| `max_attempts`    | `INTEGER`     | Maximum attempts before giving up (3 for ARQ)                         |
| `ack_deadline`    | `DATETIME`    | Absolute time after which a retry is triggered                        |
| `delivered_at`    | `DATETIME`    | Timestamp when ACK was received                                       |
| `last_error`      | `TEXT`        | Last error message if delivery failed                                 |

### `arq_receipts`

| Column                | Type          | Description                                               |
| --------------------- | ------------- | --------------------------------------------------------- |
| `callsign`            | `VARCHAR(32)` | Sender callsign, indexed                                  |
| `protocol_version`    | `INTEGER`     | ARQ protocol version                                      |
| `protocol_id`         | `VARCHAR(16)` | Six-character message ID                                  |
| `received_message_id` | `INTEGER`     | FK to `received_messages.id` (nullable for ACK-only rows) |
| `duplicate_count`     | `INTEGER`     | Number of duplicate deliveries received                   |
| `ack_sent_at`         | `DATETIME`    | When the first ACK was transmitted                        |

Unique constraint on `(callsign, protocol_version, protocol_id)`.

### `received_messages` (ARQ columns)

| Column          | Type          | Description                                     |
| --------------- | ------------- | ----------------------------------------------- |
| `delivery_mode` | `VARCHAR(24)` | `"best_effort"` or `"confirmed"`                |
| `protocol_id`   | `VARCHAR(16)` | Six-character message ID (nullable for non-ARQ) |

## Edge cases

| Scenario                                                      | Behaviour                                                                                                                             |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| Message larger than JS8Call payload limit after suffix        | JS8Call truncates; suffix may be lost. Use shorter payloads in Fast/Turbo modes.                                                      |
| Suffix appears mid-payload (e.g. user types `~1D...` in chat) | Parser uses `re.search` with `$` anchor — only a suffix at the **end** of the string is matched. Mid-payload occurrences are ignored. |
| JS8Call diamond appended                                      | Regex skips optional `♢` and trailing whitespace before matching.                                                                     |
| Unknown protocol version                                      | Messages with a non-matching version are treated as **best-effort** — the suffix stays in the displayed text.                         |
| Multiple stations behind same callsign                        | Receipt is not cryptographic; any station transmitting the correct callsign can acknowledge.                                          |
| ACK received after delivery marked failed                     | Ignored silently — the `TransmittedMessage` is no longer in `awaiting_ack`/`retrying` state.                                          |
| Duplicate ACK received                                        | Ignored — delivery is already marked `delivered`.                                                                                     |

## Compatibility

Only messages explicitly sent with `delivery_mode = "confirmed"` receive the suffix. A regular
JS8Call station treats the suffix as text and otherwise receives the directed message normally.
No automatic retries occur for best-effort messages.
