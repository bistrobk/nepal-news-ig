"""Instagram API (Instagram Login): publish images and Reels, refresh token, read insights."""
import os
import time

import requests

from . import config


def _params(**kw):
    return {"access_token": config.IG_TOKEN, **kw}


def _check(r):
    if r.status_code >= 400:
        raise RuntimeError(f"IG API {r.status_code}: {r.text[:500]}")
    return r.json()


def _wait(container_id, tries=40, delay=6):
    for _ in range(tries):
        j = _check(requests.get(f"{config.IG_API}/{container_id}",
                                params=_params(fields="status_code,status"), timeout=30))
        code = j.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"container {container_id} failed: {j}")
        time.sleep(delay)
    raise TimeoutError(f"container {container_id} not ready")


def _publish(container_id):
    j = _check(requests.post(f"{config.IG_API}/{config.IG_USER_ID}/media_publish",
                             data=_params(creation_id=container_id), timeout=60))
    return j["id"]


def post_image(image_url, caption):
    j = _check(requests.post(f"{config.IG_API}/{config.IG_USER_ID}/media",
                             data=_params(image_url=image_url, caption=caption), timeout=60))
    _wait(j["id"], tries=20, delay=3)
    return _publish(j["id"])


def post_reel(video_path, caption, video_url=None):
    """Resumable upload of the local file; falls back to a public video_url."""
    try:
        j = _check(requests.post(f"{config.IG_API}/{config.IG_USER_ID}/media",
                                 data=_params(media_type="REELS", upload_type="resumable",
                                              caption=caption, share_to_feed="true"), timeout=60))
        size = os.path.getsize(video_path)
        with open(video_path, "rb") as f:
            _check(requests.post(j["uri"], data=f, timeout=300, headers={
                "Authorization": f"OAuth {config.IG_TOKEN}",
                "offset": "0", "file_size": str(size)}))
        cid = j["id"]
    except Exception as e:
        if not video_url:
            raise
        print(f"resumable upload failed ({e}); trying video_url")
        j = _check(requests.post(f"{config.IG_API}/{config.IG_USER_ID}/media",
                                 data=_params(media_type="REELS", video_url=video_url,
                                              caption=caption, share_to_feed="true"), timeout=60))
        cid = j["id"]
    _wait(cid)
    return _publish(cid)


def refresh_token():
    """Long-lived tokens last 60 days; refreshing gives a fresh 60 days."""
    j = _check(requests.get("https://graph.instagram.com/refresh_access_token",
                            params={"grant_type": "ig_refresh_token",
                                    "access_token": config.IG_TOKEN}, timeout=30))
    return j["access_token"], j.get("expires_in")


def recent_insights(limit=70):
    """Per-post numbers for the last ~week of posts. Metrics that fail are skipped."""
    j = _check(requests.get(f"{config.IG_API}/{config.IG_USER_ID}/media", params=_params(
        fields="id,caption,media_type,timestamp,permalink,like_count,comments_count",
        limit=limit), timeout=30))
    rows = []
    for m in j.get("data", []):
        stats = {}
        r = requests.get(f"{config.IG_API}/{m['id']}/insights",
                         params=_params(metric="reach,views,saved,shares,total_interactions"),
                         timeout=30)
        if r.ok:
            for d in r.json().get("data", []):
                stats[d["name"]] = (d.get("values") or [{}])[0].get("value", d.get("total_value", {}).get("value"))
        rows.append({**m, **stats})
    return rows
