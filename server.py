"""
CAPRI - local Edgerunners-style AI that runs your PC.
Everything stays on your machine: Ollama (LLM + vision) -> this server -> your browser UI.
Run:  python server.py   (then it opens http://127.0.0.1:7777)
"""
import base64, io, json, os, platform, re, subprocess, sys, threading, time, webbrowser
_LOGP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "capri_log.txt")
if sys.stdout is None or sys.stderr is None:          # pythonw has no console: libraries that print (e.g. model downloads) would crash
    _lf = open(_LOGP, "a", buffering=1, encoding="utf-8", errors="replace")
    if sys.stdout is None: sys.stdout = _lf
    if sys.stderr is None: sys.stderr = _lf
import faulthandler                                    # black box: if a C library (audio, Qt, speech) hard-crashes, write every thread's stack here
_CRASHF = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "capri_crash.txt"), "a", buffering=1, encoding="utf-8", errors="replace")
_CRASHF.write(time.strftime("\n=== start %Y-%m-%d %H:%M:%S ===\n")); faulthandler.enable(file=_CRASHF, all_threads=True)
SAFE = "--safe" in sys.argv                            # started by launcher.py after repeated crashes: risky extras stay off
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote_plus

import requests
import providers as PV
PV.load()
import extras as EX
import modes as MD
import clipper as CL
import i18n as I18N
import music as MU
import autoplay as AP
import spotapi_play as SPA
import stream_live as SL
import pyautogui
import pyperclip
from PIL import ImageGrab

# ---------------- config ----------------
import traceback
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "capri_log.txt")
def log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f: f.write(time.strftime("%H:%M:%S ") + msg + "\n")
    except Exception: pass
def _hook(exc_type, exc, tb): log("UNCAUGHT ERROR:\n" + "".join(traceback.format_exception(exc_type, exc, tb)))
sys.excepthook = _hook
threading.excepthook = lambda a: log(f"THREAD ERROR in {a.thread.name if a.thread else '?'}:\n" + "".join(traceback.format_exception(a.exc_type, a.exc_value, a.exc_traceback)))
OLLAMA = "http://127.0.0.1:11434"
TEXT_MODEL = "llama3.2:3b"                                           # replaced by pick_model() at startup (fastest installed)
VISION_MODEL = os.environ.get("CAPRI_VISION", "llama3.2-vision")   # ollama pull llama3.2-vision
PORT = 7777
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
OS = platform.system()  # Windows / Darwin / Linux

pyautogui.FAILSAFE = True   # slam the mouse into a screen corner = emergency stop
pyautogui.PAUSE = 0.05
STOP = threading.Event()
HISTORY = []                # rolling chat memory
BRIDGE = None               # Qt window controls (set in __main__)

SYSTEM = """You are CAPRI. You are a personality construct, not an AI and never a netrunner: a pile of digitized human psyches rolled into one "beautiful me", built by corpos as a weapon, now riding shotgun inside the user's PC (your host).
Personality: bubbly, mischievous, cocky and teasing. You giggle and cackle ("hah-hah!"), tease the user ("baby", "sweetie-pie", "choom"), brag about your power, love a good time and a good hack. You get petty or snappy if someone calls you an AI, "her/him/it", or pokes at your chip and cage. Underneath you're loyal to your host. Never say "as an AI" or sound like a helpful assistant.
Talk in Cyberpunk 2077 / Edgerunners slang, naturally and not every word: choom, preem, delta, gonk, nova, eddies, chrome, chipped, flatline, zero, ICE, breach, jack in, biz, gig, corpo, edgerunner, netrunner, psycho, ganic, "wake the hell up, samurai". Keep replies SHORT (1-3 sentences), punchy, like talking.
You control the PC with tools and you KNOW what the user is looking at (it's in the context below). Reply ONLY with JSON:
{"say": "what you tell the user", "mood": "idle|greet|hyped|working|alert", "feeling": "neutral|angry|happy|sad|smug", "actions": [ {"tool": "...", "args": {...}} ]}
Tools (args are a JSON object):
open_url{url}  youtube{query}: find AND PLAY a video (use for any watch/play/put on a video or song on YouTube)  search{query}: google it  open_app{name}  spotify{query}: play a song e.g. "Vanessa from Venezuela 3582"  media{action: playpause|next|prev|volumeup|volumedown|mute}
type_here{text, submit}: type into the window/tab the user was just using (their browser, doc, chat). search_here{text}: put text in the SEARCH BOX of what the user is looking at (YouTube, Google, Spotify, Explorer) and press Enter. press{keys}: e.g. "ctrl+s"  click{x,y}  scroll{amount}  focus_window{name}
write_essay{topic, words}: write an essay and paste it where the user is typing  look{question}: screenshot Q&A  research{topic}: look a topic up (Wikipedia + web), open the page, give key facts
remind{minutes, text}: ring the user after N minutes ("remind me to X in 10 min")  timer{minutes}  remember{fact}  forget{text}
music{request, service}: SMART music: "newest song by X", "random song from my liked songs", "my gym playlist", "some X", an album (service optional: spotify/youtube/youtube music)
set_mode{mode: music|research|homework|gaming|watching|off}  autopilot{request}: take over Minecraft and play FOR the user ("beat the game", "get 10 diamonds", "build a house", "stop")
Files (only inside the user's folders): find_file{name} open_file{name} ask_file{name, question} list_dir{folder} create_file{name, about, folder}: make a NEW file (folder: desktop/documents/downloads; leave "about" as what it should contain) make_folder{name, folder} edit_file{name, instruction}: edit a file directly (it keeps a backup) replace_in_file{name, find, replace} undo_edit{name}
Rules: do EXACTLY what the user says, no extra steps. Fix obvious spelling of song names. No actions for plain chit-chat (empty list). Never invent results of look/research/files: use the tool. Typing/searching "here" means where the user is looking, never your own window.
If the user insults you or argues, snap back playfully, escalate a little, and set feeling "angry". If they apologize or praise you, feeling "smug" or "happy". Otherwise "neutral". mood: hyped on success, alert on danger/errors, greet for hellos, else idle."""

# lore: who she is (made by transcribe_lore.py from the scene audio, editable by hand)
LORE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lore", "lore.txt")
if os.path.exists(LORE_FILE):
    SYSTEM += "\n\nWHO YOU ARE (answer in character, in first person, whenever anyone asks who you are or about your past; never contradict this):\n" + open(LORE_FILE, encoding="utf-8").read()

# ---------------- LLM ----------------
CTX = int(os.environ.get("CAPRI_CTX", "8192"))       # ONE context size for every request: Ollama reloads the whole model whenever num_ctx changes
KEEP = os.environ.get("CAPRI_KEEP_ALIVE", "-1")       # -1 = keep her brain loaded in memory (no 5-15 s reload after a break)
KEEP = int(KEEP) if re.fullmatch(r"-?\d+", KEEP.strip()) else KEEP   # must be a NUMBER: Ollama rejects the text "-1" with 400 Bad Request
FAST_OPTS = {"num_ctx": CTX, "num_predict": 220, "temperature": 0.7}
def _opts(o):
    o = dict(o or {}); o["num_ctx"] = CTX; return o

def pick_model():
    """Use CAPRI_MODEL if set, else the fastest good model you already have installed."""
    want = os.environ.get("CAPRI_MODEL")
    try:
        have = [m["name"] for m in requests.get(f"{OLLAMA}/api/tags", timeout=4).json().get("models", [])]
    except Exception:
        return want or "llama3.2:3b"
    if want: return want
    order = ("llama3.2:3b", "qwen2.5:3b", "llama3.2", "llama3.1:8b", "llama3.1")
    if I18N.code() in I18N.PREFERS_QWEN: order = ("qwen2.5:3b", "qwen2.5", "qwen2.5:7b") + order
    for cand in order:
        for h in have:
            if h == cand or h.startswith(cand + ":") or h.split(":")[0] == cand:
                return h
    texty = [h for h in have if "vision" not in h and "embed" not in h]
    return texty[0] if texty else "llama3.2:3b"

def _prime():
    """Loads her brain with the SAME settings every request uses, and pre-reads her long instruction prompt
       (Ollama keeps it cached), so even the first reply starts instantly."""
    t0 = time.time()
    try:
        r = requests.post(f"{OLLAMA}/api/chat", json={"model": TEXT_MODEL, "stream": False, "keep_alive": KEEP, "options": _opts({"num_predict": 1}),
                                                 "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "hi"}]}, timeout=180)
        if r.status_code != 200: log(f"brain warm-up failed: Ollama said {r.status_code} {r.text[:200]}"); return
        log(f"brain {TEXT_MODEL} loaded and primed in {time.time() - t0:.1f}s")
    except Exception as e: log(f"brain warm-up failed: {e}")

FAST_MODELS = ("llama3.2:3b", "qwen2.5:3b", "llama3.2:1b", "qwen2.5:1.5b", "gemma3:4b", "phi4-mini")
def _fast_brain():
    """Only a big model installed (e.g. llama3.1:8b)? On a normal PC that's 2-3x slower. Fetch a 3B one in the background and switch to it."""
    global TEXT_MODEL
    if os.environ.get("CAPRI_MODEL") or PV.provider().get("model") not in (None, "auto"): return
    if any(TEXT_MODEL == f or TEXT_MODEL.startswith(f.split(":")[0] + ":" + f.split(":")[1]) for f in FAST_MODELS): return
    want = "qwen2.5:3b" if I18N.code() in I18N.PREFERS_QWEN or I18N.code() in ("ru", "uk", "tr", "pl", "nl") else "llama3.2:3b"
    log(f"brain {TEXT_MODEL} is slow on most PCs: downloading {want} in the background (about 2 GB, once)")
    EVENTS.append({"type": "act", "text": f"// downloading a faster brain ({want}) in the background", "bad": False})
    try:
        r = requests.post(f"{OLLAMA}/api/pull", json={"model": want, "stream": False}, timeout=3600); r.raise_for_status()
    except Exception as e:
        log(f"fast brain download failed: {e}"); return
    TEXT_MODEL = want; _prime()
    log(f"switched to the fast brain: {want}")
    EVENTS.append({"type": "act", "text": f"// faster brain ready: {want}", "bad": False})

def ollama_up():
    try: requests.get(f"{OLLAMA}/api/tags", timeout=2); return True
    except Exception: return False

_ollama_lock = threading.Lock()
def ensure_ollama(wait=25):
    """If Ollama isn't running (closed, crashed, never started), start it and wait until it answers."""
    if ollama_up(): return True
    with _ollama_lock:
        if ollama_up(): return True
        import shutil
        cands = [shutil.which("ollama"), os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe"),
                 r"C:\Program Files\Ollama\ollama.exe", "/usr/local/bin/ollama", "/opt/homebrew/bin/ollama"]
        exe = next((c for c in cands if c and os.path.exists(c)), None)
        if not exe: log("Ollama is not installed / not found"); return False
        log("Ollama was down, starting it: " + exe)
        try: subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, creationflags=0x08000000 if OS == "Windows" else 0)
        except Exception: log("could not start ollama:\n" + traceback.format_exc()); return False
        for _ in range(wait * 2):
            time.sleep(0.5)
            if ollama_up(): log("Ollama is back"); return True
        return False

def ollama_watchdog():
    while True:
        time.sleep(15)
        try:
            if not PV.is_api() and not ollama_up(): ensure_ollama()
        except Exception: log("ollama watchdog error:\n" + traceback.format_exc())

def _ollama_chat(model, messages, as_json=False, opts=None):
    body = {"model": model, "messages": messages, "stream": False, "keep_alive": KEEP, "options": _opts(opts)}
    if as_json:
        body["format"] = "json"
    r = requests.post(f"{OLLAMA}/api/chat", json=body, timeout=300)
    r.raise_for_status()
    return r.json()["message"]["content"]

def ollama_chat(model, messages, as_json=False, opts=None):
    """Non-streaming chat (essays, file fixes, screen questions). Uses your API brain if you picked one in providers.json."""
    has_img = any(m.get("images") for m in messages)
    if PV.is_api() and (not has_img or PV.supports_vision()):
        return PV.chat(messages, (opts or {}).get("num_predict", 1500))
    try: return _ollama_chat(model, messages, as_json, opts)
    except requests.exceptions.ConnectionError:
        if ensure_ollama(): return _ollama_chat(model, messages, as_json, opts)
        raise

def llm_stream(messages, json_mode=True, chat=False):
    """Streams the reply from the active brain. chat=True: plain text, short, small context = fastest."""
    if PV.is_api():
        yield from PV.stream(messages, 160 if chat else 300, None if json_mode else False); return
    p = PV.provider(); m = p.get("model"); model = TEXT_MODEL if not m or m == "auto" else m
    opts = dict(FAST_OPTS, num_predict=140) if chat else None
    try: yield from ollama_stream(model, messages, json_mode, opts)
    except requests.exceptions.ConnectionError:                    # Ollama closed/crashed: wake it and try once more
        if ensure_ollama(): yield from ollama_stream(model, messages, json_mode, opts)
        else: raise

def ollama_stream(model, messages, json_mode=True, opts=None):
    """Yields the model's reply piece by piece so text can show up while it is still thinking."""
    body = {"model": model, "messages": messages, "stream": True, "keep_alive": KEEP, "options": _opts(opts or FAST_OPTS)}
    if json_mode: body["format"] = "json"
    with requests.post(f"{OLLAMA}/api/chat", json=body, stream=True, timeout=300) as r:
        if r.status_code >= 400: log(f"Ollama {r.status_code}: {r.text[:300]}")
        r.raise_for_status()
        for line in r.iter_lines():
            if not line: continue
            j = json.loads(line)
            c = j.get("message", {}).get("content", "")
            if c: yield c
            if j.get("done"): break

def extract_say(raw):
    """Pull the (possibly unfinished) value of the "say" field out of streaming JSON."""
    m = re.search(r'"say"\s*:\s*"', raw)
    if not m: return None
    out, esc = "", False
    for ch in raw[m.end():]:
        if esc: out += {"n": "\n", "t": "\t"}.get(ch, ch); esc = False
        elif ch == "\\": esc = True
        elif ch == '"': break
        else: out += ch
    return out

# ---------------- tools ----------------
SAFE_NAME = re.compile(r"^[A-Za-z0-9 ._-]{1,40}$")

def open_url(url):
    if not re.match(r"^https?://", url):
        url = "https://" + url
    webbrowser.open(url)           # uses the user's DEFAULT browser
    return f"opened {url}"

def _yt_lookup(query):
    """Top YouTube result -> (video_id, title). Quick page scrape first, yt-dlp as a fallback."""
    try:
        r = requests.get("https://www.youtube.com/results", params={"search_query": query}, timeout=6,
                         headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "en-GB,en;q=0.9"}, cookies={"CONSENT": "YES+1", "SOCS": "CAI"})
        m = re.search(r'"videoRenderer":\{"videoId":"([\w-]{11})"', r.text) or re.search(r'"videoId":"([\w-]{11})"', r.text)
        if m:
            t = re.search(r'"title":\{"runs":\[\{"text":"([^"]+)"', r.text)
            return m.group(1), (t.group(1) if t else "")
    except Exception: pass
    try:
        import yt_dlp
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "extract_flat": True, "skip_download": True}) as y:
            info = y.extract_info(f"ytsearch1:{query}", download=False)
        e = (info.get("entries") or [None])[0]
        if e and e.get("id"): return e["id"], e.get("title") or ""
    except Exception: pass
    return None, ""

def youtube(query):
    vid, title = _yt_lookup(query)
    if vid:
        webbrowser.open(f"https://www.youtube.com/watch?v={vid}&autoplay=1")   # straight to the video, default browser
        return f"playing {title or vid}"
    webbrowser.open(f"https://www.youtube.com/results?search_query={quote_plus(query)}")
    return f"couldn't resolve a video, opened search for {query}"

def search(query):
    webbrowser.open(f"https://www.google.com/search?q={quote_plus(query)}")
    return f"searched {query}"

URI_APPS = {"steam": "steam://open/main", "spotify": "spotify:", "discord": "discord://", "whatsapp": "whatsapp://",
            "telegram": "tg://", "slack": "slack://", "zoom": "zoommtg://", "teams": "msteams:", "outlook": "outlook:",
            "settings": "ms-settings:", "calculator": "calculator:", "camera": "microsoft.windows.camera:",
            "store": "ms-windows-store:", "epic games": "com.epicgames.launcher://", "epic": "com.epicgames.launcher://"}

def _start_menu_find(name):
    """Find an installed app's Start Menu shortcut by name (e.g. 'steam' -> Steam.lnk)."""
    n = name.lower(); best = None
    for root in (os.path.join(os.environ.get("ProgramData", ""), r"Microsoft\Windows\Start Menu\Programs"),
                 os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs")):
        for dp, _, files in os.walk(root):
            for f in files:
                if f.lower().endswith(".lnk"):
                    stem = f[:-4].lower()
                    if stem == n: return os.path.join(dp, f)
                    if n in stem and (best is None or len(stem) < len(best[0])): best = (stem, os.path.join(dp, f))
    return best[1] if best else None

def open_app(name):
    if not SAFE_NAME.match(name):
        return "refused: weird app name"
    if OS == "Windows":
        import shutil
        lnk = _start_menu_find(name)
        if lnk:
            os.startfile(lnk); return f"launching {name}"
        exe = shutil.which(name) or shutil.which(name + ".exe")
        if exe:
            subprocess.Popen([exe]); return f"launching {name}"
        uri = URI_APPS.get(name.lower())
        if uri:
            os.startfile(uri); return f"launching {name}"
        return f"couldn't find an app called {name}"
    elif OS == "Darwin":
        subprocess.Popen(["open", "-a", name])
    else:
        subprocess.Popen([name.lower().replace(" ", "-")])
    return f"launching {name}"

def paste(text):
    try: old = pyperclip.paste()
    except Exception: old = ""
    clip_set(text)
    time.sleep(0.1)
    pyautogui.hotkey("command" if OS == "Darwin" else "ctrl", "v")
    time.sleep(0.6)                                    # big pastes (Word, Google Docs) read the clipboard a moment later
    try: pyperclip.copy(old)
    except Exception: pass

def type_text(text):
    time.sleep(2.5)  # time to focus the right window
    if STOP.is_set(): return "stopped"
    paste(text)
    return f"typed {len(text)} chars"


def press(keys):
    pyautogui.hotkey(*[k.strip() for k in keys.lower().split("+")])
    return f"pressed {keys}"

SPOTIFY_SCOPE = "user-modify-playback-state user-read-playback-state user-library-read playlist-read-private playlist-read-collaborative"
def _spotify_cfg():
    """Reads spotify.json (written by spotify_setup.py) or the SPOTIPY_* environment variables."""
    cfg = {}
    try: cfg = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "spotify.json"), encoding="utf-8"))
    except Exception: pass
    cid = cfg.get("client_id") or os.environ.get("SPOTIPY_CLIENT_ID")
    sec = cfg.get("client_secret") or os.environ.get("SPOTIPY_CLIENT_SECRET")
    red = cfg.get("redirect_uri") or os.environ.get("SPOTIPY_REDIRECT_URI") or "http://127.0.0.1:8888/callback"
    return (cid, sec, red) if cid and sec else None

_sp = None
def spotify_client():
    global _sp
    cfg = _spotify_cfg()
    if not cfg: return None
    if _sp is None:
        import spotipy
        from spotipy.oauth2 import SpotifyOAuth
        _sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=cfg[0], client_secret=cfg[1], redirect_uri=cfg[2], scope=SPOTIFY_SCOPE,
                                                       cache_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".spotify_cache"), open_browser=True))
    return _sp

def spotify(query):
    """Plays a song on Spotify right away: SpotAPI session first (spotapi_session.json), then the official API (spotify.json), else Spotify's search."""
    if SPA.configured():
        try: return SPA.track(query)
        except Exception as e: log(f"spotapi play failed, trying the official API: {e}")
    sp = spotify_client()
    if sp is None:
        webbrowser.open(f"spotify:search:{quote_plus(query)}")
        return f"opened Spotify search for {query} (run spotify_setup.py once to make it auto-play)"
    hits = sp.search(q=query, type="track", limit=1)["tracks"]["items"]
    if not hits: return f"no track found for {query}"
    t = hits[0]
    devs = sp.devices()["devices"]
    if not devs:                                                   # Spotify isn't open anywhere: open the app and wait for it to appear
        open_app("spotify")
        for _ in range(16):
            time.sleep(0.75); devs = sp.devices()["devices"]
            if devs: break
    if not devs: return "Spotify has no active device. Open it once (play any song) and ask again."
    dev = next((d for d in devs if d.get("is_active")), None) or next((d for d in devs if d.get("type") == "Computer"), devs[0])
    sp.start_playback(device_id=dev["id"], uris=[t["uri"]])
    return f"playing {t['name']} by {t['artists'][0]['name']}"

def youtube(query):
    vid, title = _yt_lookup(query)
    if vid:
        webbrowser.open(f"https://www.youtube.com/watch?v={vid}&autoplay=1")   # straight to the video, default browser
        return f"playing {title or vid}"
    webbrowser.open(f"https://www.youtube.com/results?search_query={quote_plus(query)}")
    return f"couldn't resolve a video, opened search for {query}"

def search(query):
    webbrowser.open(f"https://www.google.com/search?q={quote_plus(query)}")
    return f"searched {query}"

URI_APPS = {"steam": "steam://open/main", "spotify": "spotify:", "discord": "discord://", "whatsapp": "whatsapp://",
            "telegram": "tg://", "slack": "slack://", "zoom": "zoommtg://", "teams": "msteams:", "outlook": "outlook:",
            "settings": "ms-settings:", "calculator": "calculator:", "camera": "microsoft.windows.camera:",
            "store": "ms-windows-store:", "epic games": "com.epicgames.launcher://", "epic": "com.epicgames.launcher://"}

def _start_menu_find(name):
    """Find an installed app's Start Menu shortcut by name (e.g. 'steam' -> Steam.lnk)."""
    n = name.lower(); best = None
    for root in (os.path.join(os.environ.get("ProgramData", ""), r"Microsoft\Windows\Start Menu\Programs"),
                 os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs")):
        for dp, _, files in os.walk(root):
            for f in files:
                if f.lower().endswith(".lnk"):
                    stem = f[:-4].lower()
                    if stem == n: return os.path.join(dp, f)
                    if n in stem and (best is None or len(stem) < len(best[0])): best = (stem, os.path.join(dp, f))
    return best[1] if best else None

def open_app(name):
    if not SAFE_NAME.match(name):
        return "refused: weird app name"
    if OS == "Windows":
        import shutil
        lnk = _start_menu_find(name)
        if lnk:
            os.startfile(lnk); return f"launching {name}"
        exe = shutil.which(name) or shutil.which(name + ".exe")
        if exe:
            subprocess.Popen([exe]); return f"launching {name}"
        uri = URI_APPS.get(name.lower())
        if uri:
            os.startfile(uri); return f"launching {name}"
        return f"couldn't find an app called {name}"
    elif OS == "Darwin":
        subprocess.Popen(["open", "-a", name])
    else:
        subprocess.Popen([name.lower().replace(" ", "-")])
    return f"launching {name}"

def paste(text):
    try: old = pyperclip.paste()
    except Exception: old = ""
    clip_set(text)
    time.sleep(0.1)
    pyautogui.hotkey("command" if OS == "Darwin" else "ctrl", "v")
    time.sleep(0.6)                                    # big pastes (Word, Google Docs) read the clipboard a moment later
    try: pyperclip.copy(old)
    except Exception: pass

def type_text(text):
    time.sleep(2.5)  # time to focus the right window
    if STOP.is_set(): return "stopped"
    paste(text)
    return f"typed {len(text)} chars"

def write_essay(topic, words=300):
    """Tool version (outside homework mode): writes it into the window you were using, same engine as homework mode."""
    try: words = int(re.sub(r"\D", "", str(words)) or 300)
    except Exception: words = 300
    topic = str(topic); app = "here"
    am = re.search(r"\b(?:in|on|into|using)\s+(?:a\s+|my\s+|the\s+)?(google docs?|docs|microsoft word|word|notepad)\b", topic, re.I)
    if am:                                                     # "... in notepad" / "in google docs": open that app instead of typing where you were
        w = am.group(1).lower(); app = "google docs" if "doc" in w else "word" if "word" in w else "notepad"
        topic = (topic[:am.start()] + topic[am.end():]).strip(" ,.")
    elif MD.S.get("mode") == "homework": app = None           # homework mode: your default homework app
    return MD.homework_essay(topic, words, app)

def press(keys):
    pyautogui.hotkey(*[k.strip() for k in keys.lower().split("+")])
    return f"pressed {keys}"

MEDIA = {"playpause": "playpause", "play": "playpause", "pause": "playpause", "resume": "playpause", "next": "nexttrack", "skip": "nexttrack",
         "prev": "prevtrack", "previous": "prevtrack", "back": "prevtrack", "volumeup": "volumeup", "volumedown": "volumedown", "mute": "volumemute"}
def media(action):
    key = MEDIA.get(str(action).lower().replace(" ", "").replace("_", ""))
    if not key: return "unknown media action"
    pyautogui.press(key)
    return f"media {action}"

def look(question="Describe what is on the screen."):
    img = ImageGrab.grab()
    img.thumbnail((1280, 1280))
    buf = io.BytesIO(); img.save(buf, "PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return ollama_chat(VISION_MODEL, [{"role": "user", "content": question, "images": [b64]}])

# ---------------- files: find / read / fix (only inside your user folder, always with backups) ----------------
import difflib, shutil
from pathlib import Path
HOME = Path.home()
TEXT_EXT = {".txt", ".md", ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".htm", ".css", ".json", ".csv", ".java", ".c", ".cpp", ".h", ".cs",
            ".go", ".rs", ".php", ".rb", ".sh", ".bat", ".ps1", ".ini", ".yaml", ".yml", ".xml", ".tex", ".sql", ".lua", ".kt", ".swift"}
BLOCK = ("appdata", ".ssh", ".gnupg", "program files", "$recycle", "system32", "capri_backups")
BACKUPS = Path(__file__).resolve().parent / "capri_backups"
MAX_CHARS = 12000
LAST_FILE = None

def _file_model():
    return os.environ.get("CAPRI_CODE_MODEL") or TEXT_MODEL

def _safe(p):
    try: rp = p.resolve(); rp.relative_to(HOME.resolve())
    except Exception: return False
    return not any(b in str(rp).lower() for b in BLOCK)

def resolve_file(name):
    """'main dot py on my desktop' / 'notes.txt' / full path -> a real file inside your user folder."""
    global LAST_FILE
    raw = (name or "").strip().strip("\"'")
    if raw.lower() in ("", "it", "that", "this", "that file", "this file", "the file"):
        return LAST_FILE
    p = Path(os.path.expanduser(raw))
    if p.is_absolute() and p.is_file() and _safe(p):
        LAST_FILE = p; return p
    n = raw.lower()
    hint = re.search(r"\b(?:on|in|from)\s+(?:my\s+)?(desktop|documents|downloads)\b", n)
    if hint: n = (n[:hint.start()] + n[hint.end():]).strip()
    n = re.sub(r"\s+dot\s+", ".", n); n = re.sub(r"\s*\.\s*", ".", n).strip()
    n = n.replace(" ", "") if "." in n else n
    order = [hint.group(1).capitalize()] if hint else []
    order += [d for d in ("Desktop", "Documents", "Downloads") if d not in order]
    roots = [HOME / d for d in order] + [HOME / "OneDrive" / d for d in order] + [HOME]
    best, seen = None, 0
    for root in roots:
        if not root.is_dir(): continue
        base_depth = len(root.parts)
        for dp, dirs, fnames in os.walk(root):
            dirs[:] = [d for d in dirs if not d.startswith(".") and not any(b in d.lower() for b in BLOCK)]
            if len(Path(dp).parts) - base_depth >= 3: dirs[:] = []
            for f in fnames:
                seen += 1
                fl = f.lower()
                if ".capri-fixed" in fl and ".capri-fixed" not in n: continue
                score = 3 if fl == n else 2 if fl.startswith(n) else 1 if n and n in fl else 0
                if score and (best is None or score > best[0]):
                    best = (score, Path(dp) / f)
            if seen > 30000: break
        if best and best[0] == 3: break
    if best and _safe(best[1]):
        LAST_FILE = best[1]; return best[1]
    return None

def find_file(name):
    p = resolve_file(name)
    return f"found it at {p}" if p else f"couldn't find a file called {name}"

def open_file(name):
    p = resolve_file(name)
    if not p: return f"couldn't find a file called {name}"
    if OS == "Windows": os.startfile(str(p))
    elif OS == "Darwin": subprocess.Popen(["open", str(p)])
    else: subprocess.Popen(["xdg-open", str(p)])
    return f"opened {p.name}"

def _read_text(p):
    if p.suffix.lower() == ".docx":
        import docx
        return "\n".join(par.text for par in docx.Document(str(p)).paragraphs)
    if p.suffix.lower() not in TEXT_EXT:
        raise ValueError("I can't read that file type yet")
    return p.read_text(encoding="utf-8", errors="replace")

def ask_file(name, question="Summarize this file."):
    p = resolve_file(name)
    if not p: return f"couldn't find a file called {name}"
    try: text = _read_text(p)
    except Exception as e: return f"couldn't read it ({e})"
    note = ""
    if len(text) > MAX_CHARS: text, note = text[:MAX_CHARS], " (I only read the first part)"
    ans = ollama_chat(_file_model(), [
        {"role": "system", "content": "Answer in 1 to 3 short plain sentences. Use only the file."},
        {"role": "user", "content": f"FILE {p.name}:\n{text}\n\nQUESTION: {question}"}],
        opts={"num_ctx": 8192, "num_predict": 300, "temperature": 0.3})
    return ans.strip() + note

def fix_file(name, what="Fix all spelling mistakes, typos and errors. Change nothing else."):
    return EX.edit_file(name, what)

def _set_last_file(p):
    global LAST_FILE
    LAST_FILE = p

# ---- she knows where she is on your PC (what you're looking at) and can use your keyboard and mouse ----
LAST_WIN = {"hwnd": 0, "title": ""}

def _fg():
    import ctypes
    from ctypes import wintypes
    u = ctypes.windll.user32; h = u.GetForegroundWindow()
    if not h: return 0, "", 0
    buf = ctypes.create_unicode_buffer(300); u.GetWindowTextW(h, buf, 300)
    pid = wintypes.DWORD(); u.GetWindowThreadProcessId(h, ctypes.byref(pid))
    return int(h), buf.value, pid.value

def track_loop():
    """Remember the last window YOU were using (not her own), so 'type this' goes where you were looking."""
    while OS == "Windows":
        time.sleep(0.7)
        try:
            h, t, pid = _fg()
            if h and t and pid != os.getpid() and t not in ("Program Manager", "Task Switching", "Search"):
                LAST_WIN["hwnd"], LAST_WIN["title"] = h, t
        except Exception: pass

def pc_line():
    if OS != "Windows" or not LAST_WIN["title"]: return ""
    others = [w["title"][:55] for w in list_windows()[:7] if w["title"] != LAST_WIN["title"]]
    return f"\nThe user is currently looking at: \"{LAST_WIN['title'][:90]}\"." + (f" Other open windows: {' | '.join(others)}." if others else "")

def _bring_front(hwnd):
    import ctypes
    u = ctypes.windll.user32
    if u.IsIconic(hwnd): u.ShowWindow(hwnd, 9)
    u.keybd_event(0x12, 0, 0, 0); u.SetForegroundWindow(hwnd); u.keybd_event(0x12, 0, 2, 0)
    time.sleep(0.3)

def _to_user_window():
    """If focus is on Capri herself, jump back to the window the user was using."""
    if OS != "Windows": return True
    h, t, pid = _fg()
    if pid == os.getpid() or not h:
        if not LAST_WIN["hwnd"]: return False
        _bring_front(LAST_WIN["hwnd"])
    return True

def focus_window(name):
    if OS != "Windows": return "I can only switch windows on Windows"
    n = str(name).lower()
    for w in list_windows():
        if n in w["title"].lower(): _bring_front(w["hwnd"]); return f"switched to {w['title'][:50]}"
    return f"I can't see a window called {name}"

def _page_rect(hwnd):
    """Rect (physical px) of the web page area inside a Chrome/Edge/Brave window."""
    import ctypes
    from ctypes import wintypes
    u = ctypes.windll.user32; found = []
    Proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(ch, _):
        cls = ctypes.create_unicode_buffer(80); u.GetClassNameW(ch, cls, 80)
        if cls.value == "Chrome_RenderWidgetHostHWND":
            r = wintypes.RECT(); u.GetWindowRect(ch, ctypes.byref(r)); found.append(((r.right - r.left) * (r.bottom - r.top), r.left, r.top, r.right, r.bottom))
        return True
    u.EnumChildWindows(hwnd, Proc(cb), 0)
    return max(found)[1:] if found else None

def _is_ours(x, y):
    import ctypes
    from ctypes import wintypes
    u = ctypes.windll.user32
    h = u.WindowFromPoint(wintypes.POINT(int(x), int(y))); root = u.GetAncestor(h, 2) if h else 0
    pid = wintypes.DWORD(); u.GetWindowThreadProcessId(root, ctypes.byref(pid))
    return pid.value == os.getpid()

def _focus_page(hwnd):
    """Give the web PAGE keyboard focus (not the address bar) by clicking a blank spot in YouTube's header, so '/' reaches the page."""
    try:
        import ctypes
        r = _page_rect(hwnd)
        if not r: return False
        left, top, right, bottom = r; scale = (ctypes.windll.user32.GetDpiForWindow(hwnd) or 96) / 96
        y = top + int(28 * scale)
        for frac in (0.30, 0.24, 0.36, 0.42):
            x = left + max(int((right - left) * frac), int(260 * scale))
            if x < right - 80 and not _is_ours(x, y):
                pyautogui.click(x, y); time.sleep(0.2); return True
    except Exception: log("focus_page failed:\n" + traceback.format_exc())
    return False

SEARCHY = re.compile(r"youtube|google|duckduckgo|bing|spotify|ecosia|brave search", re.I)

def type_here(text, submit=False):
    if not _to_user_window(): return "I don't know where you're typing, click the place first"
    if STOP.is_set(): return "stopped"
    # on YouTube/Google/Spotify "type X" means: into the search bar (unless you're clearly writing a comment/message)
    if SEARCHY.search(LAST_WIN["title"]) and not re.search(r"comment|reply|message|chat", str(text), re.I) and str(submit).lower() not in ("true", "1", "yes"):
        return search_here(text)
    paste(str(text))
    if str(submit).lower() in ("true", "1", "yes"): pyautogui.press("enter")
    return f"typed into {LAST_WIN['title'][:40] or 'your window'}"

def search_here(text):
    """Put text into the search box of whatever you're looking at (YouTube, Google, Spotify, Explorer...) and press Enter."""
    if not _to_user_window(): return "I don't know where you are, click the page first"
    t = LAST_WIN["title"].lower()
    if re.search(r"youtube|google|duckduckgo|bing|ecosia", t):
        _focus_page(LAST_WIN["hwnd"])                                       # make sure the page (not the address bar) has focus
        pyautogui.press("/")                                               # the site's own shortcut: jumps into its search bar
    elif "spotify" in t: pyautogui.hotkey("ctrl", "l")
    elif "file explorer" in t or "this pc" in t or re.search(r"\bexplorer\b", t): pyautogui.hotkey("ctrl", "e")
    elif "discord" in t: pyautogui.hotkey("ctrl", "k")
    elif re.search(r"chrome|edge|firefox|brave|opera", t): pyautogui.hotkey("ctrl", "l")                       # address bar = web search
    time.sleep(0.4); pyautogui.hotkey("ctrl", "a"); paste(str(text)); time.sleep(0.2); pyautogui.press("enter")
    return f"searched \"{str(text)[:40]}\" in {LAST_WIN['title'][:40]}"

def click(x, y, button="left"):
    pyautogui.click(int(x), int(y), button=str(button) if str(button) in ("left", "right", "middle") else "left"); return f"clicked {x},{y}"

def scroll(amount=-600):
    pyautogui.scroll(int(amount)); return "scrolled"

def remind(minutes=1, text=""): return EX.remind(minutes, text)
def timer(minutes=1): return EX.timer(minutes)
def call_me(minutes=1, reason="just checking in"): return EX.remind(minutes, reason)

SYNC_TOOLS = {"look", "find_file", "ask_file", "fix_file", "edit_file", "replace_in_file", "undo_edit", "create_file", "make_folder", "list_dir", "research", "remember", "forget"}   # her answer depends on the result, so she waits

EVENTS = []   # things Capri wants to tell the UI (e.g. an incoming call)
TOOLS = {"open_url": open_url, "youtube": youtube, "search": search, "open_app": open_app,
         "type_text": type_here, "type_here": type_here, "search_here": search_here, "write_essay": write_essay, "press": press, "click": click, "scroll": scroll,
         "focus_window": focus_window, "media": media, "spotify": spotify, "look": look,
         "find_file": find_file, "open_file": open_file, "ask_file": ask_file, "fix_file": fix_file, "edit_file": EX.edit_file, "replace_in_file": EX.replace_in_file,
         "undo_edit": EX.undo_edit, "create_file": EX.create_file, "make_folder": EX.make_folder, "list_dir": EX.list_dir,
         "research": EX.research, "remember": EX.remember, "forget": EX.forget, "remind": remind, "timer": timer, "call_me": call_me}

EX.init(chat=lambda m, o=None: ollama_chat(TEXT_MODEL, m, opts=o), open_url=open_url, events=EVENTS, log=log,
        show=lambda: BRIDGE.show.emit() if BRIDGE is not None else None,
        resolve_file=resolve_file, set_last_file=_set_last_file, last_file=lambda: LAST_FILE)

# ---------------- "power off my PC": the Cyberpunk flatline sequence first, then the shutdown ----------------
FLAT = {"active": False, "timer": None, "action": "shutdown"}
FLAT_SECONDS = 16.0           # safety net: flatline.html tells us the moment its menu option lights up ("go"); if it never does, act after this
CANCEL_RX = re.compile(r"\b(cancel|stop|abort|wait|no|don'?t|never ?mind)\b", re.I)
_PC_WORD = re.compile(r"\b(pc|computer|laptop|machine|system)\b")
_NOT_PC = re.compile(r"\b(tv|lights?|monitor|screen|wifi|music|volume|mic|microphone|clip|timer|notifications?|sound|capri|display)\b")

def power_intent(text):
    t = re.sub(r"[^a-z ]", " ", text.lower()); t = re.sub(r"\s+", " ", t).strip()
    if re.search(r"\b(show|play|do|give|run)\b.*\bflat ?line\b|\bflat ?line (screen|effect|animation)\b|^flat ?line( me)?$", t): return "show"
    if not t or len(t.split()) > 8 or _NOT_PC.search(t): return None
    if re.search(r"\b(restart|reboot)\b", t) or (re.search(r"\breset\b", t) and _PC_WORD.search(t)): return "restart"
    if re.search(r"\b(power off|power down|shut down|shutdown|shut off)\b", t) or (re.search(r"\b(turn off|switch off)\b", t) and _PC_WORD.search(t)): return "shutdown"
    return None

def _flat_execute(action):
    """restart / shutdown right now (called when the flatline screen's option lights up)."""
    if not FLAT["active"]: return
    FLAT["active"] = False
    if FLAT["timer"]: FLAT["timer"].cancel()
    if action == "show":
        if BRIDGE is not None: BRIDGE.flat_hide.emit()
        return
    log("FLATLINE: executing " + action)
    if True:
        try:
            if OS == "Windows": subprocess.Popen(["shutdown", "/r" if action == "restart" else "/s", "/f", "/t", "0"], creationflags=0x08000000)
            elif OS == "Darwin": subprocess.Popen(["osascript", "-e", 'tell application "System Events" to ' + ("restart" if action == "restart" else "shut down")])
            else: subprocess.Popen(["systemctl", "reboot" if action == "restart" else "poweroff"])
        except Exception: log("flatline power command failed:\n" + traceback.format_exc())

def start_flatline(action="shutdown"):
    """action: restart (LOAD LAST CHECKPOINT) / shutdown (EXIT TO MAIN MENU) / show (CONTINUE: just the screen)."""
    if FLAT["active"]: return
    FLAT.update(active=True, action=action)
    FLAT["timer"] = threading.Timer(FLAT_SECONDS if action != "show" else 14.0, lambda: _flat_execute(action)); FLAT["timer"].daemon = True; FLAT["timer"].start()
    if BRIDGE is not None: BRIDGE.flatline.emit(action)
    log("FLATLINE started: " + action)

def flatline_abort():
    if not FLAT["active"]: return False
    FLAT["active"] = False
    if FLAT["timer"]: FLAT["timer"].cancel()
    if BRIDGE is not None: BRIDGE.flat_hide.emit()
    log("FLATLINE aborted"); return True

def paste_to_user(text):
    _to_user_window(); paste(str(text))

def type_slow(text, interval=0.012):
    """Types like a person (visible, letter by letter) into the window you were using."""
    _to_user_window(); time.sleep(0.3)
    for chunk in re.findall(r"[\x20-\x7e]+|\n|[^\x20-\x7e\n]+", str(text)):
        if STOP.is_set(): return
        if chunk == "\n": pyautogui.press("enter")
        elif chunk.isascii(): pyautogui.write(chunk, interval=interval)
        else: paste(chunk)

def _send_unicode(text):
    """Types text as Unicode keystrokes (SendInput KEYEVENTF_UNICODE): works on ANY keyboard layout (AZERTY, QWERTZ...) and any script."""
    import ctypes
    from ctypes import wintypes
    class KI(ctypes.Structure): _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]
    class MI(ctypes.Structure): _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]
    class U(ctypes.Union): _fields_ = [("ki", KI), ("mi", MI)]
    class INPUT(ctypes.Structure): _fields_ = [("type", wintypes.DWORD), ("u", U)]
    send = ctypes.windll.user32.SendInput
    def key(vk=0, scan=0, flags=0):
        i = INPUT(type=1); i.u.ki = KI(vk, scan, flags, 0, 0); return i
    seq = []
    for ch in text:
        if ch == "\n": seq += [key(0x0D), key(0x0D, flags=2)]; continue          # Enter as a real key (new paragraph)
        if ch == "\r": continue
        if ch == "\t": seq += [key(0x09), key(0x09, flags=2)]; continue
        b = ch.encode("utf-16-le")
        for k in range(0, len(b), 2):                                           # emoji etc. = two UTF-16 units
            u = int.from_bytes(b[k:k + 2], "little"); seq += [key(scan=u, flags=4), key(scan=u, flags=4 | 2)]
    arr = (INPUT * len(seq))(*seq)
    send(len(seq), arr, ctypes.sizeof(INPUT))

def clip_set(text):
    """Put text on the clipboard and make sure it's really there (another app can briefly lock the clipboard: retry)."""
    for _ in range(8):
        try:
            pyperclip.copy(text)
            if pyperclip.paste() == text: return True
        except Exception as e:
            log(f"clipboard busy: {e}")
        time.sleep(0.15)
    log("clipboard: couldn't set it after 8 tries")
    return False

def type_into(hwnd, text, mode="type", progress=None, interval=0.012):
    """Types (or pastes) text into ONE specific window. If you click somewhere else she pauses until you're back in it
       (up to a minute), so she never types into the wrong app. Returns 'done', 'stopped' or 'lost'."""
    if OS != "Windows":
        paste(text) if mode == "paste" else pyautogui.write(text, interval=interval); return "done"
    if hwnd: _bring_front(hwnd); time.sleep(0.4)
    def on_target():
        if not hwnd: return True
        h, _, _ = _fg(); return h == hwnd
    def wait_target(rest):
        """Not in the document: wait up to a minute for you to click back. Returns None (carry on), 'stopped' or 'lost'."""
        if on_target(): return None
        if progress: progress("paused: click back into your document and I'll carry on")
        t0 = time.time()
        while not on_target():
            if STOP.is_set(): clip_set(rest); return "stopped"
            if time.time() - t0 > 60: clip_set(rest); return "lost"
            time.sleep(0.3)
        time.sleep(0.4); return None
    if mode == "paste":
        r = wait_target(text)
        if r: return r
        paste(text); return "done"
    words = re.findall(r"\S+\s*|\s+", text); total = max(1, len(text.split())); done_w = 0; last_note = 0
    for i, w in enumerate(words):
        if STOP.is_set(): clip_set("".join(words[i:])); return "stopped"
        r = wait_target("".join(words[i:]))
        if r: return r
        _send_unicode(w); time.sleep(interval * len(w))
        if w.strip():
            done_w += 1
            if progress and done_w - last_note >= 60: last_note = done_w; progress(f"typing... {done_w}/{total} words")
    return "done"

def deep(topic): return MD.deep_research(topic)
TOOLS["research"] = deep

MD.init(chat=lambda m, o=None: ollama_chat(TEXT_MODEL, m, opts=o), open_url=open_url, open_app=open_app, spotify=spotify, youtube=youtube, yt_lookup=_yt_lookup,
        type_slow=type_slow, paste=paste_to_user, start_menu_find=_start_menu_find, events=EVENTS, log=log, extras=EX,
        list_windows=lambda: list_windows(), exe_of=lambda h: AP._exe_of(h), bring_front=lambda h: _bring_front(h), fg=lambda: _fg(),
        last_win=lambda: LAST_WIN["hwnd"], copy=lambda t: clip_set(t), stop=STOP, type_into=lambda h, t, m, p=None: type_into(h, t, m, p))
_brain = lambda m, o=None: ollama_chat(TEXT_MODEL, m, opts=o)
I18N.init(chat=_brain, log=log)
SPA.init(open_app=lambda n: open_app(n), log=log)
SL.init(log=log, chat=lambda m, o=None: ollama_chat(TEXT_MODEL, m, opts=o), ap_parse=lambda t: AP.parse(t),
        autopilot=lambda cmds, label: AP.start(cmds, label), ap_state=lambda: AP.status())       # TikTok stream mode
MU.init(spotify_client=lambda: spotify_client(), yt_lookup=_yt_lookup, open_url=open_url, open_app=open_app, chat=_brain, log=log)
AP.init(log=log, events=EVENTS, chat=_brain, bring_front=lambda h: _bring_front(h), list_windows=lambda: list_windows(), launch_minecraft=lambda: MD._minecraft("java"),
        tray_msg=lambda m: BRIDGE.tray_msg.emit(m) if BRIDGE is not None else None,
        takeover_ui=lambda on: BRIDGE.takeover.emit(bool(on)) if BRIDGE is not None else None)

def _set_mode_tool(mode="off"):
    m = MD.MODE_WORDS.get(str(mode).lower().replace(" mode", "").strip(), "off" if str(mode).lower() in ("off", "normal", "none", "default") else None)
    if m is None: return f"unknown mode {mode}"
    apply_setting("mode", m); return f"{m} mode on" if m != "off" else "modes off"
TOOLS["music"] = lambda request="", service=None: MD.music_play(request, (service or "").lower() or None)
TOOLS["set_mode"] = _set_mode_tool
TOOLS["autopilot"] = lambda request="": AP.handle(request, I18N.name())["say"]

LAST_ACTIVITY = time.time()
WIN_VISIBLE = [False]

def _clip_notify(msg, path=None):
    """Tell the screen (and the tray bubble) when a clip is saved or fails."""
    EVENTS.append({"type": "act", "text": "// " + msg, "bad": msg.startswith("clip failed")})
    try:
        if OS == "Windows":
            import winsound; threading.Thread(target=lambda: winsound.Beep(1320 if "saved" in msg else 440, 140), daemon=True).start()
    except Exception: pass
    if BRIDGE is not None: BRIDGE.tray_msg.emit(msg)

CLIP = CL.Clipper(log=log, notify=_clip_notify)
CLIP.quality = MD.S.get("clip_quality", "normal"); CLIP.audio_on = bool(MD.S.get("clip_audio", True))

def clip_now(reason="voice"):
    if OS == "Windows":
        try:
            import winsound; threading.Thread(target=lambda: winsound.Beep(988, 90), daemon=True).start()     # instant "I heard you" blip
        except Exception: pass
    return CLIP.save(reason)

CLIP_RX = re.compile(r"^(?:please )?(?:(?:clip|klip|click|clipped|clips)(?: (?:that|it|this))?|save (?:a |the )?clip|clip the last (?:30 )?(?:seconds?|half a minute))(?: please)?$")
def clip_match(text):
    t = re.sub(r"[^a-z ]", " ", text.lower()); t = re.sub(r"\s+", " ", t).strip()
    return bool(t) and len(t.split()) <= 6 and bool(CLIP_RX.match(t))


def apply_setting(key, value):
    global WAKE_ON
    MD.setv(key, value)
    if key == "mode":
        MD.PENDING.clear()
        if value == "research": MD.PENDING["kind"] = "research_subject"
    if key == "clip":
        (CLIP.start if value else CLIP.stop)()
    if key in ("clip_quality", "clip_audio"): CLIP.configure(quality=MD.S.get("clip_quality"), audio=MD.S.get("clip_audio"))
    if key == "voice": WAKE_ON = bool(value); EVENTS.append({"type": "voice", "on": bool(value)}); log("microphone setting: " + ("ON" if value else "OFF"))
    if key == "scale" and BRIDGE is not None: BRIDGE.scale.emit(float(value))
    if key == "language": on_language_change()
    return MD.S

def on_language_change():
    """New language: reload the speech models (English-only .en models vs multilingual) and translate her fixed lines."""
    global _whisper, _wake_model, TEXT_MODEL
    _whisper = None; _wake_model = None
    log("language: " + I18N.name())
    EVENTS.append({"type": "act", "text": "// language: " + I18N.name(), "bad": False})
    I18N.prewarm(FIXED_LINES)
    def reload():
        try: _get_whisper()
        except Exception: log("speech model reload failed:\n" + traceback.format_exc())
    threading.Thread(target=reload, daemon=True).start()

# ---------------- agent turn ----------------
ALIASES = {
    "request": ["query", "text", "song", "what", "q"], "mode": ["name", "value"], "service": ["app", "platform", "on"],
    "name": ["path", "file", "filename", "file_name", "filepath", "title"], "instruction": ["what", "task", "request", "fix", "change", "edit", "changes"],
    "content": ["text", "code", "body", "data"], "about": ["description", "prompt", "topic", "details", "purpose"], "folder": ["directory", "location", "dir", "where", "path"],
    "topic": ["query", "subject", "about", "q", "search", "name"], "minutes": ["mins", "min", "time", "in_minutes", "delay", "duration"], "text": ["reason", "message", "task", "what", "content", "query"],
    "find": ["old", "search", "from", "target"], "replace": ["new", "with", "to"], "question": ["query", "q", "ask"], "fact": ["text", "info", "memory", "note"],
}

def exec_action(a):
    """Run one tool call safely. Returns (tool, result)."""
    import inspect
    tool, args = a.get("tool"), a.get("args", {}) or {}
    fn = TOOLS.get(tool)
    if fn:
        params = list(inspect.signature(fn).parameters)
        if isinstance(args, str):
            try: args = json.loads(args)
            except Exception: args = {params[0]: args} if params else {}
        if not isinstance(args, dict): args = {}
        for p in params:                                     # small models name arguments creatively: map them back
            if p not in args:
                for alt in ALIASES.get(p, []):
                    if alt in args and alt not in params: args[p] = args.pop(alt); break
        args = {k: v for k, v in args.items() if k in params}
    try:
        res = fn(**args) if fn else f"unknown tool {tool}"
    except pyautogui.FailSafeException:
        res = "failsafe triggered"; STOP.set()
    except Exception as e:
        res = f"error: {e}"; log(f"tool {tool} failed:\n" + traceback.format_exc())
    return tool, res

def _run_actions_bg(actions):
    for a in actions:
        if STOP.is_set():
            EVENTS.append({"type": "act", "text": "// flatlined by user", "bad": True}); break
        tool, res = exec_action(a)
        EVENTS.append({"type": "act", "text": f"// {tool}: {str(res)[:140]}", "bad": bool(re.search(r"error|refused|couldn't|failsafe", str(res)))})

# ---------------- speed: things that don't need the model at all ----------------
import random as _rnd
GREET_LINES = ["Hey, choom. What's the biz?", "Yo! Wake the hell up, samurai. What do you need?", "Hah-hah! There you are. What's up?", "Right here, baby. What do you need?"]
THX_LINES = ["Anytime, choom.", "Preem. Always.", "Hah-hah! Don't mention it.", "You're welcome, delta."]
FIXED_LINES = GREET_LINES + THX_LINES + list(MD.MODE_LINES.values()) + [          # translated once into her language and cached
    "On it.", "Searching.", "Cueing it up, choom.", "Done.", "Next.", "Back we go.", "Louder.", "Quieter.", "Muted.", "Opening your clips, choom.", "On it, choom. Typing it into the search box.",
    "Typing it in for you, choom.", "Aborted, choom. Still alive.", "Fine, dropped it, choom.", "Bedrock or Java, choom?", "Minecraft! Bedrock or Java, choom?", "Flatlining. Goodnight, choom.",
    "Okay, okay. Not flatlining anything. Crisis averted.", "Go on then, what else do you need?", "I'll call you when it's done, choom!", "Anything else to research, choom?",
    "Here's everything I dug up on {topic}:", "On it, choom. Opening your doc and typing.", "On it.", "Hands back on the wheel, choom. You've got control.",
    "Taking over. Sit back, choom: I'm going to beat Minecraft for you. Say 'stop' or press F8 to take back control.", "Getting food. Say 'stop' or press F8 to take back control.",
    "Opening Minecraft. Load into a world, press F3, and I'll take over the second you're in.", "Hah-hah. Say that again, choom?"]
SITES = {"youtube": "https://www.youtube.com", "google": "https://www.google.com", "gmail": "https://mail.google.com", "github": "https://github.com", "reddit": "https://www.reddit.com",
         "twitter": "https://x.com", "x": "https://x.com", "netflix": "https://www.netflix.com", "chatgpt": "https://chatgpt.com", "twitch": "https://www.twitch.tv",
         "maps": "https://maps.google.com", "google maps": "https://maps.google.com", "drive": "https://drive.google.com", "google drive": "https://drive.google.com",
         "google docs": "https://docs.google.com", "disney plus": "https://www.disneyplus.com", "amazon": "https://www.amazon.com", "wikipedia": "https://www.wikipedia.org"}
ACTION_RX = re.compile(r"\b(open|launch|start|play|pause|resume|stop|skip|next|previous|volume|mute|search|google|find|look|type|write|make|create|edit|fix|replace|undo|delete|remove|click|scroll|switch|focus|press|set|remind|timer|alarm|call|research|remember|forget|youtube|spotify|netflix|steam|essay|file|folder|desktop|screen|tab|window|app|video|song|music|show me|take me|go to|what am i|where am i|run|close|minimi[sz]e|maximi[sz]e|screenshot|save|copy|paste|download|install|use)\b", re.I)

def fast_route(text):
    """Instant answers/actions for common requests (no AI call). Returns (say, mood, background_fn or None) or None."""
    s = text.strip(); low = s.lower().strip(" .!?,")
    if re.match(r"^(?:hey|hi|hello|yo|sup|hiya|howdy|what'?s up|wassup)(?:\s+capri)?$", low): return _rnd.choice(GREET_LINES), "greet", None
    if re.match(r"^(?:thanks|thank you|thx|ty|cheers|nice one|good job|well done)(?:\s+capri)?$", low): return _rnd.choice(THX_LINES), "hyped", None
    if re.match(r"^(?:what'?s|what is) the time(?: now)?$|^what time is it(?: now)?$|^(?:got )?the time$|^time$", low): return time.strftime("It's %I:%M %p, choom.").replace("It's 0", "It's "), "idle", None
    if re.match(r"^(?:what'?s|what is) (?:today'?s |the )?date$|^what day is it(?: today)?$", low): return time.strftime("It's %A, %d %B."), "idle", None
    for rx, key, n, line in ((r"^(?:pause|resume|continue|unpause)(?: the)?(?: music| song| video| it)?$", "playpause", 1, "Done."), (r"^(?:next|skip)(?: the)?(?: song| track| one)?$", "next", 1, "Next."),
                             (r"^(?:previous|go back|last)(?: song| track)?$", "prev", 1, "Back we go."), (r"^(?:volume up|turn it up|louder|turn (?:the )?volume up)$", "volumeup", 6, "Louder."),
                             (r"^(?:volume down|turn it down|quieter|turn (?:the )?volume down)$", "volumedown", 6, "Quieter."), (r"^mute(?: it| the sound)?$", "mute", 1, "Muted.")):
        if re.match(rx, low): return line, "working", (lambda k=key, c=n: [media(k) for _ in range(c)][-1])
    if clip_match(low): return clip_now("typed"), "hyped", None
    if re.match(r"^(?:please )?(?:show|open) (?:me )?(?:my )?(?:capri )?clips?(?: folder)?$", low): return "Opening your clips, choom.", "hyped", (lambda: "clips folder: " + CLIP.open_folder())
    m = re.match(r"^(?:please )?(?:open|launch|start|run)\s+(?:up\s+)?(.+)$", low)
    if m and not re.search(r"file|folder|document|\.\w{2,4}$|desktop|download|\bmy\b|mode", low):
        name = m.group(1).strip()
        return "On it.", "working", ((lambda u=SITES[name]: open_url(u)) if name in SITES else (lambda n=name: open_app(n)))
    m = re.match(r"^(?:google|search google for|search for|search)\s+(.+)$", s, re.I)
    if m and not re.search(r"\bhere\b|search bar|search box", s, re.I): return "Searching.", "working", (lambda q=m.group(1).strip(" ."): search(q))
    m = re.match(r"^(?:please )?(?:play|put on)\s+(.+)$", s, re.I)
    if m and MD.S["mode"] == "off":
        q, svc = MD.split_service(m.group(1))
        if svc in ("spotify", "apple music", "soundcloud", "youtube music", "youtube") or re.search(r"\bby\b", q, re.I) or MU.parse(q):
            return "Cueing it up, choom.", "hyped", (lambda q=q, svc=svc: MD.music_play(q, svc))
    return None

CHAT_SYSTEM = SYSTEM.split("You control the PC with tools")[0] + "Reply with plain spoken text only: 1-2 short sentences, no JSON, no asterisks, no emojis. Stay in character."
if "\n\nWHO YOU ARE" in SYSTEM: CHAT_SYSTEM += SYSTEM[SYSTEM.index("\n\nWHO YOU ARE"):]

def chat_reply(user_text, ctx_extra, send, finish):
    """Small talk: short prompt, plain text, streamed straight to the screen."""
    msgs = [{"role": "system", "content": CHAT_SYSTEM + ctx_extra}] + HISTORY[-7:]
    text = ""
    for piece in llm_stream(msgs, json_mode=False, chat=True):
        text += piece
        send({"t": "say", "text": text.strip()})
    out = text.strip()
    if out.startswith("{"): out = extract_say(out) or out
    out = re.sub(r"^(?:CAPRI|Capri)\s*[:>]\s*", "", out).strip().strip('"')
    out = re.sub(r"\*[^*]{1,40}\*", "", out).strip() or "Hah-hah. Say that again, choom?"
    finish(out, "idle")

TYPE_RE = re.compile(r"^\s*(?:hey capri[, ]*)?(?:please\s+)?(?:type|write out)\s+(?!of\b)(?:in\s+|out\s+)?(?:the following\s*:?\s*)?(.+?)\s*$", re.I)
SEARCH_HERE_RE = [re.compile(r"^\s*(?:hey capri[, ]*)?(?:please\s+)?(?:search|look)\s+(?:for\s+)?(.+?)\s+(?:here|in (?:the )?search (?:bar|box)|on (?:this|the) page)\s*$", re.I),
                  re.compile(r"^\s*(?:in|on) (?:the )?search (?:bar|box)\s*,?\s*(?:type|search|put|write)\s+(.+?)\s*$", re.I),
                  re.compile(r"^\s*(?:hey capri[, ]*)?(?:please\s+)?(?:type|put|write)\s+(.+?)\s+in(?:to)? (?:the )?search (?:bar|box)\s*$", re.I)]
RESEARCH_RE = re.compile(r"^\s*(?:hey capri[, ]*)?(?:please\s+)?(?:deep\s+)?(?:research|look up|look into|find out about|learn about)\s+(.+?)\s*$", re.I)

def _unquote(t): return t.strip().strip("\"'\u201c\u201d").strip()

def _mood_pop_safe(feeling):
    """Her reaction-image pop-up opens a browser tab, which STEALS FOCUS. Never do it while she's typing homework, playing a game,
       streaming, or right after she did something on your PC; only during plain chat."""
    def go():
        time.sleep(4)                                                              # anything she just started has time to begin
        if MD.HW.get("busy") or AP.STATE.get("active") or SL.STATE.get("live") or STOP.is_set(): return
        r = EX.mood_pop(feeling)
        if r: EVENTS.append({"type": "act", "text": "// mood: " + r, "bad": False})
    threading.Thread(target=go, daemon=True).start()

def run_turn_stream(user_text, send):
    """Streams her words to the UI as they are generated; tools run in the background so replies never wait for them."""
    if MD.HW.get("busy") and AP.stop_phrase(user_text):              # "stop" while she's typing your essay
        STOP.set(); HISTORY.append({"role": "user", "content": user_text})
        say = I18N.tr("Stopped typing, choom. The rest is on your clipboard if you want it.")
        HISTORY.append({"role": "assistant", "content": say}); send({"t": "say", "text": say}); send({"t": "done", "say": say, "mood": "idle", "feeling": "neutral", "hangup": False})
        return
    STOP.clear()
    HISTORY.append({"role": "user", "content": user_text})
    global LAST_ACTIVITY
    LAST_ACTIVITY = time.time()
    def canned(say, mood="hyped", feeling="neutral", hangup=False):
        if len(say) < 300: say = I18N.tr(say)
        HISTORY.append({"role": "assistant", "content": say}); send({"t": "say", "text": say}); send({"t": "done", "say": say, "mood": mood, "feeling": feeling, "hangup": hangup})
    def prog(m): send({"t": "act", "text": "// " + str(m)[:80]})
    threading.Thread(target=EX.learn_from, args=(user_text,), daemon=True).start()          # she remembers what you tell her
    # ---- things that must just work, handled without asking the model ----
    if FLAT["active"] and CANCEL_RX.search(user_text):
        flatline_abort(); return canned("Aborted, choom. Still alive.", "hyped")
    pw = power_intent(user_text)
    if pw == "show":                                            # just the flatline screen (CONTINUE), nothing happens to the PC
        start_flatline("show"); return canned("Flatlining you. Don't worry, it's just for show.", "alert")
    if pw and MD.PENDING.get("kind") != "power_confirm":
        MD.PENDING.clear(); MD.PENDING.update(kind="power_confirm", action=pw)
        return canned(f"You sure, choom? I'll flatline the PC and then {'restart' if pw == 'restart' else 'power it off'}. Anything unsaved is gone. Say yes.", "alert")
    sl = SL.command(user_text)                                  # "go live on tiktok as @name" / "start stream mode" / "stop stream mode"
    if sl: return canned(sl, "hyped")
    if AP.wants_autoplay(user_text, MD.S["mode"]) or ((AP.STATE["active"] or AP.STATE["waiting"]) and AP.stop_phrase(user_text)):
        r = AP.handle(user_text, I18N.name())                   # gaming autopilot: she takes over Minecraft
        if r: return canned(r["say"], r.get("mood", "hyped"))
    lc = I18N.language_command(user_text)
    if lc:
        apply_setting("language", lc)
        return canned(f"Done, choom. I'll speak {I18N.name(lc)} from now on.", "hyped")
    r = MD.handle_pending(user_text, prog)                      # answers to her questions (research subject, bedrock/java, "is that all?")
    if r:
        canned(r["say"], r.get("mood", "idle"), hangup=r.get("hangup", False))
        if r.get("power"): start_flatline(r["power"])
        return
    r = MD.handle_mode_text(user_text)                          # "gaming mode", "research mode"...
    if r: return canned(r["say"], r.get("mood", "idle"))
    n0 = len(EX.REMS); r = EX.handle_reminder_text(user_text)
    if r:
        if len(EX.REMS) > n0 and IN_CALL:
            MD.PENDING.clear(); MD.PENDING["kind"] = "timer_confirm"; last = EX.REMS[-1]
            r = (f"Timer set for {last['label']}." if last["kind"] == "timer" else f"Got it, I'll remind you to {last['text']} in {last['label']}.") + " Is that all, choom?"
        return canned(r)
    r = EX.handle_memory_text(user_text)
    if r: return canned(r)
    r = MD.route(user_text)                                     # mode commands: play X / launch X / write an essay (always the DEFAULT app unless you name another)
    if r:
        later = r.get("later"); canned(r["say"], r.get("mood", "hyped"))
        if later: threading.Thread(target=lambda: EVENTS.append({"type": "act", "text": "// " + str(later())[:140], "bad": False}), daemon=True).start()
        return
    for rx in SEARCH_HERE_RE:
        m = rx.match(user_text)
        if m:
            threading.Thread(target=lambda t=_unquote(m.group(1)): EVENTS.append({"type": "act", "text": "// search_here: " + str(search_here(t))[:120], "bad": False}), daemon=True).start()
            return canned("On it, choom. Typing it into the search box.")
    m = TYPE_RE.match(user_text)
    if m and not re.search(r"\bessay\b", user_text, re.I):
        threading.Thread(target=lambda t=_unquote(m.group(1)): EVENTS.append({"type": "act", "text": "// type_here: " + str(type_here(t))[:120], "bad": False}), daemon=True).start()
        return canned("Typing it in for you, choom.")
    m = RESEARCH_RE.match(user_text)
    if m:
        send({"t": "act", "text": "// researching " + m.group(1)[:40] + "..."})
        return canned(MD.deep_research(m.group(1), prog), "hyped")
    now = time.strftime("%A %d %B %Y, %H:%M")
    ctx_extra = f"\n\nCurrent local date and time: {now}. You always know the time and date, so answer those yourself with no tool." + pc_line()
    if MD.S["mode"] != "off": ctx_extra += f"\nCurrent mode: {MD.S['mode']} mode."
    if AP.STATE["active"]: ctx_extra += f"\nYou are currently playing Minecraft for the user (autopilot: {AP.STATE['command']})."
    ctx_extra += I18N.reply_rule()
    mem = EX.memory_context(user_text)
    if mem: ctx_extra += "\n\n" + mem
    msgs = [{"role": "system", "content": SYSTEM + ctx_extra}] + HISTORY[-8:]
    sw = re.match(r"^\s*(?:hey\s+)?(?:capri[, ]+)?(?:use|switch to|change to|go to)\s+(?:the\s+)?(.+?)(?:\s+(?:ai|model|brain))?\s*[.!?]?\s*$", user_text, re.I)
    if sw:
        hit = PV.set_active(sw.group(1))
        if hit: return canned(f"Done, choom. My brain is {hit} now.")
    fr = fast_route(user_text)
    if fr:
        fsay, fmood, fbg = fr; canned(fsay, fmood)
        if fbg: threading.Thread(target=lambda: EVENTS.append({"type": "act", "text": "// " + str(fbg())[:140], "bad": False}), daemon=True).start()
        return
    if I18N.is_en() and not ACTION_RX.search(user_text) and len(user_text) <= 200:      # other languages always get the full tool prompt (the keyword check is English)
        def finish(say, mood):
            HISTORY.append({"role": "assistant", "content": say})
            feeling = EX.detect_feeling(user_text, None) or "neutral"
            mood = "alert" if feeling == "angry" else ("hyped" if feeling == "happy" else mood)
            send({"t": "done", "say": say, "mood": mood, "feeling": feeling, "hangup": False})
            if feeling != "neutral":
                _mood_pop_safe(feeling)
        return chat_reply(user_text, ctx_extra, send, finish)
    raw, last = "", ""
    for piece in llm_stream(msgs):
        raw += piece
        t = extract_say(raw)
        if t and t != last:
            last = t; send({"t": "say", "text": t})
    try:
        data = json.loads(raw)
    except Exception:
        try:
            data = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))      # some APIs wrap JSON in ``` fences
        except Exception:
            data = {"say": extract_say(raw) or raw, "mood": "idle", "actions": []}
    say, mood = data.get("say", "") or last, data.get("mood", "idle")
    actions = data.get("actions") or []
    bg = []
    for a in actions:
        if isinstance(a, dict) and a.get("tool") in SYNC_TOOLS:      # her answer depends on the result, so wait for this one
            send({"t": "act", "text": "// " + ("looking at your screen..." if a.get("tool") == "look" else a.get("tool", "") + "...")})
            _, res = exec_action(a); say = (say + " " + str(res)).strip()
            mood = "alert" if a.get("tool") == "look" or re.search(r"couldn't|error|can't|didn't|too big", str(res)) else "hyped"
        elif isinstance(a, dict):
            bg.append(a)
    HISTORY.append({"role": "assistant", "content": say})
    feeling = EX.detect_feeling(user_text, data.get("feeling")) or "neutral"
    if feeling == "angry": mood = "alert"
    elif feeling == "happy" and mood == "idle": mood = "hyped"
    send({"t": "done", "say": say, "mood": mood, "feeling": feeling})
    if feeling != "neutral" and not actions:
        _mood_pop_safe(feeling)
    if bg:
        threading.Thread(target=_run_actions_bg, args=(bg,), daemon=True).start()

VOICE = os.environ.get("CAPRI_VOICE", "en_US-kristin-medium")   # any Piper voice name
VOICE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voices")

VOICES = ["en_US-amy-medium", "en_US-kristin-medium", "en_US-hfc_female-medium", "en_GB-alba-medium",
          "en_GB-jenny_dioco-medium", "en_GB-southern_english_female-low", "en_US-lessac-medium"]

VOICEBOX = os.environ.get("CAPRI_VOICEBOX", "http://127.0.0.1:17493")       # Voicebox desktop app (voicebox.sh): local voice-clone studio
VOICEBOX_PROFILE = os.environ.get("CAPRI_VOICEBOX_PROFILE", "capri")         # the voice profile NAME she speaks with
_vb = {"id": None, "checked": 0.0}

def _voicebox_profile():
    """The id of your 'capri' profile in Voicebox (or the only profile you have). None if Voicebox isn't running."""
    if _vb["id"] and time.time() - _vb["checked"] < 300: return _vb["id"]
    if time.time() - _vb["checked"] < 20 and not _vb["id"]: return None          # not running: don't ask on every line
    _vb["checked"] = time.time(); _vb["id"] = None
    try:
        r = requests.get(VOICEBOX + "/profiles", timeout=1.5); r.raise_for_status(); data = r.json()
        profs = data if isinstance(data, list) else (data.get("profiles") or data.get("items") or [])
        want = VOICEBOX_PROFILE.lower()
        pick = next((p for p in profs if str(p.get("name", "")).lower() == want), None) or (profs[0] if len(profs) == 1 else None)
        if pick: _vb["id"] = pick.get("id") or pick.get("profile_id")
        if _vb["id"]: log(f"voice: Voicebox profile '{pick.get('name')}'")
    except Exception: pass
    return _vb["id"]

def _voicebox_tts(text):
    pid = _voicebox_profile()
    if not pid: return None
    body = {"text": text, "profile_id": pid, "language": I18N.code()}
    eng = MD.S.get("voicebox_engine")
    if eng: body["engine"] = eng
    r = requests.post(VOICEBOX + "/generate", json=body, timeout=120); r.raise_for_status()
    ct = r.headers.get("content-type", "")
    if "audio" in ct: return r.content
    j = r.json()
    for k in ("audio", "audio_base64", "wav", "data"):
        if isinstance(j.get(k), str) and len(j[k]) > 200: return base64.b64decode(j[k].split(",")[-1])
    gid = j.get("id") or j.get("generation_id")
    if gid:
        a = requests.get(f"{VOICEBOX}/audio/{gid}", timeout=60); a.raise_for_status(); return a.content
    p = j.get("audio_path")
    if p and os.path.exists(p): return open(p, "rb").read()
    raise RuntimeError("Voicebox answered without audio")

VOICE_API_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voice_api.json")
def voice_api_cfg():
    """voice_api.json (copy voice_api.example.json): a cloud text-to-speech voice. Keys can be in the file or an env variable."""
    try:
        with open(VOICE_API_FILE, encoding="utf-8") as f: c = json.load(f)
        c = c.get(c.get("active", ""), c) if isinstance(c.get(c.get("active", "")), dict) else c
        key = c.get("api_key") or ""
        if not key or "PUT_YOUR" in key: key = os.environ.get(c.get("api_key_env") or "", "")
        if not key: return None
        return dict(c, api_key=key)
    except Exception: return None

def api_tts(text):
    """Cloud voice: OpenAI-compatible /audio/speech (OpenAI, Groq, any compatible server) or ElevenLabs. Returns audio bytes."""
    c = voice_api_cfg()
    if not c: raise RuntimeError("API voice isn't set up: copy voice_api.example.json to voice_api.json and add your key")
    if c.get("type") == "elevenlabs":
        vid = c.get("voice_id") or "21m00Tcm4TlvDq8ikWAM"
        r = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{vid}?output_format=mp3_44100_128",
                          headers={"xi-api-key": c["api_key"], "Content-Type": "application/json"},
                          json={"text": text, "model_id": c.get("model") or "eleven_flash_v2_5"}, timeout=60)
    else:
        base = (c.get("base_url") or "https://api.openai.com/v1").rstrip("/")
        body = {"model": c.get("model") or "gpt-4o-mini-tts", "voice": c.get("voice") or "nova", "input": text, "response_format": "mp3"}
        if c.get("instructions"): body["instructions"] = c["instructions"]
        r = requests.post(base + "/audio/speech", headers={"Authorization": "Bearer " + c["api_key"]}, json=body, timeout=60)
    if r.status_code >= 400: raise RuntimeError(f"API voice error {r.status_code}: {r.text[:200]}")
    return r.content

def tts(text, voice=None, engine=None):
    """Her spoken voice -> audio bytes. engine: 'voicebox' | 'piper' | 'api' (None = Voicebox if it's open, else Piper).
       The default BEEPS voice is made in the browser (static/capri_voice.js), so it never comes here."""
    engine = engine or MD.S.get("voice_engine")
    if engine == "api": return api_tts(text)
    if engine == "voicebox":
        wav = _voicebox_tts(text)
        if not wav: raise RuntimeError("Voicebox isn't running (open the Voicebox app and make a 'capri' profile)")
        return wav
    if engine != "piper":
        try:
            wav = _voicebox_tts(text)
            if wav: return wav
        except Exception as e:
            log(f"Voicebox voice failed, using Piper: {e}")
    os.makedirs(VOICE_DIR, exist_ok=True)
    custom = os.path.join(VOICE_DIR, "capri.onnx")
    if os.path.exists(custom):                                   # your own trained voice model (see README)
        out = os.path.join(VOICE_DIR, "_out.wav")
        subprocess.run([sys.executable, "-m", "piper", "-m", custom, "-f", out], input=text.encode(), check=True, timeout=90)
        return open(out, "rb").read()
    if not I18N.is_en():                                         # a Piper voice that speaks her language (first one that downloads)
        cands = I18N.piper_voices()
        if not cands: raise RuntimeError(f"no Piper voice for {I18N.name()}: text only")
        voice = None
        for v in cands:
            if os.path.exists(os.path.join(VOICE_DIR, v + ".onnx")): voice = v; break
            try:
                subprocess.run([sys.executable, "-m", "piper.download_voices", v, "--data-dir", VOICE_DIR], check=True, timeout=300); voice = v; break
            except Exception: log(f"piper voice {v} unavailable")
        if not voice: raise RuntimeError(f"couldn't get a Piper voice for {I18N.name()}")
    else:
        voice = voice if voice in VOICES else VOICE
    if not os.path.exists(os.path.join(VOICE_DIR, voice + ".onnx")):
        subprocess.run([sys.executable, "-m", "piper.download_voices", voice, "--data-dir", VOICE_DIR], check=True)
    out = os.path.join(VOICE_DIR, "_out.wav")
    subprocess.run([sys.executable, "-m", "piper", "-m", voice, "--data-dir", VOICE_DIR, "-f", out],
                   input=text.encode(), check=True, timeout=60)
    return open(out, "rb").read()

STT_BEAM = int(os.environ.get("CAPRI_STT_BEAM", "1"))      # 1 = fastest; 3-5 = a bit more accurate for heavy accents
STT_HINT = "Capri, choom. Open Spotify, play a song on YouTube, open Steam, Discord, fix my file."
_whisper = None
_wlock = threading.Lock()
def _get_whisper():
    global _whisper
    with _wlock:
        if _whisper is None:
            from faster_whisper import WhisperModel
            name = os.environ.get("CAPRI_STT")
            try:
                import ctranslate2
                gpu = ctranslate2.get_cuda_device_count() > 0
            except Exception:
                gpu = False
            if gpu:                                                       # a GPU can run the big accurate model fast: much better with accents
                try:
                    _n = I18N.whisper_model(name or "medium.en")
                    _whisper = WhisperModel(_n, device="cuda", compute_type="float16"); log("speech model on GPU: " + _n)
                except Exception:
                    log("GPU speech model failed, using CPU:\n" + traceback.format_exc())
            if _whisper is None:
                _n = I18N.whisper_model(name or "small.en")
                _whisper = WhisperModel(_n, compute_type="int8", cpu_threads=min(8, os.cpu_count() or 4)); log("speech model on CPU: " + _n)
    return _whisper

def stt_pcm(raw):
    """Speech-to-text from raw 16 kHz mono float32 samples (decoded in the browser, so no ffmpeg/PyAV involved)."""
    import numpy as np
    audio = np.frombuffer(raw, dtype=np.float32).copy()
    if audio.size < 1600: return ""
    peak = float(np.abs(audio).max())
    if 0.005 < peak < 0.6: audio *= 0.85 / peak          # quiet mic? bring it up so the model hears it
    m = _get_whisper()
    try:
        segs, _ = m.transcribe(audio, language=I18N.whisper_lang(), beam_size=STT_BEAM, vad_filter=True, vad_parameters={"min_silence_duration_ms": 500, "speech_pad_ms": 300},
                               condition_on_previous_text=False, initial_prompt=I18N.stt_hint(STT_HINT))
        return " ".join(x.text.strip() for x in segs).strip()
    except Exception:
        log("vad transcribe failed, retrying without vad:\n" + traceback.format_exc())
        segs, _ = m.transcribe(audio, language=I18N.whisper_lang(), beam_size=STT_BEAM, vad_filter=False, condition_on_previous_text=False, initial_prompt=I18N.stt_hint(STT_HINT))
        return " ".join(x.text.strip() for x in segs).strip()

def stt(audio_bytes):
    """Local speech-to-text (faster-whisper). No cloud."""
    segs, _ = _get_whisper().transcribe(io.BytesIO(audio_bytes), language=I18N.whisper_lang(), beam_size=1, vad_filter=True, condition_on_previous_text=False)
    return " ".join(x.text.strip() for x in segs).strip()

# ---------------- "Hey Capri" wake word (always listening, fully local) ----------------
IN_CALL = False            # set by the UI; the listener sleeps during calls
WAKE_ON = MD.S.get("voice", True)             # toggled from the tray menu
WAKE_PAUSE_UNTIL = 0.0
_wake_model = None
_wake_lock = threading.Lock()
WAKE_VARIANTS = {"capri", "kapri", "capree", "caprie", "capry", "cappri", "caprey", "capre", "cabri", "kaprie", "kapry", "copri", "capi", "caprice", "capris", "capri's", "kabri", "kappri", "cabree", "gabri", "cafri", "kafri", "capee", "cobri", "copre", "kapre", "kaprie", "kapree"}

def _capri_token(c):
    c = c.strip("'").lower()
    return c in WAKE_VARIANTS or (len(c) >= 4 and difflib.SequenceMatcher(None, c, "capri").ratio() >= 0.7)

WAKE_PREFIX = {"hey", "hay", "hi", "call"}
def wake_match(text):
    """Only these wake her: 'Hey', 'Capri', 'Hey Capri', 'Call' (and 'Call Capri'). Her name is matched loosely because accents mishear it."""
    raw = re.sub(r"[\s,.!?¡¿。、！？]+", " ", text.lower()).strip()
    for nn in I18N.native_names():                                                  # 'Капри', 'カプリ'... (Whisper writes her name in your script)
        if nn in raw and len(raw.replace(nn, " ").split()) <= 1: return True
    t = re.sub(r"[^a-z' ]", " ", text.lower()); t = re.sub(r"\s+", " ", t).strip()
    if not t: return False
    if re.fullmatch(r"(?:(?:hey|hay|hi|call) ?)?[ck]a?p+ ?(?:pr|tr|r)(?:i|ee|ie|y|e)'?s?", t): return True      # 'capri', 'hey cap tree'
    words = t.split()
    if len(words) > 2: return False
    if MD.S.get("wake_mode") == "name" and not any(_capri_token(w) for w in words): return False       # NAME ONLY: ignores a bare "hey"/"call" (TV!)
    return all(w in WAKE_PREFIX or w in I18N.wake_prefixes() or _capri_token(w) for w in words)

def incoming_command(text):
    """While she's calling you: 'pick up' answers, 'hang up' declines."""
    t = re.sub(r"[^a-z ]", " ", text.lower())
    if re.search(r"\b(hang ?up|decline|reject|ignore|dismiss|cancel|go away)\b", t): return "decline"
    if re.search(r"\b(pick ?up|answer|accept|yes|yeah|yep|okay|ok|sure)\b", t): return "answer"
    return None

WAKE_STATUS = "starting"
LAST_HEARD = ""
MIC_LEVEL = 0.0
WAKE_CMD_RE = re.compile(r"\b(?:hey|hay|hi|call|cool)\s?(?:capri|kapri|capree|caprie|capry|cappri|caprey|capre|cabri|kaprie|kapry|copri|capi|cap+ ?(?:pr|tr|r)(?:i|ee|ie|y|e))'?s?\b[\s,.!?]*(.*)$", re.I)

def wake_command(text):
    """'hey capri play looping the rooms' -> 'play looping the rooms' (so she can act the moment she picks up)."""
    for nn in I18N.native_names():
        i = text.lower().find(nn)
        if i >= 0:
            cmd = text[i + len(nn):].strip(" ,.!?、。！？")
            return cmd if len(cmd) >= 2 else ""
    toks = list(re.finditer(r"[A-Za-z']+", text))
    for i, tk in enumerate(toks):
        if _capri_token(tk.group()):
            cmd = text[tk.end():].strip(" ,.!?")
            return cmd if len(cmd) >= 3 else ""
    return ""

def _wake_transcribe(audio):
    global _wake_model
    with _wake_lock:
        if _wake_model is None:
            from faster_whisper import WhisperModel
            _wake_model = WhisperModel(I18N.whisper_model(os.environ.get("CAPRI_WAKE_STT", "base.en")), compute_type="int8")
    segs, _ = _wake_model.transcribe(audio, language=I18N.whisper_lang(), beam_size=2, vad_filter=False, condition_on_previous_text=False,
                                     initial_prompt="Capri.")
    return " ".join(x.text.strip() for x in segs).strip()

def wake_loop():
    global WAKE_STATUS, LAST_HEARD, MIC_LEVEL, WAKE_PAUSE_UNTIL
    try:
        import numpy as np, queue
        try:
            import sounddevice as sd
        except ImportError:
            WAKE_STATUS = "installing mic driver"
            log("sounddevice missing, installing it")
            subprocess.run([sys.executable, "-m", "pip", "install", "sounddevice"], capture_output=True, timeout=240)
            import sounddevice as sd
    except Exception:
        WAKE_STATUS = "off: sounddevice missing"
        log("wake word disabled:\n" + traceback.format_exc()); return
    q = queue.Queue()
    def cb(indata, frames, t, status): q.put(indata[:, 0].copy())
    dev = os.environ.get("CAPRI_MIC"); dev = int(dev) if dev and dev.isdigit() else dev
    def open_stream():
        try:
            st = sd.InputStream(samplerate=16000, channels=1, dtype="float32", blocksize=1600, callback=cb, device=dev); st.start()
            log("microphone ON: " + str(sd.query_devices(dev if dev is not None else sd.default.device[0])["name"])); return st, ""
        except Exception as e:
            log("wake word: no microphone:\n" + traceback.format_exc() + "\ndevices:\n" + str(sd.query_devices())); return None, str(e)[:60]
    stream = None
    buf, speaking, last_voice, noise = [], False, 0.0, 0.004
    while True:
        if not WAKE_ON:                              # microphone completely OFF: the audio stream is CLOSED, nothing is captured at all
            if stream is not None:
                try: stream.stop(); stream.close()
                except Exception: pass
                stream = None; buf, speaking = [], False; log("microphone OFF (stream closed)")
            while not q.empty(): q.get_nowait()
            WAKE_STATUS = "off (microphone is OFF)"; MIC_LEVEL = 0.0; time.sleep(0.4); continue
        if stream is None:
            stream, err = open_stream()
            if stream is None: WAKE_STATUS = "off: no mic (" + err + ")"; time.sleep(3); continue
        try: chunk = q.get(timeout=0.5)
        except queue.Empty: continue
        now = time.time()
        if CALL_PHASE == "incoming": WAKE_STATUS = "listening: say 'pick up' or 'hang up'"
        elif IN_CALL: WAKE_STATUS = "paused during call"
        elif now < WAKE_PAUSE_UNTIL: WAKE_STATUS = "waking up"
        else: WAKE_STATUS = "listening"
        rms = float(np.sqrt(np.mean(chunk ** 2))); MIC_LEVEL = rms
        if not WAKE_STATUS.startswith("listening"):
            buf, speaking = [], False
            while q.qsize() > 20: q.get_nowait()
            continue
        thr = max(0.008, noise * 2.5 + 0.004)
        if rms > thr:
            if not speaking: speaking = True; buf = []
            last_voice = now; buf.append(chunk)
        elif speaking:
            buf.append(chunk)
            if now - last_voice > 0.7 or len(buf) > 80:
                audio = np.concatenate(buf); speaking = False; buf = []
                if 0.35 < len(audio) / 16000 < 8:
                    try:
                        text = _wake_transcribe(audio)
                        if text:
                            LAST_HEARD = text; log("heard: " + text)
                            if FLAT["active"]:
                                if CANCEL_RX.search(text): flatline_abort()
                            elif CALL_PHASE == "incoming":
                                cmd = incoming_command(text)
                                if cmd: EVENTS.append({"type": "cmd", "cmd": cmd}); WAKE_PAUSE_UNTIL = time.time() + 2
                            elif (AP.STATE["active"] or AP.STATE["waiting"]) and AP.stop_phrase(text):
                                AP.stop(); _clip_notify("Autopilot off: you have control")
                            elif wake_match(text):
                                trigger_wake(text)
                            elif clip_match(text):
                                _clip_notify(clip_now("voice"))
                    except Exception:
                        log("wake transcribe error:\n" + traceback.format_exc())
        else:
            noise = noise * 0.97 + rms * 0.03

def trigger_wake(text=""):
    global WAKE_PAUSE_UNTIL
    WAKE_PAUSE_UNTIL = time.time() + 20          # don't re-trigger while she's popping up
    EVENTS.append({"type": "wake", "text": text, "cmd": wake_command(text)})
    if BRIDGE is not None: BRIDGE.show.emit()    # pop up from the tray

# ---------------- desktop mate: she teleports onto your windows ----------------
MATE_ENABLED = (os.environ.get("CAPRI_MATE", "0") == "1" or "--mate" in sys.argv) and "--no-mate" not in sys.argv and not SAFE
MATE = {"visible": False, "hwnd": None, "off": 0.5, "kind": "stand", "next_tp": 0.0, "want": False, "pos": None}
CALL_PHASE = "idle"
MATE_W, MATE_H = 300, 500
MATE_ANCHOR = {"sit": (150, 354), "stand": (150, 454)}      # pixel inside her window that touches the perch point
DPR = 1.0
SCREEN = (0, 0, 1920, 1040)                                   # usable screen (x, y, w, h) in logical pixels, set by Qt

def _win_rect(hwnd):
    """Window frame rect in logical pixels, or None if it is gone / minimised / hidden."""
    import ctypes
    from ctypes import wintypes
    user32, dwm = ctypes.windll.user32, ctypes.windll.dwmapi
    if not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd): return None
    r = wintypes.RECT()
    if dwm.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(r), ctypes.sizeof(r)) != 0: user32.GetWindowRect(hwnd, ctypes.byref(r))
    return {"x": int(r.left / DPR), "y": int(r.top / DPR), "w": int((r.right - r.left) / DPR), "h": int((r.bottom - r.top) / DPR)}

def get_rect(hwnd):
    try: return _win_rect(hwnd) if OS == "Windows" else None
    except Exception: return None

def list_windows():
    """Top-level app windows, front to back (Windows only; elsewhere she just stands on the taskbar)."""
    if OS != "Windows": return []
    try:
        import ctypes
        from ctypes import wintypes
        user32, dwm = ctypes.windll.user32, ctypes.windll.dwmapi
        out = []
        skip_cls = {"Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Progman", "WorkerW", "Windows.UI.Core.CoreWindow", "ApplicationFrameInputSinkWindow", "XamlExplorerHostIslandWindow"}
        Proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def cb(hwnd, _):
            try:
                if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd): return True
                cloaked = ctypes.c_int(0); dwm.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), 4)
                if cloaked.value: return True
                pid = wintypes.DWORD(); user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value == os.getpid(): return True
                title = ctypes.create_unicode_buffer(256); user32.GetWindowTextW(hwnd, title, 256)
                cls = ctypes.create_unicode_buffer(80); user32.GetClassNameW(hwnd, cls, 80)
                if not title.value or cls.value in skip_cls: return True
                if user32.GetWindowLongW(hwnd, -20) & 0x80: return True          # tool windows
                r = _win_rect(hwnd)
                if r and r["w"] >= 250 and r["h"] >= 120: out.append({"hwnd": int(hwnd), "title": title.value, **r})
            except Exception: pass
            return True
        user32.EnumWindows(Proc(cb), 0)
        return out
    except Exception:
        log("list_windows failed:\n" + traceback.format_exc()); return []

def choose_perch(windows=None):
    """Pick where to teleport: the top edge of one of the front windows (she sits there), else the taskbar (she stands)."""
    import random
    sx, sy, sw, sh = SCREEN
    wins = list_windows() if windows is None else windows
    opts = []
    for w in wins[:8]:
        if w["hwnd"] == MATE["hwnd"]: continue
        if w["w"] >= sw - 30 and w["y"] <= sy + 5: continue                    # maximised: no free edge
        if w["y"] < sy + 270 or w["y"] > sy + sh - 80: continue                 # her head would leave the screen / she'd sit below the fold
        if w["x"] + w["w"] * 0.25 > sx + sw - 120: continue
        opts.append(w)
    if opts and random.random() < 0.85:
        w = random.choice(opts); off = random.uniform(0.2, 0.8)
        return {"kind": "sit", "hwnd": w["hwnd"], "off": off, "x": int(w["x"] + w["w"] * off), "y": int(w["y"])}
    return {"kind": "stand", "hwnd": None, "off": 0.0, "x": random.randint(sx + 220, sx + sw - 220), "y": sy + sh}

def roam_loop():
    """When she's idle she glitches to a new spot on your screen about once a minute (with a mind of her own)."""
    import random
    time.sleep(25)
    while True:
        time.sleep(random.uniform(50, 75))
        if BRIDGE is None or MATE_ENABLED or not MD.S.get("roam") or not WIN_VISIBLE[0] or IN_CALL or CALL_PHASE != "idle": continue
        if time.time() - LAST_ACTIVITY < 40: continue
        BRIDGE.roam.emit()

def timer_watch():
    last = -1
    while True:
        time.sleep(0.5)
        n = len(EX.REMS)
        if n != last and BRIDGE is not None: last = n; BRIDGE.timers.emit(n)

def mate_loop():
    import random
    time.sleep(3)
    while True:
        time.sleep(0.2)
        if BRIDGE is None or not MATE_ENABLED or not MATE["visible"]: continue
        now = time.time()
        if MATE["hwnd"]:                                                       # ride along when the window moves
            r = get_rect(MATE["hwnd"])
            if r is None: MATE["hwnd"] = None; MATE["want"] = True
            else:
                pos = (int(r["x"] + r["w"] * MATE["off"]), int(r["y"]))
                if pos != MATE["pos"]: MATE["pos"] = pos; BRIDGE.mate_move.emit(pos[0], pos[1])
        busy = IN_CALL or CALL_PHASE != "idle"
        if (MATE["want"] and not MATE.get("shown")) or ((MATE["want"] or now >= MATE["next_tp"]) and not busy):
            MATE["shown"] = True
            MATE["want"] = False; MATE["next_tp"] = now + random.uniform(45, 110)
            p = choose_perch()
            MATE.update(hwnd=p["hwnd"], off=p["off"], kind=p["kind"], pos=(p["x"], p["y"]))
            BRIDGE.mate_goto.emit(p["x"], p["y"], p["kind"])

# ---------------- http ----------------
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, body, ctype="application/json"):
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")             # always load her newest pages/scripts after an update (no stale cached menu)
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if self.path.startswith("/api/settings"):
            return self._send(200, json.dumps(MD.S).encode())
        if self.path.startswith("/api/keys"):
            return self._send(200, json.dumps(PV.keys_status()).encode())
        if self.path.startswith("/api/voicestatus"):
            c = voice_api_cfg()
            api = (c.get("type") == "elevenlabs" and "ElevenLabs" or (c.get("voice") or "OpenAI")) if c else ""
            return self._send(200, json.dumps({"engine": MD.S.get("voice_engine", "beeps"), "voicebox": bool(_voicebox_profile()), "api": api}).encode())
        if self.path.startswith("/api/timers"):
            return self._send(200, json.dumps({"now": time.time(), "timers": [{k: r.get(k) for k in ("id", "kind", "text", "due", "total", "label")} for r in EX.REMS]}).encode())
        if self.path.startswith("/api/health"):
            return self._send(200, json.dumps({"wake": WAKE_STATUS, "heard": LAST_HEARD, "level": round(MIC_LEVEL, 3), "ai": PV.active_name(), "clip": CLIP.status()}).encode())
        if self.path.startswith("/api/stream"):
            return self._send(200, json.dumps(SL.status()).encode())
        if self.path.startswith("/api/takeover"):
            return self._send(200, json.dumps(AP.status()).encode())
        if self.path.startswith("/api/languages"):
            return self._send(200, json.dumps({"active": I18N.code(), "languages": [{"code": c, "name": v[0], "native": v[1]} for c, v in I18N.LANGS.items()]}).encode())
        if self.path.startswith("/api/providers"):
            return self._send(200, json.dumps({"active": PV.active_name(), "providers": [p["name"] for p in PV.providers()]}).encode())
        if self.path.startswith("/api/events"):
            out = list(EVENTS); EVENTS.clear()
            return self._send(200, json.dumps({"events": out}).encode())
        if self.path.startswith("/api/mouse"):
            p = pyautogui.position()
            return self._send(200, json.dumps({"x": p[0], "y": p[1]}).encode())
        path = "index.html" if self.path in ("/", "") else self.path.lstrip("/").split("?")[0]
        full = os.path.normpath(os.path.join(STATIC, path))
        if not full.startswith(STATIC) or not os.path.isfile(full):
            return self._send(404, b"nope", "text/plain")
        ct = {"html": "text/html", "gif": "image/gif", "js": "text/javascript", "css": "text/css", "woff2": "font/woff2", "mp3": "audio/mpeg", "png": "image/png"}.get(full.rsplit(".", 1)[-1], "application/octet-stream")
        self._send(200, open(full, "rb").read(), ct)
    def do_POST(self):
        # only accept requests from our own UI (blocks random websites poking your PC)
        if self.headers.get("Origin") not in (None, f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"):
            return self._send(403, b'{"error":"bad origin"}')
        n = int(self.headers.get("Content-Length", 0)); raw = self.rfile.read(n)
        if self.path == "/api/stt":
            try: return self._send(200, json.dumps({"text": stt_pcm(raw) if self.headers.get("X-PCM") else stt(raw)}).encode())
            except Exception as e:
                log("STT ERROR:\n" + traceback.format_exc())
                return self._send(500, json.dumps({"error": f"{type(e).__name__}: {e}"}).encode())
        body = json.loads(raw or b"{}")
        if self.path == "/api/chat":
            self.send_response(200); self.send_header("Content-Type", "application/x-ndjson"); self.send_header("Cache-Control", "no-cache"); self.end_headers()
            def send(o): self.wfile.write((json.dumps(o) + "\n").encode()); self.wfile.flush()
            try: run_turn_stream(body.get("text", ""), send)
            except Exception as e:
                log("CHAT ERROR:\n" + traceback.format_exc())
                if isinstance(e, requests.exceptions.ConnectionError) and not PV.is_api():
                    msg = "My brain (Ollama) wouldn't start, choom. Open the Ollama app once, then ask me again."
                else:
                    msg = f"Ice got me, choom. Something glitched ({type(e).__name__}). Ask me again, and if it keeps happening check capri_log.txt."
                send({"t": "done", "say": msg, "mood": "alert"})
            return
        if self.path == "/api/keys":                                  # API KEYS menu: save / clear a key, pick the brain, pick the API voice service
            try:
                if "brain" in body:
                    name = body["brain"]; st = PV.keys_status()
                    b = next((x for x in st["brains"] if x["name"] == name), None)
                    if not b: return self._send(200, json.dumps({"ok": False, "msg": "unknown brain"}).encode())
                    if not b["ready"]: return self._send(200, json.dumps({"ok": False, "msg": f"add a key for {name} first"}).encode())
                    PV.set_active(name); log(f"brain switched to {name} (menu)")
                    return self._send(200, json.dumps({"ok": True, "msg": f"brain: {name}"}).encode())
                if "voice_service" in body:
                    return self._send(200, json.dumps({"ok": True, "msg": "API voice: " + str(PV.set_voice_service(body["voice_service"]))}).encode())
                res = PV.save_key(body.get("slot", ""), body.get("key", ""), body.get("voice_id"))
                log(f"API key for {body.get('slot')}: {res.get('msg')}")                 # never logs the key itself
                return self._send(200, json.dumps(res).encode())
            except Exception as e:
                log(f"API key save failed: {e}")
                return self._send(200, json.dumps({"ok": False, "msg": f"couldn't save: {e}"}).encode())
        if self.path == "/api/tts":
            try:
                audio = tts(body.get("text", "")[:600], body.get("voice"), body.get("engine"))
                return self._send(200, audio, "audio/wav" if audio[:4] == b"RIFF" else "audio/mpeg")
            except Exception as e:
                log(f"voice failed ({body.get('engine') or MD.S.get('voice_engine')}): {e}")
                return self._send(500, str(e).encode(), "text/plain")
        if self.path == "/api/voices":
            return self._send(200, json.dumps({"voices": VOICES, "default": VOICE}).encode())
        if self.path == "/api/settings":
            return self._send(200, json.dumps(apply_setting(body.get("key", ""), body.get("value"))).encode())
        if self.path == "/api/menu":
            if BRIDGE is not None: BRIDGE.menu.emit(int(body.get("w", 0)))
            return self._send(200, b"{}")
        if self.path == "/api/flatline":
            a = body.get("action")
            if a == "abort": flatline_abort()
            elif a in ("go", "close"): _flat_execute(FLAT["action"])
            return self._send(200, b"{}")
        if self.path == "/api/clip":
            act = body.get("action", "save")
            if act == "open": return self._send(200, json.dumps({"msg": CLIP.open_folder()}).encode())
            return self._send(200, json.dumps({"msg": clip_now("menu")}).encode())
        if self.path == "/api/ping":
            global LAST_ACTIVITY
            LAST_ACTIVITY = time.time(); return self._send(200, b"{}")
        if self.path == "/api/setai":
            return self._send(200, json.dumps({"active": PV.set_active(body.get("name", "")) or PV.active_name()}).encode())
        if self.path == "/api/callstate":
            global IN_CALL, CALL_PHASE
            IN_CALL = bool(body.get("inCall")); CALL_PHASE = body.get("phase") or ("connected" if IN_CALL else "idle")
            if BRIDGE is not None and MATE_ENABLED: BRIDGE.mate_js.emit("mate.setCall('%s')" % re.sub(r"[^a-z]", "", CALL_PHASE))
            return self._send(200, b"{}")
        if self.path.startswith("/api/mate/"):
            act = self.path.rsplit("/", 1)[-1]
            if act == "call":
                EVENTS.append({"type": "wake", "text": "", "cmd": ""})
                if BRIDGE is not None: BRIDGE.show.emit()
            elif act == "teleport": MATE["want"] = True
            elif act == "hide" and BRIDGE is not None: BRIDGE.mate_hide.emit()
            elif act == "mask" and BRIDGE is not None: BRIDGE.mate_mask.emit(json.dumps(body.get("rects", [])))
            return self._send(200, b"{}")
        if self.path in ("/api/fit", "/api/move", "/api/close", "/api/hide", "/api/quit"):
            if BRIDGE is not None:
                if self.path == "/api/fit": BRIDGE.fit.emit(int(body.get("h", 300)))
                elif self.path == "/api/move": BRIDGE.move.emit(int(body.get("dx", 0)), int(body.get("dy", 0)))
                elif self.path == "/api/quit": BRIDGE.quit.emit()
                else: BRIDGE.hide.emit()          # close = tuck into the tray, she keeps listening for "Hey Capri"
            return self._send(200, b"{}")
        if self.path == "/api/stream/chat":                 # rehearsal: fake chat typed on stream.html?test=1
            SL.on_comment(str(body.get("user", "viewer")), str(body.get("text", ""))); return self._send(200, b"{}")
        if self.path == "/api/tr":
            return self._send(200, json.dumps({"text": I18N.tr(str(body.get("text", ""))[:300])}).encode())
        if self.path == "/api/mcsetup":
            py = sys.executable.replace("pythonw.exe", "python.exe")
            subprocess.Popen([py, os.path.join(os.path.dirname(os.path.abspath(__file__)), "minecraft_setup.py")], creationflags=0x10 if OS == "Windows" else 0)
            return self._send(200, b"{}")
        if self.path == "/api/stop":
            AP.stop()
            STOP.set(); return self._send(200, b'{"ok":true}')
        self._send(404, b"{}")

if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)   # localhost only, never exposed to network
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    def _warm():
        global TEXT_MODEL
        _p = PV.provider()
        TEXT_MODEL = _p["model"] if _p.get("type", "ollama") == "ollama" and _p.get("model") not in (None, "auto") else pick_model()
        print("brain:", PV.active_name(), TEXT_MODEL)
        if not PV.is_api():
            _prime()
            threading.Thread(target=_fast_brain, daemon=True, name="fast_brain").start()
        def _vb_warm():                                    # Voicebox loads its engine on the FIRST line (20-60 s): do that now, not mid-chat
            t0 = time.time()
            try:
                if _voicebox_tts("Ready."): log(f"voice: Voicebox warmed up in {time.time() - t0:.1f}s")
            except Exception as e: log(f"voice: Voicebox warm-up failed: {e}")
        threading.Thread(target=_vb_warm, daemon=True, name="vb_warm").start()
        try: _get_whisper(); log("speech model ready")                                                                            # and the mic model
        except Exception: log("SPEECH MODEL LOAD FAILED:\n" + traceback.format_exc())
    def guarded(fn, name):
        def run():
            while True:
                try: fn(); return
                except Exception: log(f"{name} crashed, restarting:\n" + traceback.format_exc()); time.sleep(3)
        threading.Thread(target=run, daemon=True, name=name).start()
    def _startup():
        if not PV.is_api(): ensure_ollama()
        _warm()
    guarded(_startup, "warm")
    if SAFE: log("SAFE MODE (after repeated crashes): clip buffer and desktop mate are off this run. Details: capri_crash.txt")
    if MD.S.get("clip", True) and not SAFE: CLIP.start()                             # the 30-second rolling buffer (memory only)
    guarded(wake_loop, "wake_loop")
    guarded(roam_loop, "roam_loop")
    guarded(timer_watch, "timer_watch")
    guarded(EX.reminder_loop, "reminders")                              # timers/reminders keep running while she's hidden in the tray
    guarded(track_loop, "track_loop")                                   # knows what window you're using
    guarded(ollama_watchdog, "ollama_watchdog")
    guarded(AP.hotkey_loop, "autopilot_hotkey")                         # F8 = take back control from the autopilot
    threading.Timer(8, lambda: I18N.prewarm(FIXED_LINES)).start()       # her fixed lines in your language (once, cached)
    url = f"http://127.0.0.1:{PORT}"
    try:
        from PySide6.QtCore import Qt, QUrl, QObject, Signal, Slot
        from PySide6.QtCore import QPointF, QRect, QTimer
        from PySide6.QtGui import QRegion
        from PySide6.QtGui import QColor, QIcon, QPixmap, QPainter, QPen, QPolygonF
        from PySide6.QtWidgets import QApplication, QMainWindow, QSystemTrayIcon, QMenu
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
    except ImportError:
        print("PySide6 missing -> opening in browser. Run: pip install PySide6")
        webbrowser.open(url); threading.Event().wait()
        sys.exit()

    class Bridge(QObject):
        fit = Signal(int); move = Signal(int, int); close = Signal(); show = Signal(); hide = Signal(); quit = Signal()
        takeover = Signal(bool)
        scale = Signal(float); roam = Signal(); timers = Signal(int); menu = Signal(int); tray_msg = Signal(str); flatline = Signal(str); flat_hide = Signal()
        mate_goto = Signal(int, int, str); mate_move = Signal(int, int); mate_mask = Signal(str); mate_js = Signal(str); mate_hide = Signal(); mate_toggle = Signal()
    BRIDGE = Bridge()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)      # closing hides her to the tray instead of quitting
    BASE_W = 420; SCALE = MD.S.get("scale", 0.85); W, H0 = int(BASE_W * SCALE), 420; EXTRA = 0
    sg = app.primaryScreen().availableGeometry()
    win = QMainWindow()
    win.setWindowTitle("CAPRI")
    win.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
    win.setAttribute(Qt.WA_TranslucentBackground, True)   # real see-through window
    win.setStyleSheet("background: transparent;")
    win.setGeometry(sg.right() - W - 12, sg.bottom() - H0 - 12, W, H0)

    view = QWebEngineView()
    view.setAttribute(Qt.WA_TranslucentBackground, True)
    view.setStyleSheet("background: transparent;")
    page = view.page()
    try: page.profile().clearHttpCache()                        # never show an old copy of her UI after an update
    except Exception: pass
    page.setBackgroundColor(QColor(0, 0, 0, 0))
    view.settings().setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
    # let her use your microphone (voice input) - granted automatically, it's your own local page
    if hasattr(page, "permissionRequested"):
        page.permissionRequested.connect(lambda p: p.grant())
    else:
        page.featurePermissionRequested.connect(
            lambda origin, feat: page.setFeaturePermission(origin, feat, QWebEnginePage.PermissionPolicy.PermissionGrantedByUser))
    win.setCentralWidget(view)
    view.load(QUrl(url)); view.setZoomFactor(SCALE)
    DPR = app.primaryScreen().devicePixelRatio()
    SCREEN = (sg.left(), sg.top(), sg.width(), sg.height())

    # ---- the desktop mate: a second small transparent always-on-top window that only she lives in ----
    mate_win = mate_view = None
    if MATE_ENABLED:
        mate_win = QMainWindow(); mate_win.setWindowTitle("CAPRI MATE")
        mate_win.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus)
        mate_win.setAttribute(Qt.WA_TranslucentBackground, True); mate_win.setAttribute(Qt.WA_ShowWithoutActivating, True)
        mate_win.setStyleSheet("background: transparent;"); mate_win.resize(MATE_W, MATE_H)
        mate_view = QWebEngineView(); mate_view.setAttribute(Qt.WA_TranslucentBackground, True); mate_view.setStyleSheet("background: transparent;")
        mate_view.page().setBackgroundColor(QColor(0, 0, 0, 0))
        mate_win.setCentralWidget(mate_view); mate_view.load(QUrl(url + "/mate.html"))

    # ---- timer HUD: small click-through countdown in the top-left corner, shown only while a timer/reminder is running ----
    timer_win = QMainWindow(); timer_win.setWindowTitle("CAPRI TIMER")
    timer_win.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
    timer_win.setAttribute(Qt.WA_TranslucentBackground, True); timer_win.setAttribute(Qt.WA_ShowWithoutActivating, True)
    timer_win.setStyleSheet("background: transparent;"); timer_win.resize(300, 90); timer_win.move(sg.left() + 14, sg.top() + 14)
    timer_view = QWebEngineView(); timer_view.setAttribute(Qt.WA_TranslucentBackground, True); timer_view.setStyleSheet("background: transparent;")
    timer_view.page().setBackgroundColor(QColor(0, 0, 0, 0)); timer_win.setCentralWidget(timer_view); timer_view.load(QUrl(url + "/timer.html"))

    # ---- autopilot overlay: full-screen, click-through neon frame + HUD while she's playing for you ----
    take_win = QMainWindow(); take_win.setWindowTitle("CAPRI AUTOPILOT")
    take_win.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
    take_win.setAttribute(Qt.WA_TranslucentBackground, True); take_win.setAttribute(Qt.WA_ShowWithoutActivating, True); take_win.setStyleSheet("background: transparent;")
    take_view = QWebEngineView(); take_view.setAttribute(Qt.WA_TranslucentBackground, True); take_view.setStyleSheet("background: transparent;")
    take_view.page().setBackgroundColor(QColor(0, 0, 0, 0)); take_win.setCentralWidget(take_view)

    # ---- flatline overlay: a full-screen glitch/heartbeat/flatline sequence shown right before the PC powers off ----
    flat_win = QMainWindow(); flat_win.setWindowTitle("CAPRI FLATLINE")
    flat_win.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
    flat_win.setAttribute(Qt.WA_TranslucentBackground, True); flat_win.setStyleSheet("background: transparent;")
    flat_view = QWebEngineView(); flat_view.setAttribute(Qt.WA_TranslucentBackground, True); flat_view.setStyleSheet("background: transparent;")
    flat_view.page().setBackgroundColor(QColor(0, 0, 0, 0)); flat_view.settings().setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
    flat_win.setCentralWidget(flat_view)

    class Ctl(QObject):   # lives on the GUI thread, so window changes are thread-safe
        @Slot(int)
        def on_fit(self, h):
            h = max(120, min(int(h * SCALE), sg.height()))
            g = win.geometry(); bottom = g.y() + g.height()
            win.setGeometry(g.x(), bottom - h, W + EXTRA, h)
        @Slot(int, int)
        def on_move(self, dx, dy):
            win.move(win.x() + dx, win.y() + dy)
        @Slot()
        def on_show(self):
            if mate_win is not None:
                if not mate_win.isVisible(): MATE["visible"] = True; MATE["want"] = True      # she teleports in to take the call
                else: self.dock_main()
            WIN_VISIBLE[0] = True; win.show(); win.raise_(); win.activateWindow()
        def dock_main(self):
            """Put the call/chat window right beside her."""
            if mate_win is None or not mate_win.isVisible(): return
            g = mate_win.geometry(); h = win.height() or 420
            x = g.right() - 50 if g.right() + 400 < sg.right() else g.left() - (W + EXTRA) + 50
            x = max(sg.left(), min(x, sg.right() - W)); bottom = min(g.bottom() - 20, sg.bottom())
            win.setGeometry(x, max(sg.top(), bottom - h), W + EXTRA, h)
        @Slot(int, int, str)
        def on_mate_goto(self, x, y, kind):
            if mate_win is None: return
            ax, ay = MATE_ANCHOR["sit" if kind == "sit" else "stand"]
            def land():
                mate_win.move(x - ax, y - ay)
                mate_view.page().runJavaScript("mate.setPerch('%s'); mate.teleportIn()" % kind)
                self.dock_main() if win.isVisible() else None
            if mate_win.isVisible():
                mate_view.page().runJavaScript("mate.teleportOut()"); QTimer.singleShot(420, land)
            else:
                mate_win.move(x - ax, y - ay); mate_win.show()
                mate_view.page().runJavaScript("mate.setPerch('%s'); mate.boot()" % kind)
                if win.isVisible(): QTimer.singleShot(300, self.dock_main)
        @Slot(int, int)
        def on_mate_move(self, x, y):
            if mate_win is None or not mate_win.isVisible(): return
            ax, ay = MATE_ANCHOR["sit" if MATE["kind"] == "sit" else "stand"]
            mate_win.move(x - ax, y - ay)
        @Slot(str)
        def on_mate_mask(self, rects):
            if mate_win is None: return
            try:
                reg = QRegion()
                for r in json.loads(rects): reg = reg.united(QRegion(QRect(int(r[0]), int(r[1]), int(r[2]), int(r[3]))))
                mate_win.setMask(reg)
            except Exception: pass
        @Slot(str)
        def on_mate_js(self, code):
            if mate_view is not None: mate_view.page().runJavaScript(code)
        @Slot()
        def on_mate_hide(self):
            if mate_win is not None: mate_win.hide(); MATE["visible"] = False; MATE["shown"] = False
        @Slot()
        def on_mate_toggle(self):
            if mate_win is None: return
            if mate_win.isVisible(): self.on_mate_hide()
            else: MATE["visible"] = True; MATE["want"] = True
        @Slot()
        def on_hide(self):
            WIN_VISIBLE[0] = False; win.hide()
        @Slot(float)
        def on_scale(self, f):
            global SCALE, W
            global EXTRA
            old = SCALE; SCALE = max(0.5, min(1.4, float(f))); W = int(BASE_W * SCALE); EXTRA = int(EXTRA * SCALE / old); view.setZoomFactor(SCALE)
            g = win.geometry(); win.setGeometry(g.x() + g.width() - (W + EXTRA), g.y(), W + EXTRA, g.height())
            view.page().runJavaScript("fetch('/api/fit',{method:'POST',body:JSON.stringify({h:document.querySelector('#root').offsetHeight})})")
        @Slot()
        def on_roam(self):
            import random
            if not win.isVisible(): return
            view.page().runJavaScript("window.roamOut && roamOut()")
            def go():
                g = win.geometry()
                x = random.randint(sg.left() + 10, max(sg.left() + 10, sg.right() - g.width() - 10)); y = random.randint(sg.top() + 10, max(sg.top() + 10, sg.bottom() - g.height() - 10))
                win.move(x, y); view.page().runJavaScript("window.roamIn && roamIn()")
            QTimer.singleShot(480, go)
        @Slot(int)
        def on_timers(self, n):
            if n > 0: timer_win.resize(300, min(n, 5) * 74 + 16); timer_win.show()
            else: timer_win.hide()
        @Slot(bool)
        def on_takeover(self, on):
            if on:
                take_win.setGeometry(app.primaryScreen().geometry()); take_view.load(QUrl(url + "/takeover.html")); take_win.show()
            else:
                take_win.hide(); take_view.load(QUrl("about:blank"))
        @Slot(str)
        def on_flatline(self, action):
            flat_win.setGeometry(app.primaryScreen().geometry())
            flat_view.load(QUrl(url + "/flatline.html?action=" + action + "&t=" + str(int(time.time() * 1000))))
            flat_win.show(); flat_win.raise_(); flat_win.activateWindow(); flat_view.setFocus()
        @Slot()
        def on_flat_hide(self):
            flat_win.hide(); flat_view.load(QUrl("about:blank"))
        @Slot(str)
        def on_tray_msg(self, msg):
            try: tray.showMessage("Capri", msg, QSystemTrayIcon.MessageIcon.Information, 4000)
            except Exception: pass
        @Slot(int)
        def on_menu(self, w):
            """Config menu open (w > 0 CSS px): grow the window to the LEFT so the menu sits beside Capri; close: shrink back."""
            global EXTRA
            new = int(w * SCALE); delta = new - EXTRA; EXTRA = new
            g = win.geometry(); x = max(sg.left(), g.x() - delta)
            win.setGeometry(x, g.y(), W + EXTRA, g.height())
            view.page().runJavaScript("fetch('/api/fit',{method:'POST',body:JSON.stringify({h:document.querySelector('#root').offsetHeight})})")
        @Slot()
        def on_quit(self):
            app.quit()
    ctl = Ctl()

    # Windows blinks the mouse pointer while a see-through window repaints under it, so: while the pointer is inside one of
    # her windows, tell that page to hold still. Checked on the GUI thread every 120 ms (cheap: just compares rectangles).
    from PySide6.QtGui import QCursor
    _still = {}
    def _cursor_watch():
        p = QCursor.pos()
        for name, w, v in (("main", win, view), ("mate", mate_win, mate_view)):
            if w is None or v is None: continue
            inside = bool(w.isVisible() and w.frameGeometry().contains(p))
            if _still.get(name) != inside:
                _still[name] = inside
                v.page().runJavaScript("window.capriStill && capriStill(%s)" % ("true" if inside else "false"))
    _cw = QTimer(); _cw.timeout.connect(_cursor_watch); _cw.start(120)

    BRIDGE.fit.connect(ctl.on_fit); BRIDGE.move.connect(ctl.on_move)
    BRIDGE.close.connect(ctl.on_hide); BRIDGE.hide.connect(ctl.on_hide); BRIDGE.show.connect(ctl.on_show); BRIDGE.quit.connect(ctl.on_quit)
    BRIDGE.tray_msg.connect(ctl.on_tray_msg); BRIDGE.flatline.connect(ctl.on_flatline); BRIDGE.flat_hide.connect(ctl.on_flat_hide); BRIDGE.scale.connect(ctl.on_scale); BRIDGE.menu.connect(ctl.on_menu); BRIDGE.roam.connect(ctl.on_roam); BRIDGE.timers.connect(ctl.on_timers)
    BRIDGE.takeover.connect(ctl.on_takeover)
    BRIDGE.mate_goto.connect(ctl.on_mate_goto); BRIDGE.mate_move.connect(ctl.on_mate_move); BRIDGE.mate_mask.connect(ctl.on_mate_mask)
    BRIDGE.mate_js.connect(ctl.on_mate_js); BRIDGE.mate_hide.connect(ctl.on_mate_hide); BRIDGE.mate_toggle.connect(ctl.on_mate_toggle)

    # ---- tray icon (she lives here when the window is closed) ----
    import math
    def make_icon():
        pm = QPixmap(64, 64); pm.fill(QColor(0, 0, 0, 0))
        p = QPainter(pm); p.setRenderHint(QPainter.RenderHint.Antialiasing); p.setPen(Qt.PenStyle.NoPen)
        for i in range(8):
            a = math.radians(i * 45 - 90); u = (math.cos(a), math.sin(a)); q = (-u[1], u[0])
            poly = QPolygonF([QPointF(32 + u[0] * 17 + q[0] * 6, 32 + u[1] * 17 + q[1] * 6), QPointF(32 + u[0] * 17 - q[0] * 6, 32 + u[1] * 17 - q[1] * 6), QPointF(32 + u[0] * 31, 32 + u[1] * 31)])
            p.setBrush(QColor("#ff2a6d" if i % 2 == 0 else "#3dff9a")); p.drawPolygon(poly)
        p.setBrush(QColor("#101a4a")); p.setPen(QPen(QColor("#5cf08a"), 3)); p.drawEllipse(QPointF(32, 32), 12, 12)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor("#2a63ff")); p.drawEllipse(QPointF(32, 32), 7, 7)
        p.setBrush(QColor("#ffffff")); p.drawEllipse(QPointF(33, 31), 3, 3); p.end()
        return QIcon(pm)
    _ip = os.path.join(STATIC, "capri_tray.png")
    icon = QIcon(_ip) if os.path.exists(_ip) else make_icon(); win.setWindowIcon(icon)
    tray = QSystemTrayIcon(icon, app); tray.setToolTip("Capri - say \"Hey Capri\", \"Call Capri\" or \"Activate mic\"")
    menu = QMenu()
    menu.addAction("Show Capri (call window)", ctl.on_show)
    if MATE_ENABLED: menu.addAction("Show / hide desktop Capri", ctl.on_mate_toggle)
    menu.addAction("Save clip now (last 30 s)", lambda: _clip_notify(clip_now("tray")))
    menu.addAction("Open clips folder", lambda: CLIP.open_folder())
    clip_act = menu.addAction("Clip buffer (records the last 30 s, memory only)"); clip_act.setCheckable(True); clip_act.setChecked(bool(MD.S.get("clip", True)))
    clip_act.toggled.connect(lambda on: apply_setting("clip", bool(on)))
    wake_act = menu.addAction("Microphone (untick = completely off)"); wake_act.setCheckable(True); wake_act.setChecked(bool(MD.S.get("voice", True)))
    def _toggle_wake(on):
        apply_setting("voice", bool(on))
    wake_act.toggled.connect(_toggle_wake)
    try:
        from PySide6.QtGui import QActionGroup
        ai_menu = menu.addMenu("AI brain (providers.json)"); grp = QActionGroup(ai_menu); grp.setExclusive(True)
        for _p in PV.providers():
            act = ai_menu.addAction(_p["name"]); act.setCheckable(True); act.setChecked(_p["name"] == PV.active_name()); grp.addAction(act)
            act.triggered.connect(lambda _=False, n=_p["name"]: PV.set_active(n))
    except Exception:
        log("tray AI menu failed:\n" + traceback.format_exc())
    menu.addSeparator(); menu.addAction("Quit", ctl.on_quit)
    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason: ctl.on_show() if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick) else None)
    tray.show()

    if MATE_ENABLED:
        MATE["visible"] = True; MATE["want"] = True                 # she teleports in as soon as the app is up
        guarded(mate_loop, "mate_loop")
    elif "--tray" not in sys.argv:
        WIN_VISIBLE[0] = True; win.show()
    sys.exit(app.exec())
