"""The visitor of the ATRIUM gallery: a cheerful cousin of the statue, the same blocky robot with a
monitor for a head, built from bevelled blocks of pale stone with brass joints, a navy chest plate
wearing its prize badge, rigged on a simple skeleton and animated by code: Idle, Walking, Running,
Wave and ThumbsUp. The gaits follow the contact method of a walk cycle: the knee flexes mid-swing
and is straight through the stance, the hips dip on each contact and rise at the passing position,
the pelvis and the chest counter-rotate and the arms swing against the legs; stride and cycle time
are set so the feet do not slide at the walking and running speeds of the controller.

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
    "visitor_plate": pw.material("visitor_plate", "#2f4466", roughness=0.45),
    "visitor_badge": pw.material("visitor_badge", "#d9b24a", roughness=0.5),
}
ORDER = ["visitor_stone", "visitor_dark", "visitor_brass", "visitor_screen", "visitor_plate", "visitor_badge"]

# --- the body, one mesh, one vertex group per bone ----------------------------------------------
bm = bmesh.new()
uv_layer = bm.loops.layers.uv.new("UVMap")
groups = {}  # bone name -> list of BMVert


def part(bone, center, size, mat="visitor_stone"):
    vs = pw.add_box(bm, center, size)
    pw.assign_material_index(bm, vs, ORDER.index(mat))
    groups.setdefault(bone, []).extend(vs)
    return vs


def front_quad(bone, center, width, height, mat):
    """A quad with UVs facing -y, for a painted surface such as the screen or the badge."""
    hw, hh = width / 2, height / 2
    cx, cy, cz = center
    corners = [(cx - hw, cy, cz - hh), (cx + hw, cy, cz - hh), (cx + hw, cy, cz + hh), (cx - hw, cy, cz + hh)]
    vs = [bm.verts.new(c) for c in corners]
    face = bm.faces.new(vs)
    face.normal_update()
    if face.normal.y > 0:
        bmesh.ops.reverse_faces(bm, faces=[face])
    uvs = [(0, 0), (1, 0), (1, 1), (0, 1)]  # with the export to y-up this order reads the right way round from the front
    for loop in face.loops:
        k = vs.index(loop.vert)
        loop[uv_layer].uv = uvs[k]
    pw.assign_material_index(bm, vs, ORDER.index(mat))
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
part("chest", (0, -0.145, 1.2), (0.30, 0.03, 0.2), "visitor_plate")  # the chest plate, navy
front_quad("chest", (0.075, -0.1615, 1.225), 0.11, 0.125, "visitor_badge")  # the prize badge, painted at runtime
part("neck", (0, 0, 1.37), (0.1, 0.1, 0.06), "visitor_dark")
part("head", (0, 0, 1.52), (0.40, 0.34, 0.30))
part("head", (0, -0.175, 1.52), (0.34, 0.02, 0.24), "visitor_dark")  # the bezel
front_quad("head", (0, -0.1865, 1.52), 0.30, 0.20, "visitor_screen")
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
points_up = {b.name: (b.tail_local.z - b.head_local.z) >= 0 for b in arm_data.bones}
for pb in rig.pose.bones:
    pb.rotation_mode = "XYZ"


def pose(frame, bone, fwd=0.0, roll=0.0, yaw=0.0, loc=None):
    """fwd swings the far end of the bone towards -y (the front): the top of an upright bone leans
    forward, the foot of a leg goes forward. roll turns about the depth axis, yaw about the vertical."""
    pb = rig.pose.bones[bone]
    angle_x = fwd if points_up[bone] else -fwd
    world = Euler((angle_x, roll, yaw), "XYZ").to_matrix()
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
        fn(f, f / frames)
    for fc in action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "BEZIER"
    rig.animation_data.action = None
    track = rig.animation_data.nla_tracks.new()
    track.name = name
    track.strips.new(name, 0, action)
    return action


def gait(f, t, legs, knee, arms, elbow0, elbow1, bob, lean, sway, twist):
    """One cycle of a gait. For the left leg the phase p runs so that sin p is its forward swing:
    contact (leg forward) at p = pi/2, passing under the body at p = pi, back at 3pi/2. The right
    leg runs half a cycle behind. The knee flexes while the leg swings forward (cos p > 0) and is
    straight through the stance; the hips are lowest at each contact and highest at passing."""
    p = math.tau * t
    for side, phase in (("L", p), ("R", p + math.pi)):
        s = math.sin(phase)
        c = math.cos(phase)
        swing = max(0.0, c) ** 1.4  # 1 at mid-swing, 0 through the stance
        pose(f, f"thigh.{side}", fwd=legs * s)
        pose(f, f"shin.{side}", fwd=-(knee * swing + 0.04))
        pose(f, f"foot.{side}", fwd=-0.45 * legs * s + 0.25 * swing)
        pose(f, f"upper_arm.{side}", fwd=-arms * s, roll=(0.06 if side == "L" else -0.06))
        pose(f, f"forearm.{side}", fwd=elbow0 + elbow1 * max(0.0, -s))
        pose(f, f"hand.{side}", fwd=0.1)
    down = (1 - math.cos(2 * p)) / 2  # 1 at the contacts, 0 at the passing positions
    pose(f, "hips", fwd=lean * 0.3, roll=sway * math.sin(p), yaw=twist * math.sin(p), loc=(0.012 * math.cos(p) if sway else 0.0, 0, -bob * down))
    pose(f, "spine", fwd=lean * 0.3)
    pose(f, "chest", fwd=lean * 0.4, yaw=-twist * 1.2 * math.sin(p))
    pose(f, "neck", fwd=-lean * 0.3)
    pose(f, "head", fwd=-lean * 0.5, yaw=twist * 0.4 * math.sin(p), roll=-0.4 * sway * math.sin(p))


# walking: 20 frames (0.83 s) with a 0.62 rad swing on 0.75 m legs gives 2 steps of 0.87 m per
# cycle, 2.1 m/s, the controller's walking speed; running: 14 frames and a 0.95 rad swing, 4.2 m/s
clip("Walking", 20, lambda f, t: gait(f, t, legs=0.62, knee=0.95, arms=0.42, elbow0=0.3, elbow1=0.35, bob=0.025, lean=0.04, sway=0.035, twist=0.07))
clip("Running", 14, lambda f, t: gait(f, t, legs=0.95, knee=1.45, arms=0.8, elbow0=0.9, elbow1=0.4, bob=0.05, lean=0.22, sway=0.03, twist=0.1))


def idle(f, t):
    p = math.tau * t
    breath = math.sin(p)
    pose(f, "hips", loc=(0, 0, 0.006 * breath))
    pose(f, "spine", fwd=0.01 * breath)
    pose(f, "chest", fwd=0.025 * breath)
    pose(f, "head", roll=0.06 * math.sin(p + 1.1), yaw=0.05 * math.sin(p * 0.5))
    for side, sign in (("L", 1), ("R", -1)):
        pose(f, f"upper_arm.{side}", fwd=0.04 * breath, roll=sign * 0.05)
        pose(f, f"forearm.{side}", fwd=0.14 + 0.03 * breath)
        pose(f, f"hand.{side}", fwd=0.08)
        pose(f, f"thigh.{side}", fwd=0.0)
        pose(f, f"shin.{side}", fwd=-0.04)
        pose(f, f"foot.{side}", fwd=0.0)


clip("Idle", FPS * 3, idle)


def wave(f, t):
    # the right arm goes up and out, and the forearm waves three times
    up = min(1.0, t * 4) if t < 0.8 else max(0.0, (1 - t) * 5)
    pose(f, "upper_arm.R", roll=2.5 * up, fwd=0.15 * up)
    pose(f, "forearm.R", roll=0.5 * up + 0.45 * up * math.sin(math.tau * 3 * t), fwd=0.1)
    pose(f, "hand.R", roll=0.3 * up * math.sin(math.tau * 3 * t))
    pose(f, "head", yaw=0.15 * up, roll=-0.08 * up)
    pose(f, "chest", yaw=0.1 * up)


clip("Wave", int(FPS * 1.6), wave, loop=False)


def thumbs(f, t):
    up = min(1.0, t * 3) if t < 0.75 else max(0.0, (1 - t) * 4)
    pose(f, "upper_arm.R", fwd=1.1 * up)
    pose(f, "forearm.R", fwd=1.5 * up)
    pose(f, "hand.R", yaw=0.4 * up)
    pose(f, "head", fwd=0.12 * up * math.sin(math.tau * 2 * t) ** 2)


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
    scene.render.resolution_x = scene.render.resolution_y = 512
    scene.render.image_settings.file_format = "JPEG"
    scene.view_settings.view_transform = "Standard"
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.lens = 60
    pw.link(cam)
    scene.camera = cam
    for track in rig.animation_data.nla_tracks:
        track.mute = True
    # one action at a time on the rig itself, so each frame shows that clip alone
    for name, frames in (("Walking", (0, 5, 10, 15)), ("Running", (0, 4, 7, 11)), ("Wave", (12, 24)), ("Idle", (36,))):
        rig.animation_data.action = bpy.data.actions[name]
        for frame in frames:
            scene.frame_set(frame)
            for yaw, tag in ((25, "front"), (90, "side")):
                a = math.radians(yaw)
                cam.location = Vector((math.sin(a) * 3.4, -math.cos(a) * 3.4, 1.2))
                cam.rotation_euler = (Vector((0, 0, 0.85)) - cam.location).to_track_quat("-Z", "Y").to_euler()
                scene.render.filepath = os.path.join(PREVIEW, f"visitor-{name.lower()}-{frame:02d}-{tag}.jpg")
                bpy.ops.render.render(write_still=True)
    rig.animation_data.action = None
    print("[visitor] previews written")
