---
name: airship-engagement-review
description: >-
  Client-ready mobile activity & engagement review of an Airship project, as an
  interactive self-contained HTML report (optional PDF companion). Covers sends, opens,
  opt-ins, devices, events, campaigns, conversion KPIs and marketing pressure vs
  benchmarks, and deep-links every analysed message to Flight Deck. Optionally ingests
  the client's RTDS data-collection audit / tagging-plan .json (parsing and analysis are
  built in) to enrich conversion, maturity and recommendations with the real tracked
  taxonomy. Use for an Airship engagement or activity review, a mobile push/in-app
  report, a CSM/AM account review, or to analyse a tagging plan / plan de taggage /
  data-collection audit .json.
  ALSO provides a lighter mode B, the "Goals review": a fully offline conversion analysis
  from the tagging plan plus brand research, with no Reports API call, saying which
  Airship Goals to configure today and which funnel stages cannot be measured at all.
  Trigger mode B on "revue goals", "goals review", "analyse light", "quels goals
  configurer", "what should we configure as goals", "conversion review of the tagging
  plan".
  ALSO provides an option orthogonal to both modes, the NotebookLM source library: a
  deterministic packager that turns an account's collected data into markdown sources to
  upload into Gemini Notebook Enterprise and dig into the data there. Trigger it on
  "bibliothèque de sources", "source pack", "notebook lm", "notebooklm", "sources pour un
  notebook", "creuser la donnée du compte".
icon: book-open
color: blue
---

# Airship Engagement Review

> **Launch this as a Custom Mode** (Option+Enter on Mac, Alt+Enter on Windows) rather than
> with `/airship-engagement-review`. A full review runs for hours across dozens of turns;
> invoked on a single message these instructions drop out of context as the window compacts,
> and the first symptom is a thin section written from memory. A Custom Mode stays in context
> for the whole session.

## Two modes — pick one before you start

| | **Mode A — Full engagement review** (default) | **Mode B — Goals review** (light) |
|---|---|---|
| Question it answers | How is this client using Airship, and how well is it working? | What should this client configure as Goals, and what can it not measure at all? |
| Inputs | Reports API (MCP) + optional tagging-plan JSON | Tagging-plan JSON + web research **only** |
| API calls | Many | **None** |
| Output | `report.html` (+ PDF companion on `--pdf`) | `goals_review.html`, **no PDF** |
| Delivered to | `~/Downloads/<Client>_Engagement_Review_<date>.html` | `~/Downloads/<Client>_Goals_Review_<date>.html` |
| Language | **One** language, EN or FR (ask the user); bilingual is opt-in | **English only** — never ask |
| Sections | 25 available, 14 mandatory | 12 |
| Gate | `verify_report.py` | `verify_report.py --profile goals` |
| Working dir | `work/<client>/` | `work/<client>/goals/` |

### Option — NotebookLM source library

Orthogonal to both modes, and not a mode C: `build_source_pack.py` turns whatever a run
has already collected into a folder of markdown sources for Gemini Notebook Enterprise,
so a team can **interrogate the account's data** rather than re-read the report's
conclusions. Deterministic — no model, no API call, no section, no verdict. It ships the
account's data together with the semantics that make it interpretable (endpoints,
denominators, forbidden inferences, sector references), because a pack of figures alone
produces a notebook that invents definitions. Bulk inventories ship in full but in their
own `9x` annex documents, so they can be deselected for a strategy question and selected
for a counting one. The delivered report ships too, as `99_rapport_engagement.md` — the
one source that concludes, kept separate precisely so it comes off in one click. Because
the pack needs both `report.html` and the raw pulls that a passing gate deletes, **build
the last report with `--keep-raw` before packing**. Tagging-plan **sample values ship
unredacted by default** (private internal notebook); `--no-samples` restores the
redacted pack. **Building it is opt-in; ASKING whether to build it is not** — see Inputs,
because the answer has to arrive before the first build and a user who does not know the
option exists will never volunteer it. See [source-pack.md](source-pack.md).

**Client data never enters the repository.** `work/` is git-ignored: every tagging plan,
API pull and generated report stays local, and the finished report is delivered to
`~/Downloads`. The skill itself must stay client-agnostic — when a real account teaches
a lesson worth keeping, record the mechanism ("on a telecom account", "on a streaming
account"), never the client name, the app or its numbers.

Mode A is the default and remains the main action. Choose mode B **only on explicit
intent** ("revue goals", "goals review", "analyse light", "quels goals configurer",
"what to configure as goals"). If the user asks for an engagement review and merely
mentions goals in passing, that is still mode A.

Everything below describes **mode A** unless a heading says otherwise; mode B has its
own workflow block, [Mode B — Goals review (light)](#mode-b--goals-review-light).
The data-exhaustiveness contract applies to both — mode B is light because it reads one
file, not because it samples it.

Produce a complete, visual, sourced review of an Airship project's mobile activity
for a CSM/AM. Every figure carries a source (endpoint) and, where useful, a definition.
Never fabricate data; label unavailable data and mark reconstructed visuals as
"illustrative reconstruction".

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

## Prerequisite — configure the client project as an MCP server in Cursor

Every review reads its data through a per-client MCP server, created once per
project. **Setup: [setup-mcp.md](setup-mcp.md)** (OAuth credentials, the Cursor
config entry, a connectivity check, and the naming convention).

Two things that bite later if missed: the server is **local** — cloud subagents and
Automations read MCP from the team configuration, so collection cannot run there —
and the credentials are per project, so a review pointed at the wrong server
produces a plausible report about the wrong account.
## Prerequisite — auth token & scopes (do this FIRST)
Before any data collection, the project's MCP server must authenticate with an Airship
auth token (OAuth client) that carries the **`rpt` (Reports) scope**. This skill calls
**only the Reports API** (`/api/reports/*`), so create the token in the Airship dashboard
(Settings → OAuth) with **exactly this scope**:
- **`rpt`** — Reports API (`/api/reports/*`): sends, opens, optins, optouts, devices,
  events, activity log, responses/list, perpush/pergroup, experiments (report endpoints).
  **Required** — the review cannot run without it.

**Do NOT call** the Content API (`/api/content/templates`, scope `tpl`), Pipelines
(`/api/pipelines`), Schedules (`/api/schedules`), or Experiments management
(`/api/experiments`). They are out of scope. Derive campaign typology and experiment
presence from the Reports API only (see Analysis).

If a call returns **401 `Expired token`**, ask the user to re-authenticate the MCP server
in Cursor settings, then retry. If it returns **401 `Missing required scope`**, add **`rpt`**
on the OAuth client and reconnect.

## Inputs (confirm first)
- **MCP server** for the project (e.g. `user-XX PROD`). Tool: `call_airship_api`.
- **Auth token with scope `rpt` only** active on that MCP server (see prerequisite above).
- **Client brand + site URL** (for brand context).
- **External orchestration — ASK, and carry the answer into every section brief as
  `orchestration_external`.** "Is any of this traffic triggered from outside Airship — a
  Salesforce Marketing Cloud connector, another orchestrator, an in-house engine — and if
  so, which programmes?" This single question decides whether a whole class of verdict is
  admissible. When targeting and personalisation happen upstream, the segmented,
  personalised programme reaches the Reports API as an untargeted broadcast: the audit
  then sees an absence that is an artefact of where the work is done, not a gap in the
  client's practice. A review that concludes "no segmentation, no personalisation" against
  an account driven by SFMC is wrong in the way that costs the most credibility, because
  the client knows it is wrong on the first read. Default to `unknown` if the user cannot
  answer, and have sections hedge capability verdicts accordingly — never to `none`.
- **Period**: **default trailing 30 days**, `precision=DAILY`. State exact dates. Wider
  windows can be requested, but high-volume accounts should stay at 30 days to keep
  `responses/list`/`activity/details`/`events` pagination tractable (a 90-day pull can be very heavy).
- **Prior-period comparison (REQUIRED on EVERY KPI card — gate-enforced)**: also pull
  `sends`/`opens`/`optins`/`optouts` over the immediately-preceding equal-length window so
  **every** headline KPI (hero tile AND `kpi_card`) shows a **period-over-period delta**, not
  just the exec-summary usage band. `hero_kpi_band(...)` and `kpi_card(...)` both take
  `delta` (fraction vs prior) + `delta_good` (`True`=up is good, `False`=up is bad e.g.
  opt-outs, `None`=neutral direction) and render a small coloured up/down/flat pill (shown on
  the card, printed in the PDF — it's content, not chrome). True year-over-year ("N-1") needs
  an aligned window a year back — only do it if the user asks and volume allows; otherwise
  label deltas "vs prior period". When a metric **genuinely can't be windowed** — a `/devices`
  point-in-time snapshot (opt-in rates, installed base) or an aggregate/un-windowable event
  series (VOD views, in-app counts, email rates, per-broadcast open rates) — pass
  `no_baseline=True` for a muted **"no prior-period baseline"** note rather than a broken/empty
  delta or a misleading `0`. The gate (`verify_report.py`) checks that every KPI tile in the
  exec summary and §4 volume / §5 engagement / §6 permission / §8b in-app / §14 email carries
  one of these two states. Wire the real numbers from `audit.json` (`usage.prior` /
  `usage.deltas`) — never invent a prior value.
- **Every computed KPI must explain itself (gated).** A number the reader cannot trace is a
  number they cannot defend in front of their own management. Give **every**
  `hero_kpi_band(...)` item and `kpi_card(...)` both `formula=` (the calculation in words) and
  `source=` (the **exact Reports API endpoint**, e.g. `GET /api/reports/devices`), plus
  `inputs=` (the numerator/denominator actually used), and `sample=` / `notes=` whenever the
  figure is sampled, extrapolated or unstable. They render as an ⓘ **"how it's computed"** modal.
  `kpi_card` takes `formula` as a named argument so it is safe by construction; **`hero_kpi_band`
  makes methodology optional and silently renders no ⓘ when it is missing** — on a telecom
  account that shipped **90 hero tiles with zero methodology** before the gate existed. Define shared tiles
  (sends, pressure, open rates) **once as a factory function** and reuse them across sections so
  a value and its stated method can never diverge. Gate: *"KPI methodology on every computed
  KPI"* + *"No orphan methodology buttons"*.
- **All tabular data goes in a styled table (gated).** A bare `<table>` has no header band, no
  borders and no zebra — this is the single most common "the data is unreadable" complaint, and
  26 of 38 tables shipped that way on a telecom account. Use **`<table class="grid">`** (the framework
  also ships a bare-`<table>` fallback so nothing ever renders raw, but the gate still demands
  the explicit class). Note `ir-searchable` / `ir-sortable` / `ir-exportable` are **behaviour
  hooks, not styling** — always pair them with `grid`. Equally: **do not bury figures in prose.**
  When a paragraph carries more than two or three numbers, turn it into a
  `Signal | Value | Reading` table — it reads faster and survives translation. Highlight the
  client's own row in a peer/competitor table with `<tr class="is-me">`.
- **Escaping contract — plain text vs raw HTML.** Most components take **PLAIN TEXT** and escape
  it themselves (`strategy_matrix`, `kpi_card`, `hero_kpi_band` labels, table cell helpers, the
  `alt=` of creative helpers): pass `"Service & transactional"`. A few take **RAW HTML**
  (`note()`, `verdict()`, `sub_html_*`, `period_html_*`, `section(body=…)`, creative `caption=`):
  those want `&amp;`, `&middot;`, `<b>`. Feeding a pre-escaped string to a text-taking helper
  double-escapes it and the reader sees a literal `&amp;` — which reads as a **French encoding
  bug**. Gate: *"No double-escaped HTML entities"*.
- **Email message/group IDs (optional)** — a list of email `push_id`s / `group_id`s. When
  supplied, they unlock a **real per-message email table** (`perpush/detail` / `pergroup/detail`);
  when absent, email is reported as an **aggregate funnel** with the per-message limitation
  stated (standalone email is NOT enumerable from the Reports API — see `reference.md`).
- **Language — ONE language per deliverable**: every analysis is language-aware. **Confirm the
  report language up front** (default **English**; **French** fully supported; detect a hint
  from the request — e.g. a French prompt — and offer to match it). Whatever is chosen applies
  to **the ENTIRE deliverable**, consistently: section titles, prose, KPI labels, verdicts,
  tags/origin labels, methodology modals, the interactive chrome (sidebar, Download-PDF,
  Expand/Collapse, search box, CSV button, KPI modal), **and number/date formatting**. Thread
  it through: pass `lang=` to `report_interactive.interactive_head(...)` and to the localisable
  components (`hero_kpi_band`, `strategy_matrix`, `pillar_coverage`, `automation_mix`,
  `kpi_card`, `methodology`), and format every figure via the locale helpers `fmt_int` /
  `fmt_pct` / `fmt_delta` / `fmt_num` (EN `1,234` `12.3%` · FR `1 234` `12,3%`). Pull
  playbook/pillar/lever labels from the `*_fr` fields when `lang="fr"`. Add a new language by
  extending `_UI_STRINGS` in `report_interactive.py`. Never ship a report that mixes languages.
  **The report ships the ONE language its reader reads** — set `LANG` in the builder and pass it
  to `fw.assemble(pages, None, lang=LANG)`. Being asked for the review in French sets `LANG="fr"`
  (translate the `<title>` with it); it is not a reason to ship two columns.
  **A bilingual build is opt-in (`--bilingual`) and costs roughly double.** Every section is
  written twice, and measured across thirteen delivered accounts the localisation checks were the
  largest single source of gate failures (10 of 28) — see *What the gate actually rejects* in
  [orchestration.md](orchestration.md). Ship both only when both columns are genuinely read; the
  primary stays the one that opens on load and the one the PDF prints.
- **Chart labels are ENGLISH in every render — ONE chart set, no per-language chart build.**
  This is the single deliberate exception to "never mix languages", and it exists because
  chart chrome is a handful of technical words (`Sends`, `Open rate %`, `Opt-out rate %`,
  `Direct` / `Indirect` / `Unattributed`, `Injected` / `Delivered`) that a French reader reads
  without friction, while maintaining two chart sets doubles the authoring cost and is exactly
  where language bugs appear. So: `make_charts.py` emits **one** `charts/` directory and **one**
  `specs.json`; never a `charts/en/` + `specs.en.json` pair, and never a language loop. Do NOT
  pass French strings to the `spec_*` label arguments — leave their English defaults alone.
  Everything *around* the chart is localised as usual: the `alt`/caption you pass to
  `chart(...)`, the surrounding prose, table headers, KPI labels, the CSV button. Axis **values**
  that come from data (event names, CTA labels, tag names) stay verbatim in whatever language
  the client's own data uses — that is data, not chrome.
- **Tagging-plan data-collection audit (OPTIONAL)** — the client's RTDS "data collection
  audit" export (`.json`). Parsing + analysis are **built into this skill** (vendored
  `scripts/parse_tagging_plan.py` + `scripts/analyze_tagging_plan.py`, from the
  `datacollection_audit` project) — no separate skill required. When supplied, it
  **enriches** conversion measurement, maturity and strategic recos with the client's real
  tracked taxonomy (events, attributes, tags, subscription lists, value/currency
  instrumentation), and adds a compact **"Data foundation & tracking coverage"** section.
  It is **strictly optional**: without it the report is identical to today (graceful
  degradation). Accept either the **raw export** (the skill runs `parse`+`analyze` for you)
  or the already-produced `inventory.json`+`analysis.json`.
  **Where it comes from**: the client's own export, or a capture the user runs with the companion
  app [`airship-rtds-data-collection-audit`](https://github.com/thomasfaro/airship-rtds-data-collection-audit)
  (private repo — ask for access). **When nobody has an export, proactively offer the app** and
  spell out the four steps — no terminal needed:
  1. Clone it with GitHub Desktop and follow its `docs/INSTALL.md` — double-click
     `Start RTDS Data Collection Audit.command` (macOS) or the `.bat` (Windows); the launcher
     installs whatever is missing, Node.js included.
  2. Add the project's **RTDS bearer token** under **Projects**.
  3. Run a **Capture**: real-time streams auto-stop; a project fed by batch API calls needs a
     manual stop spanning a full batch cycle, or the plan misses whatever the batches carried.
  4. On the coverage summary, click **Download .json** (payload `kind: airship-rtds-tagging-plan`).

  That capture needs an RTDS bearer token and a live stream, so it can never be produced
  unattended: after offering the app, **run the review without it rather than stalling**, and say
  the file can be supplied later for a re-run.
- **NotebookLM source pack — ASK at the start, because a passing gate destroys the inputs.**
  "Do you also want the NotebookLM source library, so the team can interrogate the account's
  data rather than re-read the report?" The pack itself is opt-in and stays so; what is **not**
  optional is putting the question before the first build. The option's own trigger phrases
  ("bibliothèque de sources", "source pack", "notebook lm") only help a user who already knows
  the option exists, and most do not — so waiting to be asked means the answer arrives after
  the retention step has already run. `write_report()` drops `data/*.json` the moment the gate
  passes, and the pack needs those pulls **and** the `report.html` that same build produces.
  Ask, and on a yes `touch work/<client>/.source-pack-pending` in wave 0; the builder then
  stands down from retiring anything. On a no, nothing changes.
  **Recovering from a missed ask costs a re-collection.** Only the `KEEP_ANYWHERE` files
  survive (`collect_manifest.json`, `sends.json`, `pushbodies.json`, `reconcile.json`), so
  `build_source_pack.py` degrades to about a third of its documents and reports the pulls as
  *absent* rather than *deleted* — `discover()` cannot tell the two apart. The fix is to
  re-run `collect.py` (resumable: it skips the survivors), rebuild the report against the
  **frozen** `audit.json` without re-running `analyze.py`, then pack. On a `dashboard`-shaped
  account that is minutes; on a firehose it is not, which is the real reason to ask up front.
- **Branding**: Airship default (see `reference.md`); client charter optional.

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
       (`campaign_purpose.analyze(campaigns, vertical, bodies, reachable)`).
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

### Handling client data

A review pulls a client's real send history onto a laptop and turns it into a document whose
commentary a model drafted. **The report is for internal Airship use**: it prepares the
account team for a conversation and is not sent to the client. That makes the exposure
indirect rather than absent — a figure repeated in a meeting travels just as far — so four
rules follow, and all four are enforced rather than advised.

**The report says how it was produced.** `write_report` injects a provenance footer naming
where the figures came from and which model actually wrote the prose — read from the `stop`
row of `work/<client>/run.md`, so it reports what ran rather than what was asked for.
`verify_report.py` blocks a report that lacks it. This is Airship's own commitment that AI
involvement is marked, and it applies to an internal reader too: the footer is what tells the
account manager which sentences to verify before repeating them.

**Every page is marked internal use.** `assemble()` declares the marking and a `.page` rule
prints it on each page, with a print-only running variant so a sheet pulled out of the PDF
still carries it. The gate blocks a report without it. Page 1 alone was not enough — a chart
pasted into a deck is exactly the page that travels.

**Naming a reviewer is optional.** `Reviewed-by: <name>` in `work/<client>/run.md` is
quoted by the provenance footer when set, but it no longer holds back the copy to
`~/Downloads` — a passing gate is enough to deliver.

**Raw pulls are dropped at delivery; the window is only a net.**

```bash
python scripts/purge_work.py                  # what is past the window (dry run)
python scripts/purge_work.py --apply          # reduce those accounts
python scripts/purge_work.py --purge-all --apply   # drop accounts idle for the whole window
python work/<client>/build_report.py --keep-raw    # keep data/ while investigating
```

A successful build now retires `work/<client>/data/` itself, once the gate has passed and the
signed-off copy is in `~/Downloads`: the pull existed to produce the brief and is dead weight
afterwards. The 30-day window stays for accounts whose build never finished. What survives is
what a rebuild opens — `audit.json`, `facts.json`, `specs.json`, `run.md`, `brand.json`, the
tagging plan, `build_report.py`, and `sections/`, `charts/`, `creatives/` — so the report can
be rebuilt in the other language or after a framework fix without calling the API again. Age
is measured **per file**, deliberately: a probe sweep that writes into thirteen accounts must
not extend the retention of the push history underneath it.

**Except when a NotebookLM pack is also a deliverable.** The pack reads the same pulls, and
it is built *after* the report and rebuilt again whenever the report changes — so the builder
stands down whenever `source_pack/` exists or a `.source-pack-pending` marker is present, and
says so. Touch that marker in wave 0 when the pack is on the list. Retirement is then the
explicit last step of the run: `build_source_pack.py --retire-raw`.

### Checking the skill itself (not a client report)

Two tools, and they answer different questions — running one is not a substitute for the
other:

```bash
python scripts/run_selftests.py            # offline, deterministic, ~0.2s, no credentials
python scripts/check_no_client_names.py    # no real account name in a tracked file
python scripts/probe_sweep.py <start> <end> "PROJ A" "PROJ B" … --expect probe_sweep_expected.json
```

- **`run_selftests.py`** — "does the logic still do what it did?" It runs every module's
  `--selftest` (`push_firehose.py` uses a positional `selftest`) over fixtures: the routing
  oracle's `is_floor`, the sends-weighted sample, the per-push call cap, the calendar
  contamination detector, the audit-vs-facts coherence check, and the data-handling rules
  above (what the provenance footer may claim, what the retention window nominates, what
  redaction masks out of a tagging plan). Every case pins a bug that shipped, so a failure
  names a known error returning. Run it after **any** change to `collect.py`,
  `push_firehose.py` or `build_facts.py`.
- **`check_no_client_names.py`** — "is the repository still neutral?" The skill ships
  benchmarks and general practice, never a client. It reads the account list out of
  `~/.cursor/mcp.json`, where every project this machine can reach is declared as
  `<project> <ENV>`, and fails if one of those names appears in a tracked file — so **the
  check is shipped and the names are not**. Run it before committing: naming the account is
  the natural way to write a comment while tuning, and it has drifted back twice. Describe
  the phenomenon instead; the number of accounts and the result are what carry the argument,
  not which ones. Two kinds of name are searched only beside `PROD`/`DEV` or `user-`: ones
  of two or three characters, which match inside base64 by coincidence, and ones that are
  ordinary English words. Both are listed in the output, so the narrower search is visible
  rather than assumed.
- **`probe_sweep.py`** — "do real accounts still route the way we expect?" It calls the live
  Reports API across a dozen projects (~1,000 calls, minutes, needs MCP credentials). No
  fixture can answer this, because the accounts change on their own. Run it after changing a
  routing threshold. Both its files stay local: the sweep output records volumes per named
  account and the expectation file pairs an account with its regime. Copy
  `probe_sweep_expected.example.json` and fill in your own projects.

`facts.json` also gets checked against the audit it came from, which is the one link the
delivery gate used to take on trust:

```bash
python scripts/build_facts.py work/<client>/audit.json --verify
```

`verify_report.py` runs this itself. A contradicted number (`value`, `path`, `dead_source`,
`stale_derived`) **fails** the gate; a merely absent derived block (`missing_derived`,
`resolvable_now`) is an advisory asking for a `build_facts.py` re-run. Watch for
`missing_derived window_contamination` in particular: with no contamination block, the gate's
"contaminated deltas name their cause" check has nothing to enforce and passes vacuously.

Both of those compare two artefacts and ask whether they **agree**. Neither asks whether the
audit is **plausible**, so run the pre-flight too — before charts, sections or the freeze:

```bash
python scripts/verify_audit.py work/<client>/audit.json
```

It costs under a second and catches the class of defect that agreement checks structurally
cannot: a benchmark stored as a median with no band, a volume-weighted block silently zeroed
by a key-name mismatch, marketing pressure computed from all-channel rather than push-only
volume, a run identity that leaves every Flight Deck link absent. Each of those has shipped
to wave 5 at least once. It also writes `audit.contaminated_fields`, the registry of counters
no section may publish as volume, which is why it must run **before** the freeze rather than
beside it. A FAIL is a **stop** — see
[orchestration.md](orchestration.md#the-pre-flight).

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

## Report structure (mandatory spine + optional sections that earn their place)

The spine — which sections exist, which are mandatory, their numbers and anchors —
is `scripts/canonical_sections.py`, shared with the delivery gate so the structure a
report ships and the structure the gate enforces cannot drift apart.

**What goes inside each section: [report-structure.md](report-structure.md).**
Read it while writing sections. Two things to know before you do: every
`gate_required` section ships even when its data is unavailable (kept and marked
N/A with the reason), and the optional ones are omitted rather than shipped empty.
## Quality gate (before delivery)
- [ ] **ALL canonical sections present (cover, brand context, account profile, executive summary, headline-KPI band, benchmark scorecard + reachability, strategic priorities + maturity matrix, volume & pressure, engagement, permission, campaign typology, playbook & coverage, conversion & impact, events, experiments, creatives, per-channel campaign analysis, best-practices, recommendations, appendix, DATA APPENDIX); any section with unavailable data is KEPT and marked N/A with the reason + how to enable — never silently dropped (the strategic sections AUGMENT, they do not replace the standard ones)**
- [ ] **Executive summary shows a visible period-over-period comparison (`hero_kpi_band` delta pills: window vs equal-length prior baseline), not just absolute KPIs — deltas are on the cards, not hidden in a modal**
- [ ] **Campaign playbook (7b) is fully developed: `pillar_coverage` (done vs recommended per pillar, with the "recommended" column written as sector/brand-adapted use cases, not raw generic lever names) + `personalization_ladder`; the `automation_mix` "today vs target" block is intentionally NOT included**
- [ ] **Data appendix at end of file: tracked events + attributes/tags/lists/screens tables (from the tagging-plan audit; omitted only when no audit) AND a detected-campaigns classification table (`ri.campaign_inventory_table`); every chart/table is CSV-exportable on screen**
- [ ] **Events appendix carries the collected VALUES, not just names — GATE-ENFORCED. `ri.audit_event_properties_table` accompanies `ri.audit_events_table`: per-property type + distinct count + real sample values, and the reserved `value` field shown as `€ Amount` / `Counter` / `Not populated` (three states, never a bare em dash). Every tracked event is listed, including those carrying no property and no value.**
- [ ] **Monetary value handled as a first-class signal: events appendix flags currency-carrying events distinctly; if monetary data is collected it is surfaced in the exec summary (revenue/attributed-value KPI + delta) and valorised in attribution + conversion-value evolution; if not, it is flagged as the key revenue-measurement gap. Airship `value` treated as a counter unless the audit/context confirms currency (never fabricate revenue).**
- [ ] **Report language confirmed and applied CONSISTENTLY across the whole deliverable — section titles, prose, KPI labels, verdicts, tags, methodology modals, AND the interactive chrome (sidebar, Download-PDF, Expand/Collapse, search box, CSV button, KPI modal) — via `lang=` to `interactive_head` + components; number/date formatting localised via `fmt_int`/`fmt_pct`/`fmt_delta` (no mixed-language output; no `1,234`/`12.3%` in a French report)**
- [ ] **Localisation lint clean — GATE-ENFORCED. No English prose and no English decimal marks inside a translated language block. This covers text you write: prose, captions, table headers, KPI labels, verdicts, the CSV button. It deliberately does NOT cover chart chrome, which is English everywhere (next item)**
- [ ] **Charts are ONE English set — GATE-ENFORCED. A single `charts/` + `specs.json`, reused verbatim by both language renders; the FR canvas differs only by its `_fr` DOM id. No `charts/en/`, no `specs.en.json`, no language loop in `make_charts.py`, and no French strings passed to the `spec_*` label arguments (leave their English defaults). The French page localises what surrounds the chart, not the chart. Axis values drawn from client data (event names, CTA copy) stay verbatim — that is data, not chrome**
- [ ] **The report ships ONE language: `fw.assemble(pages, None, lang=LANG)`, with the `<title>` in that language too. `--bilingual` is an explicit request, not a default; under it `LANG` stays the language that opens on load and that the PDF prints**
- [ ] **No undefined layout CSS classes — GATE-ENFORCED. A builder class with no rule (`kpi-grid`, `note-note`) fails silently: the element just loses its layout and only a PDF read-through catches it**
- [ ] **No template text survives — GATE-ENFORCED. The scaffold labels every un-filled block `TODO` so none is forgotten, which only works if `TODO` reaching the reader fails. It did not: a report shipped with its §2 reading TODO while the gate reported success, because the inline stub was not flagged `is_placeholder` and silently beat the section file someone had written. The same check catches a string that lost its `f` prefix and printed `{n(inter, lang)}` to the client**
- [ ] **No section reads `work/<client>/data/*.json` — CHECKED BY `check_section.py`. Those are raw pulls, retired the moment the gate passes. A section that opens one renders today and cannot be rebuilt tomorrow; one review lost a section outright to a purge running during the build, and two others shipped the same read undetected. If a figure is missing, `analyze.py` puts it in `audit.json`**
- [ ] **Every section was run through `check_section.py work/<client> <key> --lang <lang>` before the build — it applies the gate's own checks to one file in isolation, so an English leak or a missing `formula=` is found in the minute it was written rather than hours later in the gate-fix loop**
- [ ] **No chart re-publishes a withheld metric — GATE-ENFORCED. The prose avoids it and the appendix explains the refusal, then a `spec_*` argument puts it back on screen in a dataset label: a programme ranking shipped labelled "Influenced X%" carrying exactly the metric the same report had refused two sections earlier**
- [ ] **(PDF builds only) PDF pagination checked, not just printed: `build_report.py` compares PDF sheets to the printable `.page` divs. Fewer = content dropped in print (hard fail); a few more = appendix tables flowing (fine); many more = sections busting their sheet; a blank trailing sheet = the last page's bottom padding overflows**
- [ ] **Diagnose a page overflow in PRINT emulation, never on screen — the two disagree.** Screen height means nothing for the PDF: measure with CDP `Emulation.setEmulatedMedia {media:"print"}` and read each `.page`'s `scrollHeight` against 1754px. On one account §4b measured **-70px on screen and +723px in print**, because in print the deterministic chart PNG replaces the live canvas and the `height=` argument used to be dropped — a 340px chart rendered at 1296px. The framework now caps the print PNG at the requested height (`--ir-chart-h`), so `chart(..., height=N)` is honoured in both media; if a section still spills, **split it into a `4b`-style sub-section** (`canonical_sections.py`, `sub=True, optional=True`) rather than deleting analysis the client needs
- [ ] **Every KPI tile carries `formula=` + `source=` (the endpoint) — GATE-ENFORCED. `hero_kpi_band` renders no ⓘ at all when they are missing, so a whole report of untraceable numbers passes unnoticed**
- [ ] **Every data table is `class="grid"` and no figure-heavy paragraph is left as prose — GATE-ENFORCED. `ir-searchable`/`ir-sortable` are behaviour, not styling; pair them with `grid`**
- [ ] **No gauge verdict contradicts its own band — GATE-ENFORCED. `ri.gauge` carries its value and p10/p50/p90 as data attributes and the gate reads the worded pill against them, in EN and FR. "Well below the bottom decile" shipped once on a value sitting *above* p10, printed directly under the row that refuted it. Positional wording ("bottom decile", "top decile", "above/below the median") is checked; judgement wording ("healthy", "room to grow") is not**
- [ ] **The freeze held — GATE-ADVISORY. `Sections newer than the frozen audit.json` lists every section last written before the last edit to `audit.json`; each one may be quoting a base that has since moved. A long list means the freeze broke mid-wave: re-read those sections, and prefer re-freezing over patching (see `orchestration.md`, *The freeze*)**
- [ ] **No measurement is a literal in a section renderer.** Anything that reads as a measured figure comes from `audit.json`/`facts.json`. A hand-picked coverage percentage is indistinguishable from a derived one to the reader, and two sections will drift with nothing to catch it — one account published the same pillar at 43%, 45% and 60%. Derive it, or word it as an assessment
- [ ] **One metric, one derivation.** When two sections need the same measure on different bases (alerting vs `/sends`, campaign vs account), name both in `analyze.py` (`platform_rates.*.spum_alerting` vs `pressure.*_month`) and have each section read a key. Re-deriving in the renderer is how one report publishes a frequency twice with different numbers and inverts its own platform ranking
- [ ] **No double-escaped entities — GATE-ENFORCED. Text-taking components escape their own input; a literal `&amp;` in the output reads as an encoding bug to a non-English reader**
- [ ] Brand context researched, sourced, and used in insights/recos
- [ ] **Industry confirmed; benchmarked KPIs positioned vs the matching industry benchmark (median/range) with the benchmark's source/date/n/region — or, when unavailable, vs an internal same-type baseline; never fabricated; comparison confidence ≤ Medium**
- [ ] **Channels/metrics without an external benchmark (email/SMS opens & clicks, opt-out rate, blended rates, custom-event attribution…) positioned against an `[Internal baseline]` — client's own other messages of the same channel + campaign typology, median + range, ≥3 comparable messages (else "insufficient same-type messages" stated)**
- [ ] Each insight/reco tagged `[Data]` / `[Brand context]` / `[Data+Context]`
- [ ] **Snapshot (whole-base) vs period metrics kept separate and labelled; opt-in rate only from `/devices`; optin/optout shown as period event flows**
- [ ] **Marketing pressure reported both cross-platform AND per active channel (push iOS/Android, email, web…); denominator matched to each channel; missing denominators flagged**
- [ ] **Every active channel detected from `/sends` per-channel volume (`channel_activity.channel_summary`), not from `/devices` alone; email/SMS flagged active even when opted_in=0; each active channel has its own analysis block (volume + engagement + typology), never a bare volume number**
- [ ] **Email (when active): aggregate funnel built from Airship standard events (injection/delivery/open/click/bounce/spam/unsubscribe) with delivery/open/CTR/CTOR/bounce/spam/unsub rates; per-message table only when IDs supplied, else limitation stated**
- [ ] **Automated-vs-one-shot split reported PER CHANNEL (push per-campaign at High confidence; email/SMS channel-level cadence at Low/Medium confidence, labelled)**
- [ ] **Activity log paginated for the full period; merged with responses/list; activity-only broadcasts included in push reach ranking; push-program section seeded from group_ids + activity GROUP rows**
- [ ] **Campaigns classified on the merged inventory (activity log + responses/list + classify_campaigns.py heuristic); no /pipelines or /schedules calls; two top rankings present (one-shot vs automated/recurring); recurring campaigns analysed for volume drift + engagement trend**
- [ ] **Experiments detected via push_type == A_B in responses/list (no /api/experiments call); variants/winner shown or "none detected" stated**
- [ ] **No Content API calls (`/api/content/*`); OAuth token needs only scope `rpt`**
- [ ] **Creative coverage from pushbodies stated; UNICAST/template-driven limitation explicit where pushbody is empty**
- [ ] **Value-bearing events flagged and given per-message attribution where applicable**
- [ ] **UNICAST campaigns labelled with recovered categories (or "category unavailable")**
- [ ] **Email/SMS top-message performance sourced from the per-push report (`perpush/detail`
      or `pergroup/detail` top-level fields), not `responses/list`/activity log; email
      metrics mapped (sends; opens=`influenced_responses`; clicks=`direct_responses`);
      email presence/absence cross-checked against `/devices` opted_in before stating "0 sends"**
- [ ] **Every insight/reco carries a verification basis + confidence (High/Medium/Low); low-confidence items state what would raise confidence**
- [ ] Every visual has a source; glossary + appendix (incl. methodology) present
- [ ] Creatives fetched from Reports pushbody only; real previews where pushbody has content, reconstructions labeled (UNICAST empty-body called out)
- [ ] **Campaign analysis is COMPARTMENTALIZED BY CHANNEL (push / email / SMS / in-app in separate labelled blocks); push and email are NEVER blended in the same table, ranking or matrix**
- [ ] **The platform × type matrix and the two rankings are PUSH-ONLY (rows iOS/Android/web); each active non-push channel has its own labelled block**
- [ ] **Rich push previews use the REAL hero image (fetch_media) AND the REAL app logo (fetch_app_icon → render_push app_icon=); text-only card / colored tile only when no image / no logo existed**
- [ ] **Message Center previews are phone-sized: render_email(..., width=375, max_height=720) + creative_mc_preview() in HTML (ir-mc-viewport clips to one screen); never a raw full-scroll MC PNG**
- [ ] **Push analysis is by platform (iOS/Android/web) AND by message type; both a reach ranking and a rate ranking are shown (rate ranking has a min-volume floor); tops are not chosen by volume alone**
- [ ] **Email: per-message table (sends/opens=influenced_responses/clicks=direct_responses) when message/group IDs were provided; otherwise an aggregate funnel with the per-message limitation stated prominently; creatives chosen by the STATED objective rule, never "by looks"**
- [ ] **Every top campaign (reach- and rate-leaders, per channel) has a creative preview and a benchmark/internal-baseline position**
- [ ] **Analysis window is the default 30 days unless the user overrode it; the actual span is stated and reflected in the deliverable name**
- [ ] **Recommendations organised by the 6 pillars: TARGETED (existing campaigns) + NEW campaigns (`recommend_campaigns` gap levers used as a STARTING POINT, then REWRITTEN as concrete brand-specific proposals adapted to the brand's business model & current context — recent news/strategy/challenges/competitors — not generic lever names; tagged lifecycle/adoption/commercial/service/editorial/engagement + business stake) + GENERAL (account-level, incl. industrialisation reco); each tagged + confidence**
- [ ] **Visual headline-KPI intro present (`hero_kpi_band`): audience + usage KPIs with prior-period deltas (or the delta limitation stated); each KPI keeps its methodology modal**
- [ ] **Campaign analysis is MESSAGE-FIRST (push/MC/email/SMS primary; in_app_message/pager/mcrap/banner CTA signals are a COMPLEMENT at `cta_only`/low reliability, never a substitute)**
- [ ] **One CANONICAL multi-channel inventory built (`campaign_inventory.build_inventory`) with NO lossy drops (min-volume floor is display-only); `split_events` feeds behavioural `location:custom` to conversion and in-app campaigns to purpose**
- [ ] **Every campaign mapped to a strategic PILLAR + lever (`campaign_purpose.classify_purpose`), LANGUAGE-AWARE + HIGH-RECALL (FR/EN detection, alias stemming/prefix, pillar-priority disambiguation), name-first with content fallback (decoded pushbody, never Content API)**
- [ ] **Every mapping carries a numeric `reliability` (0-1) + High/Medium/Low (message name > body > `cta_only`), surfaced in the report (reliability pill/column) AND explained to the reader as the CONFIDENCE OF THE QUALIFICATION (how sure the campaign→pillar/lever mapping is — not a performance metric); pillar coverage counted only at reliability ≥ 0.45**
- [ ] **Custom-events / conversion sections scoped to behavioural `location:custom` only (`banner - …` impressions AND any campaign-marker prefixes like `push - `/`p+i - `/`scene - ` excluded via `exclude_name_prefixes`, and those markers routed to the campaign inventory instead); in-app CTA events not polluting the conversion taxonomy**
- [ ] **API calls de-duplicated: single daily-range pull sliced current/prior (not two windowed pulls); decode-once `pushbody` cache reused across purpose/creatives/deep-links/category recovery**
- [ ] **Per-pillar MATURITY matrix present (coverage of vertical-recommended levers + automation share + business stake/key figure) and a levers-by-pillar coverage grid (done vs recommended); strategy layer capped at Medium confidence**
- [ ] **Personalization-depth ladder present (the `automation_mix` "today vs target" industrialisation viz is intentionally omitted; the one-shot vs automated read stays in the per-channel typology §7 and/or one account-level reco)**
- [ ] **Exhaustiveness contract honoured: no voluntary sub-sampling; `/events` + activity log + `responses/list` fully paginated; ALL needed `pushbody` decoded; the audit processed in full (every event/attribute/tag/list/screen, no silent top-N); any technical limit handled by loss-less program-level aggregation with an explicitly quantified coverage**
- [ ] **(If a tagging-plan audit was supplied) Data-foundation enrichment applied AND the report is byte-for-byte the same layout when it is absent (graceful degradation via `audit["available"]`)**
- [ ] **(Audit) Conversion KPIs cross-referenced to the audit (`cross_reference_conversion`): per-KPI value/currency backing shown, `enrich-value` decided from the tagging plan (`value_index`→`audit_value_index`), conversion events tracked-but-not-fired listed; `value` ≠ currency caveat kept**
- [ ] **(Audit) Personalization ladder built from real tracked data (`personalization_ladder_from_audit`); every recommended lever tagged activatable-now vs needs-collection (`lever_data_readiness`/`annotate_recommendations`); provenance (SDK/API, contact/device, cadence) surfaced**
- [ ] **(Audit) Every gap + conversionSignal turned into a pillar-tagged data/activation reco (`data_collection_recos`) folded into section 16; contextual layer ≤ Medium confidence**
- [ ] **(Audit) "Data foundation & tracking coverage" section present (`data_foundation_block`): breadth, tags/lists segmentation, SDK/API + storage verdict, vertical coverage %, value/currency instrumentation rate**
- [ ] **(Audit) Data-collection gaps & quick-wins shown as a READABLE TABLE via `ri.data_collection_table(recos, lang)` (priority / type / target / action / what-it-unlocks / pillar) — NEVER a raw bullet dump of the reco dicts**
- [ ] No fabricated figures; unavailable data + degraded scopes flagged; reconstructions labeled
- [ ] Top rankings present for each active channel; absent channels stated
- [ ] Events: all pages paginated; location/conversion taxonomy; families
- [ ] **Account profile & Airship-adoption scorecard present — GATE-ENFORCED — via `ri.channel_adoption_matrix(rows, lang)` (channel × status × 30d volume × opt-in base) AND `ri.feature_adoption_table(rows, lang)` (feature × adoption pill × evidence + upsell note); built for EVERY account (not only firehose), never dropped on a leaner build**
- [ ] **Executive summary is RICH — GATE-ENFORCED — with a `verdict` + signal `note`s AND ≥2 `hero_kpi_band` blocks (audience / usage-vs-prior-30d with delta pills / value & pressure), each KPI carrying its methodology; not a thin one-band summary**
- [ ] **Conversion KPIs identified (conversion event taxonomy) + push-attributed funnel + attribution rate; two impact rankings (engagement AND attributed conversion)**
- [ ] **Firehose accounts analysed by PROGRAM (distinct group_ids via pergroup/detail: sends + rates + platform split), not declared intractable; web push checked inside automation groups**
- [ ] **Push account SHAPE probed before collection (`push_firehose.py probe`). A `firehose_groupless` account (external orchestrator calling /api/push per contact, no group_id, known modest daily count) is EXHAUSTIVELY enumerated via time partitioning — the per-program escape hatch does not apply — and its campaign taxonomy is rebuilt from the orchestrator's tag namespace (there, the tagging plan IS the campaign inventory, so ask for it). A `firehose_unattributed` account is NEVER enumerated: volume comes from `/api/reports/sends` alone, and every sample states the share of window sends it carries**
- [ ] **Both send counters reconciled when both appear (`/api/reports/sends` = alerting only, `responses/list` = incl. silent data-only); `/api/reports/sends` used for volume KPIs; the gap explained by a measured silent share, not hand-waved**
- [ ] **Any rate extrapolated from a SAMPLE tested for temporal drift before being reported as one number; when unstable, the trend and its breakpoint are reported instead of the blended mean**
- [ ] **Marketing pressure: cross-platform + per-platform + per-month vs benchmark + fatigue signal (pressure vs opt-out/opens) + temporal distribution + frequency governance**
- [ ] **Benchmarked KPIs shown as visual gauges (p10-p90 band, p50, client value + verdict); reachability per channel present**
- [ ] **Engagement best-practices scorecard present (rich push %, deep-link %, perso %, A/B, lifecycle, MC-paired, copy hygiene; email CTOR where active)**
- [ ] **Every analysed dashboard-composed message deep-links to Flight Deck (composer id = options.__ui_id, app_key auto); UNICAST/API sends show the "no deep-link" pill (never a fabricated URL)**
- [ ] **Deliverable is a self-contained INTERACTIVE HTML web-app (dashboard head: fixed sidebar with auto TOC + scroll-spy, Expand/Collapse-all, Download-PDF only on a `--pdf` build; fluid full-width content column) — the paginated PDF companion prints from the same file when requested; no PNG deliverable**
- [ ] **Every displayed KPI — executive summary, benchmarks, pressure, conversion, etc. — uses `kpi_card(...)` with full methodology (formula + inputs WITH values + source endpoint(s) + coverage/sample + confidence pill); screen UX is the ⓘ modal, not inline drawers — no bare unexplained numbers**
- [ ] **Key/long tables are `.ir-searchable` and `.ir-exportable` (CSV); every chart exposes a source-data CSV button (auto-derived from its spec)**
- [ ] **Charts are interactive (Chart.js canvas on screen) via the `spec_*` emitters AND each has a matplotlib PNG fallback; HTML stays single-file/offline (Chart.js inlined, no CDN); the PDF uses the PNGs; benchmarks stay as SVG gauges**
- [ ] (PDF builds only) PDF page count == #CSS pages (no overflow; screen web-app CSS does not leak into print); every `<details>` opens in the PDF; Airship branding respected
- [ ] `value` never shown as currency
- [ ] **`python scripts/verify_report.py work/<client>/report.html` PASSES** — the automated gate confirms the **full canonical section set** (every `gate_required` section in `canonical_sections.py`, currently 14, plus the cover; a condensed report FAILS), interactive charts AND message creatives are actually rendered (custom builders must ship the complete structure, set `include_charts=True` + generate charts + creatives; a legitimately creative-less account still ships a labelled illustrative/limitation creatives block)
- [ ] **The gate's STRUCTURAL floor passes (blocking): §2 channel-adoption matrix + feature-adoption scorecard present; executive summary carries ≥3 `hero_kpi_band` blocks; charts actually render (a canvas exists); at least one message creative is decoded, or a labelled illustrative block replaces it.**
- [ ] **`work/<client>/run.md` carries a filled Deviations section** — every counter refused and what replaced it, every chart dropped and why its spec was rejected, every KPI overridden or left unresolved, every section kept in the main context, every re-collection or moved window. A run with no entries has an unwritten section, not a clean record; it is the first thing read when a figure is challenged, and no automated check can produce it. See `orchestration.md`, "Run manifest".
- [ ] **The gate's VOLUME floors are read, not just cleared (advisory `!`): no thin narrative section; ≥6 recommendation items; ≥6 verdict/note callouts; ≥5 charts; ≥3 creatives (scaffold target ≥6/≥4). These no longer block, because a floor that mandates a count manufactures padding to satisfy it — six thin recommendations are worse than three that land. Read every `!` and decide: either the account genuinely has less to say (say so in the report) or the section is under-worked. Gate on them with `--strict` for a flagship deliverable.**

## Writing doctrine — three failures a delivered review came back with

Applies to **everything the client reads**, including the executive summary this
orchestrator writes itself. `.cursor/agents/airship-section.md` carries the same three
rules for the section writers; keep the two in step.

**Plain sentences, one idea each.** Frontier-model prose fails in a specific direction: it
compresses. It stacks five ratios in a paragraph, opens on an abstraction, and joins clauses
with an elliptical connective that assumes the reader already holds the argument. Every
sentence is defensible and the paragraph still has to be read twice. Cap a paragraph at two
or three figures, name the subject before the verb, and when it gets dense cut a sentence
rather than tighten it. Length is the second problem, not the first: the review has grown
long enough that a reader skims, and skimming a correct report loses the argument as surely
as writing a wrong one.

**Comparability is a claim, and it needs the same scrutiny as a number.** Two figures each
computed against its own correct denominator can still be uncomparable, and that is the
harder error to catch because the arithmetic is clean. Web against app opt-in shipped this
way: a browser prompt and an iOS system prompt are different asks on different surfaces with
different costs to reverse, so the gap measures the prompts and not the audiences. Before
putting two numbers on the same scale, ask what would have to be true for the comparison to
mean anything. If the answer is "the mechanics match", check that it does; if it does not,
report each on its own scale and make the incomparability the point.

**Calibrate every capability verdict to what Airship can see.** See `orchestration_external`
under Inputs. Absence in the Reports API is evidence about the API, not about the client's
practice, and an audit that misses context states its conclusions too strongly precisely
where it is least entitled to. Name the fact that would overturn each verdict. This is not
hedging for its own sake — a conclusion that survives the client supplying missing context
is stronger than one that collapses on the first read.

## Model requirement — route by task, never downgrade the prose
The **orchestrator and every word the client reads** run on a **frontier model**. Sustained
multi-step tool use, data reconstruction (firehose accounts, creative decoding, attribution)
and consultant-grade writing across ~14 sections all degrade on a lighter model — thin
sections, weaker insights, missed data — even though the layout holds. Not negotiable for a
client deliverable.

A large part of this workflow, however, is **not prose**. Running a collection script,
rendering charts, converting a PDF or clearing a mechanical gate ✗ is deterministic work whose
output is verified by something other than taste. Putting it on the frontier model buys nothing
and costs wall-clock.

**The routing is declarative, not advisory.** It lives in `.cursor/agents/*.md`, one file per
role, each pinning its own `model`. Delegate to the agent and the model comes with it; a
routing table that depends on the orchestrator remembering it, two hours into a run, is a
routing table that gets forgotten.

| Task | Agent | Model |
|---|---|---|
| Orchestration, arbitration, coherence pass | (main context) | `claude-opus-5[effort=high]` |
| **Any section prose, any verdict, any recommendation** | `airship-section` | `claude-opus-5[effort=high]` |
| Brand & business research (step 1, background) | `airship-brand-research` | `gpt-5.6-sol` |
| Collection, charts, creatives, PDF | `airship-shell` | `composer-2.5[fast=true]` |
| Data appendices (`appendix_events`, `appendix_attrs`, `appendix_campaigns`) | `airship-appendix` | `composer-2.5[fast=true]` |
| Gate-fix loop (mechanical ✗ only) | `airship-gate-fix` | `composer-2.5[fast=true]` |

Model parameters go in brackets after the id — `effort`, `context`, `fast`. Which values a
model accepts depends on the model and your account, so discover them rather than assuming.
**Do not pin `context=`** on the section, appendix or shell agents: their whole design is to
read `facts.json` plus one named audit slice, and a small window makes loading `data/*.json`
impossible rather than merely discouraged. Raise it only on the orchestrator or the coherence
pass, and only once `preCompact` in the run manifest shows compaction actually biting.

**Max Mode no longer exists** on usage-based plans — extended context is a property of the
model, requested with `[context=…]`. Do not go looking for a toggle.

Three rules keep this honest:

- **Never** route a section that carries interpretation to a fast model. This is now
  enforced, not asked: `.cursor/hooks/guard_model.py` denies an `airship-section` subagent
  launched on a Composer model.
- **Never** let a fast model be the last word. The gate runs after it, and the coherence pass
  is frontier.
- **State the model you actually got.** A declared `model` can be silently overridden — an
  admin block, a plan that excludes it, or a legacy request-based plan where every subagent
  falls back to Composer regardless. The `stop` hook records the real model in
  `work/<client>/run.md`. A skill that calls the frontier model non-negotiable owes the reader
  a note when it did not get one, rather than implying a standard it may not have met.

**Do not run the collection in the cloud.** Cloud subagents and Automations read their MCP
servers from the *team* configuration at cursor.com/agents, not from your local config — and
this skill's entire prerequisite is a per-client MCP server declared locally. Wave 1 in the
cloud finds no project and fails, or worse, finds a different one.

## Orchestration — waves & parallel section writing
Optional, and only worth it on a large account. Full playbook, prompt templates and run
manifest: **[orchestration.md](orchestration.md)** — start with the
[wave diagram](orchestration.md#wave-graph), which shows the three points where the flow can
send you backwards and how much work each one costs. The rules that matter here:

**Collect and analyse sequentially, then freeze, then parallelise.** `audit.json`,
`facts.json`, `specs.json`, `charts/` and `creatives/` are final before any section is
written, and read-only for every section agent. A number that moves after the freeze
silently invalidates every section that already quoted it, and nothing will tell you which.
Charts must exist before wave 4 or `fw.chart()` raises `MissingChartError` mid-section.

**Only the factual sections parallelise** — `volume_pressure`, `delivery_shape`,
`engagement`, `permission`, `events`, `inapp`, `detected`, and the three appendices. Each
reads a named slice of `audit.json`, reaches a verdict about its own subject, and depends
on no other section. One agent writes exactly one file, `sections/<key>.py`, so there is no
merge surface.

**The consultative sections stay in the main context and are written LAST**:
`exec_summary`, `benchmarks`, `strategy`, `playbook`, `recommendations`, `brand_context`,
`account_profile`, `push_program`, `email_program`, `channels_exp`, `best_practices`,
`appendix`. These carry the report's argument and need the finished deep-dives in front of
them. Writing them concurrently is exactly how a report ends up warning about over-pressure
in §4 and recommending more volume in §16.

**Every section agent gets `facts.json` + its audit slice, and never `data/*.json`.** The
raw rows were `analyze.py`'s problem; a section agent that loads them spends its context on
data it will not cite.

**Two things replace the coherence that a single writer gave you for free.** The numeric
check in the gate holds every KPI card to `facts.json` — a protection worth having even on
a sequential run, since it catches the stale copy-paste too. And a final **frontier
coherence pass** over the assembled report fixes prose only: contradictions between
sections, the same figure rounded two ways, vocabulary drift, repetition. It may not add,
remove, reorder or renumber anything, and if a number looks wrong it reports it rather than
editing it.

## Mode B — Goals review (light)

A conversion-only review produced **100% offline** from the client's tagging-plan
JSON plus public research on the brand. No MCP call, no `collect.py`, no creatives,
no PDF. English-only.

**Full specification: [mode-b.md](mode-b.md)** — who reads it, the rule that governs
candidate selection, the workflow, its 12 sections, and the limit it must state
rather than hide. Read it when mode B is the chosen mode; mode A never needs it.
## Dependencies
Python: `matplotlib`, `numpy`, `pillow`, `openpyxl` (benchmark import); `pymupdf` optional
(only for the PDF page-count sanity check in `build_report.py`).
Google Chrome (headless) for HTML→PDF and mockup rendering.
`scripts/report_interactive.py` (deep-links, interactive scaffold, gauges, interactive
charts) is pure stdlib; it inlines the vendored `scripts/vendor/chart.umd.min.js` (Chart.js
v4, MIT) so the HTML stays offline — no runtime CDN, no `pip`/`npm` install for charts.

## Resources

**Read on demand, not up front.** These four carry the detail that used to sit inline in
this file. Each is needed at exactly one point in a run, and loading all of them at the
start costs context that the sections themselves need:
- [setup-mcp.md](setup-mcp.md) — one-time MCP setup for a client project. Read once per
  new account, never again.
- [analysis-spec.md](analysis-spec.md) — what to compute in step 4 and what each metric
  means. Read when running the analysis; produces `audit.json`.
- [report-structure.md](report-structure.md) — what goes inside each mode-A section. Read
  while writing sections.
- [mode-b.md](mode-b.md) — the full Goals-review specification. Read only in mode B.

- [reference.md](reference.md) — endpoints (Reports API only, scope `rpt`),
  snapshot-vs-period, campaign-typology & experiment detection, value-bearing events,
  unicast category recovery, verification & confidence, creative-retrieval table,
  **channel-siloed campaign analysis (push-only matrix/rankings; email/SMS/in-app blocks)**,
  **objective creative-selection rule + real-app-logo sourcing**, email/SMS per-push
  performance sourcing, internal same-type baseline (no-benchmark fallback), Airship palette.
- [orchestration.md](orchestration.md) — **how to run the review as waves of subagents**
  instead of one sequential pass: the wave graph and why the split falls between the
  factual and the consultative sections, the freeze checklist, what each subagent may and
  may not read, copy-paste prompt templates (collection, one factual section, gate-fix
  loop, coherence pass), a run-manifest template, the failure modes with their fixes, and
  when *not* to parallelise. Optional — worth it on a large account, overhead on a small one.
- [benchmarks.md](benchmarks.md) + `benchmarks.json` — Airship UA Benchmarks by vertical ×
  device family × percentile (opt-in, direct/influenced open, sends/user/month, MC read rate);
  load to position client KPIs vs peers. Refresh with `scripts/import_benchmarks.py`.
- `scripts/resolve_vertical.py` — maps a free-text industry (EN/FR) to a benchmark vertical
  via the `aliases` in `benchmarks.json`, and returns a **`proxy` flag + a `disclose`
  sentence** to print in the report when the match is a stand-in rather than an exact peer
  set (telecom → Utility & Productivity, since Airship publishes no telecom vertical).
  Makes the choice reproducible instead of a per-audit judgement call.
- `scripts/airship_api.py` — **direct Reports-API client** for the exhaustive passes the MCP
  can't serve (one round-trip per page is fatal at tens of thousands of pages). Same OAuth
  client-credentials flow as the MCP server, credentials read from `~/.cursor/mcp.json` by
  project name, thread-safe token refresh, retry/backoff, `paginate()`/`collect()`.
  Read-only, scope `rpt`.
- `scripts/collect.py` — **the shared collector: run this instead of writing a per-client
  `collect*.py`**. `collect.py "<MCP project>" --start … --end … --out work/<client>/data`
  drives `airship_api` through every stage the review needs (probe → core → events →
  activity → responses → programs → details → bodies → groupbodies → split → attribution →
  decode), each **individually resumable** (a stage whose files exist is skipped; `--force`
  re-runs, `--stages a,b` selects). It encodes the rules that are easy to get wrong: ONE
  doubled-window pull sliced in code, inclusive `end` handling, de-duplication on
  `push_uuid`, a persistent decode-once `pushbodies.json` cache, automatic switch to
  `push_firehose.enumerate` on a firehose shape, and **`/events` at DAILY** (MONTHLY snaps
  the window out to whole months — measured on a streaming account it added 11 events that never
  fired in the window; the monthly superset is still saved as `events_monthly.json`).
  Writes **`data/collect_manifest.json`** (per stage: files, rows, pages, API calls,
  elapsed, coverage) so the methodology section cites *measured* coverage. Account-specific
  extras go in a `collect_hook.py` (`--hook`), not in a forked collector.
- `scripts/build_facts.py` — **emit `facts.json`, the shared numeric brief** (a few KB next
  to `audit.json`): headline KPIs with prior-period deltas, window, language, vertical /
  benchmark set, brand vocabulary, and the sections marked N/A with their reason. It does
  NOT canonicalise `audit.json` — each account's audit stays as rich and as bespoke as it
  needs to be; every KPI is resolved through a list of candidate paths and anything
  unresolved is **reported**, so you widen a path or pass `overrides={...}` instead of
  reshaping the audit. Rates are normalised to percentage points (audits disagree: `0.674`
  vs `67.4`). Two consumers: section writers quote it (that is what stops two concurrently
  written sections from quoting one KPI differently), and the delivery gate checks the
  report against it. Each KPI carries `label_patterns` because reports label KPIs
  descriptively ("alerting push sent (30d)"), not by canonical name — add an alias there
  for a bespoke label.
  It also carries **`withheld`** (`withheld_metrics`): the figures the collection
  disqualified itself, each with the value it disqualifies, why, and what to publish
  instead. The collector already decides this — `per_push_stats_reliable`,
  `split_sample.publishable`, a drift verdict, the activity-log caveat — but the verdict used
  to stay in `data/probe.json`, one key away from the number and unread by anyone. That is
  how a `mean_sends_per_push` of 1,010.87 drawn from 1.1% of an account's sends stays
  quotable. Two accounts avoided it by hand-writing a bespoke `unreliable` block, which is
  read and merged here so nobody has to invent that key again — and a wave-4 section writer
  who never opens `probe.json` now gets the verdict in its brief.
- `scripts/verify_audit.py` — **plausibility pre-flight on `audit.json`**, run between the
  analysis and the freeze. The sibling of `build_facts.py --verify`, asking the question that
  one does not: not "do these two artefacts agree" but "is this audit believable at all".
  Four checks, each a defect that has reached wave 5: a benchmark stored as a scalar median
  where a gauge needs a `p10`/`p50`/`p90` band; a volume-weighted block sitting at zero
  beside a populated count-weighted twin (a key-name mismatch between producer and consumer,
  which fails silently and whose count-weighted neighbour can point the opposite way);
  marketing pressure that reconciles with the all-channel send total rather than push-only
  (`/api/reports/sends` spans email — checked arithmetically, not by label); and a run
  identity that does not resolve, which costs every Flight Deck link with no error anywhere.
  Identity is resolved *through `build_facts` itself*, so it cannot drift from the resolver
  it guards. Exit 1 on any required failure — treat it as a stop, since the cost is not a
  wrong report but re-reading every section written against a bad base.
  It also **writes `audit.contaminated_fields`** before the freeze: every numeric field
  equal to the `responses/list` total or to the all-channel total, each with its path, its
  ratio to the authoritative push figure, and what to read instead. One account carried six
  copies of a counter 1.36x its real push volume, found one at a time over three days, the
  last while writing the appendix. They are equal, so they are findable — and the registry is
  what `check_section.py` and `airship_charts.check_series` consume, so a field caught once
  is blocked everywhere afterwards with no editing.
- `scripts/brand_schema.json` + `scripts/check_brand.py` — **the frozen shape of wave 0's
  `brand.json`, and the command that enforces it**: `check_brand.py work/<client>/brand.json`.
  Every block, its required fields, which report section consumes it, and a hard budget
  (one agent, one pass, 40 sources). Wave 0 ends when this prints `ok`. Before the schema
  existed, a run with no output shape to fill invented one, fanned the research across
  sub-topics to populate it, and then dispatched reconciliation agents — twenty subagents
  for one file, none of it research. A field that cannot be filled is
  `{"status": "unverified", "note": "…"}`, which is a finished answer, not a retry.
- `scripts/check_section.py` — **render ONE section and judge it by the gate's own rules**:
  `check_section.py work/<client> <key> [--lang fr]`. Use it instead of a full build while
  wave 4 runs, because a full build imports every section and fails on whichever file another
  agent is halfway through writing. It imports the module, renders both languages on request,
  and runs the delivery gate's section-scoped checks *as implemented*, plus a scan for values
  in the contamination registry, unrendered `None`/`nan` in a value slot, undefined CSS
  classes against the real stylesheets, and pasted reading-tool line numbers. Two runs wrote
  this file from scratch before it lived here; its selftest pins the false positives that made
  both of those versions unusable.
- `scripts/cross_compare.py` — **align N sibling-app audits into a frozen `cross.json`** for
  §3d. Aligns on `build_facts` KPI keys so the comparison and the two reports cannot disagree,
  and refuses more than it asserts: mismatched windows exit 1, a metric measured on one side
  is not a gap to zero, a contaminated value is dropped, and each row states whether it may be
  read as performance or only as numbers (two apps of one brand often sit in different
  benchmark cohorts, and then neither is the other's benchmark). See `orchestration.md`.
- `scripts/merge_source_packs.py` — **one NotebookLM pack for a multi-app run**. Sources
  identical across the accounts are emitted once; the rest keep their numeric prefix and gain
  an account suffix so the same theme sorts adjacently. Add each report's markdown to its own
  pack before merging.
- `scripts/decode_bodies.py` — **decode the pushbody caches** (no network):
  `decode_pushbodies(cache)` → creatives/features/deep-links per push,
  `decode_groupbodies(cache, pergroup)` → automation vs scheduled-broadcast programs,
  `summarise(decoded)` → the feature counts the adoption scorecard needs. Handles the three
  wrappings that otherwise yield empty creatives: `{"schedule":…,"push":…}` double wrapping,
  copy under `notification.<platform>.template.fields`, and handlebars multi-language
  strings. Used by `collect.py`'s `decode` stage; runnable standalone on a `data/` dir.
- `scripts/push_firehose.py` — **firehose push accounts, end to end**: `probe` (classify the
  account as `dashboard` / `firehose_grouped` / `firehose_groupless` in ~8s — run this BEFORE
  choosing a collection strategy), `enumerate` (exhaustive de-duplicated `responses/list` pass
  via adaptive hour→minute→2s time partitioning, parallelised), `sample` (alerting/silent/rich
  split from `perpush/detail`, **with temporal-drift detection** so an unstable rate is never
  reported as a blended constant), `reconcile` (explain the `responses/list` vs
  `/api/reports/sends` gap, or flag the unexplained residual).
- `scripts/canonical_sections.py` — **single source of truth for the report structure**: the
  ordered `CANONICAL_SECTIONS` spine (key, number/label EN+FR, id, optional/gate flags, N/A
  copy, std charts) plus `GATE_SECTIONS` (the 16 the gate enforces) and `STD_CHARTS`. Both the
  builder (via `report_framework`) and the gate (`verify_report`) import it, so the shipped
  structure and the enforced structure can never drift. Add/rename/renumber a section HERE.
  Also carries the **mode B spine**: `GOALS_SECTIONS` / `GOALS_GATE_SECTIONS` /
  `GOALS_CHARTS`, reachable through `profile("goals")`, which returns the bundle
  (sections, gate list, charts, `bilingual: False`) that the builder and the gate both
  read. `ALL_KEYS` is the union, so a section file named for either spine validates.
- `scripts/report_framework.py` — **shared assembly framework** (removes per-client
  boilerplate): `render_report(renderers, ctx, lang)` iterates the canonical spine and
  auto-emits a labelled N/A block for any non-optional section a renderer doesn't fill;
  `load_sections(dir, inline)` builds that renderer map from **one file per section**
  (`sections/<canonical_key>.py` exposing `render(ctx, lang)`) so sections can be authored
  concurrently without touching a shared file — filenames are validated against the spine,
  so a typo raises `SectionLoadError` instead of silently degrading to N/A (the failure
  mode of a mistyped key in a hand-written dict); an inline renderer wins over a file of
  the same name, and `sections/_shared.py` holds helpers shared between sections;
  `chart(id, dir, specs, lang)` embeds a chart and **raises `MissingChartError`** if the
  spec/PNG is missing (no silent drops); `cover_section(...)`, `section(...)`, `na_block(...)`,
  `assemble(en, fr, ...)` (bilingual, FR-id suffixing, brand CSS + lang toggle;
  `pdf_button=False` drops the sidebar download button for an HTML-only deliverable);
  `write_report(html, out, gate=True)` writes then runs the gate as a **blocking** step
  (`BuildGateError` on FAIL, `gate=False`/`--no-gate` to bypass); `aget("a.b.c")` reads
  audit.json defensively (missing key → N/A, not a crash); `datauri(path)`. Mode B passes
  `sections=` to `render_report`/`load_sections` and `profile="goals"` to `write_report`,
  which switches the spine and relaxes the gate defaults (no creatives, 3 charts, section
  floor = the goals spine) without any per-client flag juggling.
- `scripts/build_report_template.py` — **canonical builder scaffold new clients copy**
  (`cp … work/<client>/build_report.py`): every canonical section pre-wired to the framework,
  N/A until you replace each `renderers[...]` stub with real content. Runs the gate at build
  time; `--no-gate` to write without gating. Start here instead of hand-writing a builder.
- `scripts/sections_shared_template.py` — **section-helpers scaffold** (`cp … to
  work/<client>/sections/_shared.py`): the sibling of the builder scaffold, for the file every
  section imports. Loads the frozen artefacts once, then hands out the house rules — `kpi()`
  raises on an unknown key instead of returning a silent zero, `i()`/`n()` separate counts
  from rates, `signal_table()` escapes its own cells, `flight_deck()` renders a missing
  composer id as an explained pill, and `contamination_note()` writes the mandatory calendar
  caveat from the detector's own evidence. Per-run work is the CONFIGURE block at the top.
  Worth copying rather than re-deriving: these are the rules the ten parallel wave-4 agents
  all depend on, and a rule reconstructed from memory in a subagent holds by luck.
- `scripts/verify_report.py` — **delivery gate**: scans a generated `report.html` and FAILS
  (non-zero exit) when the **full canonical section set** is not present (condensed report), or
  the mandatory visuals are missing (interactive charts + message creatives), plus recommended
  checks (CSV export, Flight Deck links, data appendix, and **generated-vs-embedded charts** —
  warns when a `specs.json` chart was never embedded). Also catches the two silent-failure
  classes: a **localisation lint** and **undefined layout CSS classes** (a builder class with no
  rule loses its layout with no error). The localisation lint runs on **bilingual and
  monolingual** reports alike — monolingual ones are keyed on `<html lang>`, so set it — and
  flags English strings (explicit known leaks *plus* a generic English-prose detector that
  catches a whole block rendered by a helper called without `lang=`), English decimal marks,
  and **French words shipped without their accents**. Text inside `<code>`/`<pre>`/`<script>`
  and cells marked `data-verbatim` (raw client sample values) is exempt by construction.
  Canonical set imported from
  `canonical_sections.GATE_SECTIONS`. Auto-run by `report_framework.write_report`; also runnable
  standalone before delivery. `--sections-min N` tunes the structure floor (default 16),
  `--allow-no-creatives` only for accounts with nothing decodable.
  **`--profile goals`** enforces the mode B contract instead: the 11 goals sections, ≥3
  charts, exec summary ≥1 hero band, and it drops the checks that have no meaning without
  the Reports API (channel-adoption matrix, feature scorecard, prior-period deltas,
  creatives) or without a second language (localisation lint). Everything that protects
  quality regardless of mode — thin sections, recommendation count, insight callouts,
  CSV export, undefined CSS classes, empty `<img>`, charts generated vs embedded — still
  blocks.
- `scripts/goal_candidates.py` — **mode B's engine, fully deterministic** (no network, no
  model): turns `inventory.json` + `analysis.json` into `goals.json`. Builds the three
  families (`event_candidates` / `tag_candidates` / `subscription_candidates` from what
  the client collects, `native_candidates` for the zero-instrumentation Airship signals,
  `roadmap` for the vertical archetypes that are missing), matches every custom event
  against the Airship predefined catalogue (exact → alias → fuzzy, FR aliases included),
  then applies the decision layer: `antipatterns()` (technical/debug, descriptive state,
  screen noise, consent plumbing, negative signals like `uninstall` or `logout`, and
  duplicate concepts) with an explicit exclusion reason, per-candidate `config_modes`
  (`count` / `frequency` / `numeric_property`, the last only when a real **magnitude**
  property exists — an id or a code gets a blocker, not a threshold), `prioritise()` into
  north star / primary-per-stage / secondary plus the **blind funnel stages**,
  `instrumentation_route()` (SDK vs server-side, with the effort), and the client
  questions for every ambiguous candidate. Also emits `attributes` (the future
  attribute-based goals) and a `facts` brief in mode A's schema. Self-test: run it with
  no arguments.
- `scripts/airship_goal_sources.json` — the catalogue behind that engine: the Airship
  predefined events with their property templates and FR/EN aliases, the non-event goal
  sources (tags, subscription lists), the native signals, the configuration modes, the
  goal reports, the anti-pattern rules (tokens + `exactNames`), and the product caveats.
  Edit the JSON to teach the engine a new signal — no code change.
- `scripts/goals_charts.py` — the three mode B charts (funnel coverage, value
  instrumentation, configuration modes), PNG + Chart.js spec, from
  `goals.json`. Reusable as-is: `python goals_charts.py work/<client>/goals/goals.json`.
- `scripts/build_goals_template.py` — **mode B builder scaffold** (`cp … work/<client>/goals/build_report.py`):
  the 12 goals sections pre-wired to the framework, every table/board/chart already
  populated from `goals.json`, monolingual English, no PDF button, gate run at build time
  under `--profile goals`. What is left to write is the prose marked `TODO`.
- `scripts/import_benchmarks.py` — parse an Airship UA Benchmarks `.xlsx` → regenerate
  `benchmarks.json` + `benchmarks.md` (run once per new quarter).
- [event_catalog.md](event_catalog.md) + `event_catalog.json` — best-practice custom
  events & attributes per vertical (Airship "Data Collection by Vertical"): category,
  `kpi_kind`, `is_conversion`, `value_property`/`currency` flags, and the benchmark→book
  vertical map. Powers custom-event classification, conversion-KPI detection and
  data-collection opportunities. Refresh with `scripts/import_event_catalog.py`.
- `scripts/import_event_catalog.py` — parse the "Data Collection by Vertical" `.xlsx` →
  regenerate `event_catalog.json` + `event_catalog.md`.
- `scripts/event_analysis.py` — custom-event contextualisation (no network):
  `aggregate_custom_events` (direct/indirect/unattributed split of count+value),
  `classify_event` (catalog match + confidence), `detect_conversion_kpis`
  (business/usage/loyalty), `detect_monetary_value` + `currency_for_brand` (amount vs
  counter + probable currency), `opportunity_gaps` (send-more / enrich-value). Entry point
  `analyze(events, vertical, brand, region, country, currency)`.
- `scripts/event_attribution.py` — per-campaign attribution of the conversion KPIs via
  `events/summary/perpush|pergroup` (`attribute_campaigns(api_get, campaigns, analysis)`);
  network-agnostic (pass an `api_get` callable), tolerant of 401/403, min-volume floor.
- `scripts/classify_campaigns.py` — normalize message names, group, detect cadence; tag each campaign one-shot vs automated/recurring.
- `scripts/campaign_inventory.py` — **canonical multi-channel campaign inventory (no network)**:
  `build_inventory(push_campaigns, email_sms_campaigns, events)` unifies push/MC/email/SMS
  (message-first) + complementary in-app/MC CTA signals (`extract_inapp_campaigns`, tagged
  `source:"cta_only"`) into one list with **no lossy drops**; `split_events(events)` separates
  behavioural `location:custom` events (for `event_analysis`) from in-app campaign events;
  `bucket_long_tail` is a display-only volume floor; `detect_lang` FR/EN hint.
- [campaign_playbook.md](campaign_playbook.md) + `campaign_playbook.json` — best-practice CRM
  campaign **levers by strategic pillar × vertical** (bilingual EN/FR aliases, default
  typology, channels, per-vertical relevance, and per-pillar business stakes/key figures).
  Powers purpose classification, pillar maturity and new-campaign recommendations. Edit the
  JSON to add levers/verticals; regenerate the `.md` companion from it.
- `scripts/campaign_purpose.py` — maps each campaign to a **pillar + lever**, **language-aware
  & high-recall** (FR/EN detection, alias stemming + shared-prefix tolerance, pillar-priority
  disambiguation), name-first with content fallback via decoded pushbodies. Emits a numeric
  **`reliability` (0-1)** + High/Medium/Low per mapping (message name > body > `cta_only`), then
  computes `pillar_maturity` (coverage counted at reliability ≥ 0.45), `automation_mix` and
  `recommend_campaigns` (network-agnostic). Entry point
  `analyze(campaigns, vertical, bodies, reachable)`; consumes the `campaign_inventory.py` /
  `classify_campaigns.py` output.
- `scripts/data_foundation.py` — **OPTIONAL tagging-plan audit enrichment (no network)**:
  consumes the **built-in tagging-plan** outputs (`inventory.json` +
  `analysis.json`; run the vendored `parse_tagging_plan.py`+`analyze_tagging_plan.py` first, or
  pass a raw export to `load(raw_path=…)` which runs them). `load(...)` returns an `audit` dict with
  `available` (False ⇒ every helper returns a neutral result, report unchanged). Helpers:
  `build_foundation`/`foundation_scorecard` (compact summary), `cross_reference_conversion`
  + `value_index` (audit-backed value/currency per KPI + tracked-not-fired),
  `personalization_ladder_from_audit`, `lever_data_readiness`/`annotate_recommendations`
  (activatable-now vs needs-collection), `data_collection_recos` (gaps + Airship goal
  opportunities, pillar-tagged). Pairs with `report_interactive.data_foundation_block(...)`.
  Parse/analyze are vendored in this skill's `scripts/` (self-contained); set
  `$TAGGING_PLAN_SKILL_DIR` only to override. Client data only (`ua_*` excluded); `value` ≠ currency.
- `scripts/parse_tagging_plan.py` — **vendored**: normalize a raw RTDS tagging-plan export into a
  client-only `inventory.json` (`ua_*` filtered out). Stdlib only.
- `scripts/analyze_tagging_plan.py` — **vendored**: taxonomy/intents, value-bearing + monetary,
  data-driven vertical score, gaps vs best practices → `analysis.json`. Reads
  `data-collection-by-vertical.json` at the skill root (`--vertical` overrides the auto-guess).
- `data-collection-by-vertical.json` / `.md` — **vendored** best-practice reference (recommended
  events/attributes per vertical) used by `analyze_tagging_plan.py` for the gap analysis.
- `scripts/activity_log.py` — normalize activity-log rows, merge with `responses/list`
  (`merge_push_inventories`), flag one-shot broadcast candidates for push reach rankings.
- `scripts/channel_activity.py` — per-channel activity from `/sends`+`/devices`+`/events`
  (`channel_summary`): detects every active channel (email even at opted_in=0), builds the
  **email funnel from standard events** (`email_funnel_from_events`), and classifies each
  channel's **automated-vs-one-shot cadence** (`daily_cadence`).
- `scripts/event_analysis.py` also exposes `value_measurability(events, monetary)` — the one
  graded verdict on whether conversions can be tied to an amount (`revenue` / `partial` /
  `declared_not_flowing` / `counters`), rendered by `ri.value_measurability_block()` in the
  events section and repeated in the summary by `ri.value_measurability_line()` when nothing
  carries an amount. Both gate-enforced.
- `scripts/campaign_inventory.py` also exposes `scene_instrumentation_from_audit(A)` — the
  Scene instrumentation grade (named buttons / screen transitions / the app's own events),
  rendered by `ri.scene_instrumentation_block()` at the head of §8b, which becomes mandatory
  as soon as the audit records in-app volume.
- `scripts/coverage.py` — `assess(collect_manifest, audit)`: grades the run (`full` /
  `partial` / `degraded`) from the per-stage record and lists what it cannot claim, keeping
  this run's accidents apart from the **permanent** blind spots of the `rpt` scope (journey
  steps, A/B declarations, Scene funnels). Rendered by `ri.coverage_banner()` at the top of
  the executive summary; the gate requires it there, on clean runs too.
- `scripts/opportunity.py` — turn a measured gap into a sized one: `size_rate_gap`
  (what the lagging platform would return at the leading one's rate), `size_pressure_headroom`
  (distance to the peer median, in sends/month), `format_sized` (the figure **with** its
  formula and its caveat). Used in §4, §5 and §16 so a finding arrives already valued.
- `scripts/report_interactive.py` — interactive-HTML toolkit: `composer_id_from_pushbody`
  (`options.__ui_id`) + `flight_deck_url`/`flight_deck_button` (deep-links), `push_features`
  (feature/adoption + best-practice detection), the `INTERACTIVE_CSS`/`INTERACTIVE_JS`
  web-app scaffold + `interactive_head(layout="dashboard")` (sidebar + scroll-spy + fluid
  main column),   `tooltip`/`collapsible`/`gauge`/`verdict_pill`/`reliability_pill` (0-1 mapping-reliability
  pill)/`pdf_download_button`
  components, `methodology(...)` + `kpi_card(...)` (per-KPI "how it's computed" modals),
  `creative_push_preview(...)` + `creative_mc_preview(...)` (phone-sized MC viewport),
  the **account-profile components (canonical §2, GATE-ENFORCED — never drop)**
  `channel_adoption_matrix(rows, lang)` (channel × status × 30d volume × opt-in base) and
  `feature_adoption_table(rows, lang)` (Airship feature × adoption pill × evidence, + optional
  `upsell=` note) — build them for EVERY account from the Reports API channels/devices + the
  decoded creatives; the delivery gate FAILS if either is missing from the account-profile
  section, or if the executive summary carries <2 `hero_kpi_band` blocks,
  the **strategy/playbook components** `hero_kpi_band` (visual audience/usage intro with
  prior-period deltas), `priority_cards`, `strategy_matrix`, `pillar_coverage`,
  `automation_mix`, `personalization_ladder`, `data_foundation_block` (OPTIONAL tagging-plan
  audit summary; "" when no audit) + `data_collection_table(recos, lang)` (READABLE gaps/
  quick-wins TABLE from `data_foundation.data_collection_recos()` — priority / type / target /
  action / what-it-unlocks / pillar; NEVER dump the raw reco dicts as a bullet list)
  (deck-style consultative views, print-safe),
  the **data-appendix components** (end-of-file raw-data tables, searchable/sortable/CSV,
  print-safe with repeating headers) `audit_events_table`, **`audit_event_properties_table`
  (per-property type + distinct count + real sample values + the reserved `value` field —
  MANDATORY alongside `audit_events_table`)**, `audit_attributes_table`,
  `audit_tags_table`, `audit_subscriptions_table`, `audit_screens_table` (all consume the
  `AUDIT` dict from `data_foundation.load`; return "" when no audit) and
  `campaign_inventory_table(rows, lang)` (detected campaigns + classification: channel /
  typology / trigger / pillar / personalized / conversion / sends / reliability pill),
  and the interactive-chart helpers `chartjs_inline()` + `interactive_chart(id, png, spec,
  csv=…)` (canvas + CSV export on screen, PNG on print). Tables opt into search/CSV via
  `.ir-searchable`/`.ir-exportable`. **Custom-event rendering** helpers consume
  `event_analysis.py`/`event_attribution.py` output: `event_kpi_table`, `attribution_series`
  (→ `spec_donut`), `value_amounts_block`, `opportunities_tables`,
  `attributed_conversions_cell`, `confidence_pill`.
  The **mode B (Goals review) components**, all fed by `goals.json`:
  `goal_candidates_table` (source / predefined match / stage / occurrences / config modes /
  value / usable properties / blockers), `goal_config_table` (the exact Airship UI fields +
  the recommended mode), `goal_priority_board` (north star → primary → secondary),
  `goal_antipatterns_table` (what NOT to configure, with the reason),
  `funnel_coverage_matrix` (including the blind stages), `goal_eligibility_matrix`,
  `attribute_goal_candidates_table`, `discovery_questions` (the caller decides which
  questions reach the page; mode B passes those on the proposed goals). Pure stdlib.
- `scripts/airship_charts.py` — matplotlib PNG helpers (Airship palette) **and** JSON-safe
  Chart.js spec emitters that share the PNGs' data for the interactive canvases:
  `spec_pressure_fatigue`, `spec_timeseries_stacked`, `spec_funnel`, `spec_program_ranking`,
  `spec_donut`, `spec_grouped_bars`, `spec_hbar` (so every chart type can be interactive +
  CSV-exportable on screen). `stacked_bars()` is the print twin of a stacked
  `spec_grouped_bars` — use it whenever the spec stacks, or the PNG and the canvas will
  disagree.
- `scripts/vendor/chart.umd.min.js` — vendored Chart.js v4 (MIT; see `vendor/NOTICE.md`),
  inlined by `chartjs_inline()`; refresh via the curl one-liner in the NOTICE.
- `scripts/render_email.py` — render a real email / Message Center `html_body` to a cropped PNG.
  For MC/full-screen mobile templates use `width=375, max_height=720` (one phone screen).
- `scripts/render_mocks.py` — `fetch_media(url, out)` downloads a push hero image;
  `fetch_app_icon(brand, out, country)` downloads the REAL app logo (iTunes Search API by
  name; Google Play `og:image` for a package id) with a curl fallback; `render_push(notifs,
  out, app_icon=…)` renders notifications WITH the real image (5th tuple element) and the
  real app logo (`app_icon=`) — preferred for rich push; `render_card()` for MC/in-app.
  Text-only cards / the colored tile / reconstructions are a fallback only.
