#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read an account team brief (brief-template.md) into questions and context.

    python scripts/focus_brief.py work/<client>/brief_input.md     # print what was read
    python scripts/focus_brief.py --selftest

A brief with at least one `Q<n>:` line puts the review in *focused* mode: the questions
become ids (Q1, Q2, …) that the focus plan, the answers section and the gate all key on.
A brief without one — free-form notes, or no brief at all — leaves the review global.

Tolerant by design: account teams paste briefs from email. Questions are recognised under
`## Questions` or anywhere as a `Q<n>:` / `Q<n>.` / `Q<n> -` line; the headings are matched
loosely, in English or French.
"""
from __future__ import annotations

import json
import re
import sys

_HEADINGS = {
    "objective": r"objective|objectif|goal|but",
    "questions": r"questions?",
    "definitions": r"definitions?|d[ée]finitions?",
    "scope": r"scope|p[ée]rim[eè]tre",
    "hypotheses": r"hypothes[ei]s|hypoth[eè]ses?",
    "decision": r"decision|d[ée]cision",
    "context": r"(known )?context|contexte",
}
_Q_LINE = re.compile(r"^\s*(?:[-*]\s*)?\**Q(\d+)\**\s*[:.\-–)]\s*(.+?)\s*$", re.I)
_BULLET_Q = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+(.+\?)\s*$")


def _sections(text):
    out, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^#{1,3}\s+(.+?)\s*$", line)
        if m:
            title = m.group(1).lower()
            cur = next((k for k, pat in _HEADINGS.items()
                        if re.match(rf"^({pat})\b", title)), None)
            if cur:
                out.setdefault(cur, [])
            continue
        if cur:
            out[cur].append(line)
    return {k: "\n".join(v).strip() for k, v in out.items()}


def parse_text(text):
    """-> {'questions': [{'id', 'text'}], 'objective', 'definitions', ...}."""
    secs = _sections(text or "")
    questions, seen = [], set()
    for line in (text or "").splitlines():
        m = _Q_LINE.match(line)
        if m and m.group(2).strip("… .") and f"Q{int(m.group(1))}" not in seen:
            qid = f"Q{int(m.group(1))}"
            seen.add(qid)
            questions.append({"id": qid, "text": m.group(2).strip()})
    if not questions and secs.get("questions"):
        # A Questions heading holding plain bullets: number them in order.
        for line in secs["questions"].splitlines():
            m = _BULLET_Q.match(line)
            if m:
                questions.append({"id": f"Q{len(questions) + 1}", "text": m.group(1).strip()})
    out = {k: secs.get(k, "") for k in _HEADINGS if k != "questions"}
    out["questions"] = questions
    return out


def parse(path):
    with open(path, encoding="utf-8") as fh:
        return parse_text(fh.read())


def _selftest():
    fails = []

    def ck(cond, label):
        if not cond:
            fails.append(label)

    tpl = parse_text(
        "## Objective\nFind the funnel leak.\n\n## Questions\n\nQ1: Why do opt-ins drop?\n"
        "Q2: Is cadence too low?\nQ3: …\n\n## Definitions of the figures quoted\n"
        "- ~80,000 opt-ins: counts accounts — source CRM\n## Scope\nPush only.\n")
    ck([q["id"] for q in tpl["questions"]] == ["Q1", "Q2"], "template questions, the empty "
       f"placeholder skipped ({tpl['questions']})")
    ck(tpl["objective"] == "Find the funnel leak.", "objective read")
    ck("accounts" in tpl["definitions"] and tpl["scope"] == "Push only.", "definitions, scope")
    fr = parse_text("## Objectif\nx\n## Questions\n- Pourquoi l'opt-in baisse ?\n"
                    "1. La cadence est-elle trop basse ?\n")
    ck([q["id"] for q in fr["questions"]] == ["Q1", "Q2"], "plain bullets under Questions")
    free = parse_text("The client is a transport operator. We are auditing the push funnel.")
    ck(free["questions"] == [], "a free-form brief has no question → global mode")
    loose = parse_text("notes\n**Q2** - second?\nq1. first?\nQ2: duplicate\n")
    ck([q["id"] for q in loose["questions"]] == ["Q2", "Q1"], "loose Q lines, first id wins")
    ck(parse_text("")["questions"] == [], "empty brief")
    print(f"focus_brief selftest: {'ok' if not fails else 'FAILED'}")
    for f in fails:
        print(f"  - {f}")
    return 1 if fails else 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        sys.exit(_selftest())
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    print(json.dumps(parse(sys.argv[1]), ensure_ascii=False, indent=1))
