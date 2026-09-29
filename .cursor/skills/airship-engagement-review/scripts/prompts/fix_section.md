Your section `{{key}}` failed a check. The exact output:

{{failure}}

Fix it in work/{{client}}/sections/{{key}}.py (and its verdict record, if the failure is
about it). You may edit ONLY: {{allowed_files}}. Frozen artefacts (audit.json, facts.json,
analysis_brief.md) are read-only; an edit to them is reverted and ends the run.

Fix the cause, not the symptom: if the check is right that a number is not supported, the
fix is to stop publishing it or to say why it is not measurable — not to reword it until
the check stops matching. If you believe the check itself is wrong, say so and change nothing.

Re-run check_section.py before replying.
