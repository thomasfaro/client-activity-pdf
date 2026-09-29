# Reference — Custom events, value, tagging-plan audit enrichment, Airship Goals

Part of the [reference index](../reference.md). Read the files the index routes to your task, not the whole folder.

## Custom-event contextualisation, conversion KPIs & value

Custom events (`location: custom`) are analysed by `scripts/event_analysis.py` against the
best-practice **event catalog** (`event_catalog.json`, imported from the Airship "Data
Collection by Vertical" workbook with `scripts/import_event_catalog.py`). Pipeline:

1. **Aggregate** by name, excluding the standard email funnel events (kept in sync with
   `channel_activity.EMAIL_EVENT_FUNNEL`). Per event: total count/value and the
   `direct`/`indirect`/`unattributed` split of **both** count and value, plus attribution
   rates and `value_per_event`.
2. **Classify** each event against the vertical's catalog (`classify_event`): name tokens +
   bilingual EN/FR aliases → a matched catalog event/category with a **confidence** level
   (High = normalised-name match, Medium = ≥2 shared concepts, Low = 1 shared concept /
   name-token conversion hint). Vertical is resolved via `vertical_map` (fallback
   `all_verticals`); the client's vertical events are **merged over** `all_verticals`.
3. **Conversion KPIs** (`detect_conversion_kpis`): flagged when the matched category is a
   conversion/consumption KPI. `kpi_kind` = **business** (Purchase, Add to cart,
   Transaction success, Reservation, Activation, Acquisition), **loyalty** (points/tier),
   or **usage** (Consume content, Feature usage…). For each KPI, `conversion` gives
   Airship's measured contribution: direct (tap), indirect (received recently, no direct
   tap), unattributed.

### `value` — amount vs counter (heuristic, not currency)
`value` is a **client-declared number, never guaranteed to be currency.**
`detect_monetary_value` reads it per event from `value_per_event = total_value/total_count`:
- `value ≈ count` (avg ≲ 1.5) → **per-event counter**, NOT an amount (e.g. a retailer's
  `add_to_cart_web`) → no monetary read.
- avg ≥ 3 (varied) → **looks like an amount** (Medium; ≥ 5 → High). e.g. a retailer's
  `passage_commande` avg ≈ 100 → order amount.
- 1.5–3 → ambiguous (small quantity?) → not treated as money (Low).

When monetary, `currency_for_brand(brand, region, country, override)` assigns a **probable
currency** (country → currency; else region eu→EUR / us→USD), **exposed as an assumption**
with a confidence and **overridable** via config (`--currency`). The report then shows the
**direct/indirect attributed amount** vs unattributed per KPI. Always restate the caveat.

### Data-collection opportunities (`opportunity_gaps`)
- **Send more**: catalog events recommended for the vertical but not detected in the period
  (conversion-bearing ones first) — "send this to Airship".
- **Enrich with value**: conversion events the client *does* send but **without a monetary
  value** (e.g. a purchase event with no amount) — "add the amount (+ currency) so Airship
  can attribute revenue". Each opportunity carries a confidence level.
## Data-collection audit (tagging plan) enrichment (OPTIONAL) — `scripts/data_foundation.py`
An optional layer that cross-references the client's **data-collection audit** (RTDS tagging
plan) with the Reports-API engagement analysis. Parsing + analysis are **built into this
skill** (vendored `scripts/parse_tagging_plan.py` + `scripts/analyze_tagging_plan.py`, from
the `datacollection_audit` project — no separate skill needed):
- `parse_tagging_plan.py` → `inventory.json` — the client-only taxonomy (custom events,
  attributes, tags, subscription lists, screens; **`ua_*` Airship-managed data excluded**).
- `analyze_tagging_plan.py` → `analysis.json` — event **intents**, **valueBearing** /
  **monetaryValue** (amount + inferred unit), **conversionSignals** (event → suggested goal),
  **provenance** (SDK vs API source, contact vs device storage, real-time vs batch cadence),
  and **gaps** vs the vertical's recommended attributes/events (present/partial/missing + %).

`data_foundation.load(analysis_path=…, inventory_path=…)` (or `load(raw_path=…, vertical=…)`,
which runs the two vendored scripts) returns an `audit` dict; **`audit["available"] == False`**
⇒ every helper returns a neutral value and the report is unchanged (**graceful degradation**).
It never re-implements the parser/analyzer — one source of truth for the schema. Process
**every** item (no top-N).

**What it enriches**
- **Conversion (fact, not heuristic).** `cross_reference_conversion(reports_events, audit)`:
  per Reports conversion KPI → `tracked_in_audit`, `carries_value`/`carries_currency`,
  `inferred_unit` + `unit_confidence`, `missing_value`; plus `tracked_not_fired` (conversion
  events designed/tracked but with no firing in the window). `value_index(audit)` →
  `event_analysis.analyze(audit_value_index=…)`: the "enrich value" verdict is decided from
  the tagging plan (does the event already carry an amount/value property?) instead of the
  count/value heuristic — fewer false positives, `audit_backed=True` on the flagged ones.
- **Maturity (data-driven).** `personalization_ladder_from_audit(audit, lang)` builds the
  3-level ladder from the **real** attributes/events/tags/lists (identity / behaviour &
  content / context & prediction). `lever_data_readiness(recos, audit)` +
  `annotate_recommendations(recos, audit)`: for each recommended lever, is the required data
  already tracked (`abandoned_cart_commercial`→cart events, `birthday_anniversary`→birthdate…)
  → activatable-now levers surface first, with evidence.
- **Recos (collection + activation).** `data_collection_recos(audit, lang)` turns **every**
  gap (missing/partial) and **every** `conversionSignal` into pillar-tagged items:
  `track_event` / `enrich_event` / `collect_attribute` / `add_value` / `activate_goal`
  (Airship goal opportunity). Mapped to the 6 pillars via event intent; capped at **Medium**
  confidence, tagged `[Data]` / `[Data+Context]`.
- **Compact block.** `report_interactive.data_foundation_block(build_foundation(audit), lang)`
  renders the "Data foundation & tracking coverage" section (breadth, tags/lists segmentation,
  SDK/API split + storage verdict, vertical coverage %, value/currency instrumentation rate);
  returns "" when no audit.

**Caveats.**
- Custom-event `value` is a **client-declared counter, NOT currency**; currency/unit is
  **inferred** from the amount distribution (two-decimal ⇒ major currency unit; integers are
  ambiguous). Always keep the caveat.
- The audit is a **tracking capture** whose time window differs from the 30-day activity — the
  cross-reference is by **event name** (design/instrumentation view, not a same-window join).
- Client data only (`ua_*` excluded, per the vendored parser). This layer is contextual → cap
  at **Medium** confidence, and it is lang-aware (EN default / FR).

### Per-campaign attribution (only when conversion KPIs exist)
`scripts/event_attribution.py` attributes the identified conversion KPIs per campaign:
`events/summary/perpush/{push_id}` (one push) and `events/summary/pergroup/{group_id}`
(a program). It filters each response to the KPI events, aggregates `direct`/`indirect`
count (+ amount when monetary), and attaches `attributed_conversions` to the campaign row —
enabling a ranking by **conversion impact** alongside engagement. Network-agnostic (pass an
`api_get` callable), tolerant of 401/403 (degrades to "attribution unavailable"), with a
min-volume floor. Restate the not-currency caveat on any amount.
## Airship Goals — what can be a conversion, and how it is configured
Reference for the **Goals review** (mode B), and for any conversion recommendation in the
full review. Source: <https://www.airship.com/docs/guides/reports/goals/>. The machine-readable
version of everything below is `scripts/airship_goal_sources.json`; the engine that applies
it is `scripts/goal_candidates.py`.

A **goal** is a measurable act Airship attributes back to a message. It is configured once
at project level and then available across Performance Analytics, per-message reporting and
Journeys. Three families, and the distinction is the single most common source of a wrong
recommendation.

### Family A — data the client already collects
Activatable **today**, because the data is in the tagging plan.

| Source | Notes |
|---|---|
| **Custom events** | The main family. `location:custom`, SDK- or server-sourced. |
| **Airship predefined events** | `purchased`, `added_to_cart`, `starred_product`, `shared_product`, `browsed`, `search`, `registered_account`, `logged_in`, `consumed_content`, `completed_level`… These are **not free**: they are a naming + property standard the client must *send*. Available only if the JSON contains the event, or one whose name matches closely. |
| **Tags & tag groups** | A tag applied to a channel can be a goal (loyalty enrolment, opted into a programme). |
| **Subscription lists** | Joining a list is a conversion in its own right. |

**Predefined names are a standard, not a capability.** If the plan has no `purchased` and
nothing that resolves to it, `purchased` is a tracking **gap**, never a shortlist item: it
belongs in the *not measurable today* column of the coverage matrix, not in the plan.
Conversely a close match (`commande_validee` → `purchased`) is worth acting on: renaming
to the standard buys the property template, not just the metric. Matching is
exact → alias (FR + EN) → fuzzy, and the engine records which.

### Family B — native Airship signals
Present for **every** project, absent from every tagging plan by construction, zero
instrumentation. This is where a "we have no conversion data" account still gets goals.

- **Channel registration** (`first_seen`) — the install/first-contact equivalent.
- **Notification opt-in** — the user enables push. Also `first_opt_in`.
- **Named user association** — the channel is linked to an account (login or account
  creation). The cleanest identity conversion available with no work.
- **App open** / **first open** — the baseline activation and re-engagement goal.
- **Web session** for web channels.
- **Uninstall** — a signal, but a **negative** one: never a goal.
- **NPS score**, via an Airship Scene survey.

### Configuration modes — orthogonal to the source
Eligibility says *what* can be a goal; the mode says *how* it is counted. Every candidate
should be recommended with one.

| Mode | What it counts | When to use it |
|---|---|---|
| **Count** | Any occurrence of the event. | The default, and the only sane mode for a rare, decisive act (a purchase, a registration). |
| **Frequency** | *N* occurrences over a **daily / weekly / monthly** period. | Habit and loyalty. Turns a high-volume event that would be meaningless as a count ("opened the app") into a real behavioural target ("opened the app 4× this week"). |
| **Numeric property threshold** | The event fired with a numeric property above a value. | Qualifies the conversion — basket over €50, session over 10 minutes, 80% of content consumed. Requires a **magnitude** property. |

Two traps on the numeric mode. A numeric property is not automatically a magnitude: a
`product_id`, a `store_code` or a `priority` is a number with no order that means anything
— there is nothing to threshold. And *time in app* is available natively, so a
duration-based goal needs no instrumentation at all.

### Anti-patterns — what to tell the client NOT to configure
A tagging plan is full of events that are excellent for segmentation and useless, or
actively misleading, as a goal. Name them explicitly with the reason; it is what makes the
shortlist credible.

- **Technical / debug**: `sdk_init`, `config_loaded`, `error`, `timeout`, `crash`.
- **Descriptive state, not an act**: `device`, `os_version`, `app_version`, `dark_mode` —
  what the device *is*, not what the user *did*.
- **Screen or impression noise**: a screen view is a page, not an intention.
- **Consent plumbing**: a CMP interaction is compliance, not conversion.
- **Negative signals**: `uninstall`, `logout`, `unsubscribe`, `cancelled` — optimising a
  campaign toward these is the opposite of the intent.
- **Duplicate concepts**: two events for the same act split the metric; pick one and say
  which.

### The goal reports you unlock
Worth naming in the report, because they are the payoff for configuring anything:
*Goal conversions over time*, *Channels per goal*, *Goal frequency per channel*,
*Goal attribution by message/journey*. In particular a tagging-plan export counts
**occurrences, not unique channels** — configuring the goal is precisely what turns that
into a per-user metric.

### Coming: attribute-based goals
Airship will support goals on **attributes**, not only events. Anticipate it: an attribute
that is a monotonic magnitude (loyalty points, lifetime value, tier, completion
percentage) is a future goal, and the client should be collecting it now. Numeric and
date attributes qualify; a free-text one does not.

### Product limits — do not quote a number
A project has a finite number of goal slots, and the exact figure moves between releases.
**Never print a maximum in the report.** It is an internal document, but a number on the
page is a number that gets repeated in the meeting, and this one goes stale between
releases. Say the ceiling exists, that it is why the plan is a hierarchy rather than a
catalogue, and tell the team to read the current number in *Reports > Goals* in the
dashboard.
