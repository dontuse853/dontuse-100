"""
Darwin Desk — leaderboard.

INTERFACE ONLY. The table below is generated sample data standing in for
real bot performance. Replace `mock_leaderboard()` with a query into your
actual population once the engine exists.
"""

import numpy as np
import pandas as pd
import streamlit as st

from utils import hero, section_header, pill, inject_theme, render_sidebar_config

st.set_page_config(page_title="Darwin Desk · Leaderboard", page_icon="🏆", layout="wide")
inject_theme()

config = render_sidebar_config()

hero(
    "Leaderboard",
    "Every bot currently alive or recently deleted, ranked by profitability.",
    "SAMPLE DATA · ENGINE NOT CONNECTED",
)

# ---------------------------------------------------------------------------
# Mock leaderboard data
# ---------------------------------------------------------------------------
rng = np.random.default_rng(42)


def mock_leaderboard(n: int = 40) -> pd.DataFrame:
    pnl = rng.normal(loc=5, scale=45, size=n)
    pnl[0:3] = [184.3, 121.9, 98.2]  # keep a clean podium
    gens_survived = rng.integers(1, 20, size=n)
    win_rate = np.clip(rng.normal(55, 12, size=n), 20, 92)
    trades = rng.integers(15, 400, size=n)

    status = []
    for p in pnl:
        if p <= -config["hard_deletion_threshold"]:
            status.append("dead")
        elif p < -5 and rng.random() < 0.15:
            status.append("dormant")
        else:
            status.append("alive")

    df = pd.DataFrame(
        {
            "Bot ID": [f"#{1000 + i}" for i in range(n)],
            "P&L (%)": pnl.round(1),
            "Win rate (%)": win_rate.round(0).astype(int),
            "Trades": trades,
            "Generations survived": gens_survived,
            "Status": status,
        }
    ).sort_values("P&L (%)", ascending=False).reset_index(drop=True)
    df.insert(0, "Rank", df.index + 1)
    return df


df = mock_leaderboard()

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
f1, f2, f3 = st.columns([2, 1, 1])
with f1:
    search = st.text_input("Search bot ID", placeholder="e.g. 1007")
with f2:
    status_filter = st.selectbox("Status", ["All", "Alive", "Dormant", "Dead"])
with f3:
    sort_by = st.selectbox("Sort by", ["P&L (%)", "Win rate (%)", "Generations survived", "Trades"])

filtered = df.copy()
if search:
    filtered = filtered[filtered["Bot ID"].str.contains(search, case=False)]
if status_filter != "All":
    filtered = filtered[filtered["Status"] == status_filter.lower()]
filtered = filtered.sort_values(sort_by, ascending=False)

# ---------------------------------------------------------------------------
# Podium — top 3
# ---------------------------------------------------------------------------
section_header("Top of the population", f"gen {config.get('max_generations', 200)} cap · sample data")

top3 = df.head(3)
podium_cols = st.columns(3)
podium_classes = ["gold", "silver", "bronze"]
podium_labels = ["🥇 1st", "🥈 2nd", "🥉 3rd"]
for i, col in enumerate(podium_cols):
    row = top3.iloc[i]
    with col:
        st.markdown(
            f"""
            <div class="dd-podium {podium_classes[i]}">
                <div class="rank">{podium_labels[i]}</div>
                <div class="name">{row['Bot ID']}</div>
                <div class="pnl">+{row['P&L (%)']:.1f}%</div>
                <div style="color:#7c8aa3; font-size:0.78rem; margin-top:0.4rem;">
                    {row['Generations survived']} generations survived · {row['Win rate (%)']:.0f}% win rate
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

# ---------------------------------------------------------------------------
# Full table
# ---------------------------------------------------------------------------
section_header("Full population", f"{len(filtered)} bots shown")

status_icons = {"alive": "🟢 Alive", "dormant": "🟡 Dormant", "dead": "🔴 Deleted"}
display_df = filtered.copy()
display_df["Status"] = display_df["Status"].map(status_icons)
display_df["P&L (%)"] = display_df["P&L (%)"].map(lambda x: f"{x:+.1f}%")
display_df["Win rate (%)"] = display_df["Win rate (%)"].map(lambda x: f"{x}%")

st.dataframe(
    display_df,
    hide_index=True,
    width='stretch',
    height=560,
)

st.caption("Darwin Desk is an interface preview. Rankings above are randomly generated sample data, not real trading results.")
