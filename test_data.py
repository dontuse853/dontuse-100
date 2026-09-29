import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
import pytest

from engine import data as data_mod


# ---------------------------------------------------------------------
# Ticker resolution
# ---------------------------------------------------------------------
def test_resolve_ticker_maps_known_benchmarks_case_insensitively():
    assert data_mod.resolve_ticker("btc") == "BTC-USD"
    assert data_mod.resolve_ticker("BTC") == "BTC-USD"
    assert data_mod.resolve_ticker("spy") == "SPY"


def test_resolve_ticker_passes_through_unknown_tickers():
    assert data_mod.resolve_ticker("AAPL") == "AAPL"
    assert data_mod.resolve_ticker("nvda") == "nvda"


# ---------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------
def test_raises_without_start_or_period():
    with pytest.raises(ValueError):
        data_mod.download_price_history("SPY")


def test_raises_clearly_if_yfinance_missing(monkeypatch):
    monkeypatch.setattr(data_mod, "yf", None)
    with pytest.raises(RuntimeError, match="yfinance isn't installed"):
        data_mod.download_price_history("SPY", period="1y")


# ---------------------------------------------------------------------
# Helpers to fake yfinance.download's return shape
# ---------------------------------------------------------------------
def _fake_plain_ohlc(n=30):
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    rng = np.random.default_rng(0)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    return pd.DataFrame(
        {
            "Open": close + rng.normal(0, 0.1, n),
            "High": close + 1,
            "Low": close - 1,
            "Close": close,
            "Volume": rng.integers(1000, 5000, n),
        },
        index=idx,
    )


def _fake_multiindex_ohlc(ticker="SPY", n=30):
    """Mimics yfinance's (price_field, ticker) MultiIndex column shape."""
    plain = _fake_plain_ohlc(n)
    plain.columns = pd.MultiIndex.from_product([plain.columns, [ticker]])
    return plain


# ---------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------
def test_normalizes_plain_columns(monkeypatch):
    monkeypatch.setattr(data_mod.yf, "download", lambda *a, **k: _fake_plain_ohlc())
    df = data_mod.download_price_history("SPY", period="1mo")
    assert list(df.columns) == ["Open", "High", "Low", "Close"]
    assert len(df) == 30
    assert not df.isna().any().any()


def test_normalizes_multiindex_columns(monkeypatch):
    monkeypatch.setattr(data_mod.yf, "download", lambda *a, **k: _fake_multiindex_ohlc())
    df = data_mod.download_price_history("SPY", period="1mo")
    assert list(df.columns) == ["Open", "High", "Low", "Close"]
    assert len(df) == 30


def test_raises_on_empty_result(monkeypatch):
    monkeypatch.setattr(data_mod.yf, "download", lambda *a, **k: pd.DataFrame())
    with pytest.raises(RuntimeError, match="No data returned"):
        data_mod.download_price_history("FAKE", period="1mo")


def test_raises_on_missing_expected_columns(monkeypatch):
    broken = pd.DataFrame({"Close": [1, 2, 3]}, index=pd.date_range("2024-01-01", periods=3))
    monkeypatch.setattr(data_mod.yf, "download", lambda *a, **k: broken)
    with pytest.raises(RuntimeError, match="missing expected column"):
        data_mod.download_price_history("SPY", period="1mo")


# ---------------------------------------------------------------------
# Customizable time frame — period vs explicit start/end are both wired through
# ---------------------------------------------------------------------
def test_period_is_forwarded_to_yfinance(monkeypatch):
    captured = {}

    def fake_download(ticker, **kwargs):
        captured.update(kwargs)
        captured["ticker"] = ticker
        return _fake_plain_ohlc()

    monkeypatch.setattr(data_mod.yf, "download", fake_download)
    data_mod.download_price_history("btc", period="2y", interval="1d")

    assert captured["ticker"] == "BTC-USD"  # resolved from the friendly name
    assert captured["period"] == "2y"
    assert "start" not in captured


def test_explicit_dates_are_forwarded_to_yfinance(monkeypatch):
    captured = {}

    def fake_download(ticker, **kwargs):
        captured.update(kwargs)
        return _fake_plain_ohlc()

    monkeypatch.setattr(data_mod.yf, "download", fake_download)
    data_mod.download_price_history("SPY", start="2022-01-01", end="2023-01-01")

    assert captured["start"] == "2022-01-01"
    assert captured["end"] == "2023-01-01"
    assert "period" not in captured


# ---------------------------------------------------------------------
# download_many
# ---------------------------------------------------------------------
def test_download_many_returns_keyed_by_requested_name(monkeypatch):
    monkeypatch.setattr(data_mod.yf, "download", lambda *a, **k: _fake_plain_ohlc())
    results = data_mod.download_many(["SPY", "BTC"], period="1mo")
    assert set(results.keys()) == {"SPY", "BTC"}
    for df in results.values():
        assert list(df.columns) == ["Open", "High", "Low", "Close"]


def test_download_many_collects_and_raises_all_failures(monkeypatch):
    def flaky_download(ticker, **kwargs):
        if ticker == "BAD":
            return pd.DataFrame()  # triggers the empty-result error
        return _fake_plain_ohlc()

    monkeypatch.setattr(data_mod.yf, "download", flaky_download)
    with pytest.raises(RuntimeError, match="BAD"):
        data_mod.download_many(["SPY", "BAD"], period="1mo")
