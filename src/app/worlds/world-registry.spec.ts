import { WORLDS, worldPath } from './world-registry';

describe('worldPath', () => {
  it('puts English at the root and Spanish under /es', () => {
    expect(worldPath('en', null)).toBe('/');
    expect(worldPath('es', null)).toBe('/es');
    expect(worldPath('en', 'atlas')).toBe('/atlas');
    expect(worldPath('es', 'atrium')).toBe('/es/atrium');
  });

  it('gives every world a unique shortcut from 1 to 5', () => {
    expect(WORLDS.map((w) => w.key)).toEqual(['1', '2', '3', '4', '5']);
    expect(new Set(WORLDS.map((w) => w.id)).size).toBe(WORLDS.length);
  });
});
