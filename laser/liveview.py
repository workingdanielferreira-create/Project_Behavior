"""
Live camera settings (Daniel 2026-11-21) — changed WHILE the fight runs.

Ctrl+Alt+C opens / closes the panel (laser/liveviewpanel.py); the battle
keeps running behind it.  Solo and Battle alike.  Settings:

  * Battle speed     10% .. 300% of normal.  Overlay._tick advances the
                     simulation `speed` ticks per real tick (an accumulator,
                     like the KO slow-mo): fighters, FX, projectiles,
                     hit-stop, cooldowns all scale together.  Input, the
                     camera's own easing and the HUD stay real-time.
  * Camera mode      auto  = the normal World Camera follow (camera.json).
                     focus = centred on ONE fighter (its slot) at
                             `focus_zoom` (0.5x .. 4x).
                     duel  = frames the chosen fighters (2+ slots) at all
                             times: zooms out when they are far apart (down
                             to `duel_min_zoom`, below 1.0x allowed), in when
                             they are close (up to `duel_max_zoom`),
                             `duel_margin_px` round them.
                     focus / duel are free views: the old "never leave the
                     screen" clamp is off so the picked fighter stays
                     centred.  Cinematic shots, punch-in and shake still
                     play on top.  A slot whose fighter is benched (tag /
                     trio) follows the team-mate now on the field; nobody
                     to frame -> auto.
  * Background       a flat colour layer under the whole scene (screen
                     space, never camera'd), `bg_color` at `bg_alpha` %
                     (0 = the old fully see-through overlay).

Saved to characters/live_view.json (format pb_live_view, gitignored: each
player's own) — kept apart from camera.json so FX Studio's World Camera tab
never overwrites it.  The camera reads `World.live_view` in
Camera._target / Camera._clamp; the panel only edits this object.
"""

import json
import os
import threading

FILE = "live_view.json"            # in characters/
FORMAT = "pb_live_view"

MODES = ("auto", "focus", "duel")
MODE_LABELS = {"auto": "Auto (World Camera)", "focus": "Character focus", "duel": "Duel cam"}

DEFAULTS = {
    "speed": 1.0,             # battle speed (1.0 = normal)
    "cam_mode": "auto",
    "focus_slot": None,       # slot index (roster.Slot.index)
    "focus_zoom": 2.0,
    "duel_slots": [],         # slot indices
    "duel_margin_px": 140.0,
    "duel_min_zoom": 0.5,
    "duel_max_zoom": 2.5,
    "bg_color": "#000000",
    "bg_alpha": 0.0,          # 0 .. 100 %
}

RANGES = {
    "speed": (0.10, 3.00),
    "focus_zoom": (0.5, 4.0),
    "duel_margin_px": (0.0, 600.0),
    "duel_min_zoom": (0.25, 1.0),
    "duel_max_zoom": (1.0, 4.0),
    "bg_alpha": (0.0, 100.0),
}

MAX_STEPS = 3                      # sim ticks per real tick at most (300%)


def _num(v, d, lo, hi):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return d
    if v != v:
        return d
    return max(lo, min(hi, v))


def _color(v, d):
    s = str(v or "").strip()
    if len(s) == 7 and s[0] == "#":
        try:
            int(s[1:], 16)
            return s.lower()
        except ValueError:
            pass
    return d


def normalize(obj):
    s = dict(DEFAULTS)
    s["duel_slots"] = []
    if not isinstance(obj, dict):
        return s
    for k, (lo, hi) in RANGES.items():
        if k in obj:
            s[k] = _num(obj[k], DEFAULTS[k], lo, hi)
    if obj.get("cam_mode") in MODES:
        s["cam_mode"] = obj["cam_mode"]
    fs = obj.get("focus_slot")
    if isinstance(fs, int) and not isinstance(fs, bool) and fs >= 0:
        s["focus_slot"] = fs
    ds = obj.get("duel_slots")
    if isinstance(ds, list):
        s["duel_slots"] = sorted({int(i) for i in ds
                                  if isinstance(i, int) and not isinstance(i, bool) and i >= 0})
    s["bg_color"] = _color(obj.get("bg_color"), DEFAULTS["bg_color"])
    return s


class LiveView:

    def __init__(self, root_dir=None):
        self.root = root_dir
        self.cfg = normalize({})
        self.acc = 0.0                 # battle speed accumulator (sim ticks owed)
        self.free = False              # this tick's camera target is a free view
        self._save_lock = threading.Lock()
        self.load()

    # --- settings ---------------------------------------------------------
    def _path(self):
        if not self.root:
            return None
        return os.path.join(self.root, "characters", FILE)

    def load(self):
        path = self._path()
        obj = {}
        if path:
            try:
                with open(path, "r", encoding="utf-8-sig") as f:
                    obj = json.load(f)
            except (OSError, ValueError):
                obj = {}
        if not (isinstance(obj, dict) and obj.get("format") == FORMAT):
            obj = {}
        self.cfg = normalize(obj)

    def set(self, key, value):
        """Change one setting (range-checked) from the panel."""
        obj = dict(self.cfg)
        obj[key] = value
        self.cfg = normalize(obj)

    def save(self):
        """Write live_view.json on a background thread (the game thread
        never waits on a file Windows may be holding)."""
        path = self._path()
        if not path:
            return
        data = dict(self.cfg)
        data["format"] = FORMAT
        text = json.dumps(data, indent=2)

        def write():
            with self._save_lock:
                try:
                    tmp = path + ".tmp"
                    with open(tmp, "w", encoding="utf-8") as f:
                        f.write(text)
                    os.replace(tmp, path)
                except OSError:
                    pass
        threading.Thread(target=write, daemon=True).start()

    # --- battle speed -----------------------------------------------------
    def sim_steps(self):
        """Simulation ticks to run for this real tick (0..MAX_STEPS)."""
        sp = self.cfg["speed"]
        if abs(sp - 1.0) < 1e-6:
            self.acc = 0.0
            return 1
        self.acc += sp
        n = int(self.acc)
        self.acc -= n
        return min(MAX_STEPS, n)

    # --- fighters ---------------------------------------------------------
    @staticmethod
    def slot_fig(world, index):
        """The fielded fighter for slot `index`: its own fighter when on the
        field, else (tag pair / trio) the group member on the field now,
        else None."""
        slots = getattr(world, "slots", None) or ()
        if index is None or not (0 <= index < len(slots)):
            return None
        live = {id(f) for f in world.all_figures()}
        s = slots[index]
        if s.fig is not None and id(s.fig) in live:
            return s.fig
        for g in getattr(world, "tag_pairs", None) or ():
            try:
                members = list(g.members)
            except Exception:
                continue
            if s in members:
                on = getattr(g, "on", None)
                f = getattr(on, "fig", None)
                if f is not None and id(f) in live:
                    return f
        return None

    @staticmethod
    def _pos(fig):
        tr = getattr(fig, "transform", None)
        if tr is None or not getattr(tr, "init", True):
            return None
        return float(tr.x), float(tr.y)

    # --- camera -----------------------------------------------------------
    def cam_target(self, world, sw, sh):
        """(cx, cy, zoom) for focus / duel, or None = the normal follow-cam.
        Sets self.free (the camera skips its on-screen clamp)."""
        c = self.cfg
        mode = c["cam_mode"]
        self.free = False
        if mode == "focus":
            f = self.slot_fig(world, c["focus_slot"])
            p = self._pos(f) if f is not None else None
            if p is None:
                return None
            self.free = True
            return p[0], p[1], c["focus_zoom"]
        if mode == "duel":
            pts = []
            seen = set()
            for i in c["duel_slots"]:
                f = self.slot_fig(world, i)
                if f is None or id(f) in seen:
                    continue
                seen.add(id(f))
                p = self._pos(f)
                if p is not None:
                    pts.append(p)
            if not pts:
                return None
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            m = c["duel_margin_px"]
            bw = max(xs) - min(xs) + 2.0 * m
            bh = max(ys) - min(ys) + 2.0 * m
            fit = min(sw / max(1.0, bw), sh / max(1.0, bh))
            lo, hi = c["duel_min_zoom"], c["duel_max_zoom"]
            z = max(lo, min(hi, fit))
            self.free = True
            return (max(xs) + min(xs)) / 2.0, (max(ys) + min(ys)) / 2.0, z
        return None

    # --- background -------------------------------------------------------
    def paint_bg(self, p, w, h):
        """The backdrop colour, screen space, under the whole scene."""
        a = self.cfg["bg_alpha"]
        if a <= 0.0:
            return
        from PyQt5.QtGui import QColor
        col = QColor(self.cfg["bg_color"])
        col.setAlpha(max(1, min(255, int(round(a * 2.55)))))
        p.fillRect(0, 0, int(w) + 1, int(h) + 1, col)
