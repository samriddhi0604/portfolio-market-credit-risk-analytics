"""Portfolio Value-at-Risk and Expected Shortfall.

Conventions: losses are positive numbers (loss = -return). VaR_a is the a-quantile of the 1-day
loss distribution; ES_a is the expected loss given the loss is at or beyond VaR_a.

Two methods:
  * Historical simulation: empirical quantile of realised portfolio losses; ES is the mean of the
    losses at or beyond that quantile.
  * Parametric (variance-covariance): portfolio sigma from the asset covariance matrix,
    sigma_p = sqrt(w' Sigma w), with normally distributed returns assumed:
        VaR_a = -mu_p + sigma_p * z_a
        ES_a  = -mu_p + sigma_p * phi(z_a) / (1 - a)
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from risk.portfolio import (  # noqa: E402
    PORTFOLIO_NOTIONAL, asset_returns, ensure_results_dir, equal_weights, load_prices,
    portfolio_returns,
)

CONFIDENCE_LEVELS = (0.95, 0.99)


def historical_var(returns, alpha):
    losses = -np.asarray(returns, dtype=float)
    return float(np.quantile(losses, alpha))


def historical_es(returns, alpha):
    losses = -np.asarray(returns, dtype=float)
    var = np.quantile(losses, alpha)
    return float(losses[losses >= var].mean())


def parametric_var(mu, sigma, alpha):
    return float(-mu + sigma * norm.ppf(alpha))


def parametric_es(mu, sigma, alpha):
    return float(-mu + sigma * norm.pdf(norm.ppf(alpha)) / (1 - alpha))


def portfolio_moments(asset_rets, weights):
    """Portfolio mean and volatility from asset means and the covariance matrix."""
    w = weights.values
    rets = asset_rets[weights.index]
    mu = float(rets.mean().values @ w)
    sigma = float(np.sqrt(w @ rets.cov().values @ w))
    return mu, sigma


def compute_var_es(asset_rets, weights, levels=CONFIDENCE_LEVELS):
    port = portfolio_returns(asset_rets, weights)
    mu, sigma = portfolio_moments(asset_rets, weights)
    rows = [{
        "confidence": a,
        "hist_var": historical_var(port, a),
        "hist_es": historical_es(port, a),
        "param_var": parametric_var(mu, sigma, a),
        "param_es": parametric_es(mu, sigma, a),
    } for a in levels]
    return pd.DataFrame(rows).set_index("confidence"), port, mu, sigma


def main():
    rets = asset_returns(load_prices())
    weights = equal_weights()
    table, port, mu, sigma = compute_var_es(rets, weights)

    print(f"Portfolio: {len(weights)} names, equal-weighted, notional ${PORTFOLIO_NOTIONAL:,.0f}")
    print(f"Sample: {port.index.min().date()} -> {port.index.max().date()} ({len(port)} days)")
    print(f"Daily mean {mu:.4%}, daily vol {sigma:.4%} (annualised {sigma*np.sqrt(252):.2%})")
    print(f"Worst day {port.min():.2%} on {port.idxmin().date()}\n")
    print("1-day VaR / ES, % of portfolio value:")
    print((table * 100).round(3).to_string())
    print("\n1-day VaR / ES, USD on notional:")
    print((table * PORTFOLIO_NOTIONAL).round(0).to_string())

    out = {
        "sample_start": str(port.index.min().date()),
        "sample_end": str(port.index.max().date()),
        "n_days": int(len(port)),
        "n_assets": int(len(weights)),
        "notional_usd": PORTFOLIO_NOTIONAL,
        "daily_mean": mu,
        "daily_vol": sigma,
        "annualised_vol": sigma * np.sqrt(252),
        "worst_day_return": float(port.min()),
        "worst_day_date": str(port.idxmin().date()),
        "levels": {f"{a:.2f}": table.loc[a].to_dict() for a in table.index},
    }
    res = ensure_results_dir()
    (res / "var_es.json").write_text(json.dumps(out, indent=2))
    port.rename("portfolio_return").to_csv(res / "portfolio_returns.csv")
    print(f"\nSaved {res / 'var_es.json'}")


if __name__ == "__main__":
    main()
