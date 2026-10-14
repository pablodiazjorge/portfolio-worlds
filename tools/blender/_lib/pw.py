"""Shared helpers for the portfolio-worlds Blender scripts.

Every script builds its model from code so the asset is reproducible:
    blender --background --factory-startup --python tools/blender/<asset>.py -- --out <file.glb>
"""

import argparse
import math
import random
import sys

import bpy
import bmesh
from mathutils import Vector


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--seed", type=int, default=7)
    # scripts may read options of their own from the same argument list
    return parser.parse_known_args(argv)[0]


def reset(seed):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    random.seed(seed)


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_color(value, alpha=1.0):
    """Linear RGBA from an sRGB hex string, the space Blender and glTF store colors in."""
    value = value.lstrip("#")
    r, g, b = (int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return (srgb_to_linear(r), srgb_to_linear(g), srgb_to_linear(b), alpha)


def material(name, color, roughness=0.8, metallic=0.0, emission=None, emission_strength=0.0, alpha=1.0):
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = hex_color(color) if isinstance(color, str) else color
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if emission:
        bsdf.inputs["Emission Color"].default_value = hex_color(emission)
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
        mat.blend_method = "BLEND"
    return mat


def vertex_color_material(name, roughness=0.9):
    """Material whose base color comes from the mesh's active color attribute."""
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = roughness
    attr = nodes.new("ShaderNodeVertexColor")
    attr.layer_name = "Col"
    mat.node_tree.links.new(attr.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def link(obj, collection=None):
    (collection or bpy.context.scene.collection).objects.link(obj)
    return obj


def collection(name):
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return col


def mesh_object(name, verts, faces, mat=None, collection_=None, smooth=False):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    mesh.update()
    for poly in mesh.polygons:
        poly.use_smooth = smooth
    obj = bpy.data.objects.new(name, mesh)
    if mat:
        obj.data.materials.append(mat)
    return link(obj, collection_)


def bm_object(name, bm, mat=None, collection_=None, smooth=False):
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for poly in mesh.polygons:
        poly.use_smooth = smooth
    obj = bpy.data.objects.new(name, mesh)
    if mat:
        if isinstance(mat, (list, tuple)):
            for m in mat:
                obj.data.materials.append(m)
        else:
            obj.data.materials.append(mat)
    return link(obj, collection_)


def set_vertex_colors(obj, colors):
    """colors: sequence of linear RGBA tuples, one per vertex."""
    mesh = obj.data
    attr = mesh.color_attributes.new(name="Col", type="BYTE_COLOR", domain="POINT")
    flat = [channel for color in colors for channel in color]
    attr.data.foreach_set("color", flat)
    mesh.color_attributes.active_color = attr
    mesh.color_attributes.render_color_index = 0


def empty(name, location, collection_=None, size=1.0):
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_size = size
    obj.location = location
    return link(obj, collection_)


def add_cone(bm, base, radius1, radius2, depth, segments=7, rotation=0.0, cap_ends=True):
    """Adds a cone or cylinder to `bm` standing on `base` (x, y, z)."""
    result = bmesh.ops.create_cone(
        bm,
        cap_ends=cap_ends,
        cap_tris=False,
        segments=segments,
        radius1=radius1,
        radius2=radius2,
        depth=depth,
    )
    verts = result["verts"]
    bmesh.ops.rotate(bm, verts=verts, cent=(0, 0, 0), matrix=_rot_z(rotation))
    bmesh.ops.translate(bm, verts=verts, vec=Vector(base) + Vector((0, 0, depth / 2)))
    return verts


def add_box(bm, center, size, rotation=0.0):
    result = bmesh.ops.create_cube(bm, size=1.0)
    verts = result["verts"]
    bmesh.ops.scale(bm, vec=Vector(size), verts=verts)
    bmesh.ops.rotate(bm, verts=verts, cent=(0, 0, 0), matrix=_rot_z(rotation))
    bmesh.ops.translate(bm, verts=verts, vec=Vector(center))
    return verts


def add_ico(bm, center, radius, subdivisions=1, scale=(1, 1, 1)):
    result = bmesh.ops.create_icosphere(bm, subdivisions=subdivisions, radius=radius)
    verts = result["verts"]
    bmesh.ops.scale(bm, vec=Vector(scale), verts=verts)
    bmesh.ops.translate(bm, verts=verts, vec=Vector(center))
    return verts


def assign_material_index(bm, verts, index):
    vert_set = set(verts)
    for face in bm.faces:
        if all(v in vert_set for v in face.verts):
            face.material_index = index


def _rot_z(angle):
    from mathutils import Matrix
    return Matrix.Rotation(angle, 3, "Z")


def smoothstep(edge0, edge1, x):
    t = max(0.0, min(1.0, (x - edge0) / (edge1 - edge0)))
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    return a + (b - a) * t


def export_glb(path, animations=False):
    import os
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format="GLB",
        export_apply=True,
        export_yup=True,
        export_extras=True,
        export_vertex_color="ACTIVE",
        export_animations=animations,
        export_cameras=False,
        export_lights=False,
        export_materials="EXPORT",
        use_selection=False,
    )
    print(f"[pw] exported {path}")
