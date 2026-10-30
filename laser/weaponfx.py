"""
Weapons — 2.5D signature weapons for the FX Kit "technique" primitive,
painted by hand at the same standard as the sword techniques (laser/swordfx.py,
whose frame, pen and timeline they share).

Every weapon is a flat model (laser-cut parts: blade, edge, guard, grip,
accent, dark, glowing gem / spirit parts) lifted into 3D and drawn through a
small camera: it can spin round its own long axis (yaw), tilt toward or away
from the camera (pitch, with perspective: the near end grows, the far end
shrinks) and sit nearer or further away (depth).  The face toward the camera
is lit by how square-on it is, the far face shows as the blade's side wall
when it turns, and a glint runs along the edge as it spins.

Two modes (params.w_mode):

  signature   the weapon materialises, plays its own signature sequence
              (WEAPONS[style]: a pose track per weapon slot, timed events,
              shots for the guns), holds its last pose, then dissolves
  hold        the weapon simply appears in the anchor's hand in its ready
              pose and stays for Hold ticks: animate it with keyframes

Weapon controls (all numbers, so every one can be keyframed — fxkit KEY
rules; FX Studio's weapon panel):

  w_scale     size multiplier (1 = the weapon's own size)
  w_flip_x    1 = as authored, -1 = mirrored left / right on screen (round
              the anchor); keying between them turns the weapon over like a
              card (it squashes through 0)
  w_flip_y    the same for up / down
  w_yaw       spin round its own long axis, degrees (90 = edge on, 180 = the
              back face)
  w_pitch     tilt toward (+) / away from (-) the camera, degrees
  w_spin      extra yaw per tick (a continuous 3D spin)
  w_depth     how far behind (+) / in front of (-) its plane it sits (0 =
              in plane; 1 = twice as far: half size)
  w_weight    0..1: momentum.  0 = rigid (the angle is exactly the pose's);
              above 0 the angle chases the pose through a damped spring and
              the hand's acceleration swings it like a rod held at one end:
              a rising slash drags the tip down behind the hand, carries it
              on past the peak and pivots it back.  Heavier = slower spring,
              more lag and overshoot (DRAG_HZ, DRAG_ZETA)
  w_plane     swing plane tilt, degrees out of the screen: 0 = the swing
              stays in the screen plane; 90 = a horizontal swing, so the
              blade shrinks as it points at (or away from) the camera and
              stretches out again toward the target (perspective too)
  w_plane_roll  turns that plane on screen, degrees (diagonal swings)
  w_side      "front": the blade passes between the fighter and the camera
              (its near end grows); "behind": it passes behind (the far end
              shrinks and the weapon draws behind the fighter while it is
              round the far side, BEHIND_Z)

Hold mode follows the arm: the weapon lies along the rig's own blade line,
hand -> wtip of the frame on show (haL -> wtip2 when the effect is anchored
on haL), its grip on the hand.  A rig without that tip keeps the ready pose.
  rotation_deg  turns the whole weapon and its sequence (shared technique field)

Shared technique fields: length = weapon length px, thickness = blade
half-width px, radius = reach / range px (thrown weapons, shots), span =
shot spread degrees, swing_ticks = ticks per beat of the sequence, hold_ticks
= how long the weapon stays after its sequence (hold mode: how long it is
held), density = sparks / debris / petals.

Hits: a blade hits along the visible blade while its sequence plays (hold
mode: while it is held), every event (ground slam, flash cuts, X flash,
light pillar, rune bolts ...) hits where it goes off, and every shot hits
once and stops there (give the effect Pierce and a short Re-hit).

The roster (WEAPONS): the seven requested signature weapons plus one per
character in the game (see FX_GUIDE.md 12d).  Everything is a pure function
of the instance (age, seed, the anchor's and the target's paths), so FX
Studio's port (tools/fx/studio/weaponfx.js) draws the same pixels.  Keep the
two in step (tools/fx/check_parity.py compares the tables).
"""

import math

from . import fxkit as F
from . import swordfx as S

STYLES = ("buster_sword", "masamune", "oath_oblivion", "crescent_scythe", "scissor_blade", "gungnir",
          "light_pistols", "crimson_fang", "arc_carbine", "void_cannon", "phase_kunai", "astral_staff",
          "phantom_greatsword", "neon_uzis", "halo_chakram", "wisp_rapier", "pulse_bow", "rune_reaver",
          "nodachi", "earth_cleaver", "void_sniper")

HU = 10.0            # pose unit (px at size 1): where the hand holds the weapon
SUMMON = 8           # ticks the weapon takes to materialise
DISMISS = 12         # ticks it takes to dissolve
FOCAL = 4.0          # camera distance, times the weapon length (perspective strength)
THICK_K = 0.5        # side-wall depth, times the half-width
TRAIL_N = 6          # ticks of swept trail behind a swinging blade
TRAIL_SUB = 5        # trail samples per tick
TRAIL_BAND = 0.62    # the trail runs from here to the tip (fraction of the blade)
EVT_HIT = 4          # ticks an event keeps hitting after it goes off
BEAM_T = 14          # ticks a beam shot lasts
RAIL_T = 10          # ticks a void rail line lasts
LINE_T = dict(beam=BEAM_T, rail=RAIL_T)   # shots that are an instant line to the end of their range
LINE_HW = dict(beam=7.0, rail=5.0)        # their hit half-width (px, times the shot size)
IMPLODE_IN = 10      # ticks a void implosion takes to collapse before it pops
VOID = (10, 4, 18)   # the void's black core (drawn over, not added)
IMPACT_LIFE = 16
TAIL = 48            # afterglow ticks after the weapon is gone (events, shots)
EVT_LIFE = dict(slam=28, cuts=18, xflash=16, snip=16, pillar=30, runes=36, glyph=22, burst=16, charge=0, petals=30,
                blink=12, implode=26)
EVT_R = dict(slam=46, cuts=26, xflash=20, snip=22, pillar=26, runes=18, glyph=24, burst=20, charge=0, petals=0, blink=0,
             implode=0)
SHOTS = dict(light=dict(speed=15, size=1.1), spark=dict(speed=18, size=0.9), neon=dict(speed=17, size=0.75),
             arrow=dict(speed=14, size=1.0), beam=dict(speed=0, size=1.6), rail=dict(speed=0, size=0.7))
GLOWS = ("gem", "spirit")
# Weight (w_weight): the spring the weapon's angle chases its pose through.
DRAG_HZ = (14.0, 4.5)      # spring frequency (Hz) from weight 0+ (snaps) to 1 (lags)
DRAG_ZETA = (0.9, 0.42)    # damping from weight 0+ to 1 (heavy overshoots its peak)
DRAG_SUB = 4               # spring steps per tick
DRAG_MAX = 120.0           # degrees the blade may trail its pose
GRIP_SMOOTH = 0.5          # low-pass on the hand's path (rig frames step)
GRIP_ACC_MAX = 0.6         # hand acceleration cap, weapon lengths per tick^2
BEHIND_Z = 0.3             # Swing side behind: draws behind the fighter past this far round

# ---------------------------------------------------------------- models
# Each part: (role, ((u, v), ...)).  u runs along the weapon (0 = the hand,
# 1 = the tip, negative = pommel side) in weapon lengths; v across it in
# half-widths (vs "w": thickness px) or, for discs and bows (vs "l"), in
# weapon lengths too.  +v is the edge side (down when the weapon points
# forward).  hit = (u0, v0, u1, v1, half-width in v units): the cutting line.
# muzzle = where shots leave.  mat = the solid colours of the roles.
MODELS = {
    "buster_sword": dict(vs="w", blade=True, hit=(0.06, 0.0, 1.0, 0.0, 0.8), muzzle=(1.0, 0.0),
                         mat=dict(blade=(150, 160, 172), edge=(228, 234, 240), guard=(118, 122, 130),
                                  grip=(70, 52, 40), dark=(30, 30, 36), accent=(150, 160, 172), gem=(90, 255, 140)),
                         parts=(("grip", ((-0.28, -0.16), (0.0, -0.16), (0.0, 0.16), (-0.28, 0.16))),
                                ("guard", ((-0.33, -0.24), (-0.28, -0.24), (-0.28, 0.24), (-0.33, 0.24))),
                                ("guard", ((0.0, -0.6), (0.06, -0.6), (0.06, 0.6), (0.0, 0.6))),
                                ("blade", ((0.06, -0.8), (0.9, -0.8), (1.0, 0.8), (0.06, 0.8))),
                                ("edge", ((0.06, 0.58), (0.97, 0.58), (1.0, 0.8), (0.06, 0.8))),
                                ("dark", ((0.1, -0.42), (0.16, -0.42), (0.16, 0.0), (0.1, 0.0))),
                                ("dark", ((0.19, -0.42), (0.25, -0.42), (0.25, 0.0), (0.19, 0.0))),
                                ("gem", ((0.115, -0.32), (0.145, -0.32), (0.145, -0.1), (0.115, -0.1))))),
    "masamune": dict(vs="w", blade=True, hit=(0.03, 0.0, 1.0, -2.0, 1.0), muzzle=(1.0, -2.0),
                     mat=dict(blade=(200, 206, 216), edge=(245, 248, 252), guard=(150, 140, 110), grip=(60, 60, 72),
                              dark=(30, 30, 36), accent=(150, 140, 110), gem=(190, 220, 255)),
                     parts=(("grip", ((-0.17, -0.38), (0.0, -0.34), (0.0, 0.34), (-0.17, 0.38))),
                            ("guard", ((-0.01, -1.0), (0.02, -1.0), (0.03, 0.0), (0.02, 1.0), (-0.01, 1.0), (-0.02, 0.0))),
                            ("blade", ((0.02, -0.45), (0.3, -0.62), (0.6, -0.98), (0.85, -1.45), (1.0, -2.0),
                                       (0.86, -1.1), (0.6, -0.1), (0.3, 0.45), (0.02, 0.5))),
                            ("edge", ((0.02, 0.22), (0.3, 0.16), (0.6, -0.34), (0.85, -1.25), (1.0, -2.0),
                                      (0.86, -1.1), (0.6, -0.1), (0.3, 0.45), (0.02, 0.5))))),
    "oathkeeper": dict(vs="w", blade=True, hit=(0.04, 0.0, 1.03, 0.0, 1.0), muzzle=(1.0, 0.0),
                       mat=dict(blade=(226, 230, 238), edge=(255, 255, 255), guard=(206, 214, 230), grip=(70, 86, 140),
                                dark=(40, 40, 60), accent=(236, 240, 250), gem=(150, 220, 255)),
                       parts=(("grip", ((-0.2, -0.3), (0.0, -0.3), (0.0, 0.3), (-0.2, 0.3))),
                              ("guard", ((-0.24, -0.9), (0.0, -1.15), (0.05, -0.6), (0.05, 0.6), (0.0, 1.15),
                                         (-0.24, 0.9), (-0.24, 0.7), (-0.03, 0.8), (-0.03, -0.8), (-0.24, -0.7))),
                              ("blade", ((0.05, -0.28), (0.86, -0.28), (0.86, 0.28), (0.05, 0.28))),
                              ("accent", ((0.78, -0.28), (0.84, -1.5), (0.91, -0.7), (0.99, -1.7), (1.0, 0.28),
                                          (0.78, 0.28))),
                              ("blade", ((0.86, -0.4), (1.03, 0.0), (0.86, 0.4))),
                              ("gem", ((-0.38, 0.95), (-0.33, 1.4), (-0.28, 0.95), (-0.33, 0.62))))),
    "oblivion": dict(vs="w", blade=True, hit=(0.04, 0.0, 1.03, 0.0, 1.0), muzzle=(1.0, 0.0),
                     mat=dict(blade=(56, 52, 66), edge=(150, 150, 170), guard=(40, 36, 50), grip=(110, 30, 40),
                              dark=(20, 18, 26), accent=(70, 64, 84), gem=(255, 80, 110)),
                     parts=(("grip", ((-0.2, -0.3), (0.0, -0.3), (0.0, 0.3), (-0.2, 0.3))),
                            ("guard", ((-0.24, -0.95), (0.0, -1.2), (0.05, -0.6), (0.05, 0.6), (0.0, 1.2),
                                       (-0.24, 0.95), (-0.24, 0.72), (-0.03, 0.82), (-0.03, -0.82), (-0.24, -0.72))),
                            ("blade", ((0.05, -0.3), (0.86, -0.3), (0.86, 0.3), (0.05, 0.3))),
                            ("accent", ((0.76, -0.3), (0.8, -1.25), (0.86, -0.7), (0.93, -1.6), (1.0, -0.3),
                                        (1.0, 0.3), (0.76, 0.3))),
                            ("edge", ((0.86, -0.42), (1.03, 0.0), (0.86, 0.42))),
                            ("gem", ((-0.38, 0.95), (-0.33, 1.4), (-0.28, 0.95), (-0.33, 0.62))))),
    "crescent_scythe": dict(vs="w", blade=True, hit=(0.95, 0.4, 0.56, 7.1, 1.4), muzzle=(1.0, 0.0),
                            mat=dict(blade=(52, 50, 58), edge=(230, 232, 240), guard=(150, 20, 34), grip=(36, 34, 40),
                                     dark=(20, 18, 22), accent=(200, 26, 44), gem=(255, 60, 80)),
                            parts=(("grip", ((-0.6, -0.12), (0.9, -0.12), (0.9, 0.12), (-0.6, 0.12))),
                                   ("accent", ((-0.62, -0.16), (-0.5, -0.16), (-0.5, 0.16), (-0.62, 0.16))),
                                   ("guard", ((0.82, -0.4), (1.0, -0.4), (1.0, 0.4), (0.82, 0.4))),
                                   ("blade", ((0.98, 0.3), (0.92, 3.0), (0.78, 5.5), (0.56, 7.3), (0.63, 5.2),
                                              (0.79, 2.8), (0.85, 0.3))),
                                   ("edge", ((0.56, 7.3), (0.63, 5.2), (0.79, 2.8), (0.85, 0.3), (0.89, 0.3),
                                             (0.84, 2.9), (0.69, 5.4))),
                                   ("gem", ((0.86, -0.18), (0.95, -0.18), (0.95, 0.18), (0.86, 0.18))))),
    "scissor_a": dict(vs="w", blade=True, hit=(0.05, -0.4, 1.0, -0.05, 0.6), muzzle=(1.0, 0.0),
                      mat=dict(blade=(196, 28, 40), edge=(250, 236, 236), guard=(30, 28, 32), grip=(24, 22, 26),
                               dark=(16, 14, 18), accent=(196, 28, 40), gem=(255, 70, 70)),
                      parts=(("grip", ((-0.4, -0.1), (-0.22, -0.95), (-0.04, -0.82), (-0.04, -0.16), (-0.2, -0.56),
                                       (-0.3, -0.1))),
                             ("blade", ((0.05, -0.92), (0.7, -0.92), (1.0, -0.1), (1.0, 0.0), (0.05, 0.0))),
                             ("edge", ((0.05, -0.16), (0.98, -0.16), (1.0, 0.0), (0.05, 0.0))),
                             ("guard", ((-0.06, -0.42), (0.06, -0.42), (0.06, 0.0), (-0.06, 0.0))))),
    "scissor_b": dict(vs="w", blade=True, hit=(0.05, 0.4, 1.0, 0.05, 0.6), muzzle=(1.0, 0.0),
                      mat=dict(blade=(176, 20, 32), edge=(250, 236, 236), guard=(30, 28, 32), grip=(24, 22, 26),
                               dark=(16, 14, 18), accent=(176, 20, 32), gem=(255, 70, 70)),
                      parts=(("grip", ((-0.4, 0.1), (-0.22, 0.95), (-0.04, 0.82), (-0.04, 0.16), (-0.2, 0.56),
                                       (-0.3, 0.1))),
                             ("blade", ((0.05, 0.0), (1.0, 0.0), (0.82, 0.6), (0.4, 0.92), (0.05, 0.92))),
                             ("edge", ((0.05, 0.0), (1.0, 0.0), (0.97, 0.12), (0.05, 0.14))),
                             ("guard", ((-0.06, 0.0), (0.06, 0.0), (0.06, 0.42), (-0.06, 0.42))),
                             ("gem", ((-0.03, 0.12), (0.03, 0.12), (0.03, 0.3), (-0.03, 0.3))))),
    "gungnir": dict(vs="w", blade=True, hit=(0.6, 0.0, 1.0, 0.0, 1.2), muzzle=(1.0, 0.0),
                    mat=dict(blade=(236, 200, 96), edge=(255, 250, 220), guard=(200, 150, 60), grip=(150, 110, 50),
                             dark=(60, 40, 20), accent=(236, 200, 96), gem=(120, 220, 255)),
                    parts=(("grip", ((-0.45, -0.22), (0.72, -0.22), (0.72, 0.22), (-0.45, 0.22))),
                           ("guard", ((-0.45, -0.32), (-0.53, 0.0), (-0.45, 0.32))),
                           ("guard", ((0.68, -0.62), (0.74, -0.62), (0.74, 0.62), (0.68, 0.62))),
                           ("blade", ((0.74, -0.9), (0.8, -1.7), (0.84, -0.7), (1.0, 0.0), (0.84, 0.7), (0.8, 1.7),
                                      (0.74, 0.9))),
                           ("edge", ((0.82, -0.22), (1.0, 0.0), (0.82, 0.22))),
                           ("gem", ((0.08, -0.08), (0.62, -0.08), (0.62, 0.08), (0.08, 0.08))))),
    "light_pistol": dict(vs="w", blade=False, hit=(0.0, 0.0, 1.0, 0.0, 0.5), muzzle=(1.0, -0.05),
                         mat=dict(blade=(236, 238, 244), edge=(255, 255, 255), guard=(180, 150, 80), grip=(60, 64, 80),
                                  dark=(30, 32, 40), accent=(214, 180, 96), gem=(170, 255, 250)),
                         parts=(("grip", ((-0.1, 0.2), (0.1, 0.2), (0.02, 1.6), (-0.18, 1.5))),
                                ("blade", ((-0.2, -0.5), (0.8, -0.5), (0.95, -0.25), (0.95, 0.3), (-0.2, 0.3))),
                                ("accent", ((-0.1, -0.66), (0.6, -0.66), (0.7, -0.46), (-0.1, -0.46))),
                                ("guard", ((0.95, -0.18), (1.0, -0.18), (1.0, 0.12), (0.95, 0.12))),
                                ("gem", ((0.2, -0.22), (0.72, -0.22), (0.72, 0.04), (0.2, 0.04))))),
    "crimson_fang": dict(vs="w", blade=True, hit=(0.05, 0.0, 1.0, 0.0, 0.6), muzzle=(1.0, 0.0),
                         mat=dict(blade=(176, 168, 172), edge=(255, 236, 236), guard=(110, 20, 28), grip=(50, 20, 24),
                                  dark=(30, 10, 14), accent=(140, 24, 32), gem=(255, 40, 50)),
                         parts=(("grip", ((-0.22, -0.2), (0.0, -0.2), (0.0, 0.2), (-0.22, 0.2))),
                                ("guard", ((-0.28, -0.34), (-0.22, -0.34), (-0.22, 0.34), (-0.28, 0.34))),
                                ("guard", ((0.0, -1.4), (0.05, -1.2), (0.05, 1.2), (0.0, 1.4))),
                                ("blade", ((0.05, -0.6), (0.9, -0.55), (1.0, 0.0), (0.9, 0.55), (0.05, 0.6))),
                                ("edge", ((0.05, 0.42), (0.9, 0.4), (1.0, 0.0), (0.9, 0.55), (0.05, 0.6))),
                                ("gem", ((0.08, -0.15), (0.8, -0.12), (0.8, 0.12), (0.08, 0.15))))),
    "arc_carbine": dict(vs="w", blade=False, hit=(0.0, 0.0, 1.0, 0.0, 0.5), muzzle=(1.0, -0.15),
                        mat=dict(blade=(70, 86, 104), edge=(200, 220, 236), guard=(44, 50, 60), grip=(36, 40, 48),
                                 dark=(20, 22, 28), accent=(90, 200, 255), gem=(120, 230, 255)),
                        parts=(("grip", ((-0.45, -0.3), (-0.15, -0.35), (-0.15, 0.35), (-0.45, 0.7))),
                               ("blade", ((-0.15, -0.45), (0.55, -0.45), (0.6, 0.35), (-0.15, 0.35))),
                               ("grip", ((0.0, 0.35), (0.12, 0.35), (0.06, 1.2), (-0.06, 1.15))),
                               ("guard", ((0.22, 0.35), (0.34, 0.35), (0.38, 1.1), (0.26, 1.15))),
                               ("guard", ((0.55, -0.3), (1.0, -0.3), (1.0, 0.0), (0.55, 0.0))),
                               ("gem", ((0.1, -0.3), (0.5, -0.3), (0.5, -0.1), (0.1, -0.1))))),
    "void_cannon": dict(vs="w", blade=False, hit=(0.0, 0.0, 1.0, 0.0, 0.8), muzzle=(1.0, 0.0),
                        mat=dict(blade=(58, 30, 82), edge=(170, 120, 220), guard=(30, 18, 44), grip=(24, 16, 34),
                                 dark=(12, 8, 18), accent=(110, 60, 160), gem=(200, 110, 255)),
                        parts=(("blade", ((-0.3, -0.8), (0.7, -0.9), (1.0, -0.6), (1.0, 0.6), (0.7, 0.9), (-0.3, 0.8))),
                               ("accent", ((0.3, -0.96), (0.38, -0.96), (0.38, 0.96), (0.3, 0.96))),
                               ("accent", ((0.55, -0.98), (0.62, -0.98), (0.62, 0.98), (0.55, 0.98))),
                               ("dark", ((0.82, -0.45), (1.0, -0.45), (1.0, 0.45), (0.82, 0.45))),
                               ("gem", ((0.86, -0.3), (1.0, -0.3), (1.0, 0.3), (0.86, 0.3))))),
    "void_sniper": dict(vs="w", blade=False, hit=(0.0, 0.0, 1.0, 0.0, 0.6), muzzle=(1.0, 0.0),
                        mat=dict(blade=(34, 24, 46), edge=(150, 110, 200), guard=(22, 16, 30), grip=(18, 12, 24),
                                 dark=(8, 6, 12), accent=(120, 60, 180), gem=(190, 100, 255)),
                        parts=(("grip", ((-0.5, -0.7), (-0.12, -0.8), (-0.12, 0.6), (-0.3, 0.6), (-0.42, 1.5),
                                         (-0.52, 1.4))),
                               ("blade", ((-0.12, -0.9), (0.38, -0.9), (0.42, 0.7), (-0.12, 0.7))),
                               ("grip", ((-0.02, 0.7), (0.08, 0.7), (0.03, 2.0), (-0.07, 1.9))),
                               ("guard", ((0.13, 0.7), (0.22, 0.7), (0.22, 1.5), (0.13, 1.5))),
                               ("guard", ((0.06, -1.1), (0.1, -1.1), (0.1, -0.9), (0.06, -0.9))),
                               ("guard", ((0.22, -1.1), (0.26, -1.1), (0.26, -0.9), (0.22, -0.9))),
                               ("dark", ((0.0, -2.0), (0.32, -2.0), (0.32, -1.1), (0.0, -1.1))),
                               ("gem", ((0.27, -1.9), (0.32, -1.9), (0.32, -1.2), (0.27, -1.2))),
                               ("blade", ((0.38, -0.45), (1.0, -0.35), (1.0, 0.35), (0.38, 0.45))),
                               ("accent", ((0.5, -0.62), (0.55, -0.62), (0.55, 0.62), (0.5, 0.62))),
                               ("accent", ((0.64, -0.58), (0.69, -0.58), (0.69, 0.58), (0.64, 0.58))),
                               ("accent", ((0.78, -0.54), (0.83, -0.54), (0.83, 0.54), (0.78, 0.54))),
                               ("gem", ((0.42, -0.14), (0.93, -0.1), (0.93, 0.1), (0.42, 0.14))),
                               ("dark", ((0.93, -0.55), (1.0, -0.55), (1.0, 0.55), (0.93, 0.55))))),
    "kunai": dict(vs="w", blade=True, hit=(0.0, 0.0, 1.0, 0.0, 0.7), muzzle=(1.0, 0.0),
                  mat=dict(blade=(84, 90, 104), edge=(220, 228, 240), guard=(60, 64, 76), grip=(140, 40, 50),
                           dark=(20, 22, 28), accent=(140, 40, 50), gem=(140, 255, 220)),
                  parts=(("grip", ((-0.3, -0.15), (0.0, -0.15), (0.0, 0.15), (-0.3, 0.15))),
                         ("guard", ((-0.44, -0.3), (-0.3, -0.3), (-0.3, 0.3), (-0.44, 0.3))),
                         ("blade", ((0.0, -0.3), (0.35, -0.75), (1.0, 0.0), (0.35, 0.75), (0.0, 0.3))),
                         ("edge", ((0.05, -0.08), (1.0, 0.0), (0.05, 0.08))),
                         ("gem", ((-0.4, -0.12), (-0.34, -0.12), (-0.34, 0.12), (-0.4, 0.12))))),
    "astral_staff": dict(vs="w", blade=True, hit=(0.6, 0.0, 1.0, 0.0, 1.4), muzzle=(1.0, 0.0),
                         mat=dict(blade=(120, 92, 70), edge=(240, 230, 210), guard=(214, 190, 120), grip=(96, 70, 52),
                                  dark=(40, 30, 24), accent=(214, 190, 120), gem=(160, 200, 255)),
                         parts=(("grip", ((-0.6, -0.18), (0.78, -0.15), (0.78, 0.15), (-0.6, 0.18))),
                                ("accent", ((0.2, -0.24), (0.26, -0.24), (0.26, 0.24), (0.2, 0.24))),
                                ("accent", ((-0.35, -0.24), (-0.29, -0.24), (-0.29, 0.24), (-0.35, 0.24))),
                                ("guard", ((0.72, -0.25), (0.78, -1.4), (0.9, -1.65), (0.84, -0.9), (0.8, -0.25))),
                                ("guard", ((0.72, 0.25), (0.78, 1.4), (0.9, 1.65), (0.84, 0.9), (0.8, 0.25))),
                                ("gem", ((0.8, 0.0), (0.9, -0.7), (1.0, 0.0), (0.9, 0.7))))),
    "phantom_greatsword": dict(vs="w", blade=True, hit=(0.08, 0.0, 1.0, 0.0, 0.8), muzzle=(1.0, 0.0),
                               mat=dict(blade=(90, 70, 130), edge=(255, 255, 255), guard=(60, 40, 90),
                                        grip=(36, 26, 52), dark=(20, 14, 30), accent=(120, 90, 170), gem=(220, 190, 255)),
                               parts=(("grip", ((-0.2, -0.2), (0.0, -0.2), (0.0, 0.2), (-0.2, 0.2))),
                                      ("guard", ((0.0, -1.2), (0.04, -1.55), (0.08, -0.9), (0.08, 0.9), (0.04, 1.55),
                                                 (0.0, 1.2))),
                                      ("spirit", ((0.08, -0.8), (0.85, -0.7), (1.0, 0.0), (0.85, 0.7), (0.08, 0.8))),
                                      ("gem", ((0.1, -0.2), (0.9, -0.1), (0.97, 0.0), (0.9, 0.1), (0.1, 0.2))))),
    "neon_uzi": dict(vs="w", blade=False, hit=(0.0, 0.0, 1.0, 0.0, 0.5), muzzle=(1.0, -0.1),
                     mat=dict(blade=(34, 34, 42), edge=(200, 200, 220), guard=(60, 60, 72), grip=(26, 26, 32),
                              dark=(12, 12, 16), accent=(255, 60, 200), gem=(255, 90, 220)),
                     parts=(("blade", ((-0.15, -0.45), (0.7, -0.45), (0.7, 0.3), (-0.15, 0.3))),
                            ("grip", ((0.0, 0.3), (0.14, 0.3), (0.12, 1.3), (-0.02, 1.3))),
                            ("guard", ((0.7, -0.25), (1.0, -0.25), (1.0, 0.05), (0.7, 0.05))),
                            ("gem", ((-0.1, -0.26), (0.6, -0.26), (0.6, -0.12), (-0.1, -0.12))))),
    "halo_chakram": dict(vs="l", blade=True, hit=(-0.5, 0.0, 0.5, 0.0, 0.35), muzzle=(0.5, 0.0),
                         mat=dict(blade=(236, 222, 160), edge=(255, 255, 240), guard=(200, 170, 90), grip=(120, 96, 50),
                                  dark=(60, 46, 20), accent=(236, 222, 160), gem=(255, 250, 200)),
                         parts=(("blade", ((0.492, 0.087), (0.305, 0.126), (0.287, 0.41), (0.126, 0.305), (-0.087, 0.492),
                                           (-0.126, 0.305), (-0.41, 0.287), (-0.305, 0.126), (-0.492, -0.087),
                                           (-0.305, -0.126), (-0.287, -0.41), (-0.126, -0.305), (0.087, -0.492),
                                           (0.126, -0.305), (0.41, -0.287), (0.305, -0.126))),
                                ("guard", ((0.24, 0.0), (0.17, 0.17), (0.0, 0.24), (-0.17, 0.17), (-0.24, 0.0),
                                           (-0.17, -0.17), (0.0, -0.24), (0.17, -0.17))),
                                ("gem", ((0.111, 0.046), (0.046, 0.111), (-0.046, 0.111), (-0.111, 0.046),
                                         (-0.111, -0.046), (-0.046, -0.111), (0.046, -0.111), (0.111, -0.046))))),
    "wisp_rapier": dict(vs="w", blade=True, hit=(0.06, 0.0, 1.0, 0.0, 0.5), muzzle=(1.0, 0.0),
                        mat=dict(blade=(200, 236, 255), edge=(255, 255, 255), guard=(170, 190, 220), grip=(70, 80, 110),
                                 dark=(30, 34, 50), accent=(170, 190, 220), gem=(200, 240, 255)),
                        parts=(("grip", ((-0.2, -0.15), (0.0, -0.15), (0.0, 0.15), (-0.2, 0.15))),
                               ("guard", ((-0.02, -0.9), (0.06, -0.7), (0.06, 0.7), (-0.02, 0.9), (-0.06, 0.0))),
                               ("guard", ((-0.22, 0.2), (-0.2, 0.92), (0.0, 0.96), (0.0, 0.8), (-0.15, 0.76),
                                          (-0.16, 0.2))),
                               ("spirit", ((0.06, -0.3), (1.0, -0.02), (1.0, 0.02), (0.06, 0.3))),
                               ("edge", ((0.06, -0.07), (1.0, 0.0), (0.06, 0.07))))),
    "pulse_bow": dict(vs="l", blade=False, hit=(0.0, -0.5, 0.0, 0.5, 0.05), muzzle=(0.06, 0.0),
                      mat=dict(blade=(40, 60, 80), edge=(200, 240, 255), guard=(70, 110, 140), grip=(30, 40, 52),
                               dark=(16, 20, 26), accent=(90, 200, 255), gem=(140, 230, 255)),
                      parts=(("blade", ((0.03, -0.06), (0.14, -0.28), (0.05, -0.5), (-0.01, -0.5), (0.06, -0.28),
                                        (-0.04, -0.06))),
                             ("blade", ((0.03, 0.06), (0.14, 0.28), (0.05, 0.5), (-0.01, 0.5), (0.06, 0.28), (-0.04, 0.06))),
                             ("grip", ((-0.035, -0.08), (0.035, -0.08), (0.035, 0.08), (-0.035, 0.08))),
                             ("gem", ((0.0, -0.53), (0.035, -0.49), (0.0, -0.45), (-0.035, -0.49))),
                             ("gem", ((0.0, 0.53), (0.035, 0.49), (0.0, 0.45), (-0.035, 0.49))))),
    "rune_reaver": dict(vs="w", blade=True, hit=(0.06, 0.0, 1.0, -0.6, 0.7), muzzle=(1.0, 0.0),
                        mat=dict(blade=(70, 84, 96), edge=(220, 240, 250), guard=(40, 48, 56), grip=(30, 34, 40),
                                 dark=(16, 18, 22), accent=(70, 84, 96), gem=(110, 255, 200)),
                        parts=(("grip", ((-0.2, -0.2), (0.0, -0.2), (0.0, 0.2), (-0.2, 0.2))),
                               ("guard", ((0.0, -0.72), (0.06, -0.5), (0.06, 0.5), (0.0, 0.72))),
                               ("blade", ((0.06, -0.45), (0.7, -0.5), (1.0, -0.9), (0.85, 0.15), (0.4, 0.5), (0.06, 0.45))),
                               ("edge", ((0.4, 0.34), (0.85, 0.0), (1.0, -0.9), (0.85, 0.15), (0.4, 0.5))),
                               ("gem", ((0.15, -0.1), (0.2, -0.26), (0.25, -0.1), (0.2, 0.05))),
                               ("gem", ((0.35, -0.12), (0.4, -0.28), (0.45, -0.12), (0.4, 0.03))),
                               ("gem", ((0.55, -0.16), (0.6, -0.32), (0.65, -0.16), (0.6, -0.01))))),
    "nodachi": dict(vs="w", blade=True, hit=(0.03, 0.0, 1.0, -1.8, 1.0), muzzle=(1.0, -1.8),
                    mat=dict(blade=(186, 192, 204), edge=(250, 252, 255), guard=(190, 150, 60), grip=(30, 28, 34),
                             dark=(40, 40, 48), accent=(190, 150, 60), gem=(255, 220, 140)),
                    parts=(("grip", ((-0.2, -0.36), (0.0, -0.32), (0.0, 0.32), (-0.2, 0.36))),
                           ("guard", ((-0.01, -1.1), (0.025, -1.1), (0.035, 0.0), (0.025, 1.1), (-0.01, 1.1), (-0.02, 0.0))),
                           ("blade", ((0.03, -0.5), (0.3, -0.68), (0.6, -1.0), (0.85, -1.38), (1.0, -1.8), (0.86, -0.95),
                                      (0.6, 0.0), (0.3, 0.5), (0.03, 0.55))),
                           ("edge", ((0.03, 0.2), (0.3, 0.14), (0.6, -0.32), (0.85, -1.15), (1.0, -1.8), (0.86, -0.95),
                                     (0.6, 0.0), (0.3, 0.5), (0.03, 0.55))))),
    "saya": dict(vs="w", blade=False, hit=(0.0, 0.0, 1.0, 0.0, 0.5), muzzle=(1.0, 0.0),
                 mat=dict(blade=(26, 24, 30), edge=(80, 76, 90), guard=(190, 150, 60), grip=(26, 24, 30),
                          dark=(14, 12, 16), accent=(190, 150, 60), gem=(255, 220, 140)),
                 parts=(("blade", ((0.02, -0.7), (0.3, -0.85), (0.6, -1.15), (0.85, -1.58), (1.03, -2.05), (0.88, -1.05),
                                   (0.6, 0.1), (0.3, 0.7), (0.02, 0.7))),
                        ("accent", ((0.12, -0.8), (0.16, -0.82), (0.16, 0.72), (0.12, 0.72))),
                        ("accent", ((0.96, -2.0), (1.03, -2.05), (0.99, -1.4), (0.92, -1.3))))),
    "earth_cleaver": dict(vs="w", blade=True, hit=(0.08, 0.3, 0.98, 0.5, 0.8), muzzle=(1.0, 0.0),
                          mat=dict(blade=(110, 104, 98), edge=(224, 216, 204), guard=(70, 60, 50), grip=(60, 40, 28),
                                   dark=(40, 36, 32), accent=(150, 120, 80), gem=(255, 150, 60)),
                          parts=(("grip", ((-0.34, -0.2), (0.05, -0.2), (0.05, 0.2), (-0.34, 0.2))),
                                 ("guard", ((0.0, -0.5), (0.08, -0.5), (0.08, 0.5), (0.0, 0.5))),
                                 ("blade", ((0.08, -1.0), (0.95, -1.1), (1.0, -0.7), (0.97, 1.0), (0.6, 1.1), (0.55, 0.95),
                                            (0.45, 1.1), (0.08, 1.0))),
                                 ("dark", ((0.08, -1.0), (0.95, -1.1), (0.95, -0.82), (0.08, -0.74))),
                                 ("edge", ((0.08, 0.82), (0.45, 0.92), (0.55, 0.78), (0.6, 0.92), (0.97, 0.82),
                                           (0.97, 1.0), (0.6, 1.1), (0.55, 0.95), (0.45, 1.1), (0.08, 1.0))),
                                 ("accent", ((0.16, -0.5), (0.22, -0.5), (0.22, -0.38), (0.16, -0.38))),
                                 ("accent", ((0.16, 0.38), (0.22, 0.38), (0.22, 0.5), (0.16, 0.5))),
                                 ("gem", ((0.4, -0.3), (0.6, -0.34), (0.62, -0.2), (0.42, -0.16))))),
}

# ---------------------------------------------------------------- weapons
# models: one per weapon slot.  beats: the sequence lasts beats x swing_ticks.
# aim: pose angles (and the reach of a throw) are turned toward the target.
# trail: "swept" = a swept ribbon behind each swinging blade, "ghost" =
# afterimages, "" = none.  shot: what the fire list fires.
# tracks: per slot, keyed poses (t, x, y, r, ang, yaw, pitch, scale, ease):
#   t      0..1 through the sequence
#   x, y   where the hand is (HU units, +x forward, +y down)
#   r      0..1 of the way to the target (thrown / reaching weapons)
#   ang    which way the weapon points, degrees (0 forward, -90 up, 90 down;
#          keep counting past 360 for full spins)
#   yaw, pitch   its 3D turn (degrees)
#   scale  size
#   ease   into this pose: 0 linear, 1 ease out, 2 ease in, 3 in-out
# events: (t, kind, at, size, last): kind in EVT_LIFE; at = "tip0" / "tip1"
#   (that slot's blade tip), "mid" (middle of slot 0's blade) or "target";
#   last = a charge's length in sequence fractions.
# fire: (t, slot) for each shot.
WEAPONS = {
    "buster_sword": dict(models=("buster_sword",), beats=4, aim=False, trail="swept", shot="",
                         tracks=(((0.0, -0.2, -0.4, 0, 210, 0, 0, 1.0, 3), (0.4, -0.1, -1.0, 0, 250, 20, 0, 1.05, 3),
                                  (0.62, 0.5, 0.2, 0, 440, 0, 0, 1.08, 2), (0.75, 0.55, 0.3, 0, 445, 0, 0, 1.05, 1),
                                  (1.0, 0.4, 0.2, 0, 430, 0, 0, 1.0, 3)),),
                         events=((0.62, "slam", "tip0", 1.3, 0),), fire=()),
    "masamune": dict(models=("masamune",), beats=4, aim=False, trail="swept", shot="",
                     tracks=(((0.0, -0.3, 0.3, 0, 160, 0, 0, 1.0, 3), (0.3, -0.3, 0.2, 0, 150, 40, 0, 1.0, 3),
                              (0.4, 0.5, -0.4, 0, 340, 0, 0, 1.0, 1), (0.6, 0.4, -0.3, 0, 350, 0, 0, 1.0, 3),
                              (1.0, 0.2, 0.0, 0, 380, 20, 0, 1.0, 3)),),
                     events=((0.42, "cuts", "target", 8, 0),), fire=()),
    "oath_oblivion": dict(models=("oathkeeper", "oblivion"), beats=5, aim=False, trail="swept", shot="",
                          tracks=(((0.0, -0.2, -0.6, 0, -60, 0, 0, 1.0, 3), (0.45, 0.3, -1.4, 0, 300, 180, 0, 1.0, 3),
                                   (0.7, 0.6, -1.6, 0, 405, 360, 0, 1.0, 1), (1.0, 0.5, -1.4, 0, 395, 360, 0, 1.0, 3)),
                                  ((0.0, -0.2, 0.6, 0, 60, 0, 0, 1.0, 3), (0.45, 0.3, 1.4, 0, -300, -180, 0, 1.0, 3),
                                   (0.7, 0.6, 1.6, 0, -405, -360, 0, 1.0, 1), (1.0, 0.5, 1.4, 0, -395, -360, 0, 1.0, 3))),
                          events=((0.7, "xflash", "mid", 1.3, 0),), fire=()),
    "crescent_scythe": dict(models=("crescent_scythe",), beats=5, aim=False, trail="swept", shot="",
                            tracks=(((0.0, -0.4, -0.3, 0, -100, 0, 0, 1.0, 3), (0.15, -0.2, -0.4, 0, -100, 0, 40, 1.0, 3),
                                     (0.55, 0.2, -0.3, 0, 260, 0, 50, 1.0, 0), (0.75, 0.9, 0.0, 0, 390, 0, 0, 1.1, 1),
                                     (1.0, 0.7, 0.0, 0, 380, 0, 0, 1.0, 3)),),
                            events=((0.1, "petals", "tip0", 1, 0), (0.74, "burst", "tip0", 1.0, 0)), fire=()),
    "scissor_blade": dict(models=("scissor_a", "scissor_b"), beats=5, aim=True, trail="", shot="",
                          tracks=(((0.0, 0.2, -0.3, 0, -30, 0, 0, 1.0, 3), (0.3, 0.6, -0.2, 0.2, -75, 0, 0, 1.5, 3),
                                   (0.6, 0.6, -0.2, 1.0, -80, 0, 0, 1.6, 3), (0.72, 0.6, -0.2, 1.0, -5, 0, 0, 1.6, 2),
                                   (1.0, 0.3, -0.2, 0, -30, 0, 0, 1.0, 3)),
                                  ((0.0, 0.2, -0.3, 0, -30, 0, 0, 1.0, 3), (0.3, 0.6, -0.2, 0.2, 15, 0, 0, 1.5, 3),
                                   (0.6, 0.6, -0.2, 1.0, 20, 0, 0, 1.6, 3), (0.72, 0.6, -0.2, 1.0, -5, 0, 0, 1.6, 2),
                                   (1.0, 0.3, -0.2, 0, -30, 0, 0, 1.0, 3))),
                          events=((0.72, "snip", "mid", 1.4, 0),), fire=()),
    "gungnir": dict(models=("gungnir",), beats=6, aim=True, trail="", shot="",
                    tracks=(((0.0, -0.2, -0.6, 0, 0, 0, 0, 1.0, 3), (0.35, -0.9, -0.9, 0, -8, 90, 0, 1.0, 3),
                             (0.45, -0.6, -0.9, 0, -4, 180, 0, 1.05, 2), (0.72, 0.0, -0.5, 1.0, 0, 1440, 0, 1.05, 2),
                             (1.0, 0.0, -0.5, 1.0, 0, 1440, 0, 1.0, 3)),),
                    events=((0.05, "charge", "tip0", 1.0, 0.4), (0.72, "pillar", "tip0", 1.3, 0)), fire=()),
    "light_pistols": dict(models=("light_pistol", "light_pistol"), beats=6, aim=True, trail="", shot="light",
                          tracks=(((0.0, 0.3, -0.4, 0, 0, 0, 0, 1.0, 3), (0.9, 0.3, -0.4, 0, 0, 0, 0, 1.0, 3),
                                   (1.0, 0.3, -0.4, 0, 0, 360, 0, 1.0, 3)),
                                  ((0.0, 0.1, 0.5, 0, 0, 0, 0, 1.0, 3), (0.9, 0.1, 0.5, 0, 0, 0, 0, 1.0, 3),
                                   (1.0, 0.1, 0.5, 0, 0, -360, 0, 1.0, 3))),
                          events=(), fire=((0.08, 0), (0.16, 1), (0.24, 0), (0.32, 1), (0.4, 0), (0.48, 1), (0.56, 0),
                                           (0.64, 1), (0.72, 0), (0.8, 1))),
    "crimson_fang": dict(models=("crimson_fang",), beats=3, aim=False, trail="swept", shot="",
                         tracks=(((0.0, 0.0, 0.3, 0, 130, 0, 0, 1.0, 3), (0.25, -0.1, 0.4, 0, 140, 30, 0, 1.0, 3),
                                  (0.6, 0.4, -0.6, 0, -80, 0, 0, 1.05, 1), (1.0, 0.3, -0.5, 0, -70, 0, 0, 1.0, 3)),),
                         events=((0.6, "burst", "tip0", 1.0, 0),), fire=()),
    "arc_carbine": dict(models=("arc_carbine",), beats=5, aim=True, trail="", shot="spark",
                        tracks=(((0.0, 0.2, -0.1, 0, 0, 0, 0, 1.0, 3), (1.0, 0.2, -0.1, 0, 0, 0, 0, 1.0, 3)),),
                        events=(), fire=((0.15, 0), (0.21, 0), (0.27, 0), (0.55, 0), (0.61, 0), (0.67, 0))),
    "void_cannon": dict(models=("void_cannon",), beats=5, aim=True, trail="", shot="beam",
                        tracks=(((0.0, 0.3, 0.0, 0, 0, 0, 0, 1.0, 3), (0.5, 0.3, 0.0, 0, 0, 0, 0, 1.05, 3),
                                 (1.0, 0.3, 0.0, 0, 0, 0, 0, 1.0, 3)),),
                        events=((0.0, "charge", "tip0", 1.4, 0.55),), fire=((0.55, 0),)),
    "phase_kunai": dict(models=("kunai", "kunai"), beats=6, aim=True, trail="", shot="",
                        tracks=(((0.0, 0.2, -0.3, 0, -20, 0, 0, 1.0, 3), (0.15, -0.3, -0.5, 0, -30, 0, 0, 1.0, 3),
                                 (0.45, 0.0, -0.3, 1.0, -6, 720, 0, 1.0, 2), (0.48, 0.0, -0.3, 1.0, -6, 720, 0, 0.0, 0),
                                 (0.6, 0.0, -0.3, 1.35, 180, 720, 0, 0.0, 0), (0.63, 0.0, -0.3, 1.35, 180, 720, 0, 1.0, 0),
                                 (0.75, 0.0, -0.3, 1.0, 180, 720, 0, 1.0, 1), (1.0, 0.0, -0.3, 1.1, 180, 720, 0, 1.0, 3)),
                                ((0.0, 0.1, 0.3, 0, 20, 0, 0, 1.0, 3), (0.15, -0.3, 0.4, 0, 30, 0, 0, 1.0, 3),
                                 (0.45, 0.0, 0.3, 1.0, 6, -720, 0, 1.0, 2), (0.48, 0.0, 0.3, 1.0, 6, -720, 0, 0.0, 0),
                                 (0.6, 0.0, 0.3, 1.35, 180, -720, 0, 0.0, 0), (0.63, 0.0, 0.3, 1.35, 180, -720, 0, 1.0, 0),
                                 (0.75, 0.0, 0.3, 1.0, 180, -720, 0, 1.0, 1), (1.0, 0.0, 0.3, 1.1, 180, -720, 0, 1.0, 3))),
                        events=((0.46, "blink", "tip0", 1.0, 0), (0.46, "blink", "tip1", 1.0, 0),
                                (0.62, "blink", "tip0", 1.0, 0), (0.62, "blink", "tip1", 1.0, 0),
                                (0.75, "xflash", "target", 1.0, 0)), fire=()),
    "astral_staff": dict(models=("astral_staff",), beats=6, aim=False, trail="swept", shot="",
                         tracks=(((0.0, 0.3, 0.2, 0, -95, 0, 0, 1.0, 3), (0.1, 0.2, -0.2, 0, -95, 0, 0, 1.0, 3),
                                  (0.5, 0.2, -0.4, 0, 625, 360, 0, 1.0, 0), (0.6, 0.6, 0.3, 0, 640, 360, 0, 1.05, 1),
                                  (1.0, 0.5, 0.2, 0, 635, 360, 0, 1.0, 3)),),
                         events=((0.6, "runes", "target", 1.0, 0),), fire=()),
    "phantom_greatsword": dict(models=("phantom_greatsword",), beats=4, aim=False, trail="swept", shot="",
                               tracks=(((0.0, 0.0, -0.5, 0, -90, 0, 0, 0.8, 3), (0.35, -0.2, -1.6, 0, -100, 0, 0, 1.25, 3),
                                        (0.6, 0.6, 0.1, 0, 80, 0, 0, 1.3, 2), (1.0, 0.5, 0.1, 0, 85, 0, 0, 1.2, 3)),),
                               events=((0.6, "slam", "tip0", 1.6, 0),), fire=()),
    "neon_uzis": dict(models=("neon_uzi", "neon_uzi"), beats=8, aim=True, trail="", shot="neon",
                      tracks=(((0.0, 0.3, -0.4, 0, 0, 0, 0, 1.0, 3), (0.85, 0.3, -0.4, 0, 0, 0, 0, 1.0, 3),
                               (1.0, 0.3, -0.4, 0, 0, 360, 0, 1.0, 3)),
                              ((0.0, 0.1, 0.45, 0, 0, 0, 0, 1.0, 3), (0.85, 0.1, 0.45, 0, 0, 0, 0, 1.0, 3),
                               (1.0, 0.1, 0.45, 0, 0, -360, 0, 1.0, 3))),
                      events=(), fire=((0.05, 0), (0.1, 1), (0.15, 0), (0.2, 1), (0.25, 0), (0.3, 1), (0.35, 0),
                                       (0.4, 1), (0.45, 0), (0.5, 1), (0.55, 0), (0.6, 1), (0.65, 0), (0.7, 1),
                                       (0.75, 0), (0.8, 1))),
    "halo_chakram": dict(models=("halo_chakram",), beats=6, aim=True, trail="ghost", shot="",
                         tracks=(((0.0, 0.4, -0.3, 0, 0, 0, 60, 1.0, 3), (0.15, 0.0, -0.5, 0, 0, 0, 60, 1.0, 3),
                                  (0.32, 0.0, -3.0, 0.5, 540, 0, 60, 1.0, 0), (0.5, 0.0, 0.0, 1.0, 900, 0, 60, 1.0, 1),
                                  (0.68, 0.0, 3.0, 0.5, 1350, 0, 60, 1.0, 0),
                                  (0.85, 0.0, 0.0, 0.0, 1800, 0, 60, 1.0, 2), (1.0, 0.4, -0.3, 0, 1840, 0, 60, 1.0, 1)),),
                         events=((0.5, "burst", "mid", 1.2, 0),), fire=()),
    "wisp_rapier": dict(models=("wisp_rapier",), beats=6, aim=False, trail="ghost", shot="",
                        tracks=(((0.0, 0.2, 0.0, 0, 0, 0, 0, 1.0, 3), (0.1, 1.6, -0.4, 0, -10, 0, 0, 1.0, 1),
                                 (0.18, 0.4, -0.2, 0, -6, 0, 0, 1.0, 3), (0.28, 1.7, 0.3, 0, 8, 0, 0, 1.0, 1),
                                 (0.36, 0.4, 0.1, 0, 4, 0, 0, 1.0, 3), (0.46, 1.8, -0.6, 0, -14, 0, 0, 1.0, 1),
                                 (0.54, 0.4, -0.2, 0, -5, 0, 0, 1.0, 3), (0.64, 1.7, 0.5, 0, 12, 0, 0, 1.0, 1),
                                 (0.72, 0.2, 0.0, 0, 0, 0, 0, 1.0, 3), (0.85, 2.6, 0.0, 0, 0, 0, 0, 1.15, 1),
                                 (1.0, 1.2, 0.0, 0, 0, 0, 0, 1.0, 3)),),
                        events=((0.85, "burst", "tip0", 1.1, 0),), fire=()),
    "pulse_bow": dict(models=("pulse_bow",), beats=5, aim=True, trail="", shot="arrow",
                      tracks=(((0.0, 0.5, -0.2, 0, 0, 0, 0, 1.0, 3), (1.0, 0.5, -0.2, 0, 0, 0, 0, 1.0, 3)),),
                      events=(), fire=((0.6, 0),)),
    "rune_reaver": dict(models=("rune_reaver",), beats=4, aim=False, trail="swept", shot="",
                        tracks=(((0.0, 0.3, -0.2, 0, 120, 0, 0, 1.0, 3), (0.2, 0.1, -0.1, 0, 130, 0, 0, 1.0, 3),
                                 (0.65, 0.5, -0.4, 0, -410, 180, 0, 1.05, 1), (1.0, 0.4, -0.3, 0, -400, 180, 0, 1.0, 3)),),
                        events=((0.66, "glyph", "tip0", 1.0, 0),), fire=()),
    "nodachi": dict(models=("nodachi", "saya"), beats=5, aim=False, trail="swept", shot="",
                    tracks=(((0.0, -0.2, 0.3, 0, 195, 0, 0, 1.0, 3), (0.45, -0.2, 0.3, 0, 195, 0, 0, 1.0, 3),
                             (0.52, 0.6, 0.0, 0, 360, 0, 0, 1.0, 1), (1.0, 0.5, 0.0, 0, 365, 0, 0, 1.0, 3)),
                            ((0.0, -0.2, 0.35, 0, 195, 0, 0, 1.0, 3), (1.0, -0.25, 0.4, 0, 200, 0, 0, 1.0, 3))),
                    events=((0.53, "cuts", "target", 1, 0),), fire=()),
    "earth_cleaver": dict(models=("earth_cleaver",), beats=4, aim=False, trail="swept", shot="",
                          tracks=(((0.0, 0.0, -0.3, 0, -120, 0, 0, 1.0, 3), (0.4, -0.3, -1.2, 0, -110, 0, 0, 1.05, 3),
                                   (0.62, 0.6, 0.3, 0, 85, 0, 0, 1.1, 2), (1.0, 0.55, 0.3, 0, 88, 0, 0, 1.05, 3)),),
                          events=((0.62, "slam", "tip0", 1.7, 0),), fire=()),
    "void_sniper": dict(models=("void_sniper",), beats=6, aim=True, trail="", shot="rail",
                        tracks=(((0.0, 0.2, -0.2, 0, 0, 0, 0, 1.0, 3), (0.58, 0.2, -0.2, 0, 0, 0, 0, 1.0, 3),
                                 (0.76, 0.0, -0.3, 0, -16, 0, 0, 1.0, 1), (1.0, 0.2, -0.2, 0, -4, 0, 0, 1.0, 3)),),
                        events=((0.05, "charge", "tip0", 1.0, 0.53), (0.58, "implode", "target", 1.0, 0)),
                        fire=((0.58, 0),)),
}


# ---------------------------------------------------------------- timeline
def _w(P):
    return WEAPONS[S._style(P)]


def _sig(P):
    return P.get("w_mode") != "hold"


def _move(P):
    """Ticks the signature sequence lasts."""
    return _w(P)["beats"] * max(1, F.trunc(float(P.get("swing_ticks") or 6)))


def _hold(P):
    return max(0, F.trunc(float(P.get("hold_ticks") or 0)))


def _tick_of(P, t):
    return SUMMON + F.jround(t * _move(P))


def _shot_flight(P):
    w = _w(P)
    if not w["shot"]:
        return 0
    if w["shot"] in LINE_T:
        return LINE_T[w["shot"]]
    return int(math.ceil(max(20.0, float(P.get("radius") or 0)) / SHOTS[w["shot"]]["speed"]))


def active_ticks(P):
    """The weapon's life: the hit window (and how long it stays)."""
    if not _sig(P):
        return SUMMON + max(1, _hold(P))
    w = _w(P)
    n = SUMMON + _move(P) + _hold(P)
    for f in w["fire"]:
        n = max(n, _tick_of(P, f[0]) + _shot_flight(P) + 1)
    for e in w["events"]:
        if EVT_R[e[1]] > 0:
            n = max(n, _tick_of(P, e[0]) + EVT_HIT + (24 if e[1] == "runes" else 0) + 1)
    return n


def total_ticks(P):
    return active_ticks(P) + DISMISS + TAIL


def _phase(P, life, tick):
    """(u through the sequence, materialise 0..1, fade 1..0) at tick."""
    ap = min(1.0, tick / float(SUMMON))
    fd = 1.0 if tick < life else max(0.0, 1.0 - (tick - life) / float(DISMISS))
    if not _sig(P) or tick < SUMMON:
        return 0.0, ap, fd
    return min(1.0, (tick - SUMMON) / float(_move(P))), ap, fd


def _ease(e, k):
    if e == 1:
        return S.ease_out3(k)
    if e == 2:
        return S.ease_in3(k)
    if e == 3:
        return S.ease_inout3(k)
    return S._cl(k)


def _track(rows, u):
    """The pose (x, y, r, ang, yaw, pitch, scale) at u."""
    if u <= rows[0][0]:
        return list(rows[0][1:8])
    for i in range(len(rows) - 1):
        a, b = rows[i], rows[i + 1]
        if u < b[0]:
            k = (u - a[0]) / (b[0] - a[0]) if b[0] > a[0] else 1.0
            e = _ease(b[8], k)
            return [a[j] + (b[j] - a[j]) * e for j in range(1, 8)]
    return list(rows[-1][1:8])


def _at(lst, k):
    return lst[max(0, min(F.trunc(k), len(lst) - 1))]


# ---------------------------------------------------------------- 3D
class XF:
    """One weapon slot at one moment: model (u, v) -> world, through the
    yaw / pitch / perspective camera, the pose, the size and the flips."""
    __slots__ = ("fr", "px", "py", "ca", "sa", "cy", "sy", "cp", "sp", "K", "L", "W", "Fc", "dz", "fx_", "fy_",
                 "nz", "tk", "Y", "Pt", "m", "zp")

    def pt(self, u, v, t=0.0):
        x3 = u * self.L
        y3 = v * self.W * self.cy - t * self.sy * self.tk
        z3 = v * self.W * self.sy + t * self.cy * self.tk
        x4 = x3 * self.cp - z3 * self.sp
        z4 = x3 * self.sp + z3 * self.cp
        s = self.Fc / max(self.Fc * 0.25, self.Fc * (1 + self.dz) + z4)
        wx, wy = x4 * s * self.K, y3 * s * self.K
        lx = self.px + wx * self.ca - wy * self.sa
        ly = self.py + wx * self.sa + wy * self.ca
        # the flips mirror on screen round the anchor (left / right, up / down)
        g = self.fr.d(lx, ly)
        return self.fr.ox + g[0] * self.fx_, self.fr.oy + g[1] * self.fy_


def _aim_ang(inst, tick):
    """Local angle (degrees) from the anchor to the target at tick, held
    within +-75 degrees of forward."""
    ox, oy = _at(inst.tq_path, tick)
    tx, ty = _at(inst.tq_tp, tick)
    dx, dy = tx - ox, ty - oy
    fr = S.Frame(0.0, 0.0, inst.tq_f, inst.tq_m)
    lx = dx * fr.fx + dy * fr.fy
    ly = dx * fr.vx + dy * fr.vy
    if abs(lx) + abs(ly) < 1e-6:
        return 0.0, 0.0
    return max(-75.0, min(75.0, math.atan2(ly, lx) / S.D)), math.hypot(lx, ly)


def _recoil(w, P, slot, tick):
    k = 0.0
    for f in w["fire"]:
        if f[1] != slot:
            continue
        a = tick - _tick_of(P, f[0])
        if 0 <= a < 12:
            k += math.exp(-a / 2.5)
    return min(1.5, k)


def _wrap(d):
    """d degrees folded into [-180, 180)."""
    return d - 360.0 * math.floor((d + 180.0) / 360.0)


def _grip_names(fx):
    """(hand, weapon tip) anchors Hold mode lines the weapon up along."""
    return ("haL", "wtip2") if fx.get("anchor") == "haL" else ("haR", "wtip")


def arm_ang(inst, host):
    """Hold mode: the local angle (degrees) of the hand -> weapon tip line on
    the frame on show (the rig's own blade), or None (signature mode, or no
    such tip on this rig).  Recorded every tick (swordfx on_spawn / on_tick)."""
    P = inst.fx["params"]
    if host is None or _sig(P) or S._style(P) not in WEAPONS:
        return None
    g, t = _grip_names(inst.fx)
    p0, p1, fg = host.anchor(g), host.anchor(t), host.anchor("figure")
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    if (p1[0] == fg[0] and p1[1] == fg[1]) or math.hypot(dx, dy) < 1.0:
        return None
    fr = S.Frame(0.0, 0.0, inst.tq_f, inst.tq_m)
    return math.atan2(dx * fr.vx + dy * fr.vy, dx * fr.fx + dy * fr.fy) / S.D


def _arm_at(inst, tick):
    A = getattr(inst, "w_arm", None)
    if not A:
        return None
    k = max(0, min(F.trunc(tick), len(A) - 1))
    a = A[k]
    if a is None:
        return None
    b = A[k + 1] if k + 1 < len(A) else None
    f = tick - F.trunc(tick)
    if b is None or f <= 0:
        return a
    return a + _wrap(b - a) * f


def _pose(inst, P, w, slot, tick):
    """The slot's pose at tick before weight and swing plane:
    (x, y, r, ang, yaw, pitch, scale, aim angle, target distance)."""
    u, _ap, _fd = _phase(P, inst.life, tick)
    rows = w["tracks"][slot]
    x, y, r, ang, yaw, pitch, sc = _track(rows, u) if _sig(P) else list(rows[0][1:8])
    aa, dist = (_aim_ang(inst, tick) if w["aim"] else (0.0, 0.0))
    arm = None if _sig(P) else _arm_at(inst, tick)
    if arm is None:
        if not _sig(P):
            y += math.sin(tick * 0.12) * 0.15
        ang += aa
    else:
        x = y = 0.0      # the grip in the hand, along the rig's own blade line
        ang = arm
    if w["shot"]:
        kick = _recoil(w, P, slot, tick)
        ang -= 9.0 * kick
        x -= 0.25 * kick
    return x, y, r, ang, yaw, pitch, sc, aa, dist


def _weight(P):
    return max(0.0, min(1.0, float(P.get("w_weight") or 0)))


def _flip_sign(v):
    return -1.0 if (v is not None and float(v) < 0) else 1.0


def _drag(inst, ps, slot, tick):
    """Degrees the weapon trails its pose by at tick (w_weight; 0 = rigid).
    A damped spring pulls the angle toward the pose while the hand's
    acceleration swings it like a rod held at one end (angular acceleration
    -1.5 / L x (blade x hand acceleration)).  It is integrated tick by tick
    from the start of the effect over the recorded anchor path, so it is the
    same however often it is asked (scrubbing, trails, hits)."""
    P = inst.fx["params"]
    wt = _weight(P)
    if wt <= 0:
        return 0.0
    w = _w(P)
    G = float(P.get("w_scale") if P.get("w_scale") is not None else 1)
    s0 = 1.0 / (1.0 + max(-0.75, float(P.get("w_depth") or 0)))
    Lp = max(1.0, float(P.get("length") or 40)) * ps * max(0.05, abs(G))
    key = (ps, wt)
    cache = getattr(inst, "w_dg", None)
    if cache is None or cache.get("key") != key:
        cache = inst.w_dg = {"key": key}
    c = cache.get(slot)
    known = len(inst.tq_path) - 1          # ticks whose anchor is recorded
    fr = S.Frame(0.0, 0.0, inst.tq_f, inst.tq_m)
    sx, sy = _flip_sign(P.get("w_flip_x")), _flip_sign(P.get("w_flip_y"))
    w0 = 2.0 * math.pi * (DRAG_HZ[0] + (DRAG_HZ[1] - DRAG_HZ[0]) * wt) * F.TICK_MS / 1000.0
    ze = DRAG_ZETA[0] + (DRAG_ZETA[1] - DRAG_ZETA[0]) * wt
    lim = DRAG_MAX * S.D
    amax = GRIP_ACC_MAX * Lp

    def grip(k):
        # the hand in the weapon's own (unflipped) frame, px
        q = _pose(inst, P, w, slot, k)
        px, py = inst.tq_path[k]
        px, py = px * sx, py * sy
        return (px * fr.fx + py * fr.fy + q[0] * HU * ps * s0 * G,
                px * fr.vx + py * fr.vy + q[1] * HU * ps * s0 * G), q[3]

    if c is None:
        g0, a0 = grip(0)
        T0 = a0 * S.D
        c = cache[slot] = {"dev": [0.0], "th": T0, "om": 0.0, "T": T0, "raw": a0, "s": g0, "v": (0.0, 0.0)}
    dev = c["dev"]
    want = min(known, F.trunc(tick) + 1)
    h = 1.0 / DRAG_SUB
    while len(dev) <= want:
        k = len(dev)
        g, a = grip(k)
        T = c["T"] + _wrap(a - c["raw"]) * S.D
        s = (c["s"][0] + (g[0] - c["s"][0]) * GRIP_SMOOTH, c["s"][1] + (g[1] - c["s"][1]) * GRIP_SMOOTH)
        v = (s[0] - c["s"][0], s[1] - c["s"][1])
        ax, ay = v[0] - c["v"][0], v[1] - c["v"][1]
        am = math.hypot(ax, ay)
        if am > amax:
            ax, ay = ax * amax / am, ay * amax / am
        th, om, Tp = c["th"], c["om"], c["T"]
        for i in range(1, DRAG_SUB + 1):
            Tt = Tp + (T - Tp) * i * h
            tq = -1.5 / Lp * (math.cos(th) * ay - math.sin(th) * ax)
            om += (w0 * w0 * (Tt - th) - 2.0 * ze * w0 * om + tq) * h
            th += om * h
        if th - T > lim:
            th, om = T + lim, om * 0.5
        elif th - T < -lim:
            th, om = T - lim, om * 0.5
        c.update(th=th, om=om, T=T, raw=a, s=s, v=v)
        dev.append((th - T) / S.D)
    k = max(0, min(F.trunc(tick), len(dev) - 1))
    f = tick - F.trunc(tick)
    if f > 0 and k + 1 < len(dev):
        return dev[k] + (dev[k + 1] - dev[k]) * f
    return dev[k]


def _plane(P, ang):
    """The swing plane (w_plane / w_plane_roll / w_side): the pose's angle
    swept round a plane tilted out of the screen.  -> (screen angle degrees,
    tilt out of the screen degrees (- = toward the camera), how far round out
    of the screen 0..1)."""
    b = max(0.0, min(90.0, float(P.get("w_plane") or 0)))
    if b <= 0:
        return ang, 0.0, 0.0
    g = float(P.get("w_plane_roll") or 0)
    a = (ang - g) * S.D
    z = min(1.0, abs(math.sin(a)) * math.sin(b * S.D))
    scr = math.atan2(math.sin(a) * math.cos(b * S.D), math.cos(a)) / S.D + g
    side = -1.0 if P.get("w_side") == "behind" else 1.0
    return scr, -side * math.asin(z) / S.D, z


def xf(inst, ps, slot, tick):
    """The XF of weapon slot `slot` at tick (fractional ticks allowed)."""
    P = inst.fx["params"]
    w = _w(P)
    md = MODELS[w["models"][slot]]
    _u, ap, _fd = _phase(P, inst.life, tick)
    x, y, r, ang, yaw, pitch, sc, aa, dist = _pose(inst, P, w, slot, tick)
    ang, tilt, zp = _plane(P, ang + _drag(inst, ps, slot, tick))
    L = max(1.0, float(P.get("length") or 40)) * ps
    W = (L if md["vs"] == "l" else max(0.5, float(P.get("thickness") or 4)) * ps)
    G = float(P.get("w_scale") if P.get("w_scale") is not None else 1)
    dz = max(-0.75, float(P.get("w_depth") or 0))
    o = XF()
    o.fr = S.Frame(_at(inst.tq_path, tick)[0], _at(inst.tq_path, tick)[1], inst.tq_f, inst.tq_m)
    o.Y = (yaw + float(P.get("w_yaw") or 0) + float(P.get("w_spin") or 0) * tick) * S.D
    o.Pt = (pitch + float(P.get("w_pitch") or 0) + tilt) * S.D
    o.zp = zp
    o.cy, o.sy = math.cos(o.Y), math.sin(o.Y)
    o.cp, o.sp = math.cos(o.Pt), math.sin(o.Pt)
    o.ca, o.sa = math.cos(ang * S.D), math.sin(ang * S.D)
    o.L, o.W = L, W
    o.tk = THICK_K * (W if md["vs"] == "w" else L * 0.06)
    o.Fc = FOCAL * L
    o.dz = dz
    s0 = 1.0 / (1.0 + dz)
    K = sc * G * (0.75 + 0.25 * S.ease_out3(ap))
    o.K = K
    hx, hy = x * HU * ps, y * HU * ps
    if r > 0 and w["aim"]:
        # reach toward the target: the blade tip lands on it at r = 1
        reach = max(0.0, min(dist, float(P.get("radius") or 0) * ps) - md["hit"][2] * L * K)
        hx += math.cos(aa * S.D) * reach * r
        hy += math.sin(aa * S.D) * reach * r
    o.px, o.py = hx * s0 * G, hy * s0 * G
    o.fx_ = float(P.get("w_flip_x") if P.get("w_flip_x") is not None else 1)
    o.fy_ = float(P.get("w_flip_y") if P.get("w_flip_y") is not None else 1)
    o.nz = o.cy * o.cp
    o.m = md
    return o


def draw_layer(inst, ps, layer):
    """The layer the weapon draws on this tick: Swing side behind moves a
    front-layer weapon behind the fighter while it is round the far side."""
    P = inst.fx["params"]
    if layer != "front" or P.get("w_side") != "behind" or not float(P.get("w_plane") or 0) > 0:
        return layer
    if S._style(P) not in WEAPONS:
        return layer
    return "back" if xf(inst, ps, 0, inst.age).zp > BEHIND_Z else layer


def _seg(o):
    """Slot's cutting line: (x0, y0, x1, y1, half width) in world px."""
    h = o.m["hit"]
    a = o.pt(h[0], h[1])
    b = o.pt(h[2], h[3])
    return a[0], a[1], b[0], b[1], h[4] * o.W * abs(o.K) * max(0.35, abs(o.cy))


def _slots(P):
    return len(_w(P)["models"])


def _ev_pos(inst, ps, e, tick):
    at = e[2]
    if at == "target":
        return _at(inst.tq_tp, tick)
    if at == "mid":
        x0, y0, x1, y1, _hw = _seg(xf(inst, ps, 0, tick))
        return (x0 + x1) * 0.5, (y0 + y1) * 0.5
    x0, y0, x1, y1, _hw = _seg(xf(inst, ps, 1 if at == "tip1" else 0, tick))
    return x1, y1


# ---------------------------------------------------------------- shots
class Shot:
    """One shot: everything about it is rolled from the seed."""
    __slots__ = ("i", "b", "kind", "ox", "oy", "dx", "dy", "sp", "rng", "flight", "size")

    def __init__(self, inst, ps, i, f):
        P = inst.fx["params"]
        w = _w(P)
        r = S.rng_for(inst.seed, i, 47)
        self.i = i
        self.b = _tick_of(P, f[0])
        self.kind = w["shot"]
        o = xf(inst, ps, f[1], self.b)
        mu, mv = o.m["muzzle"]
        self.ox, self.oy = o.pt(mu, mv)
        ax, ay = o.pt(mu - 0.2, mv)
        dx, dy = self.ox - ax, self.oy - ay
        if (inst.fx.get("motion") or {}).get("aim") == "target":
            tx, ty = _at(inst.tq_tp, self.b)
            if math.hypot(tx - self.ox, ty - self.oy) > 4:
                dx, dy = tx - self.ox, ty - self.oy
        d = math.hypot(dx, dy) or 1.0
        sp = F.rot([dx / d, dy / d], r.uniform(-0.5, 0.5) * float(P.get("span") or 0))
        self.dx, self.dy = sp[0], sp[1]
        g = SHOTS[self.kind]
        self.size = g["size"] * r.uniform(0.9, 1.1)
        R = max(20.0, float(P.get("radius") or 0))
        self.rng = R * ps
        self.sp = g["speed"] * ps
        self.flight = LINE_T[self.kind] if self.kind in LINE_T else int(math.ceil(R / g["speed"]))

    def pos(self, k):
        d = self.sp * k
        return self.ox + self.dx * d, self.oy + self.dy * d

    def end(self, inst):
        h = inst.tq_ki.get(self.i)
        if h is not None:
            return h[0], True
        return self.b + self.flight, False


def _shots(inst, ps):
    P = inst.fx["params"]
    if not _sig(P):
        return []
    out = []
    for i, f in enumerate(_w(P)["fire"]):
        if _tick_of(P, f[0]) > inst.age:
            break
        out.append(Shot(inst, ps, i, f))
    return out


def _live(inst, ps):
    out = []
    for s in _shots(inst, ps):
        if s.kind in LINE_T:
            continue
        e, _st = s.end(inst)
        if inst.age < e:
            out.append((s, s.pos(inst.age - s.b)))
    return out


def fires(style):
    return style in WEAPONS and WEAPONS[style]["shot"] != "" and WEAPONS[style]["shot"] not in LINE_T


def live_points(inst, ps):
    """[(i, x, y, vx, vy)] for the shots in flight this tick (weaponfx.js livePoints)."""
    return [(s.i, x, y, s.dx * s.sp, s.dy * s.sp) for (s, (x, y)) in _live(inst, ps)]


# ---------------------------------------------------------------- public
def _blade_live(inst, P):
    if not _sig(P):
        return inst.age < inst.life
    return SUMMON <= inst.age <= SUMMON + _move(P)


def hit(inst, tx, ty, hr, ps):
    if inst.age >= inst.life:
        return False
    P = inst.fx["params"]
    w = _w(P)
    t = inst.age
    if _blade_live(inst, P):
        for sl in range(_slots(P)):
            o = xf(inst, ps, sl, t)
            if not o.m["blade"] or abs(o.K) < 0.05:
                continue
            x0, y0, x1, y1, hw = _seg(o)
            if F.seg_dist(tx, ty, x0, y0, x1, y1) <= hr + hw:
                return True
    if not _sig(P):
        return False
    for e in w["events"]:
        R = EVT_R[e[1]]
        if R <= 0:
            continue
        te = _tick_of(P, e[0])
        if e[1] == "runes":
            for b in (6, 12, 18):
                if te + b <= t < te + b + EVT_HIT:
                    x, y = _ev_pos(inst, ps, e, te)
                    if math.hypot(tx - x, ty - y) <= hr + R * ps * e[3]:
                        return True
            continue
        if te <= t < te + EVT_HIT:
            x, y = _ev_pos(inst, ps, e, te)
            if math.hypot(tx - x, ty - y) <= hr + R * ps * e[3]:
                return True
    for (s, (x, y)) in _live(inst, ps):
        if math.hypot(x - tx, y - ty) <= hr + 4.0 * ps * s.size:
            return True
    for s in _shots(inst, ps):
        if s.kind in LINE_T and s.b <= t < s.end(inst)[0]:
            x1, y1 = s.pos(0)
            x2, y2 = s.ox + s.dx * s.rng, s.oy + s.dy * s.rng
            if F.seg_dist(tx, ty, x1, y1, x2, y2) <= hr + LINE_HW[s.kind] * ps * s.size:
                return True
    return False


def body(inst, ps):
    """A swinging blade clashes along its cutting line; guns never do."""
    P = inst.fx["params"]
    if inst.age >= inst.life or not _blade_live(inst, P):
        return None
    o = xf(inst, ps, 0, inst.age)
    if not o.m["blade"] or abs(o.K) < 0.05:
        return None
    x0, y0, x1, y1, hw = _seg(o)
    return [(x0, y0), (x1, y1)], hw


def on_hit(inst, x, y, ps):
    """A shot that hit stops there and bursts."""
    best, bd = None, None
    for (s, (sx, sy)) in _live(inst, ps):
        d = math.hypot(sx - x, sy - y)
        if bd is None or d < bd:
            best, bd = (s, sx, sy), d
    if best is not None and bd <= 40.0 * ps:
        s, sx, sy = best
        inst.tq_ki[s.i] = (inst.age, sx, sy)


# ================================================================ drawing
def _mat(o, role, c):
    if role == "spirit":
        return c
    m = o.m["mat"]
    return m[role] if role in m else m["blade"]


def _draw_weapon(pen, o, c, a, ps, tick):
    """The weapon itself: far face (its side wall), near face lit by how
    square-on it is, glowing parts, and a glint running along the edge."""
    if a <= 0.01 or abs(o.K) < 0.02:
        return
    back = o.nz > 0
    near = -1.0 if back else 1.0
    lit = 0.5 + 0.5 * abs(o.nz)
    parts = o.m["parts"]
    pen.add(False)
    for (role, pts) in parts:
        if role in GLOWS:
            continue
        far = [o.pt(u, v, -near) for (u, v) in pts]
        nr = [o.pt(u, v, near) for (u, v) in pts]
        side = S.mix(_mat(o, role, c), S.BLACK, 0.55)
        pen.poly(far, S.mix(_mat(o, role, c), S.BLACK, 0.62), 255 * a)
        # the side walls between the two faces: the weapon's thickness
        n = len(pts)
        for i in range(n):
            j = (i + 1) % n
            pen.poly([far[i], far[j], nr[j], nr[i]], side, 255 * a)
    dk = (1 - lit) * 0.75 + (0.15 if back else 0.0)
    for (role, pts) in parts:
        if role in GLOWS:
            continue
        pen.poly([o.pt(u, v, near) for (u, v) in pts], S.mix(_mat(o, role, c), S.BLACK, dk), 255 * a)
    pen.add(True)
    for (role, pts) in parts:
        if role not in GLOWS:
            continue
        q = [o.pt(u, v, near) for (u, v) in pts]
        col = c if role == "spirit" else _mat(o, "gem", c)
        pen.poly(q, col, (150 if role == "spirit" else 235) * a)
        cx = sum(p[0] for p in q) / len(q)
        cy = sum(p[1] for p in q) / len(q)
        rr = max(math.hypot(p[0] - cx, p[1] - cy) for p in q)
        pen.glow(cx, cy, rr * 0.9 + 3 * ps, col, 80 * a)
    # glint along the cutting line, strongest square-on
    x0, y0, x1, y1, _hw = _seg(o)
    g = 0.5 + 0.45 * math.sin((o.Y + o.Pt) * 1.3 + tick * 0.07)
    st = 190 * a * o.nz * o.nz
    gx, gy = x0 + (x1 - x0) * g, y0 + (y1 - y0) * g
    if st > 4:
        L = math.hypot(x1 - x0, y1 - y0)
        k = min(0.12, 6 * ps / max(1.0, L))
        pen.diamond(x0 + (x1 - x0) * (g - k), y0 + (y1 - y0) * (g - k), x0 + (x1 - x0) * (g + k),
                    y0 + (y1 - y0) * (g + k), 1.3 * ps, S.HOT, st)
        pen.glow(gx, gy, 6 * ps * abs(o.K), S.HOT, st * 0.7)


def _draw_summon(pen, inst, o, c, ps, t):
    """Light rushes in and a scan line runs up the blade as it appears."""
    if t >= SUMMON:
        return
    q = t / float(SUMMON)
    x0, y0, x1, y1, _hw = _seg(o)
    mx, my = (x0 + x1) * 0.5, (y0 + y1) * 0.5
    for j in range(8):
        r = S.rng_for(inst.seed, j, 53)
        an = r.uniform(0, math.pi * 2)
        d0 = r.uniform(30, 50) * ps * (1 - S.ease_out3(q))
        d1 = d0 + r.uniform(8, 18) * ps * (1 - q)
        ca, sa = math.cos(an), math.sin(an)
        pen.line(mx + ca * d1, my + sa * d1, mx + ca * d0, my + sa * d0, S.mix(c, S.HOT, 0.5), 220 * (1 - q), 1.3 * ps)
    sx, sy = x0 + (x1 - x0) * q, y0 + (y1 - y0) * q
    pen.glow(sx, sy, 9 * ps, S.HOT, 230 * (1 - q * 0.5))
    pen.glow(mx, my, 18 * ps * (1 - q), c, 160 * (1 - q))


def _draw_dismiss(pen, inst, o, c, ps, t):
    """Motes drift off the blade as it dissolves."""
    k = t - inst.life
    if k < 0 or k >= DISMISS + 10:
        return
    x0, y0, x1, y1, _hw = _seg(o)
    n = max(0, F.jround(10 * float(inst.fx["params"].get("density") or 1)))
    for j in range(n):
        r = S.rng_for(inst.seed, j, 57)
        u = r()
        life = r.uniform(10, 20)
        if k >= life:
            continue
        q = k / life
        px, py = x0 + (x1 - x0) * u, y0 + (y1 - y0) * u
        px += r.uniform(-6, 6) * ps * q
        py -= r.uniform(4, 18) * ps * q
        pen.glow(px, py, 3.2 * ps * (1 - q) + 0.5, S.mix(c, S.HOT, 0.4), 220 * (1 - q))


def _draw_trail(pen, inst, ps, c, sl, t):
    """A swept ribbon between where the tip and the middle of the blade
    were over the last TRAIL_N ticks."""
    P = inst.fx["params"]
    t0 = float(SUMMON)
    t1 = float(SUMMON + _move(P))
    if t < t0 or t > t1 + TRAIL_N:
        return
    pts = []
    for i in range(TRAIL_N * TRAIL_SUB + 1):
        tt = min(t, t1) - i / float(TRAIL_SUB)
        if tt < t0:
            break
        x0, y0, x1, y1, _hw = _seg(xf(inst, ps, sl, tt))
        pts.append((x1, y1, x0 + (x1 - x0) * TRAIL_BAND, y0 + (y1 - y0) * TRAIL_BAND))
    fade = 1.0 if t <= t1 else 1 - (t - t1) / float(TRAIL_N)
    bright = S.mix(c, S.HOT, 0.45)
    n = len(pts)
    for i in range(n - 1):
        a, b = pts[i], pts[i + 1]
        q = i / float(max(1, n - 1))
        pen.poly([(a[0], a[1]), (b[0], b[1]), (b[2], b[3]), (a[2], a[3])], c, 110 * (1 - q) * fade)
        pen.line(a[0], a[1], b[0], b[1], bright, 230 * (1 - q) * fade, 2.0 * ps * (1 - q) + 0.3)


def _draw_ghosts(pen, inst, ps, c, sl, t):
    """Afterimages: the blade's outline where it was a few ticks ago."""
    P = inst.fx["params"]
    if t < SUMMON or t > SUMMON + _move(P) + 6:
        return
    for k in (2, 4, 6):
        tt = t - k
        if tt < SUMMON:
            continue
        o = xf(inst, ps, sl, tt)
        near = -1.0 if o.nz > 0 else 1.0
        for (role, pts) in o.m["parts"]:
            if role in ("grip", "dark"):
                continue
            pen.poly([o.pt(u, v, near) for (u, v) in pts], c, 70 * (1 - k / 8.0))


# ---------------------------------------------------------------- events
def _spikes(pen, x, y, ang, n, r_out, r_in, c, a):
    pts = []
    for j in range(2 * n):
        rr = r_out if j % 2 == 0 else r_in
        an = ang + math.pi * j / n
        pts.append((x + math.cos(an) * rr, y + math.sin(an) * rr))
    pen.poly(pts, c, a)


def _ev_slam(pen, inst, c, ps, x, y, a, k, salt):
    life = EVT_LIFE["slam"]
    q = a / float(life)
    if a < 5:
        pen.glow(x, y, (26 + 30 * S.ease_out3(a / 5.0)) * ps * k, S.HOT, 255 * (1 - a / 5.0))
    e = S.ease_out3(q)
    for (d0, kk) in ((0, 1.0), (4, 1.5)):
        aa = a - d0
        if aa < 0:
            continue
        qq = aa / float(life - d0)
        ee = S.ease_out3(qq)
        rr = (10 + 60 * ee) * ps * k * kk
        pen.ring(x, y, rr, rr * 0.28, 0.0, c, 210 * (1 - qq), 3.2 * ps * (1 - qq) + 0.3)
        pen.ring(x, y, rr, rr * 0.28, 0.0, S.HOT, 150 * (1 - qq) ** 2, 1.2 * ps * (1 - qq) + 0.2)
    pen.glow(x, y, (20 + 26 * e) * ps * k, c, 150 * (1 - q), 0.4)
    dens = float(inst.fx["params"].get("density") or 1)
    # cracks running along the ground
    for j in range(6):
        r = S.rng_for(inst.seed, j, 71 + salt)
        side = 1 if j % 2 == 0 else -1
        L = r.uniform(30, 60) * ps * k * S.ease_out3(min(1.0, a / 6.0))
        pts = [(x, y)]
        for s in range(1, 5):
            pts.append((x + side * L * s / 4.0, y + r.uniform(-4, 4) * ps + r.uniform(-0.15, 0.15) * L * s / 4.0))
        pen.polyline(pts, S.mix(c, S.HOT, 0.5), 230 * (1 - q), 1.6 * ps)
    # rocks thrown up
    pen.add(False)
    n = max(0, F.jround(8 * dens * k))
    for j in range(n):
        r = S.rng_for(inst.seed, j, 73 + salt)
        life_j = r.uniform(16, 26)
        if a >= life_j:
            continue
        vx = r.uniform(-3.5, 3.5) * ps
        vy = r.uniform(-7, -3.5) * ps
        px, py = x + vx * a, y + vy * a + 0.35 * ps * a * a
        sz = r.uniform(1.6, 3.8) * ps * k
        rot = r.uniform(0, 6.28) + a * 0.3
        pts = [(px + math.cos(rot + i * 2.1) * sz, py + math.sin(rot + i * 2.1) * sz) for i in range(3)]
        pen.poly(pts, S.mix((90, 80, 70), c, 0.15), 230 * (1 - a / life_j))
    pen.add(True)


def _ev_cuts(pen, inst, c, ps, x, y, a, n, salt):
    life = EVT_LIFE["cuts"]
    bright = S.mix(c, S.HOT, 0.5)
    for j in range(n):
        aj = a - j
        if aj < 0 or aj >= life - 4:
            continue
        r = S.rng_for(inst.seed, j, 77 + salt)
        if n == 1:
            an = r.uniform(-0.1, 0.1)
            L = 120 * ps
            ox, oy = 0.0, 0.0
        else:
            an = r.uniform(0, math.pi)
            L = r.uniform(40, 70) * ps
            ox, oy = r.uniform(-12, 12) * ps, r.uniform(-12, 12) * ps
        q = aj / float(life - 4)
        e = S.ease_out3(min(1.0, aj / 2.0))
        ux, uy = math.cos(an), math.sin(an)
        cx, cy = x + ox, y + oy
        hl = L * (0.4 + 0.6 * e)
        pen.diamond(cx - ux * hl, cy - uy * hl, cx + ux * hl, cy + uy * hl, 2.6 * ps * (1 - q) + 0.3, c, 230 * (1 - q))
        pen.diamond(cx - ux * hl * 0.9, cy - uy * hl * 0.9, cx + ux * hl * 0.9, cy + uy * hl * 0.9,
                    0.9 * ps * (1 - q) + 0.2, S.HOT, 255 * (1 - q))
    # the delayed burst when every cut lands at once
    b = a - (n + 2)
    if 0 <= b < 10:
        qb = b / 10.0
        pen.glow(x, y, (22 + 30 * S.ease_out3(qb)) * ps, bright, 230 * (1 - qb))
        rr = (8 + 40 * S.ease_out3(qb)) * ps
        pen.ring(x, y, rr, rr, 0.0, c, 200 * (1 - qb), 2.4 * ps * (1 - qb) + 0.2)


def _ev_xflash(pen, inst, c, ps, x, y, a, k, spread):
    life = EVT_LIFE["xflash"]
    q = a / float(life)
    e = S.ease_out3(min(1.0, a / 4.0))
    ang = math.atan2(inst.tq_f[1], inst.tq_f[0])
    L = (22 + 14 * e) * ps * k
    for sg in (1, -1):
        an = ang + sg * spread * S.D
        ux, uy = math.cos(an), math.sin(an)
        pen.diamond(x - ux * L, y - uy * L, x + ux * L, y + uy * L, 3.4 * ps * k * (1 - q) + 0.3, c, 230 * (1 - q))
        pen.diamond(x - ux * L * 0.9, y - uy * L * 0.9, x + ux * L * 0.9, y + uy * L * 0.9, 1.2 * ps * (1 - q) + 0.2,
                    S.HOT, 255 * (1 - q))
    rr = (6 + 26 * S.ease_out3(q)) * ps * k
    pen.ring(x, y, rr, rr, 0.0, c, 200 * (1 - q), 2.0 * ps * (1 - q) + 0.2)
    if a < 6:
        pen.glow(x, y, 20 * ps * k, S.HOT, 255 * (1 - a / 6.0))


def _ev_pillar(pen, inst, c, ps, x, y, a, k):
    life = EVT_LIFE["pillar"]
    q = a / float(life)
    e = S.ease_out3(min(1.0, a / 5.0))
    H = 260 * ps * e
    w = 14 * ps * k * (1 - q) * (0.85 + 0.15 * math.sin(a * 1.7))
    pen.poly([(x - w, y), (x - w * 0.6, y - H), (x + w * 0.6, y - H), (x + w, y)], c, 170 * (1 - q))
    pen.poly([(x - w * 0.4, y), (x - w * 0.2, y - H), (x + w * 0.2, y - H), (x + w * 0.4, y)], S.HOT, 230 * (1 - q))
    for j in range(3):
        rr = (14 + 40 * S.ease_out3(min(1.0, (a - j * 3) / 14.0))) * ps * k
        if a < j * 3:
            continue
        pen.ring(x, y, rr, rr * 0.3, 0.0, c, 200 * (1 - q), 2.4 * ps * (1 - q) + 0.2)
    if a < 6:
        pen.glow(x, y, 40 * ps * k, S.HOT, 255 * (1 - a / 6.0))
    pen.glow(x, y, 30 * ps * k * (1 - q), c, 160 * (1 - q))


def _rune_ring(pen, inst, c, ps, x, y, R, ry, rot, a8, alpha, salt):
    pen.ring(x, y, R, ry, 0.0, c, alpha, 1.6 * ps)
    pen.ring(x, y, R * 0.8, ry * 0.8, 0.0, S.mix(c, S.HOT, 0.4), alpha * 0.8, 1.0 * ps)
    for j in range(8):
        an = rot + j * math.pi / 4
        gx, gy = x + math.cos(an) * R * 0.9, y + math.sin(an) * ry * 0.9
        r = S.rng_for(inst.seed, j, 81 + salt)
        sz = r.uniform(2.5, 4.0) * ps
        pen.diamond(gx - sz, gy, gx + sz, gy, sz * 0.6, S.HOT, alpha * a8)


def _ev_runes(pen, inst, c, ps, x, y, a, k, salt):
    life = EVT_LIFE["runes"]
    q = a / float(life)
    e = S.ease_out3(min(1.0, a / 6.0))
    R = 36 * ps * k * e
    _rune_ring(pen, inst, c, ps, x, y + 4 * ps, R, R * 0.32, a * 0.08, 1.0, 220 * (1 - q * q), salt)
    for j, b in enumerate((6, 12, 18)):
        ab = a - b
        if ab < 0 or ab >= 14:
            continue
        r = S.rng_for(inst.seed, j, 83 + salt)
        bx = x + r.uniform(-10, 10) * ps
        if ab < 3:
            yy = y - 120 * ps * (1 - ab / 3.0)
            pen.line(bx, yy - 30 * ps, bx, yy, c, 220, 3.0 * ps)
            pen.line(bx, yy - 30 * ps, bx, yy, S.HOT, 255, 1.2 * ps)
            pen.glow(bx, yy, 8 * ps, S.HOT, 240)
        else:
            qb = (ab - 3) / 11.0
            pen.glow(bx, y, (14 + 16 * S.ease_out3(qb)) * ps * k, S.mix(c, S.HOT, 0.5), 230 * (1 - qb))
            _spikes(pen, bx, y, r.uniform(0, 1), 5, (10 + 10 * S.ease_out3(qb)) * ps * k, 4 * ps * k, S.HOT,
                    220 * (1 - qb))


def _ev_glyph(pen, inst, c, ps, x, y, a, k, salt):
    life = EVT_LIFE["glyph"]
    q = a / float(life)
    R = (8 + 34 * S.ease_out3(q)) * ps * k
    _rune_ring(pen, inst, c, ps, x, y, R, R, a * 0.12, 1.0, 230 * (1 - q), salt)
    if a < 5:
        pen.glow(x, y, 18 * ps * k, S.HOT, 255 * (1 - a / 5.0))


def _ev_burst(pen, inst, c, ps, x, y, a, k, salt):
    life = EVT_LIFE["burst"]
    q = a / float(life)
    if a < 5:
        pen.glow(x, y, (14 + 20 * S.ease_out3(a / 5.0)) * ps * k, S.HOT, 255 * (1 - a / 5.0))
    pen.glow(x, y, (18 + 18 * S.ease_out3(q)) * ps * k, c, 170 * (1 - q), 0.4)
    for j in range(10):
        r = S.rng_for(inst.seed, j, 87 + salt)
        an = r.uniform(0, math.pi * 2)
        r1 = (6 + 30 * S.ease_out3(q)) * ps * k
        ln = r.uniform(8, 18) * ps * k * (1 - q)
        ca, sa = math.cos(an), math.sin(an)
        pen.line(x + ca * r1, y + sa * r1, x + ca * (r1 + ln), y + sa * (r1 + ln), S.mix(S.HOT, c, q), 230 * (1 - q),
                 1.4 * ps)
    rr = (6 + 30 * S.ease_out3(q)) * ps * k
    pen.ring(x, y, rr, rr, 0.0, c, 190 * (1 - q), 2.0 * ps * (1 - q) + 0.2)


def _ev_charge(pen, inst, c, ps, x, y, a, dur, k, salt):
    if a >= dur + 3:
        return
    q = min(1.0, a / float(max(1, dur)))
    fade = 1.0 if a < dur else 1 - (a - dur) / 3.0
    pen.glow(x, y, (4 + 14 * S.ease_in3(q)) * ps * k, c, 200 * fade)
    pen.glow(x, y, (2 + 6 * q) * ps * k, S.HOT, 240 * fade)
    for j in range(8):
        r = S.rng_for(inst.seed, j, 89 + salt)
        per = r.uniform(6, 10)
        ph = ((a + r.uniform(0, per)) % per) / per
        an = r.uniform(0, math.pi * 2)
        d0 = (34 * (1 - ph) + 4) * ps * k
        d1 = d0 + 10 * ps * k * (1 - ph)
        ca, sa = math.cos(an), math.sin(an)
        pen.line(x + ca * d1, y + sa * d1, x + ca * d0, y + sa * d0, S.mix(c, S.HOT, 0.4), 200 * fade * ph, 1.2 * ps)
    rr = 26 * ps * k * (1 - q) + 4 * ps
    pen.ring(x, y, rr, rr, 0.0, c, 160 * fade * q, 1.4 * ps)


def _ev_petals(pen, inst, ps, c, te, t, salt):
    P = inst.fx["params"]
    life = EVT_LIFE["petals"]
    t1 = SUMMON + _move(P)
    dens = float(P.get("density") or 1)
    pen.add(False)
    tau = max(te, t - life + 1)
    while tau <= min(t, t1):
        n = max(0, F.jround(2 * dens))
        x0, y0, x1, y1, _hw = _seg(xf(inst, ps, 0, tau))
        for j in range(n):
            r = S.rng_for(inst.seed, tau * 7 + j, 91 + salt)
            a = t - tau
            q = a / float(life)
            vx = r.uniform(-1.5, 1.5) * ps
            vy = r.uniform(-1.2, 0.4) * ps
            px = x1 + vx * a + math.sin(a * 0.3 + j) * 3 * ps
            py = y1 + vy * a + 0.04 * ps * a * a
            rot = r.uniform(0, 6.28) + a * 0.25
            sz = r.uniform(1.8, 3.0) * ps
            ux, uy = math.cos(rot) * sz, math.sin(rot) * sz
            pen.diamond(px - ux, py - uy, px + ux, py + uy, sz * 0.55, S.mix(c, (200, 20, 40), 0.6), 230 * (1 - q))
        tau += 1
    pen.add(True)


def _ev_blink(pen, inst, c, ps, x, y, a, k):
    life = EVT_LIFE["blink"]
    q = a / float(life)
    rr = (20 * (1 - S.ease_out3(q)) + 2) * ps * k
    pen.ring(x, y, rr, rr, 0.0, S.mix(c, S.HOT, 0.4), 230 * (1 - q), 2.0 * ps)
    if a < 4:
        pen.glow(x, y, 16 * ps * k, S.HOT, 255 * (1 - a / 4.0))
    pen.glow(x, y, 12 * ps * k * (1 - q), c, 170 * (1 - q))


def _ev_implode(pen, inst, c, ps, x, y, a, k, salt):
    """Void implosion: rings, streaks and a dark sphere collapse to a point,
    then it pops in a flash and a ring."""
    R = 34 * ps * k
    if a < IMPLODE_IN:
        q = a / float(IMPLODE_IN)
        e = S.ease_in3(q)
        pen.glow(x, y, R * (1.0 - 0.6 * e), c, 120 + 80 * q)
        for j in range(3):
            rr = R * (1 - e) * (1 - 0.25 * j) + 1.5 * ps
            pen.ring(x, y, rr, rr, 0.0, S.mix(c, S.HOT, 0.3 * j), 200 * (0.4 + 0.6 * q), 1.6 * ps)
        for j in range(10):
            r = S.rng_for(inst.seed, j, 93 + salt)
            an = r.uniform(0, math.pi * 2)
            d0 = R * 1.3 * (1 - e) * r.uniform(0.7, 1.1) + 2 * ps
            d1 = d0 + 9 * ps * k * (1 - q)
            ca, sa = math.cos(an), math.sin(an)
            pen.line(x + ca * d1, y + sa * d1, x + ca * d0, y + sa * d0, S.mix(c, S.HOT, 0.4), 210 * q, 1.2 * ps)
        pen.add(False)
        pen.glow(x, y, (4 + 0.55 * R / ps * (1 - e)) * ps, VOID, 235, 0.7)
        pen.add(True)
        return
    b = a - IMPLODE_IN
    q = b / float(EVT_LIFE["implode"] - IMPLODE_IN)
    if b < 4:
        pen.glow(x, y, (10 + 18 * S.ease_out3(b / 4.0)) * ps * k, S.HOT, 255 * (1 - b / 4.0))
    pen.glow(x, y, (14 + 26 * S.ease_out3(q)) * ps * k, c, 190 * (1 - q), 0.4)
    for j in range(8):
        r = S.rng_for(inst.seed, j, 95 + salt)
        an = r.uniform(0, math.pi * 2)
        r1 = (4 + 34 * S.ease_out3(q)) * ps * k
        ln = r.uniform(8, 16) * ps * k * (1 - q)
        ca, sa = math.cos(an), math.sin(an)
        pen.line(x + ca * r1, y + sa * r1, x + ca * (r1 + ln), y + sa * (r1 + ln), S.mix(S.HOT, c, q), 230 * (1 - q),
                 1.3 * ps)
    rr = (4 + 40 * S.ease_out3(q)) * ps * k
    pen.ring(x, y, rr, rr, 0.0, c, 220 * (1 - q), 2.2 * ps * (1 - q) + 0.2)
    pen.add(False)
    pen.glow(x, y, 6 * ps * k * (1 - q), VOID, 220 * (1 - q), 0.7)
    pen.add(True)


def _draw_events(pen, inst, ps, c, t):
    P = inst.fx["params"]
    if not _sig(P):
        return
    for n, e in enumerate(_w(P)["events"]):
        kind = e[1]
        te = _tick_of(P, e[0])
        a = t - te
        if kind == "petals":
            if a >= 0:
                _ev_petals(pen, inst, ps, c, te, t, n * 13)
            continue
        if kind == "charge":
            dur = F.jround(e[4] * _move(P))
            if 0 <= a < dur + 3:
                x, y = _ev_pos(inst, ps, e, t)
                _ev_charge(pen, inst, c, ps, x, y, a, dur, e[3], n * 13)
            continue
        if a < 0 or a >= EVT_LIFE[kind]:
            continue
        x, y = _ev_pos(inst, ps, e, te)
        k = e[3]
        if kind == "slam":
            _ev_slam(pen, inst, c, ps, x, y, a, k, n * 13)
        elif kind == "cuts":
            _ev_cuts(pen, inst, c, ps, x, y, a, F.trunc(k), n * 13)
        elif kind == "xflash":
            _ev_xflash(pen, inst, c, ps, x, y, a, k, 45.0)
        elif kind == "snip":
            _ev_xflash(pen, inst, c, ps, x, y, a, k, 18.0)
        elif kind == "pillar":
            _ev_pillar(pen, inst, c, ps, x, y, a, k)
        elif kind == "runes":
            _ev_runes(pen, inst, c, ps, x, y, a, k, n * 13)
        elif kind == "glyph":
            _ev_glyph(pen, inst, c, ps, x, y, a, k, n * 13)
        elif kind == "burst":
            _ev_burst(pen, inst, c, ps, x, y, a, k, n * 13)
        elif kind == "blink":
            _ev_blink(pen, inst, c, ps, x, y, a, k)
        elif kind == "implode":
            _ev_implode(pen, inst, c, ps, x, y, a, k, n * 13)


# ---------------------------------------------------------------- shots drawing
def _draw_shots(pen, inst, ps, c, t):
    for s in _shots(inst, ps):
        k = t - s.b
        e, stopped = s.end(inst)
        sz = s.size * ps
        bright = S.mix(c, S.HOT, 0.5)
        # muzzle flash
        if k < 4:
            q = k / 4.0
            pen.glow(s.ox, s.oy, (8 + 8 * q) * sz, c, 220 * (1 - q))
            S._star(pen, s.ox, s.oy, s.dx, s.dy, 12 * sz * (1 - 0.4 * q), 5 * sz, S.HOT, 230 * (1 - q), 1.2 * ps)
        if s.kind == "beam":
            if t < e:
                q = k / float(BEAM_T)
                L = s.rng * S.ease_out3(min(1.0, k / 2.0))
                x2, y2 = s.ox + s.dx * L, s.oy + s.dy * L
                wd = (7 + 2 * math.sin(k * 1.9)) * sz * (1 - q * q)
                pen.line(s.ox, s.oy, x2, y2, c, 200, wd * 2.0)
                pen.line(s.ox, s.oy, x2, y2, bright, 230, wd)
                pen.line(s.ox, s.oy, x2, y2, S.HOT, 255, wd * 0.4)
                for j in range(4):
                    u = ((k * 0.11 + j * 0.25) % 1.0)
                    rx, ry = s.ox + s.dx * L * u, s.oy + s.dy * L * u
                    pen.ring(rx, ry, 3 * sz, wd * 1.3, math.atan2(s.dy, s.dx), S.HOT, 160 * (1 - q), 1.0 * ps)
                pen.glow(x2, y2, wd * 2.4, c, 200 * (1 - q))
            continue
        if s.kind == "rail":
            if t < e:
                # an instant thin line with a black void core, a violet rim
                # and two strands of light twisting round it
                q = k / float(RAIL_T)
                x2, y2 = s.ox + s.dx * s.rng, s.oy + s.dy * s.rng
                wd = 3.0 * sz * (1 - q * q)
                pen.line(s.ox, s.oy, x2, y2, c, 150, wd * 3.2)
                pen.line(s.ox, s.oy, x2, y2, bright, 230, wd * 1.5)
                n = 32
                for sg in (1, -1):
                    pts = []
                    for j in range(n + 1):
                        u = j / float(n)
                        o = sg * math.sin(u * 30 - k * 1.3) * wd * 2.2
                        pts.append((s.ox + s.dx * s.rng * u - s.dy * o, s.oy + s.dy * s.rng * u + s.dx * o))
                    pen.polyline(pts, S.mix(c, S.HOT, 0.3), 200 * (1 - q), 0.9 * ps)
                pen.glow(x2, y2, wd * 3.0, c, 160 * (1 - q))
                pen.add(False)
                pen.line(s.ox, s.oy, x2, y2, VOID, 240, wd * 0.7)
                pen.add(True)
            continue
        if t < e:
            x, y = s.pos(k)
            if s.kind == "arrow":
                tx, ty = s.pos(max(0.0, k - 2.2))
                pen.diamond(tx, ty, x, y, 1.6 * sz, c, 200)
                pen.diamond(tx, ty, x, y, 0.6 * sz, S.HOT, 255)
                for sg in (1, -1):
                    pen.line(tx, ty, tx - s.dx * 5 * sz - s.dy * sg * 4 * sz, ty - s.dy * 5 * sz + s.dx * sg * 4 * sz,
                             bright, 200, 1.2 * ps)
                pen.glow(x, y, 6 * sz, bright, 220)
            else:
                tail = 1.6 if s.kind == "neon" else 2.4
                tx, ty = s.pos(max(0.0, k - tail))
                pen.diamond(tx, ty, x, y, 2.4 * sz, c, 190)
                pen.diamond(tx, ty, x, y, 1.0 * sz, S.HOT, 255)
                pen.glow(x, y, 7 * sz, c, 170)
                if s.kind == "spark":
                    pts = []
                    for j in range(6):
                        r = S.rng_for(inst.seed, s.i * 31 + j, t)
                        u = j / 5.0
                        px, py = tx + (x - tx) * u, ty + (y - ty) * u
                        o = r.uniform(-4, 4) * sz
                        pts.append((px - s.dy * o, py + s.dx * o))
                    pen.polyline(pts, bright, 230, 1.1 * ps)
            continue
        a = t - e
        if a >= IMPACT_LIFE:
            continue
        if stopped:
            h = inst.tq_ki[s.i]
            x, y = h[1], h[2]
        else:
            x, y = s.pos(s.flight)
        q = a / float(IMPACT_LIFE)
        if a < 4:
            pen.glow(x, y, (8 + 10 * S.ease_out3(a / 4.0)) * sz, S.HOT, 255 * (1 - a / 4.0))
        pen.glow(x, y, (8 + 12 * S.ease_out3(q)) * sz, c, 190 * (1 - q), 0.4)
        rr = (3 + 14 * S.ease_out3(q)) * sz
        pen.ring(x, y, rr, rr, 0.0, bright, 200 * (1 - q), 1.6 * ps * (1 - q) + 0.2)


def _draw_bow(pen, inst, o, c, a, ps, t):
    """The bow string, pulled back while it draws, and the nocked arrow."""
    P = inst.fx["params"]
    w = _w(P)
    ft = _tick_of(P, w["fire"][0][0]) if (w["fire"] and _sig(P)) else 1 << 30
    d0 = _tick_of(P, 0.1)
    if t < d0:
        pull = 0.0
    elif t < ft:
        pull = S.ease_in3((t - d0) / float(max(1, ft - d0)))
    else:
        pull = -0.15 * max(0.0, 1 - (t - ft) / 3.0)   # the string snaps past rest
    pu = -0.32 * pull
    top = o.pt(0.02, -0.5)
    bot = o.pt(0.02, 0.5)
    mid = o.pt(pu, 0.0)
    pen.add(True)
    pen.polyline([top, mid, bot], S.mix(c, S.HOT, 0.5), 230 * a, 1.1 * ps)
    if t < ft and _sig(P):
        tip = o.pt(pu + 0.62, 0.0)
        pen.line(mid[0], mid[1], tip[0], tip[1], c, 220 * a, 2.0 * ps)
        pen.line(mid[0], mid[1], tip[0], tip[1], S.HOT, 255 * a, 0.8 * ps)
        pen.glow(tip[0], tip[1], (4 + 6 * pull) * ps, c, 220 * a)


def draw(pen, inst, host, ps):
    P = inst.fx["params"]
    t = inst.age
    c, _bright, _deep = S._colours(inst, host)
    w = _w(P)
    u, ap, fd = _phase(P, inst.life, t)
    a = S.ease_out3(ap) * fd
    pen.add(True)
    _draw_events(pen, inst, ps, c, t)
    xfs = [xf(inst, ps, sl, t) for sl in range(_slots(P))]
    if _sig(P):
        for sl in range(_slots(P)):
            if not xfs[sl].m["blade"]:
                continue
            if w["trail"] == "swept":
                _draw_trail(pen, inst, ps, c, sl, t)
            elif w["trail"] == "ghost":
                _draw_ghosts(pen, inst, ps, c, sl, t)
    for sl in range(_slots(P)):
        o = xfs[sl]
        if fd > 0:
            _draw_weapon(pen, o, c, a, ps, t)
            if w["models"][sl] == "pulse_bow":
                _draw_bow(pen, inst, o, c, a, ps, t)
        pen.add(True)
        _draw_summon(pen, inst, o, c, ps, t)
        _draw_dismiss(pen, inst, o, c, ps, t)
    pen.add(True)
    _draw_shots(pen, inst, ps, c, t)
    S._hit_marks(pen, inst, c, ps, inst.tq_f[0], inst.tq_f[1])
