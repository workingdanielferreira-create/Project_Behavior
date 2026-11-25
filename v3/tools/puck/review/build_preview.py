"""Full-mesh preview of one clip (dense, 60 fps) -> out/preview.js for view.html. Usage: build_preview.py <char> <clip>"""
import sys, os, json, base64
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
import anim3d, retarget2d as r
name, clip = sys.argv[1], sys.argv[2]
spec = json.load(open(anim3d.spec_path(name)))
B = anim3d.Body()
notes = []
dense = anim3d.bake_clip(B, spec['clips'][clip], notes, dense=True)
for n in sorted(set(notes)): print('note:', n)
j, b = r.pack(B.j, B.b, meshes=True, keep_anims=False, new_clips={clip: dense}, rig=B.rig)
os.makedirs(os.path.join(HERE, 'out'), exist_ok=True)
glb = os.path.join(HERE, 'out', 'prev.glb'); r.save_glb(glb, j, bytes(b))
open(os.path.join(HERE, 'out', 'preview.js'), 'w').write('window.GLB="%s";window.CLIP="%s";window.LEN=%f;' % (
    base64.b64encode(open(glb, 'rb').read()).decode(), clip, dense[0][-1]))
