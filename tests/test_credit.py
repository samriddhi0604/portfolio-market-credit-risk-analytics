"""Credit ratios against a hand-constructed balance sheet, and scorecard mechanics."""
import numpy as np
import pandas as pd
import pytest

from credit.ratios import altman_zone, compute_ratios
from credit.scoring import FACTORS, assign_tier, composite_score, factor_scores


def make_fin(**overrides):
    row = {
        "ticker": "TEST", "fiscal_year": 2025, "period_end": pd.Timestamp("2025-12-31"),
        "total_assets": 1000.0, "total_liabilities": 600.0, "stockholders_equity": 400.0,
        "current_assets": 300.0, "current_liabilities": 150.0, "retained_earnings": 200.0,
        "revenue": 800.0, "net_income": 60.0, "operating_cash_flow": 90.0, "ebit": 100.0,
    }
    row.update(overrides)
    return pd.DataFrame([row])


def test_ratios_hand_computed():
    r = compute_ratios(make_fin()).iloc[0]
    assert r["liabilities_to_assets"] == pytest.approx(0.60)
    assert r["liabilities_to_equity"] == pytest.approx(1.50)
    assert r["current_ratio"] == pytest.approx(2.00)
    assert r["ocf_to_liabilities"] == pytest.approx(0.15)
    assert r["net_margin"] == pytest.approx(0.075)
    assert r["roa"] == pytest.approx(0.06)


def test_altman_z2_hand_computed():
    # X1 = (300-150)/1000 = 0.15, X2 = 200/1000 = 0.2, X3 = 100/1000 = 0.1, X4 = 400/600
    # Z'' = 6.56*0.15 + 3.26*0.2 + 6.72*0.1 + 1.05*(2/3) = 0.984 + 0.652 + 0.672 + 0.7 = 3.008
    r = compute_ratios(make_fin()).iloc[0]
    assert r["altman_z2"] == pytest.approx(3.008)
    assert r["altman_zone"] == "safe"


def test_altman_zone_boundaries():
    z = pd.Series([2.61, 2.60, 1.10, 1.09, np.nan])
    assert altman_zone(z).tolist()[:4] == ["safe", "grey", "grey", "distress"]
    assert pd.isna(altman_zone(z).iloc[4])


def test_negative_equity_gives_undefined_debt_to_equity():
    r = compute_ratios(make_fin(stockholders_equity=-50.0, total_liabilities=1050.0)).iloc[0]
    assert np.isnan(r["liabilities_to_equity"])
    assert bool(r["negative_equity"])
    assert r["liabilities_to_assets"] == pytest.approx(1.05)


def test_missing_current_items_leave_liquidity_missing_not_zero():
    # Unclassified balance sheet (e.g. Deere): no current assets/liabilities reported.
    r = compute_ratios(make_fin(current_assets=np.nan, current_liabilities=np.nan)).iloc[0]
    assert np.isnan(r["current_ratio"])
    assert np.isnan(r["altman_z2"])


def test_factor_scores_orientation():
    # Lower leverage must score higher; higher ROA must score higher.
    ratios = pd.DataFrame({
        "liabilities_to_assets": [0.3, 0.9], "ocf_to_liabilities": [0.5, 0.1],
        "current_ratio": [2.0, 0.8], "roa": [0.10, 0.01], "net_margin": [0.2, 0.02],
        "altman_z2": [4.0, 1.0],
    }, index=["STRONG", "WEAK"])
    s = factor_scores(ratios)
    assert (s.loc["STRONG"] > s.loc["WEAK"]).all()
    comp = composite_score(s)
    assert comp["STRONG"] == pytest.approx(100.0)
    assert comp["WEAK"] == pytest.approx(50.0)


def test_composite_renormalises_missing_factor():
    scores = pd.DataFrame([{f: 80.0 for f in FACTORS}])
    scores.loc[0, "liquidity"] = np.nan
    # All available factors score 80, so the renormalised composite is still 80.
    assert composite_score(scores).iloc[0] == pytest.approx(80.0)


@pytest.mark.parametrize("score,tier", [(100, "Tier 1"), (70, "Tier 1"), (69.9, "Tier 2"),
                                        (55, "Tier 2"), (45, "Tier 3"), (35, "Tier 4"),
                                        (34.9, "Tier 5"), (0, "Tier 5")])
def test_tier_bands(score, tier):
    assert assign_tier(score) == tier


def test_factor_weights_sum_to_one():
    assert sum(w for _, w, _ in FACTORS.values()) == pytest.approx(1.0)
