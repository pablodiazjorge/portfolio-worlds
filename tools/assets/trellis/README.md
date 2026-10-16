# Generated assets (TRELLIS.2, local)

Assets of the ATRIUM gallery and the HELIOS orbit generated on 2026-10-14 and 2026-10-15 with Microsoft TRELLIS.2
(image to 3D) run locally on an RTX 4070 SUPER 12 GB through the TRELLIS.2-stableprojectorz
one-click package (API on 127.0.0.1:7960, launcher in `.ai-tools/trellis2/launch-api.bat`), and
prepared with `tools/blender/statue_prepare.py` (origin at the anchor the museum script holds,
centred, facing -Y, scaled, decimated, colour map and, for the metal props, the metallic-roughness
map, one material named `<name>_tex` that the scene recognises). Raw generations (`*_raw.glb`) are
not committed. The museum script places each asset when its file exists with
`place_asset("trellis/<name>", ...)`.

- `statue.glb`: the robot statue of the pedestal, from a crop of the reference painting
  (`_docs-internal/reference/statue-gen.png`). 1536 cascade, seed 7, 20 steps, 160k-face target,
  4K textures, 574 s; prepared 2.9 m tall, feet sunk 3 cm, 100k faces, 2K colour (4.7 MB).
- `banner.glb`: the hanging banner of crimson damask with the robot head in brass, from the image
  generated with Qwen-Image-2512 (`_docs-internal/reference/props/banner-4-crop.png`, the stand
  pole cropped out). 1536 cascade, seed 7, 20 steps, 120k-face target, 4K textures, 220 s; prepared
  1.4 m wide with its origin on the rod (`--anchor top`), hung straight with the modelled head
  squashed to a relief (`--hang 0.2`: a fifth of its depth, as the appliqué of the picture), 40k
  faces, 2K colour and 1K metallic-roughness (2.3 MB). Fourteen copies hang in the nave, the far
  room and the balcony, scaled in place; those on the piers hang at right angles to the wall from a
  brass pole, facing the entrance like the ones of the reference.
- `sconce.glb`: the gothic wall sconce of iron and brass with three candles and a quatrefoil
  plate, from `_docs-internal/reference/props/candelabrum-2.png` (Qwen-Image-2512). 1536 cascade,
  seed 7, 175 s; prepared 1.0 m tall with its origin on the back plate (`--anchor back`), 45k faces,
  2K colour and 1K metallic-roughness (2.4 MB). Twenty-four copies on the crests of the pier shafts,
  with flames drawn by the script on the candle tips measured on the mesh.

- `helios_shuttle.glb`: the orbital shuttle of HELIOS, from `_docs-internal/reference/helios/shuttle-10-sq.png`
  (Qwen-Image-2512, a white spaceplane with navy stripes). 1536 cascade, seed 7, a dense 220k-face target
  and 4K textures (generate-prop-hd.sh, 213 s); prepared 3.3 m long with its nose to +X and its origin at
  the centre (`--anchor centre --yaw 90`), the landing gear the picture insisted on cut away under the belly
  (`--cut-below 0.19`), 180k faces, 4K colour and 2K metallic-roughness (7.7 MB); the asset pipeline sharpens
  the colour map before compressing it (`sharpenGenerated` names its material and the buoy's; the station's
  bake only gains haloes from it) and the scene samples it with full anisotropy and adds
  five glowing discs on the nozzles measured on a rear orthographic render.
- The orbital station is not generated any more: `tools/blender/helios_station.py` draws it from
  primitives after the first picture of the series (`_docs-internal/reference/helios/station-8.png`, a
  wheel on four spokes with tank modules, a hub tower, a docking tube and two solar wings on trusses),
  modelled live in Blender through its MCP add-on and checked against the picture on headless renders.
  Three generated stations came before it and left the repository with their replacement: the wheel of
  `station-8-sq.png`, whose bent wings had to be cut off and drawn again; the smooth torus of
  `station-smooth-1.png` (`helios_station2`); and the plain hull of `station-plain-2.png`
  (`helios_station3`), whose arrays, debris and docking mouth took a long run of cutting rules (process
  report, passes 10 to 16). TRELLIS bakes a picture's thin panel lines as wide, fuzzy bands and its skin
  comes in thousands of small patches that no rule tells from debris, which is why a drawn hull won.
- `helios_buoy.glb`: the navigation buoy of the route, from `_docs-internal/reference/helios/buoy-1.png`
  (Qwen-Image-2512, one picture as the user asked: a white octagonal body with a red beacon on a mast, two
  solar panels and antennas). 1536 cascade, seed 7, 150k-face target and 4K textures (363 s); prepared 1.6 m
  tall with its origin at the centre, 90k faces, 4K colour and 2K metallic-roughness (5.4 MB); the station
  script places it as the template `buoy` with a drawn strobe sphere on its lamp (0.52 m up), and the scene
  clones it beside the five waypoints with the strobe flashing on a material of its own.
- The alternatives generated at the same time (`shuttle-11`, `station-2`) were prepared and compared on
  renders but not kept.

Face budgets were chosen on close-ups of the raw meshes decimated to several counts (sheets in
`_docs-internal/process/atrium/2026-10-15-aplique-decimado-*.jpg`): the sconce's scrollwork is
jagged below 45k faces and the banner's fringe below 40k.

Licence: TRELLIS.2 is MIT, but it bundles NVIDIA components licensed for research and evaluation
only, so the generated assets are not for sale; they are used here only as decoration of a
personal portfolio. The source images come from Qwen-Image-2512 (Apache-2.0). See
https://github.com/microsoft/TRELLIS.2 and https://github.com/IgorAherne/TRELLIS.2-stableprojectorz.
