"""Historical stress scenarios applied to the equal-weighted portfolio.

Every scenario is anchored to a real historical episode. Shock sizes are not typed in by hand —
they are measured at runtime from the downloaded S&P 500 (^GSPC) and 10Y Treasury yield (^TNX)
series between the cited dates, so the numbers always match the data.

Scenario basis (closing levels, verified against data/processed/index_history.csv):
  1. GFC drawdown        S&P 500 peak 2007-10-09 (1565.15) -> trough 2009-03-09 (676.53): -56.8%
  2. COVID-19 crash      S&P 500 peak 2020-02-19 (3386.15) -> trough 2020-03-23 (2237.40): -33.9%
  3. 2022 rate shock     10Y yield 2021-12-31 (1.51%) -> 2022-10-21 (4.21%): +270bp, with the
                         S&P 500 falling 4766.18 -> 3752.75 (-21.3%) over the same window
  4. 1994 bond massacre  10Y yield 1993-10-15 (5.19%) -> 1994-11-07 (8.02%): +283bp, S&P 500
                         roughly flat (469.50 -> 463.07)

Two ways of applying a scenario:
  * Full historical replay (scenarios 1-3): each position is shocked by that stock's own actual
    price change between the scenario dates, so sector dispersion and idiosyncratic moves are
    real, not modelled. Positions are held unchanged through the window (no rebalancing).
  * Factor shock (all scenarios): each stock's sensitivity to the S&P 500 and to 10Y yield changes
    is estimated by OLS on the core 5-year window, and the scenario's index/yield moves are
    applied linearly:  r_i = beta_mkt,i * dSPX + beta_rate,i * dYield.
    This is the only option for 1994, which predates the stock price history pulled here, and
    for scenarios 1-3 it shows how far a linear factor model falls short of the real replay.

Each historical episode also gets a "worst single day" variant (the episode's largest one-day
S&P 500 fall, replayed stock by stock), which is directly comparable with 1-day VaR.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from risk.portfolio import (  # noqa: E402
    PORTFOLIO_NOTIONAL, PROCESSED, TICKER_SECTOR, asset_returns, ensure_results_dir,
    equal_weights, load_prices,
)

SCENARIOS = [
    {
        "id": "gfc_2008",
        "name": "Global Financial Crisis",
        "start": "2007-10-09",
        "end": "2009-03-09",
        "replay": True,
        "basis": "S&P 500 peak-to-trough, 9 Oct 2007 to 9 Mar 2009",
    },
    {
        "id": "covid_2020",
        "name": "COVID-19 crash",
        "start": "2020-02-19",
        "end": "2020-03-23",
        "replay": True,
        "basis": "S&P 500 peak-to-trough, 19 Feb 2020 to 23 Mar 2020",
    },
    {
        "id": "rates_2022",
        "name": "2022 rate shock",
        "start": "2021-12-31",
        "end": "2022-10-21",
        "replay": True,
        "basis": "10Y Treasury yield move from 2021 year-end to its Oct 2022 peak",
    },
    {
        "id": "bonds_1994",
        "name": "1994 bond massacre",
        "start": "1993-10-15",
        "end": "1994-11-07",
        "replay": False,
        "basis": "10Y Treasury yield trough-to-peak, 15 Oct 1993 to 7 Nov 1994",
    },
]


def load_index_history():
    return pd.read_csv(PROCESSED / "index_history.csv", index_col="date", parse_dates=True)


def scenario_factor_moves(index_hist, start, end):
    """S&P 500 return and 10Y yield change (in percentage points) between two closes."""
    a, b = index_hist.loc[start], index_hist.loc[end]
    return {
        "spx_start": float(a["spx"]), "spx_end": float(b["spx"]),
        "spx_return": float(b["spx"] / a["spx"] - 1),
        "yield_start_pct": float(a["ust10y_yield_pct"]),
        "yield_end_pct": float(b["ust10y_yield_pct"]),
        "yield_change_pp": float(b["ust10y_yield_pct"] - a["ust10y_yield_pct"]),
        "trading_days": int(len(index_hist.loc[start:end]) - 1),
    }


def estimate_factor_betas(asset_rets, index_hist):
    """OLS of each stock's daily return on S&P 500 daily return and daily 10Y yield change (pp)."""
    factors = pd.DataFrame({
        "mkt": index_hist["spx"].pct_change(),
        "rate": index_hist["ust10y_yield_pct"].diff(),
    })
    data = asset_rets.join(factors, how="inner").dropna()
    X = np.column_stack([np.ones(len(data)), data["mkt"], data["rate"]])
    coefs, *_ = np.linalg.lstsq(X, data[asset_rets.columns].values, rcond=None)
    return pd.DataFrame(coefs[1:].T, index=asset_rets.columns, columns=["beta_mkt", "beta_rate"])


def position_pnl(stock_returns, weights, notional=PORTFOLIO_NOTIONAL):
    """P&L per position for a buy-and-hold portfolio given each stock's return over the shock."""
    exposure = weights * notional
    return (exposure * stock_returns[weights.index]).rename("pnl")


def replay_returns(prices_hist, start, end):
    return prices_hist.loc[end] / prices_hist.loc[start] - 1


def factor_shock_returns(betas, spx_return, yield_change_pp):
    return betas["beta_mkt"] * spx_return + betas["beta_rate"] * yield_change_pp


def worst_day(index_hist, start, end):
    spx = index_hist["spx"].loc[start:end].pct_change().dropna()
    return spx.idxmin(), float(spx.min())


def run_scenarios():
    weights = equal_weights()
    prices_hist = load_prices(history=True)
    index_hist = load_index_history()
    betas = estimate_factor_betas(asset_returns(load_prices()), index_hist)

    results = []
    for sc in SCENARIOS:
        moves = scenario_factor_moves(index_hist, sc["start"], sc["end"])
        factor_pnl = position_pnl(
            factor_shock_returns(betas, moves["spx_return"], moves["yield_change_pp"]), weights)
        rec = {**sc, **moves,
               "factor_pnl_total": float(factor_pnl.sum()),
               "factor_pnl_by_ticker": factor_pnl.round(2).to_dict()}
        if sc["replay"]:
            replay_pnl = position_pnl(replay_returns(prices_hist, sc["start"], sc["end"]), weights)
            day, day_ret = worst_day(index_hist, sc["start"], sc["end"])
            prev_day = prices_hist.index[prices_hist.index.get_loc(day) - 1]
            day_pnl = position_pnl(replay_returns(prices_hist, prev_day, day), weights)
            rec.update({
                "replay_pnl_total": float(replay_pnl.sum()),
                "replay_pnl_by_ticker": replay_pnl.round(2).to_dict(),
                "worst_day_date": str(day.date()),
                "worst_day_spx_return": day_ret,
                "worst_day_pnl_total": float(day_pnl.sum()),
                "worst_day_pnl_by_ticker": day_pnl.round(2).to_dict(),
            })
        results.append(rec)
    return results, betas


def main():
    results, betas = run_scenarios()
    print(f"Portfolio: {len(equal_weights())} names equal-weighted, notional "
          f"${PORTFOLIO_NOTIONAL:,.0f}\n")
    for r in results:
        print(f"== {r['name']} ({r['start']} -> {r['end']}, {r['trading_days']} trading days)")
        print(f"   S&P 500 {r['spx_start']:.2f} -> {r['spx_end']:.2f} ({r['spx_return']:+.1%}); "
              f"10Y {r['yield_start_pct']:.2f}% -> {r['yield_end_pct']:.2f}% "
              f"({r['yield_change_pp']*100:+.0f}bp)")
        if r["replay"]:
            print(f"   Full replay P&L:   ${r['replay_pnl_total']:>14,.0f} "
                  f"({r['replay_pnl_total']/PORTFOLIO_NOTIONAL:+.1%})")
        print(f"   Factor-model P&L:  ${r['factor_pnl_total']:>14,.0f} "
              f"({r['factor_pnl_total']/PORTFOLIO_NOTIONAL:+.1%})")
        if r["replay"]:
            print(f"   Worst single day {r['worst_day_date']} (S&P {r['worst_day_spx_return']:+.2%}): "
                  f"${r['worst_day_pnl_total']:,.0f} "
                  f"({r['worst_day_pnl_total']/PORTFOLIO_NOTIONAL:+.2%})")
        print()

    res = ensure_results_dir()
    (res / "stress_scenarios.json").write_text(json.dumps(results, indent=2, default=str))
    betas.assign(sector=betas.index.map(TICKER_SECTOR)).to_csv(res / "factor_betas.csv")
    print(f"Saved {res / 'stress_scenarios.json'}")


if __name__ == "__main__":
    main()
