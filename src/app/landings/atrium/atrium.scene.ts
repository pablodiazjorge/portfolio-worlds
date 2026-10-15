import * as THREE from 'three/webgpu';
import { abs, color, float, fract, max, min, mix, mx_noise_float, normalWorld, pmremTexture, positionLocal, positionWorld, reflector, smoothstep, texture, time, uv, vec2 } from 'three/tsl';
import { drawLandscape, drawPainting, drawStainedGlass } from './stained-glass';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { dequantizeMeshes } from '../../core/assets/dequantize';
import { loadGltf } from '../../core/assets/gltf';
import { DisposeBag, disposeObject } from '../../core/engine/dispose';
import { EngineContext, WorldScene } from '../../core/engine/world-scene';
import { Character, FloorBox, MoveInput } from './character';
import { drawAbout, drawBadge, drawContact, drawFace, drawLabel, drawLightbox, drawSign, loadMuseumFonts, MuseumCopy, PanelTexture, drawPlaque, quadAspect } from './museum-textures';

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
  W3: { x: -2.4, z: -33.75, rooms: ['second'] },
  E3: { x: 2.4, z: -33.75, rooms: ['second'] },
};
const EDGES: [string, string][] = [
  ['S', 'W1'], ['S', 'E1'], ['W1', 'W2'], ['E1', 'E2'], ['W2', 'A'], ['E2', 'A'], ['A', 'W3'], ['A', 'E3'],
];

const roomAt = (_x: number, z: number): Room => (z > -18.5 ? 'hall' : 'second');

/** The roped pedestal in the nave and the table case in the far room, which a straight walk must go round. */
const BLOCKS: FloorBox[] = [
  { minX: -2.9, maxX: 2.9, minZ: -9.55, maxZ: -4.45 },
  { minX: -1.4, maxX: 1.4, minZ: -34.8, maxZ: -32.7 },
];

const crossesBlocks = (from: THREE.Vector3, to: THREE.Vector3): boolean => BLOCKS.some((box) => crossesBox(from, to, box));

function crossesBox(from: THREE.Vector3, to: THREE.Vector3, box: FloorBox): boolean {
  // a 2D segment against the box, by clipping the parameter range on each axis
  let t0 = 0;
  let t1 = 1;
  for (const [a, b, lo, hi] of [
    [from.x, to.x, box.minX, box.maxX],
    [from.z, to.z, box.minZ, box.maxZ],
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
  private badge: PanelTexture | null = null;
  private face: PanelTexture | null = null;
  private envTexture: THREE.Texture | null = null;
  private blinkAt = 3;
  private eyesOpen = true;
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
  private readonly sun = new THREE.DirectionalLight('#ffb868', 10);
  private readonly sunOffset = new THREE.Vector3(-12, 7.5, 3);
  private readonly glassCache = new Map<string, THREE.Material>();
  private readonly paintings = new Map<number, HTMLCanvasElement>();
  private readonly paintingMaps = new Map<number, THREE.CanvasTexture>();
  private readonly covers = new Map<string, HTMLImageElement>();
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
    this.scene.add(new THREE.HemisphereLight('#a9b4cc', '#3a2a1e', 0.12));
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
    this.sun.shadow.bias = -0.0004;
    this.sun.shadow.normalBias = 0.02;
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

    this.dressVisitor(robot.scene);
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
    this.envTexture = target.texture;
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

    // a cream marble (Poly Haven, CC0) projected from the three axes, so nothing needs UVs
    const texLoader = new THREE.TextureLoader();
    const marbleMap = this.bag.add(texLoader.load('textures/atrium/marble-diffuse.webp'));
    const marbleRough = this.bag.add(texLoader.load('textures/atrium/marble-rough.webp'));
    for (const t of [marbleMap, marbleRough]) {
      t.wrapS = t.wrapT = THREE.RepeatWrapping;
      t.anisotropy = 8;
    }
    marbleMap.colorSpace = THREE.SRGBColorSpace;
    const triplanar = (map: THREE.Texture, scale: number) => {
      const q = positionWorld.mul(scale);
      const n = normalWorld.abs();
      const w = n.div(n.x.add(n.y).add(n.z).add(0.0001));
      return texture(map, q.zy).rgb.mul(w.x).add(texture(map, q.xz).rgb.mul(w.y)).add(texture(map, q.xy).rgb.mul(w.z));
    };
    // ashlar joints: courses of 0.9 m and blocks of 1.4 m along whichever way the wall runs
    const alongWall = mix(positionWorld.x, positionWorld.z, normalWorld.abs().x);
    const course = abs(fract(positionWorld.y.div(0.9)).sub(0.5)).negate().add(0.5).mul(0.9);
    const block = abs(fract(alongWall.div(1.4).add(positionWorld.y.div(0.9).floor().mul(0.5))).sub(0.5)).negate().add(0.5).mul(1.4);
    const ashlar = float(1).sub(smoothstep(0.006, 0.02, min(course, block)));
    const stoneTex = triplanar(marbleMap, 1 / 1.5);

    // cream stone with a little dirt in the grain; the mouldings a shade darker
    const stone = std('stone', { roughness: 0.7 });
    stone.colorNode = mix(stoneTex.mul(color('#f3e9d6')), color('#b8a98f'), ashlar.mul(0.55)).mul(mix(0.94, 1.04, grain));
    stone.roughnessNode = mix(float(0.5), float(0.85), triplanar(marbleRough, 1 / 1.5).r);
    const stoneDark = std('stone_dark', { roughness: 0.75 });
    stoneDark.colorNode = stoneTex.mul(color('#d7c8ae')).mul(mix(0.92, 1.04, grain));
    const vault = std('vault', { roughness: 0.9 });
    const vaultTex = triplanar(marbleMap, 1 / 2.6);
    // the webs darken towards the crown, where the candlelight does not reach
    vault.colorNode = vaultTex.mul(mix(color('#f6ede0'), color('#d2c4ad'), smoothstep(14, 22.5, positionWorld.y)));
    std('rib', { color: '#9c8a6a', roughness: 0.85 });
    std('panel_blue', { color: '#233459', roughness: 0.8 });
    std('gold', { color: '#d8b05a', roughness: 0.28, metalness: 1 });
    std('brass', { color: '#b08a45', roughness: 0.34, metalness: 1 });
    std('crimson', { color: '#7a1f2e', roughness: 0.85 });
    std('wood', { color: '#3b2719', roughness: 0.55 });
    std('velvet', { color: '#a1202f', roughness: 0.95 });
    const marble = std('marble', { roughness: 0.28 });
    marble.colorNode = triplanar(marbleMap, 1 / 1.2).mul(color('#fbf7f0'));
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
    const floor = std('floor', { roughness: 0.2 });
    // the studio environment map washes the polished floor white at grazing angles, and a material cannot
    // scale the scene environment on its own, so the floor samples it through a node of its own, dimmed
    if (this.envTexture) floor.envNode = pmremTexture(this.envTexture).mul(0.18);
    const veins = smoothstep(0.48, 0.92, mx_noise_float(positionWorld.mul(vec2(0.9, 0.35).xyx)).mul(0.5).add(0.5));
    const floorTex = texture(marbleMap, p.div(2.4).add(vec2(0.13, 0.41))).rgb;
    const base = floorTex.mul(mix(color('#e9dfcb'), color('#cbbda5'), veins.mul(0.6)));
    const turned = vec2(p.x.add(p.y), p.x.sub(p.y)).div(8.0);
    const cell = turned.floor();
    const toLine = abs(fract(turned).sub(0.5));
    const nearest = min(toLine.x, toLine.y);
    const band = float(1).sub(smoothstep(0.038, 0.05, nearest));
    const inner = smoothstep(0.27, 0.29, nearest).mul(float(1).sub(smoothstep(0.33, 0.35, nearest)));
    const core = smoothstep(0.42, 0.45, nearest);
    const checker = fract(cell.x.add(cell.y).mul(0.5)).mul(2);
    const field = mix(base, floorTex.mul(mix(color('#c9bca6'), color('#b2a692'), veins.mul(0.5))), checker);
    const border = float(1).sub(smoothstep(0.1, 0.2, abs(abs(p.x).sub(5.55))));
    const inlay = max(band, border);
    const stoneFloor = mix(mix(mix(field, color('#7a2f33'), inner.mul(0.85)), color('#9a9388'), core.mul(checker).mul(0.6)), color('#4f1016'), inlay.mul(0.96));
    floor.roughnessNode = mix(texture(marbleRough, p.div(2.4)).r.mul(0.35).add(0.06), float(0.3), inlay);
    if (this.ctx.quality === 'low') {
      floor.colorNode = stoneFloor;
    } else {
      // the polish: the hall mirrored in the marble, dimmer on the inlay
      const mirror = reflector({ resolutionScale: this.ctx.quality === 'high' ? 0.35 : 0.25 });
      mirror.target.rotateX(-Math.PI / 2);
      mirror.target.position.y = 0.002;
      this.scene.add(mirror.target);
      this.bag.defer(() => mirror.dispose());
      // the mirrored windows are far brighter than white, so the reflection is capped before it is mixed in
      floor.colorNode = mix(stoneFloor, min(mirror.rgb.mul(0.9), float(1.1)), mix(float(0.18), float(0.04), inlay));
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
        const art = new THREE.MeshBasicNodeMaterial();
        const canvas = document.createElement('canvas');
        this.paintings.set(index, canvas);
        const map = new THREE.CanvasTexture(canvas);
        map.colorSpace = THREE.SRGBColorSpace;
        map.flipY = false;
        map.anisotropy = 8;
        this.bag.add(map);
        this.paintingMaps.set(index, map);
        art.colorNode = texture(map).rgb.mul(0.95);
        material = this.bag.add(art);
        mesh.userData['exhibit'] = `project-${index}`;
        this.clickables.push(mesh);
      } else if (name.startsWith('label_') || name.startsWith('exp_') || name.startsWith('sign_') || name.startsWith('plaque_') || name === 'about_panel' || name === 'contact_panel') {
        // the canvas takes the proportions of the quad it is painted on, so nothing is stretched
        const heights: Record<string, number> = { label: 450, exp: 648, sign: 256, plaque: 256, about: 480, contact: 568 };
        const key = name.split('_')[0];
        const h = heights[key] ?? 512;
        const panel = new PanelTexture(Math.round(h * quadAspect(mesh.geometry)), h);
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
      } else if (source.name === 'shadow_patch') {
        // the contact shadow under the statue: a soft dark disc that fades out at its edge
        const patch = new THREE.MeshBasicNodeMaterial({ transparent: true, depthWrite: false });
        patch.colorNode = color('#1a110a');
        patch.opacityNode = smoothstep(0.3, 1.0, uv().sub(0.5).mul(2).length()).oneMinus().mul(0.6);
        material = this.bag.add(patch);
      } else if (source.name === 'statue_tex') {
        // the generated statue keeps its baked texture, lifted towards pale stone and matte
        const baked = (source as THREE.MeshStandardMaterial).map;
        const stone = new THREE.MeshStandardNodeMaterial({ roughness: 0.8, metalness: 0 });
        if (baked) stone.colorNode = texture(baked).rgb.mul(1.3);
        material = this.bag.add(stone);
      } else {
        material = lib.get(source.name);
      }
      if (material) {
        source.dispose();
        mesh.material = material;
      }
      mesh.receiveShadow = source.name !== 'glass' && source.name !== 'flame';
      mesh.castShadow = /^(marble|statue|statue_tex|plinth|wood|stone|stone_dark)$/.test(source.name);
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
      basic.colorNode = texture(map, uv()).rgb.pow(1.1).mul(2.9);
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
    const geometry = this.bag.add(new THREE.PlaneGeometry(0.9, 2.0));
    const material = new THREE.MeshBasicNodeMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide });
    const d = uv().sub(vec2(0.5, 0.42)).mul(vec2(1, 0.8)).length();
    material.colorNode = color('#ffb761').mul(float(1).sub(smoothstep(0.08, 0.5, d)).pow(1.6).mul(0.55));
    this.bag.add(material);
    root.traverse((o) => {
      if (!/^candle_sconce/.test(o.name)) return;
      const halo = new THREE.Mesh(geometry, material);
      const side = Math.sign(o.position.x);
      halo.position.set(o.position.x + side * 0.11, o.position.y + 0.3, o.position.z);
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
      // the glow sits between the wall and the picture, so the canvas and frame hide it and it lights only the panel around them
      glow.position.copy(exhibit.focus).addScaledVector(normal, -0.012);
      // the cone opens from the underside of the lamp hood, 0.18 m under the light point
      glow.position.y = light.position.y - 0.18 - glow.scale.y / 2;
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
    material.colorNode = color('#ffcf8a').mul(float(1).sub(along).pow(1.6).mul(0.045).add(dust.mul(0.014))).mul(across);
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
    material.colorNode = mix(tint, color('#fff1d8'), 0.45).mul(edge.mul(0.2));
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
      this.paint(i, project);
    });
    experience.forEach((job, i) => {
      const panel = this.panels.get(`exp_${i}`);
      if (panel) drawLightbox(panel, job);
      const plaque = this.panels.get(`plaque_exp_${i}`);
      if (plaque) drawPlaque(plaque, job);
    });
    const about = this.panels.get('about_panel');
    if (about) drawAbout(about, portfolio);
    const contact = this.panels.get('contact_panel');
    if (contact) drawContact(contact, this.copy.contactTitle, portfolio);
    // the sign over the arch names the room beyond it, where the experience is; the lectern says what it is for
    const hall = this.panels.get('sign_hall');
    if (hall) drawSign(hall, this.copy.experienceSign);
    const lectern = this.panels.get('sign_contact');
    if (lectern) drawSign(lectern, this.copy.contactTitle);
  }

  /** Paints one project's picture: a landscape in oils with its mark in a roundel and a cartouche. */
  private paint(index: number, project: { title: string; tagline: string; cover: string }): void {
    const canvas = this.paintings.get(index);
    const map = this.paintingMaps.get(index);
    if (!canvas || !map) return;
    const seed = 41 + index * 131;
    let cover = this.covers.get(project.cover) ?? null;
    if (!cover) {
      const image = new Image();
      image.onload = () => {
        this.covers.set(project.cover, image);
        drawPainting(canvas, 1024, 670, project.title, project.tagline, seed, image);
        map.needsUpdate = true;
      };
      image.src = project.cover;
      cover = null;
    }
    drawPainting(canvas, 1024, 670, project.title, project.tagline, seed, cover);
    map.needsUpdate = true;
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
      if (!crossesBlocks(from, to)) return [];
      // in the far room, round the table case by its side; in the nave, round the ropes along the
      // aisle on the target's side, in the direction of travel
      const west = Math.sign(to.x || from.x || 1) < 0;
      const side = start === 'second' ? [west ? 'W3' : 'E3'] : west ? ['W1', 'W2'] : ['E1', 'E2'];
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
    const goal = nearest(to, end);
    const distance = new Map<string, number>([[goal, 0]]);
    const towardsGoal = new Map<string, string>();
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
      if (!current) break;
      open.delete(current);
      for (const [a, b] of EDGES) {
        const next = a === current ? b : b === current ? a : null;
        if (!next || !open.has(next)) continue;
        const step = Math.hypot(NODES[a].x - NODES[b].x, NODES[a].z - NODES[b].z);
        if (best + step < (distance.get(next) ?? Infinity)) {
          distance.set(next, best + step);
          towardsGoal.set(next, current);
        }
      }
    }
    let source = '';
    let bestTotal = Infinity;
    for (const [id, node] of Object.entries(NODES)) {
      if (!node.rooms.includes(start) || !distance.has(id)) continue;
      const point = new THREE.Vector3(node.x, 0, node.z);
      const total = from.distanceTo(point) + distance.get(id)! + (crossesBlocks(from, point) ? 100 : 0);
      if (total < bestTotal) {
        bestTotal = total;
        source = id;
      }
    }
    const path: THREE.Vector3[] = [];
    for (let id: string | undefined = source; id; id = towardsGoal.get(id)) {
      path.push(new THREE.Vector3(NODES[id].x, 0, NODES[id].z));
      if (id === goal) break;
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
    this.blink(elapsed);
  }

  /** The visitor's face: a canvas on its monitor, redrawn to blink now and then. */
  private dressVisitor(model: THREE.Object3D): void {
    const panel = new PanelTexture(256, 176);
    this.face = this.bag.add(panel);
    drawFace(panel, true);
    const screen = new THREE.MeshBasicNodeMaterial();
    screen.colorNode = texture(panel.texture).rgb;
    this.bag.add(screen);
    // the prize badge on the chest plate: a rosette painted once
    const badgePanel = new PanelTexture(256, 290);
    this.badge = this.bag.add(badgePanel);
    drawBadge(badgePanel, 'best robot');
    const badge = new THREE.MeshStandardNodeMaterial({ roughness: 0.5, metalness: 0.1, alphaTest: 0.5 });
    const badgeTex = texture(badgePanel.texture);
    badge.colorNode = badgeTex.rgb;
    badge.opacityNode = badgeTex.a;
    this.bag.add(badge);
    model.traverse((o) => {
      const mesh = o as THREE.Mesh;
      if (!mesh.isMesh) return;
      const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
      const replaced = materials.map((m) => (m.name === 'visitor_screen' ? screen : m.name === 'visitor_badge' ? badge : m));
      mesh.material = Array.isArray(mesh.material) ? replaced : replaced[0];
    });
  }

  private blink(elapsed: number): void {
    if (!this.face || elapsed < this.blinkAt) return;
    this.eyesOpen = !this.eyesOpen;
    drawFace(this.face, this.eyesOpen);
    this.blinkAt = elapsed + (this.eyesOpen ? 2.5 + Math.random() * 3 : 0.14);
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
