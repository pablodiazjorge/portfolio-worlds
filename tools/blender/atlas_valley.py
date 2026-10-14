"""ATLAS: a low-poly alpine valley with a trail that climbs from base camp to a summit observatory.

Blender axes: X east, Y north, Z up (the glTF exporter converts to Y up).
The camera rig in the app reads the `anchor_*` empties and the `water` empty; `smoke_*` empties
mark chimneys and campfires for the app's smoke.
"""

import argparse
import math
import os
import random
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector, noise
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lib"))
import pw  # noqa: E402

args = pw.parse_args()
# Design variants, so they can be built side by side and compared before one becomes the default.
_variants = argparse.ArgumentParser()
_variants.add_argument("--trees", choices=("a", "b", "c"), default="a")
_variants.add_argument("--grass", choices=("a", "b", "c"), default="a")
VARIANT = _variants.parse_known_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])[0]
pw.reset(args.seed)
noise.seed_set(args.seed)
rng = random.Random(args.seed)

SIZE = 440.0
RES = 360
WATER = 1.2
SNOWLINE = 66.0
TRAIL_HALF = 0.55

# Trail waypoints: (name, x, y, target altitude). The terrain grows a ridge whose crest follows them.
ROUTE = [
    ("base", 22.0, -104.0, 4.0),
    ("camp_1", 36.0, -60.0, 13.0),
    ("camp_2", 55.0, -16.0, 25.0),
    ("camp_3", 47.0, 34.0, 40.0),
    ("camp_4", 62.0, 80.0, 58.0),
    ("camp_5", 49.0, 114.0, 78.0),
    ("ridge", 24.0, 126.0, 88.0),
    ("summit", 40.0, 150.0, 112.0),
]
SITES = {name: (x, y) for name, x, y, _ in ROUTE}
PAD = {"base": 9.0, "summit": 8.0, "ridge": 5.5}
LAKE = (-6.0, -62.0, 26.0, 17.0)


def catmull(points, samples_per_segment):
    out = []
    pts = [points[0]] + list(points) + [points[-1]]
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = (Vector(p) for p in pts[i - 1:i + 3])
        for s in range(samples_per_segment):
            t = s / samples_per_segment
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(Vector(points[-1]))
    return out


ROUTE_SAMPLES = np.array([[p.x, p.y, p.z] for p in catmull([(x, y, alt) for _, x, y, alt in ROUTE], 120)])


def route_distance(x, y):
    """Distance on the ground plane to the trail and the trail altitude at the closest point."""
    dx = ROUTE_SAMPLES[:, 0] - x
    dy = ROUTE_SAMPLES[:, 1] - y
    d2 = dx * dx + dy * dy
    k = int(np.argmin(d2))
    return math.sqrt(float(d2[k])), float(ROUTE_SAMPLES[k, 2])


def route_field(x, y):
    """Distance to the trail, the trail altitude there and the height of the ridge under it.

    Both are averages that favour the nearest stretch of trail. Where two stretches at different
    heights are about as far away they hand over smoothly; the nearest point alone jumps there
    and left tall vertical seams. An upper envelope of every stretch avoids the seams but lets
    a higher stretch bury a lower one, and cutting the trail back down then digs a gorge.
    """
    dx = ROUTE_SAMPLES[:, 0] - x
    dy = ROUTE_SAMPLES[:, 1] - y
    d = np.sqrt(dx * dx + dy * dy)
    nearest = float(d.min())
    w = np.exp(-(d - nearest) / 1.5)
    alt = float((w * ROUTE_SAMPLES[:, 2]).sum() / w.sum())
    wc = np.exp(-(d - nearest) / 8.0)
    cones = ROUTE_SAMPLES[:, 2] - d * 0.42 - d * d * 0.004
    crest = float((wc * cones).sum() / wc.sum())
    return nearest, alt, crest


def axis_x(y):
    return 16.0 * math.sin(y * 0.011) - 10.0 + 6.0 * math.sin(y * 0.029 + 1.3)


def base_height(x, y):
    ax = axis_x(y)
    d = abs(x - ax)
    floor = 2.0 + (y + 220.0) * 0.008
    walls = pw.smoothstep(9.0, 150.0, d) ** 1.25 * 84.0
    ridged = noise.ridged_multi_fractal(Vector((x * 0.011, y * 0.011, 0.5)), 0.95, 2.1, 5, 1.0, 2.0)
    walls *= 0.55 + 0.3 * ridged
    massif = pw.smoothstep(-40.0, 170.0, y) * 26.0 * (1.0 - pw.smoothstep(60.0, 200.0, abs(x - 40.0)))
    r = math.sqrt(((x - 40.0) / 40.0) ** 2 + ((y - 150.0) / 32.0) ** 2)
    rocky = 0.75 + 0.45 * noise.ridged_multi_fractal(Vector((x * 0.03, y * 0.03, 7.0)), 1.0, 2.0, 4, 1.0, 2.0)
    summit = 66.0 * math.exp(-(r ** 1.35) * 1.6) * rocky
    summit += 30.0 * math.exp(-(((x + 18.0) / 26.0) ** 2 + ((y - 168.0) / 20.0) ** 2))
    summit += 26.0 * math.exp(-(((x - 98.0) / 24.0) ** 2 + ((y - 132.0) / 22.0) ** 2))
    ends = pw.smoothstep(150.0, 220.0, abs(y)) * 36.0
    # the stream fades out before the valley ends rise, or its dry bed reads as a pale streak up the slope
    river = 2.6 * math.exp(-((x - ax) / 4.5) ** 2) * (1.0 - pw.smoothstep(118.0, 160.0, abs(y)))
    lx, ly, lrx, lry = LAKE
    lake = 5.0 * math.exp(-(((x - lx) / lrx) ** 2 + ((y - ly) / lry) ** 2))
    detail = noise.fractal(Vector((x * 0.045, y * 0.045, 3.1)), 0.7, 2.0, 3) * (0.8 + 0.04 * walls)
    # finer relief that the denser grid can actually show, rougher where the ground is high
    high = floor + walls + massif + summit + ends
    fine = noise.fractal(Vector((x * 0.13, y * 0.13, 6.2)), 0.6, 2.0, 3) * (0.35 + 0.012 * high)
    crags = noise.ridged_multi_fractal(Vector((x * 0.07, y * 0.07, 8.4)), 1.0, 2.2, 3, 1.0, 2.0) * pw.smoothstep(45.0, 95.0, high) * 2.6
    return high + detail + fine + crags - river - lake


def height(x, y):
    h = base_height(x, y)
    d, alt, crest = route_field(x, y)
    roughness = noise.ridged_multi_fractal(Vector((x * 0.05, y * 0.05, 5.0)), 1.0, 2.0, 3, 1.0, 2.0)
    crest += roughness * pw.smoothstep(4.0, 16.0, d) * (2.0 + max(crest, 0.0) * 0.05)
    # the ridge fades into the natural slopes instead of ending at a fixed distance
    blend = pw.smoothstep(0.0, 1.0, (crest - h + 6.0) / 12.0) * (1.0 - pw.smoothstep(45.0, 72.0, d))
    h = max(h, pw.lerp(h, crest, blend))
    # a corridor several cells wide, so the mesh can actually carry a smooth path
    h = pw.lerp(alt, h, pw.smoothstep(3.0, 9.0, d))
    for name, sx, sy, alt in ROUTE:
        r = PAD.get(name, 6.5)
        dist = math.hypot(x - sx, y - sy)
        h = pw.lerp(h, alt, 1.0 - pw.smoothstep(r * 0.55, r * 1.35, dist))
    return h


# --- terrain grid -------------------------------------------------------------
step = SIZE / RES
heights = [[0.0] * (RES + 1) for _ in range(RES + 1)]
coords = [[(0.0, 0.0)] * (RES + 1) for _ in range(RES + 1)]
# The grid jitter draws from its own generator; the shared one skips what the original 240 grid
# drew, so the trees, rocks and camps placed later keep their layout.
for _ in range(2 * 239 * 239):
    rng.random()
grid_rng = random.Random(f"{args.seed}-grid")
for j in range(RES + 1):
    for i in range(RES + 1):
        x = -SIZE / 2 + i * step
        y = -SIZE / 2 + j * step
        if 0 < i < RES and 0 < j < RES:
            x += grid_rng.uniform(-0.3, 0.3) * step
            y += grid_rng.uniform(-0.3, 0.3) * step
        coords[j][i] = (x, y)
        heights[j][i] = height(x, y)

# Steep rock settles into ledges: on slopes the height is pulled towards steps, which read as
# strata once shaded. Flat ground, the trail corridor and the camp pads are left alone.
LEDGE = 2.4
terraced = [row[:] for row in heights]
for j in range(1, RES):
    for i in range(1, RES):
        h = heights[j][i]
        gx = (heights[j][i + 1] - heights[j][i - 1]) / (2 * step)
        gy = (heights[j + 1][i] - heights[j - 1][i]) / (2 * step)
        steep = pw.smoothstep(0.75, 1.3, math.hypot(gx, gy))
        if steep <= 0.0:
            continue
        q = h / LEDGE
        f = q - math.floor(q)
        stepped = (math.floor(q) + pw.smoothstep(0.3, 0.7, f)) * LEDGE
        terraced[j][i] = pw.lerp(h, stepped, steep * 0.55)
heights = terraced

C = {k: Vector(pw.hex_color(v)[:3]) for k, v in {
    "meadow_low": "#6f8c50",
    "meadow_high": "#93a15c",
    "forest": "#476241",
    "rock_light": "#948b9c",
    "rock_dark": "#5e576b",
    "rock_warm": "#8f7c78",
    "snow": "#e2e6ef",
    "bank": "#a89d84",
    "earth": "#a8875c",
    "earth_worn": "#bc9d70",
    "gravel_worn": "#bab3a8",
    "gravel": "#a19a91",
    "packed_snow": "#c9d0dc",
    "pad": "#9a8a68",
}.items()}

verts, colors = [], []
for j in range(RES + 1):
    for i in range(RES + 1):
        x, y = coords[j][i]
        h = heights[j][i]
        verts.append((x, y, h))
        hl = heights[j][max(i - 1, 0)]
        hr = heights[j][min(i + 1, RES)]
        hd = heights[max(j - 1, 0)][i]
        hu = heights[min(j + 1, RES)][i]
        n = Vector((hl - hr, hd - hu, 2.0 * step)).normalized()
        slope = 1.0 - n.z
        concavity = (hl + hr + hd + hu) / 4.0 - h

        patch = noise.noise(Vector((x * 0.03, y * 0.03, 9.0)))
        grass = C["meadow_low"].lerp(C["meadow_high"], pw.smoothstep(12.0, 46.0, h))
        grass = grass.lerp(C["forest"], pw.smoothstep(-0.1, 0.45, patch) * (1.0 - pw.smoothstep(30.0, 48.0, h)))
        rock = C["rock_dark"].lerp(C["rock_light"], 0.5 + 0.5 * noise.noise(Vector((x * 0.08, y * 0.08, 2.0))))
        # strata: bands that follow the height, wobbling a little so they do not look ruled
        band = 0.5 + 0.5 * math.sin(h * 1.35 + 3.0 * noise.noise(Vector((x * 0.04, y * 0.04, 5.5))))
        rock = rock.lerp(C["rock_warm"], band * band * 0.45)
        rock_w = max(pw.smoothstep(0.2, 0.36, slope), pw.smoothstep(52.0, 72.0, h) * 0.85)
        snow_line = SNOWLINE + 5.0 * noise.noise(Vector((x * 0.05, y * 0.05, 4.0)))
        snow_w = pw.smoothstep(snow_line - 4.0, snow_line + 3.0, h) * (1.0 - pw.smoothstep(0.32, 0.5, slope))
        bank_w = 1.0 - pw.smoothstep(WATER + 0.2, WATER + 1.4, h)
        col = grass.lerp(rock, rock_w).lerp(C["snow"], snow_w).lerp(C["bank"], bank_w)

        # trampled ground around each camp
        for name, (sx, sy) in SITES.items():
            dist = math.hypot(x - sx, y - sy)
            r = PAD.get(name, 6.5)
            if dist < r:
                worn = (1.0 - pw.smoothstep(r * 0.3, r, dist)) * (0.35 if h > SNOWLINE else 0.55)
                col = col.lerp(C["pad"] if h < SNOWLINE else C["packed_snow"], worn)

        shade = 1.0 - max(0.0, min(0.32, concavity * 0.07)) + max(0.0, min(0.08, -concavity * 0.02))
        col = col * shade
        colors.append((col.x, col.y, col.z, 1.0))

faces = []
for j in range(RES):
    for i in range(RES):
        a = j * (RES + 1) + i
        b = a + 1
        c = a + (RES + 1)
        d = c + 1
        if (i + j) % 2 == 0:
            faces += [(a, b, d), (a, d, c)]
        else:
            faces += [(a, b, c), (b, d, c)]

terrain = pw.mesh_object("terrain", verts, faces, pw.vertex_color_material("terrain"))
pw.set_vertex_colors(terrain, colors)

# Exact surface queries against the built mesh, so nothing floats or sinks.
BVH = BVHTree.FromPolygons([Vector(v) for v in verts], faces)
KD = KDTree(len(verts))
for k, v in enumerate(verts):
    KD.insert(Vector(v), k)
KD.balance()


def surface(x, y):
    hit = BVH.ray_cast(Vector((x, y, 600.0)), Vector((0.0, 0.0, -1.0)))
    return hit[0].z if hit[0] is not None else 0.0


def surface_normal(x, y):
    hit = BVH.ray_cast(Vector((x, y, 600.0)), Vector((0.0, 0.0, -1.0)))
    return hit[1] if hit[1] is not None else Vector((0, 0, 1))


def terrain_color(x, y):
    _, index, _ = KD.find(Vector((x, y, surface(x, y))))
    c = colors[index]
    return Vector(c[:3])


# --- the far ranges -------------------------------------------------------------------------------------
# Three ranges at growing distance, each a band whose top is a jagged ridgeline. The farther
# ones stand higher and paler, so the haze reads in layers behind the valley; snow caps the peaks.
ring_verts, ring_faces, ring_colors = [], [], []
RANGE_SNOW = Vector(pw.hex_color("#eceaf2")[:3])


def far_range(radius, base, peak, freq, seed_z, low_hex, high_hex, snow_from, segments=220):
    low = Vector(pw.hex_color(low_hex)[:3])
    high = Vector(pw.hex_color(high_hex)[:3])
    start = len(ring_verts)
    # bottom, foot, shoulder, crest; the lower rows step in so the band has a face to shade
    rows = ((-12.0, -34.0, 0.0), (0.38, -20.0, 0.0), (0.8, -7.0, 0.35), (1.0, 0.0, 0.0))
    for share, inset, jitter in rows:
        for s_ in range(segments):
            a = s_ / segments * math.tau
            ridge = noise.ridged_multi_fractal(Vector((math.cos(a) * freq, math.sin(a) * freq, seed_z)), 0.95, 2.1, 5, 1.0, 2.0)
            crest = base + ridge * peak
            z = share if share < 0 else crest * share
            wobble = jitter * 6.0 * noise.noise(Vector((math.cos(a) * 9.0, math.sin(a) * 9.0, seed_z + 3.0)))
            rad = radius + inset + wobble
            ring_verts.append((math.cos(a) * rad, math.sin(a) * rad, z))
            tone = low.lerp(high, pw.smoothstep(base * 0.4, base + peak * 0.8, z))
            tone = tone.lerp(RANGE_SNOW, pw.smoothstep(snow_from, snow_from + 14.0, z) * 0.85)
            ring_colors.append((tone.x, tone.y, tone.z, 1.0))
    for r_ in range(len(rows) - 1):
        for s_ in range(segments):
            a_ = start + r_ * segments + s_
            b_ = start + r_ * segments + (s_ + 1) % segments
            ring_faces.append((a_, b_, b_ + segments))
            ring_faces.append((a_, b_ + segments, a_ + segments))


# all beyond the opening camera, which stands some 275 from the centre
far_range(335.0, 22.0, 52.0, 2.7, 0.5, "#5a5d7c", "#878aa6", 68.0)
far_range(440.0, 34.0, 64.0, 1.9, 2.3, "#777896", "#a2a0b9", 80.0)
far_range(560.0, 46.0, 76.0, 1.35, 4.1, "#9796b0", "#c2c0d1", 98.0)
ring = pw.mesh_object("horizon", ring_verts, ring_faces, pw.vertex_color_material("horizon"))
pw.set_vertex_colors(ring, ring_colors)

# --- materials -------------------------------------------------------------------------
M = {
    "fabric_orange": pw.material("fabric_orange", "#e5703a", 0.85),
    "fabric_yellow": pw.material("fabric_yellow", "#efbd4a", 0.85),
    "fabric_teal": pw.material("fabric_teal", "#2f8f8a", 0.85),
    "fabric_red": pw.material("fabric_red", "#c8433a", 0.85),
    "fabric_green": pw.material("fabric_green", "#5d7f3e", 0.85),
    "fabric_blue": pw.material("fabric_blue", "#3d64a8", 0.85),
    "fabric_dark": pw.material("fabric_dark", "#2a2b33", 0.9),
    "groundsheet": pw.material("groundsheet", "#5f6352", 0.95),
    "rope": pw.material("rope", "#d9cfb8", 0.9),
    "metal": pw.material("metal", "#c9ccd2", 0.45, 0.6),
    "metal_dark": pw.material("metal_dark", "#3a3d44", 0.5, 0.5),
    "wood": pw.material("wood", "#7a5537", 0.9),
    "wood_dark": pw.material("wood_dark", "#4e3524", 0.9),
    "wood_light": pw.material("wood_light", "#b08a5e", 0.85),
    "stone": pw.material("stone", "#8b8494", 0.95),
    "stone_light": pw.material("stone_light", "#b1aab5", 0.95),
    "roof": pw.material("roof", "#7a3b2e", 0.8),
    "roof_dark": pw.material("roof_dark", "#5e2b22", 0.85),
    "shutter": pw.material("shutter", "#3d6b4f", 0.7),
    "bronze": pw.material("bronze", "#a8834e", 0.45, 0.6),
    "solar": pw.material("solar", "#1d2f55", 0.3, 0.4),
    "white": pw.material("white_paint", "#eeeef0", 0.5),
    "plaster": pw.material("plaster", "#ddd6cb", 0.85),
    "glass": pw.material("glass", "#3a4a61", 0.25),
    "sign": pw.material("sign_yellow", "#f3c22f", 0.6),
    "marker_red": pw.material("marker_red", "#d23b2f", 0.6),
    "snow": pw.material("snow_block", "#e6eaf1", 0.8),
    "root": pw.material("root", "#6e5038", 0.95),
    "bush": pw.material("bush", "#3f6a3c", 0.9),
    "bush_light": pw.material("bush_light", "#5f8248", 0.9),
    "snow_print": pw.material("snow_print", "#b9c1d0", 0.9),
    "dark": pw.material("observatory_slit", "#1d2030", 0.6),
    "observatory": pw.material("observatory_white", "#eeeef0", 0.45, 0.05),
    "glow_fire": pw.material("fire_glow", "#ffb24a", 1.0, emission="#ff9a3a", emission_strength=6.0),
    "ember": pw.material("ember", "#ff7a2a", 1.0, emission="#ff6a1a", emission_strength=4.0),
    "lantern": pw.material("lantern_glass", "#ffe2a8", 1.0, emission="#ffcf7a", emission_strength=5.0),
    "window": pw.material("window_warm", "#ffd9a0", 1.0, emission="#ffc777", emission_strength=3.0),
    "window_soft": pw.material("window_soft", "#e9b97c", 1.0, emission="#ffb766", emission_strength=1.1),
    "beacon": pw.material("beacon", "#ff5a4a", 1.0, emission="#ff4a3a", emission_strength=8.0),
    "trail": pw.vertex_color_material("trail", roughness=1.0),
    "flower_white": pw.material("flower_white", "#f4f1ea", 0.8),
    "flower_yellow": pw.material("flower_yellow", "#f2c94c", 0.8),
    "flower_violet": pw.material("flower_violet", "#9a7fd1", 0.8),
    "flower_pink": pw.material("flower_pink", "#e58fa8", 0.8),
}
for k, hexcol in enumerate(("#2f6fd0", "#f4f4f0", "#d8483a", "#3f9a5a", "#f2c14e")):
    M[f"prayer_{k}"] = pw.material(f"prayer_{k}", hexcol, 0.9)


class Kit:
    """Collects prop geometry per material; each material becomes one mesh."""

    def __init__(self, prefix):
        self.prefix = prefix
        self.meshes = {}

    def bm(self, mat):
        if mat not in self.meshes:
            self.meshes[mat] = bmesh.new()
        return self.meshes[mat]

    @staticmethod
    def _place(bm, vs, origin, rot):
        bmesh.ops.rotate(bm, verts=vs, cent=(0, 0, 0), matrix=Matrix.Rotation(rot, 3, "Z"))
        bmesh.ops.translate(bm, verts=vs, vec=Vector(origin))

    def box(self, mat, origin, rot, center, size, tilt=None):
        bm = self.bm(mat)
        vs = bmesh.ops.create_cube(bm, size=1.0)["verts"]
        bmesh.ops.scale(bm, vec=Vector(size), verts=vs)
        if tilt:
            axis, angle = tilt
            bmesh.ops.rotate(bm, verts=vs, cent=(0, 0, 0), matrix=Matrix.Rotation(angle, 3, axis))
        bmesh.ops.translate(bm, verts=vs, vec=Vector(center))
        self._place(bm, vs, origin, rot)
        return vs

    def cyl(self, mat, origin, rot, a, b, r1, r2=None, seg=8):
        bm = self.bm(mat)
        a, b = Vector(a), Vector(b)
        d = b - a
        vs = pw.add_cone(bm, (0, 0, 0), r1, r1 if r2 is None else r2, max(d.length, 1e-4), segments=seg)
        rotation = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix()
        bmesh.ops.rotate(bm, verts=vs, cent=(0, 0, 0), matrix=rotation)
        bmesh.ops.translate(bm, verts=vs, vec=a)
        self._place(bm, vs, origin, rot)
        return vs

    def ico(self, mat, origin, rot, center, r, scale=(1, 1, 1), sub=1):
        bm = self.bm(mat)
        vs = bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=r)["verts"]
        bmesh.ops.scale(bm, vec=Vector(scale), verts=vs)
        bmesh.ops.translate(bm, verts=vs, vec=Vector(center))
        self._place(bm, vs, origin, rot)
        return vs

    def poly(self, mat, origin, rot, points):
        bm = self.bm(mat)
        vs = [bm.verts.new(Vector(p)) for p in points]
        bm.faces.new(vs)
        self._place(bm, vs, origin, rot)
        return vs

    def dome(self, mat, origin, rot, center, r, squash=0.65, seg=12):
        bm = self.bm(mat)
        vs = bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=seg // 2, radius=r)["verts"]
        bmesh.ops.delete(bm, geom=[v for v in vs if v.co.z < -0.001], context="VERTS")
        vs = [v for v in vs if v.is_valid]
        for v in vs:
            v.co.z *= squash
        bmesh.ops.translate(bm, verts=vs, vec=Vector(center))
        self._place(bm, vs, origin, rot)
        return vs

    def torus(self, mat, origin, rot, center, major, minor, seg=16, ring=6):
        bm = self.bm(mat)
        before = set(bm.verts)
        circle = bmesh.ops.create_circle(bm, cap_ends=False, radius=minor, segments=ring)["verts"]
        bmesh.ops.rotate(bm, verts=circle, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, "X"))
        bmesh.ops.translate(bm, verts=circle, vec=Vector((major, 0, 0)))
        edges = list({e for v in circle for e in v.link_edges})
        bmesh.ops.spin(bm, geom=circle + edges, cent=(0, 0, 0), axis=(0, 0, 1), angle=math.tau, steps=seg, use_duplicate=False)
        vs = [v for v in bm.verts if v not in before]
        bmesh.ops.remove_doubles(bm, verts=vs, dist=1e-4)
        vs = [v for v in bm.verts if v not in before]
        bmesh.ops.translate(bm, verts=vs, vec=Vector(center))
        self._place(bm, vs, origin, rot)
        return vs

    def sheet(self, mat, origin, rot, corners, nu=3, nv=2, sag=0.0, inward=(0, 0, 0)):
        """A fabric panel over four corners (bilinear, a b c d round the edge), drawn in by `sag`
        towards `inward` in the middle, the way cloth gives between its poles."""
        bm = self.bm(mat)
        a, b, c, d = (Vector(p) for p in corners)
        pull = Vector(inward)
        grid = []
        for j in range(nv + 1):
            v = j / nv
            row = []
            for i in range(nu + 1):
                u = i / nu
                q = a.lerp(b, u).lerp(d.lerp(c, u), v) + pull * (sag * math.sin(math.pi * u) * math.sin(math.pi * v))
                row.append(bm.verts.new(q))
            grid.append(row)
        for j in range(nv):
            for i in range(nu):
                bm.faces.new((grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]))
        vs = [v for row in grid for v in row]
        self._place(bm, vs, origin, rot)
        return vs

    def fly(self, mat, origin, rot, r, squash=0.72, hem=0.06, sag=0.08, around=28, rings=7):
        """A dome tent's fly over two crossing poles: between the poles the fabric is drawn in,
        most at mid height, and it ends in a hem above the ground."""
        bm = self.bm(mat)
        grid = []
        for j in range(rings):
            theta = j / rings * (math.pi / 2)
            row = []
            for i in range(around):
                phi = i / around * math.tau
                pull = sag * math.cos(2 * phi) ** 2 * math.sin(2 * theta)
                rad = r * (1.0 - pull)
                row.append(bm.verts.new((math.cos(theta) * math.cos(phi) * rad, math.cos(theta) * math.sin(phi) * rad, hem + math.sin(theta) * r * squash)))
            grid.append(row)
        apex = bm.verts.new((0, 0, hem + r * squash))
        for j in range(rings - 1):
            for i in range(around):
                n = (i + 1) % around
                bm.faces.new((grid[j][i], grid[j][n], grid[j + 1][n], grid[j + 1][i]))
        for i in range(around):
            bm.faces.new((grid[-1][i], grid[-1][(i + 1) % around], apex))
        vs = [v for row in grid for v in row] + [apex]
        self._place(bm, vs, origin, rot)
        return vs

    def finish(self, parent=None, smooth=()):
        for mat, bm in self.meshes.items():
            obj = pw.bm_object(f"{self.prefix}_{mat}", bm, M[mat], smooth=mat in smooth)
            if parent:
                obj.parent = parent
        self.meshes = {}


props = Kit("props")


def at(site, dx, dy):
    """World point on the ground at a camp-local offset (+Y points up the trail)."""
    sx, sy = SITES[site]
    v = Matrix.Rotation(frame_rot(site), 3, "Z") @ Vector((dx, dy, 0))
    x, y = sx + v.x, sy + v.y
    return Vector((x, y, surface(x, y)))


def frame_rot(site):
    names = [r[0] for r in ROUTE]
    i = names.index(site)
    a = ROUTE[i]
    b = ROUTE[i + 1] if i < len(ROUTE) - 1 else ROUTE[i - 1]
    sign = 1 if i < len(ROUTE) - 1 else -1
    d = Vector((b[1] - a[1], b[2] - a[2])) * sign
    return math.atan2(-d.x, d.y)


# --- prop builders (local space: +Y forward, origin on the ground) ---------------------------


def guy_line(origin, rot, anchor, stake):
    """A guy line with its tensioner and a peg."""
    k = props
    anchor, stake = Vector(anchor), Vector(stake)
    k.cyl("rope", origin, rot, anchor, stake, 0.007, seg=4)
    k.box("metal", origin, rot, anchor.lerp(stake, 0.72), (0.035, 0.035, 0.018))
    k.cyl("metal", origin, rot, (stake.x, stake.y, -0.05), (stake.x, stake.y, 0.08), 0.014, seg=4)
    k.box("metal", origin, rot, (stake.x, stake.y, 0.085), (0.05, 0.016, 0.012))


def boots(origin, rot):
    """A pair of hiking boots left by a tent door."""
    k = props
    for side in (-1, 1):
        x = side * 0.09
        k.box("wood_dark", origin, rot, (x, 0.02, 0.025), (0.1, 0.28, 0.05))
        k.box("wood", origin, rot, (x, -0.03, 0.12), (0.095, 0.15, 0.16))
        k.box("fabric_red", origin, rot, (x, -0.03, 0.205), (0.1, 0.155, 0.02))
        k.box("fabric_dark", origin, rot, (x, 0.07, 0.09), (0.06, 0.08, 0.05))


def stove(origin, rot):
    """A camping stove with a pot and a mug beside it."""
    k = props
    k.cyl("metal", origin, rot, (0, 0, 0), (0, 0, 0.1), 0.07, seg=10)
    for a in (0.0, 2.1, 4.2):
        k.box("metal_dark", origin, rot, (math.cos(a) * 0.08, math.sin(a) * 0.08, 0.11), (0.06, 0.012, 0.012))
    k.cyl("metal_dark", origin, rot, (0, 0, 0.12), (0, 0, 0.26), 0.1, seg=12)
    k.cyl("metal", origin, rot, (0, 0, 0.26), (0, 0, 0.275), 0.105, seg=12)
    k.cyl("fabric_blue", origin, rot, (0.24, 0.05, 0), (0.24, 0.05, 0.09), 0.04, seg=8)


def a_frame_tent(origin, rot, color, size=1.0):
    """Ridge tent. The fly sags a little between its poles and stops above a dark bathtub floor;
    the door is rolled back on a mat and a sleeping bag, with seams, a vent, guy lines,
    tensioners, pegs and a pair of boots at the door."""
    w, l, h = 1.25 * size, 1.9 * size, 1.0 * size
    k = props
    k.box("groundsheet", origin, rot, (0, 0, 0.01), (w + 0.16, l + 0.2, 0.02))
    tub = 0.1 * size
    # inner tent: bathtub floor walls and the sleeping things seen through the door
    for side in (-1, 1):
        k.box("groundsheet", origin, rot, (side * (w / 2 - 0.05), 0, tub / 2 + 0.02), (0.03, l - 0.1, tub))
    k.box("fabric_blue", origin, rot, (0.05, -l / 2 + 0.55, 0.035), (0.5 * size, 0.95 * size, 0.025))
    k.cyl("fabric_red", origin, rot, (-0.15 * size, -l / 2 + 0.2, 0.1), (-0.15 * size, -l / 2 + 0.95 * size, 0.1), 0.09 * size, seg=8)
    over = 0.12 * size
    # fly: two panels from a hem above the ground to the ridge, drawn in between the poles
    for side in (-1, 1):
        inward = Vector((-side * h, 0, -w / 2)).normalized()
        corners = [(side * (w / 2 + 0.05), -l / 2, tub * 0.7), (side * (w / 2 + 0.05), l / 2, tub * 0.7), (0, l / 2 + over, h), (0, -l / 2 - over, h)]
        k.sheet(color, origin, rot, corners, nu=4, nv=2, sag=0.05 * size, inward=inward)
        # a seam down the middle of each panel
        k.cyl("fabric_dark", origin, rot, (side * (w / 2 + 0.05), 0, tub * 0.7), (0, 0, h), 0.006, seg=3)
    k.cyl("fabric_dark", origin, rot, (0, -l / 2 - over, h + 0.006), (0, l / 2 + over, h + 0.006), 0.012, seg=4)
    # back wall with a vent
    k.poly(color, origin, rot, [(w / 2, l / 2 - 0.02, tub * 0.7), (-w / 2, l / 2 - 0.02, tub * 0.7), (0, l / 2 - 0.02, h)])
    k.poly("fabric_dark", origin, rot, [(0.1, l / 2 + 0.0, h * 0.62), (-0.1, l / 2 + 0.0, h * 0.62), (0, l / 2 + 0.0, h * 0.82)])
    # front: open door, panels either side, flaps tied back and the door rolled up beside it
    door = 0.34 * size
    k.poly("fabric_dark", origin, rot, [(-door, -l / 2 + 0.02, 0.02), (door, -l / 2 + 0.02, 0.02), (0, -l / 2 + 0.02, h * 0.82)])
    k.poly(color, origin, rot, [(-w / 2, -l / 2, tub * 0.7), (-door, -l / 2, 0.02), (0, -l / 2, h * 0.82), (0, -l / 2, h)][::-1])
    k.poly(color, origin, rot, [(door, -l / 2, 0.02), (w / 2, -l / 2, tub * 0.7), (0, -l / 2, h), (0, -l / 2, h * 0.82)][::-1])
    for side in (-1, 1):
        k.poly(color, origin, rot, [(side * door, -l / 2 - 0.01, 0.02), (side * (door + 0.22), -l / 2 - 0.2, 0.05), (side * 0.06, -l / 2 - 0.02, h * 0.7)][::side])
    k.cyl(color, origin, rot, (door * 0.95, -l / 2 - 0.05, 0.06), (0.08, -l / 2 - 0.05, h * 0.74), 0.035 * size, seg=6)
    k.cyl("fabric_dark", origin, rot, (0, -l / 2 - 0.012, h * 0.82), (0, -l / 2 - 0.012, h * 0.98), 0.008, seg=3)
    # ridge poles, guy lines with tensioners and pegs
    for end in (-1, 1):
        top = (0, end * (l / 2 + over), h)
        k.cyl("wood_dark", origin, rot, (0, end * (l / 2 + over * 0.6), 0), (0, end * (l / 2 + over * 0.6), h + 0.05), 0.02, seg=5)
        guy_line(origin, rot, top, (0, end * (l / 2 + 0.75 * size), 0.02))
    for side in (-1, 1):
        for end in (-0.3, 0.3):
            guy_line(origin, rot, (side * w * 0.26, end * l, h * 0.5), (side * (w / 2 + 0.55 * size), end * l * 1.15, 0.02))
    boots(origin + Matrix.Rotation(rot, 3, "Z") @ Vector((-0.42 * size, -l / 2 - 0.42, 0)), rot + 0.25)


def dome_tent(origin, rot, color, r=0.85):
    """Dome tent: the fly drawn in between two crossing poles over a dark bathtub floor, a vent
    hood on top, a vestibule with the inner door rolled back, guy lines, tensioners and boots."""
    k = props
    squash, hem = 0.72, 0.07
    k.box("groundsheet", origin, rot, (0, 0, 0.01), (2 * r + 0.08, 2 * r + 0.08, 0.02))
    k.cyl("groundsheet", origin, rot, (0, 0, 0.02), (0, 0, 0.1), r * 0.97, r * 0.95, seg=16)
    k.fly(color, origin, rot, r, squash=squash, hem=hem, sag=0.085)
    # crossing poles riding on the fly
    for angle in (math.pi / 4, -math.pi / 4):
        pts = []
        for s_ in range(11):
            t = s_ / 10 * math.pi
            pts.append(Matrix.Rotation(angle, 3, "Z") @ Vector((math.cos(t) * r * 1.012, 0, hem + math.sin(t) * r * squash * 1.012)))
        for a, b in zip(pts, pts[1:]):
            k.cyl("metal_dark", origin, rot, a, b, 0.016, seg=4)
    # vent hood at the crown
    top = hem + r * squash
    k.dome(color, origin, rot, (0.0, 0.12, top - 0.03), 0.22, squash=0.55, seg=10)
    k.box("fabric_dark", origin, rot, (0.0, 0.31, top - 0.02), (0.22, 0.02, 0.06))
    # vestibule over the door: two drawn-in panels to a peak, the inner door rolled back
    v = 0.58 * r
    peak = (0, -r - 0.48, 0.03)
    crown = (0, -r * 0.6, r * 0.62)
    for side in (-1, 1):
        corners = [(side * v, -r * 0.55, 0.05), peak, peak, crown]
        k.sheet(color, origin, rot, [corners[0], corners[1], corners[3], corners[3]], nu=2, nv=2, sag=0.04, inward=(side * -0.6, 0.6, -0.2))
    k.poly("fabric_dark", origin, rot, [(-v * 0.55, -r * 0.6, 0.03), (v * 0.55, -r * 0.6, 0.03), (0, -r * 0.64, r * 0.5)])
    k.cyl(color, origin, rot, (v * 0.5, -r * 0.66, 0.05), (0.08, -r * 0.7, r * 0.46), 0.03, seg=6)
    for corner in (math.pi / 4, 3 * math.pi / 4, -math.pi / 4, -3 * math.pi / 4):
        d = Vector((math.cos(corner), math.sin(corner), 0))
        anchor = d * (r * 0.72) + Vector((0, 0, hem + r * squash * 0.68))
        guy_line(origin, rot, anchor, d * (r + 0.55) + Vector((0, 0, 0.02)))
    boots(origin + Matrix.Rotation(rot, 3, "Z") @ Vector((-0.45, -r - 0.62, 0)), rot - 0.2)


def backpack(origin, rot, color):
    k = props
    k.box(color, origin, rot, (0, 0, 0.26), (0.34, 0.22, 0.48))
    k.box(color, origin, rot, (0, 0.01, 0.53), (0.36, 0.25, 0.1))
    k.box("fabric_dark", origin, rot, (0, -0.13, 0.2), (0.24, 0.06, 0.2))
    k.cyl("fabric_blue", origin, rot, (-0.22, 0.02, 0.62), (0.22, 0.02, 0.62), 0.07, seg=8)
    for side in (-1, 1):
        k.box("fabric_dark", origin, rot, (side * 0.08, 0.115, 0.3), (0.04, 0.02, 0.38))


def campfire(origin, rot):
    k = props
    for s in range(10):
        a = s / 10 * math.tau
        k.ico("stone", origin, rot, (math.cos(a) * 0.42, math.sin(a) * 0.42, 0.05), 0.1, (1.2, 1.0, 0.7))
    for s in range(5):
        a = s / 5 * math.tau + 0.3
        k.cyl("wood_dark", origin, rot, (math.cos(a) * 0.32, math.sin(a) * 0.32, 0.02), (0, 0, 0.42), 0.035, seg=5)
    k.ico("ember", origin, rot, (0, 0, 0.04), 0.2, (1.0, 1.0, 0.25))
    bm = bmesh.new()
    pw.add_cone(bm, (0, 0, 0), 0.2, 0.0, 0.55, segments=6)
    fire = pw.bm_object("fire", bm, M["glow_fire"])
    fire.location = origin + Vector((0, 0, 0.04))
    pw.empty(f"smoke_fire", origin + Vector((0, 0, 0.6)))


def log_seat(origin, rot, length=1.2):
    props.cyl("wood", origin, rot, (-length / 2, 0, 0.13), (length / 2, 0, 0.13), 0.13, seg=7)
    for end in (-1, 1):
        props.cyl("wood_light", origin, rot, (end * length / 2, 0, 0.13), (end * (length / 2 + 0.01), 0, 0.13), 0.12, seg=7)


def cooking_tripod(origin, rot):
    k = props
    for s in range(3):
        a = s / 3 * math.tau
        k.cyl("wood_dark", origin, rot, (math.cos(a) * 0.38, math.sin(a) * 0.38, 0), (0, 0, 0.82), 0.022, seg=4)
    k.cyl("metal_dark", origin, rot, (0, 0, 0.8), (0, 0, 0.42), 0.006, seg=4)
    k.cyl("metal_dark", origin, rot, (0, 0, 0.28), (0, 0, 0.44), 0.13, 0.15, seg=10)


def lantern_post(origin, rot):
    k = props
    k.box("wood_dark", origin, rot, (0, 0, 0.65), (0.07, 0.07, 1.3))
    k.box("wood_dark", origin, rot, (0.14, 0, 1.25), (0.32, 0.05, 0.05))
    k.box("metal_dark", origin, rot, (0.26, 0, 1.07), (0.14, 0.14, 0.03))
    k.box("lantern", origin, rot, (0.26, 0, 1.0), (0.1, 0.1, 0.13))
    k.box("metal_dark", origin, rot, (0.26, 0, 0.93), (0.13, 0.13, 0.025))


def signpost(origin, rot, arms):
    """Yellow hiking signpost; arms: list of (local angle, height)."""
    k = props
    k.cyl("metal", origin, rot, (0, 0, 0), (0, 0, 2.0), 0.04, seg=8)
    k.box("white", origin, rot, (0, 0, 2.02), (0.1, 0.1, 0.04))
    k.box("marker_red", origin, rot, (0, 0, 1.97), (0.1, 0.1, 0.05))
    for angle, z in arms:
        k.box("sign", origin, rot + angle, (0.36, 0, z), (0.62, 0.035, 0.15))
        k.poly("sign", origin, rot + angle, [(0.67, -0.018, z - 0.075), (0.67, -0.018, z + 0.075), (0.79, -0.018, z)])
        k.poly("sign", origin, rot + angle, [(0.67, 0.018, z + 0.075), (0.67, 0.018, z - 0.075), (0.79, 0.018, z)])
        k.box("fabric_dark", origin, rot + angle, (0.3, -0.019, z), (0.38, 0.004, 0.035))


def map_board(origin, rot):
    k = props
    for side in (-1, 1):
        k.box("wood_dark", origin, rot, (side * 0.55, 0, 0.7), (0.07, 0.07, 1.4))
    k.box("wood", origin, rot, (0, 0, 1.0), (1.2, 0.05, 0.75))
    k.box("fabric_green", origin, rot, (0, -0.03, 1.0), (1.0, 0.01, 0.6))
    k.box("sign", origin, rot, (0.18, -0.04, 1.05), (0.18, 0.01, 0.12))
    k.box("roof", origin, rot, (0, 0, 1.5), (1.35, 0.4, 0.05), tilt=("X", 0.25))


def bench(origin, rot, length=1.3):
    k = props
    k.box("wood", origin, rot, (0, 0, 0.42), (length, 0.36, 0.06))
    k.box("wood", origin, rot, (0, 0.17, 0.72), (length, 0.05, 0.22))
    for side in (-1, 1):
        k.box("wood_dark", origin, rot, (side * (length / 2 - 0.12), 0, 0.2), (0.07, 0.32, 0.4))
        k.box("wood_dark", origin, rot, (side * (length / 2 - 0.12), 0.17, 0.55), (0.07, 0.05, 0.5))


def picnic_table(origin, rot):
    k = props
    k.box("wood", origin, rot, (0, 0, 0.75), (1.6, 0.72, 0.06))
    for side in (-1, 1):
        k.box("wood", origin, rot, (0, side * 0.62, 0.44), (1.6, 0.26, 0.05))
        for end in (-1, 1):
            k.box("wood_dark", origin, rot, (end * 0.62, side * 0.22, 0.37), (0.07, 0.07, 0.75), tilt=("X", -side * 0.45))


def crates(origin, rot):
    k = props
    for (x, y, z, s) in ((0, 0, 0.22, 0.44), (0.5, 0.05, 0.19, 0.38), (0.22, 0.02, 0.62, 0.36)):
        k.box("wood_light", origin, rot, (x, y, z), (s, s * 0.9, s))
        k.box("wood_dark", origin, rot, (x, y - s * 0.46, z), (s * 1.02, 0.02, s * 0.12))


def firewood(origin, rot):
    k = props
    for row in range(3):
        for i in range(5 - row):
            x = -0.36 + i * 0.18 + row * 0.09
            k.cyl("wood", origin, rot, (x, -0.35, 0.09 + row * 0.15), (x, 0.35, 0.09 + row * 0.15), 0.075, seg=6)
    for side in (-1, 1):
        k.cyl("wood_dark", origin, rot, (side * 0.52, 0, 0), (side * 0.52, 0, 0.6), 0.03, seg=4)


def stone_wall(origin, rot, radius=1.6, start=-1.9, end=1.9, rows=2, mat="stone"):
    k = props
    count = int((end - start) * radius / 0.32)
    for row in range(rows):
        for s in range(count + 1):
            a = start + (end - start) * s / max(1, count) + (0.5 / count if row % 2 else 0)
            r = radius + rng.uniform(-0.05, 0.05)
            k.ico(mat, origin, rot, (math.cos(a) * r, math.sin(a) * r, 0.16 + row * 0.26), 0.2, (1.1, 0.75, 0.6))


def ice_axe(origin, rot, lean=0.12):
    k = props
    top = (0, math.sin(lean) * 0.7, math.cos(lean) * 0.7)
    k.cyl("metal", origin, rot, (0, 0, -0.15), top, 0.022, seg=6)
    k.box("metal_dark", origin, rot, (top[0], top[1], top[2] + 0.02), (0.36, 0.04, 0.05))
    k.box("fabric_red", origin, rot, (0, top[1] * 0.6, top[2] * 0.6), (0.05, 0.05, 0.16))


def rope_coil(origin, rot):
    for i in range(3):
        props.torus("fabric_red" if i % 2 else "rope", origin, rot, (0, 0, 0.03 + i * 0.035), 0.24 - i * 0.015, 0.025)


def prayer_flags(a, b, count=12, sag=0.35):
    """String of prayer flags between two world points."""
    k = props
    a, b = Vector(a), Vector(b)
    pts = []
    for s in range(count + 1):
        t = s / count
        p = a.lerp(b, t)
        p.z -= math.sin(t * math.pi) * sag
        pts.append(p)
    for p, q in zip(pts, pts[1:]):
        k.cyl("rope", Vector((0, 0, 0)), 0.0, p, q, 0.008, seg=4)
    side = (b - a).normalized()
    for s, p in enumerate(pts[1:-1], start=1):
        mat = f"prayer_{s % 5}"
        w = side * 0.12
        k.poly(mat, Vector((0, 0, 0)), 0.0, [p - w, p + w, p + w + Vector((0, 0, -0.3)), p - w + Vector((0, 0, -0.3))])


def flag_pole(origin, rot, mat="marker_red", height=2.4):
    k = props
    k.cyl("metal", origin, rot, (0, 0, 0), (0, 0, height), 0.03, seg=6)
    k.poly(mat, origin, rot, [(0.02, 0, height - 0.02), (0.02, 0, height - 0.42), (0.68, 0, height - 0.2)])
    k.poly(mat, origin, rot, [(0.02, 0, height - 0.42), (0.02, 0, height - 0.02), (0.68, 0, height - 0.2)])


def cairn(origin, rot, size=1.0):
    for i, (r, z) in enumerate(((0.36, 0.16), (0.28, 0.44), (0.21, 0.67), (0.15, 0.85), (0.1, 0.98))):
        props.ico("stone_light" if i % 2 else "stone", origin, rot, (rng.uniform(-0.04, 0.04), rng.uniform(-0.04, 0.04), z * size), r * size, (1.0, 0.9, 0.62))


def hut(origin, rot):
    """Mountain refuge as a log cabin. Logs cross at the corners, cut round the door and windows
    with pale ends, over a base of facing stones. Above them sits a shingled roof with fascia
    boards and a stone chimney in courses. It has windows with frames, mullions, shutters and
    flower boxes, a plank door with a sign and a lantern, a porch with balusters and steps, and
    a gutter that runs to a rain barrel."""
    k = props
    W, L, H = 3.6, 2.8, 1.9
    base = 0.5
    top = base + H
    ridge = top + 1.2
    pitch = math.atan2(1.2, L / 2)
    R = Matrix.Rotation(rot, 3, "Z")

    # base: a mortar plinth faced with stones
    k.box("stone", origin, rot, (0, 0, base / 2), (W + 0.2, L + 0.2, base))
    for row in range(2):
        z = 0.12 + row * 0.24
        for wall, (length, fixed, along_x) in enumerate(((W + 0.3, L / 2 + 0.11, True), (W + 0.3, -L / 2 - 0.11, True), (L + 0.3, W / 2 + 0.11, False), (L + 0.3, -W / 2 - 0.11, False))):
            count = int(length / 0.36)
            for i in range(count):
                t = -length / 2 + (i + 0.5 + (0.5 if row % 2 else 0.0)) * length / count
                if abs(t) > length / 2 - 0.05:
                    continue
                c = (t, fixed, z) if along_x else (fixed, t, z)
                k.ico("stone_light" if (i + row + wall) % 3 == 0 else "stone", origin, rot, c, 0.17, (1.25, 0.75, 0.7) if along_x else (0.75, 1.25, 0.7))

    # log walls with their openings (x or y range, z range) per wall
    door = (-0.98, -0.22, base, base + 1.62)
    front_windows = [(0.45, 0.95, 1.3, 1.85), (1.1, 1.6, 1.3, 1.85)]
    side_windows = [(-0.8, -0.3, 1.3, 1.85), (0.3, 0.8, 1.3, 1.85)]
    walls = (
        ("front", True, -L / 2, [door] + front_windows),
        ("back", True, L / 2, []),
        ("right", False, W / 2, side_windows),
        ("left", False, -W / 2, []),
    )
    k.box("wood_dark", origin, rot, (0, 0, base + H / 2), (W - 0.16, L - 0.16, H))
    logs = 8
    radius = 0.12
    for row in range(logs):
        z = base + radius + row * (H - 2 * radius) / (logs - 1)
        for name, along_x, fixed, openings in walls:
            length = W if along_x else L
            # front and back logs run long on even rows, the side logs on odd rows
            long_row = (row % 2 == 0) == along_x
            reach = length / 2 + (0.24 if long_row else 0.1)
            cuts = sorted((o[0], o[1]) for o in openings if o[2] - radius < z < o[3] + radius)
            spans, start = [], -reach
            for a, b in cuts:
                if a > start:
                    spans.append((start, a))
                start = max(start, b)
            if start < reach:
                spans.append((start, reach))
            for a, b in spans:
                pa = (a, fixed, z) if along_x else (fixed, a, z)
                pb = (b, fixed, z) if along_x else (fixed, b, z)
                k.cyl("wood" if row % 3 else "wood_light", origin, rot, pa, pb, radius, seg=7)
            if long_row:
                for end in (-reach, reach):
                    e = (end, fixed, z) if along_x else (fixed, end, z)
                    inside = Vector(e) - (Vector((math.copysign(0.012, end), 0, 0)) if along_x else Vector((0, math.copysign(0.012, end), 0)))
                    k.cyl("wood_light", origin, rot, inside, e, radius * 0.92, seg=7)

    # gables: vertical boards, a round vent
    for side in (-1, 1):
        for b_ in range(9):
            y = -L / 2 + (b_ + 0.5) * L / 9
            gable_h = (1.0 - abs(y) / (L / 2)) * 1.2
            if gable_h < 0.05:
                continue
            k.box("wood_light", origin, rot, (side * (W / 2 + 0.04), y, top + gable_h / 2), (0.04, L / 9 - 0.015, gable_h))
        k.cyl("wood_dark", origin, rot, (side * (W / 2 + 0.06), 0, top + 0.6), (side * (W / 2 + 0.08), 0, top + 0.6), 0.14, seg=10)
        k.cyl("fabric_dark", origin, rot, (side * (W / 2 + 0.07), 0, top + 0.6), (side * (W / 2 + 0.09), 0, top + 0.6), 0.1, seg=10)

    # roof: underlay, shingle rows in two shades, fascia and barge boards, ridge cap
    run = L / 2 + 0.38
    slope = run / math.cos(pitch)
    rows = 7
    for side in (-1, 1):
        normal = Vector((0, side * math.sin(pitch), math.cos(pitch)))
        k.box("roof", origin, rot, (0, side * (L / 4 + 0.08), top + 0.62), (W + 0.6, L / 2 / math.cos(pitch) + 0.5, 0.1), tilt=("X", -side * pitch))
        for i in range(rows):
            along = run * (1.0 - (i + 0.5) / rows)
            centre = Vector((0, side * along, ridge - along * math.tan(pitch))) + normal * (0.12 + 0.015 * (i % 2))
            k.box("roof_dark" if i % 2 else "roof", origin, rot, tuple(centre), (W + 0.62, slope / rows * 1.18, 0.05), tilt=("X", -side * pitch))
        eave = Vector((0, side * run, ridge - run * math.tan(pitch))) + normal * 0.04
        k.box("wood_dark", origin, rot, tuple(eave - Vector((0, 0, 0.06))), (W + 0.66, 0.05, 0.16))
        for end in (-1, 1):
            mid = Vector((end * (W / 2 + 0.32), side * run / 2, ridge - run / 2 * math.tan(pitch))) + normal * 0.08
            k.box("wood_dark", origin, rot, tuple(mid), (0.05, slope + 0.05, 0.16), tilt=("X", -side * pitch))
        # gutter along the eave
        k.box("metal_dark", origin, rot, tuple(eave + Vector((0, side * 0.08, -0.16))), (W + 0.5, 0.1, 0.07))
    k.box("wood_dark", origin, rot, (0, 0, ridge + 0.13), (W + 0.66, 0.2, 0.1))

    # chimney in courses of stone, with a cap and a flue
    cx, cy = W * 0.25, L * 0.15
    for c in range(7):
        jitter = 0.03 * ((c * 7) % 3 - 1)
        k.box("stone_light" if c % 2 else "stone", origin, rot, (cx + jitter, cy, ridge - 0.4 + c * 0.2), (0.5 + jitter, 0.5 - jitter, 0.21))
    k.box("stone", origin, rot, (cx, cy, ridge + 1.02), (0.62, 0.62, 0.07))
    k.cyl("metal_dark", origin, rot, (cx, cy, ridge + 1.05), (cx, cy, ridge + 1.3), 0.07, seg=8)
    pw.empty("smoke_hut", origin + R @ Vector((cx, cy, ridge + 1.36)))

    # door: planks with a Z brace, frame, handle, sign above and a lantern beside it
    dx = (door[0] + door[1]) / 2
    dw = door[1] - door[0]
    for p_ in range(3):
        k.box("wood_dark", origin, rot, (door[0] + dw * (p_ + 0.5) / 3, -L / 2 - 0.04, base + 0.8), (dw / 3 - 0.02, 0.05, 1.58))
    for z in (base + 0.35, base + 1.25):
        k.box("wood", origin, rot, (dx, -L / 2 - 0.075, z), (dw - 0.06, 0.03, 0.1))
    brace = math.atan2(0.9, dw - 0.1)
    k.box("wood", origin, rot, (dx, -L / 2 - 0.075, base + 0.8), (math.hypot(0.9, dw - 0.1), 0.03, 0.09), tilt=("Y", -brace))
    k.box("metal", origin, rot, (door[1] - 0.1, -L / 2 - 0.1, base + 0.85), (0.04, 0.04, 0.12))
    for x in (door[0] - 0.05, door[1] + 0.05):
        k.box("wood_light", origin, rot, (x, -L / 2 - 0.05, base + 0.82), (0.08, 0.07, 1.68))
    k.box("wood_light", origin, rot, (dx, -L / 2 - 0.05, base + 1.68), (dw + 0.18, 0.07, 0.08))
    k.box("wood_light", origin, rot, (dx, -L / 2 - 0.08, base + 1.86), (1.0, 0.04, 0.24))
    k.box("sign", origin, rot, (dx, -L / 2 - 0.1, base + 1.86), (0.86, 0.02, 0.15))
    for i in range(4):
        k.box("fabric_dark", origin, rot, (dx - 0.28 + i * 0.16, -L / 2 - 0.112, base + 1.86), (0.1, 0.006, 0.04))
    k.box("wood_dark", origin, rot, (door[0] - 0.32, -L / 2 - 0.12, base + 1.62), (0.05, 0.22, 0.05))
    k.box("metal_dark", origin, rot, (door[0] - 0.32, -L / 2 - 0.24, base + 1.58), (0.12, 0.12, 0.03))
    k.box("lantern", origin, rot, (door[0] - 0.32, -L / 2 - 0.24, base + 1.5), (0.09, 0.09, 0.12))
    k.box("metal_dark", origin, rot, (door[0] - 0.32, -L / 2 - 0.24, base + 1.43), (0.11, 0.11, 0.025))

    # windows: frame, mullions, glass, sill, open shutters and a flower box
    def window(centre, along_x, out):
        cx_, cz = centre
        frame = (0.56, 0.6)
        def place(u, depth, size):
            return ((cx_ + u, out + depth, cz), size) if along_x else ((out + depth, cx_ + u, cz), (size[1], size[0], size[2]))
        sign = math.copysign(1.0, out)
        c, sz = place(0, sign * 0.03, (frame[0] * 0.82, 0.03, frame[1] * 0.85))
        k.box("window", origin, rot, c, sz)
        for u, wsz in ((-frame[0] / 2, 0.06), (frame[0] / 2, 0.06)):
            c, sz = place(u, sign * 0.05, (wsz, 0.06, frame[1]))
            k.box("white", origin, rot, c, sz)
        for dz in (-frame[1] / 2, frame[1] / 2):
            c, sz = (((cx_, out + sign * 0.05, cz + dz), (frame[0], 0.06, 0.06)) if along_x else ((out + sign * 0.05, cx_, cz + dz), (0.06, frame[0], 0.06)))
            k.box("white", origin, rot, c, sz)
        c, sz = place(0, sign * 0.055, (0.035, 0.04, frame[1]))
        k.box("white", origin, rot, c, sz)
        c, sz = (((cx_, out + sign * 0.055, cz), (frame[0], 0.04, 0.035)) if along_x else ((out + sign * 0.055, cx_, cz), (0.04, frame[0], 0.035)))
        k.box("white", origin, rot, c, sz)
        for u in (-1, 1):
            c, sz = place(u * (frame[0] / 2 + 0.17), sign * 0.06, (0.28, 0.03, frame[1] * 0.95))
            k.box("shutter", origin, rot, c, sz)
            for slat in range(4):
                c, sz = (((cx_ + u * (frame[0] / 2 + 0.17), out + sign * 0.08, cz - 0.2 + slat * 0.13), (0.24, 0.01, 0.02)) if along_x else ((out + sign * 0.08, cx_ + u * (frame[0] / 2 + 0.17), cz - 0.2 + slat * 0.13), (0.01, 0.24, 0.02)))
                k.box("roof_dark", origin, rot, c, sz)
        box_c = ((cx_, out + sign * 0.14, cz - frame[1] / 2 - 0.1) if along_x else (out + sign * 0.14, cx_, cz - frame[1] / 2 - 0.1))
        k.box("wood_dark", origin, rot, box_c, (frame[0] + 0.1, 0.18, 0.14) if along_x else (0.18, frame[0] + 0.1, 0.14))
        for f in range(5):
            u = -0.24 + f * 0.12
            fc = ((cx_ + u, out + sign * 0.14, cz - frame[1] / 2 - 0.0) if along_x else (out + sign * 0.14, cx_ + u, cz - frame[1] / 2 - 0.0))
            k.ico("bush", origin, rot, fc, 0.07, (1.0, 1.0, 0.8))
            k.ico("flower_pink" if f % 2 else "flower_yellow", origin, rot, (fc[0], fc[1], fc[2] + 0.07), 0.035)

    for a, b, z0, z1 in front_windows:
        window(((a + b) / 2, (z0 + z1) / 2), True, -L / 2 - 0.12)
    for a, b, z0, z1 in side_windows:
        window(((a + b) / 2, (z0 + z1) / 2), False, W / 2 + 0.12)

    # porch: boards, steps, posts with braces, balusters, a shingled roof
    py = -L / 2 - 0.68
    for b_ in range(7):
        k.box("wood_light" if b_ % 2 else "wood", origin, rot, (0, py - 0.55 + b_ * 0.16 + 0.08, 0.47), (W, 0.145, 0.06))
    k.box("wood_dark", origin, rot, (0, py, 0.38), (W, 1.2, 0.12))
    for step in range(2):
        k.box("wood", origin, rot, (dx, py - 0.68 - step * 0.26, 0.31 - step * 0.15), (1.1, 0.28, 0.07))
        k.box("wood_dark", origin, rot, (dx, py - 0.68 - step * 0.26, 0.15 - step * 0.08), (1.1, 0.24, 0.3 - step * 0.15))
    for x in (-W / 2 + 0.1, W / 2 - 0.1):
        k.box("wood_dark", origin, rot, (x, py - 0.52, 1.18), (0.1, 0.1, 1.42))
        k.box("wood", origin, rot, (x, py - 0.35, 1.72), (0.06, 0.42, 0.06), tilt=("X", 0.7))
        for b_ in range(5):
            k.box("wood_light", origin, rot, (x, py - 0.4 + b_ * 0.2, 0.75), (0.04, 0.04, 0.5))
        k.box("wood", origin, rot, (x, py, 1.0), (0.08, 1.1, 0.06))
    k.box("wood_dark", origin, rot, (0, py - 0.52, 1.9), (W + 0.1, 0.12, 0.12))
    k.box("roof", origin, rot, (0, py + 0.02, 2.02), (W + 0.3, 1.5, 0.07), tilt=("X", 0.22))
    for i in range(3):
        k.box("roof_dark" if i % 2 else "roof", origin, rot, (0, py - 0.5 + i * 0.5, 1.94 + i * 0.11), (W + 0.32, 0.56, 0.04), tilt=("X", 0.22))
    bench(origin + R @ Vector((0.9, py + 0.1, 0.5)), rot + math.pi)

    # rain barrel under the gutter's downspout
    bx, by = W / 2 + 0.35, -L / 2 + 0.25
    k.cyl("metal_dark", origin, rot, (W / 2 + 0.3, -L / 2 - 0.4, top + 0.05), (bx, by, 1.0), 0.04, seg=6)
    k.cyl("wood", origin, rot, (bx, by, 0.0), (bx, by, 0.8), 0.28, 0.3, seg=12)
    for z in (0.18, 0.62):
        k.torus("metal_dark", origin, rot, (bx, by, z), 0.3, 0.02, seg=16, ring=4)
    k.box("solar", origin, rot, (-W * 0.2, L / 4 + 0.15, top + 0.82), (1.1, 0.8, 0.04), tilt=("X", -pitch))


def telescope(origin, rot):
    k = props
    for s in range(3):
        a = s / 3 * math.tau
        k.cyl("metal_dark", origin, rot, (math.cos(a) * 0.32, math.sin(a) * 0.32, 0), (0, 0, 1.05), 0.02, seg=4)
    k.cyl("white", origin, rot, (0, -0.35, 1.0), (0, 0.45, 1.25), 0.07, 0.09, seg=10)
    k.cyl("metal_dark", origin, rot, (0, -0.42, 0.98), (0, -0.35, 1.0), 0.04, seg=8)


def railing(points, side_offset=None):
    """Wooden posts with a rope between their tops, along world points."""
    k = props
    tops = []
    for p in points:
        base = Vector((p.x, p.y, surface(p.x, p.y)))
        top = base + Vector((0, 0, 0.95))
        k.cyl("wood_dark", Vector((0, 0, 0)), 0.0, base + Vector((0, 0, -0.2)), top, 0.035, seg=5)
        tops.append(top)
    for a, b in zip(tops, tops[1:]):
        mid = (a + b) / 2 - Vector((0, 0, 0.08))
        k.cyl("rope", Vector((0, 0, 0)), 0.0, a, mid, 0.012, seg=4)
        k.cyl("rope", Vector((0, 0, 0)), 0.0, mid, b, 0.012, seg=4)


def solar_stand(origin, rot):
    k = props
    k.box("metal_dark", origin, rot, (0, 0, 0.35), (0.05, 0.05, 0.7))
    k.box("solar", origin, rot, (0, 0, 0.75), (0.9, 0.6, 0.03), tilt=("X", 0.6))


def radio_mast(origin, rot):
    k = props
    k.cyl("metal", origin, rot, (0, 0, 0), (0, 0, 3.2), 0.04, seg=6)
    for z in (1.6, 2.4, 3.0):
        k.cyl("metal", origin, rot, (-0.3, 0, z), (0.3, 0, z), 0.012, seg=4)
    for a in (0, 2.1, 4.2):
        k.cyl("rope", origin, rot, (0, 0, 2.6), (math.cos(a) * 1.4, math.sin(a) * 1.4, 0), 0.006, seg=4)
    k.ico("beacon", origin, rot, (0, 0, 3.25), 0.07)


# --- the trail ------------------------------------------------------------------------------
dense = catmull([(x, y, 0.0) for _, x, y, _ in ROUTE], 200)
lengths = [0.0]
for a, b in zip(dense, dense[1:]):
    lengths.append(lengths[-1] + (b.xy - a.xy).length)
total = lengths[-1]
SPACING = 0.32
samples = []
cursor = 0
for s in range(int(total / SPACING) + 1):
    target = s * SPACING
    while cursor < len(lengths) - 2 and lengths[cursor + 1] < target:
        cursor += 1
    span = max(1e-6, lengths[cursor + 1] - lengths[cursor])
    t = (target - lengths[cursor]) / span
    samples.append(dense[cursor].lerp(dense[cursor + 1], min(1.0, t)).xy)

# The cross-section: soft verges that fade into the ground, a slightly raised edge where boots
# push the soil aside and a worn, sunken middle. The width breathes a little along the way.
ACROSS = (-1.32, -1.0, -0.62, -0.22, 0.22, 0.62, 1.0, 1.32)
LIFT = {-1.32: 0.02, -1.0: 0.045, -0.62: 0.032, -0.22: 0.025, 0.22: 0.025, 0.62: 0.032, 1.0: 0.045, 1.32: 0.02}
trail_rng = random.Random(f"{args.seed}-trail")
tv, tf, tc = [], [], []
rows = []
for k_, p in enumerate(samples):
    nxt = samples[min(k_ + 1, len(samples) - 1)]
    prv = samples[max(k_ - 1, 0)]
    tangent = (nxt - prv).normalized()
    side = Vector((-tangent.y, tangent.x))
    centre_z = surface(p.x, p.y)
    gravel_w = pw.smoothstep(40.0, 56.0, centre_z)
    snow_w = pw.smoothstep(SNOWLINE - 4.0, SNOWLINE + 2.0, centre_z)
    path = C["earth"].lerp(C["gravel"], gravel_w).lerp(C["packed_snow"], snow_w)
    worn = C["earth_worn"].lerp(C["gravel_worn"], gravel_w).lerp(C["snow"], snow_w)
    wear = 0.85 + 0.15 * noise.noise(Vector((p.x * 0.6, p.y * 0.6, 3.0)))
    half = TRAIL_HALF * (1.0 + 0.16 * noise.noise(Vector((k_ * SPACING * 0.09, 2.4, 7.7))))
    row = []
    for a in ACROSS:
        q = p + side * (a * half)
        z = surface(q.x, q.y) + LIFT[a]
        ground = terrain_color(q.x, q.y)
        if abs(a) > 1.1:
            col = ground.lerp(path * wear, 0.28)
        elif abs(a) > 0.8:
            col = ground.lerp(path * wear * 0.86, 0.62)
        else:
            col = (path * wear).lerp(worn, (1.0 - abs(a) / 0.8) * 0.6)
            # gravel and small stones speckled through the tread
            if trail_rng.random() < 0.16:
                col = col.lerp(C["gravel"] if snow_w < 0.5 else C["snow"], trail_rng.uniform(0.3, 0.7))
        row.append(len(tv))
        tv.append((q.x, q.y, z))
        tc.append((col.x, col.y, col.z, 1.0))
    rows.append((p, side, centre_z, tangent))
    if k_ > 0:
        prev = len(tv) - 2 * len(ACROSS)
        for i in range(len(ACROSS) - 1):
            # counter-clockwise seen from above, so the faces point up and survive back-face culling
            tf.append((prev + i, prev + len(ACROSS) + i, prev + len(ACROSS) + i + 1, prev + i + 1))
trail = pw.mesh_object("trail", tv, tf, M["trail"], smooth=True)
pw.set_vertex_colors(trail, tc)


def near_site(x, y, extra=0.0):
    return any(math.hypot(x - sx, y - sy) < PAD.get(n, 6.5) + extra for n, (sx, sy) in SITES.items())


# --- stones ------------------------------------------------------------------------------------------
STONE_TONES = [Vector(pw.hex_color(c)[:3]) for c in ("#8d8a96", "#9c9088", "#76717e", "#aaa4ae")]
LICHEN = Vector(pw.hex_color("#8c9656")[:3])
LICHEN_PALE = Vector(pw.hex_color("#b9b98f")[:3])
rock_material = pw.vertex_color_material("rock_detail", roughness=0.95)


def chiselled_stone(name, subdivisions=2, squash=(1.15, 0.92, 0.66), cuts=9, tone=0, lichen=0.35, radius=0.5, slab=False):
    """A stone with split faces: a dented sphere cut by several random planes, the way rock breaks,
    with a bedded base. Colour goes per face: every plane gets its own shade from the way it
    faces, hollows and the foot go darker, and faces that look up carry patches of lichen.
    `slab` starts from a box instead and only chips its edges, for flat stones such as steps."""
    r = random.Random(f"{args.seed}-{name}")
    bm = bmesh.new()
    if slab:
        cube = bmesh.ops.create_cube(bm, size=2.0 * radius)["verts"]
        bmesh.ops.scale(bm, vec=Vector(squash), verts=cube)
        bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=2, use_grid_fill=True)
    else:
        pw.add_ico(bm, (0, 0, 0), radius, subdivisions, squash)
    offset = Vector((r.uniform(0, 40), r.uniform(0, 40), r.uniform(0, 40)))
    dent = 0.03 if slab else 0.12
    for v in bm.verts:
        u = v.co / radius
        v.co *= 1.0 + dent * noise.noise(u * 1.2 + offset) + dent * 0.35 * noise.noise(u * 3.2 + offset)
    for _ in range(cuts):
        normal = Vector((r.uniform(-1, 1), r.uniform(-1, 1), r.uniform(-0.25, 1.0))).normalized()
        if slab:
            # a box reaches furthest at a corner, and only those corners and edges get chipped
            extent = (abs(normal.x) * squash[0] + abs(normal.y) * squash[1] + abs(normal.z) * squash[2]) * radius
            depth = extent * r.uniform(0.8, 0.93)
        else:
            extent = max(abs(normal.x) * squash[0], abs(normal.y) * squash[1], abs(normal.z) * squash[2]) * radius
            depth = extent * r.uniform(0.45, 0.78)
        for v in bm.verts:
            d = v.co.dot(normal)
            if d > depth:
                v.co -= normal * (d - depth)
    floor_ = -squash[2] * radius * 0.6
    for v in bm.verts:
        v.co.z = max(v.co.z, floor_)
    obj = pw.bm_object(name, bm, rock_material)
    mesh = obj.data
    base = STONE_TONES[tone % len(STONE_TONES)]
    mean = sum(v.co.length for v in mesh.vertices) / len(mesh.vertices)
    attr = mesh.color_attributes.new(name="Col", type="BYTE_COLOR", domain="CORNER")
    colors = [0.0] * (len(mesh.loops) * 4)
    for poly in mesh.polygons:
        n = poly.normal
        centre = poly.center
        # faces on one plane share a normal, so they share this shade and read as one cut face
        shade = 0.88 + 0.24 * (0.5 + 0.5 * noise.noise(n * 2.3 + offset))
        hollow = pw.smoothstep(0.0, 0.2, (mean - centre.length) / max(mean, 1e-4))
        face = base * (shade * (1.0 - 0.28 * hollow))
        patch = noise.noise(centre / radius * 2.2 + offset * 1.7)
        if lichen > 0 and n.z > 0.35 and patch > 0.5 - lichen:
            face = face.lerp(LICHEN if patch > 0.72 - lichen else LICHEN_PALE, 0.5 * pw.smoothstep(0.5 - lichen, 0.85 - lichen, patch))
        for li in poly.loop_indices:
            z = mesh.vertices[mesh.loops[li].vertex_index].co.z
            foot = 1.0 - pw.smoothstep(floor_, floor_ + squash[2] * radius * 0.6, z)
            c = face * (1.0 - 0.25 * foot)
            colors[li * 4:li * 4 + 4] = (c.x, c.y, c.z, 1.0)
    attr.data.foreach_set("color", colors)
    mesh.color_attributes.active_color = attr
    mesh.color_attributes.render_color_index = 0
    bpy.data.objects.remove(obj)
    return mesh


# Stones by the trail and on the scree in six shapes; the meadows get three lighter ones. The
# shared generator skips the draws the old pebbles took, so everything placed later keeps its layout.
for _ in range(3 * 42 * 3):
    rng.random()
# blocky, slab-like and upright shapes, so a handful of stones never repeats a silhouette
STONE_SHAPES = ((1.25, 0.95, 0.72), (1.45, 1.0, 0.45), (0.95, 0.85, 1.0), (1.3, 0.8, 0.62), (1.1, 1.05, 0.8), (1.5, 0.9, 0.55))
rock_src = [chiselled_stone(f"pebble_src_{k_}", 2, STONE_SHAPES[k_], 8 + k_ % 4, k_) for k_ in range(6)]
meadow_src = [chiselled_stone(f"stone_src_{k_}", 1, STONE_SHAPES[k_ * 2], 7, k_ + 1, 0.3) for k_ in range(3)]
slab_src = [chiselled_stone(f"slab_src_{k_}", 1, (1.3, 0.46, 0.11), 8, k_ + 1, 0.12, slab=True) for k_ in range(3)]

# steps on steep stretches, edging stones and way-marks

edge_col = pw.collection("trail_edges")
marker_bm = bmesh.new()
pw.add_cone(marker_bm, (0, 0, -0.2), 0.05, 0.05, 1.0, segments=6)
marker_src = pw.bm_object("marker_src", marker_bm, M["wood_dark"]).data
bpy.data.objects.remove(bpy.data.objects["marker_src"])
band_bm = bmesh.new()
pw.add_cone(band_bm, (0, 0, 0.55), 0.056, 0.056, 0.08, segments=6)
pw.add_cone(band_bm, (0, 0, 0.71), 0.056, 0.056, 0.08, segments=6)
band_src = pw.bm_object("band_src", band_bm, M["marker_red"]).data
bpy.data.objects.remove(bpy.data.objects["band_src"])
white_bm = bmesh.new()
pw.add_cone(white_bm, (0, 0, 0.63), 0.056, 0.056, 0.08, segments=6)
white_src = pw.bm_object("white_src", white_bm, M["white"]).data
bpy.data.objects.remove(bpy.data.objects["white_src"])

# flat stones set into the tread and footprints pressed into the snow
flat_src = [chiselled_stone(f"cobble_src_{k_}", 1, (1.0, 0.8, 0.24), 5, k_ + 1, 0.1, radius=1.0) for k_ in range(2)]
print_bm = bmesh.new()
sole = pw.add_cone(print_bm, (0, 0.035, 0), 0.05, 0.05, 0.008, segments=10)
bmesh.ops.scale(print_bm, vec=Vector((1.0, 1.55, 1.0)), verts=sole)
heel = pw.add_cone(print_bm, (0, -0.075, 0), 0.04, 0.04, 0.008, segments=10)
bmesh.ops.scale(print_bm, vec=Vector((1.0, 1.15, 1.0)), verts=heel)
print_src = pw.bm_object("print_src", print_bm, M["snow_print"]).data
bpy.data.objects.remove(bpy.data.objects["print_src"])

step_kit = props
last_marker = -100.0
last_bar = -100
last_cairn = -100.0
ZERO = Vector((0, 0, 0))
for k_, (p, side, z, tangent) in enumerate(rows):
    if near_site(p.x, p.y):
        continue
    ahead = rows[min(k_ + 3, len(rows) - 1)][2]
    grade = (ahead - z) / (3 * SPACING)
    distance_along = k_ * SPACING
    if grade > 0.24 and k_ % 3 == 0:
        a = Vector((p.x, p.y, z)) + Vector((side.x, side.y, 0)) * (TRAIL_HALF * 0.95)
        b = Vector((p.x, p.y, z)) - Vector((side.x, side.y, 0)) * (TRAIL_HALF * 0.95)
        # each end rests on the ground under it: where the trail crosses a slope, a level step
        # would bury one end and leave the other sticking out like a fin
        a.z = surface(a.x, a.y)
        b.z = surface(b.x, b.y)
        if z < 56:
            # set proud of the tread, which sits a few centimetres above the ground
            step_kit.cyl("wood", Vector((0, 0, 0)), 0.0, a + Vector((0, 0, 0.07)), b + Vector((0, 0, 0.07)), 0.06, seg=6)
        else:
            # steps fall on every third row, so the shape follows the step count, not the row
            obj = bpy.data.objects.new(f"slab_{k_}", slab_src[(k_ // 3) % 3])
            # tilted across the trail to lie on the slope, level along it like a step
            cross = -math.atan2(a.z - b.z, (a - b).length)
            obj.rotation_euler = (0, cross, math.atan2(side.y, side.x) + trail_rng.uniform(-0.08, 0.08))
            # bedded in the snow, with only the top of the stone showing
            obj.location = (p.x, p.y, z + 0.005)
            edge_col.objects.link(obj)
    if k_ % 4 == 0:
        s = 1 if (k_ // 4) % 2 else -1
        q = p + side * s * (TRAIL_HALF + 0.18 + rng.uniform(0, 0.12))
        obj = bpy.data.objects.new(f"pebble_{k_}", rock_src[k_ % 6])
        size = rng.uniform(0.14, 0.32)
        obj.scale = (size, size * rng.uniform(0.7, 1.1), size * rng.uniform(0.5, 0.9))
        obj.rotation_euler = (0, 0, rng.uniform(0, math.tau))
        obj.location = (q.x, q.y, surface(q.x, q.y) - size * 0.15)
        edge_col.objects.link(obj)
    # cobbles bedded in the tread
    if z < SNOWLINE - 2 and trail_rng.random() < 0.2:
        q = p + side * (trail_rng.uniform(-0.7, 0.7) * TRAIL_HALF)
        obj = bpy.data.objects.new(f"cobble_{k_}", flat_src[k_ % 2])
        size = trail_rng.uniform(0.09, 0.2)
        obj.scale = (size, size * trail_rng.uniform(0.7, 1.1), size)
        obj.rotation_euler = (0, 0, trail_rng.uniform(0, math.tau))
        obj.location = (q.x, q.y, surface(q.x, q.y) + 0.05)
        edge_col.objects.link(obj)
    # a diagonal log every so often on moderate climbs, to shed rain off the path
    if 0.12 < grade <= 0.24 and z < 56 and k_ - last_bar > 38:
        last_bar = k_
        skew = side * math.cos(0.5) + tangent * math.sin(0.5)
        a3 = p + skew * (TRAIL_HALF * 1.25)
        b3 = p - skew * (TRAIL_HALF * 1.25)
        step_kit.cyl("wood", ZERO, 0.0, Vector((a3.x, a3.y, surface(a3.x, a3.y) + 0.07)), Vector((b3.x, b3.y, surface(b3.x, b3.y) + 0.07)), 0.055, seg=6)
    # roots crossing the path through the forest
    if z < 40 and trail_rng.random() < 0.035:
        turn = trail_rng.uniform(-0.6, 0.6)
        across = side * math.cos(turn) + tangent * math.sin(turn)
        s0 = p + across * (TRAIL_HALF * 1.7)
        s1 = p - across * (TRAIL_HALF * 1.4)
        mid = (s0 + s1) / 2 + tangent * trail_rng.uniform(-0.1, 0.1)
        pts = [Vector((v.x, v.y, surface(v.x, v.y) + lift)) for v, lift in ((s0, 0.02), (mid, 0.1), (s1, 0.03))]
        step_kit.cyl("root", ZERO, 0.0, pts[0], pts[1], 0.06, 0.04, seg=5)
        step_kit.cyl("root", ZERO, 0.0, pts[1], pts[2], 0.04, 0.02, seg=5)
    # cairns above the tree line, where posts give way to stacked stones
    if z > 50 and distance_along - last_cairn > 18.0:
        last_cairn = distance_along
        sign = -1 if (k_ // 7) % 2 else 1
        q = p + side * sign * (TRAIL_HALF + 0.9)
        zc = surface(q.x, q.y) - 0.02
        for level, r_ in enumerate((0.26, 0.21, 0.17, 0.12, 0.08)):
            lift = r_ * 0.5
            step_kit.ico("stone_light" if level % 2 else "stone", Vector((q.x, q.y, 0)), trail_rng.uniform(0, math.tau), (0, 0, zc + lift), r_, scale=(1.0, 0.85, 0.5))
            zc += lift * 1.6
    # footprints up the snow, left and right
    if z > SNOWLINE - 3:
        foot = 1 if k_ % 2 else -1
        q = p + side * (foot * 0.11 + trail_rng.uniform(-0.03, 0.03)) + tangent * trail_rng.uniform(-0.04, 0.04)
        obj = bpy.data.objects.new(f"print_{k_}", print_src)
        obj.rotation_euler = (0, 0, math.atan2(tangent.y, tangent.x) - math.pi / 2 + trail_rng.uniform(-0.2, 0.2))
        obj.location = (q.x, q.y, surface(q.x, q.y) + 0.06)
        edge_col.objects.link(obj)
    if distance_along - last_marker > 22.0 and z < SNOWLINE + 6:
        last_marker = distance_along
        q = p + side * (TRAIL_HALF + 0.7)
        for mesh_ in (marker_src, band_src, white_src):
            obj = bpy.data.objects.new(f"marker_{k_}_{mesh_.name}", mesh_)
            obj.location = (q.x, q.y, surface(q.x, q.y))
            edge_col.objects.link(obj)

# a rope handrail along the exposed final stretch, on the downhill side
exposed = []
for p, side, z, tangent in rows:
    if z < 74 or near_site(p.x, p.y, 1.0):
        continue
    left = surface(*(p + side * 2.5))
    right = surface(*(p - side * 2.5))
    s = 1 if left < right else -1
    exposed.append(p + side * s * (TRAIL_HALF + 0.35))
segments, current = [], []
for q in exposed[::8]:
    if current and (q - current[-1].xy).length > 4.0:
        segments.append(current)
        current = []
    current.append(Vector((q.x, q.y, 0)))
if current:
    segments.append(current)
for seg in segments:
    if len(seg) > 1:
        railing(seg)

# --- trees -------------------------------------------------------------------------------------
foliage = pw.material("pine_foliage", "#2e5242", roughness=0.9)
foliage_light = pw.material("pine_foliage_light", "#3d6a4a", roughness=0.9)
trunk = pw.material("pine_trunk", "#5b4232", roughness=1.0)


leaf = pw.material("leaf", "#58793a", roughness=0.9)
leaf_light = pw.material("leaf_light", "#7f9a47", roughness=0.9)
leaf_autumn = pw.material("leaf_autumn", "#b9823a", roughness=0.9)
leaf_autumn_light = pw.material("leaf_autumn_light", "#d8a84c", roughness=0.9)


def pine_tiered(name, tiers, first, second):
    """Variant a: twelve-sided tiers whose rims alternate out and down like the tips of branches,
    banded in two greens, on a trunk that flares at the root."""
    bark = random.Random(f"{args.seed}-{name}")
    bm = bmesh.new()
    trunk_verts = pw.add_cone(bm, (0, 0, 0), 0.1, 0.06, 0.62, segments=7)
    for v in trunk_verts:
        if v.co.z < 0.01:
            v.co.x *= 1.35
            v.co.y *= 1.35
    pw.assign_material_index(bm, trunk_verts, 2)
    z = 0.38
    scale = 4.0 / (tiers - 1)
    for k in range(tiers):
        radius = 0.68 - k * (0.5 / tiers)
        height_ = (0.88 - k * 0.11 * scale) * scale * 0.72
        vs = pw.add_cone(bm, (0, 0, z), radius, 0.02, height_, segments=12, rotation=k * 0.45 + bark.uniform(0, 0.3))
        rim = sorted((v for v in vs if v.co.z < z + 1e-3 and v.co.xy.length > radius * 0.5), key=lambda v: math.atan2(v.co.y, v.co.x))
        for i, v in enumerate(rim):
            out = 1.13 if i % 2 == 0 else 0.9
            v.co.x *= out * bark.uniform(0.96, 1.04)
            v.co.y *= out * bark.uniform(0.96, 1.04)
            v.co.z -= (0.09 * radius if i % 2 == 0 else 0.0) + bark.uniform(0.0, 0.03)
        pw.assign_material_index(bm, vs, k % 2)
        z += height_ * 0.46
    obj = pw.bm_object(name, bm, [first, second, trunk])
    return obj.data


def pine_branches(name, tiers, first, second):
    """Variant b: a fir built from branches. Whorls of drooping blades round a tapering trunk,
    dark near the trunk and lighter at the tips, with gaps the light and the trunk show through."""
    bark = random.Random(f"{args.seed}-{name}")
    bm = bmesh.new()
    top = 0.4 + tiers * 0.36
    trunk_verts = pw.add_cone(bm, (0, 0, 0), 0.09, 0.02, top, segments=7)
    pw.assign_material_index(bm, trunk_verts, 2)
    up = Vector((0.0, 0.0, 1.0))
    for k in range(tiers):
        f = k / max(1, tiers - 1)
        z = 0.42 + k * (top - 0.75) / max(1, tiers - 1)
        reach = 0.72 - 0.5 * f
        blades = 8 - k // 2
        for b in range(blades):
            a = b / blades * math.tau + k * 0.55 + bark.uniform(-0.18, 0.18)
            d = Vector((math.cos(a), math.sin(a), 0.0))
            sd = Vector((-d.y, d.x, 0.0))
            droop = reach * bark.uniform(0.32, 0.45)
            width = reach * 0.34
            points = (
                up * (z + 0.12),
                d * 0.06 + sd * width * 0.35 + up * z,
                d * 0.06 - sd * width * 0.35 + up * z,
                d * reach * 0.55 + up * (z + 0.04 - droop * 0.35),
                d * reach * 0.55 + sd * width * 0.5 + up * (z - droop * 0.45),
                d * reach * 0.55 - sd * width * 0.5 + up * (z - droop * 0.45),
                d * reach + up * (z - droop),
            )
            v = [bm.verts.new(p) for p in points]
            for face, index in (((v[0], v[3], v[4], v[1]), 0), ((v[0], v[2], v[5], v[3]), 0), ((v[3], v[6], v[4]), 1), ((v[3], v[5], v[6]), 1)):
                bm.faces.new(face).material_index = index
        # a small core, so a whorl reads as full from below
        core = pw.add_cone(bm, (0, 0, z - 0.05), reach * 0.32, 0.03, 0.42, segments=7, rotation=k)
        pw.assign_material_index(bm, core, 0)
    spire = pw.add_cone(bm, (0, 0, top - 0.32), 0.16, 0.0, 0.5, segments=7)
    pw.assign_material_index(bm, spire, 1)
    obj = pw.bm_object(name, bm, [first, second, trunk])
    return obj.data


def broadleaf(name, first, second):
    """Variant c adds these: a round crown of dented blobs in two tones over a straight trunk."""
    bark = random.Random(f"{args.seed}-{name}")
    bm = bmesh.new()
    trunk_verts = pw.add_cone(bm, (0, 0, 0), 0.11, 0.07, 1.2, segments=7)
    pw.assign_material_index(bm, trunk_verts, 2)
    blobs = ((0.0, 0.0, 1.75, 0.62), (0.38, 0.1, 1.5, 0.48), (-0.34, -0.12, 1.55, 0.5), (0.05, -0.36, 1.45, 0.44), (-0.1, 0.34, 2.05, 0.4))
    offset = Vector((bark.uniform(0, 30), bark.uniform(0, 30), bark.uniform(0, 30)))
    for i, (x, y, z, r) in enumerate(blobs):
        vs = pw.add_ico(bm, (x, y, z), r, 1, (1.0, 1.0, 0.85))
        centre = Vector((x, y, z))
        for v in vs:
            v.co = centre + (v.co - centre) * (1.0 + 0.12 * noise.noise((v.co - centre) * 3.0 + offset))
        pw.assign_material_index(bm, vs, i % 2)
    obj = pw.bm_object(name, bm, [first, second, trunk])
    return obj.data


if VARIANT.trees == "b":
    pine_tall = pine_branches("pine_tall", 7, foliage, foliage_light)
    pine_round = pine_branches("pine_round", 5, foliage_light, foliage)
else:
    pine_tall = pine_tiered("pine_tall", 7, foliage, foliage_light)
    pine_round = pine_tiered("pine_round", 5, foliage_light, foliage)
broadleaf_green = broadleaf("broadleaf_green", leaf, leaf_light) if VARIANT.trees == "c" else None
broadleaf_autumn = broadleaf("broadleaf_autumn", leaf_autumn, leaf_autumn_light) if VARIANT.trees == "c" else None
tree_rng = random.Random(f"{args.seed}-tree-kinds")

trees_col = pw.collection("trees")
placed = 0
attempts = 0
while placed < 1800 and attempts < 70000:
    attempts += 1
    x = rng.uniform(-200.0, 200.0)
    y = rng.uniform(-200.0, 190.0)
    h = surface(x, y)
    if h < WATER + 1.4 or h > 50.0:
        continue
    n = surface_normal(x, y)
    if n.z < 0.84:
        continue
    density = noise.noise(Vector((x * 0.028, y * 0.028, 1.7)))
    if density < -0.05 - 0.25 * pw.smoothstep(30.0, 50.0, h):
        continue
    d_route, _ = route_distance(x, y)
    if d_route < 3.4 or near_site(x, y, 2.5):
        continue
    mesh = pine_tall if rng.random() < 0.65 else pine_round
    # variant c: broadleaves take over much of the low ground, a few already turning
    if broadleaf_green and h < 30.0 and tree_rng.random() < 0.45:
        mesh = broadleaf_autumn if tree_rng.random() < 0.18 else broadleaf_green
    obj = bpy.data.objects.new(f"tree_{placed}", mesh)
    s = rng.uniform(1.4, 2.6) * (1.0 - 0.3 * pw.smoothstep(30.0, 50.0, h))
    obj.scale = (s, s, s * rng.uniform(0.9, 1.25))
    obj.rotation_euler = (0.0, 0.0, rng.uniform(0, math.tau))
    obj.location = (x, y, h - 0.15)
    trees_col.objects.link(obj)
    placed += 1
print(f"[pw] trees placed: {placed}")

# --- boulders ----------------------------------------------------------------------------------------
rocks_col = pw.collection("rocks")
# Boulders: the same chiselled stones, cut more often and carrying more lichen.
boulder_src = [chiselled_stone(f"boulder_src_{k_}", 2, STONE_SHAPES[k_ * 2 + 1], 9, k_, 0.45) for k_ in range(3)]
for k in range(220):
    x = rng.uniform(-170.0, 170.0)
    y = rng.uniform(-170.0, 170.0)
    h = surface(x, y)
    if h < WATER + 0.6 or h > 95.0 or route_distance(x, y)[0] < 2.0 or near_site(x, y):
        continue
    # nothing rests on a near-vertical face; a boulder there sinks out of sight and leaves only its shadow
    if surface_normal(x, y).z < 0.74:
        continue
    obj = bpy.data.objects.new(f"rock_{k}", boulder_src[k % 3])
    s = rng.uniform(1.0, 4.0)
    obj.scale = (s, s * rng.uniform(0.75, 1.2), s * rng.uniform(0.8, 1.25))
    obj.rotation_euler = (0.0, 0.0, rng.uniform(0, math.tau))
    # settle on the lowest ground under the footprint, so no side floats and casts a loose shadow
    reach = 0.42 * s
    rim = [surface(x + math.cos(a) * reach, y + math.sin(a) * reach) for a in (0.0, 1.05, 2.1, 3.14, 4.19, 5.24)]
    if max(rim) - min(rim) > 0.55 * s:
        continue  # too much drop under it for its size
    low = min([h] + rim)
    # but never so deep on a steep face that the rock disappears into it
    obj.location = (x, y, max(low, h - 0.15 * s) - 0.05 * s)
    rocks_col.objects.link(obj)

# --- grass tufts and flowers along the trail and around the camps ---------------------------------------------
# Grass variants: a smaller; b smaller, sparser and muted; c a fine low lawn close to the ground's colour.
GRASS = {
    "a": {"scale": 0.55, "keep": 1.0, "green": "#7d9a52", "dry": "#a7a35f", "fine": False},
    "b": {"scale": 0.45, "keep": 0.55, "green": "#728c4e", "dry": "#9a9760", "fine": False},
    "c": {"scale": 1.0, "keep": 1.0, "green": "#78934f", "dry": "#a29c5c", "fine": True},
}[VARIANT.grass]
grass_keep = random.Random(f"{args.seed}-grass-keep")
grass_mat = pw.material("grass_tuft", GRASS["green"], 0.9)
grass_dry = pw.material("grass_tuft_dry", GRASS["dry"], 0.9)


def tuft_mesh(name, mat):
    # Seven curved blades: a narrowing quad up to the knee, then a leaning tip. The blades draw
    # from their own generator so everything placed after them keeps its layout.
    for _ in range(10):
        rng.random()
    blade = random.Random(f"{args.seed}-{name}")
    bm = bmesh.new()
    fine = GRASS["fine"]
    count = 11 if fine else 7
    for k in range(count):
        a = k / count * math.tau + blade.uniform(-0.35, 0.35)
        out = Vector((math.cos(a), math.sin(a), 0))
        side = Vector((-math.sin(a), math.cos(a), 0))
        tall = blade.uniform(0.13, 0.24) if fine else blade.uniform(0.3, 0.46)
        width = 0.018 if fine else 0.032
        root = out * blade.uniform(0.0, 0.07 if fine else 0.05)
        v1 = bm.verts.new(root - side * width)
        v2 = bm.verts.new(root + side * width)
        knee = root + out * tall * 0.16 + Vector((0, 0, tall * 0.55))
        v3 = bm.verts.new(knee + side * width * 0.6)
        v4 = bm.verts.new(knee - side * width * 0.6)
        v5 = bm.verts.new(root + out * tall * 0.45 + Vector((0, 0, tall)))
        bm.faces.new((v1, v2, v3, v4))
        bm.faces.new((v4, v3, v5))
    o = pw.bm_object(name, bm, mat)
    data = o.data
    bpy.data.objects.remove(o)
    return data


tufts = [tuft_mesh("tuft_green", grass_mat), tuft_mesh("tuft_dry", grass_dry)]
flower_meshes = []
for name in ("flower_white", "flower_yellow", "flower_violet", "flower_pink"):
    bm = bmesh.new()
    pw.add_ico(bm, (0, 0, 0.12), 0.045, 1, (1.0, 1.0, 0.6))
    o = pw.bm_object(f"{name}_src", bm, M[name])
    flower_meshes.append(o.data)
    bpy.data.objects.remove(o)

detail_col = pw.collection("ground_detail")
count_tufts = 0
count_flowers = 0
attempts = 0
while (count_tufts < 2600 or count_flowers < 700) and attempts < 60000:
    attempts += 1
    # half the samples hug the trail, the rest gather round the camps
    if attempts % 2:
        p, side, z, _ = rows[rng.randrange(len(rows))]
        q = p + side * rng.choice((-1, 1)) * rng.uniform(TRAIL_HALF + 0.15, 7.0)
    else:
        name = rng.choice([n for n in SITES if n not in ("summit",)])
        sx, sy = SITES[name]
        a = rng.uniform(0, math.tau)
        r = rng.uniform(1.5, PAD.get(name, 6.5) + 6.0)
        q = Vector((sx + math.cos(a) * r, sy + math.sin(a) * r))
    h = surface(q.x, q.y)
    if h > 62 or h < WATER + 0.8 or surface_normal(q.x, q.y).z < 0.82:
        continue
    if route_distance(q.x, q.y)[0] < TRAIL_HALF + 0.12:
        continue
    if count_flowers < 700 and h < 44 and rng.random() < 0.25:
        obj = bpy.data.objects.new(f"flower_{count_flowers}", flower_meshes[count_flowers % 4])
        s = rng.uniform(0.8, 1.4)
        count_flowers += 1
    elif count_tufts < 2600:
        obj = bpy.data.objects.new(f"tuft_{count_tufts}", tufts[0 if h < 30 else 1] if rng.random() < 0.8 and h < 54 else tufts[1])
        s = rng.uniform(0.9, 1.8)
        count_tufts += 1
    else:
        continue
    is_tuft = obj.name.startswith("tuft")
    if is_tuft:
        s *= GRASS["scale"]
    obj.scale = (s, s, s)
    obj.rotation_euler = (0, 0, rng.uniform(0, math.tau))
    obj.location = (q.x, q.y, h - 0.02)
    if is_tuft and grass_keep.random() > GRASS["keep"]:
        bpy.data.objects.remove(obj)
        continue
    detail_col.objects.link(obj)
print(f"[pw] tufts {count_tufts}, flowers {count_flowers}")

# scree round the high camps, where nothing grows
for name in ("camp_3", "camp_4", "camp_5", "ridge"):
    sx, sy = SITES[name]
    for k in range(90):
        a = rng.uniform(0, math.tau)
        r = rng.uniform(2.5, 12.0)
        x, y = sx + math.cos(a) * r, sy + math.sin(a) * r
        if route_distance(x, y)[0] < TRAIL_HALF + 0.3:
            continue
        obj = bpy.data.objects.new(f"scree_{name}_{k}", rock_src[k % 6])
        s = rng.uniform(0.12, 0.45) * (1.6 if rng.random() < 0.12 else 1.0)
        obj.scale = (s, s * rng.uniform(0.7, 1.2), s * rng.uniform(0.5, 0.8))
        obj.rotation_euler = (0, 0, rng.uniform(0, math.tau))
        obj.location = (x, y, surface(x, y) - s * 0.1)
        detail_col.objects.link(obj)

# --- the meadows and slopes away from the trail ------------------------------------------------------------------
# Patches of grass, bushes, loose stones and the odd fallen trunk, so the open ground between the
# camps reads as close as the camps do. Everything here is instanced, and draws from its own
# generator so the camps placed afterwards keep their layout.
scatter = random.Random(f"{args.seed}-meadows")
bush_meshes = []
for k_, mat in enumerate(("bush", "bush_light")):
    bm = bmesh.new()
    for c in range(3):
        a = c / 3 * math.tau + k_
        pw.add_ico(bm, (math.cos(a) * 0.32, math.sin(a) * 0.32, 0.28 + 0.08 * c), 0.42 - 0.06 * c, 1, (1.0, 1.0, 0.78))
    for v in bm.verts:
        v.co *= 1.0 + 0.1 * noise.noise(v.co * 4.0 + Vector((k_ * 3.3, 0.7, 1.9)))
    o = pw.bm_object(f"{mat}_src", bm, M[mat])
    bush_meshes.append(o.data)
    bpy.data.objects.remove(o)

placed_tufts = placed_bushes = placed_stones = 0
attempts = 0
while (placed_tufts < 5200 or placed_bushes < 380 or placed_stones < 1400) and attempts < 140000:
    attempts += 1
    x = scatter.uniform(-190.0, 190.0)
    y = scatter.uniform(-190.0, 180.0)
    h = surface(x, y)
    if h < WATER + 1.0 or h > 100.0:
        continue
    up = surface_normal(x, y).z
    if route_distance(x, y)[0] < TRAIL_HALF + 0.4 or near_site(x, y, 1.0):
        continue
    patch = noise.noise(Vector((x * 0.06, y * 0.06, 12.3)))
    if placed_stones < 1400 and h > 24.0 and up > 0.62 and scatter.random() < 0.3:
        obj = bpy.data.objects.new(f"stone_{placed_stones}", meadow_src[placed_stones % 3])
        size = scatter.uniform(0.12, 0.42) * (1.8 if scatter.random() < 0.1 else 1.0)
        obj.scale = (size, size * scatter.uniform(0.7, 1.2), size * scatter.uniform(0.5, 0.85))
        obj.rotation_euler = (0, 0, scatter.uniform(0, math.tau))
        obj.location = (x, y, h - size * 0.12)
        placed_stones += 1
    elif placed_bushes < 380 and h < 46.0 and up > 0.84 and patch > 0.05 and scatter.random() < 0.08:
        obj = bpy.data.objects.new(f"bush_{placed_bushes}", bush_meshes[placed_bushes % 2])
        size = scatter.uniform(0.7, 1.5)
        obj.scale = (size, size * scatter.uniform(0.85, 1.15), size * scatter.uniform(0.8, 1.1))
        obj.rotation_euler = (0, 0, scatter.uniform(0, math.tau))
        obj.location = (x, y, h - 0.08 * size)
        placed_bushes += 1
    elif placed_tufts < 5200 and h < 60.0 and up > 0.8 and patch > -0.15:
        dry = h > 32.0 or scatter.random() < 0.25
        obj = bpy.data.objects.new(f"meadow_tuft_{placed_tufts}", tufts[1 if dry else 0])
        size = scatter.uniform(0.8, 1.6) * GRASS["scale"]
        obj.scale = (size, size, size * scatter.uniform(0.85, 1.2))
        obj.rotation_euler = (0, 0, scatter.uniform(0, math.tau))
        obj.location = (x, y, h - 0.02)
        placed_tufts += 1
        if grass_keep.random() > GRASS["keep"]:
            bpy.data.objects.remove(obj)
            continue
    else:
        continue
    detail_col.objects.link(obj)
print(f"[pw] meadows: tufts {placed_tufts}, bushes {placed_bushes}, stones {placed_stones}")

# fallen trunks in the woods, bark side up, with a pale cut at each end
for k_ in range(40):
    x = scatter.uniform(-120.0, 140.0)
    y = scatter.uniform(-150.0, 60.0)
    h = surface(x, y)
    if h < WATER + 2.0 or h > 44.0 or surface_normal(x, y).z < 0.88:
        continue
    if route_distance(x, y)[0] < 2.5 or near_site(x, y, 2.0):
        continue
    length = scatter.uniform(2.2, 4.2)
    turn = scatter.uniform(0, math.tau)
    d = Vector((math.cos(turn), math.sin(turn), 0)) * (length / 2)
    a = Vector((x, y, 0)) - d
    b = Vector((x, y, 0)) + d
    r = scatter.uniform(0.12, 0.2)
    a.z = surface(a.x, a.y) + r * 0.8
    b.z = surface(b.x, b.y) + r * 0.8
    props.cyl("wood_dark", ZERO, 0.0, a, b, r, r * 0.85, seg=7)
    for end, inward in ((a, (b - a).normalized()), (b, (a - b).normalized())):
        props.cyl("wood_light", ZERO, 0.0, end - inward * 0.01, end + inward * 0.012, r * 0.9, r * 0.9, seg=7)

for name in ("pine_tall", "pine_round"):
    bpy.data.objects.remove(bpy.data.objects[name])

# --- camps ---------------------------------------------------------------------------------------------------------
for name in SITES:
    pw.empty(f"anchor_{name}", at(name, 0, 0))

# Base camp: three tents round a campfire, a cooking corner, lantern, map and the first signpost.
r0 = frame_rot("base")
campfire(at("base", 1.6, 0.6), r0)
a_frame_tent(at("base", -1.0, 2.9), r0 + 0.35, "fabric_orange", 1.1)
a_frame_tent(at("base", 4.0, 2.8), r0 - 0.4, "fabric_yellow", 1.0)
a_frame_tent(at("base", 4.6, -1.5), r0 - 1.7, "fabric_teal", 1.05)
log_seat(at("base", 0.1, 0.2), r0 + 1.4)
log_seat(at("base", 1.9, -0.9), r0 + 0.1)
cooking_tripod(at("base", 2.6, 1.3), r0)
backpack(at("base", -0.4, 1.4), r0 + 0.5, "fabric_red")
backpack(at("base", 3.1, 1.9), r0 - 0.6, "fabric_blue")
crates(at("base", -2.4, -0.6), r0 + 0.3)
firewood(at("base", -2.5, 1.2), r0 + 1.2)
picnic_table(at("base", -3.4, -3.4), r0 + 0.2)
lantern_post(at("base", 0.6, -1.6), r0)
map_board(at("base", -1.6, -4.6), r0 + 0.2)
signpost(at("base", -1.3, -1.9), r0, [(math.pi / 2, 1.7), (math.pi / 2 + 0.6, 1.5), (-math.pi / 2, 1.3)])
flag_pole(at("base", 5.6, 0.8), r0, "fabric_orange", 3.2)

# Camp 1: forest edge, a dome tent and a canadian tent, bench and way-mark.
r1 = frame_rot("camp_1")
dome_tent(at("camp_1", -2.3, 0.9), r1 + 0.4, "fabric_green", 0.9)
a_frame_tent(at("camp_1", 2.4, 1.3), r1 - 0.5, "fabric_orange", 0.95)
bench(at("camp_1", -2.0, -1.8), r1 + math.pi * 0.95)
backpack(at("camp_1", 1.3, -0.5), r1 + 0.8, "fabric_teal")
campfire_ring = at("camp_1", -0.2, 2.6)
for s in range(8):
    a = s / 8 * math.tau
    props.ico("stone", campfire_ring, r1, (math.cos(a) * 0.36, math.sin(a) * 0.36, 0.04), 0.09, (1.2, 1.0, 0.7))
props.ico("wood_dark", campfire_ring, r1, (0, 0, 0.03), 0.18, (1.0, 1.0, 0.2))
signpost(at("camp_1", 1.4, -2.0), r1, [(math.pi / 2, 1.7), (-math.pi / 2, 1.5)])
cairn(at("camp_1", -1.3, 3.4), r1)
flag_pole(at("camp_1", 3.4, -0.4), r1, "marker_red")

# Camp 2: the mountain refuge, with lit windows and smoke, a fence and a water trough.
r2 = frame_rot("camp_2")
hut(at("camp_2", 4.4, 1.6), r2 - 0.2)
dome_tent(at("camp_2", -2.8, 2.0), r2 + 0.3, "fabric_yellow", 0.85)
firewood(at("camp_2", 2.0, 3.8), r2 - 0.2)
trough = at("camp_2", -1.8, -1.3)
props.box("wood_dark", trough, r2, (0, 0, 0.3), (1.2, 0.45, 0.35))
props.box("lantern", trough, r2, (0, 0, 0.45), (1.05, 0.3, 0.02))
props.cyl("metal", trough, r2, (0.5, 0.25, 0.3), (0.5, 0.25, 1.0), 0.03, seg=6)
fence_line = [at("camp_2", -5.0 + i * 1.6, -3.4) for i in range(6)]
railing([Vector((p.x, p.y, 0)) for p in fence_line])
signpost(at("camp_2", 0.9, -2.1), r2, [(math.pi / 2, 1.7), (-math.pi / 2, 1.5), (math.pi, 1.3)])
backpack(at("camp_2", 1.6, 0.6), r2 + 2.5, "fabric_orange")
flag_pole(at("camp_2", -4.2, 0.4), r2, "fabric_blue")

# Camp 3: moraine camp sheltered by stone windbreaks, with crates and a solar panel.
r3 = frame_rot("camp_3")
for (dx, dy, color, turn) in ((-2.6, 1.4, "fabric_red", 0.4), (2.7, 1.8, "fabric_yellow", -0.3)):
    centre = at("camp_3", dx, dy)
    dome_tent(centre, r3 + turn, color, 0.85)
    stone_wall(centre, r3 + turn + math.pi / 2, radius=1.55, start=-1.6, end=1.6)
crates(at("camp_3", 0.4, 3.4), r3)
solar_stand(at("camp_3", -0.6, 3.6), r3 + math.pi)
backpack(at("camp_3", 1.3, -0.4), r3 - 0.9, "fabric_green")
cairn(at("camp_3", -1.4, -2.3), r3, 1.35)
signpost(at("camp_3", 1.5, -2.2), r3, [(math.pi / 2, 1.7), (-math.pi / 2, 1.5)])
flag_pole(at("camp_3", 4.0, -0.2), r3, "marker_red")

# Camp 4: high camp; tents tied down, ice axes, rope coils, a lantern for the night.
r4 = frame_rot("camp_4")
dome_tent(at("camp_4", -2.3, 1.2), r4 + 0.2, "fabric_yellow", 0.8)
dome_tent(at("camp_4", 2.2, 1.8), r4 - 0.4, "fabric_red", 0.8)
stone_wall(at("camp_4", 0.0, 3.2), r4 + math.pi / 2, radius=3.0, start=-0.7, end=0.7, rows=2, mat="stone_light")
ice_axe(at("camp_4", 0.7, -0.6), r4 + 0.3)
ice_axe(at("camp_4", 1.0, -0.9), r4 - 0.2)
rope_coil(at("camp_4", -0.8, -0.8), r4)
backpack(at("camp_4", -1.3, -0.3), r4 + 0.6, "fabric_blue")
lantern_post(at("camp_4", 3.3, -0.6), r4)
cairn(at("camp_4", -3.4, -1.6), r4)
flag_pole(at("camp_4", 3.8, 1.0), r4, "fabric_orange")

# Camp 5: last camp on the snow; snow wall, prayer flags and a radio mast.
r5 = frame_rot("camp_5")
dome_tent(at("camp_5", -2.0, 1.4), r5 + 0.3, "fabric_orange", 0.85)
dome_tent(at("camp_5", 2.4, 1.0), r5 - 0.3, "fabric_teal", 0.8)
stone_wall(at("camp_5", 0.2, 3.6), r5 + math.pi / 2, radius=3.4, start=-0.75, end=0.75, rows=3, mat="snow")
ice_axe(at("camp_5", 0.6, -0.4), r5)
rope_coil(at("camp_5", -0.6, -0.9), r5)
radio_mast(at("camp_5", -3.6, -0.6), r5)
pole_a = at("camp_5", -3.0, 2.8) + Vector((0, 0, 2.0))
pole_b = at("camp_5", 3.3, 2.6) + Vector((0, 0, 2.0))
props.cyl("metal", Vector((0, 0, 0)), 0.0, pole_a - Vector((0, 0, 2.0)), pole_a, 0.03, seg=6)
props.cyl("metal", Vector((0, 0, 0)), 0.0, pole_b - Vector((0, 0, 2.0)), pole_b, 0.03, seg=6)
prayer_flags(pole_a, pole_b, 14, 0.4)
lantern_post(at("camp_5", 1.7, -1.4), r5)

# Ridge: a viewing deck of separate boards on posts with stone footings and cross braces, a
# railing with two rails, steps, an orientation table, tourist binoculars, a bench, the
# panorama board and drifts of snow on the uphill side.
rr = frame_rot("ridge")
deck = at("ridge", 0, 0)
R_ = Matrix.Rotation(rr, 3, "Z")
DW, DL, DZ = 4.4, 2.6, 0.24
for x in (-2.0, 0.0, 2.0):
    for y in (-1.1, 1.1):
        props.box("stone", deck, rr, (x, y, -0.15), (0.32, 0.32, 0.3))
        props.cyl("wood_dark", deck, rr, (x, y, -0.6), (x, y, DZ - 0.08), 0.07, seg=6)
for y in (-1.1, 1.1):
    for x0, x1 in ((-2.0, 0.0), (0.0, 2.0)):
        props.cyl("wood", deck, rr, (x0, y, -0.45), (x1, y, DZ - 0.15), 0.035, seg=4)
        props.cyl("wood", deck, rr, (x0, y, DZ - 0.15), (x1, y, -0.45), 0.035, seg=4)
for y in (-DL / 2, DL / 2):
    props.box("wood_dark", deck, rr, (0, y, DZ - 0.1), (DW + 0.1, 0.1, 0.14))
for x in (-DW / 2, DW / 2):
    props.box("wood_dark", deck, rr, (x, 0, DZ - 0.1), (0.1, DL, 0.14))
for b in range(13):
    y = -DL / 2 + (b + 0.5) * DL / 13
    props.box("wood_light" if b % 3 else "wood", deck, rr, (0, y, DZ), (DW, DL / 13 - 0.025, 0.04))
# Local +Y points up to the summit, so the valley and the drop lie towards -Y: the railing runs
# along that side and round the ends, and the steps come up from the trail at the back.
rail_posts = [(x, -DL / 2 + 0.05) for x in (-2.15, -1.08, 0.0, 1.08, 2.15)] + [(side * 2.15, y) for side in (-1, 1) for y in (-0.3, 0.75)]
for x, y in rail_posts:
    props.box("wood_dark", deck, rr, (x, y, DZ + 0.5), (0.09, 0.09, 1.0))
props.box("wood", deck, rr, (0, -DL / 2 + 0.05, DZ + 1.0), (DW + 0.2, 0.12, 0.06))
props.box("wood", deck, rr, (0, -DL / 2 + 0.05, DZ + 0.55), (DW + 0.1, 0.06, 0.05))
for side in (-1, 1):
    props.box("wood", deck, rr, (side * 2.15, -0.2, DZ + 1.0), (0.12, DL - 0.6, 0.06))
    props.box("wood", deck, rr, (side * 2.15, -0.2, DZ + 0.55), (0.06, DL - 0.6, 0.05))
for step in range(3):
    props.box("wood_light", deck, rr, (0.9, DL / 2 + 0.22 + step * 0.26, DZ - 0.12 - step * 0.14), (1.2, 0.26, 0.05))
    props.box("wood_dark", deck, rr, (0.9, DL / 2 + 0.22 + step * 0.26, DZ - 0.3 - step * 0.14), (1.2, 0.2, 0.3))
# orientation table: a low stone pedestal with a bronze disc lying almost flat on its top,
# marked out towards the peaks
ot = Vector((1.25, -0.4, DZ))
props.box("stone", deck, rr, tuple(ot + Vector((0, 0, 0.36))), (0.5, 0.5, 0.72))
props.box("stone_light", deck, rr, tuple(ot + Vector((0, 0, 0.75))), (0.74, 0.74, 0.07))
disc = deck + R_ @ (ot + Vector((0, 0, 0.82)))
props.cyl("bronze", disc, rr, (0, 0.012, -0.01), (0, -0.012, 0.035), 0.3, seg=20)
for i in range(8):
    a = i / 8 * math.tau
    props.box("roof_dark", disc, rr + a, (0.15, 0, 0.04), (0.2, 0.014, 0.008))
props.ico("bronze", disc, rr, (0, 0, 0.05), 0.035)
# tourist binoculars on a pedestal
bn = Vector((-0.2, -0.75, DZ))
props.cyl("metal_dark", deck, rr, tuple(bn), tuple(bn + Vector((0, 0, 1.0))), 0.06, seg=8)
props.box("fabric_teal", deck, rr, tuple(bn + Vector((0, 0, 1.12))), (0.34, 0.22, 0.18))
for side in (-1, 1):
    props.cyl("metal_dark", deck, rr, tuple(bn + Vector((side * 0.08, -0.1, 1.14))), tuple(bn + Vector((side * 0.08, -0.2, 1.14))), 0.05, seg=10)
    props.cyl("metal_dark", deck, rr, tuple(bn + Vector((side * 0.08, 0.1, 1.15))), tuple(bn + Vector((side * 0.08, 0.17, 1.15))), 0.03, seg=8)
telescope(deck + R_ @ Vector((-1.4, -0.55, DZ)), rr + math.pi)
bench(deck + R_ @ Vector((0.2, 0.6, DZ)), rr)
map_board(at("ridge", 2.9, -1.6), rr + 0.3)
signpost(at("ridge", -2.8, -1.4), rr, [(math.pi / 2, 1.7), (-math.pi / 2, 1.5)])
flag_pole(deck + R_ @ Vector((2.15, -DL / 2 + 0.05, DZ + 1.0)), rr, "fabric_blue", 1.6)
for dx_, dy_, r_ in ((-1.6, 2.2, 0.9), (-0.6, 2.6, 1.1), (2.7, 2.0, 0.8), (-2.9, 0.4, 0.7)):
    drift = at("ridge", dx_, dy_)
    props.ico("snow", drift, rr, (0, 0, 0.0), r_, (1.6, 1.0, 0.32), sub=2)

# Summit: an observatory on a stone plinth. The last camera rests beyond the summit looking back
# at it, 34 degrees round from the ridge line, so the open slit with the telescope inside, the
# ladder and the front of the control building all turn towards it.
ox, oy = SITES["summit"]
oz = surface(ox, oy)
o = Vector((ox, oy, oz))
fr = frame_rot("summit")
FR = Matrix.Rotation(fr, 3, "Z")
CAM = math.radians(124.0)  # azimuth of the last camera in summit-local space
obs = Kit("observatory")


def here(p):
    """World point from summit-local coordinates."""
    return o + FR @ Vector(p)


def polar(az, r, z=0.0):
    return Vector((math.cos(az) * r, math.sin(az) * r, z))


def part(mat, points, faces, kit=obs):
    """Raw summit-local geometry: points and faces as index tuples."""
    bm = kit.bm(mat)
    vs = [bm.verts.new(Vector(p)) for p in points]
    for f in faces:
        bm.faces.new([vs[i] for i in f])
    Kit._place(bm, vs, o, fr)


def quads(mat, polys, facing):
    """Loose faces, each wound so its normal agrees with facing(centre)."""
    points, faces, index = [], [], {}

    def corner(p):
        key = tuple(round(c, 5) for c in p)
        if key not in index:
            index[key] = len(points)
            points.append(p)
        return index[key]

    for poly in polys:
        poly = [Vector(p) for p in poly]
        centre = sum(poly, Vector()) / len(poly)
        normal = (poly[1] - poly[0]).cross(poly[-1] - poly[0])
        if normal.dot(facing(centre)) < 0:
            poly.reverse()
        face = []
        for p in poly:
            i = corner(p)
            if i not in face:
                face.append(i)
        if len(face) >= 3:
            faces.append(tuple(face))
    part(mat, points, faces)


def open_cylinder(mat, centre, r, z0, z1, seg):
    pts = [Vector((centre[0] + math.cos(s / seg * math.tau) * r, centre[1] + math.sin(s / seg * math.tau) * r, z)) for z in (z0, z1) for s in range(seg)]
    part(mat, pts, [(s, (s + 1) % seg, seg + (s + 1) % seg, seg + s) for s in range(seg)])


def disc(mat, centre, r, z, seg):
    pts = [Vector((centre[0], centre[1], z))] + [Vector((centre[0] + math.cos(s / seg * math.tau) * r, centre[1] + math.sin(s / seg * math.tau) * r, z)) for s in range(seg)]
    part(mat, pts, [(0, 1 + s, 1 + (s + 1) % seg) for s in range(seg)])


def polyline_tube(mat, pts, radius, sides=4, closed=False, kit=obs):
    """A thin tube through summit-local points: rails, wires and lattice members."""
    pts = [Vector(p) for p in pts]
    n = len(pts)
    rings = []
    for k in range(n):
        prev = pts[k - 1] if closed else pts[max(k - 1, 0)]
        nxt = pts[(k + 1) % n] if closed else pts[min(k + 1, n - 1)]
        t = (nxt - prev).normalized()
        ref = Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))
        a = t.cross(ref).normalized()
        b = t.cross(a).normalized()
        rings.append([pts[k] + (a * math.cos(s / sides * math.tau) + b * math.sin(s / sides * math.tau)) * radius for s in range(sides)])
    faces = []
    for k in range(n if closed else n - 1):
        k2 = (k + 1) % n
        for s in range(sides):
            s2 = (s + 1) % sides
            faces.append((k * sides + s, k * sides + s2, k2 * sides + s2, k2 * sides + s))
    part(mat, [p for ring in rings for p in ring], faces, kit)


def slit_dome(centre, R, az, half, reach, rows=9, front=16, back=10, wall=0.1, seams=True, lining=(6, 12, 6)):
    """A hemisphere split by a shutter slit `2 * half` wide that rises from the horizon at
    azimuth `az`, crosses the top and ends `reach` radians beyond it, with the upper shutter
    rolled back over the rear. It is built in the slit's own coordinates, so the slit edges are
    true arcs: beta leans out of the slit's plane and alpha runs from the front horizon over the
    top to the back."""
    c = Vector(centre)
    turn = Matrix.Rotation(az, 3, "Z")
    b0 = math.asin(half / R)
    a_end = math.pi / 2 + reach

    def at_(r, beta, alpha):
        return c + turn @ Vector((r * math.cos(beta) * math.cos(alpha), r * math.sin(beta), r * math.cos(beta) * math.sin(alpha)))

    def shell(r, mat, outward, rows_, front_, back_):
        side = [b0 + (math.pi / 2 - b0) * i / rows_ for i in range(rows_ + 1)]
        betas = [-b for b in reversed(side)] + [0.0] + side
        alphas = [a_end * i / front_ for i in range(front_ + 1)] + [a_end + (math.pi - a_end) * i / back_ for i in range(1, back_ + 1)]
        pts, index = [], {}
        for j, beta in enumerate(betas):
            for i, alpha in enumerate(alphas):
                if abs(abs(beta) - math.pi / 2) < 1e-6:
                    key = ("pole", beta > 0)
                    if key not in index:
                        index[key] = len(pts)
                        pts.append(at_(r, beta, 0.0))
                    index[(j, i)] = index[key]
                else:
                    index[(j, i)] = len(pts)
                    pts.append(at_(r, beta, alpha))
        faces = []
        for j in range(len(betas) - 1):
            in_band = betas[j] >= -b0 - 1e-6 and betas[j + 1] <= b0 + 1e-6
            for i in range(len(alphas) - 1):
                if in_band and alphas[i + 1] <= a_end + 1e-6:
                    continue  # the open slit
                ring = []
                for q in (index[(j, i)], index[(j, i + 1)], index[(j + 1, i + 1)], index[(j + 1, i)]):
                    if q not in ring:
                        ring.append(q)
                if len(ring) < 3:
                    continue
                mid = sum((pts[q] for q in ring), Vector()) / len(ring)
                normal = (pts[ring[1]] - pts[ring[0]]).cross(pts[ring[-1]] - pts[ring[0]])
                if (normal.dot(mid - c) > 0) != outward:
                    ring.reverse()
                faces.append(tuple(ring))
        part(mat, pts, faces)

    shell(R, "observatory", True, rows, front, back)
    shell(R - wall, "dark", False, *lining)

    # the cut edges of the shell and the end of the slit
    fronts = [a_end * i / front for i in range(front + 1)]
    jambs = []
    for sign in (-1, 1):
        for a0, a1 in zip(fronts, fronts[1:]):
            jambs.append([at_(R, sign * b0, a0), at_(R, sign * b0, a1), at_(R - wall, sign * b0, a1), at_(R - wall, sign * b0, a0)])
    quads("metal", jambs, lambda p: turn @ Vector((0, -math.copysign(1.0, (turn.transposed() @ (p - c)).y), 0)))
    ends = [[at_(R, b_a, a_end), at_(R, b_b, a_end), at_(R - wall, b_b, a_end), at_(R - wall, b_a, a_end)] for b_a, b_b in ((-b0, 0.0), (0.0, b0))]
    quads("metal", ends, lambda p: turn @ Vector((math.sin(a_end), 0, -math.cos(a_end))))

    # shutter rails either side of the slit, from the front horizon round to the back
    rail_alphas = [math.pi * i / 22 for i in range(23)]
    h, d = 0.055, 0.035 / R
    rails = []
    for sign in (-1, 1):
        beta = sign * (b0 + 0.075 / R)
        for a0, a1 in zip(rail_alphas, rail_alphas[1:]):
            for (r0, b_0), (r1, b_1) in (((R, beta - d), (R + h, beta - d)), ((R + h, beta - d), (R + h, beta + d)), ((R + h, beta + d), (R, beta + d))):
                rails.append([at_(r0, b_0, a0), at_(r0, b_0, a1), at_(r1, b_1, a1), at_(r1, b_1, a0)])
    def rail_facing(p):
        q = turn.transposed() @ (p - c)
        beta = math.asin(max(-1.0, min(1.0, q.y / q.length)))
        centre = math.copysign(b0 + 0.075 / R, q.y)
        return (p - c).normalized() + turn @ Vector((0, math.copysign(1.0, beta - centre), 0))

    quads("metal_dark", rails, rail_facing)

    # the upper shutter rolled back over the rear, and the lower windscreen half raised
    s_alphas = [a_end + 0.04 + (min(math.pi - 0.12, a_end + 1.0) - a_end - 0.04) * i / 10 for i in range(11)]
    bs = b0 + 0.035 / R
    shutter = []
    for a0, a1 in zip(s_alphas, s_alphas[1:]):
        shutter.append([at_(R + 0.05, -bs, a0), at_(R + 0.05, -bs, a1), at_(R + 0.05, bs, a1), at_(R + 0.05, bs, a0)])
        for sign in (-1, 1):
            shutter.append([at_(R + 0.005, sign * bs, a0), at_(R + 0.005, sign * bs, a1), at_(R + 0.05, sign * bs, a1), at_(R + 0.05, sign * bs, a0)])
    for a_ in (s_alphas[0], s_alphas[-1]):
        shutter.append([at_(R + 0.005, -bs, a_), at_(R + 0.05, -bs, a_), at_(R + 0.05, bs, a_), at_(R + 0.005, bs, a_)])
    shutter_mid = at_(R + 0.03, 0.0, (s_alphas[0] + s_alphas[-1]) / 2)
    quads("white", shutter, lambda p: (p - c).normalized() * 0.4 + (p - shutter_mid).normalized())
    screen = [[at_(R - wall * 0.5, -b0, a0), at_(R - wall * 0.5, -b0, a1), at_(R - wall * 0.5, b0, a1), at_(R - wall * 0.5, b0, a0)] for a0, a1 in ((0.0, 0.16), (0.16, 0.32))]
    quads("white", screen, lambda p: p - c)

    if not seams:
        return

    # panel seams: three rings and sixteen ribs, broken where the slit and its rails run
    def clear(e, phi):
        x, y, z = math.cos(e) * math.cos(phi - az), math.cos(e) * math.sin(phi - az), math.sin(e)
        return not (abs(y) * R < half + 0.13 and math.atan2(z, x) <= a_end + 0.06)

    def on_dome(e, phi, r=R + 0.012):
        return c + Vector((r * math.cos(e) * math.cos(phi), r * math.cos(e) * math.sin(phi), r * math.sin(e)))

    strips = []
    w = 0.028 / R
    for e in (0.5, 1.0):
        steps = 56
        for s in range(steps):
            p0, p1 = s / steps * math.tau, (s + 1) / steps * math.tau
            if clear(e, p0) and clear(e, p1):
                strips.append([on_dome(e - w, p0), on_dome(e - w, p1), on_dome(e + w, p1), on_dome(e + w, p0)])
    for k in range(12):
        phi = az + (k + 0.5) / 12 * math.tau
        es = [0.03 + 1.36 * i / 9 for i in range(10)]
        for e0, e1 in zip(es, es[1:]):
            if clear(e0, phi) and clear(e1, phi):
                dp0, dp1 = w / math.cos(e0), w / math.cos(e1)
                strips.append([on_dome(e0, phi - dp0), on_dome(e1, phi - dp1), on_dome(e1, phi + dp1), on_dome(e0, phi + dp0)])
    quads("metal", strips, lambda p: p - c)


def railing_posts(points, z0, z1):
    for p in points:
        obs.cyl("metal", o, fr, (p.x, p.y, z0), (p.x, p.y, z1), 0.028, seg=5)


# plinth: a coursed stone octagon, deep enough to sit on the crest wherever the ground falls away
obs.cyl("stone", o, fr, (0, 0, -1.4), (0, 0, 0.06), 3.2, seg=16)
obs.cyl("stone_light", o, fr, (0, 0, 0.06), (0, 0, 0.25), 3.26, seg=16)
obs.cyl("stone_light", o, fr, (0, 0, -0.62), (0, 0, -0.52), 3.24, seg=16)

# drum, rotating skirt and dome
FLOOR, BASE, R_DOME = 2.92, 3.1, 2.35
SLIT = CAM + math.radians(28.0)
open_cylinder("observatory", (0, 0), 2.2, 0.25, BASE, 40)
obs.cyl("metal_dark", o, fr, (0, 0, 1.52), (0, 0, 1.6), 2.225, seg=40)
for s in range(16):
    a = SLIT + (s + 0.5) / 16 * math.tau
    obs.box("metal", o, fr + a, (2.208, 0, 1.0), (0.025, 0.045, 1.5))
    obs.box("metal", o, fr + a, (2.208, 0, 2.3), (0.025, 0.045, 1.35))
obs.cyl("metal_dark", o, fr, (0, 0, BASE - 0.13), (0, 0, BASE + 0.12), R_DOME + 0.04, seg=48)
for s in range(24):
    a = s / 24 * math.tau
    obs.box("metal", o, fr + a, (R_DOME + 0.05, 0, BASE - 0.13), (0.06, 0.08, 0.05))
slit_dome((0, 0, BASE), R_DOME, SLIT, 0.55, 0.3)
disc("wood_dark", (0, 0), 2.19, FLOOR + 0.005, 24)

# the telescope on its fork, aimed out of the slit
el = math.radians(50.0)
tube_dir = Vector((math.cos(el) * math.cos(SLIT), math.cos(el) * math.sin(SLIT), math.sin(el)))
tube_up = Vector((-math.sin(el) * math.cos(SLIT), -math.sin(el) * math.sin(SLIT), math.cos(el)))
pivot = Vector((0, 0, 3.85))
obs.cyl("metal_dark", o, fr, (0, 0, FLOOR), (0, 0, 3.32), 0.3, 0.24, seg=12)
obs.box("white", o, fr + SLIT, (0, 0, 3.37), (0.42, 1.0, 0.1))
for side in (-1, 1):
    obs.box("white", o, fr + SLIT, (0, side * 0.43, 3.62), (0.3, 0.1, 0.52))
obs.cyl("white", o, fr, pivot - tube_dir * 0.95, pivot + tube_dir * 1.4, 0.3, seg=16)
obs.cyl("metal_dark", o, fr, pivot + tube_dir * 1.4, pivot + tube_dir * 1.56, 0.33, seg=16)
obs.cyl("metal_dark", o, fr, pivot - tube_dir * 1.08, pivot - tube_dir * 0.95, 0.24, seg=12)
obs.cyl("metal_dark", o, fr, pivot - tube_dir * 0.18, pivot + tube_dir * 0.16, 0.32, seg=16)
obs.cyl("metal", o, fr, pivot + tube_up * 0.4 - tube_dir * 0.1, pivot + tube_up * 0.4 + tube_dir * 0.75, 0.06, seg=8)

# drum windows facing the last camera
for a in (CAM - math.radians(22.0), CAM + math.radians(10.0)):
    obs.box("glass", o, fr + a, (2.21, 0, 2.05), (0.04, 0.46, 0.62))
    for dz in (-0.34, 0.34):
        obs.box("metal_dark", o, fr + a, (2.23, 0, 2.05 + dz), (0.06, 0.56, 0.06))
    for dy in (-0.26, 0.26):
        obs.box("metal_dark", o, fr + a, (2.23, dy, 2.05), (0.06, 0.06, 0.74))
    obs.box("stone_light", o, fr + a, (2.27, 0, 1.68), (0.16, 0.62, 0.06))
    obs.box("snow", o, fr + a, (2.27, 0, 1.73), (0.13, 0.56, 0.04))

# control building: walls, a stone footing and a roof terrace level with the catwalk
ANNEX = CAM + math.radians(100.0)
AR = fr + ANNEX
AF = Matrix.Rotation(ANNEX, 3, "Z")


SIDE = -1.0  # turns the front (+v in these plans) towards the last camera


def annex(p):
    """Summit-local point from control-building coordinates (u out from the dome, v to its front)."""
    return AF @ Vector((p[0], SIDE * p[1], p[2]))


def block(mat, u0, u1, v0, v1, z0, z1):
    v0, v1 = sorted((SIDE * v0, SIDE * v1))
    obs.box(mat, o, AR, ((u0 + u1) / 2, (v0 + v1) / 2, (z0 + z1) / 2), (u1 - u0, v1 - v0, z1 - z0))


WALL_V, WALL_U, TERRACE = 1.75, 5.4, FLOOR - 0.01
block("stone", 1.3, WALL_U + 0.15, -WALL_V - 0.12, WALL_V + 0.12, -1.6, 0.25)
block("plaster", 1.3, WALL_U, -WALL_V, WALL_V, 0.25, TERRACE - 0.09)
block("stone", 1.3, WALL_U + 0.04, -WALL_V - 0.04, WALL_V + 0.04, 0.25, 0.72)
block("stone_light", 1.3, WALL_U + 0.2, -1.95, 1.95, TERRACE - 0.09, TERRACE)
# quoins: long and short blocks alternating up both outer corners
for v in (-1, 1):
    for k in range(4):
        z0 = 0.76 + k * 0.48
        side_len, end_len = (0.44, 0.26) if k % 2 == 0 else (0.26, 0.44)
        lo, hi = (WALL_V - 0.02, WALL_V + 0.05) if v > 0 else (-WALL_V - 0.05, -WALL_V + 0.02)
        block("stone_light", WALL_U - side_len, WALL_U + 0.05, lo, hi, z0, z0 + 0.42)
        e0, e1 = (WALL_V - end_len, WALL_V + 0.05) if v > 0 else (-WALL_V - 0.05, -WALL_V + end_len)
        block("stone_light", WALL_U - 0.02, WALL_U + 0.05, e0, e1, z0, z0 + 0.42)

def facade(mat, face, a0, a1, out0, out1, z0, z1):
    """A box on one face of the control building: along the wall, out from it and up."""
    axis, sign, plane = face
    p0, p1 = sorted((plane + sign * out0, plane + sign * out1))
    if axis == "v":
        block(mat, a0, a1, p0, p1, z0, z1)
    else:
        block(mat, p0, p1, a0, a1, z0, z1)


FRONT, BACK, END = ("v", 1, WALL_V), ("v", -1, -WALL_V), ("u", 1, WALL_U)


def window(face, a, z0, w=0.78, h=0.86, mat="glass"):
    z1 = z0 + h
    facade(mat, face, a - w / 2, a + w / 2, -0.01, 0.015, z0, z1)
    for b0, b1 in ((a - w / 2 - 0.07, a - w / 2), (a + w / 2, a + w / 2 + 0.07)):
        facade("wood_dark", face, b0, b1, 0.0, 0.07, z0 - 0.07, z1 + 0.07)
    facade("wood_dark", face, a - w / 2, a + w / 2, 0.0, 0.07, z1, z1 + 0.07)
    facade("wood_dark", face, a - 0.025, a + 0.025, 0.0, 0.045, z0, z1)
    facade("wood_dark", face, a - w / 2, a + w / 2, 0.0, 0.045, z0 + h * 0.62, z0 + h * 0.62 + 0.045)
    facade("stone_light", face, a - w / 2 - 0.13, a + w / 2 + 0.13, 0.0, 0.17, z0 - 0.14, z0 - 0.07)
    facade("snow", face, a - w / 2 - 0.08, a + w / 2 + 0.08, 0.01, 0.16, z0 - 0.07, z0 - 0.03)


# the door with its canopy, lamp and steps on the front
DOOR = 2.85
facade("wood_dark", FRONT, DOOR - 0.46, DOOR + 0.46, -0.01, 0.04, 0.27, 2.3)
for b0, b1 in ((DOOR - 0.54, DOOR - 0.46), (DOOR + 0.46, DOOR + 0.54)):
    facade("metal_dark", FRONT, b0, b1, 0.0, 0.08, 0.25, 2.38)
facade("metal_dark", FRONT, DOOR - 0.54, DOOR + 0.54, 0.0, 0.08, 2.3, 2.38)
facade("window_soft", FRONT, DOOR - 0.17, DOOR + 0.17, 0.04, 0.05, 1.55, 2.0)
for z in (0.7, 1.25):
    facade("metal_dark", FRONT, DOOR - 0.4, DOOR + 0.4, 0.04, 0.06, z, z + 0.04)
facade("metal", FRONT, DOOR + 0.3, DOOR + 0.38, 0.04, 0.1, 1.18, 1.22)
facade("metal_dark", FRONT, DOOR - 0.8, DOOR + 0.8, 0.0, 0.95, 2.52, 2.58)
facade("snow", FRONT, DOOR - 0.75, DOOR + 0.75, 0.03, 0.9, 2.58, 2.66)
for b in (DOOR - 0.7, DOOR + 0.7):
    p_wall = annex((b, WALL_V, 2.1))
    p_edge = annex((b, WALL_V + 0.88, 2.52))
    obs.cyl("metal_dark", o, fr, p_wall, p_edge, 0.025, seg=5)
facade("metal_dark", FRONT, DOOR + 0.66, DOOR + 0.78, 0.0, 0.05, 2.0, 2.16)
facade("lantern", FRONT, DOOR + 0.67, DOOR + 0.77, 0.05, 0.15, 1.9, 2.04)
facade("metal_dark", FRONT, DOOR + 0.66, DOOR + 0.78, 0.04, 0.16, 2.04, 2.07)
facade("stone_light", FRONT, DOOR - 0.68, DOOR + 0.68, 0.0, 0.62, -0.5, 0.12)
facade("stone_light", FRONT, DOOR - 0.62, DOOR + 0.62, 0.0, 0.34, 0.12, 0.25)
facade("snow", FRONT, DOOR + 0.2, DOOR + 0.66, 0.36, 0.6, 0.12, 0.17)

window(FRONT, 4.25, 1.15, mat="window_soft")
window(BACK, 3.4, 1.15)
window(BACK, 4.4, 1.15)
window(END, 0.45, 1.15)
facade("metal_dark", END, -1.15, -0.5, 0.0, 0.05, 1.5, 1.9)
for k in range(5):
    facade("metal", END, -1.12, -0.53, 0.05, 0.08, 1.54 + k * 0.075, 1.57 + k * 0.075)

# catwalk round the dome, joined to the terrace, with one railing round both
GAP = math.asin(1.88 / 2.95)
cw0, cw1 = ANNEX + GAP - 0.03, ANNEX + math.tau - GAP + 0.03
steps = 44
ring_pts, faces = [], []
for s in range(steps + 1):
    a = cw0 + (cw1 - cw0) * s / steps
    for r, z in ((2.2, FLOOR), (3.0, FLOOR), (3.0, FLOOR - 0.09), (2.2, FLOOR - 0.09)):
        ring_pts.append(polar(a, r, z))
for s in range(steps):
    i, j = s * 4, (s + 1) * 4
    faces += [(i, i + 1, j + 1, j), (i + 1, i + 2, j + 2, j + 1), (i + 2, i + 3, j + 3, j + 2)]
faces += [(3, 2, 1, 0), (steps * 4, steps * 4 + 1, steps * 4 + 2, steps * 4 + 3)]
part("metal_dark", ring_pts, faces)
for s in range(12):
    a = cw0 + (cw1 - cw0) * (s + 0.5) / 12
    obs.cyl("metal_dark", o, fr, polar(a, 2.2, FLOOR - 0.75), polar(a, 2.85, FLOOR - 0.09), 0.03, seg=4)

arc = [polar(cw0 + (cw1 - cw0) * s / 40 + 0.03 - 0.06 * s / 40, 2.95) for s in range(41)]
loop = arc + [annex((WALL_U + 0.12, -1.88, 0)), annex((WALL_U + 0.12, 1.88, 0))]
for z in (FLOOR + 0.5, FLOOR + 0.98):
    polyline_tube("metal", [Vector((p.x, p.y, z)) for p in loop], 0.022, sides=4, closed=True)
railing_posts(arc[::4], FLOOR, FLOOR + 1.0)
for u in (2.9, 3.8, 4.7):
    railing_posts([annex((u, 1.88, 0)), annex((u, -1.88, 0))], FLOOR, FLOOR + 1.0)
railing_posts([annex((WALL_U + 0.12, v, 0)) for v in (-1.88, -0.6, 0.6, 1.88)], FLOOR, FLOOR + 1.0)

# a ladder up to the catwalk on the camera's side
LADDER = CAM - math.radians(35.0)
for side in (-0.24, 0.24):
    p = polar(LADDER, 3.1) + polar(LADDER + math.pi / 2, side)
    obs.cyl("metal", o, fr, (p.x, p.y, 0.0), (p.x, p.y, FLOOR + 1.0), 0.025, seg=5)
for k in range(9):
    z = 0.32 + k * 0.31
    obs.box("metal", o, fr + LADDER, (3.1, 0, z), (0.035, 0.48, 0.035))
obs.box("metal_dark", o, fr + LADDER, (3.06, 0, FLOOR - 0.04), (0.14, 0.58, 0.07))

# second, smaller dome on the terrace
small = annex((4.45, 0.35, 0))
open_cylinder("observatory", (small.x, small.y), 0.78, TERRACE, TERRACE + 0.55, 24)
obs.cyl("metal_dark", o, fr, (small.x, small.y, TERRACE + 0.5), (small.x, small.y, TERRACE + 0.6), 0.84, seg=28)
slit_dome((small.x, small.y, TERRACE + 0.56), 0.82, CAM + math.radians(8.0), 0.16, 0.2, rows=6, front=10, back=6, wall=0.06, seams=False, lining=(4, 8, 4))

# weather station: anemometer, vane, radiation shield and a sensor box on a mast
mast = annex((3.45, 1.32, 0))
TOP = TERRACE + 2.35
obs.cyl("metal", o, fr, (mast.x, mast.y, TERRACE), (mast.x, mast.y, TOP), 0.035, seg=6)
arm = annex((0.5, 0, 0)) - annex((0, 0, 0))
obs.cyl("metal", o, fr, (mast.x - arm.x, mast.y - arm.y, TOP - 0.15), (mast.x + arm.x, mast.y + arm.y, TOP - 0.15), 0.02, seg=4)
cups = Vector((mast.x + arm.x, mast.y + arm.y, TOP - 0.15))
obs.cyl("metal", o, fr, cups, cups + Vector((0, 0, 0.22)), 0.012, seg=4)
for k in range(3):
    a = k / 3 * math.tau
    tip = cups + Vector((math.cos(a) * 0.18, math.sin(a) * 0.18, 0.2))
    obs.cyl("metal", o, fr, cups + Vector((0, 0, 0.2)), tip, 0.008, seg=3)
    obs.ico("metal_dark", o, fr, tip, 0.045, (1.0, 1.0, 0.8), sub=1)
vane = Vector((mast.x - arm.x, mast.y - arm.y, TOP - 0.15))
obs.cyl("metal", o, fr, vane, vane + Vector((0, 0, 0.2)), 0.012, seg=4)
v_dir = 0.6
obs.box("metal_dark", o, fr + v_dir, (*(Matrix.Rotation(-v_dir, 3, "Z") @ vane)[:2], vane.z + 0.22), (0.5, 0.025, 0.025))
obs.box("metal_dark", o, fr + v_dir, (*(Matrix.Rotation(-v_dir, 3, "Z") @ vane + Vector((-0.24, 0, 0)))[:2], vane.z + 0.25), (0.1, 0.01, 0.16))
for k in range(5):
    obs.cyl("white", o, fr, (mast.x, mast.y, TERRACE + 1.4 + k * 0.05), (mast.x, mast.y, TERRACE + 1.42 + k * 0.05), 0.12 - k * 0.008, seg=10)
obs.box("white", o, AR, (*(AF.transposed() @ Vector((mast.x, mast.y, 0)) + Vector((0, 0.12, 0)))[:2], TERRACE + 0.95), (0.18, 0.12, 0.26))
obs.box("solar", o, AR, (*(AF.transposed() @ Vector((mast.x, mast.y, 0)) + Vector((0, -0.2, 0)))[:2], TERRACE + 1.85), (0.36, 0.03, 0.28), tilt=("X", 0.5))

# solar panels along the back of the terrace and a vent pipe
for u in (3.95, 4.85):
    block("metal_dark", u - 0.03, u + 0.03, -1.45, -1.39, TERRACE, TERRACE + 0.35)
    obs.box("solar", o, AR, (u, SIDE * -1.3, TERRACE + 0.42), (0.82, 0.55, 0.03), tilt=("X", SIDE * 0.55))
vent = annex((5.1, 1.45, 0))
obs.cyl("metal", o, fr, (vent.x, vent.y, TERRACE), (vent.x, vent.y, TERRACE + 0.7), 0.07, seg=8)
obs.cyl("metal", o, fr, (vent.x, vent.y, TERRACE + 0.72), (vent.x, vent.y, TERRACE + 0.84), 0.15, 0.02, seg=8)

# lattice mast with the beacon at the far corner, guyed to the terrace
foot = annex((2.72, -1.45, 0))
MAST_TOP = TERRACE + 4.2
legs = []
for k in range(3):
    a = ANNEX + k / 3 * math.tau
    legs.append([Vector((foot.x + math.cos(a) * rr, foot.y + math.sin(a) * rr, z)) for rr, z in ((0.22, TERRACE), (0.08, MAST_TOP))])
for leg in legs:
    polyline_tube("metal", leg, 0.022, sides=4)
levels = 5
for lv in range(levels + 1):
    t = lv / levels
    ring = [leg[0].lerp(leg[1], t) for leg in legs]
    if lv > 0:
        polyline_tube("metal", ring, 0.01, sides=3, closed=True)
    if lv < levels:
        t2 = (lv + 1) / levels
        nxt = [leg[0].lerp(leg[1], t2) for leg in legs]
        for k in range(3):
            polyline_tube("metal", [ring[k], nxt[(k + 1) % 3]], 0.008, sides=3)
for z, k in ((MAST_TOP - 1.4, 0), (MAST_TOP - 0.8, 1)):
    t = (z - TERRACE) / (MAST_TOP - TERRACE)
    p = legs[k][0].lerp(legs[k][1], t)
    out = (p - Vector((foot.x, foot.y, p.z))).normalized()
    obs.box("white", o, fr + math.atan2(out.y, out.x), (*(Matrix.Rotation(-math.atan2(out.y, out.x), 3, "Z") @ (p + out * 0.06))[:2], z), (0.06, 0.22, 0.5))
for target in (annex((4.9, -1.9, 0)), annex((4.6, 1.9, 0)), annex((2.3, 1.9, 0))):
    polyline_tube("rope", [Vector((foot.x, foot.y, MAST_TOP - 1.0)), Vector((target.x, target.y, TERRACE + 0.02))], 0.006, sides=3)
bm = bmesh.new()
pw.add_ico(bm, (0, 0, 0), 0.12, 1)
beacon = pw.bm_object("beacon", bm, M["beacon"])
beacon.location = tuple(here((foot.x, foot.y, MAST_TOP + 0.1)))
obs.cyl("metal_dark", o, fr, (foot.x, foot.y, MAST_TOP - 0.05), (foot.x, foot.y, MAST_TOP + 0.02), 0.09, seg=8)

# snow on the terrace and against the walls
block("snow", 2.45, 4.0, 0.55, 1.7, TERRACE, TERRACE + 0.06)
block("snow", WALL_U - 0.4, WALL_U - 0.05, -0.2, 1.1, TERRACE, TERRACE + 0.05)
for u_, v_, r_ in ((WALL_U + 0.35, 0.6, 0.75), (4.1, 2.15, 0.6), (3.1, -2.2, 0.7), (WALL_U + 0.3, -1.3, 0.55)):
    obs.ico("snow", o, fr, annex((u_, v_, 0.0)), r_, (1.7, 1.0, 0.36), sub=1)
for a, r_ in ((CAM - 0.95, 0.85), (CAM + 0.15, 0.6), (CAM + math.pi + 0.9, 0.8), (CAM - 1.6, 0.7)):
    obs.ico("snow", o, fr, polar(a, 3.35, 0.02), r_, (1.6, 1.0, 0.35), sub=1)

# Everything but the white shell is shaded flat in the browser, which ignores the normals, so
# exporting it smooth only lets the faces share their corners and keeps the file small.
obs.finish(smooth=tuple(obs.meshes))

# around the summit: a trig pillar, a dish, the summit cairn and prayer flags off the catwalk
pillar = at("summit", *polar(math.radians(62.0), 5.4).xy)
props.box("white", pillar, 0.0, (0, 0, 0.55), (0.4, 0.4, 1.1))
props.cyl("metal", pillar, 0.0, (0, 0, 1.1), (0, 0, 1.16), 0.12, seg=10)
props.box("bronze", pillar, 0.0, (0, 0.205, 0.75), (0.2, 0.01, 0.14))

dish_at = polar(math.radians(36.0), 4.9)
ground = surface(*here(dish_at).xy) - oz
obs_dish = Kit("observatory_dish")
dish_az, dish_el = math.radians(36.0) + 0.4, math.radians(32.0)
axis = Vector((math.cos(dish_el) * math.cos(dish_az), math.cos(dish_el) * math.sin(dish_az), math.sin(dish_el)))
d_u = axis.cross(Vector((0, 0, 1))).normalized()
d_v = d_u.cross(axis).normalized()
hub = Vector((dish_at.x, dish_at.y, ground + 1.35))
obs_dish.cyl("metal_dark", o, fr, (dish_at.x, dish_at.y, ground - 0.2), (dish_at.x, dish_at.y, ground + 1.2), 0.06, seg=8)
obs_dish.cyl("metal_dark", o, fr, (dish_at.x, dish_at.y, ground + 1.2), hub - axis * 0.05, 0.05, seg=6)
D_R, D_DEPTH = 0.62, 0.16
rings = [[hub + axis * (0.06 + D_DEPTH * (k / 4) ** 2) + (d_u * math.cos(s / 16 * math.tau) + d_v * math.sin(s / 16 * math.tau)) * D_R * k / 4 for s in range(16)] for k in range(1, 5)]
front_pts = [hub + axis * 0.06] + [p for ring in rings for p in ring]
front_faces = [(0, 1 + (s + 1) % 16, 1 + s) for s in range(16)]
for k in range(3):
    for s in range(16):
        a_, b_ = 1 + k * 16 + s, 1 + k * 16 + (s + 1) % 16
        front_faces.append((a_, b_, b_ + 16, a_ + 16)[::-1])
bm = obs_dish.bm("white")
vs = [bm.verts.new(p) for p in front_pts]
for f in front_faces:
    face = bm.faces.new([vs[i] for i in f])
    face.normal_update()
    if face.normal.dot(axis) < 0:
        face.normal_flip()
back_tip = bm.verts.new(hub - axis * 0.06)
for s in range(16):
    face = bm.faces.new((vs[49 + s], vs[49 + (s + 1) % 16], back_tip))
    face.normal_update()
    if face.normal.dot(axis) > 0:
        face.normal_flip()
Kit._place(bm, vs + [back_tip], o, fr)
focus = hub + axis * (0.06 + D_R ** 2 / (4 * D_DEPTH) * 0.62)
for s in range(3):
    rim = rings[-1][s * 16 // 3]
    obs_dish.cyl("metal", o, fr, rim, focus, 0.012, seg=3)
obs_dish.cyl("metal_dark", o, fr, focus - axis * 0.08, focus + axis * 0.05, 0.06, seg=8)
obs_dish.finish(smooth=tuple(obs_dish.meshes))

cairn(at("summit", *polar(math.radians(300.0), 5.6).xy), 0.0, 1.1)
flag_pole(at("summit", *polar(math.radians(300.0), 5.6).xy) + Vector((0, 0, 1.05)), fr, "fabric_blue", 1.4)
flags_a = here(polar(CAM + math.radians(30.0), 2.95, FLOOR + 1.0))
flags_post = at("summit", *polar(CAM + math.radians(62.0), 7.4).xy)
props.cyl("metal", flags_post, 0.0, (0, 0, -0.2), (0, 0, 2.0), 0.03, seg=6)
prayer_flags(flags_a, flags_post + Vector((0, 0, 1.95)), 12, 0.45)

props.finish(smooth=("fabric_blue",))

pw.empty("water", (0.0, 0.0, WATER))
pw.empty("anchor_lake", (LAKE[0], LAKE[1], WATER))

pw.export_glb(args.out)
