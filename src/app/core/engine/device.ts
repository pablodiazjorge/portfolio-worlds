import { Quality } from './world-scene';

interface NavigatorWithMemory extends Navigator {
  readonly deviceMemory?: number;
}

/**
 * Whether the worlds should hold still. The motion is the content here, so by the owner's
 * decision it stays on whatever the system's reduced-motion setting says. Everything that
 * would honour the setting (the director's `smooth`, the scenes cutting to a stop with the
 * page) is in place behind this one switch should that decision change.
 */
export function prefersReducedMotion(): boolean {
  return false;
}

export function isTouchDevice(): boolean {
  return typeof matchMedia === 'function' && matchMedia('(pointer: coarse)').matches;
}

/** The tier the page asked for with `?quality=low|medium|high`, if any. */
export function forcedQuality(): Quality | null {
  const forced = new URLSearchParams(location.search).get('quality');
  return forced === 'low' || forced === 'medium' || forced === 'high' ? forced : null;
}

/** Rough device tier from memory, cores and touch; `?quality=low|medium|high` overrides it. */
export function detectQuality(): Quality {
  const forced = forcedQuality();
  if (forced) return forced;
  const nav = navigator as NavigatorWithMemory;
  const memory = nav.deviceMemory ?? 8;
  const cores = nav.hardwareConcurrency ?? 8;
  const touch = isTouchDevice();
  if (touch && (memory <= 4 || cores <= 6)) return 'low';
  if (touch || memory <= 4 || cores <= 4) return 'medium';
  return 'high';
}

/** What the renderer learnt about the GPU: the WebGPU adapter's info, or WebGL's unmasked renderer string. */
export interface GpuInfo {
  readonly vendor?: string;
  readonly architecture?: string;
  readonly description?: string;
  readonly renderer?: string;
  readonly fallback?: boolean;
}

const RANK: Record<Quality, number> = { low: 0, medium: 1, high: 2 };

/** The lower of two tiers; a missing second opinion changes nothing. */
export function lowerQuality(a: Quality, b: Quality | null): Quality {
  return b && RANK[b] < RANK[a] ? b : a;
}

/**
 * A tier for the GPU alone, or null when it says nothing. Memory and cores flatter a laptop with an
 * integrated GPU, which is where the museum's mirror floor and shadows start to lag, so integrated
 * parts cap the tier at medium and software renderers at low.
 */
export function gpuTier(info: GpuInfo | null): Quality | null {
  if (!info) return null;
  if (info.fallback) return 'low';
  const text = [info.vendor, info.architecture, info.description, info.renderer].filter(Boolean).join(' ').toLowerCase();
  if (!text) return null;
  if (/swiftshader|llvmpipe|softpipe|software|basic render|microsoft basic/.test(text)) return 'low';
  if (/intel/.test(text)) return 'medium';
  if (/qualcomm|adreno|mali|imagination|powervr|\barm\b/.test(text)) return 'medium';
  if (/amd|radeon|ati\b/.test(text)) return /gcn|vega|radeon\(tm\) graphics|radeon graphics|ryzen|raphael|rembrandt|phoenix|cezanne|renoir|picasso|raven/.test(text) ? 'medium' : 'high';
  if (/nvidia|geforce|rtx|quadro|apple/.test(text)) return 'high';
  return null;
}

/** Reads the GPU through the renderer's backend: the WebGPU device's adapter info where the browser gives it, else WebGL's renderer string. */
export function readGpu(renderer: { backend?: unknown }): GpuInfo | null {
  const backend = renderer.backend as { device?: { adapterInfo?: Record<string, unknown> }; gl?: WebGL2RenderingContext | null } | undefined;
  const info = backend?.device?.adapterInfo;
  if (info) {
    return {
      vendor: String(info['vendor'] ?? ''),
      architecture: String(info['architecture'] ?? ''),
      description: String(info['description'] ?? ''),
      fallback: Boolean(info['isFallbackAdapter']),
    };
  }
  const gl = backend?.gl;
  if (gl) {
    const ext = gl.getExtension('WEBGL_debug_renderer_info') as { UNMASKED_RENDERER_WEBGL: number } | null;
    const name = ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
    return { renderer: String(name ?? '') };
  }
  return null;
}
