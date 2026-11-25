# 3D weapon meshes (V3) — credits

Shared weapon meshes for V3 fighters (`v3/js/weapons3d.js` shape `mesh`, packed by `v3/tools/build_kits.py`).
Each `<id>.glb` is in the V3 weapon frame: origin = middle of the grip, +Y = grip -> tip, +X = edge / teeth side.

## oathkeeper.glb, oblivion.glb

This work is based on "Oathkeeper and Oblivion (Kingdom Hearts)"
(https://sketchfab.com/3d-models/oathkeeper-and-oblivion-kingdom-hearts-b29ff005b6cf46ee97ffcba5a966415d)
by PronoesPro (https://sketchfab.com/pronoespro) licensed under CC-BY-4.0
(http://creativecommons.org/licenses/by/4.0/).

Changes: split into one file per keyblade, decimated (~37k / ~14k -> ~4k triangles each), re-oriented and scaled to the
V3 weapon frame, texture reduced to 512 px JPEG (`v3/tools/blender/keyblades.py`).
