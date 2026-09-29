# Reference — Verification & confidence, value measurability, scene instrumentation, coverage, proof points

Part of the [reference index](../reference.md). Read the files the index routes to your task, not the whole folder.

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
