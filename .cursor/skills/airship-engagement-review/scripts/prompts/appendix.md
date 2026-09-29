Write the data appendix `{{key}}` ({{title}}) of the Airship engagement review for
{{client}}, following your agent instructions.

Write to: work/{{client}}/sections/{{key}}.py  (exposes `def render(ctx, lang): -> str`)
Language: {{lang}}
READ: work/{{client}}/sections/_shared.py, work/{{client}}/facts.json, the audit keys
{{audit_keys}}, and the reference files routed to `{{key}}`:
{{reference_files}}

Do not summarise, rank, truncate or compute. If the task turns out to need a verdict, stop
and hand it back. Write no verdict record: an appendix takes no position.

BEFORE YOU HAND BACK, run:
    python .cursor/skills/airship-engagement-review/scripts/check_section.py \
        work/{{client}} {{key}} --lang {{lang}}
