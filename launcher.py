"""Keeps Capri alive: if she ever crashes, this restarts her and writes what happened to capri_log.txt.
If she crashes 3 times within 2 minutes, she restarts in SAFE MODE (clip buffer + desktop mate off) instead of giving up.
Native crashes (a C library dying, e.g. audio drivers or Qt) leave their stack trace in capri_crash.txt; the launcher copies it into the log."""
import os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "capri_log.txt")
CRASH = os.path.join(HERE, "capri_crash.txt")
CODES = {3221225477: "0xC0000005 access violation", 3221226356: "0xC0000374 heap corruption", 3221225725: "0xC00000FD stack overflow", 3221226505: "0xC0000409 fatal error"}

def log(m):
    try:
        with open(LOG, "a", encoding="utf-8") as f: f.write(time.strftime("%H:%M:%S ") + m + "\n")
    except Exception: pass

def last_crash_trace():
    """The newest block faulthandler wrote, trimmed to the interesting part."""
    try:
        with open(CRASH, encoding="utf-8", errors="replace") as f: txt = f.read()[-20000:]
    except Exception: return ""
    block = txt.split("=== start")[-1]
    if "Fatal Python error" not in block and "Windows fatal exception" not in block: return ""
    return block.strip()[:4000]

def trim(path, keep=400_000):
    try:
        if os.path.getsize(path) > keep * 2:
            with open(path, "rb") as f: f.seek(-keep, 2); tail = f.read()
            with open(path, "wb") as f: f.write(tail)
    except Exception: pass

args = sys.argv[1:]
starts, safe = [], "--safe" in args
trim(LOG); trim(CRASH)
while True:
    now = time.time(); starts = [t for t in starts if now - t < 120]
    if len(starts) >= 3 and not safe:
        safe = True; starts = []
        log("launcher: 3 crashes in 2 minutes -> restarting in SAFE MODE (clip buffer and desktop mate off)")
    elif len(starts) >= 6:
        log("launcher: crashing even in safe mode, giving up. Send capri_log.txt and capri_crash.txt"); break
    starts.append(now)
    run_args = args + (["--safe"] if safe and "--safe" not in args else [])
    with open(LOG, "a", encoding="utf-8", errors="replace") as lf:
        p = subprocess.Popen([sys.executable, os.path.join(HERE, "server.py")] + run_args, cwd=HERE, stdout=lf, stderr=lf, stdin=subprocess.DEVNULL,
                             creationflags=0x08000000 if os.name == "nt" else 0)
        code = p.wait()
    if code == 0: break                                   # quit from the tray menu on purpose
    code_u = code & 0xFFFFFFFF
    log(f"launcher: Capri exited with code {code} ({CODES.get(code_u, hex(code_u))}), restarting in 2 s")
    tr = last_crash_trace()
    if tr: log("launcher: crash trace (from capri_crash.txt):\n" + tr)
    time.sleep(2)
