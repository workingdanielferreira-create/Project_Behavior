"""
Application layer — World (central state + factory) and Overlay (the Qt widget).

Overlay is deliberately thin: it owns the window, polls the cursor, runs the
systems pipeline, and paints.  All per-tick logic lives in systems; all shared
state and entity creation lives in World.
"""

import math
import os
import sys
import time
import traceback

from PyQt5.QtWidgets import QApplication, QWidget
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import (QPainter, QCursor, QPen, QColor, QRadialGradient,
                         QFont, QPixmap)

from . import config, modes, systems, ai, action_log, combat, actions, fxkit, blink, dodge, timefx, clashfx, clash, motion, unique, movestyle
from . import swordfx
from . import dmgnum
from .prebattle import PreBattleMenu
from . import platform_win as win
from .assets import AssetLibrary
from .figure import Figure
from .palette import lut_for_index, lut_for_mode, LUT_BLUE, LUT_PINK

# crash_log replaced by action_log.crash() — see laser/action_log.py



# ---------------------------------------------------------------------------
# Collision-dot sprite cache — one pre-rendered pixmap per rainbow hue.
# The dot's lifetime spans ~50 ticks, so at most ~50 hue buckets are cached.
# Fade is applied with painter opacity instead of re-building gradients.
# ---------------------------------------------------------------------------
_DOT_SPRITES = {}


def _dot_sprite(hue, rad):
    key = (hue, rad)
    entry = _DOT_SPRITES.get(key)
    if entry is None:
        size = rad * 2 + 2
        c = size / 2.0
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        qp = QPainter(pm)
        qp.setRenderHint(QPainter.Antialiasing)
        qp.setPen(Qt.NoPen)
        col = QColor.fromHsv(hue, 255, 255)
        r2, g2, b2 = col.red(), col.green(), col.blue()
        gr = QRadialGradient(c, c, rad)
        gr.setColorAt(0.0, QColor(255, 255, 255, 255))
        gr.setColorAt(0.35, QColor(r2, g2, b2, 255))
        gr.setColorAt(1.0, QColor(r2, g2, b2, 0))
        qp.setBrush(gr)
        qp.drawEllipse(0, 0, size, size)
        qp.end()
        entry = (pm, size // 2)
        _DOT_SPRITES[key] = entry
    return entry

class SideState:
    """Everything one fighter's side owns: its figures, its bullets, its
    firing cadence, and its snapshot view of the opponent.  Two of these in
    one World replace what used to be two whole processes."""

    def __init__(self, mode_key):
        self.figures = []
        self.projectiles = []
        self.mode_key = mode_key
        self.shoot_ticks = 0
        self.shot_phase = 0
        self.shot_pause_ticks = 0
        self.intercepted_bullets = set()
        self.partner_figures = []   # opponent snapshot: (x, y, dash, parry)
        self.enemy_projs = []       # opponent bullets: (x,y,vx,vy,r,g,b,dmg,proj)
        self.clones = []            # this side's own HPTClone instances
                                    # (see combat.HPTClone / hp_threshold_clones)
        self.hpt_beam_ticks = 0     # shared clock driving the clones'
                                    # synchronized beam volley (combat.tick_hpt_clones)
        self.enemy_fx = []          # opponent's live damaging FX, bullets, crescents, petals, clones: (x, y, tags, airborne)
        self.enemy_shots = []       # opponent's projectiles as fxkit.Shot, for the
                                    # FX Studio auto-projectile tracker (Intercept)
        self.round_refs = {}        # (id(inst), bullet index) -> fxkit.RoundRef, kept
                                    # across ticks so each gun / ki bullet keeps its identity
        self.partner_image = []     # per partner_figures entry: is it an image character
        self.partner_facing = []    # per partner_figures entry: facing_left (tactical retreat)
        self.partner_gone = []      # per partner_figures entry: blinked out (FX Studio blink)
        self.partner_scale = []     # per partner_figures entry: character scale (body hit circle)
        self.partner_melee = []     # per partner_figures entry: fights in melee (movement style "enemy")
        self.partner_state = []     # per partner_figures entry: (hp_pct, attacking, defending)
                                    # for FX Studio target_* trigger conditions
        self.fx_hits = []           # FX Studio hits this side landed this tick,
                                    # delivered to the opponent by refresh_battle
        self.fx_pulls = []          # FX Studio pull fields this tick (meteor /
                                    # black hole, laser/powerfx.py), same delivery
        self.fx_drags = []          # FX Studio Drag pushes this tick (fxkit
                                    # drag_step), same delivery


class World:
    """Central mutable state plus the figure factory and high-level commands."""

    def __init__(self, assets, screen_w, screen_h):
        self.assets = assets
        self.screen_w = screen_w
        self.screen_h = screen_h

        # Two locally-hosted sides. Side 0 = P1 (always fielded, key '1'
        # cycles its character), side 1 = P2 (key '2' cycles characters and
        # then OFF).  Battle mode is simply "both sides have figures" — the
        # per-tick pipeline runs once per fielded side, each side seeing the
        # other through read-only snapshots (partner_figures / enemy_projs),
        # so the two fighters keep fully independent decision streams
        # (separate Personality RNGs, separate cadences, separate FSMs).
        self.sides = [SideState(config.MODE_ORDER[0]),
                      SideState(config.MODE_ORDER[0])]
        self.side_idx = 0
        self._dead = []   # figures killed this tick; culled next refresh

        # Bound view of the current side (refreshed by bind_side).
        self.figures = self.sides[0].figures
        self.mode_key = self.sides[0].mode_key
        self.projectiles = self.sides[0].projectiles
        self.clones = self.sides[0].clones
        self.hpt_beam_ticks = self.sides[0].hpt_beam_ticks
        self.shoot_ticks = 0   # per-side firing cadence counter (bound)
        self.shot_phase = 0       # current runner cycle phase (0=cone,1=zigzag,2=homing)
        self.shot_pause_ticks = 0 # counts down the inter-cycle pause

        # Flags
        self.runner_on = True
        self.collision_on = False
        self.path_follow = False
        self.runaway = False
        self.shoot_mode = False

        # Cursor + tick
        self.cursor = (screen_w // 2, screen_h // 2)
        self.global_tick = 0

        # Battle state — bound per-side views of the opposing side.
        self.battle_mode = False
        self.partner_figures = []
        self.enemy_projs = []
        self.enemy_fx = []
        self.enemy_shots = []
        self.partner_image = []
        self.partner_facing = []
        self.partner_gone = []
        self.partner_scale = []
        self.partner_melee = []
        self.partner_state = []
        self.intercepted_bullets = set()

        # Collision impact dots: list of [x, y, age] (drawn + culled in paintEvent)
        self.collision_dots = []

        # Slash FX state
        self.hitstop_ticks = 0              # >0 = world frozen (big-hit freeze)
        # FX Studio Time control (laser/timefx.py), set per time sub-pass:
        # ids of the figures whose FX step in it (None = all), the figures
        # whose FX step while their body is stopped, and whether the side's
        # shared FX (HP-threshold clones) step.
        self.time_fx_on = None
        self.time_fx_only = ()
        self.time_side_fx = True
        self.notice = ("", 0)               # (text, ticks left) — on-screen message
        self.impact_rings = []              # [x, y, age, max_radius] shockwaves
        self.muzzle_flashes = []            # [x, y, age, r, g, b] firing flashes
        self.sparks = []                    # [x, y, vx, vy, age, r, g, b]
        # Clash explosions (laser/clashfx.py): live ClashFX objects, drawn +
        # aged in _paint.  F6 previews the next variation at the cursor.
        self.clash_fx = []
        self.damage_numbers = []            # dmgnum.DamageNumber — combined hit totals
        self.clash_preview_idx = 0

        # Input bookkeeping
        self._ctrl_prev = False
        self.ctrl_used = False
        self._quit = False
        # Ctrl+0 roster lock: while True, the add/remove/swap fighter keys
        # (1/2/3/4, F7/F8) are ignored in Solo and Battle.  Deaths still
        # follow the normal rules (World.on_figure_death).
        self.roster_locked = False
        # Ctrl+Shift+. pre-battle menu (laser/prebattle.py): while open the
        # whole game is paused and fighters stand idle (see Overlay._tick).
        self.prebattle = PreBattleMenu()

        self.add_figure()

        # update_game.py launches with --prebattle: start with the pre-battle
        # character selector already open (same as pressing Ctrl+Shift+.).
        # World-level, so Solo and Battle behave identically.
        if "--prebattle" in sys.argv[1:]:
            self.prebattle.toggle()

        # Action log — init after all state is ready
        _launcher_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        action_log.init(log_dir=_launcher_dir, enabled=config.LOG_ENABLED)
        action_log.install_excepthook()

    # --- factory -----------------------------------------------------------
    @property
    def mode(self):
        return modes.get_mode(self.mode_key)

    def add_figure(self, side_idx=0, mode_key=None, slot=None):
        """Field one more fighter on `side_idx`.

        `mode_key` overrides the side's base character, which is what lets a
        single team hold two DIFFERENT characters at once (runner +
        swordsman, mage + new_fighter, ...) — see cycle_side_extra.  `slot`
        overrides the offset/palette slot for the same reason.  A Figure
        owns its own mode/bundle/lut, so nothing below the World level cares
        that its team-mate is a different character.
        """
        side = self.sides[side_idx]
        # Mirror Legion copies (laser/unique.py) ride at the END of the list
        # and never take a fighter slot: count and insert around them.
        real = [f for f in side.figures if not unique.is_clone(f)]
        if len(real) >= config.MAX_FIGURES:
            return False
        i = len(real)
        key = mode_key or side.mode_key
        # Side 1 figures take the next offset/palette slot so the two sides
        # spawn apart and read as distinct fighters at a glance.
        if slot is None:
            slot = i + side_idx
        fig = Figure(modes.get_mode(key),
                     self.assets.bundle(key),
                     lut_for_mode(key, slot), slot,
                     self.screen_w, self.screen_h)
        side.figures.insert(len(real), fig)
        return True

    def remove_figure(self, side_idx=0):
        side = self.sides[side_idx]
        real = [f for f in side.figures if not unique.is_clone(f)]
        if real:
            side.figures.remove(real[-1])
            return True
        return False

    # --- commands ----------------------------------------------------------
    def reload_characters(self):
        """F5: re-read every image character (characters/<name>/ with its
        Rig Forge character.json, frames and FX Studio file) from disk and
        re-skin the figures using them, so an export or an FX save shows up
        in the running game straight away.  Same path for Solo and Battle."""
        from . import drops, characters as _chars
        root = self.assets.dir
        try:
            drops.organize_drops(root)
        except Exception:
            pass
        pkgs = _chars._find_packages(root)
        for key, _rel, _man, _fx in pkgs:
            m = modes.MODE_REGISTRY.get(key)
            for attr in ("_fxkit_cache", "_combo_cfg", "_retreat_cfg", "_dodge_cfg",
                         "_ua_cfg", "_glide_cache"):
                if m is not None and hasattr(m, attr):
                    try:
                        delattr(m, attr)
                    except AttributeError:
                        pass
        _chars.load_packages(root, self.assets.bundles, pkgs)
        names = {p[0] for p in pkgs}
        for side in self.sides:
            for fig in side.figures:
                if fig.mode.key in names and not unique.is_construct(fig):
                    self._reskin_figure(fig, fig.mode.key)
        msg = ("Reloaded " + ", ".join(sorted(names))) if names else "No Rig Forge characters found in characters/"
        missing = sorted(k for k, _r, _m, fx in pkgs if not fx)
        if missing:
            msg += "   (no FX file: " + ", ".join(missing) + ")"
        self.notice = (msg, 180)
        action_log.log("RELOAD", msg)

    def _reskin_figure(self, fig, mode_key):
        """Switch ONE figure to `mode_key` — sprites, speeds, palette, HP.

        Every character swap in the game funnels through here, so a team of
        mixed characters stays consistent and Solo/Battle can't diverge:
        there is only one code path.
        """
        fig.set_mode(modes.get_mode(mode_key), self.assets.bundle(mode_key))
        fig.lut = lut_for_mode(mode_key, fig.index)
        fig.trail.lut = fig.lut

    def _reskin_side(self, side_idx):
        """Re-apply a side's mode_key to its BASE fighter (slot 0) only.

        Slot 0 belongs to keys '1'/'2' and Alt+Left/Right.  The extra fighter
        added by key '3'/'4' owns its own character and is deliberately left
        untouched here — that is exactly what allows one team to field two
        different characters.
        """
        side = self.sides[side_idx]
        if side.figures:
            self._reskin_figure(side.figures[0], side.mode_key)

    def cycle_mode(self, delta, side_idx=0):
        order = modes.ordered_modes()
        if not order:
            return
        side = self.sides[side_idx]
        cur = order.index(side.mode_key) if side.mode_key in order else 0
        new_key = order[(cur + delta) % len(order)]
        if new_key == side.mode_key:
            return
        side.mode_key = new_key
        if side_idx == self.side_idx:
            self.mode_key = new_key
        self._reskin_side(side_idx)

    def cycle_side_char(self, side_idx):
        """Key '1' / '2' character cycling.  P1 (side 0) always keeps a
        fighter: tap to advance through every registered character, wrapping.
        P2 (side 1) cycles through every character and then OFF (side
        cleared, battle ends); tapping again fields the first character."""
        order = modes.ordered_modes()
        if not order:
            return
        side = self.sides[side_idx]
        if not side.figures:
            if side.mode_key not in order:
                side.mode_key = order[0]
            self.add_figure(side_idx)
            return
        cur = order.index(side.mode_key) if side.mode_key in order else -1
        nxt = cur + 1
        if side_idx == 1 and nxt >= len(order):
            side.figures.clear()
            side.projectiles.clear()
            side.mode_key = order[0]
            return
        side.mode_key = order[nxt % len(order)]
        if side_idx == self.side_idx:
            self.mode_key = side.mode_key
        self._reskin_side(side_idx)

    def cycle_side_extra(self, side_idx):
        """Key '3' (P1) / '4' (P2): the team's SECOND fighter slot.

        Lets one side field two different characters at once — runner +
        swordsman, mage + new_fighter, any pairing in the roster.

        Tap 1 fields the extra fighter as the first registered character;
        every further tap advances it one step through the roster; the tap
        after the last character retires it (team back to one fighter), and
        the next tap re-fields the first character again.  Slot 0 is never
        touched — it stays owned by keys '1'/'2'.

        Identical in Solo and Battle by construction: the per-tick pipeline
        already runs over every figure on a fielded side and every system
        routes through `fig.mode`'s predicates, so a two-character team is
        just two figures with different modes in both modes.
        """
        order = modes.ordered_modes()
        if not order:
            return
        side = self.sides[side_idx]
        if not side.figures:
            # Team is empty (P2 was cycled OFF with key '2').  Re-field the
            # base fighter first so slot 0 always belongs to key '1'/'2';
            # the next tap then stacks the extra fighter on top of it.
            if side.mode_key not in order:
                side.mode_key = order[0]
            self.add_figure(side_idx)
            return
        if len([f for f in side.figures if not unique.is_clone(f)]) < 2:
            self.add_figure(side_idx, mode_key=order[0],
                            slot=config.EXTRA_FIGURE_SLOT + side_idx)
            return
        fig = side.figures[1]
        cur = order.index(fig.mode.key) if fig.mode.key in order else -1
        nxt = cur + 1
        if nxt >= len(order):
            self._retire_extra(side_idx)
            return
        self._reskin_figure(fig, order[nxt])

    def _retire_extra(self, side_idx):
        """Remove the key-'3'/'4' fighter and clean up what it owned.

        Its in-flight bullets are killed AT SOURCE via combat.kill_projectile
        (never by setting `alive`, which is derived).  The side's
        HP-threshold clones are dropped only when no remaining fighter on
        that side spawns them, so a retiring team-mate can't leave orphan
        corner spheres firing on its behalf — and can't take a surviving
        team-mate's clones with it either.
        """
        side = self.sides[side_idx]
        if len([f for f in side.figures if not unique.is_clone(f)]) < 2:
            return
        fig = side.figures.pop(1)
        for pr in side.projectiles:
            if pr.owner is fig:
                combat.kill_projectile(pr)
        if side.clones and not any(combat.hpt_clone_cfg(f) is not None
                                   for f in side.figures):
            side.clones.clear()
        if fig in self._dead:
            self._dead.remove(fig)

    def request_manual_ultimate(self, side_idx):
        """Ctrl+1 (side 0) / Ctrl+2 (side 1): force that side's currently
        fielded figure(s) to fire their next ultimate tier, bypassing the
        HP threshold. Queues on the figure; CombatSystem/
        combat.try_fire_manual_ultimate fires it the instant the figure is
        free (see systems.py). No-op if that side has no fielded figure.
        Identical in Solo & Battle."""
        for fig in self.sides[side_idx].figures:
            fig.combat.manual_ult_queued = True

    def request_manual_special(self, side_idx, slot):
        """Ctrl+Shift+1..4: force ONE fielded fighter to fire its
        attack_special, bypassing its trigger conditions and cooldown.
        slot 0 = the key-'1'/'2' fighter, slot 1 = the key-'3'/'4' extra
        fighter (Mirror Legion copies never count as a slot).  Queues on
        the figure; combat.try_fire_manual_special fires it the instant the
        figure is free (see systems.py).  No-op if that slot is empty.
        Identical in Solo & Battle."""
        real = [f for f in self.sides[side_idx].figures if not unique.is_clone(f)]
        if slot < len(real):
            real[slot].combat.manual_special_queued = True

    def preview_clash_fx(self):
        """F6: fire the next clash explosion variation at the cursor.  Side A
        colour = P1's fighter, side B = P2's (a contrasting palette when P2
        is not fielded); the clash axis runs P1 -> P2 when both are on
        screen, else left -> right.  Sustained variations play their preview
        hold, then detonate; the blowout's winner alternates.  Identical in
        Solo and Battle."""
        keys = clashfx.preview_order()
        i = self.clash_preview_idx % len(keys)
        self.clash_preview_idx += 1
        key = keys[i]
        f0 = self.sides[0].figures[0] if self.sides[0].figures else None
        f1 = self.sides[1].figures[0] if len(self.sides) > 1 and self.sides[1].figures else None
        c1 = tuple(f0.lut[128]) if f0 is not None else tuple(LUT_BLUE[128])
        if f1 is not None:
            c2 = tuple(f1.lut[128])
        else:
            c2 = tuple(LUT_PINK[128]) if c1 != tuple(LUT_PINK[128]) else tuple(LUT_BLUE[128])
        angle = 0.0
        if f0 is not None and f1 is not None and (f0.x != f1.x or f0.y != f1.y):
            angle = math.degrees(math.atan2(f1.y - f0.y, f1.x - f0.x))
        x, y = self.cursor
        clashfx.spawn(self, key, x, y, angle=angle, c1=c1, c2=c2, winner=(self.clash_preview_idx // len(keys)) % 2)
        self.notice = ("Clash FX %d/%d: %s  (F6 next)" % (i + 1, len(keys), clashfx.display_name(key)), 150)

    def toggle_shoot_mode(self):
        self.shoot_mode = not self.shoot_mode
        if not self.shoot_mode:
            self.muzzle_flashes.clear()
            self.shoot_ticks = 0
            self.shot_phase = 0
            self.shot_pause_ticks = 0
            self.projectiles.clear()
            for side in self.sides:
                side.projectiles.clear()
                side.clones.clear()
                side.shoot_ticks = side.shot_phase = side.shot_pause_ticks = 0
                for fig in side.figures:
                    fig.combat.reset()

    def movement_target(self, fig):
        """Where this figure moves toward this tick."""
        # Movement style (laser/movestyle.py): the character's own patterns
        # and phases.  Same target in both modes (nearest enemy in Battle,
        # the cursor in Solo); None = no style / no phase passes, so the old
        # movement below runs.
        if movestyle.cfg(fig) is not None:
            if self.battle_mode and self.partner_figures:
                ex, ey = self._nearest_enemy(fig.x, fig.y)
                # The "enemy" condition: does that nearest enemy fight in melee.
                mel = [m for (px, py, _d, _p), m in zip(self.partner_figures, self.partner_melee)
                       if (px, py) == (ex, ey)]
                melee = bool(mel and mel[0])
            else:
                # Solo: the cursor hits by touching, so it counts as melee.
                ex, ey = self.cursor
                melee = True
            off = actions.chase_offset(fig, self)
            if off is None:
                off = (fig.motion.offset_x, fig.motion.offset_y)
            pt = movestyle.target(fig, ex, ey, auto_stop=(off[0] * off[0] + off[1] * off[1]) ** 0.5,
                                  wall=ai._wall_repulsion, enemy_melee=melee)
            if pt is not None:
                return pt
        elif fig.motion.style is not None:
            # No style (another character, or it was switched off and F5'd):
            # the old movement runs, not the last styled step.
            fig.motion.style.live = False
        if fig.mode.kites():
            # Kiting is identical in Solo (target=cursor) and Battle
            # (target=nearest enemy) — ai.kite_target takes a plain point
            # and doesn't know or care which mode it came from.
            if self.battle_mode and self.partner_figures:
                ex, ey = self._nearest_enemy(fig.x, fig.y)
            else:
                ex, ey = self.cursor
            return ai.kite_target(fig, ex, ey)
        if self.battle_mode and self.partner_figures:
            return ai.battle_target(self, fig)
        return self.cursor

    def melee_target(self, fig):
        """Dash/slash target for a melee figure, or None if it shouldn't attack.
        Non-battle: the cursor while attack mode is on. Battle: nearest enemy,
        but only while attack mode is on (otherwise it just chases)."""
        if not fig.mode.uses_melee():
            return None
        if self.battle_mode and self.partner_figures:
            return self._nearest_enemy(fig.x, fig.y) if self.shoot_mode else None
        if self.shoot_mode:
            return self.cursor
        return None

    def _nearest_enemy(self, fx, fy):
        best_sq = float("inf")
        best = (fx, fy)
        for ex, ey, _dash, _parry in self.partner_figures:
            d = (ex - fx) ** 2 + (ey - fy) ** 2
            if d < best_sq:
                best_sq = d
                best = (ex, ey)
        return best

    def request_quit(self):
        self._quit = True

    def queue_fx_hits(self, hits):
        """fxkit hits from the side being simulated (see refresh_battle)."""
        self.sides[self.side_idx].fx_hits.extend(hits)

    def queue_fx_pulls(self, pulls):
        """fxkit pull fields from the side being simulated (see refresh_battle)."""
        self.sides[self.side_idx].fx_pulls.extend(pulls)

    def queue_fx_drags(self, drags):
        """fxkit Drag pushes from the side being simulated (see refresh_battle)."""
        self.sides[self.side_idx].fx_drags.extend(drags)

    @staticmethod
    def _drag_figure(ef, dx, dy):
        """Drag (fxkit drag_step): move a fighter by (dx, dy).  True when that
        ran it into an invisible wall — the screen edge (motion.check_walls'
        margin) or the Battle arena oval (motion.apply_arena_oval) — where it
        is stopped on the wall.  An arc in progress slides with it."""
        t = ef.transform
        ox, oy = t.x, t.y
        t.x += dx
        t.y += dy
        wall = False
        m = 10.0
        if t.x < m or t.x > ef.screen_w - m or t.y < m or t.y > ef.screen_h - m:
            t.x = min(max(t.x, m), float(ef.screen_w) - m)
            t.y = min(max(t.y, m), float(ef.screen_h) - m)
            wall = True
        cx = ef.screen_w * config.ARENA_OVAL_CENTER_X_FRAC
        cy = ef.screen_h * config.ARENA_OVAL_CENTER_Y_FRAC
        rx = ef.screen_w * config.ARENA_OVAL_RADIUS_X_FRAC
        ry = ef.screen_h * config.ARENA_OVAL_RADIUS_Y_FRAC
        if rx > 0.0 and ry > 0.0:
            ex, ey = t.x - cx, t.y - cy
            d = math.hypot(ex / rx, ey / ry)
            if d >= 1.0:
                t.x, t.y = cx + ex / d, cy + ey / d
                wall = True
        c = ef.combat
        if c.arc_repositioning:
            c.arc_center_x += t.x - ox
            c.arc_center_y += t.y - oy
        return wall

    @staticmethod
    def _pull_figure(ef, pulls):
        """Move a fighter toward the centre of every pull field it is inside
        ((x, y, radius, step, falloff): up to step px, less toward the edge
        with falloff), kept on screen.  An arc in progress slides with it."""
        t = ef.transform
        ox, oy = t.x, t.y
        for (px, py, r, step, falloff) in pulls:
            dx, dy = px - t.x, py - t.y
            d = math.hypot(dx, dy)
            if d > r or d < 0.01 or step <= 0:
                continue
            s = min(d, step * (1.0 - 0.65 * falloff * d / r))
            t.x += dx / d * s
            t.y += dy / d * s
        t.x = min(max(t.x, 0.0), float(ef.screen_w))
        t.y = min(max(t.y, 0.0), float(ef.screen_h))
        c = ef.combat
        if c.arc_repositioning:
            c.arc_center_x += t.x - ox
            c.arc_center_y += t.y - oy

    def on_figure_death(self, fig):
        """A figure reached 0 HP.  Solo keeps the historical behaviour (the
        run ends); in battle the fallen fighter is removed and the survivor
        fights on — the winner stays standing."""
        # A Mirror Legion copy dying is never a loss (Solo or Battle): it
        # just dissolves (unique.world_tick removes it next tick).
        if unique.is_clone(fig):
            return
        if self.battle_mode:
            if fig not in self._dead:
                self._dead.append(fig)
        else:
            self.request_quit()

    # --- side binding (one simulation pass per fielded side) ---------------
    def bind_side(self, i):
        s = self.sides[i]
        self.side_idx = i
        self.figures = s.figures
        self.projectiles = s.projectiles
        self.mode_key = s.mode_key
        self.shoot_ticks = s.shoot_ticks
        self.shot_phase = s.shot_phase
        self.shot_pause_ticks = s.shot_pause_ticks
        self.intercepted_bullets = s.intercepted_bullets
        self.partner_figures = s.partner_figures
        self.enemy_fx = s.enemy_fx
        self.enemy_shots = s.enemy_shots
        self.partner_image = s.partner_image
        self.partner_facing = s.partner_facing
        self.partner_gone = s.partner_gone
        self.partner_scale = s.partner_scale
        self.partner_melee = s.partner_melee
        self.partner_state = s.partner_state
        self.enemy_projs = s.enemy_projs
        self.clones = s.clones
        self.hpt_beam_ticks = s.hpt_beam_ticks

    def unbind_side(self):
        s = self.sides[self.side_idx]
        s.figures = self.figures
        s.projectiles = self.projectiles
        s.shoot_ticks = self.shoot_ticks
        s.shot_phase = self.shot_phase
        s.shot_pause_ticks = self.shot_pause_ticks
        s.intercepted_bullets = self.intercepted_bullets
        s.enemy_projs = self.enemy_projs
        s.clones = self.clones
        s.hpt_beam_ticks = self.hpt_beam_ticks

    def refresh_battle(self):
        """Start-of-tick sync: cull fallen fighters, decide battle mode, and
        rebuild each side's read-only snapshot of its opponent.  Snapshots are
        frozen for the whole tick so both sides act on the same picture of
        the world — the same one-tick information boundary the fighters have
        always had, which is what keeps their decisions independent."""
        if self._dead:
            for side in self.sides:
                if any(f in self._dead for f in side.figures):
                    side.figures[:] = [f for f in side.figures
                                       if f not in self._dead]
                    if not side.figures:
                        # The side is eliminated — its in-flight shots (and
                        # any stationary clones) die with it (an unfielded
                        # side is never simulated).
                        side.projectiles.clear()
                        side.clones.clear()
                        side.hpt_beam_ticks = 0
            self._dead.clear()
        self.battle_mode = bool(self.sides[0].figures
                                and self.sides[1].figures)
        for i, side in enumerate(self.sides):
            other = self.sides[1 - i]
            if self.battle_mode:
                side.partner_figures = [
                    (f.x, f.y, bool(f.combat.dashing),
                     bool(f.combat.parrying))
                    for f in other.figures if f.transform.init]
                side.partner_image = [actions.is_image(f)
                                      for f in other.figures if f.transform.init]
                side.partner_facing = [bool(f.transform.facing_left)
                                       for f in other.figures if f.transform.init]
                side.partner_scale = [f.mode.body_scale()
                                      for f in other.figures if f.transform.init]
                side.partner_melee = [bool(f.mode.uses_melee())
                                      for f in other.figures if f.transform.init]
                # Blinked out, or dodging with Invulnerable on: shots,
                # FX and bodies pass where it is.
                side.partner_gone = [blink.gone(f) or dodge.untouchable(f, self.global_tick)
                                     for f in other.figures if f.transform.init]
                side.partner_state = [actions.target_state(f, self.global_tick)
                                      for f in other.figures if f.transform.init]
                # Everything the opponent has out that can hurt, read by the
                # fx_near / projectile_count action conditions:
                # (x, y, tags, airborne).  tags is a tuple; an FX Studio
                # effect with no authored tag goes by its primitive, and the
                # built-in combat FX by their type.  airborne=False marks
                # bodies that stay with their owner (petals, clones), which
                # projectile_count leaves out.
                efx = []
                # Bullets of gun / ki techniques in flight: (inst, i, x, y,
                # vx, vy).  They count as projectiles one by one (and the
                # technique itself, which stays with its owner, no longer
                # does), and become threat-only enemy shots below.
                rounds = []
                for f in other.figures:
                    drv = getattr(f, "fx", None)
                    if drv is not None:
                        for inst in drv.player.insts + drv.clane[0].insts:
                            # A lodged blade is stuck in its target and harmless.
                            if inst.fx["battle"]["deals_damage"] and not inst.dead and inst.lodge is None:
                                tg = (inst.fx.get("tag") or inst.fx.get("prim") or "",)
                                gun = swordfx.shoots(inst)
                                # A gun / ki technique stays with its owner (not
                                # airborne); its bullets are the projectiles.
                                efx.append((inst.x, inst.y, tg, not gun))
                                for (ri, rx, ry, rvx, rvy) in (swordfx.live_points(inst, inst.ps or 1.0) if gun else ()):
                                    efx.append((rx, ry, tg, True))
                                    rounds.append((inst, ri, rx, ry, rvx, rvy))
                    c = f.combat
                    efx.extend((cr.x, cr.y, ("crescent",), True) for cr in c.crescents if cr.alive)
                    efx.extend((uc.x, uc.y, ("ult_crescent",), True) for uc in c.ult_crescents if uc.alive)
                    efx.extend((pt.x, pt.y, ("petal",), False) for pt in c.petals if pt.state != "cooldown")
                    efx.extend((cl.x, cl.y, ("clone",), False) for cl in c.clones)
                efx.extend((cl.x, cl.y, ("clone",), False) for cl in other.clones if cl.alive)
                efx.extend((pr.x, pr.y, ("bullet", "beam") if pr.style == "beam" else ("bullet",), True)
                           for pr in other.projectiles if pr.alive and pr.hit_r_sq > 0.0)
                side.enemy_fx = efx
                # The same projectiles as fxkit.Shot for the auto-projectile
                # tracker: travelling damaging FX instances and real bullets.
                # Each keeps its live object so an interception acts on it
                # at its source (kill_projectile / ending the instance).
                shots = []
                for f in other.figures:
                    drv = getattr(f, "fx", None)
                    if drv is None:
                        continue
                    for inst in drv.player.insts + drv.clane[0].insts:
                        fxd = inst.fx
                        if (fxd["battle"]["deals_damage"]
                                and not inst.dead and inst.age < inst.life and inst.lodge is None
                                and fxd["motion"]["kind"] in ("travel", "homing", "zigzag", "path")
                                and fxd["prim"] not in ("weapon", "ghost", "particles", "pulse")):
                            shots.append(fxkit.Shot(inst.x, inst.y, inst.x - inst.px, inst.y - inst.py,
                                                    "fx", inst,
                                                    blockable=fxd["battle"].get("blockable", True),
                                                    deflectable=fxd["battle"].get("deflectable", True),
                                                    knockback=fxkit.inst_knockback(inst),
                                                    body=fxkit.inst_body(inst)))
                shots.extend(fxkit.Shot(pr.x, pr.y, pr.vx, pr.vy, "bullet", pr)
                             for pr in other.projectiles if pr.alive and pr.hit_r_sq > 0.0)
                # Gun / ki bullets: threat-only shots (retreat steering, Dodge,
                # projectile counts).  Not blockable / deflectable, so the
                # intercepts leave them alone, all but ki barrage orbs, which
                # go by the effect's own flags (rblock / rdeflect); each
                # keeps one RoundRef while it flies (Dodge rolls once per
                # projectile).
                refs = {}
                for (inst, ri, rx, ry, rvx, rvy) in rounds:
                    key = (id(inst), ri)
                    ref = side.round_refs.get(key)
                    if ref is None or ref.inst is not inst:
                        ref = fxkit.RoundRef(inst, ri)
                    refs[key] = ref
                    bt = inst.fx["battle"]
                    shots.append(fxkit.Shot(rx, ry, rvx, rvy, "fx", ref, blockable=False, deflectable=False,
                                            knockback=fxkit.inst_knockback(inst, ri), threat=True,
                                            rblock=bt.get("blockable", True), rdeflect=bt.get("deflectable", True)))
                side.round_refs = refs
                side.enemy_shots = shots
                # Real bullets only (hit_r_sq > 0); cosmetic deflects and
                # splinters can never deal damage across the boundary.  The
                # live Projectile rides along as tuple[8] so an interception
                # (petal / crescent / parry / scatter) truly destroys it.
                # Unique ability Berserker: the shooter's damage bonus.
                side.enemy_projs = [
                    (pr.x, pr.y, pr.vx, pr.vy, pr.r, pr.g, pr.b,
                     float(getattr(pr, "damage", 1.0))
                     * unique.out_mult(getattr(pr, "owner", None)), pr)
                    for pr in other.projectiles
                    if pr.alive and pr.hit_r_sq > 0.0]
            else:
                side.partner_figures = []
                side.partner_image = []
                side.partner_facing = []
                side.partner_gone = []
                side.partner_scale = []
                side.partner_melee = []
                side.partner_state = []
                side.enemy_fx = []
                side.enemy_shots = []
                side.round_refs = {}
                side.enemy_projs = []
                side.intercepted_bullets.clear()
        # Deliver FX Studio hits (fxkit) landed last tick: damage and
        # knockback to the opposing fighter nearest where each hit landed.
        for i, side in enumerate(self.sides):
            hits, side.fx_hits = side.fx_hits, []
            if not hits or not self.battle_mode:
                continue
            other = self.sides[1 - i]
            for (pos, dmg, dx, dy, kb, tag, inst) in hits:
                best = None
                for ef in other.figures:
                    d = (ef.x - pos[0]) ** 2 + (ef.y - pos[1]) ** 2
                    if best is None or d < best[0]:
                        best = (d, ef)
                if best is None or best[0] > 80.0 ** 2:
                    continue
                ef = best[1]
                # Damage cooldown: the fighter is invincible — the hit
                # neither damages nor knocks back.
                if ai.damage_immune(ef, self):
                    continue
                # Defence works like it does against bullets: a parry or an
                # image character's `defend` blocks the hit, and the FX that
                # was blocked ends at its source (non-piercing).  An effect
                # with Blockable off goes straight through every block.
                blockable = inst.fx["battle"].get("blockable", True)
                if blockable and (ef.combat.parrying or actions.blocks_hit(ef)):
                    if not inst.fx["battle"]["pierce"]:
                        inst.age = max(inst.age, inst.life)
                    continue
                actions.note_fx_hit(ef, tag)
                # The fighter whose FX connected (landed_hit condition); a
                # one-fighter side owns it even if the instance has ended.
                owner = next((af for af in side.figures if getattr(af, "fx", None) is not None
                              and (inst in af.fx.player.insts or inst in af.fx.clane[0].insts)),
                             side.figures[0] if len(side.figures) == 1 else None)
                if owner is not None:
                    actions.note_landed(owner)
                # Anti-knockback (FX Studio Damaged): at or above the hit's
                # knockback, the hit still takes HP but neither knocks back
                # nor counts toward the fighter's `defend` conditions.
                resisted = ai.resists_knockback(ef, kb)
                if dmg > 0:
                    if resisted:
                        actions.note_resisted(ef)
                    ai.apply_hp_damage(ef, self, dmg, unblockable=not blockable, kind="fx")
                    if resisted:
                        actions.clear_resisted(ef)
                if kb > 0 and not resisted:
                    # A new hit restarts the slide for its full distance.
                    spd = kb * (1.0 - config.BOUNCE_FRICTION)
                    motion.launch_knockback(ef, dx * spd, dy * spd, self.global_tick)
        # Deliver FX Studio pulls (gigantic meteor, black hole) from last
        # tick: the opposing fighters inside a pull field are drawn toward
        # it; a blinked-out fighter (or one not placed yet, which the
        # snapshots leave out too) is out of reach.
        for i, side in enumerate(self.sides):
            pulls, side.fx_pulls = side.fx_pulls, []
            if not pulls or not self.battle_mode:
                continue
            for ef in self.sides[1 - i].figures:
                if ef.transform.init and not blink.gone(ef):
                    self._pull_figure(ef, pulls)
        # Deliver FX Studio Drag pushes (fxkit drag_step) from last tick: the
        # opposing fighter nearest each push moves with the effect dragging
        # it; one that hits an invisible wall ends that effect at once (a
        # charged blast's orb goes off there).  An effect already ended (its
        # hit blocked, or the dragging orb gone off) drags nothing, and neither
        # does one on a fighter blinked out or mid invulnerable dodge (a
        # damage cooldown only stops the HP, the fighter is still carried).
        for i, side in enumerate(self.sides):
            drags, side.fx_drags = side.fx_drags, []
            if not drags or not self.battle_mode:
                continue
            other = self.sides[1 - i]
            for (pos, dx, dy, inst) in drags:
                if not fxkit.drag_live(inst):
                    continue
                best = None
                for ef in other.figures:
                    d = (ef.x - pos[0]) ** 2 + (ef.y - pos[1]) ** 2
                    if best is None or d < best[0]:
                        best = (d, ef)
                if best is None or best[0] > 80.0 ** 2:
                    continue
                ef = best[1]
                if not ef.transform.init or blink.gone(ef) or dodge.untouchable(ef, self.global_tick):
                    continue
                if self._drag_figure(ef, dx, dy):
                    fxkit.drag_wall(inst)
        # Deliver dash-slash knockback landed last tick to the other side.
        for i, side in enumerate(self.sides):
            other = self.sides[1 - i]
            for f in side.figures:
                if f.combat.hit_pending:
                    f.combat.hit_pending = False
                    if not self.battle_mode:
                        continue
                    # Image characters take a landed dash-slash's HP here: a
                    # plain body bump never costs them HP (CollisionSystem),
                    # and the dashing-contact window it relies on is gone by
                    # the time the struck image fighter's pass reads it, so
                    # melee hits used to only push them.  The struck one is
                    # the enemy nearest the attacker (its melee target).
                    struck = min(other.figures, default=None,
                                 key=lambda e: (e.x - f.x) ** 2 + (e.y - f.y) ** 2)
                    for ef in other.figures:
                        kb_ok = not ai.knockback_immune(ef, self)
                        if (ef is struck and actions.is_image(ef)
                                and not ef.combat.parrying):
                            ai.apply_hp_damage(ef, self)
                        if not kb_ok:
                            continue   # damage cooldown: invincible
                        # A new hit restarts the slide for its full distance.
                        motion.launch_knockback(ef, f.combat.hit_vx, f.combat.hit_vy,
                                                self.global_tick)

    def cinematic_frozen(self, i):
        """True while a figure on ANOTHER fielded side is mid vanish-cut —
        side `i`'s entire pipeline pass is skipped, freezing its figures
        AND its in-flight projectiles until the cut completes.  A side
        running its own vanish-cut is never frozen (own ult takes
        precedence), so two simultaneous cuts play out instead of
        deadlocking each other.  Generic and data-driven: any character
        whose ultimate_playback.style is 'vanish_cut' gets this for free.
        Solo has no opposing fielded side, so nothing freezes — the code
        path is identical in Solo and Battle."""
        own = self.sides[i]
        for f in own.figures:
            if f.combat.vc_phase != 0:
                return False
        for j in self.fielded_sides():
            if j == i:
                continue
            for f in self.sides[j].figures:
                if combat.vc_freezes_world(f.combat):
                    return True
        return False

    def fielded_sides(self):
        return [i for i, s in enumerate(self.sides) if s.figures]

    def all_figures(self):
        for s in self.sides:
            for f in s.figures:
                yield f

    def all_projectiles(self):
        for s in self.sides:
            for pr in s.projectiles:
                yield pr

    def all_clones(self):
        for s in self.sides:
            for c in s.clones:
                yield c

    @property
    def quitting(self):
        return self._quit


class Overlay(QWidget):

    def __init__(self):
        super().__init__()
        win.lower_process_priority()

        sd = os.path.dirname(os.path.abspath(sys.argv[0])) \
            if getattr(sys, "frozen", False) else _asset_dir()
        assets = AssetLibrary(sd)
        if not assets.ok:
            print("No frames loaded! Place Picture*.png and standing*.png "
                  "next to this script.")
            sys.exit(1)

        screen = QApplication.primaryScreen().geometry()
        self.world = World(assets, screen.width(), screen.height())
        self.input = systems.InputSystem()
        self.pipeline = systems.build_pipeline()

        self._pen = QPen()
        self._pen.setCapStyle(Qt.RoundCap)
        self._hp_font = QFont("Consolas", config.HP_DISPLAY_FONT_SIZE, QFont.Bold)

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                            | Qt.Tool | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.showFullScreen()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._safe_tick)
        self._timer.start(config.TICK_MS)

    def _safe_tick(self):
        try:
            self._tick()
        except Exception as e:
            action_log.crash("_tick", e)

    def _tick(self):
        w = self.world
        pos = QCursor.pos()
        w.cursor = (pos.x(), pos.y())

        try:
            self.input.update(w)
        except Exception as e:
            action_log.crash("InputSystem", e)
        if w.quitting:
            self._shutdown()
            return

        # --- PRE-BATTLE MENU (Ctrl+Shift+.): full pause ---
        # Nothing simulates and global_tick stands still, so cooldowns,
        # timers, bullets and HP resume exactly where they were on close.
        # _paint draws the fighters in their idle pose plus the menu.
        if w.prebattle.open:
            w.prebattle.tick += 1
            self.update()
            return

        # --- HIT-STOP: freeze the world for a few ticks on big hits ---
        # Input keeps running; combat, motion, collisions, and bullets all
        # pause — for BOTH sides at once, since they now share one clock.
        # FX (rings, sparks, ghosts) keep animating in paint for punch.
        if w.hitstop_ticks > 0:
            w.hitstop_ticks -= 1
            self.update()
            return

        # One simulation pass per fielded side.  Snapshots are rebuilt once,
        # up front, so both sides read the same frozen picture of each other
        # regardless of pass order — preserving the independent, reactive
        # feel of two fighters thinking for themselves.
        # Clash interaction (laser/clash.py): opposing FX that touch play
        # their clash rule before the sides read each other's snapshots.
        try:
            clash.step(w)
        except Exception as e:
            action_log.crash("clash", e)
        unique.world_tick(w)   # Mirror Legion copies join / dissolve
        w.refresh_battle()
        # FX Studio Time control: each figure's body / FX time scale this
        # tick (None = no time effect running anywhere).
        time_plan = timefx.plan(w)
        for i in w.fielded_sides():
            # Cinematic freeze: a vanish-cut on the other side suspends this
            # side's whole pass (combat, motion, collisions, projectiles).
            # Rendering still paints the frozen pose each frame.
            if w.cinematic_frozen(i):
                continue
            w.bind_side(i)
            if time_plan is not None or clash.holding(w):
                # Time sub-passes: slowed / stopped / sped-up figures, FX
                # and bullets take their own number of steps (timefx.run_side).
                if not timefx.run_side(w, self.pipeline):
                    self._shutdown()
                    return
                w.unbind_side()
                continue
            for system in self.pipeline:
                try:
                    system.update(w)
                except Exception as e:
                    action_log.crash(type(system).__name__, e)
                if w.quitting:
                    self._shutdown()
                    return
            w.unbind_side()

        w.global_tick += 1
        self.update()

    def _shutdown(self):
        QApplication.quit()

    def paintEvent(self, _):
        try:
            self._paint()
        except Exception as e:
            action_log.crash("paintEvent", e)

    def _paint(self):
        w = self.world
        if not w.runner_on:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        # Pre-battle menu: every FX that was mid-flight (bullets, clones,
        # trails, rings, sparks, flashes, clash explosions, fighter FX)
        # stays on screen frozen in place.  It is rendered ONCE into a
        # pixmap — that one pass ages the paint-aged FX by a single frame,
        # exactly like a normal frame — and the pixmap is redrawn unchanged
        # until the menu closes, so nothing ages while paused.  The fighters
        # are drawn on top in their idle pose, then the menu.  Re-captured
        # only if the roster changes (1/2/3/4, F7/F8) so a swapped or
        # retired fighter's FX don't linger.
        # FX Studio "absolute front" FX go in a second frozen pixmap drawn
        # over the idle fighters, so they stay above every character.
        mb = w.prebattle
        if mb.open:
            sig = mb.roster_sig(w)
            if mb.frozen is None or mb.frozen_sig != sig:
                mb.frozen = self._capture_frozen_layer(
                    lambda qp: self._paint_scene(qp, bodies=False, hud=False,
                                                 abs_front=False))
                mb.frozen_front = self._capture_frozen_layer(
                    lambda qp: self._paint_abs_layer(qp, "abs_front"))
                mb.frozen_sig = sig
            p.drawPixmap(0, 0, mb.frozen)
            mb.paint_fighters(p, w)
            p.drawPixmap(0, 0, mb.frozen_front)
            mb.paint_menu(p, w, self._pen)
            p.end()
            return
        self._paint_scene(p)
        p.end()

    def _capture_frozen_layer(self, paint_fn):
        """Whatever paint_fn draws, captured into a transparent pixmap."""
        dpr = self.devicePixelRatioF()
        pm = QPixmap(max(1, int(self.width() * dpr)),
                     max(1, int(self.height() * dpr)))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.transparent)
        qp = QPainter(pm)
        qp.setRenderHint(QPainter.Antialiasing)
        qp.setRenderHint(QPainter.SmoothPixmapTransform)
        try:
            paint_fn(qp)
        finally:
            qp.end()
        return pm

    def _paint_abs_layer(self, p, layer):
        """Every fighter's FX Studio effects on an absolute layer:
        "abs_back" sits under every character, "abs_front" over every
        character (each fighter's plain "behind"/"front" FX only stack
        against their own owner — see Figure.draw).  Identical in Solo
        and Battle."""
        for fig in self.world.all_figures():
            if fig.fx is not None:
                fig.fx.draw(p, fig, layer)

    def _paint_scene(self, p, bodies=True, hud=True, abs_front=True):
        """Everything the game draws in a normal frame.  bodies=False skips
        the fighters' sprites, hud=False the HP readout and notice,
        abs_front=False the absolute-front FX — used by the pre-battle
        menu's frozen FX layers."""
        w = self.world
        self._paint_abs_layer(p, "abs_back")
        for fig in w.all_figures():
            fig.draw(p, self._pen, body=bodies)
        # Every bullet on screen is a live Projectile drawn with its own
        # authored visuals — both sides render identically, no downgraded
        # "enemy dot" pass. Each bullet scales by its own current position.
        for proj in w.all_projectiles():
            if id(proj) in clashfx.HIDDEN:
                continue    # an anchored clash FX draws it meanwhile (laser/clash.py)
            pscale = combat.position_scale(proj.x, proj.y, w.screen_w, w.screen_h)
            proj.draw(p, pscale)
        # HP-threshold stationary clones (glowing-orb marker + orbiting sphere).
        for clone in w.all_clones():
            pscale = combat.position_scale(clone.x, clone.y, w.screen_w, w.screen_h)
            clone.draw(p, pscale)
        # FX Studio "absolute front" FX: above every character and bullet.
        if abs_front:
            self._paint_abs_layer(p, "abs_front")

        # --- Collision impact dots (rainbow radial, fade after hold period) ---
        if w.collision_dots:
            hold = config.COLLISION_DOT_HOLD
            fade = config.COLLISION_DOT_FADE
            total = hold + fade
            rad = config.COLLISION_DOT_RADIUS
            surviving = []
            p.setPen(Qt.NoPen)
            for dot in w.collision_dots:
                dx, dy, age = dot
                if age < hold:
                    alpha = 255
                else:
                    alpha = int(255 * (1.0 - (age - hold) / fade))
                if alpha > 0:
                    # Rainbow hue cycles from 0–360 over the dot's lifetime
                    hue = int((age / total) * 360) % 360
                    # _dot_sprite is cache-keyed by (hue, rad) — rad stays
                    # fixed here (protects the ~50-hue-bucket cache); the
                    # position scale is applied as a paint-time transform
                    # around the cached pixmap instead, never fed into the key.
                    pm, half = _dot_sprite(hue, rad)
                    dscale = combat.position_scale(dx, dy, w.screen_w, w.screen_h)
                    p.save()
                    p.translate(int(dx), int(dy))
                    if dscale != 1.0:
                        p.scale(dscale, dscale)
                    if alpha < 255:
                        p.setOpacity(alpha / 255.0)
                        p.drawPixmap(-half, -half, pm)
                        p.setOpacity(1.0)
                    else:
                        p.drawPixmap(-half, -half, pm)
                    p.restore()
                    dot[2] += 1
                if age + 1 < total:
                    surviving.append(dot)
            w.collision_dots = surviving

        # --- Impact shockwave rings (expand + fade on every landed slash) ---
        if w.impact_rings:
            live = []
            rpen = self._pen
            p.setBrush(Qt.NoBrush)
            for ring in w.impact_rings:
                rx, ry, age, maxr = ring
                t = age / config.IMPACT_RING_LIFETIME
                if t < 1.0:
                    ease = 1.0 - (1.0 - t) ** 3   # fast start, soft finish
                    rad = maxr * ease
                    alpha = int(220 * (1.0 - t))
                    rpen.setColor(QColor(255, 245, 235, alpha))
                    rpen.setWidthF(config.IMPACT_RING_WIDTH * (1.0 - 0.6 * t))
                    p.setPen(rpen)
                    irad = int(rad)
                    p.drawEllipse(int(rx) - irad, int(ry) - irad,
                                  irad * 2, irad * 2)
                ring[2] += 1
                if ring[2] < config.IMPACT_RING_LIFETIME:
                    live.append(ring)
            w.impact_rings = live

        # --- Impact sparks (white-hot streaks bursting from the hit point) ---
        if w.sparks:
            live = []
            spen = self._pen
            for s in w.sparks:
                sx, sy, svx, svy, age, sr, sg, sb = s
                t = age / config.IMPACT_SPARK_LIFETIME
                if t < 1.0:
                    alpha = int(255 * (1.0 - t))
                    spen.setWidthF(2.0)
                    spen.setColor(QColor(min(255, sr + 120),
                                         min(255, sg + 120),
                                         min(255, sb + 120), alpha))
                    p.setPen(spen)
                    p.drawLine(int(sx - svx), int(sy - svy), int(sx), int(sy))
                s[0] += svx
                s[1] += svy
                s[2] *= 0.88
                s[3] *= 0.88
                s[4] += 1
                if s[4] < config.IMPACT_SPARK_LIFETIME:
                    live.append(s)
            w.sparks = live

        # --- Muzzle flashes (bloom at the firing point of every shot) ---
        if w.muzzle_flashes:
            live = []
            p.setPen(Qt.NoPen)
            for fl in w.muzzle_flashes:
                mx, my, age, fr, fg, fb = fl
                t = age / config.MUZZLE_FLASH_LIFETIME
                if t < 1.0:
                    rad = config.MUZZLE_FLASH_RADIUS * (0.4 + 0.6 * t)
                    a = 1.0 - t
                    grad = QRadialGradient(mx, my, rad)
                    grad.setColorAt(0.0, QColor(255, 255, 255, int(230 * a)))
                    grad.setColorAt(0.4, QColor(fr, fg, fb, int(180 * a)))
                    grad.setColorAt(1.0, QColor(fr, fg, fb, 0))
                    p.setBrush(grad)
                    ir = int(rad)
                    p.drawEllipse(int(mx) - ir, int(my) - ir, ir * 2, ir * 2)
                fl[2] += 1
                if fl[2] < config.MUZZLE_FLASH_LIFETIME:
                    live.append(fl)
            w.muzzle_flashes = live

        # --- Clash explosions (laser/clashfx.py) — above the impact FX ---
        if w.clash_fx:
            sw, sh = w.screen_w, w.screen_h
            clashfx.draw_all(p, w, lambda x, y: combat.position_scale(x, y, sw, sh))

        # --- Damage numbers (laser/dmgnum.py) — combined 2 s totals ---
        if w.damage_numbers:
            sw, sh = w.screen_w, w.screen_h
            dmgnum.draw_all(p, w, lambda x, y: combat.position_scale(x, y, sw, sh))

        if not hud:
            return

        # --- HP readout — bottom-right, one entry per figure (both sides) ---
        _hp_rows = [(si, fig) for si, s in enumerate(w.sides)
                    for fig in s.figures if not unique.is_clone(fig)]
        if _hp_rows:
            p.setFont(self._hp_font)
            fm = p.fontMetrics()
            line_h = fm.height() + 4
            base_y = w.screen_h - config.HP_DISPLAY_MARGIN_B
            _battle = w.battle_mode
            for idx, (side_i, fig) in enumerate(_hp_rows):
                hp_val = fig.personality.hp
                max_hp = fig.personality.max_hp
                label = (f"P{side_i + 1} {hp_val} HP" if _battle
                         else f"{hp_val} HP")
                # A Rig Forge character without its FX Studio file plays with
                # no FX at all — say so instead of failing silently.
                _ch = getattr(fig.mode, "character", None) or {}
                if _ch.get("_package") and not _ch.get("_fxkit"):
                    label += "  (no FX file)"
                text_w = fm.horizontalAdvance(label)
                _hp_offset = 0 if fig.mode.uses_melee() else 70
                draw_x = w.screen_w - text_w - config.HP_DISPLAY_MARGIN_R - _hp_offset
                draw_y = base_y - idx * line_h
                # Pick colour from the figure's lut midpoint
                r2, g2, b2 = fig.lut[128]
                # Dim text slightly when low HP (below 25 %)
                alpha = 255 if hp_val > max_hp * 0.25 else 160
                # Glow pass (offset shadow for neon feel)
                p.setPen(QColor(r2, g2, b2, max(30, alpha // 4)))
                p.drawText(draw_x - 1, draw_y + 1, label)
                # Main text
                p.setPen(QColor(r2, g2, b2, alpha))
                p.drawText(draw_x, draw_y, label)

        # --- On-screen notice (F5 reload result) ---
        _txt, _left = w.notice
        if _left > 0 and _txt:
            w.notice = (_txt, _left - 1)
            p.setFont(self._hp_font)
            p.setPen(QColor(0, 0, 0, 160))
            p.drawText(21, 41, _txt)
            p.setPen(QColor(255, 255, 255, 230))
            p.drawText(20, 40, _txt)

    def closeEvent(self, event):
        action_log.close()
        super().closeEvent(event)


def _asset_dir():
    """Directory the sprite PNGs live in — the project root (one above laser/)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    overlay = Overlay()
    ret = app.exec_()
    sys.exit(ret)




