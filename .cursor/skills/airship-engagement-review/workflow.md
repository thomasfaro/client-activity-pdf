# Workflow — mode A, step by step

Part of the [airship-engagement-review skill](SKILL.md). The core lists the steps in one line each; this file carries the detail. Read it when you run a step by hand. The orchestrator (`scripts/run_review.py`) runs the same steps in code.

## Two different kinds of exhaustiveness — do not confuse them

**The DATA must be exhaustive. The PROSE must be sufficient.** These pull in opposite
directions and conflating them is what turns a review into a long document that says
little.

Reading every row is a matter of **correctness**: a rate computed on 60% of the sends is
a wrong number, and no amount of writing around it fixes that. Reading every row costs
API calls and script time, not judgement, and it is not negotiable.

Writing about every row is a matter of **editorial judgement**, and more is not better.
A section that reports a finding and reaches a verdict has done its job; the same section
padded to exploit every available field has buried it. The reader is a CSM or AM preparing
a client conversation — their scarce resource is attention, not pages.

So: **collect and compute without shortcuts, then write only what changes what the reader
would do.** When a section has less to say because the account genuinely does less, say
that in one honest paragraph instead of manufacturing three.

### Stop rule

A section is done when it states what the data shows, reaches a verdict, and carries the
visual that makes the verdict checkable. Not when every available field has appeared. If
you are adding a table because a field exists rather than because a reader needs it, stop.

The gate enforces this asymmetrically on purpose: structure and correctness **block**,
while the volume floors (how many recommendations, callouts, charts, how long a section is)
are **advisory**. A `!` on a volume floor is a question for you, not an instruction — either
the account has less to say, or the section is under-worked. Decide, and say which in the
report.

## Data exhaustiveness contract (ZERO shortcut)
Applies to **collection and computation** — everything up to and including `audit.json`.
As the analysis grows (Reports API **and** the optional tagging-plan audit), the skill
**must never skip or abridge the most expensive steps**, and **every section must have
access to the maximum of all data** available from the file(s) and the API.
- **Hard rule — no voluntary sub-sampling to go faster.** Any limit must be **technical**
  (e.g. a genuinely intractable per-push firehose) and then handled by **loss-less program-
  level aggregation with an explicitly quantified coverage** ("N of M days, X% of sends"),
  never a silent shortcut. Prefer more API calls / more passes over a thinner analysis.
- **Full pagination is mandatory**: `/events` (all pages), the activity log (every
  `next_page`), `responses/list` (whole window). **Decode ALL the `perpush/pushbody`** you
  need — the decode-once cache exists to avoid *re-*decoding, not to avoid decoding.
- **Audit exploited in full**: `parse_tagging_plan.py` already keeps every item/value (no
  top-N); the enrichment then **processes EVERY** event / attribute / tag / subscription
  list / screen — no silent "top N". Long tables stay searchable/exportable to remain
  readable **without truncating** the data.
- **Per-section data-availability checklist.** For each section, know which audit AND API
  fields it *could* draw on, so nothing is missed for lack of looking. Then publish the ones
  that change the reading — this is a list of what you must have computed, not a list of what
  must appear on the page:
  - **Conversion & impact**: every Reports KPI cross-referenced to `valueBearing` /
    `monetaryValue` / `eventProperties`; every tracked conversion event listed even when it
    did not fire in the window (design intent vs actual firing).
  - **Maturity**: the personalization ladder built from **all** attributes/tags/lists/events;
    `provenance` (SDK/API, contact/device, cadence) exploited; **data-readiness evaluated for
    every recommended lever**.
  - **Recommendations**: **all** `gaps` (present/partial/missing) and **all**
    `conversionSignals` turned into pillar-tagged items.
  - **Data foundation**: every axis of `foundation_scorecard` (breadth, SDK/API, storage,
    lists/tags, coverage, value/currency instrumentation).
- **The mandatory structure is MANDATORY — never condense it.** Every report ships every
  `gate_required` section in `canonical_sections.py` (see "Report structure" below). Do **not**
  merge several deep-dives into one "condensed" section. If a mandatory section's data is
  unavailable on this account (inactive channel, firehose / aggregate-only push, sampled
  events), **keep the section and mark it N/A** with the reason + how to enable — never drop
  it. This is enforced by the delivery gate: `scripts/verify_report.py` FAILS a report with
  too few canonical sections.
- **The optional sections are genuinely optional.** `channels_exp`, `best_practices`,
  `delivery_shape`, `detected`, `inapp`, `email_program`, `data_foundation` and the three data
  appendices ship when they have something account-specific to say, and are omitted otherwise.
  Omitting one is a decision, not a regression — an N/A block wearing a section number costs
  the reader a click and tells them nothing. `optional` in `canonical_sections.py` is the
  record of which is which.
- **Build on the shared framework — do NOT write a builder from scratch.** New client
  builders MUST start from `scripts/build_report_template.py` (`cp` it to
  `work/<client>/build_report.py`) and drive structure from
  `scripts/canonical_sections.py` via `scripts/report_framework.py`. The scaffold ships
  **every** canonical section from the first run (un-filled sections render a labelled
  `N/A (reason)` block instead of vanishing), so structural completeness is guaranteed by
  construction, not vigilance. `canonical_sections.py` is the **single source of truth** for
  the section spine — shared by the builder and the gate, so they can never drift. Writing a
  bespoke section list by hand is deprecated (the two pre-framework builders remain valid
  reference skeletons, but new work uses the template).
- **Charts fail loudly; the gate runs at build time.** Emit charts with
  `report_framework.chart(id, ...)` — it raises `MissingChartError` if the spec/PNG is
  missing, so a chart can never silently drop. `report_framework.write_report(...)` runs
  `verify_report` as a **blocking** step (raises `BuildGateError` on FAIL); only bypass with
  an explicit `--no-gate`. Read audit fields through `report_framework.aget("a.b.c")` so a
  stale/partial `audit.json` degrades one section to N/A instead of crashing the whole build.
- **Visuals are mandatory, not optional.** Every report MUST render **interactive charts**
  (Chart.js canvas + PNG fallback, from `make_charts.py` with `include_charts=True`) **and
  decoded message creatives** (push / Message Center previews). This is enforced by the
  delivery gate `scripts/verify_report.py` (workflow step 15 / Quality gate) — a report that
  fails it is not deliverable. A custom builder that hard-codes `include_charts=False` or
  omits the creatives section is a defect, not a shortcut.
- **Creatives are CURATED, not exhaustive — preview only messages that MATTER to the client.**
  Decode broadly (to classify campaigns), but only turn a message into a *preview* when it is
  **important**: an **automated / recurring program** (`pergroup` journey/trigger), a **large
  send** (top broadcasts by delivery volume), or a **strong performer** (best direct/influenced
  response rate vs the client's own same-type baseline). **Channel priority: push → Message
  Center → email** (then SMS / in-app only if material). Aim for ~**4–8 curated previews**, each
  captioned with the **objective reason it was picked** (e.g. "top automated program",
  "largest broadcast", "best CTR"). **Never** showcase a message just because its body happened
  to be decodable — skip tiny one-offs, internal tests and seed sends *for their own sake*. On
  **firehose accounts** a creative may only be recoverable from a **seed/test send**; use it
  **only** when it is the creative of an important campaign/program, map it to that program, and
  label it as captured from the campaign (not as a standalone message). Selection is part of the
  methodology and must be stated in the creatives section.

## Workflow
> **Ordering.** Step 1 (brand research) needs no project data and gates nothing —
> **launch it as a background subagent FIRST** and run steps 2–3 while it works. It runs to
> a fixed budget (**10 searches, 6 fetches, 12 sources, one pass**) against a fixed schema,
> so it finishes inside collection instead of becoming the critical path on an account whose
> collection is minutes rather than an hour. Do not raise the budget. Step 1b
> (shape probe) costs ~8 seconds and **decides how the whole push analysis is done**, so run
> it before committing to any collection strategy.
```
- [ ] 1. Brand & business context (web search, cite URLs) + confirm INDUSTRY
       (load benchmarks.md, match industry key for later comparison);
       delegate it to **ONE** `airship-brand-research` agent, **one pass**, which fills a
       fixed `brand.json` schema to a fixed source budget and ends on
       `check_brand.py work/<client>/brand.json` — do not hand it a widened brief, and
       never fan this wave out across sub-topics: with no output shape to fill, it becomes
       twenty agents inventing and reconciling a structure;
       fetch the REAL app icon (render_mocks.fetch_app_icon) for push previews.
       Resolve the industry to a benchmark vertical MECHANICALLY, don't eyeball it:
       `resolve_vertical.resolve("<industry>")` → key + `proxy` flag + a `disclose`
       sentence. When `proxy` is True (e.g. telecom → Utility & Productivity, since
       Airship publishes no telecom vertical), **print that sentence in the report**
       under the benchmark section — never imply an exact peer match.
- [ ] 1b. **Probe the push account shape (do this BEFORE any push collection):**
       `python scripts/push_firehose.py probe "<MCP project>" <start> <end>` →
       `dashboard` (standard per-push path) | `firehose_grouped` (roll up by program via
       `pergroup/detail`, reference.md 1b) | `firehose_groupless` (external orchestrator
       calling /api/push per contact, NO group layer, but a KNOWN and modest daily count —
       exhaustive time-partitioned enumeration + rebuild the taxonomy from the tag namespace,
       reference.md 1c) | `firehose_unattributed` (no group layer AND not sizeable — do NOT
       enumerate: volume from `/api/reports/sends`, inventory from the hour-tiled activity
       log, typology from a sends-weighted sample, each with its coverage stated).
       Getting this wrong wastes the whole collection phase.
- [ ] 1c. **(OPTIONAL) Tagging-plan audit pre-step** — if a data-collection audit was
       supplied, load it via `scripts/data_foundation.py`:
       `data_foundation.load(analysis_path=…, inventory_path=…)` OR
       `data_foundation.load(raw_path="audit.json", vertical="<industry>")` (runs the
       VENDORED `parse_tagging_plan.py` + `analyze_tagging_plan.py` in this skill's
       `scripts/`; `$TAGGING_PLAN_SKILL_DIR` still overrides the location if ever needed).
       Returns an `audit` dict with `available` (False ⇒ skip every enrichment, report
       unchanged). Carry `audit` into steps 4b, 7 and the Data-foundation section. Process
       the audit **in full** (all events/attributes/tags/lists/screens — no top-N).
       If none was supplied, offer the capture app ONCE (repo link + 4 steps, see Inputs →
       "Tagging-plan data-collection audit"), then continue the review without it.
- [ ] 2. **Collect with the shared collector — do NOT hand-write a `collect*.py`:**
       `python scripts/collect.py "<MCP project>" --start <start> --end <end>
       --out work/<client>/data` (add `--shape` from step 1b to skip the re-probe).
       It runs steps 2, 3, 3b and 6's fetching in one resumable pass and writes
       `data/collect_manifest.json` (files, rows, pages, API calls, elapsed, coverage) —
       cite THAT for coverage instead of asserting it. Delegate the run to a `shell`
       subagent: it is a script, not reasoning. Re-run freely; completed stages are
       skipped unless `--force`. Account-specific extras go in a `collect_hook.py`
       (`--hook`) — never a forked collector.
       What it guarantees (and what you must preserve if you ever collect by hand):
       core data = sends (**per-channel, DAILY**), opens, optins, optouts, devices
       (separate SNAPSHOT/whole-base from PERIOD metrics). **Single daily-range pull, sliced
       in code — not two windowed pulls.** sends/opens/optins/optouts ONCE over the
       **doubled window** (current + immediately-preceding equal window, `precision=DAILY`),
       split into current vs prior in code to power the intro KPI deltas (4 calls, not 8).
       `/devices` stays a point-in-time snapshot (no prior; label "(snapshot)")
- [ ] 2b. **Channel detection & per-channel activity (mandatory FIRST):**
       `channel_activity.channel_summary(sends_rows, devices, events)` → enumerate EVERY
       active channel from `/sends` volume (catches email/SMS even when `/devices` opted_in=0
       — a common trap), attach reachable base, the **email funnel from standard events**,
       and a per-channel **automated-vs-one-shot cadence** signal. This drives the
       per-channel campaign sections below.
- [ ] 3. Pull events (ALL pages) + **activity log (ALL pages)** + responses/list across the
       WHOLE period (paginate every next_page on all three; sample only with stated coverage;
       responses/list is PUSH-ONLY; activity log is the one-shot/broadcast inventory — see
       reference.md → "Activity log"); rank PUSH tops by RATE not just volume; keep channels
       SILOED (push/email/SMS/in-app); fetch creatives by send type — download push hero
       images + render with the real app logo.
       **De-duplicate on `push_uuid`** — the API's `end` bound is INCLUSIVE, so contiguous
       windows overlap and silently inflate volume (see reference.md → "Time-window quirks").
- [ ] 3c. **Reconcile the two send counters (mandatory whenever both are quoted).**
       `/api/reports/sends` counts ALERTING pushes; `responses/list` also counts SILENT
       data-only ones. Measure the split and explain the gap, or the report contradicts
       itself: `push_firehose.sample_split(...)` then `push_firehose.reconcile(...)`.
       `/api/reports/sends` is AUTHORITATIVE for volume KPIs. `sample_split` also runs drift
       detection — **if the sampled rate is unstable across the window, report the trend and
       its breakpoint, never the blended mean** (a regime change is usually the real finding).
- [ ] 3b. Merge push inventories: `activity_log.merge_push_inventories(responses, activities)`
       → feed **`merged`** into classify + push-program analysis; surface **`activity_only`**
       broadcasts in reach ranking (pull `perpush/detail` for each)
- [ ] 4. Classify campaigns one-shot vs automated/recurring — on the **merged** push inventory
       (activity log + responses/list → `merge_push_inventories`, then classify_campaigns.py;
       NO /pipelines, NO /schedules)
- [ ] 4a. **Build the CANONICAL multi-channel inventory** (scripts/campaign_inventory.py):
       `build_inventory(push_campaigns=…, email_sms_campaigns=…, events=…)` unifies every
       channel into ONE list — **MESSAGE-FIRST** (push / Message Center / email / SMS are the
       PRIMARY, decodable messages) **COMPLEMENTED** by in-app / MC CTA signals extracted from
       `/events` (`in_app_message`, `in_app_pager`, `ua_mcrap`, `banner - …` customs) tagged
       `source:"cta_only"`. **NO lossy drops** — a min-volume floor is DISPLAY-only
       (       `bucket_long_tail`), never an exclusion. Also call `split_events(events)` → feed the
       **behavioural** `location:custom` half to step 7 and the in-app campaign half here.
       **Watch for campaign-MARKER events.** Some firehose accounts (where per-message push
       is aggregate-only) log each push / push+in-app / journey campaign as a
       `location:custom` MARKER event, e.g. a grocery retailer’s `push - …`, `p+i - …` and
       `scene - …` (Airship Scene/Journey). These are CAMPAIGNS, not behaviour: turn them
       into MESSAGE-based `push_campaigns` (real campaign identity → name-basis, up to High
       reliability; infer `automated_recurring` from markers like rfm/primo/relance/aban/
       trigger/scene, else `ambiguous` batch-tactical) and pass them to `build_inventory`,
       AND add their prefixes to `exclude_name_prefixes` in step 7 so they don’t pollute the
       conversion taxonomy. Their `count` is a reach/impression proxy (label it as such — it
       is NOT the platform send count). This is what surfaces the account’s real lifecycle/
       onboarding automation instead of showing 0% coverage.
- [ ] 4c. **Client categories — read them BEFORE 4b** (scripts/campaign_categories.py).
       Clients tag sends with `campaigns.categories` for their own reporting: an external
       classification, already in the decoded `pushbody` cache (no extra call).
       `campaign_categories.py prepare work/<client>` infers the scheme deterministically
       (facets, positional codes, `key:value`, free labels; locale / channel / date / id
       positions; multilingual lexicon) and writes `category_schema.json`; when it says
       `available=False` (under 20 % of decoded sends, or no reusable taxonomy) skip the
       rest — nothing changes. Otherwise a **frontier** model reads the scheme
       (`prompts/categories.md` → `category_hypotheses.json`, then `validate`). Every
       reading, lexicon or model, is then TESTED — lexical fit, agreement with the name
       classification (echoes excluded), behaviour vs the lever's expected typology,
       position, support — and gets a confidence. **High** (≥ 0.70) may replace a weak name
       match; **Medium** (≥ 0.45) only classifies a campaign the name left unclassified;
       **Low** stays in the appendix. Step 4b then runs through
       `campaign_categories.enrich(...)`, which returns `audit.purpose` (enriched) and
       `audit.categories` (scheme, hypotheses, per-category performance, name/category
       alignment, vendor clues, what was reclassified).
- [ ] 4b. **Campaign PURPOSE / pillar classification & playbook** (scripts/campaign_purpose.py) —
       one pass over the canonical inventory (fold classify + purpose together): map each item
       (ALL channels) to a strategic PILLAR + standard LEVER — **language-aware, high-recall**:
       detect FR/EN, match `campaign_playbook.json` bilingual aliases with **stemming +
       shared-prefix tolerance** so a broad (possibly imperfect) association beats missing a
       probable one. Name-first, **content fallback** = decoded pushbody notif text / MC HTML
       (`bodies=`; reuse the decode-once cache, never the Content API). Every mapping carries a
       numeric **`reliability` (0-1)** + High/Medium/Low = match score × basis (message name >
       body > `cta_only`) × source — surface it (pill/column via `report_interactive.reliability_pill`).
       Then compute per-pillar MATURITY (coverage of vertical-recommended levers at
       reliability ≥ 0.45 + automation share), the one-shot→automated INDUSTRIALIZATION mix,
       and RECOMMENDED new campaigns tailored to the brand+vertical
       (`campaign_categories.enrich(campaigns, vertical, bodies, decoded, groups_decoded,
       hypotheses, reachable)` — it wraps `campaign_purpose.analyze` and adds the category
       signal of step 4c; identical output when the categories are unusable).
       **If an audit is available**, annotate the recommendations with data-readiness
       (`data_foundation.annotate_recommendations(recos, audit)` → activatable-now levers
       first) and build the personalization ladder from real tracked data
       (`data_foundation.personalization_ladder_from_audit(audit, lang)`; fallback to the
       data-present heuristic when absent).
- [ ] 5. Experiments — REPORTS ONLY: detect via push_type == A_B in responses/list and pull
       experiment reports if present; do NOT call /api/experiments
- [ ] 6. Decode creatives from Reports only (`perpush/pushbody` for mass sends; UNICAST →
       metadata/categories from pushbody when present, illustrative fallback when body empty).
       **DECODE ONCE** — keep a single `push_id → decoded body` cache and reuse it everywhere
       (purpose content-fallback, MC HTML, creatives, deep-link `__ui_id`, UNICAST category
       recovery); never decode the same `pushbody` in multiple steps.
- [ ] 7. Custom-event contextualisation & conversion KPIs (scripts/event_analysis.py:
       analyze(events, vertical, brand, region, country, currency) → taxonomy, conversion
       KPIs w/ direct/indirect/unattributed split, monetary value + currency, opportunities).
       **Scope = behavioural `location:custom` only** — feed the behavioural half from
       `campaign_inventory.split_events(...)`; `analyze` already drops `banner - …` campaign
       impressions (`exclude_name_prefixes`). `in_app_message`/`in_app_pager`/`ua_mcrap` are
       campaign engagement (step 4a), NOT conversion taxonomy.
       **If an audit is available**, pass `audit_value_index=data_foundation.value_index(audit)`
       to `analyze(...)` so the "enrich value" verdict becomes a FACT (the tagging plan knows
       whether an event already carries an amount/value property), and cross-reference each
       conversion KPI with `data_foundation.cross_reference_conversion(analysis["events"], audit)`
       (per-KPI value/currency backing + conversion events tracked-but-not-fired in the window).
       IF conversion KPIs found → per-campaign attribution via events/summary/perpush|pergroup
       (scripts/event_attribution.py: attribute_campaigns). For Email/SMS top messages:
       performance comes from perpush/detail (top-level sends/direct_responses/
       influenced_responses), NOT responses/list or the activity log
- [ ] 8. Recover categories for UNICAST sends (best-effort, from perpush bodies)
- [ ] 9. Aggregate to JSON; compute totals/averages/peaks/attribution; build the
       account profile & Airship-adoption scorecard (channels + feature use from
       decoded pushbodies) and the conversion funnel + attribution rate
- [ ] 10. Generate charts (scripts/airship_charts.py: PNG + Chart.js spec emitters for the
       high-value ones); build benchmark gauges + best-practice scorecard
       (scripts/report_interactive.py: gauge/verdict)
- [ ] 11. Creatives — **curate ~4–8 IMPORTANT messages only** (automated/recurring programs,
       top-volume broadcasts, rate leaders), channel priority **push → Message Center → email**;
       skip tiny one-offs / tests / seed sends unless a seed IS the creative of an important
       campaign. Real push (render_mocks: hero image + real app_icon) + real email/MC
       (render_email.py at phone width + max_height) → reconstruct only as fallback.
       In HTML: creative_push_preview() for pushes, creative_mc_preview() for Message Center
       (never embed a full-scroll MC PNG raw — clip to one phone screen); caption each with its
       objective selection reason.
- [ ] 12. Resolve deep-links: composer id = options.__ui_id from the decoded
       perpush/pushbody, app_key from perpush/detail (scripts/report_interactive.py:
       composer_id_from_pushbody + flight_deck_url) — for every analysed message
- [ ] 13. Build the INTERACTIVE HTML report. **Start from the canonical scaffold**:
       `cp scripts/build_report_template.py work/<client>/build_report.py`, then fill each
       `renderers[...]` stub. Structure comes from `canonical_sections.py`; assembly, cover,
       bilingual toggle, brand CSS, loud-fail `chart()` and the auto-gate come from
       `report_framework.py` (never hand-roll a section list). Underlying scaffold =
       report_interactive.py (dashboard layout: fixed sidebar w/ auto TOC + scroll-spy,
       Download-PDF (only when a PDF is built), Expand/Collapse-all; full-width fluid content
       column that fills the viewport left of the sidebar — prose, callouts, KPI bands, charts,
       tables and card grids ALL span the same full card width, soft-capped ~2100px; tooltips,
       collapsibles, gauges; kpi_card()/hero_kpi_band()/priority_cards() auto-render a slides-style
       brand pictogram — keyword-mapped from the KPI/card label, or pass `icon="<name>"` (from
       scripts/assets/icons/light-bg) / `icon=False` to override; searchable/sortable/exportable
       tables; Flight Deck buttons; interactive_chart canvases w/ PNG fallback + CSV export).
       Layout lives entirely in INTERACTIVE_CSS (screen) + FRAMEWORK_CSS; @media print is
       untouched so the paginated PDF is unchanged. `write_report` runs the gate before it
       succeeds. **The PDF is opt-in**: the HTML is the deliverable, so build with `--pdf`
       (→ `fw.set_pdf(True)`) only when a PDF is actually wanted, then convert from the same
       HTML (scripts/build_report.py). Every chart keeps its print PNG either way, so adding
       the PDF later needs no rebuild. No PNG deliverable.
- [ ] 14. Deliver: passing `client=CLIENT` to `write_report` already dropped
       `~/Downloads/<Client>_Engagement_Review_<YYYY-MM-DD>.html` once the gate passed (the
       builder scaffolds it) — if a PDF was requested, put it in the same folder; then summarize.
       The gate proves the report is complete and self-consistent; it cannot prove anyone
       agreed with its verdicts, so read it before it reaches a client
- [ ] 15. **VERIFY (delivery gate) — never skip.** Run
       `python scripts/verify_report.py work/<client>/report.html` and fix every ✗ before
       delivering. It FAILS the report when (a) the **full canonical section set** is not present
       (a condensed / merged-away report), (b) **interactive charts** are missing, or (c)
       **message creatives** are missing — the three things that have silently gone missing.
       A custom `build_report.py` MUST therefore (a) generate charts via `make_charts.py` and
       pass `include_charts=True` to `interactive_head(...)`, and (b) render decoded push/MC
       creatives. If an account genuinely has nothing decodable, add a **labelled illustrative /
       limitation creatives block** and re-run with `--allow-no-creatives` (never ship with an
       empty creatives section and no explanation).
ONLY the Reports API is allowed: `/api/reports/*` (scope `rpt`). Never call `/api/content/*`.
Every figure → source endpoint; every insight/reco → origin tag + confidence level.
```

## Step details

### 1. Brand & business context (do FIRST; drives insights)
Web-search the brand: sector, app role, audience/geos & languages, offers/loyalty,
**seasonality/key moments**, recent news, competitors. Collect source URLs.
Cross-reference data spikes with brand events. Tag every insight/reco origin:
`[Data]`, `[Brand context]`, or `[Data+Context]`. Separate measured fact from
contextual hypothesis.

**This step has a budget, and the budget is in the agent.** `airship-brand-research`
researches to a fixed `brand.json` schema under a ceiling of **10 web searches, 6 page
fetches, 12 sources and one pass**, then stops — it does not keep improving a field it has
already filled. The ceiling is set by what the deliverable consumes, which is less than it
looks: §1's narrative, the 3–4 priority cards in §3c, the brand-adapted column of §7b, the
rewritten new-campaign proposals in §16, and the tagged contextual sentences elsewhere.
Nothing in the pipeline parses `brand.json` on a mode A run — no script reads it, no gate
check inspects it — so an unread paragraph costs authoring tokens and buys no reader. If a
section later needs a brand fact the schema does not carry, **add the field and re-run the
one agent**; do not brief it to research broadly on the chance that something is useful.

The fields with the highest return are the two no script can infer:
`not_applicable_archetypes` and `not_applicable_attributes`. A vertical is a coarse
instrument, so the goal engine will recommend instrumenting a purchase on a free
ad-supported service unless the research says the business cannot have one.

**Determine the client's industry** here: deduce it from the brand research, then
**confirm it with the user**. Load [benchmarks.md](benchmarks.md) and select the
matching industry key (via its `aliases`); carry it into the benchmarking step. If no
industry matches, note it and skip benchmark comparisons (don't force a mismatched one).
The industry key also selects the **event catalog** vertical (`event_catalog.json`
`vertical_map`, fallback `all_verticals`) for custom-event classification. Note the brand's
**country/region** too → the **probable currency** for reading event `value` as an amount
(`event_analysis.currency_for_brand`; state it as an assumption, let the user override).
**Fetch the real app icon here too** (for realistic push previews): call
`render_mocks.fetch_app_icon("<App/brand name>", "creatives/app_icon.png", country="<store cc>")`
— iOS App Store (iTunes Search API) by name, or Google Play `og:image` when you pass a
package id. Carry the returned path into every `render_push(...)` as `app_icon=`. If it
returns None, note the source was unavailable and fall back to the colored accent tile;
the user may also override with a known store URL / package id.

### 2-3. Data collection (Airship Reports API)
Call via MCP `call_airship_api`. Endpoints, params and definitions: see
[reference.md](reference.md). Key points:
- Paginate **all** pages of `/events`. Use **`precision=DAILY`**: the response is a flat
  aggregate with no date column and `precision` decides how the API buckets the window
  *before* aggregating, so **MONTHLY snaps the window out to whole months**. Measured on a
  streaming account, a 28/06→27/07 request at MONTHLY returned **11 event names that never fired
  inside the window** — they would inflate the conversion taxonomy and the "tracked but not
  fired" cross-reference. `collect.py` writes the exact-window set to `events.json` and keeps
  the monthly superset, clearly labelled, as `events_monthly.json`.
- **Activity log (required):** paginate **all** pages of
  `GET /api/reports/activity/details?start=…&end=…&limit=100` — follow every `next_page`
  URL until exhausted. This is the Flight Deck-aligned inventory of **non-unicast** pushes
  (broadcasts, segments, A/B, `GROUP` program lines) and is the best source for **one-shot
  campaigns** that a sampled `responses/list` pull can miss. Merge with `responses/list` via
  `scripts/activity_log.py` → `merge_push_inventories(...)` before classification.
- For top campaigns, use `responses/list` on peak-send days (iterate `next_page`) and read
  each campaign's `push_type`. **Also** rank marquee sends from the activity log
  (`one_shot_broadcast_candidates(...)` or sort merged `activity_only` by delivery sends).
- **Creative retrieval — Reports API only** (full table in `reference.md`):
  - **Selection gate (decide BEFORE rendering).** A message earns a preview only if it is
    **important to the client**: (1) an **automated / recurring program** (`pergroup`
    journey/trigger campaign), (2) a **top send by delivery volume** (marquee broadcast), or
    (3) a **rate leader** (best direct/influenced response vs the client's same-type baseline).
    Preview in **channel-priority order: push → Message Center → email** (SMS / in-app only if
    material). Curate ~**4–8** previews, each captioned with its objective selection reason.
    Do **not** preview tiny one-offs, internal tests or seed sends on their own — on firehose
    accounts a seed/test send is acceptable **only** as the recovered creative of an important
    campaign (map it to that program and say so).
  - **BROADCAST / SEGMENTS / A-B** → `GET /api/reports/perpush/pushbody/{push_id}`
    (`push_id` is a **path** param). Returns notif text + Message Center / email HTML when
    present in the push payload.
  - **UNICAST / Create-and-Send** → per-push body is usually **empty** (no notif HTML).
    Still call `pushbody` for **`options.message_name`**, `campaigns.categories`, and any
    metadata — but **do not** call the Content API for template HTML. When no creative is
    recoverable from Reports, use an **illustrative reconstruction** (clearly labelled).
  - Render real HTML from pushbody with `scripts/render_email.py`; reconstruct with
    `scripts/render_mocks.py` only when pushbody returns no usable content.
  - **Push hero image (rich push) — download it and preview WITH the image.** The decoded
    pushbody carries the image URL at `notification.ios.media_attachment.url` and/or
    `notification.android.style.big_picture`. **Always** `render_mocks.fetch_media(url, path)`
    it and render the notification WITH the image via
    `render_mocks.render_push([(time,title,body,tag,image_path)], out)` — a faithful preview,
    NOT a text-only card. A text-only card is a fallback used only when no image URL exists
    or the download fails. Never ship a text-only push mock when a hero image was available.
- **Email/SMS top-message performance: use the per-push report, not the activity log.**
  `responses/list` and `pergroup/detail`'s `platforms` object never break out email/SMS
  (only `amazon`/`android`/`ios`/`web`) and the activity log can show 0/nothing for a real
  email send. Pull `GET /api/reports/perpush/detail/{push_id}` (or `pergroup/detail` for a
  recurring email step) and read its **top-level** fields: `sends` = email sends,
  `direct_responses` = clicks, `influenced_responses` = opens. Only call an email channel
  "inactive"/"0 sends" after confirming **both** `/reports/devices` (email `opted_in`) AND
  `perpush/detail` agree — see `reference.md` → "Email / SMS performance".
- **Use only the Reports API.** Do **not** call `/api/content/templates`, `/api/pipelines`,
  `/api/schedules` or `/api/experiments` — derive campaign typology and experiment
  presence from the Reports API (`responses/list`, activity log) only; never fabricate.
- **Separate SNAPSHOT (whole base) from PERIOD metrics** (see `reference.md` →
  "Scope of measurement"). `devices` = the only source for opt-in **rate** and installed
  base (point-in-time, whole base, tag "(snapshot DD/MM)"). `sends/opens/optins/optouts/
  events` are bounded by the window (tag "(period)"). `optins/optouts` are daily **event
  flows** (include reinstalls/re-detections), NOT a net base change and NOT equal to the
  snapshot `opted_in/opted_out`. Never mix a snapshot figure with a period figure in one KPI.
- Custom event `value` is a client-declared counter/weight, **not currency** — never
  show it as money.

### 4. Analysis

**Full specification: [analysis-spec.md](analysis-spec.md)** — every metric to
compute, how to compute it, and what it means. Read it when running the analysis;
it produces `audit.json`, and everything downstream reads that instead.

The one rule that belongs here rather than there: **derive each metric once, under
an explicit name, in `analyze.py`**. A metric two sections compute independently is
a metric that will be published twice with two different values, and the gate's
numeric check is the only thing that would catch it.
### 5. Charts — `scripts/airship_charts.py`
Import the styled helpers (Airship palette, k/M formatter, dated axes for time series
only, no emoji in labels). See the module docstring for available functions:
stacked daily bars, area+mean line, donut, grouped/h-bars.

**Interactive charts (progressive enhancement).** High-value charts render as an
interactive **Chart.js canvas on screen** and fall back to the deterministic **matplotlib
PNG in the PDF/print** — one HTML file, no CDN (Chart.js is vendored & inlined). For a
chart, emit BOTH from the SAME data: the PNG (existing helper) and a Chart.js spec via the
`spec_*` emitters. Make **every** chart interactive + exportable: dual-axis/time/funnel via
`spec_pressure_fatigue`, `spec_timeseries_stacked`, `spec_funnel`, `spec_program_ranking`;
composition/category/ranked via `spec_donut`, `spec_grouped_bars`, `spec_hbar` (so the
attributed-events, permission-flow, base and opens charts are canvases too, not PNG-only).
Prioritise the charts that carry the most insight: **pressure vs fatigue** (dual axis),
**daily sends stacked by platform**, **conversion funnel**, **program/campaign ranking**
(firehose). Benchmarks stay as the print-safe SVG **gauges** (`gauge()`), not canvases.
`interactive_chart(...)` renders a screen-only **CSV** button that downloads the chart's
source data (auto-derived from the embedded spec — zero extra payload; pass `csv=` only to
override). For rich hovers without JS in the JSON, attach a plain `_extra` array to a
dataset (the mount script appends it to the tooltip).

### 6. Creatives — prefer real, reconstruct only as fallback
**Real creatives (faithful preview)** — when you have actual HTML (`content.html_body`
from a Content Template, or decoded Message Center HTML from a per-push body):
```bash
python scripts/render_email.py creative.html out.png 680
```
For **Message Center / full-screen mobile templates**, render at **phone width** and cap
height so the PNG is one screen, not the full scroll:
```python
from report_interactive import creative_mc_preview
render_email(html, "creatives/mc.png", width=375, max_height=720)
# in the report HTML:
creative_mc_preview(datauri("creatives/mc.png"), "Message Center · …")
```
The viewport clips any remaining tail via CSS (`ir-mc-viewport` + `object-position:top`).
`render_email.py` is hardened for **real Airship email creatives**, which are image-based
(a stack of remote images on the same `dl.asnapieu.com` CDN as push hero images):
- **Pre-downloads every remote `<img>`** and rewrites it to a local `file://` path, so the
  render is deterministic/offline (headless Chrome otherwise skips slow remote images and
  produces a blank strip). Pass raw HTML, a bare filename, or an absolute path — all work.
- **Rendering recipe**: `--headless=new` + `--virtual-time-budget` at **device-scale-factor 1**
  (scale 2 collapses fixed-width email tables to a near-empty page), waits past the budget,
  then **kills the whole Chrome process group** — Chrome usually does not exit on these
  pages, and leaked renderer/gpu children accumulate and blank out later renders.
- **Retries a blank render** with a fresh Chrome + larger budget before giving up, and
  crops **uniform margin bands** (robust to coloured email headers AND dark themes).
If you script it directly, always reap Chrome's children (kill the process group), never
just the parent — a leaked-Chrome pile-up is the #1 cause of intermittent blank renders.

**Real push previews (real hero image AND real app logo)** — when the pushbody has a
`media_attachment`/`big_picture` URL, download it and render the notification WITH the
image, using the **real app icon** resolved in step 1 (real copy + real creative + real
logo, not a reconstruction):
```python
from render_mocks import fetch_media, fetch_app_icon, render_push
icon = fetch_app_icon("<App/brand>", "creatives/app_icon.png", country="<cc>")  # once, in step 1
img  = fetch_media(url, "creatives/hero.jpg")          # None if download fails
render_push([(time, title, body, tag, img)], "creatives/push.png",
            app_name="<App>", app_icon=icon)           # icon=None → colored tile fallback
```
`render_push` accepts a 5th tuple element (hero image path) and an `app_icon=` (real logo).
With them the card shows the real hero image and the real app logo — the default for any
rich push. Reserve text-only cards / the colored tile only when no image / no logo exists.

**Illustrative reconstructions (fallback only)** — when `perpush/pushbody` returns no
usable creative (typical for UNICAST / template-driven sends) and no hero image is available:
```bash
python scripts/render_mocks.py   # render_push() / render_card()
```
Renders iOS lock-screen push and Message Center/in-app cards. Use the client's app
branding inside mockups (it depicts their message), keep the report chrome
Airship-branded, and clearly **label these as "illustrative reconstruction".**

### 7. Deep-links — every analysed message links to Airship Flight Deck
Make each message in the report clickable through to its Flight Deck page. Use
`scripts/report_interactive.py`:
- **composer id** = `options.__ui_id` of the **decoded** `perpush/pushbody/{push_id}` (a
  base64url UUID, **not** the push_id). Get it with `composer_id_from_pushbody(pushbody)`.
- **app_key** = the `app_key` field returned by `perpush/detail`/`pergroup/detail` (no need
  to ask the user).
- Build the URL with `flight_deck_url(app_key, ui_id, region)` (`region` from the MCP env:
  `eu` → `go-admin.airship.eu`, else `.com`) and render a button via `flight_deck_button(url)`.
- **Availability**: only messages **composed in the dashboard** (BROADCAST/SEGMENTS/A-B,
  non-empty pushbody) expose `__ui_id`. **UNICAST/API sends have an empty body → no
  deep-link**; render the muted "no deep-link" pill instead of inventing a URL.

### 8. Build the interactive report — `scripts/report_interactive.py` + `scripts/build_report.py`
The deliverable is a **single self-contained interactive HTML** file (assets embedded as
base64) that renders as a **web-app on screen** (fixed sidebar + fluid full-width content
column). The *same* file can print to a **paginated PDF companion** — built only when asked
for (`--pdf`), since the HTML is what ships.

**Design system — Airship 2026 brand (use it; do not hand-roll colours/fonts).**
The look is derived from the *AIRSHIP 2026 Master* deck + airship.com. `report_interactive.py`
centralises it — always build on these instead of literal hexes / system fonts:
- **`brand_report_css()`** → the shared base stylesheet (page geometry, typography, `.grid`
  tables, `.note`/`.note-up`/`.note-warn`, `.tag`, `.pill*`, `.two-col`, `:root` tokens).
  Set your report's `REPORT_CSS = ri.brand_report_css() + "…report-specific…"`. The
  report-specific tail should reference the CSS vars, **never** raw brand hexes.
- **Fonts are auto-embedded** by `interactive_head()` (it prepends `brand_fonts_css()` — base64
  woff2 in `scripts/assets/brand_fonts.css`): **Zalando Sans Expanded** (display/headings, via
  `var(--font-display)`), **Instrument Sans** (body/UI, `var(--font-sans)`), **Geist Mono**
  (code/tags, `var(--font-mono)`). No network fetch; offline-safe in the PDF.
- **Palette tokens** (in `:root`, also `report_interactive.BRAND`): `--ink #000818`,
  `--blue/--accent #056DFF` (primary), `--navy/--indigo #030869`, `--teal/--mint #11DBC0`
  (positive signal), `--coral #E4626F` (negative signal — opt-out/churn), `--sky #7ABFFF`,
  `--lightblue #DCEAFF`, `--lime #E6F55A`, `--grey #717680`, `--panel #F7F8F8`, `--line #E9EAEB`.
  Chart colours come from the same palette (`airship_charts.py`): primary series **blue**,
  secondary **navy/teal/sky/lime**, opt-out/negative **coral**. `interactive_head` sidebar shows
  the real **white Airship logo**; use `brand_logo(variant)` (`white`/`ink`/`mark_blue`/`mark_white`)
  and `brand_asset_datauri("airship_mark_blue.png")` on the cover.
- **Cover**: dark ink→navy→blue gradient, white logo top-left, display-font title with a teal
  accent bar, faint blue diamond mark watermark, KPI band at the bottom (see any recent report's
  `.page.cover` block for the pattern).
- Write `report.html` using the report chrome CSS **plus** the interactive scaffold from
  `report_interactive.interactive_head(pdf_filename=..., layout="dashboard", lang=...)`
  (**pass `lang` — "en" default / "fr" — so the sidebar, buttons, search box, CSV button and
  KPI modal localise; it also injects `window.IR_I18N`**) (returns
  `css_block`, `nav_block`, `js_block`): put `css_block` in `<head>`, `nav_block` at the top
  of `<body>` (it opens the sidebar + the fluid `.ir-main` column), and `js_block` at the end
  of `<body>` (it closes `.ir-main` then loads the scripts). Existing call sites keep working —
  the content just gets wrapped in the main column.
- **Screen vs print are the same DOM.** The scaffold's `@media screen` rules turn the fixed
  A4 `.page` boxes into fluid reading cards, add the sidebar (auto TOC + scroll-spy, Download-
  PDF, Expand/Collapse-all), enlarge type and hide PDF-only chrome; `@media print` hides the
  sidebar and restores the paginated pages. `brand_report_css()` already sets
  `@page{size:1240px 1754px;margin:0}` and `.page{width:1240px;min-height:1754px}`, plus a
  print rule that starts **each `.page` on a fresh sheet** (`break-before:page`) and lets long
  tables flow across sheets with a repeating `<thead>` — so narrative sections stay **1 `.page`
  = 1 sheet** while the data-appendix tables can legitimately span several sheets (expected;
  don't force them into one). **Do not** hard-set `.page{height:1754px}` (fixed height clips
  long appendix tables); rely on `min-height` from the brand CSS. Screen overrides never leak
  into print.
- Give each report section a `data-toc="Label"` + `id` so the sidebar TOC + scroll-spy
  auto-build (add `data-toc-sub` for a nested/indented entry). Use `tooltip()` for metric
  definitions/benchmark sources, `collapsible()` for long tables / methodology / appendix,
  `gauge()`/`verdict_pill()` for the benchmark & best-practice scorecards.
- **Single-page-app navigation shell (screen-only; additive, print/PDF unaffected).** The
  dashboard scaffold gives every report a modern app feel while keeping continuous scroll:
  - **Reading progress bar** — a thin brand-teal bar fixed to the top of the content column
    (not under the sidebar) fills as you scroll the document.
  - **Back-to-top button** — a round brand button appears bottom-right after ~600px and
    smooth-scrolls to the top (`aria-label`, localised via `IR_I18N.back_to_top`).
  - **Hierarchical "arborescence" sidebar (tree TOC).** The menu reads as a real tree, not a
    flat list:
    - **Collapsible sub-sections** — any `<h3>` subheadings inside a `data-toc` section are
      auto-detected and rendered as an **indented, rail-connected, collapsible** group under
      their parent `<h2>` (a vertical guide line + per-item connector tick; parent gets a chevron
      with a smooth rotation). Sections with no `<h3>` behave exactly as before — just author real
      `<h3>` subheadings to get sub-entries, nothing else to wire.
    - **Thematic eyebrow clusters** — top-level sections are grouped under small uppercase cluster
      labels (Overview / Engagement & pressure / Campaigns & conversion / Playbook & reco /
      Appendix). The mapping is **data-driven** in `canonical_sections.py`
      (`CLUSTERS` + `CLUSTER_OF` + `DEFAULT_CLUSTER`, exposed via `cluster_of()` /
      `clusters_i18n()`); the framework stamps `data-toc-cluster` on each section and emits
      `window.IR_CLUSTERS` (bilingual). To re-cluster for a future client, edit those tables —
      one line per section; unknown/new keys fall back to `DEFAULT_CLUSTER` so they still appear.
      Clusters follow the canonical order (each is a contiguous run → exactly one eyebrow).
    - **Discreet sidebar numbering** — each entry shows a muted number badge parsed from the
      canonical label prefix (`1`, `2b`, `8-10`…) with sub-items as `parent.index` (`2.1`, `2.2`).
      Numbering is **sidebar-only**: the document body / PDF `<h2>`/`<h3>` are never renumbered.
    - **Active trail** — scroll-spy highlights the active `<h3>` and keeps its parent `<h2>`
      marked as the trail; the active group auto-expands (accordion) while others stay collapsed.
    - **Expand-all / Collapse-all** — a SINGLE control at the **top** of the TOC toggles every
      group at once (Expand-all suspends the accordion auto-collapse until Collapse-all). Real
      `<button>`s with `aria-label`; labels localised from `IR_I18N_ALL` (built from `_UI_STRINGS`,
      so they switch with FR/EN, as do the eyebrows and numbers). There is intentionally NO
      duplicate Expand/Collapse control at the sidebar foot (it was removed).
    The pictogram icons and the FR/EN language toggle (relabelling `.ir-toc-lbl` while preserving
    the number badge) are all preserved. **Pictograms are sized for legibility**: sidebar TOC
    icons render at ~21px (whitened for the dark sidebar with a hairline glow that thickens the
    thin line-art); `<h2>` header icons ~30px; hero/KPI-card icons ~32px; priority-card icons
    ~38px — all at full opacity with a light stroke-thickening `drop-shadow` so the line-art
    reads clearly on both the dark sidebar and light cards.
  - **Smooth scrolling + smooth active-highlight transitions** on TOC items.
  All of the above live entirely in `@media screen` (INTERACTIVE_CSS/JS) and carry `no-print`,
  so the headless-Chrome PDF is byte-for-byte unchanged (no progress bar / button in print).
  The scaffold also guards against horizontal scroll behind the fixed sidebar
  (`html,body{overflow-x:hidden}`, `.ir-main{min-width:0;max-width:100%;overflow-x:clip}`,
  `table.grid{max-width:100%}`).
- **Every displayed KPI — in every section, not just the executive summary — uses
  `kpi_card(value, label, formula=…, inputs=…, source=…, sample=…, confidence=…)`**
  instead of a bare `.card`/number: it renders the value + label + a screen-only ⓘ button
  that opens a shared **methodology modal** (formula, inputs *with their values*, source
  endpoint(s), coverage/sample, confidence pill). The modal keeps KPI grids compact on
  screen. Standalone `methodology(...)` blocks can sit under a chart/table where there's room
  (wrap in `collapsible()` to also print them).
- **Tables**: add `class="ir-searchable"` for a filter box and `class="ir-exportable"`
  (+ optional `data-csv-name`) for a "Download CSV" button on key/long tables; keep
  `ir-sortable` (with `th[data-sortable]`) for click-to-sort. All three are screen-only.
- **Raw client data in a table cell carries `data-verbatim`.** Event/attribute sample values
  are quoted exactly as the SDK stored them, so `14.00` must NOT become `14,00` in a French
  report — rewriting it would misreport the payload. `data-verbatim` exempts the cell from the
  localisation lint; the shared `audit_*` helpers already set it. Never "fix" a sample value.

#### Events appendix: names are not evidence
A tracked-event table that stops at *"`added_to_cart` — 11 properties"* proves nothing. It
does not say whether those properties are **usable**, and usability is the whole question:
a clean 7-value enum is segmentable, a 200-distinct free-text blob is not. So the appendix
must show the **collected values**, via `ri.audit_event_properties_table(AUDIT, lang)` next
to `ri.audit_events_table(AUDIT, lang)`. **A `tracked_events` table without an
`event_property_values` table fails the delivery gate.**

Three things the reader must be able to read off the appendix:
1. **Is Airship's reserved `value` field populated?** Three distinct states, never collapsed
   into one em dash: **`€ Amount`** (+ observed min–max and mean) → revenue is attributable;
   **`Counter`** (`value` ∈ {0,1}) → volume only; **`Not populated`** → nothing to attribute,
   which is usually the single highest-value data gap to raise in the recommendations.
2. **What each property actually contains** — inferred type (`enum` / `amount` / `boolean` /
   `date` / `identifier` / `json` / `text`), distinct-value count, and real sample values.
   `text` with a high distinct count on something that ought to be an enum is a finding;
   so is the `inconsistent casing across values` flag, which silently splits segments.
3. **The events that carry nothing.** `analysis["eventProperties"]` lists **every** tracked
   event, including those with no property and no value — a bare counter is a finding, and
   dropping those rows both hides it and under-reports the catalogue. Do not filter the list.

Sample values are truncated to ~38 chars (`_clip`): free-text properties (timestamps, search
queries, serialised JSON) run 60+ chars and would otherwise triple row height and overflow
the PDF page. The point of a sample is the **shape**, not the full string.
- For each chart, emit `interactive_chart(chart_id, png_data_uri, spec, alt=...)` (from
  `report_interactive`) — it drops the PNG as the print/fallback `<img>`, a `<canvas>` that
  the inlined Chart.js upgrades on screen, and a screen-only **CSV** button (auto-derived
  from the spec). `interactive_head(...)` already inlines the vendored Chart.js + mount
  script (pass `include_charts=False` only for a report with no interactive charts). The PDF
  path never depends on the canvas.
- **Creatives page**: push previews via `creative_push_preview(datauri(...), caption)`;
  Message Center / full-screen mobile templates via `creative_mc_preview(datauri(...), caption)`
  — never a bare `<img>` of a full-scroll MC render (2000+ px tall). Pair with
  `render_email(..., width=375, max_height=720)` at generation time.
- `write_report(..., client=CLIENT)` delivers the HTML to **`~/Downloads/`** (macOS
  *Téléchargements* — not `~/Desktop/`) as `<Client>_Engagement_Review_<date>.html`.
- **Only if a PDF was asked for**, build it with `--pdf` and render the companion:
```bash
python work/<client>/build_report.py --pdf     # offers the sidebar download button
python scripts/build_report.py report.html "<Client>_Engagement_Review_<Nd>"
# <Nd> = the actual window, default 30d (e.g. _30d); use the real span if overridden
# -> <name>.pdf (Chrome --print-to-pdf from the same HTML). No PNG.
```
Keep the HTML and the PDF in the **same folder** so the in-report "Download PDF" button
resolves.
