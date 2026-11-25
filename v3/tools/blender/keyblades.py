"""Oathkeeper & Oblivion (Kingdom Hearts) keyblade meshes -> V3 weapon meshes (Daniel 2026-11-25, for hooded_blades).

    python keyblades.py <scene.gltf from the Sketchfab zip> [out_dir]      (default out_dir: characters/weapons3d)

Source: "Oathkeeper and Oblivion (Kingdom Hearts)" by PronoesPro, CC-BY-4.0
(https://sketchfab.com/3d-models/oathkeeper-and-oblivion-kingdom-hearts-b29ff005b6cf46ee97ffcba5a966415d);
the credit lives in characters/weapons3d/CREDITS.md and must stay with the files.

Each keyblade is written as its own small .glb (one mesh, the shared texture at 512 px JPEG) in the V3 weapon frame
(v3/js/weapons3d.js): origin = the middle of the grip (where the fist closes), +Y = grip -> tip, +X = the side the
teeth stick out (the weapon's "edge" side), flat faces along +-Z. Decimated to ~TARGET_TRIS triangles each and
scaled so the grip -> tip length is REACH metres for Oathkeeper (the same scale for both: Oblivion stays a little
longer, as modelled).

Measured on the source (glTF space, Y up, both lie flat in XZ, hilts toward +Z, teeth toward -X):
    Oathkeeper = mesh 'Cylinder001' (light), shaft x -0.412, crossguard z 0.31 .. pommel z 1.02
    Oblivion   = mesh 'Box024' (dark),       shaft x +0.452, crossguard z 0.44 .. pommel z 1.05
"""
import os
import sys

import bpy
import bmesh
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
SRC = argv[0]
OUT = argv[1] if len(argv) > 1 else os.path.join(ROOT, "characters", "weapons3d")
TARGET_TRIS = 4000
REACH = 1.05            # m, Oathkeeper grip -> tip (the body's plain blade is ~1.0 m out of the fist)
TEX_PX = 512

# name: (source mesh prefix, grip point in glTF space (shaft x, y, mid of crossguard..pommel z))
BLADES = {
    "oathkeeper": ("Cylinder001", Vector((-0.412, 0.0, (0.31 + 1.02) / 2))),
    "oblivion": ("Box024", Vector((0.452, 0.0, (0.44 + 1.05) / 2))),
}
OATH_TIP_Z = -0.85      # Oathkeeper's tip, glTF z (sets the scale)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=SRC)
scale = REACH / (BLADES["oathkeeper"][1].z - OATH_TIP_Z)

# glTF (x, y, z) <-> Blender (x, -z, y)
G2B = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
B2G = G2B.inverted()
# weapon frame from glTF space: +Y_w = -Z_g (toward the tip), +X_w = -X_g (teeth), +Z_w = X_w x Y_w = -Y_g
W_FROM_G = Matrix(((-1, 0, 0, 0), (0, 0, -1, 0), (0, -1, 0, 0), (0, 0, 0, 1)))

os.makedirs(OUT, exist_ok=True)
for img in bpy.data.images:
    if img.size[0] > TEX_PX:
        img.scale(TEX_PX, TEX_PX)

for name, (prefix, grip) in BLADES.items():
    src = next(o for o in bpy.data.objects if o.type == "MESH" and o.name.startswith(prefix))
    # bake the world transform, move the grip to the origin, turn into the weapon frame, scale (all as one matrix,
    # in Blender space so the glTF exporter's Y-up conversion gives back the weapon frame)
    m = G2B @ Matrix.Scale(scale, 4) @ W_FROM_G @ Matrix.Translation(-grip) @ B2G @ src.matrix_world
    me = src.data.copy()
    me.transform(m)
    if m.determinant() < 0:
        me.flip_normals()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    dec = ob.modifiers.new("dec", "DECIMATE")
    dec.ratio = min(1.0, TARGET_TRIS / max(1, tris))
    dec.use_collapse_triangulate = True
    for o in bpy.context.view_layer.objects:
        o.select_set(o is ob)
    bpy.ops.object.modifier_apply(modifier="dec")
    # merge the seams the decimate leaves open (tiny distance only)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0005)
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.name = name
    for mat in ob.data.materials:
        mat.name = name
    after = sum(len(p.vertices) - 2 for p in ob.data.polygons)
    for o in bpy.context.view_layer.objects:
        o.select_set(o is ob)
    path = os.path.join(OUT, name + ".glb")
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_yup=True,
                              export_image_format="JPEG", export_jpeg_quality=85, export_apply=True,
                              export_animations=False, export_skins=False, export_morph=False)
    vs = [ob.matrix_world @ v.co for v in ob.data.vertices]
    ys = [(v.x, v.z, -v.y) for v in vs]      # back to glTF / weapon frame for the report
    lo = [min(c[i] for c in ys) for i in range(3)]
    hi = [max(c[i] for c in ys) for i in range(3)]
    print("%s: %d -> %d tris, %d KB, weapon frame x %.2f..%.2f y %.2f..%.2f z %.2f..%.2f" % (
        name, tris, after, os.path.getsize(path) // 1024, lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]))
