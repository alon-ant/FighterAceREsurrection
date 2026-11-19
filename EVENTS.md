# Running an event on Fighter Ace REsurrection (v968f9k)

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
| Tournament | Joining window (min) | how long pilots may still enter after the clock starts; **0 = no clock closes it** - open until `event close` or the fight (v968f8m) |
| Tournament | Shooting starts (min) | countdown after joining closes; no guns, no collisions until then |
| Tournament | Allow tabbing out | exiting to HQ does not cost a life |
| Tournament | Last one flying wins | the server announces the winner ("X has won") |
| Event mode | Event mode: locked until the host starts the event | the arena begins locked (see step 4); arenas without it have no event timers at all |
| Event mode | Engines free while locked (weapons-only lock) | v968f9g: the lock holds guns, rockets, bombs, torpedoes, troops and supplies only - engines start and planes taxi from the first second. Unticked = the lock holds the engines too. (v968f9r made this automatic for air-start arenas; **switched off again in v968f9t** - on arenas created 11-19 the table crashed the client at the arena click. Until that is fixed: tick the box only on an arena where it has been seen to work, and test the click with one client first) |
| Event mode | Unlock N min after the event start | delay with an "in MM:SS" countdown on the client |
| Event mode | Fly button enabled from the start | untick = the HQ Fly button is grey until `##FlyEnable` (or the fight). Only read with event mode on: an arena without event mode always starts with its Fly button (v968f9g) |
| Event mode | Event length (min) | counted from the start of the fight; when it elapses the server ends the event (tournament finished - fewest deaths wins, tie = draw - and weapons locked, "EVENT OVER"); 5-min and 1-min warnings; 0 = until `event end`/`hold` by hand |

Settings reach a client when it enters the arena - have everybody leave to the lobby and re-enter after
a change. `##JoinDisable` beforehand keeps them in HQ.

## 2. Gather and brief the field

| Command | Effect |
| --- | --- |
| `##JoinDisable` / `##JoinEnable` | hold everyone in HQ / let them fly: the Fly button stays lit, the server refuses the spawn after the click |
| `##FlyDisable` / `##FlyEnable` (console `event fly <room> on\|off`; the client's own `##EnableFlyButton` also enables) | the HQ Fly button goes grey / lit for everybody but sysops, at once and for joiners; any arena; toggles freely (v968f9j) |
| `##GagRoom` / `##UnGagRoom` | silence everyone without a staff tag |
| `:B <text>` (in game) or `say <room\|all> <text>` | yellow system line + the 10 s blinking line in every cockpit |
| `##GSM <pilot> <text>` or `gsm <pilot> <text>` | private red flash to one pilot, anywhere on the server |
| `##ChimeAll <1-22>` / `##ChimeP <pilot> <1-22>` | attention chime (20 = the server-notice chime) |
| `poll start <room\|all> <secs> <question> \| <choice> \| <choice> ...` | pilots answer `!!vote N`, `!!poll` shows it; `poll status\|end\|cancel [room]` |

The blinking line is drawn in the cockpit view only; pilots on the HQ, map or chat screens see the chat
line but no banner.

## 3. Running it: one command family, in game or on the console

Each verb does whatever applies to the arena (tournament clock, lock, or both). On the console it is
`event <verb> <room>`; in game a sysop types the `##` word in the arena he is in (v968f9g). The event
words answer only in arenas with tournament or event mode; `##FlyEnable`, `##FlyDisable` and
`##EventStatus` work everywhere.

| In game (sysop) | Console | Tournament arena | Event-mode arena (the lock) |
| --- | --- | --- | --- |
| `##EventOpen [seconds]` | `event open <room> [seconds]` | the clock starts: joining window, then the shooting countdown, then the competition. With a number the joining window of THIS run is that many seconds, whatever the arena's minutes say (`##EventOpen 180`); without, the arena's "Joining window" | locked, waiting for the fight - which the clock starts by itself when it reaches the competition. In an event arena WITHOUT a tournament the number is the countdown to the fight itself (`##EventOpen 90` = weapons free in 90 s, counted down on every client; v968f9h) |
| `##EventClose` | `event close <room>` | joining closed now; the shooting countdown runs | - |
| `##EventFight` (`##EventGo`, `##StartEvent`) | `event fight <room> [in <s>]` | competition now: collisions, hits, lives | lock off (`in <s>` = native countdown on the clients) |
| `##EventHold` | `event hold <room>` | - (the console form falls back to guns cold in an arena without event mode; in game use `##GunsCold` there) | locked again |
| `##EventEnd [winner]` | `event end <room> [winner]` | tournament finished, winner announced | - |
| `##EventReset` | `event reset <room>` | cleared: clock, lives, participants, a guns-cold hold | back to locked |
| `##FlyEnable` / `##FlyDisable` | `event fly <room> on\|off` | the HQ Fly button | the HQ Fly button |
| `##EventStatus` | `event status [room]` | phase, participants, deaths, ghosts, time left, script standings | locked / free, lock type, fly button, time left |
| - | `event scores <room>` | script standings + a report pushed to the arena now | - |

Who starts the clock:

- **Tournament arena without event mode:** the first ordinary pilot's spawn, or `##EventOpen`. A sysop's
  spawn never starts it (v968f9g) - he is told so once.
- **Tournament arena with event mode:** only the host (`##EventOpen`, or `##EventFight` straight away).
  Until then pilots assemble freely and no life is at stake.
- When the clock reaches the competition the server closes joining, frees the lock (event mode) or ends a
  guns-cold hold (no event mode), and the arena reads "the competition starts NOW" + FIGHT! (v968f9g).
  With joining 0 and shooting 0 and no number on `##EventOpen` there is no clock to wait for: the host
  starts the fight with `##EventFight`.

During the competition the server counts lives (crash, collision, bail, shot down; exit to HQ too when
tabbing is not allowed), refuses Fly asks from latecomers and from pilots out of lives (ghosts are
re-ghosted on their next plane), and with "last one flying wins" sends the result and the banner.
Moderators never count and are never refused.

## 4. The lock, in short

Only arenas with event mode ticked on the web have it; it is enforced by every client.

| | Full lock (box "Engines free while locked" unticked) | Weapons-only lock (box ticked, v968f9g) |
| --- | --- | --- |
| engines, taxi | refused: "You'll be able to start engines after Event starts" | free from the first second |
| guns, rockets, bombs, torpedoes, troops, supplies | refused: "... after Event starts" | refused: "You'll be able to open fire in MM:SS" |
| a pilot who air-starts | glides - no engine | flies |
| the HUD event clock | "not started" | counts DOWN to the fight, then UP from 0:00 (v968f9h) - so with an event length of 30 it runs 0:00 -> 30:00 |
| event text line every 15 s while locked | "Event not started yet!" | "Event will be started in MM:SS" |

The countdown of the weapons-only lock is the real time to the fight whenever the server knows it: after
`##EventOpen <seconds>` (with or without a tournament) or `event fight <room> in <s>`. During a plain
hold with nothing scheduled the game still has to be given a time - it shows a placeholder between 90
and 70 minutes (re-set every 20 minutes) that means "not scheduled"; it jumps to the real countdown the
moment the host schedules the fight, and to 0:00 when he types `##EventFight`. When a countdown runs
out the arena gets "EVENT: FIGHT - weapons free!" and the flashing cockpit line (v968f9i).

`##EventFight` / `##StartEvent` (or the tournament clock reaching the competition) frees everything, after
the arena's "unlock N min" delay if one is set; `##EventHold` locks again. This lock stops the FIRING
itself - no tracers, no bombs leave the plane. `##GunsCold` (below) is the other tool: everybody can fire,
nothing counts.

**The Fly button** (v968f9j). `##FlyDisable` / `event fly <room> off` greys the HQ Fly button of every
pilot in the arena at once - sysops keep theirs - and of every pilot who enters while it is off;
`##FlyEnable` / `event fly <room> on` lights it again. It toggles as often as you like, in any arena
(the game's own "join enabled" switch, message 0x74). While it is off the arena shows the red X in the
lobby's arena list - pilots can still enter, and find the button grey (v968f9k). As a backstop the
server also refuses a Fly ask while the button is off. `##JoinDisable` / `##JoinEnable` remain the other
gate: the button stays lit and the server refuses the spawn after the click. Separate from both is the arena setting "Fly button
enabled from the start" (event mode): unticked, the arena opens with the button grey until `##FlyEnable`
or the fight.

The weapons-only lock is part of the arena data a client receives when it ENTERS the arena. A pilot who
was already inside when the box was ticked keeps the full lock until he leaves to the lobby and comes
back in; the server tells him so, and never sends him a state that would free his weapons by mistake.

**Arenas without event mode - `##GunsCold` / `##GunsHot`** (v960f5). Ordinary arenas carry no event
flag, so the client cannot lock their weapons; instead the server holds fire for them: after a
sysop types `##GunsCold` in the arena chat (or the console runs `guns <room> cold`, or `event hold`
on such an arena), the clients keep firing but every damage report leaving the room is dropped -
plane hits, canopy hits, bombs and rockets on ground targets - so nothing registers, nobody dies of
fire and no kill is booked; collisions still happen. The arena hears `GUNS COLD - weapons hold by
<sysop>` plus a cockpit banner, joiners are told on spawn, and a pilot who shoots gets a reminder
every 8 s. `##GunsHot` (console `guns <room> hot`, `##EventFight` / `##StartEvent`, or the tournament clock
reaching the competition) frees them; `##GunsStatus` shows the state. Since v968f9a the two words mean the
same in every arena, event mode or not, and never touch the event lock or the clocks. These
`##` words are the server's own: the client passes an unknown `##` word through as chat, the server
consumes it and answers the sender only - nothing is reflected to the room.

**What has been seen working on a real client (local tests 11-17/18, one ordinary pilot + console):** the
weapons-only lock with the engine running, hold / fight / hold, the HUD clock from 0:00 at the fight, the
countdown of `event open <room> <seconds>` with the FIGHT line at the end, the Fly button toggle for a
pilot in HQ and for one who leaves and re-enters. **Not yet seen:** any of it with several pilots or on
the live server; the tournament + event-mode chain (`##EventOpen 180` in a Death Bowl arena) end to end;
the `##` words typed in game by a sysop (the tests used the console).

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
| `##EventReset` / `event reset <room>` | tournament cleared, lock back on, guns-cold hold ended; `##EventOpen` (or the first ordinary pilot's spawn in an arena without event mode) starts the next round |
| `##ResetGame` or console `reset <room>` | the full arena rebuild (scores, scenes, clock) - also clears the event |

## 7. Event scripts - custom scoring, objectives, victory (v958f5)

> Moderators: the plain-language guide with recipes, the full points table, message templates
> and troubleshooting is **EVENT_SCRIPTING.md**. This section is the short reference.

Paste a JSON script into the arena's Events tab ("Event script"). Scoring runs from the moment the
fight is on (the tournament's competition start, or `event fight` in an event-mode arena) until the
event length elapses or `event end`; every award is announced in the arena, a progress report (team
scores, top pilots, banner) goes out every `report_min` minutes, and at the end the team with the
most points - or most air kills with `"victory": "kills"` - wins ("GE WINS", or a draw).

```json
{
  "name": "Battle of Britain",
  "victory": "points",
  "report_min": 30,
  "announce": true,
  "teams": {
    "GE": {"objective": "Bomb the British airfields and factories",
           "points": {"kill_fighter": 1, "kill_bomber": 1, "scene_damage": 0.5, "scene_trigger": 25, "bridge": 10}},
    "GB": {"objective": "Defend - shoot the bombers down",
           "points": {"kill_fighter": 1, "kill_bomber": 3}}
  }
}
```

- `mode`: `team` (default) - teams score and the best team wins; `personal` - every pilot scores for
  themselves (Pin Point Parachuting, Fox hunt...), broadcasts read `Bigalon +10 (total 30): ...`,
  updates list the top pilots and the top pilot WINS. In a personal event every kill counts, even
  same-camp ones (FFA arenas). The web builder's first field picks the mode.
- Teams are the nations: `US GB SU GE JP` (or camp numbers 0-4). Each team has its own `objective`
  line (announced to that team when scoring starts) and its own `points` table; a top-level `points`
  table is the shared fallback for every team.
- Point keys, points per unit: `kill_fighter`, `kill_bomber`, `kill_any` (air kills, bombers/attackers/
  transports count as bombers); `scene_trigger`; `scene_capture`; `capture_specific {"46": 50}`;
  `hold_specific {"46": 1}` (per minute the team owns the scene); `scene_damage` (per 1 % of damage
  dealt to any scene); `damage_specific {"46": 2}` (per 1 % on that scene); `bridge`; `tank`; `train`;
  `troops_drop` (per troop chute landed); supplies: `supply_delivered` (per tonne landed and
  unloaded at a friendly field), `supply_airdrop` (per tonne air-dropped on a scene),
  `supply_specific {"46": 5}` (per tonne reaching that scene, either way - overrides the two
  generic keys), `building_repaired` (per building the delivery rebuilds).
- The web Events tab has a form builder above the JSON box: name / victory / report interval,
  a points grid (shared column + one column per team, blank = inherit), team objective lines,
  specific-scene rows (capture / hold per min / damage per % / supply per t) and the Pin Point
  Parachuting block and the message templates. The two stay in step both ways: form edits rewrite
  the JSON box, and anything typed or pasted into the box updates the form as soon as it parses
  (a half-typed script is left alone with a note; keys the form does not know are carried through).
  Save stores the JSON box, whichever way it was filled.
- Objectives: `{"type": "chute_on_target", "target": "PPS@HQ", "radius_m": 60, "points": 10}` - Pin
  Point Parachuting: a pilot who bails out and whose canopy lands within the radius of the target
  pilot's plane scores; misses are told their distance. Optional `"teams": ["GB"]`.
- Fox hunt: `{"type": "kill_target", "target": "FOX@FA", "points": 1}` - whoever shoots down the
  named pilot scores the points for their team, whatever camp either of them flies for (so the fox
  can sit on any team, or in an FFA arena), and the arena hears `FOX HUNT: <killer> bagged FOX@FA!
  GB +1 (fox down x3)`. The hunt is announced to the arena when scoring starts. The fox kill also
  earns the normal `kill_*` points if the table has them. Optional `"teams"` limits who can score.
  The web builder has a Fox hunt block (pilot, points, teams); there is a ready example script.
- `messages`: every arena broadcast the engine makes is a template you may override, e.g.
  `"messages": {"win": "And the winner is {winner}!", "personal": "-"}`. Keys: `start`, `personal`,
  `objective`, `fox_start`, `score_team`, `score_personal`, `fox_team`, `fox_personal`, `pps_hit`,
  `pps_miss`, `update`, `final`, `top`, `then`, `win`, `win_banner`, `draw`, `draw_banner`. Placeholders
  in braces (`{pilot} {team} {delta} {total} {what} {fox} {count} {name} {scores} {mins} {list}
  {winner} {dist} {target} {radius} {objective} {points}`) are filled at run time; `{delta}` carries its
  sign. A template of `-` silences that message. The web builder lists them all with their defaults
  and placeholders under *Message templates*. Unknown keys or broken braces are rejected at Save.
- Files: the builder's *Export to PC* downloads the script as `<name>.json`; *Load from PC* reads one
  back into the box and the form. The *Server library* keeps named scripts in `event_scripts/`
  next to server.py (shared by every arena): Save to server / Load / Download / Delete. Saving to the
  library validates the script with the engine's own parser. Loading from a file or the library only
  fills the box - the arena's Save button still stores it.
- `event scores <room>` prints the standings and pushes a report to the arena now; `event status`
  shows them too. Scene numbers are the terrain's scene indices (`tc status`, the map grid tools).

Scoring is on top of the normal ladder scoring - it does not replace it.

## Typical sequences

*Dogfight ladder with 3 lives:* web: tournament on, lives 3, ghosting on, joining 5, shooting 2, last one
flying wins -> `##JoinDisable` while briefing -> `##JoinEnable`; pilots spawn (clock starts) ->
`##EventClose` when the field is complete -> the clock (or `##EventFight`) starts the competition -> the
server announces the winner -> `##EventReset` (or `##ResetGame` for a full arena rebuild).

*Death Bowl (one life, air start, nobody shoots before the bell):* web: tournament on, lives 1, last one
flying wins, event mode on, "Engines free while locked" ticked, Fly button on; joining and shooting as you
like (0 / 0 is fine). Pilots enter and fly - engines run, weapons refuse. `##EventOpen 180` -> three
minutes of joining on every clock, then the shooting countdown, then the server frees the weapons and
calls FIGHT by itself. Or skip the clock: `##EventFight` when the field is complete. `##EventReset` for
the next round.

*Formation / race event without shooting:* event mode ticked, engines free -> pilots enter and form up
(`##FlyEnable` if the Fly button was left off) -> `##EventFight` for the combat part, `##EventHold` to
end it.

*Quick vote:* `poll start all 60 Next arena? | Pacific | Europe | Africa`.
