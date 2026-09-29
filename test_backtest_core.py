import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
import pytest

from engine import data as data_mod
from engine.backtest import run_backtest, run_backtest_on_ticker
from engine.market import synthetic_ohlc
from engine.supervisor import SupervisorConfig


def make_config(**overrides):
    cfg = SupervisorConfig(starting_capital=10_000, hard_deletion_threshold=40, inactivity_timeout=20)
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


# ---------------------------------------------------------------------
# The core loop is data-source-agnostic
# ---------------------------------------------------------------------
def test_run_backtest_accepts_any_ohlc_dataframe_directly():
    price = synthetic_ohlc(n_bars=200, seed=1)
    result = run_backtest(make_config(), price, children_per_archetype=2, bars_per_generation=40)
    assert len(result.total_equity) == 200
    assert set(result.archetypes.values()) == {"trend_follower", "mean_reversion", "breakout"}


def test_run_backtest_works_with_a_real_dated_index():
    idx = pd.date_range("2023-01-01", periods=250, freq="B")
    rng = np.random.default_rng(4)
    close = 100 + np.cumsum(rng.normal(0.02, 1, len(idx)))
    price = pd.DataFrame({
        "Open": close, "High": close + 1, "Low": close - 1, "Close": close,
    }, index=idx)

    result = run_backtest(make_config(), price, children_per_archetype=2, bars_per_generation=40)
    assert len(result.total_equity) == len(idx)
    # the price index (real dates) is preserved on the result
    assert result.price.index.equals(idx)


def test_run_backtest_rejects_missing_ohlc_columns():
    bad_price = pd.DataFrame({"Close": np.linspace(100, 110, 50)})
    with pytest.raises(ValueError, match="missing required column"):
        run_backtest(make_config(), bad_price)


def test_run_backtest_rejects_too_short_price_history():
    tiny = synthetic_ohlc(n_bars=1, seed=1)
    with pytest.raises(ValueError, match="at least 2 bars"):
        run_backtest(make_config(), tiny)


# ---------------------------------------------------------------------
# Cumulative ecosystem equity curve
# ---------------------------------------------------------------------
def test_total_equity_is_exactly_the_sum_of_individual_equity_lines():
    price = synthetic_ohlc(n_bars=200, seed=2)
    result = run_backtest(make_config(), price, children_per_archetype=3, bars_per_generation=30)

    for t in range(len(result.total_equity)):
        expected = sum(curve[t] for curve in result.equity_curves.values())
        assert result.total_equity[t] == pytest.approx(expected)


def test_every_bot_has_a_full_length_individual_equity_line():
    price = synthetic_ohlc(n_bars=150, seed=3)
    result = run_backtest(make_config(), price, children_per_archetype=2, bars_per_generation=25)
    for bot_id, curve in result.equity_curves.items():
        assert len(curve) == len(price)
        assert curve[0] == make_config().starting_capital


# ---------------------------------------------------------------------
# Trade log
# ---------------------------------------------------------------------
def test_trade_log_entries_have_expected_fields():
    price = synthetic_ohlc(n_bars=300, seed=6)
    result = run_backtest(make_config(), price, children_per_archetype=3, bars_per_generation=40)

    assert len(result.trade_log) > 0
    entry = result.trade_log[0]
    for field in ("step", "date", "bot_id", "archetype", "action", "strength",
                  "reason", "position_size_pct", "pnl_dollars", "capital_after"):
        assert field in entry
    assert entry["action"] in ("long", "short")


def test_trade_log_dates_come_from_the_price_index():
    idx = pd.date_range("2024-01-01", periods=260, freq="B")
    rng = np.random.default_rng(9)
    close = 100 + np.cumsum(rng.normal(0.05, 1.2, len(idx)))
    price = pd.DataFrame({
        "Open": close, "High": close + 1, "Low": close - 1, "Close": close,
    }, index=idx)

    result = run_backtest(make_config(), price, children_per_archetype=3, bars_per_generation=30)
    assert len(result.trade_log) > 0
    for entry in result.trade_log[:5]:
        assert entry["date"] in set(idx)


def test_trade_log_capital_after_matches_final_equity_for_last_trade_per_bot():
    price = synthetic_ohlc(n_bars=250, seed=11)
    result = run_backtest(make_config(), price, children_per_archetype=2, bars_per_generation=30)

    last_trade_per_bot = {}
    for entry in result.trade_log:
        last_trade_per_bot[entry["bot_id"]] = entry

    for bot_id, entry in last_trade_per_bot.items():
        # capital_after the last trade should match the equity curve at
        # that same step (nothing else changes a bot's capital between trades)
        assert result.equity_curves[bot_id][entry["step"]] == pytest.approx(entry["capital_after"])


# ---------------------------------------------------------------------
# Ticker-based convenience wrapper (mocked — no real network in this sandbox)
# ---------------------------------------------------------------------
def test_run_backtest_on_ticker_uses_download_and_the_core_loop(monkeypatch):
    idx = pd.date_range("2023-06-01", periods=220, freq="B")
    rng = np.random.default_rng(13)
    close = 100 + np.cumsum(rng.normal(0.03, 1, len(idx)))
    fake_price = pd.DataFrame({
        "Open": close, "High": close + 1, "Low": close - 1, "Close": close,
    }, index=idx)

    captured = {}

    def fake_download(ticker, start=None, end=None, period=None, interval="1d"):
        captured.update(ticker=ticker, start=start, end=end, period=period, interval=interval)
        return fake_price

    monkeypatch.setattr(data_mod, "download_price_history", fake_download)
    # backtest.py imported the name directly, so patch it there too
    import engine.backtest as bt_mod
    monkeypatch.setattr(bt_mod, "download_price_history", fake_download)

    result = run_backtest_on_ticker(
        make_config(), "SPY", period="1y", children_per_archetype=2, bars_per_generation=30,
    )

    assert captured["ticker"] == "SPY"
    assert captured["period"] == "1y"
    assert len(result.total_equity) == len(idx)
    assert result.price.index.equals(idx)
