# JS8Call protocol and diagnostic interpretation

This document is the protocol contract used by JS8Link when it interprets
JS8Call-improved 3.x data. It separates the JSON control API from the JS8 text
protocol carried over radio. Code that stores stations, SNR values, links,
messages or diagnostics must follow these rules.

## Authoritative sources

- [JS8Call-improved API documentation v3.0.0](https://js8call.com/JS8Call-improved/d7/d15/md_docs_2API.html)
- [JS8Call-improved user guide](https://js8call.com/JS8Call-improved/d6/d14/md_docs_2JS8Call__User__Guide.html)
- [JS8Call-improved source repository](https://github.com/JS8Call-improved/JS8Call-improved)

The API documentation defines the JSON envelopes and endpoints. The user
guide defines the user-facing radio commands and heartbeat behavior. If a
future JS8Call version contradicts this document, preserve the raw envelope,
classify it as unknown and update this contract only after checking an
authoritative source.

## Two protocol layers

### JSON API layer

JS8Link connects to JS8Call over TCP on port 2442 (configurable). Each
newline-delimited JSON object has:

```json
{
  "type": "RX.DIRECTED",
  "value": "KE2DMC: @HB HEARTBEAT ♢ ",
  "params": {
    "FROM": "KE2DMC",
    "TO": "@HB",
    "CMD": " HEARTBEAT",
    "GRID": "FN32",
    "SNR": 1,
    "OFFSET": 816,
    "DIAL": 7078000,
    "FREQ": 7078816,
    "SPEED": 0,
    "TDRIFT": 0.54,
    "EXTRA": "",
    "TEXT": "",
    "UTC": 1769740226361,
    "_ID": -1
  }
}
```

- `type` identifies an API command, response or asynchronous event.
- `value` contains a scalar result or rendered radio text.
- `params` contains structured fields and radio metadata.
- `_ID` correlates requests and responses. `-1` denotes an unsolicited event.
  The ID number is the epoch time of 1499299200000 (July 6, 2017) plus the
  current epoch time.
- `params.UTC` is Unix epoch time in milliseconds where supplied.
- `params.SNR` on an RX event is the SNR at which the local JS8Call instance
  decoded the transmitted frame.
- `params.DIAL` is the radio dial frequency in Hz.
- `params.FREQ` is `DIAL + OFFSET`.
- `params.OFFSET` is the audio offset in Hz within the passband.
- `params.SPEED` is the submode code (see mode table below).
- `params.TDRIFT` is the time drift in milliseconds.

### Radio text layer

Directed traffic is normally rendered as:

```text
SOURCE: TARGET COMMAND PAYLOAD ♢
```

`♢` is the configurable end-of-transmission marker. It is display metadata,
not message content. JS8Link removes it for comparison and user-facing text,
but retains the raw envelope in diagnostics.

Long messages consist of multiple over-the-air frames. The protocol defines
six frame classes at the modulation layer:

| Frame type | Purpose |
|---|---|
| **Heartbeat** | Beacon or CQ: compound callsign + grid |
| **Compound Callsign Partial** | First frame of a 2-frame transmission with a compound (long) callsign |
| **Compound Callsign Directed Command** | Second frame of a 2-frame compound transmission, carrying the command |
| **Directed Command** | Single-frame directed command with standard callsigns |
| **Data Huffman** | Uncompressed variable-encoded character data (modified Huffman code) |
| **Data Dictionary** | Compressed character data using (s,c)-Dense Code word-level compression |

Each frame carries a transmission flag:
- **Default Frame** — interior frame of a multi-frame transmission
- **First Frame** — first frame of the transmission
- **Last Frame** — last frame of the transmission (triggers display)
- **Flag Reserved** — reserved for future use

The API usually exposes assembled readable text; `TX.FRAME` can instead
contain tone symbols or incomplete frame data.

Callsigns are encoded in **28 bits** for standard callsigns and **50 bits**
for compound callsigns (up to 11 characters with `/` separators and optional
`@` prefix). Grid locators are encoded in **15 bits** as documented in the
WSJT-X protocol specification.

## RX event types — detailed structure

### RX.ACTIVITY

`RX.ACTIVITY` has two forms depending on whether the decoder identified a
directed frame:

**Simple form** (undirected decode):
```json
{"params":{"DIAL":7078000,"FREQ":7080420,"OFFSET":2420,"SNR":-22,"SPEED":1,
 "TDRIFT":0.265,"UTC":1769740328005,"_ID":-1},
 "type":"RX.ACTIVITY","value":"HC5PH: "}
```

**Rich form** (directed decode reported as activity):
```json
{"params":{"CMD":" MSG","DIAL":7078000,"EXTRA":"","FREQ":7080420,
 "FROM":"HC5PH","GRID":" FI06","OFFSET":2420,"SNR":-24,"SPEED":1,
 "TDRIFT":0.24,"TEXT":"F!104 …","TO":"@SITREP","UTC":1769740328005,"_ID":-1},
 "type":"RX.ACTIVITY","value":"HC5PH: @SITREP MSG F!104 … ♢ "}
```

The rich form carries the same structured fields as `RX.DIRECTED`. JS8Link
must handle both forms; `params.FROM`/`params.TO`/`params.CMD` take
precedence over the rendered `value` when present.

### RX.DIRECTED

```json
{"params":{"CMD":" HEARTBEAT","DIAL":7078000,"EXTRA":"","FREQ":7078816,
 "FROM":"KE2DMC","GRID":"FN32","OFFSET":816,"SNR":1,"SPEED":0,
 "TDRIFT":0.54,"TEXT":"","TO":"@HB","UTC":1769740226361,"_ID":-1},
 "type":"RX.DIRECTED","value":"KE2DMC: @HB HEARTBEAT ♢ "}
```

### RX.SPOT

```json
{"params":{"CALL":"KF7MIX","DIAL":7078000,"FREQ":7078870,"GRID":"EM48",
 "OFFSET":870,"SNR":-5,"_ID":-1},
 "type":"RX.SPOT","value":""}
```

### RX.BAND_ACTIVITY (response to RX.GET_BAND_ACTIVITY)

The response `params` is an **offset-keyed dictionary**, not a list:

```json
{"params":{"1067":{"DIAL":7078000,"FREQ":7079067,"OFFSET":1067,"SNR":-7,
 "TEXT":"W6OEM: VE3SOY HEARTBEAT SNR -20 ","UTC":1768860611907},
 "616":{"DIAL":7078000,"FREQ":7078616,"OFFSET":616,"SNR":-18,
 "TEXT":"KM4BOF: VE3SOY HEARTBEAT SNR -09 ","UTC":1768860611918}},
 "type":"RX.BAND_ACTIVITY","value":""}
```

Each key (other than `_ID` and `type`) is the offset in Hz. The value is a
dict with `DIAL`, `FREQ`, `OFFSET`, `SNR`, `TEXT` and `UTC`. JS8Link's
`_band_activity_entries` helper expands this into per-offset records.

### TX.FRAME

JS8Call emits one `TX.FRAME` event per transmitted frame. A typical message
produces two frames back-to-back:

```json
{"params":{"PTT":true,"UTC":1768862879801,"_ID":-1},"type":"RIG.PTT","value":"on"}
{"params":{"TONES":[4,2,5,6,1,3,0,…],"_ID":-1},"type":"TX.FRAME","value":""}
{"params":{"PTT":false,"UTC":1768862893402,"_ID":-1},"type":"RIG.PTT","value":"off"}
{"params":{"PTT":true,"UTC":1768862894801,"_ID":-1},"type":"RIG.PTT","value":"on"}
{"params":{"TONES":[4,2,5,6,1,3,0,…],"_ID":-1},"type":"TX.FRAME","value":""}
{"params":{"PTT":false,"UTC":1768862908402,"_ID":-1},"type":"RIG.PTT","value":"off"}
```

When `value` is non-empty it contains the transmitted text. When empty, only
the `TONES` array is present. JS8Link records transmitted frames as
`TransmittedMessage` rows regardless of whether they were initiated through
the API or by JS8Call's internal automation (heartbeats, ACKs, auto-replies).

### RX.TEXT (response to RX.GET_TEXT)

```json
{"params":{},"type":"RX.TEXT","value":"\n22:06:10 - (1950) - KJ4CTD: W4CAT SNR?  ♢ \n…"}
```

Contains the JS8Call directed-message receive window contents with timestamps
and offset annotations.

### INBOX.MESSAGES (response to INBOX.GET_MESSAGES)

```json
{"params":{"MESSAGES":[{"params":{"CMD":" MSG ","DIAL":7078000,"FREQ":7080318,
 "FROM":"KJ5MIW","GRID":" EM15","OFFSET":2318,"PATH":"KJ5MIW","SNR":-15,
 "SUBMODE":0,"TDRIFT":0.14,"TEXT":"F!104 100 ST[OK] GR[EM15] #ATTV",
 "TO":"@SITREP","UTC":"2026-01-21 01:44:26","_ID":"269660742003"},
 "type":"READ","value":""}],
 "_ID":269699597005},
 "type":"INBOX.MESSAGES","value":""}
```

Each message record carries the full directed-message metadata. `PATH` shows
the relay path if the message was forwarded. `SUBMODE` is the speed code.
`type` is `"READ"` or `"UNREAD"`. `UTC` is a string timestamp.

## Field precedence and reliability

For `RX.DIRECTED` and rich `RX.ACTIVITY`, structured `params.FROM`,
`params.TO`, `params.CMD`, `params.GRID`, `params.OFFSET`, `params.SNR`,
`params.SPEED`, `params.DIAL`, `params.TDRIFT` and `params.UTC` are
preferred. The rendered `value` remains available for verification and for
protocol elements not represented separately.

For simple `RX.ACTIVITY` and entries inside `RX.BAND_ACTIVITY`, the text may
be the only source of sender, target and command semantics. A callsign may
only be assigned when it is explicit in a documented frame or a recent,
independently verified association. Missing data remains unknown; JS8Link
must not invent a sender, target, SNR or relation.

## Heartbeat semantics

Heartbeat uses two semantically different forms.

### Heartbeat beacon

```text
M0XRS: @HB HEARTBEAT IO83 ♢
```

- Sender/transmitter: `M0XRS`
- Destination: special group `@HB`
- Sender grid: `IO83`
- Meaning: M0XRS announces that it is active on the heartbeat network and
  invites stations with AUTO and heartbeat acknowledgements enabled to report
  that they heard it.
- It does **not** mean that M0XRS received a station called `@HB`.
- It creates/updates the M0XRS station record and its local reception
  metadata.
- It never creates an `@HB` station or a station-to-`@HB` relationship.

The heartbeat network normally uses offsets between 500 and 1000 Hz and only
supports **Slow**, **Normal** and **Fast** modes. JS8 40 and JS8 60 do not
participate in heartbeat networking. The heartbeat offset may be randomised
within this range to reduce QRM.

### Heartbeat acknowledgement/reception report

```text
IU2ITE: PE1PUX HEARTBEAT SNR +07 ♢
```

- Reporter and receiver: `IU2ITE`
- Heartbeat transmitter/target: `PE1PUX`
- Reported receive SNR at IU2ITE: `+07 dB`
- Meaning: IU2ITE reports that it received PE1PUX's heartbeat at +07 dB.

The SNR written inside the message belongs to the reporting station. It must
be shown and stored at that station's side of a relationship. If the JSON
event also has `params.SNR = -14`, then the local JS8Call instance received
IU2ITE's report at -14 dB. These are two independent observations:

```text
PE1PUX -- received by IU2ITE at +07 dB
IU2ITE -- received by local JS8Call at -14 dB
```

Never substitute `params.SNR` for a missing `HEARTBEAT SNR` value.

A report can advertise a waiting stored message:

```text
KN4CRD: KM4ACK HEARTBEAT SNR -12 MSG 32 ♢
```

This retains the same SNR meaning and additionally tells KM4ACK that KN4CRD
has stored message `32`, retrievable with `QUERY MSG 32`.

## Directed queries and responses

Stations with AUTO enabled can answer documented query commands.

| Command | Response type | Meaning |
|---|---|---|
| `SNR?` | `SNR -12` | What SNR do you receive me at? |
| `GRID?` | `GRID EM85` | Return your grid locator. |
| `INFO?` | `INFO text…` | Return your station information. |
| `STATUS?` | `STATUS text…` | Return your status text. |
| `HEARING?` | `HEARING CALL1 -12 CALL2 -8 …` | Return stations you currently hear. |
| `AGN?` | Retransmits last message | Retransmit your previous message. |
| `QSL?` | `QSL` | Confirm whether the previous transmission was received. |
| `HW CPY?` | Free text | Return a reception/copy report. |
| `QUERY CALL CALL?` | `YES` or `NO` | Can you communicate directly with CALL? |
| `QUERY MSGS` | Message ID list | Which messages are stored for the sender? |
| `QUERY MSG id` | Message content | Retrieve stored message by ID. |

Documented report commands are `SNR`, `GRID`, `INFO`, `STATUS` and
`HEARING`. In `SOURCE: TARGET SNR -12`, SOURCE is the reporter, TARGET is
the station it received and `-12` is the receive SNR at SOURCE.

## Store-and-forward and relay commands

| Form | Meaning |
|---|---|
| `MSG text` | Store and display an inbox message at the addressed station. |
| `MSG TO:CALL text` | Store a message at an intermediate station for CALL. |
| `QUERY MSGS` | Ask which messages are stored for the sender. |
| `QUERY MSG id` | Retrieve a stored message by ID. |
| `QUERY CALL CALL?` | Ask whether the addressed station can directly communicate with CALL. |
| `CALL>MESSAGE` | Relay the message to CALL. |
| `CALL1>CALL2>MESSAGE` | Relay through multiple next hops. |
| `>>MESSAGE` | Request ACK without storing in Inbox (redirect prefix). |

At each relay hop the originating sender's callsign is appended (`DE
ORIGINATOR`). An ACK confirms receipt where the documented flow calls for
one. JS8Link's own `~…` confirmed-delivery extension is a separate protocol
layered in the message payload; it must not be confused with native JS8 ACK
behavior.

## Short directed responses and calls

Documented one-frame short responses: `QSL`, `YES`, `NO`, `RR`, `FB`, `TU`,
`73`, `SK` and `DIT DIT`.

### CQ formats

CQ forms begin with `CQ` and may include a variant and a four-character
grid, all in one transmission frame:

| Form | Encodes grid? |
|---|---|
| `CQ` | No (implicit) |
| `CQ CQ` | No |
| `CQ CQ CQ` | Yes (with 4-char grid) |
| `CQ CONTEST` | Yes |
| `CQ FIELD` / `CQ FD` | Yes |
| `CQ QRP` | Yes |
| `CQ DX` | Yes |

When a supported CQ format with a grid is transmitted, the callsign is
automatically prefixed and the frame is sent as a directed message. Custom
CQ text (e.g. `CQ QRP 500MW CQ?`) may be appended but will not carry the
grid in the structured encoding.

## Group callsigns

Group callsigns begin with `@` and have up to 8 alphanumeric characters
(`[A-Z0-9]`) with optional `/` separators. `@HB` is reserved for heartbeat
networking; `@ALLCALL` addresses all stations; configured groups address
their members. A group token is a destination, not a physical station.

Built-in groups include continental DX groups (`@DX/NA`, `@DX/EU`, …), ITU
regions (`@REGION/1`, …), operator groups (`@COMMAND`, `@CONTROL`, `@NTS`,
`@NET`), special groups (`@JS8NET`, `@APRSIS`, `@RAGCHEW`, `@JS8`, `@CQ`,
`@HB`, `@QSO`, `@QRP`, `@QRO`, …), and application groups (`@EMCOMM`,
`@ARES`, `@MARS`, `@RACES`, `@SKYWARN`, `@CONTEST`, `@FIELDDAY`, `@SOTA`,
`@POTA`, `@IOTA`).

### @APRSIS and @JS8NET (spotting groups)

`@APRSIS GRID FN04TV53` spots the sending callsign at that grid to the
APRS-IS network. `@APRSIS CMD :SMSGTE :@5551212 TEST` forwards a raw APRS
packet. `@JS8NET` is a generic spotting gateway for custom processing.

## Mode speeds

| Name | Code | TX duration | Bandwidth | WPM | Sensitivity | Heartbeat? |
|---|---|---|---|---|---|---|
| Slow | 4 | 25.28 s | 25 Hz | 8 | -28 dB | Yes |
| Normal | 0 | 12.64 s | 50 Hz | 16 | -24 dB | Yes |
| Fast | 1 | 7.9 s | 80 Hz | 24 | -20 dB | Yes |
| JS8 40 | 2 | 3.95 s | 160 Hz | 40 | -18 dB | No |
| JS8 60 | 8 | ~3 s | 250 Hz | 60 | -16 dB | No |

`RIG.SET_FREQ` and `MODE.SET_SPEED` responses may return a `STATION.STATUS`
envelope containing `DIAL`, `FREQ`, `OFFSET`, `SELECTED` and `SPEED`.

`RX.GET_FREE_OFFSETS` accounts for the bandwidth of the selected mode
(default: current mode) and ignores activity older than 30 seconds. Optional
params `LOW` (default 500) and `HIGH` (default 2500) constrain the search
range.

## JS8Call-improved API 3.x catalogue

### Asynchronous events

| Type | Meaning |
|---|---|
| `RX.ACTIVITY` | One decoded activity fragment with receive metadata. |
| `RX.DIRECTED` | Structured directed frame/message. |
| `RX.SPOT` | Callsign spot with grid and receive metadata. |
| `RIG.PTT` | Transmitter keyed (`"on"`) or released (`"off"`). |
| `TX.FRAME` | One transmitted encoded frame/tone sequence. |
| `STATION.CLOSING` | JS8Call is shutting down (API 3.x). Contains `params.REASON`. |
| `API.ERROR` | Invalid or rejected API input. `value` contains the error. |

### Rig and station control

`PING`, `RIG.GET_FREQ`, `RIG.SET_FREQ`, `RIG.GET_PTT` (3.0+), `RIG.SET_TUNE`
(3.0+), `RIG.TX_HALT` (3.0+), `STATION.GET_CALLSIGN`, `STATION.GET_GRID`,
`STATION.SET_GRID`, `STATION.GET_INFO`, `STATION.SET_INFO`,
`STATION.GET_STATUS`, `STATION.SET_STATUS`, `STATION.VERSION` (3.0+),
`STATION.GET_OS` (3.0+), `STATION.GET_SPOT` (3.0+) and `STATION.SET_SPOT`
(3.0+).

### Receive, transmit, mode and inbox

`RX.GET_CALL_ACTIVITY`, `RX.GET_CALL_SELECTED`, `RX.GET_BAND_ACTIVITY`,
`RX.GET_TEXT`, `RX.GET_FREE_OFFSETS` (3.0+), `TX.GET_TEXT`, `TX.SET_TEXT`,
`TX.SEND_MESSAGE`, `TX.GET_QUEUE_DEPTH` (3.0+), `MODE.GET_SPEED`,
`MODE.SET_SPEED`, `INBOX.GET_MESSAGES`, `INBOX.STORE_MESSAGE` and
`WINDOW.RAISE`.

### JS8Call-improved extensions (not in base JS8Call)

JS8Call-improved adds endpoints that JS8Link uses. These are not in the
upstream API 3.0.0 reference but are present in the JS8Call-improved fork:

- `STATION.GET_CONFIG` — returns `AUTO_REPLY`, `JS8HB`, `HBACK`,
  `MULTI_DECODER`, `HB_INTERVAL`, `MONITOR`, `TX_ENABLED`, `GROUPS`,
  `AVOID_ALLCALL`.
- `RX.GET_FILTER` / `RX.SET_FILTER` / `RX.SET_FILTER_ENABLED` — remote
  bandpass filter control.
- `STATION.SET_AUTOREPLY_CONFIRMATION` — toggle auto-reply confirmation.
- `STATION.AUTOREPLY_CONFIRM_RESPONSE` — respond to an auto-reply
  confirmation request.
- `STATION.SEND_HB` — trigger an immediate heartbeat transmission.

### Response types

JS8Call responses use a corresponding noun type. Each response carries
structured `params` with the requested data.

| Type | Request | Key params | Used by JS8Link |
|---|---|---|---|
| `RIG.FREQ` | `RIG.GET_FREQ` | `DIAL` (Hz), `OFFSET` (Hz), `FREQ` (Hz) | Status display, VFO |
| `MODE.SPEED` | `MODE.GET_SPEED` | `SPEED` (0=Normal, 1=Fast, 2=Turbo, 4=Slow, 8=JS8 60) | Status display, mode selector |
| `STATION.CALLSIGN` | `STATION.GET_CALLSIGN` | `CALLSIGN` | Callsign resolution |
| `STATION.GRID` | `STATION.GET_GRID` | `GRID` (Maidenhead locator) | Status display, station grid |
| `STATION.INFO` | `STATION.GET_INFO` | `INFO` (free text) | Settings display |
| `STATION.STATUS` | `STATION.GET_STATUS` | `STATUS` (free text) | Settings display |
| `STATION.SPOT` | `STATION.GET_SPOT` | value: `"true"` or `"false"` | Spot toggle state |
| `STATION.CONFIG` | `STATION.GET_CONFIG` | `AUTO_REPLY`, `JS8HB`, `HBACK`, `MULTI_DECODER`, `HB_INTERVAL`, `MONITOR`, `TX_ENABLED`, `GROUPS`, `AVOID_ALLCALL` | JS8Call settings |
| `STATION.VERSION` | `STATION.VERSION` | `VERSION` (semver string) | Version display, compatibility |
| `STATION.OS` | `STATION.GET_OS` | `OS_NAME`, `OS_KERNEL`, `OS_KERNEL_VERSION` | Status display |
| `RX.CALL_ACTIVITY` | `RX.GET_CALL_ACTIVITY` | Per-offset entries with callsign, SNR, grid | Not currently used |
| `RX.CALL_SELECTED` | `RX.GET_CALL_SELECTED` | `CALLSIGN` | Selected call display |
| `RX.BAND_ACTIVITY` | `RX.GET_BAND_ACTIVITY` | Per-offset entries with `TEXT`, `DIAL`, `FREQ`, `OFFSET`, `SNR`, `UTC` | Band monitor (routed via `_handle_activity`) |
| `RX.TEXT` | `RX.GET_TEXT` | `TEXT` (receive window text) | Not currently used |
| `RX.FREE_OFFSETS` | `RX.GET_FREE_OFFSETS` | Per-segment entries with `START`, `END` | Not currently used (offset auto-selection potential) |
| `TX.TEXT` | `TX.GET_TEXT` | `TEXT` (transmit buffer text) | TX buffer display in settings |
| `TX.QUEUE_DEPTH` | `TX.GET_QUEUE_DEPTH` | `DEPTH` (integer count) | TX queue display |
| `INBOX.MESSAGES` | `INBOX.GET_MESSAGES` | `MESSAGES` (array of `{CMD, FROM, GRID, PATH, SNR, SUBMODE, TEXT, TO, UTC}`) | Inbox sync |
| `INBOX.MESSAGE` | `INBOX.STORE_MESSAGE` | `ID` (stored message id) | Inbox store confirmation |
| `RIG.PTT_STATUS` | `RIG.GET_PTT` | `PTT` (boolean) | PTT state |

### JS8Call-improved extensions (not in base JS8Call)

## Three-layer diagnostic contract

Every boundary crossing is represented by:

1. **Raw data** — the complete redacted JSON envelope, HTTP body, WebSocket
   envelope, user action or automatic-task input.
2. **Interpretation** — a protocol-specific sentence that identifies actor,
   destination, command, reported value and the distinction between on-air
   payload data and local receive metadata.
3. **Processing** — concrete decisions and effects: classified kind, stale
   rejection, deduplication, database table update, station/link update,
   broadcast, API command or skipped action.

For a band-activity snapshot, each contained offset entry receives its own
semantic processing step. Unknown or undocumented data is retained as such;
the diagnostic layer must never present an inference as a protocol fact.

### Deduplication contract

JS8Call-improved can expose the same over-the-air decode through multiple
API event types — `RX.ACTIVITY` and `RX.DIRECTED` for the same frame, and
repeated `RX.BAND_ACTIVITY` snapshots for the same entry. JS8Link identifies
duplicates by normalized text, sender (either `callsign` or `from_callsign`
column), radio timestamp (±2 seconds), offset (match or NULL), SNR (match or
NULL) and, for heartbeats, the `is_heartbeat` flag.

When a duplicate is found, the richer representation (typically
`RX.DIRECTED` with `from_callsign`/`to_callsign`) is kept and the duplicate
merged. Timestamps must be timezone-aware UTC when passed to the dedup
function; naive timestamps are incorrectly interpreted as local time by
Python's `astimezone()`.

## Implementation ownership

- Semantic parsing: `backend/src/js8link/domain/js8_protocol.py`
- Monitor extraction and deduplication: `backend/src/js8link/domain/monitor.py`
- Persistence and diagnostic processing: `backend/src/js8link/app.py`

Alternative frontends should consume backend classifications and relationship
directions rather than reimplementing this protocol in TypeScript.
