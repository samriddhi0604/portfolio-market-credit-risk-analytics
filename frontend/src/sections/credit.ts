import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { fmtPct, results } from '../data';
import { hideTip, showTip } from './svg';

gsap.registerPlugin(ScrollTrigger);

const FACTOR_NAMES: Record<string, string> = {
  leverage: 'Liabilities / assets',
  cash_flow_coverage: 'Operating cash flow / liabilities',
  liquidity: 'Current ratio',
  profitability_roa: 'Return on assets',
  profitability_margin: 'Net margin',
  altman_composite: "Altman Z'' (1995)",
};

export function buildCredit() {
  const c = results.credit;
  document.getElementById('credit-weights')!.innerHTML = Object.entries(c.factors)
    .map(([k, f]) => `<li><span>${FACTOR_NAMES[k] ?? k}</span><b>${Math.round(f.weight * 100)}%</b></li>`)
    .join('');

  const fig = document.getElementById('credit-chart')!;
  const companies = [...c.companies].sort((a, b) => b.composite_score - a.composite_score);
  const v = c.validation;
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
    <p class="credit__validation">Sanity check against realised equity risk (Spearman, n=${companies.length}):
      score vs volatility ρ = ${v.spearman_score_vs_equity_vol.rho.toFixed(2)} (p = ${v.spearman_score_vs_equity_vol.p_value!.toFixed(2)}),
      score vs max drawdown ρ = ${v.spearman_score_vs_max_drawdown.rho.toFixed(2)} (p = ${v.spearman_score_vs_max_drawdown.p_value!.toFixed(2)}).
      Right direction, not statistically significant — NVDA scores top on fundamentals with ${fmtPct(companies.find((x) => x.ticker === 'NVDA')!.equity_vol, 0).replace('+', '')} equity volatility.</p>`;

  fig.querySelectorAll<HTMLElement>('.cbar').forEach((el) => {
    const co = companies.find((x) => x.ticker === el.dataset.ticker)!;
    const html = `<b>${co.ticker}</b> · ${co.sector}<br>Score ${co.composite_score.toFixed(1)} · ${co.tier} (${co.tier_label})<br>
      Liab/assets ${co.liabilities_to_assets.toFixed(2)} · OCF/liab ${co.ocf_to_liabilities.toFixed(2)}<br>
      Altman Z'' ${co.altman_z2 === null ? 'n/a (unclassified balance sheet)' : co.altman_z2.toFixed(2) + ' (' + co.altman_zone + ')'}<br>
      <span class="tip__muted">10-K period ending ${co.period_end}</span>`;
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
