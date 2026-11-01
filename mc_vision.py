"""
Capri's Minecraft AUTOPILOT, vision edition: NO MODS. She looks at the screen and plays with your keyboard and mouse.

How she sees
  * The F3 debug screen, read with Windows' built-in OCR (falls back to RapidOCR if installed):
      XYZ (where she is), Facing (yaw/pitch: where she's looking), Targeted Block / Targeted Entity (exactly what's under the crosshair).
    That makes her actions closed-loop: she only keeps mining while the crosshair is on a log/ore, stops when it breaks, notices lava, etc.
  * Colour scanning of the frame (numpy) to find trees, ores, water and lava before she walks to them.
  * Optional: a local vision model in Ollama (moondream / llava / llama3.2-vision) for "what do you see?".

How she plays
  * SendInput with hardware scan codes (what Minecraft reads) + relative mouse moves (works with raw input).
  * SAFETY: every key/mouse event first checks that the Minecraft window is the active window. If you click anywhere else she
    freezes and lets go of every key, so she can never type into another app. F8 / "stop" ends the task.

Skills: chop_wood(n), mine(target_y), find_ore(ore), explore(seconds), fight(seconds), eat(), shelter(), pillar(n), describe(), play() (a loop).
Hotbar: she uses whatever is in your hotbar. Defaults (change by voice: "my pickaxe is in slot 1"): tool 1, blocks 2, food 9.
Test what she sees:  python mc_vision.py --test   (Minecraft open, in a world)
"""
import json, math, os, random, re, threading, time
from pathlib import Path

ctx = {}
def init(**kw): ctx.update(kw)
def _log(m):
    try: ctx["log"](m)
    except Exception: print(m)
def _event(m):
    try: ctx["event"](m)
    except Exception: pass

MC_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / ".minecraft"
CFG_FILE = Path(__file__).resolve().parent / "mc_vision.json"
CFG = {"slot_tool": 1, "slot_blocks": 2, "slot_food": 9, "toggle_f3": True, "vision_model": "auto"}
try: CFG.update(json.loads(CFG_FILE.read_text(encoding="utf-8")))
except Exception: pass
def save_cfg():
    try: CFG_FILE.write_text(json.dumps(CFG, indent=1), encoding="utf-8")
    except Exception as e: _log(f"mc_vision cfg save: {e}")

class Stopped(Exception): pass
class Unfocused(Exception): pass

# ====================================================================================== WINDOWS: window + input
IS_WIN = os.name == "nt"
if IS_WIN:
    import ctypes
    from ctypes import wintypes
    U32 = ctypes.windll.user32
    try: ctypes.windll.shcore.SetProcessDpiAwareness(2)      # real pixels for capture
    except Exception: pass

    class _KI(ctypes.Structure): _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]
    class _MI(ctypes.Structure): _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]
    class _U(ctypes.Union): _fields_ = [("ki", _KI), ("mi", _MI)]
    class _INPUT(ctypes.Structure): _fields_ = [("type", wintypes.DWORD), ("u", _U)]

SCAN = {"w": 0x11, "a": 0x1E, "s": 0x1F, "d": 0x20, "space": 0x39, "shift": 0x2A, "ctrl": 0x1D, "e": 0x12, "q": 0x10, "esc": 0x01, "f3": 0x3D,
        **{str(i): 0x01 + i for i in range(1, 10)}}

class Input:
    """Keyboard + mouse that ONLY acts while the Minecraft window is in front."""
    def __init__(self, hwnd, stop_event):
        self.hwnd, self.stop = hwnd, stop_event
        self.held = set(); self.buttons = set()

    def guard(self):
        if self.stop.is_set(): self.release_all(); raise Stopped()
        if IS_WIN and U32.GetForegroundWindow() != self.hwnd: self.release_all(); raise Unfocused()

    def _send(self, inp):
        if IS_WIN: U32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))

    def _key(self, name, up):
        if not IS_WIN: return
        i = _INPUT(type=1); i.u.ki = _KI(0, SCAN[name], 0x0008 | (0x0002 if up else 0), 0, 0); self._send(i)

    def down(self, name):
        self.guard()
        if name not in self.held: self._key(name, False); self.held.add(name)
    def up(self, name):
        if name in self.held: self._key(name, True); self.held.discard(name)
    def tap(self, name, hold=0.06):
        self.down(name); time.sleep(hold); self.up(name)

    def _mouse(self, flags, dx=0, dy=0):
        if not IS_WIN: return
        i = _INPUT(type=0); i.u.mi = _MI(dx, dy, 0, flags, 0, 0); self._send(i)
    def move(self, dx, dy, steps=None):
        """Relative mouse move (camera turn), split into small steps so it looks smooth on stream."""
        dx, dy = int(round(dx)), int(round(dy))
        steps = steps or max(1, int(max(abs(dx), abs(dy)) / 35))
        sx, sy = dx / steps, dy / steps; ax = ay = 0.0
        for k in range(steps):
            self.guard()
            ax += sx; ay += sy; mx, my = int(round(ax)), int(round(ay)); ax -= mx; ay -= my
            if mx or my: self._mouse(0x0001, mx, my)
            time.sleep(0.008)
    BTN = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010)}
    def press(self, b):
        self.guard()
        if b not in self.buttons: self._mouse(self.BTN[b][0]); self.buttons.add(b)
    def release(self, b):
        if b in self.buttons: self._mouse(self.BTN[b][1]); self.buttons.discard(b)
    def click(self, b="left", hold=0.05):
        self.press(b); time.sleep(hold); self.release(b)

    def release_all(self):
        for k in list(self.held): self.up(k)
        for b in list(self.buttons): self.release(b)

def find_window():
    """Minecraft Java's game window (javaw.exe / java.exe), not the launcher. -> (hwnd, (left, top, width, height)) or None."""
    if not IS_WIN: return None
    found = []
    PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        if not U32.IsWindowVisible(h): return True
        buf = ctypes.create_unicode_buffer(256); U32.GetWindowTextW(h, buf, 256); t = buf.value
        if re.match(r"^Minecraft\*?(\s+\d|\s*$|\s.*(Singleplayer|Multiplayer|LAN|Realms))", t) and os.path.basename(exe_of(h)).lower() in ("javaw.exe", "java.exe"):
            found.append(int(h))
        return True
    U32.EnumWindows(PROC(cb), 0)
    if not found: return None
    h = found[0]
    r = wintypes.RECT(); U32.GetClientRect(h, ctypes.byref(r))
    p = wintypes.POINT(0, 0); U32.ClientToScreen(h, ctypes.byref(p))
    return h, (p.x, p.y, r.right - r.left, r.bottom - r.top)

def exe_of(hwnd):
    if not IS_WIN: return ""
    pid = wintypes.DWORD(); U32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    k32 = ctypes.windll.kernel32; k32.OpenProcess.restype = wintypes.HANDLE
    h = k32.OpenProcess(0x1000, False, pid.value)
    if not h: return ""
    try:
        buf = ctypes.create_unicode_buffer(520); n = wintypes.DWORD(520)
        return buf.value if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) else ""
    finally: k32.CloseHandle(h)

def focus(hwnd):
    if not IS_WIN: return
    if U32.IsIconic(hwnd): U32.ShowWindow(hwnd, 9)
    U32.keybd_event(0x12, 0, 0, 0); U32.SetForegroundWindow(hwnd); U32.keybd_event(0x12, 0, 2, 0)
    time.sleep(0.4)

# ====================================================================================== game settings (options.txt)
def game_options():
    o = {}
    try:
        for line in (MC_DIR / "options.txt").read_text(encoding="utf-8", errors="replace").splitlines():
            if ":" in line: k, v = line.split(":", 1); o[k] = v.strip()
    except Exception: pass
    return o

def deg_per_pixel(opts=None):
    """Minecraft camera: degrees turned per mouse pixel, from your mouse sensitivity (default 0.5 -> 0.15 deg/px)."""
    opts = opts or game_options()
    try: s = float(opts.get("mouseSensitivity", "0.5"))
    except ValueError: s = 0.5
    f = s * 0.6 + 0.2
    return max(0.01, f * f * f * 8.0 * 0.15)

def vertical_fov(opts=None):
    opts = opts or game_options()
    try:
        v = float(opts.get("fov", "0.0")); return 70 + v * 40 if -1 <= v <= 1 else v
    except ValueError: return 70.0

# ====================================================================================== capture
class Screen:
    def __init__(self, rect):
        import mss
        self.sct = mss.mss(); self.rect = rect
    def grab(self):
        """Full game frame as an RGB numpy array (h, w, 3)."""
        import numpy as np
        l, t, w, h = self.rect
        s = self.sct.grab({"left": l, "top": t, "width": w, "height": h})
        a = np.frombuffer(s.bgra, dtype=np.uint8).reshape(s.height, s.width, 4)
        return a[:, :, 2::-1].copy()

# ====================================================================================== OCR (F3 debug screen)
_ocr = {"kind": None}
def _ocr_init():
    if _ocr["kind"] is not None: return _ocr["kind"]
    _ocr["kind"] = ""
    try:
        from winrt.windows.media.ocr import OcrEngine
        eng = OcrEngine.try_create_from_user_profile_languages()
        if eng is not None: _ocr.update(kind="windows", engine=eng); return "windows"
    except Exception as e: _log(f"Windows OCR unavailable ({e}): pip install winrt-Windows.Media.Ocr winrt-Windows.Graphics.Imaging winrt-Windows.Security.Cryptography winrt-Windows.Foundation winrt-Windows.Foundation.Collections")
    try:
        from rapidocr_onnxruntime import RapidOCR
        _ocr.update(kind="rapid", engine=RapidOCR()); return "rapid"
    except Exception: pass
    return ""

def ocr_lines(rgb):
    """RGB numpy image -> list of text lines (top to bottom)."""
    kind = _ocr_init()
    if kind == "windows":
        import asyncio, numpy as np
        from winrt.windows.graphics.imaging import SoftwareBitmap, BitmapPixelFormat, BitmapAlphaMode
        from winrt.windows.security.cryptography import CryptographicBuffer
        h, w = rgb.shape[:2]
        bgra = np.dstack([rgb[:, :, 2], rgb[:, :, 1], rgb[:, :, 0], np.full((h, w), 255, np.uint8)])
        buf = CryptographicBuffer.create_from_byte_array(bgra.tobytes())
        bmp = SoftwareBitmap.create_copy_from_buffer(buf, BitmapPixelFormat.BGRA8, w, h, BitmapAlphaMode.PREMULTIPLIED)
        async def run(): return await _ocr["engine"].recognize_async(bmp)
        res = asyncio.run(run())
        return [ln.text for ln in res.lines]
    if kind == "rapid":
        out, _ = _ocr["engine"](rgb[:, :, ::-1])
        if not out: return []
        out.sort(key=lambda r: (round(r[0][0][1] / 12), r[0][0][0]))
        return [r[1] for r in out]
    return []

def ocr_words(rgb):
    """RGB numpy image -> [(text, x, y, w, h)] for every word, in image pixels. Used to find buttons ("PLAY") in launchers."""
    kind = _ocr_init(); out = []
    if kind == "windows":
        import asyncio, numpy as np
        from winrt.windows.graphics.imaging import SoftwareBitmap, BitmapPixelFormat, BitmapAlphaMode
        from winrt.windows.security.cryptography import CryptographicBuffer
        h, w = rgb.shape[:2]
        bgra = np.dstack([rgb[:, :, 2], rgb[:, :, 1], rgb[:, :, 0], np.full((h, w), 255, np.uint8)])
        bmp = SoftwareBitmap.create_copy_from_buffer(CryptographicBuffer.create_from_byte_array(bgra.tobytes()), BitmapPixelFormat.BGRA8, w, h, BitmapAlphaMode.PREMULTIPLIED)
        async def run(): return await _ocr["engine"].recognize_async(bmp)
        for ln in asyncio.run(run()).lines:
            for wd in ln.words:
                r = wd.bounding_rect; out.append((wd.text, r.x, r.y, r.width, r.height))
    elif kind == "rapid":
        res, _ = _ocr["engine"](rgb[:, :, ::-1])
        for box, text, _c in (res or []):
            xs = [p[0] for p in box]; ys = [p[1] for p in box]
            out.append((text, min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)))
    return out

def window_rect(hwnd):
    """Window rect in real screen pixels -> (left, top, width, height)."""
    if not IS_WIN: return None
    r = wintypes.RECT()
    if ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(r), ctypes.sizeof(r)) != 0: U32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.top

def click_screen(x, y):
    """Left click at a real screen pixel."""
    if not IS_WIN: return
    U32.SetCursorPos(int(x), int(y)); time.sleep(0.08)
    U32.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.06); U32.mouse_event(0x0004, 0, 0, 0, 0)

NUM = r"(-?\d+(?:[.,]\d+)?)"
def parse_debug(left_lines, right_lines):
    """F3 text -> {'pos': (x,y,z), 'yaw': f, 'pitch': f, 'block': 'oak_log', 'fluid': 'water', 'entity': 'zombie'} (missing keys = not read)."""
    L = "\n".join(left_lines); R = "\n".join(right_lines)
    fix = lambda s: s.replace(",", ".")
    d = {}
    m = re.search(r"XY[Z2]\s*[:;.]?\s*" + NUM + r"\s*[/|l]\s*" + NUM + r"\s*[/|l]\s*" + NUM, L)
    if m: d["pos"] = tuple(float(fix(x)) for x in m.groups())
    m = re.search(r"Facing.*?\(\s*" + NUM + r"\s*[/|l]\s*" + NUM + r"\s*\)", L)
    if m: d["yaw"], d["pitch"] = float(fix(m.group(1))), float(fix(m.group(2)))
    def target(label):
        mm = re.search(label + r"[^\n]*\n\s*(?:minecraft)?\W*([a-z][a-z_]+)", R, re.I)
        return mm.group(1).lower() if mm else None
    b = target(r"Targeted\s+Block");  f = target(r"Targeted\s+Fluid");  e = target(r"Targeted\s+Entity")
    if b: d["block"] = b
    if f: d["fluid"] = f
    if e: d["entity"] = e
    if "pos" not in d:                                         # some versions: "Block: x y z"
        m = re.search(r"\bBlock\W+" + r"(-?\d+)\s+(-?\d+)\s+(-?\d+)", L)
        if m: d["pos"] = tuple(float(x) for x in m.groups())
    return d

# ====================================================================================== colour perception
def hsv(rgb):
    import numpy as np
    x = rgb.astype(np.float32) / 255.0
    r, g, b = x[..., 0], x[..., 1], x[..., 2]
    mx, mn = x.max(-1), x.min(-1); d = mx - mn + 1e-6
    h = np.where(mx == r, (g - b) / d % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) * 60
    s = np.where(mx > 0, (mx - mn) / (mx + 1e-6), 0)
    return h, s, mx

# hue (deg), sat, val ranges. Tweak in mc_vision.json under "colors" if your texture pack differs.
COLORS = {"leaves": [(65, 160), (0.35, 1), (0.10, 0.62)], "bark": [(18, 42), (0.28, 0.70), (0.16, 0.52)], "bark_dark": [(10, 40), (0.30, 0.85), (0.07, 0.26)],
          "diamond": [(165, 195), (0.40, 1), (0.50, 1)], "gold": [(44, 58), (0.60, 1), (0.70, 1)], "iron": [(14, 32), (0.20, 0.50), (0.60, 0.90)],
          "redstone": [(350, 360), (0.70, 1), (0.45, 1)], "lapis": [(212, 238), (0.50, 1), (0.30, 0.85)], "emerald": [(120, 150), (0.60, 1), (0.50, 1)],
          "water": [(200, 235), (0.40, 0.90), (0.30, 0.85)], "lava": [(8, 38), (0.75, 1), (0.80, 1)]}
COLORS.update(CFG.get("colors", {}))

def mask(H, S, V, name):
    (h0, h1), (s0, s1), (v0, v1) = COLORS[name]
    m = (H >= h0) & (H <= h1) & (S >= s0) & (S <= s1) & (V >= v0) & (V <= v1)
    if name == "redstone": m |= (H <= 8) & (S >= s0) & (V >= v0)
    return m

def small(rgb, width=240):
    import numpy as np
    h, w = rgb.shape[:2]; k = max(1, w // width)
    return rgb[::k, ::k]

def find_tree(rgb):
    """-> (x_frac 0..1, strength) of the best tree trunk in view, or None. A trunk = a column of bark with leaves above or around it."""
    import numpy as np
    img = small(rgb); H, S, V = hsv(img); h, w = img.shape[:2]
    bark = mask(H, S, V, "bark") | mask(H, S, V, "bark_dark"); leaves = mask(H, S, V, "leaves")
    band = bark[int(h * 0.15):int(h * 0.85)]
    col = band.mean(0)
    lv = leaves[:int(h * 0.6)].mean(0)
    k = max(3, w // 40); ker = np.ones(k) / k
    col = np.convolve(col, ker, "same"); lv = np.convolve(lv, np.ones(k * 3) / (k * 3), "same")
    score = col * (0.3 + lv * 3)
    score[: int(w * 0.03)] = 0; score[-int(w * 0.03):] = 0               # edges: hotbar/borders noise
    i = int(score.argmax())
    if score[i] < 0.05 or col[i] < 0.08: return None
    return i / w, float(score[i])

def find_color(rgb, name, min_frac=0.0006, region=None):
    """-> (x_frac, y_frac, frac) centre of the biggest blob of a colour, or None."""
    import numpy as np
    img = small(rgb); H, S, V = hsv(img); m = mask(H, S, V, name); h, w = m.shape
    m[int(h * 0.86):] = False                                             # hotbar / hand
    if region: x0, y0, x1, y1 = region; mm = np.zeros_like(m); mm[int(y0*h):int(y1*h), int(x0*w):int(x1*w)] = m[int(y0*h):int(y1*h), int(x0*w):int(x1*w)]; m = mm
    frac = m.mean()
    if frac < min_frac: return None
    g = 8; gh, gw = h // g, w // g                                        # coarse grid: densest cell
    cells = m[:gh * g, :gw * g].reshape(g, gh, g, gw).mean((1, 3))
    cy, cx = np.unravel_index(cells.argmax(), cells.shape)
    ys, xs = np.nonzero(m[cy * gh:(cy + 1) * gh, cx * gw:(cx + 1) * gw])
    if len(xs) == 0: return None
    return (cx * gw + xs.mean()) / w, (cy * gh + ys.mean()) / h, float(frac)

def danger(rgb):
    """Lava near the crosshair / straight ahead at the bottom of the view."""
    img = small(rgb); H, S, V = hsv(img); h, w = img.shape[:2]
    lv = mask(H, S, V, "lava")[int(h * 0.35):int(h * 0.85), int(w * 0.3):int(w * 0.7)]
    return float(lv.mean()) > 0.08

def water_ahead(rgb):
    img = small(rgb); H, S, V = hsv(img); h, w = img.shape[:2]
    return float(mask(H, S, V, "water")[int(h * 0.55):int(h * 0.85), int(w * 0.3):int(w * 0.7)].mean()) > 0.45

def frame_change(a, b):
    import numpy as np
    if a is None or b is None or a.shape != b.shape: return 1.0
    x, y = small(a, 120).astype(np.int16), small(b, 120).astype(np.int16)
    return float(np.abs(x - y).mean()) / 255.0

# ====================================================================================== the player
LOGS = re.compile(r"_(log|stem|wood)$")
ORE = re.compile(r"(ore|ancient_debris)$")
HOSTILE = re.compile(r"zombie|skeleton|spider|creeper|witch|slime|drowned|husk|stray|pillager|vindicator|phantom|enderman|silverfish|blaze|ghast|piglin_brute|hoglin|zoglin|wither_skeleton|magma_cube|guardian|evoker|ravager|warden|breeze|bogged")
NO_DIG = re.compile(r"bedrock|lava|water|air|chest|spawner|end_portal|obsidian")
ORE_Y = {"diamond": -54, "redstone": -54, "gold": -16, "lapis": 0, "iron": 16, "coal": 45, "emerald": 100, "copper": 48, "any": 12}

class Player:
    def __init__(self, stop_event, progress=None):
        w = find_window()
        if not w: raise RuntimeError("Minecraft Java isn't open (or you're on the launcher). Load into a world first.")
        self.hwnd, self.rect = w
        self.stop = stop_event; self.inp = Input(self.hwnd, stop_event); self.scr = None
        self.opts = game_options(); self.dpp = deg_per_pixel(self.opts); self.vfov = vertical_fov(self.opts)
        self.yaw = None; self.pitch = None; self.dbg = {}; self.dbg_at = 0.0; self.ocr_ok = None; self.f3_by_me = False
        self.progress = progress or (lambda m: None); self.count = 0; self.last_frame = None

    # ---------- basics
    def say(self, m): self.progress(m); _log("mc: " + m)
    def check(self):
        if self.stop.is_set(): self.inp.release_all(); raise Stopped()
    def sleep(self, s):
        t = time.time() + s
        while time.time() < t:
            self.inp.guard(); time.sleep(min(0.05, max(0, t - time.time())))
    def frame(self):
        if self.scr is None: self.scr = Screen(self.rect)
        f = self.scr.grab(); self.last_frame = f; return f
    def hfov(self):
        l, t, w, h = self.rect
        return math.degrees(2 * math.atan(math.tan(math.radians(self.vfov / 2)) * w / max(1, h)))

    def read(self, force=False):
        """Reads the F3 screen (cached ~0.3 s). Updates yaw/pitch."""
        if not force and time.time() - self.dbg_at < 0.3: return self.dbg
        f = self.frame(); h, w = f.shape[:2]
        if self.ocr_ok is False: return {}
        try:
            left = ocr_lines(f[: int(h * 0.62), : int(w * 0.5)]); right = ocr_lines(f[: int(h * 0.62), int(w * 0.5):])
        except Exception as e:
            _log(f"OCR failed: {e}"); left, right = [], []
        d = parse_debug(left, right); self.dbg, self.dbg_at = d, time.time()
        if "yaw" in d: self.yaw, self.pitch = d["yaw"], d["pitch"]
        return d

    def ensure_f3(self):
        """Turns the F3 screen on (if it isn't) so she can read where she is and what she's looking at."""
        d = self.read(force=True)
        if "pos" in d or "yaw" in d: self.ocr_ok = True; return True
        if _ocr_init() == "": self.ocr_ok = False; self.say("no OCR installed: playing by colour only (less accurate)"); return False
        self.inp.tap("f3"); self.f3_by_me = True; self.sleep(0.6)
        d = self.read(force=True)
        if "pos" in d or "yaw" in d: self.ocr_ok = True; return True
        self.inp.tap("f3"); self.f3_by_me = False
        self.ocr_ok = False; self.say("couldn't read the F3 screen: playing by colour only"); return False

    def finish(self):
        self.inp.release_all()
        if self.f3_by_me and CFG.get("toggle_f3", True):
            try:
                if IS_WIN and U32.GetForegroundWindow() == self.hwnd: self.inp._key("f3", False); time.sleep(0.05); self.inp._key("f3", True)
            except Exception: pass

    def block(self): return (self.read().get("block") or "") if self.ocr_ok else ""
    def entity(self): return (self.read().get("entity") or "") if self.ocr_ok else ""
    def pos(self): return self.read().get("pos") if self.ocr_ok else None

    # ---------- camera
    def turn(self, dyaw, dpitch=0.0):
        if self.pitch is not None: dpitch = max(-89.5 - self.pitch, min(89.5 - self.pitch, dpitch))
        self.inp.move(dyaw / self.dpp, dpitch / self.dpp)
        if self.yaw is not None: self.yaw = (self.yaw + dyaw + 180) % 360 - 180
        if self.pitch is not None: self.pitch += dpitch
        self.dbg_at = 0

    def level_camera(self):
        """Knows its pitch even without OCR: look all the way up (it clamps at -90), then down 90."""
        self.inp.move(0, -95 / self.dpp, steps=12); self.inp.move(0, 90 / self.dpp, steps=12)
        self.pitch = 0.0
        if self.yaw is None: self.yaw = 0.0
        self.dbg_at = 0

    def look_to(self, yaw=None, pitch=None):
        for _ in range(2):
            if self.ocr_ok: self.read(force=True)
            cy = self.yaw if self.yaw is not None else 0.0; cp = self.pitch if self.pitch is not None else 0.0
            dy = 0.0 if yaw is None else ((yaw - cy + 180) % 360 - 180); dp = 0.0 if pitch is None else pitch - cp
            if abs(dy) < 2 and abs(dp) < 2: return
            self.turn(dy, dp)
            if not self.ocr_ok: return

    def aim_at(self, xf, yf=0.5):
        """Turn so the point (x_frac, y_frac) of the screen goes under the crosshair."""
        l, t, w, h = self.rect
        self.turn((xf - 0.5) * self.hfov(), (yf - 0.5) * self.vfov)

    # ---------- actions
    def hotbar(self, n): self.inp.tap(str(max(1, min(9, int(n))))); self.sleep(0.15)

    def walk(self, secs, sprint=False, jump_if_stuck=True):
        """Walks forward, jumping over 1-block steps; stops at lava or deep water. Returns how far she got (blocks, if OCR)."""
        p0 = self.pos(); f0 = self.frame(); stuck = 0
        if sprint: self.inp.down("ctrl")
        self.inp.down("w"); t_end = time.time() + secs
        try:
            while time.time() < t_end:
                self.sleep(0.35); f = self.frame()
                if danger(f): self.say("lava ahead, backing off"); self.inp.up("w"); self.inp.tap("s", 0.6); return -1
                if frame_change(f0, f) < 0.012:
                    stuck += 1
                    if jump_if_stuck: self.inp.tap("space", 0.15)
                    if stuck >= 4: break
                else: stuck = 0
                f0 = f
        finally:
            self.inp.up("w"); self.inp.up("ctrl")
        p1 = self.pos()
        return math.dist(p0[::2], p1[::2]) if (p0 and p1) else None

    def mine_target(self, want=None, timeout=8.0):
        """Holds attack on the block under the crosshair until it breaks (block name changes). want: regex the block must match."""
        b0 = self.block()
        if self.ocr_ok:
            if not b0 or b0 in ("air", "cave_air", "void_air"): return False
            if NO_DIG.search(b0): self.say(f"not digging {b0}"); return False
            if want and not re.search(want, b0): return False
        f0 = self.frame(); self.inp.press("left"); t0 = time.time(); broke = False
        try:
            while time.time() - t0 < timeout:
                self.sleep(0.25)
                if self.ocr_ok:
                    b = self.block()
                    if b != b0: broke = True; break
                elif time.time() - t0 > 1.0 and frame_change(f0, self.frame()) > 0.06: broke = True; break
        finally:
            self.inp.release("left")
        if broke: self.count += 1
        return broke

    # ---------- skills
    def chop_wood(self, n=8, deadline=240):
        self.say(f"looking for trees (want {n} logs)")
        t_end = time.time() + deadline; got = 0; fails = 0
        while got < n and time.time() < t_end:
            self.check()
            tree = self.scan_for(lambda f: find_tree(f), "tree")
            if not tree:
                self.say("no trees in sight, walking on"); self.turn(random.choice([-1, 1]) * random.uniform(60, 120)); self.walk(4, sprint=True); fails += 1
                if fails > 6: break
                continue
            xf, _ = tree; self.aim_at(xf, 0.5); self.look_to(pitch=5)
            reached = False
            for _ in range(14):                                   # walk up to the trunk
                if self.ocr_ok and LOGS.search(self.block() or ""): reached = True; break
                if not self.ocr_ok:
                    t = find_tree(self.frame())
                    if t and t[1] > 0.6 and abs(t[0] - 0.5) < 0.08: reached = True; break
                    if t: self.aim_at(t[0], 0.5)
                if self.walk(0.6) == -1: break
            if not reached: fails += 1; continue
            for pitch in (5, -15, -35, -55, 30):                   # the trunk, then up it, then the log at your feet
                self.look_to(pitch=pitch)
                while self.mine_target(want=r"_(log|stem|wood)$" if self.ocr_ok else None):
                    got += 1; self.say(f"logs: {got}/{n}")
                    if got >= n or not self.ocr_ok: break
                if got >= n: break
            self.look_to(pitch=10); self.walk(1.2)                # step in to pick the drops up
        return f"chopped {got} log{'s' if got != 1 else ''}"

    def scan_for(self, finder, label, steps=8):
        """Turns around in steps looking for something. Returns the finder's result with the camera facing it, or None."""
        best = None
        for i in range(steps):
            r = finder(self.frame())
            if r and (best is None or r[-1] > best[1][-1]): best = (i, r)
            if r and r[-1] > 0.35: return r
            self.turn(360 / steps)
        if not best: return None                                  # a full circle later we face the start again: turn to the best step
        i, r = best; self.turn(i * 360 / steps)
        return finder(self.frame()) or r

    def staircase_step(self):
        """Digs one step of a staircase going down-forward (break eye-level, feet-level and the block below), then steps in."""
        for pitch in (25, 55, 75):
            self.look_to(pitch=pitch)
            if danger(self.frame()): raise RuntimeError("lava")
            self.mine_target(timeout=6)
        self.look_to(pitch=25); self.walk(0.5, jump_if_stuck=False)

    def tunnel_step(self):
        for pitch in (0, 40):
            self.look_to(pitch=pitch)
            if danger(self.frame()): raise RuntimeError("lava")
            self.mine_target(timeout=6)
        self.look_to(pitch=10); self.walk(0.45, jump_if_stuck=False)

    def mine_visible_ore(self, kinds):
        f = self.frame()
        for k in kinds:
            hit = find_color(f, k, min_frac=0.0005, region=(0.15, 0.1, 0.85, 0.85))
            if hit:
                self.aim_at(hit[0], hit[1]); b = self.block()
                if not self.ocr_ok or ORE.search(b):
                    if self.mine_target(timeout=8): self.say(f"mined {b or k}!"); return True
        if self.ocr_ok and ORE.search(self.block() or ""): return self.mine_target(timeout=8)
        return False

    def mine(self, target_y=12, ore="any", deadline=600, max_steps=400):
        self.hotbar(CFG["slot_tool"])
        kinds = [ore] if ore in COLORS else ["diamond", "gold", "iron", "redstone", "lapis", "emerald"]
        self.say(f"mining down to y={target_y}" + (f" for {ore}" if ore != "any" else ""))
        t_end = time.time() + deadline; steps = 0
        try:
            while time.time() < t_end and steps < max_steps:
                self.check(); p = self.pos()
                if p and p[1] <= target_y + 0.5: break
                if not self.ocr_ok and steps >= 60: break
                self.staircase_step(); steps += 1
                if steps % 3 == 0: self.mine_visible_ore(kinds)
            self.say("strip mining")
            while time.time() < t_end and steps < max_steps:
                self.check(); self.tunnel_step(); steps += 1
                self.mine_visible_ore(kinds)
                if steps % 12 == 0:                                # peek left and right for ores
                    for side in (90, -180):
                        self.turn(side); self.mine_visible_ore(kinds)
                    self.turn(90)
        except RuntimeError as e:
            if "lava" in str(e): self.inp.tap("s", 0.8); self.turn(180); return "found lava, so I backed off. Safety first, choom"
            raise
        return f"mined {self.count} blocks"

    def explore(self, seconds=60):
        self.say("exploring"); t_end = time.time() + seconds
        while time.time() < t_end:
            self.check()
            if water_ahead(self.frame()): self.turn(random.uniform(90, 150))
            moved = self.walk(random.uniform(2.5, 5), sprint=True)
            if moved == -1 or (moved is not None and moved < 0.6): self.turn(random.choice([-1, 1]) * random.uniform(70, 140))
            elif random.random() < 0.3: self.turn(random.uniform(-45, 45))
        return "done exploring"

    def fight(self, seconds=60):
        self.hotbar(CFG["slot_tool"]); self.say("hunting hostile mobs"); t_end = time.time() + seconds; kills = 0
        while time.time() < t_end:
            self.check()
            e = self.entity()
            if e and HOSTILE.search(e):
                if "creeper" in e: self.say("creeper! backing off"); self.inp.down("s"); self.sleep(1.2); self.inp.up("s"); continue
                self.inp.down("w")
                for _ in range(6):
                    self.inp.click("left"); self.sleep(0.6)
                    if not HOSTILE.search(self.entity() or ""): kills += 1; break
                self.inp.up("w")
            else:
                self.turn(30)
                if not self.ocr_ok: self.inp.click("left"); self.sleep(0.4)
        return f"fight over ({kills} down)"

    def eat(self):
        self.hotbar(CFG["slot_food"]); self.say("eating")
        self.inp.press("right"); self.sleep(2.0); self.inp.release("right")
        self.hotbar(CFG["slot_tool"]); return "ate (food from hotbar slot %d)" % CFG["slot_food"]

    def place_at(self, pitch):
        self.look_to(pitch=pitch); self.inp.click("right", 0.05); self.sleep(0.25)

    def shelter(self):
        """Four walls, two blocks high, around where she stands (blocks from the 'blocks' hotbar slot)."""
        self.hotbar(CFG["slot_blocks"]); self.say("building walls around us")
        base = self.yaw if self.yaw is not None else 0.0
        for k in range(4):
            self.look_to(yaw=base + 90 * k)
            self.place_at(64)                                     # on the ground in front: feet level
            self.place_at(36)                                     # on top of that: head level
        self.look_to(yaw=base, pitch=0)
        return "walls up. Not exactly Arasaka tower, but it'll do"

    def pillar(self, n=5):
        self.hotbar(CFG["slot_blocks"]); self.look_to(pitch=89)
        for _ in range(int(n)):
            self.check(); self.inp.down("space"); self.sleep(0.28); self.inp.click("right", 0.05); self.inp.up("space"); self.sleep(0.35)
        self.look_to(pitch=0); return f"built a {n}-block pillar"

    def describe(self):
        return describe_frame(self.frame())

    def play(self, minutes=30):
        """'Play for me': a survival loop. Wood -> explore -> mine for ores -> fight when attacked -> eat now and then."""
        t_end = time.time() + minutes * 60; last_eat = time.time(); rounds = 0
        while time.time() < t_end:
            self.check(); rounds += 1
            self.say(f"round {rounds}: wood"); self.chop_wood(6, deadline=150)
            if HOSTILE.search(self.entity() or ""): self.fight(20)
            self.say(f"round {rounds}: exploring"); self.explore(25)
            if time.time() - last_eat > 300: self.eat(); last_eat = time.time()
            self.say(f"round {rounds}: mining"); self.mine(target_y=ORE_Y["iron"], deadline=240, max_steps=120)
        return "that's my shift done"

# ====================================================================================== vision model (optional): "what do you see?"
def describe_frame(rgb, question="Describe this Minecraft screenshot in one short sentence for a stream. Mention trees, ores, mobs, water or lava if you see them."):
    import base64, io, requests
    from PIL import Image
    try:
        tags = [m["name"] for m in requests.get("http://127.0.0.1:11434/api/tags", timeout=3).json().get("models", [])]
    except Exception: return "my vision brain isn't running"
    want = CFG.get("vision_model", "auto")
    pick = want if want != "auto" else next((t for c in ("moondream", "llava-phi3", "llava", "llama3.2-vision", "minicpm-v", "qwen2.5vl", "gemma3") for t in tags if t.startswith(c)), None)
    if not pick: return "no vision model installed (ollama pull moondream)"
    im = Image.fromarray(rgb); im.thumbnail((640, 360)); b = io.BytesIO(); im.save(b, "JPEG", quality=80)
    r = requests.post("http://127.0.0.1:11434/api/chat", json={"model": pick, "stream": False, "keep_alive": "10m", "options": {"num_predict": 60},
                       "messages": [{"role": "user", "content": question, "images": [base64.b64encode(b.getvalue()).decode()]}]}, timeout=120)
    return r.json()["message"]["content"].strip()

# ====================================================================================== runner (one task at a time, in a thread)
class Runner:
    def __init__(self): self.stop = threading.Event(); self.thread = None; self.task = ""; self.result = ""; self.player = None
    def busy(self): return bool(self.thread and self.thread.is_alive())
    def start(self, skill, args=(), on_done=None, progress=None):
        self.cancel(wait=2.0)
        self.stop = threading.Event(); self.task = skill; self.result = ""
        def run():
            p = None
            try:
                if not find_window(): raise RuntimeError("Minecraft isn't open")
                h, _ = find_window(); focus(h)
                p = Player(self.stop, progress); self.player = p
                p.ensure_f3()
                if p.pitch is None: p.level_camera()
                fn = getattr(p, skill)
                while True:
                    try: self.result = fn(*args) or "done"; break
                    except Unfocused:
                        if progress: progress("paused: click back into Minecraft and I'll carry on")
                        t0 = time.time()
                        while not self.stop.is_set() and (not IS_WIN or U32.GetForegroundWindow() != p.hwnd):
                            if time.time() - t0 > 120: raise Stopped()
                            time.sleep(0.3)
                        if self.stop.is_set(): raise Stopped()
                        time.sleep(0.5)
            except Stopped: self.result = "stopped"
            except Exception as e:
                self.result = f"couldn't finish: {e}"; _log(f"mc task {skill} failed: {e!r}")
            finally:
                if p: p.finish()
                if on_done:
                    try: on_done(self.result)
                    except Exception: pass
        self.thread = threading.Thread(target=run, daemon=True, name="mc_vision"); self.thread.start()
    def cancel(self, wait=0.0):
        self.stop.set()
        if wait and self.thread and self.thread.is_alive(): self.thread.join(wait)

RUNNER = Runner()

# ====================================================================================== self-test
def selftest():
    print("\n=== Capri Minecraft vision test ===")
    w = find_window()
    if not w: print("Minecraft Java window not found. Open Minecraft and load a world, then run this again."); return
    h, rect = w; print("window:", rect, "| sensitivity deg/px:", round(deg_per_pixel(), 4), "| vertical FOV:", vertical_fov())
    print("OCR engine:", _ocr_init() or "NONE (pip install winrt-Windows.Media.Ocr winrt-Windows.Graphics.Imaging winrt-Windows.Security.Cryptography winrt-Windows.Foundation winrt-Windows.Foundation.Collections)")
    focus(h); time.sleep(0.5)
    scr = Screen(rect); f = scr.grab(); H, W = f.shape[:2]
    t0 = time.time(); L = ocr_lines(f[: int(H * 0.62), : int(W * 0.5)]); R = ocr_lines(f[: int(H * 0.62), int(W * 0.5):])
    print(f"OCR took {time.time() - t0:.2f}s. (Press F3 in Minecraft first so the debug text is showing.)")
    print("read from F3:", parse_debug(L, R) or "nothing: is F3 open?")
    print("tree:", find_tree(f), "| lava ahead:", danger(f), "| water ahead:", water_ahead(f))
    for k in ("diamond", "iron", "gold", "redstone", "lapis"): print(f"  {k}:", find_color(f, k))
    try:
        from PIL import Image
        out = Path(__file__).resolve().parent / "mc_vision_test.png"; Image.fromarray(f).save(out); print("saved what she sees ->", out)
    except Exception: pass

if __name__ == "__main__":
    import sys
    if "--test" in sys.argv: selftest()
    else: print(__doc__)
