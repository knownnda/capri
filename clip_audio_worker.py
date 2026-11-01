"""
Records what you hear (WASAPI loopback) for the clip buffer and streams raw float32 stereo PCM to stdout.
It runs as its OWN process on purpose: audio libraries can hard-crash on some PCs / drivers, and in a separate process
that only kills this helper, never Capri. clipper.py restarts it, and gives up on sound after repeated failures.
Backends: PyAudioWPatch (made for WASAPI loopback, most reliable) first, then soundcard.
Usage (clipper.py does this):  python clip_audio_worker.py <samplerate>
"""
import os, sys, warnings

def _quiet_crashes():
    """No 'pythonw.exe - Application Error' pop-ups if a driver/library crashes in here: just exit, clipper.py handles it."""
    if os.name != "nt": return
    try:
        import ctypes
        ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)       # FAILCRITICALERRORS | NOGPFAULTERRORBOX | NOOPENFILEERRORBOX
        try: ctypes.cdll.msvcrt._set_abort_behavior(0, 0x1 | 0x2)          # no abort() / Watson dialog
        except Exception: pass
    except Exception: pass

def _to_stereo_rate(np, data, src_rate, dst_rate):
    if data.ndim == 1: data = data.reshape(-1, 1)
    if data.shape[1] == 1: data = np.repeat(data, 2, axis=1)
    data = data[:, :2]
    if src_rate != dst_rate and len(data):
        n = max(1, int(round(len(data) * dst_rate / src_rate)))
        x = np.linspace(0, len(data) - 1, n)
        data = np.stack([np.interp(x, np.arange(len(data)), data[:, c]) for c in range(2)], axis=1)
    return data.astype("float32")

def run_pyaudiowpatch(sr, out):
    import numpy as np
    import pyaudiowpatch as pa
    p = pa.PyAudio()
    wasapi = p.get_host_api_info_by_type(pa.paWASAPI)
    spk = p.get_device_info_by_index(wasapi["defaultOutputDevice"])
    if not spk.get("isLoopbackDevice"):
        spk = next((lb for lb in p.get_loopback_device_info_generator() if spk["name"] in lb["name"]), None)
        if spk is None: raise RuntimeError("no loopback device for your speakers")
    rate, ch = int(spk["defaultSampleRate"]), max(1, int(spk["maxInputChannels"]))
    frames = rate // 10
    st = p.open(format=pa.paFloat32, channels=ch, rate=rate, input=True, input_device_index=spk["index"], frames_per_buffer=frames)
    out.write(b"OK\n"); out.flush()
    buf = np.zeros((0, 2), dtype="float32"); need = sr // 10
    while True:
        raw = st.read(frames, exception_on_overflow=False)
        data = np.frombuffer(raw, dtype=np.float32).reshape(-1, ch)
        buf = np.concatenate([buf, _to_stereo_rate(np, data, rate, sr)])
        while len(buf) >= need:
            out.write(buf[:need].tobytes()); buf = buf[need:]
        out.flush()

def run_soundcard(sr, out):
    import numpy as np, soundcard as sc
    spk = sc.default_speaker()
    mic = sc.get_microphone(id=str(spk.name), include_loopback=True)
    with mic.recorder(samplerate=sr, channels=2) as rec:
        out.write(b"OK\n"); out.flush()
        while True:
            out.write(_to_stereo_rate(np, rec.record(numframes=sr // 10), sr, sr).tobytes()); out.flush()

def main():
    _quiet_crashes()
    sr = int(sys.argv[1]) if len(sys.argv) > 1 else 48000
    warnings.filterwarnings("ignore")                       # "data discontinuity" spam: harmless gaps
    out = sys.stdout.buffer
    errors = []
    for backend in (run_pyaudiowpatch, run_soundcard):
        try: return backend(sr, out)
        except (BrokenPipeError, KeyboardInterrupt): return
        except Exception as e: errors.append(f"{backend.__name__}: {e}")
    sys.stderr.write("; ".join(errors)); sys.exit(2)

if __name__ == "__main__":
    try: main()
    except (BrokenPipeError, KeyboardInterrupt): pass
