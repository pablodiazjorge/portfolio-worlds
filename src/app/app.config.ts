import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideClientHydration, withEventReplay } from '@angular/platform-browser';
import { provideRouter, RouteReuseStrategy, withInMemoryScrolling } from '@angular/router';
import { routes } from './app.routes';
import { WorldReuseStrategy } from './core/world-reuse.strategy';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes, withInMemoryScrolling({ scrollPositionRestoration: 'top' })),
    provideClientHydration(withEventReplay()),
    { provide: RouteReuseStrategy, useClass: WorldReuseStrategy },
  ],
};
