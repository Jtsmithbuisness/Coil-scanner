"""
Configuration. Rename the product, change the free-tier limit, or set the
secret key here. In production (Railway), set SECRET_KEY as an environment
variable instead of using the dev default.
"""

import os

APP_NAME = "Coil"
TAGLINE = "Paste a watchlist. See what's setting up."

# How many tickers a free-tier user can scan at once. Pro tier is unlimited.
FREE_TICKER_LIMIT = 10

# How many watchlists a free-tier user can save. Pro tier is unlimited.
FREE_WATCHLIST_LIMIT = 1

# Used to sign the session cookie. MUST be overridden in production.
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me-in-production")
