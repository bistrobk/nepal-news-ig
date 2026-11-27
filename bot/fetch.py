"""Read RSS feeds and return fresh stories we have not posted yet."""
import calendar
import html
import json
import re
import time

import feedparser
import requests

from . import config


def load_posted():
    if config.POSTED_FILE.exists():
        return json.loads(config.POSTED_FILE.read_text())
    return []


def clean(text, limit=600):
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()[:limit]


def fresh_stories():
    posted = load_posted()
    seen = {p["link"] for p in posted}
    now = time.time()
    stories = []
    for source, url in config.FEEDS.items():
        try:
            feed = feedparser.parse(url, agent="Mozilla/5.0 (news-bot)")
        except Exception as e:  # one bad feed must not stop the run
            print(f"feed error {source}: {e}")
            continue
        for e in feed.entries[:25]:
            link = e.get("link", "")
            if not link or link in seen:
                continue
            ts = e.get("published_parsed") or e.get("updated_parsed")
            age_h = (now - calendar.timegm(ts)) / 3600 if ts else 0
            if age_h > config.MAX_AGE_HOURS:
                continue
            stories.append({
                "source": source,
                "link": link,
                "title": clean(e.get("title", ""), 200),
                "summary": clean(e.get("summary", "") or e.get("description", "")),
                "age_h": round(age_h, 1),
            })
    stories.sort(key=lambda s: s["age_h"])
    print(f"{len(stories)} fresh stories")
    return stories[: config.CANDIDATES], posted


OG = re.compile(r"<meta[^>]+(?:property|name)=[\"'](?:og:image|twitter:image)(?::src)?[\"'][^>]*>", re.I)


def og_image(link, dest):
    """Save the article's share photo (og:image) to dest. Returns dest or None."""
    try:
        ua = {"User-Agent": "Mozilla/5.0 (news-bot)"}
        page = requests.get(link, timeout=15, headers=ua).text[:300000]
        for tag in OG.findall(page):
            m = re.search(r"content=[\"']([^\"']+)", tag)
            if not m:
                continue
            url = html.unescape(m.group(1).strip())
            if url.startswith("//"):
                url = "https:" + url
            r = requests.get(url, timeout=20, headers=ua)
            if r.ok and len(r.content) > 15000 and r.headers.get("content-type", "image").startswith("image"):
                dest.write_bytes(r.content)
                from PIL import Image
                with Image.open(dest) as im:
                    if min(im.size) >= 300:
                        return dest
    except Exception as e:  # a missing photo must never stop a post
        print(f"No photo: {e}")
    return None
