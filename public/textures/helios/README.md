# Textures of the HELIOS planet

All four maps come from NASA imagery, which is in the public domain (https://www.nasa.gov/nasa-brand-center/images-and-media/):

- `earth-day.webp` (4096 x 2048): Blue Marble Next Generation with topography and bathymetry, August 2004, by Reto Stöckli, NASA Earth Observatory (https://visibleearth.nasa.gov/images/73776), from the 5400 x 2700 JPEG.
- `earth-clouds.webp` (2048 x 1024): the combined cloud map of the Blue Marble 2002 set (https://visibleearth.nasa.gov/images/57747).
- `earth-night.webp` (2048 x 1024): Black Marble 2016, the Earth at night at 3 km (https://visibleearth.nasa.gov/images/144898), from the 13500 x 6750 JPEG.
- `earth-ocean.webp` (2048 x 1024): an ocean mask derived here from the day map (water where blue beats red), which the scene uses to polish the seas.

The scene lights the day map with the sun, blends the night lights in past the terminator, lays the clouds on a second sphere whose shadows fall on the ground, and wraps an atmosphere shell round it all.

## The station's hull

`hull-diffuse.webp`, `hull-normal.webp` and `hull-rough.webp` (1024 x 1024) are the colour, normal (GL) and
roughness maps of Blue Metal Plate by Rob Tuytel on Poly Haven (https://polyhaven.com/a/blue_metal_plate),
CC0 (https://polyhaven.com/license), converted from the 1K JPEGs to WebP. The scene drops the colour map to
its luminance and tints it white, so only the panel seams and the wear of the paint remain, and samples the
three maps triplanar in the station's own frame in plates of 2 m, so the panels turn with the wheel. It was
chosen among five CC0 candidates (a weathered white painted steel, two sci-fi octagon platings and a scratched
white plastic from ambientCG, besides this one) on comparison sheets kept in
`_docs-internal/process/helios/2026-10-16-texturas-casco-*.jpg`.
