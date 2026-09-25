#!/usr/bin/env python3
"""Turn the collection manifest into a statement of what the report cannot claim.

Every stage of a collection already records how it went — `ok`, `partial` with a list of
what it cut, or `FAILED` with the exception. That record then dies in `collect_manifest.json`
while the report goes on to read the surviving files and speak with one voice, as if every
figure in it rested on the same footing. A reader has no way to tell a section built on a
complete pull from one built on a stage that timed out at 40% and wrote what it had.

This module closes that gap, and it draws on two different kinds of blind spot:

  **Degraded stages** are accidents of this run — a timeout, a 502, a deadline hit. They
  vary run to run and they are read out of the manifest.

  **Structural blind spots** are permanent. The skill holds an `rpt` token and calls only
  `/api/reports/*` (SKILL.md), so journey step-level performance, A/B declarations and
  Scene-internal funnels are not "missing data" — they were never reachable, and no re-run
  will produce them. They are listed here so that page 1 says so rather than leaving a
  reader to infer completeness from silence.

The distinction matters in the banner: one invites a re-run, the other tells you not to
bother.

API:
  assess(manifest, audit=None) -> dict   # grade + degraded stages + cannot-claim lines
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from typing import List, Optional

# What a stage failing costs the *reader*, in the reader's terms. Naming the file that did
# not arrive ("responses.json missing") tells an engineer something and a client nothing;
# naming the claim that can no longer be made tells both.
#
# Each entry is a bare NOUN PHRASE, because the banner completes it two ways — "this report
# does not carry X" for a failure, "X is only partly covered" for a stage that cut itself
# short. A clause tacked on the end ("…, so no message can be ranked") reads correctly in
# the first frame and collapses in the second.
_STAGE_COST = {
    "core": ("the account's send, open, opt-in and device totals",
             "les volumes d'envois, d'ouvertures, d'opt-in et d'appareils du compte"),
    "events": ("the custom-event taxonomy and its volumes",
               "la taxonomie d'\u00e9v\u00e9nements personnalis\u00e9s et ses volumes"),
    "activity": ("the per-message activity log, from which the campaign inventory is built",
                 "le journal d'activit\u00e9 par message, dont d\u00e9coule l'inventaire "
                 "des campagnes"),
    "responses": ("per-message performance", "la performance par message"),
    "programs": ("automation programme performance",
                 "la performance des programmes d'automatisation"),
    "details": ("per-message platform splits (iOS against Android)",
                "les r\u00e9partitions par plateforme message par message (iOS / Android)"),
    "bodies": ("message creatives", "les cr\u00e9atives des messages"),
    "groupbodies": ("automation creatives",
                    "les cr\u00e9atives des programmes automatis\u00e9s"),
    "attribution": ("conversion attribution — which messages drove which events",
                    "l'attribution des conversions \u2014 quels messages ont produit quels "
                    "\u00e9v\u00e9nements"),
    "split": ("the reconciliation between the activity log and the send totals",
              "la r\u00e9conciliation entre le journal d'activit\u00e9 et les totaux d'envoi"),
    "decode": ("the decoded creative payloads (deep links, buttons)",
               "les payloads d\u00e9cod\u00e9s des cr\u00e9atives (deep links, boutons)"),
}

# Permanent, and permanent for a stated reason. Each line says what is unreachable and why,
# because "we did not measure journeys" reads like an oversight where "the Reports API does
# not expose journey steps" reads like the fact it is.
_STRUCTURAL = [
    {"key": "journeys",
     "en": "step-by-step journey performance — the Reports API exposes a programme's totals, "
           "not the conversion of each step within it",
     "fr": "la performance \u00e9tape par \u00e9tape des parcours \u2014 l'API Reports expose "
           "les totaux d'un programme, pas la conversion de chacune de ses \u00e9tapes"},
    {"key": "experiments",
     "en": "which messages were A/B tests and how variants were assigned — that lives in "
           "experiment configuration, outside the reporting scope this review holds",
     "fr": "quels messages \u00e9taient des tests A/B et comment les variantes ont \u00e9t\u00e9 "
           "assign\u00e9es \u2014 cela vit dans la configuration des exp\u00e9riences, hors du "
           "p\u00e9rim\u00e8tre de reporting de cette revue"},
    {"key": "scene_funnels",
     "en": "screen-by-screen drop-off inside a Scene — only its overall display and its "
           "resolution are reported, unless the app instruments the steps as custom events",
     "fr": "l'abandon \u00e9cran par \u00e9cran \u00e0 l'int\u00e9rieur d'une Scene \u2014 seuls "
           "son affichage global et sa r\u00e9solution sont remont\u00e9s, sauf si l'app "
           "instrumente les \u00e9tapes en \u00e9v\u00e9nements personnalis\u00e9s"},
]

_REVENUE = {
    "key": "revenue",
    "en": "revenue or basket value per message — no tracked event carries a monetary amount, "
          "so conversions are counted and never valued",
    "fr": "le chiffre d'affaires ou le panier par message \u2014 aucun \u00e9v\u00e9nement "
          "suivi ne porte de montant, les conversions sont donc compt\u00e9es et jamais "
          "valoris\u00e9es",
}


def _revenue_blind(audit: Optional[dict]) -> bool:
    """True when nothing in the account's events carries a monetary value.

    Absent an audit, returns False: the banner would rather stay silent than assert a
    blind spot it has not verified. The graded value block (\u00a7 value measurability)
    is where this is examined properly; here it only earns a line on page 1.
    """
    if not audit:
        return False
    ev = (audit.get("events") or {})
    val = ev.get("value_measurability") or ev.get("value") or {}
    if isinstance(val, dict):
        # `event_analysis.value_measurability` states this outright, and its dict carries
        # none of the older key names below — so without this line the check fell through
        # to `return False` on every account that had the graded verdict, and the revenue
        # blind spot never appeared on page 1 of the reports that needed it most.
        if isinstance(val.get("revenue_attributable"), bool):
            return not val["revenue_attributable"]
        for k in ("has_monetary", "monetary_events", "currency_events", "revenue_events"):
            v = val.get(k)
            if isinstance(v, bool):
                return not v
            if isinstance(v, (int, float)):
                return not v
            if isinstance(v, list):
                return not v
    return False


_COMPLETENESS_CLAIM = re.compile(
    r"\b100\s*%|\bevery next_page\b|\bexhaustively\b|\ball pages\b|\bcomplete\b", re.I)


def contradictions(manifest: Optional[dict]) -> List[str]:
    """Stages whose stated coverage disagrees with their own status.

    A stage writes its `coverage` line before it knows whether it will finish, so the
    line is an intention. On a truncated stage the two sit side by side and the prose
    wins, because prose is what gets read: one manifest carried
    ``"coverage": "100% of 30d window (every next_page followed)"`` next to
    ``"status": "partial"`` and a `truncated` block naming the deadline that stopped it.
    The truncation went unnoticed for a full collection pass, and the message sample the
    next stages ranked was drawn from 9% of the window — excluding the largest sending
    day of the month.

    `collect.py` now rewrites the line centrally when a stage is cut, so this should
    never fire on a fresh run. It stays because the failure was silent for a month and a
    check that only ever passes is the cheapest kind to keep.
    """
    out = []
    for name, info in ((manifest or {}).get("stages") or {}).items():
        info = info or {}
        status = str(info.get("status") or "")
        cov = str(info.get("coverage") or "")
        cut = bool(info.get("truncated")) or status == "partial"
        if cut and cov and _COMPLETENESS_CLAIM.search(cov):
            out.append(f"stage `{name}` is {status or 'truncated'} but its coverage "
                       f"reads \u201c{cov[:80]}\u201d")
        if info.get("complete") is True and cut:
            out.append(f"stage `{name}` is marked complete and truncated at once")
    return out


def assess(manifest: Optional[dict], audit: Optional[dict] = None) -> dict:
    """Grade this run's coverage and list, in plain words, what it cannot support.

    `full` means every stage that ran returned complete; `partial` means at least one cut
    itself short but wrote usable data; `degraded` means at least one stage failed outright
    and the sections that depend on it are standing on nothing.

    A cached skip is not a degradation — the data is there, from an earlier run. Grading it
    as one would make every re-run look worse than the first, which is the opposite of true.
    """
    stages = ((manifest or {}).get("stages") or {})
    failed, partial = [], []
    for name, info in stages.items():
        st = str((info or {}).get("status") or "")
        if st == "FAILED":
            failed.append({"stage": name, "why": (info or {}).get("error") or "",
                           "cost": _STAGE_COST.get(name)})
        elif st == "partial":
            cuts = (info or {}).get("truncated") or []
            partial.append({"stage": name, "cuts": cuts,
                            "why": "; ".join(sorted({str(c.get("why")) for c in cuts})),
                            "cost": _STAGE_COST.get(name)})
    grade = "degraded" if failed else ("partial" if partial else "full")
    blind = list(_STRUCTURAL) + ([_REVENUE] if _revenue_blind(audit) else [])
    return {
        "grade": grade,
        "stages_total": len(stages),
        "stages_ok": sum(1 for i in stages.values()
                         if str((i or {}).get("status") or "").startswith(("ok", "skipped"))),
        "failed": failed,
        "partial": partial,
        "structural": blind,
        "window": ((manifest or {}).get("window") or {}).get("current"),
        "settling": ((manifest or {}).get("window") or {}).get("settling") or {},
    }


if __name__ == "__main__":
    # A clean run: no accident to report, and the three permanent blind spots still stated.
    clean = {"stages": {"core": {"status": "ok"}, "probe": {"status": "skipped (cached)"},
                        "events": {"status": "ok"}},
             "window": {"current": ["2026-08-01", "2026-08-31"]}}
    c = assess(clean)
    assert c["grade"] == "full" and c["stages_ok"] == 3, c
    assert len(c["structural"]) == 3 and not c["failed"]

    # A stage that cut itself short is `partial`, and the cost is named in reader's terms.
    cut = json.loads(json.dumps(clean))
    cut["stages"]["responses"] = {"status": "partial",
                                  "truncated": [{"what": "perpush", "collected": 4000,
                                                 "why": "stage deadline"}]}
    c = assess(cut)
    assert c["grade"] == "partial" and c["partial"][0]["stage"] == "responses"
    # Named in the reader's terms, and as a bare noun phrase: the banner completes it two
    # different ways, so a trailing clause reads in one frame and collapses in the other.
    for en, fr in _STAGE_COST.values():
        for s in (en, fr):
            assert not s.endswith("."), s
            assert " so " not in s and " donc " not in s, f"clause in a noun phrase: {s}"
    assert "performance" in c["partial"][0]["cost"][0]

    # An outright failure outranks a cut: `degraded`.
    cut["stages"]["attribution"] = {"status": "FAILED", "error": "HTTPError: 502"}
    c = assess(cut)
    assert c["grade"] == "degraded" and c["failed"][0]["stage"] == "attribution"

    # Revenue is asserted blind only on evidence, never by default.
    assert not _revenue_blind(None) and not _revenue_blind({})
    assert _revenue_blind({"events": {"value_measurability": {"monetary_events": []}}})
    assert not _revenue_blind({"events": {"value_measurability": {"monetary_events": ["x"]}}})
    assert len(assess(clean, {"events": {"value_measurability":
                                         {"has_monetary": False}}})["structural"]) == 4
    # The shape `event_analysis.value_measurability` actually returns. It carries none of
    # the key names above, so this fell through to "not blind" on every account that had
    # the graded verdict — silently dropping the line from the reports that needed it.
    assert _revenue_blind({"events": {"value_measurability":
                                      {"grade": "counters",
                                       "revenue_attributable": False}}})
    assert not _revenue_blind({"events": {"value_measurability":
                                          {"grade": "revenue",
                                           "revenue_attributable": True}}})

    # A manifest that claims completeness on a stage it also reports as truncated. This
    # is drawn from a real manifest, and the contradiction cost a full re-collection pass.
    assert not contradictions(clean), "a clean manifest contradicts nothing"
    liar = {"stages": {"responses": {
        "status": "partial", "deadline_s": 3600,
        "coverage": "100% of 30d window (every next_page followed)",
        "truncated": [{"what": "responses pagination", "collected": "11400 pages",
                       "why": "stage deadline"}]}}}
    assert contradictions(liar), "the claim beside a partial status is caught"
    assert "responses" in contradictions(liar)[0]
    # Once collect.py rewrites the line centrally, the same run is clean again.
    honest = json.loads(json.dumps(liar))
    honest["stages"]["responses"]["coverage"] = (
        "INCOMPLETE — responses pagination stopped at 11400 pages (stage deadline)")
    assert not contradictions(honest), "the corrected line is not a contradiction"
    assert contradictions({"stages": {"x": {"status": "partial", "complete": True,
                                            "coverage": ""}}})

    # A real manifest, if one is at hand — the self-test should meet production shapes.
    # Whichever account happens to be in `work/`, never a named one: this file is tracked,
    # and a path is as much of a client name as a comment is.
    here = os.path.abspath(__file__)
    for _ in range(5):  # scripts / skill / skills / .cursor / repo root
        here = os.path.dirname(here)
    for real in sorted(glob.glob(os.path.join(here, "work", "*", "data",
                                              "collect_manifest.json")))[:1]:
        with open(real, encoding="utf-8") as fh:
            r = assess(json.load(fh))
        print(f"  live manifest: grade={r['grade']} ok={r['stages_ok']}/{r['stages_total']}")
        assert r["grade"] in ("full", "partial", "degraded")
    print("coverage self-test OK", file=sys.stderr)
