import * as THREE from 'three/webgpu';
import {
  abs,
  atan,
  color,
  dot,
  float,
  fwidth,
  hash,
  max,
  min,
  mix,
  mx_fractal_noise_float,
  normalize,
  normalView,
  oneMinus,
  pass,
  pmremTexture,
  positionLocal,
  positionView,
  positionViewDirection,
  positionWorld,
  positionWorldDirection,
  smoothstep,
  step,
  texture,
  time,
  uniform,
  uv,
  vec2,
  vec3,
} from 'three/tsl';
import { bloom } from 'three/addons/tsl/display/BloomNode.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { dequantizeMeshes } from '../../core/assets/dequantize';
import { loadGltf } from '../../core/assets/gltf';
import { DisposeBag, disposeObject } from '../../core/engine/dispose';
import { EngineContext, WorldScene } from '../../core/engine/world-scene';
import { CameraKey, KeyframeRig, PointerTracker } from '../../core/scroll/camera-rig';
import { ScrollDirector } from '../../core/scroll/scroll-director';

const PLANET_CENTRE = new THREE.Vector3(0, -62, 0);
const PLANET_RADIUS = 60;
// the sun sits off to the right and a little behind the camera, so the hero sees a lit Earth with
// its terminator across the disc and the station is lit from the side on the approach, not backlit
const SUN_DIR = new THREE.Vector3(0.8, 0.45, 0.4).normalize();
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
  /** How far the cloud layer has turned ahead of the ground, in turns, so its shadows follow it. */
  private readonly uCloudShift = uniform(0);
  private readonly carrier = new THREE.Group();
  private ring: THREE.Object3D | null = null;
  private wheel: THREE.Object3D | null = null;
  private envTexture: THREE.Texture | null = null;
  private clouds: THREE.Mesh | null = null;
  private planet: THREE.Mesh | null = null;
  private path: THREE.CatmullRomCurve3 | null = null;
  private readonly pathStops: number[] = [];
  private readonly gates: { mesh: THREE.Object3D; glow: ReturnType<typeof uniform> }[] = [];
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
    // a cool fill from the sky and the Earth's own blue shine from below, so the station's shadow
    // side still reads from the approach, where the sun is behind it
    this.scene.add(sun, new THREE.HemisphereLight('#2c4a7a', '#35609a', 0.35));
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
    // a faint, cool studio environment: space is black, but the Earth and the sun fill the hulls
    const pmrem = new THREE.PMREMGenerator(this.ctx.renderer);
    const room = new RoomEnvironment();
    const env = await pmrem.fromSceneAsync(room, 0.04);
    pmrem.dispose();
    room.traverse((o) => {
      const mesh = o as THREE.Mesh;
      mesh.geometry?.dispose();
      (mesh.material as THREE.Material | undefined)?.dispose();
    });
    this.bag.add(env.texture);
    this.scene.environment = env.texture;
    this.envTexture = env.texture;
    this.scene.environmentIntensity = 0.45;
    const gltf = await loadGltf('models/helios/station.glb', (f) => onProgress(f * 0.85));
    const root = gltf.scene;
    dequantizeMeshes(root);
    this.applyMaterials(root);

    const station = root.getObjectByName('station');
    const shuttle = root.getObjectByName('shuttle');
    this.ring = root.getObjectByName('ring_pivot') ?? null;
    this.wheel = root.getObjectByName('station_body') ?? null;
    if (station) {
      station.position.copy(STATION);
      station.rotation.y = 0.35;
      this.scene.add(station);
      if (this.wheel) this.addDockLights(station);
    }
    if (shuttle) {
      shuttle.rotation.y = -Math.PI / 2;
      this.carrier.add(shuttle);
      if (shuttle.getObjectByName('shuttle_generated')) this.addEngineGlow(shuttle);
    }

    this.addPlanet();
    this.buildPath(station);
    this.addGates(root);
    this.rig = new KeyframeRig(this.camera, this.keys(), { damping: 2.2, swayAmount: 1.2 });
    this.setupPipeline();
    onProgress(1);
  }

  private applyMaterials(root: THREE.Object3D): void {
    const lib = new Map<string, THREE.Material>();
    const std = (name: string, params: ConstructorParameters<typeof THREE.MeshStandardNodeMaterial>[0]) =>
      lib.set(name, new THREE.MeshStandardNodeMaterial(params));
    lib.set('hull', this.hullMaterial());
    std('truss', { color: '#9aa1aa', roughness: 0.38, metalness: 0.85 });
    std('radiator', { color: '#f2f2f0', roughness: 0.65 });
    std('glass', { color: '#0a1220', roughness: 0.05, metalness: 0.4 });
    std('gold', { color: '#d4a64c', roughness: 0.3, metalness: 1 });
    std('buoy_body', { color: '#a9afb7', roughness: 0.5, metalness: 0.35 });

    // the arrays catch the sun from the approach: matte enough not to flare white in the bloom
    const solar = new THREE.MeshStandardNodeMaterial({ roughness: 0.45, metalness: 0.3, side: THREE.DoubleSide });
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
    lib.set('dock_field', this.fieldMaterial());

    root.traverse((o) => {
      const mesh = o as THREE.Mesh;
      if (!mesh.isMesh) return;
      const source = mesh.material as THREE.Material;
      let material = lib.get(source.name);
      if (!material && source.name.endsWith('_tex')) {
        // a generated asset (TRELLIS.2) keeps its baked colour and its metallic-roughness map
        const baked = (source as THREE.MeshStandardMaterial).map;
        const mrMap = (source as THREE.MeshStandardMaterial).metalnessMap;
        for (const map of [baked, mrMap]) if (map) map.anisotropy = 16;
        const generated = new THREE.MeshStandardNodeMaterial({ roughness: 0.6, metalness: 0.2 });
        if (baked) {
          const base = texture(baked).rgb;
          generated.colorNode = base.mul(1.05);
        }
        if (mrMap) {
          const mr = texture(mrMap);
          generated.metalnessNode = mr.b.mul(0.9);
          generated.roughnessNode = mr.g.clamp(0.25, 0.9);
        }
        lib.set(source.name, generated);
        material = generated;
      }
      if (!material) return;
      source.dispose();
      mesh.material = material;
    });
    lib.forEach((m) => this.bag.add(m));
  }

  /** The station's hull: painted plates drawn from the model's own frame (the hub axis is local z, the
   *  ring lies in the x-y plane). The relief between the gold bands is modelled, so the shader only adds
   *  a faint seam down the middle of each drum of the ring and a 2.5 m grid of plates elsewhere, a tone
   *  of its own per plate, grime along the seams and a worn roughness; the seams fade with distance so
   *  the hull never reads as ruled paper from afar. */
  private hullMaterial(): THREE.MeshStandardNodeMaterial {
    const m = new THREE.MeshStandardNodeMaterial({ metalness: 0.12 });
    const p = positionLocal;
    const r = p.xy.length();
    const onRing = smoothstep(9.2, 9.8, r);
    // the ring: the drums are joined every 22.5 degrees, so one seam halfway along each
    const deg = atan(p.y, p.x).mul(180 / Math.PI).add(360);
    const ringSeam = abs(deg.mod(22.5).sub(11.25)).mul(Math.PI / 180).mul(r);
    const ringCell = deg.div(22.5).floor().add(step(0, p.z).mul(31));
    // everything else: a grid of plates in the model's frame
    const g = p.div(2.5);
    const gf = g.fract().sub(0.5).abs().mul(-1).add(0.5).mul(2.5);
    const boxSeam = min(min(gf.x, gf.y), gf.z);
    const boxCell = g.floor();
    const seamDist = mix(boxSeam, ringSeam, onRing);
    const cellId = mix(boxCell.x.add(boxCell.y.mul(37)).add(boxCell.z.mul(113)), ringCell, onRing);
    const aa = fwidth(seamDist).max(0.01);
    const near = oneMinus(smoothstep(30, 90, positionView.z.negate()));
    const seam = oneMinus(smoothstep(float(0.02).sub(aa), float(0.02).add(aa), seamDist)).mul(near);
    const grime = smoothstep(0.0, 0.3, seamDist).mul(0.1).add(0.9);
    const tone = mix(0.94, 1.03, hash(cellId.add(0.5)));
    const wear = mx_fractal_noise_float(p.mul(0.9)).mul(0.5).add(0.5);
    const paint = color('#cbd0d6').mul(tone).mul(grime).mul(wear.mul(0.08).add(0.96));
    m.colorNode = mix(paint, paint.mul(0.72), seam);
    m.roughnessNode = wear.mul(0.22).add(0.4).add(seam.mul(0.2));
    return m;
  }

  /** The plasma field across the docking port: translucent, rippling and brighter at its rim, so the
   *  lit corridor shows through it. */
  private fieldMaterial(): THREE.MeshBasicNodeMaterial {
    const m = new THREE.MeshBasicNodeMaterial({ transparent: true, depthWrite: false, side: THREE.DoubleSide });
    const p = positionLocal;
    const rr = p.xy.length().div(1.46);
    const ripple = mx_fractal_noise_float(vec3(p.x.mul(1.4), p.y.mul(1.4), time.mul(0.45))).mul(0.5).add(0.5);
    const swirl = mx_fractal_noise_float(vec3(p.x.mul(0.6).add(time.mul(0.2)), p.y.mul(0.6), time.mul(0.15))).mul(0.5).add(0.5);
    const rim = smoothstep(0.55, 1.0, rr);
    const pulse = time.mul(1.4).sin().mul(0.08).add(1);
    m.colorNode = mix(color('#2f8fff'), color('#c8f0ff'), ripple.mul(0.7).add(swirl.mul(0.3))).mul(rim.mul(1.6).add(1.0)).mul(pulse);
    m.opacityNode = float(0.22).add(rim.mul(0.5)).add(ripple.mul(0.14));
    return m;
  }

  /** A warm ring of light round the mouth of the docking port and four guide lamps on its rim. */
  private addDockLights(station: THREE.Object3D): void {
    const dockLocal = station.getObjectByName('dock')?.position ?? v(0, 0, 7.1);
    const mouth = dockLocal.clone().add(v(0, 0, -1.7));
    const ring = new THREE.MeshBasicNodeMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending });
    ring.colorNode = color('#ffcf8a').mul(time.mul(2.2).sin().mul(0.12).add(1).mul(2.2));
    this.bag.add(ring);
    const torus = new THREE.Mesh(this.bag.add(new THREE.TorusGeometry(2.35, 0.07, 10, 72)), ring);
    torus.position.copy(mouth);
    station.add(torus);
    const lamp = this.bag.add(new THREE.SphereGeometry(0.16, 10, 8));
    for (let i = 0; i < 4; i++) {
      const a = i * Math.PI / 2 + Math.PI / 4;
      const mesh = new THREE.Mesh(lamp, ring);
      mesh.position.copy(mouth).add(v(Math.cos(a) * 2.6, Math.sin(a) * 2.6, 0.15));
      station.add(mesh);
    }
  }

  /** Glowing discs on the generated shuttle's five nozzles (three above, two below), measured on a rear render; the bloom picks them up. */
  private addEngineGlow(shuttle: THREE.Object3D): void {
    const disc = this.bag.add(new THREE.CircleGeometry(0.1, 24));
    const halo = this.bag.add(new THREE.CircleGeometry(0.24, 24));
    const core = new THREE.MeshBasicNodeMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending });
    core.colorNode = color('#bfe6ff').mul(time.mul(9).sin().mul(0.08).add(1).mul(3.2));
    const soft = new THREE.MeshBasicNodeMaterial({ transparent: true, depthWrite: false, blending: THREE.AdditiveBlending });
    soft.colorNode = color('#5fb6ff').mul(float(1).sub(uv().sub(0.5).length().mul(2)).clamp(0, 1).pow(2).mul(1.4));
    this.bag.add(core);
    this.bag.add(soft);
    for (const [y, z] of [[-0.08, -0.42], [-0.08, -0.17], [-0.08, 0.1], [-0.3, -0.27], [-0.3, 0.02]] as const) {
      for (const [geometry, material, back] of [[disc, core, 0.0], [halo, soft, 0.12]] as const) {
        const mesh = new THREE.Mesh(geometry, material);
        mesh.position.set(-1.58 - back, y, z);
        mesh.rotation.y = -Math.PI / 2;
        shuttle.add(mesh);
      }
    }
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
    // the Earth from NASA's maps (public domain): Blue Marble for the day, Black Marble for the
    // city lights, the combined cloud map for the clouds and an ocean mask for the sun's glint
    const loader = new THREE.TextureLoader();
    const load = (file: string, srgb: boolean) => {
      const t = this.bag.add(loader.load(`textures/helios/${file}`));
      t.wrapS = THREE.RepeatWrapping;
      t.anisotropy = 8;
      if (srgb) t.colorSpace = THREE.SRGBColorSpace;
      return t;
    };
    const dayMap = load('earth-day.webp', true);
    const nightMap = load('earth-night.webp', true);
    const cloudMap = load('earth-clouds.webp', false);
    const oceanMap = load('earth-ocean.webp', false);

    const sphere = this.bag.add(new THREE.SphereGeometry(PLANET_RADIUS, 160, 120));
    const outward = normalize(positionWorld.sub(vec3(PLANET_CENTRE.x, PLANET_CENTRE.y, PLANET_CENTRE.z)));
    const lit = dot(outward, this.uSun);
    const night = smoothstep(0.1, -0.16, lit);
    const ocean = texture(oceanMap).r;
    // the clouds throw soft shadows on the ground, read from the cloud map where the layer has turned to
    const cloudShadow = float(1).sub(texture(cloudMap, uv().add(vec2(this.uCloudShift, 0))).r.mul(0.5));
    const rim = float(1).sub(abs(dot(normalView, positionViewDirection))).pow(3);
    const haze = color('#6fb6ff').mul(rim.mul(smoothstep(-0.25, 0.4, lit)).mul(0.7));

    const material = new THREE.MeshStandardNodeMaterial({ roughness: 0.8 });
    // the planet takes almost no light from the studio environment, so its night side stays night
    // (a zero in place of the map switches the whole lighting off, so the map is sampled and scaled)
    if (this.envTexture) material.envNode = pmremTexture(this.envTexture).mul(0.03);
    material.colorNode = texture(dayMap).rgb.mul(cloudShadow);
    material.roughnessNode = mix(float(0.92), float(0.24), ocean);
    // the city lights: the night map carries a blue cast over all the land, so only its brighter
    // part counts, warmed to sodium orange and pushed enough to read against the dark side
    const nightTex = texture(nightMap).rgb;
    const lights = smoothstep(0.1, 0.55, nightTex.r.add(nightTex.g).mul(0.5)).mul(color('#ffb060'));
    material.emissiveNode = lights.mul(night.mul(4.5)).add(haze);
    this.bag.add(material);
    this.planet = new THREE.Mesh(sphere, material);
    this.planet.position.copy(PLANET_CENTRE);
    this.planet.rotation.z = 0.35;
    this.scene.add(this.planet);

    const cloudGeometry = this.bag.add(new THREE.SphereGeometry(PLANET_RADIUS + 0.45, 128, 96));
    const clouds = new THREE.MeshStandardNodeMaterial({ transparent: true, depthWrite: false, roughness: 1 });
    if (this.envTexture) clouds.envNode = pmremTexture(this.envTexture).mul(0.03);
    clouds.colorNode = color('#ffffff');
    clouds.opacityNode = texture(cloudMap).r.mul(0.95);
    this.bag.add(clouds);
    this.clouds = new THREE.Mesh(cloudGeometry, clouds);
    this.clouds.position.copy(PLANET_CENTRE);
    this.clouds.rotation.z = 0.35;
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
    // the docking point is an empty the model carries; the approach lies 8.7 units out from it
    const dockLocal = station?.getObjectByName('dock')?.position.clone() ?? v(0, 2.6, 4.3);
    const dock = station ? station.localToWorld(dockLocal.clone()) : STATION.clone().add(dockLocal);
    const approach = station ? station.localToWorld(dockLocal.clone().add(v(0, 0, 8.7))) : STATION.clone().add(dockLocal.clone().add(v(0, 0, 8.7)));
    const points = [v(-26, 3.2, 34), v(-14, 7, 22), v(-2, 11, 10), v(9, 15, -2), v(18, 19, -15), v(24, 24, -26), approach, dock];
    this.path = new THREE.CatmullRomCurve3(points, false, 'centripetal');
    this.dockPoint.copy(dock);
    points.forEach((_, i) => this.pathStops.push(i / (points.length - 1)));
  }

  /** A navigation buoy at every waypoint: the model's template cloned, its strobe pulsing on its own
   *  material and brightening as the shuttle comes up to it. */
  private addGates(root: THREE.Object3D): void {
    if (!this.path) return;
    const template = root.getObjectByName('buoy');
    for (let i = 1; i <= 5; i++) {
      const u = this.pathStops[i];
      const glow = uniform(0.4);
      const buoy = template ? template.clone(true) : new THREE.Group();
      const strobe = buoy.getObjectByName('buoy_strobe') as THREE.Mesh | undefined;
      if (strobe) {
        const material = new THREE.MeshBasicNodeMaterial();
        // a short double flash every 1.4 s, each buoy out of step with the next
        const phase = time.mul(0.72).add(i * 0.37).fract();
        const flash = smoothstep(0.0, 0.03, phase).mul(smoothstep(0.1, 0.05, phase)).add(smoothstep(0.16, 0.19, phase).mul(smoothstep(0.26, 0.21, phase)));
        material.colorNode = color('#ff5a48').mul(flash.mul(5).add(0.9)).mul(glow);
        this.bag.add(material);
        strobe.material = material;
      }
      // the buoy keeps station beside the route, a little below it, so the shuttle passes by it
      const point = this.path.getPoint(u);
      const forward = this.path.getTangent(u).normalize();
      const right = new THREE.Vector3().crossVectors(forward, v(0, 1, 0)).normalize();
      buoy.scale.setScalar(1.25);
      buoy.position.copy(point).addScaledVector(right, 3.6).add(v(0, -1.4, 0));
      buoy.rotation.y = i * 1.3;
      this.scene.add(buoy);
      this.gates.push({ mesh: buoy, glow });
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
    // a page that jumps between stops gets a cut to the stop in the same frame
    const cut = source ? !source.smooth : reduced;
    const k = source ? (cut ? source.nearest() : source.keyframe()) : 0;
    rig.update(k, dt, cut, this.pointer?.value ?? null);
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
    // the generated station is one piece: the whole wheel turns slowly about its hub
    if (this.wheel && !reduced) this.wheel.rotateZ(dt * 0.05);
    if (this.clouds && !reduced) this.clouds.rotation.y += dt * 0.004;
    if (this.planet && !reduced) this.planet.rotation.y += dt * 0.002;
    if (this.clouds && this.planet) this.uCloudShift.value = (this.clouds.rotation.y - this.planet.rotation.y) / (Math.PI * 2);

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
