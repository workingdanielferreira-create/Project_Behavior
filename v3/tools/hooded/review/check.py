"""Audit gen_hooded.py drafts without writing anything: python check.py <clip>[,<clip>...]"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(HERE, '..'))
import anim3d, anim_audit, retarget2d as r, gen_hooded
ALL = dict(gen_hooded.CLIPS, **gen_hooded.DRAFTS)
B = anim3d.Body()
notes = []
clips = {n: anim3d.bake_clip(B, ALL[n](), notes) for n in sys.argv[1].split(',')}
for n in sorted(set(notes)): print('  note:', n)
out, bin_ = r.pack(B.j, B.b, meshes=False, keep_anims=False, new_clips=clips, rig=B.rig)
held = anim_audit.held_from(r.read_glb(os.path.join(r.CHARS, 'hooded_blades', 'hooded_blades.glb'))[0])
sys.exit(anim_audit.report_from(out, bytes(bin_), B, held=held))
