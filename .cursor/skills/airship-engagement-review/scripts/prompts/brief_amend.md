The three pilot sections are written and gated: {{pilot_keys}}.

Gate and check_section output for the pilots:
{{pilot_report}}

Update work/{{client}}/analysis_brief.md from what the pilots turned up — and ONLY that file:
  - add every conflict the pilots resolved to "## Conflicts settled"
  - add every convention they settled to "## House style"
  - add every label they had to choose to "## Terminology lock"
Two lines per item. Ten section agents are about to read this; each thing you settle here is
a discovery none of them pays for, and a phrasing none of them improvises.

Do not change audit.json, facts.json or any section. The brief is re-frozen after this edit.

Then read the three pilot sections (work/{{client}}/sections/<key>.py) against the amended
brief, audit.json and facts.json. A pilot that contradicts something you just settled — a
wrong alias, a formula the brief corrects, a comparison against the wrong baseline, a label
the terminology lock forbids — ships that error unless it is sent back. You do not fix it;
you name it. End your reply with one line per error, exactly:

    PILOT_FIX: <key> · <the error, with the figure or phrase as it stands> · <the correction expected>

or, when the pilots carry none, the single line `PILOT_FIX: none`. Each line is sent to the
section's writer as a failure to fix, so name only what is wrong, not what could be better.

Reply with the items you added, then the PILOT_FIX lines.
