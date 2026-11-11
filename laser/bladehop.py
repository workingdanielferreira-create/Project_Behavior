"""
Blade hop (Daniel 2026-11-11): blades a fighter can teleport to, and the
chain that throws them.  Solo and Battle run the same code (Solo's target is
the cursor; thrown blades only deal damage in Battle, like every FX).

Hop beacons.  A blade FX (sprite shape "blade") with params.hop on is a hop
beacon of the fighter whose FX player holds it (laser/fxkit.py: its flight -
spread at launch, hang / plant / fly once past the target, laser trail - is
_hop_flight_step).  A beacon is "field" while it is not one the chain threw
and it is planted in the ground or standing still (e.g. Sword Graveyard's
planted swords), "thrown" once it has launched.  A blade lodged in an
opponent, used up by the chain, or ended is no beacon.

Picks (Blink landing "blade", the chain's landing): newest = the most
recently launched beacon; behind = the beacon on the far side of the target
from the fighter, nearest the target (none there: the nearest to the
target); nearest = the beacon nearest the fighter.

Arrival (hop_arrive of the blade landed on): catch = it vanishes into the
hand (a glint), stay = it stays a beacon, shatter = it bursts into shards.

The Blade hop chain (action_settings[action].hop, fxkit.HOP_DEFAULTS): while
the action plays it throws every field beacon (max_throws, 0 = all), one by
one: pick a field blade (field_pick), take it by `source` - recall (it rips
out and streaks to the hand, then is thrown), ground (it launches straight
from where it stands), blink (the fighter blinks onto it, pulls it out and
throws it) or mix (a seeded pick of the three per throw) - throw it at the
target (speed, damage, knockback, Pierce, spread_deg, laser trail, flare,
after / past_px / hold_ms / arrive), wait for blink_on (passes = it went
past the target, stops = it hung or planted, delay = delay_ms after the
throw), blink (gone gone_ms) and land on land_pick, then wait the gap before
the next throw: gap_start_ms for the first, accelerating to gap_end_ms for
the last.  The action's animation loops while the chain runs; when every
field blade is thrown the action ends and `finisher` (an action name, "" =
none) plays.
"""

import math

from . import config

TICK_MS = config.TICK_MS

PICKS = ("newest", "behind", "nearest")
SOURCES = ("mix", "recall", "ground", "blink")
FIELD_PICKS = ("nearest", "farthest", "random")
BLINK_ONS = ("passes", "stops", "delay")
ARRIVALS = ("catch", "stay", "shatter")

RECALL_SPEED_K = 1.4     # a recalled blade streaks to the hand this much faster than its throw
RECALL_CATCH_PX = 16.0   # ... and is thrown once this close (x figure size)
RECALL_MAX_TICKS = 30    # ... or after this long whatever
WAIT_MAX_TICKS = 90      # longest wait for blink_on before blinking anyway
WINDUP_K = 0.25          # blink source: pause between landing on the blade and throwing it (x the gap)
GAP_CURVE = 0.6          # how the gap eases from gap_start_ms to gap_end_ms (< 1 = speeds up early)
MOVING2 = 0.25           # px/tick squared: faster than this = moving


def _ticks(ms):
    return max(1, int(round(float(ms or 0) / TICK_MS)))


# ---------------------------------------------------------------- beacons
def _players(fig):
    drv = getattr(fig, "fx", None)
    if drv is None:
        return []
    return [drv.player, drv.clane[0]] + [ln[0] for ln in drv.rlanes] + drv.stack_players()


def _moving(inst):
    return inst.vx * inst.vx + inst.vy * inst.vy > MOVING2


def is_beacon(inst):
    fx = inst.fx
    P = fx["params"]
    if fx["prim"] != "sprite" or P.get("shape") != "blade" or not P.get("hop"):
        return False
    if inst.dead or inst.age >= inst.life or inst.hop_used:
        return False
    return inst.lodge is None or bool(inst.lodge.get("g"))   # lodged in an opponent: no beacon


def planted(inst):
    return inst.lodge is not None and bool(inst.lodge.get("g"))


def is_field(inst):
    """Field beacon: not thrown by the chain, and planted or standing still
    (fully appeared)."""
    from . import fxkit
    if inst.hop_th or inst.hop_rc:
        return False
    if planted(inst):
        return True
    return not _moving(inst) and fxkit.blade_spawn_u(inst) >= 1.0


def beacons(fig):
    return [i for pl in _players(fig) for i in pl.insts if is_beacon(i)]


def spot(inst):
    """Where a fighter lands on this blade: a planted blade's foot (where it
    enters the ground, lifted by the blade's plant_px so the fighter stands
    on the ground beside it), else the middle of the blade."""
    from . import fxkit
    P, ps = inst.fx["params"], inst.ps or 1.0
    if planted(inst):
        lg = inst.lodge
        ex, ey = inst.x - math.cos(lg["a"]) * lg["depth"], inst.y - math.sin(lg["a"]) * lg["depth"]
        return ex, ey - float(P.get("plant_px") or 0) * ps
    bx, by, a = fxkit.blade_pose(inst, ps)
    h = fxkit.blade_length(P, ps) / 2.0
    return bx - math.cos(a) * h, by - math.sin(a) * h


def _target(fig, world):
    from . import retreat
    tx, ty, _f = retreat._target(world, fig)
    return tx, ty


def pick(fig, world, mode, pool=None):
    """The beacon a blink lands on (mode: newest / behind / nearest)."""
    bs = beacons(fig) if pool is None else pool
    if not bs:
        return None
    if mode == "newest":
        flown = [b for b in bs if b.hop_l]
        return max(flown, key=lambda b: b.hop_lt) if flown else max(bs, key=lambda b: b.age * -1)
    tx, ty = _target(fig, world)
    if mode == "behind":
        lx, ly = tx - fig.x, ty - fig.y
        back = []
        for b in bs:
            sx, sy = spot(b)
            if (sx - tx) * lx + (sy - ty) * ly > 0:
                back.append(b)
        bs2 = back or bs
        return min(bs2, key=lambda b: (spot(b)[0] - tx) ** 2 + (spot(b)[1] - ty) ** 2)
    return min(bs, key=lambda b: (spot(b)[0] - fig.x) ** 2 + (spot(b)[1] - fig.y) ** 2)


def count(fig, which="field"):
    bs = beacons(fig)
    if which == "field":
        return sum(1 for b in bs if is_field(b))
    if which == "thrown":
        return sum(1 for b in bs if b.hop_l and not is_field(b))
    return len(bs)


def near(fig, px):
    r2 = (float(px) * fig.mode.body_scale()) ** 2
    for b in beacons(fig):
        sx, sy = spot(b)
        if (sx - fig.x) ** 2 + (sy - fig.y) ** 2 <= r2:
            return True
    return False


def arrive(fig, world, inst, mode=None):
    """Its fighter landed on blade `inst`: catch / stay / shatter."""
    if inst is None:
        return
    mode = mode or inst.fx["params"].get("hop_arrive") or "catch"
    if mode == "stay":
        return
    sx, sy = spot(inst)
    inst.age = max(inst.age, inst.life)
    inst.lt = []
    if mode == "shatter":
        _shards(fig, inst, sx, sy)
    else:
        fig.combat.blink_fx_pending.append((sx, sy, sx, sy))   # the glint as it is caught


def consume(fig, inst):
    """The chain takes field blade `inst` (it becomes the thrown one)."""
    inst.hop_used = True
    inst.age = max(inst.age, inst.life)


def _shards(fig, inst, x, y):
    from . import fxkit
    drv = getattr(fig, "fx", None)
    if drv is None or drv.host is None:
        return
    fx = fxkit.normalize({"prim": "particles", "name": "Hop shatter", "tag": "blade", "anchor": "figure",
                          "life_ticks": 1, "blend": "additive", "motion": {"kind": "static"},
                          "color": {"mode": "gradient", "c1": "#ffffff", "c2": inst.fx["color"].get("c1") or "#9fb6ff"},
                          "params": {"mode": "burst", "count": 22, "angle_deg": -90, "spread_deg": 360, "speed_min": 80,
                                     "speed_max": 300, "gravity": 160, "drag": 0.92, "size_min": 1, "size_max": 2.4,
                                     "size_over_life": "shrink", "life_min_ms": 200, "life_max_ms": 520}})
    p = fxkit.spawn(fx, drv.host, 1, (inst.seed ^ 0x5bd1e995) & 0xFFFFFFFF, 0, 1, None)
    p.src = fx
    ax, ay = p.x, p.y
    for q in p.parts:
        q["x"] += x - ax
        q["y"] += y - ay
    p.x, p.y = x, y
    drv.player.insts.append(p)


# ---------------------------------------------------------------- the chain
class Chain:
    __slots__ = ("play", "n", "k", "phase", "t", "cur", "fb", "mode", "gap", "done", "seed")

    def __init__(self, play, n, seed):
        self.play = play
        self.n = n            # field blades it will throw
        self.k = 0            # throws done
        self.phase = "throw"
        self.t = 0            # ticks in this phase
        self.cur = None       # the blade in flight
        self.fb = None        # the field blade being taken
        self.mode = None      # this throw's source
        self.gap = 0
        self.done = n <= 0
        self.seed = seed


def config_for(fig, action):
    from . import fxkit
    cfx = fxkit.character_fx(fig.mode)
    if cfx is None or not action:
        return None
    h = (cfx.settings.get(action) or {}).get("hop")
    return h if isinstance(h, dict) and h.get("enabled") else None


def _state(fig):
    from . import blink
    st = fig.blink
    if st is None:
        st = blink.BlinkState()
        fig.blink = st
    return st


def holding(fig, action):
    """True while the Blade hop chain of `action` still runs (its
    animation loops instead of ending)."""
    st = fig.blink
    ch = st.chain if st is not None else None
    if ch is None or ch.done or config_for(fig, action) is None:
        return False
    from . import blink
    return ch.play == blink._play_key(fig, action)


def _gap_ticks(cfg, k, n):
    a, b = float(cfg.get("gap_start_ms") or 0), float(cfg.get("gap_end_ms") or 0)
    u = 0.0 if n <= 1 else min(1.0, k / float(n - 1)) ** GAP_CURVE
    return _ticks(a + (b - a) * u)


def _field_blade(fig, world, cfg, rnd):
    fl = [b for b in beacons(fig) if is_field(b)]
    if not fl:
        return None
    how = cfg.get("field_pick") or "nearest"
    if how == "random":
        return fl[int(rnd * len(fl)) % len(fl)]
    key = lambda b: (spot(b)[0] - fig.x) ** 2 + (spot(b)[1] - fig.y) ** 2
    return max(fl, key=key) if how == "farthest" else min(fl, key=key)


def _rand(ch, salt):
    """Seeded 0..1 for this chain (mulberry32 of seed + salt)."""
    a = (ch.seed + salt * 0x6D2B79F5) & 0xFFFFFFFF
    t = a
    t = ((t ^ (t >> 15)) * (t | 1)) & 0xFFFFFFFF
    t ^= (t + (((t ^ (t >> 7)) * (t | 61)) & 0xFFFFFFFF)) & 0xFFFFFFFF
    return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0


def _throw_fx(cfg, src):
    from . import fxkit
    P = dict(src.fx["params"])
    P.update(spawn_style="none", fade=False, trail_len=0, flare=True, blade_orient="motion", lodge_ms=0,
             hop=True, hop_spread_deg=float(cfg.get("spread_deg") or 0), hop_after=cfg.get("after") or "hang",
             hop_past_px=float(cfg.get("past_px") or 0), hop_hold_ms=float(cfg.get("hold_ms") or 0),
             hop_arrive=cfg.get("arrive") or "catch", laser_trail=float(cfg.get("laser_trail") or 0),
             plant_on="off")
    return fxkit.normalize({"prim": "sprite", "name": "Hop throw", "tag": "blade", "anchor": "figure",
                            "blend": "additive", "color": dict(src.fx["color"]), "life_ticks": fxkit.LAUNCH_LIFE,
                            "motion": {"kind": "travel", "aim": "target", "speed": float(cfg.get("speed") or 20)},
                            "battle": {"deals_damage": True, "damage": float(cfg.get("damage") or 0), "pierce": True,
                                       "rehit_ticks": 0, "knockback": float(cfg.get("knockback") or 0)},
                            "params": P})


def _hand(fig, host):
    p = host.anchor("wtip")
    return float(p[0]), float(p[1])


def _spawn_throw(fig, cfg, ch, src, x, y, recall):
    """The thrown blade, at (x, y): launched at the target, or (recall)
    streaking to the hand first."""
    from . import fxkit
    drv = fig.fx
    host = drv.host
    fx = _throw_fx(cfg, src)
    inst = fxkit.spawn(fx, host, 1, (ch.seed + 7919 * (ch.k + 1)) & 0xFFFFFFFF, 0, 1, None)
    inst.src = fx
    inst.x = inst.px = x
    inst.y = inst.py = y
    inst.hop_th = True
    inst.hop_rc = bool(recall)
    if recall:
        hx, hy = _hand(fig, host)
        _aim(inst, hx, hy, inst.spd * RECALL_SPEED_K)
    else:
        _aim(inst, host.target[0], host.target[1], inst.spd)
    drv.player.insts.append(inst)
    return inst


def _aim(inst, tx, ty, spd):
    dx, dy = tx - inst.x, ty - inst.y
    d = math.hypot(dx, dy)
    if d < 1e-6:
        dx, dy, d = 1.0, 0.0, 1.0
    v = spd * (inst.ps or 1.0)
    inst.vx, inst.vy = dx / d * v, dy / d * v
    inst.dir = [dx / d, dy / d]


def _start_throw(fig, world, cfg, ch):
    fb = _field_blade(fig, world, cfg, _rand(ch, 3 * ch.k + 1))
    if fb is None:
        ch.done = True
        return
    mode = cfg.get("source") or "mix"
    if mode == "mix":
        mode = ("recall", "ground", "blink")[int(_rand(ch, 3 * ch.k + 2) * 3) % 3]
    ch.fb, ch.mode, ch.t = fb, mode, 0
    if mode == "blink":
        from . import blink
        blink.hop_vanish(fig, world, ch_action(fig))
        ch.phase = "fetch"
        return
    sx, sy = spot(fb) if planted(fb) else (fb.x, fb.y)
    if planted(fb):   # rips out of the ground from its visible tip end
        lg = fb.lodge
        sx, sy = fb.x - math.cos(lg["a"]) * lg["depth"], fb.y - math.sin(lg["a"]) * lg["depth"]
    consume(fig, fb)
    ch.cur = _spawn_throw(fig, cfg, ch, fb, sx, sy, recall=(mode == "recall"))
    ch.phase = "wait"


def ch_action(fig):
    r = getattr(fig, "act", None)
    return r.playing if r is not None else None


def _wait_done(cfg, ch):
    cur = ch.cur
    if cur is None or cur.dead or cur.age >= cur.life or ch.t >= WAIT_MAX_TICKS:
        return True
    if cur.hop_rc:
        return False
    on = cfg.get("blink_on") or "passes"
    if on == "stops":
        return cur.hop_stopped or planted(cur)
    if on == "delay":
        return ch.t >= _ticks(cfg.get("delay_ms"))
    return cur.hop_passed


def _land(fig, world, cfg, ch):
    from . import blink
    how = cfg.get("land_pick") or "newest"
    cur = ch.cur if ch.cur is not None and is_beacon(ch.cur) else None
    b = cur if how == "newest" and cur is not None else pick(fig, world, how)
    if b is None:
        tx, ty = _target(fig, world)
        blink.hop_reappear(fig, world, tx - 60.0 * (1 if fig.x < tx else -1), ty)
        return
    x, y = spot(b)
    blink.hop_reappear(fig, world, x, y)
    arrive(fig, world, b, cfg.get("arrive") if b is cur else None)


def step(fig, world, action, now):
    """One tick of `action`'s Blade hop chain (from ActionRunner.update,
    before the FX update).  Returns True once the chain has just finished
    (the runner then ends the action and plays the finisher)."""
    from . import blink
    cfg = config_for(fig, action)
    if cfg is None or getattr(fig, "fx", None) is None or fig.fx.host is None:
        return False
    st = _state(fig)
    key = blink._play_key(fig, action)
    ch = st.chain
    if ch is None or ch.play != key:
        n = count(fig, "field")
        mx = int(cfg.get("max_throws") or 0)
        if mx > 0:
            n = min(n, mx)
        seed = (int(now) * 2654435761 + fig.index * 40503) & 0xFFFFFFFF
        ch = st.chain = Chain(key, n, seed)
        if ch.done:
            return False
    if ch.done:
        return False
    ch.t += 1
    if ch.phase == "pause":
        if ch.t >= ch.gap:
            ch.phase, ch.t = "throw", 0
    if ch.phase == "throw":
        if ch.k >= ch.n:
            ch.done = True
        else:
            _start_throw(fig, world, cfg, ch)
        if ch.done:
            return True
    elif ch.phase == "fetch":   # blink source: gone, then onto the field blade
        if ch.t >= _ticks(cfg.get("gone_ms")):
            fb = ch.fb
            if fb is None or not is_beacon(fb):
                blink.hop_reappear(fig, world, fig.x, fig.y)
                ch.phase, ch.t = "throw", 0
                return False
            x, y = spot(fb)
            blink.hop_reappear(fig, world, x, y)
            consume(fig, fb)
            fig.combat.blink_fx_pending.append((x, y, x, y))
            ch.phase, ch.t = "windup", 0
            ch.gap = max(1, int(round(_gap_ticks(cfg, ch.k, ch.n) * WINDUP_K)))
    elif ch.phase == "windup":
        if ch.t >= ch.gap:
            hx, hy = _hand(fig, fig.fx.host)
            ch.cur = _spawn_throw(fig, cfg, ch, ch.fb, hx, hy, recall=False)
            ch.phase, ch.t = "wait", 0
    elif ch.phase == "wait":
        cur = ch.cur
        if cur is not None and cur.hop_rc and not cur.dead:   # recalled: steer to the hand, then throw
            hx, hy = _hand(fig, fig.fx.host)
            if (math.hypot(hx - cur.x, hy - cur.y) <= RECALL_CATCH_PX * (cur.ps or 1.0)
                    or ch.t >= RECALL_MAX_TICKS):
                cur.hop_rc = False
                cur.lt = []
                tgt = fig.fx.host.target
                _aim(cur, tgt[0], tgt[1], cur.spd)
                ch.t = 0
            else:
                _aim(cur, hx, hy, cur.spd * RECALL_SPEED_K)
        elif _wait_done(cfg, ch):
            blink.hop_vanish(fig, world, action)
            ch.phase, ch.t = "gone", 0
    elif ch.phase == "gone":
        if ch.t >= _ticks(cfg.get("gone_ms")):
            _land(fig, world, cfg, ch)
            ch.k += 1
            ch.cur = ch.fb = None
            if ch.k >= ch.n or count(fig, "field") == 0:
                ch.done = True
                return True
            ch.gap = _gap_ticks(cfg, ch.k, ch.n)
            ch.phase, ch.t = "pause", 0
    return False


def abandon(fig, world):
    """The chain's action was cut off: bring the fighter back if it is gone."""
    st = fig.blink
    if st is None or st.chain is None:
        return
    from . import blink
    if st.gone and st.ext:
        blink.hop_reappear(fig, world, fig.x, fig.y)
    st.chain = None
