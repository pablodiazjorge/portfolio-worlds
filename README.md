# portfolio-worlds

[Versión en español](README.es.md)

The portfolio of Pablo Díaz-Jorge told four ways. Every world holds the same content (about, experience, projects and contact) and walks you through it with a different 3D scene, rendered with three.js on WebGPU and falling back to WebGL 2 where WebGPU is not available.

| Key | World | How you move through it |
| --- | --- | --- |
| 1 | Atlas | Scroll flies the camera up an alpine route at dawn; one camp per job, projects from the ridge, contact at the summit observatory. |
| 2 | Aeris | A drone in a product studio comes apart into five layers, one per job, each linked to its text by a callout line. |
| 3 | Helios | A shuttle leaves a procedural planet, flies through one gate per job and docks at a space station, with live telemetry. |
| 4 | Atrium | A museum you walk through with a robot: paintings are projects, lit panels are jobs, and a gallery guide walks you to any piece. |

Keys 1 to 4 switch worlds from anywhere and 0 returns to the hub. Every page exists in English (`/atlas`) and Spanish (`/es/atlas`), prerendered with its own title, description, Open Graph image and hreflang links.

## Stack

- Angular 22 (standalone, zoneless, signals) with static prerendering of all twelve routes
- three.js r186 with `WebGPURenderer` and TSL node materials; bloom through `RenderPipeline` in Helios
- Lenis for smooth scrolling, with section anchors driving a keyframe camera rig
- Tailwind CSS 4 plus per-world stylesheets and self-hosted variable fonts
- Blender 4.5 run headless to build every model from a Python script, optimized with glTF Transform and meshopt

## Commands

```bash
npm install
npm start              # dev server on http://localhost:4200
npm run build          # static site in dist/portfolio-worlds/browser
npm test               # unit tests with Vitest
npm run assets         # rebuild every 3D model (needs Blender 4.5)
npm run assets -- atlas --skip-blender   # re-optimize one model from its raw export
```

`?webgl` forces the WebGL 2 backend and `?quality=low|medium|high` overrides the device tier, which is handy for testing.

## 3D asset pipeline

Each model is a deterministic Python script in `tools/blender/` that builds the scene with `bpy` and `bmesh` and exports a GLB. `tools/build-assets.mjs` runs Blender headless, then deduplicates, instances repeated meshes, welds, prunes and compresses with meshopt, and fails when a model goes over its size budget. The optimized files in `public/models/` are committed, so deploying does not need Blender.

| Model | Size | Budget |
| --- | --- | --- |
| Atlas valley | 470 KB | 1600 KB |
| Aeris drone | 84 KB | 900 KB |
| Helios station | 88 KB | 900 KB |
| Atrium museum | 74 KB | 900 KB |
| Atrium robot | 216 KB | 500 KB |

Set `BLENDER_PATH` when Blender is not installed in `C:/Program Files/Blender Foundation/Blender 4.5/`.

The scripts also work interactively through [Blender MCP](https://github.com/ahujasid/blender-mcp) if you want an agent to edit a model live: install the add-on with `uvx mcp-for-blender install-addon`, register the server with `claude mcp add blender uvx mcp-for-blender` and press Connect in the MCP for Blender tab of the 3D viewport. The build itself only needs headless Blender.

## Architecture

- `src/app/core/engine` owns a single renderer and canvas that survive navigation. Worlds mount a `WorldScene` (load, build, update, dispose); the engine compiles its pipelines before fading it in and frees it when the page leaves.
- `src/app/core/scroll` turns page scroll into a keyframe position, holding the camera on each section while it is read. Reduced motion turns off smooth scrolling and cuts between stops.
- `src/app/landings/<world>` holds each page (HTML content, always readable without WebGL) and its scene.
- `src/app/content` holds the portfolio in both languages, typed so the Spanish copy keeps the same shape as the English one.

## Deploying to Vercel

Import the repository as a new project. `vercel.json` sets the build command, the output directory, immutable caching for hashed files and a few security headers, so no settings are needed in the dashboard. If the site lives somewhere other than `https://worlds.pablodiazjorge.com`, change `SITE_ORIGIN` in `src/app/core/site.service.ts` so canonical and Open Graph URLs point to the right host.

## Credits

- Robot character by Tomás Laulhé (Quaternius), CC0 1.0, from the three.js examples; see `tools/vendor/README.md`.
- Fonts: Instrument Sans, Fraunces, Unbounded, Syne, Michroma and Cormorant Garamond, all under the SIL Open Font License, served through Fontsource.
- three.js, Lenis and glTF Transform under their respective licenses.
