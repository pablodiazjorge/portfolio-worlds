import * as THREE from 'three/webgpu';
import {
  abs,
  color,
  exp,
  float,
  floor,
  fract,
  length,
  max,
  mix,
  mx_noise_float,
  pass,
  positionLocal,
  positionWorld,
  screenUV,
  sin,
  smoothstep,
  step,
  texture,
  uniform,
  uv,
  vec2,
} from 'three/tsl';
import { bloom } from 'three/addons/tsl/display/BloomNode.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { dequantizeMeshes } from '../../core/assets/dequantize';
import { loadGltf } from '../../core/assets/gltf';
import { DisposeBag, disposeObject } from '../../core/engine/dispose';
import { EngineContext, WorldScene } from '../../core/engine/world-scene';
import { CameraKey, KeyframeRig, PointerTracker } from '../../core/scroll/camera-rig';
import { ScrollDirector } from '../../core/scroll/scroll-director';

/**
 * Which side of the screen the text takes at each stop (-1 left, 1 right); the drone flies to
 * the other side. The project list (stops 7 and 8) scrolls freely, so the drone parks high up.
 */
const SIDES = [-1, 1, -1, 1, -1, 1, -1, -1, -1, -1] as const;
const HEIGHTS = [1.35, 1.3, 1.35, 1.25, 1.35, 1.25, 1.35, 1.7, 1.7, 1.3];
const DEPTHS = [0.2, 0.25, 0.2, 0.25, 0.2, 0.25, 0.2, -0.4, -0.4, 0.3];

const FLOOR_Y = -1.6;
const CYAN = '#5ee0ff';
/** The chain from the drone's hook to the monitor's eyebolt; shorter on portrait screens. */
const CHAIN_LENGTH = 1.15;
const CHAIN_LENGTH_PORTRAIT = 0.75;
const CHAIN_NODES = 10;
const LINK_SPACING = 0.084;
const GRAVITY = 9.8;

export class AerisScene implements WorldScene {
  readonly scene = new THREE.Scene();
  readonly camera = new THREE.PerspectiveCamera(30, 1, 0.05, 100);

  private readonly bag = new DisposeBag();
  private readonly pointer: PointerTracker | null;
  private rig: KeyframeRig | null = null;
  private scroll: ScrollDirector | null = null;
  private pipeline: THREE.RenderPipeline | null = null;

  // the drone and its flight
  private readonly drone = new THREE.Group();
  private readonly spinners: { pivot: THREE.Object3D; direction: number }[] = [];
  private gimbal: THREE.Object3D | null = null;
  private hook: THREE.Object3D | null = null;
  private readonly flightGoal = new THREE.Vector3();
  /** Where the flight physics put the drone; the drawn position adds the hover bob. */
  private readonly flightPos = new THREE.Vector3();
  private readonly velocity = new THREE.Vector3();
  private readonly acceleration = new THREE.Vector3();
  private bank = 0;
  private pitch = 0;
  private turn = 0;
  private propAngle = 0;
  private lateral = 1.6;
  private portrait = false;
  private readonly droneLight = new THREE.PointLight(CYAN, 0, 4, 2);

  private readonly uGlow = uniform(1);
  private readonly uDroneXZ = uniform(new THREE.Vector2());
  private readonly uDisc = uniform(0);

  // the monitor on its chain
  private readonly monitor = new THREE.Group();
  private readonly chainNow: THREE.Vector3[] = [];
  private readonly chainBefore: THREE.Vector3[] = [];
  private readonly chainCurve: THREE.CatmullRomCurve3;
  private chainLength = CHAIN_LENGTH;
  private links: THREE.InstancedMesh | null = null;
  private twist = 0;
  private twistRate = 0;
  private lastStep = 1 / 120;
  private readonly hookNow = new THREE.Vector3();
  private readonly hookBefore = new THREE.Vector3();
  private readonly uBlink = uniform(1);
  /** The picture on the tube, kept so it can be redrawn. */
  private screenMap: THREE.CanvasTexture | null = null;
  private readonly uPhosphor = uniform(1);
  private readonly screenLight = new THREE.PointLight('#7cff8e', 0, 1.6, 2);

  constructor(private readonly ctx: EngineContext) {
    this.pointer = ctx.touch || ctx.reducedMotion ? null : new PointerTracker();
    this.scene.backgroundNode = this.studioNode();
    const key = new THREE.DirectionalLight('#dfe8ff', 1.1);
    key.position.set(-3, 5, 4);
    const rim = new THREE.DirectionalLight('#8fb8ff', 0.9);
    rim.position.set(4, 3, -4);
    this.scene.add(key, rim, new THREE.HemisphereLight('#6f86b0', '#0a0d16', 0.35));
    this.scene.add(this.drone, this.monitor);
    this.droneLight.position.set(0, -0.8, 0.25);
    this.drone.add(this.droneLight);
    const segment = CHAIN_LENGTH / (CHAIN_NODES - 1);
    for (let i = 0; i < CHAIN_NODES; i++) {
      const at = new THREE.Vector3(0, -0.2 - i * segment, 0);
      this.chainNow.push(at);
      this.chainBefore.push(at.clone());
    }
    this.chainCurve = new THREE.CatmullRomCurve3(this.chainNow, false, 'catmullrom', 0.5);
  }

  attachScroll(source: ScrollDirector | null): void {
    this.scroll = source;
  }

  activate(): void {
    this.ctx.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.ctx.renderer.toneMappingExposure = 1.0;
  }

  async init(onProgress: (fraction: number) => void): Promise<void> {
    const [droneGltf, monitorGltf] = await Promise.all([
      loadGltf('models/aeris/drone.glb', (f) => onProgress(f * 0.45)),
      loadGltf('models/aeris/monitor.glb', (f) => onProgress(0.45 + f * 0.4)),
      this.environment(),
      this.loadScreenFont(),
    ]);
    this.buildDrone(droneGltf.scene);
    this.buildMonitor(monitorGltf.scene);
    this.addFloor();
    this.rig = new KeyframeRig(this.camera, this.keys(), { damping: 2.8, swayAmount: 0.22 });
    this.setupPipeline();
    // start with the monitor hanging straight under the drone at the first stop
    this.stopPosition(0, this.flightPos);
    this.drone.position.copy(this.flightPos);
    this.drone.updateMatrixWorld(true);
    this.hookPoint(this.hookNow);
    this.hookBefore.copy(this.hookNow);
    this.restChain();
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
    this.scene.environmentIntensity = 0.35;
  }

  private async loadScreenFont(): Promise<void> {
    try {
      await document.fonts.load("64px 'VT323'");
    } catch {
      // the fallback monospace is drawn instead
    }
  }

  /** A dark studio: a cold pool of light in the middle fading to black at the edges. */
  private studioNode() {
    const centre = screenUV.sub(vec2(0.5, 0.42)).mul(vec2(1.2, 1));
    const vignette = smoothstep(0.08, 0.95, centre.length());
    return mix(color('#0c1328'), color('#020308'), vignette);
  }

  // --- the drone ---------------------------------------------------------------------------

  private buildDrone(root: THREE.Object3D): void {
    dequantizeMeshes(root);
    const materials = this.droneMaterials();
    root.traverse((o) => {
      const mesh = o as THREE.Mesh;
      if (!mesh.isMesh) return;
      const source = mesh.material as THREE.Material;
      const replacement = materials.get(source.name);
      if (replacement) mesh.material = replacement;
      source.dispose();
    });
    for (const key of ['fl', 'fr', 'bl', 'br']) {
      const pivot = root.getObjectByName(`spin_${key}`);
      if (!pivot) continue;
      const disc = new THREE.Mesh(this.discGeometry(), this.discMaterial());
      disc.rotation.x = -Math.PI / 2;
      disc.position.y = 0.012;
      pivot.add(disc);
      this.spinners.push({ pivot, direction: key === 'fl' || key === 'br' ? 1 : -1 });
    }
    this.gimbal = root.getObjectByName('gimbal_pivot') ?? null;
    this.hook = root.getObjectByName('hook') ?? null;
    this.drone.add(root);
  }

  /** Gunmetal and carbon with a lacquer on top, and light strips that the bloom picks up. */
  private droneMaterials(): Map<string, THREE.Material> {
    const p = positionLocal;
    const map = new Map<string, THREE.Material>();

    const body = new THREE.MeshPhysicalNodeMaterial({ color: '#15171c', roughness: 0.42, clearcoat: 0.45, clearcoatRoughness: 0.25 });
    body.roughnessNode = float(0.38).add(mx_noise_float(p.mul(40)).mul(0.06));
    map.set('body', body);
    map.set('body_light', new THREE.MeshPhysicalNodeMaterial({ color: '#262a33', roughness: 0.48, clearcoat: 0.35, clearcoatRoughness: 0.3 }));

    const carbon = new THREE.MeshPhysicalNodeMaterial({ roughness: 0.42, clearcoat: 0.5, clearcoatRoughness: 0.25 });
    const weave = p.xz.mul(55);
    const cell = floor(weave.x.add(weave.y));
    const across = fract(weave.x.sub(weave.y).mul(0.5));
    const yarn = sin(fract(weave.x.add(weave.y)).mul(Math.PI)).mul(0.5).add(0.5);
    const direction = step(0.5, fract(cell.mul(0.5)));
    const sheen = mix(yarn, sin(across.mul(Math.PI)), direction);
    carbon.colorNode = mix(color('#0e0f12'), color('#2e3138'), sheen.pow(1.6));
    carbon.roughnessNode = mix(float(0.5), float(0.3), sheen);
    map.set('carbon', carbon);

    const metal = new THREE.MeshStandardNodeMaterial({ color: '#6e737c', metalness: 1, roughness: 0.5 });
    metal.roughnessNode = float(0.46).add(mx_noise_float(p.mul(vec2(160, 7).xyx)).mul(0.06));
    map.set('metal', metal);
    map.set('metal_dark', new THREE.MeshStandardNodeMaterial({ color: '#3a3e46', metalness: 0.9, roughness: 0.42 }));

    const glow = new THREE.MeshBasicNodeMaterial();
    glow.colorNode = color(CYAN).mul(1.5).mul(this.uGlow);
    map.set('glow', glow);

    // the blades spin faster than the eye follows: faint, with the blur disc standing in for them
    map.set('prop', new THREE.MeshPhysicalNodeMaterial({ color: '#0f1114', roughness: 0.3, clearcoat: 0.5, transparent: true, opacity: 0.32, depthWrite: false }));
    map.set('glass', new THREE.MeshPhysicalNodeMaterial({ color: '#04060a', roughness: 0.03, clearcoat: 1, clearcoatRoughness: 0.02 }));
    map.set('rubber', new THREE.MeshStandardNodeMaterial({ color: '#0e0f12', roughness: 0.9 }));
    for (const [name, material] of map) {
      material.name = name;
      this.bag.add(material);
    }
    return map;
  }

  private discGeometryCache: THREE.CircleGeometry | null = null;
  private discMaterialCache: THREE.MeshBasicNodeMaterial | null = null;

  private discGeometry(): THREE.CircleGeometry {
    this.discGeometryCache ??= this.bag.add(new THREE.CircleGeometry(0.7, 40));
    return this.discGeometryCache;
  }

  /** The blur of the spinning blades: a faint sheet with a brighter rim. */
  private discMaterial(): THREE.MeshBasicNodeMaterial {
    if (this.discMaterialCache) return this.discMaterialCache;
    const material = new THREE.MeshBasicNodeMaterial({ transparent: true, depthWrite: false, side: THREE.DoubleSide });
    const r = uv().sub(0.5).length().mul(2);
    const sheet = smoothstep(0.12, 0.3, r).mul(float(1).sub(smoothstep(0.84, 0.98, r)));
    const rim = smoothstep(0.9, 0.96, r).mul(float(1).sub(smoothstep(0.97, 1, r)));
    material.colorNode = mix(color('#9aa3b0'), color(CYAN), rim);
    material.opacityNode = sheet.mul(0.11).add(rim.mul(0.26)).mul(this.uDisc);
    this.discMaterialCache = this.bag.add(material);
    return material;
  }

  // --- the monitor on its chain -------------------------------------------------------------

  private buildMonitor(root: THREE.Object3D): void {
    dequantizeMeshes(root);
    const body = root.getObjectByName('monitor');
    const link = root.getObjectByName('link') as THREE.Mesh | undefined;
    const materials = this.monitorMaterials();
    body?.traverse((o) => {
      const mesh = o as THREE.Mesh;
      if (!mesh.isMesh) return;
      const source = mesh.material as THREE.Material;
      const replacement = materials.get(source.name);
      if (replacement) mesh.material = replacement;
      source.dispose();
    });
    if (body) this.monitor.add(body);
    this.monitor.scale.setScalar(this.portrait ? 0.68 : 0.85);
    this.screenLight.position.set(0, -0.5, 0.5);
    this.monitor.add(this.screenLight);

    if (link) {
      link.removeFromParent();
      const count = Math.floor(CHAIN_LENGTH / LINK_SPACING);
      const links = new THREE.InstancedMesh(this.bag.add(link.geometry), materials.get('metal')!, count);
      links.frustumCulled = false;
      this.links = links;
      this.scene.add(links);
      (link.material as THREE.Material).dispose();
    }
  }

  private readonly pivot = new THREE.Vector3();

  /** The chain's top point in the world: the eyebolt under the drone. */
  private hookPoint(out: THREE.Vector3): THREE.Vector3 {
    return this.hook ? this.hook.getWorldPosition(out) : out.copy(this.drone.position).add(this.scratchB.set(0, -0.2, 0));
  }

  /** Hangs the chain straight down from the hook, at rest. */
  private restChain(): void {
    const top = this.hookPoint(this.pivot);
    this.hookNow.copy(top);
    this.hookBefore.copy(top);
    const segment = this.chainLength / (CHAIN_NODES - 1);
    for (let i = 0; i < CHAIN_NODES; i++) {
      this.chainNow[i].set(top.x, top.y - i * segment, top.z);
      this.chainBefore[i].copy(this.chainNow[i]);
    }
    this.twist = 0;
    this.twistRate = 0;
    this.placeChain();
  }

  private monitorMaterials(): Map<string, THREE.Material> {
    const map = new Map<string, THREE.Material>();
    const p = positionLocal;
    // beige plastic that has seen some years: yellowed, with grime in patches
    const grime = smoothstep(0.3, 0.85, mx_noise_float(p.mul(7.5)).mul(0.5).add(mx_noise_float(p.mul(31)).mul(0.5)));
    const plastic = (base: string, dirt: string) => {
      const material = new THREE.MeshStandardNodeMaterial({ roughness: 0.55 });
      material.colorNode = mix(color(base), color(dirt), grime.mul(0.55));
      material.roughnessNode = float(0.48).add(grime.mul(0.25));
      return material;
    };
    map.set('case', plastic('#cbc3aa', '#8f8769'));
    map.set('case_dark', plastic('#aea68d', '#7d7560'));
    map.set('vent', new THREE.MeshStandardNodeMaterial({ color: '#3e3a2e', roughness: 0.9 }));
    map.set('frame', new THREE.MeshStandardNodeMaterial({ color: '#2b2c30', roughness: 0.6 }));
    map.set('metal', new THREE.MeshStandardNodeMaterial({ color: '#9a9ea8', metalness: 1, roughness: 0.38 }));
    map.set('led', new THREE.MeshBasicNodeMaterial({ color: '#ffb347' }));
    map.set('screen', this.screenMaterial());
    for (const [name, material] of map) {
      material.name = name;
      this.bag.add(material);
    }
    return map;
  }

  /**
   * The picture on the tube: the prompt drawn on a canvas as a mask, coloured phosphor green
   * with scan lines and a vignette, and made to blink from the frame loop.
   */
  private screenMaterial(): THREE.Material {
    const canvas = document.createElement('canvas');
    canvas.width = 640;
    canvas.height = 480;
    const g = canvas.getContext('2d')!;
    g.fillStyle = '#000';
    g.fillRect(0, 0, canvas.width, canvas.height);
    g.font = "100px 'VT323', 'Courier New', monospace";
    g.textBaseline = 'top';
    g.fillStyle = '#fff';
    g.shadowColor = 'rgba(255,255,255,0.8)';
    g.shadowBlur = 5;
    const text = '>Hello World!';
    g.fillText(text, 30, 44);
    const width = g.measureText(text).width;
    g.fillRect(30 + width + 10, 56, 40, 78);
    const map = this.bag.add(new THREE.CanvasTexture(canvas));
    this.screenMap = map;
    // the model's UVs follow the glTF convention, with the first row of the picture at the top
    map.flipY = false;
    map.colorSpace = THREE.NoColorSpace;
    map.minFilter = THREE.LinearMipmapLinearFilter;
    map.anisotropy = 4;

    const material = new THREE.MeshStandardNodeMaterial({ color: '#000000', roughness: 0.32, metalness: 0 });
    // a hint of the room in the glass, not a mirror of its light panels
    material.envMapIntensity = 0.05;
    const mask = texture(map, uv()).r;
    const scan = sin(uv().y.mul(480 * Math.PI)).mul(0.5).add(0.5).mul(0.3).add(0.7);
    const centre = uv().sub(0.5);
    const vignette = float(1).sub(smoothstep(0.42, 0.78, centre.length()));
    const glow = color('#8cffa0').mul(mask).mul(this.uBlink).mul(1.6);
    const idle = color('#0f2b1c').mul(0.5).mul(vignette);
    material.emissiveNode = glow.add(idle).mul(scan).mul(this.uPhosphor);
    return material;
  }

  // --- floor, camera and post-processing ----------------------------------------------------

  /** A faint cyan grid that fades into the dark, with a pool of light under the drone. */
  private addFloor(): void {
    const geometry = this.bag.add(new THREE.PlaneGeometry(40, 40));
    geometry.rotateX(-Math.PI / 2);
    const material = new THREE.MeshBasicNodeMaterial({ transparent: true, depthWrite: false });
    material.blending = THREE.AdditiveBlending;
    const p = positionWorld.xz;
    const toLine = abs(fract(p.add(0.5)).sub(0.5));
    const lines = max(float(1).sub(smoothstep(0.012, 0.032, toLine.x)), float(1).sub(smoothstep(0.012, 0.032, toLine.y)));
    const toMajor = abs(fract(p.mul(0.25).add(0.5)).sub(0.5)).mul(4);
    const major = max(float(1).sub(smoothstep(0.02, 0.05, toMajor.x)), float(1).sub(smoothstep(0.02, 0.05, toMajor.y)));
    const fade = float(1).sub(smoothstep(2.5, 11, length(p)));
    const pool = exp(length(p.sub(this.uDroneXZ)).div(1.35).pow(2).negate()).mul(0.55);
    const grid = lines.mul(0.12).add(major.mul(0.1)).mul(fade);
    material.colorNode = color(CYAN).mul(grid.add(pool.mul(lines.mul(0.4).add(0.3))));
    this.bag.add(material);
    const floor = new THREE.Mesh(geometry, material);
    floor.position.y = FLOOR_Y;
    floor.renderOrder = 0;
    this.scene.add(floor);
  }

  private keys(): CameraKey[] {
    const v = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);
    const angles = [6, -8, 7, -7, 6, -6, 8, 2, -3, 5];
    const radii = [7.9, 7.7, 7.7, 7.7, 7.7, 7.7, 7.7, 9.2, 9.4, 7.6];
    const heights = [0.85, 0.75, 0.9, 0.7, 0.9, 0.7, 0.9, 1.45, 1.5, 0.8];
    return SIDES.map((side, i) => {
      const a = THREE.MathUtils.degToRad(angles[i]);
      const high = i === 7 || i === 8 ? 0.4 : 0;
      return {
        position: v(Math.sin(a) * radii[i], heights[i], Math.cos(a) * radii[i]),
        // the view shifts away from the text, so the studio sits in the free half
        target: v(side * 0.5, 0.35 + high, 0),
        fov: 32,
      };
    });
  }

  private setupPipeline(): void {
    const scenePass = pass(this.scene, this.camera);
    const sceneColor = scenePass.getTextureNode();
    // only the light strips and the tube glow; the beige plastic stays below the threshold
    const glow = bloom(sceneColor, this.ctx.quality === 'low' ? 0.25 : 0.34, 0.4, 0.96);
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

  // --- frame ----------------------------------------------------------------------------------

  /** Where the drone rests at a stop: the side away from the text, up in the free half. */
  private stopPosition(index: number, out: THREE.Vector3): THREE.Vector3 {
    const i = THREE.MathUtils.clamp(index, 0, SIDES.length - 1);
    // on portrait screens the text sits below, so the drone hangs over the middle of the view,
    // which the camera keys have shifted sideways by 0.6
    const lateral = this.portrait ? -0.5 : this.lateral;
    return out.set(-SIDES[i] * lateral, HEIGHTS[i] + (this.portrait ? 0.15 : 0), DEPTHS[i]);
  }

  /**
   * The point the drone is heading for at keyframe position k: between two stops it is the
   * straight line between them, bulged up and towards the camera so a crossing of the studio
   * passes in front of the monitor instead of through its chain.
   */
  private flightGoalAt(k: number, out: THREE.Vector3): THREE.Vector3 {
    const i = Math.min(SIDES.length - 2, Math.max(0, Math.floor(k)));
    const u = THREE.MathUtils.clamp(k - i, 0, 1);
    const from = this.stopPosition(i, new THREE.Vector3());
    const to = this.stopPosition(i + 1, new THREE.Vector3());
    out.lerpVectors(from, to, u);
    if (Math.abs(to.x - from.x) > 0.8) {
      const arc = Math.sin(Math.PI * u);
      out.y += 0.3 * arc;
      out.z += 0.7 * arc;
    }
    return out;
  }

  update(dt: number, elapsed: number): void {
    const rig = this.rig;
    if (!rig) return;
    const reduced = this.ctx.reducedMotion;
    const source = this.scroll;
    // a page that jumps between stops gets a cut to the stop in the same frame
    const cut = source ? !source.smooth : reduced;
    const k = source ? (cut ? source.nearest() : source.keyframe()) : 0;
    rig.update(k, dt, cut, this.pointer?.value ?? null);
    const step = Math.min(dt, 1 / 30);

    this.flyDrone(k, step, elapsed, reduced, cut);
    this.swingChain(step, elapsed, reduced);
    this.blinkScreen(elapsed, reduced);
  }

  private flyDrone(k: number, dt: number, elapsed: number, reduced: boolean, cut: boolean): void {
    const goal = this.flightGoalAt(k, this.flightGoal);
    const drone = this.drone;
    const pos = this.flightPos;
    if (cut) {
      pos.copy(goal);
      this.velocity.set(0, 0, 0);
    } else {
      // a damped spring follows the goal, so the drone leans into every start and stop
      const omega = 5.5;
      const zeta = 0.92;
      const acc = this.acceleration;
      acc.subVectors(goal, pos).multiplyScalar(omega * omega).addScaledVector(this.velocity, -2 * zeta * omega);
      this.velocity.addScaledVector(acc, dt);
      pos.addScaledVector(this.velocity, dt);
    }
    const v = this.velocity;
    const a = this.acceleration;
    const ease = 1 - Math.exp(-dt * 7);
    this.bank += (THREE.MathUtils.clamp(-a.x * 0.03 - v.x * 0.16, -0.55, 0.55) - this.bank) * ease;
    this.pitch += (THREE.MathUtils.clamp(a.z * 0.02 + v.z * 0.1, -0.35, 0.35) - this.pitch) * ease;
    this.turn += (THREE.MathUtils.clamp(v.x * 0.45, -0.85, 0.85) - this.turn) * ease * 0.6;
    // at rest the nose turns towards the middle of the studio; the turn follows where the drone
    // is, not which stop is nearest, so it never flips in the middle of a crossing
    const lateral = Math.max(0.3, this.portrait ? 0.5 : this.lateral);
    const lean = THREE.MathUtils.clamp(pos.x / lateral, -1, 1);
    drone.position.copy(pos);
    if (!reduced) drone.position.y += Math.sin(elapsed * 1.5) * 0.03;
    drone.rotation.set(0, 0, 0);
    drone.rotation.y = Math.PI - lean * 0.5 + this.turn + (reduced ? 0 : Math.sin(elapsed * 0.6) * 0.03);
    drone.rotateZ(this.bank + (reduced ? 0 : Math.sin(elapsed * 0.9) * 0.02));
    drone.rotateX(this.pitch + (reduced ? 0 : Math.sin(elapsed * 0.7 + 1) * 0.015));

    const speed = v.length();
    this.propAngle += dt * (reduced ? 0 : 30 + speed * 12);
    for (const spinner of this.spinners) spinner.pivot.rotation.y = this.propAngle * spinner.direction;
    this.uDisc.value = reduced ? 0 : 1;
    if (this.gimbal) this.gimbal.rotation.x = -0.35 + Math.sin(elapsed * 0.5) * 0.05;
    // the light strips breathe a little
    this.uGlow.value = reduced ? 1 : 0.9 + 0.1 * Math.sin(elapsed * 2.1);
    this.droneLight.intensity = 0.6 * this.uGlow.value;
    this.uDroneXZ.value.set(drone.position.x, drone.position.z);
    drone.updateMatrixWorld(true);
  }

  /**
   * The chain is a rope of points: each step they keep their momentum, fall, get pushed by the
   * drone's downwash, and are then pulled back to one link's distance from their neighbours.
   * The monitor is the heavy last point, so the links follow it as much as it follows them.
   * Every frame simulates exactly the time it covers, in substeps no longer than 1/120 s, so
   * the motion never skips or doubles a frame whatever the display's rate.
   */
  private swingChain(dt: number, elapsed: number, reduced: boolean): void {
    if (reduced) {
      this.restChain();
      return;
    }
    this.hookBefore.copy(this.hookNow);
    this.hookPoint(this.hookNow);
    const span = Math.min(dt, 0.1);
    const steps = Math.max(1, Math.ceil(span * 120));
    const h = span / steps;
    for (let i = 1; i <= steps; i++) this.stepChain(h, elapsed, i / steps);
    this.placeChain();
  }

  private readonly scratch = new THREE.Vector3();
  private readonly scratchB = new THREE.Vector3();

  private stepChain(h: number, elapsed: number, along: number): void {
    const now = this.chainNow;
    const before = this.chainBefore;
    const n = now.length;
    // the top link rides on the hook, so every move of the drone sets the chain swinging; the
    // hook's move this frame is spread over the substeps
    const top = this.pivot.lerpVectors(this.hookBefore, this.hookNow, along);
    now[0].copy(top);
    before[0].copy(top);
    const drone = this.drone.position;
    const lift = 0.8 + this.velocity.length() * 0.5;
    const push = this.scratch;
    // steps vary in length a little from frame to frame, so the carried momentum is rescaled
    const carry = (h / this.lastStep) * Math.pow(0.992, h * 120);
    this.lastStep = h;
    for (let i = 1; i < n; i++) {
      const p = now[i];
      const q = before[i];
      // velocity from the last step, with a little air resistance
      push.subVectors(p, q).multiplyScalar(carry);
      q.copy(p);
      // gravity, and the downwash: air pushed out and down from under the rotors
      let ax = 0.1 * Math.sin(elapsed * 0.37 + i * 0.3);
      let ay = -GRAVITY;
      let az = 0.06 * Math.sin(elapsed * 0.29 + 1.7);
      const dx = p.x - drone.x;
      const dz = p.z - drone.z;
      const d = Math.hypot(dx, dz) + 1e-4;
      const below = THREE.MathUtils.clamp((drone.y - p.y) / 1.6, 0, 1);
      const wash = 2.2 * lift * Math.exp(-((d / 1.0) * (d / 1.0))) * below;
      ax += (dx / d) * wash;
      ay -= wash * 0.5;
      az += (dz / d) * wash;
      p.add(push).addScaledVector(this.scratchB.set(ax, ay, az), h * h);
    }
    const segment = this.chainLength / (n - 1);
    for (let iteration = 0; iteration < 8; iteration++) {
      for (let i = 0; i < n - 1; i++) {
        const a = now[i];
        const b = now[i + 1];
        push.subVectors(b, a);
        const dist = push.length() || 1e-6;
        const correction = (dist - segment) / dist;
        // the pivot never moves and the monitor barely does
        const wa = i === 0 ? 0 : i + 1 === n - 1 ? 0.9 : 0.5;
        a.addScaledVector(push, correction * wa);
        b.addScaledVector(push, -correction * (1 - wa));
      }
    }
    // the monitor twists a little on its hook as it swings
    const bob = now[n - 1];
    const vx = (bob.x - before[n - 1].x) / h - this.velocity.x;
    const twistAcc = -3 * this.twist - 1.2 * this.twistRate + 0.35 * vx;
    this.twistRate += twistAcc * h;
    this.twist += this.twistRate * h;
  }

  private readonly up = new THREE.Vector3(0, 1, 0);
  private readonly tangent = new THREE.Vector3();
  private readonly linkPose = new THREE.Object3D();
  private readonly hang = new THREE.Quaternion();
  private readonly spin = new THREE.Quaternion();

  /** Hangs the monitor from the last point of the chain and lays the links along it. */
  private placeChain(): void {
    const now = this.chainNow;
    const n = now.length;
    const monitor = this.monitor;
    monitor.position.copy(now[n - 1]);
    this.tangent.subVectors(now[n - 2], now[n - 1]).normalize();
    this.hang.setFromUnitVectors(this.up, this.tangent);
    this.spin.setFromAxisAngle(this.up, this.twist);
    monitor.quaternion.copy(this.hang).multiply(this.spin);

    const links = this.links;
    if (!links) return;
    const curve = this.chainCurve;
    curve.updateArcLengths();
    const total = curve.getLength();
    const count = Math.min(Math.floor(CHAIN_LENGTH / LINK_SPACING), Math.floor(total / LINK_SPACING));
    links.count = count;
    const pose = this.linkPose;
    for (let i = 0; i < count; i++) {
      const t = Math.min(0.999, ((i + 0.5) * LINK_SPACING) / total);
      curve.getPointAt(t, pose.position);
      curve.getTangentAt(t, this.tangent).negate();
      pose.quaternion.setFromUnitVectors(this.up, this.tangent);
      // every link turns a quarter from the last; the final one lies across the eyebolt's ring
      pose.rotateY(((count - 1 - i) * Math.PI) / 2 + Math.PI / 2 + this.twist);
      pose.updateMatrix();
      links.setMatrixAt(i, pose.matrix);
    }
    links.instanceMatrix.needsUpdate = true;
  }

  private blinkScreen(elapsed: number, reduced: boolean): void {
    // on for most of a beat, off for the rest, with the phosphor taking a moment to die
    const beat = elapsed % 1.35;
    const on = beat < 0.92 ? 1 : Math.max(0, 1 - (beat - 0.92) / 0.09);
    this.uBlink.value = on;
    this.uPhosphor.value = reduced ? 1 : 0.95 + 0.05 * Math.sin(elapsed * 61.3) * Math.sin(elapsed * 13.1);
    this.screenLight.intensity = 0.08 + on * 0.3;
  }

  resize(width: number, height: number): void {
    const aspect = width / height;
    this.portrait = width < height;
    this.chainLength = this.portrait ? CHAIN_LENGTH_PORTRAIT : CHAIN_LENGTH;
    // a smaller load on a narrow screen, where the text takes the lower half
    this.drone.scale.setScalar(this.portrait ? 0.8 : 1);
    this.monitor.scale.setScalar(this.portrait ? 0.68 : 0.85);
    // how far to the side the drone parks, so it stays inside the frame on every screen
    this.lateral = THREE.MathUtils.clamp(aspect * 0.62, 0.8, 1.35);
    if (this.rig) {
      this.rig.fitViewport(width, height);
      return;
    }
    this.camera.aspect = aspect;
    this.camera.updateProjectionMatrix();
  }

  dispose(): void {
    this.pointer?.dispose();
    this.bag.dispose();
    disposeObject(this.scene);
    this.scene.clear();
  }
}
