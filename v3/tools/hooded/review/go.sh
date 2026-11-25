#!/bin/bash
# Review loop for a Hooded Blades clip WITH the keyblades (Oathkeeper right, Oblivion left):
#   bash v3/tools/hooded/review/go.sh <clip> <tag>
# audits the draft (gen_hooded.py CLIPS / DRAFTS; nothing is written into the .glb) and writes into out/:
#   <clip>_keys_<tag>.gif (each key 1.1 s: 2D frame | side | 3/4 | front), <clip>_motion_<tag>.gif, <clip>_sheet_<tag>.png
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"; PR="$HERE/../../puck/review"
cd "$HERE" && mkdir -p out && (python3 check.py "$1" | grep -v " 0/" | tail -14 || true)
python3 build_preview.py "$1" | tail -5
python3 - "$1" <<'PY'
import json, sys
spec = json.load(open('out/spec.json'))
ks = [k['t'] for k in spec['keys']]; L = spec['length']
json.dump({'times': ks, 'views': ['side', 'q34', 'front'], 'labels': [k.get('label', '') for k in spec['keys']], 'ms': 1100, 'len': L}, open('out/keys.json', 'w'))
n = int(round(L * 30)); json.dump({'times': [i / 30 for i in range(n + 1)], 'views': ['side', 'q34'], 'ms': 100, 'len': L}, open('out/motion.json', 'w'))
PY
rm -rf out/k out/m; node shoot.js out/keys.json out/k >/dev/null && node shoot.js out/motion.json out/m >/dev/null
CHAR=hooded_blades python3 "$PR/compose.py" "$1" "out/$1_keys_$2.gif" out/keys.json out/k
CHAR=hooded_blades python3 "$PR/compose.py" "$1" "out/$1_motion_$2.gif" out/motion.json out/m
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
