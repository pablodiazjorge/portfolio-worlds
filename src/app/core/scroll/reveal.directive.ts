import { afterNextRender, DestroyRef, Directive, ElementRef, inject, input } from '@angular/core';

let shared: IntersectionObserver | null = null;

function observer(): IntersectionObserver {
  shared ??= new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        entry.target.classList.add('is-revealed');
        shared?.unobserve(entry.target);
      }
    },
    { rootMargin: '0px 0px -12% 0px', threshold: 0.15 },
  );
  return shared;
}

/**
 * Adds `is-revealed` the first time the element enters the viewport; each world's stylesheet
 * decides what the reveal looks like. Without JavaScript the content is simply visible.
 */
@Directive({
  selector: '[pwReveal]',
  host: { 'data-reveal': '', '[style.--reveal-delay]': 'delay() + "ms"' },
})
export class Reveal {
  readonly delay = input(0, { alias: 'pwReveal', transform: (v: number | string) => Number(v) || 0 });

  constructor() {
    const element = inject(ElementRef<HTMLElement>).nativeElement as HTMLElement;
    afterNextRender(() => observer().observe(element));
    inject(DestroyRef).onDestroy(() => shared?.unobserve(element));
  }
}
