"""
Darwin Desk — shared UI utilities.

This module holds everything that both pages (Dashboard + Leaderboard) need:
the visual theme (CSS), the sidebar configuration panel, and small HTML
component builders (KPI cards, status pills, section headers).

Nothing in here runs a trading strategy or an evolutionary algorithm —
it only renders the interface and returns whatever values the person
has chosen in the sidebar.
"""

import streamlit as st

# ---------------------------------------------------------------------------
# Design tokens — change these to re-theme the whole app from one place.
# ---------------------------------------------------------------------------
COLORS = {
    "bg": "#0a0e17",
    "panel": "#111826",
    "panel_alt": "#0d1420",
    "border": "#1e293b",
    "text": "#e8f1ff",
    "muted": "#7c8aa3",
    "cyan": "#00e5ff",
    "green": "#39ff88",
    "red": "#ff3b5c",
    "violet": "#b26bff",
    "amber": "#ffb020",
}

# Shared across every page so an archetype always reads the same color.
ARCHETYPE_COLORS = {
    "trend_follower": COLORS["cyan"],
    "mean_reversion": COLORS["violet"],
    "breakout": COLORS["amber"],
}
ARCHETYPE_LABELS = {
    "trend_follower": "Trend follower",
    "mean_reversion": "Mean reversion",
    "breakout": "Breakout",
}


def inject_theme() -> None:
    """Injects fonts + CSS for the whole app. Call once at the top of every page."""
    st.markdown(
        f"""
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
        <style>
        html, body, [class*="css"] {{
            font-family: 'Space Grotesk', sans-serif;
        }}
        .stApp {{
            background: radial-gradient(circle at 15% 0%, #101a2b 0%, {COLORS['bg']} 45%) fixed;
            color: {COLORS['text']};
        }}
        section[data-testid="stSidebar"] {{
            background: {COLORS['panel_alt']};
            border-right: 1px solid {COLORS['border']};
        }}
        section[data-testid="stSidebar"] .block-container {{
            padding-top: 1.5rem;
        }}
        /* headline treatment */
        .dd-hero {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 1rem;
            padding-bottom: 1.1rem;
            margin-bottom: 1.6rem;
            border-bottom: 1px solid {COLORS['border']};
        }}
        .dd-hero h1 {{
            font-family: 'Space Grotesk', sans-serif;
            font-weight: 700;
            font-size: 2.35rem;
            letter-spacing: -0.02em;
            margin: 0;
            line-height: 1.1;
            background: linear-gradient(90deg, {COLORS['text']} 20%, {COLORS['cyan']} 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .dd-hero p {{
            margin: 0.35rem 0 0 0;
            color: {COLORS['muted']};
            font-size: 0.95rem;
            max-width: 46ch;
        }}
        .dd-status {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.78rem;
            color: {COLORS['muted']};
            background: {COLORS['panel']};
            border: 1px solid {COLORS['border']};
            padding: 0.5rem 0.9rem;
            border-radius: 999px;
        }}
        .dd-dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: {COLORS['green']};
            box-shadow: 0 0 0 0 rgba(57,255,136,0.6);
            animation: dd-pulse 2s infinite;
        }}
        @keyframes dd-pulse {{
            0%   {{ box-shadow: 0 0 0 0 rgba(57,255,136,0.55); }}
            70%  {{ box-shadow: 0 0 0 7px rgba(57,255,136,0); }}
            100% {{ box-shadow: 0 0 0 0 rgba(57,255,136,0); }}
        }}
        /* KPI cards */
        .dd-kpi {{
            background: {COLORS['panel']};
            border: 1px solid {COLORS['border']};
            border-radius: 12px;
            padding: 1.05rem 1.2rem;
            height: 100%;
        }}
        .dd-kpi .label {{
            color: {COLORS['muted']};
            font-size: 0.78rem;
            margin-bottom: 0.45rem;
        }}
        .dd-kpi .value {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 1.55rem;
            font-weight: 700;
            color: {COLORS['text']};
        }}
        .dd-kpi .delta {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.8rem;
            margin-top: 0.3rem;
        }}
        .dd-kpi .delta.up {{ color: {COLORS['green']}; }}
        .dd-kpi .delta.down {{ color: {COLORS['red']}; }}
        .dd-kpi .delta.flat {{ color: {COLORS['muted']}; }}
        .dd-kpi.accent-cyan   {{ border-top: 2px solid {COLORS['cyan']}; }}
        .dd-kpi.accent-green  {{ border-top: 2px solid {COLORS['green']}; }}
        .dd-kpi.accent-red    {{ border-top: 2px solid {COLORS['red']}; }}
        .dd-kpi.accent-violet {{ border-top: 2px solid {COLORS['violet']}; }}
        /* section headers */
        .dd-section {{
            display: flex;
            align-items: baseline;
            justify-content: space-between;
            margin: 1.9rem 0 0.8rem 0;
        }}
        .dd-section h3 {{
            font-size: 1.05rem;
            font-weight: 600;
            margin: 0;
            color: {COLORS['text']};
        }}
        .dd-section span {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.75rem;
            color: {COLORS['muted']};
        }}
        /* panel / card wrapper for charts + tables */
        .dd-panel {{
            background: {COLORS['panel']};
            border: 1px solid {COLORS['border']};
            border-radius: 14px;
            padding: 1.1rem 1.2rem 0.4rem 1.2rem;
        }}
        .dd-panel-note {{
            color: {COLORS['muted']};
            font-size: 0.78rem;
            font-family: 'JetBrains Mono', monospace;
            padding: 0.6rem 0.1rem 0.9rem 0.1rem;
        }}
        /* status pills used in tables */
        .dd-pill {{
            display: inline-block;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.72rem;
            font-weight: 700;
            padding: 0.18rem 0.55rem;
            border-radius: 6px;
            letter-spacing: 0.03em;
        }}
        .dd-pill.alive {{ background: rgba(57,255,136,0.12); color: {COLORS['green']}; }}
        .dd-pill.dead  {{ background: rgba(255,59,92,0.12);  color: {COLORS['red']}; }}
        .dd-pill.dormant {{ background: rgba(255,176,32,0.12); color: {COLORS['amber']}; }}
        /* buttons */
        .stButton > button {{
            background: linear-gradient(90deg, {COLORS['cyan']} 0%, {COLORS['violet']} 100%);
            color: #05070c;
            font-weight: 700;
            border: none;
            border-radius: 10px;
            padding: 0.55rem 1.1rem;
        }}
        .stButton > button:hover {{
            filter: brightness(1.08);
            color: #05070c;
        }}
        /* podium cards on leaderboard */
        .dd-podium {{
            background: {COLORS['panel']};
            border-radius: 14px;
            padding: 1.1rem;
            text-align: center;
            position: relative;
        }}
        .dd-podium .rank {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.75rem;
            color: {COLORS['muted']};
        }}
        .dd-podium .name {{
            font-size: 1.1rem;
            font-weight: 700;
            margin: 0.25rem 0 0.5rem 0;
        }}
        .dd-podium .pnl {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 1.4rem;
            font-weight: 700;
        }}
        .dd-podium.gold   {{ border: 1px solid {COLORS['amber']}; box-shadow: 0 0 24px rgba(255,176,32,0.15); }}
        .dd-podium.silver {{ border: 1px solid {COLORS['cyan']};  box-shadow: 0 0 24px rgba(0,229,255,0.13); }}
        .dd-podium.bronze {{ border: 1px solid {COLORS['violet']}; box-shadow: 0 0 24px rgba(178,107,255,0.13); }}
        footer, #MainMenu {{ visibility: hidden; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def status_pill(text: str, kind: str = "armed") -> str:
    return f'<div class="dd-status"><span class="dd-dot"></span>{text}</div>'


def hero(title: str, subtitle: str, status_text: str) -> None:
    st.markdown(
        f"""
        <div class="dd-hero">
            <div>
                <h1>{title}</h1>
                <p>{subtitle}</p>
            </div>
            {status_pill(status_text)}
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_header(title: str, right_label: str = "") -> None:
    st.markdown(
        f"""
        <div class="dd-section">
            <h3>{title}</h3>
            <span>{right_label}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def kpi_card(label: str, value: str, delta: str = "", delta_dir: str = "flat", accent: str = "cyan") -> str:
    delta_html = f'<div class="delta {delta_dir}">{delta}</div>' if delta else ""
    return f"""
        <div class="dd-kpi accent-{accent}">
            <div class="label">{label}</div>
            <div class="value">{value}</div>
            {delta_html}
        </div>
    """


def pill(text: str, kind: str) -> str:
    return f'<span class="dd-pill {kind}">{text}</span>'


# ---------------------------------------------------------------------------
# Sidebar — configuration panel shared by every page.
# Values live in st.session_state so they persist as the person moves
# between the Dashboard and Leaderboard pages.
# ---------------------------------------------------------------------------
def render_sidebar_config() -> dict:
    with st.sidebar:
        st.markdown(
            """
            <div style="padding-bottom:0.6rem;">
                <div style="font-weight:700; font-size:1.05rem;">🧬 Darwin Desk</div>
                <div style="color:#7c8aa3; font-size:0.78rem;">Simulation configuration</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("**Core parameters**")

        starting_capital = st.number_input(
            "Starting capital ($)",
            min_value=100,
            max_value=10_000_000,
            value=st.session_state.get("starting_capital", 10_000),
            step=500,
            key="starting_capital",
            help="Cash each bot is spawned with at generation zero.",
        )

        mutation_rate = st.slider(
            "Mutation rate (%)",
            min_value=0,
            max_value=100,
            value=st.session_state.get("mutation_rate", 12),
            key="mutation_rate",
            help="Chance that a surviving bot's parameters randomly mutate before the next generation.",
        )

        hard_deletion_threshold = st.slider(
            "Hard deletion threshold (% drawdown)",
            min_value=5,
            max_value=95,
            value=st.session_state.get("hard_deletion_threshold", 40),
            key="hard_deletion_threshold",
            help="A bot that draws down past this level is terminated immediately, regardless of any other rule.",
        )

        inactivity_timeout = st.number_input(
            "Inactivity timeout (generations)",
            min_value=1,
            max_value=100,
            value=st.session_state.get("inactivity_timeout", 5),
            key="inactivity_timeout",
            help="Bots that place no trades for this many generations are marked dormant, then purged.",
        )

        with st.expander("Advanced genetics", expanded=False):
            population_size = st.number_input(
                "Population size",
                min_value=2,
                max_value=2000,
                value=st.session_state.get("population_size", 50),
                key="population_size",
                help="Number of bots alive at once in a single generation.",
            )
            elite_survivors_pct = st.slider(
                "Elite survivors (%)",
                min_value=0,
                max_value=50,
                value=st.session_state.get("elite_survivors_pct", 10),
                key="elite_survivors_pct",
                help="Top percentage of bots, by profitability, that pass to the next generation untouched by mutation.",
            )
            max_generations = st.number_input(
                "Max generations (0 = unlimited)",
                min_value=0,
                max_value=10_000,
                value=st.session_state.get("max_generations", 200),
                key="max_generations",
            )
            risk_tolerance = st.select_slider(
                "Risk tolerance",
                options=["Low", "Medium", "High", "Degenerate"],
                value=st.session_state.get("risk_tolerance", "Medium"),
                key="risk_tolerance",
                help="Loosely caps position sizing and volatility once a strategy engine is connected.",
            )

        st.markdown("---")
        run_clicked = st.button("▶ Initialize population", width='stretch')
        if run_clicked:
            st.toast("Interface only — the evolution + trading engine isn't connected yet.", icon="🧬")

        st.markdown(
            """
            <div style="color:#4a5568; font-size:0.7rem; font-family:'JetBrains Mono',monospace; margin-top:1rem;">
                DARWIN DESK · UI BUILD v0.1<br>no live trading logic wired up
            </div>
            """,
            unsafe_allow_html=True,
        )

    return {
        "starting_capital": starting_capital,
        "mutation_rate": mutation_rate,
        "hard_deletion_threshold": hard_deletion_threshold,
        "inactivity_timeout": inactivity_timeout,
        "population_size": population_size,
        "elite_survivors_pct": elite_survivors_pct,
        "max_generations": max_generations,
        "risk_tolerance": risk_tolerance,
    }
