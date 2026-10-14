import { computed, inject, Injectable, signal, DOCUMENT } from '@angular/core';
import { PORTFOLIO_EN } from '../content/portfolio.en';
import { PORTFOLIO_ES } from '../content/portfolio.es';
import { UI_EN } from '../content/ui.en';
import { UI_ES } from '../content/ui.es';
import { Lang, WorldId, worldPath } from '../worlds/world-registry';

export const SITE_ORIGIN = 'https://worlds.pablodiazjorge.com';
export const CLASSIC_PORTFOLIO = 'https://www.pablodiazjorge.com/';

/** Language and world of the current route, plus the content for that language. */
@Injectable({ providedIn: 'root' })
export class Site {
  private readonly document = inject(DOCUMENT);

  readonly lang = signal<Lang>('en');
  readonly world = signal<WorldId | null>(null);
  readonly t = computed(() => (this.lang() === 'es' ? UI_ES : UI_EN));
  readonly portfolio = computed(() => (this.lang() === 'es' ? PORTFOLIO_ES : PORTFOLIO_EN));
  readonly otherLang = computed<Lang>(() => (this.lang() === 'es' ? 'en' : 'es'));
  readonly classicUrl = computed(() => (this.lang() === 'es' ? `${CLASSIC_PORTFOLIO}es` : CLASSIC_PORTFOLIO));

  path(world: WorldId | null, lang: Lang = this.lang()): string {
    return worldPath(lang, world);
  }

  apply(lang: Lang, world: WorldId | null): void {
    this.lang.set(lang);
    this.world.set(world);
    const html = this.document.documentElement;
    html.setAttribute('lang', lang);
    if (world) html.setAttribute('data-world', world);
    else html.removeAttribute('data-world');
  }
}
