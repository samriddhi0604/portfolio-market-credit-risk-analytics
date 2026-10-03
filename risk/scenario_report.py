"""Structured stress-scenario report: P&L attribution and comparison with VaR/ES.

For each scenario:
  * sector attribution and the five largest losing / gaining positions
  * how the stressed loss compares with the Step 2 VaR/ES:
      - worst single day vs 1-day 99% historical VaR and ES (like-for-like horizon)
      - full-window loss vs 99% VaR scaled by sqrt(h) for an h-day horizon. The sqrt-of-time rule
        assumes i.i.d. returns, which is exactly what crisis periods violate — it is shown as a
        reference point, not as a capital number.

Run `python risk/var_es.py` and `python risk/stress_scenarios.py` first.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from risk.portfolio import PORTFOLIO_NOTIONAL, TICKER_SECTOR, ensure_results_dir  # noqa: E402


def attribution(pnl_by_ticker):
    pnl = pd.Series(pnl_by_ticker, dtype=float)
    by_sector = pnl.groupby(pnl.index.map(TICKER_SECTOR)).sum().sort_values()
    return {
        "by_sector": by_sector.round(0).to_dict(),
        "largest_losses": pnl.nsmallest(5).round(0).to_dict(),
        "largest_gains": pnl.nlargest(5).round(0).to_dict(),
    }


def compare_to_var(loss, var_1d, es_1d, horizon_days=1):
    """Ratio of a stressed loss (positive number) to VaR/ES scaled to the horizon."""
    scale = np.sqrt(horizon_days)
    var_h, es_h = var_1d * scale, es_1d * scale
    if loss <= var_h:
        verdict = "inside VaR"
    elif loss <= es_h:
        verdict = "beyond VaR, inside ES"
    else:
        verdict = "beyond ES"
    return {"horizon_days": horizon_days, "scaled_var": var_h, "scaled_es": es_h,
            "loss": loss, "loss_to_var": loss / var_h, "verdict": verdict}


def build_report(scenarios, var_es):
    lvl = var_es["levels"]["0.99"]
    var99, es99 = lvl["hist_var"] * PORTFOLIO_NOTIONAL, lvl["hist_es"] * PORTFOLIO_NOTIONAL
    report = []
    for s in scenarios:
        primary = "replay" if s["replay"] else "factor"
        total = s[f"{primary}_pnl_total"]
        entry = {
            "id": s["id"], "name": s["name"], "basis": s["basis"],
            "start": s["start"], "end": s["end"], "trading_days": s["trading_days"],
            "spx_return": s["spx_return"], "yield_change_bp": s["yield_change_pp"] * 100,
            "method": "full historical replay" if s["replay"] else "factor shock (linear betas)",
            "pnl_total": total, "pnl_pct": total / PORTFOLIO_NOTIONAL,
            "factor_pnl_total": s["factor_pnl_total"],
            "attribution": attribution(s[f"{primary}_pnl_by_ticker"]),
            "vs_var_full_window": compare_to_var(max(-total, 0.0), var99, es99, s["trading_days"]),
        }
        if s["replay"]:
            day_loss = -s["worst_day_pnl_total"]
            entry["worst_day"] = {
                "date": s["worst_day_date"],
                "spx_return": s["worst_day_spx_return"],
                "pnl_total": s["worst_day_pnl_total"],
                "pnl_pct": s["worst_day_pnl_total"] / PORTFOLIO_NOTIONAL,
                "attribution": attribution(s["worst_day_pnl_by_ticker"]),
                "vs_var_1d": compare_to_var(day_loss, var99, es99, 1),
            }
        report.append(entry)
    return {"var_reference": {"confidence": 0.99, "method": "historical",
                              "var_1d_usd": var99, "es_1d_usd": es99},
            "scenarios": report}


def main():
    res = ensure_results_dir()
    scenarios = json.loads((res / "stress_scenarios.json").read_text())
    var_es = json.loads((res / "var_es.json").read_text())
    report = build_report(scenarios, var_es)

    ref = report["var_reference"]
    print(f"Reference: 1-day 99% historical VaR ${ref['var_1d_usd']:,.0f}, "
          f"ES ${ref['es_1d_usd']:,.0f}\n")
    for s in report["scenarios"]:
        print(f"== {s['name']} [{s['method']}] {s['start']} -> {s['end']}")
        print(f"   P&L ${s['pnl_total']:,.0f} ({s['pnl_pct']:+.1%})")
        print("   Sector P&L: " + ", ".join(
            f"{k} ${v:,.0f}" for k, v in s["attribution"]["by_sector"].items()))
        print("   Largest losses: " + ", ".join(
            f"{k} ${v:,.0f}" for k, v in s["attribution"]["largest_losses"].items()))
        c = s["vs_var_full_window"]
        print(f"   vs sqrt({c['horizon_days']})-scaled 99% VaR ${c['scaled_var']:,.0f}: "
              f"loss/VaR = {c['loss_to_var']:.2f}x -> {c['verdict']}")
        if "worst_day" in s:
            w, c = s["worst_day"], s["worst_day"]["vs_var_1d"]
            print(f"   Worst day {w['date']}: ${w['pnl_total']:,.0f} ({w['pnl_pct']:+.2%}) = "
                  f"{c['loss_to_var']:.2f}x 1-day 99% VaR -> {c['verdict']}")
        print()

    (res / "stress_report.json").write_text(json.dumps(report, indent=2))
    print(f"Saved {res / 'stress_report.json'}")


if __name__ == "__main__":
    main()
