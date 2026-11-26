"""Settings. Secrets come from environment variables (GitHub secrets in CI)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"
MEDIA = ROOT / "media"
FONTS = ROOT / "fonts"
POSTED_FILE = STATE / "posted.json"
PENDING_FILE = STATE / "pending.json"

# `or` so an empty GitHub variable falls back to the default
HANDLE = os.environ.get("IG_HANDLE") or "@sparsha_np"
BRAND = os.environ.get("IG_BRAND") or "SPARSHA"  # short name in the card's top-right corner
THEME = os.environ.get("IG_THEME") or "topic"  # card colours: topic, mix (alternate), navy or light
NAVY_TOPICS = {"Politics", "Economy", "World", "Business", "Weather"}  # the rest go on light
MODEL = os.environ.get("CLAUDE_MODEL") or "claude-opus-5-5"  # cheaper: claude-haiku-5-5

IG_TOKEN = os.environ.get("IG_ACCESS_TOKEN", "")
IG_USER_ID = os.environ.get("IG_USER_ID", "")
# Facebook Login for Business (system-user token, does not expire) -> graph.facebook.com
IG_API = "https://graph.facebook.com/v23.0"

# Public URL base for media files (raw GitHub, repo must be public)
REPO = os.environ.get("GITHUB_REPOSITORY", "")
BRANCH = os.environ.get("GITHUB_REF_NAME", "main")
MEDIA_BASE = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/media"

FEEDS = {
    "Onlinekhabar English": "https://english.onlinekhabar.com/feed",
    "Onlinekhabar": "https://www.onlinekhabar.com/feed",
    "Setopati": "https://www.setopati.com/feed",
    "Ratopati": "https://www.ratopati.com/feed",
    "Nepali Times": "https://nepalitimes.com/feed",
    "The Rising Nepal": "https://risingnepaldaily.com/rss",
    "Nepal News": "https://nepalnews.com/feed",
}

MAX_AGE_HOURS = 18      # ignore stories older than this
CANDIDATES = 40         # how many fresh stories Claude chooses from
KEEP_MEDIA_DAYS = 5     # delete old images/videos from the repo
