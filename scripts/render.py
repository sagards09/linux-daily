#!/usr/bin/env python3
"""Build every image + caption + the posting schedule.

Reads:   content/days_*.json, config.json
Writes:  posts/*.jpg, content/captions.json, content/schedule.json

Usage:   pip install pillow && python3 scripts/render.py
"""
import glob
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "config.json").read_text())
DAYS = [d for f in sorted(glob.glob(str(ROOT / "content" / "days_*.json")))
        for d in json.loads(Path(f).read_text())]
OUT = ROOT / "posts"
OUT.mkdir(exist_ok=True)
FONTS = ROOT / "fonts"

W, H = 1080, 1350
M = 70
INNER = W - 2 * M

# ---------- template colours: change these to restyle everything ----------
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
_fc = {}


def F(name, size):
    size = int(size)
    if (name, size) not in _fc:
        _fc[(name, size)] = ImageFont.truetype(str(FONTS / name), size)
    return _fc[(name, size)]


def level(day):
    return "Beginner" if day <= 10 else "Intermediate" if day <= 20 else "Advanced"


def tw(d, s, f):
    return d.textlength(s, font=f)


def wrap(d, text, f, max_w):
    out, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if tw(d, t, f) <= max_w:
            cur = t
        else:
            out.append(cur)
            cur = w
    return out + ([cur] if cur else [])


def fit(d, name, text, max_w, start, minimum):
    s = start
    while s > minimum and tw(d, text, F(name, s)) > max_w:
        s -= 2
    return F(name, s)


# ---------------------------------------------------------------- shared parts
def header(d, day, right_label, colour):
    y = M
    d.text((M, y), f"DAY {day:02d}", font=F(MONO_B, 40), fill=TEXT)
    x = M + tw(d, f"DAY {day:02d}", F(MONO_B, 40)) + 14
    d.text((x, y + 5), right_label, font=F(MONO, 32), fill=MUTED)
    lv = level(day).upper()
    pf = F(SANS_B, 24)
    pw = tw(d, lv, pf) + 40
    d.rounded_rectangle((W - M - pw, y - 2, W - M, y + 44), radius=22,
                        outline=colour, width=3)
    d.text((W - M - pw + 20, y + 7), lv, font=pf, fill=colour)


def footer(d, day, colour):
    total = CFG["series_length"]
    fy = H - M - 62
    gap = 6
    sw = (INNER - gap * (total - 1)) / total
    for i in range(total):
        x0 = M + i * (sw + gap)
        d.rounded_rectangle((x0, fy, x0 + sw, fy + 9), radius=4,
                            fill=colour if i < day else BORDER)
    d.text((M, fy + 30), CFG["handle"], font=F(SANS_B, 28), fill=TEXT)
    d.text((W - M, fy + 30), CFG["tagline"], font=F(SANS_B, 28),
           fill=GREEN, anchor="ra")
    return fy


def label(d, y, text, colour, s):
    d.text((M, y), text, font=F(SANS_B, 24 * s), fill=colour)
    return y + 38 * s


def para(d, y, text, f, colour, max_w=INNER, x=M, lh=1.38):
    for line in wrap(d, text, f, max_w):
        d.text((x, y), line, font=f, fill=colour)
        y += f.size * lh
    return y


def terminal(d, y, lines, s, draw=True):
    pad = 32
    longest = max(lines, key=len) if lines else ""
    cf = fit(d, MONO, longest, INNER - 2 * pad, 29 * s, 18)
    lh = int(cf.size * 1.5)
    h = 62 + 14 + lh * len(lines) + pad - 6
    if draw:
        d.rounded_rectangle((M, y, W - M, y + h), radius=20, fill=CARD,
                            outline=BORDER, width=2)
        for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
            cx = M + 34 + i * 30
            d.ellipse((cx - 9, y + 23, cx + 9, y + 41), fill=c)
        d.text((W // 2, y + 32), "bash", font=F(MONO, 22), fill=MUTED,
               anchor="mm")
        ty = y + 62 + 14
        for line in lines:
            x = M + pad
            if line.startswith("$ "):
                d.text((x, ty), "$", font=cf, fill=GREEN)
                d.text((x + tw(d, "$ ", cf), ty), line[2:], font=cf, fill=TEXT)
            elif line.lstrip().startswith("#"):
                d.text((x, ty), line, font=cf, fill=MUTED)
            else:
                d.text((x, ty), line, font=cf, fill=CODE)
            ty += lh
    return y + h


# ---------------------------------------------------------------- lesson post
def draw_lesson(day, idx, L, theme, s):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    col = LEVELS[level(day)]
    header(d, day, f"· {idx}/5", col)
    y = M + 64
    d.text((M, y), f"{CFG.get('series', '')} · {theme}".strip(" ·"), font=F(SANS, 26), fill=MUTED)
    y += 56
    cf = fit(d, MONO_B, L["cmd"], INNER, 104 * s, 56)
    d.text((M, y), L["cmd"], font=cf, fill=GREEN)
    y += cf.size * 1.12
    # man page line
    mf = F(MONO, 25 * s)
    man_line = f"man {L['cmd']}: {L['man']}"
    y = para(d, y + 4, man_line, mf, PURPLE, lh=1.35) + 26 * s
    y = label(d, y, "WHAT IT DOES", BLUE, s)
    y = para(d, y, L["what"], F(SANS, 33 * s), TEXT) + 20 * s
    y = label(d, y, "WHEN YOU'D USE IT", BLUE, s)
    y = para(d, y, L["when"], F(SANS, 31 * s), TEXT) + 26 * s
    y = terminal(d, y, L["example"], s) + 26 * s
    tf = F(SANS, 30 * s)
    d.text((M, y), "TIP", font=F(SANS_B, 24 * s), fill=col)
    y = para(d, y - 4 * s, L["tip"], tf, TEXT, max_w=INNER - 70 * s,
             x=M + 70 * s)
    fy = footer(d, day, col)
    return img, y, fy


# ---------------------------------------------------------------- quiz post
def draw_quiz(day, D, s):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    col = LEVELS[level(day)]
    header(d, day, "· QUIZ", col)
    y = M + 80
    d.text((M, y), "Test yourself", font=F(SANS_B, 64 * s), fill=TEXT)
    y += 82 * s
    d.text((M, y), f"{CFG.get('series', '').title()} · {D['theme']} · answers tomorrow".strip(" ·"), font=F(SANS, 26 * s),
           fill=MUTED)
    y += 64 * s
    qf, of = F(SANS_B, 31 * s), F(SANS, 28 * s)
    for i, q in enumerate(D["quiz"], 1):
        d.text((M, y), f"{i}.", font=qf, fill=col)
        y = para(d, y, q["q"], qf, TEXT, max_w=INNER - 50, x=M + 50, lh=1.3)
        x, oy = M + 50, y + 4 * s
        for letter, opt in zip("ABC", q["options"]):
            chip = f"{letter}  {opt}"
            w = tw(d, chip, of) + 30
            if x + w > W - M:
                x, oy = M + 50, oy + of.size * 1.75
            d.rounded_rectangle((x, oy - 6, x + w, oy + of.size + 10),
                                radius=12, fill=CARD, outline=BORDER, width=2)
            d.text((x + 15, oy), letter, font=F(SANS_B, of.size), fill=col)
            d.text((x + 15 + tw(d, f"{letter}  ", of), oy), opt, font=of,
                   fill=CODE)
            x += w + 14
        y = oy + of.size * 1.75 + 14 * s
    y += 6
    d.text((M, y), "Drop your answers below:  1_ 2_ 3_ 4_ 5_",
           font=F(SANS_B, 28 * s), fill=BLUE)
    y += 40 * s
    fy = footer(d, day, col)
    return img, y, fy


# ---------------------------------------------------------------- answers post
def draw_answers(day, D, s):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    col = LEVELS[level(day)]
    header(d, day, "· ANSWERS", col)
    y = M + 80
    d.text((M, y), "Quiz answers", font=F(SANS_B, 64 * s), fill=TEXT)
    y += 82 * s
    key = " ".join(f"{i}{'ABC'[q['answer']]}" for i, q in
                   enumerate(D["quiz"], 1))
    d.text((M, y), f"Answer key:  {key}", font=F(MONO_B, 30 * s), fill=GREEN)
    y += 66 * s
    qf, af, wf = F(SANS, 28 * s), F(SANS_B, 30 * s), F(SANS, 26 * s)
    for i, q in enumerate(D["quiz"], 1):
        y = para(d, y, f"{i}. {q['q']}", qf, MUTED, lh=1.3)
        ans = f"✓ {'ABC'[q['answer']]}) {q['options'][q['answer']]}"
        y = para(d, y + 2, ans, af, GREEN, x=M + 30, max_w=INNER - 30, lh=1.3)
        y = para(d, y, q["why"], wf, TEXT, x=M + 30, max_w=INNER - 30,
                 lh=1.3) + 22 * s
    d.text((M, y), "How many did you get right? Comment x/5",
           font=F(SANS_B, 28 * s), fill=BLUE)
    y += 40 * s
    fy = footer(d, day, col)
    return img, y, fy


def render(fn, path, *args):
    for s in [1.0, 0.96, 0.92, 0.88, 0.84, 0.80, 0.76]:
        img, y, fy = fn(*args, s)
        if y <= fy - 24:
            break
    else:
        print(f"  WARNING {path.name}: still overflows (y={y:.0f}, fy={fy})")
    img.save(path, "JPEG", quality=92)


# ---------------------------------------------------------------- captions
TAGS = ("#linux #linuxcommands #learnlinux #bash #terminal #ubuntu "
        "#programming #coding #computerscience #engineeringstudents "
        "#cse #devops #cybersecurity #techtips #100daysofcode")


def cap_lesson(day, idx, L, theme):
    return (f"Day {day} · {idx}/5 · {L['cmd']} 🐧\n\n"
            f"📖 man {L['cmd']}: {L['man']}\n\n"
            f"What it does: {L['what']}\n\n"
            f"When you'd use it: {L['when']}\n\n"
            f"💡 {L['tip']}\n\n"
            f"Today's theme: {theme}. Quiz on all 5 commands tonight at 8 PM!\n\n"
            f"📌 Save this · 🔔 Follow {CFG['handle']} for a new command every day\n"
            f"{CFG['tagline']}\n\n{TAGS}")


def cap_quiz(day, D):
    qs = "\n".join(f"{i}. {q['q']}  A) {q['options'][0]}  B) {q['options'][1]}"
                   f"  C) {q['options'][2]}" for i, q in enumerate(D["quiz"], 1))
    return (f"Day {day} quiz 🧠 How much do you remember from today?\n\n{qs}\n\n"
            f"Drop your answers in the comments: 1_ 2_ 3_ 4_ 5_ 👇\n"
            f"Answers drop tomorrow at 8 AM. No peeking at the man pages 😉\n\n"
            f"🔔 Follow {CFG['handle']} · {CFG['tagline']}\n\n{TAGS}")


def cap_answers(day, D):
    lines = "\n".join(f"{i}. {'ABC'[q['answer']]}) {q['options'][q['answer']]}: {q['why']}"
                      for i, q in enumerate(D["quiz"], 1))
    return (f"Day {day} quiz answers ✅\n\n{lines}\n\n"
            f"How many did you get? Comment your score x/5 👇\n"
            f"Today's 5 new commands start at 9 AM!\n\n"
            f"🔔 Follow {CFG['handle']} · {CFG['tagline']}\n\n{TAGS}")


def cap_reel(day, D):
    cmds = " · ".join(L["cmd"] for L in D["lessons"])
    lines = "\n".join(f"{i}. {L['cmd']}: {L['what']}" for i, L in enumerate(D["lessons"], 1))
    return (f"Day {day} in 90 seconds 🎬 {D['theme']}\n\n{lines}\n\n"
            f"Which one did you not know? Tell me below 👇\n"
            f"Quiz on all 5 tonight at 8 PM!\n\n"
            f"📌 Save this · 🔔 Follow {CFG['handle']} · {CFG['tagline']}\n\n"
            f"#reels #linuxreels {TAGS}")


def main():
    slots = CFG["slots"]
    captions, schedule = {}, []
    for D in DAYS:
        day = D["day"]
        off = day - 1
        for i, L in enumerate(D["lessons"], 1):
            pid = f"day{day:02d}-{i}-{L['cmd'].replace(' ', '_')}"
            render(draw_lesson, OUT / f"{pid}.jpg", day, i, L, D["theme"])
            captions[pid] = cap_lesson(day, i, L, D["theme"])
            schedule.append({"id": pid, "day_offset": off,
                             "time": slots["lessons"][i - 1]})
        pid = f"day{day:02d}-reel"
        captions[pid] = cap_reel(day, D)
        schedule.append({"id": pid, "day_offset": off, "time": slots["reel"],
                         "type": "reel"})
        pid = f"day{day:02d}-6-quiz"
        render(draw_quiz, OUT / f"{pid}.jpg", day, D)
        captions[pid] = cap_quiz(day, D)
        schedule.append({"id": pid, "day_offset": off, "time": slots["quiz"]})
        # answers go out the NEXT morning
        pid = f"day{day + 1:02d}-0-answers-for-day{day:02d}"
        render(draw_answers, OUT / f"{pid}.jpg", day, D)
        captions[pid] = cap_answers(day, D)
        schedule.append({"id": pid, "day_offset": off + 1,
                         "time": slots["answers"]})
    schedule.sort(key=lambda x: (x["day_offset"], x["time"]))
    (ROOT / "content" / "captions.json").write_text(
        json.dumps(captions, indent=1, ensure_ascii=False))
    (ROOT / "content" / "schedule.json").write_text(
        json.dumps(schedule, indent=1))
    print(f"{len(schedule)} posts rendered over {len(DAYS)} days")


if __name__ == "__main__":
    main()
