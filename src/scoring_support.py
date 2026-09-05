import re
from datetime import datetime, timezone

COMMERCIAL_KEYWORDS = [
    "sponsor", "sponsored", "partner", "use code", "discount code", "promo code",
    "course", "academy", "masterclass", "coaching", "consulting", "book a call",
    "community", "membership", "newsletter", "affiliate", "join my",
    "shop", "store", "merch", "patreon", "boosty",
]

BLOCKLIST_KEYWORDS = [
    "official movie", "television network", "broadcasting corporation",
    "record label", "music label", "vevo", "news network", "government of",
    "ministry of", "archive footage", "compilation channel", "tv channel",
]

DURATION_RE = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")


def parse_duration_seconds(iso_duration):
    match = DURATION_RE.match(iso_duration or "")
    if not match:
        return 0
    hours, minutes, seconds = (int(g) if g else 0 for g in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def is_longform(seconds, threshold=180):
    return seconds >= threshold


def bucket_subscribers(subs):
    if subs < 5_000:
        return "<5k"
    if subs < 20_000:
        return "5k-20k"
    if subs < 100_000:
        return "20k-100k"
    if subs < 500_000:
        return "100k-500k"
    if subs < 1_000_000:
        return "500k-1M"
    return "1M+"


def _days_since(iso_date, now):
    dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
    return (now - dt).days


def extract_channel_signals(channel_item, recent_videos, now=None):
    now = now or datetime.now(timezone.utc)
    snippet = channel_item.get("snippet", {})
    stats = channel_item.get("statistics", {})
    channel_id = channel_item["id"]
    description = snippet.get("description", "") or ""
    title = snippet.get("title", "") or ""
    subs = int(stats.get("subscriberCount", 0) or 0)

    longform_videos = [v for v in recent_videos if is_longform(v["duration_seconds"])]
    dated_videos = sorted(recent_videos, key=lambda v: v["published_at"], reverse=True)

    uploads_30d = sum(1 for v in recent_videos if _days_since(v["published_at"], now) <= 30)
    uploads_90d = sum(1 for v in recent_videos if _days_since(v["published_at"], now) <= 90)
    days_since_upload = _days_since(dated_videos[0]["published_at"], now) if dated_videos else 9999

    view_pool = longform_videos or recent_videos
    views_sorted = sorted(v["view_count"] for v in view_pool[:10])
    median_views_10 = views_sorted[len(views_sorted) // 2] if views_sorted else 0

    recent_titles = [v["title"] for v in dated_videos[:5]]
    text_blob = " ".join([description, title] + [v.get("description", "") for v in recent_videos]).lower()

    commercial_signals = []
    for kw in COMMERCIAL_KEYWORDS:
        hits = text_blob.count(kw)
        if hits:
            commercial_signals.append((kw, hits))

    latest_video_id = dated_videos[0]["video_id"] if dated_videos else None
    longform_ratio = (len(longform_videos) / len(recent_videos)) if recent_videos else 0.0

    return {
        "channel_id": channel_id,
        "name": title,
        "description": description,
        "country": snippet.get("country"),
        "custom_url": snippet.get("customUrl"),
        "subs": subs,
        "sub_bucket": bucket_subscribers(subs),
        "uploads_30d": uploads_30d,
        "uploads_90d": uploads_90d,
        "days_since_upload": days_since_upload,
        "median_views_10": median_views_10,
        "recent_titles": recent_titles,
        "commercial_signals_raw": commercial_signals,
        "longform_ratio": longform_ratio,
        "latest_video_id": latest_video_id,
        "video_count": len(recent_videos),
    }


def prefilter(signals, lane, subscriber_ranges,
              min_uploads_90d=2, max_days_since_upload=60, longform_min_ratio=0.15):
    icp = lane["icp"]
    ranges = subscriber_ranges[icp]
    subs = signals["subs"]
    commercial_count = len(signals["commercial_signals_raw"])
    text_blob = (signals["description"] + " " + signals["name"]).lower()

    if any(kw in text_blob for kw in BLOCKLIST_KEYWORDS) and commercial_count < 2:
        return False, "blocklisted_category", 0.0

    if subs < ranges["min"]:
        return False, "below_subscriber_floor", 0.0

    if subs > ranges["stretch_max"]:
        return False, "above_reachability_ceiling", 0.0

    if subs > ranges["max"] and commercial_count < 2:
        return False, "stretch_range_needs_commercial_signal", 0.0

    if signals["uploads_90d"] < min_uploads_90d:
        return False, "insufficient_recent_activity", 0.0

    if signals["days_since_upload"] > max_days_since_upload:
        return False, "inactive_channel", 0.0

    if signals["video_count"] >= 4 and signals["longform_ratio"] < longform_min_ratio:
        return False, "shorts_dominated", 0.0

    engagement = (signals["median_views_10"] / subs) if subs else 0.0
    score = commercial_count * 10 + min(signals["uploads_90d"], 20) + min(engagement * 50, 25)
    return True, "ok", round(score, 2)


def _commercial_signal_labels(commercial_signals_raw):
    labels = []
    for kw, hits in sorted(commercial_signals_raw, key=lambda x: -x[1])[:5]:
        noun = kw.replace(" code", "").replace(" ", "_")
        labels.append(f"{hits} {noun} hit{'s' if hits != 1 else ''}")
    return labels


def build_evidence_pack(signals, lane):
    return {
        "id": signals["channel_id"],
        "name": signals["name"],
        "lane": lane["id"],
        "language": lane["language"],
        "market": lane["geography"],
        "subs": signals["subs"],
        "median_views_10": signals["median_views_10"],
        "uploads_30d": signals["uploads_30d"],
        "uploads_90d": signals["uploads_90d"],
        "days_since_upload": signals["days_since_upload"],
        "recent_titles": signals["recent_titles"],
        "commercial_signals": _commercial_signal_labels(signals["commercial_signals_raw"]),
        "eligible_offers": lane["eligible_offers"],
        "url": f"https://www.youtube.com/channel/{signals['channel_id']}",
    }


def select_shortlist(scored_candidates, max_total=25, max_per_lane=6):
    by_lane = {}
    for cand in scored_candidates:
        by_lane.setdefault(cand["lane"]["id"], []).append(cand)
    for lane_id in by_lane:
        by_lane[lane_id].sort(key=lambda c: c["score"], reverse=True)

    capped = []
    for lane_id, cands in by_lane.items():
        capped.extend(cands[:max_per_lane])
    capped.sort(key=lambda c: c["score"], reverse=True)
    return capped[:max_total]
