# Fighter Ace ground-war (PvE / EvP) protocol — reconstructed reference

Sources: live-server client logs `C:\games\FA\messages01–04.log` (2009 sessions vs. the
original master/game servers, protocol 119) cross-checked against FA.exe static analysis
(base 0x400000, no ASLR). The 2009 logs are ground truth: they show the *real* server's
message flow, which the emulator must reproduce.

Dispatch table: inbound handler pointer = `*(0xc81ed8 + msgid*4)`. Host-only handlers are
registered in `FUN_004f1240`; normal-client handlers in `FUN_004f1490`. A slot holding 0
means the client has NO inbound handler for that id (echoing such an id → the client logs
`NET::MESSAGE with Unknown Type N`).

## The destroy loop, as seen on the wire (messages04, 01:45:41–42)

A player strafes/bombs scenery. Per target destroyed:

```
out 28'15    client → server : HIT REGISTRATION (impacts on a network object)
out 31'97    client → server : GROUND-OBJECT DAMAGE REPORT (raw scenery-piece damage)
in  36'8     server → client : SCENE DESTROY / STATE  (authoritative)  ← THE ANSWER
in  33'14    server → client : ScoreEvent (Number, MEC, EEC)
out 25'7     client → server : ack/refresh request
EVENT "You have destroyed GER Birchwood/House"  + Score
```

Map-wide capture/ownership changes stream separately:

```
in  30'5 … 30'241   server → client : SCENE-STATE stream (ownership/animation, per-scene)
in  40'38           server → client : periodic ground-war push, fixed 38 B, ~every 60 s
```

Key correction to earlier guesses: **msg 60 is NOT flak damage.** msg 59'19 → 60'8 is
*exclusively* the spawn resource-supply negotiation ("Ask resources from AI" → "Insufficient
aircraft units … taking from tank production"). It fires only at plane creation. `0x5581c0`
applies that supply result to the new plane (hence it touches the plane state words).

## Message reference (confirmed formats)

### msg 28 (0x1c) — HIT REGISTRATION  [client→server, out]
Handler `LAB_004f3810`. Outer records, each:
`[shooter ONumber s16 LE][target ONumber s16 LE][subCount u8]`
then `subCount` × 9-byte sub-records `[type u8][a u8][b u8][id u16][val dword]` resolved
against the target object via `FUN_004c21a0`. Length = 6 + 9·subCount per record — observed
15 (1 sub), 24 (2), 33 (3) … 96. This is bullet/bomb impact resolution on **network
objects** (planes and ground). EvP (flak hitting YOU) most plausibly arrives here with your
own plane's ONumber as target — NOT via msg 60. To verify next test: capture an `in 28'…`
whose target ONumber == the local plane's Number.

### msg 31 (0x1f) — GROUND-OBJECT DAMAGE REPORT  [client→server, out only]
No client inbound handler (slot 0xc81f54 = 0; NEVER echo/relay). v199 consumes it. Records
are 6 bytes (older interpretation: `[attacker ONumber u16][obj idx u8][ev u8][dmg u16]`).
Objects here are individual destructible pieces inside a scene (idx seen 129/130/376),
a LARGER namespace than the 0–59 scene indices. Live lengths: 7,19,25,79,97.

### msg 36 (0x24) — SCENE DESTROY / STATE  [server→client, in]  ← primary PvE answer
Handler `LAB_004f9d90`. Wire: `[0x24]` then N × 7-byte records:
```
word[+0]  sceneIdx u16 LE   (bounds-checked < DAT_00c87274, indexes scene table DAT_00c87270)
byte[+2]  camp/owner u8     (0xFF → "neutralized/destroyed", cockpit string 0xCB;
                             else camp string 0x81 via FUN_0044e550)
f32 [+3]  progress/health   (≤ threshold @0xa23210 → scene captured: store +0x54/+0x58,
                             bump captured-counter +0x7c)
```
`in 36'8` = 1 record (1 header byte + 7). This is what the real server sends to make the
client print "You have destroyed …". Count derived from length: N = (len-1)/7.

### msg 30 (0x1e) — SCENE-STATE STREAM  [server→client, in]
Handler `LAB_004f6880`. Variable records. Each entry begins with a u16; **bit 15 (0x8000)**
= "has param":
- set  → 4-byte `[sceneIdx|0x8000][param u16]` → `FUN_00568eb0(1, param, 0)`
- clear→ 2-byte `[sceneIdx]`               → `FUN_00568eb0(0, 0, 0)`  (reset/clear)
Drives per-scene ownership/animation. `in 30'5` = one 2-byte reset; big batches (149/177/
241) follow a base flip.

### msg 40 (0x28) — periodic ground-war push  [server→client, in]  fixed 38 B, ~60 s
Host handler at 0x4f6ab0 (host-gated). Steady heartbeat of ground-war global state. Exact
field layout TBD (single fixed 38-byte record).

### msg 41 (0x29) — single-scene destroy/state  [server→client, in]
Handler `LAB_004fa110`: `[0x29][sceneIdx u16][state u8]` → `FUN_004f8750(sceneIdx)` lookup
(bounds `< DAT_00c8726c`) → `FUN_0044e5c0` destroy (explosion + 0xaf string broadcast).
Only 2× in the whole session — granular one-off; msg 36 is the batch form the server
actually uses for player-caused destroys.

### msg 42 (0x2a) — full scene-state array  [server→client, in]
Handler `LAB_004f4d50`: `[0x2a][count u16]` + count bytes, each `camp | state<<3`. The
whole-map snapshot ("AIClient. TRN_MANAGER::nSceneInstDef=%i. Receiving %i scenes.").

### msg 59 (0x3b) → 60 (0x3c) — SPAWN RESOURCE SUPPLY  [client→server → server→client]
`out 59'19` "Ask resources from AI" at plane creation → `in 60'8` applies supply result
(may pull from tank production if aircraft units are short). `0x5581c0` applies it to the
plane. NOT combat damage. Purely economy; fires once per spawn.

### msg 33 (0x21) — ScoreEvent  [server→client, in]  14 B
Handler `LAB_004f9ad0`: logs "ScoreEvent. Number=%i. MEC=%i, EEC=%i." Sent alongside 36 on
a kill/destroy to credit score.

## Scene index space (from messages17 TRN02 dump)
The client enumerates its scenes at arena join: `<sceneIdx> <camp> <value> <name>`,
"scenes with valuable objects". TRN02 = 60 scenes (0–59), 12 per camp × 5 camps
(Support/Tank Factory, Village, Airfield, Bomber Airfield, Front Airfield). msg 30/36/41/42
all index THIS 0–59 space. msg 31's object indices are the finer per-piece space inside a
scene — the mapping 31-objidx → sceneIdx is the one remaining unknown; v199's GROUND31 log
(raw bytes + per-object totals) is set up to reveal it in the next live test.

## Emulator implications (next steps)
1. Server must keep authoritative per-scene health/owner for the 0–59 scenes of the loaded
   terrain, decremented by incoming msg 31 (and/or the msg 28 sub-records vs. ground ONumbers).
2. On depletion, send **msg 36** `[0x24][sceneIdx u16][camp/0xFF u8][progress f32]` to all
   clients in the arena — that is the real destroy notify (not 41).
3. Broadcast ownership changes via **msg 30**; push periodic **msg 40** every ~60 s.
4. EvP (flak/AA damages the player): reproduce via **msg 28** targeting the player's own
   plane ONumber — confirm by capturing an inbound 28 in a fresh test where AA is active.
5. msg 59→60 is spawn economy; a minimal always-"supply OK" 8-byte 60 reply unblocks the
   client's plane creation independent of combat.
