# Free daily Islamic-history reel -> your iPhone Photos

A stick-figure narrator tells a ~45-second Islamic history story with a
voiceover and word-by-word captions (1080x1920 vertical). GitHub builds it
every night for free; an iPhone Shortcut downloads it into Photos at 5:00 am.

Cost: $0. No API keys, no accounts besides GitHub.

## One-time setup (about 15 minutes, on a computer or the GitHub app)

1. Create a free GitHub account, then a **new PUBLIC repository**
   (public = unlimited free build minutes; the videos will be public, and
   nothing secret is stored anywhere).
2. Upload everything in this folder to it (including the hidden `.github` folder).
3. Repo -> **Settings -> Actions -> General -> Workflow permissions** ->
   choose **Read and write permissions** -> Save.
4. Open `.github/workflows/generate.yml` and change the `cron` line to your
   timezone (instructions are in the comments; it is UTC).
5. Repo -> **Actions** tab -> "Daily Islamic reel" -> **Run workflow**.
   After ~3-5 minutes, the repo's **Releases** page should show a "daily"
   release with `latest.mp4`. Download it and watch it.

## iPhone: save it to Photos every day at 5:00 am

Your video's URL is:
`https://github.com/YOUR_USERNAME/YOUR_REPO/releases/download/daily/latest.mp4`

1. **Shortcuts** app -> **Automation** tab -> **+** -> **Time of Day**.
2. Set **5:00 AM**, **Daily**, and choose **Run Immediately**.
3. Add action **Get Contents of URL** -> paste the URL above (method GET).
4. Add action **Save to Photo Album** (pick Recents or an album).
5. Tap **Done**. Test it first: open the automation, tap the play/run option
   (or build the same two actions as a normal shortcut and run it).

If "Save to Photo Album" complains about the file type, tell me the exact
error and I'll adjust the shortcut steps.

Your phone needs internet (Wi-Fi) at 5:00 am. If the nightly build ever
fails, the shortcut would just re-download the previous video.

## Changing things
- **Voice:** set `TTS_VOICE` (e.g. `en-GB-RyanNeural`, `en-US-AriaNeural`).
  Full list: run `edge-tts --list-voices`.
- **More topics:** add entries to `topics.json` (title, script of ~100-130
  words, and `settings` chosen from: desert, night, city, library, coast,
  mountains). Topics rotate daily; 12 topics = repeats every 12 days.
- **Test locally:** `pip install -r requirements.txt`, install ffmpeg, then
  `python generate_video.py` (add `--dry-run` to skip the voice).

## Honest caveats
- `edge-tts` is an unofficial free tool that uses Microsoft's Edge read-aloud
  voices. It has no guarantee: Microsoft could change or block it someday.
- The animation and video build were tested; the free-voice step and the
  GitHub/iPhone steps could not be tested in the environment this was made
  in, so expect to fix a small issue or two on the first runs.
- The stick figure is a generic narrator, on purpose. Don't label it as a
  Prophet or companion; keep stories about such figures narrated only.
- Verify the history in `topics.json` yourself before posting publicly.
