"""Portfolio construction shared by the market-risk and stress-testing modules."""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from data.universe import PORTFOLIO_NOTIONAL, TICKER_SECTOR, TICKERS  # noqa: E402,F401

PROCESSED = ROOT / "data" / "processed"
RESULTS = ROOT / "results"


def equal_weights(tickers=TICKERS):
    return pd.Series(1.0 / len(tickers), index=list(tickers))


def load_prices(history=False):
    name = "prices_history.csv" if history else "prices_core.csv"
    return pd.read_csv(PROCESSED / name, index_col="date", parse_dates=True)[TICKERS]


def asset_returns(prices):
    """Daily simple returns of each asset."""
    return prices.pct_change(fill_method=None).dropna(how="all")


def portfolio_returns(returns, weights):
    """Daily return of a portfolio rebalanced to constant `weights` every day."""
    return returns[weights.index].mul(weights, axis=1).sum(axis=1, min_count=1).dropna()


def ensure_results_dir():
    RESULTS.mkdir(exist_ok=True)
    return RESULTS
