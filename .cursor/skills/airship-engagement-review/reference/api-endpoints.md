# Reference — Reports API endpoints and their traps

Part of the [reference index](../reference.md). Read the files the index routes to your task, not the whole folder.

## MCP access

Each client project is a **separate MCP server** in Cursor (`~/.cursor/mcp.json`).
The Agent calls `call_airship_api` on that server (e.g. `user-Client A PROD`).
Setup: OAuth credentials in Airship (**scope `rpt` only**), env vars
`AIRSHIP_APP_KEY`, `AIRSHIP_CLIENT_ID`, `AIRSHIP_CLIENT_SECRET`, `AIRSHIP_REGION`.
Full walkthrough: [setup-mcp.md](../setup-mcp.md).

## Airship Reports API endpoints
Call via MCP `call_airship_api` with `{method, path, params}`.

| Data | Path | Params | Definition |
|---|---|---|---|
| Sends | `/api/reports/sends` | start, end, precision=DAILY | Notifications sent per platform (ios/android/sms/email/web). **Not push-only** — totalling every platform and calling it push overstated pressure by 29% on a live account ([trap](#trap-the-sends-endpoint-is-not-push-only)). |
| Opens | `/api/reports/opens` | start, end, precision=DAILY | App/notification opens as counted by Airship (influenced included). |
| Opt-ins | `/api/reports/optins` | start, end, precision=DAILY | Daily opt-in **events** (not net base; includes re-detections/reinstalls). |
| Opt-outs | `/api/reports/optouts` | start, end, precision=DAILY | Daily opt-out **events**. |
| Devices | `/api/reports/devices` | — | Snapshot: unique devices, opted_in / opted_out / uninstalled per platform → **opt-in rate** (authoritative). |
| Responses | `/api/reports/responses/list` | start, end, limit, (next_page cursor) | **PUSH-ONLY** list (`type: PUSH`, app/web delivery). Full key set: `push_uuid`, `push_time`, `push_type` (BROADCAST/SEGMENTS/UNICAST/A-B), `group_id`, `sends`, `direct_responses`, `open_channels_sends`. **No `rich_sends`** — an inbox-only Message Center therefore reads as `sends: 0` here ([below](#sends-and-rich_sends-count-different-audiences-and-both-are-correct)). Does **not** enumerate standalone email/SMS. |
| Per-push | `/api/reports/perpush/detail/{push_id}` | — | Sends/direct/influenced per push. Also returns **`app_key`** (use it for deep-links). **For email/SMS the channel metrics are the top-level `sends`/`direct_responses`/`influenced_responses` fields** (`direct_responses`=clicks, `influenced_responses`=opens) — the nested `platforms` object only breaks out `amazon`/`android`/`ios`/`web` and has no `email` key. |
| Per-group | `/api/reports/pergroup/detail/{group_id}` | — | **Whole-program** aggregate for an automation/recurring group: top-level `sends`/`direct_responses`/`influenced_responses` + `platforms` split + **`app_key`**. Key for **firehose** accounts (a single group can be tens of millions of sends). |
| Per-push series | `/api/reports/perpush/series/{push_id}` | `push_id` is a **PATH** param; optional `precision` | Per-push response **time series** (sends/direct/influenced over time). Use for the **shape/trend** of a recurring or high-volume send, not just its totals. Scope `rpt`. |
| Push body | `/api/reports/perpush/pushbody/{push_id}` | `push_id` is a **PATH** param (not query) | Per-push creative (notif + Message Center/Email HTML when present in payload) + `options` (`message_name`, `personalization`, `bypass_frequency_limits`, and **`__ui_id`** = the Flight Deck composer id). Scope `rpt`. **Usually empty body for UNICAST / Create-and-Send** (metadata may still be present; no Content API fallback in this skill). |
| Events | `/api/reports/events` | start, end, precision=MONTHLY, page_size, page | name, location, conversion, count, value. **Paginate all pages.** |
| Events per push | `/api/reports/events/summary/perpush/{push_id}` | — | Custom events attributed to one push (name/conversion/location/count/value). Scope `rpt`. |
| Events per group | `/api/reports/events/summary/pergroup/{group_id}` | — | Custom events attributed to a campaign (all sends in the group). Scope `rpt`. |
| Experiment overview | `/api/reports/experiment/overview/{push_id}` | — | A/B experiment result summary. Scope `rpt`. |
| Experiment variant | `/api/reports/experiment/detail/{push_id}/{variant_id}` | — | Per-variant experiment detail. Scope `rpt`. |
| Activity log | `/api/reports/activity/details` | start, end, limit, (next_page URL) | **Dashboard Activity Log (API)** — non-unicast push activity (`type`: `PUSH` or `GROUP`). Each row: `push_id`, `timestamp`, `experiment`, `details.delivery` (silent/alerting/rich/web) + `details.interaction` (direct/influenced opens). **Excludes** unicast/automation micro-stream (see below). **Push-only** — not email/SMS. Paginate via `next_page` (full URL). |

### Allowed APIs: Reports ONLY
This skill calls **only** the Reports API (`/api/reports/*`, scope **`rpt`**).

**Do NOT call** the Content API (`/api/content/templates`, scope `tpl`), `/api/pipelines`,
`/api/schedules`, or `/api/experiments` (management endpoints). They are out of scope.
Instead:
- **Campaign typology** (one-shot vs automated/recurring): derive from `responses/list`
  + activity log, merged via `activity_log.py`, then the `classify_campaigns.py` heuristic.
- **Experiments**: detect via `push_type == A_B` in `responses/list`, then read the
  Reports experiment endpoints (`experiment/overview` / `experiment/detail`, scope `rpt`).
- **Creatives**: `perpush/pushbody` only; illustrative fallback when empty (UNICAST).

**Never fabricate** automation/experiment/template data; if it can't be derived from Reports,
state "not available from the Reports API".

Dates accepted as `YYYY-MM-DD`. To page `responses/list`, follow `next_page`
(`push_id_start` + `resume_at_time`). A too-narrow window returns only the latest
(small) sends; target peak-send days to find broadcasts.

**`limit=100` is a server ceiling, not a convention.** Verified read-only: `limit=1000`
returns 200 OK with **100 rows and a `next_page`**, while `limit=3` returns exactly 3. So
the parameter is honoured below 100 and silently capped above it — there is no page-size
win to be had, and a firehose day of ~1M pushes costs ~10 000 pages whatever you ask for.
Do not re-litigate this; reduce the number of rows you need instead (see 1b/1c below).

### Activity log — push programs & one-shot broadcast discovery
`GET /api/reports/activity/details` mirrors the **Flight Deck Activity Log**: a unified,
chronological list of dashboard/API **non-unicast** sends. Per Airship docs, **unicast
messages and Automation/Sequence micro-sends are not included** — which is exactly why this
endpoint complements `responses/list` on high-volume accounts.

| | Activity log | `responses/list` |
|---|---|---|
| **Includes** | Broadcasts, segments, A/B, group-level rows (`type: GROUP`) | All push rows incl. UNICAST / triggered micro-sends |
| **Excludes** | Unicast / automation long tail | Standalone email/SMS |
| **Best for** | **One-shot broadcast inventory**, marquee sends, program (`GROUP`) lines, fast full-period scan | `push_type`, `group_id`, cadence / typology, micro-send stream |
| **Pagination** | Usually tractable (dashboard sends only) | Can be intractable on firehose accounts |
| **Sends in row** | `max(alerting, rich) + silent + web.total` ≤ reach ≤ sum of all four — see below | Top-level `sends` (**no `rich_sends`**) |
| **Rates in row** | `details.interaction` (discovery only) | `direct_responses` / `influenced_responses` |

**Required for every audit:** paginate the activity log across the **whole analysis window**
(`limit=100`, follow every `next_page` URL until absent). Store raw rows in the audit JSON as
`activity_log`.

#### `rich` is NOT a subset of `alerting` — reach is an interval

This row used to prescribe summing `silent + alerting + rich`, and `collect.py` used to drop
`rich` as redundant. **Both cannot be right, and neither is.** Measured read-only on 217
activity rows of a production account: **9 rows carry `rich > alerting`**, including one at
`alerting=8 039 / rich=16 729` and one at `alerting=0, silent=0, rich=6`.

- Summing all three **double-counts** every device that was both notified and given an inbox
  copy. On those 217 rows it produced **80 740** devices against **72 350** for the coherent
  lower bound — an **11.6% overstatement** of a figure a report publishes.
- Dropping `rich` **loses an entire class of message**: the `alerting=0, silent=0, rich=6`
  row is a Message Center drop with no notification, and it ranked at zero.

Until Airship confirms whether the notified audience is contained in the inbox audience,
**state reach as an interval**, `[max(alerting, rich) + silent + web, sum of all four]`, or
state one end and say which. `activity_log.rich_overlap()` measures the gap per account and
records it in the audit; `verify_audit.py` raises an advisory when a published figure equals
the additive total.

For **ranking** — deciding which messages are worth a `perpush/detail` call — use the lower
bound `activity_log.reach_bound()`. It is the only one of the two that neither hides
inbox-only messages nor lets a notified message crowd out a genuinely larger one.

#### `sends` and `rich_sends` count different audiences, and both are correct

Not a defect, and the skill nearly published it as one:

- **`sends` / `alerting_sends`** count the alerting notification, so only devices **opted in**
  to push.
- **`rich_sends`** counts the Message Center inbox drop, which also reaches devices **opted
  out** of push. So `rich_sends > sends` is normal on a Message Center campaign and needs no
  explanation beyond this one.
- A **Message Center sent without a notification is a push message, not an in-app one.** Its
  `sends: 0` is the correct figure — it emitted no notification — and its real volume is
  `rich_sends`.

`responses/list` does **not** carry `rich_sends` (full key set: `direct_responses`,
`group_id`, `open_channels_sends`, `push_time`, `push_type`, `push_uuid`, `sends`), so an
inbox-only Message Center enters the inventory at `sends: 0` and ranking on `sends` alone
makes it permanently invisible. `collect.py` resolves a small evenly-spread sample of
zero-send rows (`DETAIL_INBOX_PROBE`) for the sole purpose of finding them, and labels any
`sends == 0 and rich_sends > 0` message as a Message Center without notification.

### Time-window quirks that silently corrupt totals

Three behaviours produce wrong numbers with no error. All three were hit on real audits.

**`end` is INCLUSIVE.** Tiling a period as `[t, t+span)` re-reads every boundary row, so
contiguous windows double-count. Tile as **`[t, t+span-1]`** *and* **de-duplicate on
`push_uuid`** — belt and braces, because the overlap is silent and inflates volume by a few
percent, which reads as plausible. `scripts/push_firehose.py:tile()` does both.

**`start == end` returns HTTP 500.** The smallest usable window is **2 seconds**, which sets
the floor for any adaptive time-partitioning descent.

**`responses/list` and `/api/reports/sends` legitimately disagree.** `/api/reports/sends`
counts **alerting** notifications; `responses/list` `sends` also counts **silent (data-only)**
pushes. On a telecom account the gap was **about 12%** — entirely explained by a
a silent share of the same size. Quote both without reconciling and the report contradicts itself.
**`/api/reports/sends` is authoritative for volume KPIs.** `perpush/detail` is the only
endpoint that separates the two (`alerting_sends` / `silent_sends` / `rich_sends`), and it is
per-push, so the split has to be sampled:
```bash
python scripts/push_firehose.py sample "<MCP project>" <start> <end> data/perpush_sample.json
python scripts/push_firehose.py reconcile data/pushes data/core.json data/perpush_sample.json
```
`reconcile()` returns a report-ready verdict and flags any residual the silent share does not
explain (check window alignment and de-duplication first).

#### TRAP: the sends endpoint is not push-only

> Summing every platform it returns and calling the result push sends.
>
> The endpoint breaks sends down by platform **including `email` and `sms`** (see the table
> above), and it is authoritative for volume KPIs (just said, and true). Both statements are
> correct, and together they invite the mistake: the natural way to get "sends over the
> window" is to total the platforms, and the total silently includes channels that are not
> push.
>
> Measured on a live account with a real email programme: marketing pressure came out at
> **14.71 sends per opted-in device per month against a true push figure of 11.38 — a 29%
> overstatement**, on the report's single most quoted number. Nothing caught it. Every
> internal check passed, because the arithmetic was self-consistent; the denominator was
> the opted-in *device* base while the numerator had quietly become all-channel.
>
> **Push is `ios` + `android` + `web` (+ `amazon`).** `email` and `sms` are separate
> programmes with their own reachable base, and dividing them by a device count is
> meaningless. Report an all-channel total only where the label says so.
>
> `scripts/verify_audit.py` now recomputes pressure both ways and fails the audit when the
> stored value matches the all-channel variant, so this cannot reach a section again.
>
> The set of columns that means "push" is declared once, in
> `channel_activity.PUSH_FAMILIES`. Two other places had written it out inline: one omitted
> `amazon`, and one fed the all-channel total into `program_volume_split`'s
> `window_alerting_sends` denominator — the same defect one layer down, understating the
> programme share instead of overstating pressure. Both now read `PUSH_FAMILIES`.

### The API answers `200` when it cannot answer

Three failure modes share one shape: a well-formed response, no error, and numbers that are
wrong. None of them is detectable from the payload — the check has to come from outside it.

**Wrong id type → `200` with every counter at zero.** An endpoint does not reject an
identifier of a type it cannot serve. Measured in **both** directions on live projects: a
Sequence group id returns **about 7 000 sends** on `pergroup/detail` and **`sends: 0`** on
`perpush/detail`; a push id returns `rich_sends: 2` on `perpush/detail` and `rich_sends: 0`
on `pergroup/detail`. Read as "this campaign reached nobody", which is indistinguishable
from the truth. `collect.suspect_zero_details()` flags any id whose counters are all zero
while the inventory saw it deliver, and `verify_audit.py` fails the run rather than let one
reach a table.

**An unsettled window → the same all-zero shape.** No windowed or per-message endpoint states
whether its data has finished consolidating, so a message read too early returns zeros and
returns real numbers two hours later. This cost real analysis time: **three findings written
up as API defects were nothing but an unsettled window.** The only watermark the Reports API
publishes anywhere is `date_closed` / `date_computed` on `/api/reports/devices` — a device
snapshot, so a proxy rather than a guarantee, but measured at **yesterday** on three
projects. `Airship.watermark()` exposes it, collection warns when `--end` runs past it, and
`verify_audit.py` fails the audit. **Never end a window on today.**

**`-1` is a sentinel, not a number.** Several counters return `-1` for "does not apply to
this message" (`rich_read` on a plain push) rather than `null`. Summed, it subtracts from a
total instead of being skipped. Every counter read from the API goes through
`activity_log.nonneg()`.

Two consequences of the first point, both measured while wiring the guard up:

- **An activity-log row of `type: GROUP` carries a GROUP id in its `push_id` field.** The
  field name is the same for both row types, so a naive candidate pool mixes group ids into
  the per-push ranking and `perpush/detail` answers each with 200 and zeros. It happened
  here: 18 group ids went down the per-push endpoint on an internal project, and all 18 were
  programmes that had really delivered. `rank_detail_ids` now keeps them out and returns
  them as `activity_group_ids`, which `s_programs` compares against its own set — the
  activity log can name a programme `responses/list` never showed a row for.
- **`perpush/detail` does not cover Create-and-Send.** For a `CREATE_AND_SEND_PUSH` it
  returns 200 with every counter at zero *and* `created: 0`, while `responses/list` reports
  real sends for the same id (15 of 15 on an internal project). Same family already known
  to return an empty `pushbody`. This is a message class the endpoint does not serve, not an
  id of the wrong type, so `collect.PERPUSH_UNCOVERED_TYPES` classifies it rather than
  flagging it — take volume from the inventory and state that no rates are available.

### What in-app campaigns do and do not expose

Established read-only across several projects.

- **`perpush/pushbody/{id}` works on in-app ids** — Scenes, Surveys, Embedded Scenes. It
  returns the full definition: `reporting_context.content_types` (`scene`, `survey`,
  `embedded`), the Survey `forms` with their questions and stable answer-option ids, and
  `embedded_id` for Embedded Scenes. So the **identity** of an in-app campaign is available;
  what is missing is the **counters**.
- **`activity/details` carries `app.in_app.impressions`, and it is a dead field** — present
  on every row and zero on every row across 354 604 rows / 11 projects. Do not read it, and
  do not report in-app impressions as zero on its authority.
- **`experiment/overview/{id}` returns `404` for an `experiment_id` published in a Scene's
  own `reporting_context`** — discoverable but not queryable, so the join fails.

Consequence for this skill: in-app campaigns stay `cta_only` in the campaign inventory. Their
conversions are attributable through custom events; their delivery and engagement counters
are not available from the Reports API at all.

**A low `attributed_share` is not a failed descent.** On a firehose, compare enumerated sends
to `/api/reports/sends` **per day** and watch the sends-per-push ratio beside it. Measured on
a grocery retailer: 0.476, 0.477 and 0.468 sends per push on three days whose reported sends
varied **fourfold** (644k, 2.61M, 2.00M). A ratio that stable means every push was found; what
is missing was never attributed to a row, because `responses/list` reports a programme's sends
per micro-push and not per broadcast. The residual is therefore the **programme layer's own
volume** — reachable only via `pergroup/detail` — and the metric is named `attributed_share`
rather than coverage or fidelity, both of which read as a defect that is not there.

**A sampled rate is not automatically a constant.** `sample_split()` runs `_drift()` over the
per-day rates and refuses to bless a blended mean when the rate is unstable: on a telecom account the
silent share sat at **2.3–4.3% until 13 July then jumped to 17–23%**, so the 13.7% average
described no actual day and hid the real finding (a data-only push mechanism switched on
mid-window). **Whenever you sample to extrapolate a rate, test for drift before collapsing it
to one number**, and report the trend and its breakpoint when it fires.

**Merge with `responses/list` before classification** using
`scripts/activity_log.py` → `merge_push_inventories(responses_pushes, activities)`:
- **`activity_only`** push_ids → almost always **one-shot broadcasts** missed by a sampled
  `responses/list` pull; **must** appear in the push reach ranking and one-shot profile.
- **`responses_only`** → typically UNICAST / automation micro-sends (expected — activity log
  excludes them).
- **`type: GROUP`** rows → program-level activity-log lines; cross-check against
  `pergroup/detail` for the push-program ranking.
- Run `classify_campaigns.classify()` on the **`merged`** inventory (not responses alone).

**Performance sourcing (unchanged):** activity-log delivery/interaction totals are fine for
**discovery, shortlists, and coverage stats** — but report KPIs (reach ranking, rate ranking,
matrix cells, benchmarks) still use **`perpush/detail`** / **`pergroup/detail`** as the
authoritative source. Pull detail for every top activity-log broadcast and every ranked program.

**Do not use activity log for email/SMS** — it is push-only (same as `responses/list`).
Email performance still comes from `perpush/detail` top-level fields when you know the
`push_id` (see below).

### Email / SMS performance — use the per-push report, not the activity log
Email (and SMS) are **not SDK platforms**: they are never broken out in the `platforms`
object of `responses/list` or `pergroup/detail`, and the activity log can show **0 or
nothing** for an email message even when it actually sent. **Do not conclude "email not
sent" or "0 sends" from `responses/list`/`pergroup/detail` alone.**

**Standalone email/SMS is NOT enumerable from the Reports API.** Both `responses/list` and
`activity/details` are **push-only** (verified read-only: every row is `type: PUSH`, app/web
delivery). So there is **no list endpoint** that hands you the set of email/SMS messages.
Per-message email/SMS is reachable **only when you already know its `push_id`/`group_id`**
(user-supplied email IDs, or a step recovered from a journey/pushbody). This is why the skill
takes **optional email message/group IDs** as an input: with them you build a real
per-message email table; without them, report the **aggregate email funnel** (email `sends`
from `/reports/sends`, opens/clicks from `/events`) and **state this limitation** — never
fabricate per-message email rows. Do **not** re-probe `activity/details`/`responses/list`
expecting email; they will only ever return push.
- **Source of truth for a top email message**: `GET /api/reports/perpush/detail/{push_id}`.
  Read the **top-level** fields, not `platforms`: `sends` = email sends, `direct_responses`
  = email **clicks**, `influenced_responses` = email **opens**.
- Finding the `push_id` to query: take it from `responses/list` when the row is present
  there, or query `perpush/detail` directly on the message/group id you already have (e.g.
  supplied by the user, or recovered from a pushbody/journey step). For a recurring email
  step, `pergroup/detail` aggregates the same top-level fields across occurrences — trust
  its top-level totals the same way; a `0` there still needs corroborating with the email
  `opted_in` count in `/reports/devices` before calling the channel inactive.
- **Cross-check presence**: only state a project's email channel is "inactive"/"not
  addressable" after confirming **both** (a) `/reports/devices` shows `opted_in: 0` (or
  near-0) for email, **and** (b) `perpush/detail` for that message also shows `sends: 0`.
  If `/devices` shows an email base > 0 but the activity log listed nothing, pull
  `perpush/detail` before reporting "0 sends" — the message very likely did send.
