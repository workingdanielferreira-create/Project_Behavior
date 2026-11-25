"""Arc check for a sampled clip (arcs.js): kinks per layer + side / top trail images.
python arcs.py out/arcs_<x>.json out/spec.json out/arcs_<x>.png"""
import json, sys, numpy as np
from PIL import Image, ImageDraw
d = json.load(open(sys.argv[1])); spec = json.load(open(sys.argv[2]))
T = np.array(d['t']); P = {k: np.array(v) for k, v in d['p'].items()}
keys = [(k['t'], k.get('label', '')) for k in spec['keys']]
LAYERS = {'hips': P['Hips'], 'chest|hips': P['Spine2'] - P['Hips'], 'head|chest': P['Head'] - P['Spine2'],
          'handR|shoulder': P['RightHand'] - P['RightArm'], 'handL|shoulder': P['LeftHand'] - P['LeftArm'],
          'Oathkeeper tip': P['KTip_R'], 'Oblivion tip': P['KTip_L']}
def kinks(X, min_v=0.004):
    out = []
    V = np.diff(X, axis=0); s = np.linalg.norm(V, axis=1)
    for i in range(1, len(V)):
        if s[i] < min_v or s[i - 1] < min_v:
            continue
        c = np.dot(V[i], V[i - 1]) / (s[i] * s[i - 1]); a = np.degrees(np.arccos(np.clip(c, -1, 1)))
        pop = s[i] / max(1e-6, 0.5 * (s[i - 1] + (s[i + 1] if i + 1 < len(s) else s[i - 1])))
        if a > 55 or pop > 2.2:
            out.append((round(T[i], 3), round(float(a)), round(float(pop), 1), round(float(s[i] * 60), 1)))
    return out
for n, X in LAYERS.items():
    ks = kinks(X)
    print('%-16s %s' % (n, ' '.join('t%.3f:%ddeg x%.1f %sm/s' % k for k in ks) or 'clean'))
# trails: side (z right, y up) and top (z right, x down)
W, H = 900, 460; img = Image.new('RGB', (W * 2, H), 'white'); dr = ImageDraw.Draw(img)
COL = {'Hips': (200, 40, 40), 'Head': (120, 60, 160), 'RightHand': (230, 140, 0), 'LeftHand': (40, 120, 200),
       'KTip_R': (160, 160, 160), 'KTip_L': (20, 20, 30)}
allp = np.concatenate([P[k] for k in COL]); zmin, zmax = allp[:, 2].min() - .1, allp[:, 2].max() + .1
sc = min((W - 40) / (zmax - zmin), (H - 40) / 3.2)
for v, (ia, oy) in enumerate(((1, 0), (0, 0))):
    ox = v * W
    def px(p):
        if ia == 1: return (ox + 20 + (p[2] - zmin) * sc, H - 30 - p[1] * sc)
        return (ox + 20 + (p[2] - zmin) * sc, H / 2 + p[0] * sc)
    dr.text((ox + 8, 6), ['SIDE (target ->, y up)', 'TOP (target ->, his right = up)'][v], fill='black')
    for k, c in COL.items():
        pts = [px(p) for p in P[k]]
        dr.line(pts, fill=c, width=2)
        for i, q in enumerate(pts): dr.ellipse([q[0] - 1.5, q[1] - 1.5, q[0] + 1.5, q[1] + 1.5], fill=c)
        for kt, lab in keys:
            i = int(round(kt * 60)); i = min(i, len(pts) - 1); q = pts[i]
            dr.ellipse([q[0] - 4, q[1] - 4, q[0] + 4, q[1] + 4], outline=c, width=2)
    yy = 20
    for k, c in COL.items():
        dr.text((ox + W - 160, yy), {'Hips': 'hips', 'Head': 'head', 'RightHand': 'R hand', 'LeftHand': 'L hand',
                'KTip_R': 'Oathkeeper tip', 'KTip_L': 'Oblivion tip'}[k], fill=c); yy += 14
img.save(sys.argv[3]); print(sys.argv[3])
