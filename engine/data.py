"""
Darwin Desk — historical price data utility.

Downloads historical OHLC bars for a benchmark ticker (SPY, BTC, ...)
using yfinance and normalizes the result to exactly the same
Open/High/Low/Close schema engine/market.py's synthetic_ohlc produces
— so real historical data is a drop-in replacement anywhere a price
DataFrame is expected: engine.backtest.run_backtest, every archetype's
precompute()/generate_signal().

This module only reads public historical price data via yfinance. It
never places an order, holds credentials, or talks to a brokerage —
and it never silently substitutes synthetic data for a failed
download. If the data isn't real, the caller finds out immediately via
a raised error, not a chart that quietly looks real when it isn't.
"""

from __future__ import annotations

import datetime as dt
from typing import Optional, Union

import pandas as pd

try:
    import yfinance as yf
    _IMPORT_ERROR: Optional[Exception] = None
except ImportError as exc:  # pragma: no cover - exercised only when yfinance is missing
    yf = None
    _IMPORT_ERROR = exc


# Friendly shorthand for a few common benchmarks -> the ticker symbol
# yfinance/Yahoo Finance actually expects. Anything not in here is
# passed straight through, so an arbitrary ticker still works.
BENCHMARKS = {
    "SPY": "SPY",        # S&P 500 ETF
    "QQQ": "QQQ",         # Nasdaq 100 ETF
    "DIA": "DIA",         # Dow Jones ETF
    "BTC": "BTC-USD",     # Bitcoin
    "ETH": "ETH-USD",     # Ethereum
    "GOLD": "GC=F",        # Gold futures
}

DateLike = Union[str, dt.date, dt.datetime]


def resolve_ticker(name: str) -> str:
    """Map a friendly benchmark name (case-insensitive) to the ticker
    symbol yfinance expects, e.g. "btc" -> "BTC-USD". Anything not in
    BENCHMARKS is returned unchanged, so a raw ticker still works."""
    return BENCHMARKS.get(name.strip().upper(), name)


def download_price_history(
    ticker: str,
    start: Optional[DateLike] = None,
    end: Optional[DateLike] = None,
    period: Optional[str] = None,
    interval: str = "1d",
) -> pd.DataFrame:
    """
    Download historical bars for `ticker` and return a DataFrame with
    exactly the columns Open/High/Low/Close, indexed by date.

    Customize the time frame either with explicit dates:
        download_price_history("SPY", start="2022-01-01", end="2024-01-01")
    or with a relative lookback window (anything yfinance's `period`
    accepts — "6mo", "1y", "5y", "max", ...):
        download_price_history("BTC", period="2y")

    `interval` follows yfinance too ("1d", "1h", "1wk", ...) — daily by
    default, per the brief.

    Raises RuntimeError rather than returning anything if the download
    fails or comes back empty (bad ticker, no network, invalid date
    range) — this function either returns real data or tells you why
    it couldn't.
    """
    if yf is None:
        raise RuntimeError(
            "yfinance isn't installed. Run `pip install yfinance`. "
            f"(original import error: {_IMPORT_ERROR})"
        )
    if period is None and start is None:
        raise ValueError("Provide either `start` (with optional `end`) or `period`.")

    resolved = resolve_ticker(ticker)
    kwargs = dict(interval=interval, progress=False, auto_adjust=True)
    if period is not None:
        kwargs["period"] = period
    else:
        kwargs["start"] = _to_date_str(start)
        if end is not None:
            kwargs["end"] = _to_date_str(end)

    raw = yf.download(resolved, **kwargs)

    if raw is None or raw.empty:
        window = f"period={period}" if period else f"{start} -> {end or 'today'}"
        raise RuntimeError(
            f"No data returned for '{ticker}' (resolved to '{resolved}') over {window}. "
            "Check the ticker and time frame, and that this environment has network "
            "access to Yahoo Finance."
        )

    return _normalize_ohlc(raw)


def download_many(
    tickers: list[str],
    start: Optional[DateLike] = None,
    end: Optional[DateLike] = None,
    period: Optional[str] = None,
    interval: str = "1d",
) -> dict[str, pd.DataFrame]:
    """Convenience helper for pulling several benchmarks at once, e.g.
    `download_many(["SPY", "BTC"], period="1y")`. Returns a dict keyed
    by the ticker exactly as passed in (not the resolved symbol), so
    it's easy to look results back up by whatever name you asked for.
    A failure on one ticker doesn't take the others down with it — it's
    collected and re-raised as a single error listing every failure."""
    results: dict[str, pd.DataFrame] = {}
    failures: list[str] = []
    for ticker in tickers:
        try:
            results[ticker] = download_price_history(ticker, start=start, end=end, period=period, interval=interval)
        except (RuntimeError, ValueError) as exc:
            failures.append(f"{ticker}: {exc}")
    if failures:
        raise RuntimeError("Failed to download one or more tickers:\n" + "\n".join(failures))
    return results


def _normalize_ohlc(raw: pd.DataFrame) -> pd.DataFrame:
    """yfinance's column shape has changed across versions — sometimes
    a plain Index, sometimes a MultiIndex (price field, ticker) even
    for a single symbol. Flatten either case down to plain
    Open/High/Low/Close columns."""
    df = raw.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    missing = [c for c in ("Open", "High", "Low", "Close") if c not in df.columns]
    if missing:
        raise RuntimeError(f"Downloaded data is missing expected column(s): {missing}")

    df = df[["Open", "High", "Low", "Close"]].dropna()
    df.index.name = "Date"
    return df


def _to_date_str(value: DateLike) -> str:
    if isinstance(value, str):
        return value
    return value.strftime("%Y-%m-%d")
