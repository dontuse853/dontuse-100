"""
Run this to watch the supervisor engine work on a sample population,
generation by generation. There's still no real trading strategy here
— capital moves are randomized — but the population is deliberately
mixed so you can see all three jobs fire:

  * bot-2000 ("reckless")  ignores survival scaling and always trades
    at its full, unscaled base size — showing why the scaling exists
    by blowing through the hard deletion threshold faster than anyone
    who respects it.
  * bot-3000 ("dormant")   never trades at all — showing the
    inactivity countdown run all the way to zero and trigger a purge
    for the *other* reason a bot can die.
  * bot-1000..1004         trade normally and size their positions off
    `scaled_position_size_pct`, so you can compare their survival odds
    against the reckless one under the same market noise.

    python demo_supervisor.py
"""

import random

from engine.supervisor import SupervisorConfig, SupervisorEngine

random.seed(8)


def log_death(agent, reason):
    label = "💀 CAPITAL" if reason == "hard_deletion_threshold" else "⏳ INACTIVITY"
    print(f"   {label} — {agent.id} purged (final capital ${agent.capital:,.0f}, "
          f"survived {agent.generations_survived} generations)")


def run_demo(generations: int = 12, normal_bots: int = 5):
    config = SupervisorConfig(
        starting_capital=10_000,
        hard_deletion_threshold=40,
        inactivity_timeout=4,
        survival_curve_exponent=2.0,
        min_survival_factor=0.05,
        base_position_size_pct=10.0,
    )
    engine = SupervisorEngine(config, on_death=log_death)

    for i in range(normal_bots):
        engine.spawn(f"bot-{1000 + i}", generation=0)
    reckless = engine.spawn("bot-2000-reckless", generation=0)
    dormant = engine.spawn("bot-3000-dormant", generation=0)

    for gen in range(1, generations + 1):
        print(f"\n=== Generation {gen} — {len(engine.active)} alive ===")

        for agent in list(engine.active.values()):
            if agent is dormant:
                # Never trades — exists purely to demonstrate the
                # inactivity countdown reaching zero.
                engine.record_tick(agent, traded=False)
                continue

            traded = random.random() > 0.15
            if traded:
                if agent is reckless:
                    # Ignores the supervisor's sizing advice on purpose.
                    risk_pct = agent.base_position_size_pct / 100
                else:
                    risk_pct = engine.scaled_position_size_pct(agent) / 100
                swing = random.uniform(-1.6, 1.3) * risk_pct * agent.capital
                agent.capital = max(0.0, agent.capital + swing)
            engine.record_tick(agent, traded=traded)

        purged = engine.run_deletion_sequence(generation=gen)
        engine.advance_generation()

        for agent in engine.active.values():
            t = engine.telemetry(agent)
            flag = " ⚠ inactivity" if t["inactivity_critical"] else ""
            print(
                f"   {t['id']:<16}  cap=${t['capital']:>9,.0f}  "
                f"dd={t['drawdown_pct']:>6.1f}%  "
                f"survival={t['survival_factor']:.2f}  "
                f"size={t['scaled_position_size_pct']:>4.1f}%  "
                f"cd={t['inactivity_countdown']}/{t['inactivity_timeout']}{flag}"
            )

        if not engine.active:
            print("\nEntire population purged — simulation over.")
            break

    print(f"\nFinal tally: {len(engine.active)} alive, {len(engine.graveyard)} in the graveyard.")


if __name__ == "__main__":
    run_demo()
