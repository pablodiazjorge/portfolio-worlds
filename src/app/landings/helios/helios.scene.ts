import * as THREE from 'three/webgpu';
import {
  abs,
  color,
  dot,
  float,
  hash,
  max,
  mix,
  mx_fractal_noise_float,
  mx_noise_float,
  normalize,
  normalLocal,
  normalView,
  pass,
  positionLocal,
  positionViewDirection,
  positionWorld,
  positionWorldDirection,
  smoothstep,
  step,
  time,
  uniform,
  vec3,
} from 'three/tsl';
import { bloom } from 'three/addons/tsl/display/BloomNode.js';
import { dequantizeMeshes } from '../../core/assets/dequantize';
import { loadGltf } from '../../core/assets/gltf';
import { DisposeBag, disposeObject } from '../../core/engine/dispose';
import { EngineContext, WorldScene } from '../../core/engine/world-scene';
import { CameraKey, KeyframeRig, PointerTracker } from '../../core/scroll/camera-rig';
import { ScrollDirector } from '../../core/scroll/scroll-director';

const PLANET_CENTRE = new THREE.Vector3(0, -62, 0);
const PLANET_RADIUS = 60;
const SUN_DIR = new THREE.Vector3(0.45, 0.12, -0.88).normalize();
const STATION = new THREE.Vector3(30, 27, -46);
/** Kilometres per scene unit, so the planet has the Earth's radius. */
const KM_PER_UNIT = 6371 / PLANET_RADIUS;

const v = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);

export interface Telemetry {
  altitude: number;
  distance: number;
}

export class HeliosScene implements WorldScene {
  readonly scene = new THREE.Scene();
  readonly camera = new THREE.PerspectiveCamera(40, 1, 0.1, 3000);

  private readonly bag = new DisposeBag();
  private readonly pointer: PointerTracker | null;
  private rig: KeyframeRig | null = null;
  private scroll: ScrollDirector | null = null;
  private pipeline: THREE.RenderPipeline | null = null;

  private readonly uSun = uniform(SUN_DIR.clone());
  private readonly carrier = new THREE.Group();
  private ring: THREE.Object3D | null = null;
  private clouds: THREE.Mesh | null = null;
  private planet: THREE.Mesh | null = null;
  private path: THREE.CatmullRomCurve3 | null = null;
  private readonly pathStops: number[] = [];
  private readonly gates: { mesh: THREE.Mesh; glow: ReturnType<typeof uniform> }[] = [];
  private shuttleU = 0;
  private readonly tangent = new THREE.Vector3();
  private readonly ahead = new THREE.Vector3();
  private readonly dockPoint = new THREE.Vector3();
  readonly telemetry: Telemetry = { altitude: 0, distance: 0 };

  constructor(private readonly ctx: EngineContext) {
    this.pointer = ctx.touch || ctx.reducedMotion ? null : new PointerTracker();
    this.scene.backgroundNode = this.spaceNode();
    const sun = new THREE.DirectionalLight('#fff4e2', 3.6);
    sun.position.copy(SUN_DIR).multiplyScalar(200);
    this.scene.add(sun, new THREE.HemisphereLight('#3b5a8a', '#000000', 0.18));
    this.scene.add(this.carrier);
  }

  attachScroll(source: ScrollDirector | null): void {
    this.scroll = source;
  }

  activate(): void {
    this.ctx.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.ctx.renderer.toneMappingExposure = 1.0;
  }

  async init(onProgress: (fraction: number) => void): Promise<void> {
    const gltf = await loadGltf('models/helios/station.glb', (f) => onProgress(f * 0.85));
    const root = gltf.scene;
    dequantizeMeshes(root);
    this.applyMaterials(root);

    const station = root.getObjectByName('station');
    const shuttle = root.getObjectByName('shuttle');
    this.ring = root.getObjectByName('ring_pivot') ?? null;
    if (station) {
      station.position.copy(STATION);
      station.rotation.y = 0.35;
      this.scene.add(station);
    }
    if (shuttle) {
      shuttle.rotation.y = -Math.PI / 2;
      this.carrier.add(shuttle);
    }

    this.addPlanet();
    this.buildPath(station);
    this.addGates();
    this.rig = new KeyframeRig(this.camera, this.keys(), { damping: 2.2, swayAmount: 1.2 });
    this.setupPipeline();
    onProgress(1);
  }

  private applyMaterials(root: THREE.Object3D): void {
    const lib = new Map<string, THREE.Material>();
    const std = (name: string, params: ConstructorParameters<typeof THREE.MeshStandardNodeMaterial>[0]) =>
      lib.set(name, new THREE.MeshStandardNodeMaterial(params));
    std('hull', { color: '#e6e7ea', roughness: 0.42, metalness: 0.1 });
    std('truss', { color: '#9aa1aa', roughness: 0.38, metalness: 0.85 });
    std('radiator', { color: '#f2f2f0', roughness: 0.65 });
    std('glass', { color: '#0a1220', roughness: 0.05, metalness: 0.4 });
    std('gold', { color: '#d4a64c', roughness: 0.3, metalness: 1 });

    const solar = new THREE.MeshStandardNodeMaterial({ roughness: 0.22, metalness: 0.5, side: THREE.DoubleSide });
    const cells = positionLocal.mul(vec3(2.2, 1, 2.2));
    const gridX = step(0.9, cells.x.fract());
    const gridZ = step(0.94, cells.z.fract());
    solar.colorNode = mix(color('#10224a'), color('#7f8796'), max(gridX, gridZ));
    lib.set('solar', solar);

    const glow = (name: string, hex: string, strength: number) => {
      const m = new THREE.MeshBasicNodeMaterial();
      m.colorNode = color(hex).mul(strength);
      lib.set(name, m);
    };
    glow('engine_glow', '#9fd8ff', 6);
    glow('beacon_red', '#ff3b30', 1.6);
    glow('beacon_green', '#34c759', 1.6);
    glow('dock_light', '#ffcf8a', 4);
    glow('window_light', '#ffd9a0', 2.5);

    root.traverse((o) => {
      const mesh = o as THREE.Mesh;
      if (!mesh.isMesh) return;
      const source = mesh.material as THREE.Material;
      const material = lib.get(source.name);
      if (!material) return;
      source.dispose();
      mesh.material = material;
    });
    lib.forEach((m) => this.bag.add(m));
  }

  private spaceNode() {
    const dir = normalize(positionWorldDirection);
    const layer = (scale: number, threshold: number, brightness: number) => {
      const scaled = dir.mul(scale);
      const cell = scaled.floor();
      const seed = cell.x.add(cell.y.mul(157)).add(cell.z.mul(311));
      const offset = scaled.fract().sub(0.5).length();
      const star = step(threshold, hash(seed)).mul(smoothstep(0.28, 0.0, offset));
      const twinkle = time.mul(hash(seed.add(7)).mul(3).add(0.5)).add(hash(seed.add(3)).mul(6.28)).sin().mul(0.35).add(0.65);
      return star.mul(twinkle).mul(brightness);
    };
    const stars = layer(120, 0.985, 2.2).add(layer(300, 0.99, 1.2)).add(layer(700, 0.993, 0.8));
    const band = float(1).sub(abs(dot(dir, normalize(vec3(0.2, 0.9, 0.35))))).pow(6);
    const dust = mx_fractal_noise_float(dir.mul(3.5), 4).mul(0.5).add(0.5);
    const milky = color('#3a4a7a').mul(band.mul(dust).mul(0.35));
    const sunDot = max(dot(dir, this.uSun), 0);
    const sun = color('#ffe8c8').mul(sunDot.pow(1400).mul(24).add(sunDot.pow(90).mul(0.35)).add(sunDot.pow(8).mul(0.04)));
    return vec3(stars).add(milky).add(sun).add(vec3(0.0006, 0.0008, 0.0025));
  }

  private addPlanet(): void {
    const sphere = this.bag.add(new THREE.SphereGeometry(PLANET_RADIUS, 160, 120));
    const n = normalLocal;
    const height = mx_fractal_noise_float(n.mul(2.1), 6, 2.0, 0.5);
    const land = smoothstep(0.02, 0.07, height);
    const shallow = smoothstep(-0.18, 0.02, height);
    const ocean = mix(color('#06204a'), color('#16609a'), shallow);
    const biome = mx_noise_float(n.mul(4.2).add(11)).mul(0.5).add(0.5);
    const latitude = abs(n.y);
    const ground = mix(mix(color('#3f6d34'), color('#a78a58'), smoothstep(0.35, 0.7, biome).mul(smoothstep(0.75, 0.25, latitude))), color('#8a8579'), smoothstep(0.22, 0.4, height));
    const ice = smoothstep(0.8, 0.88, latitude.add(height.mul(0.08)));
    const surface = mix(mix(ocean, ground, land), color('#eef3f7'), ice);

    const outward = normalize(positionWorld.sub(vec3(PLANET_CENTRE.x, PLANET_CENTRE.y, PLANET_CENTRE.z)));
    const lit = dot(outward, this.uSun);
    const night = smoothstep(0.05, -0.2, lit);
    const cities = smoothstep(0.25, 0.6, mx_noise_float(n.mul(60)))
      .mul(smoothstep(0.0, 0.3, mx_noise_float(n.mul(7).add(3))))
      .mul(land)
      .mul(float(1).sub(ice));
    const rim = float(1).sub(abs(dot(normalView, positionViewDirection))).pow(3);
    const haze = color('#6fb6ff').mul(rim.mul(smoothstep(-0.25, 0.4, lit)).mul(0.9));

    const material = new THREE.MeshStandardNodeMaterial({ roughness: 0.8 });
    material.colorNode = surface;
    material.roughnessNode = mix(float(0.32), float(0.95), land);
    material.emissiveNode = color('#ffb35c').mul(cities.mul(night).mul(2.4)).add(haze);
    this.bag.add(material);
    this.planet = new THREE.Mesh(sphere, material);
    this.planet.position.copy(PLANET_CENTRE);
    this.planet.rotation.z = 0.35;
    this.scene.add(this.planet);

    const cloudGeometry = this.bag.add(new THREE.SphereGeometry(PLANET_RADIUS + 0.45, 128, 96));
    const clouds = new THREE.MeshStandardNodeMaterial({ transparent: true, depthWrite: false, roughness: 1 });
    const cloudNoise = mx_fractal_noise_float(normalLocal.mul(3.4).add(vec3(time.mul(0.006), 0, 0)), 5);
    clouds.colorNode = color('#ffffff');
    clouds.opacityNode = smoothstep(0.08, 0.5, cloudNoise).mul(0.85);
    this.bag.add(clouds);
    this.clouds = new THREE.Mesh(cloudGeometry, clouds);
    this.clouds.position.copy(PLANET_CENTRE);
    this.scene.add(this.clouds);

    const shellGeometry = this.bag.add(new THREE.SphereGeometry(PLANET_RADIUS + 2.6, 128, 96));
    const shell = new THREE.MeshBasicNodeMaterial({ transparent: true, depthWrite: false, side: THREE.BackSide, blending: THREE.AdditiveBlending });
    const shellOut = normalize(positionWorld.sub(vec3(PLANET_CENTRE.x, PLANET_CENTRE.y, PLANET_CENTRE.z)));
    const shellLit = smoothstep(-0.35, 0.5, dot(shellOut, this.uSun));
    const edge = float(1).sub(abs(dot(normalView, positionViewDirection))).pow(5.5);
    const sunset = smoothstep(0.35, 0.0, abs(dot(shellOut, this.uSun)));
    shell.colorNode = mix(color('#5fb2ff'), color('#ffb07a'), sunset.mul(0.7)).mul(edge.mul(shellLit).mul(2.4));
    this.bag.add(shell);
    const atmosphere = new THREE.Mesh(shellGeometry, shell);
    atmosphere.position.copy(PLANET_CENTRE);
    this.scene.add(atmosphere);
  }

  private buildPath(station: THREE.Object3D | undefined): void {
    station?.updateMatrixWorld(true);
    const dock = station ? station.localToWorld(v(0, 2.6, 4.3)) : STATION.clone().add(v(0, 2.6, 4.3));
    const approach = station ? station.localToWorld(v(0, 2.6, 13)) : STATION.clone().add(v(0, 2.6, 13));
    const points = [v(-26, 3.2, 34), v(-14, 7, 22), v(-2, 11, 10), v(9, 15, -2), v(18, 19, -15), v(24, 24, -26), approach, dock];
    this.path = new THREE.CatmullRomCurve3(points, false, 'centripetal');
    this.dockPoint.copy(dock);
    points.forEach((_, i) => this.pathStops.push(i / (points.length - 1)));
  }

  private addGates(): void {
    if (!this.path) return;
    const geometry = this.bag.add(new THREE.TorusGeometry(2.6, 0.07, 12, 96));
    for (let i = 1; i <= 5; i++) {
      const u = this.pathStops[i];
      const glow = uniform(0.4);
      const material = new THREE.MeshBasicNodeMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending });
      const pulse = time.mul(1.4).add(i).sin().mul(0.15).add(0.85);
      material.colorNode = color('#8fd3ff').mul(glow.mul(pulse).mul(1.3));
      this.bag.add(material);
      const gate = new THREE.Mesh(geometry, material);
      this.path.getPoint(u, gate.position);
      this.path.getTangent(u, this.tangent);
      gate.lookAt(this.ahead.copy(gate.position).add(this.tangent));
      this.scene.add(gate);
      this.gates.push({ mesh: gate, glow });
    }
  }

  private keys(): CameraKey[] {
    const path = this.path!;
    const up = v(0, 1, 0);
    const at = (i: number) => path.getPoint(this.pathStops[i]);
    /** Chase view from behind the shuttle; `panel` 1 keeps the subject right of a left panel, -1 the opposite. */
    const chase = (i: number, panel: number, distance = 11): CameraKey => {
      const point = at(i);
      const forward = path.getTangent(this.pathStops[i]).normalize();
      const right = new THREE.Vector3().crossVectors(forward, up).normalize();
      return {
        position: point.clone().addScaledVector(forward, -distance).addScaledVector(right, -panel * 1.6).add(v(0, 2.4, 0)),
        target: point.clone().addScaledVector(forward, 2).addScaledVector(right, -panel * 3.2),
        fov: 38,
      };
    };
    const dock = at(7);
    return [
      { position: v(-46, 4, 62), target: v(10, -6, -40), fov: 42 },
      chase(0, -1, 7),
      chase(1, 1),
      chase(2, -1),
      chase(3, 1),
      chase(4, -1),
      chase(5, 1),
      { position: STATION.clone().add(v(-24, 9, 36)), target: STATION.clone().add(v(-9, 0, 0)), fov: 42 },
      { position: STATION.clone().add(v(20, 6, 28)), target: STATION.clone().add(v(-8, 1, 0)), fov: 40 },
      { position: dock.clone().add(v(-7, 2, 9)), target: dock.clone().add(v(3.2, -0.6, -2)), fov: 40 },
    ];
  }

  private setupPipeline(): void {
    const scenePass = pass(this.scene, this.camera);
    const sceneColor = scenePass.getTextureNode();
    const glow = bloom(sceneColor, this.ctx.quality === 'low' ? 0.4 : 0.55, 0.35, 0.92);
    this.pipeline = new THREE.RenderPipeline(this.ctx.renderer, sceneColor.add(glow));
    this.bag.defer(() => {
      glow.dispose();
      scenePass.dispose();
    });
    this.bag.add(this.pipeline);
  }

  render(): boolean {
    if (!this.pipeline) return false;
    this.pipeline.render();
    return true;
  }

  update(dt: number, elapsed: number): void {
    const rig = this.rig;
    const path = this.path;
    if (!rig || !path) return;
    const reduced = this.ctx.reducedMotion;
    const source = this.scroll;
    const k = source ? (reduced ? source.nearest() : source.keyframe()) : 0;
    rig.update(k, dt, reduced, this.pointer?.value ?? null);
    const s = rig.position;

    // shuttle position along the path: waits at the start, then one gate per experience stop
    const stopsForKeys = [0, 0, 1, 2, 3, 4, 5, 7, 7, 7].map((i) => this.pathStops[i]);
    const i = Math.min(stopsForKeys.length - 2, Math.floor(s));
    const f = s - i;
    const eased = f * f * (3 - 2 * f);
    const target = THREE.MathUtils.lerp(stopsForKeys[i], stopsForKeys[i + 1], eased);
    this.shuttleU = reduced ? target : this.shuttleU + (target - this.shuttleU) * (1 - Math.exp(-dt * 3));
    const u = THREE.MathUtils.clamp(this.shuttleU, 0, 1);
    path.getPoint(u, this.carrier.position);
    path.getTangent(Math.min(u, 0.999), this.tangent);
    this.carrier.lookAt(this.ahead.copy(this.carrier.position).add(this.tangent));
    if (!reduced) this.carrier.position.y += Math.sin(elapsed * 1.1) * 0.05;

    this.gates.forEach((gate, index) => {
      const distance = Math.abs(u - this.pathStops[index + 1]);
      gate.glow.value = 0.35 + Math.max(0, 1 - distance * 9) * 1.2;
    });

    if (this.ring && !reduced) this.ring.rotation.x += dt * 0.12;
    if (this.clouds && !reduced) this.clouds.rotation.y += dt * 0.004;
    if (this.planet && !reduced) this.planet.rotation.y += dt * 0.002;

    const altitude = this.carrier.position.distanceTo(PLANET_CENTRE) - PLANET_RADIUS;
    this.telemetry.altitude = Math.max(0, altitude * KM_PER_UNIT);
    this.telemetry.distance = this.carrier.position.distanceTo(this.dockPoint) * KM_PER_UNIT;
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
