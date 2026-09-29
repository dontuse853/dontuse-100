"""
The core historical backtesting loop.

`run_backtest()` is data-source-agnostic: hand it any OHLC DataFrame
with Open/High/Low/Close columns — synthetic (engine/market.py) or
real historical data (engine/data.py) — and it feeds that data bar by
bar to every currently active agent simultaneously, through the real
supervisor engine (engine/supervisor.py):

  * every active agent gets a signal computed for the current bar
  * each executed trade's P&L is calculated and applied to that
    agent's capital, and logged to `trade_log`
  * the supervisor manages the outcome — survival-scaled position
    sizing, the inactivity countdown, and the deletion sequence
  * each agent's own capital history is recorded as its individual
    equity line (`equity_curves`)
  * summing every agent's equity at each bar gives the cumulative
    ecosystem equity curve (`total_equity`) — the whole population's
    combined performance over time, dead bots included (they just
    stop contributing further gains or losses once purged)

`run_backtest_on_synthetic_market()` and `run_backtest_on_ticker()` are
thin convenience wrappers around the same core loop for the two data
sources this project ships with.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from .bots import BotTemplate, MASTER_TEMPLATES
from .data import DateLike, download_price_history
from .market import synthetic_ohlc
from .supervisor import SupervisorConfig, SupervisorEngine


@dataclass
class BacktestResult:
    price: pd.DataFrame
    equity_curves: dict               # bot_id -> list[float], one individual equity line per agent, length == n_bars
    archetypes: dict                  # bot_id -> archetype name
    engine: SupervisorEngine
    total_equity: list                 # the cumulative ecosystem equity curve: sum of every agent's equity at each bar
    bots: dict = field(default_factory=dict)         # bot_id -> BotTemplate (params, parent_id, mutation_delta_pct, ...)
    trade_log: list = field(default_factory=list)   # every executed trade, in order


def build_population(
    config: SupervisorConfig,
    children_per_archetype: int = 5,
    seed: int = 0,
) -> tuple[SupervisorEngine, dict[str, BotTemplate]]:
    """Spawn the three master templates plus `children_per_archetype`
    mutated children of each, registering all of them with a fresh
    SupervisorEngine."""
    rng = random.Random(seed)
    engine = SupervisorEngine(config)
    bots: dict[str, BotTemplate] = {}

    for cls in MASTER_TEMPLATES.values():
        master = cls(generation_born=0)
        engine.spawn(master.id, generation=0, base_position_size_pct=config.base_position_size_pct)
        bots[master.id] = master

        for _ in range(children_per_archetype):
            child = master.clone_and_mutate(config.mutation_rate, generation=0, rng=rng)
            engine.spawn(child.id, generation=0, base_position_size_pct=config.base_position_size_pct)
            bots[child.id] = child

    return engine, bots


def run_backtest(
    config: SupervisorConfig,
    price: pd.DataFrame,
    children_per_archetype: int = 5,
    population_seed: int = 0,
    bars_per_generation: int = 20,
) -> BacktestResult:
    """
    The core loop. `price` must have Open/High/Low/Close columns — any
    length, any index (integer bars or real dates), synthetic or real.

    `bars_per_generation` is what turns raw price bars into the
    "generations" the supervisor's `inactivity_timeout` counts in. P&L
    still compounds bar by bar (a bot in a live position isn't frozen
    between generation boundaries), but a bot is only judged on
    inactivity — and only swept by the deletion sequence — once per
    block of this many bars. Without this, a deliberately selective
    strategy (mean reversion, breakout) would get punished for sitting
    out a handful of individual bars while it waits for a real setup,
    which isn't what "inactivity" is meant to catch.
    """
    required_cols = {"Open", "High", "Low", "Close"}
    missing = required_cols - set(price.columns)
    if missing:
        raise ValueError(f"price is missing required column(s): {sorted(missing)}")

    n_bars = len(price)
    if n_bars < 2:
        raise ValueError(f"price needs at least 2 bars, got {n_bars}")

    engine, bots = build_population(config, children_per_archetype, population_seed)

    # One vectorized pass per bot instead of recomputing indicators
    # from scratch on every bar — see BotTemplate.precompute in bots.py.
    precomputed = {bid: bot.precompute(price) for bid, bot in bots.items()}
    close_values = price["Close"].to_numpy()
    dates = price.index

    equity_curves = {bid: [config.starting_capital] for bid in bots}
    last_known_capital = {bid: config.starting_capital for bid in bots}
    traded_this_generation = {bid: False for bid in bots}
    trade_log: list[dict] = []
    generation = 0

    for step in range(1, n_bars):
        i = step - 1  # index of the most recently completed bar
        next_return = close_values[step] / close_values[i] - 1

        for bot_id in list(engine.active.keys()):
            bot = bots[bot_id]
            if i + 1 < bot.warmup_bars:
                continue  # not enough history yet — not "inactive", just not born as a trader yet

            agent = engine.active[bot_id]
            signal = bot._signal_at(i, precomputed[bot_id])
            traded = signal.action in ("long", "short")

            if traded:
                direction = 1 if signal.action == "long" else -1
                risk_pct = engine.scaled_position_size_pct(agent) / 100
                pnl = agent.capital * risk_pct * signal.strength * direction * next_return
                agent.capital = max(0.0, agent.capital + pnl)
                traded_this_generation[bot_id] = True

                trade_log.append({
                    "step": step,
                    "date": dates[step],
                    "bot_id": bot_id,
                    "archetype": bot.archetype,
                    "action": signal.action,
                    "strength": round(signal.strength, 3),
                    "reason": signal.reason,
                    "position_size_pct": round(risk_pct * 100, 3),
                    "pnl_dollars": round(pnl, 2),
                    "capital_after": round(agent.capital, 2),
                })

        is_generation_boundary = (step % bars_per_generation == 0) or (step == n_bars - 1)
        if is_generation_boundary:
            generation += 1
            for bot_id, agent in list(engine.active.items()):
                engine.record_tick(agent, traded=traded_this_generation[bot_id])
                traded_this_generation[bot_id] = False
            engine.run_deletion_sequence(generation=generation)
            engine.advance_generation()

        for bot_id in bots:
            if bot_id in engine.active:
                last_known_capital[bot_id] = engine.active[bot_id].capital
            equity_curves[bot_id].append(last_known_capital[bot_id])

    # The cumulative ecosystem equity curve: every agent's individual
    # equity line, summed at each bar.
    total_equity = [
        sum(equity_curves[bid][t] for bid in bots) for t in range(n_bars)
    ]

    return BacktestResult(
        price=price,
        equity_curves=equity_curves,
        archetypes={bid: bot.archetype for bid, bot in bots.items()},
        engine=engine,
        total_equity=total_equity,
        bots=bots,
        trade_log=trade_log,
    )


# ---------------------------------------------------------------------------
# Convenience wrappers — same core loop, two data sources.
# ---------------------------------------------------------------------------
def run_backtest_on_synthetic_market(
    config: SupervisorConfig,
    n_bars: int = 420,
    price_seed: int = 7,
    children_per_archetype: int = 5,
    population_seed: int = 0,
    bars_per_generation: int = 20,
) -> BacktestResult:
    """Run the core loop against the synthetic, regime-switching market
    from engine/market.py — no network, no real data, purely for demos
    and testing."""
    price = synthetic_ohlc(n_bars=n_bars, seed=price_seed)
    return run_backtest(config, price, children_per_archetype, population_seed, bars_per_generation)


def run_backtest_on_ticker(
    config: SupervisorConfig,
    ticker: str,
    start: Optional[DateLike] = None,
    end: Optional[DateLike] = None,
    period: Optional[str] = None,
    interval: str = "1d",
    children_per_archetype: int = 5,
    population_seed: int = 0,
    bars_per_generation: int = 20,
) -> BacktestResult:
    """Download real historical data for `ticker` (a friendly benchmark
    name like "SPY"/"BTC" or any ticker yfinance recognizes) and run
    the same core loop against it. See engine.data.download_price_history
    for how to specify the time frame (`start`/`end` or `period`)."""
    price = download_price_history(ticker, start=start, end=end, period=period, interval=interval)
    return run_backtest(config, price, children_per_archetype, population_seed, bars_per_generation)
