"""Out-of-sample VaR backtesting with the Kupiec Proportion-of-Failures (POF) test.

Each day t, VaR is estimated from the previous WINDOW days only, then compared with the realised
loss on day t. A breach ("exception") is a day where realised loss > VaR forecast.

Kupiec POF (1995): with T test days, x breaches and expected breach rate p = 1 - confidence,
    LR_pof = -2 ln[ (1-p)^(T-x) p^x ] + 2 ln[ (1-x/T)^(T-x) (x/T)^x ]  ~  chi2(1) under H0
H0 (correct unconditional coverage) is rejected when the p-value < 5%.

Also reported:
  * Christoffersen (1998) independence test: are breaches clustered (breach today makes a breach
    tomorrow more likely)? Kupiec only checks the count, not the timing.
  * Basel traffic light for the 99% model on the most recent 250 days
    (green 0-4 exceptions, yellow 5-9, red 10+).
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import chi2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from risk.portfolio import (  # noqa: E402
    asset_returns, ensure_results_dir, equal_weights, load_prices, portfolio_returns,
)
from risk.var_es import (  # noqa: E402
    CONFIDENCE_LEVELS, historical_var, parametric_var, portfolio_moments,
)

WINDOW = 250  # ~1 trading year estimation window, the Basel convention
SIGNIFICANCE = 0.05


def _xlogy(x, y):
    return 0.0 if x == 0 else x * np.log(y)


def kupiec_pof(n_obs, n_breaches, confidence):
    """Return (LR statistic, p-value) of the Kupiec POF test."""
    p = 1 - confidence
    T, x = int(n_obs), int(n_breaches)
    phat = x / T
    log_l0 = _xlogy(T - x, 1 - p) + _xlogy(x, p)
    log_l1 = _xlogy(T - x, 1 - phat) + _xlogy(x, phat)
    lr = -2 * (log_l0 - log_l1)
    return float(lr), float(chi2.sf(lr, df=1))


def christoffersen_independence(breaches):
    """Return (LR statistic, p-value) of Christoffersen's Markov independence test."""
    b = np.asarray(breaches, dtype=int)
    prev, curr = b[:-1], b[1:]
    n00 = int(((prev == 0) & (curr == 0)).sum())
    n01 = int(((prev == 0) & (curr == 1)).sum())
    n10 = int(((prev == 1) & (curr == 0)).sum())
    n11 = int(((prev == 1) & (curr == 1)).sum())
    pi0 = n01 / (n00 + n01) if n00 + n01 else 0.0
    pi1 = n11 / (n10 + n11) if n10 + n11 else 0.0
    pi = (n01 + n11) / (n00 + n01 + n10 + n11)
    log_l0 = _xlogy(n00 + n10, 1 - pi) + _xlogy(n01 + n11, pi)
    log_l1 = (_xlogy(n00, 1 - pi0) + _xlogy(n01, pi0) + _xlogy(n10, 1 - pi1) + _xlogy(n11, pi1))
    lr = -2 * (log_l0 - log_l1)
    return float(lr), float(chi2.sf(lr, df=1))


def basel_zone(exceptions_250d):
    if exceptions_250d <= 4:
        return "green"
    if exceptions_250d <= 9:
        return "yellow"
    return "red"


def rolling_var_forecasts(asset_rets, weights, window=WINDOW, levels=CONFIDENCE_LEVELS):
    """One-step-ahead VaR forecasts using only data strictly before each forecast date."""
    port = portfolio_returns(asset_rets, weights)
    rows = []
    for i in range(window, len(port)):
        hist_port = port.iloc[i - window:i]
        mu, sigma = portfolio_moments(asset_rets.iloc[i - window:i], weights)
        row = {"date": port.index[i], "realised_return": port.iloc[i]}
        for a in levels:
            row[f"hist_var_{a:.2f}"] = historical_var(hist_port, a)
            row[f"param_var_{a:.2f}"] = parametric_var(mu, sigma, a)
        rows.append(row)
    df = pd.DataFrame(rows).set_index("date")
    df["realised_loss"] = -df["realised_return"]
    return df


def evaluate(forecasts, levels=CONFIDENCE_LEVELS):
    results = []
    for method in ("hist", "param"):
        for a in levels:
            col = f"{method}_var_{a:.2f}"
            breaches = forecasts["realised_loss"] > forecasts[col]
            T, x = len(breaches), int(breaches.sum())
            lr_pof, p_pof = kupiec_pof(T, x, a)
            lr_ind, p_ind = christoffersen_independence(breaches.values)
            res = {
                "method": "historical" if method == "hist" else "parametric",
                "confidence": a,
                "test_days": T,
                "expected_breaches": T * (1 - a),
                "actual_breaches": x,
                "breach_rate": x / T,
                "kupiec_lr": lr_pof,
                "kupiec_p_value": p_pof,
                "kupiec_result": "PASS" if p_pof >= SIGNIFICANCE else "FAIL",
                # Which way a rejection points: too many breaches = VaR understates risk;
                # too few = VaR is over-conservative (capital inefficient, still a model failure).
                "breach_direction": ("too_many" if x > T * (1 - a) else "too_few"),
                "christoffersen_ind_lr": lr_ind,
                "christoffersen_ind_p_value": p_ind,
                "independence_result": "PASS" if p_ind >= SIGNIFICANCE else "FAIL",
            }
            if a == 0.99:
                last = int(breaches.iloc[-250:].sum())
                res["basel_exceptions_last_250d"] = last
                res["basel_zone"] = basel_zone(last)
            results.append(res)
    return pd.DataFrame(results)


def main():
    rets = asset_returns(load_prices())
    forecasts = rolling_var_forecasts(rets, equal_weights())
    table = evaluate(forecasts)

    print(f"Out-of-sample test window: {forecasts.index.min().date()} -> "
          f"{forecasts.index.max().date()} ({len(forecasts)} days), "
          f"rolling {WINDOW}-day estimation\n")
    cols = ["method", "confidence", "test_days", "expected_breaches", "actual_breaches",
            "breach_rate", "kupiec_lr", "kupiec_p_value", "kupiec_result", "breach_direction",
            "christoffersen_ind_p_value", "independence_result"]
    print(table[cols].round(4).to_string(index=False))
    print("\nBasel traffic light (99%, last 250 days):")
    basel = table[table.confidence == 0.99][["method", "basel_exceptions_last_250d", "basel_zone"]]
    print(basel.astype({"basel_exceptions_last_250d": int}).to_string(index=False))

    res = ensure_results_dir()
    forecasts.to_csv(res / "var_backtest_series.csv")
    (res / "var_backtest.json").write_text(json.dumps({
        "window_days": WINDOW,
        "significance": SIGNIFICANCE,
        "test_start": str(forecasts.index.min().date()),
        "test_end": str(forecasts.index.max().date()),
        "results": table.to_dict(orient="records"),
    }, indent=2))
    print(f"\nSaved {res / 'var_backtest.json'}")


if __name__ == "__main__":
    main()
