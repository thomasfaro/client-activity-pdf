# Reference — Campaign typology, per-channel campaign analysis, experiments, unicast, creative coverage, programme names, Flight Deck deep-links

Part of the [reference index](../reference.md). Read the files the index routes to your task, not the whole folder.

## Campaign typology — one-shot vs automated/recurring
Goal: separate **one-shot** sends (manual, sent once) from **automated/recurring**
campaigns (journeys, automations, recurring schedules) and rank/analyse them separately.

Detection — **Reports API only** (do NOT call `/api/pipelines` or `/api/schedules`):
0. Build the push inventory from **`activity/details` (full period) merged with
   `responses/list`** via `activity_log.merge_push_inventories(...)`. Activity-only rows are
   typically one-shot broadcasts; responses-only rows are typically UNICAST/automation.
1. **Heuristic from reports**: group the **merged** push rows by `group_id`, then by
   **normalized `message_name`** — strip trailing date/ID tokens (e.g. `_07062026`,
   `_2026-06-07`, trailing UUID/hash, `_v\d+`). A normalized name (or group) recurring on a
   **regular cadence** (≈daily/weekly/monthly) across the window ⇒ automated/recurring. A
   unique name sent once ⇒ one-shot. `scripts/classify_campaigns.py` implements this
   (normalization + grouping + cadence).
2. `push_type` hints: `UNICAST` / Create-and-Send are typically automation/journey
   outputs; large `BROADCAST`/`SEGMENTS_PUSH` with a unique name are typically one-shot.

Analysis per type:
- **One-shot**: reach, direct/influenced rates, creative, single-send attribution.
- **Automated/recurring**: across occurrences — total + per-occurrence volume, **volume
  drift** (flag significant increases/drops vs the series median), and **engagement-rate
  trend** (direct+influenced / sends over time). Aggregate the group via
  `pergroup/detail` or sum the repeated `perpush/detail`; use `perpush/series` for shape.
## Campaign analysis — COMPARTMENTALIZED BY CHANNEL (robust method)
The campaign section is the report's centrepiece. **Channel is the top-level axis**: analyse
**push**, **email**, **SMS** and **in-app/MC** in **separate, clearly-labelled blocks**.
**Never blend two channels in one table, ranking or matrix** — the matrix and the two
rankings below are **PUSH-ONLY**.

### A. Push campaigns (SDK platforms — iOS / Android / web)
**0. Scan the Activity Log (required).** Paginate `GET /api/reports/activity/details` across
the **entire period** (`limit=100`, follow every `next_page`). This is the canonical
inventory of **dashboard broadcasts and one-shot sends** — the campaigns most visible to the
client in Flight Deck — and it excludes the unicast/automation noise that clogs
`responses/list` on firehose accounts. Merge with `responses/list` via
`activity_log.merge_push_inventories(...)`; treat **`activity_only`** rows as mandatory
candidates for the reach ranking and one-shot analysis (then confirm with `perpush/detail`).
**1. Collect the full push stream.** Page `responses/list` (push-only) across the **entire period**
(follow every `next_page` cursor until exhausted). If volume forces sampling, cover the
**top-N send days** and state the coverage ("N of M days ≈ X% of period sends"). Never imply
completeness you didn't reach.

**1b. "Firehose" / high-volume push accounts — measure by PROGRAM.** Some projects emit a
continuous stream of tiny automated/triggered/personalised pushes (dozens–hundreds per
**minute**, each a few `sends`, often empty bodies) mixed with a few mass broadcasts.
**Detect it before committing to full pagination**: sample a single narrow window (e.g. one
hour mid-period) with `responses/list`; if it returns hundreds of micro-sends and `next_page`
advances only minutes at a time, enumerating the whole period **per-push** is **intractable**
— attempting it wastes hundreds of calls and still won't be complete.
**Key insight — the firehose IS measurable at the group level.** Each micro-push carries a
`group_id`; `GET /api/reports/pergroup/detail/{group_id}` returns the **whole program's**
aggregated `sends` + `direct_responses` + `influenced_responses` + `platforms` split. A single
automation group is frequently the bulk of the account's volume (tens of millions of sends).
So switch to a **program-level push analysis**:
- **Collect the distinct `group_id`s** (and marquee broadcast `push_uuid`s) from a bounded
  `responses/list` sample over the top send-hours/days, then call `pergroup/detail` **per
  group** → a real **per-program ranking**: sends, `direct_rate`, `influenced_rate` and the
  iOS/Android/web split — not merely a volume trend.
- Volume & type mix from `/reports/sends` (per-platform daily) + the `push_type` distribution
  from the sample. Surface the identifiable **mass broadcasts** (largest `sends`) via
  `perpush/detail`.
- **Check web push inside the groups.** In firehose accounts large web-push volume hides in
  automation groups (`pergroup/detail.platforms.web`); never label web "under-used" before
  checking. (Observed: separate web-only automation groups of 100k–800k sends.)
- **State the coverage limitation** for the micro-push long tail ("analysed at program level
  via `pergroup/detail`, not enumerated per-push"). Ask the user for any extra broadcast
  `push_id`s beyond the groups — do not guess. Use **illustrative** push previews (real app
  logo, clearly labelled "illustrative") when a creative can't be tied to a specific broadcast.

**1c. The OTHER firehose: no `group_id` at all — enumerate, don't give up.** 1b assumes the
micro-pushes belong to automation *programs*. They often don't. When an external orchestrator
(**Salesforce Marketing Cloud**, Braze, a homegrown CRM) resolves the audience on its side and
calls `/api/push` **once per contact**, every push is a standalone `SEGMENTS_PUSH`/`UNICAST_PUSH`
with **no `group_id`** — there is no program layer to roll up to, and 1b's escape hatch does not
apply. Observed on a **telecom** account (0.04% of pushes carried a group).

**1b and 1c are two HALVES, not two choices.** Treating them as exclusive is what made a
grocery-retail review cost 76 086 API calls and 22 minutes. That account carried a `group_id`
on only **8.3% of its pushes**, so the probe called it groupless and enumerated — while those
pushes' **25 programmes aggregated 46.6M sends against 39.1M in the whole window**, i.e. the
programme layer *was* the account. Both halves existed and wanted opposite treatments.

So do not classify on the share of *pushes* carrying an id. On such an account the **median
push delivers 0 sends**, so counting pushes counts no-ops. Classify on what the programmes
weigh: `probe` now reports `group_id_share` (pushes), `group_sends_share` (sends) and
`confirmed_program_sends` (a handful of `pergroup/detail` calls on the ids it saw), and
`shape_reason` records which one decided. Any confirmed programme with material volume means
the program layer exists and must be rolled up, whatever the push share says.

**Always probe before choosing an approach** — it costs ~8 seconds and decides everything:
```bash
python scripts/push_firehose.py probe "<MCP project>" <start> <end>
# -> shape: dashboard | firehose_grouped | firehose_groupless | firehose_unattributed
#    (+ guidance, shape_reason, enumerable)
```

The shape answers **three** questions, and the last one is the one that gets forgotten: is a
full pass *sizeable at all*? `pushes_per_day_exact` is false when the counting oracle stopped
at its budget, and a floor is not a size. An account can be too dense to have a programme
layer *and* too dense to enumerate — that is `firehose_unattributed`, and it exists because
sending such an account down the groupless path is not a slow choice but an impossible one
(measured: 16 minutes into the adaptive descent of its **first** day, nothing written).

When the shape is `firehose_grouped`, **notice every programme, enumerate none of them.** A
programme's volume and rates come from ONE `pergroup/detail` call covering the whole
programme, so seeing more of its pushes buys nothing — only its identity has to be found:
```bash
python scripts/push_firehose.py discover "<MCP project>" <start> <end> data/discovery.json
```
`discover` scans spread windows on **every day of the window** rather than exhausting a few
days, and returns the discovery curve. Two things it must be read for:
- **Spread, not prefix.** Capping pagination at the first N pages of a day drops the
  afternoon programmes *systematically*: on the account above, one day's 19 programmes first
  fired between 00:32 and 16:05. That is a structural loss, not a sampling error.
- **It is a lower bound and says so.** `saturated` is true only when no new programme
  appeared on the last three days. A programme that recurs cannot be missed; a one-off that
  fired in a single unscanned minute can. Quote `coverage`, never "all programmes".

**Do not expect the activity log to be the grouped inventory.** It is the right instrument on
a dashboard-driven account, and it was **empty of grouped sends** on this one: 307 rows
totalling **under 2 000 sends** out of ~39M, **zero** `type: GROUP` rows and **zero** `group_id`
anywhere. Its 307 rows were still exactly the 307 decodable message bodies, so it remains the
creative inventory — just not the volume one. Check, do not assume.

When the shape is `firehose_unattributed` — dense, no programme layer, and not sizeable —
**do not enumerate, and do not pretend the sample is an inventory.** Three sources, each with
its own coverage figure:
- **Volume: `/api/reports/sends` only.** It is authoritative and it is the *sole* volume
  source for this account. Nothing else may be totalled — `responses.json` here holds
  programme representatives plus the heaviest unitary pushes, chosen for their `push_uuid`.
- **Message inventory: the hour-tiled activity log.** Budgeting pages per *day* samples the
  last seconds before midnight; budget per **hour**. Measured on a sports account: 1 hour
  covered → 24, and 30 000 rows → 322 258.
- **Typology: a sends-weighted sample.** Uniform draws are worthless where the median push
  delivers zero. On that account, 500 weighted draws out of 123 372 distinct ungrouped pushes
  carried **3.1%** of window sends — small, but a *stated* 3.1%.

Publish the coverage of each, and never a campaign count taken from the activity log: that
endpoint carries `push_id`, timestamp, type and delivery counters, and on every account tested
**no name and no `group_id`**.

When the shape is `firehose_groupless` — dense, no programme layer, but the daily count is
*known* and modest (≤ ~8 000/day):
- **Full enumeration IS tractable** if you partition time instead of paginating linearly.
  `responses/list` accepts second-precision `start`/`end`, so descend adaptively
  (hour → minute → 2-second leaf, drilling only into windows that overflow one page) and
  parallelise. 30 days × ~2.8M pushes runs in minutes, not hours:
  ```bash
  python scripts/push_firehose.py enumerate "<MCP project>" <start> <end> data/pushes
  ```
- **The campaign taxonomy is not in Airship — it is in the tag namespace.** With no activity
  log entries and no groups, the only inventory of what was actually sent is the orchestrator's
  tag space (e.g. `sfmc-integration:C_MOB_RENO_BYOU_..._INAPP_PUSH`). Parse the client's tagging
  plan and decode the naming convention into universe / pillar / lever / channel / date. Here the
  tagging plan is **not an optional enrichment — it is the campaign inventory**, so ask for it.
- **Report the delivery-architecture findings, they are the story**: sends per push (≈1 means
  per-contact calls), the share of pushes reaching **zero** devices (stale contacts in the
  orchestrator), and everything the architecture forfeits (no Airship-side audience, no capping,
  no A/B test, no orchestration).

**2. Pull per-message detail.** For each candidate, `GET /api/reports/perpush/detail/{push_id}`
(or `pergroup/detail/{group_id}` for a series). Read the **top-level** `sends`,
`direct_responses`, `influenced_responses`, and the **`platforms`** object (`ios`,
`android`, `web`) for the per-platform split.

**3. Compute rates.**
- `direct_rate = direct_responses / sends`
- `influenced_rate = influenced_responses / sends`
- Do the same **per platform** using `platforms.<fam>.{sends,direct_responses,influenced_responses}`.

**4. Two push rankings, always.**
- **Reach ranking** — by `sends` (who did we reach most).
- **Engagement ranking** — by influenced (or direct) rate, with a **minimum-volume floor**
  (e.g. `sends ≥ 1%` of the addressable base) so a 200-send push doesn't top the chart.
- A message is a "top performer" only if it wins the rate ranking; volume alone ≠ performance.

**5. The push matrix.** Cross **platform** (iOS / Android / web — **push only, no email/SMS
row**) × **type** (`push_type`: BROADCAST / SEGMENTS_PUSH / TAG_PUSH / UNICAST / A_B) — cells
hold count, total reach and typical (median) rate. Also fold in the one-shot vs
automated/recurring typology. Name absent combinations explicitly.

**6. Preview + benchmark each top push.** Render the real creative (hero image via
`fetch_media`+`render_push`, **with the real app logo** via `app_icon=fetch_app_icon(...)`),
then position each rate vs the industry benchmark **per device family**, or vs the **internal
same-type baseline** where no external benchmark exists. Tag `[Data]` vs `[Internal baseline]`.

### B. Email program (its own block — never inside the push matrix/rankings)
- **With user-supplied email message/group IDs**: build a **real per-message email table** —
  one row per email with `sends`, **opens** = `influenced_responses`, **clicks** =
  `direct_responses`, open rate, click rate (all from `perpush/detail` / `pergroup/detail`
  **top-level** fields). Rank them and give each an **internal same-type baseline**. Preview
  with `render_email`.
- **Without IDs**: report the **aggregate email funnel** (email `sends` from `/reports/sends`,
  opens/clicks from `/events` where present) and **state the per-message limitation**
  prominently (standalone email is not enumerable — see "Email / SMS performance"). Never
  invent per-message rows.

### C. SMS / In-app / Message Center (each only if present, own labelled block)
- **SMS**: per-message from `perpush/detail` top-level (`sends`; clicks=`direct_responses`)
  when IDs known, else aggregate `sends` with the limitation stated.
- **In-app / MC**: reach + read/dismiss rates from `/events` `location`
  (`in_app_message` / `in_app_pager` / `ua_mcrap`), vs the internal same-type baseline
  (no external benchmark for Scene/pager). Preview via `render_card`. **Complement, not
  substitute**: these expose only CTA names / impressions, so any purpose mapping from them is
  `cta_only` / low reliability; the message-based channels (push/MC/email/SMS) remain primary.
  Message Center content is a PRIMARY channel when its HTML is recoverable from `perpush/pushbody`.

### Objective creative selection — preview only what MATTERS
Creatives are **curated, not exhaustive**. Decode broadly to *classify* campaigns, but only
render a **preview** for a message that is **important to the client**. A message qualifies on
at least one objective criterion:
- **Automated / recurring program** — a `pergroup` journey/trigger campaign (welcome, cart,
  win-back, RDV/loyalty, replenishment…). These run continuously and drive the relationship, so
  they matter even when a single send is small.
- **Large send** — a top broadcast by delivery volume (from the activity-log / `responses/list`
  reach ranking).
- **Strong performer** — a rate leader (best `direct`/`influenced` response rate) vs the
  client's **own same-type baseline**.

Rules:
- **Channel priority: push → Message Center → email** (SMS / in-app only if material). Message
  Center and email carry the richest creative, so prefer them when a program has both a push and
  an MC/email step.
- **Cap ~4–8 previews.** Curate a spread across pillars/channels; do not dump every decodable
  body. Caption each preview with the **reason it was picked** ("top automated program",
  "largest broadcast 30d", "best CTR").
- **Never** preview a message just because its body was decodable. Skip tiny one-offs, internal
  tests and seed sends *for their own sake*.
- **Firehose accounts** (mass base delivered as per-device sends with empty `pushbody`): the
  real creative is often only recoverable from a **seed/test send** (`options.is_test`,
  seedlist audience). Use it **only** when it is the creative of an **important** campaign/program
  — map the seed to that program and label the preview as *captured from the campaign* (state the
  method), not as a standalone message.
- **Email**: with IDs → measured performance leaders (open/click rate); without IDs → an
  **objective proxy** = lifecycle coverage (welcome / newsletter / win-back / transactional)
  inferred from message names / categories in pushbodies. State which rule was used.
- **In-app / MC / SMS**: the measured reach/engagement leaders for that channel.
Do **not** select a creative because it "looks nicer"; the selection rule is part of the
report's methodology and must appear in the creatives section.

**Pagination / page-size gotchas (observed):**
- `/api/reports/events` rejects `page_size ≥ 100` — use `page_size=99` and paginate.
  (Re-tested 2026-09-08: `page_size=100` was accepted on one project, so the ceiling may have
  moved or may be account-dependent. 99 is safe either way and `collect.EVENTS_PAGE_SIZE`
  states it explicitly rather than relying on the endpoint's small default.)
- `responses/list` is cursor-based — follow `next_page`; don't assume one page is the period.
- `activity/details` paginates via full `next_page` URLs — follow until exhausted.
## Experiments (A/B) detection — Reports API only
Do NOT call `/api/experiments`. (a) Flag any `responses/list` push with
`push_type == A_B`; (b) for those `push_id`s pull
`/api/reports/experiment/overview/{push_id}` and `/experiment/detail/{push_id}/{variant_id}`
(scope `rpt`) for variant performance + winner. If none found, state "no experiments
detected in the period".
## Unicast → recover campaign categories
For `UNICAST` the `perpush/pushbody` content is empty, but campaign metadata may still be
recoverable. Best-effort, in order: (a) still call `pushbody` — `push.campaigns.categories`
and `push.options.message_name` are sometimes present even when `notification` is empty;
(b) parse `message_name` tokens (e.g. `welcome`, `winback`, `abandon`, `transactional`).
Use the recovered categories to label the campaign **type** in the top-unicast view; if
nothing is recoverable, label "category unavailable".
## Client categories — an external classification, read with a confidence
`push.campaigns.categories` (and the categories of automation / scheduled-broadcast groups)
are the client's own reporting tags. `decode_bodies.py` keeps them on every decoded push,
normalised (string or list, comma-split, de-duplicated, any script); `campaign_inventory`
carries them per campaign. `campaign_categories.py` reads them:

- **Coverage first.** Share of the decoded sends carrying a category. Under 20 %, with
  fewer than two reusable values or three campaigns, or on under 5 % of the decoded
  campaigns (one heavy send is not a taxonomy), the block says `available: false` with
  a `reason` and nothing is reclassified.
- **Scheme.** Each value is typed (facet, positional code, `key:value`, free label that
  repeats the message name, placeholder / test). A value equal to the campaign's own name
  is skipped. Values are split positionally only when codes are the majority of the
  scheme; otherwise `summer_quiz_night` is one facet, and a snake_case value with a
  date is a name. Positional codes get a role per position
  (intent, dimension, channel, locale, date, id). The lexicon
  (`campaign_playbook.json → category_lexicon`, en/fr/de/es/it/pt/nl + codes) proposes
  readings; a frontier model proposes the rest (`prompts/categories.md`).
- **Every reading is tested**, never taken on trust. Confidence = lexical fit 0.30 +
  agreement with the name-based pillar 0.25 + behaviour vs the lever's typology 0.20 +
  position 0.10 + support 0.15; a test that cannot be run counts neutral. Agreement
  ignores campaigns whose name contains the category word — the same fact twice is not
  corroboration — and name matches under 0.60 (the shared-prefix recall tier: `Content`
  is not `continuer`). Caps: one campaign → Low; a model reading not corroborated by
  names AND behaviour → below High; agreement < 20 % on ≥ 3 campaigns → Low (refuted),
  < 34 % → 0.60; a term mapping to several pillars, or where lexicon and model disagree →
  × 0.85; a lexicon reading the model gives a non-intent role (`FREE` as an offer tier,
  `winback` as a target audience) → Low. A short word inside a multi-word value (`VIP`
  in `Grande Fratello VIP`) is not a lexicon match.
- **One reading per campaign.** The most confident usable reading sets the pillar; among
  readings of the same tier and pillar, the most specific one (fewest campaigns) names
  the lever — `DIRETTA` over the `EDITORIALE` family.
- **Use.** High (≥ 0.70) may replace a name match under 0.80 (reliability capped 0.85);
  Medium (≥ 0.45) only fills an unclassified campaign (capped 0.55); Low is shown, never
  used. `purpose.basis = "category"` marks such rows; `category_conflict` marks a
  campaign whose name and category disagree.
- **Performance** per category value: `direct_responses / sends`, against the internal
  average of categorised campaigns, only above 1 000 sends. Internal, not a benchmark.
- **Vendor clues** (SFMC, Adobe, Braze…) in categories, tags or message names feed the
  external-orchestration stance — as clues ("categories reference Adobe"), not proof.

The optional section `client_categories` (7d) shows the scheme card, the readings with
their confidence and tests, the performance table and the name/category alignment
(`report_interactive.category_*`). Every other section only says, once, when a pillar
figure rests on category-based rows.

## Creative coverage (Reports only)
From decoded **`perpush/pushbody`** on analysed messages: report how many top campaigns have
a **recoverable creative** (notif text, MC/email HTML, rich-push image URL) vs an
**illustrative reconstruction**. For UNICAST / template-driven sends where pushbody is empty,
state explicitly that **creative HTML is not available via the Reports API** — metadata
(`message_name`, categories) may still label the campaign type. Never call `/api/content/*`.
## Programmes shown by their identifier — hand the rename to a human
When `responses/list` returns a `group_id` and no composer name, the label falls back to the
identifier, so a top-ranked automation reaches the report as
`00000000-0000-0000-0000-000000000000`. Every figure on that row is correct and the row is
unusable in front of a client — and nothing about it looks broken, which is exactly why it
ships.
- **There is no automated fix.** `/api/schedules` would carry the name and is outside the
  `rpt` scope this review holds. Do not call it, and do not invent a label from the payload.
- **Render `ri.unnamed_programme_note(ids, lang)`** next to the ranking. The gate requires it
  as soon as any table cell shows a bare identifier as a label, wherever it sits in the
  ranking — row 4 is no more presentable than row 1.
- The note is addressed to whoever presents the deck: look each programme up in Flight Deck
  and replace the identifier before the meeting.
## Flight Deck deep-links (link each message to the Airship dashboard)
URL shape: `https://go-admin.airship.{eu|com}/admin/flight_deck/apps/{app_key}/messages/{composer_id}`.
- **`composer_id` is `options.__ui_id`** inside the **decoded** `perpush/pushbody/{push_id}`
  (base64 → JSON → `options.__ui_id`). It is a base64url-encoded UUID and is **NOT** the
  `push_id`. Shape: push_id `10000000-2fa1-11f1-8000-000000000000` → `__ui_id`
  `EXAMPLEuiIdAAAAAAAAAAA` (22 characters), and the `__ui_id` is what the dashboard URL
  carries.
- **`app_key`** is returned directly by `perpush/detail` / `pergroup/detail` (field `app_key`)
  — no need to ask the user.
- **region**: `eu` env → `go-admin.airship.eu`, otherwise `.com`.
- **Availability**: only messages **composed in the dashboard** (BROADCAST/SEGMENTS/A-B, whose
  `perpush/pushbody` is non-empty) carry `__ui_id`. **UNICAST / Create-and-Send / API sends
  have an empty body → no `__ui_id` → no deep-link** (show the "no deep-link" pill, never a
  fabricated URL). Helpers: `composer_id_from_pushbody`, `flight_deck_url`, `flight_deck_button`.
