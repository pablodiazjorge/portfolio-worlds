import * as THREE from 'three/webgpu';
import {
  abs,
  color,
  dot,
  float,
  floor,
  fract,
  mix,
  mx_noise_float,
  normalView,
  positionLocal,
  positionViewDirection,
  screenUV,
  sin,
  smoothstep,
  step,
  uniform,
  uv,
  vec2,
} from 'three/tsl';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { dequantizeMeshes } from '../../core/assets/dequantize';
import { loadGltf } from '../../core/assets/gltf';
import { DisposeBag, disposeObject } from '../../core/engine/dispose';
import { EngineContext, WorldScene } from '../../core/engine/world-scene';
import { CameraKey, KeyframeRig, PointerTracker } from '../../core/scroll/camera-rig';
import { ScrollDirector } from '../../core/scroll/scroll-director';

/** Exploded stack, top to bottom; experience stops visit them in this order. */
export const LAYERS = ['layer_top', 'layer_battery', 'layer_board', 'layer_frame', 'layer_camera'] as const;
const EXPLODE: Record<(typeof LAYERS)[number], number> = {
  layer_top: 1.5,
  layer_battery: 0.98,
  layer_board: 0.52,
  layer_frame: 0,
  layer_camera: -0.66,
};

interface Pose {
  rotation: number;
  explode: number;
  height: number;
  props: number;
  focus: number;
  shade: number;
}

const POSES: Pose[] = [
  { rotation: 0.55, explode: 0, height: 0.5, props: 1, focus: -1, shade: 0 },
  { rotation: -0.4, explode: 0, height: 0.32, props: 0.35, focus: -1, shade: 0 },
  { rotation: 0.35, explode: 1, height: 0.3, props: 0, focus: 0, shade: 1 },
  { rotation: -0.25, explode: 1, height: 0.3, props: 0, focus: 1, shade: 1 },
  { rotation: 0.3, explode: 1, height: 0.3, props: 0, focus: 2, shade: 1 },
  { rotation: -0.3, explode: 1, height: 0.3, props: 0, focus: 3, shade: 1 },
  { rotation: 0.25, explode: 1, height: 0.3, props: 0, focus: 4, shade: 1 },
  { rotation: 0.9, explode: 0, height: 0.45, props: 0.7, focus: -1, shade: 0.2 },
  { rotation: 2.2, explode: 0, height: 0.5, props: 0.7, focus: -1, shade: 0.2 },
  { rotation: 0.05, explode: 0, height: 0.42, props: 1, focus: -1, shade: 0 },
];

const FLOOR_Y = -1.25;

export class AerisScene implements WorldScene {
  readonly scene = new THREE.Scene();
  readonly camera = new THREE.PerspectiveCamera(32, 1, 0.05, 100);

  private readonly bag = new DisposeBag();
  private readonly pointer: PointerTracker | null;
  private rig: KeyframeRig | null = null;
  private scroll: ScrollDirector | null = null;

  private readonly drone = new THREE.Group();
  private readonly layers = new Map<string, THREE.Object3D>();
  private readonly layerBase = new Map<string, number>();
  private readonly glows = LAYERS.map(() => uniform(0));
  private readonly anchors = LAYERS.map(() => new THREE.Vector3());
  private readonly spinners: { pivot: THREE.Object3D; direction: number; disc: THREE.Mesh }[] = [];
  private gimbal: THREE.Object3D | null = null;
  private readonly uShade = uniform(0);
  private readonly uDisc = uniform(0);
  private shadowBlob: THREE.Mesh | null = null;
  private readonly key = new THREE.DirectionalLight('#ffffff', 3.2);
  private readonly rim = new THREE.DirectionalLight('#dce8ff', 2.4);
  private readonly pose: Pose = { ...POSES[0] };
  private propAngle = 0;
  private readonly projected = new THREE.Vector3();

  constructor(private readonly ctx: EngineContext) {
    this.pointer = ctx.touch || ctx.reducedMotion ? null : new PointerTracker();
    this.scene.backgroundNode = this.studioNode();
    this.key.position.set(-3.5, 6, 4.5);
    this.key.castShadow = ctx.quality !== 'low';
    this.key.shadow.mapSize.set(2048, 2048);
    const shadowCam = this.key.shadow.camera;
    shadowCam.left = -3;
    shadowCam.right = 3;
    shadowCam.top = 3;
    shadowCam.bottom = -3;
    shadowCam.near = 1;
    shadowCam.far = 20;
    this.key.shadow.radius = 6;
    this.key.shadow.bias = -0.0004;
    this.rim.position.set(4, 3, -5);
    this.scene.add(this.key, this.rim, new THREE.HemisphereLight('#ffffff', '#9aa0aa', 0.7));
    this.scene.add(this.drone);
  }

  attachScroll(source: ScrollDirector | null): void {
    this.scroll = source;
  }

  activate(): void {
    this.ctx.renderer.toneMapping = THREE.NeutralToneMapping;
    this.ctx.renderer.toneMappingExposure = 1.05;
  }

  async init(onProgress: (fraction: number) => void): Promise<void> {
    const [gltf] = await Promise.all([loadGltf('models/aeris/drone.glb', (f) => onProgress(f * 0.8)), this.environment()]);
    const root = gltf.scene;
    dequantizeMeshes(root);
    const materials = this.materials();

    for (const name of LAYERS) {
      const layer = root.getObjectByName(name);
      if (!layer) continue;
      this.layers.set(name, layer);
      this.layerBase.set(name, layer.position.y);
    }

    LAYERS.forEach((name, index) => {
      const layer = this.layers.get(name);
      if (!layer) return;
      const glow = this.glows[index];
      const clones = new Map<THREE.Material, THREE.Material>();
      layer.traverse((object) => {
        const mesh = object as THREE.Mesh;
        if (!mesh.isMesh) return;
        const source = mesh.material as THREE.Material;
        const base = materials.get(source.name);
        if (!base) return;
        let clone = clones.get(base);
        if (!clone) {
          clone = base.clone();
          const rim = float(1).sub(abs(dot(normalView, positionViewDirection))).pow(3.2);
          (clone as THREE.MeshStandardNodeMaterial).emissiveNode = color('#ff6a2b').mul(rim.mul(glow).mul(0.75));
          this.bag.add(clone);
          clones.set(base, clone);
        }
        mesh.material = clone;
        source.dispose();
        mesh.castShadow = true;
        mesh.receiveShadow = true;
      });
      const box = new THREE.Box3().setFromObject(layer);
      this.anchors[index].set(box.max.x * 0.9, (box.min.y + box.max.y) / 2, 0);
    });
    materials.forEach((m) => this.bag.add(m));

    for (const key of ['fl', 'fr', 'bl', 'br']) {
      const pivot = root.getObjectByName(`spin_${key}`);
      if (!pivot) continue;
      const disc = new THREE.Mesh(this.discGeometry(), this.discMaterial());
      disc.rotation.x = -Math.PI / 2;
      disc.position.y = 0.012;
      pivot.add(disc);
      this.spinners.push({ pivot, direction: key === 'fl' || key === 'br' ? 1 : -1, disc });
    }
    this.gimbal = root.getObjectByName('gimbal_pivot') ?? null;

    this.drone.add(root);
    this.addFloor();
    this.rig = new KeyframeRig(this.camera, this.keys(), { damping: 2.8, swayAmount: 0.25 });
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
    this.scene.environmentIntensity = 0.85;
  }

  private studioNode() {
    const centre = screenUV.sub(vec2(0.5, 0.58)).mul(vec2(1.25, 1));
    const vignette = smoothstep(0.15, 0.95, centre.length());
    const light = mix(color('#f4f5f7'), color('#e3e6ea'), this.uShade);
    const dark = mix(color('#c6cad1'), color('#a7adb6'), this.uShade);
    return mix(light, dark, vignette);
  }

  private materials(): Map<string, THREE.Material> {
    const p = positionLocal;
    const map = new Map<string, THREE.Material>();

    const carbon = new THREE.MeshPhysicalNodeMaterial({ roughness: 0.42, clearcoat: 1, clearcoatRoughness: 0.12 });
    const weave = p.xz.mul(55);
    const cell = floor(weave.x.add(weave.y));
    const across = fract(weave.x.sub(weave.y).mul(0.5));
    const yarn = sin(fract(weave.x.add(weave.y)).mul(Math.PI)).mul(0.5).add(0.5);
    const direction = step(0.5, fract(cell.mul(0.5)));
    const sheen = mix(yarn, sin(across.mul(Math.PI)), direction);
    carbon.colorNode = mix(color('#0e0f12'), color('#34373e'), sheen.pow(1.6));
    carbon.roughnessNode = mix(float(0.5), float(0.3), sheen);
    map.set('carbon', carbon);

    map.set('shell', new THREE.MeshPhysicalNodeMaterial({ color: '#2a2d33', roughness: 0.4, clearcoat: 0.55, clearcoatRoughness: 0.28 }));
    map.set('accent', new THREE.MeshPhysicalNodeMaterial({ color: '#ff5a1f', roughness: 0.36, clearcoat: 0.4, clearcoatRoughness: 0.2 }));

    const metal = new THREE.MeshStandardNodeMaterial({ color: '#c4c8d0', metalness: 1, roughness: 0.3 });
    metal.roughnessNode = float(0.24).add(mx_noise_float(p.mul(vec2(180, 6).xyx)).mul(0.06));
    map.set('metal', metal);

    const pcb = new THREE.MeshStandardNodeMaterial({ roughness: 0.55 });
    const grid = p.xz.mul(42);
    const lane = mx_noise_float(floor(grid).mul(0.37));
    const traceX = step(0.86, fract(grid.x)).mul(step(0.1, lane));
    const traceZ = step(0.86, fract(grid.y)).mul(step(lane, -0.1));
    const trace = traceX.add(traceZ).clamp(0, 1);
    pcb.colorNode = mix(color('#0d3a33'), color('#c9a34a'), trace);
    pcb.metalnessNode = trace.mul(0.9);
    pcb.roughnessNode = mix(float(0.6), float(0.25), trace);
    map.set('pcb', pcb);

    map.set('chip', new THREE.MeshStandardNodeMaterial({ color: '#15161a', roughness: 0.42 }));
    map.set('battery', new THREE.MeshStandardNodeMaterial({ color: '#3b3e45', roughness: 0.55 }));
    map.set('prop', new THREE.MeshPhysicalNodeMaterial({ color: '#1d2025', roughness: 0.3, clearcoat: 0.6 }));
    map.set('glass', new THREE.MeshPhysicalNodeMaterial({ color: '#030406', roughness: 0.03, clearcoat: 1, clearcoatRoughness: 0.02 }));
    map.set('led_white', new THREE.MeshBasicNodeMaterial({ color: '#f2f8ff' }));
    map.set('led_red', new THREE.MeshBasicNodeMaterial({ color: '#ff3b30' }));
    map.set('rubber', new THREE.MeshStandardNodeMaterial({ color: '#121316', roughness: 0.85 }));
    for (const [name, material] of map) material.name = name;
    return map;
  }

  private discGeometryCache: THREE.CircleGeometry | null = null;
  private discMaterialCache: THREE.MeshBasicNodeMaterial | null = null;

  private discGeometry(): THREE.CircleGeometry {
    this.discGeometryCache ??= this.bag.add(new THREE.CircleGeometry(0.66, 48));
    return this.discGeometryCache;
  }

  /** Motion blur disc that replaces the blades as they spin up. */
  private discMaterial(): THREE.MeshBasicNodeMaterial {
    if (this.discMaterialCache) return this.discMaterialCache;
    const material = new THREE.MeshBasicNodeMaterial({ transparent: true, depthWrite: false, side: THREE.DoubleSide });
    const r = uv().sub(0.5).length().mul(2);
    const ring = smoothstep(0.12, 0.3, r).mul(float(1).sub(smoothstep(0.85, 1, r)));
    material.colorNode = color('#1d2025');
    material.opacityNode = ring.mul(this.uDisc).mul(0.32);
    this.discMaterialCache = this.bag.add(material);
    return material;
  }

  private addFloor(): void {
    const floorGeometry = this.bag.add(new THREE.PlaneGeometry(12, 12));
    floorGeometry.rotateX(-Math.PI / 2);
    const shadowMaterial = this.bag.add(new THREE.ShadowNodeMaterial({ opacity: 0.22 }));
    const floorMesh = new THREE.Mesh(floorGeometry, shadowMaterial);
    floorMesh.position.y = FLOOR_Y;
    floorMesh.receiveShadow = true;
    this.scene.add(floorMesh);

    const blobGeometry = this.bag.add(new THREE.PlaneGeometry(3.2, 2.4));
    blobGeometry.rotateX(-Math.PI / 2);
    const blob = new THREE.MeshBasicNodeMaterial({ transparent: true, depthWrite: false });
    const d = uv().sub(0.5).mul(2).length();
    blob.colorNode = color('#2a2e36');
    blob.opacityNode = float(1).sub(smoothstep(0.0, 1.0, d)).pow(2.2).mul(0.35);
    this.bag.add(blob);
    this.shadowBlob = new THREE.Mesh(blobGeometry, blob);
    this.shadowBlob.position.y = FLOOR_Y + 0.002;
    this.scene.add(this.shadowBlob);
  }

  private keys(): CameraKey[] {
    const up = new THREE.Vector3(0, 1, 0);
    const v = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);
    const around = (angleDeg: number, radius: number, y: number, subject: THREE.Vector3, panel: number, fov = 30, shift = 0.8): CameraKey => {
      const a = THREE.MathUtils.degToRad(angleDeg);
      const position = v(Math.sin(a) * radius, y, Math.cos(a) * radius);
      const view = subject.clone().sub(position).setY(0).normalize();
      const right = new THREE.Vector3().crossVectors(view, up).normalize();
      return { position, target: subject.clone().addScaledVector(right, -panel * shift), fov };
    };
    const layerY = (name: (typeof LAYERS)[number]) => {
      const layer = this.layers.get(name);
      const box = layer ? new THREE.Box3().setFromObject(layer) : null;
      const centre = box ? (box.min.y + box.max.y) / 2 : 0;
      return centre + EXPLODE[name] + POSES[2].height;
    };
    return [
      around(32, 5.4, 1.35, v(0, 0.55, 0), 1, 30, 1.0),
      around(-52, 5.0, 0.8, v(0, 0.35, 0), -1, 30, 0.9),
      around(38, 4.4, layerY('layer_top') + 0.7, v(0, layerY('layer_top'), 0), 1, 30),
      around(-34, 4.4, layerY('layer_battery') + 0.6, v(0, layerY('layer_battery'), 0), -1, 30),
      around(30, 4.4, layerY('layer_board') + 0.6, v(0, layerY('layer_board'), 0), 1, 30),
      around(-30, 4.4, layerY('layer_frame') + 0.7, v(0, layerY('layer_frame'), 0), -1, 30),
      around(26, 4.4, layerY('layer_camera') + 0.5, v(0, layerY('layer_camera'), 0), 1, 30),
      around(8, 8.6, 1.4, v(0, 0.5, 0), 1, 30, 2.4),
      around(-14, 9.2, 1.8, v(0, 0.5, 0), 1, 30, 2.6),
      around(2, 3.6, 0.62, v(0, 0.5, 0), 1, 32, 0.85),
    ];
  }

  /** Screen position, in CSS pixels, of the callout point of a layer. */
  layerPoint(index: number, width: number, height: number): { x: number; y: number } | null {
    const layer = this.layers.get(LAYERS[index]);
    if (!layer) return null;
    this.projected.copy(this.anchors[index]);
    layer.localToWorld(this.projected);
    this.projected.project(this.camera);
    if (this.projected.z > 1) return null;
    return { x: (this.projected.x * 0.5 + 0.5) * width, y: (-this.projected.y * 0.5 + 0.5) * height };
  }

  update(dt: number, elapsed: number): void {
    const rig = this.rig;
    if (!rig) return;
    const reduced = this.ctx.reducedMotion;
    const source = this.scroll;
    const k = source ? (reduced ? source.nearest() : source.keyframe()) : 0;
    rig.update(k, dt, reduced, this.pointer?.value ?? null);

    const s = rig.position;
    const i = Math.min(POSES.length - 2, Math.floor(s));
    const f = THREE.MathUtils.smoothstep(s - i, 0, 1);
    const a = POSES[i];
    const b = POSES[i + 1];
    const pose = this.pose;
    pose.rotation = THREE.MathUtils.lerp(a.rotation, b.rotation, f);
    pose.explode = THREE.MathUtils.lerp(a.explode, b.explode, f);
    pose.height = THREE.MathUtils.lerp(a.height, b.height, f);
    pose.props = THREE.MathUtils.lerp(a.props, b.props, f);
    pose.shade = THREE.MathUtils.lerp(a.shade, b.shade, f);
    this.uShade.value = pose.shade;

    const bob = reduced ? 0 : Math.sin(elapsed * 1.6) * 0.035;
    this.drone.position.y = pose.height + bob;
    this.drone.rotation.y = Math.PI + pose.rotation + (s > 6.5 && s < 8.5 && !reduced ? elapsed * 0.12 : 0);
    this.drone.rotation.z = reduced ? 0 : Math.sin(elapsed * 0.9) * 0.025 * (1 - pose.explode);
    this.drone.rotation.x = reduced ? 0 : Math.sin(elapsed * 0.7 + 1) * 0.02 * (1 - pose.explode);

    const ease = pose.explode * pose.explode * (3 - 2 * pose.explode);
    LAYERS.forEach((name, index) => {
      const layer = this.layers.get(name);
      if (!layer) return;
      layer.position.y = (this.layerBase.get(name) ?? 0) + EXPLODE[name] * ease;
      layer.rotation.y = (index - 2) * 0.12 * ease;
      const focus = Math.max(0, 1 - Math.abs(s - (index + 2)) * 1.6);
      this.glows[index].value = focus;
    });

    this.propAngle += dt * (4 + pose.props * 70);
    this.uDisc.value = THREE.MathUtils.smoothstep(pose.props, 0.25, 0.9);
    for (const spinner of this.spinners) {
      spinner.pivot.rotation.y = this.propAngle * spinner.direction;
    }
    if (this.gimbal) this.gimbal.rotation.x = Math.sin(elapsed * 0.5) * 0.08 * (1 - pose.explode);
    if (this.shadowBlob) {
      const lift = this.drone.position.y - FLOOR_Y;
      this.shadowBlob.scale.setScalar(0.8 + lift * 0.18);
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
