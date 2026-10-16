"""HELIOS: an orbital station with a habitat ring, drawn after the first picture Qwen-Image made for it
(a wheel on four spokes with tank modules, a hub tower, a docking tube and two solar wings on trusses),
plus the generated shuttle that flies to it and the generated buoy the route is marked with. As in the
picture, the ring is a polygon of sixteen straight drums joined at the gold bands by collars a little
thicker than the drums, and the tanks, the tower and the docking tube are sunk between their bands too,
so the hull reads as built from sections rather than turned smooth.

Blender axes (the station's own frame, which the scene places as it is): the hub axis runs along Y,
the shuttle approaches from -Y, the ring lies in the X-Z plane and the wings run along X. The shuttle
points along +X. Top-level empties: station (with station_body, the group the scene spins about the
hub axis, and dock, the point the shuttle's centre sits at when docked), shuttle, buoy (a template the
scene clones at the waypoints).
Materials the app replaces: hull, truss, solar, radiator, glass, gold, engine_glow, beacon_red,
beacon_green, dock_light, window_light, buoy_body.
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
    "buoy_body": pw.material("buoy_body", "#aeb3ba", 0.5, 0.3),
    "dock_field": pw.material("dock_field", "#5fb4ff", 0.2, emission="#5fb4ff", emission_strength=2.0),
}

station = pw.empty("station", (0, 0, 0))
shuttle = pw.empty("shuttle", (0, 0, 0))

# the shuttle and the buoy generated with Qwen-Image and TRELLIS.2 (tools/assets/trellis, prepared by
# statue_prepare.py) replace the drawn ones when their files exist; each is imported under its empty
ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "trellis")
SHUTTLE_GLB = os.path.join(ASSETS, "helios_shuttle.glb")
BUOY_GLB = os.path.join(ASSETS, "helios_buoy.glb")
BUOY_STROBE_Z = 0.52  # the centre of the generated buoy's red lamp, measured on the prepared mesh (its top at 0.61 m)
# the prepared shuttle already points its nose to +x, as the drawn one did, so the scene's quarter turn fits
SHUTTLE_SCALE, SHUTTLE_YAW, SHUTTLE_ROLL = 1.0, 0.0, 0.0

# --- the station's measures, read off the picture and scaled to a 30 m ring ------------------------
RING_R, RING_TUBE = 13.0, 1.9  # centre-line radius of the habitat ring and the radius of its collars
RECESS, COLLAR = 0.12, 0.8  # how far the skin sinks between the bands, and the length of the collars under them
HUB_R = 2.6  # the hub tower
TANK_R, TANK_LEN, TANK_AT = 1.9, 5.0, 6.6  # the modules on the spokes: radius, length, distance of their centre from the axis
SPOKE_R = 0.9
DOCK_TUBE_R, DOCK_END = 1.6, -5.4  # the docking tube on the approach side and the y of its collar face
DOCK = (0.0, DOCK_END - 1.7, 0.0)  # where the shuttle's centre sits when docked: its nose on the collar (Blender axes: -y is the glTF +z)
WING_X0, WING_X1 = 7.5, 29.6  # the trusses run from past the tanks, through the ring, to the wing tips


def place_generated(path, parent, name, scale, yaw, roll, shift=(0.0, 0.0, 0.0)):
    """Imports a prepared GLB and parents its meshes to `parent`, turned about X (roll) and Z (yaw) and
    scaled; `shift` moves the mesh itself first, so an axis the scene turns about passes through the origin."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    imported = [o for o in bpy.data.objects if o not in before]
    for o in imported:
        if o.type != "MESH":
            bpy.data.objects.remove(o, do_unlink=True)
            continue
        if any(shift):
            o.data.transform(Matrix.Translation(Vector(shift)))
        o.parent = parent
        o.name = name
        o.rotation_mode = "XYZ"
        o.rotation_euler = (roll, 0, yaw)
        o.scale = (scale, scale, scale)


def obj(name, bm, mat, parent, smooth=False):
    o = pw.bm_object(name, bm, M[mat], smooth=smooth)
    o.parent = parent
    return o


def cylinder_x(bm, x0, x1, radius, segments=24, y=0.0, z=0.0, radius2=None):
    verts = pw.add_cone(bm, (0, 0, 0), radius, radius2 if radius2 is not None else radius, x1 - x0, segments=segments)
    bmesh.ops.rotate(bm, verts=verts, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, "Y"))
    bmesh.ops.translate(bm, verts=verts, vec=Vector((x0, y, z)))
    return verts


def cylinder_between(bm, a, b, radius, segments=8, radius2=None):
    a, b = Vector(a), Vector(b)
    d = b - a
    verts = pw.add_cone(bm, (0, 0, 0), radius, radius2 if radius2 is not None else radius, d.length, segments=segments)
    rot = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix()
    bmesh.ops.rotate(bm, verts=verts, cent=(0, 0, 0), matrix=rot)
    bmesh.ops.translate(bm, verts=verts, vec=a)
    return verts


def box_at(bm, center, size, rot=None):
    """A box of `size` turned by the matrix `rot` (about the origin) and set at `center`."""
    verts = pw.add_box(bm, (0, 0, 0), size)
    if rot is not None:
        bmesh.ops.rotate(bm, verts=verts, cent=(0, 0, 0), matrix=rot)
    bmesh.ops.translate(bm, verts=verts, vec=Vector(center))
    return verts


def about_y(angle):
    return Matrix.Rotation(angle, 3, "Y")


def tube_y(bm, y0, y1, r_out, r_in, segments=48):
    """A hollow tube along Y between y0 and y1: an annulus of r_out and r_in extruded, walls inside
    and out. Returns the new vertices."""
    outer = bmesh.ops.create_circle(bm, cap_ends=False, radius=r_out, segments=segments)["verts"]
    inner = bmesh.ops.create_circle(bm, cap_ends=False, radius=r_in, segments=segments)["verts"]
    ring = outer + inner
    bmesh.ops.rotate(bm, verts=ring, cent=(0, 0, 0), matrix=Matrix.Rotation(-math.pi / 2, 3, "X"))
    bmesh.ops.translate(bm, verts=ring, vec=Vector((0, y0, 0)))
    vs = set(ring)
    edges = [e for e in bm.edges if e.verts[0] in vs and e.verts[1] in vs]
    faces = bmesh.ops.bridge_loops(bm, edges=edges)["faces"]
    ext = bmesh.ops.extrude_face_region(bm, geom=faces)
    moved = [g for g in ext["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=moved, vec=Vector((0, y1 - y0, 0)))
    return ring + moved


def build_station():
    body = pw.empty("station_body", (0, 0, 0))
    body.parent = station
    hull, gold, truss, solar, glass, windows = bmesh.new(), bmesh.new(), bmesh.new(), bmesh.new(), bmesh.new(), bmesh.new()

    # --- the habitat ring: sixteen straight drums, round in section and sunk, joined every 22.5
    # degrees by a collar at the full radius with a gold band on it, as the picture's segmented ring;
    # three glazed strips per drum on the outer face in two rows and one on the inner face -------------
    def ring_point(a):
        return about_y(a) @ Vector((RING_R, 0, 0))

    for k in range(16):
        a0, a1 = k * math.pi / 8, (k + 1) * math.pi / 8
        am = (a0 + a1) / 2
        p0, p1 = ring_point(a0), ring_point(a1)
        cylinder_between(hull, p0, p1, RING_TUBE - RECESS, 32)
        t = about_y(a0) @ Vector((0, 0, 1))  # the tangent at the joint: the drum ends tilt 11.25 degrees to it and stay inside the collar
        cylinder_between(hull, p0 - t * (COLLAR / 2), p0 + t * (COLLAR / 2), RING_TUBE, 32)
        cylinder_between(gold, p0 - t * 0.16, p0 + t * 0.16, RING_TUBE + 0.06, 32)
        n = about_y(am) @ Vector((1, 0, 0))  # the drum's outward normal: its skin runs along the chord, not the circle
        for j in range(3):
            c = p0.lerp(p1, (j + 1) / 4)
            for y in (0.42, -0.42):
                box_at(windows, c + n * (RING_TUBE - RECESS - 0.03) + Vector((0, y, 0)), (0.08, 0.36, 1.05), about_y(am))
            box_at(windows, c - n * (RING_TUBE - RECESS - 0.03) + Vector((0, 0.2, 0)), (0.08, 0.3, 1.05), about_y(am))

    # --- four spokes with a tank module each: a sunk skin between domed ends, collars at the full
    # radius under the three gold bands and at both ends, portholes in the bays between ---------------
    for k in range(4):
        rot = about_y(k * math.pi / 2)
        d = rot @ Vector((1, 0, 0))
        cylinder_between(hull, d * (HUB_R - 0.3), d * (RING_R - RING_TUBE + 0.4), SPOKE_R, 24)
        c0, c1 = d * (TANK_AT - TANK_LEN / 2), d * (TANK_AT + TANK_LEN / 2)
        cylinder_between(hull, c0, c1, TANK_R - RECESS, 40)
        for c in (c0, c1):
            res = bmesh.ops.create_uvsphere(hull, u_segments=32, v_segments=16, radius=TANK_R)
            bmesh.ops.translate(hull, verts=res["verts"], vec=c)
        for t in (0.0, 0.22, 0.5, 0.78, 1.0):
            c = c0.lerp(c1, t)
            cylinder_between(hull, c - d * 0.3, c + d * 0.3, TANK_R, 40)
        for t in (0.22, 0.5, 0.78):
            c = c0.lerp(c1, t)
            cylinder_between(gold, c - d * 0.09, c + d * 0.09, TANK_R + 0.05, 40)
        for c in (c0 - d * TANK_R * 0.55, c1 + d * TANK_R * 0.55):
            cylinder_between(gold, c - d * 0.12, c + d * 0.12, SPOKE_R + 0.3, 24)
        box_at(hull, d * TANK_AT + Vector((0, TANK_R - RECESS + 0.2, 0)), (1.6, 0.5, 1.2), rot)
        box_at(truss, d * TANK_AT + Vector((0, TANK_R - RECESS + 0.5, 0)), (0.12, 0.6, 0.12), rot)
        # two rings of portholes on each tank, in the middle of the bays either side of the central band
        for along in (TANK_AT - 0.7, TANK_AT + 0.7):
            for j in range(8):
                ang = j * math.pi / 4 + math.pi / 8
                box_at(windows, (along, (TANK_R - RECESS) * math.sin(ang), (TANK_R - RECESS) * math.cos(ang)), (0.42, 0.24, 0.24), rot)
        # a collar where the spoke meets the ring
        cylinder_between(gold, d * (RING_R - RING_TUBE - 0.1), d * (RING_R - RING_TUBE + 0.15), SPOKE_R + 0.12, 24)
        cylinder_between(gold, d * (HUB_R - 0.05), d * (HUB_R + 0.3), SPOKE_R + 0.12, 24)

    # --- the hub: a tower on the far side with a stepped cap and a mast, a cupola on its flank, and
    # the docking tube on the approach side with its flange, hatch and collar; the tower's skin is sunk
    # between collars at its foot, under its two gold rings and under the observation band ------------
    cylinder_between(hull, (0, -2.0, 0), (0, 6.2, 0), HUB_R - RECESS, 48)
    for y0, y1 in ((-2.0, -1.4), (0.5, 1.1), (2.9, 3.5), (4.3, 6.2)):
        cylinder_between(hull, (0, y0, 0), (0, y1, 0), HUB_R, 48)
    cylinder_between(hull, (0, 4.6, 0), (0, 5.6, 0), HUB_R + 0.35, 48)  # the observation band, a little wider
    cylinder_between(hull, (0, 6.2, 0), (0, 7.3, 0), HUB_R, 48, radius2=1.5)
    cylinder_between(hull, (0, 7.3, 0), (0, 8.1, 0), 1.5, 32)
    cylinder_between(hull, (0, 8.1, 0), (0, 8.5, 0), 1.5, 32, radius2=0.45)
    cylinder_between(truss, (0, 8.5, 0), (0, 12.2, 0), 0.09, 8)
    cylinder_between(truss, (0, 10.0, 0), (0, 10.15, 0), 0.55, 12)
    cylinder_between(truss, (0, 11.2, 0), (0, 11.3, 0), 0.3, 10)
    for k in range(3):
        rot = about_y(k * 2 * math.pi / 3 + 0.4)
        a, b = rot @ Vector((1.2, 8.2, 0)), rot @ Vector((2.0, 9.9, 0))
        cylinder_between(truss, a, b, 0.05, 6)
    for y in (0.8, 3.2, 4.55, 5.65):
        cylinder_between(gold, (0, y - 0.08, 0), (0, y + 0.08, 0), HUB_R + (0.05 if y < 4.5 else 0.4), 48)
    for j in range(16):
        box_at(windows, (HUB_R + 0.35 - 0.04, 5.1, 0.0), (0.1, 0.55, 0.62), about_y(j * math.pi / 8 + math.pi / 16))
    for j in range(12):
        box_at(windows, (HUB_R - RECESS - 0.04, 2.0, 0.0), (0.1, 0.4, 0.5), about_y(j * math.pi / 6))
    res = bmesh.ops.create_uvsphere(glass, u_segments=24, v_segments=12, radius=0.85)
    bmesh.ops.translate(glass, verts=res["verts"], vec=Vector((0, 3.9, HUB_R - 0.15)))
    cylinder_between(hull, (0, 3.9, HUB_R - 0.6), (0, 3.9, HUB_R + 0.05), 1.0, 24)
    # the docking tube: hollow, open at the mouth, with a lit corridor inside that ends in a bulkhead,
    # a flange and a gold collar at the mouth, and a plasma field across it (its own material) that
    # the scene makes translucent and alive
    inner_r = DOCK_TUBE_R - 0.18
    tube_y(hull, -2.0, DOCK_END + 0.4, DOCK_TUBE_R - 0.1, inner_r, 48)  # the sunk skin, hollow
    for yc in (-2.3, -3.0, -4.2):  # collars at the hub and under the two gold rings: rings round the skin, so the corridor stays open
        tube_y(hull, yc + 0.25, yc - 0.25, DOCK_TUBE_R, DOCK_TUBE_R - 0.14, 48)
    tube_y(hull, DOCK_END + 0.4, DOCK_END, DOCK_TUBE_R + 0.5, inner_r, 48)  # the flange at the mouth
    tube_y(gold, DOCK_END + 0.02, DOCK_END - 0.1, DOCK_TUBE_R + 0.18, inner_r + 0.06, 48)
    cylinder_between(hull, (0, -1.9, 0), (0, -2.05, 0), inner_r + 0.02, 48)  # the bulkhead
    cylinder_between(gold, (0, -2.05, 0), (0, -2.15, 0), 0.75, 32)
    cylinder_between(hull, (0, -2.15, 0), (0, -2.3, 0), 0.5, 24)
    for j in range(6):  # light strips along the corridor and a lit ring at the bulkhead
        rot = about_y(j * math.pi / 3 + math.pi / 6)
        box_at(windows, (inner_r - 0.05, (DOCK_END - 2.0) / 2 + 0.2, 0.0), (0.08, 2.4, 0.18), rot)
        box_at(windows, (1.05, -2.0, 0.0), (0.35, 0.08, 0.18), rot)
    field = bmesh.new()
    cylinder_between(field, (0, DOCK_END + 0.16, 0), (0, DOCK_END + 0.13, 0), inner_r + 0.04, 64)
    obj("dock_field", field, "dock_field", body, smooth=True)
    for y in (-3.0, -4.2):
        cylinder_between(gold, (0, y - 0.06, 0), (0, y + 0.06, 0), DOCK_TUBE_R + 0.04, 40)

    # --- two solar wings on lattice trusses along X, from past the tanks through the ring to the tips,
    # with two rows of three panels each beyond the ring and a beacon on the tip --------------------
    beacons = {"beacon_red": bmesh.new(), "beacon_green": bmesh.new()}
    for side in (1, -1):
        x0, x1 = side * WING_X0, side * WING_X1
        half = 0.38
        for (y, z) in ((half, half), (half, -half), (-half, half), (-half, -half)):
            cylinder_between(truss, (x0, y, z), (x1, y, z), 0.07, 6)
        n = int(abs(x1 - x0) / 1.5)
        for k in range(n + 1):
            x = x0 + (x1 - x0) * k / n
            corners = [(x, half, half), (x, half, -half), (x, -half, -half), (x, -half, half)]
            for i in range(4):
                cylinder_between(truss, corners[i], corners[(i + 1) % 4], 0.045, 5)
            if k < n:
                x2 = x0 + (x1 - x0) * (k + 1) / n
                cylinder_between(truss, (x, half, half), (x2, -half, -half), 0.035, 5)
                cylinder_between(truss, (x, -half, half), (x2, half, -half), 0.035, 5)
        # collars where the truss leaves the ring and meets the tank
        for xc in (side * (RING_R + RING_TUBE + 0.25), side * (RING_R - RING_TUBE - 0.25), side * (TANK_AT + TANK_LEN / 2 + 0.3)):
            box_at(gold, (xc, 0, 0), (0.3, 1.1, 1.1))
        # panels: two rows of three, in the ring plane, mounted a little above the truss
        for i in range(4):
            xc = side * (RING_R + RING_TUBE + 1.9 + i * 3.35)
            for row in (1, -1):
                zc = row * 2.15
                box_at(solar, (xc, 0.46, zc), (3.1, 0.06, 3.9))
                for sx in (1, -1):
                    box_at(hull, (xc + sx * 1.6, 0.46, zc), (0.1, 0.14, 4.1))
                for sz in (1, -1):
                    box_at(hull, (xc, 0.46, zc + sz * 2.0), (3.3, 0.14, 0.1))
                box_at(hull, (xc, 0.46, zc), (3.2, 0.1, 0.06))
                box_at(hull, (xc, 0.46, zc), (0.06, 0.1, 4.0))
                box_at(truss, (xc, 0.42, row * 0.7), (0.25, 0.3, 0.3))
        tip = Vector((x1 + side * 0.3, 0, 0))
        pw.add_ico(beacons["beacon_red" if side > 0 else "beacon_green"], tip, 0.14, 2)

    for bm in (hull, gold, truss, solar, glass, windows, *beacons.values()):
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    for bm in (hull, gold):  # the steps between collars and sunk skins, and the caps, stay crisp under smooth shading
        for e in bm.edges:
            if len(e.link_faces) == 2 and e.calc_face_angle(0.0) > math.radians(35):
                e.smooth = False
    obj("station_hull", hull, "hull", body, smooth=True)
    obj("station_gold", gold, "gold", body, smooth=True)
    obj("station_truss", truss, "truss", body)
    obj("station_solar", solar, "solar", body)
    obj("station_glass", glass, "glass", body, smooth=True)
    obj("station_windows", windows, "window_light", body)
    for name, bm in beacons.items():
        obj(f"station_{name}", bm, name, body, smooth=True)


def build_shuttle():
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


build_station()
if os.path.exists(SHUTTLE_GLB):
    place_generated(SHUTTLE_GLB, shuttle, "shuttle_generated", SHUTTLE_SCALE, SHUTTLE_YAW, SHUTTLE_ROLL)
else:
    build_shuttle()
dock = pw.empty("dock", DOCK)
dock.parent = station

# --- a navigation buoy: the scene clones it at every waypoint of the route in place of the rings --
# an octagonal body a metre tall, a mast with a red strobe, two small solar wings and a white lamp
buoy = pw.empty("buoy", (0, 0, 0))


def build_buoy():
    bm = bmesh.new()
    pw.add_cone(bm, (0, 0, -0.5), 0.42, 0.42, 1.0, segments=8)
    pw.add_cone(bm, (0, 0, 0.5), 0.42, 0.18, 0.22, segments=8)
    pw.add_cone(bm, (0, 0, -0.72), 0.18, 0.42, 0.22, segments=8)
    obj("buoy_body", bm, "buoy_body", buoy)
    bm = bmesh.new()
    cylinder_between(bm, (0, 0, 0.7), (0, 0, 1.45), 0.05, 6)
    cylinder_between(bm, (0, 0, 1.45), (0, 0, 1.52), 0.1, 8)
    obj("buoy_mast", bm, "truss", buoy)
    bm = bmesh.new()
    pw.add_ico(bm, (0, 0, 1.64), 0.14, 2)
    obj("buoy_strobe", bm, "beacon_red", buoy, smooth=True)
    bm = bmesh.new()
    for sx in (1, -1):
        pw.add_box(bm, (sx * 1.25, 0, 0), (1.4, 0.72, 0.04))
    obj("buoy_panels", bm, "solar", buoy)
    bm = bmesh.new()
    for sx in (1, -1):
        cylinder_between(bm, (sx * 0.4, 0, 0), (sx * 0.58, 0, 0), 0.035, 6)
    for k in range(4):
        a = k * math.pi / 2 + math.pi / 4
        pw.add_box(bm, (math.cos(a) * 0.4, math.sin(a) * 0.4, 0.08), (0.08, 0.08, 0.3))
    obj("buoy_arms", bm, "truss", buoy)
    bm = bmesh.new()
    pw.add_ico(bm, (0, 0, -0.84), 0.07, 2)
    obj("buoy_lamp", bm, "dock_light", buoy, smooth=True)


if os.path.exists(BUOY_GLB):
    # the generated buoy, 1.6 m tall with its origin at its centre; the strobe stays a mesh of its
    # own on the mast's tip so the scene can drive its flashing
    place_generated(BUOY_GLB, buoy, "buoy_generated", 1.0, 0.0, 0.0)
    bm = bmesh.new()
    pw.add_ico(bm, (0, 0, BUOY_STROBE_Z), 0.11, 2)
    obj("buoy_strobe", bm, "beacon_red", buoy, smooth=True)
else:
    build_buoy()

pw.export_glb(args.out)
