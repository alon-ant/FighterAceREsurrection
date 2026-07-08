#!/usr/bin/env python3
r"""
Fighter Ace LAN Server v200
===========================
v200: PvE part 2 - SCENE-DESTROY (msg 36) builder + broadcast, and a live-validatable
      'destroy' console command. Grounded in the 2009 live-server logs (messages04): the
      real destroy loop is  out 28 (hit) + out 31 (ground-damage report) -> in 36 (server's
      authoritative SCENE DESTROY/STATE) -> client prints 'You have destroyed GER Birchwood'.
      msg 36 (0x24) handler LAB_004f9d90 decoded: wire = [0x24] then N x 7-byte records
      [sceneIdx u16 LE][camp/0xFF u8][progress f32]; camp 0xFF = neutralized/destroyed,
      progress <= 0 flips the scene to captured. It is delivered through the IN-GAME VNET
      dispatch (FUN_004f18a0) which passes the TRUE message length (not bc*16+1) - the live
      'in 36'8' = exactly one 7-byte record - so msg 36 is framed with build_ingame_pkt
      (Size == n), NOT the appspace bc*16+1 tiler.
        * build_scene_destroy_36(scene_idx, camp, progress) - the 8-byte-per-record builder.
        * broadcast_scene_36(room_id, ...) - reliable send to everyone in the room.
        * console 'destroy <sceneIdx> [camp] [progress]' - fire msg 36 at a KNOWN scene index
          (e.g. 30 = 'Bomber Airfield' on TRN02) to validate the wire format in isolation,
          with ZERO dependence on the still-unconfirmed msg-31 objidx->sceneIdx mapping.
      Per-scene HP store (SCENE_HP) + auto-destroy-on-depletion logic is implemented but
      GATED OFF (AUTO_SCENE_DESTROY=False): msg 31 reports a finer per-piece object index
      (129/130/376) whose relation to the 0-59 scene index is not yet confirmed, and sending
      msg 36 with an out-of-range sceneIdx trips the client's bounds assert. The gate stays
      off until the next live capture (v199 GROUND31 logs) pins the mapping.
v199: PvE groundwork, part 1 + 5-MINUTE SESSION-DEATH fix.
      (1) msg 31 (0x1f) = GROUND-OBJECT DAMAGE REPORT is now consumed and decoded, never
      echoed. The client has NO inbound handler for 31 (dispatch slot 0xc81f54 is set to 0
      unconditionally in FUN_004f1240), so v198's generic echo raised 'NET::MESSAGE with
      Unknown Type 31' on every strafing/bomb/crash report (messages17). Records are 6 bytes:
      [attacker ONumber u16 LE][target static-object idx u8][event u8, 0x05 seen][damage u16
      LE] - observed: strafing dmg 92..1239 on objs 129/130, bomb splash = two records in one
      msg, fuel-tank crash = obj 120 dmg 9976. Consumed in all three arrival forms (direct
      sub=0x1f, type-scan pl[8]=0x1f, compound inner). v199 logs + accumulates per-object HP
      server-side (GROUND_HP dict, no client notify yet - that's part 2).
      (2) THE 300s DEADLINE: the post-auth drain loop ran 'while time.time()<deadline' with
      deadline=login+300s, so five minutes after login the server silently stopped PROCESSING
      reliable messages (still ACKing them!) - all msg-31s of the second flight, the exit-
      appspace and the disconnect of session 01-Jul were RELRX-logged but never handled
      ('Can't exit AppSpace' / 'Can't disconnect server' client errors). Loop now runs until
      s.closing.
v198: BAIL-OUT respawn fix, part 3 (completes v196/v197). v197 kept the object NUMBER in
      lock-step by consuming one for the parachute, but did NOT advance the spawn IDENT -
      and the client's local object-registration ident advances for EVERY object it creates,
      parachute included (out-4 payloads: plane1=ident 0, parachute=ident 1, plane2=ident 2).
      The respawn's ServerConfirm therefore carried ident=1 while the fresh plane was
      registered under ident 2 -> FUN_007e5030 found no local object with ident 1 ->
      'Confirm object 258 not found in list, send delete' (messages08) -> fresh plane deleted,
      sim loop never started, dead engine. Fix: the ident is IN the client's out-4 payload
      (u16 LE right after the 0x04 msg-id: pl[5:7] direct, pl[9:11] on the type-scan
      double-wrapped re-spawn form) - parse and ECHO it instead of trusting a server-side
      counter; the counter remains only as a fallback and is resynced from the parachute's
      out-4 ident field too.
v197: BAIL-OUT respawn fix, part 2 (completes v196). v196 stopped echoing the parachute's
      msg-4 (killing the 'Unsupported message 4' error) but SWALLOWED it outright - and the
      client allocates a fresh object Number for the parachute, so the server's Number counter
      then ran one BEHIND. The next respawn's ServerConfirm carried the stale Number (259 vs the
      client's 260) -> 'Confirm object 259 not found in list -> send delete' -> fresh plane deleted,
      dead engine. Now the parachute out-4 (type=0xf2 sub=0x04) CONSUMES a Number to stay in
      lock-step with the client (still no echo, no confirm, no spawn-ident advance).
v196: BAIL-OUT respawn fix. On a bail the client spawns the parachute pilot and sends its
      object state as msg-4 wrapped type=0xf2 sub=0x04 (out 4'15). That fell through to the
      generic echo -> the client received an echoed msg-4 -> 'ERROR: Unsupported message 4',
      which CORRUPTED its object list, so the next spawn's ServerConfirm was refused ('Confirm
      object 260 not found in list -> send delete') and the fresh plane was deleted (dead engine,
      teardown). msg-4 is the client's OWN object state and must NEVER be echoed - the normal
      spawn out-4 (type=0x12) is ServerConfirmed; any other sub=0x04 is now swallowed.
v195: RESPAWN-AFTER-CRASHLAND fix, part 3 (the actual one). v193/v194 fixed the DIRECT msg-3
      death path, but the log showed the crashland delete arrives WRAPPED - outer type=0x06,
      inner sub=0x03 - which hit the type-scan 'notify -> swallow' branch and bypassed the death
      handler entirely, so obj_confirmed was never re-armed and the respawn's out 4 still got no
      ServerConfirm (Conductor error, dead engine, CTD). The in-arena own-plane-removal logic
      (drop plane + stay in arena + re-arm obj_confirmed/flying) is now a shared helper
      _ingame_own_object_removed, called from BOTH the direct tb=0x42/0x52/0x32 path and the
      wrapped scan-inner (outer 0x06) path.
v194: RESPAWN-AFTER-CRASHLAND fix, part 2 (completes v193). A crashland respawn does
      InsertPlayer + out 4 with NO fresh StartPlace (the plane is on the ground, client
      continues in place), so obj_confirmed stayed True from the prior spawn and
      _fire_server_confirm gated the out-4 out -> no ServerConfirm -> Conductor error ('Server
      sent client something it doesn't understand'), engine-start ignored, then CTD. Now the
      msg-3 death handler ALSO re-arms obj_confirmed/flying = False, so the next out 4 confirms
      a fresh object whether or not a StartPlace preceded it. (v193 kept entered_game=True so
      the out-4 handler still runs; both are required.)
v193: RESPAWN-AFTER-CRASHLAND fix - the msg-3 own-plane delete used s.flying to tell a death
      from an exit-to-HQ, but a CRASHLAND (off-runway, over-speed damage) sends no respawn
      StartPlace first, so flying stayed True and the death was mis-handled as an exit ->
      handle_leave_arena cleared entered_game / sent the 0xDA handoff and BROKE the next
      respawn (engine-start ignored, in-game base-switch gone, only a full rejoin recovered).
      Now ANY in-arena own-plane removal is treated as a death: drop the dead plane on peers
      and stay in the arena so respawns work in place. Real leave-to-lobby still comes as
      msg-64 and tears down normally.
v192: WEB ARENA SETTINGS EDITOR - '[gear] Edit Settings' button on each arena in the web /admin
      panel opens a per-arena editor (name, section-header/title, status + GAME_DEF settings).
      Wired settings so far: the 7 visual ranges (fighters/bombers/tanks/plane-tags/other-tags/
      padlock/chat) and the 2 oxygen ceilings (with/without mask), edited in feet. These live in
      the fixed 173-byte post-plane-block GAME_DEF tail (float32 metres), located per-arena via
      _gamedef_plane_block so offsets hold across arenas (verified byte-identical on TC/Nations/
      FFA). Edits are stored as {key:feet} JSON in a new rooms.settings_json column and APPLIED
      AT 212 SERVE TIME in build_lz_gamedef (in-place float writes - original blob never mutated,
      212 stays bc*16+1 aligned). Take effect on the next arena entry. Pre-block settings
      (checkboxes/dropdowns/physics/weather) are variable-offset and not yet wired.
v191: Arena-creation AUTO-JOIN fix - the CREATE flow sends no 0xc8 SendEnterToGame; the client
      drives entry off the 1-Hz 0x43 game-connect poll and waits for a JoinToGameAnswer 201 to
      clear it. We only echoed 'room confirm', so the poll never stopped -> ~15s soft timeout ->
      client exits. Now the creator's first post-create 0x43 poll grants the 201 (enter game
      mode, alloc ClientNumber/PlayerIndex, stand up player-object layer), same as the 0xc8
      path. Gated by a create-only flag; join/lobby polls untouched. (In-arena OPTIONS still
      read-only - that is FA's peer-host 'am I the arena host?' check, tracked separately.)
v190: Arena-list category grouping fix - the 0xd2 block-boundary pad was appended to the LAST
      record's name1 (the CATEGORY the client groups rows under), so a shared category split
      into a duplicate 'Dogfighting   Arenas' header. Pad now lands on name2 (display label,
      invisible), keeping every category byte-clean so same-category arenas group together.
v189: STABLE MILESTONE - 2-player flight + team changes + crash recovery.
      * Per-side plane catalog now echoed as 3-byte [planeID][ushort] records so the client's
        msg-58 reader (len-1)/3 ingests every kept plane (GE bombers no longer dropped).
      * Telemetry relay marker is size-independent (cmd==0, opcode 0x07, T&0x0f==2, scan off
        0/4) - fixes asymmetric visibility (both clients now see each other).
      * Team-change roster: broadcast on current_room (not entered_game) so switches made at
        team-select propagate; self-63 sent JOIN-only (neutral echo caused a lobby-bail loop);
        no-op dedup so reliable retransmits of the same side don't re-broadcast (flood/CTD).
      * Server crash-recovery: SIO_UDP_CONNRESET disabled on Windows (a client CTD no longer
        starves recvfrom -> reconnect gets a populated pilot/arena list without a restart);
        Linux is immune by default. Reconnect reaps the stale same-account ghost session.
      Known-rough (deferred, non-blocking): reliable-seq wrap wedge after a very long single
      segment (~250 pkts, no re-entry); exit-to-lobby re-entry reliable desync on that path.
v188: FFA neutral-team guard (camps AllianceVar collapse at serve time); GAMEDEF_DEBUG
      flag gates the per-build decompressed-hex dump (default off).

TODO list:
  [x] SYN structure mapped (offsets confirmed)
  [x] Pilot creation/rename/delete (0xe2/0xe7/0xe3) saved to DB
  [x] Ticket generation: gen <name> at server console -> ticket_<name>.vr1
  [x] Chat: broadcast as APPSPACE sub=0xcd with pilot name
  [x] Lobby UI List: 0xcc LmsChangePlayers mapped (join/leave broadcasts)
  [x] Room creation: compound cmd=18 inner type=0x92/sub=0xdc stored in DB
  [x] Room list (0xce): sends actual room data via build_ce_room_list
  [x] Room confirm (0x43): slot=room_slot player_count from DB
  [x] VNET::SendEnterToGame: bc=2 type=0x82 sub=0xc8 detected; not echoed (prevents crash)
  [x] Player-object layer (v182 -> fixed v183 -> fixed v184): msg 62 AddPlayer /
      63 ChangePlayerCB / 96 ScoreTable, decoded from VNet_Rcv.cpp (FUN_004fa5f0 /
      FUN_004fa9c0 / FUN_00629600). 62 creates REMOTE_PLAYER, 63 op=1 sets side
      (rp->Camp() @ player+0x2c). Side membership was msg 63 all along - NOT msg 58
      (v175's guess); msg 58 is a LobbyRcv list, not the arena side-setter.
      v183 FIX: v182 crashed on side-select (op=2 hit the DELETE path, not camp; and
      the 63 was sent to the player about itself). op=CAMP is 1; 63 is peers-only.
      v184 FIX: v183 crashed on arena-JOIN - it sent msg 96 (ScoreTable) on the 201
      grant, which frees+reallocates the host-side score-table object before the
      client's world exists (3s stall -> WinError 10054). 96 is now DEFERRED; the 62
      stand-up self-gates to no-ops when alone, so lone entry == known-good v182 path.
      v185: layer made REQUEST-DRIVEN. bare 0x60 after FLY grant = ScoreTable request
      -> answer msg 96 (v184 left it unanswered -> no launch timer, CTD ~20s).
      v186: INVARIANT added - 62 to client X never carries X's own index; 0x66
      swallowed; self-63 kept as the team-change mechanism.
      v187 ROOT CAUSE: every player-object CTD (v182 side-select, v183 join, v185/v186
      team) was ONE bug - the client delivers Length=bc*16+1 to handlers, NOT the
      datagram length (proven in vcncnet...510.log: our 8B msg 63 arrived as Size=17
      with 9B of stale-buffer garbage, parsed as phantom records -> ScoreTable/VNet_Rcv
      "Length>=0" fatal assert -> DLL_PROCESS_DETACH). build_appspace_pkt_exact was a
      fiction; the client ignores real length. FIX: 62/63/96 now TILE to bc*16+1 with
      parser-valid padding - 63 pads to a multiple of 16 dummy-index records, 62 pads
      the last record's unused trailing string, 96 appends one pad group (9+7N bytes).
      Also fixed a 96 count off-by-one (parser loops count+1). The v183 "premature
      world state" and v185 "use-after-free" theories were both wrong: it was framing.
  [x] LOBBY/ARENA SERVER COMPLETE (v187). Verified live: auth, pilot mgmt, rooms,
      arena list, 212 GAME_DEF, player-object layer (62/63/96), team select (chat
      line + side color), chat, the FLY StartPlace grant (msg 23). The client reaches
      the runway with a plane assigned. This is the milestone stopping point.

  -- BOUNDARY: entering the flyable world needs the GAME-SERVER CHANNEL (new work) --
  The FLY -> spawn path is NOT a packet bug. On fly, FUN_004f6320 passes the spawn
  gate (worldobj exists, -0x1700 "ready" flag set by arena entry) and calls
  FUN_004e9fa0, which invokes the SIM CONDUCTOR at worldobj+0x1800:
        (**(code**)(*(worldobj+0x1800)+0x6c))(...)   <- null-vtable CTD
  worldobj+0x1800 is null. Nothing in the lobby path (LobbyRcv.cpp / VNet_Rcv.cpp,
  incl. the 212 handler FUN_004ed9c0 which only PARSES the arena def) creates it.
  The conductor's users live in Sources\FA30\PLANES\plngroup.cpp - the flight-sim
  layer, a separate subsystem. Peer-hosted FA splits into two channels: the lobby/
  arena connection (this file) and a SEPARATE game-server VNET connection that runs
  gameplay and stands up the conductor. We don't serve that channel yet, so the
  client spawns into a sim that was never initialized -> null +0x1800.

  [ ] GAME-SERVER CHANNEL (separate VNET connection) - new design thread:
      [ ] First question: how is the client told to OPEN the 2nd connection? Trace the
          writer of worldobj+0x1800 back to its triggering network event; the connect
          address/port is likely already in something we send (201 JoinToGameAnswer
          payload, or a GAME_DEF field), since the client must learn where to dial.
      [ ] Reverse the sim-entry handshake that allocates the conductor (+0x1800).
      [ ] Then: position/state replication for actual flight.
  [ ] Multi-player (lobby): verify 62 AddPlayer on a real 2nd-player join (untested)
  [ ] Pilot stats: rank, score, kills, deaths, squadron (DB placeholders exist)
  [ ] PLANE FILTERING (deferred - "get flying" comes first):
      Current: all planes shown to all teams (DEFAULT_PLANESET=0 -> stock Planes.txt;
      msg 58 0x3a echoed in full). This is intentional for now.
      [ ] Per-arena pool (option 2, mechanism DONE/dormant): map an arena in
          ARENA_PLANESETS to a plane-set index N; REQUIRES authoring PLANES\Planes_N.txt
          into the client VFS (data.q6 ships only Planes.txt=0; v164 proved a missing
          file -> "No planes' definitions found!" abort). Open Q: can a loose
          PLANES\Planes_N.txt shadow the pack, or must it be repacked?
      [ ] Per-NATION within one arena (option 1): server replies to the client's
          'out 58'121' catalog (msg 58 / FUN_004eff50) with only the selected side's
          subset instead of echoing all. Needs: (a) decode the [byte][ushort] record
          -> plane mapping (grab US vs GE 'out 58' captures and diff), (b) a plane->nation
          table. Until then 0x3a stays echoed (the exemption in handle_post_auth/
          handle_compound keeps the hangar populated).
  [ ] Telemetry RELAY (multiplayer flight): forward each player's flight-state
      ('out 6' etc.) to OTHER players in the room (the 13/20/62 entity stream),
      never echo to the sender (sender-echo = Unknown Type crash). Currently in-game
      telemetry is swallowed (single-player stopgap).

bc formula: param_3 = bc x 16 + 1
appspace LENGTH RULE: client delivers Length = bc*16+1 to handlers, not the datagram
  length. Any length-driven message MUST tile to len == 1 (mod 16) with parser-valid
  padding. (Root cause of the v182-v186 crash series; see v187 note above.)
"""
import socket, struct, time, binascii, threading, ctypes, os, sqlite3, secrets, sys, itertools, re, json
from datetime import datetime
from collections import deque

# Force UTF-8 console output with replacement so a legacy cp1252 console can never crash a
# worker thread on a box-drawing/arrow/em-dash char in a log line (the login thread died on
# '== v187 AUTH ==' under Python 3.14's cp1252 stdout). errors='replace' degrades any
# unencodable glyph to '?' instead of raising UnicodeEncodeError.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

HOST = "0.0.0.0"; PORT = 38999
FA_EPOCH = 0x7C558180; STATUS_INDEX = 0x1FF
# Diagnostic: capture the UNRELIABLE in-game packet stream (flight telemetry) that the
# server otherwise drops. Rate-limited hex sample per session, so one flight reveals the
# entity/position format we need to relay between players. Set False to silence.
CAPTURE_UNREL = True
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fa_server.db')

TICKET_SIZE     = 2172
TICKET_AB_OFF   = 0x10
TICKET_F45_OFF  = 0x20
TICKET_PID_OFF  = 0x24
TICKET_ACCT_OFF = 0x30
TICKET_ACCT_LEN = 32

SYN_OFF_AUTH = 56; SYN_OFF_F45 = 72; SYN_OFF_PID = 76; SYN_OFF_ACCT = 88
TICKET_TEMPLATE = None

import fa_logging as _falog
_falog.init_logging(
    log_dir=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs'),
    console_level=os.environ.get('FA_CONSOLE_LEVEL', 'INFO'),
    file_level=os.environ.get('FA_FILE_LEVEL', 'DEBUG'))
log  = _falog.log     # drop-in: same signature log(tag, msg[, level=...])
logx = _falog.logx    # log + traceback, for use inside except blocks

def hx(d, n=None): return binascii.hexlify(bytes(d) if n is None else bytes(d[:n])).decode()
def fa_timestamp():
    t = time.time()
    return ctypes.c_uint32(int(t)-FA_EPOCH).value, int((t%1)*1000*0x10000//1000)+0x800

# --- Database -----------------------------------------------------------------

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS accounts (
            account_name TEXT PRIMARY KEY,
            player_id    TEXT NOT NULL,
            field_45     TEXT NOT NULL DEFAULT "00000045",
            auth_block   TEXT NOT NULL DEFAULT "00000000000000000000000000000000"
        );
        CREATE TABLE IF NOT EXISTS pilots (
            pilot_name   TEXT PRIMARY KEY,
            account_name TEXT NOT NULL REFERENCES accounts(account_name),
            rank         INTEGER NOT NULL DEFAULT 0,
            score        INTEGER NOT NULL DEFAULT 0,
            kills        INTEGER NOT NULL DEFAULT 0,
            deaths       INTEGER NOT NULL DEFAULT 0,
            squadron     TEXT    NOT NULL DEFAULT '',
            rights       INTEGER NOT NULL DEFAULT 1,
            slot_index   INTEGER NOT NULL DEFAULT 1
        );
    ''')
    conn.commit(); conn.close()

def db_upsert_account(acct, pid, f45, ab):
    conn = sqlite3.connect(DB_PATH)
    # Explicitly name the columns being inserted
    conn.execute('''INSERT INTO accounts (account_name, player_id, field_45, auth_block) VALUES(?,?,?,?)
        ON CONFLICT(account_name) DO UPDATE SET
        player_id=excluded.player_id,field_45=excluded.field_45,auth_block=excluded.auth_block''',
        (acct, pid, f45, ab))
    conn.commit(); conn.close()

def db_ensure_pilot(name, acct, slot):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR IGNORE INTO pilots(pilot_name,account_name,slot_index) VALUES(?,?,?)",
                 (name, acct, slot))
    conn.commit(); conn.close()

def db_get_account_by_pid(pid_hex):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT account_name,player_id,field_45,auth_block FROM accounts WHERE player_id=?",
                       (pid_hex.lower(),)).fetchone()
    conn.close(); return row

def db_get_all_accounts():
    conn = sqlite3.connect(DB_PATH)
    # Ensure you are explicitly selecting only these 4 columns
    rows = conn.execute("SELECT account_name, player_id, field_45, auth_block FROM accounts").fetchall()
    conn.close(); return rows

def db_get_pilots(acct):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT pilot_name,slot_index FROM pilots WHERE account_name=? ORDER BY slot_index",
                        (acct,)).fetchall()
    conn.close(); return rows

def db_delete_pilot(pilot_name, acct):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM pilots WHERE pilot_name=? AND account_name=?", (pilot_name, acct))
    conn.commit(); conn.close()

def db_rename_pilot(old_name, new_name, acct):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE pilots SET pilot_name=? WHERE pilot_name=? AND account_name=?",
                 (new_name, old_name, acct))
    conn.commit(); conn.close()

def db_get_pilot_slot(acct, name):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT slot_index FROM pilots WHERE account_name=? AND pilot_name=?",
                       (acct, name)).fetchone()
    conn.close(); return row[0] if row else None

def db_next_slot(acct):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT MAX(slot_index) FROM pilots WHERE account_name=?", (acct,)).fetchone()
    conn.close(); return (row[0] or 0) + 1

def db_credit_kill(killer_name, victim_name, points):
    """Accumulate a combat result into persistent pilot stats (global scoring).
    Killer (if any) gains +1 kill and +points score; victim gains +1 death. Each
    UPDATE is additive so scores carry across games/sessions."""
    conn = sqlite3.connect(DB_PATH)
    if killer_name:
        conn.execute("UPDATE pilots SET kills=kills+1, score=score+? WHERE pilot_name=?",
                     (points, killer_name))
    if victim_name:
        conn.execute("UPDATE pilots SET deaths=deaths+1 WHERE pilot_name=?", (victim_name,))
    conn.commit(); conn.close()

def db_get_pilot_stats(name):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT score,kills,deaths FROM pilots WHERE pilot_name=?",
                       (name,)).fetchone()
    conn.close(); return row   # (score,kills,deaths) or None

# --- Terrain table & GAME_DEF terrain extraction ------------------------------
#
# FA identifies each arena's map by a TERRAIN NUMBER (1..99, sparse). The number
# is asserted >=1 (FUN_00438e30 / Trn.hpp:437) and must exist in the client's
# locally-loaded set, or the engine aborts the moment the Arenas tab renders it.
# Each room's terrain is chosen by the creator and travels inside the GAME_DEF
# text blob the client sends at creation, as a "Terrain=N" key/value line - the
# same field the client prints when it parses a GAME_DEF. We extract it there,
# store it per-room, and emit it in the 0xd2 record. Names below are the FA stock
# set (from the production + client logs) and are only used for console display.
TERRAIN_NAMES = {
    1: 'Ocean', 2: 'Mediterrain', 3: 'Two Islands', 4: 'Germany', 5: 'Circle',
    6: 'English Channel', 7: 'Bowl', 8: 'Kursk', 9: 'Canyon', 10: 'Guadalcanal',
    11: 'North Africa', 12: 'Midway', 13: 'Big Circle', 14: 'Mountains',
    15: 'Volcano', 16: 'North Cape', 17: 'Western Desert', 19: 'Solomon Islands',
    22: 'Two Islands II', 23: 'Western Desert II', 24: 'Pacific Island', 29: 'NAW',
    30: 'Desert NAW', 38: 'Classic_II', 39: 'KOTS Arena', 45: 'Five Towers',
    48: 'MKOTS Arena', 49: 'Terra Nova', 50: 'Classic_III', 51: 'Classic_III_Snow',
    60: 'Korea', 61: 'Korea Snow',
}
DEFAULT_TERRAIN = 1   # Ocean - present in every stock install; safe fallback
FORCE_GAMEDEF_TERRAIN = 6  # English Channel - terrain to stamp into client-created
                           # GAME_DEFs that store terrain=0 (the user's TC rooms are
                           # English Channel; client loaded terrain 06 at startup)

# -- Per-arena PLANE SET (option 2: GAME_DEF word[0x23] -> PLANES\Planes_<N>.txt) --
# FA's plane POOL for an arena is selected by GAME_DEF word[0x23] (the first ushort
# after the camps block). The client feeds it to FUN_004c7cd0 which loads
#   word[0x23]==0  ->  PLANES\Planes.txt   (the full stock list - every plane, all nations)
#   word[0x23]==N  ->  PLANES\Planes_<N>.txt
# This is PER-ARENA (one value per room, same for everyone in it), NOT per-nation.
# WARNING (the v164 lesson): a nonzero N only works if PLANES\Planes_<N>.txt actually
# EXISTS in data.q6, else the client aborts at load with 'No planes' definitions found!'
# (Pln_Info.cpp:93). Stock data ships only Planes.txt (N=0). So this stays 0 unless a
# SPECIAL ARENA ships its own Planes_<N>.txt. Map arena name/creator (case-insensitive)
# to its plane-set index here; anything absent resolves to DEFAULT_PLANESET.
DEFAULT_PLANESET = 0
ARENA_PLANESETS = {
    # 'pacific theater': 7,   # example: requires PLANES\Planes_7.txt present in data.q6
}
# -- Per-arena GROUND START (StartGround flag in the GAME_DEF) ------------------
# The client spawns in the AIR (OnGround=0, at StartAlt) when the arena's StartGround
# flag is 0, and on the RUNWAY (OnGround=1) when it is 1. CONFIRMED via FA.exe:
#   * deserializer FUN_0057bee0 reads it as a single byte into arena+0xec (param[0x3b]),
#     positioned EXACTLY ONE BYTE after the terrain byte (param[0x39]/+0xe4);
#   * printer FUN_005796e0 prints arena+0xec as " StartGround=%s" (yes/no);
#   * AllowTerrainChange (arena+0xe8) is a separate packed flag bit far later in the
#     struct, so flipping this byte affects ONLY the spawn, nothing else.
# StartAirfield maps side->forced field; the user's rooms use -1 (no force) for all real
# sides, so the granted start place (AF from the FLY 23 grant) is used as-is - ground
# start needs no StartAirfield change. We stamp StartGround=1 into every served GAME_DEF.
FORCE_GROUND_START = False  # reverted 2026-06-28: serve each arena's GAME_DEF untouched; use a native ground-start arena. Set True to re-enable the StartGround rewrite.
GAMEDEF_DEBUG = False  # v188: gate the per-212-build decompressed-hex dump. Set True to re-enable when diffing GAME_DEF fields.

def planeset_for_room(room):
    """Resolve the plane-set index for a room (room[1]=name, room[2]=creator).
    Default DEFAULT_PLANESET (0 = stock Planes.txt). Override per special arena via
    ARENA_PLANESETS. Returns 0 on any error so the safe default is never bypassed."""
    try:
        name    = (room[1] or '') if len(room) > 1 else ''
        creator = (room[2] or '') if len(room) > 2 else ''
        for key, idx in ARENA_PLANESETS.items():
            k = key.lower()
            if k == name.lower() or k == creator.lower():
                return int(idx)
    except Exception:
        pass
    return DEFAULT_PLANESET

# --- FFA neutral-team guard ------------------------------------------------------------
# FFA vs TC is decided by the camps-block AllianceVar (leading cstring of the camps block;
# parsed by FA.exe FUN_0056ed90 -> FUN_0056e990, Camps.cpp). The ACTIVE-CAMP MASK
# (camps+0x60) is built from which hex DIGITS appear in the string (not the dashes); Neutral
# (camp 7) is ALWAYS force-added. KEY CONSTRAINT (found v188 via live test + server log):
# Neutral has NO aircraft, so the in-arena side picker will not let you fly it -- a
# Neutral-ONLY arena left the picker with nothing flyable and it fell back to US. So instead
# we keep ONE real, flyable camp active (FFA_FLYABLE_CAMP, default 0 = US slot, which has
# planes and is the picker default) plus the forced Neutral, and relabel BOTH name groups to
# "Neutral". Result: a 2-column all-Neutral arena the player can actually fly in (they join
# the flyable camp and show as Neutral). Verified against live rooms (round-trip, p-ptr==len,
# bc*16+1). NOTE: relabeling is display-only; flyability is gated by plane availability /
# camp index, not the label string, so camp 0 stays flyable even when shown as "Neutral".
def is_ffa_room(room):
    """True if the room is a Free-For-All arena (by NAME or web-editable CATEGORY)."""
    try:
        name = (room[1] or '') if len(room) > 1 else ''
        cat  = (room[8] if len(room) > 8 and room[8] else '')
        return 'free for all' in name.lower() or 'free for all' in cat.lower()
    except Exception:
        return False

def _camp_mask_from_av(av):
    """Active-camp mask the client's FUN_0056e990 computes from an AllianceVar: each hex
    digit sets its camp bit; Neutral (7) is always forced active. (An empty string would
    make the client activate ALL camps, so callers must never produce one.)"""
    mask = 0
    for ch in av:
        c = chr(ch).upper()
        if '0' <= c <= '9':   mask |= 1 << (ord(c) - 48)
        elif 'A' <= c <= 'F': mask |= 1 << (10 + ord(c) - 65)
    return (mask | 0x80) & 0xff

def _split_camp_groups(after_av, ngroups):
    """Split the post-AllianceVar camps bytes into ngroups groups of 4 NUL-terminated
    cstrings (code, abbrev, fullname, extra). Returns (groups, consumed_bytes)."""
    pos = 0; groups = []
    for _ in range(ngroups):
        start = pos
        for _f in range(4):
            pos = after_av.index(0, pos) + 1
        groups.append(bytes(after_av[start:pos]))
    return groups, pos

# Which real (flyable) camp index the (now-disabled) FFA camps rewrite would keep active.
FFA_FLYABLE_CAMP = 0

# FFA camps rewrite is DISABLED (v188, after live testing). Two findings killed it:
#  (1) The client's camp table is GLOBAL and last-write-wins. At lobby time the server
#      pushes a 212 GAME_DEF for EVERY room and the client parses each into one shared camp
#      table; the FFA room is parsed LAST, so its reduced camps ({0,7}) overwrote the table
#      for ALL arenas -> every other room showed only camp 0 selectable, 1-4 greyed.
#      Entering a room does not re-parse, so there is no per-room isolation to exploit.
#  (2) FFA is not 'one Neutral team' at all -- the arena's own Comment reads 'no teams just
#      you against everyone else'. Stock FFA legitimately lists all nations in the side
#      picker (you choose your aircraft's nation); the free-for-all (everyone hostile,
#      no teams) comes from the camps FFA flag that '01234' already sets. So the original
#      served camps were correct and need no rewrite. Leave this False; serve camps as-is.
FFA_NEUTRAL_GUARD = False

def force_ffa_two_col(d, flyable_camp=FFA_FLYABLE_CAMP):
    """Rewrite the camps block so the FFA arena has exactly the flyable camp (default 0)
    plus the always-forced Neutral camp (7) active, with BOTH name groups relabeled to the
    real Neutral cstrings. Mutates `d` in place and fixes block_len (d[13]). The player
    joins the flyable camp (picker default, has planes) and is shown as Neutral; the result
    is the 2-column all-Neutral layout. The strict Camps.cpp p-ptr==len assert still holds
    (we recompute the active mask exactly as the client does and emit one group per active
    bit). Returns (changed, info)."""
    try:
        block_len = d[13]
        camps = bytes(d[14:14 + block_len])
        av_end = camps.index(0)
        av = camps[:av_end]
        mask = _camp_mask_from_av(av)
        active = [i for i in range(8) if mask & (1 << i)]
        groups, consumed = _split_camp_groups(camps[av_end + 1:], len(active))
        if (av_end + 1) + consumed != block_len:     # must match the client's parser exactly
            return False, 'camps parse mismatch'
        if 7 not in active:
            return False, 'no Neutral camp'
        neutral = groups[active.index(7)]            # reuse the real Neutral cstrings (NU/NEU/Neutral)
        new_av = bytes(str(flyable_camp), 'ascii')   # e.g. b'0'
        if av == new_av:
            return False, 'already collapsed'
        new_mask = _camp_mask_from_av(new_av)        # {flyable_camp, 7}
        new_active = [i for i in range(8) if new_mask & (1 << i)]
        new_camps = new_av + b'\x00' + neutral * len(new_active)   # one Neutral group per active bit
        d[14:14 + block_len] = new_camps
        d[13] = len(new_camps)
        return True, {'old_av': av, 'new_av': new_av, 'active': new_active,
                      'old_block_len': block_len, 'new_block_len': len(new_camps)}
    except (ValueError, IndexError) as e:
        return False, f'error: {e}'

def extract_terrain_from_gamedef(game_def_raw):
    """Terrain = param[0x39] of the decompressed GAME_DEF (= arena_object+0xe4).

    CONFIRMED three ways: (1) contrast rooms - Territorial Combat/Mediterranean reads 2,
    MKOTS reads 48, matching FA's terrain table exactly; (2) FA.exe FUN_00702a40 reads the
    dialog terrain from arena+0xe4; (3) FUN_0076e690 / FUN_0076d6c0 validate arena+0xe4 via
    FUN_00438e30 (the _TrnNumber>=1 assert). It is the byte immediately after the 8 camp/
    team dwords. Layout from the version byte:
      [0]ver | [1:13]3 dwords | [13]block_len | camps(block_len) | [.]3 ushorts |
      NAME\\0 | COMMENT\\0 | PASSWORD\\0 | [.]Type | LobbyType\\0 | [.]2 ushorts |
      [.]8 dwords(32B) | [.]param[0x39]=TERRAIN
    Returns 1..99 or DEFAULT_TERRAIN.
    """
    if not game_def_raw:
        return DEFAULT_TERRAIN
    try:
        d = decompress_gamedef(game_def_raw)
        if not d or len(d) < 14:
            return DEFAULT_TERRAIN
        block_len = d[13]
        p = 20 + block_len                       # NAME start (ver+3dw+blen+camps+3ushort)
        for _ in range(3):                       # skip NAME, COMMENT, PASSWORD
            p = d.index(0, p) + 1
        p += 1                                   # param[0x2a] Type byte
        p = d.index(0, p) + 1                    # LobbyType string
        p += 4                                   # param[0x2f], param[0x30] ushorts
        p += 32                                  # 8 dwords param[0x31..0x38] (camp/team idx)
        t = d[p]                                 # param[0x39] = terrain
        if 1 <= t <= 99:
            return t
    except Exception:
        pass
    return DEFAULT_TERRAIN

def gamedef_startground_offset(d):
    """Byte offset of the StartGround flag within a DECOMPRESSED GAME_DEF struct `d`.
    It sits exactly ONE byte after the terrain byte (param[0x39]) - the same walk
    extract_terrain_from_gamedef uses to reach terrain, then +1. Returns None on any
    parse failure (caller then leaves the struct untouched)."""
    try:
        if not d or len(d) < 14:
            return None
        block_len = d[13]
        p = 20 + block_len
        for _ in range(3):                       # NAME, COMMENT, PASSWORD
            p = d.index(0, p) + 1
        p += 1                                   # Type byte
        p = d.index(0, p) + 1                    # LobbyType string
        p += 4                                   # 2 ushorts
        p += 32                                  # 8 dwords
        sg = p + 1                               # terrain byte is at p; StartGround is p+1
        if 0 <= sg < len(d):
            return sg
    except (ValueError, IndexError):
        pass
    return None

# -- Per-team AIRCRAFT assignment (which nation flies each plane) ----------------
# WHY: every stored GAME_DEF leaves all 121 planes with record BYTE 0 = 0x1f. That byte is
# PLANE.field[0], the CAMP BITMASK the flyability gate FUN_00438330 checks:
#     flyable(plane, camp) = field[0] & (1<<camp).   0x1f = bits 0..4 = all 5 camps may fly
# every plane (no per-nation restriction at all). FIX (apply_plane_teams): rewrite byte 0 to
# (1<<camp) so each plane admits ONLY its team; the wrong-nation planes then grey out per
# side. The record stays the 4-byte [mask][0xff][lim][lim] form.
# NOT the earlier 6-byte [attr][camp+0x7d][0][0][lim][lim] form: that set PLANE.hascamp,
# which (a) never touched byte 0 so it never actually filtered, and (b) put the plane into
# the client's camp-RESTRICTED hangar display -> the bogus 'max N / used N' line. (The side
# PICKER's camp enablement is a separate thing entirely: camp-active from airfields/camps,
# not plane records.)
#
# EVENTS / MIX-AND-MATCH: to move a plane to another team just edit the lists below. Anything
# not listed (incl. every US type) stays on camp 0 (USA). For a one-off event arena with a
# custom roster, add ROOM_PLANE_TEAMS[<room_id>] = {camp:[names], ...}; it overrides the
# global table for that room only. Camps: 0=USA 1=GB 2=USSR 3=Germany 4=Japan.
# Re-enabled 2026-06-29: build_lz_gamedef now emits a REAL LZ-compressed stream (fa_compress)
# instead of all-literals, which shrinks even teamed GAME_DEFs far under the client's per-packet
# MTU (TC 1585B -> 801B), so the oversized-packet stall that emptied the arena list is gone.
PLANE_TEAMS_ENABLED = True

# FILTER MECHANISM (2026-06-30). Two ways to make each side see only its own aircraft:
#   True  (catalog echo): leave every plane flyable by ALL camps in the GAME_DEF
#         (byte0 = 0x1f) and instead trim the per-side plane list the server ECHOES back on
#         the client's 0x3a catalog upload. The client's OWN flyable set never changes with
#         side, so switching teams stays a lightweight in-place swap and does NOT drop into
#         the leave/teardown path that wedges the HQ menu. This is the FA "option 1".
#   False (flyability gate): set byte0 = (1<<camp) so FUN_00438330 greys wrong-nation planes.
#         Correct teams + clean display, BUT the per-side flyable LIST shrinks/empties on a
#         side change, forcing the heavy leave/re-entry flow -> HQ menu hang.
# Flip to False to fall straight back to the byte0 build if the filtered echo doesn't take.
PLANE_FILTER_VIA_CATALOG = True
# The client's msg-58 DOWNLOAD decoder FUN_004eff50 (LobbyRcv.cpp:0x209) parses (Size-1)/3
# records of 3 BYTES each: [planeID:1][ushort LE:2]. The UPLOAD is flat 1-byte ids, but the
# ECHO must be 3-byte records or the count is read as (Size-1)/3 of garbage (1-byte GE echo
# Size=27 -> only 8 planes, dropping the bombers at the tail). Visibility is driven by planeID
# membership in the list (hangar consumer FUN_006de570 gates on the GAME_DEF plane-info array,
# not this ushort), so the ushort is ancillary; 0 is safe. Bump if planes show greyed.
CATALOG_RECORD_USHORT = 0

# Stock FA 4.20 plane roster in GAME_DEF SLOT/ID order (slot = list index = the plane ID the
# GAME_DEF plane block is keyed by). The serve-time rewrite is keyed by slot; this maps
# slot->name so the team tables below can read by name.
# CORRECTED 2026-06-30: the prior list was in the client's HANGAR DISPLAY order, not slot
# order, so name->slot put camp bits on the wrong planes (Germany showed allied bombers).
# Rebuilt into true ID order via the msg-58 catalog, which maps display-position->plane-ID.
# ID 107 is the only plane the client omits from its catalog (the L2D2 transport) -> never
# shown; placed here for completeness.
PLANE_ROSTER = [
    "F4F-3","P-39D","P-40C","P-40E-1","F4F-4","F4U-1a","P-38G","F6F-3","P-47D","F4U-1c",
    "P-51D","P-38L","F4U-4","Hurr-Ia","Spit-Ia","Spit-Vb_LF","Hurr-IIC","Spit-Vb_F","Typhoon","Spit-IXc",
    "Seafire","Spit-IXe","Spit-XIV","Tempest","I-16","LaGG-3","Hurr-IIb","Kittyhawk-Ia","Yak-1b","P-39Q",
    "La-5FN","Yak-3","Yak-9U","La-7","Bf-109E-4/B","Bf-109F-4/B","FW-190A-4/U3","FW-190A-8/R6","FW-190A-8/R3","Bf-109G-6/R2",
    "FW-190A-8/R2","Bf-109G-6/R6","FW-190D-9","Me-262A-1","Bf-109K-4","Ta-152H-1","HA-200","A6M2","Ki-44-IIc37","A6M5a",
    "Ki-61","J2M3","N1K2-J","Ki-84-1a","A6M7","Ki-100","B-25D","TBF-1c","A-20Gu","B-17G",
    "Dauntless","Mosquito_B_IV","Avenger_II","DB-7B","Mosquito_FB_VI","Mitchell_III","Pe-8","Pe-2","IL-2","A-20Gs",
    "Tu-2","Tu-4","Ju-88","Do-217E-2","He-111","Do-217J-1","Ju-87G-2","D3A","G5N1","G4M2",
    "Ju-87D-3","MiG-3","J9Y","C-47A","Dakota_Mk.II","Li-2","Ju-52/3m","Mosquito_B_IX",'Mosquito_"Tse-Tse"',"Mitchell_II",
    "B-29","Martlet_I","Ki-44-IIc","Ki-43-IIa","Tomahawk","Kittyhawk","Hurr-IID","Yak-9UT","Bf-109E-1/B","Ki-84-1c",
    "FW-190F-8","F4U-4C","Bf-110C-4","Bf-110G-2","SBD-2","Lancaster","B5N2","L2D2","Ki-67","MiG-15bis",
    "F-86E","Meteor_F1","Tunnan","Ouragan","B-25J","IL-10","MiG-9","DH.100","Me-163B","FH-1_Phantom",
    "Pulqui",
]

# Historical default. Edit freely for events; unlisted planes -> USA (camp 0).
PLANE_TEAMS = {
    1: [  # Great Britain
        "Hurr-Ia","Spit-Ia","Martlet_I","Tomahawk","Hurr-IIC","Spit-Vb_F","Hurr-IID","Kittyhawk",
        "Spit-Vb_LF","Seafire","Spit-IXc","Spit-IXe","Typhoon","Spit-XIV","Tempest","Meteor_F1",
        "DH.100","Ouragan","Tunnan","Mosquito_B_IV","Lancaster","Mitchell_II","Avenger_II","DB-7B",
        "Mosquito_FB_VI",'Mosquito_"Tse-Tse"',"Mitchell_III","Mosquito_B_IX","Dakota_Mk.II",
    ],
    2: [  # USSR
        "I-16","MiG-3","LaGG-3","Hurr-IIb","Kittyhawk-Ia","Yak-1b","P-39Q","La-5FN","Yak-3",
        "Yak-9U","La-7","Yak-9UT","MiG-9","MiG-15bis","Pe-8","Pe-2","IL-2","A-20Gs","Tu-2",
        "IL-10","Tu-4","Li-2",
    ],
    3: [  # Germany
        "Bf-109E-1/B","Bf-109E-4/B","Bf-110C-4","Bf-109F-4/B","FW-190A-4/U3","Bf-110G-2",
        "Bf-109G-6/R2","FW-190A-8/R6","FW-190F-8","FW-190A-8/R3","Bf-109G-6/R6","FW-190A-8/R2",
        "FW-190D-9","Me-262A-1","Bf-109K-4","Ta-152H-1","Me-163B","Pulqui","HA-200","Ju-88",
        "Do-217E-2","Ju-87D-3","He-111","Do-217J-1","Ju-87G-2","Ju-52/3m",
    ],
    4: [  # Japan
        "A6M2","Ki-43-IIa","Ki-44-IIc","Ki-44-IIc37","A6M5a","Ki-61","J2M3","N1K2-J","Ki-84-1a",
        "Ki-84-1c","A6M7","Ki-100","D3A","B5N2","G5N1","G4M2","Ki-67","J9Y","L2D2",
    ],
}

# Optional per-room override: {room_id: {camp:[names], ...}}. Falls back to PLANE_TEAMS.
ROOM_PLANE_TEAMS = {}

def _slot_camp_map(teams):
    """{camp:[names]} -> {slot:camp} against PLANE_ROSTER. Unlisted slots -> 0 (USA)."""
    name_camp = {}
    for camp, names in teams.items():
        for nm in names:
            name_camp[nm] = camp
    return {i: name_camp.get(nm, 0) for i, nm in enumerate(PLANE_ROSTER)}

def plane_camp_for_room(room):
    """slot->camp map for this room (per-room override else global), or None if disabled."""
    if not PLANE_TEAMS_ENABLED:
        return None
    teams = ROOM_PLANE_TEAMS.get(room[0], PLANE_TEAMS) if room else PLANE_TEAMS
    return _slot_camp_map(teams)

def _session_slot_camp(s):
    """slot->camp map for the session's current room (per-room override else global table).
    Used by the 0x3a catalog-echo filter to keep only the player's current side's plane IDs."""
    rid = getattr(s, 'current_room', None)
    teams = ROOM_PLANE_TEAMS.get(rid, PLANE_TEAMS) if rid is not None else PLANE_TEAMS
    return _slot_camp_map(teams)

def _gamedef_plane_block(d):
    """Locate the plane block in a DECOMPRESSED GAME_DEF: returns (start, count, blen) where
    d[start]=count, d[start+1:start+3]=u16 block_len, d[start+3:start+3+blen]=records. Anchored
    on the same walk extract_terrain_from_gamedef uses (to the terrain byte), then scans for the
    count/length-prefixed record list that consumes exactly. Stock rooms store every plane in the
    4-byte [attr][0xff][lim][lim] form (blen == 4*(count+1)); that exact signature is required so
    we never lock onto a look-alike region. Returns None if not found."""
    try:
        block_len = d[13]
        p = 20 + block_len
        for _ in range(3):
            p = d.index(0, p) + 1
        p += 1
        p = d.index(0, p) + 1
        p += 4 + 32                              # 2 ushorts + 8 dwords; terrain byte at p
        for s in range(p, len(d) - 3):
            count = d[s]
            if count == 0 or count > 128:
                continue
            blen = struct.unpack_from('<H', d, s + 1)[0]
            if blen != 4 * (count + 1) or s + 3 + blen > len(d):
                continue
            rec = d[s + 3:s + 3 + blen]
            if all(rec[i + 1] == 0xff for i in range(0, blen, 4)):
                return s, count, blen
    except (ValueError, IndexError):
        pass
    return None

def apply_plane_teams(d, slot_camp):
    """Rewrite the plane block of bytearray `d` in place so each plane is flyable ONLY by
    its assigned nation. The flyability gate is FA.exe FUN_00438330:
        flyable(plane, camp) = PLANE.field[0] & (1 << camp)
    where PLANE.field[0] is record BYTE 0 (stock 0x1f = bits 0..4 = all 5 camps). We set
    byte 0 to (1<<camp) so a plane admits only its team; the record STAYS the 4-byte
    [mask][0xff][l1][l2] no-nation form (marker 0xff, both limit bytes preserved).
    WHY this and not the 6-byte [attr][camp+0x7d][..] form: that form set PLANE.hascamp,
    which (a) never touched byte 0 so it never actually filtered, and (b) dropped the plane
    into the client's camp-RESTRICTED hangar display -> the bogus 'max/used' line. Byte-0
    masking greys wrong-nation planes through FUN_00438330 with NO hascamp (no 'max/used')
    and does not grow the block (no MTU pressure). Returns (start, blen, blen) or None."""
    loc = _gamedef_plane_block(d)
    if not loc:
        return None
    s, count, blen = loc
    rec = bytearray(d[s + 3:s + 3 + blen])
    for slot in range(count + 1):
        if PLANE_FILTER_VIA_CATALOG:
            rec[slot * 4] = 0x1f                  # all camps flyable; per-side filter is the 0x3a echo
        else:
            camp = slot_camp.get(slot, 0) & 7
            rec[slot * 4] = 1 << camp             # byte0 = camp bitmask (US=0x01 ... JP=0x10)
        # marker rec[+1] stays 0xff (no-hascamp form); limits rec[+2],rec[+3] preserved
    d[s + 3:s + 3 + blen] = rec
    return s, blen, blen

# --- Binary GAME_DEF layout (from FA.exe FUN_0057bee0 / FUN_0056ed90) ----------
#
# The GAME_DEF is NOT text - it's a packed binary struct. The "Terrain=N" lines we
# used to grep are FA.exe PRETTY-PRINTING its parsed struct, not the wire format.
# The stored blob carries a 14-byte prefix (LobbyIndex/flags, zero for a new room)
# BEFORE the deserialisable GAME_DEF, whose first byte is the VERSION 0x8a (138).
# The deserialiser (FUN_0057bee0) requires byte[0]==0x8a, then reads:
#   version(1) | 3 dwords(12) | block_len(1) | camps-block(block_len) | 3 ushorts(6)
#   | NAME (null-term) | ... | Comment | ... many scalar/string/array fields ...
# FUN_0056ed90 (camps) asserts it consumes EXACTLY block_len bytes (Camps.cpp p-ptr==len),
# so NAME starts at  gamedef_start + 1+12+1 + block_len + 6  =  gamedef_start+20+block_len.
# --- FA Mix LZ codec (vcncNet/FA.exe FUN_007d68f0) ----------------------------
# The GAME_DEF carried by the 212 message is LZ-COMPRESSED. The decompressor reads
# exactly `size` input bytes and produces a variable-size output; the deserialiser's
# end assert (GameDef.cpp:2076 "Source.End()") requires it to consume the WHOLE
# decompressed buffer. Echoing the client's compressed blob fails because its size
# (740 ==4 mod16) can't land on the bc*16+1 appspace grid, so the client over-reads 8
# stale bytes that decompress into extra output -> Source.End.
#
# Fix: DECOMPRESS the stored blob, then re-send it via the decompressor's STORED mode
# (first byte 0x01 -> copies size-4 bytes verbatim). We pad a string field so the
# decompressed size ==8 mod16, which makes [0xd4][id:4][0x01][3][struct] land EXACTLY
# on bc*16+1 (payload = D+9). Validated against db_id=24: 732 compressed -> 1183 bytes,
# clean camps/name/comment.
_NEG_1A1 = -0x1a1
def _fa_hash(b0, b1, b2):
    v = ((((b0 << 4) ^ b1) << 4) ^ b2) & 0xffffffff
    prod = (v * _NEG_1A1) & 0xffffffff
    if prod & 0x80000000:
        prod -= 0x100000000
    return (prod >> 4) & 0x1ff

def fa_decompress(data, size=None):
    """Reimplementation of FUN_007d68f0. data[0]==0x01 -> STORED (copy data[4:size]);
    else LZ. Returns the decompressed bytes."""
    data = bytes(data)
    if size is None:
        size = len(data)
    if size < 4:
        raise ValueError('compressed input too small')
    if data[0] == 0x01:
        return data[4:size]
    # FA's decompressor (FUN_007d68f0) pre-initialises EVERY dictionary slot to point at
    # the 18-byte constant "123456789012345678", so a MATCH emitted before that slot was
    # populated by literals copies from THAT string - not from output offset 0. Model it
    # as an 18-byte PREFIX on the output buffer with all dict slots = offset 0; the real
    # output is out[18:]. Without this, a blob whose early op is such a match (the trn5
    # 'Circle' GAME_DEF) decompresses to garbage -> client GAME_DEF parser over-read CTD.
    out = bytearray(b"123456789012345678")
    dict_pos = [0] * 4096       # every slot points at the init string (offset 0 in `out`)
    ring = 0
    lit_run = 0
    ctrl = 1
    ip = 4                       # skip 4-byte header
    end = size
    while ip < end:
        if ctrl == 1:
            if ip + 1 >= end:
                break
            ctrl = data[ip] | 0x10000 | (data[ip + 1] << 8)
            ip += 2
        nops = 1 if (end - 0x20) < ip else 16
        for _ in range(nops):
            if ip >= end:
                break
            if (ctrl & 1) == 0:                      # LITERAL
                out.append(data[ip]); ip += 1
                lit_run += 1
                if lit_run == 3:
                    p = len(out) - 1
                    slot = (ring + _fa_hash(out[p-2], out[p-1], out[p]) * 8) & 0xfff
                    dict_pos[slot] = p - 2
                    lit_run = 2
                    ring = (ring + 1) & 7
            else:                                    # MATCH
                if ip + 1 >= end:
                    ip = end; break
                b0 = data[ip]; b1 = data[ip + 1]; ip += 2
                hi = (b0 & 0xf0) << 4
                src = dict_pos[(hi | b1) & 0xfff]
                n = 3 + (b0 & 0xf)
                for k in range(n):
                    out.append(out[src + k])
                start = len(out) - n
                if lit_run == 0:
                    dict_pos[((hi | (b1 & 0xfffffff8)) + ring) & 0xfff] = start
                else:
                    s = start - lit_run
                    slot = (ring + _fa_hash(out[s], out[s+1], out[s+2]) * 8) & 0xfff
                    dict_pos[slot] = s
                    ring = (ring + 1) & 7
                    if lit_run == 2:
                        slot = (ring + _fa_hash(out[s+1], out[s+2], out[s+3]) * 8) & 0xfff
                        dict_pos[slot] = s + 1
                        ring = (ring + 1) & 7
                    lit_run = 0
                    dict_pos[((hi | (b1 & 0xfffffff8)) + ring) & 0xfff] = start
                ring = (ring + 1) & 7
            ctrl >>= 1
            if ctrl == 1:
                break
    return bytes(out[18:])   # strip the 18-byte dictionary-init prefix

def _lz_comp_size(n):
    """Size of the all-literals LZ stream for an n-byte struct:
    4-byte header + one 2-byte control word per 16 literals + n literal bytes."""
    return 4 + 2 * ((n + 15) // 16) + n

def encode_all_literals(struct):
    """Encode `struct` as a valid FA LZ stream using ONLY literals: a 4-byte header
    (mode byte 0x00 = LZ, NOT 0x01/STORED) followed by [ctrl=0x0000][<=16 literal bytes]
    groups. ctrl=0x0000 -> the decompressor reads 16 literal bits (each copies 1 byte),
    so the stream decompresses to `struct` verbatim (no matches -> dictionary unused).
    We use this instead of STORED mode: FUN_007d68f0's 0x01 branch reads from the
    (uninitialised) output buffer, yielding a garbage version byte (v161: 'get 64')."""
    out = bytearray([0x00, 0x00, 0x00, 0x00])
    i = 0
    while i < len(struct):
        out += b'\x00\x00'
        out += struct[i:i + 16]
        i += 16
    return bytes(out)

def fa_compress(d, flo=-1, fhi=-1):
    """Encode `d` as a real FA LZ stream (the inverse of fa_decompress): literals plus 3-18
    byte dictionary matches, emitted by CO-SIMULATING the decompressor's exact dictionary
    state (18-byte init prefix, hash/ring/lit_run, slot writes) so every match resolves to the
    correct source at decode time. Repetitive GAME_DEFs (the plane block especially) shrink
    dramatically vs encode_all_literals, keeping the 212 payload under the client's MTU.
    Positions in [flo,fhi) are forced to literals (byte-granular alignment padding: a run of
    spaces would otherwise collapse to one fixed-size match and never move the size residue).
    The caller MUST verify the result via fa_decompress before serving."""
    d = bytes(d)
    out = bytearray(b"123456789012345678")     # decompressor's dictionary-init prefix
    dict_pos = [0] * 4096; ring = 0; lit_run = 0
    content_map = {}                            # 3-byte content -> {slots currently holding it}
    slot_content = {}                           # slot -> its indexed 3-byte content
    def set_slot(slot, pos):
        old = slot_content.get(slot)
        if old is not None:
            s = content_map.get(old)
            if s is not None: s.discard(slot)
        dict_pos[slot] = pos; c = bytes(out[pos:pos + 3])
        if len(c) == 3:
            content_map.setdefault(c, set()).add(slot); slot_content[slot] = c
        else:
            slot_content.pop(slot, None)
    ops = []; q = 0; N = len(d)
    while q < N:
        best_n = 0; best_slot = -1; best_src = -1
        if not (flo <= q < fhi) and q + 3 <= N:
            cand = content_map.get(d[q:q + 3])
            if cand:
                for S in cand:
                    src = dict_pos[S]; n = 0; lim = min(18, N - q)
                    while n < lim:
                        pos = src + n
                        pb = out[pos] if pos < len(out) else d[q + (pos - len(out))]
                        if pb != d[q + n]: break
                        n += 1
                    if n > best_n: best_n = n; best_slot = S; best_src = src
                    if best_n == lim: break
        if best_n >= 3:
            S = best_slot; n = best_n; src = best_src
            b0 = (((S >> 8) & 0xf) << 4) | (n - 3); b1 = S & 0xff; hi = (b0 & 0xf0) << 4
            for k in range(n): out.append(out[src + k])
            start = len(out) - n
            if lit_run == 0:
                set_slot(((hi | (b1 & 0xfffffff8)) + ring) & 0xfff, start)
            else:
                s = start - lit_run
                set_slot((ring + _fa_hash(out[s], out[s + 1], out[s + 2]) * 8) & 0xfff, s); ring = (ring + 1) & 7
                if lit_run == 2:
                    set_slot((ring + _fa_hash(out[s + 1], out[s + 2], out[s + 3]) * 8) & 0xfff, s + 1); ring = (ring + 1) & 7
                lit_run = 0
                set_slot(((hi | (b1 & 0xfffffff8)) + ring) & 0xfff, start)
            ring = (ring + 1) & 7; ops.append((1, b0, b1)); q += n
        else:
            ch = d[q]; out.append(ch); q += 1; lit_run += 1
            if lit_run == 3:
                p = len(out) - 1
                set_slot((ring + _fa_hash(out[p - 2], out[p - 1], out[p]) * 8) & 0xfff, p - 2)
                lit_run = 2; ring = (ring + 1) & 7
            ops.append((0, ch))
    # serialize: 4-byte header (byte0=0x00 => LZ mode) + groups of 16 ops, each preceded by its
    # 2-byte control word (bit set = match, LSB = first op of the group).
    s = bytearray([0, 0, 0, 0]); i = 0
    while i < len(ops):
        grp = ops[i:i + 16]; ctrl = 0
        for j, op in enumerate(grp):
            if op[0] == 1: ctrl |= (1 << j)
        s.append(ctrl & 0xff); s.append((ctrl >> 8) & 0xff)
        for op in grp:
            if op[0] == 0: s.append(op[1])
            else: s.append(op[1]); s.append(op[2])
        i += 16
    return bytes(s)

# -- EDITABLE ARENA SETTINGS (post-block GAME_DEF tail) --------------------------
# The 173-byte region AFTER the plane-team block is a FIXED-layout struct (verified
# byte-identical across TC / Nations at war / Free For All except the actual values).
# It is located per-arena via _gamedef_plane_block(d) -> block_end = start + blen, so
# these offsets are robust across arenas even though absolute offsets shift with the
# variable name/hash before the block. Each field is a float32 in METRES; the game UI
# shows/edits them in FEET, so we convert on read/write. Verified against the in-arena
# OPTIONS screenshots (13000 m = 42651 ft fighters, 4876 m = 15997 ft no-mask ceiling,
# 9296 m = 30499 ft mask ceiling) and read-tested on all three live arenas.
_M2FT = 3.280839895
ARENA_TAIL_FIELDS = [
    # key,             delta, label
    ('vr_fighters',     31, 'Visual range - fighters (ft)'),
    ('vr_bombers',      27, 'Visual range - bombers (ft)'),
    ('vr_tanks',        39, 'Visual range - tanks (ft)'),
    ('vr_plane_tags',   43, 'Visual range - plane tags (ft)'),
    ('vr_other_tags',   47, 'Visual range - other tags (ft)'),
    ('vr_padlock',      51, 'Visual range - padlock (ft)'),
    ('vr_chat',         63, 'Chat range (ft)'),
    ('height_no_mask',  90, 'Oxygen ceiling - without mask (ft)'),
    ('height_mask',     94, 'Oxygen ceiling - with mask (ft)'),
]

def _arena_tail_base(d):
    """Offset of the post-block settings tail in a DECOMPRESSED GAME_DEF, or None.
    Anchored to the plane-team block so it is correct for any arena."""
    try:
        start, cnt, blen = _gamedef_plane_block(d)
    except Exception:
        return None
    if start is None:
        return None
    return start + blen

def arena_settings_read(blob):
    """Read the editable post-block settings from a stored (compressed) GAME_DEF blob.
    Returns {key: value_in_feet(int)}; empty dict if the blob can't be parsed."""
    d = decompress_gamedef(blob)
    if not d:
        return {}
    bend = _arena_tail_base(d)
    if bend is None:
        return {}
    out = {}
    for key, delta, _label in ARENA_TAIL_FIELDS:
        off = bend + delta
        if off + 4 <= len(d):
            try:
                m = struct.unpack_from('<f', d, off)[0]
                if m == m:                       # not NaN
                    out[key] = int(round(m * _M2FT))
            except Exception:
                pass
    return out

def arena_settings_apply(d, settings):
    """In-place patch the post-block settings of a DECOMPRESSED GAME_DEF bytearray from a
    {key: feet} override dict. Each patch is a same-length float32 write, so it never
    shifts the struct or the 212 pad alignment. No-op for missing/blank keys."""
    if not settings:
        return
    bend = _arena_tail_base(d)
    if bend is None:
        return
    for key, delta, _label in ARENA_TAIL_FIELDS:
        v = settings.get(key)
        if v is None or v == '':
            continue
        off = bend + delta
        if off + 4 <= len(d):
            try:
                struct.pack_into('<f', d, off, float(v) / _M2FT)   # feet -> metres
            except (ValueError, TypeError):
                pass

# --- EvP: enemy anti-aircraft / flak (client-side, driven by GAME_DEF AA quality) ---------
# EvP flak is simulated CLIENT-SIDE: the AA batteries loaded with the terrain fire at the
# player when the arena's GAME_DEF sets the [AI] quality fields non-zero. The stock TC.gdf /
# FFA.gdf templates ship these at 0, so the guns are inert; the 2009 live arenas used
# AAquality=6, FlakQuality=1, BomberGunnerQuality=3, ShipAAQuality=1, TankAAQuality=1 and the
# world actively shot players ("GER Anti-Aircraft has damaged your fuselage"). We restore that
# by patching the 5 AA-quality bytes at 212-serve time - no protocol work, no new message.
#
# Field order + wire position CONFIRMED by decompiling the GAME_DEF parser FUN_0057bee0:
# the client reads AAquality from struct byte +0x418 (== dword field param_1[0x106]), and the
# 5 quality fields are 5 CONSECUTIVE single bytes on the wire. _gamedef_aa_offset replays the
# parser's variable-length walk to find them for any arena/terrain.
EVP_AA_ENABLED = True             # EvP is now always on; per-arena AA/Flak come from the web
                                  # settings (the `evp` console command still forces/overrides).
EVP_AA_QUALITY = (6, 1, 3, 1, 1)  # AAquality, FlakQuality, BomberGunnerQuality, ShipAA, TankAA
                                  # - the DEFAULT when an arena has no web-set AA/Flak sliders.

# The 5 web slider keys (0..6 each) that map 1:1 onto the AA-quality bytes, in wire order.
# Stored per-arena in rooms.settings_json and read at 212-serve time. Missing keys fall back
# to the corresponding EVP_AA_QUALITY default so old arenas behave exactly as before.
EVP_AA_SETTING_KEYS = ('aa_quality', 'flak_quality', 'bomber_gunner', 'ship_aa', 'tank_aa')

def evp_quality_from_settings(arena_settings):
    """Return the 5-tuple of AA-quality bytes for an arena, taking each value from the web
    slider (arena_settings[key], clamped 0..6) when present, else the EVP_AA_QUALITY default."""
    vals = list(EVP_AA_QUALITY)
    if isinstance(arena_settings, dict):
        for i, key in enumerate(EVP_AA_SETTING_KEYS):
            if key in arena_settings:
                try:
                    vals[i] = max(0, min(6, int(arena_settings[key])))
                except (ValueError, TypeError):
                    pass
    return tuple(vals)

def _gamedef_aa_offset(d):
    """Offset of the 5 consecutive AA-quality bytes in a DECOMPRESSED GAME_DEF, or None.
    Replays FUN_0057bee0's field walk up to param_1[0x106] (byte +0x418 = AAquality)."""
    try:
        n = len(d)
        p = 0
        if n < 1 or d[p] != 0x8a:
            return None
        p += 1
        def adv(k):
            nonlocal p
            p += k
            if p > n:
                raise ValueError('overrun')
        def cstr():
            nonlocal p
            while p < n and d[p] != 0:
                p += 1
            p += 1
            if p > n:
                raise ValueError('overrun')
        adv(4); adv(4); adv(4)               # 3 dwords param_1[0..2]
        blen = d[p]; adv(1); adv(blen)       # len byte + variable blob (FUN_0056ed90)
        adv(2); adv(2); adv(2)               # words 0x23,0x24,0x25
        cstr(); cstr(); cstr()               # 3 cstrings
        adv(1)                               # byte 0x2a
        cstr()                               # cstring
        adv(2); adv(2)                       # words 0x2f,0x30
        adv(0x20)                            # 0x20 block 0x31..38
        adv(1)                               # byte 0x39 TERRAIN
        adv(1)                               # byte 0x3b
        adv(4)                               # dword 0x3c
        adv(0x24)                            # 0x24 block 0x3d..45
        adv(1); adv(1); adv(1); adv(1); adv(1)          # bytes 0x47..0x4b
        cstr()                               # cstring5
        adv(1); adv(1); adv(2); adv(1); adv(1)          # 0x57,0x58,word 0x59,0x5a,0x5b
        adv(2); adv(4); adv(4); adv(4); adv(4)          # word 0x5c, dwords 0x5d..60
        cstr(); cstr()                       # cstring6,7
        adv(1); adv(1); adv(2); adv(2)       # 0x63,0x64,word 0x65,word 0x66
        adv(1); adv(1); adv(1); adv(1)       # 0x75,0x77,0x78,0x7a
        adv(1); adv(1); adv(1); adv(1); adv(1); adv(1)              # 0xf2..0xf7
        adv(1); adv(1); adv(1); adv(1); adv(1); adv(1); adv(1)      # 0xfb..0x101
        if p + 5 > n:
            return None
        return p                             # param_1[0x106] = AAquality
    except Exception:
        return None

def apply_aa_quality(d, values=EVP_AA_QUALITY):
    """In-place set the 5 AA-quality bytes in a DECOMPRESSED GAME_DEF. Same-length byte
    writes (no struct shift). SAFETY: only patches if the located bytes currently look like
    AA quality (all 0..10); otherwise no-ops so a parser desync can never corrupt the blob.
    Returns (offset, old_values) on success, None on no-op."""
    off = _gamedef_aa_offset(d)
    if off is None:
        return None
    old = list(d[off:off + 5])
    if not all(0 <= x <= 10 for x in old):     # doesn't look like the AA block - refuse
        return None
    for i, v in enumerate(values[:5]):
        d[off + i] = max(0, min(255, int(v)))
    return off, old

def build_lz_gamedef(blob, planeset=0, force_ffa=False, plane_camp=None, arena_settings=None):
    """Decompress the stored (LZ) GAME_DEF, pad a string field so the re-encoded
    all-literals stream lands EXACTLY on bc*16+1 (payload = 5 + comp_size(N') == 1 mod16),
    then re-encode. Returns (compressed_bytes, decompressed_size, pad) or (None,0,0)."""
    b = bytes(blob)
    v = gamedef_start(b)
    if not b or b[v] != 0x8a:
        return None, 0, 0
    comp = b[v - 6:]                 # compressed stream begins 6 bytes before the 0x8a
    if len(comp) < 4:
        return None, 0, 0
    try:
        d = bytearray(fa_decompress(comp, len(comp)))
    except Exception as e:
        log('GAMEDEF212', f'decompress failed: {e}')
        return None, 0, 0
    if not d or d[0] != 0x8a:
        log('GAMEDEF212', f'decompressed version=0x{(d[0] if d else 0):02x} (expected 0x8a)')
        return None, 0, 0
    # FFA neutral-team guard: for Free-For-All rooms, rewrite the camps block to a 2-column
    # all-Neutral set (one flyable camp + forced Neutral, both labeled "Neutral") so the
    # side picker / 213 Nations box / roster show Neutral AND the player can still fly
    # (Neutral itself has no planes; the flyable camp does). Runs BEFORE pad alignment /
    # plane-set patch so d[13] and the word[0x23] offset (14+d[13]) stay consistent.
    if force_ffa:
        changed, info = force_ffa_two_col(d)
        if changed:
            log('GAMEDEF212', f"FFA guard: camps -> 2-col Neutral "
                              f"(AllianceVar {info['old_av']!r} -> {info['new_av']!r}, "
                              f"active camps {info['active']}, "
                              f"block_len {info['old_block_len']} -> {info['new_block_len']})")
        elif info != 'already collapsed':
            log('GAMEDEF212', f'FFA guard: camps unchanged ({info})')
    # v166 DEBUG: dump the pristine decompressed GAME_DEF struct so a terrain-contrast
    # room (Ocean=1 vs English Channel=6) can be diffed field-by-field to pin the terrain
    # byte. Harmless; remove once the terrain field is located.
    if GAMEDEF_DEBUG:
        log('GAMEDEF212', f'decompressed hex ({len(d)}B): {bytes(d).hex()}')
    # v165: CORRECTION - the ushort at 14+camps_block_len (param_1[0x23]) is NOT the
    # terrain. It is the PLANE-SET id: FUN_0057bee0 feeds it straight to FUN_004c7cd0,
    # which loads "PLANES\Planes_%d.txt" (or "Planes.txt" when 0). v164 stamped 6 here,
    # so the client tried to load the nonexistent "Planes_6.txt" and aborted with
    # "No planes' definitions found!" (Pln_Info.cpp:93). 0 => default Planes.txt, which
    # the real 2009 session also used (it loaded SPIT/B17 fine). So we LEAVE 0x23 alone.
    #
    # The real terrain field lives at desc+0x1c of the 0xd2 arena descriptor and is the
    # value FUN_00438e30(N) asserts (N>=1, Trn.hpp:437). Full traces of FUN_0057bee0 (the
    # GAME_DEF deserializer) and FUN_004efda0 (the 0xd2 list parser) show NEITHER message
    # carries it: the deserializer parses to an exact Source.End() with no terrain field,
    # and the list parser reads only GameIndex(+4)+2 names, skipping the 12-byte header.
    # desc+0x1c is therefore set from FUN_004ed040's param_8 (source still being pinned),
    # not from anything we currently send. Patching the blob cannot fix it - see notes
    # below. We do NOT touch the plane-set ushort here.
    # OPT-IN per-arena plane set (option 2): stamp the plane-set id into word[0x23]
    # (first ushort after the camps block, at +14+block_len) so the client loads
    # PLANES\Planes_<planeset>.txt. planeset==0 leaves the stock selector untouched
    # (default, current behaviour). NONZERO REQUIRES PLANES\Planes_<planeset>.txt to
    # exist in data.q6 or the client aborts 'No planes' definitions found!' (v164 lesson).
    if planeset:
        try:
            ps_off = 14 + d[13]                 # word[0x23] = first ushort after camps
            struct.pack_into('<H', d, ps_off, planeset & 0xFFFF)
            log('GAMEDEF212', f"plane-set word[0x23] @+{ps_off} = {planeset} "
                              f"(client loads PLANES\\Planes_{planeset}.txt; must exist in data.q6)")
        except Exception as e:
            log('GAMEDEF212', f'plane-set patch failed ({e}); leaving word[0x23] as-is')
    # GROUND START: rewrite the StartGround byte (terrain+1) so the client spawns on the
    # runway (OnGround=1) instead of in the air. Single byte, isolated from every other
    # field (confirmed in FA.exe FUN_0057bee0/FUN_005796e0). No-op if already 1 or if the
    # offset can't be resolved.
    if FORCE_GROUND_START:
        sg = gamedef_startground_offset(d)
        if sg is not None:
            old = d[sg]
            if old != 1:
                d[sg] = 1
                log('GAMEDEF212', f'StartGround @+{sg} {old} -> 1 (runway spawn)')
        else:
            log('GAMEDEF212', 'StartGround offset unresolved; leaving spawn as-is')
    # PER-TEAM PLANES: rewrite each plane's nation marker so every active camp owns aircraft
    # (else all planes default to camp 0/USA and GB/SU/GE/JP grey out in the side picker).
    # Runs after the camps/plane-set/StartGround patches (their offsets precede the plane
    # block) and before pad alignment so the pad accounts for the grown block.
    if plane_camp:
        pinfo = apply_plane_teams(d, plane_camp)
        if pinfo:
            ps, ob, nb = pinfo
            c = {}
            for v in plane_camp.values():
                c[v] = c.get(v, 0) + 1
            log('GAMEDEF212', f"plane-teams @+{ps}: block {ob}->{nb}B  "
                              f"US={c.get(0,0)} GB={c.get(1,0)} SU={c.get(2,0)} "
                              f"GE={c.get(3,0)} JP={c.get(4,0)}")
        else:
            log('GAMEDEF212', 'plane-teams: plane block not located; planes left on USA')
    # WEB-EDITED SETTINGS: patch the post-block tail (visual ranges, oxygen ceilings) from the
    # per-room override dict. In-place float32 writes, so no struct shift / pad-alignment change.
    if arena_settings:
        arena_settings_apply(d, arena_settings)
    # EvP: enable client-side enemy flak by setting the [AI] AA-quality bytes non-zero.
    # Per-arena AA/Flak come from the web sliders (arena_settings), falling back to the
    # EVP_AA_QUALITY defaults for any slider not set. In-place same-length byte writes.
    if EVP_AA_ENABLED:
        _q = evp_quality_from_settings(arena_settings)
        _aa = apply_aa_quality(d, _q)
        if _aa:
            _off, _old = _aa
            log('GAMEDEF212', f'EvP AA quality @+{_off}: {_old} -> {list(_q)} '
                              f'(AAquality/Flak/BomberGunner/ShipAA/TankAA)')
        else:
            log('GAMEDEF212', 'EvP AA: quality bytes not located/verified; left as-is')
    D_orig = len(d)
    # REAL-LZ encode with bc*16+1 alignment. Real compression keeps even teamed GAME_DEFs far
    # under the client's per-packet MTU ceiling (the all-literals encoder INFLATES the struct
    # and overflowed it -> the oversized 212 stalled the in-order reliable channel -> the 0xd2
    # arena list queued behind it never arrived -> empty lobby). There is no closed-form size,
    # so we pad the COMMENT and recompress until 5+len(comp) == 1 (mod 16); the pad bytes are
    # FORCED to literals (flo..fhi) so each adds exactly one byte (a run of spaces would else
    # collapse to one fixed-size match and never move the residue). The chosen stream is
    # round-trip verified before use; any miss falls back to the all-literals encoder.
    try:
        p = 1 + 12
        block_len = d[p]; p += 1
        p += block_len + 6
        name_end = d.index(0, p)
        comment_end = d.index(0, name_end + 1)
    except (ValueError, IndexError):
        comment_end = None
    if comment_end is not None:
        for pad in range(0, 48):
            dp = bytes(d[:comment_end]) + b' ' * pad + bytes(d[comment_end:])
            comp = fa_compress(dp, comment_end, comment_end + pad)
            if (5 + len(comp)) % 16 == 1:
                if fa_decompress(comp, len(comp)) == dp:
                    return comp, len(dp), pad
                log('GAMEDEF212', f'real-LZ round-trip mismatch at pad={pad}; using all-literals')
                break
        else:
            log('GAMEDEF212', 'real-LZ could not align within 48; using all-literals')
    # FALLBACK: all-literals encoder with closed-form pad (original behaviour).
    pad = 0
    while (5 + _lz_comp_size(D_orig + pad)) % 16 != 1:
        pad += 1
        if pad > 64:
            log('GAMEDEF212', 'could not align (pad>64)')
            return None, 0, 0
    if pad:
        # insert `pad` spaces before the COMMENT's null terminator (cosmetic, the parser
        # reads it null-terminated). Falls back to the NAME terminator if parsing fails.
        try:
            p = 1 + 12
            block_len = d[p]; p += 1
            p += block_len + 6
            name_end = d.index(0, p)
            comment_end = d.index(0, name_end + 1)
            d[comment_end:comment_end] = b' ' * pad
        except (ValueError, IndexError) as e:
            log('GAMEDEF212', f'comment-pad failed ({e}); padding NAME')
            try:
                name_end = d.index(0, 13 + 1 + d[13] + 6)
                d[name_end:name_end] = b' ' * pad
            except Exception:
                return None, 0, 0
    return encode_all_literals(bytes(d)), D_orig, pad

def decompress_gamedef(blob):
    """Return the decompressed GAME_DEF struct (starts with version 0x8a) from a stored
    blob, or None. The stored blob is LZ-compressed beginning 6 bytes before the 0x8a."""
    try:
        b = bytes(blob)
        if not b:
            return None
        v = gamedef_start(b)
        if b[v] != 0x8a:
            return None
        d = fa_decompress(b[v - 6:], len(b) - (v - 6))
        return d if d and d[0] == 0x8a else None
    except Exception:
        return None

def gamedef_start(blob):
    """Offset of the GAME_DEF VERSION byte (0x8a) within the stored blob.
    Used for NAME extraction (fields are positioned relative to the version)."""
    if not blob:
        return 0
    b = bytes(blob)
    i = b.find(0x8a)
    return i if i >= 0 else 0

def gamedef_212_start(blob):
    """Offset where the 212 GAME_DEF must BEGIN = 6 bytes before the 0x8a version.
    The deserialiser (FUN_0057bee0) consumes a 6-byte GAME_DEF header (FUN_007cc610 +
    a 1-byte advance) BEFORE reading the version, so the stream we push must include
    those 6 bytes. Proven empirically: v158 started at the 0x8a and the client read
    version blob[ver+6]=0x90 ('get 144'); starting at ver-6 lands the 0x8a where the
    deserialiser looks. It also makes [0xd4][id:4][gdef] land exactly on bc*16+1
    (e.g. 5+732=737), so no pad/over-read. Blob layout:
      [8-byte outer prefix][6-byte gd header][0x8a version][body...]"""
    v = gamedef_start(blob)
    return max(0, v - 6)

def extract_name_from_gamedef(game_def_raw):
    """Room NAME from the DECOMPRESSED GAME_DEF (the stored blob is LZ-compressed, so the
    raw bytes look mangled e.g. 'TerHorial C'; decompressing yields the real name). Name
    sits at struct offset 20+block_len (version+3dwords+block_len byte+camps+3 ushorts)."""
    if not game_def_raw:
        return ''
    try:
        d = decompress_gamedef(game_def_raw)
        if not d or len(d) < 14:
            return ''
        block_len = d[13]
        off = 20 + block_len
        if off >= len(d):
            return ''
        end = d.find(0, off)
        if end < 0:
            end = len(d)
        raw = d[off:end]
        name = ''.join(chr(c) for c in raw if 0x20 <= c <= 0x7e).strip()
        return name[:31]
    except Exception:
        return ''

# --- Room DB ------------------------------------------------------------------

def init_rooms_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS rooms (
            room_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            room_name     TEXT    NOT NULL DEFAULT 'Unnamed',
            creator_pilot TEXT    NOT NULL DEFAULT '',
            account_name  TEXT    NOT NULL DEFAULT '',
            room_slot     INTEGER NOT NULL DEFAULT 35,
            game_def_raw  BLOB,
            terrain       INTEGER NOT NULL DEFAULT 1,
            status        TEXT    NOT NULL DEFAULT 'open',
            created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS room_players (
            room_id      INTEGER NOT NULL,
            pilot_name   TEXT    NOT NULL,
            account_name TEXT    NOT NULL DEFAULT '',
            joined_at    TEXT    NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (room_id, pilot_name)
        );
    ''')
    # Migration: add room_slot if DB was created before this column was introduced
    try:
        conn.execute("ALTER TABLE rooms ADD COLUMN room_slot INTEGER DEFAULT 35")
        conn.commit()
        log('DB', 'Migration: added room_slot column to rooms table')
    except Exception:
        pass  # column already exists - expected on every normal startup
    # Migration: add terrain column + backfill from each room's stored GAME_DEF text.
    try:
        conn.execute("ALTER TABLE rooms ADD COLUMN terrain INTEGER DEFAULT 1")
        conn.commit()
        log('DB', 'Migration: added terrain column to rooms table')
        for rid, gdef in conn.execute("SELECT room_id, game_def_raw FROM rooms").fetchall():
            t = extract_terrain_from_gamedef(gdef)
            conn.execute("UPDATE rooms SET terrain=? WHERE room_id=?", (t, rid))
        conn.commit()
        log('DB', 'Migration: backfilled terrain from stored GAME_DEFs')
    except Exception:
        pass  # column already exists - expected on every normal startup
    # Migration: add the arena-list SECTION HEADER / category (name1) column. Editable
    # from the web admin Arena Management panel; default 'Custom Arenas' = the value
    # build_arenalist hardcoded before this was made per-room.
    try:
        conn.execute("ALTER TABLE rooms ADD COLUMN category TEXT NOT NULL DEFAULT 'Custom Arenas'")
        conn.commit()
        log('DB', 'Migration: added category column to rooms table')
    except Exception:
        pass  # column already exists - expected on every normal startup
    # Migration: add settings_json - per-room web-edited GAME_DEF setting overrides (visual
    # ranges, oxygen ceilings, ...). Stored as JSON {key: feet}; applied at 212 serve time in
    # build_lz_gamedef so the original game_def_raw blob is never mutated/recompressed on save.
    try:
        conn.execute("ALTER TABLE rooms ADD COLUMN settings_json TEXT NOT NULL DEFAULT '{}'")
        conn.commit()
        log('DB', 'Migration: added settings_json column to rooms table')
    except Exception:
        pass  # column already exists - expected on every normal startup
    # Always re-derive room_name from the binary GAME_DEF (the old text-regex path
    # left every room 'Unnamed' since the blob is binary, not INI text). Cheap, and
    # corrects rooms created before binary name extraction existed.
    try:
        fixed = 0
        for rid, gdef, cur_name in conn.execute(
                "SELECT room_id, game_def_raw, room_name FROM rooms WHERE status='open'").fetchall():
            nm = extract_name_from_gamedef(gdef)
            if nm and nm != cur_name:
                conn.execute("UPDATE rooms SET room_name=? WHERE room_id=?", (nm, rid))
                fixed += 1
        if fixed:
            conn.commit()
            log('DB', f'Migration: re-derived room_name for {fixed} room(s) from binary GAME_DEF')
    except Exception as e:
        log('DB', f'name re-derive skipped: {e}')
    conn.commit(); conn.close()

def db_create_room(creator_pilot, account, game_def_raw, room_slot=35, terrain=None):
    if terrain is None:
        terrain = extract_terrain_from_gamedef(game_def_raw)
    room_name = extract_name_from_gamedef(game_def_raw) or 'Unnamed'
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        "INSERT INTO rooms(room_name, creator_pilot, account_name, game_def_raw, room_slot, terrain) "
        "VALUES(?,?,?,?,?,?)",
        (room_name, creator_pilot, account, game_def_raw, room_slot, terrain))
    room_id = cur.lastrowid
    conn.commit(); conn.close()
    return room_id

def db_get_room_settings(room_id):
    """Return the web-edited GAME_DEF setting overrides for a room as a {key: feet} dict
    (empty if none/invalid). Applied at 212 serve time by build_lz_gamedef."""
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT settings_json FROM rooms WHERE room_id=?", (room_id,)).fetchone()
        conn.close()
        if row and row[0]:
            d = json.loads(row[0])
            return d if isinstance(d, dict) else {}
    except Exception:
        pass
    return {}

def db_get_open_rooms():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT room_id, room_name, creator_pilot, account_name, created_at, room_slot, "
        "game_def_raw, terrain, category "
        "FROM rooms WHERE status='open' ORDER BY created_at DESC").fetchall()
    conn.close(); return rows

# 2026-06-29: keep rooms listed even after they empty out (or when their creator opens a
# new room), so e.g. a Territorial Combat ground room and a Free For All air room coexist
# instead of the second one reaping the first. With this True, db_close_room only VACATES
# the room (clears its players) and leaves status='open'. Manual cleanup is still available
# via the console 'clearrooms' command. Set False to restore auto-close-on-empty.
PERSIST_ROOMS = True

def db_close_room(room_id):
    conn = sqlite3.connect(DB_PATH)
    if not PERSIST_ROOMS:
        conn.execute("UPDATE rooms SET status='closed' WHERE room_id=?", (room_id,))
    conn.execute("DELETE FROM room_players WHERE room_id=?", (room_id,))
    conn.commit(); conn.close()

def db_room_join(room_id, pilot, account):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO room_players(room_id,pilot_name,account_name) VALUES(?,?,?)",
                 (room_id, pilot, account))
    conn.commit(); conn.close()

def db_room_leave(pilot):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM room_players WHERE pilot_name=?", (pilot,))
    conn.commit(); conn.close()

def db_get_pilots_in_room(room_id):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT pilot_name, joined_at FROM room_players WHERE room_id=? ORDER BY joined_at",
        (room_id,)).fetchall()
    conn.close(); return rows

def db_get_room_for_pilot(pilot_name):
    """Return (room_id, room_slot) if pilot has an open room, else None.
    Checks by creator_pilot first (most common), then room_players membership.
    Logs the result explicitly so connection drops are diagnosable.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute(
            "SELECT room_id, room_slot FROM rooms "
            "WHERE status='open' AND creator_pilot=? "
            "ORDER BY created_at DESC LIMIT 1", (pilot_name,)).fetchone()
        if not row:
            row = conn.execute(
                "SELECT r.room_id, r.room_slot FROM rooms r "
                "JOIN room_players p ON r.room_id=p.room_id "
                "WHERE r.status='open' AND p.pilot_name=? "
                "ORDER BY r.created_at DESC LIMIT 1", (pilot_name,)).fetchone()
        conn.close()
        if row:
            log('DB', f'db_get_room_for_pilot("{pilot_name}") -> room_id={row[0]} slot=0x{row[1]:02x}')
        else:
            log('DB', f'db_get_room_for_pilot("{pilot_name}") -> None (no open room)')
        return (row[0], row[1]) if row else None
    except Exception as e:
        log('DB', f'db_get_room_for_pilot error: {e}')
        return None

def db_room_player_count(room_id):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT COUNT(*) FROM room_players WHERE room_id=?", (room_id,)).fetchone()
    conn.close(); return row[0] if row else 0

# --- Ticket template ----------------------------------------------------------

TICKET_PATHS = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ticket_base.vr1'),
    r"C:\games\FA\ticket.vr1", r"C:\Games\FA\ticket.vr1", "ticket.vr1",
]

def load_ticket_template():
    global TICKET_TEMPLATE
    for path in TICKET_PATHS:
        if not os.path.exists(path): continue
        data = open(path, 'rb').read()
        if len(data) != TICKET_SIZE:
            log('TICKET', f'Skipping {path}: size {len(data)} != {TICKET_SIZE}'); continue
        TICKET_TEMPLATE = bytearray(data)
        base_acct = data[TICKET_ACCT_OFF:TICKET_ACCT_OFF+TICKET_ACCT_LEN].split(b'\x00')[0].decode(errors='replace')
        base_pid  = hx(data[TICKET_PID_OFF:TICKET_PID_OFF+4])
        log('TICKET', f'Template loaded: {path} ({TICKET_SIZE}b) base_acct="{base_acct}" base_pid={base_pid}')
        return True
    log('TICKET', 'No base ticket found - ticket generation unavailable')
    return False

def generate_ticket(account_name: str) -> tuple:
    if TICKET_TEMPLATE is None: raise RuntimeError("No ticket template loaded")
    account_name = account_name.strip()
    if not account_name: raise ValueError("Account name cannot be empty")
    if len(account_name) > TICKET_ACCT_LEN - 1: raise ValueError(f"Account name too long")
    if not all(0x20 <= ord(c) <= 0x7e for c in account_name): raise ValueError("Must be printable ASCII")
    conn = sqlite3.connect(DB_PATH)
    existing = conn.execute("SELECT player_id FROM accounts WHERE account_name=?", (account_name,)).fetchone()
    conn.close()
    if existing: raise ValueError(f'Account "{account_name}" already exists (pid={existing[0]})')
    pid_bytes = pid_hex = None
    for _ in range(200):
        candidate = secrets.token_bytes(4)
        if db_get_account_by_pid(candidate.hex()) is None:
            pid_bytes = candidate; pid_hex = candidate.hex(); break
    if pid_bytes is None: raise RuntimeError("Could not generate unique PID")
    ab_hex  = hx(TICKET_TEMPLATE[TICKET_AB_OFF:TICKET_AB_OFF+16])
    f45_hex = hx(TICKET_TEMPLATE[TICKET_F45_OFF:TICKET_F45_OFF+4])
    ticket = bytearray(TICKET_TEMPLATE)
    ticket[TICKET_PID_OFF:TICKET_PID_OFF+4] = pid_bytes
    acct_field = account_name.encode('ascii') + b'\x00' * (TICKET_ACCT_LEN - len(account_name))
    ticket[TICKET_ACCT_OFF:TICKET_ACCT_OFF+TICKET_ACCT_LEN] = acct_field
    assert len(ticket) == TICKET_SIZE
    db_upsert_account(account_name, pid_hex, f45_hex, ab_hex)
    log('TICKET_GEN', f'Created account="{account_name}" pid={pid_hex}')
    return bytes(ticket), pid_hex

def cmd_gen_ticket(account_name: str):
    try: ticket_bytes, pid_hex = generate_ticket(account_name)
    except Exception as e: log('TICKET_GEN', f'ERROR: {e}'); return
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f'ticket_{account_name}.vr1')
    with open(out_path, 'wb') as f: f.write(ticket_bytes)
    saved = open(out_path, 'rb').read()
    acct_rb = saved[TICKET_ACCT_OFF:TICKET_ACCT_OFF+TICKET_ACCT_LEN].split(b'\x00')[0].decode()
    pid_rb  = hx(saved[TICKET_PID_OFF:TICKET_PID_OFF+4])
    log('TICKET_GEN', f'Saved: {out_path}')
    log('TICKET_GEN', f'  Verify: acct="{acct_rb}" pid={pid_rb} size={len(saved)}b')

def console_handler():
    log('CONSOLE', 'Ready. Commands: gen | list | destroy | loglevel | logmute | logtags | help')
    while running:
        try:
            raw_line = sys.stdin.readline()
        except Exception:
            break
        if raw_line == '':          # EOF (stdin closed / piped / detached)
            log('CONSOLE', 'stdin closed - console commands disabled (server still running)')
            return
        line = raw_line.strip()
        if not line: continue
        try:
            parts = line.split(None, 1); cmd = parts[0].lower()
            if cmd == 'gen':
                if len(parts) < 2: log('CONSOLE', 'Usage: gen <account_name>')
                else: cmd_gen_ticket(parts[1].strip())
            elif cmd == 'list':
                accounts = db_get_all_accounts()
                if not accounts: log('CONSOLE', 'No accounts in DB')
                for a, p, f45, ab in accounts:
                    log('CONSOLE', f'  {a}  pid={p}  pilots={[n for n,_ in db_get_pilots(a)]}')
                rooms = db_get_open_rooms()
                log('CONSOLE', f'Open rooms: {len(rooms)}')
                for r in rooms:
                    rid, rname, creator = r[0], r[1], r[2]
                    trn = r[7] if len(r) > 7 else DEFAULT_TERRAIN
                    pcount = db_room_player_count(rid)
                    tname = TERRAIN_NAMES.get(trn, '?')
                    log('CONSOLE', f'  room {rid}: name={rname!r} creator={creator} '
                                   f'terrain={trn} ({tname}) players={pcount}')
            elif cmd == 'clearrooms':
                conn = sqlite3.connect(DB_PATH)
                conn.execute("UPDATE rooms SET status='closed'")
                conn.execute('DELETE FROM room_players')
                conn.commit(); conn.close()
                log('CONSOLE', 'All rooms cleared')
            elif cmd == 'reopen':
                conn = sqlite3.connect(DB_PATH)
                cur = conn.execute("UPDATE rooms SET status='open' WHERE status='closed'")
                n = cur.rowcount
                conn.commit(); conn.close()
                log('CONSOLE', f'Re-opened {n} closed room(s) (now visible in the arena list)')
            elif cmd == 'destroy':
                # destroy <sceneIdx> [camp] [progress]  - fire msg 36 SCENE DESTROY/STATE at a
                # KNOWN scene index, to validate the msg-36 wire format live (independent of the
                # unconfirmed msg-31 objidx->sceneIdx mapping). Defaults: camp=0xff (neutralized),
                # progress=0.0 (captured/destroyed). Targets every in-game room that has players.
                args = (parts[1].split() if len(parts) > 1 else [])
                if not args:
                    log('CONSOLE', 'Usage: destroy <sceneIdx> [camp=255] [progress=0]')
                else:
                    try:
                        sidx = int(args[0], 0)
                        # default camp = the scene's REAL owning camp so the client names the
                        # target ('You have destroyed <owner> <SceneName>') instead of the
                        # generic 'a bridge' that camp=0xFF forces. Pass an explicit 2nd arg
                        # (e.g. 255) to override.
                        prog = float(args[2]) if len(args) > 2 else 0.0
                    except ValueError:
                        log('CONSOLE', 'destroy: sceneIdx/camp must be ints, progress a float')
                    else:
                        rooms = {x.current_room for x in get_all_sessions()
                                 if getattr(x, 'entered_game', False) and x.current_room is not None}
                        if not rooms:
                            log('CONSOLE', 'destroy: no in-game players to send to')
                        for rid in rooms:
                            if len(args) > 1:
                                camp = int(args[1], 0)
                            else:
                                camp = scene_camp(_probe_terrain_for_room(rid), sidx)
                            broadcast_scene_36(rid, [(sidx, camp, prog)], reason='(console destroy)')
            elif cmd == 'probe':
                # probe <sceneIdx>            fire one destroy + capture ev=0x00 reconciliation
                # probe sweep [lo] [hi] [gap]  walk a scene range, building the whole map
                # probe save | show | stop
                pa = (parts[1].split() if len(parts) > 1 else [])
                rooms = {x.current_room for x in get_all_sessions()
                         if getattr(x, 'entered_game', False) and x.current_room is not None}
                if not pa:
                    log('CONSOLE', 'Usage: probe <sceneIdx> | probe sweep [lo hi gap] | probe save | show | stop')
                elif pa[0] == 'sweep':
                    if not rooms:
                        log('CONSOLE', 'probe: no in-game players to probe')
                    else:
                        lo = int(pa[1], 0) if len(pa) > 1 else 0
                        hi = int(pa[2], 0) if len(pa) > 2 else 59
                        gap = float(pa[3]) if len(pa) > 3 else 3.0
                        for rid in rooms:
                            probe_sweep(rid, lo, hi, gap)
                        log('CONSOLE', f'probe sweep {lo}..{hi} gap={gap}s started on {len(rooms)} room(s)')
                elif pa[0] == 'stop':
                    with PROBE_LOCK: PROBE['stop'] = True
                    log('CONSOLE', 'probe sweep stop requested')
                elif pa[0] == 'save':
                    n, path = probe_save(); log('CONSOLE', f'probe: {n} objIdx->sceneIdx entries saved to {path}')
                elif pa[0] == 'show':
                    with PROBE_LOCK:
                        for sc in sorted(PROBE['map']):
                            log('CONSOLE', f'  scene {sc}: objs {sorted(PROBE["map"][sc])}')
                        if not PROBE['map']: log('CONSOLE', '  (no captures yet)')
                else:
                    try:
                        sc = int(pa[0], 0)
                    except ValueError:
                        log('CONSOLE', 'probe: sceneIdx must be an int'); sc = None
                    if sc is not None:
                        if not rooms:
                            log('CONSOLE', 'probe: no in-game players to probe')
                        for rid in rooms:
                            probe_fire(rid, sc)
                        log('CONSOLE', f'probe scene {sc} fired; ev=0x00 objects will be captured (probe show to view)')
            elif cmd == 'corr':
                # corr watch | show | stop | map <obj> <scene> | find <obj> [lo hi gap]
                ca = (parts[1].split() if len(parts) > 1 else [])
                rooms = {x.current_room for x in get_all_sessions()
                         if getattr(x, 'entered_game', False) and x.current_room is not None}
                if not ca:
                    log('CONSOLE', 'Usage: corr watch | show | stop | map <obj> <scene> | find <obj> [lo hi gap]')
                elif ca[0] == 'watch':
                    with CORR_LOCK:
                        CORR['watch'] = True; CORR['weapon'].clear(); CORR['last05'].clear()
                    log('CONSOLE', 'corr: watching ev=0x05 weapon targets. Strafe ONE building, then `corr show`.')
                elif ca[0] == 'stop':
                    with CORR_LOCK: CORR['watch'] = False; CORR['stop'] = True
                    log('CONSOLE', 'corr: stopped watching / sweep cancelled')
                elif ca[0] == 'show':
                    with CORR_LOCK:
                        items = sorted(CORR['weapon'].items(), key=lambda kv: -kv[1]['dmg'])
                        if not items: log('CONSOLE', '  (no ev=0x05 weapon hits captured yet)')
                        for o, w in items:
                            log('CONSOLE', f'  obj {o}: {w["hits"]} hits, total dmg {w["dmg"]}')
                elif ca[0] == 'map':
                    if len(ca) >= 3:
                        try:
                            o = int(ca[1], 0); sc = int(ca[2], 0)
                            p = corr_map_save(o, sc)
                            log('CONSOLE', f'corr: recorded weapon obj {o} -> scene {sc} in {p}')
                        except ValueError:
                            log('CONSOLE', 'corr map: obj and scene must be ints')
                    else:
                        log('CONSOLE', 'Usage: corr map <obj> <scene>')
                elif ca[0] == 'find':
                    if len(ca) >= 2 and rooms:
                        try:
                            o = int(ca[1], 0)
                            lo = int(ca[2], 0) if len(ca) > 2 else 0
                            hi = int(ca[3], 0) if len(ca) > 3 else 59
                            gap = float(ca[4]) if len(ca) > 4 else 4.0
                            for rid in rooms:
                                corr_find(rid, o, lo, hi, gap)
                            log('CONSOLE', f'corr find obj {o} started (keep strafing it!)')
                        except ValueError:
                            log('CONSOLE', 'corr find: obj must be an int')
                    elif not rooms:
                        log('CONSOLE', 'corr find: no in-game players')
                    else:
                        log('CONSOLE', 'Usage: corr find <obj> [lo hi gap]')
                else:
                    log('CONSOLE', f'corr: unknown subcommand {ca[0]!r}')
            elif cmd == 'autopve':
                # autopve on|off|status|hp <n>  - live control of weapon-damage auto-destroy
                aa = (parts[1].split() if len(parts) > 1 else [])
                global AUTO_SCENE_DESTROY, SCENE_DEFAULT_HP
                if not aa or aa[0] == 'status':
                    log('CONSOLE', f'autopve: {"ON" if AUTO_SCENE_DESTROY else "OFF"}, '
                                   f'scene HP threshold={SCENE_DEFAULT_HP}, tracked scenes={len(SCENE_HP)}')
                elif aa[0] == 'on':
                    AUTO_SCENE_DESTROY = True
                    log('CONSOLE', 'autopve ON - weapon damage now auto-destroys scenes (obj==sceneIdx)')
                elif aa[0] == 'off':
                    AUTO_SCENE_DESTROY = False
                    log('CONSOLE', 'autopve OFF')
                elif aa[0] == 'hp' and len(aa) > 1:
                    try:
                        SCENE_DEFAULT_HP = int(aa[1], 0)
                        log('CONSOLE', f'autopve: scene HP threshold set to {SCENE_DEFAULT_HP}')
                    except ValueError:
                        log('CONSOLE', 'autopve hp: value must be an int')
                elif aa[0] == 'reset':
                    SCENE_HP.clear()
                    for x in get_all_sessions():
                        x.__dict__.pop('_scene_destroyed', None)
                    log('CONSOLE', 'autopve: scene HP + destroyed-set reset')
                else:
                    log('CONSOLE', 'Usage: autopve on | off | status | hp <n> | reset')
            elif cmd == 'evp':
                # evp on|off|status|set <a> <f> <bg> <s> <t>  - enemy flak (AA quality in GAME_DEF)
                ea = (parts[1].split() if len(parts) > 1 else [])
                global EVP_AA_ENABLED, EVP_AA_QUALITY
                if not ea or ea[0] == 'status':
                    log('CONSOLE', f'evp: {"ON" if EVP_AA_ENABLED else "OFF"}, AA quality='
                                   f'{EVP_AA_QUALITY} (AAquality/Flak/BomberGunner/ShipAA/TankAA). '
                                   f'Re-enter the arena to apply.')
                elif ea[0] == 'on':
                    EVP_AA_ENABLED = True
                    log('CONSOLE', 'evp ON - enemy flak enabled; re-enter the arena so the '
                                   'GAME_DEF re-serves with AA quality set')
                elif ea[0] == 'off':
                    EVP_AA_ENABLED = False
                    log('CONSOLE', 'evp OFF - re-enter the arena to silence the guns')
                elif ea[0] == 'set' and len(ea) >= 6:
                    try:
                        EVP_AA_QUALITY = tuple(max(0, min(10, int(x))) for x in ea[1:6])
                        log('CONSOLE', f'evp: AA quality set to {EVP_AA_QUALITY}')
                    except ValueError:
                        log('CONSOLE', 'evp set: five ints (0..10) required')
                else:
                    log('CONSOLE', 'Usage: evp on | off | status | set <AA> <Flak> <BomberGunner> <ShipAA> <TankAA>')
            elif cmd == 'rec':
                # rec on|off|status|dump  - flight recorder (reliable + telemetry ring per client)
                ra = (parts[1].split() if len(parts) > 1 else [])
                global FLIGHT_RECORDER
                if not ra or ra[0] == 'status':
                    _sess=get_all_sessions()
                    log('CONSOLE', f'rec: {"ON" if FLIGHT_RECORDER else "OFF"}, '
                                   f'ring rel={FLIGHT_REC_RELMAX}/unrel={FLIGHT_REC_UNRMAX}, '
                                   f'{len(_sess)} live session(s), dir={FLIGHT_REC_DIR}')
                elif ra[0] == 'on':
                    FLIGHT_RECORDER = True; log('CONSOLE', 'rec ON - flight recorder capturing')
                elif ra[0] == 'off':
                    FLIGHT_RECORDER = False; log('CONSOLE', 'rec OFF')
                elif ra[0] == 'dump':
                    n=0
                    for s in get_all_sessions():
                        _p=_rec_dump(s, 'manual console dump')
                        if _p:
                            n+=1; log('CONSOLE', f'  dumped {s.current_pilot} -> {_p}')
                    log('CONSOLE', f'rec dump: wrote {n} file(s)')
                else:
                    log('CONSOLE', 'Usage: rec on | off | status | dump')
            elif cmd == 'loglevel':
                a = parts[1].split() if len(parts) > 1 else []
                if len(a) == 2 and a[0] == 'console':
                    _falog.set_console_level(a[1]); log('CONSOLE', f'console level -> {a[1].upper()}')
                else:
                    log('CONSOLE', 'Usage: loglevel console <DEBUG|INFO|WARNING|ERROR>')
            elif cmd == 'logmute':
                if len(parts) > 1: _falog.mute_tag(parts[1].strip()); log('CONSOLE', f'muted {parts[1].strip()}')
                else: log('CONSOLE', 'Usage: logmute <TAG>')
            elif cmd == 'logunmute':
                if len(parts) > 1: _falog.unmute_tag(parts[1].strip()); log('CONSOLE', f'unmuted {parts[1].strip()}')
                else: log('CONSOLE', 'Usage: logunmute <TAG>')
            elif cmd == 'logtags':
                log('CONSOLE', f'muted tags: {_falog.list_muted() or "(none)"}')
            elif cmd == 'help':
                log('CONSOLE', 'gen <name>  - generate ticket for new account')
                log('CONSOLE', 'list        - show all accounts and their pilots')
                log('CONSOLE', 'destroy <sceneIdx> [camp] [progress] - fire msg 36 SCENE DESTROY to in-game players')
                log('CONSOLE', 'loglevel console <LVL> | logmute <TAG> | logunmute <TAG> | logtags - logging control')
            else: log('CONSOLE', f'Unknown command "{cmd}". Type "help".')
        except Exception:
            logx('CONSOLE', f'command failed: {line!r}')

# --- SYN identification -------------------------------------------------------

def identify_account_from_syn(syn_data):
    payload = syn_data[8:]
    pid_hex = hx(payload[SYN_OFF_PID:SYN_OFF_PID+4])   if len(payload) > SYN_OFF_PID+4  else '00000000'
    ab_hex  = hx(payload[SYN_OFF_AUTH:SYN_OFF_AUTH+16]) if len(payload) > SYN_OFF_AUTH+16 else '0'*32
    f45_hex = hx(payload[SYN_OFF_F45:SYN_OFF_F45+4])   if len(payload) > SYN_OFF_F45+4  else '00000000'
    null = payload.find(b'\x00', SYN_OFF_ACCT)
    raw  = payload[SYN_OFF_ACCT:null] if null > SYN_OFF_ACCT else b''
    acct = raw.decode('ascii', errors='ignore').strip()
    log('SYN', f'pid={pid_hex}  acct_raw={raw.hex()!r}  acct="{acct}"')
    if acct and all(0x20 <= ord(c) <= 0x7e for c in acct):
        log('SYN', f'Identified: account="{acct}" pid={pid_hex}')
        db_upsert_account(acct, pid_hex, f45_hex, ab_hex)
        return (acct, pid_hex, f45_hex, ab_hex)
    log('SYN', f'Name unreadable, falling back to pid search')
    row = db_get_account_by_pid(pid_hex)
    if row: return row
    for row in db_get_all_accounts():
        pid_bytes = bytes.fromhex(row[1])
        idx = payload.find(pid_bytes)
        if idx >= 0:
            if idx >= 20:
                ab_scan  = hx(payload[idx-20:idx-4])
                f45_scan = hx(payload[idx-4:idx])
                db_upsert_account(row[0], row[1],
                    f45_scan if f45_scan != '0'*8 else row[2],
                    ab_scan  if len(ab_scan)==32  else row[3])
            return db_get_account_by_pid(row[1])
    return None

# --- Startup ------------------------------------------------------------------

init_db(); init_rooms_db(); load_ticket_template()
for _a, _p, *_ in db_get_all_accounts():
    log('DB', f'account="{_a}" pid={_p} pilots={[n for n,_ in db_get_pilots(_a)]}')

# --- Packet builders ----------------------------------------------------------

# Time-sync epoch. The in-game STATUS/TIME beacon (type 2, p[1]=0x40, p[2]=0x80) and
# the time_reply (type 2, p[2]=0x80) carry a packed time dword at p[8:12]:
#   A = dword & 0x3FFFF  (low 18 bits)  - a MILLISECOND timestamp the client converts
#                                         to seconds (A/1000) + fixed-point fraction
#   B = dword >> 18      (high 14 bits) - a delay correction, SUBTRACTED; must stay 0
# The client (vcncNet.dll, RecalculateDriftRate @0x10008739) fits a linear regression of
# clock-offset (serverTime - localTime) vs localTime over 8 samples; the slope is the
# drift Rate. If serverTime ADVANCES 1:1 with local time the offset is constant -> slope 0.
# The old code sent A=int((time.time()%1.0)*1000) (0..999, sawtoothing every second), so
# decoded whole-seconds never advanced -> slope -1.00075 -> NET time froze ~60s in (the
# 'CRAP!!! HUGE backward NET Time' meltdown @0x10009ff2) -> disconnect. Sending a
# MONOTONIC ms counter makes A/1000 advance at 1 s/s -> slope 0. Masked to the 18-bit
# field (keeps B=0); wraps every 0x3FFFF ms ~= 262 s - the client re-bases from samples
# far more often (every ~8 beacons), so the wrap never lands inside a fit window.
_TSYNC_T0 = time.time()
def tsync_ms():
    """Monotonically-advancing millisecond value for the beacon/time_reply A field."""
    return int((time.time() - _TSYNC_T0) * 1000) & 0x3FFFF

def build_synack():
    fa_s, fa_frac = fa_timestamp()
    p = bytearray(84); p[2]=0x10
    struct.pack_into('>I',p,8,fa_s); struct.pack_into('>I',p,12,fa_frac)
    c=16
    # The client memcpy's 0x44 (68) bytes of this body (from packet+0x10) into its net-config
    # struct at vcncNet 0x10020300 and ntohl's each dword. cfg+0x40 (== packet byte 80) is the
    # RTT-sample RING CAPACITY: it sizes the ring array at struct+0x4c (0x100203ac) and is the
    # divisor in the sampler FUN_10006f55 (`div [esi+0x48]`). We previously left byte 80 = 0, so
    # the client got cap=0 -> (a) div-by-zero in the sampler and (b) an unbounded ring whose
    # writes can reach the delivery-callback pointer at 0x1002042c (exactly 64 u16 slots past the
    # array start). The `next_exp=seq+2` ACK fix normally suppresses sampling, but a client cs
    # RESET on each world re-entry misaligns it for a few packets and lets a sample slip through
    # -> div-by-zero -> CTD. That is the plane-independent "~3rd re-entry" crash. Sending a valid
    # cap <= 64 makes the ring correctly sized: no div-by-zero, and slot writes stop BEFORE the
    # callback. 32 is conservative (half the safe region) and matches the scale of neighbours.
    RTT_RING_CAP = 32   # cfg+0x40; must be 1..64 (64 = array ends right before the callback ptr)
    for off,val in [(0,30),(0x14,8),(0x18,5000),(0x1C,10),(0x20,30000),
                    (0x24,5000),(0x28,200),(0x2C,50),(0x30,100),(0x34,16),(0x38,16),(0x3C,100),
                    (0x40,RTT_RING_CAP)]:
        struct.pack_into('>I',p,c+off,val)
    return bytes(p), fa_s

def build_time_reply(cd):
    ti = struct.unpack_from('>H',cd,8)[0] if len(cd)>=10 else 0
    ms=tsync_ms(); p=bytearray(144); p[0]=2; p[2]=0x80
    struct.pack_into('>I',p,8,ms&0x3FFFF); struct.pack_into('>H',p,12,STATUS_INDEX)
    struct.pack_into('>H',p,14,ti); return bytes(p)

def build_beacon(seq, idx=0):
    ms=tsync_ms(); p=bytearray(144); p[0]=2; p[1]=0x40; p[2]=0x80
    struct.pack_into('<H',p,6,seq&0xFFFF); struct.pack_into('>I',p,8,ms&0x3FFFF)
    struct.pack_into('>H',p,12,STATUS_INDEX); struct.pack_into('>H',p,14,idx); return bytes(p)

def build_rel_ack(cid, seq=0, next_exp=None):
    # CUMULATIVE ACK -- ROOT-CAUSE FIX for the 3rd-reentry CTD.
    # Bit layout (matches vcncNet's own ACK builder FUN_10002a76 / router FUN_100032da):
    #   bits 20-28 = acked-seq (drives the client's RTT sample lookup)
    #   bits 17-19 = type (1 = reliable ACK)
    #   bits  8-16 = next-expected (drives cumulative send-queue removal)
    # WHY: vcncNet keeps a 70-entry RTT-sample history ring based at vcncNet+0x203AC;
    # ring index 64 physically overlaps the registered packet-delivery callback pointer
    # at vcncNet+0x2042c. The ring head advances once per RTT sample, and a sample is
    # taken on the FIRST *timed* ACK of each client packet (FUN_10006f55, whose sole
    # caller is the ACK processor FUN_10006b0e). After ~64 samples the head writes through
    # the callback -> next delivery via (*callback)() faults (the CTD).
    # The old code sent next_exp=0, which forced vcncNet down the single-packet ACK path
    # that finds the packet still queued and DOES sample -> one ring step per client packet.
    # Sending next_exp = seq+2 makes vcncNet remove 'seq' via the cumulative loop
    # FIRST. (The loop internally does next_exp-=1 then removes base..next_exp-1, so seq+2
    # is required to clear seq itself; seq+1 only clears base..seq-1 and leaves seq to be
    # removed -- and SAMPLED -- via the single-packet lookup, which is why seq+1 didn't work.)
    # With seq removed by the loop, the subsequent same-packet RTT lookup misses
    # (FUN_10005e0d returns 0 -> duplicate path FUN_10006fd7) so NO sample is taken. Send-queue
    # removal stays correct (we only ever clear base..seq; the +1 lives in a cosmetic tracker);
    # the ring head never advances, so the callback is never overwritten. RTT estimation is
    # lost, which is harmless on LAN.
    if next_exp is None: next_exp = (seq + 2) & 0x1FF
    p=bytearray(8); p[0]=0; p[1]=cid&0xFF; p[2]=2
    struct.pack_into('>I',p,4,(seq<<20)|0x00020000|((next_exp&0x1FF)<<8)); return bytes(p)

def build_data(cmd, sq=0):
    p=bytearray(15); p[0]=2; p[2]=0x20; p[10]=(cmd>>8)&0xFF; p[11]=cmd&0xFF; p[14]=sq&0xFF
    return bytes(p)

def build_rel(payload, seq=0):
    h=bytearray(8); h[0]=0; h[2]=0x20; h[3]=seq&0xFF
    struct.pack_into('>I',h,4,0x20000000); return bytes(h)+bytes(payload)

def build_appspace_pkt(data_bytes):
    n = len(data_bytes); bc = 0 if n<=1 else (n-1+15)//16; size = bc*16+1
    pl = bytearray(4+size); pl[0]=bc&0xFF; pl[1]=0x12; pl[4:4+min(n,size)]=data_bytes[:size]
    return bytes(pl)

def build_appspace_pkt_exact(data_bytes):
    """Like build_appspace_pkt but the payload is the EXACT length of data_bytes -
    NO rounding up to bc*16+1, so NO trailing zero padding. Required for the 212
    GAME_DEF: the client decompresses exactly `size-5` bytes (mix.cpp), and any pad
    bytes are fed into the decompressor -> DecompressedResultSize overflow / corrupt
    parse. The real server's 212 ('in 212'793') is likewise not bc*16+1-aligned, i.e.
    sent at exact size. bc is still set (block hint) but the buffer is not padded."""
    n = len(data_bytes); bc = 0 if n <= 1 else (n - 1 + 15) // 16
    pl = bytearray(4 + n); pl[0] = bc & 0xFF; pl[1] = 0x12; pl[4:4 + n] = data_bytes
    return bytes(pl)

def build_ingame_pkt(data_bytes):
    """BYTE-EXACT in-game framing. THE real Size formula (pinned from the vcncnet log):
    the client computes  Size = bc*16 + (T>>4)  where bc = appspace header byte 0 and
    T = header byte 1. The length is SPLIT - high bits in bc (x16), low 4 bits in T's
    HIGH nibble; T's low nibble (0x2) = the APPSPACE-data channel (-> 'Cmd 0'). Proof:
    StartPlace bc=0 T=0x42 -> 0+4=4; 0x3a echo bc=7 T=0x92 -> 112+9=121; cd chat bc=3
    T=0x12 -> 48+1=49; 212 bc=84 T=0x12 -> 1345. build_appspace_pkt/_exact HARDCODE T=0x12,
    i.e. they pin the size's low nibble to 1 - that's why every message was forced onto the
    Size == 1 (mod 16) grid and small msgs had to be padded. To send Size == n exactly:
    bc = n>>4, T = ((n&0xf)<<4) | 0x2. For n=5 (ServerConfirm): bc=0, T=0x52 -> Size 5 ->
    (5-1)/4 = exactly 1 record. (messages34: the old T=0x12 with bc=0 gave Size = 0*16+1 = 1
    -> client read 1 byte -> 0 records -> no confirm -> freeze. THIS is the actual fix.)"""
    n = len(data_bytes); bc = (n >> 4) & 0xFF
    pl = bytearray(4 + n); pl[0] = bc; pl[1] = ((n & 0x0f) << 4) | 0x02
    pl[4:4 + n] = data_bytes
    return bytes(pl)

def build_typed_pkt(type_byte, data_bytes, bc=None):
    n = len(data_bytes)
    if bc is None: bc = 0 if n <= 1 else (n - 1 + 15) // 16
    size = bc * 16 + 1; pl = bytearray(4 + size)
    pl[0] = bc & 0xFF; pl[1] = type_byte; pl[4:4 + min(n, size)] = data_bytes[:size]
    return bytes(pl)

def build_auth64(pid_hex, f45_hex, ab_hex, acct):
    d = bytearray(64)
    pid=bytes.fromhex(pid_hex); f45=bytes.fromhex(f45_hex); ab=bytes.fromhex(ab_hex)
    acct_b=(acct.encode() if isinstance(acct,str) else acct)+b'\x00'
    d[4:8]=pid[:4]; d[8:12]=f45[:4]; d[12:16]=ab[:4]; d[16:32]=ab[:16]
    d[32:32+len(acct_b)]=acct_b[:32]; return bytes(d)

def build_auth_response(auth64):
    pl=bytearray(80); pl[0]=4; pl[3]=0x64; pl[4:16]=auth64[32:44]; pl[16:80]=auth64
    return bytes(pl)

def build_da_session():
    data=bytearray(17); data[0]=0xDA; data[1]=0x01
    return build_appspace_pkt(bytes(data))

def build_da_session_safe():
    """63-misdispatch-safe variant of the 0xDA lobby re-attach, for the EXIT-TO-HQ
    path only (NOT login). After >=3 enter/fly/exit cycles the client routes this 0xDA
    to the msg-63 ChangePlayerCB handler FUN_004fa9c0 instead of the 218 handler
    FUN_004edcf0 (reproducible: messages29 'in 218'17' early, 'in 63'17' at the crash).
    FUN_004fa9c0 consumes FIXED 7-byte records with NO count, asserting Length>=0
    (VNet_Rcv.cpp:1227) when a remainder of 1..6 bytes is left after the last full
    record. The old Size-17 packet => Length 16 -> 9 -> 2 -> tries a 3rd record -> -5
    -> assert -> CTD. Size 15 => Length 14 -> 7 -> 0 -> loop exits clean (exactly two
    7-byte records, both 'Unknown RemotePlayer' no-ops in single-player). payload[0]
    stays 0xDA so a CORRECT dispatch still hits the 218 handler, which only reads
    offsets 1/5/9 (Size!=0x19) -> all within 15 bytes, identical effect to Size 17.
    build_ingame_pkt sends Size==n exactly: n=15 -> bc=0, T=0xf2 (T>>4=15, low nibble
    2 = appspace-data channel)."""
    return build_ingame_pkt(bytes([0xDA, 0x01]) + bytes(13))

def build_e1_pilot_list(pilots):
    data = bytearray([0xe1])
    for (name, _slot) in pilots:
        data.extend((name.encode() if isinstance(name,str) else name) + b'\x00')
    pl = build_appspace_pkt(bytes(data)); bc = pl[0]
    log('PILOTS', f'{len(pilots)} pilot(s) bc={bc}(p3={bc*16+1}): {[n for n,_ in pilots]}')
    return pl

def build_empty_room_list(sub_cmd):
    return build_appspace_pkt(bytes([sub_cmd]))

def build_ce_room_list(rooms):
    """Build 0xce AppSpaceList response.

    0xce = AppSpaceList = PLAYER/SQUADRON PRESENCE list, NOT the arena/room list.
    Evidence: sending GAME_DEF bytes via 0xce causes FA.exe to:
      - Parse them as player/squad records
      - Send sub=0xd7/0xd9 packets with IDs extracted from our GAME_DEF
      - Populate the Squadrons tab with faction names
      - NEVER add a room to the arena list
    Empty 0xce (just the byte) = correctly represents "0 players in lobby".
    TODO: find which sub-command (0xca ServerList? 0xcb GameList?) holds the room list.
    Ghidra targets: FUN_006ace60, FUN_0070f940, XREF to ArenaSt (0x00a59ad8),
                    RECEIVER<EVENT_LOBBY_CREATE_ONE_GAME_ARENAS_INFO> at 0x00bf9c98.
    """
    return build_appspace_pkt(bytes([0xce]))  # empty = 0 lobby players

# --- 0xcb GameList (ARENA LIST) - experimental, switchable --------------------
#
# Confirmed via Ghidra this session:
#   FUN_004f03b0  : client sends bare [0xcb] on lobby entry = GameList request.
#   FUN_0070eda0  : displays ArenasInfo (LobbyDialogsInitPars+0xa0), 40B entries,
#                   renders the string at entry+8.
#   FUN_006ad210  : ArenasInfo::operator[]  -> base+index*0x28.
#   FUN_006af980  : JOIN reads ArenaSt[+4]=GameIndex, ArenaSt[+0xc]=GameDef(0 OK).
#   FUN_0076bd00  : finds ArenaSt by matching [+4]==GameIndex.
# In-memory ArenaSt: [+0]type [+4]GameIndex [+8]name [+0xc]GameDef(optional).
#
# The WIRE format of the 0xcb RESPONSE (what the receive-parser converts into
# those 40B records) is the one thing we could NOT pin from decompilation, so
# this builder offers several candidates. Flip GAMELIST_FORMAT and re-test.
#
# GameIndex convention observed for room CREATION echoes:
#   bytes[2:6] = [0x00][0xff][0xff][name[0]]  ->  e.g. "Test1" -> 0x54ffff00.
# We reuse that here so a listed arena's GameIndex matches what Join expects.

GAMELIST_FORMAT = 'empty'   # 0xcb is the LOBBY PLAYER list, not arenas - keep empty until handled separately

def _arena_gameindex(name, room_id=0):
    """GameIndex as FA derives it for a room: 4 LE bytes [room_id&0xff][ff][ff][name[0]].
    name[0] is the MSB (it overlaps the creator-name field in the room echo). The LOW
    byte - a fixed 0x00 before 2026-06-29 - now carries room_id, so two rooms whose
    creators share a first letter no longer collide on the GameIndex. room_id=0
    reproduces the legacy value, kept as a resolution fallback in _find_room_by_gidx."""
    first = (name.encode()[:1] or b'\x00')[0]
    return bytes([room_id & 0xff, 0xff, 0xff, first])   # 4 bytes, little-endian on wire

def build_gamelist(rooms):
    """Build the 0xcb GameList (arena list) response.

    `rooms` = rows from db_get_open_rooms():
        (room_id, room_name, creator_pilot, account_name, created_at, room_slot, game_def_raw)
    """
    fmt = GAMELIST_FORMAT
    data = bytearray([0xcb])

    if fmt == 'empty' or not rooms:
        log('GAMELIST', f'0xcb -> empty ({len(rooms)} rooms, fmt={fmt})')
        return build_appspace_pkt(bytes([0xcb]))

    if fmt == 'byte_name':
        # CONFIRMED by decompiling the 0xcb receive parser (FUN_004ef8b0):
        #   payload = [0xcb] then, per arena, [1 byte id][name + NUL].
        # The parser reads pkt[1]=id (-> ArenaSt+4 / GameIndex via FUN_004ed150),
        # then scans the name to its NUL (-> ArenaSt+8, the displayed field),
        # advancing strlen+2 per record; it stops on an empty name (so trailing
        # zero padding is a safe terminator). The leading byte is irrelevant for
        # display, so we use a 1-based arena index here.
        for i, r in enumerate(rooms, start=1):
            nm = (r[1] or 'Arena')
            data.append(i & 0xFF)                  # 1-byte id (non-zero)
            data.extend(nm.encode()[:31] + b'\x00')  # name + NUL

    elif fmt == 'names':
        # FA's proven list convention (cf. 0xe1 pilot list): just concatenated
        # null-terminated names, no count, no index. Client assigns indices.
        for r in rooms:
            nm = (r[1] or 'Arena')
            data.extend(nm.encode()[:31] + b'\x00')

    elif fmt == 'idx_name':
        # Per arena: [GameIndex 4B LE][name \0]
        for r in rooms:
            nm = (r[1] or 'Arena')
            data.extend(_arena_gameindex(nm))
            data.extend(nm.encode()[:31] + b'\x00')

    elif fmt == 'count_idx_name':
        # [count 1B] then [GameIndex 4B][name \0] per arena
        data.append(len(rooms) & 0xFF)
        for r in rooms:
            nm = (r[1] or 'Arena')
            data.extend(_arena_gameindex(nm))
            data.extend(nm.encode()[:31] + b'\x00')

    elif fmt == 'fixed40':
        # Mirror the in-memory 40B ArenaSt minus the vtable:
        #   [+0:4]=0  [+4:8]=GameIndex  [+8:0x28]=name padded to 32B
        for r in rooms:
            nm = (r[1] or 'Arena')
            rec = bytearray(40)
            rec[4:8] = _arena_gameindex(nm)
            nb = nm.encode()[:31]
            rec[8:8+len(nb)] = nb
            data.extend(rec)

    else:
        log('GAMELIST', f'unknown GAMELIST_FORMAT={fmt!r}, sending empty')
        return build_appspace_pkt(bytes([0xcb]))

    pkt = build_appspace_pkt(bytes(data))
    bc = pkt[0]
    names = [ (r[1] or 'Arena') for r in rooms ]
    log('GAMELIST', f'0xcb -> {len(rooms)} arena(s) fmt={fmt} '
                    f'payload={len(data)}B bc={bc}(p3={bc*16+1}): {names}')
    log('GAMELIST', f'0xcb payload hex: {bytes(data).hex()}')
    return pkt

# --- 0xd2 ARENA LIST (THE REAL ONE) -------------------------------------------
#
# CONFIRMED this session via the real 2009 capture (messages04.log) + Ghidra:
#   * Real lobby prefetch: 0xce(squadrons) 0xca(news) 0xcb(lobby players) then
#     out 210'1 -> in 210'1110  <- the 1110-byte ARENA/ROOM LIST.
#   * handler[0xd2] = FUN_004efda0 parses it and fires PTR_LOOP_00bfe95c, which is
#     the arena dialog's receiver (FUN_0076e8b0 param_1[3], vtable 0xaa9658) ->
#     writes the displayed arena vector (LobbyDialogsInitPars +0xa8) that
#     FUN_0070eda0 renders. So 0xd2 IS the arena tab's list.
#   * The Arenas tab issues NO query on click - it renders this prefetch data and
#     receives live 0xcc(204) updates afterward.
#
# Record format (from the FUN_004efda0 parse loop):
#   [0xd2] then per room:
#       [12-byte header]   - only header[+4:+8] = GameIndex is read by the parser
#       [name1 \0]         - primary name (FUN_007ed210(pcVar10) -> displayed)
#       [name2 \0]         - second string (host/owner column)
#   Stride = 12 + len(name1)+1 + len(name2)+1; loop stops on empty/over-length,
#   so trailing zero padding terminates safely.
#
# GameIndex must match what JOIN expects. FA derives a created room's GameIndex as
# bytes[2:6] of the 0xdc create = [00 ff ff creator[0]] (e.g. "Test1" -> 0x54ffff00),
# so we reuse that here keyed on the creator pilot.

# Per-arena terrain now comes from the DB (extracted from each room's GAME_DEF at
# creation). ARENA_TRN_NUMBER is only the fallback when a row somehow lacks one.
ARENA_TRN_NUMBER = DEFAULT_TERRAIN

def build_arenalist(rooms):
    """Build the 0xd2 arena/room list response (the Arenas tab's list)."""
    data = bytearray([0xd2])
    if not rooms:
        log('ARENALIST', f'0xd2 -> empty (0 rooms)')
        return build_appspace_pkt(bytes([0xd2]))
    listed = []
    records = []
    for r in rooms:
        room_name = (r[1] or 'Arena')
        creator   = (r[2] or room_name)          # pilot who created the room
        gamedef = bytes(r[6]) if len(r) > 6 and r[6] else b''
        trn      = extract_terrain_from_gamedef(gamedef) & 0xFF    # param[0x39]; 1..99
        planeset = 0                                              # desc+0x04; 0 = default Planes.txt
        # 12-byte record header - field->descriptor map PROVEN from FUN_004efda0
        # disassembly (the register loads feeding FUN_004ef130->FUN_004ed040):
        #   [+0:4]  *(rec+0)        -> desc+0x04  PLANE-SET (validated by FUN_004c2b60)
        #   [+4:4]  GameIndex       -> desc+0x08  (also the uVar2 key; matches Join)
        #   [+8]    flag byte: bit0->desc+0x10, bit1->desc+0x14, bit2->desc+0x20
        #   [+9:2]  ushort          -> desc+0x18
        #   [+11]   HIGH byte of the +8 dword -> desc+0x1c  TERRAIN (_TrnNumber) *
        hdr = bytearray(12)
        hdr[0:4]  = (planeset & 0xFFFFFFFF).to_bytes(4, 'little')  # plane-set (default)
        hdr[4:8]  = _arena_gameindex(creator, r[0])                     # [00 ff ff creator[0]]
        hdr[8]    = 0                                             # flag bits (none)
        hdr[9:11] = (0).to_bytes(2, 'little')                     # desc+0x18 (unused)
        hdr[11]   = trn                                           # TERRAIN -> desc+0x1c *
        # Name slots (empirically, from v167 live test): the FIRST name is the
        # category/section HEADER the client groups rows under; the SECOND name is
        # the arena's own row label. So name1 = category, name2 = the room's name.
        category = (r[8] if len(r) > 8 and r[8] else 'Custom Arenas')   # name1 section header (web-editable)
        records.append((bytes(hdr), category.encode()[:31], room_name.encode()[:31]))
        listed.append((room_name, trn))
    # Assemble. The 0xd2 parser (FUN_004efda0) is length-driven - it keeps starting
    # new records until consumed >= len, with NO bounds check, so leftover zero pad
    # would spawn a phantom record and read past the buffer -> crash. build_appspace_pkt
    # frames to bc*16+1, so the LAST record must absorb the pad. Pad name2 (the arena's
    # DISPLAY label), NOT name1: name1 is the CATEGORY the client groups rows under, and
    # any trailing spaces on it make an otherwise-identical category compare unequal, so a
    # shared group (e.g. two 'Dogfighting' arenas) splits into a duplicate 'Dogfighting   
    # Arenas' header. Trailing spaces on name2 are display-only and invisible in the list.
    def _assemble(extra_pad):
        d = bytearray([0xd2])
        last = len(records) - 1
        for i, (hdr, cat, arena) in enumerate(records):
            d.extend(hdr)
            d.extend(cat + b'\x00')                       # name1 = CATEGORY (grouping key) - keep clean
            if i == last and extra_pad > 0:
                d.extend(arena + (b'\x20' * extra_pad) + b'\x00')   # pad the DISPLAY label instead
            else:
                d.extend(arena + b'\x00')
        return d
    d0 = _assemble(0)
    L  = len(d0)
    bc = 0 if L <= 1 else (L - 1 + 15) // 16
    size = bc * 16 + 1
    pad = size - L
    data = _assemble(pad)
    pkt = build_appspace_pkt(bytes(data)); bc = pkt[0]
    desc = [f'{n}(trn{t}:{TERRAIN_NAMES.get(t, "?")})' for n, t in listed]
    log('ARENALIST', f'0xd2 -> {len(rooms)} arena(s) payload={len(data)}B '
                     f'bc={bc}(p3={bc*16+1}) pad={pad}: {desc}')
    log('ARENALIST', f'0xd2 payload hex: {bytes(data).hex()}')
    return pkt

# --- 0xd4 / 212  GAME_DEF push (v164 experiment) ------------------------------
#
# The 0xd2 list record carries ONLY GameIndex + 2 names; the parser never sets the
# descriptor's terrain field (desc+0x1c stays 0 -> _TrnNumber>=1 assert at tab-open).
# Terrain lives in the arena's GAME_DEF (a packed BINARY blob, NOT INI text - the
# client pretty-prints it as Terrain=N). The 212 handler FUN_004ed9c0 reads the
# message as [0xd4][LobbyIndex:4 != 0][binary blob], then FUN_0057f390 deserialises
# the blob into the arena object (incl. terrain). Hypothesis: the list display
# resolves each arena's terrain from a GAME_DEF the client has cached, keyed by
# GameIndex. A server arena this client never selected was never cached -> terrain 0
# -> crash. So push the stored GAME_DEF as a 212 (same GameIndex as the 0xd2 record)
# BEFORE the list, so the arena - with its real terrain - is cached first.
def build_gamedef_212(room):
    """[0xd4][GameIndex:4][LZ GAME_DEF] as an APPSPACE packet, EXACT bc*16+1 size.
    The stored blob is LZ-compressed at a size (==4 mod16) that can't sit on the
    bc*16+1 grid. We decompress it and RE-ENCODE it as an all-literals LZ stream whose
    size we control (comment pad) so the 212 payload lands exactly on bc*16+1 - no
    over-read, valid version byte, parser consumes the whole decompressed buffer."""
    creator = (room[2] or room[1] or 'Arena')
    gidx    = _arena_gameindex(creator, room[0])          # 4 bytes [00 ff ff creator[0]] (non-zero)
    blob    = bytes(room[6]) if len(room) > 6 and room[6] else b''
    comp, D, pad = build_lz_gamedef(blob, planeset_for_room(room),
                                    force_ffa=(FFA_NEUTRAL_GUARD and is_ffa_room(room)),
                                    plane_camp=plane_camp_for_room(room),
                                    arena_settings=db_get_room_settings(room[0]))
    if comp is None:
        log('GAMEDEF212', f'LZ build failed for room {room[0]}; skipping 212')
        return None
    payload = bytes([0xd4]) + gidx + comp
    n = len(payload); bc = 0 if n <= 1 else (n - 1 + 15) // 16
    log('GAMEDEF212', f'212 LZ gidx={gidx.hex()} decompressed={D}B pad={pad} '
                      f'comp={len(comp)}B name={room[1]!r} payload={n}B bc*16+1={bc*16+1} '
                      f'{"ALIGNED" if n==bc*16+1 else "MISALIGNED!"}')
    return build_appspace_pkt_exact(payload)

def build_join_game_answer_201(client_number=0, player_index=0):
    """FA message 201 (0xc9) = VNET::JoinToGameAnswer - the server's grant in reply to
    the client's SendEnterToGame (200/0xc8). Decoded from handler FUN_004f88f0
    (VNET::JoingToGameAnswerCB), dispatch slot _DAT_00c821fc (id 201):
        [0xc9][ClientNumber:4 LE signed][PlayerIndex:4 LE signed]   (read at +1 and +5)
    ClientNumber >= 0 AND PlayerIndex >= 0  ->  client allocates its client+player
    objects, sets DAT_00bfedb4=ClientNumber (clears the 0xfffffffe 'entering' state),
    sends 0x41, sets DAT_00c82eb0=0 (STOPS the 0x43 poll) and DAT_00c82348=1 (game
    active). ClientNumber < 0  ->  'not granted, keep polling' (what our 0x43 confirm
    effectively signalled). Handler reads fixed offsets, so bc*16+1 zero-pad is fine."""
    payload = (bytes([0xc9])
               + (client_number & 0xFFFFFFFF).to_bytes(4, 'little')
               + (player_index  & 0xFFFFFFFF).to_bytes(4, 'little'))
    log('JGA201', f'JoinToGameAnswer ClientNumber={client_number} PlayerIndex={player_index} '
                  f'payload={payload.hex()}')
    return build_appspace_pkt(payload)


# -- IN-ARENA CHAT (msg 20 / 0x14) ----------------------------------------------
# Decoded from the message-20 dispatch handler FUN_004f6030 (lobby builder
# FUN_004f1490 installs it at slot _DAT_00c81f28). The handler:
#   iVar6 = GetPlayer(*(param_1+2))          ; PlayerIndex at +2 (4 bytes, LE)
#       if 0  ->  "ChatMessage from unknown player with PlayerIndex=%i" + drop
#   channel = *(param_1+1)                   ; +1
#       3      ->  FUN_0046a420(0,0xd,"%s: %s", name, text)            (plain)
#       4      ->  uppercase(text) then same + sound                  (shout)
#       0/1/2  ->  team/squadron-coloured "%s: %s", BUT only if player+0x1c != 0;
#                 squad colour looked up from *(param_1+6) (SquadronId)
#   text = param_1+10
# So the DISPLAY wire form (what the client renders) is:
#       [0x14][channel:1][PlayerIndex:4 LE][SquadronId:4 LE][text\0]
# i.e. the SEND form [0x14][channel][text\0] with an 8-byte PlayerIndex+SquadronId
# inserted after the channel. Our old blind echo left the text where PlayerIndex
# should be, so the handler read "Hell" (0x6C6C6548) as the index -> unknown player.
# We stamp PlayerIndex=0 - the player allocated by the 201 grant - so it resolves to
# the local pilot ("Test1").

def build_chat_display_20(channel, text, player_index=0, squadron_id=0):
    """Build the DISPLAY form of msg 20 so the client renders a chat line."""
    if isinstance(text, str):
        text = text.encode('ascii', 'replace')
    text = text.split(b'\x00')[0]  # stop at first NUL - drop any trailing wrapper bytes
    payload = (bytes([0x14, channel & 0xFF])
               + (player_index & 0xFFFFFFFF).to_bytes(4, 'little')
               + (squadron_id  & 0xFFFFFFFF).to_bytes(4, 'little')
               + text + b'\x00')
    return build_appspace_pkt(payload)


def reflect_chat_20(s, channel, text, player_index=0):
    """Reflect an in-arena chat so it renders in the chat pane. Recipients are scoped to
    the SENDER's room (multi-room isolation) and, for team/squadron channels, further to
    same-side / same-squad players: channel 0=all (whole room), 1=team (same nation),
    2=squadron (same squad - squad tracking TODO, currently sender only). The line is
    stamped with the SENDER's PlayerIndex so every recipient resolves it to the sender's
    name via FUN_004f6030's GetPlayer."""
    if isinstance(text, (bytes, bytearray)):
        disp = text.split(b'\x00')[0].decode('ascii', 'replace')
    else:
        disp = str(text)
    room = s.current_room
    room_players = get_sessions_in_room(room) if room is not None else []
    if channel == 1:
        targets = [x for x in room_players if x.nation == s.nation]
    elif channel == 2:
        targets = [s]                       # squadron membership not modelled yet
    else:
        targets = list(room_players)        # channel 0 = whole room
    if s not in targets:
        targets.append(s)
    if not targets:
        targets = [s]
    pkt = build_chat_display_20(channel, text, player_index=s.player_index)
    log('CHAT20', f'reflect ch={channel} {disp!r} from PI={s.player_index} '
                  f'-> {len(targets)} player(s) in room {room}')
    for sess in targets:
        threading.Thread(target=lambda _s=sess: send_rel(_s, pkt,
                         f'<- chat-20 ch={channel} {disp!r}', to=3.0), daemon=True).start()

def build_arena_players_213(room, counts=None, names=None):
    """FA message 213 - arena player info, the reply to the client's 'out 213' request.
    Layout decoded from incoming-213 handler FUN_004ef6e0:
        [0xd5][GameIndex:4][8 x uint16 per-nation counts]   (header = 0x15 = 21 bytes)
        then a length-driven list of [player_name\\0] (the arena roster).
    The 8 uint16s at +5..+0x13 are pushed to observers as per-nation player tallies
    (the Nations-list counts). local_30 (GameIndex) must be non-zero or the handler
    no-ops. Sent at EXACT length (no bc*16+1 zero pad) so the roster loop ends on the
    wire length - zero padding would be parsed as phantom empty-name players."""
    creator = (room[2] or room[1] or 'Arena')
    gidx = _arena_gameindex(creator, room[0])                         # 4 bytes, non-zero
    counts = (list(counts) if counts else [0] * 8)[:8]
    while len(counts) < 8:
        counts.append(0)
    payload = bytearray([0xd5]) + gidx
    for c in counts:
        payload += int(c & 0xFFFF).to_bytes(2, 'little')     # 8 ushorts = 16 bytes
    # COUNTS ONLY - no trailing strings. Re-RE of the incoming-213 handler
    # (FUN_004ef6e0) shows the strings after +0x15 are NOT a roster: each NUL-string
    # (budgeted strlen+1+2) is appended to a UI list - and that list renders in the
    # arena-selection page's "Combat Action" box. Our invented roster is exactly the
    # "player names + corrupt strings" bug (the per-record trailing bytes, e.g.
    # nation=0xff, parsed as 1-char garbage strings). Per-nation grouping comes from
    # the 8 counts above, not from names here. Until we emulate real combat-action
    # lines, send counts only; bc-grid zero padding may yield blank entries at most.
    if names:
        log('ARENA213', f'NOTE: roster names suppressed (combat-action box): {names}')
    log('ARENA213', f'213 gidx={gidx.hex()} counts={counts} (counts-only) '
                    f'payload={len(payload)}B')
    return build_appspace_pkt_exact(bytes(payload))

# -- PLAYER-OBJECT LAYER (msgs 62 / 63 / 96) ------------------------------------
# Decoded from FA.exe VNet_Rcv.cpp handlers (dispatch table FUN_004f1490):
#   msg 62 (0x3e) -> FUN_004fa5f0  "Add existing REMOTE_PLAYER %s PlayerIndex=%i"
#   msg 63 (0x3f) -> FUN_004fa9c0  ChangePlayerCB (op=add/remove/change-camp)
#   msg 96 (0x60) -> FUN_004f53b0 -> FUN_00629600  SCORE_TABLE (ScoreTable.cpp)
#
# CRITICAL FRAMING - THE bc*16+1 OVER-DELIVERY BUG (root cause of every CTD v182-v186):
# The client's appspace layer does NOT deliver the exact datagram length to message
# handlers. It delivers Length = bc*16+1, where bc is the block count in the vcnc
# header. PROVEN by the client trace (vcncnet...510.log) for our 8-byte msg 63:
#     ProcessMessages(256) Cmd=0 Size=17
#     Receiving Message 0 - Data: 3f 00 00 00 00 00 00 01 | 00 00 00 8a 00 00 00 00 e6
# Our 7-byte record, then 9 bytes of STALE RECEIVE-BUFFER GARBAGE (here the head of
# the prior 212 stream: 8a 00 00 ...). All three handlers (62 FUN_004fa5f0,
# 63 FUN_004fa9c0, 96 FUN_00629600) are length-driven record loops that parse until
# Length runs out and then assert "Length>=0" at severity 0xffffffff (fatal). The
# garbage tail is parsed as phantom records; the final partial record drives Length
# negative -> assertion -> DLL_PROCESS_DETACH ~2s later. This - NOT use-after-free,
# NOT premature world state - was the killer in every player-object crash.
#
# THE RULE: a length-driven payload MUST TILE EXACTLY to bc*16+1, i.e.
# len(payload) % 16 == 1, with the padding forming PARSER-VALID, side-effect-free
# records. build_appspace_pkt_exact is a no-op fiction here (the client ignores the
# real length); each builder below pads itself to the bc*16+1 boundary:
#   63: pad to a multiple of 16 fixed records with dummy PlayerIndex (lookup fails ->
#       "Unknown RemotePlayer" log -> skipped, zero side effects).
#   62: pad the LAST record's trailing (unused, scanned) string - absorbs 0..15B.
#   96: append one pad group whose count tiles the remainder (7 is invertible mod 16);
#       it writes zero score-defs at a high object-type base -> harmless.
#
# DEPENDENCY CHAIN (the actual player-object lifecycle):
#   62 creates the REMOTE_PLAYER object  ->  63 sets its Camp()/side (player+0x2c)
#   ->  96 feeds the scoreboard.  v175's guess that the 121-byte msg 58 set side
#   membership was WRONG: msg 58 (FUN_004eff50, LobbyRcv.cpp) is a LOBBY 3-byte-record
#   list, not the in-arena side-setter. Side membership is msg 63 op=change-camp.

def _pad_to_bc_boundary_len(payload_len):
    """Return how many bytes to add so payload_len becomes == 1 (mod 16) = bc*16+1."""
    return (1 - payload_len) % 16

MSG_ADD_PLAYER_62      = 0x3e
MSG_CHANGE_PLAYER_63   = 0x3f
MSG_SCORE_TABLE_96     = 0x60
MSG_SERVER_CONFIRM_5   = 0x05    # in-game ServerConfirm (post-takeoff sim-loop gate)
SERVERCONFIRM_READY    = True    # build_ingame_pkt (floored bc) -> client Size=5 -> 1 record
ADD_TEST_PLAYER        = False   # was True (fake Test2 roster test). OFF now: with a REAL
                                 # 2nd client it would collide on PlayerIndex 1 and add a
                                 # phantom. Re-enable only for solo roster tests.

# msg 63 ChangePlayerCB ops (the per-record op byte at record+6):
# msg 63 ChangePlayerCB ops (the per-record op byte at record+6). Decoded from the
# branch structure of FUN_004fa9c0: after the player is found by index,
#     if (iVar12 == 1) -> CAMP path: writes rp->Camp() at player+0x2c
#     else (any op != 1) -> DELETE path: FUN_007fca00 + free(player object)
# v182 SHIPPED THESE INVERTED (CAMP=2) -> op=2 hit the delete path and freed a live
# player object -> crash-to-desktop on side-select (messages07.log, WinError 10054).
CP_OP_CAMP   = 1     # iVar12==1 -> change-camp (set side); the ONLY op that sets +0x2c
CP_OP_REMOVE = 0     # any op != 1 -> delete the remote player object (we use 0)

def build_add_player_62(records):
    """FA msg 62 (0x3e) - Add existing REMOTE_PLAYER (handler FUN_004fa5f0).
    Per-record wire layout (decompiled record stride):
        [PlayerIndex:4 LE][side:1][reserved:1][name\\0][str2\\0]
    The handler reads PlayerIndex at +0, side at +4 (masked &0xf, valid 0..8 else
    0xffffffff), a byte at +5, then a NUL-terminated name at +6, then a SECOND
    NUL-terminated string (scanned but unused for our purposes - send empty).
    `records` = list of (player_index, side, name). side None -> 0xff (unassigned).
    Sent at EXACT length - see CRITICAL FRAMING note above.

    *** INVARIANT: a 62 sent to client X must NEVER contain X's own PlayerIndex. ***
    The msg 201 grant handler (FUN_004f88f0) already creates the LOCAL player's entry
    in the same table (FUN_004f3230, camp=-1, local pilot name). A 62 record for an
    existing index takes the "Add existing REMOTE_PLAYER" path: delete + free + re-add.
    For the local index that would free the live local player while the GamerClient
    (DAT_00c6eb98+0x128) still points at it. (NOTE: the v185 self-62 CTD was ALSO
    caused by bc*16+1 framing garbage - see v187 - but this delete+re-add hazard is
    real independent of framing, so the invariant stands. Peers only.)"""
    data = bytearray([MSG_ADD_PLAYER_62])
    for pi, side, name in records:
        sb = 0xff if side is None else (side & 0xff)
        nb = (name.encode('ascii', 'replace') if isinstance(name, str) else name)
        data += (pi & 0xFFFFFFFF).to_bytes(4, 'little')
        data += bytes([sb, 0x00])
        data += nb + b'\x00'      # name
        data += b'\x00'           # str2 (empty, NUL-terminated)
    # TILE to bc*16+1 (see CRITICAL FRAMING): the handler scans str2 to its NUL, so
    # we can grow the LAST record's str2 with filler bytes before its terminator
    # without adding a phantom record. Remove the lone terminator we just wrote,
    # insert `pad` filler bytes, then re-terminate.
    pad = _pad_to_bc_boundary_len(len(data))
    if pad:
        data = data[:-1] + (b'\x20' * pad) + b'\x00'   # spaces inside str2, then NUL
    assert len(data) % 16 == 1, f'62 framing {len(data)} !==1 mod16'
    log('PLAYER62', f'AddPlayer {len(records)} rec(s) (pad={pad}): '
                    f'{[(pi, sd, (n if isinstance(n,str) else n.decode("ascii","replace"))) for pi,sd,n in records]}')
    return build_appspace_pkt_exact(bytes(data))

# Dummy PlayerIndex for 63 padding records: a value the client's player table will
# never contain, so FUN_007fcac0 lookup fails -> "Unknown RemotePlayer(%i)" log ->
# record skipped with ZERO side effects (no add, no delete, no camp write).
DUMMY_PLAYER_INDEX = 0xFFFFFFFE

MSG63_TRUE_LENGTH = True   # send msg-63 as the real 'in 63'8' (true-length in-game framing).
                           # Set False to fall back to the legacy bc*16+1 padded form.
def build_change_player_63(records):
    """FA msg 63 (0x3f) - ChangePlayerCB (handler FUN_004fa9c0). Fixed 7-byte records:
        [PlayerIndex:4 LE][side:1][reserved:1][op:1]
    op (record+6), from the handler's branch structure after the player is found:
        op == 1  -> CHANGE-CAMP: writes rp->Camp() (player+0x2c) to `side` (masked &0xf).
                   This is the message that moves a player between nation groups.
        op != 1  -> DELETE: frees the remote player object (FUN_007fca00 + free).
    An unknown PlayerIndex logs "Unknown RemotePlayer(%i)" and is skipped - so the
    target must already exist (via the 201 grant for self, or a peer's 62), and must
    NOT be the recipient's own index for a delete op.
    `records` = list of (player_index, side, op).

    FRAMING - TRUE LENGTH (the 2009 'in 63'8' form, fully reverse-engineered):
      The handler is dispatched with (body, length); it reads the msg-id byte then loops
      `while length > 0` consuming 7 bytes/record. The client derives `length` from the
      packet size, which vcncNet computes as  Size = bc*16 + (T>>4)  (bc = appspace header
      byte 0, T = byte 1).  build_appspace_pkt_exact HARDCODES T=0x12, pinning Size's low
      nibble to 1 - so an 8-byte 1-record 63 arrived as Size=17 ('in 63'17'), the loop
      over-read into 2+ records, and we had to pad to 16 records with DUMMY(-2) entries.
      Cost of that workaround: 15 phantom 'Unknown RemotePlayer(-2)' operations PER roster
      change - something the real 2009 server (always 'in 63'8', 1306x, zero -2 errors) never
      did, and the leading suspect for the cumulative in-flight freeze.
      build_ingame_pkt encodes the EXACT size instead:  bc=n>>4, T=((n&0xf)<<4)|2.  For a
      1-record 63 (n=8): bc=0, T=0x82 -> Size = 0*16+8 = 8 -> 'in 63'8' -> handler reads exactly
      one 7-byte record, 0 leftover. No padding, no phantom records. Multiple real records
      still work (n = 1 + 7*k stays exact). Size bound: the client caps at 5000, far above
      any real roster."""
    recs = list(records)
    n = len(recs)
    data = bytearray([MSG_CHANGE_PLAYER_63])
    for pi, side, op in recs:
        sb = 0xff if side is None else (side & 0xff)
        data += (pi & 0xFFFFFFFF).to_bytes(4, 'little')
        data += bytes([sb, 0x00, op & 0xff])
    if MSG63_TRUE_LENGTH:
        # true-length in-game framing - the real 'in 63'<len>' form, no dummy padding
        log('PLAYER63', f'ChangePlayer {n} real rec(s) [true-len {len(data)}B]: {records}')
        return build_ingame_pkt(bytes(data))
    # ---- legacy fallback: pad to a multiple of 16 records (bc*16+1 grid) ----
    target = ((n + 15) // 16) * 16 if n else 16
    while len(recs) < target:
        recs.append((DUMMY_PLAYER_INDEX, None, 0))
    data = bytearray([MSG_CHANGE_PLAYER_63])
    for pi, side, op in recs:
        sb = 0xff if side is None else (side & 0xff)
        data += (pi & 0xFFFFFFFF).to_bytes(4, 'little')
        data += bytes([sb, 0x00, op & 0xff])
    assert len(data) % 16 == 1, f'63 framing {len(data)} !==1 mod16'
    log('PLAYER63', f'ChangePlayer {n} real + {target - n} pad rec(s) [legacy]: {records}')
    return build_appspace_pkt_exact(bytes(data))

def build_server_confirm_5(number, ident=0):
    """FA msg 5 - ServerConfirm (wire handler FUN_007e5030, in-game dispatch idx 5 @
    table 0xcbc190+0x14). THE post-takeoff gate: the client registers its plane locally
    with a per-client monotonic IDENT (0 for its first object), sends its full state
    (out 4'33), then blocks until the server stamps a global object NUMBER onto it -
    only then does the sim loop ('out 6') start. Missing it = the ~20s flight freeze.

    Wire: [0x05] then N x [Number:u16 LE][ident:u16 LE]; 'in 5'5' = exactly 1 record.
    FUN_007e5030 finds the local object whose registration ident == `ident`, asserts its
    NumberVar==-1, sets NumberVar=Number + ClientVar=own-id, then fires the object's
    OnConfirm (FUN_00427690 -> logs 'ServerConfirm. Client=%i, Number=%i', sets
    DAT_00bfedb8=Number). Number<0 OR ident-not-found -> the client DELETEs instead, so
    Number must be a valid non-negative u16 and `ident` must match a live local object.
    Sent BYTE-EXACT via build_ingame_pkt: n=5 -> bc=0 -> client Size=max(1,5)=5 ->
    (5-1)/4 = exactly 1 record. (build_appspace_pkt_exact's CEIL bc would give bc=1 ->
    Size=17 -> 4 records -> 3 dummy confirms -> 'not found, send delete' / assert -> CTD.)"""
    data = bytes([MSG_SERVER_CONFIRM_5]) + struct.pack('<HH', number & 0xFFFF, ident & 0xFFFF)
    return build_ingame_pkt(data)

def build_add_player_62(records):
    """FA msg 62 (0x3e) - AddPlayer / REMOTE_PLAYER (handler FUN_004fa5f0, VNET table
    0xc81ed8 slot 62). Adds remote players to the in-game ROSTER/scoreboard (not a 3D
    object - that's msg 2). Per-record wire format, looped until Length consumed:
        [PlayerIndex:u32 LE][camp:u8][field:s8][name:asciiz]
    record size = 7 + len(name). camp 0-8 valid (handler does camp & 0xf; >=9 -> camp=-1).
    FUN_004fa5f0 looks the player up by PlayerIndex, allocates a 0x24-byte REMOTE_PLAYER
    (FUN_004f3230(idx,camp,field)), sets the name, and fires the roster/announce UI
    (logs 'Add existing REMOTE_PLAYER %s' if the index already exists). Verified vs real
    log: in 62'18 = [0x3e]+17B rec = 7+10-char name; in 62'24 = 7+16.
    `records` = [(player_index, camp, name[, field]), ...]. Returns the raw msg-62
    sub-message bytes (type+records) for wrapping in a msg 13 batch."""
    data = bytearray([0x3e])                                  # MSG_ADD_PLAYER_62
    for rec in records:
        pidx, camp, name = rec[0], rec[1], rec[2]
        if camp is None: camp = 0          # player not in a side yet -> side 0; msg 63 corrects it
        field = rec[3] if len(rec) > 3 else 0
        nb = name.encode('latin1', 'replace')[:31] + b'\x00'  # asciiz, capped
        data += struct.pack('<I', pidx & 0xFFFFFFFF)
        data += bytes([camp & 0xff, field & 0xff])
        data += nb
    return bytes(data)

def build_msg13(*submsgs):
    """FA msg 13 (0x0d) - the sim-conductor BATCH CONTAINER (handler LAB_007e3230 @
    0x7e3230). Wraps N sub-messages, each as [len:u16 LE][submsg: type+data, `len` bytes];
    the client then dispatches each one through the normal tables exactly as if received
    standalone (type<0x14 -> in-game 0xcbc190, else VNET 0xc81ed8). This is the literal
    '{ ... }' group in the real log - e.g. in 13'132 = 1 + (2+18) + (2+24) + (2+83) {62,62,2}.
    Each arg is the raw type+data of one sub-message (e.g. from build_add_player_62).
    Framed BYTE-EXACT via build_ingame_pkt so the client's Size == the real byte count."""
    data = bytearray([0x0d])                                  # MSG_SIM_BATCH_13
    for sm in submsgs:
        data += struct.pack('<H', len(sm))                    # sub-message length prefix
        data += sm
    return build_ingame_pkt(bytes(data))

def build_score_table_96(nation_scores=None, object_groups=None):
    """FA msg 96 (0x60) - SCORE_TABLE (FUN_004f53b0 -> FUN_00629600, ScoreTable.cpp).

    *** SEND ONLY ON REQUEST (bare inbound 0x60) - NEVER UNSOLICITED AT ENTRY ***
    v183 sent this on the 201 grant and crashed arena-join (messages08.log): the
    handler frees+reallocates the host-side score-table object before the client's
    world is stood up (~3s stall -> WinError 10054). The client REQUESTS the table
    with a bare 0x60 right after the FLY 23 StartPlace grant (messages09.log) -
    answer it then, and only then.

    The dispatch handler FUN_004f53b0 passes (payload+1, len-1) to FUN_00629600, which
    reads its buffer starting at the VERSION byte:
        [0x60][version=0x02][7 x uint16 LE tallies]   (handler buffer = version-first)
    so on the wire, immediately after the 0x60 msg-id comes version 0x02, then the 7
    ushorts (param_1[0..6]). version MUST be 2 or the client asserts
    "Wrong SCORE_TABLE version". Header total = 1(id)+1(ver)+14 = 16 bytes.
    Then a length-driven list of object-score groups; each group:
        [base_index:1][count:1] then (count+1) x 7-byte object records
        [obj_type:1][score:2 LE][kills:2 LE][?:2 LE]
    NOTE the +1: the parser does `param_2 = count + 1` and loops that many times,
    consuming 9 + 7*count bytes per group, then asserts Length>=0. An empty arena
    needs NO real groups (loop guard `param_3>0` ends immediately after the header).

    FRAMING: like 62/63 the client delivers Length=bc*16+1, so the payload must tile
    to ==1 (mod 16) or the leftover bytes are parsed as a garbage group -> the
    ScoreTable.cpp:0x6c "Length>=0" assert (fatal). Header is 16B (==0 mod16), so an
    otherwise-empty table needs +1 byte... but a group is min 9B. We instead append
    ONE pad group sized so 9+7N tiles the whole payload: since gcd(7,16)=1 there is
    always an N in 0..15. The pad group uses a high base_index (240) so its zero
    score-defs land on unused object-type slots - harmless. See CRITICAL FRAMING."""
    ns = (list(nation_scores) if nation_scores else [0] * 7)[:7]
    while len(ns) < 7:
        ns.append(0)
    data = bytearray([MSG_SCORE_TABLE_96, 0x02])        # msg-id, then SCORE_TABLE version
    for v in ns:
        data += int(v & 0xFFFF).to_bytes(2, 'little')   # 7 ushorts = 14 bytes
    n_real_groups = 0
    if object_groups:
        for base_index, recs in object_groups:
            n_real_groups += 1
            # count byte = len(recs)-1 because the parser loops count+1 times
            cnt = max(len(recs) - 1, 0)
            data += bytes([base_index & 0xff, cnt & 0xff])
            for (obj_type, score, kills, extra) in recs:
                data += bytes([obj_type & 0xff])
                data += int(score & 0xFFFF).to_bytes(2, 'little')
                data += int(kills & 0xFFFF).to_bytes(2, 'little')
                data += int(extra & 0xFFFF).to_bytes(2, 'little')
    # TILE to bc*16+1 with one pad group consuming 9+7N bytes.
    deficit = _pad_to_bc_boundary_len(len(data))        # 0..15 bytes still needed
    # We must add a whole group: solve 9 + 7N == deficit (mod 16) for N in 0..15.
    inv7 = 7   # 7*7=49==1 mod16, so 7-1 == 7
    N = (inv7 * (deficit - 9)) % 16
    pad_recs = N + 1                                     # parser loops count+1 times
    data += bytes([0xF0, N & 0xff])                     # base_index=240, count=N
    data += b'\x00' * (7 * pad_recs)                    # zeroed score-defs
    assert len(data) % 16 == 1, f'96 framing {len(data)} !==1 mod16'
    log('SCORE96', f'ScoreTable nation_scores={ns} real_groups={n_real_groups} '
                   f'pad_group(N={N}, recs={pad_recs})')
    return build_appspace_pkt_exact(bytes(data))

# msg-96 = per-object-type point RULES; FUN_004f53b0 FREES the client's own loaded table and
# rebuilds from ours, so we MUST supply valid defs or a kill reads uninitialised memory
# (-> Score:-64662, bogus Ace/Rank, freeze - messages13 03.43.45). Two hard constraints from RE:
#   * SIZE: the msg must fit ONE reliable packet. A full 256-slot table was 1889B and the client
#     never ACKed it (entry hung -> 10054); a 1345B GAME_DEF does ACK, so the ceiling is ~MTU. The
#     score-def INDEX is the object's TYPE (FUN_00447520: bounds 0..255, but planes log Type=2 -
#     a small CATEGORY), so only low slots matter. Populate 0..31 -> ~321B, well inside one packet.
#   * FIELD: the scorer reads score-def+0xc (FUN_00449b60); the parser (FUN_00629600) fills that
#     from the record's THIRD u16 = the 'extra' field, NOT 'score'. Value must be > 0.
# Record tuple is (obj_type, score, kills, extra) - the points go in `extra`.
OBJ_SCORE_POINTS_DEFAULT = 100
SCORE_DEFS_DEFAULT = [(0, [(t, 0, 0, OBJ_SCORE_POINTS_DEFAULT) for t in range(32)])]

def push_player_roster_62(s, reason=''):
    """Send msg 62 to s: the full set of OTHER players already in s's room, so the
    client builds a REMOTE_PLAYER object for each. Self is excluded (the local pilot
    is the player object allocated by the 201 grant, not a remote)."""
    room_id = s.current_room
    if room_id is None:
        return
    peers = [x for x in get_sessions_in_room(room_id) if x is not s]
    if not peers:
        log('PLAYER62', f'no peers in room {room_id} to advertise to {s.current_pilot} {reason}')
        return
    records = [(p.player_index, p.nation, p.current_pilot or 'Player') for p in peers]
    pkt = build_msg13(build_add_player_62(records))   # WRAP in msg-13 batch (build_add_player_62
                                                      # returns a RAW sub-message; sending it
                                                      # unwrapped made the client read bc=0x3e=62)
    send_rel(s, pkt, f'<- AddPlayer 62 ({len(records)} peer(s)){(" " + reason) if reason else ""}', to=5.0)

def broadcast_player_join_62(joiner, reason=''):
    """Tell every OTHER player in joiner's room to add `joiner` as a REMOTE_PLAYER
    (msg 62, single record). Symmetric to push_player_roster_62, for the live case
    where someone enters a room others are already in."""
    room_id = joiner.current_room
    if room_id is None:
        return
    peers = [x for x in get_sessions_in_room(room_id) if x is not joiner]
    if not peers:
        log('PLAYER62', f'no peers in room {room_id} to announce {joiner.current_pilot} to '
                        f'{(reason or "").strip()}')
        return
    rec = [(joiner.player_index, joiner.nation, joiner.current_pilot or 'Player')]
    pkt = build_msg13(build_add_player_62(rec))       # WRAP in msg-13 batch (was sent raw -> bc=62)
    n = 0
    for sess in peers:
        threading.Thread(target=lambda _s=sess: send_rel(_s, pkt,
                         f'<- AddPlayer 62 (joiner {joiner.current_pilot}){(" " + reason) if reason else ""}',
                         to=3.0), daemon=True).start()
        n += 1
    log('PLAYER62', f'broadcast join of {joiner.current_pilot} -> {n} peer(s) in room {room_id}')

def broadcast_player_change_63(s, side, op=CP_OP_CAMP, reason=''):
    """Broadcast a msg 63 ChangePlayerCB for session s to EVERY player in the room,
    including s themselves.

    CORRECTED (v185/v186): v183's peers-only rule was a misread of FUN_004fa9c0 -
    the `iVar12 != DAT_00bfedb4` skip is the GetClient (FUN_004f2560) scan over the
    512-entry CLIENT table, skipping the local CLIENT NUMBER (DAT_00bfedb4 is set to
    jga->ClientNumber in the 201 handler), not the player lookup. The rp is resolved
    through FUN_007fcac0 for ANY index, INCLUDING the recipient's own: the msg 201
    grant handler (FUN_004f88f0) creates the local player's entry in that table
    (camp=-1, local pilot name) at join time. A self-directed 63 op=1 therefore
    resolves immediately, sets the camp (which drives friendly/enemy CHAT COLOR via
    FUN_0046bba0 in the msg 20 handler), and prints the "<pilot> changed to
    <nation>" system chat line. This is the designed team-change mechanism.
    The v182 crash was solely the op=2 delete path. NEVER send msg 62 about a
    player's own index (see build_add_player_62 invariant)."""
    room_id = s.current_room
    if room_id is None:
        return
    rec = [(s.player_index, side, op)]
    pkt = build_change_player_63(rec)
    # The SUBJECT must receive its OWN camp change for a real team JOIN (side is a nation):
    # the self-63 is what sets the local player's camp (chat colour + world/chat roster line),
    # and get_sessions_in_room filters on entered_game (briefly False at team-select after an
    # exit-flight), so without this the roster froze on the first side. But NEVER echo a
    # side=None (neutral/leave) self-63 to the subject: telling the client it has no team makes
    # it bail to the lobby (msg-64), and on a reliable-desynced re-entered channel that turns
    # into a back-to-lobby retransmit storm -> 'Test1 leaving GBR' flood -> dropped connection.
    # The transient leave is the client's own action; peers still get it for their roster.
    recipients = list(get_sessions_in_room(room_id))
    if side is not None and s not in recipients:
        recipients.append(s)
    n = 0
    for sess in recipients:
        threading.Thread(target=lambda _s=sess: send_rel(_s, pkt,
                         f'<- ChangePlayer 63 ({s.current_pilot} side={side} op={op})'
                         f'{(" " + reason) if reason else ""}', to=3.0), daemon=True).start()
        n += 1
    log('PLAYER63', f'broadcast camp-change {s.current_pilot} side={side} op={op} -> '
                    f'{n} session(s) incl. self')

def send_arenalist_with_gamedefs(s, rooms, label):
    """v164: send each room's 212 GAME_DEF FIRST, then the 0xd2 list.
    The 212 parse (FUN_0057bee0) calls the terrain setter FUN_004c7cd0(terrain) with
    the GAME_DEF's terrain ushort. build_lz_gamedef now patches that ushort from 0 to a
    valid terrain (FORCE_GAMEDEF_TERRAIN), so when the single arena is auto-selected and
    the list-box builds its Trn preview, _TrnNumber>=1 holds. (v163 sent the list alone
    and still asserted: with no 212 the current terrain stayed 0.)"""
    for r in rooms:
        if len(r) > 6 and r[6]:
            pkt = build_gamedef_212(r)
            if pkt is not None:
                send_rel(s, pkt, f'<- GAME_DEF 212 (room {r[0]})', to=5.0)
                time.sleep(0.01)
    send_rel(s, build_arenalist(rooms), label, to=3.0)

def build_chat_broadcast(pilot_name, message):
    nb = (pilot_name.encode() if isinstance(pilot_name,str) else pilot_name) + b'\x00'
    mb = (message.encode() if isinstance(message,str) else message) + b'\x00'
    return build_appspace_pkt(bytes([0xcd]) + nb + mb)

def build_ui_player_update(pilot_name, is_join=True):
    """Build 0xcc LmsChangePlayers packet to update the lobby UI list."""
    action_flag = 0x01 if is_join else 0x00
    status_byte = 0x00 if is_join else 0xFF
    nb = (pilot_name.encode() if isinstance(pilot_name,str) else pilot_name) + b'\x00'
    return build_appspace_pkt(bytes([0xcc, action_flag, status_byte]) + nb)

# --- Session state ------------------------------------------------------------

_session_counter = itertools.count(1)

class S:
    def __init__(self, cid, addr):
        self.sid = next(_session_counter)
        self.cid=cid; self.addr=addr; self.sq=0; self.ts=0
        self.rx=0; self.closing=False; self.t0=time.time()
        self.rseq=0; self._lock=threading.Lock(); self._evts={}
        self.undgram=0                 # per-session UNRELIABLE datagram seq (byte[3]); separate from rseq
        self._awaiting_reattach=False  # exit-to-HQ: resend 0xDA re-attach UNRELIABLY on each 0x43 poll
        self.auth_done=False; self.post_auth_cmds=[]
        self.account=None; self.auth64=None; self.auth_payload=None
        self.current_pilot=None; self.current_slot=0; self.current_room=None; self.room_slot=0; self.last_43_ts=0.0; self.entered_game=False; self.in_game=False; self.client_granted=False
        self.plane_type=PLANE_TYPE_ID   # v201: player's selected plane index (from out-4 byte[8]); default until first spawn
        # -- Per-room game state (multi-room: every player's runtime state is keyed
        # to the room they entered, so chat / roster / positions never cross rooms) --
        self.client_number=0      # assigned at the 201 grant, unique WITHIN the room
        self.player_index=0       # ditto; stamped into chat/roster so it resolves to us
        self.nation=None          # selected side 0..7 (US=0...), None = "In Menu"/unassigned
        # -- In-game spawn/object state (ServerConfirm + entity stream) --
        self.spawn_ident_next=0   # per-client object IDENT counter (0=first plane); echoed
                                  # in ServerConfirm (msg 5) to bind the client's local
                                  # object to a server object Number.
        self.obj_confirmed=False  # ServerConfirm sent for the current spawn? (reset per StartPlace)
        self.my_obj_number=None   # server-assigned object Number for this player's plane
        self.flying=False         # set once ServerConfirm sent (sim loop should start)
        self.last_telem_tick=None # this player's most recent conductor tick (telemetry[5:7]);
        self.last_telem_time=0.0  # used to re-stamp packets we RELAY *to* this player so the
                                  # tick lands on THEIR clock (small +delta = smooth interp)
        # -- Combat scoring (server-authoritative kill tracking, accumulated in DB) --
        self.last_fired_at=0.0    # time.time() of this session's most recent DAMAGE28 (msg 28);
                                  #   used to attribute a peer's death to the most-recent shooter
        self.k_kills=0; self.k_deaths=0; self.k_score=0  # this-session tallies (DB holds the total)
        # -- Reliable-channel diagnostics (stall hunt) --
        self._rel_rx_time=0.0     # time of last reliable (pt=1) packet FROM this client
        self._unrel_rx_time=0.0   # time of last unreliable in-game packet FROM this client
        self._rel_rx_last_cs=None # last reliable RX seq byte (data[3]); repeats => client retransmit
        self._rel_rx_count=0; self._rel_rx_dups=0; self._ack_in_count=0
        self._stall_warned=False  # STALL-WATCH logs the transition once, not every tick
        # -- Flight recorder rings (dumped to logs/flightrec/ when STALL-WATCH fires) --
        self._rec_rel=deque(maxlen=FLIGHT_REC_RELMAX)    # reliable msgs both directions
        self._rec_unrel=deque(maxlen=FLIGHT_REC_UNRMAX)  # trailing unreliable telemetry
        self._rec_dumped=False    # dump once per stall, re-armed when reliable RX resumes
    def nsq(self): v=self.sq; self.sq=(self.sq+1)&0xFF; return v
    def nundgram(self): v=self.undgram; self.undgram=(self.undgram+1)&0xFF; return v
    def nts(self): self.ts=(self.ts+1)&0xFF; return self.ts
    def ela(self): return time.time()-self.t0
    def nrel(self):
        # Reliable TX seq. The wire carries this as the 8-bit byte[3] (build_rel: h[3]=seq&0xFF),
        # and the server reads the client's reliable seq the same way (cs=data[3], 8-bit). So the
        # counter MUST wrap at 256 to stay in lock-step with the wire and with _evts (keyed on
        # this value). It was &0x1FF (9-bit): fine below 256, but at the 256th reliable send of a
        # session the 9-bit key (256) no longer matched the 8-bit wire seq (0) the client ACKs,
        # so the ACK lookup missed and EVERY reliable send from then on timed out - a slow
        # "everything eventually wedges" failure on long sessions. &0xFF keeps key, wire, and ACK
        # aligned across the wrap.
        with self._lock: v=self.rseq; self.rseq=(self.rseq+1)&0xFF; return v
    def sig(self, seq):
        with self._lock: e=self._evts.get(seq)
        if e: e.set(); return True
        return False
    def mke(self, seq):
        e=threading.Event()
        with self._lock: self._evts[seq]=e; return e
    def rme(self, seq): self._lock.acquire(); self._evts.pop(seq,None); self._lock.release()

sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
# -- Windows UDP WSAECONNRESET trap (FATAL server-recovery fix) ----------------------------
# When the server sendto()s a client that has CTD'd / closed its port, Windows posts an ICMP
# port-unreachable and then raises WSAECONNRESET (WinError 10054) on the NEXT recvfrom() -
# DISCARDING the datagram that was waiting. The dead session's heartbeat keeps firing every
# ~5s, so each one eats an inbound packet; a reconnecting client's SYN / pilot-list / arena-list
# requests get intermittently dropped and come back EMPTY, needing a full server restart. The
# dead session is never reaped because on Windows the failure surfaces on recvfrom, not sendto,
# so the heartbeat's OSError 3-strikes path never fires. Disabling SIO_UDP_CONNRESET makes
# recvfrom ignore the stale ICMP and never drop a good datagram. Guarded/no-op off Windows.
try:
    _SIO_UDP_CONNRESET = getattr(socket, 'SIO_UDP_CONNRESET', 0x9800000C)
    sock.ioctl(_SIO_UDP_CONNRESET, False)
    log('INIT', 'SIO_UDP_CONNRESET disabled (recvfrom survives client CTDs)')
except (AttributeError, OSError, ValueError) as _e:
    log('INIT', f'SIO_UDP_CONNRESET not disabled ({_e!r}) - 10054s handled in recv loop instead')
sock.bind((HOST,PORT)); sock.settimeout(0.5)
sids={}; sadrs={}; sl=threading.Lock(); running=True

# Globally-unique in-game object Number allocator. ServerConfirm (msg 5) stamps this
# onto each spawning player's plane; the client echoes it back as the object id at
# telemetry offset 7-8 (LE u16, e.g. 0x0100 -> bytes 00 01). Distinct per player so a
# relayed stream never collides with the RECIPIENT's own object on the receiver - A's
# plane and B's plane carry different Numbers, so B treats A's update as a remote object.
_obj_num_lock = threading.Lock(); _obj_num_next = 0x0100
_obj_num_free = []   # recycled Numbers from deleted own-planes (LIFO); popped before incrementing
# EXPERIMENT (spawn-freeze hunt): the residual instant mid-flight freeze is cumulative in total
# spawn count, plane-independent, with a provably clean server + reliable channel. The one thing
# that grew unboundedly per spawn was the object Number (256,257,... never reused), a prime
# suspect for a client-side per-object structure that never gets pruned. Recycling the player's
# own Number when their plane is deleted keeps the working set tiny (spawn 50 reuses spawn 5's
# Number) so it either stops the freeze or cleanly rules Numbers out. Safe in single-player (no
# peers); the delete-notify means the client already dropped that object before we re-hand it.
RECYCLE_OBJ_NUMBERS = True
def next_obj_number():
    global _obj_num_next
    with _obj_num_lock:
        if RECYCLE_OBJ_NUMBERS and _obj_num_free:
            return _obj_num_free.pop()          # reuse a freed Number before minting a new one
        n = _obj_num_next
        _obj_num_next = _obj_num_next + 1
        if _obj_num_next > 0xFFFF: _obj_num_next = 0x0100
        return n
def free_obj_number(n):
    """Return a deleted own-plane Number to the recycle pool. No-op if disabled, None, or already
    pooled. Capped so a pathological leak can't grow the list without bound."""
    if not RECYCLE_OBJ_NUMBERS or n is None:
        return
    with _obj_num_lock:
        if n not in _obj_num_free and len(_obj_num_free) < 256:
            _obj_num_free.append(n)

def get_s(addr):
    with sl: return sadrs.get(addr)

def build_unrel(payload, seq=0):
    # UNRELIABLE (pt=0): offset-4 control dword = 0, same 8-byte framing as relay_telemetry
    # (byte[2]=0x20, byte[3]=datagram seq). The client does NOT run these through its reliable
    # channel, so they do NOT advance vcncNet's per-packet diagnostic array (the array that,
    # after ~32 reliable packets, overruns the delivery callback @0x1002042c -> exit-to-HQ CTD).
    return bytes([0x00, 0x00, 0x20, seq & 0xFF, 0x00, 0x00, 0x00, 0x00]) + bytes(payload)

def send_unrel(s, payload, label=''):
    seq = s.nundgram()
    try: sock.sendto(build_unrel(payload, seq), s.addr)
    except OSError: return False
    log('TX/UNREL', f'dseq={seq} type=0x{payload[1]:02x} {label}')
    return True

def send_rel(s, payload, label='', to=5.0):
    seq=s.nrel(); e=s.mke(seq)
    try: sock.sendto(build_rel(payload,seq),s.addr)
    except OSError: s.rme(seq); return False
    bc=payload[0]
    log('TX/RELIABLE',f'seq={seq} bc={bc}(p3={bc*16+1}) type=0x{payload[1]:02x} {label}')
    _rec(s, 'S->C', 'RELTX',
         f'seq={seq} type=0x{payload[1]:02x} bc={bc} {label} pl={binascii.hexlify(bytes(payload[:24])).decode()}')
    ok=e.wait(timeout=to); s.rme(seq)
    log('TX/RELIABLE',f'seq={seq} {"ACKed OK" if ok else "TIMEOUT X"}')
    if not ok:
        _rec(s, 'S->C', 'RELTX', f'seq={seq} TIMEOUT (no ACK in {to}s) type=0x{payload[1]:02x} {label}')
    return ok

def send_reply(s, payload, label='', to=5.0):
    # Post-login server->client reply. When SEND_GAMEPLAY_UNRELIABLE, go UNRELIABLE (pt=0) so it
    # does NOT advance the client's reliable diagnostic array (hard ~32/connection -> CTD). On a
    # LAN this is near-lossless; a dropped reply shows as a stuck spawn, not a crash. Else reliable.
    if SEND_GAMEPLAY_UNRELIABLE:
        return send_unrel(s, payload, label)
    return send_rel(s, payload, label, to)

def get_all_sessions():
    with sl: return [s for s in sids.values() if s.auth_done and not s.closing]

def get_sessions_in_room(room_id):
    """All players currently INSIDE a given game room. The unit of isolation for
    multi-room hosting: chat, roster and (later) position updates are broadcast only
    to the sessions this returns, so nothing leaks between concurrently-hosted rooms."""
    if room_id is None: return []
    with sl:
        return [s for s in sids.values()
                if s.auth_done and not s.closing and s.entered_game
                and s.current_room == room_id]

def assign_player_slot(s, room_id):
    """Allocate a ClientNumber/PlayerIndex for a player entering a room.

    STABILITY (messages38 CTD): the index MUST stay stable for a session across arena
    changes. It was `len(peers)` - pure join order - so when two players switched arenas
    and joined the new one in a different order, their indices SWAPPED (Bigalon 0->1,
    Test2 1->0). But each client still held its ORIGINAL index and each peer's create/62
    still referenced the old one, so the client hit 'Add existing REMOTE_PLAYER Test2
    PlayerIndex=0' (index 0 now claimed by two players) -> the peer object's Client()
    resolved to 0/null -> assertion (o->Number()>=0 && o->Client()!=0) Network.cpp:440 ->
    CTD on BOTH clients on 3D entry. Fix: once a session has an index, KEEP it; only
    recompute if it would actually collide with a peer already in the target room. With
    <=8 players the first-assigned indices never collide, so identities stay put across
    every arena change."""
    peers = [x for x in get_sessions_in_room(room_id) if x is not s]
    taken = {getattr(p, 'client_number', None) for p in peers}
    prev = s.__dict__.get('_assigned_slot')
    if prev is not None and prev not in taken:
        idx = prev                       # keep our stable identity across arena changes
    else:
        idx = 0                          # first free index not already claimed in this room
        while idx in taken:
            idx += 1
    s._assigned_slot = idx
    s.client_number = idx
    s.player_index  = idx
    log('ROOM', f'{s.current_pilot} -> room {room_id} slot ClientNumber={s.client_number} '
                f'PlayerIndex={s.player_index} (peers={len(peers)}, '
                f'{"kept" if prev==idx else "assigned"})')
    return s.client_number, s.player_index

def _maybe_grant_create_entry(s):
    """Auto-join grant for the ARENA CREATOR. Unlike JOIN (client sends 0xc8
    SendEnterToGame -> we reply 201), the CREATE flow sends NO 0xc8 - the client drives
    entry purely off the 1-Hz 0x43 game-connect poll and waits for a JoinToGameAnswer 201
    to clear it (DAT_00c82eb0->0, game active). Without the 201 the poll never stops -> soft
    timeout -> the client exits the game (server.log 14:47:19 create -> ~15s of 0x43 -> exit).
    So on the creator's FIRST 0x43 poll for the room they just created, grant entry exactly
    like the 0xc8 path. Gated by _await_create_entry (set only by the 0xdc create handler)
    so JOIN/lobby polls are untouched, and idempotent via client_granted. Returns True if it
    granted on this call (caller then reports the confirm in GAME mode)."""
    if not getattr(s, '_await_create_entry', False):
        return False
    s._await_create_entry = False
    if s.entered_game or s.client_granted or s.current_room is None:
        return False
    s.entered_game = True
    s.nation = None                                   # "In Menu" until a side is picked
    assign_player_slot(s, s.current_room)
    s.client_granted = True
    send_rel(s, build_join_game_answer_201(s.client_number, s.player_index),
             f'<- JoinToGameAnswer 201 (ClientNumber={s.client_number} '
             f'PlayerIndex={s.player_index} -> GRANT, create auto-join)', to=5.0)
    def _stand_up(_s=s):
        push_player_roster_62(_s, reason='(on create, 0x43 grant)')
        broadcast_player_join_62(_s, reason='(on create, 0x43 grant)')
    threading.Thread(target=_stand_up, daemon=True).start()
    log('CREATE-JOIN', f'201 GRANT on creator 0x43 poll (room {s.current_room}) -> GAME MODE')
    return True

# -- TELEMETRY RELAY (multiplayer flight) ---------------------------------------
# The flying client streams its plane state as UNRELIABLE datagrams (control dword 0,
# pt 0, sz>8) whose payload is the object-update [05 42 00 00 07][tick:2][Number:2 LE]
# [posX:3][posY:3][posZ:3][attitude...][config]. Identity is NOT in the payload - both
# pilots emit object Number 0x0100 by default - so each player is given a GLOBALLY-UNIQUE
# Number at ServerConfirm (next_obj_number). With distinct Numbers we can forward the
# stream VERBATIM to every other flying player in the same room: the receiver sees an
# object Number != its own -> a remote plane. We send on the EXISTING server connection
# (header byte1=0, the same one build_rel uses and the client already accepts), control
# dword 0 (unreliable), per-recipient datagram seq. We normalise to the prefix-less form
# (strip the optional 4-byte [seq][flags] the sz=100 variant carries) so every relayed
# packet is the clean 88-byte 05 42... core.
#
# OPEN QUESTION this is built to answer EMPIRICALLY: does an incoming update for an
# unknown Number lazy-CREATE the remote plane, or must the server first synthesise a
# create (msg 2)? If peers see each other's planes move -> lazy-create works. If not ->
# msg 2 synthesis is the next step. Either outcome is decisive.
RELAY_TELEMETRY = True
# v188 DIAGNOSTIC (reversible): trim discretionary lobby/hangar STATUS echoes to slow the
# reliable-sequence growth on the single VNET connection. The 3rd-respawn CTD is an access
# violation INSIDE vcncNet.dll dispatching a reliable packet at seq ~34 (FA_exe_18372.dmp).
# FA opens exactly ONE connection (login path only; no game-enter second connect), so lobby
# and game share it and the reliable seq climbs ~6-8/cycle. Suppressing the small 0x22/0x39
# echoes (which the client sends repeatedly and does NOT appear to block on) cuts ~3 reliable
# seqs/cycle. KEEP 0x3a (the 113-byte plane list the hangar waits for). If the lobby HANGS
# after a leave, set TRIM_RELIABLE_ECHOES=False - that tells us those echoes ARE awaited and
# the crash is lifecycle- not volume-driven.
TRIM_RELIABLE_ECHOES = True
TRIM_ECHO_SUBS = {0x22, 0x39}

# -- Exit-to-HQ reliable-budget fix (server-side only; client + game files untouched) ------
# vcncNet advances an internal per-packet diagnostic array once per RELIABLE (pt=1) packet the
# client RECEIVES. After ~32 in a session it overruns the registered packet-delivery callback
# pointer (vcncNet .data 0x1002042c); the next reliable delivery does call [garbage] -> CTD.
# Exit-to-HQ is where it tips over (login + a few cycles ~= 32). UNRELIABLE (pt=0) packets do
# NOT advance that array (proven by stable multi-sortie respawn flight). So exit-path control
# messages (0xDA re-attach, exit 0x3a hangar list) go UNRELIABLE with resend-on-loss: continued
# 0x43 poll => re-attach didn't land => resend; empty hangar => client re-requests 0x3a => re-echo.
# On a LAN this is effectively lossless and keeps the reliable seq from climbing. False = revert.
SEND_EXIT_UNRELIABLE = False
# Round 2: extend the unreliable treatment to the per-spawn-cycle reliable sends (StartPlace
# GRANT, ServerConfirm, generic echo) so the reliable seq PLATEAUS after login instead of
# climbing ~4/cycle toward the ~32 limit. Single small packets; on a LAN unreliable delivery is
# near-lossless. If a reply is ever dropped the symptom is a stuck spawn (NOT a CTD), and we add
# progress-based resend then. False reverts this layer to reliable.
SEND_GAMEPLAY_UNRELIABLE = False

# --- Flight recorder ----------------------------------------------------------------------
# The reliable-channel stall (client freezes mid-flight, reliable RX goes silent while
# unreliable telemetry coasts on stale data) leaves no client-side log - FA only opens a new
# messagesNN.log per launch, and the hang prevents the world-entry lines from flushing. So the
# server is the only witness. This recorder keeps a small per-session ring of the most recent
# reliable messages (both directions) plus the tail of unreliable telemetry, and dumps it to a
# dedicated file the instant STALL-WATCH fires - turning every future freeze into hard data
# (exact last reliable msg each way, and the telemetry state at the moment of the stall).
FLIGHT_RECORDER   = True     # master switch (also toggleable live via `rec` console command)
FLIGHT_REC_RELMAX = 40       # reliable msgs (each direction) kept per session
FLIGHT_REC_UNRMAX = 24       # trailing unreliable telemetry packets kept per session
FLIGHT_REC_DIR    = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs', 'flightrec')

def _rec_decode_telem(data):
    """Decode the useful trend fields from an unreliable telemetry datagram for the flight
    recorder: the object-update tick (a smoothly advancing counter) and Number (object id).
    Returns a short 'tick=.. Number=..' string, or '' if this isn't a 0x42 object update.
    Never raises. Cheap - only runs on the small trailing ring, not every packet path."""
    try:
        core = data.find(b'\x05\x42\x00\x00\x07')   # object-update marker (handles sz=96 and sz=100)
        if core < 0 or core + 9 > len(data):
            return ''
        tick = int.from_bytes(data[core+5:core+7], 'little')
        num  = int.from_bytes(data[core+7:core+9], 'little')
        return f'tick={tick} Number={num}'
    except Exception:
        return ''

def _rec(s, direction, kind, detail):
    """Append one event to a session's flight-recorder ring. direction: 'C->S' or 'S->C'.
    kind: short tag (RELRX/RELTX/UNREL/EVENT). detail: compact human string. Never raises."""
    if not FLIGHT_RECORDER:
        return
    try:
        buf = getattr(s, '_rec_rel', None)
        if buf is None:
            return
        (s._rec_unrel if kind == 'UNREL' else s._rec_rel).append(
            (time.time(), direction, kind, detail))
    except Exception:
        pass

def _rec_dump(s, reason):
    """Flush a session's flight-recorder rings to logs/flightrec/<pilot>_<ts>.log. Merges the
    reliable and unreliable rings in time order. Returns the path written, or None."""
    if not FLIGHT_RECORDER:
        return None
    try:
        rel = list(getattr(s, '_rec_rel', []) or [])
        unr = list(getattr(s, '_rec_unrel', []) or [])
        if not rel and not unr:
            return None
        os.makedirs(FLIGHT_REC_DIR, exist_ok=True)
        pilot = (getattr(s, 'current_pilot', None) or 'unknown')
        safe = re.sub(r'[^A-Za-z0-9_.-]', '_', str(pilot))
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        path = os.path.join(FLIGHT_REC_DIR, f'{safe}_{ts}.log')
        merged = sorted(rel + unr, key=lambda e: e[0])
        t0 = merged[0][0] if merged else time.time()
        with open(path, 'w', encoding='utf-8') as f:
            f.write(f'# Flight recorder dump - {pilot} - {reason}\n')
            f.write(f'# {datetime.now().isoformat()}  rel={len(rel)} unrel={len(unr)}\n')
            f.write(f'# t=seconds since first captured event\n#\n')
            for (t, d, k, det) in merged:
                f.write(f'[{t - t0:+7.3f}] {d:3} {k:6} {det}\n')
        return path
    except Exception as e:
        log('REC', f'dump failed: {e}')
        return None

_TELEM_MARK = b'\x05\x42\x00\x00\x07'
# When relaying, stamp the object tick to the RECIPIENT's own latest conductor tick
# minus this small lead, so the receiver's move loop (FUN_007e4a20 ->
# nMoveCycles=(short)(recvTick-objTick)) sees a small POSITIVE delta = the object is a
# couple cycles behind -> smooth dead-reckon-forward interpolation. 0 already gives a
# small +delta (the recipient's tick is from a few ms ago); a tiny lead adds margin so
# we never cross into the <-12 'future' error window that snapped the plane.
RELAY_TICK_LEAD = 0

# -- msg 2 CREATE-OBJECT (remote plane) --------------------------------------
# Reversed from FA.exe: msg-2 dispatch LAB_007e4e00 + NetPlane ctor @0x4f2850.
# Payload = [1 skip byte] + records.  Plane object record = 41 bytes:
#   [0]      tag = (Type & 0xf) | ((nation & 7) << 4)
#   [1]      plane_type   (PLN_INFO id; FUN_004c46d0 lookup - MUST be valid or CTD)
#   [2]      (unused by ctor)
#   [3]      skin         -> NetPlane+0xb30
#   [4..27]  24B = 6xfloat32 position+orientation -> NetPlane+0xaf0
#   --- trailer @ +28 (13B) ---
#   [28..29] St  (owner ClientNumber, u16)   [30..31] ONumber (u16)   [32..40] 0
# Delivered inside a msg-13 batch (real host: in 13 { 62, 62, 2 }).
SEND_CREATE_OBJECT = True    # emit msg 2 so the remote plane exists (relay then drives it)
PLANE_OBJ_TYPE     = 1       # object Type (HeaderSize 28). If CTD / no plane, try 8.
PLANE_TYPE_ID      = 1       # PLN_INFO plane id - TUNE: must be a plane in the loaded set.
DEFAULT_SKIN       = 0

def build_object_record(st, onumber, nation, plane_type, pos, skin):
    """41-byte PLANE object record (Type 1/8, HeaderSize 28 + 13-byte trailer).
    tag=Type|nation @[0], PLN_INFO id @[1], skin @[3], 6xfloat32 pos/orient @[4:28],
    St (owner ClientNumber u16) @[28], ONumber u16 @[30]."""
    rec = bytearray(41)
    rec[0] = (PLANE_OBJ_TYPE & 0x0f) | ((nation & 7) << 4)
    rec[1] = plane_type & 0xff
    rec[3] = skin & 0xff
    px, py, pz = pos
    struct.pack_into('<6f', rec, 4, px, py, pz, 0.0, 0.0, 0.0)   # position + orientation
    struct.pack_into('<H', rec, 28, st & 0xffff)                 # St (owner ClientNumber)
    struct.pack_into('<H', rec, 30, onumber & 0xffff)            # ONumber
    return bytes(rec)

def build_client_record(st, player_index, name, squadron=0):
    """41-byte CLIENT (owner station) record - Type 0, HeaderSize 35 + 6-byte trailer.
    Layout PROVEN from the client-create parser FUN_004f25b0:
        tag=0 @[0] | Squadron u16 @[1] | name asciiz @[3] |
        St u16 @[35] (the NET::CLIENT<*,512> index - MUST be <512) | PlayerIndex u32 @[37]
    Registers the remote pilot's station so the object record's owner St resolves."""
    rec = bytearray(41)
    rec[0] = 0x00                                                # tag 0 -> client-create path
    struct.pack_into('<H', rec, 1, squadron & 0xffff)           # Squadron
    nb = (name or 'Player').encode('latin1', 'replace')[:31]
    rec[3:3 + len(nb)] = nb                                      # name asciiz (35B header)
    struct.pack_into('<H', rec, 35, st & 0xffff)                # St (client/station number)
    struct.pack_into('<I', rec, 37, player_index & 0xffffffff)  # PlayerIndex
    return bytes(rec)

def build_create_object_2(st, onumber, nation, player_index=0, name='Player',
                          plane_type=None, pos=None, skin=DEFAULT_SKIN, with_client=True):
    """msg 2 CREATE-OBJECT. First spawn = 83-byte [0x02]+client(41)+object(41) (the real
    'in 2'83'): registers the owner NET::CLIENT station THEN the plane bound to it.
    Respawn (with_client=False) = 42-byte [0x02]+object(41) ('in 2'42'). The 0x02 msg-id
    IS the handler's skip byte - NO extra byte (an extra 0 -> tag 0 -> client-create path
    -> bounds-crash; that was the v187 first-attempt CTD on Test1)."""
    pt = PLANE_TYPE_ID if plane_type is None else plane_type
    obj = build_object_record(st, onumber, nation, pt, pos or (0.0, 0.0, 0.0), skin)
    body = bytes([0x02])
    if with_client:
        body += build_client_record(st, player_index, name)
    body += obj
    return build_msg13(body)

def send_create_object_for(src, dst, with_client=True):
    """Tell dst to spawn a NetPlane bound to src's object Number, so src's relayed
    telemetry (same Number) has a 3D object to drive. First create per peer sends the
    full client+object form (registers src's station on dst); re-creates after a respawn
    are object-only (the station persists). reliable (msg 13)."""
    if src.my_obj_number is None:
        return False
    if not with_client:
        # OBJECT-ONLY re-create (airfield change / re-entry): dst may STILL hold this
        # object number. The client ASSERTs !Objects[N] on create (Network.cpp:391) ->
        # creating over a live object is a hard CTD (messages42: dup ONumber=257). Send a
        # bare type-3 OBJECT delete FIRST (same thread -> ordered before the create) so the
        # create lands on an empty slot; if the object was already gone, the delete is a
        # harmless no-op. client_number=None -> the NET::CLIENT station is left intact.
        _predel = build_delete_object_3(onumber=src.my_obj_number, client_number=None)
        send_rel(dst, _predel,
                 f'<- pre-delete obj 0x{src.my_obj_number:04x} on {dst.current_pilot} (re-create resync)',
                 to=3.0)
    pkt = build_create_object_2(st=src.client_number, onumber=src.my_obj_number,
                                nation=(src.nation or 0),
                                player_index=src.player_index,
                                name=(src.current_pilot or 'Player'),
                                plane_type=getattr(src, 'plane_type', PLANE_TYPE_ID),
                                with_client=with_client)
    _form = 'client+object' if with_client else 'object-only'
    send_rel(dst, pkt, f'<- CreateObject 2 ({_form}: {src.current_pilot} St={src.client_number} '
                       f'PI={src.player_index} ONumber={src.my_obj_number} -> {dst.current_pilot})', to=3.0)
    log('CREATE2', f'create-object({_form}) {src.current_pilot} St={src.client_number} '
                   f'ONumber=0x{src.my_obj_number:04x} plane={getattr(src, "plane_type", PLANE_TYPE_ID)} -> {dst.current_pilot}')
    return True

def build_delete_object_3(onumber=None, client_number=None, x=0.0, z=0.0):
    """In-game msg type 3 (object/client DELETE) - handler FUN_007e3bb0 @ 0x7e3bb0.
    Drops the rendered NetPlane from the in-game OBJECT table (ARR<NET::OBJECT*,2048>
    @ worldobj+0x203). Lobby msg-63 REMOVE only clears the roster/REMOTE_PLAYER, NOT
    the in-world object - this is the only thing that removes the 3D plane on peers.
    Wire layout (decompiled):
      [0]   u8  = 3
      [1:5] f32 = X ref-coord  (0.0 -> ABS<thresh -> NO death effect = silent removal)
      [5:9] f32 = Z ref-coord  (0.0)
      [9:]  u16 LE entries, looped until len-9 consumed (2 bytes each):
              val & 0x8000 == 0 -> delete OBJECT number = val        (index < 2048)
              val & 0x8000 != 0 -> delete CLIENT number = val&0x7fff (index < 512),
                                   cascades to all that client's objects.
    Delete the object FIRST, then the client, so the client-delete finds no objects
    (avoids the 'client have objects: maybe crash' branch). Wrapped in the msg-13 batch
    container + byte-exact framing, exactly like create_object_2 (type 2)."""
    body = bytearray([0x03])
    body += struct.pack('<ff', x, z)
    if onumber is not None:
        body += struct.pack('<H', onumber & 0x7fff)                    # delete OBJECT (top bit clear)
    if client_number is not None:
        body += struct.pack('<H', (client_number & 0x7fff) | 0x8000)   # delete CLIENT (cascade)
    return build_msg13(bytes(body))

def build_scored_delete_object_3(onumber, x=0.0, z=0.0):
    """Type-3 delete carrying a SCORED-kill tail so the recipient (the KILLER) runs the
    NET::OBJECT ExitData path and credits the kill on its own scoreboard.
    RE (this is the whole reason the killer never scored before):
      * FUN_007e3bb0 (type-3 handler) calls an object's delete method (vtable+0x10) ONLY
        when the entry has >2 bytes after the id (uVar4>2). Our bare delete is exactly
        [id:2] -> method skipped -> plane removed, no score.
      * vtable+0x10 = FUN_004f8f20 'ExitDataArrive'. It reads exitByte@+2 = (MEC<<4)|EEC.
        EEC (low nibble) sets the entry size via its return: EEC=3 -> returns 0xc -> 12-byte
        entry. MEC (high nibble)=5 -> the kill-score branch (FUN_00478640), gated on
        vtable+0xc==0 (true for a REMOTE object = the victim on the killer's screen), so
        it credits THIS client from its own local damage list. The victim's real exit
        byte was 0x53 = MEC 5 | EEC 3 - exactly that combo.
      * Entry = [id:2][0x53][9 bytes] = 12B; the 9 tail bytes aren't read on the MEC=5
        path (credit is local), so they're zero filler to reach 12B.
    Body = [03][X:f32=0][Z:f32=0][id:2][0x53][00*9] = 21B (client logs 'in 3'21'). X/Z=0
    keeps it a silent removal (no death-effect call), same as the bare delete."""
    body  = bytearray([0x03])
    body += struct.pack('<ff', x, z)
    body += struct.pack('<H', onumber & 0x7fff)   # object id, top bit clear
    body += bytes([0x53])                          # exit byte: MEC=5 (score) | EEC=3 (12B entry)
    body += bytes(9)                               # filler -> entry = 12B (unused on MEC=5 path)
    return build_msg13(bytes(body))

# -- Combat scoring constants ----------------------------------------
KILL_SCORE_POINTS   = 100    # flat points for an air kill (global scoring); tune to taste
SEND_SCORED_DELETE_TO_KILLER = True   # send the killer a score-tail delete so the kill
                                      #   registers in-game; toggle off for bare deletes.
KILL_CREDIT_WINDOW  = 30.0   # s: credit the most-recent OTHER shooter within this window

def score_on_death(victim, death_payload):
    """Persist a respawn-death into the DB (accumulating, global scoring).

    The 14-byte 'shot-down' death form (wire sz=18) is a SCORED kill; the short
    8-byte crash/exit form is not. FA does NOT put the killer on the wire - the
    death packet carries 0xFFFFFFFF (the damaged plane finished on the ground) and
    the victim never transmits the killer it computed locally (FUN_00428380 stores
    it only in its own plane). So the server attributes the kill to the most-recent
    OTHER pilot in the room who relayed a DAMAGE28 (msg 28) within KILL_CREDIT_WINDOW:
    exact for a 1v1 duel, a good approximation for N-player (proper msg-28 target
    parsing is a future refinement)."""
    if len(death_payload) < 14:
        return                                  # short crash/exit form - not a scored kill
    now = time.time(); killer = None; best = 0.0
    for p in get_sessions_in_room(victim.current_room):
        if p is victim:
            continue
        t = getattr(p, 'last_fired_at', 0.0)
        if t and (now - t) <= KILL_CREDIT_WINDOW and t > best:
            best = t; killer = p
    victim.k_deaths = getattr(victim, 'k_deaths', 0) + 1
    if killer is not None:
        killer.k_kills = getattr(killer, 'k_kills', 0) + 1
        killer.k_score = getattr(killer, 'k_score', 0) + KILL_SCORE_POINTS
        db_credit_kill(killer.current_pilot, victim.current_pilot, KILL_SCORE_POINTS)
        ks = db_get_pilot_stats(killer.current_pilot) or (0, 0, 0)
        vs = db_get_pilot_stats(victim.current_pilot) or (0, 0, 0)
        log('KILL', f'{killer.current_pilot} destroyed {victim.current_pilot} '
                    f'(+{KILL_SCORE_POINTS}) | {killer.current_pilot}: '
                    f'score={ks[0]} kills={ks[1]} deaths={ks[2]} | '
                    f'{victim.current_pilot}: score={vs[0]} kills={vs[1]} deaths={vs[2]}')
    else:
        db_credit_kill(None, victim.current_pilot, 0)   # death with no creditable shooter
        vs = db_get_pilot_stats(victim.current_pilot) or (0, 0, 0)
        log('KILL', f'{victim.current_pilot} died (no creditable shooter) | '
                    f'{victim.current_pilot}: score={vs[0]} kills={vs[1]} deaths={vs[2]}')
    return killer   # credited shooter (or None) -> caller sends it the SCORED delete

def broadcast_object_delete_3(s, reason='', clear_peer_created=True,
                              followup_pkt=None, followup_label='', killer=None):
    """Remove s's NetPlane (object + client station) from every peer in the room.

    clear_peer_created: True for exit-to-HQ (we wiped our whole world, so peers must
    re-create themselves on us when we return); False for an in-place death+respawn
    (we KEEP the peers' objects, so forcing them to re-create would duplicate a live
    object on the peer).

    followup_pkt: optional reliable packet (the msg-63 REMOVE) sent to each peer
    IMMEDIATELY AFTER the type-3 delete, on the SAME thread, so it always carries a
    higher reliable sequence than the delete. The NetPlane holds a pointer to the
    REMOTE_PLAYER, so the plane must be deleted BEFORE the player is freed or a FLYING
    peer use-after-frees the dangling plane (messages03: flying Test2's world died on
    'Test1 leaving game' before any DelObject)."""
    if s.my_obj_number is None or s.current_room is None:
        return
    # SINGLE entry only (object). A 2nd entry trips the handler's variable-length branch
    # and crashes the PEER ('Length=-1', messages77: 'delete object 257' OK then bogus
    # 'delete object 640'). Object-delete alone removes the rendered NetPlane from world +
    # minimap; msg-63 REMOVE (in handle_leave_arena) clears the roster.
    pkt = build_delete_object_3(onumber=s.my_obj_number, client_number=None)
    # The KILLER alone gets a score-tail delete (credits the kill in-game); everyone else
    # gets the proven bare delete. Isolating it to one recipient bounds any CTD risk.
    spkt = (build_scored_delete_object_3(s.my_obj_number)
            if (killer is not None and SEND_SCORED_DELETE_TO_KILLER) else None)
    _dlabel = (f'<- DeleteObject 3 ({s.current_pilot} ONumber=0x{s.my_obj_number:04x} '
               f'St={s.client_number}) {reason}')
    s.__dict__.pop('_created_peers', None)   # re-entry must re-create us on peers
    for sess in get_sessions_in_room(s.current_room):
        if sess is s:
            continue
        # v190: our exit-to-HQ did 'DelObject -1' - the client wiped EVERY object from its
        # world, including each still-flying peer's plane. The relay only re-creates a peer's
        # object on us when our addr is ABSENT from that peer's _created_peers, so drop it now;
        # else on our re-fly the peer keeps streaming telemetry for an object id we never
        # re-created -> 'Get coord for missing object N' -> world-build hang/CTD (messages98).
        # The relay's 'flying' filter holds these re-creates until our ServerConfirm, so the
        # CREATE lands first, then telemetry. _client_created_peers stays intact: DelObject
        # removes only the OBJECT; the NET::CLIENT station persists -> object-only re-create.
        if clear_peer_created:
            pcp = sess.__dict__.get('_created_peers')
            if pcp is not None:
                pcp.discard(s.addr)
            # ARENA-CHANGE CTD (messages39): the comment below was half-right - for an
            # in-arena DEATH the client keeps the peer's NET::CLIENT station (object-only
            # re-create is correct). But on BACK-TO-LOBBY / arena change (clear_peer_created)
            # the leaving client tears its whole world down - the peer's log shows
            # 'del CLIENT <n>' deleting our station, not just our object. If we leave
            # _client_created_peers intact, our re-entry sends an OBJECT-ONLY create whose
            # owner St references a station the peer already deleted -> o->Client()==0 ->
            # assertion Network.cpp:440 -> CTD on the peer. So on a world-teardown exit we
            # must also forget the station, forcing a full client+object re-create next time.
            ccp = sess.__dict__.get('_client_created_peers')
            if ccp is not None:
                ccp.discard(s.addr)
        # v191: send the type-3 DELETE then the optional followup (msg-63 REMOVE) on ONE
        # thread, in that order, so DELETE always gets the lower reliable seq -> a flying peer
        # tears down the NetPlane BEFORE its REMOTE_PLAYER is freed (no dangling-plane CTD).
        _is_killer = (sess is killer and spkt is not None)
        _delpkt = spkt if _is_killer else pkt
        _dl2 = (_dlabel + ' [SCORED->killer]') if _is_killer else _dlabel
        def _send(_s=sess, _del=_delpkt, _dl=_dl2, _fu=followup_pkt, _fl=followup_label):
            send_rel(_s, _del, _dl, to=3.0)
            if _fu is not None:
                send_rel(_s, _fu, _fl, to=3.0)
        threading.Thread(target=_send, daemon=True).start()
    log('DELETE3', f'{s.current_pilot} ONumber=0x{s.my_obj_number:04x} St={s.client_number} '
                   f'-> peers in room {s.current_room} {reason}')

def relay_telemetry(src, data):
    """Forward src's flying-state datagram to other flying players in the same room."""
    pl = data[8:]
    # The flying-state object-update appspace = [bc][T][00][00][07][tick u16][ONumber u16]...
    # T's LOW nibble is 0x2 (appspace-data channel); T's HIGH nibble is the SIZE
    # (Size = bc*16 + T>>4), so it VARIES with payload length - Test1's update is 86B (T=0x62)
    # while Test2's is 84B (T=0x42). The old check pinned T to 0x42 AND blindly stripped a
    # 4-byte prefix whenever pl[:2]!=0x0542, which MANGLED Test1's prefix-less 0x05 0x62 stream
    # ((00 00 07 ...) != marker -> early return -> Test1 never relayed -> peers couldn't see
    # Test1). Match the SIZE-INDEPENDENT signature instead (cmd==0x0000, opcode 0x07, T low
    # nibble 0x2), scanning offset 0 (no prefix) and 4 (sz=100 [seq][flags] prefix).
    _telem = None
    for _off in (0, 4):
        c = pl[_off:]
        if len(c) >= 9 and c[2] == 0 and c[3] == 0 and c[4] == 0x07 and (c[1] & 0x0f) == 0x02:
            _telem = c
            break
    if _telem is None:
        return                          # not a flying-state object update (e.g. pre-spawn 00c2)
    pl = _telem
    # Record the SENDER's own conductor tick (telemetry[5:7]). We use each player's
    # latest tick to re-stamp packets we relay TO them, so the tick lands on THEIR clock.
    src.last_telem_tick = int.from_bytes(pl[5:7], 'little')
    src.last_telem_time = time.time()
    peers = [x for x in get_sessions_in_room(src.current_room)
             if x is not src and getattr(x, 'flying', False)]
    if not peers:
        return
    for p in peers:
        if SEND_CREATE_OBJECT and src.my_obj_number is not None:
            _cp = src.__dict__.setdefault('_created_peers', set())
            if p.addr not in _cp:
                _cp.add(p.addr)
                # The NET::CLIENT station is created ONCE per peer and PERSISTS across
                # death/respawn/exit-to-HQ (type-3 deletes only the OBJECT, never the
                # client). So only the FIRST create per peer carries the client record;
                # re-creates are object-only - else the peer hits 'Client N already exist'
                # on the duplicate station -> CTD (messages94: in 2'83 after respawn).
                _ccp = src.__dict__.setdefault('_client_created_peers', set())
                _wc = p.addr not in _ccp
                if _wc:
                    _ccp.add(p.addr)
                # Fire the create OFF the RX thread: send_create_object_for blocks up to
                # 3s waiting for the reliable ACK; doing that inline froze the whole
                # server for 3s mid-flight (no beacons/ACKs) -> the peer's keepalive
                # desynced -> FATALLOSTCONNECTION ~30s later (messages54.log).
                threading.Thread(target=send_create_object_for,
                                 args=(src, p), kwargs={'with_client': _wc}, daemon=True).start()
        # Re-stamp the object tick to the RECIPIENT's own latest tick so their move loop
        # sees a small +delta (object slightly behind -> interpolate) instead of the
        # sender's absolute tick, which is skewed ~tens of cycles vs the receiver and
        # tripped the nMoveCycles error that snapped the plane + stalled the sim.
        relayed = bytearray(pl)
        rt = p.last_telem_tick
        if rt is not None:
            struct.pack_into('<H', relayed, 5, (rt - RELAY_TICK_LEAD) & 0xFFFF)
        seq = getattr(p, '_relay_seq', 0) & 0xFF
        p._relay_seq = seq + 1
        pkt = bytes([0x00, 0x00, 0x20, seq, 0x00, 0x00, 0x00, 0x00]) + bytes(relayed)
        try:
            sock.sendto(pkt, p.addr)
        except OSError:
            pass
    # rate-limited so we can see the relay working without flooding the console
    _now = time.time()
    if _now - getattr(src, '_relay_log_ts', 0.0) >= 1.0:
        src._relay_log_ts = _now
        num = int.from_bytes(pl[7:9], 'little')
        rticks = {p.current_pilot: p.last_telem_tick for p in peers}
        log('RELAY', f'{src.current_pilot} obj=0x{num:04x} srcTick={src.last_telem_tick} '
                     f'-> {len(peers)} peer(s) in room {src.current_room} '
                     f'(re-stamp to peer ticks {rticks})')

def _find_room_by_id(room_id):
    for r in db_get_open_rooms():
        if r[0] == room_id:
            return r
    return None

def push_arena_players_213(s, reason=''):
    """Rebuild + broadcast msg 213 for s's room from the live per-session nation state,
    so the Nations list counts and the per-side roster reflect who picked which side.
    Strictly room-scoped: only players inside this room receive it."""
    room_id = s.current_room
    if room_id is None:
        return
    room = _find_room_by_id(room_id)
    if room is None:
        return
    sessions = get_sessions_in_room(room_id)
    counts = [0] * 8
    roster = []
    for sess in sessions:
        nm = sess.current_pilot or 'Player'
        roster.append((nm, sess.nation))
        if sess.nation is not None and 0 <= sess.nation < 8:
            counts[sess.nation] += 1
    pkt = build_arena_players_213(room, counts=counts, names=roster)
    log('TEAM', f'push 213 room={room_id} counts={counts} roster={roster} {reason}')
    for sess in sessions:
        threading.Thread(target=lambda _s=sess: send_rel(_s, pkt,
                         f'<- 213 re-push ({reason})', to=3.0), daemon=True).start()

def handle_team_select(s, nation):
    """Client picked / left a side - msg 68 (0x44) = [0x44][nation:1][?:1]. nation 0..7
    is a side index (US=0, GB=1, SU=2, GE=3, JP=4, NU=...); 0xff / out-of-range = leave.
    Msg 68 itself has NO inbound dispatch handler in FA.exe, so it must NOT be echoed.

    SOLVED (v182 -> v183 -> v185): side membership is driven by msg 63 ChangePlayerCB
    op==1 CHANGE-CAMP (FUN_004fa9c0). v175's msg-58 guess was wrong (msg 58 =
    LobbyRcv list). History of fixes:
      v182 CTD: op was inverted - CAMP shipped as 2, but op==1 is camp and op!=1 is
        the DELETE path; op=2 freed a live player object.
      v183 overcorrection: made the 63 peers-only, citing the `iVar12 != DAT_00bfedb4`
        skip. MISREAD - that skip is in a separate 512-entry in-world object scan;
        the rp lookup (FUN_007fcac0) resolves ANY index including the recipient's
        own, and the op==1 path prints the "<pilot> changed to <nation>" chat line.
        Result: own team change never showed in chat (messages09.log).
      v185/v186: 63 is broadcast to ALL room members INCLUDING the sender. The self
        rp ALWAYS exists by team-select time: the msg 201 grant handler
        (FUN_004f88f0) creates the local player's table entry (camp=-1) at join, so
        the self-63 resolves, sets the camp (chat color), and prints the line. The
        v185 0x66-roster experiment is REVERTED - a 62 self-record deletes that
        live local entry -> use-after-free CTD (messages10.log).
    We still record s.nation for chat/roster scoping and the DB layer."""
    if nation is None or nation == 0xff or nation > 7:
        _changed = s.nation is not None
        s.nation = None
        raw = 0xff if nation is None else nation
        log('TEAM', f'{s.current_pilot} LEFT team (raw=0x{raw:02x}) - msg 63 op=CAMP side=0xff')
        # A camp change is a ROSTER event, not a flight event - broadcast whenever the
        # player is still associated with a room, NOT only while entered_game. Exiting a
        # flight to the team-select/HQ screen runs handle_leave_arena which clears
        # entered_game (but KEEPS current_room), so gating on entered_game silently dropped
        # every team change made AT team-select after the first spawn.
        # DEDUP: only broadcast on an ACTUAL side change. On a desynced re-entered channel
        # the client reliably RE-SENDS the same msg-63 every ~5s (its ACK isn't clearing the
        # send-queue); re-broadcasting each retransmit is a reliable send that further
        # perturbs the channel -> 'Test1 joining/leaving' flood -> the client gives up (~30s)
        # -> 10054. A retransmit of the current side is a no-op (s.nation already matches), so
        # skip the re-broadcast and let the bare ACK land.
        if _changed and s.current_room is not None:
            broadcast_player_change_63(s, None, op=CP_OP_CAMP, reason='(team leave)')
    else:
        _changed = s.nation != nation
        s.nation = nation
        log('TEAM', f'{s.current_pilot} joined side {nation} - msg 63 op=CAMP')
        # Broadcast only on an actual change (see the team-leave branch): the first join
        # after entering broadcasts (s.nation was reset to None at SendEnterToGame), while
        # a reliable retransmit of the same join finds s.nation already set -> no re-send.
        if _changed and s.current_room is not None:
            broadcast_player_change_63(s, nation, op=CP_OP_CAMP, reason='(team join)')

def _find_room_by_gidx(game_idx):
    """Resolve an open room by its 32-bit GameIndex (LE int). Matches the per-room
    UNIQUE index [room_id&0xff][ff][ff][creator[0]] first; falls back to the legacy
    creator-only index [00 ff ff creator[0]] (newest match) for a client still holding
    the pre-unique value - e.g. a creator's own room before it re-reads the 0xd2 list,
    which db_get_open_rooms orders newest-first so the creator's just-made room wins."""
    rooms = db_get_open_rooms()
    for r in rooms:
        if int.from_bytes(_arena_gameindex(r[2] or r[1] or 'Arena', r[0]), 'little') == game_idx:
            return r
    for r in rooms:
        if int.from_bytes(_arena_gameindex(r[2] or r[1] or 'Arena', 0), 'little') == game_idx:
            return r
    return None

def handle_gamedef_request(s, game_idx, via=''):
    """FA msg 212 - on-demand GAME_DEF for the selected arena ("out 212'5").
    Without the reply the arena-select dialog never populates: blank briefing /
    combat text, empty nations list, Join disabled. Shared by the direct
    (type=0x52 sub=0xd4) and compound-wrapped paths - the compound variant used to
    fall into the blanket inner_type==0x52 drop, which is exactly the intermittent
    'empty description + disabled Join' bug."""
    room = _find_room_by_gidx(game_idx)
    if room is not None:
        pkt = build_gamedef_212(room)
        if pkt is not None:
            send_rel(s, pkt, f'<- GAME_DEF 212 on-demand{via} (room {room[0]} gidx=0x{game_idx:08x})', to=5.0)
        else:
            log('POST-AUTH', f'212 request{via} gidx=0x{game_idx:08x}: LZ build failed')
    else:
        log('POST-AUTH', f'212 request{via} gidx=0x{game_idx:08x}: no matching open room - silent')

def handle_213_request(s, game_idx, via=''):
    """FA msg 213 - arena player-info request (counts + roster). If the requester's
    own room, build from live per-session nation state; otherwise DB roster."""
    room = _find_room_by_gidx(game_idx)
    if room is None:
        log('POST-AUTH', f'213 request{via} gidx=0x{game_idx:08x}: no matching room - silent')
        return
    sessions = get_sessions_in_room(room[0])
    if sessions:
        counts = [0] * 8
        roster = []
        for sess in sessions:
            roster.append((sess.current_pilot or 'Player', sess.nation))
            if sess.nation is not None and 0 <= sess.nation < 8:
                counts[sess.nation] += 1
    else:
        try:
            roster = [(p, None) for p, _ in db_get_pilots_in_room(room[0])]
        except Exception:
            roster = []
        counts = [0] * 8
    send_rel(s, build_arena_players_213(room, counts=counts, names=roster),
             f'<- ArenaPlayers 213{via} (room {room[0]} gidx=0x{game_idx:08x}, {len(roster)} players)', to=5.0)

# -- START-PLACE ALLOCATION ----------------------------------------------------
# Each airfield has several start positions (parking/runway spots). The Fly request
# (msg 23) carries N=0xff = 'assign me a spot'; the old code always granted N=0, so two
# players on the SAME airfield stacked on the SAME spot. Track occupancy per (room,af)
# and hand out the lowest free index so they spread out. Freed on airfield change
# (alloc frees the previous slot first), on leave (msg 64), and on disconnect.
SP_MAX = 8                       # distinct slots to hand out per airfield before reusing 0
_sp_occupied = {}                # (room_id, af) -> set(occupied start-place indices)
_sp_lock = threading.Lock()

def _free_start_place(s):
    room = s.__dict__.get('sp_room'); af = s.__dict__.get('sp_af'); n = s.__dict__.get('sp_n')
    if room is None or af is None or n is None:
        return
    with _sp_lock:
        occ = _sp_occupied.get((room, af))
        if occ is not None:
            occ.discard(n)
            if not occ:
                _sp_occupied.pop((room, af), None)
    s.__dict__['sp_room'] = None; s.__dict__['sp_af'] = None; s.__dict__['sp_n'] = None

def _alloc_start_place(s, af, n_req):
    """Pick a free start-place index on (room, af). Frees the session's previous slot
    first (airfield change / respawn). N=0xff = assign lowest free; an explicit N is
    honoured. Returns the granted index."""
    _free_start_place(s)
    room = s.current_room
    with _sp_lock:
        occ = _sp_occupied.setdefault((room, af), set())
        if n_req != 0xff:
            n = n_req
        else:
            n = 0
            while n in occ and n < SP_MAX:
                n += 1
            if n >= SP_MAX:           # more than SP_MAX players on one airfield - reuse slot 0
                n = 0
        occ.add(n)
    s.__dict__['sp_room'] = room; s.__dict__['sp_af'] = af; s.__dict__['sp_n'] = n
    return n

def handle_fly_start_place(s, af, mid, n, via=''):
    """FLY: msg 23 (0x17) StartPlaceList. The Fly button sends one 3-byte record
    [AF][mid][N] with N=0xff ("give me a start place on airfield AF"). The inbound
    handler FUN_004f6320 parses 3-byte records, logs "SP N %i on AF %i", and for the
    waiting player (WaitingForStartPlaceList): N=0xff -> start place -1 -> DENY path
    (vtable+0x54) - which is what our old echo did, leaving the client hanging at the
    last gate before the cockpit; valid N -> set position, vtable+8 = SPAWN into the
    world (FUN_004e9fa0). So we grant: reply msg 23 with the same record, N assigned.

    Wire form is built byte-identical to the echo framing that demonstrably arrived
    as `in 23'4` / one record (4-byte appspace header, type 0x42) - msg 23 must not
    gain pad bytes, since pad zeros would parse as bogus [AF=0][N=0] records."""
    old_af  = s.__dict__.get('sp_af')
    grant_n = _alloc_start_place(s, af, n)      # distinct spot per player on this airfield
    af_changed = (old_af is not None and old_af != af)
    s.obj_confirmed = False; s.flying = False   # new spawn -> re-ServerConfirm on its out 4
    s.entered_game = True                       # re-fly after exit-to-HQ stays IN the arena: re-arm
                                                # the msg-4 spawn gate (handle_leave_arena cleared it),
                                                # else the re-join out-4 is swallowed -> no ServerConfirm
                                                # -> no object created -> players invisible to each other
    s.__dict__.pop('_created_peers', None)      # respawn = new ONumber -> re-create on peers
    # In-world AIRFIELD CHANGE: the client rebuilds its world and DelObject's the peers'
    # planes too (the 'Get coord for missing object N' flood) - so each peer must re-
    # advertise its object to us. Drop our addr from every peer's object-created set; the
    # relay then re-creates their object on us OBJECT-ONLY (the NET::CLIENT station
    # persists, so no 'Client already exist' CTD). Same recovery the exit-to-HQ delete
    # path does via clear_peer_created. In-place respawn keeps the same airfield -> no
    # clear -> no duplicate-create.
    if af_changed:
        for _p in get_sessions_in_room(s.current_room):
            if _p is not s:
                _pcp = _p.__dict__.get('_created_peers')
                if _pcp is not None:
                    _pcp.discard(s.addr)
        log('FLY23', f'airfield change ({old_af}->{af}) -> peers re-create objects on {s.current_pilot}')
    if s.__dict__.pop('_rejoin_pending', False):     # re-join only (first join did this at enter)
        # Re-announce US to PEERS - they removed us via msg-63 REMOVE on our exit, so this is
        # a clean re-add (fixes the phantom/garbage scoreboard row).
        broadcast_player_join_62(s, reason='(re-fly)')
        # AND re-push the PEER roster back to US - but ONLY for peers we don't currently hold.
        # Original code skipped this on the assumption "exit-to-HQ keeps our OWN roster intact",
        # which is FALSE when a PEER also exited to HQ: their object was deleted in our world
        # (Server require delete object N), so on our re-entry we have no REMOTE_PLAYER for them,
        # the world-build waits for a peer that never arrives, and BOTH clients hang at 33%
        # loading (messages40: after both exit-to-HQ + a team change, neither got AddPlayer 62
        # and neither spawned). The old use-after-free warning (messages97) was about re-adding
        # a LIVE remote player; we now guard on _created_peers so we only re-advertise peers
        # whose object we actually dropped - a clean re-create, never a duplicate of a live one.
        _cp = s.__dict__.setdefault('_created_peers', set())
        _missing = [p for p in get_sessions_in_room(s.current_room)
                    if p is not s and p.addr not in _cp]
        if _missing:
            records = [(p.player_index, p.nation, p.current_pilot or 'Player') for p in _missing]
            _pkt = build_msg13(build_add_player_62(records))
            send_rel(s, _pkt, f'<- AddPlayer 62 ({len(records)} peer(s)) (re-fly roster rebuild)', to=5.0)
            log('PLAYER62', f're-fly: re-advertised {len(records)} missing peer(s) to '
                            f'{s.current_pilot}: {[p.current_pilot for p in _missing]}')
    pkt = bytes([0x00, 0x42, 0x00, 0x00, 0x17, af & 0xFF, mid & 0xFF, grant_n & 0xFF])
    log('FLY23', f'StartPlace request{via} AF={af} mid={mid} N=0x{n:02x} -> GRANT N={grant_n}')
    threading.Thread(target=lambda: send_reply(s, pkt,
                     f'<- StartPlaceList 23 GRANT (AF={af} N={grant_n})', to=5.0),
                     daemon=True).start()

def handle_leave_arena(s):
    """Client pressed 'back to lobby' - msg 64 (0x40). Msg 64 has NO inbound dispatch
    handler -> must NOT be echoed (echo -> "Unknown Type 64").

    SOLVED (v178) - what the client waits for after the back button:
    The back button fires a UI callback -> FUN_004edf0e -> FUN_004f1b10: full game-globals
    reset + re-arm of the SAME 1-Hz 0x43 connect-poll used at game entry. Data-xrefs on
    the poll timer DAT_00c82eb0 show exactly three poll-stoppers: the 201 join grant
    (FUN_004f88f0), and FUN_004edcf0 - the handler for lobby msg 218 (0xDA), the
    "lobby attach answer" (dispatch slot 0xc82240 -> id (0xc82240-0xc81ed8)/4 = 218).
    FUN_004edcf0 stores session dwords + MyRights (logs "**** MyRights=%i ****"), sets
    DAT_00c82eb0 = 0 (poll STOP) and notifies the lobby UI observers. It's the same
    218'17 every session receives right after login (our reply to 0xde).

    So leaving = re-entering the lobby state machine: clear the in-game state and
    RE-SEND the 0xDA lobby attach answer; the client stops polling and the lobby UI
    takes over (it will then re-request news/arena list itself)."""
    log('LEAVE', f'{s.current_pilot} pressed back-to-lobby (msg 64) - leaving game '
                 f'(room {s.current_room}), clearing in-game state, NOT echoed')
    # v182: tell peers to drop this player's REMOTE_PLAYER object (msg 63 op=REMOVE)
    # BEFORE we clear s.entered_game / s.current_room, so the broadcast still scopes
    # to the room and resolves the player_index. op=0 (CP_OP_REMOVE) -> FUN_004fa9c0
    # remove path (iVar12==0).
    if s.entered_game and s.current_room is not None:
        room_id = s.current_room
        # v191: ORDER MATTERS - the NetPlane holds a pointer to the REMOTE_PLAYER, so the
        # plane (type-3 DELETE) must reach a peer BEFORE the player (msg-63 REMOVE), else a
        # FLYING peer use-after-frees the dangling plane (messages03: a flying Test2 died on
        # 'Test1 leaving game' with no DelObject after it). broadcast_object_delete_3 now
        # sends DELETE then this REMOVE on the same thread (DELETE gets the lower seq). If we
        # never spawned a NetPlane, there's nothing to dangle - just send the REMOVE.
        rem_pkt = build_change_player_63([(s.player_index, s.nation, CP_OP_REMOVE)])
        rem_label = f'<- ChangePlayer 63 REMOVE ({s.current_pilot})'
        if s.my_obj_number is not None:
            broadcast_object_delete_3(s, reason='(back to lobby)',
                                      followup_pkt=rem_pkt, followup_label=rem_label)
            free_obj_number(s.my_obj_number)   # recycle the Number on exit-to-HQ too
        else:
            for sess in get_sessions_in_room(room_id):
                if sess is s:
                    continue
                threading.Thread(target=lambda _s=sess: send_rel(_s, rem_pkt, rem_label, to=3.0),
                                 daemon=True).start()
    s.entered_game = False
    # ARENA-CHANGE CTD (messages39): the leaving client runs 'del CLIENT Me 0' + 'del
    # CLIENT <n>' for EVERY peer - it destroys its whole world, including all peer
    # NET::CLIENT stations. So on re-entry every peer must be re-created client+object,
    # not object-only. Forget both our object-tracking AND station-tracking for all peers
    # (the reverse direction - peers forgetting US - is handled in broadcast_object_delete_3's
    # clear_peer_created block). Without this, our re-entry sends object-only creates whose
    # owner St points at a station the peer deleted -> o->Client()==0 -> CTD Network.cpp:440.
    s.__dict__.pop('_created_peers', None)
    s.__dict__.pop('_client_created_peers', None)
    _free_start_place(s)       # release the airfield start-place slot we held
    s._rejoin_pending = True   # exit-to-HQ tore down our roster + told peers msg-63 REMOVE; the next
                               # StartPlace must re-exchange msg-62 both ways, else the re-join
                               # camp-change (msg-63) hits a player nobody re-added -> phantom
                               # scoreboard row with garbage score (messages92: 'Unknown RemotePlayer(1)')
    s.client_granted = False   # allow a fresh 201 grant on re-entry
    # v189: KEEP s.nation across exit-to-HQ - the player re-flies under the SAME side
    # without re-sending a camp-change, so clearing it made broadcast_player_join_62 re-add
    # them as camp 0 = US (messages97: 'GBR Test2 leaving' -> 'USA Test2 entering').
    # Clear DB room membership too, or the pilot lingers in db_get_pilots_in_room
    # forever (the stale "Test2 in room 39" roster seen across restarts).
    if s.current_pilot:
        try:
            db_room_leave(s.current_pilot)
        except Exception as e:
            log('LEAVE', f'db_room_leave failed: {e}')
    # The poll stopper: 218 (0xDA) lobby attach answer (FUN_004edcf0 -> DAT_00c82eb0=0)
    if SEND_EXIT_UNRELIABLE:
        # UNRELIABLE so the exit consumes no reliable seq. If lost, the client keeps polling
        # 0x43 and we resend it there (resend-on-poll). entered_game is now False, so the
        # resend/echo gates below are armed until the player re-enters a game.
        s._awaiting_reattach = True
        send_unrel(s, build_da_session_safe(),
                   '<- 0xDA lobby re-attach (UNREL, resend-on-0x43-poll) - stops post-leave poll')
    else:
        threading.Thread(target=lambda: send_rel(s, build_da_session_safe(),
                         '<- 0xDA lobby re-attach (218, Size=15 63-safe) - stops post-leave 0x43 poll',
                         to=5.0), daemon=True).start()

# --- Lobby broadcasts ---------------------------------------------------------

def broadcast_system(message, exclude_sess=None):
    bcast = build_chat_broadcast('Server', message)
    for sess in get_all_sessions():
        if sess is exclude_sess: continue
        threading.Thread(target=lambda _s=sess: send_rel(_s, bcast, '<- sys msg', to=3.0),
                         daemon=True).start()

def build_room_echo_pkt(db_id):
    """Build the type=0x92 sub=0xdc room creation echo for a room in the DB.
    Returns the packet bytes, or None if the room is missing/invalid."""
    try:
        _c = sqlite3.connect(DB_PATH)
        row = _c.execute(
            "SELECT game_def_raw, room_slot, creator_pilot FROM rooms WHERE room_id=? AND status='open'",
            (db_id,)).fetchone()
        _c.close()
        if not row or not row[0]:
            return None
        gdef = bytes(row[0])[:740].ljust(740, b'\x00')
        slot = row[1] or 0x23
        cname = (row[2] or '').encode('ascii', 'replace')[:23] + b'\x00'
        cname = cname.ljust(24, b'\x00')
        # inner data after sub=0xdc: [slot][room_id&0xff][0xff][0xff][creator(24B)][GAME_DEF]
        # GameIndex = bytes[2:6] of [0xdc]+inner_data = [room_id&0xff][0xff][0xff][creator[0]]
        # LE. The low byte (was a fixed 0x00) now carries room_id so two rooms whose
        # creators share a first letter no longer collide - matches _arena_gameindex(
        # creator, db_id) used by the 0xd2 list / 212 / join resolution.
        inner_data = bytes([slot, db_id & 0xff, 0xff, 0xff]) + cname + gdef
        return build_typed_pkt(0x92, bytes([0xdc]) + inner_data)
    except Exception as e:
        log('ROOM-ECHO', f'build failed db_id={db_id}: {e}')
        return None

def send_room_echo(sess, db_id, label=None):
    """Send the 0xdc room creation echo for db_id to a specific session."""
    pkt = build_room_echo_pkt(db_id)
    if pkt is None: return False
    lbl = label or f'<- room echo db_id={db_id}'
    threading.Thread(target=lambda: send_rel(sess, pkt, lbl, to=5.0), daemon=True).start()
    return True

def send_all_room_echoes(sess):
    """Send 0xdc echoes for every open room in the DB to a session.
    Called when a client enters the lobby so its arena list populates."""
    rooms = db_get_open_rooms()
    if not rooms:
        log('ROOM-ECHO', f'no open rooms to advertise to session')
        return
    own_id = sess.current_room
    log('ROOM-ECHO', f'advertising {len(rooms)} room(s) to session (own={own_id})')
    for r in rooms:
        db_id, _name, creator, _acct, _t, slot, _gd = r
        tag = ' [OWN]' if db_id == own_id else ''
        send_room_echo(sess, db_id, label=f'<- room echo db_id={db_id} creator="{creator}"{tag}')

def broadcast_room_creation(db_id, exclude_sess=None):
    """Send the 0xdc echo for a newly-created room to every other authenticated
    session, so their arena lists show the new room."""
    pkt = build_room_echo_pkt(db_id)
    if pkt is None:
        log('ROOM-ECHO', f'broadcast skipped (no pkt) db_id={db_id}')
        return
    n = 0
    for sess in get_all_sessions():
        if sess is exclude_sess: continue
        threading.Thread(target=lambda _s=sess: send_rel(_s, pkt, f'<- broadcast new room db_id={db_id}', to=3.0),
                         daemon=True).start()
        n += 1
    log('ROOM-ECHO', f'broadcast room db_id={db_id} -> {n} other session(s)')

def send_active_list(target_sess):
    others = [s.current_pilot for s in get_all_sessions()
              if s.current_pilot and s is not target_sess]
    msg = ('In lobby: ' + ', '.join(others)) if others else 'No other pilots currently in lobby'
    threading.Thread(target=lambda: send_rel(target_sess, build_chat_broadcast('Server', msg),
                                              '<- active list', to=3.0), daemon=True).start()

def broadcast_player_join(pilot_name, exclude_sess=None):
    pkt = build_ui_player_update(pilot_name, is_join=True)
    for sess in get_all_sessions():
        if sess is exclude_sess: continue
        threading.Thread(target=lambda _s=sess: send_rel(_s, pkt, f'<- UI ADD [{pilot_name}]', to=3.0),
                         daemon=True).start()

def broadcast_player_leave(pilot_name, exclude_sess=None):
    pkt = build_ui_player_update(pilot_name, is_join=False)
    for sess in get_all_sessions():
        if sess is exclude_sess: continue
        threading.Thread(target=lambda _s=sess: send_rel(_s, pkt, f'<- UI REMOVE [{pilot_name}]', to=3.0),
                         daemon=True).start()

def send_initial_ui_list(target_sess):
    for sess in get_all_sessions():
        if sess is not target_sess and sess.current_pilot:
            pkt = build_ui_player_update(sess.current_pilot, is_join=True)
            time.sleep(0.05)
            send_rel(target_sess, pkt, f'<- UI INIT ADD [{sess.current_pilot}]', to=3.0)

# --- Connection handler -------------------------------------------------------

def _reap_stale_sessions(acct, new_sess):
    """Reap any prior session bound to the SAME account (a reconnect after a CTD/timeout).
    On Windows the dead client is never detected on sendto (the failure surfaces as a 10054 on
    recvfrom), so without this the old session's heartbeat thread + lobby-roster entry linger
    as a ghost across reconnects. One account == one live connection here, so any OTHER session
    on this account is stale. new_sess is not yet registered in sids at call time, so it is
    never itself reaped; clean each stale one exactly like a graceful leave so the reconnecting
    client starts fresh (no duplicate pilot in the roster, no orphaned start-place / room row)."""
    with sl:
        stale = [x for x in list(sids.values())
                 if x.account == acct and x is not new_sess and not x.closing]
    for x in stale:
        x.closing = True   # stops its heartbeat/relay loops (they gate on not s.closing)
        try:
            if x.current_pilot:
                broadcast_player_leave(x.current_pilot, exclude_sess=x)
                broadcast_system(f'[{x.current_pilot}] has left')
                db_room_leave(x.current_pilot)
            _free_start_place(x)
            free_client_number(x)   # return the global ClientNumber to the pool
        except Exception as _e:
            log('REAP', f'cleanup error: {_e}')
        with sl:
            sadrs.pop(x.addr, None); sids.pop(x.sid, None)
        log('REAP', f'reaped stale session for account="{acct}" (reconnect) - ghost cleared')

def handle_syn(data, addr):
    acct_row = identify_account_from_syn(data)
    cid=data[1:5]; s=S(cid,addr)
    if acct_row:
        acct, pid_hex, f45_hex, ab_hex = acct_row
        s.account=acct; s.auth64=build_auth64(pid_hex, f45_hex, ab_hex, acct)
        _reap_stale_sessions(acct, s)
        s.auth_payload=build_auth_response(s.auth64)
        pilots=db_get_pilots(acct)
        with sl: active = len([x for x in sids.values() if x.auth_done and not x.closing])
        log('SYN',f'Ready: account="{acct}" {len(pilots)} pilot(s) [sid={s.sid}, active_sessions={active}]')
    else: log('SYN','WARNING: unknown account')
    with sl: sids[s.sid]=s; sadrs[addr]=s
    time.sleep(0.015)
    synack,fa_s=build_synack(); sock.sendto(synack,addr); log('TX/SYNACK',f'FA_s=0x{fa_s:08X}')
    time.sleep(0.025)
    sock.sendto(build_beacon(s.nts(),0),addr); log('TX/BEACON','idx=0')
    def sp():
        time.sleep(0.05)
        if not s.closing: sock.sendto(build_data(100,s.nsq()),s.addr); log('TX/SYS','cmd=100')
    threading.Thread(target=sp,daemon=True).start()

def login(s):
    log('LOGIN','== v197 AUTH ==')
    if not s.auth_payload: log('LOGIN','No auth payload'); return
    if not send_rel(s,s.auth_payload,'<- cmd=100 auth',to=8.0): return
    log('LOGIN',f'Auth ACKed T+{s.ela():.3f}s')
    s.auth_done=True
    def _hb():
        errors = 0
        while not s.closing and not s.in_game:
            time.sleep(5)
            if not s.closing:
                try:
                    if s.entered_game:
                        # IN-GAME KEEPALIVE. Once in the world the client stops sending
                        # 12-byte time pings and only streams unreliable out 6, so the
                        # server must drive the link itself. The 4-byte 0xd3 NOP does NOT
                        # reset the VCNC 60s connection-alive timer (messages35: the client
                        # received 11x 0xd3 over 60s and still hit FATALLOSTCONNECTION at
                        # exactly 60s after the last reliable packet = the ServerConfirm).
                        # A type-2 0x80 TIME beacon DOES reset it - early lobby survived a
                        # ~19s no-reliable gap on TIME packets alone - so push one every 5s.
                        sock.sendto(build_beacon(s.nts(), 0), s.addr)
                    else:
                        sock.sendto(bytes([0,0,0,0xd3]), s.addr)   # lobby heartbeat
                    errors = 0
                except OSError:
                    errors += 1
                    if errors >= 3:   # 3 consecutive failures -> client gone
                        log('SESSION', 'Heartbeat failed 3x - closing session')
                        s.closing = True
                        with sl: sadrs.pop(s.addr,None); sids.pop(s.sid,None)
                        break
    threading.Thread(target=_hb,daemon=True).start()
    deadline=time.time()+300.0   # (kept for reference - no longer bounds the loop, v199)
    while not s.closing:
        cmds=[]
        with s._lock: cmds=list(s.post_auth_cmds); s.post_auth_cmds.clear()
        for cmd,pl in cmds: handle_post_auth(s,cmd,pl)
        time.sleep(0.02)

def parse_e4_selection(pl):
    if len(pl) <= 10: return None, None
    sb = pl[10]
    if sb < 0x20:
        name = pl[11:].split(b'\x00')[0].decode('ascii', errors='replace')
        return name, sb
    else:
        name = pl[10:].split(b'\x00')[0].decode('ascii', errors='replace')
        return name, None

def _handle_chat_pl(s, pl):
    sub = pl[4] if len(pl) > 4 else 0
    if sub == 0xcd:
        raw   = pl[5:] if len(pl) > 5 else b''
        parts = raw.split(b'\x00')
        name  = parts[0].decode('ascii', 'replace')
        msg   = parts[1].decode('ascii', 'replace') if len(parts) > 1 else ''
        sender = s.current_pilot or name
    else:
        slot_char = pl[9]  if len(pl) > 9  else 0
        parts     = pl[10:].split(b'\x00') if len(pl) > 10 else [b'', b'']
        rest      = parts[0].decode('ascii', 'replace')
        msg       = parts[1].decode('ascii', 'replace') if len(parts) > 1 else ''
        reconstructed = (chr(slot_char) + rest) if 0x20 <= slot_char <= 0x7e else rest
        sender = s.current_pilot or reconstructed
    log('CHAT', f'[{sender}]: {msg!r}')
    bcast = build_chat_broadcast(sender, msg)
    sessions = get_all_sessions()
    log('CHAT', f'Broadcasting to {len(sessions)} session(s)')
    for sess in sessions:
        threading.Thread(target=lambda _s=sess: send_rel(_s, bcast, f'<- chat [{sender}]', to=3.0),
                         daemon=True).start()

COMPOUND_CMDS = {530, 578, 4610}

def handle_compound(s, outer_cmd, pl):
    if len(pl) < 5: log('COMPOUND', f'cmd={outer_cmd} too short'); return
    inner = bytes(pl[4:])
    if len(inner) < 5: log('COMPOUND', f'cmd={outer_cmd} inner too short'); return

    inner_type = inner[1]; inner_cmd = (inner[2] << 8) | inner[3]; inner_sub = inner[4]
    log('COMPOUND', f'cmd={outer_cmd}(0x{outer_cmd:04x}) inner '
        f'type=0x{inner_type:02x} cmd={inner_cmd} sub=0x{inner_sub:02x}')

    if inner_type == 0x22 and inner_sub == 0xe2:
        name_raw = inner[6:] if len(inner) > 6 else b''
        new_name = name_raw.split(b'\x00')[0].decode('ascii', 'replace')
        if new_name and s.account:
            slot = db_next_slot(s.account); db_ensure_pilot(new_name, s.account, slot)
            log('COMPOUND', f'Created "{new_name}" slot={slot}')
        threading.Thread(target=lambda: send_rel(s, inner, '<- compound create echo', to=5.0), daemon=True).start()
        return

    if inner_type == 0x42 and inner_sub == 0xe7:
        old_raw  = inner[8:40]  if len(inner) >= 40 else inner[8:]
        new_raw  = inner[40:72] if len(inner) >= 72 else b''
        old_name = old_raw.split(b'\x00')[0].decode('ascii', 'replace')
        new_name = new_raw.split(b'\x00')[0].decode('ascii', 'replace')
        if old_name and new_name and s.account:
            db_rename_pilot(old_name, new_name, s.account)
            log('COMPOUND', f'Renamed "{old_name}" -> "{new_name}"')
        threading.Thread(target=lambda: send_rel(s, inner, '<- compound rename echo', to=5.0), daemon=True).start()
        return

    if inner_type == 0x42 and inner_sub == 0xe3:
        name_raw = inner[8:] if len(inner) > 8 else b''
        pname    = name_raw.split(b'\x00')[0].decode('ascii', 'replace')
        if pname and s.account: db_delete_pilot(pname, s.account)
        data = bytearray(33); data[0]=0xe3; data[1]=0x00; data[2]=0x00; data[3]=0x00
        nb = (pname.encode() + b'\x00') if pname else b'\x00'
        data[4:4+min(len(nb),29)] = nb[:29]
        resp = build_typed_pkt(0x42, bytes(data), bc=2)
        threading.Thread(target=lambda: send_rel(s, resp, '<- compound delete success', to=5.0), daemon=True).start()
        return

    if inner_type == 0x40 and inner_cmd == 5:
        log('COMPOUND', 'inner vcncExitAppSpace -> exit reply')
        pl2=bytearray(80); pl2[0]=4; pl2[3]=0x64
        if not send_rel(s, bytes(pl2), 'exit appspace reply'):
            s.closing = True
            with sl: sadrs.pop(s.addr,None); sids.pop(s.sid,None)
        return

    if inner_cmd == 2:
        log('COMPOUND', 'inner vcncDisconnect -> disconnect reply')
        pl2=bytearray(80); pl2[0]=4; pl2[3]=0x64
        send_rel(s, bytes(pl2), 'disconnect reply')
        return

    if inner_type == 0x12 and inner_sub == 0xe1:
        pilots = db_get_pilots(s.account) if s.account else []
        resp = build_e1_pilot_list(pilots)
        threading.Thread(target=lambda: send_rel(s, resp, '<- compound pilot list', to=5.0), daemon=True).start()
        return

    if inner_type == 0x62 and inner_sub == 0xe4:
        pname, exslot = parse_e4_selection(inner)
        if pname:
            slot = exslot or db_get_pilot_slot(s.account, pname) or 0
            s.current_pilot = pname; s.current_slot = slot
            log('COMPOUND', f'Pilot selected: "{pname}" slot={slot}')
        threading.Thread(target=lambda: send_rel(s, inner, '<- compound pilot select echo', to=5.0), daemon=True).start()
        return

    if inner_sub == 0xcd or (len(inner) > 8 and inner[8] == 0xcd):
        log('COMPOUND', 'inner chat -> _handle_chat_pl')
        _handle_chat_pl(s, inner)
        return

    # -- IN-ARENA CHAT, compound-wrapped (inner sub=0x14) ----------------------
    # Same msg-20 chat as the direct path, but inside a compound (cmd in
    # COMPOUND_CMDS). inner = pl[4:], so inner[4]=sub=0x14, inner[5]=channel,
    # inner[6:]=text. Reflect with PlayerIndex=0 -> renders as the local pilot.
    if inner_sub == 0x14:
        channel = inner[5] if len(inner) > 5 else 0
        text    = bytes(inner[6:]) if len(inner) > 6 else b''
        log('COMPOUND', f'inner sub=0x14 chat -> reflect ch={channel}')
        reflect_chat_20(s, channel, text)
        return

    # -- TEAM / SIDE SELECT, compound-wrapped (inner sub=0x44) -----------------
    # This is how FA actually sends it in the arena lobby (cmd=530). inner[5]=nation.
    if inner_sub == 0x44:
        nation = inner[5] if len(inner) > 5 else 0xff
        log('COMPOUND', f'inner sub=0x44 team-select -> nation=0x{nation:02x}')
        handle_team_select(s, nation)
        return

    # -- LEAVE ARENA / BACK TO LOBBY, compound-wrapped (inner sub=0x40) ---------
    # msg 64 = the back button. No inbound handler -> must NOT be echoed.
    if inner_sub == 0x40:
        log('COMPOUND', 'inner sub=0x40 -> leave-arena (back to lobby), NOT echoed')
        handle_leave_arena(s)
        return

    # -- FLY / START PLACE, compound-wrapped (inner sub=0x17) -------------------
    # [0x17][AF][mid][N]; reply the grant, never echo (echo = deny).
    if inner_sub == 0x17 and len(inner) >= 8:
        handle_fly_start_place(s, inner[5], inner[6], inner[7], via=' (compound)')
        return

    # -- ROOM CREATION (inner type=0x92 sub=0xdc) ------------------------------
    # Always arrives via compound cmd=18.
    # inner layout (from inner[4:] = data):
    #   data[0]=0xdc (sub), data[1]=room_slot (e.g. 0x23), data[2:5]=flags (0x00 0xff 0xff)
    #   data[5:29] = creator pilot name (24-byte null-padded)
    #   data[29:769] = GAME_DEF (740 bytes, confirmed by FA.exe "GAME_DEF size 740")
    # Echo inner -> FA.exe gets "in 220'777" which shows the room locally.
    # Player count starts at 0 - creator enters via VNET::SendEnterToGame (type=0x1d).
    if inner_sub == 0xdc and len(inner) > 33:  # inner_type varies per session (0x92 or 0xa2)
        data      = inner[4:]
        room_slot = data[1] if len(data) > 1 else 0
        creator_raw = data[5:29].split(b'\x00')[0].decode('ascii', 'replace') if len(data) > 5 else ''
        creator   = s.current_pilot or creator_raw
        # Store the FULL GAME_DEF - the old data[29:769] cap truncated it to 740 and the
        # deserialiser ran off the end (Mix.hpp:539). data[29:] = the whole GAME_DEF the
        # client serialised (the inner's appspace data, minus the 29-byte room header).
        game_def  = bytes(data[29:])
        room_id   = db_create_room(creator, s.account or '', game_def, room_slot)
        # One-room-per-creator enforcement (CLOSE the pilot's other open rooms) - now gated
        # behind PERSIST_ROOMS. With unique per-room GameIndexes a creator can hold several
        # rooms at once, and the original 0xce>bc48 worry is moot (0xce is empty). This SQL
        # was silently closing an earlier same-creator room (FFA when TC was made next).
        if creator and not PERSIST_ROOMS:
            _c = sqlite3.connect(DB_PATH)
            _c.execute("UPDATE rooms SET status='closed' WHERE creator_pilot=? AND status='open' AND room_id!=?",
                       (creator, room_id))
            _c.commit(); _c.close()
        s.current_room = room_id
        s.room_slot    = room_slot
        s._await_create_entry = True   # creator drives entry off the 0x43 poll (no 0xc8); grant 201 on it
        if creator:
            db_room_join(room_id, creator, s.account or '')
        log('COMPOUND', f'ROOM CREATED db_id={room_id} slot=0x{room_slot:02x} '
            f'creator="{creator}" name="{extract_name_from_gamedef(game_def)}" '
            f'inner={len(inner)}b data={len(data)}b GAME_DEF={len(game_def)}b '
            f'ver=0x{(bytes(game_def)[gamedef_start(game_def)] if game_def else 0):02x} '
            f'terrain={extract_terrain_from_gamedef(game_def)} '
            f'({TERRAIN_NAMES.get(extract_terrain_from_gamedef(game_def), "?")}) players=1')
        # Exclude creator: chat arriving before the echo disrupts FA.exe state machine
        broadcast_system(f'[{creator}] created a room', exclude_sess=s)
        threading.Thread(target=lambda: send_rel(s, inner, '<- compound echo room create', to=5.0), daemon=True).start()
        # Broadcast new room to all OTHER sessions so their arena lists update
        threading.Thread(target=lambda: broadcast_room_creation(room_id, exclude_sess=s), daemon=True).start()
        return

    # -- ARENA LIST REQUEST (inner sub=0xd2) ----------------------------------
    # 0xd2 = the Arenas-tab room list (real log: out 210 -> in 210'1110). FA.exe
    # often wraps it in a compound. Respond with open rooms, not an echo.
    if inner_sub == 0xd2:
        active_rooms = db_get_open_rooms()
        log('COMPOUND', f'inner sub=0xd2 -> ArenaList ({len(active_rooms)} rooms)')
        # v164: push GAME_DEF (212) per room first so terrain is cached, then the list.
        threading.Thread(
            target=lambda: send_arenalist_with_gamedefs(
                s, active_rooms, '<- compound ArenaList 0xd2'),
            daemon=True).start()
        return

    # -- ROOM CONFIRM POLL (inner sub=0x43) ------------------------------------
    # When room creation goes via compound cmd=18, FA.exe ALSO wraps ALL 0x43 polls
    # in compound (cmd=12434 or cmd=37424). It never sends a direct sub=0x43 in that
    # case, so we MUST respond here with the same 17-byte room status packet.
    # Apply the same 0.5s rate limit as the direct APPSPACE handler.
    if inner_sub == 0x43:
        now = time.time()
        if now - s.last_43_ts < 0.5:
            log('COMPOUND', 'inner sub=0x43 -> rate-limited')
            return
        s.last_43_ts = now
        _maybe_grant_create_entry(s)   # creator's post-create 0x43 poll -> 201 GRANT (enters game)
        if SEND_EXIT_UNRELIABLE and getattr(s,'_awaiting_reattach',False) and not s.entered_game:
            send_unrel(s, build_da_session_safe(), '<- 0xDA re-attach RESEND (compound 0x43 poll)')
        room_slot = getattr(s, 'room_slot', 0)
        rooms = db_get_open_rooms()
        if rooms and (s.current_room or room_slot):
            rid    = s.current_room or rooms[0][0]
            pcount = db_room_player_count(rid)
            slot   = room_slot or (rid & 0xFF)
            resp_data = bytes([0x43, slot, 0x00, 0x00, 0x00, pcount, 0x01,
                               0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
            mode = 'GAME' if s.entered_game else 'lobby'
            log('COMPOUND', f'inner sub=0x43 -> {mode} confirm slot=0x{slot:02x} db_id={rid} players={pcount}')
            resp = build_appspace_pkt(resp_data)
            threading.Thread(target=lambda: send_rel(s, resp, f'<- compound 0x43 {mode} confirm', to=3.0),
                             daemon=True).start()
        else:
            log('COMPOUND', 'inner sub=0x43 -> no room yet, not responding')
        return

    # Compound-wrapped VNET::SendEnterToGame (inner type=0x82 sub=0xc8 = msg 200).
    # This run proved the Join sends the 200 INSIDE a compound (cmd=0x0212), not as a
    # bare type=0x82 - so it was hitting "echo inner" below, bouncing the 200 back to the
    # client as "in 200'40" -> FA: "NET::MESSAGE with Unknown Type 200". NEVER echo it.
    # Instead resolve the room from the inner GameIndex (inner[5:9]) and enter game mode,
    # exactly like the direct type=0x82 path, so the 0x43 game-connect poll gets answered.
    if inner_type == 0x82 and inner_sub == 0xc8:
        game_idx = int.from_bytes(inner[5:9], 'little') if len(inner) >= 9 else 0
        pname = (inner[12:44].split(b'\x00')[0].decode('ascii', 'replace').strip()
                 if len(inner) >= 13 else '')
        if not s.current_room:
            for r in db_get_open_rooms():
                if int.from_bytes(_arena_gameindex(r[2] or r[1] or 'Arena', r[0]), 'little') == game_idx:
                    s.current_room = r[0]
                    s.room_slot = (r[5] if len(r) > 5 and r[5] else (r[0] & 0xFF))
                    break
        if pname and s.current_room:
            existing = [p for p, _ in db_get_pilots_in_room(s.current_room)]
            if pname not in existing:
                db_room_join(s.current_room, pname, s.account or '')
        s.entered_game = True
        s.entering_gidx = game_idx
        s.nation = None                       # enters "In Menu" until a side is picked
        assign_player_slot(s, s.current_room)
        log('COMPOUND', f'SendEnterToGame (compound) pilot="{pname}" gidx=0x{game_idx:08x} '
                        f'room={s.current_room} -> GAME MODE, NOT echoed')
        # Same entry GRANT as the direct path: reply msg 201 (0xc9) JoinToGameAnswer.
        # GUARD (RE FUN_004f88f0): the JoinToGameAnswer handler asserts ClientID<0 on
        # entry, so a 2nd 201 while already granted crashes the client. Grant once/entry.
        if s.client_granted:
            log('COMPOUND', 'JoinToGameAnswer 201 already granted this entry - suppressing duplicate')
        else:
            s.client_granted = True
            send_rel(s, build_join_game_answer_201(s.client_number, s.player_index),
                     f'<- JoinToGameAnswer 201 (ClientNumber={s.client_number} '
                     f'PlayerIndex={s.player_index} -> GRANT)', to=5.0)
        # -- PLAYER-OBJECT LAYER (v184) -------------------------------------------
        # 62 advertises peers to the newcomer and the newcomer to peers. Both calls
        # SELF-GATE: with no peers in the room they send nothing, so a lone player's
        # entry is byte-identical to the known-good v182 path.
        # msg 96 (ScoreTable) is DEFERRED - v183 sent it here unconditionally and it
        # crashed arena-join (messages08.log): FUN_004f53b0 frees+reallocates the
        # host-side score-table object mid-entry, before the client's world is stood
        # up, wedging it (3s stall -> WinError 10054). A lone player has nothing to
        # score; seed the board later, after full world-load, not during the grant.
        def _stand_up_player_objects(_s=s):
            push_player_roster_62(_s, reason='(on enter, compound)')
            broadcast_player_join_62(_s, reason='(on enter, compound)')
        threading.Thread(target=_stand_up_player_objects, daemon=True).start()
        return

    # -- ARENA-SELECT DATA REQUESTS, compound-wrapped (inner type=0x52) ---------
    # THE ARENA-LIST RELIABILITY BUG: msg 212 (sub=0xd4, GAME_DEF request) and msg 213
    # (sub=0xd5, player-info request) sometimes arrive compound-wrapped instead of
    # direct. The old blanket inner_type==0x52 rule swallowed them -> no GAME_DEF reply
    # -> empty description + disabled Join until the client happened to re-request
    # directly (tab away and back). Answer them here exactly like the direct path.
    # inner layout: inner[4]=sub, inner[5:9]=GameIndex LE.
    if inner_sub == 0xd4:
        gidx = int.from_bytes(inner[5:9], 'little') if len(inner) >= 9 else 0
        log('COMPOUND', f'inner sub=0xd4 GAME_DEF request gidx=0x{gidx:08x}')
        handle_gamedef_request(s, gidx, via=' (compound)')
        return
    if inner_sub == 0xd5:
        gidx = int.from_bytes(inner[5:9], 'little') if len(inner) >= 9 else 0
        log('COMPOUND', f'inner sub=0xd5 ArenaPlayers request gidx=0x{gidx:08x}')
        handle_213_request(s, gidx, via=' (compound)')
        return

    # Compound inner type=0x52 (sub=0xd7/0xd9): squad/team update - do NOT echo
    if inner_type == 0x52:
        log('COMPOUND', f'inner 0x52/0x{inner_sub:02x} (squad/team update) - not echoed')
        return
    # No-echo messages (see direct path NO_ECHO_SUBS): 0x20 = no-handler status; 0x03 =
    # NET::OBJECT delete notify (echo -> bounds-error crash); 0x45 (msg 69) =
    # SCENE_TAG_MESSAGE - spawn-point selection notify. Its inbound handler asserts
    # Length % sizeof(SCENE_TAG_MESSAGE::PACKED_INFO) == 0 (VNet_Rcv.cpp:1400), so
    # echoing the 2-byte select notify crashes the client (messages03.log).
    # 0x4d (msg 77) = PLANE-PRELOAD COUNTS (handler 0x4f4080 -> FUN_0047a6f0 sets the
    # per-type count array). Echoing the client's 0x4d makes the handler parse garbage
    # -> junk counts -> 'Preload existing planes' hits an unloaded type -> index>=0 assert
    # (Pln_Info.cpp:192, messages21 crash). Swallow it -> count array stays null -> preload
    # early-outs cleanly. Client does not block on it.
    if inner_sub in (0x20, 0x03, 0x45, 0x18, 0x53, 0x54, 0x4d):
        log('COMPOUND', f'inner sub=0x{inner_sub:02x} (notify, must not echo) - swallow')
        return
    # msg 31 (0x1f) compound-wrapped: ground-object damage report - consume, NEVER echo
    # (no client-side inbound handler for 31; echo raises 'Unknown Type 31'). v199.
    if inner_sub == 0x1f and getattr(s, 'entered_game', False):
        _handle_ground_damage_31(s, bytes(inner[5:]), via=' (compound)')
        return
    # Echo-by-default (lobby AND in-game) - matches the session that reached flight
    # (messages16). A blanket in-game swallow instead froze the world build at ~97%
    # (messages20), because the client waits for replies to some build/spawn messages.
    # Only the genuine fire-and-forget crashers are suppressed by the no-echo set above.
    log('COMPOUND', f'unknown inner -> echo inner')
    threading.Thread(target=lambda: send_rel(s, inner, '<- compound echo unknown inner', to=5.0), daemon=True).start()


GROUND_HP = {}   # (room_id, static-object idx) -> accumulated damage from msg 31 (v199, PvE part 1)

# --- PvE SCENE DESTROY (msg 36) -------------------------------------------------
# The authoritative destroy/state message the REAL server sent (2009 messages04):
#   out 28 (hit) + out 31 (ground-damage report)  ->  in 36 (SCENE DESTROY/STATE)
#   -> client: 'You have destroyed GER Birchwood'.
# Handler LAB_004f9d90 wire = [0x24] then Nx7-byte records:
#   [sceneIdx u16 LE][camp u8 (0xFF = neutralized/destroyed)][progress f32]
# progress <= 0 flips the scene captured. Delivered via the in-game VNET dispatch
# (FUN_004f18a0), which passes the TRUE length - so we frame with build_ingame_pkt
# (Size == n), exactly like the live 'in 36'8' (1 record).
MSG_SCENE_STATE_36 = 0x24
SCENE_CAMP_NEUTRAL = 0xFF          # camp byte meaning 'neutralized / destroyed'

# Per-terrain scene->owning-camp table. CONFIRMED from the msg-36 handler decompile
# (0x4f9d90): the record's camp byte at +2 selects the client's message path - 0xFF forces
# the GENERIC 'a bridge' text (msg 0xcb/203), while the scene's REAL camp (0..4) takes the
# NAMED path (msg 0x81/129) that prints 'You have destroyed <owner> <SceneName>'. Camps
# captured verbatim from the client's join-time scene table ('c <sceneIdx> <camp> <val> <name>').
# TRN02 (Mediterrain, 60 scenes):
SCENE_CAMP_BY_TERRAIN = {
    2: {0:1, 1:3, 2:2, 3:0, 4:4, 5:1, 6:3, 7:2, 8:0, 9:4, 10:1, 11:3, 12:2, 13:0, 14:4,
        15:1, 16:1, 17:3, 18:3, 19:2, 20:2, 21:0, 22:0, 23:4, 24:4, 25:1, 26:3, 27:2, 28:0,
        29:4, 30:1, 31:1, 32:0, 33:0, 34:2, 35:2, 36:4, 37:4, 38:3, 39:3, 40:4, 41:4, 42:4,
        43:2, 44:2, 45:2, 46:0, 47:0, 48:0, 49:1, 50:1, 51:1, 52:3, 53:3, 54:3, 55:1, 56:3,
        57:4, 58:2, 59:0},
}

def scene_camp(terrain, scene_idx):
    """Owning camp (0..4) for a scene, or SCENE_CAMP_NEUTRAL if unknown. Sending the real
    camp is what makes the client name the target instead of printing 'a bridge'."""
    return SCENE_CAMP_BY_TERRAIN.get(terrain, {}).get(scene_idx, SCENE_CAMP_NEUTRAL)

# Per-scene health, keyed by (room_id, sceneIdx). Seeded lazily to SCENE_DEFAULT_HP on
# first damage. Only consulted when AUTO_SCENE_DESTROY is enabled (see below).
SCENE_HP = {}
SCENE_DEFAULT_HP = 4000            # weapon dmg accumulates fast (a bomb = thousands); tune live
SCENE_MAX_IDX = 65                 # raw scene-instance array is 0..65 on TRN02 (60 named + extras)

# GATE: automatically decrement scene HP from msg 31 ev=0x05 and emit msg 36 on depletion.
# OFF by default. STATUS (msgs23, 02-Jul): the camp-byte fix works (msg 36 now names a real
# nation+building instead of 'a bridge'), BUT auto-destroy still hits the WRONG building -
# there are three distinct index spaces and we don't yet have the translation between them:
#   A weapon-target (msg-31 ev=0x05 obj, 0..95+)  = the building the player shoots
#   B display/valuable (join 'c' table, 0..59)     = the sorted list the player reads
#   C raw scene-instance (msg-36 sceneIdx)          = what destroys, array [0xc87270]
# We fire msg 36 with sceneIdx = weapon-obj (space A), but msg 36 indexes space C, so e.g.
# shooting Front Airfield (A=40) destroys raw building C=40 ('Storage') on the wrong team.
# The A->C map is built at terrain load into runtime arrays ([0xc85038] display list,
# [0xc87270] raw array) and is exactly the table.goi objIdx->sceneIdx data the .q6 route
# targets. Leave OFF until that translation is obtained (per-building calibration or table.goi).
AUTO_SCENE_DESTROY = False
# ^ default OFF; `autopve on` flips it live for experiments. While the A->C translation is
#   missing it will destroy the wrong building, so keep it off for normal play.

def build_scene_destroy_36(records):
    """Build FA msg 36 (0x24) SCENE DESTROY/STATE. `records` = list of
    (scene_idx:int, camp:int, progress:float). Wire: [0x24] + Nx[u16 LE sceneIdx]
    [u8 camp][f32 progress]. Framed with build_ingame_pkt so the client's Size == the
    true byte count (the in-game VNET dispatch passes real length, NOT bc*16+1; the live
    'in 36'8' = 1 record). camp 0xFF = neutralized/destroyed; progress <= 0 = captured."""
    body = bytearray([MSG_SCENE_STATE_36])
    for scene_idx, camp, progress in records:
        body += struct.pack('<HBf', scene_idx & 0xFFFF, camp & 0xFF, float(progress))
    return build_ingame_pkt(bytes(body))

def broadcast_scene_36(room_id, records, reason=''):
    """Send a msg-36 SCENE DESTROY/STATE to every player currently in `room_id`.
    `records` = [(scene_idx, camp, progress), ...]. Reliable (matches the live
    reliable 'in 36'). Returns the number of sessions the packet was sent to."""
    if room_id is None or not records:
        return 0
    pkt = build_scene_destroy_36(records)
    sess = get_sessions_in_room(room_id)
    _desc = ', '.join(f'scene={i} camp=0x{c:02x} prog={p:g}' for i, c, p in records)
    for s in sess:
        threading.Thread(
            target=lambda _s=s: send_rel(_s, pkt, f'<- SCENE_DESTROY 36 [{_desc}] {reason}', to=3.0),
            daemon=True).start()
    log('SCENE36', f'room {room_id}: msg 36 [{_desc}] -> {len(sess)} session(s) {reason}')
    return len(sess)

def _handle_ground_damage_31(s, body, via=''):
    """FA msg 31 (0x1f) - GROUND-OBJECT DAMAGE REPORT, client->server ONLY. The client's
    inbound dispatch slot for 31 (0xc81ed8 + 31*4 = 0xc81f54) is hard-zeroed in
    FUN_004f1240, so 31 must NEVER be echoed or relayed to any client - an inbound 31
    raises 'NET::MESSAGE with Unknown Type 31' (messages17, 01-Jul session).
    Body = N x 6-byte records: [attacker ONumber u16 LE][target static-object idx u8]
    [event u8 (only 0x05 seen)][damage u16 LE]. Observed: strafing bursts dmg 92..1239 on
    objs 129/130 (fuel tanks, Bomber Airfield), one bomb = one msg with two records
    (splash over adjacent objects), player crashing INTO a fuel tank = obj 120 dmg 9976.
    v199: decode, log, accumulate per-object HP in GROUND_HP keyed by (room, obj).
    v200: when AUTO_SCENE_DESTROY is enabled, also drive per-scene HP (SCENE_HP) down and
    emit msg 36 on depletion. GATED OFF until the objidx->sceneIdx mapping is confirmed -
    the raw obj index is used as a PROVISIONAL scene key only inside that gate, never sent
    to a client while the gate is off. Raw hex is logged so a live test can still falsify
    the field layout (2nd interpretation: [00][obj u16][05][dmg])."""
    n = len(body) // 6
    recs = []
    destroyed = []                 # (sceneIdx) that crossed 0 this message (auto path only)
    for i in range(n):
        r = body[i*6:i*6+6]
        atk  = int.from_bytes(r[0:2], 'little')
        obj  = r[2]
        ev   = r[3]
        dmg  = int.from_bytes(r[4:6], 'little')
        key = (s.current_room, obj)
        GROUND_HP[key] = GROUND_HP.get(key, 0) + dmg
        recs.append(f'atk=0x{atk:04x} obj={obj} ev=0x{ev:02x} dmg={dmg} (total={GROUND_HP[key]})')
        # live obj->scene probe: record ev=0x00 reconciliation objects against the armed scene
        probe_observe(s.current_room, obj, ev)
        # weapon-obj correlation: track ev=0x05 real weapon targets
        corr_observe(s.current_room, obj, ev, dmg)
        if AUTO_SCENE_DESTROY and ev == 0x05 and s.current_room is not None and 0 <= obj <= SCENE_MAX_IDX:
            # CONFIRMED (messages21, 02-Jul): the msg-31 ev=0x05 weapon-target `obj` byte IS
            # the msg-36 sceneIdx, identity - single-target anchors obj59->scene59 (Tank
            # Factory) and obj40->scene40 (Front Airfield) both matched the join scene table,
            # and bomb-splash bursts hit the physically-adjacent scenes. ev=0x00 is client
            # reconciliation (echoes our own destroys) and must NOT be counted here.
            scene_idx = obj
            skey = (s.current_room, scene_idx)
            hp = SCENE_HP.get(skey, SCENE_DEFAULT_HP) - dmg
            SCENE_HP[skey] = hp
            if hp <= 0 and skey not in getattr(s, '_scene_destroyed', set()):
                s.__dict__.setdefault('_scene_destroyed', set()).add(skey)
                destroyed.append(scene_idx)
    log('GROUND31', f'{s.current_pilot}{via} {n} rec(s): ' + '; '.join(recs) +
                    f' | raw={body.hex()}' + (f' +tail{len(body)%6}' if len(body)%6 else ''))
    if destroyed:
        _trn = _probe_terrain_for_room(s.current_room)
        broadcast_scene_36(s.current_room,
                           [(sidx, scene_camp(_trn, sidx), 0.0) for sidx in destroyed],
                           reason='(auto from msg 31 ev=0x05)')
        for sidx in destroyed:
            log('AUTOPVE', f'{s.current_pilot} destroyed scene {sidx} camp={scene_camp(_trn, sidx)} '
                          f'(weapon damage crossed threshold)')


# --- PvE OBJ->SCENE LIVE PROBE (no .q6 needed) ------------------------------
# The msg-31 objIdx->msg-36 sceneIdx mapping is captured live using the CLIENT as oracle:
# when the client receives a msg-36 SCENE DESTROY for sceneIdx S, it emits ev=0x00
# msg-31 RECONCILIATION records for the objects belonging to that scene's region
# (observed last session: destroy 46/51 -> client re-reported objs 44-65 with ev=0x00).
# So firing destroy(S) and recording the ev=0x00 objects that come back within a short
# window yields sceneIdx->{objIdx}; inverting gives the objIdx->sceneIdx auto-PvE needs.
# Everything here is inert unless a probe is armed from the console (`probe ...`).
PROBE = {'active': False, 'scene': None, 'room': None, 'until': 0.0,
         'map': {}, 'sweep_thread': None, 'stop': False}
PROBE_LOCK = threading.Lock()
PROBE_WINDOW = 2.5            # seconds to collect ev=0x00 after each destroy
PROBE_MAP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'objscene_map.json')

def _probe_terrain_for_room(room_id):
    """Terrain id for a room, from the rooms table (defaults to DEFAULT_TERRAIN). Used to pick
    the right scene->camp table so msg-36 names the target instead of printing 'a bridge'."""
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT terrain FROM rooms WHERE room_id=?", (room_id,)).fetchone()
        conn.close()
        if row and row[0] is not None:
            return int(row[0])
    except Exception:
        pass
    return DEFAULT_TERRAIN

def probe_arm(room, scene, window=PROBE_WINDOW):
    with PROBE_LOCK:
        PROBE.update(active=True, scene=scene, room=room, until=time.time() + window)

def probe_observe(room, obj, ev):
    """Called for every msg-31 record. Records ev=0x00 objects against the armed scene."""
    if ev != 0x00:
        return
    with PROBE_LOCK:
        if not PROBE['active'] or PROBE['room'] != room:
            return
        if time.time() > PROBE['until']:
            PROBE['active'] = False
            return
        PROBE['map'].setdefault(PROBE['scene'], set()).add(obj)

def probe_save():
    with PROBE_LOCK:
        by_scene = {str(s): sorted(v) for s, v in PROBE['map'].items()}
        inv = {}
        for s, objs in PROBE['map'].items():
            for o in objs:
                inv[str(o)] = s
    try:
        existing = json.load(open(PROBE_MAP_PATH)) if os.path.exists(PROBE_MAP_PATH) else {}
    except Exception:
        existing = {}
    existing.setdefault('by_scene', {}).update(by_scene)
    existing.setdefault('obj_to_scene', {}).update(inv)
    json.dump(existing, open(PROBE_MAP_PATH, 'w'), indent=1, sort_keys=True)
    return len(inv), PROBE_MAP_PATH

def probe_fire(room, scene):
    """Arm the window then fire a real destroy(scene) so the client reconciles."""
    probe_arm(room, scene)
    broadcast_scene_36(room, [(scene, SCENE_CAMP_NEUTRAL, 0.0)], reason=f'(probe scene {scene})')

def probe_sweep(room, lo, hi, gap=3.0):
    """Walk sceneIdx lo..hi, one destroy each with `gap` seconds between so each scene's
    ev=0x00 reconciliation lands inside its own window. Daemon thread; `probe stop` cancels."""
    def _run():
        for sc in range(lo, hi + 1):
            with PROBE_LOCK:
                if PROBE['stop']:
                    break
            probe_fire(room, sc)
            log('PROBE', f'swept scene {sc} (room {room})')
            time.sleep(gap)
        n, path = probe_save()
        log('PROBE', f'sweep done: {n} objIdx->sceneIdx entries saved to {path}')
    with PROBE_LOCK:
        PROBE['stop'] = False
    t = threading.Thread(target=_run, daemon=True)
    PROBE['sweep_thread'] = t
    t.start()


# --- PvE WEAPON-OBJ -> SCENE CORRELATION PROBE -----------------------------
# Auto-PvE needs weapon-target objIdx (msg-31 ev=0x05, e.g. 130) -> msg-36 sceneIdx. The
# destroy-sweep only exercises ev=0x00 reconciliation (scene-space 0..65), never the weapon
# space, so it cannot yield this. This mode captures it by CORRELATION:
#   1. `corr watch`      arm: every ev=0x05 record's obj is tracked with accumulating damage,
#                        so `corr show` reveals which building you're actually hitting.
#   2. strafe ONE building; its obj (e.g. 130) appears under `corr show` with rising dmg.
#   3. `corr find <obj>` server sweeps destroy over candidate scenes; narrows which scene
#                        silences that obj's ev=0x05 stream (noisy - a helper, not proof).
#   4. `corr map <obj> <scene>`  record an EYE-CONFIRMED anchor (you saw it blow up) to
#                        weapon_map.json. This is the source of truth for auto-PvE.
# Inert unless armed. Reuses broadcast_scene_36.
CORR = {'watch': False, 'weapon': {}, 'find_obj': None, 'find_thread': None,
        'stop': False, 'last05': {}}
CORR_LOCK = threading.Lock()
CORR_MAP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'weapon_map.json')

def corr_observe(room, obj, ev, dmg):
    """Called for every msg-31 record. Tracks ev=0x05 weapon targets + last-seen time."""
    if ev != 0x05:
        return
    with CORR_LOCK:
        if not CORR['watch']:
            return
        w = CORR['weapon'].setdefault(obj, {'hits': 0, 'dmg': 0, 'first': time.time()})
        w['hits'] += 1
        w['dmg'] += dmg
        CORR['last05'][obj] = time.time()

def corr_map_save(obj, scene):
    try:
        existing = json.load(open(CORR_MAP_PATH)) if os.path.exists(CORR_MAP_PATH) else {}
    except Exception:
        existing = {}
    existing.setdefault('weapon_obj_to_scene', {})[str(obj)] = scene
    json.dump(existing, open(CORR_MAP_PATH, 'w'), indent=1, sort_keys=True)
    return CORR_MAP_PATH

def corr_find(room, obj, lo=0, hi=59, gap=4.0):
    """Sweep destroy lo..hi; after each, note whether `obj` (recently active via ev=0x05)
    stops producing new ev=0x05 - a candidate for the scene that removed it. Heuristic only;
    confirm by eye and record with `corr map`."""
    def _run():
        with CORR_LOCK:
            active = obj in CORR['last05']
        log('CORR', f'find obj={obj}: sweeping destroy {lo}..{hi} gap={gap}s '
                    f'(obj {"active" if active else "NOT yet active - strafe it during the sweep!"})')
        candidates = []
        for sc in range(lo, hi + 1):
            with CORR_LOCK:
                if CORR['stop']:
                    break
                last_seen = CORR['last05'].get(obj, 0)
            broadcast_scene_36(room, [(sc, SCENE_CAMP_NEUTRAL, 0.0)],
                               reason=f'(corr find obj {obj} scene {sc})')
            time.sleep(gap)
            with CORR_LOCK:
                new_last = CORR['last05'].get(obj, 0)
                silent = (new_last == last_seen)
                recently_active = (last_seen and (time.time() - last_seen) < gap * 3)
            if silent and recently_active:
                candidates.append(sc)
                log('CORR', f'  candidate: obj {obj} went silent after destroy scene {sc}')
        log('CORR', f'find obj={obj} done. candidate scene(s): '
                    f'{candidates or "none - strafe the target continuously during the sweep"}')
    with CORR_LOCK:
        CORR['stop'] = False
    t = threading.Thread(target=_run, daemon=True)
    CORR['find_thread'] = t
    t.start()


def _fire_server_confirm(s, via='', ident=None):
    """Fire ServerConfirm (msg 5) for the current spawn: stamps the global object
    Number onto the client's plane and starts its sim loop (engine/controls). Idempotent
    per spawn via s.obj_confirmed (reset on each StartPlace grant). The trigger is the
    client's out-4 full-state, which arrives DIRECT (msg-id @ pl[4]) on the first spawn
    and FA type-scan DOUBLE-WRAPPED (msg-id @ pl[8]) on a re-spawn (airfield change) -
    both must reach here or the re-spawned plane stays cold (engine won't start)."""
    if not (SERVERCONFIRM_READY and not s.obj_confirmed):
        return
    _isrc = 'from out-4'             # v198: the client's registration ident is IN its out-4
    if ident is None:                #       payload; a server-side counter drifts (parachute
        ident = s.spawn_ident_next   #       advances the client's ident but is never confirmed).
        _isrc = 'counter fallback'   #       Counter kept only as fallback for a too-short out-4.
    number = next_obj_number()       # GLOBALLY-unique u16 so each player's telemetry id differs
    s.my_obj_number = number; s.obj_confirmed = True; s.flying = True
    s._left_world = False            # fresh spawn re-arms the exit/leave guard
    s.spawn_ident_next = ident + 1   # keep fallback counter in lock-step with the client
    log('CONFIRM5', f'out 4 spawn{via} -> ServerConfirm Number={number} ident={ident} ({_isrc})')
    threading.Thread(target=lambda nn=number, ii=ident: send_reply(
        s, build_server_confirm_5(nn, ii),
        f'<- ServerConfirm 5 (Number={nn} ident={ii})', to=5.0), daemon=True).start()
    if ADD_TEST_PLAYER:
        def _inject(_s=s):
            time.sleep(1.0)
            m62 = build_add_player_62([(1, 0, 'Test2', 0)])
            send_rel(_s, build_msg13(m62),
                     '<- msg 13 { 62 AddPlayer Test2 idx=1 camp=0 }', to=5.0)
            log('SIM13', 'injected remote player Test2 via msg 13{62}')
        threading.Thread(target=_inject, daemon=True).start()

def _ingame_own_object_removed(s, tb, stored):
    """Shared handler for a msg-3 (sub 0x03) that removes the player's OWN plane while in the
    arena - a death / crash / crashland (exit-to-HQ too; indistinguishable here). It arrives
    BOTH as a direct tb=0x42/0x52/0x32 message AND wrapped in an outer type=0x06 (the type-scan
    form). A CRASHLAND uses the WRAPPED form, so both call sites must route here or the crashland
    respawn is never re-armed and its out 4 gets no ServerConfirm (Conductor error -> dead engine
    -> CTD). Drops the dead plane on peers, stays in the arena, and re-arms obj_confirmed/flying
    so the NEXT out 4 confirms a fresh object even when the crashland respawn skips its StartPlace.
    Idempotent via _left_world (cleared on the respawn's ServerConfirm)."""
    if (s.entered_game and not getattr(s, '_left_world', False)
            and s.my_obj_number is not None):
        s._left_world = True
        log('POST-AUTH', f'msg-3 delete-notify (tb=0x{tb:02x}) = in-arena plane removal '
                         f'(death/crashland/exit-to-HQ) -> drop dead plane, stay in arena, re-arm confirm')
        _killer = score_on_death(s, stored)   # credit killer + record death in DB (accumulating)
        broadcast_object_delete_3(s, reason='(death)', clear_peer_created=False, killer=_killer)
        free_obj_number(s.my_obj_number)      # recycle this plane's Number for the next spawn
        # Re-arm the spawn-confirm so a crashland respawn (InsertPlayer + out 4 with NO StartPlace)
        # still gets a ServerConfirm. A normal death's StartPlace also resets these - harmless.
        s.obj_confirmed = False; s.flying = False
    else:
        log('POST-AUTH', f'msg-3 delete-notify (tb=0x{tb:02x}) -> swallow, no echo (guarded)')

def handle_post_auth(s, cmd, pl):
    bc=pl[0] if pl else 0; tb=pl[1] if len(pl)>1 else 0
    sub=pl[4] if len(pl)>4 else 0
    log('POST-AUTH',f'cmd={cmd}(0x{cmd:04x}) type=0x{tb:02x} sub=0x{sub:02x} bc={bc}(p3={bc*16+1}) sz={len(pl)}')
    stored=bytes(pl)
    _h4=hx(stored[:4]) if len(stored)>=4 else hx(stored)
    _d4=hx(stored[4:8]) if len(stored)>=8 else (hx(stored[4:]) if len(stored)>4 else '')
    log('RX/REL/PL', f'  [{_h4}|{_d4}] +{hx(stored[8:8+80]) if len(stored)>8 else ""}')

    if cmd in COMPOUND_CMDS:
        handle_compound(s, cmd, pl); return

    if (len(pl) > 8 and pl[8] == 0xcd) or sub == 0xcd:
        _handle_chat_pl(s, pl); return

    # -- IN-ARENA CHAT (msg 20 / 0x14) ------------------------------------------
    # Sent by the client as [0x14][channel:1][text\0]; channel 0=all,1=team,2=squadron.
    # The FA reliable type-scan cycles the OUTER type per message, so the same chat
    # arrives in different wrappers: DIRECT (sub=pl[4]=0x14, e.g. type=0xe2) or a
    # type-scan double-wrap (outer type 0x01..0x12, inner header, sub at pl[8]=0x14).
    # Compound-wrapped chat (cmd in COMPOUND_CMDS) is caught in handle_compound above.
    # We reflect with PlayerIndex=0 (the player from the 201 grant) so the display
    # handler FUN_004f6030 resolves it to "Test1" instead of logging "unknown player".
    if sub == 0x14:                                            # direct
        channel = pl[5] if len(pl) > 5 else 0
        text    = bytes(pl[6:]) if len(pl) > 6 else b''
        reflect_chat_20(s, channel, text); return
    if sub == 0x00 and len(pl) > 10 and pl[8] == 0x14:         # type-scan double-wrap
        channel = pl[9]
        text    = bytes(pl[10:])
        reflect_chat_20(s, channel, text); return

    # -- TEAM / SIDE SELECT (msg 68 / 0x44) -------------------------------------
    # [0x44][nation:1][?:1]; nation 0..7 = side (US=0...), 0xff = leave. No incoming
    # handler in FA.exe -> never echo. Same wrapper variants as chat.
    if sub == 0x44:                                            # direct
        nation = pl[5] if len(pl) > 5 else 0xff
        handle_team_select(s, nation); return
    if sub == 0x00 and len(pl) > 9 and pl[8] == 0x44:          # type-scan double-wrap
        nation = pl[9]
        handle_team_select(s, nation); return

    # -- LEAVE ARENA / BACK TO LOBBY (msg 64 / 0x40) ----------------------------
    # No inbound handler in FA.exe -> never echo (echo -> "Unknown Type 64"). Same
    # wrapper variants as the others.
    if sub == 0x40:                                            # direct
        handle_leave_arena(s); return
    if sub == 0x00 and len(pl) > 8 and pl[8] == 0x40:          # type-scan double-wrap
        handle_leave_arena(s); return

    # -- GROUND-WAR DAMAGE REPORT (msg 31 / 0x1f) - consume + decode, NEVER echo ----
    # Direct form (outer type rotates: 0x72/0xd2/... with sub at pl[4]) and the
    # type-scan double-wrap (sub=0x00, msg-id at pl[8]). Compound form is caught in
    # handle_compound. See _handle_ground_damage_31 for the wire layout + evidence.
    if sub == 0x1f and s.entered_game:
        _handle_ground_damage_31(s, bytes(pl[5:]))
        return
    if sub == 0x00 and len(pl) > 9 and pl[8] == 0x1f and s.entered_game:
        _handle_ground_damage_31(s, bytes(pl[9:]), via=' (scan)')
        return

    # -- NOTIFY MESSAGES, type-scan double-wrapped - must not be echoed ---------
    # 0x03 = NET::OBJECT delete notify (echo -> client-side bounds-error crash),
    # 0x20 = no-handler status (echo -> "Unknown Type 32"). Direct variants are
    # swallowed by NO_ECHO_SUBS below; this catches the wrapped form before the
    # generic echo fallthrough re-sends the whole wrapper.
    if sub == 0x00 and len(pl) > 8 and pl[8] == 0x03:
        # Wrapped NET::OBJECT delete: a CRASHLAND death arrives as outer type=0x06 + inner 0x03,
        # so it MUST run the same in-arena removal path (re-arm the spawn-confirm), not be swallowed
        # - otherwise the crashland respawn's out 4 gets no ServerConfirm and the engine stays dead.
        _ingame_own_object_removed(s, tb, stored)
        return
    if sub == 0x00 and len(pl) > 8 and pl[8] in (0x20, 0x45):
        log('POST-AUTH', f'scan-inner sub=0x{pl[8]:02x} (notify, must not echo) -> swallow')
        return

    # -- FLY / START PLACE (msg 23 / 0x17) --------------------------------------
    # [0x17][AF][mid][N]; N=0xff = request. Reply is the GRANT (see
    # handle_fly_start_place) - echoing the request back denies the spawn.
    if sub == 0x17 and len(pl) >= 8:                           # direct
        handle_fly_start_place(s, pl[5], pl[6], pl[7]); return
    if sub == 0x00 and len(pl) >= 12 and pl[8] == 0x17:        # type-scan double-wrap
        handle_fly_start_place(s, pl[9], pl[10], pl[11], via=' (scan)'); return

    # -- OUT-4 SPAWN STATE, type-scan DOUBLE-WRAPPED (re-spawn / airfield change) --
    # The first spawn's out-4 is DIRECT (msg-id 0x04 @ pl[4], outer type 0x12), caught
    # later in the tb==0x12 block. On a RE-spawn the type-scan rotates the outer type
    # (seen: 0x1e) and double-wraps it: outer hdr | inner appspace hdr [bc][0x12] |
    # 04 01..., so msg-id 0x04 lands at pl[8] and it never enters tb==0x12. Result was
    # ServerConfirm never firing -> re-spawned plane's sim loop never started -> engine
    # stayed cold ('couldn't start engine' after an airfield change). Catch it here,
    # independent of the rotated outer type. out-4 is the client's own state -> never
    # echoed, so swallowing (return) is correct.
    if s.entered_game and len(pl) > 8 and pl[5] == 0x12 and pl[8] == 0x04:
        _ident = struct.unpack_from('<H', pl, 9)[0] if len(pl) >= 11 else None   # v198: client's ident
        _fire_server_confirm(s, via=' (scan)', ident=_ident)
        return

    if cmd == 0:
        if tb == 0x12:
            if sub == 0xe1:
                pilots=db_get_pilots(s.account) if s.account else []
                resp=build_e1_pilot_list(pilots)
                threading.Thread(target=lambda:send_rel(s,resp,'<- pilot list',to=5.0),daemon=True).start(); return
            if sub == 0xde:
                def da_then_echo():
                    da=build_da_session()
                    if not send_rel(s,da,'<- 0xDA',to=5.0): return
                    time.sleep(0.005); send_rel(s,stored,'<- echo 0xde',to=5.0)
                threading.Thread(target=da_then_echo,daemon=True).start(); return
            if sub in (0xce, 0xca, 0xcb):
                if sub == 0xce:
                    active_rooms = db_get_open_rooms()
                    resp = build_ce_room_list(active_rooms)
                    raw_len = len(resp) - 4  # payload after vcncNet header
                    log('CE', f'AppSpaceList: {len(active_rooms)} room(s) -> {raw_len} bytes raw')
                    label = f'<- AppSpaceList ({len(active_rooms)} rooms, {raw_len}B)'
                elif sub == 0xcb:
                    # GameList = THE ARENA LIST (confirmed via FUN_004f03b0).
                    # Respond with open rooms as arena records instead of empty.
                    active_rooms = db_get_open_rooms()
                    resp = build_gamelist(active_rooms)
                    raw_len = len(resp) - 4
                    label = f'<- GameList ({len(active_rooms)} arenas, {raw_len}B, fmt={GAMELIST_FORMAT})'
                else:
                    names = {0xca:'ServerList'}
                    resp = build_empty_room_list(sub)
                    label = f'<- empty {names.get(sub, hex(sub))}'
                threading.Thread(target=lambda:send_rel(s,resp,label,to=5.0),daemon=True).start()
                # NOTE (v151): NO room echo here. List population is done entirely by
                # the 0xcb GameList response above ([0xcb] + per arena [1 byte][name\0],
                # parsed by FUN_004ef8b0). The old send_all_room_echoes() pushed 0x92
                # echoes that drove the client into a room (0x43 polling) instead of
                # leaving it on the Arenas list. Rooms created live by OTHER sessions
                # are still broadcast via the 0xdc create path; steady-state listing is
                # the 0xcb query the client issues when opening the Arenas tab.
                return
            if sub == 0xcd:
                _handle_chat_pl(s, pl); return
            if sub == 0xd2:
                # 0xd2 = THE ARENA LIST request (real log: out 210'1 -> in 210'1110).
                # v164: push each room's GAME_DEF (212) FIRST so the client caches the
                # arena's terrain, then send the list. (Was: list only -> terrain 0 crash.)
                active_rooms = db_get_open_rooms()
                threading.Thread(
                    target=lambda: send_arenalist_with_gamedefs(
                        s, active_rooms, f'<- ArenaList 0xd2 ({len(active_rooms)} rooms)'),
                    daemon=True).start(); return
            # APPSPACE-type outer with inner 0x43 (e.g. [00120000|00120000]+43)
            # type=0x12 is used as the outer type by the retry counter in this case.
            if sub == 0x00 and len(pl) >= 9 and pl[5] == 0x12 and pl[8] == 0xd2 and not s.entered_game:
                log('POST-AUTH','APPSPACE-scan sub=0xd2 -> echo inner')
                threading.Thread(target=lambda: send_rel(s, build_appspace_pkt(bytes([0xd2])),
                                 '<- APPSPACE-scan echo 0xd2', to=3.0), daemon=True).start()
                return
            if sub == 0x00 and len(pl) >= 9 and pl[5] == 0x12 and pl[8] == 0x43:
                now = time.time()
                if now - s.last_43_ts >= 0.5:
                    s.last_43_ts = now
                    _maybe_grant_create_entry(s)   # creator's post-create 0x43 poll -> 201 GRANT
                    if SEND_EXIT_UNRELIABLE and getattr(s,'_awaiting_reattach',False) and not s.entered_game:
                        send_unrel(s, build_da_session_safe(), '<- 0xDA re-attach RESEND (appspace 0x43 poll)')
                    room_slot = getattr(s,'room_slot',0)
                    rooms = db_get_open_rooms()
                    if rooms and (s.current_room or room_slot):
                        rid   = s.current_room or rooms[0][0]
                        pcount= db_room_player_count(rid)
                        slot  = room_slot or (rid & 0xFF)
                        rd = bytes([0x43,slot,0,0,0,pcount,0x01,0,0,0,0,0,0,0,0,0,0])
                        log('POST-AUTH',f'APPSPACE-scan sub=0x43 -> room confirm slot=0x{slot:02x} players={pcount}')
                        resp = build_appspace_pkt(rd)
                        threading.Thread(target=lambda:send_rel(s,resp,'<- APPSPACE-scan 0x43',to=3.0),daemon=True).start()
                    else: log('POST-AUTH','APPSPACE-scan sub=0x43 -> no room yet')
                else: log('POST-AUTH','APPSPACE-scan sub=0x43 -> rate-limited')
                return
            if sub == 0x43:
                # 0x43 poll. In lobby mode this is the room-creation confirm; after
                # VNET::SendEnterToGame (s.entered_game) the client polls it once a second
                # as the game-connect handshake (reliable; the type-scan is its retry). We
                # now ANSWER it in both modes so the client stops retrying and we can drive
                # the game-entry. EXPERIMENT v170: reply with the [0x43][slot][..][players]
                # confirm and observe whether the client advances or wants a scene push next.
                now = time.time()
                if now - s.last_43_ts < 0.5:
                    log('POST-AUTH', 'sub=0x43 -> rate-limited, skipping')
                    return
                s.last_43_ts = now
                _maybe_grant_create_entry(s)   # creator's post-create 0x43 poll -> 201 GRANT
                room_slot = getattr(s, 'room_slot', 0)
                rooms = db_get_open_rooms()
                if rooms and (s.current_room or room_slot):
                    rid    = s.current_room or rooms[0][0]
                    pcount = db_room_player_count(rid)
                    slot   = room_slot or (rid & 0xFF)
                    # data[6]=0x01 (lobby flag in creation); keep it for the first game-mode
                    # test - if the client rejects it we'll vary this byte / the layout.
                    resp_data = bytes([0x43, slot, 0x00, 0x00, 0x00, pcount, 0x01,
                                       0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
                    mode = 'GAME' if s.entered_game else 'lobby'
                    log('POST-AUTH', f'sub=0x43 {mode} confirm -> slot=0x{slot:02x} '
                        f'db_id={rid} players={pcount}')
                    resp = build_appspace_pkt(resp_data)
                    threading.Thread(target=lambda:send_rel(s,resp,f'<- 0x43 {mode} confirm',to=3.0),daemon=True).start()
                else:
                    log('POST-AUTH', 'sub=0x43 -> no room, not responding (avoids null crash)')
                return
            if sub == 0x60 and s.entered_game:
                # Bare 0x60 = client REQUESTS the SCORE_TABLE (msg 96). Sent right
                # after the FLY 23 StartPlace grant (messages09.log 06:51:00.782).
                # v184 left it unanswered -> client stalled in the 0x43 poll loop, the
                # launch timer never started, CTD after ~20s. THIS is the correct,
                # solicited send point for 96 - the v183 crash was sending it
                # UNSOLICITED during entry, before the client's world existed.
                log('SCORE96', 'bare 0x60 = ScoreTable request -> answering msg 96 (small populated defs)')
                resp = build_score_table_96(object_groups=SCORE_DEFS_DEFAULT)   # 0..31 type slots,
                #   points in `extra` (= score-def+0xc); ~321B so it fits a single reliable packet.
                threading.Thread(target=lambda: send_rel(s, resp,
                                 '<- ScoreTable 96 (on request)', to=5.0), daemon=True).start()
                return
            if sub == 0x66 and s.entered_game:
                # Bare 0x66 (msg 102): function unknown (no inbound handler slot for
                # 102; the client emits it right after team select). v185 answered it
                # with a 62 roster INCLUDING the requester - FATAL (messages10.log):
                # the msg 201 handler (FUN_004f88f0) already creates the LOCAL
                # player's entry in the player table (FUN_004f3230 + insert, camp=-1),
                # and a 62 record for an existing index DELETES + re-adds it - i.e. it
                # freed the live local player while the GamerClient still pointed at
                # it -> use-after-free -> delayed CTD (~1.7s). Unanswered 0x66 is proven
                # harmless (messages09: client chatted and flew fine). -> swallow.
                log('POST-AUTH', f'bare 0x66 from {s.current_pilot} -> swallow '
                                 f'(unknown fn; harmless unanswered. self-62 barred by invariant)')
                return
            # msg 4 (0x04) = client's FULL object state at spawn - it arrives as type=0x12
            # sub=0x04, so it MUST be caught HERE, before this block's catch-all return.
            # (messages33: with the check placed AFTER the tb==0x12 block the catch-all
            # below swallowed msg 4 and ServerConfirm never fired -> same ~50s freeze.) The
            # first msg 4 after a StartPlace is the ServerConfirm (msg 5) trigger - the gate
            # that stamps the global Number onto the client's plane and starts the sim loop.
            # msg 4/6 are the client's OWN state, never echoed.
            if s.entered_game and sub == 0x04:
                _ident = struct.unpack_from('<H', pl, 5)[0] if len(pl) >= 7 else None   # v198: client's ident
                # v201: PLANE TYPE. The client's out-4 spawn carries its selected plane's
                # index at payload byte[8] (the ordinal into the nation's plane list -
                # F4F-3=0, P-39D=1, P-40C=2, ...). CONFIRMED from a 2-player capture where
                # AC2E_Bigalon flew P-40C(idx2) on spawn-ident 0 and byte[8]=0x02, while
                # Test2 flew F4F-3(idx0) with byte[8]=0x00 (ruling out the earlier
                # ident/plane confound). Store it so send_create_object_for gives peers the
                # RIGHT aircraft instead of the hardcoded P-39D.
                if len(pl) >= 9:
                    s.plane_type = pl[8]
                    log('PLANE', f'{s.current_pilot} selected plane index {pl[8]} (out-4 byte[8])')
                _fire_server_confirm(s, ident=_ident)   # DIRECT out-4; double-wrapped variant caught earlier
                return
            return

        # In-game flight telemetry (msg 83=0x53, 84=0x54, 24=0x18, plus 6=0x06 position
        # stream) arrives wrapped in various outer types (0x22, 0x42, 0x82). The per-type
        # handlers below (0x22, 0x42) echo unknown subs by DEFAULT, so this guard MUST come
        # first: echoing telemetry back makes FA log "NET::MESSAGE with Unknown Type N" and
        # freeze the link (messages22). Lobby unaffected (entered_game False): pilot
        # create/rename/delete (0xe2/0xe3/0xe7) still echo normally.
        if s.entered_game and sub in (0x18, 0x53, 0x54, 0x06):
            log('POST-AUTH', f'in-game telemetry type=0x{tb:02x} sub=0x{sub:02x} -> swallow (no echo)')
            return
        # WRAPPED in-game telemetry: during rapid respawns the client sometimes emits its
        # position/state in the extra-wrapped form `00 00 00 00 00 82 .. <inner@pl[8]>` - pl[1]
        # then reads as sub=0x00, so the direct guard above misses it and it fell through to the
        # generic echo, which bounced it back as a reliable type=0x00. The client's Conductor
        # can't parse a type-0 reliable msg ("Server sent client something it doesn't understand
        # (-102)"), stops ACKing, and the whole reliable channel dies - surfacing as "waiting
        # start place expired" + an empty plane list on the next respawn. Swallow it exactly like
        # the direct telemetry form. Requires pl[5]==0x82 AND an inner telemetry sub at pl[8]
        # (0x18/0x53/0x54/0x06) so it can never collide with the wrapped VNET::SendEnterToGame
        # (pl[5]==0x82, pl[8]==0xc8) handled further below. Same pl[8]-inner convention as the
        # chat/team/leave double-wrap guards above.
        if (s.entered_game and sub == 0x00 and len(pl) > 8
                and pl[5] == 0x82 and pl[8] in (0x18, 0x53, 0x54, 0x06)):
            log('POST-AUTH', f'in-game telemetry (wrapped, inner=0x{pl[8]:02x}) -> swallow (no echo)')
            return

        # In-game COMBAT DAMAGE (msg 28 = sub 0x1c). The shooter's client does its OWN hit
        # detection and emits the per-bodypart hit records as a RELIABLE message ('out 28' /
        # 'You have hit ...'). It must be RELAYED to the other player(s) so the TARGET takes
        # the damage and can die. The old default ECHOED it back to the shooter, which then
        # re-applied its own damage to its LOCAL copy of the target -> over-killed a remote
        # object it doesn't own -> attacker CTD, while the target took nothing (server.log:
        # every 'sub=0x1c -> echo'; messages09: zero 'in 28'). Object ids are GLOBAL (the
        # target id is identical on every client), so forward the bytes as-is, reliably, to
        # each flying peer; no remap/re-stamp needed.
        if s.entered_game and sub == 0x1c:
            s.last_fired_at = time.time()   # stamp shooter for kill attribution on a peer's death
            peers = [x for x in get_sessions_in_room(s.current_room)
                     if x is not s and getattr(x, 'flying', False)]
            for p in peers:
                threading.Thread(target=lambda _p=p: send_rel(_p, stored,
                                 f'<- DAMAGE 28 relay ({s.current_pilot}->{_p.current_pilot})', to=3.0),
                                 daemon=True).start()
            log('DAMAGE28', f'{s.current_pilot} hit -> relay to {len(peers)} peer(s) '
                            f'in room {s.current_room} ({len(stored)}B)')
            return

        # NET::OBJECT delete-notify (msg 3 / sub=0x03) rides tb=0x42 (del object) or
        # tb=0x52 (del client). The tb==0x42 branch below echoes unknown subs by DEFAULT,
        # so echoing it back = 'Server require delete object' on a bogus id ->
        # ARR<NET::OBJECT*,2048> bounds CTD on the SENDER (messages90). NEVER echo it.
        # It is ALSO the exit-to-HQ signal (this leave sends no msg-64): the first one,
        # while still flying, drives peer plane-removal (type-3) + the 0xDA HQ handoff.
        # _left_world keeps catching the trailing del-client 0x03 after entered_game clears.
        if (s.entered_game or getattr(s, '_left_world', False)) and sub == 0x03:
            # A msg-3 that removes the player's OWN plane WHILE IN THE ARENA is a death
            # (crash / shot / crashland) OR an exit-to-HQ. Routed through the shared helper so the
            # DIRECT (tb=0x42/0x52/0x32) and the type-scan WRAPPED (outer 0x06) forms behave
            # identically - a crashland uses the wrapped form (handled at the scan-inner call site).
            _ingame_own_object_removed(s, tb, stored)
            return

        if tb == 0x22:
            if sub == 0xe2 and s.account:
                name_raw=pl[6:] if len(pl)>6 else b''
                new_name=name_raw.split(b'\x00')[0].decode('ascii',errors='replace')
                if new_name:
                    slot=db_next_slot(s.account); db_ensure_pilot(new_name,s.account,slot)
            threading.Thread(target=lambda:send_rel(s,stored,'<- echo 0xe2',to=5.0),daemon=True).start(); return

        if tb == 0x42:
            if sub == 0xe3:
                name_raw = pl[8:] if len(pl)>8 else b''
                pname = name_raw.split(b'\x00')[0].decode('ascii', 'replace')
                if pname and s.account: db_delete_pilot(pname, s.account)
                data = bytearray(33); data[0]=0xe3
                nb = pname.encode() + b'\x00'
                data[4:4+min(len(nb),29)] = nb[:29]
                resp = build_typed_pkt(0x42, bytes(data), bc=2)
                threading.Thread(target=lambda: send_rel(s, resp, '<- delete success', to=5.0), daemon=True).start(); return
            if sub == 0xe7:
                old_raw = pl[8:40] if len(pl)>=40 else pl[8:]
                new_raw = pl[40:72] if len(pl)>=72 else b''
                old_name = old_raw.split(b'\x00')[0].decode('ascii', 'replace')
                new_name = new_raw.split(b'\x00')[0].decode('ascii', 'replace')
                if old_name and new_name and s.account: db_rename_pilot(old_name, new_name, s.account)
                threading.Thread(target=lambda: send_rel(s, stored, '<- echo rename', to=5.0), daemon=True).start(); return
            threading.Thread(target=lambda: send_rel(s, stored, 'echo type=0x42', to=5.0), daemon=True).start(); return

        if tb == 0x62 and sub == 0xe4:
            pname, explicit_slot = parse_e4_selection(pl)
            if pname:
                slot = explicit_slot or db_get_pilot_slot(s.account, pname) or 0
                s.current_pilot = pname; s.current_slot = slot
                log('POST-AUTH',f'Pilot selected: "{pname}" slot={slot}')
                # NOTE (v151): NO room auto-restore. The real client never auto-joins
                # a room on reconnect - the player lands on the tabbed menu and only
                # sees rooms when they open the Arenas tab (via the 0xcb list). The old
                # restore + 0x92 echo made the client believe it owned/occupied a room
                # and start 0x43 polling, which confounded every list test. The room
                # still exists server-side (db_get_open_rooms) and appears in 0xcb.
                broadcast_system(f'[{pname}] has joined the lobby')
                broadcast_player_join(pname, exclude_sess=s)
                threading.Thread(target=lambda: send_initial_ui_list(s), daemon=True).start()
                threading.Thread(target=lambda: send_active_list(s), daemon=True).start()
            threading.Thread(target=lambda:send_rel(s,stored,'<- echo 0xe4',to=5.0),daemon=True).start()
            return

        if tb == 0x01:
            # Guard: only trigger for real ExitAppSpace notice (len<=5 = no inner data).
            # Type-scan packets also use type=0x01 but have inner data (len=9).
            # Without this guard, type-scan packets kill the session prematurely.
            if len(pl) <= 5:
                log('POST-AUTH','vcncExitAppSpace notice')
                if s.current_pilot:
                    broadcast_player_leave(s.current_pilot, exclude_sess=s)
                    broadcast_system(f'[{s.current_pilot}] has left')
                    db_room_leave(s.current_pilot)
                s.closing=True
                with sl: sadrs.pop(s.addr,None); sids.pop(s.sid,None)
                return
            # else: type-scan packet with inner data - fall through to generic echo

        # type=0x92 sub=0xdc direct path (fallback; normally arrives via compound cmd=18)
        if tb == 0x92 and sub == 0xdc and len(pl) > 33:
            data = pl[4:]
            room_slot = data[1] if len(data) > 1 else 0
            creator_raw = data[5:29].split(b'\x00')[0].decode('ascii','replace') if len(data)>5 else ''
            creator = s.current_pilot or creator_raw
            game_def = bytes(data[29:])   # full GAME_DEF (no 769 truncation)
            room_id = db_create_room(creator, s.account or '', game_def, room_slot)
            s.current_room = room_id; s.room_slot = room_slot
            if creator:
                if not PERSIST_ROOMS:              # one-room-per-creator - gated (see compound path)
                    _c = sqlite3.connect(DB_PATH)  # close stale rooms (direct)
                    _c.execute("UPDATE rooms SET status='closed' WHERE creator_pilot=? AND status='open' AND room_id!=?",
                               (creator, room_id))
                    _c.commit(); _c.close()
                db_room_join(room_id, creator, s.account or '')  # players=1 from first 0x43
            log('POST-AUTH', f'ROOM CREATED (direct) db_id={room_id} slot=0x{room_slot:02x} creator="{creator}" players=1')
            broadcast_system(f'[{creator}] created a room', exclude_sess=s)
            # Echo to creator (existing behavior) + broadcast to all other sessions
            # so their arena lists show the new room.
            threading.Thread(target=lambda:send_rel(s,stored,'<- echo room create',to=5.0),daemon=True).start()
            threading.Thread(target=lambda:broadcast_room_creation(room_id, exclude_sess=s), daemon=True).start()
            return

        # type=0x52: pilot/squad/team update packets (FA.exe -> server only)
        # sub=0xd5 = pilot status (rank, score, faction)
        # sub=0xd7 = team/squad name update (loops if echoed - FA.exe retries indefinitely)
        # sub=0xd9 = related team info (same issue)
        # DO NOT echo: echoing type=0x52 back to FA.exe causes infinite retry loops
        # and fills the squadron page with GAME_DEF garbage when triggered by wrong 0xce data.
        if tb == 0x52:
            if sub == 0xe0:
                # sub=0xe0 = "EnterArena" phase 1 (5 bytes: [0xe0][GameIndex 4B])
                # Sent at type=0x52 just before VNET::SendEnterToGame.
                # GameIndex at pl[5:9] LE.
                if len(pl) >= 9:
                    game_idx = int.from_bytes(pl[5:9], 'little')
                    log('POST-AUTH', f'EnterArena sub=0xe0 GameIndex=0x{game_idx:08x} ({game_idx}) - accepted')
                else:
                    log('POST-AUTH', f'EnterArena sub=0xe0 len={len(pl)} - accepted')
                return
            if sub == 0xd7:
                # sub=0xd7 = FUN_004f0570 "SetArena" (5 bytes: [0xd7][GameIndex 4B])
                # Sets current arena on server. No response needed.
                if len(pl) >= 9:
                    game_idx = int.from_bytes(pl[5:9], 'little')
                    log('POST-AUTH', f'SetArena sub=0xd7 GameIndex=0x{game_idx:08x} - accepted')
                else:
                    log('POST-AUTH', f'SetArena sub=0xd7 len={len(pl)} - accepted')
                return
            if sub == 0xd4:
                # FA message 212 - on-demand GAME_DEF request ("out 212'5"); see
                # handle_gamedef_request. pl[5:9] = GameIndex (LE).
                game_idx = int.from_bytes(pl[5:9], 'little') if len(pl) >= 9 else 0
                handle_gamedef_request(s, game_idx)
                return
            if sub == 0xd5:
                # FA message 213 - arena player-info request; see handle_213_request.
                game_idx = int.from_bytes(pl[5:9], 'little') if len(pl) >= 9 else 0
                handle_213_request(s, game_idx)
                return
            else:
                log('POST-AUTH', f'type=0x52 sub=0x{sub:02x} len={len(pl)} - accepted (not echoed)')
            return

                # VNET::SendEnterToGame - DIRECT FORMAT: bc=2, type=0x82, cmd=0, sub=0xc8=200
        # FA.exe logs: "VNET::SendEnterToGame GameIndex=NNN" + "out 200'40"
        # Pilot name at pl[12:44] (32-byte null-padded, confirmed from capture).
        # DO NOT echo this packet - server echoing type=0x82/sub=0xc8 causes FA.exe
        # to log "NET::MESSAGE with Unknown Type 200" and break the session.
        # After this, stop sending 0x43 responses; FA.exe will exit cleanly via type-scan.
        if tb == 0x82 and sub == 0xc8 and len(pl) >= 44:
            game_idx = int.from_bytes(pl[5:9], 'little') if len(pl) >= 9 else 0
            pname_raw = pl[12:44] if len(pl) >= 44 else pl[12:]
            pname = pname_raw.split(b'\x00')[0].decode('ascii', 'replace').strip()
            # Browse-and-join: current_room isn't set (room was created earlier), so
            # resolve which room is being entered from the GameIndex in the 200 packet.
            if not s.current_room:
                for r in db_get_open_rooms():
                    if int.from_bytes(_arena_gameindex(r[2] or r[1] or 'Arena', r[0]), 'little') == game_idx:
                        s.current_room = r[0]
                        s.room_slot = (r[5] if len(r) > 5 and r[5] else (r[0] & 0xFF))
                        break
            if pname and s.current_room:
                existing = [p for p,_ in db_get_pilots_in_room(s.current_room)]
                if pname not in existing:
                    db_room_join(s.current_room, pname, s.account or '')
                log('POST-AUTH', f'VNET::SendEnterToGame (direct) pilot="{pname}" gidx=0x{game_idx:08x} room={s.current_room}')
            else:
                log('POST-AUTH', f'VNET::SendEnterToGame (direct) pilot="{pname}" gidx=0x{game_idx:08x} (no room)')
            s.entered_game = True
            s.entering_gidx = game_idx
            s.nation = None                   # enters "In Menu" until a side is picked
            assign_player_slot(s, s.current_room)
            log('POST-AUTH', 'GAME MODE - will answer 0x43 game-connect poll (not echoing 200)')
            # Send the real entry GRANT: msg 201 (0xc9) JoinToGameAnswer. ClientNumber and
            # PlayerIndex are the room-scoped slot (both >= 0 -> grant). This stops the
            # 0x43 poll and moves the client into the arena (handler FUN_004f88f0).
            # GUARD (RE FUN_004f88f0): handler asserts ClientID<0 on entry - a 2nd 201
            # while already granted crashes the client. Grant once per entry.
            if s.client_granted:
                log('POST-AUTH', 'JoinToGameAnswer 201 already granted this entry - suppressing duplicate')
            else:
                s.client_granted = True
                send_rel(s, build_join_game_answer_201(s.client_number, s.player_index),
                         f'<- JoinToGameAnswer 201 (ClientNumber={s.client_number} '
                         f'PlayerIndex={s.player_index} -> GRANT)', to=5.0)
            # -- PLAYER-OBJECT LAYER (v184) ---------------------------------------
            # Now that the local player is granted, stand up the remote-player view:
            #   1. msg 62 -> tell the newcomer about every peer already in the room
            #      (builds a REMOTE_PLAYER object for each - handler FUN_004fa5f0).
            #   2. msg 62 -> tell those peers about the newcomer (live join).
            # Both 62 calls self-gate: no peers -> nothing sent, so a lone player's
            # entry is byte-identical to the known-good v182 path.
            # Side/camp (msg 63) is NOT sent here: nation is still None ("In Menu")
            # until the client picks a side, which drives handle_team_select -> 63.
            # msg 96 (ScoreTable) is DEFERRED - v183 sent it unconditionally here and
            # it crashed arena-join (messages08.log): FUN_004f53b0 frees+reallocates
            # the host-side score-table object mid-entry, before the client's world is
            # stood up, wedging it (3s stall -> WinError 10054). Seed the board after
            # full world-load, not during the grant.
            def _stand_up_player_objects(_s=s):
                push_player_roster_62(_s, reason='(on enter)')
                broadcast_player_join_62(_s, reason='(on enter)')
            threading.Thread(target=_stand_up_player_objects, daemon=True).start()
            # Do NOT echo: echoing type=0x82/sub=0xc8 causes FA.exe "Unknown Type 200"
            return

        # -- WRAPPED VNET::SendEnterToGame -----------------------------------------
        # Outer packet: bc=0, type=RETRY_COUNTER, cmd=0, sub=INNER_BC
        # Inner at pl[4:]: [inner_bc=0x02][inner_type=0x82][0x00][0x00][inner_sub=0xc8]...
        # BUG HISTORY: was inside sub==0x00 && len<=16 gate -> IMPOSSIBLE to trigger.
        #   pl[4]=inner_bc=0x02 != 0x00   AND   len(pl)=48 > 16.
        # FIX: check here with only pl[5]==0x82 and pl[8]==0xc8, ANY outer sub.
        if len(pl) >= 17 and pl[5] == 0x82 and pl[8] == 0xc8:
            pname_raw = pl[16:48] if len(pl) >= 48 else pl[16:]
            pname = pname_raw.split(b'\x00')[0].decode('ascii', 'replace').strip()
            game_idx = int.from_bytes(pl[9:13], 'little') if len(pl) >= 13 else 0
            if pname and s.current_room:
                existing = [p for p,_ in db_get_pilots_in_room(s.current_room)]
                if pname not in existing:
                    db_room_join(s.current_room, pname, s.account or '')
                log('POST-AUTH', f'VNET::SendEnterToGame (WRAPPED) inner_bc=0x{sub:02x} GameIndex=0x{game_idx:08x} pilot="{pname}" room={s.current_room}')
            else:
                log('POST-AUTH', f'VNET::SendEnterToGame (WRAPPED) inner_bc=0x{sub:02x} GameIndex=0x{game_idx:08x} (no room)')
            s.entered_game = True
            log('POST-AUTH', 'GAME MODE (wrapped VNET) - stopping 0x43, not echoing')
            return

        # -- SCAN-INNER PACKET DETECTION ------------------------------------------
        # FA.exe wraps APPSPACE sub-commands in type-scan outer packets:
        #   outer: bc=0, type=RETRY_COUNTER, cmd=0, sub=0x00
        #   inner at pl[4:]: inner[1]=type, inner[3]=cmd_lo, inner[4]=sub
        # These fire every 1s between compound 0x43 retries (every ~13s).
        if sub == 0x00 and len(pl) >= 9 and len(pl) <= 16:
            inner1 = pl[5] if len(pl) > 5 else 0   # inner type byte
            inner3 = pl[7] if len(pl) > 7 else 0   # inner cmd low byte
            inner4 = pl[8] if len(pl) > 8 else 0   # inner sub

            # Inner type=0x52 (pilot/squad status): accept silently - echoing causes loops
            if inner1 == 0x52:
                log('POST-AUTH', f'scan-inner 0x52/0x{inner4:02x} - accepted silently')
                return

            # Inner sub=0xd2: pre-room signal retry via type-scan -> echo it
            if inner1 == 0x12 and inner4 == 0xd2 and not s.entered_game:
                log('POST-AUTH','scan-inner sub=0xd2 -> echo inner')
                threading.Thread(target=lambda: send_rel(s, build_appspace_pkt(bytes([0xd2])),
                                 '<- scan-inner echo 0xd2', to=3.0), daemon=True).start()
                return

            # (VNET wrapped check moved OUT of this block - was dead code here
            #  because inner bc=0x02 makes outer sub=0x02 != 0x00, AND len=48 > 16)

            # Inner APPSPACE sub=0x43: type-scan room confirm poll
            if inner1 == 0x12 and inner4 == 0x43:
                now = time.time()
                if now - s.last_43_ts >= 0.5:
                    s.last_43_ts = now
                    _maybe_grant_create_entry(s)   # creator's post-create 0x43 poll -> 201 GRANT
                    room_slot = getattr(s,'room_slot',0)
                    rooms = db_get_open_rooms()
                    if rooms and (s.current_room or room_slot):
                        rid   = s.current_room or rooms[0][0]
                        pcount= db_room_player_count(rid)
                        slot  = room_slot or (rid & 0xFF)
                        rd = bytes([0x43,slot,0,0,0,pcount,0x01,0,0,0,0,0,0,0,0,0,0])
                        log('POST-AUTH',f'scan-inner sub=0x43 -> room confirm slot=0x{slot:02x} players={pcount}')
                        resp = build_appspace_pkt(rd)
                        threading.Thread(target=lambda:send_rel(s,resp,'<- scan-inner 0x43',to=3.0),daemon=True).start()
                    else:
                        log('POST-AUTH','scan-inner sub=0x43 -> no room yet')
                else:
                    log('POST-AUTH','scan-inner sub=0x43 -> rate-limited')
                return  # never echo these

            # Inner vcncExitAppSpace (inner type=0x40, inner cmd=5)
            if inner1 == 0x40 and inner3 == 0x05:
                log('POST-AUTH','scan-inner vcncExitAppSpace -> exit reply')
                pl2=bytearray(80); pl2[0]=4; pl2[3]=0x64
                if not send_rel(s,bytes(pl2),'exit appspace reply (scan)'):
                    s.closing=True
                    with sl: sadrs.pop(s.addr,None); sids.pop(s.sid,None)
                return

        # Messages that must NEVER be echoed. Two kinds:
        #  - 0x20 (msg 32): no inbound dispatch handler -> echo logs "Unknown Type 32".
        #  - 0x03 (msg 3): NET::OBJECT delete NOTIFY (client -> server "I deleted object
        #    N", e.g. `out 3'3` [03 00 80] right after the back-button teardown's
        #    "del CLIENT Me 0"). Msg 3 DOES have an inbound handler - "Server require
        #    delete object %i" - so echoing it back commands the CLIENT to delete a
        #    bogus object id and crashes the engine: bounds error
        #    ARR<NET::OBJECT*,2048>[29696] (messages01.log, the post-leave crash).
        # In-game telemetry (flight state etc.) is client->server only and has NO inbound
        # dispatch handler; echoing it makes FA log "NET::MESSAGE with Unknown Type N" and
        # drop the link. messages16.log: the client built TRN02, spawned, took off, then
        # died the instant the server echoed 83/84/24 back. 0x18=24, 0x53=83, 0x54=84.
        NO_ECHO_SUBS = {0x20, 0x03, 0x45, 0x18, 0x53, 0x54, 0x4d, 0x21}  # 0x4d=msg77 plane-preload counts (echo -> index>=0 crash); 0x21=msg33 bail/eject report (echo of its 0xFFFF object index -> ARR<NET::OBJECT*,2048>[65535] bounds-error CTD, same class as 0x03)
        if sub in NO_ECHO_SUBS:
            log('POST-AUTH', f'cmd=0 sub=0x{sub:02x} (notify, must not echo) -> swallow')
            return
        if TRIM_RELIABLE_ECHOES and sub in TRIM_ECHO_SUBS:
            log('POST-AUTH', f'cmd=0 sub=0x{sub:02x} (TRIM_RELIABLE_ECHOES) -> swallow, no echo')
            return
        if sub == 0x3a and SEND_EXIT_UNRELIABLE and getattr(s,'_awaiting_reattach',False) and not s.entered_game:
            # Exit-context hangar plane-list: echo UNRELIABLY (no reliable-seq cost). Empty hangar
            # => client re-requests 0x3a => we re-echo. Normal hangar-entry 0x3a still reliable below.
            log('POST-AUTH', 'cmd=0 sub=0x3a (exit hangar list) -> echo UNRELIABLE')
            send_unrel(s, stored, 'echo 0x3a (exit, UNREL)')
            return

        # -- Per-side CATALOG FILTER (PLANE_FILTER_VIA_CATALOG): trim the echoed 0x3a plane
        # list to the player's current side so each nation sees only its own aircraft, while
        # the GAME_DEF leaves every plane flyable (byte0=0x1f) so side-changes stay light.
        # UPLOAD 0x3a payload = [bc][T][00][00][0x3a][plane_id ...] (flat ONE byte per id);
        # appspace Size = bc*16 + (T>>4) covers the 0x3a sub byte + the ids. The client's
        # DOWNLOAD decoder reads (Size-1)/3 records of 3 BYTES [planeID][ushort], so we MUST
        # re-encode the kept ids as 3-byte records (not 1-byte) - otherwise GE's 26 ids echo
        # as Size=27 -> (27-1)/3 = 8 garbage records, dropping the tail bombers. Reframed via
        # build_ingame_pkt (Size == byte count). Only filters when ON A SIDE (0..4) and the
        # upload carries more than that side's planes; never emits EMPTY (would re-trip the
        # leave/teardown), falling through to verbatim.
        if sub == 0x3a and PLANE_FILTER_VIA_CATALOG and s.nation is not None and 0 <= s.nation < 5:
            size = pl[0] * 16 + (pl[1] >> 4)
            if 1 <= size and 4 + size <= len(pl):
                ids = list(pl[5:4 + size])
                sc = _session_slot_camp(s)
                kept = [i for i in ids if sc.get(i, 0) == s.nation]
                if kept and len(kept) != len(ids):
                    rec = b''.join(struct.pack('<BH', i & 0xff, CATALOG_RECORD_USHORT & 0xffff) for i in kept)
                    fpkt = build_ingame_pkt(bytes([0x3a]) + rec)
                    log('POST-AUTH', f'cmd=0 sub=0x3a -> side {s.nation} catalog filtered {len(ids)}->{len(kept)} (3-byte recs, {1 + 3 * len(kept)}B)')
                    threading.Thread(target=lambda p=fpkt: send_reply(s, p, 'echo 0x3a (side-filtered, 3B)', to=5.0), daemon=True).start()
                    return

        # Echo-by-default for everything else (lobby AND in-game). The session that
        # reached flight (messages16) echoed in-game build/spawn messages; a blanket
        # in-game swallow instead FROZE the world build at ~97% (messages20) - the client
        # waits for replies to some of them (e.g. the 0x3a plane list, compound 0x4d).
        # Only genuine fire-and-forget crashers are suppressed via NO_ECHO_SUBS above; if
        # a NEW type crashes on echo with "NET::MESSAGE Unknown Type N", add 0xN there.
        # msg 4 (client's OWN object state) must NEVER be echoed. The client's msg-4 RECEIVE
        # path rejects an echoed msg-4 as 'Unsupported message 4' and CORRUPTS its object list,
        # so the next spawn's ServerConfirm is refused ('Confirm object N not found in list ->
        # send delete') and the fresh plane is deleted -> dead engine / teardown. The normal
        # spawn out-4 (type=0x12) is ServerConfirmed earlier; a BAIL-OUT sends the parachute's
        # out-4 as type=0xf2 sub=0x04, which lands here - swallow it, never echo. (messages04:
        # bail -> 'in 4'15' -> 'Unsupported message 4' -> respawn 260 'not found in list'.)
        if sub == 0x04:
            # msg-4 is the client's OWN object state - NEVER echo it (an echoed msg-4 is rejected as
            # 'Unsupported message 4' and corrupts the object list). The plane spawn out-4 (type=0x12)
            # is ServerConfirmed earlier. A BAIL-OUT sends the PARACHUTE's out-4 as type=0xf2 sub=0x04:
            # the client allocates a fresh object Number for the parachute, so the server MUST consume
            # one too - else its global Number counter runs one BEHIND the client's and the next
            # respawn's ServerConfirm carries a stale Number -> the client can't match it ('Confirm
            # object 259 not found in list -> send delete') and deletes the fresh plane (dead engine,
            # teardown). Consume a Number to stay in lock-step; send NO confirm and do NOT advance the
            # spawn ident (the parachute is not a ServerConfirmed spawn), and never echo.
            _pn = next_obj_number()
            # v198: the client registers the parachute under the NEXT ident too - resync the
            # fallback ident counter from the parachute's own out-4 ident field (pl[5:7]) so the
            # counter path can never repeat v197's stale-ident confirm ('Confirm object 258 not
            # found in list, send delete' -> fresh plane deleted, dead engine after respawn).
            _pi = struct.unpack_from('<H', pl, 5)[0] if len(pl) >= 7 else None
            if _pi is not None:
                s.spawn_ident_next = _pi + 1
            log('POST-AUTH', f'msg-4 (type=0x{tb:02x}) parachute/bail object -> consumed Number {_pn} '
                             f'ident={_pi} (counters resynced), no echo/confirm')
            return
        # Generic fall-through echo. HARD GUARD: never echo a type=0x00 reliable message. The
        # client's Conductor cannot parse a reliable msg with type byte 0 ("Server sent client
        # something it doesn't understand (-102)") and stops ACKing the moment it receives one,
        # killing the whole reliable channel (observed: a wrapped msg-77 `00 00 00 00 00 12 00 00
        # 4d` parsed here as tb=0x00 sub=0x00, got echoed as reliable type=0x00 seq=44, and every
        # server send from that point timed out -> "waiting for server response" -> empty plane
        # list). Wrapped forms whose real inner type sits at pl[8] must not be echoed verbatim;
        # if we didn't recognise it above, swallowing is strictly safer than emitting a type-0
        # reliable packet. (0x4d=msg77 plane-preload is already a NO_ECHO sub in its direct form.)
        if tb == 0x00:
            _inner = pl[8] if len(pl) > 8 else 0
            log('POST-AUTH', f'cmd=0 type=0x00 (wrapped, inner=0x{_inner:02x}) -> swallow '
                             f'(never echo a type-0 reliable msg; would -102 the client)')
            return
        log('POST-AUTH',f'cmd=0 type=0x{tb:02x} sub=0x{sub:02x} -> echo')
        threading.Thread(target=lambda:send_reply(s,stored,f'echo type=0x{tb:02x}',to=5.0),daemon=True).start()
        return

    if cmd == 0x0222:
        if len(pl) >= 15:
            inner_sub = pl[8] if len(pl)>8 else 0
            if inner_sub == 0xe4:
                sb14 = pl[14] if len(pl)>14 else 0
                if sb14 < 0x20: pname = pl[15:].split(b'\x00')[0].decode('ascii','replace')
                else:             pname = pl[14:].split(b'\x00')[0].decode('ascii','replace')
                slot = db_get_pilot_slot(s.account, pname) or 0
                s.current_pilot=pname; s.current_slot=slot
        threading.Thread(target=lambda:send_rel(s,stored,'<- echo cmd=546',to=5.0),daemon=True).start(); return

    if cmd==3:
        time.sleep(0.05)
        rec=bytearray(15); rec[0]=2; rec[2]=0x20; rec[11]=0xD3; rec[14]=s.nsq()
        sock.sendto(bytes(rec),s.addr)
        time.sleep(0.05); sock.sendto(build_data(106,s.nsq()),s.addr)
    elif cmd==2:
        pl2=bytearray(80); pl2[0]=4; pl2[3]=0x64; send_rel(s,bytes(pl2),'disconnect reply')
    elif cmd==5:
        log('POST-AUTH','vcncExitAppSpace (cmd=5)')
        pl2=bytearray(80); pl2[0]=4; pl2[3]=0x64
        if not send_rel(s,bytes(pl2),'exit appspace reply'):
            s.closing=True   # reply timed out -> client gone, stop heartbeat
            with sl: sadrs.pop(s.addr,None); sids.pop(s.sid,None)
    elif cmd==512:
        pilots=db_get_pilots(s.account) if s.account else []
        resp=build_e1_pilot_list(pilots)
        threading.Thread(target=lambda:send_rel(s,resp,'<- pilot list 512',to=5.0),daemon=True).start()
    elif cmd==530: pass
    else:
        if len(pl) >= 9: handle_compound(s, cmd, pl)

# --- Packet receiver ----------------------------------------------------------

def on_pkt(data, addr):
    s=get_s(addr)
    if not s: return
    sz=len(data)
    if sz==12 and (data[2]&0x80):
        sock.sendto(build_time_reply(data),addr); return
    if sz>=8:
        dw=struct.unpack_from('>I',data,4)[0]; pt=(dw>>29)&7
        if pt==1:
            s.rx+=1; cs=data[3] if sz>3 else 0
            pl=data[8:] if sz>8 else b''
            # Reconstruct the client's FULL 9-bit (mod-512) reliable seq. vcncNet's reliable
            # logic runs mod 512 (the 0x200 modulus in the ACK processor FUN_10006b0e) and its
            # send-queue base does NOT wrap at 256 - but the wire seq byte (data[3]) is only 8-bit
            # and wraps 255->0. Below 256 the two agree, so ACKing the 8-bit value worked; but on
            # the 256th reliable msg of a session the client's base is 256 while data[3]=0, so an
            # ACK built from the 8-bit value carries the wrong next_exp, the client's cumulative
            # removal never clears that packet, and it retransmits it forever -> freeze (observed
            # exactly: cs wraps 255->0, then cs=0 DUP#1..n every 5s). We track the 255->0 wraps
            # to rebuild cs9 in 0..511 and ACK in that space so the wrap stays aligned.
            _prev_cs = getattr(s, '_rel_rx_last_cs', None)
            if _prev_cs is not None and _prev_cs >= 0xC0 and cs < 0x40:      # 255->0 style wrap
                s._rel_rx_hi = (getattr(s, '_rel_rx_hi', 0) ^ 1)
            elif _prev_cs is not None and _prev_cs < 0x40 and cs >= 0xC0:    # rare backward wrap
                s._rel_rx_hi = (getattr(s, '_rel_rx_hi', 0) ^ 1)
            cs9 = ((getattr(s, '_rel_rx_hi', 0) & 1) << 8) | cs
            # - reliable-RX diagnostics -
            _now=time.time()
            s._rel_rx_count=getattr(s,'_rel_rx_count',0)+1
            _dup=(cs==getattr(s,'_rel_rx_last_cs',None))
            if _dup: s._rel_rx_dups=getattr(s,'_rel_rx_dups',0)+1
            s._rel_rx_last_cs=cs; s._rel_rx_time=_now
            if getattr(s,'_stall_warned',False):
                s._stall_warned=False
                s._rec_dumped=False
                log('STALL-WATCH', f'{s.current_pilot}: reliable RX RESUMED (cs={cs})')
            time.sleep(0.01); sock.sendto(build_rel_ack(30,cs9),s.addr)
            cv=struct.unpack_from('>H',pl,2)[0] if len(pl)>=4 else 0
            if getattr(s,'entered_game',False):
                _dtag=f' DUP#{s._rel_rx_dups}(retransmit)' if _dup else ''
                log('RELRX', f'{s.current_pilot} cs={cs} d0=0x{data[0]:02x} cmd={cv} sz={sz}{_dtag}')
                _rec(s, 'C->S', 'RELRX',
                     f'cs={cs} cmd={cv} sz={sz}{_dtag} pl={binascii.hexlify(pl[:24]).decode()}')
            if cv==4:
                s.session_id=pl[4:6] if len(pl)>=6 else b'\x00\x01'
                if not getattr(s,'_login_started',False):
                    s._login_started=True
                    threading.Thread(target=login,args=(s,),daemon=True).start()
            elif s.auth_done:
                with s._lock: s.post_auth_cmds.append((cv,pl))
            return
        if pt==0 and sz==8:
            aseq=(dw>>20)&0x1FF
            with s._lock: is_ack=aseq in s._evts
            if is_ack:
                s._ack_in_count=getattr(s,'_ack_in_count',0)+1
                s.sig(aseq); return
            s.closing=True
            if s.current_pilot:
                broadcast_player_leave(s.current_pilot, exclude_sess=s)
                broadcast_system(f'[{s.current_pilot}] has left')
                db_room_leave(s.current_pilot)
            _free_start_place(s)   # release start-place slot on disconnect
            with sl: sadrs.pop(addr,None); sids.pop(s.sid,None); return
        # CAPTURE (diagnostic): in-game packets that are neither reliable-data (pt=1)
        # nor ack/disconnect (pt=0) - the UNRELIABLE flight-telemetry stream a flying
        # client streams (currently dropped). Rate-limited hex sample of the payload
        # after the 8-byte VCNC header, so the entity/position format can be decoded
        # and relayed to other players in the room.
        if getattr(s,'entered_game',False):
            s._unrel_rx_time=time.time()
            # Flight recorder: keep the trailing telemetry so a stall dump shows the last
            # known aircraft state. Decode tick+Number (the trend fields) so a freeze dump
            # reveals whether the sim was degrading (tick stalling / Number changing) or the
            # client froze instantly from a clean stream.
            _td = _rec_decode_telem(data)
            _rec(s, 'C->S', 'UNREL',
                 f'sz={sz} {_td} hdr={hx(data[:8])} pl={hx(data[8:32])}')
        if CAPTURE_UNREL and s.entered_game:
            _now=time.time()
            if _now - getattr(s,'_unrel_ts',0.0) >= 0.5:
                s._unrel_ts=_now
                log('RX/UNREL', f'{getattr(s,"current_pilot",None)} sz={sz} hdr={hx(data[:8])} pl={hx(data[8:])}')
        # RELAY the flying client's telemetry to other flying players in the same room.
        if RELAY_TELEMETRY and getattr(s,'flying',False) and s.current_room is not None:
            relay_telemetry(s, data)

# --- Web Server Bridge --------------------------------------------------------

def get_existing_ticket(account_name: str) -> tuple:
    """Rebuilds the binary .vr1 ticket from database hex values."""
    if TICKET_TEMPLATE is None: raise RuntimeError("No ticket template loaded")
        
    conn = sqlite3.connect(DB_PATH)
    existing = conn.execute(
        "SELECT player_id, field_45, auth_block FROM accounts WHERE account_name=?", 
        (account_name,)
    ).fetchone()
    conn.close()
    
    if existing:
        pid_hex, f45_hex, ab_hex = existing
        ticket = bytearray(TICKET_TEMPLATE)
        ticket[TICKET_PID_OFF:TICKET_PID_OFF+4] = bytes.fromhex(pid_hex)
        ticket[TICKET_F45_OFF:TICKET_F45_OFF+4] = bytes.fromhex(f45_hex)
        ticket[TICKET_AB_OFF:TICKET_AB_OFF+16] = bytes.fromhex(ab_hex)
        
        acct_field = account_name.encode('ascii') + b'\x00' * (TICKET_ACCT_LEN - len(account_name))
        ticket[TICKET_ACCT_OFF:TICKET_ACCT_OFF+TICKET_ACCT_LEN] = acct_field
        
        return bytes(ticket), pid_hex
    raise ValueError(f"Account {account_name} not found in database.")

from web_server import start_web_server

def _stall_watch():
    """Background monitor for the reliable-channel stall. The failure signature seen in
    the field: a client keeps streaming UNRELIABLE telemetry while its RELIABLE channel
    goes silent (death-notify/respawn never arrive). Flag that transition once, with the
    channel state, so the next occurrence is captured instead of inferred."""
    while running:
        time.sleep(3.0)
        now=time.time()
        for s in get_all_sessions():
            if not getattr(s,'entered_game',False): continue
            r0=getattr(s,'_rel_rx_time',0.0)
            if r0<=0: continue
            rel_idle=now-r0; unrel_idle=now-getattr(s,'_unrel_rx_time',0.0)
            if rel_idle>=10.0 and unrel_idle<3.0 and not getattr(s,'_stall_warned',False):
                s._stall_warned=True
                with s._lock: pend=len(s._evts)
                log('STALL-WATCH', f'[warn] {s.current_pilot}: reliable RX idle {rel_idle:.1f}s but '
                                   f'unreliable active ({unrel_idle:.1f}s ago) - possible reliable '
                                   f'stall | last_cs={getattr(s,"_rel_rx_last_cs",None)} '
                                   f'rel_rx={getattr(s,"_rel_rx_count",0)} dups={getattr(s,"_rel_rx_dups",0)} '
                                   f'pending_tx={pend} acks_in={getattr(s,"_ack_in_count",0)}')
                if not getattr(s,'_rec_dumped',False):
                    s._rec_dumped=True
                    _p=_rec_dump(s, f'reliable stall (idle {rel_idle:.1f}s, last_cs='
                                    f'{getattr(s,"_rel_rx_last_cs",None)})')
                    if _p:
                        log('REC', f'flight recorder dumped -> {_p}')

# --- Main loop ----------------------------------------------------------------

log('SERVER',f'Fighter Ace LAN Server v200 on {HOST}:{PORT}')
# -- ONE-TIME DEBUG (remove later): decompress the stock arena templates FFA.gdf / TC.gdf
#    so their camps/side block can be diffed against what a created room stores. The
#    decompressor anchors on the 0x8a version byte, so each .gdf's "Custom Arena" label
#    prefix is skipped automatically. Read-only.
for _gdf in ('FFA', 'TC'):
    try:
        _p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          'FA', 'NewArenas', f'{_gdf}.gdf')
        with open(_p, 'rb') as _f:
            _raw = _f.read()
        log('GDFDUMP', f'{_gdf}.gdf raw={len(_raw)}B (verbatim, NOT decompressed): {bytes(_raw).hex()}')
    except Exception as _e:
        log('GDFDUMP', f'{_gdf}.gdf dump failed: {_e}')
threading.Thread(target=console_handler, daemon=True).start()

# Start the separate web server and inject our local server variables into it
threading.Thread(
    target=start_web_server, 
    args=(DB_PATH, get_existing_ticket, generate_ticket, log, arena_settings_read,
          ARENA_TAIL_FIELDS, _falog.get_recent_logs),
    daemon=True
).start()

threading.Thread(target=_stall_watch, daemon=True).start()

_drop_ts=0.0

def _guarded(fn, data, addr):
    try:
        fn(data, addr)
    except Exception:
        logx('DISPATCH', f'{fn.__name__} failed addr={addr} sz={len(data)} '
                         f'hdr={hx(data[:16])}')

while running:
    try: data,addr=sock.recvfrom(65536)
    except socket.timeout: continue
    except KeyboardInterrupt: running=False; break
    except OSError as e:
        # WinError 10054 (WSAECONNRESET): a prior sendto() to a client that has quit made
        # Windows post a stale ICMP port-unreachable, surfaced here on the NEXT recvfrom and
        # DISCARDING no real datagram of ours. SIO_UDP_CONNRESET(False) above normally
        # suppresses it; if one still slips through it is benign. Do NOT spam it as ERROR
        # every heartbeat - rate-limit to one WARNING per 30s so a real error is still visible.
        _wr = getattr(e, 'winerror', None)
        if _wr == 10054 or getattr(e, 'errno', None) in (10054,):
            _now = time.time()
            if _now - globals().get('_connreset_ts', 0.0) > 30.0:
                globals()['_connreset_ts'] = _now
                log('RX/DROP', 'WSAECONNRESET (10054) from a departed client - benign, suppressed for 30s')
            continue
        log('ERROR', str(e)); continue
    except Exception as e: log('ERROR',str(e)); continue
    if not data: continue
    pt=data[0]; sz=len(data)
    if sz==912 and pt==0:
        threading.Thread(target=_guarded, args=(handle_syn, data, addr), daemon=True).start()
    elif sz==8 and data[2]==2: _guarded(on_pkt, data, addr)
    elif sz==8: _guarded(on_pkt, data, addr)
    elif pt==2: _guarded(on_pkt, data, addr)
    elif pt==0: _guarded(on_pkt, data, addr)
    else:
        # If a RELIABLE packet (control-dword pt==1) ever lands here it is being dropped
        # WITHOUT an ACK -> the client's reliable window wedges -> stall. Always log these,
        # un-rate-limited, so the next stall is caught at the routing layer.
        _cpt = ((struct.unpack_from('>I',data,4)[0])>>29)&7 if sz>=8 else -1
        if _cpt==1:
            log('RELDROP', f'[warn] reliable pkt NOT routed -> dropped/un-ACKed '
                           f'data0=0x{pt:02x} sz={sz} cs={data[3] if sz>3 else 0} {hx(data[:16])}')
        # CAPTURE: packet matched by no route above - a candidate UNRELIABLE in-game
        # telemetry datagram with an unexpected first byte. Rate-limited raw log only
        # (do NOT route to on_pkt: avoids misparsing telemetry as a reliable packet).
        elif CAPTURE_UNREL:
            _t=time.time()
            if _t-_drop_ts>=0.5:
                _drop_ts=_t
                log('RX/DROP', f'data0=0x{pt:02x} sz={sz} {hx(data[:96])}')