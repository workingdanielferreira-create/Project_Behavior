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
# Figure facing / rotation
# ---------------------------------------------------------------------------
# When True, every figure's sprite continuously rotates (MotionState.rotate ->
# Transform.angle, applied in figure.py's face()/draw()) to face its current
# travel/target direction, instead of only flipping left/right.  Applies to
# every mode uniformly (built-in Runner/Swordsman and any JSON-authored
# character) and identically in Solo and Battle -- there is a single Figure
# construction path (App.add_figure), so this one flag governs both.
ROTATE_TO_FACING_ENABLED = True

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
# Arc combo (50 % chance on hit; alternates CW/CCW per step)
ARC_COMBO_MAX_HITS      = 3     # total hits in one arc combo string (initial + 2 follow-ups)
ARC_COMBO_COOLDOWN_TICKS = 62  # 1 second at 62 fps before arc combo can fire again
ARC_RECOIL_PX           = 10.0  # how far to dash back from target after each hit
ARC_RECOIL_TICKS        = 12   # ticks for the recoil dash (~0.2 s at 62 fps)
ARC_ORBIT_ANGLE_DEG     = 150.0 # degrees to arc around the target between hits
ARC_REPO_TICKS          = 22   # ticks to travel the curved reposition arc

# Primary attack model — every fresh attack is a 50/50 pick between
# dashslash (straight dash) and arcslash (curved approach).
ARC_APPROACH_TICKS      = 24    # ticks for the primary arcslash curved approach
ARC_APPROACH_SWEEP_DEG  = 120.0 # degrees swept around the target during the approach
ATTACK_STRING_MAX_HITS  = 3     # hits per attack string (primary + 2 follow-ups)
ATTACK_STRING_COOLDOWN_TICKS = 62  # ~1 s after a full string before follow-ups chain again
FOLLOWUP_TYPE_LOCK_TICKS = 12   # 0.2 s: the OTHER follow-up type is locked after a 50/50 pick

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
CRESCENT_SPEED     = 0.4        # px/tick the arc travels forward
CRESCENT_LIFETIME  = 5          # ticks before it fully fades
CRESCENT_AHEAD     = 0        # px ahead of figure centre the arc starts
CRESCENT_RADIUS    = 42         # radius of the arc curve (Slash FX: was 30)
CRESCENT_SPAN      = 170        # total arc angle (degrees)
CRESCENT_WIDTH     = 6.5        # stroke width (Slash FX: was 3.5)
CRESCENT_TAIL      = 0.95       # fraction of arc trailing behind the tip
CRESCENT_SEGS      = 16         # draw segments for the alpha gradient

# ---------------------------------------------------------------------------
# Projectiles / shooting
# ---------------------------------------------------------------------------
PROJ_SPEED        = 8.0
PROJ_RADIUS       = 3
PROJ_MAX_AGE      = 220         # ~2 s
PROJ_HIT_RADIUS   = 16
PROJ_TRAIL_LEN    = 5           # history points per projectile cluster dot
SHOOT_INTERVAL    = 20         # ticks between phases; 3 phases × 20 ticks = ~1 full cycle/s

# ---------------------------------------------------------------------------
# Runner shot-cycle  (3-phase repeating pattern)
# Phase 0 — CONE   : 3 clusters spread in a fan
# Phase 1 — ZIGZAG : 2 clusters that weave toward the target
# Phase 2 — HOMING : 1 cluster that tracks the target at half speed
# After phase 2 a pause of SHOT_CYCLE_PAUSE_TICKS fires before repeating.
# ---------------------------------------------------------------------------
SHOT_CYCLE_PAUSE_TICKS  = 0     # no pause — cycle repeats immediately
SHOT_CONE_ANGLES        = (-45.0, 0.0, 45.0)     # single bullet, straight at target
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

# Fan spread (deg) across duplicate can_hit fx_layers fired together by a
# JSON character's action (see combat.fire_character_action) — e.g. mage's
# attack_special fires 5 particle layers spread across this arc.
CHAR_ATTACK_SPREAD_DEG = 24.0
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
# ULTIMATE_DURATION_TICKS ticks (~48 s at 62 fps — intentional extended barrage).
ULTIMATE_HP_THRESHOLD   = 0.4   # fraction of max_hp that triggers the ultimate
ULTIMATE_DURATION_TICKS = 3000   # ~48 s at 62 fps (intentional)

# ---------------------------------------------------------------------------
# Runner Survival Teleport (triggers at same HP threshold as ultimate)
# ---------------------------------------------------------------------------
# Every TELEPORT_INTERVAL_TICKS ticks while runner HP is at or below the
# threshold, the runner blinks to a point TELEPORT_DISTANCE_PX behind itself
# (opposite its current facing direction) relative to the combat target.
# The destination is clamped to screen bounds.  Shooting is NOT interrupted.
TELEPORT_INTERVAL_TICKS = 31    # ~1 s at 62 fps
TELEPORT_DISTANCE_PX    = 500.0 # px from target to land at

# ---------------------------------------------------------------------------
# Generic Blink system (data-driven; enabled per character by a JSON `blink`
# block — see characters/jumper.json).  A blink is a pure position warp with
# afterimage + spark FX; it never sets combat.acted by itself.  Identical in
# Solo and Battle: targeting always goes through world.melee_target /
# world.cursor, never through game-mode branches.
# ---------------------------------------------------------------------------
BLINK_COMBO_COOLDOWN_TICKS    = 12     # 0.2 s gate between combo teleports
BLINK_APPROACH_RANGE_PX       = 260.0  # distance covered per approach blink
BLINK_APPROACH_TRIGGER_PX     = 420.0  # only blink-approach when farther than this
BLINK_APPROACH_COOLDOWN_TICKS = 55     # ~0.9 s between approach blinks
BLINK_STORM_STRIKES           = 6      # teleport strikes in the blinkstorm ultimate
BLINK_STORM_INTERVAL_TICKS    = 6      # ticks between storm strikes
BLINK_STORM_RADIUS_PX         = 90.0   # ring radius around the target per strike
BLINK_FX_SPARKS               = 8      # crackle sparks per blink endpoint
BLINK_FX_SPARK_SPEED          = (2.0, 6.0)
BLINK_BOLT_SEGMENTS           = 9      # jagged electric bolt between endpoints
BLINK_BOLT_JITTER_PX          = 14.0   # perpendicular zig-zag amplitude

# ---------------------------------------------------------------------------
# Generic Clone system (engine support for the wizard's special_ability
# preset 'clone').  A clone is an autonomous ghost of its owner: it walks
# toward the owner's live target and strikes on contact via invisible
# projectiles (standard damage channel — Solo/Battle identical, IPC-safe).
# ---------------------------------------------------------------------------
CLONE_DURATION_MS_DEFAULT     = 3000   # lifetime before it dissolves
CLONE_COOLDOWN_MS_DEFAULT     = 8000   # min gap between clone spawns
CLONE_STRIKE_RADIUS_PX        = 110.0  # contact-strike range
CLONE_ATTACK_INTERVAL_TICKS   = 30     # ~0.5 s between clone strikes
CLONE_SPEED_FACTOR            = 0.8    # x owner's follow_speed
CLONE_ALPHA                   = 150    # ghost opacity (0-255)

# ---------------------------------------------------------------------------
# Per-mode tuning.  Keys match FigureMode.key.  This is the extension point:
# a new figure type registers a mode class and adds one dict here.
# ---------------------------------------------------------------------------
MODE_CONFIGS = {
    "runner": dict(
        chase_speed=3.0, follow_speed=4.5, anim_speed=5, idle_anim_speed=10,
        max_hp=100, basic_attack_radius=SLASH_RADIUS,
    ),
    "swordsman": dict(
        chase_speed=4.5, follow_speed=6.0, anim_speed=4, idle_anim_speed=8,
        max_hp=100, basic_attack_radius=SLASH_RADIUS,
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
COLLISION_DOT_RADIUS  = 3    # px

# ---------------------------------------------------------------------------
# Petals defensive FX (see combat.Petal / combat.update_petals)
# ---------------------------------------------------------------------------
PETAL_CATCH_RADIUS = 14.0    # px — how close a petal must get to consume a bullet
PETAL_TOUCH_PROJ_AGE = 6     # ticks — lifetime of the invisible touch projectile a
                             # petal spawns on enemy-figure contact; just long
                             # enough to enter the enemy side's snapshot and
                             # register the hit (identical in Solo & Battle).


# ---------------------------------------------------------------------------
# Diagnostics / action log
# ---------------------------------------------------------------------------
# Set True to write laser_cursor_log.txt next to the launcher.
# Flushes every 60 events; ~0 overhead when False.
LOG_ENABLED = True

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


# ---------------------------------------------------------------------------
# Swordsman Ultimate Crescent
# ---------------------------------------------------------------------------
# Fires once when the swordsman's HP first drops to/below 50% of max_hp.
# Two blades: the second fires ULTC_SECOND_DELAY_TICKS after the first.
# Speed: 100 px/s ≈ 1.6 px/tick at 62 fps.
# After ULTC_FADE_DIST px of travel the blade fades bottom-to-top.
# Deals 1 HP per tick to any overlapping enemy figure.
ULTC_THRESHOLDS         = (0.7, 0.5, 0.3)  # HP fractions that each trigger the ultimate
ULTC_RADIUS             = 100        # arc radius (px)
ULTC_SPAN               = 150.0      # arc span (degrees) — broad blade
ULTC_SPEED              = 25      # px/tick ≈ 100 px/s at 62 fps
ULTC_FADE_DIST          = 1000.0      # px of travel before fade begins
ULTC_WIDTH_OUTER        = 28.0       # stroke width for dark body fill pass
ULTC_WIDTH_INNER        = 6.0        # stroke width for bright rim pass
ULTC_SEGS               = 32         # draw segments for the arc gradient
ULTC_LIFETIME           = 600        # max ticks alive (safety cap)
ULTC_SECOND_DELAY_TICKS = 1          # ticks after 1st before 2nd fires
ULTC_HIT_FIGURE_DIST    = 40.0       # px — figure within this of arc surface takes 1 HP/tick
ULTC_CROSS_ANGLE        = 45.0       # degrees each blade is rotated ± from travel axis to form X


# ---------------------------------------------------------------------------
# Slash FX package (applies identically in Solo and Battle mode)
# ---------------------------------------------------------------------------
# Dash afterimages — crimson silhouettes ("speed ghosts") left behind during
# every dash, arc approach, recoil, and dodge.
AFTERIMAGE_INTERVAL   = 2       # dash ticks between ghost spawns
AFTERIMAGE_LIFETIME   = 14      # ticks a ghost takes to fade out
AFTERIMAGE_ALPHA      = 150     # starting alpha of a fresh ghost
AFTERIMAGE_RGB        = (225, 40, 55)   # crimson silhouette colour
AFTERIMAGE_MAX        = 12      # cap on live ghosts per figure

# Hit-stop — everything freezes for a few ticks on BIG hits only
# (attack-string finishers and ultimate launches).  Both sides share one
# clock, so attacker and victim freeze together in Battle mode.
HITSTOP_TICKS         = 5       # ~80 ms at 62 fps

# Impact shockwave ring + spark burst on every landed slash hit.
IMPACT_RING_LIFETIME  = 14      # ticks the ring expands and fades over
IMPACT_RING_RADIUS    = 46.0    # px max radius of the expanding ring
IMPACT_RING_WIDTH     = 3.5     # stroke width at spawn (thins as it grows)
IMPACT_SPARK_COUNT    = 8       # sparks per landed hit
IMPACT_SPARK_SPEED    = (4.0, 9.0)   # px/tick launch speed range
IMPACT_SPARK_LIFETIME = 12      # ticks before a spark dies

# Parry deflect — blocked bullets ricochet off the swordsman instead of
# vanishing.  Purely cosmetic: hit_r_sq = 0 (no collisions) and excluded
# from the enemy-side snapshot, so they can never deal damage in either mode.
DEFLECT_CONE_DEG      = 70.0    # total scatter cone around the away-axis
DEFLECT_SPEED_MULT    = 1.15    # deflected speed vs incoming speed
DEFLECT_MAX_AGE       = 45      # ticks a ricochet lives (~0.7 s)


# ---------------------------------------------------------------------------
# Bullet FX package (applies identically in Solo and Battle mode)
# ---------------------------------------------------------------------------
# Comet bolts — bullets render as elongated energy bolts stretched along
# their velocity.  Each shot phase has its own flair:
#   cone   = classic comet (3.5x)      zigzag = shorter, white-hot core (2.5x)
#   homing = comet + pulsing halo (3x) beam   = extra-long ultimate bolt (5x)
# Stretch reverted to 1.0 (round bullets + classic line trails) per Daniel;
# per-phase flair kept: zigzag white-hot core, homing pulsing halo.
BOLT_STRETCH_CONE     = 1.0
BOLT_STRETCH_ZIGZAG   = 1.0
BOLT_STRETCH_HOMING   = 1.0
BOLT_STRETCH_BEAM     = 1.0

# Muzzle flash at the firing point of every shot.
MUZZLE_FLASH_LIFETIME = 8       # ticks
MUZZLE_FLASH_RADIUS   = 15.0    # px at full bloom

# Bullet death burst — fires ONLY on impacts that reduce the target's HP.
# Blocked (parried) bullets ricochet without bursting.
BULLET_BURST_SPARKS      = 6
BULLET_BURST_RING_RADIUS = 22.0

# Off-screen projectile cull — bullets beyond this margin outside the screen
# are removed instead of living out PROJ_MAX_AGE far off-screen.
OFFSCREEN_CULL_MARGIN = 80.0

# ---------------------------------------------------------------------------
# Runner Beam Ultimate — replaces the sped-up cycle.  While the ultimate is
# active the runner fires BEAM_ROWS parallel long-tailed bolts EVERY tick.
# Each bolt flies in a fixed straight line once fired; the aim is recomputed
# at the live target every tick, so the beam sweeps as the shooter tracks.
# ---------------------------------------------------------------------------
BEAM_ROWS        = 1        # single row: a continuous STRING of bullets
BEAM_ROW_SPACING = 8.0      # (unused at 1 row; kept for future tuning)
BEAM_TRAIL_LEN   = 12       # long tails for the continuous-beam look
BEAM_MAX_AGE     = 150      # shorter life; beam bolts cross the screen fast
