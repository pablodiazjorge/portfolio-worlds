"""ATLAS: a low-poly alpine valley with a trail that climbs from base camp to a summit observatory.

Blender axes: X east, Y north, Z up (the glTF exporter converts to Y up).
The camera rig in the app reads the `anchor_*` empties and the `water` empty.
"""

import math
import os
import random
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Vector, noise

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lib"))
import pw  # noqa: E402

args = pw.parse_args()
pw.reset(args.seed)
noise.seed_set(args.seed)

SIZE = 440.0
RES = 176
WATER = 1.2
SNOWLINE = 66.0

# Trail waypoints: (x, y, target altitude). The terrain grows a ridge whose crest follows them.
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
LAKE = (-6.0, -62.0, 26.0, 17.0)


def axis_x(y):
    return 16.0 * math.sin(y * 0.011) - 10.0 + 6.0 * math.sin(y * 0.029 + 1.3)


def catmull(points, samples_per_segment):
    """Centripetal-ish Catmull-Rom through 2D/3D tuples."""
    out = []
    pts = [points[0]] + list(points) + [points[-1]]
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = (Vector(p) for p in pts[i - 1:i + 3])
        for s in range(samples_per_segment):
            t = s / samples_per_segment
            t2, t3 = t * t, t * t * t
            out.append(
                0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3)
            )
    out.append(Vector(points[-1]))
    return out


ROUTE_SAMPLES = np.array([[p.x, p.y, p.z] for p in catmull([(x, y, alt) for _, x, y, alt in ROUTE], 90)])


def route_distance(x, y):
    """Distance on the ground plane to the trail and the trail altitude at the closest point."""
    dx = ROUTE_SAMPLES[:, 0] - x
    dy = ROUTE_SAMPLES[:, 1] - y
    d2 = dx * dx + dy * dy
    k = int(np.argmin(d2))
    return math.sqrt(float(d2[k])), float(ROUTE_SAMPLES[k, 2])


def stable_hash(text):
    return sum(ord(ch) * (i + 1) for i, ch in enumerate(text))


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
    river = 2.6 * math.exp(-((x - ax) / 4.5) ** 2)
    lx, ly, lrx, lry = LAKE
    lake = 5.0 * math.exp(-(((x - lx) / lrx) ** 2 + ((y - ly) / lry) ** 2))
    detail = noise.fractal(Vector((x * 0.045, y * 0.045, 3.1)), 0.7, 2.0, 3) * (0.8 + 0.04 * walls)
    return floor + walls + massif + summit + ends + detail - river - lake


def height(x, y):
    h = base_height(x, y)
    d, alt = route_distance(x, y)
    if d < 60.0:
        roughness = noise.ridged_multi_fractal(Vector((x * 0.05, y * 0.05, 5.0)), 1.0, 2.0, 3, 1.0, 2.0)
        crest = alt - d * 0.42 - (d * d) * 0.004 + roughness * pw.smoothstep(2.0, 14.0, d) * (2.0 + alt * 0.05)
        blend = pw.smoothstep(0.0, 1.0, (crest - h + 6.0) / 12.0)
        h = max(h, pw.lerp(h, crest, blend))
        # keep the path itself walkable
        h = pw.lerp(alt, h, pw.smoothstep(0.8, 3.5, d))
    for name, sx, sy, alt in ROUTE:
        r = 7.0 if name in ("base", "summit") else 4.5
        dist2 = (x - sx) ** 2 + (y - sy) ** 2
        h = pw.lerp(h, alt, math.exp(-dist2 / (r * r)) * 0.92)
    return h


# --- terrain grid -------------------------------------------------------------
step = SIZE / RES
heights = [[0.0] * (RES + 1) for _ in range(RES + 1)]
coords = [[(0.0, 0.0)] * (RES + 1) for _ in range(RES + 1)]
rng = random.Random(args.seed)
for j in range(RES + 1):
    for i in range(RES + 1):
        x = -SIZE / 2 + i * step
        y = -SIZE / 2 + j * step
        if 0 < i < RES and 0 < j < RES:
            x += rng.uniform(-0.32, 0.32) * step
            y += rng.uniform(-0.32, 0.32) * step
        coords[j][i] = (x, y)
        heights[j][i] = height(x, y)

verts = []
colors = []
C = {k: Vector(pw.hex_color(v)[:3]) for k, v in {
    "meadow_low": "#6f8c50",
    "meadow_high": "#93a15c",
    "forest": "#476241",
    "rock_light": "#948b9c",
    "rock_dark": "#5e576b",
    "snow": "#e2e6ef",
    "bank": "#a89d84",
}.items()}

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
        rock_w = max(pw.smoothstep(0.2, 0.36, slope), pw.smoothstep(52.0, 72.0, h) * 0.85)
        snow_line = SNOWLINE + 5.0 * noise.noise(Vector((x * 0.05, y * 0.05, 4.0)))
        snow_w = pw.smoothstep(snow_line - 4.0, snow_line + 3.0, h) * (1.0 - pw.smoothstep(0.32, 0.5, slope))
        bank_w = 1.0 - pw.smoothstep(WATER + 0.2, WATER + 1.4, h)

        col = grass.lerp(rock, rock_w).lerp(C["snow"], snow_w).lerp(C["bank"], bank_w)
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


def ground(x, y):
    """Height of the built mesh under (x, y), bilinear over the grid cell."""
    fi = (x + SIZE / 2) / step
    fj = (y + SIZE / 2) / step
    i = max(0, min(RES - 1, int(fi)))
    j = max(0, min(RES - 1, int(fj)))
    tx, ty = fi - i, fj - j
    h00, h10 = heights[j][i], heights[j][i + 1]
    h01, h11 = heights[j + 1][i], heights[j + 1][i + 1]
    return pw.lerp(pw.lerp(h00, h10, tx), pw.lerp(h01, h11, tx), ty)


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

# --- trail ribbon --------------------------------------------------------------
trail_pts = [Vector((p.x, p.y, 0.0)) for p in catmull([(x, y, alt) for _, x, y, alt in ROUTE], 60)]
tv, tf = [], []
for k, p in enumerate(trail_pts):
    nxt = trail_pts[min(k + 1, len(trail_pts) - 1)]
    prv = trail_pts[max(k - 1, 0)]
    tangent = (nxt - prv).normalized()
    side = Vector((-tangent.y, tangent.x, 0.0)) * 0.42
    for q in (p - side, p + side):
        tv.append((q.x, q.y, ground(q.x, q.y) + 0.12))
    if k > 0:
        a = (k - 1) * 2
        tf.append((a, a + 1, a + 3, a + 2))
pw.mesh_object("trail", tv, tf, pw.material("trail", "#d7c49a", roughness=1.0))

# --- trees ---------------------------------------------------------------------
foliage = pw.material("pine_foliage", "#2e5242", roughness=0.9)
foliage_light = pw.material("pine_foliage_light", "#3d6a4a", roughness=0.9)
trunk = pw.material("pine_trunk", "#5b4232", roughness=1.0)


def pine_mesh(name, tiers, mat):
    bm = bmesh.new()
    trunk_verts = pw.add_cone(bm, (0, 0, 0), 0.09, 0.07, 0.5, segments=5)
    pw.assign_material_index(bm, trunk_verts, 1)
    z = 0.35
    for k in range(tiers):
        radius = 0.62 - k * (0.42 / tiers)
        height_ = 0.9 - k * 0.12
        pw.add_cone(bm, (0, 0, z), radius, 0.02, height_, segments=7, rotation=k * 0.6)
        z += height_ * 0.52
    obj = pw.bm_object(name, bm, [mat, trunk])
    return obj.data


pine_tall = pine_mesh("pine_tall", 4, foliage)
pine_round = pine_mesh("pine_round", 3, foliage_light)

trees_col = pw.collection("trees")
placed = 0
attempts = 0
while placed < 1700 and attempts < 60000:
    attempts += 1
    x = rng.uniform(-200.0, 200.0)
    y = rng.uniform(-200.0, 190.0)
    h = ground(x, y)
    if h < WATER + 1.4 or h > 50.0:
        continue
    gx = ground(x + 1.5, y) - ground(x - 1.5, y)
    gy = ground(x, y + 1.5) - ground(x, y - 1.5)
    if math.hypot(gx, gy) / 3.0 > 0.55:
        continue
    density = noise.noise(Vector((x * 0.028, y * 0.028, 1.7)))
    if density < -0.05 - 0.25 * pw.smoothstep(30.0, 50.0, h):
        continue
    d_route, _ = route_distance(x, y)
    if d_route < 3.2:
        continue
    if any((x - sx) ** 2 + (y - sy) ** 2 < 64.0 for _, sx, sy, _ in ROUTE):
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

# --- rocks -----------------------------------------------------------------------
rock_mat = pw.material("boulder", "#837b8c", roughness=0.95)
bm = bmesh.new()
pw.add_ico(bm, (0, 0, 0), 0.6, subdivisions=1, scale=(1.2, 0.9, 0.7))
for v in bm.verts:
    v.co += Vector((rng.uniform(-0.08, 0.08), rng.uniform(-0.08, 0.08), rng.uniform(-0.06, 0.06)))
boulder = pw.bm_object("boulder_src", bm, rock_mat).data
bpy.data.objects.remove(bpy.data.objects["boulder_src"])
rocks_col = pw.collection("rocks")
for k in range(160):
    x = rng.uniform(-170.0, 170.0)
    y = rng.uniform(-170.0, 170.0)
    h = ground(x, y)
    if h < WATER + 0.6 or h > 90.0:
        continue
    obj = bpy.data.objects.new(f"rock_{k}", boulder)
    s = rng.uniform(0.6, 2.4)
    obj.scale = (s, s * rng.uniform(0.7, 1.2), s * rng.uniform(0.6, 1.0))
    obj.rotation_euler = (0.0, 0.0, rng.uniform(0, math.tau))
    obj.location = (x, y, h - 0.2 * s)
    rocks_col.objects.link(obj)

# The source meshes for instancing should not render at the origin.
for name in ("pine_tall", "pine_round"):
    bpy.data.objects.remove(bpy.data.objects[name])

# --- camps and props ---------------------------------------------------------------
fabric = [pw.material("tent_orange", "#e5703a", 0.85), pw.material("tent_yellow", "#efbd4a", 0.85)]
flag_mat = pw.material("flag", "#d8483a", 0.8)
pole_mat = pw.material("pole", "#d9d6cf", 0.6, 0.2)
wood = pw.material("wood", "#7a5537", 0.9)
stone = pw.material("stone", "#8b8494", 0.95)
white = pw.material("observatory_white", "#eeeef0", 0.45, 0.05)
dark = pw.material("observatory_slit", "#1d2030", 0.6)
glow = pw.material("fire_glow", "#ffb24a", 1.0, emission="#ff9a3a", emission_strength=6.0)
beacon_mat = pw.material("beacon", "#ff5a4a", 1.0, emission="#ff4a3a", emission_strength=8.0)
window_mat = pw.material("window_warm", "#ffd9a0", 1.0, emission="#ffc777", emission_strength=3.0)

props = pw.collection("props")


def facing(name):
    """Angle that points from a site towards the next one along the trail."""
    idx = [r[0] for r in ROUTE].index(name)
    a = ROUTE[idx]
    b = ROUTE[min(idx + 1, len(ROUTE) - 1)] if idx < len(ROUTE) - 1 else ROUTE[idx - 1]
    return math.atan2(b[2] - a[2], b[1] - a[1])


def tent(bm_, origin, rot, size=1.0):
    w, l, h = 0.75 * size, 1.0 * size, 0.6 * size
    base = [Vector((-w / 2, -l / 2, 0)), Vector((w / 2, -l / 2, 0)), Vector((w / 2, l / 2, 0)), Vector((-w / 2, l / 2, 0))]
    ridge = [Vector((0, -l / 2 - 0.08 * size, h)), Vector((0, l / 2 + 0.08 * size, h))]
    rotm = pw._rot_z(rot)
    vs = [bm_.verts.new(Vector(origin) + rotm @ p) for p in base + ridge]
    bm_.faces.new((vs[0], vs[1], vs[4]))
    bm_.faces.new((vs[1], vs[2], vs[5], vs[4]))
    bm_.faces.new((vs[2], vs[3], vs[5]))
    bm_.faces.new((vs[3], vs[0], vs[4], vs[5]))
    return vs


def flag(bm_, origin, rot):
    pole = pw.add_cone(bm_, origin, 0.035, 0.03, 1.6, segments=5)
    rotm = pw._rot_z(rot)
    top = Vector(origin) + Vector((0, 0, 1.55))
    a = bm_.verts.new(top)
    b = bm_.verts.new(top + Vector((0, 0, -0.38)))
    c = bm_.verts.new(top + rotm @ Vector((0.55, 0, -0.17)))
    cloth = bm_.faces.new((a, b, c))
    return pole, cloth


for name, sx, sy, _alt in ROUTE:
    z = ground(sx, sy)
    rot = facing(name)
    pw.empty(f"anchor_{name}", (sx, sy, z), props)
    if name == "summit":
        continue
    bm = bmesh.new()
    tents = 3 if name == "base" else (0 if name == "ridge" else 1 + (stable_hash(name) % 2))
    for k in range(tents):
        off = pw._rot_z(rot) @ Vector((-1.6 + k * 1.5, -1.2 - (k % 2) * 0.9, 0))
        tent(bm, (sx + off.x, sy + off.y, ground(sx + off.x, sy + off.y) + 0.02), rot + rng.uniform(-0.4, 0.4), 1.15 if name == "base" else 1.0)
    if tents:
        pw.bm_object(f"tents_{name}", bm, fabric[stable_hash(name) % 2], props)
    else:
        bm.free()

    bm = bmesh.new()
    off = pw._rot_z(rot) @ Vector((1.6, 0.6, 0))
    pole_verts, cloth = flag(bm, (sx + off.x, sy + off.y, ground(sx + off.x, sy + off.y)), rot + 1.2)
    cloth.material_index = 1
    pw.bm_object(f"flag_{name}", bm, [pole_mat, flag_mat], props)

    if name != "base":
        bm = bmesh.new()
        off = pw._rot_z(rot) @ Vector((0.4, 1.4, 0))
        cz = ground(sx + off.x, sy + off.y)
        for k, (r, dz) in enumerate(((0.38, 0.18), (0.28, 0.5), (0.2, 0.76), (0.13, 0.95))):
            pw.add_ico(bm, (sx + off.x + rng.uniform(-0.05, 0.05), sy + off.y, cz + dz), r, 1, (1.0, 0.9, 0.6))
        pw.bm_object(f"cairn_{name}", bm, stone, props)

# base camp: campfire and a bench of logs
bx, by = ROUTE[0][1], ROUTE[0][2]
bz = ground(bx + 1.0, by + 1.4)
bm = bmesh.new()
for k in range(7):
    a = k / 7 * math.tau
    pw.add_ico(bm, (bx + 1.0 + math.cos(a) * 0.42, by + 1.4 + math.sin(a) * 0.42, bz + 0.05), 0.11, 1, (1.2, 1.0, 0.7))
pw.bm_object("fire_ring", bm, stone, props)
bm = bmesh.new()
pw.add_cone(bm, (0, 0, 0), 0.24, 0.0, 0.55, segments=6)
fire = pw.bm_object("fire", bm, glow, props)
fire.location = (bx + 1.0, by + 1.4, bz + 0.05)
bm = bmesh.new()
for k, a in enumerate((0.3, 2.4)):
    c = Vector((bx + 1.0 + math.cos(a) * 1.15, by + 1.4 + math.sin(a) * 1.15, bz + 0.12))
    verts_ = pw.add_cone(bm, (0, 0, 0), 0.13, 0.13, 1.1, segments=6)
    from mathutils import Matrix
    bmesh.ops.rotate(bm, verts=verts_, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, "X"))
    bmesh.ops.rotate(bm, verts=verts_, cent=(0, 0, 0), matrix=Matrix.Rotation(a + math.pi / 2, 3, "Z"))
    bmesh.ops.translate(bm, verts=verts_, vec=c)
pw.bm_object("logs", bm, wood, props)

# ridge overlook: wooden deck and a viewer on a post
rx, ry = ROUTE[6][1], ROUTE[6][2]
rz = ground(rx, ry)
bm = bmesh.new()
pw.add_box(bm, (rx, ry, rz + 0.1), (3.2, 2.0, 0.2), facing("ridge"))
pw.add_cone(bm, (rx - 0.9, ry - 0.5, rz + 0.2), 0.05, 0.05, 1.0, segments=6)
pw.bm_object("deck", bm, wood, props)
bm = bmesh.new()
pw.add_box(bm, (rx - 0.9, ry - 0.5, rz + 1.25), (0.42, 0.22, 0.2), facing("ridge") + math.pi)
pw.bm_object("viewer", bm, pole_mat, props)

# summit observatory
ox, oy = ROUTE[-1][1], ROUTE[-1][2]
oz = ground(ox, oy)
bm = bmesh.new()
pw.add_cone(bm, (ox, oy, oz - 0.4), 2.3, 2.3, 2.3, segments=20)
pw.bm_object("observatory_base", bm, white, props)
bm = bmesh.new()
res = bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=12, radius=2.45)
bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < -0.01], context="VERTS")
bmesh.ops.translate(bm, verts=bm.verts[:], vec=Vector((ox, oy, oz + 1.9)))
pw.bm_object("observatory_dome", bm, white, props, smooth=True)
bm = bmesh.new()
slit_rot = math.atan2(-(oy - ROUTE[6][2]), -(ox - ROUTE[6][1]))
for k in range(5):
    a = 0.15 + k * 0.28
    c = Vector((ox, oy, oz + 1.9)) + pw._rot_z(slit_rot) @ Vector((math.cos(a) * 2.36, 0, math.sin(a) * 2.36))
    pw.add_box(bm, c, (0.12, 0.62, 0.62), slit_rot)
pw.bm_object("observatory_slit", bm, dark, props)
bm = bmesh.new()
door_dir = pw._rot_z(slit_rot + math.pi * 0.85) @ Vector((2.28, 0, 0))
pw.add_box(bm, (ox + door_dir.x, oy + door_dir.y, oz + 0.55), (0.18, 0.75, 1.15), slit_rot + math.pi * 0.85)
pw.bm_object("observatory_door", bm, window_mat, props)
bm = bmesh.new()
pw.add_cone(bm, (ox - 2.8, oy + 1.2, oz - 0.3), 0.06, 0.03, 4.2, segments=5)
pw.bm_object("antenna", bm, pole_mat, props)
bm = bmesh.new()
pw.add_ico(bm, (0, 0, 0), 0.12, 1)
beacon = pw.bm_object("beacon", bm, beacon_mat, props)
beacon.location = (ox - 2.8, oy + 1.2, oz + 3.95)

pw.empty("water", (0.0, 0.0, WATER), props)
pw.empty("anchor_lake", (LAKE[0], LAKE[1], WATER), props)

pw.export_glb(args.out)
