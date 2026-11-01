"""
Screen grabber for the clip buffer, run as a SEPARATE process by clipper.py.

Windows' screen-capture call (GDI BitBlt) can hard-crash a process when the screen changes under it
(for example the Snipping Tool's Win+Shift+S overlay, a UAC prompt or a game switching to full screen).
Inside Capri that crash took her whole app down. In here, only this little helper dies and Capri restarts it.

Usage:  python clip_video_worker.py <max_height> <fps>
Output: "OK\n", then for every frame: 8-byte float timestamp + 4-byte length (little endian) + JPEG bytes.
"""
import io, struct, sys, time

def main():
    h_max = int(sys.argv[1]) if len(sys.argv) > 1 else 720
    fps = float(sys.argv[2]) if len(sys.argv) > 2 else 15
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)   # no "python stopped working" pop-ups from this helper
        except Exception: pass
    import mss
    from PIL import Image
    out = sys.stdout.buffer
    sct = mss.mss(); mon = sct.monitors[1]
    out.write(b"OK\n"); out.flush()
    fails = 0
    while True:
        t0 = time.time()
        try:
            shot = sct.grab(mon); fails = 0
        except Exception:                                   # a capture hiccup (secure desktop, mode switch): wait and try again
            fails += 1
            if fails > 50: return 3
            time.sleep(0.2)
            try: sct.close()
            except Exception: pass
            sct = mss.mss(); mon = sct.monitors[1]
            continue
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        if img.height > h_max:
            w = int(img.width * h_max / img.height) // 2 * 2
            img = img.resize((w, h_max), Image.BILINEAR)
        bio = io.BytesIO(); img.save(bio, "JPEG", quality=65); data = bio.getvalue()
        try:
            out.write(struct.pack("<dI", time.time(), len(data))); out.write(data); out.flush()
        except (BrokenPipeError, OSError):
            return 0                                        # Capri closed the pipe: we're done
        time.sleep(max(0.0, 1.0 / fps - (time.time() - t0)))

if __name__ == "__main__":
    sys.exit(main() or 0)
