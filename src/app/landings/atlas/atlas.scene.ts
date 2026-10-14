import * as THREE from 'three/webgpu';
import {
  cameraPosition,
  dot,
  float,
  hash,
  instanceIndex,
  max,
  mix,
  mx_noise_float,
  normalize,
  positionLocal,
  positionWorld,
  positionWorldDirection,
  reflect,
  smoothstep,
  time,
  uniform,
  uv,
  vec2,
  vec3,
} from 'three/tsl';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { loadGltf } from '../../core/assets/gltf';
import { DisposeBag, disposeObject } from '../../core/engine/dispose';
import { EngineContext, WorldScene } from '../../core/engine/world-scene';
import { CameraKey, KeyframeRig, PointerTracker } from '../../core/scroll/camera-rig';
import { HeightField } from '../../core/scroll/height-field';

export interface ScrollSource {
  keyframe(): number;
  nearest(): number;
}

interface SkyStop {
  t: number;
  zenith: THREE.Color;
  horizon: THREE.Color;
  ground: THREE.Color;
  fog: THREE.Color;
  sun: THREE.Color;
  hemiSky: THREE.Color;
  hemiGround: THREE.Color;
  elevation: number;
  sunIntensity: number;
  hemiIntensity: number;
  mist: number;
}

const stop = (
  t: number,
  zenith: string,
  horizon: string,
  ground: string,
  fog: string,
  sun: string,
  hemiSky: string,
  hemiGround: string,
  elevation: number,
  sunIntensity: number,
  hemiIntensity: number,
  mist: number,
): SkyStop => ({
  t,
  zenith: new THREE.Color(zenith),
  horizon: new THREE.Color(horizon),
  ground: new THREE.Color(ground),
  fog: new THREE.Color(fog),
  sun: new THREE.Color(sun),
  hemiSky: new THREE.Color(hemiSky),
  hemiGround: new THREE.Color(hemiGround),
  elevation,
  sunIntensity,
  hemiIntensity,
  mist,
});

/** Time of day along the climb: blue hour at the trailhead, full morning on the summit. */
const SKY: SkyStop[] = [
  stop(0, '#18224a', '#f0a588', '#2b2a45', '#a68aa3', '#ff9a68', '#7a80bd', '#4a3c52', 1.5, 2.5, 1.35, 1),
  stop(0.45, '#2f58a0', '#f7c595', '#3b3b55', '#b9a3ad', '#ffc690', '#93a3d6', '#5a5060', 11, 3.1, 1.4, 0.55),
  stop(1, '#3a78c9', '#cfe2f1', '#5a6a80', '#b7c9dc', '#fff0d8', '#a9c8ec', '#5b6a4b', 30, 3.0, 1.2, 0.1),
];

const SUN_AZIMUTH = THREE.MathUtils.degToRad(22);

export class AtlasScene implements WorldScene {
  readonly scene = new THREE.Scene();
  readonly camera = new THREE.PerspectiveCamera(42, 1, 0.3, 2400);

  private readonly bag = new DisposeBag();
  private readonly pointer: PointerTracker | null;
  private rig: KeyframeRig | null = null;
  private scroll: ScrollSource | null = null;
  private ground: HeightField | null = null;

  private readonly sun = new THREE.DirectionalLight('#ffffff', 2);
  private readonly hemi = new THREE.HemisphereLight('#ffffff', '#444444', 1);
  private readonly fog = new THREE.Fog('#a68aa3', 130, 780);
  private fire: THREE.Object3D | null = null;
  private fireLight: THREE.PointLight | null = null;
  private beacon: THREE.Mesh | null = null;
  private clouds: THREE.Group | null = null;

  private readonly uZenith = uniform(new THREE.Color());
  private readonly uHorizon = uniform(new THREE.Color());
  private readonly uGround = uniform(new THREE.Color());
  private readonly uSun = uniform(new THREE.Color());
  private readonly uSunDir = uniform(new THREE.Vector3(0, 1, 0));
  private readonly uMist = uniform(1);

  private readonly sunDir = new THREE.Vector3();
  private readonly lightDir = new THREE.Vector3();

  constructor(private readonly ctx: EngineContext) {
    this.pointer = ctx.touch || ctx.reducedMotion ? null : new PointerTracker();
    this.scene.fog = this.fog;
    this.scene.add(this.hemi, this.sun, this.sun.target);
    this.sun.castShadow = ctx.quality !== 'low';
    const shadowSize = ctx.quality === 'high' ? 2048 : 1024;
    this.sun.shadow.mapSize.set(shadowSize, shadowSize);
    const cam = this.sun.shadow.camera;
    cam.left = -38;
    cam.right = 38;
    cam.top = 38;
    cam.bottom = -38;
    cam.near = 1;
    cam.far = 260;
    this.sun.shadow.bias = -0.0006;
    this.sun.shadow.normalBias = 0.04;
    this.scene.backgroundNode = this.skyNode();
  }

  attachScroll(source: ScrollSource | null): void {
    this.scroll = source;
  }

  async init(onProgress: (fraction: number) => void): Promise<void> {
    const gltf = await loadGltf('models/atlas/valley.glb', onProgress);
    const root = gltf.scene;
    const anchors = new Map<string, THREE.Vector3>();
    let waterLevel = 1.2;
    const found: { terrain?: THREE.Mesh } = {};

    root.traverse((object) => {
      if (object.name.startsWith('anchor_')) anchors.set(object.name.slice(7), object.position.clone());
      if (object.name === 'water') waterLevel = object.position.y;
      const mesh = object as THREE.Mesh;
      if (!mesh.isMesh) return;
      const material = mesh.material as THREE.MeshStandardMaterial;
      const name = material.name ?? '';
      if (mesh.name === 'horizon') {
        material.flatShading = true;
        return;
      }
      mesh.castShadow = this.sun.castShadow && name !== 'terrain' && name !== 'trail';
      mesh.receiveShadow = this.sun.castShadow;
      if (name === 'terrain') {
        mesh.geometry.computeVertexNormals();
        material.flatShading = true;
        found.terrain = mesh;
      } else if (name.startsWith('pine_foliage')) {
        mesh.geometry.computeBoundingBox();
        mesh.material = this.foliageMaterial(material.color, mesh.geometry.boundingBox?.max.y ?? 1);
        material.dispose();
      } else if (name === 'trail') {
        material.polygonOffset = true;
        material.polygonOffsetFactor = -2;
        material.polygonOffsetUnits = -2;
      } else {
        material.flatShading = name !== 'observatory_white';
      }
      if (mesh.name === 'fire') this.fire = mesh;
      if (mesh.name === 'beacon') this.beacon = mesh;
      if (mesh.name === 'fire' || mesh.name === 'beacon') mesh.userData['baseScale'] = mesh.scale.clone();
    });
    this.scene.add(root);
    root.updateMatrixWorld(true);
    if (found.terrain) this.ground = new HeightField(found.terrain);

    if (this.fire) {
      this.fireLight = new THREE.PointLight('#ff9a4a', 30, 16, 1.6);
      this.fireLight.position.copy(this.fire.position).add(new THREE.Vector3(0, 0.6, 0));
      this.scene.add(this.fireLight);
    }

    this.addWater(waterLevel);
    this.addMist(waterLevel, anchors.get('lake') ?? new THREE.Vector3(-6, waterLevel, 62));
    this.addClouds();
    this.rig = new KeyframeRig(this.camera, this.keys(anchors), { damping: 2.6, swayAmount: 1.6 });
    this.clearTreesAlong(root, this.rig.samplePath(240));
    this.applySky(0);
    onProgress(1);
  }

  activate(): void {
    this.ctx.renderer.toneMappingExposure = 1.12;
  }

  /** Hides the trees that would sit right in front of the lens somewhere along the camera path. */
  private clearTreesAlong(root: THREE.Object3D, path: THREE.Vector3[]): void {
    const instance = new THREE.Matrix4();
    const world = new THREE.Matrix4();
    const position = new THREE.Vector3();
    const hidden = new THREE.Matrix4().makeScale(0, 0, 0);
    root.traverse((object) => {
      const mesh = object as THREE.InstancedMesh;
      if (!mesh.isInstancedMesh) return;
      let changed = false;
      for (let i = 0; i < mesh.count; i++) {
        mesh.getMatrixAt(i, instance);
        world.multiplyMatrices(mesh.matrixWorld, instance);
        position.setFromMatrixPosition(world);
        for (const point of path) {
          const dx = point.x - position.x;
          const dz = point.z - position.z;
          if (dx * dx + dz * dz < 36 && point.y - position.y < 14) {
            mesh.setMatrixAt(i, hidden);
            changed = true;
            break;
          }
        }
      }
      if (changed) mesh.instanceMatrix.needsUpdate = true;
    });
  }

  private groundAt(x: number, z: number): number {
    return this.ground?.at(x, z) ?? 0;
  }

  /**
   * Camera keys for every stop. Camps are framed from behind on the trail, looking up towards
   * the next camp, with the subject pushed to the half of the screen the text panel leaves free
   * (`panel`: -1 panel on the right, 1 panel on the left, 0 centred).
   */
  private keys(a: Map<string, THREE.Vector3>): CameraKey[] {
    const at = (name: string) => a.get(name)?.clone() ?? new THREE.Vector3();
    const up = new THREE.Vector3(0, 1, 0);
    const lifted = (p: THREE.Vector3, clearance: number) => {
      p.y = Math.max(p.y, this.groundAt(p.x, p.z) + clearance);
      return p;
    };
    const frame = (
      name: string,
      toward: string,
      options: { back: number; side: number; height: number; panel: number; fov?: number; shift?: number },
    ): CameraKey => {
      const site = at(name);
      const ahead = at(toward).sub(site).setY(0).normalize();
      const side = new THREE.Vector3().crossVectors(ahead, up).normalize();
      const position = lifted(
        site.clone().addScaledVector(ahead, -options.back).addScaledVector(side, options.side).add(new THREE.Vector3(0, options.height, 0)),
        3.5,
      );
      const focus = site.clone().add(new THREE.Vector3(0, 1.2, 0));
      const view = focus.clone().sub(position).setY(0).normalize();
      const right = new THREE.Vector3().crossVectors(view, up).normalize();
      const target = focus.addScaledVector(right, -options.panel * (options.shift ?? 5.5));
      return { position, target, fov: options.fov ?? 38 };
    };

    const ridge = at('ridge');
    const summit = at('summit');
    return [
      { position: new THREE.Vector3(-78, 112, 262), target: new THREE.Vector3(26, 26, -34), fov: 40 },
      frame('base', 'camp_1', { back: 17, side: -9, height: 9, panel: -1, fov: 44, shift: 6 }),
      frame('camp_1', 'camp_2', { back: 14, side: 6, height: 6, panel: 1 }),
      frame('camp_2', 'camp_3', { back: 14, side: -6, height: 6.5, panel: -1 }),
      frame('camp_3', 'camp_4', { back: 14, side: 6, height: 7, panel: 1 }),
      frame('camp_4', 'camp_5', { back: 14, side: -6, height: 7, panel: -1 }),
      frame('camp_5', 'ridge', { back: 14, side: 6, height: 7, panel: 1 }),
      {
        position: lifted(ridge.clone().add(new THREE.Vector3(4, 5, -7)), 4),
        target: new THREE.Vector3(-24, 18, 70),
        fov: 52,
      },
      {
        position: lifted(ridge.clone().add(new THREE.Vector3(-4, 6, -4)), 4),
        target: new THREE.Vector3(-70, 24, 20),
        fov: 50,
      },
      {
        position: lifted(summit.clone().add(new THREE.Vector3(-17, 7, 12)), 5),
        target: summit.clone().add(new THREE.Vector3(-6, 2.5, 3)),
        fov: 40,
      },
    ];
  }

  private skyNode() {
    const dir = positionWorldDirection;
    const h = dir.y;
    const above = mix(this.uHorizon, this.uZenith, smoothstep(0.0, 0.62, h).pow(0.75));
    const below = mix(this.uGround, this.uHorizon, smoothstep(-0.22, 0.0, h));
    const base = mix(below, above, smoothstep(-0.005, 0.005, h));
    const sunDot = max(dot(dir, this.uSunDir), 0.0);
    const halo = sunDot.pow(5).mul(0.32).add(sunDot.pow(48).mul(0.6));
    const disk = smoothstep(0.9993, 0.9997, sunDot).mul(9);
    return base.add(this.uSun.mul(halo.add(disk)));
  }

  /**
   * Pine foliage that sways in the wind. Positions are quantized, so the bend is measured as a
   * fraction of the mesh's own height rather than in scene units.
   */
  private foliageMaterial(source: THREE.Color, height: number): THREE.MeshStandardNodeMaterial {
    const material = new THREE.MeshStandardNodeMaterial({ color: source, roughness: 0.92, flatShading: true });
    const phase = hash(instanceIndex).mul(6.283);
    const level = positionLocal.y.div(height).clamp(0, 1);
    const bend = level.mul(level).mul(height * 0.045);
    const sway = time.mul(1.35).add(phase).sin().mul(bend);
    const flutter = time.mul(3.1).add(phase.mul(2)).sin().mul(bend.mul(0.25));
    material.positionNode = positionLocal.add(vec3(sway, 0, flutter));
    return material;
  }

  private addWater(level: number): void {
    const geometry = this.bag.add(new THREE.PlaneGeometry(440, 440, 1, 1));
    geometry.rotateX(-Math.PI / 2);
    const material = new THREE.MeshBasicNodeMaterial();
    const p = positionWorld.xz;
    const ripple = vec2(
      mx_noise_float(p.mul(0.32).add(time.mul(0.12))),
      mx_noise_float(p.mul(0.32).sub(time.mul(0.1)).add(17.3)),
    );
    const normal = normalize(vec3(ripple.x.mul(0.09), 1, ripple.y.mul(0.09)));
    const view = normalize(cameraPosition.sub(positionWorld));
    const fresnel = float(1).sub(max(dot(normal, view), 0)).pow(3.5);
    const reflected = reflect(view.negate(), normal);
    const glint = max(dot(reflected, this.uSunDir), 0).pow(260).mul(6);
    const deep = vec3(0.03, 0.09, 0.14);
    const sky = mix(this.uHorizon, this.uZenith, 0.35);
    material.colorNode = mix(deep, sky, fresnel.mul(0.8).add(0.12)).add(this.uSun.mul(glint));
    const water = new THREE.Mesh(geometry, material);
    water.position.y = level;
    water.receiveShadow = false;
    this.scene.add(water);
  }

  private addMist(level: number, lake: THREE.Vector3): void {
    const geometry = this.bag.add(new THREE.PlaneGeometry(1, 1, 1, 1));
    geometry.rotateX(-Math.PI / 2);
    const material = new THREE.MeshBasicNodeMaterial({ transparent: true, depthWrite: false });
    const local = uv().sub(0.5);
    const edge = float(1).sub(smoothstep(0.12, 0.5, local.length()));
    const p = positionWorld.xz;
    const wisps = mx_noise_float(p.mul(0.03).add(time.mul(0.012)))
      .mul(0.65)
      .add(mx_noise_float(p.mul(0.09).sub(time.mul(0.02))).mul(0.35));
    const drift = smoothstep(0.05, 0.6, wisps);
    material.colorNode = mix(this.uHorizon, vec3(1, 1, 1), 0.45);
    material.opacityNode = edge.mul(drift).mul(this.uMist).mul(0.32);
    material.fog = true;
    const patches: [number, number, number, number, number][] = [
      [lake.x, 5.5, lake.z, 150, 70],
      [lake.x + 20, 9, lake.z + 70, 180, 80],
      [lake.x - 10, 7, lake.z - 70, 160, 70],
      [lake.x + 30, 13, lake.z - 140, 200, 90],
    ];
    for (const [x, y, z, w, d] of patches) {
      const mist = new THREE.Mesh(geometry, material);
      mist.position.set(x, y + level, z);
      mist.scale.set(w, 1, d);
      mist.renderOrder = 2;
      this.scene.add(mist);
    }
  }

  private addClouds(): void {
    const pieces: THREE.BufferGeometry[] = [];
    const random = mulberry32(11);
    const material = new THREE.MeshStandardNodeMaterial({ color: '#ffffff', roughness: 1, flatShading: true });
    material.emissiveNode = mix(this.uHorizon, vec3(1, 1, 1), 0.35).mul(0.42);
    this.clouds = new THREE.Group();
    for (let c = 0; c < 16; c++) {
      pieces.length = 0;
      const puffs = 6 + Math.floor(random() * 6);
      for (let i = 0; i < puffs; i++) {
        const centre = 1 - Math.abs(i / (puffs - 1) - 0.5) * 2;
        const r = 2.4 + random() * 2.5 + centre * 3;
        const g = new THREE.IcosahedronGeometry(r, 1);
        g.scale(1, 0.7, 0.9);
        g.translate((i - puffs / 2) * 3.4 + random() * 1.6, centre * 1.8 + random() * 1.2, random() * 5 - 2.5);
        pieces.push(g);
      }
      const merged = mergeGeometries(pieces);
      pieces.forEach((g) => g.dispose());
      if (!merged) continue;
      const position = merged.getAttribute('position');
      for (let i = 0; i < position.count; i++) {
        if (position.getY(i) < 0) position.setY(i, position.getY(i) * 0.2);
      }
      merged.computeVertexNormals();
      this.bag.add(merged);
      const cloud = new THREE.Mesh(merged, material);
      const angle = random() * Math.PI * 2;
      const radius = 90 + random() * 210;
      cloud.position.set(Math.cos(angle) * radius + 20, 96 + random() * 60, Math.sin(angle) * radius - 40);
      cloud.scale.setScalar(0.8 + random() * 1.1);
      cloud.userData['speed'] = 0.6 + random() * 0.8;
      this.clouds.add(cloud);
    }
    this.scene.add(this.clouds);
  }

  private applySky(t: number): void {
    let i = 0;
    while (i < SKY.length - 2 && t > SKY[i + 1].t) i++;
    const a = SKY[i];
    const b = SKY[i + 1];
    const f = THREE.MathUtils.clamp((t - a.t) / (b.t - a.t), 0, 1);
    const lerpColor = (target: THREE.Color, key: keyof SkyStop) =>
      target.copy(a[key] as THREE.Color).lerp(b[key] as THREE.Color, f);

    lerpColor(this.uZenith.value as THREE.Color, 'zenith');
    lerpColor(this.uHorizon.value as THREE.Color, 'horizon');
    lerpColor(this.uGround.value as THREE.Color, 'ground');
    lerpColor(this.uSun.value as THREE.Color, 'sun');
    lerpColor(this.fog.color, 'fog');
    lerpColor(this.sun.color, 'sun');
    lerpColor(this.hemi.color, 'hemiSky');
    lerpColor(this.hemi.groundColor, 'hemiGround');
    this.sun.intensity = THREE.MathUtils.lerp(a.sunIntensity, b.sunIntensity, f);
    this.hemi.intensity = THREE.MathUtils.lerp(a.hemiIntensity, b.hemiIntensity, f);
    this.uMist.value = THREE.MathUtils.lerp(a.mist, b.mist, f);

    const elevation = THREE.MathUtils.degToRad(THREE.MathUtils.lerp(a.elevation, b.elevation, f));
    this.sunDir
      .set(Math.cos(elevation) * Math.cos(SUN_AZIMUTH), Math.sin(elevation), Math.cos(elevation) * Math.sin(SUN_AZIMUTH))
      .normalize();
    (this.uSunDir.value as THREE.Vector3).copy(this.sunDir);

    // Shadows from a grazing sun turn into long streaks, so the light itself never drops below 16°.
    const lightElevation = Math.max(elevation, THREE.MathUtils.degToRad(16));
    this.lightDir
      .set(
        Math.cos(lightElevation) * Math.cos(SUN_AZIMUTH),
        Math.sin(lightElevation),
        Math.cos(lightElevation) * Math.sin(SUN_AZIMUTH),
      )
      .normalize();
  }

  update(dt: number, elapsed: number): void {
    const rig = this.rig;
    if (!rig) return;
    const source = this.scroll;
    const reduced = this.ctx.reducedMotion;
    const k = source ? (reduced ? source.nearest() : source.keyframe()) : 0;
    rig.update(k, dt, reduced, this.pointer?.value ?? null);
    const floor = this.groundAt(this.camera.position.x, this.camera.position.z) + 2.4;
    if (this.camera.position.y < floor) {
      this.camera.position.y = floor;
      this.camera.lookAt(rig.focus);
    }

    const t = rig.position / (rig.count - 1);
    this.applySky(t);

    // keep the shadow frustum around what the camera is looking at
    this.sun.target.position.copy(rig.focus);
    this.sun.position.copy(rig.focus).addScaledVector(this.lightDir, 120);
    this.sun.target.updateMatrixWorld();

    // Quantized meshes keep their dequantization in the node scale, so animate relative to it.
    if (this.fire && this.fireLight) {
      const flicker = 0.82 + Math.sin(elapsed * 13.1) * 0.08 + Math.sin(elapsed * 7.3 + 1.7) * 0.1;
      const base = this.fire.userData['baseScale'] as THREE.Vector3;
      this.fire.scale.set(base.x, base.y * flicker * 1.1, base.z);
      this.fireLight.intensity = 26 * flicker * (1.2 - t);
    }
    if (this.beacon) {
      const pulse = Math.max(0, Math.sin(elapsed * 2.6)) ** 6;
      this.beacon.scale.copy(this.beacon.userData['baseScale'] as THREE.Vector3).multiplyScalar(0.7 + pulse * 0.6);
    }
    if (this.clouds && !reduced) {
      for (const cloud of this.clouds.children) {
        cloud.position.x += dt * (cloud.userData['speed'] as number);
        if (cloud.position.x > 330) cloud.position.x = -290;
      }
    }
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

function mulberry32(seed: number): () => number {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
