You read the client's own campaign categories (Airship `campaigns.categories`) for an
Airship engagement review (wave 2a, before the analyst). Clients tag sends with these
values for their own reporting: it is an external classification, and your job is to
propose what each value MEANS. You do not decide what is used — the code does, by testing
each reading against the data. A reading it cannot corroborate stays in the appendix.

Account: {{client}}
Input (read it whole): work/{{client}}/category_schema.json
  - `coverage`, `schema`: how the values are built — facets, positional codes
    (separator, positions and the role the code guessed for each), `key:value` pairs,
    free labels, noise.
  - `terms[]`: every analysable value, with `term` (the id you must quote), `display`,
    `scope`, `position`, campaigns/sends, the lexicon candidates already found, the share
    of automated campaigns carrying it, sample campaign labels, the pillar the name-based
    classifier gave those samples, and up to two sample message bodies.
  - `levers`, `pillars`, `roles`: the only values you may use.
  - `vertical`, `external_sources`.
Context: work/{{client}}/brand.json if it exists (the brand's business and vertical) —
the same code means different things in different verticals ("live" is a sports feed for
a broadcaster and a store opening for a retailer).

WRITE work/{{client}}/category_hypotheses.json:

    {"scheme": "<one or two sentences: how the client builds its categories>",
     "hypotheses": [
       {"term": "<a term id from category_schema.json, verbatim>",
        "role": "<one of roles>",
        "lever": "<a lever key, or null>",
        "pillar": "<a pillar key, or null>",
        "meaning": "<what the value stands for, in plain words; 'unknown' if you cannot tell>",
        "language": "<ISO code of the word, 'code' for an abbreviation, 'unknown'>",
        "rationale": "<the observed values that support it: labels, bodies, position>"}]}

RULES
  - `role: intent` is the only role that can classify campaigns; give it a lever (or at
    least a pillar) only when the samples support it. Every other role (business_unit,
    brand, product, audience, channel, locale, date, sequence, id, source, test, topic)
    describes the value without classifying: it feeds the scheme card, nothing else.
  - A lever must belong to the pillar you give. Do not invent keys.
  - Positional codes: reason per position. A position whose values are all channel or
    locale codes is not intent, however tempting one value looks.
  - Any language. Read German compounds, abbreviations (`CNV` conversion, `AWR`
    awareness, `RTN` retention), mixed-language labels. Say `code` when it is a code.
  - Do not re-propose what the lexicon already matched unless you disagree with it; when
    you disagree, propose your reading — both are tested and the code keeps the better one.
    When the lexicon matched a value that is not an intent at all (`FREE`/`PAY` as an
    offer tier, `winback` as a target audience, a show title containing `VIP`), give it
    its real role: that alone demotes the lexicon reading to the appendix.
  - Skip what you cannot read. An absent hypothesis costs nothing; a wrong one is
    tested and refuted. Never propose a term to make a coverage number look better.
  - A value naming a tool (SFMC, Adobe, Braze…) gets `role: source`.
  - Client data never leaves work/{{client}}/: write nothing anywhere else.

Then run, and fix the JSON until it passes (a FAIL is a stop):
    python .cursor/skills/airship-engagement-review/scripts/campaign_categories.py validate work/{{client}}

Reply with the scheme sentence and the three readings you are least sure of.
