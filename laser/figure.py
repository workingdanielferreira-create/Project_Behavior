"""
Figure — one companion.  A thin entity that composes the components and a mode
reference, owns its facing maths, and orchestrates drawing.  All behaviour lives
in the systems (motion, combat, ...) which read and mutate these components.
"""

import math

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPen

from . import config
from . import combat as _combat
from .components import (Transform, MotionState, TrailComponent,
                         Renderable, Combatant, Personality)


class Figure:
    __slots__ = ("transform", "motion", "trail", "render", "combat",
                 "personality", "mode", "lut", "index",
                 "screen_w", "screen_h")

    def __init__(self, mode, bundle, lut, index, screen_w, screen_h):
        spd = mode.speeds()
        ox, oy = config.FIGURE_OFFSETS[index % len(config.FIGURE_OFFSETS)]

        self.mode = mode
        self.lut = lut
        self.index = index
        self.screen_w = screen_w
        self.screen_h = screen_h

        self.transform = Transform()
        self.motion = MotionState(
            speed=spd["chase_speed"] + (index % 3) * 0.4,
            follow_speed=spd["follow_speed"] + (index % 3) * 0.5,
            offset_x=ox, offset_y=oy,
            rotate=config.ROTATE_TO_FACING_ENABLED,
        )
        self.trail = TrailComponent(lut, gradient=spd.get("trail_gradient"))
        self.render = Renderable(bundle, spd["anim_speed"], spd["idle_anim_speed"],
                                  outline_glow=spd.get("outline_glow"),
                                  afterimage_rgb=spd.get("afterimage_rgb"))
        self.combat = Combatant()
        self.personality = Personality(mode.key)

    # convenience aliases ---------------------------------------------------
    @property
    def x(self):
        return self.transform.x

    @property
    def y(self):
        return self.transform.y

    @property
    def dashing(self):
        return self.combat.dashing

    # mode switching --------------------------------------------------------
    def set_mode(self, mode, bundle):
        self.mode = mode
        spd = mode.speeds()
        self.motion.speed = spd["chase_speed"] + (self.index % 3) * 0.4
        self.motion.follow_speed = spd["follow_speed"] + (self.index % 3) * 0.5
        self.render.anim_speed = spd["anim_speed"]
        self.render.idle_anim_speed = spd["idle_anim_speed"]
        self.render.outline_glow = spd.get("outline_glow")
        self.render.afterimage_rgb = spd.get("afterimage_rgb")
        self.render.set_bundle(bundle)
        self.combat.reset()
        self.trail.clear()
        self.trail.gradient = spd.get("trail_gradient")
        # Re-initialise HP for the new mode
        _mhp = config.MODE_CONFIGS.get(mode.key, {}).get("max_hp", 30)
        self.personality.max_hp = _mhp
        self.personality.hp = _mhp

    # facing / motion classification ---------------------------------------
    def face(self, ox, oy):
        t = self.transform
        dx, dy = t.x - ox, t.y - oy
        d_sq = dx * dx + dy * dy
        self.render.is_moving = d_sq > self.motion.min_move_sq
        if dx < -0.001:
            t.facing_left = True
        elif dx > 0.001:
            t.facing_left = False
        if self.motion.rotate and d_sq > 0.01:
            a = math.degrees(math.atan2(dy, dx))
            if -90 <= a <= 90:
                # Right-facing (unmirrored) sprite: rotation angle equals the
                # travel angle directly.
                t.angle = a
            else:
                # Left-facing sprite uses the horizontally-mirrored frame set,
                # whose local "forward" axis is -x instead of +x. Rotating a
                # mirrored image by the raw travel angle flips the vertical
                # component of the lean (2026-07-10 bug: character faced down
                # while moving up, etc). The correct angle for the mirrored
                # frame is the travel angle offset by 180 degrees, normalised
                # back into (-180, 180].
                t.angle = (a - 180) if a > 0 else (a + 180)
        else:
            t.angle = 0.0

    # position-based sprite scaling ------------------------------------------
    def _position_scale(self):
        """Bilinear scale factor from the figure's screen position.

        transform.x/y are already screen-pixel coordinates (see
        motion.check_walls), so no world/frame conversion is needed. Thin
        wrapper over combat.position_scale — the same shared formula every
        FX system uses, so Solo and Battle stay identical automatically
        (same figure, same math, no mode branching). Visual only — never
        touches hurtbox_radius or attack radius.
        """
        return _combat.position_scale(self.transform.x, self.transform.y,
                                       self.screen_w, self.screen_h)

    # drawing ---------------------------------------------------------------
    def _current_frame(self):
        b = self.render.bundle
        t = self.transform
        c = self.combat
        m = self.motion
        left = t.facing_left

        if c.slashing and b.slash:
            fs = b.slash_flipped if left else b.slash
            return fs[min(c.slash_idx, len(fs) - 1)]
        if m.bouncing and b.slide is not None:
            return b.slide if left else b.slide_flipped
        if m.bounce_ending and b.slide2 is not None:
            return b.slide2 if left else b.slide2_flipped
        if self.render.is_moving and b.run:
            fs = b.run_flipped if left else b.run
            return fs[self.render.run_idx % len(fs)]
        if b.idle:
            fs = b.idle_flipped if left else b.idle
            return fs[self.render.idle_idx % len(fs)]
        if b.run:
            fs = b.run_flipped if left else b.run
            return fs[self.render.run_idx % len(fs)]
        return None

    def draw(self, p, pen):
        # --- Dash afterimages: crimson speed-ghosts, drawn behind everything ---
        c0 = self.combat
        if c0.afterimages:
            live = []
            for ghost in c0.afterimages:
                gx, gy, frame, age = ghost
                alpha = config.AFTERIMAGE_ALPHA * (1.0 - age / config.AFTERIMAGE_LIFETIME)
                if alpha > 3:
                    pm = _combat.silhouette(frame, self.render.afterimage_rgb)
                    p.setOpacity(alpha / 255.0)
                    p.drawPixmap(int(gx) - pm.width() // 2,
                                 int(gy) - pm.height() // 2, pm)
                ghost[3] += 1
                if ghost[3] < config.AFTERIMAGE_LIFETIME:
                    live.append(ghost)
            p.setOpacity(1.0)
            c0.afterimages = live

        fig_pscale = self._position_scale()
        self.trail.draw(p, pen, self.motion.follow, fig_pscale)

        # --- Sprite-line emitter FX (JSON `sprite_emitter`): pulsing glow
        # dots pinned to the current frame's colour-matched line points
        # ("glow" sources) plus the live rising/fading particles spawned by
        # "emit" sources (world-space, so they linger where emitted while
        # the figure moves on). Drawn before the sprite frame so the
        # particle layers sit behind the character. Cheap no-ops without
        # the block. ---
        _combat.draw_sprite_emitter_glow(self, p, self.render.anim_tick)
        if self.combat.sprite_particles:
            for sp in self.combat.sprite_particles:
                # These detach and drift on their own, so they scale by
                # their OWN current position, not the figure's.
                sp.draw(p, _combat.position_scale(sp.x, sp.y,
                                                   self.screen_w, self.screen_h))

        frame = self._current_frame()
        # Vanish-cut ultimate: the figure is 'gone' during the cut — the
        # sprite (and its glow) skip drawing while vc_hidden; crescent
        # slashes / sparks / impact FX below still render.
        if frame is not None and not c0.vc_hidden:
            pscale = fig_pscale
            og = self.render.outline_glow
            if og is not None:
                rgb, radius, opacity = og
                silh = _combat.silhouette(frame, rgb)
                sw, sh = silh.width() // 2, silh.height() // 2
                p.save()
                p.translate(self.transform.x, self.transform.y)
                if self.motion.rotate:
                    p.rotate(self.transform.angle)
                if pscale != 1.0:
                    p.scale(pscale, pscale)
                p.setOpacity(opacity / 255.0)
                steps = config.OUTLINE_GLOW_STEPS
                for i in range(steps):
                    ang = (2 * math.pi * i) / steps
                    ox = math.cos(ang) * radius
                    oy = math.sin(ang) * radius
                    p.drawPixmap(round(ox) - sw, round(oy) - sh, silh)
                p.setOpacity(1.0)
                p.restore()
            p.save()
            p.translate(self.transform.x, self.transform.y)
            if self.motion.rotate:
                p.rotate(self.transform.angle)
            if pscale != 1.0:
                p.scale(pscale, pscale)
            p.drawPixmap(-frame.width() // 2, -frame.height() // 2, frame)
            p.restore()

        if self.combat.crescents:
            cpen = QPen()
            cpen.setCapStyle(Qt.RoundCap)
            cpen.setJoinStyle(Qt.RoundJoin)
            for c in self.combat.crescents:
                # Crescents travel outward from the figure, so they scale
                # by their own current position.
                cscale = _combat.position_scale(c.x, c.y,
                                                 self.screen_w, self.screen_h)
                c.draw(p, cpen, lut=self.lut, flow_off=self.trail.flow_off,
                       pscale=cscale)

        if self.combat.ult_crescents:
            upen = QPen()
            upen.setCapStyle(Qt.RoundCap)
            upen.setJoinStyle(Qt.RoundJoin)
            for uc in self.combat.ult_crescents:
                uscale = _combat.position_scale(uc.x, uc.y,
                                                 self.screen_w, self.screen_h)
                uc.draw(p, upen, pscale=uscale)

        if self.combat.petals:
            for pt in self.combat.petals:
                # Petals orbit the figure but at some radius from it, so
                # they still get their own position's scale.
                pscale_pt = _combat.position_scale(pt.x, pt.y,
                                                    self.screen_w, self.screen_h)
                pt.draw(p, pscale_pt)

        # --- Clones: autonomous ghosts (special_ability preset 'clone') ---
        if self.combat.clones:
            for cl in self.combat.clones:
                cscale = _combat.position_scale(cl.x, cl.y,
                                                 self.screen_w, self.screen_h)
                cl.draw(p, self.render.bundle, cscale)

        if self.combat.particle_bursts:
            for bp in self.combat.particle_bursts:
                bpscale = _combat.position_scale(bp.x, bp.y,
                                                  self.screen_w, self.screen_h)
                bp.draw(p, bpscale)


