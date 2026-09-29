import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import random

import numpy as np
import pandas as pd

from engine import indicators as ind
from engine.bots import TrendFollowerBot, MeanReversionBot, BreakoutBot
from engine.market import synthetic_ohlc
from engine.supervisor import SupervisorConfig
from engine.backtest import build_population, run_backtest, run_backtest_on_synthetic_market


# ---------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------
def test_sma_matches_manual_mean():
    s = pd.Series([1, 2, 3, 4, 5])
    result = ind.sma(s, 3)
    assert np.isclose(result.iloc[-1], (3 + 4 + 5) / 3)


def test_rsi_is_high_in_a_strong_uptrend():
    s = pd.Series(np.linspace(100, 150, 40))  # monotonically rising
    r = ind.rsi(s, window=14).iloc[-1]
    assert r > 70


def test_rsi_is_low_in_a_strong_downtrend():
    s = pd.Series(np.linspace(150, 100, 40))
    r = ind.rsi(s, window=14).iloc[-1]
    assert r < 30


def test_bollinger_bands_bracket_the_middle():
    s = pd.Series(np.random.default_rng(1).normal(100, 2, 60))
    mid, upper, lower = ind.bollinger_bands(s, window=20, num_std=2.0)
    assert (upper.dropna() >= mid.dropna()).all()
    assert (lower.dropna() <= mid.dropna()).all()


def test_atr_rises_with_bigger_ranges():
    high = pd.Series([101] * 30 + [110] * 20)
    low = pd.Series([99] * 30 + [90] * 20)
    close = pd.Series([100] * 30 + [100] * 20)
    a = ind.atr(high, low, close, window=14)
    assert a.iloc[-1] > a.iloc[29]


# ---------------------------------------------------------------------
# Archetype behavior on purpose-built price paths
# ---------------------------------------------------------------------
def test_trend_follower_goes_long_in_a_clean_uptrend():
    bars = pd.DataFrame({"Close": np.linspace(100, 160, 80)})
    bot = TrendFollowerBot()
    signal = bot.generate_signal(bars)
    assert signal.action == "long"


def test_trend_follower_goes_short_in_a_clean_downtrend():
    bars = pd.DataFrame({"Close": np.linspace(160, 100, 80)})
    bot = TrendFollowerBot()
    signal = bot.generate_signal(bars)
    assert signal.action == "short"


def test_trend_follower_flat_when_not_enough_history():
    bars = pd.DataFrame({"Close": np.linspace(100, 110, 5)})
    bot = TrendFollowerBot()
    signal = bot.generate_signal(bars)
    assert signal.action == "flat"
    assert "warming up" in signal.reason


def test_mean_reversion_goes_long_at_the_lower_band():
    close = np.concatenate([np.full(25, 100.0), [100 - i * 0.3 for i in range(1, 8)]])
    close[-1] = close[-2] - 3.5  # sharp poke below the lower band
    bars = pd.DataFrame({"Close": close})
    bot = MeanReversionBot()
    signal = bot.generate_signal(bars)
    assert signal.action == "long"


def test_mean_reversion_flat_inside_the_bands():
    close = np.full(40, 100.0) + np.sin(np.linspace(0, 3, 40)) * 0.2
    bars = pd.DataFrame({"Close": close})
    bot = MeanReversionBot()
    signal = bot.generate_signal(bars)
    assert signal.action == "flat"


def test_breakout_bot_goes_long_on_a_volatility_spike_above_range():
    n = 40
    close = list(np.full(n, 100.0) + np.random.default_rng(0).normal(0, 0.05, n))
    high = [c + 0.1 for c in close]
    low = [c - 0.1 for c in close]
    # sudden wide-range spike bar breaking above the recent range
    close.append(110)
    high.append(111)
    low.append(103)
    bars = pd.DataFrame({"Close": close, "High": high, "Low": low})
    bot = BreakoutBot(params={"channel_window": 20, "atr_window": 14, "volatility_multiplier": 1.5})
    signal = bot.generate_signal(bars)
    assert signal.action == "long"


def test_breakout_bot_flat_in_a_quiet_range():
    n = 45
    rng = np.random.default_rng(2)
    close = list(100 + rng.normal(0, 0.05, n))
    high = [c + 0.1 for c in close]
    low = [c - 0.1 for c in close]
    bars = pd.DataFrame({"Close": close, "High": high, "Low": low})
    bot = BreakoutBot()
    signal = bot.generate_signal(bars)
    assert signal.action == "flat"


# ---------------------------------------------------------------------
# Replication
# ---------------------------------------------------------------------
def test_clone_and_mutate_stays_same_archetype_and_class():
    master = TrendFollowerBot()
    child = master.clone_and_mutate(mutation_rate_pct=100, generation=1)
    assert isinstance(child, TrendFollowerBot)
    assert child.archetype == "trend_follower"
    assert child.parent_id == master.id
    assert child.generation_born == 1


def test_clone_and_mutate_respects_param_bounds():
    master = TrendFollowerBot(params={"fast_window": 3, "slow_window": 120, "momentum_window": 5})
    for _ in range(50):
        child = master.clone_and_mutate(mutation_rate_pct=100, generation=1)
        lo, hi = master.param_bounds["fast_window"]
        assert lo <= child.params["fast_window"] <= hi
        lo, hi = master.param_bounds["slow_window"]
        assert lo <= child.params["slow_window"] <= hi


def test_zero_mutation_rate_produces_identical_params():
    master = MeanReversionBot()
    child = master.clone_and_mutate(mutation_rate_pct=0, generation=1)
    assert child.params == master.params


def test_any_positive_mutation_rate_guarantees_at_least_one_param_differs():
    # Applying mutation_rate_pct independently per parameter means a
    # low rate can roll "no mutation" on every parameter — clone_and_mutate
    # must catch that and force at least one real change instead of
    # silently handing back a duplicate.
    for cls in (TrendFollowerBot, MeanReversionBot, BreakoutBot):
        master = cls()
        rng = random.Random(1)
        for _ in range(200):
            child = master.clone_and_mutate(mutation_rate_pct=5, generation=1, rng=rng)
            assert child.params != master.params, f"{cls.__name__} produced an exact duplicate at a nonzero mutation rate"


def test_mutation_delta_pct_is_zero_for_identical_params_and_positive_after_mutation():
    master = TrendFollowerBot()
    identical_child = master.clone_and_mutate(mutation_rate_pct=0, generation=1)
    assert master.mutation_delta_pct(identical_child) == 0.0

    rng = random.Random(2)
    mutated_child = master.clone_and_mutate(mutation_rate_pct=100, generation=1, rng=rng)
    assert master.mutation_delta_pct(mutated_child) > 0.0


# ---------------------------------------------------------------------
# Market + backtest wiring
# ---------------------------------------------------------------------
def test_synthetic_ohlc_shape_and_bounds():
    df = synthetic_ohlc(n_bars=200, seed=1)
    assert len(df) == 200
    assert (df["High"] >= df["Low"]).all()
    assert (df["High"] >= df["Close"]).all()
    assert (df["Low"] <= df["Close"]).all()


def test_build_population_creates_master_plus_children():
    config = SupervisorConfig(starting_capital=10_000)
    engine, bots = build_population(config, children_per_archetype=4, seed=0)
    # 3 archetypes * (1 master + 4 children) = 15
    assert len(bots) == 15
    assert len(engine.active) == 15
    archetypes = {b.archetype for b in bots.values()}
    assert archetypes == {"trend_follower", "mean_reversion", "breakout"}


def test_run_backtest_produces_full_length_equity_curves():
    config = SupervisorConfig(starting_capital=10_000, hard_deletion_threshold=40, inactivity_timeout=10)
    result = run_backtest_on_synthetic_market(config, n_bars=150, children_per_archetype=2, price_seed=3, population_seed=1)

    assert len(result.price) == 150
    for curve in result.equity_curves.values():
        assert len(curve) == 150
    assert len(result.total_equity) == 150
    # every bot ends up either still active or in the graveyard, never both
    all_ids = set(result.archetypes.keys())
    assert set(result.engine.active.keys()) <= all_ids
    assert {a.id for a in result.engine.graveyard} <= all_ids


def test_run_backtest_is_deterministic_given_same_seeds():
    config = SupervisorConfig(starting_capital=10_000)
    r1 = run_backtest_on_synthetic_market(config, n_bars=100, children_per_archetype=2, price_seed=5, population_seed=2)
    r2 = run_backtest_on_synthetic_market(config, n_bars=100, children_per_archetype=2, price_seed=5, population_seed=2)
    assert r1.total_equity == r2.total_equity
