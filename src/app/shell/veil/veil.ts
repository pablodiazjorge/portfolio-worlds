import { ChangeDetectionStrategy, Component, computed, inject, signal, effect } from '@angular/core';
import { Site } from '../../core/site.service';
import { Transitions } from '../../core/transitions.service';
import { WorldId, worldById } from '../../worlds/world-registry';

@Component({
  selector: 'pw-veil',
  template: `
    <div
      class="veil"
      [class.is-on]="transitions.veil() !== null"
      [attr.data-target]="target()"
      [style.--veil-bg]="background()"
      aria-hidden="true"
    >
      <span class="veil-name">{{ label() }}</span>
    </div>
  `,
  styleUrl: './veil.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Veil {
  protected readonly transitions = inject(Transitions);
  private readonly site = inject(Site);
  /** Keeps the last destination while the veil fades out. */
  protected readonly target = signal<WorldId | 'hub'>('hub');

  protected readonly background = computed(() => {
    const target = this.target();
    return target === 'hub' ? '#1b1d24' : worldById(target).background;
  });

  protected readonly label = computed(() => {
    const target = this.target();
    const t = this.site.t();
    return target === 'hub' ? this.site.portfolio().name : t.worlds[target].name;
  });

  constructor() {
    effect(() => {
      const next = this.transitions.veil();
      if (next) this.target.set(next);
    });
  }
}
