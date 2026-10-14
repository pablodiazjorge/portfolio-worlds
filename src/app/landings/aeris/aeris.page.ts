import { ChangeDetectionStrategy, Component, ElementRef, inject, viewChild, viewChildren } from '@angular/core';
import { injectWorldScene } from '../../core/engine/inject-world-scene';
import { Reveal } from '../../core/scroll/reveal.directive';
import { injectFrameLoop, injectScrollDirector } from '../../core/scroll/inject-scroll-director';
import { Site } from '../../core/site.service';

@Component({
  selector: 'pw-aeris',
  imports: [Reveal],
  templateUrl: './aeris.page.html',
  styleUrl: './aeris.page.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AerisPage {
  protected readonly site = inject(Site);
  private readonly callout = viewChild<ElementRef<SVGSVGElement>>('callout');
  private readonly layerPanels = viewChildren<ElementRef<HTMLElement>>('layerPanel');

  private readonly scene = injectWorldScene(async (ctx) => {
    const { AerisScene } = await import('./aeris.scene');
    return new AerisScene(ctx);
  });

  private readonly director = injectScrollDirector(this.scene);

  constructor() {
    injectFrameLoop(() => this.drawCallout());
  }

  protected goTo(index: number): void {
    this.director()?.scrollToAnchor(index);
  }

  /** Draws the line from the highlighted layer of the drone to its text panel. */
  private drawCallout(): void {
    const svg = this.callout()?.nativeElement;
    const scene = this.scene();
    const director = this.director();
    if (!svg || !scene || !director) return;
    const k = director.keyframe();
    const index = Math.round(k) - 2;
    const strength = Math.max(0, 1 - Math.abs(k - Math.round(k)) * 3);
    const panel = this.layerPanels()[index]?.nativeElement;
    const width = window.innerWidth;
    const height = window.innerHeight;
    const point = index >= 0 && index < 5 ? scene.layerPoint(index, width, height) : null;
    if (!panel || !point || strength <= 0 || width < 768) {
      svg.style.opacity = '0';
      return;
    }
    const rect = panel.getBoundingClientRect();
    const panelOnLeft = rect.left < width / 2;
    const ex = panelOnLeft ? rect.right : rect.left;
    const ey = Math.min(Math.max(point.y, rect.top + 40), rect.bottom - 40);
    const mx = panelOnLeft ? ex + 48 : ex - 48;
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    svg.style.opacity = String(strength);
    svg.querySelector('polyline')?.setAttribute('points', `${point.x},${point.y} ${mx},${ey} ${ex},${ey}`);
    const dot = svg.querySelector('circle');
    dot?.setAttribute('cx', String(point.x));
    dot?.setAttribute('cy', String(point.y));
  }
}
