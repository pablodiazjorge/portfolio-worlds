import { ChangeDetectionStrategy, Component, computed, ElementRef, inject, signal, viewChildren } from '@angular/core';
import { injectWorldScene } from '../../core/engine/inject-world-scene';
import { Reveal } from '../../core/scroll/reveal.directive';
import { injectFrameLoop, injectScrollDirector } from '../../core/scroll/inject-scroll-director';
import { Site } from '../../core/site.service';

@Component({
  selector: 'pw-terra',
  imports: [Reveal],
  templateUrl: './terra.page.html',
  styleUrl: './terra.page.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TerraPage {
  protected readonly site = inject(Site);
  private readonly cards = viewChildren<ElementRef<HTMLElement>>('projectCard');

  /** One build phase per job, from the oldest to the newest. */
  protected readonly phases = computed(() => [...this.site.portfolio().experience].sort((a, b) => a.startYear - b.startYear));

  /** Title block label for every camera stop. */
  protected readonly sheets = computed(() => {
    const t = this.site.t();
    return [t.worlds.terra.name, t.terra.site, ...t.terra.phases, t.sections.projects, t.sections.projects, t.sections.contact];
  });

  protected readonly sheet = signal(0);

  private readonly scene = injectWorldScene(async (ctx) => {
    const { TerraScene } = await import('./terra.scene');
    return new TerraScene(ctx, this.site.portfolio().projects.map((p) => p.cover));
  });

  private readonly director = injectScrollDirector(this.scene);

  constructor() {
    let frame = 0;
    injectFrameLoop(() => {
      const director = this.director();
      if (!director) return;
      if (++frame % 6 !== 0) return;
      const nearest = director.nearest();
      if (nearest !== this.sheet()) this.sheet.set(nearest);
      const scene = this.scene();
      if (!scene || nearest < 7 || nearest > 8) return;
      const centre = window.innerHeight / 2;
      let best = 0;
      let bestDistance = Infinity;
      this.cards().forEach((card, i) => {
        const rect = card.nativeElement.getBoundingClientRect();
        const distance = Math.abs(rect.top + rect.height / 2 - centre);
        if (distance < bestDistance) {
          bestDistance = distance;
          best = i;
        }
      });
      scene.showProject(best);
    });
  }

  protected goTo(index: number): void {
    this.director()?.scrollToAnchor(index);
  }
}
