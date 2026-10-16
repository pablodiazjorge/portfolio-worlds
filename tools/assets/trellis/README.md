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
- `helios_station3.glb`: the orbital station, from `_docs-internal/reference/helios/station-plain-2.png`
  (Qwen-Image-2512, the picture the user chose among those asked for with a plain hull: a smooth white
  torus, two long modules crossing it along one axis with docking ports at their ends, two arrays on the
  other axis and a hub with a domed docking collar on top; Qwen still drew a few panel lines on the ring).
  1536 cascade, seed 7, a 360k-face target and 4K textures (`station-pipeline.sh`, 230 s); prepared 34 m
  across with its origin at the centre and its hub axis upright, 300k faces, 4K colour and 2K
  metallic-roughness (12.0 MB); `helios_station.py` shifts it 0.1 m onto its hub's axis, tips it so the
  dome's collar faces the approach and marks the docking point with the empty `dock`; the scene turns the
  whole wheel slowly about its hub, lifts the bake a tenth (it comes back a shade dark), flattens the
  ring's colour to the paint and draws its seams itself, one every 18 degrees and none across the joints
  with the arms, because TRELLIS bakes a picture's thin panel lines as wide, fuzzy bands (audit in
  `_docs-internal/process/helios/2026-10-15-auditoria-estacion-lisa.md`); the modules keep their bake. Its
  two arrays, unequal and askew, are cut away with their masts and drawn again as two identical panels
  on masts from the hub to the ring, and a hatch closes the port; the debris the cut leaves by the ring
  (sockets, a plate and a bar, rods on the outer edge, the yoke by the hub) goes by rules that pin each
  piece down by colour, size and pocket together, because the ring's skin comes in thousands of small
  patches, its section is not uniform and its inner equator is baked black (broader rules opened holes,
  caught by a coverage check and by renders of the joints from inside the ring; see the process report,
  pass 14); the masts run on to 12.3 m, into the inner wall, which is recessed to 11.5 m on that axis, and end in a drawn foot that covers the old mount. It
  replaces `helios_station.glb`, the wheel on four spokes from `station-8-sq.png` whose bent solar wings
  had to be cut off and drawn again, removed from the repository with it; an intermediate smooth station
  from `station-smooth-1.png` (a torus on two spokes with a hub cylinder and antennas, `helios_station2`)
  was placed, audited and set aside for this one.
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
