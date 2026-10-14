import { inject, Injectable, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Lang, WorldDef, WorldId, worldById, worldPath } from '../worlds/world-registry';
import { fetchBuffer } from './assets/buffer-cache';
import { prefersReducedMotion } from './engine/device';
import { Engine } from './engine/engine.service';
import { Site } from './site.service';

const wait = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/** Moves between worlds behind a veil so the old scene never flashes during the swap. */
@Injectable({ providedIn: 'root' })
export class Transitions {
  private readonly router = inject(Router);
  private readonly site = inject(Site);
  private readonly engine = inject(Engine);
  private readonly prefetched = new Set<WorldId>();
  private busy = false;

  /** Destination shown on the veil while it covers the page, or null when hidden. */
  readonly veil = signal<WorldId | 'hub' | null>(null);

  async go(world: WorldId | null, lang: Lang = this.site.lang()): Promise<void> {
    const url = worldPath(lang, world);
    if (this.busy || this.router.url === url) return;

    if (world === this.site.world()) {
      await this.router.navigateByUrl(url);
      return;
    }

    this.busy = true;
    if (world) this.prefetch(worldById(world));
    this.veil.set(world ?? 'hub');
    this.engine.visible.set(false);
    await wait(prefersReducedMotion() ? 120 : 560);
    try {
      await this.router.navigateByUrl(url);
    } finally {
      requestAnimationFrame(() =>
        requestAnimationFrame(() => {
          this.veil.set(null);
          this.busy = false;
        }),
      );
    }
  }

  /** Loads the page chunk and warms the HTTP cache with the world's models. */
  prefetch(world: WorldDef): void {
    if (this.prefetched.has(world.id)) return;
    this.prefetched.add(world.id);
    void world.page();
    for (const asset of world.assets) {
      fetchBuffer(asset).catch(() => this.prefetched.delete(world.id));
    }
  }
}
