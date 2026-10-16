import { Injectable, isDevMode, signal } from '@angular/core';
import type { Timer } from 'three/webgpu';
import { AdaptiveDpr } from './adaptive-dpr';
import { detectQuality, forcedQuality, gpuTier, isTouchDevice, lowerQuality, prefersReducedMotion, readGpu } from './device';
import { Backend, EngineContext, Quality, WorldScene, WorldSceneFactory } from './world-scene';

export interface SceneHandle {
  /** Resolves with the scene once it renders, or null if it was cancelled or failed. */
  readonly ready: Promise<WorldScene | null>;
  destroy(): void;
}

const DPR_CAP: Record<Quality, number> = { high: 2, medium: 1.5, low: 1.25 };

/**
 * Owns the single WebGPU renderer and canvas shared by every world. Worlds mount and
 * unmount scenes; the renderer, its device and the frame loop survive navigation.
 */
@Injectable({ providedIn: 'root' })
export class Engine {
  readonly backend = signal<Backend | null>(null);
  /** True while a scene is on screen; the shell fades the canvas with it. */
  readonly visible = signal(false);
  /** Loading fraction of the scene being mounted, or null when idle. */
  readonly progress = signal<number | null>(null);
  readonly failed = signal(false);

  private canvas: HTMLCanvasElement | null = null;
  private boot: Promise<EngineContext> | null = null;
  private ctx: EngineContext | null = null;
  private active: WorldScene | null = null;
  private generation = 0;
  private width = 1;
  private height = 1;
  private dpr: AdaptiveDpr | null = null;
  private timer: Timer | null = null;

  attach(canvas: HTMLCanvasElement): void {
    this.canvas = canvas;
    if (isDevMode()) (window as unknown as { __pwEngine: Engine }).__pwEngine = this;
  }

  mount(factory: WorldSceneFactory): SceneHandle {
    const generation = ++this.generation;
    let cancelled = false;
    let world: WorldScene | null = null;
    const isCurrent = () => !cancelled && generation === this.generation;

    this.visible.set(false);
    this.failed.set(false);
    this.progress.set(0);

    const ready = (async (): Promise<WorldScene | null> => {
      let ctx: EngineContext;
      try {
        ctx = await this.start();
      } catch (error) {
        console.error('[engine] renderer could not start', error);
        if (isCurrent()) this.fail();
        return null;
      }
      if (!isCurrent()) return null;

      let created: WorldScene;
      try {
        created = await factory(ctx);
      } catch (error) {
        console.error('[engine] scene module failed to load', error);
        if (isCurrent()) this.fail();
        return null;
      }
      if (!isCurrent()) {
        created.dispose();
        return null;
      }
      world = created;
      try {
        await created.init((fraction) => {
          if (isCurrent()) this.progress.set(Math.min(0.95, fraction * 0.95));
        });
        if (!isCurrent()) {
          created.dispose();
          return null;
        }
        created.resize(this.width, this.height);
        this.prepareRenderer(created);
        await ctx.renderer.compileAsync(created.scene, created.camera);
      } catch (error) {
        console.error('[engine] scene failed', error);
        created.dispose();
        world = null;
        if (isCurrent()) this.fail();
        return null;
      }
      if (!isCurrent()) {
        created.dispose();
        return null;
      }

      this.activate(created);
      this.progress.set(null);
      requestAnimationFrame(() =>
        requestAnimationFrame(() => {
          if (isCurrent()) this.visible.set(true);
        }),
      );
      return created;
    })();

    return {
      ready,
      destroy: () => {
        cancelled = true;
        if (world && this.active === world) {
          this.active = null;
          this.visible.set(false);
          this.release(world);
        }
        if (generation === this.generation) this.progress.set(null);
      },
    };
  }

  private fail(): void {
    this.progress.set(null);
    this.failed.set(true);
  }

  /** Resets renderer-wide settings and lets the scene apply its own before pipelines compile. */
  private prepareRenderer(world: WorldScene): void {
    const renderer = this.ctx!.renderer;
    renderer.toneMapping = this.ctx!.THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1;
    world.activate?.();
  }

  private activate(world: WorldScene): void {
    const previous = this.active;
    if (previous) this.release(previous);
    this.active = world;
    this.dpr?.hold();
  }

  private release(world: WorldScene): void {
    world.dispose();
    if (isDevMode() && this.ctx) {
      const info = this.ctx.renderer.info.memory;
      console.debug(`[engine] released scene, ${info.geometries} geometries and ${info.textures} textures alive`);
    }
  }

  private start(): Promise<EngineContext> {
    if (!this.boot) this.boot = this.create();
    return this.boot;
  }

  private async create(): Promise<EngineContext> {
    const canvas = this.canvas;
    if (!canvas) throw new Error('Engine canvas is not attached');

    const THREE = await import('three/webgpu');
    const forceWebGL = new URLSearchParams(location.search).has('webgl');
    const renderer = new THREE.WebGPURenderer({
      canvas,
      antialias: true,
      forceWebGL,
      powerPreference: 'high-performance',
    } as ConstructorParameters<typeof THREE.WebGPURenderer>[0]);
    await renderer.init();

    const backend: Backend = (renderer.backend as { isWebGPUBackend?: boolean }).isWebGPUBackend
      ? 'webgpu'
      : 'webgl2';
    this.backend.set(backend);
    document.documentElement.dataset['backend'] = backend;
    // the device heuristic, capped by what the GPU turns out to be, unless the page forced a tier
    const quality = forcedQuality() ?? lowerQuality(detectQuality(), gpuTier(readGpu(renderer)));
    document.documentElement.dataset['quality'] = quality;

    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFShadowMap;

    const maxDpr = Math.min(window.devicePixelRatio || 1, DPR_CAP[quality]);
    this.dpr = new AdaptiveDpr(maxDpr, Math.min(maxDpr, quality === 'low' ? 0.75 : 1));
    renderer.setPixelRatio(this.dpr.current);
    this.measure(canvas);
    renderer.setSize(this.width, this.height, false);
    new ResizeObserver(() => this.onResize()).observe(canvas);

    this.timer = new THREE.Timer();
    this.timer.connect(document);

    this.ctx = {
      THREE,
      renderer,
      backend,
      quality,
      // live, so a scene that snaps between stops and a page that slides never disagree
      get reducedMotion() {
        return prefersReducedMotion();
      },
      touch: isTouchDevice(),
    };
    renderer.setAnimationLoop(this.tick);
    return this.ctx;
  }

  private measure(canvas: HTMLCanvasElement): void {
    this.width = Math.max(1, canvas.clientWidth);
    this.height = Math.max(1, canvas.clientHeight);
  }

  private onResize(): void {
    if (!this.canvas || !this.ctx) return;
    this.measure(this.canvas);
    this.ctx.renderer.setSize(this.width, this.height, false);
    this.active?.resize(this.width, this.height);
  }

  private readonly tick = (time: number): void => {
    const timer = this.timer;
    const ctx = this.ctx;
    if (!timer || !ctx) return;
    timer.update(time);
    const world = this.active;
    if (!world) return;
    const dt = Math.min(timer.getDelta(), 1 / 15);
    world.update(dt, timer.getElapsed());
    if (!world.render?.()) ctx.renderer.render(world.scene, world.camera);
    if (this.dpr?.sample(dt)) {
      ctx.renderer.setPixelRatio(this.dpr.current);
      ctx.renderer.setSize(this.width, this.height, false);
    }
  };
}
