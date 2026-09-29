"""
Run this to see the three master templates (and their mutated children)
trade a synthetic, regime-switching market end to end through the
supervisor engine — no dashboard required.

    python demo_bots.py
"""

from engine.backtest import run_backtest_on_synthetic_market
from engine.supervisor import SupervisorConfig


def run_demo():
    # NOTE on inactivity_timeout here: the breakout archetype is built to
    # sit out anything that isn't a genuine volatility spike, and this
    # synthetic market only delivers one late in the run. Too tight an
    # inactivity budget kills every breakout bot before it ever sees its
    # own regime — that's the same trade-off a real inactivity_timeout
    # setting forces you to make: patience vs. risk of stagnating.
    config = SupervisorConfig(
        starting_capital=10_000,
        hard_deletion_threshold=40,
        inactivity_timeout=20,
        mutation_rate=15,
        base_position_size_pct=10.0,
    )

    result = run_backtest_on_synthetic_market(
        config,
        n_bars=420,
        children_per_archetype=5,
        price_seed=7,
        population_seed=1,
        bars_per_generation=20,
    )

    print(f"Simulated {len(result.price)} bars across three regimes: "
          f"trending -> choppy/range-bound -> squeeze + volatility spike.\n")

    by_archetype = {}
    for bot_id, archetype in result.archetypes.items():
        by_archetype.setdefault(archetype, []).append(bot_id)

    for archetype, bot_ids in by_archetype.items():
        print(f"=== {archetype} ({len(bot_ids)} bots) ===")
        for bot_id in bot_ids:
            final_capital = result.equity_curves[bot_id][-1]
            pnl_pct = (final_capital / config.starting_capital - 1) * 100
            agent = result.engine.active.get(bot_id)
            if agent is not None:
                status = "🟢 alive"
            else:
                dead = next(a for a in result.engine.graveyard if a.id == bot_id)
                status = f"🔴 dead ({dead.cause_of_death}, gen {dead.death_generation})"
            print(f"   {bot_id:<22} final=${final_capital:>9,.0f}  pnl={pnl_pct:+7.1f}%  {status}")
        print()

    total_final = result.total_equity[-1]
    total_start = config.starting_capital * len(result.archetypes)
    print(f"Population total: ${total_start:,.0f} -> ${total_final:,.0f} "
          f"({(total_final / total_start - 1) * 100:+.1f}%)")
    print(f"Alive: {len(result.engine.active)}   Purged: {len(result.engine.graveyard)}")


if __name__ == "__main__":
    run_demo()
