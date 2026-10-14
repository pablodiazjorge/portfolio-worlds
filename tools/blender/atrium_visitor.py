"""The visitor of the ATRIUM gallery: a cheerful cousin of the statue, the same blocky robot with a
monitor for a head, built from bevelled blocks of pale stone with brass joints, rigged on a simple
skeleton and animated by code: Idle, Walking, Running, Wave and ThumbsUp.

    blender --background --python tools/blender/atrium_visitor.py -- --out <path.glb> [--preview <dir>]
"""

import math
import os
import sys

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lib"))
import pw  # noqa: E402

args = pw.parse_args()
OUT = args.out
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
PREVIEW = argv[argv.index("--preview") + 1] if "--preview" in argv else None
pw.reset(7)

FPS = 24
scene = bpy.context.scene
scene.render.fps = FPS

# --- materials ----------------------------------------------------------------------------------
M = {
    "visitor_stone": pw.material("visitor_stone", "#ece7dc", roughness=0.62),
    "visitor_dark": pw.material("visitor_dark", "#2d2b30", roughness=0.7),
    "visitor_brass": pw.material("visitor_brass", "#c9a24a", roughness=0.38, metallic=0.85),
    "visitor_screen": pw.material("visitor_screen", "#13201c", roughness=0.3, emission="#5de08a", emission_strength=0.6),
}
ORDER = ["visitor_stone", "visitor_dark", "visitor_brass", "visitor_screen"]

# --- the body, one mesh, one vertex group per bone ----------------------------------------------
bm = bmesh.new()
uv_layer = bm.loops.layers.uv.new("UVMap")
groups = {}  # bone name -> list of BMVert


def part(bone, center, size, mat="visitor_stone"):
    vs = pw.add_box(bm, center, size)
    pw.assign_material_index(bm, vs, ORDER.index(mat))
    groups.setdefault(bone, []).extend(vs)
    return vs


def screen(bone, center, width, height):
    """The face of the monitor: a quad with UVs, facing -y."""
    hw, hh = width / 2, height / 2
    cx, cy, cz = center
    corners = [(cx - hw, cy, cz - hh), (cx + hw, cy, cz - hh), (cx + hw, cy, cz + hh), (cx - hw, cy, cz + hh)]
    vs = [bm.verts.new(c) for c in corners]
    face = bm.faces.new(vs)
    face.normal_update()
    if face.normal.y > 0:
        bmesh.ops.reverse_faces(bm, faces=[face])
    uvs = [(1, 0), (0, 0), (0, 1), (1, 1)]
    for loop in face.loops:
        k = vs.index(loop.vert)
        loop[uv_layer].uv = uvs[k]
    pw.assign_material_index(bm, vs, ORDER.index("visitor_screen"))
    groups.setdefault(bone, []).extend(vs)
    return vs


# the figure stands 1.65 m tall, feet at z = 0, facing -y
for sx, side in ((-1, "R"), (1, "L")):
    x = sx * 0.13
    part(f"foot.{side}", (x, -0.03, 0.04), (0.16, 0.26, 0.08))
    part(f"shin.{side}", (x, 0.0, 0.26), (0.12, 0.13, 0.34))
    part(f"shin.{side}", (x, -0.02, 0.44), (0.14, 0.15, 0.08), "visitor_dark")  # the knee
    part(f"thigh.{side}", (x, 0.0, 0.62), (0.15, 0.16, 0.34))
    part(f"shoulder.{side}", (sx * 0.30, 0.0, 1.28), (0.14, 0.2, 0.16))
    part(f"upper_arm.{side}", (sx * 0.30, 0.0, 1.08), (0.11, 0.11, 0.3))
    part(f"upper_arm.{side}", (sx * 0.30, 0.0, 0.935), (0.09, 0.09, 0.05), "visitor_brass")  # the elbow
    part(f"forearm.{side}", (sx * 0.30, 0.0, 0.78), (0.1, 0.1, 0.28))
    part(f"hand.{side}", (sx * 0.30, 0.0, 0.56), (0.12, 0.09, 0.12))
part("hips", (0, 0, 0.87), (0.40, 0.22, 0.14))
part("spine", (0, 0, 0.99), (0.30, 0.18, 0.1), "visitor_dark")
part("chest", (0, 0, 1.19), (0.46, 0.26, 0.30))
part("chest", (0, -0.145, 1.2), (0.30, 0.03, 0.2), "visitor_brass")  # the chest plate
part("neck", (0, 0, 1.37), (0.1, 0.1, 0.06), "visitor_dark")
part("head", (0, 0, 1.52), (0.40, 0.34, 0.30))
part("head", (0, -0.175, 1.52), (0.34, 0.02, 0.24), "visitor_dark")  # the bezel
screen("head", (0, -0.1865, 1.52), 0.30, 0.20)
part("head", (0.17, 0.08, 1.69), (0.03, 0.03, 0.08), "visitor_brass")  # an aerial
part("head", (0.17, 0.08, 1.74), (0.05, 0.05, 0.03), "visitor_brass")

bm.verts.index_update()
index_groups = {bone: sorted({v.index for v in vs}) for bone, vs in groups.items()}
body = pw.bm_object("visitor", bm, [M[k] for k in ORDER])
for bone, indices in index_groups.items():
    body.vertex_groups.new(name=bone).add(indices, 1.0, "REPLACE")
bevel = body.modifiers.new("bevel", "BEVEL")
bevel.width = 0.012
bevel.segments = 1
bevel.limit_method = "ANGLE"
bevel.angle_limit = math.radians(40)

# --- the skeleton ---------------------------------------------------------------------------------
arm_data = bpy.data.armatures.new("visitor_rig")
rig = bpy.data.objects.new("visitor_rig", arm_data)
pw.link(rig)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="EDIT")
BONES = [
    ("hips", (0, 0, 0.80), (0, 0, 0.94), None),
    ("spine", (0, 0, 0.94), (0, 0, 1.10), "hips"),
    ("chest", (0, 0, 1.10), (0, 0, 1.34), "spine"),
    ("neck", (0, 0, 1.34), (0, 0, 1.40), "chest"),
    ("head", (0, 0, 1.40), (0, 0, 1.67), "neck"),
]
for sx, side in ((-1, "R"), (1, "L")):
    BONES += [
        (f"shoulder.{side}", (sx * 0.18, 0, 1.28), (sx * 0.30, 0, 1.28), "chest"),
        (f"upper_arm.{side}", (sx * 0.30, 0, 1.26), (sx * 0.30, 0, 0.94), f"shoulder.{side}"),
        (f"forearm.{side}", (sx * 0.30, 0, 0.94), (sx * 0.30, 0, 0.64), f"upper_arm.{side}"),
        (f"hand.{side}", (sx * 0.30, 0, 0.64), (sx * 0.30, 0, 0.50), f"forearm.{side}"),
        (f"thigh.{side}", (sx * 0.13, 0, 0.80), (sx * 0.13, 0, 0.44), "hips"),
        (f"shin.{side}", (sx * 0.13, 0, 0.44), (sx * 0.13, 0, 0.09), f"thigh.{side}"),
        (f"foot.{side}", (sx * 0.13, 0, 0.09), (sx * 0.13, -0.14, 0.0), f"shin.{side}"),
    ]
for name, head, tail, parent in BONES:
    b = arm_data.edit_bones.new(name)
    b.head, b.tail = Vector(head), Vector(tail)
    b.roll = 0.0
    if parent:
        b.parent = arm_data.edit_bones[parent]
        b.use_connect = False
bpy.ops.object.mode_set(mode="OBJECT")
body.parent = rig
body.modifiers.new("armature", "ARMATURE").object = rig

# --- animation by code: poses are rotations about world axes, turned into each bone's own frame --
rest = {b.name: b.matrix_local.to_3x3() for b in arm_data.bones}
for pb in rig.pose.bones:
    pb.rotation_mode = "XYZ"


def pose(action, frame, bone, rx=0.0, ry=0.0, rz=0.0, loc=None):
    """rx nods forward (+ = forward), ry rolls about the depth axis, rz turns about the vertical."""
    pb = rig.pose.bones[bone]
    world = Euler((-rx, ry, rz), "XYZ").to_matrix()  # +rx leans the top of an upright bone to -y
    local = rest[bone].inverted() @ world @ rest[bone]
    pb.rotation_euler = local.to_euler("XYZ")
    pb.keyframe_insert("rotation_euler", frame=frame)
    if loc is not None:
        pb.location = Vector(loc)
        pb.keyframe_insert("location", frame=frame)


def clip(name, frames, fn, loop=True):
    action = bpy.data.actions.new(name)
    rig.animation_data_create()
    rig.animation_data.action = action
    for f in range(frames + (1 if loop else 0)):
        t = f / frames
        fn(f, t if loop else f / max(1, frames))
    for fc in action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "BEZIER"
    rig.animation_data.action = None
    track = rig.animation_data.nla_tracks.new()
    track.name = name
    track.strips.new(name, 0, action)
    return action


def swing(f, t, legs, knee, arms, elbow, bob, lean=0.0, sway=0.0):
    p = math.tau * t
    s = math.sin(p)
    for side, sign in (("L", 1), ("R", -1)):
        pose_leg = legs * s * sign
        pose(None, f, f"thigh.{side}", rx=pose_leg)
        # the knee bends while the leg swings back and straightens as it reaches forward
        pose(None, f, f"shin.{side}", rx=-knee * max(0.0, -s * sign) - 0.05)
        pose(None, f, f"foot.{side}", rx=0.15 * s * sign)
        pose(None, f, f"upper_arm.{side}", rx=-arms * s * sign)
        pose(None, f, f"forearm.{side}", rx=elbow)
    pose(None, f, "hips", rx=lean * 0.3, ry=sway * s, loc=(0, 0, -bob * (1 - math.cos(2 * p)) / 2))
    pose(None, f, "chest", rx=lean, rz=-0.08 * s)
    pose(None, f, "head", rx=-lean * 0.6, rz=0.05 * s)


clip("Walking", FPS, lambda f, t: swing(f, t, legs=0.55, knee=0.6, arms=0.45, elbow=0.35, bob=0.02, sway=0.03))
clip("Running", 14, lambda f, t: swing(f, t, legs=0.95, knee=1.1, arms=0.8, elbow=1.0, bob=0.045, lean=0.28, sway=0.05))


def idle(f, t):
    p = math.tau * t
    breath = math.sin(p)
    pose(None, f, "hips", loc=(0, 0, 0.006 * breath))
    pose(None, f, "chest", rx=0.025 * breath)
    pose(None, f, "head", ry=0.07 * math.sin(p + 1.1), rz=0.06 * math.sin(p * 0.5))
    for side, sign in (("L", 1), ("R", -1)):
        pose(None, f, f"upper_arm.{side}", rx=0.04 * breath, ry=sign * 0.04)
        pose(None, f, f"forearm.{side}", rx=0.12 + 0.03 * breath)
        pose(None, f, f"thigh.{side}", rx=0.0)
        pose(None, f, f"shin.{side}", rx=-0.03)


clip("Idle", FPS * 3, idle)


def wave(f, t):
    # the right arm goes up and the forearm waves three times
    up = min(1.0, t * 4) if t < 0.8 else max(0.0, (1 - t) * 5)
    pose(None, f, "upper_arm.R", ry=-2.4 * up, rx=0.2 * up)
    pose(None, f, "forearm.R", ry=-0.5 * up + 0.45 * up * math.sin(math.tau * 3 * t), rx=0.1)
    pose(None, f, "hand.R", ry=0.3 * up * math.sin(math.tau * 3 * t))
    pose(None, f, "head", rz=0.15 * up, ry=0.08 * up)
    pose(None, f, "chest", rz=0.1 * up)


clip("Wave", int(FPS * 1.6), wave, loop=False)


def thumbs(f, t):
    up = min(1.0, t * 3) if t < 0.75 else max(0.0, (1 - t) * 4)
    pose(None, f, "upper_arm.R", rx=1.1 * up)
    pose(None, f, "forearm.R", rx=1.5 * up)
    pose(None, f, "hand.R", rz=0.4 * up)
    pose(None, f, "head", rx=0.12 * up * math.sin(math.tau * 2 * t) ** 2)


clip("ThumbsUp", int(FPS * 1.2), thumbs, loop=False)

# --- export and previews ----------------------------------------------------------------------------
bpy.ops.object.select_all(action="DESELECT")
pw.export_glb(OUT, animations=True)
print(f"[visitor] {len(body.data.polygons)} faces, {len(arm_data.bones)} bones, {len(bpy.data.actions)} actions")

if PREVIEW:
    os.makedirs(PREVIEW, exist_ok=True)
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.render.resolution_x = scene.render.resolution_y = 640
    scene.render.image_settings.file_format = "JPEG"
    scene.view_settings.view_transform = "Standard"
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.lens = 60
    pw.link(cam)
    scene.camera = cam
    for strip_name, frame in (("Idle", 10), ("Walking", 6), ("Running", 4), ("Wave", 20)):
        for track in rig.animation_data.nla_tracks:
            track.mute = track.name != strip_name
        scene.frame_set(frame)
        for yaw, tag in ((20, "front"), (110, "side")):
            a = math.radians(yaw)
            cam.location = Vector((math.sin(a) * 3.6, -math.cos(a) * 3.6, 1.4))
            cam.rotation_euler = (Vector((0, 0, 0.85)) - cam.location).to_track_quat("-Z", "Y").to_euler()
            scene.render.filepath = os.path.join(PREVIEW, f"visitor-{strip_name.lower()}-{tag}.jpg")
            bpy.ops.render.render(write_still=True)
    print("[visitor] previews written")
