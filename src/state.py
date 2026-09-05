import hashlib
import json
import os
from datetime import date, datetime, timedelta

STATE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state", "state.json")

# Two independent axes, never conflated:
#
# OPPORTUNITY STATUS ("status" / "fit_tier") - fit and timing only. Whether a
# decision maker has been found yet does not change how good the opportunity
# is — a company with a real trigger and no contact yet is still a timely
# opportunity, just one with an open next action.
#   READY_NOW  - fit >= FIT_ATTRACTIVE and a real trigger (timing HIGH)
#   GOOD_FIT   - fit >= FIT_ATTRACTIVE but no live trigger
#   WATCH      - fit >= FIT_WATCH but not yet commercially compelling
#   REJECTED   - fit below FIT_WATCH
#   SEEN       - never reached Claude (failed the deterministic prefilter)
#   CONTACTED / REPLIED / WON / LOST - pipeline outcomes set only via user
#                                       feedback; a later discovery run's
#                                       re-classification never overwrites them
#
# CONTACT STATUS ("contact_status") - reachability only, tracked separately
# once an account clears the PAIN GATE into GOOD_FIT/READY_NOW. A verified
# NON-EMAIL contact is required for CONTACT_FOUND — email alone is
# CONTACT_EMAIL_ONLY (weaker; does not make a CONFIRMED_LEAD). See
# CONTACT_STATUSES below.
#
# PAIN GATE: a commercially attractive account (fit >= FIT_ATTRACTIVE) only
# becomes GOOD_FIT/READY_NOW if a concrete, evidence-backed Framehook-solvable
# problem was confirmed (pain_confirmed=True) — never inferred from money,
# subscriber count, growth, launch timing, or reachability alone. Failing the
# gate sends a would-be GOOD_FIT/READY_NOW account straight to REJECTED
# (reason NO_CLEAR_PAIN), not down to WATCH — WATCH is for genuinely
# lower fit (45-64), not a landing pad for "attractive but unproven".
FIT_ATTRACTIVE = 65
FIT_WATCH = 45

CONTACT_FOUND = "CONTACT_FOUND"
CONTACT_NEEDED = "CONTACT_NEEDED"
CONTACT_EMAIL_ONLY = "CONTACT_EMAIL_ONLY"
CONTACT_UNREACHABLE = "UNREACHABLE"
CONTACT_STATUSES = {CONTACT_FOUND, CONTACT_NEEDED, CONTACT_EMAIL_ONLY, CONTACT_UNREACHABLE}

# A proposed service that needs a visual audit before pain can be confirmed —
# matched as a case-insensitive substring of the free-text service Claude
# proposes (e.g. "thumbnail system", "YouTube packaging").
VISUAL_AUDIT_REQUIRED_SUBSTRINGS = ("thumbnail", "packaging")

# These never get a re-classification overwrite from a fresh Pass-1 verdict —
# once the user has recorded real pipeline movement, a routine run shouldn't
# silently reset it back to a fit-tier label.
PIPELINE_LOCKED_STATUSES = {"CONTACTED", "REPLIED", "WON", "LOST"}

# These only resurface on a genuine signal change (fingerprint change), never
# merely because a recheck date passed — matches "not worth spending future
# Claude analysis on unless meaningful external signals change".
LOW_PRIORITY_STATUSES = {"REJECTED", "SEEN", "LOST", "DO_NOT_CONTACT"}

RECHECK_DAYS_DEFAULT = {
    "READY_NOW": 7, "GOOD_FIT": 14, "WATCH": 25, "REJECTED": 75, "SEEN": 75,
    "CONTACTED": 21, "REPLIED": 30, "WON": 90, "LOST": 60, "DEFAULT": 14,
}

STATE_RETENTION_DAYS_DEFAULT = 180

FEEDBACK_LABELS = {
    "GOOD": {"status": None, "lane_delta": {"approved": 1}},
    "TOO_BIG": {"status": "REJECTED", "lane_delta": {"rejected": 1}},
    "NO_MONEY": {"status": "REJECTED", "lane_delta": {"rejected": 1}},
    "BAD_FIT": {"status": "REJECTED", "lane_delta": {"rejected": 1}},
    "WRONG_MARKET": {"status": "REJECTED", "lane_delta": {"rejected": 1}},
    "ALREADY_TOO_STRONG": {"status": "REJECTED", "lane_delta": {"rejected": 1}},
    "NO_CONTACT": {"status": "REJECTED", "lane_delta": {"rejected": 1}},
    "CONTACTED": {"status": "CONTACTED", "lane_delta": {"contacted": 1}},
    "REPLIED": {"status": "REPLIED", "lane_delta": {"replied": 1}},
    "CALL": {"status": "REPLIED", "lane_delta": {"replied": 1}},
    "WON": {"status": "WON", "lane_delta": {"won": 1}},
    "LOST": {"status": "LOST", "lane_delta": {}},
}


def default_state():
    return {
        "version": 1,
        "accounts": {},
        "query_stats": {},
        "lane_query_index": {},
        "rotation_index": 0,
        "runs": [],
        "feedback": {},
        "last_output": [],
    }


def load_state(path=STATE_PATH):
    if not os.path.exists(path):
        return default_state()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    base = default_state()
    base.update(data)
    return base


def save_state(state, path=STATE_PATH):
    """Atomic write: a crash mid-write leaves the previous state.json intact
    rather than a truncated/corrupt file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp{os.getpid()}"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp_path, path)


def compute_fingerprint(signals):
    material = {
        "sub_bucket": signals.get("sub_bucket"),
        "uploads_30d": signals.get("uploads_30d"),
        "days_since_upload_bucket": min(signals.get("days_since_upload", 9999) // 7, 20),
        "latest_video_id": signals.get("latest_video_id"),
        "commercial_signal_count": len(signals.get("commercial_signals_raw", [])),
    }
    blob = json.dumps(material, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def is_due_for_review(account, today, recheck_days=None):
    recheck_days = recheck_days or RECHECK_DAYS_DEFAULT
    next_review = account.get("next_review_after")
    if not next_review:
        return True
    return today >= date.fromisoformat(next_review)


def should_send_to_claude(account, fingerprint, today, recheck_days=None):
    if account is None:
        return True, "new_account"
    if account.get("fingerprint") != fingerprint:
        return True, "fingerprint_changed"
    if account.get("status") in LOW_PRIORITY_STATUSES:
        return False, "rejected_no_new_signal"
    if is_due_for_review(account, today, recheck_days):
        return True, "due_for_recheck"
    return False, "unchanged_and_not_due"


def requires_visual_audit(proposed_service):
    if not proposed_service:
        return False
    text = proposed_service.lower()
    return any(s in text for s in VISUAL_AUDIT_REQUIRED_SUBSTRINGS)


def gate_pain_confirmed(pain_confirmed, proposed_service=None, visual_audit_done=False):
    """Backstop for the PAIN GATE's visual-audit requirement: a
    thumbnail/packaging diagnosis can never count as confirmed pain without
    an actual visual audit, no matter what was claimed. This is enforced in
    code, not left to discipline alone."""
    if requires_visual_audit(proposed_service) and not visual_audit_done:
        return False
    return bool(pain_confirmed)


def classify(fit, timing, pain_confirmed=False):
    """Opportunity status: fit, timing, AND the PAIN GATE. A commercially
    attractive account (fit >= FIT_ATTRACTIVE) only reaches GOOD_FIT/READY_NOW
    if pain_confirmed is True — a concrete, evidence-backed Framehook-solvable
    problem, never inferred from money/size/growth/launch/contact alone. If
    pain isn't confirmed, a would-be GOOD_FIT/READY_NOW account is REJECTED
    outright, not downgraded to WATCH.

    Reachability is a wholly separate axis (see normalize_contact_status) and
    never affects this — a confirmed pain + a real trigger is still READY_NOW
    with no contact found yet, just one whose next action is contact
    research rather than outreach."""
    if fit >= FIT_ATTRACTIVE:
        if not pain_confirmed:
            return "REJECTED"
        return "READY_NOW" if timing == "HIGH" else "GOOD_FIT"
    if fit >= FIT_WATCH:
        return "WATCH"
    return "REJECTED"


def normalize_contact_status(fit_tier, contact_status):
    """Contact status is only meaningful once an account has cleared the
    PAIN GATE into GOOD_FIT/READY_NOW — WATCH/REJECTED accounts don't get
    contact research spent on them. Defaults to CONTACT_NEEDED (research not
    yet done, or not a recognized value) rather than assuming UNREACHABLE."""
    if fit_tier not in ("READY_NOW", "GOOD_FIT"):
        return None
    if contact_status in CONTACT_STATUSES:
        return contact_status
    return CONTACT_NEEDED


def is_confirmed_lead(fit_tier, contact_status):
    """CONFIRMED_LEAD requires: cleared the PAIN GATE into GOOD_FIT/READY_NOW,
    AND at least one verified non-email contact. Email-only or no contact at
    all never confirms a lead — a contact can never rescue a bad opportunity,
    and a good opportunity isn't confirmed until it's reachable."""
    return fit_tier in ("READY_NOW", "GOOD_FIT") and contact_status == CONTACT_FOUND


def default_rejection_reasons(pain_confirmed, rejection_reasons=None):
    if rejection_reasons:
        return list(rejection_reasons)
    if not pain_confirmed:
        return ["NO_CLEAR_PAIN"]
    return []


def next_review_date(status, today, recheck_days=None):
    recheck_days = recheck_days or RECHECK_DAYS_DEFAULT
    days = recheck_days.get(status, recheck_days["DEFAULT"])
    return (today + timedelta(days=days)).isoformat()


JUDGED_FIT_TIERS = {"READY_NOW", "GOOD_FIT", "WATCH"}


def upsert_account(state, channel_id, fingerprint, name, lane_id, today,
                    fit=None, timing=None, pain_confirmed=False,
                    proposed_service=None, visual_audit_done=False,
                    contact_status=None, rejection_reasons=None):
    accounts = state["accounts"]
    existing = accounts.get(channel_id, {})

    if fit is not None:
        effective_pain = gate_pain_confirmed(pain_confirmed, proposed_service, visual_audit_done)
        fit_tier = classify(fit, timing, effective_pain)
        contact_status = normalize_contact_status(fit_tier, contact_status)
        reasons = default_rejection_reasons(effective_pain, rejection_reasons) if fit_tier == "REJECTED" else []
    else:
        effective_pain = existing.get("pain_confirmed", False)
        fit_tier = existing.get("fit_tier", "WATCH")
        contact_status = existing.get("contact_status")
        reasons = existing.get("rejection_reasons", [])

    locked = existing.get("status") in PIPELINE_LOCKED_STATUSES
    status = existing["status"] if locked else fit_tier
    confirmed_lead = is_confirmed_lead(fit_tier, contact_status)

    history = existing.get("history", [])[-4:]
    history.append({"date": today.isoformat(), "fit": fit, "timing": timing, "fit_tier": fit_tier})
    record = {
        "name": name,
        "lane": lane_id,
        "fingerprint": fingerprint,
        "status": status,
        "fit_tier": fit_tier,
        "pain_confirmed": effective_pain,
        "rejection_reasons": reasons,
        "contact_status": contact_status,
        "confirmed_lead": confirmed_lead,
        "last_fit": fit,
        "last_timing": timing,
        "last_reviewed": today.isoformat(),
        "history": history,
    }
    # next_review_after only matters for statuses should_send_to_claude
    # actually consults on a schedule (LOW_PRIORITY_STATUSES resurface only
    # via fingerprint change, so the date is dead weight for them).
    if status not in LOW_PRIORITY_STATUSES:
        record["next_review_after"] = next_review_date(status, today)
    accounts[channel_id] = record
    return record


def record_seen_only(state, channel_id, fingerprint, today):
    """Track a candidate seen this run that failed the deterministic
    prefilter before ever reaching Claude. This is a bounded dedupe
    tombstone, not a full account record — just enough to skip
    re-processing an unchanged channel next time: fingerprint, last-seen
    date, and the SEEN marker (channel_id is already the dict key). Never
    downgrades a real pipeline outcome or an already-judged fit tier
    (READY_NOW/GOOD_FIT/WATCH) that a previous Claude pass assigned — those
    keep their full record; only their freshness fields move."""
    accounts = state["accounts"]
    existing = accounts.get(channel_id, {})
    existing_status = existing.get("status")

    if existing_status in PIPELINE_LOCKED_STATUSES or existing_status in JUDGED_FIT_TIERS:
        accounts[channel_id] = {**existing, "fingerprint": fingerprint, "last_reviewed": today.isoformat()}
        return

    accounts[channel_id] = {
        "fingerprint": fingerprint,
        "last_reviewed": today.isoformat(),
        "status": "SEEN",
    }


def prune_stale_accounts(state, today, retention_days=STATE_RETENTION_DAYS_DEFAULT):
    """Evict low-priority accounts (SEEN/REJECTED/LOST/DO_NOT_CONTACT) that
    haven't been touched in a long time, so state.json stays bounded. Real
    leads (READY_NOW/GOOD_FIT/WATCH/CONTACTED/REPLIED/WON) are never pruned.
    Re-discovering a pruned account later just creates a fresh record — no
    correctness is lost, only some rediscovery history."""
    accounts = state["accounts"]
    cutoff = today - timedelta(days=retention_days)
    stale_ids = []
    for channel_id, account in accounts.items():
        if account.get("status") not in LOW_PRIORITY_STATUSES:
            continue
        last_reviewed = account.get("last_reviewed")
        if last_reviewed and date.fromisoformat(last_reviewed) < cutoff:
            stale_ids.append(channel_id)
    for channel_id in stale_ids:
        del accounts[channel_id]
    return len(stale_ids)


def lane_score(lane_id, query_stats):
    stats = query_stats.get(lane_id, {})
    shown = stats.get("shown", 0)
    weight = stats.get("weight", 1.0)
    if shown == 0:
        return weight
    performance = (
        stats.get("approved", 0) * 1
        + stats.get("contacted", 0) * 2
        + stats.get("replied", 0) * 3
        + stats.get("won", 0) * 5
        - stats.get("rejected", 0) * 0.5
    ) / shown
    return weight * (1 + performance)


def allocate_query_budget(lanes, state, total_budget, exploration_share=0.2):
    query_stats = state.setdefault("query_stats", {})
    lane_ids = [lane["id"] for lane in lanes]
    scored = sorted(lane_ids, key=lambda lid: lane_score(lid, query_stats), reverse=True)

    exploit_budget = max(0, round(total_budget * (1 - exploration_share)))
    explore_budget = total_budget - exploit_budget

    allocation = {lid: 0 for lid in lane_ids}
    i = 0
    while exploit_budget > 0 and lane_ids:
        allocation[scored[i % len(scored)]] += 1
        i += 1
        exploit_budget -= 1

    rotation_start = state.get("rotation_index", 0)
    least_run = sorted(lane_ids, key=lambda lid: query_stats.get(lid, {}).get("runs", 0))
    j = 0
    while explore_budget > 0 and lane_ids:
        lane_id = least_run[(rotation_start + j) % len(least_run)]
        allocation[lane_id] += 1
        j += 1
        explore_budget -= 1
    state["rotation_index"] = (rotation_start + max(j, 1)) % max(len(lane_ids), 1)

    for lid in lane_ids:
        if allocation[lid]:
            stats = query_stats.setdefault(lid, {})
            stats["runs"] = stats.get("runs", 0) + 1

    return {lid: n for lid, n in allocation.items() if n > 0}


def next_query_variation(state, lane):
    index_map = state.setdefault("lane_query_index", {})
    idx = index_map.get(lane["id"], 0)
    queries = lane["queries"]
    query = queries[idx % len(queries)]
    index_map[lane["id"]] = idx + 1
    return query


def record_shown(state, lane_id, count=1):
    stats = state.setdefault("query_stats", {}).setdefault(lane_id, {})
    stats["shown"] = stats.get("shown", 0) + count


def record_run(state, run_summary):
    runs = state.setdefault("runs", [])
    runs.append(run_summary)
    state["runs"] = runs[-12:]


def set_last_output(state, finalists):
    state["last_output"] = [
        {"num": i + 1, "channel_id": f["id"], "name": f["name"]}
        for i, f in enumerate(finalists)
    ]


def parse_feedback_text(text):
    tokens = text.replace(",", " ").split()
    result = {}
    current_num = None
    current_words = []

    def flush():
        if current_num is not None and current_words:
            result[current_num] = "_".join(current_words).upper()

    for tok in tokens:
        clean = tok.strip("#:")
        if clean.isdigit():
            flush()
            current_num = int(clean)
            current_words = []
        else:
            current_words.append(clean.lower())
    flush()
    return result


def apply_feedback(state, labels_by_num, run_date=None):
    run_date = run_date or date.today().isoformat()
    mapping = {row["num"]: row for row in state.get("last_output", [])}
    applied = []
    for num, label in labels_by_num.items():
        label = label.upper()
        if label not in FEEDBACK_LABELS:
            continue
        row = mapping.get(int(num))
        if not row:
            continue
        channel_id = row["channel_id"]
        account = state["accounts"].get(channel_id)
        rule = FEEDBACK_LABELS[label]
        if account and rule["status"]:
            account["status"] = rule["status"]
        lane_id = account["lane"] if account else None
        if lane_id:
            stats = state.setdefault("query_stats", {}).setdefault(lane_id, {})
            for key, delta in rule["lane_delta"].items():
                stats[key] = stats.get(key, 0) + delta
        state.setdefault("feedback", {})[channel_id] = {"label": label, "date": run_date}
        applied.append({"num": num, "channel_id": channel_id, "label": label})
    return applied
