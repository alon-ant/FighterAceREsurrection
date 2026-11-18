# Fighter Ace Server — Moderation

Documentation of the moderator/sysop system as currently enabled on the LAN server
(`fa with web server.py`). Covers how rights are granted, the in-game `##` commands, and
the server-console commands.

Last updated for server **v968f9k** (banked 2026-11-18). Sections carry the version they were written for.

---

## 1. How moderator power works

Moderator power in Fighter Ace is **server-granted**, not client-side. Three mechanisms,
all reverse-engineered from `FA.exe`, cooperate:

1. **`MyRights` (server → client).** The login-channel message **218 (0xDA)** carries a
   `u32` at payload offset **+9**. The client stores it to the global `0xc6e8b0` and logs
   `**** MyRights=%i ****`. That global has exactly **one writer** in the whole binary and
   its only source is this message — so **a client cannot promote itself**. Rights exist
   only because the server sends them.

2. **The chat parser gate.** The client only accepts the `##<command>` admin group when
   `MyRights != 0`. A non-moderator who types `##ban …` has the line fall through to
   ordinary chat (the server logs this as `CMDPROBE`).

3. **Server-side re-validation.** Even when the client sends an admin packet, the server
   **re-checks the sender's stored rights** before acting. The client's flag is never
   trusted on its own.

**Rights model:** a single per-pilot integer `admin_rights` in the `pilots` table
(default **0** = ordinary player). **Any non-zero value = full moderator.** It is settable
**only from the server console** — no network path can write it.

> Note: the legacy `rights` column (default 1) is unrelated and unused; moderator status
> lives in the separate `admin_rights` column.

---

## 2. Granting moderator status (server console)

| Command | Effect |
| --- | --- |
| `mod <pilot> [rights]` | Grant moderator rights to a pilot. `rights` defaults to 1; any non-zero value = full mod. If the pilot is online, the grant is pushed live; otherwise it applies at their next pilot-select. |
| `unmod <pilot>` | Revoke moderator rights. |
| `mods` | List all defined moderators and whether each is currently online. |

**Notes**

- The pilot must already exist (see `list`).
- `mod <pilot> 0` is refused — use `unmod` to revoke.
- **Revoke does not take effect until reconnect.** The client caches `MyRights` for the
  whole session; the server cannot clear it remotely. An online moderator keeps powers
  until they disconnect. The console warns you when you `unmod` someone who is online.

---

## 3. In-game `##` commands (issued by a moderator in chat)

A moderator (a pilot with `admin_rights != 0`) types these in the game chat. The client sends
a packet to the server, which re-validates rights and acts. **v950f5 rewrote this layer** after
the wire was re-read from the client's own command handlers (see change.log v950f5).

### The wire (for the record)

All ban/gag commands send one 41-byte record `[op][name 32 B][A i32][B i32]`:

| | meaning |
| --- | --- |
| `op` | `0x55` = **BAN family**, `0x56` = **GAG family** |
| `name` | the target; **empty = the whole room** (`##GagRoom` / `##UnGagRoom`) |
| `A` | `-1` = this room only (`##Ban`, `##Gag`), `0` = all rooms (`##BanAll`, `##GagAll`) |
| `B` | hours to apply (`0` = soft boot), `-1` = release (`##UnBan`, `##UnGag` …) |

The server answers with the client's **native notices** on the same opcodes, `[op][u32 minutes]`:
`0x56` locks the target's chat input and prints *You are gagged for N minutes* (0 = *You are
ungagged*); `0x55` puts up the client's own *You are banned for N hour(s) M minute(s)* dialog
(0 = *You are banned. You can reenter this game right after exiting.*) and takes it back to the
lobby. No session is killed — that is how the 2009 host did it.

### Enabled and enforced

| In-game command | Effect |
| --- | --- |
| `##Gag <player> <hours>` | Mute in **this arena** for N hours (max 12). Input locked on the client, lines dropped by the server. |
| `##GagAll <player> <hours>` | Mute **everywhere** (every arena and the lobby). |
| `##UnGag <player>` / `##UnGagAll <player>` | Lift the gag; the client is told *You are ungagged*. |
| `##GagRoom` / `##UnGagRoom` | Gag (1 h) / ungag every non-moderator currently in the room. |
| `##Ban <player> <hours>` | Native boot to the lobby + no re-entry to **this arena** for N hours. `0` = soft boot (can return at once). |
| `##BanAll <player> <hours>` | Native boot + no entry to **any arena** for N hours (also kicked at pilot select). |
| `##UnBan <player>` / `##UnBanAll <player>` | Lift the ban. |
| `##JoinDisable` / `##JoinEnable` (also `##EnableFlyButton`) | While disabled a non-moderator's Fly ask is refused (*Joining is disabled by the host*); the room is told either way. |
| `##FlyDisable` / `##FlyEnable` | Server-side words, any arena (v968f9j): msg 0x74 `[0x74][disabled u8]` to the room and to joiners - the client's JOIN ENABLED flag (DAT_00c1cdb8, handler FUN_004ee470; a client with moderator rights ignores 'disabled'), which the HQ dialog reads for the Fly button and redraws at once. Toggles both ways. For a pilot who enters later the same flag comes from the arena list: 0xd2 row flag bit 0x04 (the red X icon) -> arena record +0x24 -> set when the join completes (v968f9k); the state is also re-sent when his HQ screen opens. The server also refuses non-sysop Fly asks while off. An arena reset clears it. |
| `##EventOpen [s]`, `##EventClose`, `##EventFight` (`##EventGo`), `##EventHold`, `##EventEnd [winner]`, `##EventReset`, `##EventStatus` | v968f9g, server-side words: the console's `event` verbs for the arena the sysop is in. Answer only in arenas with tournament or event mode (status everywhere). See EVENTS.md. |
| `##ResetGame` | Runs the arena reset (announce, countdown, boot, rebuild). |
| `##AllChatOn` / `##AllChatOff` | Recorded for the room. |
| `##killp` / `##ejectp` / `##crumblep` / `##nofuelp <player>` | Relayed natively to the target's client, which runs the death / bail-out / fuel loss itself. |
| `##GSM <player> <text>` | Private global message (relayed). |

### Chime sound indices (`##ChimeP <pilot> <idx>` / `##ChimeAll <idx>`)

The index is the client's sound table (`SOUNDS\Sounds.str`), sent raw by the client (`atoi` of
the typed number). The chimes are a block of 22 short 44.1 kHz samples at **500..521**. (A first
listing had them at 379..400: the `.str` format skips indices with a `\0<n>` pair, and the pair in
front of Chime01 jumps 118 entries - that is why nothing played.) The server also accepts the plain
chime number: `##ChimeP X 7` plays Chime07 (1..22 are mapped to 500..521; anything else is passed
through as a raw index).

| idx | # | file | length | character (auto-analysed) |
| --- | --- | --- | --- | --- |
| 500 | 1 | Chime01 | 1.0 s | very high bright tinkle (G#9-D#10), loud attack, fades |
| 501 | 2 | Chime02 | 0.6 s | quick double hit, C5 / A#5 |
| 502 | 3 | Chime03 | 0.6 s | low, soft (A2) |
| 503 | 4 | Chime04 | 0.6 s | high D#6 ping over a low tone |
| 504 | 5 | Chime05 | 0.5 s | mid F4, falling |
| 505 | 6 | Chime06 | 0.9 s | very high C8 tick + low C3 |
| 506 | 7 | Chime07 | 0.5 s | two high A6 pings |
| 507 | 8 | Chime08 | 0.9 s | C#5 / E5 with a low tail |
| 508 | 9 | Chime09 | 0.5 s | E6-C#6-E6 triple |
| 509 | 10 | Chime10 | 1.0 s | four-note phrase D4 C#3 F3 A4 |
| 510 | 11 | Chime11 | 1.0 s | six hits, C#6 E5 F#5 D4 |
| 511 | 12 | Chime12 | 0.6 s | low buzz B2 / B4 |
| 512 | 13 | Chime13 | 1.2 s | loud F4 with G#2 tail (loudest of the set) |
| 513 | 14 | Chime14 | 1.0 s | D#4-F#4-F#4-D#4 phrase |
| 514 | 15 | Chime15 | 1.0 s | D#4-F#4-D#4 phrase |
| 515 | 16 | Chime16 | 1.0 s | very high F7/F8 sparkle, quiet |
| 516 | 17 | Chime17 | 1.0 s | high G#7/F#7 sparkle, quiet |
| 517 | 18 | Chime18 | 1.3 s | E6 / A6 bell, loud |
| 518 | 19 | Chime19 | 1.5 s | D6 A#5 G5 descending, loud (longest) |
| 519 | 20 | Chime20 | 1.0 s | A5 A6 D7 rising, loud |
| 520 | 21 | Chime21 | 1.0 s | F6 G#6 D6 |
| 521 | 22 | Chime22 | 0.5 s | single high E7 ping |

Only the chime block is usable: the client plays the sound as a 3-D source parked at the world
origin (the chime helper object @0xc84a54 reports position (0, 1, 0)), and the chime `.snd`
definitions carry MaxDistance = 1,000,000 m so they are heard anywhere on the map. Every other
sound (Beep/BadBeep 200 m, explosions, the Stuka siren, ...) has a normal range and is inaudible
unless the pilot happens to be flying over the map origin - that is why `##ChimeP X 2` is silent.
Gaps in the table (e.g. 382..499) are silent as well.

A banned pilot who enters a barred arena is granted the entry (the join grant cannot be refused
cleanly) and two seconds later his own ban dialog takes him out again. **Moderators are never
gagged or booted.** Bans and gags persist in `moderation_state.json` across restarts.

### Where the broadcast banner shows (`:B`, `say`, `broadcast`)

The "blinking message across the screen" is the yellow centre-screen line of the **cockpit (3-D)
view** - Msn_Serv.cpp FUN_00474e90 draws it blinking (200 ms) in colour 14 for the 10 s the msg-20
channel-4 handler arms (FUN_0046a8a0(text, 10000)). It is not drawn on the HQ, map, plane-select or
chat screens, and switching to any of those frees the text (0x44296d / 0x45f720). It also yields to
every higher-priority centre message: server-shutdown / exit countdowns, "Bailing out!", "Your pilot
has been killed!!!", "Fueling and Arming Plane... N" (the 15 s after a re-arm request), "Loading
Cargo", "Your view is returning to cockpit mode", "Waiting Start Place On Airfield", take-off queue
lines, competition timers. The magenta `NAME: TEXT` line in the chat pane is always printed. So to
see the banner the receiver must be in the cockpit with none of those active - the 19:55 test had
Taurus on the HQ screen and Alon parked right after a repair request.

### Server polls (v951f5)

The client ships a complete poll UI that the 2009 event scripts drove (script ops `CreatePoll` /
`GetPollVotes`); the server now drives it from the console (terminal or web-admin console):

```
poll start <room|all> <seconds> <question> | <choice 0> | <choice 1> [| ...]
poll status [room]        poll end [room]        poll cancel [room]
```

What the pilots see: yellow system lines with the question and `!!vote N = choice` list, the
client's own poll record (msg 0x93 - Chime20 and an automatic print if the player has those two
Options toggles on), and `!!poll` prints it any time ("Current Poll Criteria", "Choice N - ...",
"Poll is active for N seconds more"). They answer with `!!vote N` (0-9); the client refuses a
second vote, a closed poll or a bad number itself, and sends 0x94 `[id][choice]`. The server keeps
one vote per pilot name (a reconnect does not reset it), acks with "Vote counted: N - choice",
relays the 0x94 to the room so the clients' counters stay in step, re-sends the poll to pilots
entering the arena while it runs, and when time is up prints the counts per choice and flashes
the winner as a banner (`POLL: <choice> (n of m)`), or a tie line. Up to 10 choices, 10 s - 1 h,
one poll per room; `all` opens the same poll in every room with in-game pilots. Poll ids run
1..99 (the client's limit).

Wire: 0x93 is a fixed 0x245-byte record `[0x93][id u32][3 x u32 unused][0 u32][duration s u32]
[44 x 00][text 0x200]` with `question|choice|choice...`; 0x94 is `[0x94][id u32][choice u32]` both
ways (client vote in, relay out; the client tallies per poll @0xc6f52c but never displays it).

### Tournament mode (v952f5)

The step-by-step event command chain (prepare, gather, clock, weapons lock, discipline, reset) is in
**EVENTS.md** next to this file.


The arena-creation dialog's Tournament group (enabled / number of lives / ghosting) plus the hidden
template values (joining window 5 min, shooting 2 min later, allow tabbing off, last one flying wins
on) are editable per arena on the web (Tournament section) and are served in the GAME_DEF. The server
runs the clock: it starts at the first ordinary pilot's spawn (never a sysop's, v968f9g; never by a spawn in
an event-mode arena, v968f8m) or with `event open <room> [joining seconds]` / `##EventOpen [seconds]`, every
pilot receives the same start (msg 0x5c, late joiners at ServerConfirm), the cockpit counts down the
joining window and then the shooting delay (no guns, no collisions until then). Pilots who ask to fly
after the joining window closed are refused unless they were already in; a pilot out of lives is
refused too, or, with ghosting, flies on as a ghost (the server ghosts his new plane). With "last one
flying wins" the server declares the winner (msg 0x30: "<name> has won") and flashes the banner.
`event close <room>` closes joining now (the shooting countdown then runs); `event fight <room>`
skips both countdowns (joining closes, the competition starts now - "FIGHT!"); `event status [room]`
shows phase, deaths and ghosts; `event end <room> [winner]` closes it by hand; `event reset <room>`
(and an arena reset) clears it so the next spawn restarts. v955f5: one `event` command family drives
both the tournament clock and the weapons lock - see EVENTS.md. v968f9g: a number on `event open` is the
joining window of that run in seconds (the start is placed so that the clients' own "Time until end of
joining" counts exactly that; with a 0-minute window the start lies in the future, which the client's
signed clock arithmetic handles), and when the clock reaches the competition the server itself closes
joining, frees the event lock or ends a guns-cold hold, and announces the fight.
Moderators never count as participants and are never refused.

### Event mode - the lock (v953f5, rewritten for v968f9k)

The game's [Event] section, served only to arenas with **event mode** ticked on the web (Tournament
section); all other arenas carry no event flag, no timers and no entry message. The command chain is in
EVENTS.md; this is how it works.

**The lock.** With `DelaysActive` in the GAME_DEF every client checks each ACTION by itself - engine
start, guns, rockets, bombs / supplies, taxi:

    refused while   no event start is known,   or   now < start + (Event.StartDelay + the action's minutes) min

The action's minutes come from the [EventParam<Fighters|Bombers|Support><camp>] table of the GAME_DEF
(EngineStart, FireGuns, FireRockets, DropBombs|DropSupply, Taxi; 3 classes x 8 camps; empty in every
template). The start is msg 0x83 `[0x83][fly enable u8][start NET ms u32]`; start 0 = "no start".

| Arena setting | GAME_DEF served | Locked | Fight |
| --- | --- | --- | --- |
| "Engines free while locked" unticked (the old lock) | no table, Event.StartDelay = the arena's "unlock N min" | start 0: every action refused, "... after Event starts" | the real start (10 s back-dated): everything free after the unlock delay |
| ticked (weapons-only lock, v968f9g/h) | 24 records `[0x20 + class*8 + camp][EngineStart -120][0][0][0][Taxi -120]` (each byte value + 0x80) at the list byte, +144 bytes; Event.StartDelay = 120 | a start in the PAST: engines and taxi net 0 minutes = free; weapons 120 minutes = "You'll be able to open fire in MM:SS" | `fight time - 120 min`: weapons free at the fight time (the arena's unlock delay is added by the server) |

- The HUD event clock is `now - (start + Event.StartDelay)`: with the weapons-only lock it counts down to
  the fight and up from 0:00 after it. While locked the cockpit prints "Event will be started in MM:SS"
  every 15 s (the old lock: "Event not started yet!").
- The locked start is `scheduled fight - 120 min` when the fight time is known (tournament clock
  running, `event open <room> <seconds>`, `event fight <room> in <s>`) - the clients then free the
  weapons at that moment themselves and the server announces FIGHT; with nothing scheduled it is 30
  minutes in the past, re-sent every 20 minutes (a 90..70 minute placeholder on the clients).
- Each pilot gets the form that fits the GAME_DEF HE was served (recorded when the 212 is sent): one who
  entered before the box was ticked gets the old lock and is told to re-enter. If the table cannot be
  inserted (unknown tail layout) or would push the GAME_DEF message past 1320 bytes, the arena is served
  without it and keeps the old lock - the log says so.
- The state is sent at arena entry and on every change. While an event is on hold the server also drops
  the room's damage reports (v968f8z).
- When the tournament clock reaches the competition, or a countdown runs out, the server starts the
  event by itself (v968f9g/i).

**The Fly button - two separate flags in the client** (HQ dialog, FUN_006de570):

| Flag | Set by | Behaviour |
| --- | --- | --- |
| event "Fly button enabled" (DAT_00c1cdbc) | GAME_DEF `FlyButtonEnabled` (the arena setting "Fly button enabled from the start", served only with event mode on) and the enable byte of msg 0x83 | ONE WAY: the byte can only light the button, and a client that got it once keeps a lit button in every arena until the game is restarted (FUN_00440b40, HQ init 0x6e1b9b). The server sends the byte only to a client whose own GAME_DEF said "off", when a host enables the button or the fight starts |
| JOIN ENABLED (DAT_00c1cdb8) | msg 0x74 `[0x74][disabled u8]` (FUN_004ee470; a client with moderator rights ignores "disabled"), and at the moment a join completes the arena-list row's flag bit 0x04 (the red X icon; FUN_006af7b0) | TWO WAY, any number of times, on pilots already in HQ. This is what `##FlyDisable` / `##FlyEnable` / `event fly <room> on|off` drive (v968f9j/k): 0x74 to the room, bit 0x04 in the 0xd2 list while off, and the state again when a client opens its HQ screen |

The server also refuses a non-sysop Fly ask while the button is off. `##JoinDisable` / `##JoinEnable`
(client opcode 0x5f) are server-side only: the button stays lit, the spawn is refused. An arena reset
returns everything to the arena's own state.

### The Chat tab's filter boxes - what each one really switches (v961f5, from the EXE)

Flight_Chat has a HUD row and a LOG row of boxes: Chat (All, Team, Squad), Logins, Hits, AI, Score,
Help, News, Events, Weather, Hints. Two mechanisms:

- **Logins, Hits, AI** are decided by the line's PRINTER. Logins = the msg-62/63 join-leave lines,
  Hits = the hit lines, **AI = the server's AI-text messages msg 66 (0x42) and msg 121 (0x79)**:
  `[0x42][3 bytes][text]` -> the client prints `AI: <text>` (Texts.str 0x108) in the AI colour. The 2009
  server pushed seven such lines (90-105 chars each) at every arena entry - the arena news. The TC AI
  lines (`tc_say`) now use msg 66, so they read `AI: ...` natively and the AI box hides them (before
  they rode chat channel 3 and showed as `AI (O):`). Console: `ai <room|all> <text>`.
- **Score, Help, News, Events, Weather, Hints** are TEXT PREFIX filters: every printer searches the
  finished line for `SCORE:`, `HELP:`, `NEWS:`, `EVENT:`, `WEATHER:`, `HINT:` and honours the matching
  box. The prefix is the server's to write, on any transport (chat, AI line, yellow system line). Used
  now: MOTD lines `NEWS: ...`; event-script score lines `SCORE: ...`; event start/update/final/win,
  tournament, weapons lock and guns-cold lines `EVENT: ...`. Free for later: `WEATHER:` (wind/clouds/time
  changes), `HINT:` (tips), `HELP:` (a `!!help` answer).
- Chat All/Team/Squad follow the msg-20 channel byte (0/1/2; 3 Operator and 4 Broadcast are separate).

### Live weather - `##Weather` (v962f5, field-verified 2026-10-23)

FA msg 137 changes the clouds, rain and wind of everyone in the arena at once (the client rebuilds its
wind and cloud objects; no re-entry). Sysop in game: `##Weather status`, `##Weather clear|scattered|
broken|overcast|rain|storm`, `##Weather clouds <none|cumulus|stratus> <density%> <min m> <max m> [rain]`,
`##Weather rain on|off` (rain only draws under Stratus), `##Weather wind <m/s> <deg>`, `##Weather reset`
(back to the arena's forecast). Console: `weather <room> ...` with the same words. Every change is
announced as an AI line `WEATHER: ...` (the Weather box). Per-arena *Dynamic weather every N min*
(Reality/Weather tab) walks clear -> scattered -> broken -> overcast -> rain -> storm one rung at a time.
Joiners receive the room's live weather at spawn; an arena reset returns to the forecast.

### Guns cold / guns hot - the weapons hold for ordinary arenas (v960f5)

`##GunsCold` and `##GunsHot`, typed in the arena chat by a sysop, are SERVER-SIDE `##` commands: the
client passes a `##` word it does not know through as plain chat (its own table is fixed, FUN_0044d180),
the server recognises the word, acts and answers the sender only - the line is never reflected to the
room, and a non-sysop gets `Sysops only.` Since v968f9a they are the weapons hold in EVERY arena and
never touch the event state: engines stay on, the event and tournament clocks keep running. The event
lock (engines and weapons locked on the clients) is a separate word, `##EventHold` (console `event hold
<room>`), lifted by `##StartEvent` / `event fight <room>` - which also ends a guns-cold hold. While an
event is on hold the server drops the room's damage reports too (v968f8z). A guns-cold hold also ends
when the tournament clock reaches the competition and at `##EventReset` (v968f9g).
The guns-cold hold is server-side: the clients keep firing but the
server drops every damage report that leaves the room (msg 28 plane hits, msg 29 canopy hits, msg 31
ground damage - bombs and rockets included), so nothing registers and no kill is booked; collisions
remain. Broadcast + cockpit banner on each change, a spawn notice for joiners, a reminder to a shooter
every 8 s, `##GunsStatus` for the state. Console: `guns <room> cold|hot|status`, `guns status`; an arena
reset returns the room to guns hot. More server-side `##` words can be added to CHAT_SERVER_COMMANDS.

### Relayed pilot effects (field-verified 2026-10-21)

`##GhostP <pilot>` / `##GhostAll` (ghost mode, toggle), `##SmokeP <pilot> <0-7>` (decorative smoke -
the bit field selects the colour; all three colours and their mixes work) and `##ChimeP` / `##ChimeAll`
(see the chime table above) are relayed by the server to the named pilot's client, which applies them
to its own plane. All verified in game.

### Not modelled

`##ClearScores` (arena scores live in the ladder; the command is logged only) and the long 0xDA form
that would show *banned for all games* in the lobby dialogs.

---

## 4. Server-console / admin-panel moderation commands

| Command | Effect |
| --- | --- |
| `kick <pilot> [text]` | Soft boot through the native dialog; nothing recorded, he can return at once. |
| `ban <pilot> [hours] [message...]` / `banall …` | Native boot + no arena entry for N hours (omit = open-ended, `0` = soft boot, max 12). A non-numeric token after the name starts the message. |
| `unban <pilot>` / `unbanall <pilot>` | Lift a ban. |
| `bans` | Active bans with scope and remaining time. |
| `gag <pilot> [hours]` / `gagall …` | Mute everywhere (default 1 h); the client's input locks. |
| `ungag <pilot>` / `ungagall <pilot>` | Lift a gag. |
| `gags` | Active gags with scope. |
| `say <room|all> <text>` | Yellow system line **and** the ~10 s on-screen banner. |
| `broadcast <text>` | Server-wide banner (in-game) + *Server:* chat (lobby). |
| `boot <pilot> [text]` | EShutDown with text (the client exits the game). |
| `event open\|close\|fight\|hold\|end\|reset\|fly\|status\|scores <room> ...` | The event toolbox - see EVENTS.md. In game: `##EventOpen [s]`, `##EventClose`, `##EventFight`, `##EventHold`, `##EventEnd [winner]`, `##EventReset`, `##EventStatus`, `##FlyEnable`, `##FlyDisable`. |
| `guns <room> cold\|hot\|status` | Server-side weapons hold (in game `##GunsCold` / `##GunsHot` / `##GunsStatus`). |
| `poll start\|status\|end\|cancel ...` | Server polls (above). |
| `help [word]` | Every console command by section; `help ban` filters. |

### 4b. Operational console commands added up to v968f9k (not moderation)

| Command | Effect |
| --- | --- |
| `lagwatch [on\|off]`, `lagwatch notify on\|off` | The lag watch: finds a pilot whose game handles what it is sent late (a slipped input queue), logs the episode, dumps the recorder. |
| `pad`, `pad on\|off`, `pad <pilot> <datagrams/s> [seconds]`, `pad <pilot> off` | Padding: empty datagrams that push a slipped queue through. Automatic since v968f9d - on when a pilot is late, off when he is in step again; the manual forms are for tests. |
| `slip <pilot> <datagrams behind, 1-250> [minutes]`, `slip <pilot> off`, `slip` | TEST: the server plays a slipped input queue for one pilot so the padding can be watched working (v968f9e). |
| `mlist [on\|off]` | Bundling of AI frames into message lists (singles for a pilot the lag watch has confirmed late). |
| `lagperf [on\|off]` | The lag/performance CSV in `logs/`. |
| `car decoylane on\|off` | One kill-line decoy at a time per client, so every lorry kill prints its line (v968f9f; off = the old timing). |

---

## 4a. Reserved staff-tag names

Players cannot create a pilot whose name carries a staff tag: **`@FA3`, `@FA`, `@HQ`,
`@FAVG`, `@VR1`** (case-insensitive, tag anywhere in the name). The pilot-create is refused,
no create-echo is sent (so the pilot is never registered), and the player is told:
`The name "X" is reserved for staff and cannot be used.`

- Applies to **in-game pilot creation** only. Ordinary names that merely contain the letters
  (e.g. `Falcon`, `Fafnir`, `HQof`) are **not** blocked — the `@` is what makes a tag.
- The server-console `gen <account>` is **exempt**, so staff accounts such as `sysop@fa` can
  still be created by the admin.
- Not retroactive: existing pilots are not renamed, and a moderator does **not** need the tag
  in their name to have powers (rights come from `admin_rights`, not the name).

---

## 5. Quick reference

```
console:  kick <pilot> [text] | ban|banall <pilot> [hours] [msg] | unban|unbanall <pilot> | bans
          gag|gagall <pilot> [hours] | ungag|ungagall <pilot> | gags
          mod <pilot> [rights] | unmod <pilot> | mods | say <room|all> <text> | broadcast <text>
in-game:  ##Ban/##BanAll <player> <hours>   ##UnBan/##UnBanAll <player>
          ##Gag/##GagAll <player> <hours>   ##UnGag/##UnGagAll <player>   ##GagRoom / ##UnGagRoom
          ##JoinDisable / ##JoinEnable      ##ResetGame      ##GSM <player> <text>
          ##killp / ##ejectp / ##crumblep / ##nofuelp <player>
          ##EventOpen [s] / ##EventClose / ##EventFight (##StartEvent) / ##EventHold / ##EventEnd [winner]
          ##EventReset / ##EventStatus      ##FlyDisable / ##FlyEnable      ##GunsCold / ##GunsHot / ##GunsStatus
console:  event open|close|fight|hold|end|reset|fly|status|scores <room> ...   guns <room> cold|hot|status
```

---

## 6. Still open

- **Event lock, client limits (v968f9k):** during a hold with nothing scheduled the weapons-only lock
  shows a placeholder countdown (90..70 min) and "Event will be started in MM:SS" every 15 s - the HUD
  clock cannot both start from 0 at the fight and stay silent before it. A pilot whose grey event
  button ("Fly button enabled from the start" unticked) was lit once keeps it lit until he restarts the
  game; `##FlyDisable` still greys him through the other flag. The 0x74 state is re-sent at every HQ
  open of a room a host has switched (harmless, a little chatty).

- **Lobby "for all games" dialogs**: the client reads GagAll/BanAll minutes from a 25-byte 0xDA
  lobby attach (offsets +0xd / +0x11); we send the 15-byte safe form, so a globally banned pilot
  is kicked at pilot select instead of seeing that dialog.
- ~~Sysop roster section~~ — done in v954f5: moderators are listed under **Sysops** in the chat/arena
  roster. The client derives that group from the player's rights (bit 0x02 set, bit 0x01 = incognito
  clear), which the server now sends in msg 218 (own) and in the msg-62 roster record byte +5 (peers).
  `mod <pilot> hidden` makes a sysop incognito (listed under his nation), `mod <pilot> visible` undoes it;
  peers see a change at their next arena entry.

---

## 7. Configuration

At the top of the moderator section in `fa with web server.py`:

| Flag | Default | Meaning |
| --- | --- | --- |
| `MODERATORS_ENABLED` | `True` | Master kill-switch for the whole moderator layer. |
| `MOD_RIGHTS_DEFAULT` | `1` | Value written by `mod <pilot>` when no rights value is given. |

Ban and gag state (`BANS`, `GAGS`, with their scope) persists in `moderation_state.json`.
