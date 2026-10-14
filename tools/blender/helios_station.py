"""HELIOS: an orbital station with a rotating habitat ring, plus the shuttle that flies to it.

Blender axes: the station's long axis runs along X; the shuttle points along +X.
Top-level empties: station, shuttle. Animated pivots: ring_pivot (spins around X).
Materials the app replaces: hull, truss, solar, radiator, glass, gold, engine_glow,
beacon_red, beacon_green, dock_light, window_light.
"""

import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lib"))
import pw  # noqa: E402

args = pw.parse_args()
pw.reset(args.seed)

M = {
    "hull": pw.material("hull", "#e9eaec", 0.45),
    "truss": pw.material("truss", "#9ba1aa", 0.4, 0.8),
    "solar": pw.material("solar", "#13244a", 0.25, 0.3),
    "radiator": pw.material("radiator", "#f4f4f2", 0.6),
    "glass": pw.material("glass", "#0a0f18", 0.05),
    "gold": pw.material("gold", "#c9a14a", 0.35, 1.0),
    "engine_glow": pw.material("engine_glow", "#9fd8ff", 0.3, emission="#9fd8ff", emission_strength=8.0),
    "beacon_red": pw.material("beacon_red", "#ff3b30", 0.3, emission="#ff3b30", emission_strength=8.0),
    "beacon_green": pw.material("beacon_green", "#34c759", 0.3, emission="#34c759", emission_strength=8.0),
    "dock_light": pw.material("dock_light", "#ffd28a", 0.3, emission="#ffcf8a", emission_strength=6.0),
    "window_light": pw.material("window_light", "#ffe7c2", 0.3, emission="#ffd9a0", emission_strength=4.0),
}

station = pw.empty("station", (0, 0, 0))
shuttle = pw.empty("shuttle", (0, 0, 0))


def obj(name, bm, mat, parent, smooth=False):
    o = pw.bm_object(name, bm, M[mat], smooth=smooth)
    o.parent = parent
    return o


def cylinder_x(bm, x0, x1, radius, segments=24, y=0.0, z=0.0, radius2=None):
    verts = pw.add_cone(bm, (0, 0, 0), radius, radius2 if radius2 is not None else radius, x1 - x0, segments=segments)
    bmesh.ops.rotate(bm, verts=verts, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, "Y"))
    bmesh.ops.translate(bm, verts=verts, vec=Vector((x0, y, z)))
    return verts


def cylinder_between(bm, a, b, radius, segments=8):
    a, b = Vector(a), Vector(b)
    d = b - a
    verts = pw.add_cone(bm, (0, 0, 0), radius, radius, d.length, segments=segments)
    rot = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix()
    bmesh.ops.rotate(bm, verts=verts, cent=(0, 0, 0), matrix=rot)
    bmesh.ops.translate(bm, verts=verts, vec=a)
    return verts


# --- truss ----------------------------------------------------------------------------------
bm = bmesh.new()
half = 0.6
for (y, z) in ((half, half), (half, -half), (-half, half), (-half, -half)):
    cylinder_between(bm, (-16, y, z), (16, y, z), 0.08, 6)
for k in range(17):
    x = -16 + k * 2
    corners = [(x, half, half), (x, half, -half), (x, -half, -half), (x, -half, half)]
    for i in range(4):
        cylinder_between(bm, corners[i], corners[(i + 1) % 4], 0.05, 5)
    if k < 16:
        cylinder_between(bm, (x, half, half), (x + 2, -half, -half), 0.04, 5)
obj("truss", bm, "truss", station)

# --- pressurised modules ------------------------------------------------------------------------
bm = bmesh.new()
for (x0, x1, r) in ((-5.5, -1.0, 1.7), (1.0, 6.0, 1.7), (-11.5, -7.5, 1.3)):
    cylinder_x(bm, x0, x1, r, 32, 0, 2.6)
    cylinder_x(bm, x0 - 0.25, x0, r * 0.75, 32, 0, 2.6, r)
    cylinder_x(bm, x1, x1 + 0.25, r, 32, 0, 2.6, r * 0.75)
obj("modules", bm, "hull", station, smooth=True)
bm = bmesh.new()
for (x0, x1, r) in ((-5.5, -1.0, 1.7), (1.0, 6.0, 1.7)):
    for k in range(4):
        x = x0 + 0.5 + k * (x1 - x0 - 1.0) / 3
        cylinder_x(bm, x - 0.06, x + 0.06, r + 0.04, 32, 0, 2.6)
obj("module_bands", bm, "gold", station, smooth=True)
bm = bmesh.new()
bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=16, radius=1.5)
bmesh.ops.translate(bm, verts=bm.verts[:], vec=Vector((0, 0, 2.6)))
obj("node", bm, "hull", station, smooth=True)
bm = bmesh.new()
verts = pw.add_cone(bm, (0, 0, 0), 0.75, 0.75, 1.1, segments=24)
bmesh.ops.rotate(bm, verts=verts, cent=(0, 0, 0), matrix=Matrix.Rotation(-math.pi / 2, 3, "X"))
bmesh.ops.translate(bm, verts=verts, vec=Vector((0, -1.3, 2.6)))
obj("dock", bm, "hull", station, smooth=True)
bm = bmesh.new()
verts = pw.add_cone(bm, (0, 0, 0), 0.8, 0.8, 0.08, segments=32)
bmesh.ops.rotate(bm, verts=verts, cent=(0, 0, 0), matrix=Matrix.Rotation(-math.pi / 2, 3, "X"))
bmesh.ops.translate(bm, verts=verts, vec=Vector((0, -2.42, 2.6)))
obj("dock_ring", bm, "dock_light", station)

# windows along the modules
bm = bmesh.new()
for x in (-4.6, -3.4, -2.2, 2.0, 3.2, 4.4):
    pw.add_box(bm, (x, -1.66, 2.9), (0.5, 0.1, 0.3))
obj("module_windows", bm, "window_light", station)

# cupola under the node
bm = bmesh.new()
bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=0.9)
bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z > 0.01], context="VERTS")
bmesh.ops.translate(bm, verts=bm.verts[:], vec=Vector((0, 0, 1.1)))
obj("cupola", bm, "glass", station, smooth=True)
bm = bmesh.new()
pw.add_cone(bm, (0, 0, 0.6), 0.95, 0.95, 0.5, segments=16)
obj("cupola_frame", bm, "hull", station)

# --- habitat ring ------------------------------------------------------------------------------------
ring = pw.empty("ring_pivot", (-9.5, 0, 0))
ring.parent = station
bm = bmesh.new()
res = bmesh.ops.create_circle(bm, cap_ends=False, radius=0.85, segments=12)
circle = res["verts"]
bmesh.ops.rotate(bm, verts=circle, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, "Y"))
bmesh.ops.translate(bm, verts=circle, vec=Vector((0, 9.0, 0)))
edges = [e for e in bm.edges]
bmesh.ops.spin(bm, geom=circle + edges, cent=(0, 0, 0), axis=(1, 0, 0), angle=math.tau, steps=72, use_duplicate=False)
bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=0.001)
obj("ring", bm, "hull", ring, smooth=True)
bm = bmesh.new()
for k in range(4):
    a = k * math.pi / 2 + math.pi / 4
    cylinder_between(bm, (0, 0, 0), (0, math.cos(a) * 8.3, math.sin(a) * 8.3), 0.22, 10)
cylinder_x(bm, -0.9, 0.9, 1.0, 24)
obj("spokes", bm, "truss", ring, smooth=True)
bm = bmesh.new()
for k in range(24):
    a = k / 24 * math.tau
    c = Vector((0.0, math.cos(a) * 9.0, math.sin(a) * 9.0))
    n = Vector((0.0, math.cos(a), math.sin(a)))
    verts = pw.add_box(bm, (0, 0, 0), (0.6, 0.05, 0.25))
    bmesh.ops.rotate(bm, verts=verts, cent=(0, 0, 0), matrix=Vector((0, 1, 0)).rotation_difference(n).to_matrix())
    bmesh.ops.translate(bm, verts=verts, vec=c + n * 0.86)
obj("ring_windows", bm, "window_light", ring)

# --- solar arrays ------------------------------------------------------------------------------------------
bm = bmesh.new()
uv = bm.loops.layers.uv.new("UVMap")
for side_z in (1, -1):
    mast_x = 11.0 if side_z > 0 else 13.0
    for side_y in (1, -1):
        for (length, offset) in ((12.0, 1.4),):
            grid = bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.5, calc_uvs=True)
            verts = grid["verts"]
            bmesh.ops.scale(bm, vec=Vector((3.2, length, 1)), verts=verts)
            bmesh.ops.translate(bm, verts=verts, vec=Vector((mast_x, side_y * (offset + length / 2), side_z * 2.2)))
obj("solar_panels", bm, "solar", station)
bm = bmesh.new()
for side_z in (1, -1):
    mast_x = 11.0 if side_z > 0 else 13.0
    cylinder_between(bm, (mast_x, 0, 0), (mast_x, 0, side_z * 2.2), 0.12, 8)
    cylinder_between(bm, (mast_x, -13.6, side_z * 2.2), (mast_x, 13.6, side_z * 2.2), 0.07, 6)
obj("solar_masts", bm, "truss", station)

# radiators
bm = bmesh.new()
for side_y in (1, -1):
    verts = pw.add_box(bm, (0, 0, 0), (2.6, 0.06, 5.0))
    bmesh.ops.rotate(bm, verts=verts, cent=(0, 0, 0), matrix=Matrix.Rotation(side_y * 0.35, 3, "X"))
    bmesh.ops.translate(bm, verts=verts, vec=Vector((6.5, side_y * 1.0, -3.0)))
obj("radiators", bm, "radiator", station)

# beacons
bm = bmesh.new()
pw.add_ico(bm, (16.2, 0.6, 0.6), 0.16, 1)
pw.add_ico(bm, (-16.2, 0.6, 0.6), 0.16, 1)
obj("beacon_r", bm, "beacon_red", station)
bm = bmesh.new()
pw.add_ico(bm, (16.2, -0.6, -0.6), 0.16, 1)
pw.add_ico(bm, (-16.2, -0.6, -0.6), 0.16, 1)
obj("beacon_g", bm, "beacon_green", station)

# --- shuttle ----------------------------------------------------------------------------------------------------
bm = bmesh.new()
cylinder_x(bm, -1.1, 0.7, 0.42, 24)
cylinder_x(bm, 0.7, 1.5, 0.42, 24, radius2=0.08)
cylinder_x(bm, -1.3, -1.1, 0.34, 24, radius2=0.42)
obj("shuttle_body", bm, "hull", shuttle, smooth=True)
bm = bmesh.new()
for side in (1, -1):
    v = [bm.verts.new(p) for p in ((0.4, side * 0.35, -0.12), (-0.9, side * 1.45, -0.18), (-1.15, side * 1.45, -0.18), (-1.1, side * 0.35, -0.12))]
    bm.faces.new(v if side > 0 else list(reversed(v)))
v = [bm.verts.new(p) for p in ((-0.3, 0, 0.35), (-1.05, 0, 1.05), (-1.25, 0, 1.05), (-1.15, 0, 0.35))]
bm.faces.new(v)
bmesh.ops.solidify(bm, geom=bm.faces[:], thickness=0.06)
obj("shuttle_wings", bm, "hull", shuttle)
bm = bmesh.new()
for y in (0.16, -0.16):
    cylinder_x(bm, -1.65, -1.3, 0.16, 16, y, -0.05, 0.11)
obj("shuttle_engines", bm, "truss", shuttle, smooth=True)
bm = bmesh.new()
for y in (0.16, -0.16):
    cylinder_x(bm, -1.68, -1.64, 0.13, 16, y, -0.05)
obj("shuttle_glow", bm, "engine_glow", shuttle)
bm = bmesh.new()
pw.add_box(bm, (1.0, 0, 0.22), (0.45, 0.5, 0.14))
obj("shuttle_windows", bm, "glass", shuttle)
bm = bmesh.new()
cylinder_x(bm, -0.2, 0.0, 0.43, 24)
obj("shuttle_band", bm, "gold", shuttle, smooth=True)

pw.export_glb(args.out)
