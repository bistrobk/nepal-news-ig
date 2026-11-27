"""Kinetic 9:16 Reel: story photo, animated headline, key points, branded outro, made-to-measure music.

make(post, photo, out_path, theme)  photo may be None (branded animated background).

Three scenes, about 13 s at 30 fps:
  0.0-4.5   photo with slow push-in, category chip, headline builds word by word, key word marked
  4.5-10.5  key points 01/02/03 on a dark, blurred version of the photo
  10.5-13   outro: ripple rings, स्पर्श, follow line, source and photo credit
Frames are drawn with Pillow and piped straight into ffmpeg.
"""
import math
import random
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from . import config, music
from .render import NPT, RAQM, THEMES, font, nepali_date, spaced, wrap

W, H, FPS = 1080, 1920, 30
X0, X1 = 80, 1000          # text column (Reels safe zone is about x 80..1000, y 250..1500)
S1, S2, END = 4.5, 10.5, 13.0
LAT, DEV = "NotoSans.ttf", "NotoSansDevanagari.ttf"


# ---------- timing helpers ----------
def clamp(v, a=0.0, b=1.0):
    return max(a, min(b, v))


def ease(p):  # ease-out cubic
    p = clamp(p)
    return 1 - (1 - p) ** 3


def ease_io(p):
    p = clamp(p)
    return 4 * p ** 3 if p < .5 else 1 - (-2 * p + 2) ** 3 / 2


def prog(t, start, dur):
    return ease((t - start) / dur)


# ---------- mood ----------
def mood(post):
    text = f"{post.get('headline_en', '')} {' '.join(post.get('points_en', []))}".lower()
    cat = post.get("category", "")
    if re.search(r"\b(kill|killed|dead|death|died|dies|accident|flood|landslide|crash|blast|victim|mourn|tragedy|earthquake)", text):
        return "somber"
    if re.search(r"\b(arrest|protest|strike|fire|crisis|clash|curfew|warn|alert|emergency|scam|raid|ban)", text):
        return "urgent"
    if cat in ("Sport", "Sports", "Tech", "Technology", "Culture", "Entertainment") or \
            re.search(r"\b(win|wins|won|record|festival|celebrat|launch|first|award|medal|victory)", text):
        return "upbeat"
    if cat in ("Health", "Education", "Weather", "Environment"):
        return "calm"
    return "serious"


# ---------- static layers ----------
def cover(img, w, h):
    s = max(w / img.width, h / img.height)
    img = img.resize((math.ceil(img.width * s), math.ceil(img.height * s)), Image.LANCZOS)
    x, y = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))


def vgrad(w, h, top, bottom, stops):
    """Vertical alpha mask. stops: [(pos 0..1, alpha 0..255)]."""
    col = Image.new("L", (1, h))
    px = col.load()
    for y in range(h):
        p = y / (h - 1)
        for (p0, a0), (p1, a1) in zip(stops, stops[1:]):
            if p0 <= p <= p1:
                k = (p - p0) / max(1e-6, p1 - p0)
                k = k * k * (3 - 2 * k)
                px[0, y] = int(a0 + (a1 - a0) * k)
                break
    return col.resize((w, h))


def rings_layer(color, accent, scale=1.0, spin=0.0, width=4):
    """The brand's broken-ellipse 'touch' rings, on a transparent 1080x1080 layer."""
    ss = 2
    size = 1080 * ss
    lay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    c = size / 2
    spec = [(26, 200, 0), (46, 120, 40), (66, 250, 35), (88, 60, 30),
            (110, 170, 45), (132, 300, 30), (156, 20, 40), (180, 220, 35)]
    k = 2.6 * scale * ss
    for i, (r, g0, gap) in enumerate(spec):
        rx, ry = r * k, r * 1.35 * k
        box = [c - rx, c - ry, c + rx, c + ry]
        rot = spin * (1 if i % 2 else -1) * (1 + i * .15)
        if gap:
            d.arc(box, g0 + gap + rot, g0 + 360 + rot, fill=color, width=width * ss)
        else:
            d.ellipse(box, outline=color, width=width * ss)
    d.ellipse([c - 11 * ss, c - 11 * ss, c + 11 * ss, c + 11 * ss], fill=accent)
    return lay.resize((1080, 1080), Image.LANCZOS)


def fallback_bg(post, t):
    """No photo: deep navy field with large drifting rings and a soft crimson glow."""
    bg = Image.new("RGB", (W, H), t["bg"])
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).ellipse([W * .25, H * .05, W * 1.25, H * .55], fill=90)
    glow = glow.filter(ImageFilter.GaussianBlur(160))
    bg.paste(Image.new("RGB", (W, H), t["accent"]), (0, 0), glow)
    lay = rings_layer((255, 255, 255, 34), (*t["accent"], 255), scale=1.25, width=3)
    bg.paste(lay, (260, 60), lay)
    return bg


def sprite(text, fnt, fill, pad=6):
    """Text drawn once onto a tight transparent layer."""
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    l, tp, r, b = probe.textbbox((0, 0), text, font=fnt)
    img = Image.new("RGBA", (r - l + pad * 2, b - tp + pad * 2), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((pad - l, pad - tp), text, font=fnt, fill=fill)
    return img, (l - pad, tp - pad)


def fade(img, a):
    if a >= 1:
        return img
    out = img.copy()
    out.putalpha(img.getchannel("A").point(lambda v: int(v * a)))
    return out


def key_index(words):
    """Word to mark: the first with a digit, else the longest (skipping short glue words)."""
    for i, w in enumerate(words):
        if any(ch.isdigit() for ch in w):
            return i
    return max(range(len(words)), key=lambda i: len(re.sub(r"\W", "", words[i])))


# ---------- the video ----------
class Reel:
    def __init__(self, post, photo, theme):
        self.post = post
        self.t = dict(THEMES["navy"])  # Reels always use the dark look; photos read better on it
        self.accent = self.t["accent"]
        self.bg = self.t["bg"]
        random.seed(3)
        probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))

        # backgrounds: big photo for the push-in, blurred dark copy for the points
        src = None
        if photo:
            try:
                src = Image.open(photo).convert("RGB")
            except Exception:
                src = None
        self.has_photo = src is not None
        base = cover(src, W, H) if src else fallback_bg(post, self.t)
        self.photo = cover(src, int(W * 1.14), int(H * 1.14)) if src else base.resize((int(W * 1.14), int(H * 1.14)))
        dark = base.filter(ImageFilter.GaussianBlur(28))
        dark = Image.blend(dark, Image.new("RGB", (W, H), self.bg), .72)
        self.blur = dark
        # gradient that sinks the photo into navy under the headline
        self.shade = vgrad(W, H, 0, 0, [(0, 130), (.14, 25), (.38, 10), (.56, 175), (.68, 240), (1, 255)])
        self.shade_rgb = Image.new("RGB", (W, H), self.bg)

        # grain, a few frames cycled
        self.grain = [Image.effect_noise((W // 2, H // 2), 40).resize((W, H)).convert("RGB") for _ in range(4)]

        # ---- scene 1 text ----
        head = post["headline_en"]
        for size in (104, 96, 88, 80, 72, 66):
            hf = font(LAT, size, "Black")
            lines = wrap(probe, head, hf, X1 - X0)
            if len(lines) <= 4:
                break
        self.hsize = size
        lh = int(size * 1.08)
        words, self.marker = [], None
        flat = head.split()
        ki = key_index(flat)
        n = 0
        # headline block sits above the Nepali line, bottom aligned at y ~1330
        ne_h = 0
        self.ne_lines = []
        if RAQM and post.get("headline_ne"):
            nf = font(DEV, 46, "SemiBold")
            self.ne_lines = [sprite(l, nf, (210, 214, 228)) for l in wrap(probe, post["headline_ne"], nf, X1 - X0)[:2]]
            ne_h = 34 + 62 * len(self.ne_lines)
        top = 1360 - ne_h - lh * len(lines)
        self.chip_y = top - 92
        for li, line in enumerate(lines):
            x = X0
            y = top + li * lh
            for w in line.split():
                spr, off = sprite(w, hf, (255, 255, 255))
                wl = probe.textlength(w, font=hf)
                if n == ki:
                    core = re.sub(r"[^\w%]+$", "", w) or w
                    l, tp, r, b = probe.textbbox((x, y), core, font=hf)
                    self.marker = (x - 14, tp - 10, r + 14, b + 12)
                words.append((spr, int(x + off[0]), int(y + off[1]), n))
                x += wl + probe.textlength(" ", font=hf)
                n += 1
        self.words = words
        self.nwords = n
        self.ne_y = top + lh * len(lines) + 30

        # chip, wordmark, date
        cf = font(LAT, 30, "Bold")
        cat = post["category"].upper()
        cw = sum(probe.textlength(c, font=cf) + 5 for c in cat) - 5
        chip = Image.new("RGBA", (int(cw) + 44, 56), (*self.accent, 255))
        spaced(ImageDraw.Draw(chip), (22, 9), cat, cf, (255, 255, 255), 5)
        self.chip = chip
        bs = nepali_date() if RAQM else None
        if bs:
            self.date = sprite(bs, font(DEV, 34, "SemiBold"), (255, 255, 255, 235))
        else:
            self.date = sprite(datetime.now(NPT).strftime("%-d %b %Y").upper(), font(LAT, 30, "SemiBold"),
                               (255, 255, 255, 235))
        wm = Image.new("RGBA", (420, 70), (0, 0, 0, 0))
        spaced(ImageDraw.Draw(wm), (0, 8), config.BRAND.upper(), font(LAT, 34, "Black"), (255, 255, 255), 9)
        self.wordmark = wm

        # ---- scene 2: points ----
        pts = [p for p in post.get("points_en", []) if p][:3] or [post["headline_en"]]
        self.points = []
        pf = font(LAT, 72, "Bold")
        for i, p in enumerate(pts):
            ls = wrap(probe, p, pf, X1 - X0)[:5]
            self.points.append([sprite(l, pf, (255, 255, 255)) for l in ls])
        self.nf = font(LAT, 150, "Black")
        self.num = [sprite(f"{i + 1:02d}", self.nf, (*self.accent, 255)) for i in range(len(pts))]
        self.of = sprite(f"/ {len(pts):02d}", font(LAT, 40, "Bold"), (150, 158, 180))
        self.kp = sprite("KEY POINTS", font(LAT, 30, "Bold"), (150, 158, 180))
        self.slot = (S2 - S1) / len(pts)

        # ---- scene 3: outro ----
        self.mark = sprite("स्पर्श" if RAQM else config.BRAND.title(), font(DEV if RAQM else LAT, 170, "ExtraBold"),
                           (255, 255, 255))
        self.tag = sprite("News you can feel.", font(LAT, 48, "SemiBold"), (200, 206, 224))
        self.follow = sprite(f"Follow {config.HANDLE}", font(LAT, 46, "Bold"), (255, 255, 255))
        story = post.get("story", {})
        credit = f"Source: {story.get('source', '')}"
        if self.has_photo:
            credit += f"   ·   Photo: {story.get('source', '')}"
        self.credit = sprite(credit, font(LAT, 30, "Medium"), (150, 158, 180))
        self.small_credit = sprite(f"PHOTO: {story.get('source', '').upper()}", font(LAT, 22, "SemiBold"),
                                   (255, 255, 255, 170)) if self.has_photo else None

    # ---- pieces ----
    def progress(self, img, t):
        """Three segments at the top, one per scene, filling as the scene plays."""
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        segs = [(0, S1), (S1, S2), (S2, END)]
        gap, y = 12, 236
        w = (X1 - X0 - gap * 2) / 3
        for i, (a, b) in enumerate(segs):
            x = X0 + i * (w + gap)
            d.rounded_rectangle([x, y, x + w, y + 6], 3, fill=(255, 255, 255, 64))
            p = clamp((t - a) / (b - a))
            if p > 0:
                d.rounded_rectangle([x, y, x + max(6, w * p), y + 6], 3, fill=(255, 255, 255, 255))
        if img.mode == "RGBA":
            img.alpha_composite(layer)
        else:
            img.paste(layer, (0, 0), layer)

    def top_bar(self, img, t, a=1.0):
        y = 276
        img.alpha_composite(fade(self.wordmark, a), (X0, y)) if img.mode == "RGBA" else img.paste(
            self.wordmark, (X0, y), fade(self.wordmark, a))
        spr, off = self.date
        img.paste(spr, (X1 - spr.width - off[0] + 6, y + 4), fade(spr, a))

    def scene1(self, t):
        # push-in on the photo, slight drift up
        z = 1.0 + .10 * ease_io(t / (S1 + .6))
        pw, ph = self.photo.size
        cw, ch = int(W * 1.14 / z), int(H * 1.14 / z)
        cx = (pw - cw) / 2
        cy = (ph - ch) / 2 - 40 * ease_io(t / S1)
        frame = self.photo.crop((int(cx), int(cy), int(cx) + cw, int(cy) + ch)).resize((W, H), Image.BILINEAR)
        frame.paste(self.shade_rgb, (0, 0), self.shade)
        a_in = prog(t, 0, .35)
        self.top_bar(frame, t, a_in)
        if self.small_credit:
            spr, _ = self.small_credit
            frame.paste(spr, (X1 - spr.width, 336), fade(spr, a_in))

        # chip slides in from the left
        p = prog(t, .15, .45)
        if p > 0:
            frame.paste(self.chip, (int(X0 - 40 * (1 - p)), self.chip_y), fade(self.chip, p))

        # marker bar grows behind the key word after it lands
        d = ImageDraw.Draw(frame)
        step = .11
        if self.marker:
            x0, y0, x1, y1 = self.marker
            t_m = .35 + self.key_n() * step + .35
            pm = prog(t, t_m, .4)
            if pm > 0:
                d.rectangle([x0, y0, x0 + (x1 - x0) * pm, y1], fill=self.accent)
        # words rise in one after another
        for spr, x, y, n in self.words:
            pw_ = prog(t, .35 + n * step, .45)
            if pw_ <= 0:
                continue
            frame.paste(spr, (x, int(y + 60 * (1 - pw_))), fade(spr, pw_))
        # Nepali headline
        pn = prog(t, .35 + self.nwords * step + .2, .6)
        if pn > 0 and self.ne_lines:
            d.rectangle([X0, self.ne_y + 6, X0 + 6, self.ne_y + 6 + 62 * len(self.ne_lines) - 14], fill=self.accent)
            for i, (spr, off) in enumerate(self.ne_lines):
                frame.paste(spr, (X0 + 26 + off[0], self.ne_y + i * 62 + int(20 * (1 - pn))), fade(spr, pn))
        return frame

    def key_n(self):
        if not hasattr(self, "_kn"):
            words = self.post["headline_en"].split()
            self._kn = key_index(words)
        return self._kn

    def scene2(self, t):
        lt = t - S1
        z = 1.0 + .04 * (lt / (S2 - S1))
        frame = self.blur
        if z > 1.001:
            cw, ch = int(W / z), int(H / z)
            frame = frame.crop(((W - cw) // 2, (H - ch) // 2, (W - cw) // 2 + cw, (H - ch) // 2 + ch)).resize(
                (W, H), Image.BILINEAR)
        else:
            frame = frame.copy()
        self.top_bar(frame, t)
        d = ImageDraw.Draw(frame)
        i = min(len(self.points) - 1, int(lt / self.slot))
        st = lt - i * self.slot
        out = clamp((st - (self.slot - .28)) / .28) if i < len(self.points) - 1 else 0
        y0 = 820
        # "KEY POINTS  01 / 03"
        spr, off = self.kp
        frame.paste(spr, (X0, y0 - 120), spr)
        # big number: slides up, old one slides out
        num, noff = self.num[i]
        pn = prog(st, 0, .4)
        ny = y0 + int(70 * (1 - pn)) - int(70 * ease(out))
        a = pn * (1 - out)
        frame.paste(num, (X0 + noff[0], ny + noff[1]), fade(num, a))
        ofs, ooff = self.of
        frame.paste(ofs, (X0 + num.width + 10, y0 + 108), fade(ofs, a))
        # accent rule that draws across
        pr = prog(st, .1, .5)
        d.rectangle([X0, y0 + 190, X0 + int(160 * pr * (1 - out)), y0 + 197], fill=self.accent)
        # point text, line by line
        for k, (spr, off) in enumerate(self.points[i]):
            pl = prog(st, .2 + k * .09, .45)
            if pl <= 0:
                continue
            al = pl * (1 - out)
            frame.paste(spr, (X0 + off[0] + int(-30 * ease(out)), y0 + 250 + k * 92 + int(40 * (1 - pl)) + off[1]),
                        fade(spr, al))
        return frame

    def scene3(self, t):
        lt = t - S2
        frame = Image.new("RGB", (W, H), self.bg)
        # rings ripple out from the centre
        sc = .7 + .5 * ease(lt / 1.4)
        lay = rings_layer((*self.t["rings"], 255), (*self.accent, 255), scale=sc, spin=lt * 10)
        frame.paste(lay, (0, 330), fade(lay, prog(lt, 0, .5)))
        cy = 870
        spr, off = self.mark
        pm = prog(lt, .25, .6)
        frame.paste(spr, ((W - spr.width) // 2, cy - spr.height // 2 + int(40 * (1 - pm))), fade(spr, pm))
        spr, off = self.tag
        pt = prog(lt, .55, .5)
        frame.paste(spr, ((W - spr.width) // 2, cy + 160 + int(20 * (1 - pt))), fade(spr, pt))
        # follow pill
        pf = prog(lt, .8, .5)
        if pf > 0:
            spr, off = self.follow
            pw_, ph_ = spr.width + 70, 96
            pill = Image.new("RGBA", (pw_, ph_), (0, 0, 0, 0))
            ImageDraw.Draw(pill).rounded_rectangle([0, 0, pw_ - 1, ph_ - 1], 48, fill=(*self.accent, 255))
            pill.alpha_composite(spr, (35, (ph_ - spr.height) // 2))
            frame.paste(pill, ((W - pw_) // 2, 1240 + int(30 * (1 - pf))), fade(pill, pf))
        spr, off = self.credit
        pc = prog(lt, 1.0, .5)
        frame.paste(spr, ((W - spr.width) // 2, 1400), fade(spr, pc))
        return frame

    def frame(self, i):
        t = i / FPS
        if t < S1:
            f = self.scene1(t)
        elif t < S2:
            f = self.scene2(t)
        else:
            f = self.scene3(t)
        # quick flash-wipe at each cut
        for c in (S1, S2):
            if 0 <= t - c < .2:
                f = Image.blend(f, Image.new("RGB", (W, H), self.accent), .35 * (1 - (t - c) / .2))
        rgba = f.convert("RGBA")
        self.progress(rgba, t)
        f = rgba.convert("RGB")
        f = Image.blend(f, self.grain[i % 4], .035)
        # fade to black at the very end so the loop restart is clean
        if t > END - .25:
            f = Image.blend(f, Image.new("RGB", (W, H), (0, 0, 0)), clamp((t - (END - .25)) / .25) * .6)
        return f


def make(post, photo, out_path, theme=None, preview=None):
    """Render the Reel to out_path. preview: list of seconds to also save as PNG stills (for review)."""
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    r = Reel(post, photo, theme)
    m = mood(post)
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "music.wav"
        music.make(wav, END, m, hits=[S1, S2])
        cmd = [ff, "-y", "-loglevel", "error",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
               "-i", str(wav),
               "-map", "0:v", "-map", "1:a",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-profile:v", "high",
               "-pix_fmt", "yuv420p", "-color_range", "tv",
               "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2",
               "-shortest", "-movflags", "+faststart", str(out_path)]
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        want = {int(s * FPS) for s in (preview or [])}
        try:
            for i in range(int(END * FPS)):
                f = r.frame(i)
                if i in want:
                    f.save(Path(out_path).with_name(f"{Path(out_path).stem}-{i / FPS:04.1f}s.png"))
                p.stdin.write(f.tobytes())
            p.stdin.close()
        except BrokenPipeError:
            pass
        err = p.stderr.read().decode()
        if p.wait() != 0:
            raise RuntimeError(f"ffmpeg failed: {err[-500:]}")
    return out_path, m
