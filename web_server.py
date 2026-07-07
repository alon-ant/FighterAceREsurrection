import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
import subprocess
import sqlite3
import hashlib
import secrets
import json
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
                reload(); toggle();
                </script>
"""

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

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
            for u_name, is_adm in users:
                role = "&#128081; Admin" if is_adm else "Player"
                user_html += f"""
                <tr>
                    <td><strong>{u_name}</strong> <br><small style="color:#666;">{role}</small></td>
                    <td style="text-align:right;">
                        <form method="POST" action="/admin/reset_password" style="display:inline-block; margin-right: 10px;">
                            <input type="hidden" name="account_name" value="{u_name}">
                            <input type="password" name="new_password" placeholder="New Password" required style="width:130px; padding:8px; margin:0; display:inline-block;">
                            <button type="submit" class="btn-yellow" style="width:auto; padding:8px 12px; margin:0; display:inline-block;">Reset</button>
                        </form>
                        <form method="POST" action="/admin/delete_user" style="display:inline-block;" onsubmit="return confirm('Delete user {u_name}? This permanently deletes their ticket and cannot be undone.');">
                            <input type="hidden" name="account_name" value="{u_name}">
                            <button type="submit" class="btn-red" style="width:auto; padding:8px 12px; margin:0; display:inline-block;">Delete</button>
                        </form>
                    </td>
                </tr>"""

            conn.close()

            content = f"""
                <div class="nav"><a href="/">&larr; Back to Dashboard</a> |
                    <a href="/admin/logs" style="color:#17a2b8;">Live Console</a> |
                    Logged in as <strong>{user}</strong></div>
                <h1>Server Administration</h1>
                
                <div class="card">
                    <h2 style="margin-top:0;">User Management</h2>
                    <table>{user_html}</table>
                </div>

                <div class="card">
                    <h2 style="margin-top:0;">Arena Management</h2>
                    <table>{arena_html}</table>
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

def start_web_server(db_path, get_ticket_fn, gen_ticket_fn, log_fn, settings_read_fn=None,
                     tail_fields=None, get_logs_fn=None):
    SRV['db_path'] = db_path
    SRV['get_existing_ticket'] = get_ticket_fn
    SRV['generate_ticket'] = gen_ticket_fn
    SRV['log'] = log_fn
    SRV['settings_read'] = settings_read_fn          # arena_settings_read(blob) -> {key: feet}
    SRV['tail_fields'] = tail_fields or []           # [(key, delta, label), ...]
    SRV['get_logs'] = get_logs_fn                    # get_recent_logs(n, min_level) -> [str]

    migrate_web_db()
    server_address = ('', WEB_PORT)
    httpd = HTTPServer(server_address, WebInterfaceHandler)
    SRV['log']('WEB', f'Web interface running on http://localhost:{WEB_PORT}')
    httpd.serve_forever()