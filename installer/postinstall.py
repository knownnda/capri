"""
Capri's setup worker. The installer (CapriSetup.exe) runs this right after copying her files:
    python postinstall.py <app_dir>/install_plan.json
It is safe to run again any time (Start Menu > Capri > Repair): every step skips what's already done.

Steps (each one is skipped if you unticked it in the installer):
  0. web installer only: download Capri herself from app_zip_url and unpack her
  1. a private Python environment (venv) with all her packages
  2. her brain: start Ollama and pull the model that speaks your language best
  3. her ears: the speech-recognition model for your language (English-only model for English, multilingual otherwise)
  4. her voice: a Piper voice in your language (and switches "speak replies" on)
  5. the language you picked in the installer -> install_language.json (Capri reads it on her next start)
Standard library only: this runs before any packages are installed.
"""
import json, os, shutil, subprocess, sys, tempfile, time, traceback, urllib.request, zipfile
from pathlib import Path

PLAN_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "install_plan.json"
try:
    PLAN = json.loads(PLAN_PATH.read_text(encoding="utf-8-sig"))
except Exception:
    PLAN = {}
APP = Path(PLAN.get("app_dir") or Path(__file__).resolve().parent.parent)
LANG = (PLAN.get("language") or "en").lower()
S = {"title": "CAPRI // SETUP", "app": "Downloading Capri", "packages": "Installing her Python packages", "brain": "Downloading her AI brain",
     "ears": "Downloading her ears (speech recognition)", "voice": "Downloading her voice", "ok": "OK", "failed": "FAILED (details in install_log.txt)",
     "done": "Capri is ready.", "close": "Press Enter to close this window."}
S.update({k: v for k, v in (PLAN.get("strings") or {}).items() if v})
LOG = APP / "install_log.txt"
VENV_PY = APP / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
NOWIN = 0x08000000 if os.name == "nt" else 0          # CREATE_NO_WINDOW

# the same voice lists Capri uses (i18n.py); English uses her default voice
PIPER = {"en": ["en_US-kristin-medium", "en_US-amy-medium"], "fr": ["fr_FR-siwis-medium", "fr_FR-upmc-medium"], "de": ["de_DE-eva_k-x_low", "de_DE-thorsten-medium"],
         "es": ["es_MX-claude-high", "es_ES-sharvard-medium"], "it": ["it_IT-paola-medium", "it_IT-riccardo-x_low"], "pt": ["pt_BR-faber-medium"],
         "nl": ["nl_BE-nathalie-medium", "nl_NL-mls-medium"], "pl": ["pl_PL-gosia-medium", "pl_PL-darkman-medium"], "ru": ["ru_RU-irina-medium", "ru_RU-dmitri-medium"],
         "tr": ["tr_TR-dfki-medium", "tr_TR-fettah-medium"], "uk": ["uk_UA-lada-x_low", "uk_UA-ukrainian_tts-medium"], "ar": ["ar_JO-kareem-medium", "ar_JO-kareem-low"],
         "zh": ["zh_CN-huayan-medium", "zh_CN-huayan-x_low"]}

# ---------------------------------------------------------------- output
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
if os.name == "nt":
    os.system("")                                   # turn on colours in the Windows console
    try:
        import ctypes; ctypes.windll.kernel32.SetConsoleTitleW("CAPRI SETUP")
    except Exception: pass
PINK, TEAL, RED, DIM, END = "\033[38;2;255;42;109m", "\033[38;2;93;230;214m", "\033[38;2;255;80;80m", "\033[2m", "\033[0m"

def log(m):
    try:
        with open(LOG, "a", encoding="utf-8") as f: f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + str(m).rstrip() + "\n")
    except Exception: pass

def step(n, total, text): print(f"\n{PINK}[{n}/{total}]{END} {text}...", flush=True); log(f"== {text}")
def ok(extra=""): print(f"      {TEAL}{S['ok']}{END} {DIM}{extra}{END}", flush=True); log("ok " + extra)
def fail(err):
    print(f"      {RED}{S['failed']}{END}", flush=True); log("FAILED: " + str(err)); FAILS.append(str(err)[:200])
FAILS = []
class Skip(Exception):
    """Not an error: the step just doesn't apply (e.g. no voice for this language)."""

def run(cmd, live=True, timeout=None, **kw):
    """Run a command; live = show its own progress output in this window. Returns the exit code."""
    log("$ " + " ".join(str(c) for c in cmd))
    if live:
        return subprocess.run([str(c) for c in cmd], timeout=timeout, **kw).returncode
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, errors="replace", timeout=timeout, creationflags=NOWIN, **kw)
    log((r.stdout or "")[-3000:] + (r.stderr or "")[-3000:])
    return r.returncode

# ---------------------------------------------------------------- 0. the app itself (web installer)
KEEP = {"providers.json", "capri_settings.json", "capri_memory.json", "reminders.json", "spotify.json", "spotapi_session.json"}       # your stuff: never overwritten
def fetch_app(url):
    tmp = Path(tempfile.mkdtemp(prefix="capri_"))
    zp = tmp / "capri.zip"
    req = urllib.request.Request(url, headers={"User-Agent": "CapriSetup/4.0"})
    with urllib.request.urlopen(req, timeout=60) as r, open(zp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0); got = 0
        while True:
            chunk = r.read(1 << 16)
            if not chunk: break
            f.write(chunk); got += len(chunk)
            if total: print(f"\r      {got * 100 // total:3d}%  {got >> 20} / {total >> 20} MB", end="", flush=True)
    print()
    with zipfile.ZipFile(zp) as z:
        for n in z.namelist():                                   # refuse paths that escape the folder
            if n.startswith("/") or ".." in Path(n).parts: raise RuntimeError(f"unsafe path in zip: {n}")
        z.extractall(tmp / "x")
    root = next((p.parent for p in sorted((tmp / "x").rglob("server.py"), key=lambda p: len(p.parts))), None)
    if root is None: raise RuntimeError("that zip has no server.py in it")
    for src in root.rglob("*"):
        rel = src.relative_to(root); dst = APP / rel
        if src.is_dir(): dst.mkdir(parents=True, exist_ok=True); continue
        if rel.as_posix() in KEEP and dst.exists(): continue
        dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dst)
    shutil.rmtree(tmp, ignore_errors=True)

# ---------------------------------------------------------------- 1. python packages
def packages(voice):
    if not VENV_PY.exists():
        if run([sys.executable, "-m", "venv", APP / "venv"], live=False) != 0: raise RuntimeError("couldn't create the Python environment (venv)")
    run([VENV_PY, "-m", "pip", "install", "--upgrade", "pip", "--disable-pip-version-check", "-q"], live=False)
    req = [VENV_PY, "-m", "pip", "install", "--disable-pip-version-check", "--progress-bar", "on", "-r", APP / "requirements.txt"]
    if voice: req.append("piper-tts")
    for attempt in range(2):                                    # flaky Wi-Fi: one retry
        if run(req) == 0: return
        time.sleep(3)
    raise RuntimeError("pip install failed")

# ---------------------------------------------------------------- 2. the brain
def find_ollama():
    for p in (PLAN.get("ollama"), os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"), r"C:\Program Files\Ollama\ollama.exe", shutil.which("ollama")):
        if p and os.path.exists(p): return p
    return None

def ollama_up():
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3) as r: return json.loads(r.read().decode()).get("models", [])
    except Exception: return None

def brain(model):
    exe = find_ollama()
    if not exe: raise RuntimeError("Ollama isn't installed (get it from ollama.com, then run Start Menu > Capri > Repair)")
    if ollama_up() is None:
        subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=NOWIN | 0x00000008)   # detached
        for _ in range(40):
            time.sleep(0.5)
            if ollama_up() is not None: break
    tag = lambda n: n if ":" in n else n + ":latest"
    if tag(model) in {tag(m.get("name", "")) for m in (ollama_up() or [])}:
        return f"{model} (already there)"
    for attempt in range(2):
        if run([exe, "pull", model]) == 0: return model
        time.sleep(3)
    raise RuntimeError(f"ollama pull {model} failed")

# ---------------------------------------------------------------- 3. the ears
def ears():
    names = ["small.en", "base.en"] if LANG == "en" else ["small", "base"]   # same choice as server.py (calls) and the wake word
    code = ("import sys\nfrom faster_whisper import download_model\n"
            "for n in sys.argv[1:]:\n    print('      ' + n, flush=True); download_model(n)\n")
    if run([VENV_PY, "-c", code] + names) != 0: raise RuntimeError("speech model download failed")
    return ", ".join(names)

# ---------------------------------------------------------------- 4. the voice
def voice():
    vd = APP / "voices"; vd.mkdir(exist_ok=True)
    cands = PIPER.get(LANG, [])
    if not cands: raise Skip(f"no Piper voice exists for '{LANG}' yet: she replies in text")
    for v in cands:
        if (vd / (v + ".onnx")).exists(): return v
        if run([VENV_PY, "-m", "piper.download_voices", v, "--data-dir", vd], live=False, timeout=600) == 0 and (vd / (v + ".onnx")).exists(): return v
    raise RuntimeError("couldn't download a voice")

# ---------------------------------------------------------------- 5. language (+ speak) for Capri
def write_language(speak):
    """The installer just wrote install_language.json (fresh install / update): add "speak" to it.
       Run from Repair (file already used up by Capri): never touch her language, you may have changed it since."""
    f = APP / "install_language.json"
    data = {}
    try: data = json.loads(f.read_text(encoding="utf-8-sig"))
    except FileNotFoundError: pass
    except Exception: data = {"language": LANG}
    if speak: data["speak"] = True
    if data: f.write_text(json.dumps(data), encoding="utf-8")

# ---------------------------------------------------------------- main
def main():
    log(f"postinstall start: lang={LANG} plan={PLAN}")
    print(f"\n{PINK}  ▄████▄   ▄▄▄       ██▓███   ██▀███   ██▓\n ▒██▀ ▀█  ▒████▄    ▓██░  ██▒▓██ ▒ ██▒▓██▒\n ▒▓█    ▄ ▒██  ▀█▄  ▓██░ ██▓▒▓██ ░▄█ ▒▒██▒\n ▒▓▓▄ ▄██▒░██▄▄▄▄██ ▒██▄█▓▒ ▒▒██▀▀█▄  ░██░\n ▒ ▓███▀ ░ ▓█   ▓██▒▒██▒ ░  ░░██▓ ▒██▒░██░{END}\n")
    print(f"  {TEAL}{S['title']}{END}  {DIM}({LANG}){END}")
    want_voice = bool(PLAN.get("voice", True))
    steps = ([("app", lambda: fetch_app(PLAN["app_zip_url"]))] if PLAN.get("app_zip_url") else []) + [("packages", lambda: packages(want_voice))]
    if PLAN.get("brain", True): steps.append(("brain", lambda: brain(PLAN.get("model") or "llama3.2:3b")))
    if PLAN.get("ears", True): steps.append(("ears", ears))
    if want_voice: steps.append(("voice", voice))
    spoke = pkgs_ok = False
    for i, (key, fn) in enumerate(steps, 1):
        step(i, len(steps), S[key])
        if key in ("ears", "voice") and not pkgs_ok:
            fail("skipped: the Python packages didn't install"); continue
        try:
            extra = fn(); ok(extra or "")
            if key == "voice": spoke = True
            if key == "packages": pkgs_ok = True
        except Skip as e:
            print(f"      {DIM}-- {e}{END}", flush=True); log(f"skip: {e}")
        except Exception as e:
            log(traceback.format_exc()); fail(e)
            if key == "app": break                                  # nothing else makes sense without her files
    try: write_language(spoke)
    except Exception as e: fail(e)
    print(f"\n  {TEAL if not FAILS else RED}{S['done'] if not FAILS else S['failed']}{END}")
    for f in FAILS: print(f"    {DIM}- {f}{END}")
    log("postinstall end, failures: " + str(FAILS))
    if FAILS or "--wait" in sys.argv:
        try: input(f"\n  {S['close']} ")
        except EOFError: pass
    else:
        time.sleep(4)
    return 0                                                         # never fail the installer: Capri repairs the rest on her first start

if __name__ == "__main__":
    sys.exit(main())
