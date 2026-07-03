"""Project Behavior — FX Previewer.
Renders .fx.json files (exported from the FX Creator) with real QPainter,
hot-reloading the instant the file changes on disk.

Usage:
    python tools/fx_preview.py path/to/effect.fx.json   # watch one file
    python tools/fx_preview.py                          # watch tools/fx/ for newest *.fx.json

Controls: Space = replay | L = toggle loop | B = cycle background | Esc = quit
"""
import sys, os, json, math, random, glob, time
from PyQt5.QtWidgets import QApplication, QWidget
from PyQt5.QtCore import Qt, QTimer, QPointF
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QRadialGradient, QFont

FPS = 60

def lerp(a, b, t): return a + (b - a) * t

def col_at(l, t):
    a, b = QColor(l["c1"]), QColor(l["c2"])
    return QColor(int(lerp(a.red(), b.red(), t)),
                  int(lerp(a.green(), b.green(), t)),
                  int(lerp(a.blue(), b.blue(), t)))

class Preview(QWidget):
    def __init__(self, path_arg):
        super().__init__()
        self.setWindowTitle("PB FX Preview")
        self.resize(860, 560)
        self.path_arg = path_arg
        self.fx = None; self.mtime = 0; self.cur_path = None
        self.parts = []; self.spawned = set(); self.acc = {}
        self.t0 = time.time(); self.loop = True; self.bg = 0
        self.timer = QTimer(self); self.timer.timeout.connect(self.tick)
        self.timer.start(int(1000 / FPS)); self.last = time.time()
        self.reload(force=True)

    # ---------- file watching ----------
    def target_path(self):
        if self.path_arg: return self.path_arg
        here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fx")
        files = glob.glob(os.path.join(here, "*.fx.json"))
        return max(files, key=os.path.getmtime) if files else None

    def reload(self, force=False):
        p = self.target_path()
        if not p or not os.path.exists(p): return
        m = os.path.getmtime(p)
        if force or p != self.cur_path or m != self.mtime:
            try:
                with open(p, "r", encoding="utf-8") as f:
                    self.fx = json.load(f)
                self.cur_path, self.mtime = p, m
                self.replay()
            except Exception as e:
                print("reload failed:", e)

    def replay(self):
        self.parts = []; self.spawned = set(); self.acc = {}; self.t0 = time.time()

    # ---------- engine ----------
    def anchor(self):  # static center; demo motion lives in the HTML editor
        return self.width() / 2, self.height() / 2

    def spawn(self, l, li, x, y, n):
        for _ in range(n):
            life = random.uniform(l.get("life_min", 300), l.get("life_max", 300))
            p = {"l": l, "type": l["type"], "x": x, "y": y, "life": life, "age": 0.0}
            t = l["type"]
            if t in ("particles", "trail"):
                a = math.radians(l.get("angle_deg", 0)) + \
                    random.uniform(-.5, .5) * math.radians(l.get("spread_deg", 360))
                s = random.uniform(l.get("speed_min", 0), l.get("speed_max", 0))
                p.update(vx=math.cos(a) * s, vy=math.sin(a) * s,
                         sz=random.uniform(l.get("size_min", 2), l.get("size_max", 5)),
                         px=x, py=y)
            if t in ("ring", "crescent"): p["a0"] = math.radians(l.get("angle_deg", 0))
            if t == "flash": p["sz"] = random.uniform(l.get("size_min", 20), l.get("size_max", 60))
            if t == "beam": p["seed"] = random.random() * 99
            self.parts.append(p)

    def tick(self):
        self.reload()
        now = time.time(); dt = min(now - self.last, 0.05); self.last = now
        if not self.fx: self.update(); return
        el = (now - self.t0) * 1000.0
        dur = self.fx.get("duration_ms", 800)
        ax, ay = self.anchor()
        for li, l in enumerate(self.fx.get("layers", [])):
            if el < l.get("delay_ms", 0): continue
            one = l["type"] in ("ring", "flash", "crescent", "beam") or \
                  (l["type"] == "particles" and l.get("burst", True))
            if one:
                if li not in self.spawned:
                    self.spawned.add(li)
                    self.spawn(l, li, ax, ay, l.get("count", 1) if l["type"] == "particles" else 1)
            else:
                rate = l.get("emit_rate", 60)
                self.acc[li] = self.acc.get(li, 0) + dt * rate
                while self.acc[li] >= 1:
                    self.acc[li] -= 1; self.spawn(l, li, ax, ay, 1)
        for p in self.parts[:]:
            p["age"] += dt * 1000
            if p["age"] >= p["life"]: self.parts.remove(p); continue
            if "vx" in p:
                dr = p["l"].get("drag", 1.0) ** (dt * 60)
                p["vx"] *= dr; p["vy"] *= dr
                p["vy"] += p["l"].get("gravity", 0) * dt
                p["px"], p["py"] = p["x"], p["y"]
                p["x"] += p["vx"] * dt; p["y"] += p["vy"] * dt
        if el > dur and self.loop: self.replay()
        self.update()

    # ---------- render ----------
    def paintEvent(self, _):
        qp = QPainter(self); qp.setRenderHint(QPainter.Antialiasing)
        qp.fillRect(self.rect(), QColor(10, 12, 18) if self.bg == 0 else QColor(0, 0, 0))
        el = (time.time() - self.t0) * 1000.0
        for p in self.parts:
            l, t = p["l"], p["age"] / p["life"]
            fade = 1 - t * t
            qp.setCompositionMode(QPainter.CompositionMode_Plus
                                  if l.get("blend", "additive") == "additive"
                                  else QPainter.CompositionMode_SourceOver)
            c = col_at(l, t); c.setAlphaF(max(0.0, min(1.0, fade)))
            ty = p["type"]
            if ty in ("particles", "trail"):
                s = p["sz"]; m = l.get("size_over_life", "shrink")
                if m == "shrink": s *= 1 - t
                elif m == "grow": s *= 0.3 + t
                elif m == "pulse": s *= 0.7 + 0.5 * math.sin(t * 12)
                if l.get("shape") == "spark" and "vx" in p:
                    vl = math.hypot(p["vx"], p["vy"]) or 1
                    k = min(0.06, 14 / vl)
                    qp.setPen(QPen(c, max(1, s * 0.5)))
                    qp.drawLine(QPointF(p["x"], p["y"]),
                                QPointF(p["x"] - p["vx"] * k, p["y"] - p["vy"] * k))
                else:
                    qp.setPen(Qt.NoPen); qp.setBrush(QBrush(c))
                    r = max(0.4, s / 2)
                    qp.drawEllipse(QPointF(p["x"], p["y"]), r, r)
                if ty == "trail" and l.get("line") and "px" in p:
                    qp.setPen(QPen(c, max(1, s * 0.4)))
                    qp.drawLine(QPointF(p["px"], p["py"]), QPointF(p["x"], p["y"]))
            elif ty == "ring":
                r = lerp(l["radius_start"], l["radius_end"], t)
                th = l["thickness"] * ((1 - t * 0.7) if l.get("thin_out", True) else 1)
                qp.setPen(QPen(c, max(0.5, th))); qp.setBrush(Qt.NoBrush)
                qp.drawEllipse(QPointF(p["x"], p["y"]), r, r)
            elif ty == "flash":
                s = p["sz"] * (1 - t * 0.5)
                g = QRadialGradient(p["x"], p["y"], s)
                c0 = col_at(l, 0); c0.setAlphaF(fade)
                g.setColorAt(0, c0); g.setColorAt(1, QColor(0, 0, 0, 0))
                qp.setPen(Qt.NoPen); qp.setBrush(QBrush(g))
                qp.drawEllipse(QPointF(p["x"], p["y"]), s, s)
                if l.get("rays"):
                    qp.setPen(QPen(c, 2))
                    for i in range(int(l["rays"])):
                        a = i / l["rays"] * 2 * math.pi
                        qp.drawLine(QPointF(p["x"], p["y"]),
                                    QPointF(p["x"] + math.cos(a) * s * 1.6,
                                            p["y"] + math.sin(a) * s * 1.6))
            elif ty == "crescent":
                r = lerp(l["radius_start"], l["radius_end"], t)
                spin = math.radians(l.get("spin_deg", 0)) * t
                a0 = p["a0"] + spin; half = math.radians(l["arc_deg"]) / 2
                pen = QPen(c, max(1, l["thickness"] * (1 - t * 0.5)))
                pen.setCapStyle(Qt.RoundCap); qp.setPen(pen); qp.setBrush(Qt.NoBrush)
                rect = (p["x"] - r, p["y"] - r, r * 2, r * 2)
                start = int(-math.degrees(a0 + half) * 16)
                span = int(math.degrees(2 * half) * 16)
                qp.drawArc(int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3]), start, span)
            elif ty == "afterimage":
                qp.setPen(Qt.NoPen)
                c2 = QColor(c); c2.setAlphaF(fade * 0.7); qp.setBrush(QBrush(c2))
                w, h = l.get("w", 16), l.get("h", 44)
                qp.drawRoundedRect(int(p["x"] - w / 2), int(p["y"] - h / 2),
                                   int(w), int(h), w / 2, w / 2)
            elif ty == "beam":
                a = math.radians(l.get("angle_deg", 0))
                pulse = 1 + 0.3 * math.sin(el / 1000 * 2 * math.pi * l.get("pulse_hz", 0) + p["seed"])
                seg, ln, j = int(l["segments"]), l["length"], l.get("jitter", 0)
                qp.setPen(QPen(c, max(1, l["width"] * pulse * (1 - t * 0.6)),
                               Qt.SolidLine, Qt.RoundCap))
                pts = [QPointF(p["x"] + math.cos(a) * ln * i / seg + random.uniform(-j, j),
                               p["y"] + math.sin(a) * ln * i / seg + random.uniform(-j, j))
                       for i in range(seg + 1)]
                for i in range(seg): qp.drawLine(pts[i], pts[i + 1])
                core = QColor(255, 255, 255); core.setAlphaF(fade)
                qp.setPen(QPen(core, max(0.5, l["width"] * 0.35)))
                qp.drawLine(QPointF(p["x"], p["y"]),
                            QPointF(p["x"] + math.cos(a) * ln, p["y"] + math.sin(a) * ln))
        qp.setCompositionMode(QPainter.CompositionMode_SourceOver)
        qp.setPen(QColor(120, 130, 150)); qp.setFont(QFont("Segoe UI", 8))
        name = self.fx.get("name", "?") if self.fx else "waiting for .fx.json ..."
        qp.drawText(10, 18, f"{name}   [Space]=replay  [L]=loop:{'on' if self.loop else 'off'}  [B]=bg  — watching: {self.cur_path or 'tools/fx/'}")

    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key_Space: self.replay()
        elif k == Qt.Key_L: self.loop = not self.loop
        elif k == Qt.Key_B: self.bg = 1 - self.bg
        elif k == Qt.Key_Escape: self.close()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Preview(sys.argv[1] if len(sys.argv) > 1 else None)
    w.show()
    sys.exit(app.exec_())
