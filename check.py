"""Readiness check:  python check.py   - tells you what's ready for a demo and what to fix."""
import importlib, json, os, shutil, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ok = lambda m: print("  [ OK ]", m)
bad = lambda m, fix="": print("  [ !! ]", m, ("-> " + fix) if fix else "")
note = lambda m: print("  [ -- ]", m)
print("\nCAPRI READINESS CHECK\n")
print("Python / packages")
(ok if sys.version_info >= (3, 9) else bad)("Python " + sys.version.split()[0])
for mod, pip in (("PySide6", "PySide6"), ("requests", "requests"), ("faster_whisper", "faster-whisper"), ("sounddevice", "sounddevice"), ("pyautogui", "pyautogui"),
                 ("pyperclip", "pyperclip"), ("spotipy", "spotipy"), ("yt_dlp", "yt-dlp"), ("PIL", "pillow"), ("mss", "mss (clip)"), ("imageio_ffmpeg", "imageio-ffmpeg (clip)"), ("soundcard", "soundcard (clip sound, optional)")):
    try: importlib.import_module(mod); ok(mod)
    except Exception: bad(mod + " missing", "pip install " + pip)
print("\nAI brain")
try:
    import requests
    tags = requests.get("http://127.0.0.1:11434/api/tags", timeout=3).json().get("models", [])
    ok("Ollama is running, models: " + (", ".join(m["name"] for m in tags) or "none"))
    if not any("3b" in m["name"] or "1b" in m["name"] for m in tags): note("for speed run: ollama pull llama3.2:3b")
    if not any("vision" in m["name"] for m in tags): note("for 'look at my screen': ollama pull llama3.2-vision")
except Exception:
    bad("Ollama isn't running", "install from ollama.com (Capri starts it for you once it's installed)")
print("\nMicrophone")
try:
    import sounddevice as sd; d = sd.query_devices(sd.default.device[0]); ok("mic: " + d["name"])
except Exception as e: bad("no microphone found (" + str(e)[:50] + ")", "plug one in / set CAPRI_MIC")
print("\nSpotify auto-play")
_spa = os.path.exists(os.path.join(HERE, "spotapi_session.json"))
if _spa:
    try: importlib.import_module("spotapi"); ok("SpotAPI session present (spotapi_session.json): no developer app needed")
    except Exception as e: bad("SpotAPI session present but the spotapi package is missing", "python -m pip install spotapi websockets pymongo redis")
if os.path.exists(os.path.join(HERE, "spotify.json")): ok("official API: spotify.json present" + (" and logged in" if os.path.exists(os.path.join(HERE, ".spotify_cache")) else " (run spotify_setup.py to log in)"))
elif not _spa: bad("not set up", "python spotify_setup.py   (option 1: paste one cookie, no developer app)")
note("open the Spotify app and play any song once before a demo (that makes it the active device)")
print("\nApps for the modes")
(ok if shutil.which("winword") or os.path.exists(r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE") else note)("Word " + ("found" if shutil.which("winword") else "not detected (homework mode can use Google Docs or Notepad instead)"))
try:
    sys.path.insert(0, HERE); import modes
    g = modes.steam_games(); (ok if g else note)(f"Steam library: {len(g)} games found" if g else "no Steam games found (gaming mode falls back to the Start Menu)")
except Exception as e: note("steam check skipped: " + str(e)[:50])
for p in (r"C:\Riot Games\Riot Client\RiotClientServices.exe",):
    (ok if os.path.exists(p) else note)("Riot Client " + ("found" if os.path.exists(p) else "not found"))
print("\nLanguage")
try:
    import modes as _m, i18n as _i; ok("Capri speaks " + _i.name() + " (right-click > LANGUAGE to change)")
except Exception as e: note("language check skipped: " + str(e)[:50])
try: importlib.import_module("ytmusicapi"); ok("ytmusicapi (smart YouTube music)")
except Exception: bad("ytmusicapi missing", "pip install ytmusicapi")
print("\nMinecraft autopilot (Java, no mods)")
try:
    import mc_vision as _mv
    _k = _mv._ocr_init(); (ok if _k else bad)("OCR for the F3 screen: " + (_k or "missing"), "python minecraft_setup.py")
except Exception as e: bad("mc_vision failed to load: " + str(e)[:60], "python minecraft_setup.py")
print("\nDone. Anything marked [ !! ] needs fixing before you demo.\n")
