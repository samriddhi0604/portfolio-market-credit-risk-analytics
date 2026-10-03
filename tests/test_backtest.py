"""Kupiec POF, Christoffersen independence and Basel zones."""
import math

import numpy as np
import pandas as pd
import pytest

from risk.backtest_var import basel_zone, christoffersen_independence, kupiec_pof, evaluate


def test_kupiec_zero_when_breach_rate_matches():
    lr, p = kupiec_pof(1000, 10, 0.99)
    assert lr == pytest.approx(0.0, abs=1e-12)
    assert p == pytest.approx(1.0)


def test_kupiec_hand_computed_five_breaches_in_100_days():
    # LR = -2[95 ln 0.99 + 5 ln 0.01] + 2[95 ln 0.95 + 5 ln 0.05]
    expected = (-2 * (95 * math.log(0.99) + 5 * math.log(0.01))
                + 2 * (95 * math.log(0.95) + 5 * math.log(0.05)))
    lr, p = kupiec_pof(100, 5, 0.99)
    assert lr == pytest.approx(expected)
    assert lr == pytest.approx(8.2582, abs=1e-3)
    assert p < 0.05  # rejected: 5% breach rate vs 1% target


def test_kupiec_zero_breaches_uses_limit():
    # x = 0: the alternative likelihood is 1, so LR = -2 * T * ln(1 - p).
    lr, _ = kupiec_pof(250, 0, 0.99)
    assert lr == pytest.approx(-2 * 250 * math.log(0.99))
    assert lr == pytest.approx(5.0252, abs=1e-4)


def test_kupiec_rejects_too_few_as_well_as_too_many():
    _, p_few = kupiec_pof(1000, 1, 0.99)
    _, p_many = kupiec_pof(1000, 25, 0.99)
    assert p_few < 0.05 and p_many < 0.05


def test_christoffersen_flags_clustering():
    clustered = np.zeros(500, dtype=int)
    clustered[100:110] = 1                      # ten breaches in a row
    spread = np.zeros(500, dtype=int)
    spread[::50] = 1                            # ten isolated breaches
    _, p_clustered = christoffersen_independence(clustered)
    _, p_spread = christoffersen_independence(spread)
    assert p_clustered < 0.01
    assert p_spread > 0.05


@pytest.mark.parametrize("n,zone", [(0, "green"), (4, "green"), (5, "yellow"), (9, "yellow"),
                                    (10, "red"), (15, "red")])
def test_basel_zones(n, zone):
    assert basel_zone(n) == zone


def test_evaluate_counts_breaches_strictly_greater():
    # loss equal to VaR is not a breach; loss above it is.
    idx = pd.date_range("2024-01-01", periods=4)
    f = pd.DataFrame({
        "realised_loss": [0.02, 0.03, 0.01, 0.05],
        "hist_var_0.99": [0.02, 0.02, 0.02, 0.02], "param_var_0.99": [0.02] * 4,
        "hist_var_0.95": [0.02] * 4, "param_var_0.95": [0.02] * 4,
    }, index=idx)
    res = evaluate(f).set_index(["method", "confidence"])
    assert res.loc[("historical", 0.99), "actual_breaches"] == 2
    assert res.loc[("historical", 0.99), "breach_direction"] == "too_many"
