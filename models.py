from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(254), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    tier = db.Column(db.String(16), nullable=False, default="free")
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Watchlist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    tickers = db.Column(db.Text, nullable=False)  # comma-separated, normalised by parse_tickers
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    user = db.relationship("User", backref=db.backref("watchlists", lazy=True))

    @property
    def ticker_count(self) -> int:
        return len([t for t in self.tickers.split(",") if t])


class ScanResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    watchlist_id = db.Column(db.Integer, db.ForeignKey("watchlist.id"), nullable=True)
    watchlist_name = db.Column(db.String(100), nullable=False)
    ran_at = db.Column(db.DateTime, nullable=False)
    results_json = db.Column(db.Text, nullable=False)  # JSON-serialised buckets dict

    user = db.relationship("User", backref=db.backref("scan_results", lazy=True))
