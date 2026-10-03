import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import Lenis from 'lenis';
import 'lenis/dist/lenis.css';
import './style.css';
import { results } from './data';
import { initCounters, renderCountersFinal } from './sections/counters';
import { buildCredit, initCredit } from './sections/credit';
import { buildMarket, initMarket, renderMarketStatic } from './sections/market';
import { runPreloader } from './sections/preloader';
import { heroEntrance, initHeadlineReveals } from './sections/reveal';
import { buildStress, initStress, renderStressStatic } from './sections/stress';

gsap.registerPlugin(ScrollTrigger);

const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

// Build all data-driven DOM up front from the real exported results.
const market = buildMarket();
const beats = buildStress();
const credit = buildCredit();
document.getElementById('links-meta')!.textContent =
  `Results generated ${results.generated} · Prices: Yahoo Finance, ${results.var.sample_start} → ${results.var.sample_end} · ` +
  `Financials: SEC EDGAR 10-K companyfacts, ${results.universe.n_credit} companies · ` +
  `${results.data_quality.n_checks} data-quality checks: ${results.data_quality.pass} pass, ${results.data_quality.warn} warn, ${results.data_quality.fail} fail`;

if (!reduceMotion) {
  // Lenis owns the scroll feel; GSAP's ticker drives it so ScrollTrigger and Lenis share a clock.
  const lenis = new Lenis({ lerp: 0.1 });
  lenis.on('scroll', ScrollTrigger.update);
  gsap.ticker.add((time) => lenis.raf(time * 1000));
  gsap.ticker.lagSmoothing(0);
  document.querySelectorAll<HTMLAnchorElement>('a[href^="#"]').forEach((a) =>
    a.addEventListener('click', (e) => {
      e.preventDefault();
      lenis.scrollTo(a.getAttribute('href')!, { duration: 1.4 });
    }),
  );
}

window.addEventListener('preloader:complete', () => {
  if (reduceMotion) {
    renderMarketStatic(market);
    renderStressStatic(beats);
    renderCountersFinal();
    return;
  }
  heroEntrance();
  initHeadlineReveals();
  initMarket(market);
  initStress(beats);
  initCredit(credit);
  initCounters();
  initTopbarTheme();
  ScrollTrigger.refresh();
});

/** Top bar ink follows whichever section is behind it (dark panels, the accent panel, paper). */
function initTopbarTheme() {
  const bar = document.querySelector<HTMLElement>('.topbar')!;
  const zones: [string, string][] = [['.panel--dark', 'dark'], ['.limits', 'accent']];
  zones.forEach(([sel, on]) =>
    document.querySelectorAll(sel).forEach((el) =>
      ScrollTrigger.create({
        trigger: el, start: 'top 30px', end: 'bottom 30px',
        onToggle: (self) => {
          if (self.isActive) bar.dataset.on = on;
          else if (bar.dataset.on === on) delete bar.dataset.on;
        },
      }),
    ),
  );
}

runPreloader();
