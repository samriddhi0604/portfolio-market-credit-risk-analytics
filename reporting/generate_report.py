"""Consolidated risk report (single self-contained HTML file).

Combines: VaR/ES + backtest verdicts, stress-scenario P&L and attribution, credit tier summary,
and the data-quality check results. Charts are rendered with matplotlib and embedded as base64
PNGs so the report is one file that can be emailed or archived.

Run the pipeline first (see README), then:  python reporting/generate_report.py
Output: reports/risk_report.html
"""
import base64
import html
import io
import json
import sys
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from reporting.data_quality_checks import run_all  # noqa: E402

RESULTS = ROOT / "results"
OUT_DIR = ROOT / "reports"

# Palette (validated reference palette from the dataviz method): blue / orange series,
# red reserved for breaches/losses, ordinal blue ramp for credit tiers.
BLUE, ORANGE, RED, INK, MUTED, GRID = "#2a78d6", "#eb6834", "#e34948", "#0b0b0b", "#52514e", "#e4e3df"
TIER_RAMP = {"Tier 1": "#104281", "Tier 2": "#256abf", "Tier 3": "#3987e5", "Tier 4": "#6da7ec",
             "Tier 5": "#86b6ef"}


def _style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def _png(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def chart_backtest(series):
    fig, ax = plt.subplots(figsize=(9, 3.4))
    loss = series["realised_loss"] * 100
    var = series["hist_var_0.99"] * 100
    ax.plot(series.index, loss, color="#a9a8a2", linewidth=0.7, label="Realised daily loss")
    ax.plot(series.index, var, color=BLUE, linewidth=2, label="99% historical VaR (rolling 250d)")
    br = loss > var
    ax.scatter(series.index[br], loss[br], s=22, color=RED, zorder=3,
               edgecolor="white", linewidth=1, label=f"Breach ({int(br.sum())} days)")
    ax.set_ylabel("Loss, % of portfolio", color=MUTED, fontsize=8)
    ax.legend(frameon=False, fontsize=8, loc="upper left", ncol=3)
    _style(ax)
    return _png(fig)


def chart_stress(report):
    rows = [(s["name"], s["pnl_pct"] * 100 if "replay" in s["method"] else None,
             s["factor_pnl_total"] / 1e5) for s in report["scenarios"]]
    names = [r[0] for r in rows]
    fig, ax = plt.subplots(figsize=(9, 3.2))
    y = range(len(rows))
    h = 0.36
    replay = [r[1] if r[1] is not None else 0 for r in rows]
    factor = [r[2] for r in rows]  # USD / 1e5 on a $10M notional = percent
    ax.barh([i - h / 2 for i in y], replay, height=h - 0.04, color=BLUE, label="Full historical replay")
    ax.barh([i + h / 2 for i in y], factor, height=h - 0.04, color=ORANGE, label="Factor model (linear betas)")
    for i, r in enumerate(rows):
        if r[1] is None:
            ax.text(0.3, i - h / 2, "n/a — predates price history", va="center", fontsize=7, color=MUTED)
    ax.axvline(0, color=INK, linewidth=0.8)
    ax.set_yticks(list(y), names, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("Scenario P&L, % of portfolio", color=MUTED, fontsize=8)
    ax.legend(frameon=False, fontsize=8, loc="lower left")
    _style(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    return _png(fig)


def chart_credit(companies):
    df = pd.DataFrame(companies).sort_values("composite_score")
    fig, ax = plt.subplots(figsize=(9, 5.2))
    ax.barh(df["ticker"], df["composite_score"], color=df["tier"].map(TIER_RAMP), height=0.7)
    for i, (_, r) in enumerate(df.iterrows()):
        ax.text(r["composite_score"] + 0.8, i, f"{r['composite_score']:.0f}  {r['tier']}",
                va="center", fontsize=7, color=MUTED)
    ax.set_xlim(0, 112)
    ax.set_xlabel("Composite credit score (0-100, higher = stronger)", color=MUTED, fontsize=8)
    ax.tick_params(axis="y", labelsize=7)
    _style(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    return _png(fig)


def _table(df, fmt=None):
    fmt = fmt or {}
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
    body = ""
    for _, row in df.iterrows():
        cells = ""
        for c in df.columns:
            v = row[c]
            s = fmt[c](v) if c in fmt and pd.notna(v) else ("—" if pd.isna(v) else str(v))
            cells += f"<td>{html.escape(s)}</td>"
        body += f"<tr>{cells}</tr>"
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def pct(d=2):
    return lambda v: f"{v * 100:.{d}f}%"


def usd(v):
    return f"${v:,.0f}"


def build_html():
    var_es = json.loads((RESULTS / "var_es.json").read_text())
    backtest = json.loads((RESULTS / "var_backtest.json").read_text())
    series = pd.read_csv(RESULTS / "var_backtest_series.csv", index_col="date", parse_dates=True)
    stress = json.loads((RESULTS / "stress_report.json").read_text())
    credit = json.loads((RESULTS / "credit_scoring.json").read_text())
    dq = run_all()

    notional = var_es["notional_usd"]
    var_rows = pd.DataFrame([{"Confidence": k, "Hist VaR": v["hist_var"], "Hist ES": v["hist_es"],
                              "Param VaR": v["param_var"], "Param ES": v["param_es"],
                              "Hist VaR (USD)": v["hist_var"] * notional,
                              "Hist ES (USD)": v["hist_es"] * notional}
                             for k, v in var_es["levels"].items()])
    bt = pd.DataFrame(backtest["results"])
    bt_tbl = bt[["method", "confidence", "expected_breaches", "actual_breaches", "kupiec_lr",
                 "kupiec_p_value", "kupiec_result", "breach_direction",
                 "christoffersen_ind_p_value", "independence_result"]]
    st_rows = []
    for s in stress["scenarios"]:
        st_rows.append({
            "Scenario": s["name"], "Window": f"{s['start']} → {s['end']}",
            "S&P 500": s["spx_return"], "10Y yield (bp)": round(s["yield_change_bp"]),
            "Method": s["method"], "P&L (USD)": s["pnl_total"], "P&L %": s["pnl_pct"],
            "Worst day vs 1d 99% VaR": (f"{s['worst_day']['vs_var_1d']['loss_to_var']:.2f}x "
                                        f"({s['worst_day']['date']})" if "worst_day" in s else "—"),
            "Biggest losing sector": min(s["attribution"]["by_sector"].items(), key=lambda kv: kv[1])[0],
        })
    st = pd.DataFrame(st_rows)
    cr = pd.DataFrame(credit["companies"])[["ticker", "sector", "period_end", "composite_score",
                                             "tier", "tier_label", "altman_z2", "altman_zone"]]
    tiers = pd.DataFrame(credit["tier_summary"])
    val = credit["validation"]
    dq_df = pd.DataFrame(dq)[["status", "dataset", "check", "detail"]].assign(
        detail=lambda d: d["detail"].astype(str).str.slice(0, 160))

    n_fail = int((dq_df["status"] == "FAIL").sum())
    n_warn = int((dq_df["status"] == "WARN").sum())
    v99h = var_es["levels"]["0.99"]

    css = """
    body{font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;color:#0b0b0b;background:#fcfcfb;
         max-width:1040px;margin:0 auto;padding:32px 20px;line-height:1.5}
    h1{font-size:28px;margin:0 0 4px} h2{font-size:20px;margin:40px 0 8px;border-top:1px solid #e4e3df;padding-top:24px}
    .meta{color:#52514e;font-size:13px} .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:20px 0}
    .kpi{background:#fff;border:1px solid #e4e3df;border-radius:8px;padding:12px 14px}
    .kpi .v{font-size:22px;font-weight:600} .kpi .l{font-size:12px;color:#52514e}
    table{border-collapse:collapse;width:100%;font-size:12px;margin:8px 0 16px;display:block;overflow-x:auto}
    th,td{padding:6px 8px;border-bottom:1px solid #e4e3df;text-align:left;white-space:nowrap}
    th{color:#52514e;font-weight:600} img{max-width:100%;height:auto}
    .note{background:#f4f3ef;border-left:3px solid #52514e;padding:10px 14px;font-size:13px}
    """
    kupiec99 = bt[(bt.method == "historical") & (bt.confidence == 0.99)].iloc[0]
    kupiec95 = bt[(bt.method == "historical") & (bt.confidence == 0.95)].iloc[0]

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Consolidated Risk Report</title><style>{css}</style></head><body>
<h1>Consolidated Risk Report</h1>
<div class="meta">Generated {date.today().isoformat()} · Equal-weighted {var_es['n_assets']}-stock portfolio,
${notional:,.0f} notional · Market data {var_es['sample_start']} → {var_es['sample_end']} (Yahoo Finance) ·
Financials: SEC EDGAR 10-K filings</div>

<div class="kpis">
 <div class="kpi"><div class="v">{usd(v99h['hist_var'] * notional)}</div><div class="l">1-day 99% historical VaR ({v99h['hist_var']*100:.2f}%)</div></div>
 <div class="kpi"><div class="v">{usd(v99h['hist_es'] * notional)}</div><div class="l">1-day 99% historical ES ({v99h['hist_es']*100:.2f}%)</div></div>
 <div class="kpi"><div class="v">{kupiec99['kupiec_result']} / {kupiec95['kupiec_result']}</div><div class="l">Kupiec POF, historical VaR, 99% / 95%</div></div>
 <div class="kpi"><div class="v">{len(stress['scenarios'])}</div><div class="l">Historical stress scenarios</div></div>
 <div class="kpi"><div class="v">{len(cr)} · 5 tiers</div><div class="l">Companies credit-scored</div></div>
 <div class="kpi"><div class="v">{n_fail} fail · {n_warn} warn</div><div class="l">Data-quality checks ({len(dq_df)} run)</div></div>
</div>

<h2>1. Market risk — VaR and Expected Shortfall</h2>
<p>Full-sample 1-day estimates over {var_es['n_days']} trading days. Annualised portfolio volatility
{var_es['annualised_vol']*100:.1f}%; worst day {var_es['worst_day_return']*100:.2f}% on {var_es['worst_day_date']}.</p>
{_table(var_rows, {c: pct(3) for c in ['Hist VaR','Hist ES','Param VaR','Param ES']} | {'Hist VaR (USD)': usd, 'Hist ES (USD)': usd})}

<h2>2. VaR backtest — Kupiec POF and Christoffersen independence</h2>
<p>Out-of-sample, one-day-ahead forecasts from a rolling {backtest['window_days']}-day window,
{backtest['test_start']} → {backtest['test_end']}. H0 rejected at {backtest['significance']:.0%}.</p>
<img alt="Realised daily losses against rolling 99% historical VaR with breaches marked" src="data:image/png;base64,{chart_backtest(series)}">
{_table(bt_tbl, {'expected_breaches': lambda v: f'{v:.1f}', 'kupiec_lr': lambda v: f'{v:.3f}',
                 'kupiec_p_value': lambda v: f'{v:.4f}', 'christoffersen_ind_p_value': lambda v: f'{v:.4f}'})}
<div class="note">Reading the result: at 95% both methods fail Kupiec because there are <em>too few</em> breaches
(over-conservative — the rolling window still carried 2022's volatility into calmer periods). At 99% both pass the
breach-count test but fail Christoffersen independence: breaches cluster in stress periods, which a rolling-window
VaR reacts to too slowly.</div>

<h2>3. Stress testing — historical scenarios</h2>
<img alt="Scenario P&L by method" src="data:image/png;base64,{chart_stress(stress)}">
{_table(st, {'S&P 500': pct(1), 'P&L (USD)': usd, 'P&L %': pct(1)})}
<div class="note">Reference: 1-day 99% historical VaR {usd(stress['var_reference']['var_1d_usd'])},
ES {usd(stress['var_reference']['es_1d_usd'])}. Multi-week windows are compared with VaR scaled by √h, which assumes
i.i.d. returns — exactly the assumption crises break — so treat that comparison as a reference point only.</div>

<h2>4. Credit risk — ratio-based scorecard</h2>
<p><strong>Simplified, educational model — not a credit rating.</strong> Composite of percentile-ranked leverage,
cash-flow coverage, liquidity, profitability and Altman Z'' on each company's latest 10-K.</p>
<img alt="Composite credit score by company, coloured by tier" src="data:image/png;base64,{chart_credit(credit['companies'])}">
{_table(tiers, {'avg_score': lambda v: f'{v:.1f}', 'avg_equity_vol': pct(1), 'avg_max_drawdown': pct(1), 'safe_zone_share': pct(0)})}
<p>Directional validation vs realised equity risk (Spearman, n={len(cr)}): score vs equity volatility
ρ = {val['spearman_score_vs_equity_vol']['rho']:+.3f} (p = {val['spearman_score_vs_equity_vol']['p_value']:.3f});
score vs max drawdown ρ = {val['spearman_score_vs_max_drawdown']['rho']:+.3f}
(p = {val['spearman_score_vs_max_drawdown']['p_value']:.3f}). Signs are in the expected direction but not
statistically significant at this sample size. Year-on-year score stability ρ = {val['spearman_latest_vs_prior_year_score']['rho']:.3f}.</p>
{_table(cr, {'composite_score': lambda v: f'{v:.1f}', 'altman_z2': lambda v: f'{v:.2f}'})}

<h2>5. Data quality</h2>
{_table(dq_df)}
</body></html>"""


def main():
    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / "risk_report.html"
    out.write_text(build_html(), encoding="utf-8")
    print(f"Wrote {out} ({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
