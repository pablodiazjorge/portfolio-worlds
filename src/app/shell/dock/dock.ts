import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { Site } from '../../core/site.service';
import { Transitions } from '../../core/transitions.service';
import { WorldDef, WorldId, WORLDS } from '../../worlds/world-registry';

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName);
}

@Component({
  selector: 'pw-dock',
  templateUrl: './dock.html',
  styleUrl: './dock.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { '(document:keydown)': 'onKey($event)' },
})
export class Dock {
  protected readonly site = inject(Site);
  private readonly transitions = inject(Transitions);
  protected readonly worlds = WORLDS;

  protected go(event: MouseEvent, world: WorldId | null): void {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    void this.transitions.go(world);
  }

  protected switchLang(event: MouseEvent): void {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    void this.transitions.go(this.site.world(), this.site.otherLang());
  }

  protected prefetch(world: WorldDef): void {
    this.transitions.prefetch(world);
  }

  protected onKey(event: KeyboardEvent): void {
    if (event.metaKey || event.ctrlKey || event.altKey || event.repeat || isTyping(event.target)) return;
    if (event.key === '0') {
      void this.transitions.go(null);
      return;
    }
    const world = this.worlds.find((w) => w.key === event.key);
    if (world) void this.transitions.go(world.id);
  }
}
