import * as THREE from 'three/webgpu';
import type { ExperienceEntry, Portfolio, ProjectEntry } from '../../content/portfolio.model';

const SERIF = '"Cormorant Garamond Variable", Garamond, Georgia, serif';
const SANS = '"Instrument Sans Variable", system-ui, sans-serif';

export interface MuseumCopy {
  readonly portfolio: Portfolio;
  readonly experience: readonly ExperienceEntry[];
  readonly projectsSign: string;
  readonly experienceSign: string;
  readonly contactTitle: string;
  readonly medium: string;
}

/** Waits for the faces the canvases use, so the first drawing does not fall back to Georgia. */
export async function loadMuseumFonts(): Promise<void> {
  if (typeof document === 'undefined' || !document.fonts) return;
  await Promise.all([
    document.fonts.load(`500 48px ${SERIF}`),
    document.fonts.load(`600 48px ${SERIF}`),
    document.fonts.load(`500 24px ${SANS}`),
  ]).catch(() => undefined);
}

function wrap(ctx: CanvasRenderingContext2D, text: string, maxWidth: number): string[] {
  const words = text.split(/\s+/);
  const lines: string[] = [];
  let line = '';
  for (const word of words) {
    const next = line ? `${line} ${word}` : word;
    if (ctx.measureText(next).width > maxWidth && line) {
      lines.push(line);
      line = word;
    } else {
      line = next;
    }
  }
  if (line) lines.push(line);
  return lines;
}

/** A canvas-backed texture that can be redrawn when the language changes. */
export class PanelTexture {
  readonly canvas: HTMLCanvasElement;
  readonly texture: THREE.CanvasTexture;
  private readonly ctx: CanvasRenderingContext2D;

  constructor(width: number, height: number) {
    this.canvas = document.createElement('canvas');
    this.canvas.width = width;
    this.canvas.height = height;
    this.ctx = this.canvas.getContext('2d')!;
    this.texture = new THREE.CanvasTexture(this.canvas);
    this.texture.colorSpace = THREE.SRGBColorSpace;
    this.texture.anisotropy = 4;
    this.texture.flipY = false;
  }

  draw(painter: (ctx: CanvasRenderingContext2D, w: number, h: number) => void): void {
    const { width, height } = this.canvas;
    this.ctx.save();
    this.ctx.clearRect(0, 0, width, height);
    painter(this.ctx, width, height);
    this.ctx.restore();
    this.texture.needsUpdate = true;
  }

  dispose(): void {
    this.texture.dispose();
  }
}

function brassPlate(ctx: CanvasRenderingContext2D, w: number, h: number): void {
  const brass = ctx.createLinearGradient(0, 0, w, h);
  brass.addColorStop(0, '#c9a24e');
  brass.addColorStop(0.5, '#e3c468');
  brass.addColorStop(1, '#b8892f');
  ctx.fillStyle = brass;
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = '#6b5320';
  ctx.lineWidth = Math.max(3, h / 40);
  ctx.strokeRect(10, 10, w - 20, h - 20);
}

export function drawLabel(panel: PanelTexture, project: ProjectEntry, medium: string): void {
  panel.draw((ctx, w, h) => {
    // the title gets the largest size that fits one line, or two lines a little smaller; the year
    // and the medium keep their size; the whole block is measured from explicit baselines and centred
    brassPlate(ctx, w, h);
    const margin = w * 0.045;
    const usable = w - margin * 2;
    const titleFont = (size: number) => `600 ${Math.round(size)}px ${SERIF}`;
    let titleSize = h * 0.26;
    let titleLines: string[] = [];
    for (;;) {
      ctx.font = titleFont(titleSize);
      titleLines = wrap(ctx, project.title, usable);
      if (titleLines.length === 1 || titleSize <= h * 0.2) break;
      titleSize -= h * 0.01;
    }
    if (titleLines.length > 1) {
      titleSize = h * 0.2;
      ctx.font = titleFont(titleSize);
      titleLines = wrap(ctx, project.title, usable).slice(0, 2);
    }
    const yearSize = h * 0.11;
    let mediumSize = h * 0.105;
    const tech = `${medium}: ${project.tech.slice(0, 3).join(', ')}`;
    ctx.font = `500 ${Math.round(mediumSize)}px ${SERIF}`;
    let mediumLines = wrap(ctx, tech, usable);
    if (mediumLines.length > 2) {
      mediumSize = h * 0.09;
      ctx.font = `500 ${Math.round(mediumSize)}px ${SERIF}`;
      mediumLines = wrap(ctx, tech, usable).slice(0, 3);
    }
    // baselines measured from the top of the block
    const baselines: { text: string; y: number; font: string; colour: string }[] = [];
    let y = titleSize * 0.78;
    titleLines.forEach((line, i) => {
      if (i) y += titleSize * 1.02;
      baselines.push({ text: line, y, font: titleFont(titleSize), colour: '#2e2012' });
    });
    if (project.year) {
      y += yearSize * 1.55;
      baselines.push({ text: project.year, y, font: `500 ${Math.round(yearSize)}px ${SERIF}`, colour: '#3f2e18' });
    }
    y += mediumSize * 1.5;
    mediumLines.forEach((line, i) => {
      if (i) y += mediumSize * 1.22;
      baselines.push({ text: line, y, font: `500 ${Math.round(mediumSize)}px ${SERIF}`, colour: '#3f2e18' });
    });
    const block = y + mediumSize * 0.28;
    const top = Math.max(h * 0.08, (h - block) / 2);
    for (const line of baselines) {
      ctx.font = line.font;
      ctx.fillStyle = line.colour;
      ctx.fillText(line.text, margin, top + line.y);
    }
  });
}

export function drawLightbox(panel: PanelTexture, job: ExperienceEntry): void {
  panel.draw((ctx, w, h) => {
    const gradient = ctx.createLinearGradient(0, 0, 0, h);
    gradient.addColorStop(0, '#fbf7ef');
    gradient.addColorStop(1, '#efe6d6');
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = '#1d1b18';
    ctx.font = `500 230px ${SERIF}`;
    ctx.fillText(String(job.startYear), 60, 250);
    ctx.font = `600 64px ${SERIF}`;
    const roleLines = wrap(ctx, job.role, w - 120).slice(0, 2);
    let y = 360;
    for (const line of roleLines) {
      ctx.fillText(line, 64, y);
      y += 68;
    }
    ctx.font = `500 34px ${SANS}`;
    ctx.fillStyle = '#5a554c';
    ctx.fillText(`${job.company}, ${job.period}`, 66, y + 16);
  });
}

export function drawAbout(panel: PanelTexture, portfolio: Portfolio): void {
  panel.draw((ctx, w, h) => {
    // centred: the name across the top, the role and the focus below it, a rule and the place at the foot
    brassPlate(ctx, w, h);
    ctx.textAlign = 'center';
    ctx.fillStyle = '#2e2012';
    ctx.font = `600 ${Math.round(h * 0.27)}px ${SERIF}`;
    ctx.fillText(portfolio.name, w / 2, h * 0.35, w * 0.9);
    ctx.fillStyle = '#3f2e18';
    ctx.font = `500 ${Math.round(h * 0.11)}px ${SERIF}`;
    ctx.fillText(portfolio.role, w / 2, h * 0.53, w * 0.9);
    ctx.font = `500 ${Math.round(h * 0.085)}px ${SERIF}`;
    ctx.fillText(portfolio.focus, w / 2, h * 0.675, w * 0.9);
    ctx.fillStyle = '#8a6a3a';
    ctx.fillRect(w / 2 - w * 0.06, h * 0.75, w * 0.12, Math.max(2, h * 0.008));
    ctx.fillStyle = '#3f2e18';
    ctx.font = `500 ${Math.round(h * 0.078)}px ${SERIF}`;
    ctx.fillText(portfolio.location, w / 2, h * 0.885, w * 0.9);
  });
}

export function drawContact(panel: PanelTexture, title: string, portfolio: Portfolio): void {
  panel.draw((ctx, w, h) => {
    brassPlate(ctx, w, h);
    ctx.textAlign = 'center';
    ctx.fillStyle = '#2e2012';
    ctx.font = `600 ${Math.round(h * 0.23)}px ${SERIF}`;
    ctx.fillText(title, w / 2, h * 0.3, w * 0.9);
    ctx.fillStyle = '#8a6a3a';
    ctx.fillRect(w / 2 - w * 0.07, h * 0.38, w * 0.14, Math.max(2, h * 0.008));
    ctx.fillStyle = '#3f2e18';
    ctx.font = `500 ${Math.round(h * 0.095)}px ${SERIF}`;
    ctx.fillText(portfolio.contact.linkedin.replace('https://www.', ''), w / 2, h * 0.56, w * 0.92);
    ctx.fillText(portfolio.contact.github.replace('https://', ''), w / 2, h * 0.69, w * 0.92);
    ctx.font = `500 ${Math.round(h * 0.075)}px ${SERIF}`;
    ctx.fillText(portfolio.location, w / 2, h * 0.87, w * 0.9);
  });
}

export function drawSign(panel: PanelTexture, text: string): void {
  panel.draw((ctx, w, h) => {
    brassPlate(ctx, w, h);
    ctx.fillStyle = '#2e2012';
    ctx.font = `600 ${Math.round(h * 0.58)}px ${SERIF}`;
    const width = ctx.measureText(text).width;
    ctx.fillText(text, (w - width) / 2, h / 2 + h * 0.2, w * 0.9);
  });
}

/** The small brass plaque on a cabinet: the role, the company and the years, engraved dark on brass. */
export function drawPlaque(panel: PanelTexture, job: ExperienceEntry): void {
  panel.draw((ctx, w, h) => {
    const brass = ctx.createLinearGradient(0, 0, w, h);
    brass.addColorStop(0, '#c9a24e');
    brass.addColorStop(0.5, '#e3c468');
    brass.addColorStop(1, '#b8892f');
    ctx.fillStyle = brass;
    ctx.fillRect(0, 0, w, h);
    ctx.strokeStyle = '#6b5320';
    ctx.lineWidth = Math.max(3, h / 40);
    ctx.strokeRect(12, 12, w - 24, h - 24);
    ctx.fillStyle = '#3a2a12';
    ctx.textAlign = 'center';
    const usable = w * 0.88;
    // the role in the largest size that fits one line, down to a size where it takes two lines
    let roleSize = h * 0.3;
    let roleLines: string[] = [];
    for (;;) {
      ctx.font = `600 ${Math.round(roleSize)}px ${SERIF}`;
      roleLines = wrap(ctx, job.role, usable);
      if (roleLines.length === 1 || roleSize <= h * 0.2) break;
      roleSize -= h * 0.01;
    }
    if (roleLines.length > 1) {
      // two lines at most: the size comes down until the role fits in them
      roleSize = h * 0.19;
      for (;;) {
        ctx.font = `600 ${Math.round(roleSize)}px ${SERIF}`;
        roleLines = wrap(ctx, job.role, usable);
        if (roleLines.length <= 2 || roleSize <= h * 0.13) break;
        roleSize -= h * 0.005;
      }
      roleLines = roleLines.slice(0, 2);
    }
    const line = `${job.company}, ${job.period}`;
    let lineSize = h * 0.19;
    ctx.font = `500 ${Math.round(lineSize)}px ${SERIF}`;
    while (ctx.measureText(line).width > usable && lineSize > h * 0.12) {
      lineSize -= h * 0.01;
      ctx.font = `500 ${Math.round(lineSize)}px ${SERIF}`;
    }
    const roleBlock = roleSize * (0.78 + (roleLines.length - 1) * 1.05);
    const block = roleBlock + lineSize * 1.6;
    let y = (h - block) / 2 + roleSize * 0.78;
    ctx.font = `600 ${Math.round(roleSize)}px ${SERIF}`;
    roleLines.forEach((text, i) => {
      if (i) y += roleSize * 1.05;
      ctx.fillText(text, w / 2, y);
    });
    ctx.font = `500 ${Math.round(lineSize)}px ${SERIF}`;
    ctx.fillText(line, w / 2, y + lineSize * 1.5);
  });
}

/** The visitor's face on its monitor: two bright eyes and a wide smile in phosphor green, shut for a blink. */
export function drawFace(panel: PanelTexture, open: boolean): void {
  panel.draw((ctx, w, h) => {
    ctx.fillStyle = '#0f1b17';
    ctx.fillRect(0, 0, w, h);
    const glow = ctx.createRadialGradient(w / 2, h / 2, h * 0.1, w / 2, h / 2, h * 0.85);
    glow.addColorStop(0, 'rgba(93,224,138,0.22)');
    glow.addColorStop(1, 'rgba(93,224,138,0)');
    ctx.fillStyle = glow;
    ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = '#9af7b0';
    ctx.strokeStyle = '#9af7b0';
    ctx.lineCap = 'round';
    ctx.lineWidth = h * 0.075;
    for (const x of [w * 0.33, w * 0.67]) {
      ctx.beginPath();
      if (open) {
        ctx.ellipse(x, h * 0.38, w * 0.075, h * 0.13, 0, 0, Math.PI * 2);
        ctx.fill();
      } else {
        ctx.moveTo(x - w * 0.08, h * 0.4);
        ctx.lineTo(x + w * 0.08, h * 0.4);
        ctx.stroke();
      }
    }
    ctx.beginPath();
    ctx.arc(w / 2, h * 0.5, w * 0.26, Math.PI * 0.18, Math.PI * 0.82);
    ctx.stroke();
    // a cheek dot either side of the smile, and the scan lines of an old tube
    for (const x of [w * 0.14, w * 0.86]) {
      ctx.beginPath();
      ctx.arc(x, h * 0.62, w * 0.025, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.fillStyle = 'rgba(0,0,0,0.2)';
    for (let y = 0; y < h; y += 4) ctx.fillRect(0, y, w, 1);
  });
}

/** The width of a painted quad divided by its height, read from the corners its UVs mark. */
export function quadAspect(geometry: THREE.BufferGeometry): number {
  const position = geometry.getAttribute('position');
  const uv = geometry.getAttribute('uv');
  if (!position || !uv) return 1;
  const corner = (u: number, v: number): THREE.Vector3 | null => {
    for (let i = 0; i < uv.count; i++) {
      if (Math.abs(uv.getX(i) - u) < 0.01 && Math.abs(uv.getY(i) - v) < 0.01) return new THREE.Vector3().fromBufferAttribute(position, i);
    }
    return null;
  };
  const o = corner(0, 0);
  const right = corner(1, 0);
  const up = corner(0, 1);
  if (!o || !right || !up) return 1;
  const height = o.distanceTo(up);
  return height > 1e-6 ? o.distanceTo(right) / height : 1;
}

/** The prize badge on the visitor's chest: a gold rosette with its ribbons and the words round it. */
export function drawBadge(panel: PanelTexture, text: string): void {
  panel.draw((ctx, w, h) => {
    ctx.clearRect(0, 0, w, h);
    const cx = w / 2;
    const cy = h * 0.4;
    const r = w * 0.4;
    // two ribbon tails
    ctx.fillStyle = '#b8323a';
    for (const dir of [-1, 1]) {
      ctx.beginPath();
      ctx.moveTo(cx + dir * r * 0.18, cy + r * 0.5);
      ctx.lineTo(cx + dir * r * 0.62, cy + r * 0.5);
      ctx.lineTo(cx + dir * r * 0.78, h * 0.97);
      ctx.lineTo(cx + dir * r * 0.5, h * 0.9);
      ctx.lineTo(cx + dir * r * 0.3, h * 0.97);
      ctx.closePath();
      ctx.fill();
    }
    // the pleated rosette
    ctx.fillStyle = '#d9b24a';
    ctx.beginPath();
    for (let i = 0; i < 32; i++) {
      const a = (i / 32) * Math.PI * 2;
      const rr = i % 2 ? r : r * 0.86;
      ctx.lineTo(cx + Math.cos(a) * rr, cy + Math.sin(a) * rr);
    }
    ctx.closePath();
    ctx.fill();
    ctx.strokeStyle = '#8a6a1e';
    ctx.lineWidth = Math.max(2, w * 0.012);
    ctx.stroke();
    // the centre disc with the words round it and a star in the middle
    ctx.fillStyle = '#2f4466';
    ctx.beginPath();
    ctx.arc(cx, cy, r * 0.62, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = '#e9d58a';
    ctx.lineWidth = Math.max(2, w * 0.014);
    ctx.stroke();
    ctx.fillStyle = '#f3e6b0';
    ctx.font = `700 ${Math.round(r * 0.19)}px ${SANS}`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const letters = text.toUpperCase().split('');
    const span = Math.PI * 1.25;
    letters.forEach((ch, i) => {
      const a = -Math.PI / 2 - span / 2 + (span * (i + 0.5)) / letters.length;
      ctx.save();
      ctx.translate(cx + Math.cos(a) * r * 0.47, cy + Math.sin(a) * r * 0.47);
      ctx.rotate(a + Math.PI / 2);
      ctx.fillText(ch, 0, 0);
      ctx.restore();
    });
    ctx.fillStyle = '#e9d58a';
    ctx.beginPath();
    for (let i = 0; i < 10; i++) {
      const a = -Math.PI / 2 + (i / 10) * Math.PI * 2;
      const rr = i % 2 ? r * 0.1 : r * 0.24;
      ctx.lineTo(cx + Math.cos(a) * rr, cy + r * 0.06 + Math.sin(a) * rr);
    }
    ctx.closePath();
    ctx.fill();
  });
}
