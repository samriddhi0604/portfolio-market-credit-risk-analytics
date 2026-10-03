import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { SplitText } from 'gsap/SplitText';

gsap.registerPlugin(ScrollTrigger, SplitText);

/** Line-mask headline reveal: each line slides up from behind an overflow-hidden wrapper. */
export function splitReveal(el: HTMLElement, opts: { trigger?: Element; immediate?: boolean } = {}) {
  SplitText.create(el, {
    type: 'lines',
    linesClass: 'line-wrapper',
    mask: 'lines',
    autoSplit: true,
    onSplit(self) {
      return gsap.from(self.lines, {
        yPercent: 110,
        duration: 1.0,
        ease: 'expo.out',
        stagger: 0.08,
        ...(opts.immediate
          ? {}
          : { scrollTrigger: { trigger: opts.trigger ?? el, start: 'top 82%', once: true } }),
      });
    },
  });
}

export function initHeadlineReveals() {
  document.querySelectorAll<HTMLElement>('[data-split]').forEach((el) => splitReveal(el));
  document.querySelectorAll<HTMLElement>('[data-fade]').forEach((el) => {
    gsap.from(el, {
      y: 32,
      autoAlpha: 0,
      duration: 0.9,
      ease: 'power3.out',
      scrollTrigger: { trigger: el, start: 'top 88%', once: true },
    });
  });
}

/** Hero entrance — waits for the preloader so it never plays behind the overlay. */
export function heroEntrance() {
  const title = document.querySelector<HTMLElement>('[data-hero-title]');
  if (title) splitReveal(title, { immediate: true });
  gsap.from('[data-hero-sub], .hero__eyebrow', { y: 24, autoAlpha: 0, duration: 0.9, delay: 0.35, ease: 'power3.out' });
  gsap.from('[data-hero-cue]', { autoAlpha: 0, duration: 0.6, delay: 0.8 });
  gsap.fromTo('.hero__cue-line', { scaleX: 0 }, { scaleX: 1, duration: 1.2, ease: 'expo.inOut', repeat: -1, yoyo: true, delay: 1 });
}
