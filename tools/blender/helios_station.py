"""HELIOS: an orbital station with a rotating habitat ring, plus the shuttle that flies to it.

Blender axes: the station's long axis runs along X; the shuttle points along +X.
Top-level empties: station, shuttle, buoy (a template the scene clones at the waypoints). Animated pivots: ring_pivot (spins around X).
Materials the app replaces: hull, truss, solar, radiator, glass, gold, engine_glow,
beacon_red, beacon_green, dock_light, window_light.
"""

import math
import os
import sys

import bmesh
import bpy
import numpy as np
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
}

station = pw.empty("station", (0, 0, 0))
shuttle = pw.empty("shuttle", (0, 0, 0))

# the station and the shuttle generated with Qwen-Image and TRELLIS.2 (tools/assets/trellis, prepared
# by statue_prepare.py) replace the drawn ones when their files exist; each is imported under its
# empty, scaled to the size the scene expects (the drawn station spans 32 m, the shuttle 3 m)
ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "trellis")
STATION_GLB = os.path.join(ASSETS, "helios_station3.glb")
SHUTTLE_GLB = os.path.join(ASSETS, "helios_shuttle.glb")
BUOY_GLB = os.path.join(ASSETS, "helios_buoy.glb")
BUOY_STROBE_Z = 0.52  # the centre of the generated buoy's red lamp, measured on the prepared mesh (its top at 0.61 m)
# the prepared station has its hub axis upright; tipped by +90 degrees about X its docking end
# (the collar on the hub's dome, the raw model's top) points to -y, the glTF +z the shuttle
# approaches along; the prepared shuttle already points its nose to +x, as the drawn one did, so
# the scene's quarter turn fits
STATION_SCALE, STATION_YAW, STATION_ROLL = 1.0, 0.0, math.pi / 2
SHUTTLE_SCALE, SHUTTLE_YAW, SHUTTLE_ROLL = 1.0, 0.0, 0.0
STATION_SHIFT = (-0.10, 0.0, 0.0)  # the prepared station's hub axis, brought onto the origin
DOCK = (0.0, -4.6, 0.0)  # where the shuttle's centre sits when docked at the hub's collar, on its axis (Blender axes: -y is the glTF +z)


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



def strip_where(name, keep_out):
    """Deletes the vertices of the generated mesh `name` for which `keep_out(co)` is true (its own frame,
    before the roll), with the faces they carry: used to take away pieces the script draws again."""
    o = bpy.data.objects[name]
    bm = bmesh.new()
    bm.from_mesh(o.data)
    doomed = [v for v in bm.verts if keep_out(v.co)]
    bmesh.ops.delete(bm, geom=doomed, context="VERTS")
    bm.to_mesh(o.data)
    bm.free()
    return len(doomed)


def strip_islands(name, zone, judge, log=None):
    """Deletes every connected piece of the generated mesh `name` that has a vertex inside `zone` and for
    which `judge(points, mean_rgb)` is true, given the piece's vertex positions and its mean baked colour
    (sampled at its faces' centres): the leftovers of a cut that climb onto a neighbour (the old arrays'
    ends over the ring, their masts' sockets and rods). `log` collects a line per piece removed. Size,
    thinness or colour alone do not tell debris from skin here (the skin is cut into thousands of small
    patches, and its section is not uniform enough for a distance test), so each rule pins a piece down
    by colour, size and the pocket it lies in together."""
    import numpy as np
    o = bpy.data.objects[name]
    bsdf = next(n for n in o.active_material.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    img = bsdf.inputs["Base Color"].links[0].from_node.image
    w, h = img.size
    px = np.empty(w * h * img.channels, np.float32)
    img.pixels.foreach_get(px)
    tex = px.reshape(h, w, img.channels)[:, :, :3] * 255  # row 0 at the bottom, as Blender stores it
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bm.verts.ensure_lookup_table()
    uv = bm.loops.layers.uv.active
    seen, doomed, pieces = set(), [], 0
    for seed in bm.verts:
        if seed.index in seen or not zone(seed.co):
            continue
        island, stack = [], [seed]
        seen.add(seed.index)
        while stack:
            v = stack.pop()
            island.append(v)
            for e in v.link_edges:
                other = e.other_vert(v)
                if other.index not in seen:
                    seen.add(other.index)
                    stack.append(other)
        faces = {f for v in island for f in v.link_faces}
        samples = []
        for f in faces:
            u = sum(l[uv].uv.x for l in f.loops) / len(f.loops)
            vv = sum(l[uv].uv.y for l in f.loops) / len(f.loops)
            samples.append(tex[min(h - 1, max(0, int(vv * h))), min(w - 1, max(0, int(u * w)))])
        if not samples:
            continue
        mean = np.mean(np.array(samples), axis=0)
        pts = np.array([v.co[:] for v in island])
        if judge(pts, mean):
            doomed.extend(island)
            pieces += 1
            if log is not None:
                ext = pts.max(axis=0) - pts.min(axis=0)
                log.append(f"{len(pts)} verts, extent {ext[0]:.2f} x {ext[1]:.2f} x {ext[2]:.2f}, luma {mean.mean():.0f}, at r {np.hypot(pts[:, 0], pts[:, 1]).mean():.1f}")
    bmesh.ops.delete(bm, geom=doomed, context="VERTS")
    bm.to_mesh(o.data)
    bm.free()
    return pieces, len(doomed)


def symmetric_arrays(y_plane, z0, z1, half_width):
    """Two identical solar arrays on the station's z axis (the placed frame: the hub axis is y, the
    approach is -y), each a flat panel with a white rim on a mast that runs from the hub to the ring."""
    bm_panel, bm_rim, bm_mast = bmesh.new(), bmesh.new(), bmesh.new()
    length = z1 - z0
    for side in (1, -1):
        zc = side * (z0 + length / 2)
        pw.add_box(bm_panel, (0, y_plane, zc), (half_width * 2, 0.08, length))
        for sx in (1, -1):
            pw.add_box(bm_rim, (sx * (half_width + 0.05), y_plane, zc), (0.1, 0.16, length + 0.2))
        for sz in (1, -1):
            pw.add_box(bm_rim, (0, y_plane, zc + sz * (length / 2 + 0.05)), (half_width * 2 + 0.2, 0.16, 0.1))
        # the ring's inner wall is recessed on this axis (11.5 m from the hub at this height, measured on
        # the mesh): the mast runs on into the tube, where the overshoot is hidden
        cylinder_between(bm_mast, (0, y_plane + 0.18, side * 2.2), (0, y_plane + 0.18, side * 12.3), 0.13, 12)
        # a foot where the mast meets the wall: a plate against it and a collar on the mast, which
        # also cover the mount the old mast grew out of
        pw.add_box(bm_rim, (0, y_plane + 0.18, side * 11.3), (1.4, 1.4, 0.3))
        cylinder_between(bm_mast, (0, y_plane + 0.18, side * 10.5), (0, y_plane + 0.18, side * 11.2), 0.3, 16)
        for k in (0.15, 0.5, 0.85):
            pw.add_box(bm_rim, (0, y_plane + 0.12, side * (z0 + length * k)), (0.5, 0.16, 0.3))
        # dividers between the cells, two columns by four rows, proud of the cells by a centimetre
        pw.add_box(bm_rim, (0, y_plane, zc), (0.06, 0.1, length))
        for k in (0.25, 0.5, 0.75):
            pw.add_box(bm_rim, (0, y_plane, side * (z0 + length * k)), (half_width * 2, 0.1, 0.06))
    obj("station_arrays", bm_panel, "solar", station)
    obj("station_array_rims", bm_rim, "hull", station)
    obj("station_array_masts", bm_mast, "truss", station)


def dock_hatch(centre, depth, radius):
    """A closed hatch set a little inside the docking port: a plain disc with a raised ring and a boss,
    facing the approach (-y of the placed frame)."""
    bm = bmesh.new()
    cx, cy, cz = centre
    for r, d, h in ((radius, depth, 0.12), (radius * 0.62, depth - 0.03, 0.06), (radius * 0.22, depth - 0.07, 0.08)):
        verts = pw.add_cone(bm, (0, 0, 0), r, r, h, segments=48)
        bmesh.ops.rotate(bm, verts=verts, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, "X"))
        bmesh.ops.translate(bm, verts=verts, vec=Vector((cx, cy + d, cz)))
    obj("dock_hatch", bm, "hull", station, smooth=True)


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



def build_station():
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



if os.path.exists(STATION_GLB):
    # the hub's axis sits 0.1 m off the prepared mesh's origin (the dome's port is 0.2 m off, the
    # hub core and the collar on it, so the mesh is shifted half-way): the mesh is shifted so the wheel turns about its hub and the port stays
    # put under its lights; the plain-hull station keeps everything TRELLIS made (ring, two long
    # modules crossing it with ports at their ends, two arrays, hub with its domed collar)
    place_generated(STATION_GLB, station, "station_generated", STATION_SCALE, STATION_YAW, STATION_ROLL, shift=STATION_SHIFT)
    # the two arrays TRELLIS made differ in size and sit askew: they go (everything in the sector
    # about the model's y axis between the hub and the ring, below the ring's mid-plane, short of the
    # ring's inner face at 10 m) and two identical ones are drawn on the same axis, with a mast each
    # from the hub to the ring
    n1 = strip_where("station_generated", lambda c: abs(c.x) < 4.5 and abs(c.y) > 3.2 and math.hypot(c.x, c.y) < 9.85 and -3.0 < c.z < -0.1)
    # (their roots on the hub, between 2.2 and 3.3 m from the centre, share that space with the root
    # collars of the two modules, which a box cut tears; they go piece by piece below)
    # the ends of the old arrays reached the ring's inner face and bend over it, past that cut: every
    # piece touching the strip along the ring there whose bake is solar blue goes too (the ring's own
    # patches are light grey and stay), and so do the thin rods of the old masts with their knobs
    log = []
    ext = lambda pts: pts.max(axis=0) - pts.min(axis=0)
    zone = lambda c: abs(c.x) < 4.6 and 9.0 < abs(c.y) < 10.9 and -3.3 < c.z < 0.5
    n2 = strip_islands("station_generated", zone, lambda pts, rgb: rgb[2] > rgb[0] + 30 and rgb.mean() < 110, log)
    # the dark metal sockets of the old masts on the ring's inner face, the size of a hand: small in
    # every axis, dark and wholly inside their pocket (the skin there is light; without the colour test
    # the rule took light slivers of skin and pricked the wall with pinholes). The light mount plate
    # the old mast grew out of stays on the wall: the new mast runs into it
    pocket = lambda c: abs(c.x) < 2.5 and 9.5 < abs(c.y) < 12.0 and -3.3 < c.z < 0.3
    n3 = strip_islands("station_generated", pocket, lambda pts, rgb: len(pts) < 400 and rgb.mean() < 120
                       and all(pocket(Vector(q)) for q in pts)
                       and (max(ext(pts)) < 2.0 or (max(ext(pts)) < 2.6 and sorted(ext(pts))[1] < 0.3)), log)
    # (a rule for the scraps of the joints by size and shape alone opened a hole of two metres in the
    # wall next to the mount, seen from inside the ring: nothing of that kind is applied)
    # (the black flat strips at the height of the inner equator are the wall's own skin, painted black
    # by the bake, so nothing takes them: the wall sits 10 to 12 m from the axis depending on the angle)
    # the end plate and the frame bar of the old arrays standing against the inner wall: thin along y,
    # metres long along x, darker than the paint
    plate = lambda c: abs(c.x) < 2.5 and 10.8 < abs(c.y) < 11.8 and -2.8 < c.z < 0.0
    n3d = strip_islands("station_generated", plate, lambda pts, rgb: len(pts) < 200 and rgb.mean() < 120
                        and ext(pts)[1] < 0.3 and ext(pts)[0] > 3.0 and np.all(np.abs(pts[:, 1]) > 10.5), log)
    # the dark rods standing on the ring's outer edge on the same axis (knobs seen from above): thin,
    # one to three metres long, dark, and nowhere near the skin's light colour
    edge = lambda c: abs(c.x) < 1.5 and abs(c.y) > 15.0 and -3.5 < c.z < 1.8
    n4 = strip_islands("station_generated", edge, lambda pts, rgb: len(pts) < 200 and rgb.mean() < 110
                       and sorted(ext(pts))[1] < 1.0 and 1.0 < max(ext(pts)) < 3.0
                       and np.all(np.abs(pts[:, 0]) < 2.0) and np.all(np.hypot(pts[:, 0], pts[:, 1]) > 14.5), log)
    # the roots of the old arrays by the hub (the yoke that joined them to it, their rim bars and the
    # serrated strip of panel the sector cut leaves): bars and plates a metre or more along x, narrow
    # in y and z, in the band from 2.2 to 3.4 m from the centre; the modules' root collars there are
    # made of short curved patches and the hub's skin ends at 2.1 m on this axis
    root = lambda c: abs(c.x) < 2.3 and 2.2 < abs(c.y) < 3.4 and -3.0 < c.z < -0.1
    n5 = strip_islands("station_generated", root, lambda pts, rgb: len(pts) < 400 and ext(pts)[0] > 1.0
                       and ext(pts)[1] < 0.6 and ext(pts)[2] < 0.4 and np.all(np.abs(pts[:, 1]) > 2.15), log)
    # the knobs on the ring's outer edge on the array axis, the size of a fist, with their chips: small,
    # darker than the skin, wholly in their spot (the skin's slivers there are tiny and light)
    knob = lambda c: abs(c.x) < 0.6 and 15.5 < abs(c.y) < 16.3 and -0.7 < c.z < -0.1
    n6 = strip_islands("station_generated", knob, lambda pts, rgb: len(pts) < 80 and rgb.mean() < 125 and max(ext(pts)) < 0.7
                       and np.all(np.abs(pts[:, 0]) < 0.6) and np.all(np.abs(pts[:, 1]) > 15.5), log)
    # the vertical rods standing by the hub, half a metre to a metre off its skin (which ends 2.1 m from
    # the centre): thin, one to two and a half metres tall; four beside the modules' collars inside
    # |y| 2 (the modules' own skin lies beyond 2.07 there) and the rest on the arrays' axis within |x| 1.3
    rods = lambda c: 2.4 < math.hypot(c.x, c.y) < 3.5 and abs(c.x) < 3.0 and -2.0 < c.z < 1.0
    n7 = strip_islands("station_generated", rods, lambda pts, rgb: len(pts) < 150 and sorted(ext(pts))[1] < 0.5
                       and 1.2 < ext(pts)[2] < 2.6 and np.all(np.hypot(pts[:, 0], pts[:, 1]) > 2.35)
                       and ((np.all(np.abs(pts[:, 1]) < 2.0) and np.all(np.abs(pts[:, 0]) < 2.6))
                            or (np.all(np.abs(pts[:, 0]) < 1.3) and np.all(np.abs(pts[:, 1]) > 2.3))), log)
    print(f"  [pw] old arrays stripped: {n1} vertices in the sector, then {n2[0]} blue pieces, {n3[0]} sockets, {n3d[0]} plates, {n4[0]} edge rods, {n5[0]} root bars by the hub, {n6[0]} edge knobs and {n7[0]} rods by the hub:")
    for line in log:
        print("  [pw]   " + line)
    symmetric_arrays(1.5, 3.8, 9.4, 1.75)
    # a hatch closes the port on the hub's dome (the port is 0.1 m off the axis after the shift)
    dock_hatch((0.1, -2.89, 0.0), 0.35, 0.86)
else:
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
