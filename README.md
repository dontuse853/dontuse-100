# Darwin Desk — interface preview

A dashboard shell for an evolutionary trading-bot simulator: bots that
replicate when profitable and get deleted when they aren't. **This is UI
only** — there is no trading logic, no brokerage connection, and no
evolutionary algorithm running yet. Every chart and table is sample data,
clearly labeled as such, so you can review the layout before wiring up
the real engine.

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open the URL Streamlit prints (usually `http://localhost:8501`).
The **Leaderboard** page appears automatically in the sidebar nav —
Streamlit picks up everything in `pages/`.

## What's here

```
darwin_desk/
├── app.py                     # Main dashboard (hero, KPIs, chart tabs, top-bots preview)
├── pages/
│   └── 1_Leaderboard.py    # Full ranked table + podium + filters
├── utils.py                   # Shared theme/CSS, sidebar config panel, HTML components
├── .streamlit/config.toml     # Dark theme base colors
└── requirements.txt
```

## Configuration panel (sidebar)

Lives in `utils.py:render_sidebar_config()` and is shared by every page
via `st.session_state`, so values stay in sync as you navigate:

- **Starting capital** — cash each bot spawns with
- **Mutation rate (%)** — odds a surviving bot's parameters mutate before the next generation
- **Hard deletion threshold (% drawdown)** — instant termination line, independent of any other rule
- **Inactivity timeout (generations)** — no trades for this long → marked dormant, then purged
- Advanced: population size, elite survivor %, max generations, risk tolerance

## Supervisor engine (`engine/supervisor.py`)

This is real, tested logic — not a placeholder like the dashboard's
mock data. It manages agent *lifecycle*, not trading decisions:

- **`SupervisorEngine.scaled_position_size_pct(agent)`** — as an
  agent's drawdown climbs toward `hard_deletion_threshold`, its
  "survival factor" falls from 1.0 toward a small floor
  (`min_survival_factor`), and position size is scaled down to match.
  The falloff curve is convex by default (`survival_curve_exponent`),
  so a bot keeps close to full size for most of its runway and only
  really throttles down near the edge.
- **`SupervisorEngine.record_tick(agent, traded)`** — call once per
  generation per agent. Trading resets its inactivity countdown to
  `inactivity_timeout`; not trading ticks it down by one. Read
  `engine.telemetry(agent)` at any point to see the countdown, whether
  it's in the "critical" warning window, and its current scaled size —
  that's the visibility a strategy needs to see a stagnation death
  coming and act before it happens.
- **`SupervisorEngine.run_deletion_sequence(generation)`** — sweeps
  every active agent each generation, purges anyone whose drawdown has
  hit `hard_deletion_threshold` *or* whose countdown hit zero (capital
  death takes priority if both are true at once), and moves them from
  `engine.active` into `engine.graveyard` with the cause and
  generation recorded.

Try it:

```bash
python demo_supervisor.py   # watch a mixed population survive, throttle, and get purged
python -m pytest tests/     # 14 tests covering scaling, inactivity, and deletion
```

`SupervisorConfig.from_dashboard_config(cfg)` maps straight from the
dict `utils.render_sidebar_config()` returns, so the sidebar can drive
this engine directly once you're ready to wire it into `app.py`.

## Bot archetypes (`engine/bots.py`)

The "master templates" — generation-zero bots the rest of the
population replicates from via `clone_and_mutate()`, which nudges each
numeric parameter by up to ±35% (bounded by `param_bounds`) with
independent odds per parameter set by the mutation rate:

- **`TrendFollowerBot`** — fast/slow EMA crossover confirmed by simple
  momentum. Reads every bar printed so far, including the newest one,
  and only takes a position when both agree on direction. Built for
  trending markets.
- **`MeanReversionBot`** — Bollinger Bands + RSI. Fades price back
  toward the mean when it pokes outside a band *and* RSI confirms
  overbought/oversold; sits out anything inside the bands. Built for
  range-bound, choppy markets.
- **`BreakoutBot`** — Donchian channel breakout, gated by an ATR
  volatility-expansion check, so it only fires when price clears its
  recent range *and* the market is genuinely more volatile than its
  own recent norm. Built to catch sudden, news-driven spikes rather
  than grind.

Each archetype computes its indicators two ways for the same logic:
`generate_signal(bars)` is a simple one-shot call (what the tests and
`demo_bots.py` use), while `precompute()` + `_signal_at()` vectorize
the same math once over an entire price history — that's what
`engine/backtest.py` and the dashboard use so a few dozen bots over a
few hundred bars stays fast inside a Streamlit rerun.

## Backtest harness (`engine/backtest.py`, `engine/market.py`)

`run_backtest()` wires the archetypes + supervisor together against a
synthetic, regime-switching price series (`synthetic_ohlc` — NOT real
market data): a trending phase, then a choppy range-bound phase, then
a volatility squeeze and spike, so each archetype gets a stretch of
price action suited to what it's designed to trade. `bars_per_generation`
batches raw bars into the "generations" `inactivity_timeout` counts in,
so a deliberately selective strategy (mean reversion, breakout) isn't
punished for sitting out individual bars while it waits for a real
setup.

Try it:

```bash
python demo_bots.py   # trend follower profits in the trend phase, breakout waits for its spike, etc.
```

## Historical data utility (`engine/data.py`)

`download_price_history(ticker, start=None, end=None, period=None, interval="1d")`
pulls real daily OHLC bars via [yfinance](https://pypi.org/project/yfinance/)
and normalizes the result to exactly the Open/High/Low/Close schema
`engine/market.py`'s synthetic data already uses — so real history is
a drop-in replacement anywhere a price DataFrame is expected. Time
frame is customizable either way:

```python
from engine.data import download_price_history

download_price_history("SPY", start="2022-01-01", end="2024-01-01")
download_price_history("BTC", period="2y")          # friendly name -> "BTC-USD"
download_price_history("NVDA", period="6mo", interval="1d")
```

`BENCHMARKS` maps a few friendly names to their actual ticker (`SPY`,
`QQQ`, `DIA`, `BTC` → `BTC-USD`, `ETH` → `ETH-USD`, `GOLD` → `GC=F`);
anything else is passed straight through to yfinance. `download_many(["SPY", "BTC"], period="1y")`
pulls several at once. On a bad ticker, empty result, or no network,
it raises a clear `RuntimeError` rather than ever silently handing
back fake data dressed up as real — a finance chart should never look
real when it isn't.

*(This sandbox's network egress doesn't include Yahoo Finance's hosts,
so the download itself couldn't be tested live here — the wrapper
logic is covered by 12 tests against a mocked `yfinance.download`, and
`demo_real_data.py`'s full pipeline was verified end-to-end the same
way. It'll hit the real network the moment you run it somewhere that
has Yahoo Finance reachable.)*

## The core backtest loop is now data-source-agnostic

`run_backtest(config, price, ...)` in `engine/backtest.py` no longer
generates its own price data — it takes any OHLC DataFrame and feeds
it bar by bar to every currently active agent simultaneously, same as
before. Two thin wrappers cover the two data sources this project
ships with:

- `run_backtest_on_synthetic_market(config, n_bars=420, price_seed=7, ...)` — the regime-switching synthetic market, for demos/tests
- `run_backtest_on_ticker(config, ticker, start=None, end=None, period=None, ...)` — downloads real data first, then runs the same loop

Each bar, for every active agent: a signal is computed, the trade's
P&L is calculated and applied to that agent's capital (and logged to
`result.trade_log`), the supervisor manages the outcome (survival-scaled
sizing, inactivity countdown, deletion sequence), and the agent's
capital is appended to its own individual equity line
(`result.equity_curves[bot_id]`). Summing every agent's equity at each
bar gives `result.total_equity` — the cumulative ecosystem equity
curve the "Total population P&L" dashboard tab charts.

`result.trade_log` is a list of every executed trade in order — each
entry has `step`, `date` (from the price index — a real date for real
data), `bot_id`, `archetype`, `action`, `strength`, `reason`,
`position_size_pct`, `pnl_dollars`, and `capital_after`.

Try the real-data path:

```bash
python demo_real_data.py                                  # SPY, last 2 years
python demo_real_data.py --ticker BTC --period 2y
python demo_real_data.py --ticker SPY --start 2022-01-01 --end 2024-01-01
```

## Two fixes worth knowing about

**Does an unprofitable bot actually die?** Yes, but via
`hard_deletion_threshold` — a configurable *drawdown %*, not "any
single negative P&L instantly kills it." A bot has to fall that far
below its starting capital before the deletion sequence purges it;
normal trading noise dips negative constantly, so a literal
any-negative-P&L-means-death rule would wipe out the whole population
almost immediately. If you want that harsher behavior, set the sidebar's
hard deletion threshold very low (close to 0%) — otherwise it's already
doing "sustained unprofitability kills you," just with a buffer for noise.

**Did mutation actually produce variation?** Not always — it does now.
`clone_and_mutate()` applies the mutation rate independently per
parameter, and at realistic rates (5-15%) with only 3-5 parameters per
archetype, roughly half of all "children" were rolling zero mutations
on every parameter and coming out as exact duplicates of their master
wearing a new ID — confirmed empirically at 53-70% duplicate rates
before the fix. `clone_and_mutate()` now guarantees every clone differs
from its parent by at least one parameter whenever the mutation rate is
above 0% (0% stays a genuine off-switch — no forced mutation, true
identical clones, since that's an explicit choice to disable it). Also
fixed a subtler version of the same bug: a "successful" mutation roll
could still round-trip an integer parameter back to its original value
and silently count as a real change when it wasn't — now only an
actually-different value counts. `mutation_delta_pct(other)` gives a
rough "how far has this clone drifted from its parent" number, shown on
the new Bot-100 page below. All fixed in `engine/bots.py`, covered by
new tests in `tests/test_bots.py`.

## Bot-100 (`pages/2_Bot100.py`)

A new page that runs a much larger population than the main
dashboard — 168 bots (55 mutated children per archetype instead of up
to 8) — through the same real backtest, keeps only the ones that
finished profitable, and ranks up to the top 100 by return. Shows P&L
%, $ profit, generations survived, alive/deleted status (with cause),
and each bot's mutation drift from its archetype's master template
(👑), plus a per-archetype breakdown of how many profitable bots each
strategy produced. "Bot-100" is the page's name, not a guarantee of
exactly 100 rows — with a harsh hard-deletion threshold or inactivity
timeout there may honestly be fewer than 100 profitable bots, and
that's what gets shown.

This page has its own cached backtest (bigger population than the
dashboard's, same sidebar parameters) — moving a sidebar slider
recomputes both this page's and the main dashboard's backtests
independently.

## Dashboard wiring

`app.py`'s "Total population P&L", "Per-bot equity curves", and
"Fitness distribution" tabs now run this real backtest off whatever
you set in the sidebar (cached with `st.cache_data` so moving a slider
only recomputes when a value actually changes). The **Total population
P&L** tab is every bot's full profit history layered under a bold
total line, bounded by a ±0.8x reference channel scaled to the widest
individual swing — a stock-chart-style view of the whole population's
combined performance. Only the "Lineage map" tab is still a schematic
placeholder, since generation-over-generation reproduction across the
whole population (not just one-shot mutation from the three masters)
isn't wired up yet.

The dashboard still runs `run_backtest_on_synthetic_market` — it isn't
wired to `run_backtest_on_ticker` yet, since pulling real data into a
Streamlit rerun needs its own UX (a ticker/date picker, a loading
state, a visible error if the download fails) rather than silently
reusing the sidebar's existing controls. That, and pulling the
Leaderboard page onto this same cached backtest, are the natural next
steps.

## Wiring in the real engine (next steps)

Everything that needs to be replaced is marked `mock_*` in `app.py` and
`pages/1_Leaderboard.py`:

- `mock_kpis`, `mock_equity_curves`, `mock_fitness_distribution`, `mock_population_tree` in `app.py`
- `mock_leaderboard` in the Leaderboard page

Swap each for a call into your actual simulation state (a DataFrame, a
DB query, a websocket feed — whatever it ends up being) and the layout,
styling, and filters keep working unchanged. The "▶ Initialize
population" button in the sidebar currently just shows a toast — that's
the hook point for actually starting a run.
