"""Export the pipeline's actual results to frontend/src/data/results.json for the explainer site.

The site visualises exactly these numbers — nothing on it is typed in by hand. Re-run this after
re-running the pipeline, then rebuild the site.
"""
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from data.universe import TICKERS  # noqa: E402

RESULTS = ROOT / "results"
OUT = ROOT / "frontend" / "src" / "data" / "results.json"


def main():
    var_es = json.loads((RESULTS / "var_es.json").read_text())
    backtest = json.loads((RESULTS / "var_backtest.json").read_text())
    series = pd.read_csv(RESULTS / "var_backtest_series.csv", parse_dates=["date"])
    stress = json.loads((RESULTS / "stress_report.json").read_text())
    credit = json.loads((RESULTS / "credit_scoring.json").read_text())
    dq = json.loads((RESULTS / "data_quality.json").read_text())

    out = {
        "generated": date.today().isoformat(),
        "universe": {"n_stocks": len(TICKERS), "n_credit": len(credit["companies"]),
                     "notional_usd": var_es["notional_usd"]},
        "var": {
            "sample_start": var_es["sample_start"], "sample_end": var_es["sample_end"],
            "n_days": var_es["n_days"], "annualised_vol": var_es["annualised_vol"],
            "worst_day_return": var_es["worst_day_return"], "worst_day_date": var_es["worst_day_date"],
            "levels": var_es["levels"],
        },
        "backtest": {
            "window_days": backtest["window_days"], "test_start": backtest["test_start"],
            "test_end": backtest["test_end"], "results": backtest["results"],
            "series": [{"d": r.date.strftime("%Y-%m-%d"), "loss": round(r.realised_loss, 6),
                        "var99": round(r["hist_var_0.99"], 6)}
                       for _, r in series.iterrows()],
        },
        "stress": {
            "var_reference": stress["var_reference"],
            "scenarios": [{
                "id": s["id"], "name": s["name"], "basis": s["basis"], "start": s["start"],
                "end": s["end"], "trading_days": s["trading_days"], "spx_return": s["spx_return"],
                "yield_change_bp": s["yield_change_bp"], "method": s["method"],
                "pnl_total": s["pnl_total"], "pnl_pct": s["pnl_pct"],
                "factor_pnl_total": s["factor_pnl_total"],
                "by_sector": s["attribution"]["by_sector"],
                "largest_losses": s["attribution"]["largest_losses"],
                "worst_day": ({k: s["worst_day"][k] for k in ("date", "spx_return", "pnl_total", "pnl_pct")}
                              | {"loss_to_var": s["worst_day"]["vs_var_1d"]["loss_to_var"]}
                              if "worst_day" in s else None),
            } for s in stress["scenarios"]],
        },
        "credit": {
            "factors": credit["factors"], "tier_bands": credit["tier_bands"],
            "validation": credit["validation"], "tier_summary": credit["tier_summary"],
            "companies": [{k: c[k] for k in (
                "ticker", "sector", "period_end", "composite_score", "tier", "tier_label",
                "altman_z2", "altman_zone", "liabilities_to_assets", "ocf_to_liabilities",
                "current_ratio", "roa", "net_margin", "equity_vol", "max_drawdown")}
                for c in credit["companies"]],
        },
        "data_quality": {
            "n_checks": len(dq),
            "pass": sum(r["status"] == "PASS" for r in dq),
            "warn": sum(r["status"] == "WARN" for r in dq),
            "fail": sum(r["status"] == "FAIL" for r in dq),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # NaN (e.g. Deere's missing Altman Z'') becomes null so the file is valid JSON.
    text = json.dumps(out, indent=1, default=float).replace("NaN", "null")
    OUT.write_text(text, encoding="utf-8")
    print(f"Wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
