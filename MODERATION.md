# Fighter Ace Server — Moderation

Documentation of the moderator/sysop system as currently enabled on the LAN server
(`fa with web server.py`). Covers how rights are granted, the in-game `##` commands, and
the server-console commands.

Last updated for server **v950f5**.

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
| 500 | 1 | Chime01 | - | (not analysed - was skipped as "mis-listed" in the first pass) |
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

### Not modelled

`##ClearScores` (arena scores live in the ladder), `##Ghost`/`##Chime`/`##Smoke` relay forms (logged
only), the long 0xDA form that would show *banned for all games* in the lobby dialogs.

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
| `help [word]` | Every console command by section; `help ban` filters. |

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
```

---

## 6. Still open

- **Lobby "for all games" dialogs**: the client reads GagAll/BanAll minutes from a 25-byte 0xDA
  lobby attach (offsets +0xd / +0x11); we send the 15-byte safe form, so a globally banned pilot
  is kicked at pilot select instead of seeing that dialog.
- **Sysop roster section** (camp -2 for moderators) — unchanged, see the code TODO.

---

## 7. Configuration

At the top of the moderator section in `fa with web server.py`:

| Flag | Default | Meaning |
| --- | --- | --- |
| `MODERATORS_ENABLED` | `True` | Master kill-switch for the whole moderator layer. |
| `MOD_RIGHTS_DEFAULT` | `1` | Value written by `mod <pilot>` when no rights value is given. |

Ban and gag state (`BANS`, `GAGS`, with their scope) persists in `moderation_state.json`.
