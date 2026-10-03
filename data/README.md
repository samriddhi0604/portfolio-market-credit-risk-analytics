# Data

All data in `processed/` is pulled from real public sources by the two fetch scripts. Nothing is
synthetic. Re-running the scripts reproduces the files (Yahoo Finance may revise adjusted prices
slightly when new dividends/splits occur; SEC values only change if a company restates).

Data pull date: **2026-10-03**.

## Market data — Yahoo Finance via `yfinance`

`python data/fetch_market_data.py`

**Universe: 30 US large-cap equities, 6 sectors × 5 names** (defined in `universe.py`):

| Sector | Tickers |
|---|---|
| Technology | AAPL, MSFT, NVDA, ORCL, CSCO |
| Financials | JPM, BAC, GS, MS, WFC |
| Health Care | JNJ, PFE, MRK, UNH, ABT |
| Energy | XOM, CVX, COP, SLB, OXY |
| Consumer | WMT, PG, KO, MCD, HD |
| Industrials | CAT, BA, HON, UPS, DE |

Every name has traded continuously since before October 2007, so the same universe is used for
the 5-year VaR window and for full-history stress replays.

| File | Contents | Range | Shape |
|---|---|---|---|
| `ohlcv_core.csv` | Long-format daily OHLCV, split/dividend adjusted | 2021-10-01 → 2026-09-30 | 37,620 rows (30 × 1,254 days) |
| `prices_core.csv` | Wide adjusted close, core VaR window | 2021-10-01 → 2026-09-30 | 1,254 × 30, no missing values |
| `prices_history.csv` | Wide adjusted close for stress replays | 2007-01-03 → 2026-09-30 | 4,967 × 30 |
| `index_history.csv` | S&P 500 (`^GSPC`) close and 10Y Treasury yield (`^TNX`, %) | 1993-01-04 → 2026-09-30 | 8,494 × 2 |

**Spot checks against published records:** S&P 500 closes on 2007-10-09 (1565.15),
2009-03-09 (676.53), 2020-02-19 (3386.15), 2020-03-23 (2237.40), and 2008-10-15 (907.84) all match
the historical record exactly.

## Financial statements — SEC EDGAR `companyfacts` API

`SEC_USER_AGENT="Your Name you@example.com" python data/fetch_credit_data.py`

SEC requires a User-Agent with a contact email. Without one, requests get HTTP 403.

**Credit universe: 25 companies.** These are the 30 market names minus the 5 banks. Bank balance
sheets have no current/non-current split, and Altman-style ratios don't apply to them.

**Fiscal years:** the 5 most recent 10-K fiscal years per company (125 company-years in total).
Fiscal year ends differ by company. Calendar-year filers cover FY2021–FY2025. Off-calendar
filers include later periods:

| Fiscal year end | Companies | Periods covered |
|---|---|---|
| Calendar year | ABT, BA, CAT, COP, CVX, HON, JNJ*, KO, MCD, MRK, OXY, PFE, SLB, UNH, UPS, XOM | FY ending 2021-12 → 2025-12 |
| September | AAPL | 2021-09-25 → 2025-09-27 |
| October/November | DE | 2021-10-31 → 2025-11-02 |
| January/February | NVDA, WMT, HD | FY ending 2022-01 → 2026-01/02 |
| May | ORCL | 2022-05-31 → 2026-05-31 |
| June | MSFT, PG | 2022-06-30 → 2026-06-30 |
| July | CSCO | 2022-07-30 → 2026-07-25 |

\*JNJ uses a 52/53-week year ending on the Sunday closest to Dec 31.

Line items pulled (us-gaap XBRL tags, with fallbacks; `financials_sources.csv` records which tag
and which filing accession number each figure came from):

- total assets, total liabilities, stockholders' equity, total equity incl. NCI
- current assets, current liabilities, retained earnings
- revenue, operating income, pre-tax income, interest expense, net income, operating cash flow

**Extraction rules:**

- Only 10-K / FY facts are used. Flow items must span 350–380 days.
- If a period appears in several filings, the most recently filed value wins, so restatements
  override the original figures.

**Spot checks against published 10-Ks:**

| Company | Fiscal year | Figure | Value |
|---|---|---|---|
| Apple | FY2024 | Revenue | $391.035bn |
| Apple | FY2024 | Net income | $93.736bn |
| Apple | FY2022 | Revenue | $394.328bn |
| Microsoft | FY2024 | Revenue | $245.122bn |
| Walmart | FY2025 (ended Jan-2025) | Revenue | $680.985bn |

### Data caveats (documented, not hidden)

- **XOM registrant change.** SEC's ticker map now points XOM to ExxonMobil Holdings Corp
  (CIK 2115436), the new listed parent since mid-2026. As of the pull, that registrant had filed
  only 10-Qs. Annual history is read from Exxon Mobil Corporation (CIK 34088), which filed every
  10-K in the window. See `PREDECESSOR_CIK` in `fetch_credit_data.py`.
- **Total liabilities derived for 45 rows** (ABT, HON, KO, MCD, MRK, ORCL, OXY, UPS, WMT). These
  filers don't tag a total `Liabilities` line, so it's computed as total assets − total equity
  (including noncontrolling interest). This is exact under the balance-sheet identity, provided
  the filer has no mezzanine/temporary equity. Rows are flagged `liabilities_derived=True`.
- **EBIT fallback for 39 rows** (COP, CVX, JNJ, MRK, OXY, PFE, XOM, and some SLB/HON/DE years).
  These filers don't report an operating-income subtotal, so EBIT = pre-tax income + interest
  expense. The column `ebit_source` says which method was used.
- **Deere (DE) has an unclassified balance sheet.** Its John Deere Financial captive-finance arm
  means no current assets/liabilities are reported, so DE's current ratio and working-capital
  ratio are left missing, not imputed.
