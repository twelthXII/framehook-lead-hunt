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
