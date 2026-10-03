const NS = 'http://www.w3.org/2000/svg';

export function svg<K extends keyof SVGElementTagNameMap>(
  tag: K,
  attrs: Record<string, string | number> = {},
  parent?: Element,
): SVGElementTagNameMap[K] {
  const el = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v));
  parent?.appendChild(el);
  return el;
}

/** One shared floating tooltip, positioned next to the pointer and kept inside the viewport. */
let tip: HTMLDivElement | null = null;
export function showTip(html: string, x: number, y: number) {
  if (!tip) {
    tip = document.createElement('div');
    tip.className = 'tip';
    tip.setAttribute('role', 'status');
    document.body.appendChild(tip);
  }
  tip.innerHTML = html;
  tip.style.opacity = '1';
  const r = tip.getBoundingClientRect();
  const left = Math.min(window.innerWidth - r.width - 12, x + 14);
  const top = y - r.height - 14 < 8 ? y + 18 : y - r.height - 14;
  tip.style.transform = `translate(${Math.max(8, left)}px, ${top}px)`;
}
export function hideTip() {
  if (tip) tip.style.opacity = '0';
}
