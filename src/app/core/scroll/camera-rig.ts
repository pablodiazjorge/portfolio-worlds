import { CatmullRomCurve3, MathUtils, PerspectiveCamera, Vector3 } from 'three/webgpu';

export interface CameraKey {
  readonly position: Vector3;
  readonly target: Vector3;
  readonly fov: number;
  /**
   * What to look at on portrait screens, where the text sits below the scene instead of beside
   * it, so a subject pushed aside for a side panel goes back to the centre. Steering rigs only.
   */
  readonly subject?: Vector3;
}

export interface RigOptions {
  damping?: number;
  swayAmount?: number;
  /**
   * Turns the camera between keys by blending its heading and pitch instead of sliding the
   * point it looks at. Long moves then read as a steady glide: the camera never swings over
   * a target that passes underneath it.
   */
  steer?: boolean;
  /** How high the camera rises in the middle of each move, like a crane; 0 keeps the curve. */
  arc?: number;
  /**
   * Keeps the camera and the first stretch of its view above a terrain. `solid` adds what the
   * camera itself must not fly through (buildings, props) but may look past.
   */
  ground?: {
    at: (x: number, z: number) => number;
    clearance: number;
    sight?: number;
    solid?: (x: number, z: number) => number;
  };
}

/** Lift samples per key segment. */
const SAMPLES = 48;

/**
 * Moves a camera through keyframes. `update(k)` takes the continuous keyframe position from the
 * scroll director; curves run through every key so k = 2 lands exactly on the third key.
 */
export class KeyframeRig {
  private readonly positions: CatmullRomCurve3;
  private readonly targets: CatmullRomCurve3;
  private readonly fovs: number[];
  private readonly aim: Aim | null = null;
  private readonly aimNarrow: Aim | null = null;
  private narrow = false;
  private readonly lift: Float32Array | null = null;
  private readonly tilt: Float32Array | null = null;
  private readonly sway = new Vector3();
  private readonly swayTarget = new Vector3();
  private readonly right = new Vector3();
  private readonly up = new Vector3();
  private readonly forward = new Vector3();
  private readonly probe = new Vector3();
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
    this.narrow = portrait;
    this.fovScale = portrait ? 1.35 : 1;
    if (portrait) this.camera.setViewOffset(width, height, 0, height * 0.16, width, height);
    else this.camera.clearViewOffset();
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
  }

  constructor(
    private readonly camera: PerspectiveCamera,
    keys: readonly CameraKey[],
    private readonly options: RigOptions = {},
  ) {
    this.positions = new CatmullRomCurve3(keys.map((k) => k.position.clone()), false, 'centripetal');
    this.targets = new CatmullRomCurve3(keys.map((k) => k.target.clone()), false, 'centripetal');
    this.fovs = keys.map((k) => k.fov);
    if (options.steer) {
      this.aim = new Aim(keys, (key) => key.target);
      if (keys.some((key) => key.subject)) this.aimNarrow = new Aim(keys, (key) => key.subject ?? key.target);
    }
    if (options.ground) {
      this.lift = this.planLift(options.ground);
      if (options.steer) this.tilt = this.planTilt(options.ground);
    }
  }

  get count(): number {
    return this.fovs.length;
  }

  /** Points along the camera path, for example to keep it clear of props. */
  samplePath(samples: number): Vector3[] {
    const last = this.fovs.length - 1;
    return Array.from({ length: samples }, (_, i) => {
      const k = (i / (samples - 1)) * last;
      const point = this.base(k, new Vector3());
      point.y += this.arcAt(k) + this.liftAt(k);
      return point;
    });
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

    const at = this.smoothed;
    const camera = this.camera;
    const arc = this.arcAt(at);
    const lift = this.liftAt(at);
    this.base(at, camera.position);
    camera.position.y += arc + lift;
    if (this.options.steer) {
      this.heading(at, arc, lift, this.forward);
      this.focus.copy(camera.position).addScaledVector(this.forward, Math.exp(this.currentAim().reach.at(at)));
    } else {
      this.targets.getPoint(last === 0 ? 0 : at / last, this.focus);
    }

    const i = Math.min(last - 1, Math.floor(at));
    const f = at - i;
    const fov = (last === 0 ? this.fovs[0] : MathUtils.lerp(this.fovs[i], this.fovs[i + 1], f * f * (3 - 2 * f))) * this.fovScale;
    if (Math.abs(camera.fov - fov) > 1e-3) {
      camera.fov = fov;
      camera.updateProjectionMatrix();
    }

    const amount = this.options.swayAmount ?? 0;
    this.swayTarget.set(pointer?.x ?? 0, pointer?.y ?? 0, 0).multiplyScalar(amount);
    this.sway.lerp(this.swayTarget, snap ? 1 : 1 - Math.exp(-dt * 2.2));
    this.forward.subVectors(this.focus, camera.position).normalize();
    this.right.crossVectors(this.forward, camera.up).normalize();
    this.up.crossVectors(this.right, this.forward).normalize();
    camera.position.addScaledVector(this.right, this.sway.x).addScaledVector(this.up, this.sway.y * 0.6);

    // the planned lift already clears the terrain; this only catches the pointer parallax
    const ground = this.options.ground;
    if (ground) camera.position.y = Math.max(camera.position.y, this.solidAt(ground, camera.position.x, camera.position.z) + ground.clearance * 0.8);
    camera.lookAt(this.focus);
  }

  /** Camera position on the key curve, before any lift. */
  private base(k: number, out: Vector3): Vector3 {
    const last = this.fovs.length - 1;
    return this.positions.getPoint(last === 0 ? 0 : k / last, out);
  }

  /** Crane lift, zero with zero slope on every key so passing a stop never kinks. */
  private arcAt(k: number): number {
    const amount = this.options.arc ?? 0;
    if (!amount) return 0;
    const s = Math.sin(Math.PI * (k - Math.floor(k)));
    return amount * s * s;
  }

  /**
   * View direction while steering. The crane tilts it down a little to keep the ground in
   * frame; on a climb the planned tilt raises it so the camera looks up the slope ahead; and
   * near a stop, where the terrain may have lifted the camera, it looks down at the subject.
   */
  private heading(k: number, arc: number, lift: number, out: Vector3): Vector3 {
    const aim = this.currentAim();
    const yaw = aim.yaw.at(k);
    const near = Math.cos(Math.PI * (k - Math.floor(k)));
    const settle = near * near * Math.atan2(lift, Math.exp(aim.reach.at(k)));
    const pitch = aim.pitch.at(k) - Math.atan2(arc, 30) + sampleTable(this.tilt, k) - settle;
    return out.set(Math.sin(yaw) * Math.cos(pitch), Math.sin(pitch), Math.cos(yaw) * Math.cos(pitch));
  }

  /** The portrait aim when there is one and the screen is narrow; plans always use the wide aim. */
  private currentAim(): Aim {
    return (this.narrow && this.aimNarrow) || this.aim!;
  }

  private liftAt(k: number): number {
    return sampleTable(this.lift, k);
  }

  private solidAt(ground: NonNullable<RigOptions['ground']>, x: number, z: number): number {
    const surface = ground.at(x, z);
    return ground.solid ? Math.max(surface, ground.solid(x, z)) : surface;
  }

  /**
   * Between stops, how far to raise the view so its centre clears the ground for a good
   * distance ahead: on a steep climb the camera would otherwise stare into the slope. Zero on
   * every key, so the framed stops stay exactly as composed.
   */
  private planTilt(ground: NonNullable<RigOptions['ground']>): Float32Array {
    const last = this.fovs.length - 1;
    const n = last * SAMPLES + 1;
    const wanted = new Float32Array(n);
    const point = new Vector3();
    const sight = (ground.sight ?? 1) * 2;
    for (let i = 0; i < n; i++) {
      const k = i / SAMPLES;
      const arc = this.arcAt(k);
      this.base(k, point);
      point.y += arc + this.liftAt(k);
      const yaw = this.aim!.yaw.at(k);
      const pitch = this.aim!.pitch.at(k) - Math.atan2(arc, 30);
      let angle = -Infinity;
      for (let d = 8; d <= 50; d += 3) {
        const height = ground.at(point.x + Math.sin(yaw) * d, point.z + Math.cos(yaw) * d) + sight - point.y;
        angle = Math.max(angle, Math.atan2(height, d));
      }
      wanted[i] = MathUtils.clamp(angle - pitch, 0, 0.45);
    }
    // blur first, then fade to zero on the keys so the stops keep their exact framing
    const tilt = boxBlur(boxBlur(wanted, Math.round(SAMPLES * 0.18)), Math.round(SAMPLES * 0.18));
    for (let i = 0; i < n; i++) {
      const s = Math.sin(Math.PI * ((i / SAMPLES) % 1));
      tilt[i] *= s * s;
    }
    return tilt;
  }

  /**
   * Walks the whole path once and works out how much higher the camera has to fly so neither
   * the camera nor the near part of what it looks at goes into the ground. The result is
   * spread and blurred so the camera starts rising well before a ridge instead of popping.
   */
  private planLift(ground: NonNullable<RigOptions['ground']>): Float32Array {
    const last = this.fovs.length - 1;
    const n = last * SAMPLES + 1;
    const need = new Float32Array(n);
    const point = new Vector3();
    const dir = new Vector3();
    const sight = ground.sight ?? 1;
    for (let i = 0; i < n; i++) {
      const k = i / SAMPLES;
      const arc = this.arcAt(k);
      this.base(k, point);
      point.y += arc;
      let reach: number;
      if (this.options.steer) {
        this.heading(k, arc, 0, dir);
        reach = Math.exp(this.aim!.reach.at(k));
      } else {
        this.targets.getPoint(last === 0 ? 0 : k / last, dir);
        dir.sub(point);
        reach = dir.length();
        dir.normalize();
      }
      const below = this.solidAt(ground, point.x, point.z);
      let required = below + ground.clearance - point.y;
      // Only the stretch of the view that would still be above flat ground: looking down, the
      // ground is meant to appear; a hill that cuts the view short is what needs the lift.
      const expected = Math.max(0, point.y - below) / Math.max(0.05, -dir.y);
      const span = Math.min(reach * 0.7, 30, expected * 0.6);
      for (let s = 1.5; s <= span; s += 1.5) {
        this.probe.copy(point).addScaledVector(dir, s);
        required = Math.max(required, ground.at(this.probe.x, this.probe.z) + sight - this.probe.y);
      }
      need[i] = Math.max(0, required);
    }
    // Each obstacle raises a smooth bump that is back to zero within 0.4 of a key, so a ridge
    // between two stops lifts the move without leaking into the framed stops beside it.
    return boxBlur(dilate(need, Math.round(SAMPLES * 0.4)), Math.round(SAMPLES * 0.05));
  }
}

/** Heading, pitch and log distance to what each key looks at, as smooth curves over k. */
class Aim {
  readonly yaw: Monotone;
  readonly pitch: Monotone;
  readonly reach: Monotone;

  constructor(keys: readonly CameraKey[], pick: (key: CameraKey) => Vector3) {
    const yaws: number[] = [];
    const pitches: number[] = [];
    const reaches: number[] = [];
    for (const key of keys) {
      const look = pick(key).clone().sub(key.position);
      const length = Math.max(1e-3, look.length());
      let yaw = Math.atan2(look.x, look.z);
      // unwrap so each turn takes the short way round
      if (yaws.length) yaw = yaws[yaws.length - 1] + MathUtils.euclideanModulo(yaw - yaws[yaws.length - 1] + Math.PI, Math.PI * 2) - Math.PI;
      yaws.push(yaw);
      pitches.push(Math.asin(MathUtils.clamp(look.y / length, -1, 1)));
      reaches.push(Math.log(length));
    }
    this.yaw = new Monotone(yaws);
    this.pitch = new Monotone(pitches);
    this.reach = new Monotone(reaches);
  }
}

/** Monotone cubic through evenly spaced values: smooth, and never overshoots between keys. */
class Monotone {
  private readonly slopes: number[];

  constructor(private readonly values: number[]) {
    const n = values.length;
    const d = values.slice(0, -1).map((v, i) => values[i + 1] - v);
    const m = values.map((_, i) => {
      if (n < 2) return 0;
      if (i === 0) return d[0];
      if (i === n - 1) return d[n - 2];
      return d[i - 1] * d[i] <= 0 ? 0 : (d[i - 1] + d[i]) / 2;
    });
    for (let i = 0; i < n - 1; i++) {
      if (d[i] === 0) {
        m[i] = 0;
        m[i + 1] = 0;
        continue;
      }
      const a = m[i] / d[i];
      const b = m[i + 1] / d[i];
      const s = a * a + b * b;
      if (s > 9) {
        const t = 3 / Math.sqrt(s);
        m[i] = t * a * d[i];
        m[i + 1] = t * b * d[i];
      }
    }
    this.slopes = m;
  }

  at(x: number): number {
    const v = this.values;
    if (v.length < 2) return v[0] ?? 0;
    const i = Math.min(v.length - 2, Math.max(0, Math.floor(x)));
    const t = MathUtils.clamp(x - i, 0, 1);
    const t2 = t * t;
    const t3 = t2 * t;
    return (
      (2 * t3 - 3 * t2 + 1) * v[i] +
      (t3 - 2 * t2 + t) * this.slopes[i] +
      (-2 * t3 + 3 * t2) * v[i + 1] +
      (t3 - t2) * this.slopes[i + 1]
    );
  }
}

/** Linear lookup in a per-segment table, or 0 without one. */
function sampleTable(table: Float32Array | null, k: number): number {
  if (!table) return 0;
  const x = MathUtils.clamp(k * SAMPLES, 0, table.length - 1);
  const i = Math.min(table.length - 2, Math.floor(x));
  return MathUtils.lerp(table[i], table[i + 1], x - i);
}

/** Smallest smooth envelope over the values: a cosine bump of the given radius under each one. */
function dilate(values: Float32Array, radius: number): Float32Array {
  const out = new Float32Array(values.length);
  for (let j = 0; j < values.length; j++) {
    const v = values[j];
    if (v <= 0) continue;
    for (let i = Math.max(0, j - radius); i <= Math.min(values.length - 1, j + radius); i++) {
      const c = Math.cos((Math.PI / 2) * (Math.abs(i - j) / radius));
      out[i] = Math.max(out[i], v * c * c);
    }
  }
  return out;
}

function boxBlur(values: Float32Array, radius: number): Float32Array {
  const out = new Float32Array(values.length);
  for (let i = 0; i < values.length; i++) {
    let sum = 0;
    let count = 0;
    for (let j = Math.max(0, i - radius); j <= Math.min(values.length - 1, i + radius); j++) {
      sum += values[j];
      count++;
    }
    out[i] = sum / count;
  }
  return out;
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
