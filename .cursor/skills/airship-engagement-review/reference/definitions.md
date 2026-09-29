# Reference — Metric definitions

Part of the [reference index](../reference.md). Read the files the index routes to your task, not the whole folder.

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
