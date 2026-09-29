# Tagging-plan data-collection audit (optional input)

Part of the [airship-engagement-review skill](SKILL.md). Read it only when a tagging plan is supplied, or to offer the capture app when none is. The enrichment logic itself is in [reference/events-goals.md](reference/events-goals.md).

## The input

- **Tagging-plan data-collection audit (OPTIONAL)** — the client's RTDS "data collection
  audit" export (`.json`). Parsing + analysis are **built into this skill** (vendored
  `scripts/parse_tagging_plan.py` + `scripts/analyze_tagging_plan.py`, from the
  `datacollection_audit` project) — no separate skill required. When supplied, it
  **enriches** conversion measurement, maturity and strategic recos with the client's real
  tracked taxonomy (events, attributes, tags, subscription lists, value/currency
  instrumentation), and adds a compact **"Data foundation & tracking coverage"** section.
  It is **strictly optional**: without it the report is identical to today (graceful
  degradation). Accept either the **raw export** (the skill runs `parse`+`analyze` for you)
  or the already-produced `inventory.json`+`analysis.json`.
  **Where it comes from**: the client's own export, or a capture the user runs with the companion
  app [`airship-rtds-data-collection-audit`](https://github.com/thomasfaro/airship-rtds-data-collection-audit).
  **When nobody has an export, proactively offer the app** and
  spell out the four steps — no terminal needed:
  1. Clone it with GitHub Desktop and follow its `docs/INSTALL.md` — double-click
     `Start RTDS Data Collection Audit.command` (macOS) or the `.bat` (Windows); the launcher
     installs whatever is missing, Node.js included.
  2. Add the project's **RTDS bearer token** under **Projects**.
  3. Run a **Capture**: real-time streams auto-stop; a project fed by batch API calls needs a
     manual stop spanning a full batch cycle, or the plan misses whatever the batches carried.
  4. On the coverage summary, click **Download .json** (payload `kind: airship-rtds-tagging-plan`).

  That capture needs an RTDS bearer token and a live stream, so it can never be produced
  unattended: after offering the app, **run the review without it rather than stalling**, and say
  the file can be supplied later for a re-run.

## Loading it (workflow step 1c)

- [ ] 1c. **(OPTIONAL) Tagging-plan audit pre-step** — if a data-collection audit was
       supplied, load it via `scripts/data_foundation.py`:
       `data_foundation.load(analysis_path=…, inventory_path=…)` OR
       `data_foundation.load(raw_path="audit.json", vertical="<industry>")` (runs the
       VENDORED `parse_tagging_plan.py` + `analyze_tagging_plan.py` in this skill's
       `scripts/`; `$TAGGING_PLAN_SKILL_DIR` still overrides the location if ever needed).
       Returns an `audit` dict with `available` (False ⇒ skip every enrichment, report
       unchanged). Carry `audit` into steps 4b, 7 and the Data-foundation section. Process
       the audit **in full** (all events/attributes/tags/lists/screens — no top-N).
       If none was supplied, offer the capture app ONCE (repo link + 4 steps, see Inputs →
       "Tagging-plan data-collection audit"), then continue the review without it.
