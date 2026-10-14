import * as THREE from 'three/webgpu';
import { abs, color, float, fract, max, min, mix, mx_noise_float, positionLocal, positionWorld, reflector, smoothstep, texture, time, uv, vec2 } from 'three/tsl';
import { drawLandscape, drawStainedGlass } from './stained-glass';
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

type Room = 'hall' | 'second';

/** Waypoints so routes between the two rooms go down the aisles and through the arch. */
const NODES: Record<string, { x: number; z: number; rooms: Room[] }> = {
  S: { x: 0, z: 2, rooms: ['hall'] },
  W1: { x: -4.1, z: -1, rooms: ['hall'] },
  E1: { x: 4.1, z: -1, rooms: ['hall'] },
  W2: { x: -4.1, z: -12.5, rooms: ['hall'] },
  E2: { x: 4.1, z: -12.5, rooms: ['hall'] },
  A: { x: 0, z: -16, rooms: ['hall', 'second'] },
  N: { x: 0, z: -30, rooms: ['second'] },
};
const EDGES: [string, string][] = [
  ['S', 'W1'], ['S', 'E1'], ['W1', 'W2'], ['E1', 'E2'], ['W2', 'A'], ['E2', 'A'], ['A', 'N'],
];

const roomAt = (_x: number, z: number): Room => (z > -18.5 ? 'hall' : 'second');

/** The roped pedestal in the middle of the nave, which a straight walk must go round. */
const PEDESTAL = { minX: -3.8, maxX: 3.8, minZ: -10.8, maxZ: -3.2 };

function crossesPedestal(from: THREE.Vector3, to: THREE.Vector3): boolean {
  // a 2D segment against the box, by clipping the parameter range on each axis
  let t0 = 0;
  let t1 = 1;
  for (const [a, b, lo, hi] of [
    [from.x, to.x, PEDESTAL.minX, PEDESTAL.maxX],
    [from.z, to.z, PEDESTAL.minZ, PEDESTAL.maxZ],
  ]) {
    const d = b - a;
    if (Math.abs(d) < 1e-6) {
      if (a < lo || a > hi) return false;
      continue;
    }
    let near = (lo - a) / d;
    let far = (hi - a) / d;
    if (near > far) [near, far] = [far, near];
    t0 = Math.max(t0, near);
    t1 = Math.min(t1, far);
    if (t0 > t1) return false;
  }
  return true;
}

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
  private readonly sun = new THREE.DirectionalLight('#ffc27a', 7.5);
  private readonly sunOffset = new THREE.Vector3(-12, 7.5, 3);
  private readonly glassCache = new Map<string, THREE.Material>();
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
    this.scene.background = new THREE.Color('#1a1712');
    // a bright hall: warm bounce from the marble, cooler light from high up, sun from the west
    this.scene.add(new THREE.HemisphereLight('#ffdcb0', '#5a4636', 0.22));
    this.sun.position.set(-9, 14, 4);
    this.sun.castShadow = ctx.quality !== 'low';
    this.sun.shadow.mapSize.set(2048, 2048);
    const cam = this.sun.shadow.camera;
    cam.left = -16;
    cam.right = 16;
    cam.top = 16;
    cam.bottom = -16;
    cam.near = 1;
    cam.far = 50;
    this.sun.shadow.bias = -0.0006;
    this.sun.shadow.radius = 4;
    this.scene.add(this.sun, this.sun.target);
  }

  activate(): void {
    this.ctx.renderer.toneMapping = THREE.AgXToneMapping;
    this.ctx.renderer.toneMappingExposure = 0.85;
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
    this.addWindowLight(root);
    this.addColourPools(root);
    this.addSconceHalos(root);
    this.addCandles(root);
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
    const p = positionWorld.xz;
    const grain = mx_noise_float(positionWorld.mul(1.3)).mul(0.5).add(0.5);

    // cream stone with a little dirt in the grain; the mouldings a shade darker
    const stone = std('stone', { roughness: 0.85 });
    stone.colorNode = mix(color('#e3d5be'), color('#cdbb9e'), grain.mul(0.6));
    const stoneDark = std('stone_dark', { roughness: 0.85 });
    stoneDark.colorNode = mix(color('#cbbb9f'), color('#b5a387'), grain.mul(0.6));
    const vault = std('vault', { roughness: 0.9 });
    // the webs darken towards the crown, where the candlelight does not reach
    vault.colorNode = mix(color('#efe4d2'), color('#cdbfa8'), smoothstep(14, 22.5, positionWorld.y));
    std('rib', { color: '#9c8a6a', roughness: 0.85 });
    std('panel_blue', { color: '#233459', roughness: 0.8 });
    std('gold', { color: '#d8b05a', roughness: 0.28, metalness: 1 });
    std('brass', { color: '#b08a45', roughness: 0.34, metalness: 1 });
    std('crimson', { color: '#7a1f2e', roughness: 0.85 });
    std('wood', { color: '#3b2719', roughness: 0.55 });
    std('velvet', { color: '#a1202f', roughness: 0.95 });
    const marble = std('marble', { roughness: 0.28 });
    marble.colorNode = mix(color('#f3efe8'), color('#d9d2c6'), smoothstep(0.55, 0.9, mx_noise_float(positionWorld.mul(2.2))).mul(0.5));
    std('statue', { color: '#a6a39d', roughness: 0.72 });
    std('plinth', { color: '#2b211c', roughness: 0.75 });
    std('lead', { color: '#141418', roughness: 0.9 });
    std('candle', { color: '#f2e6cc', roughness: 0.6 });
    std('iron', { color: '#2a2b30', roughness: 0.5, metalness: 0.8 });
    std('paper', { color: '#f1e8d2', roughness: 0.85 });
    std('screen', { color: '#28303a', roughness: 0.3 });
    std('label', { color: '#f4f2ee', roughness: 0.7 });
    std('canvas', { color: '#222222', roughness: 0.8 });

    // the windows are painted per opening in glassFor, below
    const flame = new THREE.MeshBasicNodeMaterial();
    flame.colorNode = color('#ffc46a').mul(2.2);
    lib.set('flame', flame);
    const caseGlass = new THREE.MeshPhysicalNodeMaterial({ color: '#dfe8f0', roughness: 0.05, transparent: true, opacity: 0.16, depthWrite: false, side: THREE.DoubleSide });
    lib.set('case_glass', caseGlass);

    // polished marble with the inlay: red bands on a diamond grid and a border along the walls
    const floor = std('floor', { roughness: 0.14 });
    const veins = smoothstep(0.48, 0.92, mx_noise_float(positionWorld.mul(vec2(0.9, 0.35).xyx)).mul(0.5).add(0.5));
    const base = mix(color('#e2d9c8'), color('#c9bda9'), veins.mul(0.55));
    const turned = vec2(p.x.add(p.y), p.x.sub(p.y)).div(8.0);
    const cell = turned.floor();
    const toLine = abs(fract(turned).sub(0.5));
    const nearest = min(toLine.x, toLine.y);
    const band = float(1).sub(smoothstep(0.024, 0.034, nearest));
    const inner = smoothstep(0.3, 0.32, nearest).mul(float(1).sub(smoothstep(0.34, 0.36, nearest)));
    const checker = fract(cell.x.add(cell.y).mul(0.5)).mul(2);
    const field = mix(base, mix(color('#bdb19d'), color('#a89d8b'), veins.mul(0.5)), checker);
    const border = float(1).sub(smoothstep(0.1, 0.2, abs(abs(p.x).sub(5.55))));
    const joints = max(float(1).sub(smoothstep(0.004, 0.012, abs(fract(p.x.div(1.1)).sub(0.5)).negate().add(0.5))), float(1).sub(smoothstep(0.004, 0.012, abs(fract(p.y.div(1.1)).sub(0.5)).negate().add(0.5))));
    const inlay = max(band, border);
    const stoneFloor = mix(mix(mix(field, color('#b9b2a4'), joints.mul(0.45)), color('#9a9388'), inner.mul(0.6)), color('#4f1016'), inlay.mul(0.96));
    floor.roughnessNode = mix(float(0.12), float(0.3), inlay);
    if (this.ctx.quality === 'low') {
      floor.colorNode = stoneFloor;
    } else {
      // the polish: the hall mirrored in the marble, dimmer on the inlay
      const mirror = reflector({ resolutionScale: this.ctx.quality === 'high' ? 0.35 : 0.25 });
      mirror.target.rotateX(-Math.PI / 2);
      mirror.target.position.y = 0.002;
      this.scene.add(mirror.target);
      this.bag.defer(() => mirror.dispose());
      floor.colorNode = mix(stoneFloor, mirror.rgb.mul(0.9), mix(float(0.3), float(0.06), inlay));
    }

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
      } else if (source.name === 'collider') {
        mesh.visible = false;
        return;
      } else if (source.name === 'glass') {
        material = this.glassFor(mesh);
      } else if (mesh.name.startsWith('deco_canvas')) {
        material = this.landscapeFor(mesh);
      } else {
        material = lib.get(source.name);
      }
      if (material) {
        source.dispose();
        mesh.material = material;
      }
      mesh.receiveShadow = source.name !== 'glass' && source.name !== 'flame';
      mesh.castShadow = /^(marble|statue|plinth|wood|stone|stone_dark)$/.test(source.name);
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

  /** A stained-glass window painted on a canvas, sized to the opening, one of a few variants. */
  private glassFor(mesh: THREE.Mesh): THREE.Material {
    mesh.geometry.computeBoundingBox();
    const size = mesh.geometry.boundingBox!.getSize(new THREE.Vector3());
    const width = Math.max(size.x, size.z);
    const height = size.y;
    const lights: 1 | 2 = width / height > 0.3 ? 2 : 1;
    const variant = [...mesh.name].reduce((h, ch) => (h * 31 + ch.charCodeAt(0)) >>> 0, 7) % 5;
    const key = `${lights}:${(width / height).toFixed(2)}:${variant}`;
    let material = this.glassCache.get(key);
    if (!material) {
      const canvas = document.createElement('canvas');
      const w = lights === 2 ? 1024 : 512;
      drawStainedGlass(canvas, { width: w, height: Math.round((w * height) / width), spring: 0.3, lights, seed: 101 + variant * 977 });
      const map = new THREE.CanvasTexture(canvas);
      map.colorSpace = THREE.SRGBColorSpace;
      map.flipY = false;
      map.anisotropy = 8;
      this.bag.add(map);
      const basic = new THREE.MeshBasicNodeMaterial({ side: THREE.DoubleSide });
      basic.colorNode = texture(map, uv()).rgb.pow(1.1).mul(2.4);
      material = basic;
      this.glassCache.set(key, material);
    }
    return material;
  }

  /** A small landscape painted on a canvas, for the decorative frame left of the arch. */
  private landscapeFor(mesh: THREE.Mesh): THREE.Material {
    const canvas = document.createElement('canvas');
    drawLandscape(canvas, 512, 768, [...mesh.name].reduce((h, ch) => (h * 31 + ch.charCodeAt(0)) >>> 0, 3));
    const map = new THREE.CanvasTexture(canvas);
    map.colorSpace = THREE.SRGBColorSpace;
    map.flipY = false;
    this.bag.add(map);
    const material = new THREE.MeshStandardNodeMaterial({ roughness: 0.6 });
    material.colorNode = texture(map, uv()).rgb;
    this.bag.add(material);
    return material;
  }

  /** A warm halo on the wall behind each sconce, where its candles would light the stone. */
  private addSconceHalos(root: THREE.Object3D): void {
    const geometry = this.bag.add(new THREE.PlaneGeometry(1.8, 2.4));
    const material = new THREE.MeshBasicNodeMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide });
    const d = uv().sub(vec2(0.5, 0.42)).mul(vec2(1, 0.8)).length();
    material.colorNode = color('#ffb761').mul(float(1).sub(smoothstep(0.08, 0.5, d)).pow(1.6).mul(0.55));
    this.bag.add(material);
    root.traverse((o) => {
      if (!/^candle_sconce/.test(o.name)) return;
      const halo = new THREE.Mesh(geometry, material);
      const side = Math.sign(o.position.x);
      halo.position.set(o.position.x + side * 0.72, o.position.y + 0.3, o.position.z);
      halo.rotation.y = -side * Math.PI / 2;
      halo.renderOrder = 2;
      this.scene.add(halo);
    });
  }

  /** Warm cones on the wall under each picture light; cheaper than thirteen real spotlights. */
  private addPictureLights(root: THREE.Object3D): void {
    const geometry = this.bag.add(new THREE.PlaneGeometry(1, 1));
    const material = new THREE.MeshBasicNodeMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending });
    const local = uv();
    const fromTop = float(1).sub(local.y);
    const spread = abs(local.x.sub(0.5)).mul(2);
    const cone = smoothstep(fromTop.mul(0.75).add(0.25), fromTop.mul(0.3), spread).mul(smoothstep(1.0, 0.1, fromTop));
    material.colorNode = color('#ffd9a3').mul(cone.mul(0.55));
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

  /** Shafts of sunlight slanting in from the west windows, with a little dust drifting through. */
  private addWindowLight(root: THREE.Object3D): void {
    const geometry = this.bag.add(new THREE.BoxGeometry(3.2, 15, 1.6));
    geometry.translate(0, -7.5, 0);
    const material = new THREE.MeshBasicNodeMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide });
    const along = positionLocal.y.negate().div(15);
    const dust = smoothstep(0.62, 0.9, mx_noise_float(positionWorld.mul(1.4).add(time.mul(0.06))));
    const across = float(1).sub(smoothstep(0.45, 1.0, abs(positionLocal.x).div(1.6))).mul(float(1).sub(smoothstep(0.4, 1.0, abs(positionLocal.z).div(0.8))));
    material.colorNode = color('#ffe2b4').mul(float(1).sub(along).pow(1.6).mul(0.075).add(dust.mul(0.02))).mul(across);
    this.bag.add(material);
    const down = new THREE.Vector3(0, -1, 0);
    root.traverse((o) => {
      if (!/^window_-1_\d+_at$/.test(o.name)) return;
      const beam = new THREE.Mesh(geometry, material);
      beam.position.copy(o.position);
      beam.quaternion.setFromUnitVectors(down, new THREE.Vector3(0.62, -0.78, 0).normalize());
      beam.renderOrder = 3;
      this.scene.add(beam);
    });
  }

  /** Pools of coloured light on the floor under the west windows, in the glass's own colours. */
  private addColourPools(root: THREE.Object3D): void {
    const geometry = this.bag.add(new THREE.PlaneGeometry(4.4, 8.5));
    geometry.rotateX(-Math.PI / 2);
    const material = new THREE.MeshBasicNodeMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending });
    const cell = uv().mul(vec2(7, 13)).floor();
    const pick = fract(mx_noise_float(cell.mul(0.37).xyx).mul(4.7).add(0.5));
    const tint = mix(mix(color('#2f5fb8'), color('#b8262d'), smoothstep(0.2, 0.3, pick)), mix(color('#e0a62a'), color('#2f7c45'), smoothstep(0.7, 0.8, pick)), smoothstep(0.45, 0.55, pick));
    const edge = smoothstep(0, 0.18, uv().x).mul(smoothstep(1, 0.82, uv().x)).mul(smoothstep(0, 0.12, uv().y)).mul(smoothstep(1, 0.88, uv().y));
    material.colorNode = mix(tint, color('#fff1d8'), 0.45).mul(edge.mul(0.26));
    this.bag.add(material);
    root.traverse((o) => {
      if (!/^window_-1_\d+_at$/.test(o.name)) return;
      const pool = new THREE.Mesh(geometry, material);
      pool.position.set(o.position.x + 6.4, 0.012, o.position.z);
      pool.rotation.y = -0.18;
      pool.renderOrder = 1;
      this.scene.add(pool);
    });
  }

  /** A few warm lights where the chandeliers hang; the flames themselves are drawn bright. */
  private addCandles(root: THREE.Object3D): void {
    let count = 0;
    root.traverse((o) => {
      if (!o.name.startsWith('candle_chandelier') || count >= 6) return;
      const light = new THREE.PointLight('#ffb561', 32, 20, 2);
      light.position.copy(o.position).add(new THREE.Vector3(0, -0.6, 0));
      this.scene.add(light);
      count++;
    });
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
    if (start === end) {
      if (!crossesPedestal(from, to)) return [];
      // round the ropes along the aisle on the target's side, in the direction of travel
      const side = Math.sign(to.x || from.x || 1) < 0 ? ['W1', 'W2'] : ['E1', 'E2'];
      const ordered = from.z > to.z ? side : [...side].reverse();
      return ordered.map((id) => new THREE.Vector3(NODES[id].x, 0, NODES[id].z));
    }
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
    this.sun.position.copy(character.position).add(this.sunOffset);
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
