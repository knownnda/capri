# Capri plays Minecraft LIVE on TikTok: step by step

## Once (setup, ~15 minutes)
1. **Minecraft autopilot**: in this folder run `python minecraft_setup.py` (installs the screen-reading OCR packages, no mods). In Minecraft put a pickaxe in slot 1, blocks in slot 2, food in slot 9, and press F3 once.
2. **Stream setup**: double-click `stream_setup.bat`. It installs OBS (if missing) and TikTokLive, builds the OBS scene **Capri Live**
   (1920x1080: Capri gif top-left, chat top-right, Minecraft in the middle, her replies in the black box at the bottom) and opens OBS on it.
   (There's also an optional vertical version: Profile 'Capri Vertical' + Scene Collection 'Capri Live (vertical)'.)
   If OBS asks about the Auto-Configuration Wizard, click **No**.
3. **Voice (optional)**: she uses whatever is picked in right-click Capri > VOICE (CAPRI BEEPS by default). In OBS, tick "Control audio via OBS" on the Capri overlay source so viewers hear her.

## Every stream
1. Start **Capri** (run.bat) and wait ~20 s.
2. Start **Minecraft** with the **fabric-loader** profile, load a single-player world, press **F11** for windowed-fullscreen-ish focus.
3. Open **OBS** (Start Menu) > Profile menu: **Capri**, Scene Collection menu: **Capri Live**.
   You should see Minecraft behind the overlay. Black? Click the eye on **Minecraft backup** and hide **Minecraft**.
4. **Get your TikTok stream key**: in your browser go to **livecenter.tiktok.com/producer** > pick a category + title > **Save & Go LIVE**.
   Scroll down: copy the **Server URL** and **Stream Key** (they change every stream: never share the key).
5. OBS > **Settings > Stream** > Service: **Custom** > paste Server URL into *Server* and the key into *Stream Key* > OK.
6. OBS > **Start Streaming**. Check the preview on livecenter shows your stream.
7. Tell Capri: **"go live on tiktok as @yourname"**. The overlay switches to LIVE and starts reading chat.
8. Say **"beat the game for me"** (or let chat vote with !diamonds, !build, !food, !explore, !beat).
9. To end: tell Capri **"stop stream mode"**, OBS > **Stop Streaming**, then end the LIVE on livecenter.

## Controls while live
- **F8** or say "stop" / "my turn": you take over Minecraft instantly. Votes resume on the next round.
- Viewers can only pick Minecraft tasks. Slurs and links are hidden from the overlay.
- Rehearse without going live: say "start stream mode", open `http://127.0.0.1:7777/stream.html?test=1` and type fake chat.

## Requirements (TikTok's rules)
LIVE with a stream key needs about 1,000 followers, age 18+ and an account in good standing. No key yet? Use **TikTok LIVE Studio**
(tiktok.com/studio/download): add a *Window Capture* of OBS's **Windowed Projector** (right-click OBS preview > Windowed Projector (Preview)).
