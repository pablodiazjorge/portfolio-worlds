"""AERIS: a compact beige monitor from the eighties, the kind that sat on a desk with a floppy
drive, hung from an eyebolt screwed into its top. The origin is the centre of the eyebolt's
ring, where the last link of the chain hooks in, so the app hangs the whole model by that point.
The screen faces -Y in Blender (+Z after export) and carries UVs for the app's own picture.

Hierarchy: monitor (empty) with one mesh per material: case, case_dark, vent, frame, screen,
metal, led. A separate `link` mesh at the origin is one chain link for the app to instance.
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
    "case": pw.material("case", "#d6cfb8", 0.55),
    "case_dark": pw.material("case_dark", "#bfb79f", 0.6),
    "vent": pw.material("vent", "#5e5947", 0.85),
    "frame": pw.material("frame", "#35363a", 0.6),
    "screen": pw.material("screen", "#232c38", 0.12),
    "metal": pw.material("metal", "#8e9198", 0.35, 1.0),
    "led": pw.material("led", "#ffb347", 0.4, emission="#ff9a2a", emission_strength=4.0),
}

root = pw.empty("monitor", (0, 0, 0))
meshes = {}


def bm_for(mat):
    if mat not in meshes:
        meshes[mat] = bmesh.new()
    return meshes[mat]


def fresh(bm, before):
    """Vertices added since `before`, a bevel's included."""
    return [v for v in bm.verts if v.is_valid and v not in before]


def box(mat, center, size, rotation=0.0, bevel=0.0, segments=2):
    bm = bm_for(mat)
    before = set(bm.verts)
    vs = pw.add_box(bm, (0, 0, 0), size, 0.0)
    if bevel > 0:
        edges = list({e for v in vs for e in v.link_edges})
        bmesh.ops.bevel(bm, geom=edges, offset=bevel, segments=segments, profile=0.5, affect="EDGES", clamp_overlap=True)
    moved = fresh(bm, before)
    bmesh.ops.rotate(bm, verts=moved, cent=(0, 0, 0), matrix=Matrix.Rotation(rotation, 3, "Z"))
    bmesh.ops.translate(bm, verts=moved, vec=Vector(center))
    return moved


def cyl(mat, a, b, r1, r2=None, seg=16):
    bm = bm_for(mat)
    a, b = Vector(a), Vector(b)
    d = b - a
    vs = pw.add_cone(bm, (0, 0, 0), r1, r1 if r2 is None else r2, max(d.length, 1e-4), segments=seg)
    rotation = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix()
    bmesh.ops.rotate(bm, verts=vs, cent=(0, 0, 0), matrix=rotation)
    bmesh.ops.translate(bm, verts=vs, vec=a)
    return vs


def tube(mat, points, radius, sides=8, closed=True):
    """A round tube through a polyline, for the chain link and the eyebolt ring."""
    bm = bm_for(mat)
    pts = [Vector(p) for p in points]
    n = len(pts)
    rings = []
    for k in range(n):
        prev = pts[k - 1] if closed else pts[max(k - 1, 0)]
        nxt = pts[(k + 1) % n] if closed else pts[min(k + 1, n - 1)]
        t = (nxt - prev).normalized()
        ref = Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))
        a = t.cross(ref).normalized()
        b = t.cross(a).normalized()
        rings.append([bm.verts.new(pts[k] + (a * math.cos(s / sides * math.tau) + b * math.sin(s / sides * math.tau)) * radius) for s in range(sides)])
    for k in range(n if closed else n - 1):
        k2 = (k + 1) % n
        for s in range(sides):
            s2 = (s + 1) % sides
            bm.faces.new((rings[k][s], rings[k][s2], rings[k2][s2], rings[k2][s]))
    return [v for ring in rings for v in ring]


def finish(name_prefix, smooth=()):
    for mat, bm in meshes.items():
        obj = pw.bm_object(f"{name_prefix}_{mat}", bm, M[mat], smooth=mat in smooth)
        obj.parent = root
    meshes.clear()


# --- the case ---------------------------------------------------------------------------------
# Width 1.0, the front block 0.44 deep and the rear block tapering behind it; the eyebolt ring
# sits at the origin and the case hangs 0.1 below it. The front face rakes back 7 degrees.
W, H, D1 = 1.0, 0.86, 0.44
TOP = -0.1
BOT = TOP - H
RAKE = math.tan(math.radians(7.0))
FRONT = -0.2  # y of the front face at the bottom edge

# main block, bevelled, slightly narrower than the front plate so the plate's rim reads, and
# starting behind the plate's recess so nothing cuts through the glass
main = box("case", (0, FRONT + 0.1 + (D1 - 0.08) / 2, (TOP + BOT) / 2), (W - 0.02, D1 - 0.08, H - 0.02), bevel=0.035, segments=3)
for v in main:
    v.co.y += (v.co.z - BOT) * RAKE

# the front plate: a frame with the screen opening, the recess walls and the recess floor
bm = bm_for("case")
before = set(bm.verts)
PLATE = 0.11
ow, oh = W / 2, H / 2
iw, ih = 0.345, 0.285
cz = (TOP + BOT) / 2 + 0.04  # the screen sits a little above the middle
outer = [(-ow, FRONT, BOT), (ow, FRONT, BOT), (ow, FRONT, TOP), (-ow, FRONT, TOP)]
inner = [(-iw, FRONT, cz - ih), (iw, FRONT, cz - ih), (iw, FRONT, cz + ih), (-iw, FRONT, cz + ih)]
deep = [(x, y + 0.095, z) for x, y, z in inner]
back = [(x, y + PLATE, z) for x, y, z in outer]
o_v = [bm.verts.new(Vector(p)) for p in outer]
i_v = [bm.verts.new(Vector(p)) for p in inner]
d_v = [bm.verts.new(Vector(p)) for p in deep]
b_v = [bm.verts.new(Vector(p)) for p in back]
for k in range(4):
    k2 = (k + 1) % 4
    bm.faces.new((o_v[k], o_v[k2], i_v[k2], i_v[k]))  # frame
    bm.faces.new((i_v[k], i_v[k2], d_v[k2], d_v[k]))  # recess wall
    bm.faces.new((o_v[k2], o_v[k], b_v[k], b_v[k2]))  # plate side
bm.faces.new((d_v[3], d_v[2], d_v[1], d_v[0]))  # recess floor
bm.faces.new(b_v)  # plate back, hidden by the main block
plate_verts = o_v + i_v + d_v + b_v
bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
rim = [e for e in bm.edges if e.verts[0] in o_v and e.verts[1] in o_v]
bmesh.ops.bevel(bm, geom=rim, offset=0.03, segments=3, profile=0.5, affect="EDGES", clamp_overlap=True)
for v in fresh(bm, before):
    v.co.y += (v.co.z - BOT) * RAKE

# the recess gets a dark inner frame, a hair inside the recess walls
bm = bm_for("frame")
before = set(bm.verts)
fw, fh, lip = iw - 0.004, ih - 0.004, 0.028
o2 = [(-fw, FRONT + 0.02, cz - fh), (fw, FRONT + 0.02, cz - fh), (fw, FRONT + 0.02, cz + fh), (-fw, FRONT + 0.02, cz + fh)]
i2 = [(-fw + lip, FRONT + 0.085, cz - fh + lip), (fw - lip, FRONT + 0.085, cz - fh + lip), (fw - lip, FRONT + 0.085, cz + fh - lip), (-fw + lip, FRONT + 0.085, cz + fh - lip)]
a_v = [bm.verts.new(Vector(p)) for p in o2]
c_v = [bm.verts.new(Vector(p)) for p in i2]
for k in range(4):
    k2 = (k + 1) % 4
    bm.faces.new((a_v[k], a_v[k2], c_v[k2], c_v[k]))
bm.faces.new((c_v[3], c_v[2], c_v[1], c_v[0]))
# an open sheet: make every face look out of the recess, towards the viewer
bm.normal_update()
for f in bm.faces:
    if f.normal.y > 0:
        f.normal_flip()
for v in fresh(bm, before):
    v.co.y += (v.co.z - BOT) * RAKE

# the glass: a bulged grid with UVs, nudged in front of the inner frame's floor
bm = bm_for("screen")
before = set(bm.verts)
uv_layer = bm.loops.layers.uv.new("UVMap")
gw, gh, bulge = fw - lip + 0.01, fh - lip + 0.01, 0.045
NU, NV = 24, 20
grid = []
for j in range(NV + 1):
    row = []
    for i in range(NU + 1):
        u, vv = i / NU, j / NV
        x, z = (u - 0.5) * 2 * gw, (vv - 0.5) * 2 * gh
        dome = (1.0 - (x / gw) ** 2) * (1.0 - (z / gh) ** 2)
        y = FRONT + 0.05 - bulge * dome ** 0.8
        row.append(bm.verts.new(Vector((x, y, cz + z))))
    grid.append(row)
for j in range(NV):
    for i in range(NU):
        face = bm.faces.new((grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]))
        for loop in face.loops:
            v = loop.vert
            loop[uv_layer].uv = ((v.co.x / gw) * 0.5 + 0.5, ((v.co.z - cz) / gh) * 0.5 + 0.5)
bm.normal_update()
for f in bm.faces:
    if f.normal.y > 0:
        f.normal_flip()
for v in fresh(bm, before):
    v.co.y += (v.co.z - BOT) * RAKE

# rear block, lower and narrower, with the vents
RW, RH, RD = 0.84, H - 0.16, 0.42
RZ = (TOP + BOT) / 2 - 0.02
RY = FRONT + D1 + 0.02 + RD / 2 - 0.06
box("case", (0, RY, RZ), (RW, RD, RH), bevel=0.03, segments=3)
for sx in (-1, 1):
    for k in range(14):
        z = RZ - RH / 2 + 0.11 + k * 0.034
        box("vent", (sx * (RW / 2 + 0.001), RY + 0.02, z), (0.012, RD - 0.16, 0.012))
for row in range(2):
    for k in range(9):
        box("vent", (-0.3 + k * 0.075, RY - 0.08 + row * 0.16, RZ + RH / 2 + 0.001), (0.03, 0.09, 0.008))

# base: a plinth under the front block with a recessed foot band
box("case", (0, FRONT + D1 / 2 + 0.05, BOT - 0.035), (W - 0.06, D1 + 0.06, 0.07), bevel=0.02)
box("case_dark", (0, FRONT + D1 / 2 + 0.06, BOT - 0.085), (W - 0.16, D1 - 0.06, 0.03))

# chin: the floppy slot, a dial and the power light under the screen
chin = cz - ih - 0.06
box("vent", (-0.18, FRONT + (chin - BOT) * RAKE - 0.002, chin), (0.34, 0.006, 0.014))
box("case_dark", (-0.18, FRONT + (chin - BOT) * RAKE - 0.004, chin), (0.4, 0.004, 0.05))
cyl("case_dark", (0.3, FRONT + (chin - BOT) * RAKE + 0.01, chin), (0.3, FRONT + (chin - BOT) * RAKE - 0.012, chin), 0.022, seg=16)
box("led", (0.4, FRONT + (chin - BOT) * RAKE - 0.004, chin), (0.016, 0.006, 0.01))

# a port on the right side of the front block, a mains lead at the back
cyl("metal", (W / 2 - 0.01, FRONT + 0.12, BOT + 0.12), (W / 2 + 0.008, FRONT + 0.12, BOT + 0.12), 0.012, seg=12)
cyl("frame", (W / 2 + 0.008, FRONT + 0.12, BOT + 0.12), (W / 2 + 0.012, FRONT + 0.12, BOT + 0.12), 0.006, seg=10)

# the eyebolt: a hex nut and washer on the case top, the shaft and the ring
box("metal", (0, 0.02, TOP + 0.012), (0.09, 0.09, 0.024), rotation=math.radians(30))
cyl("metal", (0, 0.02, TOP + 0.024), (0, 0.02, TOP + 0.03), 0.055, seg=6)
cyl("metal", (0, 0.02, TOP + 0.03), (0, 0.02, -0.052), 0.014, seg=10)
RING_R = 0.052
ring = [(math.cos(a) * RING_R, 0.02, math.sin(a) * RING_R) for a in (k / 28 * math.tau for k in range(28))]
tube("metal", ring, 0.012, sides=8)

finish("monitor", smooth=("screen", "metal"))

# --- one chain link, built at the origin along Z for the app to instance ---------------------
LINK_LEN, LINK_W, WIRE = 0.1, 0.046, 0.0085
straight = (LINK_LEN - LINK_W) / 2
path = []
for k in range(10):
    a = math.pi * k / 9
    path.append((math.cos(a) * LINK_W / 2, 0.0, straight + math.sin(a) * LINK_W / 2))
for k in range(10):
    a = math.pi + math.pi * k / 9
    path.append((math.cos(a) * LINK_W / 2, 0.0, -straight + math.sin(a) * LINK_W / 2))
bm = bmesh.new()
pts = [Vector(p) for p in path]
rings = []
n = len(pts)
for k in range(n):
    t = (pts[(k + 1) % n] - pts[k - 1]).normalized()
    a_ = t.cross(Vector((0, 1, 0))).normalized()
    b_ = t.cross(a_).normalized()
    rings.append([bm.verts.new(pts[k] + (a_ * math.cos(s / 8 * math.tau) + b_ * math.sin(s / 8 * math.tau)) * WIRE) for s in range(8)])
for k in range(n):
    k2 = (k + 1) % n
    for s in range(8):
        bm.faces.new((rings[k][s], rings[k][(s + 1) % 8], rings[k2][(s + 1) % 8], rings[k2][s]))
bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
link = pw.bm_object("link", bm, M["metal"], smooth=True)

pw.export_glb(args.out)
