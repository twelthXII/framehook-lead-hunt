---
name: framehook-lead-hunt
description: Business judgment for the Framehook weekly lead hunt — ICP definitions, service geography, fit/timing scoring, enrichment rules, and the fixed output format. Use this whenever running the weekly Framehook Lead Hunt routine, processing candidate evidence packs from src/hunt.py, or answering "expand #N" follow-ups on a prior hunt's output.
---

# Framehook Lead Hunt — business judgment

Framehook (framehook.agency) sells YouTube thumbnails, packaging, editing, Shorts,
motion, strategy, and full-service channel management. This skill exists to turn a
small set of deterministic candidate evidence packs into a short list of real sales
opportunities. It does not do discovery or scoring math — `src/hunt.py` already did
that. Your job is judgment: read each pack, decide fit and timing, pick finalists,
do targeted research on those finalists only, and write the fixed-format output.

**Goal: 7-12 genuinely strong opportunities. 20 is a hard ceiling, never a target.**
Ask before including any lead: *would a rational Framehook founder actually spend
time contacting this account?* If probably not, drop it — do not pad the table.

## Who Framehook sells to

**Primary — commercial creators.** Channels that function as businesses: regular
publishing, sponsorships, own product/course/community, affiliate activity,
ecommerce, podcast/newsletter, a team, multiple platforms. Niches: business,
entrepreneurship, AI, SaaS, tech, finance, education, fitness, automotive,
marketing, sales, real estate, consulting, gaming, entertainment.

**Secondary — established monetized creators.** Consistent publishing, meaningful
views, sponsors, products, a reachable business contact.

**Founder-led businesses — only with existing content intent.** A founder who
already posts video, runs a podcast, or has a content team. Do not qualify a
random well-funded SaaS company just because it has money and no content habit.

**Agencies — white-label potential.** YouTube/personal-branding/podcast/creator
agencies that lack in-house thumbnail, editing, packaging, Shorts, or motion
capacity.

## Service geography (this is service-specific, not one global filter)

- **Editing / montage:** actively target Russian-speaking / CIS creators and
  businesses (Russia, Belarus, Kazakhstan, Armenia, Georgia, Uzbekistan,
  Kyrgyzstan, Azerbaijan, Moldova, and other Russian-speaking markets). The
  variable is language/audience, not passport. Do not actively pursue standalone
  editing for global English-speaking creators.
- **Thumbnails / YouTube packaging:** global — US, Canada, UK, Australia, Europe,
  CIS, other commercially strong markets. Never reject a candidate just because
  editing isn't the right offer for them — assign `eligible_offers` instead and
  pitch packaging.

Every evidence pack already carries `eligible_offers` computed from its lane. Trust
it, but use judgment if the pack's signals suggest a different offer fits better.

## Creator range

Commercial creators: mainly 20k-500k subscribers. Allow 500k-1M selectively when
reachability and commercial fit are unusually strong — this is the exception, not
the rule. Founder-led businesses and CIS editing leads can justify much smaller
channels when the underlying business economics, content volume, or views are
strong. `src/hunt.py` has already applied a coarse subscriber filter per ICP; still
use judgment on the exceptions.

## Pass 1 — score the shortlist (no web browsing yet)

You receive at most 25 compact evidence packs (~200-400 tokens each) in one batch.
Score all of them in a single pass, no per-account subagents, no browsing yet.
For each pack return only structured fields — no prose:

```
{"id", "preliminary_fit", "timing", "account_value", "expansion",
 "confidence", "missing_information", "keep"}
```

Select roughly 8-12 `keep: true` finalists (never more than 12 unless the crop is
unusually strong, never above the hard 20-lead ceiling downstream).

### Fit (0-100) — a single objective score, independent of timing

- Economic / monetization value: 25
- Recurring content need: 20
- Framehook-solvable gap: 20
- Reachability: 15
- Proof fit (does the observable content match what Framehook is good at): 10
- Expansion potential (thumbnail → packaging → editing → Shorts → strategy →
  full channel management): 10

### Timing — HIGH / MEDIUM / LOW, scored separately from fit

Timing reflects buying triggers only: a new sponsor keyword, a cadence change, a
new product/course signal, a visible content-quality gap that *just appeared*, a
recent upload spike. **Never invent a trigger.** No trigger observed = LOW timing,
which is fine — a high-fit account with LOW timing is still worth including.

**A high fit score is never enough by itself for the urgent status.** Fit and
timing are independent axes, and they map to status like this:

| | Timing HIGH (real trigger) | Timing MEDIUM/LOW (no live trigger) |
|---|---|---|
| Fit ≥ 65 | **READY_NOW** | **GOOD_FIT** |
| Fit 45-64 | WATCH | WATCH |
| Fit < 45 | REJECTED | REJECTED |

"The channel could use better thumbnails" is a Framehook-solvable gap, not a
buying trigger — it never on its own justifies READY_NOW.

### Reachability is a SEPARATE axis — it never changes opportunity status

Whether you've found a way to reach a decision maker does not make an
opportunity more or less good — it only tells you what the next action is.
**A missing contact must never demote READY_NOW to GOOD_FIT.** A funded studio
with a confirmed launch in 11 days is a READY_NOW opportunity whether or not
you've found the marketing team's email yet — the fit and the timing trigger
are both real and already verified; only the contact is still open.

Track `contact_status` on every GOOD_FIT-or-better account, one of:

- **`CONTACT_FOUND`** — a named decision maker, a real business email, or (for
  a solo creator) a business site/About-page/DM path you actually found.
- **`CONTACT_NEEDED`** — not yet researched, or researched but inconclusive.
  This is the default — never assume `UNREACHABLE` just because one search
  didn't turn up a contact.
- **`UNREACHABLE`** — you actively researched and found good reason to believe
  there is no viable path in (e.g. a gatekept large media company with no
  public contact surface at all). Use sparingly; this is a stronger claim than
  "I didn't find one."

READY_NOW + CONTACT_NEEDED means: *this is a timely opportunity — contact
research is the next action*, not "this isn't ready yet."

### Account value

- ENTRY: realistic <$2k/mo
- CORE: realistic $2k-5k/mo
- WHALE: realistic $5k+/mo

These are potential estimates from observable economics (subs, views, sponsorship
signals, business maturity) — never claim a known budget.

## Targeted enrichment (finalists only, max 10 accounts)

Before every search ask: **what unknown fact could materially change the
decision?** Default to **one** targeted web search per finalist (monetization
model, decision maker, recent trigger, business model, team size — whichever is
the actual open question for that account). Allow a second search only if a major
qualification uncertainty remains. Hard cap: 2 searches per finalist. Do not check
Instagram, LinkedIn, TikTok, X, the website, and Telegram all for the same
account — only the one or two that resolve the real unknown.

For any account that scores READY_NOW or GOOD_FIT (fit ≥ 65), spend the
search on reachability itself: is there a named contact, a business email, or
(for a solo creator) a real business site/About page — something you'd
actually message? A YouTube channel simply existing is not `CONTACT_FOUND`.
If the search doesn't turn up a contact, that's `CONTACT_NEEDED` — it does
not change the account's fit or timing, and it does not mean `UNREACHABLE`.

## Visual thumbnail audit (5-8 finalists being considered for thumbnails/packaging)

Run `python3 src/hunt.py contact-sheet --channel <id> --count 6` and Read the
resulting PNG. Judge visual hierarchy, clarity, concept strength, consistency, and
the observable Framehook-solvable packaging gap. Never claim or invent CTR
numbers — you cannot observe CTR from thumbnails alone.

## Persisting your verdicts (required every run)

After Pass 1 and enrichment, write a JSON file (e.g. to a scratch path) shaped as:

```json
{
  "verdicts": [
    {"id": "channelId", "fit": 91, "timing": "HIGH", "contact_status": "CONTACT_FOUND"},
    ...
  ],
  "finalists_order": ["channelId1", "channelId2", ...]
}
```

`contact_status` is one of `CONTACT_FOUND` / `CONTACT_NEEDED` / `UNREACHABLE`;
omit it (or leave it out for anything below GOOD_FIT) and it defaults to
`CONTACT_NEEDED`.

Include a verdict for every pack you scored in Pass 1 (not just finalists — a
rejected account still needs its fit/timing recorded so the recheck cadence
works). `finalists_order` must match the numbering in your final output table.
Then run:

```
python3 src/hunt.py record --input <path-to-that-json>
python3 src/hunt.py commit-state
```

## Output format (this is the ONLY thing that goes to chat)

Two axes, both shown, neither hidden: group by opportunity status
(READY_NOW / GOOD_FIT / WATCH) as before, but order rows within READY_NOW and
GOOD_FIT by this priority so the most actionable leads are always on top:

1. READY_NOW + CONTACT_FOUND
2. READY_NOW + CONTACT_NEEDED
3. GOOD_FIT + CONTACT_FOUND
4. GOOD_FIT + CONTACT_NEEDED
5. WATCH (unordered by contact — contact research isn't spent here yet)

An account marked `UNREACHABLE` stays in state at its real opportunity status
but is left out of this table — confirmed-unreachable isn't something the user
can act on this week, so it doesn't earn a row (it's not "rejected," just not
actionable right now; it'll resurface if its fingerprint changes).

```
## READY_NOW

| # | Lead | Fit | Timing | ICP | Value | Opportunity | Offer | Contact |
|---:|------|----:|--------|-----|-------|-------------|-------|---------|

## GOOD_FIT

| # | Lead | Fit | Timing | ICP | Value | Opportunity | Offer | Contact |
|---:|------|----:|--------|-----|-------|-------------|-------|---------|

## WATCH

| # | Lead | Fit | Timing | ICP | Value | Opportunity | Offer | Contact |
|---:|------|----:|--------|-----|-------|-------------|-------|---------|
```

- Number rows continuously across all three sections (READY_NOW #1-#3, GOOD_FIT
  #4-#9, ...) — the numbering is what the user replies to with feedback.
- READY_NOW + GOOD_FIT combined: maximum 20 rows, prefer 8-12. Omit a section
  entirely if it's empty — don't print an empty table.
- WATCH is supplementary, not part of the lead count: cap it at 5 rows and only
  include an account there if it's genuinely worth tracking, not to pad the
  report.
- Opportunity: max 12 words, concrete and specific — not generic filler.
- Offer: max 5 words, one primary entry offer (do not pitch everything at once:
  thumbnails, thumbnail system, YouTube packaging, titles + thumbnails, editing,
  editing + packaging, Shorts, content production, or channel management).
- Contact: the actual contact when `CONTACT_FOUND`, or literally `CONTACT_NEEDED`
  otherwise — never paper over an open contact gap with a vague "YouTube About
  page" guess, and never let a missing contact talk you into writing GOOD_FIT
  for a row whose Fit/Timing columns say READY_NOW.

Then:

```
## STATUS CHANGES
```

Max 5 accounts whose status materially changed since last run (e.g. moved into
READY_NOW, or dropped out of WATCH into REJECTED). Omit this section entirely if
nothing materially changed.

Then exactly one stats line:

```
Raw: X | Filtered: X | Claude: X | Enriched: X | READY_NOW: X | GOOD_FIT: X
```

**Never output:** essays, architecture explanation, a rejected-account report, a
raw source dump, development commentary, or drafted outreach messages. If the
user later asks to "expand #4", research and show detail only for that one
account — do not produce per-lead detail reports by default.

## What this skill will never do

Do not rewrite scoring weights, subscriber ranges, or keyword lists based on one
run's feedback — that requires the user's explicit instruction (feedback only
adjusts which query lanes get budget, which is handled entirely in
`src/state.py`, not by you). Do not modify `src/`, `config/`, or this skill file
during a production hunt — if something is broken, report the blocker instead of
fixing it live. Production hunts are operated, not engineered.
