import { Mesh, Vector3 } from 'three/webgpu';

/**
 * Coarse height lookup built from mesh vertices, used to keep cameras above the surface
 * without raycasting every frame.
 */
export class HeightField {
  private readonly heights: Float32Array;
  private readonly minX: number;
  private readonly minZ: number;
  private readonly cell: number;
  private readonly size: number;

  /**
   * @param meshes the surface, or several meshes whose tops count (buildings, props)
   * @param grid reuse another field's grid; cells nothing covers then stay far below ground
   */
  constructor(meshes: Mesh | Mesh[], cells = 160, grid?: HeightField) {
    const list = Array.isArray(meshes) ? meshes : [meshes];
    const v = new Vector3();
    const points: number[] = [];
    let minX = Infinity;
    let maxX = -Infinity;
    let minZ = Infinity;
    let maxZ = -Infinity;
    for (const mesh of list) {
      mesh.updateWorldMatrix(true, false);
      const position = mesh.geometry.getAttribute('position');
      for (let i = 0; i < position.count; i++) {
        v.fromBufferAttribute(position, i).applyMatrix4(mesh.matrixWorld);
        points.push(v.x, v.y, v.z);
        minX = Math.min(minX, v.x);
        maxX = Math.max(maxX, v.x);
        minZ = Math.min(minZ, v.z);
        maxZ = Math.max(maxZ, v.z);
      }
    }
    if (grid) {
      this.size = grid.size;
      this.minX = grid.minX;
      this.minZ = grid.minZ;
      this.cell = grid.cell;
    } else {
      this.size = cells;
      this.minX = minX;
      this.minZ = minZ;
      this.cell = Math.max(maxX - minX, maxZ - minZ) / (cells - 1);
    }
    const n = this.size;
    this.heights = new Float32Array(n * n).fill(-Infinity);
    for (let i = 0; i < points.length; i += 3) {
      const gx = Math.round((points[i] - this.minX) / this.cell);
      const gz = Math.round((points[i + 2] - this.minZ) / this.cell);
      if (gx < 0 || gz < 0 || gx >= n || gz >= n) continue;
      const index = gz * n + gx;
      this.heights[index] = Math.max(this.heights[index], points[i + 1]);
    }
    this.fillGaps(grid ? -1e4 : 0);
  }

  /** Spreads heights into empty cells, which also pads small objects by a few cells. */
  private fillGaps(empty: number): void {
    const n = this.size;
    for (let pass = 0; pass < 4; pass++) {
      // read from a snapshot so one pass only grows each filled area by a single cell
      const before = this.heights.slice();
      for (let z = 0; z < n; z++) {
        for (let x = 0; x < n; x++) {
          const i = z * n + x;
          if (before[i] !== -Infinity) continue;
          let sum = 0;
          let count = 0;
          for (const [dx, dz] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
            const nx = x + dx;
            const nz = z + dz;
            if (nx < 0 || nz < 0 || nx >= n || nz >= n) continue;
            const h = before[nz * n + nx];
            if (h !== -Infinity) {
              sum += h;
              count++;
            }
          }
          if (count) this.heights[i] = sum / count;
        }
      }
    }
    for (let i = 0; i < this.heights.length; i++) if (this.heights[i] === -Infinity) this.heights[i] = empty;
  }

  /** Height under (x, z), interpolated between cells. */
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
