/**
 * Lowers the pixel ratio when frames run slow and raises it back when they recover.
 * Frame time is averaged over one second windows; changes are spaced out so the ratio
 * does not oscillate.
 */
export class AdaptiveDpr {
  private elapsed = 0;
  private frames = 0;
  private cooldown = 2.5;
  private goodTime = 0;
  private ceiling: number;
  current: number;

  constructor(
    private readonly max: number,
    private readonly min: number,
  ) {
    this.current = max;
    this.ceiling = max;
  }

  /** Ignore the next seconds, for example while a new scene compiles its pipelines. */
  hold(seconds = 2.5): void {
    this.cooldown = Math.max(this.cooldown, seconds);
    this.elapsed = 0;
    this.frames = 0;
  }

  /** Feeds one frame time in seconds. Returns true when `current` changed. */
  sample(dt: number): boolean {
    this.cooldown -= dt;
    this.elapsed += dt;
    this.frames++;
    if (this.elapsed < 1) return false;

    const average = this.elapsed / this.frames;
    this.elapsed = 0;
    this.frames = 0;
    if (this.cooldown > 0) return false;

    if (average > 1 / 45 && this.current > this.min) {
      this.current = Math.max(this.min, this.current - 0.25);
      this.ceiling = this.current;
      this.goodTime = 0;
      this.cooldown = 2;
      return true;
    }

    if (average < 1 / 57) {
      this.goodTime += 1;
      if (this.goodTime >= 20 && this.ceiling < this.max) {
        this.ceiling = Math.min(this.max, this.ceiling + 0.25);
        this.goodTime = 0;
      }
      if (this.current < this.ceiling && this.goodTime >= 4) {
        this.current = Math.min(this.ceiling, this.current + 0.25);
        this.cooldown = 4;
        return true;
      }
    } else {
      this.goodTime = 0;
    }
    return false;
  }
}
