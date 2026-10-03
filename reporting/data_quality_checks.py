"""Data-integrity checks on the ingested market and financial-statement data.

Each check returns a dict {check, dataset, status, detail} with status PASS / WARN / FAIL:
  FAIL = data that would silently corrupt a risk number (missing prices, broken OHLC, negative
         assets) and should block the report;
  WARN = data that is plausibly real but needs a human look (a 20% one-day move, a derived
         liabilities figure, a balance sheet that doesn't tie out exactly).
"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from data.universe import CREDIT_TICKERS, TICKERS  # noqa: E402

PROCESSED = ROOT / "data" / "processed"
RESULTS = ROOT / "results"

STALE_RUN_DAYS = 3            # identical closes this many days in a row = possible stale feed
EXTREME_MOVE = 0.20           # |daily return| above this is flagged for review
MAX_GAP_CALENDAR_DAYS = 5     # longer gaps than a long weekend + holiday
MAX_FILING_AGE_DAYS = 550     # latest 10-K period older than ~18 months is stale
BS_TIE_TOLERANCE = 0.02       # |A - L - E| / A tolerance (mezzanine/temporary equity, rounding)


def _result(check, dataset, ok, detail, severity="FAIL"):
    return {"check": check, "dataset": dataset, "status": "PASS" if ok else severity,
            "detail": detail}


def check_prices(prices, as_of=None):
    out = []
    missing_tickers = sorted(set(TICKERS) - set(prices.columns))
    out.append(_result("all tickers present", "prices", not missing_tickers,
                       f"missing: {missing_tickers}" if missing_tickers else
                       f"{len(TICKERS)}/{len(TICKERS)} tickers"))

    n_missing = prices.isna().sum()
    bad = n_missing[n_missing > 0]
    out.append(_result("no missing closes", "prices", bad.empty,
                       bad.to_dict() if not bad.empty else "0 missing values"))

    nonpos = (prices <= 0).sum()
    nonpos = nonpos[nonpos > 0]
    out.append(_result("prices strictly positive", "prices", nonpos.empty,
                       nonpos.to_dict() if not nonpos.empty else "all > 0"))

    stale = {}
    for t in prices.columns:
        same = prices[t].diff().eq(0)
        run = same.groupby((~same).cumsum()).cumsum().max()
        if run >= STALE_RUN_DAYS:
            stale[t] = int(run)
    out.append(_result(f"no stale prices (>= {STALE_RUN_DAYS} identical closes)", "prices",
                       not stale, stale or "none found", "WARN"))

    rets = prices.pct_change(fill_method=None)
    extreme = rets[rets.abs() > EXTREME_MOVE].stack().dropna()
    detail = {f"{t} {d.date()}": round(float(v), 4) for (d, t), v in extreme.items()}
    out.append(_result(f"no daily moves > {EXTREME_MOVE:.0%}", "prices", extreme.empty,
                       detail or "none", "WARN"))

    gaps = prices.index.to_series().diff().dt.days
    big = gaps[gaps > MAX_GAP_CALENDAR_DAYS]
    out.append(_result(f"no date gaps > {MAX_GAP_CALENDAR_DAYS} calendar days", "prices",
                       big.empty, {str(d.date()): int(g) for d, g in big.items()} or "none"))

    if as_of is not None:
        lag = (pd.Timestamp(as_of) - prices.index.max()).days
        out.append(_result("price history is current", "prices", lag <= 7,
                           f"last date {prices.index.max().date()}, {lag} days before {as_of}",
                           "WARN"))
    return out


def check_ohlcv(ohlcv):
    hi_bad = ohlcv["high"] < ohlcv[["open", "close"]].max(axis=1) - 1e-6
    lo_bad = ohlcv["low"] > ohlcv[["open", "close"]].min(axis=1) + 1e-6
    vol_bad = ohlcv["volume"] < 0
    n = int(hi_bad.sum() + lo_bad.sum())
    return [
        _result("OHLC consistent (low <= open,close <= high)", "ohlcv", n == 0,
                f"{n} inconsistent rows of {len(ohlcv)}"),
        _result("volume non-negative", "ohlcv", not vol_bad.any(),
                f"{int(vol_bad.sum())} negative-volume rows"),
    ]


def check_financials(fin, as_of=None):
    out = []
    counts = fin.groupby("ticker").size()
    short = counts[counts < 5]
    missing = sorted(set(CREDIT_TICKERS) - set(counts.index))
    out.append(_result("5 fiscal years per company", "financials",
                       short.empty and not missing,
                       {"short": short.to_dict(), "missing": missing}
                       if (not short.empty or missing) else f"{len(counts)} companies x 5 years"))

    out.append(_result("total assets positive", "financials", (fin["total_assets"] > 0).all(),
                       f"{int((fin['total_assets'] <= 0).sum())} non-positive"))

    la = fin["total_liabilities"] / fin["total_assets"]
    mask = (la < 0) | (la > 1.5)
    odd = fin.loc[mask, ["ticker", "fiscal_year"]].assign(ratio=la[mask].round(3))
    out.append(_result("liabilities/assets within [0, 1.5]", "financials", odd.empty,
                       odd.to_dict(orient="records") or "all in range", "WARN"))

    cr = fin["current_assets"] / fin["current_liabilities"]
    odd = fin.loc[(cr <= 0) | (cr > 10), ["ticker", "fiscal_year"]]
    out.append(_result("current ratio within (0, 10]", "financials", odd.empty,
                       odd.to_dict(orient="records") or "all in range (NaN excluded)", "WARN"))

    margin = fin["net_income"] / fin["revenue"]
    odd = fin.loc[margin.abs() > 1, ["ticker", "fiscal_year"]]
    out.append(_result("|net margin| <= 100%", "financials", odd.empty,
                       odd.to_dict(orient="records") or "all in range", "WARN"))

    reported = fin[~fin["liabilities_derived"]]
    gap = ((reported["total_assets"] - reported["total_liabilities"]
            - reported["total_equity_incl_nci"]).abs() / reported["total_assets"])
    off = reported.loc[gap > BS_TIE_TOLERANCE, ["ticker", "fiscal_year"]].assign(
        gap_pct=(gap[gap > BS_TIE_TOLERANCE] * 100).round(2))
    out.append(_result(f"balance sheet ties out within {BS_TIE_TOLERANCE:.0%} "
                       "(reported liabilities only)", "financials", off.empty,
                       off.to_dict(orient="records") or f"{len(reported)} rows tie out", "WARN"))

    derived = fin.groupby("ticker")["liabilities_derived"].any()
    derived = sorted(derived[derived].index)
    out.append(_result("total liabilities reported directly", "financials", not derived,
                       f"derived as assets - equity for: {derived}", "WARN"))

    if as_of is not None:
        latest = fin.groupby("ticker")["period_end"].max()
        age = (pd.Timestamp(as_of) - latest).dt.days
        stale = age[age > MAX_FILING_AGE_DAYS]
        out.append(_result(f"latest 10-K period within {MAX_FILING_AGE_DAYS} days", "financials",
                           stale.empty, stale.to_dict() or "all current", "WARN"))
    return out


def run_all(as_of=None):
    prices = pd.read_csv(PROCESSED / "prices_core.csv", index_col="date", parse_dates=True)
    ohlcv = pd.read_csv(PROCESSED / "ohlcv_core.csv")
    fin = pd.read_csv(PROCESSED / "financials_annual.csv", parse_dates=["period_end"])
    as_of = as_of or pd.Timestamp.today().normalize()
    return check_prices(prices, as_of) + check_ohlcv(ohlcv) + check_financials(fin, as_of)


def main():
    results = run_all()
    for r in results:
        print(f"[{r['status']:4s}] {r['dataset']:10s} {r['check']}")
        if r["status"] != "PASS":
            print(f"         {r['detail']}")
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "data_quality.json").write_text(json.dumps(results, indent=2, default=str))
    n_fail = sum(r["status"] == "FAIL" for r in results)
    n_warn = sum(r["status"] == "WARN" for r in results)
    print(f"\n{len(results)} checks: {len(results) - n_fail - n_warn} pass, {n_warn} warn, "
          f"{n_fail} fail")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
