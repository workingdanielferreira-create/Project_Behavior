"""
pewpew skate frames — draws pewpew's skating actions in the package's own
style (solid #9FBCFF stick figure, dark pistols with a light outline) and
writes the frames plus their anchors into characters/pewpew/character.json.

    python tools/pewpew_skate_frames.py

Frames face right on a 224 x 224 canvas; the image centre (112, 112) is the
figure's position in game, as in every Rig Forge package.

The feel is loose and playful — a skater in the flow: an easy, fairly upright
posture with the chin up, a bouncy push-and-glide rhythm with the hips
swaying into each push, and arms / guns that lag a beat behind the body
(follow-through), so nothing moves stiffly at once.

  run                 skating forward, arms swinging loose for balance, a
                      pistol dangling from each hand.
  attack_normal       the same legs; both pistols out at the target, the guns
                      kicking alternately (near gun on frames 1, 5, 9, 13, far
                      gun on 3, 7, 11, 15), in step with the shots
                      pewpew.fxkit.json fires from each barrel every 9 ticks.
  skate_back_fire     attack_normal's upper body (same anchors, so the shots
                      still leave the barrels) on backward-skating legs; the
                      game swaps it in while he fires gliding away from the
                      target (movement.glide.backward_frames).
  attack_normal_2     a 360 spin on both skates, arms flung out wide, both
                      guns firing as they come round.
  twirl               skating forward, spinning the near pistol twice round
                      his trigger finger beside his head.

Every joint carries a depth (z: + toward the viewer) so the spin can turn the
whole figure about its vertical axis; the limbs are drawn back to front.
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
HIP_X, HIP_Y = 112.0, 117.0
THIGH, SHIN = 46.0, 47.0
UPPER, FORE = 31.0, 29.0
TORSO = 55.0                   # hip -> neck
HEAD_R = 15.0
LEAN = 19.0                    # easy forward lean from vertical, degrees
W_NEAR, W_FAR, W_TORSO = 11.0, 9.0, 11.0
Z_SIDE = 7.0                   # depth of the near (+) / far (-) shoulder and hip

STANCE = 0.66                  # share of the cycle a foot is on the ground

# action: (frames, frame_ms)
SPECS = {
    "run": (16, 32.0),               # 2 game ticks a frame: one stride = 512 ms
    "attack_normal": (16, 37.5),
    "skate_back_fire": (16, 37.5),   # matches attack_normal frame for frame
    "attack_normal_2": (16, 40.0),   # the spin: one turn in 640 ms
    "twirl": (16, 40.0),
}


def lerp(a, b, t):
    return a + (b - a) * t


def ease_inout(t):
    return t * t * (3 - 2 * t)


def wave(phase, lag=0.0, k=1):
    """sin over the stride cycle (k = beats per cycle), delayed by lag."""
    return math.sin(2 * math.pi * k * (phase - lag))


def foot_pos(p, back=False):
    """Foot (x offset from the hip, lift) for leg phase p: a long easy glide
    under the body, a smooth push out behind, then a light heel-flick
    recovery.  back=True mirrors it for skating backwards (the push goes out
    in front)."""
    p %= 1.0
    if p < STANCE:
        s = p / STANCE
        if s < 0.45:                                   # long glide
            x = lerp(18.0, 8.0, s / 0.45)
        else:                                          # smooth push
            u = (s - 0.45) / 0.55
            x = lerp(8.0, -52.0, u * u * (2 - u) * 0.5 + u * 0.5)
        lift = 0.0
    else:
        s = (p - STANCE) / (1.0 - STANCE)              # heel-flick recovery
        x = lerp(-52.0, 18.0, ease_inout(s))
        lift = math.sin(math.pi * min(1.0, s * 1.1) ** 0.6) * 38.0
    if back:      # backwards: short C-cuts out in front, feet kept low
        return -x * 0.7, lift * 0.45
    return x, lift


def ik(a, target, l1, l2, bend):
    """Two-bone IK in the side plane; bend = +1 puts the joint forward (+x)."""
    dx, dy = target[0] - a[0], target[1] - a[1]
    reach = math.hypot(dx, dy)
    d = max(1e-6, min(l1 + l2 - 1e-3, reach))
    base = math.atan2(dy, dx)
    cos_a = (l1 * l1 + d * d - l2 * l2) / (2 * l1 * d)
    off = math.acos(max(-1.0, min(1.0, cos_a)))
    ang = base - off * bend
    j = (a[0] + math.cos(ang) * l1, a[1] + math.sin(ang) * l1)
    if reach > l1 + l2:                                # clamp an over-reach
        k = (l1 + l2) / reach
        target = (a[0] + dx * k, a[1] + dy * k)
    return j, target


def pol(o, deg, length):
    """Point `length` from o at `deg` (0 = straight down, + = forward)."""
    r = math.radians(deg)
    return (o[0] + math.sin(r) * length, o[1] + math.cos(r) * length)


def P3(p, z):
    return (p[0], p[1], z)


def torso(phase, upright=0.0):
    """Hip, chest, neck, head and the shoulder / hip points for the stride:
    a bouncy double-beat bob, hips swaying into each push, the lean breathing
    with it, the head riding a beat late with the chin up."""
    bob = 5.5 * abs(math.sin(2 * math.pi * phase))       # bounce on each push
    sway = 3.0 * wave(phase, 0.1)
    hip = (HIP_X + sway, HIP_Y + bob)
    lean = LEAN - upright + 3.0 * wave(phase, 0.05, 2)
    neck = pol(hip, 180 - lean, TORSO)                   # 180 = straight up
    chest = pol(hip, 180 - lean, TORSO * 0.54)
    head_tilt = 180 - lean * 0.2 + 4.0 * wave(phase, 0.18, 2)   # chin up, late bob
    head = pol(neck, head_tilt, 19.0)
    return dict(hip=P3(hip, 0), chest=P3(chest, 0), neck=P3(neck, 0), head=P3(head, 0),
                shB=P3((neck[0], neck[1] + 1.0), 0),
                shL=P3((neck[0] + 3.0, neck[1] - 1.0), -Z_SIDE),
                shR=P3((neck[0] - 2.0, neck[1] + 1.5), Z_SIDE),
                hpL=P3((hip[0] + 1.5, hip[1] + 2.0), -Z_SIDE),
                hpR=P3((hip[0] - 1.0, hip[1] + 2.4), Z_SIDE))


def legs(j, phase, back=False):
    """Skating legs: near leg at phase, far leg half a cycle later."""
    for side, ph in (("R", phase), ("L", phase + 0.5)):
        hp = j["hp" + side]
        dx, lift = foot_pos(ph, back)
        kn, ft = ik(hp[:2], (HIP_X + dx, GROUND - lift), THIGH, SHIN, +1)
        j["kn" + side] = P3(kn, hp[2])
        j["ft" + side] = P3(ft, hp[2])


def arms_swing(j, phase):
    """Loose balance swing opposite the legs.  The forearm trails the upper
    arm and the pistol trails the forearm, so the hands whip through."""
    for side, sign in (("R", 1.0), ("L", -1.0)):
        sh = j["sh" + side]
        s = sign * wave(phase, STANCE - 0.25)
        s_late = sign * wave(phase, STANCE - 0.25 + 0.08)
        s_later = sign * wave(phase, STANCE - 0.25 + 0.16)
        a = 2.0 + 58.0 * s                               # degrees off straight down
        bend = 14.0 + 30.0 * max(0.0, s_late)            # elbow folds on the way up
        el = pol(sh[:2], a, UPPER)
        ha = pol(el, a + bend, FORE)
        j["el" + side] = P3(el, sh[2])
        j["ha" + side] = P3(ha, sh[2])
        # guns hang loose off the fingers and swing a beat late
        j["_gun" + side] = (a + bend - 25.0 + 30.0 * s_later, 1.0)


def arms_fire(j, frame):
    """Both pistols out at the target, the near arm locked straight, the far
    one a touch higher with a cocky bend; alternate recoil."""
    kick = {"R": 7.0 if frame % 4 == 0 else 0.0, "L": 7.0 if frame % 4 == 2 else 0.0}
    base = {"R": 82.0, "L": 100.0}
    bend = {"R": 4.0, "L": 12.0}
    for side in ("R", "L"):
        sh, k = j["sh" + side], kick[side]
        a = base[side] + k * 0.9
        el = pol(sh[:2], a, UPPER - k * 0.25)
        ha = pol(el, a + bend[side] - k * 0.3, FORE - k * 0.35)
        j["el" + side] = P3(el, sh[2])
        j["ha" + side] = P3(ha, sh[2])
        j["_gun" + side] = ((87.0 if side == "R" else 95.0) + k * 2.2, 1.0)


def pose(action, i, n):
    phase = i / n
    if action == "attack_normal_2":
        return spin_pose(i, n)
    upright = 7.0 if action in ("attack_normal", "skate_back_fire") else 0.0
    j = torso(phase, upright)
    legs(j, phase, back=(action == "skate_back_fire"))
    if action in ("attack_normal", "skate_back_fire"):
        arms_fire(j, i)
    elif action == "twirl":
        arms_swing(j, phase)
        # near hand up by the head, pistol spinning twice round the finger
        sh = j["shR"]
        el = pol(sh[:2], 112.0, UPPER)
        ha = pol(el, 170.0, FORE * 0.9)
        j["elR"], j["haR"] = P3(el, sh[2]), P3(ha, sh[2])
        j["_gunR"] = (90.0 - 720.0 * phase, 1.0)
        j["_twirl"] = True
    else:
        arms_swing(j, phase)
    return j


def spin_pose(i, n):
    """A full turn about the vertical axis on both skates, arms flung wide."""
    u = i / n
    theta = 2 * math.pi * ease_inout(u)          # wind in, whip round, settle
    j = torso(u, upright=10.0)
    hip = j["hip"]
    # feet together, gliding side by side, knees soft
    for side, z in (("R", Z_SIDE + 4), ("L", -Z_SIDE - 4)):
        hp = j["hp" + side]
        kn, ft = ik(hp[:2], (HIP_X + 6.0, GROUND - 2.0), THIGH, SHIN, +1)
        j["kn" + side] = P3(kn, z * 0.8)
        j["ft" + side] = P3(ft, z)
    # arms straight out to the sides (along z), slightly raised and forward
    for side, sgn in (("R", 1.0), ("L", -1.0)):
        sh = j["sh" + side]
        el = (sh[0] + 4.0, sh[1] - 4.0, sh[2] + sgn * UPPER * 0.95)
        ha = (sh[0] + 8.0, sh[1] - 9.0, sh[2] + sgn * (UPPER + FORE) * 0.95)
        j["el" + side], j["ha" + side] = el, ha
        j["_gun" + side] = (None, sgn)      # barrel continues the arm outward
    # turn every joint about the vertical axis through the hip
    c, s = math.cos(theta), math.sin(theta)
    for k, v in list(j.items()):
        if k.startswith("_"):
            continue
        x, y, z = v
        dx = x - hip[0]
        j[k] = (hip[0] + dx * c - z * s, y, dx * s + z * c)
    j["_spin"] = (c, s)
    return j


def gun_shape(hand, fx, fy, length=1.0):
    """Pistol outline at `hand` with the barrel along unit (fx, fy), the barrel
    foreshortened by `length`.  Returns (polygon points, barrel tip)."""
    gx, gy = -fy, fx                         # grip side: toward the ground
    if gy < 0:
        gx, gy = -gx, -gy

    def P(a, b):                             # a along barrel, b along grip
        a *= length
        return (hand[0] + fx * a + gx * b, hand[1] + fy * a + gy * b)

    pts = [P(-5, -3.2), P(23, -3.2), P(23, 2.4), P(3, 2.4), P(1.5, 11), P(-4.5, 11), P(-3, 2.4), P(-5, 2.4)]
    return pts, P(23, -0.4)


def gun_dir(j, side):
    """Barrel direction (unit, image plane) and foreshortening for a hand."""
    deg, sgn = j["_gun" + side]
    if deg is not None:
        r = math.radians(deg)
        return math.sin(r), math.cos(r), 1.0
    # spin: barrel continues elbow -> hand in 3D; project it
    el, ha = j["el" + side], j["ha" + side]
    vx, vy, vz = ha[0] - el[0], ha[1] - el[1], ha[2] - el[2]
    L = math.sqrt(vx * vx + vy * vy + vz * vz) or 1.0
    pl = math.hypot(vx, vy)
    if pl < 1e-3:
        return 1.0, 0.0, 0.25
    return vx / pl, vy / pl, max(0.25, pl / L)


SEGMENTS = [("hpL", "knL", W_FAR), ("knL", "ftL", W_FAR), ("shL", "elL", W_FAR), ("elL", "haL", W_FAR),
            ("hip", "neck", W_TORSO),
            ("hpR", "knR", W_NEAR), ("knR", "ftR", W_NEAR), ("shR", "elR", W_NEAR), ("elR", "haR", W_NEAR)]


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

    # Draw back to front.  In the spin by true depth; in side view the far
    # side, then the body, then the near side (each gun over its own arm).
    spin = "_spin" in j
    side_depth = {"L": -10.0, "R": 10.0}

    def depth(a, b=None):
        if spin:
            return (j[a][2] + j[b][2]) / 2.0 if b else j[a][2]
        return side_depth.get(a[-1], 0.0)

    tips = {}
    items = [(depth(a, b), "bone", (a, b, w)) for a, b, w in SEGMENTS]
    items.append((0.5 if spin else 0.0, "head", None))
    for side in ("L", "R"):
        items.append((depth("ha" + side) + 0.1, "gun", side))
    for _, kind, p in sorted(items, key=lambda t: t[0]):
        if kind == "bone":
            bone(j[p[0]][:2], j[p[1]][:2], p[2])
        elif kind == "head":
            h = S(j["head"])
            r = HEAD_R * SS
            d.ellipse([h[0] - r, h[1] - r, h[0] + r, h[1] + r], fill=BODY)
        else:
            fx, fy, ln = gun_dir(j, p)
            pts, tip = gun_shape(j["ha" + p][:2], fx, fy, ln)
            d.polygon([S(q) for q in pts], fill=GUN_FILL, outline=GUN_LINE, width=int(1.1 * SS))
            tips[p] = tip
    return im.resize((SIZE, SIZE), Image.LANCZOS), tips["R"], tips["L"]


ORDER = ["hip", "chest", "neck", "head", "shB", "shL", "shR", "elL", "elR", "haL", "haR",
         "hpL", "hpR", "knL", "knR", "ftL", "ftR", "wtip", "wtip2", "root"]


def build(action, n):
    files, anchors = [], {k: [] for k in ORDER}
    for i in range(n):
        j = pose(action, i, n)
        im, tip, tip2 = render(j)
        name = "%s_%02d.png" % (action, i + 1)
        im.save(os.path.join(PKG, name))
        files.append(name)
        j["wtip"], j["wtip2"] = tip, tip2
        j["root"] = (j["head"][0], j["head"][1] - 36.0)
        for k in ORDER:
            anchors[k].append([round(j[k][0], 2), round(j[k][1], 2)])
    return files, anchors


# how each generated action is triggered (the FX file decides the details)
TRIGGERS = {"run": "moving", "attack_normal": "in_range", "skate_back_fire": "",
            "attack_normal_2": "in_range", "twirl": ""}


def main():
    path = os.path.join(PKG, "character.json")
    with open(path, "r", encoding="utf-8") as f:
        man = json.load(f)
    old = set()
    for act in SPECS:
        old.update((man["actions"].get(act) or {}).get("frames") or [])
    new = set()
    for action, (n, fm) in SPECS.items():
        files, anchors = build(action, n)
        a = man["actions"].setdefault(action, {"trigger": TRIGGERS[action]})
        a["frames"] = files
        a["frame_ms"] = fm
        a["duration_ms"] = round(fm * n, 3)
        man["anchors"][action] = anchors
        new.update(files)
    for name in old - new:                       # frames no longer referenced
        p = os.path.join(PKG, name)
        if os.path.exists(p):
            os.remove(p)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(man, f, indent=1)
    print("wrote " + ", ".join("%d %s" % (n, a) for a, (n, _) in SPECS.items()) + " frames")


if __name__ == "__main__":
    sys.exit(main())
