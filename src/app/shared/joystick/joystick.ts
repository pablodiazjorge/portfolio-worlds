import { ChangeDetectionStrategy, Component, ElementRef, input, output, signal, viewChild } from '@angular/core';

export interface StickVector {
  x: number;
  y: number;
}

/** Touch stick: drag the knob to get a vector in -1..1, released back to the centre. */
@Component({
  selector: 'pw-joystick',
  template: `
    <div
      #base
      class="base"
      role="application"
      [attr.aria-label]="label()"
      (pointerdown)="start($event)"
      (pointermove)="move($event)"
      (pointerup)="end($event)"
      (pointercancel)="end($event)"
    >
      <span class="knob" [style.transform]="'translate(' + knob().x + 'px, ' + knob().y + 'px)'"></span>
    </div>
  `,
  styles: `
    .base {
      position: relative;
      display: grid;
      place-items: center;
      width: 8.5rem;
      height: 8.5rem;
      border: 1px solid rgb(255 255 255 / 0.28);
      border-radius: 50%;
      background: rgb(16 22 20 / 0.35);
      backdrop-filter: blur(10px);
      -webkit-backdrop-filter: blur(10px);
      touch-action: none;
    }
    .knob {
      width: 3.4rem;
      height: 3.4rem;
      border-radius: 50%;
      background: rgb(240 230 210 / 0.85);
      box-shadow: 0 6px 18px rgb(0 0 0 / 0.3);
      transition: transform 0.18s var(--ease-out-quart);
      pointer-events: none;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Joystick {
  readonly label = input('');
  readonly changed = output<StickVector>();
  private readonly base = viewChild.required<ElementRef<HTMLElement>>('base');
  protected readonly knob = signal({ x: 0, y: 0 });
  private pointer: number | null = null;

  protected start(event: PointerEvent): void {
    this.pointer = event.pointerId;
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
    this.move(event);
  }

  protected move(event: PointerEvent): void {
    if (event.pointerId !== this.pointer) return;
    const rect = this.base().nativeElement.getBoundingClientRect();
    const radius = rect.width / 2;
    let dx = event.clientX - (rect.left + radius);
    let dy = event.clientY - (rect.top + radius);
    const length = Math.hypot(dx, dy);
    const max = radius * 0.62;
    if (length > max) {
      dx = (dx / length) * max;
      dy = (dy / length) * max;
    }
    this.knob.set({ x: dx, y: dy });
    this.changed.emit({ x: dx / max, y: -dy / max });
  }

  protected end(event: PointerEvent): void {
    if (event.pointerId !== this.pointer) return;
    this.pointer = null;
    this.knob.set({ x: 0, y: 0 });
    this.changed.emit({ x: 0, y: 0 });
  }
}
