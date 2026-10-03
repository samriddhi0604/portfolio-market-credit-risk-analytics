import gsap from 'gsap';

/**
 * Percentage preloader driven by real asset progress — not a timer.
 * Tracked assets: each web-font face the page uses, plus the window `load` event (stylesheets,
 * scripts). The counter only ever tweens toward the fraction actually loaded, and reaches 100
 * only when every tracked asset has settled. Fires `preloader:complete` on window when done.
 */
const FONT_FACES = [
  '900 1em Fraunces',
  '700 1em Fraunces',
  '400 1em Inter',
  '500 1em Inter',
  '400 1em "JetBrains Mono"',
];
const FONT_TIMEOUT_MS = 6000; // a font that never arrives counts as settled (fallback font used)

export function runPreloader(): Promise<void> {
  const root = document.getElementById('preloader');
  const countEl = document.getElementById('preloader-count');
  const labelEl = document.getElementById('preloader-label');
  if (!root || !countEl) return Promise.resolve();

  document.documentElement.classList.add('is-loading');
  const total = FONT_FACES.length + 1;
  let settled = 0;
  const shown = { value: 0 };

  const advance = (what: string) => {
    settled += 1;
    if (labelEl) labelEl.textContent = `Loaded ${what}`;
    gsap.to(shown, {
      value: (settled / total) * 100,
      duration: 0.45,
      ease: 'power2.out',
      overwrite: true,
      onUpdate: () => { countEl.textContent = String(Math.round(shown.value)); },
    });
  };

  const withTimeout = <T,>(p: Promise<T>) =>
    Promise.race([p, new Promise((r) => setTimeout(r, FONT_TIMEOUT_MS))]);

  const fonts = FONT_FACES.map((face) =>
    withTimeout(document.fonts.load(face)).catch(() => undefined).then(() => advance(face.replace(/^\d+ 1em /, '').replace(/"/g, ''))),
  );
  const page = new Promise<void>((resolve) => {
    if (document.readyState === 'complete') resolve();
    else window.addEventListener('load', () => resolve(), { once: true });
  }).then(() => advance('page assets'));

  return Promise.all([...fonts, page]).then(
    () =>
      new Promise<void>((resolve) => {
        gsap.timeline({
          onComplete: () => {
            root.remove();
            document.documentElement.classList.remove('is-loading');
            window.dispatchEvent(new CustomEvent('preloader:complete'));
            resolve();
          },
        })
          .to(shown, {
            value: 100, duration: 0.3, ease: 'power1.out',
            onUpdate: () => { countEl.textContent = String(Math.round(shown.value)); },
          })
          .to(root, { yPercent: -100, duration: 0.9, ease: 'expo.inOut' }, '+=0.15');
      }),
  );
}
