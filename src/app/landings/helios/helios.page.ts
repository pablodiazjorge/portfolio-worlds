import { ChangeDetectionStrategy, Component, computed, ElementRef, inject, viewChild } from '@angular/core';
import { injectWorldScene } from '../../core/engine/inject-world-scene';
import { Reveal } from '../../core/scroll/reveal.directive';
import { injectFrameLoop, injectScrollDirector } from '../../core/scroll/inject-scroll-director';
import { Site } from '../../core/site.service';

@Component({
  selector: 'pw-helios',
  imports: [Reveal],
  templateUrl: './helios.page.html',
  styleUrl: './helios.page.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class HeliosPage {
  protected readonly site = inject(Site);
  private readonly altitude = viewChild<ElementRef<HTMLElement>>('altitude');
  private readonly distance = viewChild<ElementRef<HTMLElement>>('distance');

  /** Waypoints from the oldest job, close to the planet, to the newest, close to the station. */
  protected readonly route = computed(() => [...this.site.portfolio().experience].sort((a, b) => a.startYear - b.startYear));

  private readonly scene = injectWorldScene(async (ctx) => {
    const { HeliosScene } = await import('./helios.scene');
    return new HeliosScene(ctx);
  });

  private readonly director = injectScrollDirector(this.scene);

  constructor() {
    const formats = {
      en: new Intl.NumberFormat('en-GB', { maximumFractionDigits: 0 }),
      es: new Intl.NumberFormat('es-ES', { maximumFractionDigits: 0 }),
    };
    let frame = 0;
    injectFrameLoop(() => {
      if (++frame % 4 !== 0) return;
      const scene = this.scene();
      const altitude = this.altitude()?.nativeElement;
      const distance = this.distance()?.nativeElement;
      if (!scene || !altitude || !distance) return;
      const format = formats[this.site.lang()];
      altitude.textContent = format.format(scene.telemetry.altitude);
      distance.textContent = format.format(scene.telemetry.distance);
    });
  }

  protected goTo(index: number): void {
    this.director()?.scrollToAnchor(index);
  }
}
