---
name: airship-engagement-review
description: >-
  Generate an exhaustive, client-ready mobile activity & engagement review from a
  project's Airship Reports API data, as a shareable PDF + PNG. Use when the user
  asks for an Airship engagement/activity review, a mobile push/in-app report, a
  CSM/AM account review, or to analyze an Airship project's sends, opens, opt-ins,
  devices, events, or campaigns. Default branding is Airship; report language
  defaults to English (offer French).
---

# Airship Engagement Review

Produce a complete, visual, sourced review of an Airship project's mobile activity
for a CSM/AM. Favor **exhaustiveness** (no page cap). Every figure carries a source
(endpoint) and, where useful, a definition. Never fabricate data; label unavailable
data and mark reconstructed visuals as "illustrative reconstruction".

## Inputs (confirm first)
- **MCP server** for the project (e.g. `user-XX PROD`). Tool: `call_airship_api`.
- **Client brand + site URL** (for brand context).
- **Period**: default trailing ~90 days, `precision=DAILY`. State exact dates.
- **Language**: default English; offer French.
- **Branding**: Airship default (see `reference.md`); client charter optional.

## Workflow
```
- [ ] 1. Brand & business context (web search, cite URLs)
- [ ] 2. Pull core data: sends, opens, optins, optouts, devices
- [ ] 3. Pull events (ALL pages) + responses/list for peak days; test pushbody
- [ ] 4. Aggregate to JSON; compute totals/averages/peaks/attribution
- [ ] 5. Generate charts (scripts/airship_charts.py)
- [ ] 6. Render creative mockups (scripts/render_mocks.py)
- [ ] 7. Build HTML report; convert to PDF+PNG (scripts/build_report.py)
- [ ] 8. Copy deliverables to Desktop; summarize
```

### 1. Brand & business context (do FIRST; drives insights)
Web-search the brand: sector, app role, audience/geos & languages, offers/loyalty,
**seasonality/key moments**, recent news, competitors. Collect source URLs.
Cross-reference data spikes with brand events. Tag every insight/reco origin:
`[Data]`, `[Brand context]`, or `[Data+Context]`. Separate measured fact from
contextual hypothesis.

### 2-3. Data collection (Airship Reports API)
Call via MCP `call_airship_api`. Endpoints, params and definitions: see
[reference.md](reference.md). Key points:
- Paginate **all** pages of `/events` (`precision=MONTHLY`).
- For top campaigns, use `responses/list` on peak-send days (iterate `next_page`).
- Test `perpush/pushbody` once; it returns 404 on some projects → reconstruct creatives.
- `devices` snapshot = authoritative opt-in rate; `optins/optouts` are daily **events**
  (include reinstalls/re-detections), not net base — state this caveat.
- Custom event `value` is a client-declared counter/weight, **not currency** — never
  show it as money.

### 4. Analysis (push deeper on events)
- Inventory: total distinct events, total volume; taxonomy by `location`
  (custom / in_app_message / in_app_pager / ua_mcrap=Message Center / ua_interactive_notification).
- Attribution per key event: `direct` / `indirect` / `unattributed` (count and value).
- Business families (browse / conversion / loyalty / store / win-back …) tied to brand.
- Attribution funnel: push-attributed (direct+indirect) product views → cart → purchase.
- Flag anomalies/spikes and any multi-market/data-hygiene signals (e.g. foreign-language
  campaign names in one project).

### 5. Charts — `scripts/airship_charts.py`
Import the styled helpers (Airship palette, k/M formatter, dated axes for time series
only, no emoji in labels). See the module docstring for available functions:
stacked daily bars, area+mean line, donut, grouped/h-bars.

### 6. Creative mockups — `scripts/render_mocks.py`
```bash
python scripts/render_mocks.py   # see module for render_push() / render_card()
```
Renders iOS lock-screen push and Message Center/in-app cards via Chrome headless with
auto-crop. Use the client's app branding inside mockups (it depicts their push), keep
the report chrome Airship-branded. Label all mockups as reconstructions when pushbody
is unavailable.

### 7. Build report — `scripts/build_report.py`
Write `report.html` using `@page{size:1240px 1754px;margin:0}` and
`.page{height:1754px}` so 1 CSS page = 1 PDF page (prevents overflow/doubled pages).
Then:
```bash
python scripts/build_report.py report.html "<Client>_Engagement_Review_90d"
# -> <name>.pdf (Chrome --print-to-pdf) and <name>.png (PyMuPDF, pages stitched)
```
Copy both to `~/Desktop/`.

## Report structure (add sections as needed — do not cap pages)
1. Cover (Airship branding) · 2. Brand & business context (sources) ·
3. Executive summary (verdict, KPIs, tags) · 4. Volume & channels / pressure ·
5. Engagement (opens) · 6. Permission & installed base · 7. Commerce/attribution funnel ·
8-9. Events deep dive (taxonomy, attribution, families, hygiene) ·
10-12. Top 5 per channel (Push / Message Center / In-app; flag absent Email/SMS) ·
13. Recommendations (tagged) · 14. Appendix: sources & definitions (glossary, endpoints).

## Quality gate (before delivery)
- [ ] Brand context researched, sourced, and used in insights/recos
- [ ] Each insight/reco tagged `[Data]` / `[Brand context]` / `[Data+Context]`
- [ ] Every visual has a source; glossary + appendix present
- [ ] No fabricated figures; unavailable data flagged; reconstructions labeled
- [ ] Top 5 for each present channel; absent channels stated
- [ ] Events: all pages paginated; location/conversion taxonomy; families
- [ ] PDF page count == #CSS pages (no overflow); Airship branding respected
- [ ] `value` never shown as currency

## Dependencies
Python: `matplotlib`, `numpy`, `pillow`, `pymupdf`. Google Chrome (headless) for
HTML→PDF and mockup rendering.

## Resources
- [reference.md](reference.md) — endpoints, params, definitions, Airship palette.
