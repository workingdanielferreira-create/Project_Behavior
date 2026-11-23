"""Rig Forge 3D move library, Aggressive class (Daniel 2026-11-23: horizontal sweeps, backhands, spinning follow-ups).

    python v3/tools/library/gen_aggressive.py      (re)writes the ag_* clips into v3/tools/library/moves.anim3d.json
      (keeps every other clip and each ag_* clip's "approved" flag)

Aggressive class: horizontal sweeps, backhands, spinning follow-ups (pb_anim3d, chest-space arms).
Arms are designed in BODY space by angle round the fighter (phi: 0 = at the target, + = to the fighter's left)
and converted to chest space per key, so the sweep arc is exact whatever the torso does."""
import json, math, os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from anim3d import rot_euler

def r3(v): return [round(float(x), 3) for x in v]
def hdir(deg, y=0.0):
    a = math.radians(deg); v = np.array([math.sin(a), y, math.cos(a)]); return v / np.linalg.norm(v)

def chest_M(hips_rot, spine):
    return rot_euler(*hips_rot) @ rot_euler(*spine)

def sword(M, hand_deg, blade_deg, h=0.0, elbow="fore", bslope=0.0, ext=0.5):
    """hand at angle hand_deg round the shoulder (ext m out), height h; blade toward blade_deg."""
    reach = hdir(hand_deg) * ext + np.array([0, h - 0.10, 0])
    if elbow == "fore":   el = np.array([0, -1, 0]) + hdir(hand_deg - 90) * 0.35        # elbow down, a bit behind the hand
    elif elbow == "back": el = np.array([0, -0.5, 0]) + hdir(hand_deg + 90) * 0.6       # backhand: elbow leads across
    elif elbow == "up":   el = np.array([0, 0.35, 0]) + hdir(hand_deg - 100) * 1.0      # overhead: elbow out to the sword side
    elif elbow == "upb":  el = np.array([0, 0.35, 0]) + hdir(hand_deg + 100) * 1.0
    else:                 el = np.array([0, -1, 0])
    blade = hdir(blade_deg, bslope)
    return {"reach": r3(M.T @ reach), "elbow": r3(M.T @ el), "blade": r3(M.T @ blade)}

def free(M, deg, h=-0.14, ext=0.36):
    reach = hdir(deg) * ext + np.array([0, h, 0])
    return {"reach": r3(M.T @ reach), "elbow": r3(M.T @ (np.array([0, -0.6, 0]) + hdir(deg + 60) * 0.5)),
            "blade": r3(M.T @ hdir(deg + 10, -0.25))}           # a second blade (if any) carries on out past the hand

def kneedir(deg, out): return r3(hdir(deg + out))

def key(t, ease, yaw, sy, lean, drop, rf, lf, S, F, head=None, rlift=0.0, llift=0.0, over=None):
    """yaw / sy = hips / spine yaw (deg, cumulative); lean deg toward the target; drop = hips down (m);
    S = sword (hand_deg, blade_deg, h[, elbow]); F = free hand angle; over = foot the hips sit over (spins)."""
    if t > 0: drop += 0.08
    if ease == "snap": lean += 8                                          # throw the weight into every hit
    tot = yaw + sy
    w = ((tot + 180) % 360) - 180
    hy = max(-80, min(80, -w)) if head is None else head
    if over is None: mx, mz = (rf[0] + lf[0]) / 2, (rf[1] + lf[1]) / 2
    else:
        o = rf if over == "R" else lf; q = lf if over == "R" else rf
        mx, mz = o[0] * 0.75 + q[0] * 0.25, o[1] * 0.75 + q[1] * 0.25
    # lean toward the target, split hips / spine; it tips sideways when turned, so ease it off past 60 deg
    lk = max(0.35, math.cos(math.radians(min(abs(w), 90)) ) ** 0.5)
    hr, sp = [yaw, lean * 0.55 * lk, 0], [sy, lean * 0.45 * lk, 0]
    M = chest_M(hr, sp)
    if callable(S): S = S(tot)
    n = round(yaw / 360.0); fy = 360 * n + 0.6 * (yaw - 360 * n)       # feet follow every full turn, part of the rest
    if over is not None: fy = yaw                                         # spinning: pivot on the ball of the foot with the hips
    s = sword(M, *S)
    return {"t": round(t, 3), "ease": ease,
            "hips": {"pos": r3([mx, -drop, mz]), "rot": r3(hr)}, "spine": r3(sp), "head": r3([hy, -10 - lean * 0.12, 0]),
            "R": s, "L": free(M, F),
            "fR": {"ankle": r3([rf[0], 0.104 + rlift, rf[1]]), "knee": kneedir(fy, -12), "yaw": round(fy - 5, 1), "pitch": 25 if rlift > 0.05 else 0},
            "fL": {"ankle": r3([lf[0], 0.104 + llift, lf[1]]), "knee": kneedir(fy, 25), "yaw": round(fy + 30, 1), "pitch": 25 if llift > 0.05 else 0}}

def pivot(foot, other, deg):
    a = math.radians(deg); x, z = other[0] - foot[0], other[1] - foot[1]
    return (foot[0] + x * math.cos(a) + z * math.sin(a), foot[1] - x * math.sin(a) + z * math.cos(a))

RF0, LF0 = (-0.15, 0.28), (0.18, -0.34)      # guard: sword-side foot forward
RF1 = (-0.22, 0.80)                            # step in
GUARD = (-5, 10, -0.05)                        # sword angles at guard: hand just right of centre, blade at target
def lf_at(deg, piv=RF1, base=LF0): return pivot(piv, base, deg)

# forehand sweep beats (right -> left): load (hand right-back), contact (front), through (left)
F_LOAD  = (-75, -135, 0.0)      # hand out right, blade trailing back-right
F_HIT   = (-10, 15, 0.0)        # blade just past the hand: the wrist snaps it through
F_THRU  = (70, 105, 0.0)
# backhand beats (left -> right)
B_LOAD  = (55, 130, 0.02, "back")
B_HIT   = (10, -15, 0.0, "back")
B_THRU  = (-70, -105, 0.0, "back")
def h(beat, dh): return (beat[0], beat[1], beat[2] + dh) + tuple(beat[3:])
# spin transit beats, relative to the chest heading tot: the blade goes OVER the head, never through the body
def OVER(side=1):        # side 1 = turning left (forehand spin), -1 = turning right (backhand spin)
    return lambda tot: (tot + 15 * side, tot + 180, 0.50, "up" if side > 0 else "upb", 0.45, 0.22)
def TRAIL_F(dh=0.0):     # forehand load riding the turn: hand right, blade trailing back-right
    return lambda tot: (tot - 80, tot - 135, dh)
def TRAIL_B(dh=0.0):     # backhand load riding a right turn: hand left, blade trailing back-left
    return lambda tot: (tot + 60, tot + 130, dh + 0.02, "back")

CL = {}
CL["ag_wide_sweep"] = {"name": "Wide sweep (step-in forehand)", "length": 0.7, "keys": [
  key(0.00, "inout", 15, 5, 16, 0.14, RF0, LF0, GUARD, 60),
  key(0.15, "in", -50, -30, 12, 0.20, RF0, LF0, F_LOAD, 15),                         # coil right, free hand aims
  key(0.23, "linear", -55, -33, 14, 0.22, (-0.20, 0.52), LF0, F_LOAD, 10, rlift=0.10),  # foot leaves, still coiled
  key(0.29, "snap", 0, 5, 34, 0.32, RF1, LF0, F_HIT, 100),                           # CONTACT: foot lands, hips whip
  key(0.37, "out", 50, 30, 36, 0.35, RF1, LF0, F_THRU, 160),                         # overshoot
  key(0.70, "inout", 35, 20, 26, 0.28, RF1, LF0, h(F_THRU, -0.05), 130),
]}
CL["ag_sweep_return"] = {"name": "Sweep + backhand return", "length": 0.95, "keys": [
  key(0.00, "inout", 15, 5, 16, 0.14, RF0, LF0, GUARD, 60),
  key(0.14, "in", -50, -30, 12, 0.22, RF0, LF0, F_LOAD, 15),
  key(0.22, "snap", 0, 5, 32, 0.30, RF1, LF0, F_HIT, 100),
  key(0.30, "out", 55, 32, 34, 0.33, RF1, LF0, B_LOAD, 150),                         # carries through into the backhand load
  key(0.39, "in", 60, 34, 32, 0.34, RF1, LF0, h(B_LOAD, 0.03), 120),                 # moving hold: coil for the return
  key(0.46, "snap", 0, -8, 34, 0.35, RF1, (0.08, -0.12), B_HIT, 60),                 # BACKHAND contact, back foot slides up
  key(0.55, "out", -50, -30, 36, 0.36, RF1, (0.08, -0.12), B_THRU, 30),
  key(0.95, "inout", -30, -15, 24, 0.27, RF1, (0.08, -0.12), h(B_THRU, -0.05), 60),
]}
# forehand, then the follow-through is the backhand load: reverse spin (to the right) whips the backhand round
CL["ag_spin_backhand"] = {"name": "Forehand into spinning backhand", "length": 1.1, "keys": [
  key(0.00, "inout", 15, 5, 16, 0.14, RF0, LF0, GUARD, 60),
  key(0.14, "in", -50, -30, 12, 0.22, RF0, LF0, F_LOAD, 15),
  key(0.22, "snap", 0, 5, 32, 0.30, RF1, LF0, F_HIT, 100),
  key(0.30, "out", 55, 32, 34, 0.33, RF1, LF0, B_LOAD, 150),
  key(0.41, "linear", -80, -10, 16, 0.22, RF1, lf_at(-110), OVER(-1), -20, llift=0.18, head=-70, over="R"),       # reverse turn: blade over the head
  key(0.51, "in", -200, 10, 18, 0.26, RF1, lf_at(-230), TRAIL_B(), -120, llift=0.10, head=70, over="R"),          # head whips round, blade drops into the backhand load
  key(0.60, "snap", -355, -8, 34, 0.34, RF1, lf_at(-360), (10, -15, 0.0, "back"), -300),   # BACKHAND contact (one full turn)
  key(0.69, "out", -405, -30, 36, 0.36, RF1, lf_at(-360), (-70, -105, 0.0, "back"), -330),
  key(1.10, "inout", -390, -15, 24, 0.28, RF1, lf_at(-360), (-60, -95, -0.05, "back"), -300),
]}
# low forehand, keep turning left (same way), rise, high forehand
def spin_trail(yaw, sy, dh=0.0): tot = yaw + sy; return (tot - 90, tot - 140, dh)
CL["ag_low_high_spin"] = {"name": "Low sweep, rising spin to a high sweep", "length": 1.15, "keys": [
  key(0.00, "inout", 15, 5, 16, 0.14, RF0, LF0, GUARD, 60),
  key(0.15, "in", -50, -30, 28, 0.34, RF0, LF0, h(F_LOAD, -0.22), 15),
  key(0.23, "snap", 0, 5, 52, 0.50, RF1, LF0, h(F_HIT, -0.40), 100),                # LOW sweep, deep and long
  key(0.31, "out", 55, 32, 52, 0.52, RF1, LF0, h(F_THRU, -0.38), 160),
  key(0.45, "linear", 150, 20, 22, 0.22, RF1, lf_at(100), OVER(), 150 + 100, llift=0.20, head=65, over="R"),
  key(0.55, "in", 250, -20, 10, 0.10, RF1, lf_at(215), TRAIL_F(0.18), 250 + 110, llift=0.12, head=-70, over="R"),
  key(0.63, "snap", 360, 5, 18, 0.16, RF1, lf_at(360), h(F_HIT, 0.24), 360 + 100),         # HIGH sweep at head height
  key(0.72, "out", 410, 30, 20, 0.20, RF1, lf_at(360), h(F_THRU, 0.22), 360 + 160),
  key(1.15, "inout", 395, 20, 22, 0.26, RF1, lf_at(360), h(F_THRU, 0.0), 360 + 130),
]}
# cyclone: forehand, turn, forehand, step through, travelling turn, low forehand
LP = lf_at(360)
LP2 = (0.12, 1.00)                     # left foot steps through after sweep 2 and becomes the new pivot
RF2 = (-0.30, 0.42)
CL["ag_cyclone"] = {"name": "Cyclone (double spin, sweep on each)", "length": 1.5, "keys": [
  key(0.00, "inout", 15, 5, 16, 0.14, RF0, LF0, GUARD, 60),
  key(0.17, "in", -55, -32, 14, 0.24, RF0, LF0, F_LOAD, 15),
  key(0.25, "snap", 0, 5, 32, 0.30, RF1, LF0, F_HIT, 100),
  key(0.33, "out", 60, 32, 32, 0.30, RF1, LF0, F_THRU, 170),
  key(0.45, "linear", 160, 20, 20, 0.22, RF1, lf_at(100), OVER(), 160 + 110, llift=0.20, head=65, over="R"),
  key(0.55, "in", 255, -22, 20, 0.24, RF1, lf_at(220), TRAIL_F(), 255 + 110, llift=0.10, head=-70, over="R"),
  key(0.62, "snap", 360, 5, 32, 0.30, RF1, LP, F_HIT, 360 + 100),                          # sweep 2
  key(0.71, "out", 420, 32, 30, 0.28, RF1, (0.16, 0.45), F_THRU, 360 + 170, llift=0.16, over="R"),   # step through
  key(0.80, "linear", 500, 20, 22, 0.24, pivot(LP2, RF1, 80), LP2, OVER(), 500 + 110, rlift=0.20, head=65, over="L"),
  key(0.91, "in", 610, -22, 28, 0.32, pivot(LP2, RF1, 200), LP2, TRAIL_F(-0.15), 610 + 110, rlift=0.12, head=-70, over="L"),
  key(1.00, "snap", 720, 5, 50, 0.46, RF2, LP2, h(F_HIT, -0.30), 720 + 100),               # sweep 3, LOW finish
  key(1.08, "out", 775, 32, 54, 0.50, RF2, LP2, h(F_THRU, -0.30), 720 + 160),
  key(1.50, "inout", 760, 22, 40, 0.42, RF2, LP2, h(F_THRU, -0.22), 720 + 130),
]}
# double backhand spin: start loaded left, backhand, keep turning right, backhand again
CL["ag_backhand_spin"] = {"name": "Double backhand spin", "length": 1.1, "keys": [
  key(0.00, "inout", 15, 5, 16, 0.14, RF0, LF0, GUARD, 60),
  key(0.15, "in", 60, 30, 12, 0.22, RF0, LF0, B_LOAD, 0),                               # wind the blade over to the left
  key(0.23, "snap", 0, -8, 32, 0.32, RF1, LF0, B_HIT, 60),                              # backhand 1
  key(0.31, "out", -55, -32, 34, 0.34, RF1, LF0, B_THRU, 20),
  key(0.43, "linear", -150, -20, 18, 0.22, RF1, lf_at(-110), OVER(-1), -100, llift=0.18, head=-70, over="R"),
  key(0.53, "in", -250, 15, 16, 0.26, RF1, lf_at(-220), TRAIL_B(), -200, llift=0.10, head=70, over="R"),
  key(0.61, "snap", -360, -8, 34, 0.34, RF1, lf_at(-360), (10, -15, 0.0, "back"), -300),  # backhand 2 (one full turn)
  key(0.70, "out", -410, -32, 38, 0.36, RF1, lf_at(-360), (-70, -105, 0.0, "back"), -330),
  key(1.10, "inout", -395, -16, 26, 0.28, RF1, lf_at(-360), (-60, -95, -0.05, "back"), -300),
]}
for c in CL.values():
    c["cat"] = "Aggressive"; c["arm_space"] = "chest"; c["approved"] = False
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "moves.anim3d.json")
if len(sys.argv) > 1:                                      # a scratch spec file (previews)
    json.dump({"format": "pb_anim3d", "version": 1, "notes": "draft", "clips": CL}, open(sys.argv[1], "w"), indent=1)
else:
    spec = json.load(open(OUT, encoding="utf-8"))
    for c, v in CL.items():
        v["approved"] = bool((spec["clips"].get(c) or {}).get("approved"))
        spec["clips"][c] = v
    json.dump(spec, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print("wrote", list(CL))
