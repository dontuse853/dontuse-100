from .supervisor import AgentState, SupervisorConfig, SupervisorEngine
from .bots import Signal, BotTemplate, TrendFollowerBot, MeanReversionBot, BreakoutBot, MASTER_TEMPLATES
from .market import synthetic_ohlc
from .data import (
    BENCHMARKS,
    resolve_ticker,
    download_price_history,
    download_many,
)
from .backtest import (
    BacktestResult,
    build_population,
    run_backtest,
    run_backtest_on_synthetic_market,
    run_backtest_on_ticker,
)

__all__ = [
    "AgentState",
    "SupervisorConfig",
    "SupervisorEngine",
    "Signal",
    "BotTemplate",
    "TrendFollowerBot",
    "MeanReversionBot",
    "BreakoutBot",
    "MASTER_TEMPLATES",
    "synthetic_ohlc",
    "BENCHMARKS",
    "resolve_ticker",
    "download_price_history",
    "download_many",
    "BacktestResult",
    "build_population",
    "run_backtest",
    "run_backtest_on_synthetic_market",
    "run_backtest_on_ticker",
]
