import Lenis from 'lenis';

export interface ScrollDirectorOptions {
  /** Elements whose vertical centre marks a camera keyframe, in page order. */
  readonly anchors: readonly HTMLElement[];
  /** Smooth scrolling with Lenis; off under reduced motion. */
  readonly smooth: boolean;
  /** Fraction of each gap between anchors where the camera stays on its keyframe. */
  readonly hold?: number;
}

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));
const smootherstep = (t: number) => t * t * t * (t * (t * 6 - 15) + 10);

/**
 * Turns page scroll into a keyframe position: `keyframe()` returns k when anchor k sits in
 * the middle of the viewport and eases between neighbours, holding on each anchor for a
 * while so the camera rests while the visitor reads.
 */
export class ScrollDirector {
  private readonly lenis: Lenis | null;
  private readonly observer: ResizeObserver;
  private stops: number[] = [];
  private maxScroll = 1;

  constructor(private readonly options: ScrollDirectorOptions) {
    this.lenis = options.smooth
      ? new Lenis({ autoRaf: true, lerp: 0.085, wheelMultiplier: 0.85, touchMultiplier: 1.4 })
      : null;
    this.observer = new ResizeObserver(() => this.measure());
    this.observer.observe(document.body);
    this.measure();
  }

  get count(): number {
    return this.options.anchors.length;
  }

  /** Scroll progress of the whole page, 0 to 1. */
  progress(): number {
    return clamp01(window.scrollY / this.maxScroll);
  }

  /** Scroll velocity in pixels per frame, smoothed by Lenis when it runs. */
  velocity(): number {
    return this.lenis?.velocity ?? 0;
  }

  keyframe(): number {
    const stops = this.stops;
    const n = stops.length;
    if (n < 2) return 0;
    const y = window.scrollY;
    if (y <= stops[0]) return 0;
    if (y >= stops[n - 1]) return n - 1;
    let i = 0;
    while (i < n - 2 && y > stops[i + 1]) i++;
    const local = (y - stops[i]) / Math.max(1, stops[i + 1] - stops[i]);
    const hold = this.options.hold ?? 0.22;
    return i + smootherstep(clamp01((local - hold) / (1 - 2 * hold)));
  }

  /** Index of the anchor closest to the viewport centre. */
  nearest(): number {
    const y = window.scrollY;
    let best = 0;
    for (let i = 1; i < this.stops.length; i++) {
      if (Math.abs(this.stops[i] - y) < Math.abs(this.stops[best] - y)) best = i;
    }
    return best;
  }

  scrollToAnchor(index: number): void {
    const target = this.stops[index];
    if (target === undefined) return;
    if (this.lenis) this.lenis.scrollTo(target, { duration: 1.6 });
    else window.scrollTo({ top: target });
  }

  measure(): void {
    const viewport = window.innerHeight;
    this.maxScroll = Math.max(1, document.documentElement.scrollHeight - viewport);
    this.stops = this.options.anchors.map((el) => {
      const rect = el.getBoundingClientRect();
      const top = rect.top + window.scrollY;
      const centre = top + Math.min(rect.height, viewport) / 2 - viewport / 2;
      return Math.min(this.maxScroll, Math.max(0, centre));
    });
    this.stops[0] = Math.min(this.stops[0], 0);
    if (this.stops.length > 1) this.stops[this.stops.length - 1] = this.maxScroll;
  }

  destroy(): void {
    this.observer.disconnect();
    this.lenis?.destroy();
  }
}
