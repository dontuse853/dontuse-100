"""
Plain pandas/numpy implementations of the handful of technical
indicators the bot archetypes use. No external TA library required.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    """Simple moving average."""
    return series.rolling(window, min_periods=window).mean()


def ema(series: pd.Series, span: int) -> pd.Series:
    """Exponential moving average."""
    return series.ewm(span=span, adjust=False).mean()


def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    """Wilder's Relative Strength Index, 0-100. Neutral (50) wherever
    there isn't enough history or there's been no movement at all."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    value = 100 - (100 / (1 + rs))

    # avg_loss == 0 because it's a pure uptrend (no losses at all) means
    # maximum strength, not "no data" — that's RSI 100, not a neutral 50.
    all_gains_no_losses = (avg_loss == 0) & (avg_gain > 0)
    value = value.where(~all_gains_no_losses, 100.0)

    # Truly flat (no gains and no losses) is the only case that's
    # actually undefined/neutral.
    perfectly_flat = (avg_loss == 0) & (avg_gain == 0)
    value = value.where(~perfectly_flat, 50.0)

    return value.fillna(50.0)


def bollinger_bands(series: pd.Series, window: int = 20, num_std: float = 2.0):
    """Returns (middle, upper, lower) bands. Middle is a plain SMA;
    upper/lower are `num_std` rolling standard deviations from it."""
    mid = sma(series, window)
    std = series.rolling(window, min_periods=window).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return mid, upper, lower


def atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    """Average True Range — Wilder-smoothed. Measures how much a bar
    typically moves, so a rising ATR flags expanding volatility."""
    prev_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()


def donchian_channel(high: pd.Series, low: pd.Series, window: int = 20):
    """Returns (upper, lower): the rolling highest-high and lowest-low
    over `window` bars — the classic breakout channel."""
    upper = high.rolling(window, min_periods=window).max()
    lower = low.rolling(window, min_periods=window).min()
    return upper, lower
