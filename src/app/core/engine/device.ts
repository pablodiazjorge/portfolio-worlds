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
