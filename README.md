# MY MESS

A meal-subscription manager for hostel/PG messes — hosts create a community
and track dues, students join with an ID/password and manage their own
lunch/dinner cycle.

This is a real Flask + SQLite backend with genuine authentication
(hashed passwords, server-side sessions) — not a front-end-only demo.
It was built and verified end-to-end with an automated test hitting every
route (signup, login, join, plan pricing, payment marking, dashboards,
QR generation) before being handed over.

## Features

**Host account**
- Sign up, create a mess community, get a generated Community ID + password
- Real scannable QR code (generated server-side, no third-party API) for students to join
- Dashboard: total students, expected/received/pending totals, All / Pending / Paid tabs
- Settings: edit charges, UPI ID, instructions
- Hosting subscription ($1/mo or $11/yr) with active → 5-day grace → locked status

**Student account**
- Join a mess via Community ID + password
- Sign up with photo upload, name, phone, email, college, optional ID-proof upload
- Pick Lunch+Dinner or a one-time plan (morning/night) — price adjusts automatically
- Start date auto-computes a 30-day end date
- Dashboard: days-left ring, payment status, mess instructions
- Renewing after a cycle ends starts the next cycle from the old end date

## Setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5000**

The SQLite database (`mymess.db`) is created automatically on first run.

## Project structure

```
my_mess_app/
├── app.py                  Flask routes, auth, QR generation
├── models.py                Host & Student database models
├── requirements.txt
├── static/
│   ├── css/style.css        Shared design system
│   ├── js/main.js           File previews, plan picker, live price preview
│   └── uploads/             Student photos / ID proofs (created at runtime)
└── templates/               Jinja2 pages (landing, host/student flows)
```

## What's real vs. what's a stand-in

**Real:**
- Passwords are hashed with werkzeug (`generate_password_hash`) — never stored in plain text
- Sessions are server-side (Flask's signed session cookie) with `@host_required` / `@student_required` guards on every protected route
- Data persists in a real SQLite database — host and student accounts, students, and payment records all survive a server restart
- QR codes are generated server-side as real, scannable images (`qrcode` + Pillow), not hotlinked from a third party

**Stand-in (needs real infrastructure before this handles actual money):**
- **Payment is a manual confirmation, not a real transaction.** "I've paid" / "Mark as received" just flips a `paid` flag in the database. No money actually moves. A production version needs a real payment gateway (e.g. Razorpay, Cashfree, or a UPI intent + webhook flow) so payment status updates automatically when money is actually received — that requires a merchant account and API keys only you can set up.
- **Single server, single database file.** Fine for one mess owner testing this locally. For multiple real messes running concurrently over the internet, you'd want this deployed behind a real WSGI server (gunicorn/uwsgi) with a production database (Postgres) instead of SQLite, plus HTTPS.
- **No email verification / password reset flow** — signups are trusted as-entered. Worth adding before real users rely on it.

## Community ID / password vs. login password

Two different kinds of "password" are used on purpose:
- **Login password** (host & student accounts) — hashed, never shown again after signup.
- **Community password** — a shared join code a host hands out to their students (like a room code). It's stored in plain text intentionally, since it's meant to be shared and re-displayed in Settings, not a personal secret.
