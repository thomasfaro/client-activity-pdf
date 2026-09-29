---
name: airship-engagement-review
description: >-
  Client-ready mobile activity & engagement review of an Airship project, as an
  interactive self-contained HTML report (optional PDF companion). Covers sends, opens,
  opt-ins, devices, events, campaigns, conversion KPIs and marketing pressure vs
  benchmarks, and deep-links every analysed message to Flight Deck. Optionally ingests
  the client's RTDS data-collection audit / tagging-plan .json (parsing and analysis are
  built in) to enrich conversion, maturity and recommendations with the real tracked
  taxonomy. Use for an Airship engagement or activity review, a mobile push/in-app
  report, a CSM/AM account review, or to analyse a tagging plan / plan de taggage /
  data-collection audit .json.
  ALSO provides a lighter mode B, the "Goals review": a fully offline conversion analysis
  from the tagging plan plus brand research, with no Reports API call, saying which
  Airship Goals to configure today and which funnel stages cannot be measured at all.
  Trigger mode B on "revue goals", "goals review", "analyse light", "quels goals
  configurer", "what should we configure as goals", "conversion review of the tagging
  plan".
  ALSO provides an option orthogonal to both modes, the NotebookLM source library: a
  deterministic packager that turns an account's collected data into markdown sources to
  upload into Gemini Notebook Enterprise and dig into the data there. Trigger it on
  "bibliothèque de sources", "source pack", "notebook lm", "notebooklm", "sources pour un
  notebook", "creuser la donnée du compte".
icon: book-open
color: blue
---

# Airship Engagement Review

> **Run it through the orchestrator when the SDK is available.** A full review runs for
> hours; in a single chat the instructions drop out of context as the window compacts, and
> the first symptom is a thin section written from memory. `scripts/run_review.py` holds
> the waves, the loops and the checks in code and hands each agent one scoped task
> (needs `pip install cursor-sdk` and `CURSOR_API_KEY`; `--check-sdk` verifies both):
>
> ```bash
> python .cursor/skills/airship-engagement-review/scripts/run_review.py \
>   --project "<MCP project>" --client <client> --start <YYYY-MM-DD> --end <YYYY-MM-DD> \
>   --lang en --orchestration-external unknown --source-pack no
> ```
>
> In chat, your job is to collect the inputs below, launch it, and arbitrate at its
> checkpoints (after the pre-flight and after the pilots). The manual path — the same waves,
> prompts and checks, run by hand — is in [workflow.md](workflow.md) and
> [orchestration.md](orchestration.md). It stays the reference until the
> [before/after protocol](orchestration.md#before--after--when-the-script-becomes-the-default)
> has passed on a few delivered accounts.

## Two modes — pick one before you start

| | **Mode A — Full engagement review** (default) | **Mode B — Goals review** (light) |
|---|---|---|
| Question it answers | How is this client using Airship, and how well is it working? | What should this client configure as Goals, and what can it not measure at all? |
| Inputs | Reports API (MCP) + optional tagging-plan JSON | Tagging-plan JSON + web research **only** |
| API calls | Many | **None** |
| Output | `report.html` (+ PDF companion on `--pdf`) | `goals_review.html`, **no PDF** |
| Delivered to | `~/Downloads/<Client>_Engagement_Review_<date>.html` | `~/Downloads/<Client>_Goals_Review_<date>.html` |
| Language | **One** language, EN or FR (ask the user); bilingual is opt-in | **English only** — never ask |
| Sections | 25 available, 14 mandatory | 12 |
| Gate | `verify_report.py` | `verify_report.py --profile goals` |
| Working dir | `work/<client>/` | `work/<client>/goals/` |
| Specification | this file + [workflow.md](workflow.md) | [mode-b.md](mode-b.md) |

Mode A is the default. Choose mode B **only on explicit intent** ("revue goals", "goals
review", "analyse light", "quels goals configurer"); an engagement review that mentions goals
in passing is still mode A.

**NotebookLM source library** — orthogonal to both modes: `build_source_pack.py` turns what a
run collected into markdown sources for Gemini Notebook Enterprise. Opt-in, but **the
question must be asked before the first build**, because a passing gate retires the raw pulls
the pack needs. See [source-pack.md](source-pack.md).

Produce a complete, visual, sourced review of an Airship project's mobile activity for a
CSM/AM. Every figure carries a source (endpoint) and, where useful, a definition. Never
fabricate data; label unavailable data and mark reconstructed visuals as "illustrative
reconstruction".

## Non-negotiable rules

- **The DATA must be exhaustive; the PROSE must be sufficient.** Collect and compute without
  shortcuts — full pagination, every `pushbody` needed, the tagging plan in full, any
  technical limit handled by loss-less aggregation with a quantified coverage. Then write only
  what changes what the reader would do. A section is done when it states what the data
  shows, reaches a verdict and carries the visual that makes it checkable. Full contract:
  [workflow.md](workflow.md#data-exhaustiveness-contract-zero-shortcut).
- **Reports API only** (`/api/reports/*`, OAuth scope `rpt`). Never the Content, Pipelines,
  Schedules or Experiments APIs. Setup: [setup-mcp.md](setup-mcp.md).
- **The mandatory structure is mandatory.** Every `gate_required` section in
  `scripts/canonical_sections.py` ships, marked N/A with its reason when the data is absent.
  Optional sections ship only when they have something account-specific to say.
- **Build on the framework.** Start from `scripts/build_report_template.py`; charts and
  creatives are mandatory; the gate runs at build time. Conventions every section must follow
  (deltas, `formula=`, `grid` tables, escaping, language): [report-conventions.md](report-conventions.md).
- **Client data never enters the repository.** `work/` is git-ignored and the report is
  delivered to `~/Downloads`. When an account teaches a lesson worth keeping, record the
  mechanism ("on a telecom account"), never the client name or its numbers. Retention and
  provenance: [data-handling.md](data-handling.md).
- **Collection does not run in the cloud.** The per-client MCP credentials are local.

## Inputs (confirm first — the orchestrator refuses to start without them)

- **MCP project** (e.g. `user-XX PROD`) with an `rpt`-only token → `--project`.
- **Client brand + site URL** → `--client`, used by brand research.
- **Window** — default trailing 30 days, `precision=DAILY`, exact dates stated → `--start/--end`.
- **Language** — ONE per deliverable, EN default, FR supported; offer to match the request →
  `--lang`. Bilingual only on explicit request (`--bilingual`).
- **External orchestration** — "Is any of this traffic triggered from outside Airship (SFMC
  connector, another orchestrator, an in-house engine), and which programmes?" →
  `--orchestration-external` (`none` / `unknown` / a description). Default `unknown`, never
  `none`: it decides whether "no segmentation" is a finding or an artefact.
- **Account team brief** (optional) → `--context <brief.md>`. It decides between the two
  intents a review serves. A **global** review (no brief, or context only) reads the whole
  account at even depth. A **focused** review — "a broadcaster's app during a tournament",
  "why so many opt-ins but so few reachable devices" — asks numbered questions (`Q1: …`); the report then answers each in
  §3a, leads with the sections that answer them and condenses the rest (never drops them).
  Start from [brief-template.md](brief-template.md), and define every figure the brief
  quotes: an undefined count is the commonest reason a focused question stays unanswerable.
- **NotebookLM source pack** — ask, yes or no → `--source-pack`.
- **Tagging-plan audit** (optional) → `--tagging-plan`. If none exists, offer the capture
  app once, then run without it: [tagging-plan.md](tagging-plan.md).
- **Email message/group IDs** (optional) → unlock a per-message email table.
- **PDF companion** (optional) → `--pdf`.

## Workflow (mode A)

One line per step; detail in [workflow.md](workflow.md), metric semantics in
[analysis-spec.md](analysis-spec.md), endpoint semantics via the [reference index](reference.md).

1. **Brand & business context** — one `airship-brand-research` agent, fixed budget, fixed
   `brand.json` schema, ends on `check_brand.py`. Launched first, in the background. Confirm
   the industry and resolve it with `resolve_vertical.resolve()`.
1b. **Probe the push shape** — `push_firehose.py probe` (~8 s) decides the collection strategy.
1c. **Tagging-plan audit** (optional) — `data_foundation.load(...)`.
2. **Collect** — `collect.py`, never a hand-written collector; cite `collect_manifest.json`.
2b. **Channel detection** — `channel_activity.channel_summary(...)` from `/sends`.
3. **Events + activity log + responses/list**, all pages, de-duplicated on `push_uuid`.
3b–3c. **Merge push inventories; reconcile the two send counters.**
4. **Classify** (one-shot vs automated) → **4a** canonical inventory → **4c** client categories
   (`campaign_categories.py`: scheme inferred, readings tested and scored; only Medium-or-better
   ones reclassify) → **4b** purpose / pillar through `campaign_categories.enrich(...)`.
5. **Experiments** from `push_type == A_B` only.
6. **Decode creatives once** — one `push_id → body` cache reused everywhere.
7. **Custom events & conversion KPIs** — `event_analysis.analyze(...)`, behavioural events only.
8. **Unicast categories** from perpush bodies.
9. **Aggregate** → `audit.json` (+ `analysis_brief.md`), then `verify_audit.py` and
   `build_facts.py --verify`, then **freeze**.
10. **Charts** — `airship_charts.py`, PNG + Chart.js spec from the same data.
11. **Creatives** — 4–8 curated previews, each with its objective selection reason.
12. **Flight Deck deep-links** for every dashboard-composed message.
13. **Build** from the canonical scaffold; the gate runs inside `write_report`.
14. **Deliver** to `~/Downloads`; read it before it reaches a client.
15. **Verify** — `verify_report.py` must pass; go through [quality-gate.md](quality-gate.md).

## Writing doctrine — three failures a delivered review came back with

Applies to **everything the client reads**, including the executive summary this
orchestrator writes itself. `.cursor/agents/airship-section.md` carries the same three
rules for the section writers; keep the two in step.

**Plain sentences, one idea each.** Frontier-model prose fails in a specific direction: it
compresses. It stacks five ratios in a paragraph, opens on an abstraction, and joins clauses
with an elliptical connective that assumes the reader already holds the argument. Every
sentence is defensible and the paragraph still has to be read twice. Cap a paragraph at two
or three figures, name the subject before the verb, and when it gets dense cut a sentence
rather than tighten it. Length is the second problem, not the first: the review has grown
long enough that a reader skims, and skimming a correct report loses the argument as surely
as writing a wrong one.

**Comparability is a claim, and it needs the same scrutiny as a number.** Two figures each
computed against its own correct denominator can still be uncomparable, and that is the
harder error to catch because the arithmetic is clean. Web against app opt-in shipped this
way: a browser prompt and an iOS system prompt are different asks on different surfaces with
different costs to reverse, so the gap measures the prompts and not the audiences. Before
putting two numbers on the same scale, ask what would have to be true for the comparison to
mean anything. If the answer is "the mechanics match", check that it does; if it does not,
report each on its own scale and make the incomparability the point.

**Calibrate every capability verdict to what Airship can see.** See `orchestration_external`
under Inputs. Absence in the Reports API is evidence about the API, not about the client's
practice, and an audit that misses context states its conclusions too strongly precisely
where it is least entitled to. Name the fact that would overturn each verdict. This is not
hedging for its own sake — a conclusion that survives the client supplying missing context
is stronger than one that collapses on the first read.

## Model routing — never downgrade the prose

Declared in `.cursor/agents/*.md`, one file per role, each pinning its model; the
orchestrator reads them from there. Full rationale: [orchestration.md](orchestration.md#model-requirement--route-by-task-never-downgrade-the-prose).

| Task | Agent | Model class |
|---|---|---|
| Orchestration, analysis, consultative sections, coherence pass | (main / frontier) | frontier — same as `airship-section` |
| Reading the client's category scheme (wave 2a, `prompts/categories.md`) | (main / frontier) | frontier — a wrong reading reclassifies campaigns report-wide |
| **Any section prose, any verdict, any recommendation** | `airship-section` | frontier |
| Brand & business research (background) | `airship-brand-research` | web-capable reasoning |
| Collection, charts, creatives, PDF (manual path only) | `airship-shell` | fast |
| Data appendices | `airship-appendix` | fast |
| Gate-fix loop (mechanical ✗ only) | `airship-gate-fix` | fast |

The exact id is the agent file's `model:` line — deliberately not repeated here. To try
another model, `run_review.py --model role=spec` for one run; the agent file changes only
after the before/after protocol passes.

Never route a section that carries interpretation to a fast model (`guard_model.py` denies
it); never let a fast model have the last word; state the model you actually got (`run.md`).

## Orchestration in one paragraph

Collect and analyse sequentially; check the audit is plausible; **freeze** `audit.json`,
`facts.json`, `analysis_brief.md`, `specs.json`, `charts/` and `creatives/`; write three pilot
sections and gate them; write the factual sections in parallel (two or three at a time), each
returning a verdict record into `verdicts.json`; check the verdicts for contradictions; write
the consultative sections last, in one context, with `exec_summary` at the very end; build and
gate; finish with a prose-only coherence pass. Playbook, prompts and failure modes:
[orchestration.md](orchestration.md); prompts themselves: `scripts/prompts/`.

## When to read what

| You are about to… | Read |
|---|---|
| set up a new client project | [setup-mcp.md](setup-mcp.md) |
| run a workflow step by hand | [workflow.md](workflow.md) |
| run the analysis (step 9) | [analysis-spec.md](analysis-spec.md) |
| look up an endpoint, a definition, a trap | [reference.md](reference.md) → the one or two files it routes you to |
| write or fix a section | [report-structure.md](report-structure.md) + [report-conventions.md](report-conventions.md) |
| use a tagging plan, or offer the capture app | [tagging-plan.md](tagging-plan.md) |
| run waves, brief subagents, read `run.md` | [orchestration.md](orchestration.md) |
| deliver | [quality-gate.md](quality-gate.md) |
| decide on retention, provenance, or change the skill | [data-handling.md](data-handling.md) |
| find what a script does | [scripts-catalog.md](scripts-catalog.md) |
| position against peers | [benchmarks.md](benchmarks.md) |
| run mode B | [mode-b.md](mode-b.md) |
| build the NotebookLM pack | [source-pack.md](source-pack.md) |
