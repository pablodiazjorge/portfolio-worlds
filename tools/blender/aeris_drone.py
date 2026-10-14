"""AERIS: a quadcopter built in five layers that the app pulls apart into an exploded view.

Hierarchy (empties keep their names in the GLB; meshes may be renamed by the optimizer):
  drone
    layer_top      canopy, stripe, gps, antennas
    layer_battery  battery pack and label
    layer_board    flight controller, chips, heatsink
    layer_frame    plate, arms, motors, skids, leds, spin_* pivots with props
    layer_camera   gimbal_pivot with yoke, camera body, lens
Materials are named so the app can swap in TSL materials: carbon, shell, accent, metal, pcb,
chip, battery, prop, glass, led_white, led_red, rubber.
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
    "carbon": pw.material("carbon", "#1c1d21", 0.4),
    "shell": pw.material("shell", "#2b2e34", 0.45),
    "accent": pw.material("accent", "#ff5a1f", 0.4),
    "metal": pw.material("metal", "#b8bcc4", 0.28, 1.0),
    "pcb": pw.material("pcb", "#0f3b33", 0.55),
    "chip": pw.material("chip", "#15161a", 0.5),
    "battery": pw.material("battery", "#3a3d44", 0.6),
    "prop": pw.material("prop", "#1c1f24", 0.35),
    "glass": pw.material("glass", "#05070a", 0.05),
    "led_white": pw.material("led_white", "#ffffff", 0.3, emission="#e8f4ff", emission_strength=6.0),
    "led_red": pw.material("led_red", "#ff3b30", 0.3, emission="#ff2a1f", emission_strength=6.0),
    "rubber": pw.material("rubber", "#111215", 0.9),
}

MOTORS = {"fl": (-1.0, 0.8), "fr": (1.0, 0.8), "bl": (-1.0, -0.8), "br": (1.0, -0.8)}


def empty(name, parent=None, location=(0, 0, 0)):
    obj = pw.empty(name, location)
    if parent:
        obj.parent = parent
    return obj


def part(name, bm, mat, parent, smooth=False):
    obj = pw.bm_object(name, bm, M[mat] if isinstance(mat, str) else [M[m] for m in mat], smooth=smooth)
    obj.parent = parent
    return obj


def bevel_all(bm, offset, segments=2):
    bmesh.ops.bevel(bm, geom=bm.edges[:], offset=offset, segments=segments, profile=0.5, affect="EDGES", clamp_overlap=True)


def rounded_box(size, center=(0, 0, 0), bevel=0.02, segments=2, rotation=0.0):
    bm = bmesh.new()
    pw.add_box(bm, center, size, rotation)
    bevel_all(bm, bevel, segments)
    return bm


root = empty("drone")
layer_top = empty("layer_top", root)
layer_battery = empty("layer_battery", root)
layer_board = empty("layer_board", root)
layer_frame = empty("layer_frame", root)
layer_camera = empty("layer_camera", root)

# --- frame -----------------------------------------------------------------------------
part("plate", rounded_box((0.92, 0.62, 0.04), (0, 0, 0.02), 0.015), "carbon", layer_frame)
for key, (mx, my) in MOTORS.items():
    angle = math.atan2(my, mx)
    length = math.hypot(mx, my)
    bm = rounded_box((length + 0.05, 0.12, 0.055), (0, 0, 0), 0.02, 2)
    bmesh.ops.translate(bm, verts=bm.verts[:], vec=Vector((length / 2, 0, 0.03)))
    bmesh.ops.rotate(bm, verts=bm.verts[:], cent=(0, 0, 0), matrix=Matrix.Rotation(angle, 3, "Z"))
    part(f"arm_{key}", bm, "carbon", layer_frame)

    # motor: stator base, bell and orange cap
    bm = bmesh.new()
    pw.add_cone(bm, (mx, my, 0.055), 0.12, 0.12, 0.05, segments=24)
    part(f"motor_base_{key}", bm, "metal", layer_frame, smooth=True)
    bm = bmesh.new()
    pw.add_cone(bm, (mx, my, 0.105), 0.145, 0.135, 0.11, segments=32)
    bevel_all(bm, 0.008, 1)
    part(f"motor_bell_{key}", bm, "metal", layer_frame, smooth=True)
    bm = bmesh.new()
    pw.add_cone(bm, (mx, my, 0.215), 0.09, 0.07, 0.025, segments=24)
    part(f"motor_cap_{key}", bm, "accent", layer_frame, smooth=True)

    # led under the arm tip
    bm = rounded_box((0.07, 0.03, 0.02), (mx * 0.86, my * 0.86, 0.0), 0.006, 1, angle)
    part(f"led_{key}", bm, "led_white" if my > 0 else "led_red", layer_frame)

    # propeller on its own pivot so the app can spin it
    pivot = empty(f"spin_{key}", layer_frame, (mx, my, 0.245))
    direction = 1 if key in ("fl", "br") else -1
    bm = bmesh.new()
    pw.add_cone(bm, (0, 0, -0.012), 0.045, 0.035, 0.035, segments=16)
    for side in (0, 1):
        blade = bmesh.ops.create_cube(bm, size=1.0)["verts"]
        bmesh.ops.scale(bm, vec=Vector((0.6, 0.085, 0.012)), verts=blade)
        bmesh.ops.translate(bm, verts=blade, vec=Vector((0.34, 0, 0.004)))
        for v in blade:
            r = max(0.0, v.co.x)
            twist = direction * (0.38 - r * 0.42)
            v.co.y, v.co.z = v.co.y * math.cos(twist) - v.co.z * math.sin(twist), v.co.y * math.sin(twist) + v.co.z * math.cos(twist)
            v.co.y *= 1.0 - 0.45 * (r / 0.64) ** 2
        bmesh.ops.rotate(bm, verts=blade, cent=(0, 0, 0), matrix=Matrix.Rotation(side * math.pi, 3, "Z"))
    part(f"prop_{key}", bm, "prop", pivot)

# skids
for sx in (-0.34, 0.34):
    bm = bmesh.new()
    pw.add_cone(bm, (0, 0, 0), 0.014, 0.014, 0.9, segments=10)
    bmesh.ops.rotate(bm, verts=bm.verts[:], cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, "X"))
    bmesh.ops.translate(bm, verts=bm.verts[:], vec=Vector((sx * 1.15, 0.45, -0.3)))
    for sy in (-0.22, 0.22):
        pw.add_cone(bm, (sx * 1.05, sy, -0.3), 0.012, 0.012, 0.3, segments=8)
    part(f"skid_{'l' if sx < 0 else 'r'}", bm, "rubber", layer_frame, smooth=True)

# --- flight controller board ----------------------------------------------------------------
part("board", rounded_box((0.62, 0.46, 0.022), (0, 0, 0.09), 0.006, 1), "pcb", layer_board)
bm = bmesh.new()
for (cx, cy, sx, sy) in ((0.0, 0.05, 0.16, 0.16), (-0.18, -0.12, 0.08, 0.06), (0.17, -0.12, 0.1, 0.05), (-0.2, 0.14, 0.06, 0.06), (0.2, 0.15, 0.07, 0.04)):
    pw.add_box(bm, (cx, cy, 0.112), (sx, sy, 0.025))
part("chips", bm, "chip", layer_board)
bm = bmesh.new()
for k in range(7):
    pw.add_box(bm, (-0.06 + k * 0.02, -0.02, 0.15), (0.008, 0.18, 0.06))
pw.add_box(bm, (0.0, -0.02, 0.117), (0.15, 0.2, 0.012))
part("heatsink", bm, "metal", layer_board)
bm = bmesh.new()
for (cx, cy) in ((0.24, -0.02), (0.24, 0.05), (-0.25, 0.02)):
    pw.add_cone(bm, (cx, cy, 0.1), 0.022, 0.022, 0.05, segments=12)
part("capacitors", bm, "battery", layer_board, smooth=True)

# --- battery ------------------------------------------------------------------------------------
part("battery_pack", rounded_box((0.68, 0.34, 0.15), (0, -0.02, 0.21), 0.035, 3), "battery", layer_battery, smooth=False)
part("battery_label", rounded_box((0.69, 0.345, 0.04), (0, -0.02, 0.215), 0.012, 2), "accent", layer_battery)
bm = bmesh.new()
pw.add_box(bm, (0.36, -0.02, 0.2), (0.05, 0.12, 0.06))
part("battery_plug", bm, "chip", layer_battery)

# --- canopy ----------------------------------------------------------------------------------------
bm = bmesh.new()
bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=1.0)
bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < -0.05], context="VERTS")
for v in bm.verts:
    v.co.x *= 0.6
    v.co.y *= 0.44
    v.co.z = max(v.co.z, 0.0) * 0.22
    # sloped nose
    if v.co.y > 0.2:
        v.co.z *= 1.0 - (v.co.y - 0.2) * 1.2
bmesh.ops.translate(bm, verts=bm.verts[:], vec=Vector((0, -0.01, 0.2)))
part("canopy", bm, "shell", layer_top, smooth=True)
bm = bmesh.new()
bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=1.0)
bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < -0.05 or abs(v.co.x) > 0.16], context="VERTS")
for v in bm.verts:
    v.co.x *= 0.6
    v.co.y *= 0.445
    v.co.z = max(v.co.z, 0.0) * 0.225
    if v.co.y > 0.2:
        v.co.z *= 1.0 - (v.co.y - 0.2) * 1.2
bmesh.ops.translate(bm, verts=bm.verts[:], vec=Vector((0, -0.01, 0.201)))
part("stripe", bm, "accent", layer_top, smooth=True)
bm = bmesh.new()
pw.add_cone(bm, (0, -0.16, 0.405), 0.075, 0.07, 0.03, segments=24)
part("gps", bm, "shell", layer_top, smooth=True)
bm = bmesh.new()
for sx in (-0.18, 0.18):
    verts = pw.add_cone(bm, (0, 0, 0), 0.009, 0.006, 0.22, segments=8)
    bmesh.ops.rotate(bm, verts=verts, cent=(0, 0, 0), matrix=Matrix.Rotation(-0.5, 3, "X"))
    bmesh.ops.translate(bm, verts=verts, vec=Vector((sx, -0.3, 0.3)))
part("antennas", bm, "rubber", layer_top, smooth=True)
bm = bmesh.new()
pw.add_box(bm, (0, 0.33, 0.27), (0.22, 0.02, 0.04))
part("front_sensor", bm, "glass", layer_top)

# --- camera and gimbal ----------------------------------------------------------------------------------
gimbal = empty("gimbal_pivot", layer_camera, (0, 0.36, -0.12))
bm = bmesh.new()
pw.add_box(bm, (0, 0, 0.06), (0.24, 0.06, 0.02))
pw.add_box(bm, (-0.125, 0, -0.03), (0.02, 0.05, 0.18))
pw.add_box(bm, (0.125, 0, -0.03), (0.02, 0.05, 0.18))
pw.add_cone(bm, (0, 0, 0.07), 0.035, 0.035, 0.08, segments=16)
part("gimbal_yoke", bm, "metal", gimbal)
part("camera_body", rounded_box((0.2, 0.16, 0.15), (0, 0, -0.06), 0.03, 3), "shell", gimbal, smooth=False)
bm = bmesh.new()
verts = pw.add_cone(bm, (0, 0, 0), 0.06, 0.055, 0.06, segments=32)
bmesh.ops.rotate(bm, verts=verts, cent=(0, 0, 0), matrix=Matrix.Rotation(-math.pi / 2, 3, "X"))
bmesh.ops.translate(bm, verts=verts, vec=Vector((0, 0.08, -0.06)))
part("lens_ring", bm, "metal", gimbal, smooth=True)
bm = bmesh.new()
verts = pw.add_cone(bm, (0, 0, 0), 0.045, 0.045, 0.01, segments=32)
bmesh.ops.rotate(bm, verts=verts, cent=(0, 0, 0), matrix=Matrix.Rotation(-math.pi / 2, 3, "X"))
bmesh.ops.translate(bm, verts=verts, vec=Vector((0, 0.141, -0.06)))
part("lens_glass", bm, "glass", gimbal, smooth=True)

pw.export_glb(args.out)
