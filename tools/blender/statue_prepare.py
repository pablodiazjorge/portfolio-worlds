"""Prepares a generated asset for the gallery: imports the raw GLB that TRELLIS.2 produced from a
reference image, puts its origin where the museum script will hold it (the feet on the ground for
the statue, the rod for a banner, the back plate for a sconce), centres it, turns it to face -Y,
scales it to a height or a width, decimates it to a budget of faces, keeps only the colour map,
shrinks it and exports the GLB with a material named for the scene.

    blender --background --python tools/blender/statue_prepare.py -- --in <raw.glb> --out <asset.glb> [--faces 40000] [--yaw 0] [--height 2.9 | --width 1.4] [--anchor bottom|top|back] [--material statue_tex]
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
parser.add_argument("--width", type=float, default=None, help="metres across, instead of a height")
parser.add_argument("--anchor", choices=("bottom", "top", "back"), default="bottom", help="where the origin goes: the feet, the top (a banner on its rod) or the back face (a wall sconce)")
parser.add_argument("--material", default="statue_tex", help="name of the single material, which the scene recognises by its _tex suffix")
parser.add_argument("--report", action="store_true", help="only print the bounds and face count")
parser.add_argument("--sink", type=float, default=0.03, help="metres the feet bite into the ground, so the figure does not hover")
parser.add_argument("--texture", type=int, default=1024, help="longest side the baked textures are shrunk to")
parser.add_argument("--keep-mr", action="store_true", help="keep the baked metallic-roughness map too (at most 1K), for props with metal in them")
parser.add_argument("--hang", type=float, default=None, help="for a banner: hang the cloth straight under its rod and keep this fraction of the depth of whatever stands off it, so a modelled emblem becomes a relief")
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

# scale so the figure stands `height` tall (or `width` across), hang a banner straight, then set
# the origin at the anchor
scale = args.width / size.x if args.width else args.height / size.z
statue.scale = (scale, scale, scale)
bpy.ops.object.transform_apply(scale=True)

if args.hang is not None:
    # the cloth's lean is read from the median depth of each band of height below the rod loops,
    # then every vertex below the loops is moved to a vertical plane through the top of the cloth,
    # keeping only `hang` of its distance to the cloth; the rod and loops are left alone
    me = statue.data
    z_top = max(v.co.z for v in me.vertices)
    z_loops = z_top - 0.35
    bands = {}
    for v in me.vertices:
        if v.co.z < z_loops:
            bands.setdefault(int(v.co.z // 0.15), []).append(v.co.y)
    samples = [((k + 0.5) * 0.15, sorted(ys)[len(ys) // 2]) for k, ys in bands.items() if len(ys) > 20]
    n = len(samples)
    mz, my = sum(z for z, _ in samples) / n, sum(y for _, y in samples) / n
    slope = sum((z - mz) * (y - my) for z, y in samples) / max(1e-9, sum((z - mz) ** 2 for z, _ in samples))
    y_hang = my + slope * (z_loops - mz)
    for v in me.vertices:
        t = min(1.0, max(0.0, (z_loops - v.co.z) / 0.1))
        if t > 0:
            y_cloth = my + slope * (v.co.z - mz)
            v.co.y += t * (y_hang + (v.co.y - y_cloth) * args.hang - v.co.y)
    me.update()
    bpy.context.view_layer.update()
    print(f"[statue] hung straight: lean {slope:+.3f} m/m, cloth at y {y_hang:+.3f}, relief kept {args.hang:.2f}")

corners = [statue.matrix_world @ Vector(c) for c in statue.bound_box]
lo = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
hi = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
if args.anchor == "top":
    statue.location = Vector((-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -hi.z))
elif args.anchor == "back":
    statue.location = Vector((-(lo.x + hi.x) / 2, -hi.y, -(lo.z + hi.z) / 2))
else:
    statue.location = Vector((-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z - args.sink))
bpy.ops.object.transform_apply(location=True)

if len(statue.data.polygons) > args.faces:
    mod = statue.modifiers.new("decimate", "DECIMATE")
    mod.ratio = args.faces / len(statue.data.polygons)
    bpy.ops.object.modifier_apply(modifier="decimate")
print(f"[statue] faces after decimation {len(statue.data.polygons)}")

# one material named for the scene, which keeps the baked texture and lets the statue cast shadows
statue.name = statue.data.name = args.material.replace("_tex", "")
for m in statue.data.materials:
    if m:
        m.name = args.material

# only the base colour map goes out (and the metallic-roughness map when asked for): the scene
# lights a stone figure with its own roughness, a metal prop with the baked one
for m in statue.data.materials:
    if not m or not m.node_tree:
        continue
    tree = m.node_tree
    bsdf = next((n for n in tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    sockets = {"Base Color"} | ({"Metallic", "Roughness"} if args.keep_mr else set())
    keep, mr = set(), set()
    for link in tree.links:
        if not bsdf or link.to_node != bsdf or link.to_socket.name not in sockets:
            continue
        # the importer puts a Separate Color node between the metallic-roughness image and the BSDF
        node = link.from_node
        for _ in range(3):
            if node.type == "TEX_IMAGE":
                keep.add(node)
                if link.to_socket.name != "Base Color":
                    mr.add(node)
                break
            inputs = [l.from_node for l in tree.links if l.to_node == node]
            if not inputs:
                break
            node = inputs[0]
    for n in list(tree.nodes):
        if n.type == "TEX_IMAGE" and n not in keep:
            tree.nodes.remove(n)
    for n in tree.nodes:
        if n.type == "TEX_IMAGE" and n.image:
            limit = min(args.texture, 1024) if n in mr else args.texture
            if max(n.image.size) > limit:
                n.image.scale(limit, limit)

os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
bpy.ops.export_scene.gltf(filepath=args.out, export_format="GLB", export_apply=True, export_yup=True, export_image_format="JPEG", export_jpeg_quality=82, export_materials="EXPORT", export_animations=False, export_cameras=False, export_lights=False)
print(f"[statue] exported {args.out} ({os.path.getsize(args.out) // 1024} KB)")
