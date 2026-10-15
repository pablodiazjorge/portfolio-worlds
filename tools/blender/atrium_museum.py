"""ATRIUM: a gothic gallery hall, after the reference painting: a tall nave of cream stone where
every bay carries a painting on a navy panel below and a two-light stained-glass window above,
clustered piers with gilt capitals, crimson banners hung beside the windows, candle sconces and
chandeliers under a pointed ribbed vault, a balcony with a great window over the pointed arch to
a narrower second room with arcades and side aisles, a stone pedestal with a statue in the middle
of the hall ringed by velvet ropes, ebonised cabinets with the experience in the far room, a bench
and a lectern by the entrance.

Proportions measured against the reference from its own camera (see the reference camera in the
live session: from the east side at 1.6 m, looking north-west): paintings 1.3-5.5 m, window sills
at 6 m, window points at 13.6 m, vault springing at 14.5 m, crown at 22.5 m, bays of 4.5 m.

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
HW = 6.0  # half width of the nave, to the inner face of the walls
T = 0.6  # wall thickness
BAY = 4.5  # one painting below and one window above per bay
Y0, Y_ARCH = -18.0, 18.0  # entrance wall and the arch to the second room: eight bays
SILL, SPRING, WAPEX, WHW = 6.0, 11.0, 13.6, 1.5  # the two-light windows
WALL = 14.5  # where the vault springs
APEX = 22.5  # the vault's point
PANEL_Z0, PANEL_Z1, PANEL_W = 1.3, 5.5, 3.1  # the navy panels behind the paintings
PIER_D, PIER_W = 0.3, 0.9  # the piers stand proud of the wall, with three shafts in front
HW2, WALL2, APEX2 = 4.0, 14.5, 20.5  # the second room: narrower, with arcades to side aisles
AISLE, AISLE_Z = 3.0, 8.6  # the aisles behind the arcades and their flat ceiling
Y1 = Y_ARCH + 6 * BAY  # the far wall: six bays

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
    "shadow_patch": pw.material("shadow_patch", "#000000", 0.9, alpha=0.5),
    "marble": pw.material("marble", "#f1ede6", 0.3),
    "statue": pw.material("statue", "#a9a7a3", 0.7),
    "plinth": pw.material("plinth", "#2b211c", 0.75),
    "glass": pw.material("glass", "#dfe9f7", 0.4),
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
    "collider": pw.material("collider", "#ff00ff", 0.8),  # floor-level colliders, hidden at runtime
}

groups = {name: pw.empty(name, (0, 0, 0)) for name in ("solid", "decor", "exhibits")}
n = {"i": 0}
ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
_asset_cache = {}
_asset_templates = []


def place_asset(asset, location, scale=1.0, yaw=0.0, name=None):
    """A copy of a CC0 model from tools/assets/polyhaven, sharing mesh data with the other copies,
    placed with its origin at `location`, scaled and turned about Z. The first call imports it."""
    if asset not in _asset_cache:
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=os.path.join(ASSETS, asset + ".glb"))
        imported = [o for o in bpy.data.objects if o not in before]
        meshes = [o for o in imported if o.type == "MESH"]
        for o in imported:
            if o.type != "MESH":
                bpy.data.objects.remove(o, do_unlink=True)
        for o in meshes:
            o.parent = None
            o.hide_render = True
            o.hide_viewport = True
            o.location = (0, 0, -100)
        _asset_cache[asset] = meshes
        # the templates themselves must not be exported: they are removed once the last copy exists
        _asset_templates.extend(meshes)
    copies = []
    for k, template in enumerate(_asset_cache[asset]):
        o = template.copy()
        o.hide_render = False
        o.hide_viewport = False
        o.name = f"{name or os.path.basename(asset)}_{k}" if len(_asset_cache[asset]) > 1 else (name or os.path.basename(asset))
        o.location = location
        o.scale = (scale, scale, scale)
        # the glTF importer leaves objects in quaternion mode, where Euler angles are ignored
        o.rotation_mode = "XYZ"
        o.rotation_euler = (0, 0, yaw)
        o.parent = groups["decor"]
        bpy.context.scene.collection.objects.link(o)
        copies.append(o)
    return copies


def obj(name, bm, mat, group, smooth=False):
    o = pw.bm_object(name, bm, M[mat] if isinstance(mat, str) else mat, smooth=smooth)
    o.parent = groups[group]
    return o


def box(group, mat, x0, x1, y0, y1, z0, z1, name=None):
    bm = bmesh.new()
    pw.add_box(bm, ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), (abs(x1 - x0), abs(y1 - y0), abs(z1 - z0)))
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


def prism(group, mat, centre, r, z0, z1, sides, name, phase=0.0):
    """An upright prism with `sides` flat faces, one of them facing -y when phase is half a step."""
    bm = bmesh.new()
    vs = pw.add_cone(bm, (0, 0, 0), r, r, z1 - z0, segments=sides)
    bmesh.ops.rotate(bm, verts=vs, cent=(0, 0, 0), matrix=Matrix.Rotation(phase, 3, "Z"))
    bmesh.ops.translate(bm, verts=vs, vec=Vector((centre[0], centre[1], z0)))
    return obj(name, bm, mat, group)


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


def opening(hw, z_bottom, z_spring, z_apex, steps=14):
    """A pointed opening's outline: the arch over two jambs down to z_bottom."""
    return [(u, z) for u, z in arch(hw, z_spring, z_apex, steps)] + [(hw, z_bottom), (-hw, z_bottom)]


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
        du, dz = u - hc_u, z - hc_z
        s = min(((u1 if du > 0 else u0) - hc_u) / du if du else 1e9, ((z1 if dz > 0 else z0) - hc_z) / dz if dz else 1e9)
        return (hc_u + du * s, hc_z + dz * s)

    def angle(u, z):
        return math.atan2(z - hc_z, u - hc_u)

    def sweep(a, b):
        d = (b - a) if ccw else (a - b)
        return d % math.tau

    def corners_between(a, b):
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
    """A round tube through a polyline of Vectors; the section's frame is carried along the curve
    (parallel transport) so it never flips halfway, as it did with a fixed up vector."""
    rings = []
    a = None
    for k, p in enumerate(points):
        prev = points[max(k - 1, 0)]
        nxt = points[min(k + 1, len(points) - 1)]
        t = (nxt - prev).normalized()
        if a is None:
            ref = Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))
            a = t.cross(ref).normalized()
        else:
            a = a - t * a.dot(t)
            if a.length < 1e-6:
                a = t.cross(Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0)))
            a.normalize()
        b = t.cross(a).normalized()
        rings.append([bm.verts.new(p + (a * math.cos(s / sides * math.tau) + b * math.sin(s / sides * math.tau)) * radius) for s in range(sides)])
    for ring_a, ring_b in zip(rings, rings[1:]):
        for s in range(sides):
            bm.faces.new((ring_a[s], ring_a[(s + 1) % sides], ring_b[(s + 1) % sides], ring_b[s]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])


def inset(points, d, z_spring):
    """The arch's points moved inwards (towards the hall) by `d` along the curve's normal."""
    out = []
    for i, (u, z) in enumerate(points):
        u0, z0 = points[max(i - 1, 0)]
        u1, z1 = points[min(i + 1, len(points) - 1)]
        tu, tz = u1 - u0, z1 - z0
        length = math.hypot(tu, tz) or 1.0
        nu, nz = -tz / length, tu / length
        if nu * (0 - u) + nz * (z_spring - z) < 0:
            nu, nz = -nu, -nz
        out.append(Vector((u + nu * d, 0, z + nz * d)))
    return out


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


def stained_window(name, axis, at, u_centre, hw, z_sill, z_spring, z_apex, facing, depth=0.0):
    """One UV quad over the whole opening, which the runtime paints with stained glass; the
    corners beyond the pointed arch lie buried in the wall. A stone mullion and a tracery ring
    stand in front of it."""
    zc = (z_sill + z_apex) / 2
    centre = (u_centre, at + depth, zc) if axis == "y" else (at + depth, u_centre, zc)
    quad(f"glass_{name}", "glass", centre, 2 * hw, z_apex - z_sill, facing, group="decor")
    if hw > 0.8:
        if axis == "y":
            box("decor", "stone", u_centre - 0.07, u_centre + 0.07, at - 0.14, at + 0.14, z_sill, z_spring + hw * 0.6, name + "_mullion")
        else:
            box("decor", "stone", at - 0.14, at + 0.14, u_centre - 0.07, u_centre + 0.07, z_sill, z_spring + hw * 0.6, name + "_mullion")
        bm = bmesh.new()
        centre_v = Vector((u_centre, at, z_spring + hw * 0.95)) if axis == "y" else Vector((at, u_centre, z_spring + hw * 0.95))
        ring_pts = [centre_v + (Vector((math.cos(a) * hw * 0.55, 0, math.sin(a) * hw * 0.55)) if axis == "y" else Vector((0, math.cos(a) * hw * 0.55, math.sin(a) * hw * 0.55))) for a in (k / 20 * math.tau for k in range(21))]
        tube(bm, ring_pts, 0.07, sides=6)
        obj(name + "_tracery", bm, "stone", "decor")


# --- the main hall: walls, piers, windows and panels ---------------------------------------------
paintings = []  # (facing, x, y, scale)
bays = [(Y0 + k * BAY, Y0 + (k + 1) * BAY) for k in range(8)]
PAINTING_BAYS = range(1, 7)  # the entrance bay and the bay by the arch stay plain

for side in (-1, 1):
    x_in = side * HW  # the inner face
    x_out = side * (HW + T)
    facing = "e" if side < 0 else "w"  # the side the wall shows to the nave
    for k, (b0, b1) in enumerate(bays):
        yc = (b0 + b1) / 2
        # the lower wall is solid and carries the collision; the upper part, pierced, is decor
        box("solid", "stone", min(x_in, x_out), max(x_in, x_out), b0, b1, 0, SILL, f"wall_{side}_{k}_low")
        hole = [(yc + u * (1 if side < 0 else -1), z) for u, z in arch(WHW, SPRING, WAPEX, 12)] + [(yc + WHW * (1 if side < 0 else -1), SILL), (yc - WHW * (1 if side < 0 else -1), SILL)]
        pierced_wall(f"wall_{side}_{k}", "stone", "decor", "x", side * (HW + T / 2), b0, b1, SILL - 0.3, WALL, hole)
        box("decor", "stone_dark", min(x_in - side * 0.12, x_out), max(x_in - side * 0.12, x_out), yc - WHW - 0.25, yc + WHW + 0.25, SILL - 0.14, SILL + 0.06, f"sill_{side}_{k}")
        stained_window(f"window_{side}_{k}", "x", side * (HW + T / 2), yc, WHW, SILL, SPRING, WAPEX, facing, depth=side * 0.14)
        pw.empty(f"window_{side}_{k}_at", (x_in, yc, (SILL + WAPEX) / 2))
        if k in PAINTING_BAYS:
            # the navy panel with a stone moulding round it, the painting hung on it
            inner = x_in - side * 0.02
            box("decor", "stone_dark", min(inner, inner - side * 0.14), max(inner, inner - side * 0.14), yc - PANEL_W / 2 - 0.22, yc + PANEL_W / 2 + 0.22, PANEL_Z0 - 0.22, PANEL_Z1 + 0.22, f"moulding_{side}_{k}")
            box("decor", "panel_blue", min(inner - side * 0.14, inner - side * 0.17), max(inner - side * 0.14, inner - side * 0.17), yc - PANEL_W / 2, yc + PANEL_W / 2, PANEL_Z0, PANEL_Z1, f"panel_{side}_{k}")
            paintings.append((facing, inner - side * 0.17, yc, 1.0))
    # piers at every bay line: a block with three shafts in front, a base, a gilt capital
    for k in range(len(bays) + 1):
        yb = Y0 + k * BAY
        xp = x_in - side * PIER_D / 2
        box("solid", "stone", min(x_in, x_in - side * PIER_D), max(x_in, x_in - side * PIER_D), yb - PIER_W / 2, yb + PIER_W / 2, 0, WALL - 0.6, f"pier_{side}_{k}")
        for dy in (-0.3, 0.0, 0.3):
            cyl("decor", "stone", (x_in - side * (PIER_D + 0.1), yb + dy, 0.6), (x_in - side * (PIER_D + 0.1), yb + dy, WALL - 0.6), 0.13, seg=10, name=f"shaft_{side}_{k}_{dy}")
        # the bases of the end piers stop at the wall faces, so nothing pokes through into the aisles
        box("decor", "stone_dark", min(x_in, x_in - side * (PIER_D + 0.3)), max(x_in, x_in - side * (PIER_D + 0.3)), max(yb - 0.55, Y0), min(yb + 0.55, Y_ARCH - 0.45), 0, 0.6, f"pier_base_{side}_{k}")
        box("decor", "stone_dark", min(x_in, x_in - side * (PIER_D + 0.32)), max(x_in, x_in - side * (PIER_D + 0.32)), yb - 0.56, yb + 0.56, WALL - 0.6, WALL - 0.34, f"capital_{side}_{k}")
        box("decor", "gold", min(x_in, x_in - side * (PIER_D + 0.34)), max(x_in, x_in - side * (PIER_D + 0.34)), yb - 0.58, yb + 0.58, WALL - 0.62, WALL - 0.56, f"capital_fillet_{side}_{k}")
        box("decor", "stone_dark", min(x_in, x_in - side * (PIER_D + 0.38)), max(x_in, x_in - side * (PIER_D + 0.38)), yb - 0.62, yb + 0.62, WALL - 0.34, WALL, f"abacus_{side}_{k}")
    # a cornice along the top of the wall and a plinth course along the bottom
    box("decor", "stone_dark", min(x_in - side * 0.3, x_out), max(x_in - side * 0.3, x_out), Y0, Y_ARCH - 0.45, WALL - 0.3, WALL, f"cornice_{side}")
    box("decor", "stone_dark", min(x_in - side * 0.1, x_out), max(x_in - side * 0.1, x_out), Y0, Y_ARCH - 0.45, 0, 0.5, f"plinth_course_{side}")
    # a string course under the windows, between the panels and the sills
    box("decor", "stone_dark", min(x_in - side * 0.1, x_out), max(x_in - side * 0.1, x_out), Y0, Y_ARCH - 0.45, SILL - 0.3, SILL - 0.14, f"string_{side}")

# the entrance wall: a tall doorway with a dark wooden door, a great window above it
DOOR_HW, DOOR_Z = 1.6, 4.4
EW_HW, EW_SILL, EW_SPRING, EW_APEX = 2.3, 8.0, 12.6, 15.4
pierced_wall("wall_entrance_low", "stone", "decor", "y", Y0 - T / 2, -HW - T, HW + T, -0.2, EW_SILL - 0.3, opening(DOOR_HW, 0.0, DOOR_Z, DOOR_Z + 2.0, 10))
pierced_wall("wall_entrance_high", "stone", "decor", "y", Y0 - T / 2, -HW - T, HW + T, EW_SILL - 0.3, APEX + 0.5, opening(EW_HW, EW_SILL, EW_SPRING, EW_APEX, 12))
stained_window("window_entrance", "y", Y0 - T / 2, 0.0, EW_HW, EW_SILL, EW_SPRING, EW_APEX, "n", depth=-0.12)
pw.empty("window_entrance_at", (0, Y0, (EW_SILL + EW_APEX) / 2))
box("solid", "collider", -HW - T, -DOOR_HW, Y0 - T, Y0, 0, WALL, "entrance_l")
box("solid", "collider", DOOR_HW, HW + T, Y0 - T, Y0, 0, WALL, "entrance_r")
box("solid", "wood", -DOOR_HW, DOOR_HW, Y0 - T / 2 - 0.1, Y0 - T / 2 + 0.1, 0, DOOR_Z + 2.0, "door")
for k in range(5):
    box("decor", "iron", -DOOR_HW + 0.1, DOOR_HW - 0.1, Y0 - T / 2 + 0.1, Y0 - T / 2 + 0.14, 0.8 + k * 1.0, 0.86 + k * 1.0, f"door_band_{k}")
for sx in (-1, 1):
    box("decor", "stone_dark", sx * (DOOR_HW + 0.05), sx * (DOOR_HW + 0.45), Y0 - T / 2 - 0.2, Y0, 0, DOOR_Z + 0.3, f"door_jamb_{sx}")
for step, (dr, depth) in enumerate(((0.0, 0.0), (0.26, 0.16))):
    bm = bmesh.new()
    pts = [Vector((u, Y0 + depth, z)) for u, z in arch(DOOR_HW + dr + 0.12, DOOR_Z, DOOR_Z + 2.0 + dr * 1.1, 12)]
    tube(bm, [Vector((-DOOR_HW - dr - 0.12, Y0 + depth, 0.0))] + pts + [Vector((DOOR_HW + dr + 0.12, Y0 + depth, 0.0))], 0.1, sides=6)
    obj(f"door_archivolt_{step}", bm, "stone_dark", "decor")

# the arch between the two rooms, pointed, with the balcony above it
ARCH_HW, ARCH_SPRING, ARCH_APEX = 2.9, 6.0, 10.0
BALC_Z = 10.6  # the balcony floor over the arch
pierced_wall("wall_arch", "stone", "decor", "y", Y_ARCH, -HW - T, HW + T, -0.2, BALC_Z, opening(ARCH_HW, 0.0, ARCH_SPRING, ARCH_APEX, 14), thickness=0.9)
box("solid", "collider", -HW - T, -ARCH_HW, Y_ARCH - 0.45, Y_ARCH + 0.45, 0, WALL, "arch_l")
box("solid", "collider", ARCH_HW, HW + T, Y_ARCH - 0.45, Y_ARCH + 0.45, 0, WALL, "arch_r")
# archivolts: two stepped mouldings following the arch on the hall side
for step, (dr, depth) in enumerate(((0.0, 0.0), (0.32, 0.18))):
    bm = bmesh.new()
    pts = [Vector((u, Y_ARCH - 0.45 - depth, z)) for u, z in arch(ARCH_HW + dr + 0.12, ARCH_SPRING, ARCH_APEX + dr * 1.1, 14)]
    tube(bm, [Vector((-ARCH_HW - dr - 0.12, Y_ARCH - 0.45 - depth, 0.0))] + pts + [Vector((ARCH_HW + dr + 0.12, Y_ARCH - 0.45 - depth, 0.0))], 0.12, sides=6)
    obj(f"archivolt_{step}", bm, "stone_dark", "decor")
# the balcony: a slab over the arch and a stout stone balustrade, a sign on its face
box("decor", "stone", -HW, HW, Y_ARCH - 1.6, Y_ARCH + 0.45, BALC_Z - 0.4, BALC_Z, "balcony_slab")
box("decor", "stone_dark", -HW, HW, Y_ARCH - 1.78, Y_ARCH - 1.6, BALC_Z - 0.55, BALC_Z, "balcony_edge")
for i in range(22):
    xb = -HW + 0.4 + i * (2 * HW - 0.8) / 21
    cyl("decor", "marble", (xb, Y_ARCH - 1.45, BALC_Z + 0.1), (xb, Y_ARCH - 1.45, BALC_Z + 0.95), 0.09, seg=8, name=f"baluster_{i}")
    cyl("decor", "marble", (xb, Y_ARCH - 1.45, BALC_Z + 0.35), (xb, Y_ARCH - 1.45, BALC_Z + 0.65), 0.15, seg=8, name=f"baluster_belly_{i}")
box("decor", "marble", -HW, HW, Y_ARCH - 1.62, Y_ARCH - 1.28, BALC_Z + 0.95, BALC_Z + 1.15, "balcony_rail")
box("decor", "marble", -HW, HW, Y_ARCH - 1.62, Y_ARCH - 1.28, BALC_Z, BALC_Z + 0.1, "balcony_rail_low")
quad("sign_hall", "label", (0, Y_ARCH - 1.79, BALC_Z - 0.3), 2.4, 0.5, "s")
# the gallery wall above the balcony, pierced by a great window glazed on both faces
GW_HW, GW_SILL, GW_SPRING, GW_APEX = 2.6, BALC_Z + 1.0, BALC_Z + 4.6, BALC_Z + 8.0
pierced_wall("wall_gallery", "stone", "decor", "y", Y_ARCH, -HW - T, HW + T, BALC_Z, APEX + 0.5, opening(GW_HW, GW_SILL, GW_SPRING, GW_APEX, 14), thickness=0.6)
stained_window("window_gallery", "y", Y_ARCH, 0.0, GW_HW, GW_SILL, GW_SPRING, GW_APEX, "s", depth=-0.1)
stained_window("window_gallery_back", "y", Y_ARCH, 0.0, GW_HW, GW_SILL, GW_SPRING, GW_APEX, "n", depth=0.1)
pw.empty("window_gallery_at", (0, Y_ARCH, (GW_SILL + GW_APEX) / 2))
# the hall face of the arch wall keeps only its banners: the stone stays bare between them

# --- the second room: a narrower nave between arcades, side aisles behind them ------------------
bays2 = [(Y_ARCH + k * BAY, Y_ARCH + (k + 1) * BAY) for k in range(6)]
AR_HW, AR_SPRING, AR_APEX = 1.9, 5.0, 8.3  # the arcade's arches, near equilateral
CL_HW, CL_SILL, CL_SPRING, CL_APEX = 1.3, 9.4, 11.8, 14.0  # the clerestory windows, pointed
for side in (-1, 1):
    x_arc = side * HW2  # the arcade's plane
    x_outer = side * (HW2 + AISLE)
    for k, (b0, b1) in enumerate(bays2):
        yc = (b0 + b1) / 2
        sgn = 1 if side < 0 else -1
        hole = [(yc + u * sgn, z) for u, z in arch(AR_HW, AR_SPRING, AR_APEX, 12)] + [(yc + AR_HW * sgn, 0.0), (yc - AR_HW * sgn, 0.0)]
        pierced_wall(f"arcade_{side}_{k}", "stone", "decor", "x", x_arc, b0, b1, -0.2, CL_SILL - 0.3, hole)
        hole = [(yc + u * sgn, z) for u, z in arch(CL_HW, CL_SPRING, CL_APEX, 10)] + [(yc + CL_HW * sgn, CL_SILL), (yc - CL_HW * sgn, CL_SILL)]
        pierced_wall(f"clerestory_{side}_{k}", "stone", "decor", "x", x_arc, b0, b1, CL_SILL - 0.3, WALL2, hole)
        stained_window(f"window2_{side}_{k}", "x", x_arc, yc, CL_HW, CL_SILL, CL_SPRING, CL_APEX, "e" if side < 0 else "w", depth=side * 0.14)
        pw.empty(f"window2_{side}_{k}_at", (x_arc, yc, (CL_SILL + CL_APEX) / 2))
        # sconces on the arcade piers at the painting height of the main hall
    for k in range(1, len(bays2)):
        yb = Y_ARCH + k * BAY
        box("solid", "collider", x_arc - 0.35, x_arc + 0.35, yb - 0.42, yb + 0.42, 0, AISLE_Z, f"arcade_pier_{side}_{k}")
        # a clustered pier: a square core with four shafts, a base and a stone capital with a gilt fillet
        box("decor", "stone", x_arc - 0.3, x_arc + 0.3, yb - 0.3, yb + 0.3, 0.5, AR_SPRING - 0.4, f"column_{side}_{k}")
        for sx, sy in ((-0.3, 0), (0.3, 0), (0, -0.3), (0, 0.3)):
            cyl("decor", "stone", (x_arc + sx, yb + sy, 0.5), (x_arc + sx, yb + sy, AR_SPRING - 0.4), 0.11, seg=10, name=f"column_shaft_{side}_{k}_{sx}_{sy}")
        box("decor", "stone_dark", x_arc - 0.5, x_arc + 0.5, yb - 0.5, yb + 0.5, 0, 0.5, f"column_base_{side}_{k}")
        box("decor", "stone_dark", x_arc - 0.46, x_arc + 0.46, yb - 0.46, yb + 0.46, AR_SPRING - 0.4, AR_SPRING - 0.2, f"column_capital_{side}_{k}")
        box("decor", "gold", x_arc - 0.47, x_arc + 0.47, yb - 0.47, yb + 0.47, AR_SPRING - 0.42, AR_SPRING - 0.37, f"column_fillet_{side}_{k}")
        box("decor", "stone_dark", x_arc - 0.52, x_arc + 0.52, yb - 0.52, yb + 0.52, AR_SPRING - 0.2, AR_SPRING + 0.05, f"column_abacus_{side}_{k}")
        # a transverse arch across the aisle at every bay line, under the aisle ceiling
        # the vault's responds above the arcade
        box("decor", "stone", min(x_arc, x_arc - side * 0.3), max(x_arc, x_arc - side * 0.3), yb - 0.4, yb + 0.4, AR_APEX + 0.6, WALL2 - 0.5, f"respond_{side}_{k}")
        box("decor", "gold", min(x_arc, x_arc - side * 0.34), max(x_arc, x_arc - side * 0.34), yb - 0.46, yb + 0.46, WALL2 - 0.5, WALL2 - 0.3, f"respond_capital_{side}_{k}")
    box("decor", "stone_dark", min(x_arc - side * 0.25, x_arc + side * T / 2), max(x_arc - side * 0.25, x_arc + side * T / 2), Y_ARCH, Y1, WALL2 - 0.3, WALL2, f"cornice2_{side}")
    box("decor", "stone_dark", min(x_arc - side * 0.25, x_arc + side * T / 2), max(x_arc - side * 0.25, x_arc + side * T / 2), Y_ARCH, Y1, AR_APEX + 0.3, AR_APEX + 0.6, f"string2_{side}")
    # the aisle: an outer wall with a two-light window per bay, a cream ceiling, the end walls
    AW_HW, AW_SILL, AW_SPRING, AW_APEX = 1.1, 2.4, 5.4, 7.3
    for k, (b0, b1) in enumerate(bays2):
        yc = (b0 + b1) / 2
        sgn = 1 if side < 0 else -1
        box("solid", "stone", min(x_outer, x_outer + side * T), max(x_outer, x_outer + side * T), b0, b1, 0, AW_SILL, f"aisle_wall_{side}_{k}_low")
        hole = [(yc + u * sgn, z) for u, z in arch(AW_HW, AW_SPRING, AW_APEX, 10)] + [(yc + AW_HW * sgn, AW_SILL), (yc - AW_HW * sgn, AW_SILL)]
        pierced_wall(f"aisle_wall_{side}_{k}", "stone", "decor", "x", x_outer + side * T / 2, b0, b1, AW_SILL - 0.3, AISLE_Z, hole)
        stained_window(f"window3_{side}_{k}", "x", x_outer + side * T / 2, yc, AW_HW, AW_SILL, AW_SPRING, AW_APEX, "e" if side < 0 else "w", depth=side * 0.14)
        pw.empty(f"window3_{side}_{k}_at", (x_outer, yc, (AW_SILL + AW_APEX) / 2))
    box("solid", "stone", min(x_arc, x_outer + side * T), max(x_arc, x_outer + side * T), Y1 - T / 2, Y1 + T / 2, 0, AISLE_Z + 0.4, f"aisle_end_{side}")
    box("solid", "stone", min(side * (HW + T), x_outer + side * T), max(side * (HW + T), x_outer + side * T), Y_ARCH - 0.45, Y_ARCH + 0.45, 0, AISLE_Z + 0.4, f"aisle_start_{side}")
    box("decor", "stone", min(x_arc, side * (HW + T)), max(x_arc, side * (HW + T)), Y_ARCH + 0.05, Y_ARCH + 0.45, AISLE_Z + 0.4, WALL2, f"aisle_start_high_{side}")

# the far wall of the second room: the featured painting under a tall bright window
FW_HW, FW_SILL, FW_SPRING, FW_APEX = 2.2, 6.4, 11.8, 14.8
pierced_wall("wall_far", "stone", "decor", "y", Y1, -HW2 - T, HW2 + T, -0.2, APEX2 + 0.5, opening(FW_HW, FW_SILL, FW_SPRING, FW_APEX, 12))
box("solid", "collider", -HW2 - T, HW2 + T, Y1 - T / 2, Y1 + T / 2, 0, WALL2, "far_low")
stained_window("window_far", "y", Y1, 0.0, FW_HW, FW_SILL, FW_SPRING, FW_APEX, "s", depth=0.14)
pw.empty("window_far_at", (0, Y1, (FW_SILL + FW_APEX) / 2))
box("decor", "stone_dark", -2.7, 2.7, Y1 - T / 2 - 0.14, Y1 - T / 2, PANEL_Z0 - 0.22, PANEL_Z1 + 0.6, "far_moulding")
box("decor", "panel_blue", -2.48, 2.48, Y1 - T / 2 - 0.17, Y1 - T / 2 - 0.14, PANEL_Z0, PANEL_Z1 + 0.38, "far_panel")
paintings.append(("s", 0.0, Y1 - T / 2 - 0.17, 1.4))

# --- the vaults ------------------------------------------------------------------------------------
def vault(name, hw, z_spring, z_apex, ya, yb, bays_, ridge_r, x0=0.0, steps=16, inset_wall=T):
    section = [(u + x0, z) for u, z in arch(hw + inset_wall, z_spring, z_apex, steps)]
    bm = bmesh.new()
    rings = [[bm.verts.new(Vector((u, yy, z))) for u, z in section] for yy in (ya, yb)]
    loft(bm, rings, closed=False)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    for f in bm.faces:
        if f.normal.z > 0:
            f.normal_flip()
    obj(name, bm, "vault", "decor", smooth=True)
    rib_section = [Vector((p.x + x0, 0, p.z)) for p in inset([(u - x0, z) for u, z in section], 0.1, z_spring)]
    diag_section = [Vector((p.x + x0, 0, p.z)) for p in inset([(u - x0, z) for u, z in section], 0.04, z_spring)]
    for (b0, b1) in bays_:
        bm = bmesh.new()
        tube(bm, [Vector((p.x, b0, p.z)) for p in rib_section], 0.2, sides=6)
        obj(f"{name}_rib_{b0}", bm, "rib", "decor")
        for (y_from, y_to) in ((b0, b1), (b1, b0)):
            bm = bmesh.new()
            pts = [Vector((p.x, y_from + (y_to - y_from) * i / (len(diag_section) - 1), p.z)) for i, p in enumerate(diag_section)]
            tube(bm, pts, 0.14, sides=5)
            obj(f"{name}_diag_{b0}_{y_from}", bm, "rib", "decor")
        bm = bmesh.new()
        pw.add_ico(bm, (x0, (b0 + b1) / 2, z_apex - 0.2), 0.3 if hw > 3 else 0.16, 1)
        obj(f"{name}_boss_{b0}", bm, "gold", "decor", smooth=True)
    bm = bmesh.new()
    tube(bm, [Vector((p.x, bays_[-1][1], p.z)) for p in rib_section], 0.2, sides=6)
    obj(f"{name}_rib_end", bm, "rib", "decor")
    bm = bmesh.new()
    tube(bm, [Vector((x0, yy, z_apex - 0.08)) for yy in (ya, yb)], ridge_r, sides=6)
    obj(f"{name}_ridge", bm, "rib", "decor")


vault("vault_main", HW, WALL, APEX, Y0 - T, Y_ARCH - 0.45, bays, 0.18)
vault("vault_second", HW2, WALL2, APEX2, Y_ARCH, Y1 + T, bays2, 0.15)
# the aisles get a pointed barrel vault each, narrow and low, with the transverse ribs at the bay lines
for side in (-1, 1):
    vault(f"vault_aisle_{side}", AISLE / 2, AISLE_Z - 1.6, AISLE_Z + 0.9, Y_ARCH, Y1 + T, bays2, 0.1, x0=side * (HW2 + T / 2 + AISLE / 2), steps=10, inset_wall=T / 2)

# --- the floor: cream marble with the inlay drawn at runtime ------------------------------------
box("decor", "floor", -HW - T, HW + T, Y0 - T, Y_ARCH, -0.1, 0, "floor")
box("decor", "floor", -HW2 - AISLE - T, HW2 + AISLE + T, Y_ARCH, Y1 + T, -0.1, 0, "floor_second")

# --- paintings -------------------------------------------------------------------------------------
CW, CH, CZ = 2.6, 1.7, 3.5
for i, (facing, px, py, scale) in enumerate(paintings):
    w, h = CW * scale, CH * scale
    z = CZ
    if facing in ("e", "w"):
        d = 1 if facing == "e" else -1
        # a deep gold frame in two steps: an outer bar and an inner lip, the canvas a hair in front
        for (yy0, yy1, zz0, zz1) in ((py - w / 2 - 0.2, py + w / 2 + 0.2, z - h / 2 - 0.2, z - h / 2), (py - w / 2 - 0.2, py + w / 2 + 0.2, z + h / 2, z + h / 2 + 0.2), (py - w / 2 - 0.2, py - w / 2, z - h / 2, z + h / 2), (py + w / 2, py + w / 2 + 0.2, z - h / 2, z + h / 2)):
            box("decor", "gold", min(px, px + 0.1 * d), max(px, px + 0.1 * d), yy0, yy1, zz0, zz1)
        for (yy0, yy1, zz0, zz1) in ((py - w / 2 - 0.08, py + w / 2 + 0.08, z - h / 2 - 0.08, z - h / 2), (py - w / 2 - 0.08, py + w / 2 + 0.08, z + h / 2, z + h / 2 + 0.08), (py - w / 2 - 0.08, py - w / 2, z - h / 2, z + h / 2), (py + w / 2, py + w / 2 + 0.08, z - h / 2, z + h / 2)):
            box("decor", "brass", min(px + 0.1 * d, px + 0.14 * d), max(px + 0.1 * d, px + 0.14 * d), yy0, yy1, zz0, zz1)
        quad(f"canvas_{i}", "canvas", (px + 0.02 * d, py, z), w, h, facing)
        quad(f"label_{i}", "label", (px + 0.01 * d, py, z - h / 2 - 0.5), 1.0, 0.44, facing)
        pw.empty(f"spot_canvas_{i}", (px + 1.9 * d, py, 0))
        pw.empty(f"light_{i}", (px + 0.3 * d, py, z + h / 2 + 0.6))
        cyl("decor", "brass", (px, py, z + h / 2 + 0.62), (px + 0.36 * d, py, z + h / 2 + 0.5), 0.02, seg=6, name=f"picture_light_arm_{i}")
        box("decor", "brass", min(px + 0.3 * d, px + 0.42 * d), max(px + 0.3 * d, px + 0.42 * d), py - 0.5, py + 0.5, z + h / 2 + 0.42, z + h / 2 + 0.52, f"picture_light_{i}")
    else:
        for (xx0, xx1, zz0, zz1) in ((px - w / 2 - 0.2, px + w / 2 + 0.2, z - h / 2 - 0.2, z - h / 2), (px - w / 2 - 0.2, px + w / 2 + 0.2, z + h / 2, z + h / 2 + 0.2), (px - w / 2 - 0.2, px - w / 2, z - h / 2, z + h / 2), (px + w / 2, px + w / 2 + 0.2, z - h / 2, z + h / 2)):
            box("decor", "gold", xx0, xx1, py - 0.1, py, zz0, zz1)
        quad(f"canvas_{i}", "canvas", (px, py - 0.02, z), w, h, facing)
        quad(f"label_{i}", "label", (px, py - 0.01, z - h / 2 - 0.5), 1.3, 0.57, facing)
        pw.empty(f"spot_canvas_{i}", (px, py - 4.5, 0))
        pw.empty(f"light_{i}", (px, py - 0.4, z + h / 2 + 0.6))

# --- banners, sconces, chandeliers ---------------------------------------------------------------
# the banners and sconces generated with Qwen-Image and TRELLIS.2 (tools/assets/trellis) hang in
# place of the drawn ones when their files exist; the generated banner faces -y and hangs from its
# rod (its origin), the sconce faces -y with its origin on its back plate
BANNER_GLB = os.path.join(ASSETS, "trellis", "banner.glb")
SCONCE_GLB = os.path.join(ASSETS, "trellis", "sconce.glb")


def banner(side, yc, name, top=WAPEX - 0.6, bottom=SILL + 0.4, w=1.1, x=None, face=None):
    x = side * (HW - PIER_D - 0.26 - 0.1) if x is None else x
    if os.path.exists(BANNER_GLB):
        # the generated banner is prepared 1.4 m wide and 2.4 m tall; in the nave it hangs 2.2 m wide
        # from 12.6 m at right angles to the wall with its emblem to the entrance, as in the
        # reference, on a brass pole from the pier face with a strut under it
        sc = w * 1.45
        face = side * (HW - PIER_D) if face is None else face
        xc = face - side * (0.12 + 0.7 * sc)
        zr = top - 0.4
        place_asset("trellis/banner", (xc, yc, zr), scale=sc, yaw=0.0, name=name)
        cyl("decor", "gold", (face, yc, zr), (xc, yc, zr), 0.025, seg=6, name=name + "_pole")
        cyl("decor", "gold", (face, yc + 0.06, zr - 0.8), (face - side * 0.55, yc + 0.06, zr - 0.03), 0.018, seg=6, name=name + "_strut")
        return
    bm = bmesh.new()
    pts = [(x, yc - w / 2, top), (x, yc + w / 2, top), (x, yc + w / 2, bottom + 0.7), (x, yc, bottom), (x, yc - w / 2, bottom + 0.7)]
    face = bm.faces.new([bm.verts.new(Vector(p)) for p in pts])
    face.normal_update()
    if (face.normal.x > 0) != (side < 0):
        face.normal_flip()
    obj(name, bm, "crimson", "decor")
    cyl("decor", "gold", (x, yc - w / 2 - 0.15, top), (x, yc + w / 2 + 0.15, top), 0.04, seg=8, name=name + "_rod")
    # the emblem: a cross with trefoil ends, in gold
    xe = x - side * 0.02
    zc = (top + bottom) / 2 + 0.45
    s = min((top - bottom) / 6.0, w / 2.0)
    arms = [
        (yc - 0.07 * s, yc + 0.07 * s, zc - 0.95 * s, zc + 0.95 * s),
        (yc - 0.7 * s, yc + 0.7 * s, zc + 0.12 * s, zc + 0.26 * s),
    ]
    for (ay, az) in ((0, 0.95 * s), (0, -0.95 * s), (-0.7 * s, 0.19 * s), (0.7 * s, 0.19 * s)):
        for (dy, dz) in ((-0.16 * s, 0), (0.16 * s, 0), (0, 0.16 * s if az >= 0 else -0.16 * s)):
            arms.append((yc + ay + dy - 0.09 * s, yc + ay + dy + 0.09 * s, zc + az + dz - 0.09 * s, zc + az + dz + 0.09 * s))
    for (y0, y1, z0, z1) in arms:
        box("decor", "gold", min(xe, xe - side * 0.02), max(xe, xe - side * 0.02), y0, y1, z0, z1)
    for k in range(5):
        box("decor", "gold", min(xe, xe - side * 0.01), max(xe, xe - side * 0.01), yc - w / 2 + 0.05 + k * (w - 0.1) / 5, yc - w / 2 + 0.15 + k * (w - 0.1) / 5, bottom + 0.62 - k * 0.14, bottom + 0.8 - k * 0.14)


def sconce(side, yc, name, x=None, z=3.3, plate=0.11):
    x = side * (HW - PIER_D - 0.26 - 0.08) if x is None else x
    if os.path.exists(SCONCE_GLB):
        # the generated sconce, 1.25 m tall, its back plate on the crest of the pier's shafts (`plate`
        # behind `x`) and its candles to the nave, with three flames where its candles end (measured
        # on the mesh); the empty puts the scene's halo on the shafts just behind the plate
        sc = 1.25
        xp = x + side * plate
        place_asset("trellis/sconce", (xp, yc, z + 0.05), scale=sc, yaw=-side * math.pi / 2, name=name)
        for k, (dy, dz, dd) in enumerate(((-0.21 * sc, 0.23 * sc, 0.075 * sc), (0.0, 0.18 * sc, 0.12 * sc), (0.21 * sc, 0.23 * sc, 0.075 * sc))):
            xf = xp - side * dd
            cyl("decor", "flame", (xf, yc + dy, z + 0.05 + dz), (xf, yc + dy, z + 0.05 + dz + 0.12), 0.026, seg=6, name=f"{name}_flame_{k}", r2=0.0)
        pw.empty(f"candle_{name}", (xp - side * 0.12, yc, z + 0.55))
        return
    cyl("decor", "gold", (x + side * 0.25, yc, z - 0.6), (x, yc, z), 0.03, seg=6, name=name + "_arm")
    for k, dy in enumerate((-0.22, 0.0, 0.22)):
        cyl("decor", "gold", (x, yc + dy, z - 0.1), (x, yc + dy, z + 0.05), 0.06, seg=8, name=f"{name}_cup_{k}")
        cyl("decor", "candle", (x, yc + dy, z + 0.05), (x, yc + dy, z + 0.3), 0.022, seg=6, name=f"{name}_candle_{k}")
        cyl("decor", "flame", (x, yc + dy, z + 0.3), (x, yc + dy, z + 0.42), 0.028, seg=6, name=f"{name}_flame_{k}", r2=0.0)
    cyl("decor", "gold", (x, yc - 0.3, z - 0.1), (x, yc + 0.3, z - 0.1), 0.025, seg=6, name=name + "_bar")
    pw.empty(f"candle_{name}", (x, yc, z + 0.45))


for side in (-1, 1):
    # banners beside the windows on every other pier, sconces on all the piers between paintings
    for k in range(2, 7, 2):
        banner(side, Y0 + k * BAY, f"banner_{side}_{k}")
    for k in range(1, 8):
        sconce(side, Y0 + k * BAY, f"sconce_{side}_{k}")
    for k in range(1, 6):
        sconce(side, Y_ARCH + k * BAY, f"sconce2_{side}_{k}", x=side * (HW2 - 0.56), z=3.3, plate=0.15)
    for k in (1, 3, 5):
        banner(side, Y_ARCH + k * BAY, f"banner2_{side}_{k}", top=CL_APEX - 0.4, bottom=AR_APEX + 0.9, w=1.0, x=side * (HW2 - 0.5), face=side * HW2)
# a narrow banner hanging from the balcony rail, to the right of the arch, facing the hall
def banner_south(xc, y, top, bottom, w, name):
    if os.path.exists(BANNER_GLB):
        place_asset("trellis/banner", (xc, y, top - 0.2), scale=w * 1.55, yaw=0.0, name=name)
        return
    bm = bmesh.new()
    pts = [(xc - w / 2, y, top), (xc + w / 2, y, top), (xc + w / 2, y, bottom + 0.6), (xc, y, bottom), (xc - w / 2, y, bottom + 0.6)]
    face = bm.faces.new([bm.verts.new(Vector(p)) for p in pts])
    face.normal_update()
    if face.normal.y > 0:
        face.normal_flip()
    obj(name, bm, "crimson", "decor")
    zc = (top + bottom) / 2 + 0.3
    s = min((top - bottom) / 6.0, w / 2.0)
    arms = [(xc - 0.07 * s, xc + 0.07 * s, zc - 0.95 * s, zc + 0.95 * s), (xc - 0.7 * s, xc + 0.7 * s, zc + 0.12 * s, zc + 0.26 * s)]
    for (ax, az) in ((0, 0.95 * s), (0, -0.95 * s), (-0.7 * s, 0.19 * s), (0.7 * s, 0.19 * s)):
        for (dx, dz) in ((-0.16 * s, 0), (0.16 * s, 0), (0, 0.16 * s if az >= 0 else -0.16 * s)):
            arms.append((xc + ax + dx - 0.09 * s, xc + ax + dx + 0.09 * s, zc + az + dz - 0.09 * s, zc + az + dz + 0.09 * s))
    for (x0, x1, z0, z1) in arms:
        box("decor", "gold", x0, x1, y - 0.04, y - 0.02, z0, z1)


banner_south(5.45, Y_ARCH - 1.8, BALC_Z + 1.15, BALC_Z - 3.4, 0.9, "banner_balcony")
banner_south(-5.45, Y_ARCH - 1.8, BALC_Z + 1.15, BALC_Z - 3.4, 0.9, "banner_balcony_l")


def chandelier(x, yv, z, name, radius=1.3, tiers=2, ring_mat="gold", top=None):
    cyl("decor", "iron", (x, yv, (APEX if top is None else top) - 0.3), (x, yv, z + 0.9 * (tiers - 1) + 0.6), 0.025, seg=6, name=name + "_chain")
    for tier, (r, dz, count) in enumerate(((radius, 0.0, 12), (radius * 0.55, 0.9, 6))[:tiers]):
        bm = bmesh.new()
        ring_pts = [Vector((x + math.cos(a) * r, yv + math.sin(a) * r, z + dz)) for a in (k / 24 * math.tau for k in range(25))]
        tube(bm, ring_pts, 0.05 + 0.04 * (tiers == 1), sides=6)
        if tiers == 1:
            # a single-ring chandelier gets a flat band and a hub, like the iron one in the reference
            bm2 = bmesh.new()
            tube(bm2, [Vector((x + math.cos(a) * r, yv + math.sin(a) * r, z + dz - 0.18)) for a in (k / 24 * math.tau for k in range(25))], 0.05, sides=6)
            obj(f"{name}_ring_{tier}_low", bm2, ring_mat, "decor")
            for a in (k / 12 * math.tau for k in range(12)):
                cyl("decor", ring_mat, (x + math.cos(a) * r, yv + math.sin(a) * r, z + dz - 0.18), (x + math.cos(a) * r, yv + math.sin(a) * r, z + dz), 0.02, seg=4, name=f"{name}_bar_{tier}_{a:.2f}")
            cyl("decor", ring_mat, (x, yv, z + dz + 1.0), (x, yv, z + dz + 1.5), 0.12, seg=8, name=f"{name}_hub")
        obj(f"{name}_ring_{tier}", bm, ring_mat, "decor")
        for k in range(count):
            a = k / count * math.tau
            cx, cy = x + math.cos(a) * r, yv + math.sin(a) * r
            cyl("decor", "gold", (cx, cy, z + dz), (cx, cy, z + dz + 0.12), 0.07, seg=8, name=f"{name}_cup_{tier}_{k}")
            cyl("decor", "candle", (cx, cy, z + dz + 0.12), (cx, cy, z + dz + 0.42), 0.026, seg=6, name=f"{name}_candle_{tier}_{k}")
            cyl("decor", "flame", (cx, cy, z + dz + 0.42), (cx, cy, z + dz + 0.58), 0.032, seg=6, name=f"{name}_flame_{tier}_{k}", r2=0.0)
        for k in range(4):
            a = k / 4 * math.tau + 0.4
            cyl("decor", "iron", (x + math.cos(a) * r, yv + math.sin(a) * r, z + dz), (x, yv, z + dz + 1.3), 0.015, seg=4, name=f"{name}_spoke_{tier}_{k}")
    # the crown: a small upper ring with gilt points, where the chains meet
    bm = bmesh.new()
    tube(bm, [Vector((x + math.cos(a) * radius * 0.35, yv + math.sin(a) * radius * 0.35, z + 1.3)) for a in (k / 16 * math.tau for k in range(17))], 0.035, sides=5)
    obj(f"{name}_crown", bm, ring_mat, "decor")
    for k in range(6):
        a = k / 6 * math.tau
        cyl("decor", "gold", (x + math.cos(a) * radius * 0.35, yv + math.sin(a) * radius * 0.35, z + 1.3), (x + math.cos(a) * radius * 0.42, yv + math.sin(a) * radius * 0.42, z + 1.55), 0.025, seg=5, name=f"{name}_point_{k}", r2=0.0)
    pw.empty(f"candle_{name}", (x, yv, z + 0.6))


chandelier(0.0, -5.0, 9.4, "chandelier_0", radius=1.8, tiers=1, ring_mat="iron")
chandelier(0.0, 9.0, 9.4, "chandelier_1", radius=1.8, tiers=1, ring_mat="iron")
for k in range(3):
    chandelier(0.0, Y_ARCH + (k + 1) * BAY + 2.25, 9.0, f"chandelier_second_{k}", radius=1.2, tiers=1, ring_mat="iron", top=APEX2)

# --- the centre of the hall: pedestal, ropes and the statue --------------------------------------
PX, PY = 0.0, 7.0
# the pedestal sits to the statue's measure: a rectangle with chamfered corners in four tiers,
# longer across the nave because the hand truck trails to the east; the ropes follow it as a
# rectangle, so their colliders match them exactly
def plinth(name, hx, hy, z0, z1, chamfer, mat="stone_dark"):
    bm = bmesh.new()
    pts = [(-hx + chamfer, -hy), (hx - chamfer, -hy), (hx, -hy + chamfer), (hx, hy - chamfer), (hx - chamfer, hy), (-hx + chamfer, hy), (-hx, hy - chamfer), (-hx, -hy + chamfer)]
    vs = [bm.verts.new((PX + x, PY + y, z0)) for x, y in pts]
    face = bm.faces.new(vs)
    res = bmesh.ops.extrude_face_region(bm, geom=[face])
    top = [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=top, vec=Vector((0, 0, z1 - z0)))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return obj(name, bm, mat, "decor")


TOP_HX, TOP_HY = 1.4, 1.0
for k, (hx, hy, z0, z1, ch) in enumerate(((2.15, 1.75, 0.0, 0.22, 0.45), (1.9, 1.5, 0.22, 0.5, 0.4), (1.65, 1.25, 0.5, 0.78, 0.35), (TOP_HX, TOP_HY, 0.78, 1.25, 0.3))):
    plinth(f"pedestal_{k}", hx, hy, z0, z1, ch)
# a soft shadow of contact under the figure, so it sits on the stone instead of hovering
quad("shadow_statue", "shadow_patch", (PX + 0.05, PY, 1.254), 2.6, 1.8, "up", group="decor")
box("solid", "collider", PX - 2.15, PX + 2.15, PY - 1.75, PY + 1.75, 0, 1.25, "pedestal_collider")
box("solid", "collider", PX - 1.25, PX + 1.25, PY - 0.85, PY + 0.85, 0, 4.4, "statue_collider")
box("decor", "brass", PX - 0.66, PX + 0.66, PY - TOP_HY - 0.03, PY - TOP_HY, 0.79, 1.25, "plaque_back")
quad("about_panel", "label", (PX, PY - TOP_HY - 0.04, 1.02), 1.28, 0.42, "s")
pw.empty("spot_about", (PX, PY - 3.4, 0))
RX, RY = 2.45, 2.1
ring = [(-RX, -RY), (0, -RY), (RX, -RY), (RX, 0), (RX, RY), (0, RY), (-RX, RY), (-RX, 0)]
for k, (rx, ry) in enumerate(ring):
    sx, sy = PX + rx, PY + ry
    cyl("decor", "brass", (sx, sy, 0.0), (sx, sy, 0.06), 0.18, seg=12, name=f"stanchion_base_{k}")
    cyl("decor", "brass", (sx, sy, 0.06), (sx, sy, 0.95), 0.03, seg=8, name=f"stanchion_{k}")
    bm = bmesh.new()
    pw.add_ico(bm, (sx, sy, 1.0), 0.06, 1)
    obj(f"stanchion_knob_{k}", bm, "brass", "decor", smooth=True)
    ex, ey = PX + ring[(k + 1) % len(ring)][0], PY + ring[(k + 1) % len(ring)][1]
    bm = bmesh.new()
    pts = [Vector((sx + (ex - sx) * t, sy + (ey - sy) * t, 0.9 - 0.22 * math.sin(math.pi * t))) for t in (i / 6 for i in range(7))]
    tube(bm, pts, 0.03, sides=6)
    obj(f"rope_{k}", bm, "velvet", "decor")
for name_, (x0, x1, y0, y1) in {"ropes_s": (-RX, RX, -RY - 0.05, -RY + 0.05), "ropes_n": (-RX, RX, RY - 0.05, RY + 0.05), "ropes_w": (-RX - 0.05, -RX + 0.05, -RY, RY), "ropes_e": (RX - 0.05, RX + 0.05, -RY, RY)}.items():
    box("solid", "collider", PX + x0, PX + x1, PY + y0, PY + y1, 0, 0.95, name_)

# the statue: a blocky figure in stone hauling an old computer on a cable, leaning into the pull
base = 1.25


def statue_box(name, center, size, yaw=0.0, pitch=0.0):
    bm = bmesh.new()
    vs = pw.add_box(bm, (0, 0, 0), size, 0.0)
    if pitch:
        bmesh.ops.rotate(bm, verts=vs, cent=(0, 0, 0), matrix=Matrix.Rotation(pitch, 3, "X"))
    if yaw:
        bmesh.ops.rotate(bm, verts=vs, cent=(0, 0, 0), matrix=Matrix.Rotation(yaw, 3, "Z"))
    bmesh.ops.translate(bm, verts=vs, vec=Vector(center))
    obj(name, bm, "statue", "decor")


STATUE_GLB = os.path.join(ASSETS, "trellis", "statue.glb")
if os.path.exists(STATUE_GLB):
    # the statue generated from the reference crop with TRELLIS.2 (see tools/assets/trellis/README.md)
    STATUE_SCALE, STATUE_YAW = 1.0, 0.0
    place_asset("trellis/statue", (PX, PY, base), scale=STATUE_SCALE, yaw=STATUE_YAW, name="statue_generated")
else:
    # the figure faces the entrance and leans hard into the pull; the hand truck with the computer
    # tilts behind it to the north, on two wheels
    fx, fy = PX - 0.25, PY - 0.3
    lean = math.radians(15)
    statue_box("statue_leg_back", (fx + 0.22, fy + 0.62, base + 0.5), (0.3, 0.3, 1.0), pitch=math.radians(26))
    statue_box("statue_foot_back", (fx + 0.22, fy + 0.9, base + 0.08), (0.32, 0.52, 0.16))
    statue_box("statue_leg_front", (fx - 0.22, fy - 0.34, base + 0.5), (0.3, 0.3, 1.0), pitch=math.radians(-12))
    statue_box("statue_foot_front", (fx - 0.22, fy - 0.56, base + 0.08), (0.32, 0.52, 0.16))
    statue_box("statue_hips", (fx, fy + 0.05, base + 1.04), (0.72, 0.42, 0.3), pitch=lean)
    statue_box("statue_waist", (fx, fy - 0.02, base + 1.3), (0.5, 0.34, 0.26), pitch=lean)
    statue_box("statue_torso", (fx + 0.04, fy - 0.22, base + 1.72), (0.86, 0.5, 0.74), pitch=lean)
    statue_box("statue_chest_plate", (fx + 0.04, fy - 0.5, base + 1.78), (0.56, 0.08, 0.44), pitch=lean)
    for sx in (-0.56, 0.64):
        statue_box(f"statue_shoulder_{sx}", (fx + sx, fy - 0.3, base + 2.06), (0.34, 0.36, 0.3), pitch=lean)
    statue_box("statue_neck", (fx + 0.06, fy - 0.42, base + 2.28), (0.22, 0.22, 0.14), pitch=lean)
    # the head: a monitor with a bezel, a recessed dark screen, two eyes and a mouth
    statue_box("statue_head", (fx + 0.1, fy - 0.46, base + 2.62), (0.62, 0.56, 0.52), pitch=lean)
    statue_box("statue_head_bezel", (fx + 0.1, fy - 0.76, base + 2.62), (0.5, 0.06, 0.4), pitch=lean)
    box("decor", "screen", fx - 0.1, fx + 0.3, fy - 0.81, fy - 0.78, base + 2.47, base + 2.77, "statue_face")
    for ex in (fx + 0.0, fx + 0.2):
        box("decor", "candle", ex - 0.04, ex + 0.04, fy - 0.82, fy - 0.81, base + 2.65, base + 2.71, f"statue_eye_{ex:.2f}")
    box("decor", "candle", fx + 0.03, fx + 0.17, fy - 0.82, fy - 0.81, base + 2.53, base + 2.55, "statue_mouth")
    # arms: the near one down and back to the truck's handle, the far one swinging forward
    statue_box("statue_arm_r", (fx + 0.66, fy + 0.02, base + 1.66), (0.22, 0.22, 0.8), pitch=math.radians(48))
    statue_box("statue_forearm_r", (fx + 0.66, fy + 0.5, base + 1.2), (0.2, 0.2, 0.7), pitch=math.radians(66))
    statue_box("statue_hand_r", (fx + 0.66, fy + 0.78, base + 0.92), (0.22, 0.26, 0.24))
    statue_box("statue_arm_l", (fx - 0.58, fy - 0.55, base + 1.7), (0.22, 0.22, 0.8), pitch=math.radians(-30))
    statue_box("statue_forearm_l", (fx - 0.58, fy - 0.9, base + 1.3), (0.2, 0.2, 0.7), pitch=math.radians(-55))
    statue_box("statue_hand_l", (fx - 0.58, fy - 1.1, base + 1.05), (0.22, 0.26, 0.24))
    # the hand truck: two wheels, an axle, a tilted frame with a nose plate, the computer strapped on
    tx, ty = PX + 0.9, PY + 0.95
    tilt = math.radians(32)
    for wx in (-1, 1):
        cyl("decor", "statue", (tx + wx * 0.34, ty, base + 0.2), (tx + wx * 0.42, ty, base + 0.2), 0.2, seg=12, name=f"statue_wheel_{wx}")
    cyl("decor", "iron", (tx - 0.42, ty, base + 0.2), (tx + 0.42, ty, base + 0.2), 0.03, seg=6, name="statue_axle")
    for rx in (-0.26, 0.26):
        statue_box(f"statue_truck_rail_{rx}", (tx + rx, ty - 0.1 - 0.95 * math.sin(tilt) * 0.5, base + 0.14 + 0.95 * math.cos(tilt)), (0.06, 0.06, 1.9), pitch=-tilt)
    statue_box("statue_truck_nose", (tx, ty - 0.42, base + 0.14), (0.62, 0.5, 0.05), pitch=-tilt)
    statue_box("statue_truck_handle", (tx, ty - 0.1 - 1.9 * math.sin(tilt) * 0.5 - 0.05, base + 0.2 + 1.9 * math.cos(tilt) * 0.5 + 0.1), (0.62, 0.06, 0.06), pitch=-tilt)
    statue_box("statue_computer", (tx, ty - 0.46 + 0.1, base + 0.5), (0.7, 0.56, 0.62), pitch=-tilt)
    box("decor", "screen", tx - 0.24, tx + 0.24, ty - 0.86, ty - 0.84, base + 0.42, base + 0.8, "statue_computer_screen")
    statue_box("statue_keyboard", (tx, ty - 0.1, base + 0.92), (0.56, 0.28, 0.05), pitch=-tilt)
    bm = bmesh.new()
    pull = [Vector((fx + 0.66 + (tx - fx - 0.66) * t, fy + 0.78 + (ty - 1.0 - fy - 0.78) * t, base + 0.92 + (base + 1.1 - base - 0.92) * t - 0.1 * math.sin(math.pi * t))) for t in (i / 8 for i in range(9))]
    tube(bm, pull, 0.03, sides=5)
    obj("statue_cable", bm, "iron", "decor")

# --- glass cases with open books: the experience ---------------------------------------------------
# the cabinets of the experience stand in the second room, between the arcade piers on both sides,
# so the nave keeps its paintings and its statue as the only exhibits
# two cabinets a side, facing each other across the room, and the current post in a table case in
# the middle; the order round the room runs from the oldest post by the arch on the west to the
# newest in the centre: the reader stands on the side the plaque faces
X_CASE = HW2 - 0.95
layout = [
    (0, -X_CASE, Y_ARCH + 2.5 * BAY, "e"),
    (1, -X_CASE, Y_ARCH + 4.5 * BAY, "e"),
    (4, 0.0, Y_ARCH + 3.5 * BAY, "s"),
    (2, X_CASE, Y_ARCH + 4.5 * BAY, "w"),
    (3, X_CASE, Y_ARCH + 2.5 * BAY, "w"),
]
for i, cx, cy, reader in layout:
    rdx, rdy = {"e": (1, 0), "w": (-1, 0), "s": (0, -1)}[reader]
    top = 2.1 if i == 1 else 1.65

    def rect(u0, u1, v0, v1):
        """u runs along the long side, v across it towards the reader; world bounds back."""
        if rdx:
            xs, ys = (cx + v0 * rdx, cx + v1 * rdx), (cy + u0, cy + u1)
        else:
            xs, ys = (cx + u0, cx + u1), (cy + v0 * rdy, cy + v1 * rdy)
        return min(xs), max(xs), min(ys), max(ys)

    def point(u, v, z):
        return (cx + v * rdx, cy + u, z) if rdx else (cx + u, cy + v * rdy, z)

    # the cabinet: dark wood on a stone base, with recessed panels and a brass lip
    box("solid", "collider", *rect(-0.9, 0.9, -0.6, 0.6), 0, top, f"case_collider_{i}")
    box("decor", "stone_dark", *rect(-0.9, 0.9, -0.6, 0.6), 0, 0.12, f"case_base_{i}")
    box("decor", "wood", *rect(-0.85, 0.85, -0.55, 0.55), 0.12, 0.92, f"case_body_{i}")
    for sv in (-1, 1):
        for (u0, u1) in ((-0.78, -0.1), (0.1, 0.78)):
            box("decor", "wood", *rect(u0, u1, sv * 0.55, sv * 0.58), 0.22, 0.82, f"case_panel_{i}_{sv}_{u0:.1f}")
    for su in (-1, 1):
        box("decor", "wood", *rect(su * 0.85, su * 0.88, -0.45, 0.45), 0.22, 0.82, f"case_panel_end_{i}_{su}")
    box("decor", "brass", *rect(-0.9, 0.9, -0.6, 0.6), 0.92, 0.97, f"case_lip_{i}")
    box("decor", "velvet", *rect(-0.8, 0.8, -0.5, 0.5), 0.97, 1.0, f"case_cloth_{i}")
    # the glass top in a brass frame
    box("decor", "case_glass", *rect(-0.82, 0.82, -0.52, 0.52), 1.0, top, f"case_glass_{i}")
    for pu, pv in ((-0.83, -0.53), (0.83, -0.53), (-0.83, 0.53), (0.83, 0.53)):
        box("decor", "brass", *rect(pu - 0.025, pu + 0.025, pv - 0.025, pv + 0.025), 0.97, top + 0.03, f"case_post_{i}_{pu:.1f}_{pv:.1f}")
    for (u0, u1, v0, v1) in ((-0.85, 0.85, -0.55, -0.51), (-0.85, 0.85, 0.51, 0.55), (-0.85, -0.81, -0.55, 0.55), (0.81, 0.85, -0.55, 0.55)):
        box("decor", "brass", *rect(u0, u1, v0, v1), top, top + 0.04)
    page_yaw = {"e": math.pi / 2, "w": -math.pi / 2, "s": 0.0}[reader]
    if i == 1:
        # the retro computer (Poly Haven, CC0) on the cloth, its screen to the reader, the page in front
        place_asset("polyhaven/television_02", point(0.3, 0.0, 1.0), scale=1.25, yaw=page_yaw, name="case_computer")
        quad(f"exp_{i}", "lightbox", point(-0.42, -0.02, 1.005), 0.72, 0.45, "up", yaw=page_yaw)
    else:
        # an open book on a low slanted stand: two leaves rising in a V from the spine, the page on top
        box("decor", "wood", *rect(-0.42, 0.42, -0.3, 0.3), 1.0, 1.06, f"book_stand_{i}")
        bm = bmesh.new()
        for leaf in (-1, 1):
            if rdx:
                vs = pw.add_box(bm, (0, 0, 0), (0.56, 0.4, 0.08), 0.0)
                bmesh.ops.rotate(bm, verts=vs, cent=(0, 0, 0), matrix=Matrix.Rotation(leaf * math.radians(7), 3, "X"))
            else:
                vs = pw.add_box(bm, (0, 0, 0), (0.4, 0.56, 0.08), 0.0)
                bmesh.ops.rotate(bm, verts=vs, cent=(0, 0, 0), matrix=Matrix.Rotation(-leaf * math.radians(7), 3, "Y"))
            bmesh.ops.translate(bm, verts=vs, vec=Vector(point(leaf * 0.21, 0.0, 1.12)))
        obj(f"book_block_{i}", bm, "paper", "decor")
        box("decor", "wood", *rect(-0.29, 0.29, -0.03, 0.03), 1.06, 1.1, f"book_spine_{i}")
        quad(f"exp_{i}", "lightbox", point(0.0, -0.02, 1.185), 0.8, 0.5, "up", yaw=page_yaw)
    # a brass plaque on the reader's side, and where the visitor stands
    box("decor", "brass", *rect(-0.3, 0.3, 0.58, 0.6), 0.66, 0.9, f"case_plaque_back_{i}")
    quad(f"plaque_exp_{i}", "label", point(0.0, 0.605, 0.78), 0.56, 0.22, reader, group="decor")
    pw.empty(f"spot_exp_{i}", point(0.0, 1.7, 0.0))

# --- the bench and the lectern ---------------------------------------------------------------------
# the bench on the open floor to the left of the entrance, across the nave, with open trapezoid legs
BX0, BX1, BY0, BY1 = -4.4, -2.0, -15.9, -15.2
box("decor", "wood", BX0, BX1, BY0, BY1, 0.4, 0.48, "bench")
box("decor", "velvet", BX0 + 0.05, BX1 - 0.05, BY0 + 0.05, BY1 - 0.05, 0.48, 0.6, "bench_cushion")
for sx in (BX0 + 0.3, BX1 - 0.3):
    bm = bmesh.new()
    verts_low = [bm.verts.new(Vector((sx + tx * 0.22, y_, 0.0))) for tx, y_ in ((-1, BY0 - 0.15), (1, BY0 - 0.15), (1, BY1 + 0.15), (-1, BY1 + 0.15))]
    verts_top = [bm.verts.new(Vector((sx + tx * 0.1, y_, 0.4))) for tx, y_ in ((-1, BY0 + 0.1), (1, BY0 + 0.1), (1, BY1 - 0.1), (-1, BY1 - 0.1))]
    loft(bm, [verts_low, verts_top])
    bm.faces.new(list(reversed(verts_low)))
    bm.faces.new(verts_top)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    obj(f"bench_leg_{sx:.1f}", bm, "wood", "decor")
box("solid", "collider", BX0 - 0.1, BX1 + 0.1, BY0 - 0.2, BY1 + 0.2, 0, 0.5, "bench_collider")

LX, LY = 0.0, -15.6
box("solid", "wood", LX - 0.3, LX + 0.3, LY - 0.3, LY + 0.3, 0, 0.1, "lectern")
box("decor", "wood", LX - 0.3, LX + 0.3, LY - 0.3, LY + 0.3, 0, 0.12, "lectern_base")
cyl("decor", "wood", (LX, LY, 0.12), (LX, LY, 1.0), 0.09, seg=10, name="lectern_column")
bm = bmesh.new()
vs = pw.add_box(bm, (0, 0, 0), (0.9, 0.62, 0.06), 0.0)
bmesh.ops.rotate(bm, verts=vs, cent=(0, 0, 0), matrix=Matrix.Rotation(math.radians(-22), 3, "X"))
bmesh.ops.translate(bm, verts=vs, vec=Vector((LX, LY, 1.1)))
obj("lectern_top", bm, "wood", "decor")
quad("contact_panel", "label", (LX, LY, 1.135), 0.8, 0.5, "up", group="exhibits", tilt=math.radians(22), yaw=math.pi)
pw.empty("spot_contact", (LX, LY + 1.4, 0))
box("decor", "brass", LX - 0.36, LX + 0.36, LY - 0.33, LY - 0.3, 0.72, 0.98, "lectern_sign_back")
quad("sign_contact", "label", (LX, LY - 0.335, 0.85), 0.7, 0.24, "s")
pw.empty("spawn", (1.5, -6.0, 0))

for template in _asset_templates:
    bpy.data.objects.remove(template, do_unlink=True)

# the decor is some 1800 small meshes; joined per material they become a few dozen draw calls, and
# the runtime still finds everything it needs by name (exhibits, glass, panels, signs, empties)
# the generated banners and sconces stay apart so their copies keep sharing one mesh in the GLB
KEEP_APART = ("glass_", "canvas_", "label_", "exp_", "plaque_", "deco_canvas", "about_panel", "contact_panel", "sign_", "shadow_", "banner", "sconce")
by_material = {}
for o in list(groups["decor"].children):
    if o.type != "MESH" or o.name.startswith(KEEP_APART):
        continue
    key = o.data.materials[0].name if o.data.materials else ""
    by_material.setdefault(key, []).append(o)
for key, objs in by_material.items():
    if len(objs) < 2:
        continue
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    objs[0].name = f"decor_{key}"
pw.export_glb(args.out)
