# Option — NotebookLM source library

Not a third mode: an **option** that runs on whatever a review has already collected.
`build_source_pack.py` reads `work/<client>/` and emits a folder of markdown documents
to upload into Gemini Notebook Enterprise, so an account team can interrogate the
account's data instead of re-reading the report's conclusions.

No model in the loop, no API call, no written section, no verdict. It is a packager.

Read this only when the user asks for it — see the mode table at the top of
[SKILL.md](SKILL.md), which the option is orthogonal to. It changes nothing about mode A
or mode B.

**But ask at the start of every run whether it is wanted**, which is not the same thing as
reading this file. Building the pack is opt-in; putting the question is mandatory, because
the answer has to arrive before the first build and the trigger phrases only reach a user
who already knows the option exists. One run went the whole way to a delivered report
without the question being asked, and by the time it came up the gate had already retired
the pulls — see [The raw pulls, and who retires them](#the-raw-pulls-and-who-retires-them)
for what that costs and how to recover.

## When it is the right tool

**Use it when the question is "let me dig".** A finished report answers the questions its
sections were written for. A source pack answers the ones that come afterwards: which
programmes drift against their own median, which tracked event never fired, which levers
of the sector playbook this account does not run at all, which figures the collection's
coverage forbids concluding from.

**Do not use it to produce the review.** It carries no analysis and it is not a
deliverable for a client — the documents are internal, and the destination is a notebook
that retains and shares what it is given (see [Governance](#governance)).

## Workflow

```
python scripts/build_source_pack.py work/<client> --client "Brand" \
    [--vertical retail] [--lang fr|en] [--out DIR] [--no-deliver]
python scripts/build_source_pack.py --selftest        # offline, no work dir needed
```

Then upload the `.md` files of `~/Downloads/<Client>_Source_Pack_<date>/` as sources in
the notebook. `manifest.json` and `series_daily.csv` are **not** sources: the first
documents the pack, the second is a spreadsheet annex (CSV is not an accepted source
type — import it through Sheets if you need it).

**Nothing is mandatory beyond `data/`.** `discover()` inspects the directory and records
every absence in the manifest and in `11_perimetre_et_couverture.md`. A pack built minutes
after `collect.py` is valid and smaller; `audit.json`/`facts.json` add the consolidated
KPIs and the benchmark positioning; `inventory.json`/`analysis.json` add the tagging plan.
Nothing crashes, and nothing is silently thin.

Run it **after** `analyze.py` when you can. Not because the pack needs the audit, but
because `facts.json` is what stops a figure being derived twice with two values, and it
carries the `withheld` list — metrics the collection disqualified, which the pack then
refuses to publish as numbers.

### The raw pulls, and who retires them

There is one ordering trap, and it is silent. A passing gate makes `write_report()`
drop the raw pulls — that is the 30-day retention rule doing its job. But the pack wants
**both** halves of what that build produces: `report.html`, which only exists after the
build, and `data/*.json`, which the same build deletes. Run the pack after a normal
build and it degrades to a third of its documents, reporting the pulls as absent rather
than as deleted, because from `discover()`'s point of view there is no difference. The
symptom to recognise: `[pack] 9 inputs found, 13 absent` on an account you know was
collected in full.

The builder now stands down by itself: it keeps the pulls whenever
`work/<client>/source_pack/` exists or a `.source-pack-pending` marker is present. Touch
that marker as soon as a pack is on the deliverables list, and the trap cannot be walked
into even by a rebuild you did not plan — which is the case that broke it, since a
report gets rebuilt to fix a section long after the first pack was written.

**The marker only protects a run that knew the pack was coming**, which is why the ask
belongs in Inputs rather than here. When it was never touched, the survivors are the
`purge_work.KEEP_ANYWHERE` set — `collect_manifest.json`, `sends.json`, `pushbodies.json`,
`reconcile.json` — and everything the tier-3 and tier-4 documents are built from is gone:
`responses.json`, `activity.json`, `perpush_detail.json`, `decoded.json`, `events.json`,
`devices.json` and the opens/optins/optouts series. Recovery, in order: re-run `collect.py`
over the same window (it skips the survivors), rebuild the report against the **frozen**
`audit.json` — do **not** re-run `analyze.py`, or the pack and the report will disagree
about numbers the report has already published — then pack. The window is closed and
before the watermark, so the re-pull returns the same rows; the cost is wall-clock and API
calls, which is minutes on a `dashboard` account and hours on a firehose.

`--keep-raw` on the builder still works and still means the same thing.

Retirement is then an explicit last step, `build_source_pack.py --retire-raw`, because a
pack is rebuilt more often than a report: after the report markdown is added to it,
after a `--refresh`, to produce a second language. Two builds of the same pack in one
run is normal. `purge_work.py --apply` remains the backstop.

## What is in the pack — four tiers

Around 25 documents at most, against a 300-source ceiling. **The numbering carries the
tier** so it is visible in the notebook's source list, and every file opens with a
`provenance:` block naming its origin file or endpoint, the window, and the method.

The success criterion is **the notebook's autonomy**, and that is a content requirement
rather than a packaging one. A pack of figures alone produces a notebook that invents
definitions: it adds opens to direct opens, compares a device snapshot to period opt-ins,
reads a benchmark as a point instead of a band, and takes a custom event's `value` for an
amount in euros.

### Tier 1 — the semantics (client-agnostic, identical from one account to the next)

| File | What it carries |
|---|---|
| `00_README_pack.md` | Map of the pack, reading order, a routing table filtered to what actually shipped, what is **not** in the pack, the scrub manifest, opening questions |
| `01_endpoints_reports_api.md` | **Verbatim** from `reference.md`: what each endpoint returns, what it does not, and its known traps |
| `02_definitions_et_perimetre.md` | **Verbatim**: definitions, channels, the snapshot/period split, verification & confidence |
| `03_fiches_metriques.md` | **Generated** from `build_facts.KPI_SPECS`: one fiche per metric — definition, source endpoint, exact denominator, snapshot or period, how it gets misread, applicable benchmark or none |
| `04_limites_et_inferences_interdites.md` | **Generated**: what this account's data does not allow you to conclude, written as prohibitions |
| `05_comment_lire_les_benchmarks.md` | **Verbatim**: the percentile legend and the "`sends_per_user_month` is per MONTH" warning |
| `06_referentiels_metier.md` | **Verbatim and whole**: event catalog, campaign playbook, data-collection practices, Airship Goals — **every** vertical, not only the account's |

The sector books ship **entire**. An earlier version filtered them to the account's
vertical on a retrieval-dilution argument, which does not survive contact with the target:
the context window swallows the whole corpus, and the filtering removed the material
needed to answer *"what would a travel app track that we do not"* — a question worth
asking precisely because the account is not a travel app. Same reasoning for
`27_benchmarks_secteur.md`, which keeps the account's vertical and the cross-vertical
baseline and pushes the other verticals into `96_annexe_benchmarks_tous_verticaux.md`.

### Tier 2 — the account's context

`10_profil_du_compte.md` (window, resolved vertical, account shape and **what that shape
implies for reading every figure**, active channels, brand research when present) and
`11_perimetre_et_couverture.md` (stages, pages, rows, API calls, measured coverage, the
consolidation watermark, what could not be collected and why, absent inputs).

### Tier 3 — the account's analysis, one document per theme

`20_audience_et_permission` · `21_volume_et_pression` · `22_inventaire_campagnes` ·
`23_programmes_automatises` · `24_creatives_decodees` · `25_evenements_custom` ·
`26_plan_de_taggage` *(conditional)* · `27_benchmarks_secteur` ·
`28_kpis_consolides` *(conditional)*.

Each carries an overview, the canonical metrics for its theme, and the notes that qualify
them. On a dense account these stay small — 170 to 850 words — because the bulk moves to
tier 4.

### Outside the tiers — `99`, the delivered report

`99_rapport_engagement.md` is `report.html` converted to markdown by
`report_markdown.py`, and it is **the only source in the pack that concludes**. It ships
because an account team discussing a recommendation needs the recommendation in the
conversation, and the alternative — pasting the report in by hand — produces an
unscrubbed, unnumbered source nobody can deselect.

Everything else about the pack's design is preserved by making it a *separate* source:
`99` sorts last, reads as "not part of the numbered library", and comes off in one
click. `00_README_pack.md` says so, twice, and says why: a notebook given the answers
recites them instead of rebuilding them from the data, which is the whole point of the
pack. Deselect it for any analytical question.

The conversion keeps two things a generic HTML-to-text pass drops, and they are the
reason this is not `pandoc`. **The method block behind every KPI** — formula, source,
confidence — lives in a `<template>` the browser only reveals on click, and a figure
that arrives without it is exactly what the autonomy gate exists to refuse. **The chart
data** is re-emitted as the table it was drawn from, capped at `CHART_ROW_CAP` rows with
a pointer to the daily annex; left as an image it would leave a caption pointing at a
curve that is not there. Long tables are segmented on `ROWS_PER_SEGMENT`, imported from
`source_pack_docs` rather than duplicated, so the two cannot drift.

It goes through `Pack.add` like every other document, which is what scrubs it. That is
not a formality: the first account this ran on carried three real consumer email
addresses into the delivered report through the tagging plan's `sampleValues`, and the
pack's mask is what stopped them reaching the notebook. The self-test pins it, with an
address planted in the fixture's appendix rather than in a push body.

### Tier 4 — the `9x` annexes, exhaustive inventories and nothing else

`90_annexe_inventaire_campagnes` · `91_annexe_creatives` · `92_annexe_evenements` ·
`93_annexe_plan_de_taggage` · `94_annexe_series_quotidiennes` · `95_annexe_programmes` ·
`96_annexe_benchmarks_tous_verticaux` · `97_annexe_permission_quotidienne`, each emitted
only once its inventory passes
`ANNEX_THRESHOLD` (40 rows). Below that it stays inline, where a separate source would
cost a click and buy nothing.

**The split exists because an annex is a separate notebook source, and can therefore be
deselected.** That is the only real control the reader has over what competes for the
model's attention:

| Question | Selection |
|---|---|
| Strategy — which levers are not run, where is the volume | tiers 1-3, **90+ and 99 off** |
| Counting or debugging — top 10 events by volume, which attributes are mistyped | everything, **90+ on** |
| Arguing with a recommendation, preparing a readout | tiers 1-3 plus **99** |
| Audio Overview / podcast | tiers 1-3, **90+ and 99 off** — raw nomenclature is what makes the voices read event keys aloud for ten minutes |

`00_README_pack.md` states this in the pack itself, listing the annexes that actually
shipped. Nothing is dropped in either selection: the full inventory is always in the
folder, the reader chooses when it is in the conversation.

## Table shape

Notebook Enterprise accepts `.md`, `.txt`, `.pdf`, `.docx`, `.pptx`, `.xlsx`, at 300
sources per notebook and 500,000 words or 200 MB per source. **It reads long markdown
tables well and has the context window to hold them**, so a table stays a table:
`data_table` cuts it into 50-row segments, each preceded by its own header and by a
`Lignes 51–100 sur 168` caption so a segment read in isolation still says how much it is
not showing. `verify` fails a generated table segment that runs past its header, which
catches an emitter that built its markdown by hand.

An earlier version reshaped any table over 30 rows into one self-describing bullet per
record, on the assumption that the target was a small-chunk retrieval engine. It is not,
and the bullet form both tripled the token count and destroyed the tabular structure that
makes *"the ten events with the most volume"* an easy question. The annex split above is
what replaced it: same problem — bulk crowding out reasoning — solved by letting the
reader deselect the bulk rather than by degrading it.

The vendored tier-1 books are exempt from all of this: they ship as their authors wrote
them.

## Verbatim rather than rewritten

The whole methodological corpus is ~30,000 words against a 500,000-word ceiling per
source, so there is no budget reason to paraphrase it and two reasons not to: a paraphrase
drifts the first time the skill is updated, and `check_no_client_names.py` already
guarantees this material names no client.

Extraction works from an **allow-list of H2 headings**, not by whole-file copy —
`reference.md` also carries build machinery (MCP setup, brand colours, the i18n contract,
the PDF page rules) which teaches a notebook nothing and dilutes retrieval.

**Extraction fails loudly.** A renamed H2 raises `MissingSectionError` instead of shipping
an amputated referential, the same rule as `MissingChartError` in
`report_framework.chart()`. A context document that disappears in silence is worse than an
error, because the notebook keeps answering confidently on an incomplete base. A *new*
`reference.md` section that is on neither the allow-list nor the exclusion list is
reported as a generation note rather than a failure.

## Language

The tier-1 corpus is vendored in its source language, **English**, and the two generated
tier-1 documents follow it: half-translating a definitions corpus is the one outcome worse
than having it in a single language, and the technical terms (`direct open`, `alerting
sends`, `value-bearing`) are API labels everywhere anyway. The account's own documents
(tiers 2 and 3) follow `--lang`, `fr` by default. A bilingual pack does not bother the
notebook, which answers in the language of the question.

`--lang en` has to mean an English document, not English paragraphs under French headings.
Prose is localised inline; the ~170 structural labels — section titles, column headers,
key/value row labels — go through `source_pack_docs.L()`, which records anything it cannot
translate. The self-test fails on a non-empty `LABEL_MISSES`, so a heading added without an
English form is caught rather than shipped in French. Field names discovered in the data
(`android`, `custom_name`) are deliberately left alone: translating a column name would
break the link to the field it came from. **Source filenames follow `--lang` too**:
an English pack emits `20_audience_and_permission.md`, an equivalent French pack emits
`20_audience_et_permission.md`. The numeric prefixes stay stable because they carry the
tier; `Pack.source_name()` is the single mapping used by the writer, manifest, verifier
and README routing table so translated filenames cannot leave stale internal links.

## The blocking gate

`verify()` runs before delivery and refuses to ship:

- an empty file, one over 500,000 words, or one over 200 MB;
- a residual email or phone pattern in any emitted file;
- an individual identifier field (`named_user`, `channel_id`, `device_token`…) in a
  generated document;
- a generated table segment longer than 50 rows;
- a manifest that disagrees with what is on disk;
- an incomplete tier 1 — the seven documents must be there;
- a table segment in the converted report longer than the pack's own segment size;
- **a metric published in tier 3 with no fiche in `03_fiches_metriques.md`.** This is the
  autonomy check: a figure without its definition in the same pack is a figure the
  notebook will read wrong. `KPI_SPECS` gaining a key with no fiche is a hard failure.

`--selftest` builds two complete packs offline, from a fabricated account and from an
almost-empty one, and pins that an address embedded in a push body does not reach the
output. It also pins the annex split in both directions — a 60-row series must leave its
analysis document and leave a pointer behind, a 3-row inventory must stay inline — because
tables silently coming back inline would still build, still be correct, and quietly remove
the deselect affordance. It runs in `run_selftests.py`.

## Governance

**Named client, aggregates, creatives and tagging-plan sample values at full fidelity.**
The pack is for a **private internal notebook**. Sample values (including personal data)
are load-bearing for taxonomy analysis and ship unredacted by default. `--no-samples`
restores the old behaviour: drop `sampleValues` / `valueSamples` and mask emails and
phones in free text.

Individual identifier *fields* (`named_user`, `channel_id`, `device_token`) are still
not selected as rows of their own. When samples are on, a sample cell may contain those
values because that is the data.

The destination is still a persistent, shareable enterprise notebook: keep it in the
private internal workspace, not a client-facing one.
