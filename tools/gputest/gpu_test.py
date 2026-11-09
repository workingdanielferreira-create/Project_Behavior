"""
GPU overlay test - is a GPU canvas (Skia on OpenGL, in a GLFW window) a
workable replacement for the game's QPainter overlay on THIS machine?

Run it with "GPU Test.bat" in the game folder.  It takes about a minute,
changes nothing in the game, and writes gpu_test_result.txt next to the
.bat.  It answers the open questions from the renderer review:

  1. Graphics card: does OpenGL run on real hardware here (not a software
     fallback, as on many remote / virtual desktops)?
  2. Overlay: can the window be see-through, click-through and always on top
     without admin rights, like the game's overlay?
  3. Speed: how long does a frame take for loads like the game's (additive
     glows, anti-aliased polygons, the big-ball warp) and far heavier ones?
  4. Baseline: the same loads painted with QPainter on the CPU (what the
     game does today), for a like-for-like comparison.
  5. Qt: do a Qt window and the GLFW overlay run together in one process
     (the start menu would stay Qt)?

While it runs you should see glowing dots over your desktop and still be
able to click the windows underneath.  Nothing here is game code: the loads
are stand-ins sized from the profile of the real game (about 570 polygons
and a 48 x 8 cell warp of two fullscreen layers per frame).
"""

import ctypes
import ctypes.util
import math
import os
import platform
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
RESULT = os.path.join(ROOT, "gpu_test_result.txt")

MEASURE_S = float(os.environ.get("PB_GPUTEST_S", 4.0))        # measured time per stage
WARMUP_FRAMES = 30     # frames thrown away at the start of a stage
FRAME_SETS = 4         # pre-built animation frames (keeps Python maths out of the timing)
WARP_COLS, WARP_BANDS = 48, 8      # the game's planet_ball_cols / planet_ball_bands
SOFTWARE = ("gdi generic", "llvmpipe", "softpipe", "swiftshader", "basic render", "software")

# name, glows, how the glows are drawn, polygons, big-ball warp
#   naive = one gradient + one draw call per glow (a line-for-line port of today's code)
#   atlas = every glow in ONE batched call (what a tuned port would do)
STAGES = (
    ("A  game-like load, no warp", 500, "naive", 570, False),
    ("B  game-like load + ball warp", 500, "naive", 570, True),
    ("C  4x glows + ball warp", 2000, "naive", 570, True),
    ("B2 game-like load batched + warp", 500, "atlas", 570, True),
    ("D  10,000 batched glows + warp", 10000, "atlas", 570, True),
    ("E  40,000 batched glows", 40000, "atlas", 0, False),
)
CPU_STAGES = (0, 1, 2)     # stages repeated with QPainter on the CPU
CPU_FRAMES = 25

OUT = []


def say(line=""):
    OUT.append(line)
    print(line, flush=True)


def stats(ms):
    a = sorted(ms)
    n = len(a)
    mean = sum(a) / n
    return mean, a[int(n * 0.95)] if n > 1 else a[0], 1000.0 / mean if mean > 0 else 0.0


# ---------------------------------------------------------------- the load
def build_frames(w, h, glows, polys):
    """FRAME_SETS frames of (glows, polygons), deterministic."""
    rng = random.Random(1234)
    pal = ((255, 60, 90), (60, 200, 255), (255, 190, 40), (150, 110, 255), (80, 255, 160))
    g = [(rng.uniform(0, w), rng.uniform(0, h), rng.uniform(6, 34), rng.uniform(0, 6.28),
          rng.uniform(20, 160), pal[rng.randrange(len(pal))]) for _ in range(glows)]
    p = [(rng.uniform(0, w), rng.uniform(0, h), rng.uniform(8, 60), rng.uniform(0, 6.28),
          pal[rng.randrange(len(pal))]) for _ in range(polys)]
    frames = []
    for k in range(FRAME_SETS):
        t = k / float(FRAME_SETS) * 6.28318
        gl = [(x + math.cos(ph + t) * amp, y + math.sin(ph * 1.7 + t) * amp, r, c)
              for (x, y, r, ph, amp, c) in g]
        pl = []
        for (x, y, r, ph, c) in p:
            a0 = ph + t
            pl.append(([(x + math.cos(a0 + i * 1.2566) * r * (1.0 if i % 2 else 0.55),
                         y + math.sin(a0 + i * 1.2566) * r * (1.0 if i % 2 else 0.55))
                        for i in range(5)], c))
        frames.append((gl, pl))
    return frames


def warp_grid(w, h):
    """The big ball's mapping (laser/ballwarp.py, simplified): source point ->
    drawn point, as a list of (src quad corners, dst quad corners)."""
    px, py = w * 0.5, h * 0.62
    rx, ry = 3.0 * w, py - 0.08 * h

    def bend(x, y):
        lon = (x - px) / rx
        if y >= py:
            return px + rx * math.sin(lon), y
        lat = min(1.0, (py - y) / ry) * math.pi / 2
        return px + rx * math.sin(lon) * math.cos(lat), py - ry * math.sin(lat)

    ys = [py * j / WARP_BANDS for j in range(WARP_BANDS + 1)] + [float(h)]
    xs = [w * i / float(WARP_COLS) for i in range(WARP_COLS + 1)]
    return xs, ys, bend


# ---------------------------------------------------------------- GL bits
def gl_library():
    if sys.platform == "win32":
        return ctypes.windll.opengl32
    name = ctypes.util.find_library("GL")
    return ctypes.CDLL(name) if name else None


def gl_strings(gl):
    out = {}
    if gl is None:
        return out
    gl.glGetString.restype = ctypes.c_char_p
    for key, code in (("vendor", 0x1F00), ("renderer", 0x1F01), ("version", 0x1F02)):
        try:
            v = gl.glGetString(code)
            out[key] = v.decode("ascii", "replace") if v else "?"
        except Exception:
            out[key] = "?"
    return out


def overlay_checks(glfw, window):
    """What the window manager actually gave us."""
    res = {"see-through": bool(glfw.get_window_attrib(window, glfw.TRANSPARENT_FRAMEBUFFER)),
           "always on top": bool(glfw.get_window_attrib(window, glfw.FLOATING)),
           "click-through": bool(glfw.get_window_attrib(window, glfw.MOUSE_PASSTHROUGH))}
    if sys.platform == "win32":
        try:
            u = ctypes.windll.user32
            hwnd = glfw.get_win32_window(window)
            ex = u.GetWindowLongW(hwnd, -20)
            res["always on top"] = bool(ex & 0x00000008)           # WS_EX_TOPMOST

            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
            u.WindowFromPoint.restype = ctypes.c_void_p
            x, y = glfw.get_window_pos(window)
            w, h = glfw.get_window_size(window)
            under = u.WindowFromPoint(POINT(x + w // 2, y + h // 2))
            # A click in the middle must land on some OTHER window.
            res["click-through"] = bool(under) and int(under) != int(hwnd)
        except Exception as e:
            say("  (could not query Windows for the overlay flags: %s)" % e)
    return res


# ---------------------------------------------------------------- GPU side
class GpuTest:

    def __init__(self):
        import glfw
        import skia
        self.glfw, self.skia = glfw, skia
        if not glfw.init():
            raise RuntimeError("GLFW could not start")
        mon = glfw.get_primary_monitor()
        mode = glfw.get_video_mode(mon)
        mx, my = glfw.get_monitor_pos(mon)
        sw, sh = mode.size.width, mode.size.height
        glfw.window_hint(glfw.TRANSPARENT_FRAMEBUFFER, True)
        glfw.window_hint(glfw.DECORATED, False)
        glfw.window_hint(glfw.FLOATING, True)
        glfw.window_hint(glfw.MOUSE_PASSTHROUGH, True)
        glfw.window_hint(glfw.FOCUSED, False)
        glfw.window_hint(glfw.FOCUS_ON_SHOW, False)
        glfw.window_hint(glfw.RESIZABLE, False)
        glfw.window_hint(glfw.STENCIL_BITS, 8)
        glfw.window_hint(glfw.ALPHA_BITS, 8)
        # One pixel taller than the screen: an exactly-screen-sized borderless
        # GL window can be switched to exclusive fullscreen by the driver,
        # which drops the see-through background.
        self.window = glfw.create_window(sw, sh + 1, "Project Behavior GPU test", None, None)
        if not self.window:
            glfw.terminate()
            raise RuntimeError("could not create an OpenGL window")
        glfw.set_window_pos(self.window, mx, my)
        glfw.make_context_current(self.window)
        glfw.swap_interval(0)          # no vsync: measure the real cost
        self.gl = gl_library()
        self.info = gl_strings(self.gl)
        self.w, self.h = glfw.get_framebuffer_size(self.window)
        self.screen = (sw, sh)

        self.ctx = skia.GrDirectContext.MakeGL()
        if self.ctx is None:
            raise RuntimeError("Skia could not use this OpenGL context")
        target = skia.GrBackendRenderTarget(self.w, self.h, 0, 8,
                                            skia.GrGLFramebufferInfo(0, 0x8058))   # GL_RGBA8
        self.surface = skia.Surface.MakeFromBackendRenderTarget(
            self.ctx, target, skia.kBottomLeft_GrSurfaceOrigin,
            skia.kRGBA_8888_ColorType, skia.ColorSpace.MakeSRGB())
        if self.surface is None:
            raise RuntimeError("Skia could not draw to the window")
        self._target = target
        ii = skia.ImageInfo.MakeN32Premul(self.w, self.h)
        self.layers = [skia.Surface.MakeRenderTarget(self.ctx, skia.Budgeted.kNo, ii) for _ in range(2)]
        if None in self.layers:
            raise RuntimeError("Skia could not create an offscreen GPU layer")
        # The warp reads each layer straight from its texture.  (v1 took a
        # snapshot of the layer every frame, which cost hundreds of ms and
        # made the warp stages look far slower than they are.)
        self.layer_paints = None
        try:
            lp = []
            for layer in self.layers:
                bt = layer.getBackendTexture(skia.Surface.kFlushRead_BackendHandleAccess)
                im = skia.Image.MakeFromTexture(self.ctx, bt, skia.kBottomLeft_GrSurfaceOrigin,
                                                skia.kRGBA_8888_ColorType, skia.kPremul_AlphaType, None)
                p = skia.Paint()
                p.setShader(im.makeShader(skia.TileMode.kClamp, skia.TileMode.kClamp,
                                          skia.SamplingOptions(skia.FilterMode.kLinear)))
                lp.append((p, im))
            self.layer_paints = lp
        except Exception as e:
            say("  (direct layer textures not available: %s - using snapshots, the warp will be slow)" % e)

        self.plus = skia.Paint(AntiAlias=True, BlendMode=skia.BlendMode.kPlus)
        self.plus_flat = skia.Paint(AntiAlias=True, BlendMode=skia.BlendMode.kPlus)
        self.sampling = skia.SamplingOptions(skia.FilterMode.kLinear)
        self.font = skia.Font(skia.Typeface("Consolas"), 20)
        self.text = skia.Paint(AntiAlias=True, Color=skia.ColorWHITE)
        self.panel = skia.Paint(AntiAlias=True, Color=skia.Color(0, 0, 0, 190))
        self.edge = skia.Paint(AntiAlias=True, Color=skia.Color(60, 200, 255, 255),
                               Style=skia.Paint.kStroke_Style, StrokeWidth=4)
        self._make_atlas()
        self._make_warp()

        self.stage = -1
        self.results = []
        self.checks = None
        self.frame = 0
        self.stopped = False
        self.hud = ""
        self._next_stage()

    # -- one-off resources
    def _make_atlas(self):
        skia = self.skia
        s = skia.Surface.MakeRenderTarget(self.ctx, skia.Budgeted.kNo, skia.ImageInfo.MakeN32Premul(64, 64))
        c = s.getCanvas()
        c.clear(skia.ColorTRANSPARENT)
        p = skia.Paint(AntiAlias=True)
        p.setShader(skia.GradientShader.MakeRadial((32, 32), 32, [0xFFFFFFFF, 0x00FFFFFF]))
        c.drawCircle(32, 32, 32, p)
        self.atlas = s.makeImageSnapshot()
        self.atlas_rect = skia.Rect.MakeWH(64, 64)

    def _make_warp(self):
        skia = self.skia
        xs, ys, bend = warp_grid(self.w, self.h)
        pos, tex, idx = [], [], []
        nx = len(xs)
        for y in ys:
            for x in xs:
                bx, by = bend(x, y)
                pos.append(skia.Point(bx, by))
                tex.append(skia.Point(x, y))
        for j in range(len(ys) - 1):
            for i in range(nx - 1):
                a = j * nx + i
                idx += [a, a + 1, a + nx, a + 1, a + nx + 1, a + nx]
        self.warp = skia.Vertices(skia.Vertices.kTriangles_VertexMode, pos, tex, None, idx)

    # -- stages
    def _next_stage(self):
        self.stage += 1
        if self.stage >= len(STAGES):
            return
        name, glows, how, polys, warp = STAGES[self.stage]
        say("  running %s ..." % name)
        self.frames = build_frames(self.w, self.h, glows, polys)
        self.batches = None
        if how == "atlas":
            skia = self.skia
            self.batches = []
            for gl, _pl in self.frames:
                xf = [skia.RSXform(r / 32.0, 0.0, x - r, y - r) for (x, y, r, _c) in gl]
                col = [skia.Color(c[0], c[1], c[2], 255) for (_x, _y, _r, c) in gl]
                self.batches.append((xf, [self.atlas_rect] * len(gl), col))
        self.times = []
        self.py_ms = 0.0
        self.count = 0
        self.t_stage = None

    def _content(self, canvas, k, part=None):
        """The glows + polygons of frame k (part 0 / 1 = the half that goes
        in the ground / air layer when the warp is on)."""
        skia = self.skia
        gl, pl = self.frames[k]
        paint = self.plus          # glows (gets a gradient per glow)
        flat = self.plus_flat      # polygons (plain colour)
        if part is not None:
            gl, pl = gl[part::2], pl[part::2]
        for pts, c in pl:
            path = skia.Path()
            path.moveTo(*pts[0])
            for q in pts[1:]:
                path.lineTo(*q)
            path.close()
            flat.setColor(skia.Color(c[0], c[1], c[2], 150))
            canvas.drawPath(path, flat)
        if self.batches is not None:
            xf, rects, col = self.batches[k]
            if part is not None:
                xf, rects, col = xf[part::2], rects[part::2], col[part::2]
            canvas.drawAtlas(self.atlas, xf, rects, col, skia.BlendMode.kModulate,
                             self.sampling, None, self.plus_plain)
        else:
            mk = skia.GradientShader.MakeRadial
            for x, y, r, c in gl:
                paint.setShader(mk((x, y), r, [skia.Color(c[0], c[1], c[2], 255),
                                               skia.Color(c[0], c[1], c[2], 0)]))
                canvas.drawCircle(x, y, r, paint)

    @property
    def plus_plain(self):
        p = getattr(self, "_pp", None)
        if p is None:
            p = self._pp = self.skia.Paint(BlendMode=self.skia.BlendMode.kPlus)
        return p

    def _draw(self):
        skia = self.skia
        canvas = self.surface.getCanvas()
        canvas.clear(skia.ColorTRANSPARENT)
        k = self.frame % FRAME_SETS
        if STAGES[self.stage][4]:
            for part, layer in enumerate(self.layers):
                lc = layer.getCanvas()
                lc.clear(skia.ColorTRANSPARENT)
                self._content(lc, k, part)
                if self.layer_paints is not None:
                    tf = time.perf_counter()
                    layer.flushAndSubmit()     # graphics-card work, not Python's
                    self.flush_s += time.perf_counter() - tf
                    canvas.drawVertices(self.warp, self.layer_paints[part][0])
                else:
                    img = layer.makeImageSnapshot()
                    wp = skia.Paint()
                    wp.setShader(img.makeShader(skia.TileMode.kClamp, skia.TileMode.kClamp, self.sampling))
                    canvas.drawVertices(self.warp, wp)
        else:
            self._content(canvas, k)
        # HUD: border (shows the overlay covers the screen) + status
        sw, sh = self.screen
        canvas.drawRect(skia.Rect.MakeLTRB(2, 2, self.w - 2, min(self.h, sh) - 2), self.edge)
        canvas.drawRoundRect(skia.Rect.MakeXYWH(20, 20, 760, 96), 10, 10, self.panel)
        canvas.drawString("Project Behavior GPU test  -  you should see your desktop and be able to click it",
                          34, 50, self.font, self.text)
        canvas.drawString(self.hud, 34, 80, self.font, self.text)
        canvas.drawString("stage %d of %d   (closes by itself)" % (self.stage + 1, len(STAGES)),
                          34, 106, self.font, self.text)

    def step(self):
        """One frame.  False once every stage has run."""
        glfw = self.glfw
        glfw.poll_events()
        if self.stopped or glfw.window_should_close(self.window) or self.stage >= len(STAGES):
            return False
        t0 = time.perf_counter()
        self.flush_s = 0.0
        self._draw()                   # Python issuing the draw calls
        t1 = time.perf_counter()
        self.ctx.flushAndSubmit()      # Skia + the graphics card doing them
        if self.gl is not None:
            self.gl.glFinish()         # wait for the GPU: honest frame time
        glfw.swap_buffers(self.window)
        t2 = time.perf_counter()
        dt = (t2 - t0) * 1000.0
        self.frame += 1
        self.count += 1
        if self.checks is None and self.frame == 10:
            self.checks = overlay_checks(glfw, self.window)
        if self.count == WARMUP_FRAMES:
            self.t_stage = time.perf_counter()
        elif self.count > WARMUP_FRAMES:
            self.times.append(dt)
            self.py_ms += (t1 - t0 - self.flush_s) * 1000.0
            if len(self.times) % 20 == 0:
                m = sum(self.times[-20:]) / 20.0
                self.hud = "%s:  %.1f ms a frame  (%.0f fps)" % (STAGES[self.stage][0], m, 1000.0 / m)
            if time.perf_counter() - self.t_stage >= MEASURE_S:
                self.results.append(stats(self.times) + (self.py_ms / len(self.times),))
                self._next_stage()
        return True

    def close(self):
        try:
            self.glfw.destroy_window(self.window)
            self.glfw.terminate()
        except Exception:
            pass


# ---------------------------------------------------------------- CPU baseline
def cpu_baseline(w, h, done):
    """The same loads with QPainter into an image, as the game paints today
    (without the copy to the screen, which the real overlay also pays)."""
    from PyQt5.QtCore import QPointF, QRectF, Qt
    from PyQt5.QtGui import QBrush, QColor, QImage, QPainter, QPolygonF, QRadialGradient

    main = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
    layers = [QImage(w, h, QImage.Format_ARGB32_Premultiplied) for _ in range(2)]
    xs, ys, bend = warp_grid(w, h)
    cells = []
    for j in range(len(ys) - 1):
        for i in range(len(xs) - 1):
            x0, y0 = bend(xs[i], ys[j])
            x1, y1 = bend(xs[i + 1], ys[j + 1])
            cells.append((QRectF(x0, y0, x1 - x0 + 1, y1 - y0 + 1),
                          QRectF(xs[i], ys[j], xs[i + 1] - xs[i], ys[j + 1] - ys[j])))

    def content(p, gl, pl):
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        p.setPen(Qt.NoPen)
        for pts, c in pl:
            p.setBrush(QColor(c[0], c[1], c[2], 150))
            p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))
        for x, y, r, c in gl:
            g = QRadialGradient(x, y, r)
            g.setColorAt(0.0, QColor(c[0], c[1], c[2], 255))
            g.setColorAt(1.0, QColor(c[0], c[1], c[2], 0))
            p.setBrush(QBrush(g))
            p.drawEllipse(QPointF(x, y), r, r)

    out = []
    for si in CPU_STAGES:
        if si >= done:
            break
        name, glows, _how, polys, warp = STAGES[si]
        say("  running %s on the CPU ..." % name)
        frames = build_frames(w, h, glows, polys)
        ms = []
        for f in range(CPU_FRAMES + 3):
            gl, pl = frames[f % FRAME_SETS]
            t0 = time.perf_counter()
            main.fill(0)
            p = QPainter(main)
            p.setRenderHint(QPainter.Antialiasing)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            if warp:
                for part, img in enumerate(layers):
                    img.fill(0)
                    q = QPainter(img)
                    q.setRenderHint(QPainter.Antialiasing)
                    content(q, gl[part::2], pl[part::2])
                    q.end()
                    for dst, src in cells:
                        p.drawImage(dst, img, src)
            else:
                content(p, gl, pl)
            p.end()
            if f >= 3:
                ms.append((time.perf_counter() - t0) * 1000.0)
        out.append(stats(ms))
    return out


# ---------------------------------------------------------------- report
def report(test, gpu, cpu, qt_ok, qt_note):
    info = test.info
    renderer = info.get("renderer", "?")
    software = any(s in renderer.lower() for s in SOFTWARE)
    say()
    say("=" * 72)
    say("PROJECT BEHAVIOR - GPU OVERLAY TEST RESULT (test v2)")
    say("=" * 72)
    say("Machine      : %s %s, Python %s" % (platform.system(), platform.release(), platform.python_version()))
    say("Screen       : %d x %d   (drawing surface %d x %d)" % (test.screen + (test.w, test.h)))
    say("Graphics card: %s" % renderer)
    say("  vendor     : %s" % info.get("vendor", "?"))
    say("  OpenGL     : %s" % info.get("version", "?"))
    say("  hardware   : %s" % ("NO - software rendering" if software else "yes"))
    say()
    say("Overlay window")
    for key in ("see-through", "click-through", "always on top"):
        v = (test.checks or {}).get(key)
        say("  %-14s: %s" % (key, "not checked" if v is None else ("yes" if v else "NO")))
    say("  Qt + overlay in one process: %s%s" % ("yes" if qt_ok else "NOT TESTED", qt_note))
    say()
    say("Frame time (the game needs 16 ms or less; lower is better)")
    say("  %-34s %-22s %s" % ("load", "GPU canvas (Skia)", "CPU (QPainter, today)"))
    for i, (name, _g, _h, _p, _w) in enumerate(STAGES):
        g = "%6.1f ms  %5.0f fps" % (gpu[i][0], gpu[i][2]) if i < len(gpu) else "not run"
        c = ""
        if i in CPU_STAGES:
            j = CPU_STAGES.index(i)
            c = "%6.1f ms  %5.0f fps" % (cpu[j][0], cpu[j][2]) if j < len(cpu) else "not run"
        say("  %-34s %-22s %s" % (name, g, c))
    say("  (95th percentile, GPU: %s ms)" % ", ".join("%.1f" % r[1] for r in gpu))
    say()
    say("Where the GPU canvas frame goes")
    say("  %-34s %-22s %s" % ("load", "Python sending draws", "Skia + graphics card"))
    for i, r in enumerate(gpu):
        say("  %-34s %6.1f ms %s %6.1f ms" % (STAGES[i][0], r[3], " " * 12, r[0] - r[3]))
    say()
    ok_overlay = bool(test.checks) and all(test.checks.get(k) for k in ("see-through", "click-through", "always on top"))
    verdict = "INCOMPLETE - the test was stopped before stage B finished"
    if len(gpu) > 1:
        b = gpu[1][0]
        if software:
            verdict = "FAIL - OpenGL is running in software here, so a GPU canvas would not help"
        elif not ok_overlay:
            verdict = "FAIL - the overlay window is missing a feature (see above)"
        elif b <= 8.0:
            verdict = "PASS - the game-like load with the ball warp takes %.1f ms" % b
        elif b <= 16.0:
            verdict = "MARGINAL - the game-like load with the ball warp takes %.1f ms" % b
        else:
            verdict = "FAIL - the game-like load with the ball warp takes %.1f ms (over 16)" % b
    say("VERDICT: %s" % verdict)
    say("=" * 72)
    try:
        with open(RESULT, "w", encoding="utf-8") as f:
            f.write("\n".join(OUT) + "\n")
        print("\nSaved to %s - paste its contents to Claude." % RESULT, flush=True)
    except OSError as e:
        print("\nCould not save the result file (%s); copy the text above instead." % e, flush=True)


def main():
    say("Project Behavior GPU overlay test - about a minute, closes by itself.")
    try:
        test = GpuTest()
    except ImportError as e:
        say("Could not load a library: %s" % e)
        say("Run it through \"GPU Test.bat\" (it installs glfw and skia-python).")
        return 2
    except Exception as e:
        say("Could not start the GPU canvas: %s: %s" % (type(e).__name__, e))
        say("VERDICT: FAIL - the GPU canvas does not start on this machine")
        try:
            with open(RESULT, "w", encoding="utf-8") as f:
                f.write("\n".join(OUT) + "\n")
        except OSError:
            pass
        return 1
    say("Graphics card: %s" % test.info.get("renderer", "?"))

    qt_ok, qt_note, app = False, "  (PyQt5 not found)", None
    if "--noqt" in sys.argv:
        qt_note = "  (--noqt)"
    else:
        try:
            from PyQt5.QtCore import QTimer, Qt
            from PyQt5.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget
            app = QApplication(sys.argv[:1])
        except Exception as e:
            qt_note = "  (%s)" % e
    if app is not None:
        # The Qt window and the GLFW overlay share one event loop, the way
        # the game's start menu and a GPU overlay would.
        panel = QWidget()
        panel.setWindowTitle("GPU test")
        panel.setWindowFlags(Qt.WindowStaysOnTopHint)
        lay = QVBoxLayout(panel)
        label = QLabel("Running...")
        stop = QPushButton("Stop test")
        lay.addWidget(label)
        lay.addWidget(stop)
        stop.clicked.connect(lambda: setattr(test, "stopped", True))
        panel.resize(420, 90)
        panel.show()
        ticks = [0]
        timer = QTimer()

        def tick():
            try:
                test.glfw.make_context_current(test.window)
                alive = test.step()
            except Exception as e:      # report it instead of dying inside Qt
                say("  drawing failed: %s: %s" % (type(e).__name__, e))
                alive = False
            ticks[0] += 1
            if ticks[0] % 30 == 0:
                label.setText(test.hud or "Running...")
            if not alive:
                timer.stop()
                app.quit()
        timer.timeout.connect(tick)
        timer.start(0)
        app.exec_()
        panel.close()
        qt_ok, qt_note = ticks[0] > 0, ""
    else:
        try:
            while test.step():
                pass
        except Exception as e:
            say("  drawing failed: %s: %s" % (type(e).__name__, e))

    gpu = list(test.results)
    w, h = test.w, test.h
    test.close()
    cpu = []
    try:
        import PyQt5  # noqa: F401
        if app is None and "--noqt" not in sys.argv:
            raise ImportError
        if "--noqt" not in sys.argv:
            cpu = cpu_baseline(w, h, len(gpu))
    except Exception as e:
        say("  (CPU baseline skipped: %s)" % (e or "PyQt5 not available"))
    report(test, gpu, cpu, qt_ok, qt_note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
