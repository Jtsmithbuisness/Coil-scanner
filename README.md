# Coil — momentum / VCP watchlist scanner

A web app that runs your VCP scanner logic on any watchlist a user pastes in,
and groups the results by signal strength. Same engine as `morning-scanner`,
different front door: a web page instead of a Discord webhook.

## What it does
- User pastes a watchlist (spaces, commas, or new lines)
- Engine runs the **exact** VCP criteria from the original scanner
- Results group into lanes: Strong setups → Coiling → On watch → Passed
- Free tier is capped at a ticker limit; Pro tier is unlimited

## Run it locally
```bash
cd ~/Desktop/scanner-app          # wherever you put it
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```
Then open http://127.0.0.1:5002

To test the tiers while developing:
- `/upgrade`   → switch the session to Pro (no cap)
- `/downgrade` → switch back to Free

## The criteria (unchanged from your scanner)
| Flag      | Meaning                                            |
|-----------|----------------------------------------------------|
| MOVE      | up 20%+ off the 60-day low                         |
| PB<30%    | within 30% of the 60-day high (shallow pullback)   |
| TIGHT     | daily range contracting (last 5d < prior 10d)      |
| VOL↓      | 5-day avg volume below 20-day avg                  |
| B/O       | closed above the prior 10-day high on RVOL > 1.5   |

Signal = BREAKOUT (all) → COILING → WATCH → PASS, exactly as before.

## Deploy to Railway (same as ranch-manager)
1. Push to a private GitHub repo
2. New Railway project → deploy from the repo
3. Set an environment variable: `SECRET_KEY` = a long random string
4. Railway uses the `Procfile` (`gunicorn app:app`) automatically

## One thing to know about speed (read this)
The scan calls Yahoo Finance once per ticker. The free tier (10 tickers) is
quick. Large lists are slower and Yahoo can rate-limit if hammered — that's why
the engine uses a small thread pool (6 workers). For big Pro watchlists later
you'll want one of: a longer gunicorn timeout, a background job + "results
ready" screen, or short-term caching of recent scans. That's a polish item,
not a v1 blocker.

## Roadmap — the Hawaii build
v1 (this) ships the engine + tier gating. Next:
1. **Real accounts** — replace the session `tier` flag with a user table + login.
2. **Stripe** — Checkout for the Pro subscription; a webhook sets `tier = 'pro'`.
   The only two spots that change are the `/upgrade` route and `current_tier()`
   in `app.py` (both marked with TODO).
3. **Discord funnel** — free community that points people to the app.

## Not financial advice
Coil is a screening tool for educational/informational use only. It does not
recommend trades. Keep your own trading record private until your execution is
where you want it — the product is the scanner, not your P&L.
