#!/usr/bin/env node
// Regenerates every 3D model: Blender builds the raw GLB headless, glTF Transform optimizes it
// into public/models and the build fails when a file goes over its size budget.
//
//   npm run assets               all models
//   npm run assets -- atlas      only the matching models
//   npm run assets -- --skip-blender   reuse tools/out/raw and only optimize
//
// BLENDER_PATH overrides the Blender executable.

import { spawnSync } from 'node:child_process';
import { copyFileSync, existsSync, mkdirSync, rmSync, statSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { dedup, flatten, instance, meshopt, prune, textureCompress, weld } from '@gltf-transform/functions';
import { MeshoptDecoder, MeshoptEncoder } from 'meshoptimizer';
import sharp from 'sharp';

const ROOT = resolve(import.meta.dirname, '..');
const BLENDER = process.env.BLENDER_PATH ?? 'C:/Program Files/Blender Foundation/Blender 4.5/blender.exe';

/**
 * script: Blender script that builds the model; source: an existing GLB to optimize instead.
 * stripNormals: meshes shaded flat at runtime, so their normals are rebuilt in the browser.
 * keepNodes: models whose node names and hierarchy drive animation, so they are not flattened.
 */
const ASSETS = [
  {
    name: 'atlas-valley',
    script: 'atlas_valley.py',
    out: 'public/models/atlas/valley.glb',
    budgetKB: 2600,
    stripNormals: ['terrain', 'horizon', 'trail'],
  },
  {
    name: 'aeris-drone',
    script: 'aeris_drone.py',
    out: 'public/models/aeris/drone.glb',
    budgetKB: 900,
    keepNodes: true,
  },
  {
    name: 'aeris-monitor',
    script: 'aeris_monitor.py',
    out: 'public/models/aeris/monitor.glb',
    budgetKB: 400,
    keepNodes: true,
  },
  {
    name: 'helios-station',
    script: 'helios_station.py',
    out: 'public/models/helios/station.glb',
    budgetKB: 18000,
    textureSize: 4096,
    sharpenGenerated: ['shuttle_tex', 'buoy_tex'],
    keepNodes: true,
  },
  {
    name: 'atrium-museum',
    script: 'atrium_museum.py',
    out: 'public/models/atrium/museum.glb',
    budgetKB: 6500,
    textureSize: 2048,
    keepNodes: true,
  },
  {
    name: 'atrium-robot',
    script: 'atrium_visitor.py',
    out: 'public/models/atrium/robot.glb',
    budgetKB: 500,
    keepNodes: true,
  },
];

const args = process.argv.slice(2);
// BLENDER_ARGS passes options to the model script (say a design variant) and ASSET_OUT writes
// the result elsewhere, so variants can be compared without touching the published model.
const blenderArgs = (process.env.BLENDER_ARGS ?? '').split(' ').filter(Boolean);
const skipBlender = args.includes('--skip-blender');
const filters = args.filter((a) => !a.startsWith('--'));
const selected = ASSETS.filter((a) => filters.length === 0 || filters.some((f) => a.name.includes(f)));

if (selected.length === 0) {
  console.error(`No asset matches ${filters.join(', ')}`);
  process.exit(1);
}

await MeshoptEncoder.ready;
await MeshoptDecoder.ready;
const io = new NodeIO()
  .registerExtensions(ALL_EXTENSIONS)
  .registerDependencies({ 'meshopt.decoder': MeshoptDecoder, 'meshopt.encoder': MeshoptEncoder });

const stripNormals = (names) => (document) => {
  for (const mesh of document.getRoot().listMeshes()) {
    if (!names.includes(mesh.getName())) continue;
    for (const primitive of mesh.listPrimitives()) primitive.setAttribute('NORMAL', null);
  }
};

const report = [];
let failed = false;

for (const asset of selected) {
  const raw = join(ROOT, 'tools/out/raw', `${asset.name}.glb`);
  const out = process.env.ASSET_OUT && selected.length === 1 ? resolve(ROOT, process.env.ASSET_OUT) : join(ROOT, asset.out);
  mkdirSync(dirname(raw), { recursive: true });
  mkdirSync(dirname(out), { recursive: true });

  if (asset.source) {
    copyFileSync(join(ROOT, asset.source), raw);
  } else if (!skipBlender) {
    console.log(`\n[assets] ${asset.name}: building in Blender`);
    const started = Date.now();
    // A stale export must never pass for a fresh one, and a Python error must fail the build.
    rmSync(raw, { force: true });
    const result = spawnSync(
      BLENDER,
      ['--background', '--factory-startup', '--python-exit-code', '1', '--python', join(ROOT, 'tools/blender', asset.script), '--', '--out', raw, ...blenderArgs],
      { stdio: ['ignore', 'pipe', 'pipe'], encoding: 'utf8' },
    );
    const log = `${result.stdout ?? ''}${result.stderr ?? ''}`;
    for (const line of log.split(/\r?\n/)) if (line.includes('[pw]') || /error|traceback/i.test(line)) console.log(`  ${line}`);
    if (result.status !== 0 || !existsSync(raw)) {
      console.error(`[assets] ${asset.name}: Blender failed (exit ${result.status})`);
      console.error(log.split(/\r?\n/).slice(-30).join('\n'));
      failed = true;
      continue;
    }
    console.log(`  built in ${((Date.now() - started) / 1000).toFixed(1)} s`);
  }

  const document = await io.read(raw);
  const transforms = [dedup()];
  if (asset.stripNormals) transforms.push(stripNormals(asset.stripNormals));
  if (!asset.keepNodes) transforms.push(instance({ min: 4 }), flatten({ cleanup: false }));
  // Empty nodes are camera anchors and markers read by the scenes, and some UVs only receive
  // textures at runtime, so both survive pruning.
  transforms.push(weld(), prune({ keepLeaves: true, keepAttributes: true }));
  if (asset.sharpenGenerated) {
    // the colour maps TRELLIS.2 bakes come back soft: an unsharp mask on the base colour of the
    // generated materials named here (not the station's, whose fuzzy seams it only haloes)
    for (const material of document.getRoot().listMaterials()) {
      if (!asset.sharpenGenerated.includes(material.getName())) continue;
      const tex = material.getBaseColorTexture();
      const image = tex?.getImage();
      if (!tex || !image) continue;
      tex.setImage(new Uint8Array(await sharp(Buffer.from(image)).sharpen({ sigma: 1.0, m1: 1.0, m2: 2.0 }).jpeg({ quality: 92 }).toBuffer()));
      tex.setMimeType('image/jpeg');
    }
  }
  if (document.getRoot().listTextures().length > 0) {
    transforms.push(textureCompress({ encoder: sharp, targetFormat: 'webp', resize: [asset.textureSize ?? 1024, asset.textureSize ?? 1024] }));
  }
  transforms.push(meshopt({ encoder: MeshoptEncoder, level: 'medium' }));
  await document.transform(...transforms);
  await io.write(out, document);

  const rawKB = statSync(raw).size / 1024;
  const outKB = statSync(out).size / 1024;
  const over = outKB > asset.budgetKB;
  if (over) failed = true;
  report.push({ asset: asset.name, rawKB: rawKB.toFixed(0), outKB: outKB.toFixed(0), budgetKB: asset.budgetKB, status: over ? 'OVER BUDGET' : 'ok' });
}

console.log('');
console.table(report);
if (failed) {
  console.error('[assets] finished with errors');
  process.exit(1);
}
