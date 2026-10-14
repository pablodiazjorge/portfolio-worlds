import * as THREE from 'three/webgpu';
import {
  abs,
  color,
  float,
  fract,
  hash,
  max,
  mix,
  normalize,
  positionWorld,
  positionWorldDirection,
  screenUV,
  smoothstep,
  step,
  texture,
  uniform,
  vec2,
  vec3,
} from 'three/tsl';
import { dequantizeMeshes } from '../../core/assets/dequantize';
import { loadGltf } from '../../core/assets/gltf';
import { DisposeBag, disposeObject } from '../../core/engine/dispose';
import { EngineContext, WorldScene } from '../../core/engine/world-scene';
import { CameraKey, KeyframeRig, PointerTracker } from '../../core/scroll/camera-rig';
import { ScrollDirector } from '../../core/scroll/scroll-director';

const STAGES = ['stage_1', 'stage_2', 'stage_3', 'stage_4', 'stage_5'] as const;
/** Groups that are not stages build together with one. */
const GROUP_STAGE: Record<string, number> = {
  stage_1: 0,
  stage_2: 1,
  stage_3: 2,
  stage_4: 3,
  facade: 3,
  stage_5: 4,
  interior: 4,
  site: 4,
};

const BLUEPRINT = '#1d4f91';

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));
const smooth = (a: number, b: number, v: number) => {
  const t = clamp01((v - a) / (b - a));
  return t * t * (3 - 2 * t);
};

export class TerraScene implements WorldScene {
  readonly scene = new THREE.Scene();
  readonly camera = new THREE.PerspectiveCamera(36, 1, 0.1, 400);

  private readonly bag = new DisposeBag();
  private readonly pointer: PointerTracker | null;
  private rig: KeyframeRig | null = null;
  private scroll: ScrollDirector | null = null;

  private readonly reveal = STAGES.map(() => uniform(-1));
  private readonly building = STAGES.map(() => uniform(0));
  private readonly lines = STAGES.map(() => uniform(1));
  private readonly stageRange = STAGES.map(() => ({ min: 0, max: 1 }));
  private readonly uBlueprint = uniform(1);
  private readonly uDusk = uniform(0);
  private readonly uNight = uniform(0);
  private readonly uSolid = uniform(0);

  private facade: THREE.Object3D | null = null;
  private readonly screens: { node: ReturnType<typeof texture> }[] = [];
  private readonly covers: THREE.Texture[] = [];
  private activeCover = -1;
  private readonly sun = new THREE.DirectionalLight('#ffe2b8', 2.6);
  private readonly hemi = new THREE.HemisphereLight('#cfe0ff', '#3c4a3a', 1.0);
  private readonly lamps: THREE.PointLight[] = [];

  constructor(
    private readonly ctx: EngineContext,
    private readonly coverUrls: readonly string[],
  ) {
    this.pointer = ctx.touch || ctx.reducedMotion ? null : new PointerTracker();
    this.scene.backgroundNode = this.skyNode();
    this.sun.position.set(-18, 22, 14);
    this.sun.castShadow = ctx.quality !== 'low';
    this.sun.shadow.mapSize.set(2048, 2048);
    const cam = this.sun.shadow.camera;
    cam.left = -22;
    cam.right = 22;
    cam.top = 22;
    cam.bottom = -22;
    cam.near = 1;
    cam.far = 80;
    this.sun.shadow.bias = -0.0005;
    this.sun.shadow.normalBias = 0.03;
    this.scene.add(this.sun, this.hemi);
  }

  attachScroll(source: ScrollDirector | null): void {
    this.scroll = source;
  }

  activate(): void {
    this.ctx.renderer.toneMapping = THREE.AgXToneMapping;
    this.ctx.renderer.toneMappingExposure = 1.15;
  }

  async init(onProgress: (fraction: number) => void): Promise<void> {
    const gltf = await loadGltf('models/terra/house.glb', (f) => onProgress(f * 0.9));
    const root = gltf.scene;
    dequantizeMeshes(root);
    root.updateMatrixWorld(true);
    const materials = this.materialLibrary();

    for (const [group, stage] of Object.entries(GROUP_STAGE)) {
      const node = root.getObjectByName(group);
      if (!node) continue;
      if (group === 'facade') this.facade = node;
      const box = new THREE.Box3().setFromObject(node);
      if (STAGES.includes(group as (typeof STAGES)[number])) {
        this.stageRange[stage] = { min: box.min.y - 0.05, max: box.max.y + 0.05 };
      }
      const clones = new Map<string, THREE.Material>();
      const meshes: THREE.Mesh[] = [];
      node.traverse((o) => {
        if ((o as THREE.Mesh).isMesh) meshes.push(o as THREE.Mesh);
      });
      for (const mesh of meshes) {
        const name = (mesh.material as THREE.Material).name;
        (mesh.material as THREE.Material).dispose();
        let material = clones.get(name);
        if (!material) {
          material = this.stageMaterial(materials, name, stage);
          clones.set(name, material);
          this.bag.add(material);
        }
        mesh.material = material;
        mesh.castShadow = name !== 'glass' && name !== 'light' && name !== 'water';
        mesh.receiveShadow = true;
        if (mesh.name.startsWith('screen_')) this.setupScreen(mesh);
        this.addEdges(mesh, stage);
      }
    }
    materials.forEach((m) => this.bag.add(m));

    this.scene.add(root);
    this.addGround();
    this.addLamps();
    this.rig = new KeyframeRig(this.camera, this.keys(), { damping: 2.6, swayAmount: 0.9 });
    void this.loadCovers();
    onProgress(1);
  }

  private materialLibrary(): Map<string, THREE.MeshStandardNodeMaterial> {
    const lib = new Map<string, THREE.MeshStandardNodeMaterial>();
    const add = (name: string, params: ConstructorParameters<typeof THREE.MeshStandardNodeMaterial>[0]) => {
      const m = new THREE.MeshStandardNodeMaterial(params);
      m.name = name;
      lib.set(name, m);
    };
    add('concrete', { color: '#a6a49f', roughness: 0.88 });
    add('render', { color: '#ecebe6', roughness: 0.9 });
    add('timber', { color: '#a46d47', roughness: 0.72 });
    add('steel', { color: '#22252a', roughness: 0.42, metalness: 0.6 });
    add('glass', { color: '#13202c', roughness: 0.06, metalness: 0.2 });
    add('oak', { color: '#c79c6e', roughness: 0.6 });
    add('fabric', { color: '#6c6f73', roughness: 0.95 });
    add('linen', { color: '#e6e0d5', roughness: 0.95 });
    add('screen', { color: '#0a0c0f', roughness: 0.3 });
    add('water', { color: '#3fa8c2', roughness: 0.05, metalness: 0.1 });
    add('stone', { color: '#cdc8be', roughness: 0.8 });
    add('light', { color: '#fff1d6', roughness: 0.5 });
    add('leaves', { color: '#5a8a47', roughness: 0.9, flatShading: true });
    add('bark', { color: '#5b4434', roughness: 0.95 });
    return lib;
  }

  /** A clone of the library material that only exists below the stage's reveal height. */
  private stageMaterial(lib: Map<string, THREE.MeshStandardNodeMaterial>, name: string, stage: number): THREE.Material {
    const base = lib.get(name) ?? lib.get('concrete')!;
    const material = base.clone() as THREE.MeshStandardNodeMaterial;
    const y = positionWorld.y;
    const revealY = this.reveal[stage];
    material.alphaTest = 0.5;
    material.opacityNode = step(y, revealY as never);
    const band = smoothstep(0.35, 0.0, abs(y.sub(revealY as never))).mul(this.building[stage]);
    let emissive = color('#7fd4ff').mul(band.mul(3));
    if (name === 'glass') emissive = emissive.add(color('#ffcf8a').mul(this.uNight.mul(1.4)));
    if (name === 'light') emissive = emissive.add(color('#ffd9a0').mul(this.uNight.mul(6).add(0.3)));
    if (name === 'water') emissive = emissive.add(color('#1f7fa0').mul(this.uNight.mul(0.35)));
    material.emissiveNode = emissive;
    return material;
  }

  private addEdges(mesh: THREE.Mesh, stage: number): void {
    const edges = this.bag.add(new THREE.EdgesGeometry(mesh.geometry, 28));
    const material = new THREE.LineBasicNodeMaterial({ transparent: true, depthWrite: false });
    material.colorNode = color('#e9f3ff');
    material.opacityNode = (this.lines[stage] as unknown as ReturnType<typeof float>).mul(0.85);
    this.bag.add(material);
    const segments = new THREE.LineSegments(edges, material);
    segments.renderOrder = 3;
    mesh.add(segments);
  }

  private setupScreen(mesh: THREE.Mesh): void {
    const blank = this.bag.add(new THREE.DataTexture(new Uint8Array([12, 14, 18, 255]), 1, 1));
    blank.needsUpdate = true;
    const node = texture(blank);
    const material = new THREE.MeshBasicNodeMaterial();
    material.colorNode = node.rgb.mul(1.1);
    material.alphaTest = 0.5;
    material.opacityNode = step(positionWorld.y, this.reveal[4] as never);
    this.bag.add(material);
    (mesh.material as THREE.Material).dispose();
    mesh.material = material;
    mesh.castShadow = false;
    const index = Number(mesh.name.split('_')[1]);
    this.screens[index] = { node };
  }

  private async loadCovers(): Promise<void> {
    const loader = new THREE.TextureLoader();
    const textures = await Promise.all(
      this.coverUrls.map((url) =>
        loader.loadAsync(url).then((t) => {
          t.colorSpace = THREE.SRGBColorSpace;
          t.flipY = false;
          return this.bag.add(t);
        }),
      ),
    ).catch(() => []);
    this.covers.push(...textures);
    this.showProject(Math.max(0, this.activeCover), true);
  }

  /** Puts a project cover on the middle monitor and its neighbours on the side ones. */
  showProject(index: number, force = false): void {
    if (!force && index === this.activeCover) return;
    this.activeCover = index;
    const n = this.covers.length;
    if (!n) return;
    const pick = (i: number) => this.covers[((i % n) + n) % n];
    this.screens[0]?.node && (this.screens[0].node.value = pick(index - 1));
    this.screens[1]?.node && (this.screens[1].node.value = pick(index));
    this.screens[2]?.node && (this.screens[2].node.value = pick(index + 1));
  }

  private skyNode() {
    const dir = positionWorldDirection;
    const h = dir.y;
    const day = mix(color('#f3c9a0'), color('#6f95c9'), smoothstep(-0.02, 0.5, h));
    const dusk = mix(color('#f59a6b'), color('#3d4f86'), smoothstep(-0.02, 0.45, h));
    const sky = mix(day, dusk, this.uDusk);
    const cell = normalize(dir).mul(260).floor();
    const stars = step(0.9975, hash(cell.x.add(cell.y.mul(57)).add(cell.z.mul(113)))).mul(smoothstep(0.05, 0.4, h));
    const night = mix(color('#0c1530'), color('#030612'), smoothstep(0.0, 0.6, h)).add(vec3(stars));
    const real = mix(sky, night, this.uNight);
    const uvGrid = screenUV.mul(vec2(32, 18));
    const grid = max(step(0.97, fract(uvGrid.x)), step(0.95, fract(uvGrid.y))).mul(0.08);
    const vignette = smoothstep(0.9, 0.2, screenUV.sub(0.5).length());
    const blueprint = color(BLUEPRINT).mul(vignette.mul(0.35).add(0.75)).add(grid);
    return mix(real, blueprint, this.uBlueprint);
  }

  private addGround(): void {
    const geometry = this.bag.add(new THREE.CircleGeometry(380, 96));
    geometry.rotateX(-Math.PI / 2);
    const material = new THREE.MeshStandardNodeMaterial({ roughness: 0.95 });
    const p = positionWorld.xz;
    const fine = max(step(0.96, fract(p.x)), step(0.96, fract(p.y)));
    const coarse = max(step(0.985, fract(p.x.div(5))), step(0.985, fract(p.y.div(5))));
    const lineFade = smoothstep(90, 25, p.length());
    const gridLines = max(fine.mul(0.35), coarse).mul(lineFade);
    const tile = p.mul(1.7).floor();
    const lawn = mix(color('#5f8c45'), color('#77a255'), hash(tile.x.add(tile.y.mul(91))).mul(0.4));
    material.colorNode = mix(color('#0f2f5c'), lawn, this.uSolid);
    material.emissiveNode = mix(color(BLUEPRINT).mul(0.85).add(vec3(gridLines.mul(0.5))), vec3(0), this.uSolid);
    this.bag.add(material);
    const ground = new THREE.Mesh(geometry, material);
    ground.position.y = -0.01;
    ground.receiveShadow = true;
    this.scene.add(ground);
  }

  private addLamps(): void {
    for (const [x, y, z, intensity] of [
      [-3, 6.2, 2.5, 26],
      [2, 2.8, 0.5, 30],
      [5, 0.6, 12, 18],
    ] as const) {
      const lamp = new THREE.PointLight('#ffcf8f', 0, 14, 1.8);
      lamp.position.set(x, y, z);
      lamp.userData['max'] = intensity;
      this.lamps.push(lamp);
      this.scene.add(lamp);
    }
  }

  private keys(): CameraKey[] {
    const v = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);
    return [
      { position: v(19, 14, 23), target: v(-3.2, 2.6, 0.5), fov: 34 },
      { position: v(1.5, 38, 9), target: v(-4.5, 0, 0.5), fov: 36 },
      { position: v(-16, 8.5, 17), target: v(3.8, 0.8, 0), fov: 36 },
      { position: v(17, 9.5, 15), target: v(-3.8, 2.2, 0), fov: 36 },
      { position: v(-15, 12, 18), target: v(3.6, 4, 0.5), fov: 36 },
      { position: v(16, 11, 19), target: v(-3.6, 4.4, 0.5), fov: 36 },
      { position: v(-19, 8.5, 24), target: v(4.5, 3, -0.5), fov: 38 },
      { position: v(2.2, 5.6, 15.5), target: v(-6.2, 4.9, 3.2), fov: 38 },
      { position: v(-0.4, 5.4, 9.5), target: v(-5.6, 5.0, 4.9), fov: 38 },
      { position: v(15, 3.2, 21), target: v(-4.5, 3.2, 0), fov: 38 },
    ];
  }

  update(dt: number): void {
    const rig = this.rig;
    if (!rig) return;
    const reduced = this.ctx.reducedMotion;
    const source = this.scroll;
    // a page that jumps between stops gets a cut to the stop in the same frame
    const cut = source ? !source.smooth : reduced;
    const k = source ? (cut ? source.nearest() : source.keyframe()) : 0;
    rig.update(k, dt, cut, this.pointer?.value ?? null);
    const s = rig.position;

    STAGES.forEach((_, i) => {
      const p = clamp01(s - (i + 1));
      const eased = p * p * (3 - 2 * p);
      const range = this.stageRange[i];
      this.reveal[i].value = range.min + (range.max - range.min + 0.4) * eased - (p === 0 ? 1 : 0);
      this.building[i].value = p > 0 && p < 1 ? 1 : 0;
      this.lines[i].value = 1 - eased;
    });
    this.uBlueprint.value = 1 - smooth(3.2, 6, s);
    this.uSolid.value = smooth(4.5, 6, s);
    const night = smooth(8.2, 9, s);
    this.uDusk.value = smooth(6, 7.6, s) * (1 - night);
    this.uNight.value = night;

    if (this.facade) {
      const lift = smooth(6.3, 7, s) * (1 - smooth(8.3, 9, s));
      this.facade.position.y = lift * 10;
      this.facade.position.z = lift * 3;
      this.facade.rotation.x = -lift * 0.25;
    }

    const dusk = this.uDusk.value as number;
    this.sun.intensity = 2.6 * (1 - night) * (1 - dusk * 0.45);
    // Parts that are not built yet are discarded on screen but still reach the shadow map.
    this.sun.shadow.intensity = this.uSolid.value as number;
    this.sun.color.set(dusk > 0.5 ? '#ffb27a' : '#ffe2b8');
    this.hemi.intensity = 1.0 - night * 0.75;
    for (const lamp of this.lamps) lamp.intensity = (lamp.userData['max'] as number) * Math.max(dusk * 0.6, night);
  }

  resize(width: number, height: number): void {
    if (this.rig) {
      this.rig.fitViewport(width, height);
      return;
    }
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
  }

  dispose(): void {
    this.pointer?.dispose();
    this.bag.dispose();
    disposeObject(this.scene);
    this.scene.clear();
  }
}
