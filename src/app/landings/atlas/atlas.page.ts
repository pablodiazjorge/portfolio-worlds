import { ChangeDetectionStrategy, Component, computed, ElementRef, inject, signal, viewChild } from '@angular/core';
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

  constructor() {
    let last = -1;
    injectFrameLoop(() => {
      const director = this.director();
      const gauge = this.altimeter()?.nativeElement;
      if (!director || !gauge) return;
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

  protected goTo(index: number): void {
    this.director()?.scrollToAnchor(index);
  }
}
