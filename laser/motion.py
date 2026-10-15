"""
Motion — non-combat movement strategies for a Figure.

`update` runs the chase / path-follow / runaway / cursor-bounce state machine,
then updates facing, trail, and animation.  Combat movement (dash/dodge/slash)
is handled separately by the combat system, which short-circuits before this
runs when a figure is mid-attack.
"""

import math

from . import config
from . import combat as _combat


def update(fig, tx, ty, collision_on, path_follow, runaway, offset=None):
    """Advance one figure's position toward (tx, ty) for this tick.
    offset: the chase offset to use instead of the figure's formation offset
    (actions.chase_offset).  Returns (cx, cy) if a cursor-collision bounce
    was triggered this tick, otherwise None."""
    m = fig.motion
    t = fig.transform

    # Toggling follow mode clears the persistent path trail.
    if path_follow != m.follow:
        fig.trail.clear()
    m.follow = path_follow
    m.runaway = runaway

    # Cursor-collision bounce trigger.
    cursor_hit = None
    if collision_on and not m.bouncing and not m.bounce_ending:
        dx = tx - t.x
        dy = ty - t.y
        d_sq = dx * dx + dy * dy
        hb = fig.mode.hurtbox_radius()
        bs = fig.mode.body_scale()
        hit_sq = hb * hb if hb else config.HIT_RADIUS_SQ * bs * bs
        if 0 < d_sq < hit_sq:
            inv = config.BOUNCE_STRENGTH / (d_sq ** 0.5)
            m.bounce_vx = -dx * inv
            m.bounce_vy = -dy * inv
            m.bouncing = True
            cursor_hit = (t.x, t.y)

    ox, oy = t.x, t.y

    # Position speed scale: every movement step below is multiplied by this
    # figure's own bilinear speed factor, so a fighter at the bottom-left runs at 100% and one at the
    # top-right at 40% — the same four-corner grid the sprite size uses.
    # Read from the figure's live position each tick, identical maths for
    # both fielded fighters, so Solo and Battle match automatically.
    sf = _combat.position_speed_scale(t.x, t.y, fig.screen_w, fig.screen_h)

    if m.bouncing:
        _bounce(fig, sf)
    elif m.bounce_ending:
        _bounce_end(fig)
    elif not t.init:
        t.x, t.y = tx, ty
        t.init = True
        m.path.clear()
    elif runaway:
        _runaway(fig, tx, ty, sf)
    elif path_follow:
        _follow_path(fig, tx, ty, sf)
    elif glide_cfg(fig) is not None:
        _glide(fig, tx, ty, sf, offset)
    else:
        _chase(fig, tx, ty, sf, offset)

    fig.face(ox, oy)
    g = glide_cfg(fig)
    m.glide_alt = None
    if g is not None:
        anim = fig.combat.action_anim or ""
        if g["face_target_attacking"] and fig.aim is None and anim.startswith("attack"):
            # Skate-and-shoot: while an attack plays the glide carries on but
            # the fighter turns to the target, so both pistols fire forward.
            if tx - t.x < -0.001:
                t.facing_left = True
            elif tx - t.x > 0.001:
                t.facing_left = False
        # Skating backwards: speed along the facing below -BACK_ON px/tick
        # (released above -BACK_OFF, so it doesn't flicker).  An action with
        # backward_frames then shows those frames instead (Figure).
        along = m.glide_vx * (-1.0 if t.facing_left else 1.0)
        m.glide_back = along < (-GLIDE_BACK_OFF if m.glide_back else -GLIDE_BACK_ON)
        alt = g["backward_frames"].get(anim) if m.glide_back else None
        if alt:
            m.glide_alt = (anim, alt)
    anchor = _combat.sprite_emitter_trail_anchor(fig)
    if anchor is not None:
        ax, ay = anchor
        fig.trail.update(ax, ay, t.facing_left, fig.render.is_moving,
                          path_follow, apply_offset=False)
    else:
        fig.trail.update(t.x, t.y, t.facing_left, fig.render.is_moving,
                          path_follow)
    fig.render.advance()
    return cursor_hit


def _bounce(fig, sf=1.0):
    """One knockback tick.  Every launch is calibrated as v0 = dist * (1 -
    BOUNCE_FRICTION), so the travel sums to exactly `dist`.  The position
    speed scale slows the step to v * sf; the decay is slowed to match
    (friction 1 - (1 - BOUNCE_FRICTION) * sf), so the slide plays out slower
    but still covers the full set distance:
    sum(v0 * sf * g^k) = v0 * sf / ((1 - BOUNCE_FRICTION) * sf) = dist.
    At sf = 1 this is exactly the old per-tick BOUNCE_FRICTION decay."""
    m = fig.motion
    t = fig.transform
    t.x += m.bounce_vx * sf
    t.y += m.bounce_vy * sf
    decay = 1.0 - (1.0 - config.BOUNCE_FRICTION) * sf
    m.bounce_vx *= decay
    m.bounce_vy *= decay
    if m.bounce_vx * m.bounce_vx + m.bounce_vy * m.bounce_vy < config.BOUNCE_THRESH_SQ:
        m.bouncing = False
        m.bounce_vx = m.bounce_vy = 0.0
        m.bounce_ending = True
        m.bounce_end_ticks = config.BOUNCE_END_HOLD


def launch_knockback(fig, vx, vy, tick, heavy_ticks=0):
    """Start a knockback slide at (vx, vy), calibrated by the caller as
    dist * (1 - BOUNCE_FRICTION) so it travels the full set distance.  A new
    hit restarts the slide in its own direction even mid-slide or in the
    slide-stop hold.  The same hit can reach a fighter through two channels
    one tick apart (dash body contact, then the hit_pending delivery), so a
    slide launched on this or the previous tick is left alone.  A heavy
    launch (heavy_ticks > 0: the sword duel's final hit) can't be replaced
    by a weaker knockback for that many ticks while it slides — a stronger
    one still can.  Returns True when the slide was (re)started."""
    m = fig.motion
    if m.bouncing and tick - m.knock_tick <= 1:
        return False
    if (m.bouncing and tick < m.heavy_until
            and vx * vx + vy * vy <= m.bounce_vx * m.bounce_vx + m.bounce_vy * m.bounce_vy):
        return False
    m.heavy_until = tick + int(heavy_ticks) if heavy_ticks > 0 else -1000
    m.glide_vx = m.glide_vy = 0.0     # a knockback kills any glide momentum
    m.bounce_vx, m.bounce_vy = vx, vy
    m.bouncing = True
    m.bounce_ending = False
    m.knock_tick = tick
    return True


def carry_knockback(fig):
    """Advance a knockback slide for a fighter whose movement is owned
    elsewhere this tick (a melee attack in progress, or a stationary
    character): the slide is laid on top of that movement so the fighter
    still travels the full set distance.  An arc in progress is placed
    absolutely around its centre, so the centre slides with it."""
    m = fig.motion
    t = fig.transform
    if m.bouncing:
        ox, oy = t.x, t.y
        _bounce(fig, _combat.position_speed_scale(t.x, t.y, fig.screen_w, fig.screen_h))
        c = fig.combat
        if c.arc_repositioning:
            c.arc_center_x += t.x - ox
            c.arc_center_y += t.y - oy
    elif m.bounce_ending:
        _bounce_end(fig)


def _bounce_end(fig):
    m = fig.motion
    m.bounce_end_ticks -= 1
    if m.bounce_end_ticks <= 0:
        m.bounce_ending = False
        # Resume the run cycle from a recognisable frame (Picture11 == index 10).
        run = fig.render.bundle.run
        if run:
            fig.render.run_idx = min(10, len(run) - 1)


def _runaway(fig, cx, cy, sf=1.0):
    m = fig.motion
    t = fig.transform
    if m.path:
        m.path.clear()
    dx = t.x - cx
    dy = t.y - cy
    d_sq = dx * dx + dy * dy
    rad_sq = config.RUNAWAY_RADIUS * config.RUNAWAY_RADIUS
    if 0.01 < d_sq < rad_sq:
        inv = config.RUNAWAY_SPEED * sf / (d_sq ** 0.5)
        t.x += dx * inv
        t.y += dy * inv


def _follow_path(fig, cx, cy, sf=1.0):
    m = fig.motion
    path = m.path
    if not path:
        path.append((cx, cy))
    else:
        lx, ly = path[-1]
        if (cx - lx) ** 2 + (cy - ly) ** 2 >= config.PATH_MIN_D_SQ:
            path.append((cx, cy))
    # Walk along queued breadcrumbs by exactly follow_speed px this tick.
    budget = m.follow_speed * sf
    t = fig.transform
    while budget > 1e-6 and path:
        bx, by = path[0]
        dx = bx - t.x
        dy = by - t.y
        d = (dx * dx + dy * dy) ** 0.5
        if d <= budget:
            t.x, t.y = bx, by
            budget -= d
            path.popleft()
        else:
            inv = budget / d
            t.x += dx * inv
            t.y += dy * inv
            budget = 0.0


def _chase(fig, cx, cy, sf=1.0, offset=None):
    m = fig.motion
    t = fig.transform
    if m.path:
        m.path.clear()
    ox, oy = (m.offset_x, m.offset_y) if offset is None else offset
    dx = cx + ox - t.x
    dy = cy + oy - t.y
    d_sq = dx * dx + dy * dy
    step = m.speed * sf
    if d_sq > step * step:
        inv = step / (d_sq ** 0.5)
        t.x += dx * inv
        t.y += dy * inv
    else:
        t.x = cx + ox
        t.y = cy + oy


# Glide (JSON `movement.glide`, opt-in per character): instead of running to
# its chase point and stopping, the fighter skates.  Its velocity is carried
# from tick to tick and only steered toward where it wants to go (accel = the
# share of the gap closed per tick), so it drifts through wide turns; and it
# never parks — it works round its target at its chase distance (at least
# orbit_min_px), swapping which way round every swap_ms (random in the
# range).  weave_deg / weave_ms carve that line into S-curves (the heading
# swings weave_deg either side, one full S every weave_ms); range_wobble
# lets the distance breathe in and out by that share, so it flows into range
# and back out.  face_target_attacking: while an attack plays it faces the
# target whichever way it is skating.  backward_frames {action: frame set}:
# while skating backwards that action shows the set instead.  The target is
# the same point _chase uses (cursor in Solo, battle target in Battle), so
# Solo and Battle match.
GLIDE_DEFAULTS = dict(accel=0.08, orbit_min_px=60.0, swap_ms=[1500.0, 3500.0],
                      face_target_attacking=True, weave_deg=0.0, weave_ms=1600.0,
                      range_wobble=0.0, backward_frames={})
GLIDE_BACK_ON, GLIDE_BACK_OFF = 0.8, 0.3     # px/tick against the facing


def glide_cfg(fig):
    """Normalised movement.glide block of this figure's character, or None."""
    mode = fig.mode
    cached = getattr(mode, "_glide_cache", False)
    if cached is not False:
        return cached
    char = getattr(mode, "character", None) or {}
    raw = (char.get("movement") or {}).get("glide")
    cfg = None
    if isinstance(raw, dict) and raw.get("enabled", True):
        cfg = dict(GLIDE_DEFAULTS)
        try:
            cfg["accel"] = max(0.01, min(1.0, float(raw.get("accel", cfg["accel"]))))
        except (TypeError, ValueError):
            pass
        try:
            cfg["orbit_min_px"] = max(0.0, float(raw.get("orbit_min_px", cfg["orbit_min_px"])))
        except (TypeError, ValueError):
            pass
        sw = raw.get("swap_ms", cfg["swap_ms"])
        try:
            lo, hi = (float(sw[0]), float(sw[1])) if isinstance(sw, (list, tuple)) else (float(sw), float(sw))
            cfg["swap_ms"] = [max(0.0, min(lo, hi)), max(0.0, lo, hi)]
        except (TypeError, ValueError, IndexError):
            pass
        cfg["face_target_attacking"] = bool(raw.get("face_target_attacking", True))
        for k, lo, hi in (("weave_deg", 0.0, 89.0), ("weave_ms", 100.0, 60000.0),
                          ("range_wobble", 0.0, 0.9)):
            try:
                cfg[k] = max(lo, min(hi, float(raw.get(k, cfg[k]))))
            except (TypeError, ValueError):
                pass
        bf = raw.get("backward_frames")
        cfg["backward_frames"] = ({str(a): str(b) for a, b in bf.items() if a and b}
                                  if isinstance(bf, dict) else {})
    mode._glide_cache = cfg
    return cfg


def _glide(fig, cx, cy, sf=1.0, offset=None):
    m = fig.motion
    t = fig.transform
    g = glide_cfg(fig)
    if m.path:
        m.path.clear()
    if m.glide_swap_ticks <= 0:
        lo, hi = g["swap_ms"]
        m.glide_swap_ticks = max(1, int(fig.personality.rng.uniform(lo, hi) / config.TICK_MS))
        if hi > 0:
            m.glide_dir = -m.glide_dir
    else:
        m.glide_swap_ticks -= 1
    m.glide_t += 1
    ox, oy = (m.offset_x, m.offset_y) if offset is None else offset
    ring = max(g["orbit_min_px"] * fig.mode.body_scale(), (ox * ox + oy * oy) ** 0.5)
    period = g["weave_ms"] / config.TICK_MS
    if g["range_wobble"] > 0.0:
        # the distance breathes on a slower beat than the weave
        ring *= 1.0 + g["range_wobble"] * math.sin(2 * math.pi * m.glide_t / (period * 2.7))
    dx, dy = t.x - cx, t.y - cy
    d = (dx * dx + dy * dy) ** 0.5
    if d < 1e-3:
        dx, dy, d = (-1.0 if t.facing_left else 1.0), 0.0, 1.0
    ux, uy = dx / d, dy / d                      # outward from the target
    # Round the ring (tangent), bent in / out by how far off the ring it is:
    # far away it heads almost straight in, on the ring it skates round.
    pull = max(-3.0, min(3.0, (ring - d) / max(1.0, ring * 0.35)))
    vx = -uy * m.glide_dir + ux * pull
    vy = ux * m.glide_dir + uy * pull
    if g["weave_deg"] > 0.0:
        # carve: swing the heading either side of the line -> S-curves
        w = math.radians(g["weave_deg"]) * math.sin(2 * math.pi * m.glide_t / period)
        cw, sw = math.cos(w), math.sin(w)
        vx, vy = vx * cw - vy * sw, vx * sw + vy * cw
    vn = (vx * vx + vy * vy) ** 0.5
    step = m.speed * sf
    vx, vy = vx / vn * step, vy / vn * step
    a = g["accel"]
    m.glide_vx += (vx - m.glide_vx) * a
    m.glide_vy += (vy - m.glide_vy) * a
    nx, ny = t.x + m.glide_vx, t.y + m.glide_vy
    # Skating into a screen edge turns the circle round and drops the speed
    # into the wall, rather than grinding along it.
    margin = 10
    hit = False
    if not (margin <= nx <= fig.screen_w - margin):
        m.glide_vx = -m.glide_vx * 0.5
        hit = True
    if not (margin <= ny <= fig.screen_h - margin):
        m.glide_vy = -m.glide_vy * 0.5
        hit = True
    if hit:
        m.glide_dir = -m.glide_dir
    t.x += m.glide_vx
    t.y += m.glide_vy


def apply_arena_oval(fig, world):
    """Battle-mode-only invisible oval arena boundary.

    Confirmed as a deliberate Solo/Battle exception: Solo has no arena wall
    (only the rectangular check_walls() screen clamp below applies), Battle
    additionally confines both fighters to an oval so the fight stays inside
    a bounded ring. Center/radii are fractions of the figure's own
    screen_w/screen_h, so the oval scales with window size and is identical
    for both fielded fighters (same world, same screen dims).

    Behaviour: a gentle gradient push-back starts at
    config.ARENA_OVAL_GRADIENT_START (normalized ellipse distance, 0..1) and
    grows stronger approaching the edge; a hard clamp exactly onto the
    boundary guarantees the fighter can never actually cross it, however
    fast it was moving. Fully invisible — no rendering, pure position math.
    """
    t = fig.transform
    cx = fig.screen_w * config.ARENA_OVAL_CENTER_X_FRAC
    cy = fig.screen_h * config.ARENA_OVAL_CENTER_Y_FRAC
    rx = fig.screen_w * config.ARENA_OVAL_RADIUS_X_FRAC
    ry = fig.screen_h * config.ARENA_OVAL_RADIUS_Y_FRAC
    if rx <= 0.0 or ry <= 0.0:
        return

    dx = t.x - cx
    dy = t.y - cy
    nx = dx / rx
    ny = dy / ry
    d = (nx * nx + ny * ny) ** 0.5
    if d <= config.ARENA_OVAL_GRADIENT_START:
        return

    if d >= 1.0:
        # Past the boundary (or landed exactly on it) — clamp back onto the
        # ellipse edge along the same radial direction from center.
        scale = 1.0 / d
        t.x = cx + dx * scale
        t.y = cy + dy * scale
        return

    # Gentle gradient zone: push strength ramps from 0 (at GRADIENT_START)
    # to full strength (at the edge, d == 1.0), eased with a square curve so
    # it's soft at first and firm right at the edge.
    span = 1.0 - config.ARENA_OVAL_GRADIENT_START
    push_t = (d - config.ARENA_OVAL_GRADIENT_START) / span
    strength = push_t * push_t * config.ARENA_OVAL_PUSHBACK_STRENGTH
    inv = strength / (d * max(rx, ry))
    t.x -= dx * inv
    t.y -= dy * inv


def check_walls(fig, margin=10):
    """Clamp inside the screen; reflect bounce velocity off edges in flight."""
    m = fig.motion
    t = fig.transform
    t.x = max(margin, min(fig.screen_w - margin, t.x))
    t.y = max(margin, min(fig.screen_h - margin, t.y))
    if m.bouncing or m.bounce_ending:
        if t.x <= margin and m.bounce_vx < 0:
            m.bounce_vx = abs(m.bounce_vx)
        elif t.x >= fig.screen_w - margin and m.bounce_vx > 0:
            m.bounce_vx = -abs(m.bounce_vx)
        if t.y <= margin and m.bounce_vy < 0:
            m.bounce_vy = abs(m.bounce_vy)
        elif t.y >= fig.screen_h - margin and m.bounce_vy > 0:
            m.bounce_vy = -abs(m.bounce_vy)

