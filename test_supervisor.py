import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.supervisor import SupervisorConfig, SupervisorEngine


def make_engine(**overrides) -> SupervisorEngine:
    cfg = SupervisorConfig(
        starting_capital=10_000,
        hard_deletion_threshold=40,   # dead at -40%
        inactivity_timeout=5,
        survival_curve_exponent=2.0,
        min_survival_factor=0.05,
        base_position_size_pct=10.0,
        inactivity_warning_ratio=0.34,
    )
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return SupervisorEngine(cfg)


# ---------------------------------------------------------------------
# 1. Position-size scaling
# ---------------------------------------------------------------------
def test_full_health_agent_gets_full_size():
    eng = make_engine()
    a = eng.spawn("bot-1")
    assert eng.survival_factor(a) == 1.0
    assert eng.scaled_position_size_pct(a) == a.base_position_size_pct


def test_profitable_agent_is_not_scaled_down():
    eng = make_engine()
    a = eng.spawn("bot-1", capital=12_000)  # up 20%
    assert eng.survival_factor(a) == 1.0


def test_position_size_shrinks_as_drawdown_grows():
    eng = make_engine()
    a = eng.spawn("bot-1")

    sizes = []
    for capital in (10_000, 9_000, 8_000, 7_000, 6_500, 6_100):
        a.capital = capital
        sizes.append(eng.scaled_position_size_pct(a))

    # monotonically non-increasing as capital falls toward the threshold
    assert all(sizes[i] >= sizes[i + 1] for i in range(len(sizes) - 1))
    assert sizes[0] > sizes[-1]


def test_survival_factor_never_collapses_fully_while_alive():
    eng = make_engine()
    a = eng.spawn("bot-1", capital=6_050)  # -39.5%, just shy of -40% death line
    assert eng.survival_factor(a) >= eng.config.min_survival_factor
    assert eng.survival_factor(a) > 0.0


def test_survival_factor_hits_zero_floor_right_at_threshold():
    eng = make_engine()
    a = eng.spawn("bot-1", capital=6_000)  # exactly -40%
    # at the threshold, raw survival is 0 -> floored at min_survival_factor
    assert eng.survival_factor(a) == eng.config.min_survival_factor


# ---------------------------------------------------------------------
# 2. Inactivity tracking
# ---------------------------------------------------------------------
def test_countdown_ticks_down_when_inactive():
    eng = make_engine()
    a = eng.spawn("bot-1")
    assert a.inactivity_countdown == 5
    eng.record_tick(a, traded=False)
    assert a.inactivity_countdown == 4
    eng.record_tick(a, traded=False)
    assert a.inactivity_countdown == 3


def test_countdown_resets_on_a_trade():
    eng = make_engine()
    a = eng.spawn("bot-1")
    eng.record_tick(a, traded=False)
    eng.record_tick(a, traded=False)
    assert a.inactivity_countdown == 3
    eng.record_tick(a, traded=True)
    assert a.inactivity_countdown == 5
    assert a.status == "alive"


def test_agent_flagged_dormant_and_critical_before_it_dies():
    eng = make_engine()
    a = eng.spawn("bot-1")
    # timeout=5, warning_ratio=0.34 -> warning window <= 1
    for _ in range(4):
        eng.record_tick(a, traded=False)
    assert a.inactivity_countdown == 1
    assert eng.is_inactivity_critical(a) is True
    assert a.status == "dormant"


# ---------------------------------------------------------------------
# 3. Deletion sequence
# ---------------------------------------------------------------------
def test_purged_on_hard_deletion_threshold():
    eng = make_engine()
    a = eng.spawn("bot-1", capital=5_500)  # -45%, past -40% line
    purged = eng.run_deletion_sequence(generation=3)

    assert len(purged) == 1
    assert purged[0].id == "bot-1"
    assert purged[0].cause_of_death == "hard_deletion_threshold"
    assert purged[0].death_generation == 3
    assert "bot-1" not in eng.active
    assert eng.graveyard[0].id == "bot-1"


def test_purged_on_inactivity_timeout():
    eng = make_engine()
    a = eng.spawn("bot-1")
    for _ in range(5):
        eng.record_tick(a, traded=False)
    assert a.inactivity_countdown == 0

    purged = eng.run_deletion_sequence(generation=7)

    assert len(purged) == 1
    assert purged[0].cause_of_death == "inactivity_timeout"
    assert "bot-1" not in eng.active


def test_capital_death_takes_priority_over_inactivity():
    eng = make_engine()
    a = eng.spawn("bot-1", capital=5_000)  # -50%, past threshold
    a.inactivity_countdown = 0             # also inactive-expired

    purged = eng.run_deletion_sequence(generation=1)

    assert purged[0].cause_of_death == "hard_deletion_threshold"


def test_healthy_active_agent_survives_the_sweep():
    eng = make_engine()
    eng.spawn("bot-1")  # full capital, full countdown
    purged = eng.run_deletion_sequence(generation=1)
    assert purged == []
    assert "bot-1" in eng.active


def test_on_death_callback_fires():
    events = []
    eng = make_engine()
    eng.on_death = lambda agent, reason: events.append((agent.id, reason))
    eng.spawn("bot-1", capital=5_000)
    eng.run_deletion_sequence(generation=2)
    assert events == [("bot-1", "hard_deletion_threshold")]


def test_from_dashboard_config_maps_sidebar_dict():
    cfg = SupervisorConfig.from_dashboard_config(
        {
            "starting_capital": 25_000,
            "hard_deletion_threshold": 30,
            "inactivity_timeout": 8,
            "mutation_rate": 20,
        }
    )
    assert cfg.starting_capital == 25_000
    assert cfg.hard_deletion_threshold == 30
    assert cfg.inactivity_timeout == 8
    assert cfg.mutation_rate == 20
