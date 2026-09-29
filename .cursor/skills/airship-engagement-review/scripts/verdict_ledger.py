#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The verdict ledger — what each section concluded, checked for contradictions.

    python scripts/verdict_ledger.py work/<client>            # merge + check, exit 1 on conflict
    python scripts/verdict_ledger.py work/<client> --json     # machine-readable
    python scripts/verdict_ledger.py --selftest

Sections written by isolated agents lose the one property a single writer had for free:
someone who saw every conclusion. The report then says "reduce cadence" in §4 and "send
more" in §16, each paragraph defensible, the argument broken. The gate cannot see this —
its only cross-section check compares KPI cards to facts.json.

So every section agent also writes `work/<client>/verdicts/<key>.json`:

    {"key": "volume_pressure",
     "verdict": "Pressure sits above the peer band and opt-outs follow it.",
     "directions": {"pressure": "down"},
     "cites": {"pressure": "6.1"}}

This module merges them into `verdicts.json` and reports two kinds of conflict:

- **direction** — two sections take opposite positions (`up` vs `down`) on the same axis;
  `hold` conflicts with neither, because "keep it where it is" is compatible with a section
  that only says "do not increase".
- **citation** — two sections display the same facts.json KPI differently. That is either
  a rounding drift or a stale copy, and both read as an error to the client.

It decides nothing about who is right. A conflict goes back to the agents, or to a human.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

AXES = ("pressure", "engagement", "permission", "automation", "value", "personalisation")
DIRECTIONS = ("up", "down", "hold")


def load_records(work_dir):
    """-> (records, problems). One record per verdicts/<key>.json, validated."""
    vdir = os.path.join(work_dir, "verdicts")
    records, problems = [], []
    if not os.path.isdir(vdir):
        return records, problems
    for fn in sorted(os.listdir(vdir)):
        if not fn.endswith(".json"):
            continue
        path = os.path.join(vdir, fn)
        try:
            rec = json.load(open(path, encoding="utf-8"))
        except (OSError, ValueError) as exc:
            problems.append(f"{fn}: unreadable ({exc})")
            continue
        key = fn[:-5]
        if rec.get("key") != key:
            problems.append(f"{fn}: 'key' is {rec.get('key')!r}, expected {key!r}")
            rec["key"] = key
        if not isinstance(rec.get("verdict"), str) or not rec["verdict"].strip():
            problems.append(f"{fn}: no one-sentence 'verdict'")
        dirs = rec.get("directions") or {}
        for axis, d in list(dirs.items()):
            if axis not in AXES or d not in DIRECTIONS:
                problems.append(f"{fn}: direction {axis}={d!r} is not one of "
                                f"{'/'.join(AXES)} × {'/'.join(DIRECTIONS)}")
                dirs.pop(axis)
        rec["directions"] = dirs
        rec["cites"] = {k: str(v) for k, v in (rec.get("cites") or {}).items()}
        records.append(rec)
    return records, problems


def _canon(shown):
    """A displayed value reduced to its digits and unit, locale-neutral."""
    s = re.sub(r"[\s\u00a0\u202f\u2009]", "", str(shown)).lower()
    s = s.replace(",", ".") if re.search(r",\d{1,2}(?!\d)", s) else s.replace(",", "")
    return s


def conflicts(records):
    """-> list of {"kind", "axis"/"kpi", "sections", "detail"}."""
    out = []
    for axis in AXES:
        ups = [r["key"] for r in records if r["directions"].get(axis) == "up"]
        downs = [r["key"] for r in records if r["directions"].get(axis) == "down"]
        if ups and downs:
            out.append({"kind": "direction", "axis": axis, "sections": ups + downs,
                        "detail": f"{axis}: up in {', '.join(ups)} but down in "
                                  f"{', '.join(downs)}"})
    shown = {}
    for r in records:
        for kpi, val in r["cites"].items():
            shown.setdefault(kpi, {}).setdefault(_canon(val), []).append((r["key"], val))
    for kpi, variants in shown.items():
        if len(variants) > 1:
            parts = [f"{v[0][1]} in {', '.join(k for k, _ in v)}" for v in variants.values()]
            out.append({"kind": "citation", "kpi": kpi,
                        "sections": sorted({k for v in variants.values() for k, _ in v}),
                        "detail": f"{kpi} shown as " + " / ".join(parts)})
    return out


def merge(work_dir):
    """Write verdicts.json and return it: {"records", "problems", "conflicts"}."""
    records, problems = load_records(work_dir)
    ledger = {"records": records, "problems": problems, "conflicts": conflicts(records)}
    with open(os.path.join(work_dir, "verdicts.json"), "w", encoding="utf-8") as fh:
        json.dump(ledger, fh, ensure_ascii=False, indent=1)
    return ledger


def _selftest():
    import tempfile
    fails = []

    def ck(cond, label):
        if not cond:
            fails.append(label)

    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "verdicts"))

        def put(key, **rec):
            rec.setdefault("key", key)
            json.dump(rec, open(os.path.join(d, "verdicts", key + ".json"), "w"))

        put("volume_pressure", verdict="Too much pressure.",
            directions={"pressure": "down"}, cites={"pressure": "6.1"})
        put("recommendations", verdict="Grow the programme.",
            directions={"pressure": "up", "automation": "up"}, cites={"pressure": "6,1"})
        put("engagement", verdict="Engagement holds.", directions={"pressure": "hold"},
            cites={"open_rate": "3.4%"})
        put("exec_summary", verdict="Summary.", cites={"open_rate": "3.5%"})
        led = merge(d)
        kinds = sorted((c["kind"], c.get("axis") or c.get("kpi")) for c in led["conflicts"])
        ck(("direction", "pressure") in kinds, "up vs down on pressure is a conflict")
        ck(("citation", "pressure") not in kinds,
           "6.1 and 6,1 are the same figure in two locales, not a conflict")
        ck(("citation", "open_rate") in kinds, "3.4% vs 3.5% for one KPI is a conflict")
        ck(not any(c.get("axis") == "automation" for c in led["conflicts"]),
           "a single position on an axis is not a conflict")
        ck(os.path.isfile(os.path.join(d, "verdicts.json")), "verdicts.json is written")

        put("typology", verdict="x", directions={"cadence": "up"})
        _, probs = load_records(d)
        ck(any("cadence" in p for p in probs), "an unknown axis is reported, not trusted")
    print(f"verdict_ledger selftest: {'ok' if not fails else 'FAILED'}")
    for f in fails:
        print(f"  - {f}")
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("work_dir", nargs="?")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()
    if not args.work_dir:
        ap.print_help()
        return 2
    led = merge(args.work_dir)
    if args.json:
        print(json.dumps(led, ensure_ascii=False, indent=1))
    else:
        print(f"{len(led['records'])} verdict record(s)")
        for p in led["problems"]:
            print(f"  ! {p}")
        for c in led["conflicts"]:
            print(f"  ✗ {c['kind']}: {c['detail']}")
        if not led["conflicts"]:
            print("  no contradiction between sections")
    return 1 if led["conflicts"] else 0


if __name__ == "__main__":
    sys.exit(main())
