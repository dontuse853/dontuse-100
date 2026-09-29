"""
Darwin Desk — Supervisor Engine.

This module owns the *lifecycle* of a bot, not its trading strategy:

1. Position-size scaling  — as an agent's capital approaches the death
   threshold, its "survival factor" drops toward 0 and its position size
   is scaled down to match. A dying bot should be taking smaller and
   smaller bets, not doubling down.

2. Inactivity tracking     — every agent carries a visible countdown of
   how many ticks it has left before it's purged for doing nothing. A
   strategy can read that countdown (via `telemetry()`) to know it's at
   risk and act before it stagnates to death.

3. Deletion sequence       — each tick, the supervisor checks every
   active agent against two independent failure conditions — drawdown
   past the hard deletion threshold, or inactivity countdown hitting
   zero — and purges anyone who trips either one, moving them from the
   active list into the graveyard with a recorded cause of death.

Nothing here places trades or knows about markets. It only manages risk
sizing and survival bookkeeping for whatever strategy layer sits on top.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
@dataclass
class SupervisorConfig:
    """Mirrors the sidebar controls in the dashboard, plus a few knobs
    the UI doesn't need to expose but the engine does."""

    starting_capital: float = 10_000.0

    # % drawdown (0-100) at which an agent is force-killed regardless of
    # anything else. e.g. 40 means "dead the moment capital falls 40%
    # below starting_capital".
    hard_deletion_threshold: float = 40.0

    # Ticks (generations) an agent may go without trading before it is
    # purged for inactivity.
    inactivity_timeout: int = 5

    # How aggressively position size collapses as an agent nears the
    # death threshold. 1.0 = linear falloff. >1.0 = stays fuller size
    # for longer, then collapses hard near the edge (convex curve).
    survival_curve_exponent: float = 2.0

    # Position size never scales all the way to zero while still alive
    # — this is the floor, expressed as a fraction of survival_factor
    # (e.g. 0.05 = never scale below 5% of base size just from proximity
    # to death; an agent only truly stops trading once it's purged).
    min_survival_factor: float = 0.05

    # Default position size (% of capital) a fresh agent risks per
    # trade before any survival scaling is applied.
    base_position_size_pct: float = 10.0

    # Fraction of an agent's inactivity budget remaining at which it is
    # flagged "critical" so a strategy can see the warning coming.
    inactivity_warning_ratio: float = 0.34

    # Carried through for forward-compatibility with the reproduction /
    # mutation step (not implemented in this module).
    mutation_rate: float = 12.0

    @classmethod
    def from_dashboard_config(cls, cfg: dict) -> "SupervisorConfig":
        """Build a SupervisorConfig straight from utils.render_sidebar_config()'s
        return value, so the dashboard sidebar can drive this engine directly."""
        return cls(
            starting_capital=float(cfg.get("starting_capital", 10_000.0)),
            hard_deletion_threshold=float(cfg.get("hard_deletion_threshold", 40.0)),
            inactivity_timeout=int(cfg.get("inactivity_timeout", 5)),
            mutation_rate=float(cfg.get("mutation_rate", 12.0)),
        )


# ---------------------------------------------------------------------------
# Agent state
# ---------------------------------------------------------------------------
@dataclass
class AgentState:
    """Everything the supervisor tracks about one bot. A strategy layer
    can read this freely; only the supervisor should mutate it."""

    id: str
    capital: float
    starting_capital: float
    base_position_size_pct: float
    generation_born: int = 0

    status: str = "alive"          # "alive" | "dormant" | "dead"
    generations_survived: int = 0
    inactivity_countdown: int = field(default=5)

    cause_of_death: Optional[str] = None   # "hard_deletion_threshold" | "inactivity_timeout"
    death_generation: Optional[int] = None

    # -- convenience read-only-ish properties -------------------------------
    @property
    def drawdown_pct(self) -> float:
        """% of starting capital lost. Negative means the agent is up."""
        if self.starting_capital <= 0:
            return 0.0
        return (1.0 - (self.capital / self.starting_capital)) * 100.0


# ---------------------------------------------------------------------------
# The supervisor itself
# ---------------------------------------------------------------------------
class SupervisorEngine:
    """Owns the active population + graveyard and runs the three jobs
    described at the top of this file: scale, track, purge."""

    def __init__(
        self,
        config: SupervisorConfig,
        on_death: Optional[Callable[[AgentState, str], None]] = None,
    ):
        self.config = config
        self.active: dict[str, AgentState] = {}
        self.graveyard: list[AgentState] = []
        # Optional hook fired the moment an agent is purged, e.g. to push
        # a "🔴 Deleted" event into a UI or log — receives (agent, reason).
        self.on_death = on_death

    # -- registration --------------------------------------------------
    def spawn(
        self,
        agent_id: str,
        generation: int = 0,
        capital: Optional[float] = None,
        base_position_size_pct: Optional[float] = None,
    ) -> AgentState:
        """Register a brand-new agent with the supervisor and return its state."""
        agent = AgentState(
            id=agent_id,
            capital=capital if capital is not None else self.config.starting_capital,
            starting_capital=self.config.starting_capital,
            base_position_size_pct=(
                base_position_size_pct
                if base_position_size_pct is not None
                else self.config.base_position_size_pct
            ),
            generation_born=generation,
            inactivity_countdown=self.config.inactivity_timeout,
        )
        self.active[agent_id] = agent
        return agent

    # -----------------------------------------------------------------
    # 1. Position-size scaling
    # -----------------------------------------------------------------
    def survival_factor(self, agent: AgentState) -> float:
        """
        1.0  = full health, no scaling.
        0.0  = right at (or past) the hard deletion threshold.

        Linear proximity to death is raised to `survival_curve_exponent`
        so the size stays close to full for most of the agent's runway
        and only really collapses near the edge (convex curve for
        exponent > 1). A floor (`min_survival_factor`) keeps it from
        going fully to zero while the agent is still alive.
        """
        threshold = self.config.hard_deletion_threshold
        if threshold <= 0:
            return 1.0

        drawdown = agent.drawdown_pct
        if drawdown <= 0:
            return 1.0  # flat or profitable — no defensive scaling needed

        proximity_to_death = min(drawdown / threshold, 1.0)  # 0 -> 1
        raw_survival = 1.0 - proximity_to_death
        shaped = raw_survival ** self.config.survival_curve_exponent
        return max(shaped, self.config.min_survival_factor)

    def scaled_position_size_pct(self, agent: AgentState) -> float:
        """The position size (% of capital) this agent should actually
        risk on its next trade, after survival scaling."""
        return agent.base_position_size_pct * self.survival_factor(agent)

    # -----------------------------------------------------------------
    # 2. Inactivity tracking
    # -----------------------------------------------------------------
    def record_tick(self, agent: AgentState, traded: bool) -> None:
        """Call once per generation/tick for every active agent.

        If the agent traded, its countdown resets to a full inactivity
        budget. If it didn't, the countdown ticks down by one — and once
        it reaches zero, `run_deletion_sequence` will purge it.
        """
        if traded:
            agent.inactivity_countdown = self.config.inactivity_timeout
            agent.status = "alive"
        else:
            agent.inactivity_countdown -= 1
            if agent.inactivity_countdown <= max(
                0, int(self.config.inactivity_timeout * self.config.inactivity_warning_ratio)
            ):
                # Still alive, but flagged so telemetry can warn the
                # strategy layer before it's too late.
                agent.status = "dormant"

    def is_inactivity_critical(self, agent: AgentState) -> bool:
        """True once an agent is inside its final warning window before
        an inactivity purge — the signal a strategy should watch for."""
        warning_window = self.config.inactivity_timeout * self.config.inactivity_warning_ratio
        return agent.inactivity_countdown <= max(0, int(warning_window))

    # -----------------------------------------------------------------
    # Telemetry — the read-only view a strategy or dashboard consumes
    # -----------------------------------------------------------------
    def telemetry(self, agent: AgentState) -> dict:
        return {
            "id": agent.id,
            "status": agent.status,
            "capital": round(agent.capital, 2),
            "starting_capital": agent.starting_capital,
            "drawdown_pct": round(agent.drawdown_pct, 2),
            "survival_factor": round(self.survival_factor(agent), 4),
            "base_position_size_pct": agent.base_position_size_pct,
            "scaled_position_size_pct": round(self.scaled_position_size_pct(agent), 3),
            "inactivity_countdown": agent.inactivity_countdown,
            "inactivity_timeout": self.config.inactivity_timeout,
            "inactivity_critical": self.is_inactivity_critical(agent),
            "generations_survived": agent.generations_survived,
            "cause_of_death": agent.cause_of_death,
            "death_generation": agent.death_generation,
        }

    # -----------------------------------------------------------------
    # 3. Deletion sequence
    # -----------------------------------------------------------------
    def evaluate(self, agent: AgentState) -> Optional[str]:
        """Return the reason an agent should be purged right now, or
        None if it's still fit to stay in the active population.

        Hard deletion (drawdown) is checked before inactivity — a bot
        that's both broke *and* idle dies for the capital reason, since
        that's the more informative cause of death.
        """
        if agent.drawdown_pct >= self.config.hard_deletion_threshold:
            return "hard_deletion_threshold"
        if agent.inactivity_countdown <= 0:
            return "inactivity_timeout"
        return None

    def run_deletion_sequence(self, generation: int) -> list[AgentState]:
        """Sweep every active agent, purge anyone who has failed either
        condition, and return the list of agents removed this pass.

        Purged agents are moved out of `self.active` and into
        `self.graveyard` with `status`, `cause_of_death`, and
        `death_generation` set, so a leaderboard can render them as
        "🔴 Deleted" without losing their final stats.
        """
        purged: list[AgentState] = []
        for agent_id in list(self.active.keys()):
            agent = self.active[agent_id]
            reason = self.evaluate(agent)
            if reason is None:
                continue

            agent.status = "dead"
            agent.cause_of_death = reason
            agent.death_generation = generation

            del self.active[agent_id]
            self.graveyard.append(agent)
            purged.append(agent)

            if self.on_death is not None:
                self.on_death(agent, reason)

        return purged

    # -- convenience -----------------------------------------------------
    def advance_generation(self) -> None:
        """Bump the survival counter for everyone still active. Call this
        once per generation, after trading + record_tick + deletion."""
        for agent in self.active.values():
            agent.generations_survived += 1
