import { afterNextRender, DestroyRef, effect, ElementRef, inject, Signal, signal } from '@angular/core';
import { prefersReducedMotion } from '../engine/device';
import { ScrollDirector } from './scroll-director';

export interface ScrollAware {
  attachScroll(source: ScrollDirector | null): void;
}

/**
 * Builds a ScrollDirector from the page's `[data-anchor]` elements once it renders in the
 * browser, hands it to the scene when the scene is ready, and tears both down with the page.
 */
export function injectScrollDirector(scene: Signal<ScrollAware | null>, hold?: number): Signal<ScrollDirector | null> {
  const host = inject(ElementRef<HTMLElement>).nativeElement as HTMLElement;
  const director = signal<ScrollDirector | null>(null);

  afterNextRender(() => {
    const anchors = Array.from(host.querySelectorAll<HTMLElement>('[data-anchor]'));
    director.set(new ScrollDirector({ anchors, smooth: !prefersReducedMotion(), hold }));
  });

  effect(() => scene()?.attachScroll(director()));

  inject(DestroyRef).onDestroy(() => {
    scene()?.attachScroll(null);
    director()?.destroy();
  });

  return director.asReadonly();
}

/** Runs `callback` on every animation frame while the component lives, in the browser only. */
export function injectFrameLoop(callback: (time: number) => void): void {
  let handle = 0;
  let running = true;
  afterNextRender(() => {
    const loop = (time: number) => {
      if (!running) return;
      callback(time);
      handle = requestAnimationFrame(loop);
    };
    handle = requestAnimationFrame(loop);
  });
  inject(DestroyRef).onDestroy(() => {
    running = false;
    if (handle) cancelAnimationFrame(handle);
  });
}
