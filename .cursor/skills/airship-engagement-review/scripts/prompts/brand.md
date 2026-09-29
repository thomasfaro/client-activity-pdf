Research the brand behind the Airship engagement review for {{client}}, following your
agent instructions to the letter: one pass, the fixed budget, the fixed schema.

Brand / site: {{brand}}
Market: {{country}}
Account team brief: {{client_context}} (leads to verify and to cite from public sources,
never a source in itself)
Write: work/{{client}}/brand.json
End with:  python .cursor/skills/airship-engagement-review/scripts/check_brand.py work/{{client}}/brand.json
It must print `ok`. Do not dispatch any other agent.
