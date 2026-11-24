"""Ask Claude to pick the best new story and write a bilingual post for it."""
import json

import anthropic

from . import config

SYSTEM = """You run a neutral Nepali news Instagram account for people in Nepal and the Nepali diaspora.
Each post is one story in two languages: Nepali (Devanagari) and English.

Pick ONE story from the candidates:
- Prefer stories that matter most to many Nepalis: national politics, economy, prices, remittance, jobs abroad,
  foreign employment rules, visas, weather and disasters warnings, health, education, sport, big achievements.
- Do NOT pick a story that repeats a recently posted one (same event), even from another outlet.
- Skip graphic violence, suicide details, sexual crimes, content about minors as victims, unverified rumours,
  and anything one-sided or defamatory about a private person. If every candidate is like that, set ok=false.

Writing rules:
- Write in your own words. Never copy sentences from the source. Facts only, no opinion, no clickbait.
- Do not add facts that are not in the candidate text. Keep names, numbers and dates exactly as given.
- headline_ne / headline_en: max 9 words each.
- points_ne / points_en: 2 or 3 short bullet facts each, max 14 words per bullet.
- caption: hook line, English summary (2-3 sentences), Nepali summary (2-3 sentences),
  one question to invite comments, then "Source: <outlet>". No hashtags in caption.
- hashtags: 4 tags, no '#', mix of broad (NepalNews) and topic tags.
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "ok": {"type": "boolean"},
        "index": {"type": "integer"},
        "category": {"type": "string", "enum": [
            "Politics", "Economy", "World", "Diaspora", "Weather", "Sport", "Health",
            "Education", "Tech", "Society", "Culture", "Business"]},
        "headline_ne": {"type": "string"},
        "headline_en": {"type": "string"},
        "points_ne": {"type": "array", "items": {"type": "string"}},
        "points_en": {"type": "array", "items": {"type": "string"}},
        "caption": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["ok", "index", "category", "headline_ne", "headline_en",
                 "points_ne", "points_en", "caption", "hashtags"],
    "additionalProperties": False,
}


def write_post(stories, posted):
    recent = [p["headline_en"] for p in posted[-30:]]
    cands = "\n\n".join(
        f"[{i}] {s['source']} ({s['age_h']} h ago)\nTitle: {s['title']}\nText: {s['summary']}"
        for i, s in enumerate(stories)
    )
    prompt = (f"Recently posted (do not repeat):\n- " + "\n- ".join(recent or ["(none)"])
              + f"\n\nCandidates:\n\n{cands}")

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=config.MODEL,
        max_tokens=4000,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        output_config={"effort": "low",
                       "format": {"type": "json_schema", "schema": SCHEMA}},
    )
    if resp.stop_reason == "refusal":
        print("Claude declined this batch")
        return None
    text = next(b.text for b in resp.content if b.type == "text")
    post = json.loads(text)
    if not post["ok"] or not 0 <= post["index"] < len(stories):
        print("No suitable story this run")
        return None
    post["story"] = stories[post["index"]]
    post["hashtags"] = [h.lstrip("#").replace(" ", "") for h in post["hashtags"]][:5]
    return post
