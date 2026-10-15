# Generated assets (TRELLIS.2, local)

Assets of the ATRIUM gallery generated on 2026-10-14 and 2026-10-15 with Microsoft TRELLIS.2
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

Face budgets were chosen on close-ups of the raw meshes decimated to several counts (sheets in
`_docs-internal/process/atrium/2026-10-15-aplique-decimado-*.jpg`): the sconce's scrollwork is
jagged below 45k faces and the banner's fringe below 40k.

Licence: TRELLIS.2 is MIT, but it bundles NVIDIA components licensed for research and evaluation
only, so the generated assets are not for sale; they are used here only as decoration of a
personal portfolio. The source images come from Qwen-Image-2512 (Apache-2.0). See
https://github.com/microsoft/TRELLIS.2 and https://github.com/IgorAherne/TRELLIS.2-stableprojectorz.
