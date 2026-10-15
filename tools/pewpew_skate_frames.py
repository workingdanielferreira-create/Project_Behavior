"""
pewpew skate frames — draws pewpew's skating `run` loop and skate-and-shoot
`attack_normal` loop in the package's own style (solid #9FBCFF stick figure,
dark pistols with a light outline) and writes the frames plus their anchors
into characters/pewpew/character.json.

    python tools/pewpew_skate_frames.py

Frames face right on a 224 x 224 canvas; the image centre (112, 112) is the
figure's position in game, as in every Rig Forge package.  Legs run a
push-and-glide stride (each leg glides under the body, then pushes back and
out, then swings forward again, half a cycle apart); the torso leans into the
skate and bobs low on each push.

  run            arms swing for balance, opposite the legs, a pistol loose
                 in each hand.
  attack_normal  the same legs, both arms out front firing; the guns kick
                 alternately (near gun on frames 1, 5, 9, 13 and far gun on
                 3, 7, 11, 15), in step with the shots pewpew.fxkit.json
                 fires from each barrel every 9 ticks.
"""

import json
import math
import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "characters", "pewpew")

SIZE = 224
SS = 4                         # supersampling for smooth edges
BODY = (159, 188, 255, 255)    # #9FBCFF, the package's figure_colour
GUN_FILL = (27, 29, 32, 255)
GUN_LINE = (255, 255, 255, 150)

GROUND = 201.0                 # foot line (idle's near foot sits at y 201)
HIP_X, HIP_Y = 112.0, 121.0
THIGH, SHIN = 46.0, 47.0
UPPER, FORE = 31.0, 29.0
TORSO = 55.0                   # hip -> neck
HEAD_R = 15.0
LEAN = 28.0                    # torso lean forward from vertical, degrees
W_NEAR, W_FAR, W_TORSO = 11.0, 9.0, 11.0

N_RUN, RUN_MS = 16, 32.0         # 2 game ticks a frame: one stride cycle = 512 ms
N_ATK, ATK_MS = 16, 37.5

STANCE = 0.62                  # share of the cycle a foot is on the ground


def lerp(a, b, t):
    return a + (b - a) * t


def ease_in(t):
    return t * t


def ease_inout(t):
    return t * t * (3 - 2 * t)


def foot_pos(p):
    """Foot position for leg phase p in [0, 1): glide under the body, push
    back along the ground, then lift and swing forward."""
    p %= 1.0
    if p < STANCE:
        s = p / STANCE
        if s < 0.35:                                   # glide
            x = lerp(16.0, 6.0, s / 0.35)
        else:                                          # push back
            x = lerp(6.0, -60.0, ease_in((s - 0.35) / 0.65))
        return HIP_X + x, GROUND
    s = (p - STANCE) / (1.0 - STANCE)                  # recovery swing
    x = lerp(-60.0, 16.0, ease_inout(s))
    lift = math.sin(math.pi * min(1.0, s * 1.1) ** 0.7) * 34.0
    return HIP_X + x, GROUND - lift


def ik(a, target, l1, l2, bend):
    """Two-bone IK from a to target; bend = +1 puts the joint forward (+x)."""
    dx, dy = target[0] - a[0], target[1] - a[1]
    d = max(1e-6, min(l1 + l2 - 1e-3, math.hypot(dx, dy)))
    base = math.atan2(dy, dx)
    cos_a = (l1 * l1 + d * d - l2 * l2) / (2 * l1 * d)
    off = math.acos(max(-1.0, min(1.0, cos_a)))
    # y is down, so a negative angle offset swings the joint toward +x when
    # the limb points down.
    ang = base - off * bend
    j = (a[0] + math.cos(ang) * l1, a[1] + math.sin(ang) * l1)
    reach = math.hypot(dx, dy)
    if reach > l1 + l2:                                # clamp an over-reach
        k = (l1 + l2) / reach
        target = (a[0] + dx * k, a[1] + dy * k)
    return j, target


def pol(o, deg, length):
    """Point `length` from o at `deg` (0 = straight down, + = forward)."""
    r = math.radians(deg)
    return (o[0] + math.sin(r) * length, o[1] + math.cos(r) * length)


def pose(phase, shooting, frame):
    """All joints for one frame (image px)."""
    bob = 4.0 * (0.5 - 0.5 * math.cos(4 * math.pi * phase))   # low on each push
    hip = (HIP_X, HIP_Y + bob)
    lean = LEAN + 2.0 * math.sin(4 * math.pi * phase)
    neck = pol(hip, 180 - lean, TORSO)          # 180 = straight up
    chest = pol(hip, 180 - lean, TORSO * 0.54)
    head = pol(neck, 180 - lean * 0.45, 19.0)
    shb = (neck[0], neck[1] + 1.0)
    sh_far = (neck[0] + 4.0, neck[1] - 2.0)
    sh_near = (neck[0] - 3.0, neck[1] + 1.5)
    hp_far = (hip[0] + 2.0, hip[1] + 2.0)
    hp_near = (hip[0] - 1.0, hip[1] + 2.4)

    # legs: near leg at phase, far leg half a cycle later
    ft_near_t = foot_pos(phase)
    ft_far_t = foot_pos(phase + 0.5)
    kn_near, ft_near = ik(hp_near, ft_near_t, THIGH, SHIN, +1)
    kn_far, ft_far = ik(hp_far, ft_far_t, THIGH, SHIN, +1)

    if shooting:
        # both arms out front, level with the shoulders; alternate recoil
        kick_near = 7.0 if frame % 4 == 0 else 0.0
        kick_far = 7.0 if frame % 4 == 2 else 0.0
        a_near = 80.0 + kick_near * 0.9      # near gun a little low
        a_far = 101.0 + kick_far * 0.9       # far gun a little high

        el_near = pol(sh_near, a_near, UPPER - kick_near * 0.25)
        ha_near = pol(el_near, a_near + 4.0, FORE - kick_near * 0.35)
        el_far = pol(sh_far, a_far, UPPER - kick_far * 0.25)
        ha_far = pol(el_far, a_far + 4.0, FORE - kick_far * 0.35)
        gun_near_deg = 86.0 + kick_near * 2.2   # barrels near level, tip up on the kick
        gun_far_deg = 96.0 + kick_far * 2.2
    else:
        # balance swing, opposite the legs: the near arm is furthest forward
        # when the near foot is furthest back (end of its push).  The front
        # arm reaches forward with a soft elbow, the back arm trails almost
        # straight.
        s = math.cos(2 * math.pi * (phase - STANCE))
        a_near = 8.0 + 62.0 * s             # degrees from straight down, + forward
        a_far = 8.0 - 62.0 * s
        el_near = pol(sh_near, a_near, UPPER)
        el_far = pol(sh_far, a_far, UPPER)
        bend_near = 10.0 + 22.0 * max(0.0, s)
        bend_far = 10.0 + 22.0 * max(0.0, -s)
        ha_near = pol(el_near, a_near + bend_near, FORE)
        ha_far = pol(el_far, a_far + bend_far, FORE)
        # pistols continue the forearm line
        gun_near_deg = a_near + bend_near
        gun_far_deg = a_far + bend_far

    return dict(hip=hip, chest=chest, neck=neck, head=head, shB=shb,
                shL=sh_far, shR=sh_near, elL=el_far, elR=el_near,
                haL=ha_far, haR=ha_near, hpL=hp_far, hpR=hp_near,
                knL=kn_far, knR=kn_near, ftL=ft_far, ftR=ft_near,
                root=(head[0], head[1] - 36.0),
                _gun_near=gun_near_deg, _gun_far=gun_far_deg)


def gun_shape(hand, deg):
    """Pistol outline at `hand`, barrel along `deg` (pol convention).
    Returns (polygon points, barrel tip)."""
    r = math.radians(deg)
    fx, fy = math.sin(r), math.cos(r)            # barrel direction
    # "down" for the grip: the barrel direction turned a quarter toward the
    # ground side (+y when the barrel points forward).
    gx, gy = -fy, fx
    if gy < 0:
        gx, gy = -gx, -gy

    def P(a, b):                                 # a along barrel, b along grip
        return (hand[0] + fx * a + gx * b, hand[1] + fy * a + gy * b)

    pts = [P(-5, -3.2), P(23, -3.2), P(23, 2.4), P(3, 2.4), P(1.5, 11), P(-4.5, 11), P(-3, 2.4), P(-5, 2.4)]
    return pts, P(23, -0.4)


def render(j):
    W = SIZE * SS
    im = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    def S(p):
        return (p[0] * SS, p[1] * SS)

    def bone(a, b, w):
        d.line([S(a), S(b)], fill=BODY, width=int(round(w * SS)))
        r = w * SS / 2.0
        for p in (a, b):
            q = S(p)
            d.ellipse([q[0] - r, q[1] - r, q[0] + r, q[1] + r], fill=BODY)

    def gun(hand, deg):
        pts, tip = gun_shape(hand, deg)
        d.polygon([S(p) for p in pts], fill=GUN_FILL, outline=GUN_LINE, width=int(1.1 * SS))
        return tip

    # far side first, then body, then the near side on top
    tip2 = None
    bone(j["hpL"], j["knL"], W_FAR)
    bone(j["knL"], j["ftL"], W_FAR)
    bone(j["shL"], j["elL"], W_FAR)
    bone(j["elL"], j["haL"], W_FAR)
    tip2 = gun(j["haL"], j["_gun_far"])
    bone(j["hip"], j["neck"], W_TORSO)
    h = S(j["head"])
    r = HEAD_R * SS
    d.ellipse([h[0] - r, h[1] - r, h[0] + r, h[1] + r], fill=BODY)
    bone(j["hpR"], j["knR"], W_NEAR)
    bone(j["knR"], j["ftR"], W_NEAR)
    bone(j["shR"], j["elR"], W_NEAR)
    bone(j["elR"], j["haR"], W_NEAR)
    tip = gun(j["haR"], j["_gun_near"])
    return im.resize((SIZE, SIZE), Image.LANCZOS), tip, tip2


ORDER = ["hip", "chest", "neck", "head", "shB", "shL", "shR", "elL", "elR", "haL", "haR",
         "hpL", "hpR", "knL", "knR", "ftL", "ftR", "wtip", "wtip2", "root"]


def build(action, n, shooting):
    files, anchors = [], {k: [] for k in ORDER}
    for i in range(n):
        j = pose(i / n, shooting, i)
        im, tip, tip2 = render(j)
        name = "%s_%02d.png" % (action, i + 1)
        im.save(os.path.join(PKG, name))
        files.append(name)
        j["wtip"], j["wtip2"] = tip, tip2
        for k in ORDER:
            anchors[k].append([round(j[k][0], 2), round(j[k][1], 2)])
    return files, anchors


def main():
    path = os.path.join(PKG, "character.json")
    with open(path, "r", encoding="utf-8") as f:
        man = json.load(f)
    old = set()
    for act in ("run", "attack_normal"):
        old.update((man["actions"].get(act) or {}).get("frames") or [])
    specs = [("run", N_RUN, RUN_MS, False), ("attack_normal", N_ATK, ATK_MS, True)]
    for action, n, fm, shooting in specs:
        files, anchors = build(action, n, shooting)
        a = man["actions"][action]
        a["frames"] = files
        a["frame_ms"] = fm
        a["duration_ms"] = round(fm * n, 3)
        man["anchors"][action] = anchors
    new = set(man["actions"]["run"]["frames"]) | set(man["actions"]["attack_normal"]["frames"])
    for name in old - new:                       # frames no longer referenced
        p = os.path.join(PKG, name)
        if os.path.exists(p):
            os.remove(p)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(man, f, indent=1)
    print("wrote %d run + %d attack_normal frames" % (N_RUN, N_ATK))


if __name__ == "__main__":
    sys.exit(main())
