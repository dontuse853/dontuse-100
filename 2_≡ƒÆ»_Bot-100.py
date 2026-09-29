"""
Darwin Desk — Bot-100.

Runs a larger population than the main dashboard (168 bots instead of
up to 27 — see BOT100_CHILDREN_PER_ARCHETYPE below) through the same
real backtest, keeps only the bots that finished profitable, and
ranks up to the top 100 of them by return. "Bot-100" is the page's
name, not a promise there are exactly 100 rows — on a rough run, or
with an aggressive hard_deletion_threshold, there may be fewer than
100 profitable bots, and that's shown honestly rather than padded out.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils import COLORS, ARCHETYPE_COLORS, ARCHETYPE_LABELS, hero, section_header, inject_theme, render_sidebar_config
from engine.supervisor import SupervisorConfig
from engine.backtest import run_backtest_on_synthetic_market

st.set_page_config(page_title="Darwin Desk · Bot-100", page_icon="💯", layout="wide")
inject_theme()

config = render_sidebar_config()

hero(
    "Bot-100",
    "Every profitable bot in a full population run, ranked by return.",
    "REAL BACKTEST · SYNTHETIC MARKET",
)

N_BARS = 420
BOT100_CHILDREN_PER_ARCHETYPE = 55  # 3 archetypes * (1 master + 55 children) = 168 bots
BARS_PER_GENERATION = 80


@st.cache_data(show_spinner=False)
def get_bot100_backtest(starting_capital, hard_deletion_threshold, inactivity_timeout, mutation_rate):
    cfg = SupervisorConfig(
        starting_capital=float(starting_capital),
        hard_deletion_threshold=float(hard_deletion_threshold),
        inactivity_timeout=int(inactivity_timeout),
        mutation_rate=float(mutation_rate),
    )
    return run_backtest_on_synthetic_market(
        cfg,
        n_bars=N_BARS,
        children_per_archetype=BOT100_CHILDREN_PER_ARCHETYPE,
        price_seed=7,
        population_seed=1,
        bars_per_generation=BARS_PER_GENERATION,
    )


result = get_bot100_backtest(
    config["starting_capital"],
    config["hard_deletion_threshold"],
    config["inactivity_timeout"],
    config["mutation_rate"],
)

starting_capital = config["starting_capital"]
bot_ids = list(result.archetypes.keys())

# One master per archetype — mutation_delta_pct is measured against it,
# since every child's immediate parent *is* the master (one hop, no
# multi-generation breeding yet).
masters = {bot.archetype: bot for bot in result.bots.values() if bot.parent_id is None}

rows = []
for bid in bot_ids:
    final_capital = result.equity_curves[bid][-1]
    pnl_pct = (final_capital / starting_capital - 1) * 100
    if pnl_pct <= 0:
        continue  # Bot-100 only ranks profitable bots

    archetype = result.archetypes[bid]
    bot = result.bots[bid]
    is_master = bot.parent_id is None
    mutation_delta = 0.0 if is_master else masters[archetype].mutation_delta_pct(bot)

    is_alive = bid in result.engine.active
    if is_alive:
        gens_survived = result.engine.active[bid].generations_survived
        status_kind, status_text = "alive", "🟢 Alive"
    else:
        dead = next(a for a in result.engine.graveyard if a.id == bid)
        gens_survived = dead.death_generation
        cause = "capital" if dead.cause_of_death == "hard_deletion_threshold" else "inactivity"
        status_kind, status_text = "dead", f"🔴 Deleted ({cause})"

    rows.append({
        "bot_id": bid,
        "archetype": archetype,
        "pnl_pct": pnl_pct,
        "profit_dollars": final_capital - starting_capital,
        "mutation_delta_pct": mutation_delta,
        "is_master": is_master,
        "generations_survived": gens_survived,
        "status_kind": status_kind,
        "status_text": status_text,
    })

rows.sort(key=lambda r: r["pnl_pct"], reverse=True)
top_rows = rows[:100]

# ---------------------------------------------------------------------------
# Summary stats
# ---------------------------------------------------------------------------
total_bots = len(bot_ids)
profitable_count = len(rows)
avg_profitable_pnl = float(np.mean([r["pnl_pct"] for r in rows])) if rows else 0.0

s1, s2, s3, s4 = st.columns(4)
with s1:
    st.markdown(
        f'<div class="dd-kpi accent-cyan"><div class="label">Bots simulated</div>'
        f'<div class="value">{total_bots}</div>'
        f'<div class="delta flat">3 archetypes, mutated children</div></div>',
        unsafe_allow_html=True,
    )
with s2:
    st.markdown(
        f'<div class="dd-kpi accent-green"><div class="label">Profitable</div>'
        f'<div class="value">{profitable_count} / {total_bots}</div>'
        f'<div class="delta up">{profitable_count / total_bots:.0%} of the population</div></div>',
        unsafe_allow_html=True,
    )
with s3:
    st.markdown(
        f'<div class="dd-kpi accent-violet"><div class="label">Avg P&L, profitable only</div>'
        f'<div class="value">+{avg_profitable_pnl:.1f}%</div>'
        f'<div class="delta flat">across {profitable_count} bots</div></div>',
        unsafe_allow_html=True,
    )
with s4:
    best = top_rows[0] if top_rows else None
    st.markdown(
        f'<div class="dd-kpi accent-amber"><div class="label">Best bot</div>'
        f'<div class="value">+{best["pnl_pct"]:.1f}%</div>'
        f'<div class="delta up">{best["bot_id"]} · {ARCHETYPE_LABELS[best["archetype"]]}</div></div>'
        if best else
        '<div class="dd-kpi accent-amber"><div class="label">Best bot</div><div class="value">—</div></div>',
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Who's dominating the profitable pool, by archetype
# ---------------------------------------------------------------------------
section_header("Profitable bots by archetype", "count and average return")

archetype_stats = {a: {"count": 0, "pnls": []} for a in ARCHETYPE_LABELS}
for r in rows:
    archetype_stats[r["archetype"]]["count"] += 1
    archetype_stats[r["archetype"]]["pnls"].append(r["pnl_pct"])

st.markdown('<div class="dd-panel">', unsafe_allow_html=True)
fig_breakdown = go.Figure()
archetypes_ordered = list(ARCHETYPE_LABELS.keys())
counts = [archetype_stats[a]["count"] for a in archetypes_ordered]
avg_pnls = [float(np.mean(archetype_stats[a]["pnls"])) if archetype_stats[a]["pnls"] else 0.0 for a in archetypes_ordered]
labels = [ARCHETYPE_LABELS[a] for a in archetypes_ordered]
colors = [ARCHETYPE_COLORS[a] for a in archetypes_ordered]

fig_breakdown.add_trace(go.Bar(
    x=labels, y=counts, marker=dict(color=colors),
    text=[f"+{p:.1f}% avg" for p in avg_pnls], textposition="outside",
    hovertemplate="%{x}<br>%{y} profitable bots<br>%{text}<extra></extra>",
))
fig_breakdown.update_layout(
    template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=10, r=10, t=30, b=10), height=260, showlegend=False,
    xaxis=dict(showgrid=False), yaxis=dict(title="Profitable bots", showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
)
st.plotly_chart(fig_breakdown, width='stretch')
st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
section_header("Top 100 profitable bots", f"ranked by return · ${starting_capital:,.0f} starting capital each")

f1, f2 = st.columns([2, 1])
with f1:
    search = st.text_input("Search bot ID", placeholder="e.g. trend_follower-4f2a1c")
with f2:
    archetype_filter = st.selectbox("Archetype", ["All"] + [ARCHETYPE_LABELS[a] for a in ARCHETYPE_LABELS])

filtered = top_rows
if search:
    filtered = [r for r in filtered if search.lower() in r["bot_id"].lower()]
if archetype_filter != "All":
    filtered = [r for r in filtered if ARCHETYPE_LABELS[r["archetype"]] == archetype_filter]

if not filtered:
    st.info("No profitable bots match these filters yet — try loosening the hard deletion threshold or inactivity timeout in the sidebar.")
else:
    display_df = pd.DataFrame([
        {
            "Rank": i + 1,
            "Bot ID": r["bot_id"] + (" 👑" if r["is_master"] else ""),
            "Archetype": ARCHETYPE_LABELS[r["archetype"]],
            "P&L (%)": f"+{r['pnl_pct']:.1f}%",
            "Profit ($)": f"+${r['profit_dollars']:,.0f}",
            "Mutation Δ vs master": "—" if r["is_master"] else f"{r['mutation_delta_pct']:.0f}%",
            "Generations survived": r["generations_survived"],
            "Status": r["status_text"],
        }
        for i, r in enumerate(filtered)
    ])
    st.dataframe(display_df, hide_index=True, width='stretch', height=560)

st.markdown(
    '<div class="dd-panel-note" style="margin-top:0.5rem;">'
    '👑 marks a generation-zero master template (not a mutated clone). '
    '"Mutation Δ vs master" is the average % each parameter has drifted from the master\'s — '
    'every clone is guaranteed at least one real parameter difference, never an exact duplicate.'
    '</div>',
    unsafe_allow_html=True,
)

st.caption("Same synthetic market and real supervisor engine as the main dashboard — this page just runs a much larger population to make a meaningful top-100 cut.")
