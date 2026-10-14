import { afterNextRender, Component, ElementRef, inject, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRouteSnapshot, ResolveEnd, Router, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs';
import { Engine } from './core/engine/engine.service';
import { Seo } from './core/seo.service';
import { Site } from './core/site.service';
import { Lang, WorldId } from './worlds/world-registry';
import { Dock } from './shell/dock/dock';
import { Veil } from './shell/veil/veil';
import { LoadingLine } from './shell/loading-line/loading-line';

function deepest(snapshot: ActivatedRouteSnapshot): ActivatedRouteSnapshot {
  let current = snapshot;
  while (current.firstChild) current = current.firstChild;
  return current;
}

@Component({
  selector: 'pw-root',
  imports: [RouterOutlet, Dock, Veil, LoadingLine],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  protected readonly site = inject(Site);
  protected readonly engine = inject(Engine);
  private readonly seo = inject(Seo);
  private readonly stage = viewChild.required<ElementRef<HTMLCanvasElement>>('stage');

  constructor() {
    inject(Router)
      .events.pipe(
        filter((event): event is ResolveEnd => event instanceof ResolveEnd),
        takeUntilDestroyed(),
      )
      .subscribe((event) => {
        const data = deepest(event.state.root).data;
        const lang = (data['lang'] as Lang | undefined) ?? 'en';
        const world = (data['world'] as WorldId | null | undefined) ?? null;
        this.site.apply(lang, world);
        this.seo.update(lang, world);
      });

    afterNextRender(() => this.engine.attach(this.stage().nativeElement));
  }
}
