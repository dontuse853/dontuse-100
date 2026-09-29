"""
Downloads real historical daily data for a benchmark (SPY by default)
and runs the same core backtest loop against it that demo_bots.py runs
against the synthetic market.

    python demo_real_data.py
    python demo_real_data.py --ticker BTC --period 2y
    python demo_real_data.py --ticker SPY --start 2022-01-01 --end 2024-01-01

This makes a real network call to Yahoo Finance via yfinance. If that
network isn't reachable from wherever you're running this (a sandboxed
CI box, an offline machine, a locked-down container), the download
raises a clear RuntimeError explaining why rather than silently
falling back to fake data — see engine/data.py for why that matters
for anything with "finance" in the name.
"""

import argparse

from engine.backtest import run_backtest_on_ticker
from engine.supervisor import SupervisorConfig


def run_demo(ticker: str, start: str | None, end: str | None, period: str | None):
    config = SupervisorConfig(
        starting_capital=10_000,
        hard_deletion_threshold=40,
        inactivity_timeout=20,
        mutation_rate=15,
        base_position_size_pct=10.0,
    )

    window = f"period={period}" if period else f"{start} -> {end or 'today'}"
    print(f"Downloading {ticker} ({window}) ...")

    result = run_backtest_on_ticker(
        config,
        ticker,
        start=start,
        end=end,
        period=period,
        children_per_archetype=5,
        population_seed=1,
        bars_per_generation=15,  # daily bars: ~3 trading weeks per "generation"
    )

    print(f"Got {len(result.price)} daily bars, "
          f"{result.price.index[0].date()} -> {result.price.index[-1].date()}\n")

    by_archetype: dict[str, list[str]] = {}
    for bot_id, archetype in result.archetypes.items():
        by_archetype.setdefault(archetype, []).append(bot_id)

    for archetype, bot_ids in by_archetype.items():
        finals = [result.equity_curves[b][-1] for b in bot_ids]
        avg_pnl = (sum(finals) / len(finals) / config.starting_capital - 1) * 100
        alive = sum(1 for b in bot_ids if b in result.engine.active)
        print(f"{archetype:>15}: avg P&L {avg_pnl:+6.1f}%   {alive}/{len(bot_ids)} still alive")

    total_start = config.starting_capital * len(result.archetypes)
    total_final = result.total_equity[-1]
    print(f"\nEcosystem total: ${total_start:,.0f} -> ${total_final:,.0f} "
          f"({(total_final / total_start - 1) * 100:+.1f}%)")
    print(f"Trades executed: {len(result.trade_log)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", default="SPY", help="Benchmark name or ticker, e.g. SPY, BTC, QQQ, or any yfinance symbol")
    parser.add_argument("--start", default=None, help="YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="YYYY-MM-DD (defaults to today)")
    parser.add_argument("--period", default=None, help="Relative window instead of start/end, e.g. 6mo, 1y, 2y, 5y, max")
    args = parser.parse_args()

    if not args.period and not args.start:
        args.period = "2y"  # sensible default time frame

    run_demo(args.ticker, args.start, args.end, args.period)
