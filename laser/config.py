"""
Central configuration — the single source of truth for every tunable value.

Everything that used to be a scattered module-level constant lives here, grouped
by concern.  Nothing in this file imports from the rest of the package, so it can
be read, patched, or serialised by a future tuning tool without side effects.

Conventions
-----------
* Values are plain module-level constants grouped under comment banners.
* Per-figure-mode tuning lives in `MODE_CONFIGS`, keyed by the mode's string key
  (see laser/modes.py).  Adding a mode adds one entry here — no other edits.
"""

# ---------------------------------------------------------------------------
# Window / loop
# ---------------------------------------------------------------------------
TICK_MS          = 16          # timer interval; ~62.5 fps
DEFAULT_SCREEN_W = 1920
DEFAULT_SCREEN_H = 1080

# ---------------------------------------------------------------------------
# Sprite sizing
# ---------------------------------------------------------------------------
# Run and idle frames were exported at different resolutions; we normalise both
# sets by head diameter.  Change TARGET_HEAD_PX to resize the whole companion
# while keeping every animation visually consistent.
TARGET_HEAD_PX        = 16.0
RUN_SRC_HEAD          = 75.0    # measured avg head diameter in Picture*.png
IDLE_SRC_HEAD         = 60.0    # head diameter in standing*.png
SLIDE_SRC_HEAD        = 135.0   # head diameter in slidingback*.png
SWORD_RUN_SRC_HEAD    = 105.0
SWORD_IDLE_SRC_HEAD   = 205.0
SWORD_SLASH_SRC_HEAD  = 155.0

BG_REMOVE_TOLERANCE   = 40      # black-background -> transparent threshold

# ---------------------------------------------------------------------------
# Trail (per figure)
# ---------------------------------------------------------------------------
TRAIL_LEN       = 50            # chase-mode tail length (points)
TRAIL_DECAY     = 2            # points dropped per idle tick
TRAIL_MIN_D_SQ  = 4.0          # min sq distance between recorded points
TRAIL_FLOW_SPD  = 0.008        # palette sweep speed along the trail
TRAIL_DOT_R     = 1            # core dot radius
TRAIL_GLOW_R    = 1            # glow radius
TRAIL_W_TAIL    = 1.0          # stroke width at the tail
TRAIL_W_HEAD    = 5.0          # stroke width at the head
TRAIL_BACK      = 8.0          # px the trail anchor sits behind the figure
TRAIL_DOWN      = 6.0          # px the trail anchor sits below the figure

# ---------------------------------------------------------------------------
# Cursor-collision bounce
# ---------------------------------------------------------------------------
BOUNCE_STRENGTH       = 12.0
BOUNCE_FRICTION       = 0.85
BOUNCE_THRESH_SQ      = 0.09    # speed^2 below this = fully stopped
BOUNCE_END_THRESH_SQ  = 4.0     # speed^2 below this = enter slide2 hold
BOUNCE_END_HOLD       = 8       # ticks slide2 frame is held before resuming run
HIT_RADIUS_SQ         = 225.0   # cursor within sqrt(225)=15px triggers bounce

# ---------------------------------------------------------------------------
# Runaway (flee the cursor)
# ---------------------------------------------------------------------------
RUNAWAY_RADIUS  = 120.0
RUNAWAY_SPEED   = 4.5

# ---------------------------------------------------------------------------
# Path-follow
# ---------------------------------------------------------------------------
PATH_MIN_D_SQ   = 16.0          # record a breadcrumb every ~4 px

# ---------------------------------------------------------------------------
# Swordsman slash / dash
# ---------------------------------------------------------------------------
SLASH_RADIUS      = 180.0
SLASH_SPEED_MUL   = 9.0
SLASH_HIT_RADIUS  = 20.0
SLASH_ANIM_SPD    = 3
COMBO_MAX               = 2     # max follow-up dashes per combo string
COMBO_COOLDOWN_TICKS    = 125   # ticks before follow-ups available again (~2 s at 62 fps)
COMBO_TRAVEL_TICKS_MIN  = 0     # follow-up dash travel time range in ticks (0 s)
COMBO_TRAVEL_TICKS_MAX  = 31    # follow-up dash travel time range in ticks (~0.5 s)

# ---------------------------------------------------------------------------
# Swordsman dodge sidestep
# ---------------------------------------------------------------------------
DODGE_TRIGGER_RADIUS = 90.0     # incoming bullet within this range triggers dodge
DODGE_SPEED          = 20.0     # px/tick during the sidestep

# ---------------------------------------------------------------------------
# Swordsman parry
# ---------------------------------------------------------------------------
PARRY_RADIUS         = 30.0     # px — bullets entering this radius trigger a parry
PARRY_COOLDOWN_TICKS = 19       # ~0.3 s at 62 fps before another parry can fire
PARRY_STANCE_TICKS   = 19       # ~0.3 s the active deflect window stays open

# ---------------------------------------------------------------------------
# Crescent wave
# ---------------------------------------------------------------------------
CRESCENT_SPEED     = 0.0        # px/tick the arc travels forward
CRESCENT_LIFETIME  = 5          # ticks before it fully fades
CRESCENT_AHEAD     = -10        # px ahead of figure centre the arc starts
CRESCENT_RADIUS    = 30         # radius of the arc curve
CRESCENT_SPAN      = 270        # total arc angle (degrees)
CRESCENT_WIDTH     = 3.5        # stroke width
CRESCENT_TAIL      = 0.95       # fraction of arc trailing behind the tip
CRESCENT_SEGS      = 16         # draw segments for the alpha gradient

# ---------------------------------------------------------------------------
# Projectiles / shooting
# ---------------------------------------------------------------------------
PROJ_SPEED        = 8.0
PROJ_RADIUS       = 3
PROJ_MAX_AGE      = 120         # ~2 s
PROJ_HIT_RADIUS   = 16
PROJ_TRAIL_LEN    = 3           # history points per projectile cluster dot
SHOOT_INTERVAL    = 32          # ticks between shots in non-battle shoot mode

# ---------------------------------------------------------------------------
# Runner shot-cycle  (3-phase repeating pattern)
# Phase 0 — CONE   : 3 clusters spread in a fan
# Phase 1 — ZIGZAG : 2 clusters that weave toward the target
# Phase 2 — HOMING : 1 cluster that tracks the target at half speed
# After phase 2 a pause of SHOT_CYCLE_PAUSE_TICKS fires before repeating.
# ---------------------------------------------------------------------------
SHOT_CYCLE_PAUSE_TICKS  = 31    # ~0.5 s at 62 fps between cycles
SHOT_CONE_ANGLES        = (0.0,)                # single bullet straight at target
SHOT_ZIGZAG_AMPLITUDE   = 55.0  # px lateral offset for each zigzag cluster
SHOT_ZIGZAG_FREQUENCY   = 0.18  # radians/tick of the sinusoidal weave
SHOT_HOMING_SPEED_MULT  = 0.5   # fraction of PROJ_SPEED for the homing cluster

# Legacy fan angles kept for non-runner modes (swordsman battle fire, etc.)
SHOT_ANGLES = (0.0,)           # single bullet

# ---------------------------------------------------------------------------
# Battle / AI
# ---------------------------------------------------------------------------
BATTLE_BODY_HIT_SQ        = 18.0 * 18.0
BATTLE_BODY_PUSH          = 14.0
DASH_HIT_KNOCKBACK_PX     = 200.0  # target travels this many px when struck by a dash-slash
BATTLE_PROJ_HIT_SQ   = 20.0 * 20.0
HIT_POWER_BASE       = 30.0
HIT_POWER_STEP       = 3.0
HIT_POWER_MAX        = 1000.0
WALL_ZONE            = 250       # px from edge where soft repulsion begins
WALL_PUSH            = 400       # max px nudge at the wall
DAZE_TICKS_RANGE     = (15, 45)
RETREAT_TICKS_RANGE  = (10, 30)
SHOOT_INTERVAL_RANGE = (18, 58)  # per-figure randomised battle fire cadence
# Shooter knockback immunity cycle:
#   receive KNOCKBACK_LIMIT knockbacks → immune for next IMMUNITY_HIT_LIMIT hits → repeat
KNOCKBACK_LIMIT      = 3         # knockbacks before immunity kicks in
IMMUNITY_HIT_LIMIT   = 10        # hits absorbed while immune before resetting

# ---------------------------------------------------------------------------
# Where each figure sits relative to the cursor (so they don't fully overlap)
# +x = right of cursor, +y = below cursor (screen px)
# ---------------------------------------------------------------------------
FIGURE_OFFSETS = [(100, 0), (30, 6), (-30, 6), (34, -14),
                  (-34, -14), (54, 2), (-54, 2), (0, 20)]
MAX_FIGURES    = 8

# ---------------------------------------------------------------------------
# Hit Points (HP)
# ---------------------------------------------------------------------------
# Each figure starts with max_hp from its mode config.  When HP reaches 0 the
# instance calls request_quit() and the process exits.
# Solo mode: cursor-bounce collisions cost 1 HP per hit.
# Battle mode: every enemy hit (projectile, dash-slash, body-slam) costs 1 HP.
HP_DISPLAY_FONT_SIZE  = 14       # pt — neon HP readout bottom-right
HP_DISPLAY_MARGIN_R   = 18       # px from right edge per figure slot
HP_DISPLAY_MARGIN_B   = 48       # px above the taskbar

# ---------------------------------------------------------------------------
# Runner Ultimate Attack
# ---------------------------------------------------------------------------
# When HP drops to or below max_hp * ULTIMATE_HP_THRESHOLD, the runner enters
# an ultimate state: shooting frequency becomes 0 (fires every tick) for
# ULTIMATE_DURATION_TICKS ticks (~3 s at 62 fps).
ULTIMATE_HP_THRESHOLD   = 0.5   # fraction of max_hp that triggers the ultimate
ULTIMATE_DURATION_TICKS = 187   # ~3 s at 62 fps

# ---------------------------------------------------------------------------
# Per-mode tuning.  Keys match FigureMode.key.  This is the extension point:
# a new figure type registers a mode class and adds one dict here.
# ---------------------------------------------------------------------------
MODE_CONFIGS = {
    "runner": dict(
        chase_speed=3.0, follow_speed=4.5, anim_speed=5, idle_anim_speed=10,
        max_hp=60,
    ),
    "swordsman": dict(
        chase_speed=4.5, follow_speed=6.0, anim_speed=4, idle_anim_speed=8,
        max_hp=100,
    ),
}

# Order modes cycle through with Alt+Left / Alt+Right.
MODE_ORDER = ["runner", "swordsman"]

# ---------------------------------------------------------------------------
# Collision impact dot FX
# ---------------------------------------------------------------------------
# At ~62 fps: appear for ~0.5 s then fade over ~0.3 s → total lifetime ~0.8 s
COLLISION_DOT_HOLD    = 31   # ticks dot stays at full brightness  (~0.5 s)
COLLISION_DOT_FADE    = 19   # ticks it takes to fade to transparent (~0.3 s)
COLLISION_DOT_RADIUS  = 5    # px


# ---------------------------------------------------------------------------
# Diagnostics / action log
# ---------------------------------------------------------------------------
# Set True to write laser_cursor_log.txt next to the launcher.
# Flushes every 60 events; ~0 overhead when False.
LOG_ENABLED = False

# ---------------------------------------------------------------------------
# Bullet-vs-bullet scatter (cross-fire collision)
# ---------------------------------------------------------------------------
# Distance (px) at which two crossing bullets register a collision.
BULLET_COLLIDE_DIST_SQ   = 12.0 * 12.0   # 12 px detection radius
# Each splinter is this fraction of the parent's visual radius.
SPLINTER_RADIUS_SCALE    = 0.333          # splinter radius = PROJ_RADIUS * scale = ~1 px
# Splinters live for this many ticks (shorter than normal bullets).
SPLINTER_MAX_AGE         = 30            # ~0.5 s
# Splinters travel at this multiplier of the parent's speed.
SPLINTER_SPEED_MULT      = 1.4
# Spread angle (degrees) between the three perpendicular splinters.
SPLINTER_SPREAD_DEG      = 55.0
