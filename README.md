# portfolio-worlds

> **Status: experiment, finished; not maintained.** A test of programming with local models, MCP and WebGPU; the living portfolio is [pablodiazjorge.com](https://www.pablodiazjorge.com/). See [Limitations](#limitations).

[Versión en español](README.es.md)

My portfolio, told four ways. Every world holds the same content (about, experience, projects and contact) and walks you through it with a different 3D scene, rendered with three.js on WebGPU and falling back to WebGL 2 where WebGPU is not available.

| Key | World | How you move through it |
| --- | --- | --- |
| 1 | Atlas | Scroll flies the camera up an alpine route at dawn; one camp per job, projects from the ridge, contact at the summit observatory. |
| 2 | Aeris | A holographic cargo drone crosses a dark studio from stop to stop, one per job, carrying on a chain the monitor where it all began. |
| 3 | Helios | A shuttle leaves the Earth, drawn from NASA imagery, passes one navigation buoy per job and docks at a space station, with live telemetry. |
| 4 | Atrium | A museum you walk through with a robot: the paintings are projects, the glass cases hold the jobs, the statue tells about me and the lectern by the entrance is the contact; a gallery guide walks you to any piece. |

Keys 1 to 4 switch worlds from anywhere and 0 returns to the hub. Every page exists in English (`/atlas`) and Spanish (`/es/atlas`), prerendered with its own title, description, Open Graph image and hreflang links.

## An experiment, not the living portfolio

This site was an experiment, not the portfolio I keep up to date: a test of programming with local models, MCP servers and WebGPU on a real deliverable. It is finished and not maintained. It freezes my profile as of October 2026 and will not follow it from here; the current version lives at [pablodiazjorge.com](https://www.pablodiazjorge.com/). What I set out to try was a way of working: WebGPU and TSL in production, an asset pipeline that runs Blender from scripts and, above all, development with AI coding agents under my direction, mixing local generation models with hosted ones, MCP servers and the practices that make that work reviewable. The result stands as it is, with the state of the tools and of my experience at that date.

## How it was built

The site was developed end to end with AI coding agents (Claude Code) under my direction. I chose the concepts and the reference pictures, reviewed every capture the agents produced, kept what worked and discarded what did not (a station generated from a picture lost to one drawn by script; a shuttle drawn by script lost to the generated one), and made every commit by hand from the messages the agents prepared. The agents wrote the code and the Blender scripts, adapted the copy of the classic portfolio, and worked with:

- Blender 4.5 headless for the asset pipeline, and [Blender MCP](https://github.com/ahujasid/blender-mcp) to model live in my open Blender, checking each pass against the reference picture on renders from fixed cameras.
- Local generation models alongside Claude: Qwen-Image through ComfyUI for concept pictures and Microsoft TRELLIS.2 for image-to-3D, both run on my own GPU. The Helios shuttle and buoy and the Atrium statue, banners and wall sconces come from that chain; the station, the robot and everything else is drawn by script.
- Playwright through MCP to verify every change in a real browser: route captures at every stop, before/after crops at 2x, console and network checks and a production build before each commit.
- CC0 or public-domain assets only: textures from Poly Haven and ambientCG, a model from Poly Haven and NASA imagery for the Earth.
- Practices: specifications written in plan mode, an independent audit of the station's shader by a second agent, a reviewed commit log, verification sheets kept as process records and a persistent memory of lessons between sessions.

## Stack

- Angular 22 (standalone, zoneless, signals) with static prerendering of all ten routes
- three.js r186 with `WebGPURenderer` and TSL node materials; in Helios a selective bloom through `RenderPipeline` that only picks up what emits light
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

`?webgl` forces the WebGL 2 backend and `?quality=low|medium|high` overrides the device tier, which is handy for testing. The tier comes from memory, cores and touch, capped by what the GPU turns out to be (integrated parts stop at medium, software renderers at low); the page reports it in `data-quality` on the `<html>` element.

## 3D asset pipeline

Each model is a deterministic Python script in `tools/blender/` that builds the scene with `bpy` and `bmesh` and exports a GLB. `tools/build-assets.mjs` runs Blender headless, then deduplicates, instances repeated meshes, welds, prunes and compresses with meshopt, and fails when a model goes over its size budget. The optimized files in `public/models/` are committed, so deploying does not need Blender.

| Model | Size | Budget |
| --- | --- | --- |
| Atlas valley | 2583 KB | 2600 KB |
| Aeris drone | 109 KB | 900 KB |
| Aeris monitor | 41 KB | 400 KB |
| Helios station | 5847 KB | 18000 KB |
| Atrium museum | 5600 KB | 6500 KB |
| Atrium robot | 154 KB | 500 KB |

Set `BLENDER_PATH` when Blender is not installed in `C:/Program Files/Blender Foundation/Blender 4.5/`.

The scripts also work interactively through [Blender MCP](https://github.com/ahujasid/blender-mcp), which is how the Helios station was modelled: install the add-on with `uvx mcp-for-blender install-addon`, register the server with `claude mcp add blender uvx mcp-for-blender` and press Connect in the MCP for Blender tab of the 3D viewport. The build itself only needs headless Blender.

### Generated and third-party assets

- `tools/assets/trellis/` holds the assets generated with TRELLIS.2 from Qwen-Image pictures (the Helios shuttle and buoy; the Atrium statue, banners and sconces), and its README says how each was prepared. TRELLIS.2 is MIT but bundles NVIDIA components licensed for research and evaluation only, so these assets are not for sale: they are decoration of a personal portfolio.
- `tools/assets/polyhaven/` holds the Television 02 model (CC0).
- `public/textures/atrium/` and `public/textures/helios/` hold the textures (Poly Haven and ambientCG, CC0) and the NASA maps of the Earth (public domain), each with its source in a README.

## Architecture

- `src/app/core/engine` owns a single renderer and canvas that survive navigation. Worlds mount a `WorldScene` (load, build, update, dispose); the engine compiles its pipelines before fading it in and frees it when the page leaves.
- `src/app/core/scroll` turns page scroll into a keyframe position, holding the camera on each section while it is read. Reduced motion turns off smooth scrolling and cuts between stops.
- `src/app/landings/<world>` holds each page (HTML content, always readable without WebGL) and its scene.
- `src/app/content` holds the portfolio in both languages, typed so the Spanish copy keeps the same shape as the English one.

## Deploying to Vercel

Import the repository as a new project. `vercel.json` sets the build command, the output directory, immutable caching for hashed files and a few security headers, so no settings are needed in the dashboard. If the site lives somewhere other than `https://worlds.pablodiazjorge.com`, change `SITE_ORIGIN` in `src/app/core/site.service.ts` so canonical and Open Graph URLs point to the right host.

## Limitations

- **Not maintained.** The dependencies and the content stay as they were in October 2026 and will not be updated, security fixes included.
- **Some files are very long.** `tools/blender/atlas_valley.py` (2,372 lines), `tools/blender/atrium_museum.py` (1,130) and `src/app/landings/atrium/atrium.scene.ts` (1,044) were never split into smaller modules, so they are hard to read and to change.
- **Large binaries live in git.** About 40 MB of GLB models, textures and images are committed directly, without Git LFS, and the history keeps every earlier version of them. The heaviest are the TRELLIS.2 sources in `tools/assets/trellis/` (up to 7.8 MB each) and the Helios and Atrium models (about 6 MB each), which also make the first load of those two worlds slow on a weak connection.
- **Few tests.** Four Vitest spec files cover the content, the world registry and the device and DPR helpers. The scenes, the camera rig and the asset pipeline have no automated tests; they were checked by eye, through the Playwright captures described above.

## Licence

The code (the Angular application, the scenes, the Blender scripts and the asset pipeline) is released under the [MIT License](LICENSE). The portfolio's own content is not: the texts of my profile, experience and projects, the project covers and the hub and link images are personal and not licensed for reuse. The third-party and generated assets keep their own terms, listed in the credits below and in the READMEs next to each of them: the Poly Haven and ambientCG assets are CC0, the NASA imagery is public domain, and the meshes generated with TRELLIS.2 are not for sale.

## Credits

- Textures: Marble 01 and Blue Metal Plate by Rob Tuytel and Dark Wood by Dario Barresi, Dimitrios Savva and Rico Cilliers (Poly Haven, CC0); Marble 014 and Fabric 061 (ambientCG, CC0). Model: Television 02 by Benny Weimer (Poly Haven, CC0).
- Earth: NASA Blue Marble, Black Marble and cloud imagery, public domain.
- Generated assets: concept pictures from Qwen-Image (Apache-2.0) and meshes from Microsoft TRELLIS.2 (MIT, with NVIDIA components for research and evaluation only); see `tools/assets/trellis/README.md`.
- Fonts: Instrument Sans, Fraunces, Space Grotesk, VT323, Michroma and Cormorant Garamond, all under the SIL Open Font License, served through Fontsource.
- three.js, Lenis and glTF Transform under their respective licenses.
