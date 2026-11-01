"""
Smart music requests for Music mode. Understands things like:
  "play hutchers newest song"            -> the artist's latest release (fuzzy artist match, "hutchers" -> "Hutcher")
  "play the latest album by drake"       -> newest album as a whole
  "play a random song from my liked songs" / "shuffle my likes"
  "play my gym playlist" / "play a random song from my chill playlist" / "shuffle my road trip playlist"
  "play some kendrick" / "play drake's top songs"
  "play the album to pimp a butterfly"
Spotify does it through its Web API (Premium, spotify_setup.py). YouTube / YouTube Music use ytmusicapi (no login needed)
for artists and releases, and your own signed-in browser for liked songs.
server.py calls init(spotify_client=..., yt_lookup=..., open_url=..., open_app=..., chat=..., log=...).
"""
import difflib, json, random, re, time, urllib.parse
import spotapi_play as SPA

ctx = {}
def init(**kw): ctx.update(kw)
def _log(m):
    try: ctx["log"](m)
    except Exception: pass

# ======================================================================= understanding the request
_NEW = r"(?:newest|latest|new|most recent|last|brand new|recent)"
_SONG = r"(?:song|songs|track|tracks|single|singles|release|drop|music|tune|banger|joint)"
_ALBUM = r"(?:album|record|lp|ep|mixtape|tape)"
_LIKED = r"(?:liked|likes|favou?rites?|faves|saved|loved|heart(?:ed)?)"

def parse(text):
    """'hutchers newest song' -> {'kind': 'newest', 'artist': 'hutchers'}. None if it's just a plain song search."""
    t = re.sub(r"\s+", " ", text.strip(" .!?")).strip()
    low = t.lower()
    shuffle = bool(re.search(r"\b(random|shuffle|shuffled|any|something|a song|some songs|mix)\b", low))
    # ---- liked songs
    if re.search(rf"\bmy\s+(?:{_LIKED})\b|\b(?:{_LIKED})\s+(?:songs|music|tracks|playlist|list)\b|\bsongs i(?:'ve| have)? liked\b", low):
        return {"kind": "liked", "shuffle": True if not re.search(r"\b(in order|from the top|from the start|latest|newest|recent)\b", low) else False,
                "recent": bool(re.search(r"\b(latest|newest|recent|last)\b", low))}
    # ---- one of my playlists
    m = re.search(r"\bmy\s+(.+?)\s+play\s?list\b", low) or re.search(r"\bplay\s?list\s+(?:called|named)?\s*(.+)$", low) or re.search(r"\bmy\s+play\s?list\s+(.+)$", low)
    if m and m.group(1).strip() not in ("liked", "likes"):
        return {"kind": "playlist", "name": m.group(1).strip(" '\""), "shuffle": shuffle, "random": bool(re.search(r"\b(random|a song|any song|one song)\b", low))}
    # ---- newest album
    m = re.search(rf"^(?:the\s+|a\s+)?{_NEW}\s+{_ALBUM}\s+(?:by|from|of)\s+(.+)$", low) or re.search(rf"^(.+?)(?:'s|’s|s')?\s+{_NEW}\s+{_ALBUM}$", low)
    if m: return {"kind": "newest", "artist": m.group(1).strip(), "album": True}
    # ---- newest song
    m = (re.search(rf"^(?:the\s+|a\s+)?{_NEW}\s+{_SONG}\s+(?:by|from|of)\s+(.+)$", low) or
         re.search(rf"^(.+?)(?:'s|’s|s')?\s+{_NEW}\s+{_SONG}(?:\s+(?:out|right now|now))?$", low) or
         re.search(rf"^(?:what(?:'s| is)\s+)?(?:the\s+)?{_NEW}\s+(?:from|by)\s+(.+)$", low) or
         re.search(rf"^{_NEW}\s+(.+?)(?:\s+{_SONG})?$", low))
    if m and m.group(1).strip() not in ("music", "songs", "song"): return {"kind": "newest", "artist": m.group(1).strip(), "album": False}
    # ---- an album
    m = re.search(rf"^(?:the\s+)?{_ALBUM}\s+(.+?)(?:\s+by\s+(.+))?$", low) or re.search(rf"^(.+?)\s+(?:the\s+)?{_ALBUM}(?:\s+by\s+(.+))?$", low)
    if m and not re.search(r"\b(song|track)\b", low): return {"kind": "album", "query": (m.group(1) + (" " + m.group(2) if m.group(2) else "")).strip()}
    # ---- an artist in general
    m = (re.search(r"^(?:some|a bit of|a little|more)\s+(.+)$", low) or re.search(r"^(?:songs|music|tracks|hits|bangers)\s+(?:by|from)\s+(.+)$", low) or
         re.search(r"^(.+?)(?:'s|’s|s')?\s+(?:top|best|biggest|greatest|popular|most popular)\s+(?:songs|tracks|hits)$", low) or
         re.search(r"^(?:the\s+)?(?:top|best|biggest|greatest|popular)\s+(?:songs|tracks|hits)\s+(?:by|from|of)\s+(.+)$", low) or
         re.search(r"^(?:anything|something|a song|any song|a random song|random songs?)\s+(?:by|from)\s+(.+)$", low))
    if m and not re.search(r"\b(by)\b.+\bby\b", low): return {"kind": "artist", "artist": m.group(1).strip()}
    return None

HINTS = re.compile(rf"\b(my|{_NEW}|random|shuffle|playlist|album|{_LIKED}|top|best|some)\b", re.I)

def parse_llm(text, lang_name="English"):
    """For phrasing the rules don't catch (or other languages): ask the brain to fill the same fields."""
    try:
        out = ctx["chat"]([
            {"role": "system", "content": "You turn a music request into JSON. Fields: kind (one of: track, newest, liked, playlist, artist, album), "
                                          "artist (string), album (true if they want a whole album), name (playlist name), query (song or album search text), "
                                          "shuffle (bool), random (bool: a single random song). The request may be in " + lang_name + ". "
                                          "Keep names exactly as written. Output ONLY the JSON object."},
            {"role": "user", "content": text}], {"num_ctx": 1024, "num_predict": 90, "temperature": 0})
        d = json.loads(re.search(r"\{.*\}", out, re.S).group(0))
        if d.get("kind") in ("newest", "liked", "playlist", "artist", "album", "track"): return d
    except Exception as e:
        _log(f"music parse_llm failed: {e}")
    return None

# ======================================================================= helpers
def _norm(s): return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()
def _sim(a, b):
    a, b = _norm(a), _norm(b)
    if not a or not b: return 0.0
    if a == b: return 1.0
    wa, wb = set(a.split()), set(b.split())
    if wa and (wa <= wb or wb <= wa): return 0.86                          # "gym" -> "Gym Bangers"
    return max(difflib.SequenceMatcher(None, a, b).ratio(), 0.9 if (a in b or b in a) and min(len(a), len(b)) >= 4 else 0)

def _name_variants(name):
    """'hutchers' -> ['hutchers', 'hutcher'] (people drop the apostrophe in "hutcher's")."""
    n = name.strip(" '\"")
    out = [n]
    if re.search(r"[^s]s$", n, re.I) and len(n) > 3: out.append(n[:-1])
    if n.lower().endswith("s'"): out.append(n[:-2])
    return list(dict.fromkeys(out))

# ======================================================================= SPOTIFY
def _sp_device(sp):
    devs = sp.devices()["devices"]
    if not devs:
        ctx["open_app"]("spotify")
        for _ in range(16):
            time.sleep(0.75); devs = sp.devices()["devices"]
            if devs: break
    if not devs: return None
    return (next((d for d in devs if d.get("is_active")), None) or next((d for d in devs if d.get("type") == "Computer"), devs[0]))["id"]

def _sp_artist(sp, name):
    best, score = None, 0
    for v in _name_variants(name):
        try: items = sp.search(q=v, type="artist", limit=5)["artists"]["items"]
        except Exception: items = []
        for i, a in enumerate(items):
            s = max(_sim(v, a["name"]) for v in _name_variants(name)) + (a.get("popularity") or 0) / 1000 - i * 0.01
            if s > score: best, score = a, s
    return best if score >= 0.55 else None

def _sp_play(sp, dev, uris=None, context=None, offset=None, shuffle=None):
    if shuffle is not None:
        try: sp.shuffle(bool(shuffle), device_id=dev)
        except Exception: pass
    kw = {"device_id": dev}
    if uris: kw["uris"] = uris
    if context: kw["context_uri"] = context
    if offset is not None: kw["offset"] = {"position": int(offset)}
    sp.start_playback(**kw)

def _sp_releases(sp, artist_id, groups):
    out = []
    for g in groups:
        try: items = sp.artist_albums(artist_id, include_groups=g, limit=10)["items"]
        except TypeError: items = sp.artist_albums(artist_id, album_type=g, limit=10)["items"]
        except Exception: items = []
        out += items
    return sorted(out, key=lambda a: a.get("release_date") or "", reverse=True)

def spotify_newest(sp, artist, album=False):
    a = _sp_artist(sp, artist)
    if not a: return None, f"I couldn't find an artist called {artist} on Spotify, choom"
    rel = _sp_releases(sp, a["id"], ["album"] if album else ["single", "album"])
    if not rel: return None, f"{a['name']} has nothing out on Spotify"
    r = rel[0]; dev = _sp_device(sp)
    if not dev: return None, "Spotify has no active device. Open it once and ask again."
    when = r.get("release_date", "")
    if album:
        _sp_play(sp, dev, context=r["uri"], shuffle=False); return True, f"playing {a['name']}'s newest album {r['name']} ({when})"
    tr = sp.album_tracks(r["id"], limit=1)["items"]
    if not tr: return None, f"couldn't open {r['name']}"
    _sp_play(sp, dev, context=r["uri"], offset=0, shuffle=False)
    return True, f"playing {a['name']}'s newest: {tr[0]['name']} ({when})"

def spotify_liked(sp, shuffle=True, recent=False):
    total = sp.current_user_saved_tracks(limit=1)["total"]
    if not total: return None, "your Liked Songs on Spotify are empty, choom"
    dev = _sp_device(sp)
    if not dev: return None, "Spotify has no active device. Open it once and ask again."
    if recent or not shuffle:
        items = sp.current_user_saved_tracks(limit=50)["items"]
    else:
        items, seen = [], set()
        for off in random.sample(range(0, max(1, total - 49), 1), k=min(3, max(1, total - 49))) if total > 50 else [0]:
            for it in sp.current_user_saved_tracks(limit=50, offset=off)["items"]:
                if it["track"]["uri"] not in seen: seen.add(it["track"]["uri"]); items.append(it)
        random.shuffle(items)
    uris = [it["track"]["uri"] for it in items if it.get("track")][:60]
    _sp_play(sp, dev, uris=uris, shuffle=False)
    first = items[0]["track"]
    return True, f"playing {first['name']} by {first['artists'][0]['name']} from your Liked Songs" + (" (shuffled)" if shuffle and not recent else "")

def spotify_playlist(sp, name, shuffle=False, one_random=False):
    pls, off = [], 0
    while off < 250:
        page = sp.current_user_playlists(limit=50, offset=off)
        pls += page["items"]; off += 50
        if not page.get("next"): break
    pls = [p for p in pls if p]
    if not pls: return None, "you don't have any playlists on Spotify, choom"
    best = max(pls, key=lambda p: _sim(name, p["name"]))
    if _sim(name, best["name"]) < 0.5: return None, f"I can't find a playlist called {name}. You've got: " + ", ".join(p["name"] for p in pls[:6])
    dev = _sp_device(sp)
    if not dev: return None, "Spotify has no active device. Open it once and ask again."
    total = (best.get("tracks") or {}).get("total") or (best.get("items") or {}).get("total") or 0
    if one_random or shuffle:
        pos = random.randrange(total) if total else 0
        _sp_play(sp, dev, context=best["uri"], offset=pos, shuffle=True)
        return True, f"shuffling your {best['name']} playlist"
    _sp_play(sp, dev, context=best["uri"], shuffle=False)
    return True, f"playing your {best['name']} playlist"

def spotify_artist(sp, artist):
    a = _sp_artist(sp, artist)
    if not a: return None, f"I couldn't find {artist} on Spotify"
    dev = _sp_device(sp)
    if not dev: return None, "Spotify has no active device. Open it once and ask again."
    _sp_play(sp, dev, context=a["uri"], shuffle=True)        # the artist's own "This is" style context: their popular tracks
    return True, f"playing {a['name']}"

def spotify_album(sp, query):
    hits = sp.search(q=query, type="album", limit=1)["albums"]["items"]
    if not hits: return None, f"no album found for {query}"
    dev = _sp_device(sp)
    if not dev: return None, "Spotify has no active device. Open it once and ask again."
    _sp_play(sp, dev, context=hits[0]["uri"], shuffle=False)
    return True, f"playing the album {hits[0]['name']} by {hits[0]['artists'][0]['name']}"

# ======================================================================= YOUTUBE / YOUTUBE MUSIC
_ytm = None
def _yt():
    global _ytm
    if _ytm is None:
        from ytmusicapi import YTMusic
        _ytm = YTMusic()
    return _ytm

def _yt_open(vid, service, radio=False):
    host = "https://music.youtube.com" if service == "youtube music" else "https://www.youtube.com"
    url = f"{host}/watch?v={vid}" + (f"&list=RDAMVM{vid}" if radio else "") + ("" if service == "youtube music" else "&autoplay=1")
    ctx["open_url"](url)

def _ytm_artist(name):
    best, score = None, 0
    for v in _name_variants(name):
        for i, a in enumerate(_yt().search(v, filter="artists", limit=5)[:5]):
            s = max(_sim(x, a.get("artist") or a.get("title") or "") for x in _name_variants(name)) - i * 0.02
            if s > score: best, score = a, s
    return best if score >= 0.55 else None

def youtube_newest(artist, service, album=False):
    try:
        a = _ytm_artist(artist)
        if not a: raise LookupError("no artist")
        page = _yt().get_artist(a["browseId"]); aname = page.get("name") or a.get("artist")
        cands = []
        for sec in (["albums"] if album else ["singles", "albums"]):
            for i, r in enumerate(((page.get(sec) or {}).get("results") or [])[:4]):
                try: yr = int(re.sub(r"\D", "", str(r.get("year") or "0"))[:4] or 0)
                except Exception: yr = 0
                cands.append((yr, -i, sec == "singles", r))
        if not cands: raise LookupError("no releases")
        cands.sort(key=lambda c: (c[0], c[2], c[1]), reverse=True)        # newest year; singles first; keep the page's own order
        rel = cands[0][3]
        alb = _yt().get_album(rel["browseId"])
        tracks = [t for t in alb.get("tracks", []) if t.get("videoId")]
        if not tracks: raise LookupError("empty release")
        if album and alb.get("audioPlaylistId"):
            ctx["open_url"](("https://music.youtube.com" if service == "youtube music" else "https://www.youtube.com") + f"/watch?v={tracks[0]['videoId']}&list={alb['audioPlaylistId']}")
            return f"playing {aname}'s newest album {alb.get('title')}"
        _yt_open(tracks[0]["videoId"], service)
        return f"playing {aname}'s newest: {tracks[0].get('title')}" + (f" ({rel.get('year')})" if rel.get("year") else "")
    except ImportError:
        pass
    except Exception as e:
        _log(f"youtube_newest via ytmusicapi failed: {e}")
    vid, title = ctx["yt_lookup"](f"{artist} new {'album' if album else 'song'} {time.strftime('%Y')}")
    if not vid: return f"I couldn't find anything new from {artist}"
    _yt_open(vid, service); return f"playing {title} (my best guess at {artist}'s newest)"

def youtube_artist(artist, service):
    try:
        a = _ytm_artist(artist)
        if a:
            page = _yt().get_artist(a["browseId"])
            songs = [s for s in ((page.get("songs") or {}).get("results") or []) if s.get("videoId")]
            if songs:
                _yt_open(songs[0]["videoId"], service, radio=True); return f"playing {page.get('name')}: {songs[0].get('title')} and more"
    except ImportError: pass
    except Exception as e: _log(f"youtube_artist failed: {e}")
    vid, title = ctx["yt_lookup"](f"{artist} top songs")
    if vid: _yt_open(vid, service, radio=True); return f"playing {title}"
    return f"I couldn't find {artist}"

def youtube_album(query, service):
    try:
        hits = _yt().search(query, filter="albums", limit=1)
        if hits:
            alb = _yt().get_album(hits[0]["browseId"]); tr = [t for t in alb.get("tracks", []) if t.get("videoId")]
            if tr:
                ctx["open_url"](("https://music.youtube.com" if service == "youtube music" else "https://www.youtube.com") + f"/watch?v={tr[0]['videoId']}" + (f"&list={alb['audioPlaylistId']}" if alb.get("audioPlaylistId") else ""))
                return f"playing the album {alb.get('title')}"
    except ImportError: pass
    except Exception as e: _log(f"youtube_album failed: {e}")
    vid, title = ctx["yt_lookup"](query + " full album")
    if vid: _yt_open(vid, service); return f"playing {title}"
    return f"no album found for {query}"

def youtube_liked(service, shuffle=True):
    """Uses YOUR signed-in browser: YouTube Music 'Liked music' (LM) or YouTube 'Liked videos' (LL). A random start position = a random song."""
    idx = random.randint(1, 40) if shuffle else 1
    if service == "youtube music":
        ctx["open_url"](f"https://music.youtube.com/watch?list=LM&index={idx}")
        return "playing a random pick from your Liked music on YouTube Music" if shuffle else "playing your Liked music"
    ctx["open_url"](f"https://www.youtube.com/watch?list=LL&index={idx}")
    return "playing a random pick from your Liked videos on YouTube" if shuffle else "playing your Liked videos"

def youtube_playlist(name, service):
    host = "https://music.youtube.com/library/playlists" if service == "youtube music" else "https://www.youtube.com/feed/playlists"
    ctx["open_url"](host)
    return f"YouTube won't let me read your playlists without a login, so I opened your playlists: click {name}"

# ======================================================================= the one entry point
def play(text, service, plain_play, lang_name="English", allow_llm=True):
    """text = what comes after 'play'. service = spotify / youtube / youtube music / ... plain_play(query) is the old simple search-and-play.
       Returns what she says."""
    intent = parse(text)
    if intent is None and allow_llm and (HINTS.search(text) or lang_name != "English"):
        intent = parse_llm(text, lang_name)
    if not intent or intent.get("kind") == "track":
        return plain_play((intent or {}).get("query") or text)
    k = intent["kind"]; svc = (service or "spotify").lower()
    if svc == "spotify" and SPA.configured():                 # SpotAPI session (no developer app / Premium needed): try it first
        try:
            if k == "newest": return SPA.newest(intent.get("artist") or text, bool(intent.get("album")))
            if k == "liked": return SPA.liked(bool(intent.get("shuffle", True) or intent.get("random", False)))
            if k == "playlist": return SPA.playlist(intent.get("name") or text, bool(intent.get("shuffle") or intent.get("random")))
            if k == "artist": return SPA.artist(intent.get("artist") or text)
            if k == "album": return SPA.album(intent.get("query") or text)
        except Exception as e:
            _log(f"spotapi smart play failed, trying the official API: {e}")
    if svc == "spotify":
        sp = ctx["spotify_client"]()
        if sp is None:
            if k == "liked":
                ctx["open_url"]("https://open.spotify.com/collection/tracks"); return "opened your Liked Songs (run spotify_setup.py once so I can pick and play songs myself)"
            return plain_play(intent.get("artist") or intent.get("name") or intent.get("query") or text)
        try:
            if k == "newest": ok, say = spotify_newest(sp, intent.get("artist") or text, bool(intent.get("album")))
            elif k == "liked": ok, say = spotify_liked(sp, intent.get("shuffle", True) or intent.get("random", False), intent.get("recent", False))
            elif k == "playlist": ok, say = spotify_playlist(sp, intent.get("name") or text, intent.get("shuffle", False), intent.get("random", False))
            elif k == "artist": ok, say = spotify_artist(sp, intent.get("artist") or text)
            elif k == "album": ok, say = spotify_album(sp, intent.get("query") or text)
            else: return plain_play(text)
            return say
        except Exception as e:
            _log(f"spotify smart play failed: {e}")
            msg = str(e)
            if "403" in msg: return "Spotify said no (403): playback control needs Premium, choom"
            if "scope" in msg.lower() or "401" in msg: return "Spotify needs a quick re-login for your library: run spotify_setup.py once more"
            return plain_play(intent.get("artist") or intent.get("query") or text)
    if svc in ("youtube", "youtube music"):
        if k == "newest": return youtube_newest(intent.get("artist") or text, svc, bool(intent.get("album")))
        if k == "liked": return youtube_liked(svc, intent.get("shuffle", True) or intent.get("random", False))
        if k == "playlist": return youtube_playlist(intent.get("name") or text, svc)
        if k == "artist": return youtube_artist(intent.get("artist") or text, svc)
        if k == "album": return youtube_album(intent.get("query") or text, svc)
    return plain_play(intent.get("artist") or intent.get("query") or text)
