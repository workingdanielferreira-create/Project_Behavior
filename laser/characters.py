"""
Character loader — imports Character Creator `pb_character` JSON files at
startup and turns them into fully playable figure types.

Pipeline (runs once inside AssetLibrary._load_all, after Qt is up):
  1. Scan `<launcher>/characters/*.json` for files with format == "pb_character".
  2. A Python port of the FX Creator rig maths (tools/fx/rig.js `joints()`)
     rasterises every keyframe of the baseline actions into transparent
     QPixmaps — keyframes only, no interpolation, so the animation plays the
     exact authored poses (snappy).
  3. The frames are packed into a FrameBundle:
        run            -> run frames
        idle           -> idle frames
        attack_normal  -> slash frames
        defend kf 0/1  -> slide / slide2
  4. A FigureMode subclass, MODE_CONFIGS entry, MODE_ORDER key, and a palette
     LUT (built from the character's body/accent colours) are registered, so
     every system — Solo AND Battle, which all route through the mode
     predicates — treats the character exactly like a built-in figure.

Archetype: v2 files carry an explicit ``"archetype"`` ("shooter" | "melee" |
"New") mapped directly to the four mode predicates; "New" reads a
``"predicates"`` block (custom mix of can_shoot / uses_melee / retreats /
charges_full).  v1 files (no archetype key) fall back to inference from the
weapon polyline: empty polyline => shooter (can_shoot + retreats), drawn
weapon => melee (uses_melee + charges_full).

Movement: ``"movement": {"wander_strength": 0..1}`` overrides wander_blend()
on the generated mode class as ``min(ws, dist/300) * strength`` (swordsman
charge ≈ 0.15, runner weave ≈ 1.0).  A thumbnail
``characters/<key>_thumb.png`` (idle keyframe 0) is written on first load if
missing.

Battle properties from the JSON (`damage`, `pierce`, `explode`, ...) and the
raw fx_layers are kept on the mode instance (`mode.character`) for combat/VFX
integration.  Runtime FX are played live by the game's existing VFX engine
(trail component, projectiles, beam ultimate, muzzle flashes, crescents),
coloured through the character's palette LUT — identical in Solo and Battle.
"""

import glob
import json
import math
import os

from PyQt5.QtCore import Qt, QPointF
from PyQt5.QtGui import QPixmap, QPainter, QPen, QColor, QTransform

from . import config, modes, palette

_D = math.pi / 180.0

# Default pose (rig.js `Z`) — merged under every keyframe pose defensively.
_ZERO_POSE = dict(rx=0, ry=0, sp=0, sp2=0, hd=0, lsht=0, rsht=0, lpvt=0,
                  rpvt=0, lua=15, lfa=5, rua=-15, rfa=-5, lth=8, lsh=5,
                  rth=-8, rsh=-5, wp=-45, luas=1, lfas=1, ruas=1, rfas=1,
                  lths=1, lshs=1, rths=1, rshs=1)

_DEFAULT_BONES = dict(ua=22, fa=20, th=26, sh=24, torso=36)

# Native rig head diameter (radius 10 in rig.js) — used to normalise the
# character to the same on-screen size as the sprite figures.
_RIG_HEAD_DIAMETER = 20.0

_BODY_SEGMENTS = [
    ("hip", "torso_mid"), ("torso_mid", "chest"),
    ("chest", "l_shoulder"), ("chest", "r_shoulder"),
    ("hip", "l_hip"), ("hip", "r_hip"),
    ("l_shoulder", "l_elbow"), ("l_elbow", "l_hand"),
    ("r_shoulder", "r_elbow"), ("r_elbow", "r_hand"),
    ("l_hip", "l_knee"), ("l_knee", "l_foot"),
    ("r_hip", "r_knee"), ("r_knee", "r_foot"),
]


# ---------------------------------------------------------------------------
# Rig maths — faithful port of tools/fx/rig.js `joints()` (y-down, like Qt)
# ---------------------------------------------------------------------------
def _bone_end(origin, angle, length):
    return (origin[0] + math.cos(angle) * length,
            origin[1] + math.sin(angle) * length)


def rig_joints(pose, bones, weapon_points):
    """World joint positions for a pose, with the root (before rx/ry) at (0,0)."""
    p = dict(_ZERO_POSE)
    p.update(pose)
    B = _bone_end
    BL = bones
    J = {}
    hip = (p["rx"], p["ry"])
    J["hip"] = hip

    sp_w = (-90 + p["sp"]) * _D
    J["torso_mid"] = B(hip, sp_w, BL["torso"] / 2.0)
    sp_w2 = sp_w + p.get("sp2", 0) * _D
    J["chest"] = B(J["torso_mid"], sp_w2, BL["torso"] / 2.0)
    hd_w = sp_w2 + p["hd"] * _D
    J["head"] = B(J["chest"], hd_w, 16)

    J["r_shoulder"] = B(J["chest"], sp_w2 + math.pi / 2 + p["rsht"] * _D, 11)
    J["l_shoulder"] = B(J["chest"], sp_w2 - math.pi / 2 + p["lsht"] * _D, 11)
    J["r_hip"] = B(hip, p["rpvt"] * _D, 8)
    J["l_hip"] = B(hip, math.pi + p["lpvt"] * _D, 8)

    arm_base = sp_w2 + math.pi
    lua_w = arm_base + p["lua"] * _D
    J["l_elbow"] = B(J["l_shoulder"], lua_w, BL["ua"] * p.get("luas", 1))
    lfa_w = lua_w + p["lfa"] * _D
    J["l_hand"] = B(J["l_elbow"], lfa_w, BL["fa"] * p.get("lfas", 1))
    rua_w = arm_base + p["rua"] * _D
    J["r_elbow"] = B(J["r_shoulder"], rua_w, BL["ua"] * p.get("ruas", 1))
    rfa_w = rua_w + p["rfa"] * _D
    J["r_hand"] = B(J["r_elbow"], rfa_w, BL["fa"] * p.get("rfas", 1))

    lth_w = (90 + p["lth"]) * _D
    J["l_knee"] = B(J["l_hip"], lth_w, BL["th"] * p.get("lths", 1))
    J["l_foot"] = B(J["l_knee"], lth_w + p["lsh"] * _D, BL["sh"] * p.get("lshs", 1))
    rth_w = (90 + p["rth"]) * _D
    J["r_knee"] = B(J["r_hip"], rth_w, BL["th"] * p.get("rths", 1))
    J["r_foot"] = B(J["r_knee"], rth_w + p["rsh"] * _D, BL["sh"] * p.get("rshs", 1))

    # Custom weapon polyline — points are local to r_hand, rotated by wW
    # (rig.js wpnWorld).  Empty polyline => no weapon geometry.
    w_w = rfa_w + p["wp"] * _D
    pts = []
    if weapon_points:
        c, s = math.cos(w_w), math.sin(w_w)
        hx, hy = J["r_hand"]
        pts = [(hx + wx * c - wy * s, hy + wx * s + wy * c)
               for wx, wy in weapon_points]
    J["_weapon_pts"] = pts
    return J


# ---------------------------------------------------------------------------
# Rasterisation
# ---------------------------------------------------------------------------
def _pose_extent(J):
    """Max |x|, |y| this pose reaches, including head circle and weapon."""
    max_x = max_y = 0.0
    for k, v in J.items():
        if k.startswith("_"):
            continue
        max_x = max(max_x, abs(v[0]))
        max_y = max(max_y, abs(v[1]))
    hx, hy = J["head"]
    max_x = max(max_x, abs(hx) + 10)
    max_y = max(max_y, abs(hy - 4) + 10)
    for wx, wy in J["_weapon_pts"]:
        max_x = max(max_x, abs(wx))
        max_y = max(max_y, abs(wy))
    return max_x, max_y


def _pose_max_joint_dist(J):
    """Max joint distance from the root (0,0) — the raw (unscaled) hurtbox
    extent of one pose.  Excludes the weapon so hurtbox tracks the body."""
    best = 0.0
    for k, v in J.items():
        if k.startswith("_"):
            continue
        best = max(best, math.hypot(v[0], v[1]))
    return best


def _char_scale(char):
    """Clamped stats.scale (0.5-2.0), defaulting to 1.0."""
    stats = char.get("stats", {}) or {}
    try:
        s = float(stats.get("scale", 1.0))
    except (TypeError, ValueError):
        s = 1.0
    return max(0.5, min(2.0, s))


def _render_pose(J, char, half_w, half_h, scale):
    """Draw one pose into a transparent QPixmap.  The pixmap centre is the
    figure root, so Figure.draw's centred drawPixmap keeps frames aligned."""
    w = max(2, int(math.ceil(half_w * scale)) * 2)
    h = max(2, int(math.ceil(half_h * scale)) * 2)
    pm = QPixmap(w, h)
    pm.fill(Qt.transparent)
    qp = QPainter(pm)
    qp.setRenderHint(QPainter.Antialiasing)
    qp.translate(w / 2.0, h / 2.0)
    qp.scale(scale, scale)

    body_col = QColor(char["palette"].get("body", "#8fa0b8"))
    pen = QPen(body_col)
    pen.setWidthF(3.5)
    pen.setCapStyle(Qt.RoundCap)
    qp.setPen(pen)
    for a, b in _BODY_SEGMENTS:
        qp.drawLine(QPointF(*J[a]), QPointF(*J[b]))
    hx, hy = J["head"]
    qp.setBrush(Qt.NoBrush)
    qp.drawEllipse(QPointF(hx, hy - 4), 10, 10)

    pts = J["_weapon_pts"]
    if pts:
        wpn = char.get("weapon", {})
        chain = [QPointF(*J["r_hand"])] + [QPointF(*p) for p in pts]
        glow = QPen(QColor(char["palette"].get("accent", "#ff5050")))
        glow.setWidthF(float(wpn.get("thickness", 3)) + 3.0)
        glow.setCapStyle(Qt.RoundCap)
        qp.setOpacity(0.55)
        qp.setPen(glow)
        for i in range(len(chain) - 1):
            qp.drawLine(chain[i], chain[i + 1])
        qp.setOpacity(1.0)
        wp_pen = QPen(QColor(wpn.get("color", "#d8dee9")))
        wp_pen.setWidthF(float(wpn.get("thickness", 3)))
        wp_pen.setCapStyle(Qt.RoundCap)
        qp.setPen(wp_pen)
        for i in range(len(chain) - 1):
            qp.drawLine(chain[i], chain[i + 1])

    qp.end()
    return pm


def rasterize_character(char):
    """Rasterise every action's keyframes.  Returns {action: [QPixmap, ...]}.

    One shared canvas size is computed over ALL actions so the root stays at
    the pixmap centre in every frame (no jitter between animations)."""
    bones = dict(_DEFAULT_BONES)
    bones.update(char.get("bones", {}))
    wpn_pts = char.get("weapon", {}).get("points", []) or []
    # stats.scale (0.5-2.0) multiplies the rasterization scale factor; every
    # frame still shares one root-centred canvas, so nothing else changes.
    scale = (config.TARGET_HEAD_PX / _RIG_HEAD_DIAMETER) * _char_scale(char)

    joints_per_action = {}
    half_w = half_h = 1.0
    idle_max_joint_dist = 0.0
    for name, action in char.get("actions", {}).items():
        js = []
        for kf in action.get("keyframes", []):
            J = rig_joints(kf.get("p", {}), bones, wpn_pts)
            ex, ey = _pose_extent(J)
            half_w = max(half_w, ex)
            half_h = max(half_h, ey)
            if name == "idle":
                idle_max_joint_dist = max(idle_max_joint_dist,
                                           _pose_max_joint_dist(J))
            js.append(J)
        joints_per_action[name] = js
    half_w += 4.0
    half_h += 4.0

    # Hurtbox: max joint extent of the idle pose, scaled — derivable, no
    # wizard field needed.  Hit checks read it via the figure's mode, with
    # the existing fixed constants as fallback for built-in figures.
    char["hurtbox_radius"] = idle_max_joint_dist * scale

    frames = {}
    for name, js in joints_per_action.items():
        frames[name] = [_render_pose(J, char, half_w, half_h, scale)
                        for J in js]
    return frames


def _flip(pixmaps):
    t = QTransform().scale(-1, 1)
    return [pm.transformed(t) for pm in pixmaps]


# ---------------------------------------------------------------------------
# Registration — mode, tuning, palette LUT
# ---------------------------------------------------------------------------
def _hex_rgb(h):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _anim_ticks(action, fallback):
    """Ticks-per-frame so the keyframe sequence roughly spans duration_ms."""
    if not action:
        return fallback
    n = max(1, len(action.get("keyframes", [])))
    dur = float(action.get("duration_ms", 0) or 0)
    if dur <= 0:
        return fallback
    return max(1, int(round(dur / n / config.TICK_MS)))


_ARCHETYPE_PREDICATES = {
    "shooter": ("can_shoot", "retreats"),
    "melee": ("uses_melee", "charges_full"),
}
_PREDICATE_KEYS = ("can_shoot", "uses_melee", "retreats", "charges_full")


def _predicates_for(char):
    """True-predicate names for a character (v2 explicit, v1 inferred)."""
    arch = str(char.get("archetype", "") or "").strip().lower()
    if arch in _ARCHETYPE_PREDICATES:
        return _ARCHETYPE_PREDICATES[arch]
    if arch == "new":
        raw = char.get("predicates", {}) or {}
        return tuple(k for k in _PREDICATE_KEYS if raw.get(k))
    # v1 fallback: infer from weapon polyline
    if char.get("weapon", {}).get("points"):
        return _ARCHETYPE_PREDICATES["melee"]
    return _ARCHETYPE_PREDICATES["shooter"]


def _wander_strength(char):
    """Clamped movement.wander_strength, or None if absent/invalid."""
    mv = char.get("movement", {}) or {}
    if "wander_strength" not in mv:
        return None
    try:
        return max(0.0, min(1.0, float(mv["wander_strength"])))
    except (TypeError, ValueError):
        return None


def _outline_glow(char):
    """Top-level outline_glow opt-in -> (rgb, radius, opacity) tuple, or None
    when absent/disabled. Any character's JSON can enable this; no
    archetype/game-mode branching involved."""
    og = char.get("outline_glow")
    if not isinstance(og, dict) or not og.get("enabled"):
        return None
    try:
        rgb = _hex_rgb(og.get("color", ""))
    except (TypeError, ValueError, IndexError):
        rgb = config.OUTLINE_GLOW_DEFAULT_RGB
    try:
        radius = max(0.0, float(og.get("radius", config.OUTLINE_GLOW_DEFAULT_RADIUS)))
    except (TypeError, ValueError):
        radius = config.OUTLINE_GLOW_DEFAULT_RADIUS
    try:
        opacity = max(0, min(255, int(og.get("opacity", config.OUTLINE_GLOW_DEFAULT_OPACITY))))
    except (TypeError, ValueError):
        opacity = config.OUTLINE_GLOW_DEFAULT_OPACITY
    return (rgb, radius, opacity)


def _trail_gradient(char):
    """Top-level trail_gradient opt-in -> (start_rgb, end_rgb, start_fraction)
    tuple, or None when absent/disabled. Overrides the default flowing
    LUT-driven trail colour with a static two-colour gradient by trail
    position (tail->head). Any character's JSON can enable this; no
    archetype/game-mode branching involved."""
    tg = char.get("trail_gradient")
    if not isinstance(tg, dict) or not tg.get("enabled"):
        return None
    try:
        start_rgb = _hex_rgb(tg.get("start_color", ""))
    except (TypeError, ValueError, IndexError):
        start_rgb = config.TRAIL_GRADIENT_DEFAULT_START_RGB
    try:
        end_rgb = _hex_rgb(tg.get("end_color", ""))
    except (TypeError, ValueError, IndexError):
        end_rgb = config.TRAIL_GRADIENT_DEFAULT_END_RGB
    try:
        start_fraction = max(0.0, min(1.0, float(
            tg.get("start_fraction",
                   config.TRAIL_GRADIENT_DEFAULT_START_FRACTION))))
    except (TypeError, ValueError):
        start_fraction = config.TRAIL_GRADIENT_DEFAULT_START_FRACTION
    return (start_rgb, end_rgb, start_fraction)


def _kites_flag(char):
    """movement.kites opt-in — independent of archetype/predicates (which
    are locked by the archetype trap for 'shooter'/'melee'). Any character,
    regardless of archetype, can opt into always-hold-distance kiting this
    way. Defaults False."""
    mv = char.get("movement", {}) or {}
    return bool(mv.get("kites"))


def _register(char):
    """Register mode class, tuning, cycle-order key, and palette LUT."""
    key = str(char.get("name", "custom")).strip().lower().replace(" ", "_")

    if key not in modes.MODE_REGISTRY:
        attrs = {"key": key}
        for name in _predicates_for(char):
            attrs[name] = (lambda self: True)
        if _kites_flag(char):
            attrs["kites"] = (lambda self: True)
        ws = _wander_strength(char)
        if ws is not None:
            # Cap semantics: lateral wander never exceeds ws (0.15 = charge
            # straight like swordsman, 1.0 = full weave like runner).  Same
            # mode instance drives Solo and Battle — parity is automatic.
            attrs["wander_blend"] = (
                lambda self, dist, strength, _ws=ws:
                    min(_ws, dist / 300.0) * strength)
        cls = type(key.title() + "CharacterMode", (modes.FigureMode,), attrs)
        inst = cls()
        inst.character = char           # battle props + fx_layers for combat
        modes.MODE_REGISTRY[key] = inst
    else:
        modes.MODE_REGISTRY[key].character = char

    actions = char.get("actions", {})
    stats = char.get("stats", {}) or {}

    def _stat(name, default):
        try:
            return float(stats.get(name, default))
        except (TypeError, ValueError):
            return default

    tuning = dict(
        chase_speed=_stat("chase_speed", 3.0),
        follow_speed=_stat("follow_speed", 4.5),
        anim_speed=_anim_ticks(actions.get("run"), 5),
        idle_anim_speed=_anim_ticks(actions.get("idle"), 10),
        max_hp=_stat("max_hp", 100),
        basic_attack_radius=_stat("basic_attack_radius", config.SLASH_RADIUS),
        outline_glow=_outline_glow(char),
        trail_gradient=_trail_gradient(char),
    )
    # Written straight into MODE_CONFIGS[key] — everything downstream (Solo
    # and Battle alike) already reads from there, so no other file changes.
    if key in config.MODE_CONFIGS:
        config.MODE_CONFIGS[key].update(tuning)
    else:
        config.MODE_CONFIGS[key] = tuning
    if key not in config.MODE_ORDER:
        config.MODE_ORDER.append(key)

    pal = char.get("palette", {})
    body = _hex_rgb(pal.get("body", "#8fa0b8"))
    accent = _hex_rgb(pal.get("accent", "#ff5050"))
    palette.register_custom_lut(key, palette.build_lut([body, accent]))
    return key


def _build_bundle(frames):
    """Pack rasterised action frames into a FrameBundle."""
    from .assets import FrameBundle   # lazy: avoids circular import at load
    run = frames.get("run", [])
    idle = frames.get("idle", [])
    slash = frames.get("attack_normal", [])
    defend = frames.get("defend", [])
    slide = defend[0] if defend else None
    slide2 = defend[1] if len(defend) > 1 else slide
    return FrameBundle(
        run, _flip(run), idle, _flip(idle),
        slide, _flip([slide])[0] if slide else None,
        slide2, _flip([slide2])[0] if slide2 else None,
        slash, _flip(slash),
    )


def _tint_pixmap(pm, hex_color):
    """Return a NEW QPixmap: same alpha silhouette as `pm`, flattened to one
    solid colour. Non-destructive — `pm` (the borrowed sprite_source frame)
    is never mutated, so the donor character's own sprites stay untouched."""
    if pm is None:
        return None
    tinted = QPixmap(pm.size())
    tinted.fill(Qt.transparent)
    qp = QPainter(tinted)
    qp.drawPixmap(0, 0, pm)
    qp.setCompositionMode(QPainter.CompositionMode_SourceIn)
    qp.fillRect(tinted.rect(), QColor(hex_color))
    qp.end()
    return tinted


def _tint_bundle(bundle, hex_color):
    """Build a private FrameBundle whose frames are solid-colour silhouettes
    of a borrowed sprite_source bundle. Generic: any JSON character using
    sprite_source can opt in via `"sprite_tint": true` (colour comes from its
    own `palette.body`) — no per-character special-casing, and the donor
    mode's bundle object is left completely alone."""
    from .assets import FrameBundle   # lazy: avoids circular import at load

    def _tint_list(pixmaps):
        return [_tint_pixmap(pm, hex_color) for pm in (pixmaps or [])]

    return FrameBundle(
        _tint_list(bundle.run), _tint_list(bundle.run_flipped),
        _tint_list(bundle.idle), _tint_list(bundle.idle_flipped),
        _tint_pixmap(bundle.slide, hex_color),
        _tint_pixmap(bundle.slide_flipped, hex_color),
        _tint_pixmap(bundle.slide2, hex_color),
        _tint_pixmap(bundle.slide2_flipped, hex_color),
        _tint_list(bundle.slash), _tint_list(bundle.slash_flipped),
    )


# ---------------------------------------------------------------------------
# Entry point — called by AssetLibrary._load_all (Solo and Battle both build
# their worlds from the same AssetLibrary, so parity is automatic).
# ---------------------------------------------------------------------------
def _write_thumb(folder, key, frames):
    """Write <key>_thumb.png (idle keyframe 0) only if the file is missing."""
    path = os.path.join(folder, key + "_thumb.png")
    if os.path.exists(path):
        return
    idle = frames.get("idle")
    if not idle:
        idle = next((f for f in frames.values() if f), None)
    if idle:
        idle[0].save(path, "PNG")


def _load_sprite_files(root_dir, sf):
    """Generic `sprite_files` loader: build a FrameBundle from PNG frame
    sets the character JSON authors itself (files live next to the launcher,
    like the built-in sets).  Each set carries its own measured
    `src_head_px` so mixed-scale source art lands at roster size:

        "sprite_files": {
          "remove_bg": false,           # skip near-black bg removal (alpha art)
          "run":   {"files": [...], "src_head_px": 406},
          "idle":  {"files": [...], "src_head_px": 117},
          "slash": {"files": [...], "src_head_px": 117},
          "slide": {"files": [...], "src_head_px": 117}   # optional (2 files)
        }

    Missing sets simply stay empty (slide falls back to the idle frame in
    the renderer).  Every process loads through this same path, so Solo and
    Battle see the identical bundle."""
    from .assets import FrameBundle   # lazy: avoids circular import at load

    def _set(name):
        blk = sf.get(name) or {}
        files = [os.path.join(root_dir, str(f))
                 for f in (blk.get("files") or [])]
        try:
            head = float(blk.get("src_head_px", 100.0) or 100.0)
        except (TypeError, ValueError):
            head = 100.0
        return files, config.TARGET_HEAD_PX / max(head, 1.0)

    run_files, run_sc = _set("run")
    idle_files, idle_sc = _set("idle")
    slash_files, slash_sc = _set("slash")
    slide_files, slide_sc = _set("slide")
    return FrameBundle.load(
        run_files, idle_files, run_sc, idle_sc,
        slide_files=slide_files if len(slide_files) >= 2 else None,
        slide_scale=slide_sc,
        slash_files=slash_files or None, slash_scale=slash_sc,
        remove_bg=bool(sf.get("remove_bg", True)))


def load_all(root_dir, bundles):
    """Scan <root>/characters/*.json, register each, add its FrameBundle."""
    folder = os.path.join(root_dir, "characters")
    for path in sorted(glob.glob(os.path.join(folder, "*.json"))):
        try:
            with open(path, "r", encoding="utf-8") as f:
                char = json.load(f)
            if char.get("format") != "pb_character":
                continue
            key = _register(char)
            # sprite_source: borrow a built-in mode's .png FrameBundle
            # (e.g. "swordsman") instead of rasterising the rig — the
            # borrowed frames play in the same contexts (run/idle/slash/
            # slide).  hurtbox_radius is dropped so hit checks fall back
            # to the same fixed constants the built-in uses.  Every
            # process loads through this same path, so Solo and Battle
            # see the identical bundle.
            sprite_src = str(char.get("sprite_source", "") or "").strip().lower()
            if sprite_src and sprite_src in bundles:
                donor = bundles[sprite_src]
                if char.get("sprite_tint"):
                    # Opt-in recolor: private silhouette copy tinted with
                    # sprite_tint_color if authored, else palette.body (old
                    # default behaviour). Decoupling lets a character's
                    # sprite colour differ from its trail/particle LUT
                    # colour (which always derives from palette.body/accent
                    # — see register_custom_lut below), without touching
                    # anything for characters that don't set the new field.
                    # Donor mode (e.g. swordsman) keeps its own bundle
                    # object untouched, so this never bleeds into other
                    # characters/modes.
                    tint_hex = (char.get("sprite_tint_color")
                                or char.get("palette", {}).get("body", "#ffffff"))
                    bundles[key] = _tint_bundle(donor, tint_hex)
                else:
                    bundles[key] = donor
                char.pop("hurtbox_radius", None)
            elif isinstance(char.get("sprite_files"), dict):
                # Character-authored PNG frame sets (generic sprite_files
                # block).  hurtbox_radius is dropped so hit checks fall back
                # to the same fixed constants the built-ins use — matching
                # the sprite_source path above.
                bundle = _load_sprite_files(root_dir, char["sprite_files"])
                bundles[key] = bundle
                # Resolved source-PNG paths per set, consumed by the sprite
                # emitter so it can colour-scan the full-res art instead of
                # the (possibly tiny) scaled pixmaps.
                char["_sprite_src_paths"] = {
                    n: [os.path.join(root_dir, str(f)) for f in
                        ((char["sprite_files"].get(n) or {}).get("files")
                         or [])]
                    for n in ("run", "idle", "slash")}
                char.pop("hurtbox_radius", None)
                thumb_path = os.path.join(folder, key + "_thumb.png")
                if bundle.idle and not os.path.exists(thumb_path):
                    bundle.idle[0].save(thumb_path, "PNG")
            else:
                if sprite_src:
                    print("sprite_source %r not found for %s — rasterising"
                          % (sprite_src, key))
                frames = rasterize_character(char)
                bundles[key] = _build_bundle(frames)
                _write_thumb(folder, key, frames)
        except Exception as e:                        # never kill the game
            print("Character load failed for %s: %s" % (path, e))


