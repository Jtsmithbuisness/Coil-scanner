#!/usr/bin/env python3
"""
Coil daily scanner — run by cron to automatically scan all pro users'
saved watchlists and write results to the database.

Each run creates one ScanResult row per watchlist, all sharing the same
ran_at timestamp so /scans/latest can retrieve the full batch together.

Usage (from the project directory, venv active):
    python daily_scan.py

Cron setup — see bottom of this file for the exact command to copy.
"""

import json
import sys
from datetime import datetime, timezone

from app import app
from models import ScanResult, User, Watchlist, db
from src.scanners.vcp_scanner import parse_tickers, scan_watchlist


def run() -> int:
    """Scan all pro users' watchlists. Returns exit code (0 = ok, 1 = error)."""
    ran_at = datetime.now(timezone.utc)
    print(f"[{ran_at.strftime('%Y-%m-%d %H:%M:%S UTC')}] Coil daily scan starting")

    try:
        with app.app_context():
            pro_users = User.query.filter_by(tier="pro").all()
            print(f"  Pro users with accounts: {len(pro_users)}")

            users_scanned = 0
            tickers_scanned = 0

            for user in pro_users:
                watchlists = Watchlist.query.filter_by(user_id=user.id).all()
                if not watchlists:
                    continue

                users_scanned += 1
                for wl in watchlists:
                    tickers = parse_tickers(wl.tickers)
                    if not tickers:
                        continue

                    print(f"  [{user.email}] '{wl.name}' — {len(tickers)} tickers")
                    buckets, errors = scan_watchlist(tickers)

                    if errors:
                        print(f"    No data for: {', '.join(errors)}")

                    hits = sum(
                        len(v) for k, v in buckets.items() if k != "PASS"
                    )
                    print(f"    Results: {hits} setup(s) found")

                    db.session.add(ScanResult(
                        user_id=user.id,
                        watchlist_id=wl.id,
                        watchlist_name=wl.name,
                        ran_at=ran_at,
                        results_json=json.dumps(buckets),
                    ))
                    tickers_scanned += len(tickers)

            db.session.commit()

        print(
            f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}] "
            f"Done — {tickers_scanned} tickers across {users_scanned} user(s)"
        )
        return 0

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(run())

# ── Cron setup ────────────────────────────────────────────────────────────────
#
# Run `crontab -e` and add a line like this (edit the path and time to suit):
#
#   30 6 * * 1-5 cd /Users/you/Desktop/scanner-app && .venv/bin/python daily_scan.py >> logs/daily_scan.log 2>&1
#
# That runs the scan at 6:30 AM every weekday (Mon–Fri).
# Adjust the time to whenever after market close you want the scan to run.
# Create the logs/ directory first: mkdir -p logs
#
# To test the cron entry without waiting:
#   cd /Users/you/Desktop/scanner-app && source .venv/bin/activate && python daily_scan.py
