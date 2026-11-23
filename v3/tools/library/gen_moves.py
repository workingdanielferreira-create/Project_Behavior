"""Rig Forge 3D move library: the authored moves, rebuilt as MOBILE moves (Daniel 2026-11-23).

    python v3/tools/library/gen_moves.py            (re)writes every authored clip into v3/tools/library/moves.anim3d.json
    python v3/tools/library/gen_moves.py out.json   writes a scratch spec (previews)

Daniel's brief: a very mobile action game, so no tutorial-style "strike and return to guard": every move travels
(the fighter ends 1.5 - 4 m further on, V3 carries it there with root motion, glbody.js), starts already moving
and ends moving into the next thing. Kicks, forward <-> reverse grip switches mid-attack (`grip`), blade twirls
(`twirl`), spins that carry the body across the ground. Few keys, big pose changes: the tween fills the rest.

Body space: +Z = forward (the target), +X = the fighter's left, metres. Arms are designed by angle round the fighter
(deg: 0 = at the target, + = to the fighter's left) in BODY space and converted to chest space per key, so a sweep's
arc is exact whatever the torso does. Feet are placed on the ground with the travel included; the hips sit over the
feet (or over one foot on a pivot / kick) and lift off the ground on jumps.
"""
import json, math, os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from anim3d import rot_euler

ANKLE = 0.104
WIDE = 2.6          # stance width (Daniel's references: wide, deep, one leg locked straight): every foot's distance from
                    # the travel line x this, so planted feet stay planted; the hips drop to let the legs reach
WRIST_OFF = 25.0    # deg a blade may lean off square to the arm (the wrist's comfortable bend)
LEG = 0.80          # usable leg reach hip joint -> ankle (m)


def r3(v): return [round(float(x), 3) for x in v]


def hdir(deg, y=0.0):
    a = math.radians(deg)
    v = np.array([math.sin(a), y, math.cos(a)])
    return v / np.linalg.norm(v)


def chest_M(hips_rot, spine):
    return rot_euler(*hips_rot) @ rot_euler(*spine)


def arm(M, hand_deg, blade_deg, h=0.0, elbow="fore", bslope=0.0, ext=0.5, grip=None, twirl=None, side=1):
    """Hand at angle hand_deg round the shoulder, ext m out, height h (0 = shoulder - 0.10); blade toward blade_deg
    (bslope = its rise). side 1 = right arm, -1 = left. grip "rev" = reverse grip (blade = where it points)."""
    reach = hdir(hand_deg) * ext + np.array([0, h - 0.10, 0])
    s = side
    if elbow == "fore":   el = np.array([0, -1, 0]) + hdir(hand_deg - 90 * s) * 0.35
    elif elbow == "back": el = np.array([0, -0.5, 0]) + hdir(hand_deg + 90 * s) * 0.6
    elif elbow == "up":   el = np.array([0, 0.35, 0]) + hdir(hand_deg - 100 * s) * 1.0
    elif elbow == "upb":  el = np.array([0, 0.35, 0]) + hdir(hand_deg + 100 * s) * 1.0
    elif elbow == "out":  el = np.array([0, -0.2, 0]) + hdir(hand_deg - 70 * s) * 1.0
    else:                 el = np.array([0, -1, 0])
    # natural wrist (Daniel: "what's wrong with his wrist?"): a held sword sits about square to the arm and the wrist
    # only angles it; keep the blade within WRIST_OFF deg of the plane square to the shoulder -> hand line
    bl = hdir(blade_deg, bslope)
    an = reach / np.linalg.norm(reach)
    sq = bl - np.dot(bl, an) * an
    if np.linalg.norm(sq) < 1e-3:
        sq = np.cross(an, [0, 1.0, 0])
    sq = sq / np.linalg.norm(sq)
    off = math.degrees(math.atan2(np.dot(bl, an), np.dot(bl, sq)))
    off = max(-WRIST_OFF, min(WRIST_OFF, off))
    bl = sq * math.cos(math.radians(off)) + an * math.sin(math.radians(off))
    out = {"reach": r3(M.T @ reach), "elbow": r3(M.T @ el), "blade": r3(M.T @ bl)}
    out["grip"] = grip or "fwd"
    out["twirl"] = twirl or 0
    return out


def foot(p, y=0.0, yaw=0.0, pitch=0.0, knee=None):
    k = knee if knee is not None else yaw
    kv = np.array(k, float) / np.linalg.norm(k) if isinstance(k, (tuple, list)) else hdir(k, 0.15 if y > 0.25 else 0.0)
    return {"ankle": r3([p[0] * WIDE, ANKLE + y, p[1]]), "knee": r3(kv), "yaw": round(yaw, 1),
            "pitch": pitch}


_KN = [0]
_PREV = [0.0]
CLAV = {"snap": ([-6, 26], [4, -18]), "in": ([14, -24], [0, 14]), "out": ([-2, 16], [0, -10]),
        "inout": ([4, 4], [0, 0]), "linear": ([6, -6], [0, 6])}   # [lift, forward]: sword shoulder, free shoulder


# class attitude (review 2026-11-23: one attitude for all made the ethereal summon cower): Aggressive = hunched
# brawler, Katana = low, compact, explosive, Ethereal swords = tall, open, regal (chest lifted on the big gestures)
PROFILES = {
    "Aggressive":      dict(hunch=14, bendk=1.0, arch={"snap": 20, "in": -12, "out": 12}, prowl=8, wide=2.6, glare=0.7),
    "Katana":          dict(hunch=18, bendk=0.6, arch={"snap": 14, "in": -6, "out": 8}, prowl=6, wide=2.4, glare=0.8),
    "Ethereal swords": dict(hunch=-6, bendk=0.45, arch={"snap": -8, "in": 6, "out": -4}, prowl=0, wide=2.0, glare=0.3),
}
PROF = dict(PROFILES["Aggressive"])


def begin(cls):
    """the moves after this call belong to this class (attitude + stance width)"""
    global WIDE
    PROF.clear()
    PROF.update(PROFILES[cls])
    WIDE = PROF["wide"]


def attitude(ease, hrel, drop, over, arch, bend, tilt, proll):
    """The back and spine doing the fighting (Daniel 2026-11-23: "they have backs and spines that bend"): a predator's
    hunch everywhere, the chest crunching sideways INTO each hit, the shoulder dropping toward a loaded blade with the
    chest arched open on the wind-up, a whipping side bend on the follow-through, the pelvis tipping against the chest
    (contrapposto), an arched back in the air, and the head glaring up from under the brow with a cocky tilt.
    Returns (extra spine pitch, spine side bend, pelvis roll, head pitch, head roll); any can be given per key."""
    air = drop < 0
    k = {"snap": 0.38, "in": 0.26, "out": 0.42}.get(ease, 0.16) * PROF["bendk"]
    a = PROF["arch"].get(ease, PROF["prowl"])
    if air:
        a = 22 if ease == "snap" else -20
    a += 0 if air else PROF["hunch"]                        # the class's carry (hunch / tall)
    b = max(-38.0, min(38.0, -hrel * k))                    # hand to the right (negative) -> bend to the right (+roll)
    if arch is not None:
        a = arch
    if bend is not None:
        b = bend
    # line of action (figure-drawing / animation posing): strikes and wind-ups are ONE C-curve from the planted foot
    # through pelvis, spine and head (pelvis tilt and head tilt continue the spine's bend); in-between / prowling
    # keys use contrapposto instead (pelvis tilted against the shoulders) with a cocky head tilt
    _KN[0] += 1
    cock = (9 if _KN[0] % 3 else -11) * (1 if _KN[0] % 2 else -1)
    if ease in ("snap", "out", "in"):
        pr, hr = 0.30 * b, 0.45 * b
    else:
        pr, hr = -0.35 * b, -0.30 * b + cock
    pr += {"R": -7, "L": 7}.get(over, 0)                     # the pelvis drops toward a lifted leg
    if proll is not None:
        pr = proll
    if tilt is not None:
        hr = tilt
    return a, b, pr, hr


def key(t, ease, yaw, sy, lean, drop, fr, fl, S, F, head=None, over=None, roll=None, sroll=None, hx=0.0, hz=0.0,
        arch=None, tilt=None):
    """yaw / sy = hips / spine yaw (deg, cumulative over spins); lean = deg toward the target; drop = hips down (m, < 0 =
    up off the ground); fr / fl = foot(...) dicts; S = right arm kwargs for arm(); F = left arm kwargs; over = foot the
    hips sit over ("R" / "L", spins and kicks); hx / hz = extra hips shift. Attitude (see attitude()): arch = extra
    spine pitch (+ hunch / crunch, - arch back), sroll = spine side bend (+ = to the right), roll = pelvis roll,
    tilt = head roll; left out = automatic from the key's ease and where the sword hand is."""
    # hips and shoulders telegraph (Daniel 2026-11-23): the wind-up coils the chest further back than the hips, the
    # hit is led by the hips (the chest arrives a beat behind), the follow-through whips the chest past them
    tot0 = yaw + sy
    if t == 0:
        _PREV[0] = tot0
    d = tot0 - _PREV[0]
    sg = (d > 2) - (d < -2)
    _PREV[0] = tot0
    if ease == "in":
        sy, yaw = sy + 14 * sg, yaw - 6 * sg          # coil: chest past the hips, hips held back
    elif ease == "snap":
        yaw, sy = yaw + 16 * sg, sy - 16 * sg         # hips lead the strike, the chest lags (same heading)
    elif ease == "out":
        sy = sy + 10 * sg                             # chest whips on past the hips
    if ease in ("snap", "out") and drop >= 0:
        lean += 10                                    # throw the chest out over the front knee on hits
    tot = yaw + sy
    w = ((tot + 180) % 360) - 180
    hy = max(-75, min(75, -w)) if head is None else head
    a, b = fr["ankle"], fl["ankle"]
    if over is None:
        # weight: strikes drive onto the front foot (the back leg straightens = a long line of action), a wind-up
        # sits back on the loaded back leg
        fw = {"snap": 0.72, "out": 0.68, "in": 0.32}.get(ease, 0.5) if abs(a[2] - b[2]) > 0.25 else 0.5
        f1, f2 = (a, b) if a[2] >= b[2] else (b, a)
        mx, mz = f1[0] * fw + f2[0] * (1 - fw), f1[2] * fw + f2[2] * (1 - fw)
    else:
        o, q = (a, b) if over == "R" else (b, a)
        mx, mz = o[0] * 0.8 + q[0] * 0.2, o[2] * 0.8 + q[2] * 0.2
    if drop >= 0:                                            # grounded: sink the hips until both planted legs reach
        for f_, sx in ((a, -1), (b, 1)):
            if f_[1] > ANKLE + 0.2:
                continue
            dxz = math.hypot(f_[0] - (mx + hx + 0.09 * sx), f_[2] - (mz + hz))
            if dxz < LEG:
                need = 0.917 - 0.05 - (f_[1] + math.sqrt(LEG * LEG - dxz * dxz))
                drop = max(drop, need)
    sk = dict(S)
    if ease in ("snap", "out"):                              # hits: the sword arm goes all the way out
        sk["ext"] = max(sk.get("ext", 0.5), 0.55)
    for kk in ("hand_deg", "blade_deg"):
        if callable(sk.get(kk)):
            sk[kk] = sk[kk](tot)
    hrel = ((sk["hand_deg"] - tot + 180) % 360) - 180
    ar, bend, pr, hroll = attitude(ease, hrel, drop, over, arch, sroll, tilt, roll)
    lk = max(0.35, math.cos(math.radians(min(abs(w), 90))) ** 0.5)
    sp_pitch = lean * 0.45 * lk + ar
    hr, sp = [yaw, lean * 0.5 * lk, pr], [sy, sp_pitch, bend]
    M = chest_M(hr, sp)
    fk = dict(F)
    if ease in ("snap", "out", "in"):                        # the free hand flares out wide and low as a counterweight
        fk["ext"] = max(fk.get("ext", 0.38), 0.50)
        fk["h"] = min(fk.get("h", -0.12), -0.05)
    for kk in ("hand_deg", "blade_deg"):
        if callable(fk.get(kk)):
            fk[kk] = fk[kk](tot)
    fk.setdefault("side", -1)
    hp = max(-55.0, -PROF["glare"] * sp_pitch - 10 - lean * 0.1)         # eyes stay on the target: the head glares up
    cr, cl = CLAV.get(ease, ([0, 0], [0, 0]))
    hilt = fk.pop("hilt", False)
    R, L = arm(M, **sk), arm(M, **fk)
    if hilt:
        L["hilt"] = True
    R["clav"], L["clav"] = list(cr), list(cl)
    return {"t": round(t, 3), "ease": ease,
            "hips": {"pos": r3([mx + hx, -drop, mz + hz - 0.0]), "rot": r3(hr)}, "spine": r3(sp),
            "head": r3([hy, hp, hroll]),
            "R": R, "L": L, "fR": fr, "fL": fl}


def S(hand, blade, h=0.0, elbow="fore", **k):
    return dict(hand_deg=hand, blade_deg=blade, h=h, elbow=elbow, **k)


def FREE(deg, h=-0.12, ext=0.38, **k):
    """the free (left) hand: fist out at deg, its blade (if the character holds one) carries on past it."""
    k.setdefault("elbow", "fore")
    return dict(hand_deg=deg, blade_deg=(lambda tot, d=deg: d + 10) if not callable(deg) else deg, h=h, ext=ext,
                bslope=-0.25, side=-1, **k)


def HILT():
    """left hand on the katana's handle (two-hand grip)"""
    return dict(hand_deg=0, blade_deg=0, h=-0.1, ext=0.4, side=-1, hilt=True)


def rel(d):
    """an angle relative to the chest heading (for spins)"""
    return lambda tot: tot + d


CL = {}
# ============================================================================================ KATANA (right hand)
# Iai on the move: run in, the draw-cut lands on the passing step, the katana flips to a reverse grip as the body
# carries on past the target, and the fighter is already striding out of it.
begin("Katana")
CL["kt_iai"] = {"cat": "Katana", "name": "Running iai: draw-cut, flip to reverse grip", "length": 0.95, "keys": [
    key(0.00, "inout", 25, 15, 30, 0.12, foot((-0.12, 0.30), yaw=-5), foot((0.14, -0.30), y=0.10, yaw=25, pitch=25),
        S(40, 140, -0.15, "back", bslope=0.0, ext=0.30), FREE(30, -0.30, 0.25)),          # hand on the hilt at the hip, mid-stride
    key(0.22, "in", 45, 25, 42, 0.26, foot((-0.12, 0.30), yaw=-5), foot((0.16, 1.15), yaw=10),   # long low stride, coiled
        S(50, 145, -0.18, "back", bslope=0.0, ext=0.28), FREE(35, -0.32, 0.22)),
    key(0.30, "snap", -35, -30, 48, 0.32, foot((-0.20, 2.00), yaw=-10), foot((0.16, 1.15), yaw=10),  # DRAW-CUT on the landing foot
        S(-55, -95, 0.05, "fore", bslope=0.05, ext=0.55), FREE(70, -0.28, 0.30), head=20),
    key(0.46, "out", -60, -40, 40, 0.30, foot((-0.20, 2.00), yaw=-10), foot((0.20, 2.70), yaw=-25),  # carries past, back foot through
        S(-85, -170, 0.02, "out", bslope=0.0, ext=0.48, grip="rev"), FREE(60, -0.18, 0.32), head=40, over="L"),
    key(0.95, "inout", -20, -10, 34, 0.18, foot((-0.18, 3.10), y=0.05, yaw=-10, pitch=20), foot((0.20, 2.70), yaw=-25),
        S(-30, 175, -0.15, "back", bslope=-0.1, ext=0.38, grip="rev"), FREE(20, -0.20, 0.32), over="L"),  # reverse grip, blade along the forearm, striding on
]}

# Leaping kirioroshi: two strides, jump, katana high over the head in the air, cut down as the feet land,
# the cut drives the body on into a forward roll-out step.
CL["kt_kirioroshi"] = {"cat": "Katana", "name": "Leaping overhead cut (kirioroshi)", "length": 0.9, "keys": [
    key(0.00, "inout", 10, 5, 28, 0.14, foot((-0.14, 0.25), yaw=-5), foot((0.14, -0.35), y=0.06, yaw=20, pitch=20),
        S(-10, 20, 0.0, "fore"), HILT()),                                   # two-hand guard, running
    key(0.18, "in", 0, 0, 20, 0.30, foot((-0.14, 0.80), yaw=-5), foot((0.14, 0.40), yaw=15),    # gather: deep take-off crouch
        S(-15, 30, -0.10, "fore"), HILT()),
    key(0.36, "out", 5, 0, 8, -0.08, foot((-0.16, 1.75), y=0.55, yaw=0, pitch=30, knee=(0, 0.6, 1)), foot((0.14, 0.75), y=0.75, yaw=10, pitch=70, knee=(0, -1, 0.2)),
        S(-5, 175, 0.62, "up", bslope=0.25, ext=0.25), HILT()),  # AIR: katana high over the head, arched back
    key(0.46, "snap", 0, 0, 55, 0.32, foot((-0.16, 2.30), yaw=-5), foot((0.16, 1.55), yaw=15),  # CUT down as the feet land
        S(-5, 10, -0.40, "fore", bslope=-0.55, ext=0.55), HILT()),
    key(0.62, "out", 0, 0, 58, 0.36, foot((-0.16, 2.30), yaw=-5), foot((0.16, 1.55), yaw=15),
        S(-20, -40, -0.55, "fore", bslope=-0.8, ext=0.52), HILT()),
    key(0.90, "inout", -5, 0, 38, 0.24, foot((-0.16, 2.30), yaw=-5), foot((0.18, 2.95), yaw=5),     # back foot steps through: keeps going
        S(-60, -150, -0.30, "fore", bslope=-0.3, ext=0.45), HILT()),
]}

# Chiburi + noto on the move: walk forward out of a cut, twirl the katana twice (blood off), snap a reverse-grip flick,
# then slide it home along the hip while still walking.
CL["kt_chiburi_noto"] = {"cat": "Katana", "name": "Walking twirl, chiburi flick, reverse-grip sheathe", "length": 1.25, "keys": [
    key(0.00, "inout", -20, -10, 24, 0.20, foot((-0.18, 0.25), yaw=-10), foot((0.16, -0.30), yaw=15),
        S(-70, -70, -0.10, "out", bslope=-0.3, ext=0.52), FREE(25, -0.25, 0.30)),                     # just finished a cut, low blade
    key(0.32, "inout", 0, 0, 14, 0.12, foot((-0.18, 0.25), yaw=-10), foot((0.14, 0.85), yaw=5),   # step: two twirls at the side
        S(-75, -60, 0.10, "out", bslope=0.2, ext=0.45, twirl=720), FREE(30, -0.25, 0.28)),
    key(0.46, "snap", -25, -15, 20, 0.18, foot((-0.18, 0.25), yaw=-10), foot((0.14, 0.85), yaw=5),  # CHIBURI: sharp flick out and down
        S(-70, -110, -0.15, "out", bslope=-0.35, ext=0.55, twirl=720), FREE(25, -0.22, 0.28)),
    key(0.72, "inout", 10, 5, 16, 0.12, foot((-0.18, 1.45), yaw=-5), foot((0.14, 0.85), yaw=5),   # step; flip to reverse grip
        S(-60, 175, -0.25, "back", bslope=-1.2, ext=0.45, grip="rev", twirl=720), FREE(40, -0.30, 0.22)),
    key(0.86, "inout", 15, 5, 15, 0.12, foot((-0.18, 1.45), yaw=-5), foot((0.15, 1.45), y=0.10, yaw=8, pitch=20),
        S(-5, 5, -0.15, "back", bslope=-0.6, ext=0.45, grip="rev", twirl=720), FREE(35, -0.30, 0.22)),   # carried across, point down
    key(1.00, "in", 25, 10, 14, 0.12, foot((-0.18, 1.45), yaw=-5), foot((0.16, 2.00), yaw=10),    # NOTO: blade laid along the hip
        S(35, 150, -0.20, "back", bslope=0.1, ext=0.30, grip="rev", twirl=720), FREE(30, -0.33, 0.24)),
    key(1.25, "snap", 15, 5, 18, 0.12, foot((-0.18, 2.50), y=0.04, yaw=-5, pitch=15), foot((0.16, 2.00), yaw=10),  # click: sheathed, walking on
        S(40, 150, -0.22, "back", bslope=0.1, ext=0.28, grip="rev", twirl=720), FREE(32, -0.34, 0.22)),
]}

# Battojutsu flash step: drop into the coil, cross 4 m in one burst (body nearly flat, feet trailing), the cut lands
# on arrival, the slide carries past, and the katana twirls into a reverse grip as the fighter rises out of it.
CL["kt_dash_slash"] = {"cat": "Katana", "name": "Battojutsu flash step (4 m dash cut, twirl out)", "length": 1.0, "flash": [2, 3], "keys": [
    key(0.00, "inout", 30, 20, 30, 0.18, foot((-0.14, 0.30), yaw=-5), foot((0.16, -0.35), yaw=30),
        S(45, 140, -0.15, "back", bslope=0.0, ext=0.30), FREE(35, -0.30, 0.22)),
    key(0.20, "in", 40, 25, 50, 0.42, foot((-0.14, 0.40), yaw=-5), foot((0.18, -0.45), yaw=30),   # coil: deep, hand on the hilt
        S(50, 145, -0.18, "back", bslope=0.0, ext=0.28), FREE(40, -0.32, 0.20)),
    key(0.30, "snap", 30, 15, 58, 0.36, foot((-0.16, 2.30), y=0.06, yaw=0, pitch=-10), foot((0.18, 0.90), y=0.30, yaw=15, pitch=60),
        S(45, 145, -0.15, "back", bslope=0.0, ext=0.30), FREE(35, -0.25, 0.20)),                        # BURST: flat out, feet off the ground
    key(0.40, "snap", -45, -35, 50, 0.30, foot((-0.22, 3.80), yaw=-15), foot((0.20, 2.90), yaw=0),  # CUT on arrival
        S(-40, -70, 0.0, "out", ext=0.56), FREE(75, -0.20, 0.45), head=30),
    key(0.62, "out", -70, -40, 45, 0.32, foot((-0.24, 4.30), yaw=-20), foot((0.20, 3.50), yaw=-5),  # skid on past it
        S(-65, -120, -0.05, "out", ext=0.55), FREE(70, -0.15, 0.45), head=50),
    key(1.00, "inout", -25, -10, 28, 0.20, foot((-0.24, 4.30), yaw=-20), foot((0.18, 4.80), y=0.04, yaw=-5, pitch=15),
        S(-55, -150, 0.10, "out", bslope=-0.3, ext=0.55, grip="rev", twirl=-360), FREE(25, -0.22, 0.32), over="R"),  # rises, reverse grip
]}

# ============================================================================== ETHEREAL SWORDS (blades are FX)
# Advancing summon: stride in, a full turn with the arms flung open (the blades fan out round the fighter), land the
# turn stepping forward with both arms spread wide.
begin("Ethereal swords")
CL["et_summon"] = {"cat": "Ethereal swords", "name": "Spinning summon (stride, turn, arms flung open)", "length": 1.15, "keys": [
    key(0.00, "inout", 10, 5, 22, 0.12, foot((-0.14, 0.25), yaw=-5), foot((0.14, -0.30), yaw=20),
        S(-30, -60, -0.25, "fore", ext=0.35), FREE(30, -0.25, 0.35)),
    key(0.25, "in", -30, -20, 28, 0.26, foot((-0.16, 1.00), yaw=-10), foot((0.14, -0.30), yaw=20),  # arms gathered in, coil
        S(30, 120, -0.20, "back", bslope=-0.3, ext=0.30), FREE(-25, -0.18, 0.26, elbow="back")),
    key(0.55, "linear", 170, 20, 6, 0.10, foot((-0.16, 1.00), yaw=150), foot((0.45, 1.45), y=0.30, yaw=160, pitch=20),
        S(rel(-90), rel(-90), 0.20, "out", bslope=0.3, ext=0.55), FREE(rel(90), 0.20, 0.55, elbow="out"), over="R", head=-40),  # turning, arms flung wide
    key(0.80, "snap", 360, 0, 10, 0.20, foot((-0.20, 1.95), yaw=355), foot((0.24, 1.55), yaw=375),   # lands the turn: ARMS OPEN
        S(-95, -100, 0.35, "out", bslope=0.6, ext=0.56), FREE(95, 0.35, 0.56, elbow="out")),
    key(1.15, "out", 360, 0, 18, 0.14, foot((-0.20, 1.95), yaw=355), foot((0.20, 2.60), y=0.04, yaw=365, pitch=15),
        S(-80, -80, 0.25, "out", bslope=0.4, ext=0.54), FREE(80, 0.25, 0.54, elbow="out")),
]}

# Command strike on the move: lunge and point (the blades fly), then a turning back kick on the same line and land
# striding on.
CL["et_command"] = {"cat": "Ethereal swords", "name": "Lunging point, turning back kick", "length": 0.85, "keys": [
    key(0.00, "inout", 15, 10, 22, 0.14, foot((-0.14, 0.25), yaw=-5), foot((0.14, -0.30), yaw=20),
        S(25, -30, -0.10, "back", ext=0.30), FREE(30, -0.20, 0.30)),
    key(0.16, "snap", -25, -20, 42, 0.28, foot((-0.18, 1.10), yaw=-15), foot((0.14, -0.10), yaw=20),  # POINT: arm straight at the target
        S(-3, 0, 0.12, "fore", bslope=0.1, ext=0.56), FREE(70, -0.10, 0.40), head=25),
    key(0.34, "in", 110, 40, 10, 0.18, foot((-0.18, 1.10), yaw=100), foot((0.10, 0.70), y=0.10, yaw=110, pitch=20),  # turn on the front foot
        S(rel(-60), rel(-60), 0.0, "out", ext=0.40), FREE(rel(60), -0.05, 0.38), over="R", head=-60),
    key(0.46, "snap", 180, 0, -35, 0.10, foot((-0.18, 1.10), yaw=180), foot((0.0, 2.05), y=0.78, yaw=170, pitch=50, knee=(0, -1, 0.3)),
        S(rel(-70), rel(-80), 0.10, "out", ext=0.45), FREE(rel(70), 0.10, 0.45), over="R", head=-75),  # BACK KICK at the target
    key(0.62, "out", 220, 20, -10, 0.14, foot((-0.18, 1.10), yaw=200), foot((0.10, 1.80), y=0.30, yaw=200, pitch=30, knee=(0, -1, 0.3)),
        S(rel(-80), rel(-80), 0.0, "out", ext=0.40), FREE(rel(70), 0.0, 0.40), over="R", head=-70),
    key(0.85, "inout", 360, 0, 22, 0.16, foot((-0.18, 2.50), yaw=355), foot((0.16, 1.85), yaw=375),   # spins on round, lands stepping
        S(-30, -40, -0.10, "fore", ext=0.40), FREE(35, -0.15, 0.36)),
]}

# Running sweep + launch: arc out to the side and forward with one arm sweeping across (the blades fan), plant, and
# shove both palms at the target in a long lunge (the volley).
CL["et_sweep_launch"] = {"cat": "Ethereal swords", "name": "Curving run sweep, double-palm launch", "length": 1.05, "keys": [
    key(0.00, "inout", 10, 5, 24, 0.14, foot((-0.14, 0.25), yaw=-5), foot((0.14, -0.30), yaw=20),
        S(-30, -50, -0.20, "fore", ext=0.35), FREE(30, -0.22, 0.32)),
    key(0.28, "in", -45, -35, 30, 0.24, foot((-0.60, 0.95), yaw=-40), foot((-0.25, 0.30), y=0.10, yaw=-30, pitch=20),  # run out to the right
        S(-100, -120, 0.15, "out", bslope=0.2, ext=0.55), FREE(-20, -0.10, 0.30), over="R"),
    key(0.46, "snap", 35, 25, 36, 0.26, foot((-0.55, 1.55), yaw=10), foot((-0.15, 1.40), yaw=30),   # SWEEP across, curving in
        S(80, 100, 0.20, "back", bslope=0.25, ext=0.55), FREE(10, -0.15, 0.30)),
    key(0.66, "in", 50, 30, 10, 0.20, foot((-0.55, 1.55), yaw=10), foot((-0.15, 1.40), yaw=30),     # draw both hands back to the hip
        S(-35, 0, -0.25, "fore", bslope=-1.5, ext=0.25), FREE(35, -0.25, 0.25)),
    key(0.78, "snap", -10, -5, 48, 0.36, foot((-0.40, 2.50), yaw=-10), foot((-0.15, 1.40), yaw=30),  # LAUNCH: both palms out, long lunge
        S(-8, 5, 0.05, "fore", ext=0.56), FREE(8, 0.05, 0.56), head=5),
    key(1.05, "out", -5, 0, 34, 0.24, foot((-0.40, 2.50), yaw=-10), foot((-0.10, 3.05), y=0.04, yaw=10, pitch=15),
        S(-15, -10, -0.05, "fore", ext=0.50), FREE(15, -0.05, 0.50)),
]}

# Rain of blades: run, leap high and forward raising both arms (the blades gather overhead), bring them down hard as
# the fighter lands in a deep crouch, and spring out of it.
CL["et_rain"] = {"cat": "Ethereal swords", "name": "Leaping rain of blades (arms up in the air, slam on landing)", "length": 1.2, "keys": [
    key(0.00, "inout", 5, 0, 26, 0.14, foot((-0.14, 0.25), yaw=-5), foot((0.14, -0.30), yaw=20),
        S(-25, -40, -0.25, "fore", ext=0.32), FREE(25, -0.25, 0.32)),
    key(0.18, "in", 0, 0, 34, 0.36, foot((-0.14, 0.85), yaw=-5), foot((0.14, 0.45), yaw=10),       # take-off crouch, arms swing back
        S(-25, -30, -0.30, "fore", bslope=-1.2, ext=0.45), FREE(20, -0.30, 0.45)),
    key(0.45, "out", 0, 0, 12, -0.15, foot((-0.16, 1.90), y=0.60, yaw=0, pitch=35, knee=(0, 0.6, 1)), foot((0.14, 0.95), y=0.80, yaw=10, pitch=70, knee=(0, -1, 0.2)),
        S(-30, -20, 0.70, "up", bslope=1.5, ext=0.30), FREE(30, 0.70, 0.30, elbow="up")),       # AIR: arms high, body arched
    key(0.62, "snap", 0, 0, 58, 0.40, foot((-0.20, 2.40), yaw=-10), foot((0.20, 2.10), yaw=20),     # SLAM: lands, arms driven down
        S(-25, -10, -0.55, "fore", bslope=-1.2, ext=0.56), FREE(25, -0.55, 0.56)),
    key(0.92, "inout", 0, 0, 50, 0.38, foot((-0.20, 2.40), yaw=-10), foot((0.20, 2.10), yaw=20),
        S(-35, -30, -0.50, "fore", bslope=-1.0, ext=0.52), FREE(35, -0.50, 0.52)),
    key(1.20, "out", 0, 0, 32, 0.18, foot((-0.20, 2.40), yaw=-10), foot((0.16, 3.05), y=0.05, yaw=10, pitch=15),  # springs out of it
        S(-30, -60, -0.20, "fore", ext=0.40), FREE(30, -0.20, 0.38)),
]}

# ============================================================================================ AGGRESSIVE (sword)
# Wide sweep with a crossover step: the back foot crosses in front, the hips whip the forehand through, and the
# follow-through pulls the fighter into the next stride.
begin("Aggressive")
CL["ag_wide_sweep"] = {"cat": "Aggressive", "name": "Crossover step-in forehand sweep", "length": 0.75, "keys": [
    key(0.00, "inout", 5, 5, 34, 0.12, foot((-0.14, 0.45), yaw=-5), foot((0.16, -0.25), y=0.18, yaw=20, pitch=40),
        S(-25, -20, -0.10, ext=0.45), FREE(30, -0.20, 0.40)),                                    # entry: sprinting in
    key(0.16, "in", -60, -35, 22, 0.26, foot((-0.20, 0.90), yaw=-35), foot((0.16, -0.30), yaw=25),  # step + coil: blade back right
        S(-85, -150, 0.05), FREE(20, -0.10)),
    key(0.28, "snap", 10, 10, 40, 0.34, foot((-0.20, 0.90), yaw=-35), foot((-0.05, 1.55), yaw=30),   # CROSSOVER + SWEEP
        S(-10, 15, 0.0, ext=0.56), FREE(110, -0.15)),
    key(0.40, "out", 70, 35, 40, 0.36, foot((-0.20, 0.90), yaw=25, pitch=25), foot((-0.05, 1.55), yaw=30),
        S(75, 120, 0.02), FREE(150, -0.10), over="L"),
    key(0.75, "inout", 30, 15, 30, 0.22, foot((-0.25, 2.30), y=0.04, yaw=10, pitch=15), foot((-0.05, 1.55), yaw=30),
        S(40, 80, -0.05), FREE(110, -0.15), over="L"),
]}

# Forehand, flip to a reverse grip on the follow-through, reverse-grip backhand stab-slash stepping through, flip
# back to forward grip as the fighter keeps advancing.
CL["ag_sweep_return"] = {"cat": "Aggressive", "name": "Forehand, flip to reverse grip, backhand return", "length": 1.0, "keys": [
    key(0.00, "inout", 30, 15, 20, 0.20, foot((-0.20, 0.30), yaw=-10), foot((0.20, -0.35), yaw=40),
        S(20, -150, 0.25, "up", bslope=0.3, ext=0.30), FREE(35, -0.25, 0.45)),                    # entry: blade over the shoulder
    key(0.14, "in", -55, -32, 22, 0.24, foot((-0.20, 0.80), yaw=-25), foot((0.16, -0.30), yaw=25),
        S(-80, -145, 0.0), FREE(20, -0.10)),
    key(0.24, "snap", 5, 8, 38, 0.32, foot((-0.20, 0.80), yaw=-25), foot((0.16, -0.30), yaw=25),     # FOREHAND
        S(-10, 15, 0.0, ext=0.56), FREE(90, -0.15)),
    key(0.40, "out", 60, 35, 30, 0.30, foot((-0.20, 0.80), yaw=-25), foot((0.20, 1.20), y=0.08, yaw=30, pitch=20),  # flip: reverse grip
        S(85, 170, 0.05, "back", ext=0.50, grip="rev"), FREE(130, -0.10), over="R"),
    key(0.52, "snap", -40, -30, 40, 0.34, foot((-0.20, 0.80), yaw=-25), foot((0.18, 1.70), yaw=10),  # REVERSE BACKHAND stepping through
        S(-60, -30, 0.0, "out", ext=0.52, grip="rev"), FREE(50, -0.10)),
    key(0.68, "out", -75, -40, 36, 0.32, foot((-0.20, 0.80), yaw=-25), foot((0.18, 1.70), yaw=10),
        S(-95, -60, 0.05, "out", ext=0.48, grip="rev"), FREE(40, -0.15), over="L"),
    key(1.00, "inout", -15, -5, 28, 0.20, foot((-0.20, 2.40), y=0.04, yaw=-5, pitch=15), foot((0.18, 1.70), yaw=10),
        S(-60, -40, 0.05, "out", ext=0.55, grip="fwd", twirl=-360), FREE(40, -0.15), over="L"),               # twirls back to forward grip
]}

# Forehand into a spinning roundhouse kick (the sword arm flung out for balance), landing the turn into a backhand.
CL["ag_spin_backhand"] = {"cat": "Aggressive", "name": "Forehand, spinning hook kick, backhand", "length": 1.1, "keys": [
    key(0.00, "inout", 0, 0, 30, 0.32, foot((-0.16, 0.30), yaw=-5), foot((0.18, 0.0), yaw=20),
        S(-45, -70, -0.05, "out", ext=0.5), FREE(60, -0.05, 0.5)),                                # entry: landing from the air
    key(0.12, "in", -55, -32, 22, 0.24, foot((-0.20, 0.80), yaw=-25), foot((0.16, -0.30), yaw=25),
        S(-80, -145, 0.0), FREE(20, -0.10)),
    key(0.22, "snap", 5, 8, 38, 0.32, foot((-0.20, 0.80), yaw=-25), foot((0.10, 0.60), yaw=25),      # FOREHAND, back foot drawn up
        S(-10, 15, 0.0, ext=0.56), FREE(90, -0.15)),
    key(0.40, "linear", 150, 30, 5, 0.14, foot((-0.20, 0.80), yaw=140), foot((0.30, 1.10), y=0.35, yaw=150, pitch=30),  # spin on the front foot
        S(rel(-100), rel(-130), 0.25, "out", bslope=0.3, ext=0.50), FREE(rel(70), 0.0, 0.35), over="R", head=-60),
    key(0.52, "snap", 290, 30, -30, 0.12, foot((-0.20, 0.80), yaw=270), foot((-0.10, 1.85), y=0.85, yaw=280, pitch=40, knee=250),
        S(rel(-110), rel(-140), 0.30, "out", bslope=0.3, ext=0.52), FREE(rel(80), 0.10, 0.40), over="R", head=60),  # HOOK KICK at the target
    key(0.66, "in", 330, 25, 20, 0.24, foot((-0.20, 0.80), yaw=310), foot((0.15, 1.55), yaw=345),     # kick foot lands ahead, blade loaded left
        S(rel(70), rel(140), 0.05, "back"), FREE(rel(30), -0.15), head=20),
    key(0.76, "snap", 365, -8, 40, 0.34, foot((-0.15, 2.20), yaw=355), foot((0.15, 1.55), yaw=345),   # BACKHAND stepping in
        S(-10, -15, 0.0, "back", ext=0.56), FREE(60, -0.10)),
    key(1.10, "out", 320, -30, 34, 0.30, foot((-0.15, 2.20), yaw=355), foot((0.18, 2.85), y=0.04, yaw=0, pitch=15),
        S(-75, -105, 0.0, "back"), FREE(40, -0.15)),
]}

# Low slide sweep under the guard, then explode up into a jumping spin and a high sweep in the air, landing forward.
CL["ag_low_high_spin"] = {"cat": "Aggressive", "name": "Sliding low sweep, jumping spin high sweep", "length": 1.15, "keys": [
    key(0.00, "inout", -35, -10, 18, 0.22, foot((-0.45, 0.10), yaw=-30), foot((-0.05, -0.30), y=0.12, yaw=0, pitch=30),
        S(-60, -90, 0.0, "out", ext=0.5), FREE(50, -0.10, 0.45)),                                 # entry: out of a side dodge
    key(0.14, "in", -50, -30, 34, 0.36, foot((-0.20, 0.85), yaw=-25), foot((0.16, -0.20), yaw=25),
        S(-80, -140, -0.25), FREE(20, -0.20)),
    key(0.26, "snap", 0, 5, 54, 0.48, foot((-0.30, 1.80), yaw=-30), foot((0.25, 0.65), yaw=40, pitch=-20),  # LOW SWEEP: slide in deep
        S(-10, 15, -0.45, ext=0.56), FREE(100, -0.40)),
    key(0.40, "in", 60, 30, 40, 0.42, foot((-0.30, 1.80), yaw=30, pitch=25), foot((0.25, 0.65), yaw=40, pitch=-20),
        S(70, 110, -0.40), FREE(140, -0.30), over="R"),
    key(0.58, "linear", 200, 20, 0, -0.12, foot((-0.20, 2.40), y=0.70, yaw=180, pitch=40, knee=(0, 0.6, 1)), foot((0.20, 2.10), y=0.70, yaw=190, pitch=40, knee=(0, 0.6, 1)),
        S(rel(15), rel(180), 0.50, "up", bslope=0.45, ext=0.45), FREE(rel(-60), 0.20, 0.40), head=60),   # AIR: spinning, blade over the head
    key(0.72, "snap", 360, 5, 45, -0.04, foot((-0.20, 3.05), y=0.50, yaw=350, pitch=30, knee=(0, 0.6, 1)), foot((0.20, 2.05), y=0.80, yaw=360, pitch=70, knee=(0, -1, 0.2)),
        S(-10, 15, 0.35, ext=0.56), FREE(100, 0.0)),                                              # HIGH SWEEP in the air
    key(0.86, "out", 410, 30, 30, 0.30, foot((-0.20, 3.20), yaw=380), foot((0.20, 2.85), yaw=395),    # lands
        S(70, 110, 0.10), FREE(150, -0.10)),
    key(1.15, "inout", 390, 15, 30, 0.20, foot((-0.20, 3.20), yaw=380), foot((0.18, 3.75), y=0.04, yaw=375, pitch=15),
        S(40, 80, -0.05), FREE(110, -0.15)),
]}

# Cyclone: a travelling double spin, the blade twirling overhead between sweeps, each turn a step further in, the
# second sweep low, and out into a run.
CL["ag_cyclone"] = {"cat": "Aggressive", "name": "Travelling cyclone (two spins, twirls overhead)", "length": 1.35, "keys": [
    key(0.00, "inout", 0, 0, 45, 0.22, foot((-0.14, 0.55), yaw=-5), foot((0.16, -0.20), y=0.20, yaw=20, pitch=45),
        S(-35, -150, -0.20, "fore", bslope=-0.2, ext=0.45), FREE(35, -0.25, 0.45)),               # entry: low sprint, blade trailing
    key(0.14, "in", -60, -35, 22, 0.26, foot((-0.20, 0.85), yaw=-30), foot((0.16, -0.30), yaw=25),
        S(-85, -150, 0.05), FREE(20, -0.10)),
    key(0.24, "snap", 10, 10, 38, 0.32, foot((-0.20, 0.85), yaw=10, pitch=20), foot((0.10, 1.40), yaw=30),     # SWEEP 1
        S(-10, 15, 0.0, ext=0.56), FREE(110, -0.15)),
    key(0.46, "linear", 190, 20, 6, 0.10, foot((-0.30, 2.10), y=0.20, yaw=170, pitch=20), foot((0.10, 1.40), yaw=200),
        S(rel(10), rel(180), 0.55, "up", bslope=0.4, ext=0.35, twirl=180), FREE(rel(-110), 0.25, 0.50, elbow="out"), over="L", head=60),  # turn, blade twirls overhead
    key(0.64, "in", 300, 20, 20, 0.30, foot((-0.30, 2.30), yaw=290), foot((0.25, 2.70), yaw=320),
        S(rel(-85), rel(-150), -0.15, twirl=360), FREE(rel(40), -0.05, 0.5), head=-50),
    key(0.74, "snap", 370, 10, 50, 0.44, foot((-0.30, 2.30), yaw=340, pitch=20), foot((0.30, 3.00), yaw=350, pitch=-15),  # SWEEP 2, LOW
        S(-10, 15, -0.40, ext=0.56, twirl=360), FREE(110, -0.35)),
    key(0.90, "out", 430, 35, 45, 0.40, foot((-0.30, 2.30), yaw=390, pitch=30), foot((0.30, 3.00), yaw=400),
        S(75, 120, -0.30, twirl=360), FREE(150, -0.25), over="L"),
    key(1.35, "inout", 380, 10, 30, 0.20, foot((-0.20, 3.70), y=0.04, yaw=375, pitch=15), foot((0.30, 3.00), yaw=400),
        S(20, 60, -0.05, twirl=360), FREE(90, -0.15), over="L"),
]}

# Front push kick to break the guard, flip to reverse grip, then a two-turn reverse-grip backhand spin across the
# ground (KH-style), finishing striding forward.
CL["ag_backhand_spin"] = {"cat": "Aggressive", "name": "Push kick, reverse-grip double backhand spin", "length": 1.2, "keys": [
    key(0.00, "inout", 25, 10, 22, 0.18, foot((-0.16, 0.25), yaw=-5), foot((0.18, -0.35), yaw=35),
        S(45, 160, 0.0, "back", bslope=0.1, grip="rev", ext=0.40), FREE(-30, -0.10, 0.45)),     # entry: reverse-grip guard
    key(0.12, "in", 15, 5, 10, 0.10, foot((-0.14, 0.28), yaw=-5), foot((0.16, 0.25), y=0.45, yaw=10, pitch=10, knee=(0.1, 0.5, 1)),  # chamber the knee
        S(-30, -60, 0.0, "fore", grip="rev"), FREE(30, 0.0, 0.30)),
    key(0.22, "snap", 15, 0, -25, 0.10, foot((-0.14, 0.28), yaw=-5), foot((0.14, 0.95), y=0.70, yaw=10, pitch=-40, knee=(0.1, 0.5, 1)),  # PUSH KICK
        S(-50, -120, 0.05, "out", grip="rev"), FREE(50, 0.0, 0.35), over="R"),
    key(0.34, "in", 50, 30, 20, 0.24, foot((-0.14, 0.28), yaw=-5), foot((0.14, 1.00), yaw=20),         # kick foot lands, load the backhand
        S(60, 150, 0.0, "back", grip="rev"), FREE(25, -0.15), over="L"),
    key(0.46, "snap", -20, -20, 38, 0.32, foot((-0.20, 1.60), yaw=-30), foot((0.14, 1.00), yaw=20),    # REVERSE BACKHAND 1
        S(-40, -10, 0.0, "out", ext=0.52, grip="rev"), FREE(60, -0.10)),
    key(0.66, "linear", -200, -20, 10, 0.14, foot((-0.20, 1.60), yaw=-180, pitch=25), foot((0.35, 2.30), y=0.25, yaw=-210, pitch=20),
        S(rel(-90), rel(-40), 0.10, "out", ext=0.50, grip="rev"), FREE(rel(60), 0.0, 0.40), over="R", head=60),  # spin to the right
    key(0.80, "snap", -340, -20, 40, 0.36, foot((-0.25, 2.90), yaw=-345), foot((0.30, 2.30), yaw=-320),   # REVERSE BACKHAND 2
        S(-40, -10, 0.0, "out", ext=0.52, grip="rev"), FREE(60, -0.10)),
    key(1.20, "out", -385, -30, 30, 0.22, foot((-0.25, 2.90), yaw=-345), foot((0.25, 3.55), y=0.04, yaw=-355, pitch=15),
        S(-95, -40, 0.15, "out", ext=0.55, grip="rev"), FREE(40, -0.15), over="R"),  # exits still in reverse grip             # twirl back to forward grip
]}

FOOT_V = 7.5     # m/s: average swing speed of a stepping foot (a sprinter's stride is ~2 m in ~0.25 s)
BODY_V = 6.0     # m/s: fastest the hips may cross the ground between two keys (a lunge), flash steps excepted
HANG = 1.5       # anime hang: jumps may rise this much higher than real gravity gives for their airtime
G = 9.8


def lateral_path(c):
    """c["path"] = (shape, metres): the move curves / slides sideways (review: everything went straight at the
    target). The offset is a function of how far along the travel line a spot is, so a planted foot stays planted.
    side = drifts across linearly (sidestep cut), arc = bows out and comes back in (circling the target), hook =
    straight in then curls across at the end. + = to the fighter's left."""
    if not c.get("path"):
        return
    shape, A = c["path"]
    zs = [k[f]["ankle"][2] for k in c["keys"] for f in ("fR", "fL")]
    z0, z1 = min(zs), max(max(zs), min(zs) + 0.5)
    fn = {"side": lambda u: u, "arc": lambda u: math.sin(math.pi * u), "hook": lambda u: u ** 2.5}[shape]
    off = lambda z: A * fn(min(1.0, max(0.0, (z - z0) / (z1 - z0))))
    for k in c["keys"]:
        for f in ("fR", "fL"):
            k[f] = dict(k[f]); k[f]["ankle"] = list(k[f]["ankle"]); k[f]["ankle"][0] = round(k[f]["ankle"][0] + off(k[f]["ankle"][2]), 3)
        k["hips"] = dict(k["hips"]); k["hips"]["pos"] = list(k["hips"]["pos"])
        k["hips"]["pos"][0] = round(k["hips"]["pos"][0] + off(k["hips"]["pos"][2]), 3)


def physical_timing(c):
    """Daniel 2026-11-23: "why does he float around like that? what's wrong with his physics?". Stretch every
    segment that asks a foot / the hips to move faster than a body can, give jumps the airtime their height needs
    (rise eases out, the fall accelerates in = gravity), and push the later keys back. c["flash"] = key indices whose
    incoming segment is a deliberate flash step (no foot / body speed limit)."""
    ks, flash = c["keys"], set(c.get("flash", ()))
    hy = lambda k: k["hips"]["pos"][1]
    shift = 0.0
    out = [dict(ks[0])]
    for i in range(1, len(ks)):
        a, b = ks[i - 1], ks[i]
        dt = b["t"] - a["t"]
        need = 0.0
        if i not in flash:
            for f in ("fR", "fL"):
                d = math.hypot(b[f]["ankle"][0] - a[f]["ankle"][0], b[f]["ankle"][2] - a[f]["ankle"][2])
                need = max(need, d / FOOT_V)
            hd = math.hypot(b["hips"]["pos"][0] - a["hips"]["pos"][0], b["hips"]["pos"][2] - a["hips"]["pos"][2])
            need = max(need, hd / BODY_V)
        rise = hy(b) - hy(a)
        air_b = min(b["fR"]["ankle"][1], b["fL"]["ankle"][1]) > ANKLE + 0.15
        air_a = min(a["fR"]["ankle"][1], a["fL"]["ankle"][1]) > ANKLE + 0.15
        nb = dict(b)
        # flight = above standing hips height (0); below it the legs push off / absorb the landing (~0.1 s)
        if air_b and rise > 0.05:                      # going up: decelerating
            fl = max(0.0, hy(b)) - max(0.0, min(hy(a), 0.0))
            need = max(need, math.sqrt(2 * fl / (G / HANG)) + (0.10 if hy(a) < -0.05 else 0.0))
            nb["bease"] = "out"
        elif air_a and rise < -0.05:                   # coming down: accelerating
            fl = max(0.0, hy(a))
            need = max(need, math.sqrt(2 * fl / (G / HANG)) + (0.08 if hy(b) < -0.05 else 0.0))
            nb["bease"] = "in"
        if dt < need:
            shift += need - dt
        nb["t"] = round(b["t"] + shift, 3)
        out.append(nb)
    c["keys"] = out
    c["length"] = round(max(c["length"] + shift, out[-1]["t"]), 3)


PATHS = {"ag_sweep_return": ("side", 0.9), "kt_chiburi_noto": ("arc", -0.9), "et_summon": ("side", 0.7),
         "ag_cyclone": ("arc", -1.0), "ag_backhand_spin": ("hook", -0.9), "et_sweep_launch": ("arc", -0.4)}
for n, c in CL.items():
    if n in PATHS:
        c["path"] = PATHS[n]
    lateral_path(c)
    physical_timing(c)
    c["arm_space"] = "chest"
    c["physics"] = True             # body lunges / feet stride (anim3d interp), never a one-frame skate
    c["key_tol"] = [0.08, 0.22]      # few key poses: the tween does the in-betweens (Daniel 2026-11-23)
    c["approved"] = False

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "moves.anim3d.json")
if __name__ == "__main__":
    if len(sys.argv) > 1:
        json.dump({"format": "pb_anim3d", "version": 1, "notes": "draft", "clips": CL}, open(sys.argv[1], "w"), indent=1)
    else:
        spec = json.load(open(OUT, encoding="utf-8"))
        spec["clips"] = {c: v for c, v in CL.items()}
        json.dump(spec, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("wrote", list(CL))
