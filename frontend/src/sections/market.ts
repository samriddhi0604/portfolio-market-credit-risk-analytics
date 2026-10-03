import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { fmtDate, fmtUsd, results } from '../data';
import { hideTip, showTip, svg } from './svg';

gsap.registerPlugin(ScrollTrigger);

const W = 820;
const H = 440;
const M = { top: 24, right: 16, bottom: 34, left: 44 };

/**
 * Realised daily losses (loss days only) against the rolling 1-day 99% historical VaR, with every
 * breach marked. The whole chart is revealed left-to-right by a clip rect whose width is scrubbed
 * to scroll progress; a cursor carries the date and the running breach count.
 */
export function buildMarket() {
  const fig = document.getElementById('var-chart')!;
  const { series } = results.backtest;
  const hist99 = results.backtest.results.find((r) => r.method === 'historical' && r.confidence === 0.99)!;
  const hist95 = results.backtest.results.find((r) => r.method === 'historical' && r.confidence === 0.95)!;

  const maxY = Math.ceil(Math.max(...series.map((s) => Math.max(s.loss, s.var99))) * 100) / 100;
  const x = (i: number) => M.left + (i / (series.length - 1)) * (W - M.left - M.right);
  const y = (v: number) => H - M.bottom - (Math.max(0, v) / maxY) * (H - M.top - M.bottom);

  const root = svg('svg', { viewBox: `0 0 ${W} ${H}`, class: 'chart__svg', role: 'img',
    'aria-label': `Daily realised losses versus rolling 99% VaR, ${hist99.actual_breaches} breaches in ${hist99.test_days} days` }, fig);

  // Axes / grid (recessive)
  const grid = svg('g', { class: 'grid' }, root);
  for (let t = 0; t <= maxY + 1e-9; t += 0.02) {
    svg('line', { x1: M.left, x2: W - M.right, y1: y(t), y2: y(t) }, grid);
    svg('text', { x: M.left - 8, y: y(t) + 4, 'text-anchor': 'end' }, grid).textContent = `${Math.round(t * 100)}%`;
  }
  let lastYear = '';
  series.forEach((s, i) => {
    const yr = s.d.slice(0, 4);
    if (yr !== lastYear && s.d.slice(5, 7) === '01') {
      svg('text', { x: x(i), y: H - 10, 'text-anchor': 'middle' }, grid).textContent = yr;
      lastYear = yr;
    }
  });

  const clipId = 'var-clip';
  const clip = svg('clipPath', { id: clipId }, svg('defs', {}, root));
  const clipRect = svg('rect', { x: 0, y: 0, width: M.left, height: H }, clip);
  const plot = svg('g', { 'clip-path': `url(#${clipId})` }, root);

  // Loss-day spikes
  const spikes = series.map((s, i) => (s.loss > 0 ? `M${x(i).toFixed(1)},${y(0).toFixed(1)}V${y(s.loss).toFixed(1)}` : '')).join('');
  svg('path', { d: spikes, class: 'loss-spikes' }, plot);
  // VaR line
  const varPath = series.map((s, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(s.var99).toFixed(1)}`).join('');
  svg('path', { d: varPath, class: 'var-line' }, plot);
  // Breaches
  const breachIdx = series.map((s, i) => (s.loss > s.var99 ? i : -1)).filter((i) => i >= 0);
  const dots = breachIdx.map((i) => svg('circle', { cx: x(i), cy: y(series[i].loss), r: 5, class: 'breach' }, plot));

  // Legend
  const legend = document.createElement('figcaption');
  legend.className = 'chart__legend';
  legend.innerHTML = `
    <span><i class="key key--line"></i>Rolling 99% VaR (historical, ${results.backtest.window_days}d)</span>
    <span><i class="key key--spike"></i>Realised loss (loss days)</span>
    <span><i class="key key--dot"></i>Breach</span>`;
  fig.appendChild(legend);

  // Scrub cursor
  const cursor = svg('g', { class: 'cursor' }, root);
  svg('line', { x1: 0, x2: 0, y1: M.top, y2: H - M.bottom }, cursor);
  const cursorText = svg('text', { x: 6, y: M.top + 12 }, cursor);

  // Verdict overlay
  const verdict = document.createElement('div');
  verdict.className = 'verdict';
  verdict.innerHTML = `
    <div class="verdict__row"><span class="verdict__big">${hist99.actual_breaches}</span>
      <span>breaches vs <b>${hist99.expected_breaches.toFixed(1)}</b> expected at 99%
      over ${hist99.test_days} days</span></div>
    <div class="verdict__tests">
      <span>Kupiec 99% <b class="tag tag--${hist99.kupiec_result.toLowerCase()}">${hist99.kupiec_result}</b> p=${hist99.kupiec_p_value.toFixed(3)}</span>
      <span>Kupiec 95% <b class="tag tag--${hist95.kupiec_result.toLowerCase()}">${hist95.kupiec_result}</b> p=${hist95.kupiec_p_value.toFixed(3)} · too few breaches</span>
      <span>Independence 99% <b class="tag tag--${hist99.independence_result.toLowerCase()}">${hist99.independence_result}</b> p=${hist99.christoffersen_ind_p_value.toFixed(4)} · breaches cluster</span>
    </div>`;
  fig.appendChild(verdict);

  // Hover: nearest day
  const hit = svg('rect', { x: M.left, y: M.top, width: W - M.left - M.right, height: H - M.top - M.bottom, fill: 'transparent' }, root);
  const hoverLine = svg('line', { y1: M.top, y2: H - M.bottom, class: 'hover-line' }, root);
  hit.addEventListener('pointermove', (e) => {
    const pt = root.createSVGPoint();
    pt.x = e.clientX; pt.y = e.clientY;
    const local = pt.matrixTransform(root.getScreenCTM()!.inverse());
    const i = Math.max(0, Math.min(series.length - 1, Math.round(((local.x - M.left) / (W - M.left - M.right)) * (series.length - 1))));
    if (x(i) > Number(clipRect.getAttribute('width'))) return hideTip();
    const s = series[i];
    hoverLine.setAttribute('x1', String(x(i))); hoverLine.setAttribute('x2', String(x(i)));
    hoverLine.style.opacity = '1';
    showTip(`<b>${fmtDate(s.d)}</b><br>${s.loss >= 0 ? 'Loss' : 'Gain'} ${(Math.abs(s.loss) * 100).toFixed(2)}%<br>99% VaR ${(s.var99 * 100).toFixed(2)}%${s.loss > s.var99 ? '<br><em>Breach</em>' : ''}`, e.clientX, e.clientY);
  });
  hit.addEventListener('pointerleave', () => { hideTip(); hoverLine.style.opacity = '0'; });

  // Stats below the pinned panel
  const lv = results.var.levels['0.99'];
  const n = results.universe.notional_usd;
  document.getElementById('market-stats')!.innerHTML = `
    <div class="stat"><div class="stat__value" data-count="${Math.round(lv.hist_var * n)}" data-prefix="$"></div>
      <div class="stat__label">1-day 99% historical VaR on a ${fmtUsd(n)} book (${(lv.hist_var * 100).toFixed(2)}%)</div></div>
    <div class="stat"><div class="stat__value" data-count="${Math.round(lv.hist_es * n)}" data-prefix="$"></div>
      <div class="stat__label">1-day 99% Expected Shortfall — the average loss once VaR is breached</div></div>
    <div class="stat"><div class="stat__value"><span data-count="${hist99.actual_breaches}"></span><span class="stat__of"> / ${hist99.expected_breaches.toFixed(1)}</span></div>
      <div class="stat__label">Breaches vs expected, ${fmtDate(results.backtest.test_start)} – ${fmtDate(results.backtest.test_end)}</div></div>
    <div class="stat"><div class="stat__value" data-count="${hist99.kupiec_p_value}" data-decimals="3"></div>
      <div class="stat__label">Kupiec p-value at 99% <span class="stat__tag stat__tag--${hist99.kupiec_result.toLowerCase()}">${hist99.kupiec_result}</span></div></div>`;

  return { clipRect, dots, breachIdx, cursor, cursorText, verdict, x, series, W, M };
}

export function initMarket(chart: ReturnType<typeof buildMarket>) {
  const steps = gsap.utils.toArray<HTMLElement>('[data-steps="market"] .steps__item');
  const { clipRect, dots, breachIdx, cursor, cursorText, verdict, series, W, M } = chart;
  const reveal = { p: 0 };
  gsap.set(dots, { attr: { r: 0 } });
  gsap.set(verdict, { autoAlpha: 0, y: 20 });

  const render = () => {
    const xi = M.left + reveal.p * (W - M.left - M.right);
    clipRect.setAttribute('width', String(xi + 6));
    const idx = Math.round(reveal.p * (series.length - 1));
    const passed = breachIdx.filter((i) => i <= idx).length;
    cursor.setAttribute('transform', `translate(${xi},0)`);
    cursorText.textContent = `${series[idx].d}  ·  ${passed} breach${passed === 1 ? '' : 'es'}`;
    cursorText.setAttribute('text-anchor', xi > W * 0.7 ? 'end' : 'start');
    cursorText.setAttribute('x', xi > W * 0.7 ? '-6' : '6');
    dots.forEach((d, k) => gsap.to(d, { attr: { r: breachIdx[k] <= idx ? 5 : 0 }, duration: 0.25, overwrite: true }));
  };
  render();

  const tl = gsap.timeline({
    scrollTrigger: {
      trigger: '[data-pin="market"]',
      start: 'top top',
      end: '+=260%',
      pin: true,
      scrub: 0.6,
      onUpdate(self) {
        const active = self.progress < 0.3 ? 0 : self.progress < 0.68 ? 1 : 2;
        steps.forEach((s, i) => s.classList.toggle('is-active', i === active));
      },
    },
  });
  tl.to(reveal, { p: 1, ease: 'none', duration: 0.68, onUpdate: render })
    .to(cursor, { opacity: 0, duration: 0.05 }, 0.68)
    .to(verdict, { autoAlpha: 1, y: 0, duration: 0.15, ease: 'power2.out' }, 0.74)
    .to({}, { duration: 0.1 });
}

export function renderMarketStatic(chart: ReturnType<typeof buildMarket>) {
  chart.clipRect.setAttribute('width', String(chart.W));
  chart.cursor.style.display = 'none';
  chart.dots.forEach((d) => d.setAttribute('r', '5'));
  document.querySelectorAll('[data-steps="market"] .steps__item').forEach((s) => s.classList.add('is-active'));
}
