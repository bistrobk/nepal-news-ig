"""Draw the 1080x1350 news card, and turn it into a short Reel video."""
import subprocess
import textwrap

from PIL import Image, ImageDraw, ImageFont, features

from . import config

W, H = 1080, 1350
PAD = 80
BG = (14, 22, 38)
ACCENT = (220, 20, 60)      # Nepal crimson
WHITE = (245, 245, 245)
GREY = (170, 180, 195)
RAQM = features.check("raqm")  # needed to shape Devanagari correctly


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


def draw_block(draw, y, text, fnt, fill, width, gap=1.25, max_lines=4):
    lines = wrap(draw, text, fnt, width)[:max_lines]
    for ln in lines:
        draw.text((PAD, y), ln, font=fnt, fill=fill)
        y += int(fnt.size * gap)
    return y


def card(post, path):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    width = W - 2 * PAD
    nepali = RAQM

    # top bar: category tag + brand
    d.rectangle([0, 0, W, 14], fill=ACCENT)
    tag = post["category"].upper()
    tf = font("NotoSans.ttf", 34)
    tw = d.textlength(tag, font=tf)
    d.rounded_rectangle([PAD, 70, PAD + tw + 40, 124], radius=10, fill=ACCENT)
    d.text((PAD + 20, 75), tag, font=tf, fill=WHITE)
    bf = font("NotoSans.ttf", 34, "SemiBold")
    d.text((W - PAD - d.textlength(config.BRAND, font=bf), 77), config.BRAND, font=bf, fill=GREY)

    y = 190
    if nepali:
        y = draw_block(d, y, post["headline_ne"], font("NotoSansDevanagari.ttf", 74), WHITE, width, 1.4, 3)
        y += 20
        y = draw_block(d, y, post["headline_en"], font("NotoSans.ttf", 48, "SemiBold"), GREY, width, 1.25, 3)
    else:
        y = draw_block(d, y, post["headline_en"], font("NotoSans.ttf", 76), WHITE, width, 1.2, 4)

    y += 40
    d.rectangle([PAD, y, PAD + 120, y + 8], fill=ACCENT)
    y += 50

    pf = font("NotoSans.ttf", 38, "Regular")
    for p in post["points_en"][:3]:
        if y > H - 300:
            break
        d.ellipse([PAD, y + 16, PAD + 14, y + 30], fill=ACCENT)
        lines = wrap(d, p, pf, width - 40)[:2]
        for ln in lines:
            d.text((PAD + 36, y), ln, font=pf, fill=WHITE)
            y += 52
        y += 18

    # footer
    d.line([PAD, H - 170, W - PAD, H - 170], fill=(50, 62, 85), width=2)
    sf = font("NotoSans.ttf", 32, "Regular")
    d.text((PAD, H - 140), f"Source: {post['story']['source']}", font=sf, fill=GREY)
    hf = font("NotoSans.ttf", 40)
    d.text((PAD, H - 92), config.HANDLE, font=hf, fill=WHITE)
    follow = "Follow for daily Nepal news"
    d.text((W - PAD - d.textlength(follow, font=sf), H - 86), follow, font=sf, fill=GREY)

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
