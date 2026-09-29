# Reference — index

The reference material lives in [`reference/`](reference/), one file per topic. **Read the
files routed to your task below, and only those.** A section agent needs one or two of
them; the endpoint tables, the i18n contract and the framework scaffold belong to waves 1,
2 and 6, and a wave-4 agent that loads them has spent its context on material it cannot
cite.

If your section is not listed, or the files named do not define a metric you must publish,
**say so in your reply** rather than reading the whole folder: the gap belongs in this
table. `check_section.py` flags a published KPI whose definition file is not routed to its
section (see `build_facts.KPI_DEFINITIONS`).

## Routing — canonical section key → files

| Section (canonical key) | Files | ≈ tokens |
|---|---|---|
| `volume_pressure` | [channels-scope](reference/channels-scope.md) · [definitions](reference/definitions.md) | 4 200 |
| `delivery_shape` | [campaigns](reference/campaigns.md) · [definitions](reference/definitions.md) | 6 500 |
| `engagement` | [channels-scope](reference/channels-scope.md) · [definitions](reference/definitions.md) | 4 200 |
| `permission` | [channels-scope](reference/channels-scope.md) · [definitions](reference/definitions.md) | 4 200 |
| `typology` | [campaigns](reference/campaigns.md) · [channels-scope](reference/channels-scope.md) | 8 200 |
| `detected` | [campaigns](reference/campaigns.md) · [verification](reference/verification.md) | 7 200 |
| `client_categories` | [campaigns](reference/campaigns.md) · [verification](reference/verification.md) | 7 200 |
| `events` | [events-goals](reference/events-goals.md) · [verification](reference/verification.md) | 5 300 |
| `inapp` | [channels-scope](reference/channels-scope.md) · [verification](reference/verification.md) | 4 900 |
| `data_foundation` | [events-goals](reference/events-goals.md) | 3 300 |
| `appendix_events` | [events-goals](reference/events-goals.md) | 3 300 |
| `appendix_attrs` | [events-goals](reference/events-goals.md) | 3 300 |
| `appendix_campaigns` | [campaigns](reference/campaigns.md) · [verification](reference/verification.md) | 7 200 |
| `benchmarks` | [benchmarks-baseline](reference/benchmarks-baseline.md) · [definitions](reference/definitions.md) | 2 700 |
| `strategy`, `playbook` | [pillar-playbook](reference/pillar-playbook.md) | 2 300 |
| `push_program` | [campaigns](reference/campaigns.md) · [channels-scope](reference/channels-scope.md) | 8 300 |
| `channels_exp`, `best_practices` | [campaigns](reference/campaigns.md) | 5 300 |
| `email_program` | [channels-scope](reference/channels-scope.md) · [api-endpoints](reference/api-endpoints.md) | 8 600 |
| `account_profile` | [channels-scope](reference/channels-scope.md) · [definitions](reference/definitions.md) · [events-goals](reference/events-goals.md) | 7 600 |
| `brand_context` | [verification](reference/verification.md) · [definitions](reference/definitions.md) | 3 300 |
| `exec_summary` | [verification](reference/verification.md) · [definitions](reference/definitions.md) · [channels-scope](reference/channels-scope.md) · [events-goals](reference/events-goals.md) | 9 600 |
| `focus_answers`, `recommendations` | [verification](reference/verification.md) · [definitions](reference/definitions.md) | 3 300 |
| `cross_app` | [benchmarks-baseline](reference/benchmarks-baseline.md) · [definitions](reference/definitions.md) | 2 700 |
| `appendix` | [verification](reference/verification.md) · [definitions](reference/definitions.md) | 3 300 |

**Waves 1–2** (collection and analysis) are the opposite case: they need
[api-endpoints](reference/api-endpoints.md) in full, with the time-window quirks, plus
[channels-scope](reference/channels-scope.md). **Wave 6** (build, gate, PDF) needs
[build-framework](reference/build-framework.md).

The machine-readable copy of this table is `REFERENCE_ROUTING` in
[`scripts/canonical_sections.py`](scripts/canonical_sections.py); the selftest keeps the
two in step.

## Where each heading lives

Scripts and older notes say "see reference.md, *heading*". The heading is unchanged; this
is the file it moved to.

| File | Headings |
|---|---|
| [api-endpoints](reference/api-endpoints.md) | MCP access · Airship Reports API endpoints (activity log, `rich` vs `alerting`, `sends` vs `rich_sends`, time-window quirks, the sends-is-not-push-only trap, `200` without an answer, in-app, email/SMS per-push) |
| [channels-scope](reference/channels-scope.md) | Per-channel activity & typology · Scope of measurement (snapshot vs period, creative retrieval, hero image, Message Center preview, real app logo) · Channels |
| [campaigns](reference/campaigns.md) | Campaign typology · Campaign analysis by channel (push shape `1b`/`1c`, email, SMS/in-app/MC, objective creative selection) · Experiments · Unicast · Creative coverage · Programmes shown by their identifier · Flight Deck deep-links |
| [pillar-playbook](reference/pillar-playbook.md) | Campaign purpose & pillar playbook |
| [events-goals](reference/events-goals.md) | Custom-event contextualisation (`value`, opportunity gaps) · Data-collection audit enrichment (per-campaign attribution) · Airship Goals |
| [verification](reference/verification.md) | Verification & confidence · Value measurability · Scene instrumentation · Coverage · Proof points |
| [benchmarks-baseline](reference/benchmarks-baseline.md) | Industry benchmarks · Internal baseline |
| [definitions](reference/definitions.md) | Definitions |
| [build-framework](reference/build-framework.md) | Airship branding · Multi-language (i18n contract) · Deliverable · Shared framework & canonical scaffold · Page / PDF rules |
