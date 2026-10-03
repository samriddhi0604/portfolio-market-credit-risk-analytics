"""Credit-analysis ratios from SEC EDGAR 10-K data.

Ratios (per company, per fiscal year):
  leverage       liabilities_to_assets = total liabilities / total assets
                 liabilities_to_equity = total liabilities / stockholders' equity
                                         (undefined -> NaN when equity <= 0)
  liquidity      current_ratio         = current assets / current liabilities
  coverage       ocf_to_liabilities    = operating cash flow / total liabilities
  profitability  net_margin            = net income / revenue
                 roa                   = net income / total assets (year-end)

Altman Z'' (Altman, 1995 — the non-manufacturer / emerging-market version):
    Z'' = 6.56*X1 + 3.26*X2 + 6.72*X3 + 1.05*X4
      X1 = working capital / total assets
      X2 = retained earnings / total assets
      X3 = EBIT / total assets
      X4 = book equity / total liabilities
    Zones: Z'' > 2.60 safe, 1.10-2.60 grey, < 1.10 distress.
  Z'' is used instead of the original 1968 Z because it needs no market capitalisation and no
  sales/assets term (which is heavily industry-dependent), so every input comes from the filing.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PROCESSED = ROOT / "data" / "processed"

Z_SAFE, Z_DISTRESS = 2.60, 1.10


def _div(a, b):
    a, b = pd.to_numeric(a), pd.to_numeric(b)
    return a / b.where(b != 0)


def altman_z2(working_capital, retained_earnings, ebit, book_equity, total_assets,
              total_liabilities):
    x1 = _div(working_capital, total_assets)
    x2 = _div(retained_earnings, total_assets)
    x3 = _div(ebit, total_assets)
    x4 = _div(book_equity, total_liabilities)
    return 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4


def altman_zone(z):
    return pd.Series(np.select([z > Z_SAFE, z >= Z_DISTRESS], ["safe", "grey"], "distress"),
                     index=z.index).where(z.notna())


def compute_ratios(fin):
    """Return a ratio table for a frame with the columns produced by fetch_credit_data.py."""
    out = fin[["ticker", "fiscal_year", "period_end"]].copy()
    equity = fin["stockholders_equity"]
    out["liabilities_to_assets"] = _div(fin["total_liabilities"], fin["total_assets"])
    out["liabilities_to_equity"] = _div(fin["total_liabilities"], equity.where(equity > 0))
    out["current_ratio"] = _div(fin["current_assets"], fin["current_liabilities"])
    out["ocf_to_liabilities"] = _div(fin["operating_cash_flow"], fin["total_liabilities"])
    out["net_margin"] = _div(fin["net_income"], fin["revenue"])
    out["roa"] = _div(fin["net_income"], fin["total_assets"])
    out["altman_z2"] = altman_z2(
        fin["current_assets"] - fin["current_liabilities"], fin["retained_earnings"],
        fin["ebit"], equity, fin["total_assets"], fin["total_liabilities"])
    out["altman_zone"] = altman_zone(out["altman_z2"])
    out["negative_equity"] = equity <= 0
    return out


def load_financials():
    return pd.read_csv(PROCESSED / "financials_annual.csv", parse_dates=["period_end"])


def main():
    ratios = compute_ratios(load_financials())
    ratios.to_csv(ROOT / "results" / "credit_ratios.csv", index=False)
    latest = ratios.sort_values("period_end").groupby("ticker").tail(1).set_index("ticker")
    print("Latest fiscal year ratios:")
    print(latest.drop(columns=["fiscal_year"]).round(3).to_string())


if __name__ == "__main__":
    main()
