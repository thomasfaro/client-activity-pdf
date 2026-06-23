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

## Prerequisite — configure the client project as an MCP server in Cursor

Each Airship client project needs its **own MCP entry** in Cursor so the Agent can call
`call_airship_api` against that project's data. Credentials stay **local only**
(`~/.cursor/mcp.json` or Cursor Settings → MCP) — never commit them to this repo.

### 1. Create OAuth credentials in Airship (per project)

In the Airship dashboard for the target project:

1. Project dropdown → **Settings** → **Project settings** → **OAuth**.
2. Create (or edit) an OAuth client. Enable **Allow Basic Auth** so a Client Secret is
   generated.
3. Enable scopes — **at minimum for this skill**: `rpt` + `tpl` (see next section).
   Recommended extras: `pln`, `sch`, and experiment scope if available.
4. Note three values from the dashboard:
   - **App Key** (`AIRSHIP_APP_KEY`) — also under Project settings → **General**.
   - **Client ID** (`AIRSHIP_CLIENT_ID`)
   - **Client Secret** (`AIRSHIP_CLIENT_SECRET`)
5. Set **region**: `eu` for `go.airship.eu` / `api.asnapieu.com`, `us` otherwise.

### 2. Add the MCP server in Cursor

**UI:** Cursor Settings (`Cmd+Shift+J`) → **MCP** → **Add new MCP server** (or edit
`~/.cursor/mcp.json` directly).

Add one block **per client project**. Use a clear name — this is what you pass to the
Agent (e.g. *"generate a review for **Carrefour PROD**"*). Cursor exposes it to the
Agent as `user-<name>` (e.g. `user-Carrefour PROD`).

```json
{
  "mcpServers": {
    "Carrefour PROD": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/agent-tools",
        "airship-mcp"
      ],
      "env": {
        "AIRSHIP_APP_KEY": "<app_key>",
        "AIRSHIP_CLIENT_ID": "<oauth_client_id>",
        "AIRSHIP_CLIENT_SECRET": "<oauth_client_secret>",
        "AIRSHIP_REGION": "eu"
      }
    }
  }
}
```

- **`/path/to/agent-tools`**: directory containing the `airship-mcp` package (clone or
  install the Airship MCP / agent-tools repo; requires `uv` on PATH).
- Duplicate the block for each client (`GMF PROD`, `M6 PROD`, …) with **that project's**
  app key and OAuth credentials.
- Optional env vars: `AIRSHIP_RTDS_BEARER_TOKEN` (RTDS), `AIRSHIP_API_URL` (staging).

After saving: **reload Cursor** (Command Palette → **Developer: Reload Window**) or use
the **Restart** button on the MCP server row in Settings.

### 3. Verify connectivity (before running a review)

In Agent chat, or by probing from the skill workflow:

```
GET /api/reports/devices   → 200 + ios/android opted_in counts (needs scope rpt)
GET /api/content/templates → 200 or empty list (needs scope tpl)
```

If **401 `Expired token`**: restart / re-authenticate the MCP server in Cursor Settings,
then retry (OAuth tokens are short-lived; the MCP client refreshes on restart).

If **401 `Missing required scope`**: add the scope on the OAuth client in Airship, then
**restart the MCP server** so a new token is issued.

### 4. Naming convention (recommended)

| MCP config key | Agent invocation | Example |
|---|---|---|
| `"Carrefour PROD"` | `user-Carrefour PROD` | Production retail |
| `"GMF PROD"` | `user-GMF PROD` | Production finance |
| `"HM DEV"` | `user-HM DEV` | Non-prod sandbox |

Use **`PROD` / `DEV` suffixes** when the same brand has multiple Airship projects.

---

## Prerequisite — auth token & scopes (do this FIRST)
Before any data collection, the project's MCP server must authenticate with an Airship
auth token (OAuth client) that carries the right **scopes**. Create the token in the
Airship dashboard (Settings → OAuth) with **at least**:
- **`rpt`** — Reports API (`/api/reports/*`): sends, opens, optins, optouts, devices,
  events, responses/list, perpush/pergroup. **Required** — the review cannot run without it.
- **`tpl`** — Content API (`/api/content/templates`): template inventory & creatives.
  **Required** whenever the project uses template-driven / unicast campaigns.
- Optional but recommended for full depth: **`pln`** (pipelines/automations),
  **`sch`** (schedules), **experiments** (A/B). Missing → degrade gracefully (note
  "scope `<x>` unavailable"), don't fabricate.

If a call returns **401 `Expired token`**, ask the user to re-authenticate the MCP server
in Cursor settings, then retry. If it returns **401 `Missing required scope`**, the token
lacks that scope — add it on the token (report + content at minimum) and reconnect.

## Inputs (confirm first)
- **MCP server** for the project (e.g. `user-XX PROD`). Tool: `call_airship_api`.
- **Auth token with `rpt` + `tpl` scopes** active on that MCP server (see prerequisite above).
- **Client brand + site URL** (for brand context).
- **Period**: default trailing ~90 days, `precision=DAILY`. State exact dates.
- **Language**: default English; offer French.
- **Branding**: Airship default (see `reference.md`); client charter optional.

## Workflow
```
- [ ] 1. Brand & business context (web search, cite URLs) + confirm INDUSTRY
       (load benchmarks.md, match industry key for later comparison)
- [ ] 2. Pull core data: sends, opens, optins, optouts, devices
       (separate SNAPSHOT/whole-base from PERIOD metrics)
- [ ] 3. Pull events (ALL pages) + responses/list for peak days; fetch creatives by send type
- [ ] 4. Classify campaigns: one-shot vs automated/recurring
       (probe /pipelines, /schedules; else heuristic via classify_campaigns.py)
- [ ] 5. Check experiments (probe /experiments; flag A_B; pull experiment reports)
- [ ] 6. Templates inventory (/api/content/templates) + best-effort usage mapping
- [ ] 7. Value-bearing events + per-message attribution (events/summary/perpush|pergroup)
- [ ] 8. Recover categories for UNICAST sends (best-effort)
- [ ] 9. Aggregate to JSON; compute totals/averages/peaks/attribution
- [ ] 10. Generate charts (scripts/airship_charts.py)
- [ ] 11. Creatives: real (render_email.py) → reconstruct (render_mocks.py) as fallback
- [ ] 12. Build HTML report; convert to PDF+PNG (scripts/build_report.py)
- [ ] 13. Copy deliverables to Desktop; summarize
Every figure → source endpoint; every insight/reco → origin tag + confidence level.
```

### 1. Brand & business context (do FIRST; drives insights)
Web-search the brand: sector, app role, audience/geos & languages, offers/loyalty,
**seasonality/key moments**, recent news, competitors. Collect source URLs.
Cross-reference data spikes with brand events. Tag every insight/reco origin:
`[Data]`, `[Brand context]`, or `[Data+Context]`. Separate measured fact from
contextual hypothesis.
**Determine the client's industry** here: deduce it from the brand research, then
**confirm it with the user**. Load [benchmarks.md](benchmarks.md) and select the
matching industry key (via its `aliases`); carry it into the benchmarking step. If no
industry matches, note it and skip benchmark comparisons (don't force a mismatched one).

### 2-3. Data collection (Airship Reports API)
Call via MCP `call_airship_api`. Endpoints, params and definitions: see
[reference.md](reference.md). Key points:
- Paginate **all** pages of `/events` (`precision=MONTHLY`).
- For top campaigns, use `responses/list` on peak-send days (iterate `next_page`) and read
  each campaign's `push_type`.
- **Creative retrieval depends on the send type** (full table in `reference.md`):
  - **BROADCAST / SEGMENTS / A-B** → `GET /api/reports/perpush/pushbody/{push_id}`
    (`push_id` is a **path** param). Returns notif text + Message Center / email HTML.
  - **UNICAST / Create-and-Send** → per-push body is **empty**; don't rely on it. The
    creative lives in the **Content Template**: `GET /api/content/templates` (scope `tpl`),
    matched by `name`/`type`, then read `content.html_body`.
  - Only scan `/api/content/templates` when the project runs template-driven / unicast
    campaigns (automations, journeys, transactional). Skip it for pure-broadcast projects.
  - Render real `html_body` with `scripts/render_email.py`; reconstruct illustratively
    only when neither source yields content.
- **Probe the non-report endpoints** (other scopes) once each and degrade gracefully:
  `/api/pipelines` (`pln`, automations/journeys), `/api/schedules` (`sch`, recurring),
  `/api/experiments` (A/B), `/api/content/templates` (`tpl`). On 401/403, note
  "scope `<x>` unavailable" and fall back to reports-only heuristics; never fabricate.
- **Separate SNAPSHOT (whole base) from PERIOD metrics** (see `reference.md` →
  "Scope of measurement"). `devices` = the only source for opt-in **rate** and installed
  base (point-in-time, whole base, tag "(snapshot DD/MM)"). `sends/opens/optins/optouts/
  events` are bounded by the window (tag "(period)"). `optins/optouts` are daily **event
  flows** (include reinstalls/re-detections), NOT a net base change and NOT equal to the
  snapshot `opted_in/opted_out`. Never mix a snapshot figure with a period figure in one KPI.
- Custom event `value` is a client-declared counter/weight, **not currency** — never
  show it as money.

### 4. Analysis
Cover all of the following (see `reference.md` for detection logic & definitions):

**Permission & base (keep snapshot vs period separate)**
- Whole-base block (`/devices`): installed base, opt-in **rate**, opted-out, uninstalled
  per platform — all "(snapshot DD/MM)".
- Period block (`optins/optouts`): opt-in/opt-out **event** flows over the window — never
  framed as net base change, never equated to the snapshot counts.

**Marketing pressure (cross-platform AND per-platform)**
- Report **both** views (see `reference.md` → "Marketing pressure"):
  - **Cross-platform**: total sends (all channels) / weeks / total addressable base.
  - **Per-platform**: one figure per active channel (push iOS, push Android, push blended,
    email, web push, SMS…) = channel sends / weeks / that channel's own addressable base.
- **Match the denominator to the channel** (push → push `opted_in`; email → email base;
  web → web `opted_in`). If a denominator is unavailable (e.g. email = 0 active devices),
  show sends/week only and flag it. Call out channels far above/below the others
  (over-solicitation vs under-use). Tag "(period)".

**Campaign typology (one-shot vs automated/recurring)**
- Classify every campaign. Probe `/api/pipelines` (`pln`) and `/api/schedules` (`sch`);
  if unavailable, use the reports-only heuristic (`scripts/classify_campaigns.py`:
  group by `group_id` + normalized `message_name`, detect cadence).
- Produce **two separate top rankings**: Top one-shot sends and Top automated/recurring.
- One-shot: reach, direct/influenced rates, creative.
- Automated/recurring: per-occurrence volume, **volume drift** vs series median, and
  **engagement-rate trend** over time; flag significant drifts. (`pergroup/detail` or
  summed `perpush/detail`; `perpush/series` for shape.)

**Experiments (always check)**
- Probe `/api/experiments`; flag `push_type == A_B` in `responses/list`; for those pull
  `experiment/overview/{push_id}` + `experiment/detail/{push_id}/{variant_id}` (`rpt`).
  Report variants/winner, or state "no experiments detected in the period".

**Events deep dive (push deeper)**
- Inventory: total distinct events, total volume; taxonomy by `location`
  (custom / in_app_message / in_app_pager / ua_mcrap=Message Center / ua_interactive_notification).
- Attribution per key event: `direct` / `indirect` / `unattributed` (count and value).
- Business families (browse / conversion / loyalty / store / win-back …) tied to brand.
- Attribution funnel: push-attributed (direct+indirect) product views → cart → purchase.
- **Value-bearing events**: flag events whose name implies a quantity/revenue/duration AND
  whose `value` is non-zero (see `reference.md`). For each, add **per-message attribution**
  via `events/summary/perpush/{push_id}` (and `events/summary/pergroup/{group_id}` for
  recurring) on the top messages, shown beside top-campaign performance. Restate the
  `value` ≠ currency caveat.
- Flag anomalies/spikes and any multi-market/data-hygiene signals (e.g. foreign-language
  campaign names in one project).

**Unicast category recovery**
- For `UNICAST` sends, best-effort recover `campaigns.categories`/type (retry `pushbody`
  for metadata, pipeline lookup, `message_name` parse). Label the campaign type; if nothing
  recoverable, label "category unavailable".

**Templates inventory**
- From `/api/content/templates` (`tpl`): `total_count`, `type` mix, created/modified
  recency, feeds/snippets. Best-effort usage mapping (label "best-effort") — match names
  vs pushbody `message_name`/categories and vs pipelines/schedules; `modified_at` recency
  as activity proxy.

**Industry benchmarking (position KPIs vs peers)**
- Using the vertical from step 1, load benchmark values from `benchmarks.json` (human
  reference: `benchmarks.md`; source: Airship UA Benchmarks workbook). Benchmarked KPIs:
  `optin_rate`, `direct_open_rate`, `influenced_open_rate`, `sends_per_user_month`,
  `message_center_read_rate`. Show the **client value next to the vertical median (p50)**
  and the **[p10–p90] range** and the **gap** (points or ×), tagged `[Data]`.
- **Compare per device family** (iOS/Android/Web) — never blend platforms against a
  per-platform benchmark. There is **no blended opt-in** and **no opt-out** benchmark:
  compare opt-in per platform; for opt-out, state "no benchmark".
- **Pressure is PER MONTH**: the report's marketing pressure is sends/opted-in user/week →
  ×~4.33 (or recompute monthly) before comparing to `sends_per_user_month`.
- **Cite source + quarter + region (global)** beside every comparison. Telecom has no own
  vertical → use `utility_productivity` (or `all_verticals`) as a **labelled proxy**.
- If `benchmarks.json` is empty, the vertical/metric doesn't match, or the file is stale,
  **state "industry benchmark not available" and do not fabricate**.
- Benchmark comparisons are capped at **Medium** confidence (external/contextual).

**Verification & confidence (apply to every insight/reco)**
- State the verification basis (source endpoint(s) + sanity checks: sums reconcile, rates
  in 0–100%, sample size, full pagination, scope available).
- Tag each insight/reco with a confidence level **High / Medium / Low** (criteria in
  `reference.md`). Brand-context-only → Low; low-sample/degraded-scope → Medium max.
- Low-confidence items carry a "to verify" note (what would raise confidence).

### 5. Charts — `scripts/airship_charts.py`
Import the styled helpers (Airship palette, k/M formatter, dated axes for time series
only, no emoji in labels). See the module docstring for available functions:
stacked daily bars, area+mean line, donut, grouped/h-bars.

### 6. Creatives — prefer real, reconstruct only as fallback
**Real creatives (faithful preview)** — when you have actual HTML (`content.html_body`
from a Content Template, or decoded Message Center HTML from a per-push body):
```bash
python scripts/render_email.py creative.html out.png 680
```
`render_email.py` renders via Chrome headless (tolerates Chrome not exiting; uses a
timeout) and crops background-aware (works for white AND dark emails).

**Illustrative reconstructions (fallback only)** — when neither `perpush/pushbody`
(non-unicast) nor `/api/content/templates` (unicast) returns content:
```bash
python scripts/render_mocks.py   # render_push() / render_card()
```
Renders iOS lock-screen push and Message Center/in-app cards. Use the client's app
branding inside mockups (it depicts their message), keep the report chrome
Airship-branded, and clearly **label these as "illustrative reconstruction".**

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
3. Executive summary (verdict, KPIs with snapshot/period labels, **vs industry benchmark
   where available**, tags + confidence) ·
4. Volume & channels / **marketing pressure — cross-platform AND per-platform** (period) ·
5. Engagement (opens, period) ·
6. Permission & installed base — **two blocks: snapshot/whole-base (rate, base) vs period
   opt-in/opt-out event flows** ·
7. Campaign typology — one-shot vs automated/recurring (counts, mix, recurring trends) ·
8. Commerce/attribution funnel ·
9-10. Events deep dive (taxonomy, attribution, families, value-bearing events + per-message
   attribution, hygiene) ·
11. Experiments (variants/winner, or "none detected") ·
12. Templates inventory (count, types, recency, feeds; best-effort usage) ·
13-15. Top 5 per channel **split by one-shot vs automated/recurring**
   (Push / Message Center / In-app; UNICAST labelled with recovered categories; flag absent Email/SMS) ·
16. Recommendations (tagged + confidence) ·
17. Appendix: sources, definitions, **methodology (verification & confidence scale)**, glossary, endpoints.

## Quality gate (before delivery)
- [ ] Brand context researched, sourced, and used in insights/recos
- [ ] **Industry confirmed; benchmarked KPIs positioned vs the matching industry benchmark (median/range) with the benchmark's source/date/n/region — or "benchmark not available" stated; never fabricated; comparison confidence ≤ Medium**
- [ ] Each insight/reco tagged `[Data]` / `[Brand context]` / `[Data+Context]`
- [ ] **Snapshot (whole-base) vs period metrics kept separate and labelled; opt-in rate only from `/devices`; optin/optout shown as period event flows**
- [ ] **Marketing pressure reported both cross-platform AND per active channel (push iOS/Android, email, web…); denominator matched to each channel; missing denominators flagged**
- [ ] **Campaigns classified; two top rankings present (one-shot vs automated/recurring); recurring campaigns analysed for volume drift + engagement trend**
- [ ] **Experiments checked (probe + A_B); variants/winner shown or "none detected" stated**
- [ ] **Templates inventory present (count/types/recency/feeds) with best-effort usage mapping**
- [ ] **Value-bearing events flagged and given per-message attribution where applicable**
- [ ] **UNICAST campaigns labelled with recovered categories (or "category unavailable")**
- [ ] **Every insight/reco carries a verification basis + confidence (High/Medium/Low); low-confidence items state what would raise confidence**
- [ ] Every visual has a source; glossary + appendix (incl. methodology) present
- [ ] Creatives fetched by send type (pushbody for mass; Content Templates for unicast/CaS); real previews used where available, reconstructions labeled only as fallback
- [ ] No fabricated figures; unavailable data + degraded scopes flagged; reconstructions labeled
- [ ] Top 5 for each present channel; absent channels stated
- [ ] Events: all pages paginated; location/conversion taxonomy; families
- [ ] PDF page count == #CSS pages (no overflow); Airship branding respected
- [ ] `value` never shown as currency

## Dependencies
Python: `matplotlib`, `numpy`, `pillow`, `pymupdf`, `openpyxl` (benchmark import).
Google Chrome (headless) for HTML→PDF and mockup rendering.

## Resources
- [reference.md](reference.md) — endpoints (reports + pipelines/schedules/experiments/templates),
  snapshot-vs-period, campaign-typology & experiment detection, value-bearing events,
  unicast category recovery, verification & confidence, creative-retrieval table, Airship palette.
- [benchmarks.md](benchmarks.md) + `benchmarks.json` — Airship UA Benchmarks by vertical ×
  device family × percentile (opt-in, direct/influenced open, sends/user/month, MC read rate);
  load to position client KPIs vs peers. Refresh with `scripts/import_benchmarks.py`.
- `scripts/import_benchmarks.py` — parse an Airship UA Benchmarks `.xlsx` → regenerate
  `benchmarks.json` + `benchmarks.md` (run once per new quarter).
- `scripts/classify_campaigns.py` — normalize message names, group, detect cadence; tag each campaign one-shot vs automated/recurring.
- `scripts/render_email.py` — render a real email / Message Center `html_body` to a cropped PNG.
- `scripts/render_mocks.py` — illustrative push / in-app reconstructions (fallback only).
