import { ChangeDetectionStrategy, Component, computed, effect, inject, signal, untracked } from '@angular/core';
import { injectWorldScene } from '../../core/engine/inject-world-scene';
import { isTouchDevice } from '../../core/engine/device';
import { Site } from '../../core/site.service';
import { Joystick, StickVector } from '../../shared/joystick/joystick';
import type { Exhibit, SeatState } from './atrium.scene';
import type { MuseumCopy } from './museum-textures';

const MOVE_KEYS: Record<string, [number, number]> = {
  KeyW: [1, 0],
  ArrowUp: [1, 0],
  KeyS: [-1, 0],
  ArrowDown: [-1, 0],
  KeyA: [0, -1],
  ArrowLeft: [0, -1],
  KeyD: [0, 1],
  ArrowRight: [0, 1],
};

function isTyping(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName));
}

@Component({
  selector: 'pw-atrium',
  imports: [Joystick],
  templateUrl: './atrium.page.html',
  styleUrl: './atrium.page.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    '(document:keydown)': 'onKeyDown($event)',
    '(document:keyup)': 'onKeyUp($event)',
    '(window:blur)': 'releaseKeys()',
  },
})
export class AtriumPage {
  protected readonly site = inject(Site);
  protected readonly touch = signal(false);
  protected readonly guideOpen = signal(false);
  protected readonly hintVisible = signal(true);
  protected readonly exhibit = signal<Exhibit | null>(null);
  protected readonly seatState = signal<SeatState>('none');
  protected readonly pointerOverExhibit = signal(false);

  /** Experience from the oldest job, on the first lightbox, to the newest. */
  protected readonly experience = computed(() => [...this.site.portfolio().experience].sort((a, b) => a.startYear - b.startYear));

  private readonly copy = computed<MuseumCopy>(() => {
    const t = this.site.t();
    return {
      portfolio: this.site.portfolio(),
      experience: this.experience(),
      projectsSign: t.sections.projects,
      experienceSign: t.sections.experience,
      contactTitle: t.sections.contact,
      medium: t.atrium.medium,
    };
  });

  private readonly scene = injectWorldScene(async (ctx) => {
    const { AtriumScene } = await import('./atrium.scene');
    const scene = new AtriumScene(ctx, untracked(this.copy));
    scene.onExhibit = (exhibit) => this.exhibit.set(exhibit);
    scene.onSeat = (state) => this.seatState.set(state);
    scene.onFirstMove = () => this.hintVisible.set(false);
    return scene;
  });

  private readonly pressed = new Set<string>();
  private drag: { id: number; x: number; y: number; moved: boolean } | null = null;
  private hoverFrame = 0;

  constructor() {
    effect(() => {
      const copy = this.copy();
      untracked(() => this.scene()?.setCopy(copy));
    });
    if (typeof window !== 'undefined') this.touch.set(isTouchDevice());
  }

  protected toggleGuide(): void {
    this.guideOpen.update((open) => !open);
  }

  protected visit(id: string): void {
    this.guideOpen.set(false);
    this.scene()?.goTo(id);
  }

  protected toggleSit(): void {
    this.scene()?.toggleSit();
  }

  protected onStick(vector: StickVector): void {
    this.scene()?.setStick(vector.x, vector.y);
  }

  protected onKeyDown(event: KeyboardEvent): void {
    if (isTyping(event.target) || event.metaKey || event.ctrlKey || event.altKey) return;
    if (event.key === 'Escape' && this.guideOpen()) {
      this.guideOpen.set(false);
      return;
    }
    if (event.code === 'KeyG') {
      this.toggleGuide();
      return;
    }
    if (event.code === 'KeyE') {
      this.toggleSit();
      return;
    }
    if (!(event.code in MOVE_KEYS) && event.key !== 'Shift') return;
    if (event.code.startsWith('Arrow')) event.preventDefault();
    this.pressed.add(event.code === 'ShiftLeft' || event.code === 'ShiftRight' ? 'Shift' : event.code);
    this.pushKeys();
  }

  protected onKeyUp(event: KeyboardEvent): void {
    this.pressed.delete(event.code === 'ShiftLeft' || event.code === 'ShiftRight' ? 'Shift' : event.code);
    this.pushKeys();
  }

  protected releaseKeys(): void {
    this.pressed.clear();
    this.pushKeys();
  }

  private pushKeys(): void {
    let forward = 0;
    let right = 0;
    for (const code of this.pressed) {
      const move = MOVE_KEYS[code];
      if (!move) continue;
      forward += move[0];
      right += move[1];
    }
    this.scene()?.setKeys(Math.sign(forward), Math.sign(right), this.pressed.has('Shift'));
  }

  private ndc(event: PointerEvent | WheelEvent): [number, number] {
    return [(event.clientX / window.innerWidth) * 2 - 1, -(event.clientY / window.innerHeight) * 2 + 1];
  }

  protected pointerDown(event: PointerEvent): void {
    if (event.button !== 0 && event.pointerType === 'mouse') return;
    this.drag = { id: event.pointerId, x: event.clientX, y: event.clientY, moved: false };
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
  }

  protected pointerMove(event: PointerEvent): void {
    const drag = this.drag;
    if (drag && drag.id === event.pointerId) {
      const dx = event.clientX - drag.x;
      const dy = event.clientY - drag.y;
      if (!drag.moved && Math.hypot(dx, dy) < 6) return;
      drag.moved = true;
      drag.x = event.clientX;
      drag.y = event.clientY;
      this.scene()?.rotate(dx, dy);
      return;
    }
    if (event.pointerType !== 'mouse' || ++this.hoverFrame % 4 !== 0) return;
    const [x, y] = this.ndc(event);
    this.pointerOverExhibit.set(!!this.scene()?.pick(x, y));
  }

  protected pointerUp(event: PointerEvent): void {
    const drag = this.drag;
    if (!drag || drag.id !== event.pointerId) return;
    this.drag = null;
    if (drag.moved) return;
    const [x, y] = this.ndc(event);
    this.scene()?.click(x, y);
  }

  protected wheel(event: WheelEvent): void {
    this.scene()?.zoom(event.deltaY);
  }
}
