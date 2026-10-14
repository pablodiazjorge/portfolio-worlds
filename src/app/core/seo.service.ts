import { inject, Injectable, DOCUMENT } from '@angular/core';
import { Meta, Title } from '@angular/platform-browser';
import { Lang, WorldId, worldPath } from '../worlds/world-registry';
import { Site, SITE_ORIGIN } from './site.service';

@Injectable({ providedIn: 'root' })
export class Seo {
  private readonly title = inject(Title);
  private readonly meta = inject(Meta);
  private readonly document = inject(DOCUMENT);
  private readonly site = inject(Site);

  update(lang: Lang, world: WorldId | null): void {
    const t = this.site.t();
    const name = this.site.portfolio().name;
    const pageTitle = world ? `${t.worlds[world].name} - ${name}` : `${name} - ${t.hub.title}`;
    const description = world ? t.worlds[world].seo : `${t.hub.title}. ${t.hub.lead}`;
    const url = `${SITE_ORIGIN}${worldPath(lang, world)}`;
    const image = `${SITE_ORIGIN}/og/${world ?? 'hub'}.jpg`;

    this.title.setTitle(pageTitle);
    this.meta.updateTag({ name: 'description', content: description });
    this.meta.updateTag({ property: 'og:type', content: 'website' });
    this.meta.updateTag({ property: 'og:title', content: pageTitle });
    this.meta.updateTag({ property: 'og:description', content: description });
    this.meta.updateTag({ property: 'og:url', content: url });
    this.meta.updateTag({ property: 'og:image', content: image });
    this.meta.updateTag({ property: 'og:locale', content: lang === 'es' ? 'es_ES' : 'en_US' });
    this.meta.updateTag({ name: 'twitter:card', content: 'summary_large_image' });
    this.meta.updateTag({ name: 'twitter:title', content: pageTitle });
    this.meta.updateTag({ name: 'twitter:description', content: description });
    this.meta.updateTag({ name: 'twitter:image', content: image });

    this.setLink('canonical', url);
    this.setLink('alternate', `${SITE_ORIGIN}${worldPath('en', world)}`, 'en');
    this.setLink('alternate', `${SITE_ORIGIN}${worldPath('es', world)}`, 'es');
    this.setLink('alternate', `${SITE_ORIGIN}${worldPath('en', world)}`, 'x-default');
  }

  private setLink(rel: string, href: string, hreflang?: string): void {
    const head = this.document.head;
    const selector = hreflang ? `link[rel="${rel}"][hreflang="${hreflang}"]` : `link[rel="${rel}"]`;
    let link = head.querySelector<HTMLLinkElement>(selector);
    if (!link) {
      link = this.document.createElement('link');
      link.rel = rel;
      if (hreflang) link.hreflang = hreflang;
      head.appendChild(link);
    }
    link.href = href;
  }
}
