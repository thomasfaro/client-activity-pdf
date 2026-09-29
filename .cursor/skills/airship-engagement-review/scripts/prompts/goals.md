Write the prose of the mode B Goals review for {{client}}, following
.cursor/skills/airship-engagement-review/mode-b.md.

The deterministic part is done: work/{{client}}/goals/goals.json and the charts exist, and
work/{{client}}/goals/build_report.py was copied from build_goals_template.py. What is left
is every block marked TODO in that builder. English only. Do not call any API.

Rules from mode-b.md bind: candidate selection comes from goals.json, never from your own
list; the blind funnel stages are stated, not hidden.

When done, run:
    python work/{{client}}/goals/build_report.py
It runs the gate under --profile goals. Reply with its output.
