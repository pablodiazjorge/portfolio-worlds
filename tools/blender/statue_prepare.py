"""Prepares the generated statue for the gallery: imports the raw GLB that TRELLIS.2 produced from
the reference crop, drops it onto the ground with its feet at z = 0 and its centre on the origin,
turns it to face -Y (the gallery's statue faces the entrance, to the south), decimates it to a
budget of faces, shrinks its textures to 1K JPEG and exports tools/assets/trellis/statue.glb.

    blender --background --python tools/blender/statue_prepare.py -- --in <raw.glb> --out <statue.glb> [--faces 40000] [--yaw 0] [--height 2.9]
"""

import argparse
import math
import os
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
parser = argparse.ArgumentParser()
parser.add_argument("--in", dest="src", required=True)
parser.add_argument("--out", required=True)
parser.add_argument("--faces", type=int, default=40000)
parser.add_argument("--yaw", type=float, default=0.0, help="degrees, applied before measuring")
parser.add_argument("--height", type=float, default=2.9, help="metres from the feet to the top of the head")
parser.add_argument("--report", action="store_true", help="only print the bounds and face count")
parser.add_argument("--sink", type=float, default=0.03, help="metres the feet bite into the ground, so the figure does not hover")
parser.add_argument("--texture", type=int, default=1024, help="longest side the baked textures are shrunk to")
args = parser.parse_args(argv)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=args.src)
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
if not meshes:
    raise SystemExit("no meshes in " + args.src)

# one object, transforms applied, so the bounds are honest
bpy.ops.object.select_all(action="DESELECT")
for o in meshes:
    o.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
if len(meshes) > 1:
    bpy.ops.object.join()
statue = bpy.context.view_layer.objects.active
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
statue.rotation_euler = (0, 0, math.radians(args.yaw))
bpy.ops.object.transform_apply(rotation=True)

corners = [statue.matrix_world @ Vector(c) for c in statue.bound_box]
lo = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
hi = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
size = hi - lo
print(f"[statue] raw bounds {size.x:.2f} x {size.y:.2f} x {size.z:.2f} m, faces {len(statue.data.polygons)}")
images = sorted({(n.image.name, tuple(n.image.size)) for m in statue.data.materials if m and m.node_tree for n in m.node_tree.nodes if n.type == "TEX_IMAGE" and n.image})
print("[statue] images", images)
if args.report:
    raise SystemExit(0)

# scale so the figure stands `height` tall, feet on the ground, centred in x and y
scale = args.height / size.z
statue.scale = (scale, scale, scale)
bpy.ops.object.transform_apply(scale=True)
corners = [statue.matrix_world @ Vector(c) for c in statue.bound_box]
lo = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
hi = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
statue.location = Vector((-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z - args.sink))
bpy.ops.object.transform_apply(location=True)

if len(statue.data.polygons) > args.faces:
    mod = statue.modifiers.new("decimate", "DECIMATE")
    mod.ratio = args.faces / len(statue.data.polygons)
    bpy.ops.object.modifier_apply(modifier="decimate")
print(f"[statue] faces after decimation {len(statue.data.polygons)}")

# one material named for the scene, which keeps the baked texture and lets the statue cast shadows
statue.name = statue.data.name = "statue"
for m in statue.data.materials:
    if m:
        m.name = "statue_tex"

# only the base colour map goes out: the scene lights the statue with its own roughness
for m in statue.data.materials:
    if not m or not m.node_tree:
        continue
    tree = m.node_tree
    bsdf = next((n for n in tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    keep = {link.from_node for link in tree.links if bsdf and link.to_node == bsdf and link.to_socket.name == "Base Color"}
    for n in list(tree.nodes):
        if n.type == "TEX_IMAGE" and n not in keep:
            tree.nodes.remove(n)
    for n in tree.nodes:
        if n.type == "TEX_IMAGE" and n.image and max(n.image.size) > args.texture:
            n.image.scale(args.texture, args.texture)

os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
bpy.ops.export_scene.gltf(filepath=args.out, export_format="GLB", export_apply=True, export_yup=True, export_image_format="JPEG", export_jpeg_quality=82, export_materials="EXPORT", export_animations=False, export_cameras=False, export_lights=False)
print(f"[statue] exported {args.out} ({os.path.getsize(args.out) // 1024} KB)")
