"""Stress-scenario P&L math and the VaR comparison."""
import numpy as np
import pandas as pd
import pytest

from risk.scenario_report import attribution, compare_to_var
from risk.stress_scenarios import (
    estimate_factor_betas, factor_shock_returns, position_pnl, replay_returns,
    scenario_factor_moves, worst_day,
)


def test_position_pnl_hand_computed():
    w = pd.Series({"A": 0.5, "B": 0.5})
    rets = pd.Series({"A": -0.10, "B": 0.20})
    pnl = position_pnl(rets, w, notional=1_000_000)
    assert pnl["A"] == pytest.approx(-50_000)
    assert pnl["B"] == pytest.approx(100_000)
    assert pnl.sum() == pytest.approx(50_000)


def test_replay_returns_between_dates():
    prices = pd.DataFrame({"A": [100.0, 80.0, 50.0], "B": [20.0, 22.0, 30.0]},
                          index=pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03"]))
    r = replay_returns(prices, "2020-01-01", "2020-01-03")
    assert r["A"] == pytest.approx(-0.5)
    assert r["B"] == pytest.approx(0.5)


def test_factor_shock_linear():
    betas = pd.DataFrame({"beta_mkt": [1.2, 0.5], "beta_rate": [0.03, -0.02]}, index=["A", "B"])
    r = factor_shock_returns(betas, spx_return=-0.5, yield_change_pp=1.0)
    # A: 1.2 * -0.5 + 0.03 * 1.0 = -0.57 ; B: 0.5 * -0.5 - 0.02 * 1.0 = -0.27
    assert r["A"] == pytest.approx(-0.57)
    assert r["B"] == pytest.approx(-0.27)


def test_estimate_factor_betas_recovers_known_betas():
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2022-01-03", periods=300)
    spx_ret = rng.normal(0, 0.01, len(idx))
    dy = rng.normal(0, 0.05, len(idx))
    spx = 4000 * np.cumprod(1 + spx_ret)
    ylds = 3 + np.cumsum(dy)
    index_hist = pd.DataFrame({"spx": spx, "ust10y_yield_pct": ylds}, index=idx)
    mkt = index_hist["spx"].pct_change()
    rate = index_hist["ust10y_yield_pct"].diff()
    assets = pd.DataFrame({"A": 1.3 * mkt + 0.02 * rate, "B": 0.4 * mkt - 0.01 * rate}).dropna()
    b = estimate_factor_betas(assets, index_hist)
    assert b.loc["A", "beta_mkt"] == pytest.approx(1.3, abs=1e-9)
    assert b.loc["A", "beta_rate"] == pytest.approx(0.02, abs=1e-9)
    assert b.loc["B", "beta_mkt"] == pytest.approx(0.4, abs=1e-9)
    assert b.loc["B", "beta_rate"] == pytest.approx(-0.01, abs=1e-9)


def test_scenario_factor_moves_and_worst_day():
    idx = pd.to_datetime(["2020-02-19", "2020-02-20", "2020-02-21", "2020-02-24"])
    ih = pd.DataFrame({"spx": [100.0, 90.0, 95.0, 80.0], "ust10y_yield_pct": [1.5, 1.4, 1.2, 1.0]}, index=idx)
    m = scenario_factor_moves(ih, "2020-02-19", "2020-02-24")
    assert m["spx_return"] == pytest.approx(-0.20)
    assert m["yield_change_pp"] == pytest.approx(-0.5)
    assert m["trading_days"] == 3
    day, ret = worst_day(ih, "2020-02-19", "2020-02-24")
    assert day == pd.Timestamp("2020-02-24")
    assert ret == pytest.approx(80 / 95 - 1)


def test_compare_to_var_sqrt_time_and_verdicts():
    c = compare_to_var(loss=250.0, var_1d=100.0, es_1d=150.0, horizon_days=4)
    assert c["scaled_var"] == pytest.approx(200.0)
    assert c["scaled_es"] == pytest.approx(300.0)
    assert c["loss_to_var"] == pytest.approx(1.25)
    assert c["verdict"] == "beyond VaR, inside ES"
    assert compare_to_var(50.0, 100.0, 150.0)["verdict"] == "inside VaR"
    assert compare_to_var(200.0, 100.0, 150.0)["verdict"] == "beyond ES"


def test_attribution_by_sector_sums_to_total():
    pnl = {"AAPL": -100.0, "MSFT": -50.0, "XOM": 30.0}
    a = attribution(pnl)
    assert a["by_sector"]["Technology"] == pytest.approx(-150.0)
    assert a["by_sector"]["Energy"] == pytest.approx(30.0)
    assert sum(a["by_sector"].values()) == pytest.approx(sum(pnl.values()))
    assert list(a["largest_losses"])[0] == "AAPL"
