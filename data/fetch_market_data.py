"""Pull real daily OHLCV data from Yahoo Finance (yfinance) for the equity universe.

Outputs (data/processed/):
  ohlcv_core.csv         long-format OHLCV for the core 5-year window (split/dividend adjusted)
  prices_core.csv        wide adjusted-close panel for the core window (dates x tickers)
  prices_history.csv     wide adjusted-close panel 2007->today, used for stress-scenario replay
  index_history.csv      S&P 500 level and 10Y Treasury yield since 1993, for scenario calibration
"""
import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data.universe import (  # noqa: E402
    CORE_END, CORE_START, HISTORY_START_INDEX, HISTORY_START_STOCKS, MARKET_INDEX, RATE_INDEX,
    TICKERS,
)

RAW = Path(__file__).resolve().parent / "raw"
PROCESSED = Path(__file__).resolve().parent / "processed"


def download(tickers, start, end):
    df = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False,
                     group_by="column", threads=True)
    if df.empty:
        raise RuntimeError(f"yfinance returned no data for {tickers}")
    return df


def main():
    RAW.mkdir(exist_ok=True)
    PROCESSED.mkdir(exist_ok=True)

    print(f"Downloading {len(TICKERS)} tickers {HISTORY_START_STOCKS} -> {CORE_END} ...")
    stocks = download(TICKERS, HISTORY_START_STOCKS, CORE_END)
    stocks.to_csv(RAW / "stocks_full_raw.csv")

    missing = [t for t in TICKERS if stocks["Close"][t].dropna().empty]
    if missing:
        raise RuntimeError(f"No price data returned for: {missing}")

    close_hist = stocks["Close"][TICKERS].dropna(how="all")
    close_hist.index.name = "date"
    close_hist.to_csv(PROCESSED / "prices_history.csv")

    core = stocks.loc[CORE_START:]
    long = (core.stack(level=1, future_stack=True).rename_axis(["date", "ticker"]).reset_index()
            [["date", "ticker", "Open", "High", "Low", "Close", "Volume"]]
            .dropna(subset=["Close"]).sort_values(["ticker", "date"]))
    long.columns = [c.lower() for c in long.columns]
    long.to_csv(PROCESSED / "ohlcv_core.csv", index=False)

    prices_core = close_hist.loc[CORE_START:]
    prices_core.to_csv(PROCESSED / "prices_core.csv")

    print(f"Downloading {MARKET_INDEX}, {RATE_INDEX} {HISTORY_START_INDEX} -> {CORE_END} ...")
    idx = download([MARKET_INDEX, RATE_INDEX], HISTORY_START_INDEX, CORE_END)["Close"]
    idx = idx.rename(columns={MARKET_INDEX: "spx", RATE_INDEX: "ust10y_yield_pct"})
    idx.index.name = "date"
    idx.dropna(how="all").to_csv(PROCESSED / "index_history.csv")

    # --- Verification ---------------------------------------------------------------------
    print("\n=== Verification ===")
    print(f"prices_core:    shape={prices_core.shape}, "
          f"{prices_core.index.min().date()} -> {prices_core.index.max().date()}, "
          f"NaNs={int(prices_core.isna().sum().sum())}")
    print(f"prices_history: shape={close_hist.shape}, "
          f"{close_hist.index.min().date()} -> {close_hist.index.max().date()}")
    print(f"ohlcv_core:     rows={len(long)}, tickers={long['ticker'].nunique()}")
    print(f"index_history:  shape={idx.shape}, "
          f"{idx.index.min().date()} -> {idx.index.max().date()}")
    print("\nLast available adjusted close (spot check):")
    print(prices_core.iloc[-1].round(2).to_string())


if __name__ == "__main__":
    main()
