import hashlib
import json
import os
from datetime import date, datetime, timedelta

STATE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state", "state.json")

RECHECK_DAYS_DEFAULT = {
    "HOT": 10, "STRONG": 10, "WATCHLIST": 25, "REJECTED": 75,
    "CONTACTED": 21, "REPLIED": 30, "DEFAULT": 14,
}

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
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
        f.write("\n")


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
    if is_due_for_review(account, today, recheck_days):
        return True, "due_for_recheck"
    return False, "unchanged_and_not_due"


def classify(fit, timing):
    if fit >= 85:
        base = "STRONG"
    elif fit >= 65:
        base = "WATCHLIST"
    else:
        base = "REJECTED"
    if timing == "HIGH" and fit >= 65:
        return "HOT"
    return base


def next_review_date(status, today, recheck_days=None):
    recheck_days = recheck_days or RECHECK_DAYS_DEFAULT
    days = recheck_days.get(status, recheck_days["DEFAULT"])
    return (today + timedelta(days=days)).isoformat()


def upsert_account(state, channel_id, fingerprint, name, lane_id, today, fit=None, timing=None):
    accounts = state["accounts"]
    existing = accounts.get(channel_id, {})
    status = classify(fit, timing) if fit is not None else existing.get("status", "WATCHLIST")
    history = existing.get("history", [])[-4:]
    history.append({"date": today.isoformat(), "fit": fit, "timing": timing, "status": status})
    accounts[channel_id] = {
        "name": name,
        "lane": lane_id,
        "fingerprint": fingerprint,
        "status": status,
        "last_fit": fit,
        "last_timing": timing,
        "last_reviewed": today.isoformat(),
        "next_review_after": next_review_date(status, today),
        "history": history,
    }
    return accounts[channel_id]


def record_seen_only(state, channel_id, fingerprint, name, lane_id, today):
    """Track a candidate seen this run without a Claude verdict yet (kept out of shortlist)."""
    accounts = state["accounts"]
    existing = accounts.get(channel_id, {})
    accounts[channel_id] = {
        **existing,
        "name": name,
        "lane": lane_id,
        "fingerprint": fingerprint,
        "status": existing.get("status", "SEEN"),
        "last_reviewed": existing.get("last_reviewed", today.isoformat()),
        "next_review_after": existing.get("next_review_after", next_review_date("DEFAULT", today)),
    }


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
