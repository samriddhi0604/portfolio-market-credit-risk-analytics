"""VaR / ES against small hand-computable examples."""
import numpy as np
import pandas as pd
import pytest

from risk.var_es import (
    historical_es, historical_var, parametric_es, parametric_var, portfolio_moments,
)


@pytest.fixture
def ladder_returns():
    # 101 daily returns of -1%, -2%, ..., -101%  ->  losses 0.01 ... 1.01.
    # The 95% quantile sits exactly on the 96th smallest loss (index 95 of 0..100): 0.96.
    return -np.arange(1, 102) / 100


def test_historical_var_exact_quantile(ladder_returns):
    assert historical_var(ladder_returns, 0.95) == pytest.approx(0.96)


def test_historical_es_is_mean_of_tail(ladder_returns):
    # Tail = losses >= 0.96 -> {0.96, 0.97, 0.98, 0.99, 1.00, 1.01}, mean 0.985.
    assert historical_es(ladder_returns, 0.95) == pytest.approx(0.985)


def test_es_at_least_var(ladder_returns):
    for a in (0.95, 0.99):
        assert historical_es(ladder_returns, a) >= historical_var(ladder_returns, a)


def test_historical_var_sign_convention():
    # All gains -> the 95% "loss" is negative (a gain), not flipped to positive.
    assert historical_var(np.full(50, 0.01), 0.95) == pytest.approx(-0.01)


def test_parametric_var_standard_normal_quantile():
    # mu = 0, sigma = 1% -> VaR99 = 2.326348 * 1%.
    assert parametric_var(0.0, 0.01, 0.99) == pytest.approx(0.02326348, abs=1e-8)
    # A positive mean drift reduces VaR one-for-one.
    assert parametric_var(0.001, 0.01, 0.99) == pytest.approx(0.02226348, abs=1e-8)


def test_parametric_es_closed_form():
    # ES99 = sigma * phi(z_0.99) / 0.01 = 0.01 * 0.0266521 / 0.01 = 0.0266521.
    assert parametric_es(0.0, 0.01, 0.99) == pytest.approx(0.02665214, abs=1e-7)


def test_portfolio_moments_perfect_correlation():
    a = [0.01, -0.01, 0.01, -0.01]
    rets = pd.DataFrame({"A": a, "B": a})
    w = pd.Series({"A": 0.5, "B": 0.5})
    mu, sigma = portfolio_moments(rets, w)
    # Sample variance = 4 * 0.0001 / 3; perfectly correlated -> portfolio sigma = asset sigma.
    assert mu == pytest.approx(0.0)
    assert sigma == pytest.approx(np.sqrt(0.0004 / 3))


def test_portfolio_moments_perfect_hedge():
    a = np.array([0.01, -0.01, 0.01, -0.01])
    rets = pd.DataFrame({"A": a, "B": -a})
    _, sigma = portfolio_moments(rets, pd.Series({"A": 0.5, "B": 0.5}))
    assert sigma == pytest.approx(0.0, abs=1e-12)
