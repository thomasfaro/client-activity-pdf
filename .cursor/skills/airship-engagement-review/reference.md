# Reference — endpoints, definitions, branding

## MCP access

Each client project is a **separate MCP server** in Cursor (`~/.cursor/mcp.json`).
The Agent calls `call_airship_api` on that server (e.g. `user-Carrefour PROD`).
Setup: OAuth credentials in Airship (`rpt` + `tpl` minimum), env vars
`AIRSHIP_APP_KEY`, `AIRSHIP_CLIENT_ID`, `AIRSHIP_CLIENT_SECRET`, `AIRSHIP_REGION`.
Full walkthrough: see **Prerequisite — configure the client project as an MCP server**
in [SKILL.md](SKILL.md).

## Airship Reports API endpoints
Call via MCP `call_airship_api` with `{method, path, params}`.

| Data | Path | Params | Definition |
|---|---|---|---|
| Sends | `/api/reports/sends` | start, end, precision=DAILY | Notifications sent per platform (ios/android/sms/email/web). |
| Opens | `/api/reports/opens` | start, end, precision=DAILY | App/notification opens as counted by Airship (influenced included). |
| Opt-ins | `/api/reports/optins` | start, end, precision=DAILY | Daily opt-in **events** (not net base; includes re-detections/reinstalls). |
| Opt-outs | `/api/reports/optouts` | start, end, precision=DAILY | Daily opt-out **events**. |
| Devices | `/api/reports/devices` | — | Snapshot: unique devices, opted_in / opted_out / uninstalled per platform → **opt-in rate** (authoritative). |
| Responses | `/api/reports/responses/list` | start, end, limit, (next_page cursor) | Push list: `push_type` (BROADCAST/SEGMENTS/UNICAST/A-B), `sends`, `direct_responses`, `group_id`. |
| Per-push | `/api/reports/perpush/detail/{push_id}` | — | Sends/direct/influenced per push. |
| Push body | `/api/reports/perpush/pushbody/{push_id}` | `push_id` is a **PATH** param (not query) | Per-push creative (notif + Message Center/Email HTML). Scope `rpt`. **Empty body for UNICAST / Create-and-Send.** |
| Content Templates | `/api/content/templates` and `/{template_id}` | page_size, page, sort, order | Reusable creatives (`type` email/sms/…) with `content.{subject, html_body, plaintext_body}`. **Scope `tpl` (Content).** This is where template-driven (unicast) campaign creatives live. |
| Events | `/api/reports/events` | start, end, precision=MONTHLY, page_size, page | name, location, conversion, count, value. **Paginate all pages.** |
| Events per push | `/api/reports/events/summary/perpush/{push_id}` | — | Custom events attributed to one push (name/conversion/location/count/value). Scope `rpt`. |
| Events per group | `/api/reports/events/summary/pergroup/{group_id}` | — | Custom events attributed to a campaign (all sends in the group). Scope `rpt`. |
| Experiment overview | `/api/reports/experiment/overview/{push_id}` | — | A/B experiment result summary. Scope `rpt`. |
| Experiment variant | `/api/reports/experiment/detail/{push_id}/{variant_id}` | — | Per-variant experiment detail. Scope `rpt`. |
| Activity | `/api/reports/activity/details` | — | Extra granularity if accessible. |

### Allowed APIs: Reports + Content ONLY
This skill calls **only** the Reports API (`/api/reports/*`, scope `rpt`) and the
Content API (`/api/content/templates`, scope `tpl`).

**Do NOT call** `/api/pipelines`, `/api/schedules`, or `/api/experiments` (the
management endpoints). They are out of scope. Instead:
- **Campaign typology** (one-shot vs automated/recurring): derive from `responses/list`
  push types + the `classify_campaigns.py` heuristic (group by `group_id` + normalized
  `message_name`, detect cadence).
- **Experiments**: detect via `push_type == A_B` in `responses/list`, then read the
  Reports experiment endpoints (`experiment/overview` / `experiment/detail`, scope `rpt`).
- **Content Templates**: `/api/content/templates` (+ `/{template_id}`), scope `tpl`.

**Never fabricate** automation/experiment data; if it can't be derived from Reports,
state "not available from the Reports API".

Dates accepted as `YYYY-MM-DD`. To page `responses/list`, follow `next_page`
(`push_id_start` + `resume_at_time`). A too-narrow window returns only the latest
(small) sends; target peak-send days to find broadcasts.

## Scope of measurement — snapshot (whole base) vs period
Keep these two families of metrics **strictly separate** in analysis and in the report;
never mix a snapshot figure with a period figure in the same KPI.
- **Snapshot / whole base** = `/api/reports/devices` **only**. Point-in-time state of the
  entire installed base at `date_closed`: `unique_devices`, `opted_in`, `opted_out`,
  `uninstalled` per platform. This is the **only** source for the **opt-in rate** and
  installed-base size. Tag these "(snapshot DD/MM)".
- **Period** = `sends`, `opens`, `optins`, `optouts`, `events`, `responses/list`,
  per-push/per-group reports — all bounded by the analysis window. `optins`/`optouts`
  are **event flows during the period**, NOT a net change of the installed base, and they
  do **not** equal the snapshot `opted_in`/`opted_out` counts. Tag these "(period)".
- A period opt-in/opt-out **event** balance (sum optins − sum optouts) describes activity
  flow only; it must never be presented as "the base grew/shrank by X".

### Creative retrieval — which source by send type
Determine each top campaign's `push_type` from `responses/list`, then pick the source:

| Send type | Has per-push body? | Where the creative lives |
|---|---|---|
| **BROADCAST / SEGMENTS / A-B** (mass) | ✅ Yes | `GET /api/reports/perpush/pushbody/{push_id}` → notif text + Message Center / email HTML. |
| **UNICAST / Create-and-Send** (1:1, automation/journey) | ❌ Empty | per-push body is blank → use the campaign's **Content Template**: `GET /api/content/templates` (scope `tpl`), match by `name`/`type`, read `content.html_body`. |

Rules of thumb:
- Only call `perpush/pushbody` for **non-unicast** pushes; for unicast it wastes calls and returns nothing.
- Only scan `/api/content/templates` when the project actually runs **template-driven / unicast** campaigns (automations, journeys, transactional). For a pure-broadcast project the templates list is not the campaign creative — skip it.
- Legacy `/api/templates` (List/Lookup template) is deprecated and not covered by an active scope on most projects → expect 401; use `/api/content/templates` instead.
- Render real `html_body` with `scripts/render_email.py` (faithful preview). Reconstruct
  illustratively (`scripts/render_mocks.py`) **only** when neither source returns content.

## Campaign typology — one-shot vs automated/recurring
Goal: separate **one-shot** sends (manual, sent once) from **automated/recurring**
campaigns (journeys, automations, recurring schedules) and rank/analyse them separately.

Detection — **Reports API only** (do NOT call `/api/pipelines` or `/api/schedules`):
1. **Heuristic from reports**: group `responses/list` pushes by `group_id`, then by
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

## Experiments (A/B) detection — Reports API only
Do NOT call `/api/experiments`. (a) Flag any `responses/list` push with
`push_type == A_B`; (b) for those `push_id`s pull
`/api/reports/experiment/overview/{push_id}` and `/experiment/detail/{push_id}/{variant_id}`
(scope `rpt`) for variant performance + winner. If none found, state "no experiments
detected in the period".

## Value-bearing custom events
`value` is a **client-declared counter/weight, not currency**. Flag an event as
*value-bearing* when **both**: (a) its `name` implies a measurable quantity — e.g.
`purchase`, `order`, `revenue`, `amount`, `price`, `cart`, `checkout`, `watch`, `vod`,
`play`, `view_time`, `duration`, `minutes`, `points`, `qty`, `quantity` — **and** (b) its
aggregated `value` (or per-event avg `value`/`count`) is non-zero. For each flagged event,
add **per-message attribution** via `events/summary/perpush/{push_id}` on the top messages
(and `events/summary/pergroup/{group_id}` for recurring campaigns), reporting `direct` /
`indirect` / `unattributed` count and value. Always restate the not-currency caveat.

## Unicast → recover campaign categories
For `UNICAST` the `perpush/pushbody` content is empty, but campaign metadata may still be
recoverable. Best-effort, in order: (a) still call `pushbody` — `push.campaigns.categories`
and `push.options.message_name` are sometimes present even when `notification` is empty;
(b) parse `message_name` tokens (e.g. `welcome`, `winback`, `abandon`, `transactional`).
Use the recovered categories to label the campaign **type** in the top-unicast view; if
nothing is recoverable, label "category unavailable".

## Templates inventory & usage
From `/api/content/templates` (scope `tpl`): report `total_count`, `type` mix
(email/sms/…), creation/modification recency, and `feed_references` / `snippet_references`
(dynamic personalization). **Usage mapping is best-effort** (no direct "where-used" API):
cross-reference each template `name` against `message_name`/`campaigns.categories` seen in
pushbodies; use `modified_at` recency as an activity proxy. Label the usage column
"best-effort". (Reports + Content APIs only — no pipelines/schedules lookups.)

## Verification & confidence
Attach to **every** insight/reco a verification basis and a confidence level.
- **Verification basis**: name the source endpoint(s) and the sanity checks that pass —
  per-platform sums reconcile with reported totals; rates fall within 0–100%; the sample
  size (sends/devices/event count behind the figure) is stated; the period is fully
  covered (all `next_page`/pages pulled); the scope was actually available (not degraded).
- **Confidence scale**:
  - **High** — measured `[Data]`, complete (all pages, no 401/403 gaps), large sample,
    and corroborated by ≥2 signals or reconciling sums.
  - **Medium** — measured but single-source, partial data, moderate sample, or one
    heuristic step (e.g. name-normalized recurrence without `pln`).
  - **Low** — small sample, degraded scope, or `[Brand context]` hypothesis not yet
    confirmed by data. Brand-context-only insights are capped at **Low**; low-sample or
    degraded-scope ones at **Medium** max.
- Low-confidence items must carry a **"to verify"** note stating what would raise
  confidence (wider window, missing scope `<x>`, larger sample, corroborating source).

## Industry benchmarks
Per-industry peer values used to position the client's KPIs. Source = the **Airship UA
Benchmarks** workbook (per quarter). Human reference: `benchmarks.md`; machine-readable:
`benchmarks.json` (scripts read this one). Regenerate when a new quarter ships:
`python scripts/import_benchmarks.py <UA_Benchmarks.xlsx>`.
- **Select the vertical** from step 1 (deduced from brand research, confirmed by the user),
  matching a vertical key via its `aliases` (e.g. retail/grocery → `retail`,
  bank/insurance → `finance_insurance`, news/TV/publisher → `media`, telecom/operator →
  `utility_productivity` as nearest proxy — flag the proxy). No match → use `all_verticals`
  as a labelled baseline or state "no matching vertical".
- **Compare like-for-like, per device family**: align metric, platform and denominator.
  Show client value vs the vertical **median (p50)** and the **[p10–p90] range** and the gap.
  Percentiles legend: **Low=p10, Medium=p50, High=p90**.
- **Pressure is PER MONTH** (`sends_per_user_month`): the skill's marketing pressure is
  sends/opted-in user/**week** → multiply by ~4.33 (or recompute monthly) before comparing.
- **Region = global, no locale split**; the workbook has no `n`. Cite `source + quarter + region`.
- **Confidence**: benchmark comparisons are external/contextual → cap at **Medium**. If
  `benchmarks.json` is empty, the vertical/metric doesn't match, or the file is stale,
  **do not compare** — state "industry benchmark not available". **Never fabricate** a value.
- Canonical metric keys (must match `benchmarks.json`): `optin_rate` (ios/android),
  `direct_open_rate` (ios/android/web), `influenced_open_rate` (ios/android),
  `sends_per_user_month` (ios/android), `message_center_read_rate` (vertical-only).
  No benchmark exists for opt-out rate or a blended (cross-platform) opt-in rate → compare
  opt-in per platform; for opt-out, state "no benchmark".

## Definitions
- **Direct**: action after a direct open of the push.
- **Indirect (influenced)**: action after push received without a direct open, within
  the attribution window.
- **Unattributed**: action with no associated push.
- **Push-attributed** = direct + indirect.
- **Opt-in rate** = opted_in / unique devices (devices snapshot).
- **Opt-in/opt-out events**: daily permission state changes; not net base change.
- **Event `value`**: client-declared counter/weight, **not currency** — never convert to money.
- **Marketing pressure** (indicator): messages sent per addressable user per week, over the
  period. Always report it **two ways**:
  - **Cross-platform pressure** = total sends (all channels) / weeks / total addressable
    base. A blended top-line; useful but can mask per-channel over/under-use.
  - **Per-platform pressure** = channel sends / weeks / that channel's addressable base —
    compute **one figure per active channel** (push iOS, push Android, push blended, email,
    web push, SMS…). This is the new required breakdown.
  - **Denominator must match the channel** (never divide email sends by the push opted-in
    base): push → `opted_in` (snapshot, `/devices`); email/SMS → that channel's addressable
    /opted-in count from `/devices` when present; web push → web `opted_in`. If a channel's
    denominator is unavailable (e.g. email shows 0 active devices), report pressure as
    sends/week only and flag the missing denominator (cap confidence at Medium).
  - Weeks = period days / 7. Tag "(period)". Flag channels whose pressure is far above/below
    the others (over-solicitation risk vs under-use opportunity).
- **`location` values**: `custom` (app behaviour), `in_app_message` (fullscreen),
  `in_app_pager` (carousels/stories), `ua_mcrap` (Message Center), `ua_interactive_notification`
  (notification buttons).

## Channels
- A channel is **present** only if devices/sends > 0. State absent channels (often
  Email/SMS/Web) explicitly; do not create empty pages.
- Web push devices that are all opted-out = channel not activated.

## Airship branding (visual)
Confirm against airship.com if possible.
- Ink / dark bg: `#16161D`; text `#1A1A2E`; grey `#6A6A82`.
- Primary accent (red/coral): `#E7233E`.
- Secondary: indigo `#3D2CE0`, blue `#2A5BD7`.
- Positive/tertiary: mint `#12B886`.
- Light neutral / panels: `#F5F5F7`; hairline `#E5E5EC`.
- Sans-serif, generous whitespace, bold titles, big-number KPIs.
- Footer: "Powered by Airship" + "Confidential document".
- Origin tags: `[Data]`, `[Brand context]`, `[Data+Context]` (localize labels per report language).

## Page / PDF rules
- HTML: `@page{size:1240px 1754px;margin:0}` + `.page{width:1240px;height:1754px}`.
- PDF: Chrome `--headless=new --print-to-pdf --no-pdf-header-footer`.
- PNG: PyMuPDF render at 2x, stitch pages vertically.
- Verify final PDF page count equals the number of `.page` divs (no overflow).
