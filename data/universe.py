"""Single source of truth for the equity universe and date ranges.

Every name below has traded continuously since before October 2007, so the same universe can be
used for both the 5-year VaR window and the full-history stress replays (GFC, COVID, 2022).
"""

SECTORS = {
    "Technology": ["AAPL", "MSFT", "NVDA", "ORCL", "CSCO"],
    "Financials": ["JPM", "BAC", "GS", "MS", "WFC"],
    "Health Care": ["JNJ", "PFE", "MRK", "UNH", "ABT"],
    "Energy": ["XOM", "CVX", "COP", "SLB", "OXY"],
    "Consumer": ["WMT", "PG", "KO", "MCD", "HD"],
    "Industrials": ["CAT", "BA", "HON", "UPS", "DE"],
}

TICKERS = [t for names in SECTORS.values() for t in names]
TICKER_SECTOR = {t: s for s, names in SECTORS.items() for t in names}

# Banks are excluded from ratio-based credit scoring: their balance sheets have no current/
# non-current split and Altman-style ratios are not meaningful for them.
CREDIT_TICKERS = [t for t in TICKERS if TICKER_SECTOR[t] != "Financials"]

# Reference series used for stress-scenario calibration and factor betas.
MARKET_INDEX = "^GSPC"   # S&P 500
RATE_INDEX = "^TNX"      # CBOE 10-year Treasury yield index (yield in percent)

# Core analysis window (VaR / ES / backtest). End is exclusive in yfinance.
CORE_START = "2021-10-01"
CORE_END = "2026-10-01"

# Long history for scenario replay (stocks) and rate-shock calibration (indexes back to 1993).
HISTORY_START_STOCKS = "2007-01-01"
HISTORY_START_INDEX = "1993-01-01"

PORTFOLIO_NOTIONAL = 10_000_000  # USD, equal-weighted across TICKERS
