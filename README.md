# Framehook Lead Hunt

A weekly sales-intelligence system for [Framehook](https://www.framehook.agency/).
It runs entirely on Claude Code: a deterministic Python discovery pipeline finds
and filters real YouTube activity, and Claude — guided by a static Skill — applies
business judgment to a small shortlist and does targeted research on finalists
only. There is no separate app, database, or dashboard. The GitHub repo is the
whole system.

## Why it's built this way

The previous version mirrored code into Claude Project documents so scheduled
sessions could see it, which made it fragile and hard to maintain. This version
runs directly against a cloned git repo via a Claude Code Remote Routine, so there
is nothing to mirror and nothing to keep in sync.

## Architecture

```
MANY RAW CANDIDATES (YouTube search, ~300-500/week)
        v
DETERMINISTIC CODE (src/hunt.py + scoring_support.py)  <- no Claude tokens spent here
        v
SMALL SHORTLIST (<=25 compact evidence packs, ~200-400 tokens each)
        v
CLAUDE, guided by .claude/skills/framehook-lead-hunt/SKILL.md
        v
8-12 FINALISTS -> targeted WebSearch/WebFetch (max 2 searches each) + thumbnail contact sheets
        v
FINAL OUTPUT: one markdown table, max 20 rows, prefer 8-12
```

```
.claude/skills/framehook-lead-hunt/SKILL.md   Business judgment: ICPs, geography, fit/timing, output format
src/hunt.py           CLI entry point — discover, lookup, contact-sheet, record, feedback, commit-state, stats
src/youtube.py        Minimal YouTube Data API v3 client (stdlib only)
src/state.py          Fingerprinting, recheck cadence, adaptive query-lane budget, feedback parsing
src/scoring_support.py Signal extraction, deterministic prefilter, evidence-pack building, shortlist selection
config/lanes.json     Query lanes, subscriber ranges, recheck cadence, budget knobs
state/state.json      Small persistent state — committed to git after every run
eval/golden.json      Empty schema; only human-reviewed real leads may ever be added
tests/                Deterministic unit tests (no synthetic "lead quality" tests)
```

## Persistent state

State lives in `state/state.json` and is committed back to this repo by
`python3 src/hunt.py commit-state` at the end of every run. No external database,
no Cloudflare Worker, no Claude Project documents. Git history is the audit log.

## Setup

1. `pip install -r requirements.txt`
2. Set `YOUTUBE_API_KEY` (YouTube Data API v3 key) in your environment — see
   `.env.example`. Never commit the real key.
3. Run the deterministic tests: `pytest tests/`

## Running a hunt (what the Remote Routine does)

1. `python3 src/hunt.py discover` — prints `{"stats": {...}, "candidates": [...]}`
   (at most 25 evidence packs) to stdout and updates `state/state.json` in place.
2. Claude reads the Skill (`.claude/skills/framehook-lead-hunt/SKILL.md`), scores
   the candidates, picks finalists, runs targeted enrichment and thumbnail
   contact sheets (`python3 src/hunt.py contact-sheet --channel <id>`), then
   optionally pulls in extra candidates found via its own WebSearch budget with
   `python3 src/hunt.py lookup --channel <id_or_@handle> --lane <lane_id>`.
3. Claude writes its verdicts to a scratch JSON file and runs:
   `python3 src/hunt.py record --input <file>`
4. Claude runs `python3 src/hunt.py commit-state` to persist the run.
5. Claude posts the fixed-format output (see the Skill) to chat. Nothing else.

## Feedback loop

Reply to a weekly result with lines like `1 good`, `2 too big`, `5 bad fit`,
`7 replied`. Feed that text to:

```
python3 src/hunt.py feedback "1 good 2 too big 5 bad fit 7 replied"
```

Supported labels: `GOOD`, `TOO_BIG`, `NO_MONEY`, `BAD_FIT`, `WRONG_MARKET`,
`ALREADY_TOO_STRONG`, `NO_CONTACT`, `CONTACTED`, `REPLIED`, `CALL`, `WON`, `LOST`.
This only ever adjusts which query lanes get more/less budget next run and each
account's status/recheck date — it never changes scoring weights or filters. No
lane is ever permanently reduced to zero budget by this loop.

## Production vs. development

**Production** (the scheduled Remote Routine) only runs the steps above. It must
never edit `src/`, `config/`, or the Skill, and must never "improve" the system
mid-run — if something breaks, it reports the blocker and stops.

**Development** (this interactive session, or a future one) is where filters,
lanes, scoring, and the Skill get changed and tested with `pytest tests/`.

## Setting up the weekly Remote Routine

Once a real controlled hunt (see below) has been reviewed and looks right, use
the `/schedule` skill to create a Claude Code Remote Routine against this repo
(`twelthXII/framehook-lead-hunt`) that runs the steps in "Running a hunt" on a
weekly cadence, with `YOUTUBE_API_KEY` set as an environment secret on the
routine. This is a deliberate manual step, not something this build does for you.
