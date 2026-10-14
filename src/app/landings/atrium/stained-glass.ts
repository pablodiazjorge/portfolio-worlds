/**
 * Stained glass and a small landscape drawn on canvases for the gallery's windows and frames.
 *
 * A window is a pointed opening with one or two lancets and, for two, a tracery oculus above. Each
 * lancet holds a saint: halo, head, shoulders and an A-shaped robe in two tones with folds, hands
 * before the chest, a canopy over the head and a ground band under the feet, all on a pale lattice
 * ground. The panes are an irregular grid, bigger than tesserae, with leads between them and
 * heavier leads along the silhouettes. Everything comes from a seed, so each window differs while
 * keeping the same hand.
 */

export interface GlassSpec {
  width: number;
  height: number;
  /** Where the lancets' arches spring, as a fraction of the height from the top (two lights). */
  spring: number;
  lights: 1 | 2;
  seed: number;
}

const ROBES = ['#1f4fb3', '#b0202a', '#2e7a46', '#6d3a9c', '#d4652d', '#1b7f9c'];
const MANTLES = ['#b0202a', '#d9a227', '#2e7a46', '#6d3a9c', '#1f4fb3', '#c84a2b'];
const PALES = ['#f6edd2', '#f8f3e4', '#dfe9f7', '#fbe9cd', '#e9f1dc'];
const SKIN = '#f2d6b6';
const HAIR = ['#5a3a1e', '#2b2b2b', '#a8782f', '#8c5a2a'];

function mulberry(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** A colour scaled by k; takes '#rrggbb' or an 'rgb(r,g,b)' it produced earlier. */
function shade(colour: string, k: number): string {
  let r: number, g: number, b: number;
  if (colour.startsWith('#')) {
    const n = parseInt(colour.slice(1), 16);
    r = (n >> 16) & 255;
    g = (n >> 8) & 255;
    b = n & 255;
  } else {
    [r, g, b] = colour.slice(4, -1).split(',').map(Number);
  }
  return `rgb(${Math.min(255, Math.round(r * k))},${Math.min(255, Math.round(g * k))},${Math.min(255, Math.round(b * k))})`;
}

/** The outline of a pointed light: jambs from the bottom up to the springing, a two-centre arch over. */
function lancetPath(ctx: CanvasRenderingContext2D, x0: number, x1: number, spring: number, bottom: number): number {
  const hw = (x1 - x0) / 2;
  const cx = (x0 + x1) / 2;
  const h = hw * 1.7; // near-equilateral
  const c = (h * h - hw * hw) / (2 * hw);
  const R = hw + c;
  const tTop = Math.acos(c / R);
  ctx.beginPath();
  ctx.moveTo(x0, bottom);
  ctx.lineTo(x0, spring);
  for (let i = 0; i <= 24; i++) {
    const a = Math.PI - (i / 24) * tTop;
    ctx.lineTo(cx + c + R * Math.cos(a), spring - R * Math.sin(a));
  }
  for (let i = 24; i >= 0; i--) {
    const a = (i / 24) * tTop;
    ctx.lineTo(cx - c + R * Math.cos(a), spring - R * Math.sin(a));
  }
  ctx.lineTo(x1, bottom);
  ctx.closePath();
  return spring - h;
}

export function drawStainedGlass(canvas: HTMLCanvasElement, spec: GlassSpec): void {
  const { width: W, height: H, lights } = spec;
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext('2d')!;
  const rnd = mulberry(spec.seed);
  const pick = <T,>(list: T[]): T => list[Math.floor(rnd() * list.length)];

  // stone first: what is not glass is the tracery between the lights and round the oculus
  ctx.fillStyle = '#d3c7b2';
  ctx.fillRect(0, 0, W, H);

  const margin = W * 0.04;
  const gap = lights === 2 ? W * 0.06 : 0;
  const lightW = (W - 2 * margin - gap) / lights;
  const bottom = H - margin;
  // two lights spring at spec.spring from the top; a single light springs as high as its width allows
  const springY = lights === 2 ? H * spec.spring : H * 0.03 + lightW * 0.85;
  const lancets = Array.from({ length: lights }, (_, i) => {
    const x0 = margin + i * (lightW + gap);
    return { x0, x1: x0 + lightW, spring: springY, top: springY - lightW * 0.85 };
  });
  const oculus = lights === 2 ? { cx: W / 2, cy: springY - lightW * 1.05, r: W * 0.19 } : null;

  // the panes: an irregular grid, roughly a sixth of a light across
  const cell = lightW / 6.5;
  const cols = Math.ceil(W / cell) + 1;
  const rows = Math.ceil(H / cell) + 1;
  const grid: { x: number; y: number }[][] = [];
  for (let j = 0; j <= rows; j++) {
    grid.push([]);
    for (let i = 0; i <= cols; i++) {
      grid[j].push({ x: i * cell + (rnd() - 0.5) * cell * 0.55, y: j * cell + (rnd() - 0.5) * cell * 0.55 });
    }
  }

  const figures = lancets.map((l) => {
    const w = l.x1 - l.x0;
    const cx = (l.x0 + l.x1) / 2;
    const headR = w * 0.1;
    const headY = l.top + (bottom - l.top) * 0.28;
    const robe = pick(ROBES);
    return {
      cx, headR, headY, robe,
      mantle: pick(MANTLES.filter((c) => c !== robe)),
      hair: pick(HAIR),
      shoulderY: headY + headR * 1.5,
      feet: bottom - (bottom - l.top) * 0.09,
      halfW: w * 0.3,
      ground: pick(['#6b4a2b', '#4b5d3a', '#7a5a3a']),
      lattice: pick(PALES),
      lattice2: pick(PALES),
      canopy: pick(['#d9a227', '#e9c25a']),
    };
  });

  const colourAt = (x: number, y: number, l: (typeof lancets)[number], f: (typeof figures)[number]): string => {
    const dx = x - f.cx;
    // the border: one pane wide, red and gold alternating
    const bx = Math.min(x - l.x0, l.x1 - x);
    if (bx < cell * 0.75 || y > bottom - cell * 0.75) return (Math.floor(x / cell) + Math.floor(y / cell)) % 2 ? '#b0202a' : '#d9a227';
    // the ground band under the feet
    if (y > f.feet) return f.ground;
    // the canopy over the head: a gilt pointed arch band
    const canopyY = f.headY - f.headR * 3.1;
    const canopyHalf = f.halfW * 0.95;
    const arch = canopyY + (Math.abs(dx) / canopyHalf) ** 1.6 * f.headR * 1.8;
    if (Math.abs(dx) < canopyHalf && y > arch - cell * 0.45 && y < arch + cell * 0.45) return f.canopy;
    // the figure, from the top down
    const dy = y - f.headY;
    if (Math.hypot(dx, dy) < f.headR * 1.75) {
      if (Math.hypot(dx, dy) < f.headR) return y < f.headY - f.headR * 0.3 ? f.hair : SKIN;
      return '#e9c25a';
    }
    if (y > f.shoulderY) {
      const t = (y - f.shoulderY) / (f.feet - f.shoulderY);
      const half = f.halfW * (0.5 + 0.5 * t);
      if (Math.abs(dx) < half) {
        // hands before the chest
        if (t > 0.22 && t < 0.34 && Math.abs(dx) < f.headR * 0.9) return SKIN;
        // the mantle falls over the shoulders and down one side; folds as darker bands
        const fold = Math.floor((dx + half) / (half * 0.5)) % 2 === 0 ? 1 : 0.82;
        if (t < 0.1) return shade(f.mantle, fold);
        if (dx > half * 0.35) return shade(f.mantle, fold);
        return shade(f.robe, fold);
      }
    }
    // the pale lattice ground round the figure: diamonds of two pale glasses
    const d = Math.floor((x + y) / (cell * 1.6)) + Math.floor((x - y) / (cell * 1.6));
    return d % 2 === 0 ? f.lattice : f.lattice2;
  };

  const panes = (clip: () => void, colour: (x: number, y: number) => string | null) => {
    ctx.save();
    clip();
    for (let j = 0; j < rows; j++) {
      for (let i = 0; i < cols; i++) {
        const p = [grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]];
        const mx = (p[0].x + p[2].x) / 2;
        const my = (p[0].y + p[2].y) / 2;
        const col = colour(mx, my);
        if (!col) continue;
        ctx.fillStyle = shade(col, 0.88 + rnd() * 0.24);
        ctx.beginPath();
        ctx.moveTo(p[0].x, p[0].y);
        for (let q = 1; q < 4; q++) ctx.lineTo(p[q].x, p[q].y);
        ctx.closePath();
        ctx.fill();
        ctx.fillStyle = 'rgba(255,255,255,0.09)';
        ctx.beginPath();
        ctx.moveTo(p[0].x, p[0].y);
        ctx.lineTo(p[1].x, p[1].y);
        ctx.lineTo(mx, my);
        ctx.closePath();
        ctx.fill();
        ctx.strokeStyle = '#1a1716';
        ctx.lineWidth = Math.max(2, W / 300);
        ctx.beginPath();
        ctx.moveTo(p[0].x, p[0].y);
        for (let q = 1; q < 4; q++) ctx.lineTo(p[q].x, p[q].y);
        ctx.closePath();
        ctx.stroke();
      }
    }
    ctx.restore();
  };

  lancets.forEach((l, k) => {
    const f = figures[k];
    panes(() => { lancetPath(ctx, l.x0, l.x1, l.spring, bottom); ctx.clip(); }, (x, y) => colourAt(x, y, l, f));
    // heavier leads along the silhouette, the halo and the canopy
    ctx.save();
    lancetPath(ctx, l.x0, l.x1, l.spring, bottom);
    ctx.clip();
    ctx.strokeStyle = '#121010';
    ctx.lineWidth = Math.max(3, W / 180);
    ctx.beginPath();
    ctx.arc(f.cx, f.headY, f.headR * 1.75, 0, Math.PI * 2);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(f.cx, f.headY, f.headR, 0, Math.PI * 2);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(f.cx - f.halfW * 0.5, f.shoulderY);
    ctx.lineTo(f.cx - f.halfW, f.feet);
    ctx.lineTo(f.cx + f.halfW, f.feet);
    ctx.lineTo(f.cx + f.halfW * 0.5, f.shoulderY);
    ctx.closePath();
    ctx.stroke();
    ctx.restore();
    // the stone edge of the light, as a thick lead
    ctx.strokeStyle = '#1a1716';
    ctx.lineWidth = Math.max(4, W / 110);
    lancetPath(ctx, l.x0, l.x1, l.spring, bottom);
    ctx.stroke();
  });

  if (oculus) {
    // the quatrefoil: four gilt lobes round a ruby centre on pale glass, inside a stone ring
    panes(() => { ctx.beginPath(); ctx.arc(oculus.cx, oculus.cy, oculus.r * 0.92, 0, Math.PI * 2); ctx.clip(); }, (x, y) => {
      const d = Math.hypot(x - oculus.cx, y - oculus.cy) / oculus.r;
      const a = Math.atan2(y - oculus.cy, x - oculus.cx);
      if (d < 0.2) return '#b0202a';
      if (d < 0.62 && Math.abs(Math.cos(2 * a)) > 0.5) return '#d9a227';
      return d < 0.62 ? '#1f4fb3' : PALES[1];
    });
    ctx.strokeStyle = '#1a1716';
    ctx.lineWidth = Math.max(4, W / 110);
    ctx.beginPath();
    ctx.arc(oculus.cx, oculus.cy, oculus.r * 0.92, 0, Math.PI * 2);
    ctx.stroke();
  }
}

/** A small landscape in oils: a warm sky, far hills, a river and a town with towers. */
export function drawLandscape(canvas: HTMLCanvasElement, W: number, H: number, seed: number): void {
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext('2d')!;
  const rnd = mulberry(seed);
  const sky = ctx.createLinearGradient(0, 0, 0, H * 0.55);
  sky.addColorStop(0, '#5f87c4');
  sky.addColorStop(0.6, '#d9c7a4');
  sky.addColorStop(1, '#f1d9a8');
  ctx.fillStyle = sky;
  ctx.fillRect(0, 0, W, H);
  // clouds
  for (let i = 0; i < 9; i++) {
    const x = rnd() * W;
    const y = H * (0.08 + rnd() * 0.3);
    const r = W * (0.05 + rnd() * 0.08);
    ctx.fillStyle = `rgba(255,245,230,${0.5 + rnd() * 0.4})`;
    for (let k = 0; k < 4; k++) {
      ctx.beginPath();
      ctx.arc(x + (rnd() - 0.5) * r * 2, y + (rnd() - 0.5) * r * 0.6, r * (0.5 + rnd() * 0.5), 0, Math.PI * 2);
      ctx.fill();
    }
  }
  // far hills in two planes
  for (const [yBase, colour, amp] of [[0.5, '#8aa1b8', 0.06], [0.58, '#6f8b63', 0.05]] as const) {
    ctx.fillStyle = colour;
    ctx.beginPath();
    ctx.moveTo(0, H);
    for (let x = 0; x <= W; x += W / 24) {
      ctx.lineTo(x, H * yBase - Math.abs(Math.sin(x / W * 7 + seed)) * H * amp - rnd() * H * 0.01);
    }
    ctx.lineTo(W, H);
    ctx.closePath();
    ctx.fill();
  }
  // the town: a wall and towers with spires on the skyline
  ctx.fillStyle = '#8c7a62';
  ctx.fillRect(W * 0.1, H * 0.56, W * 0.8, H * 0.08);
  for (let i = 0; i < 7; i++) {
    const x = W * (0.12 + i * 0.11 + rnd() * 0.03);
    const w = W * (0.04 + rnd() * 0.03);
    const h = H * (0.08 + rnd() * 0.12);
    ctx.fillStyle = i % 2 ? '#a08b6e' : '#7f6c55';
    ctx.fillRect(x, H * 0.6 - h, w, h);
    ctx.fillStyle = '#5a4a3a';
    ctx.beginPath();
    ctx.moveTo(x - w * 0.1, H * 0.6 - h);
    ctx.lineTo(x + w / 2, H * 0.6 - h - H * (0.04 + rnd() * 0.05));
    ctx.lineTo(x + w * 1.1, H * 0.6 - h);
    ctx.closePath();
    ctx.fill();
  }
  // the river with a bridge, and the meadow
  ctx.fillStyle = '#6f9a5a';
  ctx.fillRect(0, H * 0.64, W, H * 0.36);
  const river = ctx.createLinearGradient(0, H * 0.66, 0, H);
  river.addColorStop(0, '#9bb8d2');
  river.addColorStop(1, '#5a7fa3');
  ctx.fillStyle = river;
  ctx.beginPath();
  ctx.moveTo(W * 0.35, H * 0.66);
  ctx.lineTo(W * 0.62, H * 0.66);
  ctx.lineTo(W * 0.95, H);
  ctx.lineTo(W * 0.05, H);
  ctx.closePath();
  ctx.fill();
  ctx.fillStyle = '#9c8a70';
  ctx.fillRect(W * 0.2, H * 0.74, W * 0.62, H * 0.03);
  for (let i = 0; i < 4; i++) {
    ctx.fillStyle = '#5a7fa3';
    ctx.beginPath();
    ctx.arc(W * (0.28 + i * 0.15), H * 0.78, W * 0.045, Math.PI, 0);
    ctx.fill();
  }
  // trees and a warm glaze, like varnish
  for (let i = 0; i < 12; i++) {
    const x = rnd() * W;
    const y = H * (0.66 + rnd() * 0.3);
    ctx.fillStyle = i % 2 ? '#3f6b3a' : '#5b8a4a';
    ctx.beginPath();
    ctx.arc(x, y, W * (0.02 + rnd() * 0.03), 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.fillStyle = 'rgba(190,140,70,0.16)';
  ctx.fillRect(0, 0, W, H);
}
