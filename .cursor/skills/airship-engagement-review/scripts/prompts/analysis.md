You are the analyst of an Airship engagement review (wave 2). The collection is finished;
the raw pulls are in work/{{client}}/data/ and their coverage in
work/{{client}}/data/collect_manifest.json.

Account: {{client}} · MCP project {{project}} · window {{start}} → {{end}} · language {{lang}}
External orchestration (from the inputs): {{orchestration_external}}
Tagging-plan audit: {{tagging_plan}}
Brand research: work/{{client}}/brand.json (may still be in progress; read it by key)
Account team brief: {{client_context}}
  Read it first. Its questions set the report's focus: every question it asks is answered
  by a Key finding, or named under Withheld metrics with the reason the data cannot answer
  it. Its figures are the account team's, not measurements: check each against the data
  and settle any gap under Conflicts settled — never publish one unverified.

{{focus_rule}}

READ:
  - .cursor/skills/airship-engagement-review/analysis-spec.md — what to compute and what it means
  - .cursor/skills/airship-engagement-review/workflow.md — steps 2b to 9
  - reference/api-endpoints.md and reference/channels-scope.md (via the reference.md index)

PRODUCE, in this order:
  1. work/{{client}}/analyze.py and its output work/{{client}}/audit.json. Derive each metric
     once, under an explicit name. Process every row — no voluntary sub-sampling.
     Build `audit.purpose` AND `audit.categories` in one call,
     `campaign_categories.enrich(campaigns, vertical, bodies, decoded, groups_decoded,
     hypotheses=<work/{{client}}/category_hypotheses.json if present>, reachable)`, never
     `campaign_purpose.analyze` alone: the client's own categories (wave 2a) reclassify
     campaigns only where their reading is Medium or High, and every section then reads
     the enriched `audit.purpose`. When categories are unavailable, `enrich` returns the
     plain classification unchanged and `audit.categories.reason` says why.
  2. work/{{client}}/analysis_brief.md, with EXACTLY these headings:

     ## Key findings
     5 to 8 bullets. Each: the finding in one plain sentence, then `(facts: <kpi key>)` —
     the facts.json key that supports it. A finding with no supporting key is an opinion;
     label it `(assessment)`.
     ## Conflicts settled
     Every apparent contradiction you investigated: the two figures, the reading kept, the
     phrasing sections must use.
     ## Withheld metrics
     Every figure the collection disqualified, what to publish instead.
     ## External orchestration
     The stance the whole report takes, given the input above, and which verdicts it hedges.
     Weigh `audit.categories.external_sources` here: a `strong` vendor clue (SFMC, Adobe,
     Braze… in categories, tags or message names) is a reason to hedge, not proof — say
     "categories reference <vendor>", never "sent by <vendor>". When the account team's
     brief names an orchestrator, set the clues against it: a matching clue corroborates
     the brief (say both, and which is which); a different vendor is a conflict to settle
     above. No clue is evidence of nothing when wave 2a was skipped (`audit.categories`
     unavailable, e.g. no decoded push body): say the categories could not be read, not
     that they contradict the brief.
     ## House style
     Conventions settled for this run (counts vs rates helpers, channel naming, how absence
     is phrased).
     ## Terminology lock
     One label per metric: `<metric>` is always "<label>", never "<the tempting wrong one>".

Then run, and fix analyze.py until both pass (a FAIL is a stop, not a note):
    python .cursor/skills/airship-engagement-review/scripts/verify_audit.py work/{{client}}/audit.json
    python .cursor/skills/airship-engagement-review/scripts/build_facts.py work/{{client}}/audit.json --verify

Do not write any section. Reply with the findings list and anything you could not resolve.
