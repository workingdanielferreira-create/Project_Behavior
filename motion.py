"""
Motion — non-combat movement strategies for a Figure.

`update` runs the chase / path-follow / runaway / cursor-bounce state machine,
then updates facing, trail, and animation.  Combat movement (dash/dodge/slash)
is handled separately by the combat system, which short-circuits before this
runs when a figure is mid-attack.
"""

from . import config


def update(fig, tx, ty, collision_on, path_follow, runaway):
    """Advance one figure's position toward (tx, ty) for this tick."""
    m = fig.motion
    t = fig.transform

    # Toggling follow mode clears the persistent path trail.
    if path_follow != m.follow:
        fig.trail.clear()
    m.follow = path_follow
    m.runaway = runaway

    # Cursor-collision bounce trigger.
    if collision_on and not m.bouncing and not m.bounce_ending:
        dx = tx - t.x
        dy = ty - t.y
        d_sq = dx * dx + dy * dy
        if 0 < d_sq < config.HIT_RADIUS_SQ:
            inv = config.BOUNCE_STRENGTH / (d_sq ** 0.5)
            m.bounce_vx = -dx * inv
            m.bounce_vy = -dy * inv
            m.bouncing = True

    ox, oy = t.x, t.y

    if m.bouncing:
        _bounce(fig)
    elif m.bounce_ending:
        _bounce_end(fig)
    elif not t.init:
        t.x, t.y = tx, ty
        t.init = True
        m.path.clear()
    elif runaway:
        _runaway(fig, tx, ty)
    elif path_follow:
        _follow_path(fig, tx, ty)
    else:
        _chase(fig, tx, ty)

    fig.face(ox, oy)
    fig.trail.update(t.x, t.y, t.facing_left, fig.render.is_moving, path_follow)
    fig.render.advance()


def _bounce(fig):
    m = fig.motion
    t = fig.transform
    t.x += m.bounce_vx
    t.y += m.bounce_vy
    m.bounce_vx *= config.BOUNCE_FRICTION
    m.bounce_vy *= config.BOUNCE_FRICTION
    if m.bounce_vx * m.bounce_vx + m.bounce_vy * m.bounce_vy < config.BOUNCE_THRESH_SQ:
        m.bouncing = False
        m.bounce_vx = m.bounce_vy = 0.0
        m.bounce_ending = True
        m.bounce_end_ticks = config.BOUNCE_END_HOLD


def _bounce_end(fig):
    m = fig.motion
    m.bounce_end_ticks -= 1
    if m.bounce_end_ticks <= 0:
        m.bounce_ending = False
        # Resume the run cycle from a recognisable frame (Picture11 == index 10).
        run = fig.render.bundle.run
        if run:
            fig.render.run_idx = min(10, len(run) - 1)


def _runaway(fig, cx, cy):
    m = fig.motion
    t = fig.transform
    if m.path:
        m.path.clear()
    dx = t.x - cx
    dy = t.y - cy
    d_sq = dx * dx + dy * dy
    rad_sq = config.RUNAWAY_RADIUS * config.RUNAWAY_RADIUS
    if 0.01 < d_sq < rad_sq:
        inv = config.RUNAWAY_SPEED / (d_sq ** 0.5)
        t.x += dx * inv
        t.y += dy * inv


def _follow_path(fig, cx, cy):
    m = fig.motion
    path = m.path
    if not path:
        path.append((cx, cy))
    else:
        lx, ly = path[-1]
        if (cx - lx) ** 2 + (cy - ly) ** 2 >= config.PATH_MIN_D_SQ:
            path.append((cx, cy))
    # Walk along queued breadcrumbs by exactly follow_speed px this tick.
    budget = m.follow_speed
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


def _chase(fig, cx, cy):
    m = fig.motion
    t = fig.transform
    if m.path:
        m.path.clear()
    dx = cx + m.offset_x - t.x
    dy = cy + m.offset_y - t.y
    d_sq = dx * dx + dy * dy
    if d_sq > m.speed * m.speed:
        inv = m.speed / (d_sq ** 0.5)
        t.x += dx * inv
        t.y += dy * inv
    else:
        t.x = cx + m.offset_x
        t.y = cy + m.offset_y


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
