#!/bin/bash
# Review loop for a Puck clip (Daniel 2026-11-24: key poses shown as GIF stills beside the 2D frames, he corrects):
#   bash v3/tools/puck/review/go.sh <clip> <tag>
# regenerates the clip from gen_puck.py, audits it, then writes into v3/tools/puck/review/out/:
#   <clip>_keys_<tag>.gif   (each key pose 1.1 s: 2D frame | side | 3/4 | front)
#   <clip>_motion_<tag>.gif (the whole clip at 1/30 s steps)   <clip>_sheet_<tag>.png (keys contact sheet)
# Needs node + playwright (pre-installed in cloud sessions). out/ is gitignored.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$HERE/../../../.."
cd "$ROOT" && python3 v3/tools/puck/gen_puck.py "$1" >/dev/null && python3 v3/tools/anim3d.py puck --check | grep -v " 0/" | tail -12
cd "$HERE" && mkdir -p out && python3 build_preview.py puck "$1"
python3 - "$1" <<'PY'
import json, sys
spec = json.load(open('../../../../characters/puck/puck.anim3d.json'))['clips'][sys.argv[1]]
ks = [k['t'] for k in spec['keys']]; L = spec['length']
json.dump({'times': ks, 'views': ['side', 'q34', 'front'], 'labels': [k.get('label', '') for k in spec['keys']], 'ms': 1100}, open('out/keys.json', 'w'))
n = int(round(L * 30)); json.dump({'times': [i / 30 for i in range(n + 1)], 'views': ['side', 'q34'], 'ms': 100}, open('out/motion.json', 'w'))
PY
rm -rf out/k out/m; node shoot.js out/keys.json out/k >/dev/null && node shoot.js out/motion.json out/m >/dev/null
python3 compose.py "$1" "out/$1_keys_$2.gif" out/keys.json out/k && python3 compose.py "$1" "out/$1_motion_$2.gif" out/motion.json out/m
python3 - "out/$1_keys_$2.gif" "out/$1_sheet_$2.png" <<'PY'
import sys
from PIL import Image
im = Image.open(sys.argv[1]); fr = []
try:
    while True: fr.append(im.convert('RGB').resize((724, 300))); im.seek(im.tell() + 1)
except EOFError: pass
rows = (len(fr) + 1) // 2; s = Image.new('RGB', (1448, 300 * rows), 'white')
for i, f in enumerate(fr): s.paste(f, ((i % 2) * 724, (i // 2) * 300))
s.save(sys.argv[2])
PY
