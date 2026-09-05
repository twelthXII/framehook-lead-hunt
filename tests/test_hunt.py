import hunt


def _item(channel_id):
    return {"snippet": {"channelId": channel_id}}


def test_dedupe_channel_hits_keeps_first_lane_seen():
    video_items_by_lane = [
        ("LANE_A", [_item("chan1"), _item("chan2")]),
        ("LANE_B", [_item("chan2"), _item("chan3")]),
    ]
    result = hunt.dedupe_channel_hits(video_items_by_lane)
    assert result == {"chan1": "LANE_A", "chan2": "LANE_A", "chan3": "LANE_B"}


def test_dedupe_channel_hits_empty_input():
    assert hunt.dedupe_channel_hits([]) == {}


def test_dedupe_channel_hits_deduplicates_within_same_lane():
    video_items_by_lane = [("LANE_A", [_item("chan1"), _item("chan1"), _item("chan1")])]
    result = hunt.dedupe_channel_hits(video_items_by_lane)
    assert result == {"chan1": "LANE_A"}


class _FakeYouTubeClient:
    def __init__(self, playlist_items, videos):
        self._playlist_items = playlist_items
        self._videos = videos

    def get_playlist_items(self, playlist_id, max_results=15):
        return self._playlist_items

    def get_videos(self, video_ids):
        return self._videos


def _channel_item():
    return {
        "id": "chan1",
        "snippet": {"title": "Chan One", "description": "", "country": "US"},
        "statistics": {"subscriberCount": "50000"},
        "contentDetails": {"relatedPlaylists": {"uploads": "PLxyz"}},
    }


def test_fetch_channel_signals_tolerates_video_missing_duration_and_statistics():
    # A live/upcoming broadcast can omit contentDetails.duration and
    # statistics entirely — this used to raise KeyError and crash discovery.
    playlist_items = [{"contentDetails": {"videoId": "vid1"}}]
    videos = [{
        "id": "vid1",
        "snippet": {"title": "Live now", "publishedAt": "2026-01-01T00:00:00Z"},
        "contentDetails": {},
        "statistics": {},
    }]
    yt = _FakeYouTubeClient(playlist_items, videos)

    signals, recent_videos = hunt.fetch_channel_signals(yt, _channel_item())

    assert recent_videos[0]["duration_seconds"] == 0
    assert recent_videos[0]["view_count"] == 0
    assert signals["channel_id"] == "chan1"
