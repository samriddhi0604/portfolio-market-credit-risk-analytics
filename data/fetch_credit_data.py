"""Pull real annual financial-statement data from SEC EDGAR's XBRL `companyfacts` API.

Endpoint: https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json (no API key; SEC asks
for a descriptive User-Agent — override via the SEC_USER_AGENT environment variable).

Only figures reported on annual reports (form 10-K, fiscal period FY) are kept. Flow items
(revenue, net income, cash flow) must cover a ~12-month duration; balance-sheet items are point-
in-time at the fiscal year end. Where a figure was reported in several filings (the original 10-K
and later 10-Ks as a comparative), the most recently filed value is used, so restatements win.

Outputs (data/processed/):
  financials_annual.csv   one row per (ticker, fiscal_year_end) with the core line items
  financials_sources.csv  which XBRL tag and which accession number each figure came from
"""
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data.universe import CREDIT_TICKERS  # noqa: E402

RAW = Path(__file__).resolve().parent / "raw" / "edgar"
PROCESSED = Path(__file__).resolve().parent / "processed"

# SEC rejects requests (HTTP 403) unless the User-Agent names the requester and a contact email,
# e.g.  SEC_USER_AGENT="Jane Doe jane@example.com" python data/fetch_credit_data.py
USER_AGENT = os.environ.get("SEC_USER_AGENT")
HEADERS = {"User-Agent": USER_AGENT or "", "Accept-Encoding": "gzip, deflate"}

N_YEARS = 5

# SEC's ticker map points to the *current* registrant. When a company re-domiciles under a new
# holding company, the new CIK has no 10-K history yet, so annual data is read from the
# predecessor registrant instead.
#   XOM: ExxonMobil Holdings Corp (CIK 2115436) became the listed parent in mid-2026 and had only
#        filed 10-Qs as of the data pull; Exxon Mobil Corporation (CIK 34088) filed every 10-K.
PREDECESSOR_CIK = {"XOM": 34088}

# Line item -> candidate us-gaap tags in priority order (companies differ in tag choice).
CONCEPTS = {
    "total_assets": ["Assets"],
    "total_liabilities": ["Liabilities"],
    "stockholders_equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "total_equity_incl_nci": [
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        "StockholdersEquity",
    ],
    "current_assets": ["AssetsCurrent"],
    "current_liabilities": ["LiabilitiesCurrent"],
    "retained_earnings": ["RetainedEarningsAccumulatedDeficit"],
    "revenue": [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
    ],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "pretax_income": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic",
    ],
    "interest_expense": [
        "InterestExpense",
        "InterestExpenseNonoperating",
        "InterestExpenseDebt",
        "InterestAndDebtExpense",
        "InterestPaidNet",
    ],
    "operating_cash_flow": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
}
FLOW_ITEMS = {"revenue", "operating_income", "net_income", "pretax_income", "interest_expense",
              "operating_cash_flow"}


def get_json(url):
    for attempt in range(4):
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 503):
            time.sleep(2 ** attempt)
            continue
        r.raise_for_status()
    r.raise_for_status()


def cik_map():
    data = get_json("https://www.sec.gov/files/company_tickers.json")
    return {row["ticker"]: int(row["cik_str"]) for row in data.values()}


def annual_series(facts, tag, is_flow):
    """Return {period_end: (value, accession, filed)} for annual 10-K values of one tag."""
    node = facts.get("facts", {}).get("us-gaap", {}).get(tag)
    if not node or "USD" not in node.get("units", {}):
        return {}
    df = pd.DataFrame(node["units"]["USD"])
    df = df[df["form"].isin(["10-K", "10-K/A"]) & (df["fp"] == "FY")]
    if df.empty:
        return {}
    df["end"] = pd.to_datetime(df["end"])
    if is_flow:
        df = df.dropna(subset=["start"])
        days = (df["end"] - pd.to_datetime(df["start"])).dt.days
        df = df[(days >= 350) & (days <= 380)]
    df = df.sort_values("filed").drop_duplicates("end", keep="last")
    return {row.end: (row.val, row.accn, row.filed) for row in df.itertuples()}


def extract_company(ticker, facts):
    records, sources = {}, []
    for item, tags in CONCEPTS.items():
        merged = {}
        # Earlier tags take priority; later tags only fill period ends the earlier ones miss
        # (handles companies that switched tags, e.g. SalesRevenueNet -> ASC 606 revenue).
        for tag in tags:
            for end, (val, accn, filed) in annual_series(facts, tag, item in FLOW_ITEMS).items():
                if end not in merged:
                    merged[end] = (val, accn, filed, tag)
        for end, (val, accn, filed, tag) in merged.items():
            records.setdefault(end, {})[item] = val
            sources.append({"ticker": ticker, "period_end": end.date(), "item": item,
                            "tag": tag, "accession": accn, "filed": filed})
    df = pd.DataFrame.from_dict(records, orient="index").sort_index()
    df.index.name = "period_end"
    return df, sources


def main():
    if not USER_AGENT:
        sys.exit('Set SEC_USER_AGENT to "<name> <contact email>" (required by SEC fair-access '
                 "policy) before running this script.")
    RAW.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(exist_ok=True)
    ciks = cik_map()

    frames, all_sources = [], []
    for ticker in CREDIT_TICKERS:
        cik = PREDECESSOR_CIK.get(ticker, ciks[ticker])
        facts = get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json")
        pd.Series(facts.get("entityName")).to_json(RAW / f"{ticker}_entity.json")
        df, sources = extract_company(ticker, facts)
        if not {"revenue", "total_assets"} <= set(df.columns):
            raise RuntimeError(f"{ticker} (CIK {cik}) has no annual 10-K revenue/assets facts; "
                               "check for a registrant change and add it to PREDECESSOR_CIK")
        # Fiscal year ends are anchored on the revenue series (always present on a 10-K income
        # statement) so stray balance-sheet-only dates don't create phantom years.
        years = df.dropna(subset=["revenue", "total_assets"]).tail(N_YEARS)
        years = years.assign(ticker=ticker, cik=cik, entity_name=facts.get("entityName"))
        frames.append(years.reset_index())
        keep = set(years.index)
        all_sources += [s for s in sources if pd.Timestamp(s["period_end"]) in keep]
        print(f"{ticker:5s} CIK {cik:>7d}  {len(years)} fiscal years  "
              f"{years.index.min().date()} -> {years.index.max().date()}")
        time.sleep(0.15)  # stay well under SEC's 10 requests/second fair-access limit

    out = pd.concat(frames, ignore_index=True)
    # Some filers (e.g. Apple, Microsoft) never tag total Liabilities; derive it from the
    # balance-sheet identity rather than dropping the company, and flag that it was derived.
    total_equity_proxy = out["total_equity_incl_nci"]
    derived = out["total_liabilities"].isna() & out["total_assets"].notna() & total_equity_proxy.notna()
    out.loc[derived, "total_liabilities"] = out.loc[derived, "total_assets"] - total_equity_proxy[derived]
    out["liabilities_derived"] = derived
    # EBIT: reported operating income where tagged; otherwise pre-tax income + interest expense
    # (several oil majors and pharma companies do not report an operating-income subtotal).
    out["ebit"] = out["operating_income"].fillna(out["pretax_income"] + out["interest_expense"].fillna(0))
    out["ebit_source"] = out["operating_income"].notna().map(
        {True: "operating_income", False: "pretax_plus_interest"})
    out.loc[out["ebit"].isna(), "ebit_source"] = None
    out["fiscal_year"] = out["period_end"].dt.year
    cols = ["ticker", "cik", "entity_name", "fiscal_year", "period_end"] + list(CONCEPTS) + [
        "ebit", "ebit_source", "liabilities_derived"]
    out = out[cols].sort_values(["ticker", "period_end"])
    out.to_csv(PROCESSED / "financials_annual.csv", index=False)
    pd.DataFrame(all_sources).to_csv(PROCESSED / "financials_sources.csv", index=False)

    # --- Verification ---------------------------------------------------------------------
    print("\n=== Verification ===")
    print(f"financials_annual: shape={out.shape}, companies={out['ticker'].nunique()}, "
          f"period ends {out['period_end'].min().date()} -> {out['period_end'].max().date()}")
    print("Missing values per line item:")
    print(out[list(CONCEPTS) + ["ebit"]].isna().sum().to_string())
    print("EBIT source counts:", out["ebit_source"].value_counts().to_dict())
    print(f"Total liabilities derived as assets - equity for {int(derived.sum())} rows")
    spot = out[out["ticker"].isin(["AAPL", "MSFT", "WMT"])][
        ["ticker", "period_end", "revenue", "net_income", "total_assets"]]
    print("\nSpot check (USD bn):")
    print((spot.set_index(["ticker", "period_end"]) / 1e9).round(3).to_string())


if __name__ == "__main__":
    main()
