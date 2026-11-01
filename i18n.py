"""
Capri's languages. The installer's language (or right-click > SYSTEM > LANGUAGE) decides what she speaks:
  - the AI brain is told to always answer in that language (she keeps her slang: choom, preem, delta...)
  - her instant canned lines are translated once by the brain and cached in capri_translations.json
  - speech recognition switches to a multilingual Whisper model, and Piper TTS to a voice for that language
server.py calls init(chat=..., log=...) once at startup.
"""
import json, re, threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE_FILE = HERE / "capri_translations.json"
ctx = {}
def init(**kw): ctx.update(kw)
def _log(m):
    try: ctx["log"](m)
    except Exception: pass

# code -> (English name, native name, Piper voice candidates (first that downloads wins), extra wake-word greetings)
LANGS = {
    "en": ("English", "English", [], []),
    "fr": ("French", "Français", ["fr_FR-siwis-medium", "fr_FR-siwis-low", "fr_FR-upmc-medium"], ["salut", "coucou", "allo"]),
    "de": ("German", "Deutsch", ["de_DE-eva_k-x_low", "de_DE-kerstin-low", "de_DE-thorsten-medium"], ["hallo", "hei"]),
    "es": ("Spanish", "Español", ["es_MX-claude-high", "es_ES-sharvard-medium", "es_ES-davefx-medium"], ["hola", "oye"]),
    "it": ("Italian", "Italiano", ["it_IT-paola-medium", "it_IT-riccardo-x_low"], ["ciao", "ehi"]),
    "pt": ("Portuguese", "Português", ["pt_BR-faber-medium", "pt_PT-tugão-medium"], ["oi", "olá", "ola"]),
    "nl": ("Dutch", "Nederlands", ["nl_BE-nathalie-medium", "nl_BE-nathalie-x_low", "nl_NL-mls-medium"], ["hoi", "hallo"]),
    "pl": ("Polish", "Polski", ["pl_PL-gosia-medium", "pl_PL-darkman-medium"], ["hej", "cześć"]),
    "ru": ("Russian", "Русский", ["ru_RU-irina-medium", "ru_RU-dmitri-medium"], ["привет", "эй"]),
    "tr": ("Turkish", "Türkçe", ["tr_TR-dfki-medium", "tr_TR-fettah-medium"], ["merhaba", "hey"]),
    "uk": ("Ukrainian", "Українська", ["uk_UA-lada-x_low", "uk_UA-ukrainian_tts-medium"], ["привіт", "агов"]),
    "ja": ("Japanese", "日本語", [], ["ねえ", "おい"]),
    "ar": ("Arabic", "العربية", ["ar_JO-kareem-medium", "ar_JO-kareem-low"], ["مرحبا", "يا"]),
    "zh": ("Chinese (Mandarin)", "中文", ["zh_CN-huayan-medium", "zh_CN-huayan-x_low"], ["你好", "嘿"]),
    "ko": ("Korean", "한국어", [], ["안녕", "야"]),
    "hi": ("Hindi", "हिन्दी", [], ["नमस्ते", "अरे"]),
}
# small models handle these much better with Qwen than with Llama
PREFERS_QWEN = {"ja", "zh", "ko", "ar", "hi"}

def code():
    try:
        import modes
        c = (modes.S.get("language") or "en").lower()
    except Exception:
        c = "en"
    return c if c in LANGS else "en"

def name(c=None): return LANGS.get(c or code(), LANGS["en"])[0]
def is_en(): return code() == "en"

def reply_rule():
    """Added to every system prompt. Empty for English."""
    if is_en(): return ""
    n = name()
    return (f"\n\nLANGUAGE: The user speaks {n}. ALWAYS write your reply (the \"say\" text) in natural, casual {n}, even if they write in English. "
            f"Keep your Edgerunners slang words (choom, preem, delta, gonk, nova, eddies) as they are, mixed into the {n}. "
            "Tool names, JSON keys, song titles, artist names, file names and search queries stay exactly as the user said them.")

# ---------------------------------------------------------------- speech recognition
def whisper_lang():
    """Language passed to faster-whisper (None = auto-detect). CAPRI_LANG still overrides."""
    import os
    env = os.environ.get("CAPRI_LANG")
    if env: return None if env == "auto" else env
    return code()

def whisper_model(base):
    """'small.en' -> 'small' for anything but English (the .en models only understand English)."""
    lang = whisper_lang()
    if lang == "en": return base
    return base[:-3] if base.endswith(".en") else base

def stt_hint(english_hint):
    return english_hint if whisper_lang() == "en" else "Capri."

def wake_prefixes():
    return set(LANGS.get(code(), LANGS["en"])[3])

# her name the way Whisper writes it in non-Latin scripts
NATIVE_NAMES = {"ru": ["капри"], "uk": ["капрі", "капри"], "ja": ["カプリ", "かぷり"], "zh": ["卡普里", "卡布里", "卡皮"], "ko": ["카프리", "까프리"],
                "ar": ["كابري", "كابرى"], "hi": ["कैप्री", "काप्री", "कप्री"]}
def native_names(): return NATIVE_NAMES.get(code(), [])

_ALIASES = {"english": "en", "anglais": "en", "inglés": "en", "ingles": "en", "englisch": "en", "inglese": "en", "french": "fr", "francais": "fr", "français": "fr",
            "german": "de", "deutsch": "de", "allemand": "de", "spanish": "es", "español": "es", "espanol": "es", "castellano": "es", "italian": "it", "italiano": "it",
            "portuguese": "pt", "português": "pt", "portugues": "pt", "brazilian": "pt", "dutch": "nl", "nederlands": "nl", "polish": "pl", "polski": "pl",
            "russian": "ru", "русский": "ru", "turkish": "tr", "türkçe": "tr", "turkce": "tr", "ukrainian": "uk", "українська": "uk", "japanese": "ja", "日本語": "ja",
            "arabic": "ar", "العربية": "ar", "chinese": "zh", "mandarin": "zh", "中文": "zh", "korean": "ko", "한국어": "ko", "hindi": "hi", "हिन्दी": "hi"}
def match_language(word):
    w = (word or "").strip().lower()
    if w in LANGS: return w
    return _ALIASES.get(w)

LANG_CMD = re.compile(r"^\s*(?:hey\s+)?(?:capri[, ]+)?(?:please\s+)?(?:(?:speak|talk|reply|answer|chat)(?:\s+to\s+me)?\s+(?:in\s+)?|(?:switch|change|set)\s+(?:your\s+|the\s+)?language\s+to\s+|(?:switch|change)\s+to\s+)([^\s.!?]+)(?:\s+(?:please|now|from now on))*\s*[.!?]?\s*$", re.I)
def language_command(text):
    """'speak french' / 'change your language to german' / 'switch to spanish' -> 'fr' / 'de' / 'es' (None if it isn't one)."""
    m = LANG_CMD.match(text or "")
    return match_language(m.group(1)) if m else None

# ---------------------------------------------------------------- text to speech
def piper_voices():
    return list(LANGS.get(code(), LANGS["en"])[2])

# ---------------------------------------------------------------- translating her canned lines
_cache = None
_clock = threading.Lock()
def _load_cache():
    global _cache
    if _cache is None:
        try: _cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception: _cache = {}
    return _cache

def _save_cache():
    try: CACHE_FILE.write_text(json.dumps(_cache, ensure_ascii=False, indent=0), encoding="utf-8")
    except Exception as e: _log(f"translation cache save failed: {e}")

def _translate_many(lines, lang):
    """One brain call for many lines. Returns {english: translated}."""
    numbered = "\n".join(f"{i + 1}. {l}" for i, l in enumerate(lines))
    out = ctx["chat"]([
        {"role": "system", "content": f"Translate each numbered line into casual spoken {name(lang)}. The speaker is CAPRI, a cocky, teasing Cyberpunk Edgerunners AI personality. "
                                      "Keep slang words like choom, preem, delta, nova, gonk, eddies untranslated. Keep song titles, game names, app names, numbers and file names unchanged. "
                                      "Answer with the same numbering, one line each, and nothing else."},
        {"role": "user", "content": numbered}], {"num_ctx": 4096, "num_predict": 60 * len(lines) + 80, "temperature": 0.2})
    res = {}
    for line in out.splitlines():
        m = re.match(r"^\s*(\d+)[\.\)]\s*(.+)$", line)
        if m and 1 <= int(m.group(1)) <= len(lines): res[lines[int(m.group(1)) - 1]] = m.group(2).strip().strip('"')
    return res

def tr(text, cache=True):
    """English text -> the user's language. Instant for anything already in the cache; otherwise one quick brain call."""
    if not text or is_en() or "chat" not in ctx: return text
    lang = code()
    with _clock:
        c = _load_cache().setdefault(lang, {})
        if text in c: return c[text]
    try:
        hit = _translate_many([text], lang).get(text)
    except Exception as e:
        _log(f"translate failed: {e}"); return text
    if not hit: return text
    if cache and len(text) < 160:
        with _clock: _load_cache().setdefault(lang, {})[text] = hit; _save_cache()
    return hit

def prewarm(lines):
    """Translate all of her fixed lines in the background (once per language) so they stay instant."""
    if is_en() or "chat" not in ctx: return
    lang = code()
    def run():
        with _clock: have = _load_cache().setdefault(lang, {})
        todo = [l for l in dict.fromkeys(lines) if l and l not in have]
        for i in range(0, len(todo), 12):
            try:
                got = _translate_many(todo[i:i + 12], lang)
                with _clock: _load_cache().setdefault(lang, {}).update(got); _save_cache()
            except Exception as e:
                _log(f"prewarm translations failed: {e}"); return
        if todo: _log(f"translated {len(todo)} lines into {name(lang)}")
    threading.Thread(target=run, daemon=True, name="i18n_prewarm").start()
