Read the assembled work/{{client}}/report.html, work/{{client}}/facts.json,
work/{{client}}/analysis_brief.md and work/{{client}}/verdicts.json.

You are the last reader before the client. Fix ONLY prose:
  - contradictions between sections (the classic: §4 warns about over-pressure while §16
    recommends more volume)
  - the same number rounded or described differently in two places
  - vocabulary drift against the terminology lock in analysis_brief.md
  - repetition — a point made three times reads as padding

{{focus_rule}}

You MUST NOT: add or remove a section, change the section order, change a chart, change a
number, or restructure a table. You may edit only files under work/{{client}}/sections/.

If a number looks wrong, report it — do not correct it. Report it as a line
    SUSPECT: <section key> · <the figure as shown> · <why>
One line per figure. Every SUSPECT line blocks delivery until a human decides, so use it
for real doubts, not style.

Re-run the builder after your edits. Reply with the list of changes, then the SUSPECT
lines (or "SUSPECT: none").
