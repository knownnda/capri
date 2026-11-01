"""
Turns lore/scene.mp3 into lore/lore_from_scene.txt (a draft bio from the scene audio; the real lore is lore/lore.txt), all locally.
Run once:  python transcribe_lore.py     (needs: pip install faster-whisper, and Ollama running)
Then restart server.py. When anyone asks "who are you?", she answers from lore.txt.
"""
import os, requests
from faster_whisper import WhisperModel

HERE = os.path.dirname(os.path.abspath(__file__))
MP3 = os.path.join(HERE, "lore", "scene.mp3")
MODEL = os.environ.get("CAPRI_MODEL", "llama3.1:8b")

print("transcribing (first run downloads a small speech model)...")
segs, _ = WhisperModel("small", compute_type="int8").transcribe(MP3, language="en")
text = " ".join(s.text.strip() for s in segs)
open(os.path.join(HERE, "lore", "transcript.txt"), "w", encoding="utf-8").write(text)

print("writing her bio...")
prompt = ("Below is a transcript of a scene from Cyberpunk: Edgerunners involving Capri. Write a short first-person bio for Capri "
          "(max 150 words): who she is, personality, how she talks, who she's connected to, and anything else the scene reveals. "
          "Only use facts from the transcript. Do not invent details.\n\nTRANSCRIPT:\n" + text[:12000])
r = requests.post("http://127.0.0.1:11434/api/chat", json={"model": MODEL, "stream": False,
                  "messages": [{"role": "user", "content": prompt}]}, timeout=300)
bio = r.json()["message"]["content"]
open(os.path.join(HERE, "lore", "lore_from_scene.txt"), "w", encoding="utf-8").write(bio)
print("\n--- lore.txt ---\n" + bio + "\n\nEdit lore/lore.txt by hand if she got anything wrong, then restart server.py.")
