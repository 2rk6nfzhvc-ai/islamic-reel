
#!/usr/bin/env python3
"""
Free Islamic-history reel generator (no API keys, no paid services).

  topics.json  ->  script text
  edge-tts     ->  free neural voiceover + word timings (for synced captions)
  Pillow       ->  draws a stick-figure narrator, backgrounds and captions
  ffmpeg       ->  encodes a 1080x1920 vertical mp4 with the voiceover

Usage:
  python generate_video.py                # today's topic, real voice
  python generate_video.py --topic 3      # pick a specific topic (0-based)
  python generate_video.py --dry-run      # no internet needed: silent audio, estimated timing

Output: output/latest.mp4  (+ output/title.txt)
"""

import argparse
import asyncio
import datetime
import json
import math
import os
import random
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent
TOPICS_PATH = ROOT / "topics.json"
WORK = ROOT / "work"
OUT = ROOT / "output"

W, H, FPS = 1080, 1920, 24
LEAD, TAIL = 0.7, 1.2            # seconds of silence before / after the voice
VOICE = os.environ.get("TTS_VOICE", "en-US-GuyNeural")
RATE = os.environ.get("TTS_RATE", "-8%")
YELLOW, WHITE, BLACK = (255, 214, 10), (255, 255, 255), (0, 0, 0)


# ------------------------------------------------------------------ voice ---

async def _tts(text, out_path):
    """Free Microsoft Edge neural TTS. Returns [(word, start_s, end_s), ...]."""
    import edge_tts
    try:
        comm = edge_tts.Communicate(text, VOICE, rate=RATE, boundary="WordBoundary")
    except TypeError:                      # older edge-tts versions
        comm = edge_tts.Communicate(text, VOICE, rate=RATE)
    words = []
    with open(out_path, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                s = chunk["offset"] / 1e7
                words.append((chunk["text"], s, s + chunk["duration"] / 1e7))
    return words


def audio_duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def silent_audio(path, seconds):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "anullsrc=r=24000:cl=mono", "-t", f"{seconds:.2f}", "-q:a", "9", str(path)],
                   check=True)


# --------------------------------------------------------------- timeline ---

def build_timeline(script, tts_words, dur):
    """Per-token (start, end) in video time. Uses real word timings when
    available, otherwise estimates by character count."""
    tokens = script.split()
    n, m = len(tokens), len(tts_words)
    times = []
    if m:
        for i in range(n):
            j = i if m == n else round(i * (m - 1) / max(n - 1, 1))
            _, s, e = tts_words[j]
            times.append((s + LEAD, e + LEAD))
    else:
        total = sum(len(t) + 1 for t in tokens)
        acc = 0
        for t in tokens:
            s = acc / total * dur
            acc += len(t) + 1
            times.append((s + LEAD, acc / total * dur + LEAD))
    return tokens, times


def sentence_ids(script):
    ids = []
    for k, sent in enumerate(re.split(r"(?<=[.!?])\s+", script.strip())):
        ids += [k] * len(sent.split())
    return ids


def caption_groups(tokens, times, max_words=4):
    groups, cur = [], []
    for i, tok in enumerate(tokens):
        cur.append(i)
        if len(cur) >= max_words or tok[-1] in ".!?" or (tok[-1] == "," and len(cur) >= 2):
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return [{"idx": g, "start": times[g[0]][0], "end": times[g[-1]][1]} for g in groups]


# ------------------------------------------------------------ backgrounds ---

def font(size):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def mix(c0, c1, f):
    return tuple(int(c0[i] + (c1[i] - c0[i]) * f) for i in range(3))


def vgrad(d, y0, y1, c0, c1):
    for y in range(y0, y1):
        d.line([(0, y), (W, y)], fill=mix(c0, c1, (y - y0) / max(1, y1 - y0 - 1)))


def dunes(d, base, amp, freq, phase, color):
    pts = [(0, H)] + [(x, base + amp * math.sin(x * freq + phase)) for x in range(0, W + 1, 15)] + [(W, H)]
    d.polygon(pts, fill=color)


def dome(d, x0, x1, top, base, color):
    d.rectangle([x0, base, x1, base + 10], fill=color)
    d.pieslice([x0, top, x1, top + (x1 - x0)], 180, 360, fill=color)
    cx = (x0 + x1) // 2
    d.line([(cx, top), (cx, top - 40)], fill=color, width=6)
    d.ellipse([cx - 9, top - 56, cx + 9, top - 38], fill=color)


def minaret(d, x, top, ground, color):
    d.rectangle([x - 20, top, x + 20, ground], fill=color)
    d.rectangle([x - 30, top + 90, x + 30, top + 106], fill=color)
    d.polygon([(x - 26, top), (x + 26, top), (x, top - 90)], fill=color)


def bg_desert():
    im = Image.new("RGB", (W, H)); d = ImageDraw.Draw(im)
    vgrad(d, 0, 1160, (252, 190, 115), (255, 238, 195))
    d.ellipse([700, 310, 940, 550], fill=(255, 245, 218))
    dunes(d, 1060, 45, 1 / 170, 0.5, (226, 172, 104))
    dunes(d, 1150, 30, 1 / 120, 2.0, (214, 160, 92))
    d.rectangle([0, 1180, W, H], fill=(205, 150, 84))
    return im, (60, 35, 20)


def bg_night():
    im = Image.new("RGB", (W, H)); d = ImageDraw.Draw(im)
    c0, c1 = (8, 14, 40), (34, 44, 96)
    vgrad(d, 0, H, c0, c1)
    rnd = random.Random(7)
    for _ in range(150):
        x, y, r = rnd.randint(0, W), rnd.randint(0, 1000), rnd.choice((1, 2, 2, 3))
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 230))
    d.ellipse([720, 280, 920, 480], fill=(250, 244, 210))
    d.ellipse([765, 255, 945, 435], fill=mix(c0, c1, 345 / H))   # carves the crescent
    dunes(d, 1120, 35, 1 / 160, 1.0, (22, 28, 66))
    d.rectangle([0, 1190, W, H], fill=(16, 22, 54))
    return im, (245, 245, 235)


def bg_city():
    im = Image.new("RGB", (W, H)); d = ImageDraw.Draw(im)
    vgrad(d, 0, 1160, (125, 188, 236), (226, 241, 250))
    for cx, cy in ((220, 330), (760, 520), (480, 220)):
        for dx, dy, r in ((0, 0, 60), (60, 15, 50), (-60, 20, 45)):
            d.ellipse([cx + dx - r, cy + dy - r // 2, cx + dx + r, cy + dy + r // 2], fill=(250, 252, 255))
    s, win = (196, 164, 118), (170, 138, 96)
    d.rectangle([120, 880, 520, 1160], fill=s); dome(d, 220, 420, 780, 880, s)
    minaret(d, 150, 660, 1160, s); minaret(d, 490, 700, 1160, s)
    d.rectangle([590, 990, 760, 1160], fill=s); d.rectangle([780, 950, 970, 1160], fill=s)
    dome(d, 830, 920, 880, 950, s)
    for x in range(200, 440, 60):
        d.rectangle([x, 940, x + 24, 1010], fill=win)
    d.rectangle([0, 1160, W, H], fill=(186, 156, 114))
    return im, (25, 30, 55)


def bg_library():
    im = Image.new("RGB", (W, H)); d = ImageDraw.Draw(im)
    vgrad(d, 0, H, (62, 40, 28), (92, 62, 42))
    rnd = random.Random(11)
    palette = [(150, 60, 50), (60, 90, 120), (70, 110, 80), (190, 150, 70), (110, 70, 120), (130, 90, 60)]
    for board in (380, 600, 820, 1040):
        x = 20
        while x < W - 20:
            w, h = rnd.randint(24, 50), rnd.randint(110, 195)
            c = mix(rnd.choice(palette), (40, 28, 20), 0.35)
            d.rectangle([x, board - h, x + w, board], fill=c)
            x += w + rnd.randint(1, 4)
        d.rectangle([0, board, W, board + 18], fill=(34, 22, 14))
    d.rectangle([0, 1160, W, H], fill=(44, 30, 22))
    return im, (250, 240, 215)


def bg_coast():
    im = Image.new("RGB", (W, H)); d = ImageDraw.Draw(im)
    vgrad(d, 0, 880, (120, 186, 236), (218, 236, 246))
    d.ellipse([140, 330, 320, 510], fill=(255, 248, 222))
    vgrad(d, 880, 1110, (62, 134, 192), (30, 92, 152))
    rnd = random.Random(5)
    for _ in range(40):
        x, y = rnd.randint(0, W - 80), rnd.randint(900, 1100)
        d.arc([x, y, x + 70, y + 24], 200, 340, fill=(160, 205, 232), width=4)
    d.polygon([(640, 880), (760, 880), (735, 918), (665, 918)], fill=(110, 70, 40))
    d.line([(700, 880), (700, 740)], fill=(80, 55, 35), width=6)
    d.polygon([(708, 748), (708, 872), (790, 872)], fill=(250, 250, 245))
    vgrad(d, 1110, H, (236, 214, 160), (214, 188, 130))
    return im, (30, 45, 70)


def bg_mountains():
    im = Image.new("RGB", (W, H)); d = ImageDraw.Draw(im)
    vgrad(d, 0, 1160, (190, 215, 240), (240, 246, 250))
    d.polygon([(0, 1160), (0, 880), (180, 700), (330, 860), (520, 640), (720, 840), (900, 720), (W, 860), (W, 1160)],
              fill=(150, 172, 198))
    d.polygon([(0, 1160), (0, 980), (240, 820), (430, 960), (650, 800), (860, 950), (W, 880), (W, 1160)],
              fill=(112, 138, 154))
    vgrad(d, 1160, H, (98, 132, 86), (70, 100, 64))
    return im, (22, 34, 28)


BACKGROUNDS = {"desert": bg_desert, "night": bg_night, "city": bg_city,
               "library": bg_library, "coast": bg_coast, "mountains": bg_mountains}


def outlined(d, xy, text, fnt, fill, stroke=7):
    d.text(xy, text, font=fnt, fill=fill, stroke_width=stroke, stroke_fill=BLACK)


def wrap(d, words, fnt, maxw):
    lines, cur = [], []
    for w in words:
        if cur and d.textlength(" ".join(cur + [w]), font=fnt) > maxw:
            lines.append(cur); cur = []
        cur.append(w)
    return lines + [cur]


def make_scene_base(kind, title):
    im, ink = BACKGROUNDS[kind]()
    d = ImageDraw.Draw(im)
    k = font(40)
    kicker = "ISLAMIC HISTORY"
    outlined(d, ((W - d.textlength(kicker, font=k)) / 2, 120), kicker, k, YELLOW, 5)
    tf = font(66)
    y = 190
    for line in wrap(d, title.split(), tf, W - 160):
        txt = " ".join(line)
        outlined(d, ((W - d.textlength(txt, font=tf)) / 2, y), txt, tf, WHITE, 7)
        y += 84
    return im, ink


# ----------------------------------------------------------- stick figure ---

RX, RY, RW, RH, SS = 140, 480, 800, 780, 2     # figure region + supersampling


def draw_figure(frame, t, ink, energy, amp):
    layer = Image.new("RGBA", (RW * SS, RH * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    P = lambda x, y: ((x - RX) * SS, (y - RY) * SS)
    lw = 15 * SS
    col = ink + (255,)

    def line(a, b):
        (x0, y0), (x1, y1) = P(*a), P(*b)
        d.line([x0, y0, x1, y1], fill=col, width=lw)
        for x, y in ((x0, y0), (x1, y1)):
            d.ellipse([x - lw / 2, y - lw / 2, x + lw / 2, y + lw / 2], fill=col)

    cx, ground = 540, 1160
    bob = 6 * math.sin(t * 2.2)
    hy = 690 + bob
    neck, sh, hip = (cx, hy + 95), (cx, hy + 145), (cx, 1010)

    sx0, sy0 = P(cx - 210, ground - 8); sx1, sy1 = P(cx + 210, ground + 22)
    d.ellipse([sx0, sy0, sx1, sy1], fill=(0, 0, 0, 45))                    # ground shadow

    line(neck, hip)                                                        # torso
    for side in (-1, 1):                                                   # legs + feet
        foot = (cx + side * 85, ground)
        line(hip, foot)
        line(foot, (cx + side * 135, ground))

    w = 3.0
    arms = (
        (1, 25 + energy * (10 + 14 * math.sin(w * t)), 30 + energy * (65 + 35 * math.sin(w * t + 1.0))),
        (-1, 25 + energy * (8 + 10 * math.sin(0.9 * w * t + 2.0)), 30 + energy * (35 + 25 * math.sin(0.9 * w * t + 3.0))),
    )
    for side, up, fo in arms:                                              # arms
        ex = sh[0] + side * 130 * math.sin(math.radians(up))
        ey = sh[1] + 130 * math.cos(math.radians(up))
        hx = ex + side * 120 * math.sin(math.radians(fo))
        hy2 = ey + 120 * math.cos(math.radians(fo))
        line(sh, (ex, ey)); line((ex, ey), (hx, hy2))

    x0, y0 = P(cx - 95, hy - 95); x1, y1 = P(cx + 95, hy + 95)             # head
    d.ellipse([x0, y0, x1, y1], outline=col, width=lw)

    blink = (t % 3.4) < 0.12
    for ex in (cx - 34, cx + 34):                                          # eyes
        ex_, ey_ = P(ex, hy - 14)
        if blink:
            d.line([ex_ - 9 * SS, ey_, ex_ + 9 * SS, ey_], fill=col, width=5 * SS)
        else:
            d.ellipse([ex_ - 9 * SS, ey_ - 9 * SS, ex_ + 9 * SS, ey_ + 9 * SS], fill=col)

    mx, my = P(cx, hy + 42)                                                # mouth
    if amp > 0:
        mh = (5 + 26 * amp) * SS
        d.ellipse([mx - 22 * SS, my - mh / 2, mx + 22 * SS, my + mh / 2], fill=col)
    else:
        d.arc([mx - 28 * SS, my - 22 * SS, mx + 28 * SS, my + 14 * SS], 20, 160, fill=col, width=5 * SS)

    layer = layer.resize((RW, RH), Image.Resampling.LANCZOS)
    frame.paste(layer, (RX, RY), layer)


# ---------------------------------------------------------------- render ---

def render(topic, tts_words, audio_path, dur, out_path, max_seconds=None):
    script = topic["script"]
    tokens, times = build_timeline(script, tts_words, dur)
    sids = sentence_ids(script)
    groups = caption_groups(tokens, times)
    settings = topic["settings"]
    total = dur + LEAD + TAIL
    if max_seconds:
        total = min(total, max_seconds)
    speech_end = times[-1][1]

    bases = {k: make_scene_base(k, topic["title"]) for k in set(settings)}
    cap_font = font(76)
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    layouts = {}
    for gi, g in enumerate(groups):                       # caption layout, computed once per group
        lines = wrap(probe, [tokens[i] for i in g["idx"]], cap_font, W - 140)
        pos, k = [], 0
        y = 1290
        for ln in lines:
            widths = [probe.textlength(w + " ", font=cap_font) for w in ln]
            x = (W - sum(widths)) / 2
            for w, wd in zip(ln, widths):
                pos.append((g["idx"][k], w, x, y)); x += wd; k += 1
            y += 100
        layouts[gi] = pos

    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", str(audio_path),
           "-af", f"adelay={int(LEAD * 1000)}:all=1,apad", "-t", f"{total:.3f}",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out_path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    ci = gi = 0
    for f in range(int(total * FPS)):
        t = f / FPS
        while ci + 1 < len(tokens) and t >= times[ci + 1][0]:
            ci += 1
        while gi + 1 < len(groups) and t >= groups[gi + 1]["start"]:
            gi += 1

        kind = settings[sids[ci] % len(settings)]
        base, ink = bases[kind]
        frame = base.copy()

        speaking = times[ci][0] - 0.03 <= t <= times[ci][1] + 0.05
        amp = 0.35 + 0.65 * abs(math.sin(t * 38)) if speaking else 0
        energy = 1.0 if LEAD - 0.2 <= t <= speech_end + 0.3 else 0.15
        draw_figure(frame, t, ink, energy, amp)

        g = groups[gi]
        if g["start"] - 0.1 <= t <= g["end"] + 0.7:
            d = ImageDraw.Draw(frame)
            for i, word, x, y in layouts[gi]:
                outlined(d, (x, y), word, cap_font, YELLOW if t >= times[i][0] else WHITE, 8)

        proc.stdin.write(frame.tobytes())

    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg failed")


# ------------------------------------------------------------------ main ---

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", type=int, help="0-based topic index (default: rotates daily)")
    ap.add_argument("--dry-run", action="store_true", help="skip TTS (no internet): silent audio, estimated timing")
    ap.add_argument("--max-seconds", type=float, help="cap video length (testing)")
    a = ap.parse_args()

    topics = json.loads(TOPICS_PATH.read_text(encoding="utf-8"))
    idx = a.topic if a.topic is not None else datetime.date.today().toordinal() % len(topics)
    topic = topics[idx]
    print(f"Topic {idx}: {topic['title']}")

    WORK.mkdir(exist_ok=True); OUT.mkdir(exist_ok=True)
    audio = WORK / "voice.mp3"
    if a.dry_run:
        dur = len(topic["script"].split()) / 2.4
        silent_audio(audio, dur)
        words = []
    else:
        words = asyncio.run(_tts(topic["script"], audio))
        dur = audio_duration(audio)
    print(f"Voice length {dur:.1f}s, {len(words)} word timings")

    out = OUT / "latest.mp4"
    render(topic, words, audio, dur, out, a.max_seconds)
    (OUT / "title.txt").write_text(topic["title"], encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    sys.exit(main())
