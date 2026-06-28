"""
VCP / momentum scanner engine.

The classification math here is IDENTICAL to the original morning-scanner
logic. It has only been split into two functions so that:
  1. the web app can run a whole watchlist (scan_watchlist), and
  2. the criteria math can be unit-tested without a live network call
     (_classify_from_df accepts any OHLCV dataframe).

Criteria (unchanged):
  big_move            close >= 60-day low  * 1.20   (up 20%+ off the low)
  shallow_pullback    close >= 60-day high * 0.70   (within 30% of high)
  controlled_pullback close >= 60-day high * 0.85   (within 15% of high)
  vol_contract        avg daily range last 5d < prior 10d
  vol_declining       5-day avg volume < 20-day avg volume
  breakout            close > prior 10-day high AND rel_volume > 1.5

  BREAKOUT  = big_move + shallow_pullback + vol_contract + vol_declining + breakout
  COILING   = big_move + controlled_pullback + vol_contract + vol_declining
  WATCH     = big_move + shallow_pullback + vol_contract
  PASS      = anything else
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

try:
    import yfinance as yf
except ImportError:  # lets the module import for tests even if yfinance is absent
    yf = None

SIGNAL_ORDER = {"BREAKOUT": 0, "COILING": 1, "WATCH": 2, "PASS": 3}


def load_watchlist(filepath: str) -> list[str]:
    with open(filepath) as f:
        return [
            line.strip().upper()
            for line in f
            if line.strip() and not line.startswith("#")
        ]


def parse_tickers(raw: str) -> list[str]:
    """Parse a user-pasted watchlist: commas, spaces, tabs, or newlines."""
    if not raw:
        return []
    seen, out = set(), []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        line = line.replace(",", " ").replace("\t", " ")
        for tok in line.split():
            t = tok.strip().upper()
            if t and not t.startswith("#") and t not in seen:
                seen.add(t)
                out.append(t)
    return out


def _yn(val: bool) -> str:
    return "Yes" if val else "No"


def _classify_from_df(df: pd.DataFrame, ticker: str) -> dict | None:
    """
    Pure computation. Expects a daily OHLCV dataframe with single-level
    columns: Open, High, Low, Close, Volume. Returns the snapshot dict or
    None if there isn't enough data. This is the original math verbatim.
    """
    if df is None or len(df) < 60:
        return None

    df = df.tail(60)

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    current_close = close.iloc[-1]
    if pd.isna(current_close):
        return None

    low_60 = low.min()
    high_60 = high.max()

    big_move = current_close >= low_60 * 1.20
    shallow_pullback = current_close >= high_60 * 0.70
    controlled_pullback = current_close >= high_60 * 0.85

    daily_range = high - low
    vol_contract = daily_range.iloc[-5:].mean() < daily_range.iloc[-15:-5].mean()

    vol_20_avg = volume.iloc[-21:-1].mean()
    vol_5_avg = volume.iloc[-6:-1].mean()
    vol_declining = vol_5_avg < vol_20_avg

    highest_close_10 = close.iloc[-11:-1].max()
    rel_volume = volume.iloc[-1] / vol_20_avg if vol_20_avg else 0.0
    breakout = (current_close > highest_close_10) and (rel_volume > 1.5)

    if big_move and shallow_pullback and vol_contract and vol_declining and breakout:
        signal = "BREAKOUT"
    elif big_move and controlled_pullback and vol_contract and vol_declining:
        signal = "COILING"
    elif big_move and shallow_pullback and vol_contract:
        signal = "WATCH"
    else:
        signal = "PASS"

    return {
        "Ticker": ticker,
        "Close": round(float(current_close), 2),
        "RelVolume": round(float(rel_volume), 2),
        "BIG_MOVE": _yn(bool(big_move)),
        "SHALLOW_PB": _yn(bool(shallow_pullback)),
        "CONTROLLED_PB": _yn(bool(controlled_pullback)),
        "VOL_CONTRACT": _yn(bool(vol_contract)),
        "VOL_DECLINING": _yn(bool(vol_declining)),
        "BREAKOUT": _yn(bool(breakout)),
        "Signal": signal,
    }


def get_vcp_snapshot(ticker: str) -> dict | None:
    """Fetch 3 months of daily data and classify a single ticker."""
    if yf is None:
        raise RuntimeError("yfinance is not installed in this environment.")

    df = yf.download(
        ticker, period="3mo", interval="1d", progress=False, auto_adjust=True
    )
    if df is None or len(df) < 60:
        return None

    # yfinance returns a MultiIndex (field, ticker) for single tickers too
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    return _classify_from_df(df, ticker)


def scan_watchlist(tickers: list[str], max_workers: int = 6) -> tuple[dict, list[str]]:
    """
    Run the scan across a watchlist concurrently and return signal buckets
    plus a list of tickers that failed (bad symbol / not enough data).

    max_workers is kept modest on purpose — yfinance can rate-limit if you
    hammer it with too many simultaneous requests.
    """
    buckets = {"BREAKOUT": [], "COILING": [], "WATCH": [], "PASS": []}
    errors: list[str] = []

    if not tickers:
        return buckets, errors

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(get_vcp_snapshot, t): t for t in tickers}
        for fut in as_completed(futures):
            ticker = futures[fut]
            try:
                result = fut.result()
                if result is None:
                    errors.append(ticker)
                else:
                    buckets[result["Signal"]].append(result)
            except Exception:
                errors.append(ticker)

    # sort each bucket alphabetically for a stable display
    for key in buckets:
        buckets[key].sort(key=lambda s: s["Ticker"])

    return buckets, errors
