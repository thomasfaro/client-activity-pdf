# Account team brief — template

Copy this file to `work/<client>/brief_input.md` (client data never enters the repository),
fill it, and pass it with `run_review.py --context work/<client>/brief_input.md`.

- **With at least one question under `## Questions`**, the review runs in *focused* mode:
  the analyst maps each question to the sections that answer it, those sections are
  written in depth, the others condensed, and a section "Answers to your questions" opens
  the report. The run stops if a question is left without an answer.
- **Without questions** (or without a brief), the review is the global one, unchanged.

Every heading is optional except `## Questions` in focused mode. Delete the guidance lines.

---

## Objective

One or two sentences: what the review is for, and for whom.

## Questions

One per line, `Q<n>:` then the question. Ask what you want answered, not what to compute.

Q1: …
Q2: …

## Definitions of the figures quoted

Every figure this brief quotes: what it counts, and where it comes from. A figure without
a definition is checked against the nearest measurable one, and the two may not measure
the same thing (accounts are not devices; a segment is not an opt-in base).

- ~<figure> <label>: counts <unit> — source <tool / report / person>, as of <date>.

## Scope

The window, the platforms, the programmes or messages in scope, and what is out of scope.

## Hypotheses to test

What the account team believes, stated so the data can confirm or overturn it.

## Decision this report informs

The decision or programme it feeds (e.g. a welcome programme, a budget, a renewal).

## Known context

Systems outside Airship, recent releases, incidents, seasonality — anything the Reports
API cannot show.
