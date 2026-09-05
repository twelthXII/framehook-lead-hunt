#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone

import scoring_support as scoring
import state as state_mod
from youtube import YouTubeClient

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANES_PATH = os.path.join(ROOT, "config", "lanes.json")
PENDING_PATH = os.path.join(ROOT, ".runtime", "pending.json")
CONTACT_SHEET_DIR = os.path.join(ROOT, ".runtime", "contact_sheets")


def load_lanes_config():
    with open(LANES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_pending():
    if not os.path.exists(PENDING_PATH):
        return {}
    with open(PENDING_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_pending(pending):
    os.makedirs(os.path.dirname(PENDING_PATH), exist_ok=True)
    with open(PENDING_PATH, "w", encoding="utf-8") as f:
        json.dump(pending, f, indent=2)


def dedupe_channel_hits(video_items_by_lane):
    """video_items_by_lane: [(lane_id, [search_result_item, ...]), ...].
    Returns {channel_id: first_lane_id_that_found_it}."""
    channel_hits = {}
    for lane_id, items in video_items_by_lane:
        for item in items:
            channel_id = item["snippet"]["channelId"]
            channel_hits.setdefault(channel_id, lane_id)
    return channel_hits


def fetch_channel_signals(yt, channel_item, now=None):
    uploads_playlist = (
        channel_item.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
    )
    recent_videos = []
    if uploads_playlist:
        playlist_items = yt.get_playlist_items(uploads_playlist, max_results=15)
        video_ids = [
            pi["contentDetails"]["videoId"]
            for pi in playlist_items
            if "videoId" in pi.get("contentDetails", {})
        ]
        video_items = yt.get_videos(video_ids)
        for v in video_items:
            # Live/upcoming broadcasts and a few other edge cases omit
            # contentDetails.duration and/or statistics entirely.
            recent_videos.append({
                "video_id": v["id"],
                "title": v["snippet"]["title"],
                "description": v["snippet"].get("description", ""),
                "published_at": v["snippet"]["publishedAt"],
                "duration_seconds": scoring.parse_duration_seconds(v.get("contentDetails", {}).get("duration", "")),
                "view_count": int(v.get("statistics", {}).get("viewCount", 0) or 0),
                "thumbnail_url": (
                    v["snippet"].get("thumbnails", {}).get("high", {}).get("url")
                    or v["snippet"].get("thumbnails", {}).get("default", {}).get("url")
                ),
            })
    return scoring.extract_channel_signals(channel_item, recent_videos, now=now), recent_videos


def cmd_discover(args):
    lanes_config = load_lanes_config()
    state = state_mod.load_state()
    yt = YouTubeClient()
    today = date.today()
    now = datetime.now(timezone.utc)

    lanes_by_id = {lane["id"]: lane for lane in lanes_config["lanes"]}
    allocation = state_mod.allocate_query_budget(
        lanes_config["lanes"],
        state,
        total_budget=args.budget or lanes_config["weekly_query_budget"],
        exploration_share=lanes_config["exploration_share"],
    )

    published_after = (now - timedelta(days=args.window_days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    video_items_by_lane = []
    raw_video_count = 0
    queries_run = []
    for lane_id, n_queries in allocation.items():
        lane = lanes_by_id[lane_id]
        for _ in range(n_queries):
            query = state_mod.next_query_variation(state, lane)
            region = "RU" if lane["geography"] == "cis" else None
            items = yt.search_videos(
                query, published_after, max_results=25,
                relevance_language=lane["language"], region_code=region,
            )
            queries_run.append({"lane": lane_id, "query": query, "results": len(items)})
            raw_video_count += len(items)
            video_items_by_lane.append((lane_id, items))

    channel_hits = dedupe_channel_hits(video_items_by_lane)
    channel_ids = list(channel_hits.keys())
    channel_items = yt.get_channels(channel_ids)

    scored_candidates = []
    pending = {}
    for channel_item in channel_items:
        channel_id = channel_item["id"]
        lane = lanes_by_id[channel_hits[channel_id]]
        signals, _ = fetch_channel_signals(yt, channel_item, now=now)
        fingerprint = state_mod.compute_fingerprint(signals)

        keep, reason, score = scoring.prefilter(signals, lane, lanes_config["subscriber_ranges"])
        existing_account = state["accounts"].get(channel_id)

        if not keep:
            state_mod.record_seen_only(state, channel_id, fingerprint, today)
            continue

        due, due_reason = state_mod.should_send_to_claude(existing_account, fingerprint, today)
        if not due:
            continue

        pack = scoring.build_evidence_pack(signals, lane)
        scored_candidates.append({"lane": lane, "score": score, "pack": pack})
        pending[channel_id] = {"fingerprint": fingerprint, "name": signals["name"], "lane": lane["id"]}

    shortlist = scoring.select_shortlist(
        scored_candidates,
        max_total=lanes_config["claude_shortlist_max"],
        max_per_lane=lanes_config["max_per_lane_in_shortlist"],
    )
    shortlist_ids = {c["pack"]["id"] for c in shortlist}
    save_pending({cid: p for cid, p in pending.items() if cid in shortlist_ids})

    for lane_id in allocation:
        shown = sum(1 for c in shortlist if c["lane"]["id"] == lane_id)
        if shown:
            state_mod.record_shown(state, lane_id, count=shown)

    pruned = state_mod.prune_stale_accounts(
        state, today, retention_days=lanes_config.get("state_retention_days", state_mod.STATE_RETENTION_DAYS_DEFAULT)
    )

    run_summary = {
        "date": today.isoformat(),
        "raw_videos": raw_video_count,
        "raw_channels": len(channel_ids),
        "filtered_survivors": len(scored_candidates),
        "claude_packs": len(shortlist),
        "pruned_accounts": pruned,
    }
    state_mod.record_run(state, run_summary)
    state_mod.save_state(state)

    print(json.dumps({
        "stats": run_summary,
        "queries_run": queries_run if args.verbose else None,
        "candidates": [c["pack"] for c in shortlist],
    }, indent=2, default=str))


def parse_comma_list(text):
    if not text:
        return []
    return [item.strip() for item in text.split(",") if item.strip()]


def build_adhoc_lane(label=None, icp="commercial_creator", geography="global", language="en", offers=None):
    """Pure, in-memory lane shape for one AD_HOC_HUNT run. Never written to
    config/lanes.json — natural-language interpretation happens at the Skill
    layer; this just gives the deterministic pipeline a structured lane to
    run the same discovery/filter/evidence-pack code against."""
    return {
        "id": f"ADHOC:{label}" if label else "ADHOC",
        "icp": icp,
        "geography": geography,
        "language": language,
        "eligible_offers": offers or ["thumbnails", "youtube_packaging"],
    }


def build_adhoc_subscriber_ranges(base_ranges, icp, subs_min=None, subs_max=None):
    """Returns a NEW dict with a temporary override for one icp's subscriber
    range; never mutates base_ranges (production config stays untouched). An
    explicit subs_max is a hard ceiling the user asked for — it also caps
    stretch_max, rather than silently stretching past what was requested."""
    ranges = dict(base_ranges)
    if subs_min is not None or subs_max is not None:
        base = ranges.get(icp, {"min": 0, "max": 10**9, "stretch_max": 10**9})
        subs_max_val = subs_max if subs_max is not None else base["max"]
        stretch_max_val = subs_max if subs_max is not None else base.get("stretch_max", subs_max_val)
        ranges[icp] = {
            "min": subs_min if subs_min is not None else base["min"],
            "max": subs_max_val,
            "stretch_max": stretch_max_val,
        }
    return ranges


def cmd_adhoc(args):
    """A temporary, one-off targeted search (AD_HOC_HUNT) that reuses the
    exact same discovery/filter/evidence-pack/qualification pipeline as the
    weekly hunt, but never touches config/lanes.json or the weekly bookkeeping
    (query_stats, lane_query_index, rotation_index, runs) in state.json.
    state.json is read (for dedupe against known accounts) but never written
    here — only `record` (run afterwards, same as the weekly flow) writes to
    the shared `accounts` registry."""
    lanes_config = load_lanes_config()
    yt = YouTubeClient()
    today = date.today()
    now = datetime.now(timezone.utc)

    icp = args.icp or "commercial_creator"
    subscriber_ranges = build_adhoc_subscriber_ranges(
        lanes_config["subscriber_ranges"], icp, args.subs_min, args.subs_max,
    )
    lane = build_adhoc_lane(
        label=args.label, icp=icp,
        geography=args.region or "global", language=args.language or "en",
        offers=parse_comma_list(args.offers) or None,
    )
    queries = parse_comma_list(args.queries)
    if not queries:
        print(json.dumps({"error": "--queries is required, e.g. --queries \"CS2 highlights,CS2 tournament recap\""}))
        sys.exit(1)

    published_after = (now - timedelta(days=args.window_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    state = state_mod.load_state()  # read-only: used for dedupe, never saved back

    video_items_by_lane = []
    raw_video_count = 0
    for query in queries:
        items = yt.search_videos(
            query, published_after, max_results=args.max_results,
            relevance_language=lane["language"],
            region_code=None if lane["geography"] == "global" else lane["geography"],
        )
        raw_video_count += len(items)
        video_items_by_lane.append((lane["id"], items))

    channel_hits = dedupe_channel_hits(video_items_by_lane)
    channel_ids = list(channel_hits.keys())
    channel_items = yt.get_channels(channel_ids)

    scored_candidates = []
    pending_updates = {}
    skipped_unchanged_rejected = 0
    for channel_item in channel_items:
        channel_id = channel_item["id"]
        signals, _ = fetch_channel_signals(yt, channel_item, now=now)
        fingerprint = state_mod.compute_fingerprint(signals)

        keep, _reason, score = scoring.prefilter(signals, lane, subscriber_ranges)
        if not keep:
            continue

        existing_account = state["accounts"].get(channel_id)
        due, due_reason = state_mod.should_send_to_claude(existing_account, fingerprint, today)
        if not due:
            if due_reason == "rejected_no_new_signal":
                skipped_unchanged_rejected += 1
            continue

        pack = scoring.build_evidence_pack(signals, lane)
        scored_candidates.append({"lane": lane, "score": score, "pack": pack})
        pending_updates[channel_id] = {"fingerprint": fingerprint, "name": signals["name"], "lane": lane["id"]}

    shortlist = scoring.select_shortlist(
        scored_candidates,
        max_total=lanes_config["claude_shortlist_max"],
        max_per_lane=lanes_config["claude_shortlist_max"],
    )
    shortlist_ids = {c["pack"]["id"] for c in shortlist}

    pending = load_pending()
    pending.update({cid: meta for cid, meta in pending_updates.items() if cid in shortlist_ids})
    save_pending(pending)

    print(json.dumps({
        "mode": "adhoc",
        "lane": lane,
        "stats": {
            "raw_videos": raw_video_count,
            "raw_channels": len(channel_ids),
            "filtered_survivors": len(scored_candidates),
            "skipped_unchanged_rejected": skipped_unchanged_rejected,
            "claude_packs": len(shortlist),
        },
        "candidates": [c["pack"] for c in shortlist],
    }, indent=2, default=str))


def cmd_lookup(args):
    lanes_config = load_lanes_config()
    lanes_by_id = {lane["id"]: lane for lane in lanes_config["lanes"]}
    lane = lanes_by_id.get(args.lane)
    if not lane:
        print(json.dumps({"error": f"unknown lane {args.lane}"}))
        sys.exit(1)

    yt = YouTubeClient()
    if args.channel.startswith("@"):
        channel_item = yt.get_channel_by_handle(args.channel)
    else:
        items = yt.get_channels([args.channel])
        channel_item = items[0] if items else None

    if not channel_item:
        print(json.dumps({"error": "channel not found"}))
        sys.exit(1)

    signals, _ = fetch_channel_signals(yt, channel_item)
    fingerprint = state_mod.compute_fingerprint(signals)
    pack = scoring.build_evidence_pack(signals, lane)

    pending = load_pending()
    pending[channel_item["id"]] = {"fingerprint": fingerprint, "name": signals["name"], "lane": lane["id"]}
    save_pending(pending)

    print(json.dumps(pack, indent=2))


def cmd_contact_sheet(args):
    from PIL import Image
    import urllib.request

    lanes_config = load_lanes_config()
    yt = YouTubeClient()
    items = yt.get_channels([args.channel])
    if not items:
        print(json.dumps({"error": "channel not found"}))
        sys.exit(1)
    signals, recent_videos = fetch_channel_signals(yt, items[0])
    longform = [v for v in recent_videos if scoring.is_longform(
        v["duration_seconds"], lanes_config["longform_min_seconds"]
    ) and v.get("thumbnail_url")]
    longform.sort(key=lambda v: v["published_at"], reverse=True)
    chosen = longform[:args.count]

    if not chosen:
        print(json.dumps({"error": "no long-form thumbnails available"}))
        sys.exit(1)

    from youtube import _ssl_context

    thumbs = []
    ctx = _ssl_context()
    for v in chosen:
        req = urllib.request.Request(v["thumbnail_url"], headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            path = os.path.join(CONTACT_SHEET_DIR, f"_tmp_{v['video_id']}.jpg")
            os.makedirs(CONTACT_SHEET_DIR, exist_ok=True)
            with open(path, "wb") as f:
                f.write(resp.read())
            thumbs.append((path, v["title"]))

    cols = min(3, len(thumbs))
    rows = (len(thumbs) + cols - 1) // cols
    thumb_w, thumb_h = 480, 270
    sheet = Image.new("RGB", (cols * thumb_w, rows * thumb_h), "black")
    for i, (path, _title) in enumerate(thumbs):
        img = Image.open(path).convert("RGB").resize((thumb_w, thumb_h))
        x = (i % cols) * thumb_w
        y = (i // cols) * thumb_h
        sheet.paste(img, (x, y))
        os.remove(path)

    out_path = os.path.join(CONTACT_SHEET_DIR, f"{args.channel}.png")
    sheet.save(out_path)
    print(json.dumps({"path": out_path, "titles": [t for _, t in thumbs]}, indent=2))


def cmd_record(args):
    with open(args.input, "r", encoding="utf-8") as f:
        payload = json.load(f)

    state = state_mod.load_state()
    pending = load_pending()
    today = date.today()

    for verdict in payload.get("verdicts", []):
        channel_id = verdict["id"]
        meta = pending.get(channel_id)
        if not meta:
            continue
        state_mod.upsert_account(
            state, channel_id, meta["fingerprint"], meta["name"], meta["lane"], today,
            fit=verdict.get("fit"), timing=verdict.get("timing"),
            pain_confirmed=bool(verdict.get("pain_confirmed", False)),
            proposed_service=verdict.get("proposed_service"),
            visual_audit_done=bool(verdict.get("visual_audit_done", False)),
            contact_status=verdict.get("contact_status"),
            rejection_reasons=verdict.get("rejection_reasons"),
            contact_platform=verdict.get("contact_platform"),
            contact_value=verdict.get("contact_value"),
        )

    finalists = []
    for channel_id in payload.get("finalists_order", []):
        account = state["accounts"].get(channel_id)
        finalists.append({"id": channel_id, "name": account["name"] if account else channel_id})
    state_mod.set_last_output(state, finalists)

    state_mod.save_state(state)
    print(json.dumps({"accounts_updated": len(payload.get("verdicts", [])), "finalists": len(finalists)}))


def cmd_feedback(args):
    state = state_mod.load_state()
    labels = state_mod.parse_feedback_text(args.text)
    applied = state_mod.apply_feedback(state, labels)
    state_mod.save_state(state)
    print(json.dumps({"applied": applied}, indent=2))


def cmd_commit_state(args):
    diff = subprocess.run(
        ["git", "status", "--porcelain", "state/state.json"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if not diff.stdout.strip():
        print(json.dumps({"committed": False, "reason": "no changes"}))
        return

    fetch = subprocess.run(["git", "fetch", "origin", "main"], cwd=ROOT, capture_output=True, text=True)
    if fetch.returncode != 0:
        print(json.dumps({"committed": False, "error": "fetch_failed", "detail": fetch.stderr[:500]}))
        sys.exit(1)

    # Refuse if origin has moved since our clone's base — another run already
    # committed production state. Better to stop and report than to silently
    # overwrite or attempt a risky auto-merge of a JSON file.
    ancestor_check = subprocess.run(
        ["git", "merge-base", "--is-ancestor", "origin/main", "HEAD"], cwd=ROOT,
    )
    if ancestor_check.returncode != 0:
        print(json.dumps({
            "committed": False,
            "error": "state_conflict",
            "detail": (
                "origin/main has commits this run's clone doesn't have — another run "
                "already updated production state. Not overwriting it. Re-run discover "
                "against a fresh clone instead of retrying this commit."
            ),
        }))
        sys.exit(1)

    subprocess.run(["git", "add", "state/state.json"], cwd=ROOT, check=True)
    subprocess.run(
        ["git", "commit", "-m", f"state: update after weekly hunt {date.today().isoformat()}"],
        cwd=ROOT, check=True,
    )

    push = subprocess.run(["git", "push", "origin", "main"], cwd=ROOT, capture_output=True, text=True)
    if push.returncode != 0:
        print(json.dumps({"committed": False, "error": "push_rejected", "detail": push.stderr[:500]}))
        sys.exit(1)

    print(json.dumps({"committed": True}))


def cmd_stats(args):
    state = state_mod.load_state()
    accounts = state.get("accounts", {})
    by_status = {}
    for account in accounts.values():
        status = account.get("status", "UNKNOWN")
        by_status[status] = by_status.get(status, 0) + 1
    print(json.dumps({
        "runs": state.get("runs", [])[-5:],
        "query_stats": state.get("query_stats", {}),
        "account_count": len(accounts),
        "accounts_by_status": by_status,
        "state_file_bytes": os.path.getsize(state_mod.STATE_PATH) if os.path.exists(state_mod.STATE_PATH) else 0,
    }, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Framehook Lead Hunt")
    sub = parser.add_subparsers(dest="command", required=True)

    p_discover = sub.add_parser("discover", help="Run deterministic discovery and build the Claude shortlist")
    p_discover.add_argument("--budget", type=int, default=None)
    p_discover.add_argument("--window-days", type=int, default=14)
    p_discover.add_argument("--verbose", action="store_true")
    p_discover.set_defaults(func=cmd_discover)

    p_adhoc = sub.add_parser("adhoc", help="AD_HOC_HUNT: one temporary targeted search, never touches weekly config")
    p_adhoc.add_argument("--queries", required=True, help="Comma-separated search query strings")
    p_adhoc.add_argument("--icp", default="commercial_creator",
                          help="One of the icp keys in config/lanes.json subscriber_ranges")
    p_adhoc.add_argument("--language", default=None, help="YouTube relevanceLanguage, e.g. ru, en")
    p_adhoc.add_argument("--region", default=None, help="YouTube regionCode, e.g. RU")
    p_adhoc.add_argument("--subs-min", type=int, default=None)
    p_adhoc.add_argument("--subs-max", type=int, default=None)
    p_adhoc.add_argument("--offers", default=None, help="Comma-separated eligible_offers, e.g. thumbnails,editing")
    p_adhoc.add_argument("--window-days", type=int, default=14)
    p_adhoc.add_argument("--max-results", type=int, default=25)
    p_adhoc.add_argument("--label", default=None, help="Short label for this run, shown in the lane id")
    p_adhoc.set_defaults(func=cmd_adhoc)

    p_lookup = sub.add_parser("lookup", help="Build one evidence pack for a channel found via web research")
    p_lookup.add_argument("--channel", required=True, help="Channel ID or @handle")
    p_lookup.add_argument("--lane", required=True, help="Lane id to attach for offer/geography context")
    p_lookup.set_defaults(func=cmd_lookup)

    p_sheet = sub.add_parser("contact-sheet", help="Build a thumbnail contact sheet for one channel")
    p_sheet.add_argument("--channel", required=True)
    p_sheet.add_argument("--count", type=int, default=6)
    p_sheet.set_defaults(func=cmd_contact_sheet)

    p_record = sub.add_parser("record", help="Persist Claude's fit/timing verdicts and the final output order")
    p_record.add_argument("--input", required=True, help="Path to a JSON file: {verdicts:[...], finalists_order:[...]}")
    p_record.set_defaults(func=cmd_record)

    p_feedback = sub.add_parser("feedback", help="Apply user feedback like '1 good 2 too big 5 bad fit'")
    p_feedback.add_argument("text")
    p_feedback.set_defaults(func=cmd_feedback)

    p_commit = sub.add_parser("commit-state", help="Commit and push state/state.json if it changed")
    p_commit.set_defaults(func=cmd_commit_state)

    p_stats = sub.add_parser("stats", help="Print recent run stats and lane performance")
    p_stats.set_defaults(func=cmd_stats)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
