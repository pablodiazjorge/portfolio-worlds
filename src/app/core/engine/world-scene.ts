import type { PerspectiveCamera, Scene, WebGPURenderer } from 'three/webgpu';

export type ThreeModule = typeof import('three/webgpu');
export type Backend = 'webgpu' | 'webgl2';
export type Quality = 'high' | 'medium' | 'low';

export interface EngineContext {
  readonly THREE: ThreeModule;
  readonly renderer: WebGPURenderer;
  readonly backend: Backend;
  readonly quality: Quality;
  readonly reducedMotion: boolean;
  readonly touch: boolean;
}

/**
 * One world's 3D content. The engine owns the renderer and the frame loop;
 * a scene only builds its graph, advances it each frame and frees what it created.
 */
export interface WorldScene {
  readonly scene: Scene;
  readonly camera: PerspectiveCamera;
  /** Loads assets and builds the graph. `onProgress` receives a fraction between 0 and 1. */
  init(onProgress: (fraction: number) => void): Promise<void>;
  /** Called right before the scene goes on screen, after the engine reset renderer settings. */
  activate?(): void;
  update(dt: number, elapsed: number): void;
  resize(width: number, height: number): void;
  /** Returns true when the scene rendered the frame itself, for example through post-processing. */
  render?(): boolean;
  dispose(): void;
}

export type WorldSceneFactory<T extends WorldScene = WorldScene> = (ctx: EngineContext) => T | Promise<T>;
