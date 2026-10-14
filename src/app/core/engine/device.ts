import { Quality } from './world-scene';

interface NavigatorWithMemory extends Navigator {
  readonly deviceMemory?: number;
}

export function prefersReducedMotion(): boolean {
  return typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
}

export function isTouchDevice(): boolean {
  return typeof matchMedia === 'function' && matchMedia('(pointer: coarse)').matches;
}

/** Rough device tier; `?quality=low|medium|high` overrides it. */
export function detectQuality(): Quality {
  const forced = new URLSearchParams(location.search).get('quality');
  if (forced === 'low' || forced === 'medium' || forced === 'high') return forced;
  const nav = navigator as NavigatorWithMemory;
  const memory = nav.deviceMemory ?? 8;
  const cores = nav.hardwareConcurrency ?? 8;
  const touch = isTouchDevice();
  if (touch && (memory <= 4 || cores <= 6)) return 'low';
  if (touch || memory <= 4 || cores <= 4) return 'medium';
  return 'high';
}
