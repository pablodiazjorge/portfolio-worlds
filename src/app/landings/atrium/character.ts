import * as THREE from 'three/webgpu';
import type { GLTF } from 'three/addons/loaders/GLTFLoader.js';

/** Axis-aligned obstacle on the floor plane. Walls are full height, so XZ is enough. */
export interface FloorBox {
  minX: number;
  maxX: number;
  minZ: number;
  maxZ: number;
}

export interface MoveInput {
  /** Desired direction on the floor in world space, length up to 1. */
  x: number;
  z: number;
  run: boolean;
}

const WALK_SPEED = 1.4;
const RUN_SPEED = 4.6;
const RADIUS = 0.42;
const HEIGHT = 1.65;
/** The visitor model stands this tall to the top of its head before scaling (the aerial sticks up further). */
const MODEL_HEIGHT = 1.7;
/** Metres one cycle of each gait covers at the model's own scale: the clips plant the feet, so these are exact. */
const STRIDE_WALK = 1.4 * 0.75;
const STRIDE_RUN = 4.6 * 0.583;
const TURN_RATE = 10;

const smoothstep = (x: number, a: number, b: number) => {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
};

const lerpAngle = (from: number, to: number, t: number) => {
  let delta = (to - from) % (Math.PI * 2);
  if (delta > Math.PI) delta -= Math.PI * 2;
  if (delta < -Math.PI) delta += Math.PI * 2;
  return from + delta * t;
};

/** The robot visitor: movement, collisions, routes and animation blending. */
export class Character {
  readonly root = new THREE.Group();
  readonly velocity = new THREE.Vector3();
  heading = Math.PI;
  /** The body leans into turns and accelerations through this node between the root and the model. */
  private readonly lean = new THREE.Group();
  private readonly modelScale: number;
  private moveHeading = Math.PI;
  private speedValue = 0;
  private phase = 0;
  private roll = 0;
  private pitch = 0;

  private readonly mixer: THREE.AnimationMixer;
  private readonly actions = new Map<string, THREE.AnimationAction>();
  private gesture: THREE.AnimationAction | null = null;
  private route: THREE.Vector3[] = [];
  private routeRun = false;
  private onArrive: (() => void) | null = null;
  private stuckTime = 0;
  private readonly last = new THREE.Vector3();

  constructor(
    gltf: GLTF,
    private readonly obstacles: readonly FloorBox[],
  ) {
    const model = gltf.scene;
    const scale = HEIGHT / MODEL_HEIGHT;
    this.modelScale = scale;
    model.scale.setScalar(scale);
    model.traverse((o) => {
      const mesh = o as THREE.Mesh;
      if (mesh.isMesh) {
        mesh.castShadow = true;
        mesh.receiveShadow = true;
        mesh.frustumCulled = false;
      }
    });
    this.lean.add(model);
    this.root.add(this.lean);

    this.mixer = new THREE.AnimationMixer(model);
    for (const clip of gltf.animations) {
      const action = this.mixer.clipAction(clip);
      this.actions.set(clip.name, action);
    }
    for (const name of ['Idle', 'Walking', 'Running']) {
      const action = this.actions.get(name);
      if (!action) continue;
      action.enabled = true;
      action.setEffectiveWeight(name === 'Idle' ? 1 : 0);
      action.play();
    }
    // the two gaits share one phase that this class advances by hand, so their legs never cross-fade out of step
    for (const name of ['Walking', 'Running']) this.actions.get(name)?.setEffectiveTimeScale(0);
    this.mixer.addEventListener('finished', (event) => {
      const action = (event as unknown as { action: THREE.AnimationAction }).action;
      if (action === this.gesture) {
        action.fadeOut(0.35);
        this.gesture = null;
      }
    });
  }

  get position(): THREE.Vector3 {
    return this.root.position;
  }

  get speed(): number {
    return Math.hypot(this.velocity.x, this.velocity.z);
  }

  get walking(): boolean {
    return this.route.length > 0;
  }

  place(x: number, z: number, heading: number): void {
    this.root.position.set(x, 0, z);
    this.heading = heading;
    this.moveHeading = heading;
    this.root.rotation.y = heading;
    this.velocity.set(0, 0, 0);
    this.speedValue = 0;
  }

  /** Walks through the given points; manual input cancels the route. */
  follow(points: THREE.Vector3[], run: boolean, onArrive: (() => void) | null = null): void {
    this.route = points.map((p) => p.clone().setY(0));
    this.routeRun = run;
    this.onArrive = onArrive;
    this.stuckTime = 0;
  }

  cancelRoute(): void {
    this.route = [];
    this.onArrive = null;
  }

  /** Plays a one-off animation such as Wave or ThumbsUp over the locomotion. */
  play(name: string): void {
    const action = this.actions.get(name);
    if (!action || this.gesture === action) return;
    this.gesture?.fadeOut(0.2);
    action.reset();
    action.setLoop(THREE.LoopOnce, 1);
    action.clampWhenFinished = true;
    action.setEffectiveWeight(1);
    action.fadeIn(0.25).play();
    this.gesture = action;
  }

  turnTowards(target: THREE.Vector3): void {
    this.targetHeading = Math.atan2(target.x - this.position.x, target.z - this.position.z);
  }

  private targetHeading: number | null = null;
  private seated = false;

  get isSeated(): boolean {
    return this.seated;
  }

  /** Sits on a seat point facing `heading`: the locomotion rests and the Sitting clip takes over. */
  sit(x: number, z: number, heading: number): void {
    this.cancelRoute();
    this.gesture?.fadeOut(0.2);
    this.gesture = null;
    this.place(x, z, heading);
    this.targetHeading = null;
    this.lean.rotation.set(0, 0, 0);
    this.seated = true;
    const sitting = this.actions.get('Sitting');
    if (sitting) {
      sitting.reset();
      sitting.setLoop(THREE.LoopRepeat, Infinity);
      sitting.enabled = true;
      sitting.setEffectiveTimeScale(1);
      sitting.setEffectiveWeight(1);
      sitting.fadeIn(0.4).play();
    }
    this.actions.get('Idle')?.fadeOut(0.4);
  }

  /** Gets up: the Sitting clip fades and the locomotion blends back in through animate(). */
  stand(): void {
    if (!this.seated) return;
    this.seated = false;
    this.actions.get('Sitting')?.fadeOut(0.35);
    this.phase = 0;
    const idle = this.actions.get('Idle');
    if (idle) {
      idle.enabled = true;
      idle.play();
    }
  }

  update(dt: number, input: MoveInput): void {
    if (this.seated) {
      this.velocity.set(0, 0, 0);
      this.speedValue = 0;
      this.mixer.update(dt);
      return;
    }
    const manual = Math.hypot(input.x, input.z) > 0.05;
    if (manual && this.route.length) this.cancelRoute();

    let dx = input.x;
    let dz = input.z;
    let run = input.run;
    if (this.route.length) {
      const next = this.route[0];
      const toX = next.x - this.position.x;
      const toZ = next.z - this.position.z;
      const distance = Math.hypot(toX, toZ);
      const last = this.route.length === 1;
      if (distance < (last ? 0.18 : 0.6)) {
        this.route.shift();
        if (!this.route.length) {
          const done = this.onArrive;
          this.onArrive = null;
          done?.();
        }
      } else {
        const slow = last ? Math.min(1, distance / 1.4) : 1;
        dx = (toX / distance) * slow;
        dz = (toZ / distance) * slow;
        run = this.routeRun && distance > 2.5;
      }
    }

    if (this.seated) {
      // the arrival callback of a route may have sat the visitor down this very frame
      this.velocity.set(0, 0, 0);
      this.speedValue = 0;
      this.mixer.update(dt);
      return;
    }
    const length = Math.hypot(dx, dz);
    if (length > 1) {
      dx /= length;
      dz /= length;
    }
    // direction and pace apart: the heading turns at a bounded rate, the pace eases with its own
    // constants (slower to get going than to stop), so turning never drains the speed
    const wanted = Math.min(1, length) * (run ? RUN_SPEED : WALK_SPEED);
    const previousHeading = this.moveHeading;
    if (length > 0.05) {
      const target = Math.atan2(dx, dz);
      let delta = (target - this.moveHeading) % (Math.PI * 2);
      if (delta > Math.PI) delta -= Math.PI * 2;
      if (delta < -Math.PI) delta += Math.PI * 2;
      const step = Math.min(Math.abs(delta), TURN_RATE * dt);
      this.moveHeading += Math.sign(delta) * step;
    }
    const tau = wanted > this.speedValue ? 0.3 : 0.2;
    const previousSpeed = this.speedValue;
    this.speedValue += (wanted - this.speedValue) * (1 - Math.exp(-dt / tau));
    if (this.speedValue < 0.01) this.speedValue = 0;
    this.velocity.set(Math.sin(this.moveHeading) * this.speedValue, 0, Math.cos(this.moveHeading) * this.speedValue);
    // the lean: into the turn by the lateral acceleration, fore and aft by the pace change
    const omega = dt > 0 ? ((this.moveHeading - previousHeading) / dt) : 0;
    const accel = dt > 0 ? (this.speedValue - previousSpeed) / dt : 0;
    const rollTarget = THREE.MathUtils.clamp(0.35 * Math.atan((this.speedValue * omega) / 9.81), -0.15, 0.15);
    const pitchTarget = THREE.MathUtils.clamp(0.03 * accel, -0.1, 0.1);
    const ease = 1 - Math.exp(-dt / 0.12);
    this.roll += (rollTarget - this.roll) * ease;
    this.pitch += (pitchTarget - this.pitch) * ease;
    this.lean.rotation.set(this.pitch, 0, -this.roll);

    this.last.copy(this.position);
    this.position.x += this.velocity.x * dt;
    this.position.z += this.velocity.z * dt;
    this.collide();

    if (this.route.length) {
      const moved = this.last.distanceTo(this.position);
      this.stuckTime = moved < 0.4 * dt ? this.stuckTime + dt : 0;
      if (this.stuckTime > 1.2) {
        // blocked: skip a waypoint, or, close to the end, settle for where we are
        const last = this.route.length === 1;
        const near = last && this.route[0].distanceTo(this.position) < 2.2;
        this.route.shift();
        this.stuckTime = 0;
        if (near) {
          this.route = [];
          const done = this.onArrive;
          this.onArrive = null;
          done?.();
        }
      }
    }

    const current = this.speed;
    if (current > 0.15) {
      this.targetHeading = null;
      this.heading = lerpAngle(this.heading, Math.atan2(this.velocity.x, this.velocity.z), 1 - Math.exp(-dt * 10));
    } else if (this.targetHeading !== null) {
      this.heading = lerpAngle(this.heading, this.targetHeading, 1 - Math.exp(-dt * 6));
    }
    this.root.rotation.y = this.heading;
    this.animate(dt, current);
  }

  private collide(): void {
    const p = this.position;
    for (let pass = 0; pass < 2; pass++) {
      for (const box of this.obstacles) {
        const cx = Math.max(box.minX, Math.min(p.x, box.maxX));
        const cz = Math.max(box.minZ, Math.min(p.z, box.maxZ));
        const ox = p.x - cx;
        const oz = p.z - cz;
        const d2 = ox * ox + oz * oz;
        if (d2 >= RADIUS * RADIUS) continue;
        if (d2 > 1e-8) {
          const d = Math.sqrt(d2);
          p.x = cx + (ox / d) * RADIUS;
          p.z = cz + (oz / d) * RADIUS;
        } else {
          // centre inside the box: push out along the shallowest side
          const pushes = [p.x - box.minX + RADIUS, box.maxX - p.x + RADIUS, p.z - box.minZ + RADIUS, box.maxZ - p.z + RADIUS];
          const side = pushes.indexOf(Math.min(...pushes));
          if (side === 0) p.x = box.minX - RADIUS;
          else if (side === 1) p.x = box.maxX + RADIUS;
          else if (side === 2) p.z = box.minZ - RADIUS;
          else p.z = box.maxZ + RADIUS;
        }
      }
    }
  }

  /**
   * Locomotion as one continuous gait: a single phase drives both cycles so the legs stay in step
   * through the walk-to-run blend; the cadence comes from the pace and the stride each cycle covers,
   * so the planted feet keep their grip, and below walking pace the stride shortens through the
   * blend with the standing pose instead of the feet skating. Stopping settles on the nearest contact.
   */
  private animate(dt: number, speed: number): void {
    const idle = this.actions.get('Idle');
    const walk = this.actions.get('Walking');
    const runAction = this.actions.get('Running');
    const strideWalk = STRIDE_WALK * this.modelScale;
    const strideRun = STRIDE_RUN * this.modelScale;
    const gait = smoothstep(speed, 1.6, 3.8);
    let cadence: number;
    let stride = 1;
    if (speed < WALK_SPEED) {
      cadence = (1 / 0.75) * (0.6 + 0.4 * (speed / WALK_SPEED));
      stride = Math.min(1, speed / (strideWalk * cadence));
    } else {
      cadence = THREE.MathUtils.clamp(speed / THREE.MathUtils.lerp(strideWalk, strideRun, gait), 1.3, 1.8);
    }
    const move = smoothstep(speed, 0.06, 0.45) * stride;
    if (speed > 0.06) {
      this.phase = (this.phase + dt * cadence) % 1;
    } else {
      // come to rest on a contact pose: the nearest of the two in the cycle
      const rest = Math.round(this.phase * 2) / 2;
      this.phase += (rest - this.phase) * (1 - Math.exp(-dt * 10));
    }
    if (walk) walk.time = (this.phase % 1) * walk.getClip().duration;
    if (runAction) runAction.time = (this.phase % 1) * runAction.getClip().duration;
    const gestureWeight = this.gesture ? this.gesture.getEffectiveWeight() : 0;
    // a sitting clip still fading out after standing keeps its share of the blend; an action that
    // never played reports a weight of one, so only a running one counts
    const sitting = this.actions.get('Sitting');
    const sittingWeight = sitting && sitting.isRunning() ? sitting.getEffectiveWeight() : 0;
    const base = (1 - gestureWeight * (1 - move)) * (1 - sittingWeight);
    idle?.setEffectiveWeight((1 - move) * base);
    walk?.setEffectiveWeight(move * (1 - gait) * base);
    runAction?.setEffectiveWeight(move * gait * base);
    this.mixer.update(dt);
  }

  dispose(): void {
    this.mixer.stopAllAction();
    this.mixer.uncacheRoot(this.mixer.getRoot());
  }
}
