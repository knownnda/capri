"""
One-click stream setup for Capri's TikTok Minecraft show:   double-click stream_setup.bat   (or: python stream_setup.py)
  1. installs OBS Studio (winget) if it's missing
  2. installs TikTokLive (reads your LIVE chat)
  3. creates an OBS scene collection "Capri Live":
       - Minecraft (Game Capture of javaw.exe)            -> the game, full screen
       - Minecraft backup (Window Capture, hidden)        -> turn this on instead if Game Capture shows black
       - Capri overlay (Browser source stream.html)       -> gif, chat, votes, her replies (+ her voice, routed into OBS)
  4. opens OBS on that scene
Nothing here touches your existing OBS scenes: it adds a new collection (and backs up an old "Capri Live" if there is one).
"""
import json, os, shutil, subprocess, sys, time, uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
APPDATA = Path(os.environ.get("APPDATA", str(Path.home())))
OBS_CFG = APPDATA / "obs-studio"
SCENES = OBS_CFG / "basic" / "scenes"
NAME = "Capri Live"; FILE = "Capri_Live"                       # YOUR layout (landscape 1920x1080): gif top-left, chat top-right, game, reply bar
NAME_V = "Capri Live (vertical)"; FILE_V = "Capri_Live_vertical"  # optional TikTok-portrait version
PROFILE = "Capri"; PROFILE_DIR = "Capri"; PROFILE_V = "Capri Vertical"; PROFILE_V_DIR = "Capri_Vertical"
OVERLAY = "http://127.0.0.1:7777/stream.html"
W, H = 1920, 1080

def say(m): print("  " + m, flush=True)

def find_obs():
    for p in (os.path.expandvars(r"%ProgramFiles%\obs-studio\bin\64bit\obs64.exe"), os.path.expandvars(r"%ProgramFiles(x86)%\obs-studio\bin\64bit\obs64.exe"),
              os.path.expandvars(r"%LOCALAPPDATA%\Programs\obs-studio\bin\64bit\obs64.exe"), r"C:\Program Files\obs-studio\bin\64bit\obs64.exe"):
        if p and os.path.exists(p): return p
    for root in (os.path.expandvars(r"%ProgramFiles%\Steam\steamapps\common\OBS Studio\bin\64bit"), os.path.expandvars(r"%ProgramFiles(x86)%\Steam\steamapps\common\OBS Studio\bin\64bit")):
        if os.path.exists(os.path.join(root, "obs64.exe")): return os.path.join(root, "obs64.exe")
    return None

def obs_running():
    if os.name != "nt": return False
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq obs64.exe"], capture_output=True, text=True).stdout
        return "obs64.exe" in out.lower()
    except Exception: return False

def _src(name, kind, settings, extra=None):
    d = {"name": name, "uuid": str(uuid.uuid4()), "id": kind, "versioned_id": kind, "settings": settings, "mixers": 255, "sync": 0, "flags": 0,
         "volume": 1.0, "balance": 0.5, "enabled": True, "muted": False, "push-to-mute": False, "push-to-mute-delay": 0, "push-to-talk": False,
         "push-to-talk-delay": 0, "hotkeys": {}, "deinterlace_mode": 0, "deinterlace_field_order": 0, "monitoring_type": 0, "private_settings": {}}
    d.update(extra or {}); return d

def _item(src, i, visible=True, locked=False, box=(0, 0, W, H)):
    x, y, w, h = box
    return {"name": src["name"], "source_uuid": src["uuid"], "visible": visible, "locked": locked, "rot": 0.0, "pos": {"x": float(x), "y": float(y)},
            "scale": {"x": 1.0, "y": 1.0}, "align": 5, "bounds_type": 2, "bounds_align": 0, "bounds": {"x": float(w), "y": float(h)},
            "crop_left": 0, "crop_top": 0, "crop_right": 0, "crop_bottom": 0, "id": i, "group_item_backup": False, "scale_filter": "disable",
            "blend_method": "default", "blend_type": "normal", "show_transition": {"duration": 0}, "hide_transition": {"duration": 0}, "private_settings": {}}

LOADER = """<!doctype html><html><head><meta charset="utf-8"><title>Capri overlay</title>
<style>html,body{margin:0;width:100%;height:100%;background:transparent;overflow:hidden}iframe{border:0;width:100%;height:100%;background:transparent}
#w{position:absolute;left:30px;bottom:30px;font:600 26px 'Segoe UI',sans-serif;color:#ff2a6d;background:rgba(0,0,0,.75);padding:10px 18px;border:2px solid #ff2a6d}</style></head>
<body><div id="w">waiting for Capri... (start run.bat)</div><script>
// OBS loads this file from disk, so it always loads. It keeps checking until Capri's server answers, then shows the overlay,
// and reloads it if Capri restarts. (Pointing OBS straight at http://127.0.0.1:7777 left it blank forever if Capri started second.)
const URL_ = "__URL__"; let up = false, frame = null;
async function check(){
  let ok = false;
  try { await fetch("http://127.0.0.1:7777/api/health", {mode: "no-cors", cache: "no-store"}); ok = true; } catch (e) {}
  if (ok && !up){ up = true; document.getElementById("w").style.display = "none";
    if (frame) frame.remove(); frame = document.createElement("iframe"); frame.src = URL_ + (URL_.includes("?") ? "&" : "?") + "t=" + Date.now();
    frame.setAttribute("allowtransparency", "true"); document.body.appendChild(frame); }
  if (!ok && up){ up = false; document.getElementById("w").style.display = "block"; }
}
check(); setInterval(check, 3000);
</script></body></html>"""

def write_loaders():
    """Local loader pages next to stream.html: OBS opens these from disk (works even if Capri starts after OBS)."""
    out = {}
    for name, url in (("obs_overlay.html", OVERLAY), ("obs_overlay_vertical.html", OVERLAY + "?portrait=1")):
        f = HERE / "static" / name; f.write_text(LOADER.replace("__URL__", url), encoding="utf-8"); out[name] = f
    return out

def collection_vertical():
    """TikTok's recommended portrait canvas: game band in the middle, overlay (stream.html?portrait=1) around it."""
    c = collection(portrait=True); return c

def collection(portrait=False):
    win = "Minecraft:GLFW30:javaw.exe"                     # matched by the javaw.exe executable, whatever the version in the title
    game = _src("Minecraft", "game_capture", {"capture_mode": "window", "window": win, "priority": 2, "capture_cursor": False, "allow_transparency": False,
                                              "anti_cheat_hook": True, "capture_audio": True})
    backup = _src("Minecraft backup (turn on if the game is black)", "window_capture", {"window": win, "priority": 2, "method": 2, "cursor": False, "capture_audio": True})
    cw, ch = (1080, 1920) if portrait else (W, H)
    loader = HERE / "static" / ("obs_overlay_vertical.html" if portrait else "obs_overlay.html")
    overlay = _src("Capri overlay", "browser_source", {"is_local_file": True, "local_file": str(loader).replace("\\", "/"),
                                                      "url": OVERLAY + ("?portrait=1" if portrait else ""), "width": cw, "height": ch, "fps": 30, "fps_custom": False, "reroute_audio": True,
                                                      "restart_when_active": False, "shutdown": False, "css": "body { background-color: rgba(0,0,0,0); margin: 0; overflow: hidden; }"})
    name = NAME_V if portrait else NAME
    if portrait:      # game: full width band in the middle (y 700..1308); overlay: whole canvas
        gi, bi, oi = _item(game, 1, box=(0, 700, 1080, 608)), _item(backup, 2, visible=False, box=(0, 700, 1080, 608)), _item(overlay, 3, locked=True, box=(0, 0, 1080, 1920))
    else:
        gi, bi, oi = _item(game, 1), _item(backup, 2, visible=False), _item(overlay, 3, locked=True)
    scene = _src(name, "scene", {"id_counter": 3, "custom_size": False, "items": [gi, bi, oi]})
    return {"name": name, "current_scene": name, "current_program_scene": name, "scene_order": [{"name": name}],
            "sources": [game, backup, overlay, scene], "groups": [], "quick_transitions": [], "transitions": [], "saved_projectors": [],
            "current_transition": "Fade", "transition_duration": 300, "preview_locked": False, "scaling_enabled": False, "scaling_level": 0,
            "scaling_off_x": 0.0, "scaling_off_y": 0.0, "virtual-camera": {"type2": 3}, "modules": {}}

def _write(fname, data):
    SCENES.mkdir(parents=True, exist_ok=True)
    f = SCENES / (fname + ".json")
    if f.exists():
        bak = SCENES / f"{fname}.backup-{time.strftime('%Y%m%d-%H%M%S')}.json"; shutil.copy2(f, bak); say(f"old {fname} backed up -> {bak.name}")
    f.write_text(json.dumps(data, indent=1), encoding="utf-8"); return f

def _profile(name, folder, w, h):
    d = OBS_CFG / "basic" / "profiles" / folder; d.mkdir(parents=True, exist_ok=True)
    ini = d / "basic.ini"
    if not ini.exists():
        ini.write_text(f"[General]\nName={name}\n\n[Video]\nBaseCX={w}\nBaseCY={h}\nOutputCX={w}\nOutputCY={h}\nFPSType=0\nFPSCommon=30\n\n"
                       "[Output]\nMode=Simple\n\n[SimpleOutput]\nVBitrate=6000\nABitrate=160\nPreset=veryfast\n", encoding="utf-8")
    return d

def write_profile():
    """OBS profiles: 'Capri' (1920x1080, your layout) and 'Capri Vertical' (1080x1920). Your own profiles are untouched."""
    _profile(PROFILE_V, PROFILE_V_DIR, 1080, 1920)
    return _profile(PROFILE, PROFILE_DIR, 1920, 1080)

def write_collection():
    _write(FILE_V, collection_vertical())
    return _write(FILE, collection())

def main():
    print("\n=== CAPRI // STREAM SETUP (OBS + TikTok chat) ===\n")
    if os.name == "nt" and obs_running():
        say("OBS is open. Close it (it rewrites its scenes when it closes), then press Enter.")
        try: input("  ")
        except EOFError: pass
    obs = find_obs()
    if not obs and os.name == "nt":
        say("OBS Studio isn't installed: installing it with winget (click Yes if Windows asks)...")
        subprocess.run(["winget", "install", "-e", "--id", "OBSProject.OBSStudio", "--accept-package-agreements", "--accept-source-agreements"])
        obs = find_obs()
        if not obs: say("couldn't install OBS automatically: get it from https://obsproject.com, then run this again.")
    else:
        say(f"OBS found: {obs}" if obs else "OBS check skipped (not Windows)")
    say("installing TikTokLive (reads your LIVE chat)...")
    r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", "TikTokLive"])
    say("TikTokLive ready" if r.returncode == 0 else "TikTokLive install failed: run  python -m pip install TikTokLive")
    try:
        sys.path.insert(0, str(HERE)); import mc_vision as MV
        say("Minecraft autopilot (no mods): OCR " + (MV._ocr_init() or "missing -> run  python minecraft_setup.py"))
    except Exception as e: say(f"Minecraft autopilot check skipped: {e}")
    write_loaders()
    f = write_collection(); say(f"OBS scene collections '{NAME}' (your layout) and '{NAME_V}' -> {f.parent}")
    p = write_profile(); say(f"OBS profiles '{PROFILE}' (1920x1080) and '{PROFILE_V}' (1080x1920) -> {p.parent}")
    if obs:
        say("opening OBS on the Capri Live scene...")
        subprocess.Popen([obs, "--profile", PROFILE, "--collection", NAME, "--scene", NAME], cwd=os.path.dirname(obs))
    print("""
  Done. OBS opens on the 'Capri Live' scene (1920x1080): Capri top-left, chat top-right, game in the middle, her replies at the bottom.
  If OBS asks to run the Auto-Configuration Wizard: click No (the 'Capri' profile is already set up).
  Then follow the steps in STREAM_GUIDE.md (or the chat) to connect TikTok and go live.
""")
    if os.name == "nt":
        try: input("  Press Enter to close.")
        except EOFError: pass

if __name__ == "__main__":
    main()
