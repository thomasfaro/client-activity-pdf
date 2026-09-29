# Scripts catalogue

Part of the [airship-engagement-review skill](SKILL.md). What each script does. Look a script up here when a step names it; do not load the whole catalogue up front.

## Dependencies
Python: `matplotlib`, `numpy`, `pillow`, `openpyxl` (benchmark import); `pymupdf` optional
(only for the PDF page-count sanity check in `build_report.py`); `cursor-sdk` optional
(only for `run_review.py`, which also needs `CURSOR_API_KEY`).
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
  both of those versions unusable. It also advises (`?`) when a published KPI's definition
  file (`build_facts.KPI_DEFINITIONS`) is not routed to the section
  (`canonical_sections.REFERENCE_ROUTING`): the writer published a number whose definition
  it was never handed.
- `scripts/run_review.py` — **the review as a program** on the Cursor SDK: waves,
  semaphore of three, freeze hashes, per-turn file-scope guard, bounded check / gate-fix
  loops, verdict ledger, mandatory coherence pass, checkpoints, `run_state.json` resume
  (`--from`, `--stop-after`), mode B (`--mode goals`), `--model role=spec` (one-run model
  trial, kept on resume), `--context` (the brief; numbered questions switch on the focused
  review), tokens and duration per session in `run_state.json`, `--dry-run`,
  `--check-sdk`. See
  [orchestration.md](orchestration.md#running-it-as-a-program--run_reviewpy). Its
  `--selftest` plays a whole run against fake agents.
- `scripts/prompts/*.md` — the agent prompts, one per role, with `{{placeholders}}`;
  `run_review.render_prompt` refuses one left unfilled.
- `scripts/focus_brief.py` — parses the account team's brief (`--context`, see
  [brief-template.md](brief-template.md)) into objective, definitions, scope, hypotheses,
  decision and numbered questions. Questions make the review focused; none keeps it global.
- `scripts/focus_plan.py` — the focused review's contract. `--check work/<client>`
  (pre-flight): every brief question is in `focus_plan.json`, its sections are canonical and
  `lead`, its facts exist (a facts.json KPI or `audit:<dotted.path>`), every mandatory
  section has a depth, an unanswerable question has a reason. `--check-answers` (after
  §3a): every question has an answer, a valid confidence and checkable facts. Also renders
  the depth and focus lines the prompts carry. Exit 1 on any problem.
- `scripts/verdict_ledger.py` — merges `verdicts/<key>.json` into `verdicts.json` and
  reports opposite directions on one axis and one KPI cited two ways. Exit 1 on conflict.
- `scripts/compare_reports.py` — before/after comparison of two reports (sections, gate
  counts, KPI cards against facts, KPIs shown two ways, verdict conflicts, length per
  section), plus tokens, agent time and models when a `run_state.json` sits beside each
  report; the instrument of the before/after protocol and of a model trial.
- `scripts/check_links.py` — every relative markdown link and `#anchor` in the skill and
  `.cursor/agents/` resolves; run by `run_selftests.py`.
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
  `classify_campaigns.py` output. `classify_one(..., category_signal=)` applies a tested
  client-category reading (basis `category`) under the rules of `campaign_categories.py`.
- `scripts/campaign_categories.py` — **client categories as a classification signal (no
  network)**: coverage, deterministic scheme inference (facets / positional codes /
  `key:value` / free labels, per-position roles, multilingual lexicon from
  `campaign_playbook.json → category_lexicon`), readings tested on lexical fit, name
  agreement, behaviour, position and support → confidence + tier; per-category performance,
  name/category alignment, vendor clues (SFMC, Adobe, Braze…). Entry point
  `enrich(campaigns, vertical, bodies, decoded, groups_decoded, hypotheses, reachable)` →
  `(audit.purpose, audit.categories)`. CLI: `prepare work/<c>` (writes
  `category_schema.json` for the frontier reader, `prompts/categories.md`),
  `validate work/<c>` (checks `category_hypotheses.json`), `analyze work/<c>` (summary).
  Self-test: `python scripts/campaign_categories.py`.
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
  typology / trigger / pillar / personalized / conversion / sends / reliability pill; a
  client-category column and a "via category" mark when rows carry categories), the
  client-category components `category_scheme_card`, `category_hypotheses_table`,
  `category_performance_table` (with its methodology), `category_alignment_table` (all read
  `audit.categories`, return "" when absent),
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
