import { CatmullRomCurve3, MathUtils, PerspectiveCamera, Vector3 } from 'three/webgpu';

export interface CameraKey {
  readonly position: Vector3;
  readonly target: Vector3;
  readonly fov: number;
}

/**
 * Moves a camera through keyframes. `update(k)` takes the continuous keyframe position from the
 * scroll director; curves run through every key so k = 2 lands exactly on the third key.
 */
export class KeyframeRig {
  private readonly positions: CatmullRomCurve3;
  private readonly targets: CatmullRomCurve3;
  private readonly fovs: number[];
  private readonly sway = new Vector3();
  private readonly swayTarget = new Vector3();
  private readonly right = new Vector3();
  private readonly up = new Vector3();
  private readonly forward = new Vector3();
  private readonly lookAt = new Vector3();
  private smoothed = 0;
  private initialised = false;
  private fovScale = 1;
  readonly focus = new Vector3();

  /**
   * On portrait screens the text sits at the bottom, so the view widens and the scene moves
   * up into the free top half.
   */
  fitViewport(width: number, height: number): void {
    const portrait = width < height;
    this.fovScale = portrait ? 1.35 : 1;
    if (portrait) this.camera.setViewOffset(width, height, 0, height * 0.16, width, height);
    else this.camera.clearViewOffset();
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
  }

  constructor(
    private readonly camera: PerspectiveCamera,
    keys: readonly CameraKey[],
    private readonly options: { damping?: number; swayAmount?: number } = {},
  ) {
    this.positions = new CatmullRomCurve3(keys.map((k) => k.position.clone()), false, 'centripetal');
    this.targets = new CatmullRomCurve3(keys.map((k) => k.target.clone()), false, 'centripetal');
    this.fovs = keys.map((k) => k.fov);
  }

  get count(): number {
    return this.fovs.length;
  }

  /** Points along the camera path, for example to keep it clear of props. */
  samplePath(samples: number): Vector3[] {
    return Array.from({ length: samples }, (_, i) => this.positions.getPoint(i / (samples - 1)));
  }

  /** Smoothed keyframe position the camera is at right now. */
  get position(): number {
    return this.smoothed;
  }

  /**
   * @param k target keyframe position, 0 to count - 1
   * @param snap jump straight to k (reduced motion, first frame)
   * @param pointer pointer position in -1..1 for a small parallax, or null
   */
  update(k: number, dt: number, snap: boolean, pointer: { x: number; y: number } | null): void {
    const last = this.fovs.length - 1;
    const goal = MathUtils.clamp(k, 0, last);
    if (snap || !this.initialised) {
      this.smoothed = goal;
      this.initialised = true;
    } else {
      this.smoothed += (goal - this.smoothed) * (1 - Math.exp(-dt * (this.options.damping ?? 3)));
    }

    const u = last === 0 ? 0 : this.smoothed / last;
    this.positions.getPoint(u, this.camera.position);
    this.targets.getPoint(u, this.focus);

    const i = Math.min(last - 1, Math.floor(this.smoothed));
    const f = this.smoothed - i;
    const fov = (last === 0 ? this.fovs[0] : MathUtils.lerp(this.fovs[i], this.fovs[i + 1], f * f * (3 - 2 * f))) * this.fovScale;
    if (Math.abs(this.camera.fov - fov) > 1e-3) {
      this.camera.fov = fov;
      this.camera.updateProjectionMatrix();
    }

    const amount = this.options.swayAmount ?? 0;
    this.swayTarget.set(pointer?.x ?? 0, pointer?.y ?? 0, 0).multiplyScalar(amount);
    this.sway.lerp(this.swayTarget, snap ? 1 : 1 - Math.exp(-dt * 2.2));
    this.forward.subVectors(this.focus, this.camera.position).normalize();
    this.right.crossVectors(this.forward, this.camera.up).normalize();
    this.up.crossVectors(this.right, this.forward).normalize();
    this.camera.position.addScaledVector(this.right, this.sway.x).addScaledVector(this.up, this.sway.y * 0.6);
    this.lookAt.copy(this.focus);
    this.camera.lookAt(this.lookAt);
  }
}

/** Pointer position normalised to -1..1, or null on touch devices. */
export class PointerTracker {
  readonly value = { x: 0, y: 0 };
  private readonly onMove = (event: PointerEvent) => {
    if (event.pointerType !== 'mouse') return;
    this.value.x = (event.clientX / window.innerWidth) * 2 - 1;
    this.value.y = -((event.clientY / window.innerHeight) * 2 - 1);
  };

  constructor() {
    window.addEventListener('pointermove', this.onMove, { passive: true });
  }

  dispose(): void {
    window.removeEventListener('pointermove', this.onMove);
  }
}
