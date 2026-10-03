"""Ratio-based credit scorecard and rating tiers.

THIS IS A SIMPLIFIED, EDUCATIONAL MODEL. It ranks 25 large US companies on a handful of
transparent financial-statement ratios. It is not a credit rating, it is not calibrated to
default probabilities, and it is not comparable to a rating agency's methodology (which adds
business-risk assessment, industry and country risk, management, debt structure, forward-looking
projections and committee judgement).

Method:
  1. For each company, ratios from the most recent 10-K (credit/ratios.py).
  2. Each ratio is converted to a 0-100 score by its percentile rank within the universe, oriented
     so higher = stronger credit (e.g. lower liabilities/assets scores higher).
  3. Weighted average of the factor scores (weights below). A missing ratio (e.g. Deere's current
     ratio — unclassified balance sheet) is dropped and the remaining weights are renormalised.
  4. Fixed score bands map the composite to five tiers, Tier 1 (strongest) to Tier 5 (weakest).
     Bands are fixed, not quintiles, so tiers are not forced to hold equal counts.

Validation (directional sanity check against something observable and independent of the filings):
  structural credit models (Merton, 1974) imply that firms with weaker credit quality have more
  volatile equity and deeper drawdowns. So the composite score should be negatively rank-
  correlated with each company's realised equity volatility and max drawdown over the core
  5-year price window. Spearman rank correlations are reported, along with tier-average market
  risk measures.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from credit.ratios import compute_ratios, load_financials  # noqa: E402
from data.universe import TICKER_SECTOR  # noqa: E402

RESULTS = ROOT / "results"

# factor -> (ratio column, weight, True if higher ratio = stronger credit)
FACTORS = {
    "leverage": ("liabilities_to_assets", 0.25, False),
    "cash_flow_coverage": ("ocf_to_liabilities", 0.20, True),
    "liquidity": ("current_ratio", 0.15, True),
    "profitability_roa": ("roa", 0.10, True),
    "profitability_margin": ("net_margin", 0.10, True),
    "altman_composite": ("altman_z2", 0.20, True),
}

# Lower bound of the composite score for each tier.
TIER_BANDS = [(70, "Tier 1"), (55, "Tier 2"), (45, "Tier 3"), (35, "Tier 4"), (-np.inf, "Tier 5")]
TIER_LABELS = {
    "Tier 1": "Strongest",
    "Tier 2": "Strong",
    "Tier 3": "Adequate",
    "Tier 4": "Weaker",
    "Tier 5": "Weakest",
}


def factor_scores(ratios):
    """Percentile-rank each ratio into a 0-100 score (higher = stronger)."""
    scores = pd.DataFrame(index=ratios.index)
    for factor, (col, _, higher_better) in FACTORS.items():
        pct = ratios[col].rank(pct=True, ascending=higher_better)
        scores[factor] = 100 * pct
    return scores


def composite_score(scores):
    w = pd.Series({f: v[1] for f, v in FACTORS.items()})
    available = scores.notna()
    weighted = scores.fillna(0).mul(w, axis=1).sum(axis=1)
    return weighted / available.mul(w, axis=1).sum(axis=1)


def assign_tier(score):
    for lower, tier in TIER_BANDS:
        if score >= lower:
            return tier
    return TIER_BANDS[-1][1]


def score_universe(ratios):
    scores = factor_scores(ratios)
    out = ratios.join(scores)
    out["composite_score"] = composite_score(scores)
    out["tier"] = out["composite_score"].apply(assign_tier)
    out["tier_label"] = out["tier"].map(TIER_LABELS)
    return out


def market_risk_measures(tickers):
    prices = pd.read_csv(ROOT / "data" / "processed" / "prices_core.csv", index_col="date",
                         parse_dates=True)[tickers]
    rets = prices.pct_change(fill_method=None).dropna()
    vol = rets.std() * np.sqrt(252)
    mdd = (prices / prices.cummax() - 1).min()
    return pd.DataFrame({"equity_vol": vol, "max_drawdown": mdd})


def validate(scored):
    mkt = market_risk_measures(list(scored.index))
    df = scored.join(mkt)
    rho_vol, p_vol = spearmanr(df["composite_score"], df["equity_vol"])
    # max drawdown is negative; a deeper drawdown (more negative) should go with a lower score,
    # so we expect a positive correlation between score and max_drawdown.
    rho_mdd, p_mdd = spearmanr(df["composite_score"], df["max_drawdown"])
    by_tier = df.groupby("tier").agg(
        n=("composite_score", "size"), avg_score=("composite_score", "mean"),
        avg_equity_vol=("equity_vol", "mean"), avg_max_drawdown=("max_drawdown", "mean"),
        safe_zone_share=("altman_zone", lambda z: (z == "safe").mean()))
    return df, {
        "spearman_score_vs_equity_vol": {"rho": float(rho_vol), "p_value": float(p_vol),
                                         "expected_sign": "negative"},
        "spearman_score_vs_max_drawdown": {"rho": float(rho_mdd), "p_value": float(p_mdd),
                                           "expected_sign": "positive"},
    }, by_tier


def main():
    ratios_all = compute_ratios(load_financials())
    RESULTS.mkdir(exist_ok=True)
    ratios_all.to_csv(RESULTS / "credit_ratios.csv", index=False)

    latest = ratios_all.sort_values("period_end").groupby("ticker").tail(1).set_index("ticker")
    scored = score_universe(latest)
    scored["sector"] = scored.index.map(TICKER_SECTOR)
    scored, checks, by_tier = validate(scored)

    # Stability: score each company on its prior fiscal year too and compare rankings.
    prior = (ratios_all.sort_values("period_end").groupby("ticker").nth(-2).set_index("ticker"))
    prior_scored = score_universe(prior)
    rho_stab, _ = spearmanr(scored["composite_score"],
                            prior_scored.loc[scored.index, "composite_score"])
    checks["spearman_latest_vs_prior_year_score"] = {"rho": float(rho_stab)}

    show = ["sector", "period_end", "liabilities_to_assets", "ocf_to_liabilities",
            "current_ratio", "roa", "net_margin", "altman_z2", "altman_zone",
            "composite_score", "tier", "tier_label", "equity_vol", "max_drawdown"]
    table = scored.sort_values("composite_score", ascending=False)[show]
    print("Credit scorecard — most recent 10-K per company "
          "(SIMPLIFIED EDUCATIONAL MODEL, not a credit rating):\n")
    print(table.assign(period_end=table["period_end"].dt.date).round(3).to_string())
    print("\nTier summary:")
    print(by_tier.round(3).to_string())
    print("\nDirectional validation (Spearman rank correlation, n=25):")
    for k, v in checks.items():
        extra = f", p={v['p_value']:.4f}, expected {v['expected_sign']}" if "p_value" in v else ""
        print(f"  {k}: rho={v['rho']:+.3f}{extra}")

    table.to_csv(RESULTS / "credit_scores.csv")
    (RESULTS / "credit_scoring.json").write_text(json.dumps({
        "disclaimer": "Simplified, ratio-based educational model. Not a credit rating and not "
                      "comparable to a rating agency methodology.",
        "factors": {f: {"ratio": c, "weight": w, "higher_is_stronger": h}
                    for f, (c, w, h) in FACTORS.items()},
        "tier_bands": {t: (None if np.isinf(lo) else lo) for lo, t in TIER_BANDS},
        "validation": checks,
        "tier_summary": by_tier.reset_index().to_dict(orient="records"),
        "companies": table.reset_index().assign(
            period_end=table["period_end"].dt.strftime("%Y-%m-%d").values
        ).to_dict(orient="records"),
    }, indent=2, default=float))
    print(f"\nSaved {RESULTS / 'credit_scoring.json'}")


if __name__ == "__main__":
    main()
