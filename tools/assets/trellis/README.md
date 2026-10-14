# Generated statue

`statue.glb` is the robot statue of the ATRIUM pedestal, generated on 2026-10-14 from a crop of the
reference painting (`_docs-internal/reference/statue-gen.png`, 1200 x 1340, background removed by
the pipeline itself) with Microsoft TRELLIS.2 (image to 3D), run locally on an RTX 4070 Ti 12 GB
through the TRELLIS.2-stableprojectorz one-click package (API on 127.0.0.1:7960, launcher in
`.ai-tools/trellis2/launch-api.bat`). Two runs with the same seed, so the pose is the same: first
the 1024 cascade (seed 7, guidance 7.5, 16 steps, 80k-face target, 2K textures, 227 s; raw
`statue_raw.glb`, 11 MB, 75k faces), then the 1536 cascade used now (seed 7, guidance 7.5, 20
steps, 160k-face target, 4K textures, 574 s; raw `statue_1536_raw.glb`, 33 MB, 153k faces). Raw
files are not committed. The asset was prepared with `tools/blender/statue_prepare.py`: one object
named `statue` with the material `statue_tex`, centred with the feet sunk 3 cm into the ground,
2.9 m tall, facing -Y, decimated to 100k faces, only the base colour map kept, shrunk from 4K to
2K JPEG (4.7 MB). The museum script places it on the pedestal with
`place_asset("trellis/statue", ...)` when the file exists, and the scene lifts its baked colour by
30 % so it reads as pale stone.

Licence: TRELLIS.2 is MIT, but it bundles NVIDIA components licensed for research and evaluation
only, so the generated asset is not for sale; it is used here only as decoration of a personal
portfolio. See https://github.com/microsoft/TRELLIS.2 and
https://github.com/IgorAherne/TRELLIS.2-stableprojectorz.
