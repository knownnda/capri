"""
Bring your own AI. Capri's brain can be local Ollama, or any API you add in providers.json:
  type "ollama"     -> your local Ollama (default)
  type "openai"     -> anything OpenAI-compatible: OpenAI, Groq, OpenRouter, Together, Mistral, LM Studio, vLLM, DeepSeek...
  type "anthropic"  -> Anthropic's Claude API
Keys can be written in the file ("api_key") or read from an environment variable ("api_key_env").
"""
import json, os
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
FILE = os.path.join(HERE, "providers.json")
_DEFAULT = [{"name": "local", "type": "ollama", "model": "auto"}]
_state = {"providers": list(_DEFAULT), "active": "local"}

def load():
    try:
        with open(FILE, encoding="utf-8") as f: d = json.load(f)
        provs = [p for p in (d.get("providers") or []) if isinstance(p, dict) and p.get("name")]
        if provs:
            _state["providers"] = provs
            _state["active"] = d.get("active") if any(p["name"] == d.get("active") for p in provs) else provs[0]["name"]
    except Exception:
        pass
    return _state

def providers(): return _state["providers"]
def active_name(): return _state["active"]

def provider():
    for p in _state["providers"]:
        if p["name"].lower() == _state["active"].lower(): return p
    return _state["providers"][0]

def set_active(name):
    """Switch brain by (part of) a provider's name. Returns the provider name or None."""
    n = (name or "").strip().lower()
    hit = next((p for p in _state["providers"] if p["name"].lower() == n), None) or \
          next((p for p in _state["providers"] if n and n in p["name"].lower()), None)
    if not hit: return None
    _state["active"] = hit["name"]
    try: _write(FILE, {"active": hit["name"], "providers": _state["providers"]})
    except Exception: pass
    return hit["name"]

def _key(p):
    k = p.get("api_key") or ""
    if not k or "PUT_YOUR" in k: k = os.environ.get(p.get("api_key_env") or "", "")
    return k

# =====================================================================  API keys from the right-click menu (API KEYS)
# Keys are saved ONLY on this PC, in providers.json (AI brains) and voice_api.json (API voice). Both are git-ignored.
# The menu never gets a key back, only a hint like "sk-...9f2a".
EXAMPLE = os.path.join(HERE, "providers.example.json")
VOICE_FILE = os.path.join(HERE, "voice_api.json")
VOICE_EXAMPLE = os.path.join(HERE, "voice_api.example.json")
SLOTS = {   # menu slot -> where the key goes
    "openai":     {"label": "OpenAI",     "brain": "openai",     "voice": "openai",     "check": ("openai", "https://api.openai.com/v1")},
    "groq":       {"label": "Groq",       "brain": "groq",       "check": ("openai", "https://api.groq.com/openai/v1")},
    "openrouter": {"label": "OpenRouter", "brain": "openrouter", "check": ("openai", "https://openrouter.ai/api/v1")},
    "claude":     {"label": "Claude",     "brain": "claude",     "check": ("anthropic", "https://api.anthropic.com")},
    "elevenlabs": {"label": "ElevenLabs", "voice": "elevenlabs", "check": ("elevenlabs", "https://api.elevenlabs.io")},
}

def _read(path, fallback):
    for f in (path, fallback):
        try:
            with open(f, encoding="utf-8") as fh: return json.load(fh)
        except Exception: pass
    return {}

def _write(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(data, f, indent=2)
    os.replace(tmp, path)

def hint(k):
    k = k or ""
    if not k or "PUT_YOUR" in k: return ""
    return (k[:3] + "..." + k[-4:]) if len(k) > 10 else "saved"

def keys_status():
    """What the API KEYS menu shows: which slots have a key (as a hint), the active brain, the API voice setup."""
    load(); v = _read(VOICE_FILE, VOICE_EXAMPLE)
    out = {"active": active_name(), "slots": [], "brains": [{"name": p["name"], "type": p.get("type", "ollama"), "model": p.get("model", ""),
                                                              "ready": p.get("type", "ollama") == "ollama" or bool(_key(p))} for p in providers()],
           "voice_active": v.get("active", "openai"), "voice_id": (v.get("elevenlabs") or {}).get("voice_id", "")}
    if "PUT_A_VOICE" in out["voice_id"]: out["voice_id"] = ""
    for slot, d in SLOTS.items():
        k = ""
        if d.get("brain"):
            p = next((p for p in providers() if p["name"] == d["brain"]), None)
            if p: k = _key(p)
        if not k and d.get("voice"):
            vp = v.get(d["voice"]) or {}
            k = vp.get("api_key") or os.environ.get(vp.get("api_key_env") or "", "")
        out["slots"].append({"slot": slot, "label": d["label"], "hint": hint(k), "brain": bool(d.get("brain")), "voice": bool(d.get("voice"))})
    return out

def check_key(slot, key):
    """Quick 'does this key work?' call (lists models / account). Returns 'ok', 'rejected' or 'unchecked'."""
    kind, base = SLOTS[slot]["check"]
    try:
        if kind == "openai": r = requests.get(base + "/models", headers={"Authorization": "Bearer " + key}, timeout=8)
        elif kind == "anthropic": r = requests.get(base + "/v1/models", headers={"x-api-key": key, "anthropic-version": "2023-06-01"}, timeout=8)
        else: r = requests.get(base + "/v1/voices", headers={"xi-api-key": key}, timeout=8)
        if r.status_code in (401, 403): return "rejected"
        return "ok" if r.status_code < 400 else "unchecked"
    except Exception:
        return "unchecked"

def save_key(slot, key, voice_id=None):
    """Store (key="" clears) a key for a menu slot. Returns {'ok', 'check', 'msg'}."""
    if slot not in SLOTS: return {"ok": False, "msg": "unknown service"}
    key = (key or "").strip(); d = SLOTS[slot]
    if key and (len(key) < 12 or " " in key): return {"ok": False, "msg": "that doesn't look like an API key"}
    if d.get("brain"):
        data = _read(FILE, EXAMPLE); provs = data.get("providers") or [dict(x) for x in _DEFAULT]
        p = next((p for p in provs if p.get("name") == d["brain"]), None)
        if p is None:
            ex = next((x for x in _read(EXAMPLE, EXAMPLE).get("providers", []) if x.get("name") == d["brain"]), None)
            if ex: p = dict(ex); provs.append(p)
        if p is not None:
            if key: p["api_key"] = key
            else: p.pop("api_key", None)
        active = data.get("active") or "local"
        if not key and active == d["brain"]: active = "local"                   # cleared the key of the brain in use: back to local
        _write(FILE, {"active": active, "providers": provs})
        _state["active"] = active
    if d.get("voice"):
        v = _read(VOICE_FILE, VOICE_EXAMPLE); vp = dict(v.get(d["voice"]) or {"type": d["voice"]})
        if key: vp["api_key"] = key
        else: vp.pop("api_key", None)
        if voice_id is not None and d["voice"] == "elevenlabs": vp["voice_id"] = voice_id.strip()
        v[d["voice"]] = vp
        if key and (slot == "elevenlabs" or not v.get("active")): v["active"] = d["voice"]
        v.pop("_help", None); _write(VOICE_FILE, v)
    load()
    if not key: return {"ok": True, "check": "", "msg": f"{d['label']} key removed"}
    c = check_key(slot, key)
    return {"ok": True, "check": c, "msg": {"ok": f"{d['label']} key saved and working", "rejected": f"saved, but {d['label']} rejected that key: double-check it",
                                              "unchecked": f"{d['label']} key saved (couldn't test it right now)"}[c]}

def set_voice_service(name):
    v = _read(VOICE_FILE, VOICE_EXAMPLE)
    if name in ("openai", "elevenlabs"): v["active"] = name; v.pop("_help", None); _write(VOICE_FILE, v)
    return v.get("active")

def _openai_msgs(messages):
    out = []
    for m in messages:
        imgs = m.get("images")
        if imgs:
            out.append({"role": m["role"], "content": [{"type": "text", "text": m["content"]}] +
                        [{"type": "image_url", "image_url": {"url": "data:image/png;base64," + i}} for i in imgs]})
        else:
            out.append({"role": m["role"], "content": m["content"]})
    return out

def _check(r, p):
    if r.status_code >= 400:
        raise RuntimeError(f"{p['name']} said HTTP {r.status_code}: {r.text[:200]}")

def openai_stream(p, messages, max_tokens=300, json_mode=None):
    base = (p.get("base_url") or "https://api.openai.com/v1").rstrip("/")
    body = {"model": p["model"], "messages": _openai_msgs(messages), "stream": True,
            "max_tokens": max_tokens, "temperature": p.get("temperature", 0.7)}
    if (p.get("json_mode", True) if json_mode is None else json_mode): body["response_format"] = {"type": "json_object"}
    hdr = {"Authorization": "Bearer " + _key(p), "Content-Type": "application/json"}; hdr.update(p.get("headers") or {})
    with requests.post(base + "/chat/completions", json=body, headers=hdr, stream=True, timeout=120) as r:
        _check(r, p)
        for line in r.iter_lines():
            if not line: continue
            line = line.decode("utf-8", "ignore")
            if not line.startswith("data:"): continue
            d = line[5:].strip()
            if d == "[DONE]": break
            try: delta = json.loads(d)["choices"][0]["delta"].get("content") or ""
            except Exception: continue
            if delta: yield delta

def anthropic_stream(p, messages, max_tokens=300):
    base = (p.get("base_url") or "https://api.anthropic.com").rstrip("/")
    system = "\n".join(m["content"] for m in messages if m["role"] == "system")
    msgs = []
    for m in messages:
        if m["role"] == "system": continue
        imgs = m.get("images")
        content = m["content"] if not imgs else [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": i}} for i in imgs] + [{"type": "text", "text": m["content"]}]
        msgs.append({"role": m["role"], "content": content})
    while msgs and msgs[0]["role"] != "user": msgs.pop(0)          # Claude wants the first message to be the user's
    body = {"model": p["model"], "max_tokens": max_tokens, "system": system, "messages": msgs, "stream": True}
    hdr = {"x-api-key": _key(p), "anthropic-version": "2023-06-01", "content-type": "application/json"}
    with requests.post(base + "/v1/messages", json=body, headers=hdr, stream=True, timeout=120) as r:
        _check(r, p)
        for line in r.iter_lines():
            if not line: continue
            line = line.decode("utf-8", "ignore")
            if not line.startswith("data:"): continue
            try: j = json.loads(line[5:].strip())
            except Exception: continue
            if j.get("type") == "content_block_delta" and j.get("delta", {}).get("type") == "text_delta":
                yield j["delta"].get("text", "")

def stream(messages, max_tokens=300, json_mode=None):
    p = provider(); t = p.get("type", "ollama")
    if t == "openai": return openai_stream(p, messages, max_tokens, json_mode)
    if t == "anthropic": return anthropic_stream(p, messages, max_tokens)
    raise ValueError("not an API provider")

def chat(messages, max_tokens=1500):
    return "".join(stream(messages, max_tokens))

def is_api(): return provider().get("type", "ollama") in ("openai", "anthropic")
def supports_vision(): return bool(provider().get("vision"))
