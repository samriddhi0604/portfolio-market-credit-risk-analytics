import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

gsap.registerPlugin(ScrollTrigger);

/** Pins the market-risk panel and steps through Estimate -> Compare -> Test as the user scrolls. */
export function initMarketSteps() {
  const steps = gsap.utils.toArray<HTMLElement>('[data-steps="market"] .steps__item');
  ScrollTrigger.create({
    trigger: '[data-pin="market"]',
    start: 'top top',
    end: '+=220%',
    pin: true,
    scrub: true,
    onUpdate(self) {
      const active = Math.min(steps.length - 1, Math.floor(self.progress * steps.length));
      steps.forEach((s, i) => s.classList.toggle('is-active', i === active));
    },
  });
}
