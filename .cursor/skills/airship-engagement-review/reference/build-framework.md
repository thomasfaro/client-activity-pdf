# Reference — Branding, i18n, deliverable, framework scaffold, page/PDF rules (waves 1-2 and 6 only)

Part of the [reference index](../reference.md). Read the files the index routes to your task, not the whole folder.

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
  With `unit="%"` a gauge takes percentages (54.7), never fractions (0.547): four values in
  [0, 1] raise `ValueError` (`sub_one_percent=True` for rates genuinely under 1 %).
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
