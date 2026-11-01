"""
One-time setup for Capri's Minecraft AUTOPILOT (vision edition: NO MODS):   python minecraft_setup.py
  1. installs Windows' OCR bindings (so she can read the F3 debug screen: position, facing, the block under the crosshair)
  2. turns off "pause on lost focus" in Minecraft so the game keeps running while you talk to her   (close Minecraft first)
  3. optional: pulls a small vision model (moondream) so she can answer "what do you see?"
  4. runs a test if Minecraft is open
Only use the autopilot in single-player or on your own server: most public servers ban automated play.
"""
import os, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MC = Path(os.environ.get("APPDATA", str(Path.home()))) / ".minecraft"
PKGS = ["mss", "numpy", "pillow", "winrt-runtime", "winrt-Windows.Media.Ocr", "winrt-Windows.Graphics.Imaging", "winrt-Windows.Security.Cryptography",
        "winrt-Windows.Foundation", "winrt-Windows.Foundation.Collections", "winrt-Windows.Globalization", "winrt-Windows.Storage.Streams"]

def say(m): print("  " + m, flush=True)

def set_option(key, value):
    opt = MC / "options.txt"
    if not opt.exists(): say("options.txt not found: start Minecraft once, then run this again"); return False
    lines = [l for l in opt.read_text(encoding="utf-8", errors="replace").splitlines() if not l.startswith(key + ":")] + [f"{key}:{value}"]
    opt.write_text("\n".join(lines) + "\n", encoding="utf-8"); return True

def main():
    print("\n=== Capri // Minecraft autopilot setup (no mods) ===\n")
    say("installing OCR + screen capture packages...")
    r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check"] + PKGS)
    say("packages ready" if r.returncode == 0 else "some packages failed: run  python -m pip install " + " ".join(PKGS))
    sys.path.insert(0, str(HERE)); import mc_vision as MV
    say("OCR engine: " + (MV._ocr_init() or "NOT AVAILABLE (she'll play by colour only)"))
    if MV.find_window():
        say("Minecraft is open: close it if you want me to change 'pause on lost focus' (it rewrites options.txt when it exits).")
    elif set_option("pauseOnLostFocus", "false"):
        say("pause on lost focus -> OFF")
    if input("  Download the 'moondream' vision model (~1.7 GB) so she can describe the screen? (y/n) [n]: ").strip().lower().startswith("y"):
        subprocess.run(["ollama", "pull", "moondream"])
    print("""
  Done. In Minecraft (Java): load a world, hold a pickaxe/axe in hotbar slot 1, blocks in slot 2, food in slot 9.
  Then tell Capri: 'chop some wood', 'find diamonds', 'explore', 'build a shelter' or 'play for me'.  F8 / 'stop' = your turn.
  Test what she sees (Minecraft open, F3 showing):  python mc_vision.py --test
""")

if __name__ == "__main__":
    main()
    try: input("  Press Enter to close.")
    except EOFError: pass
