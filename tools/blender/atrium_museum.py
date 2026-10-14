"""ATRIUM: a museum with a lobby, a long green gallery of thirteen paintings and a dark experience wing.

Blender axes: X across, Y forward into the museum, Z up. One unit is one metre.
Groups: solid (walls and furniture the visitor collides with), decor (no collision).
Quads with UVs that receive runtime textures: canvas_0..12, label_0..12, exp_0..4, about_panel,
contact_panel, sign_hall, sign_wing. Empties: spawn and spot_* (where the visitor stands to look),
light_* (picture light positions), sky_* (skylights).
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

H = 6.0  # ceiling height
T = 0.3  # wall thickness

M = {
    "wall_light": pw.material("wall_light", "#ebe7e0", 0.92),
    "wall_green": pw.material("wall_green", "#264238", 0.9),
    "wall_dark": pw.material("wall_dark", "#25272c", 0.9),
    "floor_stone": pw.material("floor_stone", "#cdcac3", 0.3),
    "floor_oak": pw.material("floor_oak", "#6b4a33", 0.45),
    "ceiling": pw.material("ceiling", "#f2f0ec", 0.95),
    "skylight": pw.material("skylight", "#ffffff", 0.2, emission="#fff6e8", emission_strength=3.0),
    "frame": pw.material("frame", "#b48a4a", 0.35, 1.0),
    "frame_dark": pw.material("frame_dark", "#18191c", 0.4),
    "canvas": pw.material("canvas", "#222222", 0.8),
    "label": pw.material("label", "#f4f2ee", 0.7),
    "lightbox": pw.material("lightbox", "#ffffff", 0.5),
    "brass": pw.material("brass", "#c59a52", 0.3, 1.0),
    "bench": pw.material("bench", "#3a2a1f", 0.55),
    "leather": pw.material("leather", "#1d1e22", 0.6),
    "marble": pw.material("marble", "#e9e6e1", 0.25),
    "desk": pw.material("desk", "#f0ede8", 0.5),
    "trim": pw.material("trim", "#1a1b1e", 0.5),
}

groups = {name: pw.empty(name, (0, 0, 0)) for name in ("solid", "decor", "exhibits")}
n = {"i": 0}


def box(group, mat, x0, x1, y0, y1, z0, z1, name=None):
    bm = bmesh.new()
    pw.add_box(bm, ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), (x1 - x0, y1 - y0, z1 - z0))
    n["i"] += 1
    o = pw.bm_object(name or f"{group}_{n['i']}", bm, M[mat])
    o.parent = groups[group]
    return o


def quad(name, mat, centre, width, height, facing, group="exhibits"):
    """A vertical quad with UVs facing `facing` ('n', 's', 'e', 'w')."""
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    hw, hh = width / 2, height / 2
    # corner order sets the normal (facing direction) and keeps U running to the viewer's right
    if facing in ("n", "s"):
        sign = 1 if facing == "s" else -1
        corners = [(-hw * sign, 0, -hh), (hw * sign, 0, -hh), (hw * sign, 0, hh), (-hw * sign, 0, hh)]
    else:
        sign = 1 if facing == "w" else -1
        corners = [(0, hw * sign, -hh), (0, -hw * sign, -hh), (0, -hw * sign, hh), (0, hw * sign, hh)]
    verts = [bm.verts.new(Vector(centre) + Vector(c)) for c in corners]
    face = bm.faces.new(verts)
    for loop, coords in zip(face.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        loop[uv].uv = coords
    face.normal_update()
    o = pw.bm_object(name, bm, M[mat])
    o.parent = groups[group]
    return o


def wall_x(mat, x, y0, y1, gaps=(), z1=H):
    """Wall along Y at x, with door gaps (y_start, y_end, height)."""
    cursor = y0
    for (g0, g1, gh) in sorted(gaps):
        if g0 > cursor:
            box("solid", mat, x - T / 2, x + T / 2, cursor, g0, 0, z1)
        box("decor", mat, x - T / 2, x + T / 2, g0, g1, gh, z1)
        cursor = g1
    if cursor < y1:
        box("solid", mat, x - T / 2, x + T / 2, cursor, y1, 0, z1)


def wall_y(mat, y, x0, x1, gaps=(), z1=H):
    cursor = x0
    for (g0, g1, gh) in sorted(gaps):
        if g0 > cursor:
            box("solid", mat, cursor, g0, y - T / 2, y + T / 2, 0, z1)
        box("decor", mat, g0, g1, y - T / 2, y + T / 2, gh, z1)
        cursor = g1
    if cursor < x1:
        box("solid", mat, cursor, x1, y - T / 2, y + T / 2, 0, z1)


# --- rooms --------------------------------------------------------------------------------------
# lobby
box("decor", "floor_stone", -8, 8, -34, -20, -0.1, 0, "floor_lobby")
wall_y("wall_light", -34, -8, 8)
wall_x("wall_light", -8, -34, -20)
wall_x("wall_light", 8, -34, -20)
wall_y("wall_light", -20, -8, 8, gaps=((-2.5, 2.5, 4.2),))
# main hall
box("decor", "floor_stone", -7, 7, -20, 26, -0.1, 0, "floor_hall")
wall_x("wall_green", -7, -20, 26)
wall_x("wall_green", 7, -20, 26, gaps=((-2.0, 4.0, 4.2),))
wall_y("wall_green", 26, -7, 7)
# experience wing
box("decor", "floor_oak", 7, 21, -6, 12, -0.1, 0, "floor_wing")
wall_y("wall_dark", -6, 7, 21)
wall_y("wall_dark", 12, 7, 21)
wall_x("wall_dark", 21, -6, 12)
# ceilings
box("decor", "ceiling", -8, 8, -34, -20, H, H + 0.2, "ceiling_lobby")
box("decor", "ceiling", 7, 21, -6, 12, H, H + 0.2, "ceiling_wing")
# hall ceiling with skylight openings
for k, (y0, y1) in enumerate(((-20, -16), (-12, -8), (-4, 0), (4, 8), (12, 16), (20, 26))):
    box("decor", "ceiling", -7, 7, y0, y1, H, H + 0.2, f"ceiling_hall_{k}")
for k, (y0, y1) in enumerate(((-16, -12), (-8, -4), (0, 4), (8, 12), (16, 20))):
    box("decor", "ceiling", -7, -3, y0, y1, H, H + 0.2, f"ceiling_side_w_{k}")
    box("decor", "ceiling", 3, 7, y0, y1, H, H + 0.2, f"ceiling_side_e_{k}")
    box("decor", "skylight", -3, 3, y0, y1, H + 0.15, H + 0.2, f"skylight_{k}")
    pw.empty(f"sky_{k}", (0, (y0 + y1) / 2, H))
# skirting trim in the hall
box("decor", "trim", -6.84, -6.8, -20, 26, 0, 0.15, "skirting_w")
box("decor", "trim", 6.8, 6.84, -20, -2, 0, 0.15, "skirting_e1")
box("decor", "trim", 6.8, 6.84, 4, 26, 0, 0.15, "skirting_e2")

# --- paintings -------------------------------------------------------------------------------------------
CW, CH, CZ = 2.4, 1.35, 2.1
paintings = []
for y in (-15, -9, -3, 3, 9, 15, 21):
    paintings.append(("e", -7 + T / 2 + 0.06, y, 1.0))   # west wall, facing east
for y in (-15, -9, 9, 15, 21):
    paintings.append(("w", 7 - T / 2 - 0.06, y, 1.0))    # east wall, facing west
paintings.append(("s", 0, 26 - T / 2 - 0.06, 2.0))         # north wall, featured, facing south

for i, (facing, px, py, scale) in enumerate(paintings):
    w, h = CW * scale, CH * scale
    z = CZ + (0.5 if scale > 1 else 0)
    if facing in ("e", "w"):
        d = 1 if facing == "e" else -1
        box("decor", "frame", px - 0.04 * d - 0.03, px - 0.04 * d + 0.03, py - w / 2 - 0.12, py + w / 2 + 0.12, z - h / 2 - 0.12, z + h / 2 + 0.12, f"frame_{i}")
        quad(f"canvas_{i}", "canvas", (px + 0.02 * d, py, z), w, h, facing)
        quad(f"label_{i}", "label", (px + 0.01 * d, py + (w / 2 + 0.55) * (-d), 1.45), 0.46, 0.3, facing)
        pw.empty(f"spot_canvas_{i}", (px + 3.0 * d, py, 0))
        pw.empty(f"light_{i}", (px + 0.35 * d, py, z + h / 2 + 0.35))
        bm = bmesh.new()
        verts = pw.add_cone(bm, (0, 0, 0), 0.035, 0.035, w * 0.6, segments=10)
        bmesh.ops.rotate(bm, verts=verts, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, "X"))
        bmesh.ops.translate(bm, verts=verts, vec=Vector((px + 0.3 * d, py + w * 0.3, z + h / 2 + 0.32)))
        lamp = pw.bm_object(f"lamp_{i}", bm, M["brass"])
        lamp.parent = groups["decor"]
    else:
        box("decor", "frame", px - w / 2 - 0.16, px + w / 2 + 0.16, py + 0.0, py + 0.06, z - h / 2 - 0.16, z + h / 2 + 0.16, f"frame_{i}")
        quad(f"canvas_{i}", "canvas", (px, py - 0.02, z), w, h, facing)
        quad(f"label_{i}", "label", (px + w / 2 + 0.7, py - 0.01, 1.45), 0.46, 0.3, facing)
        pw.empty(f"spot_canvas_{i}", (px, py - 5.0, 0))
        pw.empty(f"light_{i}", (px, py - 0.4, z + h / 2 + 0.4))

# benches and sculpture
for y in (-12, 0, 18):
    box("solid", "bench", -1.6, 1.6, y - 0.35, y + 0.35, 0.0, 0.42, f"bench_{y}")
    box("decor", "leather", -1.55, 1.55, y - 0.3, y + 0.3, 0.42, 0.48, f"bench_top_{y}")
box("solid", "marble", -0.8, 0.8, 7.4, 9.0, 0, 1.0, "pedestal")
bm = bmesh.new()
torus_like = bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=0.7)
for v in torus_like["verts"]:
    a = math.atan2(v.co.y, v.co.x)
    twist = Matrix.Rotation(v.co.z * 1.8, 3, "Z")
    v.co = twist @ Vector((v.co.x * (0.55 + 0.35 * math.cos(3 * a)), v.co.y * (0.55 + 0.35 * math.cos(3 * a)), v.co.z * 1.6))
bmesh.ops.translate(bm, verts=bm.verts[:], vec=Vector((0, 8.2, 2.2)))
sculpture = pw.bm_object("sculpture", bm, M["marble"], smooth=True)
sculpture.parent = groups["decor"]

# --- lobby: about wall and contact desk ------------------------------------------------------------------
quad("about_panel", "label", (-8 + T / 2 + 0.03, -27, 2.6), 7.0, 3.6, "e")
pw.empty("spot_about", (-4.2, -27, 0))
box("solid", "desk", 3.6, 6.4, -28.6, -25.4, 0, 1.05, "desk")
box("decor", "marble", 3.5, 6.5, -28.7, -25.3, 1.05, 1.1, "desk_top")
quad("contact_panel", "label", (8 - T / 2 - 0.03, -27, 2.7), 3.6, 2.0, "w")
pw.empty("spot_contact", (2.0, -27, 0))
quad("sign_hall", "label", (0, -20 - T / 2 - 0.02, 4.9), 3.2, 0.8, "s")
quad("sign_wing", "label", (7 - T / 2 - 0.02, 1.0, 4.9), 3.2, 0.8, "w")
pw.empty("spawn", (0, -31, 0))

# --- experience wing: lightboxes ---------------------------------------------------------------------------
boxes = [
    ("n", 14.0, -6 + T / 2 + 0.08, (14.0, -2.6)),
    ("w", 21 - T / 2 - 0.08, -1.0, (17.6, -1.0)),
    ("w", 21 - T / 2 - 0.08, 3.0, (17.6, 3.0)),
    ("w", 21 - T / 2 - 0.08, 7.0, (17.6, 7.0)),
    ("s", 14.0, 12 - T / 2 - 0.08, (14.0, 8.6)),
]
LW, LH, LZ = 3.0, 1.9, 2.2
for i, (facing, px, py, spot) in enumerate(boxes):
    if facing in ("n", "s"):
        d = 1 if facing == "n" else -1
        box("decor", "frame_dark", px - LW / 2 - 0.1, px + LW / 2 + 0.1, py - 0.06 * d - 0.05, py - 0.06 * d + 0.05, LZ - LH / 2 - 0.1, LZ + LH / 2 + 0.1, f"lightbox_frame_{i}")
        quad(f"exp_{i}", "lightbox", (px, py + 0.01 * d, LZ), LW, LH, facing)
    else:
        box("decor", "frame_dark", px + 0.01, px + 0.11, py - LW / 2 - 0.1, py + LW / 2 + 0.1, LZ - LH / 2 - 0.1, LZ + LH / 2 + 0.1, f"lightbox_frame_{i}")
        quad(f"exp_{i}", "lightbox", (px - 0.01, py, LZ), LW, LH, facing)
    pw.empty(f"spot_exp_{i}", (spot[0], spot[1], 0))

pw.export_glb(args.out)
