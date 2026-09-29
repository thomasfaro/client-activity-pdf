Run:  python .cursor/skills/airship-engagement-review/scripts/verify_report.py work/{{client}}/report.html

The failures to fix this round (only these):
{{failures}}

You may edit ONLY these files: {{allowed_files}}
Any other edit is rejected and reverted by the orchestrator.

For each ✗, apply the fix named in the message, then re-run until it passes or you are
blocked. These are the mechanical ones and are yours to fix:
  missing `grid` class · missing formula= · double-escaped entity · missing French accent ·
  undefined CSS class · orphan methodology button · empty <img> src ·
  an unformatted f-string under "No template text"

STOP and hand back if the ✗ is: a missing canonical section, a missing chart or creative,
a thin section, insufficient recommendation depth, "KPI values agree with facts.json",
a TODO under "No template text", or "Charts do not re-publish a withheld metric".
Those are content problems, not formatting ones. Never edit audit.json, facts.json or
analysis_brief.md. Never pass --no-gate. Edit section sources, never report.html.

The builder side is not yours either: build_report.py, make_charts.py and
sections/_shared.py are shared by every section, and an edit there is reverted. If a ✗ can
only be fixed in one of them, change nothing and hand back with the word "structural" and
the file it would take.
