# Arch Rogue Multiplayer — Player Guide, Operations, and Protocol Specification

Applies to game release **4.7.0** (wire protocol version **1**). Covers the
player-facing co-op flow, running the relay server, the client/server
architecture, and the complete technical specification of the wire protocol.

The canonical protocol implementation is the stdlib-only package
[`src/arch_rogue_protocol/wire.py`](../src/arch_rogue_protocol/wire.py). The
game client consumes it through the facade `arch_rogue.net.protocol`; the
standalone server consumes the same package via a local path dependency.
**Where this document and that module disagree, the module wins.**

---

## 1. Overview

Arch Rogue co-op is a two-player descent: a **host** and a **joiner** share
one dungeon. The host runs the only authoritative simulation; the joiner
renders replicated state and sends input intents. A standalone, ephemeral
**relay server** pairs the two clients by a short run code and forwards their
traffic — it never simulates, persists, or inspects game state beyond routing.

```
host client  ── TLS ──►  relay server  ◄── TLS ──  joiner client
(simulates)             (pairs + forwards)          (renders + intends)
```

Components:

| Piece | Location | Role |
|---|---|---|
| Wire protocol | `src/arch_rogue_protocol/` | Framing, codec, validation, builders, shared constants |
| Client transport | `src/arch_rogue/net/client.py` | `MultiplayerClient`: one TCP/TLS connection, one worker thread |
| Client integration | `src/arch_rogue/net/mixin.py` | `NetMixin`: session state machine, driven once per frame from `Game.run()` |
| World replication | `src/arch_rogue/net/sync.py` | Floor descriptor + snapshot payload build/apply |
| Relay server | `server/` | `python -m server.server`; asyncio, in-memory rooms, stdlib only |

Both sides of a pair must run the same game release: the hello carries
`content_revision` (the game version string) and the server rejects a joiner
whose revision differs from the host's (`bad_revision`).

---

## 2. Playing co-op

### 2.1 Setup

Multiplayer needs a configured server endpoint (Options → Multiplayer):

- **Server host** — default `ar.rita-kasari.fi`
- **Server port** — default `43666`
- **Server encryption** — default **On (certificate verified)**. TLS with full
  certificate-chain and hostname verification against the platform trust
  store. Turn it off only for a plaintext relay you run yourself (LAN,
  loopback).

Your **name** (asked on first entry, kept between sessions) is shown in the
lobby and over your head in the dungeon (max 16 characters, control
characters stripped).

Before the first connection to a server each session, a **consent screen**
("A Word Before the Gate") states that the game is a hobby project used at
your own risk, names the exact endpoint about to be contacted, describes the
encryption state (TLS-verified, or a plaintext warning), and points to the
project repository. Agreeing is remembered for that endpoint until the game
is closed or the endpoint changes; Exit returns to the multiplayer menu
without opening a socket.

### 2.2 Hosting

*Two will descend* → **Host a new run** → the game draws a 4-character **run
code** (alphabet `ABCDEFGHJKLMNPQRSTUVWXYZ23456789` — no 0/O/1/I, safe to
read aloud). Share the code out-of-band, then *Begin descent* to open the
lobby.

**The code is a locator, not a secret.** When someone enters it, the host
lobby shows a knock: *"NAME knocks at the gate."* The host must decide:

- **Enter** — admit them; the lobby proceeds to archetype binding.
- **D** — turn them away. The joiner is disconnected with *"The host turned
  you away"*, and the same code stays open for another knock.

The host cannot ready up while a knock is unanswered, so a run can never
start with an unvetted partner. Admit only the name you shared the code with
— names are self-chosen and not authentication.

### 2.3 Joining

*Two will descend* → **Join a run** → type the code. After the host admits
you, both players pick any archetype (duplicates allowed) and press Enter to
ready. When both stand ready the server issues the start and both clients
enter the same floor.

### 2.4 In the dungeon

- The **host simulates everything**: enemies, damage, loot, traps, story.
  The joiner's client sends movement and action intents; the host validates
  cooldowns, stamina, range, and ownership before anything happens.
- Loot, gold, XP, inventory, and disciplines are **per-player**; pickups are
  first-claim, host-validated.
- **Stairs** require every living player within range to descend.
- **No revive**: a fallen player spectates; the run ends when no player is
  alive. Victory and death screens show both players' results.
- Either player's Time Skip slows the shared enemy simulation.
- Story dialogue, relic choices, and shops are host-controlled; the joiner
  sees resolved outcomes.

### 2.5 Disconnects

An unexpected socket loss holds the run for **30 seconds** on both sides.
The dropped client retries automatically (0.5 s → 4 s backoff) using its
128-bit reconnect token; on success a rejoined joiner receives a fresh floor
descriptor and snapshot before input re-enables. If the grace expires, the
partner is gone for good (`partner_left`) and the survivor returns to the
title with a notice. Leaving via menu/quit sends a graceful `bye` — no grace
window, the run ends immediately for the partner. On Android, suspending the
app pauses outbound traffic while holding the socket; resume reconnects if
the socket died meanwhile.

---

## 3. Running a server

The relay is stdlib-only and runs on bare `python3` (≥ 3.11) from a repo
checkout:

```bash
python -m server.server                  # 0.0.0.0:43666, plain TCP
arch-rogue-server                        # same, if installed (pip install -e server/)
```

Configuration — CLI flags override environment variables override defaults:

| Flag | Env var | Default | Meaning |
|---|---|---|---|
| `--host` | `ARCH_ROGUE_MP_HOST` | `0.0.0.0` | Bind address |
| `--port` | `ARCH_ROGUE_MP_PORT` | `43666` | Bind port (0 = ephemeral) |
| `--run-id-length` | `ARCH_ROGUE_MP_RUN_ID_LENGTH` | `4` | Accepted code length (1–32) |
| `--hello-timeout` | `ARCH_ROGUE_MP_HELLO_TIMEOUT` | `10` s | Connect→hello deadline |
| `--reconnect-grace` | `ARCH_ROGUE_MP_RECONNECT_GRACE` | `30` s | Seat reservation after socket loss |
| `--idle-timeout` | `ARCH_ROGUE_MP_IDLE_TIMEOUT` | `600` s | Room closes after inactivity |
| `--max-rooms` | `ARCH_ROGUE_MP_MAX_ROOMS` | `128` | Concurrent room cap |
| `--log-level` | `ARCH_ROGUE_MP_LOG_LEVEL` | `INFO` | Python logging level |
| `--tls-cert` | `ARCH_ROGUE_MP_TLS_CERT` | *(empty)* | PEM chain for direct TLS termination |
| `--tls-key` | `ARCH_ROGUE_MP_TLS_KEY` | *(empty)* | PEM key (must accompany `--tls-cert`) |

The server stores nothing: rooms live in memory and evaporate when both
clients disconnect or the idle timeout fires. There is no database, no
logging of game state, and nothing to back up.

### 3.1 TLS deployment

Two supported shapes:

**A. Reverse proxy terminates TLS.** The relay listens plaintext on
loopback; nginx's `stream` module terminates TLS on the public port:

```nginx
stream {
    server {
        listen 43666 ssl;
        ssl_certificate     /etc/letsencrypt/live/example/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/example/privkey.pem;
        proxy_pass 127.0.0.1:43667;         # relay: --host 127.0.0.1 --port 43667
    }
}
```

**B. Direct termination** — pass `--tls-cert`/`--tls-key`; the relay serves
TLS 1.2+ itself. Useful without a proxy.

Clients verify the certificate chain **and hostname**, so players must enter
the server by the DNS name on the certificate (or an IP listed as a SAN).

### 3.2 Hardening an Internet-facing relay

- **Rate-limit connection attempts per IP.** A 4-character code is ~20 bits;
  guessing is only made irrelevant by attempt-rate limits plus the host
  accept gate. Note nginx's `stream` module has `limit_conn` (concurrency)
  but **no** `limit_req` — use an nftables/iptables `hashlimit` rule on new
  connections to the port, fail2ban on the relay's `run_not_found` log
  lines, or both.
- Optionally raise `--run-id-length` — but the **client generates and
  validates codes at the shared constant `MP_RUN_ID_LENGTH` (4)**, so a
  longer server setting rejects stock clients. Changing code length is a
  coordinated protocol change, not a deployment flag.
- Every failed guess costs the attacker (and you) a full TLS handshake;
  handshake flood is the same availability concern as any TLS service.
- `--max-rooms` bounds memory; the hello timeout drops silent connections.

---

## 4. Architecture

### 4.1 Authority model

The host is the sole simulator. The joiner never runs AI, combat, RNG, or
loot logic; it renders the latest authoritative snapshot, advances purely
cosmetic motion (projectile flight, animation clocks, actor smoothing), and
sends inputs. On the host, the remote player's actor is simulated through
the *same* code paths as the local player (`acting_as_player` context), so
cooldowns, stamina costs, pickup claims, and upgrade rules are enforced
server-of-record-side regardless of what a modified client sends.

### 4.2 Client transport (`MultiplayerClient`)

One client object owns one connection lifecycle:

- A single background thread connects (and performs the TLS handshake in
  blocking mode under the 6 s connect timeout), then multiplexes reads and
  queued writes with `select` on the non-blocking socket. A socketpair wakes
  the selector immediately when the main thread queues a message.
- The thread only decodes and enqueues immutable typed messages
  (`net/messages.py`); all game-state mutation happens on the main thread in
  `NetMixin.poll()`, called once per frame.
- **Queue bounds:** inbound 512 events (consecutive snapshots coalesce to
  the newest); outbound 256 payloads (movement intents and host snapshots
  coalesce by key). Overflow ends the connection rather than growing
  unbounded.
- Every event carries the client's **connection generation**; events from a
  superseded reconnect attempt are ignored by the consumer.
- TLS specifics: `SSLWantRead/WantWrite` are retried like `EWOULDBLOCK`, and
  after each read the loop drains `SSLSocket.pending()` — decrypted records
  buffered inside OpenSSL are invisible to `select` on the raw fd.

### 4.3 World replication (`net/sync.py`)

Two payload kinds flow host → joiner, both opaque to the server:

- **Floor descriptor** (`floor` message, once per floor / rejoin /
  partner-rejoin): the complete static floor — dungeon tiles, enemies with
  stable `entity_id`s, items, story state — plus full per-player dictionaries.
  The joiner rebuilds its world through the same code path as loading a save,
  with its own actor as the primary.
- **Snapshots** (`snapshot` messages at 15 Hz): the fast-changing subset —
  compact player/enemy/projectile positions, recent floaters, tile patches
  (diffs against the floor baseline), boss engagement, pause reason, depth,
  elapsed time, and first-seen enemy spawn records. Every 5th tick (or
  immediately when any world-list length changes) the snapshot also carries a
  `slow` section: full player dicts, items, traps, shrines, secrets,
  familiars, shop state.

The joiner eases actors toward snapshot positions (distant corrections snap,
small ones lerp) so 15 Hz reads as motion; projectiles fly ballistically
between snapshots; collision damage remains exclusively host business.

### 4.4 Joiner input

At 20 Hz the joiner samples movement (keyboard / controller / touch / mouse
hold-to-walk) into a unit-clamped vector and sends a move intent (coalesced —
only the newest queued vector survives). One-shot actions (attack, dash,
potion, interact, slot use, discipline choice) are sent immediately and never
coalesced; each carries the aim vector in `move_x/move_y`. The host times out
stale movement 0.6 s after the last intent so a silent joiner stops walking.

---

## 5. Wire protocol specification (version 1)

### 5.1 Transport and framing

- **Transport:** TCP, optionally wrapped in TLS (client default: TLS on,
  minimum version 1.2, certificate chain + hostname verification required).
  The protocol layer is identical either way.
- **Framing:** newline-delimited JSON. One message = one UTF-8 encoded JSON
  object terminated by `\n` (LF). `\r` adjacent to the terminator is
  tolerated on receipt. Blank lines are ignored.
- **Size limit:** an encoded line, including its terminator, must not exceed
  `MP_MAX_MESSAGE_BYTES` = **262 144 bytes (256 KiB)**. Receivers must drop
  the connection of a peer whose line (or unterminated partial line) exceeds
  the limit; the reference `LineFramer` clears its buffer and raises so no
  peer can grow receive buffers without bound.

### 5.2 Encoding rules

- Payloads are JSON **objects**; any other top-level type is a protocol error.
- Every message carries `"t"`: a non-empty string message type.
- `NaN`, `Infinity`, and `-Infinity` are **forbidden** in both directions
  (encoders use `allow_nan=False`; decoders reject the tokens).
- Encoding is compact (no whitespace) with `ensure_ascii=False`; decoders
  must accept any valid JSON spacing.
- Unknown *fields* in a known message are ignored. Unknown *types* are
  tolerated for forward compatibility: the server logs and ignores them
  (with an escalating counter), the client maps them to an ignored
  `UnknownMessage`.

### 5.3 Versioning and compatibility

- `protocol_version` (integer, currently **1**) is carried in `hello`. A
  mismatch is rejected fatally with `bad_version` before any pairing.
- `content_revision` (string; the game sends its release version, e.g.
  `"4.7.0"`) is fixed by the host at room creation; a joiner with a
  different revision is rejected with `bad_revision`. This intentionally
  fences off cross-version pairs even within one protocol version.
- Additive message types (e.g. `kick`, added in 4.7.0) do not bump
  `protocol_version`: peers that don't know a type ignore it gracefully.

### 5.4 Identity, codes, and secrets

| Thing | Spec |
|---|---|
| Run id (room code) | `MP_RUN_ID_LENGTH` = 4 chars from `ABCDEFGHJKLMNPQRSTUVWXYZ23456789` (32 symbols, ~20 bits). Case-insensitive on entry (normalized to upper). Generated client-side with `secrets.choice`, never the game RNG. Max accepted length 32. **A locator, not authentication.** |
| Player id | Server-assigned: host = `"p1"`, joiner = `"p2"`. Stable for the room's lifetime and used to stamp relayed intents. |
| Player name | Free text, sanitized on every boundary: control characters and non-printables stripped, whitespace collapsed, capped at `MP_PLAYER_NAME_MAX_CHARS` = 16. Self-chosen; never treat as identity. |
| Reconnect token | Server-generated `secrets.token_hex(16)` (128 bits), issued in `welcome`, bound to one room seat. Presenting it in a later `hello` reclaims the seat during the grace window. Compared with `hmac.compare_digest`. Sent only over the (ideally TLS) transport; never persisted by either side. |
| Run seed | Host-generated `secrets.randbits(63)` sent in the host's `ready`; the server echoes it in `start` so both clients seed identical floor generation. |

### 5.5 Sequence numbers

- `seq` on client control messages (`hello`, `ready`, `kick`, `ping`) is a
  per-connection positive integer that must be **strictly monotonic**. The
  server rejects a non-increasing `seq` with a non-fatal `bad_msg`. The
  `hello` seq initializes the counter for the connection.
- `input_seq` on `intent` is a separate joiner-side counter; the host drops
  any intent whose `input_seq` is ≤ the highest seen (stale input).
- Server-initiated events carry no `seq`. Replies echo the request's `seq`
  where one exists (`welcome`, `pong`, `error`).
- `floor_revision`/`tick` order world payloads: the joiner ignores snapshots
  whose `(floor_revision, tick)` is not strictly newer than the last applied
  one, and ignores snapshots for floors it has not applied.

### 5.6 Connection lifecycle

```
TCP connect (+ TLS handshake)
   │
   ▼
client sends hello ──────────────► server validates within 10 s
   │                                 │ bad → error{fatal} + close
   ▼                                 ▼ good
client receives welcome         seat bound (room created or joined)
   │                                 │ (join: host receives partner_joined)
   ▼                                 ▼
        ...lobby / active phase (below)...
   │
   ▼
either side sends bye  (graceful; no grace window; partner gets partner_left)
or the socket dies     (30 s reconnect grace; see §5.9)
```

The **first** message on a connection must be `hello`; anything else is a
fatal `bad_msg`. A connection that has not completed hello within
`hello_timeout` (10 s) is dropped with a fatal `timeout`.

### 5.7 Session flow (happy path)

```
HOST                        SERVER                        JOINER
hello{role:host,run_id} ──►
                       ◄── welcome{you_are:host,p1,token}
                                          ◄────── hello{role:join,run_id}
        ◄── partner_joined{name,p2}
                       welcome{you_are:join,p2,token,partner_name} ──►

   [host UI: accept gate — admit (no message) or kick (§5.10)]

ready{archetype,run_seed} ─►
                            ├─ ready_ack{p1,archetype} ──►
                                          ◄────────── ready{archetype}
        ◄── ready_ack{p2,archetype}
                            │  both ready & connected:
        ◄── start{run_seed,ids,names,archetypes} ──►

floor{revision,depth,seed,state} ──► (relayed verbatim) ──►
snapshot{revision,tick,state} ──► (relayed, coalesced) ──►   [15 Hz]
                                          ◄── intent{input_seq,move,action}  [20 Hz]
ping{seq,ts} ◄──────────────┼──────────────► ping{seq,ts}    [every 5 s]
        ◄── pong{seq,ts}    │    pong{seq,ts} ──►
run_ended{outcome,results} ─►  (relayed) ──►
bye ───────────────────────►   partner_left ──►
```

Notes:

- Ready order is race-free: whichever side readies first waits; `start` is
  emitted only when both seats are ready **and** connected. Only the host's
  `ready` may carry `run_seed` (required for start).
- `ready_ack` events pushed to the partner carry no `seq`.
- The room retains the **latest** `floor` and `snapshot` verbatim for
  reconnect replay; it never parses their `state`.

### 5.8 Room state machine (server)

```
waiting_for_join ──joiner hello──► selecting ──both ready──► active
      ▲                               │                        │
      └────── joiner leaves/kicked ───┘                        │
                                                               │
   closed ◄── host leaves for good / idle timeout / both gone ─┘
```

- `waiting_for_join`: host seat bound, join seat empty. Joining requires
  exactly this state with one occupied seat.
- `selecting`: both seats bound; archetype/ready exchange (and the host
  accept gate) happen here. `ready` is accepted in `waiting_for_join` and
  `selecting` only (`bad_state` otherwise, non-fatal).
- `active`: started. Set `started=True`; world traffic flows.
- `closed`: terminal. Host departure closes the room outright (a room cannot
  outlive its sole simulator); a joiner departing **before start** frees the
  seat and returns the room to `waiting_for_join`.
- Any room inactive for `idle_timeout` (600 s) is closed after a fatal
  `timeout` error to both live peers. Every accepted message touches the
  activity clock.

### 5.9 Reconnect protocol

When a socket dies unexpectedly (no `bye`):

- **Server:** the seat keeps its `reconnect_token` and enters a *reserved*
  state for `reconnect_grace` (30 s). The partner is told
  `partner_disconnected{grace_seconds}`. If the grace expires, the departure
  is finalized: `partner_left`, seat released (pre-start joiner: room
  reopens; host: room closes).
- **Client:** enters a reconnect loop until its own 30 s deadline: new TCP/TLS
  connection, `hello` with the original `run_id`, `role`, and
  `reconnect_token`, backoff 0.5 s doubling to a 4 s cap. Each attempt bumps
  the connection generation so stale events are discarded.
- **On token match** (constant-time compare; seat not `left`): any zombie
  socket still bound to the seat is closed — the token holder is
  authoritative. The seat rebinds, the partner gets
  `partner_rejoined{name, player_id}`, and — if the run has started and the
  rejoiner is the joiner — the server replays the retained `floor` then the
  latest `snapshot` so it renders fresh authoritative data before input
  re-enables. A host rejoining pushes a fresh `floor` itself.
- **On failure** (room gone, token mismatch, seat finalized): the hello is
  processed as a normal join attempt and typically fails `run_not_found` —
  the client gives up and returns to the title with a notice.

### 5.10 Lobby accept gate and kick (4.7.0)

`partner_joined` puts the **host client** into a pending-accept state: the
host cannot send `ready` until the knock is answered (client-enforced; the
server additionally resets host readiness on every kick as defense against
modified clients).

- **Admit** is a client-local decision — no wire message.
- **Turn away** sends `kick{seq}` (host-only). Server handling: valid only
  pre-start in `selecting` with a join seat present (`bad_state` otherwise,
  non-fatal). The joiner is removed with a fatal `error{code:"kicked"}` —
  this also cancels a reconnect-grace reservation, killing the token — the
  host receives the standard `partner_left`, and the room returns to
  `waiting_for_join` on the same code.

### 5.11 Timers, rates, and limits (normative constants)

| Constant | Value | Meaning |
|---|---|---|
| `MP_PROTOCOL_VERSION` | 1 | Hello version gate |
| `MP_MAX_MESSAGE_BYTES` | 262 144 | Line size cap, both directions |
| `MP_RUN_ID_LENGTH` / max | 4 / 32 | Generated / accepted code length |
| `MP_PLAYER_NAME_MAX_CHARS` | 16 | Name cap after sanitation |
| `MP_HELLO_TIMEOUT_SECONDS` | 10 | Connect → hello deadline |
| `MP_RECONNECT_GRACE_SECONDS` | 30 | Seat reservation + client retry window |
| `MP_ROOM_IDLE_TIMEOUT_SECONDS` | 600 | Room inactivity close |
| `MP_SNAPSHOT_RATE_HZ` | 15 | Host snapshot emission |
| `MP_INTENT_RATE_HZ` | 20 | Joiner movement-intent emission |
| Ping interval | 5 s | Both clients; RTT measured via `pong` |
| Intent move timeout | 0.6 s | Host zeroes remote movement after silence |
| Slow-payload cadence | every 5th snapshot | Or immediately on world-list length change |
| Client inbound queue | 512 events | Snapshots coalesce; overflow = disconnect |
| Client outbound queue | 256 payloads | Keyed coalescing; overflow = send refused |
| Server outbound queue | 256 messages/peer | Snapshot coalescing; overflow drops the peer |
| Client connect timeout | 6 s | TCP + TLS handshake budget |
| Reconnect backoff | 0.5 s → 4 s cap | Doubling per failed attempt |

### 5.12 Message catalog

Direction key: **C→S** client to server, **S→C** server to client. "Relayed"
messages are forwarded verbatim to the partner (the server reads only the
envelope fields it needs).

#### Client → server

| `t` | Fields | Sender | Notes |
|---|---|---|---|
| `hello` | `seq` (pos int), `protocol_version` (int), `content_revision` (str), `name` (str), `run_id` (str), `role` (`"host"`\|`"join"`), `reconnect_token`? (str) | both | Must be first. Creates the room (host) or claims the join seat / reclaims by token. |
| `ready` | `seq`, `archetype_key` (non-empty str), `run_seed`? (non-neg int) | both | Lobby only. Host **must** include `run_seed`; a joiner sending one is rejected `role_forbidden`. Partner is notified via `ready_ack`. |
| `kick` | `seq` | host | Turn away the lobby joiner. Pre-start only. |
| `floor` | `floor_revision` (non-neg int), `depth` (pos int), `floor_seed` (non-neg int), `state` (object) | host | Relayed. Retained (latest) for rejoin replay. |
| `snapshot` | `floor_revision`, `tick` (non-neg ints), `state` (object) | host | Relayed with snapshot coalescing. Retained (latest). |
| `intent` | `input_seq` (non-neg int), `move_x`, `move_y` (finite, clamped to [-1, 1]), `action` (enum, may be `""`), `target`? (str\|null) | joiner | Relayed to the host stamped with the sender's `player_id`; the server re-clamps `move_x`/`move_y` on relay. |
| `run_ended` | `outcome` (str), `results` (list of objects) | host | Relayed. Result entries: `player_id`, `name`, `class_name`, `level`, `alive`. |
| `ping` | `seq`, `ts` (float, sender-local monotonic) | both | Server answers `pong` echoing both. |
| `bye` | — | both | Graceful leave. No reconnect grace. Partner gets `partner_left`. |

`action` enum (`INTENT_ACTIONS`): `""` (movement-only), `melee`, `bolt`,
`skill`, `dash`, `potion_hp`, `potion_mana`, `interact`, `use_slot`,
`drop_slot`, `choose_discipline`. `use_slot`/`drop_slot` carry the inventory
slot index in `target`; `choose_discipline` carries the discipline node key;
`interact` targets the nearest host-validated interactable. An action
intent's `move_x/move_y` carry the **aim vector**, not movement.

#### Server → client

| `t` | Fields | Recipient | Notes |
|---|---|---|---|
| `welcome` | `seq` (echoes hello), `run_id`, `you_are` (role), `player_id`, `partner_ready` (bool), `reconnect_token`, `partner_name`? | both | Seat bound. Fresh session or successful token reclaim. |
| `partner_joined` | `name`, `player_id` | host | A joiner claimed the seat. Triggers the accept gate. |
| `ready_ack` | `player_id`, `archetype_key` (no `seq`) | partner | The other seat readied. |
| `start` | `run_seed`, `host_player_id`, `host_name`, `host_archetype`, `joiner_player_id`, `joiner_name`, `joiner_archetype` | both | Both ready and connected. Enter the run. |
| `floor` / `snapshot` / `intent` / `run_ended` | as sent | partner | Relayed world traffic (see C→S). |
| `partner_disconnected` | `grace_seconds` (float) | survivor | Partner socket died; grace running. |
| `partner_rejoined` | `name`, `player_id` | survivor | Token reclaim succeeded. |
| `partner_left` | — | survivor | Departure is final (bye, grace expiry, kick, or pre-start leave). |
| `pong` | `seq`, `ts` (echoed) | pinger | RTT probe answer. |
| `error` | `code`, `msg`, `fatal` (bool), `seq`? | offender | See §5.13. `fatal:true` precedes connection close. |
| `bye` | — | both | Server-initiated close (rare; clients treat like `partner_left`). |

#### World-state payloads (`floor.state`, `snapshot.state`)

These objects are **client-defined and server-opaque** — the relay forwards
and retains them without parsing. Their shape is an implementation contract
between same-revision clients (which is why `content_revision` gates
pairing), summarized here non-normatively:

- `floor.state`: the full run-state dictionary (same schema as a save file)
  minus the singular `player`, plus: `players` (full per-player dicts),
  `enemies` (full dicts + stable `entity_id`), `story_intro_pending:false`,
  `active_cutscene:null`, `revealed_tiles:[]` (the joiner builds its own
  fog-of-war).
- `snapshot.state` (fast, every tick): `players` (compact: position, facing,
  motion, hp/mana/stamina, timers, `name`, class), `enemies` (compact, alive
  only), `projectiles`, `floaters` (last 10), `tile_patches` (diffs against
  the floor baseline), `boss.engaged`, `paused` (host pause reason), `depth`,
  `elapsed`, `spawns`? (full dicts for first-seen enemies).
- `snapshot.state.slow` (every 5th tick or on list-length change): full
  `players`, `items`, `traps`, `shrines`, `secrets`, `familiars`, `shop_met`.

### 5.13 Error codes

| Code | Fatal? | Meaning |
|---|---|---|
| `run_id_in_use` | fatal | Hosting with a code that already has a room. |
| `run_not_found` | fatal | Joining a code with no waiting room (also failed reconnects). |
| `run_full` | fatal | Room not open for joining / seat taken. |
| `bad_revision` | fatal | Joiner's `content_revision` ≠ host's. |
| `bad_version` | fatal | `protocol_version` mismatch. |
| `bad_msg` | varies | Structural/seq violation. Fatal pre-hello or on framing violations; non-fatal for an in-room invalid message. |
| `bad_state` | varies | Message not valid in the current room state (fatal only when the room is closed). |
| `role_forbidden` | non-fatal | Host-only/join-only routing violation. |
| `timeout` | fatal | Hello deadline or room idle timeout. |
| `kicked` | fatal | The host turned the joiner away (4.7.0). |

Client UX mapping: fatal errors during setup/lobby return to the appropriate
setup step with a human-readable notice (`kicked`, `run_not_found`,
`run_full`, `bad_revision` reopen the code entry; `run_id_in_use` redraws a
host code). Non-fatal in-run errors are diagnostics and ignored.

### 5.14 Security model

Trust boundaries and the defenses at each:

- **Network ↔ client:** TLS by default with chain + hostname verification
  (TLS 1.2+). Trust anchors come from the platform store, falling back to
  `certifi` where the platform has none (Android APK bundles it); with no
  anchors the client fails closed. `ConnectionUp` fires only after an
  authenticated handshake. Plaintext is an explicit per-user opt-out for
  self-hosted relays.
- **Relay ↔ clients:** the relay is trusted for routing and lobby metadata
  integrity, not for content: clients re-sanitize every inbound string at
  ingestion (names via `sanitize_player_name`; ids/codes printable-only and
  length-capped; error text capped) so even a hostile relay cannot inject
  control characters, bidi overrides, or unbounded strings into the UI. The
  relay sees relayed game payloads in cleartext (TLS terminates at the
  server boundary); there is no player-to-player end-to-end encryption.
- **Peer ↔ peer:** the partner's client is untrusted. The host enforces all
  gameplay rules on remote intents (clamped movement, whitelisted actions,
  same cooldown/stamina/ownership code as local input) and remote-intent
  application is bounded (32-action queue, 0.6 s movement timeout). The
  joiner treats host world data as untrusted *structurally*: malformed floor
  or snapshot payloads end the session cleanly instead of crashing; message
  size caps, JSON constraints, and bounded queues limit resource abuse. A
  hostile host can at worst spoil the run it is hosting — Python clients
  have no memory-unsafe parse path.
- **Lobby access:** run codes are locators; the accept gate (§5.10) makes
  admission an explicit host decision, and server-side attempt rate limiting
  (§3.2) makes guessing uneconomical. Names shown at the gate are
  self-chosen — social verification (out-of-band code sharing) is the
  authentication.
- **Secrets:** reconnect tokens and run seeds come from `secrets`, never the
  game RNG; tokens are compared constant-time and die with the seat (kick,
  grace expiry, or room close).

---

## 6. Testing

- `tests/test_net_protocol.py` — codec, framing, validation, run ids.
- `tests/test_server_room.py` — room lifecycle on a fake clock.
- `tests/test_mp_flow.py` — the integration surface: an in-process asyncio
  relay on a loopback port (`LoopbackServer`), raw client pairs, two full
  headless `Game` instances completing the lobby→start→snapshot→intent→leave
  flow, TLS end-to-end (self-signed cert via the `openssl` CLI) including
  wrong-trust and wrong-transport pairings, the host accept/kick flow,
  hostile-payload handling, joiner mouse-walk sampling, and mobile-mode
  touch/suspend behavior. Loopback test games set `mp_server_tls = False`
  (the in-process relay speaks plain TCP).

Run everything: `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python -m unittest discover tests`.
