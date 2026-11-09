#!/usr/bin/env python3
"""Make ONE Reel per day (9:16 MP4) covering that day's 5 commands, with voice-over.

  python3 scripts/reel.py --voice 1          # day 1
  python3 scripts/reel.py --voice 1 2 3      # several days
  python3 scripts/reel.py --voice --all      # all 30 days
  python3 scripts/reel.py 1                  # no voice (quick preview, same pacing)

--voice uses the Mac's built-in `say` (voice + speed in config.json: "voice", "voice_rate").
Needs: pillow, numpy, ffmpeg.   Output: reels/dayXX-reel.mp4
"""
import glob
import json
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "config.json").read_text())
FONTS = ROOT / "fonts"
OUT = ROOT / "reels"
OUT.mkdir(exist_ok=True)
DAYS = [d for f in sorted(glob.glob(str(ROOT / "content" / "days_*.json")))
        for d in json.loads(Path(f).read_text())]

W, H, FPS, SR = 1080, 1920, 30, 48000
M = 84
TOP = 230                       # keep clear of Instagram's top UI
BOTTOM = 1500                   # keep clear of caption/buttons at the bottom
TYPE_SPEED = 0.085              # seconds per typed character (calm, readable)
WORDS_PER_SEC = 2.6             # used to estimate pacing when no voice

BG = (13, 17, 23)
CARD = (22, 27, 34)
BORDER = (48, 54, 61)
TEXT = (230, 237, 243)
MUTED = (139, 148, 158)
CODE = (173, 186, 199)
GREEN = (63, 185, 80)
BLUE = (88, 166, 255)
PURPLE = (188, 140, 255)
LEVELS = {"Beginner": (63, 185, 80), "Intermediate": (210, 153, 34),
          "Advanced": (248, 81, 73)}
SANS, SANS_B = "DejaVuSans.ttf", "DejaVuSans-Bold.ttf"
MONO, MONO_B = "DejaVuSansMono.ttf", "DejaVuSansMono-Bold.ttf"
NUM_WORDS = ["one", "two", "three", "four", "five"]
_fc = {}


def F(name, size):
    key = (name, int(size))
    if key not in _fc:
        _fc[key] = ImageFont.truetype(str(FONTS / name), int(size))
    return _fc[key]


def level(day):
    return "Beginner" if day <= 10 else "Intermediate" if day <= 20 else "Advanced"


def wrap(d, text, f, max_w):
    out, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= max_w:
            cur = t
        else:
            out.append(cur)
            cur = w
    return out + ([cur] if cur else [])


def ease(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def fit(d, name, text, max_w, start, minimum):
    s = start
    while s > minimum and d.textlength(text, font=F(name, s)) > max_w:
        s -= 4
    return F(name, s)


# ------------------------------------------------------------------ voice-over (macOS `say`)
import os, re, shutil, tempfile

SPEAK = {
 "pwd":"P W D","ls":"L S","cd":"C D","cp":"C P","mv":"M V","rm":"R M","wc":"W C",
 "whoami":"who am I","mkdir":"make dir","rmdir":"remove dir","nl":"N L","tr":"T R",
 "tac":"tack","rev":"rev","cmp":"compare","comm":"comm","gzip":"G zip","gunzip":"G unzip",
 "chmod":"C H mod","chown":"C H own","chgrp":"C H group","umask":"U mask","id":"I D",
 "sudo":"sue doo","su":"S U","ps":"P S","pkill":"P kill","pgrep":"P grep","bg":"B G",
 "fg":"F G","nohup":"no hup","df":"D F","du":"D U","lsblk":"L S block","env":"env",
 "ln":"L N","md5sum":"M D 5 sum","sha256sum":"shah 256 sum","base64":"base 64","od":"O D",
 "ip":"I P","ss":"S S","dig":"dig","curl":"curl","wget":"W get","ssh":"S S H","scp":"S C P",
 "rsync":"R sync","ssh-keygen":"S S H keygen","sed":"sed","awk":"awk","xargs":"X args",
 "printf":"print F","seq":"seek","renice":"re nice","uname":"U name","lscpu":"L S C P U",
 "dmesg":"D message","systemctl":"system control","journalctl":"journal control",
 "crontab":"cron tab","timedatectl":"time date control","hostnamectl":"hostname control",
 "useradd":"user add","usermod":"user mod","userdel":"user del","groupadd":"group add",
 "chage":"change age","lsof":"L S O F","strace":"S trace","ldd":"L D D","nc":"net cat",
 "dd":"D D","blkid":"block I D","fdisk":"F disk","mkfs":"make F S","umount":"U mount",
 "apt":"apt","dpkg":"D package","ufw":"U F W","w":"W","expr":"expression","shuf":"shuff",
 "cal":"cal",
}
SHORT_ONLY = {"w"}   # only spoken as the command name, never replaced inside sentences


def speak_cmd(cmd):
    return SPEAK.get(cmd, cmd)


OVERRIDES = {
 "cd": {"explain": "Pro tip. Dot dot goes one folder up, tilde goes home, and dash goes back to the previous folder."},
 "pgrep": {"explain": "Pro tip. dash L shows names too. P grep and P kill are a pair."},
 "uname": {"hook": "A tutorial says you need kernel 6 or newer. Which one do you have? Here's the fix."},
 "man": {"explain": "Pro tip. Inside man, press slash to search, and Q to quit."},
 "mv": {"hook": "Renaming final final v3 dot text, to something less embarrassing. Here's the fix."},
 "date": {"explain": "Pro tip. Plus percent F gives year, month, day. Perfect for file names."},
 "cal": {"explain": "Pro tip. cal dash 3 shows last month, this month and next month."},
 "history": {"explain": "Pro tip. Exclamation 502 re-runs command number 502. Control R searches your history."},
 "stat": {"explain": "Pro tip. stat dash C percent S prints just the size in bytes."},
 "find": {"explain": "Pro tip. dash m time minus 1 means modified in the last 24 hours."},
 "chmod": {"explain": "Pro tip. Read is 4, write is 2, execute is 1. So 7 means read, write and execute."},
 "umask": {"explain": "Pro tip. U mask 0 7 7 means only you can open new files."},
 "fg": {"explain": "Pro tip. Percent 1, percent 2, and so on, pick which job."},
 "alias": {"explain": "Pro tip. Put aliases in your bash R C file to keep them forever."},
 "source": {"hook": "You edited your bash R C file. Apply it without closing the terminal. Here's the fix.",
            "explain": "Pro tip. A single dot works too, instead of the word source."},
 "od": {"explain": "Pro tip. dash C shows characters. Backslash N is the newline."},
 "dig": {"explain": "Pro tip. Plus short gives just the answer."},
 "xargs": {"explain": "Pro tip. dash print zero, with dash zero, handles file names with spaces safely."},
 "printf": {"explain": "Pro tip. Unlike echo, print F doesn't add a new line. Add backslash N yourself."},
 "crontab": {"explain": "Pro tip. Star slash 10, then four more stars, means every 10 minutes."},
 "groupadd": {"explain": "Pro tip. Groups, plus C H group and C H mod, give you shared folders."},
 "chage": {"explain": "Pro tip. dash D zero forces a password change at the next login."},
 "strace": {"explain": "Pro tip. Look for E N O ENT errors. Those are files it couldn't find."},
 "read": {"hook": "Making your script interactive, like asking: enter your name. Here's the fix."},
 "test": {"explain": "Pro tip. Square brackets work the same as test. Spaces matter!"},
 "expr": {"explain": "Pro tip. In modern bash, double round brackets with a dollar sign are easier."},
 "bash": {"explain": "Pro tip. The hash bang line at the top tells Linux which program runs the file."},
 "exit": {"explain": "Pro tip. Dollar question mark holds the last exit code. Zero means success."},
}


def speakable(text):
    t = text
    t = t.replace("...", "").replace("(", ", ").replace(")", ", ").replace("~/", "")
    t = re.sub(r"(?<=\w)\.(?=[A-Za-z])", " dot ", t)
    t = re.sub(r"(?<=\s)\.(?=[A-Za-z])", "dot ", t)
    t = t.replace(" / ", " or ").replace("/", " or ")
    t = t.replace("->", " becomes ").replace("Ctrl + ", "Control ").replace("Ctrl+", "Control ")
    t = re.sub(r"(?<![\w-])--(\w[\w-]*)", lambda m: "dash dash " + m.group(1), t)
    t = re.sub(r"(?<![\w-])-(\d+)", lambda m: "minus " + m.group(1), t)
    t = re.sub(r"(?<![\w-])-([A-Za-z]{1,3})\b",
               lambda m: "dash " + " ".join(m.group(1).upper()), t)
    t = t.replace("~", " home ").replace("..", " dot dot ").replace("$", " dollar ")
    t = t.replace("&&", " and ").replace(" | ", " pipe ").replace("|", " pipe ")
    t = t.replace(">>", " append to ").replace("=", " is ").replace('"', "")
    t = re.sub(r"(?<!\w)'|'(?!\w)", "", t)          # drop quote marks, keep don't/you're
    for k, v in SPEAK.items():
        if k in SHORT_ONLY:
            continue
        t = re.sub(rf"(?<![\w-]){re.escape(k)}(?![\w-])", v, t)
    return re.sub(r"\s+", " ", t).strip()




def tts(text, path, sr=44100):
    """Synthesise text to a mono WAV with macOS `say`. Returns seconds, or None."""
    if not shutil.which("say"):
        return None
    voice = CFG.get("voice", "Rishi")
    rate = str(CFG.get("voice_rate", 185))
    with tempfile.TemporaryDirectory() as td:
        aiff = os.path.join(td, "v.aiff")
        r = subprocess.run(["say", "-v", voice, "-r", rate, "-o", aiff, text])
        if r.returncode != 0:          # voice not installed -> system default
            subprocess.run(["say", "-r", rate, "-o", aiff, text], check=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", aiff, "-ac", "1",
                        "-ar", str(sr), str(path)], check=True)
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()



# ------------------------------------------------------------------ script (what the voice says)
def day_script(D):
    day, Ls = D["day"], D["lessons"]
    spoken_handle = CFG.get("handle_spoken", CFG["handle"])
    scenes = [("intro", None, f"Day {day}. {speakable(D['theme'])}. 5 commands you should know.")]
    for k, L in enumerate(Ls):
        o = OVERRIDES.get(L["cmd"], {})
        scenes.append(("card", k, f"Number {NUM_WORDS[k]}. {speak_cmd(L['cmd'])}. "
                       + speakable(L["what"])))
        when = o.get("hook", speakable(L["when"])).replace(" Here's the fix.", "")
        tip = o.get("explain", "Pro tip. " + speakable(L["tip"]))
        scenes.append(("term", k, "Use it when: " + when + " " + tip))
    scenes.append(("outro", None, f"That's day {day}. Quiz tonight at 8. "
                   f"Follow {spoken_handle} for more."))
    return [(a, b, tidy(c)) for a, b, c in scenes]


def tidy(t):
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    t = re.sub(r",\s*([.,])", r"\1", t)
    t = re.sub(r"\.\s*\.", ".", t)
    return re.sub(r"\s+", " ", t).strip()


def typing_time(L):
    t = 0.6
    for line in L["example"]:
        t += (0.3 + len(line) * TYPE_SPEED + 0.5) if line.startswith("$ ") else 0.35
    return t + 0.8


def plan(D, voice):
    """Return scenes as dicts with start/duration (seconds) and their voice file."""
    out, t = [], 0.0
    for i, (kind, k, text) in enumerate(day_script(D)):
        vpath, vdur = None, None
        if voice:
            vpath = OUT / f"_v{D['day']:02d}_{i:02d}.wav"
            vdur = tts(text, vpath, SR)
            if vdur is None:
                print("  `say` not found: making the Reel WITHOUT voice")
                voice, vpath = False, None
        est = vdur if vdur else len(text.split()) / WORDS_PER_SEC
        dur = est + 0.7
        if kind == "term":
            dur = max(dur, typing_time(D["lessons"][k]))
        if kind == "intro":
            dur = max(dur, 5.0)
        if kind == "outro":
            dur = max(dur + 1.2, 5.5)
        out.append({"kind": kind, "k": k, "start": t, "dur": dur, "voice": vpath, "text": text})
        t += dur
    return out, t


# ------------------------------------------------------------------ drawing
def chrome(d, D, t, total, kind, k):
    day = D["day"]
    col = LEVELS[level(day)]
    off = int((t * 18) % 60)                       # slow drifting dot grid
    for y in range(-60 + off, H, 60):
        for x in range(30, W, 60):
            d.point((x, y), fill=(28, 34, 44))
    y = TOP - 110
    d.text((M, y), f"DAY {day:02d}", font=F(MONO_B, 46), fill=TEXT)
    w = d.textlength(f"DAY {day:02d}", font=F(MONO_B, 46))
    d.text((M + w + 18, y + 8), CFG.get("series", ""), font=F(SANS_B, 28), fill=MUTED)
    lv = level(day).upper()
    pf = F(SANS_B, 26)
    pw = d.textlength(lv, font=pf) + 44
    d.rounded_rectangle((W - M - pw, y + 2, W - M, y + 52), radius=25, outline=col, width=3)
    d.text((W - M - pw + 22, y + 12), lv, font=pf, fill=col)
    # 5 progress pills = the 5 commands
    gap, pw2 = 14, (W - 2 * M - 4 * 14) / 5
    for i in range(5):
        x0 = M + i * (pw2 + gap)
        done = kind == "outro" or (k is not None and i < k)
        cur = k == i and kind != "outro"
        fill = col if done else (mix(BORDER, col, 0.55) if cur else BORDER)
        d.rounded_rectangle((x0, y + 76, x0 + pw2, y + 86), radius=5, fill=fill)
    d.text((M, BOTTOM), CFG["handle"], font=F(SANS_B, 36), fill=TEXT)
    d.text((M, BOTTOM + 52), CFG["tagline"], font=F(SANS_B, 30), fill=GREEN)


def text_block(d, x, y, text, f, col, a, lh=1.35, max_w=W - 2 * M):
    for ln in wrap(d, text, f, max_w):
        d.text((x, y), ln, font=f, fill=mix(BG, col, a))
        y += f.size * lh
    return y


def terminal(d, L, lt, top):
    lines = L["example"]
    pad = 40
    longest = max(len(x) for x in lines)
    size = 40
    while size > 22 and d.textlength("M" * longest, font=F(MONO, size)) > W - 2 * M - 2 * pad:
        size -= 2
    cf = F(MONO, size)
    lh = int(size * 1.55)
    h = 84 + pad + lh * len(lines) + pad - 10
    d.rounded_rectangle((M, top, W - M, top + h), radius=26, fill=CARD, outline=BORDER, width=3)
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        cx = M + 44 + i * 38
        d.ellipse((cx - 12, top + 30, cx + 12, top + 54), fill=c)
    d.text((W // 2, top + 42), "bash", font=F(MONO, 28), fill=MUTED, anchor="mm")
    ty, t, blink = top + 84 + pad - 10, 0.6, int(lt * 2.2) % 2 == 0
    for line in lines:
        x = M + pad
        if line.startswith("$ "):
            typed = line[2:]
            start = t + 0.3
            n = int((lt - start) / TYPE_SPEED)
            if lt < t:
                break
            d.text((x, ty), "$", font=cf, fill=GREEN)
            x2 = x + d.textlength("$ ", font=cf)
            n = max(0, min(len(typed), n))
            d.text((x2, ty), typed[:n], font=cf, fill=TEXT)
            end = start + len(typed) * TYPE_SPEED
            if lt < end + 0.5 and blink:
                cx = x2 + d.textlength(typed[:n], font=cf)
                d.rectangle((cx, ty + 4, cx + size * 0.55, ty + size + 4), fill=TEXT)
            t = end + 0.5
            if lt < t:
                break
        else:
            if lt < t:
                break
            col = MUTED if line.lstrip().startswith("#") else CODE
            d.text((x, ty), line, font=cf, fill=col)
            t += 0.35
        ty += lh
    return top + h


def frame(D, sc, t, total):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    kind, k = sc["kind"], sc["k"]
    lt = t - sc["start"]
    chrome(d, D, t, total, kind, k)
    a = ease(lt / 0.6)
    col = LEVELS[level(D["day"])]
    y0 = TOP + 60
    if kind == "intro":
        f = F(SANS_B, 84)
        y = text_block(d, M, y0 + 40, D["theme"], f, TEXT, a, lh=1.2)
        y = text_block(d, M, y + 30, "5 commands you should know:", F(SANS, 44), MUTED,
                       ease((lt - 0.6) / 0.6))
        y += 40
        for i, L in enumerate(D["lessons"]):
            ai = ease((lt - 1.2 - i * 0.45) / 0.5)
            if ai <= 0:
                continue
            d.rounded_rectangle((M, y, W - M, y + 96), radius=18, fill=mix(BG, CARD, ai),
                                outline=mix(BG, BORDER, ai), width=2)
            d.text((M + 30, y + 48), f"{i + 1}", font=F(MONO_B, 44), fill=mix(BG, col, ai), anchor="lm")
            d.text((M + 100, y + 48), L["cmd"], font=F(MONO_B, 48), fill=mix(BG, GREEN, ai), anchor="lm")
            y += 116
    elif kind == "card":
        L = D["lessons"][k]
        d.text((M, y0 + 20), f"{k + 1} / 5", font=F(MONO_B, 48), fill=mix(BG, MUTED, a))
        cf = fit(d, MONO_B, L["cmd"], W - 2 * M, 200, 90)
        d.text((M, y0 + 90), L["cmd"], font=cf, fill=mix(BG, GREEN, a))
        y = y0 + 90 + cf.size * 1.15
        y = text_block(d, M, y, f"man {L['cmd']}: {L['man']}", F(MONO, 32), PURPLE, a, lh=1.4)
        y += 60
        a2 = ease((lt - 0.8) / 0.6)
        d.text((M, y), "WHAT IT DOES", font=F(SANS_B, 34), fill=mix(BG, BLUE, a2))
        text_block(d, M, y + 60, L["what"], F(SANS_B, 58), TEXT, a2, lh=1.3)
    elif kind == "term":
        L = D["lessons"][k]
        d.text((M, y0), L["cmd"], font=F(MONO_B, 72), fill=GREEN)
        d.text((M, y0 + 100), "WHEN YOU'D USE IT", font=F(SANS_B, 32), fill=mix(BG, BLUE, a))
        y = text_block(d, M, y0 + 150, L["when"], F(SANS, 46), TEXT, a, lh=1.3)
        yb = terminal(d, L, lt, int(y + 50))
        at = ease((lt - sc["dur"] * 0.55) / 0.6)
        if at > 0:
            d.text((M, yb + 50), "PRO TIP", font=F(SANS_B, 32), fill=mix(BG, col, at))
            text_block(d, M, yb + 100, L["tip"], F(SANS_B, 46), TEXT, at, lh=1.3)
    elif kind == "tip":
        L = D["lessons"][k]
        d.text((M, y0), L["cmd"], font=F(MONO_B, 72), fill=GREEN)
        d.rounded_rectangle((M, y0 + 160, W - M, y0 + 760), radius=30, fill=CARD,
                            outline=mix(BG, col, a), width=4)
        d.text((M + 50, y0 + 220), "PRO TIP", font=F(SANS_B, 40), fill=mix(BG, col, a))
        text_block(d, M + 50, y0 + 300, L["tip"], F(SANS_B, 62), TEXT, ease((lt - 0.3) / 0.6),
                   lh=1.3, max_w=W - 2 * M - 100)
    elif kind == "outro":
        d.text((M, y0 + 20), f"Day {D['day']} done", font=F(SANS_B, 90), fill=mix(BG, TEXT, a))
        y = y0 + 160
        for i, L in enumerate(D["lessons"]):
            ai = ease((lt - 0.3 - i * 0.25) / 0.4)
            d.text((M, y), "✓", font=F(SANS_B, 52), fill=mix(BG, GREEN, ai))
            d.text((M + 80, y + 4), L["cmd"], font=F(MONO_B, 50), fill=mix(BG, TEXT, ai))
            y += 82
        a2 = ease((lt - 1.8) / 0.6)
        y += 40
        d.text((M, y), "Quiz on all 5 tonight at 8 PM", font=F(SANS_B, 46), fill=mix(BG, BLUE, a2))
        d.text((M, y + 80), f"Follow {CFG['handle']}", font=F(SANS_B, 54), fill=mix(BG, GREEN, a2))
        d.text((M, y + 150), "Save this for later", font=F(SANS, 42), fill=mix(BG, MUTED, a2))
    return img


# ------------------------------------------------------------------ sound (synthesised: no copyright)
def soundtrack(D, scenes, total, path):
    n = int(total * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    prog = [(220.0, 261.63, 329.63), (174.61, 220.0, 261.63), (196.0, 246.94, 293.66),
            (164.81, 207.65, 246.94)]
    bar = 4.0
    for i in range(int(total / bar) + 1):
        a, b = int(i * bar * SR), min(n, int((i + 1) * bar * SR))
        if a >= n:
            break
        tt = t[a:b] - i * bar
        env = np.minimum(1, tt / 0.8) * np.minimum(1, (bar - tt) / 0.8)
        for fr in prog[i % 4]:
            out[a:b] += env * (np.sin(2 * np.pi * fr * t[a:b]) + 0.4 * np.sin(2 * np.pi * fr * 2.002 * t[a:b]))
    out *= 0.022 * np.minimum(1, t / 2) * np.minimum(1, (total - t) / 2)
    rng = np.random.default_rng(D["day"])

    def click(at, vol):
        i, ln = int(at * SR), int(0.016 * SR)
        if 0 <= i and i + ln < n:
            out[i:i + ln] += vol * np.convolve(rng.normal(0, 1, ln) * np.exp(-np.linspace(0, 9, ln)),
                                               np.ones(5) / 5, mode="same")

    def ding(at, fr, vol):
        i, ln = int(at * SR), int(0.25 * SR)
        if 0 <= i and i + ln < n:
            tt = np.arange(ln) / SR
            out[i:i + ln] += vol * np.sin(2 * np.pi * fr * tt) * np.exp(-tt * 14)

    for sc in scenes:
        if sc["kind"] == "card":
            ding(sc["start"] + 0.05, 880, 0.10)
        if sc["kind"] == "term":
            L, tt = D["lessons"][sc["k"]], 0.6
            for line in L["example"]:
                if line.startswith("$ "):
                    s0 = sc["start"] + tt + 0.3
                    for j in range(len(line) - 2):
                        click(s0 + j * TYPE_SPEED + rng.uniform(0, 0.015), rng.uniform(0.10, 0.18))
                    tt += 0.3 + (len(line) - 2) * TYPE_SPEED + 0.5
                else:
                    tt += 0.35
    for sc in scenes:
        if sc["voice"]:
            with wave.open(str(sc["voice"])) as w:
                v = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16) / 32768.0
            i = int((sc["start"] + 0.25) * SR)
            j = min(n, i + len(v))
            out[i:j] = out[i:j] * 0.5 + 0.95 * v[: j - i]
    peak = np.max(np.abs(out)) or 1
    out = out / max(1.0, peak / 0.95)
    data = (out * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())


# ------------------------------------------------------------------ render
def render(day, voice):
    D = next(x for x in DAYS if x["day"] == day)
    scenes, total = plan(D, voice)
    wav = OUT / f"_a{day:02d}.wav"
    soundtrack(D, scenes, total, wav)
    mp4 = OUT / f"day{day:02d}-reel.mp4"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", str(wav),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "128k", "-ar", str(SR), "-ac", "2",
           "-shortest", "-movflags", "+faststart", str(mp4)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    si = 0
    for f in range(int(total * FPS)):
        t = f / FPS
        while si + 1 < len(scenes) and t >= scenes[si + 1]["start"]:
            si += 1
        p.stdin.write(frame(D, scenes[si], t, total).tobytes())
    p.stdin.close()
    p.wait()
    wav.unlink()
    for sc in scenes:
        if sc["voice"] and Path(sc["voice"]).exists():
            Path(sc["voice"]).unlink()
    print(f"{mp4.name}: {total:.0f}s{' with voice' if any(s['voice'] for s in scenes) else ''}")


if __name__ == "__main__":
    args = sys.argv[1:]
    voice = "--voice" in args
    args = [a for a in args if a != "--voice"]
    days = [D["day"] for D in DAYS] if "--all" in args else [int(a) for a in args]
    if not days:
        sys.exit(__doc__)
    for dday in days:
        render(dday, voice)
