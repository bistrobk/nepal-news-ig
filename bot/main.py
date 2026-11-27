"""Entry point.

python -m bot.main prepare [--reel]   pick a story, draw media, write state/pending.json
python -m bot.main digest             today's summary card (evening), write state/pending.json
python -m bot.main publish            post what prepare made, record it in state/posted.json
python -m bot.main dry-run [--reel]   prepare only, nothing is saved to state
python -m bot.main cleanup            delete media files older than KEEP_MEDIA_DAYS
python -m bot.main report             write state/report.md from Instagram insights
"""
import json
import sys
import time
from datetime import datetime

from . import config, fetch, render

NPT = config.NPT


def caption_text(post):
    tags = " ".join(f"#{h}" for h in post["hashtags"])
    return f"{post['caption'].strip()}\n\n{tags}"[:2200]


def prepare(reel=False, save=True):
    from .summarize import write_post
    stories, posted = fetch.fresh_stories()
    if not stories:
        print("Nothing new")
        return None
    post = write_post(stories, posted)
    if not post:
        return None
    config.MEDIA.mkdir(exist_ok=True)
    stamp = datetime.now(NPT).strftime("%Y%m%d-%H%M")
    img = config.MEDIA / f"{stamp}.jpg"
    theme = config.THEME
    if theme == "topic":  # hard news on navy, lighter topics on light
        theme = "navy" if post["category"] in config.NAVY_TOPICS else "light"
    elif theme == "mix":  # alternate navy / light, one post each
        theme = ("navy", "light")[len(posted) % 2]
    render.card(post, img, theme)
    post["theme"] = theme
    post["image"] = img.name
    if reel:
        vid = config.MEDIA / f"{stamp}.mp4"
        render.reel(img, vid)
        post["video"] = vid.name
    print(f"Prepared: {post['headline_en']} ({post['story']['source']})")
    if save:
        config.STATE.mkdir(exist_ok=True)
        config.PENDING_FILE.write_text(json.dumps(post, ensure_ascii=False, indent=1))
    else:
        print(caption_text(post))
    return post


def digest(save=True):
    """Evening 'Today in Nepal' card from what was posted earlier today (Nepal date)."""
    from .summarize import write_digest
    today = datetime.now(NPT).date()
    todays = [p for p in fetch.load_posted()
              if datetime.fromisoformat(p["time"]).astimezone(NPT).date() == today]
    if any(p.get("type") == "digest" for p in todays):
        print("Summary already posted today")
        return None
    entries = [p for p in todays if p.get("type") != "digest"]
    if len(entries) < 3:
        print(f"Only {len(entries)} posts today, no summary")
        return None
    out = write_digest(entries)
    if not out or len(out["items"]) < 3:
        print("No summary this run")
        return None
    config.MEDIA.mkdir(exist_ok=True)
    stamp = datetime.now(NPT).strftime("%Y%m%d-%H%M")
    img = config.MEDIA / f"{stamp}.jpg"
    sources = len({p["source"] for p in entries})
    render.digest_card(out["items"], img, sources)
    post = {"type": "digest", "category": "Digest", "headline_en": "Today in Nepal",
            "caption": out["caption"], "hashtags": out["hashtags"], "items": out["items"],
            "story": {"source": config.BRAND, "link": ""}, "theme": "navy", "image": img.name}
    print(f"Prepared summary of {len(out['items'])} stories")
    if save:
        config.STATE.mkdir(exist_ok=True)
        config.PENDING_FILE.write_text(json.dumps(post, ensure_ascii=False, indent=1))
    else:
        print(caption_text(post))
    return post


def publish():
    from . import publish as ig
    if not config.PENDING_FILE.exists():
        print("No pending post")
        return
    post = json.loads(config.PENDING_FILE.read_text())
    cap = caption_text(post)
    if post.get("video"):
        media_id = ig.post_reel(config.MEDIA / post["video"], cap,
                                video_url=f"{config.MEDIA_BASE}/{post['video']}")
    else:
        media_id = ig.post_image(f"{config.MEDIA_BASE}/{post['image']}", cap)
    posted = fetch.load_posted()
    posted.append({
        "time": datetime.now(NPT).isoformat(timespec="minutes"),
        "id": media_id,
        "type": post.get("type") or ("reel" if post.get("video") else "image"),
        "category": post["category"],
        "headline_en": post["headline_en"],
        "headline_ne": post.get("headline_ne", ""),
        "source": post["story"]["source"],
        "link": post["story"]["link"],
    })
    config.POSTED_FILE.write_text(json.dumps(posted[-600:], ensure_ascii=False, indent=1))
    config.PENDING_FILE.unlink()
    print(f"Published {media_id}")


def cleanup():
    # Use the date in the file name (YYYYMMDD-HHMM): a fresh CI checkout resets mtimes.
    cutoff = time.time() - config.KEEP_MEDIA_DAYS * 86400
    for f in config.MEDIA.glob("*"):
        if not f.is_file() or f.name == ".gitkeep":
            continue
        try:
            made = datetime.strptime(f.stem, "%Y%m%d-%H%M").replace(tzinfo=NPT).timestamp()
        except ValueError:
            made = f.stat().st_mtime
        if made < cutoff:
            f.unlink()
            print(f"deleted {f.name}")


def report():
    from . import publish as ig
    rows = ig.recent_insights()
    posted = {p["id"]: p for p in fetch.load_posted()}
    lines = ["# Weekly Instagram report", "",
             f"Generated {datetime.now(NPT):%Y-%m-%d} (Nepal time)", "",
             "| Date | Type | Category | Reach | Views | Likes | Comments | Saves | Shares | Headline |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    by_cat = {}
    for r in rows:
        p = posted.get(r["id"], {})
        cat = p.get("category", "?")
        reach = r.get("reach") or 0
        by_cat.setdefault(cat, []).append(reach)
        lines.append(f"| {r['timestamp'][:10]} | {r['media_type']} | {cat} | {reach} | {r.get('views', '')} | "
                     f"{r.get('like_count', '')} | {r.get('comments_count', '')} | {r.get('saved', '')} | "
                     f"{r.get('shares', '')} | {p.get('headline_en', (r.get('caption') or '')[:50])} |")
    lines += ["", "## Average reach by category", ""]
    for cat, v in sorted(by_cat.items(), key=lambda kv: -sum(kv[1]) / len(kv[1])):
        lines.append(f"- {cat}: {sum(v) // len(v)} ({len(v)} posts)")
    out = config.STATE / "report.md"
    out.write_text("\n".join(lines) + "\n")
    print(out.read_text())


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dry-run"
    reel = "--reel" in sys.argv
    if cmd == "prepare":
        prepare(reel)
    elif cmd == "dry-run":
        prepare(reel, save=False)
    elif cmd == "digest":
        digest(save="--dry" not in sys.argv)
    elif cmd == "publish":
        publish()
    elif cmd == "cleanup":
        cleanup()
    elif cmd == "report":
        report()
    else:
        print(__doc__)
