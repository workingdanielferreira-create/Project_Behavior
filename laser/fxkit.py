"""
FX Kit runtime — the game's port of tools/fx/studio/fxkit.js (pb_fxkit v2).

FX Studio authors every effect of an image character (characters/<name>/
<name>.fxkit.json).  This module plays them in game exactly as the Studio
previews them: same fixed 16 ms tick, same mulberry32 random streams, same
maths for every primitive, motion, entry set and path, and the same "the
shape that's drawn is the shape that hits" damage rule.  fxkit.js is the
reference; keep the two in step (see its PORTING CONTRACT).

Game side (bottom of this file): one FxDriver per figure whose character
carries an FX file.  CombatSystem ticks it every tick (Solo and Battle
alike); Figure.draw paints its "behind" layer before the sprite and its
"front" layer after.  The action being played and its frame come from the
same state Figure._current_frame uses to pick the sprite, so FX stay locked
to the keyframes on screen.  Damage in Battle is queued on the side
(SideState.fx_hits) and delivered to the opposing fighter by
World.refresh_battle at the start of the next tick — the same one-tick
boundary the cross-side knockback uses.
"""

import math
import re

from PyQt5.QtCore import Qt, QPointF, QRectF
from PyQt5.QtGui import QColor, QPen, QPainter, QPainterPath, QRadialGradient

from . import config

TICK_MS = 16
TICK_S = TICK_MS / 1000.0
D = math.pi / 180.0
M32 = 0xFFFFFFFF
INF = float("inf")


def trunc(v):
    return int(v)


def jround(v):
    """Math.round: halves round up (Python's round() rounds half to even)."""
    return int(math.floor(v + 0.5))


def imul(a, b):
    return ((a & M32) * (b & M32)) & M32


# ---------------------------------------------------------------- random
class Rng:
    """mulberry32 — identical stream to FXK.rng."""
    __slots__ = ("a",)

    def __init__(self, seed):
        self.a = seed & M32

    def __call__(self):
        self.a = (self.a + 0x6D2B79F5) & M32
        t = self.a
        t = imul(t ^ (t >> 15), t | 1)
        t ^= (t + imul(t ^ (t >> 7), t | 61)) & M32
        return ((t ^ (t >> 14)) & M32) / 4294967296.0

    def uniform(self, lo, hi):
        return lo + (hi - lo) * self()


def hash32(s):
    h = 0x811C9DC5
    for ch in str(s):
        h ^= ord(ch)
        h = imul(h, 0x01000193)
    return h & M32


# ---------------------------------------------------------------- colour
def hex_rgb(h, d):
    if not isinstance(h, str):
        return d
    h = h.replace("#", "")
    if len(h) != 6:
        return d
    try:
        return [int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)]
    except ValueError:
        return d


def qcolor(c, a=255):
    return QColor(max(0, min(255, trunc(c[0]))), max(0, min(255, trunc(c[1]))),
                  max(0, min(255, trunc(c[2]))), max(0, min(255, trunc(a))))


def color_at(fx, inst, t, lut):
    c = fx["color"]
    if c["mode"] == "palette":
        idx = trunc((((t + inst.flow + (c.get("lut_offset") or 0)) % 1) + 1) % 1 * 256) & 255
        return lut[idx]
    c1 = hex_rgb(c.get("c1"), [255, 255, 255])
    if c["mode"] == "gradient":
        c2 = hex_rgb(c.get("c2"), c1)
        sf = 0 if c.get("start_fraction") is None else float(c["start_fraction"])
        if t <= sf:
            return c1
        k = (t - sf) / max(1e-6, 1 - sf)
        return [c1[0] + (c2[0] - c1[0]) * k, c1[1] + (c2[1] - c1[1]) * k, c1[2] + (c2[2] - c1[2]) * k]
    return c1


def color_pair(fx, lut):
    c = fx["color"]
    if c["mode"] == "palette":
        a = trunc(128 if c.get("lut_index") is None else c["lut_index"]) & 255
        b = trunc(a if c.get("lut_index2") is None else c["lut_index2"]) & 255
        return [list(lut[a]), list(lut[b])]
    c1 = hex_rgb(c.get("c1"), [255, 255, 255])
    return [c1, hex_rgb(c.get("c2"), c1) if c["mode"] == "gradient" else c1]


# ---------------------------------------------------------------- geometry
def angle_deg_qt(dx, dy):
    return math.atan2(-dy, dx) / D


def norm(dx, dy):
    d = math.sqrt(dx * dx + dy * dy)
    return [dx / d, dy / d] if d > 0.001 else [1.0, 0.0]


def rot(v, deg):
    c, s = math.cos(deg * D), math.sin(deg * D)
    return [v[0] * c - v[1] * s, v[0] * s + v[1] * c]


def seg_dist(px, py, x0, y0, x1, y1):
    dx, dy = x1 - x0, y1 - y0
    L = dx * dx + dy * dy
    t = ((px - x0) * dx + (py - y0) * dy) / L if L > 0 else 0
    t = max(0.0, min(1.0, t))
    ex, ey = x0 + dx * t - px, y0 + dy * t - py
    return math.sqrt(ex * ex + ey * ey)


# ---------------------------------------------------------------- schema
PRIMS = ["ribbon", "arc", "beam", "sprite", "particles", "glow", "ghost", "weapon"]
PARAM_DEFAULTS = {
    "ribbon": dict(max_points=50, min_dist=2, decay=2, taper=True, w_tail=1, w_head=5, alpha=220, head_glow_r=1, head_dot_r=1),
    "arc": dict(radius=42, span=170, width=6.5, tail=0.95, segs=16, grow=0.85, core_alpha=0.7, core_width=0.3, orient="motion",
                angle_deg=0, placement="anchor", back=51, lead=26),
    "beam": dict(length=200, w_start0=6, w_start1=6, w_end0=2, w_end1=2, segments=1, glow=0, glow_color="", pulse_hz=0,
                 jitter=0, detach_ticks=0, grow_ticks=0),
    "sprite": dict(shape="orb", radius=3, stretch=1, hot=False, halo=False, fade=True, trail_len=5),
    "particles": dict(mode="burst", count=12, rate_per_s=60, angle_deg=0, spread_deg=30, speed_min=50, speed_max=150, gravity=0,
                      drag=1, size_min=3, size_max=3, size_over_life="shrink", life_min_ms=200, life_max_ms=400),
    "glow": dict(r_start=6, r_end=6, a_center=140, a_mid=60, mid=0.4, core_r=0, fade="out", pulse_hz=0),
    "ghost": dict(interval=2, ghost_life=14, alpha=150, max=12),
    "weapon": dict(to_anchor="wtip", width=6),
}
MOTION_DEFAULTS = dict(kind="attached", aim="target", angle_deg=0, aim_offset_deg=0, speed=8, turn_deg=6, amplitude=55,
                       freq=0.18, orbit_rx=46, orbit_ry=46, orbit_deg=1.12, path="")
COLOR_DEFAULTS = dict(mode="palette", lut_index=128, lut_index2=128, lut_offset=0, flow_speed=0.008, c1="#ffffff",
                      c2="#ff2200", start_fraction=0)
BATTLE_DEFAULTS = dict(deals_damage=False, damage=1, pierce=False, rehit_ticks=0, knockback=0)
ACTION_DEFAULTS = dict(logic="any", cooldown_ms=0, conditions=[], chain_next="", chain_reset_ms=1000, fx_continuous=False,
                       movement="stand", move_speed_pct=100, anim_loops=1)
ENTRY_DEFAULTS = dict(name="entry points", base="figure", mode="simultaneous", interval_ticks=6, points=[])
PATH_DEFAULTS = dict(name="path", points=[[0, 0]], smooth=True, ticks=30, orient="facing", end="stop", follow=False)


def _fill(dst, default):
    import copy
    for k, v in default.items():
        if k not in dst:
            dst[k] = copy.deepcopy(v)
    return dst


def normalize(fx):
    if fx.get("prim") not in PRIMS:
        fx["prim"] = "glow"
    _fill(fx, dict(name=fx["prim"], tag="", enabled=True, start_frame=0, end_frame=-1, life_ticks=0, continuous=False,
                   anchor="figure", offset=[0, 0], layer="front", blend="normal"))
    fx["emit"] = _fill(dict(fx.get("emit") or {}), dict(every_ticks=0, count=1, fan_deg=0))
    fx["motion"] = _fill(dict(fx.get("motion") or {}), MOTION_DEFAULTS)
    fx["color"] = _fill(dict(fx.get("color") or {}), COLOR_DEFAULTS)
    fx["params"] = _fill(dict(fx.get("params") or {}), PARAM_DEFAULTS[fx["prim"]])
    fx["battle"] = _fill(dict(fx.get("battle") or {}), BATTLE_DEFAULTS)
    if fx["prim"] == "ghost":
        fx["battle"]["deals_damage"] = False
    if fx["prim"] == "weapon":
        fx["motion"]["kind"] = "attached"
    fx.setdefault("id", "E" + str(id(fx)))
    return fx


def normalize_action(cfg):
    cfg = _fill(dict(cfg or {}), ACTION_DEFAULTS)
    return cfg


def normalize_entry_set(e):
    e = _fill(dict(e or {}), ENTRY_DEFAULTS)
    e["points"] = [[float(p[0] or 0), float(p[1] or 0)] for p in (e.get("points") or [])]
    return e


def normalize_path(p):
    p = _fill(dict(p or {}), PATH_DEFAULTS)
    p["points"] = [[float(q[0] or 0), float(q[1] or 0)] for q in (p.get("points") or [])] or [[0.0, 0.0]]
    p["points"][0] = [0.0, 0.0]
    p["ticks"] = max(1, jround((float(p.get("ticks") or 1))))
    return p


def action_kind(name):
    if name in ("idle", "run"):
        return "locomotion"
    if re.match(r"^attack_normal", name or ""):
        return "attack"
    return "triggered"


def can_continue(fx):
    return fx["prim"] != "arc" and fx["motion"]["kind"] in ("attached", "static", "orbit", "path")


def is_continuous(fx):
    return bool(fx.get("continuous")) and can_continue(fx)


def life_t(inst):
    return min(1.0, inst.age / max(1, inst.win if inst.cont else inst.life))


# ---------------------------------------------------------------- entry sets / paths
def lib_find(host, key, ident):
    lib = host.lib
    if not lib or not ident:
        return None
    for it in lib.get(key) or []:
        if it.get("id") == ident:
            return it
    return None


def entry_set_of(fx, host):
    a = fx.get("anchor")
    if not isinstance(a, str) or not a.startswith("set:"):
        return None
    e = lib_find(host, "entry_sets", a[4:])
    return e if e and e["points"] else None


def entry_point(eset, k, host):
    b = host.anchor(eset.get("base") or "figure")
    q = eset["points"][k] if k < len(eset["points"]) else [0, 0]
    return [b[0] + q[0] * host.facing, b[1] + q[1]]


def anchor_pos(fx, host, ep=None):
    eset = entry_set_of(fx, host)
    a = fx.get("anchor")
    if eset:
        p = entry_point(eset, (ep if ep is not None else 0) % len(eset["points"]), host)
    elif isinstance(a, str) and a.startswith("set:"):
        p = host.anchor("figure")
    else:
        p = host.anchor(a)
    off = fx.get("offset") or [0, 0]
    return [p[0] + float(off[0] or 0) * host.facing, p[1] + float(off[1] or 0)]


def path_line(path):
    P = path["points"]
    if len(P) < 2:
        return {"pts": [[0, 0], [0, 0]], "cum": [0, 0], "len": 0}
    if not path.get("smooth") or len(P) < 3:
        pts = [list(q) for q in P]
    else:
        pts = []
        for i in range(len(P) - 1):
            p0, p1, p2, p3 = P[max(0, i - 1)], P[i], P[i + 1], P[min(len(P) - 1, i + 2)]
            for k in range(12):
                t = k / 12.0
                t2, t3 = t * t, t * t * t
                pts.append([0.5 * (2 * p1[0] + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                                   + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3),
                            0.5 * (2 * p1[1] + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                                   + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)])
        pts.append(list(P[-1]))
    cum = [0.0]
    for j in range(1, len(pts)):
        cum.append(cum[-1] + math.hypot(pts[j][0] - pts[j - 1][0], pts[j][1] - pts[j - 1][1]))
    return {"pts": pts, "cum": cum, "len": cum[-1]}


def path_at(pl, u):
    n = len(pl["pts"])
    d = max(0.0, min(1.0, u)) * pl["len"]
    i = 1
    while i < n - 1 and pl["cum"][i] < d:
        i += 1
    a, b = pl["pts"][i - 1], pl["pts"][i]
    seg = pl["cum"][i] - pl["cum"][i - 1]
    f = (d - pl["cum"][i - 1]) / seg if seg > 1e-9 else 0.0
    return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f], norm(b[0] - a[0], b[1] - a[1])


def path_matrix(path, host, d):
    f = host.facing
    last = path["points"][-1]
    if path.get("orient") != "aim" or (not last[0] and not last[1]):
        return [f, 0, 0, 1]
    th = math.atan2(d[1], d[0]) - math.atan2(last[1], last[0] * f)
    c, s = math.cos(th), math.sin(th)
    return [c * f, -s, s * f, c]


def path_step(inst, host):
    path, pl = inst.path, inst.pl
    k = inst.age / path["ticks"]
    if path.get("follow"):
        inst.po = anchor_pos(inst.fx, host, inst.ep)
    if path.get("end") == "loop":
        k = k - math.floor(k)
    if k > 1 and path.get("end") == "continue" and pl["len"] > 0:
        e, ld = path_at(pl, 1)
        local = [e[0] + ld[0] * (k - 1) * pl["len"], e[1] + ld[1] * (k - 1) * pl["len"]]
    else:
        local, ld = path_at(pl, k)
    M = inst.pm
    inst.x = inst.po[0] + M[0] * local[0] + M[1] * local[1]
    inst.y = inst.po[1] + M[2] * local[0] + M[3] * local[1]
    wd = norm(M[0] * ld[0] + M[1] * ld[1], M[2] * ld[0] + M[3] * ld[1])
    inst.dir = wd


# ---------------------------------------------------------------- instances
def aim_dir(fx, host, x, y):
    m, f = fx["motion"], host.facing
    if m["aim"] == "target":
        return norm(host.target[0] - x, host.target[1] - y)
    if m["aim"] == "angle":
        return [math.cos(m["angle_deg"] * D) * f, math.sin(m["angle_deg"] * D)]
    if m["aim"] == "weapon":
        return [math.sin(host.wang * D) * f, -math.cos(host.wang * D)]
    return [float(f), 0.0]


class Inst:
    __slots__ = ("fx", "x", "y", "px", "py", "vx", "vy", "dir", "age", "life", "seed", "r", "flow", "dead", "hist",
                 "trail", "parts", "ghosts", "acc", "facing", "orbitA", "phase", "zx", "zy", "hits", "last_hit", "ep",
                 "path", "pl", "po", "pm", "centre_deg", "x2", "y2", "cont", "win", "open", "hit_targets")

    def __init__(self):
        self.path = None
        self.cont = False
        self.win = 1
        self.open = False
        self.x2 = self.y2 = 0.0
        self.centre_deg = 0.0


def emit_particles(inst, fx, host, n):
    P, cp = fx["params"], color_pair(fx, host.lut)
    spread, base = P["spread_deg"] * D, P["angle_deg"] * D
    if inst.facing < 0:
        base = math.pi - base
    smin = float(P["speed_min"])
    smax = max(smin, float(P["speed_max"]))
    s0 = max(0.5, float(P["size_min"]))
    s1 = max(s0, float(P["size_max"]))
    l0 = max(1.0, float(P["life_min_ms"]))
    l1 = max(l0, float(P["life_max_ms"]))
    for _ in range(n):
        a = base + inst.r.uniform(-spread / 2, spread / 2)
        spd = inst.r.uniform(smin, smax) if smax > smin else smin
        life_ms = inst.r.uniform(l0, l1)
        inst.parts.append(dict(x=inst.x, y=inst.y, vx=math.cos(a) * spd, vy=math.sin(a) * spd, age=0,
                               life=max(1, trunc(life_ms / TICK_MS)), s0=s0, s1=s1, rgb1=cp[0], rgb2=cp[1], hits=0,
                               last_hit=-1e9))


def spawn(fx, host, window_ticks, seed, idx, n, ep):
    m = fx["motion"]
    p = anchor_pos(fx, host, ep)
    d = aim_dir(fx, host, p[0], p[1])
    if n > 1 and fx["emit"]["fan_deg"]:
        d = rot(d, (-fx["emit"]["fan_deg"] / 2 + fx["emit"]["fan_deg"] * idx / (n - 1)) * host.facing)
    if m["aim_offset_deg"]:
        d = rot(d, m["aim_offset_deg"] * host.facing)
    life = fx["life_ticks"] if fx["life_ticks"] > 0 else max(1, window_ticks)
    inst = Inst()
    inst.fx = fx
    inst.x, inst.y = p[0], p[1]
    inst.px, inst.py = p[0], p[1]
    inst.vx = inst.vy = 0.0
    inst.dir = d
    inst.age = 0
    inst.life = life
    inst.seed = seed & M32
    inst.r = Rng(seed)
    inst.flow = 0.0
    inst.dead = False
    inst.hist, inst.trail, inst.parts, inst.ghosts = [], [], [], []
    inst.acc = 0.0
    inst.facing = host.facing
    inst.orbitA = inst.phase = inst.zx = inst.zy = 0.0
    inst.hits = 0
    inst.last_hit = -1e9
    inst.ep = ep
    spd = float(m["speed"] or 0)
    if m["kind"] == "path":
        inst.path = lib_find(host, "paths", m.get("path"))
        if inst.path:
            inst.pl = path_line(inst.path)
            inst.po = list(p)
            inst.pm = path_matrix(inst.path, host, d)
    if m["kind"] in ("travel", "homing", "zigzag"):
        inst.vx, inst.vy = d[0] * spd, d[1] * spd
    if m["kind"] == "zigzag":
        pr = [-inst.vy / spd, inst.vx / spd] if spd > 0.001 else [0, 1]
        inst.zx, inst.zy = pr[0] * m["amplitude"], pr[1] * m["amplitude"]
        inst.phase = math.pi * idx if n > 1 else 0.0
    if m["kind"] == "orbit":
        inst.orbitA = 360.0 * idx / max(1, n)
        inst.x = p[0] + math.cos(inst.orbitA * D) * m["orbit_rx"]
        inst.y = p[1] + math.sin(inst.orbitA * D) * m["orbit_ry"]
    if fx["prim"] == "arc":
        P = fx["params"]
        od = [math.cos(P["angle_deg"] * D) * host.facing, math.sin(P["angle_deg"] * D)] if P["orient"] == "angle" else d
        inst.centre_deg = angle_deg_qt(-od[1], od[0])
        tg = host.target
        if P["placement"] == "wrap_target":
            inst.x, inst.y = tg[0] - od[0] * P["back"], tg[1] - od[1] * P["back"]
        elif P["placement"] == "through_target":
            R = P["radius"]
            inst.x = tg[0] + od[1] * R - od[0] * P["lead"]
            inst.y = tg[1] - od[0] * R - od[1] * P["lead"]
    if fx["prim"] == "particles" and fx["params"]["mode"] == "burst":
        emit_particles(inst, fx, host, trunc(fx["params"]["count"]))
    if fx["prim"] == "weapon":
        e2 = host.anchor(fx["params"]["to_anchor"])
        inst.x2, inst.y2 = e2[0], e2[1]
    inst.px, inst.py = inst.x, inst.y
    return inst


def move_inst(inst, host):
    fx, m = inst.fx, inst.fx["motion"]
    inst.px, inst.py = inst.x, inst.y
    if m["kind"] == "attached":
        a = anchor_pos(fx, host, inst.ep)
        inst.x, inst.y = a[0], a[1]
    if m["kind"] == "path" and inst.path:
        path_step(inst, host)
        inst.vx, inst.vy = inst.x - inst.px, inst.y - inst.py
        return
    if fx["prim"] == "weapon":
        b2 = host.anchor(fx["params"]["to_anchor"])
        inst.x2, inst.y2 = b2[0], b2[1]
    elif m["kind"] == "travel":
        inst.x += inst.vx
        inst.y += inst.vy
    elif m["kind"] == "homing":
        spd = math.sqrt(inst.vx * inst.vx + inst.vy * inst.vy) or float(m["speed"] or 0)
        want = math.atan2(host.target[1] - inst.y, host.target[0] - inst.x)
        cur = math.atan2(inst.vy, inst.vx)
        da = want - cur
        while da > math.pi:
            da -= 2 * math.pi
        while da < -math.pi:
            da += 2 * math.pi
        lim = float(m["turn_deg"] or 0) * D
        cur += max(-lim, min(lim, da))
        inst.vx, inst.vy = math.cos(cur) * spd, math.sin(cur) * spd
        inst.x += inst.vx
        inst.y += inst.vy
    elif m["kind"] == "zigzag":
        lat = math.sin(inst.phase) * m["freq"]
        inst.x += inst.vx + inst.zx * lat
        inst.y += inst.vy + inst.zy * lat
        inst.phase += m["freq"]
    elif m["kind"] == "orbit":
        c = anchor_pos(fx, host, inst.ep)
        inst.orbitA += m["orbit_deg"]
        inst.x = c[0] + math.cos(inst.orbitA * D) * m["orbit_rx"]
        inst.y = c[1] + math.sin(inst.orbitA * D) * m["orbit_ry"]
    if m["kind"] in ("travel", "homing", "zigzag"):
        mdx, mdy = inst.x - inst.px, inst.y - inst.py
        if mdx * mdx + mdy * mdy > 1e-6:
            inst.dir = norm(mdx, mdy)
    elif fx["prim"] == "beam":
        d = aim_dir(fx, host, inst.x, inst.y)
        inst.dir = rot(d, m["aim_offset_deg"] * host.facing) if m["aim_offset_deg"] else d


def tick_inst(inst, host):
    fx, P = inst.fx, inst.fx["params"]
    active = inst.age < inst.life
    if active:
        if fx["prim"] in ("sprite", "beam"):
            inst.trail.append((inst.x, inst.y))
            while len(inst.trail) > max(0, trunc(P.get("trail_len") or 0)):
                inst.trail.pop(0)
        move_inst(inst, host)
    inst.flow = (inst.flow + float(fx["color"].get("flow_speed") or 0)) % 1
    prim = fx["prim"]
    if prim == "ribbon":
        h = inst.hist
        if active:
            moved = True
            if h:
                lx, ly = h[-1]
                dx, dy = inst.x - lx, inst.y - ly
                moved = dx * dx + dy * dy >= P["min_dist"] * P["min_dist"]
            if moved:
                h.append((inst.x, inst.y))
                while len(h) > P["max_points"]:
                    h.pop(0)
            mx, my = inst.x - inst.px, inst.y - inst.py
            if mx * mx + my * my < 0.01:
                for _ in range(int(P["decay"])):
                    if len(h) > 1:
                        h.pop(0)
        else:
            for _ in range(max(1, int(P["decay"]))):
                if h:
                    h.pop(0)
        if not active and len(h) <= 1:
            inst.dead = True
    elif prim == "particles":
        if active and P["mode"] == "stream":
            inst.acc += P["rate_per_s"] * TICK_S
            k = trunc(inst.acc)
            if k > 0:
                inst.acc -= k
                emit_particles(inst, fx, host, k)
        drag = float(P["drag"])
        for q in inst.parts:
            q["vx"] *= drag
            q["vy"] = q["vy"] * drag + P["gravity"] * TICK_S
            q["x"] += q["vx"] * TICK_S
            q["y"] += q["vy"] * TICK_S
            q["age"] += 1
        inst.parts = [q for q in inst.parts if q["age"] < q["life"]]
        if not active and not inst.parts:
            inst.dead = True
    elif prim == "ghost":
        if active and inst.age % max(1, trunc(P["interval"])) == 0 and len(inst.ghosts) < P["max"]:
            inst.ghosts.append({"snap": host.snapshot(), "x": inst.x, "y": inst.y, "facing": host.facing, "age": 0})
        for gh in inst.ghosts:
            gh["age"] += 1
        inst.ghosts = [gh for gh in inst.ghosts if gh["age"] < P["ghost_life"]]
        if not active and not inst.ghosts:
            inst.dead = True
    elif not active:
        inst.dead = True
    inst.age += 1


# ---------------------------------------------------------------- shapes (draw + hit)
def arc_segs(inst, ps):
    P, life, age, out = inst.fx["params"], inst.life, inst.age, []
    if age >= life:
        return out
    segs = trunc(P["segs"])
    half = P["span"] / 2.0
    start = inst.centre_deg - half
    step = P["span"] / segs
    half_life = life * P["grow"]
    if age <= half_life:
        tip, fade = age / half_life, 1.0
    else:
        tip, fade = 1.0, 1 - (age - half_life) / (life - half_life)
    for i in range(segs):
        st = (i + 0.5) / segs
        if st > tip:
            continue
        dft = tip - st
        if dft > P["tail"]:
            continue
        tt = 1 - dft / P["tail"]
        a = trunc(255 * (tt ** 0.6) * fade)
        if a < 4:
            continue
        out.append((start + i * step, step, P["width"] * (0.25 + 0.75 * tt) * ps, tt, a, st))
    return out


def beam_segs(inst, host, ps):
    fx, P, m = inst.fx, inst.fx["params"], inst.fx["motion"]
    fade = max(0.0, 1 - inst.age / inst.life)
    if fade <= 0:
        return None
    ux, uy = inst.dir
    hx, hy = inst.x, inst.y
    spd = math.sqrt(inst.vx * inst.vx + inst.vy * inst.vy)
    detach = P["detach_ticks"] if P["detach_ticks"] > 0 else 1e9
    if m["kind"] in ("attached", "static", "orbit") or spd < 0.0001:
        reach = P["length"] * (min(1.0, inst.age / P["grow_ticks"]) if P["grow_ticks"] > 0 else 1.0)
        hx, hy = inst.x + ux * reach, inst.y + uy * reach
    else:
        dist = spd * inst.age
        if inst.age < detach:
            reach = min(P["length"], dist)
        else:
            rd = min(P["length"], spd * detach)
            post = max(1, inst.life - detach)
            reach = max(0.0, rd * (1 - min(1.0, (inst.age - detach) / post)))
    if reach <= 0:
        return None
    prog = life_t(inst)
    wT = P["w_start0"] + (P["w_start1"] - P["w_start0"]) * prog
    wH = P["w_end0"] + (P["w_end1"] - P["w_end0"]) * prog
    pulse = 1.0
    if P["pulse_hz"] > 0:
        pulse = 0.65 + 0.35 * math.sin(2 * math.pi * P["pulse_hz"] * (inst.age * TICK_MS / 1000.0))
    c1, c2 = color_pair(fx, host.lut)
    segs = max(1, trunc(P["segments"]))
    jr = Rng((inst.seed + trunc(inst.age if inst.age != INF else 0)) & M32)
    out = []
    for i in range(segs):
        t0, t1 = i / segs, (i + 1) / segs
        x0, y0 = hx - ux * reach * t0, hy - uy * reach * t0
        x1, y1 = hx - ux * reach * t1, hy - uy * reach * t1
        if P["jitter"] > 0:
            j = (jr() * 2 - 1) * P["jitter"]
            x0 += -uy * j
            y0 += ux * j
            x1 += -uy * j
            y1 += ux * j
        out.append((x0, y0, x1, y1, (wH + (wT - wH) * t0) * ps,
                    [c2[0] + (c1[0] - c2[0]) * t0, c2[1] + (c1[1] - c2[1]) * t0, c2[2] + (c1[2] - c2[2]) * t0]))
    return out, fade * pulse


def _hit_shape(inst, tx, ty, hr, ps, host):
    prim, P = inst.fx["prim"], inst.fx["params"]
    if prim == "ribbon":
        h, n = inst.hist, len(inst.hist)
        for i in range(1, n):
            t = i / n
            w = (P["w_tail"] + (P["w_head"] - P["w_tail"]) * t if P["taper"] else P["w_head"]) * ps
            if seg_dist(tx, ty, h[i - 1][0], h[i - 1][1], h[i][0], h[i][1]) <= hr + w / 2:
                return True
        return False
    if prim == "arc":
        r2 = P["radius"] * ps
        for q in arc_segs(inst, ps):
            a0, a1 = q[0] * D, (q[0] + q[1]) * D
            if seg_dist(tx, ty, inst.x + r2 * math.cos(a0), inst.y - r2 * math.sin(a0),
                        inst.x + r2 * math.cos(a1), inst.y - r2 * math.sin(a1)) <= hr + q[2] / 2:
                return True
        return False
    if prim == "beam":
        b = beam_segs(inst, host, ps)
        if not b:
            return False
        for q in b[0]:
            if seg_dist(tx, ty, q[0], q[1], q[2], q[3]) <= hr + max(1, q[4]) / 2:
                return True
        return False
    if prim == "sprite":
        if inst.age >= inst.life:
            return False
        dx, dy = inst.x - tx, inst.y - ty
        return dx * dx + dy * dy <= hr * hr
    if prim == "glow":
        if inst.age >= inst.life:
            return False
        t = life_t(inst)
        gr = max(P["core_r"], P["r_start"] + (P["r_end"] - P["r_start"]) * t) * ps
        return math.hypot(inst.x - tx, inst.y - ty) <= hr + gr
    if prim == "weapon":
        if inst.age >= inst.life:
            return False
        return seg_dist(tx, ty, inst.x, inst.y, inst.x2, inst.y2) <= hr + P["width"] * ps / 2
    return False


def _can_hit(b, obj_hits, obj_last, now):
    return now - obj_last >= b["rehit_ticks"] if b["rehit_ticks"] > 0 else obj_hits == 0


def resolve_hits(inst, host, ps):
    """host.hurts = [(x, y, r, target_key)]; host.on_hit(inst, damage, dx, dy,
    knockback, target_key) once per hit.  A non-piercing hit ends the instance
    (a hit particle is removed instead)."""
    b = inst.fx["battle"]
    hurts = host.hurts
    if not b["deals_damage"] or not hurts or inst.dead:
        return
    now = inst.age
    if inst.fx["prim"] == "particles":
        keep = []
        for q in inst.parts:
            hit_key = None
            size = max(0.5, q["s0"])
            for (hx, hy, hr, key) in hurts:
                if math.hypot(q["x"] - hx, q["y"] - hy) <= hr + size / 2:
                    hit_key = key
                    break
            if hit_key is None or not _can_hit(b, q["hits"], q["last_hit"], now):
                keep.append(q)
                continue
            q["hits"] += 1
            q["last_hit"] = now
            d = norm(q["vx"], q["vy"])
            host.on_hit(inst, b["damage"], d[0], d[1], b["knockback"], hit_key)
            if b["pierce"]:
                keep.append(q)
        inst.parts = keep
        return
    if not _can_hit(b, inst.hits, inst.last_hit, now):
        return
    for (hx, hy, hr, key) in hurts:
        if _hit_shape(inst, hx, hy, hr, ps, host):
            inst.hits += 1
            inst.last_hit = now
            host.on_hit(inst, b["damage"], inst.dir[0], inst.dir[1], b["knockback"], key)
            if not b["pierce"]:
                inst.age = max(inst.age, inst.life)
            return


# ---------------------------------------------------------------- drawing (QPainter)
def _pen(color, width):
    pen = QPen(color)
    pen.setWidthF(max(0.0, width))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def _line(p, x0, y0, x1, y1):
    p.drawLine(trunc(x0), trunc(y0), trunc(x1), trunc(y1))


def _radial_ellipse(p, cx, cy, r, stops, ir):
    g = QRadialGradient(cx, cy, max(0.0001, r))
    for at, col in stops:
        g.setColorAt(at, col)
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawEllipse(trunc(cx - ir), trunc(cy - ir), ir * 2, ir * 2)
    p.setBrush(Qt.NoBrush)


def _draw_ribbon(p, inst, host, ps):
    fx, P, tl = inst.fx, inst.fx["params"], inst.hist
    n = len(tl)
    if n <= 1:
        return
    inv = 1.0 / n
    for i in range(1, n):
        t = i * inv
        c = color_at(fx, inst, t, host.lut)
        if P["taper"]:
            p.setPen(_pen(qcolor(c, P["alpha"] * t), (P["w_tail"] + (P["w_head"] - P["w_tail"]) * t) * ps))
        else:
            p.setPen(_pen(qcolor(c, P["alpha"]), P["w_head"] * ps))
        _line(p, tl[i - 1][0], tl[i - 1][1], tl[i][0], tl[i][1])
    hx, hy = trunc(tl[-1][0]), trunc(tl[-1][1])
    hc = [trunc(v) for v in color_at(fx, inst, 1, host.lut)]
    gr = P["head_glow_r"] * ps
    igr = trunc(gr)
    if igr > 0:
        _radial_ellipse(p, hx, hy, gr, [(0, qcolor(hc, 140)), (0.4, qcolor(hc, 60)), (1, qcolor(hc, 0))], igr)
    dr = P["head_dot_r"] * ps
    idr = trunc(dr)
    if idr > 0:
        _radial_ellipse(p, hx, hy, dr, [(0, QColor(255, 255, 255, 200)), (0.5, qcolor(hc, 180)), (1, qcolor(hc, 100))], idr)


def _draw_arc(p, inst, host, ps):
    fx, P = inst.fx, inst.fx["params"]
    r2 = P["radius"] * ps
    rect = QRectF(inst.x - r2, inst.y - r2, r2 * 2, r2 * 2)
    p.setBrush(Qt.NoBrush)
    for q in arc_segs(inst, ps):
        a0, step, a = q[0], q[1], q[4]
        c = color_at(fx, inst, q[5], host.lut) if fx["color"]["mode"] == "palette" else color_pair(fx, host.lut)[0]
        path = QPainterPath()
        path.arcMoveTo(rect, a0)
        path.arcTo(rect, a0, step)
        p.setPen(_pen(qcolor(c, a), q[2]))
        p.drawPath(path)
        p.setPen(_pen(QColor(255, 255, 255, max(0, min(255, trunc(a * P["core_alpha"])))),
                      P["width"] * P["core_width"] * (0.25 + 0.75 * q[3]) * ps))
        p.drawPath(path)


def _draw_beam(p, inst, host, ps):
    P = inst.fx["params"]
    b = beam_segs(inst, host, ps)
    if not b:
        return
    segs, am = b
    gc = hex_rgb(P["glow_color"], None) if P.get("glow_color") else None
    for q in segs:
        w, col = q[4], q[5]
        if P["glow"] > 0:
            p.setPen(_pen(qcolor(gc or [trunc(v) for v in col], 70 * am), w + P["glow"] * ps))
            _line(p, q[0], q[1], q[2], q[3])
        p.setPen(_pen(qcolor(col, 235 * am), max(1.0, w)))
        _line(p, q[0], q[1], q[2], q[3])


def _draw_sprite(p, inst, host, ps):
    from . import combat as _combat
    fx, P = inst.fx, inst.fx["params"]
    if inst.age >= inst.life:
        return
    fade = max(0.0, 1 - inst.age / inst.life) if P["fade"] else 1.0
    c = [trunc(v) for v in color_pair(fx, host.lut)[0]]
    hx, hy = trunc(inst.x), trunc(inst.y)
    pts, n = inst.trail, len(inst.trail)
    for i in range(1, n):
        t = i / n
        p.setPen(_pen(qcolor(c, 200 * t * fade), (1 + 2 * t) * ps))
        _line(p, pts[i - 1][0], pts[i - 1][1], pts[i][0], pts[i][1])
    spd2 = inst.vx * inst.vx + inst.vy * inst.vy
    p.save()
    p.translate(hx, hy)
    p.setOpacity(p.opacity() * fade)
    if P["shape"] == "bolt" and spd2 > 0.0001 and P["stretch"] > 1.001:
        pm, head_x, half_h = _combat.bolt_sprite(c[0], c[1], c[2], P["radius"], P["stretch"], bool(P["hot"]))
        p.rotate(math.degrees(math.atan2(inst.vy, inst.vx)))
        p.scale(ps, ps)
        p.drawPixmap(trunc(-head_x), trunc(-half_h), pm)
    elif P["shape"] == "bolt":
        pm, head_x, half_h = _combat.bolt_sprite(c[0], c[1], c[2], P["radius"], 1, bool(P["hot"]))
        p.scale(ps, ps)
        p.drawPixmap(-trunc(pm.width() / 2), -trunc(pm.height() / 2), pm)
    else:
        pm, half = _combat.bullet_sprite(c[0], c[1], c[2], P["radius"])
        p.scale(ps, ps)
        p.drawPixmap(-half, -half, pm)
    p.restore()
    if P["halo"]:
        ha = trunc((110 + 70 * math.sin(inst.age * 0.5)) * fade)
        if ha > 4:
            ihr = trunc(P["radius"] * 3.6 * ps)
            p.setBrush(Qt.NoBrush)
            p.setPen(_pen(qcolor(c, ha), 1.4))
            p.drawEllipse(QPointF(hx, hy), ihr, ihr)


def _draw_particles(p, inst, host, ps):
    from . import combat as _combat
    P = inst.fx["params"]
    base = p.opacity()
    for q in inst.parts:
        t = min(1.0, q["age"] / q["life"])
        s0, s1 = q["s0"], q["s1"]
        sol = P["size_over_life"]
        if sol == "shrink":
            size = s1 + (s0 - s1) * (1 - t)
        elif sol == "grow":
            size = s0 + (s1 - s0) * t
        elif sol == "pulse":
            size = s0 + (s1 - s0) * math.sin(min(1.0, t) * math.pi)
        else:
            size = s0
        size = max(0.5, size)
        r = max(0, min(255, trunc(q["rgb1"][0] + (q["rgb2"][0] - q["rgb1"][0]) * t)))
        g = max(0, min(255, trunc(q["rgb1"][1] + (q["rgb2"][1] - q["rgb1"][1]) * t)))
        b = max(0, min(255, trunc(q["rgb1"][2] + (q["rgb2"][2] - q["rgb1"][2]) * t)))
        pm, half = _combat.bullet_sprite(r, g, b, size / 2)
        p.save()
        p.translate(trunc(q["x"]), trunc(q["y"]))
        p.scale(ps, ps)
        p.setOpacity(base * max(0.0, 1 - t))
        p.drawPixmap(-half, -half, pm)
        p.restore()


def _draw_glow(p, inst, host, ps):
    fx, P = inst.fx, inst.fx["params"]
    if inst.age >= inst.life:
        return
    t = life_t(inst)
    c = [trunc(v) for v in color_pair(fx, host.lut)[0]]
    fade = P["fade"]
    k = 1 - t if fade == "out" else t if fade == "in" else math.sin(t * math.pi) if fade == "inout" else 1.0
    if inst.cont:
        k = t if fade == "in" else 1.0
    if P["pulse_hz"] > 0:
        k *= 0.65 + 0.35 * math.sin(2 * math.pi * P["pulse_hz"] * (inst.age * TICK_MS / 1000.0))
    hx, hy = trunc(inst.x), trunc(inst.y)
    gr = (P["r_start"] + (P["r_end"] - P["r_start"]) * t) * ps
    igr = trunc(gr)
    if igr > 0:
        _radial_ellipse(p, hx, hy, gr, [(0, qcolor(c, P["a_center"] * k)), (P["mid"], qcolor(c, P["a_mid"] * k)),
                                        (1, qcolor(c, 0))], igr)
    dr = P["core_r"] * ps
    idr = trunc(dr)
    if idr > 0:
        _radial_ellipse(p, hx, hy, dr, [(0, QColor(255, 255, 255, max(0, min(255, trunc(200 * k))))),
                                        (0.5, qcolor(c, 180 * k)), (1, qcolor(c, 100 * k))], idr)


def _draw_ghost(p, inst, host, ps):
    P = inst.fx["params"]
    c = tuple(trunc(v) for v in color_pair(inst.fx, host.lut)[0])
    for gh in inst.ghosts:
        a = P["alpha"] * (1 - gh["age"] / P["ghost_life"])
        if a > 1:
            host.draw_ghost(p, gh, c, a / 255.0)


_DRAW = {"ribbon": _draw_ribbon, "arc": _draw_arc, "beam": _draw_beam, "sprite": _draw_sprite,
         "particles": _draw_particles, "glow": _draw_glow, "ghost": _draw_ghost, "weapon": lambda *a: None}


def draw_inst(p, inst, host, ps):
    p.save()
    if inst.fx.get("blend") == "additive":
        p.setCompositionMode(QPainter.CompositionMode_Plus)
    _DRAW[inst.fx["prim"]](p, inst, host, ps or 1.0)
    p.restore()


# ---------------------------------------------------------------- player
class Player:
    """Plays every effect bound to one action in lock-step with its frames
    (FXK.Player).  `t` counts ticks since the action started; `t_prev` is the
    previous tick's value (the game can skip ahead when an attack's frames
    advance faster than 16 ms, so a start tick is 'crossed' rather than hit
    exactly)."""

    def __init__(self):
        self.insts = []
        self.clock = 0
        self.pending = []

    def reset(self):
        self.insts = []
        self.clock = 0
        self.pending = []

    @staticmethod
    def window(fx, frames, frame_ms):
        total = max(1, jround((frames * frame_ms / TICK_MS)))
        s = jround((max(0, fx["start_frame"]) * frame_ms / TICK_MS))
        e = total if fx["end_frame"] < 0 else jround(((min(frames - 1, fx["end_frame"]) + 1) * frame_ms / TICK_MS))
        return min(s, total - 1), max(s + 1, e), total

    def _spawn_job(self, j, host):
        for i in range(j["n"]):
            ep = j["ep"]
            seed = (hash32(j["fx"]["id"]) ^ imul(j["t"] + 1, 0x9E3779B1) ^ imul(i, 0x85EBCA6B)
                    ^ imul(0 if ep is None else ep + 1, 0xC2B2AE35)) & M32
            inst = spawn(j["fx"], host, max(1, j["win"]), seed, i, j["n"], ep)
            if j["tag"] == "cont":
                inst.cont = True
                inst.win = inst.life
                inst.life = INF
            else:
                inst.open = j["tag"] == "open"
            self.insts.append(inst)

    def _fire(self, fx, t, n, win, tag, host):
        eset = entry_set_of(fx, host)
        pts = len(eset["points"]) if eset else 1
        for k in range(pts):
            delay = k * max(0, trunc(eset["interval_ticks"])) if eset and eset.get("mode") == "sequential" else 0
            job = {"fx": fx, "t": t, "n": n, "win": win - delay, "ep": k if eset else None, "tag": tag,
                   "due": self.clock + delay}
            if delay > 0:
                self.pending.append(job)
            else:
                self._spawn_job(job, host)

    def tick(self, effects, host, t, frames, frame_ms, continuous=False, t_prev=None):
        # t_prev == t: the action is holding a frame (time did not advance),
        # so nothing new fires this tick; live instances still update.
        held = t_prev is not None and t_prev == t
        if t_prev is None or t_prev > t:
            t_prev = t - 1
        due = [j for j in self.pending if j["due"] <= self.clock]
        self.pending = [j for j in self.pending if j["due"] > self.clock]
        for j in due:
            if j["fx"].get("enabled", True) and j["fx"] in effects:
                self._spawn_job(j, host)
        for inst in self.insts:
            if inst.cont and (not inst.fx.get("enabled", True) or inst.fx not in effects or not is_continuous(inst.fx)):
                inst.dead = True
        for fx in (() if held else effects):
            if not fx.get("enabled", True):
                continue
            s, e, total = self.window(fx, frames, frame_ms)
            if is_continuous(fx):
                if t < s or any(q.fx is fx and q.cont and not q.dead and q.age < q.life for q in self.insts) \
                        or any(q["fx"] is fx for q in self.pending):
                    continue
                self._fire(fx, t, max(1, trunc(fx["emit"]["count"])), total - s, "cont", host)
                continue
            every = fx["emit"]["every_ticks"]
            periodic = every > 0 and s < t < e and (t - s) % every == 0
            fire = (t_prev < s <= t) or periodic
            if not fire:
                continue
            opn = fx["life_ticks"] <= 0 and e >= total
            if continuous and opn and not periodic and any(q.fx is fx and q.open and not q.dead for q in self.insts):
                continue
            self._fire(fx, t, max(1, trunc(fx["emit"]["count"])), e - t, "open" if opn else "", host)
        self.clock += 1
        ps = host.pscale or 1.0
        if continuous:
            for inst in self.insts:
                if inst.open and inst.age < inst.life:
                    inst.life = max(inst.life, inst.age + 2)
        for inst in self.insts:
            tick_inst(inst, host)
            resolve_hits(inst, host, ps)
        self.insts = [i for i in self.insts if not i.dead]

    def draw(self, p, host, layer):
        ps = host.pscale or 1.0
        for inst in self.insts:
            if inst.fx.get("layer", "front") == layer:
                draw_inst(p, inst, host, ps)


# ===========================================================================
# Game side
# ===========================================================================
class CharacterFx:
    """The FX file of one character, normalised once (cached on its mode)."""

    def __init__(self, char):
        pkg = char.get("_package") or {}
        fxk = char.get("_fxkit") or {}
        img = pkg.get("image") or {}
        space = fxk.get("space") or {}
        self.origin = list(space.get("image_origin_px") or img.get("origin_px") or [0, 0])
        head = float(space.get("head_px") or img.get("head_px") or 58)
        self.k = config.TARGET_HEAD_PX / max(1.0, head)          # game px per image px
        self.anchors = fxk.get("anchors") or pkg.get("anchors") or {}
        self.effects = [normalize(dict(e)) for e in (fxk.get("effects") or [])]
        self.by_action = {}
        for e in self.effects:
            self.by_action.setdefault(e.get("action") or "idle", []).append(e)
        self.settings = {k: normalize_action(v) for k, v in (fxk.get("action_settings") or {}).items()}
        self.lib = {"entry_sets": [normalize_entry_set(e) for e in (fxk.get("entry_sets") or [])],
                    "paths": [normalize_path(p) for p in (fxk.get("paths") or [])]}
        self.timing = {}
        for name, act in (char.get("actions") or {}).items():
            n = len(act.get("keyframes") or []) or 1
            fm = float(act.get("frame_ms") or 0) or float(act.get("duration_ms") or 100 * n) / n
            self.timing[name] = (n, fm)

    def anchor_px(self, action, ident, frame):
        row = (self.anchors.get(action) or {}).get(ident)
        if not row:
            return None
        frame = max(0, min(frame, len(row) - 1))
        for i in range(frame, -1, -1):
            if row[i]:
                return row[i]
        for i in range(frame + 1, len(row)):
            if row[i]:
                return row[i]
        return None


def character_fx(mode):
    """CharacterFx for a mode, or None when its character has no FX file."""
    char = getattr(mode, "character", None)
    if not char or not char.get("_fxkit"):
        return None
    cfx = getattr(mode, "_fxkit_cache", None)
    if cfx is None:
        cfx = CharacterFx(char)
        mode._fxkit_cache = cfx
    return cfx


def current_action(fig):
    """(action name, frame index) the figure is showing — the same choice
    Figure._current_frame makes for the sprite."""
    b, c, m, r = fig.render.bundle, fig.combat, fig.motion, fig.render
    if c.action_anim:
        ex = b.extra.get(c.action_anim)
        if ex and ex[0]:
            return c.action_anim, max(0, min(c.action_idx, len(ex[0]) - 1))
    if c.slashing and b.slash:
        return "attack_normal", min(c.slash_idx, len(b.slash) - 1)
    if m.bouncing and b.slide is not None:
        return "defend", 0
    if m.bounce_ending and b.slide2 is not None:
        return "defend", 1
    if r.is_moving and b.run:
        return "run", r.run_idx % len(b.run)
    if b.idle:
        return "idle", r.idle_idx % len(b.idle)
    return "run", r.run_idx % max(1, len(b.run))


class _Host:
    """What the runtime asks the game: anchors, facing, target, hurt circles."""

    def __init__(self, drv, fig, world):
        self.drv, self.fig, self.world = drv, fig, world
        self.facing = -1 if fig.transform.facing_left else 1
        self.pscale = fig._position_scale()
        self.lut = fig.lut
        self.lib = drv.cfx.lib
        self.wang = 90.0
        self.target = drv.target
        self.hurts = drv.hurts

    def anchor(self, name):
        fig, cfx, drv = self.fig, self.drv.cfx, self.drv
        if name == "figure" or not name:
            return [fig.x, fig.y]
        if name == "target":
            return list(self.target)
        p = cfx.anchor_px(drv.action, name, drv.frame)
        if p is None:
            return [fig.x, fig.y]
        k = cfx.k * self.pscale
        ox, oy = (p[0] - cfx.origin[0]) * k * self.facing, (p[1] - cfx.origin[1]) * k
        if fig.motion.rotate and fig.transform.angle:
            a = math.radians(fig.transform.angle)
            ox, oy = ox * math.cos(a) - oy * math.sin(a), ox * math.sin(a) + oy * math.cos(a)
        return [fig.x + ox, fig.y + oy]

    def snapshot(self):
        return self.fig._current_frame()

    def draw_ghost(self, p, gh, rgb, a):
        from . import combat as _combat
        frame = gh["snap"]
        if frame is None:
            return
        pm = _combat.silhouette(frame, rgb)
        p.save()
        p.setOpacity(p.opacity() * a)
        p.drawPixmap(trunc(gh["x"]) - pm.width() // 2, trunc(gh["y"]) - pm.height() // 2, pm)
        p.restore()

    def on_hit(self, inst, damage, dx, dy, knockback, key):
        self.drv.hits_out.append((key, float(damage), dx, dy, float(knockback or 0), inst.fx.get("tag", "")))


class FxDriver:
    """Per-figure FX playback for an image character with an FX file."""

    def __init__(self, cfx):
        self.cfx = cfx
        self.player = Player()
        self.action = None
        self.frame = 0
        self.t = 0
        self.t_prev = -1
        self.cycle = 0
        self.target = (0.0, 0.0)
        self.hurts = []
        self.hits_out = []
        self.host = None

    def _time_for(self, action):
        n, fm = self.cfx.timing.get(action, (1, 100.0))
        return n, fm

    def update(self, fig, world):
        # Action time follows the frame on screen: it advances one tick per
        # tick inside the frame's own span (frame_ms), jumps forward when the
        # engine's frames run ahead, holds when a frame is held, and starts
        # a new pass when the frames loop back (idle / run cycles).
        action, frame = current_action(fig)
        n, fm = self._time_for(action)
        f0 = jround(frame * fm / TICK_MS)
        f1 = max(f0, jround((frame + 1) * fm / TICK_MS) - 1)
        if action != self.action:
            self.action, self.cycle = action, 0
            self.t, self.t_prev = f0, -1
        elif frame < self.frame:
            self.cycle += 1
            self.t, self.t_prev = f0, -1
        else:
            self.t_prev = self.t
            self.t = min(max(self.t + 1, f0), f1)
        self.frame = frame
        # Target and hurt circles: the nearest opposing fighter in Battle
        # (its snapshot position), the cursor in Solo (no damage there).
        hurts = []
        if world.battle_mode and world.partner_figures:
            best = None
            for idx, pf in enumerate(world.partner_figures):
                d = (pf[0] - fig.x) ** 2 + (pf[1] - fig.y) ** 2
                if best is None or d < best[0]:
                    best = (d, pf)
                hurts.append((pf[0], pf[1], float(config.PROJ_HIT_RADIUS), (pf[0], pf[1])))
            self.target = (best[1][0], best[1][1])
        else:
            self.target = tuple(world.cursor)
        self.hurts = hurts
        host = _Host(self, fig, world)
        self.host = host
        cfg = self.cfx.settings.get(action) or normalize_action({})
        effects = self.cfx.by_action.get(action) or []
        self.player.tick(effects, host, self.t, n, fm, continuous=bool(cfg.get("fx_continuous")), t_prev=self.t_prev)

    def draw(self, p, fig, layer):
        if self.host is None or not self.player.insts:
            return
        self.host.fig = fig
        self.player.draw(p, self.host, layer)

    def take_hits(self):
        h, self.hits_out = self.hits_out, []
        return h


def update_figure(fig, world):
    """CombatSystem hook: tick this figure's FX (no-op without an FX file)."""
    cfx = character_fx(fig.mode)
    drv = getattr(fig, "fx", None)
    if cfx is None:
        if drv is not None:
            fig.fx = None
        return
    if drv is None or drv.cfx is not cfx:
        drv = FxDriver(cfx)
        fig.fx = drv
    drv.update(fig, world)
    hits = drv.take_hits()
    if hits and world.battle_mode:
        world.queue_fx_hits(hits)
