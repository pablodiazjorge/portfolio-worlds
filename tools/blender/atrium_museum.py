"""ATRIUM: a gothic gallery hall, after the reference painting: a tall nave of cream stone with
pointed stained-glass windows between navy panels that carry the paintings, crimson banners,
candle chandeliers under a ribbed vault, a balcony over the arch to the second room, a stone
pedestal with a statue in the middle of the hall ringed by velvet ropes, glass cases with open
books along the sides, marble busts, a bench and a lectern by the entrance.

Blender axes: X across, Y forward into the museum, Z up. One unit is one metre.
Groups: solid (what the visitor collides with), decor (no collision), exhibits (textured quads).
Quads with UVs that receive runtime textures: canvas_0..12, label_0..12, exp_0..4, about_panel,
contact_panel, sign_hall, sign_wing. Empties: spawn, spot_* (where the visitor stands to look),
light_* (picture light positions), candle_* (chandelier and sconce flames), window_* (window
centres, for the light shafts).
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

# --- proportions -------------------------------------------------------------------------------
HW = 6.0  # half width of the nave
WALL = 10.0  # height of the walls, where the vault springs
APEX = 16.6  # height of the vault's point
T = 0.5  # wall thickness
BAY = 3.75  # one window or one painting panel per bay
Y0, Y_ARCH, Y1 = -16.0, 14.0, 36.5  # entrance wall, the arch to the second room, the far wall

M = {
    "stone": pw.material("stone", "#e6ddcd", 0.85),
    "stone_dark": pw.material("stone_dark", "#cfc2ad", 0.85),
    "vault": pw.material("vault", "#ece5d8", 0.9),
    "rib": pw.material("rib", "#9e8c6c", 0.85),
    "panel_blue": pw.material("panel_blue", "#1d2b4f", 0.8),
    "gold": pw.material("gold", "#c9a24e", 0.3, 1.0),
    "brass": pw.material("brass", "#a8823f", 0.35, 1.0),
    "crimson": pw.material("crimson", "#8c1f2f", 0.85),
    "wood": pw.material("wood", "#3a2619", 0.6),
    "velvet": pw.material("velvet", "#9d1f2e", 0.9),
    "marble": pw.material("marble", "#f1ede6", 0.3),
    "statue": pw.material("statue", "#a9a7a3", 0.7),
    "plinth": pw.material("plinth", "#3b3d42", 0.75),
    "glass": pw.vertex_color_material("glass", roughness=0.4),
    "lead": pw.material("lead", "#15151a", 0.9),
    "case_glass": pw.material("case_glass", "#dfe8f0", 0.05, alpha=0.18),
    "candle": pw.material("candle", "#f3e8cf", 0.6),
    "flame": pw.material("flame", "#ffd27a", 0.5, emission="#ffb13a", emission_strength=6.0),
    "iron": pw.material("iron", "#2b2c30", 0.5, 0.8),
    "floor": pw.material("floor", "#ded6c8", 0.2),
    "canvas": pw.material("canvas", "#222222", 0.8),
    "label": pw.material("label", "#f4f2ee", 0.7),
    "paper": pw.material("paper", "#f3ead6", 0.8),
    "lightbox": pw.material("lightbox", "#f6efe0", 0.8),
    "screen": pw.material("screen", "#2a3238", 0.3),
}

groups = {name: pw.empty(name, (0, 0, 0)) for name in ("solid", "decor", "exhibits")}
n = {"i": 0}


def obj(name, bm, mat, group, smooth=False):
    o = pw.bm_object(name, bm, M[mat] if isinstance(mat, str) else mat, smooth=smooth)
    o.parent = groups[group]
    return o


def box(group, mat, x0, x1, y0, y1, z0, z1, name=None):
    bm = bmesh.new()
    pw.add_box(bm, ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), (x1 - x0, y1 - y0, z1 - z0))
    n["i"] += 1
    return obj(name or f"{group}_{n['i']}", bm, mat, group)


def cyl(group, mat, a, b, r, seg=12, name=None, r2=None):
    bm = bmesh.new()
    a, b = Vector(a), Vector(b)
    d = b - a
    vs = pw.add_cone(bm, (0, 0, 0), r, r if r2 is None else r2, max(d.length, 1e-4), segments=seg)
    rotation = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix()
    bmesh.ops.rotate(bm, verts=vs, cent=(0, 0, 0), matrix=rotation)
    bmesh.ops.translate(bm, verts=vs, vec=a)
    n["i"] += 1
    return obj(name or f"{group}_{n['i']}", bm, mat, group, smooth=seg >= 10)


def quad(name, mat, centre, width, height, facing, group="exhibits", tilt=0.0, yaw=0.0):
    """A quad with UVs facing `facing` ('n', 's', 'e', 'w', 'up'); `tilt` leans a wall quad back
    and `yaw` turns a flat one, so its top edge faces away from whoever reads it."""
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    hw, hh = width / 2, height / 2
    if facing == "up":
        corners = [(-hw, -hh, 0), (hw, -hh, 0), (hw, hh, 0), (-hw, hh, 0)]
    elif facing in ("n", "s"):
        sign = 1 if facing == "s" else -1
        corners = [(-hw * sign, 0, -hh), (hw * sign, 0, -hh), (hw * sign, 0, hh), (-hw * sign, 0, hh)]
    else:
        sign = 1 if facing == "w" else -1
        corners = [(0, hw * sign, -hh), (0, -hw * sign, -hh), (0, -hw * sign, hh), (0, hw * sign, hh)]
    if tilt:
        rot = Matrix.Rotation(tilt, 3, "X")
        corners = [tuple(rot @ Vector(c)) for c in corners]
    if yaw:
        rot = Matrix.Rotation(yaw, 3, "Z")
        corners = [tuple(rot @ Vector(c)) for c in corners]
    verts = [bm.verts.new(Vector(centre) + Vector(c)) for c in corners]
    face = bm.faces.new(verts)
    for loop, coords in zip(face.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        loop[uv].uv = coords
    face.normal_update()
    return obj(name, bm, mat, group)


def arch(hw, z_spring, z_apex, steps=14):
    """Points of a pointed arch from the left springing over the point to the right, in (x, z)."""
    h = z_apex - z_spring
    c = (h * h - hw * hw) / (2 * hw)  # centres sit on the springing line, outside the opening
    R = hw + c
    t_top = math.acos(c / R)
    left = [(c - R * math.cos(t), z_spring + R * math.sin(t)) for t in (t_top * i / steps for i in range(steps + 1))]
    right = [(-x, z) for x, z in reversed(left[:-1])]
    return left + right


def pierced_wall(name, mat, group, axis, at, u0, u1, z0, z1, hole, thickness=T):
    """A slab of wall in the plane `axis` = `at` ('y' for a wall across X, 'x' for a wall along
    Y), spanning u0..u1 sideways and z0..z1 up, with a hole whose outline is `hole`, a list of
    (u, z) points in order. The slab's faces are the ring between the hole and the rectangle:
    every hole point is sent out from the hole's own centre to the rectangle's edge, and the
    rectangle's corners are stitched in wherever two neighbouring rays land on different edges."""
    bm = bmesh.new()
    hc_u = (min(u for u, _ in hole) + max(u for u, _ in hole)) / 2
    hc_z = (min(z for _, z in hole) + max(z for _, z in hole)) / 2
    corners = [(u0, z0), (u1, z0), (u1, z1), (u0, z1)]
    ccw = sum(hole[i][0] * hole[(i + 1) % len(hole)][1] - hole[(i + 1) % len(hole)][0] * hole[i][1] for i in range(len(hole))) > 0

    def rim(u, z):
        # the hole's point sent outwards from the hole's centre to the rectangle's edge
        du, dz = u - hc_u, z - hc_z
        s = min(((u1 if du > 0 else u0) - hc_u) / du if du else 1e9, ((z1 if dz > 0 else z0) - hc_z) / dz if dz else 1e9)
        return (hc_u + du * s, hc_z + dz * s)

    def angle(u, z):
        return math.atan2(z - hc_z, u - hc_u)

    def sweep(a, b):
        # how far round the hole's centre it is from direction a to direction b, the hole's way
        d = (b - a) if ccw else (a - b)
        return d % math.tau

    def corners_between(a, b):
        # the rectangle's corners passed when walking its edge from rim point a to rim point b
        extent = sweep(angle(*a), angle(*b))
        if extent > math.pi:
            return []
        found = [(sweep(angle(*a), angle(*c)), c) for c in corners]
        return [c for d, c in sorted(found) if 1e-6 < d < extent - 1e-6]

    def place(u, z, depth):
        return Vector((u, at + depth, z)) if axis == "y" else Vector((at + depth, u, z))

    m = len(hole)
    rims = [rim(u, z) for u, z in hole]
    front_in = [bm.verts.new(place(u, z, -thickness / 2)) for u, z in hole]
    back_in = [bm.verts.new(place(u, z, thickness / 2)) for u, z in hole]
    front_out = [bm.verts.new(place(u, z, -thickness / 2)) for u, z in rims]
    back_out = [bm.verts.new(place(u, z, thickness / 2)) for u, z in rims]
    for i in range(m):
        j = (i + 1) % m
        between = corners_between(rims[i], rims[j])
        front_path = [front_out[i]] + [bm.verts.new(place(u, z, -thickness / 2)) for u, z in between] + [front_out[j]]
        back_path = [back_out[i]] + [bm.verts.new(place(u, z, thickness / 2)) for u, z in between] + [back_out[j]]
        bm.faces.new([front_in[i], front_in[j]] + list(reversed(front_path)))
        bm.faces.new([back_in[j], back_in[i]] + back_path)
        bm.faces.new((front_in[j], front_in[i], back_in[i], back_in[j]))  # the reveal
        for a, b in zip(front_path, front_path[1:]):
            bb = back_path[front_path.index(b)]
            ba = back_path[front_path.index(a)]
            bm.faces.new((a, b, bb, ba))  # the slab's edge
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-4)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return obj(name, bm, mat, group)


def loft(bm, rings, close=False, closed=True):
    """Skins consecutive rings of bmesh verts; `close` joins the last ring to the first, and
    `closed=False` leaves each ring open between its last point and its first."""
    count = len(rings[0])
    pairs = list(zip(rings, rings[1:])) + ([(rings[-1], rings[0])] if close else [])
    for a, b in pairs:
        for i in range(count if closed else count - 1):
            j = (i + 1) % count
            if a[i] is b[i]:
                continue
            bm.faces.new((a[i], a[j], b[j], b[i]))


def tube(bm, points, radius, sides=8):
    """A round tube through a polyline of Vectors."""
    rings = []
    for k, p in enumerate(points):
        prev = points[max(k - 1, 0)]
        nxt = points[min(k + 1, len(points) - 1)]
        t = (nxt - prev).normalized()
        ref = Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))
        a = t.cross(ref).normalized()
        b = t.cross(a).normalized()
        rings.append([bm.verts.new(p + (a * math.cos(s / sides * math.tau) + b * math.sin(s / sides * math.tau)) * radius) for s in range(sides)])
    for ring_a, ring_b in zip(rings, rings[1:]):
        for s in range(sides):
            bm.faces.new((ring_a[s], ring_a[(s + 1) % sides], ring_b[(s + 1) % sides], ring_b[s]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])


# --- the stained glass -------------------------------------------------------------------------
PALETTE = [
    ("#2f5fb8", 3), ("#4a86d8", 3), ("#b8262d", 2), ("#e0a62a", 3), ("#f1e3b0", 6),
    ("#2f7c45", 2), ("#7a3fa0", 1), ("#e8773a", 1), ("#f7f1dc", 7), ("#dfe9f7", 4), ("#fbe7c8", 3),
]
PALETTE_WEIGHTED = [c for c, w in PALETTE for _ in range(w)]


def inside_arch(u, z, hw, z_sill, z_spring, z_apex):
    if z < z_sill or abs(u) > hw:
        return False
    if z <= z_spring:
        return True
    h = z_apex - z_spring
    c = (h * h - hw * hw) / (2 * hw)
    R = hw + c
    return (abs(u) + c) ** 2 + (z - z_spring) ** 2 <= R * R


def stained_window(name, axis, at, u_centre, hw, z_sill, z_spring, z_apex, cell=0.24, depth=0.0):
    """Mosaic cells inside a pointed arch, coloured by vertex, over a dark lead backing."""
    bm = bmesh.new()
    colors = []
    cols = int(2 * hw / cell) + 1
    rows = int((z_apex - z_sill) / cell) + 1
    jitter = cell * 0.18

    def place(u, z):
        return Vector((u, at + depth, z)) if axis == "y" else Vector((at + depth, u, z))

    # colours come in patches, the way a figure's robe or a patch of sky is many panes of one
    # glass: a handful of seeds, each pane takes the colour of the nearest one. A border of
    # alternating red and gold runs round the edge, and the tracery circle glows warm.
    seeds = []
    for _ in range(int(14 + hw * 8)):
        seeds.append((rng.uniform(-hw, hw), rng.uniform(z_sill, z_apex), rng.choice(PALETTE_WEIGHTED)))
    border_colors = ["#b8262d", "#e0a62a"]
    for j in range(rows):
        for i in range(cols):
            u = u_centre - hw + (i + 0.5) * cell
            z = z_sill + (j + 0.5) * cell
            if not inside_arch(u - u_centre, z, hw - 0.04, z_sill, z_spring, z_apex):
                continue
            if abs(u - u_centre) < 0.05 and z < z_spring + hw * 0.6:
                continue  # the mullion
            edge = not inside_arch(u - u_centre, z, hw - cell - 0.04, z_sill + cell, z_spring, z_apex - cell)
            ring = math.hypot(u - u_centre, z - (z_spring + hw * 0.95))
            if ring < hw * 0.55:
                color = rng.choice(["#e0a62a", "#f1e3b0", "#b8262d", "#f7f1dc"])
            elif edge:
                color = border_colors[(i + j) % 2]
            else:
                du = u - u_centre
                color = min(seeds, key=lambda sd: (sd[0] - du) ** 2 + (sd[1] - z) ** 2 * 0.6)[2]
            # a few panes are a strip two cells tall, like the long folds of a robe
            tall = not edge and rng.random() < 0.15 and j + 1 < rows
            h = cell * (2 if tall else 1) - 0.035
            w = cell - 0.035
            c = (u + rng.uniform(-jitter, jitter) * 0.3, z + (h - cell) / 2)
            pts = [place(c[0] - w / 2, c[1] - h / 2), place(c[0] + w / 2, c[1] - h / 2), place(c[0] + w / 2, c[1] + h / 2), place(c[0] - w / 2, c[1] + h / 2)]
            vs = [bm.verts.new(p) for p in pts]
            bm.faces.new(vs)
            rgba = pw.hex_color(color)
            colors.extend([rgba] * 4)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    o = obj(name, bm, "glass", "decor")
    pw.set_vertex_colors(o, colors)
    # the lead backing: a dark sheet behind the cells, just outside
    bm = bmesh.new()
    outline = arch(hw, z_spring, z_apex, 12)
    pts = [place(u_centre + u, z) for u, z in outline] + [place(u_centre + hw, z_sill), place(u_centre - hw, z_sill)]
    face = bm.faces.new([bm.verts.new(p + (Vector((0, 0.06, 0)) if axis == "y" else Vector((0.06, 0, 0))) * (1 if depth >= 0 else -1)) for p in pts])
    face.normal_update()
    obj(name + "_lead", bm, "lead", "decor")
    # mullion and the tracery ring in stone
    if hw > 0.8:
        mu = place(u_centre, (z_sill + z_spring + hw * 0.6) / 2)
        if axis == "y":
            box("decor", "stone", u_centre - 0.06, u_centre + 0.06, at - 0.12, at + 0.12, z_sill, z_spring + hw * 0.6, name + "_mullion")
        else:
            box("decor", "stone", at - 0.12, at + 0.12, u_centre - 0.06, u_centre + 0.06, z_sill, z_spring + hw * 0.6, name + "_mullion")
        bm = bmesh.new()
        centre = place(u_centre, z_spring + hw * 0.95)
        ring_pts = [centre + (Vector((math.cos(a) * hw * 0.55, 0, math.sin(a) * hw * 0.55)) if axis == "y" else Vector((0, math.cos(a) * hw * 0.55, math.sin(a) * hw * 0.55))) for a in (k / 20 * math.tau for k in range(21))]
        tube(bm, ring_pts, 0.06, sides=6)
        obj(name + "_tracery", bm, "stone", "decor")


# --- walls, windows and panels -----------------------------------------------------------------
# bays along both side walls: windows and painting panels alternate, a window first
SILL, SPRING, WAPEX, WHW = 2.9, 7.4, 9.3, 1.25
PANEL_W, PANEL_H, PANEL_Z = 3.0, 3.6, 3.6

paintings = []  # (facing, x, y, scale)
window_slots = []
bays = []
y = Y0
while y + BAY <= Y1 + 1e-6:
    bays.append((y, y + BAY))
    y += BAY

for side in (-1, 1):
    x_face = side * HW
    facing = "e" if side < 0 else "w"  # the side the wall shows to the nave
    for k, (b0, b1) in enumerate(bays):
        yc = (b0 + b1) / 2
        is_window = k % 2 == 0 or k == len(bays) - 1
        # the lower wall, solid, carries the collision; the upper part is decor
        if is_window:
            box("solid", "stone", min(x_face - T / 2, x_face + T / 2), max(x_face - T / 2, x_face + T / 2), b0, b1, 0, SILL, f"wall_{side}_{k}_low")
            hole = [(yc + u * (1 if side < 0 else -1), z) for u, z in arch(WHW, SPRING, WAPEX, 12)] + [(yc + WHW * (1 if side < 0 else -1), SILL), (yc - WHW * (1 if side < 0 else -1), SILL)]
            pierced_wall(f"wall_{side}_{k}", "stone", "decor", "x", x_face, b0, b1, SILL - 0.3, WALL, hole)
            # a sill ledge and the glass, set into the opening
            box("decor", "stone_dark", x_face - T / 2 - 0.12 * (side < 0), x_face + T / 2 + 0.12 * (side > 0), yc - WHW - 0.2, yc + WHW + 0.2, SILL - 0.12, SILL + 0.06, f"sill_{side}_{k}")
            stained_window(f"window_{side}_{k}", "x", x_face, yc, WHW, SILL, SPRING, WAPEX, depth=side * 0.12)
            pw.empty(f"window_{side}_{k}_at", (x_face, yc, (SILL + WAPEX) / 2))
            window_slots.append((side, yc))
        else:
            box("solid", "stone", min(x_face - T / 2, x_face + T / 2), max(x_face - T / 2, x_face + T / 2), b0, b1, 0, WALL, f"wall_{side}_{k}")
            # the navy panel with a stone moulding round it
            inner = x_face - side * (T / 2 + 0.03)
            box("decor", "stone_dark", min(inner, inner - side * 0.14), max(inner, inner - side * 0.14), yc - PANEL_W / 2 - 0.2, yc + PANEL_W / 2 + 0.2, PANEL_Z - PANEL_H / 2 - 0.2, PANEL_Z + PANEL_H / 2 + 0.2, f"moulding_{side}_{k}")
            box("decor", "panel_blue", min(inner - side * 0.14, inner - side * 0.17), max(inner - side * 0.14, inner - side * 0.17), yc - PANEL_W / 2, yc + PANEL_W / 2, PANEL_Z - PANEL_H / 2, PANEL_Z + PANEL_H / 2, f"panel_{side}_{k}")
            paintings.append((facing, inner - side * 0.17, yc, 1.0))
        # pilasters between bays, with a gold capital and a base
        xp = x_face - side * (T / 2 + 0.2)
        box("solid", "stone", min(xp - 0.2, xp + 0.2), max(xp - 0.2, xp + 0.2), b1 - 0.3, b1 + 0.3, 0, WALL, f"pilaster_{side}_{k}")
        box("decor", "stone_dark", min(xp - 0.28, xp + 0.28), max(xp - 0.28, xp + 0.28), b1 - 0.38, b1 + 0.38, 0, 0.6, f"pilaster_base_{side}_{k}")
        box("decor", "gold", min(xp - 0.3, xp + 0.3), max(xp - 0.3, xp + 0.3), b1 - 0.4, b1 + 0.4, WALL - 0.55, WALL - 0.3, f"capital_{side}_{k}")
        box("decor", "stone_dark", min(xp - 0.34, xp + 0.34), max(xp - 0.34, xp + 0.34), b1 - 0.44, b1 + 0.44, WALL - 0.3, WALL, f"abacus_{side}_{k}")
    # a cornice along the top of the wall and a plinth course along the bottom
    box("decor", "stone_dark", min(x_face - T / 2, x_face - side * (T / 2 + 0.35)), max(x_face + T / 2, x_face - side * (T / 2 + 0.35)), Y0, Y1, WALL - 0.3, WALL, f"cornice_{side}")
    box("decor", "stone_dark", min(x_face - T / 2, x_face - side * (T / 2 + 0.1)), max(x_face + T / 2, x_face - side * (T / 2 + 0.1)), Y0, Y1, 0, 0.5, f"plinth_course_{side}")

# the entrance wall with a tall doorway, closed by a dark wooden door
DOOR_HW, DOOR_Z = 1.6, 4.4
hole = [(u, z) for u, z in arch(DOOR_HW, DOOR_Z, DOOR_Z + 2.0, 10)] + [(DOOR_HW, 0.0), (-DOOR_HW, 0.0)]
pierced_wall("wall_entrance", "stone", "decor", "y", Y0, -HW - T, HW + T, -0.2, APEX + 0.5, hole)
box("solid", "stone", -HW - T, -DOOR_HW, Y0 - T / 2, Y0 + T / 2, 0, 0.1, "entrance_l")
box("solid", "stone", DOOR_HW, HW + T, Y0 - T / 2, Y0 + T / 2, 0, 0.1, "entrance_r")
box("solid", "wood", -DOOR_HW, DOOR_HW, Y0 - 0.1, Y0 + 0.1, 0, DOOR_Z + 2.0, "door")
for k in range(5):
    box("decor", "iron", -DOOR_HW + 0.1, DOOR_HW - 0.1, Y0 + 0.1, Y0 + 0.14, 0.8 + k * 1.0, 0.86 + k * 1.0, f"door_band_{k}")

# the arch between the two rooms, with the balcony above it
ARCH_HW, ARCH_SPRING, ARCH_APEX = 3.2, 6.0, 9.7
hole = [(u, z) for u, z in arch(ARCH_HW, ARCH_SPRING, ARCH_APEX, 14)] + [(ARCH_HW, 0.0), (-ARCH_HW, 0.0)]
pierced_wall("wall_arch", "stone", "decor", "y", Y_ARCH, -HW - T, HW + T, -0.2, WALL, hole, thickness=0.9)
box("solid", "stone", -HW - T, -ARCH_HW, Y_ARCH - 0.45, Y_ARCH + 0.45, 0, 0.1, "arch_l")
box("solid", "stone", ARCH_HW, HW + T, Y_ARCH - 0.45, Y_ARCH + 0.45, 0, 0.1, "arch_r")
# the balcony: a slab over the arch, a balustrade and the big window behind it
BALC_Z = 10.4
box("decor", "stone", -HW, HW, Y_ARCH - 1.6, Y_ARCH + 0.45, BALC_Z - 0.35, BALC_Z, "balcony_slab")
box("decor", "stone_dark", -HW, HW, Y_ARCH - 1.75, Y_ARCH - 1.6, BALC_Z - 0.5, BALC_Z, "balcony_edge")
for i in range(26):
    xb = -HW + 0.35 + i * (2 * HW - 0.7) / 25
    cyl("decor", "marble", (xb, Y_ARCH - 1.5, BALC_Z), (xb, Y_ARCH - 1.5, BALC_Z + 0.95), 0.07, seg=8, name=f"baluster_{i}")
    cyl("decor", "marble", (xb, Y_ARCH - 1.5, BALC_Z + 0.35), (xb, Y_ARCH - 1.5, BALC_Z + 0.6), 0.11, seg=8, name=f"baluster_belly_{i}")
box("decor", "marble", -HW, HW, Y_ARCH - 1.62, Y_ARCH - 1.38, BALC_Z + 0.95, BALC_Z + 1.1, "balcony_rail")
box("decor", "crimson", -2.6, 2.6, Y_ARCH - 1.72, Y_ARCH - 1.66, BALC_Z - 1.1, BALC_Z + 1.12, "balcony_drape")
box("decor", "gold", -2.6, 2.6, Y_ARCH - 1.74, Y_ARCH - 1.66, BALC_Z - 1.1, BALC_Z - 0.95, "balcony_drape_fringe")
box("decor", "gold", -2.7, 2.7, Y_ARCH - 1.74, Y_ARCH - 1.36, BALC_Z + 1.1, BALC_Z + 1.16, "balcony_drape_bar")
box("decor", "marble", -HW, HW, Y_ARCH - 1.62, Y_ARCH - 1.38, BALC_Z, BALC_Z + 0.1, "balcony_rail_low")
# a thin wall above the balcony, pierced by a great window
GW_HW, GW_SILL, GW_SPRING, GW_APEX = 2.4, BALC_Z + 1.2, BALC_Z + 3.6, BALC_Z + 5.4
hole = [(u, z) for u, z in arch(GW_HW, GW_SPRING, GW_APEX, 14)] + [(GW_HW, GW_SILL), (-GW_HW, GW_SILL)]
pierced_wall("wall_gallery", "stone", "decor", "y", Y_ARCH + 0.2, -HW - T, HW + T, BALC_Z, APEX + 0.5, hole, thickness=0.5)
stained_window("window_gallery", "y", Y_ARCH + 0.2, 0.0, GW_HW, GW_SILL, GW_SPRING, GW_APEX, cell=0.26, depth=0.0)
pw.empty("window_gallery_at", (0, Y_ARCH + 0.2, (GW_SILL + GW_APEX) / 2))

# the far wall of the second room: the featured painting under a rose of glass
pierced_wall("wall_far", "stone", "decor", "y", Y1, -HW - T, HW + T, -0.2, APEX + 0.5, [(u, z) for u, z in arch(2.2, 9.4, 11.2, 12)] + [(2.2, 7.6), (-2.2, 7.6)])
box("solid", "stone", -HW - T, HW + T, Y1 - T / 2, Y1 + T / 2, 0, 0.1, "far_low")
stained_window("window_far", "y", Y1, 0.0, 2.2, 7.6, 9.4, 11.2, cell=0.26, depth=0.12)
pw.empty("window_far_at", (0, Y1, 9.4))
box("decor", "stone_dark", -2.9, 2.9, Y1 - T / 2 - 0.14, Y1 - T / 2, 1.0, 6.6, "far_moulding")
box("decor", "panel_blue", -2.6, 2.6, Y1 - T / 2 - 0.17, Y1 - T / 2 - 0.14, 1.3, 6.3, "far_panel")
paintings.append(("s", 0.0, Y1 - T / 2 - 0.17, 1.9))

# --- the vault -----------------------------------------------------------------------------------
section = arch(HW + T, WALL, APEX, 16)
for (ya, yb, name) in ((Y0 - T, Y_ARCH, "vault_main"), (Y_ARCH, Y1 + T, "vault_second")):
    bm = bmesh.new()
    rings = [[bm.verts.new(Vector((u, yy, z))) for u, z in section] for yy in (ya, yb)]
    loft(bm, rings, closed=False)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    for f in bm.faces:
        if f.normal.z > 0:
            f.normal_flip()
    obj(name, bm, "vault", "decor", smooth=True)
# ribs: one at every bay line, and a ridge along the point
def inset(points, d):
    """The arch's points moved inwards (towards the hall) by `d` along the curve's normal."""
    out = []
    for i, (u, z) in enumerate(points):
        u0, z0 = points[max(i - 1, 0)]
        u1, z1 = points[min(i + 1, len(points) - 1)]
        tu, tz = u1 - u0, z1 - z0
        length = math.hypot(tu, tz) or 1.0
        nu, nz = -tz / length, tu / length
        if nu * (0 - u) + nz * (WALL - z) < 0:
            nu, nz = -nu, -nz
        out.append(Vector((u + nu * d, 0, z + nz * d)))
    return out


rib_section = inset(arch(HW + T, WALL, APEX, 16), 0.1)
diag_section = inset(arch(HW + T, WALL, APEX, 16), 0.04)
for (b0, b1) in bays:
    bm = bmesh.new()
    tube(bm, [Vector((p.x, b0, p.z)) for p in rib_section], 0.2, sides=6)
    obj(f"rib_{b0}", bm, "rib", "decor")
    # the diagonal ribs: from each corner of the bay up to the crown in the middle
    for (ya, yb) in ((b0, b1), (b1, b0)):
        bm = bmesh.new()
        pts = []
        for i, p in enumerate(diag_section):
            t = i / (len(diag_section) - 1)
            yy = ya + (yb - ya) * t
            pts.append(Vector((p.x, yy, p.z)))
        tube(bm, pts, 0.14, sides=5)
        obj(f"rib_diag_{b0}_{ya}", bm, "rib", "decor")
    bm = bmesh.new()
    pw.add_ico(bm, (0, (b0 + b1) / 2, APEX - 0.2), 0.3, 1)
    obj(f"boss_{b0}", bm, "gold", "decor", smooth=True)
bm = bmesh.new()
tube(bm, [Vector((0, yy, APEX - 0.08)) for yy in (Y0, Y1)], 0.18, sides=6)
obj("ridge_rib", bm, "rib", "decor")

# --- the floor: cream marble with the inlay drawn at runtime ------------------------------------
box("decor", "floor", -HW - T, HW + T, Y0 - T, Y1 + T, -0.1, 0, "floor")

# --- paintings -------------------------------------------------------------------------------------
CW, CH = 2.4, 1.5
for i, (facing, px, py, scale) in enumerate(paintings):
    w, h = CW * scale, CH * scale
    z = PANEL_Z if scale == 1 else 4.0
    if facing in ("e", "w"):
        d = 1 if facing == "e" else -1
        # a gold frame: four bars round the canvas, and the canvas a hair in front of the panel
        for (yy0, yy1, zz0, zz1) in ((py - w / 2 - 0.16, py + w / 2 + 0.16, z - h / 2 - 0.16, z - h / 2), (py - w / 2 - 0.16, py + w / 2 + 0.16, z + h / 2, z + h / 2 + 0.16), (py - w / 2 - 0.16, py - w / 2, z - h / 2, z + h / 2), (py + w / 2, py + w / 2 + 0.16, z - h / 2, z + h / 2)):
            box("decor", "gold", min(px, px + 0.08 * d), max(px, px + 0.08 * d), yy0, yy1, zz0, zz1)
        quad(f"canvas_{i}", "canvas", (px + 0.02 * d, py, z), w, h, facing)
        quad(f"label_{i}", "label", (px + 0.01 * d, py, z - h / 2 - 0.42), 0.6, 0.26, facing)
        pw.empty(f"spot_canvas_{i}", (px + 3.2 * d, py, 0))
        pw.empty(f"light_{i}", (px + 0.3 * d, py, z + h / 2 + 0.5))
    else:
        for (xx0, xx1, zz0, zz1) in ((px - w / 2 - 0.2, px + w / 2 + 0.2, z - h / 2 - 0.2, z - h / 2), (px - w / 2 - 0.2, px + w / 2 + 0.2, z + h / 2, z + h / 2 + 0.2), (px - w / 2 - 0.2, px - w / 2, z - h / 2, z + h / 2), (px + w / 2, px + w / 2 + 0.2, z - h / 2, z + h / 2)):
            box("decor", "gold", xx0, xx1, py - 0.08, py, zz0, zz1)
        quad(f"canvas_{i}", "canvas", (px, py - 0.02, z), w, h, facing)
        quad(f"label_{i}", "label", (px, py - 0.01, z - h / 2 - 0.5), 0.8, 0.34, facing)
        pw.empty(f"spot_canvas_{i}", (px, py - 5.5, 0))
        pw.empty(f"light_{i}", (px, py - 0.4, z + h / 2 + 0.5))

# --- banners, sconces, chandeliers ---------------------------------------------------------------
def banner(side, yc, name):
    x = side * (HW - T / 2 - 0.47)  # just in front of the pilaster's face, which stands 0.4 proud of the wall
    top, bottom, w = WALL - 1.4, 3.2, 1.3
    bm = bmesh.new()
    pts = [(x, yc - w / 2, top), (x, yc + w / 2, top), (x, yc + w / 2, bottom + 0.8), (x, yc, bottom), (x, yc - w / 2, bottom + 0.8)]
    face = bm.faces.new([bm.verts.new(Vector(p)) for p in pts])
    face.normal_update()
    if (face.normal.x > 0) != (side < 0):
        face.normal_flip()
    obj(name, bm, "crimson", "decor")
    cyl("decor", "gold", (x, yc - w / 2 - 0.15, top), (x, yc + w / 2 + 0.15, top), 0.04, seg=8, name=name + "_rod")
    # the emblem: a cross with flared ends, in gold
    xe = x - side * 0.02
    zc = (top + bottom) / 2 + 0.5
    arms = [
        (yc - 0.09, yc + 0.09, zc - 1.1, zc + 1.1),  # the upright
        (yc - 0.75, yc + 0.75, zc + 0.16, zc + 0.34),  # the crossbar
        (yc - 0.3, yc + 0.3, zc + 1.0, zc + 1.18),  # flared ends
        (yc - 0.3, yc + 0.3, zc - 1.18, zc - 1.0),
        (yc - 0.78, yc - 0.62, zc - 0.05, zc + 0.55),
        (yc + 0.62, yc + 0.78, zc - 0.05, zc + 0.55),
        (yc - 0.22, yc + 0.22, zc - 0.5, zc - 0.36),  # a lower bar
    ]
    for (y0, y1, z0, z1) in arms:
        box("decor", "gold", min(xe, xe - side * 0.02), max(xe, xe - side * 0.02), y0, y1, z0, z1)
    for k in range(6):
        box("decor", "gold", min(xe, xe - side * 0.01), max(xe, xe - side * 0.01), yc - w / 2 + 0.05 + k * 0.24, yc - w / 2 + 0.15 + k * 0.24, bottom + 0.75 - k * 0.12, bottom + 0.95 - k * 0.12)


def sconce(side, yc, name):
    x = side * (HW - T / 2 - 0.45)
    z = 3.9
    cyl("decor", "gold", (x + side * 0.25, yc, z - 0.6), (x, yc, z), 0.03, seg=6, name=name + "_arm")
    for k, dy in enumerate((-0.22, 0.0, 0.22)):
        cyl("decor", "gold", (x, yc + dy, z - 0.1), (x, yc + dy, z + 0.05), 0.06, seg=8, name=f"{name}_cup_{k}")
        cyl("decor", "candle", (x, yc + dy, z + 0.05), (x, yc + dy, z + 0.4), 0.03, seg=6, name=f"{name}_candle_{k}")
        box("decor", "flame", x - 0.025, x + 0.025, yc + dy - 0.025, yc + dy + 0.025, z + 0.4, z + 0.52, f"{name}_flame_{k}")
    cyl("decor", "gold", (x, yc - 0.3, z - 0.1), (x, yc + 0.3, z - 0.1), 0.025, seg=6, name=name + "_bar")
    pw.empty(f"candle_{name}", (x, yc, z + 0.45))


for side in (-1, 1):
    # banners hang on the pilasters before each panel, sconces on the ones after
    for k in range(1, len(bays) - 1, 2):
        banner(side, bays[k][0], f"banner_{side}_{k}")
        sconce(side, bays[k][1], f"sconce_{side}_{k}")


def chandelier(x, yv, z, name, radius=1.3):
    cyl("decor", "iron", (x, yv, APEX - 0.3), (x, yv, z + 0.9), 0.025, seg=6, name=name + "_chain")
    for tier, (r, dz, count) in enumerate(((radius, 0.0, 10), (radius * 0.55, 0.9, 6))):
        bm = bmesh.new()
        ring_pts = [Vector((x + math.cos(a) * r, yv + math.sin(a) * r, z + dz)) for a in (k / 24 * math.tau for k in range(25))]
        tube(bm, ring_pts, 0.05, sides=6)
        obj(f"{name}_ring_{tier}", bm, "gold", "decor")
        for k in range(count):
            a = k / count * math.tau
            cx, cy = x + math.cos(a) * r, yv + math.sin(a) * r
            cyl("decor", "gold", (cx, cy, z + dz), (cx, cy, z + dz + 0.12), 0.07, seg=8, name=f"{name}_cup_{tier}_{k}")
            cyl("decor", "candle", (cx, cy, z + dz + 0.12), (cx, cy, z + dz + 0.5), 0.035, seg=6, name=f"{name}_candle_{tier}_{k}")
            box("decor", "flame", cx - 0.03, cx + 0.03, cy - 0.03, cy + 0.03, z + dz + 0.5, z + dz + 0.64, f"{name}_flame_{tier}_{k}")
        for k in range(4):
            a = k / 4 * math.tau + 0.4
            cyl("decor", "iron", (x + math.cos(a) * r, yv + math.sin(a) * r, z + dz), (x, yv, z + dz + 1.2), 0.015, seg=4, name=f"{name}_spoke_{tier}_{k}")
    pw.empty(f"candle_{name}", (x, yv, z + 0.6))


for k, yv in enumerate((-9.0, 1.0, 10.0)):
    chandelier(0.0, yv, 8.2, f"chandelier_{k}")
for k, yv in enumerate((20.0, 29.0)):
    chandelier(0.0, yv, 8.2, f"chandelier_second_{k}", radius=1.1)

# --- the centre of the hall: pedestal, ropes and the statue --------------------------------------
# the pedestal stands in a window bay, so its ropes leave the paintings' viewing spots free
PX, PY = 0.0, 0.9
for r, z0, z1 in ((2.7, 0.0, 0.24), (2.25, 0.24, 0.5), (1.85, 0.5, 0.92)):
    bm = bmesh.new()
    vs = pw.add_cone(bm, (0, 0, 0), r, r, z1 - z0, segments=8)
    bmesh.ops.rotate(bm, verts=vs, cent=(0, 0, 0), matrix=Matrix.Rotation(math.radians(22.5), 3, "Z"))
    bmesh.ops.translate(bm, verts=vs, vec=Vector((PX, PY, z0)))
    obj(f"pedestal_{z0}", bm, "marble", "decor")
box("solid", "marble", PX - 2.75, PX + 2.75, PY - 2.75, PY + 2.75, 0, 0.1, "pedestal_collider")
box("decor", "brass", PX - 0.6, PX + 0.6, PY - 1.86, PY - 1.83, 0.52, 0.86, "plaque_back")
quad("about_panel", "label", (PX, PY - 1.87, 0.69), 1.1, 0.3, "s")
pw.empty("spot_about", (PX, PY - 4.6, 0))
for k in range(10):
    a = k / 10 * math.tau
    sx, sy = PX + math.cos(a) * 3.2, PY + math.sin(a) * 3.2
    cyl("decor", "brass", (sx, sy, 0), (sx, sy, 0.06), 0.18, seg=12, name=f"stanchion_base_{k}")
    cyl("decor", "brass", (sx, sy, 0.06), (sx, sy, 0.95), 0.03, seg=8, name=f"stanchion_{k}")
    bm = bmesh.new()
    pw.add_ico(bm, (sx, sy, 1.0), 0.06, 1)
    obj(f"stanchion_knob_{k}", bm, "brass", "decor", smooth=True)
    a2 = (k + 1) / 10 * math.tau
    ex, ey = PX + math.cos(a2) * 3.2, PY + math.sin(a2) * 3.2
    bm = bmesh.new()
    pts = [Vector((sx + (ex - sx) * t, sy + (ey - sy) * t, 0.9 - 0.22 * math.sin(math.pi * t))) for t in (i / 6 for i in range(7))]
    tube(bm, pts, 0.03, sides=6)
    obj(f"rope_{k}", bm, "velvet", "decor")
box("solid", "brass", PX - 3.3, PX + 3.3, PY - 3.3, PY - 3.1, 0, 0.1, "ropes_s")
box("solid", "brass", PX - 3.3, PX + 3.3, PY + 3.1, PY + 3.3, 0, 0.1, "ropes_n")
box("solid", "brass", PX - 3.3, PX - 3.1, PY - 3.3, PY + 3.3, 0, 0.1, "ropes_w")
box("solid", "brass", PX + 3.1, PX + 3.3, PY - 3.3, PY + 3.3, 0, 0.1, "ropes_e")

# the statue: a blocky figure in stone hauling an old computer on a cable, leaning into the pull
base = 0.92


def statue_box(name, center, size, yaw=0.0, pitch=0.0):
    bm = bmesh.new()
    vs = pw.add_box(bm, (0, 0, 0), size, 0.0)
    if pitch:
        bmesh.ops.rotate(bm, verts=vs, cent=(0, 0, 0), matrix=Matrix.Rotation(pitch, 3, "X"))
    if yaw:
        bmesh.ops.rotate(bm, verts=vs, cent=(0, 0, 0), matrix=Matrix.Rotation(yaw, 3, "Z"))
    bmesh.ops.translate(bm, verts=vs, vec=Vector(center))
    obj(name, bm, "statue", "decor")


# the figure faces the entrance, leaning south into the pull, the computer dragged behind to the north
fx, fy = PX - 0.3, PY - 0.2
lean = math.radians(16)
statue_box("statue_leg_back", (fx + 0.2, fy + 0.5, base + 0.55), (0.3, 0.3, 1.05), pitch=math.radians(20))
statue_box("statue_foot_back", (fx + 0.2, fy + 0.72, base + 0.08), (0.32, 0.5, 0.16))
statue_box("statue_leg_front", (fx - 0.2, fy - 0.28, base + 0.55), (0.3, 0.3, 1.05), pitch=math.radians(-14))
statue_box("statue_foot_front", (fx - 0.2, fy - 0.5, base + 0.08), (0.32, 0.5, 0.16))
statue_box("statue_hips", (fx, fy, base + 1.12), (0.74, 0.44, 0.3), pitch=lean)
statue_box("statue_torso", (fx + 0.05, fy - 0.14, base + 1.72), (0.8, 0.5, 0.9), pitch=lean)
statue_box("statue_chest_plate", (fx + 0.05, fy - 0.42, base + 1.82), (0.5, 0.06, 0.45), pitch=lean)
statue_box("statue_shoulders", (fx + 0.08, fy - 0.22, base + 2.18), (1.3, 0.4, 0.26), pitch=lean)
statue_box("statue_neck", (fx + 0.12, fy - 0.3, base + 2.36), (0.22, 0.22, 0.16), pitch=lean)
statue_box("statue_head", (fx + 0.16, fy - 0.4, base + 2.66), (0.56, 0.52, 0.52), pitch=lean)
for sx in (-0.58, 0.74):
    statue_box(f"statue_arm_{sx}", (fx + sx, fy + 0.2, base + 1.7), (0.22, 0.22, 0.85), pitch=math.radians(42))
    statue_box(f"statue_forearm_{sx}", (fx + sx, fy + 0.62, base + 1.18), (0.2, 0.2, 0.75), pitch=math.radians(62))
statue_box("statue_hands", (fx + 0.08, fy + 0.92, base + 0.86), (1.4, 0.22, 0.22))
# the screen on the head looks south, and the computer sits behind on a trolley
box("decor", "screen", fx - 0.04, fx + 0.36, fy - 0.68, fy - 0.64, base + 2.52, base + 2.82, "statue_face")
cx, cy = PX + 0.95, PY + 1.0
statue_box("statue_dolly", (cx, cy, base + 0.16), (0.95, 0.75, 0.12))
for wx in (-1, 1):
    for wy in (-1, 1):
        cyl("decor", "statue", (cx + wx * 0.5, cy + wy * 0.28, base + 0.09), (cx + wx * 0.56, cy + wy * 0.28, base + 0.09), 0.09, seg=10, name=f"statue_wheel_{wx}_{wy}")
statue_box("statue_computer", (cx, cy, base + 0.56), (0.72, 0.64, 0.68))
statue_box("statue_computer_top", (cx, cy + 0.06, base + 0.92), (0.66, 0.5, 0.06))
box("decor", "screen", cx - 0.26, cx + 0.26, cy - 0.34, cy - 0.31, base + 0.36, base + 0.78, "statue_computer_screen")
statue_box("statue_keyboard", (cx - 0.05, cy - 0.55, base + 0.26), (0.6, 0.3, 0.06), pitch=math.radians(-8))
bm = bmesh.new()
pull = [Vector((fx + 0.08 + (cx - 0.3 - fx - 0.08) * t, fy + 0.92 + (cy - 0.1 - fy - 0.92) * t, base + 0.86 + (0.7 - 0.86) * t + 0.2 * math.sin(math.pi * t))) for t in (i / 8 for i in range(9))]
tube(bm, pull, 0.035, sides=5)
obj("statue_cable", bm, "iron", "decor")

# --- glass cases with open books: the experience ---------------------------------------------------
cases = [(-1, -6.6), (1, -6.6), (-1, 8.4), (1, 8.4), (-1, 23.4)]
for i, (side, yc) in enumerate(cases):
    x = side * (HW - 2.4)
    box("solid", "plinth", x - 0.8, x + 0.8, yc - 0.55, yc + 0.55, 0, 0.95, f"case_plinth_{i}")
    box("decor", "iron", x - 0.84, x + 0.84, yc - 0.59, yc + 0.59, 0.93, 0.98, f"case_lip_{i}")
    box("decor", "case_glass", x - 0.78, x + 0.78, yc - 0.53, yc + 0.53, 0.98, 1.7, f"case_glass_{i}")
    box("decor", "iron", x - 0.8, x + 0.8, yc - 0.55, yc + 0.55, 1.7, 1.74, f"case_top_{i}")
    box("decor", "velvet", x - 0.7, x + 0.7, yc - 0.45, yc + 0.45, 0.98, 1.02, f"case_cloth_{i}")
    for px_, py_ in ((x - 0.78, yc - 0.53), (x + 0.78, yc - 0.53), (x - 0.78, yc + 0.53), (x + 0.78, yc + 0.53)):
        box("decor", "iron", px_ - 0.02, px_ + 0.02, py_ - 0.02, py_ + 0.02, 0.98, 1.72, f"case_post_{i}_{px_:.1f}_{py_:.1f}")
    # the open book: two leaves rising from the spine towards the visitor's side, the page on top
    facing = "e" if side < 0 else "w"
    bm = bmesh.new()
    for leaf in (-1, 1):
        vs = pw.add_box(bm, (0, 0, 0), (0.56, 0.74, 0.1), 0.0)
        bmesh.ops.rotate(bm, verts=vs, cent=(0, 0, 0), matrix=Matrix.Rotation(-leaf * math.radians(6), 3, "Y"))
        bmesh.ops.translate(bm, verts=vs, vec=Vector((x + leaf * 0.29, yc, 1.09)))
    obj(f"book_block_{i}", bm, "paper", "decor")
    box("decor", "wood", x - 0.04, x + 0.04, yc - 0.37, yc + 0.37, 1.02, 1.07, f"book_spine_{i}")
    quad(f"exp_{i}", "lightbox", (x + side * 0.02, yc, 1.175), 1.1, 0.7, "up", yaw=-side * math.pi / 2)
    quad(f"plaque_exp_{i}", "label", (x - side * 0.81, yc, 0.6), 0.5, 0.2, facing, group="decor")
    pw.empty(f"spot_exp_{i}", (x - side * 1.9, yc, 0))

# --- busts, bench and the lectern ---------------------------------------------------------------------
busts = [(-1, -14.1), (1, -14.1), (-1, 0.9), (1, 0.9), (-1, 15.9), (1, 15.9), (-1, 30.9), (1, 30.9)]
for i, (side, yc) in enumerate(busts):
    x = side * (HW - 0.95)
    box("solid", "plinth", x - 0.3, x + 0.3, yc - 0.3, yc + 0.3, 0, 1.35, f"bust_pedestal_{i}")
    box("decor", "stone_dark", x - 0.34, x + 0.34, yc - 0.34, yc + 0.34, 1.35, 1.42, f"bust_cap_{i}")
    box("decor", "marble", x - 0.3, x + 0.3, yc - 0.2, yc + 0.2, 1.42, 1.72, f"bust_shoulders_{i}")
    cyl("decor", "marble", (x, yc, 1.72), (x, yc, 1.84), 0.1, seg=10, name=f"bust_neck_{i}")
    bm = bmesh.new()
    pw.add_ico(bm, (x, yc, 2.06), 0.24, 2, scale=(0.9, 1.0, 1.25))
    obj(f"bust_head_{i}", bm, "marble", "decor", smooth=True)

box("solid", "wood", -3.75, -3.05, -13.4, -10.8, 0, 0.46, "bench")
box("decor", "velvet", -3.7, -3.1, -13.35, -10.85, 0.46, 0.58, "bench_cushion")
for sx in (-3.65, -3.15):
    for sy in (-13.25, -10.95):
        box("decor", "wood", sx - 0.06, sx + 0.06, sy - 0.06, sy + 0.06, 0, 0.46, f"bench_leg_{sx}_{sy}")

LX, LY = 3.6, -14.2
box("solid", "wood", LX - 0.35, LX + 0.35, LY - 0.3, LY + 0.3, 0, 1.0, "lectern")
box("decor", "wood", LX - 0.45, LX + 0.45, LY - 0.42, LY + 0.3, 1.0, 1.12, "lectern_top")
quad("contact_panel", "label", (LX, LY - 0.05, 1.14), 0.8, 0.5, "up", group="exhibits", yaw=math.pi)
pw.empty("spot_contact", (LX, LY + 1.4, 0))
quad("sign_hall", "label", (0, Y_ARCH - 1.76, BALC_Z + 0.05), 2.4, 0.4, "s")
quad("sign_wing", "label", (-HW + T / 2 + 0.03, -14.0, 1.55), 1.6, 0.44, "e")
pw.empty("spawn", (0, -13.5, 0))

pw.export_glb(args.out)
