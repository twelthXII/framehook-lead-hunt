from datetime import datetime, timedelta, timezone

import scoring_support as scoring

SUBSCRIBER_RANGES = {
    "commercial_creator": {"min": 20000, "max": 500000, "stretch_max": 1000000},
    "cis_editing": {"min": 5000, "max": 500000, "stretch_max": 1000000},
}

LANE = {
    "id": "GLOBAL_PACKAGING_BUSINESS",
    "icp": "commercial_creator",
    "geography": "global",
    "language": "en",
    "eligible_offers": ["thumbnails", "youtube_packaging"],
}


def test_parse_duration_seconds():
    assert scoring.parse_duration_seconds("PT10M30S") == 630
    assert scoring.parse_duration_seconds("PT1H") == 3600
    assert scoring.parse_duration_seconds("PT45S") == 45
    assert scoring.parse_duration_seconds("") == 0


def test_is_longform_threshold():
    assert scoring.is_longform(200, threshold=180) is True
    assert scoring.is_longform(60, threshold=180) is False


def test_bucket_subscribers():
    assert scoring.bucket_subscribers(1000) == "<5k"
    assert scoring.bucket_subscribers(50000) == "20k-100k"
    assert scoring.bucket_subscribers(2_000_000) == "1M+"


def _channel_item(subs=80000, description="", country="US"):
    return {
        "id": "chan1",
        "snippet": {"title": "Test Channel", "description": description, "country": country, "customUrl": "@test"},
        "statistics": {"subscriberCount": str(subs)},
    }


def _recent_video(days_ago, duration=600, views=10000, title="Episode", description=""):
    published = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")
    return {
        "video_id": f"vid{days_ago}",
        "title": title,
        "description": description,
        "published_at": published,
        "duration_seconds": duration,
        "view_count": views,
    }


def test_extract_channel_signals_counts_activity_and_commercial_hits():
    videos = [
        _recent_video(2, description="use code FRAME10 for discount"),
        _recent_video(10, description="check out our new course"),
        _recent_video(40),
        _recent_video(100),
    ]
    signals = scoring.extract_channel_signals(_channel_item(), videos)
    assert signals["uploads_30d"] == 2
    assert signals["uploads_90d"] == 3
    assert signals["days_since_upload"] == 2
    assert signals["subs"] == 80000
    assert len(signals["commercial_signals_raw"]) >= 2


def test_prefilter_rejects_below_subscriber_floor():
    signals = scoring.extract_channel_signals(_channel_item(subs=500), [_recent_video(1), _recent_video(2), _recent_video(3)])
    keep, reason, _score = scoring.prefilter(signals, LANE, SUBSCRIBER_RANGES)
    assert keep is False
    assert reason == "below_subscriber_floor"


def test_prefilter_rejects_inactive_channel():
    videos = [_recent_video(65), _recent_video(70)]
    signals = scoring.extract_channel_signals(_channel_item(), videos)
    keep, reason, _score = scoring.prefilter(signals, LANE, SUBSCRIBER_RANGES)
    assert keep is False
    assert reason == "inactive_channel"


def test_prefilter_rejects_blocklisted_category_without_commercial_signals():
    signals = scoring.extract_channel_signals(
        _channel_item(description="Official television network archive footage"),
        [_recent_video(1), _recent_video(2), _recent_video(3)],
    )
    keep, reason, _score = scoring.prefilter(signals, LANE, SUBSCRIBER_RANGES)
    assert keep is False
    assert reason == "blocklisted_category"


def test_prefilter_accepts_healthy_commercial_channel():
    videos = [
        _recent_video(1, description="sponsored by our partner, use code SAVE"),
        _recent_video(5, description="join our community and course"),
        _recent_video(20),
        _recent_video(40),
    ]
    signals = scoring.extract_channel_signals(_channel_item(subs=80000), videos)
    keep, reason, score = scoring.prefilter(signals, LANE, SUBSCRIBER_RANGES)
    assert keep is True
    assert reason == "ok"
    assert score > 0


def test_prefilter_shorts_dominated_rejected():
    videos = [_recent_video(1, duration=30), _recent_video(2, duration=45),
              _recent_video(3, duration=20), _recent_video(4, duration=50)]
    signals = scoring.extract_channel_signals(_channel_item(subs=80000), videos)
    keep, reason, _score = scoring.prefilter(signals, LANE, SUBSCRIBER_RANGES)
    assert keep is False
    assert reason == "shorts_dominated"


def test_build_evidence_pack_shape_and_size():
    videos = [_recent_video(1, description="use code SAVE"), _recent_video(5), _recent_video(10)]
    signals = scoring.extract_channel_signals(_channel_item(), videos)
    pack = scoring.build_evidence_pack(signals, LANE)

    expected_keys = {
        "id", "name", "lane", "language", "market", "subs", "median_views_10",
        "uploads_30d", "uploads_90d", "days_since_upload", "recent_titles",
        "commercial_signals", "eligible_offers", "url",
    }
    assert set(pack.keys()) == expected_keys
    assert len(pack["recent_titles"]) <= 5
    assert isinstance(pack["commercial_signals"], list)
    assert len(pack["commercial_signals"]) <= 5
    assert pack["eligible_offers"] == LANE["eligible_offers"]


def test_select_shortlist_respects_max_total_and_per_lane_cap():
    lane_a = {"id": "A"}
    lane_b = {"id": "B"}
    candidates = (
        [{"lane": lane_a, "score": 10 - i, "pack": {"id": f"a{i}"}} for i in range(10)]
        + [{"lane": lane_b, "score": 5 - i * 0.1, "pack": {"id": f"b{i}"}} for i in range(3)]
    )
    shortlist = scoring.select_shortlist(candidates, max_total=8, max_per_lane=4)
    assert len(shortlist) <= 8
    from_a = [c for c in shortlist if c["lane"] is lane_a]
    assert len(from_a) <= 4


def test_select_shortlist_does_not_force_weak_lane_to_fill_quota():
    lane_a = {"id": "A"}
    lane_b = {"id": "B"}
    candidates = (
        [{"lane": lane_a, "score": 100 - i, "pack": {"id": f"a{i}"}} for i in range(20)]
        + [{"lane": lane_b, "score": 0.01, "pack": {"id": "b0"}}]
    )
    shortlist = scoring.select_shortlist(candidates, max_total=5, max_per_lane=10)
    assert len(shortlist) == 5
    assert all(c["lane"] is lane_a for c in shortlist)
