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

export function drawLabel(panel: PanelTexture, project: ProjectEntry, medium: string): void {
  panel.draw((ctx, w, h) => {
    ctx.fillStyle = '#f4f2ee';
    ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = '#1b1c20';
    ctx.font = `600 50px ${SERIF}`;
    const titleLines = wrap(ctx, project.title, w - 64).slice(0, 2);
    let y = 74;
    for (const line of titleLines) {
      ctx.fillText(line, 32, y);
      y += 50;
    }
    ctx.font = `500 26px ${SANS}`;
    ctx.fillStyle = '#5b5e66';
    if (project.year) {
      ctx.fillText(project.year, 32, y + 4);
      y += 38;
    }
    ctx.font = `500 22px ${SANS}`;
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
    ctx.fillStyle = '#ebe7e0';
    ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = '#1c1d21';
    ctx.font = `500 150px ${SERIF}`;
    ctx.fillText(portfolio.name, 60, 200);
    ctx.font = `500 46px ${SANS}`;
    ctx.fillStyle = '#3a3c42';
    ctx.fillText(portfolio.role, 66, 290);
    ctx.font = `500 34px ${SANS}`;
    ctx.fillStyle = '#6a6c72';
    ctx.fillText(portfolio.focus, 66, 350);
    ctx.fillText(portfolio.location, 66, h - 50);
  });
}

export function drawContact(panel: PanelTexture, title: string, portfolio: Portfolio): void {
  panel.draw((ctx, w, h) => {
    ctx.fillStyle = '#ebe7e0';
    ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = '#1c1d21';
    ctx.font = `500 130px ${SERIF}`;
    ctx.fillText(title, 56, 170);
    ctx.font = `500 38px ${SANS}`;
    ctx.fillStyle = '#4c4e54';
    ctx.fillText(portfolio.contact.linkedin.replace('https://www.', ''), 60, 280);
    ctx.fillText(portfolio.contact.github.replace('https://', ''), 60, 340);
    ctx.fillStyle = '#8a6a3a';
    ctx.fillRect(60, h - 70, 140, 4);
  });
}

export function drawSign(panel: PanelTexture, text: string): void {
  panel.draw((ctx, w, h) => {
    ctx.fillStyle = '#16171a';
    ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = '#e8d3a8';
    ctx.font = `500 96px ${SERIF}`;
    const width = ctx.measureText(text).width;
    ctx.fillText(text, (w - width) / 2, h / 2 + 32);
  });
}
