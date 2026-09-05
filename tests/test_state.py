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


def test_classify_good_fit_requires_pain_confirmed():
    assert state_mod.classify(fit=91, timing="LOW", pain_confirmed=True) == "GOOD_FIT"


def test_classify_ready_now_requires_high_timing_min_fit_and_pain():
    assert state_mod.classify(fit=86, timing="HIGH", pain_confirmed=True) == "READY_NOW"
    assert state_mod.classify(fit=50, timing="HIGH", pain_confirmed=True) == "WATCH"
    assert state_mod.classify(fit=40, timing="HIGH", pain_confirmed=True) == "REJECTED"


def test_classify_never_ready_now_on_fit_alone():
    # A high fit score without a real trigger is GOOD_FIT, never READY_NOW —
    # "could use better thumbnails" is not a buying trigger.
    assert state_mod.classify(fit=99, timing="LOW", pain_confirmed=True) != "READY_NOW"
    assert state_mod.classify(fit=99, timing="MEDIUM", pain_confirmed=True) != "READY_NOW"


def test_classify_ready_now_unaffected_by_missing_contact():
    # A missing contact must never demote READY_NOW -> GOOD_FIT. Reachability
    # is tracked entirely separately via contact_status.
    assert state_mod.classify(fit=95, timing="HIGH", pain_confirmed=True) == "READY_NOW"


def test_classify_watch_and_rejected_bands():
    assert state_mod.classify(fit=50, timing="LOW") == "WATCH"
    assert state_mod.classify(fit=30, timing="LOW") == "REJECTED"


# --- PAIN GATE: calibration regression tests (A, B, H, I from the spec) ---

def test_pain_gate_a_money_monetization_contact_no_pain_rejected():
    # High money + monetization + reachable contact + no confirmed pain.
    assert state_mod.classify(fit=90, timing="MEDIUM", pain_confirmed=False) == "REJECTED"


def test_pain_gate_b_major_launch_high_timing_no_pain_rejected():
    # A launch/trigger with HIGH timing but no evidence-backed pain: REJECTED,
    # not READY_NOW. This is the Aniimo case exactly.
    assert state_mod.classify(fit=82, timing="HIGH", pain_confirmed=False) == "REJECTED"


def test_pain_gate_h_coherent_system_no_problem_fails_gate():
    # Professional, coherent system with no concrete problem: pain_confirmed
    # should never be True here, so classify rejects regardless of fit.
    assert state_mod.classify(fit=82, timing="LOW", pain_confirmed=False) == "REJECTED"


def test_pain_gate_i_inferred_pain_is_not_confirmed_pain():
    # A trigger exists, but if pain was only inferred (not independently
    # confirmed), pain_confirmed must be False and the gate fails.
    assert state_mod.classify(fit=88, timing="HIGH", pain_confirmed=False) == "REJECTED"


def test_pain_gate_j_visual_audit_required_for_packaging_pain():
    # A thumbnail/packaging diagnosis cannot count as confirmed pain without
    # an actual visual audit, even if pain_confirmed=True was claimed.
    assert state_mod.gate_pain_confirmed(True, "thumbnail system", visual_audit_done=False) is False
    assert state_mod.gate_pain_confirmed(True, "YouTube packaging", visual_audit_done=False) is False
    assert state_mod.gate_pain_confirmed(True, "thumbnail system", visual_audit_done=True) is True
    # A non-visual service (e.g. editing) isn't gated by the visual audit.
    assert state_mod.gate_pain_confirmed(True, "editing", visual_audit_done=False) is True


def test_normalize_contact_status_only_applies_after_pain_gate():
    assert state_mod.normalize_contact_status("GOOD_FIT", "CONTACT_FOUND") == "CONTACT_FOUND"
    assert state_mod.normalize_contact_status("READY_NOW", "UNREACHABLE") == "UNREACHABLE"
    assert state_mod.normalize_contact_status("WATCH", "CONTACT_FOUND") is None
    assert state_mod.normalize_contact_status("REJECTED", "CONTACT_FOUND") is None


def test_normalize_contact_status_defaults_to_needed():
    # Not yet researched, or an invalid/unrecognized value — default to
    # CONTACT_NEEDED, never assume UNREACHABLE.
    assert state_mod.normalize_contact_status("GOOD_FIT", None) == "CONTACT_NEEDED"
    assert state_mod.normalize_contact_status("GOOD_FIT", "garbage") == "CONTACT_NEEDED"


# --- CONFIRMED_LEAD: calibration regression tests (C, D, E, F, G from the spec) ---

def test_confirmed_lead_c_ready_now_no_contact_not_confirmed():
    assert state_mod.is_confirmed_lead("READY_NOW", "CONTACT_NEEDED") is False


def test_confirmed_lead_d_ready_now_social_contact_confirmed():
    assert state_mod.is_confirmed_lead("READY_NOW", "CONTACT_FOUND") is True


def test_confirmed_lead_e_good_fit_social_contact_confirmed():
    assert state_mod.is_confirmed_lead("GOOD_FIT", "CONTACT_FOUND") is True


def test_confirmed_lead_f_email_only_not_confirmed():
    assert state_mod.is_confirmed_lead("GOOD_FIT", "CONTACT_EMAIL_ONLY") is False


def test_confirmed_lead_g_youtube_handle_only_is_contact_needed_not_confirmed():
    # A YouTube handle alone never counts as a qualifying contact — it should
    # be reported as CONTACT_NEEDED (not a recognized contact value), and
    # never confirms the lead.
    status = state_mod.normalize_contact_status("GOOD_FIT", None)
    assert status == "CONTACT_NEEDED"
    assert state_mod.is_confirmed_lead("GOOD_FIT", status) is False


def test_confirmed_lead_contact_alone_cannot_rescue_a_rejected_opportunity():
    assert state_mod.is_confirmed_lead("REJECTED", "CONTACT_FOUND") is False


def test_should_send_rejected_account_ignores_due_date_needs_fingerprint_change():
    today = date.today()
    account = {
        "fingerprint": "fp1",
        "status": "REJECTED",
        "next_review_after": (today - timedelta(days=5)).isoformat(),
    }
    due, reason = state_mod.should_send_to_claude(account, "fp1", today)
    assert due is False
    assert reason == "rejected_no_new_signal"

    due, reason = state_mod.should_send_to_claude(account, "fp2", today)
    assert due is True
    assert reason == "fingerprint_changed"


def test_upsert_account_does_not_overwrite_locked_pipeline_status():
    state = state_mod.default_state()
    today = date.today()
    state_mod.upsert_account(state, "chan1", "fp1", "Chan One", "LANE_A", today, fit=80, timing="LOW", pain_confirmed=True)
    state["accounts"]["chan1"]["status"] = "CONTACTED"

    state_mod.upsert_account(
        state, "chan1", "fp2", "Chan One", "LANE_A", today, fit=90, timing="HIGH",
        pain_confirmed=True, contact_status="CONTACT_FOUND",
    )

    assert state["accounts"]["chan1"]["status"] == "CONTACTED"
    assert state["accounts"]["chan1"]["fit_tier"] == "READY_NOW"


def test_upsert_account_ready_now_with_contact_needed_stays_ready_now():
    # The Aniimo-shape case, corrected: fit >= 65, timing HIGH, pain CONFIRMED,
    # no contact found yet — this is READY_NOW, with contact_status flagging
    # the open next action.
    state = state_mod.default_state()
    today = date.today()
    state_mod.upsert_account(state, "chan1", "fp1", "Chan One", "LANE_A", today, fit=82, timing="HIGH", pain_confirmed=True)
    assert state["accounts"]["chan1"]["fit_tier"] == "READY_NOW"
    assert state["accounts"]["chan1"]["status"] == "READY_NOW"
    assert state["accounts"]["chan1"]["contact_status"] == "CONTACT_NEEDED"
    assert state["accounts"]["chan1"]["confirmed_lead"] is False


def test_upsert_account_rejects_without_pain_regardless_of_fit_and_timing():
    # The corrected Aniimo case: high fit, HIGH timing, no confirmed pain.
    state = state_mod.default_state()
    today = date.today()
    state_mod.upsert_account(state, "chan1", "fp1", "Chan One", "LANE_A", today, fit=82, timing="HIGH", pain_confirmed=False)
    acc = state["accounts"]["chan1"]
    assert acc["fit_tier"] == "REJECTED"
    assert acc["status"] == "REJECTED"
    assert acc["rejection_reasons"] == ["NO_CLEAR_PAIN"]
    assert acc["contact_status"] is None


def test_upsert_account_records_custom_rejection_reasons():
    # The corrected Pavel/Aniimo calibration: multiple rejection reasons.
    state = state_mod.default_state()
    today = date.today()
    state_mod.upsert_account(
        state, "chan1", "fp1", "Chan One", "LANE_A", today, fit=82, timing="HIGH",
        pain_confirmed=False, rejection_reasons=["NO_CLEAR_PAIN", "ALREADY_WELL_RESOURCED"],
    )
    assert state["accounts"]["chan1"]["rejection_reasons"] == ["NO_CLEAR_PAIN", "ALREADY_WELL_RESOURCED"]


def test_upsert_account_records_confirmed_lead_true_with_social_contact():
    state = state_mod.default_state()
    today = date.today()
    state_mod.upsert_account(
        state, "chan1", "fp1", "Chan One", "LANE_A", today, fit=70, timing="LOW",
        pain_confirmed=True, contact_status="CONTACT_FOUND",
    )
    assert state["accounts"]["chan1"]["confirmed_lead"] is True


def test_upsert_account_visual_audit_gate_blocks_packaging_pain():
    # Claiming pain_confirmed=True for a packaging service without a visual
    # audit must not reach GOOD_FIT/READY_NOW.
    state = state_mod.default_state()
    today = date.today()
    state_mod.upsert_account(
        state, "chan1", "fp1", "Chan One", "LANE_A", today, fit=80, timing="LOW",
        pain_confirmed=True, proposed_service="thumbnail system", visual_audit_done=False,
    )
    assert state["accounts"]["chan1"]["fit_tier"] == "REJECTED"
    assert state["accounts"]["chan1"]["rejection_reasons"] == ["NO_CLEAR_PAIN"]


def test_upsert_account_omits_next_review_for_low_priority_status():
    state = state_mod.default_state()
    today = date.today()
    state_mod.upsert_account(state, "chan1", "fp1", "Chan One", "LANE_A", today, fit=20, timing="LOW")
    assert state["accounts"]["chan1"]["status"] == "REJECTED"
    assert "next_review_after" not in state["accounts"]["chan1"]


def test_record_seen_only_does_not_downgrade_locked_status():
    state = state_mod.default_state()
    today = date.today()
    state["accounts"]["chan1"] = {"name": "Chan One", "lane": "LANE_A", "status": "WON"}
    state_mod.record_seen_only(state, "chan1", "fp1", today)
    assert state["accounts"]["chan1"]["status"] == "WON"


def test_record_seen_only_does_not_downgrade_a_judged_fit_tier():
    state = state_mod.default_state()
    today = date.today()
    state["accounts"]["chan1"] = {
        "name": "Chan One", "lane": "LANE_A", "status": "GOOD_FIT",
        "fit_tier": "GOOD_FIT", "last_fit": 80, "history": [{"date": "2026-01-01", "fit": 80}],
    }
    state_mod.record_seen_only(state, "chan1", "fp2", today)
    assert state["accounts"]["chan1"]["status"] == "GOOD_FIT"
    assert state["accounts"]["chan1"]["last_fit"] == 80
    assert state["accounts"]["chan1"]["fingerprint"] == "fp2"


def test_record_seen_only_is_a_minimal_tombstone_for_a_true_reject():
    state = state_mod.default_state()
    today = date.today()
    state_mod.record_seen_only(state, "chan1", "fp1", today)
    assert state["accounts"]["chan1"] == {
        "fingerprint": "fp1",
        "last_reviewed": today.isoformat(),
        "status": "SEEN",
    }


def test_prune_stale_accounts_removes_only_old_low_priority_entries():
    state = state_mod.default_state()
    today = date.today()
    old = (today - timedelta(days=200)).isoformat()
    recent = (today - timedelta(days=5)).isoformat()
    state["accounts"] = {
        "stale_rejected": {"status": "REJECTED", "last_reviewed": old},
        "fresh_rejected": {"status": "REJECTED", "last_reviewed": recent},
        "stale_but_good_fit": {"status": "GOOD_FIT", "last_reviewed": old},
        "stale_seen": {"status": "SEEN", "last_reviewed": old},
    }
    pruned = state_mod.prune_stale_accounts(state, today, retention_days=180)
    assert pruned == 2
    assert set(state["accounts"].keys()) == {"fresh_rejected", "stale_but_good_fit"}


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
    state["accounts"]["chan1"] = {"name": "Chan One", "lane": "LANE_A", "status": "GOOD_FIT"}
    state["last_output"] = [{"num": 1, "channel_id": "chan1", "name": "Chan One"}]

    applied = state_mod.apply_feedback(state, {1: "CONTACTED"})

    assert applied == [{"num": 1, "channel_id": "chan1", "label": "CONTACTED"}]
    assert state["accounts"]["chan1"]["status"] == "CONTACTED"
    assert state["query_stats"]["LANE_A"]["contacted"] == 1


def test_state_save_load_round_trip(tmp_path):
    path = str(tmp_path / "state.json")
    state = state_mod.default_state()
    state["accounts"]["chan1"] = {"name": "X", "status": "READY_NOW"}
    state_mod.save_state(state, path=path)

    loaded = state_mod.load_state(path=path)
    assert loaded["accounts"]["chan1"]["status"] == "READY_NOW"

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    assert raw["accounts"]["chan1"]["name"] == "X"


def test_load_state_missing_file_returns_default(tmp_path):
    path = str(tmp_path / "missing.json")
    state = state_mod.load_state(path=path)
    assert state == state_mod.default_state()
