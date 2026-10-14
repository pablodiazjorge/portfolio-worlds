import type { Light, Material, Mesh, Object3D, SkinnedMesh, Texture } from 'three/webgpu';

interface Disposable {
  dispose(): void;
}

function isTexture(value: unknown): value is Texture {
  return !!value && typeof value === 'object' && (value as Texture).isTexture === true;
}

function collectMaterial(material: Material, textures: Set<Texture>): void {
  for (const value of Object.values(material)) {
    if (isTexture(value)) textures.add(value);
  }
  material.dispose();
}

/** Frees geometries, materials, textures, shadow maps and skeletons under `root`. */
export function disposeObject(root: Object3D): void {
  const textures = new Set<Texture>();
  root.traverse((object) => {
    const mesh = object as Mesh;
    mesh.geometry?.dispose();
    const material = mesh.material as Material | Material[] | undefined;
    if (material) {
      for (const m of Array.isArray(material) ? material : [material]) collectMaterial(m, textures);
    }
    const skinned = object as SkinnedMesh;
    if (skinned.isSkinnedMesh) skinned.skeleton?.dispose();
    const light = object as Light;
    if (light.isLight) light.dispose();
  });
  for (const texture of textures) texture.dispose();
}

/** Collects resources a scene creates outside its graph (render targets, node textures, loaders). */
export class DisposeBag {
  private readonly items: Disposable[] = [];
  private readonly callbacks: (() => void)[] = [];

  add<T extends Disposable>(item: T): T {
    this.items.push(item);
    return item;
  }

  defer(callback: () => void): void {
    this.callbacks.push(callback);
  }

  dispose(): void {
    for (const callback of this.callbacks.splice(0)) callback();
    for (const item of this.items.splice(0)) item.dispose();
  }
}
