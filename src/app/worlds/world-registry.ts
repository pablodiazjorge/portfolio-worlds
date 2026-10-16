import { Type } from '@angular/core';

export type WorldId = 'atlas' | 'aeris' | 'helios' | 'atrium';
export type Lang = 'en' | 'es';

export interface WorldDef {
  readonly id: WorldId;
  /** Keyboard shortcut. */
  readonly key: string;
  /** Page background shown before the scene fades in. */
  readonly background: string;
  /** Two colors that identify the world in the dock and the hub. */
  readonly swatch: readonly [string, string];
  /** Files fetched in advance when the visitor hovers the world in the dock. */
  readonly assets: readonly string[];
  readonly page: () => Promise<Type<unknown>>;
}

export const WORLDS: readonly WorldDef[] = [
  {
    id: 'atlas',
    key: '1',
    background: '#27304f',
    swatch: ['#2a3a66', '#f0b98d'],
    assets: ['models/atlas/valley.glb'],
    page: () => import('../landings/atlas/atlas.page').then((m) => m.AtlasPage),
  },
  {
    id: 'aeris',
    key: '2',
    background: '#d9dce1',
    swatch: ['#e3e5e9', '#ff6a2b'],
    assets: ['models/aeris/drone.glb'],
    page: () => import('../landings/aeris/aeris.page').then((m) => m.AerisPage),
  },
  {
    id: 'helios',
    key: '3',
    background: '#03050b',
    swatch: ['#071226', '#ffcf8a'],
    assets: ['models/helios/station.glb'],
    page: () => import('../landings/helios/helios.page').then((m) => m.HeliosPage),
  },
  {
    id: 'atrium',
    key: '4',
    background: '#1f3a33',
    swatch: ['#24443b', '#c9a465'],
    assets: ['models/atrium/museum.glb', 'models/atrium/robot.glb'],
    page: () => import('../landings/atrium/atrium.page').then((m) => m.AtriumPage),
  },
];

export const WORLD_IDS: readonly WorldId[] = WORLDS.map((w) => w.id);

export function worldById(id: WorldId): WorldDef {
  const world = WORLDS.find((w) => w.id === id);
  if (!world) throw new Error(`Unknown world ${id}`);
  return world;
}

export function worldPath(lang: Lang, world: WorldId | null): string {
  const prefix = lang === 'es' ? '/es' : '';
  if (!world) return prefix || '/';
  return `${prefix}/${world}`;
}
