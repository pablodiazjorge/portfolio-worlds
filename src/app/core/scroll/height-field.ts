import { Mesh, Vector3 } from 'three/webgpu';

/**
 * Coarse ground height lookup built from a terrain mesh's vertices, used to keep cameras
 * above the surface without raycasting every frame.
 */
export class HeightField {
  private readonly heights: Float32Array;
  private readonly minX: number;
  private readonly minZ: number;
  private readonly cell: number;
  private readonly size: number;

  constructor(mesh: Mesh, cells = 160) {
    mesh.updateWorldMatrix(true, false);
    const position = mesh.geometry.getAttribute('position');
    const v = new Vector3();
    let minX = Infinity;
    let maxX = -Infinity;
    let minZ = Infinity;
    let maxZ = -Infinity;
    const world = new Float32Array(position.count * 3);
    for (let i = 0; i < position.count; i++) {
      v.fromBufferAttribute(position, i).applyMatrix4(mesh.matrixWorld);
      world.set([v.x, v.y, v.z], i * 3);
      minX = Math.min(minX, v.x);
      maxX = Math.max(maxX, v.x);
      minZ = Math.min(minZ, v.z);
      maxZ = Math.max(maxZ, v.z);
    }
    this.size = cells;
    this.minX = minX;
    this.minZ = minZ;
    this.cell = Math.max(maxX - minX, maxZ - minZ) / (cells - 1);
    this.heights = new Float32Array(cells * cells).fill(-Infinity);
    for (let i = 0; i < position.count; i++) {
      const gx = Math.round((world[i * 3] - minX) / this.cell);
      const gz = Math.round((world[i * 3 + 2] - minZ) / this.cell);
      const index = gz * cells + gx;
      this.heights[index] = Math.max(this.heights[index], world[i * 3 + 1]);
    }
    this.fillGaps();
  }

  private fillGaps(): void {
    const n = this.size;
    for (let pass = 0; pass < 4; pass++) {
      for (let z = 0; z < n; z++) {
        for (let x = 0; x < n; x++) {
          const i = z * n + x;
          if (this.heights[i] !== -Infinity) continue;
          let sum = 0;
          let count = 0;
          for (const [dx, dz] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
            const nx = x + dx;
            const nz = z + dz;
            if (nx < 0 || nz < 0 || nx >= n || nz >= n) continue;
            const h = this.heights[nz * n + nx];
            if (h !== -Infinity) {
              sum += h;
              count++;
            }
          }
          if (count) this.heights[i] = sum / count;
        }
      }
    }
    for (let i = 0; i < this.heights.length; i++) if (this.heights[i] === -Infinity) this.heights[i] = 0;
  }

  /** Ground height under (x, z), interpolated between cells. */
  at(x: number, z: number): number {
    const n = this.size;
    const fx = Math.min(n - 1.001, Math.max(0, (x - this.minX) / this.cell));
    const fz = Math.min(n - 1.001, Math.max(0, (z - this.minZ) / this.cell));
    const x0 = Math.floor(fx);
    const z0 = Math.floor(fz);
    const tx = fx - x0;
    const tz = fz - z0;
    const h = this.heights;
    const a = h[z0 * n + x0] * (1 - tx) + h[z0 * n + x0 + 1] * tx;
    const b = h[(z0 + 1) * n + x0] * (1 - tx) + h[(z0 + 1) * n + x0 + 1] * tx;
    return a * (1 - tz) + b * tz;
  }
}
