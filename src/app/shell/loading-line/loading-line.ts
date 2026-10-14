import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { Engine } from '../../core/engine/engine.service';
import { Site } from '../../core/site.service';

@Component({
  selector: 'pw-loading-line',
  template: `
    <div
      class="line"
      [class.is-on]="engine.progress() !== null"
      role="progressbar"
      [attr.aria-label]="site.t().loading"
      aria-valuemin="0"
      aria-valuemax="100"
      [attr.aria-valuenow]="percent()"
      [attr.aria-hidden]="engine.progress() === null"
    >
      <span [style.transform]="'scaleX(' + (engine.progress() ?? 1) + ')'"></span>
    </div>
  `,
  styles: `
    .line {
      position: fixed;
      inset: 0 0 auto;
      z-index: 45;
      height: 2px;
      opacity: 0;
      pointer-events: none;
      transition: opacity 0.6s ease-out 0.2s;
    }
    .line.is-on {
      opacity: 1;
      transition-delay: 0s;
    }
    span {
      display: block;
      height: 100%;
      background: var(--accent);
      transform-origin: left center;
      transition: transform 0.5s var(--ease-out-quart);
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LoadingLine {
  protected readonly engine = inject(Engine);
  protected readonly site = inject(Site);
  protected readonly percent = computed(() => Math.round((this.engine.progress() ?? 1) * 100));
}
