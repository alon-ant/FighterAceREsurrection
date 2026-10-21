# Running an event on Fighter Ace REsurrection (v953f5)

The sysop's command chain for a tournament, a squad event or a plain "everyone hold fire" round.
Console commands work on the terminal and in the web-admin console; `##` commands are typed in game by
a sysop (moderator rights); `!!` commands are for every pilot. Details of each mechanism and its wire
form are in MODERATION.md.

## 1. Prepare the arena (web: Admin -> arena -> Settings)

| Section | Setting | Meaning |
| --- | --- | --- |
| Tournament | Tournament mode enabled | the game's tournament clock: joining window -> shooting countdown -> competition |
| Tournament | Number of lives | 0 = unlimited; the server keeps the count |
| Tournament | Ghosting | out of lives = the pilot flies on as a ghost (no fire, no collisions) |
| Tournament | Joining window (min) | how long pilots may still enter after the start |
| Tournament | Shooting starts (min) | countdown after joining closes; no guns, no collisions until then |
| Tournament | Allow tabbing out | exiting to HQ does not cost a life |
| Tournament | Last one flying wins | the server announces the winner ("X has won") |
| Event mode | Start with weapons and engines locked | the arena begins locked (see step 4) |
| Event mode | Unlock N min after the event start | delay with an "in MM:SS" countdown on the client |
| Event mode | Fly button enabled from the start | untick = the HQ Fly button is grey until enabled |

Settings reach a client when it enters the arena - have everybody leave to the lobby and re-enter after
a change. `##JoinDisable` beforehand keeps them in HQ.

## 2. Gather and brief the field

| Command | Effect |
| --- | --- |
| `##JoinDisable` / `##JoinEnable` | hold everyone in HQ / let them fly (server-enforced) |
| `##EnableFlyButton` or `event fly <room> on\|off` | the HQ Fly button itself |
| `##GagRoom` / `##UnGagRoom` | silence everyone without a staff tag |
| `:B <text>` (in game) or `say <room\|all> <text>` | yellow system line + the 10 s blinking line in every cockpit |
| `##GSM <pilot> <text>` or `gsm <pilot> <text>` | private red flash to one pilot, anywhere on the server |
| `##ChimeAll <1-22>` / `##ChimeP <pilot> <1-22>` | attention chime (20 = the server-notice chime) |
| `poll start <room\|all> <secs> <question> \| <choice> \| <choice> ...` | pilots answer `!!vote N`, `!!poll` shows it; `poll status\|end\|cancel [room]` |

The blinking line is drawn in the cockpit view only; pilots on the HQ, map or chat screens see the chat
line but no banner.

## 3. The tournament clock

| Command | Effect |
| --- | --- |
| `tournament start <room> [in <seconds>]` | (re)start the clock for everyone; the first spawn starts it by itself |
| `tournament status [room]` | phase, time to the next phase, participants, deaths, ghosts |
| `tournament close <room>` | close joining now - the shooting countdown runs |
| `tournament go <room>` | skip both countdowns - competition now ("FIGHT!") |
| `tournament end <room> [winner]` | close it by hand (announces the winner if named) |
| `tournament reset <room>` | clear it; the next spawn restarts the clock |

During the competition the server counts lives (crash, collision, bail, shot down; exit to HQ too when
tabbing is not allowed), refuses Fly asks from latecomers and from pilots out of lives (ghosts are
re-ghosted on their next plane), and with "last one flying wins" sends the result and the banner.
Moderators never count and are never refused.

## 4. The weapons lock (any arena, any time)

| Command | Effect |
| --- | --- |
| `event stop <room>` | HOLD FIRE: no engine start, guns, rockets, bombs/torpedoes, troops, supplies ("You'll be able to open fire after Event starts") |
| `event start <room> [in <seconds>]` or `##StartEvent` | weapons free (after the unlock delay if set) - "EVENT STARTED" banner |
| `event fly <room> on\|off` | the HQ Fly button |
| `event status [room]` | state and the arena's initial setting |

A pilot already airborne keeps his running engine when the lock lands but cannot fire. Pilots who were
in the arena before the server was updated to v953f5 keep their old arena data and ignore the lock until
they re-enter.

## 5. Discipline during the event

| Command | Effect |
| --- | --- |
| `##KillP` / `##EjectP` / `##CrumbleP` / `##NoFuelP <pilot>` | kill the pilot / eject him / disintegrate / drain the fuel |
| `##GhostP <pilot>` / `##GhostAll` | ghost mode (toggle) |
| `##SmokeP <pilot> <bits>` | decorative smoke on his plane |
| `##Gag <pilot> [h]` / `##GagAll`, `##UnGag` / `##UnGagAll` | mute in this room / everywhere |
| `##Ban <pilot> 0` | soft boot (he may return at once); `##Ban <pilot> <h>` / `##BanAll <pilot> <h>` bar him for h hours |
| console `kick`, `gag`, `ban`, `unban`, `bans`, `gags` | the same from the console |

## 6. Next round

| Command | Effect |
| --- | --- |
| `##ResetGame` or console `reset <room>` | rebuild the arena; clears the tournament, returns the lock to the arena's initial state, re-bases the arena clock |
| `tournament start <room>` / `event stop <room>` | as needed for the next round |

## Typical sequences

*Dogfight ladder with 3 lives:* web: tournament on, lives 3, ghosting on, joining 5, shooting 2, last one
flying wins -> `##JoinDisable` while briefing -> `##JoinEnable`; pilots spawn (clock starts) ->
`tournament close 149` when the field is complete -> `tournament go 149` -> the server announces the winner
-> `##ResetGame`.

*Formation / race event without shooting:* `event stop 149` as pilots enter -> they form up with engines
running (start them before the lock, or `event start` briefly) -> `event start 149` for the combat part,
`event stop 149` to end it.

*Quick vote:* `poll start all 60 Next arena? | Pacific | Europe | Africa`.
