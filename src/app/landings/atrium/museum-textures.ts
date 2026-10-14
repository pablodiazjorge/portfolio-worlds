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
    brassPlate(ctx, w, h);
    ctx.fillStyle = '#2e2012';
    ctx.font = `600 54px ${SERIF}`;
    const titleLines = wrap(ctx, project.title, w - 64).slice(0, 2);
    let y = 74;
    for (const line of titleLines) {
      ctx.fillText(line, 32, y);
      y += 50;
    }
    ctx.font = `500 28px ${SERIF}`;
    ctx.fillStyle = '#3f2e18';
    if (project.year) {
      ctx.fillText(project.year, 32, y + 4);
      y += 38;
    }
    ctx.font = `500 24px ${SERIF}`;
    const mediumLines = wrap(ctx, `${medium}: ${project.tech.slice(0, 3).join(', ')}`, w - 64).slice(0, 3);
    y += 8;
    for (const line of mediumLines) {
      ctx.fillText(line, 32, y);
      y += 30;
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
    brassPlate(ctx, w, h);
    ctx.fillStyle = '#2e2012';
    ctx.font = `600 150px ${SERIF}`;
    ctx.fillText(portfolio.name, 60, 200);
    ctx.font = `500 50px ${SERIF}`;
    ctx.fillStyle = '#3f2e18';
    ctx.fillText(portfolio.role, 66, 290);
    ctx.font = `500 38px ${SERIF}`;
    ctx.fillText(portfolio.focus, 66, 350);
    ctx.fillText(portfolio.location, 66, h - 50);
  });
}

export function drawContact(panel: PanelTexture, title: string, portfolio: Portfolio): void {
  panel.draw((ctx, w, h) => {
    brassPlate(ctx, w, h);
    ctx.fillStyle = '#2e2012';
    ctx.font = `600 130px ${SERIF}`;
    ctx.fillText(title, 56, 170);
    ctx.font = `500 42px ${SERIF}`;
    ctx.fillStyle = '#3f2e18';
    ctx.fillText(portfolio.contact.linkedin.replace('https://www.', ''), 60, 280);
    ctx.fillText(portfolio.contact.github.replace('https://', ''), 60, 340);
    ctx.fillStyle = '#8a6a3a';
    ctx.fillRect(60, h - 70, 140, 4);
  });
}

export function drawSign(panel: PanelTexture, text: string): void {
  panel.draw((ctx, w, h) => {
    brassPlate(ctx, w, h);
    ctx.fillStyle = '#2e2012';
    ctx.font = `600 ${Math.round(h * 0.5)}px ${SERIF}`;
    const width = ctx.measureText(text).width;
    ctx.fillText(text, (w - width) / 2, h / 2 + h * 0.17);
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
    ctx.lineWidth = 6;
    ctx.strokeRect(12, 12, w - 24, h - 24);
    ctx.fillStyle = '#3a2a12';
    ctx.textAlign = 'center';
    ctx.font = `600 ${Math.round(h * 0.3)}px ${SERIF}`;
    ctx.fillText(job.role, w / 2, h * 0.46, w - 60);
    ctx.font = `500 ${Math.round(h * 0.2)}px ${SERIF}`;
    ctx.fillText(`${job.company}, ${job.period}`, w / 2, h * 0.78, w - 60);
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
