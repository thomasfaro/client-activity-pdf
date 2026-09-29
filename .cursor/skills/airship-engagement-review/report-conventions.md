# Report conventions — KPIs, tables, escaping, language, charts

Part of the [airship-engagement-review skill](SKILL.md). Read it before writing or fixing any section; the gate enforces every rule here.

## Conventions

- **Prior-period comparison (REQUIRED on EVERY KPI card — gate-enforced)**: also pull
  `sends`/`opens`/`optins`/`optouts` over the immediately-preceding equal-length window so
  **every** headline KPI (hero tile AND `kpi_card`) shows a **period-over-period delta**, not
  just the exec-summary usage band. `hero_kpi_band(...)` and `kpi_card(...)` both take
  `delta` (fraction vs prior) + `delta_good` (`True`=up is good, `False`=up is bad e.g.
  opt-outs, `None`=neutral direction) and render a small coloured up/down/flat pill (shown on
  the card, printed in the PDF — it's content, not chrome). True year-over-year ("N-1") needs
  an aligned window a year back — only do it if the user asks and volume allows; otherwise
  label deltas "vs prior period". When a metric **genuinely can't be windowed** — a `/devices`
  point-in-time snapshot (opt-in rates, installed base) or an aggregate/un-windowable event
  series (VOD views, in-app counts, email rates, per-broadcast open rates) — pass
  `no_baseline=True` for a muted **"no prior-period baseline"** note rather than a broken/empty
  delta or a misleading `0`. The gate (`verify_report.py`) checks that every KPI tile in the
  exec summary and §4 volume / §5 engagement / §6 permission / §8b in-app / §14 email carries
  one of these two states. Wire the real numbers from `audit.json` (`usage.prior` /
  `usage.deltas`) — never invent a prior value.
- **Every computed KPI must explain itself (gated).** A number the reader cannot trace is a
  number they cannot defend in front of their own management. Give **every**
  `hero_kpi_band(...)` item and `kpi_card(...)` both `formula=` (the calculation in words) and
  `source=` (the **exact Reports API endpoint**, e.g. `GET /api/reports/devices`), plus
  `inputs=` (the numerator/denominator actually used), and `sample=` / `notes=` whenever the
  figure is sampled, extrapolated or unstable. They render as an ⓘ **"how it's computed"** modal.
  `kpi_card` takes `formula` as a named argument so it is safe by construction; **`hero_kpi_band`
  makes methodology optional and silently renders no ⓘ when it is missing** — on a telecom
  account that shipped **90 hero tiles with zero methodology** before the gate existed. Define shared tiles
  (sends, pressure, open rates) **once as a factory function** and reuse them across sections so
  a value and its stated method can never diverge. Gate: *"KPI methodology on every computed
  KPI"* + *"No orphan methodology buttons"*.
- **All tabular data goes in a styled table (gated).** A bare `<table>` has no header band, no
  borders and no zebra — this is the single most common "the data is unreadable" complaint, and
  26 of 38 tables shipped that way on a telecom account. Use **`<table class="grid">`** (the framework
  also ships a bare-`<table>` fallback so nothing ever renders raw, but the gate still demands
  the explicit class). Note `ir-searchable` / `ir-sortable` / `ir-exportable` are **behaviour
  hooks, not styling** — always pair them with `grid`. Equally: **do not bury figures in prose.**
  When a paragraph carries more than two or three numbers, turn it into a
  `Signal | Value | Reading` table — it reads faster and survives translation. Highlight the
  client's own row in a peer/competitor table with `<tr class="is-me">`.
- **Escaping contract — plain text vs raw HTML.** Most components take **PLAIN TEXT** and escape
  it themselves (`strategy_matrix`, `kpi_card`, `hero_kpi_band` labels, table cell helpers, the
  `alt=` of creative helpers): pass `"Service & transactional"`. A few take **RAW HTML**
  (`note()`, `verdict()`, `sub_html_*`, `period_html_*`, `section(body=…)`, creative `caption=`):
  those want `&amp;`, `&middot;`, `<b>`. Feeding a pre-escaped string to a text-taking helper
  double-escapes it and the reader sees a literal `&amp;` — which reads as a **French encoding
  bug**. Gate: *"No double-escaped HTML entities"*.
- **Email message/group IDs (optional)** — a list of email `push_id`s / `group_id`s. When
  supplied, they unlock a **real per-message email table** (`perpush/detail` / `pergroup/detail`);
  when absent, email is reported as an **aggregate funnel** with the per-message limitation
  stated (standalone email is NOT enumerable from the Reports API — see `reference.md`).
- **Language — ONE language per deliverable**: every analysis is language-aware. **Confirm the
  report language up front** (default **English**; **French** fully supported; detect a hint
  from the request — e.g. a French prompt — and offer to match it). Whatever is chosen applies
  to **the ENTIRE deliverable**, consistently: section titles, prose, KPI labels, verdicts,
  tags/origin labels, methodology modals, the interactive chrome (sidebar, Download-PDF,
  Expand/Collapse, search box, CSV button, KPI modal), **and number/date formatting**. Thread
  it through: pass `lang=` to `report_interactive.interactive_head(...)` and to the localisable
  components (`hero_kpi_band`, `strategy_matrix`, `pillar_coverage`, `automation_mix`,
  `kpi_card`, `methodology`), and format every figure via the locale helpers `fmt_int` /
  `fmt_pct` / `fmt_delta` / `fmt_num` (EN `1,234` `12.3%` · FR `1 234` `12,3%`). Pull
  playbook/pillar/lever labels from the `*_fr` fields when `lang="fr"`. Add a new language by
  extending `_UI_STRINGS` in `report_interactive.py`. Never ship a report that mixes languages.
  **The report ships the ONE language its reader reads** — set `LANG` in the builder and pass it
  to `fw.assemble(pages, None, lang=LANG)`. Being asked for the review in French sets `LANG="fr"`
  (translate the `<title>` with it); it is not a reason to ship two columns.
  **A bilingual build is opt-in (`--bilingual`) and costs roughly double.** Every section is
  written twice, and measured across thirteen delivered accounts the localisation checks were the
  largest single source of gate failures (10 of 28) — see *What the gate actually rejects* in
  [orchestration.md](orchestration.md). Ship both only when both columns are genuinely read; the
  primary stays the one that opens on load and the one the PDF prints.
- **Chart labels are ENGLISH in every render — ONE chart set, no per-language chart build.**
  This is the single deliberate exception to "never mix languages", and it exists because
  chart chrome is a handful of technical words (`Sends`, `Open rate %`, `Opt-out rate %`,
  `Direct` / `Indirect` / `Unattributed`, `Injected` / `Delivered`) that a French reader reads
  without friction, while maintaining two chart sets doubles the authoring cost and is exactly
  where language bugs appear. So: `make_charts.py` emits **one** `charts/` directory and **one**
  `specs.json`; never a `charts/en/` + `specs.en.json` pair, and never a language loop. Do NOT
  pass French strings to the `spec_*` label arguments — leave their English defaults alone.
  Everything *around* the chart is localised as usual: the `alt`/caption you pass to
  `chart(...)`, the surrounding prose, table headers, KPI labels, the CSV button. Axis **values**
  that come from data (event names, CTA labels, tag names) stay verbatim in whatever language
  the client's own data uses — that is data, not chrome.
