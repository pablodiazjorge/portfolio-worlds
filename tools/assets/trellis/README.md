# Generated statue

`statue.glb` is the robot statue of the ATRIUM pedestal, generated on 2026-10-14 from a crop of the
reference painting (`_docs-internal/reference/statue-gen.png`, 1200 x 1340, background removed by
the pipeline itself) with Microsoft TRELLIS.2 (image to 3D), run locally on an RTX 4070 Ti 12 GB
through the TRELLIS.2-stableprojectorz one-click package (API on 127.0.0.1:7960, launcher in
`.ai-tools/trellis2/launch-api.bat`). Parameters: seed 7, guidance 7.5, 16 steps, 1024 cascade,
80k-face target, 2048 textures; 227 s on the GPU. The raw result (`statue_raw.glb`, 11 MB, 75k
faces, two 2K textures, not committed) was prepared with `tools/blender/statue_prepare.py`: one
object named `statue` with the material `statue_tex`, centred with the feet sunk 3 cm into the
ground, 2.9 m tall, facing -Y, decimated to 60k faces, only the base colour map kept at 2K JPEG
(2.4 MB). The museum script places it on the pedestal with `place_asset("trellis/statue", ...)` when
the file exists, and the scene lifts its baked colour by 30 % so it reads as pale stone.

Licence: TRELLIS.2 is MIT, but it bundles NVIDIA components licensed for research and evaluation
only, so the generated asset is not for sale; it is used here only as decoration of a personal
portfolio. See https://github.com/microsoft/TRELLIS.2 and
https://github.com/IgorAherne/TRELLIS.2-stableprojectorz.
