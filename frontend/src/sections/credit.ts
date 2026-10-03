import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { results } from '../data';
import { hideTip, showTip } from './svg';

gsap.registerPlugin(ScrollTrigger);

const FACTOR_NAMES: Record<string, string> = {
  leverage: 'Debt load — how much it owes vs. owns',
  cash_flow_coverage: 'Cash it brings in vs. what it owes',
  liquidity: 'Can it pay the bills due this year?',
  profitability_roa: 'Profit vs. the size of the business',
  profitability_margin: 'Profit from each dollar of sales',
  altman_composite: "Bankruptcy-warning score (Altman Z'')",
};

const NAMES: Record<string, string> = {
  AAPL: 'Apple', MSFT: 'Microsoft', NVDA: 'NVIDIA', ORCL: 'Oracle', CSCO: 'Cisco',
  JNJ: 'Johnson & Johnson', PFE: 'Pfizer', MRK: 'Merck', UNH: 'UnitedHealth', ABT: 'Abbott',
  XOM: 'ExxonMobil', CVX: 'Chevron', COP: 'ConocoPhillips', SLB: 'SLB (Schlumberger)', OXY: 'Occidental Petroleum',
  WMT: 'Walmart', PG: 'Procter & Gamble', KO: 'Coca-Cola', MCD: "McDonald's", HD: 'Home Depot',
  CAT: 'Caterpillar', BA: 'Boeing', HON: 'Honeywell', UPS: 'UPS', DE: 'Deere & Co.',
};

export function buildCredit() {
  const c = results.credit;
  document.getElementById('credit-weights')!.innerHTML = Object.entries(c.factors)
    .map(([k, f]) => `<li><span>${FACTOR_NAMES[k] ?? k}</span><b>${Math.round(f.weight * 100)}%</b></li>`)
    .join('');

  const fig = document.getElementById('credit-chart')!;
  const companies = [...c.companies].sort((a, b) => b.composite_score - a.composite_score);
  const v = c.validation;
  const top = companies[0];
  // Only claim the weakest tier was the riskiest on the market if the data actually says so.
  const ts = c.tier_summary;
  const t5 = ts.find((t) => t.tier === 'Tier 5');
  const t5Riskiest = !!t5 && ts.every((t) => t.avg_equity_vol <= t5.avg_equity_vol && t.avg_max_drawdown >= t5.avg_max_drawdown);
  fig.innerHTML = `
    <div class="cbars">${companies.map((co) => `
      <div class="cbar" data-tier="${co.tier.slice(-1)}" data-ticker="${co.ticker}" tabindex="0">
        <span class="cbar__t">${co.ticker}</span>
        <span class="cbar__track"><i style="--w:${co.composite_score / 100}"></i></span>
        <span class="cbar__s">${co.composite_score.toFixed(0)}</span>
        <span class="cbar__tier">${co.tier.replace('Tier ', 'T')}</span>
      </div>`).join('')}
    </div>
    <figcaption class="chart__legend chart__legend--tiers">
      ${['1', '2', '3', '4', '5'].map((t) => `<span><i class="key key--tier" data-tier="${t}"></i>Tier ${t}</span>`).join('')}
    </figcaption>
    <p class="credit__validation"><b>Does the score hold up?</b> Companies in weak financial shape
      usually have bumpier stock prices. Our scores lean that way${t5Riskiest ? " — the Tier 5 group's stocks swung the most and fell the furthest —" : ','} but across all ${companies.length} companies the link is weak
      and could be chance (correlation ${v.spearman_score_vs_equity_vol.rho.toFixed(2)}, p = ${v.spearman_score_vs_equity_vol.p_value!.toFixed(2)}).
      The clearest exception: ${NAMES[top.ticker] ?? top.ticker} has the top score on paper, yet its stock
      swings about ${Math.round(top.equity_vol * 100)}% a year.</p>`;

  fig.querySelectorAll<HTMLElement>('.cbar').forEach((el) => {
    const co = companies.find((x) => x.ticker === el.dataset.ticker)!;
    const zone: Record<string, string> = { safe: 'safe zone', grey: 'grey zone', distress: 'warning zone' };
    const html = `<b>${NAMES[co.ticker] ?? co.ticker}</b> (${co.ticker}) · ${co.sector}<br>
      Score ${co.composite_score.toFixed(0)} / 100 · ${co.tier} — ${co.tier_label}<br>
      Owes ${co.liabilities_to_assets < 1 ? Math.round(co.liabilities_to_assets * 100) + '¢' : '$' + co.liabilities_to_assets.toFixed(2)} for every $1 it owns<br>
      Bankruptcy-warning formula: ${co.altman_z2 === null ? 'not available (its accounts mix in a lending business)' : co.altman_z2.toFixed(1) + ' — ' + zone[co.altman_zone ?? ''] }<br>
      <span class="tip__muted">From its annual report for the year ending ${co.period_end}</span>`;
    el.addEventListener('pointermove', (e) => showTip(html, e.clientX, e.clientY));
    el.addEventListener('pointerleave', hideTip);
    el.addEventListener('focus', () => { const r = el.getBoundingClientRect(); showTip(html, r.right - 120, r.top); });
    el.addEventListener('blur', hideTip);
  });
  return fig;
}

export function initCredit(fig: HTMLElement) {
  const bars = fig.querySelectorAll('.cbar__track i');
  const rows = fig.querySelectorAll('.cbar');
  const weights = document.querySelectorAll('#credit-weights li');
  const tl = gsap.timeline({
    scrollTrigger: { trigger: '[data-pin="credit"]', start: 'top top', end: '+=200%', pin: true, scrub: 0.6 },
  });
  tl.from(weights, { autoAlpha: 0.15, x: -12, stagger: 0.06, duration: 0.2 }, 0)
    .from(rows, { autoAlpha: 0, duration: 0.1, stagger: 0.02 }, 0.1)
    .from(bars, { scaleX: 0, duration: 0.4, stagger: 0.02, ease: 'power2.out' }, 0.15)
    .from('.credit__validation, .chart__legend--tiers', { autoAlpha: 0, y: 12, duration: 0.15 }, 0.85);
}
