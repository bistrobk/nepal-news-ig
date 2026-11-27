"""Decide what this run should do, from the Nepal clock and the post log.

GitHub runs scheduled jobs late (often hours) and drops some, so the cron line
that fired says nothing reliable about the time. The workflow wakes every 20
minutes and this script picks: skip, card, reel or digest.

python -m bot.when    prints the action, and writes action=... to $GITHUB_OUTPUT

Standard library only: it runs before the pip install step.
"""
import json
import os
from datetime import datetime, timedelta

from . import config

FIRST_HOUR = 6          # first post at 06:00 Nepal time
LAST_HOUR = 21          # last post in the 21:00 hour; nothing from 22:00
REEL_HOURS = {8, 18, 21}
DIGEST_FROM = (20, 30)  # 'Today in Nepal' from 20:30 until LAST_HOUR ends
MIN_GAP_MIN = 35        # never two posts closer than this (late runs bunch up)


def decide(now=None, posted=None):
    now = now or datetime.now(config.NPT)
    if posted is None:
        posted = json.loads(config.POSTED_FILE.read_text()) if config.POSTED_FILE.exists() else []
    if not FIRST_HOUR <= now.hour <= LAST_HOUR:
        return "skip", f"{now:%H:%M} is outside posting hours"
    times = [(datetime.fromisoformat(p["time"]).astimezone(config.NPT), p.get("type")) for p in posted]
    if times:
        last = max(t for t, _ in times)
        if now - last < timedelta(minutes=MIN_GAP_MIN):
            return "skip", f"last post was at {last:%H:%M}"
    today = [(t, kind) for t, kind in times if t.date() == now.date()]
    if (now.hour, now.minute) >= DIGEST_FROM and not any(k == "digest" for _, k in today):
        if sum(k != "digest" for _, k in today) >= 3:
            return "digest", "evening summary not posted yet"
    if any(t.hour == now.hour and k != "digest" for t, k in today):
        return "skip", f"already posted in the {now.hour}:00 hour"
    return ("reel" if now.hour in REEL_HOURS else "card"), f"{now:%H:%M} slot is free"


if __name__ == "__main__":
    action, why = decide()
    print(f"{action}: {why}")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"action={action}\n")
