# Fighter Ace Server — Moderation

Documentation of the moderator/sysop system as currently enabled on the LAN server
(`fa with web server.py`). Covers how rights are granted, the in-game `##` commands, and
the server-console commands.

Last updated for server **v307**.

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

A moderator (a pilot with `admin_rights != 0`) types these in the game chat. The client
sends a packet to the server, which re-validates rights and acts.

### Enabled and enforced

| In-game command | Server effect | Notes |
| --- | --- | --- |
| `##Gag <player>` | Mutes the target's chat server-side. | See collision note below. |
| `##Ungag <player>` | Clears the mute. | |
| `##JoinDisable` | Marks the current room as join-disabled (Fly-Now suppressed). | Tracked server-side. |
| `##JoinEnable` | Clears join-disable for the room. | |
| `##AllChatOn` / `##AllChatOff` | Records the all-chat toggle for the room. | |

**Gag behavior:** a gagged player's chat is dropped at the server's authoritative reflect
point, so it never reaches anyone (the player sees their own text vanish, matching retail
behavior). **Moderators are never gaggable.** Duration from the command: `0` = soft/no-op,
open-ended, or up to a documented **12-hour** maximum.

### The `##Ban` / `##Gag` wire collision (important)

`##Ban` and `##Gag` send the **byte-identical** packet (opcode `0x55`, same layout). The
server physically cannot tell them apart. By design decision, **inbound `0x55` is treated
as GAG**. Therefore:

- **In-game `##Ban` currently acts as a gag (chat mute), not a room ban.**
- **Real bans come from the server console** (see §4).

### Logged but not yet enacted (relay-only)

These target a **remote** client and cannot be validated on a single machine (the client's
own name-resolver walks the remote roster, which excludes the moderator themselves). They
are decoded and logged, but do not yet produce an effect:

| In-game command | Wire opcode | Status |
| --- | --- | --- |
| `##crumblep <player>` (explode plane) | `0x80` sub `0x01` | Logged only |
| `##nofuelp <player>` (drain fuel) | `0x80` sub `0x02` | Logged only |
| `##ejectp <player>` (force bail) | `0x80` sub `0x03` | Logged only |
| `##killp <player>` (kill pilot) | `0x80` sub `0x04` | Logged only |
| `##Ghost` / `##GhostAll` | `0x8d` | Logged only |
| `##Chime`, `##Smoke` | `0x8c` / `0x91` | Logged only |

Enacting these requires the outbound plane-destroy format, which needs a two-client capture
to complete. See §6.

---

## 4. Server-console moderation commands

Typed at the server's console (stdin). These are the authoritative, fully-enacted actions.

### Bans

| Command | Effect |
| --- | --- |
| `ban <pilot> [hours] [message...]` | Ban a pilot. Kicks any live session and blocks re-entry until expiry. |
| `unban <pilot>` | Lift a ban. |
| `bans` | List active bans (remaining time, who set it, reason). |

**`ban` argument rules**

- `hours` is optional. Omitted or `0` = **open-ended**; otherwise N hours, capped at 12.
- The token after the pilot name is treated as `hours` **only if it is numeric**; otherwise
  it becomes the first word of the message. So both of these work:
  - `ban Bob spamming` → open-ended ban, reason "spamming"
  - `ban Bob 2 team killing` → 2-hour ban, reason "team killing"
- `message` is optional and shown to the banned player.

**What the banned player sees**

- On kick: a private system chat line, e.g.
  `You have been banned by a sysop (2h): team killing`
- On any reconnect + pilot-select while still banned:
  `You are banned (Nmin remaining): team killing`

The notice is delivered reliably (server waits for the client's ACK) **before** the session
is torn down, so it renders before the connection goes quiet. Moderators are exempt from the
ban list.

> Edit note: a purely numeric pilot name would be misread as `hours`. FA pilot names are
> never purely numeric, so this does not occur in practice.

### Gags (view)

| Command | Effect |
| --- | --- |
| `gags` | List active gags and remaining time. |

(Gags themselves are applied in-game via `##Gag`; see §3.)

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

**Console — moderation:**

```
mod <pilot> [rights]        grant moderator rights (non-zero = full mod)
unmod <pilot>               revoke (effective on reconnect)
mods                        list moderators (+ online status)
ban <pilot> [hours] [msg]   ban: kick + block re-entry + notice
unban <pilot>               lift a ban
bans                        list active bans
gags                        list active gags
```

**In-game (moderator, `MyRights != 0`):**

```
##Gag <player>              mute chat (also what ##Ban maps to)
##Ungag <player>            unmute
##JoinDisable / ##JoinEnable    toggle Fly-Now for the room
##AllChatOn / ##AllChatOff      toggle all-chat for the room
```

---

## 6. Not yet implemented

- **Plane-destroy relay** (`##crumblep` / `##killp` / `##ejectp` / `##nofuelp`): needs the
  outbound destroy packet format, which requires a two-client capture to finalize (msg 36
  is scene-object only and cannot target a player plane).
- **Ghost / Chime / Smoke** relay to remote clients.
- **Native ban dialog:** FA has a built-in `EVENT_BANNED_PLAYER` event and
  `CAN_BANNED_DIALOGS` UI, but its text is data-driven from the packed `*.str` resource and
  its trigger is buried in the C++ event machinery. The current chat-line notice is the
  practical substitute.
- **JoinDisable / AllChat enforcement:** the toggles are recorded server-side but not yet
  wired into the actual Fly-Now / chat gating.
- **Sysop roster section:** moderators are not yet grouped under the client's dedicated
  "sysop" section in the roster. The client files a player there when the server reports
  their **camp = -2** (`C_SYSOPS`; normal nations are 0..7, "In Menu" is -1). Camp rides the
  player-object layer (msg 63, `rp->Camp()` at player+0x2c), not the `0xcc` lobby update.
  Wiring this means emitting camp -2 for `admin_rights != 0` pilots in the roster message,
  carefully gated so -2 never reaches nation-indexed logic. Tracked in the code TODO block.

---

## 7. Configuration

At the top of the moderator section in `fa with web server.py`:

| Flag | Default | Meaning |
| --- | --- | --- |
| `MODERATORS_ENABLED` | `True` | Master kill-switch for the whole moderator layer. |
| `MOD_RIGHTS_DEFAULT` | `1` | Value written by `mod <pilot>` when no rights value is given. |

Ban and gag state is held in memory (`BANS`, `GAGS`) and does not currently persist across
a server restart.
