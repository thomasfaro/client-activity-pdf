# Report structure — mode A

The section-by-section content specification for a full engagement review. The
*spine* (which sections exist, which are mandatory, their numbering and anchors)
lives in `scripts/canonical_sections.py` and is the single source of truth shared
with the delivery gate; this file says what goes *inside* each one.

## Report structure (mandatory spine + optional sections that earn their place)
> **Completeness rule (do not regress).** The strategic-consulting sections (3a headline KPI
> band, 3c strategic priorities + maturity matrix, 7b playbook & coverage, and the pillar-based
> recommendations) **AUGMENT** the full canonical structure below — they **never replace** the
> standard deep-dive sections (account profile, volume & pressure, engagement, permission,
> per-channel campaign analysis, conversion & impact, events, experiments, creatives,
> best-practices, appendix). A report that ships only the strategic layer (as an early retail
> draft did) is **incomplete**. If a section's data is genuinely unavailable (inactive channel,
> firehose account with aggregate-only push, sampled events), **keep the section and mark it
> N/A with the reason + how to enable it** (e.g. "email inactive: 0 devices", "push per-message
> unavailable: pulled at aggregate level"); do **not** silently drop it. Build from the
> chart-heavy template (`include_charts=True`) and insert the strategic components.

Delivered as an **interactive HTML web-app** on screen (fixed sidebar with auto TOC +
scroll-spy, Download-PDF and Expand/Collapse-all; fluid reading column; tooltips,
collapsibles, benchmark gauges; **per-KPI methodology modals** (every section); searchable/sortable/
exportable channel tables; per-chart **CSV export**; per-message **Flight Deck** buttons)
with a print stylesheet that produces the paginated **PDF companion** from the same file.
1. Cover (Airship branding) · 2. Brand & business context (sources) ·
2b. **Account profile & Airship adoption** (channel-adoption matrix, feature-adoption
   scorecard from decoded pushbodies, inferred use-cases, adoption gaps / upsell for Airship) ·
2c. **Data foundation & tracking coverage** (ONLY when a tagging-plan audit was supplied —
   `data_foundation_block`: breadth of tracked events/attributes, tags & subscription lists,
   SDK/API split + storage verdict, vertical coverage %, value/currency instrumentation rate;
   omitted entirely when no audit) ·
3. Executive summary (**opens with `ri.coverage_banner()`** — what the collection covered
   and what no review of this kind can claim; then the verdict, KPIs with snapshot/period
   labels, **vs industry benchmark where available (visual gauges), else vs internal
   same-type baseline**, tags + confidence) ·
3a. **Headline KPIs (visual intro)** — audience (app contacts, opt-in app, opt-in email,
   active users) + usage (push / in-app / email sent) as a `hero_kpi_band` with
   **prior-period deltas** (or the delta limitation stated); front-and-centre, each KPI keeps
   its methodology modal. **Never ship the executive summary without a visible
   period-over-period comparison** — even for a campaign / event-window analysis, compare the
   window to the **equal-length prior baseline** (e.g. a tournament window vs the pre-tournament
   window, or 30d vs previous 30d) and show the deltas as `hero_kpi_band` pills, not
   buried inside a methodology modal ·
3b. **Benchmark scorecard** (gauges per benchmarked KPI: p10–p90 band, p50, client value +
   verdict) · **Reachability** (per channel: unique devices, opt-in devices, and a **single
   opt-in %** — do NOT show two near-duplicate opt-in columns like "% of uniques" AND "%
   messageable"; pick the one meaningful denominator and define it in the footnote) ·
3c. **Strategic priorities & maturity matrix** (vertical-aware, brand-tailored): the 3–4
   strategic priorities for this brand (`priority_cards`) + a typology **maturity matrix**
   (`strategy_matrix`: pillar × business stake × key figure × current maturity) ·
4. Volume & channels / **marketing pressure — cross-platform, per-platform, per-month vs
   benchmark, fatigue (pressure vs opt-out/opens), temporal distribution, frequency
   governance** (period) · include the **per-channel activity table** from `channel_summary`
   (every active channel: sends, reachable base, automated-vs-one-shot cadence) ·
5. Engagement (opens, period) ·
6. Permission & installed base — **two blocks: snapshot/whole-base (rate, base) vs period
   opt-in/opt-out event flows** ·
7. Campaign typology — one-shot vs automated/recurring **per channel** (push: per-campaign
   counts/mix/recurring trends; email/SMS: channel-level cadence signal with confidence) ·
7b. **Campaign playbook & coverage (fully developed — not just a ladder)** — purpose/pillar
   classification of what the client runs. Include **both**: `pillar_coverage`
   (already-done ✓ vs recommended levers per pillar, with coverage % + maturity) and
   `personalization_ladder` (identity / behaviour / context depth). In `pillar_coverage` the
   **"recommended" column must be sector/brand-adapted best-practice use cases** — written as a
   marketer of THIS brand (its loyalty/programme, purchase & basket data, fulfilment options,
   monetisation, current strategy), not the raw generic lever names. **Do NOT** include the
   `automation_mix` "today vs target" industrialisation block (dropped for confusing readers;
   the one-shot vs automated read lives in the per-channel typology §7 and, if useful, as one
   account-level recommendation). This is a centrepiece: give every pillar concrete
   already-running levers AND concrete new-campaign recommendations tailored to the brand
   (see the reference reports under `work/` for the depth expected) ·
8. **Conversion & business impact** — conversion event taxonomy (the client's conversion
   KPIs), push-attributed funnel (view → cart → purchase), attribution rate, and the
   **two impact rankings** (top campaigns by engagement AND by attributed conversion). ·
   **MONETARY VALUE (revenue) — treat as a first-class, high-value signal.** Detect whether
   the client collects currency amounts via `data_foundation.monetary_summary(AUDIT)` (audit
   `monetaryValue` / `valueBearing.carriesAmount` / `eventProperties[].valueField.carriesAmount`)
   **and** `cross_reference_conversion` (`carries_value`/`carries_currency`) and Reports
   `/events` `value` **only when the audit/context confirms it behaves as currency** (Airship
   `value` defaults to a *counter*, not money — never assume revenue). **When monetary data IS
   collected**: surface it front-and-centre — a **revenue / attributed-value / AOV KPI in the
   executive summary `hero_kpi_band` (with prior-period delta)** and in the verdict, then
   **valorise it maximally**: push-**attributed revenue**, revenue per send/opt-in, a **top
   campaigns by attributed monetary value** ranking, and **conversion-value evolution vs the
   prior period**. **When it is NOT collected**: flag it as the single highest-value
   measurement **gap** ("value is a counter, no revenue attributable") in the exec
   summary, the events appendix and the recommendations. **The verdict itself is not prose:
   close the gaps discussion with `ri.value_measurability_block()` (gate-enforced), and when
   it grades `counters` or `declared_not_flowing`, repeat it in the executive summary with
   `ri.value_measurability_line()`** — see reference.md, "Value measurability". ·
9-10. Events deep dive (taxonomy, attribution, families, value-bearing events + per-message
   attribution, hygiene) ·
11. Experiments (variants/winner, or "none detected") ·
12. Creative coverage (Reports-only: recoverable vs illustrative share from pushbodies;
   UNICAST limitation stated) ·
13-15. **Campaign analysis (robust) — COMPARTMENTALIZED BY CHANNEL** — the centrepiece.
   One clearly-labelled section per channel; **push and email are never in the same table,
   ranking or matrix**:
   **13. Push campaigns** — (a) a **push-only platform × type matrix** (rows = iOS / Android /
   web; cols = BROADCAST / SEGMENTS / TAG / UNICAST / A_B) with counts, reach and typical
   rates; (b) **two push rankings** — a **reach ranking** (by sends) AND an **engagement
   ranking** (by influenced/direct rate, min-volume floor) — each entry with a **real preview**
   (hero image via `render_push` **with the real app logo**), per-platform (iOS/Android) rate
   breakout, and its **benchmark position** (`[Data]` vs industry, or `[Internal baseline]`);
   reach ranking **must include every activity-log-only broadcast** above the min-volume floor;
   (c) short profile per message type (one-shot vs automated/recurring; recurring trends);
   (d) **push programs** — per-program table/chart from `pergroup/detail` (sends, rates,
   platform split), seeded by distinct `group_id`s from the merged inventory **and**
   `type: GROUP` activity-log rows.
   **14. Email program** — its own section (never blended with push). Always present when
   email is active in `/sends` (even if `/devices` opted_in=0). Build the **aggregate email
   funnel from Airship standard events** (`channel_activity.email_funnel_from_events`):
   delivered, opens (`initial_open`), clicks, and delivery/open/CTR/CTOR/bounce/spam/
   unsubscribe rates vs `[Internal baseline]`, plus the automated-vs-one-shot **cadence**
   signal. **Open with `ri.email_reconcile_note(A["channels"]["email"]["reconcile"], lang)`**
   — the two volume counters disagree, and the gate blocks an active §14 without it. Add a **per-message table** (sends / opens=`influenced_responses` /
   clicks=`direct_responses`, `render_email` preview) **when the user supplied email
   message/group IDs**; otherwise state the per-message limitation prominently and keep the
   funnel. Creatives chosen by the **stated objective rule** (measured perf with IDs; else
   lifecycle coverage from message names), never "by looks".
   **15. SMS / In-app / Message Center** (each only if present) — separate labelled blocks;
   SMS per-message from `perpush/detail` top-level when IDs known else aggregate; in-app/MC
   reach + read/dismiss from `/events` `location`, vs internal same-type baseline.
   **§8b is mandatory as soon as the audit records in-app volume, and must OPEN with
   `ri.scene_instrumentation_block()`** (both gate-enforced) — see reference.md, "Scene
   instrumentation". ·
   Flag any absent channel; do not blend channels to fill a table. ·
15b. **Engagement best-practices scorecard** (Good/Average/Poor per practice: rich push %,
   deep-link %, personalization %, A/B adoption, lifecycle coverage, MC-paired push, copy
   hygiene; email open/click/CTOR/opt-out vs internal baseline). **OPTIONAL** — the same
   scorecard for every account, and its account-specific reading already lives in §3c and
   §16. Ship it when the client team wants the artefact; omit it rather than shipping it
   half-filled. ·
16. **Recommendations — organised by the 6 strategic pillars** (Editorial, Onboarding &
   Adoption, Service, Lifecycle, Engagement & Data, Commercial). For each pillar: **(a) TARGETED**
   actions on existing campaigns (tied to a specific finding above + expected lever) and
   **(b) NEW campaigns to launch** — **tailored to the brand's business model & current context**,
   not generic vertical levers. Treat `recommend_campaigns` gap levers as a STARTING POINT and
   **rewrite each as a concrete, brand-specific proposal**: research the brand (business model,
   loyalty/monetisation mechanics, recent news, strategic priorities, challenges, competitors)
   and be a force of proposal so every idea is genuinely relevant to THIS brand. Tie each to the
   detected coverage gap and the business stake it serves (**when an audit is present**, mark
   each **activatable now** vs **needs data collection** via
   `data_foundation.annotate_recommendations`). Plus **(c) GENERAL / account-level** actions
   (strategy, cadence, **industrialization** one-shot→automated, data & A/B, measurement,
   roadmap) — including a **"Data & measurement"** thread fed by `data_collection_recos`
   (collection gaps + Airship goal opportunities) **when an audit is present**. Each tagged +
   confidence.
   **Close the section with `ri.action_plan_table(rows, lang)` — Action / Horizon / Expected
   impact / Evidence — and the gate blocks §16 without it.** Prose recommendations do not
   sequence and do not say what each one is worth, which is what a reader needs to turn the
   review into a plan. Size the impact with `opportunity.py` and cite it in the evidence
   column: a row stating an impact with no evidence raises at build time rather than
   shipping, because a plausible unsourced number is the most quotable line in a review and
   the least defensible. An action that genuinely cannot be sized leaves `impact` empty and
   renders as "not sized" — honest, and visibly so. Horizons come from
   `ri.ACTION_HORIZONS` so two accounts' plans read on one scale. ·
17. Appendix: sources, definitions, **methodology (verification & confidence scale)**, glossary, endpoints.
18. **Data appendix (end of file) — the raw data every analysis is built on, so a reader can
   audit it.** Always present. Use the reusable `report_interactive` helpers (all
   searchable/sortable/CSV-exportable on screen, and print-safe with repeating table headers):
   - **Tracked events** — `ri.audit_events_table(AUDIT, lang)`: **every** custom event with its
     categorisation (source SDK/API, behavioural **category/intent**, occurrences, the state of
     the reserved `value` field, and its **property names**). Add a monetary callout above the
     table (`data_foundation.monetary_summary`): valorise it if currency amounts are collected,
     else flag the revenue-measurement gap.
   - **Collected property values** — `ri.audit_event_properties_table(AUDIT, lang)`,
     **GATE-ENFORCED whenever the events table is rendered.** One row per (event, property)
     with its inferred **type**, distinct-value count and **real sample values**, plus a row
     for the reserved `value` field. See "Events appendix: names are not evidence" below.
   - **Tracked attributes, tags, subscription lists, screens** — `ri.audit_attributes_table`,
     `ri.audit_tags_table`, `ri.audit_subscriptions_table`, `ri.audit_screens_table` (attributes
     get a heuristic category column).
   - **Detected campaigns & classification** — `ri.campaign_inventory_table(rows, lang)`: every
     detected campaign with channel · typology (one-shot vs automated) · trigger · **pillar** ·
     personalized · conversion · sends · **reliability** score. Feed it from the canonical
     campaign inventory / `campaign_purpose` output; for firehose accounts build rows from the
     marquee broadcasts + automation programs + email broadcasts.
   The events/attributes/tags/lists/screens tables come from the tagging-plan **audit**
   (`data_foundation.load` → `AUDIT`); **omit those blocks (graceful degradation) when no audit
   was supplied**, but always keep the detected-campaigns table and a note that every chart's
   data is CSV-downloadable.
