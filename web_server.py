# =============================================================================
# FA Server - web interface (separate module, launched as a daemon thread from the
# main server file). Login / launcher / ladder / admin panel / arena settings / live console.
#
# CHANGELOG
# 2026-09-30: /auth - login API for the game website / forum.
#   POST /auth (JSON account_name + password) -> authorization token + the account's pilots;
#   GET /auth (Authorization: Bearer) re-checks a token; OPTIONS /auth answers the CORS
#   preflight. Callers are limited to auth_domains.txt (Origin host for browsers, resolved
#   address for a backend), optional shared key in auth_api_key.txt, HTTPS only, failed-login
#   limiter, [WEBAUTH] log lines. Full contract in the block above WebInterfaceHandler.
# 2026-09-29: SECURITY + WEBPERF flood.
#   * LOG_READ_TOKEN was hardcoded here and the GitHub repo is public -> anyone could read all
#     logs. Token now loaded from log_token.txt (gitignored) / FA_LOG_TOKEN_FILE; no file =
#     token access off. Old token burned. Compared with hmac.compare_digest.
#   * [WEBACCESS] log line for every log-endpoint reader: user, via session|token|BAD-TOKEN,
#     client IP, user agent; rate-limited to 1 line per (ip, via, user) per 10 min.
#   * [WEBPERF] threshold applies to BUILD time; lines show '(build Xms + send Yms)'. The
#     Live Console's 2s logs.json poll (70 KB, ~310 ms of transfer to a far browser) logged
#     itself every poll and kept the ring INFO-heavy -> self-sustaining flood.
# 2026-08-15: v418f5 - admin promote/demote from the Users tab.
#   Each account row gains a Promote (btn-green) / Demote (btn-yellow) toggle POSTing to
#   /admin/set_admin (admin-only, same guard as every other handler). Two rows never show
#   the toggle: your OWN account (an admin demoting themselves mid-session is a lock-out
#   footgun) and the built-in 'admin' account (init_db re-asserts its is_admin=1 on every
#   start, so a demote would silently revert - refusing is honest). Both are also enforced
#   server-side in the handler, not just hidden in the HTML.
# 2026-08-03: v410f5 - pilot editor edits the per-mode ladder boards.
#   /admin/edit_pilot gains a 'Ladder Boards - FFA / TC / Events' fieldset with all twelve
#   per-mode columns (fighter/bomber score + kills + deaths per board), for seeding or
#   correcting boards manually - e.g. copying a career total into the board it was really
#   earned on. Guarded like every other field: only rendered/saved when the column exists,
#   so an un-migrated DB is unaffected. Rank still derives from career scores only.
# 2026-08-03: v408f5 - ladder restructured: FFA | TC | Events are the MAIN tabs.
#   Fighter and Bomber scores are no longer their own tabs - they are COLUMNS inside every
#   board, exactly like the career split (score_<mode> = fighter-flown, new bscore_<mode> =
#   bomber-flown, fed by db_apply_score_delta(mode=, bomber=)). Four tabs now: Career (the
#   client-rendered career: Fighter/Bomber/Total + career kills/deaths) and FFA / TC /
#   Events, each a full 9-column scoreboard (#, Pilot, Rank, Fighter Score, Bomber Score,
#   Total, Kills, Deaths, K/D) sorted by that board's Total; every column header sorts.
# 2026-08-03: v407f5 - every ladder board is a COMPLETE scoreboard.
#   The FFA/TC/Events tabs showed career kills/deaths on every board; now each mode board
#   reads its OWN kills_<mode>/deaths_<mode> columns (fed by db_credit_kill(mode=)) and
#   computes its own K/D, so a pilot's FFA record is fully independent of their TC record.
#   The three career boards (Combined/Fighter/Bomber) share the career kill/death columns -
#   the DB has no per-airframe kill split, and inventing one would lie.
# 2026-08-03: v406f5 - per-mode ladder boards: FFA | TC | Events tabs.
#   The ladder gains three more tabs reading the new pilots.score_ffa/score_tc/score_events
#   tally columns the game server now feeds per arena mode (db_apply_score_delta(mode=)).
#   'Events' became a first-class scoring mode server-side, so the arena editor's Scoring
#   dropdown gains 'Force Events board' and the POST accepts it. Columns are guarded, so a
#   pre-migration DB renders zeros. Rank stays the combined-career rank on every board.
# 2026-08-03: v405f5 - ladder tabs: Combined | Fighter Score | Bomber Score.
#   The ladder only read the `score` column (Fighter Score, msg-25 f9) while FA keeps TWO
#   boards - `bomber_score` (f10) fed by what you were FLYING when you earned the points
#   (v242). Now three tabs, each its own sorted table: Combined (fighter+bomber - the total
#   that RANK is computed from, so it is the canonical board), Fighter, Bomber. Rank column
#   shows the same combined-ladder rank on every tab (it IS the pilot's rank; a per-column
#   'rank' would be an invention). One search box filters all three; chosen tab persists
#   (localStorage); sortTable generalized to sortLadder(tableId, col). Pilot names are now
#   HTML-escaped in ladder rows (they weren't - v317 allows @/#/! names, so they must be).
#   Tab chrome lives in LADDER_TABS_ASSETS, a PLAIN string for the same brace-escaping
#   reason as ADMIN_TABS_ASSETS.
# 2026-08-03: v404f5 - scoring reference page + per-arena scoring control + ladder ranks.
#   * /scoring - renders the game server's live scoring tables (injected via scoring_ref_fn so
#     the page can never drift from the code): the 13-rank 2004 ladder with score bands and
#     loss percentages, the authoritative per-plane FFA/TC values (filterable), the AI-object
#     values, and the flat event bonuses. Linked from the dashboard nav and the ladder.
#   * Arena settings editor gained a Scoring dropdown (settings_json 'scoring_mode'):
#     Default (decided by the Title/category - the effective result is shown inline), or force
#     FFA values / TC values / no global scoring for this one arena. The game server reads the
#     override FIRST, so it wins over the category. Default stores no key.
#   * /ladder shows each pilot's military rank (computed from score against the injected
#     ladder) in its own sortable column; the position column is now '#'.
# 2026-07-24: v322 - the health watchdog is now SILENT while healthy.
#   The web server has been stable, so the observability scaffolding from the 07-23 work is
#   just noise. Removed: the startup ping line, the per-check DEBUG heartbeat, the INFO pulse
#   every 10 checks, and the "recovered" line. The check itself is UNCHANGED - still every 30s
#   with a 10s timeout, still two consecutive bad checks before a restart.
#   Nothing diagnostic was lost. The reason for each bad check is buffered and emitted as part
#   of the restart line, so a restart still says exactly what failed and when:
#     restarting web server - 2 failed checks: [10:14:03 no response within 10s;
#                                               10:14:33 slow 12.4s > 10s]
#   WEB_HEALTH_VERBOSE = True restores the old per-check chatter for debugging.
#   ALSO added a guard that the new silence made necessary: if the health ping can never
#   succeed for an ENVIRONMENTAL reason (proxy env var, 127.0.0.1 blocked, port taken by
#   another process), the watchdog would bounce a perfectly healthy web server every 60s
#   forever - and with healthy checks now silent, restart lines would be the only clue. After
#   3 restarts with no successful check in between it says so once, plainly, and backs off to
#   one check every 300s; any successful check resets it and logs that it has resumed.
# 2026-07-24: v321 - admin Logs tab: browse, tail and download the server's log files.
#   Third top-level tab on /admin. The list is loaded lazily from /admin/logfiles.json (there
#   are already 170+ run_*.log files, so rendering them into every /admin response would bloat
#   the page); each row offers "View tail" (last 128 KB in the browser, so a multi-MB log can
#   be peeked at without downloading) and "Download".
#   SECURITY - this is the only place the panel serves files off disk, so the path handling is
#   deliberately paranoid. The client supplies a BARE FILENAME only; the directory always comes
#   from the server (SRV['log_dir'], injected from the game server's LOG_DIR). Four independent
#   checks in _safe_log_path(), any one of which suffices alone:
#     1. basename(name) == name   -> no separators, no '..'
#     2. reject ':' and NUL       -> no Windows drive-relative paths, no NTFS ADS, no NUL trunc
#     3. extension allowlist      -> .log / .log.<n> / .txt / .err only
#     4. realpath containment     -> resolves symlinks/junctions, proves it's inside logs/
#   Verified against 27 attack strings (../, ..\, URL-encoded, absolute, C:.., ADS, NUL,
#   sub-dir, and a symlink deliberately pointing outside the dir) under BOTH posix and Windows
#   path semantics - all blocked; all 5 legitimate log shapes resolve.
#   The name charset also makes Content-Disposition header injection impossible (no quote, CR,
#   LF, space or ';' can appear in a name that passes).
#   Downloads STREAM in 64 KB chunks and emit exactly the Content-Length advertised, so the
#   live server.log growing (or rotating) mid-read cannot desync the body from the header.
#   The listing is filtered through _safe_log_path() too, so it can never show an entry that
#   would then 404. flightrec/ is not traversed FROM HERE; since v418f5 it is served as its
#   OWN flat root (second card on the Logs tab: _stall_dir/_safe_stall_path/_list_stall_files
#   + /admin/stallfiles.json + src=stall on view/download) with the identical four checks, so
#   the invariant is unchanged: every served root is one flat directory, keeping the
#   traversal surface at exactly zero.
# 2026-07-24: v318 - admin page split into tabs with per-panel filtering.
#   The page had grown into three long stacked cards on one scroll. Now:
#     User Management  ->  Users | Pilot Stats     (sub-tabs)
#     Arenas
#   Each of the three panels has its own filter box that hides non-matching table rows and
#   shows an "N of M" count. Tabbing is client-side only - no new routes, no extra requests,
#   and the server-side HTML for each table is unchanged, so every existing form still posts
#   to the same endpoint.
#   The chosen tab is persisted (localStorage, guarded by try/catch) because every admin
#   action POSTs and then 302s back to /admin; without it, renaming a pilot or saving an
#   arena would bounce you back to the Users tab each time.
#   ADMIN_TABS_ASSETS holds the CSS+JS as a PLAIN string, not an f-string: the admin body IS
#   an f-string, and CSS/JS braces inside one need doubling. Keeping them separate means the
#   braces pass through untouched (an f-string does not re-scan substituted values).
# 2026-07-24: v317 - admin console command box, account/pilot rename, manual pilot create.
#   * Live Console page gained a command input. It POSTs to /admin/console_cmd, which hands the
#     line to the game server's queue_console_command() - the SAME queue the server terminal
#     feeds - so every existing console command works identically from the browser. Command
#     output already goes through log('CONSOLE', ...), which this page streams, so nothing had
#     to be captured or plumbed back; the submitted line is echoed as "[web:<admin>] > <cmd>".
#     Up/Down arrows walk the in-page command history. Admin-only.
#   * /admin/rename_account and /admin/rename_pilot rename across EVERY table holding the name
#     (accounts, pilots, room_players, rooms.account_name, rooms.creator_pilot) in one
#     transaction - the DB has no foreign keys, so a partial rename silently orphans a pilot's
#     stats and their arenas. Duplicate checks are case-insensitive.
#     Account rename warns, in the UI, that the .vr1 ticket must be re-downloaded: the pid is
#     kept (so pilots/stats/arenas follow) but the account NAME lives inside the ticket and the
#     game server identifies a connection by that name first, so a stale ticket would re-create
#     the old account on the next connect.
#   * /admin/create_pilot makes a pilot by hand. _valid_name() accepts any printable ASCII
#     (0x20-0x7e) up to 31 chars, so staff names like @HQ / @FA / @INSTRUCTOR / @HELP and the
#     characters @ * # ! and space are all allowed - the game server never restricted pilot
#     names, that limit is the client's own name-entry box. Rejected: control bytes (they
#     terminate the NUL-terminated wire field and corrupt the client's text parse), non-ASCII,
#     empty/whitespace-only, over-length, and duplicates.
#     NOTE: because names may now contain ' " < > &, every place a name is rendered is escaped
#     and no name is interpolated into a JS confirm() string.
# 2026-07-23: STABILITY - made the web server multithreaded and added a health watchdog.
#   Was plain single-threaded HTTPServer (serial: one request at a time). One stalled request -
#   a half-open FA-launcher browser socket, a SQLite lock, or the /admin/logs.json 2s auto-poll
#   from a console left open - queued ALL others forever, so after a few hours it wedged and
#   "stopped responding". Fixes:
#     * ThreadingHTTPServer (_ThreadedWebServer, daemon_threads) so one stuck request can't block
#       the rest; per-request socket timeout + larger accept backlog.
#     * _connect() opens SQLite with a 5s busy_timeout so concurrent writers wait instead of
#       erroring 'database is locked' (used by new code; the existing per-request connects still
#       work and can be migrated to it later).
#     * Health watchdog thread: every 30s it GETs http://127.0.0.1:80/login (needs no DB/auth);
#       if it doesn't answer within 10s twice in a row, _restart_httpd() tears down and rebuilds
#       just the web server on the same port (shutdown -> server_close -> rebind, 5 retries).
#       This is the requested "wget localhost:80, if >10s restart the web portion" keep-alive.
#   serving now runs on its own thread; start_web_server still blocks (unchanged contract).
# =============================================================================
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
import os
import ssl
import subprocess
import sqlite3
import hashlib
import hmac
import secrets
import json
import re
import threading
import time
import socket
import urllib.request
from http import cookies
from html import escape as hesc

# 2026-08-23: HTTPS variant. TLS files live next to this script so the same file runs on
# Windows and on the GCP VM. If cert+key are present we serve HTTPS on 443; if they are
# absent (e.g. a test box without keys) we fall back to plain HTTP on 80, exactly like
# the original web_server.py.
_WEB_DIR      = os.path.dirname(os.path.abspath(__file__))
WEB_CERT_FILE = os.path.join(_WEB_DIR, 'fa-re-srv_ddns_net.pem')  # fullchain: leaf + 2 intermediates
WEB_KEY_FILE  = os.path.join(_WEB_DIR, 'privateKey.key')          # private key (chmod 600 on the VM)
WEB_TLS       = os.path.exists(WEB_CERT_FILE) and os.path.exists(WEB_KEY_FILE)
WEB_PORT      = 443 if WEB_TLS else 80
DEFAULT_CLIENT_PATH = r"C:\games\FA\FA.exe"
WEB_SESSIONS = {}

# Bridge to hold references injected from the main game server
# example event scripts shown under the Events tab (v958f5c)
# ---- v958f5e: event-script library on the server (<server dir>/event_scripts/<name>.json) ----
def _evs_lib_dir():
    d = os.path.join(os.path.dirname(os.path.abspath(SRV.get('server_py') or __file__)), 'event_scripts')
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d

def _evs_lib_safe(name):
    """File-safe script name: letters, digits, space, _ - . ( ); 1..60 chars; '' if nothing is left."""
    n = re.sub(r'[^A-Za-z0-9 _\-.()]+', '', str(name or '')).strip()
    if n.lower().endswith('.json'):
        n = n[:-5]
    return n.strip().strip('.')[:60]

def _evs_lib_list():
    out = []
    try:
        for fn in sorted(os.listdir(_evs_lib_dir())):
            if not fn.lower().endswith('.json'):
                continue
            p = os.path.join(_evs_lib_dir(), fn)
            try:
                st = os.stat(p)
                title = ''
                try:
                    with open(p, encoding='utf-8') as f:
                        j = json.load(f)
                    title = f'{j.get("name", "")} ({j.get("mode", "team")}, {j.get("victory", "points")})'
                except Exception:
                    title = '(not valid JSON)'
                out.append({'name': fn[:-5], 'size': st.st_size, 'mtime': int(st.st_mtime), 'title': title})
            except OSError:
                continue
    except Exception:
        pass
    return out

def _evs_lib_json(handler, code, obj):
    body = json.dumps(obj).encode('utf-8')
    handler.send_response(code)
    handler.send_header('Content-Type', 'application/json')
    handler.send_header('Cache-Control', 'no-store')
    handler.end_headers()
    handler.wfile.write(body)

EVS_EX_BOB = json.dumps({
    'name': 'Battle of Britain', 'victory': 'points', 'report_min': 30, 'announce': True,
    'points': {'kill_fighter': 1, 'kill_bomber': 2},
    'teams': {
        'GB': {'objective': 'Stop the raids - every bomber shot down counts double',
               'points': {'kill_fighter': 1, 'kill_bomber': 4}},
        'GE': {'objective': 'Bomb the radar chain and the sector airfields',
               'points': {'kill_fighter': 1, 'scene_damage': 0.5, 'damage_specific': {'46': 2, '47': 2}}}},
}, indent=2)
EVS_EX_PPS = json.dumps({
    'name': 'Pin Point Parachuting', 'mode': 'personal', 'victory': 'points', 'report_min': 15, 'announce': True,
    'objectives': [{'type': 'chute_on_target', 'target': 'PPS@HQ', 'radius_m': 60, 'points': 10}],
}, indent=2)
EVS_EX_TC = json.dumps({
    'name': 'Capture the front', 'victory': 'points', 'report_min': 30, 'announce': True,
    'points': {'kill_fighter': 1, 'kill_bomber': 2, 'scene_capture': 5, 'capture_specific': {'46': 50},
               'hold_specific': {'46': 1}, 'tank': 2, 'train': 3, 'bridge': 5, 'troops_drop': 1,
               'supply_delivered': 2, 'supply_airdrop': 1},
}, indent=2)
EVS_EX_FOX = json.dumps({
    'name': 'Fox hunt', 'mode': 'personal', 'victory': 'points', 'report_min': 15, 'announce': True,
    'points': {'kill_fighter': 0.5, 'kill_bomber': 1},
    'objectives': [{'type': 'kill_target', 'target': 'FOX@FA', 'points': 1}],
}, indent=2)

EVS_BUILDER_HTML = '<div id="evsb" style="border:1px solid #c9d6e2; border-radius:6px; padding:10px; margin:8px 0; background:#fafcfe; max-width:760px;">\n<div style="font-weight:bold; margin-bottom:6px;">Script builder <span style="font-weight:normal; color:#888; font-size:0.85em;">- fills the JSON box below as you edit; "Load from JSON" reads the box back into the form</span></div>\n<div style="display:flex; flex-wrap:wrap; gap:12px; align-items:flex-end;">\n <label style="font-size:0.85em;">Event name<br><input type="text" id="eb_name" style="width:200px; padding:5px;"></label>\n <label style="font-size:0.85em;">Scoring<br><select id="eb_mode" style="padding:5px;"><option value="team">team event - teams score</option><option value="personal">personal event - every pilot for themselves</option></select></label>\n <label style="font-size:0.85em;">Winner has<br><select id="eb_victory" style="padding:5px;"><option value="points">most points</option><option value="kills">most air kills</option><option value="none">no winner (scores only)</option></select></label>\n <label style="font-size:0.85em;">Progress update every<br><input type="number" id="eb_report" min="0" max="240" style="width:70px; padding:5px;"> min (0 = none)</label>\n <label style="font-size:0.85em;"><input type="checkbox" id="eb_announce" checked> announce every score</label>\n</div>\n<div style="margin-top:10px; font-size:0.85em;"><b>Points per action</b> - the <i>All teams</i> column is the shared table; a team column overrides it for that team (blank = inherit). In a personal event the points go to the pilot who did it (the <i>All teams</i> column is all you need). Kills: a bomber is any bomber / attacker / transport.</div>\n<div style="overflow:auto;"><table id="eb_tbl" style="border-collapse:collapse; font-size:0.85em; margin-top:4px;">\n<tr><th style="text-align:left; padding:3px 6px;">Action</th><th style="padding:3px 6px;">All teams</th>\n<th style="padding:3px 6px;">US</th><th style="padding:3px 6px;">GB</th><th style="padding:3px 6px;">SU</th><th style="padding:3px 6px;">GE</th><th style="padding:3px 6px;">JP</th></tr>\n</table></div>\n<div style="margin-top:8px; font-size:0.85em;"><b>Team objectives</b> (shown to each team when scoring starts; a team with an objective or any points of its own takes part)</div>\n<div id="eb_objs" style="display:flex; flex-wrap:wrap; gap:8px; margin-top:4px;"></div>\n<div style="margin-top:10px; font-size:0.85em;"><b>Specific scenes</b> - scene number from <code>tc status</code> / the map; points for capturing it, per minute holding it, per 1 % damage on it, per tonne of supplies delivered to it</div>\n<table id="eb_sc" style="border-collapse:collapse; font-size:0.85em; margin-top:4px;">\n<tr><th style="padding:3px 6px;">Scene #</th><th style="padding:3px 6px;">Capture</th><th style="padding:3px 6px;">Hold /min</th><th style="padding:3px 6px;">Damage /%</th><th style="padding:3px 6px;">Supply /t</th><th></th></tr>\n</table>\n<a href="#" onclick="ebAddScene();return false;" style="font-size:0.85em;">+ add a scene</a>\n<div style="margin-top:10px; font-size:0.85em;"><b>Pin Point Parachuting</b> - bail out and land the canopy on the target pilot\'s parked plane</div>\n<div style="display:flex; flex-wrap:wrap; gap:12px; align-items:flex-end; margin-top:4px;">\n <label style="font-size:0.85em;">Target pilot<br><input type="text" id="eb_pps_target" placeholder="PPS@HQ" style="width:140px; padding:5px;"></label>\n <label style="font-size:0.85em;">Within<br><input type="number" id="eb_pps_radius" min="5" max="2000" placeholder="60" style="width:70px; padding:5px;"> m</label>\n <label style="font-size:0.85em;">Points<br><input type="number" id="eb_pps_points" min="0" step="0.5" placeholder="10" style="width:70px; padding:5px;"></label>\n <label style="font-size:0.85em;">Teams (optional, e.g. GB,GE)<br><input type="text" id="eb_pps_teams" style="width:120px; padding:5px;"></label>\n</div>\n<div style="margin-top:10px; font-size:0.85em;"><b>Fox hunt</b> - whoever shoots down the named pilot scores for their team (any camp), with an arena-wide announcement</div>\n<div style="display:flex; flex-wrap:wrap; gap:12px; align-items:flex-end; margin-top:4px;">\n <label style="font-size:0.85em;">Fox pilot<br><input type="text" id="eb_fox_target" placeholder="FOX@FA" style="width:140px; padding:5px;"></label>\n <label style="font-size:0.85em;">Points per fox kill<br><input type="number" id="eb_fox_points" min="0" step="0.5" placeholder="1" style="width:70px; padding:5px;"></label>\n <label style="font-size:0.85em;">Teams (optional)<br><input type="text" id="eb_fox_teams" style="width:120px; padding:5px;"></label>\n</div>\n<details style="margin-top:10px; font-size:0.85em;"><summary style="cursor:pointer; color:#2c5f8a;"><b>Message templates</b> - the arena broadcasts, editable (blank = default text, a single <code>-</code> silences that message)</summary>\n<div style="color:#666; margin:4px 0;">Placeholders in braces are filled in at run time; <code>{delta}</code> already carries its sign (+1). Lines longer than 74 characters are word-wrapped onto further yellow lines.</div>\n<table id="eb_msgs" style="border-collapse:collapse; width:100%;"></table>\n</details>\n<div style="margin-top:10px;">\n <a href="#" onclick="ebBuild();return false;" class="btn-green" style="padding:6px 14px; font-size:0.85em; text-decoration:none; color:#fff;">Build JSON from the form</a>\n &nbsp; <a href="#" onclick="ebLoad();return false;" style="font-size:0.85em;">&uarr; Form from JSON box</a>\n &nbsp; <a href="#" onclick="ebClear();return false;" style="font-size:0.85em; color:#a00;">Clear</a>\n <span id="eb_msg" style="font-size:0.85em; color:#888; margin-left:10px;"></span>\n</div>\n<div style="margin-top:12px; padding-top:8px; border-top:1px dashed #c9d6e2; font-size:0.85em;">\n<b>Files</b> &nbsp;\n<a href="#" onclick="ebExport();return false;">Export to PC (.json)</a>\n&nbsp;|&nbsp; Load from PC: <input type="file" id="eb_file" accept=".json,application/json" style="font-size:0.85em;" onchange="ebImport(this)">\n</div>\n<div style="margin-top:8px; font-size:0.85em;">\n<b>Server library</b> <span style="color:#888;">(event_scripts/ next to server.py - shared by every arena)</span><br>\n<select id="eb_lib" style="padding:4px; min-width:260px; margin-top:4px;"><option value="">(loading...)</option></select>\n<a href="#" onclick="ebLibLoad();return false;" style="margin-left:6px;">Load</a>\n&nbsp;<a href="#" onclick="ebLibDownload();return false;">Download</a>\n&nbsp;<a href="#" onclick="ebLibDelete();return false;" style="color:#a00;">Delete</a>\n&nbsp;&nbsp; <input type="text" id="eb_lib_name" placeholder="name to save as" style="padding:4px; width:180px;">\n<a href="#" onclick="ebLibSave();return false;" class="btn-green" style="padding:4px 10px; text-decoration:none; color:#fff;">Save to server</a>\n<span id="eb_lib_msg" style="color:#888; margin-left:8px;"></span>\n</div>\n</div>\n<script>\nvar EB_MSGS=[[\'start\',\'EVENT "{name}" is ON - scoring started.\',\'name\'],[\'personal\',\'PERSONAL EVENT - every pilot scores for themselves.\',\'name\'],\n [\'objective\',\'{team} objective: {objective}\',\'team objective\'],[\'fox_start\',\'FOX HUNT: shoot down {fox} for {points} pts!\',\'fox points\'],\n [\'score_team\',\'{team} {delta}: {pilot} {what}\',\'team delta pilot what total\'],[\'score_personal\',\'{pilot} {delta} (total {total}): {what}\',\'pilot delta total what team\'],\n [\'fox_team\',\'FOX HUNT: {pilot} bagged {fox}! {team} {delta} (fox down x{count})\',\'pilot fox team delta total count\'],\n [\'fox_personal\',\'FOX HUNT: {pilot} bagged {fox}! {delta} (total {total}, fox down x{count})\',\'pilot fox team delta total count\'],\n [\'pps_hit\',\'landed {dist} m from {target}\',\'dist target radius pilot\'],[\'pps_miss\',\'Missed: {dist} m from {target} (target {radius} m).\',\'dist target radius pilot\'],\n [\'update\',\'EVENT UPDATE ({mins} min) - {name}: {scores}\',\'mins name scores\'],[\'final\',\'FINAL - {name}: {scores}\',\'mins name scores\'],\n [\'top\',\'Top: {list}\',\'list\'],[\'then\',\'Then: {list}\',\'list\'],[\'win\',\'{winner} WINS "{name}"!\',\'winner name\'],[\'win_banner\',\'{winner} WINS\',\'winner name\'],\n [\'draw\',\'"{name}" ends in a draw.\',\'name\'],[\'draw_banner\',\'DRAW\',\'name\']];\nfunction ebInitMsgs(){\n  var t=document.getElementById(\'eb_msgs\'); if(!t) return;\n  EB_MSGS.forEach(function(m){ var tr=document.createElement(\'tr\');\n    tr.innerHTML=\'<td style="padding:2px 6px; white-space:nowrap; vertical-align:top;"><code>\'+m[0]+\'</code><br><span style="color:#999; font-size:0.9em;">{\'+m[2].split(\' \').join(\'} {\')+\'}</span></td>\'\n      +\'<td style="padding:2px 4px; width:100%;"><input type="text" class="eb_msg" data-key="\'+m[0]+\'" placeholder="\'+m[1].replace(/"/g,\'&quot;\')+\'" style="width:100%; padding:3px; font-family:monospace; font-size:0.95em;"></td>\';\n    t.appendChild(tr); });\n}\nfunction ebMsgsBuild(sc){ var out={}; document.querySelectorAll(\'input.eb_msg\').forEach(function(e){ var v=e.value; if(v.trim()!==\'\') out[e.getAttribute(\'data-key\')]=v; });\n  if(Object.keys(out).length) sc.messages=out; }\nfunction ebMsgsLoad(sc){ var m=sc.messages||{}; document.querySelectorAll(\'input.eb_msg\').forEach(function(e){ var v=m[e.getAttribute(\'data-key\')]; e.value=(v==null)?\'\':v; }); }\nfunction ebExport(){ var txt=ebBox().value.trim(); if(!txt){ ebBuild(true); txt=ebBox().value.trim(); } if(!txt){ document.getElementById(\'eb_msg\').textContent=\'nothing to export\'; return; }\n  var nm=\'event\'; try{ nm=(JSON.parse(txt).name||\'event\'); }catch(e){} nm=nm.replace(/[^A-Za-z0-9 _\\-.()]+/g,\'\').trim()||\'event\';\n  var a=document.createElement(\'a\'); a.href=URL.createObjectURL(new Blob([txt],{type:\'application/json\'})); a.download=nm+\'.json\'; document.body.appendChild(a); a.click();\n  setTimeout(function(){ URL.revokeObjectURL(a.href); a.remove(); },500); }\nfunction ebImport(inp){ var f=inp.files&&inp.files[0]; if(!f) return; var r=new FileReader();\n  r.onload=function(){ try{ var j=JSON.parse(r.result); if(typeof j!==\'object\'||Array.isArray(j)) throw new Error(\'not a script object\'); ebBox().value=JSON.stringify(j,null,2); ebLoad(true);\n      document.getElementById(\'eb_msg\').textContent=\'loaded "\'+f.name+\'" from your PC - press Save to store it on this arena.\'; }\n    catch(e){ document.getElementById(\'eb_msg\').textContent=\'could not load \'+f.name+\': \'+e.message; } inp.value=\'\'; };\n  r.readAsText(f); }\nfunction ebLibFill(list){ var sel=document.getElementById(\'eb_lib\'); if(!sel) return; var cur=sel.value; sel.innerHTML=\'\';\n  var o0=document.createElement(\'option\'); o0.value=\'\'; o0.textContent=list.length?\'- pick a saved script -\':\'(library is empty)\'; sel.appendChild(o0);\n  list.forEach(function(s){ var o=document.createElement(\'option\'); o.value=s.name; o.textContent=s.name+\'  -  \'+s.title; sel.appendChild(o); }); sel.value=cur; }\nfunction ebLibRefresh(){ fetch(\'/admin/evs_library.json\',{credentials:\'same-origin\'}).then(function(r){return r.json();}).then(function(j){ ebLibFill(j.scripts||[]); })\n  .catch(function(e){ var m=document.getElementById(\'eb_lib_msg\'); if(m) m.textContent=\'library unavailable: \'+e; }); }\nfunction ebLibPost(data){ var body=Object.keys(data).map(function(k){return encodeURIComponent(k)+\'=\'+encodeURIComponent(data[k]);}).join(\'&\');\n  return fetch(\'/admin/evs_library\',{method:\'POST\',credentials:\'same-origin\',headers:{\'Content-Type\':\'application/x-www-form-urlencoded\'},body:body}).then(function(r){return r.json();}); }\nfunction ebLibLoad(){ var n=document.getElementById(\'eb_lib\').value; var m=document.getElementById(\'eb_lib_msg\'); if(!n){ m.textContent=\'pick a script first\'; return; }\n  fetch(\'/admin/evs_library_get?name=\'+encodeURIComponent(n),{credentials:\'same-origin\'}).then(function(r){return r.json();}).then(function(j){\n    if(!j.ok){ m.textContent=j.error||\'failed\'; return; } ebBox().value=j.script; ebLoad(true); document.getElementById(\'eb_lib_name\').value=n;\n    m.textContent=\'loaded "\'+n+\'" - press Save to store it on this arena.\'; }).catch(function(e){ m.textContent=\'failed: \'+e; }); }\nfunction ebLibDownload(){ var n=document.getElementById(\'eb_lib\').value; if(!n){ document.getElementById(\'eb_lib_msg\').textContent=\'pick a script first\'; return; }\n  window.location=\'/admin/evs_library_get?download=1&name=\'+encodeURIComponent(n); }\nfunction ebLibSave(){ var m=document.getElementById(\'eb_lib_msg\'); var n=document.getElementById(\'eb_lib_name\').value.trim(); var txt=ebBox().value.trim();\n  if(!txt){ ebBuild(true); txt=ebBox().value.trim(); } if(!n){ try{ n=JSON.parse(txt).name||\'\'; }catch(e){} } if(!n){ m.textContent=\'give it a name\'; return; } if(!txt){ m.textContent=\'nothing to save\'; return; }\n  ebLibPost({action:\'save\',name:n,script:txt}).then(function(j){ if(j.ok){ ebLibFill(j.scripts||[]); document.getElementById(\'eb_lib\').value=j.name; m.textContent=\'saved "\'+j.name+\'" on the server.\'; } else m.textContent=j.error||\'failed\'; })\n  .catch(function(e){ m.textContent=\'failed: \'+e; }); }\nfunction ebLibDelete(){ var n=document.getElementById(\'eb_lib\').value; var m=document.getElementById(\'eb_lib_msg\'); if(!n){ m.textContent=\'pick a script first\'; return; }\n  if(!window.confirm(\'Delete "\'+n+\'" from the server library?\')) return;\n  ebLibPost({action:\'delete\',name:n}).then(function(j){ if(j.ok){ ebLibFill(j.scripts||[]); m.textContent=\'deleted "\'+n+\'".\'; } else m.textContent=j.error||\'failed\'; }); }\n\nvar EB_KEYS=[[\'kill_fighter\',\'Shoot down a fighter\'],[\'kill_bomber\',\'Shoot down a bomber\'],[\'kill_any\',\'Any air kill (if the two above are blank)\'],\n [\'scene_trigger\',\'Trigger a scene\'],[\'scene_capture\',\'Capture a scene\'],[\'scene_damage\',\'Damage a scene (per 1 %)\'],\n [\'bridge\',\'Destroy a bridge\'],[\'tank\',\'Destroy a tank\'],[\'train\',\'Destroy a train\'],[\'troops_drop\',\'Land a troop chute\'],\n [\'supply_delivered\',\'Deliver supplies by landing (per tonne)\'],[\'supply_airdrop\',\'Air-drop supplies (per tonne)\'],[\'building_repaired\',\'Building rebuilt by a delivery\']];\nvar EB_TEAMS=[\'US\',\'GB\',\'SU\',\'GE\',\'JP\'];\nfunction ebBox(){return document.querySelector(\'textarea[name=s_ev_script]\');}\nfunction ebInit(){\n  var t=document.getElementById(\'eb_tbl\');\n  EB_KEYS.forEach(function(k){\n    var tr=document.createElement(\'tr\'); var h=\'<td style="padding:2px 6px; white-space:nowrap;">\'+k[1]+\'</td>\';\n    h+=\'<td style="padding:2px 4px;"><input type="number" step="0.5" class="eb_pt" data-key="\'+k[0]+\'" data-team="" style="width:64px; padding:3px;"></td>\';\n    EB_TEAMS.forEach(function(tm){h+=\'<td style="padding:2px 4px;"><input type="number" step="0.5" class="eb_pt" data-key="\'+k[0]+\'" data-team="\'+tm+\'" style="width:64px; padding:3px;"></td>\';});\n    tr.innerHTML=h; t.appendChild(tr);\n  });\n  var o=document.getElementById(\'eb_objs\');\n  EB_TEAMS.forEach(function(tm){\n    var d=document.createElement(\'label\'); d.style.fontSize=\'0.85em\';\n    d.innerHTML=tm+\'<br><input type="text" class="eb_obj" data-team="\'+tm+\'" placeholder="objective for \'+tm+\'" style="width:220px; padding:4px;">\';\n    o.appendChild(d);\n  });\n  ebInitMsgs();\n  document.getElementById(\'evsb\').addEventListener(\'input\', function(ev){ if(ev.target && (ev.target.id===\'eb_lib_name\'||ev.target.id===\'eb_file\')) return; ebBuild(true);});\n  ebLoad(true); ebLibRefresh();\n  var bx=ebBox(); if(bx){ var tmr=null; bx.addEventListener(\'input\', function(){ ebBox()._typing=true; clearTimeout(tmr); tmr=setTimeout(function(){ ebLoad(false, true); ebBox()._typing=false; }, 400); }); }\n}\nfunction ebAddScene(v){\n  v=v||{}; var t=document.getElementById(\'eb_sc\'); var tr=document.createElement(\'tr\');\n  function inp(n,val){return \'<td style="padding:2px 4px;"><input type="number" step="0.5" class="eb_sc_\'+n+\'" value="\'+(val==null?\'\':val)+\'" style="width:70px; padding:3px;"></td>\';}\n  tr.innerHTML=\'<td style="padding:2px 4px;"><input type="number" class="eb_sc_id" value="\'+(v.id==null?\'\':v.id)+\'" style="width:64px; padding:3px;"></td>\'\n    +inp(\'cap\',v.cap)+inp(\'hold\',v.hold)+inp(\'dmg\',v.dmg)+inp(\'sup\',v.sup)\n    +\'<td><a href="#" onclick="this.parentNode.parentNode.remove();ebBuild(true);return false;" style="color:#a00;">x</a></td>\';\n  t.appendChild(tr);\n}\nfunction ebNum(el){ if(!el) return null; var s=(el.value||\'\').trim(); if(s===\'\') return null; var n=parseFloat(s); return isNaN(n)?null:n; }\nvar EB_MANAGED={name:1,mode:1,victory:1,report_min:1,announce:1,points:1,teams:1,objectives:1,messages:1};\nfunction ebBuild(quiet){\n  if(ebBox() && ebBox()._typing) return;\n  var sc={};\n  try{ var prev=JSON.parse(ebBox().value); if(prev && typeof prev===\'object\') for(var pk in prev){ if(!EB_MANAGED[pk]) sc[pk]=prev[pk]; } }catch(e){} var name=document.getElementById(\'eb_name\').value.trim(); if(name) sc.name=name;\n  sc.mode=document.getElementById(\'eb_mode\').value; sc.victory=document.getElementById(\'eb_victory\').value;\n  var rep=ebNum(document.getElementById(\'eb_report\')); sc.report_min=(rep==null?30:rep);\n  sc.announce=document.getElementById(\'eb_announce\').checked;\n  var shared={}; var teams={};\n  document.querySelectorAll(\'input.eb_pt\').forEach(function(e){\n    var v=ebNum(e); if(v==null) return; var tm=e.getAttribute(\'data-team\'); var k=e.getAttribute(\'data-key\');\n    if(!tm){shared[k]=v;} else {teams[tm]=teams[tm]||{points:{}}; teams[tm].points[k]=v;}\n  });\n  document.querySelectorAll(\'input.eb_obj\').forEach(function(e){\n    var v=e.value.trim(); if(!v) return; var tm=e.getAttribute(\'data-team\'); teams[tm]=teams[tm]||{points:{}}; teams[tm].objective=v;\n  });\n  var rows=document.querySelectorAll(\'#eb_sc tr\'); var caps={},holds={},dmgs={},sups={};\n  rows.forEach(function(tr){\n    var id=tr.querySelector(\'.eb_sc_id\'); if(!id) return; var sid=(id.value||\'\').trim(); if(!sid) return;\n    var c=ebNum(tr.querySelector(\'.eb_sc_cap\')), h=ebNum(tr.querySelector(\'.eb_sc_hold\')), d=ebNum(tr.querySelector(\'.eb_sc_dmg\')), s2=ebNum(tr.querySelector(\'.eb_sc_sup\'));\n    if(c!=null) caps[sid]=c; if(h!=null) holds[sid]=h; if(d!=null) dmgs[sid]=d; if(s2!=null) sups[sid]=s2;\n  });\n  if(Object.keys(caps).length) shared.capture_specific=caps; if(Object.keys(holds).length) shared.hold_specific=holds;\n  if(Object.keys(dmgs).length) shared.damage_specific=dmgs; if(Object.keys(sups).length) shared.supply_specific=sups;\n  if(Object.keys(shared).length) sc.points=shared;\n  for(var tm in teams){ if(!Object.keys(teams[tm].points).length) delete teams[tm].points; }\n  if(Object.keys(teams).length) sc.teams=teams;\n  var tg=document.getElementById(\'eb_pps_target\').value.trim();\n  if(tg){ var o={type:\'chute_on_target\', target:tg, radius_m:(ebNum(document.getElementById(\'eb_pps_radius\'))||60), points:(ebNum(document.getElementById(\'eb_pps_points\'))||10)};\n    var tms=document.getElementById(\'eb_pps_teams\').value.split(\',\').map(function(x){return x.trim().toUpperCase();}).filter(function(x){return x;});\n    if(tms.length) o.teams=tms; sc.objectives=[o]; }\n  var fx=document.getElementById(\'eb_fox_target\').value.trim();\n  if(fx){ var f={type:\'kill_target\', target:fx, points:(ebNum(document.getElementById(\'eb_fox_points\'))||1)};\n    var ft=document.getElementById(\'eb_fox_teams\').value.split(\',\').map(function(x){return x.trim().toUpperCase();}).filter(function(x){return x;});\n    if(ft.length) f.teams=ft; sc.objectives=(sc.objectives||[]).concat([f]); }\n  ebMsgsBuild(sc);\n  var empty=!sc.name && !sc.points && !sc.teams && !sc.objectives && !sc.messages && Object.keys(sc).every(function(k){return EB_MANAGED[k];});\n  if(!ebBox()) return; ebBox().value=empty?\'\':JSON.stringify(sc,null,2);\n  if(!quiet) document.getElementById(\'eb_msg\').textContent=\'JSON built - press Save to store it.\';\n}\nfunction ebClear(keepBox){ document.querySelectorAll(\'#evsb input[type=text], #evsb input[type=number]\').forEach(function(e){ if(e.id!==\'eb_lib_name\') e.value=\'\'; });\n  document.getElementById(\'eb_victory\').value=\'points\'; document.getElementById(\'eb_mode\').value=\'team\'; document.getElementById(\'eb_announce\').checked=true;\n  document.querySelectorAll(\'#eb_sc tr\').forEach(function(tr,i){ if(i>0) tr.remove(); }); if(!keepBox){ ebBox().value=\'\'; document.getElementById(\'eb_msg\').textContent=\'cleared - press Save to remove the script.\'; } }\nfunction ebLoad(quiet, fromBox){\n  var bx=ebBox(); if(!bx) return; var txt=bx.value.trim(); if(!txt){ if(fromBox){ ebClear(true); document.getElementById(\'eb_msg\').textContent=\'JSON box is empty - form cleared.\'; } return; }\n  var sc; try{ sc=JSON.parse(txt); }catch(e){ document.getElementById(\'eb_msg\').textContent=(fromBox?\'form not updated - JSON box is not valid JSON yet: \':\'JSON box is not valid JSON: \')+e.message; return; }\n  if(typeof sc!==\'object\'||Array.isArray(sc)){ document.getElementById(\'eb_msg\').textContent=\'the script must be a JSON object {...}\'; return; }\n  document.getElementById(\'eb_name\').value=sc.name||\'\'; document.getElementById(\'eb_mode\').value=sc.mode||\'team\'; document.getElementById(\'eb_victory\').value=sc.victory||\'points\';\n  document.getElementById(\'eb_report\').value=(sc.report_min==null?\'\':sc.report_min); document.getElementById(\'eb_announce\').checked=(sc.announce!==false);\n  document.querySelectorAll(\'input.eb_pt\').forEach(function(e){ var tm=e.getAttribute(\'data-team\'), k=e.getAttribute(\'data-key\'); var tbl=tm?((sc.teams||{})[tm]||{}).points:(sc.points);\n    var v=tbl?tbl[k]:null; e.value=(v==null||typeof v===\'object\')?\'\':v; });\n  document.querySelectorAll(\'input.eb_obj\').forEach(function(e){ var tm=e.getAttribute(\'data-team\'); e.value=((sc.teams||{})[tm]||{}).objective||\'\'; });\n  document.querySelectorAll(\'#eb_sc tr\').forEach(function(tr,i){ if(i>0) tr.remove(); });\n  var p=sc.points||{}; var ids={}; [\'capture_specific\',\'hold_specific\',\'damage_specific\',\'supply_specific\'].forEach(function(k){ for(var sid in (p[k]||{})) ids[sid]=1; });\n  Object.keys(ids).forEach(function(sid){ ebAddScene({id:sid, cap:(p.capture_specific||{})[sid], hold:(p.hold_specific||{})[sid], dmg:(p.damage_specific||{})[sid], sup:(p.supply_specific||{})[sid]}); });\n  var o=(sc.objectives||[]).filter(function(x){return x.type===\'chute_on_target\';})[0];\n  document.getElementById(\'eb_pps_target\').value=o?o.target||\'\':\'\'; document.getElementById(\'eb_pps_radius\').value=o?(o.radius_m||\'\'):\'\';\n  document.getElementById(\'eb_pps_points\').value=o?(o.points||\'\'):\'\'; document.getElementById(\'eb_pps_teams\').value=o&&o.teams?o.teams.join(\',\'):\'\';\n  ebMsgsLoad(sc);\n  var f=(sc.objectives||[]).filter(function(x){return x.type===\'kill_target\';})[0];\n  document.getElementById(\'eb_fox_target\').value=f?f.target||\'\':\'\'; document.getElementById(\'eb_fox_points\').value=f?(f.points||\'\'):\'\';\n  document.getElementById(\'eb_fox_teams\').value=f&&f.teams?f.teams.join(\',\'):\'\';\n  if(!quiet) document.getElementById(\'eb_msg\').textContent=fromBox?\'form updated from the JSON box.\':\'form loaded from the JSON box.\';\n}\ndocument.addEventListener(\'DOMContentLoaded\', ebInit);\n</script>\n'

SRV = {
    'db_path': None,
    'get_existing_ticket': None,
    'generate_ticket': None,
    'exec_console': None,
    'log_dir': None,
    'date_read': None,
    'scoring_ref': None,
    'password_read': None,
    'reality_read': None,     # v948f5: extract_reality_from_gamedef(blob) -> {rw_*}
    'radar_read': None,       # v949f5: extract_radar_from_gamedef(blob) -> {rd_*}
    'tournament_read': None,  # v952f5: extract_tournament_from_gamedef(blob) -> {tn_*}
    'log': print
}

# Tag -> level inference for the web console. Mirrors fa_logging._level_for so the
# page can colour lines without fa_logging changing its (plain-string) return type.
_WEB_TAG_LEVELS = {
    'ERROR': 'ERROR', 'RELDROP': 'WARNING', 'STALL-WATCH': 'WARNING',
    'RX/DROP': 'WARNING', 'REAP': 'WARNING', 'DISPATCH': 'ERROR',
    'TX': 'DEBUG', 'RX': 'DEBUG', 'RELAY': 'DEBUG', 'SIM13': 'DEBUG',
    'GAMEDEF212': 'DEBUG', 'GDFDUMP': 'DEBUG', 'POST-AUTH': 'DEBUG',
    'COMPOUND': 'DEBUG', 'RELRX': 'DEBUG',
}
def _infer_level_from_line(line):
    # line looks like: [HH:MM:SS.mmm][TAG            ] message
    try:
        tag = line.split('][', 1)[1].split(']', 1)[0].strip()
    except Exception:
        return 'INFO'
    if tag in _WEB_TAG_LEVELS:
        return _WEB_TAG_LEVELS[tag]
    return _WEB_TAG_LEVELS.get(tag.split('/', 1)[0], 'INFO')

LOG_CONSOLE_PAGE = """
                <div class="nav"><a href="/admin">&larr; Back to Admin</a> |
                    <a href="/logout" style="color:#dc3545;">Logout</a></div>
                <h1 style="display:flex; align-items:center; gap:14px; flex-wrap:wrap;">Live Server Console
                  <span id="pcount" style="font-size:0.55em; font-weight:normal; background:#1e1e1e; color:#7ec97e;
                        border-radius:14px; padding:5px 14px; font-family:monospace;">players: &hellip;</span>
                  <span id="sver" style="font-size:0.55em; font-weight:normal; background:#1e1e1e; color:#e0c060;
                        border-radius:14px; padding:5px 14px; font-family:monospace;">server: &hellip;</span>
                </h1>
                <div class="card" style="padding:12px;">
                  <label>Min level:
                    <select id="lvl" onchange="reload()" autocomplete="off">
                      <option value="INFO" selected>INFO+</option>
                      <option value="DEBUG">DEBUG (all)</option>
                      <option value="WARNING">WARNING+</option>
                      <option value="ERROR">ERROR only</option>
                    </select>
                  </label>
                  &nbsp; <label><input type="checkbox" id="auto" checked onchange="toggle()"> Auto-refresh (2s)</label>
                  &nbsp; <button style="width:auto;padding:6px 12px;margin:0;" onclick="reload()">Refresh now</button>
                  &nbsp; <label>Filter: <input type="text" id="flt" oninput="render()" style="width:200px;padding:5px;margin:0;"></label>
                </div>
                <div class="card" style="padding:12px;">
                  <form method="POST" action="/admin/console_cmd" onsubmit="return sendCmd(event);"
                        style="display:flex; gap:8px; align-items:center; margin:0;">
                    <span style="font-family:monospace; font-weight:bold; color:#2a7;">&gt;</span>
                    <input type="text" id="cmd" name="cmd" autocomplete="off" spellcheck="false"
                           placeholder="server command (try: help)"
                           style="flex:1; padding:8px; margin:0; font-family:monospace;">
                    <button type="submit" class="btn-green" style="width:auto; padding:8px 18px; margin:0;">Run</button>
                  </form>
                  <small style="color:#888;">Runs on the server exactly as if typed at its terminal.
                    Output appears in the stream above (tagged CONSOLE). Up/Down = history.</small>
                </div>
                <div class="card" style="padding:12px; border-left:4px solid #ffc107;">
                  <div style="display:flex; gap:12px; align-items:center; flex-wrap:wrap;">
                    <button class="btn-yellow" style="width:auto; padding:9px 20px; margin:0;"
                            onclick="doUpdate();">&#8635; Update &amp; Restart</button>
                    <button style="width:auto; padding:9px 20px; margin:0; background:#6c757d;"
                            onclick="doRestart();">&#8635; Restart (no update)</button>
                    <label style="margin:0; white-space:nowrap;" title="10 s countdown in the arena and lobby, then every pilot is disconnected cleanly before the pull/restart. Untick for the hard way: no warning, everyone dropped by the restart.">
                      <input type="checkbox" id="grace" checked style="width:auto; margin:0 4px 0 0;"> Graceful (10 s countdown, drain pilots first)</label>
                    <small style="color:#666; flex:1; min-width:280px;">
                      <strong>Update &amp; Restart</strong> runs <code>git pull --ff-only</code> then
                      restarts (tagged <code>UPDATE</code>). <strong>Restart</strong> reboots the
                      <em>current</em> build with no pull (tagged <code>RESTART</code>) - use it to
                      clear state or recover a wedged server. Either way the server goes down for a
                      few seconds and players are disconnected, so do it between sessions; Restart
                      warns any players first.
                    </small>
                  </div>
                </div>
                <pre id="con" style="background:#1e1e1e;color:#ddd;padding:12px;border-radius:6px;height:62vh;overflow:auto;font-size:12px;line-height:1.4;white-space:pre-wrap;word-break:break-word;margin:0;"></pre>
                <script>
                var COLORS={DEBUG:"#888",INFO:"#ddd",WARNING:"#e6c07b",ERROR:"#e06c75"};
                var DATA=[];
                function esc(s){return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}
                function render(){
                  var flt=document.getElementById('flt').value.toLowerCase();
                  var con=document.getElementById('con');
                  var atBottom=con.scrollTop+con.clientHeight>=con.scrollHeight-30;
                  con.innerHTML=DATA.filter(function(d){return !flt||d.line.toLowerCase().indexOf(flt)>=0;})
                    .map(function(d){return '<span style="color:'+(COLORS[d.level]||"#ddd")+'">'+esc(d.line)+'</span>';})
                    .join("\\n");
                  if(atBottom) con.scrollTop=con.scrollHeight;
                }
                function reload(){
                  var lvl=document.getElementById('lvl').value;
                  fetch('/admin/logs.json?level='+lvl).then(function(r){return r.json();})
                    .then(function(j){DATA=j.lines;render();showCounts(j.players);showVer(j.version);}).catch(function(){});
                }
                function showVer(v){
                  var el=document.getElementById('sver');
                  if(el) el.textContent='server: '+(v||'n/a');
                }
                function showCounts(p){
                  var el=document.getElementById('pcount');
                  if(!el) return;
                  if(!p){ el.textContent='players: n/a'; el.style.color='#888'; return; }
                  el.style.color = p.connected>0 ? '#7ec97e' : '#888';
                  el.textContent = p.connected+' connected \\u00b7 '+p.in_arena+' in arena \\u00b7 '+p.flying+' flying';
                }
                var timer=null;
                function toggle(){var on=document.getElementById('auto').checked;
                  if(on){timer=setInterval(reload,2000);}else{if(timer)clearInterval(timer);timer=null;}}
                var HIST=[],HI=-1;
                function sendCmd(ev){
                  ev.preventDefault();
                  var box=document.getElementById('cmd');
                  var v=box.value.trim();
                  if(!v) return false;
                  HIST.push(v); HI=HIST.length;
                  box.value='';
                  fetch('/admin/console_cmd',{method:'POST',
                    headers:{'Content-Type':'application/x-www-form-urlencoded'},
                    body:'cmd='+encodeURIComponent(v)})
                    .then(function(){setTimeout(reload,250);})
                    .catch(function(){});
                  return false;
                }
                document.getElementById('cmd').addEventListener('keydown',function(e){
                  if(e.key==='ArrowUp'){ if(HI>0){HI--; this.value=HIST[HI];} e.preventDefault(); }
                  else if(e.key==='ArrowDown'){ if(HI<HIST.length-1){HI++; this.value=HIST[HI];}
                    else {HI=HIST.length; this.value='';} e.preventDefault(); }
                });
                function graceArg(){ var g=document.getElementById('grace'); return (g && g.checked) ? ' graceful' : ''; }
                function doUpdate(){
                  var g = graceArg();
                  if(!confirm('Update and restart the server?\\n\\n'
                    + '\\u2022 git pull --ff-only in the server directory\\n'
                    + '\\u2022 the server process restarts\\n'
                    + (g ? '\\u2022 GRACEFUL: 10 s countdown to every pilot, then a clean disconnect for all, then the pull\\n\\n'
                         : '\\u2022 HARD: ALL CONNECTED PLAYERS ARE DISCONNECTED without warning\\n\\n')
                    + 'The pull is aborted (and nothing restarts) if the working tree has\\n'
                    + 'local edits or the branches have diverged.')) return;
                  document.getElementById('auto').checked = true; toggle();
                  fetch('/admin/console_cmd',{method:'POST',
                    headers:{'Content-Type':'application/x-www-form-urlencoded'},
                    body:'cmd=update' + encodeURIComponent(g)})
                    .then(function(){setTimeout(reload,300);})
                    .catch(function(){});
                }
                function doRestart(){
                  var g = graceArg();
                  if(!confirm('Restart the CURRENT server build now?\\n\\n'
                    + '\\u2022 NO git pull - the running code is unchanged\\n'
                    + '\\u2022 the server process restarts\\n'
                    + (g ? '\\u2022 GRACEFUL: 10 s countdown to every pilot, then a clean disconnect for all\\n\\n'
                         : '\\u2022 HARD: ALL CONNECTED PLAYERS ARE DISCONNECTED (one warning line, 1.5 s)\\n\\n')
                    + 'Use this to clear state or recover a wedged server.')) return;
                  document.getElementById('auto').checked = true; toggle();
                  fetch('/admin/console_cmd',{method:'POST',
                    headers:{'Content-Type':'application/x-www-form-urlencoded'},
                    body:'cmd=restart' + encodeURIComponent(g)})
                    .then(function(){setTimeout(reload,300);})
                    .catch(function(){});
                }
                reload(); toggle();
                </script>
"""

# v318: tab chrome for the admin page. Kept as a PLAIN string (not an f-string) so the CSS and
# JS braces need no doubling - the admin page body is an f-string and mixing the two is how
# brace-escaping bugs get in.
# Structure: two top-level tabs (User Management | Arenas); User Management has two sub-tabs
# (Users | Pilot Stats). Every panel carries its own filter box that hides non-matching table
# rows client-side. The chosen tab is remembered so the POST-then-redirect-to-/admin cycle
# (rename, reset, create, save) returns you to the panel you were working in instead of
# bouncing back to Users every time.
ADMIN_TABS_ASSETS = """
<style>
  .tabbar { display:flex; gap:4px; border-bottom:2px solid #dee2e6; margin-bottom:0; }
  .tabbar button { width:auto; margin:0; border-radius:6px 6px 0 0; background:#e9ecef; color:#495057;
                   padding:11px 22px; font-size:1em; border:1px solid #dee2e6; border-bottom:none;
                   position:relative; top:2px; }
  .tabbar button:hover { background:#dde2e6; }
  .tabbar button.on { background:#fff; color:#0b5ed7; border-bottom:2px solid #fff; }
  .subbar { display:flex; gap:4px; margin:14px 0 0 0; }
  .subbar button { width:auto; margin:0; padding:7px 16px; font-size:0.9em; border-radius:14px;
                   background:#f1f3f5; color:#495057; border:1px solid #dee2e6; }
  .subbar button:hover { background:#e6e9ec; }
  .subbar button.on { background:#0d6efd; color:#fff; border-color:#0d6efd; }
  .panel { display:none; }
  .panel.on { display:block; }
  .filterbar { display:flex; align-items:center; gap:10px; margin:14px 0 6px; }
  .filterbar input { flex:1; padding:9px 12px; margin:0; border:1px solid #ccc; border-radius:4px; }
  .filtercount { color:#888; font-size:0.85em; white-space:nowrap; }
</style>
<script>
function faShow(group, id){
  var scope = document.querySelectorAll('[data-group="'+group+'"]');
  for (var i=0;i<scope.length;i++){
    var on = scope[i].getAttribute('data-panel')===id;
    scope[i].classList.toggle('on', on);
  }
  var btns = document.querySelectorAll('[data-btngroup="'+group+'"]');
  for (var j=0;j<btns.length;j++){
    btns[j].classList.toggle('on', btns[j].getAttribute('data-target')===id);
  }
  try { localStorage.setItem('fa_admin_'+group, id); } catch(e){}
}
function faFilter(inputEl){
  var tbl = document.getElementById(inputEl.getAttribute('data-table'));
  if(!tbl) return;
  var q = inputEl.value.toLowerCase();
  var rows = tbl.getElementsByTagName('tr');
  var shown = 0, total = 0;
  for (var i=0;i<rows.length;i++){
    var txt = (rows[i].textContent||'').toLowerCase();
    total++;
    var hit = !q || txt.indexOf(q) >= 0;
    rows[i].style.display = hit ? '' : 'none';
    if(hit) shown++;
  }
  var out = document.getElementById(inputEl.getAttribute('data-count'));
  if(out) out.textContent = q ? (shown + ' of ' + total) : (total + ' total');
}
document.addEventListener('DOMContentLoaded', function(){
  var groups = ['main','user'];
  for (var g=0; g<groups.length; g++){
    var saved = null;
    try { saved = localStorage.getItem('fa_admin_'+groups[g]); } catch(e){}
    var exists = saved && document.querySelector('[data-group="'+groups[g]+'"][data-panel="'+saved+'"]');
    if (exists) faShow(groups[g], saved);
  }
  var f = document.querySelectorAll('.filterbar input');
  for (var i=0;i<f.length;i++){ faFilter(f[i]); }
  faLoadLogs();
  faLoadStalls();
});
function faBytes(n){
  if(n < 1024) return n + ' B';
  if(n < 1048576) return (n/1024).toFixed(1) + ' KB';
  return (n/1048576).toFixed(1) + ' MB';
}
function faFileList(url, src, tblId, dirId, sumId, fltId){
  // v418f5: one loader for both file tabs (run logs + stall dumps). `src` is appended to the
  // view/download links so the server resolves the name against the matching root.
  var tb = document.getElementById(tblId);
  if(!tb) return;
  tb.innerHTML = '<tr><td>Loading&hellip;</td></tr>';
  var extra = src ? '&src=' + src : '';
  fetch(url).then(function(r){return r.json();}).then(function(j){
    var d = document.getElementById(dirId);
    if(d) d.textContent = j.dir || '(directory not available)';
    if(!j.files || !j.files.length){
      tb.innerHTML = '<tr><td>' + (src==='stall'
        ? 'No stall dumps - STALL-WATCH has not fired this run.'
        : 'No log files found.') + '</td></tr>';
      var s0 = document.getElementById(sumId);
      if(s0) s0.textContent = '0 files';
      return;
    }
    var total = 0, html = '';
    for(var i=0;i<j.files.length;i++){
      var f = j.files[i];
      total += f.size;
      var when = new Date(f.mtime*1000).toLocaleString();
      var q = encodeURIComponent(f.name);
      html += '<tr><td><strong>' + f.name + '</strong><br>'
            + '<small style="color:#666;">' + faBytes(f.size) + ' &middot; ' + when + '</small></td>'
            + '<td style="text-align:right; white-space:nowrap;">'
            + '<a class="btn-green" style="display:inline-block;width:auto;padding:7px 13px;'
            + 'margin:0 6px 0 0;text-decoration:none;" href="/admin/log_view?name=' + q + extra + '">View tail</a>'
            + '<a class="btn-yellow" style="display:inline-block;width:auto;padding:7px 13px;'
            + 'margin:0;text-decoration:none;color:#333;" href="/admin/log_download?name=' + q + extra + '">Download</a>'
            + '</td></tr>';
    }
    tb.innerHTML = html;
    var s = document.getElementById(sumId);
    if(s) s.textContent = j.files.length + ' files, ' + faBytes(total) + ' total';
    var fb = document.getElementById(fltId);
    if(fb) faFilter(fb);
  }).catch(function(e){
    tb.innerHTML = '<tr><td style="color:#c00;">Could not load the file list.</td></tr>';
  });
}
function faLoadLogs(){
  faFileList('/admin/logfiles.json', '', 'logsTable', 'logsDir', 'logsSummary', 'logsFilter');
}
function faLoadStalls(){
  faFileList('/admin/stallfiles.json', 'stall', 'stallsTable', 'stallsDir', 'stallsSummary', 'stallsFilter');
}
</script>
"""

# v405f5: ladder tab chrome + behaviour. PLAIN string (not an f-string) - the ladder page body
# is an f-string and CSS/JS braces inside one need doubling; keeping this separate means the
# braces pass through untouched (same reasoning as ADMIN_TABS_ASSETS above).
LADDER_TABS_ASSETS = """
                <style>
                  .lbar { display:flex; gap:6px; padding:15px 15px 0; }
                  .ltab { width:auto; margin:0; padding:8px 18px; font-size:0.95em; border-radius:14px;
                          background:#f1f3f5; color:#495057; border:1px solid #dee2e6; }
                  .ltab:hover { background:#e6e9ec; }
                  .ltab.lon { background:#0d6efd; color:#fff; border-color:#0d6efd; }
                  /* v713f5: the Squadrons board grew to 13 columns - keep it inside the card:
                     the panel scrolls sideways, cells stay on one line at a slightly smaller size */
                  .lpanel { overflow-x:auto; }
                  .lpanel table { width:100%; min-width:100%; }
                  #lsqn, #lcareer, #ltc { font-size:0.9em; }
                  #lsqn th, #lsqn td, #lcareer th, #lcareer td, #ltc th, #ltc td { white-space:nowrap; padding:6px 8px; }
                </style>
                <script>
                function lshow(tid){
                  /* v545f5: panels discovered from the DOM (was a hardcoded id list, which left any
                     newer tab - e.g. Squadrons - permanently hidden: lshow hid all listed panels
                     and never showed the unlisted one -> blank page). */
                  var ps=document.querySelectorAll('.lpanel');
                  for(var i=0;i<ps.length;i++){
                    var id=ps[i].id.substring(4);   /* strip 'pan-' */
                    ps[i].style.display=(id===tid)?'block':'none';
                    var b=document.getElementById('btn-'+id);
                    if(b) b.classList.toggle('lon', id===tid);
                  }
                  try{localStorage.setItem('fa_ladder_tab',tid);}catch(e){}
                  var s=document.getElementById('searchInput');
                  if(s) lfilter(s.value);
                }
                function lfilter(q){
                  q=(q||'').toLowerCase();
                  var rows=document.querySelectorAll('.lpanel tbody tr');
                  for(var i=0;i<rows.length;i++){
                    var name=rows[i].cells[1].textContent.toLowerCase();
                    rows[i].style.display=(!q||name.indexOf(q)>=0)?'':'none';
                  }
                }
                document.getElementById('searchInput').addEventListener('keyup',function(){lfilter(this.value);});
                function sortLadder(tid,n){
                  var table, rows, switching, i, x, y, shouldSwitch, dir, switchcount = 0;
                  table = document.getElementById(tid);
                  if(!table) return;
                  switching = true;
                  dir = "asc";
                  while (switching) {
                    switching = false;
                    rows = table.rows;
                    for (i = 1; i < (rows.length - 1); i++) {
                      shouldSwitch = false;
                      x = rows[i].getElementsByTagName("TD")[n];
                      y = rows[i + 1].getElementsByTagName("TD")[n];
                      var valX = isNaN(parseFloat(x.innerHTML)) ? x.innerHTML.toLowerCase() : parseFloat(x.innerHTML);
                      var valY = isNaN(parseFloat(y.innerHTML)) ? y.innerHTML.toLowerCase() : parseFloat(y.innerHTML);
                      if (dir == "asc") {
                        if (valX > valY) { shouldSwitch = true; break; }
                      } else if (dir == "desc") {
                        if (valX < valY) { shouldSwitch = true; break; }
                      }
                    }
                    if (shouldSwitch) {
                      rows[i].parentNode.insertBefore(rows[i + 1], rows[i]);
                      switching = true;
                      switchcount++;
                    } else {
                      if (switchcount == 0 && dir == "asc") {
                        dir = "desc";
                        switching = true;
                      }
                    }
                  }
                }
                (function(){
                  var saved=null;
                  try{saved=localStorage.getItem('fa_ladder_tab');}catch(e){}
                  if(saved&&document.getElementById('pan-'+saved)) lshow(saved);
                })();
                </script>
"""

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def _connect():
    """Open a SQLite connection with a busy timeout. Now that the web server is threaded, several
    requests can hit the DB at once; a 5s busy_timeout makes a writer wait for a concurrent write
    to finish instead of immediately raising 'database is locked'. check_same_thread=False is safe
    here because each connection is created, used, and closed within a single request handler (we
    never share one connection across threads)."""
    conn = sqlite3.connect(SRV['db_path'], timeout=5.0, check_same_thread=False)
    try:
        conn.execute('PRAGMA busy_timeout=5000')
    except Exception:
        pass
    return conn

def migrate_web_db():
    conn = sqlite3.connect(SRV['db_path'])
    c = conn.cursor()
    c.execute("PRAGMA table_info(accounts)")
    columns = [row[1] for row in c.fetchall()]
    
    if 'web_password' not in columns:
        c.execute("ALTER TABLE accounts ADD COLUMN web_password TEXT")
    if 'client_path' not in columns:
        c.execute("ALTER TABLE accounts ADD COLUMN client_path TEXT")
    if 'is_admin' not in columns:
        c.execute("ALTER TABLE accounts ADD COLUMN is_admin INTEGER DEFAULT 0")
        
    c.execute("UPDATE accounts SET is_admin=1 WHERE account_name='admin'")

    # Arena (room) section-header / category column, editable from the admin Arena
    # Management panel. Default 'Custom Arenas' matches the game server's prior hardcoded
    # value. The game server's init_rooms_db adds this too; harmless if already present.
    try:
        rcols = [row[1] for row in c.execute("PRAGMA table_info(rooms)").fetchall()]
        if rcols and 'category' not in rcols:
            c.execute("ALTER TABLE rooms ADD COLUMN category TEXT NOT NULL DEFAULT 'Custom Arenas'")
        if rcols and 'persistent' not in rcols:
            # v475: cleanup-exemption flag, set from the arena-management checkbox. The game
            # server's init_rooms_db adds this too; harmless if already present.
            c.execute("ALTER TABLE rooms ADD COLUMN persistent INTEGER NOT NULL DEFAULT 0")
        if rcols and 'password_protected' not in rcols:
            # Denormalised lock-icon flag for the arena list. The game server's init_rooms_db
            # adds AND backfills this from the stored blobs; here we only ensure the column
            # exists (default 0) in case the web server reaches the DB first. Harmless if present.
            c.execute("ALTER TABLE rooms ADD COLUMN password_protected INTEGER NOT NULL DEFAULT 0")
    except Exception:
        pass

    conn.commit()
    conn.close()
    SRV['log']('WEB', 'Database schema verified for web login and admin roles.')

def is_user_admin(username):
    if not username: return False
    try:
        conn = sqlite3.connect(SRV['db_path'])
        res = conn.execute("SELECT is_admin FROM accounts WHERE account_name=?", (username,)).fetchone()
        conn.close()
        return res and res[0] == 1
    except:
        return False

# v464 read-only log access for diagnostics tooling: the four LOG endpoints (logs.json,
# logfiles.json, log_view, log_download) accept EITHER an admin session OR ?key=<LOG_READ_TOKEN>.
# Read-only and log-scoped - account/settings/moderation endpoints remain strictly
# admin-session.
# 2026-09-29 SECURITY: the token used to be a constant HERE, and the repo is public - anyone
# reading the source could pull every live/archived log (player IPs, account names, typed
# squadron passwords). The old token is burned (it stays in git history forever). The token
# now lives in log_token.txt next to this file (gitignored) or the file named by the env var
# FA_LOG_TOKEN_FILE; >=32 chars. No file = token access DISABLED, admin sessions still work.
# Rotate: write a new token into the file and restart the web portion.
#   python3 -c "import secrets;print(secrets.token_hex(24))" > log_token.txt
def _load_log_token():
    p = (os.environ.get('FA_LOG_TOKEN_FILE')
         or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'log_token.txt'))
    try:
        with open(p, encoding='ascii') as f:
            t = f.read().strip()
        return t if len(t) >= 32 else None
    except (OSError, UnicodeDecodeError):
        return None

LOG_READ_TOKEN = _load_log_token()

# 2026-09-29 SECURITY [WEBACCESS]: who read the logs, and how. The HTTP layer's log_message is
# silenced and WEBPERF never had a client address, so 'was that poll us or an outsider?' was
# unanswerable. One line per (ip, method, user) per WEBACCESS_QUIET_S - an open Live Console
# polling every 2s costs one line per 10 min, not a flood. BAD-TOKEN = a wrong ?key= (probing).
WEBACCESS_QUIET_S = 600
_ACCESS_SEEN = {}
_ACCESS_LOCK = threading.Lock()

def _log_access(handler, user, via):
    try:
        ip = handler.client_address[0]
        k, now = (ip, via, user), time.time()
        with _ACCESS_LOCK:
            if now - _ACCESS_SEEN.get(k, 0) < WEBACCESS_QUIET_S:
                return
            _ACCESS_SEEN[k] = now
            if len(_ACCESS_SEEN) > 4096:            # scanner churn: drop stale keys
                for kk in [kk for kk, t in _ACCESS_SEEN.items() if now - t > WEBACCESS_QUIET_S]:
                    _ACCESS_SEEN.pop(kk, None)
        ua = (handler.headers.get('User-Agent') or '')[:80]
        SRV['log']('WEBACCESS', f'{handler.path.split("?")[0]} by {user or "-"} '
                                f'via {via} from {ip} ua={ua!r}')
    except Exception:
        pass

def _log_read_ok(handler, user):
    if is_user_admin(user):
        _log_access(handler, user, 'session')
        return True
    try:
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(handler.path).query)
        key = qs.get('key', [''])[0]
    except Exception:
        key = ''
    if not key:
        return False
    if LOG_READ_TOKEN and hmac.compare_digest(key.encode('utf-8', 'replace'),
                                              LOG_READ_TOKEN.encode('ascii')):
        _log_access(handler, user, 'token')
        return True
    _log_access(handler, user, 'BAD-TOKEN')
    return False

def arena_owner_account(room_id):
    """Return the account_name that created a room, or '' if unknown."""
    try:
        conn = sqlite3.connect(SRV['db_path'])
        rcols = [r[1] for r in conn.execute("PRAGMA table_info(rooms)").fetchall()]
        if 'account_name' not in rcols:
            conn.close(); return ''
        row = conn.execute("SELECT COALESCE(account_name,'') FROM rooms WHERE room_id=?", (room_id,)).fetchone()
        conn.close()
        return (row[0] if row else '') or ''
    except Exception:
        return ''

def user_can_edit_arena(username, room_id):
    """A user may edit an arena if they are an admin OR they created it (account match)."""
    if not username:
        return False
    if is_user_admin(username):
        return True
    return arena_owner_account(room_id) == username

# --- v317: NAME VALIDATION ----------------------------------------------------
# There is NO character restriction on pilot names anywhere in the game server - the limits
# people hit are enforced by the CLIENT's own name-entry box. Names travel the wire as
# NUL-terminated ASCII inside fixed 32-byte fields, so the only things that genuinely break are:
#   * a NUL or any control byte (terminates the string early / trips the client's text parser,
#     which is what the "Wrong char 13, pos 1" errors look like)
#   * non-ASCII (the fields are ASCII; the client renders bytes >0x7e as garbage)
#   * more than 31 characters (32 minus the terminator)
# Everything else printable is fine, which is exactly what lets an admin create the reserved
# looking staff names - @HQ, @FA, @INSTRUCTOR, @HELP - and use @ * # ! and spaces.
NAME_MAX = 31

def _valid_name(name):
    """Return (ok, cleaned_or_error). Accepts printable ASCII 0x20..0x7e, 1..31 chars."""
    if name is None:
        return False, 'Name is empty.'
    # Only trim the outer edges - interior spaces are legal and intentional ("@FA Instructor").
    n = name.strip()
    if not n:
        return False, 'Name is empty.'
    if len(n) > NAME_MAX:
        return False, f'Name is {len(n)} characters; the wire field holds {NAME_MAX}.'
    bad = sorted({c for c in n if not (0x20 <= ord(c) <= 0x7e)})
    if bad:
        shown = ', '.join(f'0x{ord(c):02x}' for c in bad)
        return False, ('Name contains bytes that are not printable ASCII (' + shown +
                       '). Control bytes terminate the name field and corrupt the client parse.')
    return True, n

def _name_taken(conn, table, column, name):
    row = conn.execute(f"SELECT 1 FROM {table} WHERE {column}=? COLLATE NOCASE", (name,)).fetchone()
    return row is not None

# Every place a name is stored. The DB has NO foreign keys, so a rename must touch all of these
# in one transaction or the pilot's stats / arenas silently orphan.
ACCOUNT_REFS = [('accounts', 'account_name'), ('pilots', 'account_name'),
                ('room_players', 'account_name'), ('rooms', 'account_name')]
PILOT_REFS   = [('pilots', 'pilot_name'), ('room_players', 'pilot_name'),
                ('rooms', 'creator_pilot')]

def _rename_everywhere(conn, refs, old, new):
    """Apply a rename across every (table, column) that exists in this DB. Returns a report."""
    done = []
    for table, col in refs:
        try:
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            if not cols or col not in cols:
                continue
            cur = conn.execute(f"UPDATE {table} SET {col}=? WHERE {col}=?", (new, old))
            if cur.rowcount:
                done.append(f'{table}.{col}x{cur.rowcount}')
        except Exception as e:
            done.append(f'{table}.{col}:ERR({e})')
    return done

# --- v321: LOG FILE ACCESS -----------------------------------------------------
# Serving files off disk over HTTP is the one genuinely dangerous thing this admin panel
# does, so the path handling is deliberately paranoid. A request only ever supplies a BARE
# FILENAME; the directory comes from the server, never from the client.
#
# Four independent checks, any one of which is sufficient on its own:
#   1. basename(name) == name  -> kills 'a/b', 'a\b', and anything with a separator
#   2. reject ':' and NUL      -> kills Windows drive-relative paths ('C:..\x') and NTFS
#                                 alternate data streams ('server.log:hidden')
#   3. extension allowlist     -> only .log / .log.<n> / .txt / .err are downloadable
#   4. realpath containment    -> resolves symlinks/junctions and proves the final path is
#                                 genuinely inside the logs directory
# Plus: it must exist and be a regular file (never a directory or device node).
LOG_NAME_OK = re.compile(r'^[A-Za-z0-9._-]+$')
LOG_EXT_OK  = re.compile(r'\.(log(\.\d+)?|txt|err)$', re.IGNORECASE)

def _log_dir():
    d = SRV.get('log_dir')
    return d if d and os.path.isdir(d) else None

def _safe_log_path(name):
    """Map a client-supplied filename to an absolute path inside the logs dir, or None."""
    d = _log_dir()
    if not d or not name:
        return None
    if '\x00' in name or ':' in name:
        return None
    if os.path.basename(name) != name:          # any separator, '.' or '..'
        return None
    if name in ('.', '..') or not LOG_NAME_OK.match(name):
        return None
    if not LOG_EXT_OK.search(name):
        return None
    full = os.path.realpath(os.path.join(d, name))
    root = os.path.realpath(d)
    try:
        if os.path.commonpath([root, full]) != root:
            return None
    except ValueError:                          # different drives on Windows
        return None
    if not os.path.isfile(full):
        return None
    return full

def _stall_dir():
    # v418f5: logs/flightrec - the STALL-WATCH flight-recorder dumps. Kept as its own root
    # (never reachable through _safe_log_path) so the v321 guarantee still holds exactly:
    # each download root is one flat directory, bare filenames only, zero traversal surface.
    d = _log_dir()
    if not d:
        return None
    fr = os.path.join(d, 'flightrec')
    return fr if os.path.isdir(fr) else None

def _safe_stall_path(name):
    """v418f5: _safe_log_path with the root swapped to logs/flightrec/. Same four
    independent checks; dump names are pre-sanitized by the recorder to [A-Za-z0-9_.-]
    (<pilot>_<ts>.log) so every legitimate dump passes and nothing else does."""
    d = _stall_dir()
    if not d or not name:
        return None
    if '\x00' in name or ':' in name:
        return None
    if os.path.basename(name) != name:
        return None
    if name in ('.', '..') or not LOG_NAME_OK.match(name):
        return None
    if not LOG_EXT_OK.search(name):
        return None
    full = os.path.realpath(os.path.join(d, name))
    root = os.path.realpath(d)
    try:
        if os.path.commonpath([root, full]) != root:
            return None
    except ValueError:
        return None
    if not os.path.isfile(full):
        return None
    return full

def _list_stall_files():
    """v418f5: [{name,size,mtime}] for logs/flightrec/, newest first - filtered through
    _safe_stall_path exactly as the run-log list is through _safe_log_path."""
    d = _stall_dir()
    if not d:
        return []
    out = []
    try:
        for nm in os.listdir(d):
            p = _safe_stall_path(nm)
            if not p:
                continue
            try:
                st = os.stat(p)
            except OSError:
                continue
            out.append({'name': nm, 'size': st.st_size, 'mtime': st.st_mtime})
    except OSError as e:
        SRV['log']('WEB', f'stall listing failed: {e!r}')
        return []
    out.sort(key=lambda r: r['mtime'], reverse=True)
    return out

def _list_log_files():
    """[{name,size,mtime}] for every downloadable file in the logs dir, newest first.
    Sub-directories (e.g. flightrec/) are intentionally NOT traversed - one flat directory
    keeps the traversal surface at exactly zero."""
    d = _log_dir()
    if not d:
        return []
    out = []
    try:
        for nm in os.listdir(d):
            # Filter with the SAME function that guards the download, so the list can never
            # show an entry that would then 404 - e.g. a symlink/junction pointing outside
            # the logs dir passes the name checks but fails realpath containment.
            p = _safe_log_path(nm)
            if not p:
                continue
            try:
                st = os.stat(p)
            except OSError:
                continue
            out.append({'name': nm, 'size': st.st_size, 'mtime': st.st_mtime})
    except OSError as e:
        SRV['log']('WEB', f'log listing failed: {e!r}')
        return []
    out.sort(key=lambda r: r['mtime'], reverse=True)
    return out

def _scoring_ref():
    """v404f5: the game server's live scoring tables (ranks/planes/AI/events), or None if the
    server build predates the injection. A callable so the page always reflects the constants
    actually in force, never a stale copy."""
    fn = SRV.get('scoring_ref')
    if not fn:
        return None
    try:
        return fn() or None
    except Exception:
        return None

def _rank_name_for_score(ref, score):
    """Map a career score to its rank name using the injected ladder; '' if unavailable."""
    try:
        name = ''
        for r in ref['ranks']:
            if score >= r['lo']:
                name = r['name']
        return name
    except Exception:
        return ''

# =============================================================================
# 2026-09-30: /auth - login API for the game WEBSITE / forum (a separate site).
#   The website checks a player's login against THIS server's accounts table and gets back an
#   authorization token plus the pilots on that account. Nothing here touches the admin panel:
#   the token is NOT a 'session' cookie and opens no /admin or dashboard page.
#
#   POST /auth      Content-Type: application/json
#                   {"account_name": "...", "password": "..."}
#     200 {"ok": true, "account": "...", "is_admin": false,
#          "authorization": {"type": "Bearer", "token": "...", "expires_in": 43200,
#                            "expires_at": 1790000000},
#          "pilots": [{"pilot_name", "rank", "squadron", "score", "bomber_score",
#                      "total_score", "kills", "deaths", "slot"}, ...]}
#     401 {"ok": false, "error": "invalid_credentials"}   (same answer for 'no such account',
#                                                          'no web password' and 'wrong password')
#   GET /auth       Authorization: Bearer <token>
#     200 the same body without a new token (pilots re-read from the DB) / 401 invalid_token
#   OPTIONS /auth   CORS preflight for a browser calling from an approved site.
#
#   WHO MAY CALL (fail-closed: no auth_domains.txt, or an empty one = the endpoint answers 403):
#     auth_domains.txt next to this file, one entry per line, '#' comments. An entry is a host
#     name (forum.example.com), a wildcard (*.example.com = any sub-domain, not the bare
#     domain) or a literal IP. The file is re-read when it changes - no restart needed.
#       * a request WITH an Origin header (a browser): the Origin's host must be listed and
#         the scheme must be https (http is accepted for localhost / 127.0.0.1 only). The
#         reply then carries Access-Control-Allow-Origin for exactly that origin.
#       * a request WITHOUT Origin (the website's own backend): the caller's IP must be a
#         listed IP or one of the addresses a listed host name resolves to (cached 5 min).
#     Origin is a BROWSER rule: it stops other websites' pages from using the endpoint, but a
#     script can type any Origin it likes. What actually stops password guessing is the limiter
#     below, and - for a backend-only integration - the optional shared key:
#     auth_api_key.txt (>=32 chars, keep it out of git). When that file exists every POST/GET
#     must also send 'X-Auth-Key: <key>'. Do not use the key from browser JavaScript.
#
#   CREDENTIALS IN TRANSIT: JSON body only (never the URL - URLs end up in logs), refused over
#   plain HTTP unless the caller is loopback, body capped at 4 KB, never logged.
#   LIMITER: 8 failed logins per account and (browser path) 30 per IP in 10 minutes -> 429
#   with Retry-After. The per-IP bucket is skipped on the backend path, where every player's
#   login arrives from the website's one address.
#   TOKENS live in memory (12 h): a process restart logs website users out, nothing else.
# =============================================================================
AUTH_DOMAINS_FILE  = os.path.join(_WEB_DIR, 'auth_domains.txt')
AUTH_KEY_FILE      = os.path.join(_WEB_DIR, 'auth_api_key.txt')
AUTH_TOKEN_TTL_S   = 12 * 3600
AUTH_MAX_BODY      = 4096
AUTH_FAIL_WINDOW_S = 600
AUTH_FAIL_MAX_ACCT = 8
AUTH_FAIL_MAX_IP   = 30
AUTH_DNS_TTL_S     = 300
AUTH_REQUIRE_TLS   = True

_AUTH_LOCK   = threading.Lock()
_AUTH_CFG    = {'loaded': False, 'mtime': None, 'hosts': frozenset(), 'wild': (),
                'key_mtime': None, 'key': None}
_AUTH_DNS    = {}     # host -> (expires, {ip, ...})
_AUTH_TOKENS = {}     # token -> (account_name, expires)
_AUTH_FAILS  = {}     # ('acct'|'ip', value) -> [failure timestamps]
_AUTH_QUIET  = {}     # (ip, why) -> last time a denial was logged

def _auth_config():
    """-> (hosts frozenset, wildcard suffixes tuple, api key or None). Both files are re-read
    whenever their mtime changes, so the allowlist can be edited on a live server."""
    def _mt(p):
        try:
            return os.path.getmtime(p)
        except OSError:
            return None
    dm, km = _mt(AUTH_DOMAINS_FILE), _mt(AUTH_KEY_FILE)
    with _AUTH_LOCK:
        c = _AUTH_CFG
        if not c['loaded'] or dm != c['mtime']:
            hosts, wild = set(), []
            if dm is not None:
                try:
                    with open(AUTH_DOMAINS_FILE, encoding='utf-8') as f:
                        for line in f:
                            e = line.split('#', 1)[0].strip().lower()
                            if not e:
                                continue
                            if '://' in e:                  # tolerate a pasted URL
                                e = e.split('://', 1)[1]
                            e = e.split('/', 1)[0].rstrip('.')
                            if e.count(':') == 1:           # host:port (leave IPv6 literals alone)
                                e = e.split(':', 1)[0]
                            if e.startswith('*.') and len(e) > 2:
                                wild.append(e[1:])          # '.example.com'
                            elif e and '*' not in e:
                                hosts.add(e)
                except (OSError, UnicodeDecodeError):
                    hosts, wild = set(), []
            c['hosts'], c['wild'], c['mtime'] = frozenset(hosts), tuple(wild), dm
            _AUTH_DNS.clear()
        if not c['loaded'] or km != c['key_mtime']:
            key = None
            if km is not None:
                try:
                    with open(AUTH_KEY_FILE, encoding='ascii') as f:
                        key = f.read().strip()
                except (OSError, UnicodeDecodeError):
                    key = None
                if key is not None and len(key) < 32:
                    key = ''            # file present but unusable: '' can never match = locked
            c['key'], c['key_mtime'] = key, km
        c['loaded'] = True
        return c['hosts'], c['wild'], c['key']

def _auth_client_ip(handler):
    ip = handler.client_address[0]
    return ip[7:] if ip.startswith('::ffff:') else ip

def _auth_domain_ips(hosts):
    """Addresses the listed host names resolve to right now (5-minute cache per name). A failed
    lookup keeps the previous answer, so a DNS blip does not lock the website out."""
    now, out = time.time(), set()
    for h in hosts:
        ent = _AUTH_DNS.get(h)
        if ent is None or ent[0] < now:
            try:
                ips = {ai[4][0] for ai in socket.getaddrinfo(h, None)}
            except (OSError, UnicodeError):
                ips = ent[1] if ent else set()
            ent = (now + AUTH_DNS_TTL_S, ips)
            _AUTH_DNS[h] = ent
        out |= ent[1]
    return out

def _auth_gate(handler, need_key=True):
    """The approved-domains check. -> (ok, cors_origin or None, via, why)."""
    hosts, wild, key = _auth_config()
    ip = _auth_client_ip(handler)
    if AUTH_REQUIRE_TLS and not isinstance(handler.connection, ssl.SSLSocket) \
            and ip not in ('127.0.0.1', '::1'):
        return False, None, '', 'https_required'
    if not hosts and not wild:
        return False, None, '', 'no_allowlist'
    origin = (handler.headers.get('Origin') or '').strip()
    if origin:
        via, cors = 'origin', None
        try:
            u = urllib.parse.urlsplit(origin)
            host = (u.hostname or '').lower().rstrip('.')
            scheme = u.scheme.lower()
        except ValueError:
            host, scheme = '', ''
        local = host in ('localhost', '127.0.0.1')
        if host and (scheme == 'https' or (scheme == 'http' and local)) \
                and (host in hosts or any(host.endswith(s) for s in wild)):
            cors = origin
        if cors is None:
            return False, None, via, 'origin_not_approved'
    else:
        via, cors = 'ip', None
        if ip not in hosts and ip not in _auth_domain_ips(hosts):
            return False, None, via, 'address_not_approved'
    if need_key and key is not None:
        got = handler.headers.get('X-Auth-Key') or ''
        if not key or not hmac.compare_digest(got.encode('utf-8', 'replace'),
                                              key.encode('ascii')):
            return False, cors, via, 'bad_api_key'
    return True, cors, via, ''

def _auth_send(handler, code, obj, origin=None, headers=()):
    body = json.dumps(obj).encode('utf-8') if obj is not None else b''
    handler._perf_ready = time.time()
    handler.send_response(code)
    if body:
        handler.send_header('Content-Type', 'application/json; charset=utf-8')
    handler.send_header('Content-Length', str(len(body)))
    handler.send_header('Cache-Control', 'no-store')
    handler.send_header('Vary', 'Origin')
    if origin:
        handler.send_header('Access-Control-Allow-Origin', origin)
    for k, v in headers:
        handler.send_header(k, v)
    handler.end_headers()
    if body:
        handler.wfile.write(body)

def _auth_deny(handler, via, why, origin=None):
    """403 for a caller that fails the gate. One log line per (ip, reason) per 10 minutes."""
    try:
        ip, now = _auth_client_ip(handler), time.time()
        with _AUTH_LOCK:
            quiet = now - _AUTH_QUIET.get((ip, why), 0) < WEBACCESS_QUIET_S
            if not quiet:
                _AUTH_QUIET[(ip, why)] = now
                if len(_AUTH_QUIET) > 4096:
                    for k in [k for k, t in _AUTH_QUIET.items() if now - t > WEBACCESS_QUIET_S]:
                        _AUTH_QUIET.pop(k, None)
        if not quiet:
            SRV['log']('WEBAUTH', f'DENIED {why} from {ip} via {via or "-"} '
                                  f'origin={(handler.headers.get("Origin") or "")[:80]!r} '
                                  f'ua={(handler.headers.get("User-Agent") or "")[:80]!r}')
    except Exception:
        pass
    _auth_send(handler, 403, {'ok': False, 'error': why}, origin)

def _auth_limited(key, limit):
    """Seconds until this bucket may try again, 0 if it is not limited."""
    now = time.time()
    with _AUTH_LOCK:
        ts = [t for t in _AUTH_FAILS.get(key, ()) if now - t < AUTH_FAIL_WINDOW_S]
        if ts:
            _AUTH_FAILS[key] = ts
        else:
            _AUTH_FAILS.pop(key, None)
        if len(ts) >= limit:
            return max(1, int(AUTH_FAIL_WINDOW_S - (now - ts[0])) + 1)
    return 0

def _auth_note_fail(key):
    now = time.time()
    with _AUTH_LOCK:
        _AUTH_FAILS.setdefault(key, []).append(now)
        if len(_AUTH_FAILS) > 4096:             # guessing churn: drop buckets that have expired
            for k in [k for k, ts in _AUTH_FAILS.items()
                      if not ts or now - ts[-1] > AUTH_FAIL_WINDOW_S]:
                _AUTH_FAILS.pop(k, None)

def _auth_account_view(acct):
    """(canonical account name, is_admin, pilots list) for the reply, or None if the account
    is gone. Columns are guarded like the ladder's, so an un-migrated DB still answers."""
    conn = _connect()
    try:
        row = conn.execute("SELECT account_name, COALESCE(is_admin,0) FROM accounts "
                           "WHERE account_name=?", (acct,)).fetchone()
        if not row:
            return None
        pcols = [r[1] for r in conn.execute("PRAGMA table_info(pilots)").fetchall()]
        def _gc(col, dflt='0'):
            return ("COALESCE(" + col + "," + dflt + ")") if col in pcols else dflt
        rows = conn.execute(
            "SELECT pilot_name, " + _gc('score') + ", " + _gc('bomber_score') + ", "
            + _gc('kills') + ", " + _gc('deaths') + ", " + _gc('squadron', "''") + ", "
            + _gc('slot_index') + " FROM pilots WHERE account_name=? "
            "ORDER BY 7, pilot_name", (row[0],)).fetchall()
    finally:
        conn.close()
    ref = _scoring_ref()
    pilots = []
    for name, f_score, b_score, kills, deaths, sq, slot in rows:
        total = (f_score or 0) + (b_score or 0)
        pilots.append({'pilot_name': name,
                       'rank': _rank_name_for_score(ref, total) if ref else '',
                       'squadron': sq or '',
                       'score': f_score or 0, 'bomber_score': b_score or 0,
                       'total_score': total, 'kills': kills or 0, 'deaths': deaths or 0,
                       'slot': slot or 0})
    return row[0], bool(row[1]), pilots

def _auth_handle_options(handler):
    if handler.path.split('?')[0] != '/auth':
        return handler.send_error(404)
    ok, origin, via, why = _auth_gate(handler, need_key=False)   # a preflight carries no key
    if not ok or not origin:
        return _auth_deny(handler, via, why or 'origin_required')
    _auth_send(handler, 204, None, origin, (
        ('Access-Control-Allow-Methods', 'POST, GET, OPTIONS'),
        ('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Auth-Key'),
        ('Access-Control-Max-Age', '600')))

def _auth_handle_get(handler):
    """Token check: Authorization: Bearer <token> -> the account and its current pilots."""
    ok, origin, via, why = _auth_gate(handler)
    if not ok:
        return _auth_deny(handler, via, why, origin)
    hdr = (handler.headers.get('Authorization') or '').strip()
    token = hdr[7:].strip() if hdr[:7].lower() == 'bearer ' else ''
    now = time.time()
    with _AUTH_LOCK:
        ent = _AUTH_TOKENS.get(token) if token else None
        if ent and ent[1] <= now:
            _AUTH_TOKENS.pop(token, None)
            ent = None
    view = _auth_account_view(ent[0]) if ent else None
    if not view:
        return _auth_send(handler, 401, {'ok': False, 'error': 'invalid_token'}, origin)
    _auth_send(handler, 200, {'ok': True, 'account': view[0], 'is_admin': view[1],
                              'expires_in': int(ent[1] - now), 'expires_at': int(ent[1]),
                              'pilots': view[2]}, origin)

def _auth_handle_post(handler):
    """Login: JSON {account_name, password} -> authorization token + pilots."""
    ok, origin, via, why = _auth_gate(handler)
    if not ok:
        return _auth_deny(handler, via, why, origin)
    def _bad(code, err, headers=()):
        _auth_send(handler, code, {'ok': False, 'error': err}, origin, headers)
    # JSON only: a cross-site HTML form cannot send this content type, and it forces a browser
    # to preflight, so a page on an unapproved site never gets its POST through.
    if (handler.headers.get('Content-Type') or '').split(';')[0].strip().lower() != 'application/json':
        return _bad(415, 'json_required')
    try:
        n = int(handler.headers.get('Content-Length') or 0)
    except ValueError:
        n = 0
    if n <= 0:
        return _bad(400, 'bad_request')
    if n > AUTH_MAX_BODY:
        return _bad(413, 'too_large')
    try:
        d = json.loads(handler.rfile.read(n).decode('utf-8'))
    except (ValueError, OSError):
        return _bad(400, 'bad_json')
    if not isinstance(d, dict):
        return _bad(400, 'bad_json')
    acct = d.get('account_name', d.get('username'))
    pwd = d.get('password')
    if not isinstance(acct, str) or not isinstance(pwd, str):
        return _bad(400, 'bad_request')
    # .strip() on both: /register and /login strip them, so the stored hash is of the stripped
    # password - hashing the raw value here would fail logins the dashboard accepts.
    acct, pwd = acct.strip(), pwd.strip()
    if not acct or not pwd or len(acct) > 64 or len(pwd) > 256:
        return _bad(400, 'bad_request')

    ip = _auth_client_ip(handler)
    k_acct, k_ip = ('acct', acct.lower()), ('ip', ip)
    wait = _auth_limited(k_acct, AUTH_FAIL_MAX_ACCT)
    if not wait and via == 'origin':
        wait = _auth_limited(k_ip, AUTH_FAIL_MAX_IP)
    if wait:
        SRV['log']('WEBAUTH', f'LIMITED {acct[:32]!r} from {ip} via {via} (retry in {wait}s)')
        return _bad(429, 'too_many_attempts', (('Retry-After', str(wait)),))

    conn = _connect()
    try:
        rec = conn.execute("SELECT account_name, web_password FROM accounts "
                           "WHERE account_name=?", (acct,)).fetchone()
    finally:
        conn.close()
    # Hash and compare even when the account is missing or has no web password, so the three
    # failure cases cost the same and give the same answer (no account-name probing).
    stored = (rec[1] if rec and rec[1] else '')
    good = hmac.compare_digest(hash_password(pwd).encode('ascii'),
                               stored.encode('utf-8', 'replace')) and bool(stored)
    view = _auth_account_view(rec[0]) if good else None
    if not view:
        _auth_note_fail(k_acct)
        if via == 'origin':
            _auth_note_fail(k_ip)
        SRV['log']('WEBAUTH', f'FAIL {acct[:32]!r} from {ip} via {via}')
        return _bad(401, 'invalid_credentials')

    now = time.time()
    token = secrets.token_urlsafe(32)
    with _AUTH_LOCK:
        _AUTH_FAILS.pop(k_acct, None)
        for t in [t for t, e in _AUTH_TOKENS.items() if e[1] <= now]:
            _AUTH_TOKENS.pop(t, None)
        _AUTH_TOKENS[token] = (view[0], now + AUTH_TOKEN_TTL_S)
    SRV['log']('WEBAUTH', f'OK {view[0]!r} from {ip} via {via} ({len(view[2])} pilot(s))')
    _auth_send(handler, 200, {
        'ok': True, 'account': view[0], 'is_admin': view[1],
        'authorization': {'type': 'Bearer', 'token': token,
                          'expires_in': AUTH_TOKEN_TTL_S,
                          'expires_at': int(now + AUTH_TOKEN_TTL_S)},
        'pilots': view[2]}, origin)

class WebInterfaceHandler(BaseHTTPRequestHandler):
    def get_current_user(self):
        cookie_header = self.headers.get('Cookie')
        if cookie_header:
            c = cookies.SimpleCookie(cookie_header)
            if 'session' in c:
                token = c['session'].value
                return WEB_SESSIONS.get(token)
        return None

    def send_html(self, content):
        self._perf_ready = time.time()   # 2026-09-29 WEBPERF: page built, transfer starts
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        html = f"""<!DOCTYPE html><html>
        <head>
            <meta charset="utf-8">
            <title>FA Server Control</title>
            <style>
                body {{ font-family: sans-serif; background: #f4f4f9; padding: 20px; color: #333; }}
                .container {{ max-width: 850px; margin: auto; background: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
                h1 {{ text-align: center; color: #2c3e50; }}
                .card {{ border: 1px solid #ddd; padding: 20px; margin-bottom: 20px; border-radius: 5px; background: #fafafa; }}
                input[type="text"], input[type="password"] {{ width: 100%; padding: 10px; margin: 10px 0; box-sizing: border-box; border: 1px solid #ccc; border-radius: 4px; }}
                button {{ background: #007bff; color: white; border: none; padding: 10px 15px; cursor: pointer; border-radius: 4px; font-weight: bold; width: 100%; margin-top: 10px; }}
                button:hover {{ background: #0056b3; }}
                .btn-green {{ background: #28a745; }}
                .btn-green:hover {{ background: #218838; }}
                .btn-red {{ background: #dc3545; }}
                .btn-red:hover {{ background: #c82333; }}
                .btn-yellow {{ background: #ffc107; color: #333; }}
                .btn-yellow:hover {{ background: #e0a800; }}
                .nav {{ text-align: right; margin-bottom: 20px; font-size: 0.95em; border-bottom: 2px solid #eee; padding-bottom: 10px; }}
                .nav a {{ color: #007bff; text-decoration: none; font-weight: bold; margin-left: 10px; }}
                .nav a:hover {{ text-decoration: underline; }}
                table {{ width: 100%; border-collapse: collapse; background: #fff; }}
                th {{ padding: 12px; border-bottom: 2px solid #ddd; text-align: left; background: #f8f9fa; cursor: pointer; user-select: none; }}
                th:hover {{ background: #e2e6ea; }}
                td {{ padding: 10px; border-bottom: 1px solid #eee; vertical-align: middle; }}
                tr:hover td {{ background-color: #f1f1f1; }}
            </style>
        </head>
        <body><div class="container">{content}</div></body></html>"""
        self.wfile.write(html.encode('utf-8'))

    def do_GET(self):
        # v475 [WEBPERF]: per-request timing - the layer never had it, and the 'arena page
        # takes 4-5s with multiple refreshes' report was unanswerable from logs. Anything
        # >=200ms gets a WEBPERF line (path only, query stripped); one page load now names
        # the slow request(s) directly. Wraps the real handler; POST likewise.
        # 2026-09-29: split BUILD vs SEND. wfile.write on TLS blocks until the kernel takes the
        # whole body, so over a long-RTT link the 70 KB logs.json poll 'took' ~310 ms of pure
        # transfer and logged itself every 2 s - and each such INFO line kept the next poll at
        # 70 KB (feedback loop, the 2026-09-29 flood). Handlers stamp self._perf_ready when they
        # start sending (send_html does it for every page); the 200 ms threshold now applies
        # to server-side build time. Unstamped handlers keep the old total-time behaviour.
        _t0 = time.time()
        self._perf_ready = None
        try:
            self._do_GET_inner()
        finally:
            self._perf_log('GET', _t0)

    def _perf_log(self, method, t0):
        _end = time.time()
        _ready = getattr(self, '_perf_ready', None)
        if _ready is not None and not (t0 <= _ready <= _end):
            _ready = None                       # stale stamp from an earlier keep-alive request
        _build = (_ready - t0) if _ready is not None else (_end - t0)
        if _build >= 0.2:
            try:
                _split = (f' (build {_build*1000:.0f}ms + send {(_end - _ready)*1000:.0f}ms)'
                          if _ready is not None else '')
                SRV['log']('WEBPERF', f'{method} {self.path.split("?")[0]} '
                                      f'took {(_end - t0)*1000:.0f}ms{_split}')
            except Exception:
                pass

    def do_OPTIONS(self):
        # 2026-09-30: CORS preflight for the website login API; every other path is a 404.
        _auth_handle_options(self)

    def _do_GET_inner(self):
        if self.path.split('?')[0] == '/auth':      # 2026-09-30: website login API (token check)
            return _auth_handle_get(self)
        user = self.get_current_user()
        
        if self.path == '/':
            if not user:
                self.send_response(302)
                self.send_header('Location', '/login')
                self.end_headers()
                return

            conn = sqlite3.connect(SRV['db_path'])
            client_path = conn.execute("SELECT client_path FROM accounts WHERE account_name=?", (user,)).fetchone()[0]
            conn.close()
            
            display_path = client_path if client_path else DEFAULT_CLIENT_PATH
            admin_link = '<a href="/admin" style="color:#28a745;">Admin Panel</a> |' if is_user_admin(user) else ''

            content = f"""
                <div class="nav">
                    Logged in as <strong>{user}</strong> | 
                    <a href="/ladder" style="color:#17a2b8;">Ladder Board</a> |
                    <a href="/scoring" style="color:#fd7e14;">Scoring</a> |
                    <a href="/squadrons" style="color:#20c997;">Squadrons</a> |
                    <a href="/my_arenas" style="color:#6f42c1;">My Arenas</a> |
                    {admin_link} 
                    <a href="/logout" style="color:#dc3545;">Logout</a>
                </div>
                <h1>Welcome Pilot</h1>
                
                <div class="card">
                    <h2 style="margin-top:0;">Play Fighter Ace</h2>
                    <form method="POST" action="/update_path" style="margin-bottom: 15px;">
                        <label>Your Game Client Path:</label>
                        <input type="text" name="client_path" value="{display_path}" required>
                        <button type="submit" style="background: #6c757d;">Save Path Settings</button>
                    </form>
                    <form method="GET" action="/download">
                        <button type="submit" class="btn-green">Launch Game</button>
                    </form>
                </div>
            """
            self.send_html(content)
            
        elif self.path == '/ladder':
            conn = sqlite3.connect(SRV['db_path'])
            # v405f5: FA keeps TWO boards - Fighter Score and Bomber Score (which one your points
            # feed depends on what you were FLYING, v242). Query both; guard the column for an
            # un-migrated DB. account_name is still queried only to highlight the active user.
            pcols = [r[1] for r in conn.execute("PRAGMA table_info(pilots)").fetchall()]
            def _gc(col):
                return ("COALESCE(" + col + ",0)") if col in pcols else "0"
            stats = conn.execute("SELECT pilot_name, account_name, COALESCE(score,0), "
                                 + _gc('bomber_score') + ", " + _gc('score_ffa') + ", "
                                 + _gc('bscore_ffa') + ", " + _gc('score_tc') + ", "
                                 + _gc('bscore_tc') + ", " + _gc('score_events') + ", "
                                 + _gc('bscore_events') + ", "
                                 + _gc('kills_ffa') + ", " + _gc('deaths_ffa') + ", "
                                 + _gc('kills_tc') + ", " + _gc('deaths_tc') + ", "
                                 + _gc('kills_events') + ", " + _gc('deaths_events') + ", "
                                 "COALESCE(kills,0), COALESCE(deaths,0), "
                                 + _gc('ai_buildings') + ", " + _gc('ai_tanks') + ", " + _gc('ai_ground') + ", "
                                 + _gc('ai_trains') + ", " + _gc('captures') + " FROM pilots").fetchall()   # v714f5
            conn.close()

            _ref = _scoring_ref()
            def _kd(k, d):
                return round(k / d, 2) if d > 0 else float(k)
            pilots = []
            for (p_name, a_name, f_score, b_score, f_ffa, b_ffa, f_tc, b_tc, f_ev, b_ev,
                 k_ffa, d_ffa, k_tc, d_tc, k_ev, d_ev, k, d, g_bld, g_tk, g_gr, g_tr, g_cp) in stats:
                total = (f_score or 0) + (b_score or 0)
                # Rank is ALWAYS the combined-ladder rank - it IS the pilot's rank (the server
                # computes it from fighter+bomber, db_apply_score_delta), same on every tab.
                rname = _rank_name_for_score(_ref, total) if _ref else ''
                pilots.append({'name': p_name, 'acct': a_name, 'rank': rname,
                               'career_f': f_score, 'career_b': b_score, 'career_t': total,
                               'career_k': k, 'career_d': d, 'career_kd': _kd(k, d),
                               'ffa_f': f_ffa, 'ffa_b': b_ffa, 'ffa_t': f_ffa + b_ffa,
                               'ffa_k': k_ffa, 'ffa_d': d_ffa, 'ffa_kd': _kd(k_ffa, d_ffa),
                               'tc_f': f_tc, 'tc_b': b_tc, 'tc_t': f_tc + b_tc,
                               'tc_k': k_tc, 'tc_d': d_tc, 'tc_kd': _kd(k_tc, d_tc),
                               'ev_f': f_ev, 'ev_b': b_ev, 'ev_t': f_ev + b_ev,
                               'ev_k': k_ev, 'ev_d': d_ev, 'ev_kd': _kd(k_ev, d_ev),
                               'bld': g_bld, 'tanks': g_tk, 'ground': g_gr, 'trains': g_tr, 'caps': g_cp})

            # v408f5: FFA / TC / Events are the MAIN boards (plus Career - the totals the game
            # client itself renders). Fighter and Bomber scores are COLUMNS inside every board,
            # exactly mirroring the career split; each board sorts by its own Total then K/D,
            # and every column header re-sorts. Each mode's kills/deaths/K/D are its own.
            ladder_boards = []
            for tid, prefix in (('lcareer', 'career'), ('lffa', 'ffa'),
                                ('ltc', 'tc'), ('levents', 'ev')):
                fk, bk, tk = prefix + '_f', prefix + '_b', prefix + '_t'
                kk, dk, kdk = prefix + '_k', prefix + '_d', prefix + '_kd'
                rows = sorted(pilots, key=lambda x: (x[tk], x[kdk]), reverse=True)
                body = ""
                for pos, p in enumerate(rows, 1):
                    row_style = ("background-color: #e8f4f8; font-weight: bold;"
                                 if p['acct'] == user else "")
                    body += ("<tr style='" + row_style + "'><td>" + str(pos) + "</td>"
                             "<td><strong>" + hesc(str(p['name'])) + "</strong></td>"
                             "<td>" + hesc(str(p['rank'])) + "</td>"
                             "<td>" + str(p[fk]) + "</td><td>" + str(p[bk]) + "</td>"
                             "<td><strong>" + str(p[tk]) + "</strong></td>"
                             "<td>" + str(p[kk]) + "</td><td>" + str(p[dk]) + "</td>"
                             "<td>" + str(p[kdk]) + "</td>"
                             + (("<td>" + str(p['bld']) + "</td><td>" + str(p['tanks']) + "</td>"
                                 "<td>" + str(p['ground']) + "</td><td>" + str(p['trains']) + "</td>"
                                 "<td>" + str(p['caps']) + "</td>") if tid in ('lcareer', 'ltc') else "")
                             + "</tr>")
                ths = ""
                _hdr = ['#', 'Pilot Name', 'Rank', 'Fighter Score', 'Bomber Score', 'Total',
                        'Kills', 'Deaths', 'K/D Ratio']
                if tid in ('lcareer', 'ltc'):          # v714f5: ground tallies (career counters) on Career + TC
                    _hdr += ['Buildings', 'Tanks', 'Ground Units', 'Trains', 'Captures']
                for i, h in enumerate(_hdr):
                    ths += ('<th onclick="sortLadder(' + "'" + tid + "'," + str(i) + ')">'
                            + h + ' &#x21D5;</th>')
                ladder_boards.append((tid, prefix, ths, body))

            # v545f5 SQUADRONS board: per-squadron career tallies accumulated by the game server
            # (db_squadron_score_add mirrors every member point delta / kill / death onto the
            # squadron they were flying under at credit time). Approved squadrons only.
            try:
                conn = sqlite3.connect(SRV['db_path'])
                scols = [r[1] for r in conn.execute("PRAGMA table_info(squadrons)").fetchall()]
                def _sc(col):
                    return ("COALESCE(s." + col + ",0)") if col in scols else "0"
                sq = conn.execute(
                    "SELECT s.name, COALESCE(s.tag,''), " + _sc('score') + ", " + _sc('kills')
                    + ", " + _sc('deaths') + ", "
                    "(SELECT COUNT(*) FROM squadron_members m WHERE m.squadron_id=s.squadron_id "
                    " AND m.status='approved'), "
                    + _sc('ai_buildings') + ", " + _sc('ai_tanks') + ", " + _sc('ai_ground') + ", "
                    + _sc('ai_trains') + ", " + _sc('captures') + " "          # v713f5: ground tallies
                    "FROM squadrons s WHERE s.status='approved'").fetchall()
                conn.close()
                srows = sorted(({'name': n, 'tag': t, 'score': sc, 'kills': k, 'deaths': d,
                                 'members': m, 'kd': _kd(k, d),
                                 'bld': b, 'tanks': tk, 'ground': g, 'trains': tr, 'caps': cp}
                                for n, t, sc, k, d, m, b, tk, g, tr, cp in sq),
                               key=lambda x: (x['score'], x['kd']), reverse=True)
                sbody = ""
                for pos, q in enumerate(srows, 1):
                    sbody += ("<tr><td>" + str(pos) + "</td>"
                              "<td><strong>" + hesc(str(q['name'])) + "</strong></td>"
                              "<td>" + hesc(str(q['tag'])) + "</td>"
                              "<td>" + str(q['members']) + "</td>"
                              "<td><strong>" + str(q['score']) + "</strong></td>"
                              "<td>" + str(q['kills']) + "</td><td>" + str(q['deaths']) + "</td>"
                              "<td>" + str(q['kd']) + "</td>"
                              "<td>" + str(q['bld']) + "</td><td>" + str(q['tanks']) + "</td>"
                              "<td>" + str(q['ground']) + "</td><td>" + str(q['trains']) + "</td>"
                              "<td>" + str(q['caps']) + "</td></tr>")
                sths = ""
                for i, h in enumerate(('#', 'Squadron', 'Tag', 'Members', 'Score',
                                       'Kills', 'Deaths', 'K/D Ratio',
                                       'Buildings', 'Tanks', 'Ground Units', 'Trains', 'Captures')):
                    sths += ('<th onclick="sortLadder(' + "'lsqn'," + str(i) + ')">'
                             + h + ' &#x21D5;</th>')
                ladder_boards.append(('lsqn', 'sqn', sths, sbody))
            except Exception as _e:
                SRV['log']('WEB', f'squadron ladder board failed: {_e}')

            tabs_html = ""
            panels_html = ""
            for i, (tid, prefix, ths, body) in enumerate(ladder_boards):
                on = ' lon' if i == 0 else ''
                tab_lbl = {'lcareer': 'Career', 'lffa': 'FFA', 'ltc': 'TC',
                           'levents': 'Events', 'lsqn': 'Squadrons'}.get(tid, prefix)
                tabs_html += ('<button type="button" class="ltab' + on + '" id="btn-' + tid + '" '
                              'onclick="lshow(' + "'" + tid + "'" + ')">' + tab_lbl + '</button>')
                panels_html += ('<div class="lpanel" id="pan-' + tid + '" style="display:'
                                + ('block' if i == 0 else 'none') + ';">'
                                + '<table id="' + tid + '"><thead><tr>' + ths + '</tr></thead>'
                                + '<tbody>' + body + '</tbody></table></div>')

            content = f"""
                <div class="nav"><a href="/">&larr; Back to Dashboard</a> |
                    <a href="/scoring" style="color:#fd7e14;">Scoring Reference</a></div>
                <h1>Top Aces Ladder</h1>
                <div class="card" style="padding: 0;">
                    <div class="lbar">{tabs_html}</div>
                    <p style="color:#888; font-size:0.85em; margin:8px 15px 0;">Every board splits
                    its score into Fighter and Bomber - which one your points feed depends on what
                    you were <em>flying</em> when you earned them. The FFA, TC and Events boards
                    count only what happened in arenas of that type; Career is the record the game
                    itself renders. Rank comes from the combined career total everywhere.</p>
                    <div style="padding: 15px;">
                        <input type="text" id="searchInput" placeholder="Search by pilot name..." style="width: 100%; padding: 10px; margin: 0; box-sizing: border-box; border: 1px solid #ccc; border-radius: 4px;">
                    </div>
                    {panels_html}
                </div>
            """ + LADDER_TABS_ASSETS
            self.send_html(content)

        elif self.path == '/admin':
            if not is_user_admin(user):
                self.send_html("<h2>Access Denied</h2><p>Administrator privileges required.</p><a href='/'>&larr; Back</a>")
                return
            # v475b [WEBPERF-DETAIL]: coarse per-section timing so the 1.3s /admin build names
            # its own hot spot on the next load. Logged once per request at the end.
            _ps = {}
            _pt0 = time.time()
            conn = sqlite3.connect(SRV['db_path'])
            users = conn.execute("SELECT account_name, is_admin FROM accounts ORDER BY account_name").fetchall()
            _ps['users_q'] = time.time() - _pt0

            # Pilot stats management. Pilots live in the `pilots` table. v240: the msg-25 stat block
            # is fully mapped, so EVERY row of the in-game HQ Scores screen has its own column and is
            # editable - the editor doubles as an end-to-end test harness for the block.
            pilot_html = ""
            _pt0 = time.time()
            try:
                pcols = [r[1] for r in conn.execute("PRAGMA table_info(pilots)").fetchall()]
                if 'pilot_name' in pcols:
                    def _c(col):
                        return f'COALESCE({col},0)' if col in pcols else '0'
                    pilot_rows = conn.execute(
                        "SELECT pilot_name, COALESCE(account_name,''), " + _c('rank') + ", "
                        + _c('score') + ", " + _c('kills') + ", " + _c('deaths') + ", "
                        + _c('aces') + ", " + _c('planes_lost') + ", " + _c('kills_in_a_row') + " "
                        "FROM pilots ORDER BY account_name, pilot_name").fetchall()
                    if not pilot_rows:
                        pilot_html = "<tr><td colspan='2'>No pilots in the database.</td></tr>"
                    for (pname, pacct, prank, pscore, pkills, pdeaths,
                         paces, plost, pstreak) in pilot_rows:
                        acct_lbl = f' <small style="color:#666;">({hesc(str(pacct))})</small>' if pacct else ''
                        pilot_html += f"""
                        <tr>
                            <td><strong>{hesc(str(pname))}</strong>{acct_lbl}<br>
                                <small style="color:#666;">Rank {prank} &middot; Fighter Score {pscore} &middot;
                                {pkills} kills / {pdeaths} lost pilots &middot; {plost} planes lost &middot;
                                {pstreak} in a row &middot; Aces {paces}</small></td>
                            <td style="text-align:right;">
                                <a href="/admin/edit_pilot?pilot={urllib.parse.quote(pname)}" class="btn-green"
                                   style="display:inline-block; width:auto; padding:8px 14px; margin:0;
                                   text-decoration:none;">&#9998; Edit&nbsp;Stats</a>
                                <form method="POST" action="/admin/rename_pilot" style="display:inline-block; margin-left:8px;"
                                      onsubmit="return confirm('Rename this pilot? Stats, arenas and room membership follow the new name.');">
                                    <input type="hidden" name="pilot" value="{hesc(str(pname), quote=True)}">
                                    <input type="text" name="new_name" placeholder="New pilot name" required
                                           maxlength="31" style="width:150px; padding:8px; margin:0; display:inline-block;">
                                    <button type="submit" class="btn-yellow" style="width:auto; padding:8px 12px; margin:0; display:inline-block;">Rename</button>
                                </form>
                            </td>
                        </tr>"""
                else:
                    pilot_html = "<tr><td colspan='2'>No pilots table in the database.</td></tr>"
            except Exception as e:
                pilot_html = f"<tr><td colspan='2'>Error loading pilots: {e}</td></tr>"
            _ps['pilots'] = time.time() - _pt0

            # Arena (room) management. Rooms live in the `rooms` table; expose name,
            # title (the arena-list section header / category) and status for editing.
            arena_html = ""
            _pt0 = time.time()
            try:
                rcols = [r[1] for r in conn.execute("PRAGMA table_info(rooms)").fetchall()]
                cat_sel = "COALESCE(category,'Custom Arenas')" if 'category' in rcols else "'Custom Arenas'"
                pers_sel = "COALESCE(persistent,0)" if 'persistent' in rcols else "0"
                pw_sel   = "COALESCE(password_protected,0)" if 'password_protected' in rcols else "0"
                arena_rows = conn.execute(
                    "SELECT room_id, COALESCE(room_name,''), COALESCE(creator_pilot,''), "
                    "COALESCE(status,'open'), COALESCE(terrain,1), " + cat_sel + ", "
                    "(SELECT COUNT(*) FROM room_players rp WHERE rp.room_id=rooms.room_id), "
                    + pers_sel + ", " + pw_sel + " FROM rooms ORDER BY created_at DESC").fetchall()
                if not arena_rows:
                    arena_html = "<tr><td>No arenas in the database.</td><td></td></tr>"
                for rid, rname, creator, status, terrain, category, pcount, pers, pwp in arena_rows:
                    sel_open   = 'selected' if status == 'open' else ''
                    sel_closed = 'selected' if status != 'open' else ''
                    row_bg = '' if status == 'open' else 'background:#f3f3f3;'
                    pers_chk = 'checked' if pers else ''
                    lock_badge = (' <span title="Password protected" style="color:#b8860b;">&#128274;</span>'
                                  if pwp else '')
                    arena_html += f"""
                    <tr style="{row_bg}">
                        <td>
                            <form method="POST" action="/admin/edit_arena" style="margin:0;">
                                <input type="hidden" name="room_id" value="{rid}">
                                <div style="display:flex; gap:10px; flex-wrap:wrap; align-items:flex-end;">
                                    <label style="font-size:0.8em; color:#666;">Name{lock_badge}<br>
                                        <input type="text" name="room_name" value="{hesc(str(rname), quote=True)}" style="width:190px; padding:6px; margin:2px 0;">
                                    </label>
                                    <label style="font-size:0.8em; color:#666;">Title (section header)<br>
                                        <input type="text" name="category" value="{hesc(str(category), quote=True)}" style="width:170px; padding:6px; margin:2px 0;">
                                    </label>
                                    <label style="font-size:0.8em; color:#666;">Status<br>
                                        <select name="status" style="padding:7px; margin:2px 0;">
                                            <option value="open" {sel_open}>open</option>
                                            <option value="closed" {sel_closed}>closed</option>
                                        </select>
                                    </label>
                                    <label style="font-size:0.8em; color:#666; white-space:nowrap;" title="Persistent arenas are exempt from the 24h auto-cleanup and the console 'cleanup' command.">
                                        Persistent<br>
                                        <input type="checkbox" name="persistent" value="1" {pers_chk} style="width:18px; height:18px; margin:8px 0;">
                                    </label>
                                    <button type="submit" class="btn-green" style="width:auto; padding:8px 16px; margin:0;">Save</button>
                                </div>
                                <small style="color:#888;">DB id {rid} &middot; creator {hesc(str(creator), quote=True) or '?'} &middot; terrain {terrain} &middot; players {pcount}</small>
                            </form>
                        </td>
                        <td style="text-align:right; vertical-align:top; white-space:nowrap;">
                            <a href="/admin/arena_settings?room={rid}" class="btn-green" style="display:inline-block; width:auto; padding:8px 14px; margin:0 0 6px 0; text-decoration:none;">&#9881; Edit&nbsp;Settings</a><br>
                            <form method="POST" action="/admin/delete_arena" onsubmit="return confirm('Permanently delete this arena row?');">
                                <input type="hidden" name="table" value="rooms">
                                <input type="hidden" name="rowid" value="{rid}">
                                <button type="submit" class="btn-red" style="width:auto; padding:8px 12px; margin:0;">Delete</button>
                            </form>
                        </td>
                    </tr>"""
            except Exception as e:
                arena_html = f"<tr><td>Error loading arenas: {e}</td><td></td></tr>"
            _ps['arenas'] = time.time() - _pt0

            user_html = ""
            acct_options = ''.join(
                '<option value="' + hesc(str(u), quote=True) + '">' + hesc(str(u)) + '</option>'
                for u, _a in users)
            for u_name, is_adm in users:
                role = "&#128081; Admin" if is_adm else "Player"
                u_esc = hesc(str(u_name), quote=True)
                # v418f5: promote/demote toggle. Hidden (and refused server-side) for the
                # requesting admin's own row and for the pinned built-in 'admin' account.
                if u_name == user or u_name == 'admin':
                    admin_toggle = ''
                elif is_adm:
                    admin_toggle = f"""
                        <form method="POST" action="/admin/set_admin" style="display:inline-block; margin-right:10px;"
                              onsubmit="return confirm('Remove admin rights from this account?');">
                            <input type="hidden" name="account_name" value="{u_esc}">
                            <input type="hidden" name="make_admin" value="0">
                            <button type="submit" class="btn-yellow" style="width:auto; padding:8px 12px; margin:0; display:inline-block;">Demote</button>
                        </form>"""
                else:
                    admin_toggle = f"""
                        <form method="POST" action="/admin/set_admin" style="display:inline-block; margin-right:10px;"
                              onsubmit="return confirm('Grant this account FULL admin rights?\\n\\nThey will be able to edit pilots, arenas, accounts and promote/demote others.');">
                            <input type="hidden" name="account_name" value="{u_esc}">
                            <input type="hidden" name="make_admin" value="1">
                            <button type="submit" class="btn-green" style="width:auto; padding:8px 12px; margin:0; display:inline-block;">Promote</button>
                        </form>"""
                user_html += f"""
                <tr>
                    <td><strong>{u_esc}</strong> <br><small style="color:#666;">{role}</small></td>
                    <td style="text-align:right;">
                        {admin_toggle}
                        <form method="POST" action="/admin/reset_password" style="display:inline-block; margin-right: 10px;">
                            <input type="hidden" name="account_name" value="{u_esc}">
                            <input type="password" name="new_password" placeholder="New Password" required style="width:130px; padding:8px; margin:0; display:inline-block;">
                            <button type="submit" class="btn-yellow" style="width:auto; padding:8px 12px; margin:0; display:inline-block;">Reset</button>
                        </form>
                        <form method="POST" action="/admin/rename_account" style="display:inline-block; margin-right:10px;"
                              onsubmit="return confirm('Rename this account?\\n\\nThe player_id is kept, so pilots and stats follow - but the account name lives inside the .vr1 ticket, so this account MUST re-download its ticket before it can connect again.');">
                            <input type="hidden" name="account_name" value="{u_esc}">
                            <input type="text" name="new_name" placeholder="New account name" required
                                   maxlength="31" style="width:150px; padding:8px; margin:0; display:inline-block;">
                            <button type="submit" class="btn-yellow" style="width:auto; padding:8px 12px; margin:0; display:inline-block;">Rename</button>
                        </form>
                        <form method="POST" action="/admin/delete_user" style="display:inline-block;" onsubmit="return confirm('Delete this user? This permanently deletes their ticket and cannot be undone.');">
                            <input type="hidden" name="account_name" value="{u_esc}">
                            <button type="submit" class="btn-red" style="width:auto; padding:8px 12px; margin:0; display:inline-block;">Delete</button>
                        </form>
                    </td>
                </tr>"""

            # Squadron management: every squadron (pending + approved) with approve / edit / delete
            # and its roster (grant role, remove) + pending join requests. Squadrons live in the game DB.
            squadron_html = ""
            _pt0 = time.time()
            try:
                scols = [r[1] for r in conn.execute("PRAGMA table_info(squadrons)").fetchall()]
                if 'squadron_id' in scols:
                    sq_rows = conn.execute(
                        "SELECT squadron_id, name, COALESCE(tag,''), COALESCE(motto,''), "
                        "COALESCE(password,''), COALESCE(status,'pending'), COALESCE(commander,'') "
                        "FROM squadrons ORDER BY (status='approved'), name").fetchall()
                    if not sq_rows:
                        squadron_html = "<p style='color:#666;'>No squadrons yet.</p>"
                    for (sid, sname, stag, smotto, spw, sstatus, scmdr) in sq_rows:
                        _sid = hesc(str(sid), quote=True)
                        members = conn.execute(
                            "SELECT account_name, COALESCE(role,'member') FROM squadron_members "
                            "WHERE squadron_id=? AND status='approved' ORDER BY "
                            "CASE role WHEN 'commander' THEN 0 WHEN 'officer' THEN 1 ELSE 2 END, account_name",
                            (sid,)).fetchall()
                        pend = conn.execute(
                            "SELECT account_name FROM squadron_members WHERE squadron_id=? AND status='pending' "
                            "ORDER BY account_name", (sid,)).fetchall()
                        badge = ("<span style='color:#28a745;'>approved</span>" if sstatus == 'approved'
                                 else "<span style='color:#e0a800;'>pending</span>")
                        lock = ' &#128274;' if spw else ''
                        mem_html = ""
                        for (macct, mrole) in members:
                            _m = hesc(str(macct), quote=True)
                            opts = "".join(
                                f"<option value='{r}'{' selected' if r == mrole else ''}>{r}</option>"
                                for r in ('member', 'officer', 'commander'))
                            mem_html += f"""
                              <tr><td>{hesc(str(macct))}</td><td style="text-align:right;">
                                <form method="POST" action="/admin/squadron_member" style="display:inline;">
                                  <input type="hidden" name="squadron_id" value="{_sid}">
                                  <input type="hidden" name="member" value="{_m}">
                                  <select name="role" style="padding:4px;">{opts}</select>
                                  <button type="submit" name="op" value="setrole" class="btn-yellow" style="width:auto;padding:5px 10px;margin:0;">Set role</button>
                                  <button type="submit" name="op" value="remove" class="btn-red" style="width:auto;padding:5px 10px;margin:0;" onclick="return confirm('Remove this member?');">Remove</button>
                                </form></td></tr>"""
                        if not mem_html:
                            mem_html = "<tr><td colspan='2' style='color:#666;'>No members.</td></tr>"
                        pend_block = ""
                        if pend:
                            pr = ""
                            for (pacct,) in pend:
                                _p = hesc(str(pacct), quote=True)
                                pr += f"""
                                  <tr><td>{hesc(str(pacct))}</td><td style="text-align:right;">
                                    <form method="POST" action="/admin/squadron_member" style="display:inline;">
                                      <input type="hidden" name="squadron_id" value="{_sid}">
                                      <input type="hidden" name="member" value="{_p}">
                                      <button type="submit" name="op" value="approve" class="btn-green" style="width:auto;padding:5px 10px;margin:0;">Approve</button>
                                      <button type="submit" name="op" value="reject" class="btn-red" style="width:auto;padding:5px 10px;margin:0;">Reject</button>
                                    </form></td></tr>"""
                            pend_block = f'<h4 style="margin:12px 0 4px;">Pending join requests</h4><table>{pr}</table>'
                        approve_block = ""
                        if sstatus != 'approved':
                            approve_block = f"""
                              <form method="POST" action="/admin/squadron_approve" style="display:inline-block; margin-right:8px;">
                                <input type="hidden" name="squadron_id" value="{_sid}">
                                <button type="submit" class="btn-green" style="width:auto;padding:8px 14px;margin:0;">Approve squadron</button>
                              </form>"""
                        squadron_html += f"""
                        <div class="card" style="margin:10px 0;">
                          <h3 style="margin:0 0 6px;">{hesc(str(sname))}{lock} &nbsp;<small>[{badge}]</small>
                              <small style="color:#666;">&middot; {len(members)} member(s) &middot; id {sid}</small></h3>
                          {approve_block}
                          <form method="POST" action="/admin/squadron_delete" style="display:inline-block;"
                                onsubmit="return confirm('Delete this squadron and all memberships? Cannot be undone.');">
                            <input type="hidden" name="squadron_id" value="{_sid}">
                            <button type="submit" class="btn-red" style="width:auto;padding:8px 14px;margin:0;">Delete</button>
                          </form>
                          <form method="POST" action="/admin/squadron_edit" style="margin-top:10px;">
                            <input type="hidden" name="squadron_id" value="{_sid}">
                            <div style="display:flex; gap:10px; align-items:flex-end; flex-wrap:wrap;">
                              <label style="font-size:0.8em; color:#666;">Name<br>
                                <input type="text" name="name" value="{hesc(str(sname), quote=True)}" maxlength="31" style="width:200px; padding:6px;"></label>
                              <label style="font-size:0.8em; color:#666;">Tag<br>
                                <input type="text" name="tag" value="{hesc(str(stag), quote=True)}" maxlength="31" style="width:110px; padding:6px;"></label>
                              <label style="font-size:0.8em; color:#666;">Password (blank = open)<br>
                                <input type="text" name="password" value="{hesc(str(spw), quote=True)}" maxlength="31" autocomplete="off" style="width:150px; padding:6px;"></label>
                            </div>
                            <label style="font-size:0.8em; color:#666; display:block; margin-top:6px;">Notes / motto<br>
                              <textarea name="motto" rows="2" style="width:100%; max-width:500px; padding:6px;">{hesc(str(smotto))}</textarea></label>
                            <button type="submit" class="btn-green" style="width:auto; padding:8px 14px; margin-top:6px;">Save changes</button>
                          </form>
                          <h4 style="margin:12px 0 4px;">Members</h4>
                          <table>{mem_html}</table>
                          {pend_block}
                        </div>"""
                else:
                    squadron_html = "<p style='color:#666;'>Squadrons table not found (start the game server once).</p>"
            except Exception as e:
                squadron_html = f"<p style='color:red;'>Error loading squadrons: {hesc(str(e))}</p>"
            _ps['squadrons'] = time.time() - _pt0

            conn.close()
            try:
                SRV['log']('WEBPERF', 'admin sections: '
                           + ' '.join(f'{k}={v*1000:.0f}ms' for k, v in _ps.items()))
            except Exception:
                pass

            content = f"""
                {ADMIN_TABS_ASSETS}
                <div class="nav"><a href="/">&larr; Back to Dashboard</a> |
                    <a href="/admin/logs" style="color:#17a2b8;">Live Console</a> |
                    <a href="/admin/lobby_news" style="color:#6f42c1;">Lobby News</a> |
                    <a href="/admin/motd" style="color:#b8860b;">Message of the Day</a> |
                    <a href="/admin/leaders" style="color:#198754;">Leaderboards</a> |
                    <a href="/admin/badwords" style="color:#dc3545;">Chat Filter</a> |
                    Logged in as <strong>{hesc(str(user))}</strong></div>
                <h1>Server Administration</h1>

                <div class="tabbar">
                    <button class="on" data-btngroup="main" data-target="p-users"
                            onclick="faShow('main','p-users')">User Management</button>
                    <button data-btngroup="main" data-target="p-arenas"
                            onclick="faShow('main','p-arenas')">Arenas</button>
                    <button data-btngroup="main" data-target="p-squadrons"
                            onclick="faShow('main','p-squadrons')">Squadrons</button>
                    <button data-btngroup="main" data-target="p-logs"
                            onclick="faShow('main','p-logs')">Logs</button>
                    <button data-btngroup="main" data-target="p-stalls"
                            onclick="faShow('main','p-stalls')">Stall Dumps</button>
                </div>

                <div class="panel on" data-group="main" data-panel="p-users">
                    <div class="subbar">
                        <button class="on" data-btngroup="user" data-target="s-accounts"
                                onclick="faShow('user','s-accounts')">Users</button>
                        <button data-btngroup="user" data-target="s-pilots"
                                onclick="faShow('user','s-pilots')">Pilot Stats</button>
                    </div>

                    <div class="panel on" data-group="user" data-panel="s-accounts">
                        <div class="card">
                            <h2 style="margin-top:0;">Users</h2>
                            <p style="color:#666; margin-top:0; font-size:0.9em;">Login accounts. Each owns
                            its own .vr1 ticket and any number of pilots.</p>
                            <div class="filterbar">
                                <input type="text" placeholder="Filter accounts&hellip;"
                                       data-table="usersTable" data-count="usersCount"
                                       oninput="faFilter(this)">
                                <span class="filtercount" id="usersCount"></span>
                            </div>
                            <table id="usersTable">{user_html}</table>
                        </div>
                    </div>

                    <div class="panel" data-group="user" data-panel="s-pilots">
                        <div class="card">
                            <h2 style="margin-top:0;">Pilot Stats</h2>
                            <p style="color:#666; margin-top:0; font-size:0.9em;">Career totals stored on the
                            server (rank, score, kills, deaths). Aces are awarded live by the game client
                            (5 kills without dying, reset on death) and are not stored here.</p>
                            <form method="POST" action="/admin/create_pilot"
                                  style="background:#fff; border:1px dashed #bbb; border-radius:6px; padding:10px 14px; margin-bottom:6px;">
                                <strong style="font-size:0.95em;">Create a pilot manually</strong>
                                <div style="display:flex; gap:10px; align-items:flex-end; flex-wrap:wrap; margin-top:8px;">
                                    <label style="font-size:0.8em; color:#666;">Account<br>
                                        <select name="account_name" style="padding:8px; margin:2px 0;">{acct_options}</select>
                                    </label>
                                    <label style="font-size:0.8em; color:#666;">Pilot name (max 31)<br>
                                        <input type="text" name="pilot_name" required maxlength="31"
                                               placeholder="@HQ" style="width:210px; padding:8px; margin:2px 0;">
                                    </label>
                                    <button type="submit" class="btn-green" style="width:auto; padding:9px 18px; margin:0;">Create</button>
                                </div>
                                <small style="color:#888;">Any printable ASCII is accepted &mdash; including
                                <code>@ * # !</code> and spaces &mdash; so staff names like
                                <code>@HQ</code>, <code>@FA</code>, <code>@INSTRUCTOR</code> and <code>@HELP</code>
                                can be made here. The game client's own name box refuses these; the server never did.
                                Only control bytes and non-ASCII are rejected (they terminate the name field on the
                                wire and corrupt the client's text parse).</small>
                            </form>
                            <div class="filterbar">
                                <input type="text" placeholder="Filter pilots (name, account, stats)&hellip;"
                                       data-table="pilotsTable" data-count="pilotsCount"
                                       oninput="faFilter(this)">
                                <span class="filtercount" id="pilotsCount"></span>
                            </div>
                            <table id="pilotsTable">{pilot_html}</table>
                        </div>
                    </div>
                </div>

                <div class="panel" data-group="main" data-panel="p-arenas">
                    <div class="card">
                        <h2 style="margin-top:0;">Arena Management</h2>
                        <p style="color:#666; margin-top:0; font-size:0.9em;">Rooms served in the client's
                        arena list. Use <em>Edit Settings</em> for altitudes and enemy AA/Flak strength.</p>
                        <div class="filterbar">
                            <input type="text" placeholder="Filter arenas (name, title, creator)&hellip;"
                                   data-table="arenasTable" data-count="arenasCount"
                                   oninput="faFilter(this)">
                            <span class="filtercount" id="arenasCount"></span>
                        </div>
                        <table id="arenasTable">{arena_html}</table>
                    </div>
                </div>

                <div class="panel" data-group="main" data-panel="p-squadrons">
                    <div class="card">
                        <h2 style="margin-top:0;">Squadron Management</h2>
                        <p style="color:#666; margin-top:0; font-size:0.9em;">Approve pending squadrons, edit
                        name/tag/notes/password, grant roles (member &harr; officer &harr; commander), approve
                        join requests, remove members, or delete a squadron. Backed by the game DB.</p>
                        {squadron_html}
                    </div>
                </div>

                <div class="panel" data-group="main" data-panel="p-logs">
                    <div class="card">
                        <h2 style="margin-top:0;">Server Logs</h2>
                        <p style="color:#666; margin-top:0; font-size:0.9em;">
                            Download or peek at the server's log files without opening a session on
                            the VM. <em>View tail</em> shows the last 128&nbsp;KB in the browser;
                            <em>Download</em> fetches the whole file.<br>
                            <small style="color:#888;">Directory: <code id="logsDir">&hellip;</code>
                            &middot; <span id="logsSummary"></span></small>
                        </p>
                        <div class="filterbar">
                            <input type="text" id="logsFilter" placeholder="Filter logs (try a date, e.g. 20260724)&hellip;"
                                   data-table="logsTable" data-count="logsCount"
                                   oninput="faFilter(this)">
                            <span class="filtercount" id="logsCount"></span>
                            <button style="width:auto; padding:8px 14px; margin:0;"
                                    onclick="faLoadLogs()">Refresh</button>
                        </div>
                        <table id="logsTable"></table>
                    </div>
                </div>

                <div class="panel" data-group="main" data-panel="p-stalls">
                    <div class="card">
                        <h2 style="margin-top:0;">Stall Dumps (flight recorder)</h2>
                        <p style="color:#666; margin-top:0; font-size:0.9em;">
                            Per-session packet rings flushed by STALL-WATCH when a reliable
                            channel goes quiet - the first thing to pull when a player reports
                            a freeze, a one-sided fight or an 82%-style hang.<br>
                            <small style="color:#888;">Directory: <code id="stallsDir">&hellip;</code>
                            &middot; <span id="stallsSummary"></span></small>
                        </p>
                        <div class="filterbar">
                            <input type="text" id="stallsFilter" placeholder="Filter dumps (pilot or date, e.g. Gary or 20260804)&hellip;"
                                   data-table="stallsTable" data-count="stallsCount"
                                   oninput="faFilter(this)">
                            <span class="filtercount" id="stallsCount"></span>
                            <button style="width:auto; padding:8px 14px; margin:0;"
                                    onclick="faLoadStalls()">Refresh</button>
                        </div>
                        <table id="stallsTable"></table>
                    </div>
                </div>
            """
            self.send_html(content)

        elif self.path.startswith('/admin/edit_pilot'):
            if not is_user_admin(user):
                self.send_html("<h2>Access Denied</h2><p>Administrator privileges required.</p>"
                               "<a href='/'>&larr; Back</a>")
                return
            q = urllib.parse.urlparse(self.path).query
            pilot = urllib.parse.parse_qs(q).get('pilot', [''])[0]
            conn = sqlite3.connect(SRV['db_path'])
            pcols = [r[1] for r in conn.execute("PRAGMA table_info(pilots)").fetchall()]

            # v240: one field per HQ Scores row. Every one of these maps to a slot in the msg-25
            # stat block (score+0x30), so whatever is saved here is exactly what the game renders -
            # which makes this form an end-to-end test harness for the block.
            STAT_FIELDS = [
                # (db column,        label,                    msg-25 slot, min, max)
                ('rank',             'Rank',                   'f0  u8',    0,   12),
                ('score',            'Fighter Score',          'f9  float', -2147483648, 2147483647),
                ('bomber_score',     'Bomber Score',           'f10 float', -2147483648, 2147483647),
                ('planes_lost',      'Planes Lost (players)',  'f4  u16',   0,   65535),
                ('planes_lost_ai',   'Planes Lost to AI',      'f13 u16',   0,   65535),
                ('deaths',           'Lost Pilots (deaths)',   'f1  u16',   0,   65535),
                ('kills',            'Kills (total)',          'f5  u16',   0,   65535),
                ('kills_fighters',   'Kills &rsaquo; Fighters','f2  u16',   0,   65535),
                ('kills_bombers',    'Kills &rsaquo; Bombers', 'f3  u16',   0,   65535),
                ('kills_in_a_row',   'Kills In A Row',         'f7  u8',    0,   255),
                ('aces',             'Aces',                   'f8  u8',    0,   255),
                ('ai_fighters',      'AI Fighters',            'f11 u16',   0,   65535),
                ('ai_bombers',       'AI Bombers',             'f12 u16',   0,   65535),
                ('ai_tanks',         'AI Tanks',               'f17 u16',   0,   65535),
                ('ai_ships',         'AI Ships',               'f16 u16',   0,   65535),
                ('ai_ground',        'AI Ground Units',        'f18 u16',   0,   65535),
                ('ai_buildings',     'AI Buildings',           'f19 u16',   0,   65535),
                # v410f5: per-mode ladder boards (web-only columns; the game client never sees
                # them). Same bounds as their career counterparts.
                ('score_ffa',        'FFA Fighter Score',      'FFA board', -2147483648, 2147483647),
                ('bscore_ffa',       'FFA Bomber Score',       'FFA board', -2147483648, 2147483647),
                ('kills_ffa',        'FFA Kills',              'FFA board', 0, 65535),
                ('deaths_ffa',       'FFA Deaths',             'FFA board', 0, 65535),
                ('score_tc',         'TC Fighter Score',       'TC board', -2147483648, 2147483647),
                ('bscore_tc',        'TC Bomber Score',        'TC board', -2147483648, 2147483647),
                ('kills_tc',         'TC Kills',               'TC board', 0, 65535),
                ('deaths_tc',        'TC Deaths',              'TC board', 0, 65535),
                ('score_events',     'Events Fighter Score',   'Events board', -2147483648, 2147483647),
                ('bscore_events',    'Events Bomber Score',    'Events board', -2147483648, 2147483647),
                ('kills_events',     'Events Kills',           'Events board', 0, 65535),
                ('deaths_events',    'Events Deaths',          'Events board', 0, 65535),
            ]
            have = [f for f in STAT_FIELDS if f[0] in pcols]
            sel = ', '.join(f'COALESCE({c},0)' for c, _l, _s, _lo, _hi in have)
            row = conn.execute(
                "SELECT pilot_name, COALESCE(account_name,'')" + (', ' + sel if sel else '') +
                " FROM pilots WHERE pilot_name=?", (pilot,)).fetchone()
            conn.close()
            if not row:
                self.send_html("<h2>Pilot not found</h2><a href='/admin'>&larr; Back to Admin</a>")
                return
            pname, pacct = row[0], row[1]
            vals = {c: v for (c, _l, _s, _lo, _hi), v in zip(have, row[2:])}
            pname_esc = hesc(pname, quote=True)
            acct_lbl = f" (account: {hesc(pacct)})" if pacct else ""

            def _grp(title, note, cols):
                inner = ""
                for c, label, slot, lo, hi in have:
                    if c not in cols:
                        continue
                    inner += f"""
                        <label style="display:inline-block; margin:8px 18px 8px 0; font-size:0.9em; color:#333; vertical-align:top;">
                            {label}<br>
                            <input type="number" step="1" name="{c}" value="{vals.get(c, 0)}"
                                   min="{lo}" max="{hi}" required
                                   style="display:block; width:150px; padding:6px; margin-top:3px;">
                            <small style="color:#999;">{slot}</small>
                        </label>"""
                if not inner:
                    return ""
                return f"""
                    <fieldset style="border:1px solid #ddd; border-radius:6px; padding:10px 14px; margin:14px 0;">
                        <legend style="padding:0 6px; color:#444; font-weight:bold;">{title}</legend>
                        <p style="margin:2px 0 6px; color:#888; font-size:0.82em;">{note}</p>
                        {inner}
                    </fieldset>"""

            content = f"""
                <div class="nav"><a href="/admin">&larr; Back to Admin</a></div>
                <h1>Edit Pilot Stats</h1>
                <div class="card">
                    <h2 style="margin-top:0;">{hesc(pname)}{acct_lbl}</h2>
                    <p style="color:#666; font-size:0.9em;">These are the pilot's career stats. Every
                    field below maps 1:1 to a slot in the game's stat block (msg 25), which fills the
                    <strong>HQ &rarr; SCORES</strong> screen in-game &mdash; so whatever you save here is exactly
                    what the client will render. The grey code under each box is its slot and wire type.
                    The server pushes this whenever the pilot opens the HQ screen, spawns, or scores a
                    kill/death.</p>
                    <form method="POST" action="/admin/edit_pilot">
                        <input type="hidden" name="pilot" value="{pname_esc}">
                        {_grp('Overall Scores',
                              'Rank is an index 0-12; the client renders its own name for it (5 = "Major"). '
                              'The HQ "Planes Lost" row displays the SUM of the two Planes-Lost fields.',
                              ('rank', 'score', 'bomber_score', 'planes_lost', 'planes_lost_ai', 'deaths'))}
                        {_grp('Record vs. Other Players',
                              'Kills is the total; Fighters/Bombers break it down. Dying resets Kills In A '
                              'Row, and every 5 without dying earns an Ace.',
                              ('kills', 'kills_fighters', 'kills_bombers', 'kills_in_a_row', 'aces'))}
                        {_grp('AI Units Destroyed',
                              'Not yet tracked by the server - set them here to verify the client renders them.',
                              ('ai_fighters', 'ai_bombers', 'ai_tanks', 'ai_ships', 'ai_ground', 'ai_buildings'))}
                        {_grp('Ladder Boards &mdash; FFA / TC / Events',
                              'The web ladder&#39;s per-arena-type boards (the game client never sees '
                              'these). They fill automatically from kills and deaths in arenas of that '
                              'type; edit them here to seed or correct a board &mdash; e.g. copy a career '
                              'total into the board it was really earned on. Rank always derives from '
                              'the career scores above, never from these.',
                              ('score_ffa', 'bscore_ffa', 'kills_ffa', 'deaths_ffa',
                               'score_tc', 'bscore_tc', 'kills_tc', 'deaths_tc',
                               'score_events', 'bscore_events', 'kills_events', 'deaths_events'))}
                        <div style="margin-top:15px;">
                            <button type="submit" class="btn-green" style="width:auto; padding:10px 20px;">Save Stats</button>
                            &nbsp; <a href="/admin" style="color:#666;">Cancel</a></div>
                    </form>
                </div>
            """
            self.send_html(content)

        elif self.path.startswith('/admin/arena_reset'):
            # v640f5: reset an arena now (admins, or the arena's creator); ?winner=<camp> announces
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            try:
                room_id = int(qs.get('room', ['0'])[0])
            except (ValueError, TypeError):
                room_id = 0
            if not user_can_edit_arena(user, room_id):
                return self.send_error(403)
            wq = qs.get('winner', [''])[0].strip()
            if wq == 'ask':
                opts = ''.join(f'<option value="{c}">camp {c}</option>' for c in range(8))
                self.send_html(f"""<div class="card"><h2>Announce a winner and reset arena {room_id}</h2>
                    <form method="get" action="/admin/arena_reset"><input type="hidden" name="room" value="{room_id}">
                    <label>Winning camp (0 = first assigned country, 1 = second, ...)<br><select name="winner">{opts}</select></label>
                    <div style="margin-top:14px;"><button type="submit" class="btn-red">Announce &amp; reset</button>
                    &nbsp; <a href="/admin/arena_settings?room={room_id}" style="color:#666;">Cancel</a></div></form></div>""")
                return
            winner = None
            if wq != '':
                try:
                    winner = max(0, min(7, int(wq)))
                except ValueError:
                    winner = None
            fn = SRV.get('arena_reset')
            if fn:
                try:
                    fn(room_id, winner, f'web:{user}')
                    SRV['log']('WEB', f'{user} reset arena {room_id} (winner {winner})')
                except Exception as e:
                    SRV['log']('WEB', f'arena reset failed: {e!r}')
            self.send_response(302)
            self.send_header('Location', '/admin/arena_settings?room=%d' % room_id)
            self.end_headers()

        elif self.path.startswith('/admin/arena_settings'):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            try:
                room_id = int(qs.get('room', ['0'])[0])
            except (ValueError, TypeError):
                room_id = 0
            # Admins may edit any arena; a regular player may edit only arenas they created.
            if not user_can_edit_arena(user, room_id):
                self.send_html("<h2>Access Denied</h2><p>You can only edit arenas you created.</p><a href='/my_arenas'>&larr; Back</a>")
                return
            conn = sqlite3.connect(SRV['db_path'])
            rcols = [r[1] for r in conn.execute("PRAGMA table_info(rooms)").fetchall()]
            sj_sel = "COALESCE(settings_json,'{}')" if 'settings_json' in rcols else "'{}'"
            cat_sel = "COALESCE(category,'Custom Arenas')" if 'category' in rcols else "'Custom Arenas'"
            row = conn.execute(
                "SELECT room_id, COALESCE(room_name,''), " + cat_sel + ", COALESCE(status,'open'), "
                "game_def_raw, " + sj_sel + " FROM rooms WHERE room_id=?", (room_id,)).fetchone()
            conn.close()
            if not row:
                self.send_html("<h2>Arena not found</h2><a href='/admin'>&larr; Back to Admin</a>")
                return
            rid, rname, category, status, gdef, sj = row
            # current value for each field = GAME_DEF as-created value, overlaid with saved edits
            base = {}
            try:
                if SRV.get('settings_read') and gdef:
                    base = SRV['settings_read'](bytes(gdef)) or {}
            except Exception:
                base = {}
            try:
                overrides = json.loads(sj) if sj else {}
            except Exception:
                overrides = {}
            if not isinstance(overrides, dict):
                overrides = {}
            cur = dict(base); cur.update(overrides)
            fields_html = ""
            for key, delta, label in SRV.get('tail_fields', []):
                val = cur.get(key, '')
                edited = ' &bull; <span style="color:#c60;">edited</span>' if key in overrides else ''
                fields_html += (
                    '<label style="display:block; margin:10px 0; font-size:0.9em; color:#333;">'
                    + hesc(str(label)) + edited + '<br>'
                    + '<input type="number" step="1" name="s_' + hesc(str(key)) + '" value="'
                    + hesc(str(val)) + '" style="width:200px; padding:6px;"></label>')
            # EvP AA/Flak sliders (0..6, map 1:1 onto the GAME_DEF AA-quality bytes). Stored in
            # settings_json under their own keys; read per-arena by the game server at 212 serve.
            EVP_SLIDERS = [
                ('aa_quality',    'AA (anti-aircraft) quality', 6),
                ('flak_quality',  'Flak quality',               1),
                ('bomber_gunner', 'Bomber gunner quality',      3),
                ('ship_aa',       'Ship AA quality',            1),
                ('tank_aa',       'Tank AA quality',            1),
            ]
            evp_html = ""
            for skey, slabel, sdefault in EVP_SLIDERS:
                sval = cur.get(skey, sdefault)
                try:
                    sval = max(0, min(6, int(sval)))
                except (ValueError, TypeError):
                    sval = sdefault
                sedited = ' &bull; <span style="color:#c60;">edited</span>' if skey in overrides else ''
                evp_html += (
                    '<label style="display:block; margin:14px 0; font-size:0.9em; color:#333;">'
                    + hesc(str(slabel)) + sedited + '<br>'
                    + '<input type="range" min="0" max="6" step="1" name="s_' + hesc(skey) + '" '
                    + 'value="' + str(sval) + '" '
                    + "oninput=\"this.nextElementSibling.textContent=this.value\" "
                    + 'style="width:240px; vertical-align:middle;">'
                    + '<span style="display:inline-block; width:1.5em; text-align:center; '
                    + 'font-weight:bold; color:#2a7;">' + str(sval) + '</span>'
                    + '<span style="color:#999; font-size:0.8em;"> (0 = off, 6 = strongest)</span>'
                    + '</label>')
            # WAR DATE (v383): full date + opt-in checkbox. Default = settings_json override, else
            # the GAME_DEF's own date (via the date_read bridge), else the stock 22-Jun-1941.
            _wd_def = (22, 6, 1941)
            try:
                if SRV.get('date_read') and gdef:
                    _dr = SRV['date_read'](bytes(gdef))
                    if _dr:
                        _wd_def = _dr
            except Exception:
                _wd_def = (22, 6, 1941)
            war_on = bool(overrides.get('war_enabled'))
            war_d  = overrides.get('war_day',   _wd_def[0])
            war_m  = overrides.get('war_month', _wd_def[1])
            war_y  = overrides.get('war_year',  _wd_def[2])
            war_edited = ' &bull; <span style="color:#c60;">edited</span>' if 'war_enabled' in overrides else ''
            wardate_html = (
                '<label style="display:block; margin:12px 0; font-weight:bold;">'
                '<input type="checkbox" name="s_war_enabled" value="1"'
                + (' checked' if war_on else '') + '> Restrict planes to this war date'
                + war_edited + '</label>'
                '<div style="display:flex; gap:10px; align-items:flex-end;">'
                '<label style="font-size:0.85em; color:#333;">Day<br>'
                '<input type="number" min="1" max="31" name="s_war_day" value="' + hesc(str(war_d))
                + '" style="width:70px; padding:6px;"></label>'
                '<label style="font-size:0.85em; color:#333;">Month<br>'
                '<input type="number" min="1" max="12" name="s_war_month" value="' + hesc(str(war_m))
                + '" style="width:70px; padding:6px;"></label>'
                '<label style="font-size:0.85em; color:#333;">Year<br>'
                '<input type="number" min="1935" max="1955" name="s_war_year" value="' + hesc(str(war_y))
                + '" style="width:90px; padding:6px;"></label>'
                '</div>')
            # DATE, TIME & WEATHER (v948f5): the client's Options > Misc page is read-only for a
            # player - every value there is the arena's GAME_DEF [Reality]/[Weather] block. Defaults
            # come from the stored GAME_DEF (reality_read), overlaid with saved rw_* overrides.
            _rwb = {}
            try:
                if SRV.get('reality_read') and gdef:
                    _rwb = SRV['reality_read'](bytes(gdef)) or {}
            except Exception:
                _rwb = {}
            _rwv = dict(_rwb); _rwv.update({k: v for k, v in overrides.items() if k.startswith('rw_')})
            rw_on = bool(overrides.get('rw_enabled'))
            rw_edited = ' &bull; <span style="color:#c60;">edited</span>' if 'rw_enabled' in overrides else ''
            def _rwi(key, dflt=''):
                v = _rwv.get(key, dflt)
                return hesc('' if v is None else str(v), quote=True)
            def _rwnum(key, label, lo, hi, step=1, width=90, unit=''):
                return ('<label style="font-size:0.85em; color:#333;">' + label + '<br>'
                        '<input type="number" min="' + str(lo) + '" max="' + str(hi) + '" step="' + str(step) + '" '
                        'name="s_' + key + '" value="' + _rwi(key) + '" style="width:' + str(width) + 'px; padding:6px;">'
                        + (' <span style="color:#999;">' + unit + '</span>' if unit else '') + '</label>')
            def _rwsel(key, label, opts):
                cur = str(_rwv.get(key, ''))
                h = '<label style="font-size:0.85em; color:#333;">' + label + '<br><select name="s_' + key + '" style="padding:6px;">'
                for val, text in opts:
                    h += '<option value="' + str(val) + '"' + (' selected' if cur == str(val) else '') + '>' + hesc(text) + '</option>'
                return h + '</select></label>'
            _row = '<div style="display:flex; gap:12px; align-items:flex-end; flex-wrap:wrap; margin:8px 0;">'
            # the client's time spinners are LOGARITHMIC: the Time= value in WindParam is an exponent N
            # and the time is 2^N milliseconds (FUN_00728330: `shl esi, cl` then /3,600,000 for the
            # 'Nh Mm' label) - so the choices are powers of two, 4 s .. 18.6 h.
            def _rwdur(n):
                sec = (1 << n) / 1000.0
                if sec < 60: return '%d s' % round(sec)
                if sec < 3600: return '%.1f min' % (sec / 60)
                return '%dh %02dm' % (int(sec // 3600), int((sec % 3600) // 60))
            _rwtimes = [(n, _rwdur(n)) for n in range(12, 27)]
            for _tk in ('rw_wind_rot_time', 'rw_wind_osc_time'):
                try:
                    if _rwv.get(_tk) not in (None, '') and not (12 <= int(_rwv[_tk]) <= 26):
                        _rwv[_tk] = max(12, min(26, int(_rwv[_tk])))
                except (TypeError, ValueError):
                    pass
            _tzopts = [(m, ('UTC' if m == 0 else 'UTC%+03d:%02d' % (int(m / 60), abs(m) % 60))) for m in range(-720, 841, 30)]
            if _rwv.get('rw_tz') not in (None, '') and int(_rwv.get('rw_tz')) not in [m for m, _ in _tzopts]:
                _tzopts.append((int(_rwv.get('rw_tz')), 'UTC%+d min' % int(_rwv.get('rw_tz'))))
            reality_html = (
                '<label style="display:block; margin:12px 0; font-weight:bold;">'
                '<input type="checkbox" name="s_rw_enabled" value="1"' + (' checked' if rw_on else '') +
                '> Override the arena\'s date, time and weather' + rw_edited + '</label>'
                '<div style="color:#666; font-size:0.85em; margin:4px 0;">Date &amp; time</div>'
                + _row + _rwnum('rw_day', 'Day', 1, 31) + _rwnum('rw_month', 'Month', 1, 12)
                + _rwnum('rw_year', 'Year', 1900, 2000, 1, 90) + _rwnum('rw_hour', 'Hour', 0, 23)
                + _rwnum('rw_minute', 'Minute', 0, 59) + _rwsel('rw_tz', 'Time zone', _tzopts) + '</div>'
                + _row + _rwnum('rw_time_speed', 'Time speed', 0, 100, 0.1, 90, 'x')
                + _rwnum('rw_night_speed', 'Night speed', 0, 100, 0.1, 90, 'x')
                + _rwnum('rw_lat', 'Latitude', -90, 90, 0.01, 100, '&deg; N (negative = S)')
                + _rwnum('rw_lon', 'Longitude', -180, 180, 0.01, 100, '&deg; E (negative = W)') + '</div>'
                '<div style="color:#666; font-size:0.85em; margin:10px 0 4px;">Wind &mdash; speeds in m/s (the game shows mph: 2.0 m/s = 4.5 mph). Constant uses speed + direction; Const. rotating uses speed + rotation time; Oscill. rotating uses min/max speed + oscillation time + rotation time. The times are the game&#39;s own spinner steps (powers of two).</div>'
                + _row + _rwsel('rw_wind_type', 'Wind', [(0, 'Constant'), (1, 'Const. rotating'), (2, 'Oscill. rotating')])
                + _rwnum('rw_wind_speed', 'Speed', 0, 60, 0.1, 80, 'm/s') + _rwnum('rw_wind_dir', 'Direction', 0, 359, 1, 80, 'deg')
                + _rwsel('rw_wind_rot_time', 'Dir. rotation time', _rwtimes) + '</div>'
                + _row + _rwnum('rw_wind_min', 'Oscill. min speed', 0, 60, 0.1, 80, 'm/s')
                + _rwnum('rw_wind_max', 'Oscill. max speed', 0, 60, 0.1, 80, 'm/s')
                + _rwsel('rw_wind_osc_time', 'Oscillation time', _rwtimes) + '</div>'
                '<div style="color:#666; font-size:0.85em; margin:10px 0 4px;">Clouds</div>'
                + _row + _rwsel('rw_clouds_type', 'Clouds', [(0, 'No clouds'), (1, 'Cumulus'), (2, 'Stratus')])
                + _rwnum('rw_clouds_density', 'Density', 0, 100, 1, 80, '%')
                + _rwnum('rw_clouds_min', 'Min. height', 0, 20000, 1, 90, 'm') + _rwnum('rw_clouds_max', 'Max. height', 0, 20000, 1, 90, 'm')
                + '<label style="font-size:0.85em; color:#333;"><input type="checkbox" name="s_rw_rain" value="1"'
                + (' checked' if str(_rwv.get('rw_rain', 0)) in ('1', 'True') else '') + '> Rain'
                + ' <span style="color:#999;">(the game only allows rain with Stratus clouds)</span></label></div>'
                # v949f5 ARENA WORLD CLOCK: the server keeps the arena's time of day running from the start
                # time above (day at Time speed, 18:00-06:00 at Time speed x Night speed) and serves every
                # joiner the CURRENT time, so a fresh pilot gets the same dusk as the ones already flying.
                + '<div style="margin:6px 0;"><label style="font-size:0.85em; color:#333;"><input type="checkbox" name="s_clock_static" value="1"'
                + (' checked' if str(overrides.get('clock_static', '')) in ('1', 'True') else '')
                + '> Reset the clock to the start time on every arena entry'
                + ' <span style="color:#999;">(unticked = the arena clock runs on by itself; a joiner gets the current time of day. '
                  'The clock re-starts at an arena reset or the console\'s <code>clock &lt;room&gt; reset</code>.)</span></label></div>'
                # v962f5 DYNAMIC WEATHER: the server changes clouds / rain live (msg 137) every N minutes,
                # walking a clear -> scattered -> broken -> overcast -> rain -> storm ladder one rung at a time
                + '<div style="margin:10px 0;"><label style="font-size:0.85em; color:#333;">Dynamic weather: change the clouds and rain every '
                + '<input type="number" name="s_weather_cycle" min="0" max="240" value="' + hesc(str(overrides.get('weather_cycle', '') or ''), quote=True) + '" '
                  'placeholder="0" style="width:70px; padding:4px;"> minutes'
                + ' <span style="color:#999;">(0 = fixed weather as set above. The live change goes to everyone in the arena at once - no re-entry - '
                  'and is announced as an AI line <code>WEATHER: ...</code>; it walks one step at a time between clear skies and a rain storm, '
                  'starting from the setting above. Console: <code>weather &lt;room&gt; status|clear|scattered|broken|overcast|rain|storm|reset</code>.)</span></label>'
                + '<label style="font-size:0.85em; color:#333; display:block; margin-top:6px;">Max wind for the dynamic weather: '
                + '<input type="number" name="s_weather_max_wind" min="0" max="60" step="0.5" value="' + hesc(str(overrides.get('weather_max_wind', '') or ''), quote=True) + '" '
                  'placeholder="8" style="width:70px; padding:4px;"> m/s'
                + ' <span style="color:#999;">(the cycle blows harder as the weather worsens - 2 m/s clear to 12 m/s storm - but never above this, so nobody is '
                  'blown off the runway; 8 m/s = 18 mph. 0 = the cycle leaves the wind as set above. The direction drifts up to 30&deg; per step.)</span></label></div>'
                # per-type field enabling, mirroring the client's own dialog: Constant = speed + direction;
                # Const. rotating = speed + rotation time; Oscill. rotating = min/max + oscillation + rotation
                '<script>(function(){var f=document.forms[0];function u(){var t=f.s_rw_wind_type.value;'
                'var on={s_rw_wind_speed:t!="2",s_rw_wind_dir:t=="0",s_rw_wind_rot_time:t!="0",'
                's_rw_wind_min:t=="2",s_rw_wind_max:t=="2",s_rw_wind_osc_time:t=="2",s_rw_rain:f.s_rw_clouds_type.value=="2"};'
                'for(var k in on){var e=f[k];if(e){e.disabled=!on[k];e.style.opacity=on[k]?"1":"0.45";}}}'
                'f.s_rw_wind_type.addEventListener("change",u);f.s_rw_clouds_type.addEventListener("change",u);'
                'f.addEventListener("submit",function(){for(var i=0;i<f.elements.length;i++)f.elements[i].disabled=false;});u();})();</script>')
            # RADAR (v949f5): the server-side radar-failure gate (peer planes beyond visual range are
            # relayed only inside a standing radar of the viewer's camp) + the GAME_DEF [Radar] block
            # the client draws the rings and tests its map icons with. Defaults from radar_read.
            _rdb = {}
            try:
                if SRV.get('radar_read') and gdef:
                    _rdb = SRV['radar_read'](bytes(gdef)) or {}
            except Exception:
                _rdb = {}
            _rdv = dict(_rdb); _rdv.update({k: v for k, v in overrides.items() if k.startswith('rd_')})
            rd_on = bool(overrides.get('rd_enabled'))
            rd_edited = ' &bull; <span style="color:#c60;">edited</span>' if ('rd_enabled' in overrides or 'radar_enabled' in overrides) else ''
            def _rdi(key, dflt=''):
                v = _rdv.get(key, dflt)
                return hesc('' if v is None else str(v), quote=True)
            def _rdnum(key, label, lo, hi, step=1, width=90, unit=''):
                return ('<label style="font-size:0.85em; color:#333;">' + label + '<br>'
                        '<input type="number" min="' + str(lo) + '" max="' + str(hi) + '" step="' + str(step) + '" '
                        'name="s_' + key + '" value="' + _rdi(key) + '" style="width:' + str(width) + 'px; padding:6px;">'
                        + (' <span style="color:#999;">' + unit + '</span>' if unit else '') + '</label>')
            def _rdsel(key, label, opts, cur):
                h = '<label style="font-size:0.85em; color:#333;">' + label + '<br><select name="s_' + key + '" style="padding:6px;">'
                for val, text in opts:
                    h += '<option value="' + str(val) + '"' + (' selected' if str(cur) == str(val) else '') + '>' + hesc(text) + '</option>'
                return h + '</select></label>'
            def _rdchk(key, label, note=''):
                return ('<label style="font-size:0.85em; color:#333;"><input type="checkbox" name="s_' + key + '" value="1"'
                        + (' checked' if str(_rdv.get(key, 0)) in ('1', 'True') else '') + '> ' + label
                        + (' <span style="color:#999;">' + note + '</span>' if note else '') + '</label>')
            _rg_en = str(overrides.get('radar_enabled', '') if overrides.get('radar_enabled', '') is not None else '')
            _rg_fr = str(overrides.get('radar_friends', '') if overrides.get('radar_friends', '') is not None else '')
            _rg_vis = overrides.get('radar_visual_m', '')
            radar_html = (
                '<div style="margin:8px 0 14px 0;">'
                + _row + _rdsel('radar_enabled', 'Radar failure (server gate)',
                                [('', 'Arena default (on in Territorial Combat)'), ('1', 'On'), ('0', 'Off')], _rg_en)
                + '<label style="font-size:0.85em; color:#333;">Always visible within<br>'
                  '<input type="number" min="1000" max="100000" step="500" name="s_radar_visual_m" value="'
                + hesc('' if _rg_vis in (None, '') else str(_rg_vis), quote=True)
                + '" placeholder="15000" style="width:100px; padding:6px;"> <span style="color:#999;">m of the pilot</span></label>'
                + _rdsel('radar_friends', 'Outside coverage, hide', [('', 'All aircraft (the game\'s rule)'), ('1', 'All aircraft'), ('0', 'Enemy aircraft only')], _rg_fr)
                + '<label style="font-size:0.85em; color:#333;">Under the radar below<br>'
                  '<input type="number" min="0" max="5000" step="10" name="s_radar_agl_m" value="'
                + hesc('' if overrides.get('radar_agl_m', '') in (None, '') else str(overrides.get('radar_agl_m')), quote=True)
                + '" placeholder="150" style="width:90px; padding:6px;"> <span style="color:#999;">m above terrain (500 ft = 152 m)</span></label>'
                + '</div>'
                + '<label style="font-size:0.9em;">'
                '<input type="checkbox" name="s_rd_enabled" value="1"' + (' checked' if rd_on else '') +
                '> Override the arena\'s [Radar] block (rings and map icons on the client)' + rd_edited + '</label>'
                + _row + _rdnum('rd_always_vis', 'Always visible range', 0, 100000, 100, 100, 'm')
                + _rdnum('rd_range_mult', 'Radar range multiplier', 0.1, 10, 0.1, 80, 'x (Antenna 50 km)')
                + _rdnum('rd_above_terrain', 'Under the radar below', 0, 5000, 10, 90, 'm above terrain')
                + _rdsel('rd_show_range', 'Draw rings for', [(0, 'none'), (1, 'friends'), (2, 'enemies'), (3, 'all')], _rdv.get('rd_show_range', 3))
                + '</div>' + _row
                + _rdchk('rd_works', 'Radar works', '(off = no radar layer at all)')
                + _rdchk('rd_apply_local', 'Low flyers under the radar', '(hides planes beyond the always-visible range that fly below the level above)')
                + '</div></div>')
            # TOURNAMENT (v952f5): the arena-creation dialog's Tournament group, served into the GAME_DEF
            # [Tournament] block (tn_* keys; '' = template value). Defaults from tournament_read.
            _tnb = {}
            try:
                if SRV.get('tournament_read') and gdef:
                    _tnb = SRV['tournament_read'](bytes(gdef)) or {}
            except Exception:
                _tnb = {}
            _tnv = dict(_tnb); _tnv.update({k: v for k, v in overrides.items() if (k.startswith('tn_') or k.startswith('ev_')) and v not in (None, '')})
            tn_edited = ' &bull; <span style="color:#c60;">edited</span>' if any(k.startswith('tn_') for k in overrides) else ''
            ev_edited = ' &bull; <span style="color:#c60;">edited</span>' if any(k.startswith('ev_') for k in overrides) else ''
            def _tnchk(key, label, note=''):
                return ('<label style="font-size:0.85em; color:#333;"><input type="checkbox" name="s_' + key + '" value="1"'
                        + (' checked' if str(_tnv.get(key, 0)) in ('1', 'True') else '') + '> ' + label
                        + (' <span style="color:#999;">' + note + '</span>' if note else '') + '</label>')
            def _tnnum(key, label, lo, hi, unit=''):
                v = _tnv.get(key, '')
                return ('<label style="font-size:0.85em; color:#333;">' + label + '<br>'
                        '<input type="number" min="' + str(lo) + '" max="' + str(hi) + '" step="1" name="s_' + key
                        + '" value="' + hesc('' if v is None else str(v), quote=True) + '" style="width:80px; padding:6px;">'
                        + (' <span style="color:#999;">' + unit + '</span>' if unit else '') + '</label>')
            tournament_html = (
                '<div style="margin:8px 0 14px 0;">' + _row
                + _tnchk('tn_enabled', '<b>Tournament mode enabled</b>', tn_edited)
                + _tnnum('tn_lives', 'Number of lives', 0, 99, '(0 = unlimited)')
                + _tnchk('tn_ghosting', 'Ghosting', '(out of lives = fly on as a ghost)')
                + '</div>' + _row
                + _tnnum('tn_start_delay', 'Joining window', 0, 240, 'min from the start')
                + _tnnum('tn_shoot_delay', 'Shooting starts', 0, 240, 'min after joining closes')
                + _tnchk('tn_allow_tabbing', 'Allow tabbing out', '(exiting to HQ does not cost a life)')
                + _tnchk('tn_last_is_winner', 'Last one flying wins', '(the server announces the winner)')
                + '</div>'
                + '<div style="margin:14px 0 6px 0; font-weight:bold;">Event mode (weapons lock)' + ev_edited + '</div>' + _row
                + _tnchk('ev_enabled', '<b>Event mode: weapons and engines locked until the host starts the event</b>',
                         '(##StartEvent / <code>event start &lt;room&gt;</code> frees them, <code>event stop &lt;room&gt;</code> locks again; off = no event timers at all)')
                + _tnnum('ev_start_delay', 'Unlock', 0, 240, 'min after the event start')
                + _tnchk('ev_fly_button', 'Fly button enabled from the start', '(untick = greyed until ##EnableFlyButton / <code>event fly on</code>)')
                + '</div>' + _row
                + _tnnum('ev_length', 'Event length', 0, 1440, 'min from the start of the fight (0 = until ended by hand); the server ends it: tournament finished, weapons locked')
                + '</div>'
                + '<div style="margin:14px 0 6px 0; font-weight:bold;">Event script (scoring rules, objectives, victory)</div>'
                + '<p style="color:#888; font-size:0.85em; max-width:640px;">JSON. Scoring starts when the fight starts '
                  '(<code>event fight</code>, or the tournament countdown) and ends with the event length or <code>event end</code>; '
                  'every award is announced, a progress report goes out every <code>report_min</code> minutes, and the team with the '
                  'most points (or kills) wins. Team keys: US GB SU GE JP. Point keys: kill_fighter, kill_bomber, kill_any, '
                  'scene_trigger, scene_capture, capture_specific {\"scene\": pts}, hold_specific {\"scene\": pts per minute}, '
                  'scene_damage (per 1 %), damage_specific {\"scene\": pts per 1 %}, bridge, tank, train, troops_drop, supply_delivered / supply_airdrop (per tonne), supply_specific {\"scene\": pts per tonne}, building_repaired; objectives: '
                  'chute_on_target (target pilot, radius_m, points), kill_target = fox hunt (target pilot, points). mode: team (default) or personal - in a personal event every pilot scores for themselves and the top pilot wins. Leave empty for no script.</p>'
                + EVS_BUILDER_HTML
                + '<div style="font-size:0.85em; margin-top:6px;"><b>JSON</b> (what is saved - edit by hand or use the builder above; the form follows what you type here, '
                + '<a href="#" onclick="ebLoad();return false;">&uarr; reload the form from this box</a>)</div>'
                + '<textarea name="s_ev_script" rows="14" spellcheck="false" style="width:100%; max-width:720px; font-family:monospace; font-size:0.85em; padding:6px;">'
                + hesc(str(overrides.get('ev_script', '') or '')) + '</textarea>'
                + '<details style="margin:8px 0;"><summary style="cursor:pointer; color:#2c5f8a;">Example scripts (click to copy from)</summary>'
                + '<p style="margin:6px 0 2px;"><b>Battle of Britain</b> - two teams, different objectives and point tables</p>'
                + '<pre style="background:#f4f6f8; padding:8px; font-size:0.8em; overflow:auto;">' + hesc(EVS_EX_BOB) + '</pre>'
                + '<p style="margin:6px 0 2px;"><b>Pin Point Parachuting</b> - personal event: bail out and land on the plane of PPS@HQ</p>'
                + '<pre style="background:#f4f6f8; padding:8px; font-size:0.8em; overflow:auto;">' + hesc(EVS_EX_PPS) + '</pre>'
                + '<p style="margin:6px 0 2px;"><b>Capture the front</b> - one shared table for every team, a key scene</p>'
                + '<pre style="background:#f4f6f8; padding:8px; font-size:0.8em; overflow:auto;">' + hesc(EVS_EX_TC) + '</pre>'
                + '<p style="margin:6px 0 2px;"><b>Fox hunt</b> - personal event: whoever shoots down FOX@FA scores a point; half a point per ordinary kill</p>'
                + '<pre style="background:#f4f6f8; padding:8px; font-size:0.8em; overflow:auto;">' + hesc(EVS_EX_FOX) + '</pre>'
                + '</details>'
                + '</div>')
            # FIGHTERS ONLY (v391): opt-in checkbox. The game server hides every non-fighter
            # (bombers, attackers, transports - the BOMBER_PLANE_IDS scoring classification)
            # via the same camp-7/byte0 mechanism as the war-date filter.
            fo_on = bool(overrides.get('fighters_only'))
            fo_edited = ' &bull; <span style="color:#c60;">edited</span>' if 'fighters_only' in overrides else ''
            fighters_html = (
                '<label style="display:block; margin:12px 0; font-weight:bold;">'
                '<input type="checkbox" name="s_fighters_only" value="1"'
                + (' checked' if fo_on else '') + '> Fighters only'
                + fo_edited + '</label>')
            # EXIT = CRASH (v400f5): opt-in checkbox. When ON, leaving the plane while airborne
            # counts as a crash/death; the pilot must land (and be undamaged) to exit for free.
            # When OFF (default), an undamaged in-flight exit is a clean bug-out - no death.
            ec_on = bool(overrides.get('exit_is_crash'))
            ec_edited = ' &bull; <span style="color:#c60;">edited</span>' if 'exit_is_crash' in overrides else ''
            exitcrash_html = (
                '<label style="display:block; margin:12px 0; font-weight:bold;">'
                '<input type="checkbox" name="s_exit_is_crash" value="1"'
                + (' checked' if ec_on else '') + '> Exit while airborne counts as a crash'
                + ec_edited + '</label>')
            # SHOW GROUND OBJECTS (v719f5): the map draws tank / train / soldier icons only when this
            # [UI] flag is set. The templates ship it OFF; default ON here (checked when unset).
            _sgo_key = 'show_ground_objects'
            _sgo_on = bool(int(overrides.get(_sgo_key, 1))) if _sgo_key in overrides else True
            _sgo_edited = ' &bull; <span style="color:#c60;">edited</span>' if _sgo_key in overrides else ''
            showground_html = (
                '<label style="display:block; margin:12px 0; font-weight:bold;">'
                '<input type="checkbox" name="s_show_ground_objects" value="1"'
                + (' checked' if _sgo_on else '') + '> Show tanks / trains / soldiers on the map'
                + _sgo_edited + '</label>')
            # SCORING (v404f5): per-arena override of the category-decided scoring mode.
            # '' / absent = decided by the Title/category; 'ffa'/'tc' force that value column;
            # 'none' turns global scoring off for this arena. The game server checks this key
            # FIRST, so it wins over the category.
            sm = str(overrides.get('scoring_mode', '') or '')
            sm_edited = ' &bull; <span style="color:#c60;">edited</span>' if 'scoring_mode' in overrides else ''
            _cl = (str(category) or '').lower()
            _ref_sc = _scoring_ref() or {}
            _ev_col = str(_ref_sc.get('modes', {}).get('events_table', 'ffa')).upper()
            if 'dogfight' in _cl:      eff = 'FFA values'
            elif 'territorial' in _cl: eff = 'TC values'
            elif 'event' in _cl:       eff = 'Events (' + _ev_col + ' values)'
            else:                      eff = 'no global scoring'
            def _sm_opt(v, label):
                s = ' selected' if sm == v else ''
                return '<option value="' + v + '"' + s + '>' + label + '</option>'
            scoring_html = (
                '<label style="display:block; margin:12px 0;">Scoring mode' + sm_edited + '<br>'
                '<select name="s_scoring_mode" style="padding:7px; margin-top:3px; min-width:340px;">'
                + _sm_opt('',     'Default - by Title/category (currently: ' + eff + ')')
                + _sm_opt('ffa',  'Force FFA values')
                + _sm_opt('tc',   'Force TC values')
                + _sm_opt('events', 'Force Events board')
                + _sm_opt('none', 'Force NO global scoring')
                + '</select></label>')
            # TC ECONOMY (v960f5c): production, supplies, trains, tank battalions - its own switch,
            # independent of which ladder the arena scores on (a Battle of Britain event arena is a TC
            # world scored on the Events board).
            _eco = str(overrides.get('economy', '') or '').lower()
            def _eco_opt(v, label):
                return '<option value="' + v + '"' + (' selected' if _eco == v else '') + '>' + label + '</option>'
            scoring_html += (
                '<label style="display:block; margin:12px 0;">Territorial Combat economy<br>'
                '<select name="s_economy" style="padding:7px; margin-top:3px; min-width:340px;">'
                + _eco_opt('',    'Auto - on when the arena scores on the TC board (currently: ' + ('ON' if (sm == 'tc' or (sm == '' and 'territorial' in _cl)) else 'off') + ')')
                + _eco_opt('on',  'On - production, supplies, trains, tank battalions, country scores')
                + _eco_opt('off', 'Off - arcade: full service at every field, no AI ground war')
                + '</select></label>'
                # v968f5z: same-side kills. Default follows the arena's camps block exactly as the
                # client does (one alliance group = free-for-all, everyone hostile, kills count).
                + '<label style="display:block; margin:12px 0;">Same-side kills<br>'
                '<select name="s_team_kills" style="padding:7px; margin-top:3px; min-width:340px;">'
                + ''.join('<option value="' + v + '"' + (' selected' if str(overrides.get('team_kills', '') or '').lower() == v else '') + '>' + l + '</option>'
                          for v, l in (('', 'Default - from the arena camps (one alliance group = free-for-all, kills count)'),
                                       ('everyone', 'Everyone is a target - same-side kills count'),
                                       ('teams', 'Teams - a same-side kill is a death with no credit')))
                + '</select></label>'
                '<p class="muted" style="margin:-6px 0 12px; max-width:640px;">Needs the terrain\'s map data '
                '(trn_tables / scene profiles, rails for trains - see ADDING_A_MAP.md). Pilots inside the arena '
                'see the change at their next spawn; trains and production start within a minute.</p>')
            # TC WIN / RESET (v640f5): tc_win_mode + a Reset button (calls the game server's arena_reset)
            _wm = str(overrides.get('tc_win_mode', 'off') or 'off').lower()
            if _wm == 'wipeout':
                _wm = 'eliminated'                 # v933f5: the old mode name maps to the new rule
            def _wm_opt(v, label):
                s = ' selected' if _wm == v else ''
                return '<option value="' + v + '"' + s + '>' + label + '</option>'
            winmode_html = (
                '<label style="display:block; margin:12px 0;">Win condition<br>'
                '<select name="s_tc_win_mode" style="padding:7px; margin-top:3px; min-width:340px;">'
                + _wm_opt('off', 'Off - the arena runs until reset by hand')
                + _wm_opt('all', 'One country owns every scene -> it has won, arena resets')
                + _wm_opt('eliminated', 'One country is eliminated (has no scenes left) -> the country holding the most scenes has won, arena resets')
                + '</select></label>'
                '<div style="margin:8px 0 16px;"><a href="/admin/arena_reset?room=' + str(room_id) + '" '
                'onclick="return confirm(\'Reset this arena now? Everyone in it is sent back to the lobby after a 3 s countdown.\');" '
                'class="btn-red" style="padding:8px 18px;">Reset arena now</a>'
                ' &nbsp; <a href="/admin/arena_reset?room=' + str(room_id) + '&winner=ask" style="color:#666;">announce a winner first...</a></div>')
            # RUNWAY CRATERS (v686f5): per-arena CratersVanishDelay (minutes) / CratersVanishNumber
            _cvd = overrides.get('craters_vanish_min', '')
            _cvn = overrides.get('craters_vanish_max', '')
            _cv_def = (SRV.get('craters_defaults') or (lambda: (10, 40)))()
            craters_html = (
                '<label style="display:block; margin:10px 0;">Craters vanish tick (minutes between ticks)<br>'
                '<input type="number" name="s_craters_vanish_min" min="1" max="120" value="' + hesc(str(_cvd), quote=True) + '" '
                'placeholder="' + str(_cv_def[0]) + '" style="width:120px; padding:6px;"></label>'
                '<label style="display:block; margin:10px 0;">Crater volume removed per tick<br>'
                '<input type="number" name="s_craters_vanish_max" min="1" max="1000" value="' + hesc(str(_cvn), quote=True) + '" '
                'placeholder="' + str(_cv_def[1]) + '" style="width:120px; padding:6px;"></label>'
                '<p class="muted" style="margin:4px 0 12px; max-width:640px;">Every tick, each map square removes '
                '<b>volume-per-tick</b> from its <b>oldest craters first</b> (whole craters, the last one partly). A 500 lb crater is '
                '10 volume, a 1,000 lb one 15. So a bombed square clears at <b>volume &divide; minutes</b> per minute, and the n-th '
                'oldest crater lasts about <b>n &times; 10 &divide; volume &times; minutes</b>. For 15 &times; 500 lb on one runway: '
                '1 min / 5 &rarr; first gone at 2 min, last at 30; 1 min / 10 &rarr; one crater a minute; 2 min / 4 &rarr; last one at 75 min; '
                '10 min / 40 &rarr; four craters at the first tick.</p>')
            # SUPPLY TRAINS PER TEAM (v959f5): trains_per_camp - the floor of supply trains each
            # team runs (one per rail line is always guaranteed on top of it).
            _tpc = overrides.get('trains_per_camp', '')
            craters_html += (
                '<label style="display:block; margin:10px 0;">Supply trains per team<br>'
                '<input type="number" name="s_trains_per_camp" min="0" max="12" value="' + hesc(str(_tpc), quote=True) + '" '
                'placeholder="3" style="width:120px; padding:6px;"></label>'
                '<p class="muted" style="margin:4px 0 12px; max-width:640px;">Every team gets at least this many supply trains '
                '(default 3), and in any case one per rail line it holds. Trains start at the team\'s depots (factory, port, rail '
                'yard nearest its bomber field), its front airfields and halfway between, on each line in turn. Stations are only '
                'scenes that store or produce something - AA sites and villages are passed through. 0 = no supply trains in this arena. '
                'Needs a rails file for the terrain (rails_trnNN.json).</p>')
            # SUPPLY MODE (v964f5): trains (classic TC), road convoys of lorries, or both; convoy cadence
            # and the on-demand rule (a scene whose stores are shot up calls a convoy).
            _smode = str(overrides.get('supply_mode', 'train') or 'train').lower()
            def _sm_opt(v, label):
                return '<option value="' + v + '"' + (' selected' if _smode == v else '') + '>' + label + '</option>'
            _cvm = overrides.get('convoy_minutes', '')
            _cod = overrides.get('convoy_on_demand', 'on')
            craters_html += (
                '<label style="display:block; margin:10px 0;">Supply traffic<br>'
                '<select name="s_supply_mode" style="padding:7px; margin-top:3px; min-width:340px;">'
                + _sm_opt('train', 'Trains only (classic Territorial Combat; lorries only as the on-demand safety net below)')
                + _sm_opt('car',   'Road convoys only (lorry columns with AA escort, depot to scene overland)')
                + _sm_opt('both',  'Trains and road convoys')
                + '</select></label>'
                '<label style="display:block; margin:10px 0;">Convoy every (minutes, per team)<br>'
                '<input type="number" name="s_convoy_minutes" min="2" max="120" value="' + hesc(str(_cvm), quote=True) + '" '
                'placeholder="10" style="width:120px; padding:6px;"></label>'
                '<label style="display:block; margin:10px 0;">Convoy escort (the cars that shoot back)<br>'
                '<select name="s_convoy_escort" style="padding:7px; margin-top:3px; min-width:340px;">'
                + ''.join('<option value="' + v + '"' + (' selected' if str(overrides.get('convoy_escort', 'both') or 'both').lower() == v else '') + '>' + l + '</option>'
                          for v, l in (('both', 'AA car in front and Flak car at the tail (default)'), ('aa', 'AA car only (machine guns)'),
                                       ('flak', 'Flak car only'), ('none', 'No escort - lorries alone')))
                + '</select></label>'
                '<p class="muted" style="margin:-6px 0 12px; max-width:640px;">The escorts\' guns are driven by each pilot\'s own client '
                'and obey the AA / Flak gunner sliders on the Game Settings tab (there is no separate car-gun setting in the game); this '
                'knob decides how many guns a convoy brings.</p>'
                '<label style="display:block; margin:10px 0;"><input type="checkbox" name="s_convoy_on_demand" value="1"'
                + (' checked' if str(_cod).lower() in ('1', 'on', 'true', 'yes') else '') + '> '
                'On-demand convoys (works in every mode, trains-only included): a scene whose fuel/ammo/metal store falls '
                'below 35% - bombed or drained by refuelling - or whose storage has been destroyed, calls a convoy from the '
                'best friendly depot within 120 km, whatever the trains are doing (one per scene per 10 min, 2 per team at once; '
                'a bombed-out field also gets the metal to rebuild its tanks)</label>'
                '<p class="muted" style="margin:4px 0 12px; max-width:640px;">A convoy is a WWII-style road serial: an AA lorry '
                'in front, 2-6 cargo lorries (fuel tankers 3,000 kg, ammunition 3,000 kg, box lorry 2,500 kg metal) at 60 m '
                'interval, a Flak lorry at the tail, 40 km/h overland from depot to scene (the tank driver: path-finding around obstacles). It unloads at the '
                'depot, waits a minute and drives home empty - a target both ways; every lorry destroyed is cargo the front '
                'does not get. Teams hear their own convoys on the AI channel. Needs the car classes in tank_tables.json.</p>')
            # NAVAL TASK GROUPS (v968f5b): a fleet script - carrier groups on patrol with escorts in formation,
            # for open-water maps with no ports; overrides mapdata/fleets_trnNN.json for this arena.
            _fs = str(overrides.get('fleet_script', '') or '')
            craters_html += (
                '<label style="display:block; margin:14px 0 4px;">Naval task groups (fleet script, JSON - leave empty to use the terrain\'s mapdata/fleets_trnNN.json)<br>'
                '<textarea name="s_fleet_script" rows="8" style="width:100%; max-width:640px; font-family:monospace; font-size:12px; padding:6px; margin-top:3px;" '
                'placeholder=\'{"groups": [{"name": "TF-58", "camp": 0, "flagship": "carrier", "escorts": ["cruiser", "cruiser", "battle"], '
                '"formation": "ring", "spacing": 700, "spawn": [x, y], "heading": 270, "speed": 12, "patrol": [[x, y], [x, y], [x, y]], '
                '"loop": true, "respawn_min": 30, "enabled": true}]}\'>' + hesc(_fs) + '</textarea></label>'
                '<p class="muted" style="margin:0 0 12px; max-width:640px;">Each group is a flagship (carrier = a floating airfield pilots can '
                'spawn on, with its take-off queue) steaming a patrol - a closed loop of open-sea points (loop true) or there and back - at '
                '<i>speed</i> m/s, with the escorts (battle, cruiser, cargo, uboat; a type picks the team\'s own nation) holding station in a '
                'ring, column or line at <i>spacing</i> metres. Groups are raised when pilots are in the arena and re-raised <i>respawn_min</i> '
                'after the whole group is gone. Coordinates are world metres (x east, y north) - check them with the console: '
                '<code>ship ports &lt;room&gt;</code>, <code>navy script &lt;room&gt;</code>, <code>navy spawn &lt;room&gt; &lt;name&gt;</code>.</p>')
            # ARENA PASSWORD (client-side gate). Current value = the editor's override if one has
            # been set, else the password the arena was CREATED with (read from the blob via the
            # game-server bridge). The field is pre-filled with that value so an unchanged save
            # round-trips it; clearing it (or unticking the box) removes protection.
            if 'password' in overrides:
                cur_pw = str(overrides.get('password') or '')
            else:
                cur_pw = ''
                try:
                    if SRV.get('password_read') and gdef:
                        cur_pw = SRV['password_read'](bytes(gdef)) or ''
                except Exception:
                    cur_pw = ''
            pw_on = bool(cur_pw)
            pw_edited = ' &bull; <span style="color:#c60;">edited</span>' if 'password' in overrides else ''
            password_html = (
                '<label style="display:block; margin:12px 0; font-weight:bold;">'
                '<input type="checkbox" name="s_password_protected" value="1"'
                + (' checked' if pw_on else '') + '> Password protected'
                + pw_edited + '</label>'
                '<label style="display:block; margin:8px 0; font-size:0.9em; color:#333;">Arena password<br>'
                '<input type="text" name="s_password" value="' + hesc(str(cur_pw), quote=True) + '" '
                'autocomplete="off" style="width:240px; padding:6px;"></label>')
            # AIRCRAFT PER TEAM (v932f5): a checklist of every aircraft x the five nations. Default
            # ticks = the server's nation table; the arena stores only the planes that differ
            # (settings_json 'plane_teams' = {name: [camps]}, [] = hidden from everyone). The game
            # server turns the ticks into the GAME_DEF byte-0 flyability mask at serve time.
            planes_html = ''
            _pt_over = overrides.get('plane_teams') if isinstance(overrides.get('plane_teams'), dict) else {}
            try:
                _roster = SRV['plane_roster']() if SRV.get('plane_roster') else []
            except Exception:
                _roster = []
            if _roster:
                _NAT = [(0, 'US'), (1, 'GB'), (2, 'SU'), (3, 'GE'), (4, 'JP')]
                _nat_name = {0: 'United States', 1: 'Great Britain', 2: 'Soviet Union', 3: 'Germany', 4: 'Japan', 7: 'Staff / neutral (hidden by default)'}
                _groups = {}
                for slot, name, dcamp, is_bomber, year in _roster:
                    _groups.setdefault(dcamp if dcamp in (0, 1, 2, 3, 4) else 7, []).append((slot, name, dcamp, is_bomber, year))
                _pt_edited = ' &bull; <span style="color:#c60;">' + str(len(_pt_over)) + ' plane(s) edited</span>' if _pt_over else ''
                rows = ''
                for g in (0, 1, 2, 3, 4, 7):
                    if g not in _groups:
                        continue
                    rows += ('<tr style="background:#eef;"><td colspan="7" style="padding:6px 8px; font-weight:bold;">'
                             + hesc(_nat_name.get(g, str(g))) + ' &mdash; default aircraft</td></tr>')
                    for slot, name, dcamp, is_bomber, year in _groups[g]:
                        if name in _pt_over:
                            cur_set = set(int(c) for c in _pt_over[name] if str(c).lstrip('-').isdigit())
                            mark = ' <span style="color:#c60;" title="edited for this arena">&#9998;</span>'
                        else:
                            cur_set = {dcamp} if dcamp in (0, 1, 2, 3, 4) else set()
                            mark = ''
                        cells = ''
                        for c, tag in _NAT:
                            cells += ('<td style="text-align:center;"><input type="checkbox" class="pt pt-c' + str(c) + '" '
                                      'name="pt_' + str(slot) + '_' + str(c) + '" value="1"'
                                      + (' checked' if c in cur_set else '')
                                      + ' data-def="' + ('1' if (dcamp == c) else '0') + '"></td>')
                        rows += ('<tr><td style="padding:3px 8px; white-space:nowrap;">' + hesc(name) + mark
                                 + ('<span style="color:#888; font-size:0.8em;"> bomber/attacker</span>' if is_bomber else '')
                                 + ('<span style="color:#aaa; font-size:0.8em;"> ' + hesc(str(year)) + '</span>' if year else '')
                                 + '</td>' + cells + '<td></td></tr>')
                heads = ''.join('<th style="width:48px;">' + tag + '<br><a href="#" onclick="ptCol(' + str(c) + ',1);return false;" style="font-size:0.75em; font-weight:normal;">all</a> '
                                '<a href="#" onclick="ptCol(' + str(c) + ',0);return false;" style="font-size:0.75em; font-weight:normal;">none</a></th>' for c, tag in _NAT)
                planes_html = (
                    '<input type="hidden" name="pt_present" value="1">'
                    '<p style="margin:6px 0;">' + _pt_edited.lstrip(' &bull;') + '</p>'
                    '<div style="margin:6px 0 10px;">'
                    '<a href="#" onclick="ptReset();return false;" class="btn-red" style="padding:6px 14px; font-size:0.85em;">Reset all to the default nation table</a>'
                    ' &nbsp; <a href="#" onclick="ptToggle();return false;" style="font-size:0.85em;">show / hide the list</a></div>'
                    '<div id="ptbox" style="max-height:520px; overflow:auto; border:1px solid #ccc; padding:4px; display:'
                    + ('block' if _pt_over else 'none') + ';">'
                    '<table style="border-collapse:collapse; font-size:0.85em; min-width:560px;">'
                    '<tr style="position:sticky; top:0; background:#fff;"><th style="text-align:left; padding:4px 8px;">Aircraft</th>' + heads + '<th></th></tr>'
                    + rows + '</table></div>'
                    '<script>'
                    'function ptReset(){document.querySelectorAll("input.pt").forEach(function(e){e.checked=(e.getAttribute("data-def")=="1");});}'
                    'function ptCol(c,on){document.querySelectorAll("input.pt-c"+c).forEach(function(e){e.checked=!!on;});}'
                    'function ptToggle(){var b=document.getElementById("ptbox");b.style.display=(b.style.display=="none")?"block":"none";}'
                    '</script>')
            sel_open = 'selected' if status == 'open' else ''
            sel_closed = 'selected' if status != 'open' else ''
            content = f"""
                <style>
                  .tabbar{{display:flex; flex-wrap:wrap; gap:4px; border-bottom:2px solid #2c5f8a; margin:0 0 14px 0;}}
                  .tabbar a.tabbtn{{padding:8px 16px; border:1px solid #c9d6e2; border-bottom:none; border-radius:6px 6px 0 0; background:#eef3f7; color:#2c5f8a; text-decoration:none; font-weight:bold;}}
                  .tabbar a.tabbtn.active{{background:#2c5f8a; color:#fff; border-color:#2c5f8a;}}
                  .tabpane{{display:none;}} .tabpane.active{{display:block;}}
                  .tabpane h3{{margin-top:18px;}} .tabpane h3:first-child{{margin-top:4px;}}
                  .tabsave{{position:sticky; bottom:0; background:#fff; padding:12px 0 4px 0; border-top:1px solid #ddd; margin-top:18px;}}
                </style>
                <div class="nav"><a href="/admin">&larr; Back to Admin</a></div>
                <h1>Edit Arena &mdash; {hesc(str(rname))}</h1>
                <div class="card">
                <form method="POST" action="/admin/arena_settings">
                    <input type="hidden" name="room_id" value="{rid}">
                    <div class="tabbar"><a href="#general" class="tabbtn" data-tab="general" onclick="return arTab('general')">General</a><a href="#flight" class="tabbtn" data-tab="flight" onclick="return arTab('flight')">Flight & ground</a><a href="#aircraft" class="tabbtn" data-tab="aircraft" onclick="return arTab('aircraft')">Aircraft</a><a href="#world" class="tabbtn" data-tab="world" onclick="return arTab('world')">World & radar</a><a href="#events" class="tabbtn" data-tab="events" onclick="return arTab('events')">Events</a></div>
                    <div class="tabpane" id="tab-general">
                    <h3 >General</h3>
                    <label style="display:block; margin:10px 0;">Name<br>
                        <input type="text" name="room_name" value="{hesc(str(rname), quote=True)}" style="width:280px; padding:6px;"></label>
                    <label style="display:block; margin:10px 0;">Title (arena-list section header)<br>
                        <input type="text" name="category" value="{hesc(str(category), quote=True)}" style="width:280px; padding:6px;"></label>
                    <label style="display:block; margin:10px 0;">Status<br>
                        <select name="status" style="padding:7px;"><option value="open" {sel_open}>open</option><option value="closed" {sel_closed}>closed</option></select></label>
                    <h3>Password protection</h3>
                    <p style="color:#888; font-size:0.85em; max-width:560px;">Tick to require a password to join this arena, and set it below (the client prompts for it &mdash; enforcement is client-side, exactly as when the arena was created). Untick, or clear the field, to remove protection. The password shown is the current one; change it and Save to change what players must type. Takes effect the next time the arena is entered.</p>
                    {password_html}
                    <h3>Scoring</h3>
                    <p style="color:#888; font-size:0.85em; max-width:560px;">Which value table this
                    arena scores with. <em>Default</em> follows the Title/category (Dogfighting &rarr;
                    FFA, Territorial Combat &rarr; TC, Events &rarr; the server's events column,
                    anything else &rarr; no global scoring). Forcing a mode here overrides the
                    category for this arena only. See the <a href="/scoring">Scoring Reference</a>
                    for the tables. Takes effect on the next death in the arena.</p>
                    {scoring_html}
                    <h3>Win condition &amp; reset</h3>
                    <p style="color:#888; font-size:0.85em; max-width:560px;">Territorial Combat: when the
                    chosen condition is met the server announces the winner, then <em>Arena reset, please
                    leave the arena</em>, counts down and sends everyone to the lobby, and rebuilds the
                    arena from its GAME_DEF (ownership, stores, units, AI units). The button does the
                    same immediately, without a winner.</p>
                    {winmode_html}
                    </div>
                    <div class="tabpane" id="tab-flight">
                    <h3>Arena settings</h3>
                    <p style="color:#888; font-size:0.85em; max-width:560px;">All values in <strong>feet</strong>. Leave a field blank to keep the value the arena was created with. Changes are written into the arena's GAME_DEF and take effect the next time the arena is entered (they are served fresh on entry).</p>
                    {fields_html}
                    <h3>Enemy defences (EvP)</h3>
                    <p style="color:#888; font-size:0.85em; max-width:560px;">Strength of the terrain's automatic anti-aircraft defences that fire at players (0 = off, 6 = strongest). Applied the next time the arena is entered.</p>
                    {evp_html}
                    <h3>Exit = crash</h3>
                    <p style="color:#888; font-size:0.85em; max-width:560px;">Tick to make LEAVING THE PLANE WHILE AIRBORNE count as a crash (a death and a lost plane) &mdash; pilots must land, and be undamaged, to exit for free. Leave unticked (the default) and an undamaged in-flight exit is a clean bug-out that costs nothing. An exit while <em>damaged</em> is a death either way. Takes effect the next time the arena is entered.</p>
                    {exitcrash_html}
                    <h3>Runway craters</h3>
                    <p style="color:#888; font-size:0.85em; max-width:560px;">How long bomb craters stay on the
                    ground before they are filled in, and how many the arena keeps at once. The room template
                    ships 1 minute / 10 craters, which makes runway bombing pointless; the server default is
                    shown as the placeholder. Leave blank for the server default. Takes effect the next time the
                    arena is entered.</p>
                    {craters_html}
                    <h3>Ground objects on the map</h3>
                    <p style="color:#888; font-size:0.85em; max-width:560px;">Territorial Combat: tick to show
                    tanks, supply trains and paratroops as icons on the in-game map (the arena templates ship
                    this off, so ground objects were invisible on the map). Takes effect the next time the
                    arena is entered.</p>
                    {showground_html}
                    
                    </div>
                    <div class="tabpane" id="tab-aircraft">
                    <h3>War date (plane era)</h3>
                    <p style="color:#888; font-size:0.85em; max-width:560px;">Tick to restrict this arena to aircraft that had entered service by the date below, and push that date into the arena so the client shows it too (e.g. a 1943 arena hides 1944+ planes). Leave unticked for no restriction (all planes &mdash; today's behaviour). A stopgap for standing arenas; takes effect the next time the arena is entered.</p>
                    {wardate_html}
                    <h3>Fighters only</h3>
                    <p style="color:#888; font-size:0.85em; max-width:560px;">Tick to hide every bomber, attacker and transport in this arena &mdash; a pure fighter-vs-fighter setup. Fighter-bombers on fighter airframes (e.g. Typhoon, the Bf-109 bomb variants, Hurr-IID) stay available. Combines freely with the war date above; takes effect the next time the arena is entered.</p>
                    {fighters_html}
                    <h3>Aircraft per team</h3>
                    <p style="color:#888; font-size:0.85em; max-width:640px;">Tick which aircraft each nation may fly in this arena &mdash; a plane can be opened to several nations (coalition) or to none (hidden). The ticks start from the server's nation table; only planes you change are stored for this arena. The war date and Fighters-only filters above still apply on top (they can only hide). Takes effect the next time the arena is entered.</p>
                    {planes_html}
                    </div>
                    <div class="tabpane" id="tab-world">
                    <h3>Date, time &amp; weather</h3>
                    <p style="color:#888; font-size:0.85em; max-width:640px;">What the client shows read-only under
                    Options &rarr; Misc: the arena's date and clock, time zone, time and night speed, position on the
                    globe, wind, clouds and rain. Untick to keep the arena template's own values. Takes effect the
                    next time the arena is entered (a client that stays in the arena keeps the old sky).</p>
                    {reality_html}
                    <h3>Radar</h3>
                    <p style="color:#888; font-size:0.85em; max-width:640px;">Radar failure: with the gate on, a plane
                    farther than the always-visible range is shown to a pilot only while a standing radar antenna of
                    his own side covers it (or it is within visual range of one of his side&#39;s installations) &mdash;
                    destroy the antenna and its ring goes grey and the contacts in it vanish from the map unless another
                    ring still reaches them. &quot;Under the radar&quot;: a plane lower than the given height above the
                    terrain is dropped from the map beyond the always-visible range even inside coverage (the client
                    tests the ground under it). The lower row edits the arena&#39;s own
                    [Radar] block: ring display, range multiplier (also used by the gate) and the altitude under which a
                    plane slips below the radar. Takes effect the next time the arena is entered.</p>
                    {radar_html}
                    </div>
                    <div class="tabpane" id="tab-events">
                    <h3>Tournament</h3>
                    <p style="color:#888; font-size:0.85em; max-width:640px;">The Tournament group of the game&#39;s
                    arena-creation dialog. The clock starts when the first pilot spawns (or with the console
                    <code>event open &lt;room&gt;</code>): pilots may join during the joining window, then
                    everybody flies unarmed until shooting starts (the cockpit shows both countdowns). Each pilot has
                    the given number of lives; out of lives he is either grounded or, with ghosting, flies on as a
                    ghost. With &quot;last one flying wins&quot; the server declares the winner when one pilot is left.
                    Event mode is the game&#39;s own weapons lock: the arena starts locked (nobody can start engines,
                    fire, launch rockets, drop bombs or troops - &quot;Event not started yet!&quot; on entry) until the host
                    starts the event (<code>event fight</code> on the console or ##StartEvent in game); <code>event
                    hold</code> locks it again. Arenas without the tick have no event timers at all. See EVENTS.md
                    for the command chain. Values take effect the next time the arena is entered.</p>
                    {tournament_html}
                    </div>
                    <div class="tabsave"><button type="submit" class="btn-green" style="width:auto; padding:10px 26px;">Save</button>
                        &nbsp; <a href="/admin" style="color:#666;">Cancel</a></div>
                </form>
                </div>
                <script>
                  function arTab(t){{
                    document.querySelectorAll('.tabpane').forEach(function(p){{p.classList.toggle('active', p.id==='tab-'+t);}});
                    document.querySelectorAll('.tabbar a.tabbtn').forEach(function(a){{a.classList.toggle('active', a.getAttribute('data-tab')===t);}});
                    try{{ localStorage.setItem('arena_tab', t); }}catch(e){{}}
                    if(history.replaceState){{ history.replaceState(null,'','#'+t); }}
                    return false;
                  }}
                  (function(){{
                    var t=(location.hash||'').replace('#','');
                    if(!document.getElementById('tab-'+t)){{ try{{ t=localStorage.getItem('arena_tab')||''; }}catch(e){{ t=''; }} }}
                    if(!document.getElementById('tab-'+t)){{ t='general'; }}
                    arTab(t);
                  }})();
                </script>
            """
            self.send_html(content)

        elif self.path == '/my_arenas':
            # A logged-in player's own arenas (those they created). Admins get a link to the
            # full admin panel instead. Reuses the same per-arena settings editor.
            if not user:
                self.send_response(302); self.send_header('Location', '/login'); self.end_headers(); return
            conn = sqlite3.connect(SRV['db_path'])
            rcols = [r[1] for r in conn.execute("PRAGMA table_info(rooms)").fetchall()]
            cat_sel = "COALESCE(category,'Custom Arenas')" if 'category' in rcols else "'Custom Arenas'"
            pw_sel  = "COALESCE(password_protected,0)" if 'password_protected' in rcols else "0"
            rows = []
            if 'account_name' in rcols:
                rows = conn.execute(
                    "SELECT room_id, COALESCE(room_name,''), COALESCE(status,'open'), "
                    "COALESCE(terrain,1), " + cat_sel + ", " + pw_sel + " FROM rooms WHERE account_name=? "
                    "ORDER BY created_at DESC", (user,)).fetchall()
            conn.close()
            if rows:
                items = ""
                for rid, rname, status, terrain, category, pwp in rows:
                    lock_badge = (' <span title="Password protected" style="color:#b8860b;">&#128274;</span>'
                                  if pwp else '')
                    items += (
                        '<div class="card" style="margin:10px 0;">'
                        '<div style="display:flex; justify-content:space-between; align-items:center;">'
                        '<div><strong>' + hesc(str(rname) or 'Unnamed') + '</strong>' + lock_badge
                        + '<br><small style="color:#888;">' + hesc(str(category))
                        + ' &middot; ' + hesc(str(status)) + ' &middot; terrain ' + str(terrain)
                        + ' &middot; id ' + str(rid) + '</small></div>'
                        '<a href="/admin/arena_settings?room=' + str(rid) + '" class="btn-green" '
                        'style="display:inline-block; width:auto; padding:8px 16px; text-decoration:none;">'
                        '&#9881; Edit Settings</a>'
                        '</div></div>')
            else:
                items = '<div class="card"><p style="color:#888;">You haven\'t created any arenas yet.</p></div>'
            admin_extra = ('<p><a href="/admin" style="color:#28a745;">Go to full Admin Panel &rarr;</a></p>'
                           if is_user_admin(user) else '')
            content = f"""
                <div class="nav"><a href="/">&larr; Home</a></div>
                <h1>My Arenas</h1>
                <p style="color:#666;">Arenas you created. Edit each one's settings, including enemy AA/Flak strength.</p>
                {admin_extra}
                {items}
            """
            self.send_html(content)

        elif self.path == '/squadrons':
            if not user:
                self.send_response(302); self.send_header('Location', '/login'); self.end_headers(); return
            conn = sqlite3.connect(SRV['db_path'])
            try:
                sqns = conn.execute(
                    "SELECT squadron_id, name, tag, motto, "
                    "CASE WHEN COALESCE(password,'')<>'' THEN 1 ELSE 0 END, "
                    "(SELECT COUNT(*) FROM squadron_members m WHERE m.squadron_id=squadrons.squadron_id "
                    " AND m.status='approved') "
                    "FROM squadrons WHERE status='approved' ORDER BY name").fetchall()
                mine = conn.execute(
                    "SELECT s.name, s.status FROM squadrons s WHERE s.commander IN "
                    "(SELECT pilot_name FROM pilots WHERE account_name=?) OR s.commander=? "
                    "ORDER BY s.status, s.name", (user, user)).fetchall()
                pilots = conn.execute("SELECT pilot_name FROM pilots WHERE account_name=? "
                                      "ORDER BY pilot_name", (user,)).fetchall()
            except Exception:
                sqns, mine, pilots = [], [], []
            conn.close()
            if sqns:
                rows = ""
                for sid, name, tag, motto, locked, cnt in sqns:
                    lock = ' <span title="Password protected">&#128274;</span>' if locked else ''
                    rows += (f"<tr><td><strong>{hesc(str(name))}</strong>{lock}</td>"
                             f"<td>{hesc(str(tag or ''))}</td>"
                             f"<td>{hesc(str(motto or ''))}</td>"
                             f"<td style='text-align:center;'>{cnt}</td></tr>")
                table = ("<table><tr><th>Squadron</th><th>Tag</th><th>Notes</th>"
                         f"<th>Members</th></tr>{rows}</table>")
            else:
                table = ("<p style='color:#666;'>No active squadrons yet. Create one below - it appears "
                         "here once an admin approves it.</p>")
            mine_html = ""
            if mine:
                items = "".join(f"<li>{hesc(str(n))} &mdash; <em>{hesc(str(st))}</em></li>" for n, st in mine)
                mine_html = (f"<div class='card'><h2 style='margin-top:0;'>Squadrons you created</h2>"
                             f"<ul style='margin:0;'>{items}</ul></div>")
            # v851f5 [SQUADRON MANAGEMENT FOR COs AND OFFICERS]: every approved squadron in which one of
            # the user's pilots is commander or officer gets a management card: members with role,
            # a RANK TAG (appended to the pilot's in-game name as ^TAG, e.g. AC2E_Bigalon^CO), pending
            # applications to approve, and removal. The tag rename goes through the same carry-over
            # as any pilot rename, so membership and command follow it.
            manage_html = ""
            try:
                conn = sqlite3.connect(SRV['db_path'])
                _mypilots = [p for (p,) in conn.execute("SELECT pilot_name FROM pilots WHERE account_name=?", (user,)).fetchall()]
                _managed = []
                if _mypilots:
                    _q = ','.join('?' * len(_mypilots))
                    _managed = conn.execute(
                        f"SELECT DISTINCT s.squadron_id, s.name, s.tag FROM squadrons s JOIN squadron_members m "
                        f"ON m.squadron_id=s.squadron_id WHERE s.status='approved' AND m.status='approved' "
                        f"AND m.role IN ('commander','officer') AND m.account_name IN ({_q}) ORDER BY s.name",
                        tuple(_mypilots)).fetchall()
                for _sid, _sname, _stag in _managed:
                    _mem = conn.execute(
                        "SELECT account_name, COALESCE(role,'member'), status FROM squadron_members WHERE squadron_id=? "
                        "ORDER BY status DESC, CASE role WHEN 'commander' THEN 0 WHEN 'officer' THEN 1 ELSE 2 END, account_name",
                        (_sid,)).fetchall()
                    _rows = ""
                    for _mname, _mrole, _mstatus in _mem:
                        _base, _sep, _cur = str(_mname).partition('^')
                        _sidh = hesc(str(_sid), quote=True); _mh = hesc(str(_mname), quote=True)
                        _opts = ''.join(f"<option value='{r}'{' selected' if r == _mrole else ''}>{r}</option>" for r in ('member', 'officer', 'commander'))
                        if _mstatus == 'pending':
                            _rows += (f"<tr><td>{hesc(str(_mname))}</td><td colspan='2'><em>application pending</em></td>"
                                      f"<td><form method='POST' action='/squadrons/manage' style='display:inline;'>"
                                      f"<input type='hidden' name='squadron_id' value='{_sidh}'><input type='hidden' name='member' value='{_mh}'>"
                                      f"<button type='submit' name='op' value='approve' class='btn-green' style='width:auto;padding:5px 10px;margin:0;'>Approve</button> "
                                      f"<button type='submit' name='op' value='remove' class='btn-red' style='width:auto;padding:5px 10px;margin:0;'>Decline</button></form></td></tr>")
                            continue
                        _rows += (f"<tr><td>{hesc(str(_mname))}</td>"
                                  f"<td><form method='POST' action='/squadrons/manage' style='display:inline;'>"
                                  f"<input type='hidden' name='squadron_id' value='{_sidh}'><input type='hidden' name='member' value='{_mh}'>"
                                  f"<select name='role' style='padding:4px;'>{_opts}</select> "
                                  f"<button type='submit' name='op' value='setrole' class='btn-yellow' style='width:auto;padding:5px 10px;margin:0;'>Set role</button></form></td>"
                                  f"<td><form method='POST' action='/squadrons/manage' style='display:inline;'>"
                                  f"<input type='hidden' name='squadron_id' value='{_sidh}'><input type='hidden' name='member' value='{_mh}'>"
                                  f"{hesc(_base)}^<input type='text' name='rank' value='{hesc(_cur, quote=True)}' maxlength='6' size='5' style='padding:4px;' placeholder='CO'> "
                                  f"<button type='submit' name='op' value='setrank' class='btn-yellow' style='width:auto;padding:5px 10px;margin:0;'>Set tag</button></form></td>"
                                  f"<td><form method='POST' action='/squadrons/manage' style='display:inline;'>"
                                  f"<input type='hidden' name='squadron_id' value='{_sidh}'><input type='hidden' name='member' value='{_mh}'>"
                                  f"<button type='submit' name='op' value='remove' class='btn-red' style='width:auto;padding:5px 10px;margin:0;' onclick=\"return confirm('Remove this member?');\">Remove</button></form></td></tr>")
                    manage_html += (f"<div class='card'><h2 style='margin-top:0;'>Manage {hesc(str(_sname))}"
                                    f"{(' [' + hesc(str(_stag)) + ']') if _stag else ''}</h2>"
                                    f"<p style='color:#666; margin-top:0; font-size:0.9em;'>The rank tag is appended to the pilot's "
                                    f"in-game name as <code>name^TAG</code> (letters, digits, _ and -; up to 6). A pilot who is "
                                    f"online sees the new name after his next login.</p>"
                                    f"<table><tr><th>Pilot</th><th>Role</th><th>Rank tag</th><th></th></tr>{_rows}</table></div>")
                conn.close()
            except Exception as _e:
                manage_html = f"<div class='card'><p style='color:#c00;'>Squadron management unavailable: {hesc(str(_e))}</p></div>"
            pilot_opts = "".join(f"<option>{hesc(str(p))}</option>" for (p,) in pilots)
            if pilot_opts:
                create_card = f"""
                <div class="card">
                    <h2 style="margin-top:0;">Create a Squadron</h2>
                    <p style="color:#666; margin-top:0; font-size:0.9em;">New squadrons start as
                    <em>pending</em> and become visible &amp; joinable once an admin approves them.
                    The pilot you choose becomes its commander.</p>
                    <form method="POST" action="/squadrons/create">
                        <div style="display:flex; gap:10px; align-items:flex-end; flex-wrap:wrap;">
                            <label style="font-size:0.8em; color:#666;">Commander (your pilot)<br>
                                <select name="commander" required style="padding:8px;">{pilot_opts}</select></label>
                            <label style="font-size:0.8em; color:#666;">Name (max 31)<br>
                                <input type="text" name="name" required maxlength="31" style="width:220px; padding:8px;"></label>
                            <label style="font-size:0.8em; color:#666;">Tag / prefix (max 31)<br>
                                <input type="text" name="tag" maxlength="31" style="width:130px; padding:8px;"></label>
                            <label style="font-size:0.8em; color:#666;">Password (optional)<br>
                                <input type="text" name="password" maxlength="31" autocomplete="off" style="width:150px; padding:8px;"></label>
                        </div>
                        <label style="font-size:0.8em; color:#666; display:block; margin-top:8px;">Notes / motto<br>
                            <textarea name="motto" rows="2" style="width:100%; max-width:520px; padding:8px;"></textarea></label>
                        <button type="submit" class="btn-green" style="margin-top:8px;">Create (pending approval)</button>
                    </form>
                </div>"""
            else:
                create_card = ("<div class='card'><h2 style='margin-top:0;'>Create a Squadron</h2>"
                               "<p style='color:#666;'>You need a pilot first &mdash; launch the game and create "
                               "a pilot, then come back here to found a squadron.</p></div>")
            content = f"""
                <div class="nav"><a href="/">&larr; Back to Dashboard</a> |
                    Logged in as <strong>{hesc(str(user))}</strong></div>
                <h1>Squadrons</h1>
                <div class="card">
                    <h2 style="margin-top:0;">Active Squadrons</h2>
                    {table}
                </div>
                {mine_html}
                {manage_html}
                {create_card}
            """
            self.send_html(content)

        elif self.path == '/scoring':
            # v404f5: the live scoring reference - rendered from the GAME SERVER's own constants
            # (injected as a callable), so this page can never drift from the code in force.
            ref = _scoring_ref()
            if not ref:
                self.send_html("<h2>Scoring reference unavailable</h2><p>The game server did not "
                               "inject its scoring tables (older server build?).</p>"
                               "<a href='/'>&larr; Back</a>")
                return
            ev_tbl = str(ref.get('modes', {}).get('events_table', 'ffa')).upper()
            rank_rows = ""
            for r in ref.get('ranks', []):
                hi = ('{:,}'.format(r['hi']) if r.get('hi') is not None else '&infin;')
                rank_rows += (f"<tr><td>{r['idx']}</td><td><strong>{hesc(str(r['name']))}</strong></td>"
                              f"<td>{r['lo']:,} &ndash; {hi}</td><td>{r['loss_pct']}%</td></tr>")
            plane_rows = ""
            planes = sorted(ref.get('planes', []), key=lambda x: (x['bomber'], str(x['name']).lower()))
            for p in planes:
                cls = 'Bomber' if p['bomber'] else 'Fighter'
                note = '' if p.get('listed', True) else ' <small style="color:#c60;">(class default)</small>'
                plane_rows += (f"<tr><td><strong>{hesc(str(p['name']))}</strong>{note}</td><td>{cls}</td>"
                               f"<td>{p['ffa']}</td><td>{p['tc']}</td></tr>")
            ai_rows = ""
            for nm, v in ref.get('ai', {}).items():
                ai_rows += (f"<tr><td><strong>{hesc(str(nm).replace('_', ' '))}</strong></td>"
                            f"<td>{v['ffa']}</td><td>{v['tc']}</td></tr>")
            ev_rows = ''.join(f"<tr><td>{hesc(str(k))}</td><td>{v}</td></tr>"
                              for k, v in ref.get('events', {}).items())
            content = f"""
                <div class="nav"><a href="/">&larr; Back to Dashboard</a> |
                    <a href="/ladder" style="color:#17a2b8;">Ladder Board</a></div>
                <h1>Scoring Reference</h1>
                <div class="card">
                    <h2 style="margin-top:0;">How arenas score</h2>
                    <p style="color:#555; font-size:0.95em; max-width:720px;">
                    Every plane has TWO point values. Which one an arena uses is decided by the
                    arena's list category (its Title / section header):
                    <strong>Dogfighting</strong> arenas use the <strong>FFA value</strong>,
                    <strong>Territorial Combat</strong> arenas use the <strong>TC value</strong>,
                    and <strong>Events</strong> arenas score with the {ev_tbl} column.
                    Arenas in any other category (including <em>Custom Arenas</em>) do
                    <strong>not</strong> change global scores, kills, deaths, aces or ranks at all
                    &mdash; unless the arena's editor forces a scoring mode.
                    A kill pays the killer the shot-down plane's value <em>plus</em> the Destroy Plane
                    Bonus (points gained are never reduced by rank). A loss costs the owner his plane's
                    value, and the Pilot Death penalty if he died, both scaled by his rank percentage below.</p>
                </div>
                <div class="card" style="padding:0;">
                    <div style="padding:15px 15px 0;"><h2 style="margin:0;">Ranks</h2>
                    <p style="color:#666; font-size:0.9em;">Rank comes from career score. The
                    percentage is how much of a loss's base cost a pilot of that rank actually
                    pays (points GAINED are never reduced).</p></div>
                    <table>
                        <thead><tr><th>Idx</th><th>Rank</th><th>Score</th><th>% of losses paid</th></tr></thead>
                        <tbody>{rank_rows}</tbody>
                    </table>
                </div>
                <div class="card" style="padding:0;">
                    <div style="padding:15px 15px 0;"><h2 style="margin:0;">Plane values</h2>
                    <p style="color:#666; font-size:0.9em;">The value is what the killer GAINS for
                    shooting the plane down (on top of the Destroy Plane Bonus) and what its owner
                    LOSES when it goes down (before the rank percentage). Blank-TC planes in the
                    original table fall back to their FFA value.</p>
                    <input type="text" id="planeSearch" placeholder="Search planes..."
                           style="width:100%; padding:10px; margin:0 0 10px; box-sizing:border-box;
                                  border:1px solid #ccc; border-radius:4px;"></div>
                    <table id="planeTable">
                        <thead><tr><th>Plane</th><th>Class</th><th>FFA value</th><th>TC value</th></tr></thead>
                        <tbody>{plane_rows}</tbody>
                    </table>
                </div>
                <div class="card" style="padding:0;">
                    <div style="padding:15px 15px 0;"><h2 style="margin:0;">AI objects</h2></div>
                    <table>
                        <thead><tr><th>Object</th><th>FFA value</th><th>TC value</th></tr></thead>
                        <tbody>{ai_rows}</tbody>
                    </table>
                </div>
                <div class="card" style="padding:0;">
                    <div style="padding:15px 15px 0;"><h2 style="margin:0;">Event bonuses / penalties</h2>
                    <p style="color:#666; font-size:0.9em;">Flat amounts (positive and negative)
                    applied on the event, before rank scaling where losses are concerned.</p></div>
                    <table>
                        <thead><tr><th>Event</th><th>Base points</th></tr></thead>
                        <tbody>{ev_rows}</tbody>
                    </table>
                </div>
                <script>
                document.getElementById('planeSearch').addEventListener('keyup', function() {{
                    let filter = this.value.toLowerCase();
                    let rows = document.querySelectorAll('#planeTable tbody tr');
                    rows.forEach(row => {{
                        row.style.display = row.textContent.toLowerCase().includes(filter) ? '' : 'none';
                    }});
                }});
                </script>
            """
            self.send_html(content)

        # ---- Public player ticker (no login needed) ------------------------
        # /ticker.json - bare counts as JSON, CORS-open so any site can poll it.
        # /ticker      - a tiny self-refreshing dark badge page made for
        #                embedding in an <iframe> on the community website.
        # Exposes ONLY the three aggregate counts (nothing about who they are).
        elif self.path == '/ticker.json':
            counts = None
            pc = SRV.get('player_counts')
            if pc:
                try:
                    counts = pc()
                except Exception:
                    counts = None
            if not isinstance(counts, dict):
                counts = {'connected': 0, 'in_arena': 0, 'flying': 0}
            body = json.dumps(counts).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(body)

        # ---- WHO'S ONLINE (v968f7a, Alon 10-30: for the fa-re.net "WHO'S ONLINE" block) ------------
        # /whosonline/onlineplayers.json - the feed: who is connected and in which arena, CORS-open,
        #                                  no-store, so the website (or anyone) can poll it.
        # /whosonline                    - the embeddable page: a dark badge like /ticker, refreshed
        #                                  every 5 s from the feed, grouped by arena; colours can be
        #                                  matched to the site with ?bg=&fg=&accent=&muted= (hex, no #).
        elif self.path.split('?')[0] in ('/whosonline/onlineplayers.json', '/whosonline.json'):
            data = None
            fn = SRV.get('online_players')
            if fn:
                try:
                    data = fn()
                except Exception:
                    data = None
            if not isinstance(data, dict):
                data = {'updated': None, 'connected': 0, 'in_arena': 0, 'flying': 0, 'arenas': [], 'players': []}
            body = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(body)

        elif self.path.split('?')[0] in ('/whosonline', '/whosonline/'):
            _q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            def _hex(k, d):
                v = (_q.get(k, [''])[0] or '').strip().lstrip('#')
                return ('#' + v) if re.fullmatch(r'[0-9a-fA-F]{3}|[0-9a-fA-F]{6}', v or '') else d
            bg, fg, accent, muted = _hex('bg', '#1e1e1e'), _hex('fg', '#e6e6e6'), _hex('accent', '#7ec97e'), _hex('muted', '#888888')
            page = ("""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Fighter Ace - who's online</title>
<style>
html,body{margin:0;padding:0;background:%(bg)s;color:%(fg)s;font-family:Consolas,'Courier New',monospace;font-size:14px;}
#w{padding:8px 14px;}
.hd{color:%(accent)s;letter-spacing:.06em;text-transform:uppercase;font-size:13px;margin:0 0 6px 0;}
.hd .n{color:%(fg)s;}
.ar{margin:8px 0 2px 0;color:%(accent)s;text-transform:uppercase;font-size:12px;letter-spacing:.05em;}
.ar .c{color:%(muted)s;text-transform:none;letter-spacing:0;}
.pl{margin:0;padding:0 0 0 12px;list-style:none;}
.pl li{line-height:1.5;white-space:nowrap;}
.pl .side{color:%(muted)s;font-size:12px;}
.pl .fly{color:%(accent)s;}
.lobby{color:%(muted)s;margin-top:8px;font-size:12px;}
.zero{color:%(muted)s;}
</style></head><body><div id="w"><div class="hd">Who's online <span class="n">&hellip;</span></div><div id="b"></div></div>
<script>
function esc(t){return String(t).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
function tick(){
 fetch('/whosonline/onlineplayers.json').then(function(r){return r.json();}).then(function(d){
  var n=document.querySelector('.hd .n'); var b=document.getElementById('b');
  n.textContent='\u00b7 '+d.connected+' connected \u00b7 '+d.in_arena+' in arena \u00b7 '+d.flying+' flying';
  n.className='n'+(d.connected>0?'':' zero');
  var html='';
  var byArena={};
  d.players.forEach(function(p){ if(p.arena_id===null||p.arena_id===undefined) return; (byArena[p.arena_id]=byArena[p.arena_id]||[]).push(p); });
  d.arenas.forEach(function(a){
   html+='<div class="ar">'+esc(a.arena)+' <span class="c">('+a.players+(a.flying?', '+a.flying+' flying':'')+')</span></div><ul class="pl">';
   (byArena[a.arena_id]||[]).forEach(function(p){
    html+='<li>'+(p.state==='flying'?'<span class="fly">&#9992;</span> ':'&nbsp;&nbsp;')+esc(p.pilot)
        +(p.side?' <span class="side">'+esc(p.side)+'</span>':'')
        +(p.minutes!==null&&p.minutes!==undefined?' <span class="side">'+p.minutes+' min</span>':'')+'</li>';
   });
   html+='</ul>';
  });
  var lobby=d.players.filter(function(p){return p.arena_id===null||p.arena_id===undefined;});
  if(lobby.length) html+='<div class="lobby">In the lobby: '+lobby.map(function(p){return esc(p.pilot);}).join(', ')+'</div>';
  if(!d.players.length) html='<div class="zero">Nobody online right now.</div>';
  b.innerHTML=html;
 }).catch(function(){});
}
tick();setInterval(tick,5000);
</script></body></html>""" % {'bg': bg, 'fg': fg, 'accent': accent, 'muted': muted})
            body = page.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        elif self.path == '/ticker':
            page = ("<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
                    "<title>Fighter Ace - players online</title>"
                    "<style>"
                    "html,body{margin:0;padding:0;background:#1e1e1e;}"
                    "#t{font-family:Consolas,monospace;color:#7ec97e;font-size:15px;"
                    "padding:8px 14px;white-space:nowrap;}"
                    "#t.zero{color:#888;}"
                    "</style></head><body>"
                    "<div id=\"t\">&hellip;</div>"
                    "<script>"
                    "function tick(){"
                    "fetch('/ticker.json').then(function(r){return r.json();})"
                    ".then(function(p){"
                    "var el=document.getElementById('t');"
                    "el.textContent=p.connected+' connected \\u00b7 '+p.in_arena+"
                    "' in arena \\u00b7 '+p.flying+' flying';"
                    "el.className=p.connected>0?'':'zero';"
                    "}).catch(function(){});"
                    "}"
                    "tick();setInterval(tick,5000);"
                    "</script></body></html>")
            body = page.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        elif self.path.startswith('/admin/badwords'):
            # v780f5: the chat word filter list (badwords.txt next to server.py, reloaded live)
            if not is_user_admin(user):
                self.send_html("<h2>Access Denied</h2><a href='/'>&larr; Back</a>"); return
            _dir = os.path.dirname(os.path.abspath(SRV.get('server_py') or __file__))
            try:
                with open(os.path.join(_dir, 'badwords.txt'), 'r', encoding='utf-8', errors='replace') as f:
                    _cur = f.read()
            except Exception:
                _cur = ''
            _saved = 'saved' in urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            content = f"""
                <div class="nav"><a href="/admin">&larr; Back to Admin</a></div>
                <h1>Chat Word Filter</h1>
                {'<p style="color:#198754;"><strong>Saved.</strong> In effect immediately.</p>' if _saved else ''}
                <div class="card">
                  <p style="color:#888; max-width:640px;">One word per line. Matched words are replaced by asterisks in
                  lobby and arena chat (whole words, case-insensitive, common leetspeak folded: 0=o 1=i 3=e 4=a 5=s
                  7=t). End a line with <code>*</code> to match any word starting with it. Start a line with
                  <code>+</code> to <strong>whitelist</strong> a word that a prefix would otherwise catch (e.g.
                  <code>+cockpit</code> alongside <code>cock*</code>). <code>#</code> starts a
                  comment. Hits are logged under CHATFILTER with the sender's name.</p>
                  <form method="POST" action="/admin/badwords">
                    <textarea name="words" rows="20" style="width:100%; font-family:monospace;">{hesc(_cur)}</textarea>
                    <p><button type="submit">Save</button></p>
                  </form>
                </div>"""
            self.send_html(content)

        elif self.path.startswith('/admin/motd'):
            # v891f5: message of the day - yellow server lines sent to each pilot entering an arena's world
            if not is_user_admin(user):
                self.send_html("<h2>Access Denied</h2><a href='/'>&larr; Back</a>"); return
            _dir = os.path.dirname(os.path.abspath(SRV.get('server_py') or __file__))
            try:
                with open(os.path.join(_dir, 'motd.txt'), 'r', encoding='utf-8', errors='replace') as f:
                    _cur = f.read()
            except Exception:
                _cur = ''
            _saved = 'saved' in urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            content = f"""
                <div class="nav"><a href="/admin">&larr; Back to Administration</a></div>
                <h1>Message of the Day</h1>
                {'<p style="color:#198754;"><strong>Saved.</strong> Pilots get it the next time they enter an arena.</p>' if _saved else ''}
                <div class="card">
                  <p style="color:#888; max-width:680px;">Each line below is shown to every pilot, in the small yellow
                  server text, a few seconds after he enters an arena's world (once per arena entry, not on every
                  respawn). Up to <strong>8 lines</strong> of up to <strong>74 characters</strong> each (the limit of the
                  client's system-message line); longer lines are cut. Blank lines are skipped. Leave it empty to send nothing.</p>
                  <form method="POST" action="/admin/motd">
                    <textarea name="motd" rows="9" maxlength="700" style="width:100%; font-family:monospace;">{hesc(_cur)}</textarea>
                    <p><button type="submit">Save</button></p>
                  </form>
                </div>"""
            self.send_html(content)

        elif self.path.startswith('/admin/leaders'):
            # v891f5: player / squadron of the week / month from pilot_stats_daily
            if not is_user_admin(user):
                self.send_html("<h2>Access Denied</h2><a href='/'>&larr; Back</a>"); return
            _q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            _period = _q.get('period', ['week'])[0]
            _room = _q.get('room', ['all'])[0]
            import datetime as _dt
            _today = _dt.datetime.utcnow().date()
            _mon = _today - _dt.timedelta(days=_today.weekday())
            _m1 = _today.replace(day=1)
            _periods = {
                'week':       ('This week',  _mon, _today),
                'lastweek':   ('Last week',  _mon - _dt.timedelta(days=7), _mon - _dt.timedelta(days=1)),
                'month':      ('This month', _m1, _today),
                'lastmonth':  ('Last month', (_m1 - _dt.timedelta(days=1)).replace(day=1), _m1 - _dt.timedelta(days=1)),
            }
            if _period not in _periods:
                _period = 'week'
            _plabel, _d0, _d1 = _periods[_period]
            conn = sqlite3.connect(SRV['db_path'])
            try:
                _has = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pilot_stats_daily'").fetchone()
                _rooms = conn.execute("SELECT room_id, room_name FROM rooms ORDER BY room_name").fetchall()
                _rname = {int(r[0]): (r[1] or f'Arena {r[0]}') for r in _rooms}
                _sq = {int(r[0]): (r[1], r[2]) for r in conn.execute("SELECT squadron_id, name, tag FROM squadrons").fetchall()}
                _where = "day >= ? AND day <= ?"
                _args = [_d0.isoformat(), _d1.isoformat()]
                if _room != 'all' and _room.isdigit():
                    _where += " AND room_id = ?"; _args.append(int(_room))
                def _top(col, by_squad, extra=''):
                    if not _has:
                        return []
                    if by_squad:
                        return conn.execute(f"SELECT squadron_id, SUM({col}) v FROM pilot_stats_daily WHERE {_where} "
                                            f"AND squadron_id > 0 {extra} GROUP BY squadron_id HAVING v > 0 ORDER BY v DESC LIMIT 10",
                                            _args).fetchall()
                    return conn.execute(f"SELECT pilot, SUM({col}) v FROM pilot_stats_daily WHERE {_where} {extra} "
                                        f"GROUP BY pilot HAVING v > 0 ORDER BY v DESC LIMIT 10", _args).fetchall()
                # TC triggers only count in TC rooms (the trigger hook only fires there anyway)
                _boards = [
                    ('Most time online', 'online_s', 'time'),
                    ('Most kills', 'kills', 'n'),
                    ('Most TC triggers', 'triggers', 'n'),
                ]
                def _fmt(v, kind):
                    if kind == 'time':
                        v = int(v or 0); return f'{v // 3600}h {(v % 3600) // 60:02d}m'
                    return str(int(v or 0))
                def _table(title, rows, kind, squad):
                    if not rows:
                        return f"<div class='card' style='flex:1; min-width:280px;'><h3 style='margin-top:0;'>{title}</h3><p style='color:#888;'>No data yet.</p></div>"
                    trs = ''
                    for i, (k, v) in enumerate(rows):
                        if squad:
                            nm, tg = _sq.get(int(k), (f'Squadron {k}', ''))
                            label = hesc(str(nm)) + (f' [{hesc(str(tg))}]' if tg else '')
                        else:
                            label = hesc(str(k))
                        star = ' &#9733;' if i == 0 else ''
                        style = " style='font-weight:bold; background:#fff8dc;'" if i == 0 else ''
                        trs += f"<tr{style}><td>{i + 1}</td><td>{label}{star}</td><td style='text-align:right;'>{_fmt(v, kind)}</td></tr>"
                    return (f"<div class='card' style='flex:1; min-width:280px;'><h3 style='margin-top:0;'>{title}</h3>"
                            f"<table><tr><th>#</th><th>{'Squadron' if squad else 'Pilot'}</th><th></th></tr>{trs}</table></div>")
                _html = ''
                for title, col, kind in _boards:
                    _html += (f"<h2>{title}</h2><div style='display:flex; gap:16px; flex-wrap:wrap;'>"
                              + _table('Player', _top(col, False), kind, False)
                              + _table('Squadron', _top(col, True), kind, True) + "</div>")
            finally:
                conn.close()
            _popts = ''.join(f"<option value='{k}'{' selected' if k == _period else ''}>{v[0]}</option>" for k, v in _periods.items())
            _ropts = "<option value='all'>All arenas</option>" + ''.join(
                f"<option value='{rid}'{' selected' if str(rid) == _room else ''}>{hesc(nm)}</option>" for rid, nm in _rname.items())
            content = f"""
                <div class="nav"><a href="/admin">&larr; Back to Administration</a></div>
                <h1>Player &amp; Squadron of the {'Week' if 'week' in _period else 'Month'}</h1>
                <form method="GET" action="/admin/leaders" style="margin-bottom:12px;">
                  <select name="period" style="padding:6px;">{_popts}</select>
                  <select name="room" style="padding:6px;">{_ropts}</select>
                  <button type="submit" style="width:auto; padding:6px 14px;">Show</button>
                </form>
                <p style="color:#888;">{_plabel}: {_d0.isoformat()} to {_d1.isoformat()} (UTC days, weeks start Monday).
                Time online counts time inside an arena's world, not the lobby. A pilot's squadron is the one he
                flew under when the time or kill was recorded. The starred row is the player / squadron of the period.</p>
                {_html}"""
            self.send_html(content)

        elif self.path.startswith('/admin/lobby_news'):
            # v731f5: edit the lobby News page (msg 202): the right-hand news lines and the left
            # welcome pane. Files live next to server.py so the game server picks them up live.
            if not is_user_admin(user):
                self.send_html("<h2>Access Denied</h2><a href='/'>&larr; Back</a>"); return
            _dir = os.path.dirname(os.path.abspath(SRV.get('server_py') or __file__))
            def _rd(nm):
                try:
                    with open(os.path.join(_dir, nm), 'r', encoding='utf-8', errors='replace') as f:
                        return f.read()
                except Exception:
                    return ''
            _saved = 'saved' in urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            content = f"""
                <div class="nav"><a href="/">&larr; Back to Dashboard</a></div>
                <h1>Lobby News</h1>
                {'<p style="color:#198754;"><strong>Saved.</strong> Pilots see it when they open the News page (or on their next login).</p>' if _saved else ''}
                <div class="card">
                  <p style="color:#888; max-width:640px;">The <strong>News</strong> lines fill the right-hand pane of the
                  lobby's News page, one line each, in order. The <strong>Welcome</strong> text replaces the left pane
                  (the client's built-in "you are in offline mode" message). Plain text; keep lines under ~120
                  characters or they are trimmed. Leave Welcome empty to keep the client's own text.</p>
                  <form method="POST" action="/admin/lobby_news">
                    <h3>News (right pane)</h3>
                    <textarea name="news" rows="14" style="width:100%; font-family:monospace;">{hesc(_rd('lobby_news.txt'))}</textarea>
                    <h3>Welcome (left pane)</h3>
                    <textarea name="welcome" rows="8" style="width:100%; font-family:monospace;">{hesc(_rd('lobby_welcome.txt'))}</textarea>
                    <p><button type="submit">Save</button></p>
                  </form>
                </div>"""
            self.send_html(content)

        elif self.path == '/login':
            content = """
                <h1>Server Login</h1>
                <form method="POST" action="/login">
                    <label>Account Name:</label>
                    <input type="text" name="account_name" required>
                    <label>Password:</label>
                    <input type="password" name="password" required>
                    <button type="submit">Login</button>
                </form>
                <div style="text-align:center; margin-top:15px;">
                    <a href="/register" style="color: #007bff;">Need an account? Create New Account</a>
                </div>
            """
            self.send_html(content)

        elif self.path == '/register':
            content = """
                <h1>Create New Account</h1>
                <form method="POST" action="/register">
                    <label>Account Name (max 31 chars):</label>
                    <input type="text" name="account_name" required>
                    <label>Password:</label>
                    <input type="password" name="password" required>
                    <button type="submit" class="btn-green">Create Account & Generate Ticket</button>
                </form>
                <div style="text-align:center; margin-top:15px;">
                    <a href="/login" style="color: #007bff;">Back to Login</a>
                </div>
            """
            self.send_html(content)
            
        elif self.path == '/logout':
            self.send_response(302)
            self.send_header('Set-Cookie', 'session=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT')
            self.send_header('Location', '/login')
            self.end_headers()

        elif self.path.startswith('/download'):
            if not user:
                self.send_error(401, 'Unauthorized')
                return
                
            try:
            
                ticket_bytes, pid_hex = SRV['get_existing_ticket'](user)
                # Tell the launcher the client path THIS account has stored, so it can
                # save the ticket next to the right FA.exe and launch it - instead of
                # relying on a path hard-coded in launcher.ini. Header must be latin-1
                # safe (HTTP header), so we percent-safe it minimally.
                try:
                    conn = sqlite3.connect(SRV['db_path'])
                    row = conn.execute("SELECT client_path FROM accounts WHERE account_name=?", (user,)).fetchone()
                    conn.close()
                    client_path = (row[0] if row and row[0] else DEFAULT_CLIENT_PATH)
                except Exception:
                    client_path = DEFAULT_CLIENT_PATH
                self.send_response(200)
                self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Content-Disposition', f'attachment; filename="ticket_{pid_hex}.vr1"')
                # Custom header the FA launcher reads to locate the game client.
                self.send_header('X-Game-Client-Path', client_path)
                self.end_headers()
                self.wfile.write(ticket_bytes)
            except Exception as e:
                self.send_error(500, f"Error generating ticket: {str(e)}")
        elif self.path == '/admin/logs':
            if not is_user_admin(user):
                self.send_html("<h2>Access Denied</h2><a href='/'>&larr; Back</a>")
                return
            self.send_html(LOG_CONSOLE_PAGE)
        elif self.path.startswith('/admin/logs.json'):
            if not _log_read_ok(self, user):
                self.send_error(403); return
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            level = (qs.get('level', ['INFO'])[0] or 'INFO').upper()
            getter = SRV.get('get_logs')
            lines = []
            if getter:
                try:
                    raw = getter(500, 'DEBUG')
                except Exception:
                    raw = []
                order = {'DEBUG': 10, 'INFO': 20, 'WARNING': 30, 'ERROR': 40}
                want = order.get(level, 20)
                for ln in raw:
                    lv = _infer_level_from_line(ln)
                    if order.get(lv, 20) >= want:
                        lines.append({'level': lv, 'line': ln})
            # v418f5: piggyback the live player counts on the poll the console already makes
            # every 2s - no extra endpoint, no extra request, counter is as fresh as the log.
            counts = None
            pc = SRV.get('player_counts')
            if pc:
                try:
                    counts = pc()
                except Exception:
                    counts = None
            body = json.dumps({'lines': lines, 'players': counts,
                               'version': SRV.get('version')}).encode('utf-8')     # v798f5: server build on the console
            self._perf_ready = time.time()     # 2026-09-29 WEBPERF: built; the rest is transfer
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)
        elif self.path.startswith('/admin/evs_library.json'):
            # v958f5e: event-script library listing for the Events tab
            if not is_user_admin(user):
                self.send_error(403); return
            _evs_lib_json(self, 200, {'dir': _evs_lib_dir(), 'scripts': _evs_lib_list()})

        elif self.path.startswith('/admin/evs_library_get'):
            if not is_user_admin(user):
                self.send_error(403); return
            _q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            _n = _evs_lib_safe(_q.get('name', [''])[0])
            _p = os.path.join(_evs_lib_dir(), _n + '.json') if _n else ''
            if not _n or not os.path.isfile(_p):
                _evs_lib_json(self, 404, {'ok': False, 'error': 'no such script'}); return
            with open(_p, encoding='utf-8') as f:
                _txt = f.read()
            if 'download' in _q:
                body = _txt.encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Disposition', f'attachment; filename="{_n}.json"')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers(); self.wfile.write(body)
            else:
                _evs_lib_json(self, 200, {'ok': True, 'name': _n, 'script': _txt})

        elif self.path.startswith('/admin/logfiles.json'):
            # v321: directory listing for the admin Logs tab. Loaded lazily by the page so
            # /admin stays fast even with hundreds of run_*.log files accumulated.
            if not _log_read_ok(self, user):
                self.send_error(403); return
            files = _list_log_files()
            body = json.dumps({'dir': _log_dir() or '', 'files': files}).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        elif self.path.startswith('/admin/stallfiles.json'):
            # v418f5: listing for the Stall Dumps sub-tab (STALL-WATCH flight recorder).
            if not is_user_admin(user):
                self.send_error(403); return
            files = _list_stall_files()
            body = json.dumps({'dir': _stall_dir() or '', 'files': files}).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        elif self.path.startswith('/admin/log_download'):
            if not _log_read_ok(self, user):
                self.send_error(403); return
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            name = q.get('name', [''])[0]
            # v418f5: src=stall selects the flightrec root. The parameter picks WHICH of the
            # two pre-defined roots resolves the bare filename - it is never part of a path.
            src_kind = q.get('src', [''])[0]
            path = _safe_stall_path(name) if src_kind == 'stall' else _safe_log_path(name)
            if not path:
                SRV['log']('WEB', f'log download REJECTED for {user!r}: name={name!r} src={src_kind!r}')
                self.send_error(404); return
            try:
                size = os.path.getsize(path)
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.send_header('Content-Length', str(size))
                self.send_header('Content-Disposition',
                                 'attachment; filename="' + name + '"')
                self.end_headers()
                # Stream in chunks rather than read()-ing the whole file: some run logs are
                # megabytes, and the live server.log is being APPENDED TO while we read. We
                # send exactly the `size` bytes we advertised, so a file that grows mid-read
                # can't desync Content-Length from the body.
                sent = 0
                with open(path, 'rb') as f:
                    while sent < size:
                        chunk = f.read(min(65536, size - sent))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        sent += len(chunk)
                    if sent < size:                 # file shrank (rotated) mid-read: pad so
                        self.wfile.write(b'\n' * (size - sent))   # the body matches the header
                SRV['log']('WEB', f'Admin {user} downloaded log {name} ({size} bytes)')
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                pass                                # client cancelled the download; harmless
            except Exception as e:
                SRV['log']('WEB', f'log download failed for {name!r}: {e!r}')

        elif self.path.startswith('/admin/log_view'):
            # Show the TAIL of a log in the browser, so a 2 MB run log can be peeked at
            # without downloading it.
            if not _log_read_ok(self, user):
                self.send_error(403); return
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            name = q.get('name', [''])[0]
            try:
                kb = max(1, min(1024, int(q.get('kb', ['128'])[0])))
            except (ValueError, TypeError):
                kb = 128
            src_kind = q.get('src', [''])[0]      # v418f5: same two-root selection as download
            path = _safe_stall_path(name) if src_kind == 'stall' else _safe_log_path(name)
            if not path:
                SRV['log']('WEB', f'log view REJECTED for {user!r}: name={name!r} src={src_kind!r}')
                self.send_error(404); return
            try:
                size = os.path.getsize(path)
                want = kb * 1024
                with open(path, 'rb') as f:
                    if size > want:
                        f.seek(size - want)
                        f.readline()               # drop the partial first line
                    data = f.read()
                text = data.decode('utf-8', 'replace')
            except Exception as e:
                self.send_html(f"<h2 style='color:red;'>Could not read log</h2><p>{hesc(str(e))}</p>"
                               "<a href='/admin'>&larr; Back to Admin</a>")
                return
            trunc = ('<p style="color:#c60;">Showing the last '
                     + str(kb) + ' KB of ' + f'{size/1024.0:,.0f}' + ' KB &mdash; '
                     + '<a href="/admin/log_view?name=' + urllib.parse.quote(name) + '&kb=1024">last 1 MB</a>'
                     + ' &middot; <a href="/admin/log_download?name=' + urllib.parse.quote(name)
                     + '">download the whole file</a></p>') if size > want else ''
            self.send_html(
                '<div class="nav"><a href="/admin">&larr; Back to Admin</a></div>'
                '<h1>' + hesc(name) + '</h1>' + trunc
                + '<pre style="background:#1e1e1e;color:#ddd;padding:12px;border-radius:6px;'
                  'height:70vh;overflow:auto;font-size:12px;line-height:1.4;'
                  'white-space:pre-wrap;word-break:break-word;">' + hesc(text) + '</pre>')

        else:
            self.send_error(404)

    def do_POST(self):
        _t0 = time.time()   # v475 [WEBPERF] - see do_GET (2026-09-29 build/send split)
        self._perf_ready = None
        try:
            self._do_POST_inner()
        finally:
            self._perf_log('POST', _t0)

    def _do_POST_inner(self):
        if self.path.split('?')[0] == '/auth':      # 2026-09-30: website login API - JSON body,
            return _auth_handle_post(self)          # read by the handler itself, not as a form
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length).decode('utf-8')
        qs = urllib.parse.parse_qs(post_data)
        
        user = self.get_current_user()

        if self.path == '/admin/evs_library':
            # v958f5e: save / delete an event script in the server library (JSON reply for the page's JS)
            if not is_user_admin(user):
                _evs_lib_json(self, 403, {'ok': False, 'error': 'admin only'}); return
            _act = qs.get('action', [''])[0]
            _n = _evs_lib_safe(qs.get('name', [''])[0])
            if not _n:
                _evs_lib_json(self, 400, {'ok': False, 'error': 'give the script a name (letters, digits, space, - _ . )'}); return
            _p = os.path.join(_evs_lib_dir(), _n + '.json')
            if _act == 'delete':
                try:
                    os.remove(_p)
                    SRV['log']('WEB', f'{user} deleted event script "{_n}" from the library')
                    _evs_lib_json(self, 200, {'ok': True, 'scripts': _evs_lib_list()})
                except FileNotFoundError:
                    _evs_lib_json(self, 404, {'ok': False, 'error': 'no such script'})
                except Exception as e:
                    _evs_lib_json(self, 500, {'ok': False, 'error': str(e)})
                return
            _txt = qs.get('script', [''])[0].strip()
            try:
                _obj = json.loads(_txt)
                if not isinstance(_obj, dict):
                    raise ValueError('the script must be a JSON object')
                _chk = SRV.get('evs_parse')
                if _chk:
                    _sc, _err = _chk(_txt)
                    if _err:
                        raise ValueError(_err)
                _txt = json.dumps(_obj, indent=2)
            except Exception as e:
                _evs_lib_json(self, 400, {'ok': False, 'error': f'not a valid event script: {e}'}); return
            try:
                with open(_p, 'w', encoding='utf-8') as f:
                    f.write(_txt)
                SRV['log']('WEB', f'{user} saved event script "{_n}" to the library ({len(_txt)} bytes)')
                _evs_lib_json(self, 200, {'ok': True, 'name': _n, 'scripts': _evs_lib_list()})
            except Exception as e:
                _evs_lib_json(self, 500, {'ok': False, 'error': str(e)})
            return

        if self.path == '/admin/badwords':
            if not is_user_admin(user):
                self.send_response(302); self.send_header('Location', '/'); self.end_headers(); return
            _dir = os.path.dirname(os.path.abspath(SRV.get('server_py') or __file__))
            _txt = qs.get('words', [''])[0].replace('\r\n', '\n')
            try:
                with open(os.path.join(_dir, 'badwords.txt'), 'w', encoding='utf-8') as f:
                    f.write(_txt)
                SRV['log']('WEB', f'{user} updated the chat word filter ({len([l for l in _txt.splitlines() if l.strip() and not l.strip().startswith("#")])} entries)')
            except Exception as e:
                SRV['log']('WEB', f'badwords save failed: {e!r}')
            self.send_response(302); self.send_header('Location', '/admin/badwords?saved=1'); self.end_headers()
            return

        if self.path == '/admin/motd':
            # v891f5: save the message of the day (admin only)
            if not is_user_admin(user):
                self.send_response(302); self.send_header('Location', '/'); self.end_headers(); return
            _dir = os.path.dirname(os.path.abspath(SRV.get('server_py') or __file__))
            _txt = qs.get('motd', [''])[0].replace('\r\n', '\n')
            try:
                with open(os.path.join(_dir, 'motd.txt'), 'w', encoding='utf-8') as f:
                    f.write(_txt)
                SRV['log']('WEB', f'{user} updated the message of the day ({len([l for l in _txt.splitlines() if l.strip()])} line(s))')
            except Exception as e:
                SRV['log']('WEB', f'motd save failed: {e!r}')
            self.send_response(302); self.send_header('Location', '/admin/motd?saved=1'); self.end_headers()
            return

        if self.path == '/admin/lobby_news':
            # v731f5: save the lobby News / Welcome text (admin only)
            if not is_user_admin(user):
                self.send_response(302); self.send_header('Location', '/'); self.end_headers(); return
            _dir = os.path.dirname(os.path.abspath(SRV.get('server_py') or __file__))
            for _key, _nm in (('news', 'lobby_news.txt'), ('welcome', 'lobby_welcome.txt')):
                _txt = qs.get(_key, [''])[0].replace('\r\n', '\n')
                try:
                    with open(os.path.join(_dir, _nm), 'w', encoding='utf-8') as f:
                        f.write(_txt)
                except Exception as e:
                    SRV['log']('WEB', f'lobby news save failed ({_nm}): {e!r}')
            SRV['log']('WEB', f'{user} updated the lobby news '
                              f'({len(qs.get("news", [""])[0].splitlines())} news line(s), '
                              f'{len(qs.get("welcome", [""])[0].strip())} welcome chars)')
            # v870f5: NO push to connected clients here - the News pane is append-only until the client
            # re-opens the page and asks again (0xca), and an unsolicited push would double the text.
            # The request is now always answered (the pilot-select push that swallowed it is gone),
            # so pilots see the edit the next time they open the News tab.
            self.send_response(302); self.send_header('Location', '/admin/lobby_news?saved=1'); self.end_headers()
            return

        if self.path == '/register':
            acct = qs.get('account_name', [''])[0].strip()
            pwd = qs.get('password', [''])[0].strip()
            
            if acct and pwd:
                try:
                    SRV['generate_ticket'](acct) 
                    
                    conn = sqlite3.connect(SRV['db_path'])
                    is_adm = 1 if acct.lower() == 'admin' else 0
                    conn.execute("UPDATE accounts SET web_password=?, is_admin=? WHERE account_name=?", (hash_password(pwd), is_adm, acct))
                    conn.commit()
                    conn.close()
                    
                    self.send_html(f"<h2>Success</h2><p>Account '{acct}' registered!</p><a href='/login'>Go to Login</a>")
                except Exception as e:
                    self.send_html(f"<h2 style='color:red;'>Registration Failed</h2><p>{str(e)}</p><a href='/register'>Try Again</a>")

        elif self.path == '/login':
            acct = qs.get('account_name', [''])[0].strip()
            pwd = qs.get('password', [''])[0].strip()
            
            conn = sqlite3.connect(SRV['db_path'])
            record = conn.execute("SELECT web_password FROM accounts WHERE account_name=?", (acct,)).fetchone()
            conn.close()
            
            if record and record[0] == hash_password(pwd):
                token = secrets.token_hex(16)
                WEB_SESSIONS[token] = acct
                self.send_response(302)
                self.send_header('Set-Cookie', f'session={token}; Path=/; HttpOnly')
                self.send_header('Location', '/')
                self.end_headers()
            else:
                self.send_html("<h2 style='color:red;'>Login Failed</h2><p>Invalid credentials or account does not exist.</p><a href='/login'>Back</a>")

        elif self.path == '/update_path':
            if not user: return self.send_error(401)
            new_path = qs.get('client_path', [''])[0].strip()
            
            conn = sqlite3.connect(SRV['db_path'])
            conn.execute("UPDATE accounts SET client_path=? WHERE account_name=?", (new_path, user))
            conn.commit()
            conn.close()
            
            self.send_response(302)
            self.send_header('Location', '/')
            self.end_headers()

        elif self.path == '/launch':
            if not user: return self.send_error(401)
            
            conn = sqlite3.connect(SRV['db_path'])
            client_path = conn.execute("SELECT client_path FROM accounts WHERE account_name=?", (user,)).fetchone()[0]
            conn.close()
            client_path = client_path if client_path else DEFAULT_CLIENT_PATH
            
            try:
                ticket_bytes, pid_hex = SRV['get_existing_ticket'](user)
                
                game_dir = os.path.dirname(client_path)
                ticket_path = os.path.join(game_dir, 'ticket.vr1')
                with open(ticket_path, 'wb') as f:
                    f.write(ticket_bytes)
                
                cmd_string = f'"{client_path}" /NET /Name:{pid_hex} /MK:0 "/MCD1:0 /MCD2:0 /MTD:0 /NoPreload /PPS:5 /FPS:50 /SDM:1000"'
                
                SRV['log']('WEB', f'Launching game locally for {user}: {cmd_string}')
                subprocess.Popen(cmd_string, cwd=game_dir)
                
                self.send_html(f"<h2>Game Launched!</h2><p>Deployed to: {game_dir}</p><a href='/'>Back to Dashboard</a>")
            except Exception as e:
                self.send_html(f"<h2 style='color:red;'>Launch Error</h2><p>{str(e)}</p><a href='/'>Back</a>")
                
        elif self.path == '/squadrons/manage':
            # v851f5: commander/officer management of their own squadron (see the GET card)
            if not user: return self.send_error(401)
            sid = qs.get('squadron_id', [''])[0].strip(); member = qs.get('member', [''])[0].strip()
            op = qs.get('op', [''])[0].strip()
            if not sid.isdigit() or not member:
                return self.send_error(400)
            conn = sqlite3.connect(SRV['db_path'])
            try:
                _mypilots = [p for (p,) in conn.execute("SELECT pilot_name FROM pilots WHERE account_name=?", (user,)).fetchall()]
                _my = conn.execute(
                    "SELECT role FROM squadron_members WHERE squadron_id=? AND status='approved' AND account_name IN (%s) "
                    "ORDER BY CASE role WHEN 'commander' THEN 0 WHEN 'officer' THEN 1 ELSE 2 END LIMIT 1"
                    % ','.join('?' * max(1, len(_mypilots))), (int(sid), *(_mypilots or ['']))).fetchone()
                _myrole = _my[0] if _my else None
                if _myrole not in ('commander', 'officer'):
                    conn.close(); return self.send_error(403)
                _trow = conn.execute("SELECT role, status FROM squadron_members WHERE squadron_id=? AND account_name=?",
                                     (int(sid), member)).fetchone()
                if _trow is None:
                    conn.close(); return self.send_error(404)
                _trole = _trow[0]
                # v871f5: an officer may not REMOVE or re-ROLE the commander, but may set anyone's tag
                # (the CO's ^CO included) - the blanket rule refused an officer tagging his own CO (403)
                if _myrole == 'officer' and (op == 'setrole' or (_trole == 'commander' and op == 'remove')):
                    conn.close(); return self.send_error(403)
                msg = ''
                if op == 'setrole':
                    role = qs.get('role', ['member'])[0].strip()
                    if role in ('member', 'officer', 'commander'):
                        conn.execute("UPDATE squadron_members SET role=? WHERE squadron_id=? AND account_name=?", (role, int(sid), member))
                        if role == 'commander':
                            conn.execute("UPDATE squadrons SET commander=? WHERE squadron_id=?", (member, int(sid)))
                            conn.execute("UPDATE squadron_members SET role='officer' WHERE squadron_id=? AND role='commander' AND account_name<>?", (int(sid), member))
                        msg = f'{member} role -> {role}'
                elif op == 'remove':
                    conn.execute("DELETE FROM squadron_members WHERE squadron_id=? AND account_name=?", (int(sid), member))
                    _c = conn.execute("SELECT commander FROM squadrons WHERE squadron_id=?", (int(sid),)).fetchone()
                    if _c and _c[0] == member:
                        conn.execute("UPDATE squadrons SET commander='' WHERE squadron_id=?", (int(sid),))
                    msg = f'{member} removed'
                elif op == 'approve':
                    conn.execute("UPDATE squadron_members SET status='approved' WHERE squadron_id=? AND account_name=?", (int(sid), member))
                    msg = f'{member} approved'
                elif op == 'setrank':
                    rank = qs.get('rank', [''])[0].strip()[:6]
                    _allowed = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-')
                    if any(c not in _allowed for c in rank):
                        conn.close(); return self.send_html("<h2 style='color:red;'>Tag may use letters, digits, _ and - only</h2><a href='/squadrons'>Back</a>")
                    _base = member.split('^', 1)[0]
                    new_name = (_base + '^' + rank) if rank else _base
                    if new_name != member:
                        if len(new_name) > 24:
                            conn.close(); return self.send_html("<h2 style='color:red;'>Name with tag would exceed 24 characters</h2><a href='/squadrons'>Back</a>")
                        if conn.execute("SELECT 1 FROM pilots WHERE pilot_name=?", (new_name,)).fetchone():
                            conn.close(); return self.send_html(f"<h2 style='color:red;'>A pilot named {hesc(new_name)} already exists</h2><a href='/squadrons'>Back</a>")
                        # the rename with the v850 carry-over: pilot record, membership rows, command
                        conn.execute("UPDATE pilots SET pilot_name=? WHERE pilot_name=?", (new_name, member))
                        conn.execute("UPDATE squadron_members SET account_name=? WHERE account_name=?", (new_name, member))
                        conn.execute("UPDATE squadrons SET commander=? WHERE commander=?", (new_name, member))
                        msg = f'{member} -> {new_name}'
                conn.commit()
                if msg:
                    SRV['log']('WEB', f'{user} ({_myrole}) squadron {sid}: {msg}')
            finally:
                conn.close()
            self.send_response(302); self.send_header('Location', '/squadrons'); self.end_headers()

        elif self.path == '/squadrons/create':
            if not user: return self.send_error(401)
            name = qs.get('name', [''])[0].strip()[:31]
            tag = qs.get('tag', [''])[0].strip()[:31]
            motto = qs.get('motto', [''])[0].strip()
            password = qs.get('password', [''])[0].strip()[:31]
            commander = qs.get('commander', [''])[0].strip()
            if name and commander:
                try:
                    conn = sqlite3.connect(SRV['db_path'])
                    # the commander must be one of THIS account's pilots (squadrons are per-pilot,
                    # keyed by pilot name to match in-game membership)
                    owns = conn.execute("SELECT 1 FROM pilots WHERE account_name=? AND pilot_name=?",
                                        (user, commander)).fetchone()
                    if owns:
                        _now = time.strftime('%Y-%m-%d %H:%M:%S')
                        cur = conn.execute(
                            "INSERT INTO squadrons(name, tag, password, motto, status, commander, created_at) "
                            "VALUES(?,?,?,?, 'pending', ?, ?)", (name, tag, password, motto, commander, _now))
                        sid = cur.lastrowid
                        conn.execute(
                            "INSERT INTO squadron_members(squadron_id, account_name, role, status, joined_at) "
                            "VALUES(?,?, 'commander', 'approved', ?)", (sid, commander, _now))
                        conn.commit()
                        SRV['log']('WEB', f'{user} created squadron {name!r} cmdr={commander!r} (pending, id={sid})')
                    conn.close()
                except Exception as e:
                    SRV['log']('WEB', f'{user} create squadron failed: {e}')
            self.send_response(302); self.send_header('Location', '/squadrons'); self.end_headers()

        elif self.path == '/admin/delete_user':
            if not is_user_admin(user): return self.send_error(403)
            target_user = qs.get('account_name', [''])[0].strip()
            if target_user and target_user != user:
                conn = sqlite3.connect(SRV['db_path'])
                # Delete from accounts and cascade to pilots
                conn.execute("DELETE FROM accounts WHERE account_name=?", (target_user,))
                conn.execute("DELETE FROM pilots WHERE account_name=?", (target_user,))
                conn.commit()
                conn.close()
                SRV['log']('WEB', f'Admin {user} deleted account: {target_user}')
            self.send_response(302)
            self.send_header('Location', '/admin')
            self.end_headers()

        elif self.path == '/admin/reset_password':
            if not is_user_admin(user): return self.send_error(403)
            target_user = qs.get('account_name', [''])[0].strip()
            new_pwd = qs.get('new_password', [''])[0].strip()
            if target_user and new_pwd:
                conn = sqlite3.connect(SRV['db_path'])
                conn.execute("UPDATE accounts SET web_password=? WHERE account_name=?", (hash_password(new_pwd), target_user))
                conn.commit()
                conn.close()
                SRV['log']('WEB', f'Admin {user} reset password for: {target_user}')
            self.send_response(302)
            self.send_header('Location', '/admin')
            self.end_headers()

        elif self.path == '/admin/set_admin':
            # v418f5: promote/demote an account. Any admin may flip any OTHER account's
            # is_admin flag. Two refusals, enforced here (not merely hidden in the HTML):
            #   * your own account - self-demotion mid-session is a lock-out footgun, and
            #     self-"promotion" is a no-op (you got here, so you are already admin);
            #   * the built-in 'admin' account - init_db pins is_admin=1 on every start,
            #     so a demote would silently revert on restart. Refusing is honest.
            if not is_user_admin(user): return self.send_error(403)
            target_user = qs.get('account_name', [''])[0].strip()
            make_admin = 1 if qs.get('make_admin', ['0'])[0].strip() == '1' else 0
            if target_user and target_user != user and target_user != 'admin':
                conn = sqlite3.connect(SRV['db_path'])
                cur = conn.execute("UPDATE accounts SET is_admin=? WHERE account_name=?",
                                   (make_admin, target_user))
                conn.commit()
                conn.close()
                if cur.rowcount:
                    verb = 'promoted' if make_admin else 'demoted'
                    SRV['log']('WEB', f'Admin {user} {verb} account: {target_user} (is_admin={make_admin})')
            self.send_response(302)
            self.send_header('Location', '/admin')
            self.end_headers()

        elif self.path == '/admin/squadron_approve':
            if not is_user_admin(user): return self.send_error(403)
            sid = qs.get('squadron_id', [''])[0].strip()
            if sid.isdigit():
                conn = sqlite3.connect(SRV['db_path'])
                conn.execute("UPDATE squadrons SET status='approved' WHERE squadron_id=?", (int(sid),))
                conn.commit(); conn.close()
                SRV['log']('WEB', f'Admin {user} approved squadron id={sid}')
            self.send_response(302); self.send_header('Location', '/admin'); self.end_headers()

        elif self.path == '/admin/squadron_edit':
            if not is_user_admin(user): return self.send_error(403)
            sid = qs.get('squadron_id', [''])[0].strip()
            if sid.isdigit():
                name = qs.get('name', [''])[0].strip()[:31]
                tag = qs.get('tag', [''])[0].strip()[:31]
                motto = qs.get('motto', [''])[0].strip()
                password = qs.get('password', [''])[0].strip()[:31]
                if name:
                    conn = sqlite3.connect(SRV['db_path'])
                    conn.execute("UPDATE squadrons SET name=?, tag=?, motto=?, password=? WHERE squadron_id=?",
                                 (name, tag, motto, password, int(sid)))
                    conn.commit(); conn.close()
                    SRV['log']('WEB', f'Admin {user} edited squadron id={sid} name={name!r}')
            self.send_response(302); self.send_header('Location', '/admin'); self.end_headers()

        elif self.path == '/admin/squadron_delete':
            if not is_user_admin(user): return self.send_error(403)
            sid = qs.get('squadron_id', [''])[0].strip()
            if sid.isdigit():
                conn = sqlite3.connect(SRV['db_path'])
                conn.execute("DELETE FROM squadron_members WHERE squadron_id=?", (int(sid),))
                conn.execute("DELETE FROM squadrons WHERE squadron_id=?", (int(sid),))
                conn.commit(); conn.close()
                SRV['log']('WEB', f'Admin {user} deleted squadron id={sid}')
            self.send_response(302); self.send_header('Location', '/admin'); self.end_headers()

        elif self.path == '/admin/squadron_member':
            if not is_user_admin(user): return self.send_error(403)
            sid = qs.get('squadron_id', [''])[0].strip()
            member = qs.get('member', [''])[0].strip()
            op = qs.get('op', [''])[0].strip()
            if sid.isdigit() and member:
                conn = sqlite3.connect(SRV['db_path'])
                if op == 'setrole':
                    role = qs.get('role', ['member'])[0].strip()
                    if role in ('member', 'officer', 'commander'):
                        conn.execute("UPDATE squadron_members SET role=? WHERE squadron_id=? AND account_name=?",
                                     (role, int(sid), member))
                        if role == 'commander':
                            conn.execute("UPDATE squadrons SET commander=? WHERE squadron_id=?", (member, int(sid)))
                elif op in ('remove', 'reject'):
                    conn.execute("DELETE FROM squadron_members WHERE squadron_id=? AND account_name=?",
                                 (int(sid), member))
                elif op == 'approve':
                    conn.execute("UPDATE squadron_members SET status='approved' "
                                 "WHERE squadron_id=? AND account_name=?", (int(sid), member))
                conn.commit(); conn.close()
                SRV['log']('WEB', f'Admin {user} squadron id={sid} member {member!r} op={op}')
            self.send_response(302); self.send_header('Location', '/admin'); self.end_headers()

        elif self.path == '/admin/edit_arena':
            if not is_user_admin(user): return self.send_error(403)
            try:
                rid = int(qs.get('room_id', ['0'])[0])
            except (ValueError, TypeError):
                rid = 0
            room_name = qs.get('room_name', [''])[0].strip() or 'Unnamed'
            category  = qs.get('category', [''])[0].strip() or 'Custom Arenas'
            status    = qs.get('status', ['open'])[0].strip()
            if status not in ('open', 'closed'):
                status = 'open'
            if rid:
                conn = sqlite3.connect(SRV['db_path'])
                rcols = [r[1] for r in conn.execute("PRAGMA table_info(rooms)").fetchall()]
                # v475: the persistent checkbox lives in THIS form (row form -> this endpoint,
                # its own handler - the settings form posts elsewhere and never touches it).
                # Absence of the field = unchecked = 0, standard checkbox semantics.
                _pers = 1 if qs.get('persistent', [''])[0] == '1' else 0
                _pers_set = ', persistent=?' if 'persistent' in rcols else ''
                _pers_args = [_pers] if _pers_set else []
                if 'category' in rcols:
                    conn.execute("UPDATE rooms SET room_name=?, category=?, status=?"
                                 + _pers_set + " WHERE room_id=?",
                                 (room_name, category, status, *_pers_args, rid))
                else:
                    conn.execute("UPDATE rooms SET room_name=?, status=?"
                                 + _pers_set + " WHERE room_id=?",
                                 (room_name, status, *_pers_args, rid))
                conn.commit(); conn.close()
                SRV['log']('WEB', f"Admin {user} edited arena {rid}: name={room_name!r} title={category!r} "
                                  f"status={status}"
                                  + (f" persistent={_pers}" if _pers_set else ""))
            self.send_response(302)
            self.send_header('Location', '/admin')
            self.end_headers()

        elif self.path == '/admin/edit_pilot':
            if not is_user_admin(user): return self.send_error(403)
            pilot = qs.get('pilot', [''])[0].strip()
            def _clamp(name, lo, hi, default=0):
                try:
                    v = int(qs.get(name, [str(default)])[0])
                except (ValueError, TypeError):
                    v = default
                return max(lo, min(hi, v))
            # v240: every column that feeds the msg-25 stat block (the HQ Scores screen).
            # (column, lo, hi) - the bounds match each slot's wire width so a typo can't corrupt the
            # packet. rank is capped at 12 because the client clamps anything higher to 12 anyway.
            SAVE_FIELDS = [
                ('rank',           0, 12),           # f0  u8
                ('deaths',         0, 65535),        # f1  u16  "Lost Pilots"
                ('kills_fighters', 0, 65535),        # f2  u16
                ('kills_bombers',  0, 65535),        # f3  u16
                ('planes_lost',    0, 65535),        # f4  u16
                ('kills',          0, 65535),        # f5  u16
                ('kills_in_a_row', 0, 255),          # f7  u8
                ('aces',           0, 255),          # f8  u8
                ('score',          -2147483648, 2147483647),   # f9  float (Fighter Score)
                ('bomber_score',   -2147483648, 2147483647),   # f10 float
                ('ai_fighters',    0, 65535),        # f11 u16
                ('ai_bombers',     0, 65535),        # f12 u16
                ('planes_lost_ai', 0, 65535),        # f13 u16
                ('ai_ships',       0, 65535),        # f16 u16
                ('ai_tanks',       0, 65535),        # f17 u16
                ('ai_ground',      0, 65535),        # f18 u16
                ('ai_buildings',   0, 65535),        # f19 u16
                # v410f5: per-mode ladder boards (web-only; same widths as career counterparts)
                ('score_ffa',      -2147483648, 2147483647),
                ('bscore_ffa',     -2147483648, 2147483647),
                ('kills_ffa',      0, 65535),
                ('deaths_ffa',     0, 65535),
                ('score_tc',       -2147483648, 2147483647),
                ('bscore_tc',      -2147483648, 2147483647),
                ('kills_tc',       0, 65535),
                ('deaths_tc',      0, 65535),
                ('score_events',   -2147483648, 2147483647),
                ('bscore_events',  -2147483648, 2147483647),
                ('kills_events',   0, 65535),
                ('deaths_events',  0, 65535),
            ]
            if pilot:
                conn = sqlite3.connect(SRV['db_path'])
                exists = conn.execute("SELECT 1 FROM pilots WHERE pilot_name=?", (pilot,)).fetchone()
                if exists:
                    pcols = [r[1] for r in conn.execute("PRAGMA table_info(pilots)").fetchall()]
                    # Only touch columns that (a) exist in this DB and (b) were actually posted, so an
                    # un-migrated DB or a partial form still saves cleanly.
                    upd = [(c, _clamp(c, lo, hi)) for c, lo, hi in SAVE_FIELDS
                           if c in pcols and c in qs]
                    if upd:
                        sets = ', '.join(f'{c}=?' for c, _v in upd)
                        args = [v for _c, v in upd] + [pilot]
                        conn.execute(f"UPDATE pilots SET {sets} WHERE pilot_name=?", args)
                        conn.commit()
                        SRV['log']('WEB', f"Admin {user} edited pilot {pilot!r} stats: "
                                          + ' '.join(f'{c}={v}' for c, v in upd))
                conn.close()
            self.send_response(302)
            self.send_header('Location', '/admin')
            self.end_headers()

        elif self.path == '/admin/console_cmd':
            # v317: run a server console command from the web. The command is queued onto the
            # SAME queue the server terminal feeds, so console_handler executes it identically;
            # its log('CONSOLE', ...) output shows up in the live stream on this page.
            if not is_user_admin(user): return self.send_error(403)
            cmd = qs.get('cmd', [''])[0].strip()
            runner = SRV.get('exec_console')
            if cmd and runner:
                try:
                    runner(cmd, 'web:' + str(user))
                    SRV['log']('WEB', f'Admin {user} ran console command: {cmd!r}')
                except Exception as e:
                    SRV['log']('WEB', f'console command failed: {e!r}')
            elif not runner:
                SRV['log']('WEB', 'console command ignored - server did not inject a runner')
            self.send_response(204)      # fetch() call; the page refreshes the log itself
            self.end_headers()

        elif self.path == '/admin/rename_account':
            if not is_user_admin(user): return self.send_error(403)
            old = qs.get('account_name', [''])[0].strip()
            ok, new = _valid_name(qs.get('new_name', [''])[0])
            if not ok:
                self.send_html(f"<h2 style='color:red;'>Rename failed</h2><p>{hesc(new)}</p>"
                               "<a href='/admin'>&larr; Back to Admin</a>")
                return
            conn = _connect()
            try:
                if not conn.execute("SELECT 1 FROM accounts WHERE account_name=?", (old,)).fetchone():
                    raise ValueError(f'No such account "{old}".')
                if new.lower() != old.lower() and _name_taken(conn, 'accounts', 'account_name', new):
                    raise ValueError(f'An account named "{new}" already exists.')
                done = _rename_everywhere(conn, ACCOUNT_REFS, old, new)
                conn.commit()
            except Exception as e:
                conn.rollback(); conn.close()
                self.send_html(f"<h2 style='color:red;'>Rename failed</h2><p>{hesc(str(e))}</p>"
                               "<a href='/admin'>&larr; Back to Admin</a>")
                return
            conn.close()
            # Keep any live web session pointing at the renamed account.
            for tok, who in list(WEB_SESSIONS.items()):
                if who == old:
                    WEB_SESSIONS[tok] = new
            SRV['log']('WEB', f'Admin {user} renamed account {old!r} -> {new!r} ({", ".join(done)})')
            self.send_html(
                "<h2>Account renamed</h2>"
                f"<p><strong>{hesc(old)}</strong> is now <strong>{hesc(new)}</strong>.<br>"
                f"<small style='color:#666;'>Updated: {hesc(', '.join(done) or 'nothing')}</small></p>"
                "<div class='card' style='border-left:4px solid #ffc107;'>"
                "<strong>The ticket must be re-downloaded.</strong><br>"
                "The player_id is unchanged, so all pilots, stats and arenas stay attached - but the "
                "account name is stored <em>inside</em> the .vr1 ticket, and the game server "
                "identifies a connection by the name in the ticket before anything else. Until this "
                "account logs in to the web page and launches/downloads again, its old ticket will "
                "re-create the old account name on connect.</div>"
                "<a href='/admin'>&larr; Back to Admin</a>")

        elif self.path == '/admin/rename_pilot':
            if not is_user_admin(user): return self.send_error(403)
            old = qs.get('pilot', [''])[0].strip()
            ok, new = _valid_name(qs.get('new_name', [''])[0])
            if not ok:
                self.send_html(f"<h2 style='color:red;'>Rename failed</h2><p>{hesc(new)}</p>"
                               "<a href='/admin'>&larr; Back to Admin</a>")
                return
            conn = _connect()
            try:
                if not conn.execute("SELECT 1 FROM pilots WHERE pilot_name=?", (old,)).fetchone():
                    raise ValueError(f'No such pilot "{old}".')
                if new.lower() != old.lower() and _name_taken(conn, 'pilots', 'pilot_name', new):
                    raise ValueError(f'A pilot named "{new}" already exists.')
                done = _rename_everywhere(conn, PILOT_REFS, old, new)
                conn.commit()
            except Exception as e:
                conn.rollback(); conn.close()
                self.send_html(f"<h2 style='color:red;'>Rename failed</h2><p>{hesc(str(e))}</p>"
                               "<a href='/admin'>&larr; Back to Admin</a>")
                return
            conn.close()
            SRV['log']('WEB', f'Admin {user} renamed pilot {old!r} -> {new!r} ({", ".join(done)})')
            self.send_response(302)
            self.send_header('Location', '/admin')
            self.end_headers()

        elif self.path == '/admin/create_pilot':
            if not is_user_admin(user): return self.send_error(403)
            acct = qs.get('account_name', [''])[0].strip()
            ok, pname = _valid_name(qs.get('pilot_name', [''])[0])
            if not ok:
                self.send_html(f"<h2 style='color:red;'>Create failed</h2><p>{hesc(pname)}</p>"
                               "<a href='/admin'>&larr; Back to Admin</a>")
                return
            conn = _connect()
            try:
                if not conn.execute("SELECT 1 FROM accounts WHERE account_name=?", (acct,)).fetchone():
                    raise ValueError(f'No such account "{acct}".')
                if _name_taken(conn, 'pilots', 'pilot_name', pname):
                    raise ValueError(f'A pilot named "{pname}" already exists.')
                pcols = [r[1] for r in conn.execute("PRAGMA table_info(pilots)").fetchall()]
                cols, vals = ['pilot_name', 'account_name'], [pname, acct]
                if 'slot_index' in pcols:
                    row = conn.execute("SELECT MAX(slot_index) FROM pilots WHERE account_name=?",
                                       (acct,)).fetchone()
                    cols.append('slot_index'); vals.append((row[0] or 0) + 1)
                conn.execute("INSERT INTO pilots (" + ','.join(cols) + ") VALUES ("
                             + ','.join('?' * len(cols)) + ")", vals)
                conn.commit()
            except Exception as e:
                conn.rollback(); conn.close()
                self.send_html(f"<h2 style='color:red;'>Create failed</h2><p>{hesc(str(e))}</p>"
                               "<a href='/admin'>&larr; Back to Admin</a>")
                return
            conn.close()
            SRV['log']('WEB', f'Admin {user} created pilot {pname!r} on account {acct!r}')
            self.send_response(302)
            self.send_header('Location', '/admin')
            self.end_headers()

        elif self.path == '/admin/delete_arena':
            if not is_user_admin(user): return self.send_error(403)
            table = qs.get('table', [''])[0].strip()
            rowid = qs.get('rowid', [''])[0].strip()
            if table in ('rooms', 'arenas') and rowid.isdigit():
                conn = sqlite3.connect(SRV['db_path'])
                conn.execute(f"DELETE FROM {table} WHERE rowid=?", (int(rowid),))
                conn.commit()
                conn.close()
                SRV['log']('WEB', f'Admin {user} deleted arena ID {rowid} from {table}')
            self.send_response(302)
            self.send_header('Location', '/admin')
            self.end_headers()

        elif self.path == '/admin/arena_settings':
            try:
                rid = int(qs.get('room_id', ['0'])[0])
            except (ValueError, TypeError):
                rid = 0
            # Admins may edit any arena; a regular player may edit only arenas they created.
            if not user_can_edit_arena(user, rid):
                return self.send_error(403)
            room_name = qs.get('room_name', [''])[0].strip() or 'Unnamed'
            category  = qs.get('category', [''])[0].strip() or 'Custom Arenas'
            status    = qs.get('status', ['open'])[0].strip()
            if status not in ('open', 'closed'): status = 'open'
            # collect the arena-setting fields (name prefix s_) into a {key: feet} override dict.
            # Blank fields are omitted so the GAME_DEF keeps its as-created value for them.
            settings = {}
            for key, delta, label in SRV.get('tail_fields', []):
                v = qs.get('s_' + key, [''])[0].strip()
                if v != '':
                    try:
                        settings[key] = int(round(float(v)))
                    except ValueError:
                        pass
            # EvP AA/Flak sliders (0..6). Always present (range inputs post a value), stored as
            # ints clamped to 0..6 under their own keys; read per-arena by the game server.
            for skey in ('aa_quality', 'flak_quality', 'bomber_gunner', 'ship_aa', 'tank_aa'):
                v = qs.get('s_' + skey, [''])[0].strip()
                if v != '':
                    try:
                        settings[skey] = max(0, min(6, int(round(float(v)))))
                    except ValueError:
                        pass
            # WAR DATE (v383): opt-in checkbox + full date. The checkbox only posts when ticked, so
            # its absence means off. The date values are stored regardless so toggling back on
            # remembers them. The game server reads war_enabled/war_year/war_month/war_day per arena.
            settings['war_enabled'] = 1 if qs.get('s_war_enabled', [''])[0].strip() else 0
            # FIGHTERS ONLY (v391): checkbox only posts when ticked; absence means off.
            settings['fighters_only'] = 1 if qs.get('s_fighters_only', [''])[0].strip() else 0
            # DATE, TIME & WEATHER (v948f5): checkbox + the rw_* fields; values stored whether or not the
            # override is on, so toggling it back on remembers them. Blank fields are left out (the
            # game server keeps the template's value for those).
            settings['rw_enabled'] = 1 if qs.get('s_rw_enabled', [''])[0].strip() else 0
            for _rk, _lo, _hi, _isf in (('rw_day', 1, 31, 0), ('rw_month', 1, 12, 0), ('rw_year', 1900, 2000, 0),
                                        ('rw_hour', 0, 23, 0), ('rw_minute', 0, 59, 0), ('rw_tz', -720, 840, 0),
                                        ('rw_time_speed', 0, 100, 1), ('rw_night_speed', 0, 100, 1),
                                        ('rw_lat', -90, 90, 1), ('rw_lon', -180, 180, 1),
                                        ('rw_wind_type', 0, 2, 0), ('rw_wind_speed', 0, 60, 1), ('rw_wind_dir', 0, 359, 0),
                                        ('rw_wind_rot_time', 12, 26, 0), ('rw_wind_min', 0, 60, 1), ('rw_wind_max', 0, 60, 1),
                                        ('rw_wind_osc_time', 12, 26, 0), ('rw_clouds_type', 0, 2, 0),
                                        ('rw_clouds_density', 0, 100, 0), ('rw_clouds_min', 0, 20000, 0), ('rw_clouds_max', 0, 20000, 0)):
                _rv = qs.get('s_' + _rk, [''])[0].strip()
                if _rv == '':
                    continue
                try:
                    _rf = float(_rv)
                    settings[_rk] = round(max(_lo, min(_hi, _rf)), 3) if _isf else int(round(max(_lo, min(_hi, _rf))))
                except ValueError:
                    pass
            settings['rw_rain'] = 1 if qs.get('s_rw_rain', [''])[0].strip() else 0
            settings['clock_static'] = 1 if qs.get('s_clock_static', [''])[0].strip() else 0   # v949f5 arena world clock
            _wc = qs.get('s_weather_cycle', [''])[0].strip()                                 # v962f5 dynamic weather
            if _wc == '':
                settings.pop('weather_cycle', None)
            else:
                try:
                    settings['weather_cycle'] = max(0, min(240, int(_wc)))
                except ValueError:
                    pass
            _wm = qs.get('s_weather_max_wind', [''])[0].strip()                              # v962f5c max wind for the cycle
            if _wm == '':
                settings.pop('weather_max_wind', None)
            else:
                try:
                    settings['weather_max_wind'] = round(max(0.0, min(60.0, float(_wm))), 1)
                except ValueError:
                    pass
            # RADAR (v949f5): the server gate (radar_enabled ''/1/0, radar_visual_m, radar_friends ''/1/0) and the
            # GAME_DEF [Radar] override (rd_enabled + rd_* fields; the two checkboxes are stored as 1/0).
            for _gk in ('radar_enabled', 'radar_friends'):
                _gv = qs.get('s_' + _gk, [''])[0].strip()
                if _gv in ('0', '1'):
                    settings[_gk] = _gv
                else:
                    settings.pop(_gk, None)
            for _gk, _glo, _ghi in (('radar_visual_m', 1000, 100000), ('radar_agl_m', 0, 5000)):
                _gv = qs.get('s_' + _gk, [''])[0].strip()
                try:
                    settings[_gk] = int(max(_glo, min(_ghi, float(_gv)))) if _gv else None
                except ValueError:
                    settings[_gk] = None
                if settings.get(_gk) is None:
                    settings.pop(_gk, None)
            settings['rd_enabled'] = 1 if qs.get('s_rd_enabled', [''])[0].strip() else 0
            for _rk, _lo, _hi, _isf in (('rd_always_vis', 0, 100000, 1), ('rd_range_mult', 0.1, 10, 1),
                                        ('rd_above_terrain', 0, 5000, 1), ('rd_show_range', 0, 3, 0)):
                _rv = qs.get('s_' + _rk, [''])[0].strip()
                if _rv == '':
                    continue
                try:
                    _rf = float(_rv)
                    settings[_rk] = round(max(_lo, min(_hi, _rf)), 3) if _isf else int(round(max(_lo, min(_hi, _rf))))
                except ValueError:
                    pass
            settings['rd_works'] = 1 if qs.get('s_rd_works', [''])[0].strip() else 0
            settings['rd_apply_local'] = 1 if qs.get('s_rd_apply_local', [''])[0].strip() else 0
            # TOURNAMENT (v952f5): checkboxes stored 1/0, numbers only when given (blank = template value)
            for _tk in ('tn_enabled', 'tn_ghosting', 'tn_allow_tabbing', 'tn_last_is_winner', 'ev_enabled', 'ev_fly_button'):
                settings[_tk] = 1 if qs.get('s_' + _tk, [''])[0].strip() else 0
            _scr = qs.get('s_ev_script', [''])[0].strip()
            if _scr:
                try:
                    _j = json.loads(_scr)
                    if not isinstance(_j, dict):
                        raise ValueError('the script must be a JSON object')
                    if SRV.get('evs_parse'):                       # v958f5e: full engine validation
                        _sc_ok, _sc_err = SRV['evs_parse'](_scr)
                        if _sc_err:
                            raise ValueError(_sc_err)
                    settings['ev_script'] = _scr
                except Exception as _ex:
                    self.send_html(f"<h2 style='color:red;'>Event script not saved</h2><p>{hesc(str(_ex))}</p>"
                                   "<p>Fix the JSON and save again (the other settings were not saved either).</p>"
                                   f"<a href='/admin/arena_settings?room_id={rid}#events'>&larr; Back to the arena</a>")
                    return
            else:
                settings.pop('ev_script', None)
            for _tk, _lo, _hi in (('tn_lives', 0, 99), ('tn_start_delay', 0, 240), ('tn_shoot_delay', 0, 240), ('ev_start_delay', 0, 240),
                                  ('ev_length', 0, 1440)):
                _tv = qs.get('s_' + _tk, [''])[0].strip()
                try:
                    settings[_tk] = int(max(_lo, min(_hi, float(_tv)))) if _tv else None
                except ValueError:
                    settings[_tk] = None
                if settings.get(_tk) is None:
                    settings.pop(_tk, None)
            # AIRCRAFT PER TEAM (v932f5): the grid posts pt_<slot>_<camp>=1 for every tick. Store only
            # the planes whose tick set differs from the server's default nation table; [] = hidden.
            # The grid is always on the page (pt_present), so a save without it keeps nothing stale.
            if qs.get('pt_present', [''])[0].strip():
                try:
                    _roster = SRV['plane_roster']() if SRV.get('plane_roster') else []
                except Exception:
                    _roster = []
                _pt = {}
                for slot, name, dcamp, is_bomber, year in _roster:
                    picked = [c for c in (0, 1, 2, 3, 4) if qs.get('pt_%d_%d' % (slot, c), [''])[0].strip()]
                    default = [dcamp] if dcamp in (0, 1, 2, 3, 4) else []
                    if picked != default:
                        _pt[name] = picked
                if _pt:
                    settings['plane_teams'] = _pt
            # EXIT = CRASH (v400f5): checkbox only posts when ticked; absence means off (the
            # default - an undamaged airborne exit is a clean bug-out, not a death).
            settings['exit_is_crash'] = 1 if qs.get('s_exit_is_crash', [''])[0].strip() else 0
            # SHOW GROUND OBJECTS (v719f5): default ON. Checkbox absence = off; a first save with it
            # ticked stores 1. Stored explicitly so the default-on can be turned off per arena.
            settings['show_ground_objects'] = 1 if qs.get('s_show_ground_objects', [''])[0].strip() else 0
            # SCORING MODE (v404f5): only stored when forced; '' (Default) leaves no key so the
            # category keeps deciding.
            _sm = qs.get('s_scoring_mode', [''])[0].strip().lower()
            if _sm in ('ffa', 'tc', 'none', 'events'):
                settings['scoring_mode'] = _sm
            _tk = qs.get('s_team_kills', [''])[0].strip().lower()            # v968f5z
            if _tk in ('everyone', 'teams'):
                settings['team_kills'] = _tk
            _eco = qs.get('s_economy', [''])[0].strip().lower()              # v960f5c
            if _eco in ('on', 'off'):
                settings['economy'] = _eco
            else:
                settings.pop('economy', None)
            _wm = qs.get('s_tc_win_mode', [''])[0].strip().lower()          # v640f5
            if _wm in ('off', 'all', 'eliminated', 'wipeout'):
                settings['tc_win_mode'] = 'eliminated' if _wm == 'wipeout' else _wm   # v933f5
            _smv = qs.get('s_supply_mode', [''])[0].strip().lower()        # v964f5
            if _smv in ('car', 'both'):
                settings['supply_mode'] = _smv
            else:
                settings.pop('supply_mode', None)
            settings['convoy_on_demand'] = 'on' if qs.get('s_convoy_on_demand', [''])[0].strip() else 'off'
            _fsv = qs.get('s_fleet_script', [''])[0].strip()                 # v968f5b
            if _fsv:
                try:
                    _fsd = json.loads(_fsv)
                    if not isinstance(_fsd, dict) or not isinstance(_fsd.get('groups'), list):
                        raise ValueError('top level must be {"groups": [...]}')
                    for _g in _fsd['groups']:
                        if not isinstance(_g, dict) or not _g.get('name'):
                            raise ValueError('every group needs a "name"')
                        if not (_g.get('spawn') or _g.get('patrol')):
                            raise ValueError('group %r needs "spawn" or "patrol"' % _g.get('name'))
                    settings['fleet_script'] = json.dumps(_fsd)
                except Exception as _fe:
                    self.send_html(f"<h2 style='color:red;'>Fleet script not saved</h2><p>{hesc(str(_fe))}</p>"
                                   "<p>Fix the JSON and save again (the other settings were not saved either).</p>"
                                   f"<a href='/admin/arena_settings?room_id={rid}'>&larr; Back to the arena</a>")
                    return
            else:
                settings.pop('fleet_script', None)
            _esc = qs.get('s_convoy_escort', [''])[0].strip().lower()        # v967f5c
            if _esc in ('aa', 'flak', 'none'):
                settings['convoy_escort'] = _esc
            else:
                settings.pop('convoy_escort', None)
            for _ck, _lo, _hi in (('craters_vanish_min', 1, 120), ('craters_vanish_max', 1, 1000), ('trains_per_camp', 0, 12),
                                  ('convoy_minutes', 2, 120)):   # v686f5, v959f5, v964f5
                _cv = qs.get('s_' + _ck, [''])[0].strip()
                if _cv == '':
                    settings.pop(_ck, None)
                else:
                    try:
                        _cvi = int(_cv)
                        if _lo <= _cvi <= _hi:
                            settings[_ck] = _cvi
                    except ValueError:
                        pass
            for _wk, _lo, _hi in (('war_year', 1935, 1955), ('war_month', 1, 12), ('war_day', 1, 31)):
                _wv = qs.get('s_' + _wk, [''])[0].strip()
                if _wv != '':
                    try:
                        settings[_wk] = max(_lo, min(_hi, int(round(float(_wv)))))
                    except ValueError:
                        pass
            if rid:
                conn = sqlite3.connect(SRV['db_path'])
                rcols = [r[1] for r in conn.execute("PRAGMA table_info(rooms)").fetchall()]
                # ARENA PASSWORD (client-side gate): fold the toggle + field into settings_json's
                # 'password' key and keep the denormalised password_protected column in sync. The
                # editor pre-fills the field with the current password, so an unchanged save round-
                # trips it. Semantics: box off -> '' (removed); box on + field -> that password;
                # box on + blank field -> fall back to the existing override / the arena's created-
                # with password; none available -> treated as off.
                pw_req   = bool(qs.get('s_password_protected', [''])[0].strip())
                pw_typed = qs.get('s_password', [''])[0].strip()
                prev_over = {}; blob_pw = ''
                try:
                    _pr = conn.execute("SELECT game_def_raw, COALESCE(settings_json,'{}') "
                                       "FROM rooms WHERE room_id=?", (rid,)).fetchone()
                    if _pr:
                        _blob, _sj = _pr
                        try:
                            _po = json.loads(_sj) if _sj else {}
                            if isinstance(_po, dict): prev_over = _po
                        except Exception:
                            prev_over = {}
                        try:
                            if SRV.get('password_read') and _blob:
                                blob_pw = SRV['password_read'](bytes(_blob)) or ''
                        except Exception:
                            blob_pw = ''
                except Exception:
                    pass
                if not pw_req:
                    desired_pw = ''
                elif pw_typed != '':
                    desired_pw = pw_typed
                else:
                    desired_pw = str(prev_over.get('password') or '') if 'password' in prev_over else blob_pw
                # store the key only when it changes something: a real password, OR an explicit
                # clear of an arena that IS currently protected (created-with or prior override).
                if desired_pw:
                    settings['password'] = desired_pw
                elif blob_pw or ('password' in prev_over):
                    settings['password'] = ''
                pw_col = 1 if desired_pw else 0
                has_pw_col = 'password_protected' in rcols
                if 'settings_json' in rcols and has_pw_col:
                    conn.execute("UPDATE rooms SET room_name=?, category=?, status=?, settings_json=?, "
                                 "password_protected=? WHERE room_id=?",
                                 (room_name, category, status, json.dumps(settings), pw_col, rid))
                elif 'settings_json' in rcols:
                    conn.execute("UPDATE rooms SET room_name=?, category=?, status=?, settings_json=? WHERE room_id=?",
                                 (room_name, category, status, json.dumps(settings), rid))
                else:
                    conn.execute("UPDATE rooms SET room_name=?, category=?, status=? WHERE room_id=?",
                                 (room_name, category, status, rid))
                conn.commit(); conn.close()
                _log_settings = dict(settings)
                if 'password' in _log_settings:      # don't write the arena password to the log
                    _log_settings['password'] = '***' if _log_settings['password'] else ''
                SRV['log']('WEB', f"Admin {user} edited arena {rid}: name={room_name!r} title={category!r} "
                                  f"status={status} password_protected={pw_col} settings={_log_settings}")
                try:
                    if SRV.get('exec_console'):
                        SRV['exec_console'](f'arena_changed {rid}', 'web:settings')   # v953f5e: tell pilots inside to re-enter
                except Exception:
                    pass
            self.send_response(302)
            self.send_header('Location', '/admin' if is_user_admin(user) else '/my_arenas')
            self.end_headers()

    def log_message(self, format, *args):
        pass

    def handle_one_request(self):
        # Suppress the harmless ConnectionResetError (WinError 10054) that occurs when
        # the FA launcher's embedded browser opens a download connection and then hands
        # off to its own WinINet fetch, abandoning the browser's half-opened socket.
        # Nothing actually failed - the real ticket fetch succeeds on its own connection.
        try:
            super().handle_one_request()
        except (ConnectionResetError, ConnectionAbortedError):
            self.close_connection = True

# A per-request-threaded HTTP server. Each request runs in its own daemon thread, so one slow
# or stalled request (a half-open launcher socket, a SQLite lock, a client that opened the
# auto-refreshing console and walked away) can no longer wedge the single accept loop and freeze
# the whole web UI - which is what made it "stop responding after a few hours" under the plain
# serial HTTPServer.
class _ThreadedWebServer(ThreadingHTTPServer):
    daemon_threads = True          # worker threads don't block process/thread shutdown
    allow_reuse_address = True     # let a restart re-bind port 80 immediately (no TIME_WAIT wait)

# 2026-08-23 HOTFIX: the first HTTPS build wrapped the LISTENING socket, which runs the TLS
# handshake inside accept() - i.e. on the single serve_forever loop. Any internet scanner that
# opened TCP to public port 443 and then sent nothing parked the accept loop in a blocking
# handshake with no timeout. Health pings then failed, the watchdog called shutdown(), and
# shutdown() waits for serve_forever() to exit - which it never could - so the watchdog itself
# wedged and the web UI stayed dead until a process restart (field-observed on the GCP VM,
# 2026-08-23 11:27 log). Fix: accept plain TCP on the main loop and perform the handshake in
# the per-connection worker thread, bounded by a 15s timeout. A stalled scanner now costs one
# daemon thread for 15s instead of the whole server.
_TLS_CTX = None

def _tls_context():
    global _TLS_CTX
    if _TLS_CTX is None:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(certfile=WEB_CERT_FILE, keyfile=WEB_KEY_FILE)
        _TLS_CTX = ctx
    return _TLS_CTX

class _TLSThreadedWebServer(_ThreadedWebServer):
    """HTTPS server whose TLS handshake happens in the worker thread (see hotfix note above).
    finish_request() is called by ThreadingMixIn.process_request_thread, already off the accept
    loop, so blocking or garbage handshakes cannot freeze serve_forever()."""
    def finish_request(self, request, client_address):
        request.settimeout(15)      # hard cap on the handshake: silent scanners get dropped
        try:
            tls = _tls_context().wrap_socket(request, server_side=True)
        except (ssl.SSLError, OSError):
            # Plain-HTTP probes, TLS scanners, resets mid-handshake: close quietly, no traceback
            # spam in the journal.
            try:
                request.close()
            except OSError:
                pass
            return
        tls.settimeout(60)          # per-IO cap for real requests; idle keep-alives get reaped
        self.RequestHandlerClass(tls, client_address, self)

# The live server + the thread running it, so the watchdog can restart just this part.
_WEB = {'httpd': None, 'thread': None}

def _serve_forever_guarded():
    """Run the current httpd.serve_forever(); if it ever throws, log it instead of silently
    killing the web thread (the old code had no guard, so any unexpected error left the UI dead
    with no trace)."""
    httpd = _WEB.get('httpd')
    if httpd is None:
        return
    try:
        httpd.serve_forever(poll_interval=0.5)
    except Exception as e:
        try:
            SRV['log']('WEB', f'serve_forever exited with error: {e!r}')
        except Exception:
            pass

def _build_httpd():
    server_address = ('', WEB_PORT)
    # 2026-08-23 HOTFIX: TLS handshakes must not run on the accept loop - see the note above
    # _TLSThreadedWebServer. The listening socket itself stays plain TCP in both modes.
    server_cls = _TLSThreadedWebServer if WEB_TLS else _ThreadedWebServer
    httpd = server_cls(server_address, WebInterfaceHandler)
    # Cap how long a single request may tie up its worker. request_queue_size raises the accept
    # backlog so bursts don't get refused while workers spin up.
    httpd.timeout = 30
    httpd.request_queue_size = 64
    return httpd

def _start_http_redirector():
    """2026-08-23: When serving HTTPS on 443, keep a tiny listener on port 80 that 301s
    every request to its https:// equivalent, so old http:// bookmarks and bare-hostname
    entries keep working. Runs as a daemon thread with no watchdog - if it ever dies the
    main site is unaffected. If port 80 is already taken the failure is logged and the
    redirector is simply skipped."""
    class _RedirectHandler(BaseHTTPRequestHandler):
        def _redir(self):
            # Redirect to whatever host the client asked for (minus any :port), so both
            # fa-re-srv.ddns.net and localhost tests land on the right https URL.
            host = (self.headers.get('Host') or 'fa-re-srv.ddns.net').split(':')[0]
            self.send_response(301)
            self.send_header('Location', f'https://{host}{self.path}')
            self.send_header('Content-Length', '0')
            self.send_header('Connection', 'close')
            self.end_headers()
        do_GET  = _redir
        do_HEAD = _redir
        do_POST = _redir
        def log_message(self, fmt, *args):
            pass                    # silent - redirect hits are not worth log lines
    try:
        redirector = ThreadingHTTPServer(('', 80), _RedirectHandler)
    except OSError as e:
        SRV['log']('WEB', f'http->https redirector could not bind port 80 ({e!r}) - skipped')
        return
    threading.Thread(target=redirector.serve_forever, name='web-http-redirect',
                     daemon=True).start()
    SRV['log']('WEB', 'http->https redirector listening on port 80')

def _start_httpd_thread():
    """(Re)build the httpd and start its serving thread. Any previous instance must already be
    shut down by the caller. Returns the new thread."""
    _WEB['httpd'] = _build_httpd()
    t = threading.Thread(target=_serve_forever_guarded, name='web-serve', daemon=True)
    t.start()
    _WEB['thread'] = t
    return t

def _restart_httpd(reason=''):
    """Tear down the current web server and stand a fresh one up on the same port. Called by the
    watchdog when the UI stops answering. shutdown() unblocks serve_forever(); server_close()
    frees the listening socket so the rebuild can re-bind."""
    old = _WEB.get('httpd')
    SRV['log']('WEB', f'restarting web server{(" - " + reason) if reason else ""}')
    if old is not None:
        try:
            old.shutdown()          # signals serve_forever() to return (must not be called from
                                    # the serving thread itself - the watchdog is a separate thread)
        except Exception as e:
            SRV['log']('WEB', f'shutdown() during restart raised: {e!r}')
        try:
            old.server_close()      # release the port
        except Exception as e:
            SRV['log']('WEB', f'server_close() during restart raised: {e!r}')
    # Give the old thread a moment to unwind, then rebuild.
    old_thread = _WEB.get('thread')
    if old_thread is not None:
        old_thread.join(timeout=5)
    for attempt in range(1, 6):
        try:
            _start_httpd_thread()
            SRV['log']('WEB', f'web server restarted on {"https" if WEB_TLS else "http"}://localhost:{WEB_PORT}')
            return True
        except OSError as e:
            SRV['log']('WEB', f'rebind attempt {attempt}/5 failed ({e!r}); retrying in 2s')
            time.sleep(2)
    SRV['log']('WEB', 'ERROR: web server could not be restarted after 5 attempts')
    return False

def _health_ping(timeout=10.0):
    """GET http://localhost:<port>/login and return the elapsed seconds, or None if it failed /
    timed out. /login is used because it needs no DB row and no auth, so a slow reply means the
    server itself is wedged, not a slow query. This is the wget-with-10s-timeout check."""
    scheme = 'https' if WEB_TLS else 'http'
    url = f'{scheme}://127.0.0.1:{WEB_PORT}/login'
    start = time.monotonic()
    try:
        # The cert names fa-re-srv.ddns.net, not 127.0.0.1, so a verifying client would fail
        # on hostname mismatch and the watchdog would restart a perfectly healthy server
        # forever. Verification is pointless for a loopback liveness ping anyway.
        insecure = ssl._create_unverified_context() if WEB_TLS else None
        with urllib.request.urlopen(url, timeout=timeout, context=insecure) as r:
            r.read(256)             # drain a little so the handler completes
        return time.monotonic() - start
    except Exception:
        return None

def _wlog(msg, level=None):
    """Log helper that tolerates an injected log_fn which may or may not accept level=."""
    try:
        if level is None:
            SRV['log']('WEB', msg)
        else:
            SRV['log']('WEB', msg, level=level)
    except TypeError:
        SRV['log']('WEB', msg)
    except Exception:
        pass

# v322: the watchdog is SILENT while healthy. It used to log a startup ping, a DEBUG line per
# check, an INFO pulse every 10 checks and a "recovered" line - useful while proving the thing
# worked, pure noise now that it has. It now logs ONLY when a failure actually causes a restart.
#
# Nothing diagnostic is lost: the reason for each bad check is BUFFERED and emitted as part of
# the restart line, so a restart still says exactly what went wrong and when, e.g.
#   restarting web server - 2 failed checks: [10:14:03 no response within 10s,
#                                             10:14:33 slow 12.4s > 10s]
# Set WEB_HEALTH_VERBOSE = True to get the old per-check chatter back for debugging.
WEB_HEALTH_VERBOSE = False
# If the health ping can never succeed for an ENVIRONMENTAL reason (a proxy env var, 127.0.0.1
# blocked, port taken by something else) the watchdog would otherwise bounce a perfectly healthy
# web server every 60s forever - and now that healthy checks are silent, the only clue would be
# the restart lines. After this many restarts with no successful check in between, the watchdog
# says so plainly and backs off to WEB_HEALTH_BACKOFF seconds; any successful check resets it.
WEB_HEALTH_MAX_INEFFECTIVE = 3
WEB_HEALTH_BACKOFF = 300.0

def _web_watchdog(interval=30.0, timeout=10.0):
    """Every `interval` seconds, ping the web server; after two consecutive bad checks, restart
    just the web-server portion. Two are required so a single transient blip doesn't bounce a
    working server.

    Logging: silent while healthy (see WEB_HEALTH_VERBOSE). The only lines this produces in
    normal operation are the ones describing a restart and the failures that caused it."""
    consecutive_bad = 0
    reasons = []                 # why each bad check in the current streak failed
    ineffective = 0              # restarts with no successful check since
    delay = interval
    while True:
        time.sleep(delay)
        elapsed = _health_ping(timeout=timeout)
        if elapsed is not None and elapsed <= timeout:
            if WEB_HEALTH_VERBOSE:
                _wlog(f'health check OK ({elapsed:.2f}s)', level='DEBUG')
            # A success clears the streak AND proves the ping works, so the back-off resets.
            if ineffective or delay != interval:
                if ineffective >= WEB_HEALTH_MAX_INEFFECTIVE:
                    _wlog('health check OK again - resuming normal 30s checks')
                ineffective = 0
                delay = interval
            consecutive_bad = 0
            reasons = []
            continue
        # --- bad check -------------------------------------------------------------------
        consecutive_bad += 1
        why = ('no response within %.0fs' % timeout) if elapsed is None \
              else ('slow %.1fs > %.0fs' % (elapsed, timeout))
        reasons.append(time.strftime('%H:%M:%S') + ' ' + why)
        if WEB_HEALTH_VERBOSE:
            _wlog(f'health check {why} [{consecutive_bad}/2]')
        if consecutive_bad < 2:
            continue
        # --- two in a row: restart, and report the whole streak ---------------------------
        _restart_httpd(reason=f'{consecutive_bad} failed checks: [' + '; '.join(reasons) + ']')
        consecutive_bad = 0
        reasons = []
        ineffective += 1
        if ineffective >= WEB_HEALTH_MAX_INEFFECTIVE:
            delay = WEB_HEALTH_BACKOFF
            if ineffective == WEB_HEALTH_MAX_INEFFECTIVE:   # say it ONCE, not on every retry
                _wlog(f'ERROR: {ineffective} restarts with no healthy check in between - the '
                      f'health ping itself may be failing (proxy env var, 127.0.0.1:{WEB_PORT} '
                      f'blocked, or the port taken by another process) rather than the web '
                      f'server being down. Backing off to {WEB_HEALTH_BACKOFF:.0f}s between '
                      f'checks until one succeeds.')

def start_web_server(db_path, get_ticket_fn, gen_ticket_fn, log_fn, settings_read_fn=None,
                     tail_fields=None, get_logs_fn=None, exec_console_fn=None, log_dir=None,
                     date_read_fn=None, scoring_ref_fn=None, player_counts_fn=None,
                     password_read_fn=None, arena_reset_fn=None, craters_defaults_fn=None,
                     server_py=None, version=None, push_lobby_news_fn=None, plane_roster_fn=None,
                     reality_read_fn=None, radar_read_fn=None, tournament_read_fn=None,
                     evs_parse_fn=None, online_players_fn=None):
    SRV['online_players'] = online_players_fn        # v968f7a: web_online_players() -> dict (/whosonline)
    SRV['reality_read'] = reality_read_fn   # v948f5: date/time/weather editor defaults
    SRV['radar_read'] = radar_read_fn       # v949f5: radar editor defaults
    SRV['tournament_read'] = tournament_read_fn   # v952f5: tournament editor defaults
    SRV['evs_parse'] = evs_parse_fn               # v958f5e: validate scripts saved to the library
    SRV['plane_roster'] = plane_roster_fn   # v932f5: () -> [(slot, name, default_camp, is_bomber, year)]
    SRV['server_py'] = server_py        # v731f5: where lobby_news.txt / lobby_welcome.txt live
    SRV['version'] = version            # v798f5: shown on the live console
    SRV['push_lobby_news'] = push_lobby_news_fn   # v870f5: (reason) -> n clients pushed
    SRV['db_path'] = db_path
    SRV['get_existing_ticket'] = get_ticket_fn
    SRV['generate_ticket'] = gen_ticket_fn
    SRV['log'] = log_fn
    SRV['settings_read'] = settings_read_fn          # arena_settings_read(blob) -> {key: feet}
    SRV['tail_fields'] = tail_fields or []           # [(key, delta, label), ...]
    SRV['get_logs'] = get_logs_fn                    # get_recent_logs(n, min_level) -> [str]
    SRV['exec_console'] = exec_console_fn            # v317: queue_console_command(line, src)
    SRV['log_dir'] = log_dir                         # v321: for the admin Logs tab
    SRV['date_read'] = date_read_fn                  # v383: extract_date_from_gamedef(blob)->(d,m,y)
    SRV['scoring_ref'] = scoring_ref_fn              # v404f5: web_scoring_reference() -> dict
    SRV['player_counts'] = player_counts_fn          # v418f5: web_player_counts() -> dict
    SRV['password_read'] = password_read_fn          # arena_password_read(blob) -> plaintext pw / ''
    SRV['arena_reset'] = arena_reset_fn              # v640f5: arena_reset(room_id, winner_camp, by)
    SRV['craters_defaults'] = craters_defaults_fn    # v686f5: () -> (minutes, max craters) server defaults

    migrate_web_db()
    _start_httpd_thread()
    SRV['log']('WEB', f'Web interface running on {"https" if WEB_TLS else "http"}://localhost:{WEB_PORT} (threaded)')
    if WEB_TLS:
        _start_http_redirector()
    # Health watchdog: pings the server and restarts the web portion if it stops answering.
    threading.Thread(target=_web_watchdog, name='web-watchdog', daemon=True).start()
    SRV['log']('WEB', 'Web health watchdog started (30s interval, 10s timeout) - '
                      'silent unless a restart is needed')
    # This call previously ran serve_forever() inline and blocked here forever. serving now happens
    # on its own thread (so the watchdog, which shares this thread, can restart it). Block here to
    # preserve the original contract that start_web_server does not return while the server lives.
    while True:
        time.sleep(3600)