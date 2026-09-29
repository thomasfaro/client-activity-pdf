You now write the consultative sections of the Airship engagement review for {{client}},
one at a time, in this conversation. They carry the report's argument, so they are written
last, by one writer, against everything already on disk.

This turn: `{{key}}` ({{title}}) → work/{{client}}/sections/{{key}}.py
Sections still to come after this one, in order: {{remaining}}
{{depth_rule}}
{{focus_rule}}

READ (once, at your first turn; later turns re-read only what changed):
  - work/{{client}}/analysis_brief.md       (binding: findings, settled conflicts, vocabulary)
  - work/{{client}}/verdicts.json            (the verdict every factual section reached)
  - account team brief: {{client_context}}
    (the recommendations and exec_summary answer its questions, from the data)
  - work/{{client}}/facts.json
  - the finished factual sections under work/{{client}}/sections/ (read, never edit)
  - the reference files routed to `{{key}}`:
{{reference_files}}
  - .cursor/skills/airship-engagement-review/report-structure.md, the entry for `{{key}}`

Rules:
  - Your section must not contradict verdicts.json. If you believe a factual verdict is
    wrong, say so in your reply; do not overrule it in prose.
  - Recommendations follow the directions in verdicts.json: no "send more" where a factual
    section concluded pressure should go down.
  - Language {{lang}}; external orchestration: {{orchestration_external}}.
  - The same section rules as every other section apply: kpi_card(..., formula=...),
    `grid` tables, _shared helpers, no data/*.json, no invented numbers.
  - A campaign classified from the client's own categories (`basis: "category"`) is a
    reading, not a fact: see the CLIENT CATEGORIES rule of the section prompt.
  - Write the verdict record work/{{client}}/verdicts/{{key}}.json, same format as the
    factual sections (see the section prompt), unless `{{key}}` takes no position.

BEFORE YOU HAND BACK, run:
    python .cursor/skills/airship-engagement-review/scripts/check_section.py \
        work/{{client}} {{key}} --lang {{lang}}
