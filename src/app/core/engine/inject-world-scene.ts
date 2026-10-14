import { afterNextRender, DestroyRef, inject, Signal, signal } from '@angular/core';
import { Engine, SceneHandle } from './engine.service';
import { WorldScene, WorldSceneFactory } from './world-scene';

/**
 * Mounts a world's scene once the page is in the browser and frees it when the page is
 * destroyed. Returns the scene once it is on screen, or null before that.
 */
export function injectWorldScene<T extends WorldScene>(factory: WorldSceneFactory<T>): Signal<T | null> {
  const engine = inject(Engine);
  const scene = signal<T | null>(null);
  let handle: SceneHandle | null = null;
  let destroyed = false;

  afterNextRender(() => {
    if (destroyed) return;
    handle = engine.mount(factory);
    void handle.ready.then((ready) => {
      if (!destroyed) scene.set(ready as T | null);
    });
  });

  inject(DestroyRef).onDestroy(() => {
    destroyed = true;
    handle?.destroy();
    scene.set(null);
  });

  return scene.asReadonly();
}
