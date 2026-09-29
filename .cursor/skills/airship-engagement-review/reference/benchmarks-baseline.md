# Reference — Industry benchmarks and the internal baseline

Part of the [reference index](../reference.md). Read the files the index routes to your task, not the whole folder.

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
