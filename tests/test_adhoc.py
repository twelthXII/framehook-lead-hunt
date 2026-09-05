import json
import os
from datetime import date, datetime, timedelta, timezone

import hunt
import state as state_mod


# --- A, B, C, D, E: pure config-building tests (no network) ---

def test_a_queries_become_temporary_search_constraint():
    # "Найди мне CS2 ютуберов" -> Claude supplies explicit queries; the
    # deterministic side just carries them through unchanged.
    assert hunt.parse_comma_list("CS2 highlights, CS2 tournament recap") == [
        "CS2 highlights", "CS2 tournament recap",
    ]
    lane = hunt.build_adhoc_lane(label="cs2", language="en")
    assert lane["id"] == "ADHOC:cs2"


def test_b_russian_language_constraint_respected():
    lane = hunt.build_adhoc_lane(label="cs2_ru", language="ru", geography="RU")
    assert lane["language"] == "ru"
    assert lane["geography"] == "RU"


def test_c_subscriber_range_override_respected():
    base_ranges = {"commercial_creator": {"min": 20000, "max": 500000, "stretch_max": 1000000}}
    ranges = hunt.build_adhoc_subscriber_ranges(base_ranges, "commercial_creator", subs_min=50000, subs_max=500000)
    assert ranges["commercial_creator"] == {"min": 50000, "max": 500000, "stretch_max": 500000}


# --- Calibration: explicit constraints only, nothing inferred across fields ---

def test_unspecified_language_defaults_to_none_not_english():
    # "Найди CS2 ютуберов" with no language mentioned must run a
    # language-neutral search, not silently default to English.
    lane = hunt.build_adhoc_lane(label="cs2")
    assert lane["language"] is None


def test_russian_geography_does_not_imply_editing_offer():
    # "Найди русских CS2 ютуберов": language/region stated, service NOT
    # stated. Must not auto-set offers to editing just because the audience
    # is Russian-speaking — the offer is decided after evidence + PAIN GATE.
    lane = hunt.build_adhoc_lane(label="cs2_ru", language="ru", geography="RU")
    assert lane["eligible_offers"] == ["thumbnails", "youtube_packaging"]
    assert "editing" not in lane["eligible_offers"]


def test_explicit_service_request_sets_offers_independent_of_language():
    # "Найди CS2 ютуберов, которым нужны превью": service stated, language
    # not. Offers reflects the stated service; language stays neutral.
    lane = hunt.build_adhoc_lane(label="cs2_thumbnails", offers=["thumbnails"])
    assert lane["language"] is None
    assert lane["eligible_offers"] == ["thumbnails"]


def test_explicit_russian_editing_request_sets_both_independently():
    # "Найди русских CS2 ютуберов для монтажа": both language AND service are
    # stated explicitly — both flow through, each from its own explicit
    # constraint, not from each other.
    lane = hunt.build_adhoc_lane(
        label="cs2_ru_editing", language="ru", geography="RU",
        icp="cis_editing", offers=["editing"],
    )
    assert lane["language"] == "ru"
    assert lane["geography"] == "RU"
    assert lane["eligible_offers"] == ["editing"]
    assert lane["icp"] == "cis_editing"


def test_adhoc_cli_defaults_leave_language_and_offers_unset(monkeypatch, tmp_path, capsys):
    # End-to-end through cmd_adhoc's own argument handling (not just the pure
    # helper): a request with no --language/--offers flags must not end up
    # with English or a forced service baked into the lane it builds.
    state_path = str(tmp_path / "state.json")
    pending_path = str(tmp_path / "pending.json")
    monkeypatch.setattr(state_mod, "STATE_PATH", state_path)
    monkeypatch.setattr(hunt, "PENDING_PATH", pending_path)

    class _EmptyClient:
        def search_videos(self, *a, **kw):
            return []

        def get_channels(self, channel_ids):
            return []

    monkeypatch.setattr(hunt, "YouTubeClient", lambda: _EmptyClient())

    args = argparse_namespace(
        queries="CS2 highlights", icp="commercial_creator", language=None, region=None,
        subs_min=None, subs_max=None, offers=None, window_days=14,
        max_results=25, label="cs2",
    )
    hunt.cmd_adhoc(args)
    output = json.loads(capsys.readouterr().out)
    assert output["lane"]["language"] is None
    assert output["lane"]["eligible_offers"] == ["thumbnails", "youtube_packaging"]


def test_d_adhoc_config_does_not_mutate_base_ranges_dict():
    base_ranges = {"commercial_creator": {"min": 20000, "max": 500000, "stretch_max": 1000000}}
    original = json.loads(json.dumps(base_ranges))
    hunt.build_adhoc_subscriber_ranges(base_ranges, "commercial_creator", subs_min=50000, subs_max=500000)
    assert base_ranges == original


def test_e_production_lanes_json_untouched_by_adhoc_config_building(tmp_path):
    lanes_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "lanes.json")
    with open(lanes_path, "r", encoding="utf-8") as f:
        before = f.read()

    hunt.build_adhoc_lane(label="cs2", language="ru", offers=["thumbnails"])
    hunt.build_adhoc_subscriber_ranges(
        {"commercial_creator": {"min": 20000, "max": 500000, "stretch_max": 1000000}},
        "commercial_creator", subs_min=50000, subs_max=500000,
    )

    with open(lanes_path, "r", encoding="utf-8") as f:
        after = f.read()
    assert before == after


# --- F, G, H, I: PAIN GATE and contact qualification (shared with weekly hunt) ---

def test_f_pain_gate_applies_to_adhoc_sourced_verdicts_too():
    # classify()/upsert_account are the same code path regardless of which
    # pipeline (discover or adhoc) found the candidate.
    assert state_mod.classify(fit=90, timing="HIGH", pain_confirmed=False) == "REJECTED"


def test_g_email_only_does_not_confirm_lead():
    assert state_mod.is_confirmed_lead("GOOD_FIT", "CONTACT_EMAIL_ONLY") is False


def test_h_linkedin_only_does_not_confirm_lead():
    assert state_mod.is_confirmed_lead("GOOD_FIT", "CONTACT_LINKEDIN_ONLY") is False
    assert state_mod.normalize_contact_status("GOOD_FIT", "CONTACT_LINKEDIN_ONLY") == "CONTACT_LINKEDIN_ONLY"


def test_i_instagram_x_telegram_confirm_lead():
    # The code tracks reachability generically as CONTACT_FOUND regardless of
    # which qualifying platform it came from — Instagram/X/Telegram/Discord
    # all normalize to the same confirming value.
    assert state_mod.is_confirmed_lead("GOOD_FIT", "CONTACT_FOUND") is True
    assert state_mod.is_confirmed_lead("READY_NOW", "CONTACT_FOUND") is True


# --- J: known unchanged REJECTED accounts are not re-analyzed (full pipeline) ---

class _FakeFullYouTubeClient:
    def __init__(self, search_map, channels, playlists, videos):
        self.search_map = search_map
        self.channels = channels
        self.playlists = playlists
        self.videos = videos

    def search_videos(self, query, published_after, max_results=25,
                       relevance_language=None, region_code=None, order="relevance"):
        return self.search_map.get(query, [])

    def get_channels(self, channel_ids):
        return [self.channels[cid] for cid in channel_ids if cid in self.channels]

    def get_playlist_items(self, playlist_id, max_results=15):
        return self.playlists.get(playlist_id, [])

    def get_videos(self, video_ids):
        return [self.videos[v] for v in video_ids if v in self.videos]


def _adhoc_fixture():
    channel_id = "chanA"
    playlist_id = "PL_chanA"
    video_ids = ["vidA1", "vidA2", "vidA3"]

    def video(vid, days_ago):
        published = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")
        return {
            "id": vid,
            "snippet": {"title": f"CS2 video {vid}", "description": "", "publishedAt": published},
            "contentDetails": {"duration": "PT600S"},
            "statistics": {"viewCount": "10000"},
        }

    search_map = {"CS2 highlights": [{"snippet": {"channelId": channel_id}}]}
    channels = {
        channel_id: {
            "id": channel_id,
            "snippet": {"title": "CS2 Channel", "description": "", "country": "RU"},
            "statistics": {"subscriberCount": "100000"},
            "contentDetails": {"relatedPlaylists": {"uploads": playlist_id}},
        }
    }
    playlists = {playlist_id: [{"contentDetails": {"videoId": vid}} for vid in video_ids]}
    videos = {vid: video(vid, days_ago=i + 1) for i, vid in enumerate(video_ids)}
    return channel_id, _FakeFullYouTubeClient(search_map, channels, playlists, videos)


def _adhoc_args():
    return argparse_namespace(
        queries="CS2 highlights", icp="commercial_creator", language="ru", region=None,
        subs_min=50000, subs_max=500000, offers="editing", window_days=14,
        max_results=25, label="cs2",
    )


class argparse_namespace:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def test_j_known_unchanged_rejected_account_is_not_reanalyzed(tmp_path, monkeypatch, capsys):
    state_path = str(tmp_path / "state.json")
    pending_path = str(tmp_path / "pending.json")
    monkeypatch.setattr(state_mod, "STATE_PATH", state_path)
    monkeypatch.setattr(hunt, "PENDING_PATH", pending_path)

    channel_id, fake_client = _adhoc_fixture()
    monkeypatch.setattr(hunt, "YouTubeClient", lambda: fake_client)

    # First run: fresh state, the channel should surface as a candidate.
    hunt.cmd_adhoc(_adhoc_args())
    first_output = json.loads(capsys.readouterr().out)
    assert first_output["stats"]["claude_packs"] == 1
    assert first_output["stats"]["skipped_unchanged_rejected"] == 0

    pending = json.loads(open(pending_path, "r", encoding="utf-8").read())
    fingerprint = pending[channel_id]["fingerprint"]

    # Mark it REJECTED with that exact fingerprint, as if a prior run judged it.
    state = state_mod.default_state()
    state["accounts"][channel_id] = {
        "status": "REJECTED", "fingerprint": fingerprint,
        "last_reviewed": date.today().isoformat(),
    }
    state_mod.save_state(state, path=state_path)

    # Second run with identical fixture data (same fingerprint): should skip it.
    hunt.cmd_adhoc(_adhoc_args())
    second_output = json.loads(capsys.readouterr().out)
    assert second_output["stats"]["claude_packs"] == 0
    assert second_output["stats"]["skipped_unchanged_rejected"] == 1


def test_adhoc_never_writes_query_stats_or_runs(tmp_path, monkeypatch, capsys):
    state_path = str(tmp_path / "state.json")
    pending_path = str(tmp_path / "pending.json")
    monkeypatch.setattr(state_mod, "STATE_PATH", state_path)
    monkeypatch.setattr(hunt, "PENDING_PATH", pending_path)

    _channel_id, fake_client = _adhoc_fixture()
    monkeypatch.setattr(hunt, "YouTubeClient", lambda: fake_client)

    hunt.cmd_adhoc(_adhoc_args())
    capsys.readouterr()

    # cmd_adhoc must never call save_state — no state.json should exist at
    # all after a run against a brand-new tmp_path.
    assert not os.path.exists(state_path)
