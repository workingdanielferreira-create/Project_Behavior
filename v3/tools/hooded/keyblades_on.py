"""Put Oathkeeper (right hand) and Oblivion (left hand) on Hooded Blades (Daniel 2026-11-25: hands as the FX presets,
w_hand1 = right = Oathkeeper). Writes pb_body.weapons into characters/hooded_blades/hooded_blades.glb; dict weapon
configs survive retarget2d / anim3d rebuilds and Rig Forge 3D saves (its weapon editor shows them as shape "mesh").

    python v3/tools/hooded/keyblades_on.py [roll_R roll_L]
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import retarget2d as r  # noqa: E402

GLB = os.path.join(HERE, '..', '..', '..', 'characters', 'hooded_blades', 'hooded_blades.glb')
ROLL = (0.0, 0.0)           # deg round the blade line (checked on renders of the hands)
ROLL_R, ROLL_L = (float(a) for a in sys.argv[1:3]) if len(sys.argv) > 2 else ROLL

j, b = r.read_glb(GLB)
ex = j["scenes"][j.get("scene", 0)].setdefault("extras", {})
pb = ex.setdefault("pb_body", {})
pb["weapons"] = {"R": {"on": True, "shape": "mesh", "mesh": "oathkeeper", "len": 0, "grip": 0, "roll": ROLL_R},
                 "L": {"on": True, "shape": "mesh", "mesh": "oblivion", "len": 0, "grip": 0, "roll": ROLL_L}}
r.save_glb(GLB, j, b)
print("hooded_blades weapons:", pb["weapons"])
