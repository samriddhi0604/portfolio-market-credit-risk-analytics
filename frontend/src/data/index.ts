// Real results exported by `python reporting/export_frontend_data.py` — never edited by hand.
import raw from './results.json';

export interface BacktestResult {
  method: 'historical' | 'parametric';
  confidence: number;
  test_days: number;
  expected_breaches: number;
  actual_breaches: number;
  kupiec_lr: number;
  kupiec_p_value: number;
  kupiec_result: 'PASS' | 'FAIL';
  breach_direction: 'too_many' | 'too_few';
  christoffersen_ind_p_value: number;
  independence_result: 'PASS' | 'FAIL';
}

export interface Scenario {
  id: string;
  name: string;
  basis: string;
  start: string;
  end: string;
  trading_days: number;
  spx_return: number;
  yield_change_bp: number;
  method: string;
  pnl_total: number;
  pnl_pct: number;
  factor_pnl_total: number;
  by_sector: Record<string, number>;
  largest_losses: Record<string, number>;
  worst_day: { date: string; spx_return: number; pnl_total: number; pnl_pct: number; loss_to_var: number } | null;
}

export interface Company {
  ticker: string;
  sector: string;
  period_end: string;
  composite_score: number;
  tier: string;
  tier_label: string;
  altman_z2: number | null;
  altman_zone: string | null;
  liabilities_to_assets: number;
  ocf_to_liabilities: number;
  current_ratio: number | null;
  roa: number;
  net_margin: number;
  equity_vol: number;
  max_drawdown: number;
}

export interface Results {
  generated: string;
  universe: { n_stocks: number; n_credit: number; notional_usd: number };
  var: {
    sample_start: string;
    sample_end: string;
    n_days: number;
    annualised_vol: number;
    worst_day_return: number;
    worst_day_date: string;
    levels: Record<string, { hist_var: number; hist_es: number; param_var: number; param_es: number }>;
  };
  backtest: {
    window_days: number;
    test_start: string;
    test_end: string;
    results: BacktestResult[];
    series: { d: string; loss: number; var99: number }[];
  };
  stress: { var_reference: { var_1d_usd: number; es_1d_usd: number }; scenarios: Scenario[] };
  credit: {
    factors: Record<string, { ratio: string; weight: number; higher_is_stronger: boolean }>;
    tier_bands: Record<string, number | null>;
    validation: Record<string, { rho: number; p_value?: number }>;
    tier_summary: { tier: string; n: number; avg_score: number; avg_equity_vol: number; avg_max_drawdown: number }[];
    companies: Company[];
  };
  data_quality: { n_checks: number; pass: number; warn: number; fail: number };
}

export const results = raw as unknown as Results;

export const fmtUsd = (v: number) =>
  (v < 0 ? '−$' : '$') + Math.abs(Math.round(v)).toLocaleString('en-US');
export const fmtPct = (v: number, d = 1) =>
  (v < 0 ? '−' : v > 0 ? '+' : '') + Math.abs(v * 100).toFixed(d) + '%';
export const fmtDate = (iso: string) =>
  new Date(iso + 'T00:00:00Z').toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
