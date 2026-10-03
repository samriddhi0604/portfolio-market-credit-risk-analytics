import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { fmtDate, fmtPct, fmtUsd, results, type Scenario } from '../data';

gsap.registerPlugin(ScrollTrigger);

const SCALE = 0.6; // bar full width = 60% portfolio move, enough for the GFC replay (-49%)

// What each episode was, in one sentence. The numbers shown next to it come from the data.
const PLAIN: Record<string, string> = {
  gfc_2008: "The 2008 global financial crisis, measured from the stock market's peak to its lowest point.",
  covid_2020: 'The month-long crash when COVID-19 shut down much of the world economy.',
  rates_2022: 'The year US interest rates rose at their fastest pace in decades to fight inflation.',
  bonds_1994: 'A surprise run of interest-rate rises that caused a bond-market rout.',
};

function moveWords(spx: number, bp: number) {
  const mkt = `the US stock market (S&amp;P 500) ${spx < 0 ? 'fell' : 'rose'} ${Math.abs(spx * 100).toFixed(1)}%`;
  const rate = `the 10-year US interest rate ${bp > 0 ? 'rose' : 'fell'} by ${Math.abs(bp / 100).toFixed(2)} percentage points`;
  return `Over this period, ${mkt} and ${rate}.`;
}

function beatHtml(s: Scenario, i: number, n: number) {
  const replay = s.method.startsWith('full');
  const sectors = Object.entries(s.by_sector).sort((a, b) => a[1] - b[1]);
  const maxAbs = Math.max(...sectors.map(([, v]) => Math.abs(v)));
  const [worstName, worstVal] = sectors[0];
  const [bestName, bestVal] = sectors[sectors.length - 1];
  const notional = results.universe.notional_usd;
  const takeaway = bestVal > 0
    ? `Hit hardest: <b>${worstName}</b> (${fmtUsd(worstVal)}). Biggest help: <b>${bestName}</b> (+${fmtUsd(bestVal)}).`
    : `Hit hardest: <b>${worstName}</b> (${fmtUsd(worstVal)}). Every sector lost money.`;
  return `
  <article class="beat" data-beat="${i}">
    <div class="beat__meta"><span>Crisis ${i + 1} of ${n}</span>
      <span>${fmtDate(s.start)} → ${fmtDate(s.end)} · ${s.trading_days} trading days</span></div>
    <h3 class="beat__name">${s.name}</h3>
    <p class="beat__basis">${PLAIN[s.id] ?? s.basis} ${moveWords(s.spx_return, s.yield_change_bp)}</p>
    <div class="beat__pnl ${s.pnl_total < 0 ? 'is-loss' : 'is-gain'}">
      <span class="beat__num" data-target="${s.pnl_pct}">0.0%</span>
      <span class="beat__usd">${s.pnl_total < 0 ? 'a loss of' : 'a gain of'} ${fmtUsd(Math.abs(s.pnl_total))} on our ${fmtUsd(notional)} portfolio</span>
    </div>
    <div class="beat__bar"><div class="beat__axis"></div>
      <div class="beat__fill ${s.pnl_total < 0 ? 'is-loss' : 'is-gain'}" style="--w:${Math.min(1, Math.abs(s.pnl_pct) / SCALE)}"></div></div>
    <p class="beat__takeaway">${takeaway}</p>
    <p class="beat__method">${replay
      ? `How we measured it: each stock's real price change between these two dates. A simpler shortcut — guessing from how each stock usually follows the market — would have said ${fmtPct(s.factor_pnl_total / notional)}.`
      : `This one is an estimate: our stock prices don't go back to 1994, so we used how each stock reacts to market and interest-rate moves today.`}</p>
    <p class="beat__stitle">Gain or loss by sector</p>
    <ul class="beat__sectors">${sectors.map(([k, v]) => `
      <li><span>${k}</span><span class="beat__sbar"><i class="${v < 0 ? 'is-loss' : 'is-gain'}" style="--w:${Math.abs(v) / maxAbs}"></i></span><span>${fmtUsd(v)}</span></li>`).join('')}
    </ul>
    ${s.worst_day ? `<p class="beat__day">Worst single day, ${fmtDate(s.worst_day.date)}: the portfolio fell <b>${Math.abs(s.worst_day.pnl_pct * 100).toFixed(2)}%</b> —
      <b>${s.worst_day.loss_to_var.toFixed(1)}×</b> the daily risk limit of ${fmtUsd(results.stress.var_reference.var_1d_usd)}.</p>` : ''}
  </article>`;
}

export function buildStress() {
  const host = document.getElementById('stress-beats')!;
  const sc = results.stress.scenarios;
  host.innerHTML = sc.map((s, i) => beatHtml(s, i, sc.length)).join('');
  return gsap.utils.toArray<HTMLElement>('.beat', host);
}

function setNum(beat: HTMLElement, p: number) {
  const el = beat.querySelector<HTMLElement>('.beat__num')!;
  el.textContent = fmtPct(Number(el.dataset.target) * p);
}

/** One scenario per scroll "beat": the card enters, its P&L bar and number scrub with scroll, it exits. */
export function initStress(beats: HTMLElement[]) {
  gsap.set(beats, { autoAlpha: 0, yPercent: 8 });
  const tl = gsap.timeline({
    defaults: { ease: 'power2.out' },
    scrollTrigger: { trigger: '[data-pin="stress"]', start: 'top top', end: `+=${beats.length * 110}%`, pin: true, scrub: 0.6 },
  });
  beats.forEach((beat, i) => {
    const prog = { p: 0 };
    const at = i * 1.0;
    tl.to(beat, { autoAlpha: 1, yPercent: 0, duration: 0.2 }, at)
      .fromTo(beat.querySelector('.beat__fill'), { scaleX: 0 }, { scaleX: 1, duration: 0.45, ease: 'none' }, at + 0.15)
      .to(prog, { p: 1, duration: 0.45, ease: 'none', onUpdate: () => setNum(beat, prog.p) }, at + 0.15)
      .fromTo(beat.querySelectorAll('.beat__sbar i'), { scaleX: 0 }, { scaleX: 1, duration: 0.3, stagger: 0.03, ease: 'power2.out' }, at + 0.3);
    if (i < beats.length - 1) tl.to(beat, { autoAlpha: 0, yPercent: -8, duration: 0.2, ease: 'power2.in' }, at + 0.85);
  });
}

export function renderStressStatic(beats: HTMLElement[]) {
  beats.forEach((b) => { b.classList.add('is-static'); setNum(b, 1); });
}
