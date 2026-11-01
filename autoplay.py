"""
Gaming mode AUTOPILOT: Capri takes over Minecraft (Java Edition) with your keyboard and mouse. NO MODS.
She watches the screen (F3 debug text + colours, see mc_vision.py) and plays: chop wood, mine, find ores, explore, fight, eat, build.

Say: "chop some wood" / "get 20 logs" / "mine down" / "find diamonds" / "explore" / "fight" / "eat" / "build a shelter" /
     "build a 6 block tower" / "what do you see?" / "play for me".  Hotbar: "my pickaxe is in slot 1", "food is in slot 9", "blocks in slot 2".
Take control back: "stop" / "my turn" / F8. She also freezes the moment Minecraft isn't the active window (so she can't type into anything else).
server.py calls init(log, events, chat, bring_front, list_windows, launch_minecraft, tray_msg, takeover_ui). stream_live.py uses parse()/start().
"""
import os, re, threading, time
from pathlib import Path
import mc_vision as MV

ctx = {}
def init(**kw):
    ctx.update(kw)
    MV.init(log=_log, event=lambda m: _event(m))
def _log(m):
    try: ctx["log"](m)
    except Exception: pass
def _event(text, bad=False):
    try: ctx["events"].append({"type": "act", "text": "// " + text, "bad": bad})
    except Exception: pass

MC_DIR = MV.MC_DIR
LOG_FILE = MC_DIR / "logs" / "latest.log"
STATE = {"active": False, "game": "", "task": "", "command": "", "since": 0.0, "last_chat": "", "waiting": False, "fullscreen": False, "joined": False}
_exe_of = MV.exe_of                                            # modes.py uses it to find windows by program

# ===================================================================== what you say -> a skill
NUMS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12,
        "fifteen": 15, "twenty": 20, "thirty": 30, "a stack of": 64, "a stack": 64, "stack of": 64, "some": 8, "a few": 5, "a bunch of": 20, "lots of": 32, "loads of": 32}
def _n(word, default, cap=64):
    if not word: return default
    w = word.strip().lower()
    if w.isdigit(): return max(1, min(int(w), cap))
    return min(NUMS.get(w, default), cap)

QTY = r"(\d+|a stack of|a stack|stack of|a bunch of|lots of|loads of|a few|some|an|a|one|two|three|four|five|six|seven|eight|nine|ten|twelve|fifteen|twenty|thirty)?"
STOP_RX = re.compile(r"^(?:ok(?:ay)?\s+)?(?:stop|stop it|stop playing|stop now|halt|freeze|pause|my turn|i got it|i'?ve got it|i'?ll take it from here|take back control|give me control|give me back control|"
                     r"let me play|hands off|cancel|abort|enough|that'?s enough)(?:\s+(?:capri|please|now|it))*$", re.I)

def stop_phrase(text):
    t = re.sub(r"[^a-z' ]", " ", text.lower()); t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"^(?:hey )?(?:capri )?", "", t)
    return bool(STOP_RX.match(t))

def _clean(text):
    t = re.sub(r"\s+", " ", text.lower().strip(" .!?")); t = re.sub(r"^(?:hey )?capri[, ]*", "", t)
    t = re.sub(r"^(?:please |can you |could you |go (?!to\b)|now |i want you to |try to )+", "", t)
    return re.sub(r"\s+(?:for me|please|in minecraft|on minecraft|now|real quick)$", "", t)

def parse(text):
    """-> (["skill:<name>:<arg>"], what she says) or None. Rules first (fast, any phrasing below works)."""
    t = _clean(text)
    m = re.search(r"\b(pick(?:axe)?|tool|sword|axe|food|blocks?|dirt|cobble(?:stone)?)\b.*\bslot\s*(\d)\b|\bslot\s*(\d)\b.*\b(pick(?:axe)?|tool|sword|axe|food|blocks?)\b", t)
    if m:
        what = (m.group(1) or m.group(4)); slot = int(m.group(2) or m.group(3))
        key = "slot_food" if what == "food" else "slot_blocks" if re.match(r"block|dirt|cobble", what) else "slot_tool"
        return [f"config:{key}:{slot}"], f"Got it: {key.split('_')[1]} in slot {slot}."
    if re.search(r"\b(beat|finish|complete|win|speedrun|speed run)\b.*\b(game|minecraft|it|dragon)\b|^(?:auto ?play|autopilot|take over|play for me|play it for me|play minecraft for me|you play|play the game for me|keep playing)\b", t) \
       or re.fullmatch(r"(?:take over|play)(?: minecraft)?", t):
        return ["skill:play:30"], "Taking over: I'll get wood, explore and mine. Fair warning, choom: beating the dragon by eye is above my pay grade, but watch this."
    if re.search(r"\b(what do you see|what(?:'s| is) on (?:the )?screen|describe|look around|where are we)\b", t):
        return ["skill:describe:"], "Let me look."
    if re.search(r"\b(status|what are you doing|progress)\b", t): return ["status:"], "Checking."
    m = re.search(r"\b(?:chop(?: down)?|cut(?: down)?|get|grab|collect|gather|punch|find)\s+(?:me\s+)?" + QTY + r"\s*(?:more\s+)?(?:wood|woods|logs?|trees?|oak|birch|spruce)\b", t) \
        or re.search(r"\b(?:chop|lumberjack)\b" + r"\s*" + QTY, t)
    if m: n = _n(m.group(1), 8); return [f"skill:chop_wood:{n}"], f"Chopping {n} logs."
    m = re.search(r"\b(?:find|get|mine|look for|hunt for|search for)\s+(?:me\s+)?(?:some\s+|a few\s+|\d+\s+)?(diamonds?|iron|gold|coal|redstone|lapis|emeralds?|copper|ores?)\b", t)
    if m:
        ore = re.sub(r"s$", "", m.group(1)); ore = "any" if ore == "ore" else ore
        return [f"skill:find_ore:{ore}"], f"Going down for {ore if ore != 'any' else 'ores'}. Pickaxe in hand, I hope."
    if re.search(r"\b(?:mine|mining|dig|digging|tunnel|strip ?mine)\b", t) or re.search(r"\b(?:get|collect|gather)\s+(?:some\s+|\d+\s+)?(?:stone|cobble(?:stone)?)\b", t):
        return ["skill:mine:12"], "Digging a staircase down."
    if re.search(r"\b(?:explore|wander|go exploring|look for a village|find a village|roam|run around)\b", t):
        m = re.search(r"(\d+)\s*(?:min|minute)", t); secs = int(m.group(1)) * 60 if m else 60
        return [f"skill:explore:{min(secs, 900)}"], "Exploring."
    if re.search(r"\b(?:fight|kill|attack|protect me|defend|hunt)\b", t): return ["skill:fight:60"], "Weapons hot."
    if re.search(r"\b(?:eat|i'?m (?:hungry|starving)|feed (?:me|yourself)|get food|food)\b", t): return ["skill:eat:"], "Snack time."
    m = re.search(r"\b(?:build|make|place)\s+(?:me\s+)?(?:a\s+|an\s+)?(\d+)?\s*(?:block\s+)?(?:high\s+)?(?:tower|pillar)\b|\bpillar up\b|\btower up\b", t)
    if m: n = _n(m.group(1) if m.lastindex else None, 5, 32); return [f"skill:pillar:{n}"], f"Building a {n}-block tower."
    if re.search(r"\b(?:build|make)\s+(?:me\s+)?(?:a\s+|an\s+|the\s+)?(?:little\s+|small\s+|quick\s+)?(?:house|home|hut|base|shelter|cabin|walls?|fort)\b", t):
        return ["skill:shelter:"], "Building walls around us."
    return None

def parse_llm(text, lang_name="English"):
    """Other phrasing / languages: the brain picks one skill."""
    try:
        out = ctx["chat"]([
            {"role": "system", "content": "Map the player's Minecraft request (may be in " + lang_name + ") to ONE command, output only the command:\n"
             "chop_wood <n> | find_ore <diamond|iron|gold|coal|redstone|lapis|emerald|any> | mine | explore <seconds> | fight | eat | shelter | pillar <n> | describe | play | stop | NONE"},
            {"role": "user", "content": text}], {"num_predict": 12, "temperature": 0})
        w = out.strip().strip("`\"' ").split()
        if not w: return None
        k = w[0].lower(); a = w[1] if len(w) > 1 else ""
        if k == "stop": return ["stop:"], "Stopping."
        if k in ("chop_wood", "find_ore", "mine", "explore", "fight", "eat", "shelter", "pillar", "describe", "play"):
            if k == "mine": a = "12"
            return [f"skill:{k}:{a}"], "On it, choom."
    except Exception as e: _log(f"autoplay parse_llm failed: {e}")
    return None

def wants_autoplay(text, mode):
    """Is this a Minecraft-control request? ('play minecraft' alone still just LAUNCHES the game.)"""
    low = text.lower()
    if STATE["active"] and (stop_phrase(text) or parse(text)): return True
    if re.search(r"\b(for me|autopilot|auto ?play|take over|takeover|beat (?:the game|minecraft)|kill the (?:ender )?dragon|speedrun)\b", low): return True
    if "minecraft" in low and re.search(r"\b(beat|mine|build|chop|collect|explore|play for)\b", low): return True
    p = parse(text)
    if not p: return False
    if mode == "gaming": return True
    # outside gaming mode only clear game orders count ("describe X" / "I'm hungry" / "status" stay normal chat)
    return p[0][0].split(":")[1] in ("chop_wood", "find_ore", "mine", "explore", "fight", "shelter", "pillar", "play") and bool(MV.find_window())

# ===================================================================== running
_lock = threading.Lock()
def _ui(on):
    try: ctx["takeover_ui"](False)               # the full-screen frame would be in her own camera: tray message instead
    except Exception: pass
    if on:
        try: ctx["tray_msg"]("Capri is playing Minecraft. Say 'stop' or press F8 to take back control.")
        except Exception: pass

def _done(result):
    STATE.update(active=False, task="", command="")
    _event(f"minecraft: {result}")
    _log(f"minecraft task done: {result}")

def start(cmds, label):
    """Runs a parsed command. Returns False if Minecraft isn't there."""
    with _lock:
        cmd = cmds[0]; kind, name, arg = (cmd.split(":") + ["", ""])[:3]
        if kind == "config":
            MV.CFG[name] = int(arg); MV.save_cfg(); return True
        if kind == "stop": stop(); return True
        if kind == "status": return True
        if not MV.find_window(): return False
        args = ()
        if name in ("chop_wood", "pillar"): args = (int(arg or 8),)
        elif name == "explore": args = (int(arg or 60),)
        elif name == "fight": args = (int(arg or 60),)
        elif name == "play": args = (int(arg or 30),)
        elif name == "mine": args = (int(arg or 12),)
        elif name == "find_ore":
            ore = arg or "any"; name = "mine"; args = (MV.ORE_Y.get(ore, 12), ore)
        STATE.update(active=True, game="Minecraft", task=label, command=cmd, since=time.time(), last_chat="")
        _ui(True)
        MV.RUNNER.start(name, args, on_done=_done, progress=lambda m: STATE.__setitem__("last_chat", m) or _event("mc: " + m))
        _event(f"autopilot: {label}")
        return True

def stop(silent=False):
    was = STATE["active"] or MV.RUNNER.busy()
    MV.RUNNER.cancel()
    STATE.update(active=False, waiting=False, task="", command="")
    if was and not silent: _event("autopilot: stopped, you have control")
    return was

# ===================================================================== Minecraft not open yet: launch it and wait
def _tail_until_joined(timeout=600):
    pos = LOG_FILE.stat().st_size if LOG_FILE.exists() else 0; t0 = time.time()
    while STATE["waiting"] and time.time() - t0 < timeout:
        try:
            if LOG_FILE.exists():
                size = LOG_FILE.stat().st_size
                if size < pos: pos = 0
                if size > pos:
                    with open(LOG_FILE, encoding="utf-8", errors="replace") as f: f.seek(pos); new = f.read(); pos = f.tell()
                    if re.search(r"joined the game|Started integrated server|Connecting to", new): return True
        except Exception as e: _log(f"mc log tail: {e}")
        time.sleep(1)
    return False

def _wait_then_start(cmds, label):
    STATE.update(waiting=True)
    if _tail_until_joined() and STATE["waiting"]:
        time.sleep(5); STATE["waiting"] = False
        if start(cmds, label): _event("autopilot: you're in, taking over")
    STATE["waiting"] = False

def bedrock_running():
    if os.name != "nt": return False
    try:
        for w in ctx["list_windows"]():
            if w.get("title", "").strip() == "Minecraft" and "minecraft.windows" in MV.exe_of(w["hwnd"]).lower(): return True
    except Exception: pass
    return False

def handle(text, lang_name="English"):
    """Returns {'say', 'mood'} or None."""
    if stop_phrase(text):
        if STATE["active"] or STATE["waiting"] or MV.RUNNER.busy():
            stop(); return {"say": "Hands back on the wheel, choom. You've got control.", "mood": "idle"}
        return None
    p = parse(text) or parse_llm(text, lang_name)
    if not p:
        return {"say": "Tell me what to do in Minecraft, choom: 'chop wood', 'find diamonds', 'explore', 'fight', 'build a shelter' or 'play for me'.", "mood": "idle"}
    cmds, say = p
    kind = cmds[0].split(":")[0]
    if kind == "stop": stop(); return {"say": "Hands back on the wheel, choom.", "mood": "idle"}
    if kind == "config": start(cmds, say); return {"say": say, "mood": "hyped"}
    if kind == "status":
        if MV.RUNNER.busy(): return {"say": f"Working on: {STATE['task']}. Last thing I did: {STATE['last_chat'] or 'just started'}.", "mood": "working"}
        return {"say": f"Not playing right now. Last result: {MV.RUNNER.result or 'nothing yet'}.", "mood": "idle"}
    if os.name != "nt": return {"say": "Autopilot only works on Windows, choom.", "mood": "alert"}
    if not MV.find_window():
        if bedrock_running():
            return {"say": "That's Bedrock, choom. I can only drive Minecraft Java Edition (it has the F3 screen I read).", "mood": "alert"}
        try: ctx["launch_minecraft"]()
        except Exception as e: _log(f"launch minecraft failed: {e}")
        threading.Thread(target=_wait_then_start, args=(cmds, say), daemon=True, name="mc_wait").start()
        return {"say": "Opening Minecraft. Load into a world and I'll take over the second you're in.", "mood": "working"}
    if cmds[0].startswith("skill:describe"):
        def look():
            try:
                h, rect = MV.find_window(); MV.focus(h); f = MV.Screen(rect).grab(); _event("I see: " + MV.describe_frame(f))
            except Exception as e: _event(f"couldn't look: {e}", True)
        threading.Thread(target=look, daemon=True).start()
        return {"say": say, "mood": "working"}
    if not start(cmds, say):
        return {"say": "I couldn't find the Minecraft window, choom. Load into a world and ask again.", "mood": "alert"}
    return {"say": say + " Say 'stop' or press F8 to take back control.", "mood": "hyped"}

def status():
    return {"active": STATE["active"] and MV.RUNNER.busy(), "waiting": STATE["waiting"], "game": STATE["game"], "task": STATE["task"], "command": STATE["command"],
            "elapsed": int(time.time() - STATE["since"]) if STATE["active"] else 0, "last": STATE["last_chat"]}

# ===================================================================== F8 = take back control (works even inside the game)
def hotkey_loop():
    if os.name != "nt": return
    import ctypes
    from ctypes import wintypes
    u = ctypes.windll.user32
    if not u.RegisterHotKey(None, 0xCA9, 0, 0x77):                         # VK_F8, no modifiers
        _log("F8 hotkey is taken by another app; say 'stop' instead"); return
    msg = wintypes.MSG()
    while u.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
        if msg.message == 0x0312 and msg.wParam == 0xCA9 and (STATE["active"] or STATE["waiting"] or MV.RUNNER.busy()):
            stop(); _log("autopilot stopped with F8")
