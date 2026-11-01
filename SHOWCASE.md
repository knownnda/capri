# Capri: showcase guide (what works, what to say, what to watch out for)

Run `python check.py` (Start Menu > Capri > readiness check) before you record. Anything marked [ !! ] needs fixing first.

## Before you hit record (2 minutes)
- Open the **Spotify app** and play any song for a second (makes it the active device), then pause it.
- Open your browser and make sure you're **signed into Google** (for the Google Docs essay).
- For Minecraft: launch the **fabric-loader** profile and load a single-player world, then alt-tab out.
- Close anything private: the clip buffer records the last 30 s of your screen.

## The v4 demo (5 minutes, best order)
1. **The installer** (record this once): run CapriSetup.exe, pick **Français** (or any language) in the very first window. Capri then answers in French, and the right-click menu shows LANGUAGE: FRANÇAIS. Say "speak English" to switch back live.
2. **Wake + call**: "Hey Capri". She rings, picks up, hands-free from there.
3. **Smart music**: "music mode" then
   - "play hutchers newest song": she finds the artist (even with the 's') and plays their latest release.
   - "play a random song from my liked songs": shuffled from YOUR likes.
   - "play my gym playlist" (use a real playlist name of yours).
   - "pause" / "next" / "volume up" (instant).
   - "play blinding lights on youtube": override to YouTube in the same mode.
4. **Homework, the crowd-pleaser**: "homework mode" then "write a 400 word essay on the french revolution".
   Google Docs opens a new doc **while** she writes, then she types it in live, paragraph by paragraph, and makes the first line a big title.
   Click away mid-essay: she pauses ("click back into your document"). Click back: she carries on. Say "stop": she stops and puts the rest on your clipboard.
   Variations: "...in word", "...in notepad", "...here" (types where your cursor is).
5. **Minecraft autopilot**: "gaming mode" then "get me 10 diamonds" (or "chop 32 wood" for a quick one). The pink AUTOPILOT frame appears and your player moves on its own.
   Press **F8** or say "my turn": you get control back instantly. Save "beat the game for me" for the end: it's a long run (hours), so show the first few minutes.
6. **Timer HUD**: "start a timer for 1 minute" -> "yes" -> countdown top-left -> she calls you back (red card).
7. **Research**: "research mode" -> "research 2pac and all his albums".
8. **Clip**: during the Minecraft part say "clip that": an mp4 of the last 30 s lands in Videos\Capri Clips.
9. **Personality**: insult her. She snaps back.
10. **Flatline finale**: "power off my pc" -> "yes" -> press ESC halfway for a safe demo.

## Lines that land well on camera
- "Hey Capri, play hutchers newest song" (wake + action in one breath)
- "Write a 300 word essay on why cats are better than dogs in Google Docs"
- "Get me a stack of wood" -> "build a house" (have ~200 planks first: "get planks")
- "Speak Japanese" -> ask her anything -> "speak English"
- "What do you know about me?" after telling her a couple of things earlier

## Older demo list (still works)
1. **Wake + holocall** (needs a mic). Say "Hey Capri". She pops up, the green call card rings, she picks up. Then speak normally, hands-free.
   *Risk:* a noisy room/TV can trigger or confuse her: use the config menu > SYSTEM > MICROPHONE or WAKE WORDS: NAME ONLY.
2. **Instant commands** (no AI wait): "pause", "volume up", "open youtube", "google best ramen near me", "what time is it".
3. **Music mode + Spotify auto-play**: "Music mode" -> "play pain 1993 by drake" (starts instantly). Then "play hotline bling on youtube" to show the override.
   *Needs:* `python spotify_setup.py` once (option 1 = paste one cookie).
4. **Timer HUD**: "start a timer for 1 minute" -> "Is that all?" -> "yes" -> she hangs up, a countdown (00:50...) appears top-left, then she calls you back with the RED card. Click it.
5. **Homework mode** (very visual): "Homework mode" -> "write a 300 word essay on the french revolution". Google Docs (default) opens and she types it in.
6. **Research mode**: "Research mode" -> she asks what to research -> "research 2pac and all his albums". She opens Wikipedia and lists grouped bullet points.
   *Reality check:* it takes 1-2 minutes on CPU with a 3B model. Much faster/better with a GPU or an API brain (providers.json).
7. **Typing into YouTube's search bar**: open YouTube in Chrome, say "type vanessa from venezuela by 3582".
8. **Files**: "make a file called ideas on my desktop", "fix the errors in notes dot txt", then "undo".
9. **Memory**: "my favorite food is spicy ramen" ... later "what's my favorite food?".
10. **Personality**: insult her. She snaps back and sometimes pops an angry-face picture in your browser.
11. **Clip** (great for gamers): play anything, say "clip that". Beep, then a second beep and the mp4 appears in Videos\Capri Clips. Needs the clip buffer on (it is by default).
12. **Flatline (do this one LAST)**: save everything, then say "power off my pc" -> "yes". Full-screen flatline, then the PC shuts down. (ESC aborts.) For a safe demo, say "yes" then press ESC halfway: it shows the whole effect without powering off.
13. **Style points**: right-click her (Cyberpunk-menu config), change SIZE, wait ~1 minute and she glitches to a new spot.

## Most reliable for a live demo
Instant commands, clip (video only if sound capture isn't available), timers + countdown, files (create/edit/undo), memory, config menu, music with Spotify set up, homework typing into Notepad.

## Depends on your setup (test before showing)
Wake word + hands-free voice (mic/room/accent), research quality (model + internet), SpotAPI (unofficial: can break when Spotify updates their site), Minecraft autopilot (she plays by eye: slow, can get stuck or die), launching Steam/Riot games, typing into YouTube (Chrome/Edge/Brave only).

## Things that can't do what you might expect
- Netflix/Disney+/Prime/Twitch: she pulls up the title's page, but you press play (those sites block autoplay).
- She cannot "see" a button and click it by name; she uses keyboard shortcuts (YouTube "/", Spotify Ctrl+L, Explorer Ctrl+E...).
- Everything runs on your PC. Nothing is sent anywhere except web searches/Spotify when you use them.
