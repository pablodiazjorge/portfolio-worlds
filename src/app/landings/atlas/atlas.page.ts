import { ChangeDetectionStrategy, Component, computed, ElementRef, inject, signal, viewChild } from '@angular/core';
import { prefersReducedMotion } from '../../core/engine/device';
import { injectWorldScene } from '../../core/engine/inject-world-scene';
import { Reveal } from '../../core/scroll/reveal.directive';
import { injectFrameLoop, injectScrollDirector } from '../../core/scroll/inject-scroll-director';
import { Site } from '../../core/site.service';

@Component({
  selector: 'pw-atlas',
  imports: [Reveal],
  templateUrl: './atlas.page.html',
  styleUrl: './atlas.page.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AtlasPage {
  protected readonly site = inject(Site);
  private readonly altimeter = viewChild<ElementRef<HTMLElement>>('altimeter');

  /** Experience from the oldest job at the first camp to the newest near the summit. */
  protected readonly climb = computed(() => [...this.site.portfolio().experience].sort((a, b) => a.startYear - b.startYear));

  /** Labels for the route gauge, one per camera stop. */
  protected readonly stops = computed(() => {
    const a = this.site.t().atlas;
    return [
      { label: a.hero, index: 0 },
      { label: a.baseCamp, index: 1 },
      ...this.climb().map((job, i) => ({ label: String(job.startYear), index: i + 2 })),
      { label: a.ridge, index: 7 },
      { label: a.summit, index: 9 },
    ];
  });

  protected readonly active = signal(0);

  private readonly scene = injectWorldScene(async (ctx) => {
    const { AtlasScene } = await import('./atlas.scene');
    return new AtlasScene(ctx);
  });

  // every stop is one gesture away; only the project list scrolls freely
  private readonly director = injectScrollDirector(this.scene, { stepped: true });

  private readonly host = inject(ElementRef<HTMLElement>).nativeElement as HTMLElement;
  private stages: { section: HTMLElement; inner: HTMLElement }[] | null = null;

  constructor() {
    let last = -1;
    const still = prefersReducedMotion();
    injectFrameLoop(() => {
      const director = this.director();
      const gauge = this.altimeter()?.nativeElement;
      if (!director || !gauge) return;
      if (!still) this.crossfade();
      const k = director.keyframe();
      gauge.style.setProperty('--k', String(k / (director.count - 1)));
      const nearest = director.nearest();
      const stop = nearest >= 8 ? (nearest === 8 ? 7 : 9) : nearest;
      if (stop !== last) {
        last = stop;
        this.active.set(stop);
      }
    });
  }

  /**
   * Between two stops the cards cross-fade: the one leaving fades from the start of the move
   * and drifts at half the page's speed, and the one arriving does the same in reverse, so a
   * change of card reads as a dissolve rather than a page flying past.
   */
  private crossfade(): void {
    this.stages ??= Array.from(this.host.querySelectorAll<HTMLElement>('.hero, .stage')).flatMap((section) => {
      const inner = section.querySelector<HTMLElement>(':scope > .hero-inner, :scope > .stage-inner');
      return inner ? [{ section, inner }] : [];
    });
    const viewport = window.innerHeight;
    for (const { section, inner } of this.stages) {
      const rect = section.getBoundingClientRect();
      let opacity: number;
      let drift: number;
      if (rect.top <= 0) {
        // leaving: progress over the whole travel to the next stop, which is the section's height
        const travelled = -rect.top / Math.max(1, rect.height);
        opacity = 1 - smoothstep(0, 0.6, travelled);
        const pinnedTop = Math.min(0, rect.bottom - viewport);
        drift = -0.5 * pinnedTop;
      } else {
        opacity = 1 - smoothstep(0.15, 0.85, rect.top / viewport);
        drift = -0.5 * rect.top;
      }
      inner.style.opacity = opacity.toFixed(3);
      inner.style.transform = drift ? `translate3d(0, ${drift.toFixed(1)}px, 0)` : '';
      inner.style.visibility = opacity < 0.01 ? 'hidden' : '';
    }
  }

  protected goTo(index: number): void {
    this.director()?.scrollToAnchor(index);
  }
}

function smoothstep(edge0: number, edge1: number, x: number): number {
  const t = Math.min(1, Math.max(0, (x - edge0) / (edge1 - edge0)));
  return t * t * (3 - 2 * t);
}
