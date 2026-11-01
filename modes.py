"""
Capri's modes: Music, Research, Homework, Gaming, Watching. Each mode has a DEFAULT app/service (change it by right-clicking Capri),
and you can always override it in the same sentence ("play pain 1993 by drake on youtube").
server.py gives us what we need via init(): chat, open_url, open_app, spotify, youtube, yt_lookup, type_slow, paste, start_menu_find, events, log, in_call
"""
import difflib, html, json, os, re, shutil, subprocess, threading, time, urllib.parse
from pathlib import Path
import requests
import i18n as I18N
import music as MU

HERE = Path(__file__).resolve().parent
ctx = {}
def init(**kw): ctx.update(kw)
def _log(m):
    try: ctx["log"](m)
    except Exception: pass

# =====================================================================  settings (right-click menu writes these)
FILE = HERE / "capri_settings.json"
DEFAULTS = {"mode": "off",
            "defaults": {"music": "spotify", "research": "web", "homework": "google docs", "gaming": "steam", "watching": "youtube"},
            "minecraft": "ask", "homework_input": "type", "wake_mode": "any", "clip": True, "clip_quality": "normal", "clip_audio": True, "scale": 0.85, "roam": True, "voice": True, "speak": False, "language": "en",
            "voice_engine": "beeps", "voice_pitch": "normal", "voice_volume": 0.6, "text_bg": False}     # her voice: beeps (default) / piper / voicebox / api / off
def _load():
    s = json.loads(json.dumps(DEFAULTS))
    try:
        d = json.loads(FILE.read_text(encoding="utf-8"))
        for k, v in d.items():
            if k == "defaults" and isinstance(v, dict): s["defaults"].update(v)
            elif k in s: s[k] = v
    except Exception: pass
    inst = HERE / "install_language.json"            # written by the installer: the language you picked there is the language she speaks
    try:
        d = json.loads(inst.read_text(encoding="utf-8-sig"))
        lang = d.get("language", "")
        if lang: s["language"] = lang.lower().split("-")[0]
        if d.get("speak") is True: s["speak"] = True            # the installer downloaded a voice in her language
        if lang or "speak" in d:
            FILE.write_text(json.dumps(s, indent=1), encoding="utf-8")
        inst.unlink()
    except FileNotFoundError: pass
    except Exception: pass
    return s
S = _load()
def save():
    try: FILE.write_text(json.dumps(S, indent=1), encoding="utf-8")
    except Exception as e: _log(f"settings save failed: {e}")
def setv(key, value):
    if key.startswith("default."): S["defaults"][key.split(".", 1)[1]] = value
    elif key in S and key != "defaults": S[key] = value
    if key == "mode" and value not in MODES + ["off"]: S["mode"] = "off"
    if key == "language" and value not in I18N.LANGS: S["language"] = "en"
    save(); return S

MODES = ["music", "research", "homework", "gaming", "watching"]
PENDING = {}

# =====================================================================  tiny helpers
def _clean(t): return re.sub(r"\s+", " ", re.sub(r"^(?:hey capri|capri)[, ]*", "", t.strip(), flags=re.I)).strip(" ,.!?")
def _q(t): return urllib.parse.quote_plus(t)

SERVICE_RX = re.compile(r"\b(?:on|in|using|with|via|through|from)\s+(youtube music|yt music|youtube|spotify|apple music|soundcloud|netflix|disney\s*\+|disney plus|prime video|amazon prime|prime|twitch|crunchyroll|hulu|max)\b\s*$", re.I)
SERVICE_NAMES = {"youtube music": "youtube music", "yt music": "youtube music", "youtube": "youtube", "spotify": "spotify", "apple music": "apple music", "soundcloud": "soundcloud",
                 "netflix": "netflix", "disney+": "disney+", "disney plus": "disney+", "prime video": "prime video", "amazon prime": "prime video", "prime": "prime video", "twitch": "twitch",
                 "crunchyroll": "crunchyroll", "hulu": "hulu", "max": "max"}
def split_service(text):
    """'pain 1993 by drake on youtube' -> ('pain 1993 by drake', 'youtube')"""
    m = SERVICE_RX.search(text.strip(" .!?"))
    if not m: return text.strip(" .!?"), None
    svc = SERVICE_NAMES.get(re.sub(r"\s+", " ", m.group(1).lower().replace("disney +", "disney+")), None)
    return text.strip(" .!?")[:m.start()].strip(" ,"), svc

# =====================================================================  MUSIC
def music_play(query, service=None):
    """Smart first ("hutchers newest song", "a random song from my liked songs", "my gym playlist"), plain search-and-play otherwise."""
    svc = (service or S["defaults"]["music"]).lower()
    if svc in ("spotify", "youtube", "youtube music"):
        return MU.play(query, svc, lambda q: _plain_music(q, svc), I18N.name())
    return _plain_music(query, svc)

def _plain_music(query, svc):
    if svc == "spotify": return ctx["spotify"](query)
    if svc == "youtube": return ctx["youtube"](query)
    if svc == "youtube music":
        vid, title = ctx["yt_lookup"](query)
        ctx["open_url"](f"https://music.youtube.com/watch?v={vid}" if vid else f"https://music.youtube.com/search?q={_q(query)}")
        return f"playing {title or query} on YouTube Music"
    if svc == "apple music": ctx["open_url"](f"https://music.apple.com/search?term={_q(query)}"); return f"pulled up {query} on Apple Music"
    if svc == "soundcloud": ctx["open_url"](f"https://soundcloud.com/search?q={_q(query)}"); return f"pulled up {query} on SoundCloud"
    return ctx["youtube"](query)

# =====================================================================  WATCHING
WATCH_URLS = {"netflix": "https://www.netflix.com/search?q={q}", "disney+": "https://www.disneyplus.com/search?q={q}", "prime video": "https://www.amazon.com/s?k={q}&i=instant-video",
              "twitch": "https://www.twitch.tv/search?term={q}", "crunchyroll": "https://www.crunchyroll.com/search?q={q}", "hulu": "https://www.hulu.com/search?q={q}", "max": "https://play.max.com/search?q={q}"}
def latest_from_channel(name):
    try:
        import yt_dlp
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "extract_flat": True, "skip_download": True, "playlistend": 1}) as y:
            top = (y.extract_info(f"ytsearch1:{name}", download=False).get("entries") or [None])[0]
            chan = (top or {}).get("channel_url") or (top or {}).get("uploader_url")
            if not chan: return None, ""
            vids = y.extract_info(chan.rstrip("/") + "/videos", download=False)
            e = (vids.get("entries") or [None])[0]
            if e and e.get("entries"): e = e["entries"][0]
            return (e or {}).get("id"), (e or {}).get("title", "")
    except Exception as ex:
        _log(f"latest_from_channel failed: {ex}"); return None, ""

def watch_play(query, service=None):
    svc = (service or S["defaults"]["watching"]).lower()
    if svc == "youtube":
        m = re.search(r"^(.*?)(?:'s|s'|’s)?\s+(?:latest|newest|most recent|new)\s+(?:video|upload|vid)s?\b", query, re.I)
        if m and m.group(1).strip():
            vid, title = latest_from_channel(m.group(1).strip())
            if vid:
                ctx["open_url"](f"https://www.youtube.com/watch?v={vid}&autoplay=1"); return f"playing {m.group(1).strip()}'s latest: {title}"
        return ctx["youtube"](query)
    url = WATCH_URLS.get(svc)
    if not url: return ctx["youtube"](query)
    ctx["open_url"](url.format(q=_q(query))); return f"pulled up {query} on {svc.title()}"

# =====================================================================  GAMING
RIOT = {"valorant": "valorant", "league of legends": "league_of_legends", "league": "league_of_legends", "lol": "league_of_legends", "teamfight tactics": "bacon", "tft": "bacon", "legends of runeterra": "bacon", "2xko": "2xko"}
EPIC = {"fortnite": "fortnite", "rocket league": "sugar", "fall guys": "fallguys"}
def _steam_root():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k: return Path(winreg.QueryValueEx(k, "SteamPath")[0])
    except Exception: pass
    for c in (r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam", str(Path.home() / ".steam" / "steam"), str(Path.home() / "Library/Application Support/Steam")):
        if Path(c).is_dir(): return Path(c)
    return None

def steam_games(root=None):
    root = Path(root) if root else _steam_root()
    if not root: return {}
    libs = [root / "steamapps"]
    try:
        txt = (root / "steamapps" / "libraryfolders.vdf").read_text(encoding="utf-8", errors="replace")
        libs += [Path(p.replace("\\\\", "\\")) / "steamapps" for p in re.findall(r'"path"\s+"([^"]+)"', txt)]
    except Exception: pass
    games = {}
    for lib in dict.fromkeys(libs):
        for acf in lib.glob("appmanifest_*.acf"):
            try:
                t = acf.read_text(encoding="utf-8", errors="replace")
                games[re.search(r'"name"\s+"([^"]+)"', t).group(1)] = re.search(r'"appid"\s+"(\d+)"', t).group(1)
            except Exception: pass
    return games

def find_steam_game(name, root=None):
    games = steam_games(root); n = name.lower().strip()
    if not games or not n: return None
    best, score = None, 0
    for g, appid in games.items():
        gl = g.lower()
        sc = 1.0 if gl == n else 0.92 if n in gl or gl in n else difflib.SequenceMatcher(None, n, gl).ratio()
        if sc > score: best, score = (g, appid), sc
    return best if score >= 0.62 else None

def _launch_uri(uri): os.startfile(uri)       # Windows only
RIOT_GAME_EXE = {"valorant": ("VALORANT-Win64-Shipping.exe", "VALORANT.exe"), "league_of_legends": ("LeagueClientUx.exe", "LeagueClient.exe", "League of Legends.exe"),
                 "bacon": ("LoR.exe",), "2xko": ("2XKO.exe",)}
PLAY_WORDS = {"PLAY", "JOUER", "SPIELEN", "JUGAR", "GIOCA", "JOGAR", "GRAJ", "ИГРАТЬ", "OYNA", "ГРАТИ", "プレイ", "플레이", "开始游戏", "العب", "SPELEN"}

def _riot_exe():
    """Where the Riot Client really is (Riot writes it to RiotClientInstalls.json), else the usual places."""
    try:
        d = json.loads(Path(r"C:\ProgramData\Riot Games\RiotClientInstalls.json").read_text(encoding="utf-8"))
        for k in ("rc_default", "rc_live", "rc_beta"):
            if d.get(k) and os.path.exists(d[k]): return d[k]
    except Exception: pass
    for p in (r"C:\Riot Games\Riot Client\RiotClientServices.exe", r"D:\Riot Games\Riot Client\RiotClientServices.exe",
              os.path.expandvars(r"%ProgramFiles%\Riot Games\Riot Client\RiotClientServices.exe")):
        if os.path.exists(p): return p
    p = ctx["start_menu_find"]("riot client")
    return p

def _running(names):
    try:
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, creationflags=0x08000000).stdout.lower()
        return any(f'"{n.lower()}"' in out for n in names)
    except Exception: return False

def _press_play(prod, label, timeout=75):
    """The Riot Client often just opens the game's page. If the game hasn't started after a few seconds,
       find the PLAY button in the Riot Client window (OCR) and click it, then confirm the game process appears."""
    import mc_vision as MV
    exes = RIOT_GAME_EXE.get(prod, ())
    t0 = time.time(); clicks = 0; say = lambda m: ctx["events"].append({"type": "act", "text": "// " + m, "bad": False})
    while time.time() - t0 < timeout:
        time.sleep(3)
        if exes and _running(exes): say(f"{label} is starting"); return
        if time.time() - t0 < 7 or clicks >= 3: continue
        try:
            win = next((w for w in ctx["list_windows"]() if re.match(r"^Riot Client", w["title"]) or os.path.basename(ctx["exe_of"](w["hwnd"])).lower() in ("riot client.exe", "riotclientux.exe")), None)
            if not win: continue
            ctx["bring_front"](win["hwnd"]); time.sleep(0.8)
            l, t, w, h = MV.window_rect(win["hwnd"]); img = MV.Screen((l, t, w, h)).grab()
            words = [x for x in MV.ocr_words(img) if x[0].strip().upper().strip(".!") in PLAY_WORDS]
            if not words: continue
            _, tx, ty, tw, th = max(words, key=lambda x: x[3] * x[4])            # the big PLAY button, not a small "play" link
            MV.click_screen(l + tx + tw / 2, t + ty + th / 2); clicks += 1
            say(f"pressed PLAY in the Riot Client ({clicks})")
        except Exception as e:
            _log(f"riot play click failed: {e}")
    if exes and not _running(exes): say(f"{label} didn't start: check the Riot Client (update / login / Vanguard restart?)")

def _try_riot(low):
    for k, prod in RIOT.items():
        if re.search(rf"\b{re.escape(k)}\b", low):
            exe = _riot_exe()
            if not exe: return None
            if prod in RIOT_GAME_EXE and _running(RIOT_GAME_EXE[prod]): return f"{k.title()} is already running, choom"
            if exe.lower().endswith(".lnk"): os.startfile(exe)
            else: subprocess.Popen([exe, f"--launch-product={prod}", "--launch-patchline=live"])
            threading.Thread(target=_press_play, args=(prod, k.title()), daemon=True, name="riot_play").start()
            return f"launching {k.title()} through the Riot Client"
    return None
def _try_epic(low):
    for k, app in EPIC.items():
        if re.search(rf"\b{re.escape(k)}\b", low):
            try: _launch_uri(f"com.epicgames.launcher://apps/{app}?action=launch&silent=true"); return f"launching {k.title()} through Epic"
            except Exception: return None
    return None
# ---- Roblox: "open roblox and play steal a brainrot" -> find that experience and join it directly
ROBLOX_GAME_RX = re.compile(r"(?:roblox\s+(?:and\s+)?(?:play|join|launch|open|start|load|hop on|get on)\s+(?:the\s+game\s+)?(.+))|"
                            r"(?:(?:play|join|launch|open|start|load)\s+(.+?)\s+(?:on|in|from|through)\s+roblox)|"
                            r"(?:^roblox\s+(?!and\b)(.+))", re.I)
ROBLOX_FIX = {"braintrot": "brainrot", "brain rot": "brainrot", "brainrott": "brainrot", "bloxfruits": "blox fruits", "grow a garden": "grow a garden"}

def _roblox_experience(name):
    """Name of a Roblox experience -> (title, placeId), using Roblox's own search (the same one as the search bar)."""
    q = name.strip(" .!?'\"")
    for k, v in ROBLOX_FIX.items(): q = re.sub(rf"\b{re.escape(k)}\b", v, q, flags=re.I)
    hdr = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Capri/1.0", "Accept": "application/json"}
    def walk(o, out):
        if isinstance(o, dict):
            if o.get("rootPlaceId") or (o.get("universeId") and o.get("name")): out.append(o)
            for v in o.values(): walk(v, out)
        elif isinstance(o, list):
            for v in o: walk(v, out)
    try:
        import uuid
        r = requests.get("https://apis.roblox.com/search-api/omni-search", params={"searchQuery": q, "sessionId": str(uuid.uuid4()), "pageType": "all"}, headers=hdr, timeout=8)
        hits = []; walk(r.json(), hits)
        if hits:
            best = max(hits[:6], key=lambda h: difflib.SequenceMatcher(None, q.lower(), str(h.get("name", "")).lower()).ratio() + (0.15 if hits.index(h) == 0 else 0))
            pid = best.get("rootPlaceId")
            if not pid and best.get("universeId"):
                g = requests.get("https://games.roblox.com/v1/games", params={"universeIds": best["universeId"]}, headers=hdr, timeout=8).json()
                pid = (g.get("data") or [{}])[0].get("rootPlaceId")
            if pid: return str(best.get("name") or q), str(pid)
    except Exception as e:
        _log(f"roblox search failed: {e}")
    try:                                                         # fallback: a web search for the game's roblox.com page
        html_ = requests.get("https://html.duckduckgo.com/html/", params={"q": f"site:roblox.com/games {q}"}, headers={"User-Agent": hdr["User-Agent"]}, timeout=8).text
        m = re.search(r"roblox\.com/games/(\d+)/([\w-]+)", urllib.parse.unquote(html_))
        if m: return m.group(2).replace("-", " "), m.group(1)
    except Exception as e:
        _log(f"roblox web search failed: {e}")
    return None

def _roblox_join(name):
    hit = _roblox_experience(name)
    if not hit: return None
    title, pid = hit
    try: _launch_uri(f"roblox://experiences/start?placeId={pid}")          # Roblox Player joins the game directly
    except Exception:
        ctx["open_url"](f"https://www.roblox.com/games/{pid}")              # no Roblox Player protocol: open the game page (press Play)
        return f"opened {title} on roblox.com, hit the green Play button"
    return f"joining {title} on Roblox"

def _try_roblox(low):
    if "roblox" not in low: return None
    m = ROBLOX_GAME_RX.search(low)
    game = next((g for g in (m.groups() if m else ()) if g), None)
    if game and not re.fullmatch(r"(?:it|the app|roblox|now|please)", game.strip()):
        r = _roblox_join(game)
        if r: return r
        return f"I couldn't find '{game}' on Roblox, choom. Opening Roblox so you can pick it." + (" " + (_open_roblox() or ""))
    return _open_roblox()

def _open_roblox():
    p = ctx["start_menu_find"]("roblox player") or ctx["start_menu_find"]("roblox")
    if p: os.startfile(p); return "launching Roblox"
    try: _launch_uri("roblox-player:"); return "launching Roblox"
    except Exception: return None
def _try_steam(low, n):
    hit = find_steam_game(n)
    if not hit: return None
    try: _launch_uri(f"steam://rungameid/{hit[1]}"); return f"launching {hit[0]} on Steam"
    except Exception as e: return f"couldn't start {hit[0]}: {e}"

def launch_game(name):
    """Tries your DEFAULT launcher's library first, then the others, then the Start Menu."""
    n = re.sub(r"^(?:the\s+game\s+)?", "", _clean(name), flags=re.I).strip()
    low = n.lower()
    if "minecraft" in low:
        edition = "java" if "java" in low else "bedrock" if "bedrock" in low else S["minecraft"]
        if edition not in ("java", "bedrock"):
            PENDING.clear(); PENDING["kind"] = "minecraft_edition"
            return "Minecraft! Bedrock or Java, choom?"
        return _minecraft(edition)
    order = {"steam": ["steam", "riot", "epic", "roblox"], "riot": ["riot", "steam", "epic", "roblox"], "roblox": ["roblox", "steam", "riot", "epic"],
             "epic": ["epic", "steam", "riot", "roblox"], "minecraft": ["steam", "riot", "epic", "roblox"]}.get(S["defaults"].get("gaming", "steam"), ["steam", "riot", "epic", "roblox"])
    fns = {"steam": lambda: _try_steam(low, n), "riot": lambda: _try_riot(low), "epic": lambda: _try_epic(low), "roblox": lambda: _try_roblox(low)}
    for k in order:
        r = fns[k]()
        if r: return r
    p = ctx["start_menu_find"](n)
    if p:
        try: os.startfile(p); return f"launching {n}"
        except Exception as e: return f"couldn't start {n}: {e}"
    if S["defaults"].get("gaming") == "roblox":                  # Roblox is your default: "play steal a brainrot" = that Roblox experience
        r = _roblox_join(n)
        if r: return r
    return f"I can't find {n} in your Steam library or Start Menu, choom"

def _minecraft(edition):
    if edition == "bedrock":
        try: _launch_uri("minecraft:"); return "launching Minecraft Bedrock"
        except Exception: return "couldn't start Minecraft Bedrock (is it installed?)"
    p = ctx["start_menu_find"]("minecraft launcher")
    if p:
        os.startfile(p); return "launching Minecraft Java"
    return "I can't find the Minecraft Launcher, choom"

# =====================================================================  HOMEWORK
HW = {"busy": False}
APP_NAMES = {"word": "Word", "google docs": "Google Docs", "docs": "Google Docs", "notepad": "Notepad", "here": "the window you were on"}
# the Google Docs tab title in the languages Capri speaks ("Untitled document - Google Docs", "Документ без названия - Google Документы"...)
DOCS_TITLE = re.compile(r"Google Docs|Google Документы|Google Документи|Google ドキュメント|Google 문서|Google 文档|Google 文件|Documentos de Google|Documenti Google|"
                        r"Documentos Google|Dokumenty Google|Google Dokümanlar|مستندات Google|Google डॉक्स", re.I)
GOOGLE_LOGIN = re.compile(r"Google Accounts|Comptes Google|Google Konten|Cuentas de Google|Account Google|Contas do Google|Konta Google|Google-accounts|Аккаунты Google|"
                          r"Google Hesapları|Облікові записи Google|Google アカウント|Google 계정|Google 账号|حسابات Google|Google खाते|Sign in|Connexion|Anmelden|Iniciar sesión|Accedi|Fazer login|Zaloguj", re.I)
BROWSERS = ("chrome.exe", "msedge.exe", "brave.exe", "firefox.exe", "opera.exe", "vivaldi.exe", "arc.exe")

def _word_installed():
    if shutil.which("winword"): return True
    try:
        import winreg
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try: winreg.CloseKey(winreg.OpenKey(root, r"Software\Microsoft\Windows\CurrentVersion\App Paths\Winword.exe")); return True
            except OSError: pass
    except Exception: pass
    return any(os.path.exists(p) for p in (r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE", r"C:\Program Files (x86)\Microsoft Office\root\Office16\WINWORD.EXE"))

def _wait_window(match, timeout, before=()):
    """Polls the open windows until one matches. match(title, exe) -> True / 'login' / False."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            for w in ctx["list_windows"]():
                if w["hwnd"] in before: continue
                r = match(w["title"], os.path.basename(ctx["exe_of"](w["hwnd"])).lower())
                if r: return w["hwnd"], r
        except Exception as e: _log(f"wait_window: {e}")
        time.sleep(0.5)
    return None, None

def _dismiss_dialogs(exe):
    """Closes message boxes (window class #32770) that app popped up, by pressing their default button (OK)."""
    if os.name != "nt": return
    try:
        import ctypes
        u = ctypes.windll.user32; buf = ctypes.create_unicode_buffer(64)
        for w in ctx["list_windows"]():
            if os.path.basename(ctx["exe_of"](w["hwnd"])).lower() != exe: continue
            u.GetClassNameW(w["hwnd"], buf, 64)
            if buf.value == "#32770":
                u.PostMessageW(w["hwnd"], 0x0111, 1, 0)                   # WM_COMMAND IDOK
                _log(f"closed a {exe} pop-up: {w['title']}"); time.sleep(0.4)
    except Exception as e: _log(f"dismiss dialogs: {e}")

def _open_target(app):
    """Opens the place to write in and returns (hwnd, app, problem). hwnd is the exact window she will type into."""
    if os.name != "nt": return None, app, None
    if app == "here":
        return ctx["last_win"](), app, None
    if app == "word" and not _word_installed():
        _log("Word isn't installed: using Google Docs"); app = "google docs"
    before = {w["hwnd"] for w in ctx["list_windows"]()}
    if app == "word":
        subprocess.Popen(["cmd", "/c", "start", "", "winword", "/w"], creationflags=0x08000000)
        h, _ = _wait_window(lambda t, e: e == "winword.exe" and "word" in t.lower(), 45, before)
        if not h: return None, app, "Word didn't open (is it activated / signed in?)"
        time.sleep(1.5); return h, app, None
    if app == "notepad":
        ctx["open_app"]("notepad")
        h, _ = _wait_window(lambda t, e: e == "notepad.exe", 15)
        if not h: return None, app, "Notepad didn't open"
        time.sleep(0.8); _dismiss_dialogs("notepad.exe")                       # e.g. "Cannot find <old file>" when Notepad restores a deleted tab
        ctx["bring_front"](h); time.sleep(0.6)
        import pyautogui
        pyautogui.press("esc"); time.sleep(0.3); pyautogui.press("esc"); time.sleep(0.3)   # new Notepad's in-window pop-ups close with Esc (harmless otherwise)
        pyautogui.hotkey("ctrl", "n"); time.sleep(0.8)        # Windows 11 reopens your old tabs: always write in a fresh one
        _dismiss_dialogs("notepad.exe")
        h2, _ = _wait_window(lambda t, e: e == "notepad.exe", 3)
        return h2 or h, app, None
    # Google Docs: a brand-new doc in your default browser (where you're signed in to Google)
    old = {(w["hwnd"], w["title"]) for w in ctx["list_windows"]()}           # Docs you already had open don't count
    t_open = time.time()
    ctx["open_url"]("https://docs.google.com/document/create")
    def docs(t, e):
        if e and e not in BROWSERS: return False
        if DOCS_TITLE.search(t):
            fg_h, fg_t, _ = ctx["fg"]()
            for w in ctx["list_windows"]():
                if w["title"] == t and (w["hwnd"], t) not in old: return "doc"
            if time.time() - t_open > 6 and DOCS_TITLE.search(fg_t or ""): return "doc"     # same title as an old doc, but it's the tab in front
            return False
        if GOOGLE_LOGIN.search(t) and "google" in t.lower(): return "login"
        return False
    h, kind = _wait_window(docs, 40)
    if kind == "doc":
        fg_h, fg_t, _ = ctx["fg"]()
        if fg_h and DOCS_TITLE.search(fg_t or ""): h = fg_h                    # the new tab is the one in front
    if kind == "login": return None, app, "Google wants you to sign in first: log into Google in your browser, then ask me again"
    if not h: return None, app, "Google Docs didn't load in time (slow internet?)"
    time.sleep(2.5)                                     # the doc's editor finishes loading after the title appears
    return h, app, None

CODE_RX = re.compile(r"\b(python|java(?:script)?|c\+\+|c#|html|css|sql|php|ruby|rust|golang|kotlin|swift|lua|scratch|code|coding|program(?:ming)?|function|loop|algorithm|script|variable|array|recursion)\b", re.I)
CREATIVE_RX = re.compile(r"\b(story|poem|poetry|letter|diary|speech|script for|song)\b", re.I)

def kind_of(topic, noun=""):
    if noun in ("code", "program", "script") or CODE_RX.search(topic or ""): return "code"
    if noun in ("story", "poem", "letter", "speech") or CREATIVE_RX.search(noun or ""): return "creative"
    return "essay"

def _write(topic, words, kind="essay"):
    lang = "" if I18N.is_en() else f" Write it entirely in {I18N.name()}."
    if kind == "code":
        sysmsg = ("You are a top student doing a programming homework. Output ONLY the homework as plain text: the title on the first line, a short clear explanation "
                  "of the concept, then complete, correct, runnable code examples with helpful # comments (indent with 4 spaces), each followed by one line saying "
                  "what it outputs, then a short summary. Never use markdown: no ``` fences, no asterisks, no headings symbols. No 'Here is your homework'." + lang)
        msgs = [{"role": "system", "content": sysmsg}, {"role": "user", "content": f"Do this programming homework (about {words} words including code): {topic}"}]
        text = ctx["chat"](msgs, {"num_ctx": 4096, "num_predict": int(words * 2.6) + 200, "temperature": 0.3}).strip()
        return clean_code(text)
    if kind == "creative":
        sysmsg = ("You are a talented student writer. Output ONLY the piece: the title on the first line, then the text. Vivid, original, age-appropriate, "
                  "plain text with no markdown, no asterisks, no 'Here is your story'." + lang)
        msgs = [{"role": "system", "content": sysmsg}, {"role": "user", "content": f"Write about {words} words: {topic}"}]
        return clean_essay(ctx["chat"](msgs, {"num_ctx": 4096, "num_predict": int(words * 2.0) + 120, "temperature": 0.8}).strip())
    sysmsg = ("You are a top student writing a school essay. Output ONLY the essay: the title on the first line, then 4-7 paragraphs separated by one blank line "
              "(an introduction with a clear thesis, body paragraphs each with one main point and concrete facts, dates, names or examples, and a conclusion). "
              "Plain text: no markdown, no bullet points, no asterisks, no headings other than the title, no 'Here is your essay'." + lang)
    msgs = [{"role": "system", "content": sysmsg}, {"role": "user", "content": f"Write an essay of about {words} words on: {topic}"}]
    text = ctx["chat"](msgs, {"num_ctx": 4096, "num_predict": int(words * 2.0) + 120, "temperature": 0.6}).strip()
    if len(text.split()) < words * 0.7:                 # small models stop early: ask for the rest once
        more = ctx["chat"](msgs + [{"role": "assistant", "content": text}, {"role": "user", "content": f"Continue the essay from where it stops, so the whole thing is about {words} words. Only output the new paragraphs, then the conclusion."}],
                           {"num_ctx": 6144, "num_predict": int(words * 1.4) + 80, "temperature": 0.6}).strip()
        if more: text = text.rstrip() + "\n\n" + more
    return clean_essay(text)

def clean_code(text):
    """Like clean_essay but keeps code intact (# comments, indentation, * operators): only drops ``` fences and chatter."""
    lines = text.replace("\r", "").split("\n")
    while lines and re.match(r"^\s*(?:sure|okay|ok|here(?:'s| is)|certainly|of course)\b.*[:!.]\s*$", lines[0], re.I): lines.pop(0)
    lines = [l for l in lines if not re.match(r"^\s*```", l)]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    text = re.sub(r"^\s*(?:title)\s*:\s*", "", text.strip(), flags=re.I)
    return re.sub(r"\*\*([^*\n]+)\*\*", r"\1", text).strip()

def clean_essay(text):
    lines = text.replace("\r", "").split("\n")
    while lines and re.match(r"^\s*(?:sure|okay|ok|here(?:'s| is)|certainly|of course|voici|claro|hier ist|ecco)\b.*[:!.]\s*$", lines[0], re.I): lines.pop(0)
    text = "\n".join(lines)
    text = re.sub(r"^\s*(?:title|titre|título|titel|titolo)\s*:\s*", "", text.strip(), flags=re.I)
    text = re.sub(r"(?m)^[ \t]{0,3}#{1,6}[ \t]*", "", text)
    text = re.sub(r"\*\*|__|`+|(?<!\w)\*(?!\s)|(?<!\s)\*(?!\w)", "", text)
    text = re.sub(r"(?m)^[ \t]*[-*•][ \t]+", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def _english_keyboard():
    try:
        import ctypes
        u = ctypes.windll.user32
        hkl = u.GetKeyboardLayout(u.GetWindowThreadProcessId(u.GetForegroundWindow(), None))
        return (hkl & 0x3FF) == 0x09                    # English layouts: Ctrl+Alt+1 is safe (on AltGr layouts it can type a symbol)
    except Exception: return False

def _backup(text, topic):
    """Every piece of homework is ALSO saved as a .txt in Documents\\Capri Homework, so nothing is ever lost
       (the clipboard isn't safe: a screenshot with Win+Shift+S replaces it)."""
    try:
        d = Path.home() / "Documents" / "Capri Homework"; d.mkdir(parents=True, exist_ok=True)
        name = re.sub(r"[^\w\- ]+", "", topic)[:50].strip() or "homework"
        f = d / f"{name} {time.strftime('%Y-%m-%d %H%M')}.txt"
        f.write_text(text, encoding="utf-8"); return f
    except Exception as e:
        _log(f"homework backup failed: {e}"); return None

def homework_essay(topic, words=400, app=None, progress=None, kind=None):
    """Opens Word / Google Docs / Notepad WHILE she writes, waits until that exact window is really ready, then types it in
       (Unicode keystrokes: any keyboard layout, any language). Click away and she pauses; say 'stop' and she stops."""
    prog = progress or (lambda m: None)
    def ev(m):
        prog(m)
        try: ctx["events"].append({"type": "act", "text": "// " + m, "bad": False})
        except Exception: pass
    words = max(80, min(int(words), 1500)); app = (app or S["defaults"]["homework"]).lower()
    if app == "docs": app = "google docs"
    if HW["busy"]: return "I'm already writing one, choom. Say 'stop' if you want me to drop it."
    HW["busy"] = True
    try:
        here = ctx["last_win"]() if app == "here" else None
        out = {}
        def gen():
            try: out["text"] = _write(topic, words, kind or kind_of(topic))
            except Exception as e: out["err"] = e
        g = threading.Thread(target=gen, daemon=True); g.start()
        ev(f"writing ~{words} words on {topic[:40]}...")
        hwnd, app, problem = (here, "here", None) if app == "here" else _open_target(app)
        g.join()
        if "err" in out: return f"my brain choked writing that: {out['err']}"
        text = out.get("text") or ""
        if not text: return "I came up blank, choom. Try again?"
        saved = _backup(text, topic)
        where = f" It's also saved in Documents\\Capri Homework\\{saved.name}." if saved else ""
        def opn():
            if saved and os.name == "nt":
                try: os.startfile(str(saved))                       # opens it in Notepad so you can copy it right away
                except Exception: pass
        if problem:
            ctx["copy"](text); opn(); return problem + ". The essay is on your clipboard (Ctrl+V)." + where
        if ctx["stop"].is_set(): ctx["copy"](text); return "stopped. The essay is on your clipboard." + where
        ev(f"typing it into {APP_NAMES.get(app, app)}...")
        res = ctx["type_into"](hwnd, text, "paste" if S["homework_input"] == "paste" else "type", ev)
        n = len(text.split())
        if res == "stopped": return "stopped typing. The rest is on your clipboard." + where
        if res == "lost": return "you left the document, so I stopped. The rest is on your clipboard: click where it goes and press Ctrl+V." + where
        if app in ("word", "google docs") and os.name == "nt" and _english_keyboard():
            try:                                            # make the first line a real title (Heading 1)
                import pyautogui
                pyautogui.hotkey("ctrl", "home"); time.sleep(0.2); pyautogui.hotkey("shift", "end"); time.sleep(0.2)
                pyautogui.hotkey("ctrl", "alt", "1"); time.sleep(0.3); pyautogui.hotkey("ctrl", "end")
            except Exception as e: _log(f"title style failed: {e}")
        return f"done: {n} words on {topic} in {APP_NAMES.get(app, app)}." + where
    finally:
        HW["busy"] = False

# =====================================================================  DEEP RESEARCH
UA = {"User-Agent": "Mozilla/5.0 (CapriDesktop personal assistant)"}
def _page_text(url, limit=3500):
    try:
        r = requests.get(url, headers=UA, timeout=10)
        if r.status_code != 200 or "html" not in r.headers.get("content-type", ""): return ""
        t = re.sub(r"(?is)<(script|style|nav|footer|header|aside|noscript)[^>]*>.*?</\1>", " ", r.text)
        t = html.unescape(re.sub(r"<[^>]+>", " ", t)); t = re.sub(r"\s+", " ", t).strip()
        return t[:limit]
    except Exception: return ""

def _plan(topic):
    try:
        out = ctx["chat"]([{"role": "system", "content": "Output 4 short web search queries (one per line, no numbering) that together cover the topic from different angles."},
                           {"role": "user", "content": topic}], {"num_ctx": 2048, "num_predict": 80, "temperature": 0.3})
        qs = [re.sub(r"^[\-\d\.\)\s]+", "", l).strip() for l in out.splitlines() if l.strip()]
        qs = [q for q in qs if 3 < len(q) < 90][:4]
        if qs: return [topic] + [q for q in qs if q.lower() != topic.lower()][:3]
    except Exception: pass
    return [topic, topic + " overview", topic + " facts"]

def clean_topic(t):
    t = re.sub(r"^(?:please\s+)?(?:deep\s+)?(?:research|look up|look into|find out about|learn about)\s+", "", t.strip(), flags=re.I)
    return re.sub(r"^(?:about|on|into)\s+", "", t, flags=re.I).strip(" ?.!")

def deep_research(topic, progress=None):
    """Plans several searches, reads Wikipedia + the top pages, then compiles precise bullet points."""
    prog = progress or (lambda m: None)
    topic = clean_topic(topic) or topic
    prog("planning searches...")
    sources, wiki_url = [], None
    queries = _plan(topic)
    ex = ctx["extras"]
    seen_titles = set()
    for q in queries[:3]:
        try:
            title = ex._wiki_title(q)
            if title and title not in seen_titles and len(seen_titles) < 2:
                seen_titles.add(title); txt = ex._wiki_extract(title)
                if txt: sources.append((f"Wikipedia: {title}", txt[:3500]));  wiki_url = wiki_url or "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
        except Exception as e: _log(f"wiki failed: {e}")
    pages = 0
    for q in queries:
        prog(f"searching: {q}")
        try: res = ex._ddg(q)
        except Exception as e: _log(f"ddg failed: {e}"); res = []
        for r in res[:3]:
            if r["snippet"]: sources.append((f"{r['title']} (snippet)", r["snippet"]))
        for r in res[:2]:
            if pages >= 3 or "wikipedia.org" in r["url"]: continue
            txt = _page_text(r["url"])
            if len(txt) > 600: sources.append((r["title"], txt)); pages += 1
    if not sources: return f"I couldn't reach anything on {topic}, choom. Is the internet on?"
    notes = []
    big = [s for s in sources if len(s[1]) > 400][:6]
    for i, (title, txt) in enumerate(big):
        prog(f"reading {i + 1}/{len(big)}: {title[:40]}")
        try:
            notes.append(ctx["chat"]([{"role": "system", "content": "From the source text, list up to 8 concrete facts relevant to the topic (names, dates, numbers, meanings). One per line starting with '- '. Facts only, no opinions."},
                                      {"role": "user", "content": f"TOPIC: {topic}\nSOURCE: {title}\n\n{txt}"}], {"num_ctx": 4096, "num_predict": 300, "temperature": 0.1}))
        except Exception as e: _log(f"summarise failed: {e}")
    snippets = "\n".join(f"- {t}: {x}" for t, x in sources if len(x) <= 400)[:1500]
    prog("compiling...")
    final = ctx["chat"]([{"role": "system", "content": "You compile research notes into precise bullet points. Merge duplicates, drop anything vague. Group under 3-6 short headings written in CAPS on their own line, each followed by bullet lines starting with '- '. Max 25 bullets. Use ONLY the notes." + ("" if I18N.is_en() else f" Write everything in {I18N.name()}.")},
                         {"role": "user", "content": f"TOPIC: {topic}\n\nNOTES:\n" + "\n".join(notes)[:6000] + "\n\nSNIPPETS:\n" + snippets}], {"num_ctx": 8192, "num_predict": 900, "temperature": 0.2}).strip()
    final = re.sub(r"^\s*[\*\u2022]\s*", "- ", final, flags=re.M)
    try: ctx["open_url"](wiki_url or "https://duckduckgo.com/?q=" + _q(topic))
    except Exception: pass
    return I18N.tr("Here's everything I dug up on {topic}:").replace("{topic}", topic) + "\n" + final

# =====================================================================  talking to modes
MODE_WORDS = {"music": "music", "research": "research", "homework": "homework", "gaming": "gaming", "game": "gaming", "watching": "watching", "watch": "watching", "movie": "watching"}
MODE_LINES = {
    "music": "Music mode, preem. Tell me what to play, choom.",
    "research": "Research mode. What should I research on?",
    "homework": "Homework mode. Ugh, fine. What are we writing?",
    "gaming": "Gaming mode! What are we launching, choom? Or say 'beat Minecraft for me' and I'll take over.",
    "watching": "Watching mode. What are we watching, baby?",
    "off": "Back to normal, choom."}

def handle_mode_text(t):
    low = _clean(t).lower()
    m = re.match(r"^(?:please\s+)?(?:switch to |turn on |enable |start |go to |enter |activate )?(music|research|homework|gaming|game|watching|watch|movie|normal|default)\s+mode\b(?:\s+(on|off))?", low)
    if m:
        word, onoff = m.group(1), m.group(2)
        if word in ("normal", "default") or onoff == "off": S["mode"] = "off"; save(); PENDING.clear(); return {"say": MODE_LINES["off"], "mood": "greet"}
        mode = MODE_WORDS[word]; S["mode"] = mode; save(); PENDING.clear()
        if mode == "research": PENDING["kind"] = "research_subject"
        return {"say": MODE_LINES[mode], "mood": "hyped"}
    if re.match(r"^(?:please\s+)?(?:exit|stop|leave|end|turn off|disable|quit)\s+(?:\w+\s+)?mode\b", low):
        S["mode"] = "off"; save(); PENDING.clear(); return {"say": MODE_LINES["off"], "mood": "greet"}
    return None

POWER_YES = re.compile(r"^(?:yes|yeah|yep|yup|sure|do it|go ahead|confirm|flatline|please do|ok|okay|affirmative|go on)\b", re.I)
YES = re.compile(r"^(?:yes|yeah|yep|yup|yea|sure|ok|okay|that'?s all|that is all|thats all|all good|nope that'?s it|no that'?s it|that'?s it|nothing else|no thanks|nah that'?s all)\b", re.I)
NO = re.compile(r"^(?:no|nope|nah|not yet|wait|actually)\b", re.I)

COMMANDISH = re.compile(r"^(?:shut|power|restart|reboot|remember|forget|what do you know|what have i told|set a timer|start a timer|timer|remind me|call me|ring me|cancel|hang up|play|launch|open|type|search|what time|what'?s the time|what is the time|use |switch to )", re.I)

def handle_pending(t, progress=None):
    kind = PENDING.get("kind")
    if not kind: return None
    low = _clean(t).lower()
    if re.match(r"^(?:never ?mind|cancel|forget it|stop)\b", low): PENDING.clear(); return {"say": "Fine, dropped it, choom.", "mood": "idle"}
    if kind == "research_subject":
        if handle_mode_text(t) is not None or COMMANDISH.match(low): return None      # a different command: don't treat it as a research subject
        PENDING.clear(); PENDING["kind"] = "research_subject"          # stay in research mode for the next subject
        res = deep_research(t, progress)
        return {"say": res + "\n\n" + I18N.tr("Anything else to research, choom?"), "mood": "hyped"}
    if kind == "minecraft_edition":
        ed = "java" if "java" in low else "bedrock" if "bedrock" in low else None
        if not ed: return {"say": "Bedrock or Java, choom?", "mood": "idle"}
        PENDING.clear()
        if re.search(r"\b(always|default|every time|from now on)\b", low): S["minecraft"] = ed; save()
        return {"say": _minecraft(ed), "mood": "hyped"}
    if kind == "power_confirm":
        action = PENDING.get("action", "shutdown"); PENDING.clear()
        if POWER_YES.match(low): return {"say": "Flatlining. Goodnight, choom.", "mood": "alert", "power": action}
        return {"say": "Okay, okay. Not flatlining anything. Crisis averted.", "mood": "hyped"}
    if kind == "timer_confirm":
        if NO.match(low) and not YES.match(low): PENDING.clear(); return {"say": "Go on then, what else do you need?", "mood": "idle"}
        if YES.match(low):
            PENDING.clear(); return {"say": "I'll call you when it's done, choom!", "mood": "hyped", "hangup": True}
        PENDING.clear(); return None                                     # something else: handle it normally
    return None

PLAY_RX = re.compile(r"^(?:please\s+)?(?:play|put on|queue up|queue|stream)\s+(.+)$", re.I)
LAUNCH_RX = re.compile(r"^(?:please\s+)?(?:launch|open|start|run|play|boot up|fire up)\s+(.+)$", re.I)
ESSAY_RX = re.compile(r"(?:write|do|make|type|draft|create)\s+(?:me\s+)?(?:an?\s+|my\s+|the\s+)?(?:(\d{2,4})[- ]words?\s+)?((?:[\w'+-]+\s+){0,4}?)(essay|report|paper|article|paragraph|summary|assignment|homework|coursework|worksheet|notes|answers?|story|poem|letter|speech|code|program|script|project|explanation)\b\s*(?:(?:about|on|for|regarding|of)\s+)?(.*)$", re.I)   # allows "a gcse style essay", "a 500 word persuasive essay"

def route(t):
    """Mode-aware commands, always using the DEFAULT unless the sentence names another service. Returns {'say','mood'} or None."""
    text = _clean(t); mode = S["mode"]
    m = PLAY_RX.match(text)
    if m:
        q, svc = split_service(m.group(1))
        if mode == "music" or svc in ("spotify", "apple music", "soundcloud", "youtube music"):
            return {"say": music_play(q, svc), "mood": "hyped", "pre": "Cueing it up, choom."}
        if mode == "watching" or svc in ("netflix", "disney+", "prime video", "twitch", "crunchyroll", "hulu", "max"):
            return {"say": watch_play(q, svc), "mood": "hyped", "pre": "On it."}
        if svc == "youtube":
            return {"say": ctx["youtube"](q), "mood": "hyped", "pre": "On it."}
    if mode == "gaming":
        m = LAUNCH_RX.match(text)
        if m: return {"say": launch_game(m.group(1)), "mood": "hyped"}
    if mode == "homework":
        m = ESSAY_RX.search(text)
        if m:
            words = int(m.group(1)) if m.group(1) else (int(re.search(r"(\d{2,4})\s*[- ]?words?", text).group(1)) if re.search(r"(\d{2,4})\s*[- ]?words?", text) else 400)
            topic = (m.group(4) or text).strip() or text
            style = re.sub(r"(\d{2,4})[- ]?words?", "", m.group(2) or "").strip()
            app = None
            am = re.search(r"\b(?:in|on|into|using)\s+(?:a\s+|my\s+|the\s+)?(google docs?|docs|word|microsoft word|notepad|here|this (?:window|doc|document|page))\b", topic, re.I)
            if not am: am = re.search(r"\s+(here|right here)\s*$", topic, re.I)
            if am:
                w = am.group(1).lower(); app = "google docs" if "doc" in w and "this" not in w else "word" if "word" in w else "notepad" if "notepad" in w else "here"
                topic = (topic[:am.start()] + topic[am.end():]).strip(" ,.")
            topic = re.sub(r"[,\s]*(?:(?:that(?:'s| is)|in|of|with)\s+)?(?:about\s+)?\d{2,4}\s*[- ]?words?(?:\s+long)?\s*$", "", topic, flags=re.I).strip(" ,.") or topic
            noun = m.group(3).lower()
            if style: topic = f"{topic} (written as a {style} {noun})"           # e.g. GCSE style, persuasive, A-level
            kind = kind_of(topic, noun)
            target = app or S["defaults"]["homework"]
            say = ("On it, choom. I'm writing it now, then I'll type it where you were." if target == "here"
                   else f"On it, choom. Opening {APP_NAMES.get(target, 'your doc')} and typing while I write.")
            return {"say": say, "mood": "working", "later": lambda: homework_essay(topic, words, app, kind=kind)}
    return None
