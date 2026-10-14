import { ActivatedRouteSnapshot, BaseRouteReuseStrategy } from '@angular/router';

/**
 * Keeps the page component alive when only the language changes, so the 3D scene
 * stays on screen and only the text is swapped.
 */
export class WorldReuseStrategy extends BaseRouteReuseStrategy {
  override shouldReuseRoute(future: ActivatedRouteSnapshot, current: ActivatedRouteSnapshot): boolean {
    if (future.routeConfig === current.routeConfig) return true;
    const futureWorld = future.data['world'];
    return (
      futureWorld !== undefined &&
      futureWorld === current.data['world'] &&
      future.routeConfig?.loadComponent === current.routeConfig?.loadComponent
    );
  }
}
