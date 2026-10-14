import { ChangeDetectionStrategy, Component, ElementRef, inject } from '@angular/core';
import { injectWorldScene } from '../../core/engine/inject-world-scene';
import { CardCrossfade } from '../../core/scroll/card-crossfade';
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

  private readonly scene = injectWorldScene(async (ctx) => {
    const { AerisScene } = await import('./aeris.scene');
    return new AerisScene(ctx);
  });

  // every stop is one gesture away, and the drone flies to the next one; only the project
  // list scrolls freely
  private readonly director = injectScrollDirector(this.scene, { stepped: true });
  private readonly cards = new CardCrossfade(inject(ElementRef<HTMLElement>).nativeElement as HTMLElement);

  constructor() {
    injectFrameLoop(() => {
      const director = this.director();
      if (director?.smooth) this.cards.update(director);
    });
  }

  protected goTo(index: number): void {
    this.director()?.scrollToAnchor(index);
  }
}
