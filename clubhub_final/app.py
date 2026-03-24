from flask import Flask, render_template, request, redirect, url_for, flash
from flask_mail import Mail, Message
import sqlite3
import os

app = Flask(__name__)
app.secret_key = "clubhub-secret-2024"

# ── Email config ──────────────────────────────────────────────────────────────
# Fill in your Gmail and App Password (see README Step 4 for how to get it)
app.config["MAIL_SERVER"]         = "smtp.gmail.com"
app.config["MAIL_PORT"]           = 587
app.config["MAIL_USE_TLS"]        = True
app.config["MAIL_USERNAME"]       = "your_gmail@gmail.com"   # ← change this
app.config["MAIL_PASSWORD"]       = "your_app_password"       # ← change this
app.config["MAIL_DEFAULT_SENDER"] = "your_gmail@gmail.com"   # ← change this
mail = Mail(app)

DB_PATH = "database.db"

# ── DB helpers ────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                date        TEXT NOT NULL,
                time        TEXT,
                location    TEXT,
                description TEXT
            );
            CREATE TABLE IF NOT EXISTS payments (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                member_name TEXT NOT NULL,
                amount      REAL NOT NULL,
                purpose     TEXT NOT NULL,
                status      TEXT DEFAULT 'Paid',
                date        TEXT NOT NULL,
                notes       TEXT
            );
            CREATE TABLE IF NOT EXISTS subscribers (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                name  TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL
            );
            CREATE TABLE IF NOT EXISTS newsletters (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                subject TEXT NOT NULL,
                body    TEXT NOT NULL,
                sent_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS feedback (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                name         TEXT NOT NULL,
                rating       INTEGER NOT NULL,
                category     TEXT,
                message      TEXT NOT NULL,
                submitted_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)

# ── Home ──────────────────────────────────────────────────────────────────────
@app.route("/")
def home():
    with get_db() as c:
        events        = c.execute("SELECT * FROM events WHERE date >= date('now') ORDER BY date LIMIT 3").fetchall()
        total         = c.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE status='Paid'").fetchone()[0]
        members       = c.execute("SELECT COUNT(*) FROM subscribers").fetchone()[0]
        feedback_cnt  = c.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
    return render_template("home.html", events=events, total=total,
                           members=members, feedback_cnt=feedback_cnt)

# ── Events ────────────────────────────────────────────────────────────────────
@app.route("/events")
def events():
    with get_db() as c:
        upcoming = c.execute("SELECT * FROM events WHERE date >= date('now') ORDER BY date").fetchall()
        past     = c.execute("SELECT * FROM events WHERE date < date('now') ORDER BY date DESC").fetchall()
    return render_template("events.html", upcoming=upcoming, past=past)

@app.route("/events/add", methods=["GET","POST"])
def add_event():
    if request.method == "POST":
        with get_db() as c:
            c.execute("INSERT INTO events (title,date,time,location,description) VALUES (?,?,?,?,?)",
                      (request.form["title"], request.form["date"],
                       request.form.get("time",""), request.form.get("location",""),
                       request.form.get("description","")))
        flash("Event added!", "success")
        return redirect(url_for("events"))
    return render_template("add_event.html")

@app.route("/events/delete/<int:eid>")
def delete_event(eid):
    with get_db() as c:
        c.execute("DELETE FROM events WHERE id=?", (eid,))
    flash("Event deleted.", "info")
    return redirect(url_for("events"))

# ── Payments ──────────────────────────────────────────────────────────────────
@app.route("/payments")
def payments():
    with get_db() as c:
        rows         = c.execute("SELECT * FROM payments ORDER BY date DESC").fetchall()
        total_paid   = c.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE status='Paid'").fetchone()[0]
        total_pend   = c.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE status='Pending'").fetchone()[0]
    return render_template("payments.html", payments=rows, total_paid=total_paid, total_pend=total_pend)

@app.route("/payments/add", methods=["GET","POST"])
def add_payment():
    if request.method == "POST":
        with get_db() as c:
            c.execute("INSERT INTO payments (member_name,amount,purpose,status,date,notes) VALUES (?,?,?,?,?,?)",
                      (request.form["member_name"], float(request.form["amount"]),
                       request.form["purpose"], request.form.get("status","Paid"),
                       request.form["date"], request.form.get("notes","")))
        flash("Payment recorded!", "success")
        return redirect(url_for("payments"))
    return render_template("add_payment.html")

@app.route("/payments/delete/<int:pid>")
def delete_payment(pid):
    with get_db() as c:
        c.execute("DELETE FROM payments WHERE id=?", (pid,))
    flash("Record deleted.", "info")
    return redirect(url_for("payments"))

# ── Newsletter ────────────────────────────────────────────────────────────────
@app.route("/newsletter")
def newsletter():
    with get_db() as c:
        subs  = c.execute("SELECT * FROM subscribers ORDER BY id DESC").fetchall()
        sent  = c.execute("SELECT * FROM newsletters ORDER BY sent_at DESC").fetchall()
    return render_template("newsletter.html", subs=subs, sent=sent)

@app.route("/newsletter/subscribe", methods=["POST"])
def subscribe():
    try:
        with get_db() as c:
            c.execute("INSERT INTO subscribers (name,email) VALUES (?,?)",
                      (request.form["name"], request.form["email"]))
        flash("Subscriber added!", "success")
    except sqlite3.IntegrityError:
        flash("That email is already subscribed.", "warning")
    return redirect(url_for("newsletter"))

@app.route("/newsletter/remove/<int:sid>")
def remove_subscriber(sid):
    with get_db() as c:
        c.execute("DELETE FROM subscribers WHERE id=?", (sid,))
    flash("Subscriber removed.", "info")
    return redirect(url_for("newsletter"))

@app.route("/newsletter/send", methods=["POST"])
def send_newsletter():
    subject = request.form["subject"]
    body    = request.form["body"]
    with get_db() as c:
        subs = c.execute("SELECT * FROM subscribers").fetchall()
        c.execute("INSERT INTO newsletters (subject,body) VALUES (?,?)", (subject, body))
    if not subs:
        flash("No subscribers yet!", "warning")
        return redirect(url_for("newsletter"))
    try:
        for s in subs:
            msg = Message(subject=subject, recipients=[s["email"]])
            msg.body = f"Hi {s['name']},\n\n{body}\n\n---\nTo unsubscribe reply to this email."
            mail.send(msg)
        flash(f"Newsletter sent to {len(subs)} subscriber(s)!", "success")
    except Exception as e:
        flash(f"Email error: {e}. Check your Gmail settings in app.py.", "error")
    return redirect(url_for("newsletter"))

# ── Feedback ──────────────────────────────────────────────────────────────────
@app.route("/feedback")
def feedback():
    with get_db() as c:
        rows = c.execute("SELECT * FROM feedback ORDER BY submitted_at DESC").fetchall()
        avg  = c.execute("SELECT AVG(rating) FROM feedback").fetchone()[0]
    avg = round(avg, 1) if avg else 0
    return render_template("feedback.html", feedbacks=rows, avg=avg)

@app.route("/feedback/submit", methods=["POST"])
def submit_feedback():
    with get_db() as c:
        c.execute("INSERT INTO feedback (name,rating,category,message) VALUES (?,?,?,?)",
                  (request.form["name"], int(request.form["rating"]),
                   request.form.get("category","General"), request.form["message"]))
    flash("Thanks for your feedback!", "success")
    return redirect(url_for("feedback"))

@app.route("/feedback/delete/<int:fid>")
def delete_feedback(fid):
    with get_db() as c:
        c.execute("DELETE FROM feedback WHERE id=?", (fid,))
    flash("Feedback deleted.", "info")
    return redirect(url_for("feedback"))

# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    app.run(debug=True)
