"""
Capri's clip feature: keeps the LAST 30 SECONDS of your screen (and, if possible, your system sound) in memory only.
Say "clip" (or "clip that") and the last 30 seconds are saved as an mp4. Nothing is written to disk until you clip.

Video:  mss (screen grabs) -> JPEG frames in a RAM ring buffer -> ffmpeg (bundled via imageio-ffmpeg) encodes on demand.
Audio:  soundcard (WASAPI loopback = whatever you hear) -> PCM ring buffer -> muxed into the clip. Optional, best effort.
"""
import collections, io, os, shutil, subprocess, sys, threading, time, traceback, wave
from pathlib import Path

SECONDS = 30
QUALITY = {"low": (540, 12), "normal": (720, 15), "high": (1080, 24)}      # (max height, frames per second)

class Clipper:
    def __init__(self, log=print, notify=None, grab=None, out_dir=None):
        self.log = log; self.notify = notify or (lambda msg, path=None: None); self._grab = grab
        self.frames = collections.deque()          # (timestamp, jpeg bytes)
        self.audio = collections.deque()           # (timestamp_at_end, float32 array [n, 2])
        self.quality = "normal"; self.audio_on = True; self.sr = 48000
        self.running = False; self.lock = threading.Lock(); self._threads = []; self._saving = False
        self.audio_ok = False; self.error = ""
        self.out_dir = Path(out_dir) if out_dir else Path.home() / "Videos" / "Capri Clips"

    # ---------------- control ----------------
    def start(self):
        if self.running: return
        self.running = True; self.error = ""
        t = threading.Thread(target=self._video_loop, daemon=True, name="clip_video"); t.start(); self._threads = [t]
        if self.audio_on:
            a = threading.Thread(target=self._audio_loop, daemon=True, name="clip_audio"); a.start(); self._threads.append(a)
        self.log("clip buffer ON (last %d s kept in memory only)" % SECONDS)

    def stop(self):
        self.running = False
        with self.lock: self.frames.clear(); self.audio.clear()             # free the RAM, nothing was ever on disk
        self.log("clip buffer OFF (memory cleared)")

    def configure(self, quality=None, audio=None):
        restart = False
        if quality in QUALITY and quality != self.quality: self.quality = quality
        if audio is not None and bool(audio) != self.audio_on:
            self.audio_on = bool(audio); restart = self.running
        if restart: self.stop(); time.sleep(0.4); self.start()

    def status(self):
        with self.lock:
            n = len(self.frames); span = (self.frames[-1][0] - self.frames[0][0]) if n > 1 else 0.0
        return {"running": self.running, "seconds": round(min(span, SECONDS), 1), "audio": bool(self.audio_ok and self.audio_on), "error": self.error, "quality": self.quality}

    def ffmpeg(self):
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return shutil.which("ffmpeg")

    # ---------------- capture loops ----------------
    def _video_loop(self):
        """Screen frames come from clip_video_worker.py in a SEPARATE process: Windows' screen capture can hard-crash when the
           screen changes under it (Win+Shift+S, UAC, games going full screen). Now only the helper dies and gets restarted."""
        if self._grab is not None: return self._video_loop_inproc()
        import struct
        worker = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clip_video_worker.py")
        crashes = []
        while self.running:
            p = None; q = self.quality; h_max, fps = QUALITY[q]
            try:
                p = subprocess.Popen([sys.executable, worker, str(h_max), str(fps)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                                     creationflags=0x08000000 if os.name == "nt" else 0)
                if p.stdout.readline().strip() != b"OK": raise RuntimeError(f"screen capture helper didn't start (exit {p.poll()})")
                self.error = ""
                while self.running and self.quality == q:
                    head = p.stdout.read(12)
                    if len(head) < 12: raise RuntimeError(f"screen capture helper stopped (exit {p.poll()})")
                    ts, n = struct.unpack("<dI", head); data = p.stdout.read(n)
                    if len(data) < n: raise RuntimeError("screen capture helper stopped mid-frame")
                    now = time.time()
                    with self.lock:
                        self.frames.append((now, data))
                        while self.frames and now - self.frames[0][0] > SECONDS + 2: self.frames.popleft()
            except Exception as e:
                if not self.running: break
                now = time.time(); crashes = [t for t in crashes if now - t < 120] + [now]
                if len(crashes) >= 6:
                    self.error = "screen capture keeps failing: " + str(e)[:80]; self.running = False
                    self.log("clip video off: " + str(e)); break
                self.log(f"clip video helper restarting: {e}"); time.sleep(1.5)
            finally:
                if p is not None:
                    try: p.kill()
                    except Exception: pass

    def _video_loop_inproc(self):
        try:
            from PIL import Image
            while self.running:
                t0 = time.time(); h_max, fps = QUALITY[self.quality]
                img = self._grab()
                if img.height > h_max:
                    h = h_max; w = int(img.width * h_max / img.height) // 2 * 2
                    img = img.resize((w, h), Image.BILINEAR)
                bio = io.BytesIO(); img.save(bio, "JPEG", quality=65); now = time.time()
                with self.lock:
                    self.frames.append((now, bio.getvalue()))
                    while self.frames and now - self.frames[0][0] > SECONDS + 2: self.frames.popleft()
                time.sleep(max(0.0, 1.0 / fps - (time.time() - t0)))
        except Exception as e:
            self.error = "screen capture failed: " + str(e)[:80]; self.running = False
            self.log("clip video loop crashed:\n" + traceback.format_exc())

    def _audio_loop(self):
        """System sound comes from clip_audio_worker.py in a SEPARATE process: the soundcard library can hard-crash
           (heap corruption) on some drivers, and that used to take all of Capri down with it. Now only the helper dies."""
        import subprocess, sys
        import numpy as np
        here = os.path.dirname(os.path.abspath(__file__))
        worker = os.path.join(here, "clip_audio_worker.py")
        marker = os.path.join(here, "clip_audio_failed.txt")            # sound capture failed here recently: try just once, quietly
        try: limit = 1 if time.time() - os.path.getmtime(marker) < 86400 else 3
        except OSError: limit = 3
        crashes = []
        chunk = (self.sr // 10) * 2 * 4                                   # 0.1 s of float32 stereo
        while self.running and self.audio_on:
            p = None
            try:
                p = subprocess.Popen([sys.executable, worker, str(self.sr)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                                     creationflags=0x08000000 if os.name == "nt" else 0)
                if p.stdout.readline().strip() != b"OK":
                    code = p.wait(timeout=5) if p.poll() is None else p.poll()
                    raise RuntimeError(f"system sound capture unavailable (helper exit {code if code is None else hex(code & 0xFFFFFFFF)})")
                self.audio_ok = True
                try: os.remove(marker)
                except OSError: pass
                while self.running and self.audio_on:
                    buf = p.stdout.read(chunk)
                    if not buf or len(buf) < chunk: raise RuntimeError(f"audio helper stopped (exit {p.poll()})")
                    data = np.frombuffer(buf, dtype=np.float32).reshape(-1, 2); now = time.time()
                    with self.lock:
                        self.audio.append((now, data))
                        while self.audio and now - self.audio[0][0] > SECONDS + 2: self.audio.popleft()
            except Exception as e:
                self.audio_ok = False
                if not (self.running and self.audio_on): break
                now = time.time(); crashes = [t for t in crashes if now - t < 300] + [now]
                if len(crashes) >= limit:
                    self.log(f"clip audio off ({e}): clips are video-only. Fix: pip install PyAudioWPatch, then restart")
                    try: open(marker, "w").write(str(e))
                    except OSError: pass
                    break
                self.log(f"clip audio helper restarting: {e}"); time.sleep(3)
            finally:
                if p is not None:
                    try: p.kill()
                    except Exception: pass

    # ---------------- save ----------------
    def save(self, reason="voice"):
        """Starts saving the last 30 s in the background. Returns a short status string right away."""
        if self._saving: return "already saving a clip, choom"
        if not self.running: return "the clip buffer is OFF (turn it on in the config menu)"
        with self.lock: frames = list(self.frames); audio = list(self.audio)
        if len(frames) < 8: return "not enough footage buffered yet, give me a few seconds"
        exe = self.ffmpeg()
        if not exe: return "I can't find ffmpeg (pip install imageio-ffmpeg)"
        self._saving = True
        threading.Thread(target=self._encode, args=(frames, audio, exe), daemon=True, name="clip_encode").start()
        return "clipping the last %d seconds..." % min(SECONDS, int(frames[-1][0] - frames[0][0]))

    def _encode(self, frames, audio, exe):
        tmp_wav = None
        try:
            end = frames[-1][0]; start = max(frames[0][0], end - SECONDS)
            frames = [f for f in frames if f[0] >= start]
            dur = max(0.5, frames[-1][0] - frames[0][0]); fps = max(5.0, min(60.0, len(frames) / dur))
            self.out_dir.mkdir(parents=True, exist_ok=True)
            out = self.out_dir / time.strftime("Capri clip %Y-%m-%d %H-%M-%S.mp4")
            cmd = [exe, "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", "%.3f" % fps, "-vcodec", "mjpeg", "-i", "-"]
            a_ok = False
            if self.audio_on and audio:
                import numpy as np
                chunks = [a for t, a in audio if t >= start - 0.2]
                if chunks:
                    pcm = np.concatenate(chunks, axis=0); want = int(dur * self.sr)
                    pcm = pcm[-want:] if len(pcm) >= want else np.vstack([np.zeros((want - len(pcm), 2), dtype="float32"), pcm])
                    tmp_wav = str(self.out_dir / ("._tmp_%d.wav" % int(time.time())))
                    with wave.open(tmp_wav, "wb") as w:
                        w.setnchannels(2); w.setsampwidth(2); w.setframerate(self.sr)
                        w.writeframes((np.clip(pcm, -1, 1) * 32767).astype("<i2").tobytes())
                    cmd += ["-i", tmp_wav]; a_ok = True
            cmd += ["-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p"]
            if a_ok: cmd += ["-c:a", "aac", "-b:a", "160k", "-shortest"]
            cmd += ["-movflags", "+faststart", str(out)]
            p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=0x08000000 if os.name == "nt" else 0)
            try:
                for _, jpg in frames: p.stdin.write(jpg)
                p.stdin.close()
            except BrokenPipeError: pass
            err = p.stderr.read().decode("utf-8", "replace")[:300]; p.wait()
            if p.returncode != 0 or not out.exists(): raise RuntimeError("ffmpeg failed: " + err)
            self.log("clip saved: %s (%.0f s, audio=%s)" % (out, dur, a_ok))
            self.notify("clip saved (%d s%s): %s" % (round(dur), ", with sound" if a_ok else ", no sound", out.name), str(out))
        except Exception as e:
            self.log("clip failed:\n" + traceback.format_exc()); self.notify("clip failed: " + str(e)[:100], None)
        finally:
            self._saving = False
            if tmp_wav:
                try: os.remove(tmp_wav)
                except Exception: pass

    def open_folder(self):
        self.out_dir.mkdir(parents=True, exist_ok=True)
        try:
            if os.name == "nt": os.startfile(str(self.out_dir))
            elif sys.platform == "darwin": subprocess.Popen(["open", str(self.out_dir)])
            else: subprocess.Popen(["xdg-open", str(self.out_dir)])
        except Exception: pass
        return str(self.out_dir)
