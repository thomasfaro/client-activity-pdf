#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The focus plan of a focused review, and the check that every question got an answer.

    python scripts/focus_plan.py --check work/<client>            # after the analysis
    python scripts/focus_plan.py --check-answers work/<client>    # after wave 5
    python scripts/focus_plan.py --selftest

A review whose brief (`work/<client>/client_context.md`, see brief-template.md) asks
questions is *focused*. The analyst then writes `focus_plan.json`:

    {"questions": [{"id": "Q1", "sections": ["permission"], "facts": ["app_optin"],
                    "answerable": true, "reason": ""}],
     "depth": {"permission": "lead", "typology": "condensed", ...}}

and wave 5 writes `answers.json` beside the "Answers to your questions" section:

    {"Q1": {"answer": "...", "confidence": "high|medium|low|not_measurable",
            "facts": ["app_optin"], "sections": ["permission"], "reason": "",
            "overturned_by": "..."}}

A fact is a facts.json KPI key, or `audit:<dotted.path>` into audit.json — a question the
brief asks is not always one of the dozen KPIs, and the path is still checkable.

Neither file decides anything about the numbers; both only make sure the report is built
around the questions it was asked, and that none of them is silently dropped. Exit 1 on
any problem.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import canonical_sections as cs  # noqa: E402
import focus_brief as fb         # noqa: E402

DEPTHS = ("lead", "standard", "condensed")
CONFIDENCE = ("high", "medium", "low", "not_measurable")
ANSWERS_KEY = "focus_answers"
# They carry the report's argument; condensing them would condense the answers.
NEVER_CONDENSED = ("exec_summary", "recommendations")
CONDENSED_MAX_WORDS = 120

DEPTH_RULES = {
    "lead": ("DEPTH: lead — this section answers the brief's question(s) {qs}. Write it in "
             "full depth, and address each of those questions explicitly, by its id, with "
             "what the data shows, the verdict, and the fact that would overturn it."),
    "standard": "DEPTH: standard.",
    "condensed": ("DEPTH: condensed — off the brief's focus. KPI cards and the verdict only, "
                  f"at most ~{CONDENSED_MAX_WORDS} words of prose, no sub-analysis, no "
                  "extra table. The verdict record is still due. Condensed is not N/A: "
                  "the section still measures this account."),
}


def _load(work, name):
    p = os.path.join(work, name)
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def load_plan(work):
    return _load(work, "focus_plan.json") or {}


def brief_questions(work):
    p = os.path.join(work, "client_context.md")
    return fb.parse(p)["questions"] if os.path.isfile(p) else []


def spine_keys():
    return [s["key"] for s in cs.CANONICAL_SECTIONS if s["key"] not in ("cover", ANSWERS_KEY)]


def depth_of(plan, key):
    return (plan.get("depth") or {}).get(key) or "standard"


def questions_for(plan, key):
    return [q["id"] for q in plan.get("questions") or [] if key in (q.get("sections") or [])]


def depth_rule(plan, key):
    """The line the section prompt carries; 'standard' outside a focused review."""
    if not plan:
        return DEPTH_RULES["standard"]
    d = depth_of(plan, key)
    return DEPTH_RULES[d].format(qs=", ".join(questions_for(plan, key)) or "—")


def _qlist(questions):
    return "\n".join(f"    {q['id']}: {q['text']}" for q in questions)


def analysis_rule(client, questions):
    """{{focus_rule}} of prompts/analysis.md."""
    if not questions:
        return ("GLOBAL REVIEW — the brief asks no numbered question (or there is no brief). "
                "Every section is written at standard depth; do not write focus_plan.json.")
    return f"""FOCUSED REVIEW — the brief asks {len(questions)} question(s):
{_qlist(questions)}
  The Key findings answer them first, in that order. Then write
  work/{client}/focus_plan.json:
    {{"questions": [{{"id": "Q1", "sections": ["<canonical key>", ...],
                    "facts": ["<facts.json KPI key>" | "audit:<dotted.path>", ...],
                    "answerable": true, "reason": ""}}],
     "depth": {{"<canonical key>": "lead" | "standard" | "condensed", ...}}}}
  - one entry per question id above, no other;
  - `sections`: the sections whose data answers it — each of them is "lead"; never one
    this run will not write (client_categories when audit.categories is not available,
    data_foundation and the data appendices without a tagging plan);
  - "condensed" for a section off the brief's focus (KPI cards and a verdict, ~{CONDENSED_MAX_WORDS}
    words); never exec_summary or recommendations; condensed is not N/A — the section
    still measures the account;
  - a depth for every mandatory section; the others default to "standard";
  - a question the data cannot answer: "answerable": false, the reason, and the same
    question named under Withheld metrics.
  Then run, and fix focus_plan.json until it passes:
    python .cursor/skills/airship-engagement-review/scripts/focus_plan.py --check work/{client}"""


def consultative_rule(client, key, plan):
    """{{focus_rule}} of prompts/consultative.md."""
    if not plan:
        return "GLOBAL REVIEW — no brief question to answer; argue from the data."
    if key == ANSWERS_KEY:
        return f"""FOCUSED REVIEW — this section answers the brief's questions. Write
  work/{client}/answers.json first:
    {{"Q1": {{"answer": "<one or two sentences, English>",
             "confidence": "high" | "medium" | "low" | "not_measurable",
             "facts": ["<the keys the answer rests on, as in focus_plan.json>"],
             "sections": ["<the lead sections that show the evidence>"],
             "reason": "<why, when not_measurable>",
             "overturned_by": "<the fact that would change the answer>"}}}}
  One entry per question in focus_plan.json. Answer from verdicts.json and the finished
  sections — never against them. A question the plan found not answerable gets
  "not_measurable", its reason, and what would make it measurable. Then render the
  section from `_shared.QUESTIONS` (the brief's wording) and `_shared.ANSWERS`: one
  ri.question_card(qid, question, answer, confidence, facts=..., section_links=...,
  lang=lang) per question, in order, `section_links` built with `_shared.ref(key)`, the
  answer rewritten in the deliverable's language. No verdict record: the answers
  restate verdicts, they do not add one. Then run:
    python .cursor/skills/airship-engagement-review/scripts/focus_plan.py --check-answers work/{client}"""
    if key == "exec_summary":
        return (f"FOCUSED REVIEW — open on the answers: the first paragraph gives each "
                f"question's answer in one sentence, as in work/{client}/answers.json, and "
                f"points to `_shared.ref(\"{ANSWERS_KEY}\")`. The rest of the summary follows.")
    if key == "recommendations":
        return ("FOCUSED REVIEW — order the recommendations by the brief's questions they "
                "serve, the questions first; the rest after.")
    return "FOCUSED REVIEW — the brief's questions are answered in focus_answers."


def coherence_rule(client, plan):
    """{{focus_rule}} of prompts/coherence.md."""
    if not plan:
        return "GLOBAL REVIEW — no answers section to check."
    return (f"FOCUSED REVIEW — also check the answers (sections/{ANSWERS_KEY}.py and "
            f"work/{client}/answers.json) against the sections they link: an answer the "
            f"section's data does not support, or a confidence the section contradicts, is a "
            f"contradiction. Fix the prose if it is only wording; if the answer itself is "
            f"wrong, report SUSPECT: {ANSWERS_KEY} · <Q id> · <why>. answers.json is not "
            f"yours to edit.")


def _fact_ok(ref, facts, audit):
    if ref.startswith("audit:"):
        node = audit
        for part in ref[6:].split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return False
        return True
    return ref in {k.get("key") for k in (facts or {}).get("kpis") or []}


def unwritten_sections(work, audit):
    """{key: why} — optional sections this run will not write, as run_review decides them.

    A question resting on one of them would pass here and leave its lead section missing
    from the report, so the plan is refused instead.
    """
    out = {}
    cats = (audit or {}).get("categories")
    if not (isinstance(cats, dict) and cats.get("available")):
        out["client_categories"] = ("the client's categories were not readable "
                                    "(audit.categories.available is false)")
    inputs = (_load(work, "run_state.json") or {}).get("inputs") or {}
    if not (inputs.get("tagging_plan") or os.path.isfile(os.path.join(work, "tagging_plan.json"))):
        for k in ["data_foundation"] + list(cs.APPENDIX_POOL):
            out[k] = "no tagging plan was supplied"
    return out


def check_plan(plan, questions, facts, audit, unwritten=None):
    """-> problems (list of str). `questions`: the brief's [{'id', 'text'}].
    `unwritten`: {key: why} of sections the run will not write (see unwritten_sections)."""
    probs = []
    unwritten = unwritten or {}
    if not plan:
        return ["focus_plan.json is missing — a focused review needs one"]
    keys = set(spine_keys())
    ids = [q["id"] for q in questions]
    got = {q.get("id"): q for q in plan.get("questions") or []}
    for qid in ids:
        if qid not in got:
            probs.append(f"{qid} from the brief is not in focus_plan.json")
    for qid in got:
        if qid not in ids:
            probs.append(f"{qid} is in focus_plan.json but not in the brief")
    depth = plan.get("depth") or {}
    for k, d in depth.items():
        if k not in keys:
            probs.append(f"depth: '{k}' is not a canonical section key")
        elif d not in DEPTHS:
            probs.append(f"depth: {k}={d!r} (one of {', '.join(DEPTHS)})")
    for s in cs.CANONICAL_SECTIONS:
        if s.get("gate_required") and s["key"] not in depth:
            probs.append(f"depth: mandatory section '{s['key']}' has no depth")
    for k in NEVER_CONDENSED:
        if depth.get(k) == "condensed":
            probs.append(f"depth: '{k}' carries the argument and cannot be condensed")
    for qid, q in got.items():
        secs = q.get("sections") or []
        if q.get("answerable", True):
            if not secs:
                probs.append(f"{qid}: answerable but names no section that answers it")
            if not q.get("facts"):
                probs.append(f"{qid}: answerable but cites no fact")
        elif not (q.get("reason") or "").strip():
            probs.append(f"{qid}: not answerable, and no reason given")
        for k in secs:
            if k not in keys:
                probs.append(f"{qid}: section '{k}' is not a canonical key")
            elif k in unwritten:
                probs.append(f"{qid}: section '{k}' will not be written in this run — "
                             f"{unwritten[k]}; answer from a section that will, or mark "
                             f"the question not answerable")
            elif depth.get(k) != "lead":
                probs.append(f"{qid}: section '{k}' answers it but is not 'lead'")
        for f in q.get("facts") or []:
            if not _fact_ok(f, facts, audit):
                probs.append(f"{qid}: fact '{f}' is neither a facts.json KPI nor an "
                             f"audit.json path")
    return probs


def check_answers(answers, plan, facts, audit):
    probs = []
    if answers is None:
        return ["answers.json is missing — wave 5 wrote no answer record"]
    keys = set(spine_keys())
    for q in plan.get("questions") or []:
        qid = q["id"]
        a = answers.get(qid)
        if not isinstance(a, dict):
            probs.append(f"{qid}: no answer")
            continue
        if not (a.get("answer") or "").strip():
            probs.append(f"{qid}: empty answer")
        conf = a.get("confidence")
        if conf not in CONFIDENCE:
            probs.append(f"{qid}: confidence {conf!r} (one of {', '.join(CONFIDENCE)})")
        if conf == "not_measurable" and not (a.get("reason") or "").strip():
            probs.append(f"{qid}: not_measurable, and no reason given")
        if conf == "high" and q.get("answerable") is False:
            probs.append(f"{qid}: answered with high confidence, but the plan found it "
                         f"not answerable ({q.get('reason')})")
        if conf != "not_measurable" and not a.get("facts"):
            probs.append(f"{qid}: an answer that cites no fact is an opinion")
        for f in a.get("facts") or []:
            if not _fact_ok(f, facts, audit):
                probs.append(f"{qid}: fact '{f}' is neither a facts.json KPI nor an "
                             f"audit.json path")
        for k in a.get("sections") or []:
            if k not in keys:
                probs.append(f"{qid}: section '{k}' is not a canonical key")
    return probs


def summary(plan):
    """A few lines for the pre-flight checkpoint."""
    lines = []
    for q in plan.get("questions") or []:
        if q.get("answerable", True):
            lines.append(f"{q['id']} → {', '.join(q.get('sections') or [])} "
                         f"(facts: {', '.join(q.get('facts') or [])})")
        else:
            lines.append(f"{q['id']} → NOT ANSWERABLE: {q.get('reason')}")
    depth = plan.get("depth") or {}
    cond = sorted(k for k, d in depth.items() if d == "condensed")
    if cond:
        lines.append(f"condensed: {', '.join(cond)}")
    return "\n".join(lines)


def run_check(work, answers=False):
    plan = load_plan(work)
    facts, audit = _load(work, "facts.json") or {}, _load(work, "audit.json") or {}
    if answers:
        return check_answers(_load(work, "answers.json"), plan, facts, audit)
    return check_plan(plan, brief_questions(work), facts, audit,
                      unwritten_sections(work, audit))


def _selftest():
    fails = []

    def ck(cond, label):
        if not cond:
            fails.append(label)

    qs = [{"id": "Q1", "text": "a?"}, {"id": "Q2", "text": "b?"}]
    facts = {"kpis": [{"key": "app_optin"}, {"key": "pressure"}]}
    audit = {"events": {"per_event": {"logged_in": {"total": 3}}}}
    depth = {k: "standard" for k in spine_keys()
             if cs.BY_KEY[k].get("gate_required")}
    depth.update(permission="lead", typology="condensed", volume_pressure="lead")
    good = {"questions": [
        {"id": "Q1", "sections": ["permission"], "facts": ["app_optin",
                                                           "audit:events.per_event.logged_in"],
         "answerable": True},
        {"id": "Q2", "sections": [], "facts": [], "answerable": False,
         "reason": "the Reports API has one opted_in flag"}], "depth": depth}
    ck(check_plan(good, qs, facts, audit) == [], f"a good plan passes "
       f"({check_plan(good, qs, facts, audit)})")
    ck(check_plan({}, qs, facts, audit), "no plan fails")

    def bad(mutate, expect):
        p = json.loads(json.dumps(good))
        mutate(p)
        got = check_plan(p, qs, facts, audit)
        ck(any(expect in g for g in got), f"expected '{expect}' in {got}")

    bad(lambda p: p["questions"].pop(), "Q2 from the brief")
    bad(lambda p: p["questions"].append({"id": "Q9", "answerable": False, "reason": "x"}),
        "Q9 is in focus_plan.json but not in the brief")
    bad(lambda p: p["depth"].update(nonsense="lead"), "not a canonical section key")
    bad(lambda p: p["depth"].update(permission="standard"), "is not 'lead'")
    bad(lambda p: p["depth"].pop("events"), "mandatory section 'events' has no depth")
    bad(lambda p: p["depth"].update(exec_summary="condensed"), "cannot be condensed")
    bad(lambda p: p["questions"][0]["facts"].append("made_up"), "fact 'made_up'")
    bad(lambda p: p["questions"][0]["facts"].append("audit:events.nope"), "audit:events.nope")
    bad(lambda p: p["questions"][1].update(reason=""), "no reason given")

    # a question resting on a section the run will not write
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        un = unwritten_sections(tmp, {"categories": {"available": False}})
        ck("client_categories" in un and "data_foundation" in un,
           f"unreadable categories and no tagging plan leave both unwritten ({sorted(un)})")
        with open(os.path.join(tmp, "tagging_plan.json"), "w") as fh:
            fh.write("{}")
        un = unwritten_sections(tmp, {"categories": {"available": True}})
        ck(not un, f"categories readable, tagging plan present: everything is written ({un})")
    p = json.loads(json.dumps(good))
    p["questions"][0]["sections"].append("client_categories")
    p["depth"]["client_categories"] = "lead"
    got = check_plan(p, qs, facts, audit,
                     {"client_categories": "the client's categories were not readable"})
    ck(any("'client_categories' will not be written" in g for g in got),
       f"a lead section the run will not write is refused ({got})")
    ck(check_plan(p, qs, facts, audit) == [], "...and accepted when it will be written")

    ok = {"Q1": {"answer": "Selection, not permission.", "confidence": "medium",
                 "facts": ["app_optin"], "sections": ["permission"]},
          "Q2": {"answer": "Not measurable from Reports.", "confidence": "not_measurable",
                 "reason": "one opted_in flag"}}
    ck(check_answers(ok, good, facts, audit) == [], "good answers pass "
       f"({check_answers(ok, good, facts, audit)})")
    ck(check_answers(None, good, facts, audit), "missing answers.json fails")
    for mutate, expect in (
            (lambda a: a.pop("Q2"), "Q2: no answer"),
            (lambda a: a["Q1"].update(answer=""), "empty answer"),
            (lambda a: a["Q1"].update(confidence="sure"), "confidence 'sure'"),
            (lambda a: a["Q2"].update(reason=""), "not_measurable, and no reason"),
            (lambda a: a["Q2"].update(confidence="high", facts=["app_optin"]),
             "not answerable"),
            (lambda a: a["Q1"].update(facts=[]), "cites no fact")):
        a = json.loads(json.dumps(ok))
        mutate(a)
        got = check_answers(a, good, facts, audit)
        ck(any(expect in g for g in got), f"expected '{expect}' in {got}")

    ck("Q1" in depth_rule(good, "permission") and "lead" in depth_rule(good, "permission"),
       "a lead section is told which questions it answers")
    ck("condensed" in depth_rule(good, "typology"), "condensed rule")
    ck(depth_rule({}, "typology") == DEPTH_RULES["standard"], "global mode: standard")
    ck("NOT ANSWERABLE" in summary(good) and "condensed: typology" in summary(good),
       "checkpoint summary")
    print(f"focus_plan selftest: {'ok' if not fails else 'FAILED'}")
    for f in fails:
        print(f"  - {f}")
    return 1 if fails else 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["--selftest"]:
        return _selftest()
    if len(argv) != 2 or argv[0] not in ("--check", "--check-answers"):
        print(__doc__)
        return 2
    probs = run_check(argv[1], answers=argv[0] == "--check-answers")
    what = "answers" if argv[0] == "--check-answers" else "focus plan"
    if probs:
        print(f"{what}: FAIL")
        for p in probs:
            print(f"  [✗] {p}")
        return 1
    print(f"{what}: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
