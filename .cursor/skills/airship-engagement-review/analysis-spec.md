# Analysis specification — step 4 of the mode A workflow

What to compute from the collected data, and what each metric actually means.
This is wave-2 material: it is read once, by whoever runs the analysis, and
produces `audit.json`. Section writers do not need it — they read `facts.json` and
their own audit slice. For the semantics of an individual Reports API metric, see
[reference.md](reference.md).

**RULE THAT APPLIES TO EVERYTHING BELOW — `audit.json` carries facts and enumerated
verdicts, never sentences.** A hand-typed sentence sitting next to the number it describes
ends up contradicting it. This is not hypothetical: one audit computed
`total_direct_responses: 96` while a prose field in the same block read "95 direct
responses in total" — six sections copied the prose, the summary read the calculation, and
the report shipped both. Another wrote `split_population_note: "…runs below p10 of the
panel"` for a rate of 1.38% against a p10 of 0.9%, and that claim reached two sections.

So: **any position against a band is derived from the band**, never asserted (`p10: 0.009,
value: 0.0138` → the renderer says where it sits). A judgement is an enumerated grade with
its inputs beside it — `{"grade": "counters", "valued_events": 0, "conversion_events": 14}`
— not `"verdict": "No event carries an amount."`.

Two consequences worth stating, because both were learned the expensive way:
- Every string field in `audit.json` is **internal working English**. It briefs the agent
  writing the section; it is never client copy. A section quoting one ships English into a
  French report, which is what `check_section.py --lang fr` now refuses.
- Where a sentence genuinely has to be pre-written — a caveat whose exact wording matters —
  write it as a `*_fr` / `*_en` pair beside the key it qualifies, and have `_shared.py`
  pick the language. That convention was invented mid-run on one account, worked, and was
  never carried back here; it is the only sanctioned exception.

### 4. Analysis
Cover all of the following (see `reference.md` for detection logic & definitions):

**Account profile & Airship adoption (help Airship teams understand the client)**
Open the analysis with a snapshot of **how this client uses Airship** — the primary lens
for a CSM/AM reader:
- **Channel adoption matrix**: for push (iOS/Android/web), email, SMS, in-app, Message
  Center, Scenes — active/inactive + period volume (`/devices`, `/sends`, `/events`
  `location`). A channel is active only if devices/sends > 0.
- **Feature-adoption scorecard** from the **decoded pushbodies** (use
  `report_interactive.push_features()`): personalization (`options.personalization` or
  `{{…}}` merge fields), **rich push** (% with a hero image URL), **deep-links**
  (`uairship://` actions), **Message Center pairing** (`message` body present / "P+I"
  naming), **A/B testing** (`push_type==A_B` in `responses/list`), **frequency governance**
  (`options.bypass_frequency_limits`), automations vs one-shot. Report each as
  used/not-used + a rough share.
- **Inferred business use-cases** from campaign names + event taxonomy (e.g. store
  reopening, loyalty, couponing, win-back). Tag `[Data+Context]`.
- **Adoption gaps / opportunities for Airship** (upsell lens): channels/features not used
  (e.g. email inactive, web push absent, no A/B, no Scenes, no rich push). Frame as
  concrete account-team opportunities, tagged with confidence.

**Permission & base (keep snapshot vs period separate)**
- Whole-base block (`/devices`): installed base, opt-in **rate**, opted-out, uninstalled
  per platform — all "(snapshot DD/MM)".
- Period block (`optins/optouts`): opt-in/opt-out **event** flows over the window — never
  framed as net base change, never equated to the snapshot counts.

**Marketing pressure (cross-platform AND per-platform) — a headline focus**
- Report **both** views (see `reference.md` → "Marketing pressure"):
  - **Cross-platform**: total sends (all channels) / weeks / total addressable base.
  - **Per-platform**: one figure per active channel (push iOS, push Android, push blended,
    email, web push, SMS…) = channel sends / weeks / that channel's own addressable base.
- **Match the denominator to the channel** (push → push `opted_in`; email → email base;
  web → web `opted_in`). If a denominator is unavailable (e.g. email = 0 active devices),
  show sends/week only and flag it. Call out channels far above/below the others
  (over-solicitation vs under-use). Tag "(period)".
- **Per month + benchmark**: also express pressure as **sends/opted-in user/month**
  (×~4.33 or recompute) and position it **per device family** vs `sends_per_user_month`
  from `benchmarks.json` (gauge). This is the pressure figure that maps to the benchmark.
- **Fatigue signal (engagement best practice)**: plot **pressure vs opt-out rate** and
  **pressure vs open rate** over the period; call out whether send-volume spikes coincide
  with opt-out/uninstall spikes or open-rate erosion (`/optouts`, `/devices`, `/sends`,
  `/opens`). Frame over-pressure as a churn/deliverability risk with a concrete cadence reco.
- **Temporal distribution**: hour-of-day / day-of-week send distribution from
  `responses/list` timestamps (night sends, quiet-hours respect) and the **peak
  concentration** (max sends/user in a single day), not just the average.
- **Frequency governance**: share of messages sent with `bypass_frequency_limits` — a
  high share means frequency caps are being overridden (governance flag).

**Campaign typology (one-shot vs automated/recurring) — Reports API only**
Report the one-shot vs automated/recurring split **per channel** — never a single global mix.
- **Push (per-campaign, High confidence):** classify every campaign with the reports-only
  heuristic (`scripts/classify_campaigns.py`: group by `group_id` + normalized `message_name`,
  detect cadence) on the **merged** activity-log + responses/list inventory. Do **not** call
  `/api/pipelines` or `/api/schedules`.
  - One-shot: reach, direct/influenced rates, creative.
  - Automated/recurring: per-occurrence volume, **volume drift** vs series median, and
    **engagement-rate trend** over time; flag drifts. (`pergroup/detail` or summed
    `perpush/detail`; `perpush/series` for shape.)
- **Email / SMS (channel-level, when no per-message list):** these channels are **not
  listable** from Reports, so classify the channel's typology from its **daily send cadence**
  via `channel_activity.daily_cadence(...)` — near-daily continuous volume ⇒ automated
  program (newsletters/lifecycle); sparse spikes ⇒ one-shot broadcasts. Label this a
  **channel-level signal at Low/Medium confidence**. When the user supplies email/SMS
  `push_id`/`group_id`, upgrade to per-message typology (a `group_id` with repeats ⇒
  automated; a single `push_id` ⇒ one-shot) at High confidence.

**Strategic priorities, campaign playbook & maturity (the consultative layer) —
`scripts/campaign_purpose.py` + `campaign_playbook.json`**
Turn the campaign inventory into a strategy-led CSM/AM story built on 6 **pillars**:
Editorial & Content, Onboarding & Adoption, Service & Transactional, Lifecycle & Retention,
Engagement & Data, Commercial & Monetization.
- **Purpose classification (language-aware, high-recall).** Map every item of the canonical
  inventory (all channels) to a pillar + a standard **lever** via `classify_purpose(campaigns,
  vertical=…, bodies=…)`. Detection **reads the label in its own language** (FR/EN) and matches
  `campaign_playbook.json` bilingual aliases with **stemming + shared-prefix tolerance** — it
  **prefers recall**: a broad, possibly-imperfect association beats missing a probable one, so
  partial hits still yield a (low-reliability) candidate. **Name-first**, with a **content
  fallback** (`bodies={push_uuid: text}` from decoded `perpush/pushbody` / MC HTML; Reports-only,
  never the Content API). **Pillar-priority disambiguation** routes intent-specific levers over
  generic ones (e.g. "Je crée ma Carte Club" → `account_creation`, not `loyalty_offer`). Every
  mapping carries a numeric **`reliability` (0-1)** + High/Medium/Low (message name up to High,
  body ≤ Medium, `cta_only` capped low) and its `lang`/`basis`/`source` — surface the score
  (`report_interactive.reliability_pill`). A lever counts toward pillar coverage only at
  reliability ≥ 0.45, so broad `cta_only` matches stay visible without inflating maturity.
- **Maturity matrix (per pillar).** `pillar_maturity(...)` → for each pillar: the levers
  **recommended for the client's vertical**, which the client already runs (coverage %), the
  **automation share** and **volume share** within the pillar, a maturity tier, and the
  vertical **business stake + key figure** (`campaign_playbook.json` `vertical_stakes`).
  Render with `report_interactive.strategy_matrix(...)`; render the done-vs-recommended
  levers per pillar with `pillar_coverage(...)`. Feed `pillar_coverage`'s `recommended` list
  with **sector/brand-adapted best-practice use cases authored as a marketer of THIS brand**
  (concrete, grounded in the brand's real mechanics: loyalty/programme, purchase & basket data,
  fulfilment options, monetisation, current strategy) — **not** the raw generic lever labels;
  the generic `missing_levers` are only a fallback when no brand-specific use case applies.
- **Industrialization mix (DEPRECATED in the report).** Do **not** ship the `automation_mix(...)`
  "today vs target" viz — it was dropped for confusing readers (the today-vs-target framing is
  unclear). Keep the automated-vs-one-shot read where it is factual and useful: in the
  **per-channel campaign typology** (§7) and, when relevant, as a single **account-level
  recommendation** (rebalance toward automated lifecycle/service). The toolkit function stays
  available but is no longer part of the standard playbook section.
- **Personalization depth ladder.** Position what the client can already personalise on
  (identity / behaviour & content / context & prediction) from the data actually present
  (device attributes, event taxonomy, custom events) → `report_interactive.personalization_ladder(...)`.
- **Recommended new campaigns.** `recommend_campaigns(...)` → the vertical-recommended levers
  the client does NOT run yet, ranked by relevance × reachable base, each tagged with its
  pillar (lifecycle / adoption / commercial / service / editorial / engagement), typology,
  channels and the business stake it serves. **Use these as a STARTING POINT only**: rewrite
  each as a concrete proposal tailored to the brand's **business model & current context**
  (brand research: recent news, strategy, challenges, competitors) so the Recommendations
  section is genuinely relevant to THIS brand — be a force of proposal, not a generic lever list.
- **Strategic priorities.** Distil 3–4 brand-tailored priorities (e.g. complete content with
  service; industrialise recurrence; gain relevance via data & A/B; orchestrate channel
  complementarity) from the maturity gaps + vertical stakes → `report_interactive.priority_cards(...)`.
This layer is **contextual → cap at Medium confidence** and always state the detection basis.

**Robust campaign analysis — the core deliverable (COMPARTMENTALIZED BY CHANNEL)**
**Scope — MESSAGE-FIRST.** Campaign analysis is driven PRIMARILY by decodable messages:
**push, Message Center, email, SMS** (decode bodies when the name is ambiguous). It is
**COMPLEMENTED** by `location:in_app_message` (and `in_app_pager` / `ua_mcrap` / `banner - …`)
signals, but those expose only a **CTA name / impression** (no full message) → they carry a
**low reliability** (`source:"cta_only"`, capped Medium) and never outrank a real message.
Build a clear, complete picture of what was sent over the period. **Channel is the
top-level axis**: analyse **push**, **email**, **SMS** and **in-app/MC** in **separate,
clearly-labelled blocks**. **Never blend push and email (or any two channels) in the same
table, ranking or matrix** — the reader must always know which channel a figure describes.
**Every active channel (from step 2b `channel_summary`) gets its own block, and each block
states its automated-vs-one-shot split.** An active channel must never be reduced to a single
volume number: give it, at minimum, volume + engagement (funnel or rates) + typology.

*Email channel (robust aggregate even without a message list):*
- **Detect it from `/sends` email volume**, not `/devices` — email frequently shows
  `opted_in: 0` in the snapshot while sending millions (verified on real projects). The
  `channel_summary` flag `email_active_but_zero_optin` catches exactly this; never call email
  "inactive" on the `/devices` snapshot alone.
- **Build the funnel from Airship standard email events** (`channel_activity.email_funnel_from_events`):
  `injection`/`delivery` ≈ sends delivered, `initial_open`/`open` ≈ opens, `click` ≈ clicks,
  `bounce` / `spam_complaint` / `unsubscribe` ≈ deliverability & hygiene. Report delivery
  rate, open rate, CTR, CTOR, bounce/spam/unsubscribe rates vs the internal baseline (no
  external email benchmark). This is the **robust email KPI set** the Reports API supports.
- **Reconcile the two email volume counters** — `channel_summary` now attaches
  `channels.email.reconcile` (`channel_activity.email_reconcile`). `/api/reports/sends` and
  the event feed disagree by ~11% on a real account; a review that quoted one in the
  executive summary and the other in the funnel published more email delivered than sent.
  Volume KPIs take `/api/reports/sends`; the open rate takes `delivered`. Render the gap
  with `ri.email_reconcile_note()` — the gate requires it whenever §14 is not N/A.
- **Per-message email** only when the user supplies `push_id`/`group_id` (then `perpush/detail`
  / `pergroup/detail` top-level fields). Otherwise state the per-message limitation prominently
  and keep the aggregate funnel + cadence typology.

*Push campaigns* (SDK platforms — iOS / Android / web):
- **Activity log first (required).** Paginate `/api/reports/activity/details` across the
  **whole period** — it lists dashboard/API **non-unicast** sends (broadcasts, segments,
  A/B, program `GROUP` rows) and **excludes** the unicast/automation micro-stream. This is
  the canonical inventory for **one-shot / marquee broadcasts** and complements
  `responses/list`. Merge both via `activity_log.merge_push_inventories(...)`. Any
  **`activity_only`** push_id must enter the reach ranking and one-shot profile (then
  `perpush/detail` + `pushbody` for KPIs and creative). Activity-log delivery/interaction
  totals are for discovery; **rates in the report come from `perpush/detail`**.
- **Full collection, not a peek.** Paginate `responses/list` across the **whole period**
  (follow every `next_page` cursor). If the volume forces sampling, cover the **top-N
  send days** and **state the coverage** ("N of M days, X% of period sends") — never imply
  completeness you didn't achieve. `responses/list` is **push-only** (see `reference.md`).
- **"Firehose" / high-volume push accounts — analyse by PROGRAM, don't give up.** Some
  projects emit an enormous stream of tiny automated/triggered/personalised pushes (dozens–
  hundreds per **minute**, each with a handful of `sends` and often empty bodies) interleaved
  with a few mass broadcasts. **Detect it early**: sample one narrow mid-period window (e.g.
  one hour) with `responses/list`; if it returns hundreds of micro-sends and the `next_page`
  cursor barely advances in time, exhaustive **per-push** enumeration is **intractable** — do
  NOT page through it all. **But the firehose IS measurable at the program level**: the tiny
  pushes carry a **`group_id`**, and `GET /api/reports/pergroup/detail/{group_id}` returns the
  **whole program's** aggregated `sends` + `direct_responses` + `influenced_responses` +
  per-platform split (this is often the bulk of the account's volume — e.g. a single
  automation group can be tens of millions of sends). So switch to a **program-level push
  analysis**:
  - **Collect the distinct `group_id`s** (and the marquee broadcast `push_uuid`s) from a
    bounded `responses/list` sample across the top send-hours/days, then pull
    `pergroup/detail` **per group** → a real **per-program ranking** (sends + direct/influenced
    rates + iOS/Android/web split), not just a volume trend.
  - Characterise the **send-type mix and volume trend** from `/reports/sends`; surface the
    identifiable **mass broadcasts** (largest `sends`) with `perpush/detail`.
  - **Surface web push explicitly** — in firehose accounts a lot of web volume hides inside
    automation groups (visible only via `pergroup/detail.platforms.web`); do not report web
    as "under-used" before checking the groups.
  - **State the coverage limitation** for the individual micro-pushes ("the long tail of
    triggered pushes is analysed at program level via `pergroup/detail`, not enumerated
    per-push"). Ask the user for any specific broadcast `push_id`s they care about beyond the
    groups; use **illustrative** push previews (real app logo, clearly labelled) when a
    creative can't be tied to a specific broadcast.
- **Rank tops by PERFORMANCE, not only volume.** For each candidate pull `perpush/detail`
  (or `pergroup/detail`) and compute **direct rate** = `direct_responses`/`sends` and
  **influenced rate** = `influenced_responses`/`sends`. Present **two push rankings side by
  side**: a **reach ranking** (by sends) AND an **engagement ranking** (by influenced/direct
  rate, with a **minimum-volume floor** — e.g. ≥1% of the addressable base — so tiny sends
  don't top the chart). A message is only a "top performer" if it wins on rate, not volume.
- **By platform.** For every top push, break out **iOS vs Android** (and web) sends +
  direct/influenced rates from `perpush/detail.platforms`. Call out platform gaps (e.g.
  Android influenced > iOS on the same push) and tie them to the opt-in mix.
- **By message type.** Split every push ranking by `push_type` (BROADCAST / SEGMENTS_PUSH /
  TAG_PUSH / UNICAST / A_B) **and** by typology (one-shot vs automated/recurring). Give
  each type a short profile: typical reach, typical rates, and its **best example** (with a
  preview). Note absent types explicitly.
- **Push matrix.** Present a compact **platform × type matrix** (rows = iOS / Android / web;
  cols = BROADCAST / SEGMENTS / TAG / UNICAST / A_B) — **push only** — plus the two rankings.
- **Preview every top push** (reach- AND rate-leaders): real hero image via
  `fetch_media`+`render_push` (with the real `app_icon=`); text-only card only if no image.
- **Benchmark every push rate** per device family vs the industry benchmark; where none
  exists, use the **internal same-type baseline**. Tag `[Data]` / `[Internal baseline]`.

*Email program* (its own block — never inside the push matrix/rankings):
- **If the user supplied email message/group IDs**: build a **real per-message email table**
  — one row per email with `sends`, **opens** (`influenced_responses`), **clicks**
  (`direct_responses`), open rate, click rate — read from `perpush/detail` (or
  `pergroup/detail` for a recurring step) **top-level** fields (NOT the `platforms` object,
  NOT `responses/list`/activity log). Rank these emails and give each an **internal same-type
  baseline** (median + range of the client's other emails). Preview each with `render_email`.
- **If no IDs were supplied**: report email as an **aggregate funnel** (email `sends` from
  `/reports/sends`, opens/clicks from `/events` where present) and **state the limitation
  prominently**: "standalone email is not enumerable from the Reports API; supply
  email message/group IDs for per-message detail." Do **not** invent per-message email rows.
- **Objective creative selection (email)** — never pick "by looks": with IDs, show the
  measured performance leaders; without IDs, pick by an **objective proxy** (lifecycle
  coverage — welcome / newsletter / win-back / transactional — plus Content-Template
  `modified_at` recency) and **state the selection criterion** used.

*SMS* — same rule as email: per-message from `perpush/detail` top-level (`sends`;
clicks=`direct_responses`) when IDs are known, else aggregate `sends` with the limitation
stated. Its own block; never merged with push.

*In-app / Message Center* — from `/events` `location` (`in_app_message`, `in_app_pager`,
`ua_mcrap`): reach and read/dismiss rates in a **separate block**, benchmarked against the
internal same-type baseline (no external benchmark for Scene/pager). Preview via `render_card`.
**These are a COMPLEMENT to the message-based analysis, not a substitute**: the feed exposes
only CTA names / impressions, so purpose mappings built from them are `cta_only` / low
reliability. Message Center content itself is a PRIMARY channel when its HTML is recoverable
from `perpush/pushbody`; `ua_mcrap` only measures its engagement.

State any absent channel explicitly; do not blend channels to fill a table.

**Experiments (Reports API only)**
- Detect A/B activity via `push_type == A_B` in `responses/list`; for those pull the
  Reports experiment endpoints `experiment/overview/{push_id}` +
  `experiment/detail/{push_id}/{variant_id}` (`rpt`). Do **not** call `/api/experiments`.
  Report variants/winner, or state "no experiments detected in the period".

**Custom-event contextualisation & conversion KPIs — `scripts/event_analysis.py`**
This is the core of the `location: custom` deep dive. Run `event_analysis.analyze(events,
vertical=…, brand=…, region=…, country=…, currency=…)` on the **merged `/events` array**
(all pages). It uses `event_catalog.json` (best-practice events per vertical, imported from
the "Data Collection by Vertical" workbook via `scripts/import_event_catalog.py`) to:
- **Contextualise every event**: `classify_event()` matches each client event name to a
  catalog event/category with a **confidence level** (name tokens + bilingual EN/FR
  aliases). Excludes the standard email funnel events (handled by `channel_activity`).
  Produces a **taxonomy** by category and by `kpi_kind` (business / usage-consumption /
  loyalty) — the picture of *what the client actually reports to Airship*.
- **Identify conversion KPIs**: `detect_conversion_kpis()` flags events whose matched
  category is a conversion/consumption KPI (Purchase, Add to cart, Transaction success,
  Reservation, Activation, Loyalty, Consume content…), split **business** vs
  **usage/consumption**. For each KPI, `conversion` becomes meaningful: report the
  **direct / indirect / unattributed** split (count) and the **attribution rate**
  (`direct+indirect / total`) = Airship's measured contribution.
- **Interpret `value` as an amount**: `detect_monetary_value()` decides per event whether
  `value` behaves like a **monetary amount** (avg value/event ≫ 1 and varied) vs a plain
  per-event counter (`value ≈ count` → NOT money). `currency_for_brand()` assigns a
  **probable currency** from the brand country/region (overridable, labelled as an
  assumption + confidence). When monetary, report the **direct & indirect attributed
  amount** per KPI (e.g. push-attributed order revenue). Always restate `value` ≠ currency.
- **Data-collection opportunities** (`opportunity_gaps()`): (a) catalog events recommended
  for the vertical but **not sent** → "send more to Airship"; (b) conversion events the
  client **does** send but **without a monetary value** (e.g. a purchase event with no
  amount) → "enrich with conversion value (+ currency)". Each carries a confidence level.

**REQUIRED — write `events.value_measurability` into `audit.json`.** Call
`event_analysis.value_measurability(events, tagging_monetary=…)` and store the dict it
returns verbatim. The delivery gate asks the executive summary whether this account's
conversions can be given an amount at all, and nothing upstream produced the answer — so
a section had to recompute it by opening `data/events.json` directly, which is a raw pull
retired the moment the gate passes. That report can no longer be rebuilt. The grade
(`revenue` / `partial` / `declared_not_flowing` / `counters`) also feeds the page-1
coverage banner, which states the revenue blind spot only when this key says there is one.

**Per-campaign conversion attribution — `scripts/event_attribution.py`**
When (and only when) conversion KPIs are identified, attribute them **per campaign** so the
report shows conversion impact next to engagement:
- Call `events/summary/perpush/{push_id}` for the top analysed pushes and
  `events/summary/pergroup/{group_id}` for recurring programs (reuse the campaign
  enumeration from `responses/list` + activity log; see `activity_log.py`).
- `attribute_campaigns(api_get, campaigns, analysis, min_sends=…)` filters each response to
  the conversion-KPI events, aggregates **direct/indirect** count (+ **amount** when
  monetary), and attaches `attributed_conversions` to each campaign row. Tolerates 401/403
  (degrades to "attribution unavailable" + lower confidence) and applies a min-volume floor.
- Produce **two rankings**: top campaigns by **engagement** AND by **conversion impact** —
  a message that opens well but drives no conversion is not a top performer. Where an A/B
  exists (`experiment/*`), report the real **lift**; else use the attributed share as a proxy.

**Events deep dive (rendering)** — via `report_interactive.py` helpers:
- `event_kpi_table(kpis, currency)` — conversion KPIs with the direct/indirect/unattributed
  split (+ attributed amount when monetary); `attribution_series(kpi)` feeds
  `airship_charts.spec_donut` for per-KPI attribution donuts.
- `value_amounts_block(analysis)` — attributed vs unattributed **amount** per monetary
  event, currency assumption + caveat (empty when nothing looks monetary).
- `opportunities_tables(opps)` — the "send more" and "enrich with value" tables.
- `attributed_conversions_cell(attr)` — the per-campaign conversion/amount cell.
- Also report full taxonomy by `location` (custom / in_app_message / in_app_pager /
  ua_mcrap=Message Center / ua_interactive_notification) and flag anomalies/spikes and any
  multi-market/data-hygiene signals (e.g. foreign-language campaign names in one project).

**Unicast category recovery**
- For `UNICAST` sends, best-effort recover `campaigns.categories`/type (retry `pushbody`
  for metadata, `message_name` parse). Label the campaign type; if nothing
  recoverable, label "category unavailable".

**Creative coverage (Reports only)**
- From decoded **`perpush/pushbody`** on analysed messages: count how many tops have real
  notif text, MC/email HTML, rich-push hero URLs, deep-links, personalization. Report the
  **share with a recoverable creative** vs illustrative fallback.
- **UNICAST / template-driven** sends: creative HTML is **not available** via Reports alone
  when pushbody is empty — state this limitation; use metadata (`message_name`, categories)
  + labelled reconstruction. Never call `/api/content/templates`.

**Industry benchmarking (position KPIs vs peers)**
- Using the vertical from step 1, load benchmark values from `benchmarks.json` (human
  reference: `benchmarks.md`; source: Airship UA Benchmarks workbook). Benchmarked KPIs:
  `optin_rate`, `direct_open_rate`, `influenced_open_rate`, `sends_per_user_month`,
  `message_center_read_rate`. Show the **client value next to the vertical median (p50)**
  and the **[p10–p90] range** and the **gap** (points or ×), tagged `[Data]`.
- **Compare per device family** (iOS/Android/Web) — never blend platforms against a
  per-platform benchmark. There is **no blended opt-in** and **no opt-out** benchmark:
  compare opt-in per platform; for opt-out, state "no benchmark".
- **Pressure is PER MONTH**: the report's marketing pressure is sends/opted-in user/week →
  ×~4.33 (or recompute monthly) before comparing to `sends_per_user_month`.
- **Cite source + quarter + region (global)** beside every comparison. Telecom has no own
  vertical → use `utility_productivity` (or `all_verticals`) as a **labelled proxy**.
- If `benchmarks.json` is empty, the vertical/metric doesn't match, or the file is stale,
  **do not fabricate** — fall back to the internal baseline (next bullet) instead of just
  stating "not available".
- Benchmark comparisons are capped at **Medium** confidence (external/contextual).
- **Present benchmarked KPIs as visual gauges** (`report_interactive.gauge(value, p10, p50,
  p90, verdict=…)`): the peer [p10–p90] band, the p50 median tick and the client value, with
  a one-word verdict pill (`verdict_pill`). Group them into a **benchmark scorecard** page.

**Reachability (installed base you can actually message)**
- From `/devices`: **% of the base reachable** per channel = channel `opted_in` / unique
  devices — push (iOS/Android/web), email, SMS. A low reachability caps every downstream
  metric; call it out and tie recos to opt-in growth. Tag "(snapshot DD/MM)".

**Engagement best-practices scorecard (email + mobile)**
- Score the account **Good / Average / Poor** (use `verdict_pill`) on concrete best
  practices, each from measured data: **rich push %** (share of pushes with a hero image),
  **deep-link %** (`uairship://` actions), **personalization %**, **A/B adoption**,
  **lifecycle coverage** (welcome / onboarding / win-back / transactional present?),
  **Message-Center-paired push**, and copy hygiene (title/body length, emoji) from decoded
  pushbodies. For email (if active): **open rate, click rate, CTOR (click-to-open), opt-out,
  list growth** vs the internal same-type baseline (no external email benchmark). Each row =
  the client value, the best-practice target, and the verdict — a quick "what to fix" view.

**Internal baseline (channels/metrics with no external benchmark) — see `reference.md`**
- Most channels have **no `benchmarks.json` entry** (email/SMS opens & clicks, opt-out rate,
  blended cross-platform rates, web influenced-open, in-app Scene/pager dismiss, custom-event
  attribution…). For these, compare each message against **the client's own other messages
  of the same type** (same channel + same campaign typology — one-shot vs
  automated/recurring) rather than stopping at "no benchmark".
- Show the message's value next to the **median** (and min–max or [p25–p75] range) of the
  other same-type messages; tag it **`[Internal baseline]`**, source "client's own history,
  N messages, `<endpoint>`". Require **≥3 comparable messages**; below that, state
  "insufficient same-type messages for an internal baseline".
- Capped at **Medium** confidence, same as external benchmarks. Use **alongside**, not
  instead of, the external benchmark wherever one exists.

**Data foundation & tracking coverage (OPTIONAL — tagging-plan audit) — `scripts/data_foundation.py`**
Only when a data-collection audit was supplied (`audit["available"]`); otherwise skip this
whole layer and leave every other section unchanged (graceful degradation). It reuses the
**built-in tagging-plan** outputs (`inventory.json` = client taxonomy, `ua_*` excluded;
`analysis.json` = intents, value-bearing, gaps, provenance) produced by the vendored
`parse_tagging_plan.py`+`analyze_tagging_plan.py` — one source of truth, never
re-implemented here. Process **every** item (no top-N). It enriches three areas:
- **Conversion measurement (fact, not heuristic).** `cross_reference_conversion(reports_events,
  audit)` attaches to each Reports conversion KPI whether the event is tracked, whether it
  **carries a value / currency** (from `valueBearing`/`monetaryValue`/`eventProperties`), the
  inferred monetary unit + confidence, and `missing_value`; plus **conversion events tracked
  but not fired** in the window (design intent vs firing). `value_index(audit)` feeds
  `event_analysis.analyze(audit_value_index=…)` so "enrich with value" is decided from the
  tagging plan, not the count/value heuristic. **Caveat**: custom-event `value` ≠ currency —
  the currency is *inferred* from the amount distribution (decimals ⇒ major unit); the audit is
  a tracking capture whose window differs from the 30-day activity, so the cross-reference is
  by **event name**.
- **Maturity (data-driven).** `personalization_ladder_from_audit(audit, lang)` builds the 3-level
  ladder (identity / behaviour & content / context & prediction) from the **real** attributes,
  events, tags and subscription lists (replaces the hard-coded ladder; fallback kept when absent).
  `lever_data_readiness(recos, audit)` / `annotate_recommendations(recos, audit)` tell, for each
  recommended lever, whether the client **already tracks** the data it needs (activatable now)
  vs **needs collection first**. `provenance` (SDK vs API, contact vs device-level, cadence)
  is surfaced as the new foundation dimension.
- **Strategic recos (collection + activation).** `data_collection_recos(audit, lang)` turns
  **every** gap (missing/partial attributes & events) and **every** `conversionSignal` into
  pillar-tagged items: `track_event`, `enrich_event`, `collect_attribute`, `add_value`,
  `activate_goal` (Airship goal opportunities). Contextual layer → confidence capped at Medium,
  each tagged `[Data]` / `[Data+Context]`. Fold these into the pillar Recommendations (section 16)
  under a "Data & measurement" thread.
- **Compact block.** `report_interactive.data_foundation_block(foundation, lang)` renders the
  "Data foundation & tracking coverage" section (breadth of events/attributes, tags & lists =
  segmentation surface, SDK/API split + storage verdict, vertical coverage %, value/currency
  instrumentation rate). It returns "" when no audit, so the section is conditionally included.

**Size the gaps you report (`scripts/opportunity.py`)**
A gap the reader has to value themselves is a finding they will not act on. "iOS converts
below Android" leaves open whether it is worth a sprint; "closing it would return about
7.5M opens a month" is the same finding, decidable. The inputs are already in the audit —
so where §4 (volume & pressure), §5 (engagement) or §16 (recommendations) states a gap
that can be sized, size it.
- `size_rate_gap(lagging_*, leading_*, outcome=…)` — what the lagging side would return at
  the leading side's rate, at its own volume. Only across sides that differ in performance
  and not in kind: two platforms of one programme, yes; web against app permission, no
  (see the comparability rule in `reference.md`).
- `size_pressure_headroom(per_month, p50, opted_in)` — the distance to the peer median in
  sends/month, and it reads both ways. Below the median it is unused capacity; above it,
  the same arithmetic is volume beyond what peers send, which is a pressure question. The
  median is **not a target** and must never be rendered as "should send X more".
- `format_sized(op, lang)` prints the figure with **its formula and its caveat**, which is
  the point: a projection that reads like a measurement is worse than no figure at all.
  It returns `None` when there is no opportunity, so a caller drops the line rather than
  printing a negative one. Confidence for a sized gap caps at **Medium** — it assumes an
  audience of comparable quality, which the audit cannot verify.

**Verification & confidence (apply to every insight/reco)**
- State the verification basis (source endpoint(s) + sanity checks: sums reconcile, rates
  in 0–100%, sample size, full pagination, scope available).
- Tag each insight/reco with a confidence level **High / Medium / Low** (criteria in
  `reference.md`). Brand-context-only → Low; low-sample/degraded-scope → Medium max.
- Low-confidence items carry a "to verify" note (what would raise confidence).
