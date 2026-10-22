# Event Scripting - a guide for moderators (v958f5f)

An **event script** tells the server how to keep score during an event: what earns points, whether
teams or individual pilots compete, what the arena is told after every score, how often a progress
report goes out, and who wins at the end. The script is a small text block attached to one arena;
you build it with a form on the web admin, no programming needed. The engine does not touch the
normal ladder - it is an extra scoreboard, announced in the arena chat, that lives for one event.

How it fits with the rest of the event tooling (see EVENTS.md for the command chain):

```
web: Admin -> arena -> Settings -> Events tab      write / load the script, tick event or tournament mode, Save
   |
pilots re-enter the arena                          (settings reach a client on entry)
   |
event open 149  ->  event fight 149                scoring STARTS when the fight starts
   |      every award: a chat line (and the log)
   |      every N minutes: "EVENT UPDATE" with the standings + cockpit banner
   |      event scores 149 / event status 149       look at the board at any time
   v
event length elapses, or  event end 149            FINAL standings, "GB WINS" / "Bigalon WINS" / draw
```

---

## 1. Where the script lives: the Events tab

Open the arena on the web admin (Admin -> arena -> Settings) and pick the **Events** tab. From top
to bottom:

1. **Tournament / Event mode settings** - the clock, lives, the weapons lock, the event length.
   The script needs one of them: scoring starts at the *fight* (the tournament's competition start,
   or `event fight` in an event-mode arena). An arena with neither has no fight, so no scoring.
2. **Script builder** - the form. Everything you fill in is written into the JSON box below it as
   you type; everything you type or paste into the JSON box flows back into the form the moment it
   is valid. Use whichever you like, they are the same script.
3. **JSON box** - the script itself, as text. This is what the arena's **Save** button stores.
4. **Example scripts** (fold-out) - four ready scripts to copy from.
5. **Files**: *Export to PC* downloads the script as `<name>.json`; *Load from PC* reads such a file
   back into the box and the form.
6. **Server library**: named scripts kept on the server (folder `event_scripts/` next to server.py),
   shared by every arena: pick one and *Load*, *Download* or *Delete*; type a name and *Save to
   server* to add the current script.

Loading from a file or from the library only fills the box - press the arena's **Save** to store it on
the arena. Save checks the script with the same rules the engine uses and refuses it with a plain
message if something is wrong (nothing else on the page is saved in that case). An empty box means
"no script" for that arena.

After a save, pilots already in the arena are told to re-enter; the script itself is read fresh at
each `event fight`, so a script change between rounds needs no re-entry.

---

## 2. Ready recipes

**Fox hunt (personal).** Whoever shoots down FOX@FA gets a point; ordinary kills are worth half.
Builder: Scoring = *personal event*; Winner has *most points*; *Shoot down a fighter* = 0.5 (All
teams column); Fox hunt block: Fox pilot `FOX@FA`, Points 1. The arena hears
`FOX HUNT: shoot down FOX@FA for 1 pts!` at the start and `FOX HUNT: Zed bagged FOX@FA! +1 (total 2,
fox down x3)` on every fox kill; the top pilot wins.

**Pin Point Parachuting (personal).** Bail out and land the canopy on PPS@HQ's parked plane.
Builder: *personal event*; Pin Point Parachuting block: Target pilot `PPS@HQ`, Within 60 m, Points 10.
A hit announces `Bigalon +10 (total 20): landed 12 m from PPS@HQ`; a miss tells only the jumper his
distance (`Missed: 140 m from PPS@HQ (target 60 m).`). The target pilot must be in the arena, in a
plane, when the chutes come down.

**Battle of Britain (team).** GE bombs, GB defends. Builder: *team event*; shared column: fighter 1,
bomber 2; GB column: bomber 4; GE column: *Damage a scene* 0.5 per % plus specific-scene rows for
the radar sites (scene numbers, Damage /% = 2); objectives `Stop the raids - every bomber counts
double` (GB) and `Bomb the radar chain and the sector airfields` (GE). Each team hears its own
objective at the start; the best team wins.

**Capture the front (team).** One shared table for every team: captures 5, the key scene 50 and
1 point per minute holding it, tanks 2, trains 3, bridges 5, troop drops 1, supplies 2 per tonne.

All four are in the Example scripts fold-out and in the server library.

---

## 3. The building blocks

### Scoring mode
- **Team event** (default): points go to the pilot's nation (US, GB, SU, GE, JP). Standings are the
  teams; the best team wins. Only kills on the *other* side count.
- **Personal event**: every pilot scores for themselves. Standings are pilots; the top pilot wins.
  Every kill counts, same-camp ones too (so FFA-style arenas work). The *All teams* points column
  is all you need; team columns and objectives are ignored for scoring (objectives are still
  announced).

### Winner has
- **most points** - the sum of everything in the points tables and objectives.
- **most air kills** - only shoot-downs count for the win (points are still shown).
- **no winner** - scores and reports, but no "WINS" line at the end (training, demos).
A tie is announced as a draw.

### Progress update every N min
`EVENT UPDATE (30 min) - Battle of Britain: GB 42  GE 37` plus the top pilots and a cockpit banner,
every N minutes from the fight start. 0 = no automatic updates (`event scores <room>` still works).

### Announce every score
Ticked: each award is a chat line in the arena (`GB +3: Bigalon shot down Hans (bomber)`). Untick for
a quiet event where only the updates and the final board are shown. Fox-hunt lines are always shown.

### Points per action
Each cell is *points per unit*; blank = 0 = not scored. The **All teams** column is the shared table;
a team's own column overrides it for that team only (a blank team cell inherits the shared value).

| Action | Unit | Notes |
| --- | --- | --- |
| Shoot down a fighter | per kill | the victim was flying a fighter |
| Shoot down a bomber | per kill | bombers, attackers and transports |
| Any air kill | per kill | used only when the two above are blank |
| Trigger a scene | per trigger | the TC scene-trigger (the AI "trigger" message) |
| Capture a scene | per capture | any scene changing hands to the pilot's side |
| Damage a scene | per 1 % | damage dealt to any scene's structures |
| Destroy a bridge / tank / train | per kill | TC objects |
| Land a troop chute | per paratroop chute | troops landed, any scene |
| Deliver supplies by landing | per tonne | landed and unloaded at a friendly field |
| Air-drop supplies | per tonne | dropped by parachute onto a scene |
| Building rebuilt by a delivery | per building | when a delivery repairs a structure |

Decimals are fine (0.5, 2.5). Points can be negative if you want a penalty.

### Specific scenes
One row per scene you care about: the scene number, then points for **capturing it**, **per minute
holding it** (paid every minute to the owning team while the fight is on), **per 1 % damage** on it
and **per tonne of supplies** reaching it. A specific-scene value replaces the generic one for that
scene (so the key scene can be worth 50 while others stay at 5). Scene numbers: `tc status` on the
console, or the map tools - they are the terrain's scene indices.

### Team objectives
A free line per team, shown to that team only when scoring starts (`GB objective: Stop the raids`).
A team takes part in the standings when it has an objective or any points of its own; otherwise it
appears when it first scores.

### Pin Point Parachuting
Target pilot (exact name, case does not matter), radius in metres, points per hit, and optionally the
teams allowed to score. The jumper's own canopy must come down within the radius of the target's
*plane*; the target must therefore be in the arena, in a plane, parked where the jumpers can aim.
Misses are told their distance privately.

### Fox hunt
Fox pilot, points per fox kill, optional teams. Any pilot of any camp who shoots the fox down scores
for his team (or himself in a personal event), whatever camp the fox flies for. The fox kill also
earns the ordinary kill points if the table has them. A running "fox down xN" counter is shown.

---

## 4. What the pilots see - and how to change the wording

Every line the engine sends to the arena is a template you may rewrite under **Message templates**
(fold-out at the bottom of the builder). Leave a field blank for the default text; type a single `-`
to silence that message. Words in braces are filled in at run time; the game cuts chat lines at 74
characters, so keep them short.

| Key | Default | When | Placeholders |
| --- | --- | --- | --- |
| start | EVENT "{name}" is ON - scoring started. | fight starts | name |
| personal | PERSONAL EVENT - every pilot scores for themselves. | fight starts, personal mode | name |
| objective | {team} objective: {objective} | fight starts, to that team | team objective |
| fox_start | FOX HUNT: shoot down {fox} for {points} pts! | fight starts, fox hunt | fox points |
| score_team | {team} {delta}: {pilot} {what} | every award, team mode | team delta pilot what total |
| score_personal | {pilot} {delta} (total {total}): {what} | every award, personal mode | pilot delta total what team |
| fox_team / fox_personal | FOX HUNT: {pilot} bagged {fox}! ... | fox kill | pilot fox team delta total count |
| pps_hit | landed {dist} m from {target} | the "what" of a PPS score | dist target radius pilot |
| pps_miss | Missed: {dist} m from {target} (target {radius} m). | private, to the jumper | dist target radius pilot |
| update / final | EVENT UPDATE ({mins} min) - {name}: {scores} / FINAL - {name}: {scores} | reports | mins name scores |
| top / then | Top: {list} / Then: {list} | reports (team: top 3 pilots; personal: places 4-8) | list |
| win / win_banner | {winner} WINS "{name}"! / {winner} WINS | the end | winner name |
| draw / draw_banner | "{name}" ends in a draw. / DRAW | the end | name |

`{delta}` already carries its sign (`+3`), `{total}` is the scorer's running total, `{what}` is the
deed (`shot down Hans (bomber)`, `captured Dover (46)`, `delivered 1500 kg to Lille (12)`...).
A placeholder the message does not know is left as typed; a broken brace is refused at Save.

Example - a louder fox hunt:
```json
"messages": {"fox_personal": "*** {pilot} got the FOX ({count}x) - {total} pts ***",
             "win": "And the winner is {winner}!", "personal": "-"}
```

---

## 5. Running it

| Moment | What the script does |
| --- | --- |
| `event open <room>` / pilots spawn | nothing yet - the board is empty until the fight |
| `event fight <room>` (or the tournament's competition start, or `##StartEvent`) | scoring starts from zero: start lines, objectives, fox-hunt notice |
| during the fight | awards announced, updates every N min, hold points every minute |
| `event scores <room>` | prints the standings on the console and pushes an update to the arena now |
| `event status <room>` | script name, mode, time since start, standings, top 10 pilots |
| `event hold <room>` | weapons locked; the board keeps its scores (nothing can be scored anyway) |
| event length elapses or `event end <room>` | FINAL update, winner (or draw), banner; the board is frozen |
| `event fight <room>` again | a new round - the board starts from zero |
| `event reset <room>` / arena reset | board wiped |

Only pilots inside the arena score; a pilot who leaves keeps his points. Moderators score like anyone
else - fly as a referee on the neutral side, or in a plane that cannot score, if that matters.

---

## 6. Checklist and troubleshooting

- **Save refused** - the message names the problem (`unknown team "UK"`, `message "win": bad
  braces`, `objective kill_target needs a "target"`). Fix and Save again; teams are `US GB SU GE JP`.
- **No scoring at all** - was there a fight? `event status <room>` says `scoring NOT running (starts
  at event fight)`. Event mode or tournament mode must be ticked and the fight started.
- **Scores but no chat lines** - *announce every score* is off, or the template was silenced with `-`.
- **PPS hits never land** - the log says `target "PPS@HQ" not in the arena` or `has no position yet`:
  the target must be in the arena in a plane. Check the exact pilot name.
- **Fox kills not counted** - the fox's name must match exactly (case does not matter); the fox hunt
  needs no team setup. A kill by a pilot outside the allowed teams is ignored on purpose.
- **Wrong scene** - scene numbers come from `tc status` / the map; a number the terrain does not
  have simply never scores.
- **Pilots say nothing changed** - settings reach a client on entry; the script is re-read at every
  `event fight`, the arena settings (modes, length) only on re-entry.
- Every award is also in the server log as an `EVS` line with the running score - the place to settle
  arguments afterwards.

---

## 7. The script as text (for the JSON box)

```json
{
  "name": "Battle of Britain",          // shown in the announcements
  "mode": "team",                       // team | personal
  "victory": "points",                  // points | kills | none
  "report_min": 30,                     // 0 = no automatic updates
  "announce": true,
  "points": {                           // shared table - see section 3 for every key
    "kill_fighter": 1, "kill_bomber": 2, "kill_any": 0,
    "scene_trigger": 0, "scene_capture": 5, "scene_damage": 0,
    "capture_specific": {"46": 50}, "hold_specific": {"46": 1},
    "damage_specific": {"46": 2}, "supply_specific": {"12": 5},
    "bridge": 5, "tank": 2, "train": 3, "troops_drop": 1,
    "supply_delivered": 2, "supply_airdrop": 1, "building_repaired": 1
  },
  "teams": {                            // optional, per team: objective + overrides
    "GB": {"objective": "Stop the raids", "points": {"kill_bomber": 4}},
    "GE": {"objective": "Bomb the radar chain", "points": {"scene_damage": 0.5}}
  },
  "objectives": [                       // optional
    {"type": "chute_on_target", "target": "PPS@HQ", "radius_m": 60, "points": 10, "teams": ["GB"]},
    {"type": "kill_target", "target": "FOX@FA", "points": 1}
  ],
  "messages": {"win": "And the winner is {winner}!"}   // optional, see section 4
}
```
(JSON itself does not allow the `//` comments - they are here for reading only; the builder writes
clean JSON for you.) Keys you leave out take their defaults; keys the builder does not know are kept
untouched, so a note such as `"author": "Taurus"` survives form edits.
