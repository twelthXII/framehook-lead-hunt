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

## Output language: Russian (permanent rule)

Every piece of user-facing prose this skill produces — lead descriptions,
observed-pain summaries, "why now" explanations, rejection reasons, proposed
service, contact research notes, weekly summaries, recommendations — is
written in **Russian**. This is permanent, not a one-time instruction.

Left unchanged (never translated): people's names, company/channel names,
URLs, usernames, email addresses, and the machine-readable status codes
themselves (`READY_NOW`, `GOOD_FIT`, `WATCH`, `REJECTED`, `CONTACT_FOUND`,
`CONTACT_NEEDED`, `CONTACT_EMAIL_ONLY`, `CONTACT_LINKEDIN_ONLY`,
`UNREACHABLE`, `CONFIRMED_LEAD`, `NO_CLEAR_PAIN`, `ALREADY_WELL_RESOURCED`).

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
 "confidence", "missing_information", "pain_hypothesis", "keep"}
```

`pain_hypothesis` at this stage is just your working guess at what the
concrete problem might be (e.g. "possible inconsistent thumbnail system") —
it is NOT a confirmed diagnosis yet. Nothing is confirmed pain until it
survives the PAIN GATE below, which for a visual claim requires an actual
visual audit, not a Pass-1 guess from metadata alone.

Select roughly 8-12 `keep: true` finalists (never more than 12 unless the crop is
unusually strong, never above the hard 20-lead ceiling downstream). `keep: true`
at this stage means "worth spending enrichment budget on to try to confirm
pain" — it does not mean the account has already qualified.

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

## The PAIN GATE — the most important rule in this skill

**A trigger is not a pain.** Money, monetization, sponsor count, subscriber
count, rapid growth, upload cadence, a launch, funding, or commercial activity
in general can make an account *interesting to look at*. None of it proves
Framehook has something useful to sell them. TRIGGER = why this account is
worth examining now. PAIN = the actual problem Framehook has evidence it can
solve. A trigger can raise urgency; it cannot manufacture pain that isn't
observed.

**A lead may only become GOOD_FIT or READY_NOW if it passes this gate.**
Before assigning either status, answer explicitly: *can we point to a
concrete, currently observable or independently confirmed problem that
Framehook can solve?*

- If **YES** (pain confirmed) → proceed to GOOD_FIT/READY_NOW per the fit/timing
  table above.
- If **NO** → **REJECTED, reason `NO_CLEAR_PAIN`** — regardless of money,
  company size, subscriber count, contact availability, timing, launch,
  sponsorship, or commercial value. This is a hard rule, not a nudge: a
  would-be GOOD_FIT/READY_NOW account that fails the gate goes straight to
  REJECTED, not down to WATCH (WATCH is for genuinely lower fit, 45-64 — not
  a landing pad for "attractive but unproven").

**Never invent a hypothetical operational problem to justify a lead.**
Unacceptable reasoning (do not write anything shaped like this): "they
probably need more content capacity," "they may need help scaling," "the
launch probably creates workload," "their output is high so they could use
help," "their packaging may be limiting performance" — unless actual evidence
supports the specific conclusion.

### What counts as evidence for the PAIN GATE

**Thumbnails / packaging** — acceptable: a visibly inconsistent thumbnail
system, weak or unclear hierarchy, repeated obvious execution problems, broken
compositing/background removal, weak series identity, poor visual
differentiation between videos, generic/repetitive packaging that creates a
credible business problem, a major mismatch between strong content and weak
packaging. **Not acceptable on their own:** "their thumbnails could be
better," "there's always room to improve." A creator already running a
coherent, professional system is not automatically a sales opportunity —
"pretty good, could be marginally better" is not pain.

**Content / editing** — acceptable: observable inconsistency in editing/output
quality, clearly weak editing relative to the creator's level, a specific
content-production problem confirmed through research, a confirmed need for
more production output or external support.

**Channel / content system** — acceptable: an obvious lack of
packaging/content consistency, a concrete evidence-backed content-operations
problem, a confirmed external production need.

### Visual audit requirement — mandatory for any thumbnail/packaging diagnosis

If the proposed service is thumbnails, a thumbnail system, packaging, a
thumbnail refresh, or visual channel packaging, **the lead cannot be
confirmed without an actual visual audit** of recent thumbnails (see the
Visual thumbnail audit section below). Do not give a high-confidence
packaging diagnosis from channel metadata, subscriber count, view rate,
monetization signals, or search snippets alone — none of that is a
substitute for actually looking at the thumbnails. If the audit hasn't
happened yet, the evidence is incomplete: report it as incomplete, do not
mark pain confirmed. **This is enforced in code, not just by discipline** —
`gate_pain_confirmed()` in `src/state.py` forces `pain_confirmed` to `False`
for any packaging-shaped proposed service when `visual_audit_done` isn't set,
regardless of what you submit.

### Evidence discipline

Always distinguish three kinds of statement:

- **OBSERVED/VERIFIED** — a fact actually supported by channel data, a visual
  audit, or research you did.
- **INFERENCE** — a reasonable interpretation drawn from that evidence, and
  labeled as an inference, not stated as fact.
- **UNKNOWN** — you tried to find out and couldn't. Say so; don't guess and
  present the guess as known.

Never invent: internal production capacity, team size, dissatisfaction with
current contractors, a lack of internal designers/editors, a need to scale
production, marketing budget, or decision-maker intent. If you don't know it,
say you don't know it.

**Do not invent performance metrics.** Never claim a thumbnail's CTR is bad,
that packaging is suppressing CTR, or that a redesign will improve CTR, unless
actual CTR data exists (it essentially never will from public research). A
visual audit can identify inconsistency, weak hierarchy, an unclear concept,
execution problems, or poor differentiation — visual appearance alone does
not prove anything about CTR.

## Reachability is a SEPARATE axis — it never changes opportunity status

Whether you've found a way to reach a decision maker does not make an
opportunity more or less good — it only tells you what the next action is.
**A missing contact must never demote READY_NOW to GOOD_FIT.** A funded studio
with a confirmed launch in 11 days *and confirmed pain* is a READY_NOW
opportunity whether or not you've found the marketing team's contact yet —
fit, timing, and pain are all already verified; only the contact is still
open. (Note: a launch alone, with no confirmed pain, is not READY_NOW at
all — see the PAIN GATE above. Reachability only becomes relevant once an
account has already cleared that gate.)

### Confirmed contact requires a NON-EMAIL, NON-LINKEDIN social/DM route

A candidate is not a confirmed lead until at least one usable direct
social/DM outreach route has been verified. **Neither email nor LinkedIn
qualifies a candidate as confirmed** — store both as supplemental
information if found, but neither does the job a qualifying contact does.
LinkedIn was previously treated as qualifying; it no longer is, because a
LinkedIn profile alone rarely translates into a realistic DM-able route for
this kind of outreach.

**Qualifying contacts**, preferred order:

1. personal Telegram profile/username
2. founder/creator Telegram
3. personal X/Twitter
4. founder/creator X/Twitter
5. personal Instagram
6. founder/creator Instagram
7. Discord or another genuine direct-message route
8. (fallback) an official brand/company Instagram, X, Telegram, or other
   social page where DM outreach is realistically possible

A personal decision-maker account is stronger than a generic company account.

**Never count as a qualifying contact:** email only, LinkedIn only, a website
URL, a contact form, a YouTube channel, a YouTube handle, a person's name
with no reachable profile, a generic search result with no verified
ownership, or a social account that can't reasonably be connected to the
creator/business.

### Contact status — five values

- **`CONTACT_FOUND`** — at least one verified qualifying social/DM contact
  (see the list above — Telegram, X, Instagram, Discord, or an equivalent)
  exists.
- **`CONTACT_NEEDED`** — a good opportunity, but no qualifying contact found
  yet. This is the default — never assume `UNREACHABLE` just because one
  search came up empty, and a YouTube handle alone still reports as
  `CONTACT_NEEDED`, not `CONTACT_FOUND`.
- **`CONTACT_EMAIL_ONLY`** — only an email address was found. Weaker than
  `CONTACT_FOUND`; store the email as supplemental info, but this status does
  not confirm the lead.
- **`CONTACT_LINKEDIN_ONLY`** — only a LinkedIn profile was found. Same
  weakness as `CONTACT_EMAIL_ONLY` — store it as supplemental info, but it
  does not confirm the lead either.
- **`UNREACHABLE`** — you actively researched and found good reason to believe
  there is no viable path in at all (e.g. a gatekept large company with no
  public contact surface). Use sparingly; this is a stronger claim than "I
  didn't find one."

When you record a verdict with `contact_status: "CONTACT_FOUND"`, also record
`contact_platform` (e.g. `"Telegram"`, `"X"`, `"Instagram"`) and
`contact_value` (the actual handle/link) — the report needs to show these.

### CONFIRMED_LEAD

A candidate is `CONFIRMED_LEAD: YES` only when **all** of these hold:

1. correct ICP / sufficient fit
2. passes the PAIN GATE
3. the diagnosis is evidence-backed (not an inference presented as fact)
4. at least one qualifying social/DM contact is verified (`CONTACT_FOUND`) —
   email or LinkedIn alone is not enough

Worked examples:

| Opportunity | Contact | CONFIRMED_LEAD |
|---|---|---|
| READY_NOW | CONTACT_FOUND | **YES** |
| READY_NOW | CONTACT_NEEDED | NO |
| GOOD_FIT | CONTACT_FOUND | **YES** |
| GOOD_FIT | CONTACT_EMAIL_ONLY | NO |
| GOOD_FIT | CONTACT_LINKEDIN_ONLY | NO |
| REJECTED | CONTACT_FOUND | NO |

**A contact can never rescue a bad opportunity**, and a good opportunity isn't
confirmed until it's reachable through a real social/DM route.

### Account value

- ENTRY: realistic <$2k/mo
- CORE: realistic $2k-5k/mo
- WHALE: realistic $5k+/mo

These are potential estimates from observable economics (subs, views, sponsorship
signals, business maturity) — never claim a known budget.

## Processing order (do not skip ahead to contact research)

```
discovery (src/hunt.py, already done)
  -> deterministic filtering (already done)
  -> Pass 1 fit/timing scoring + pain hypothesis
  -> evidence gathering / visual audit
  -> PAIN GATE
  -> business qualification (GOOD_FIT / READY_NOW / WATCH / REJECTED)
  -> targeted enrichment (only accounts that passed the gate)
  -> social contact research (only accounts that passed the gate)
  -> final classification + CONFIRMED_LEAD
```

Resolve pain *before* spending any budget on contact research. Do not
research decision-maker contacts for an account that already fails the PAIN
GATE — that's wasted tokens and wasted search budget on an account that's
being rejected anyway.

## Targeted enrichment (only accounts that passed the PAIN GATE, max 10 accounts)

Before every search ask: **what unknown fact could materially change the
decision?** Default to **one** targeted web search per finalist (monetization
model, business model, confirming/refuting a pain hypothesis — whichever is
the actual open question for that account). Allow a second search only if a
major qualification uncertainty remains. Hard cap: 2 searches per finalist.

Once an account has passed the PAIN GATE (GOOD_FIT or READY_NOW), spend
research on **social contact research**: look specifically for a creator,
founder, owner, or other decision-maker's personal Telegram, X, or Instagram
(see the qualifying-contact list above — LinkedIn does NOT qualify, treat a
LinkedIn hit the same as an email: worth storing, not worth confirming a lead
over), not just "does this account have a website." Do not check every
platform for every account — stop once you've found a qualifying contact, or
once you've made a genuine attempt and come up empty (that's `CONTACT_NEEDED`,
not a reason to keep burning searches).

## Visual thumbnail audit (5-8 finalists being considered for thumbnails/packaging)

Run `python3 src/hunt.py contact-sheet --channel <id> --count 6` and Read the
resulting PNG. Judge visual hierarchy, clarity, concept strength, consistency,
recurring system/series identity, obvious execution mistakes, and quality
relative to the channel's commercial level — i.e. whether an actual solvable
problem exists, per the PAIN GATE criteria above. Never claim or invent CTR
numbers — you cannot observe CTR from thumbnails alone. If you have not run
this audit, do not report a packaging pain as confirmed (see the visual audit
requirement above) — say the evidence is incomplete instead.

## Persisting your verdicts (required every run)

After Pass 1 and enrichment, write a JSON file (e.g. to a scratch path) shaped as:

```json
{
  "verdicts": [
    {
      "id": "channelId",
      "fit": 91,
      "timing": "HIGH",
      "pain_confirmed": true,
      "proposed_service": "thumbnail system",
      "visual_audit_done": true,
      "contact_status": "CONTACT_FOUND",
      "contact_platform": "Telegram",
      "contact_value": "@handle",
      "rejection_reasons": []
    },
    ...
  ],
  "finalists_order": ["channelId1", "channelId2", ...]
}
```

Field notes:

- `pain_confirmed` — your PAIN GATE answer for this account. Omit or `false`
  means the gate failed; `src/state.py` will send a would-be GOOD_FIT/READY_NOW
  straight to REJECTED when this is false, regardless of fit/timing.
- `proposed_service` — free text (e.g. "thumbnail system", "editing +
  packaging"). Used to check whether a visual audit was required.
- `visual_audit_done` — set `true` only if you actually ran the contact-sheet
  audit for this account. If `proposed_service` is thumbnail/packaging-shaped
  and this is false, `pain_confirmed` is forced to `false` regardless of what
  you submit — the code enforces this, not just the instructions.
- `contact_status` — one of `CONTACT_FOUND` / `CONTACT_NEEDED` /
  `CONTACT_EMAIL_ONLY` / `CONTACT_LINKEDIN_ONLY` / `UNREACHABLE`. Omit it and
  it defaults to `CONTACT_NEEDED`. Only meaningful for accounts that passed
  the PAIN GATE. LinkedIn found but nothing better → `CONTACT_LINKEDIN_ONLY`,
  not `CONTACT_FOUND`.
- `contact_platform` / `contact_value` — only when `contact_status` is
  `CONTACT_FOUND`: which platform (`"Telegram"`, `"X"`, `"Instagram"`, ...)
  and the actual handle/link. The report needs both.
- `rejection_reasons` — a list, only meaningful when the account ends up
  REJECTED. Include specific codes like `["NO_CLEAR_PAIN"]` or
  `["NO_CLEAR_PAIN", "ALREADY_WELL_RESOURCED"]`. If omitted and pain wasn't
  confirmed, it defaults to `["NO_CLEAR_PAIN"]`.

Include a verdict for every pack you scored in Pass 1 (not just finalists — a
rejected account still needs its fit/timing recorded so the recheck cadence
works). `finalists_order` must match the numbering in your final output table.
Then run:

```
python3 src/hunt.py record --input <path-to-that-json>
python3 src/hunt.py commit-state
```

## Output format (this is the ONLY thing that goes to chat — written in Russian, see above)

The report prioritizes CONFIRMED actionable leads first. Order every
candidate you show by this 5-tier priority (this supersedes plain
READY_NOW-then-GOOD_FIT ordering — a confirmed GOOD_FIT outranks an
unconfirmed READY_NOW, because it's something the user can act on today):

1. READY_NOW + CONTACT_FOUND + CONFIRMED_LEAD
2. GOOD_FIT + CONTACT_FOUND + CONFIRMED_LEAD
3. READY_NOW + CONTACT_NEEDED
4. GOOD_FIT + CONTACT_NEEDED
5. WATCH (small, only if genuinely worth tracking — cap 5)

An account marked `UNREACHABLE`, `CONTACT_EMAIL_ONLY`, or
`CONTACT_LINKEDIN_ONLY` with nothing better still appears (it's a real
opportunity, just not yet actionable by DM) but sorts below the
`CONTACT_NEEDED` rows in its tier. Do not clutter the report with REJECTED
accounts — they don't appear here at all, regardless of how interesting they
looked before the PAIN GATE. If nothing qualifies for a tier, skip that
heading entirely rather than printing an empty section.

For every candidate shown, use this compact card (all prose in Russian; names,
URLs, usernames, emails, and status codes stay as-is):

```
### N. <Название>

- Ссылка на канал: <url>
- Размер канала: <subs, если известен>
- Opportunity Status: READY_NOW | GOOD_FIT | WATCH
- Подтверждённый лид: ДА | НЕТ
- Fit: <0-100>
- Timing: HIGH | MEDIUM | LOW
- ICP: <...>
- Коммерческий сигнал: <...>
- Наблюдаемая проблема: <...>
- Доказательства: <что именно проверено — метаданные / визуальный аудит / поиск>
- Почему сейчас: <триггер, если есть, иначе явно "триггера нет">
- Предлагаемая услуга Framehook: <...>
- Contact Status: CONTACT_FOUND | CONTACT_NEEDED | CONTACT_EMAIL_ONLY | CONTACT_LINKEDIN_ONLY | UNREACHABLE
- Telegram / X / Instagram / qualifying DM-контакт: <тип и что найдено, или "не найден">
- Ссылка/username: <...>
- Email (отдельно, если найден): <...>
- LinkedIn (отдельно, если найден): <...>
- Что делать дальше: <конкретное следующее действие>
```

If no real pain was found for a candidate, do not invent an offer to fill the
report — that candidate is REJECTED and simply doesn't appear.

Number cards continuously across all tiers (the numbering is what the user
replies to with feedback). Total leads across tiers 1-4: prefer 8-12, hard
ceiling 20.

Then, if applicable:

```
## Изменения статуса
```

Max 5 accounts whose status materially changed since last run. Omit entirely
if nothing materially changed.

Then exactly one stats line (machine-readable, can stay in English):

```
Raw: X | Filtered: X | Claude: X | Enriched: X | CONFIRMED_LEAD: X | READY_NOW: X | GOOD_FIT: X
```

**Never output:** essays, architecture explanation, a rejected-account report, a
raw source dump, development commentary, or drafted outreach messages. If the
user later asks to "expand #4", research and show detail only for that one
account — do not produce per-lead detail reports by default.

## AD_HOC_HUNT — a temporary, natural-language targeted search

The user can ask for a one-off targeted search in plain language at any time,
separately from the weekly hunt — e.g. "Найди мне CS2 ютуберов", "Найди
русских CS2 каналов", "Найди SaaS-компании с плохими YouTube превью", "Найди
автомобильных блогеров 50k–500k подписчиков", "Найди англоязычных
AI-ютуберов, которым можно продавать packaging". Recognize these as
AD_HOC_HUNT requests.

**This is temporary by design and must never permanently change the weekly
system.** Never touch `config/lanes.json`, the weekly query budget, the
production ICP/subscriber defaults, or `query_stats`/`lane_query_index`/
`rotation_index`/`runs` in state — those stay exactly as the weekly hunt left
them, unless the user explicitly says something like "сохрани это в еженедельный
поиск" / "apply this to the weekly hunt". "Найди мне CS2 ютуберов" must not
turn the production system into a CS2-only search.

### Interpreting the request — explicit constraints only, nothing inferred

**Rule: EXPLICIT USER CONSTRAINTS become hard temporary constraints.
UNSPECIFIED FIELDS stay neutral / use broad Framehook discovery defaults.**
Never fill in an unspecified field by inferring it from a *different*
explicit field — geography/language never implies a service, and a service
never implies geography/language. Each constraint the user actually stated
maps to exactly one `adhoc` flag; nothing else.

- **Geography/language stated** ("русских", "англоязычных") → set
  `--language`/`--region` to that. Do NOT also set `--offers` from it. Russian
  language/geography does not by itself prove editing is the right offer —
  it only affects the geography-specific editing rule if a service ends up
  being editing after the PAIN GATE (see Service geography, above).
- **Language/geography not stated** ("Найди CS2 ютуберов", with nothing about
  language) → leave `--language`/`--region` unset entirely. Do not default to
  English. An unset `--language` runs a broad, language-neutral search
  (`relevanceLanguage` is simply omitted) — that is the true neutral default,
  not "en".
- **Service/offer stated explicitly** ("которым нужны превью" → thumbnails,
  "для монтажа" → editing) → set `--offers` to that, and if it's editing,
  that's also where a CIS-leaning `--icp cis_editing`/`--region` becomes
  justified (the service implies the ICP here, not the other way around).
- **Service/offer not stated** → do NOT set `--offers` at all (it falls back
  to the neutral thumbnails+packaging baseline, which is informational context
  for Claude, not a restriction). The actual service you propose per account
  is decided **after** evidence collection and the PAIN GATE, per-candidate —
  never pre-committed from the request text.
- **Subscriber range stated** ("50k–500k подписчиков") → set
  `--subs-min`/`--subs-max` to exactly that. Not stated → leave both unset
  (normal ICP default range applies).
- **Niche/topic/game** → always comes through as the actual search query
  strings you compose for `--queries`. This is the one thing every AD_HOC_HUNT
  request specifies by definition.

Worked examples:

| Request | `--language`/`--region` | `--offers` | `--icp` |
|---|---|---|---|
| "Найди русских CS2 ютуберов" | `ru` / `RU` (stated) | unset — decide after evidence | default |
| "Найди CS2 ютуберов" | unset (not stated) | unset — decide after evidence | default |
| "Найди CS2 ютуберов, которым нужны превью" | unset | `thumbnails` (stated) | default |
| "Найди русских CS2 ютуберов для монтажа" | `ru` / `RU` (stated) | `editing` (stated) | `cis_editing` (justified by the stated service) |

Do not ask clarifying questions first for anything left unspecified — run
with the neutral default and let the results speak.

Translate your interpretation into real YouTube search query strings and
pass them to `adhoc`, e.g. for "Найди русских CS2 ютуберов" (language stated,
service not):

```
python3 src/hunt.py adhoc \
  --queries "<comma-separated search strings you composed>" \
  --language ru --region RU \
  --label cs2_ru
```

This is a thin, purely mechanical layer — it builds one temporary in-memory
lane, runs the exact same search/prefilter/evidence-pack code the weekly hunt
uses, and prints a shortlist, exactly like `discover`. It never writes
`config/lanes.json` and never touches weekly bookkeeping in state.json.

### Same standards, no exceptions

AD_HOC_HUNT uses the identical qualification pipeline as the weekly hunt —
do not lower the bar just because the user asked for a specific niche:

```
natural-language request -> temporary query config (you build this)
  -> python3 src/hunt.py adhoc (discovery + deterministic filtering)
  -> evidence collection / visual audit where relevant
  -> PAIN GATE
  -> business/ICP qualification
  -> targeted enrichment
  -> social contact research (same non-email, non-LinkedIn rule)
  -> final classification, same READY_NOW/GOOD_FIT/WATCH/REJECTED + CONFIRMED_LEAD
```

"Найди CS2 ютуберов" does not mean "return every CS2 creator" — it still
requires real confirmed pain, business fit, and Framehook relevance. Most
niche searches will still turn up mostly REJECTED accounts; that's expected
and correct, not a bug.

### State and dedupe

`adhoc` reads `state/state.json` to skip re-analyzing an unchanged, already-
REJECTED channel (same as the weekly hunt's fingerprint check) — if the user
says "проверь его заново", that overrides the skip for that one account. After
Claude's judgment, persist verdicts through the same `record` command used by
the weekly hunt (it writes to the shared `accounts` registry only — never to
query lanes or weekly bookkeeping).

### Output

All in Russian, following the same CONFIRMED-first priority, but with its own
headings:

```
## ПОДТВЕРЖДЁННЫЕ ЛИДЫ
## ПЕРСПЕКТИВНЫЕ, НО НУЖЕН КОНТАКТ
## WATCH   (optional, small)
```

Same per-candidate fields as the weekly report (channel, link, subs, niche,
Fit, Timing, concrete pain, evidence, proposed service, Telegram/X/Instagram
contact, Contact Status, Подтверждённый лид). Do not dump large REJECTED lists
unless the user asks for them.

## What this skill will never do

Do not rewrite scoring weights, subscriber ranges, or keyword lists based on one
run's feedback — that requires the user's explicit instruction (feedback only
adjusts which query lanes get budget, which is handled entirely in
`src/state.py`, not by you). Do not modify `src/`, `config/`, or this skill file
during a production hunt — if something is broken, report the blocker instead of
fixing it live. Production hunts are operated, not engineered.

An AD_HOC_HUNT request never edits `config/lanes.json`, never changes the
weekly query budget or ICP defaults, and never writes to `query_stats`,
`lane_query_index`, `rotation_index`, or `runs` — even when the user's request
is oddly specific ("Найди только Valorant-каналы"). Those files/fields belong
to the weekly hunt alone.

## Learning from manual calibration feedback — generalize, don't overfit

When the user manually reviews a lead and corrects its classification, that
correction is a calibration example, not a rule about that specific account.
Extract the general principle, not the specifics.

- Correct: "commercially attractive account + no observable pain = reject."
  Incorrect: "reject channels above 300k subscribers."
- Correct: "a launch is timing, not proof of production pain."
  Incorrect: "reject game studios."

Manual feedback should sharpen future judgment (and, through the normal
feedback-loop mechanism, future query-lane allocation) — it should never
harden into a hard rule tied to one channel, one subscriber count, or one
niche unless the user explicitly asks for that rule.
