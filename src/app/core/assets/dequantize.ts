import { BufferAttribute, BufferGeometry, InterleavedBufferAttribute, Mesh, Object3D } from 'three/webgpu';

function toFloat(attribute: BufferAttribute | InterleavedBufferAttribute): BufferAttribute {
  const size = attribute.itemSize;
  const out = new Float32Array(attribute.count * size);
  for (let i = 0; i < attribute.count; i++) {
    out[i * size] = attribute.getX(i);
    if (size > 1) out[i * size + 1] = attribute.getY(i);
    if (size > 2) out[i * size + 2] = attribute.getZ(i);
    if (size > 3) out[i * size + 3] = attribute.getW(i);
  }
  return new BufferAttribute(out, size);
}

function dequantizeGeometry(geometry: BufferGeometry): void {
  for (const name of ['position', 'normal', 'uv', 'tangent']) {
    const attribute = geometry.getAttribute(name) as BufferAttribute | InterleavedBufferAttribute | undefined;
    if (!attribute) continue;
    const array = (attribute as BufferAttribute).array ?? (attribute as InterleavedBufferAttribute).data.array;
    if (array instanceof Float32Array && !(attribute as InterleavedBufferAttribute).isInterleavedBufferAttribute) continue;
    geometry.setAttribute(name, toFloat(attribute));
  }
}

/**
 * Meshopt quantization stores positions as integers and moves the scale into the mesh node.
 * For models whose parts animate and whose shaders read local positions, this converts the
 * attributes back to floats and bakes the node transform into the geometry, so every mesh sits
 * at its parent's origin and positions are in scene units. Animate the parent nodes instead.
 */
export function dequantizeMeshes(root: Object3D, include: (mesh: Mesh) => boolean = () => true): void {
  const meshes: Mesh[] = [];
  root.traverse((object) => {
    const mesh = object as Mesh & { isInstancedMesh?: boolean };
    if (mesh.isMesh && !mesh.isInstancedMesh && include(mesh)) meshes.push(mesh);
  });
  for (const mesh of meshes) {
    dequantizeGeometry(mesh.geometry);
    mesh.updateMatrix();
    mesh.geometry.applyMatrix4(mesh.matrix);
    mesh.position.set(0, 0, 0);
    mesh.quaternion.identity();
    mesh.scale.set(1, 1, 1);
    mesh.updateMatrix();
    if (!mesh.geometry.getAttribute('normal')) mesh.geometry.computeVertexNormals();
    mesh.geometry.computeBoundingBox();
    mesh.geometry.computeBoundingSphere();
  }
}
