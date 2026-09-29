The pre-flight passed and audit.json, facts.json and analysis_brief.md are now FROZEN — do
not edit them again; the orchestrator hashes them and stops the run on any change.

Prepare everything the section writers will need, and nothing they will write themselves:

  1. The builder and the section helpers, from the scaffolds:
       cp .cursor/skills/airship-engagement-review/scripts/build_report_template.py work/{{client}}/build_report.py
       mkdir -p work/{{client}}/sections
       cp .cursor/skills/airship-engagement-review/scripts/sections_shared_template.py work/{{client}}/sections/_shared.py
     Fill ONLY their Inputs / CONFIGURE blocks (client display name, LANG = "{{lang}}",
     paths). Leave every renderer stub alone: sections/<key>.py files override them.
  2. work/{{client}}/make_charts.py — one English chart set (charts/ + specs.json), the
     STD_CHARTS ids of reference/build-framework.md, read from audit.json only.
  3. work/{{client}}/make_creatives.py — the 4-8 important messages of workflow.md step 11,
     rendered into creatives/ + creatives.json, from the decoded bodies in data/.
     Do NOT run 2 and 3: the orchestrator runs them concurrently, next.
  4. work/{{client}}/section_slices.json — for EVERY canonical key in this list:
         {{section_keys}}
     an object {"audit_keys": [top-level audit.json keys the section reads],
                "chart_ids": [chart ids from step 2 it may embed]}.
     Use [] rather than omitting a key. This is what each section writer is told to read,
     so a key missing here is a section written blind.

Reply with the chart ids you defined and anything you could not wire.
