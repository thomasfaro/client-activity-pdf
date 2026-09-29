#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Before / after: is the orchestrated report at least as good as the hand-run one?

    python scripts/compare_reports.py work/<client>/baseline/report.html work/<client>/report.html
    python scripts/compare_reports.py A.html B.html --json
    python scripts/compare_reports.py --selftest

Each report is read with the files that sit next to it (facts.json, verdicts.json,
run_state.json), so keep a baseline as a directory copy, not a lone HTML file:

    mkdir -p work/<client>/baseline
    cp work/<client>/{report.html,facts.json,verdicts.json,run_state.json} work/<client>/baseline/

When both sides were produced by run_review.py, their run_state.json adds what the
run cost: tokens, agent time, tokens per role, and which models differ. Those rows are
information, never a regression: a cheaper run is only a win if the rows above hold.
No dollar figure: the SDK prices cloud agents only, and run_review.py runs local ones.

Everything measured here is mechanical and uses the gate's own parsers, so "a KPI
disagrees with facts" means exactly what it means in verify_report.py:

| metric | better is |
|---|---|
| canonical sections present | more (the full spine) |
| gate ✗ / ! lines | fewer |
| KPI cards disagreeing with facts.json | fewer (0) |
| one KPI shown with two different values | fewer (0) — the parallel-writing failure |
| verdict conflicts in verdicts.json | fewer (0) |
| words per section, and their spread | similar — a big drop is a thinner report |

What it cannot measure is whether the argument is right. That is the human read the
protocol in orchestration.md still requires before the default changes.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import canonical_sections as cs  # noqa: E402
import verdict_ledger as vl      # noqa: E402
import verify_report as vr       # noqa: E402


def _body(html):
    return re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.I | re.S)


def _words(chunk):
    text = re.sub(r"<script[^>]*>.*?</script>", " ", chunk, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return len(re.findall(r"\w+", text))


def kpi_variants(body, facts):
    """facts KPI key → distinct values it is shown with, where there are two or more."""
    matchers = []
    for k in (facts or {}).get("kpis") or []:
        for pat in k.get("label_patterns") or []:
            try:
                matchers.append((re.compile(pat), k["key"]))
            except (re.error, KeyError):
                continue
    shown = {}
    for rx in vr._KPI_CARD_RE:
        for mt in rx.finditer(body):
            label = vr._norm_label(mt.group("label"))
            key = next((kk for pat, kk in matchers if pat.fullmatch(label)), None)
            if key:
                shown.setdefault(key, set()).add(vr._plain(mt.group("val")).strip())
    return {k: sorted(v) for k, v in shown.items() if len(v) > 1}


def gate_counts(path):
    proc = subprocess.run([sys.executable, os.path.join(HERE, "verify_report.py"), path],
                          capture_output=True, text=True)
    lines = [l.strip() for l in (proc.stdout + proc.stderr).splitlines()]
    return {"exit": proc.returncode,
            "fail": sum(1 for l in lines if l.startswith("[✗]")),
            "advisory": sum(1 for l in lines if l.startswith("[!]"))}


def run_cost(here):
    """run_state.json beside the report → tokens, agent time, per role, models; or None."""
    p = os.path.join(here, "run_state.json")
    if not os.path.isfile(p):
        return None
    state = json.load(open(p, encoding="utf-8"))
    usage = state.get("usage") or {}
    if not usage:
        return None
    by_role = {}
    for u in usage.values():
        r = by_role.setdefault(u.get("role") or "?", {"tokens": 0, "ms": 0})
        r["tokens"] += u.get("total", 0)
        r["ms"] += u.get("ms", 0)
    return {"tokens": sum(r["tokens"] for r in by_role.values()),
            "ms": sum(r["ms"] for r in by_role.values()),
            "by_role": by_role, "models": state.get("models") or {}}


def measure(path, run_gate=True):
    html = open(path, encoding="utf-8").read()
    body = _body(html)
    here = os.path.dirname(os.path.abspath(path))
    facts = vr._sibling_facts(path)
    words, present = {}, []
    for s in cs.CANONICAL_SECTIONS:
        chunk = vr._one_section(body, s["id"])
        if chunk:
            present.append(s["key"])
            words[s["key"]] = _words(chunk)
    vpath = os.path.join(here, "verdicts.json")
    conflicts = None
    if os.path.isfile(vpath):
        conflicts = len(vl.conflicts(json.load(open(vpath, encoding="utf-8"))["records"]))
    wv = list(words.values())
    return {
        "path": path,
        "sections": present,
        "kpi_vs_facts": len(vr._facts_coherence(body, facts)) if facts else None,
        "kpi_variants": kpi_variants(body, facts),
        "verdict_conflicts": conflicts,
        "words_total": sum(wv),
        "words_median": int(statistics.median(wv)) if wv else 0,
        "words_by_section": words,
        "gate": gate_counts(path) if run_gate else None,
        "cost": run_cost(here),
    }


def compare(a, b):
    rows = []

    def row(name, va, vb, better):
        if va is None or vb is None:
            verdict = "n/a"
        elif va == vb:
            verdict = "="
        else:
            verdict = "better" if better(va, vb) else "worse"
        rows.append((name, va, vb, verdict))

    lower = lambda x, y: y < x       # noqa: E731
    row("canonical sections", len(a["sections"]), len(b["sections"]), lambda x, y: y > x)
    if a["gate"] and b["gate"]:
        row("gate ✗", a["gate"]["fail"], b["gate"]["fail"], lower)
        row("gate !", a["gate"]["advisory"], b["gate"]["advisory"], lower)
    row("KPI cards ≠ facts", a["kpi_vs_facts"], b["kpi_vs_facts"], lower)
    row("KPIs shown two ways", len(a["kpi_variants"]), len(b["kpi_variants"]), lower)
    row("verdict conflicts", a["verdict_conflicts"], b["verdict_conflicts"], lower)
    # Length is not better either way; flag only a drop large enough to mean thinner.
    ta, tb = a["words_total"], b["words_total"]
    rows.append(("words (total)", ta, tb,
                 "worse" if ta and tb < 0.8 * ta else ("=" if ta == tb else "ok")))
    thinner = sorted(k for k, n in a["words_by_section"].items()
                     if n >= 80 and b["words_by_section"].get(k, 0) < 0.6 * n)
    lost = sorted(set(a["sections"]) - set(b["sections"]))
    ca, cb = a.get("cost"), b.get("cost")
    if ca or cb:
        def cost_row(name, fa):
            rows.append((name, fa(ca) if ca else None, fa(cb) if cb else None, "info"))
        cost_row("tokens (total)", lambda c: c["tokens"])
        cost_row("agent time (min)", lambda c: round(c["ms"] / 60000, 1))
        for role in sorted(set((ca or {}).get("by_role", {})) | set((cb or {}).get("by_role", {}))):
            cost_row(f"tokens · {role}", lambda c, r=role: c["by_role"].get(r, {}).get("tokens"))
        ma, mb = (ca or {}).get("models", {}), (cb or {}).get("models", {})
        for role in sorted(set(ma) | set(mb)):
            if ma.get(role) != mb.get(role):
                rows.append((f"model · {role}", ma.get(role), mb.get(role), "info"))
    return {"rows": rows, "thinner": thinner, "lost_sections": lost,
            "kpi_variants_after": b["kpi_variants"]}


def render(result):
    out = ["| metric | before | after | |", "|---|---|---|---|"]
    out += [f"| {n} | {va} | {vb} | {v} |" for n, va, vb, v in result["rows"]]
    if result["lost_sections"]:
        out.append(f"\nSections lost: {', '.join(result['lost_sections'])}")
    if result["thinner"]:
        out.append(f"\nSections at least 40% shorter: {', '.join(result['thinner'])}")
    for k, vals in result["kpi_variants_after"].items():
        out.append(f"\n`{k}` is shown as {' / '.join(vals)} in the after report")
    worse = [r[0] for r in result["rows"] if r[3] == "worse"]
    out.append("\nVerdict: " + ("not yet — worse on " + ", ".join(worse) if worse
                                else "no mechanical regression; the human read decides"))
    return "\n".join(out)


def _selftest():
    import tempfile
    fails = []

    def ck(cond, label):
        if not cond:
            fails.append(label)

    facts = {"kpis": [{"key": "open_rate", "label_patterns": [r"open rate"],
                       "value": 3.4, "unit": "pct"}]}
    card = '<div class="ir-kpi-val">{}</div><div class="ir-kpi-label">Open rate</div>'
    ck(kpi_variants(card.format("3.4%") + card.format("3.5%"), facts) ==
       {"open_rate": ["3.4%", "3.5%"]}, "one KPI shown two ways is found")
    ck(not kpi_variants(card.format("3.4%") * 2, facts), "the same value twice is fine")

    with tempfile.TemporaryDirectory() as d:
        paths = []
        for name, val, extra in (("a", "3.4%", "one two three " * 50),
                                 ("b", "3.5%", "one")):
            os.makedirs(os.path.join(d, name))
            p = os.path.join(d, name, "report.html")
            html = (f'<section id="summary">{card.format("3.4%")}{card.format(val)}'
                    f'<p>{extra}</p></section>')
            open(p, "w").write(html)
            json.dump(facts, open(os.path.join(d, name, "facts.json"), "w"))
            json.dump({"models": {"section": "m-" + name, "brand": "w"},
                       "usage": {"engagement": {"role": "section", "total": 900 if name == "a"
                                                else 400, "ms": 120000},
                                 "brand": {"role": "brand", "total": 100, "ms": 60000}}},
                      open(os.path.join(d, name, "run_state.json"), "w"))
            paths.append(p)
        res = compare(measure(paths[0], run_gate=False), measure(paths[1], run_gate=False))
        verdicts = {r[0]: r[3] for r in res["rows"]}
        rows = {r[0]: r for r in res["rows"]}
        ck(rows["tokens (total)"][1:] == (1000, 500, "info"), "tokens come from run_state.json")
        ck(rows["agent time (min)"][1:3] == (3.0, 3.0), "agent time sums the sessions")
        ck(rows["tokens · section"][1:3] == (900, 400), "tokens are split per role")
        ck(rows["model · section"][1:3] == ("m-a", "m-b") and "model · brand" not in rows,
           "only the models that differ are listed")
        ck("| tokens (total) | 1000 | 500 | info |" in render(res), "cost rows are rendered")
        ck(verdicts["KPIs shown two ways"] == "worse", "a new two-way KPI is a regression")
        ck(verdicts["words (total)"] == "worse", "a much shorter report is flagged")
        ck("exec_summary" in res["thinner"], "the thinner section is named")
        ck("not yet" in render(res), "the verdict says not yet")
    print(f"compare_reports selftest: {'ok' if not fails else 'FAILED'}")
    for f in fails:
        print(f"  - {f}")
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("before", nargs="?")
    ap.add_argument("after", nargs="?")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-gate", action="store_true", help="skip running verify_report")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()
    if not (args.before and args.after):
        ap.print_help()
        return 2
    a = measure(args.before, not args.no_gate)
    b = measure(args.after, not args.no_gate)
    res = compare(a, b)
    if args.json:
        print(json.dumps({"before": a, "after": b, "compare": res}, ensure_ascii=False,
                         indent=1, default=list))
    else:
        print(render(res))
    return 1 if any(r[3] == "worse" for r in res["rows"]) else 0


if __name__ == "__main__":
    sys.exit(main())
