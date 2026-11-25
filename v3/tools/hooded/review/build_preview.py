"""Full-mesh preview of one Hooded Blades clip with the keyblades -> out/preview.js for view.html.
Usage: build_preview.py <clip>   (the draft in gen_hooded.py CLIPS, else hooded_blades.anim3d.json)"""
import sys, os, json, base64, glob
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(HERE, '..'))
import anim3d, retarget2d as r
clip = sys.argv[1]
B = anim3d.Body()
import gen_hooded
os.makedirs(os.path.join(HERE, 'out'), exist_ok=True)
spec = gen_hooded.CLIPS[clip]() if clip in gen_hooded.CLIPS else json.load(open(anim3d.spec_path('hooded_blades')))['clips'][clip]
notes = []
dense = anim3d.bake_clip(B, spec, notes, dense=True)
for n in sorted(set(notes)): print('note:', n)
json.dump(spec, open(os.path.join(HERE, 'out', 'spec.json'), 'w'))
j, b = r.pack(B.j, B.b, meshes=True, keep_anims=False, new_clips={clip: dense}, rig=B.rig)
glb = os.path.join(HERE, 'out', 'prev.glb'); r.save_glb(glb, j, bytes(b))
cj, _ = r.read_glb(os.path.join(ROOT, 'characters', 'hooded_blades', 'hooded_blades.glb'))
W = ((cj['scenes'][0].get('extras') or {}).get('pb_body') or {}).get('weapons') or {}
wm = {os.path.splitext(os.path.basename(p))[0]: base64.b64encode(open(p, 'rb').read()).decode()
      for p in glob.glob(os.path.join(ROOT, 'characters', 'weapons3d', '*.glb'))}
open(os.path.join(HERE, 'out', 'preview.js'), 'w').write('window.GLB="%s";window.CLIP="%s";window.LEN=%f;window.WEAPONS=%s;window.PB3_WEAPONS=%s;' % (
    base64.b64encode(open(glb, 'rb').read()).decode(), clip, dense[0][-1], json.dumps(W), json.dumps(wm)))
