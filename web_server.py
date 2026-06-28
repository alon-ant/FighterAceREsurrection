import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
import subprocess
import sqlite3
import hashlib
import secrets
from http import cookies

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
                    {admin_link} 
                    <a href="/logout" style="color:#dc3545;">Logout</a>
                </div>
                <h1>Welcome Pilot</h1>
                
                <div class="card">
                    <h2 style="margin-top:0;">1. Play Locally (Host)</h2>
                    <form method="POST" action="/update_path" style="margin-bottom: 15px;">
                        <label>Your Game Client Path:</label>
                        <input type="text" name="client_path" value="{display_path}" required>
                        <button type="submit" style="background: #6c757d;">Save Path Settings</button>
                    </form>
                    <form method="POST" action="/launch">
                        <button type="submit" class="btn-green">Deploy Ticket & Launch Game</button>
                    </form>
                </div>

                <div class="card">
                    <h2 style="margin-top:0;">2. Play Remotely</h2>
                    <p style="font-size: 0.9em; color: #555;">Download your ticket for another PC.</p>
                    <form method="GET" action="/download">
                        <button type="submit">Download ticket.vr1</button>
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
            
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            arena_table = 'arenas' if 'arenas' in tables else ('rooms' if 'rooms' in tables else None)
            
            arena_html = ""
            if arena_table:
                try:
                    arena_rows = conn.execute(f"SELECT rowid, * FROM {arena_table}").fetchall()
                    if not arena_rows:
                        arena_html = "<tr><td colspan='2'>No active arenas found.</td></tr>"
                    for row in arena_rows:
                        a_id = row[0]
                        a_desc = str(row[1]) if len(row) > 1 else f"Arena DB_ID {a_id}"
                        arena_html += f"""
                        <tr>
                            <td><strong>{a_desc}</strong> <br><small style="color:#666;">(DB Row: {a_id})</small></td>
                            <td style="text-align:right;">
                                <form method="POST" action="/admin/delete_arena" onsubmit="return confirm('Delete this arena?');">
                                    <input type="hidden" name="table" value="{arena_table}">
                                    <input type="hidden" name="rowid" value="{a_id}">
                                    <button type="submit" class="btn-red" style="width:auto; padding:8px 12px; margin:0;">Delete Arena</button>
                                </form>
                            </td>
                        </tr>"""
                except Exception as e:
                    arena_html = f"<tr><td colspan='2'>Error loading arenas: {e}</td></tr>"
            else:
                arena_html = "<tr><td colspan='2'>No arenas/rooms table found in database.</td></tr>"

            user_html = ""
            for u_name, is_adm in users:
                role = "👑 Admin" if is_adm else "Player"
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
                <div class="nav"><a href="/">&larr; Back to Dashboard</a> | Logged in as <strong>{user}</strong></div>
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
                ticket_bytes, _ = SRV['get_existing_ticket'](user)
                self.send_response(200)
                self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Content-Disposition', 'attachment; filename="ticket.vr1"')
                self.end_headers()
                self.wfile.write(ticket_bytes)
            except Exception as e:
                self.send_error(500, f"Error generating ticket: {str(e)}")
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
                
    def log_message(self, format, *args):
        pass

def start_web_server(db_path, get_ticket_fn, gen_ticket_fn, log_fn):
    SRV['db_path'] = db_path
    SRV['get_existing_ticket'] = get_ticket_fn
    SRV['generate_ticket'] = gen_ticket_fn
    SRV['log'] = log_fn

    migrate_web_db()
    server_address = ('', WEB_PORT)
    httpd = HTTPServer(server_address, WebInterfaceHandler)
    SRV['log']('WEB', f'Web interface running on http://localhost:{WEB_PORT}')
    httpd.serve_forever()