"""
One-time Spotify setup so Capri can start songs instantly:   python spotify_setup.py
  1) EASY (SpotAPI): paste one cookie from the Spotify web player. No developer app, no client ID/secret.
  2) OFFICIAL Web API: Spotify PREMIUM + a free developer app (the script tells you exactly what to click).
"""
import json, os, sys, time, webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "spotify.json")
REDIRECT = "http://127.0.0.1:8888/callback"
SCOPE = "user-modify-playback-state user-read-playback-state user-library-read playlist-read-private playlist-read-collaborative"   # library = liked songs + your playlists

def spotapi_setup():
    sys.path.insert(0, HERE)
    import spotapi_play as SPA
    print("""
=== Connect Capri to Spotify (SpotAPI, the easy way) ===
Capri will control Spotify the same way the Spotify web player does, using your own login cookie.
Heads up: this is Spotify's unofficial private API. It's against Spotify's terms and can break when Spotify updates,
so it's at your own risk on your own account. The cookie is your login: it stays in spotapi_session.json on this PC only, never share it.

1) A browser opens https://open.spotify.com : log in there if you aren't already.
2) Press F12 (developer tools).
     Chrome / Edge / Brave / Opera:  Application tab > Storage > Cookies > https://open.spotify.com
     Firefox:                        Storage tab > Cookies > https://open.spotify.com
3) Find the row named  sp_dc  and double-click its Value, copy it (it's long, starts with AQ...).
""")
    try: webbrowser.open("https://open.spotify.com")
    except Exception: pass
    cookies = {}
    while not cookies:
        cookies = SPA.parse_cookies(input("Paste the sp_dc value here: "))
        if not cookies.get("sp_dc") or len(cookies["sp_dc"]) < 50:
            print("That doesn't look like sp_dc (it's well over 100 characters). Try again."); cookies = {}
    user = input("Your Spotify USERNAME (spotify.com > Account > Edit profile; press Enter to let me find it): ").strip()
    SPA.save_session(user or "me", cookies)
    print("\nSaved spotapi_session.json. Testing...")
    try:
        import spotapi  # noqa: F401
    except Exception as e:
        print("SpotAPI isn't installed:", e, "\nRun:  python -m pip install spotapi websockets pymongo redis   and start this again."); return 1
    try:
        print("  logged in as:", SPA._username())
    except Exception as e:
        print("  couldn't read your account (", str(e)[:120], ")\n  -> the cookie is probably wrong or expired: log in on open.spotify.com again and copy a fresh sp_dc."); return 1
    print("\nNow open the Spotify app on this PC and play any song for a second (that makes it the active device).")
    if input("Done? Play a test song now? (y/n): ").strip().lower().startswith("y"):
        try: print("  " + SPA.track("Blinding Lights The Weeknd"))
        except Exception as e: print("  test failed:", str(e)[:200]); return 1
    print("\nAll set! Say: 'music mode' then 'play hutchers newest song' / 'play a random song from my liked songs' / 'play my gym playlist'.")
    print("If Spotify ever stops responding, run this again with a fresh sp_dc (cookies expire after a while).")
    return 0

print("\nHow should Capri control Spotify?\n  [1] EASY: SpotAPI, paste one cookie (recommended)\n  [2] OFFICIAL: Spotify developer app (needs Premium)")
if input("Pick 1 or 2 [1]: ").strip() != "2":
    code = spotapi_setup()
    try: input("\nPress Enter to close.")
    except EOFError: pass
    sys.exit(code)

print("""
=== Connect Capri to Spotify ===
1) Open  https://developer.spotify.com/dashboard  and log in with the Spotify account you listen with.
2) Click "Create app".  Name: Capri   Description: my desktop assistant
3) Redirect URI (type it EXACTLY, then click Add):
       %s
4) Tick "Web API", accept the terms, click Save.
5) Open the app > Settings. Copy the "Client ID", click "View client secret" and copy that too.
""" % REDIRECT)
try: webbrowser.open("https://developer.spotify.com/dashboard")
except Exception: pass

cid = input("Paste your Client ID here: ").strip()
sec = input("Paste your Client secret here: ").strip()
if len(cid) < 20 or len(sec) < 20:
    print("\nThose don't look right (both are about 32 characters). Try again."); sys.exit(1)
json.dump({"client_id": cid, "client_secret": sec, "redirect_uri": REDIRECT}, open(CFG, "w"), indent=1)
print("\nSaved spotify.json. Now a browser opens: click 'Agree' to let Capri control playback.")

try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth
except ImportError:
    print("Run:  pip install spotipy   and start this again."); sys.exit(1)

auth = SpotifyOAuth(client_id=cid, client_secret=sec, redirect_uri=REDIRECT, scope=SCOPE, cache_path=os.path.join(HERE, ".spotify_cache"), open_browser=True)
sp = spotipy.Spotify(auth_manager=auth)
try:
    me = sp.current_user(); print("\nConnected as:", me.get("display_name") or me.get("id"))
except Exception as e:
    print("\nLogin failed:", e, "\n(Most common cause: the Redirect URI in the dashboard is not exactly %s)" % REDIRECT); sys.exit(1)

devs = sp.devices().get("devices", [])
if not devs:
    print("\nNo Spotify device is open right now. Open the Spotify app on this PC (or your phone), play any song for a second, then run this script again to test.")
    print("Setup itself is done: 'play <song> by <artist>' will work once Spotify is open.")
    sys.exit(0)
print("Devices found:", ", ".join(d["name"] for d in devs))
if input("Play a test song now? (y/n): ").strip().lower().startswith("y"):
    t = sp.search(q="Blinding Lights The Weeknd", type="track", limit=1)["tracks"]["items"][0]
    dev = next((d for d in devs if d.get("is_active")), devs[0])
    sp.start_playback(device_id=dev["id"], uris=[t["uri"]])
    print("Playing:", t["name"], "-", t["artists"][0]["name"])
print("\nAll set! Tell Capri: 'play pain 1993 by drake' (music mode, Spotify default) or 'play <song> on spotify'.")
