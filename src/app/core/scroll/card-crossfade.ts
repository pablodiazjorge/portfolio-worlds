import { ScrollDirector } from './scroll-director';

interface Stage {
  readonly section: HTMLElement;
  readonly inner: HTMLElement;
  readonly face: HTMLElement;
  readonly index: number;
}

/**
 * Between two stops the cards cross-fade: the one leaving fades from the start of the move
 * and drifts at half the page's speed, and the one arriving does the same in reverse, so a
 * change of card reads as a dissolve rather than a page flying past. The fade follows the
 * director's stops, so every card, the last one included, is fully opaque where it rests.
 *
 * Sections are the `.hero` and `.stage` elements that are director anchors; each holds a
 * `.hero-inner` or `.stage-inner` layer, and the opacity goes on that layer's `.panel` when
 * it has one, because an opacity on an ancestor would switch off the panel's blur.
 */
export class CardCrossfade {
  private stages: Stage[] | null = null;

  constructor(private readonly host: HTMLElement) {}

  update(director: ScrollDirector): void {
    this.stages ??= Array.from(this.host.querySelectorAll<HTMLElement>('.hero, .stage')).flatMap((section) => {
      const inner = section.querySelector<HTMLElement>(':scope > .hero-inner, :scope > .stage-inner');
      const index = director.indexOf(section);
      const face = inner?.querySelector<HTMLElement>(':scope > .panel') ?? inner;
      return inner && face && index >= 0 ? [{ section, inner, face, index }] : [];
    });
    const k = director.keyframe();
    const viewport = window.innerHeight;
    for (const { section, inner, face, index } of this.stages) {
      // stops travelled from this card's own, positive once it is leaving
      const away = k - index;
      const opacity = away >= 0 ? 1 - smoothstep(0, 0.6, away) : 1 - smoothstep(0.1, 0.6, -away);
      const rect = section.getBoundingClientRect();
      // arriving it rises at half speed; leaving it stays pinned until the section runs out
      const drift = rect.top > 0 ? -0.5 * rect.top : -0.5 * Math.min(0, rect.bottom - viewport);
      face.style.opacity = opacity.toFixed(3);
      // hiding the whole layer, not just the panel, keeps it from catching clicks meant for the
      // card underneath while it drifts over it
      inner.style.visibility = opacity < 0.01 ? 'hidden' : '';
      inner.style.transform = Math.abs(drift) >= 0.5 ? `translate3d(0, ${drift.toFixed(1)}px, 0)` : '';
    }
  }
}

function smoothstep(edge0: number, edge1: number, x: number): number {
  const t = Math.min(1, Math.max(0, (x - edge0) / (edge1 - edge0)));
  return t * t * (3 - 2 * t);
}
