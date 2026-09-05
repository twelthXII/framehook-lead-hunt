import json
from datetime import date, timedelta

import state as state_mod


def make_signals(**overrides):
    base = {
        "sub_bucket": "20k-100k",
        "uploads_30d": 4,
        "days_since_upload": 3,
        "latest_video_id": "vid1",
        "commercial_signals_raw": [("sponsor", 2)],
    }
    base.update(overrides)
    return base


def test_fingerprint_stable_for_same_signals():
    a = state_mod.compute_fingerprint(make_signals())
    b = state_mod.compute_fingerprint(make_signals())
    assert a == b


def test_fingerprint_changes_when_activity_changes():
    a = state_mod.compute_fingerprint(make_signals())
    b = state_mod.compute_fingerprint(make_signals(uploads_30d=10))
    assert a != b


def test_should_send_new_account_always_true():
    due, reason = state_mod.should_send_to_claude(None, "fp1", date.today())
    assert due is True
    assert reason == "new_account"


def test_should_send_false_when_unchanged_and_not_due():
    today = date.today()
    account = {
        "fingerprint": "fp1",
        "next_review_after": (today + timedelta(days=5)).isoformat(),
    }
    due, reason = state_mod.should_send_to_claude(account, "fp1", today)
    assert due is False
    assert reason == "unchanged_and_not_due"


def test_should_send_true_when_fingerprint_changed_even_if_not_due():
    today = date.today()
    account = {
        "fingerprint": "fp1",
        "next_review_after": (today + timedelta(days=30)).isoformat(),
    }
    due, reason = state_mod.should_send_to_claude(account, "fp2", today)
    assert due is True
    assert reason == "fingerprint_changed"


def test_should_send_true_when_due_date_passed():
    today = date.today()
    account = {
        "fingerprint": "fp1",
        "next_review_after": (today - timedelta(days=1)).isoformat(),
    }
    due, reason = state_mod.should_send_to_claude(account, "fp1", today)
    assert due is True
    assert reason == "due_for_recheck"


def test_classify_strong_survives_low_timing():
    assert state_mod.classify(fit=91, timing="LOW") == "STRONG"


def test_classify_hot_requires_high_timing_and_min_fit():
    assert state_mod.classify(fit=86, timing="HIGH") == "HOT"
    assert state_mod.classify(fit=40, timing="HIGH") == "REJECTED"


def test_classify_watchlist_and_rejected_bands():
    assert state_mod.classify(fit=70, timing="LOW") == "WATCHLIST"
    assert state_mod.classify(fit=30, timing="LOW") == "REJECTED"


def test_allocate_query_budget_uses_full_budget_and_never_zeroes_a_lane():
    lanes = [{"id": f"LANE_{i}", "base_weight": 1.0} for i in range(5)]
    state = state_mod.default_state()
    total_allocated = 0
    seen_lanes = set()
    for _ in range(10):
        allocation = state_mod.allocate_query_budget(lanes, state, total_budget=6, exploration_share=0.2)
        total_allocated += sum(allocation.values())
        seen_lanes.update(allocation.keys())
    assert total_allocated == 60
    assert seen_lanes == {lane["id"] for lane in lanes}


def test_allocate_query_budget_favors_high_performing_lane():
    lanes = [{"id": "GOOD", "base_weight": 1.0}, {"id": "BAD", "base_weight": 1.0}]
    state = state_mod.default_state()
    state["query_stats"] = {
        "GOOD": {"shown": 10, "approved": 8, "contacted": 5, "replied": 3, "won": 1, "runs": 3},
        "BAD": {"shown": 10, "approved": 0, "rejected": 9, "runs": 3},
    }
    allocation = state_mod.allocate_query_budget(lanes, state, total_budget=4, exploration_share=0.0)
    assert allocation.get("GOOD", 0) >= allocation.get("BAD", 0)


def test_next_query_variation_cycles_deterministically():
    state = state_mod.default_state()
    lane = {"id": "LANE_A", "queries": ["q1", "q2"]}
    seq = [state_mod.next_query_variation(state, lane) for _ in range(4)]
    assert seq == ["q1", "q2", "q1", "q2"]


def test_parse_feedback_text_basic():
    parsed = state_mod.parse_feedback_text("1 good 2 too big 5 bad fit 7 replied")
    assert parsed == {1: "GOOD", 2: "TOO_BIG", 5: "BAD_FIT", 7: "REPLIED"}


def test_parse_feedback_text_with_commas_and_hash():
    parsed = state_mod.parse_feedback_text("#1 good, #3 no money")
    assert parsed == {1: "GOOD", 3: "NO_MONEY"}


def test_apply_feedback_updates_status_and_lane_stats():
    state = state_mod.default_state()
    state["accounts"]["chan1"] = {"name": "Chan One", "lane": "LANE_A", "status": "WATCHLIST"}
    state["last_output"] = [{"num": 1, "channel_id": "chan1", "name": "Chan One"}]

    applied = state_mod.apply_feedback(state, {1: "CONTACTED"})

    assert applied == [{"num": 1, "channel_id": "chan1", "label": "CONTACTED"}]
    assert state["accounts"]["chan1"]["status"] == "CONTACTED"
    assert state["query_stats"]["LANE_A"]["contacted"] == 1


def test_state_save_load_round_trip(tmp_path):
    path = str(tmp_path / "state.json")
    state = state_mod.default_state()
    state["accounts"]["chan1"] = {"name": "X", "status": "HOT"}
    state_mod.save_state(state, path=path)

    loaded = state_mod.load_state(path=path)
    assert loaded["accounts"]["chan1"]["status"] == "HOT"

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    assert raw["accounts"]["chan1"]["name"] == "X"


def test_load_state_missing_file_returns_default(tmp_path):
    path = str(tmp_path / "missing.json")
    state = state_mod.load_state(path=path)
    assert state == state_mod.default_state()
