"""Data-quality checks fire on deliberately broken inputs."""
import numpy as np
import pandas as pd

from data.universe import TICKERS
from reporting.data_quality_checks import check_ohlcv, check_prices


def clean_prices(n=20):
    idx = pd.bdate_range("2024-01-01", periods=n)
    return pd.DataFrame({t: 100 + np.arange(n) * 0.5 for t in TICKERS}, index=idx)


def status(results, name_part):
    return next(r["status"] for r in results if name_part in r["check"])


def test_clean_prices_pass():
    res = check_prices(clean_prices())
    assert all(r["status"] == "PASS" for r in res)


def test_missing_stale_and_extreme_prices_flagged():
    p = clean_prices()
    p.iloc[3, 0] = np.nan                    # missing close
    p.iloc[5:9, 1] = 101.0                   # four identical closes
    p.iloc[12, 2] = p.iloc[11, 2] * 1.5      # +50% day
    res = check_prices(p)
    assert status(res, "no missing closes") == "FAIL"
    assert status(res, "stale") == "WARN"
    assert status(res, "daily moves") == "WARN"


def test_broken_ohlc_flagged():
    df = pd.DataFrame({"open": [10.0, 10.0], "high": [11.0, 9.0], "low": [9.0, 8.0],
                       "close": [10.5, 9.5], "volume": [100, 100]})
    res = check_ohlcv(df)
    assert res[0]["status"] == "FAIL"  # second row: high below open/close
