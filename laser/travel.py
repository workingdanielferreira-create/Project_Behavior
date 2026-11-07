"""Per-action travel paths (FX Studio action Movement, Daniel 2026-11-07).

Pure maths, no Qt: the FX Studio mirror is FXK.travelPlan / travelAt in
tools/fx/studio/fxkit.js (same numbers).  laser/actions.py runs it.

Movements that travel to the target between the action's leap.start_frame
and leap.land_frame (all settings live on action_settings[action].leap):

  leap         straight hop onto the target (its own arc height settings)
  arc          a curved run: arc_radius_px = how far it swings out sideways,
               arc_curve_pct = hook (0 = symmetric C, 100 = swings out past
               the target and hooks back in)
  hit_retreat  in to the target, then out (retreat_px at return_angle_deg
               off straight back, 0 = back the way it came, + toward `side`).
               The in-leg ends as turn_frame starts (-1 = halfway); `flip`
               runs it out first, then in (the hit at land_frame)
  zigzag       zig_count zigs of zig_len_px at +-zig_angle_deg off the line to
               the target, then a last zag in; zig_turn sharp / smooth /
               inertia (zig_turn_pct = how round / how far it overshoots)
  flank        fake_len_px straight at fake_angle_deg (+ = toward `side`,
               - = the other way), then round the target flank_radius_px out
               on `side`, ending behind it facing it

Every movement: dist_px = distance from target along the final direction of
travel (0 = the hit point lands on the target, - = short, + = past it);
side = left / right / random (relative to the line to the target); hop_px =
an optional hop arc (each leg) for the non-leap ones.  Lengths are game px
at 100 %, times the fighter's position scale when it takes off.
"""
import math
import random

TRAVEL_MOVES = ("leap", "arc", "hit_retreat", "zigzag", "flank")
ZIG_TURNS = ("sharp", "smooth", "inertia")
SIDES = ("left", "right", "random")
_SAMPLES = 40          # points per curve piece


def _unit(x, y, fx=1.0):
    d = math.hypot(x, y)
    if d < 1e-6:
        return fx, 0.0, 0.0
    return x / d, y / d, d


def _left(dx, dy):
    """Left of travel direction (screen y down)."""
    return dy, -dx


def _cubic(p0, p1, p2, p3, n=_SAMPLES):
    out = []
    for i in range(1, n + 1):
        t = i / float(n)
        a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3
        out.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return out


def _quad(p0, p1, p2, n=_SAMPLES // 2):
    out = []
    for i in range(1, n + 1):
        t = i / float(n)
        a, b, c = (1 - t) ** 2, 2 * (1 - t) * t, t * t
        out.append((a * p0[0] + b * p1[0] + c * p2[0], a * p0[1] + b * p1[1] + c * p2[1]))
    return out


def side_sign(lp, rnd=None):
    s = lp.get("side") or "left"
    if s == "random":
        return 1.0 if (rnd or random.random)() < 0.5 else -1.0
    return -1.0 if s == "right" else 1.0


def _num(lp, k, d=0.0):
    try:
        return float(lp.get(k) if lp.get(k) is not None else d)
    except (TypeError, ValueError):
        return d


# ------------------------------------------------------------ shapes
def _arc(lp, s, sx, sy, px, py, ps):
    fx, fy, D = _unit(px - sx, py - sy)
    lx, ly = _left(fx, fy)
    lx, ly = lx * s, ly * s
    R = max(0.0, _num(lp, "arc_radius_px", 120)) * ps
    h = max(0.0, min(100.0, _num(lp, "arc_curve_pct", 0))) / 100.0
    k = 4.0 / 3.0
    p1 = (sx + fx * D * (1 / 3.0 + 0.5 * h) + lx * k * R * (1 - 0.5 * h),
          sy + fy * D * (1 / 3.0 + 0.5 * h) + ly * k * R * (1 - 0.5 * h))
    p2 = (sx + fx * D * (2 / 3.0 + 0.9 * h) + lx * k * R, sy + fy * D * (2 / 3.0 + 0.9 * h) + ly * k * R)
    return [(sx, sy)] + _cubic((sx, sy), p1, p2, (px, py))


def _corners(verts, style, k):
    """Polyline through verts with sharp / smooth / inertia corners."""
    out = [verts[0]]
    if style not in ("smooth", "inertia") or k <= 0:
        return list(verts)
    for i in range(1, len(verts) - 1):
        a, v, b = verts[i - 1], verts[i], verts[i + 1]
        ix, iy, li = _unit(v[0] - a[0], v[1] - a[1])
        ox, oy, lo = _unit(b[0] - v[0], b[1] - v[1])
        c = 0.45 * k * min(li, lo)
        p0 = (v[0] - ix * c, v[1] - iy * c)
        p3 = (v[0] + ox * c, v[1] + oy * c)
        out.append(p0)
        if style == "smooth":
            out += _quad(p0, v, p3)
        else:   # inertia: carries on past the corner, then swings into the next leg
            p1 = (v[0] + ix * c, v[1] + iy * c)
            p2 = (v[0] + ix * c * 0.5 + ox * c * 0.5, v[1] + iy * c * 0.5 + oy * c * 0.5)
            out += _cubic(p0, p1, p2, p3, _SAMPLES // 2)
    out.append(verts[-1])
    return out


def _zigzag(lp, s, sx, sy, px, py, ps):
    fx, fy, D = _unit(px - sx, py - sy)
    lx, ly = _left(fx, fy)
    lx, ly = lx * s, ly * s
    n = max(1, min(20, int(round(_num(lp, "zig_count", 3)))))
    th = math.radians(max(5.0, min(85.0, _num(lp, "zig_angle_deg", 45))))
    L = max(0.0, _num(lp, "zig_len_px", 120)) * ps
    fwd = L * math.cos(th) * (n - 0.5)
    if fwd > 0.85 * D and fwd > 1e-6:
        L *= 0.85 * D / fwd
    w = L * math.sin(th) / 2.0
    verts = [(sx, sy)]
    a = L * math.cos(th) / 2.0
    for i in range(n):
        b = w if i % 2 == 0 else -w
        verts.append((sx + fx * a + lx * b, sy + fy * a + ly * b))
        a += L * math.cos(th)
    verts.append((px, py))
    st = lp.get("zig_turn") or "sharp"
    return _corners(verts, st, max(0.0, min(100.0, _num(lp, "zig_turn_pct", 50))) / 100.0)


def _flank(lp, s, sx, sy, tx, ty, px, py, ps):
    fx, fy, _d = _unit(tx - sx, ty - sy)
    lx, ly = _left(fx, fy)
    lx, ly = lx * s, ly * s
    a = math.radians(_num(lp, "fake_angle_deg", -20))
    dx, dy = fx * math.cos(a) + lx * math.sin(a), fy * math.cos(a) + ly * math.sin(a)
    fl = max(0.0, _num(lp, "fake_len_px", 120)) * ps
    R = max(4.0, _num(lp, "flank_radius_px", 100) * ps)
    F = (sx + dx * fl, sy + dy * fl)
    M = (tx + lx * R, ty + ly * R)
    k1 = math.hypot(M[0] - F[0], M[1] - F[1]) / 3.0
    pts = [(sx, sy), F]
    pts += _cubic(F, (F[0] + dx * k1, F[1] + dy * k1), (M[0] - fx * k1, M[1] - fy * k1), M)
    pts += _cubic(M, (M[0] + fx * R * 1.3, M[1] + fy * R * 1.3), (px + fx * R * 1.3, py + fy * R * 1.3), (px, py))
    return pts


def _end_dir(pts):
    """Final travel direction of a polyline."""
    ex, ey = pts[-1]
    for q in reversed(pts[:-1]):
        dx, dy = ex - q[0], ey - q[1]
        if dx * dx + dy * dy > 1.0:
            return _unit(dx, dy)[:2]
    return None


def _face_of(dx, fallback):
    return (-1.0 if dx < 0 else 1.0) if abs(dx) > 0.15 else fallback


# ------------------------------------------------------------ plan
def plan(move, lp, sx, sy, tx, ty, ps, face0, hit_off, t0, t1, tturn=None, rnd=None):
    """The path for one take-off.  face0 = facing at take-off (+1 right / -1
    left), hit_off(face) -> (ox, oy) where the hit lands relative to the body,
    t0/t1 = take-off / arrival ms, tturn = attack & retreat turn ms.  Returns
    a dict: legs = [{pts, t0, t1, face}] (face "travel" = faces the way it
    moves, "lock" = holds `face`), face = facing at the hit, hop = hop px."""
    s = side_sign(lp, rnd)
    dist = _num(lp, "dist_px", 0) * ps
    hop = max(0.0, _num(lp, "hop_px", 0)) * ps
    fx, fy, _d = _unit(tx - sx, ty - sy, face0)

    def aim(dx, dy):
        f = _face_of(dx, _face_of(tx - sx, face0))
        ox, oy = hit_off(f)
        return tx - ox + dx * dist, ty - oy + dy * dist, f

    if move == "hit_retreat":
        if tturn is None:
            tturn = (t0 + t1) / 2.0
        tturn = max(t0 + 1.0, min(t1 - 1.0, tturn)) if t1 - t0 > 2 else (t0 + t1) / 2.0
        lx, ly = _left(fx, fy)
        a = math.radians(_num(lp, "return_angle_deg", 0))
        rx, ry = -fx * math.cos(a) + s * lx * math.sin(a), -fy * math.cos(a) + s * ly * math.sin(a)
        rl = max(0.0, _num(lp, "retreat_px", 150)) * ps
        if lp.get("flip"):
            r0 = (sx + rx * rl, sy + ry * rl)
            dx, dy, _ = _unit(tx - r0[0], ty - r0[1], face0)
            ex, ey, f = aim(dx, dy)
            legs = [dict(pts=[(sx, sy), r0], t0=t0, t1=tturn, face="lock"),
                    dict(pts=[r0, (ex, ey)], t0=tturn, t1=t1, face="lock")]
            return dict(legs=legs, face=f, hop=hop, hit_t=t1)
        ex, ey, f = aim(fx, fy)
        legs = [dict(pts=[(sx, sy), (ex, ey)], t0=t0, t1=tturn, face="lock"),
                dict(pts=[(ex, ey), (ex + rx * rl, ey + ry * rl)], t0=tturn, t1=t1, face="lock")]
        return dict(legs=legs, face=f, hop=hop, hit_t=tturn)

    if move == "flank":
        f = _face_of(-fx, face0)
        ox, oy = hit_off(f)
        ex, ey = tx - ox - fx * dist, ty - oy - fy * dist
        pts = _flank(lp, s, sx, sy, tx, ty, ex, ey, ps)
        return dict(legs=[dict(pts=pts, t0=t0, t1=t1, face="travel")], face=f, hop=hop, hit_t=t1)

    if move in ("arc", "zigzag"):
        shape = _arc if move == "arc" else _zigzag
        d0 = _end_dir(shape(lp, s, sx, sy, tx, ty, ps)) or (fx, fy)
        ex, ey, f = aim(d0[0], d0[1])
        pts = shape(lp, s, sx, sy, ex, ey, ps)
        return dict(legs=[dict(pts=pts, t0=t0, t1=t1, face="travel")], face=f, hop=hop, hit_t=t1)

    # leap: straight, faces the target it locked at take-off
    ex, ey, f = aim(fx, fy)
    return dict(legs=[dict(pts=[(sx, sy), (ex, ey)], t0=t0, t1=t1, face="lock")], face=f, hop=0.0, hit_t=t1)


def _along(pts, u):
    """Point at fraction u of the polyline's length, and the direction there."""
    if len(pts) < 2:
        return pts[0][0], pts[0][1], 0.0, 0.0
    segs, tot = [], 0.0
    for i in range(1, len(pts)):
        d = math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
        segs.append(d)
        tot += d
    if tot < 1e-6:
        return pts[-1][0], pts[-1][1], 0.0, 0.0
    want = max(0.0, min(1.0, u)) * tot
    for i, d in enumerate(segs):
        if want <= d or i == len(segs) - 1:
            k = want / d if d > 1e-9 else 1.0
            a, b = pts[i], pts[i + 1]
            return a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k, b[0] - a[0], b[1] - a[1]
        want -= d
    return pts[-1][0], pts[-1][1], 0.0, 0.0


def at(pl, t):
    """Where the body is at ms t: (x, ground y, hop lift, dx of travel,
    leg face mode, done)."""
    legs = pl["legs"]
    for i, lg in enumerate(legs):
        if t < lg["t1"] or i == len(legs) - 1:
            u = max(0.0, min(1.0, (t - lg["t0"]) / max(1.0, lg["t1"] - lg["t0"])))
            x, y, dx, _dy = _along(lg["pts"], u)
            lift = pl["hop"] * 4.0 * u * (1.0 - u)
            return x, y, lift, dx, lg["face"], (i == len(legs) - 1 and u >= 1.0)
    lg = legs[-1]
    return lg["pts"][-1][0], lg["pts"][-1][1], 0.0, 0.0, lg["face"], True


def guide(pl):
    """Every point of the planned route (Studio stage guide / wireframe)."""
    out = []
    for lg in pl["legs"]:
        out += lg["pts"]
    return out
