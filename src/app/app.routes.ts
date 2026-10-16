import { Routes } from '@angular/router';
import { Lang, WORLDS } from './worlds/world-registry';

const hub = () => import('./hub/hub.page').then((m) => m.HubPage);

function localized(lang: Lang): Routes {
  const prefix = lang === 'es' ? 'es' : '';
  const join = (segment: string) => (prefix ? `${prefix}/${segment}` : segment);
  return [
    { path: prefix, pathMatch: 'full', loadComponent: hub, data: { lang, world: null } },
    ...WORLDS.map((world) => ({
      path: join(world.id),
      loadComponent: world.page,
      data: { lang, world: world.id },
    })),
  ];
}

// an unknown path keeps its language: under /es it falls back to the Spanish hub, elsewhere to the English one
export const routes: Routes = [
  ...localized('es'),
  { path: 'es', children: [{ path: '**', redirectTo: '/es' }] },
  ...localized('en'),
  { path: '**', redirectTo: '' },
];
