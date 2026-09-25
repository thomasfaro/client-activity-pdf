# Reference — endpoints, definitions, branding

## Read only your slice of this file

This file is ~24 000 tokens. **A section agent needs 3–19% of it** and must not read the
rest: the endpoint tables, the i18n contract and the framework scaffold belong to waves 1,
2 and 6, and a wave-4 agent that loads them has spent its context on material it cannot
cite. Find your current line range with `grep -n '^## ' reference.md`, then read those
headings with an offset and a limit.

| Section (canonical key) | Headings it needs | ≈ tokens |
|---|---|---|
| `volume_pressure` | Scope of measurement · Definitions | 2 200 |
| `delivery_shape` | Campaign analysis (per channel) · Definitions | 4 700 |
| `engagement` | Per-channel activity & typology · Definitions | 1 400 |
| `permission` | Scope of measurement · Channels · Definitions | 2 300 |
| `typology` | Campaign typology · Per-channel activity & typology | 1 100 |
| `detected` | Campaign analysis (per channel) · Unicast → recover categories · Verification & confidence | 4 300 |
| `events` | Custom-event contextualisation · Airship Goals | 2 200 |
| `inapp` | Channels · Per-channel activity & typology | 800 |
| `data_foundation` | Data-collection audit enrichment | 1 100 |
| `appendix_events` | Data-collection audit enrichment · Custom-event contextualisation | 1 800 |
| `appendix_attrs` | Data-collection audit enrichment | 1 100 |
| `appendix_campaigns` | Campaign typology · Campaign analysis (per channel) · Verification & confidence | 4 600 |
| `benchmarks` | Industry benchmarks · Internal baseline | 1 000 |
| `strategy`, `playbook` | Campaign purpose & pillar playbook | 2 000 |
| `push_program`, `channels_exp` | Creative coverage · Experiments (A/B) detection · Flight Deck deep-links | 500 |
| `brand_context`, `exec_summary`, `recommendations` | Verification & confidence | 300 |
| `appendix` | Verification & confidence · Definitions | 1 000 |

Across the twelve-section wave-4 pool that is **~28 000 tokens read instead of ~286 000** —
the same semantics reaching each agent, with the 90% that no agent cites left on disk. If
your section is not listed, or the headings named do not cover a metric you must define,
**say so in your reply** rather than reading the whole file: the gap belongs in this table.

**Waves 1–2** (collection and analysis) are the opposite case — they need the endpoint
tables and the time-window quirks in full, and they are one context, not twelve.

## MCP access

Each client project is a **separate MCP server** in Cursor (`~/.cursor/mcp.json`).
The Agent calls `call_airship_api` on that server (e.g. `user-Client A PROD`).
Setup: OAuth credentials in Airship (**scope `rpt` only**), env vars
`AIRSHIP_APP_KEY`, `AIRSHIP_CLIENT_ID`, `AIRSHIP_CLIENT_SECRET`, `AIRSHIP_REGION`.
Full walkthrough: see **Prerequisite — configure the client project as an MCP server**
in [SKILL.md](SKILL.md).

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
pushes. On a telecom account the gap was **11.6%** (2 028 319 vs 1 817 381) — entirely explained by a
13.7% silent share. Quote both without reconciling and the report contradicts itself.
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
Sequence group id returns **6 968 sends** on `pergroup/detail` and **`sends: 0`** on
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

## Per-channel activity & typology (robust, Reports-only)
Because push is enumerable but email/SMS are **not listable** from Reports, per-channel
robustness comes from combining three endpoints. Use `scripts/channel_activity.py`.

**1. Detect every active channel from `/api/reports/sends` (per-channel daily), not `/devices`.**
`/sends` returns per-day columns `ios`, `android`, `amazon`, `web`, `email`, `sms`. A channel
is **active** if its period volume > 0 — even when `/devices` shows `opted_in: 0`. This is a
real, verified trap: e.g. a project can show `email opted_in: 0` in the snapshot while sending
tens of millions of emails in the period. `channel_summary(...)` sets
`email_active_but_zero_optin: true` for exactly this case. Never declare a channel inactive
from the `/devices` snapshot alone.

**2. Email funnel from Airship standard events** (`email_funnel_from_events(events)`).
Email engagement surfaces in `/api/reports/events` as standard events with `location: custom`:

| Event name | Funnel stage |
|---|---|
| `injection` | injected (accepted by Airship) |
| `delivery` | delivered (accepted by receiving MTA) |
| `initial_open` | unique opens |
| `open` | opens (incl. repeats) |
| `click` | clicks |
| `bounce` | bounces |
| `spam_complaint` | spam complaints |
| `unsubscribe` | unsubscribes |
| `open_tracking_opt_out` | open-tracking opt-outs |

From these: delivery rate = delivered/injected; open rate = unique_opens/delivered; CTR =
clicks/delivered; CTOR = clicks/unique_opens; bounce/spam/unsubscribe rates. This is the
**robust email KPI set** the Reports API supports without a message list. Position vs the
`[Internal baseline]` (no external email benchmark). SMS, when present, is measured from
`/sends` volume (+ any SMS events); per-message needs supplied IDs.

**Email has TWO volume counters and they disagree — reconcile them (gate-enforced).**
`/api/reports/sends` counts email sends over the window; `injection`/`delivery` above come
from the event feed. On a real account the feed injects ~11% more than `/sends` reports for
the same window. A review that put one figure in the executive summary and the other in the
funnel published **more email delivered than sent**, and its headline 52.8% open rate stood
on the funnel's base without saying so — so the rate depended on whichever counter was
wrong. Call `channel_activity.email_reconcile(reports_sends, funnel)` and render
`ri.email_reconcile_note(rec, lang)` in §14 whenever email is active. The rules the note
states are the rules to follow: **volume KPIs use `/api/reports/sends`**, the **open rate
denominator is `delivered`**, and the two counters are never added, averaged, or presented
as one figure. Check `funnel_internally_consistent` too — when injected less bounced does
not return delivered, the feed itself is unreliable and every email rate is provisional.

**3. Automated-vs-one-shot typology PER CHANNEL.**
- **Push** — per campaign, High confidence: `classify_campaigns.classify()` on the merged
  activity-log + responses/list inventory (group_id + normalized message_name + cadence).
- **Email / SMS** — channel-level, Low/Medium confidence when no message list:
  `channel_activity.daily_cadence(daily_series)` classifies the channel's daily send series
  (near-daily continuous ⇒ automated program; sparse spikes ⇒ one-shot heavy). Upgrade to
  per-message typology (group ⇒ automated, single push ⇒ one-shot) when the user supplies
  email/SMS `push_id`/`group_id`.

Every active channel gets its own analysis block: **volume + engagement (funnel/rates) +
typology** — never a bare volume number, never blended with another channel.

## Scope of measurement — snapshot (whole base) vs period
Keep these two families of metrics **strictly separate** in analysis and in the report;
never mix a snapshot figure with a period figure in the same KPI.
- **Snapshot / whole base** = `/api/reports/devices` **only**. Point-in-time state of the
  entire installed base at `date_closed`: `unique_devices`, `opted_in`, `opted_out`,
  `uninstalled` per platform. This is the **only** source for the **opt-in rate** and
  installed-base size. Tag these "(snapshot DD/MM)".
- **Period** = `sends`, `opens`, `optins`, `optouts`, `events`, `responses/list`,
  `activity/details`, per-push/per-group reports — all bounded by the analysis window. `optins`/`optouts`
  are **event flows during the period**, NOT a net change of the installed base, and they
  do **not** equal the snapshot `opted_in`/`opted_out` counts. Tag these "(period)".
- A period opt-in/opt-out **event** balance (sum optins − sum optouts) describes activity
  flow only; it must never be presented as "the base grew/shrank by X".
- **Every count tile in the executive summary states which kind it is (gate-enforced).**
  `(période)` / `(period)` / `(events)` for a flow, `(instantané)` / `(snapshot)` for a
  point-in-time base. The doctrine above existed and a delivered summary still put
  "Opt-ins app 1 765 735" three tiles above "Opt-outs 2 663 252" — read straight down, a
  collapsing base; in fact a snapshot next to thirty days of events. The classification
  lives in `build_facts.KPI_TEMPORAL` and the canonical labels already carry the marker,
  so a tile built from `F["kpis"]` inherits it. Rates are deliberately exempt: nobody
  reads "direct open rate 24%" as a headcount, and tagging them would only add noise.

**Web opt-in and app opt-in are not on the same scale — do not compare them.** Both come
out of `/devices` as a clean `opted_in / unique_devices`, which is exactly what makes the
comparison tempting and wrong. They measure different acts. A browser permission prompt is
fired by the site at a moment it chooses, on a visitor who may never return, and it is
reversed in one click from the address bar; an iOS or Android system prompt is asked once
per install, is costly to reverse, and the denominator is an installed base the user chose
to keep. A web rate near 75% against an app rate near 47% therefore says the two prompts
are different, not that the web audience is more willing. The same applies to anything
built on those bases — messages per opted-in browser against messages per opted-in device
is not a pressure comparison, and reporting it as a ratio ("45× less solicited") is a
finding the client will reject on sight. Report each channel on its own scale, benchmark
each against its own vertical band, and when the contrast looks striking, make the reason
they do not meet the point rather than the ratio.

### Creative retrieval — which source by send type
Determine each top campaign's `push_type` from `responses/list`, then pick the source:

| Send type | Has per-push body? | Where the creative lives (Reports only) |
|---|---|---|
| **BROADCAST / SEGMENTS / A-B** (mass) | ✅ Usually | `GET /api/reports/perpush/pushbody/{push_id}` → notif text + Message Center / email HTML when embedded in the push payload. |
| **UNICAST / Create-and-Send** (1:1, automation/journey) | ❌ Usually empty | No Content API in this skill. Call `pushbody` anyway for **`options.message_name`**, `campaigns.categories`, and any partial metadata. If no HTML/notif content → **illustrative reconstruction** (labelled). |

Rules of thumb:
- Always try `perpush/pushbody` for analysed top messages — even UNICAST may expose metadata.
- **Do not call** `/api/content/templates` or any `/api/content/*` endpoint.
- Render real HTML from pushbody with `scripts/render_email.py`. Reconstruct with
  `scripts/render_mocks.py` **only** when pushbody has no usable creative content.
  `render_email.py` pre-downloads the email's remote CDN images (Airship emails are
  image-based) to local `file://` before rendering, renders headless at scale 1, **kills
  the whole Chrome process group** (leaked headless children are the #1 cause of blank
  renders), and retries a blank frame. If you render email HTML yourself, do the same.

#### Push hero image (rich push) — download it and preview WITH the image
Rich/expanded pushes carry a hero image. In the decoded `perpush/pushbody`, the image URL
sits at:
- iOS: `notification.ios.media_attachment.url` (sometimes under `content[].url`);
- Android: `notification.android.style.big_picture` (or `notification.android.big_picture`).

Do **not** ship a text-only mock when an image exists. Instead:
```python
from render_mocks import fetch_media, render_push
img = fetch_media(image_url, "creatives/hero.jpg")     # None if the download fails
# 5-tuple → renders WITH the real image; 4-tuple → text-only card (fallback)
render_push([(time, title, body, tag, img)], "creatives/push.png", app_name="<App>")
```
`fetch_media` is a plain binary GET (public CDN URL, no auth). If it returns None (or no URL
is present), fall back to the 4-tuple text-only card and label it a reconstruction. The
same push can carry both an iOS `media_attachment` and an Android `big_picture` — either is
enough to treat the push as rich.

#### Message Center / full-screen mobile templates — phone-sized preview only
MC and inbox full-screen templates render as **very tall PNGs** (2000+ px — the full
scrollable page). Never embed them as a bare `<img>` in the report: they overflow mobile
screens and dominate the creatives page.

**At render time** (`render_email.py`):
```python
render_email(html_body, "creatives/mc.png", width=375, max_height=720)
```
`width=375` matches a phone viewport; `max_height=720` keeps only above-the-fold content
(after autocrop).

**In the HTML report** (`report_interactive.py`):
```python
creative_mc_preview(datauri("creatives/mc.png"), "Message Center · …")
```
Wraps the image in `.ir-mc-viewport` (~380–420 px tall, rounded phone frame) with
`object-fit:cover; object-position:top` so any remaining tail is clipped. Use
`creative_push_preview(...)` for push lock-screen cards (natural height).

#### Real app logo — resolve once, reuse in every push preview
For realistic previews, render the notification icon as the **real app logo**, not a colored
tile. Resolve it once during brand research (step 1) and pass it to every `render_push`:
```python
from render_mocks import fetch_app_icon
icon = fetch_app_icon("<App/brand name>", "creatives/app_icon.png", country="fr")  # or "us"
render_push([...], "creatives/push.png", app_name="<App>", app_icon=icon)  # icon=None → tile
```
- **Source order**: (1) iTunes Search API (`itunes.apple.com/search?term=<brand>&entity=software`)
  → `artworkUrl512`/`artworkUrl100` for the iOS App Store icon; (2) Google Play store-page
  `og:image` **only when `query` is an Android package id** (e.g. `com.example.app`) — Play
  *search* is skipped because its og:image is a generic Play logo. Uses a curl fallback (the
  macOS system Python often fails TLS verification, same as `fetch_media`).
- **Override**: if auto-resolution picks the wrong app (common name collisions) or returns
  None, the user can supply the exact **App Store name / country** or the **Android package
  id**; pass that as `query`. Document which source produced the logo.
- If no logo is found, `render_push` keeps the colored accent tile — acceptable fallback,
  but prefer the real logo whenever it resolves.

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

## Campaign purpose & pillar playbook (the consultative strategy layer)
On top of the one-shot/automated typology, map every campaign to *what it is for*. This
powers the visual strategy views (maturity matrix, coverage grid, recommendations) and is
implemented by `scripts/campaign_purpose.py` + `campaign_playbook.json`, fed by the canonical
`scripts/campaign_inventory.py`. **Reports API only** — the content used for detection comes
from decoded `perpush/pushbody`, never the Content API.

**Scope — message-first.** The inventory is built PRIMARILY from decodable messages (push,
Message Center, email, SMS) and COMPLEMENTED by in-app / MC CTA signals from `/events`
(`in_app_message`, `in_app_pager`, `ua_mcrap`, `banner - …` customs). CTA-only items carry
just a button label / impression (no full message), so they are tagged `source:"cta_only"`
and their mapping reliability is capped low. `campaign_inventory.build_inventory(...)` unifies
all channels with **no lossy drops** (a min-volume floor is display-only via `bucket_long_tail`);
`split_events(...)` hands the behavioural `location:custom` events to `event_analysis` and the
in-app campaign events here.

**The 6 pillars** (canonical, cross-vertical):
| Pillar | Goal | Typical levers |
|---|---|---|
| Editorial & Content | Maximise content/product discovery | new-content alert, trending, curation, personalised reco, newsletter, live companion |
| Onboarding & Adoption | Activate new users; drive first value | welcome, opt-in/re-opt-in ask, first-action activation, feature education, account creation, cross-device |
| Service & Transactional | Anchor usage with useful/real-time messaging | order/booking status, confirmations, security alerts, reminders, real-time alerts, balance info |
| Lifecycle & Retention | Retain: reactivate, prevent churn, renew | inactive reactivation, win-back, anti-churn, renewal, birthday, abandonment recovery |
| Engagement & Data | Qualify audience via zero/first-party data | NPS/surveys, progressive profiling, gamification, contests, votes, referral |
| Commercial & Monetization | Convert: upsell, cross-sell, promote, subscribe | upsell premium, free trial, promotions, coupons, abandoned-cart offers, loyalty offers |

**Detection — language-aware, high-recall, name-first, content-fallback:**
1. **Detect the label's language** (`detect_lang`, FR/EN heuristic) so tokens are interpreted
   in their own language; aliases stay bilingual.
2. **Name-first, graded, high-recall.** Normalise the `message_name` (accents dropped, alnum
   tokens) and score each catalogue lever by **bilingual EN/FR alias overlap with inflection
   tolerance**: exact token = 1.0, **stem-equal** (light FR/EN stemming, e.g. `decouvrez`~
   `decouvre`, `inscris`~`inscription` family) = 0.85, compound/substring alias ≥5 chars = 0.7,
   **shared 4-char prefix = 0.5** (the broad, recall-first tier). The threshold is deliberately
   low: a partial hit yields a (low-reliability) candidate rather than "no match" — **a broad
   association that may be wrong beats missing a probable one**.
3. **Pillar-priority disambiguation.** When several levers hit, an intent-specific lever
   outranks a generic one via a `priority`/specificity weight (pillar default, overridable per
   lever in `campaign_playbook.json`). E.g. "Je crée ma Carte Club" → `account_creation`
   (onboarding, priority 6), not `loyalty_offer` (commercial); "Je cumule avec la Carte Club"
   stays `loyalty_offer`. Ties then break on vertical relevance. Priority is a tie-break + mild
   score weight, never a hard override (a strong generic match still beats a weak specific one).
4. **Content fallback.** When the name yields no match, pass `bodies={push_uuid: text}` (the
   decoded pushbody **notification text** and/or **Message Center HTML**) — the same scoring
   runs on the body, tagged `basis=content`. Use this for UNICAST/ambiguously-named sends.

**Reliability (numeric, everywhere the mapping is uncertain).** Every mapping exposes
`reliability` ∈ [0,1] = **match quality × basis/source ceiling**: message **name** up to 0.95
(→ High), **body/content** ≤ 0.60 (→ Medium), **`cta_only`** ≤ 0.45 (→ Medium at best). The
High/Medium/Low `confidence` is derived from it (≥0.70 High, ≥0.45 Medium, else Low). Surface
the score with `report_interactive.reliability_pill(score, lang)` so broad matches are shown,
never hidden, but always flagged. **In the report, explain to the reader that this
reliability column/pill is the CONFIDENCE OF THE QUALIFICATION** — i.e. how sure we are the
campaign is correctly mapped to its pillar & lever (High/Medium/Low) — and **not** a
performance metric. `classify_one` also returns `lang`, `basis`, `source` and the
`matched_tokens`.

**The vocabulary is FR/EN only, and the classifier now says so.** On a body written in a
third language the content fallback stops being a fallback and becomes pattern noise: a
German account matched 30 campaigns from content and got 28 of them wrong in one direction,
returning partner coupon pushes as `welcome_onboarding` — which would have shown the client
running the very onboarding programme the review concluded they were missing. So
`covered_by_vocabulary(body_text)` gates the fallback, and a body carrying no French or
English function word comes back `basis="unsupported language"`, `lever=None`. **Treat that
as a signal, not a gap**: if a run returns many of them, the campaign layer has to be read by
someone who speaks the language, and the playbook coverage section must say so rather than
report the classified remainder as if it were the whole book.

**Vertical relevance & "recommended".** Each lever carries a base relevance plus per-vertical
overrides in `campaign_playbook.json`; `relevance(lever, vertical) = verticals.get(vertical,
base)`. A lever is **recommended for the vertical** when relevance ≥ 3. The vertical is
resolved from the brand research (same key family as `benchmarks.json`; `vertical_map`
handles aliases, e.g. `telecom → utility_productivity`).

**Maturity (per pillar) — `pillar_maturity(...)`:**
- **Coverage %** = recommended levers the client already runs (matched at **reliability ≥ 0.45**,
  i.e. ≥ Medium) / recommended levers for the vertical. Tier: ≥70% Mastered, ≥45% In
  consolidation, ≥20% Emerging, else Untapped. Low-reliability (broad `cta_only`) matches stay
  visible in the report but do **not** inflate coverage.
- **Automation share** within the pillar (by campaign count and by sends) and **volume
  share** of total sends.
- **Business stake + key figure** from `campaign_playbook.json` `vertical_stakes[vertical]`
  (falls back to `all_verticals`). Drives the matrix's "Business stake" column and the
  strategic-priority cards. Key figures are contextual → tag `[Brand context]`, confidence
  ≤ Medium.

**Industrialization mix — `automation_mix(...)` (DEPRECATED in the report):** the function
still computes the one-shot vs automated split (by count AND by sends), but the **"today vs
target" viz is no longer shipped** in the standard report — the today-vs-target framing was
dropped for confusing readers. Keep the automated-vs-one-shot read where it is factual: the
**per-channel campaign typology** section, and (optionally) a single account-level
recommendation to rebalance toward automated lifecycle/service.

**Recommended new campaigns — `recommend_campaigns(...)`:** the vertical-recommended levers
NOT run yet, ranked by relevance (× reachable base when provided), each carrying its pillar,
default typology, channels and the business stake it serves. **Treat these as a STARTING POINT
only** — in the report, rewrite each as a concrete proposal **tailored to the brand's business
model & current context** (brand research: recent news, strategy, challenges, competitors) so
the "campaigns to launch" are genuinely relevant to THIS brand, not a generic lever list.
Likewise, the per-pillar **"recommended" use cases in `pillar_coverage`** should be sector/
brand-adapted best-practice ideas (marketer-authored), not raw generic lever labels. Tagged
`[Data+Context]`, confidence ≤ Medium (they rest on detection coverage + vertical guidance +
brand context, not a measured gap in outcome).

**Personalization depth ladder.** Position what the client can already personalise on across
three levels — Level 1 Identity & profile, Level 2 Behaviour & content, Level 3 Context &
prediction — from the data actually present (`/devices` attributes, the event taxonomy from
`event_analysis.py`, custom events). Mark each data point available/not, and note that
deeper targeting typically reduces pressure while lifting performance (state as context).

**Confidence.** The whole layer is contextual and driven by the numeric `reliability`: message
name up to High, content ≤ Medium, `cta_only` ≤ Medium, and the maturity/recommendation/priority
outputs ≤ Medium. Always surface the reliability score + detection basis (name/content/cta_only)
and that stakes/key-figures are external context.

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
totalling **1 847 sends** out of 39.1M, **zero** `type: GROUP` rows and **zero** `group_id`
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

## Unicast → recover campaign categories
For `UNICAST` the `perpush/pushbody` content is empty, but campaign metadata may still be
recoverable. Best-effort, in order: (a) still call `pushbody` — `push.campaigns.categories`
and `push.options.message_name` are sometimes present even when `notification` is empty;
(b) parse `message_name` tokens (e.g. `welcome`, `winback`, `abandon`, `transactional`).
Use the recovered categories to label the campaign **type** in the top-unicast view; if
nothing is recoverable, label "category unavailable".

## Creative coverage (Reports only)
From decoded **`perpush/pushbody`** on analysed messages: report how many top campaigns have
a **recoverable creative** (notif text, MC/email HTML, rich-push image URL) vs an
**illustrative reconstruction**. For UNICAST / template-driven sends where pushbody is empty,
state explicitly that **creative HTML is not available via the Reports API** — metadata
(`message_name`, categories) may still label the campaign type. Never call `/api/content/*`.

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
- **Pressure is PER MONTH** (`sends_per_user_month`) — and so is the pressure this skill
  publishes, by construction. The two align directly: no conversion step, and no weekly
  figure to reconcile. See Marketing pressure under Definitions.
- **Region = global, no locale split**; the workbook has no `n`. Cite `source + quarter + region`
  — through `ri.benchmark_source_note(A["benchmarks"], lang)`, never by retyping the vintage
  in prose. Four delivered reviews cited three different vintages and two cited none, so a
  reader could not tell whether two accounts had been measured against the same ruler. The
  component prints it from the audit block, so the only way it can drift is not using it.
- **A percentile verdict names its sample (gate-enforced).** `ri.gauge(..., sample=…)` —
  "n=412 pushes", "3,9 M appareils", "30 jours". A delivered review graded a direct open
  rate top-decile off **one** push: the arithmetic was right and the conclusion described a
  single campaign rather than the account. Below `GAUGE_SAMPLE_FLOOR` (3) observations,
  word the verdict as inconclusive — "non concluant, un seul envoi" — instead of naming a
  decile. Judgement words ("healthy", "room to grow") are not positional claims and need
  no sample; "above the median", "top decile" and "below p10" do.
- **§3b must carry a real vertical band — the gate blocks a report without one.** At least
  one `ri.gauge(value, p10, p50, p90, …)` plus the source note. Positioning the account
  against its peers is the part of this deliverable the client cannot produce alone, so
  "internal baseline only" is not an acceptable §3b. If the vertical genuinely has no
  published band, declare that in an `na_block()`: a stated absence is comparable across
  accounts, a silent one is not.
- **Confidence**: benchmark comparisons are external/contextual → cap at **Medium**. If
  `benchmarks.json` is empty, the vertical/metric doesn't match, or the file is stale,
  **do not compare** against the external workbook — fall back to the **internal baseline**
  below instead of just stating "not available". **Never fabricate** a value.
- Canonical metric keys (must match `benchmarks.json`): `optin_rate` (ios/android),
  `direct_open_rate` (ios/android/web), `influenced_open_rate` (ios/android),
  `sends_per_user_month` (ios/android), `message_center_read_rate` (vertical-only).
  No benchmark exists for opt-out rate or a blended (cross-platform) opt-in rate → compare
  opt-in per platform; for opt-out, use the internal baseline below.

## Internal baseline — when no external benchmark exists
Most channels/metrics have **no entry in `benchmarks.json`** — e.g. email/SMS opens &
clicks, opt-out rate, blended (cross-platform) rates, web influenced-open, in-app Scene/pager
dismiss rates, and virtually all custom-event attribution. For these, **do not stop at "no
benchmark available"** — instead position the message/channel against **the client's own
other messages of the same type**, over the analysis window:
- **Same type** = same channel (e.g. push, email, in-app Scene) **and** same campaign
  typology (one-shot vs automated/recurring — see "Campaign typology" below; for a
  recurring journey step, its own other occurrences are the natural comparison set).
- Compute the **median** of the metric across those other same-type messages (add the
  **min–max range**, or **[p25–p75]** if the sample is large enough — 8+ messages). Show the
  target message's value **next to** this internal median/range.
- **Tag these comparisons `[Internal baseline]`** (a distinct tag from `[Data]`,
  `[Brand context]`, `[Data+Context]`) so the reader never confuses a client-relative
  reading with an external industry position. State the source as **"client's own history,
  N comparable messages, `<endpoint>`"**.
- **Minimum sample**: at least **3 other same-type messages** to compute a meaningful
  baseline. Below that, state **"insufficient same-type messages for an internal
  baseline"** — do not compare against 1–2 data points.
- **Confidence**: internal-baseline comparisons are capped at **Medium** (small,
  single-client sample) — same cap as external benchmarks, but distinguishable by the
  `[Internal baseline]` tag and the "client's own history" source line.
- Use this **in addition to** the external benchmark wherever a metric IS covered by
  `benchmarks.json` (e.g. push opt-in/open rates): the external benchmark answers "how do we
  compare to peers", the internal baseline answers "is this message on-trend for this
  client" — both are useful and should coexist, not replace one another.

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

## Value measurability — the finding that bounds every revenue claim
Whether a conversion can be tied to an amount decides what Airship is able to *prove* for an
account. The counter-versus-currency heuristic, the tagging plan's declaration and the list
of conversions that ought to carry a value all existed already — in three places, none of
them a verdict. So a report could describe an account's events at length and never say the
one thing that matters: every conversion is a count, so no message can be attached to a euro.
- **`event_analysis.value_measurability(analysis_events, monetary)`** returns one grade,
  rendered by `ri.value_measurability_block()` **inside the events section** (gate-enforced):
  `revenue` · `partial` · `declared_not_flowing` · `counters`.
- **`declared_not_flowing` is deliberately its own grade.** A plan that declares amounts and
  a feed that carries none is a wiring bug someone can fix this sprint. An account that never
  declared any is a product decision. Collapsing the two loses the actionable case.
- **When the grade is `counters` or `declared_not_flowing`, the executive summary must say
  so** via `ri.value_measurability_line()` (gate-enforced). A reader who discovers in §10
  that nothing carries an amount has read nine sections expecting a revenue figure.
- Name the conversions missing their amount (`missing_amount`), not just how many there are.
  A count is not an action.

## Scene instrumentation — grade §8b, do not describe it
Airship's in-app events say a Scene was shown and how it ended. They say nothing about what
happened inside it: which screen a user left on, whether they finished, what they chose.
That gap hides well, because the dismissal count *looks* like data — an account reads "69%
dismissed" and never notices it has no idea what the other 31% did.
- **§8b becomes mandatory as soon as the audit records in-app volume** (gate-enforced). It
  stays a legitimate N/A only at zero: an account running Scenes blind is exactly the case
  worth reporting, and also the easiest to skip.
- **`campaign_inventory.scene_instrumentation_from_audit(A)`** grades three separately
  observable things, rendered by `ri.scene_instrumentation_block()`:
  `outcomes_named` (do buttons carry meaningful identifiers, or only Airship's defaults),
  `screen_transitions` (`swipe-0-1` is screen 0 to screen 1 — more visibility than most
  accounts realise they have), `custom_events` (the app's own events on the flow, the only
  one that supports a **step-level funnel**, because only the app knows what "completed"
  means).
- **The named-button share is measured over button presses, not over all interactions.**
  In-app is dismissal-dominated by nature; the other denominator fails every client for a
  reason unrelated to how they configured anything.
- **The block opens the section**, ahead of the tables (gate-enforced). A reader who stops
  at the dismissal split must first know which question it answers.
- **The remediation is fixed**, in `campaign_inventory.SCENE_REMEDIATION`: custom events on
  Scene view/completion (or Scene event streaming), and explicit button identifiers in the
  composer. Do not re-argue it per client — that is how three reports recommend three things.
- Be conservative on what counts as Scene instrumentation: `onboarding_finished` may be a
  Scene completion or an app onboarding that has nothing to do with one. Only explicit
  naming (`scene`, `in_app`, `pager`, `story`) counts, so no account is credited with a
  grade it has not earned.

## Coverage — say what the review cannot claim, up front
Every collection stage already records how it went in `collect_manifest.json` (`ok`,
`partial` with what it cut, `FAILED` with the exception). Left there, the report then reads
the surviving files and speaks in one voice, as if every figure rested on the same footing.
- **`coverage.assess(manifest, audit)`** turns that record into a grade (`full` / `partial` /
  `degraded`) and a list of claims the run cannot support, phrased in the reader's terms —
  the lost claim, not the missing file.
- **`ri.coverage_banner(cov, lang)`** opens the **executive summary** with it. Not the cover
  (a full-bleed hero page), and emphatically not a methodology appendix: the reader who goes
  on to quote a figure has read the summary. The gate requires it there.
- **Two kinds of gap, kept visibly apart.** A failed or truncated stage is an accident of
  this run and a re-run may fix it. The **structural** blind spots are permanent: the skill
  holds an `rpt` token and calls only `/api/reports/*`, so journey step-level performance,
  A/B declarations and Scene-internal funnels were never reachable. Saying "we did not
  measure journeys" reads as an oversight; saying the Reports API does not expose them reads
  as the fact it is.
- **The banner renders on a clean run too**, and still lists the structural lines. A banner
  that only appears when something broke teaches readers to read its absence as
  completeness — the gate therefore rejects a banner listing zero structural blind spots.

## Proof points — what the lever produced elsewhere
A recommendation that says only *"Lifecycle & Retention: 0%, not started"* tells the client
what they are not doing and nothing about what doing it returns. A proof point closes that:
one outcome from another Airship account, on the same lever, with the document it came from.
- **Rendered only by `ri.proof_point(lever, lang)`**, which reads `proof_points.json` and
  prints nothing when that file has no entry for the lever. `lever` must be a real
  `campaign_playbook.json` `levers[].key` — an invented key silently never matches.
- **Returning "" is the normal case.** No entry means the recommendation ships without a
  proof point. It does **not** mean write one in prose: an outcome figure recalled about
  another client is precisely the figure nobody can source afterwards, and fabricating one
  puts a false claim about a third party in a client-facing document. The gate rejects any
  `ir-proof` block that reaches the HTML without a source attached.
- **Adding an entry is a human act.** It needs a real document (deck, case study, published
  result), its date, and the figure quoted from it — see the `rule` field in
  `proof_points.json`. Entries cleared for an internal review are not automatically cleared
  for a client-facing deck.
- Prefer the sized gap from `scripts/opportunity.py` where one exists: a figure computed
  from this account's own volumes argues the case better than another client's, and needs no
  provenance beyond the report itself. The proof point answers the different question of
  whether the lever works at all.

## Definitions
- **Direct**: action after a direct open of the push.
- **Indirect (influenced)**: action after push received without a direct open, within
  the attribution window.
- **Unattributed**: action with no associated push.
- **Push-attributed** = direct + indirect.
- **One column, one basis — and no ranking on a column that mixes them (gate-enforced).**
  A delivered review shipped a column headed "push-attributed rate" holding
  (direct+influenced)/sends where both terms existed and direct/sends where the influenced
  term was missing, marking only the latter "(direct)". Every cell was arithmetically
  right and the ranking built on them meant nothing. So: the header states the basis, and
  **every** row honours it. A row missing a term is `ri.attributed_conversions_cell(None)`
  or an explicit `n/a` — never the same figure on a narrower basis, which reads as a small
  number rather than as a missing one. If both bases matter, give them **two columns**.
  Never write a superlative ("the best-performing campaign", "×2 the next one") off a
  column carrying an `n/a`: rank on a basis every ranked row actually has, and say which
  one you ranked on.
- **Email/SMS mapping** (per-push report top-level fields, NOT the `platforms` object):
  `sends` = email/SMS sends; `direct_responses` = **clicks**; `influenced_responses` =
  **opens**. Source: `perpush/detail`/`pergroup/detail`, never the activity log alone.
- **Opt-in rate** = opted_in / unique devices (devices snapshot).
- **Opt-in/opt-out events**: daily permission state changes; not net base change.
- **Event `value`**: a client-declared number, **not guaranteed to be currency**. May be a
  per-event counter OR a real amount — decide with the `event_analysis` heuristic
  (`value_per_event`); when it reads as money, label the currency as an **assumption**
  (confidence) and keep the not-currency caveat. Never assert an exact currency amount.
- **Marketing pressure** (indicator): messages sent **per addressable user per month**, over
  the period. **The month is the unit the report always publishes and always benchmarks**,
  because it is the unit of the UA benchmark (`sends_per_user_month`): a figure in any other
  unit only reaches the band through a conversion the reader cannot see, and someone
  comparing two accounts has no way to know one was divided by weeks. This is not a
  stylistic preference — publishing one account at "~1.2 / opt-in / week, pressure under
  control" and another at "0.46 / month, far below median" put two reviews a factor of ten
  apart, both correct, neither comparable. A per-day or per-week figure may sit **beside**
  the monthly one when it reads better (on a firehose account "7 sends per device per day"
  is easier to feel than "212 per month"), but never instead of it, and the benchmark
  comparison is always the monthly one. The gate blocks a report whose only pressure figure
  is sub-monthly. Always report it **two ways**:
  - **Cross-platform pressure** = total sends (all channels) / months / total addressable
    base. A blended top-line; useful but can mask per-channel over/under-use.
  - **Per-platform pressure** = channel sends / months / that channel's addressable base —
    compute **one figure per active channel** (push iOS, push Android, push blended, email,
    web push, SMS…). This is the required breakdown.
  - **Denominator must match the channel** (never divide email sends by the push opted-in
    base): push → `opted_in` (snapshot, `/devices`); email/SMS → that channel's addressable
    /opted-in count from `/devices` when present; web push → web `opted_in`. If a channel's
    denominator is unavailable (e.g. email shows 0 active devices), report **sends/month
    only** and flag the missing denominator (cap confidence at Medium).
  - Months = period days / 30.44 (or a weekly intermediate × 4.33). Tag "(period)". Flag
    channels whose pressure is far above/below the others (over-solicitation risk vs
    under-use opportunity).
  - **Do not put two channels' pressure on one scale when their mechanics differ.** Messages
    per opted-in browser and messages per opted-in app device are different acts on
    different surfaces — see the web/app rule under Snapshot vs period. Report each against
    its own band; never as a ratio between the two.
- **`location` values**: `custom` (app behaviour), `in_app_message` (fullscreen),
  `in_app_pager` (carousels/stories), `ua_mcrap` (Message Center), `ua_interactive_notification`
  (notification buttons).
  - **Conversion / custom-event taxonomy uses `location:custom` BEHAVIOURAL events only.**
    In-app campaign impressions that also live under `location:custom` (`banner - …`) are
    excluded from the taxonomy (`event_analysis.analyze(..., exclude_name_prefixes=("banner - ",))`)
    and routed to the campaign inventory instead. `in_app_message` / `in_app_pager` / `ua_mcrap`
    are **campaign engagement signals** (a low-reliability `cta_only` complement to the
    message-based campaign analysis), not behavioural conversion events. Use
    `campaign_inventory.split_events(events)` to make the split.

## Channels
- A channel is **present** only if devices/sends > 0. State absent channels (often
  Email/SMS/Web) explicitly; do not create empty pages.
- Web push devices that are all opted-out = channel not activated.
- **Email/SMS presence must be judged from two sources together**: the email/SMS
  `opted_in` count in `/reports/devices` AND the top-level `sends` in `perpush/detail`
  (or `pergroup/detail`) for that message — **not** from `responses/list`/activity log,
  which does not reliably surface email/SMS. Only call the channel "absent"/"inactive"
  when both sources agree (see "Email / SMS performance" above).

## Airship branding (visual) — Airship 2026 brand
Sourced from the *AIRSHIP 2026 Master* deck + airship.com. **Don't hand-code these** — use
`report_interactive.brand_report_css()` / `BRAND` tokens / `brand_logo()` (see SKILL §8).
- Ink / dark bg: `#000818`; body text `#414651`; grey `#717680`.
- **Primary accent: Airship blue `#056DFF`.**
- Secondary: navy/indigo `#030869`, sky `#7ABFFF`, light-blue `#DCEAFF`.
- Positive signal: teal `#11DBC0`. Negative signal (opt-out/churn): coral `#E4626F`. Highlight: lime `#E6F55A`.
- Light neutral / panels: `#F7F8F8`; hairline `#E9EAEB`.
- **Fonts (embedded woff2):** display/headings **Zalando Sans Expanded**, body **Instrument Sans**,
  code/tags **Geist Mono**. Generous whitespace, bold display titles, big-number KPIs.
- **Logo assets** in `scripts/assets/`: `airship_logo_white.png` / `airship_logo_ink.png`
  (full wordmark), `airship_mark_blue.png` / `airship_mark_white.png` (diamond mark).
- Footer: "Powered by Airship" + "Confidential document".
- Origin tags: `[Data]`, `[Brand context]`, `[Data+Context]` (localize labels per report language).

## Multi-language (default) — i18n contract
Every report is language-aware. **English is the primary language; French is fully supported**
behind the toggle. The chosen language applies to the **whole** deliverable — content AND the
interactive chrome AND number/date formatting — with **no mixing**, save the one carve-out
below.

- **English is PRIMARY.** `fw.assemble(...)` defaults to `lang="en"`, which decides three
  things at once: what `<html lang>` says, which language block is visible on load, and which
  language the PDF prints (the other becomes screen-only). Keep that default and write the
  `<title>` in English. Build French-primary only when the user asks for a French-primary
  *file* — asking *in* French is a request to be *answered* in French, not necessarily to
  invert the deliverable.
- **Charts are English in BOTH renders — the one deliberate exception to "no mixing".** A
  chart's chrome is a handful of technical words (`Sends`, `Open rate %`, `Direct`/`Indirect`/
  `Unattributed`), and a second chart set doubles the authoring surface for no comprehension
  gain — it is where language bugs come from, not where they get fixed. So `make_charts.py`
  emits exactly one `charts/` + one `specs.json`, both renders read it, and the `spec_*` label
  arguments keep their English defaults. Localise what *frames* the chart instead: the
  `alt`/caption, the prose, the table below it. Axis values that come from client data (event
  names, CTA copy, tag names) are reproduced verbatim in whatever language the data uses —
  that is data, not chrome. The localisation lint is aligned with this: it strips `<script>`
  blocks, so the embedded spec JSON is out of scope by design.

- **Choose once, thread everywhere.** Pass `lang=` ("en"/"fr") to
  `report_interactive.interactive_head(...)`, to `cover_section(...)`, and to the section
  components (`hero_kpi_band`, `strategy_matrix`, `pillar_coverage`, `priority_cards`,
  `personalization_ladder`, `automation_mix`, `kpi_card`, `methodology`, `event_kpi_table`,
  `campaign_inventory_table`, `data_collection_table`). **Every one of them accepts `lang=`**,
  including the few that currently localise nothing, so you can thread it uniformly without
  tracking which is which. `interactive_head` injects `window.IR_I18N` *and* `window.IR_LANG`,
  so the **JS-driven** chrome (search placeholder, "Download CSV", KPI-modal title,
  Expand/Collapse-all) localises even in a **monolingual** report, where there is no
  second-language DOM to switch against. Set `<html lang="...">` and the `<title>` to match —
  the delivery gate reads `<html lang>` to decide which language to lint.
- **Prose generated upstream.** `analyze_tagging_plan.py` and `data_foundation.py` emit their
  findings in both languages (`verdict`/`verdictFr`, `signals`/`signalsFr`, `note`/`noteFr`);
  read the `*_fr` variant when `lang="fr"`. `data_collection_recos(audit, lang=...)` bakes its
  wording in **at analyze time**, so a wording fix means re-running the analyze step, not just
  the build.
- **Chrome strings** live in `_UI_STRINGS` (`report_interactive.py`): Download-PDF,
  Expand/Collapse-all, "How it's computed", Close, filter placeholder, Download-CSV, the
  methodology row labels (Formula/Inputs/Source/Coverage/Confidence/Notes) and the
  confidence-tier labels (High/Medium/Low → Élevée/Moyenne/Faible). `ui_string(key, lang)`
  resolves with an English fallback; `resolve_lang(...)` normalises hints
  ("français"/"french"/… → "fr"). **Add a language** by extending `_UI_STRINGS`.
- **Numbers & percentages** use the locale helpers — `fmt_int` (EN `1,234` · FR `1 234` with a
  narrow no-break space), `fmt_pct` / `fmt_delta` (EN `12.3%`/`+3.0%` · FR `12,3 %`/`+3,0 %`,
  with a **non-breaking** space before the sign, per French typography), `fmt_num`. Do not
  hand-roll separators in per-run build scripts. Pass the *fraction*, not a pre-computed
  percentage — `fmt_pct(0.064)`, never `fmt_pct(6.4)`.
- **Accents are not optional.** French literals in the skill scripts must carry their accents
  (`fidélité`, `téléphone`, `débloqué`); the gate flags a known list of unaccented forms,
  because nothing spellchecks a generated report.
- **Markup in escaped fields.** Several components escape their own text so client data is
  safe to pass. They route prose through `ri.plain_text()` first, so a field may contain the
  report's own idiom (`<code>`, `&amp;`) without it reaching the reader as literal markup.
  Builders do **not** need to pre-sanitize.
- **Playbook labels**: read the `*_fr` fields (`label_fr`, pillar `label_fr`, maturity tier
  `label_fr`) from `campaign_playbook.json` / `campaign_purpose.py` output when `lang="fr"`.
- **Origin/verification tags** and any prose you author in the build script must be localised
  too (e.g. `[Data]`→`[Données]`, `[Context]`→`[Contexte]`, `[Limitation]`→`[Limite]`).

## Deliverable — interactive HTML web-app (primary) + optional PDF companion
The review is delivered as a **single self-contained HTML** file (charts and creatives
embedded as base64 data URIs) that renders as a **web-app on screen**. The *same* file
prints to a **paginated PDF companion**, built only when one is asked for
(`fw.set_pdf(True)` / `--pdf`, which is also what shows the sidebar download button).
Charts always carry their print PNG, so enabling the PDF never means rebuilding. **No PNG
deliverable.**

**Screen vs print — one DOM, two skins.** The scaffold's `@media screen` rules turn the
report into a web-app: a **fixed left sidebar** (brand, Download-PDF, auto section nav with
**scroll-spy**, Expand/Collapse-all), the body wrapped in a **fluid full-width content
column** where prose and data share one width,
fixed A4 `.page` boxes relaxed into fluid cards, larger type, and PDF-only chrome hidden.
`@media print` hides the sidebar and restores the paginated pages, so the **PDF is byte-for-
byte the same as before**. Keep `@page{size:1240px 1754px;margin:0}` + `.page{width:1240px;
height:1754px}` in the per-run CSS — the screen overrides are scoped to `@media screen` and
never leak into print.

**Delivery location:** `write_report(..., client=CLIENT)` copies the HTML to
**`~/Downloads/<Client>_<Review>_<date>.html`** (macOS *Téléchargements*). Do **not** use
`~/Desktop/`. When a PDF is built, put it in the same folder so the in-report Download-PDF
link resolves.

Build blocks live in `scripts/report_interactive.py`:
- `interactive_head(pdf_filename=…, layout="dashboard")` → `(css_block, nav_block, js_block)`:
  the web-app shell — sidebar with auto-TOC + scroll-spy (from `[data-toc]`+`id` sections;
  `data-toc-sub` nests an entry), Download-PDF, Expand/Collapse-all — plus tooltips,
  collapsibles, gauges. `nav_block` opens the sidebar + the fluid `.ir-main` column; `js_block`
  closes `.ir-main` then loads the scripts. `css_block`→`<head>`, `nav_block`→top of `<body>`,
  `js_block`→end of `<body>`. (`layout="bar"` keeps the legacy sticky top-bar for back-compat.)
- Components: `tooltip(text,tip)`, `collapsible(summary,body,open_)`, `gauge(value,p10,p50,p90,
  unit,verdict)`, `verdict_pill(tier,label)`, `flight_deck_button(url)`, `pdf_download_button`.
- **Per-KPI methodology (justify every number).** `kpi_card(value, label, formula=…, inputs=…,
  source=…, sample=…, confidence=…, notes=…)` renders the number + label + a screen-only ⓘ
  button that opens a shared **methodology modal** (formula, inputs *with values*, source
  endpoint(s), coverage/sample, confidence pill). Use it for **every displayed KPI in every
  section** — not only the executive summary — instead of a bare `.card` number.
  `methodology(formula, inputs, source, confidence, sample, notes)` returns the block
  standalone (put it under a chart/table; wrap in `collapsible()` to also carry it into the
  PDF). The modal is screen-only by default (keeps KPI grids compact); pass
  `print_methodology=True` to also render the block inline under the card in the PDF where
  there is room. `interactive_head(...)` injects one `#ir-kpi-modal` shell per report.
- **Tables**: `class="ir-searchable"` adds a filter box; `class="ir-exportable"` (+ optional
  `data-csv-name`) adds a "Download CSV" button (serialises thead+tbody); `ir-sortable`
  (with `th[data-sortable]`) keeps click-to-sort. All three are screen-only (`.no-print`).
- The print stylesheet hides `.no-print`/sidebar/tools and **force-opens every `<details>`**
  so the PDF shows all content.
- **Interactive charts (progressive enhancement, still single-file/offline).** Every chart
  uses `interactive_chart(chart_id, png_data_uri, spec, alt, csv=None)`: a static matplotlib
  **PNG** (the print/fallback `<img>`), a `<canvas>` that the **inlined Chart.js** upgrades on
  screen, and a screen-only **CSV** button that downloads the chart's source data (auto-derived
  from the embedded spec; pass `csv=` to override). `interactive_head(...)` inlines the vendored
  `scripts/vendor/chart.umd.min.js` (Chart.js v4, MIT — see `vendor/NOTICE.md`) once via
  `chartjs_inline()` and the mount script, so there is **no CDN/network dependency**. Emit the
  Chart.js config (JSON-safe dict) from the `spec_*` helpers in `airship_charts.py` sharing the
  PNG's data (`spec_pressure_fatigue`, `spec_timeseries_stacked`, `spec_funnel`,
  `spec_program_ranking`, `spec_donut`, `spec_grouped_bars`, `spec_hbar` — so every chart type
  can be a canvas). The mount reveals the canvas before instantiating Chart (so it measures a
  real height) and, on failure, keeps the PNG; **print always uses the PNG**, so the PDF never
  depends on canvas rendering. Rich hovers come from a plain `_extra` array on a dataset
  (appended in a shared tooltip callback — keeps specs JSON-only). Benchmarks stay as the
  print-safe SVG `gauge()` (no canvas).
- **Mandatory visuals + delivery gate.** A report is only deliverable with **interactive
  charts** and **decoded message creatives** actually rendered. A per-client `make_charts.py`
  emits `charts/*.png` + `specs.json` — **one English set, reused by both language renders**
  (see the i18n contract); the builder loads `SPECS`, defines a `chart(cid)` helper
  around `interactive_chart(...)`, and passes `include_charts=True` to `interactive_head(...)`.
  A bilingual builder suffixes the FR chart id (`cid + "_fr"`, which `fw.chart(..., lang=)`
  does for you) so the two canvases have unique DOM ids — that suffix is about the DOM, not
  about content: both ids point at the same spec and the same PNG.
  Creatives use `creative_push_preview(datauri(...), caption)` /
  `creative_mc_preview(...)`. Before delivery run `python scripts/verify_report.py
  work/<client>/report.html`; it fails when charts or creatives are missing. If an account has
  nothing decodable (e.g. UNICAST-only, empty pushbodies), still ship a labelled
  illustrative/limitation creatives block and re-run with `--allow-no-creatives`.

## Shared framework & canonical scaffold — build here (do NOT hand-roll a builder)
New client builders start from `scripts/build_report_template.py`
(`cp scripts/build_report_template.py work/<client>/build_report.py`) and are driven by three
shared modules so structural completeness, chart integrity and the delivery gate are guaranteed
by construction rather than by remembering to check.

- **`scripts/canonical_sections.py` — the single source of truth for structure.** An ordered
  `CANONICAL_SECTIONS` list of section specs: `key`, `num` (label prefix, e.g. `"3b"`, `"8-10"`),
  `id`, `toc_en/toc_fr`, `title_en/title_fr`, `optional` (skippable when no renderer), `sub`
  (nested TOC), `raw` (renderer returns the full `<section>` — the cover), `match` (gate regexes),
  `na_en/na_fr` (default N/A copy) and `std_charts`. `GATE_SECTIONS` is the 16-section subset the
  gate enforces; `verify_report.py` imports it, so the shipped and enforced structure can't drift.
  `STD_CHARTS` is the standard chart id set `make_charts.py` should emit. **Add/rename/renumber a
  section in this file only** — every builder and the gate follow.
- **`scripts/report_framework.py` — assembly + guardrails.**
  - `render_report(renderers, ctx, lang)` walks the canonical spine. `renderers` maps a section
    `key` → `fn(ctx, lang) -> body_html`. A non-optional section whose renderer returns falsy or
    raises `NoData(reason_en, reason_fr, how_en, how_fr)` is auto-filled with a standard
    `na_block(...)` — so a section can **never silently vanish**. Optional sections are omitted
    only when no renderer is supplied.
  - `chart(cid, charts_dir, specs, lang, ...)` embeds a chart and **raises `MissingChartError`**
    if `cid` is absent from `specs.json` or its PNG is missing (replaces the old
    `if cid not in SPECS: return ""` that silently dropped charts). FR canvases are auto-suffixed
    `_fr`. `charts_row(fig1, fig2, …)` wraps the two-up chart row.
  - `cover_section(...)`, `section(spec, body, lang)`, `na_block(...)` build the branded shells;
    `assemble(en_pages, fr_pages, title=…, pdf_filename=…, css_extra=…)` does the bilingual
    assembly (FR `id` suffixing, `brand_report_css` + `FRAMEWORK_CSS` + cover CSS + lang toggle).
    Pass `fr_pages=None` for a monolingual report.
  - `write_report(html, out, gate=True, en_pages=…, fr_pages=…)` writes the file then runs
    `verify_report` as a **blocking** step — it raises `BuildGateError` on FAIL. Wire a builder
    `--no-gate` flag to `gate=False` for an explicit override only.
  - `aget(data, "a.b.c", default=None)` reads nested audit values defensively (supports integer
    list indices); a missing/stale key degrades one section to N/A instead of crashing the build.
  - `datauri(path)` for base64 image embedding; `NBSP`/`EM` constants for FR typography.
- **`scripts/build_report_template.py` — the scaffold.** Every canonical section is pre-wired to a
  renderer (`_todo` stubs raise `NoData` → ship as labelled N/A). Replace each stub with real
  content section by section, re-running until the auto-gate passes. Runs the gate at build time;
  `python work/<client>/build_report.py --no-gate` writes without gating.

Two builders under `work/` predate the framework and remain valid reference skeletons for
section *content*, but new builders must use the scaffold + framework rather than copying a full
hand-written section list.

### Component input contract — plain text vs raw HTML

Getting this wrong is invisible in Python and shows up as a literal `&amp;` in the reader's
PDF, which looks like a **character-encoding bug in the client's language**. Every one of these
gets escaped by the component, so pass **plain text** (`"Service & transactional"`):

| Escapes its input (pass PLAIN TEXT) | Takes raw HTML (pass `&amp;`, `<b>`) |
| --- | --- |
| `strategy_matrix` labels/stakes/figures | `note(...)`, `verdict(...)` |
| `kpi_card` label, `hero_kpi_band` label | `sub_html_en/fr`, `period_html_en/fr` |
| `methodology` formula/inputs/source | `section(body=…)`, section bodies |
| `creative_*_preview(alt=…)` | `creative_*_preview(caption=…)` |
| hand-built table cells via `ri.html.escape` | `<h3>` / `<p>` you write yourself |

The two creative-preview arguments differ, which is a genuine trap: `cre(name, caption)` helpers
usually pass one string to both, double-escaping the `alt`. Derive the alt instead —
`ri.html.unescape(re.sub(r"<[^>]+>", "", caption))`. `verify_report.py` fails the build on any
`&amp;amp;` / `&amp;nbsp;` / `&amp;#NN;` in the output.

### Tables

`<table class="grid">` is the styled data table (dark header band, zebra rows, hover, print
`break-inside` rules). `ir-searchable` / `ir-sortable` / `ir-exportable` add the filter box,
sorting and CSV button — they are **behaviour only** and must be combined with `grid`
(`class="grid ir-searchable ir-exportable"`), which is what the built-in components do.
`<tr class="is-me">` highlights the analysed client's row in a peer/competitor table.
`FRAMEWORK_CSS` styles bare `.page table` as a safety net so nothing ever renders raw, but the
gate still requires the explicit class. Prefer a `Signal | Value | Reading` table over any
paragraph carrying more than two or three figures.

A `<td>` holding **raw client data** (event/attribute sample values) carries `data-verbatim`,
which exempts it from the localisation lint. Sample values are quoted exactly as the SDK
stored them: turning a sampled `14.00` into `14,00` for a French report would misreport the
payload. The `audit_*` helpers set this attribute themselves.

### Custom-event properties & values (`data-csv-name="event_property_values"`)

`ri.audit_event_properties_table(AUDIT, lang)` renders one row per (event, property) plus one
row for Airship's reserved `value` field. It is **required whenever `audit_events_table` is
rendered** (delivery gate `Custom-events appendix carries value samples`), because a property
*name* never shows whether a taxonomy is usable — the values do.

Data path, from the RTDS tagging plan to the table:

| Stage | Key | What it holds |
|---|---|---|
| raw export | `values.customValues[]` | `{event, source, property, value, count}` histogram — the `value` field appears here as `property: "value"` |
| `parse_tagging_plan` | `customEvents[].properties[].samples[]` | `[{value, count}]` per property |
| `parse_tagging_plan` | `customEvents[].valueSamples[]` | `[{value, count}]` for the reserved `value` field |
| `analyze_tagging_plan` | `eventProperties[]` | **every** event; per property `{name, kind, distinctShown, samples, min, max, note}` + `valueField` + `hasValueObject` |

`kind` comes from `classify_values()`: `enum` / `number` / `amount` / `date` / `boolean` /
`identifier` / `json` / `text` / `empty`. `note` currently carries
`inconsistent casing across values` — a real segmentation bug, since `Paris` and `paris` split
into two segments. The raw row's `propSamples` text blob is deliberately ignored: all
property-level data comes from the structured `customValues` histogram.

`valueField` (from `value_field_stats`) is `None` when the SDK never populated `value`. The
renderer keeps the three states apart — `€ Amount` (with min–max and mean) / `Counter` /
`Not populated` — because "counter" and "absent" have different remediations, and collapsing
them into an em dash was hiding the gap.

`eventProperties` lists **every** tracked event, property-less ones included. It used to skip
them, which silently dropped 9 of one account's 14 events from an appendix advertised as exhaustive
and made `monetary_summary()["total_events"]` report 5 instead of 14.

## Flight Deck deep-links (link each message to the Airship dashboard)
URL shape: `https://go-admin.airship.{eu|com}/admin/flight_deck/apps/{app_key}/messages/{composer_id}`.
- **`composer_id` is `options.__ui_id`** inside the **decoded** `perpush/pushbody/{push_id}`
  (base64 → JSON → `options.__ui_id`). It is a base64url-encoded UUID and is **NOT** the
  `push_id`. Verified: push_id `960a5780-76be-11f1-9a56-0000a1ace989` → `__ui_id`
  `78amsVlZQtGBylROYqHlmA` (the real dashboard URL).
- **`app_key`** is returned directly by `perpush/detail` / `pergroup/detail` (field `app_key`)
  — no need to ask the user.
- **region**: `eu` env → `go-admin.airship.eu`, otherwise `.com`.
- **Availability**: only messages **composed in the dashboard** (BROADCAST/SEGMENTS/A-B, whose
  `perpush/pushbody` is non-empty) carry `__ui_id`. **UNICAST / Create-and-Send / API sends
  have an empty body → no `__ui_id` → no deep-link** (show the "no deep-link" pill, never a
  fabricated URL). Helpers: `composer_id_from_pushbody`, `flight_deck_url`, `flight_deck_button`.

## Page / PDF rules
The print geometry stays in the HTML whether or not a PDF is built — it costs nothing and
keeps the companion one command away.
- HTML: `@page{size:1240px 1754px;margin:0}` + `.page{width:1240px;height:1754px}`.
- PDF: Chrome `--headless=new --print-to-pdf --no-pdf-header-footer` (via `build_report.py`).
- When a PDF ships, verify its page count equals the number of `.page` divs (no overflow) and
  that every `<details>` is expanded in it.

### Screen height ≠ print height — always diagnose overflow in print emulation

A `.page` that fits on screen can bust its sheet in the PDF, so measuring in the default
(screen) media sends you chasing the wrong pixels. Measure what Chrome will actually print:

```js
await send('Emulation.setEmulatedMedia', { media: 'print' });   // BEFORE Page.navigate
// then read each visible .page's scrollHeight and compare against 1754
```

The main cause is charts. On screen the live `<canvas>` is sized by `chart(..., height=N)`;
in print that canvas is hidden and the deterministic PNG (`.ir-chart-static`) is shown instead.
The PNG is scaled to the full column width at **its own aspect ratio**, so a tall matplotlib
figure ignores the requested height entirely — on one account a `height=340` chart rendered
**1296px** tall, putting §4b at **+723px in print while measuring -70px on screen**.
`INTERACTIVE_CSS` now caps it (`--ir-chart-h` on the `<figure>`, `max-height` in the print
block), so the height argument is honoured in both media. Two consequences:

- Sizing a chart down is now a real fix for an overflowing page, not a no-op in the PDF.
- If a section still overflows after that, the content genuinely needs two pages: add a
  sub-section to `canonical_sections.py` (`num="4b", sub=True, optional=True`, and register it
  in `CLUSTER_OF`) and split the renderer. Never solve a page overflow by deleting analysis.

Long **data-appendix** tables are allowed to flow onto extra sheets — `check_pagination()`
tolerates `max(2, 15%)` extra sheets for exactly this. A *narrative* section spilling is a bug.
