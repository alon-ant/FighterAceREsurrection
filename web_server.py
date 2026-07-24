# =============================================================================
# FA Server - web interface (separate module, launched as a daemon thread from the
# main server file). Login / launcher / ladder / admin panel / arena settings / live console.
#
# CHANGELOG
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
import subprocess
import sqlite3
import hashlib
import secrets
import json
import threading
import time
import socket
import urllib.request
from http import cookies
from html import escape as hesc

WEB_PORT = 80
DEFAULT_CLIENT_PATH = r"C:\games\FA\FA.exe"
WEB_SESSIONS = {}

# Bridge to hold references injected from the main game server
SRV = {
    'db_path': None,
    'get_existing_ticket': None,
    'generate_ticket': None,
    'exec_console': None,
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
                <h1>Live Server Console</h1>
                <div class="card" style="padding:12px;">
                  <label>Min level:
                    <select id="lvl" onchange="reload()">
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
                    .then(function(j){DATA=j.lines;render();}).catch(function(){});
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
});
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
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        html = f"""<!DOCTYPE html><html>
        <head>
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
            # We still query account_name so we can highlight the active user, but we won't print it
            stats = conn.execute("SELECT pilot_name, account_name, COALESCE(score,0), COALESCE(kills,0), COALESCE(deaths,0) FROM pilots").fetchall()
            conn.close()
            
            ladder_data = []
            for p_name, a_name, score, k, d in stats:
                kd = round(k / d, 2) if d > 0 else float(k)
                ladder_data.append((p_name, a_name, score, k, d, kd))
                
            # Sort by score descending, then K/D descending
            ladder_data.sort(key=lambda x: (x[2], x[5]), reverse=True)
            
            table_rows = ""
            for rank, (p_name, a_name, score, k, d, kd) in enumerate(ladder_data, 1):
                # Highlight if this pilot belongs to the currently logged in account
                row_style = "background-color: #e8f4f8; font-weight: bold;" if a_name == user else ""
                table_rows += f"""<tr style='{row_style}'>
                    <td>{rank}</td>
                    <td><strong>{p_name}</strong></td>
                    <td>{score}</td>
                    <td>{k}</td>
                    <td>{d}</td>
                    <td>{kd}</td>
                </tr>"""

            content = f"""
                <div class="nav"><a href="/">&larr; Back to Dashboard</a></div>
                <h1>Top Aces Ladder</h1>
                
                <div class="card" style="padding: 0;">
                    <div style="padding: 15px;">
                        <input type="text" id="searchInput" placeholder="Search by pilot name..." style="width: 100%; padding: 10px; margin: 0; box-sizing: border-box; border: 1px solid #ccc; border-radius: 4px;">
                    </div>
                    <table id="ladderTable">
                        <thead>
                            <tr>
                                <th onclick="sortTable(0)">Rank &#x21D5;</th>
                                <th onclick="sortTable(1)">Pilot Name &#x21D5;</th>
                                <th onclick="sortTable(2)">Score &#x21D5;</th>
                                <th onclick="sortTable(3)">Kills &#x21D5;</th>
                                <th onclick="sortTable(4)">Deaths &#x21D5;</th>
                                <th onclick="sortTable(5)">K/D Ratio &#x21D5;</th>
                            </tr>
                        </thead>
                        <tbody>
                            {table_rows}
                        </tbody>
                    </table>
                </div>

                <script>
                    document.getElementById('searchInput').addEventListener('keyup', function() {{
                        let filter = this.value.toLowerCase();
                        let rows = document.querySelectorAll('#ladderTable tbody tr');
                        rows.forEach(row => {{
                            let name = row.cells[1].textContent.toLowerCase();
                            row.style.display = name.includes(filter) ? '' : 'none';
                        }});
                    }});

                    function sortTable(n) {{
                        var table, rows, switching, i, x, y, shouldSwitch, dir, switchcount = 0;
                        table = document.getElementById("ladderTable");
                        switching = true;
                        dir = "asc"; 
                        while (switching) {{
                            switching = false;
                            rows = table.rows;
                            for (i = 1; i < (rows.length - 1); i++) {{
                                shouldSwitch = false;
                                x = rows[i].getElementsByTagName("TD")[n];
                                y = rows[i + 1].getElementsByTagName("TD")[n];
                                
                                let valX = isNaN(parseFloat(x.innerHTML)) ? x.innerHTML.toLowerCase() : parseFloat(x.innerHTML);
                                let valY = isNaN(parseFloat(y.innerHTML)) ? y.innerHTML.toLowerCase() : parseFloat(y.innerHTML);

                                if (dir == "asc") {{
                                    if (valX > valY) {{ shouldSwitch = true; break; }}
                                }} else if (dir == "desc") {{
                                    if (valX < valY) {{ shouldSwitch = true; break; }}
                                }}
                            }}
                            if (shouldSwitch) {{
                                rows[i].parentNode.insertBefore(rows[i + 1], rows[i]);
                                switching = true;
                                switchcount ++; 
                            }} else {{
                                if (switchcount == 0 && dir == "asc") {{
                                    dir = "desc";
                                    switching = true;
                                }}
                            }}
                        }}
                    }}
                </script>
            """
            self.send_html(content)

        elif self.path == '/admin':
            if not is_user_admin(user):
                self.send_html("<h2>Access Denied</h2><p>Administrator privileges required.</p><a href='/'>&larr; Back</a>")
                return
                
            conn = sqlite3.connect(SRV['db_path'])
            users = conn.execute("SELECT account_name, is_admin FROM accounts ORDER BY account_name").fetchall()

            # Pilot stats management. Pilots live in the `pilots` table. v240: the msg-25 stat block
            # is fully mapped, so EVERY row of the in-game HQ Scores screen has its own column and is
            # editable - the editor doubles as an end-to-end test harness for the block.
            pilot_html = ""
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

            # Arena (room) management. Rooms live in the `rooms` table; expose name,
            # title (the arena-list section header / category) and status for editing.
            arena_html = ""
            try:
                rcols = [r[1] for r in conn.execute("PRAGMA table_info(rooms)").fetchall()]
                cat_sel = "COALESCE(category,'Custom Arenas')" if 'category' in rcols else "'Custom Arenas'"
                arena_rows = conn.execute(
                    "SELECT room_id, COALESCE(room_name,''), COALESCE(creator_pilot,''), "
                    "COALESCE(status,'open'), COALESCE(terrain,1), " + cat_sel + ", "
                    "(SELECT COUNT(*) FROM room_players rp WHERE rp.room_id=rooms.room_id) "
                    "FROM rooms ORDER BY created_at DESC").fetchall()
                if not arena_rows:
                    arena_html = "<tr><td>No arenas in the database.</td><td></td></tr>"
                for rid, rname, creator, status, terrain, category, pcount in arena_rows:
                    sel_open   = 'selected' if status == 'open' else ''
                    sel_closed = 'selected' if status != 'open' else ''
                    row_bg = '' if status == 'open' else 'background:#f3f3f3;'
                    arena_html += f"""
                    <tr style="{row_bg}">
                        <td>
                            <form method="POST" action="/admin/edit_arena" style="margin:0;">
                                <input type="hidden" name="room_id" value="{rid}">
                                <div style="display:flex; gap:10px; flex-wrap:wrap; align-items:flex-end;">
                                    <label style="font-size:0.8em; color:#666;">Name<br>
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

            user_html = ""
            acct_options = ''.join(
                '<option value="' + hesc(str(u), quote=True) + '">' + hesc(str(u)) + '</option>'
                for u, _a in users)
            for u_name, is_adm in users:
                role = "&#128081; Admin" if is_adm else "Player"
                u_esc = hesc(str(u_name), quote=True)
                user_html += f"""
                <tr>
                    <td><strong>{u_esc}</strong> <br><small style="color:#666;">{role}</small></td>
                    <td style="text-align:right;">
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

            conn.close()

            content = f"""
                {ADMIN_TABS_ASSETS}
                <div class="nav"><a href="/">&larr; Back to Dashboard</a> |
                    <a href="/admin/logs" style="color:#17a2b8;">Live Console</a> |
                    Logged in as <strong>{hesc(str(user))}</strong></div>
                <h1>Server Administration</h1>

                <div class="tabbar">
                    <button class="on" data-btngroup="main" data-target="p-users"
                            onclick="faShow('main','p-users')">User Management</button>
                    <button data-btngroup="main" data-target="p-arenas"
                            onclick="faShow('main','p-arenas')">Arenas</button>
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
                        <div style="margin-top:15px;">
                            <button type="submit" class="btn-green" style="width:auto; padding:10px 20px;">Save Stats</button>
                            &nbsp; <a href="/admin" style="color:#666;">Cancel</a></div>
                    </form>
                </div>
            """
            self.send_html(content)

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
            sel_open = 'selected' if status == 'open' else ''
            sel_closed = 'selected' if status != 'open' else ''
            content = f"""
                <div class="nav"><a href="/admin">&larr; Back to Admin</a></div>
                <h1>Edit Arena &mdash; {hesc(str(rname))}</h1>
                <div class="card">
                <form method="POST" action="/admin/arena_settings">
                    <input type="hidden" name="room_id" value="{rid}">
                    <h3 style="margin-top:0;">General</h3>
                    <label style="display:block; margin:10px 0;">Name<br>
                        <input type="text" name="room_name" value="{hesc(str(rname), quote=True)}" style="width:280px; padding:6px;"></label>
                    <label style="display:block; margin:10px 0;">Title (arena-list section header)<br>
                        <input type="text" name="category" value="{hesc(str(category), quote=True)}" style="width:280px; padding:6px;"></label>
                    <label style="display:block; margin:10px 0;">Status<br>
                        <select name="status" style="padding:7px;"><option value="open" {sel_open}>open</option><option value="closed" {sel_closed}>closed</option></select></label>
                    <h3>Arena settings</h3>
                    <p style="color:#888; font-size:0.85em; max-width:560px;">All values in <strong>feet</strong>. Leave a field blank to keep the value the arena was created with. Changes are written into the arena's GAME_DEF and take effect the next time the arena is entered (they are served fresh on entry).</p>
                    {fields_html}
                    <h3>Enemy defences (EvP)</h3>
                    <p style="color:#888; font-size:0.85em; max-width:560px;">Strength of the terrain's automatic anti-aircraft defences that fire at players (0 = off, 6 = strongest). Applied the next time the arena is entered.</p>
                    {evp_html}
                    <div style="margin-top:18px;"><button type="submit" class="btn-green" style="width:auto; padding:10px 26px;">Save</button>
                        &nbsp; <a href="/admin" style="color:#666;">Cancel</a></div>
                </form>
                </div>
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
            rows = []
            if 'account_name' in rcols:
                rows = conn.execute(
                    "SELECT room_id, COALESCE(room_name,''), COALESCE(status,'open'), "
                    "COALESCE(terrain,1), " + cat_sel + " FROM rooms WHERE account_name=? "
                    "ORDER BY created_at DESC", (user,)).fetchall()
            conn.close()
            if rows:
                items = ""
                for rid, rname, status, terrain, category in rows:
                    items += (
                        '<div class="card" style="margin:10px 0;">'
                        '<div style="display:flex; justify-content:space-between; align-items:center;">'
                        '<div><strong>' + hesc(str(rname) or 'Unnamed') + '</strong>'
                        '<br><small style="color:#888;">' + hesc(str(category))
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
            if not is_user_admin(user):
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
            body = json.dumps({'lines': lines}).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length).decode('utf-8')
        qs = urllib.parse.parse_qs(post_data)
        
        user = self.get_current_user()

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
                if 'category' in rcols:
                    conn.execute("UPDATE rooms SET room_name=?, category=?, status=? WHERE room_id=?",
                                 (room_name, category, status, rid))
                else:
                    conn.execute("UPDATE rooms SET room_name=?, status=? WHERE room_id=?",
                                 (room_name, status, rid))
                conn.commit(); conn.close()
                SRV['log']('WEB', f"Admin {user} edited arena {rid}: name={room_name!r} title={category!r} status={status}")
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
            if rid:
                conn = sqlite3.connect(SRV['db_path'])
                rcols = [r[1] for r in conn.execute("PRAGMA table_info(rooms)").fetchall()]
                if 'settings_json' in rcols:
                    conn.execute("UPDATE rooms SET room_name=?, category=?, status=?, settings_json=? WHERE room_id=?",
                                 (room_name, category, status, json.dumps(settings), rid))
                else:
                    conn.execute("UPDATE rooms SET room_name=?, category=?, status=? WHERE room_id=?",
                                 (room_name, category, status, rid))
                conn.commit(); conn.close()
                SRV['log']('WEB', f"Admin {user} edited arena {rid}: name={room_name!r} title={category!r} "
                                  f"status={status} settings={settings}")
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
    httpd = _ThreadedWebServer(server_address, WebInterfaceHandler)
    # Cap how long a single request may tie up its worker. request_queue_size raises the accept
    # backlog so bursts don't get refused while workers spin up.
    httpd.timeout = 30
    httpd.request_queue_size = 64
    return httpd

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
            SRV['log']('WEB', f'web server restarted on http://localhost:{WEB_PORT}')
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
    url = f'http://127.0.0.1:{WEB_PORT}/login'
    start = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
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

def _web_watchdog(interval=30.0, timeout=10.0):
    """Every `interval` seconds, ping the web server. If it does not answer within `timeout`
    seconds (or errors), restart just the web-server portion. Two consecutive bad checks are
    required before a restart, so a single transient blip doesn't cause a needless bounce.

    Observability: a healthy check used to log nothing, which made it impossible to tell a
    silent-because-healthy watchdog from a dead one. Now it does an immediate startup ping
    (logged at INFO so you get proof-of-life at boot), then logs each healthy check as a DEBUG
    heartbeat (goes to the file log / DEBUG console, stays off the INFO console) and a periodic
    INFO summary every ~10 checks so there's a visible pulse without spam."""
    consecutive_bad = 0
    checks_ok = 0
    # Immediate startup ping so we know the watchdog can actually reach the server right now,
    # rather than waiting a full interval and staying silent.
    first = _health_ping(timeout=timeout)
    if first is None:
        _wlog(f'startup health ping FAILED (no response within {timeout:.0f}s) - '
              f'will keep checking every {interval:.0f}s')
    else:
        _wlog(f'startup health ping OK ({first:.2f}s) - watchdog is live, '
              f'checking every {interval:.0f}s')
    while True:
        time.sleep(interval)
        elapsed = _health_ping(timeout=timeout)
        if elapsed is None:
            consecutive_bad += 1
            _wlog(f'health check FAILED (no response within {timeout:.0f}s) '
                  f'[{consecutive_bad}/2]')
        elif elapsed > timeout:
            consecutive_bad += 1
            _wlog(f'health check SLOW ({elapsed:.1f}s > {timeout:.0f}s) '
                  f'[{consecutive_bad}/2]')
        else:
            if consecutive_bad:
                _wlog(f'health check OK ({elapsed:.2f}s) - recovered')
            consecutive_bad = 0
            checks_ok += 1
            # DEBUG heartbeat every check (file/DEBUG only), plus an INFO pulse every 10 checks
            # (~5 min at 30s) so a healthy watchdog is provably alive on the normal console too.
            if checks_ok % 10 == 0:
                _wlog(f'health check OK ({elapsed:.2f}s) - {checks_ok} checks passed')
            else:
                _wlog(f'health check OK ({elapsed:.2f}s)', level='DEBUG')
            continue
        if consecutive_bad >= 2:
            _restart_httpd(reason=f'unresponsive ({consecutive_bad} failed checks)')
            consecutive_bad = 0

def start_web_server(db_path, get_ticket_fn, gen_ticket_fn, log_fn, settings_read_fn=None,
                     tail_fields=None, get_logs_fn=None, exec_console_fn=None):
    SRV['db_path'] = db_path
    SRV['get_existing_ticket'] = get_ticket_fn
    SRV['generate_ticket'] = gen_ticket_fn
    SRV['log'] = log_fn
    SRV['settings_read'] = settings_read_fn          # arena_settings_read(blob) -> {key: feet}
    SRV['tail_fields'] = tail_fields or []           # [(key, delta, label), ...]
    SRV['get_logs'] = get_logs_fn                    # get_recent_logs(n, min_level) -> [str]
    SRV['exec_console'] = exec_console_fn            # v317: queue_console_command(line, src)

    migrate_web_db()
    _start_httpd_thread()
    SRV['log']('WEB', f'Web interface running on http://localhost:{WEB_PORT} (threaded)')
    # Health watchdog: pings the server and restarts the web portion if it stops answering.
    threading.Thread(target=_web_watchdog, name='web-watchdog', daemon=True).start()
    SRV['log']('WEB', 'Web health watchdog started (30s interval, 10s timeout)')
    # This call previously ran serve_forever() inline and blocked here forever. serving now happens
    # on its own thread (so the watchdog, which shares this thread, can restart it). Block here to
    # preserve the original contract that start_web_server does not return while the server lives.
    while True:
        time.sleep(3600)