import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { Site } from '../core/site.service';
import { Transitions } from '../core/transitions.service';
import { WorldDef, WorldId, WORLDS } from '../worlds/world-registry';

@Component({
  selector: 'pw-hub',
  templateUrl: './hub.page.html',
  styleUrl: './hub.page.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class HubPage {
  protected readonly site = inject(Site);
  private readonly transitions = inject(Transitions);
  protected readonly worlds = WORLDS;

  protected go(event: MouseEvent, world: WorldId): void {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    void this.transitions.go(world);
  }

  protected prefetch(world: WorldDef): void {
    this.transitions.prefetch(world);
  }
}
