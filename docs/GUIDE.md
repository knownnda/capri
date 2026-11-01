# Capri: full guide

## Install (one installer, does everything)
Run **CapriSetup.exe**. The FIRST window asks for the setup language: **that is the language Capri will speak and listen in.**
(16 languages: English, Français, Deutsch, Español, Italiano, Português, Nederlands, Polski, Русский, Türkçe, Українська, 日本語, 한국어, العربية, 中文, हिन्दी.
A language only shows up in that first window if Inno Setup has a translation for it; any of them can still be picked later with right-click Capri > LANGUAGE.)
It then downloads whatever is missing and sets it up:
- Python 3.12 (skipped if you already have 3.10-3.13) and a private Python environment with all her packages
- Ollama + the AI model that speaks your language best (llama3.2:3b for English/French/German/Spanish/Italian/Portuguese, qwen2.5:3b for the rest)
- her ears (speech-recognition model for your language) and her voice (a Piper voice in your language, where one exists)
- optional: Minecraft autopilot (no mods) and Spotify auto-play
- Start Menu shortcuts (Capri, desktop mate, readiness check, Repair), desktop icon, start-with-Windows (tray)
Downloads take a while (about 3 GB in total). The black window shows progress; install_log.txt has the details. Start Menu > Capri > Repair re-runs any step that failed.

**Making the installer:** double-click build_installer.bat -> installer\Output\CapriSetup.exe (it installs Inno Setup for you with winget if needed).
Web installer (a tiny exe that downloads Capri herself): zip this folder, upload it anywhere, then `build_installer.bat web https://your.link/capri.zip` -> CapriWebSetup.exe.

## Manual install (developers)
1. Install Ollama (https://ollama.com) then:
   ollama pull llama3.1:8b
   ollama pull llama3.2-vision
2. pip install -r requirements.txt
3. python server.py   -> opens http://127.0.0.1:7777

Try: "put on a lofi video on youtube", "open spotify", "what's on my screen?",
"open notepad" then "write a 200 word essay on cybersecurity" (click into the doc within 2.5s).

Safety: localhost only, rejects other websites, STOP button, and slamming your mouse into a screen corner kills pyautogui.
Voice input in Chrome/Edge may use the browser's cloud speech service (voice output is local).
Swap models: set CAPRI_MODEL / CAPRI_VISION env vars.

## Spotify auto-play (Premium needed)
1. developer.spotify.com/dashboard -> Create app, redirect URI: http://127.0.0.1:8888/callback
2. Windows (PowerShell), in the same window you run the server:
   $env:SPOTIPY_CLIENT_ID="your_id"; $env:SPOTIPY_CLIENT_SECRET="your_secret"; python server.py
3. First play opens a browser to log in once.

## Voice
Text only: she doesn't speak out loud. You talk to her with the mic icon or by just talking during a call.

## Lore (who she is)
python transcribe_lore.py  -> reads lore/scene.mp3, writes lore/lore.txt. Restart server.py.
You can also just write lore/lore.txt yourself.

## Desktop app
Double-click run.bat -> CAPRI opens as a transparent always-on-top desktop window (PySide6) at the bottom-right of your screen (no browser). Drag her anywhere that is not a button..
For a real .exe: double-click build_exe.bat -> dist/CAPRI.exe (Ollama still needs to be installed).

## Calls
- Click CALL CAPRI (or press P) -> call screen -> CALL. Green = you're calling; ringtone plays, she picks up, then it's hands-free voice (just talk, she answers).
- She can call you: say "call me in 5 minutes to remind me about X". Red = Capri calling. A = answer, D = decline.
- Type /ring in the box to test an incoming call right now.
## Lore
lore/lore.txt is who she is (a personality construct, not a netrunner). Edit it freely.

## Speed
- For the fastest replies: ollama pull llama3.2:3b (she auto-picks it if installed; otherwise she uses what you have). Force one with CAPRI_MODEL.
- Her words stream in as they're generated, tools run in the background, and the model + mic model are loaded at startup.
- Mic model: CAPRI_STT=tiny.en is even faster (a bit less accurate); default is base.en.

## Hey Capri (voice activation + tray)
- Closing her (C key / the hang-up after a voice call) tucks her into the system tray (bottom-right, near the clock). She keeps listening locally for "Hey Capri" / "Call Capri" / "Activate mic".
- When she hears it she pops up, does the ringing effect, and picks up. Say "hang up" to end the call (she tucks back into the tray if a wake word started it).
- run_tray.bat starts her hidden in the tray. For auto-start with Windows: press Win+R, type shell:startup, put a shortcut to run_tray.bat there.
- Tray icon right-click: Show Capri / Listen for "Hey Capri" (untick to turn the always-listening off) / Quit.
- It uses a tiny local speech model; nothing leaves your PC. Heard phrases are logged in capri_log.txt for debugging.

## Files (she can work with your files)
Inside your user folder only (Desktop, Documents, Downloads...). Ask things like:
- "find notes dot txt on my desktop" / "open my CV"
- "what does main dot py do?" / "summarize my essay file"
- "fix the errors in essay dot txt": she saves a fixed COPY (name.capri-fixed.ext) and never touches the original. Say "apply it" to replace the original; it's backed up in capri_backups first.

## Bring your own AI (providers.json)
Copy entries from providers.example.json into providers.json. Works with anything OpenAI-compatible (OpenAI, Groq, OpenRouter, LM Studio, DeepSeek...), Claude, or local Ollama.
Switch brains by saying/typing "use groq", "switch to claude", "use local" or from the tray icon > AI brain.
Keys: put "api_key" in the file, or "api_key_env": "SOME_ENV_VAR". Her "look at my screen" stays local unless the provider has "vision": true.

## If "Hey Capri" doesn't trigger
The first screen shows a status line: WAKE: LISTENING, a MIC level meter and what she last HEARD. If the meter stays empty your mic isn't reaching her (set CAPRI_MIC to your mic's name/number; devices are listed in capri_log.txt). If she hears the words wrong, tell me what she heard.
"Hey Capri, play X" works too: she picks up and does it straight away.

## Desktop Capri (desktop mate) - OPTIONAL, run_mate.bat
- She lives on your desktop: a transparent always-on-top Capri that teleports (glitch out/in) to the top edge of your windows and sits there swinging her legs, or stands on the taskbar. She rides along if you drag the window she's sitting on, and teleports to a new spot every 45-110 s (not during calls).
- Click her for a menu: CALL CAPRI / TELEPORT / HIDE. There's also a small green call button by her hip.
- Calling: she pulls out her phone (it buzzes when she's calling you), the green/red call card appears, then she puts it to her ear and the chat window docks next to her. Hang up and she tucks the window away.
- "Hey Capri" / "Call Capri" teleports her in if she's hidden. Tray icon: show/hide desktop Capri, wake words on/off, AI brain.
- Window perching works on Windows. It is OFF by default (normal mode = call window with her picture). Start it with run_mate.bat or: python server.py --mate

## Listening better (accents)
- Calls and the mic now use the small.en model (more accurate than base.en, a bit slower; ~480 MB download the first time). CAPRI_STT=base.en for speed, CAPRI_STT=medium.en for even better accuracy. Non-English or heavy accents: CAPRI_LANG=auto.
- Audio goes to the model untouched (no re-encoding), the start of your sentence is no longer clipped, quiet mics get boosted, and the wake word uses base.en with looser spelling matching.

## Timers & reminders (they ring you in the background)
- "set a timer for 10 minutes", "remind me to call my mom in 10 minutes", "call me in half an hour to stretch", "remind me at 5pm to ...".
- They survive closing the window (she hides in the tray) and even a restart (reminders.json). When one is due she pops up with the RED calling card; click it (or press A) and she tells you it's time / what the reminder was.
- "what timers do I have" / "cancel my timers".

## Memory
- She remembers things you tell her ("my favorite food is ramen", "I live in Leeds", "remember that my exam is Friday") in capri_memory.json on your PC, and uses them later ("what's my favorite food?").
- "what do you know about me", "forget my dog". Delete capri_memory.json to wipe everything.

## Research
- "research 2pac" / "deep search the Roman empire": she pulls up the Wikipedia page (or a top web result), reads Wikipedia + a web search, and gives you 5 key facts.

## Files
- "make a file called ideas on my desktop" / "make a python script that ... in documents": she creates it and shows it in File Explorer. "make a folder called school".
- "fix the errors in essay dot txt" / "make notes dot txt shorter": she edits the file directly, keeps a backup in capri_backups, never saves an edit that breaks Python/JSON, and "undo" puts it back. Long files are done in pieces.

## Her keyboard and mouse
- She knows which window you're looking at (and what else is open). "type vanessa from venezuela by 3582" types into the tab/app you were using; "search ... here" puts it in the search box of YouTube / Google / Spotify / Explorer and hits Enter. Also click, scroll, switch window, press keys.

## Arguments
- Insult her and she snaps back; sometimes (not always, with a cooldown) she pops open an angry-face picture in your browser. Apologize or praise her and she gets smug or happy. Turn the pop-ups off with CAPRI_MOODWEB=0.

## Hearing accents better
- With an NVIDIA GPU she now automatically uses the big accurate speech model (medium.en) on it. Without one: small.en on CPU. Force one with CAPRI_STT=large-v3 etc., or CAPRI_LANG=auto for other languages.
- Wake: just say "Capri" (also "Hey Capri", "Call Capri", "Activate mic").

## If she crashes or errors
- run.bat now starts her through launcher.py: if she ever crashes she restarts herself in 2 s and the reason goes to capri_log.txt. (Quit from the tray menu stops her for real.)
- "My brain isn't answering" = Ollama wasn't running. She now starts Ollama herself (and checks every 15 s), so you shouldn't see that again. If Ollama isn't installed she says so.
- Her background workers (mic, timers, window tracking) restart themselves if they fail.
- Typing into YouTube: she clicks a blank spot in YouTube's header so the PAGE has focus (not the address bar), presses "/" (YouTube's own jump-to-search), types, and hits Enter. Works in Chrome/Edge/Brave.
- Send me capri_log.txt if anything still misbehaves.

## v3: modes, right-click menu, timers on screen
**Right-click Capri** (anywhere on her window, or click the MODE tab) for the config menu: pick a mode, change each mode's DEFAULT app, how she writes homework, Minecraft edition, window SIZE, VOICE (beeps / Piper / Voicebox / API / off, beep tone and volume), microphone on/off, glitch-around on/off.

**Modes** (say "music mode", "research mode", "homework mode", "gaming mode", "watching mode", "normal mode", or click them in the menu). She always uses the mode's DEFAULT unless you name another service in the same sentence.
- Music: "play pain 1993 by drake" -> default app (Spotify / YouTube / YouTube Music / Apple Music / SoundCloud). "play pain 1993 by drake on youtube" -> YouTube whatever the default is.
- Research: she asks "What should I research on?" You answer ("research drake and all his albums and every song and their meaning"). She plans several searches, reads Wikipedia + the top pages, and gives precise bullet points. She keeps asking for the next subject until you leave the mode.
- Homework: "write a 500 word essay on the french revolution" -> opens your default (Word / Google Docs / Notepad / the window you're in) and TYPES it with your keyboard (or pastes instantly, your choice in the menu). Click into the place you want first if you chose "here".
- Gaming: "launch stardew valley" -> finds it in your Steam library (all library folders), Riot Client (Valorant, League...), Roblox, Epic (Fortnite...), Minecraft ("bedrock or java?" unless you set a default), else the Start Menu. Your default launcher is checked first.
- Watching: "play Mr Beast's latest video" -> plays it on YouTube. "play stellar blade" on Netflix/Disney+/Prime/Twitch -> pulls up the title there (those sites don't allow autoplay, so you press play).

**Timers and reminders**: "start a timer for 1 minute" -> she asks "Is that all?" -> say "yes" -> "I'll call you when it's done, choom!" and hangs up. A countdown (00:50, 1:20...) shows in the top-left corner of the screen until it's done, then she calls you (red card).

**Wake words (only these):** "Hey", "Capri", "Hey Capri", "Call". While she's calling you, say "pick up" or "hang up" (also works in a call: "hang up").
**Voice hearing on/off:** right-click menu > VOICE HEARING, or the tray icon.
**She has a mind of her own:** when you haven't touched her for a while she glitches to a new spot on your screen about once a minute and mutters something (turn off: menu > GLITCH AROUND).

## Training a voice for her
Important: only train on a voice you have the rights to: your own, a friend who agrees, or a properly licensed dataset. I won't help clone a real actor's voice from show audio.
1. Record the dataset: Piper Recording Studio (github.com/rhasspy/piper-recording-studio) walks you through reading ~200-500 sentences. Quiet room, same mic, 22.05 kHz mono. Or make your own LJSpeech-style folder (wavs + metadata.csv).
2. Train with Piper (github.com/rhasspy/piper, see TRAINING.md): preprocess your dataset, then fine-tune from an existing English checkpoint (e.g. "lessac medium") rather than from scratch. A GPU (or free Google Colab) is strongly recommended. When it sounds good, export to ONNX.
3. Put the result in lucy/voices/ as capri.onnx and capri.onnx.json, run pip install piper-tts, then right-click Capri > VOICE > PIPER. She'll use your voice model automatically.

## Speed (v3.1)
- Greetings, time/date, pause/next/volume, "open X", "google X", "play <song> by <artist>" are answered INSTANTLY with no AI call.
- Small talk uses a short prompt and plain-text streaming (much faster than the tool prompt). Only requests that need tools use the full prompt.
- Calls connect in about 1 s; end-of-speech detection is 0.7 s; speech recognition uses greedy decoding on all your CPU threads (CAPRI_STT_BEAM=3 for more accuracy with heavy accents).
- For the biggest boost: ollama pull llama3.2:3b (auto-picked), keep Ollama on your GPU, or add a fast API brain in providers.json.

## Spotify auto-play, step by step
1. You need Spotify PREMIUM (Spotify only lets apps control playback on Premium).
2. Run: python spotify_setup.py   (it walks you through everything below)
3. https://developer.spotify.com/dashboard > Create app. Name "Capri". Redirect URI exactly: http://127.0.0.1:8888/callback  (Add it, then Save). Tick "Web API".
4. App > Settings: copy the Client ID and Client secret into the script when it asks.
5. A browser opens: click Agree. Open the Spotify app (PC or phone) and play anything once so there's an active device.
6. Say: "music mode" then "play pain 1993 by drake". If Spotify is closed she opens it herself.
Problems: "INVALID_CLIENT / redirect" = the Redirect URI isn't EXACTLY the one above. "No active device" = open Spotify and play a song for a second. 403 = not Premium.

## Showcase + readiness
SHOWCASE.md has a 3-minute demo script. python check.py tells you what's ready.

## Clip: "Hey, that was insane" -> say "clip"
- Capri keeps the LAST 30 SECONDS of your screen (and your system sound) in a rolling buffer in MEMORY ONLY. Nothing touches the disk until you clip, and turning the buffer off wipes it.
- Say "clip", "clip that" or "clip it" (works whenever the microphone is on, even while you're in a game), or type it, or use Config menu > CLIP > SAVE A CLIP NOW, or the tray icon > "Save clip now".
- You hear a short beep when she hears you, then a second beep + a tray notification when the mp4 is saved to  Videos\Capri Clips\  ("show my clips" opens the folder).
- Config menu > CLIP: buffer on/off, quality (LOW 540p/12fps, NORMAL 720p/15fps, HIGH 1080p/24fps) and system sound on/off. The first-screen status line shows "CLIP: REC 30s".
- Cost: roughly 10-15% of a CPU core at NORMAL, about 100-200 MB of RAM. If a game stutters, pick LOW or switch the buffer off.
- Needs: pip install mss imageio-ffmpeg soundcard (run.bat installs them). Sound capture uses Windows loopback; if it isn't available she still saves video.
- It records your PRIMARY monitor only. Anything on screen in the last 30 s ends up in a clip if you clip, so don't clip while a password manager is open.

## Her eyes (call screen) and the cursor
- The first screen is just her eyes (the Capricorn gif). Idle: two big eyes looking around. When your cursor lands on her she CUTS to the swarm of eyes, settles into the narrow eyes, and the CALL button (plus mic switch and status) fades in. Move away and she cuts back.

## Flatline: "power off my PC"
- Say or type "power off my pc", "shut down", "shut down my computer" (or "restart my pc"). She asks "You sure, choom?". Say "yes" and a full-screen Cyberpunk flatline plays: heartbeat monitor, the long flatline tone, "FLATLINED" with glitch/tearing, "SIGNAL LOST", CRT collapse to black. The sound bed is cut from your reference track from 10 s onward (static/flatline.mp3). About 7.6 s after you say yes, the PC powers off.
- Abort any time before it ends: ESC, click, or say "cancel"/"stop".
- It FORCES apps closed (shutdown /f), so unsaved work is lost. Save first!

## v4: her language, smart music, Minecraft autopilot
**Language.** Picked by the installer (see Install). Change it any time: right-click > LANGUAGE, or say "speak French" / "switch to Japanese".
She answers in that language (keeping her slang: choom, preem, delta), hears it (multilingual Whisper instead of the English-only model), and speaks it if you have a voice for it.
Her quick canned lines are translated once by her brain and cached in capri_translations.json.

**Music mode, smart requests** (Spotify, YouTube, YouTube Music):
- "play hutchers newest song" -> finds the artist (fuzzy: "hutchers" also tries "Hutcher") and plays their latest release
- "play drake's newest album" / "play the latest album by SZA"
- "play a random song from my liked songs" / "shuffle my liked playlist" / "play my liked songs in order"
- "play my gym playlist" / "shuffle my chill playlist" (Spotify reads your playlists; YouTube opens your playlist page)
- "play some kendrick" / "play the album to pimp a butterfly" / plain "play pain 1993 by drake" still works
Spotify: run spotify_setup.py again once after updating (she now needs permission to read your Liked Songs and playlists). Needs Premium.
YouTube Music liked songs use the account you're signed into in your browser.

**Gaming mode autopilot: she plays Minecraft for you** (Java Edition, no mods): see "Minecraft autopilot" in the main README.

## v4.1: Spotify through SpotAPI, homework rebuilt
**Spotify without a developer app.** `python spotify_setup.py` -> option 1: paste your `sp_dc` cookie from open.spotify.com (F12 > Application > Cookies).
Capri then drives Spotify the way the web player does ([SpotAPI](https://github.com/Aran404/SpotAPI)): songs, newest releases, liked songs, your playlists, artists, albums.
It plays on whichever Spotify is open (desktop app, web player or phone); if none is, she opens the desktop app and waits for it.
The cookie stays in spotapi_session.json on your PC (it's your login: never share it; the installer never packages it). Cookies expire now and then: run the setup again.
Heads up: SpotAPI uses Spotify's private, unofficial API. It's against Spotify's terms (your own account, your call) and it can break when Spotify updates the web player.
If it fails, she automatically falls back to the official API (spotify.json, option 2) and then to opening Spotify search.

**Homework mode, rebuilt** (default app is now Google Docs):
- She opens the doc while the essay is being written, waits until that exact window is really there (no blind timers), then types into it.
- Types with Unicode keystrokes: works on any keyboard layout (AZERTY, QWERTZ...) and in every language she speaks (accents, Cyrillic, Japanese...).
- Never types into the wrong window: click away and she pauses until you're back (after a minute she stops and puts the rest on your clipboard). Say "stop" any time.
- Not signed into Google? She tells you and leaves the essay on your clipboard instead of typing into the login page.
- Word not installed? She uses Google Docs. Notepad: she opens a fresh tab (Windows 11 reopens your old ones).
- Better essays: title + intro with a thesis + body paragraphs with facts + conclusion; if the model stops short she asks it to finish. First line becomes a Heading (English keyboards).
- Pick the app per request: "...in word", "...in google docs", "...in notepad", "...here". Length: "500 word essay", "an essay on X that's 800 words".
