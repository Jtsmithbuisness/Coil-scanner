"""
Coil — a momentum / VCP watchlist scanner.

Paste your own watchlist, the engine filters it by the VCP criteria and
groups the results by signal strength. Free tier is capped at a ticker
limit; pro tier is unlimited.
"""

import json
import os
import re

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
)
from flask_login import current_user, login_user, logout_user

from src.scanners.vcp_scanner import parse_tickers, scan_watchlist
from extensions import db, login_manager
from models import User, Watchlist, ScanResult

import config

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///coil.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)
login_manager.init_app(app)
login_manager.login_view = "login"

with app.app_context():
    db.create_all()


@login_manager.user_loader
def load_user(user_id: str):
    return User.query.get(int(user_id))


def current_tier() -> str:
    if current_user.is_authenticated:
        return current_user.tier
    return "free"


def ticker_limit() -> int | None:
    """None means unlimited."""
    return None if current_tier() == "pro" else config.FREE_TICKER_LIMIT


@app.context_processor
def inject_globals():
    return {
        "app_name": config.APP_NAME,
        "tagline": config.TAGLINE,
        "tier": current_tier(),
        "free_limit": config.FREE_TICKER_LIMIT,
        "free_limit_wl": config.FREE_WATCHLIST_LIMIT,
    }


def _user_watchlists():
    if not current_user.is_authenticated:
        return []
    return (
        Watchlist.query
        .filter_by(user_id=current_user.id)
        .order_by(Watchlist.created_at.desc())
        .all()
    )


def _can_save_watchlist(current_count: int) -> bool:
    if not current_user.is_authenticated:
        return False
    if current_user.tier == "pro":
        return True
    return current_count < config.FREE_WATCHLIST_LIMIT


@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("scanner"))
    return render_template("landing.html")


@app.route("/scanner", methods=["GET", "POST"])
def scanner():
    results = None
    errors = []
    # Pre-fill textarea when loading a saved watchlist via GET
    raw = request.args.get("tickers", "")
    truncated_from = None
    total_scanned = 0
    watchlists = _user_watchlists()

    if request.method == "POST":
        raw = request.form.get("watchlist", "")
        tickers = parse_tickers(raw)
        save_name = request.form.get("save_name", "").strip()

        if not tickers:
            flash("Add at least one ticker to scan.", "warn")
            return render_template(
                "index.html", raw=raw, watchlists=watchlists,
                can_save=_can_save_watchlist(len(watchlists)),
            )

        # Save before truncating so the full list is stored
        if save_name:
            if not current_user.is_authenticated:
                flash("Log in to save watchlists.", "warn")
            elif not _can_save_watchlist(len(watchlists)):
                flash(
                    f"Free accounts can save {config.FREE_WATCHLIST_LIMIT} watchlist. "
                    "Go pro for unlimited.", "warn"
                )
            else:
                wl = Watchlist(
                    user_id=current_user.id,
                    name=save_name,
                    tickers=",".join(tickers),
                )
                db.session.add(wl)
                db.session.commit()
                flash(f'Watchlist "{save_name}" saved.', "ok")
                watchlists = _user_watchlists()

        limit = ticker_limit()
        if limit is not None and len(tickers) > limit:
            truncated_from = len(tickers)
            tickers = tickers[:limit]

        buckets, errors = scan_watchlist(tickers)
        total_scanned = sum(len(v) for v in buckets.values())
        results = buckets

    return render_template(
        "index.html",
        results=results,
        errors=errors,
        raw=raw,
        truncated_from=truncated_from,
        total_scanned=total_scanned,
        watchlists=watchlists,
        can_save=_can_save_watchlist(len(watchlists)),
    )


@app.route("/upgrade")
def upgrade():
    # TODO: replace with Stripe Checkout session creation.
    # On successful payment webhook, set current_user.tier = 'pro' and db.session.commit().
    if not current_user.is_authenticated:
        flash("Log in to upgrade.", "warn")
        return redirect(url_for("login"))
    current_user.tier = "pro"
    db.session.commit()
    flash("You're on the pro tier. Unlimited tickers unlocked.", "ok")
    return redirect(url_for("scanner"))


@app.route("/downgrade")
def downgrade():
    # Convenience for testing the free-tier gating during development.
    if not current_user.is_authenticated:
        return redirect(url_for("index"))
    current_user.tier = "free"
    db.session.commit()
    flash("Switched back to the free tier.", "ok")
    return redirect(url_for("scanner"))


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("scanner"))
    email = ""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not _EMAIL_RE.match(email):
            flash("Enter a valid email address.", "warn")
        elif len(password) < 8:
            flash("Password must be at least 8 characters.", "warn")
        elif User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "warn")
        else:
            user = User(email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("Account created — welcome to Coil.", "ok")
            return redirect(url_for("scanner"))
    return render_template("register.html", email=email)


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("scanner"))
    email = ""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user is None or not user.check_password(password):
            flash("Incorrect email or password.", "warn")
        else:
            login_user(user)
            flash("Welcome back.", "ok")
            return redirect(url_for("scanner"))
    return render_template("login.html", email=email)


@app.route("/logout")
def logout():
    logout_user()
    flash("You've been logged out.", "ok")
    return redirect(url_for("index"))


@app.route("/watchlists/<int:wl_id>/load")
def load_watchlist(wl_id):
    if not current_user.is_authenticated:
        return redirect(url_for("login"))
    wl = Watchlist.query.filter_by(id=wl_id, user_id=current_user.id).first_or_404()
    return redirect(url_for("scanner", tickers=wl.tickers))


@app.route("/watchlists/<int:wl_id>/delete", methods=["POST"])
def delete_watchlist(wl_id):
    if not current_user.is_authenticated:
        return redirect(url_for("login"))
    wl = Watchlist.query.filter_by(id=wl_id, user_id=current_user.id).first_or_404()
    name = wl.name
    db.session.delete(wl)
    db.session.commit()
    flash(f'Watchlist "{name}" deleted.', "ok")
    return redirect(url_for("scanner"))


@app.route("/scans/latest")
def last_scan():
    if not current_user.is_authenticated:
        return redirect(url_for("login"))

    if current_user.tier != "pro":
        return render_template("last_scan.html", scan_data=None, ran_at=None, upgrade=True)

    latest = (
        ScanResult.query
        .filter_by(user_id=current_user.id)
        .order_by(ScanResult.ran_at.desc())
        .first()
    )

    if not latest:
        return render_template("last_scan.html", scan_data=None, ran_at=None, upgrade=False)

    # Pull every result from the same batch run (all share the same ran_at timestamp)
    batch = (
        ScanResult.query
        .filter_by(user_id=current_user.id, ran_at=latest.ran_at)
        .order_by(ScanResult.watchlist_name)
        .all()
    )
    scan_data = [(s, json.loads(s.results_json)) for s in batch]

    return render_template(
        "last_scan.html",
        scan_data=scan_data,
        ran_at=latest.ran_at,
        upgrade=False,
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5002))
    app.run(host="0.0.0.0", port=port, debug=True)
