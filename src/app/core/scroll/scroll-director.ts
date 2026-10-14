import Lenis from 'lenis';

export interface ScrollDirectorOptions {
  /** Elements whose vertical centre marks a camera keyframe, in page order. */
  readonly anchors: readonly HTMLElement[];
  /** Smooth scrolling with Lenis; off under reduced motion. */
  readonly smooth: boolean;
  /** Fraction of each gap between anchors where the camera stays on its keyframe. */
  readonly hold?: number;
  /**
   * One wheel gesture, key press or swipe travels to the neighbouring anchor instead of
   * scrolling freely. An anchor marked `data-free` opens a stretch, up to the next anchor, that
   * scrolls normally (a long list); a gesture past either end of it steps on again.
   */
  readonly stepped?: boolean;
}

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));
const smootherstep = (t: number) => t * t * t * (t * (t * 6 - 15) + 10);
const easeInOutSine = (t: number) => -(Math.cos(Math.PI * t) - 1) / 2;

/** Seconds for one step between neighbouring anchors; longer jumps take a little longer. */
const STEP_DURATION = 2.8;

/** Wheel events closer together than this belong to the same gesture (trackpad inertia). */
const GESTURE_GAP = 220;
/** Pixels of wheel travel a gesture needs before it counts, so a stray nudge does nothing. */
const WHEEL_THRESHOLD = 24;
/** Pixels a finger has to travel before a swipe counts. */
const SWIPE_THRESHOLD = 36;

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
  /** Anchor index pairs [a, a + 1] between which the page scrolls freely. */
  private readonly free: [number, number][];
  private travelling = false;
  private lastWheel = 0;
  private wheelSum = 0;
  private answeredUntil = 0;
  private touchStartY: number | null = null;
  private touchAnswered = false;
  private settleTimer = 0;

  constructor(private readonly options: ScrollDirectorOptions) {
    this.lenis = options.smooth
      ? new Lenis({ autoRaf: true, lerp: 0.085, wheelMultiplier: 0.85, touchMultiplier: 1.4 })
      : null;
    this.free = options.anchors.flatMap((el, i): [number, number][] =>
      el.hasAttribute('data-free') && i + 1 < options.anchors.length ? [[i, i + 1]] : [],
    );
    this.observer = new ResizeObserver(() => this.measure());
    this.observer.observe(document.body);
    this.measure();
    if (options.stepped) {
      // capture on window runs before Lenis, which listens on window too
      window.addEventListener('wheel', this.onWheel, { passive: false, capture: true });
      window.addEventListener('touchstart', this.onTouchStart, { passive: true, capture: true });
      window.addEventListener('touchmove', this.onTouchMove, { passive: false, capture: true });
      window.addEventListener('touchend', this.onTouchEnd, { passive: true, capture: true });
      window.addEventListener('keydown', this.onKey);
      window.addEventListener('scroll', this.onScroll, { passive: true });
    }
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
    // a stepped page always comes to rest on an anchor and its travel is already eased, so the
    // camera follows the whole travel instead of rushing through the middle of it
    if (this.options.stepped) return i + local;
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
    if (this.options.stepped) {
      this.travel(index);
      return;
    }
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
    // anchors move with the layout, so a stepped page settles on its anchor again
    if (this.options.stepped) this.scheduleSettle();
  }

  destroy(): void {
    this.observer.disconnect();
    window.clearTimeout(this.settleTimer);
    if (this.options.stepped) {
      window.removeEventListener('wheel', this.onWheel, { capture: true });
      window.removeEventListener('touchstart', this.onTouchStart, { capture: true });
      window.removeEventListener('touchmove', this.onTouchMove, { capture: true });
      window.removeEventListener('touchend', this.onTouchEnd, { capture: true });
      window.removeEventListener('keydown', this.onKey);
      window.removeEventListener('scroll', this.onScroll);
    }
    this.lenis?.destroy();
  }

  /** The free stretch the page is in, if any. */
  private freeStretch(y = window.scrollY): [number, number] | null {
    return this.free.find(([a, b]) => y >= this.stops[a] - 2 && y <= this.stops[b] + 2) ?? null;
  }

  /**
   * Where a gesture in this direction takes the page: an anchor index, -1 to swallow it at the
   * first or last anchor, or null to let it scroll a free stretch.
   */
  private stepTarget(direction: 1 | -1): number | null {
    const y = window.scrollY;
    const stretch = this.freeStretch(y);
    let target: number;
    if (stretch) {
      const [a, b] = stretch;
      if (direction > 0 && y >= this.stops[b] - 2) target = b + 1;
      else if (direction < 0 && y <= this.stops[a] + 2) target = a - 1;
      else return null;
    } else {
      // coming back up into a free stretch lands on its end, so the list scrolls up from there
      target = this.nearest() + direction;
    }
    return target >= 0 && target < this.stops.length ? target : -1;
  }

  private travel(index: number): void {
    const target = this.stops[index];
    if (target === undefined) return;
    const steps = Math.max(1, Math.abs(index - this.nearest()));
    window.clearTimeout(this.settleTimer);
    this.travelling = true;
    const done = () => {
      this.travelling = false;
      this.answeredUntil = Math.max(this.answeredUntil, performance.now() + 120);
    };
    if (this.lenis) {
      const duration = Math.min(5, STEP_DURATION + 0.5 * (steps - 1));
      this.lenis.scrollTo(target, { duration, easing: easeInOutSine, lock: true, force: true, onComplete: done });
    } else {
      window.scrollTo({ top: target });
      requestAnimationFrame(done);
    }
  }

  private readonly onWheel = (event: WheelEvent) => {
    if (event.ctrlKey) return; // pinch zoom
    const direction = Math.sign(event.deltaY) as 1 | -1 | 0;
    if (!direction) return;
    const now = performance.now();
    if (now - this.lastWheel > GESTURE_GAP) this.wheelSum = 0;
    this.lastWheel = now;
    // the tail of a gesture that already moved the page, or a travel still under way
    const answered = this.travelling || now < this.answeredUntil;
    const target = answered ? -1 : this.stepTarget(direction);
    if (target === null) return;
    event.preventDefault();
    event.stopPropagation();
    if (answered) {
      this.answeredUntil = now + GESTURE_GAP;
      return;
    }
    this.wheelSum += Math.abs(event.deltaY);
    if (this.wheelSum < WHEEL_THRESHOLD) return;
    this.wheelSum = 0;
    this.answeredUntil = now + GESTURE_GAP;
    if (target >= 0) this.travel(target);
  };

  private readonly onTouchStart = (event: TouchEvent) => {
    this.touchStartY = event.touches[0]?.clientY ?? null;
    this.touchAnswered = false;
  };

  private readonly onTouchMove = (event: TouchEvent) => {
    if (this.touchStartY === null) return;
    const dy = this.touchStartY - (event.touches[0]?.clientY ?? this.touchStartY);
    if (Math.abs(dy) < 6) return;
    const target = this.travelling || this.touchAnswered ? -1 : this.stepTarget(dy > 0 ? 1 : -1);
    if (target === null) return;
    event.preventDefault();
    if (target >= 0 && Math.abs(dy) > SWIPE_THRESHOLD) {
      this.touchAnswered = true;
      this.travel(target);
    }
  };

  private readonly onTouchEnd = () => {
    this.touchStartY = null;
  };

  private readonly onKey = (event: KeyboardEvent) => {
    if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) return;
    const el = event.target as HTMLElement | null;
    if (el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName))) return;
    let direction: 1 | -1;
    switch (event.key) {
      case 'ArrowDown':
      case 'PageDown':
        direction = 1;
        break;
      case 'ArrowUp':
      case 'PageUp':
        direction = -1;
        break;
      case ' ':
        if (el && /^(BUTTON|A|SUMMARY)$/.test(el.tagName)) return; // Space presses the control
        direction = event.shiftKey ? -1 : 1;
        break;
      case 'Home':
      case 'End':
        event.preventDefault();
        if (!this.travelling) this.travel(event.key === 'Home' ? 0 : this.stops.length - 1);
        return;
      default:
        return;
    }
    const target = this.stepTarget(direction);
    if (target === null) return; // the browser scrolls the free stretch
    event.preventDefault();
    if (this.travelling || event.repeat || target < 0) return;
    this.travel(target);
  };

  private readonly onScroll = () => {
    if (!this.travelling) this.scheduleSettle();
  };

  private scheduleSettle(): void {
    window.clearTimeout(this.settleTimer);
    this.settleTimer = window.setTimeout(() => this.settle(), 160);
  }

  /**
   * After a scrollbar drag, a find-in-page jump, a resize or an overshoot out of a free
   * stretch, the page comes to rest on the nearest anchor.
   */
  private settle(): void {
    if (this.travelling) return;
    if (this.lenis?.isScrolling) {
      // still easing out of a drag or a fling: look again once it rests
      this.scheduleSettle();
      return;
    }
    const y = window.scrollY;
    if (this.freeStretch(y)) return;
    const index = this.nearest();
    if (Math.abs(this.stops[index] - y) > 2) this.travel(index);
  }
}
