import os, json, hmac, hashlib, secrets, sqlite3, random
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
import click
from flask import Flask, g, render_template, request, redirect, url_for, flash, session, jsonify, abort
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
INSTANCE_DIR.mkdir(exist_ok=True)
app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
    DATABASE=os.environ.get("DATABASE_PATH", str(INSTANCE_DIR / "basketball.sqlite3")),
    SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
    MAX_CONTENT_LENGTH=1 * 1024 * 1024,
)

def connect_db():
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def db():
    if "db" not in g:
        g.db = connect_db()
    return g.db

@app.teardown_appcontext
def close_db(_error=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()

def init_db():
    conn = connect_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
      password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','friend')),
      player_id INTEGER UNIQUE, active INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE SET NULL
    );
    CREATE TABLE IF NOT EXISTS players (
      id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE,
      active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS teams (
      id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE,
      sort_order INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS assignments (
      player_id INTEGER PRIMARY KEY, team_id INTEGER NOT NULL,
      FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE,
      FOREIGN KEY(team_id) REFERENCES teams(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS drafts (
      id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS history (
      id INTEGER PRIMARY KEY, published_at TEXT NOT NULL, published_by INTEGER,
      data TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
      FOREIGN KEY(published_by) REFERENCES users(id) ON DELETE SET NULL
    );
    CREATE TABLE IF NOT EXISTS api_keys (
      id INTEGER PRIMARY KEY, label TEXT NOT NULL, key_hash TEXT NOT NULL UNIQUE,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, last_used_at TEXT,
      revoked INTEGER NOT NULL DEFAULT 0
    );
    """)
    conn.commit()
    conn.close()

init_db()

def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]

@app.context_processor
def inject_globals():
    return {"csrf_token": csrf_token, "current_user": get_user()}

@app.before_request
def protect_posts():
    if request.method == "POST":
        sent = request.form.get("_csrf") or request.headers.get("X-CSRF-Token")
        expected = session.get("_csrf", "")
        if not sent or not expected or not hmac.compare_digest(sent, expected):
            abort(400, "Invalid or missing CSRF token.")

def get_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return db().execute("SELECT * FROM users WHERE id=? AND active=1", (uid,)).fetchone()

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not get_user():
            flash("Please sign in first.", "info")
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    return wrapped

def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        user = get_user()
        if not user:
            flash("Please sign in first.", "info")
            return redirect(url_for("login", next=request.path))
        if user["role"] != "admin":
            abort(403)
        return fn(*args, **kwargs)
    return wrapped

def teams_from_rows(rows):
    result = {}
    for row in rows:
        result.setdefault(row["team_name"], []).append({"id": row["player_id"], "name": row["player_name"]})
    return result

def current_teams():
    rows = db().execute("""SELECT t.name team_name, p.id player_id, p.name player_name
        FROM teams t LEFT JOIN assignments a ON a.team_id=t.id
        LEFT JOIN players p ON p.id=a.player_id AND p.active=1
        ORDER BY t.sort_order, t.id, p.name""").fetchall()
    result = {r["team_name"]: [] for r in rows}
    for r in rows:
        if r["player_id"] is not None:
            result[r["team_name"]].append({"id": r["player_id"], "name": r["player_name"]})
    return result

def draft_data():
    row = db().execute("SELECT data FROM drafts WHERE id=1").fetchone()
    if row:
        try: return json.loads(row["data"])
        except (ValueError, TypeError): pass
    return {name: [p["name"] for p in players] for name, players in current_teams().items()}

def save_draft(data):
    db().execute("INSERT INTO drafts(id,data,updated_at) VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
                 (json.dumps(data), now_iso()))
    db().commit()

def clean_assignments(data):
    if not isinstance(data, dict) or len(data) < 2:
        raise ValueError("Create at least two teams.")
    names = [str(x).strip() for x in data.keys()]
    if any(not n or len(n) > 40 for n in names) or len(set(n.casefold() for n in names)) != len(names):
        raise ValueError("Team names must be unique and 1–40 characters.")
    cleaned, seen = {}, set()
    active_players = {r["name"].casefold(): r["name"] for r in db().execute("SELECT name FROM players WHERE active=1")}
    for team, people in data.items():
        if not isinstance(people, list):
            raise ValueError("Each team must contain a list of player names.")
        cleaned[str(team).strip()] = []
        for person in people:
            name = str(person).strip()
            key = name.casefold()
            if key not in active_players:
                raise ValueError("Unknown or inactive player: " + name)
            if key in seen:
                raise ValueError("A player cannot be assigned more than once: " + name)
            seen.add(key)
            cleaned[str(team).strip()].append(active_players[key])
    return cleaned

def publish(data, note="", user_id=None):
    cleaned = clean_assignments(data)
    conn = db()
    conn.execute("DELETE FROM assignments")
    conn.execute("DELETE FROM teams")
    for order, (team_name, people) in enumerate(cleaned.items()):
        cur = conn.execute("INSERT INTO teams(name,sort_order) VALUES(?,?)", (team_name, order))
        team_id = cur.lastrowid
        for name in people:
            player = conn.execute("SELECT id FROM players WHERE name=? COLLATE NOCASE", (name,)).fetchone()
            conn.execute("INSERT INTO assignments(player_id,team_id) VALUES(?,?)", (player["id"], team_id))
    conn.execute("INSERT INTO history(published_at,published_by,data,note) VALUES(?,?,?,?)",
                 (now_iso(), user_id, json.dumps(cleaned), note[:200]))
    conn.execute("DELETE FROM drafts")
    conn.commit()
    return cleaned

@app.cli.command("create-admin")
def create_admin():
    """Create the first administrator account interactively."""
    if db().execute("SELECT 1 FROM users WHERE role='admin' LIMIT 1").fetchone():
        raise click.ClickException("An administrator already exists.")
    username = click.prompt("Admin username").strip()
    password = click.prompt("Admin password", hide_input=True, confirmation_prompt=True)
    if len(username) < 3 or len(username) > 40 or len(password) < 10:
        raise click.ClickException("Username must be at least 3 characters and password at least 10.")
    db().execute("INSERT INTO users(username,password_hash,role) VALUES(?,?,'admin')",
                 (username, generate_password_hash(password)))
    db().commit()
    click.echo("Administrator created. Sign in at /login.")

@app.route("/")
def index():
    teams = current_teams()
    latest = db().execute("SELECT published_at FROM history ORDER BY id DESC LIMIT 1").fetchone()
    return render_template("index.html", teams=teams, latest=latest)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username, password = request.form.get("username","").strip(), request.form.get("password","")
        user = db().execute("SELECT * FROM users WHERE username=? COLLATE NOCASE AND active=1", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            flash("Welcome back.", "success")
            target = request.args.get("next", "")
            return redirect(target if target.startswith("/") and not target.startswith("//") else url_for("index"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("index"))

@app.route("/account", methods=["GET", "POST"])
@login_required
def account():
    user = get_user()
    if request.method == "POST":
        old, new = request.form.get("current_password",""), request.form.get("new_password","")
        row = db().execute("SELECT password_hash FROM users WHERE id=?", (user["id"],)).fetchone()
        if not check_password_hash(row["password_hash"], old):
            flash("Current password is incorrect.", "error")
        elif len(new) < 10:
            flash("New password must be at least 10 characters.", "error")
        else:
            db().execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(new), user["id"]))
            db().commit()
            flash("Password updated.", "success")
            return redirect(url_for("account"))
    return render_template("account.html")

@app.route("/manage")
@admin_required
def manage():
    users = db().execute("""SELECT u.id,u.username,u.role,u.active,p.name player_name
        FROM users u LEFT JOIN players p ON p.id=u.player_id ORDER BY u.role,u.username""").fetchall()
    players = db().execute("SELECT * FROM players ORDER BY name").fetchall()
    teams = draft_data()
    return render_template("manage.html", users=users, players=players, teams=teams)

@app.route("/manage/players", methods=["POST"])
@admin_required
def manage_players():
    action = request.form.get("action")
    name = request.form.get("name","").strip()
    if action == "add":
        if not name or len(name) > 60:
            flash("Player name must be 1–60 characters.", "error")
        else:
            try:
                db().execute("INSERT INTO players(name) VALUES(?)", (name,))
                db().commit()
                flash("Player added.", "success")
            except sqlite3.IntegrityError:
                flash("That player already exists.", "error")
    elif action == "toggle":
        pid = request.form.get("player_id", type=int)
        player = db().execute("SELECT name,active FROM players WHERE id=?", (pid,)).fetchone()
        if player:
            db().execute("UPDATE players SET active=1-active WHERE id=?", (pid,))
            if player["active"]:
                db().execute("DELETE FROM assignments WHERE player_id=?", (pid,))
                saved = db().execute("SELECT data FROM drafts WHERE id=1").fetchone()
                if saved:
                    draft = json.loads(saved["data"])
                    for team in draft.values():
                        team[:] = [person for person in team if person.casefold() != player["name"].casefold()]
                    save_draft(draft)
            db().commit()
        flash("Player status updated.", "success")
    return redirect(url_for("manage"))

@app.route("/manage/users", methods=["POST"])
@admin_required
def manage_users():
    action = request.form.get("action")
    if action == "create":
        username = request.form.get("username","").strip()
        password = request.form.get("password","")
        pid = request.form.get("player_id", type=int) or None
        role = request.form.get("role", "friend")
        if len(username) < 3 or len(username) > 40 or len(password) < 10 or role not in ("friend","admin"):
            flash("Use a username of 3+ characters and password of 10+ characters.", "error")
        else:
            try:
                db().execute("INSERT INTO users(username,password_hash,role,player_id) VALUES(?,?,?,?)",
                    (username, generate_password_hash(password), role, pid))
                db().commit()
                flash("Account created.", "success")
            except sqlite3.IntegrityError:
                flash("Username already exists or player already has an account.", "error")
    elif action == "toggle":
        uid = request.form.get("user_id", type=int)
        if uid != get_user()["id"]:
            db().execute("UPDATE users SET active=1-active WHERE id=? AND role!='admin' OR id=? AND role='admin'",
                         (uid, uid))
            db().commit()
            flash("Account status updated.", "success")
    elif action == "reset":
        uid = request.form.get("user_id", type=int)
        password = request.form.get("password","")
        if len(password) >= 10:
            db().execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(password), uid))
            db().commit()
            flash("Password reset.", "success")
        else:
            flash("Temporary password must be at least 10 characters.", "error")
    return redirect(url_for("manage"))

@app.route("/manage/edit", methods=["GET", "POST"])
@admin_required
def edit():
    players = db().execute("SELECT id,name FROM players WHERE active=1 ORDER BY name").fetchall()
    names = [p["name"] for p in players]
    data = draft_data()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "save":
            team_names = request.form.getlist("team_name")
            if len(team_names) < 2 or any(not x.strip() for x in team_names) or len(set(x.strip().casefold() for x in team_names)) != len(team_names):
                flash("Create at least two teams with unique, non-empty names.", "error")
            else:
                draft = {x.strip(): [] for x in team_names}
                for name in names:
                    player_id = db().execute("SELECT id FROM players WHERE name=? COLLATE NOCASE", (name,)).fetchone()["id"]
                    team = request.form.get("player_" + str(player_id))
                    if team in draft:
                        draft[team].append(name)
                try:
                    save_draft(clean_assignments(draft))
                    flash("Draft saved. It is not public until you publish.", "success")
                    data = draft
                except ValueError as exc:
                    flash(str(exc), "error")
        elif action == "randomize":
            team_names = [x.strip() for x in request.form.getlist("team_name") if x.strip()]
            if len(team_names) < 2 or len(set(x.casefold() for x in team_names)) != len(team_names):
                flash("Create at least two uniquely named teams before randomizing.", "error")
            else:
                shuffled = names[:]
                random.SystemRandom().shuffle(shuffled)
                data = {name: [] for name in team_names}
                for i, person in enumerate(shuffled):
                    data[team_names[i % len(team_names)]].append(person)
                save_draft(data)
                flash("New randomized draft created. You can reroll or adjust it.", "success")
        elif action == "publish":
            try:
                team_names = request.form.getlist("team_name")
                if len(team_names) < 2 or any(not x.strip() for x in team_names) or len(set(x.strip().casefold() for x in team_names)) != len(team_names):
                    raise ValueError("Create at least two teams with unique, non-empty names.")
                draft = {x.strip(): [] for x in team_names}
                for name in names:
                    player_id = db().execute("SELECT id FROM players WHERE name=? COLLATE NOCASE", (name,)).fetchone()["id"]
                    team = request.form.get("player_" + str(player_id))
                    if team in draft:
                        draft[team].append(name)
                draft = clean_assignments(draft)
                note = request.form.get("note","").strip()
                publish(draft, note, get_user()["id"])
                flash("Teams published. A history snapshot was created.", "success")
                return redirect(url_for("manage"))
            except ValueError as exc:
                flash(str(exc), "error")
        return redirect(url_for("edit"))
    if not data:
        data = {"Team 1": [], "Team 2": []}
    assigned_names = {person.casefold() for group in data.values() for person in group}
    return render_template("edit.html", data=data, players=players, assigned_names=assigned_names)

@app.route("/manage/api-key", methods=["GET", "POST"])
@admin_required
def api_keys():
    shown_key = None
    if request.method == "POST":
        label = request.form.get("label","").strip()[:60] or "API key"
        raw = "bt_" + secrets.token_urlsafe(32)
        digest = hashlib.sha256(raw.encode()).hexdigest()
        db().execute("INSERT INTO api_keys(label,key_hash) VALUES(?,?)", (label,digest))
        db().commit()
        shown_key = raw
        flash("Copy this key now. It will not be shown again.", "success")
    keys = db().execute("SELECT id,label,created_at,last_used_at,revoked FROM api_keys ORDER BY id DESC").fetchall()
    return render_template("api_keys.html", keys=keys, shown_key=shown_key)

@app.route("/manage/api-key/<int:key_id>/revoke", methods=["POST"])
@admin_required
def revoke_key(key_id):
    db().execute("UPDATE api_keys SET revoked=1 WHERE id=?", (key_id,))
    db().commit()
    flash("API key revoked.", "success")
    return redirect(url_for("api_keys"))

@app.route("/history")
def history():
    entries = db().execute("""SELECT h.id,h.published_at,h.note,u.username
        FROM history h LEFT JOIN users u ON u.id=h.published_by ORDER BY h.id DESC""").fetchall()
    return render_template("history.html", entries=entries)

@app.route("/manage/restore/<int:history_id>", methods=["POST"])
@admin_required
def restore_history(history_id):
    entry = db().execute("SELECT data FROM history WHERE id=?", (history_id,)).fetchone()
    if not entry:
        abort(404)
    try:
        restored = clean_assignments(json.loads(entry["data"]))
        save_draft(restored)
        flash("Historical lineup loaded as a draft. Review it, then publish when ready.", "success")
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        flash("Could not restore this snapshot: " + str(exc), "error")
    return redirect(url_for("edit"))

@app.route("/history/<int:history_id>")
def history_detail(history_id):
    entry = db().execute("SELECT * FROM history WHERE id=?", (history_id,)).fetchone()
    if not entry: abort(404)
    return render_template("history_detail.html", entry=entry, teams=json.loads(entry["data"]))

def api_error(message, status):
    return jsonify({"error": message}), status

def api_key_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        raw = request.headers.get("X-API-Key", "")
        if not raw:
            return api_error("API key required.", 401)
        digest = hashlib.sha256(raw.encode()).hexdigest()
        row = db().execute("SELECT id FROM api_keys WHERE key_hash=? AND revoked=0", (digest,)).fetchone()
        if not row:
            return api_error("Invalid or revoked API key.", 401)
        db().execute("UPDATE api_keys SET last_used_at=? WHERE id=?", (now_iso(), row["id"]))
        db().commit()
        return fn(*args, **kwargs)
    return wrapped

@app.route("/api/v1/teams", methods=["GET", "PUT"])
def api_teams():
    if request.method == "GET":
        return jsonify({"teams": {k: [p["name"] for p in v] for k,v in current_teams().items()},
                        "published_at": (db().execute("SELECT published_at FROM history ORDER BY id DESC LIMIT 1").fetchone() or {"published_at": None})["published_at"]})
    @api_key_required
    def update():
        body = request.get_json(silent=True) or {}
        try:
            teams = publish(body.get("teams"), body.get("note","API update"), None)
            return jsonify({"ok": True, "teams": teams}), 200
        except (ValueError, TypeError) as exc:
            return api_error(str(exc), 400)
    return update()

@app.route("/api/v1/teams/<history_ref>")
def api_history(history_ref):
    if len(history_ref) == 8 and history_ref.isdigit():
        try:
            day = datetime.strptime(history_ref, "%Y%m%d").strftime("%Y-%m-%d")
        except ValueError:
            return api_error("Date must use YYYYMMDD format.", 400)
        entry = db().execute("SELECT id,published_at,data,note FROM history WHERE substr(published_at,1,10)=? ORDER BY id DESC LIMIT 1", (day,)).fetchone()
    else:
        try:
            history_id = int(history_ref)
        except ValueError:
            return api_error("Use a history ID or YYYYMMDD date.", 400)
        entry = db().execute("SELECT id,published_at,data,note FROM history WHERE id=?", (history_id,)).fetchone()
    if not entry:
        return api_error("Historical lineup not found.", 404)
    return jsonify({"id": entry["id"], "published_at": entry["published_at"], "note": entry["note"], "teams": json.loads(entry["data"])})

@app.route("/api/v1/players")
def api_players():
    rows = db().execute("SELECT id,name FROM players WHERE active=1 ORDER BY name").fetchall()
    return jsonify({"players": [{"id": r["id"], "name": r["name"]} for r in rows]})

@app.errorhandler(403)
def forbidden(_error):
    return render_template("error.html", code=403, message="You do not have permission to view this page."), 403

@app.errorhandler(404)
def not_found(_error):
    return render_template("error.html", code=404, message="That page could not be found."), 404

@app.errorhandler(400)
def bad_request(error):
    return render_template("error.html", code=400, message=getattr(error, "description", "Bad request.")), 400

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
