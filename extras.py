"""
Capri's extra brains: reminders/timers that ring you, long-term memory, research, safe file creating/editing, and mood pop-ups.
server.py hands us what we need through init(): ctx["chat"](messages, opts) -> str, ctx["open_url"](url), ctx["events"], ctx["show"](), ctx["log"](msg)
"""
import difflib, html, json, os, random, re, shutil, subprocess, threading, time, urllib.parse
from pathlib import Path
import requests

HERE = Path(__file__).resolve().parent
ctx = {}
def init(**kw): ctx.update(kw)
def _log(m):
    try: ctx["log"](m)
    except Exception: pass

def _read_json(p, default):
    try: return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception: return default
def _write_json(p, data):
    try: Path(p).write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    except Exception as e: _log(f"write {p} failed: {e}")

# =====================================================================  reminders / timers
REM_FILE = HERE / "reminders.json"
REMS = _read_json(REM_FILE, [])
_NUMS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
         "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "forty-five": 45, "forty five": 45, "fifty": 50, "sixty": 60, "ninety": 90}
_NUMRE = r"(\d+(?:\.\d+)?|" + "|".join(sorted((re.escape(k) for k in _NUMS), key=len, reverse=True)) + r")"
DUR = re.compile(r"(?:(half an?|a quarter of an?)\s*(hour|minute)|" + _NUMRE + r"\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?|hr|h|m|s)\b)", re.I)
_UNIT = {"s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1, "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60, "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600}

def _dur_seconds(m):
    if m.group(1):
        base = 3600 if m.group(2).lower() == "hour" else 60
        return base * (0.5 if m.group(1).lower().startswith("half") else 0.25)
    n = m.group(3).lower(); n = float(_NUMS[n]) if n in _NUMS else float(n)
    return n * _UNIT[m.group(4).lower()]

def _label(sec):
    sec = int(round(sec))
    if sec % 3600 == 0 and sec >= 3600: h = sec // 3600; return f"{h} hour{'s' if h != 1 else ''}"
    if sec >= 120 or sec % 60 == 0 and sec >= 60: m = round(sec / 60); return f"{m} minute{'s' if m != 1 else ''}"
    return f"{sec} second{'s' if sec != 1 else ''}"

def parse_reminder(text):
    """'set a timer for 10 mins' / 'remind me to call mom in 10 minutes' / 'call me in 5 minutes' -> {seconds, text, kind}"""
    t = text.strip()
    low = t.lower()
    m = DUR.search(t)
    is_timer = re.search(r"\btimer\b", low) is not None
    wants = re.search(r"\b(remind me|reminder|call me|ring me|phone me|ping me|wake me|alarm|set a timer|start a timer|timer)\b", low)
    if not wants: return None
    if m:
        sec = _dur_seconds(m)
        rest = (t[:m.start()] + " " + t[m.end():])
    else:
        at = re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", low)
        if not at or not re.search(r"remind me|call me|ring me|alarm", low): return None
        h, mi, ap = int(at.group(1)), int(at.group(2) or 0), at.group(3)
        if ap == "pm" and h < 12: h += 12
        if ap == "am" and h == 12: h = 0
        now = time.localtime(); due = time.mktime((now.tm_year, now.tm_mon, now.tm_mday, h % 24, mi, 0, 0, 0, -1))
        if due <= time.time(): due += 86400
        sec = due - time.time(); rest = t[:at.start()] + " " + t[at.end():]
    rest = re.sub(r"\b(in|for|after|within|from now|please|hey|capri|set|start|make|a|an|the|timer|remind me|reminder|call me|ring me|phone me|ping me|wake me|alarm|can you|could you|to|about|that|of|me)\b", " ", rest, flags=re.I) if is_timer else \
           re.sub(r"\b(please|hey capri|capri|can you|could you|remind me|call me|ring me|phone me|ping me|wake me|set a reminder|reminder|in|from now|after)\b", " ", rest, flags=re.I)
    rest = re.sub(r"^\s*(to|about|that|for)\s+", "", re.sub(r"\s+", " ", rest).strip(" ,.!?"), flags=re.I).strip(" ,.!?")
    if is_timer and not re.search(r"remind me", low): return {"seconds": sec, "text": "", "kind": "timer"}
    return {"seconds": sec, "text": rest, "kind": "reminder" if rest else "timer"}

def fire_text(r):
    if r["kind"] == "timer": return f"Time's up, choom. Your {r.get('label', 'timer')} timer is done."
    return f"Hey choom, it's time: {r['text']}."

def add_reminder(seconds, text="", kind=None):
    seconds = max(1, float(seconds)); kind = kind or ("reminder" if text else "timer")
    r = {"id": int(time.time() * 1000) % 10**9, "due": time.time() + seconds, "text": text.strip(), "kind": kind, "label": _label(seconds), "total": seconds}
    REMS.append(r); _write_json(REM_FILE, REMS)
    return r

def clear_reminders():
    n = len(REMS); REMS.clear(); _write_json(REM_FILE, REMS); return n

def list_reminders():
    if not REMS: return "nothing on the clock, choom"
    out = []
    for r in sorted(REMS, key=lambda x: x["due"]):
        left = max(0, r["due"] - time.time())
        out.append(f"{(r['text'] or r['kind'])} in {_label(left) if left >= 1 else 'a moment'}")
    return "; ".join(out)

def remind(minutes=1, text=""):
    r = add_reminder(float(minutes) * 60, str(text or ""))
    return f"will ring you in {r['label']}" + (f" about: {r['text']}" if r["text"] else "")

def timer(minutes=1):
    r = add_reminder(float(minutes) * 60, "", "timer"); return f"{r['label']} timer started"

def reminder_loop():
    """Runs in the background (even when the window is hidden in the tray) and rings you when something is due."""
    while True:
        time.sleep(2)
        now = time.time()
        for r in [x for x in REMS if x["due"] <= now]:
            REMS.remove(r); _write_json(REM_FILE, REMS)
            late = now - r["due"] > 90
            phrase = fire_text(r) + (" (sorry, I was asleep.)" if late else "")
            ctx["events"].append({"type": "incoming", "reason": phrase, "kind": r["kind"], "text": r["text"]})
            try: ctx["show"]()
            except Exception: pass

def handle_reminder_text(user_text):
    """Deterministic handling of timers/reminders (no LLM needed). Returns her reply or None."""
    low = user_text.lower()
    if re.search(r"\b(cancel|clear|stop|delete|remove)\b.*\b(timers?|reminders?|alarms?)\b", low):
        return f"Wiped {clear_reminders()} of them, choom."
    if re.search(r"\b(what|which|any|list|show)\b.*\b(timers?|reminders?)\b", low) and "remind me" not in low:
        return "On the clock: " + list_reminders() + "."
    p = parse_reminder(user_text)
    if not p: return None
    r = add_reminder(p["seconds"], p["text"], p["kind"])
    if r["kind"] == "timer": return f"Timer's running, choom: {r['label']}. I'll call you when it's up."
    return f"Done. I'll ring you in {r['label']} to remind you: {r['text']}."

# =====================================================================  long-term memory
MEM_FILE = HERE / "capri_memory.json"
MEM = _read_json(MEM_FILE, [])
_STOP = set("a an the is are was were my your i me you it its of to in on at for and or but with that this what whats which who do does did have has had be been am im i'm you're tell about know remember favorite favourite fav".split())

def remember(fact):
    fact = re.sub(r"\s+", " ", str(fact)).strip(" .")
    if len(fact) < 3: return "tell me what to remember, choom"
    if any(m["t"].lower() == fact.lower() for m in MEM): return "I already knew that"
    MEM.append({"t": fact, "ts": int(time.time())}); _write_json(MEM_FILE, MEM)
    return f"locked in: {fact}"

def forget(text):
    words = [w for w in re.findall(r"[a-z0-9']+", str(text).lower()) if w not in _STOP]
    gone = [m for m in MEM if words and all(w in m["t"].lower() for w in words)] or [m for m in MEM if words and any(w in m["t"].lower() for w in words)][:1]
    for m in gone: MEM.remove(m)
    _write_json(MEM_FILE, MEM)
    return f"forgot {len(gone)} thing{'s' if len(gone) != 1 else ''}" if gone else "I don't remember anything like that"

def what_i_know():
    return "; ".join(m["t"] for m in MEM[-25:]) if MEM else "nothing yet, choom. Tell me stuff."

def memory_context(user_text, limit=8):
    if not MEM: return ""
    q = {w for w in re.findall(r"[a-z0-9']+", user_text.lower()) if w not in _STOP}
    scored = []
    for i, m in enumerate(MEM):
        toks = set(re.findall(r"[a-z0-9']+", m["t"].lower()))
        scored.append((len(q & toks) * 3 + (i / max(1, len(MEM))), m["t"]))
    scored.sort(reverse=True)
    picks = [t for s, t in scored[:limit]]
    return "Things you know about the user from before (use them naturally, don't recite them):\n- " + "\n- ".join(picks)

_LEARN = [
    (r"\bmy (?:fav(?:ou?rite)?)\s+([a-z ]{2,30}?)\s+(?:is|are|was)\s+(.+)", lambda m: f"favorite {m.group(1).strip()}: {m.group(2).strip()}"),
    (r"\bmy name(?:'s| is)\s+([A-Za-z][\w-]*)", lambda m: f"name is {m.group(1)}"),
    (r"\bcall me\s+([A-Za-z][\w-]*)\s*$", lambda m: f"likes to be called {m.group(1)}"),
    (r"\bi(?:'m| am)\s+(\d{1,2})(?:\s+years?\s+old)?\b", lambda m: f"is {m.group(1)} years old"),
    (r"\bi live in\s+(.+)", lambda m: f"lives in {m.group(1).strip()}"),
    (r"\bi(?:'m| am) from\s+(.+)", lambda m: f"is from {m.group(1).strip()}"),
    (r"\bi (?:really |absolutely )?(love|like|enjoy|hate|dislike|prefer)\s+(.+)", lambda m: f"{m.group(1)}s {m.group(2).strip()}"),
    (r"\bi (?:work|study)\s+(?:at|as|for|in)\s+(.+)", lambda m: f"works/studies at {m.group(1).strip()}"),
    (r"\bi go to\s+(.+)", lambda m: f"goes to {m.group(1).strip()}"),
    (r"\bmy ([a-z]+) (?:is|are) (?:called|named)\s+([A-Za-z][\w -]*)", lambda m: f"their {m.group(1)} is called {m.group(2).strip()}"),
    (r"\bi have (?:a|an)\s+(.+)", lambda m: f"has a {m.group(1).strip()}"),
]
def learn_from(user_text):
    t = user_text.strip()
    if len(t) > 220 or "?" in t: return
    m = re.match(r"^(?:hey capri[, ]*)?(?:please )?remember(?: that)?\s+(.+)", t, re.I)
    if m: remember(m.group(1)); return
    for sentence in re.split(r"(?<=[.!])\s+| and (?=i |my )", t):
        for pat, fmt in _LEARN:
            mm = re.search(pat, sentence.strip(" .!"), re.I)
            if mm:
                fact = fmt(mm)
                if len(fact) <= 90: remember(fact)
                break

def handle_memory_text(user_text):
    t = user_text.strip()
    m = re.match(r"^(?:hey capri[, ]*)?(?:please )?remember(?: that)?\s+(.+)", t, re.I)
    if m: return remember(m.group(1)).replace("locked in:", "Got it, locked in:")
    m = re.match(r"^(?:hey capri[, ]*)?(?:please )?forget(?: about| that)?\s+(.+)", t, re.I)
    if m: return forget(m.group(1)).capitalize() + "."
    if re.search(r"\bwhat (?:do|did) you (?:know|remember) about me\b|\bwhat have i told you\b", t, re.I):
        return "Here's what I've got on you: " + what_i_know() + "."
    return None

# =====================================================================  research
UA = {"User-Agent": "CapriDesktop/1.0 (personal local assistant)"}
def _wiki_title(q):
    r = requests.get("https://en.wikipedia.org/w/api.php", params={"action": "opensearch", "search": q, "limit": 1, "format": "json"}, headers=UA, timeout=10).json()
    return r[1][0] if len(r) > 1 and r[1] else None
def _wiki_extract(title):
    r = requests.get("https://en.wikipedia.org/w/api.php", params={"action": "query", "prop": "extracts", "explaintext": 1, "exchars": 3000, "redirects": 1, "titles": title, "format": "json"}, headers=UA, timeout=10).json()
    return next(iter(r["query"]["pages"].values())).get("extract", "")
def _ddg(q):
    page = requests.post("https://html.duckduckgo.com/html/", data={"q": q}, headers=UA, timeout=10).text
    out = []
    for href, title, snip in re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</a>', page, re.S)[:5]:
        m = re.search(r"uddg=([^&]+)", href); url = urllib.parse.unquote(m.group(1)) if m else href
        clean = lambda s: html.unescape(re.sub(r"<[^>]+>", "", s)).strip()
        out.append({"title": clean(title), "url": url, "snippet": clean(snip)})
    return out

def clean_topic(t):
    t = re.sub(r"^(?:please\s+)?(?:deep\s+)?(?:research|look up|look into|search up|find out about|find info on|tell me about|learn about)\s+", "", t.strip(), flags=re.I)
    return re.sub(r"^(?:about|on|into)\s+", "", t, flags=re.I).strip(" ?.!")

def research(topic):
    topic = clean_topic(topic) or topic
    src, page_url, title = [], None, None
    try:
        title = _wiki_title(topic)
        if title:
            ext = _wiki_extract(title)
            if ext: src.append("WIKIPEDIA: " + ext[:2800]); page_url = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
    except Exception as e: _log(f"wiki failed: {e}")
    web = []
    try: web = _ddg(topic)
    except Exception as e: _log(f"ddg failed: {e}")
    for w in web[:4]: src.append(f"WEB ({w['title']}): {w['snippet']}")
    if not src: return f"I couldn't reach anything on {topic} (no internet?)"
    if page_url is None and web: page_url = web[0]["url"]
    try: ctx["open_url"](page_url or "https://duckduckgo.com/?q=" + urllib.parse.quote(topic))
    except Exception: pass
    facts = ctx["chat"]([
        {"role": "system", "content": "You write key facts. Use ONLY the sources given. Output exactly 5 short bullet points, each starting with '- ', each one concrete fact (dates, places, numbers, names). No intro, no outro."},
        {"role": "user", "content": f"TOPIC: {title or topic}\n\n" + "\n\n".join(src)[:6500]}], {"num_ctx": 4096, "num_predict": 380, "temperature": 0.2}).strip()
    facts = re.sub(r"^\s*[\*\u2022]\s*", "- ", facts, flags=re.M)
    return f"Here's the rundown on {title or topic} (pulled up the page for you):\n{facts}"

# =====================================================================  files: create / edit / undo
HOME = Path.home()
TEXT_EXT = {".txt", ".md", ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".htm", ".css", ".json", ".csv", ".java", ".c", ".cpp", ".h", ".cs", ".go", ".rs", ".php", ".rb", ".sh", ".bat", ".ps1",
            ".ini", ".yaml", ".yml", ".xml", ".tex", ".sql", ".lua", ".kt", ".swift", ".log", ".cfg", ".toml"}
BACKUPS = HERE / "capri_backups"

def _backup(p):
    BACKUPS.mkdir(exist_ok=True)
    dst = BACKUPS / f"{time.strftime('%Y%m%d-%H%M%S')}-{int(time.time() * 1000) % 1000:03d}-{p.name}"
    shutil.copy2(p, dst); return dst
KIND_EXT = [(r"python|\.py\b|script", ".py"), (r"html|web ?page|website", ".html"), (r"css|stylesheet", ".css"), (r"javascript|\bjs\b", ".js"), (r"json", ".json"), (r"csv|spreadsheet", ".csv"),
            (r"markdown|\.md\b|readme", ".md"), (r"batch|\.bat\b", ".bat"), (r"java\b", ".java"), (r"c\+\+|cpp", ".cpp")]

def _desktop():
    for c in (HOME / "Desktop", HOME / "OneDrive" / "Desktop"):
        if c.is_dir(): return c
    return HOME

def dest_dir(hint=""):
    h = (hint or "").lower()
    for key in ("desktop", "documents", "downloads", "pictures", "music", "videos"):
        if key in h:
            for base in (HOME, HOME / "OneDrive"):
                if (base / key.capitalize()).is_dir(): return base / key.capitalize()
    if hint:
        p = Path(os.path.expanduser(hint))
        if p.is_dir() and _inside_home(p): return p
    return _desktop()

def _inside_home(p):
    try: Path(p).resolve().relative_to(HOME.resolve()); return True
    except Exception: return False

def _clean_name(name, about=""):
    n = re.sub(r"[\\/:*?\"<>|]", "", (name or "").strip().strip("\"'")).strip(". ")
    n = re.sub(r"\s+dot\s+", ".", n, flags=re.I)
    if not n: n = "capri note"
    if "." not in n:
        ext = ".txt"
        for pat, e in KIND_EXT:
            if re.search(pat, (about or "") + " " + name, re.I): ext = e; break
        n += ext
    return n

def _strip_fences(s):
    s = s.strip(); s = re.sub(r"^```[\w+-]*\s*\n", "", s); s = re.sub(r"\n```\s*$", "", s); return s

def create_file(name, about="", content="", folder=""):
    d = dest_dir(folder)
    if not _inside_home(d): return "I only make files inside your user folder"
    fname = _clean_name(name, about)
    p = d / fname; n = 2
    while p.exists(): p = d / f"{Path(fname).stem} ({n}){Path(fname).suffix}"; n += 1
    text = content or ""
    if not text.strip():
        kind = Path(fname).suffix.lower()
        text = _strip_fences(ctx["chat"]([
            {"role": "system", "content": "You create files. Return ONLY the full contents of the file: no explanation, no markdown fences. Code must be complete and runnable."},
            {"role": "user", "content": f"File name: {fname}\nWhat it should contain: {about or name}"}], {"num_ctx": 4096, "num_predict": 1800, "temperature": 0.3}))
    if p.suffix.lower() == ".py":
        try: compile(text, str(p), "exec")
        except SyntaxError as e: _log(f"created py has syntax error line {e.lineno}")
    p.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    try: ctx["set_last_file"](p)
    except Exception: pass
    try:
        if os.name == "nt": subprocess.Popen(["explorer", "/select,", str(p)])        # show it in File Explorer
    except Exception: pass
    return f"made {p.name} in {p.parent.name} ({len(text.splitlines())} lines)"

def make_folder(name, folder=""):
    d = dest_dir(folder)
    if not _inside_home(d): return "I only make folders inside your user folder"
    n = re.sub(r"[\\/:*?\"<>|]", "", (name or "").strip()).strip(". ") or "New folder"
    p = d / n; p.mkdir(exist_ok=True)
    try:
        if os.name == "nt": subprocess.Popen(["explorer", str(p)])
    except Exception: pass
    return f"made the folder {p.name} in {p.parent.name}"

def list_dir(folder=""):
    d = dest_dir(folder)
    items = sorted(d.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))[:25]
    return f"{d.name}: " + ", ".join((i.name + ("/" if i.is_dir() else "")) for i in items) if items else f"{d.name} is empty"

def _chunks(text, size=3200):
    lines = text.splitlines(keepends=True); out, cur, n = [], [], 0
    for l in lines:
        cur.append(l); n += len(l)
        if n >= size and (not l.strip() or n >= size * 1.4): out.append("".join(cur)); cur, n = [], 0
    if cur: out.append("".join(cur))
    return out or [""]

def _ask_edit(chunk, instruction, hint=""):
    out = ctx["chat"]([
        {"role": "system", "content": "You are a careful editor and programmer. Apply the instruction to the text. Return ONLY the full edited text, keeping everything else exactly as it is, same line breaks. No explanations, no markdown fences."},
        {"role": "user", "content": f"INSTRUCTION: {instruction}\n{hint}\nTEXT:\n{chunk}"}], {"num_ctx": 8192, "num_predict": 4096, "temperature": 0.1})
    return _strip_fences(out)

def _validate(path, new, old, instruction=""):
    """Never save an edit that breaks the file."""
    suf = path.suffix.lower()
    if suf == ".py":
        try: compile(new, str(path), "exec")
        except SyntaxError as e:
            try: compile(old, str(path), "exec"); return f"my edit broke the Python (line {e.lineno}), so I didn't save it"
            except SyntaxError: pass
    if suf == ".json":
        try: json.loads(new)
        except Exception:
            try: json.loads(old); return "my edit broke the JSON, so I didn't save it"
            except Exception: pass
    if len(new) < len(old) * 0.5 and not re.search(r"delete|remove|shorter|shorten|summar|trim|cut|clear", instruction, re.I): return "my edit came out cut off, so I left your file alone"
    return None

def edit_file(name, instruction="Fix all spelling mistakes, typos and errors. Change nothing else."):
    """Edits the file in place (with a backup you can undo). Long files are done in pieces."""
    p = ctx["resolve_file"](name)
    if not p: return f"couldn't find a file called {name}"
    if p.suffix.lower() not in TEXT_EXT: return "I can only edit text and code files, choom"
    old = p.read_text(encoding="utf-8", errors="replace")
    if len(old) > 60000: return "that file is huge, I'd choke on it"
    hint = ""
    if p.suffix.lower() == ".py":
        try: compile(old, str(p), "exec")
        except SyntaxError as e: hint = f"Python reports: SyntaxError: {e.msg} on line {e.lineno}. "
    new = "".join(_ask_edit(c, instruction, hint) if c.strip() else c for c in _chunks(old))
    if old.endswith("\n") and not new.endswith("\n"): new += "\n"
    if new.strip() == old.strip(): return "I can't see anything to change in there"
    bad = _validate(p, new, old, instruction)
    if bad: return bad
    _backup(p); p.write_text(new, encoding="utf-8")
    diff = [l for l in difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=0) if l[:1] in "+-" and l[:3] not in ("+++", "---")]
    plus = [l[1:].strip() for l in diff if l.startswith("+")][:2]
    return f"edited {p.name}: {sum(1 for l in diff if l.startswith('+'))} lines changed" + (f" (e.g. \"{plus[0][:70]}\")" if plus else "") + ". Say 'undo' to put it back."

def replace_in_file(name, find, replace=""):
    p = ctx["resolve_file"](name)
    if not p or p.suffix.lower() not in TEXT_EXT: return f"couldn't find a text file called {name}"
    old = p.read_text(encoding="utf-8", errors="replace")
    if find not in old: return f"I can't find \"{find[:40]}\" in {p.name}"
    _backup(p); p.write_text(old.replace(find, replace), encoding="utf-8")
    return f"replaced {old.count(find)} spot(s) in {p.name}. Say 'undo' to put it back."

def undo_edit(name=""):
    p = ctx["resolve_file"](name) if name else None
    if p is None and ctx.get("last_file"): p = ctx["last_file"]()
    if not p: return "tell me which file, choom"
    cands = sorted(BACKUPS.glob(f"*-{p.name}")) if BACKUPS.is_dir() else []
    if not cands: return f"no backup of {p.name} yet"
    target = cands[-1]; _backup(p)                                                    # keep the current one too
    shutil.copy2(target, p)
    return f"put {p.name} back how it was"

# =====================================================================  mood pop-ups (she shows you how she feels)
INSULT = re.compile(r"\b(stupid|idiot|dumb|useless|shut up|trash|garbage|hate you|you suck|worst|annoying|loser|moron|pathetic|bad bot|you(?:'re| are) wrong|you(?:'re| are) bad)\b", re.I)
PRAISE = re.compile(r"\b(love you|thank you|thanks|good job|well done|nice one|you(?:'re| are) (?:the )?(?:best|awesome|amazing|great|goated)|preem|legend)\b", re.I)
SORRY = re.compile(r"\b(sorry|my bad|i apologi[sz]e|forgive me)\b", re.I)
MOOD_QUERIES = {
    "angry": ["angry face meme", "angry anime face", "furious cat meme", "rage face reaction"],
    "sad": ["sad cat meme", "crying anime face", "sad reaction meme"],
    "happy": ["happy dance gif", "excited anime face", "celebration reaction gif"],
    "smug": ["smug anime face", "smug cat meme", "smirk reaction meme"],
}
SITES = ["https://www.google.com/search?tbm=isch&safe=active&q={q}", "https://giphy.com/search/{slug}", "https://tenor.com/search/{slug}-gifs"]
_mood_state = {"last": 0.0, "count": 0}

def detect_feeling(user_text, model_feeling=None):
    if INSULT.search(user_text): return "angry"
    if SORRY.search(user_text): return "smug"
    if PRAISE.search(user_text): return "happy"
    f = (model_feeling or "").lower().strip()
    return f if f in MOOD_QUERIES else None

def mood_pop(feeling):
    """Sometimes (not always) she opens a reaction image in your browser to show how she feels."""
    if os.environ.get("CAPRI_MOODWEB", "1") == "0" or feeling not in MOOD_QUERIES: return None
    now = time.time()
    if now - _mood_state["last"] < 120 or _mood_state["count"] >= 12: return None
    if random.random() > (0.65 if feeling == "angry" else 0.3): return None
    q = random.choice(MOOD_QUERIES[feeling]); site = random.choice(SITES)
    url = site.format(q=urllib.parse.quote_plus(q), slug=urllib.parse.quote(q.replace(" ", "-")))
    _mood_state["last"] = now; _mood_state["count"] += 1
    try: ctx["open_url"](url)
    except Exception: return None
    return f"popped up {'an' if feeling[0] in 'aeiou' else 'a'} {feeling} face for you"
