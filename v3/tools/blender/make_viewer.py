"""Embed a .glb into viewer_template.html -> a single self-contained viewer page.

    python make_viewer.py characters/ronin_copy/ronin_copy.glb out.html
"""
import base64
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
glb, out = sys.argv[1], sys.argv[2]
tpl = open(os.path.join(HERE, "viewer_template.html"), encoding="utf-8").read()
data = base64.b64encode(open(glb, "rb").read()).decode("ascii")
open(out, "w", encoding="utf-8").write(tpl.replace("__GLB__", data))
print("wrote", out)
