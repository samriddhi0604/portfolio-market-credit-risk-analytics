import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import Lenis from 'lenis';
import 'lenis/dist/lenis.css';
import './style.css';
import { runPreloader } from './sections/preloader';
import { heroEntrance, initHeadlineReveals } from './sections/reveal';
import { initMarketSteps } from './sections/market';

gsap.registerPlugin(ScrollTrigger);

const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

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
  if (reduceMotion) return;
  heroEntrance();
  initHeadlineReveals();
  initMarketSteps();
  ScrollTrigger.refresh();
});

runPreloader();
