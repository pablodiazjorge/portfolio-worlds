"""TERRA: a two storey modern house split into five build stages, a removable facade and an interior.

Blender axes: X across the front, Y depth (the front faces -Y), Z up. One unit is one metre.
Top-level empties read by the app: stage_1 .. stage_5, facade, interior, site.
Monitor screens are meshes named screen_0, screen_1, screen_2 with UVs for the project covers.
"""

import math
import os
import random
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lib"))
import pw  # noqa: E402

args = pw.parse_args()
pw.reset(args.seed)
rng = random.Random(args.seed)

M = {
    "concrete": pw.material("concrete", "#a9a7a2", 0.85),
    "render": pw.material("render", "#ecebe6", 0.9),
    "timber": pw.material("timber", "#a8714a", 0.75),
    "steel": pw.material("steel", "#23262b", 0.45, 0.6),
    "glass": pw.material("glass", "#1b2430", 0.05),
    "oak": pw.material("oak", "#c79c6e", 0.6),
    "fabric": pw.material("fabric", "#6e7073", 0.95),
    "linen": pw.material("linen", "#e7e1d6", 0.95),
    "screen": pw.material("screen", "#0b0d10", 0.3),
    "water": pw.material("water", "#4fb3c8", 0.05),
    "stone": pw.material("stone", "#cfcac0", 0.8),
    "light": pw.material("light", "#fff1d6", 0.5, emission="#ffd9a0", emission_strength=4.0),
    "leaves": pw.material("leaves", "#5f8f4a", 0.9),
    "bark": pw.material("bark", "#5b4434", 0.95),
    "lawn": pw.material("lawn", "#6f9a4f", 0.95),
}

groups = {name: pw.empty(name, (0, 0, 0)) for name in ("stage_1", "stage_2", "stage_3", "stage_4", "stage_5", "facade", "interior", "site")}
counter = {"n": 0}


def box(group, mat, x0, x1, y0, y1, z0, z1, bevel=0.0, name=None):
    bm = bmesh.new()
    pw.add_box(bm, ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), (x1 - x0, y1 - y0, z1 - z0))
    if bevel:
        bmesh.ops.bevel(bm, geom=bm.edges[:], offset=bevel, segments=1, affect="EDGES", clamp_overlap=True)
    counter["n"] += 1
    obj = pw.bm_object(name or f"{group}_{mat}_{counter['n']}", bm, M[mat])
    obj.parent = groups[group]
    return obj


def merge(group, mat, boxes, name):
    """Several boxes in one mesh: fewer draw calls for repeated pieces."""
    bm = bmesh.new()
    for (x0, x1, y0, y1, z0, z1) in boxes:
        pw.add_box(bm, ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), (x1 - x0, y1 - y0, z1 - z0))
    obj = pw.bm_object(name, bm, M[mat])
    obj.parent = groups[group]
    return obj


GF = 0.4  # ground floor level
FF = 3.9  # first floor level
GH = 3.2  # storey height

# --- stage 1: foundation ------------------------------------------------------------------------
box("stage_1", "concrete", -7.2, 7.2, -4.7, 4.7, 0.0, GF, name="slab")
box("stage_1", "concrete", -7.2, 7.2, -8.5, -4.7, 0.0, 0.25, name="terrace_slab")
merge("stage_1", "concrete", [(-7.4, 7.4, -4.9, -4.5, -0.6, 0.0), (-7.4, 7.4, 4.5, 4.9, -0.6, 0.0), (-7.4, -7.0, -4.9, 4.9, -0.6, 0.0), (7.0, 7.4, -4.9, 4.9, -0.6, 0.0)], "footings")

# --- stage 2: ground floor structure ---------------------------------------------------------------
walls = [
    (-7.0, 7.0, 4.2, 4.5, GF, GF + GH),        # back
    (-7.0, -6.7, -4.5, 4.5, GF, GF + GH),      # west
    (6.7, 7.0, -4.5, -1.0, GF, GF + GH),       # east, front part
    (6.7, 7.0, 1.6, 4.5, GF, GF + GH),         # east, back part
    (-1.0, -0.8, 0.5, 4.2, GF, GF + GH),       # partition
]
merge("stage_2", "concrete", walls, "ground_walls")
merge("stage_2", "steel", [(x - 0.1, x + 0.1, -4.6, -4.4, GF, GF + GH) for x in (-6.85, -2.3, 2.3, 6.85)], "front_columns")
box("stage_2", "concrete", -0.6, 2.2, 1.4, 4.2, GF, GF + 0.18 * 0 + 0.01, name="stair_landing")
for k in range(16):
    z = GF + k * (GH + 0.3) / 16
    box("stage_2", "oak", 2.4, 3.5, 4.1 - k * 0.24, 4.2 - k * 0.24 + 0.24, z, z + 0.08, name=f"step_{k}")

# --- stage 3: first floor slab and the cantilevered box --------------------------------------------
box("stage_3", "concrete", -7.0, 7.0, -4.5, 4.5, GF + GH, FF, name="first_slab")
box("stage_3", "render", -6.2, 4.4, -6.8, 3.9, FF - 0.3, FF, name="box_floor")
upper = [
    (-6.2, -5.9, -6.8, 3.9, FF, FF + GH),      # west
    (4.1, 4.4, -6.8, 3.9, FF, FF + GH),        # east
    (-6.2, 4.4, 3.6, 3.9, FF, FF + GH),        # back
]
merge("stage_3", "render", upper, "upper_walls")
merge("stage_3", "steel", [(4.4, 7.0, -4.5, -4.35, FF, FF + 1.05), (6.85, 7.0, -4.5, 4.5, FF, FF + 1.05)], "roof_terrace_rail")

# --- stage 4: roof and glazing ---------------------------------------------------------------------------
box("stage_4", "render", -6.4, 4.6, -7.0, 4.1, FF + GH, FF + GH + 0.35, name="roof")
merge("stage_4", "render", [(-6.4, 4.6, -7.0, -6.8, FF + GH + 0.35, FF + GH + 0.7), (-6.4, 4.6, 3.9, 4.1, FF + GH + 0.35, FF + GH + 0.7),
                             (-6.4, -6.2, -7.0, 4.1, FF + GH + 0.35, FF + GH + 0.7), (4.4, 4.6, -7.0, 4.1, FF + GH + 0.35, FF + GH + 0.7)], "parapet")
box("stage_4", "glass", 6.75, 6.95, -1.0, 1.6, GF + 0.1, GF + GH - 0.1, name="east_window")
box("stage_4", "glass", -6.1, 4.3, 3.65, 3.85, FF + 1.0, FF + 2.4, name="back_window")
box("stage_4", "light", -5.5, 3.8, -1.0, -0.6, FF + GH - 0.06, FF + GH - 0.02, name="light_upper")
box("stage_4", "light", -6.0, 6.0, 0.2, 0.6, GF + GH - 0.06, GF + GH - 0.02, name="light_ground")

# facade: the front glazing of both floors and their frames, removed for the dollhouse view
box("facade", "glass", -6.75, 6.75, -4.55, -4.45, GF + 0.05, GF + GH - 0.05, name="front_glass_ground")
merge("facade", "steel", [(x - 0.04, x + 0.04, -4.62, -4.38, GF, GF + GH) for x in (-4.5, 0.0, 4.5)] + [(-6.75, 6.75, -4.62, -4.38, GF + GH - 0.12, GF + GH)], "front_mullions_ground")
box("facade", "glass", -5.9, 4.1, -6.85, -6.75, FF + 0.05, FF + GH - 0.05, name="front_glass_upper")
merge("facade", "timber", [(x - 0.06, x + 0.06, -6.95, -6.75, FF, FF + GH) for x in (-5.95, -3.4, -0.9, 1.6, 4.15)], "front_fins_upper")

# --- stage 5: finishes, cladding and landscape ---------------------------------------------------------------
slats = []
for side_x, (x0, x1) in ((-1, (-6.32, -6.2)), (1, (4.4, 4.52))):
    for k in range(48):
        y = -6.75 + k * 0.22
        slats.append((x0, x1, y, y + 0.12, FF + 0.05, FF + GH - 0.05))
merge("stage_5", "timber", slats, "cladding")
merge("stage_5", "oak", [(-6.7, 6.7, -4.4, 4.2, GF, GF + 0.04), (-5.9, 4.1, -6.75, 3.6, FF, FF + 0.04)], "floors")
box("stage_5", "oak", -7.0, 7.0, -8.4, -4.7, 0.25, 0.32, name="deck")
merge("stage_5", "steel", [(-6.1, 4.3, -6.95, -6.85, FF - 0.35, FF - 0.3)], "box_edge")

# pool, coping and path
box("site", "stone", 1.0, 9.5, -14.6, -9.2, 0.0, 0.22, name="pool_coping")
box("site", "water", 1.4, 9.1, -14.2, -9.6, 0.0, 0.18, name="pool_water")
for k in range(6):
    x = -3.0 + rng.uniform(-0.2, 0.2)
    y = -9.5 - k * 1.4
    box("site", "stone", x - 0.55, x + 0.55, y - 0.35, y + 0.35, 0.0, 0.06, name=f"path_{k}")

# trees
for k, (tx, ty, s) in enumerate(((-11, -6, 1.2), (-12.5, 2, 1.5), (-9.5, 8, 1.0), (11.5, 6.5, 1.4), (12.5, -2, 1.1), (-6, -15, 0.9), (13, -12, 1.3))):
    bm = bmesh.new()
    pw.add_cone(bm, (tx, ty, 0), 0.18 * s, 0.13 * s, 2.4 * s, segments=6)
    trunk = pw.bm_object(f"trunk_{k}", bm, M["bark"])
    trunk.parent = groups["site"]
    bm = bmesh.new()
    for j in range(3):
        pw.add_ico(bm, (tx + rng.uniform(-0.6, 0.6) * s, ty + rng.uniform(-0.6, 0.6) * s, (2.6 + j * 0.7) * s), (1.4 - j * 0.25) * s, 1)
    crown = pw.bm_object(f"crown_{k}", bm, M["leaves"])
    crown.parent = groups["site"]

# --- interior --------------------------------------------------------------------------------------------------
# living room
box("interior", "fabric", -5.8, -2.6, -2.6, -1.7, GF, GF + 0.45, 0.05, "sofa_seat")
box("interior", "fabric", -5.8, -2.6, -1.85, -1.55, GF, GF + 0.85, 0.05, "sofa_back")
box("interior", "fabric", -5.8, -5.0, -2.6, 0.2, GF, GF + 0.45, 0.05, "sofa_chaise")
box("interior", "linen", -5.4, -2.2, -3.9, -2.4, GF, GF + 0.02, name="rug")
box("interior", "oak", -4.6, -3.4, -3.5, -2.9, GF, GF + 0.4, 0.02, "coffee_table")
merge("interior", "oak", [(-6.6, -6.3, -3.8, 3.8, GF, GF + 2.2)] + [(-6.6, -5.9, -3.8, 3.8, GF + h, GF + h + 0.04) for h in (0.45, 0.9, 1.35, 1.8, 2.2)], "shelf")
# kitchen and dining
box("interior", "render", 0.6, 4.4, -1.6, -0.6, GF, GF + 0.92, 0.03, "island")
box("interior", "oak", 0.5, 4.5, -1.7, -0.5, GF + 0.92, GF + 0.97, name="island_top")
box("interior", "render", -0.6, 6.6, 3.5, 4.15, GF, GF + 0.92, name="kitchen_run")
box("interior", "oak", 1.0, 4.0, 1.4, 2.5, GF + 0.72, GF + 0.77, name="dining_top")
merge("interior", "steel", [(1.1, 1.18, 1.5, 1.58, GF, GF + 0.72), (3.82, 3.9, 1.5, 1.58, GF, GF + 0.72), (1.1, 1.18, 2.32, 2.4, GF, GF + 0.72), (3.82, 3.9, 2.32, 2.4, GF, GF + 0.72)], "dining_legs")
# studio upstairs: desk, chair and three monitors
box("interior", "oak", -4.8, -1.0, -5.6, -4.8, FF + 0.72, FF + 0.77, name="desk_top")
merge("interior", "steel", [(-4.75, -4.65, -5.55, -4.85, FF, FF + 0.72), (-1.15, -1.05, -5.55, -4.85, FF, FF + 0.72)], "desk_legs")
box("interior", "fabric", -3.3, -2.5, -4.4, -3.6, FF + 0.42, FF + 0.5, 0.04, "chair_seat")
box("interior", "fabric", -3.3, -2.5, -3.7, -3.6, FF + 0.5, FF + 1.2, 0.04, "chair_back")
for i, cx in enumerate((-4.1, -2.9, -1.7)):
    angle = (i - 1) * -0.35
    bm = bmesh.new()
    pw.add_box(bm, (0, 0, 0), (1.1, 0.06, 0.66))
    bmesh.ops.rotate(bm, verts=bm.verts[:], cent=(0, 0, 0), matrix=Matrix.Rotation(angle, 3, "Z"))
    bmesh.ops.translate(bm, verts=bm.verts[:], vec=Vector((cx, -5.35, FF + 1.25)))
    frame = pw.bm_object(f"monitor_{i}", bm, M["steel"])
    frame.parent = groups["interior"]
    bm = bmesh.new()
    uv_layer = bm.loops.layers.uv.new("UVMap")
    corners = [Vector((-0.5, 0, -0.29)), Vector((0.5, 0, -0.29)), Vector((0.5, 0, 0.29)), Vector((-0.5, 0, 0.29))]
    rot = Matrix.Rotation(angle, 3, "Z")
    verts = [bm.verts.new(rot @ c + Vector((cx, -5.39, FF + 1.25))) for c in corners]
    face = bm.faces.new(verts)
    for loop, uv in zip(face.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        loop[uv_layer].uv = uv
    screen = pw.bm_object(f"screen_{i}", bm, M["screen"])
    screen.parent = groups["interior"]
    bm = bmesh.new()
    pw.add_box(bm, (cx, -5.3, FF + 0.85), (0.08, 0.08, 0.2))
    stand = pw.bm_object(f"stand_{i}", bm, M["steel"])
    stand.parent = groups["interior"]
# bedroom upstairs
box("interior", "oak", 0.4, 3.6, 0.8, 3.5, FF, FF + 0.35, 0.03, "bed_base")
box("interior", "linen", 0.5, 3.5, 0.9, 3.0, FF + 0.35, FF + 0.6, 0.06, "bed_duvet")
box("interior", "linen", 0.7, 3.3, 2.9, 3.4, FF + 0.35, FF + 0.75, 0.08, "bed_pillows")

pw.empty("anchor_studio", (-2.9, -5.2, FF + 1.2))
pw.empty("anchor_house", (0.0, -1.0, 3.5))
pw.export_glb(args.out)
