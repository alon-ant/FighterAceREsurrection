# Running an event on Fighter Ace REsurrection (v958f5)

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
| Event mode | Event mode: weapons locked until the host starts the event | the arena begins locked (see step 4); arenas without it have no event timers at all |
| Event mode | Unlock N min after the event start | delay with an "in MM:SS" countdown on the client |
| Event mode | Fly button enabled from the start | untick = the HQ Fly button is grey until enabled |
| Event mode | Event length (min) | counted from the start of the fight; when it elapses the server ends the event (tournament finished - fewest deaths wins, tie = draw - and weapons locked, "EVENT OVER"); 5-min and 1-min warnings; 0 = until `event end`/`hold` by hand |

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

## 3. Running it: one command, seven verbs

Everything below is `event <verb> <room>`; each verb does whatever applies to the arena (tournament
clock, weapons lock, or both). `##StartEvent` in game equals `event fight`.

| Command | Tournament arena | Event-mode arena (weapons lock) |
| --- | --- | --- |
| `event open <room> [in <s>]` | clock starts: joining window, then shooting countdown (the first spawn does this by itself) | weapons locked, waiting for `fight` |
| `event close <room>` | joining closed now; the shooting countdown runs | - |
| `event fight <room> [in <s>]` | competition now: guns, collisions, lives | weapons free (`in <s>` = native countdown on the clients) |
| `event hold <room>` | - | weapons locked again |
| `event end <room> [winner]` | tournament finished, winner announced | - |
| `event reset <room>` | cleared; the next spawn re-opens | back to locked |
| `event fly <room> on\|off` | - | the HQ Fly button |
| `event status [room]` | phase, participants, deaths, ghosts, time left, script standings | locked / free, fly button, time left |
| `event scores <room>` | script standings + a report pushed to the arena now | - |

During the competition the server counts lives (crash, collision, bail, shot down; exit to HQ too when
tabbing is not allowed), refuses Fly asks from latecomers and from pilots out of lives (ghosts are
re-ghosted on their next plane), and with "last one flying wins" sends the result and the banner.
Moderators never count and are never refused.

## 4. The weapons lock, in short

Only arenas with event mode ticked on the web have it. They are entered locked ("Event not started
yet!"): a pilot can take off but cannot start engines, fire guns, launch rockets, drop bombs or
torpedoes, deploy paratroopers or drop supplies. `event fight` frees everything (after the arena's
"unlock N min" delay, which the client counts down as "Event will be started in MM:SS"); `event hold`
locks again. A pilot already airborne keeps his running engine when the lock lands but cannot fire; a
pilot who entered before the setting was ticked keeps his old arena data until he re-enters (the
server tells everyone inside when a setting is saved).

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
| `event reset <room>` | tournament cleared, weapons locked again; the next spawn re-opens |
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
`event close 149` when the field is complete -> `event fight 149` -> the server announces the winner
-> `event reset 149` (or `##ResetGame` for a full arena rebuild).

*Formation / race event without shooting:* event mode ticked on the web -> pilots enter locked and form
up (`event fly 149 on` if the Fly button was left off) -> `event fight 149` for the combat part,
`event hold 149` to end it.

*Quick vote:* `poll start all 60 Next arena? | Pacific | Europe | Africa`.
