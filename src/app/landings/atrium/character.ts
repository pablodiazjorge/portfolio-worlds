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

const WALK_SPEED = 2.1;
const RUN_SPEED = 4.6;
const RADIUS = 0.34;
const HEIGHT = 1.65;

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
    const box = new THREE.Box3().setFromObject(model);
    const scale = HEIGHT / Math.max(0.001, box.max.y - box.min.y);
    model.scale.setScalar(scale);
    model.position.y = -box.min.y * scale;
    model.traverse((o) => {
      const mesh = o as THREE.Mesh;
      if (mesh.isMesh) {
        mesh.castShadow = true;
        mesh.receiveShadow = true;
      }
    });
    this.root.add(model);

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
    this.root.rotation.y = heading;
    this.velocity.set(0, 0, 0);
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

  update(dt: number, input: MoveInput): void {
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

    const length = Math.hypot(dx, dz);
    if (length > 1) {
      dx /= length;
      dz /= length;
    }
    const speed = run ? RUN_SPEED : WALK_SPEED;
    const blend = 1 - Math.exp(-dt * 8);
    this.velocity.x += (dx * speed - this.velocity.x) * blend;
    this.velocity.z += (dz * speed - this.velocity.z) * blend;

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

  private animate(dt: number, speed: number): void {
    const idle = this.actions.get('Idle');
    const walk = this.actions.get('Walking');
    const runAction = this.actions.get('Running');
    const run = THREE.MathUtils.smoothstep(speed, WALK_SPEED * 1.05, RUN_SPEED * 0.85);
    const move = THREE.MathUtils.smoothstep(speed, 0.08, 0.9);
    const gestureWeight = this.gesture ? this.gesture.getEffectiveWeight() : 0;
    const base = 1 - gestureWeight * (1 - move);
    idle?.setEffectiveWeight((1 - move) * base);
    walk?.setEffectiveWeight(move * (1 - run) * base);
    runAction?.setEffectiveWeight(move * run * base);
    walk?.setEffectiveTimeScale(Math.max(0.6, speed / WALK_SPEED));
    runAction?.setEffectiveTimeScale(Math.max(0.7, speed / RUN_SPEED));
    this.mixer.update(dt);
  }

  dispose(): void {
    this.mixer.stopAllAction();
    this.mixer.uncacheRoot(this.mixer.getRoot());
  }
}
