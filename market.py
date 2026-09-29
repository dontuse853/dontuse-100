"""
Synthetic OHLC price generator — NOT real market data, and not
connected to any brokerage or data feed. It exists purely so the bot
archetypes have something to run against in a demo/backtest: a
regime-switching random walk that spends time trending, then chopping
sideways, then squeezing and spiking, so each archetype gets a stretch
of price action suited to what it's designed to trade.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def synthetic_ohlc(n_bars: int = 420, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = [100.0]

    trend_bars = int(n_bars * 0.40)
    chop_bars = int(n_bars * 0.35)
    breakout_bars = n_bars - trend_bars - chop_bars

    # Phase 1 — trending: steady drift, direction flips partway through.
    # Favors a moving-average crossover strategy.
    for i in range(trend_bars):
        drift = 0.0022 if i < trend_bars * 0.55 else -0.0016
        close.append(close[-1] * (1 + drift + rng.normal(0, 0.006)))

    # Phase 2 — choppy / range-bound: mean-reverts around a level.
    # Favors a Bollinger/RSI mean-reversion strategy.
    level = close[-1]
    for _ in range(chop_bars):
        pull = (level - close[-1]) * 0.12
        close.append(close[-1] + pull + rng.normal(0, level * 0.006))

    # Phase 3 — quiet squeeze, then a sharp directional spike.
    # Favors a volatility-breakout strategy.
    squeeze_bars = int(breakout_bars * 0.6)
    spike_bars = breakout_bars - squeeze_bars
    for _ in range(squeeze_bars):
        close.append(close[-1] * (1 + rng.normal(0, 0.0015)))
    spike_dir = 1 if rng.random() > 0.5 else -1
    for i in range(spike_bars):
        shock = spike_dir * 0.02 * np.exp(-i / max(spike_bars * 0.4, 1))
        close.append(close[-1] * (1 + shock + rng.normal(0, 0.01)))

    close = np.array(close[1:])  # drop the seed value -> length == n_bars

    open_ = np.roll(close, 1)
    open_[0] = close[0]
    intrabar_noise = np.abs(rng.normal(0, close * 0.004))
    high = np.maximum(open_, close) + intrabar_noise
    low = np.minimum(open_, close) - intrabar_noise

    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close})
