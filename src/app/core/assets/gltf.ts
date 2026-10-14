import { GLTFLoader, type GLTF } from 'three/addons/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';
import { fetchBuffer } from './buffer-cache';

let loader: GLTFLoader | null = null;

/**
 * Parses a fresh copy of a GLB on every call, so a scene can change and dispose its copy
 * without affecting the next visit. The download itself happens once per session.
 */
export async function loadGltf(url: string, onProgress?: (fraction: number) => void): Promise<GLTF> {
  const buffer = await fetchBuffer(url, onProgress);
  loader ??= new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);
  return loader.parseAsync(buffer.slice(0), '');
}
