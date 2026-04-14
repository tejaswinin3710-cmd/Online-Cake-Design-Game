from flask import Flask, render_template, request, redirect, session, url_for, jsonify # pyright: ignore[reportMissingImports]
import sqlite3
import random
import json

app = Flask(__name__)
app.secret_key = "bakery_secret_2024"

# ---------- GAME DATA ----------
GAME_DATA = {
    "shapes":      ["round", "square", "heart"],
    "layers":      ["1", "2", "3"],
    "fillings":    ["vanilla", "chocolate", "strawberry"],
    "icing_sides": ["white", "pink", "blue"],
    "icing_tops":  ["plain", "swirl", "stripe"],
    "decorations": ["sprinkles", "berries", "candles"],
    "centerpieces":["star", "rose", "smiley"],
}

CUSTOMERS = [
    {"name": "Alice 🌸", "emoji": "👩‍🦰", "bubble": "Make it pretty!"},
    {"name": "Bob 🤵",   "emoji": "🧔",   "bubble": "For my wedding!"},
    {"name": "Clara 👶", "emoji": "👱‍♀️", "bubble": "It's for my kid!"},
    {"name": "David 🥳", "emoji": "🧑",   "bubble": "Birthday time!"},
    {"name": "Emma 💕",  "emoji": "👩",   "bubble": "Make it special!"},
    {"name": "Chef Leo 👨‍🍳", "emoji": "👨‍🍳", "bubble": "Impress me!"},
]

# ---------- DATABASE ----------
def init_db():
    conn = sqlite3.connect("bakery_users.db")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            name     TEXT,
            username TEXT PRIMARY KEY,
            phone    TEXT,
            email    TEXT,
            password TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scores (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            score    INTEGER,
            level    INTEGER,
            played_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.close()

init_db()

# ---------- HELPERS ----------
def get_db():
    conn = sqlite3.connect("bakery_users.db")
    conn.row_factory = sqlite3.Row
    return conn

def generate_order():
    return {
        "shape":       random.choice(GAME_DATA["shapes"]),
        "layers":      random.choice(GAME_DATA["layers"]),
        "filling":     random.choice(GAME_DATA["fillings"]),
        "icingSide":   random.choice(GAME_DATA["icing_sides"]),
        "icingTop":    random.choice(GAME_DATA["icing_tops"]),
        "decoration":  random.choice(GAME_DATA["decorations"]),
        "centerpiece": random.choice(GAME_DATA["centerpieces"]),
    }

# ---------- ROUTES ----------

@app.route("/")
def main():
    return redirect("/login")


#----------ADMIN----------
@app.route('/admin')
def admin():
    if 'admin' in session:
        return render_template('admin.html')
    return redirect('/')

# ---------- HOME / GAME ----------
@app.route("/home")
def home():
    if "user" not in session:
        return redirect("/login")
    return render_template(
        "index.html",
        username=session.get("user"),
        player_name=session.get("name"),
        score=session.get("score", 0),
        level=session.get("level", 1),
    )


# ---------- SIGNUP ----------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name     = request.form["name"]
        username = request.form["username"]
        phone    = request.form["phone"]
        email    = request.form["email"]
        password = request.form["password"]

        try:
            conn = get_db()
            conn.execute(
                "INSERT INTO users VALUES (?, ?, ?, ?, ?)",
                (name, username, phone, email, password)
            )
            conn.commit()
            conn.close()

            session["user"] = username
            session["name"] = name
            session["score"] = 0
            session["level"] = 1
            return redirect(url_for("home"))

        except sqlite3.IntegrityError:
            return render_template("signup.html", error="Username already exists!")
        except Exception as e:
            return render_template("signup.html", error=str(e))

    return render_template("signup.html")


# ---------- LOGIN ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db()
        cursor = conn.execute(
            "SELECT * FROM users WHERE username=? AND password=?",
            (username, password)
        )
        user = cursor.fetchone()
        conn.close()

        if user:
            session["user"]  = username
            session["name"]  = user["name"]
            session["score"] = 0
            session["level"] = 1
            return redirect(url_for("home"))

        return render_template("login.html", error="Invalid username or password!")

    return render_template("login.html")


# ---------- API: NEW ORDER ----------
@app.route("/api/new_order", methods=["GET"])
def new_order():
    """Returns a freshly generated cake order + random customer as JSON."""
    if "user" not in session:
        return jsonify({"error": "Not logged in"}), 401

    order    = generate_order()
    customer = random.choice(CUSTOMERS)

    # Store current order in session so /api/submit can validate
    session["current_order"] = order

    return jsonify({
        "order":    order,
        "customer": customer,
    })


# ---------- API: SUBMIT CAKE ----------
@app.route("/api/submit", methods=["POST"])
def submit_cake():
    """Receives player's cake choices, scores them, updates session."""
    if "user" not in session:
        return jsonify({"error": "Not logged in"}), 401

    data    = request.get_json()
    answers = data.get("answers", {})
    correct = session.get("current_order", {})
    time_left = int(data.get("timeLeft", 0))
    patience  = float(data.get("patience", 100))

    field_labels = ["shape", "layers", "filling", "icingSide", "icingTop", "decoration", "centerpiece"]
    pts = 0
    breakdown = []

    for field in field_labels:
        user_val    = answers.get(field, "")
        correct_val = correct.get(field, "")
        ok = (user_val == correct_val)
        p  = 14 if ok else 0
        pts += p
        breakdown.append({
            "field":   field,
            "ok":      ok,
            "user":    user_val,
            "correct": correct_val,
            "pts":     p,
        })

    # Bonuses
    bonus = 0
    if pts == 98:
        bonus = 20
    elif pts >= 70:
        bonus = 10

    time_pts    = int((time_left / 60) * 20)
    patience_pts = int((patience / 100) * 15)
    grand_total  = pts + bonus + time_pts + patience_pts

    # Update session score & level
    session["score"] = session.get("score", 0) + grand_total
    if session["score"] >= session["level"] * 200:
        session["level"] = session.get("level", 1) + 1

    # Persist best score to DB
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO scores (username, score, level) VALUES (?, ?, ?)",
            (session["user"], session["score"], session["level"])
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

    return jsonify({
        "breakdown":   breakdown,
        "bonus":       bonus,
        "timePts":     time_pts,
        "patiencePts": patience_pts,
        "grandTotal":  grand_total,
        "totalScore":  session["score"],
        "level":       session["level"],
        "success":     pts >= 56,
    })


# ---------- API: CHECK STEP ----------
@app.route("/api/check_step", methods=["POST"])
def check_step():
    """Validates a single step against the current order."""
    if "user" not in session:
        return jsonify({"error": "Not logged in"}), 401

    data    = request.get_json()
    field   = data.get("field", "")
    value   = data.get("value", "")
    correct = session.get("current_order", {})

    field_map = {
        "shape":       correct.get("shape"),
        "layers":      correct.get("layers"),
        "filling":     correct.get("filling"),
        "icing-side":  correct.get("icingSide"),
        "icing-top":   correct.get("icingTop"),
        "decoration":  correct.get("decoration"),
        "centerpiece": correct.get("centerpiece"),
    }

    correct_val = field_map.get(field, "")
    ok = (value == correct_val)

    if not ok:
        session["score"] = max(0, session.get("score", 0) - 5)

    return jsonify({
        "ok":      ok,
        "correct": correct_val,
        "score":   session.get("score", 0),
    })


# ---------- LEADERBOARD ----------
@app.route("/leaderboard")
def leaderboard():
    if "user" not in session:
        return redirect("/login")

    conn = get_db()
    rows = conn.execute("""
        SELECT username, MAX(score) as best_score, MAX(level) as best_level
        FROM scores
        GROUP BY username
        ORDER BY best_score DESC
        LIMIT 10
    """).fetchall()
    conn.close()

    return render_template(
        "leaderboard.html",
        rows=rows,
        current_user=session["user"],
    )


# ---------- LOGOUT ----------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ---------- RUN ----------
if __name__ == "__main__":
    app.run(debug=True)