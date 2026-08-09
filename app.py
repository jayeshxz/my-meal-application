"""
MY MESS — Flask backend
------------------------
Run with:
    pip install -r requirements.txt
    python app.py

Then open http://127.0.0.1:5000

Two account types share this app:
    /host/...      mess owners: create a community, manage students & dues
    /student/...   students: join a community, pick a plan, track their cycle

Real password hashing + server-side sessions + a real SQLite database —
this is a genuine backend, not a browser-only demo. The one thing that is
still a stand-in is payment: there's no payment gateway wired up (that
needs real merchant credentials, e.g. Razorpay/UPI), so "Pay now" simply
marks a record as paid so the rest of the app (dues, dashboards, cycles)
can be exercised end-to-end.
"""

import io
import os
from datetime import date, timedelta
from functools import wraps

import qrcode
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, send_file, abort
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from models import db, Host, Student, gen_community_id, gen_join_password

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_UPLOAD_MB = 5

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me-in-production")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "mymess.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

db.init_app(app)


# ------------------------------- helpers -------------------------------- #

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def save_upload(file_storage, prefix):
    if not file_storage or file_storage.filename == "":
        return None
    if not allowed_file(file_storage.filename):
        return None
    filename = secure_filename(f"{prefix}_{file_storage.filename}")
    file_storage.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
    return f"uploads/{filename}"


def host_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("host_id"):
            return redirect(url_for("host_login"))
        return f(*args, **kwargs)
    return wrapper


def student_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("student_id"):
            return redirect(url_for("student_login"))
        return f(*args, **kwargs)
    return wrapper


def subscription_state(host):
    """Returns ('active' | 'grace' | 'expired', days)."""
    diff = (host.subscription_end - date.today()).days
    if diff >= 0:
        return "active", diff
    if diff >= -5:
        return "grace", -diff
    return "expired", -diff


# -------------------------------- landing -------------------------------- #

@app.route("/")
def landing():
    return render_template("landing.html")


# ------------------------------ host: auth -------------------------------- #

@app.route("/host/signup", methods=["GET", "POST"])
def host_signup():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        mess_name = request.form.get("mess_name", "").strip()
        monthly_raw = request.form.get("monthly_charge", "")
        yearly_raw = request.form.get("yearly_charge", "")
        upi = request.form.get("upi_id", "").strip()
        instructions = request.form.get("instructions", "").strip()
        sub_plan = request.form.get("subscription_plan", "yearly")

        if not all([name, email, password, mess_name, monthly_raw, upi]):
            flash("Please fill in all required fields.", "error")
            return render_template("host_signup.html", form=request.form)

        if Host.query.filter_by(email=email).first():
            flash("An account with that email already exists — try logging in.", "error")
            return render_template("host_signup.html", form=request.form)

        monthly = float(monthly_raw)
        yearly = float(yearly_raw) if yearly_raw else monthly * 11

        community_id = gen_community_id()
        while Host.query.filter_by(community_id=community_id).first():
            community_id = gen_community_id()

        host = Host(
            name=name,
            email=email,
            password_hash=generate_password_hash(password),
            mess_name=mess_name,
            community_id=community_id,
            community_password=gen_join_password(),
            monthly_charge=monthly,
            yearly_charge=yearly,
            upi_id=upi,
            instructions=instructions or "Add your mess timings and rules here.",
            subscription_plan=sub_plan,
            subscription_end=date.today() + timedelta(days=30 if sub_plan == "monthly" else 365),
        )
        db.session.add(host)
        db.session.commit()

        session["host_id"] = host.id
        return redirect(url_for("host_created"))

    return render_template("host_signup.html", form={})


@app.route("/host/created")
@host_required
def host_created():
    host = Host.query.get(session["host_id"])
    return render_template("host_created.html", host=host)


@app.route("/host/login", methods=["GET", "POST"])
def host_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        host = Host.query.filter_by(email=email).first()
        if not host or not check_password_hash(host.password_hash, password):
            flash("Incorrect email or password.", "error")
            return render_template("host_login.html")
        session["host_id"] = host.id
        return redirect(url_for("host_dashboard"))
    return render_template("host_login.html")


@app.route("/host/logout")
def host_logout():
    session.pop("host_id", None)
    return redirect(url_for("landing"))


@app.route("/host/qr.png")
@host_required
def host_qr():
    host = Host.query.get(session["host_id"])
    img = qrcode.make(host.community_id)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


# ---------------------------- host: dashboard ----------------------------- #

@app.route("/host/dashboard")
@host_required
def host_dashboard():
    host = Host.query.get(session["host_id"])
    students = Student.query.filter_by(community_id_fk=host.id).order_by(Student.name).all()

    expected = sum(s.amount for s in students)
    received = sum(s.amount for s in students if s.paid)
    pending = expected - received

    state, days = subscription_state(host)

    return render_template(
        "host_dashboard.html",
        host=host, students=students,
        expected=expected, received=received, pending=pending,
        sub_state=state, sub_days=days,
        tab=request.args.get("tab", "all"),
    )


@app.route("/host/settings", methods=["POST"])
@host_required
def host_settings():
    host = Host.query.get(session["host_id"])
    monthly = request.form.get("monthly_charge")
    yearly = request.form.get("yearly_charge")
    upi = request.form.get("upi_id", "").strip()
    instructions = request.form.get("instructions", "").strip()

    if monthly:
        host.monthly_charge = float(monthly)
    if yearly:
        host.yearly_charge = float(yearly)
    if upi:
        host.upi_id = upi
    if instructions:
        host.instructions = instructions

    db.session.commit()
    flash("Settings saved.", "success")
    return redirect(url_for("host_dashboard", tab="settings"))


@app.route("/host/renew", methods=["POST"])
@host_required
def host_renew():
    host = Host.query.get(session["host_id"])
    host.subscription_end = date.today() + timedelta(
        days=30 if host.subscription_plan == "monthly" else 365
    )
    db.session.commit()
    flash("Hosting subscription renewed.", "success")
    return redirect(url_for("host_dashboard"))


@app.route("/host/student/<int:student_id>/mark_paid", methods=["POST"])
@host_required
def mark_paid(student_id):
    host = Host.query.get(session["host_id"])
    student = Student.query.get_or_404(student_id)
    if student.community_id_fk != host.id:
        abort(403)
    student.paid = True
    student.paid_on = date.today()
    db.session.commit()
    return redirect(url_for("host_dashboard", tab="pending"))


# ----------------------------- student: auth ------------------------------ #

@app.route("/student/join", methods=["GET", "POST"])
def student_join():
    if request.method == "POST":
        community_id = request.form.get("community_id", "").strip().upper()
        password = request.form.get("community_password", "").strip()
        host = Host.query.filter_by(community_id=community_id).first()

        if not host or host.community_password != password:
            flash("No match — check the Community ID and password with your mess owner.", "error")
            return render_template("student_join.html")

        session["join_host_id"] = host.id
        return redirect(url_for("student_signup"))

    return render_template("student_join.html")


@app.route("/student/signup", methods=["GET", "POST"])
def student_signup():
    join_host_id = session.get("join_host_id")
    if not join_host_id:
        return redirect(url_for("student_join"))
    host = Host.query.get(join_host_id)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        college = request.form.get("college", "").strip()
        plan = request.form.get("plan", "both")
        time_of_day = request.form.get("time_of_day") or None
        start_date_str = request.form.get("start_date") or date.today().isoformat()

        if not all([name, phone, email, password, college]):
            flash("Please fill in all required fields.", "error")
            return render_template("student_signup.html", host=host, form=request.form)

        if plan == "one" and time_of_day not in ("morning", "night"):
            flash("Pick morning or night for a one-time plan.", "error")
            return render_template("student_signup.html", host=host, form=request.form)

        if Student.query.filter_by(email=email).first():
            flash("An account with that email already exists — try logging in.", "error")
            return render_template("student_signup.html", host=host, form=request.form)

        avatar_path = save_upload(request.files.get("avatar"), f"avatar_{email}")
        proof_path = save_upload(request.files.get("proof"), f"proof_{email}")

        start_dt = date.fromisoformat(start_date_str)
        end_dt = start_dt + timedelta(days=30)
        amount = host.monthly_charge if plan == "both" else round(host.monthly_charge * 0.6, 2)

        student = Student(
            community_id_fk=host.id,
            name=name, phone=phone, email=email,
            password_hash=generate_password_hash(password),
            college=college,
            avatar_path=avatar_path, proof_path=proof_path,
            plan=plan, time_of_day=time_of_day,
            start_date=start_dt, end_date=end_dt, amount=amount,
            paid=False,
        )
        db.session.add(student)
        db.session.commit()

        session.pop("join_host_id", None)
        session["student_id"] = student.id
        return redirect(url_for("student_pay"))

    return render_template("student_signup.html", host=host, form={})


@app.route("/student/login", methods=["GET", "POST"])
def student_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        student = Student.query.filter_by(email=email).first()
        if not student or not check_password_hash(student.password_hash, password):
            flash("Incorrect email or password.", "error")
            return render_template("student_login.html")
        session["student_id"] = student.id
        return redirect(url_for("student_dashboard"))
    return render_template("student_login.html")


@app.route("/student/logout")
def student_logout():
    session.pop("student_id", None)
    return redirect(url_for("landing"))


# --------------------------- student: pay / dashboard ---------------------- #

@app.route("/student/pay", methods=["GET", "POST"])
@student_required
def student_pay():
    student = Student.query.get(session["student_id"])
    host = Host.query.get(student.community_id_fk)

    if request.method == "POST":
        # Demo confirmation only — see note in host_qr()/README about real payment gateways.
        student.paid = True
        student.paid_on = date.today()
        db.session.commit()
        return redirect(url_for("student_dashboard"))

    return render_template("student_pay.html", student=student, host=host)


@app.route("/student/pay/qr.png")
@student_required
def student_pay_qr():
    student = Student.query.get(session["student_id"])
    host = Host.query.get(student.community_id_fk)
    upi_uri = f"upi://pay?pa={host.upi_id}&am={student.amount}&tn=MessDues"
    img = qrcode.make(upi_uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


@app.route("/student/dashboard")
@student_required
def student_dashboard():
    student = Student.query.get(session["student_id"])
    host = Host.query.get(student.community_id_fk)

    today = date.today()
    total_days = (student.end_date - student.start_date).days or 1
    days_left = max(0, (student.end_date - today).days)
    progress = min(1.0, max(0.0, (total_days - days_left) / total_days))
    cycle_ended = days_left <= 0

    # thali-ring stroke math, mirrors the front-end circle (r=52 -> circumference ~326.7)
    circumference = 326.7
    ring_offset = round(circumference * (1 - progress), 1)

    return render_template(
        "student_dashboard.html",
        student=student, host=host,
        days_left=days_left, cycle_ended=cycle_ended,
        ring_offset=ring_offset, circumference=circumference,
    )


@app.route("/student/renew", methods=["POST"])
@student_required
def student_renew():
    student = Student.query.get(session["student_id"])
    student.start_date = student.end_date
    student.end_date = student.start_date + timedelta(days=30)
    student.paid = False
    db.session.commit()
    return redirect(url_for("student_pay"))


# ---------------------------------- main ---------------------------------- #

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
