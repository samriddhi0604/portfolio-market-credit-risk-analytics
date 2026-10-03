import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

gsap.registerPlugin(ScrollTrigger);

/**
 * Rolling count-up for stat numbers. Markup: <span data-count="0.5442" data-decimals="3"
 * data-prefix="$" data-suffix="%"></span>. Fires once when scrolled into view and never replays,
 * so a number never re-animates mid-read. Final text is always the exact formatted value.
 */
export function format(v: number, decimals: number, grouping: boolean) {
  return v.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
    useGrouping: grouping,
  });
}

export function initCounters(root: ParentNode = document) {
  root.querySelectorAll<HTMLElement>('[data-count]').forEach((el) => {
    const target = Number(el.dataset.count);
    const decimals = Number(el.dataset.decimals ?? 0);
    const prefix = el.dataset.prefix ?? '';
    const suffix = el.dataset.suffix ?? '';
    const grouping = el.dataset.grouping !== 'false';
    const render = (v: number) => { el.textContent = prefix + format(v, decimals, grouping) + suffix; };
    render(0);
    const state = { v: 0 };
    ScrollTrigger.create({
      trigger: el,
      start: 'top 90%',
      once: true,
      onEnter: () =>
        gsap.to(state, {
          v: target,
          duration: 1.6,
          ease: 'power3.out',
          onUpdate: () => render(state.v),
          onComplete: () => render(target),
        }),
    });
  });
}

/** Static fallback (reduced motion): write final values immediately. */
export function renderCountersFinal(root: ParentNode = document) {
  root.querySelectorAll<HTMLElement>('[data-count]').forEach((el) => {
    el.textContent = (el.dataset.prefix ?? '') +
      format(Number(el.dataset.count), Number(el.dataset.decimals ?? 0), el.dataset.grouping !== 'false') +
      (el.dataset.suffix ?? '');
  });
}
