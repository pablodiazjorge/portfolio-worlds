"""ATLAS: a low-poly alpine valley with a trail that climbs from base camp to a summit observatory.

Blender axes: X east, Y north, Z up (the glTF exporter converts to Y up).
The camera rig in the app reads the `anchor_*` empties and the `water` empty; `smoke_*` empties
mark chimneys and campfires for the app's smoke.
"""

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


# --- distant ring of mountains for the horizon ---------------------------------
ring_verts, ring_faces, ring_colors = [], [], []
SEG, ROWS = 96, 5
for r in range(ROWS):
    radius = 300.0 + r * 70.0
    for s in range(SEG):
        a = s / SEG * math.tau
        x, y = math.cos(a) * radius, math.sin(a) * radius
        ridge = noise.ridged_multi_fractal(Vector((math.cos(a) * 2.2, math.sin(a) * 2.2, r * 0.7)), 0.9, 2.0, 4, 1.0, 2.0)
        z = (0.0 if r == 0 else 30.0 + ridge * 55.0 + r * 12.0) if r < ROWS - 1 else 10.0
        ring_verts.append((x, y, z))
        tone = Vector(pw.hex_color("#6b6f8c")[:3]).lerp(Vector(pw.hex_color("#e9e7ee")[:3]), pw.smoothstep(95.0, 130.0, z))
        ring_colors.append((tone.x, tone.y, tone.z, 1.0))
for r in range(ROWS - 1):
    for s in range(SEG):
        a = r * SEG + s
        b = r * SEG + (s + 1) % SEG
        ring_faces += [(a, b, b + SEG), (a, b + SEG, a + SEG)]
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
    "solar": pw.material("solar", "#1d2f55", 0.3, 0.4),
    "white": pw.material("white_paint", "#eeeef0", 0.5),
    "sign": pw.material("sign_yellow", "#f3c22f", 0.6),
    "marker_red": pw.material("marker_red", "#d23b2f", 0.6),
    "snow": pw.material("snow_block", "#e6eaf1", 0.8),
    "root": pw.material("root", "#6e5038", 0.95),
    "bush": pw.material("bush", "#3f6a3c", 0.9),
    "bush_light": pw.material("bush_light", "#5f8248", 0.9),
    "snow_print": pw.material("snow_print", "#a9b2c4", 0.9),
    "dark": pw.material("observatory_slit", "#1d2030", 0.6),
    "observatory": pw.material("observatory_white", "#eeeef0", 0.45, 0.05),
    "glow_fire": pw.material("fire_glow", "#ffb24a", 1.0, emission="#ff9a3a", emission_strength=6.0),
    "ember": pw.material("ember", "#ff7a2a", 1.0, emission="#ff6a1a", emission_strength=4.0),
    "lantern": pw.material("lantern_glass", "#ffe2a8", 1.0, emission="#ffcf7a", emission_strength=5.0),
    "window": pw.material("window_warm", "#ffd9a0", 1.0, emission="#ffc777", emission_strength=3.0),
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


def a_frame_tent(origin, rot, color, size=1.0):
    w, l, h = 1.25 * size, 1.9 * size, 1.0 * size
    k = props
    # a muted groundsheet that only peeks out round the tent; a dark one read as a hole in the ground
    k.box("groundsheet", origin, rot, (0, 0, 0.01), (w + 0.16, l + 0.2, 0.02))
    over = 0.12 * size
    for side in (-1, 1):
        k.poly(color, origin, rot, [(side * w / 2, -l / 2, 0.02), (side * w / 2, l / 2, 0.02), (0, l / 2 + over, h), (0, -l / 2 - over, h)][::side])
    k.poly(color, origin, rot, [(w / 2, l / 2 - 0.02, 0.02), (-w / 2, l / 2 - 0.02, 0.02), (0, l / 2 - 0.02, h)])
    door = 0.34 * size
    k.poly("fabric_dark", origin, rot, [(-door, -l / 2 + 0.02, 0.02), (door, -l / 2 + 0.02, 0.02), (0, -l / 2 + 0.02, h * 0.82)])
    k.poly(color, origin, rot, [(-w / 2, -l / 2, 0.02), (-door, -l / 2, 0.02), (0, -l / 2, h * 0.82), (0, -l / 2, h)][::-1])
    k.poly(color, origin, rot, [(door, -l / 2, 0.02), (w / 2, -l / 2, 0.02), (0, -l / 2, h), (0, -l / 2, h * 0.82)][::-1])
    # flaps tied back on each side of the door
    for side in (-1, 1):
        k.poly(color, origin, rot, [(side * door, -l / 2 - 0.01, 0.02), (side * (door + 0.22), -l / 2 - 0.2, 0.05), (side * 0.06, -l / 2 - 0.02, h * 0.7)][::side])
    # ridge pole ends, guy lines and stakes
    for end in (-1, 1):
        top = (0, end * (l / 2 + over), h)
        stake = (0, end * (l / 2 + 0.75 * size), 0.02)
        k.cyl("rope", origin, rot, top, stake, 0.008, seg=4)
        k.cyl("metal", origin, rot, (stake[0], stake[1], -0.05), (stake[0], stake[1], 0.07), 0.015, seg=4)
        k.cyl("wood_dark", origin, rot, (0, end * (l / 2 + over * 0.6), 0), (0, end * (l / 2 + over * 0.6), h + 0.05), 0.02, seg=5)
    for side in (-1, 1):
        for end in (-0.3, 0.3):
            anchor = (side * w * 0.26, end * l, h * 0.5)
            stake = (side * (w / 2 + 0.55 * size), end * l * 1.15, 0.02)
            k.cyl("rope", origin, rot, anchor, stake, 0.007, seg=4)
            k.cyl("metal", origin, rot, (stake[0], stake[1], -0.05), (stake[0], stake[1], 0.07), 0.014, seg=4)


def dome_tent(origin, rot, color, r=0.85):
    k = props
    k.box("groundsheet", origin, rot, (0, 0, 0.01), (2 * r + 0.08, 2 * r + 0.08, 0.02))
    k.dome(color, origin, rot, (0, 0, 0.02), r, squash=0.72, seg=14)
    # crossing poles
    for angle in (math.pi / 4, -math.pi / 4):
        pts = []
        for s in range(9):
            t = s / 8 * math.pi
            pts.append(Matrix.Rotation(angle, 3, "Z") @ Vector((math.cos(t) * r * 1.01, 0, 0.02 + math.sin(t) * r * 0.73)))
        for a, b in zip(pts, pts[1:]):
            k.cyl("metal_dark", origin, rot, a, b, 0.016, seg=4)
    # vestibule over the door
    v = 0.55 * r
    k.poly(color, origin, rot, [(-v, -r * 0.55, 0.02), (0, -r - 0.42, 0.02), (0, -r * 0.62, r * 0.6)])
    k.poly(color, origin, rot, [(0, -r - 0.42, 0.02), (v, -r * 0.55, 0.02), (0, -r * 0.62, r * 0.6)])
    k.poly("fabric_dark", origin, rot, [(-v * 0.55, -r * 0.6, 0.03), (v * 0.55, -r * 0.6, 0.03), (0, -r * 0.64, r * 0.5)])
    for side in (-1, 1):
        stake = (side * (r + 0.45), 0.25, 0.02)
        k.cyl("rope", origin, rot, (side * r * 0.62, 0.15, r * 0.45), stake, 0.007, seg=4)
        k.cyl("metal", origin, rot, (stake[0], stake[1], -0.05), (stake[0], stake[1], 0.07), 0.014, seg=4)


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
    """Mountain refuge: stone base, timber walls, pitched roof, chimney and lit windows."""
    k = props
    W, L, H = 3.6, 2.8, 1.9
    k.box("stone", origin, rot, (0, 0, 0.25), (W + 0.3, L + 0.3, 0.5))
    k.box("wood", origin, rot, (0, 0, 0.5 + H / 2), (W, L, H))
    for z in range(1, 7):
        for side in (-1, 1):
            k.box("wood_dark", origin, rot, (0, side * (L / 2 + 0.005), 0.5 + z * H / 7), (W + 0.02, 0.012, 0.03))
            k.box("wood_dark", origin, rot, (side * (W / 2 + 0.005), 0, 0.5 + z * H / 7), (0.012, L + 0.02, 0.03))
    ridge = 0.5 + H + 1.2
    for side in (-1, 1):
        k.poly("wood", origin, rot, [(side * W / 2, -L / 2, 0.5 + H), (side * W / 2, L / 2, 0.5 + H), (side * W / 2, 0, ridge)][::side])
    pitch = math.atan2(1.2, L / 2)
    for side in (-1, 1):
        k.box("roof", origin, rot, (0, side * (L / 4 + 0.05), 0.5 + H + 0.62), (W + 0.6, L / 2 / math.cos(pitch) + 0.45, 0.1), tilt=("X", -side * pitch))
    k.box("roof", origin, rot, (0, 0, ridge + 0.04), (W + 0.62, 0.16, 0.08))
    # chimney with smoke
    k.box("stone_light", origin, rot, (W * 0.25, L * 0.15, ridge), (0.45, 0.45, 1.2))
    k.box("stone", origin, rot, (W * 0.25, L * 0.15, ridge + 0.62), (0.55, 0.55, 0.08))
    chimney_top = origin + Matrix.Rotation(rot, 3, "Z") @ Vector((W * 0.25, L * 0.15, ridge + 0.75))
    pw.empty("smoke_hut", chimney_top)
    # door, windows and a small porch on the front (-Y)
    k.box("wood_dark", origin, rot, (-0.6, -L / 2 - 0.02, 0.5 + 0.8), (0.75, 0.05, 1.6))
    k.box("white", origin, rot, (-0.6, -L / 2 - 0.03, 0.5 + 1.62), (0.85, 0.04, 0.06))
    for x in (0.75, 1.35):
        k.box("white", origin, rot, (x, -L / 2 - 0.02, 1.55), (0.5, 0.04, 0.55))
        k.box("window", origin, rot, (x, -L / 2 - 0.04, 1.55), (0.38, 0.03, 0.42))
    for y in (-0.5, 0.6):
        k.box("white", origin, rot, (W / 2 + 0.02, y, 1.55), (0.04, 0.5, 0.55))
        k.box("window", origin, rot, (W / 2 + 0.04, y, 1.55), (0.03, 0.38, 0.42))
    k.box("wood_light", origin, rot, (0, -L / 2 - 0.65, 0.48), (W, 1.2, 0.08))
    for x in (-W / 2 + 0.1, W / 2 - 0.1):
        k.box("wood_dark", origin, rot, (x, -L / 2 - 1.2, 1.15), (0.1, 0.1, 1.4))
    k.box("roof", origin, rot, (0, -L / 2 - 0.7, 1.95), (W + 0.3, 1.5, 0.07), tilt=("X", 0.22))
    bench(origin + Matrix.Rotation(rot, 3, "Z") @ Vector((0.9, -L / 2 - 0.55, 0.48)), rot + math.pi)
    k.box("solar", origin, rot, (-W * 0.2, L / 4 + 0.15, 0.5 + H + 0.75), (1.1, 0.8, 0.04), tilt=("X", -pitch))


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


# steps on steep stretches, edging stones and way-marks
rock_src = []
for k_ in range(3):
    bm = bmesh.new()
    pw.add_ico(bm, (0, 0, 0), 0.5, 1, (1.2, 0.9, 0.6))
    for v in bm.verts:
        v.co += Vector((rng.uniform(-0.08, 0.08), rng.uniform(-0.08, 0.08), rng.uniform(-0.05, 0.05)))
    o = pw.bm_object(f"pebble_src_{k_}", bm, M["stone_light" if k_ == 1 else "stone"])
    rock_src.append(o.data)
    bpy.data.objects.remove(o)

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
flat_src = []
for k_ in range(2):
    bm = bmesh.new()
    pw.add_ico(bm, (0, 0, 0), 1.0, 1, (1.0, 0.8, 0.22))
    o = pw.bm_object(f"cobble_src_{k_}", bm, M["stone_light" if k_ else "stone"])
    flat_src.append(o.data)
    bpy.data.objects.remove(o)
print_bm = bmesh.new()
pw.add_cone(print_bm, (0, 0, 0), 0.06, 0.06, 0.01, segments=7)
bmesh.ops.scale(print_bm, vec=Vector((1.0, 1.8, 1.0)), verts=print_bm.verts[:])
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
        # set proud of the tread, which now sits a few centimetres above the ground
        if z < 56:
            step_kit.cyl("wood", Vector((0, 0, 0)), 0.0, a + Vector((0, 0, 0.07)), b + Vector((0, 0, 0.07)), 0.06, seg=6)
        else:
            centre = Vector((p.x, p.y, z + 0.06))
            step_kit.box("stone_light", centre, math.atan2(side.y, side.x), (0, 0, 0), (TRAIL_HALF * 1.9, 0.26, 0.09))
    if k_ % 4 == 0:
        s = 1 if (k_ // 4) % 2 else -1
        q = p + side * s * (TRAIL_HALF + 0.18 + rng.uniform(0, 0.12))
        obj = bpy.data.objects.new(f"pebble_{k_}", rock_src[k_ % 3])
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


def pine_mesh(name, tiers, mat):
    """More, slimmer tiers with nine sides each, and a slight irregularity so no two rims match."""
    bark = random.Random(f"{args.seed}-{name}")
    bm = bmesh.new()
    trunk_verts = pw.add_cone(bm, (0, 0, 0), 0.09, 0.07, 0.5, segments=6)
    pw.assign_material_index(bm, trunk_verts, 1)
    z = 0.35
    scale = 4.0 / (tiers - 1)
    for k in range(tiers):
        radius = 0.64 - k * (0.46 / tiers)
        height_ = (0.9 - k * 0.12 * scale) * scale * 0.8
        vs = pw.add_cone(bm, (0, 0, z), radius, 0.02, height_, segments=9, rotation=k * 0.6)
        for v in vs:
            if v.co.z < z + height_ * 0.2:
                v.co.x *= bark.uniform(0.9, 1.08)
                v.co.y *= bark.uniform(0.9, 1.08)
                v.co.z -= bark.uniform(0.0, 0.07)
        z += height_ * 0.5
    obj = pw.bm_object(name, bm, [mat, trunk])
    return obj.data


pine_tall = pine_mesh("pine_tall", 5, foliage)
pine_round = pine_mesh("pine_round", 4, foliage_light)

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
# Boulders get their own, finer meshes: twice subdivided and dented, so they hold up close.
boulder_rng = random.Random(f"{args.seed}-boulders")
boulder_src = []
for k_ in range(3):
    bm = bmesh.new()
    pw.add_ico(bm, (0, 0, 0), 0.5, 2, (1.2, 0.95, 0.68))
    for v in bm.verts:
        dent = noise.noise(v.co * 3.1 + Vector((k_ * 7.3, 1.7, 4.2)))
        v.co *= 1.0 + 0.16 * dent + boulder_rng.uniform(-0.03, 0.03)
    o = pw.bm_object(f"boulder_src_{k_}", bm, M["stone_light" if k_ == 1 else "stone"])
    boulder_src.append(o.data)
    bpy.data.objects.remove(o)
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
grass_mat = pw.material("grass_tuft", "#7d9a52", 0.9)
grass_dry = pw.material("grass_tuft_dry", "#a7a35f", 0.9)


def tuft_mesh(name, mat):
    # Seven curved blades: a narrowing quad up to the knee, then a leaning tip. The blades draw
    # from their own generator so everything placed after them keeps its layout.
    for _ in range(10):
        rng.random()
    blade = random.Random(f"{args.seed}-{name}")
    bm = bmesh.new()
    for k in range(7):
        a = k / 7 * math.tau + blade.uniform(-0.35, 0.35)
        out = Vector((math.cos(a), math.sin(a), 0))
        side = Vector((-math.sin(a), math.cos(a), 0))
        tall = blade.uniform(0.3, 0.46)
        root = out * blade.uniform(0.0, 0.05)
        v1 = bm.verts.new(root - side * 0.032)
        v2 = bm.verts.new(root + side * 0.032)
        knee = root + out * tall * 0.16 + Vector((0, 0, tall * 0.55))
        v3 = bm.verts.new(knee + side * 0.02)
        v4 = bm.verts.new(knee - side * 0.02)
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
    obj.scale = (s, s, s)
    obj.rotation_euler = (0, 0, rng.uniform(0, math.tau))
    obj.location = (q.x, q.y, h - 0.02)
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
        obj = bpy.data.objects.new(f"scree_{name}_{k}", rock_src[k % 3])
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
        obj = bpy.data.objects.new(f"stone_{placed_stones}", rock_src[placed_stones % 3])
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
        size = scatter.uniform(0.8, 1.6)
        obj.scale = (size, size, size * scatter.uniform(0.85, 1.2))
        obj.rotation_euler = (0, 0, scatter.uniform(0, math.tau))
        obj.location = (x, y, h - 0.02)
        placed_tufts += 1
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

# Ridge: viewing deck with railing, telescope, bench and a panorama board.
rr = frame_rot("ridge")
deck = at("ridge", 0, 0)
props.box("wood_light", deck, rr, (0, 0, 0.12), (4.4, 2.6, 0.16))
for x in (-2.0, 2.0):
    for y in (-1.1, 1.1):
        props.cyl("wood_dark", deck, rr, (x, y, -0.6), (x, y, 0.1), 0.06, seg=6)
rail = [deck + Matrix.Rotation(rr, 3, "Z") @ Vector((x, 1.25, 0)) for x in (-2.1, -1.05, 0.0, 1.05, 2.1)]
railing([Vector((p.x, p.y, 0)) for p in rail])
telescope(deck + Matrix.Rotation(rr, 3, "Z") @ Vector((-1.1, 0.6, 0.2)), rr + math.pi)
bench(deck + Matrix.Rotation(rr, 3, "Z") @ Vector((0.9, -0.2, 0.2)), rr)
map_board(at("ridge", 2.9, -1.6), rr + 0.3)
signpost(at("ridge", -2.8, -1.4), rr, [(math.pi / 2, 1.7), (-math.pi / 2, 1.5)])

# Summit: observatory with a railing, summit pillar, prayer flags and a dish.
ox, oy = SITES["summit"]
oz = surface(ox, oy)
observatory = Kit("observatory")
o = Vector((ox, oy, oz))
observatory.cyl("observatory", o, 0.0, (0, 0, -0.6), (0, 0, 1.9), 2.3, seg=24)
observatory.box("stone", o, 0.0, (0, 0, -0.35), (5.4, 5.4, 0.5))
bm = bmesh.new()
bmesh.ops.create_uvsphere(bm, u_segments=28, v_segments=14, radius=2.45)
bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < -0.01], context="VERTS")
bmesh.ops.translate(bm, verts=bm.verts[:], vec=Vector((ox, oy, oz + 1.9)))
pw.bm_object("observatory_dome", bm, M["observatory"], smooth=True)
slit_rot = math.atan2(-(oy - SITES["ridge"][1]), -(ox - SITES["ridge"][0]))
for k in range(6):
    a = 0.1 + k * 0.25
    c = Vector((ox, oy, oz + 1.9)) + Matrix.Rotation(slit_rot, 3, "Z") @ Vector((math.cos(a) * 2.37, 0, math.sin(a) * 2.37))
    observatory.box("dark", c, slit_rot, (0, 0, 0), (0.12, 0.62, 0.5))
door_rot = slit_rot + math.pi * 0.85
observatory.box("window", o, door_rot, (2.28, 0, 0.55), (0.18, 0.75, 1.15))
observatory.box("metal_dark", o, door_rot, (2.3, 0, 1.18), (0.2, 0.95, 0.08))
for k in range(4):
    observatory.box("stone_light", o, door_rot, (2.7 + k * 0.3, 0, -0.45 + k * 0.12), (0.3, 1.0, 0.12))
for a in range(0, 360, 30):
    rad = math.radians(a)
    if abs(((a - math.degrees(door_rot)) + 180) % 360 - 180) < 25:
        continue
    observatory.cyl("metal", o, 0.0, (math.cos(rad) * 2.85, math.sin(rad) * 2.85, -0.1), (math.cos(rad) * 2.85, math.sin(rad) * 2.85, 0.85), 0.03, seg=5)
observatory.torus("metal", o, 0.0, (0, 0, 0.85), 2.85, 0.025, seg=48, ring=4)
observatory.finish()
bm = bmesh.new()
pw.add_cone(bm, (ox - 2.8, oy + 1.2, oz - 0.3), 0.06, 0.03, 4.2, segments=5)
pw.bm_object("antenna", bm, M["metal"])
bm = bmesh.new()
pw.add_ico(bm, (0, 0, 0), 0.12, 1)
beacon = pw.bm_object("beacon", bm, M["beacon"])
beacon.location = (ox - 2.8, oy + 1.2, oz + 3.95)
pillar = at("summit", -4.6, -1.2)
props.box("white", pillar, 0.0, (0, 0, 0.55), (0.4, 0.4, 1.1))
props.cyl("metal", pillar, 0.0, (0, 0, 1.1), (0, 0, 1.16), 0.12, seg=10)
dish = at("summit", 3.6, 2.8)
props.cyl("metal_dark", dish, 0.0, (0, 0, 0), (0, 0, 1.3), 0.05, seg=6)
props.dome("white", dish, 0.0, (0, 0, 1.25), 0.55, squash=0.35, seg=12)
flags_a = at("summit", -3.4, 2.6) + Vector((0, 0, 0.3))
prayer_flags(Vector((ox, oy, oz + 4.1)), flags_a, 12, 0.6)

props.finish(smooth=("fabric_blue",))

pw.empty("water", (0.0, 0.0, WATER))
pw.empty("anchor_lake", (LAKE[0], LAKE[1], WATER))

pw.export_glb(args.out)
