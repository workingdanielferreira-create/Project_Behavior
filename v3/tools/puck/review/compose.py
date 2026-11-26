"""compose.py clip out.gif times.json frames_dir (env CHAR, default puck): 2D frame at that time | side | 3/4, labelled; GIF."""
import sys, json, os
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
CH = os.environ.get("CHAR", "puck")
from PIL import Image, ImageDraw, ImageFont
clip, out, tf, fd = sys.argv[1:5]
T = json.load(open(tf)); d = json.load(open(os.path.join(ROOT, 'characters', CH, 'character.json')))
act = d['actions'][clip]; fms = act['frame_ms'] / 1000.0; fr = act['frames']
try: F = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 18)
except Exception: F = None
ims = []
for i, t in enumerate(T['times']):
    fi = min(len(fr) - 1, int(t * act['duration_ms'] / 1000.0 / T['len'] / fms + 1e-6)) if T.get('len') else min(len(fr)-1, int(t / fms))
    two = Image.open(os.path.join(ROOT, 'characters', CH, fr[fi])).convert('RGBA').resize((408, 472))
    panel = Image.new('RGB', (408 + 520 * len(T['views']), 600), 'white')
    panel.paste(two, (0, 70), two)
    for k, v in enumerate(T['views']):
        panel.paste(Image.open('%s/%d_%s.png' % (fd, i, v)), (408 + 520 * k, 40))
    dr = ImageDraw.Draw(panel)
    lab = T['labels'][i] if T.get('labels') else ''
    dr.text((10, 8), '%s   t=%.3fs   2D frame %d   %s' % (clip, t, fi + 1, lab), fill='black', font=F)
    for k, v in enumerate(T['views']):
        dr.text((418 + 520 * k, 575), {'side': 'side (target ->)', 'q34': '3/4 front', 'front': 'front', 'top': 'top', 'sil': 'silhouette (side)'}[v], fill='#555', font=F)
    ims.append(panel)
dur = T.get('ms', 900)
ims[0].save(out, save_all=True, append_images=ims[1:], duration=dur, loop=0)
print(out, len(ims))
