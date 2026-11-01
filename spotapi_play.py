"""
Spotify auto-play through SpotAPI (github.com/Aran404/SpotAPI): it talks to Spotify the way the web player does,
using YOUR logged-in session cookie (sp_dc). No developer app, no client ID/secret, no captcha solver.
One-time setup: python spotify_setup.py -> option 1 (paste your sp_dc cookie). Saved in spotapi_session.json on this PC only.

It plays on whatever Spotify is open (the desktop app, the web player or your phone): open Spotify and play any song once so
there's an active device. If nothing is open, Capri opens the desktop app and waits for it.

Heads up: this is Spotify's PRIVATE web API (unofficial). It can break when Spotify changes their site, and using it is against
Spotify's terms, so use it on your own account at your own risk. If it fails, Capri falls back to the official API (spotify.json) or search.
music.py / server.py call configured() and the play_* functions. server.py calls init(open_app=..., log=...).
"""
import difflib, json, os, random, re, signal, threading, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SESSION = HERE / "spotapi_session.json"
ctx = {}
def init(**kw): ctx.update(kw)
def _log(m):
    try: ctx["log"](m)
    except Exception: pass

def configured():
    if not SESSION.exists(): return False
    try:
        import spotapi  # noqa: F401
        return True
    except Exception as e:
        _log(f"spotapi not importable ({e}): python -m pip install spotapi websockets pymongo redis")
        return False

# ---------------------------------------------------------------- session
_lock = threading.RLock()
_login = None
_player = None
_player_at = 0.0

def parse_cookies(text):
    """'sp_dc=AQ...; sp_key=...' or just the bare sp_dc value -> {'sp_dc': ..., ...}"""
    text = (text or "").strip().strip('"\'')
    if "=" not in text: return {"sp_dc": text} if len(text) > 50 else {}
    out = {}
    for part in text.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)                       # values can contain '='
            if k.strip(): out[k.strip()] = v.strip()
    return out

def save_session(identifier, cookies):
    SESSION.write_text(json.dumps({"identifier": identifier or "me", "cookies": cookies}, indent=1), encoding="utf-8")

def login():
    global _login
    with _lock:
        if _login is None:
            from spotapi import Login, Config, NoopLogger
            dump = json.loads(SESSION.read_text(encoding="utf-8"))
            if isinstance(dump.get("cookies"), str): dump["cookies"] = parse_cookies(dump["cookies"])
            _login = Login.from_cookies(dump, Config(logger=NoopLogger()))
        return _login

class _NoSignal:
    """SpotAPI's player calls signal.signal() when it connects, which Python only allows on the main thread.
       Capri runs music in a worker thread, so while it connects we skip that (Ctrl+C handling isn't needed here)."""
    def __enter__(self):
        self.orig = signal.signal
        if threading.current_thread() is not threading.main_thread():
            signal.signal = lambda *a, **k: None
    def __exit__(self, *a): signal.signal = self.orig

class _Connect:
    """Capri's own Spotify Connect remote, built on SpotAPI's websocket session.
       (SpotAPI's Player class parses Spotify's state into strict types and breaks whenever Spotify adds/removes a field,
       e.g. 'MetadataMap missing tier1_port'. This reads the raw JSON instead, so it keeps working.)"""
    def __init__(self, lg):
        from spotapi.websocket import WebsocketStreamer
        with _NoSignal(): self.ws = WebsocketStreamer(lg)
        self.client = self.ws.client
        self.ws.register_device()
        self.me = self.ws.device_id
        self.target = None

    def devices(self):
        dump = self.ws.connect_device() or {}
        devs = dump.get("devices") or {}
        mine = {self.me, "hobs_" + self.me}
        devs = {k: v for k, v in devs.items() if k not in mine and not (v or {}).get("capabilities", {}).get("hidden")}
        return dump.get("active_device_id"), devs

    def pick(self):
        active, devs = self.devices()
        if active and active in devs: return active, True
        if active and active not in {self.me, "hobs_" + self.me}: return active, True
        def rank(item):
            k, v = item; t = str((v or {}).get("device_type", "")).upper(); n = str((v or {}).get("name", "")).lower()
            return (t == "COMPUTER" and "web player" not in n, t == "COMPUTER", t == "SMARTPHONE")
        if not devs: return None, False
        return max(devs.items(), key=rank)[0], False

    def post(self, url, payload):
        r = self.client.post(url, json=payload, authenticate=True)
        if r.fail: raise RuntimeError(f"Spotify said no: {getattr(r.error, 'string', r.error)}")
        return r

    def transfer(self, to):
        self.post(f"https://gue1-spclient.spotify.com/connect-state/v1/connect/transfer/from/{self.me}/to/{to}",
                  {"transfer_options": {"restore_paused": "resume"}, "command_id": _hex()})

    def command(self, payload):
        if not self.target:
            t, active = self.pick()
            if not t: raise RuntimeError("no Spotify device is open")
            if not active:
                try: self.transfer(t); time.sleep(0.8)              # wake the app up as the player
                except Exception as e: _log(f"spotapi transfer failed (trying the command anyway): {e}")
            self.target = t
            _, devs = self.devices()
            _log(f"spotify: sending to {(devs.get(t) or {}).get('name', t)} ({'already active' if active else 'woke it up'})")
        self.post(f"https://gue1-spclient.spotify.com/connect-state/v1/player/command/from/{self.me}/to/{self.target}", payload)

def player(fresh=False):
    """A connected remote (cached ~10 min). Opens the Spotify app if no device is there yet."""
    global _player, _player_at
    with _lock:
        if _player is not None and not fresh and time.time() - _player_at < 600: return _player
        last = None
        for attempt in range(5):
            try:
                c = _player if (_player is not None and not fresh and attempt == 0) else _Connect(login())
                t, _ = c.pick()
                if not t: raise RuntimeError("no Spotify device is open")
                _player, _player_at = c, time.time(); return c
            except Exception as e:
                last = e; _log(f"spotify connect attempt {attempt + 1}: {e}")
                if attempt == 0:
                    try: ctx["open_app"]("spotify")
                    except Exception: pass
                time.sleep(4 if attempt == 0 else 2.5)
        raise RuntimeError(f"couldn't reach the Spotify app: open Spotify on this PC ({last})")

def _command(payload):
    p = player()
    try: p.command(payload)
    except Exception as e:
        _log(f"spotify command failed, reconnecting: {e}")
        p = player(fresh=True); p.target = None; p.command(payload)          # device changed / token expired: reconnect once
    return p

def _hex(n=32): return "".join(random.choice("0123456789abcdef") for _ in range(n))

def _simple(endpoint, **extra):
    return {"command": dict({"endpoint": endpoint, "logging_params": {"page_instance_ids": [], "interaction_ids": [], "command_id": _hex()}}, **extra)}

def play_context(context_uri, track_uri=None, index=None, shuffle=None):
    """Same 'play' command the web player sends. context = album / playlist / artist / liked songs."""
    opts = {"license": "tft", "player_options_override": {}}
    if shuffle is not None: opts["player_options_override"]["shuffling_context"] = bool(shuffle)
    if track_uri: opts["skip_to"] = {"track_uri": track_uri}
    elif index is not None: opts["skip_to"] = {"track_index": int(index)}
    payload = {"command": {
        "context": {"uri": context_uri, "url": "context://" + context_uri, "metadata": {}},
        "play_origin": {"feature_identifier": context_uri.split(":")[1] if context_uri.count(":") >= 2 else "search", "referrer_identifier": "search"},
        "options": opts,
        "logging_params": {"page_instance_ids": [], "interaction_ids": [], "command_id": _hex()},
        "endpoint": "play"}}
    _command(payload)
    _log(f"spotify: play {context_uri}" + (f" from {track_uri}" if track_uri else f" at #{index}" if index is not None else ""))
    if shuffle is not None:
        try: _command(_simple("set_shuffling_context", value=bool(shuffle)))
        except Exception as e: _log(f"spotify shuffle failed: {e}")

# ---------------------------------------------------------------- reading Spotify's answers (walk them: field names drift between versions)
def _walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values(): yield from _walk(v)
    elif isinstance(o, list):
        for v in o: yield from _walk(v)

def _uri(d):
    for k in ("uri", "_uri"):
        v = d.get(k)
        if isinstance(v, str) and v.startswith("spotify:"): return v
    return None

def _name(d):
    if isinstance(d.get("name"), str): return d["name"]
    for k in ("data", "profile"):
        if isinstance(d.get(k), dict) and isinstance(d[k].get("name"), str): return d[k]["name"]
    return ""

def _items(resp, kind):
    """All (uri, name, dict) for 'track' / 'artist' / 'album' / 'playlist' entries in a response, in order, no duplicates."""
    seen, out = set(), []
    for d in _walk(resp):
        u = _uri(d)
        if u and u.split(":")[1] == kind and u not in seen and _name(d):
            seen.add(u); out.append((u, _name(d), d))
    return out

def _norm(s): return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()
def _sim(a, b):
    a, b = _norm(a), _norm(b)
    if not a or not b: return 0.0
    if a == b: return 1.0
    wa, wb = set(a.split()), set(b.split())
    if wa and (wa <= wb or wb <= wa): return 0.86
    return difflib.SequenceMatcher(None, a, b).ratio()

def _variants(name):
    n = name.strip(" '\""); out = [n]
    if re.search(r"[^s]s$", n, re.I) and len(n) > 3: out.append(n[:-1])          # "hutchers" -> "hutcher"
    return out

# ---------------------------------------------------------------- what Capri can ask for
def track(query):
    from spotapi import Song
    hits = _items(Song().query_songs(query, limit=5), "track")
    if not hits: return f"no track found for {query}"
    uri, name, d = hits[0]
    artist = next((_name(x) for x in _walk(d.get("artists") or (d.get("data") or {}).get("artists") or {}) if _uri(x) and ":artist:" in _uri(x)), "")
    album = next((u for u, _, _ in _items(d, "album")), None)
    if album: play_context(album, track_uri=uri, shuffle=False)
    else: play_context(uri, shuffle=False)
    return f"playing {name}" + (f" by {artist}" if artist else "")

def find_artist(name):
    from spotapi import Artist
    best, score = None, 0.0
    for v in _variants(name):
        for i, (u, n, _) in enumerate(_items(Artist(login()).query_artists(v, limit=5), "artist")[:5]):
            s = max(_sim(x, n) for x in _variants(name)) - i * 0.02
            if s > score: best, score = (u, n), s
    return best if score >= 0.55 else None

def _date(d):
    for x in _walk(d.get("date") or {}):
        v = x.get("isoString") or x.get("year")
        if v: return str(v)
    return ""

def newest(artist, album=False):
    from spotapi import Artist
    a = find_artist(artist)
    if not a: return f"I couldn't find an artist called {artist} on Spotify, choom"
    uri, aname = a; api = Artist(login()); aid = uri.split(":")[-1]
    rel = []
    try: rel = _items(api.get_artist_discography(aid, section="albums" if album else "all", limit=5, order="DATE_DESC"), "album")
    except Exception as e: _log(f"discography failed, using the artist page: {e}")
    if not rel:                                                                     # older SpotAPI: the overview's "latest" release
        ov = api.get_artist(aid)
        latest = next((x for x in _walk(ov) if isinstance(x.get("latest"), dict)), {}).get("latest")
        rel = _items(latest or {}, "album") or _items(ov, "album")
    if not rel: return f"{aname} has nothing out on Spotify"
    ruri, rname, d = rel[0]
    play_context(ruri, index=0, shuffle=False)
    when = _date(d)
    return f"playing {aname}'s newest {'album' if album else 'drop'}: {rname}" + (f" ({when[:10]})" if when else "")

def artist(name):
    a = find_artist(name)
    if not a: return f"I couldn't find {name} on Spotify"
    play_context(a[0], shuffle=True)
    return f"playing {a[1]}"

def album(query):
    from spotapi import Song
    hits = _items(Song().query_songs(query, limit=5), "album")
    if not hits: return f"no album found for {query}"
    play_context(hits[0][0], index=0, shuffle=False)
    return f"playing the album {hits[0][1]}"

def _username():
    from spotapi import User
    try: return User(login()).username
    except Exception as e:
        _log(f"spotapi username failed: {e}")
        ident = json.loads(SESSION.read_text(encoding="utf-8")).get("identifier", "")
        if ident and "@" not in ident and ident != "me": return ident
        raise RuntimeError("couldn't read your Spotify username: run spotify_setup.py again and type your username")

def liked(shuffle=True):
    from spotapi import PrivatePlaylist
    total = 0
    try:
        info = PrivatePlaylist(login()).get_saved_tracks_info(limit=1)
        total = int(next((x["totalCount"] for x in _walk(info) if isinstance(x.get("totalCount"), int)), 0))
    except Exception as e: _log(f"liked count failed: {e}")
    ctx_uri = f"spotify:user:{_username()}:collection"
    play_context(ctx_uri, index=random.randrange(total) if (shuffle and total) else 0, shuffle=bool(shuffle))
    return "playing a random song from your Liked Songs (shuffle on)" if shuffle else "playing your Liked Songs"

def playlist(name, shuffle=False):
    from spotapi import PrivatePlaylist
    pls = _items(PrivatePlaylist(login()).get_library(50), "playlist")
    if not pls: return "I can't see any playlists in your library, choom"
    uri, pname, _ = max(pls, key=lambda p: _sim(name, p[1]))
    if _sim(name, pname) < 0.5: return f"I can't find a playlist called {name}. You've got: " + ", ".join(p[1] for p in pls[:6])
    play_context(uri, shuffle=bool(shuffle))
    return f"{'shuffling' if shuffle else 'playing'} your {pname} playlist"

def control(what):
    """pause / resume / next / previous through SpotAPI (Capri also has media keys as a fallback)."""
    _command(_simple({"pause": "pause", "resume": "resume", "next": "skip_next", "previous": "skip_prev"}[what]))
    return what
