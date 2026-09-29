"""
Darwin Desk — bot archetypes ("master templates").

Each class here is a *strategy*, not a lifecycle manager — capital,
position sizing, and death are the supervisor engine's job
(`engine/supervisor.py`). A bot only answers one question every time
it's handed a fresh price bar: given everything printed so far, do I
want to be long, short, or flat right now?

The three master templates below (`TrendFollowerBot`, `MeanReversionBot`,
`BreakoutBot`) are the "generation zero" bots. `clone_and_mutate()` is
how any of them — master or descendant — produces a child: same
archetype, same logic, parameters nudged at random by up to the
configured mutation rate. That's the replication mechanism the rest of
the population grows from.

Performance note: each archetype implements its indicator math twice
in spirit but once in code — `precompute()` computes every indicator
series it needs *vectorized* over an entire price history in one pass,
and `_signal_at(i, ...)` just reads values out of that at position i.
`generate_signal(bars)` (used by the tests and the standalone demo) is
a convenience wrapper that precomputes over whatever `bars` it's given
and reads the last position — simple, but O(bars) per call. A backtest
looping over hundreds of bars for dozens of bots should call
`precompute()` once per bot and `_signal_at()` per step instead;
`engine/backtest.py` does exactly that.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from . import indicators as ind


@dataclass
class Signal:
    """What a bot wants to do on its next bar."""

    action: str = "flat"     # "long" | "short" | "flat"
    strength: float = 0.0    # 0..1 conviction — scales position size on top of survival scaling
    reason: str = ""         # human-readable justification, handy for logging/debugging


class BotTemplate:
    """Base class every archetype implements."""

    archetype: str = "base"
    default_params: dict = {}
    # (min, max) bounds per param so mutation can't wander somewhere
    # nonsensical, like a 2-bar slow moving average.
    param_bounds: dict = {}

    def __init__(
        self,
        params: Optional[dict] = None,
        bot_id: Optional[str] = None,
        generation_born: int = 0,
        parent_id: Optional[str] = None,
    ):
        self.params = {**self.default_params, **(params or {})}
        self.id = bot_id or f"{self.archetype}-{uuid.uuid4().hex[:6]}"
        self.generation_born = generation_born
        self.parent_id = parent_id

    # -- to override -------------------------------------------------------
    def precompute(self, bars: pd.DataFrame) -> dict:
        """Compute every indicator series this archetype needs, once,
        vectorized over the full `bars` history (oldest first). Returns
        a dict of numpy arrays aligned to `bars`' index, for `_signal_at`
        to read by position."""
        raise NotImplementedError

    def _signal_at(self, i: int, pre: dict) -> Signal:
        """Build a Signal using only information available up to and
        including position i, reading from `pre` (the dict `precompute`
        returned). Must not look at index > i."""
        raise NotImplementedError

    @property
    def warmup_bars(self) -> int:
        """How many bars of history this bot needs before its indicators
        are meaningful. Subclasses compute this from their own params."""
        return 1

    # -- convenience one-shot API --------------------------------------
    def generate_signal(self, bars: pd.DataFrame) -> Signal:
        """`bars` is every bar printed so far (oldest first), including
        the newest one that just came in. Precomputes over `bars` and
        returns the signal as of the most recent bar — fine for tests
        and small runs. For a long backtest, call `precompute()` once
        and `_signal_at()` per step instead (see module docstring)."""
        if len(bars) < self.warmup_bars:
            return Signal("flat", 0.0, "warming up")
        pre = self.precompute(bars)
        return self._signal_at(len(bars) - 1, pre)

    # -- replication -------------------------------------------------------
    def _mutate_value(self, key: str, value, rng: random.Random, force_change: bool = False):
        """Nudge one parameter by up to ±35%, clamped to its bounds. With
        `force_change`, retries a few times to avoid landing back on the
        exact original value (only matters for a parameter pinned near
        its bound, where a small jitter can round-trip to the same
        number)."""
        lo, hi = self.param_bounds.get(key, (None, None))
        attempts = 8 if force_change else 1
        new_value = value
        for _ in range(attempts):
            jitter = value * rng.uniform(-0.35, 0.35) if value else rng.uniform(-1, 1)
            new_value = value + jitter
            if lo is not None:
                new_value = max(lo, new_value)
            if hi is not None:
                new_value = min(hi, new_value)
            if isinstance(value, int):
                new_value = int(round(new_value))
            if not force_change or new_value != value:
                break
        return new_value

    def clone_and_mutate(
        self,
        mutation_rate_pct: float,
        generation: int,
        rng: Optional[random.Random] = None,
    ) -> "BotTemplate":
        """Produce a child of the same archetype. Each parameter has an
        independent `mutation_rate_pct` chance of being nudged by up to
        ±35%; everything else is copied straight from the parent.

        Applying that chance independently per parameter means a child
        can easily roll "no mutation" on every single parameter — at a
        mutation rate of 12% with 3-5 params, that happens to roughly
        half of all "children". A clone with parameters identical to
        its parent isn't variation, it's just a duplicate wearing a new
        ID, so if every independent roll comes up empty, one parameter
        is mutated anyway. Every clone this method returns is
        guaranteed to differ from its parent by at least one parameter
        (bounds permitting) — *unless* `mutation_rate_pct` is exactly
        0, which stays a genuine off-switch: no mutation at all, ever.
        """
        rng = rng or random.Random()
        keys = list(self.params.keys())
        child_params = {}
        any_mutated = False

        for key in keys:
            value = self.params[key]
            if rng.random() * 100 < mutation_rate_pct:
                new_value = self._mutate_value(key, value, rng)
                child_params[key] = new_value
                # A small jitter can round right back to the original
                # value (especially for an integer parameter) — that's
                # a "mutation" that changed nothing, so it shouldn't
                # count as having produced real variation.
                if new_value != value:
                    any_mutated = True
            else:
                child_params[key] = value

        if not any_mutated and mutation_rate_pct > 0:
            forced_key = rng.choice(keys)
            child_params[forced_key] = self._mutate_value(
                forced_key, self.params[forced_key], rng, force_change=True
            )

        return self.__class__(
            params=child_params,
            generation_born=generation,
            parent_id=self.id,
        )

    def mutation_delta_pct(self, other: "BotTemplate") -> float:
        """Average absolute % difference between this bot's parameters
        and `other`'s (same archetype assumed) — a rough "how different
        is this clone from its parent" number, handy for display."""
        diffs = []
        for key, value in self.params.items():
            other_value = other.params.get(key, value)
            if value:
                diffs.append(abs(other_value - value) / abs(value))
            elif other_value:
                diffs.append(1.0)
        return float(np.mean(diffs) * 100) if diffs else 0.0


def _nan_safe(*values) -> bool:
    """True if any value is NaN (i.e. still inside indicator warmup)."""
    return any(pd.isna(v) for v in values)


# ---------------------------------------------------------------------------
# Archetype 1 — Trend follower
# ---------------------------------------------------------------------------
class TrendFollowerBot(BotTemplate):
    """Rides sustained directional moves. Reads every past bar plus the
    newest incoming one each call, and takes a position only when a
    fast/slow EMA crossover and simple momentum both agree on direction
    — built for trending markets, not chop."""

    archetype = "trend_follower"
    default_params = {
        "fast_window": 10,
        "slow_window": 40,
        "momentum_window": 20,
    }
    param_bounds = {
        "fast_window": (3, 30),
        "slow_window": (15, 120),
        "momentum_window": (5, 60),
    }

    @property
    def warmup_bars(self) -> int:
        p = self.params
        return max(p["slow_window"], p["momentum_window"]) + 1

    def precompute(self, bars: pd.DataFrame) -> dict:
        close = bars["Close"]
        fast = ind.ema(close, self.params["fast_window"])
        slow = ind.ema(close, self.params["slow_window"])
        momentum = close / close.shift(self.params["momentum_window"]) - 1
        return {
            "fast": fast.to_numpy(),
            "slow": slow.to_numpy(),
            "momentum": momentum.to_numpy(),
        }

    def _signal_at(self, i: int, pre: dict) -> Signal:
        fast_val, slow_val, momentum_val = pre["fast"][i], pre["slow"][i], pre["momentum"][i]
        if _nan_safe(fast_val, slow_val, momentum_val):
            return Signal("flat", 0.0, "warming up")

        spread = (fast_val - slow_val) / slow_val if slow_val else 0.0
        strength = float(np.clip(abs(spread) * 25, 0, 1))

        if fast_val > slow_val and momentum_val > 0:
            return Signal("long", strength, f"fast EMA above slow EMA, momentum {momentum_val:+.1%}")
        if fast_val < slow_val and momentum_val < 0:
            return Signal("short", strength, f"fast EMA below slow EMA, momentum {momentum_val:+.1%}")
        return Signal("flat", 0.0, "no aligned trend")


# ---------------------------------------------------------------------------
# Archetype 2 — Mean reversion
# ---------------------------------------------------------------------------
class MeanReversionBot(BotTemplate):
    """Built for range-bound, choppy markets: fades price back toward
    the mean using Bollinger Bands, confirmed by RSI, rather than
    chasing a direction. Sits out anything inside the bands."""

    archetype = "mean_reversion"
    default_params = {
        "bb_window": 20,
        "bb_std": 2.0,
        "rsi_window": 14,
        "rsi_oversold": 30.0,
        "rsi_overbought": 70.0,
    }
    param_bounds = {
        "bb_window": (10, 60),
        "bb_std": (1.0, 3.5),
        "rsi_window": (5, 30),
        "rsi_oversold": (10.0, 40.0),
        "rsi_overbought": (60.0, 90.0),
    }

    @property
    def warmup_bars(self) -> int:
        p = self.params
        return max(p["bb_window"], p["rsi_window"]) + 1

    def precompute(self, bars: pd.DataFrame) -> dict:
        close = bars["Close"]
        _, upper, lower = ind.bollinger_bands(close, self.params["bb_window"], self.params["bb_std"])
        rsi_series = ind.rsi(close, self.params["rsi_window"])
        return {
            "close": close.to_numpy(),
            "upper": upper.to_numpy(),
            "lower": lower.to_numpy(),
            "rsi": rsi_series.to_numpy(),
        }

    def _signal_at(self, i: int, pre: dict) -> Signal:
        price, upper_val, lower_val, rsi_val = pre["close"][i], pre["upper"][i], pre["lower"][i], pre["rsi"][i]
        if _nan_safe(price, upper_val, lower_val, rsi_val):
            return Signal("flat", 0.0, "warming up")

        band_width = (upper_val - lower_val) or 1e-9

        if price <= lower_val and rsi_val <= self.params["rsi_oversold"]:
            depth = (lower_val - price) / band_width
            strength = float(np.clip(0.5 + depth, 0, 1))
            return Signal("long", strength, f"price under lower band, RSI {rsi_val:.0f} oversold")

        if price >= upper_val and rsi_val >= self.params["rsi_overbought"]:
            depth = (price - upper_val) / band_width
            strength = float(np.clip(0.5 + depth, 0, 1))
            return Signal("short", strength, f"price over upper band, RSI {rsi_val:.0f} overbought")

        return Signal("flat", 0.0, "inside bands, no edge")


# ---------------------------------------------------------------------------
# Archetype 3 — Breakout
# ---------------------------------------------------------------------------
class BreakoutBot(BotTemplate):
    """Sits out quiet markets and swings hard the moment volatility
    expands past its own recent norm *and* price clears its recent
    range — built to capture sudden, news-driven spikes rather than
    grind out small edges."""

    archetype = "breakout"
    default_params = {
        "channel_window": 20,
        "atr_window": 14,
        "volatility_multiplier": 1.5,
    }
    param_bounds = {
        "channel_window": (10, 60),
        "atr_window": (7, 30),
        "volatility_multiplier": (1.1, 3.0),
    }

    @property
    def warmup_bars(self) -> int:
        p = self.params
        return max(p["channel_window"], p["atr_window"]) + 10

    def precompute(self, bars: pd.DataFrame) -> dict:
        high, low, close = bars["High"], bars["Low"], bars["Close"]
        upper, lower = ind.donchian_channel(high, low, self.params["channel_window"])
        atr_series = ind.atr(high, low, close, self.params["atr_window"])
        # Rolling mean of ATR over the bot's own warmup window, computed
        # as of the *prior* bar — the "recent normal" volatility level
        # the current bar's ATR gets compared against.
        baseline_atr = atr_series.rolling(self.warmup_bars, min_periods=1).mean().shift(1)
        return {
            "close": close.to_numpy(),
            "upper": upper.to_numpy(),
            "lower": lower.to_numpy(),
            "atr": atr_series.to_numpy(),
            "baseline_atr": baseline_atr.to_numpy(),
        }

    def _signal_at(self, i: int, pre: dict) -> Signal:
        if i < 2:
            return Signal("flat", 0.0, "warming up")

        price = pre["close"][i]
        current_atr = pre["atr"][i]
        baseline_atr = pre["baseline_atr"][i]
        prior_upper = pre["upper"][i - 1]
        prior_lower = pre["lower"][i - 1]

        if _nan_safe(price, current_atr, baseline_atr, prior_upper, prior_lower):
            return Signal("flat", 0.0, "warming up")

        expansion = current_atr / baseline_atr if baseline_atr else 1.0
        is_spike = expansion >= self.params["volatility_multiplier"]
        strength = float(np.clip((expansion - 1) / 2, 0, 1))

        if is_spike and price >= prior_upper:
            return Signal("long", strength, f"{self.params['channel_window']}-bar high broken on a {expansion:.1f}x volatility spike")
        if is_spike and price <= prior_lower:
            return Signal("short", strength, f"{self.params['channel_window']}-bar low broken on a {expansion:.1f}x volatility spike")
        return Signal("flat", 0.0, "no breakout / volatility normal")


MASTER_TEMPLATES = {
    "trend_follower": TrendFollowerBot,
    "mean_reversion": MeanReversionBot,
    "breakout": BreakoutBot,
}
