# Portfolio Market & Credit Risk Analytics

**Live explainer:** https://samriddhi0604.github.io/portfolio-market-credit-risk-analytics/

This project runs the core risk workflows end to end on **real data**:

- **Market risk:** Value-at-Risk and Expected Shortfall, validated out of sample with the
  Kupiec proportion-of-failures test.
- **Stress testing:** stress tests anchored to real historical crises.
- **Credit risk:** a financial-statement credit scorecard built from SEC EDGAR 10-K filings.

All of it rolls up into a consolidated risk report with data-quality checks.

Every number in this README is copied from the pipeline output in `results/`, produced on
2026-10-03 from data pulled that day.

---

## Data

| Source | What | Coverage |
|---|---|---|
| Yahoo Finance (`yfinance`) | Daily OHLCV, split/dividend adjusted | **30 US large caps**, 6 sectors × 5. Core window **2021-10-01 → 2026-09-30** (1,254 trading days). Replay history from 2007. |
| Yahoo Finance | S&P 500 (`^GSPC`), 10Y Treasury yield (`^TNX`) | 1993-01-04 → 2026-09-30 |
| SEC EDGAR `companyfacts` API | 10-K balance sheet, income statement, cash flow | **25 non-financial companies × 5 fiscal years** (125 company-years) |

**Universe:**

| Sector | Tickers |
|---|---|
| Technology | AAPL, MSFT, NVDA, ORCL, CSCO |
| Financials | JPM, BAC, GS, MS, WFC |
| Health Care | JNJ, PFE, MRK, UNH, ABT |
| Energy | XOM, CVX, COP, SLB, OXY |
| Consumer | WMT, PG, KO, MCD, HD |
| Industrials | CAT, BA, HON, UPS, DE |

Banks are excluded from credit scoring, because the ratios used don't apply to bank balance sheets.

[`data/README.md`](data/README.md) documents:

- exact fiscal-year coverage per company
- spot checks against published figures (e.g. Apple FY2024 revenue $391.035bn, which matches the 10-K)
- every data caveat, such as XOM's 2026 registrant change, derived liabilities, and Deere's unclassified balance sheet

## Running it

```bash
python -m venv .venv && .venv/Scripts/activate         # (source .venv/bin/activate on macOS/Linux)
pip install -r requirements.txt

python data/fetch_market_data.py
SEC_USER_AGENT="Your Name you@example.com" python data/fetch_credit_data.py   # SEC requires a contact
python risk/var_es.py
python risk/backtest_var.py
python risk/stress_scenarios.py
python risk/scenario_report.py
python credit/scoring.py
python reporting/data_quality_checks.py
python reporting/generate_report.py          # -> reports/risk_report.html
python reporting/export_frontend_data.py     # -> frontend/src/data/results.json
pytest                                       # 46 tests

cd frontend && npm install && npm run dev    # explainer site
```

---

## 1. Market risk: VaR and Expected Shortfall

**Portfolio:** the 30 stocks equally weighted, rebalanced daily, on a $10,000,000 notional.

**Sample:** 1,253 daily returns, 2021-10-04 → 2026-09-30.
- Annualised volatility: 15.0%.
- Worst day: −6.14% on 2025-04-04.

**Methods** ([`risk/var_es.py`](risk/var_es.py)). Losses are positive numbers.
- **Historical simulation:** VaR is the empirical α-quantile of realised losses. ES is the mean of the losses at or beyond it.
- **Parametric (variance-covariance):** σₚ = √(wᵀΣw) from the asset covariance matrix, assuming normality.
  - VaR = −μ + σ·z_α
  - ES = −μ + σ·φ(z_α)/(1−α)

| 1-day | Hist VaR | Hist ES | Param VaR | Param ES |
|---|---|---|---|---|
| 95% | 1.383% ($138,264) | 2.127% ($212,680) | 1.491% ($149,112) | 1.886% ($188,603) |
| 99% | 2.593% ($259,287) | 3.473% ($347,296) | 2.135% ($213,519) | 2.455% ($245,545) |

At 99%, the normal model understates historical VaR by about 18% and historical ES by about 29%.
That's the fat-tail gap the normality assumption misses.

## 2. VaR backtest: Kupiec POF

[`risk/backtest_var.py`](risk/backtest_var.py) produces one-day-ahead VaR forecasts from a rolling
**250-day** window, using only data before each forecast date. It tests them over **1,003
out-of-sample days** (2022-09-30 → 2026-09-30). A breach is a realised loss greater than the
forecast.

- **Kupiec (1995) POF:** LR = −2 ln[(1−p)^(T−x) p^x] + 2 ln[(1−x/T)^(T−x) (x/T)^x] ~ χ²(1).
  It tests whether the breach count is consistent with the target rate.
- **Christoffersen (1998) independence test:** tests whether breaches cluster in time.
- **Basel traffic light:** applied to the 99% model over the last 250 days.

| Model | Breaches (expected) | Kupiec LR | p-value | Kupiec | Direction | Independence p | Independence |
|---|---|---|---|---|---|---|---|
| Historical 95% | 34 (50.15) | 6.143 | 0.0132 | **FAIL** | too few | 0.0289 | **FAIL** |
| Historical 99% | 12 (10.03) | 0.368 | 0.5442 | **PASS** | too many | 0.0002 | **FAIL** |
| Parametric 95% | 34 (50.15) | 6.143 | 0.0132 | **FAIL** | too few | 0.0049 | **FAIL** |
| Parametric 99% | 13 (10.03) | 0.812 | 0.3674 | **PASS** | too many | 0.0003 | **FAIL** |

Basel traffic light (99%, last 250 days): 1 exception for both models, which is **green**.

**What the backtest shows:**

- **95% models fail Kupiec on the conservative side.** There are too few breaches. The rolling
  window carried 2022's volatility into the calmer 2023–24 period, so the model held more capital
  than the realised risk needed. That's still a model failure, just the cheaper kind.
- **99% models pass the breach count but fail independence.** Breaches cluster around the
  April 2025 tariff selloff, the single largest stress in the sample. A 250-day equally weighted
  window reacts too slowly to a volatility regime change. The natural next step would be a
  volatility-scaled approach, such as EWMA or filtered historical simulation. That isn't
  implemented here.

These results were not tuned to pass. The window length and confidence levels were fixed
before the test was run.

## 3. Stress testing

[`risk/stress_scenarios.py`](risk/stress_scenarios.py) defines the scenarios.
[`risk/scenario_report.py`](risk/scenario_report.py) attributes the P&L by position and sector
and compares it with VaR.

Scenario magnitudes are measured from the downloaded index data between the cited dates, not
typed in:

| Scenario | Basis (real historical move) | Window |
|---|---|---|
| Global Financial Crisis | S&P 500 peak 1565.15 → trough 676.53 (**−56.8%**) | 2007-10-09 → 2009-03-09 |
| COVID-19 crash | S&P 500 3386.15 → 2237.40 (**−33.9%**) | 2020-02-19 → 2020-03-23 |
| 2022 rate shock | 10Y yield 1.51% → 4.21% (**+270bp**), S&P 500 −21.3% | 2021-12-31 → 2022-10-21 |
| 1994 bond massacre | 10Y yield 5.19% → 8.02% (**+283bp**), S&P 500 −1.4% | 1993-10-15 → 1994-11-07 |

Scenarios are applied in two ways:

- **Full historical replay** (2008, 2020, 2022): each position takes that stock's own actual
  move between the two dates.
- **Factor shock** (all four): each stock's market beta and 10Y-yield beta are estimated by OLS
  on the 5-year window, then applied to the real index and yield moves. This is the only option
  for 1994, which predates the price history.

| Scenario | Replay P&L | Factor-model P&L | Largest losing sector | Worst single day | Worst day vs 1-day 99% VaR |
|---|---|---|---|---|---|
| GFC | **−$4,909,511 (−49.1%)** | −$4,562,397 | Financials (−$1,239,561) | 2008-10-15: −8.67% | **3.34×**, beyond ES |
| COVID-19 | **−$3,707,963 (−37.1%)** | −$2,702,659 | Energy (−$988,627) | 2020-03-16: −12.44% | **4.80×**, beyond ES |
| 2022 rate shock | **+$228,120 (+2.3%)** | −$1,390,808 | Technology (−$491,255) | 2022-09-13: −3.72% | **1.44×**, beyond ES |
| 1994 bond massacre | n/a | +$161,811 (+1.6%) | Consumer (−$129,634) | n/a | n/a |

**What the stress tests show:**

- **VaR misses crisis days entirely.** The worst day of each crisis lost 1.4–4.8× the 1-day
  99% VaR, beyond ES in every case. That's the gap stress testing exists to cover.
- **The 2022 replay made money; the factor model said −13.9%.** Energy gained $1.42M as oil
  rallied, more than offsetting losses everywhere else. A linear market/rate-beta model can't
  see that sector rotation. That's the argument for replaying real cross-sections instead of
  shocking a few factors.
- **COVID was worse than its index move.** The factor model understated the replay by about
  10 points. Energy and Boeing fell far more than their market betas implied.
- Multi-week losses are also compared with √h-scaled 99% VaR in `results/stress_report.json`.
  For example, the GFC loss is 1.00× its √355-scaled VaR. Treat that only as a reference point
  (see limitations).

## 4. Credit risk: ratio-based scorecard

[`credit/ratios.py`](credit/ratios.py) and [`credit/scoring.py`](credit/scoring.py) compute the
ratios and scores. Each company is scored on its most recent 10-K.

| Factor | Ratio | Weight |
|---|---|---|
| Leverage | Total liabilities / total assets (lower is stronger) | 25% |
| Cash-flow coverage | Operating cash flow / total liabilities | 20% |
| Liquidity | Current ratio | 15% |
| Profitability | Return on assets | 10% |
| Profitability | Net margin | 10% |
| Composite | **Altman Z″ (1995)** = 6.56·WC/TA + 3.26·RE/TA + 6.72·EBIT/TA + 1.05·BookEquity/TL | 20% |

Altman Z″ is used instead of the 1968 Z-score for two reasons: it needs no market cap, and it
drops the sales/assets term, which is industry-dependent. That keeps every input inside the
filing.

**Scoring:**
- Each ratio is percentile-ranked within the universe (0–100, oriented so higher means stronger).
- The ranks are weight-averaged. A missing ratio drops out, and the remaining weights are renormalised.
- Fixed bands map the score to tiers: Tier 1 ≥ 70, Tier 2 ≥ 55, Tier 3 ≥ 45, Tier 4 ≥ 35, Tier 5 below 35.

| Tier | Companies | Avg score | Avg equity vol | Avg max drawdown | Altman "safe" share |
|---|---|---|---|---|---|
| Tier 1 (Strongest) | NVDA, MSFT, ABT, XOM | 84.7 | 32.4% | −40.9% | 100% |
| Tier 2 (Strong) | COP, MRK, JNJ, PG, SLB, CVX, KO | 61.8 | 24.6% | −30.1% | 100% |
| Tier 3 (Adequate) | AAPL, CAT, MCD | 50.3 | 25.9% | −32.8% | 67% |
| Tier 4 (Weaker) | CSCO, HD, OXY, PFE, WMT, HON, UPS | 40.1 | 26.9% | −41.4% | 43% |
| Tier 5 (Weakest) | ORCL, DE, UNH, BA | 22.2 | 35.6% | −52.5% | 0% |

**Directional validation.** Structural credit models (Merton) imply weaker credits have more
volatile equity and deeper drawdowns. So the scores are checked against each company's realised
5-year equity risk, which comes from market prices and is independent of the filings:

- **Score vs. equity volatility:** Spearman ρ = **−0.157** (p = 0.454). Expected sign: negative.
- **Score vs. max drawdown:** Spearman ρ = **+0.235** (p = 0.257). Expected sign: positive.
- **Year-on-year stability:** latest vs. prior fiscal-year score, ρ = **0.945**.

Both signs point the right way, but **neither is statistically significant** with 25 companies.
- **Where it works:** Tier 5 has the highest volatility and the deepest drawdowns.
- **Where it doesn't:** Tier 1 contains NVDA, which has 52% equity volatility despite the
  strongest fundamentals in the set. Balance-sheet strength and equity risk are different things.

> **This is a simplified, educational model, not a credit rating.** It ranks 25 companies on
> transparent ratios. It has none of the following, which a rating agency's methodology includes:
> - a business-risk assessment
> - debt structure and seniority
> - industry or country risk
> - forward-looking projections
> - committee judgement
>
> It is not calibrated to default probabilities and should not be read as comparable to S&P,
> Moody's or Fitch ratings.

## 5. Reporting and data quality

- [`reporting/generate_report.py`](reporting/generate_report.py) writes
  [`reports/risk_report.html`](reports/risk_report.html), a single self-contained file. It covers
  the VaR/ES tables, the backtest chart with breaches marked, stress P&L and attribution, credit
  tiers, and the data-quality results.
- [`reporting/data_quality_checks.py`](reporting/data_quality_checks.py) runs **17 checks**:
  **15 pass, 2 warn, 0 fail**. The checks are:
  - **Prices:** missing closes, non-positive prices, stale runs of identical closes, daily moves
    above 20%, date gaps, freshness.
  - **OHLCV:** low ≤ open/close ≤ high consistency.
  - **Financials:** 5 years present per company, asset sign, leverage and liquidity ranges,
    balance-sheet tie-out within 2%, derived-liabilities flag, filing staleness.
- Both warnings are real and reviewed:
  - **Three genuine >20% single-day moves:** NVDA 2023-05-25 +24.4% (earnings), UNH 2025-04-17
    −22.4%, ORCL 2025-09-10 +36.0%.
  - **Total liabilities derived** as assets − equity for 9 filers that don't tag the total.

## 6. Explainer site

[`frontend/`](frontend/) is a scroll-driven explainer built with **Vite + TypeScript, GSAP
ScrollTrigger + SplitText, and Lenis**. It's deployed to GitHub Pages by
[`.github/workflows/deploy-site.yml`](.github/workflows/deploy-site.yml).

Every number on it comes from `frontend/src/data/results.json`, which
`reporting/export_frontend_data.py` writes from the pipeline output. Motion features:

- a preloader driven by actual font/page loading
- line-mask headline reveals
- a scrubbed, pinned VaR chart that reveals breaches as you scroll
- one stress scenario per scroll beat
- a credit-tier reveal

The page honours `prefers-reduced-motion`.

## 7. Tests

`pytest` runs **46 tests, all passing**. They check against hand-computable examples:

- **VaR/ES:**
  - an exact-quantile ladder
  - closed-form normal VaR/ES
  - portfolio σ under perfect correlation and a perfect hedge
- **Kupiec:**
  - LR = 0 at the target rate
  - LR = 8.2582 for 5 breaches in 100 days at 99%
  - the x = 0 limit (LR = 5.0252 for 250 days)
- **Christoffersen:** clustered vs. spread breaches.
- **Credit ratios:** a hand-built balance sheet with Z″ = 3.008, the negative-equity case, the
  missing-current-items case, factor orientation, weight renormalisation, and tier bands.
- **Stress math:** position P&L, replay returns, linear factor shocks, exact beta recovery, the
  √h-scaled VaR comparison, and sector attribution.
- **Data-quality checks:** each fires on deliberately broken inputs.

---

## Known limitations

- **The credit model is an educational proxy, not a rating.** Its validation against
  market-implied risk is directionally right but not statistically significant (n = 25).
- **A stated universe, not the market.** The book is 30 US large caps, equal-weighted,
  long-only equity, with no bonds, FX or derivatives. A "rate shock" reaches it only through
  estimated equity rate betas.
- **Limited backtest power.** 1,003 out-of-sample days give about 10 expected 99% breaches.
  Kupiec has low power to separate a good model from a mediocre one at counts this small.
- **Survivorship bias.** The universe was chosen in 2026 from companies that exist today.
  Replaying 2008 only with names known to have survived understates what that crisis did to a
  real book.
- **Regime-bound betas.** Rate betas are estimated on 2021–2026, when yields and energy/bank
  stocks rose together. Applied to 1994, they describe this decade's correlations, which is why
  that scenario shows a small gain.
- **√time scaling assumes i.i.d. returns.** Crises violate exactly that assumption. Multi-week
  VaR comparisons are reference points, not capital numbers.
- **Static positions in replays.** No rebalancing, hedging or liquidity effects. Bid/ask and
  market impact are ignored.
- **Data caveats.**
  - Adjusted prices from Yahoo Finance can be revised as new dividends are paid.
  - XBRL tag choice varies by filer, so total liabilities are derived for 9 companies, and EBIT
    is pre-tax income + interest for 39 company-years.
  - DE has no current split, so its liquidity factors are missing (not imputed).
- **Fiscal years differ by company.** "Latest 10-K" means fiscal years ending anywhere from
  Nov 2025 (DE) to Jul 2026 (CSCO). Check `data/README.md` before quoting a specific company's
  figure.

## Structure

```
data/         fetch_market_data.py, fetch_credit_data.py, universe.py, processed/, README.md
risk/         portfolio.py, var_es.py, backtest_var.py, stress_scenarios.py, scenario_report.py
credit/       ratios.py, scoring.py
reporting/    generate_report.py, data_quality_checks.py, export_frontend_data.py
results/      JSON/CSV outputs of every step
reports/      risk_report.html
tests/        46 unit tests
frontend/     Vite + GSAP + Lenis explainer site
```
