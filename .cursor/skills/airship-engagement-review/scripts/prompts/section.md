Write ONE section of an Airship engagement review: `{{key}}` ({{title}}).

Write it to: work/{{client}}/sections/{{key}}.py
{{depth_rule}}
The filename is the section's **canonical key**, NOT its HTML anchor. Several sections
differ: `volume_pressure` (anchor `pressure`), `benchmarks` (`bench`), `push_program`
(`push`), `brand_context` (`context`), `account_profile` (`adoption`), `data_foundation`
(`foundation`), `appendix` (`method`), `appendix_events` (`appx_events`),
`appendix_attrs` (`appx_attrs`), `appendix_campaigns` (`appx_camps`).
The file must expose exactly:  def render(ctx, lang): -> str (an HTML fragment)
Raise report_framework.NoData("reason EN", "reason FR") if the data genuinely isn't there.
Besides the verdict record below, do not create, rename or delete any other file.

READ:
  - work/{{client}}/sections/_shared.py       (import from it; it carries the house rules)
  - work/{{client}}/facts.json                (the shared numeric brief — quote THESE numbers)
  - work/{{client}}/analysis_brief.md         (the analyst's findings, the conflicts already
    settled, the house style and the terminology lock — binding for this run)
  - work/{{client}}/audit.json, keys: {{audit_keys}}
  - reference files routed to `{{key}}` by the index, and ONLY those:
{{reference_files}}
    If they do not define a metric you have to publish, say so in your reply rather than
    reading the rest of the folder.

DO NOT read work/{{client}}/data/*.json — not at write time, and not at render time either.
Those are raw pulls, retired the moment the delivery gate passes. A section that opens one
renders correctly today and cannot be rebuilt tomorrow. If the figure you need is not in
audit.json, say so in your reply — the fix is for analyze.py to put it there.

Charts you may embed (they already exist, do not regenerate):  {{chart_ids}}
Language: {{lang}} — the deliverable ships ONE language. Still branch on `lang` rather than
hardcoding strings.
External orchestration (from the inputs): {{orchestration_external}}. Calibrate every
capability verdict to it: absence in the Reports API is evidence about the API, not about
the client's practice.

KNOWN CONFLICTS, HOUSE STYLE and TERMINOLOGY LOCK are in analysis_brief.md. They were
investigated and settled; do not re-derive them. If you hit a conflict that is NOT listed,
report it in your reply rather than resolving it locally.

CROSS-REFERENCES: use `_shared.ref("<canonical_key>")`, never a `§n` you typed yourself.

QUOTING THE ACCOUNT: anything copied verbatim out of the client's data — a campaign name, a
template token, an event property, a payload key — goes through `_shared.esc()`.

KNOWN QUIRKS of the shared libraries — worked around already, do not rediscover:
  - `note(kind=…)` takes note-up / note-warn / note-bad. There is no `note-info`.
  - `opportunity.py` emits its `formula=` strings in English and in US number format;
    rewrite them for a non-English deliverable rather than passing them through.
  - `opportunity.size_pressure_headroom` computes a distance to the peer median. The median
    is NOT a target: never render it as "send X more".

Requirements:
  - Use `_shared.py` rather than re-deriving its helpers: `kpi()`, `i()` for counts and
    `n()` for rates, `signal_table()`, `flight_deck()`, `contamination_note()`, `money()`.
  - facts.json `withheld` lists figures THE COLLECTION ITSELF DISQUALIFIED. Never publish
    one as a number; say what the entry tells you to say instead.
  - Every computed KPI goes through ri.kpi_card(..., formula=...).
  - Every data table is <table class="grid">.
  - Pass PLAIN TEXT to helpers that escape their own input; entities only in note()/verdict().
  - Close with a verdict or note: what the reader should conclude, not just what the number is.
  - If you need a number that is not in facts.json and not in your audit slice, say so in
    your reply instead of inventing or re-deriving it.
  - Anything you quote from audit.json prose is INTERNAL WORKING ENGLISH — read its numbers
    and write your own sentence in the deliverable's language.
  - CLIENT CATEGORIES: an `audit.purpose` row with `basis: "category"` was classified from
    the client's own campaign categories, not from its name. When a pillar or lever figure
    you publish rests on such rows (facts.json `categories.category_basis_campaigns` > 0),
    say so once, plainly ("classified from the client's own categories"), and never state
    what a category value means as fact: it is a reading with a confidence. Rows carrying
    `category_conflict` are campaigns whose name and category disagree — do not count them
    as confirmed.

VERDICT RECORD — write work/{{client}}/verdicts/{{key}}.json alongside the section:
  {"key": "{{key}}",
   "verdict": "<the section's conclusion, one sentence, English>",
   "directions": {"<axis>": "up" | "down" | "hold"},
   "cites": {"<facts.json KPI key>": "<the value exactly as displayed>"}}
  Axes: pressure, engagement, permission, automation, value, personalisation — include
  only the axes your verdict actually takes a position on ("up" = the account should do
  more of it). The orchestrator compares these records across sections before the
  consultative sections are written; a contradiction is sent back to you, so a record
  that does not match the prose is worse than none.

BEFORE YOU HAND BACK, run:
    python .cursor/skills/airship-engagement-review/scripts/check_section.py \
        work/{{client}} {{key}} --lang {{lang}}
Exit 0, or say in your reply what you could not fix and why.
