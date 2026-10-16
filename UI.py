"""
UI.py  -  NEON//KATALOG
Cyberpunk 3D animated interface for katalog_elektronik.

Jalankan:  python UI.py

File ini TIDAK mengubah Main.py, tambah_elektronik.py, tampil_elektronik.py
atau models.py. Semua logika diambil langsung dari modul-modul tersebut:
  - tambah_elektronik.simpan_elektronik()   -> menyimpan data (validasi + CSV asli)
  - tampil_elektronik.muat_data()           -> memuat data katalog
  - tampil_elektronik.tampilkan_elektronik() -> output terminal asli
  - Main.buka_tambah_elektronik() / Main.buka_tampil_elektronik() -> modul terminal lama

Kontrol:
  [1-4]  pindah halaman        [F5]  sinkron ulang data
  [F11]  layar penuh           [S]   scanline on/off
  Drag hologram = putar, scroll = zoom, klik = morph bentuk
"""

import hashlib
import math
import os
import random
import sys
import threading
import time
import traceback
from collections import Counter, deque
from functools import lru_cache

import tkinter as tk
import tkinter.font as tkfont

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import Main  # noqa: E402
import tambah_elektronik  # noqa: E402
import tampil_elektronik  # noqa: E402
from models import Elektronik  # noqa: E402


# --------------------------------------------------------------------------
#  PALETTE
# --------------------------------------------------------------------------
BG = "#05010d"
PANEL = "#0a0418"
ENTRY_BG = "#07020f"
CYAN = "#00f0ff"
MAG = "#ff2a6d"
YEL = "#f9f002"
PURP = "#7a00ff"
DIM = "#3a2a5a"
TXT = "#d6f7ff"
WHITE = "#ffffff"
GREEN = "#39ff88"


def clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def ease_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ease_back(x):
    x = clamp(x)
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


@lru_cache(maxsize=8192)
def _mix(a, b, t):
    ra, ga, ba = int(a[1:3], 16), int(a[3:5], 16), int(a[5:7], 16)
    rb, gb, bb = int(b[1:3], 16), int(b[3:5], 16), int(b[5:7], 16)
    return "#%02x%02x%02x" % (
        int(ra + (rb - ra) * t),
        int(ga + (gb - ga) * t),
        int(ba + (bb - ba) * t),
    )


def mix(a, b, t):
    return _mix(a, b, round(clamp(t), 2))


def hash01(text):
    h = hashlib.md5(str(text).encode("utf-8")).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def chamfer(x1, y1, x2, y2, c=12):
    return [x1 + c, y1, x2, y1, x2, y2 - c, x2 - c, y2, x1, y2, x1, y1 + c]


def is_available(item):
    return item.status.strip().lower() == "tersedia"


# --------------------------------------------------------------------------
#  Bridge to the original modules (patch print/input on the module only
#  for the duration of the call so the original code runs untouched).
# --------------------------------------------------------------------------
def run_captured(module, func, answers=()):
    logs = []
    feed = iter(answers)

    def fake_print(*args, sep=" ", end="\n", **_):
        logs.extend(sep.join(str(a) for a in args).split("\n"))

    def fake_input(prompt=""):
        return next(feed, "")

    module.print = fake_print
    module.input = fake_input
    try:
        result = func()
    finally:
        del module.print
        del module.input
    return result, logs


# --------------------------------------------------------------------------
#  3D SHAPES
# --------------------------------------------------------------------------
def _edges_by(verts, test):
    n = len(verts)
    return [(i, j) for i in range(n) for j in range(i + 1, n) if test(verts[i], verts[j])]


def build_cube():
    v = [(x, y, z) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
    e = _edges_by(v, lambda a, b: sum(p != q for p, q in zip(a, b)) == 1)
    v = [(x * 0.82, y * 0.82, z * 0.82) for x, y, z in v]
    return (lambda t: v), e


def build_ico():
    p = (1 + 5 ** 0.5) / 2
    v = []
    for a in (-1, 1):
        for b in (-p, p):
            v += [(0, a, b), (a, b, 0), (b, 0, a)]
    e = _edges_by(v, lambda a, b: abs(math.dist(a, b) - 2) < 1e-6)
    s = 1.3 / math.sqrt(1 + p * p)
    v = [(x * s, y * s, z * s) for x, y, z in v]
    return (lambda t: v), e


def build_octa():
    s = 1.35
    v = [(s, 0, 0), (-s, 0, 0), (0, s, 0), (0, -s, 0), (0, 0, s), (0, 0, -s)]
    e = _edges_by(v, lambda a, b: math.dist(a, b) < 2.5)
    return (lambda t: v), e


def build_torus(U=14, V=7, R=0.95, r=0.38):
    v = []
    for i in range(U):
        u = 2 * math.pi * i / U
        for j in range(V):
            w = 2 * math.pi * j / V
            v.append(((R + r * math.cos(w)) * math.cos(u), r * math.sin(w), (R + r * math.cos(w)) * math.sin(u)))
    e = []
    for i in range(U):
        for j in range(V):
            a = i * V + j
            e.append((a, ((i + 1) % U) * V + j))
            e.append((a, i * V + (j + 1) % V))
    return (lambda t: v), e


def build_sphere(lat=7, lon=12, R=1.15):
    v = []
    for i in range(1, lat):
        phi = math.pi * i / lat
        for j in range(lon):
            th = 2 * math.pi * j / lon
            v.append((R * math.sin(phi) * math.cos(th), R * math.cos(phi), R * math.sin(phi) * math.sin(th)))
    e = []
    for i in range(lat - 1):
        for j in range(lon):
            a = i * lon + j
            e.append((a, i * lon + (j + 1) % lon))
            if i < lat - 2:
                e.append((a, (i + 1) * lon + j))
    return (lambda t: v), e


def build_tesseract():
    v4 = [(x, y, z, w) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1) for w in (-1, 1)]
    e = _edges_by(v4, lambda a, b: sum(p != q for p, q in zip(a, b)) == 1)

    def verts(t):
        a, b = t * 0.9, t * 0.55
        ca, sa, cb, sb = math.cos(a), math.sin(a), math.cos(b), math.sin(b)
        out = []
        for x, y, z, w in v4:
            x, w = x * ca - w * sa, x * sa + w * ca
            z, w = z * cb - w * sb, z * sb + w * cb
            k = 1.5 / (2.8 - w)
            out.append((x * k * 0.85, y * k * 0.85, z * k * 0.85))
        return out

    return verts, e


SHAPES = [
    ("TESSERACT // 4D HYPERCUBE",) + build_tesseract(),
    ("ICOSAHEDRON // D20 CORE",) + build_ico(),
    ("TORUS // FLUX RING",) + build_torus(),
    ("GEOSPHERE // NET GLOBE",) + build_sphere(),
    ("CUBE // DATA BLOCK",) + build_cube(),
    ("OCTAHEDRON // PRISM",) + build_octa(),
]

NAV = [
    ("DASHBOARD", "SYSTEM OVERVIEW", 1),
    ("UPLOAD UNIT", "TAMBAH ELEKTRONIK", 4),
    ("DATA VAULT", "TAMPIL KATALOG", 5),
    ("TERMINAL", "Main.py BRIDGE", 0),
]


def pick_font(root, prefs, fallback):
    fams = {f.lower(): f for f in tkfont.families(root)}
    for p in prefs:
        if p.lower() in fams:
            return fams[p.lower()]
    return fallback


# --------------------------------------------------------------------------
#  APPLICATION
# --------------------------------------------------------------------------
class NeonKatalog(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("NEON//KATALOG  -  Electronic Inventory Mainframe")
        self.geometry("1320x820")
        self.minsize(1080, 700)
        self.configure(bg=BG)

        self.cv = tk.Canvas(self, bg=BG, highlightthickness=0, cursor="crosshair")
        self.cv.pack(fill="both", expand=True)

        display = pick_font(self, ["Orbitron", "Audiowide", "Rajdhani", "Bahnschrift", "Segoe UI Black",
                                   "Arial Black", "DejaVu Sans", "Helvetica"], "Helvetica")
        mono = pick_font(self, ["Cascadia Mono", "Consolas", "JetBrains Mono", "SF Mono", "Menlo",
                                "DejaVu Sans Mono", "Courier New", "Courier"], "Courier")
        self.MONO = mono
        self.f_logo = (display, 24, "bold")
        self.f_huge = (display, 40, "bold")
        self.f_big = (display, 30, "bold")
        self.f_h1 = (display, 17, "bold")
        self.f_h2 = (display, 12, "bold")
        self.f_btn = (display, 10, "bold")
        self.f_mono = (mono, 11)
        self.f_mono_b = (mono, 11, "bold")
        self.f_small = (mono, 9, "bold")
        self.f_tiny = (mono, 8)
        self.f_rain = (mono, 11, "bold")

        self.stipple = "" if self.tk.call("tk", "windowingsystem") == "aqua" else "gray75"

        # time / state
        self.t = 0.0
        self.dt = 0.016
        self.last = time.perf_counter()
        self.fps = 60.0
        self.boot_until = 3.2
        self.booting = True
        self.page = 0
        self.page_t = 0.0
        self.warp = 0.0
        self.scan_on = False
        self.scan_size = (0, 0)
        self.glitch_until = 0.0
        self.next_glitch = 5.0

        # mouse
        self.mx, self.my = -100, -100
        self.mouse_down = False
        self.trail = deque(maxlen=18)
        self.hot = []
        self.hov = {}
        self.cursor_hand = False

        # FX
        self.particles = []
        self.waves = []
        self.toasts = []
        self.pending = []
        self.shake_until = 0.0

        # hologram
        self.shape_idx = 0
        self.rx, self.ry, self.rz = 0.4, 0.0, 0.0
        self.spin_x, self.spin_y = 0.35, 0.6
        self.zoom = 1.0
        self.zoom_target = 1.0
        self.morph_t = -10.0
        self.dragging = False
        self.drag_moved = 0.0
        self.drag_last = (0, 0)
        self.holo_rect = (0, 0, 0, 0)

        # data
        self.items = []
        self.selected = None
        self.detail_anim = 0.0
        self.filter_mode = "ALL"
        self.scroll = 0.0
        self.scroll_target = 0.0
        self.max_scroll = 0.0
        self.list_t0 = 0.0
        self.upload_start = None
        self.term_lines = []
        self.term_t0 = 0.0

        # scenery
        rnd = random.Random(2077)
        self.stars = [[rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(0.05, 1)] for _ in range(90)]
        self.buildings = []
        x = -0.15
        while x < 1.15:
            bw = rnd.randint(26, 80)
            bh = rnd.randint(40, 190)
            wins = [(rnd.random(), rnd.random(), rnd.random()) for _ in range(rnd.randint(2, 5))]
            self.buildings.append((x, bw, bh, wins, rnd.random() < 0.3, rnd.random()))
            x += rnd.uniform(0.025, 0.06)
        self.rain = [(rnd.uniform(0.2, 1.0), rnd.random(), "".join(rnd.choice("01ABCDEF#$%<>") for _ in range(26)))
                     for _ in range(120)]
        self.beam_dots = [(rnd.uniform(-1, 1), rnd.random(), rnd.uniform(0.5, 1.5)) for _ in range(26)]

        # entries
        self.entry_geom = {}
        self.entry_pos = {}
        self.form = []
        for _ in range(3):
            self.form.append(self._make_entry())
        self.search, self.search_win = self._make_entry(size=12)
        self.search.bind("<KeyRelease>", lambda e: self._on_search())

        self.reload(silent=True)
        self.run_terminal_capture()

        # bindings
        self.cv.bind("<Motion>", self.on_motion)
        self.cv.bind("<B1-Motion>", self.on_drag)
        self.cv.bind("<ButtonPress-1>", self.on_press)
        self.cv.bind("<ButtonRelease-1>", self.on_release)
        self.cv.bind("<Leave>", lambda e: self._set_mouse(-100, -100))
        self.bind_all("<MouseWheel>", lambda e: self.on_wheel(1 if e.delta > 0 else -1))
        self.bind_all("<Button-4>", lambda e: self.on_wheel(1))
        self.bind_all("<Button-5>", lambda e: self.on_wheel(-1))
        self.bind("<Key>", self.on_key)
        self.bind("<F5>", lambda e: self.reload())
        self.bind("<F11>", lambda e: self.attributes("-fullscreen", not self.attributes("-fullscreen")))
        self.bind("<Escape>", self.on_escape)

        self.after(10, self.loop)

    # ------------------------------------------------------------------ data
    def reload(self, silent=False):
        try:
            items, logs = run_captured(tampil_elektronik, tampil_elektronik.muat_data)
        except Exception as exc:  # malformed CSV rows etc.
            self.toast(f"CSV CORRUPTED :: {exc}", MAG)
            return
        self.items = items
        if self.selected is not None:
            match = [i for i in items if i.nomor_seri == self.selected.nomor_seri]
            self.selected = match[0] if match else None
        self.list_t0 = self.t
        if not silent:
            self.warp = 1.0
            msg = logs[0] if logs else f"SYNC COMPLETE :: {len(items)} UNITS LOADED"
            self.toast(msg.upper(), CYAN)

    def run_terminal_capture(self):
        try:
            _, logs = run_captured(tampil_elektronik, tampil_elektronik.tampilkan_elektronik)
        except Exception as exc:
            logs = [f"Traceback: {exc}"]
        self.term_lines = ["root@neon-mainframe:~/katalog$ python tampil_elektronik.py"] + logs
        self.term_t0 = self.t

    def commit_upload(self):
        values = [e.get() for e, _ in self.form]
        try:
            _, logs = run_captured(tambah_elektronik, tambah_elektronik.simpan_elektronik, values)
        except Exception as exc:
            logs = [f"[ERROR] {exc}"]
        text = " ".join(l for l in logs if l.strip() and "===" not in l).strip()
        w, h = self._size()
        if "[BERHASIL]" in text:
            self.toast("UPLINK OK :: " + text.replace("[BERHASIL]", "").strip().upper(), GREEN)
            for e, _ in self.form:
                e.delete(0, "end")
            self.reload(silent=True)
            self.run_terminal_capture()
            self.burst(w * 0.45, h * 0.55, 160, [CYAN, MAG, YEL, GREEN], speed=700)
            self.waves.append([w * 0.45, h * 0.55, self.t, CYAN, 900])
            self.waves.append([w * 0.45, h * 0.55, self.t + 0.12, MAG, 900])
            self.warp = 1.0
            self.form[0][0].focus_set()
        else:
            self.toast("ACCESS DENIED :: " + (text.replace("[PERINGATAN]", "").strip().upper() or "INVALID INPUT"), MAG)
            self.shake_until = self.t + 0.5
            self.glitch_until = self.t + 0.25

    def launch_legacy(self, fn, label):
        self.toast(f"SPAWNING {label} IN CONSOLE WINDOW...", YEL)

        def run():
            try:
                fn()
                self.pending.append((f"{label} SESSION CLOSED", CYAN))
            except Exception as exc:
                self.pending.append((f"LAUNCH FAILED :: {exc}", MAG))
            self.pending.append(("__reload__", None))

        threading.Thread(target=run, daemon=True).start()

    # ------------------------------------------------------------ helpers
    def _size(self):
        return max(self.cv.winfo_width(), 200), max(self.cv.winfo_height(), 200)

    def _make_entry(self, size=13):
        e = tk.Entry(self.cv, bg=ENTRY_BG, fg=CYAN, insertbackground=MAG, insertwidth=3, relief="flat", bd=0,
                     highlightthickness=0, font=(self.MONO, size, "bold"), selectbackground=MAG,
                     selectforeground=BG)
        wid = self.cv.create_window(-2000, -2000, window=e, anchor="nw", state="hidden")
        e.bind("<Key>", lambda ev, ent=e: self.on_entry_key(ev, ent), add="+")
        return e, wid

    def place_entry(self, wid, x, y, w, h):
        geom = (int(x), int(y), int(w), int(h))
        self._placed.add(wid)
        if self.entry_geom.get(wid) != geom:
            self.cv.coords(wid, geom[0], geom[1])
            self.cv.itemconfigure(wid, width=geom[2], height=geom[3], state="normal")
            self.entry_geom[wid] = geom
        self.entry_pos[wid] = geom

    def L(self, *pts, **kw):
        return self.cv.create_line(*pts, tags="dyn", **kw)

    def P(self, pts, **kw):
        return self.cv.create_polygon(*pts, tags="dyn", **kw)

    def R(self, x1, y1, x2, y2, **kw):
        return self.cv.create_rectangle(x1, y1, x2, y2, tags="dyn", **kw)

    def O(self, x1, y1, x2, y2, **kw):
        return self.cv.create_oval(x1, y1, x2, y2, tags="dyn", **kw)

    def T(self, x, y, text, font, fill, anchor="nw", **kw):
        return self.cv.create_text(x, y, text=text, font=font, fill=fill, anchor=anchor, tags="dyn", **kw)

    def A(self, x1, y1, x2, y2, **kw):
        return self.cv.create_arc(x1, y1, x2, y2, tags="dyn", **kw)

    def glow(self, pts, color, width=2, strength=1.0):
        self.L(*pts, fill=mix(BG, color, 0.14 * strength), width=width + 7, capstyle="round", joinstyle="round")
        self.L(*pts, fill=mix(BG, color, 0.38 * strength), width=width + 3, capstyle="round", joinstyle="round")
        self.L(*pts, fill=color, width=width, capstyle="round", joinstyle="round")

    def gtext(self, x, y, text, font, color=TXT, anchor="nw", amp=1.0):
        j = 1.5 * amp
        if random.random() < 0.05 * amp or self.t < self.glitch_until:
            j = random.uniform(3, 9) * max(amp, 0.6)
        self.T(x - j, y, text, font, MAG, anchor)
        self.T(x + j, y, text, font, CYAN, anchor)
        self.T(x, y, text, font, color, anchor)

    def hover(self, key, x1, y1, x2, y2):
        inside = (not self.booting) and x1 <= self.mx <= x2 and y1 <= self.my <= y2
        cur = self.hov.get(key, 0.0)
        cur += ((1.0 if inside else 0.0) - cur) * min(1.0, self.dt * 14)
        self.hov[key] = cur
        return cur, inside

    def hotspot(self, x1, y1, x2, y2, cb):
        self.hot.append((x1, y1, x2, y2, cb))

    def panel(self, x1, y1, x2, y2, title=None, color=CYAN, accent=MAG):
        pts = chamfer(x1, y1, x2, y2, 18)
        self.P(pts, fill=PANEL, outline="", stipple=self.stipple)
        self.L(*(pts + pts[:2]), fill=mix(BG, color, 0.55), width=1)
        L = 28
        self.L(x1, y1 + 18 + L, x1, y1 + 18, x1 + 18, y1, x1 + 18 + L, y1, fill=accent, width=3)
        self.L(x2, y2 - 18 - L, x2, y2 - 18, x2 - 18, y2, x2 - 18 - L, y2, fill=accent, width=3)
        span = max(1, x2 - x1 - 40)
        p = (self.t * 0.28 + hash01(title)) % 1
        lx = x1 + 20 + p * span
        self.L(max(x1 + 20, lx - 70), y1, lx, y1, fill=color, width=3)
        self.O(lx - 3, y1 - 3, lx + 3, y1 + 3, fill=WHITE, outline="")
        if title:
            tw = len(title) * 7.4 + 34
            self.P([x1 + 34, y1, x1 + 34 + tw, y1, x1 + 24 + tw, y1 + 20, x1 + 44, y1 + 20],
                   fill=mix(BG, color, 0.2), outline=mix(BG, color, 0.7))
            self.T(x1 + 52, y1 + 10, title, self.f_small, color, "w")

    def button(self, key, x1, y1, x2, y2, label, cb, color=CYAN, font=None):
        h, inside = self.hover(key, x1, y1, x2, y2)
        if inside and self.mouse_down:
            y1 += 2
            y2 += 2
        pts = chamfer(x1, y1, x2, y2, 10)
        self.P(pts, fill=mix(PANEL, color, 0.08 + 0.25 * h), outline="")
        if h > 0.05:
            self.glow(pts + pts[:2], mix(DIM, color, 0.5 + 0.5 * h), 1, strength=h)
            sweep = ((self.t * 1.3) % 1.6 - 0.3)
            sx = x1 + sweep * (x2 - x1)
            if x1 + 6 < sx < x2 - 26:
                self.L(sx, y2 - 3, sx + 18, y1 + 3, fill=mix(color, WHITE, 0.6), width=4)
        else:
            self.L(*(pts + pts[:2]), fill=mix(DIM, color, 0.45), width=1)
        self.T((x1 + x2) / 2, (y1 + y2) / 2, label, font or self.f_btn, mix(color, WHITE, 0.2 + h * 0.6), "center")
        self.hotspot(x1, y1, x2, y2, cb)
        return h

    def wire(self, verts, edges, cx, cy, scale, ax, ay, az, near=CYAN, far=PURP, width=2, glow=True, dots=True):
        ca, sa = math.cos(ax), math.sin(ax)
        cb, sb = math.cos(ay), math.sin(ay)
        cc, sc = math.cos(az), math.sin(az)
        proj = []
        for x, y, z in verts:
            y, z = y * ca - z * sa, y * sa + z * ca
            x, z = x * cb + z * sb, -x * sb + z * cb
            x, y = x * cc - y * sc, x * sc + y * cc
            f = scale * 3.4 / (3.4 + z)
            proj.append((cx + x * f, cy + y * f, z))
        order = sorted(edges, key=lambda e: -(proj[e[0]][2] + proj[e[1]][2]))
        for a, b in order:
            pa, pb = proj[a], proj[b]
            depth = clamp((1.4 - (pa[2] + pb[2]) / 2) / 2.8)
            col = mix(far, near, depth)
            if glow:
                self.L(pa[0], pa[1], pb[0], pb[1], fill=mix(BG, col, 0.3), width=width + 5, capstyle="round")
            self.L(pa[0], pa[1], pb[0], pb[1], fill=col, width=width if depth > 0.4 else max(1, width - 1))
        if dots:
            for x, y, z in proj:
                if z < 0.1:
                    r = 2.5 if z < -0.5 else 1.6
                    self.O(x - r, y - r, x + r, y + r, fill=WHITE, outline="")
        return proj

    # FX
    def burst(self, x, y, n, colors, speed=360):
        for _ in range(n):
            ang = random.uniform(0, math.tau)
            sp = random.uniform(0.2, 1.0) * speed
            life = random.uniform(0.4, 1.1)
            self.particles.append([x, y, math.cos(ang) * sp, math.sin(ang) * sp, life, life, random.choice(colors)])
        if len(self.particles) > 700:
            del self.particles[: len(self.particles) - 700]

    def toast(self, text, color=CYAN):
        self.toasts.append([text, color, self.t])
        self.toasts = self.toasts[-4:]

    def go(self, page):
        if page == self.page:
            return
        self.page = page
        self.page_t = 0.0
        self.warp = 1.0
        self.glitch_until = self.t + 0.18
        self.list_t0 = self.t
        self.cv.focus_set()
        if page == 3:
            self.run_terminal_capture()
        if page == 1:
            self.after(50, lambda: self.form[0][0].focus_set())

    # ------------------------------------------------------------ events
    def _set_mouse(self, x, y):
        self.mx, self.my = x, y

    def on_motion(self, e):
        self.mx, self.my = e.x, e.y
        self.trail.append((e.x, e.y, self.t))

    def on_drag(self, e):
        self.on_motion(e)
        if self.dragging:
            dx, dy = e.x - self.drag_last[0], e.y - self.drag_last[1]
            self.drag_last = (e.x, e.y)
            self.drag_moved += abs(dx) + abs(dy)
            self.ry += dx * 0.012
            self.rx += dy * 0.012
            d = max(self.dt, 0.008)
            self.spin_y = clamp(dx * 0.012 / d, -12, 12)
            self.spin_x = clamp(dy * 0.012 / d, -12, 12)

    def on_press(self, e):
        self.mouse_down = True
        self.cv.focus_set()
        if self.booting:
            self.boot_until = self.t
            return
        self.burst(e.x, e.y, 14, [CYAN, MAG])
        self.waves.append([e.x, e.y, self.t, CYAN, 120])
        for x1, y1, x2, y2, cb in reversed(self.hot):
            if x1 <= e.x <= x2 and y1 <= e.y <= y2:
                cb()
                return
        hx1, hy1, hx2, hy2 = self.holo_rect
        if self.page == 0 and hx1 <= e.x <= hx2 and hy1 <= e.y <= hy2:
            self.dragging = True
            self.drag_moved = 0
            self.drag_last = (e.x, e.y)

    def on_release(self, e):
        self.mouse_down = False
        if self.dragging and self.drag_moved < 6:
            self.morph()
        self.dragging = False

    def morph(self):
        self.shape_idx = (self.shape_idx + 1) % len(SHAPES)
        self.morph_t = self.t
        hx1, hy1, hx2, hy2 = self.holo_rect
        self.burst((hx1 + hx2) / 2, (hy1 + hy2) / 2 - 30, 70, [CYAN, MAG, PURP], speed=500)
        self.waves.append([(hx1 + hx2) / 2, (hy1 + hy2) / 2 - 30, self.t, MAG, 400])
        self.glitch_until = self.t + 0.15

    def on_wheel(self, direction):
        if self.page == 0:
            self.zoom_target = clamp(self.zoom_target + direction * 0.1, 0.5, 1.8)
        elif self.page == 2:
            self.scroll_target = clamp(self.scroll_target - direction * 60, 0, self.max_scroll)

    def on_key(self, e):
        if self.booting:
            self.boot_until = self.t
            return
        if isinstance(self.focus_get(), tk.Entry):
            return
        if e.char in "1234" and e.char:
            self.go(int(e.char) - 1)
        elif e.char.lower() == "s":
            self.scan_on = not self.scan_on
            self.cv.delete("scan")
            self.scan_size = (0, 0)
        elif e.char.lower() == "m" and self.page == 0:
            self.morph()

    def on_escape(self, e):
        if self.attributes("-fullscreen"):
            self.attributes("-fullscreen", False)
        self.cv.focus_set()

    def on_entry_key(self, ev, ent):
        geom = None
        for e, wid in self.form + [(self.search, self.search_win)]:
            if e is ent:
                geom = self.entry_pos.get(wid)
                break
        if geom:
            x, y, w, h = geom
            cx = x + min(w - 8, 10 * (len(ent.get()) + 1))
            self.burst(cx, y + h / 2, 6, [CYAN, YEL, MAG], speed=180)
        if ev.keysym == "Return":
            for i, (e, _) in enumerate(self.form):
                if e is ent:
                    if i < len(self.form) - 1:
                        self.form[i + 1][0].focus_set()
                    else:
                        self.start_upload()
                    return "break"
        if ev.keysym == "Escape":
            self.cv.focus_set()
        return None

    def _on_search(self):
        self.scroll_target = 0
        self.list_t0 = self.t

    def start_upload(self):
        if self.upload_start is None:
            self.upload_start = self.t

    # ------------------------------------------------------------ main loop
    def loop(self):
        now = time.perf_counter()
        self.dt = min(0.05, max(0.001, now - self.last))
        self.last = now
        self.t += self.dt
        self.page_t += self.dt
        self.fps += (1 / self.dt - self.fps) * 0.05
        try:
            self.simulate()
            self.render()
        except Exception:
            traceback.print_exc()
        self.after(16, self.loop)

    def simulate(self):
        dt = self.dt
        self.booting = self.t < self.boot_until
        self.warp = max(0.0, self.warp - dt * 1.4)
        if self.t > self.next_glitch:
            self.glitch_until = self.t + random.uniform(0.08, 0.2)
            self.next_glitch = self.t + random.uniform(4, 9)
        if not self.dragging:
            self.rx += self.spin_x * dt
            self.ry += self.spin_y * dt
            k = min(1, dt * 1.5)
            self.spin_x += (0.35 - self.spin_x) * k
            self.spin_y += (0.6 - self.spin_y) * k
        self.rz = math.sin(self.t * 0.4) * 0.25
        self.zoom += (self.zoom_target - self.zoom) * min(1, dt * 8)
        self.scroll += (self.scroll_target - self.scroll) * min(1, dt * 12)
        target = 1.0 if (self.selected is not None and self.page == 2) else 0.0
        self.detail_anim += (target - self.detail_anim) * min(1, dt * 9)

        for p in self.particles:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[2] *= 0.96
            p[3] = p[3] * 0.96 + 420 * dt
            p[4] -= dt
        self.particles = [p for p in self.particles if p[4] > 0]
        self.waves = [wv for wv in self.waves if self.t - wv[2] < 0.8]
        self.toasts = [ts for ts in self.toasts if self.t - ts[2] < 4.2]

        for s in self.stars:
            s[2] -= dt * 0.12 * (1 + self.warp * 12)
            if s[2] <= 0.04:
                s[0], s[1], s[2] = random.uniform(-1, 1), random.uniform(-1, 1), 1.0

        while self.pending:
            msg, col = self.pending.pop(0)
            if msg == "__reload__":
                self.reload(silent=True)
                self.run_terminal_capture()
            else:
                self.toast(msg, col)

        if self.upload_start is not None and self.t - self.upload_start > 0.9:
            self.upload_start = None
            self.commit_upload()

    def render(self):
        cv = self.cv
        cv.delete("dyn")
        self.hot = []
        self._placed = set()
        w, h = self._size()

        if self.booting:
            self.draw_boot(w, h)
        else:
            self.draw_background(w, h)
            self.draw_header(w, h)
            self.draw_sidebar(w, h)
            cx1, cy1, cx2, cy2 = 252, 96, w - 24, h - 46
            ease = ease_out(self.page_t / 0.5)
            ox = (1 - ease) * 70
            if self.t < self.shake_until:
                ox += math.sin(self.t * 70) * 12 * (self.shake_until - self.t) * 2
            pages = [self.draw_dashboard, self.draw_add, self.draw_catalog, self.draw_terminal]
            pages[self.page](cx1 + ox, cy1, cx2 + ox, cy2)
            if self.page_t < 0.3:
                self.draw_page_wipe(cx1, cy1, cx2, cy2)
            self.draw_footer(w, h)
            self.draw_toasts(w, h)

        self.draw_fx()
        if self.t < self.glitch_until:
            self.draw_glitch(w, h)

        for _, wid in self.form + [(self.search, self.search_win)]:
            if wid not in self._placed and self.entry_geom.get(wid) != "hidden":
                cv.itemconfigure(wid, state="hidden")
                self.entry_geom[wid] = "hidden"

        if self.scan_on:
            if self.scan_size != (w, h):
                cv.delete("scan")
                for y in range(0, h, 4):
                    cv.create_line(0, y, w, y, fill="#000000", tags="scan")
                self.scan_size = (w, h)
            cv.tag_raise("scan")

        want_hand = any(x1 <= self.mx <= x2 and y1 <= self.my <= y2 for x1, y1, x2, y2, _ in self.hot)
        hx1, hy1, hx2, hy2 = self.holo_rect
        if self.page == 0 and hx1 <= self.mx <= hx2 and hy1 <= self.my <= hy2 and not want_hand:
            cursor = "fleur"
        else:
            cursor = "hand2" if want_hand else "crosshair"
        if cursor != self.cursor_hand:
            cv.configure(cursor=cursor)
            self.cursor_hand = cursor

    # ------------------------------------------------------------ scenes
    def draw_boot(self, w, h):
        prog = clamp(self.t / self.boot_until)
        for i, (speed, off, chars) in enumerate(self.rain):
            x = (i / len(self.rain)) * w
            y = ((self.t * speed * 0.35 + off) % 1.4 - 0.4) * h
            body = "\n".join(chars[:18])
            self.T(x, y, body, self.f_rain, mix(BG, GREEN if i % 3 else CYAN, 0.35 * speed), "s")
            self.T(x, y + 2, chars[-1], self.f_rain, WHITE, "n")

        cx, cy = w / 2, h / 2
        self.wire(*([SHAPES[0][1](self.t * 2)] + [SHAPES[0][2]]), cx, cy - 150, 70 + prog * 10,
                  self.t, self.t * 1.3, 0, near=CYAN, far=MAG)
        self.P(chamfer(cx - 330, cy - 50, cx + 330, cy + 150, 20), fill=BG, outline=mix(BG, CYAN, 0.6))
        self.gtext(cx, cy - 20, "NEON//KATALOG", self.f_huge, WHITE, "center", amp=1.6)
        lines = [
            "> ESTABLISHING NEURAL LINK..........OK",
            "> DECRYPTING elektronik.csv.........OK",
            f"> LOADING {len(self.items):03d} HARDWARE SIGNATURES...OK",
            "> BRIDGING Main.py // tambah // tampil OK",
            "> RENDER ENGINE :: 3D HOLO CORE ONLINE",
        ]
        shown = int(self.t * 70)
        y = cy + 18
        for ln in lines:
            part = ln[: max(0, shown)]
            shown -= len(ln)
            self.T(cx - 300, y, part, self.f_small, CYAN if part.endswith("OK") else TXT)
            y += 16
        bx1, bx2, by = cx - 300, cx + 300, cy + 122
        self.R(bx1, by, bx2, by + 10, outline=mix(BG, CYAN, 0.6))
        self.R(bx1 + 2, by + 2, bx1 + 2 + (bx2 - bx1 - 4) * prog, by + 8, fill=MAG, outline="")
        self.T(bx2, by - 4, f"{int(prog * 100):3d}%", self.f_small, YEL, "se")
        if int(self.t * 3) % 2:
            self.T(cx, cy + 180, "[ PRESS ANY KEY TO JACK IN ]", self.f_small, MAG, "center")

    def draw_background(self, w, h):
        H0 = h * 0.6
        par = (self.mx - w / 2) / w if self.mx > 0 else 0
        vx = w / 2 - par * 80
        bands = 10
        for i in range(bands):
            y1 = H0 * i / bands
            self.R(0, y1, w, H0 * (i + 1) / bands + 1, fill=mix("#05010d", "#2a0845", i / bands), outline="")
        self.R(0, H0, w, h, fill="#06021a", outline="")

        cx, cy = w / 2 - par * 30, H0 * 0.45
        for x, y, z in self.stars:
            sx = cx + x / z * w * 0.12
            sy = cy + y / z * H0 * 0.18
            if not (0 <= sx <= w and 0 <= sy <= H0):
                continue
            z2 = min(1, z + 0.015 * (1 + self.warp * 10))
            px = cx + x / z2 * w * 0.12
            py = cy + y / z2 * H0 * 0.18
            col = mix(BG, WHITE if self.warp < 0.2 else CYAN, 1.1 - z)
            self.L(px, py, sx, sy + 0.5, fill=col, width=2 if z < 0.3 else 1)

        r = min(w, h) * 0.17
        sx = vx
        for dy in range(-int(r), 0, 3):
            yy = H0 + dy
            frac = (dy + r) / r
            if frac > 0.4 and (yy + self.t * 14) % 14 < (frac - 0.4) * 15:
                continue
            hw = math.sqrt(max(0, r * r - dy * dy))
            self.L(sx - hw, yy, sx + hw, yy, fill=mix(YEL, MAG, frac), width=3)

        for bx, bw, bh, wins, antenna, seed in self.buildings:
            x1 = bx * w - par * 40
            self.R(x1, H0 - bh, x1 + bw, H0, fill="#0b041c", outline=mix(BG, PURP, 0.55))
            for fx, fy, ws in wins:
                if int(self.t * 0.7 + ws * 10) % 4:
                    wx, wy = x1 + 4 + fx * (bw - 12), H0 - bh + 6 + fy * (bh - 16)
                    self.R(wx, wy, wx + 5, wy + 3, fill=YEL if ws > 0.5 else CYAN, outline="")
            if antenna:
                self.L(x1 + bw / 2, H0 - bh, x1 + bw / 2, H0 - bh - 22, fill=mix(BG, PURP, 0.8))
                if int(self.t * 2 + seed * 5) % 2:
                    self.O(x1 + bw / 2 - 2, H0 - bh - 25, x1 + bw / 2 + 2, H0 - bh - 21, fill=MAG, outline="")

        self.glow([0, H0, w, H0], MAG, 2)
        speed = 1.1 * (1 + self.warp * 5)
        phase = 1 - (self.t * speed % 1)
        for i in range(18):
            zz = i + phase
            if zz < 0.3:
                continue
            y = H0 + (h - H0) * 0.9 / zz
            if y > h:
                continue
            k = min(1.0, 0.9 / zz)
            self.L(0, y, w, y, fill=mix(BG, MAG, 0.15 + 0.6 * k), width=2 if k > 0.5 else 1)
        spread = w * 0.075
        for kx in range(-18, 19):
            self.L(vx + kx * 3, H0 + 1, vx + kx * spread, h, fill=mix(BG, MAG, 0.4))

    def draw_header(self, w, h):
        self.P([0, 0, w, 0, w, 66, w - 30, 76, 30, 76, 0, 66], fill=BG, outline="")
        verts, edges = SHAPES[1][1](self.t), SHAPES[1][2]
        self.wire(verts, edges, 44, 38, 20, self.t * 0.8, self.t * 1.2, 0, width=1, glow=False, dots=False)
        self.gtext(80, 12, "NEON//KATALOG", self.f_logo, WHITE, amp=0.6)
        self.T(82, 50, "ELECTRONIC INVENTORY MAINFRAME  //  v2.077  //  NIGHT CITY NODE 07", self.f_tiny, mix(BG, CYAN, 0.8))
        lt = time.localtime()
        self.T(w - 28, 14, time.strftime("%H:%M:%S", lt), self.f_h1, YEL, "ne")
        self.T(w - 28, 44, time.strftime("%a %d.%m.2077", lt).upper(), self.f_tiny, mix(BG, TXT, 0.7), "ne")
        blink = int(self.t * 2) % 2
        self.O(w - 250, 22, w - 242, 30, fill=GREEN if blink else mix(BG, GREEN, 0.4), outline="")
        self.T(w - 236, 26, "UPLINK STABLE", self.f_small, GREEN, "w")
        self.T(w - 236, 44, f"{self.fps:4.0f} FPS  //  {len(self.particles):03d} PX", self.f_tiny, mix(BG, CYAN, 0.7), "w")
        self.glow([30, 76, w - 30, 76], MAG, 1, 0.8)
        p = (self.t * 0.4) % 1
        px = 30 + p * (w - 60)
        self.L(px - 90, 76, px, 76, fill=CYAN, width=3)

    def draw_sidebar(self, w, h):
        x1, x2 = 20, 228
        y = 96
        for i, (label, sub, shape) in enumerate(NAV):
            y1, y2 = y, y + 58
            active = i == self.page
            hv, _ = self.hover(f"nav{i}", x1, y1, x2, y2)
            shift = hv * 8
            col = MAG if active else CYAN
            pts = chamfer(x1 + shift, y1, x2 + shift, y2, 12)
            self.P(pts, fill=mix(PANEL, col, 0.1 + 0.18 * hv + (0.15 if active else 0)), outline="")
            if active or hv > 0.05:
                self.glow(pts + pts[:2], col, 1, max(hv, 0.8 if active else 0))
            else:
                self.L(*(pts + pts[:2]), fill=mix(BG, CYAN, 0.35))
            if active:
                pulse = 0.6 + 0.4 * math.sin(self.t * 6)
                self.glow([x1 + shift + 3, y1 + 12, x1 + shift + 3, y2 - 12], MAG, 3, pulse)
            vs, es = SHAPES[shape][1](self.t), SHAPES[shape][2]
            spd = 3.0 if (hv > 0.3 or active) else 0.8
            self.wire(vs, es, x1 + shift + 30, (y1 + y2) / 2, 11 + hv * 3, self.t * spd, self.t * spd * 1.3, 0,
                      near=col, far=mix(BG, col, 0.4), width=1, glow=False, dots=False)
            self.T(x1 + shift + 54, y1 + 14, label, self.f_h2, WHITE if active else mix(TXT, col, hv))
            self.T(x1 + shift + 54, y1 + 36, sub, self.f_tiny, mix(BG, col, 0.75))
            self.T(x2 + shift - 10, y1 + 8, f"[{i + 1}]", self.f_tiny, mix(BG, YEL, 0.5 + hv * 0.5), "ne")
            self.hotspot(x1, y1, x2 + 8, y2, lambda i=i: self.go(i))
            y += 68

        my1, my2 = y + 10, h - 46
        if my2 - my1 < 120:
            return
        self.panel(x1, my1, x2, my2, "SYS//MONITOR", PURP, CYAN)
        oy = my1 + 54
        pts = []
        for k in range(48):
            xx = x1 + 14 + k * (x2 - x1 - 28) / 47
            v = math.sin(k * 0.45 + self.t * 5) * 10 + math.sin(k * 1.7 - self.t * 9) * 5 * (0.5 + 0.5 * math.sin(self.t))
            pts += [xx, oy + v]
        self.glow(pts, GREEN, 1, 0.7)
        bars = [("CPU", 0.55 + 0.35 * math.sin(self.t * 1.7)), ("RAM", 0.62 + 0.12 * math.sin(self.t * 0.6)),
                ("NET", 0.5 + 0.45 * math.sin(self.t * 3.1 + 1))]
        by = oy + 28
        for name, v in bars:
            self.T(x1 + 14, by, name, self.f_tiny, mix(BG, TXT, 0.8))
            self.R(x1 + 46, by + 2, x2 - 14, by + 9, outline=mix(BG, PURP, 0.7))
            self.R(x1 + 47, by + 3, x1 + 47 + (x2 - x1 - 62) * clamp(v), by + 8,
                   fill=MAG if v > 0.8 else CYAN, outline="")
            by += 18
        rr = min((x2 - x1) / 2 - 30, (my2 - by - 40) / 2)
        if rr > 26:
            rcx, rcy = (x1 + x2) / 2, by + 14 + rr
            for k in (1.0, 0.66, 0.33):
                self.O(rcx - rr * k, rcy - rr * k, rcx + rr * k, rcy + rr * k, outline=mix(BG, GREEN, 0.35))
            ang = self.t * 2.2
            self.A(rcx - rr, rcy - rr, rcx + rr, rcy + rr, start=-math.degrees(ang), extent=40, style="pieslice",
                   fill=mix(BG, GREEN, 0.25), outline="")
            self.L(rcx, rcy, rcx + math.cos(ang) * rr, rcy + math.sin(ang) * rr, fill=GREEN, width=2)
            for it in self.items:
                a = hash01(it.nomor_seri) * math.tau
                d = (0.25 + 0.7 * hash01(it.nama_barang)) * rr
                diff = (ang - a) % math.tau
                bright = clamp(1 - diff / 2.5)
                bx, byy = rcx + math.cos(a) * d, rcy + math.sin(a) * d
                c = mix(BG, GREEN if is_available(it) else MAG, 0.25 + bright * 0.75)
                self.O(bx - 2.5, byy - 2.5, bx + 2.5, byy + 2.5, fill=c, outline="")
            self.T(rcx, rcy + rr + 8, f"{len(self.items):03d} SIGNALS TRACKED", self.f_tiny, mix(BG, GREEN, 0.8), "n")

    def draw_footer(self, w, h):
        y = h - 30
        self.L(20, y - 6, w - 20, y - 6, fill=mix(BG, CYAN, 0.35))
        ticker = "   ///   ".join(f"{i.nama_barang.upper()} [{i.merek.upper()}] SN:{i.nomor_seri} :: {i.status.upper()}"
                                  for i in self.items) or "NO DATA IN VAULT"
        ticker = "LIVE FEED >>  " + ticker + "   ///   "
        tw = len(ticker) * 7
        x = w - 420 - ((self.t * 70) % (tw + w - 420))
        self.T(x, y + 6, ticker, self.f_tiny, mix(BG, CYAN, 0.8), "w")
        self.R(0, y - 4, 250, h, fill=BG, outline="")
        self.R(w - 430, y - 4, w, h, fill=BG, outline="")
        self.T(24, y + 6, "> NEON_OS :: READY_", self.f_tiny, YEL, "w")
        self.T(w - 24, y + 6, "[1-4] NAV  [F5] SYNC  [F11] FULL  [S] SCANLINES  [M] MORPH", self.f_tiny,
               mix(BG, MAG, 0.85), "e")

    def draw_page_wipe(self, x1, y1, x2, y2):
        p = self.page_t / 0.3
        yy = y1 + (y2 - y1) * ease_out(p)
        self.glow([x1, yy, x2, yy], CYAN, 2, 1 - p)
        for _ in range(5):
            gy = random.uniform(y1, y2)
            gx = random.uniform(x1, x2 - 200)
            self.R(gx, gy, gx + random.uniform(60, 260), gy + random.uniform(2, 8),
                   fill=random.choice([MAG, CYAN, PURP]), outline="")

    def draw_glitch(self, w, h):
        for _ in range(7):
            gy = random.uniform(0, h)
            gh = random.uniform(2, 14)
            gx = random.uniform(-100, w)
            self.R(gx, gy, gx + random.uniform(80, 500), gy + gh, fill=random.choice([MAG, CYAN, BG, PURP]),
                   outline="", stipple=self.stipple or "")

    def draw_fx(self):
        pts = list(self.trail)
        if not self.booting and len(pts) > 1:
            n = len(pts)
            for i in range(1, n):
                age = self.t - pts[i][2]
                if age > 0.4:
                    continue
                k = (i / n) * (1 - age / 0.4)
                self.L(pts[i - 1][0], pts[i - 1][1], pts[i][0], pts[i][1], fill=mix(BG, CYAN if i % 2 else MAG, k),
                       width=1 + k * 4, capstyle="round")
        for x, y, t0, col, rmax in self.waves:
            age = self.t - t0
            if age < 0:
                continue
            k = age / 0.8
            r = ease_out(k) * rmax
            self.O(x - r, y - r, x + r, y + r, outline=mix(BG, col, 1 - k), width=max(1, 4 * (1 - k)))
        for x, y, vx, vy, life, maxlife, col in self.particles:
            k = life / maxlife
            self.L(x, y, x - vx * 0.03, y - vy * 0.03, fill=mix(BG, col, k), width=2 if k > 0.5 else 1)

    def draw_toasts(self, w, h):
        y = 92
        for text, col, t0 in reversed(self.toasts):
            age = self.t - t0
            slide = ease_back(age / 0.35) if age < 0.35 else 1.0
            if age > 3.8:
                slide = 1 - ease_out((age - 3.8) / 0.4)
            tw = min(520, 60 + len(text) * 7.2)
            x2 = w - 24
            x1 = x2 - tw * slide
            if slide <= 0.01:
                continue
            pts = chamfer(x1, y, x2, y + 44, 10)
            self.P(pts, fill=mix(BG, col, 0.14), outline="")
            self.glow(pts + pts[:2], col, 1, 0.9)
            self.R(x1, y, x1 + 6, y + 44, fill=col, outline="")
            shown = text[: int(age * 90)]
            cursor = "_" if int(self.t * 4) % 2 else " "
            self.T(x1 + 18, y + 22, shown + cursor, self.f_small, mix(col, WHITE, 0.4), "w")
            prog = clamp(age / 4.2)
            self.L(x1 + 8, y + 42, x1 + 8 + (x2 - x1 - 16) * (1 - prog), y + 42, fill=col, width=2)
            y += 54

    # ------------------------------------------------------------ pages
    def draw_hologram(self, x1, y1, x2, y2):
        self.panel(x1, y1, x2, y2, "HOLO-PROJECTOR", CYAN, MAG)
        self.holo_rect = (x1, y1 + 24, x2, y2)
        cx = (x1 + x2) / 2
        by = y2 - 64
        oy = y1 + (by - y1) * 0.5 + 10
        size = min(x2 - x1, by - y1) * 0.26 * self.zoom
        mt = self.t - self.morph_t
        if mt < 0.7:
            size *= 1 + 0.45 * math.sin(mt * 18) * (1 - mt / 0.7)

        for k in range(4):
            rx = 70 + k * 30 + math.sin(self.t * 2 + k) * 5
            ry = rx * 0.24
            self.O(cx - rx, by - ry, cx + rx, by + ry, outline=mix(BG, CYAN if k % 2 == 0 else MAG, 0.7 - k * 0.14),
                   width=2 if k == 0 else 1)
        rot = self.t * 90
        self.A(cx - 150, by - 36, cx + 150, by + 36, start=rot, extent=60, style="arc", outline=YEL, width=2)
        self.A(cx - 150, by - 36, cx + 150, by + 36, start=rot + 180, extent=60, style="arc", outline=YEL, width=2)
        self.P([cx - 70, by, cx + 70, by, cx + size * 1.1, oy, cx - size * 1.1, oy], fill=mix(BG, CYAN, 0.12),
               outline="", stipple="gray25" if self.stipple else "")
        self.L(cx - 70, by, cx - size * 1.1, oy, fill=mix(BG, CYAN, 0.4))
        self.L(cx + 70, by, cx + size * 1.1, oy, fill=mix(BG, CYAN, 0.4))
        for bxr, ph, sp in self.beam_dots:
            k = (self.t * 0.4 * sp + ph) % 1
            yy = by + (oy - by) * k
            xx = cx + bxr * (70 + (size * 1.1 - 70) * k)
            self.O(xx - 1.5, yy - 1.5, xx + 1.5, yy + 1.5, fill=mix(BG, CYAN, 1 - k), outline="")

        name, vfn, edges = SHAPES[self.shape_idx]
        verts = vfn(self.t)
        jx = random.uniform(-6, 6) if (random.random() < 0.04 or self.t < self.glitch_until) else 0
        if jx:
            self.wire(verts, edges, cx + jx * 2, oy, size, self.rx, self.ry, self.rz, near=MAG, far=BG, width=1,
                      glow=False, dots=False)
        proj = self.wire(verts, edges, cx + jx, oy, size, self.rx, self.ry, self.rz, near=CYAN, far=PURP, width=2)

        ys = [p[1] for p in proj]
        top, bot = min(ys), max(ys)
        sy = top + (bot - top) * ((self.t * 0.6) % 1)
        self.L(cx - size * 1.3, sy, cx + size * 1.3, sy, fill=mix(BG, CYAN, 0.6))

        for k in range(3):
            a = self.t * (1.2 + k * 0.4) + k * 2.1
            ex, ez = math.cos(a) * size * (1.5 + k * 0.15), math.sin(a)
            ey = math.sin(a) * size * 0.35
            r = 3 + (1 - ez) * 1.5
            col = [YEL, MAG, GREEN][k]
            self.O(cx + ex - r, oy + ey - r, cx + ex + r, oy + ey + r, fill=col, outline="")

        self.gtext(x1 + 26, y1 + 36, name, self.f_h2, WHITE, amp=0.5)
        self.T(x1 + 26, y1 + 58, f"SHAPE {self.shape_idx + 1}/{len(SHAPES)}  //  ZOOM {self.zoom:.1f}x  //  "
                                 f"RX {math.degrees(self.rx) % 360:05.1f}  RY {math.degrees(self.ry) % 360:05.1f}",
               self.f_tiny, mix(BG, CYAN, 0.8))
        self.T(cx, y2 - 18, "[ DRAG = ROTATE   SCROLL = ZOOM   CLICK = MORPH ]", self.f_tiny,
               mix(BG, MAG, 0.6 + 0.4 * math.sin(self.t * 3)), "center")

    def stat_card(self, key, x1, y1, x2, y2, label, value, color, sub, delay=0.0):
        hv, _ = self.hover(key, x1, y1, x2, y2)
        e = ease_back((self.page_t - delay) / 0.6)
        if e <= 0:
            return
        lift = hv * 6
        y1 -= lift
        y2 -= lift
        ox = (1 - e) * 40
        x1 += ox
        x2 += ox
        pts = chamfer(x1, y1, x2, y2, 14)
        self.P(pts, fill=mix(PANEL, color, 0.06 + 0.12 * hv), outline="")
        self.glow(pts + pts[:2], mix(DIM, color, 0.5 + 0.5 * hv), 1, 0.4 + 0.6 * hv)
        self.T(x1 + 16, y1 + 12, label, self.f_small, color)
        shown = int(round(value * ease_out((self.page_t - delay) / 1.2)))
        self.gtext(x1 + 16, y1 + 30, f"{shown:03d}", self.f_big, WHITE, amp=0.2 + hv)
        self.T(x1 + 16, y2 - 16, sub, self.f_tiny, mix(BG, TXT, 0.65), "w")
        for k in range(8):
            bh = 6 + (math.sin(self.t * 4 + k * 0.9 + hash01(key) * 6) * 0.5 + 0.5) * 22 * (0.5 + hv)
            bx = x2 - 20 - (7 - k) * 8
            self.R(bx, y2 - 12 - bh, bx + 5, y2 - 12, fill=mix(BG, color, 0.4 + k * 0.07), outline="")

    def draw_dashboard(self, x1, y1, x2, y2):
        hx2 = x1 + (x2 - x1) * 0.45
        self.draw_hologram(x1, y1, hx2, y2)

        rx1 = hx2 + 18
        total = len(self.items)
        avail = sum(1 for i in self.items if is_available(i))
        used = total - avail
        cw = (x2 - rx1 - 24) / 3
        cards = [("TOTAL UNITS", total, CYAN, "IN DATA VAULT"), ("TERSEDIA", avail, GREEN, "READY TO DEPLOY"),
                 ("DIPINJAM", used, MAG, "OUT IN THE FIELD")]
        for k, (lab, val, col, sub) in enumerate(cards):
            cx1 = rx1 + k * (cw + 12)
            self.stat_card(f"card{k}", cx1, y1, cx1 + cw, y1 + 116, lab, val, col, sub, delay=k * 0.12)

        my1 = y1 + 134
        mid_h = (y2 - my1) * 0.55
        gx2 = rx1 + (x2 - rx1) * 0.42
        self.panel(rx1, my1, gx2, my1 + mid_h, "AVAILABILITY", GREEN, CYAN)
        gcx, gcy = (rx1 + gx2) / 2, my1 + mid_h / 2 + 12
        gr = min(gx2 - rx1, mid_h) * 0.32
        pct = avail / total if total else 0
        e = ease_out(self.page_t / 1.4)
        self.O(gcx - gr, gcy - gr, gcx + gr, gcy + gr, outline=mix(BG, GREEN, 0.18), width=12)
        self.A(gcx - gr, gcy - gr, gcx + gr, gcy + gr, start=90, extent=-359.9 * pct * e, style="arc",
               outline=mix(BG, GREEN, 0.35), width=20)
        self.A(gcx - gr, gcy - gr, gcx + gr, gcy + gr, start=90, extent=-359.9 * pct * e, style="arc",
               outline=GREEN, width=10)
        ring = gr + 16
        for k in range(10):
            self.A(gcx - ring, gcy - ring, gcx + ring, gcy + ring, start=self.t * 50 + k * 36, extent=18,
                   style="arc", outline=mix(BG, CYAN, 0.6), width=2)
        ring2 = gr + 26
        self.A(gcx - ring2, gcy - ring2, gcx + ring2, gcy + ring2, start=-self.t * 80, extent=120, style="arc",
               outline=MAG, width=2)
        self.T(gcx, gcy - 6, f"{int(pct * 100 * e)}%", self.f_big, WHITE, "center")
        self.T(gcx, gcy + 24, "ONLINE", self.f_tiny, GREEN, "center")

        bx1 = gx2 + 14
        self.panel(bx1, my1, x2, my1 + mid_h, "BRAND MATRIX", MAG, YEL)
        brands = Counter(i.merek.strip().upper() or "?" for i in self.items).most_common(6)
        maxc = max([c for _, c in brands] or [1])
        bar_y = my1 + 40
        row_h = max(18, min(32, (mid_h - 56) / max(1, len(brands))))
        bw = x2 - bx1 - 130
        for k, (brand, count) in enumerate(brands):
            hv, _ = self.hover(f"brand{k}", bx1 + 10, bar_y, x2 - 10, bar_y + row_h - 4)
            pe = ease_out((self.page_t - 0.2 - k * 0.1) / 0.8)
            ww = bw * (count / maxc) * pe
            self.T(bx1 + 18, bar_y + row_h / 2 - 2, brand[:10], self.f_small, mix(TXT, YEL, hv), "w")
            col = [MAG, CYAN, YEL, GREEN, PURP, MAG][k]
            xb = bx1 + 100
            self.R(xb, bar_y + 3, xb + ww + hv * 10, bar_y + row_h - 7, fill=mix(BG, col, 0.5 + hv * 0.5), outline="")
            self.L(xb, bar_y + 3, xb + ww + hv * 10, bar_y + 3, fill=col, width=2)
            self.T(xb + ww + hv * 10 + 8, bar_y + row_h / 2 - 2, str(count), self.f_small, col, "w")
            bar_y += row_h

        ly1 = my1 + mid_h + 18
        if y2 - ly1 > 70:
            self.panel(rx1, ly1, x2, y2, "RECENT UPLINKS", YEL, MAG)
            yy = ly1 + 34
            for k, it in enumerate(list(reversed(self.items))[: max(0, int((y2 - ly1 - 40) / 22))]):
                txt = f"> {it.nama_barang.upper()[:28]:<28}  {it.merek.upper()[:12]:<12}  SN:{it.nomor_seri}"
                n = int((self.page_t - k * 0.15) * 60)
                self.O(rx1 + 22, yy + 4, rx1 + 30, yy + 12, fill=GREEN if is_available(it) else MAG, outline="")
                self.T(rx1 + 40, yy, txt[: max(0, n)], self.f_small, mix(TXT, CYAN, 0.3))
                yy += 22

    def draw_add(self, x1, y1, x2, y2):
        fx2 = x1 + (x2 - x1) * 0.58
        self.panel(x1, y1, fx2, y2, "UPLOAD PROTOCOL // tambah_elektronik.simpan_elektronik()", CYAN, MAG)
        self.gtext(x1 + 30, y1 + 40, "REGISTER NEW HARDWARE", self.f_h1, WHITE, amp=0.4)
        self.T(x1 + 30, y1 + 70, "Data dikirim ke fungsi asli simpan_elektronik() -> elektronik.csv", self.f_tiny,
               mix(BG, CYAN, 0.75))
        labels = ["01 // NAMA BARANG", "02 // MEREK", "03 // NOMOR SERI"]
        focus = self.focus_get()
        y = y1 + 108
        fw = fx2 - x1 - 60
        filled = 0
        for k, (ent, wid) in enumerate(self.form):
            appear = ease_out((self.page_t - k * 0.1) / 0.5)
            ox = (1 - appear) * 60
            is_f = focus is ent
            fa = self.hov.get(f"focus{k}", 0.0)
            fa += ((1.0 if is_f else 0.0) - fa) * min(1, self.dt * 10)
            self.hov[f"focus{k}"] = fa
            col = mix(DIM, CYAN, 0.35 + fa * 0.65)
            self.T(x1 + 30 + ox, y, labels[k], self.f_small, mix(MAG, YEL, fa))
            val = ent.get()
            if val.strip():
                filled += 1
                self.T(fx2 - 30 + ox, y, "[ OK ]", self.f_tiny, GREEN, "ne")
            ex1, ey1, ex2, ey2 = x1 + 30 + ox, y + 18, x1 + 30 + fw + ox, y + 58
            pts = chamfer(ex1, ey1, ex2, ey2, 10)
            self.P(pts, fill=ENTRY_BG, outline="")
            if fa > 0.05:
                self.glow(pts + pts[:2], col, 1, fa)
                br = 10 + 4 * math.sin(self.t * 8)
                for cxx, cyy, dx, dy in ((ex1 - 6, ey1 - 6, 1, 1), (ex2 + 6, ey1 - 6, -1, 1),
                                         (ex1 - 6, ey2 + 6, 1, -1), (ex2 + 6, ey2 + 6, -1, -1)):
                    self.L(cxx + dx * br, cyy, cxx, cyy, cxx, cyy + dy * br, fill=YEL, width=2)
            else:
                self.L(*(pts + pts[:2]), fill=col)
            self.T(ex1 + 12, (ey1 + ey2) / 2, ">", self.f_mono_b, MAG, "w")
            self.place_entry(wid, ex1 + 28, ey1 + 8, ex2 - ex1 - 40, ey2 - ey1 - 16)
            lvl = clamp(len(val) / 24)
            self.L(ex1 + 10, ey2 + 6, ex1 + 10 + (ex2 - ex1 - 20) * lvl, ey2 + 6, fill=mix(CYAN, MAG, lvl), width=2)
            y += 92

        by = y + 6
        bw = fw
        if self.upload_start is not None:
            p = clamp((self.t - self.upload_start) / 0.9)
            pts = chamfer(x1 + 30, by, x1 + 30 + bw, by + 52, 10)
            self.P(pts, fill=mix(PANEL, MAG, 0.15), outline="")
            self.R(x1 + 34, by + 4, x1 + 34 + (bw - 8) * p, by + 48, fill=mix(BG, MAG, 0.7), outline="")
            self.glow(pts + pts[:2], MAG, 1)
            self.T(x1 + 30 + bw / 2, by + 26, f"UPLOADING TO MAINFRAME ... {int(p * 100)}%", self.f_btn, WHITE, "center")
        else:
            half = (bw - 12) * 0.7
            self.button("upload", x1 + 30, by, x1 + 30 + half, by + 52, ">> UPLOAD TO MAINFRAME <<",
                        self.start_upload, MAG)
            self.button("clear", x1 + 42 + half, by, x1 + 30 + bw, by + 52, "PURGE", self.clear_form, CYAN)
        self.T(x1 + 30, by + 66, "[ENTER] next field / upload    [ESC] release focus", self.f_tiny,
               mix(BG, TXT, 0.55))

        px1 = fx2 + 18
        self.panel(px1, y1, x2, y2, "LIVE PREVIEW", MAG, CYAN)
        cx = (px1 + x2) / 2
        name = self.form[0][0].get().strip() or "UNKNOWN DEVICE"
        merek = self.form[1][0].get().strip() or "---"
        sn = self.form[2][0].get().strip() or "SN-????"
        preview = Elektronik(name, merek, sn)
        shape = int(hash01(name) * len(SHAPES)) if name != "UNKNOWN DEVICE" else 4
        vfn, edges = SHAPES[shape][1], SHAPES[shape][2]
        ph = (y2 - y1)
        ocy = y1 + ph * 0.3
        sz = min(x2 - px1, ph) * 0.17
        rr = sz * 1.7
        self.O(cx - rr, ocy - rr, cx + rr, ocy + rr, outline=mix(BG, MAG, 0.3), width=6)
        self.A(cx - rr, ocy - rr, cx + rr, ocy + rr, start=90, extent=-359.9 * ease_out(filled / 3 * 0.999 + 0.001),
               style="arc", outline=GREEN if filled == 3 else MAG, width=6)
        self.T(cx, ocy + rr + 12, f"INTEGRITY {filled}/3", self.f_tiny, GREEN if filled == 3 else MAG, "n")
        self.wire(vfn(self.t), edges, cx, ocy, sz, self.t * 0.7, self.t * 1.1, 0.3, near=MAG, far=PURP)

        ty = ocy + rr + 40
        self.T(cx, ty, preview.nama_barang.upper()[:22], self.f_h2, WHITE, "n")
        self.T(cx, ty + 26, f"MFR :: {preview.merek.upper()[:20]}", self.f_small, CYAN, "n")
        self.T(cx, ty + 44, f"SN  :: {preview.nomor_seri[:20]}", self.f_small, YEL, "n")
        pill = preview.status.upper()
        self.R(cx - 50, ty + 66, cx + 50, ty + 86, fill=mix(BG, GREEN, 0.25), outline=GREEN)
        self.T(cx, ty + 76, pill, self.f_tiny, GREEN, "center")
        self.draw_barcode(cx - 110, ty + 100, 220, 34, preview.nomor_seri)
        self.T(cx, y2 - 20, str(preview)[:46], self.f_tiny, mix(BG, TXT, 0.6), "center")

    def clear_form(self):
        for e, _ in self.form:
            e.delete(0, "end")
        self.toast("BUFFER PURGED", CYAN)
        self.form[0][0].focus_set()

    def draw_barcode(self, x, y, w, h, seed):
        rnd = random.Random(str(seed))
        xx = x
        k = 0
        while xx < x + w:
            bw = rnd.choice([1, 1, 2, 3])
            if k % 2 == 0:
                self.R(xx, y, xx + bw, y + h, fill=mix(TXT, CYAN, rnd.random()), outline="")
            xx += bw + 1
            k += 1
        sy = y + ((self.t * 1.2) % 1) * h
        self.L(x - 6, sy, x + w + 6, sy, fill=MAG, width=2)

    def filtered(self):
        q = self.search.get().strip().lower()
        out = []
        for it in self.items:
            if self.filter_mode == "TERSEDIA" and not is_available(it):
                continue
            if self.filter_mode == "DIPINJAM" and is_available(it):
                continue
            if q and q not in f"{it.nama_barang} {it.merek} {it.nomor_seri} {it.status}".lower():
                continue
            out.append(it)
        return out

    def set_filter(self, mode):
        self.filter_mode = mode
        self.scroll_target = 0
        self.list_t0 = self.t
        self.warp = 0.6

    def select(self, item):
        self.selected = None if self.selected is item else item
        self.glitch_until = self.t + 0.1

    def draw_catalog(self, x1, y1, x2, y2):
        self.panel(x1, y1, x2, y2, "DATA VAULT // tampil_elektronik.muat_data()", CYAN, MAG)
        da = self.detail_anim
        lx1 = x1 + 24
        lx2 = x2 - 24 - 350 * da
        sy = y1 + 36

        sw = min(300, lx2 - lx1 - 420)
        sw = max(170, sw)
        pts = chamfer(lx1, sy, lx1 + sw, sy + 40, 10)
        foc = self.focus_get() is self.search
        self.P(pts, fill=ENTRY_BG, outline="")
        if foc:
            self.glow(pts + pts[:2], CYAN, 1)
        else:
            self.L(*(pts + pts[:2]), fill=mix(BG, CYAN, 0.45))
        self.O(lx1 + 12, sy + 12, lx1 + 26, sy + 26, outline=MAG, width=2)
        self.L(lx1 + 24, sy + 24, lx1 + 30, sy + 30, fill=MAG, width=2)
        self.place_entry(self.search_win, lx1 + 38, sy + 9, sw - 48, 22)
        if not self.search.get() and not foc:
            self.T(lx1 + 40, sy + 20, "SCAN QUERY...", self.f_small, mix(BG, CYAN, 0.45), "w")

        cxp = lx1 + sw + 14
        for mode, col in (("ALL", CYAN), ("TERSEDIA", GREEN), ("DIPINJAM", MAG)):
            cw = len(mode) * 9 + 28
            active = self.filter_mode == mode
            hv, _ = self.hover(f"chip{mode}", cxp, sy + 4, cxp + cw, sy + 36)
            pts = chamfer(cxp, sy + 4, cxp + cw, sy + 36, 8)
            self.P(pts, fill=mix(PANEL, col, (0.4 if active else 0.06) + hv * 0.15), outline="")
            self.L(*(pts + pts[:2]), fill=col if active or hv > 0.3 else mix(BG, col, 0.5))
            self.T(cxp + cw / 2, sy + 20, mode, self.f_small, WHITE if active else col, "center")
            self.hotspot(cxp, sy + 4, cxp + cw, sy + 36, lambda m=mode: self.set_filter(m))
            cxp += cw + 8
        if lx2 - cxp > 110:
            self.button("refresh", lx2 - 104, sy, lx2, sy + 40, "SYNC  F5", self.reload, YEL)

        rows = self.filtered()
        hy = sy + 56
        W = lx2 - lx1
        cols = [(0.0, "#"), (0.07, "NAMA BARANG"), (0.43, "MEREK"), (0.62, "NOMOR SERI"), (0.83, "STATUS")]
        for fx, label in cols:
            self.T(lx1 + 14 + fx * W, hy, label, self.f_small, mix(BG, YEL, 0.85))
        self.T(lx2, y2 - 6, f"SHOWING {len(rows):02d}/{len(self.items):02d}", self.f_tiny, mix(BG, CYAN, 0.8), "se")
        self.L(lx1, hy + 20, lx2, hy + 20, fill=mix(BG, CYAN, 0.5))

        ly1, ly2 = hy + 30, y2 - 22
        rh = 50
        self.max_scroll = max(0, len(rows) * rh - (ly2 - ly1))
        self.scroll_target = clamp(self.scroll_target, 0, self.max_scroll)

        if not rows:
            self.gtext((lx1 + lx2) / 2, (ly1 + ly2) / 2 - 10, "NO SIGNAL", self.f_huge, MAG, "center", amp=1.5)
            self.T((lx1 + lx2) / 2, (ly1 + ly2) / 2 + 34, "0 MATCHES IN DATA VAULT // ADJUST QUERY", self.f_small,
                   mix(BG, TXT, 0.6), "center")

        for idx, it in enumerate(rows):
            ry = ly1 + idx * rh - self.scroll
            if ry < ly1 - 2 or ry + rh - 6 > ly2:
                continue
            ent = ease_out((self.t - self.list_t0 - idx * 0.05) / 0.45)
            if ent <= 0:
                continue
            ox = (1 - ent) * 120
            key = f"row{it.nomor_seri}{idx}"
            hv, _ = self.hover(key, lx1, ry, lx2, ry + rh - 6)
            sel = it is self.selected
            avail = is_available(it)
            scol = GREEN if avail else MAG
            sk = hv * 9
            xa, xb = lx1 + ox + hv * 6, lx2 + ox
            pts = [xa + sk, ry, xb, ry, xb - sk, ry + rh - 8, xa, ry + rh - 8]
            base = mix(PANEL, CYAN, 0.05 + hv * 0.14 + (0.12 if sel else 0))
            self.P(pts, fill=mix(BG, base, ent), outline="")
            if sel:
                self.glow(pts + pts[:2], MAG, 1)
            elif hv > 0.05:
                self.glow(pts + pts[:2], CYAN, 1, hv)
            else:
                self.L(*(pts + pts[:2]), fill=mix(BG, DIM, ent))
            self.P([xa + sk, ry, xa + sk + 5, ry, xa + 5, ry + rh - 8, xa, ry + rh - 8], fill=scol, outline="")
            mid = ry + (rh - 8) / 2
            tc = lambda c: mix(BG, c, ent)
            self.T(xa + 14 + 0 * W, mid, f"{idx + 1:02d}", self.f_small, tc(mix(BG, CYAN, 0.6)), "w")
            self.T(xa + 14 + 0.07 * W, mid, it.nama_barang[:30], self.f_mono_b, tc(mix(TXT, WHITE, hv)), "w")
            self.T(xa + 14 + 0.43 * W, mid, it.merek[:16].upper(), self.f_small, tc(CYAN), "w")
            self.T(xa + 14 + 0.62 * W, mid, it.nomor_seri[:18], self.f_small, tc(YEL), "w")
            px = xa + 14 + 0.83 * W
            pw = len(it.status) * 7 + 22
            pulse = 0.25 + 0.15 * math.sin(self.t * 5 + idx)
            self.R(px, mid - 10, px + pw, mid + 10, fill=mix(BG, scol, pulse * ent), outline=tc(scol))
            self.T(px + pw / 2, mid, it.status.upper(), self.f_tiny, tc(scol), "center")
            self.hotspot(lx1, ry, lx2, ry + rh - 8, lambda it=it: self.select(it))

        if self.max_scroll > 0:
            track = ly2 - ly1
            th = max(30, track * (track / (track + self.max_scroll)))
            ty = ly1 + (track - th) * (self.scroll / self.max_scroll)
            self.R(lx2 + 8, ly1, lx2 + 11, ly2, fill=mix(BG, CYAN, 0.2), outline="")
            self.R(lx2 + 7, ty, lx2 + 12, ty + th, fill=MAG, outline="")

        if da > 0.02 and self.selected is not None:
            self.draw_detail(x2 - 24 - 330 + (1 - da) * 380, y1 + 34, x2 - 24 + (1 - da) * 380, y2 - 20, self.selected)

    def draw_detail(self, x1, y1, x2, y2, it):
        avail = is_available(it)
        col = GREEN if avail else MAG
        pts = chamfer(x1, y1, x2, y2, 16)
        self.P(pts, fill=mix(BG, PANEL, 0.9), outline="")
        self.glow(pts + pts[:2], MAG, 1, 0.8)
        self.T(x1 + 18, y1 + 16, "UNIT DOSSIER", self.f_small, MAG)
        self.button("close", x2 - 44, y1 + 10, x2 - 12, y1 + 38, "X", lambda: self.select(it), MAG)
        cx = (x1 + x2) / 2
        ocy = y1 + 120
        shape = int(hash01(it.nama_barang) * len(SHAPES))
        vfn, edges = SHAPES[shape][1], SHAPES[shape][2]
        for k in range(3):
            r = 60 + k * 14 + math.sin(self.t * 3 + k) * 3
            self.A(cx - r, ocy - r, cx + r, ocy + r, start=self.t * (60 + k * 40) * (-1) ** k, extent=100 + k * 30,
                   style="arc", outline=mix(BG, [CYAN, MAG, YEL][k], 0.7), width=2)
        self.wire(vfn(self.t), edges, cx, ocy, 42, self.t * 0.9, self.t * 1.3, 0, near=col, far=PURP)
        y = ocy + 96
        self.cv.create_text(cx, y, text=it.nama_barang.upper(), font=self.f_h2, fill=WHITE, anchor="n",
                            width=x2 - x1 - 40, justify="center", tags="dyn")
        y += 44
        for label, val, c in (("MEREK", it.merek, CYAN), ("NOMOR SERI", it.nomor_seri, YEL), ("STATUS", it.status, col)):
            self.T(x1 + 22, y, label, self.f_tiny, mix(BG, TXT, 0.6))
            self.T(x2 - 22, y, val.upper()[:22], self.f_small, c, "ne")
            self.L(x1 + 22, y + 18, x2 - 22, y + 18, fill=mix(BG, DIM, 0.8))
            y += 28
        if y2 - y > 90:
            self.draw_barcode(x1 + 22, y + 6, x2 - x1 - 44, 30, it.nomor_seri)
            y += 50
        if y2 - y > 80:
            rnd = random.Random(it.nomor_seri + it.nama_barang)
            cell = 9
            gx = cx - cell * 5
            for r in range(10):
                for c in range(10):
                    on = rnd.random() < 0.5
                    if on:
                        flick = 0.6 + 0.4 * math.sin(self.t * 4 + r + c)
                        self.R(gx + c * cell, y + r * cell, gx + c * cell + cell - 2, y + r * cell + cell - 2,
                               fill=mix(BG, col, flick), outline="")

    def draw_terminal(self, x1, y1, x2, y2):
        self.panel(x1, y1, x2, y2, "LEGACY TERMINAL // Main.py BRIDGE", GREEN, MAG)
        by = y1 + 36
        bw = (x2 - x1 - 48 - 24) / 3
        btns = [
            ("RUN tampilkan_elektronik()", self.run_terminal_capture, GREEN),
            ("SPAWN Main.buka_tambah_elektronik()",
             lambda: self.launch_legacy(Main.buka_tambah_elektronik, "TAMBAH MODULE"), YEL),
            ("SPAWN Main.buka_tampil_elektronik()",
             lambda: self.launch_legacy(Main.buka_tampil_elektronik, "TAMPIL MODULE"), MAG),
        ]
        for k, (lab, cb, col) in enumerate(btns):
            bx = x1 + 24 + k * (bw + 12)
            self.button(f"term{k}", bx, by, bx + bw, by + 46, lab, cb, col, self.f_small)

        tx1, ty1, tx2, ty2 = x1 + 24, by + 64, x2 - 24, y2 - 22
        self.R(tx1, ty1, tx2, ty2, fill="#020108", outline=mix(BG, GREEN, 0.5))
        self.R(tx1, ty1, tx2, ty1 + 24, fill=mix(BG, GREEN, 0.15), outline="")
        for k, c in enumerate((MAG, YEL, GREEN)):
            self.O(tx1 + 12 + k * 16, ty1 + 7, tx1 + 22 + k * 16, ty1 + 17, fill=c, outline="")
        self.T((tx1 + tx2) / 2, ty1 + 12, "neon-mainframe :: bash :: 80x24", self.f_tiny, mix(BG, GREEN, 0.8), "center")

        lh = 18
        max_lines = int((ty2 - ty1 - 40) / lh)
        budget = int((self.t - self.term_t0) * 1400)
        out = []
        for ln in self.term_lines:
            if budget <= 0:
                break
            out.append(ln[:budget])
            budget -= max(1, len(ln))
        done = budget > 0
        visible = out[-max_lines:]
        y = ty1 + 34
        for ln in visible:
            if ln.startswith("root@"):
                c = YEL
            elif "===" in ln:
                c = MAG
            elif ln.startswith("-"):
                c = mix(BG, GREEN, 0.5)
            elif ln.startswith("Total"):
                c = CYAN
            else:
                c = GREEN
            self.T(tx1 + 14, y, ln, self.f_mono, c)
            y += lh
        if done and len(visible) < max_lines:
            cur = "_" if int(self.t * 3) % 2 else " "
            self.T(tx1 + 14, y, "root@neon-mainframe:~/katalog$ " + cur, self.f_mono, YEL)
        sy = ty1 + 24 + ((self.t * 0.25) % 1) * (ty2 - ty1 - 24)
        self.R(tx1 + 1, sy, tx2 - 1, sy + 3, fill=mix(BG, GREEN, 0.18), outline="")
        self.T(tx2 - 10, ty2 - 8, "Output asli dari tampil_elektronik.tampilkan_elektronik()   SPAWN = jalan di "
                                  "jendela console", self.f_tiny, mix(BG, TXT, 0.45), "se")


def main(start_page=0):
    app = NeonKatalog()
    if start_page:
        app.after(int(app.boot_until * 1000) + 100, lambda: app.go(start_page))
    app.mainloop()


if __name__ == "__main__":
    main()
