import * as THREE from 'three/webgpu';
import { abs, color, float, fract, max, mix, mx_noise_float, positionLocal, positionWorld, smoothstep, step, texture, time, uv, vec2 } from 'three/tsl';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { dequantizeMeshes } from '../../core/assets/dequantize';
import { loadGltf } from '../../core/assets/gltf';
import { DisposeBag, disposeObject } from '../../core/engine/dispose';
import { EngineContext, WorldScene } from '../../core/engine/world-scene';
import { Character, FloorBox, MoveInput } from './character';
import { drawAbout, drawContact, drawLabel, drawLightbox, drawSign, loadMuseumFonts, MuseumCopy, PanelTexture } from './museum-textures';

export type ExhibitKind = 'about' | 'experience' | 'project' | 'contact';

export interface Exhibit {
  readonly id: string;
  readonly kind: ExhibitKind;
  readonly index: number;
  readonly spot: THREE.Vector3;
  readonly focus: THREE.Vector3;
}

interface Obstacle extends FloorBox {
  maxY: number;
}

type Room = 'lobby' | 'hall' | 'wing';

/** Waypoints so routes go through doors instead of into walls. */
const NODES: Record<string, { x: number; z: number; rooms: Room[] }> = {
  L: { x: 0, z: 27, rooms: ['lobby'] },
  D1: { x: 0, z: 19.6, rooms: ['lobby', 'hall'] },
  W1: { x: -4.5, z: 15, rooms: ['hall'] },
  E1: { x: 4.5, z: 15, rooms: ['hall'] },
  W2: { x: -4.5, z: 4, rooms: ['hall'] },
  E2: { x: 4.5, z: 4, rooms: ['hall'] },
  E3: { x: 4.5, z: -1, rooms: ['hall'] },
  W3: { x: -4.5, z: -9, rooms: ['hall'] },
  E4: { x: 4.5, z: -9, rooms: ['hall'] },
  W4: { x: -4.5, z: -21, rooms: ['hall'] },
  E5: { x: 4.5, z: -21, rooms: ['hall'] },
  D2: { x: 8.6, z: -1, rooms: ['hall', 'wing'] },
  WC: { x: 14, z: -3, rooms: ['wing'] },
};
const EDGES: [string, string][] = [
  ['L', 'D1'], ['D1', 'W1'], ['D1', 'E1'], ['W1', 'E1'], ['W1', 'W2'], ['E1', 'E2'], ['W2', 'E2'], ['E2', 'E3'],
  ['E3', 'E4'], ['W2', 'W3'], ['W3', 'W4'], ['E4', 'E5'], ['W4', 'E5'], ['E3', 'D2'], ['D2', 'WC'],
];

const roomAt = (x: number, z: number): Room => (z > 20 ? 'lobby' : x > 7.2 ? 'wing' : 'hall');

export class AtriumScene implements WorldScene {
  readonly scene = new THREE.Scene();
  readonly camera = new THREE.PerspectiveCamera(50, 1, 0.1, 200);

  private readonly bag = new DisposeBag();
  private character: Character | null = null;
  private readonly obstacles: Obstacle[] = [];
  readonly exhibits: Exhibit[] = [];
  private readonly clickables: THREE.Mesh[] = [];
  private readonly panels = new Map<string, PanelTexture>();
  private copy: MuseumCopy;

  private readonly keys = { forward: 0, right: 0, run: false };
  private readonly stick = { x: 0, y: 0 };
  private yaw = 0;
  private pitch = 0.32;
  private distance = 4.6;
  private targetDistance = 4.6;
  private manualCameraAt = -10;
  private elapsed = 0;
  private active: Exhibit | null = null;
  private lastWave = -10;
  private readonly sun = new THREE.DirectionalLight('#fff4e4', 2.2);
  private readonly raycaster = new THREE.Raycaster();
  private readonly floor = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
  private readonly pivot = new THREE.Vector3();
  private readonly desired = new THREE.Vector3();
  private readonly look = new THREE.Vector3();

  /** Called whenever the visitor reaches or leaves an exhibit. */
  onExhibit: ((exhibit: Exhibit | null) => void) | null = null;
  /** Called the first time the visitor moves, so the page can hide the controls hint. */
  onFirstMove: (() => void) | null = null;
  private moved = false;

  constructor(
    private readonly ctx: EngineContext,
    copy: MuseumCopy,
  ) {
    this.copy = copy;
    this.scene.background = new THREE.Color('#141615');
    this.scene.add(new THREE.HemisphereLight('#fff3e2', '#2c3230', 0.9));
    this.sun.position.set(4, 14, 3);
    this.sun.castShadow = ctx.quality !== 'low';
    this.sun.shadow.mapSize.set(1024, 1024);
    const cam = this.sun.shadow.camera;
    cam.left = -10;
    cam.right = 10;
    cam.top = 10;
    cam.bottom = -10;
    cam.near = 1;
    cam.far = 40;
    this.sun.shadow.bias = -0.0008;
    this.sun.shadow.radius = 4;
    this.scene.add(this.sun, this.sun.target);
  }

  activate(): void {
    this.ctx.renderer.toneMapping = THREE.AgXToneMapping;
    this.ctx.renderer.toneMappingExposure = 1.25;
  }

  async init(onProgress: (fraction: number) => void): Promise<void> {
    let museumPart = 0;
    let robotPart = 0;
    const report = () => onProgress(museumPart * 0.35 + robotPart * 0.55);
    const [museum, robot] = await Promise.all([
      loadGltf('models/atrium/museum.glb', (f) => {
        museumPart = f;
        report();
      }),
      loadGltf('models/atrium/robot.glb', (f) => {
        robotPart = f;
        report();
      }),
      loadMuseumFonts(),
      this.environment(),
    ]);

    const root = museum.scene;
    dequantizeMeshes(root);
    root.updateMatrixWorld(true);
    this.applyMaterials(root);
    this.collectObstacles(root);
    this.collectExhibits(root);
    this.addPictureLights(root);
    this.addSkyBeams(root);
    this.scene.add(root);
    this.redraw();

    this.character = new Character(robot, this.obstacles);
    const spawn = root.getObjectByName('spawn')?.position ?? new THREE.Vector3(0, 0, 31);
    this.character.place(spawn.x, spawn.z, Math.PI);
    this.yaw = this.character.heading + Math.PI;
    this.scene.add(this.character.root);
    this.updateCamera(1, true);
    onProgress(1);
  }

  private async environment(): Promise<void> {
    const pmrem = new THREE.PMREMGenerator(this.ctx.renderer);
    const room = new RoomEnvironment();
    const target = pmrem.fromScene(room, 0.04);
    this.bag.add(target);
    this.bag.add(pmrem);
    room.traverse((o) => {
      const mesh = o as THREE.Mesh;
      mesh.geometry?.dispose();
      (mesh.material as THREE.Material | undefined)?.dispose();
    });
    this.scene.environment = target.texture;
    this.scene.environmentIntensity = 0.5;
  }

  private applyMaterials(root: THREE.Object3D): void {
    const lib = new Map<string, THREE.Material>();
    const std = (name: string, params: ConstructorParameters<typeof THREE.MeshStandardNodeMaterial>[0]) => {
      const m = new THREE.MeshStandardNodeMaterial(params);
      lib.set(name, m);
      return m;
    };
    std('wall_light', { color: '#ebe7e0', roughness: 0.92 });
    std('wall_green', { color: '#25423a', roughness: 0.9 });
    std('wall_dark', { color: '#232529', roughness: 0.9 });
    std('ceiling', { color: '#efede8', roughness: 0.95 });
    std('frame', { color: '#b48a4a', roughness: 0.32, metalness: 1 });
    std('frame_dark', { color: '#17181b', roughness: 0.4 });
    std('brass', { color: '#c59a52', roughness: 0.28, metalness: 1 });
    std('bench', { color: '#3a2a1f', roughness: 0.55 });
    std('leather', { color: '#1d1e22', roughness: 0.55 });
    std('marble', { color: '#ebe8e3', roughness: 0.22 });
    std('desk', { color: '#efece7', roughness: 0.45 });
    std('trim', { color: '#191a1d', roughness: 0.5 });

    const stone = std('floor_stone', { roughness: 0.2 });
    const p = positionWorld.xz;
    const tile = p.div(1.2);
    const seam = max(step(0.985, fract(tile.x)), step(0.985, fract(tile.y)));
    const veins = mx_noise_float(p.mul(0.45)).mul(0.5).add(0.5);
    stone.colorNode = mix(mix(color('#d2cfc8'), color('#c3bfb6'), veins), color('#9b978f'), seam);
    stone.roughnessNode = mix(float(0.16), float(0.5), seam);

    const oak = std('floor_oak', { roughness: 0.45 });
    const plank = fract(p.y.div(0.22));
    const grain = mx_noise_float(p.mul(vec2(0.6, 9))).mul(0.5).add(0.5);
    oak.colorNode = mix(mix(color('#5c3e2a'), color('#7a5539'), grain), color('#2e2016'), step(0.97, plank));

    const sky = new THREE.MeshBasicNodeMaterial();
    sky.colorNode = color('#fff6e8').mul(1.8);
    lib.set('skylight', sky);

    const loader = new THREE.TextureLoader();
    root.traverse((o) => {
      const mesh = o as THREE.Mesh;
      if (!mesh.isMesh) return;
      const source = mesh.material as THREE.Material;
      const name = mesh.name;
      let material: THREE.Material | undefined;
      if (name.startsWith('canvas_')) {
        const index = Number(name.split('_')[1]);
        const project = this.copy.portfolio.projects[index];
        const art = new THREE.MeshBasicNodeMaterial();
        const map = loader.load(project?.cover ?? '');
        map.colorSpace = THREE.SRGBColorSpace;
        map.flipY = false;
        map.anisotropy = 8;
        this.bag.add(map);
        art.colorNode = texture(map).rgb.mul(0.95);
        material = this.bag.add(art);
        mesh.userData['exhibit'] = `project-${index}`;
        this.clickables.push(mesh);
      } else if (name.startsWith('label_') || name.startsWith('exp_') || name.startsWith('sign_') || name === 'about_panel' || name === 'contact_panel') {
        const size: Record<string, [number, number]> = { label: [512, 334], exp: [1024, 648], sign: [1024, 256], about: [1400, 720], contact: [1024, 568] };
        const key = name.split('_')[0];
        const [w, h] = size[key] ?? [512, 512];
        const panel = new PanelTexture(w, h);
        this.panels.set(name, panel);
        this.bag.add(panel);
        const flat = new THREE.MeshBasicNodeMaterial();
        flat.colorNode = texture(panel.texture).rgb.mul(key === 'exp' ? 1.15 : key === 'sign' ? 1 : 0.9);
        material = this.bag.add(flat);
        if (key === 'exp') {
          mesh.userData['exhibit'] = `experience-${name.split('_')[1]}`;
          this.clickables.push(mesh);
        }
        if (name === 'about_panel') {
          mesh.userData['exhibit'] = 'about';
          this.clickables.push(mesh);
        }
        if (name === 'contact_panel') {
          mesh.userData['exhibit'] = 'contact';
          this.clickables.push(mesh);
        }
      } else {
        material = lib.get(source.name);
      }
      if (material) {
        source.dispose();
        mesh.material = material;
      }
      mesh.receiveShadow = true;
      mesh.castShadow = source.name === 'bench' || source.name === 'marble' || source.name === 'desk';
    });
    lib.forEach((m) => this.bag.add(m));
  }

  private collectObstacles(root: THREE.Object3D): void {
    const solid = root.getObjectByName('solid');
    solid?.traverse((o) => {
      if (!(o as THREE.Mesh).isMesh) return;
      const box = new THREE.Box3().setFromObject(o);
      this.obstacles.push({ minX: box.min.x, maxX: box.max.x, minZ: box.min.z, maxZ: box.max.z, maxY: box.max.y });
    });
  }

  private collectExhibits(root: THREE.Object3D): void {
    const centre = (name: string) => {
      const object = root.getObjectByName(name);
      return object ? new THREE.Box3().setFromObject(object).getCenter(new THREE.Vector3()) : new THREE.Vector3();
    };
    const spot = (name: string) => root.getObjectByName(name)?.position.clone() ?? new THREE.Vector3();
    this.exhibits.push({ id: 'about', kind: 'about', index: 0, spot: spot('spot_about'), focus: centre('about_panel') });
    for (let i = 0; i < 5; i++) {
      this.exhibits.push({ id: `experience-${i}`, kind: 'experience', index: i, spot: spot(`spot_exp_${i}`), focus: centre(`exp_${i}`) });
    }
    for (let i = 0; i < 13; i++) {
      this.exhibits.push({ id: `project-${i}`, kind: 'project', index: i, spot: spot(`spot_canvas_${i}`), focus: centre(`canvas_${i}`) });
    }
    this.exhibits.push({ id: 'contact', kind: 'contact', index: 0, spot: spot('spot_contact'), focus: centre('contact_panel') });
  }

  /** Warm cones on the wall under each picture light; cheaper than thirteen real spotlights. */
  private addPictureLights(root: THREE.Object3D): void {
    const geometry = this.bag.add(new THREE.PlaneGeometry(1, 1));
    const material = new THREE.MeshBasicNodeMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending });
    const local = uv();
    const fromTop = float(1).sub(local.y);
    const spread = abs(local.x.sub(0.5)).mul(2);
    const cone = smoothstep(fromTop.mul(0.75).add(0.25), fromTop.mul(0.3), spread).mul(smoothstep(1.0, 0.1, fromTop));
    material.colorNode = color('#ffd9a3').mul(cone.mul(0.32));
    this.bag.add(material);
    for (let i = 0; i < 13; i++) {
      const light = root.getObjectByName(`light_${i}`);
      const exhibit = this.exhibits.find((e) => e.id === `project-${i}`);
      if (!light || !exhibit) continue;
      const normal = exhibit.spot.clone().sub(exhibit.focus).setY(0).normalize();
      const featured = i === 12;
      const glow = new THREE.Mesh(geometry, material);
      glow.scale.set(featured ? 6.4 : 3.4, featured ? 4.2 : 2.9, 1);
      glow.position.copy(exhibit.focus).addScaledVector(normal, 0.04);
      glow.position.y = light.position.y - glow.scale.y / 2 + 0.2;
      glow.lookAt(glow.position.clone().add(normal));
      glow.renderOrder = 2;
      this.scene.add(glow);
    }
  }

  /** Soft shafts of light under the skylights, with a little dust drifting through. */
  private addSkyBeams(root: THREE.Object3D): void {
    const geometry = this.bag.add(new THREE.BoxGeometry(5.4, 6, 3.6));
    geometry.translate(0, 3, 0);
    const material = new THREE.MeshBasicNodeMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide });
    const height = positionLocal.y.div(6);
    const dust = smoothstep(0.62, 0.9, mx_noise_float(positionWorld.mul(1.6).add(time.mul(0.08))));
    material.colorNode = color('#fff1dc').mul(height.pow(1.6).mul(0.05).add(dust.mul(0.02)));
    this.bag.add(material);
    for (let k = 0; k < 5; k++) {
      const anchor = root.getObjectByName(`sky_${k}`);
      if (!anchor) continue;
      const beam = new THREE.Mesh(geometry, material);
      beam.position.set(anchor.position.x, 0, anchor.position.z);
      beam.rotation.x = 0.12;
      beam.renderOrder = 3;
      this.scene.add(beam);
    }
  }

  /** Redraws every canvas texture, for example after a language change. */
  setCopy(copy: MuseumCopy): void {
    this.copy = copy;
    this.redraw();
  }

  private redraw(): void {
    const { portfolio, experience } = this.copy;
    portfolio.projects.forEach((project, i) => {
      const panel = this.panels.get(`label_${i}`);
      if (panel) drawLabel(panel, project, this.copy.medium);
    });
    experience.forEach((job, i) => {
      const panel = this.panels.get(`exp_${i}`);
      if (panel) drawLightbox(panel, job);
    });
    const about = this.panels.get('about_panel');
    if (about) drawAbout(about, portfolio);
    const contact = this.panels.get('contact_panel');
    if (contact) drawContact(contact, this.copy.contactTitle, portfolio);
    const hall = this.panels.get('sign_hall');
    if (hall) drawSign(hall, this.copy.projectsSign);
    const wing = this.panels.get('sign_wing');
    if (wing) drawSign(wing, this.copy.experienceSign);
  }

  // --- input -----------------------------------------------------------------------------------

  setKeys(forward: number, right: number, run: boolean): void {
    this.keys.forward = forward;
    this.keys.right = right;
    this.keys.run = run;
  }

  setStick(x: number, y: number): void {
    this.stick.x = x;
    this.stick.y = y;
  }

  rotate(dx: number, dy: number): void {
    this.yaw -= dx * 0.005;
    this.pitch = THREE.MathUtils.clamp(this.pitch + dy * 0.004, 0.05, 1.0);
    this.manualCameraAt = this.elapsed;
  }

  zoom(delta: number): void {
    this.targetDistance = THREE.MathUtils.clamp(this.targetDistance + delta * 0.004, 2.4, 8);
  }

  /** Exhibit under a screen point, in normalised device coordinates. */
  pick(x: number, y: number): Exhibit | null {
    this.raycaster.setFromCamera(new THREE.Vector2(x, y), this.camera);
    const hit = this.raycaster.intersectObjects(this.clickables, false)[0];
    const id = hit?.object.userData['exhibit'] as string | undefined;
    return id ? (this.exhibits.find((e) => e.id === id) ?? null) : null;
  }

  /** Click or tap: walk to the exhibit under the pointer, or to that spot on the floor. */
  click(x: number, y: number): void {
    const exhibit = this.pick(x, y);
    if (exhibit) {
      this.goTo(exhibit.id);
      return;
    }
    const point = new THREE.Vector3();
    if (this.raycaster.ray.intersectPlane(this.floor, point)) this.walkTo(point, null);
  }

  goTo(id: string): void {
    const exhibit = this.exhibits.find((e) => e.id === id);
    if (!exhibit || !this.character) return;
    this.walkTo(exhibit.spot, () => {
      this.character?.turnTowards(exhibit.focus);
      this.yaw = Math.atan2(exhibit.focus.x - exhibit.spot.x, exhibit.focus.z - exhibit.spot.z) + Math.PI;
      this.pitch = 0.16;
      this.targetDistance = 4.2;
      this.manualCameraAt = this.elapsed;
      this.character?.play('Wave');
      this.lastWave = this.elapsed;
    });
  }

  private walkTo(target: THREE.Vector3, onArrive: (() => void) | null): void {
    const character = this.character;
    if (!character) return;
    const from = character.position;
    const route = this.route(from, target);
    character.follow([...route, target], from.distanceTo(target) > 6, onArrive);
    this.markMoved();
  }

  private route(from: THREE.Vector3, to: THREE.Vector3): THREE.Vector3[] {
    const start = roomAt(from.x, from.z);
    const end = roomAt(to.x, to.z);
    if (start === end) return [];
    const nearest = (p: THREE.Vector3, room: Room) => {
      let best = '';
      let bestDistance = Infinity;
      for (const [id, node] of Object.entries(NODES)) {
        if (!node.rooms.includes(room)) continue;
        const d = Math.hypot(node.x - p.x, node.z - p.z);
        if (d < bestDistance) {
          bestDistance = d;
          best = id;
        }
      }
      return best;
    };
    const source = nearest(from, start);
    const goal = nearest(to, end);
    const distance = new Map<string, number>([[source, 0]]);
    const previous = new Map<string, string>();
    const open = new Set(Object.keys(NODES));
    while (open.size) {
      let current = '';
      let best = Infinity;
      for (const id of open) {
        const d = distance.get(id) ?? Infinity;
        if (d < best) {
          best = d;
          current = id;
        }
      }
      if (!current || current === goal) break;
      open.delete(current);
      for (const [a, b] of EDGES) {
        const next = a === current ? b : b === current ? a : null;
        if (!next || !open.has(next)) continue;
        const step = Math.hypot(NODES[a].x - NODES[b].x, NODES[a].z - NODES[b].z);
        if (best + step < (distance.get(next) ?? Infinity)) {
          distance.set(next, best + step);
          previous.set(next, current);
        }
      }
    }
    const path: THREE.Vector3[] = [];
    for (let id: string | undefined = goal; id; id = previous.get(id)) {
      path.unshift(new THREE.Vector3(NODES[id].x, 0, NODES[id].z));
      if (id === source) break;
    }
    return path;
  }

  private markMoved(): void {
    if (this.moved) return;
    this.moved = true;
    this.onFirstMove?.();
  }

  // --- frame -----------------------------------------------------------------------------------

  update(dt: number, elapsed: number): void {
    const character = this.character;
    if (!character) return;
    this.elapsed = elapsed;

    const forwardX = -Math.sin(this.yaw);
    const forwardZ = -Math.cos(this.yaw);
    const rightX = Math.cos(this.yaw);
    const rightZ = -Math.sin(this.yaw);
    const ahead = THREE.MathUtils.clamp(this.keys.forward + this.stick.y, -1, 1);
    const side = THREE.MathUtils.clamp(this.keys.right + this.stick.x, -1, 1);
    const input: MoveInput = {
      x: forwardX * ahead + rightX * side,
      z: forwardZ * ahead + rightZ * side,
      run: this.keys.run || Math.hypot(this.stick.x, this.stick.y) > 0.92,
    };
    if (Math.abs(ahead) + Math.abs(side) > 0) this.markMoved();
    character.update(dt, input);

    // keep the camera behind the visitor while walking, unless the user turned it recently
    if (character.speed > 0.6 && elapsed - this.manualCameraAt > 1.6 && Math.abs(side) < 0.1) {
      let target = character.heading + Math.PI;
      let delta = (target - this.yaw) % (Math.PI * 2);
      if (delta > Math.PI) delta -= Math.PI * 2;
      if (delta < -Math.PI) delta += Math.PI * 2;
      target = this.yaw + delta;
      this.yaw += (target - this.yaw) * (1 - Math.exp(-dt * 1.4));
    }
    this.updateCamera(dt, false);

    this.sun.target.position.copy(character.position);
    this.sun.position.copy(character.position).add(new THREE.Vector3(4, 14, 3));
    this.sun.target.updateMatrixWorld();

    this.detectExhibit(elapsed);
  }

  private updateCamera(dt: number, snap: boolean): void {
    const character = this.character;
    if (!character) return;
    this.distance += (this.targetDistance - this.distance) * (1 - Math.exp(-dt * 6));
    this.pivot.copy(character.position).add(new THREE.Vector3(0, 1.35, 0));
    const cosPitch = Math.cos(this.pitch);
    const dirX = Math.sin(this.yaw) * cosPitch;
    const dirY = Math.sin(this.pitch);
    const dirZ = Math.cos(this.yaw) * cosPitch;
    let reach = this.distance;
    for (const box of this.obstacles) {
      if (box.maxY < 1.6) continue;
      const t = this.rayBox(this.pivot.x, this.pivot.z, dirX, dirZ, box);
      if (t !== null && t < reach) reach = Math.max(0.6, t - 0.25);
    }
    this.desired.set(this.pivot.x + dirX * reach, Math.min(5.4, this.pivot.y + dirY * reach), this.pivot.z + dirZ * reach);
    if (snap) this.camera.position.copy(this.desired);
    else this.camera.position.lerp(this.desired, 1 - Math.exp(-dt * 12));
    this.look.copy(this.pivot).add(new THREE.Vector3(0, 0.15, 0));
    this.camera.lookAt(this.look);
  }

  /** Distance along a horizontal ray to a floor box, or null if it misses. */
  private rayBox(ox: number, oz: number, dx: number, dz: number, box: FloorBox): number | null {
    let tMin = 0;
    let tMax = Infinity;
    for (const [o, d, lo, hi] of [
      [ox, dx, box.minX, box.maxX],
      [oz, dz, box.minZ, box.maxZ],
    ]) {
      if (Math.abs(d) < 1e-6) {
        if (o < lo || o > hi) return null;
        continue;
      }
      let t1 = (lo - o) / d;
      let t2 = (hi - o) / d;
      if (t1 > t2) [t1, t2] = [t2, t1];
      tMin = Math.max(tMin, t1);
      tMax = Math.min(tMax, t2);
      if (tMin > tMax) return null;
    }
    // (dx, dz) are the horizontal parts of the unit arm direction, so t is already a distance along the arm
    return tMin;
  }

  private detectExhibit(elapsed: number): void {
    const character = this.character!;
    let best: Exhibit | null = null;
    let bestDistance = 2.6;
    for (const exhibit of this.exhibits) {
      const d = Math.hypot(exhibit.spot.x - character.position.x, exhibit.spot.z - character.position.z);
      if (d < bestDistance) {
        bestDistance = d;
        best = exhibit;
      }
    }
    if (best === this.active) return;
    this.active = best;
    if (best && !character.walking && elapsed - this.lastWave > 8) {
      character.play('ThumbsUp');
      this.lastWave = elapsed;
    }
    this.onExhibit?.(best);
  }

  resize(width: number, height: number): void {
    this.camera.aspect = width / height;
    this.camera.fov = width < height ? 62 : 50;
    this.camera.updateProjectionMatrix();
  }

  dispose(): void {
    this.character?.dispose();
    this.bag.dispose();
    disposeObject(this.scene);
    this.scene.clear();
  }
}
