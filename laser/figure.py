"""
Figure — one companion.  A thin entity that composes the components and a mode
reference, owns its facing maths, and orchestrates drawing.  All behaviour lives
in the systems (motion, combat, ...) which read and mutate these components.
"""

import math

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPen, QColor

from . import config
from . import combat as _combat
from .components import (Transform, MotionState, TrailComponent,
                         Renderable, Combatant, Personality, JumpState)


class Figure:
    __slots__ = ("transform", "motion", "trail", "render", "combat",
                 "personality", "mode", "lut", "index",
                 "screen_w", "screen_h", "jump")

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
        self.trail = TrailComponent(lut)
        self.render = Renderable(bundle, spd["anim_speed"], spd["idle_anim_speed"],
                                  outline_glow=spd.get("outline_glow"))
        self.combat = Combatant()
        self.personality = Personality(mode.key)
        self.jump = JumpState()

    # convenience aliases ---------------------------------------------------
    @property
    def x(self):
        return self.transform.x

    @property
    def y(self):
        return self.transform.y

    @property
    def z(self):
        """Height above the ground plane (px, 0 = grounded). Render-only —
        never used for combat/collision math, which stay on Transform x/y."""
        return self.jump.z

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
        self.render.set_bundle(bundle)
        self.combat.reset()
        self.jump.reset()
        self.trail.clear()
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
        z = self.jump.z

        # --- Ground shadow: drawn at the TRUE ground position, never offset —
        # this is the one thing that's meant to stay anchored to the ground,
        # as a height cue. Everything else about this figure (afterimages,
        # trail, sprite, outline glow, crescents, petals, clones, particle
        # bursts) is shifted together by the same painter-level translate
        # below, so the whole visual identity floats as one cohesive unit
        # instead of the sprite splitting away from its own FX. Combat/hit
        # math never touches the painter, so this is purely cosmetic in
        # both Solo and Battle. ---
        if z > 0.5:
            shadow_t = max(config.JUMP_SHADOW_MIN_SCALE,
                            1.0 - z / config.JUMP_SHADOW_FALLOFF_PX)
            srx = config.JUMP_SHADOW_BASE_RADIUS_X * shadow_t
            sry = config.JUMP_SHADOW_BASE_RADIUS_Y * shadow_t
            p.save()
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, int(config.JUMP_SHADOW_MAX_ALPHA * shadow_t)))
            p.drawEllipse(int(self.transform.x - srx), int(self.transform.y - sry),
                          int(srx * 2), int(sry * 2))
            p.restore()

        p.save()
        if z > 0.5:
            p.translate(0, -z)

        # --- Dash afterimages: crimson speed-ghosts, drawn behind everything ---
        c0 = self.combat
        if c0.afterimages:
            live = []
            for ghost in c0.afterimages:
                gx, gy, frame, age = ghost
                alpha = config.AFTERIMAGE_ALPHA * (1.0 - age / config.AFTERIMAGE_LIFETIME)
                if alpha > 3:
                    pm = _combat.silhouette(frame)
                    p.setOpacity(alpha / 255.0)
                    p.drawPixmap(int(gx) - pm.width() // 2,
                                 int(gy) - pm.height() // 2, pm)
                ghost[3] += 1
                if ghost[3] < config.AFTERIMAGE_LIFETIME:
                    live.append(ghost)
            p.setOpacity(1.0)
            c0.afterimages = live

        self.trail.draw(p, pen, self.motion.follow)

        frame = self._current_frame()
        if frame is not None:
            og = self.render.outline_glow
            if og is not None:
                rgb, radius, opacity = og
                silh = _combat.silhouette(frame, rgb)
                sw, sh = silh.width() // 2, silh.height() // 2
                p.save()
                p.translate(self.transform.x, self.transform.y)
                if self.motion.rotate:
                    p.rotate(self.transform.angle)
                p.setOpacity(opacity / 255.0)
                steps = config.OUTLINE_GLOW_STEPS
                for i in range(steps):
                    ang = (2 * math.pi * i) / steps
                    ox = math.cos(ang) * radius
                    oy = math.sin(ang) * radius
                    p.drawPixmap(int(ox) - sw, int(oy) - sh, silh)
                p.setOpacity(1.0)
                p.restore()
            p.save()
            p.translate(self.transform.x, self.transform.y)
            if self.motion.rotate:
                p.rotate(self.transform.angle)
            p.drawPixmap(-frame.width() // 2, -frame.height() // 2, frame)
            p.restore()

        if self.combat.crescents:
            cpen = QPen()
            cpen.setCapStyle(Qt.RoundCap)
            cpen.setJoinStyle(Qt.RoundJoin)
            for c in self.combat.crescents:
                c.draw(p, cpen, lut=self.lut, flow_off=self.trail.flow_off)

        if self.combat.ult_crescents:
            upen = QPen()
            upen.setCapStyle(Qt.RoundCap)
            upen.setJoinStyle(Qt.RoundJoin)
            for uc in self.combat.ult_crescents:
                uc.draw(p, upen)

        if self.combat.petals:
            for pt in self.combat.petals:
                pt.draw(p)

        # --- Clones: autonomous ghosts (special_ability preset 'clone') ---
        if self.combat.clones:
            for cl in self.combat.clones:
                cl.draw(p, self.render.bundle)

        if self.combat.particle_bursts:
            for bp in self.combat.particle_bursts:
                bp.draw(p)

        p.restore()

