"""
Dev Cockpit publisher — pushes a capture bundle to the repo and registers it
in `captures/index.json` (cockpit_index v1), which the Cockpit's scene
picker reads.

Usage:
    GH_TOKEN=... python3 publish.py --bundle run.pbrun.json \
        --file captures/beam_debug.pbrun.json \
        --title "Beam debug — new_fighter vs mage · seed 42"

Index format (fields only ever added, never renamed/removed):
    {"version": "cockpit_index v1",
     "runs": [{"file": "captures/x.pbrun.json", "title": "...",
               "mode": "...", "p1": "...", "p2": "...", "seed": 0,
               "ticks": 0, "engine_commit": "...", "captured_at": "...",
               "size_mb": 0.0}]}

Rules honoured: fresh SHA fetched immediately before every PUT; 0.3 s sleep
between PUTs; blob-sha verification after each push.
"""

import argparse
import base64
import hashlib
import json
import os
import sys
import time
import urllib.request

REPO = "workingdanielferreira-create/Project_Behavior"
API = f"https://api.github.com/repos/{REPO}/contents/"
INDEX_PATH = "captures/index.json"
INDEX_VERSION = "cockpit_index v1"


def _token():
    tok = os.environ.get("GH_TOKEN", "")
    if not tok:
        sys.exit("set GH_TOKEN in the environment (never hardcode it here — "
                 "GitHub push protection rejects files containing tokens)")
    return tok


def req(url, method="GET", body=None):
    r = urllib.request.Request(
        url, method=method,
        data=json.dumps(body).encode() if body else None,
        headers={"Authorization": f"token {_token()}",
                 "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def blob_sha(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def put(path, data, message):
    st, cur = req(API + path)                 # fresh SHA, always
    body = {"message": message,
            "content": base64.b64encode(data).decode()}
    if st == 200:
        body["sha"] = cur["sha"]
    st, resp = req(API + path, "PUT", body)
    if st not in (200, 201):
        sys.exit(f"PUT {path} failed: {st} {str(resp)[:200]}")
    if resp["content"]["sha"] != blob_sha(data):
        sys.exit(f"PUT {path}: blob verification FAILED")
    print(f"pushed {path} ({len(data)/1e6:.1f} MB, verified)")
    time.sleep(0.3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True, help="local bundle file")
    ap.add_argument("--file", required=True,
                    help="repo path, e.g. captures/beam_debug.pbrun.json")
    ap.add_argument("--title", required=True)
    a = ap.parse_args()

    data = open(a.bundle, "rb").read()
    meta = json.loads(data)["meta"]
    put(a.file, data, f"cockpit: publish run {a.file}")

    st, cur = req(API + INDEX_PATH)           # fresh index read
    if st == 200:
        index = json.loads(base64.b64decode(cur["content"]).decode())
    else:
        index = {"version": INDEX_VERSION, "runs": []}

    entry = dict(file=a.file, title=a.title, mode=meta["mode"],
                 p1=meta["p1"], p2=meta.get("p2"), seed=meta["seed"],
                 ticks=meta["ticks"],
                 engine_commit=meta.get("engine_commit", "unknown"),
                 captured_at=meta.get("captured_at", ""),
                 size_mb=round(len(data) / 1e6, 1))
    index["runs"] = [r for r in index["runs"] if r["file"] != a.file]
    index["runs"].insert(0, entry)            # newest first
    put(INDEX_PATH, json.dumps(index, indent=1).encode(),
        f"cockpit: index {a.file}")


if __name__ == "__main__":
    main()
