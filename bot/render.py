"""Draw the 1080x1350 news card, and turn it into a short Reel video."""
import subprocess
from datetime import datetime, timedelta, timezone

from PIL import Image, ImageDraw, ImageFont, features

from . import config

W, H = 1080, 1350
PAD = 80
RAQM = features.check("raqm")  # needed to shape Devanagari correctly
NPT = timezone(timedelta(hours=5, minutes=45))  # Nepal time, for the date on the card

THEMES = {
    "navy": dict(bg=(16, 21, 38), ink=(255, 255, 255), muted=(150, 158, 180),
                 rule=(42, 49, 72), rings=(54, 62, 90), accent=(235, 72, 92)),
    "light": dict(bg=(243, 244, 248), ink=(18, 22, 40), muted=(98, 104, 124),
                  rule=(214, 217, 228), rings=(206, 210, 224), accent=(200, 30, 50)),
}


def font(name, size, weight="Bold"):
    f = ImageFont.truetype(str(config.FONTS / name), size,
                           layout_engine=ImageFont.Layout.RAQM if RAQM else ImageFont.Layout.BASIC)
    try:
        f.set_variation_by_name(weight)
    except Exception:
        pass
    return f


def wrap(draw, text, fnt, width):
    """Wrap by measured pixel width (works for Devanagari too)."""
    lines, line = [], ""
    for word in text.split():
        test = f"{line} {word}".strip()
        if draw.textlength(test, font=fnt) <= width:
            line = test
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def spaced(draw, xy, text, fnt, fill, track):
    """Draw letter-spaced text, return its width."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=fnt, fill=fill)
        x += draw.textlength(ch, font=fnt) + track
    return x - track - xy[0]


def rings(img, cx, cy, color, accent, scale=3):
    """Fingerprint-style broken ellipses ('sparsha' = touch), drawn large then shrunk for smooth edges."""
    layer = Image.new("RGBA", (W * scale, H * scale), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    s = scale
    # (radius, gap start, gap size) in degrees; Pillow angles go clockwise from 3 o'clock
    spec = [(26, 200, 0), (46, 120, 40), (66, 250, 35), (88, 60, 30),
            (110, 170, 45), (132, 300, 30), (156, 20, 40), (180, 220, 35)]
    for r, g0, gap in spec:
        box = [(cx - r) * s, (cy - r * 1.35) * s, (cx + r) * s, (cy + r * 1.35) * s]
        if gap:
            d.arc(box, g0 + gap, g0 + 360, fill=color, width=3 * s)
        else:
            d.ellipse(box, outline=color, width=3 * s)
    d.ellipse([(cx - 8) * s, (cy - 8) * s, (cx + 8) * s, (cy + 8) * s], fill=accent)
    layer = layer.resize((W, H), Image.LANCZOS)
    img.paste(layer, (0, 0), layer)


def nepali_date():
    """Today's Bikram Sambat date in Devanagari, e.g. '१० मंसिर २०८३'. None if the package is missing."""
    try:
        import nepali_datetime
        bs = nepali_datetime.date.from_datetime_date(datetime.now(NPT).date())
        return bs.strftime("%D %N %K").lstrip("०")
    except Exception:
        return None


def header(img, label, t):
    """Top row: LABEL | date            brand. Returns the draw object."""
    d = ImageDraw.Draw(img)
    top = 92
    cf = font("NotoSans.ttf", 25)
    cw = spaced(d, (PAD, top), label.upper(), cf, t["accent"], 5)
    x = PAD + cw + 22
    d.line([x, top + 4, x, top + 30], fill=t["rule"], width=2)
    bs = nepali_date() if RAQM else None
    if bs:
        df = font("NotoSansDevanagari.ttf", 27, "SemiBold")
        d.text((x + 22, top - 4), bs, font=df, fill=t["muted"])
    else:  # fallback: English date, Nepal time
        df = font("NotoSans.ttf", 23, "SemiBold")
        d.text((x + 22, top + 2), datetime.now(NPT).strftime("%-d %b %Y").upper(), font=df, fill=t["muted"])
    if RAQM:
        bf = font("NotoSansDevanagari.ttf", 58, "ExtraBold")
        mark, by = "स्पर्श", top - 26
    else:  # no shaping library: Devanagari would break, use the Latin name
        bf = font("NotoSans.ttf", 34, "ExtraBold")
        mark, by = config.BRAND, top - 4
    d.text((W - PAD - d.textlength(mark, font=bf), by), mark, font=bf, fill=t["ink"])
    return d


def footer(d, left, t):
    d.line([PAD, 1212, W - PAD, 1212], fill=t["rule"], width=2)
    sf = font("NotoSans.ttf", 24, "Regular")
    d.text((PAD, 1240), left, font=sf, fill=t["muted"])
    hf = font("NotoSans.ttf", 27)
    d.text((W - PAD - d.textlength(config.HANDLE, font=hf), 1237), config.HANDLE, font=hf, fill=t["ink"])


def card(post, path, theme=None):
    t = THEMES.get(theme or config.THEME, THEMES["navy"])
    img = Image.new("RGB", (W, H), t["bg"])
    rings(img, 968, 400, t["rings"], t["accent"])
    d = header(img, post["category"], t)

    # headline: biggest size that fits in 4 lines, left of the rings
    hw = 730
    for size in (88, 80, 72, 64, 58):
        hf = font("NotoSans.ttf", size, "ExtraBold")
        lines = wrap(d, post["headline_en"], hf, hw)
        if len(lines) <= 4:
            break
    lines = lines[:4]
    y = 205
    for ln in lines:
        d.text((PAD, y), ln, font=hf, fill=t["ink"])
        y += int(size * 1.12)

    # Nepali headline under the English one (needs shaping)
    ne = post.get("headline_ne", "") if RAQM else ""
    if ne:
        nf = font("NotoSansDevanagari.ttf", 46, "Bold")
        y += 14
        for ln in wrap(d, ne, nf, hw)[:2]:
            d.text((PAD, y), ln, font=nf, fill=t["muted"])
            y += 64
    head_end = y

    # points: right under the headline
    pf = font("NotoSans.ttf", 32, "Regular")
    blocks = [wrap(d, p, pf, W - 2 * PAD - 50)[:2] for p in post["points_en"][:3]]
    lh, gap = 44, 24
    y = head_end + 70
    for b in blocks:
        if y + len(b) * lh > 1160:
            break
        cy = y + 23
        d.ellipse([PAD, cy - 11, PAD + 22, cy + 11], outline=t["accent"], width=3)
        d.ellipse([PAD + 6, cy - 5, PAD + 16, cy + 5], fill=t["accent"])
        for ln in b:
            d.text((PAD + 48, y), ln, font=pf, fill=t["ink"])
            y += lh
        y += gap

    footer(d, f"Source: {post['story']['source']}", t)
    img.save(path, "JPEG", quality=92)
    return path


def digest_card(items, path, sources, theme="navy"):
    """Evening summary: big title, then up to 6 numbered stories (category, line)."""
    t = THEMES[theme]
    img = Image.new("RGB", (W, H), t["bg"])
    rings(img, 968, 400, t["rings"], t["accent"])
    d = header(img, "Daily summary", t)
    if RAQM:  # English title on one line, Nepali under it
        d.text((PAD, 205), "Today in Nepal", font=font("NotoSans.ttf", 72, "ExtraBold"), fill=t["ink"])
        d.text((PAD, 300), "आजको नेपाल", font=font("NotoSansDevanagari.ttf", 56, "Bold"), fill=t["muted"])
    else:
        tf = font("NotoSans.ttf", 88, "ExtraBold")
        d.text((PAD, 205), "Today", font=tf, fill=t["ink"])
        d.text((PAD, 304), "in Nepal", font=tf, fill=t["ink"])

    nf = font("NotoSans.ttf", 38, "ExtraBold")
    cf = font("NotoSans.ttf", 19)
    lf = font("NotoSans.ttf", 30, "SemiBold")
    nef = font("NotoSansDevanagari.ttf", 27, "Medium")
    y = 440
    for n, item in enumerate(items[:6], 1):
        cat, line = item[0], item[1]
        ne = item[2] if len(item) > 2 and RAQM else ""  # Devanagari needs shaping
        lines = wrap(d, line, lf, W - 2 * PAD - 80)[:2]
        ne_lines = wrap(d, ne, nef, W - 2 * PAD - 80)[:1] if ne else []
        if y + 28 + len(lines) * 38 + len(ne_lines) * 38 > 1190:
            break
        d.text((PAD, y + 6), f"{n:02d}", font=nf, fill=t["accent"])
        spaced(d, (PAD + 80, y), cat.upper(), cf, t["muted"], 3)
        yy = y + 28
        for ln in lines:
            d.text((PAD + 80, yy), ln, font=lf, fill=t["ink"])
            yy += 38
        for ln in ne_lines:
            d.text((PAD + 80, yy - 2), ln, font=nef, fill=t["muted"])
            yy += 38
        y = yy + 18

    footer(d, f"From {sources} sources", t)
    img.save(path, "JPEG", quality=92)
    return path


def reel(card_path, out_path, seconds=10):
    """Slow zoom on the card, 1080x1920 with blurred fill, silent audio track."""
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    frames = seconds * 30
    vf = (
        "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=30:5,"
        "eq=brightness=-0.15[bg];"
        f"[0:v]scale=1080:-2,zoompan=z='min(zoom+0.0006,1.08)':d={frames}:"
        "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1350:fps=30[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2,scale=out_range=tv,format=yuv420p[v]"
    )
    cmd = [ff, "-y", "-loop", "1", "-i", str(card_path),
           "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
           "-filter_complex", vf, "-map", "[v]", "-map", "1:a",
           "-t", str(seconds), "-r", "30", "-c:v", "libx264", "-preset", "veryfast",
           "-profile:v", "high", "-pix_fmt", "yuv420p", "-color_range", "tv", "-c:a", "aac", "-b:a", "128k",
           "-shortest", "-movflags", "+faststart", str(out_path)]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path
