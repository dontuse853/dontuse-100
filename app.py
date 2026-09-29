"""
Darwin Desk — main dashboard.

The visualization tabs below now run a REAL backtest: the three master
templates in engine/bots.py (trend follower, mean reversion, breakout),
each with mutated children, trading a synthetic regime-switching market
through the real supervisor engine (engine/supervisor.py). Nothing here
touches live market data or a brokerage — the price series is
synthetic, generated fresh from the sidebar's parameters — but the
survival scaling, inactivity tracking, and deletion sequence you see
are the actual engine, not mock numbers.

The lineage map tab is still a schematic placeholder (`mock_population_tree`)
since generation-over-generation reproduction across the whole
population isn't wired up yet — that's the natural next step.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils import COLORS, ARCHETYPE_COLORS, ARCHETYPE_LABELS, hero, kpi_card, section_header, inject_theme, render_sidebar_config
from engine.supervisor import SupervisorConfig
from engine.backtest import run_backtest_on_synthetic_market

st.set_page_config(page_title="Darwin Desk", page_icon="🧬", layout="wide")
inject_theme()

config = render_sidebar_config()

# ---------------------------------------------------------------------------
# Hero
# ---------------------------------------------------------------------------
hero(
    "Darwin Desk",
    "Trading bots that replicate when profitable and get deleted when they aren't. Natural selection, pointed at the market.",
    "ENGINE LIVE · SYNTHETIC MARKET",
)

# ---------------------------------------------------------------------------
# Run (and cache) the real backtest off the sidebar's parameters.
#
# bars_per_generation controls how many price bars make up one
# "generation" for inactivity-timeout purposes — see the docstring in
# engine/backtest.run_backtest for why that matters. 80 keeps the
# sidebar's inactivity_timeout default (5) generous enough for a
# patient archetype like breakout to reach its own regime, while a
# tight timeout (1-2) still visibly purges bots — try it.
# ---------------------------------------------------------------------------
N_BARS = 420
BARS_PER_GENERATION = 80


@st.cache_data(show_spinner=False)
def get_backtest(starting_capital, hard_deletion_threshold, inactivity_timeout,
                  mutation_rate, children_per_archetype):
    cfg = SupervisorConfig(
        starting_capital=float(starting_capital),
        hard_deletion_threshold=float(hard_deletion_threshold),
        inactivity_timeout=int(inactivity_timeout),
        mutation_rate=float(mutation_rate),
    )
    return run_backtest_on_synthetic_market(
        cfg,
        n_bars=N_BARS,
        children_per_archetype=children_per_archetype,
        price_seed=7,
        population_seed=1,
        bars_per_generation=BARS_PER_GENERATION,
    )


children_per_archetype = int(np.clip(round((config["population_size"] - 3) / 3), 2, 8))

result = get_backtest(
    config["starting_capital"],
    config["hard_deletion_threshold"],
    config["inactivity_timeout"],
    config["mutation_rate"],
    children_per_archetype,
)

bot_ids = list(result.archetypes.keys())
n_bots = len(bot_ids)
starting_capital = config["starting_capital"]

# % return curve per bot, and the population's blended % return curve
# (cap-weighted average = total dollar profit / total dollar starting capital).
pct_curves = {
    bid: [(v / starting_capital - 1) * 100 for v in result.equity_curves[bid]]
    for bid in bot_ids
}
total_pct_curve = [(v / (starting_capital * n_bots) - 1) * 100 for v in result.total_equity]

# ---------------------------------------------------------------------------
# KPI row — computed from the real backtest result.
# ---------------------------------------------------------------------------
alive_ids = list(result.engine.active.keys())
final_pnls = {bid: pct_curves[bid][-1] for bid in bot_ids}
best_bot_id = max(final_pnls, key=final_pnls.get)

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(kpi_card("Bars simulated", f"{N_BARS}", f"~{N_BARS // BARS_PER_GENERATION} generations", "flat", "cyan"), unsafe_allow_html=True)
with c2:
    st.markdown(
        kpi_card(
            "Population alive",
            f"{len(alive_ids)} / {n_bots}",
            f"-{len(result.engine.graveyard)} purged total", "down" if result.engine.graveyard else "flat", "green",
        ),
        unsafe_allow_html=True,
    )
with c3:
    st.markdown(kpi_card("Best bot P&L", f"{final_pnls[best_bot_id]:+.1f}%", f"{best_bot_id} · {ARCHETYPE_LABELS[result.archetypes[best_bot_id]]}", "up" if final_pnls[best_bot_id] >= 0 else "down", "violet"), unsafe_allow_html=True)
with c4:
    avg_pnl = float(np.mean(list(final_pnls.values())))
    st.markdown(kpi_card("Avg fitness (P&L)", f"{avg_pnl:+.1f}%", "across full population", "up" if avg_pnl >= 0 else "down", "cyan"), unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------
section_header("Population performance", "live from the backtest below")

tab1, tab2, tab3, tab4 = st.tabs([
    "Total population P&L", "Per-bot equity curves", "Fitness distribution", "Lineage map",
])

with tab1:
    st.markdown('<div class="dd-panel">', unsafe_allow_html=True)

    total_final = total_pct_curve[-1]
    ticker_color = COLORS["green"] if total_final >= 0 else COLORS["red"]
    st.markdown(
        f"""
        <div style="display:flex; align-items:baseline; gap:0.7rem; padding:0.2rem 0 0.9rem 0;">
            <span style="font-family:'JetBrains Mono',monospace; font-size:2.1rem; font-weight:700; color:{ticker_color};">
                {total_final:+.2f}%
            </span>
            <span style="color:{COLORS['muted']}; font-size:0.85rem;">
                blended population return across {n_bots} bots, {N_BARS} bars
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    max_abs = max(1e-6, max(abs(v) for curve in pct_curves.values() for v in curve))
    slope = 0.8 * max_abs / (N_BARS - 1)
    steps = np.arange(N_BARS)
    upper_envelope = slope * steps
    lower_envelope = -slope * steps

    fig_total = go.Figure()
    for bid in bot_ids:
        fig_total.add_trace(go.Scatter(
            x=steps, y=pct_curves[bid], mode="lines", name=ARCHETYPE_LABELS[result.archetypes[bid]],
            line=dict(width=1, color=ARCHETYPE_COLORS[result.archetypes[bid]]),
            opacity=0.28, showlegend=False, hoverinfo="skip",
        ))
    fig_total.add_trace(go.Scatter(
        x=steps, y=upper_envelope, mode="lines", name="+0.8x envelope",
        line=dict(width=1.5, color=COLORS["muted"], dash="dot"),
    ))
    fig_total.add_trace(go.Scatter(
        x=steps, y=lower_envelope, mode="lines", name="-0.8x envelope",
        line=dict(width=1.5, color=COLORS["muted"], dash="dot"),
    ))
    fig_total.add_trace(go.Scatter(
        x=steps, y=total_pct_curve, mode="lines", name="Total population P&L",
        line=dict(width=3, color=ticker_color),
    ))
    fig_total.update_layout(
        template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=10, b=10), height=380,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        xaxis=dict(title="Bar", showgrid=False),
        yaxis=dict(title="Cumulative return (%)", showgrid=True, gridcolor="rgba(255,255,255,0.05)", zeroline=True, zerolinecolor="rgba(255,255,255,0.15)"),
    )
    st.plotly_chart(fig_total, width='stretch')
    st.markdown(
        '<div class="dd-panel-note">Every bot\'s full profit history layered underneath the bold total, '
        'bounded by a &plusmn;0.8x reference channel scaled to the widest individual swing &mdash; the fan of thin lines is real, '
        'traded by the archetypes below against a synthetic market.</div></div>',
        unsafe_allow_html=True,
    )

with tab2:
    st.markdown('<div class="dd-panel">', unsafe_allow_html=True)
    fig = go.Figure()
    for bid in bot_ids:
        fig.add_trace(go.Scatter(
            x=steps, y=result.equity_curves[bid], mode="lines",
            name=f"{ARCHETYPE_LABELS[result.archetypes[bid]]} · {bid}",
            line=dict(width=1.6, color=ARCHETYPE_COLORS[result.archetypes[bid]]),
            opacity=0.75 if bid in alive_ids else 0.35,
        ))
    fig.update_layout(
        template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=10, b=10), height=380,
        showlegend=False,
        xaxis=dict(title="Bar", showgrid=False),
        yaxis=dict(title="Capital ($)", showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
    )
    st.plotly_chart(fig, width='stretch')
    st.markdown(
        f'<div class="dd-panel-note">'
        f'<span style="color:{COLORS["cyan"]}">■</span> trend follower &nbsp;'
        f'<span style="color:{COLORS["violet"]}">■</span> mean reversion &nbsp;'
        f'<span style="color:{COLORS["amber"]}">■</span> breakout — faded lines were purged before bar {N_BARS}.'
        f'</div></div>',
        unsafe_allow_html=True,
    )

with tab3:
    st.markdown('<div class="dd-panel">', unsafe_allow_html=True)
    fig2 = go.Figure()
    for archetype, color in ARCHETYPE_COLORS.items():
        values = [final_pnls[bid] for bid in bot_ids if result.archetypes[bid] == archetype]
        fig2.add_trace(go.Histogram(x=values, name=ARCHETYPE_LABELS[archetype],
                                     marker=dict(color=color), opacity=0.75, nbinsx=12))
    fig2.add_vline(x=-config["hard_deletion_threshold"], line=dict(color=COLORS["red"], dash="dash"),
                   annotation_text="hard deletion line", annotation_font_color=COLORS["red"])
    fig2.update_layout(
        template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=10, b=10), height=340, barmode="overlay",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        xaxis=dict(title="Final P&L (%)", showgrid=False),
        yaxis=dict(title="Bot count", showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
    )
    st.plotly_chart(fig2, width='stretch')
    st.markdown('<div class="dd-panel-note">Final return distribution across the real backtested population, by archetype, with your configured hard-deletion line overlaid.</div></div>', unsafe_allow_html=True)

with tab4:
    st.markdown('<div class="dd-panel">', unsafe_allow_html=True)

    def mock_population_tree(generations: int = 6) -> go.Figure:
        """Still a schematic placeholder — generation-over-generation
        reproduction across the whole population isn't wired up yet,
        so there's no real ancestry tree to draw."""
        rng = np.random.default_rng(3)
        fig = go.Figure()
        prev_x, prev_y = None, None
        for g in range(generations):
            count = max(3, 10 - g)
            ys = np.linspace(-1, 1, count)
            xs = np.full(count, g)
            survivors = rng.choice(count, size=max(1, count // 2), replace=False)
            fig.add_trace(go.Scatter(
                x=xs, y=ys, mode="markers",
                marker=dict(size=9, color=COLORS["cyan"] if g == generations - 1 else COLORS["muted"],
                            line=dict(width=1, color=COLORS["border"])),
                showlegend=False, hoverinfo="skip",
            ))
            if prev_x is not None:
                for s in survivors:
                    target = rng.integers(0, count)
                    fig.add_trace(go.Scatter(
                        x=[prev_x[s % len(prev_x)], xs[target]],
                        y=[prev_y[s % len(prev_y)], ys[target]],
                        mode="lines", line=dict(width=1, color="rgba(0,229,255,0.18)"),
                        showlegend=False, hoverinfo="skip",
                    ))
            prev_x, prev_y = xs, ys
        fig.update_layout(
            template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=10, r=10, t=10, b=10), height=320,
            xaxis=dict(title="Generation", showgrid=False, zeroline=False),
            yaxis=dict(showticklabels=False, showgrid=False, zeroline=False, title=""),
        )
        return fig

    st.plotly_chart(mock_population_tree(), width='stretch')
    st.markdown('<div class="dd-panel-note">Placeholder lineage map — who mutated from whom, generation over generation. Not wired to the real backtest yet.</div></div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Top bots preview — real backtest results, sorted by final P&L.
# ---------------------------------------------------------------------------
section_header("Top bots this generation", "→ full leaderboard in the sidebar nav")

ranked = sorted(bot_ids, key=lambda b: final_pnls[b], reverse=True)[:5]
preview_rows = []
for rank, bid in enumerate(ranked, start=1):
    is_alive = bid in alive_ids
    if is_alive:
        gens_survived = result.engine.active[bid].generations_survived
        status = "🟢 Alive"
    else:
        dead = next(a for a in result.engine.graveyard if a.id == bid)
        gens_survived = dead.death_generation
        status = "🔴 Deleted"
    preview_rows.append({
        "Rank": rank,
        "Bot ID": bid,
        "Archetype": ARCHETYPE_LABELS[result.archetypes[bid]],
        "P&L (%)": round(final_pnls[bid], 1),
        "Generations survived": gens_survived,
        "Status": status,
    })
st.dataframe(pd.DataFrame(preview_rows), hide_index=True, width='stretch')

st.caption("Darwin Desk backtest uses a synthetic, regime-switching price series — not live market data. Position sizing, inactivity tracking, and deletion are the real supervisor engine.")
