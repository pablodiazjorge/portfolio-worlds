"""AERIS: a heavy-lift quadcopter in the style of a concept render: a faceted hull with a
raised canopy and a glowing spine, four boxy arms with light strips, motor pods with cooling
rings and a glowing crown, and a tapered fin hanging under each pod as a landing leg. An
eyebolt under the belly is where the chain that carries the monitor hooks in.

Hierarchy (empties keep their names in the GLB):
  drone
    hull, canopy, arms, pods, fins, belly and the glow strips
    spin_fl, spin_fr, spin_bl, spin_br   pivots with one propeller each, spun by the app
    gimbal_pivot                         yoke, camera body and lens under the nose
    hook                                 the chain's attachment point under the belly
Materials: body, body_light, carbon, metal, metal_dark, glow, prop, glass, rubber.
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
    "body": pw.material("body", "#15171c", 0.35),
    "body_light": pw.material("body_light", "#262a33", 0.4),
    "carbon": pw.material("carbon", "#1a1c21", 0.4),
    "metal": pw.material("metal", "#9aa0ab", 0.28, 1.0),
    "metal_dark": pw.material("metal_dark", "#3a3e46", 0.4, 0.9),
    "glow": pw.material("glow", "#5ee0ff", 0.3, emission="#5ee0ff", emission_strength=6.0),
    "prop": pw.material("prop", "#0f1114", 0.3),
    "glass": pw.material("glass", "#04060a", 0.05),
    "rubber": pw.material("rubber", "#0e0f12", 0.9),
}

# motor pods at the arm tips, (x, y) in the drone's plane; the nose points to +Y
PODS = {"fl": (-0.95, 0.78), "fr": (0.95, 0.78), "bl": (-0.95, -0.78), "br": (0.95, -0.78)}
SHOULDER = {"fl": (-0.22, 0.2), "fr": (0.22, 0.2), "bl": (-0.22, -0.24), "br": (0.22, -0.24)}


def empty(name, parent=None, location=(0, 0, 0)):
    obj = pw.empty(name, location)
    if parent:
        obj.parent = parent
    return obj


def part(name, bm, mat, parent, smooth=False):
    obj = pw.bm_object(name, bm, M[mat], smooth=smooth)
    obj.parent = parent
    return obj


def bevel_all(bm, offset, segments=1):
    bmesh.ops.bevel(bm, geom=bm.edges[:], offset=offset, segments=segments, profile=0.5, affect="EDGES", clamp_overlap=True)


def rounded_box(size, center=(0, 0, 0), bevel=0.02, segments=1, rotation=0.0):
    bm = bmesh.new()
    pw.add_box(bm, center, size, rotation)
    if bevel > 0:
        bevel_all(bm, bevel, segments)
    return bm


def ring(bm, center, major, minor, seg=24, sides=6, plane="XY"):
    """A torus lying in `plane` through `center`."""
    before = set(bm.verts)
    circle = bmesh.ops.create_circle(bm, cap_ends=False, radius=minor, segments=sides)["verts"]
    bmesh.ops.rotate(bm, verts=circle, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, "X"))
    bmesh.ops.translate(bm, verts=circle, vec=Vector((major, 0, 0)))
    edges = list({e for v in circle for e in v.link_edges})
    bmesh.ops.spin(bm, geom=circle + edges, cent=(0, 0, 0), axis=(0, 0, 1), angle=math.tau, steps=seg, use_duplicate=False)
    vs = [v for v in bm.verts if v.is_valid and v not in before]
    bmesh.ops.remove_doubles(bm, verts=vs, dist=1e-4)
    vs = [v for v in bm.verts if v.is_valid and v not in before]
    if plane == "XZ":
        bmesh.ops.rotate(bm, verts=vs, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, "X"))
    elif plane == "YZ":
        bmesh.ops.rotate(bm, verts=vs, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, "Y"))
    bmesh.ops.translate(bm, verts=vs, vec=Vector(center))
    return vs


def section(y, hw, h, zc):
    """A faceted cross-section of the hull: a ridge on top, flat sides and a narrow belly."""
    return [
        (0.0, y, zc + h * 0.5),
        (hw * 0.9, y, zc + h * 0.22),
        (hw, y, zc - h * 0.05),
        (hw * 0.82, y, zc - h * 0.36),
        (hw * 0.35, y, zc - h * 0.5),
        (-hw * 0.35, y, zc - h * 0.5),
        (-hw * 0.82, y, zc - h * 0.36),
        (-hw, y, zc - h * 0.05),
        (-hw * 0.9, y, zc + h * 0.22),
    ]


def loft(bm, sections):
    """Skins a run of cross-sections into one closed shell."""
    rings = [[bm.verts.new(Vector(p)) for p in s] for s in sections]
    n = len(rings[0])
    for a, b in zip(rings, rings[1:]):
        for i in range(n):
            bm.faces.new((a[i], a[(i + 1) % n], b[(i + 1) % n], b[i]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])


root = empty("drone")

# --- hull and canopy ---------------------------------------------------------------------------
bm = bmesh.new()
loft(bm, [
    section(-0.58, 0.05, 0.08, 0.07),
    section(-0.42, 0.13, 0.17, 0.08),
    section(-0.16, 0.2, 0.25, 0.1),
    section(0.12, 0.21, 0.25, 0.1),
    section(0.36, 0.15, 0.18, 0.1),
    section(0.55, 0.06, 0.08, 0.1),
])
part("hull", bm, "body", root)
bm = bmesh.new()
loft(bm, [
    section(-0.32, 0.08, 0.03, 0.215),
    section(-0.16, 0.17, 0.11, 0.225),
    section(0.06, 0.17, 0.11, 0.225),
    section(0.24, 0.07, 0.03, 0.21),
])
part("canopy", bm, "body_light", root)
# the glowing spine and the slits along the canopy
bm = bmesh.new()
pw.add_box(bm, (0, -0.04, 0.277), (0.028, 0.42, 0.012))
for sx in (-1, 1):
    for y in (-0.2, -0.1, 0.0, 0.1):
        pw.add_box(bm, (sx * 0.148, y, 0.248), (0.012, 0.05, 0.01))
# intakes on the hull sides
for sx in (-1, 1):
    for y in (-0.3, -0.22, -0.14):
        pw.add_box(bm, (sx * 0.192, y, 0.085), (0.012, 0.04, 0.025))
part("glow_body", bm, "glow", root)
# the eye on the nose: a glowing ring round a lens
bm = bmesh.new()
ring(bm, (0, 0.553, 0.1), 0.042, 0.007, seg=24, sides=6, plane="XZ")
part("glow_eye", bm, "glow", root, smooth=True)
bm = bmesh.new()
verts = pw.add_cone(bm, (0, 0, 0), 0.034, 0.034, 0.02, segments=20)
bmesh.ops.rotate(bm, verts=verts, cent=(0, 0, 0), matrix=Matrix.Rotation(-math.pi / 2, 3, "X"))
bmesh.ops.translate(bm, verts=verts, vec=Vector((0, 0.56, 0.1)))
part("eye_lens", bm, "glass", root, smooth=True)
# two antenna blades on the tail
bm = bmesh.new()
for sx in (-0.07, 0.07):
    fin = bmesh.ops.create_cube(bm, size=1.0)["verts"]
    bmesh.ops.scale(bm, vec=Vector((0.01, 0.16, 0.1)), verts=fin)
    for v in fin:
        if v.co.z > 0:
            v.co.y -= 0.06
    bmesh.ops.translate(bm, verts=fin, vec=Vector((sx, -0.46, 0.17)))
part("tail_fins", bm, "body_light", root)

# --- belly, winch and the hook for the chain ----------------------------------------------------
part("belly", rounded_box((0.26, 0.52, 0.03), (0, -0.02, -0.035), 0.008), "metal_dark", root)
part("winch", rounded_box((0.14, 0.14, 0.08), (0, -0.02, -0.08), 0.012), "metal", root)
bm = bmesh.new()
pw.add_cone(bm, (0, -0.02, -0.15), 0.012, 0.012, 0.04, segments=10)
ring(bm, (0, -0.02, -0.175), 0.028, 0.007, seg=20, sides=6, plane="XZ")
part("eyebolt", bm, "metal", root, smooth=True)
empty("hook", root, (0, -0.02, -0.175))

# --- arms, pods, fins and propellers ------------------------------------------------------------
for key, (px, py) in PODS.items():
    sx, sy = SHOULDER[key]
    dx, dy = px - sx, py - sy
    length = math.hypot(dx, dy)
    angle = math.atan2(dy, dx)
    outward = Vector((math.cos(angle), math.sin(angle), 0))
    part(f"shoulder_{key}", rounded_box((0.18, 0.15, 0.13), (sx, sy, 0.03), 0.02, 1, angle), "body_light", root)
    bm = rounded_box((length + 0.08, 0.13, 0.085), (0, 0, 0), 0.018)
    bmesh.ops.translate(bm, verts=bm.verts[:], vec=Vector((length / 2, 0, 0.03)))
    bmesh.ops.rotate(bm, verts=bm.verts[:], cent=(0, 0, 0), matrix=Matrix.Rotation(angle, 3, "Z"))
    bmesh.ops.translate(bm, verts=bm.verts[:], vec=Vector((sx, sy, 0)))
    part(f"arm_{key}", bm, "carbon", root)
    # light strips along the top and both sides of the arm
    bm = bmesh.new()
    pw.add_box(bm, (length * 0.52, 0, 0.074), (length * 0.62, 0.03, 0.01))
    for side in (-1, 1):
        pw.add_box(bm, (length * 0.55, side * 0.066, 0.02), (length * 0.5, 0.008, 0.028))
    bmesh.ops.rotate(bm, verts=bm.verts[:], cent=(0, 0, 0), matrix=Matrix.Rotation(angle, 3, "Z"))
    bmesh.ops.translate(bm, verts=bm.verts[:], vec=Vector((sx, sy, 0)))
    part(f"glow_arm_{key}", bm, "glow", root)

    # the motor pod: housing with cooling rings, a cap and a glowing crown
    bm = bmesh.new()
    pw.add_cone(bm, (px, py, 0.02), 0.14, 0.13, 0.19, segments=24)
    part(f"motor_{key}", bm, "metal_dark", root, smooth=True)
    bm = bmesh.new()
    for z in (0.07, 0.11, 0.15):
        ring(bm, (px, py, z), 0.138, 0.007, seg=24, sides=5)
    pw.add_cone(bm, (px, py, 0.21), 0.1, 0.085, 0.035, segments=20)
    part(f"motor_rings_{key}", bm, "metal_dark", root, smooth=True)
    bm = bmesh.new()
    ring(bm, (px, py, 0.212), 0.118, 0.006, seg=24, sides=5)
    part(f"glow_crown_{key}", bm, "glow", root, smooth=True)

    # the fin under the pod: a tapered wedge leaning outward, the landing leg
    bm = bmesh.new()
    fin = bmesh.ops.create_cube(bm, size=1.0)["verts"]
    for v in fin:
        t = 0.5 - v.co.z  # 0 at the top, 1 at the bottom
        v.co.x *= 0.22 - 0.15 * t
        v.co.y *= 0.16 - 0.11 * t
        v.co.z = 0.03 - t * 0.46
    bmesh.ops.rotate(bm, verts=fin, cent=(0, 0, 0.03), matrix=Matrix.Rotation(math.radians(-11), 3, "Y"))
    bmesh.ops.rotate(bm, verts=fin, cent=(0, 0, 0), matrix=Matrix.Rotation(angle, 3, "Z"))
    bmesh.ops.translate(bm, verts=fin, vec=Vector((px, py, 0)))
    bevel_all(bm, 0.01, 1)
    part(f"fin_{key}", bm, "body", root)
    # a glowing panel on the fin's outer face and a pad at its tip
    bm = bmesh.new()
    panel = pw.add_box(bm, (0.085, 0, -0.14), (0.012, 0.05, 0.16))
    bmesh.ops.rotate(bm, verts=panel, cent=(0, 0, 0.03), matrix=Matrix.Rotation(math.radians(-11), 3, "Y"))
    bmesh.ops.rotate(bm, verts=panel, cent=(0, 0, 0), matrix=Matrix.Rotation(angle, 3, "Z"))
    bmesh.ops.translate(bm, verts=panel, vec=Vector((px, py, 0)))
    part(f"glow_fin_{key}", bm, "glow", root)
    bm = bmesh.new()
    pad = pw.add_box(bm, (0.0, 0, -0.44), (0.075, 0.06, 0.03))
    bmesh.ops.rotate(bm, verts=pad, cent=(0, 0, 0.03), matrix=Matrix.Rotation(math.radians(-11), 3, "Y"))
    bmesh.ops.rotate(bm, verts=pad, cent=(0, 0, 0), matrix=Matrix.Rotation(angle, 3, "Z"))
    bmesh.ops.translate(bm, verts=pad, vec=Vector((px, py, 0)))
    part(f"pad_{key}", bm, "rubber", root)

    # propeller on its own pivot so the app can spin it
    pivot = empty(f"spin_{key}", root, (px, py, 0.25))
    direction = 1 if key in ("fl", "br") else -1
    bm = bmesh.new()
    pw.add_cone(bm, (0, 0, -0.01), 0.045, 0.038, 0.035, segments=16)
    for side in (0, 1):
        blade = bmesh.ops.create_cube(bm, size=1.0)["verts"]
        bmesh.ops.scale(bm, vec=Vector((0.64, 0.075, 0.01)), verts=blade)
        bmesh.ops.translate(bm, verts=blade, vec=Vector((0.36, 0, 0.004)))
        for v in blade:
            r = max(0.0, v.co.x)
            twist = direction * (0.36 - r * 0.4)
            v.co.y, v.co.z = v.co.y * math.cos(twist) - v.co.z * math.sin(twist), v.co.y * math.sin(twist) + v.co.z * math.cos(twist)
            v.co.y *= 1.0 - 0.5 * (r / 0.68) ** 2
            v.co.y -= 0.05 * (r / 0.68) ** 2  # swept back
        bmesh.ops.rotate(bm, verts=blade, cent=(0, 0, 0), matrix=Matrix.Rotation(side * math.pi, 3, "Z"))
    part(f"prop_{key}", bm, "prop", pivot)

# --- camera and gimbal under the nose ----------------------------------------------------------
gimbal = empty("gimbal_pivot", root, (0, 0.34, -0.04))
bm = bmesh.new()
pw.add_box(bm, (0, 0, 0.03), (0.16, 0.05, 0.015))
pw.add_box(bm, (-0.085, 0, -0.03), (0.015, 0.04, 0.12))
pw.add_box(bm, (0.085, 0, -0.03), (0.015, 0.04, 0.12))
part("gimbal_yoke", bm, "metal", gimbal)
part("camera_body", rounded_box((0.13, 0.11, 0.1), (0, 0, -0.05), 0.02, 2), "body_light", gimbal)
bm = bmesh.new()
verts = pw.add_cone(bm, (0, 0, 0), 0.04, 0.036, 0.05, segments=20)
bmesh.ops.rotate(bm, verts=verts, cent=(0, 0, 0), matrix=Matrix.Rotation(-math.pi / 2, 3, "X"))
bmesh.ops.translate(bm, verts=verts, vec=Vector((0, 0.055, -0.05)))
part("lens_ring", bm, "metal", gimbal, smooth=True)
bm = bmesh.new()
verts = pw.add_cone(bm, (0, 0, 0), 0.03, 0.03, 0.01, segments=20)
bmesh.ops.rotate(bm, verts=verts, cent=(0, 0, 0), matrix=Matrix.Rotation(-math.pi / 2, 3, "X"))
bmesh.ops.translate(bm, verts=verts, vec=Vector((0, 0.1, -0.05)))
part("lens_glass", bm, "glass", gimbal, smooth=True)

pw.export_glb(args.out)
