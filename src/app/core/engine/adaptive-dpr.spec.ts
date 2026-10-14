import { AdaptiveDpr } from './adaptive-dpr';

function run(dpr: AdaptiveDpr, seconds: number, frameTime: number): void {
  for (let t = 0; t < seconds; t += frameTime) dpr.sample(frameTime);
}

describe('AdaptiveDpr', () => {
  it('ignores slow frames while it is holding, for example during shader compilation', () => {
    const dpr = new AdaptiveDpr(2, 1);
    run(dpr, 2, 1 / 20);
    expect(dpr.current).toBe(2);
  });

  it('steps down when frames stay slow and never goes below the minimum', () => {
    const dpr = new AdaptiveDpr(2, 1);
    run(dpr, 30, 1 / 20);
    expect(dpr.current).toBe(1);
  });

  it('climbs back after a long stretch of fast frames', () => {
    const dpr = new AdaptiveDpr(2, 1);
    run(dpr, 10, 1 / 20);
    const lowered = dpr.current;
    run(dpr, 90, 1 / 120);
    expect(lowered).toBeLessThan(2);
    expect(dpr.current).toBeGreaterThan(lowered);
  });
});
