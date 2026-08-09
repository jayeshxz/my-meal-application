"""
Database models for MY MESS.

Two account types:
    Host    - runs a mess/community, has students under it
    Student - joins one community, tracks one active meal-plan cycle

Passwords for real login (Host.password_hash, Student.password_hash) are
hashed with werkzeug's generate_password_hash — never stored in plain text.

The community_password is different: it's a shared "join code" a host gives
out to students (like a room code), not a personal secret, so it's kept
plain so the host can display/re-share it from Settings.
"""

import random
import string

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def gen_community_id():
    return "MESS" + "".join(random.choices(string.digits, k=4))


def gen_join_password(length=8):
    chars = string.ascii_letters + string.digits
    return "".join(random.choices(chars, k=length))


class Host(db.Model):
    __tablename__ = "hosts"

    id = db.Column(db.Integer, primary_key=True)

    # login credentials
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    # community / mess details
    mess_name = db.Column(db.String(120), nullable=False)
    community_id = db.Column(db.String(20), unique=True, nullable=False)
    community_password = db.Column(db.String(20), nullable=False)

    monthly_charge = db.Column(db.Float, default=0)
    yearly_charge = db.Column(db.Float, default=0)
    upi_id = db.Column(db.String(120), default="")
    instructions = db.Column(db.Text, default="")

    # hosting subscription ($1/mo or $11/yr)
    subscription_plan = db.Column(db.String(20), default="yearly")
    subscription_end = db.Column(db.Date, nullable=False)

    students = db.relationship(
        "Student", backref="community", lazy=True, cascade="all, delete-orphan"
    )


class Student(db.Model):
    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True)
    community_id_fk = db.Column(db.Integer, db.ForeignKey("hosts.id"), nullable=False)

    # login credentials
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    college = db.Column(db.String(150))

    avatar_path = db.Column(db.String(255))   # relative to /static
    proof_path = db.Column(db.String(255))    # optional ID proof

    # meal plan
    plan = db.Column(db.String(10))            # 'both' | 'one'
    time_of_day = db.Column(db.String(10))      # 'morning' | 'night' | None

    # billing cycle
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    paid = db.Column(db.Boolean, default=False)
    paid_on = db.Column(db.Date)

    def meal_label(self):
        if self.plan == "both":
            return "Lunch + Dinner"
        return "Morning only" if self.time_of_day == "morning" else "Night only"
