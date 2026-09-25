#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Align N audits of sibling apps into one frozen `cross.json` for §3d.

    python scripts/cross_compare.py work/app_a/audit.json work/app_b/audit.json \\
        -o work/_shared/cross.json --freeze
    python scripts/cross_compare.py --selftest

Reviewing two apps of the same brand is not a rare request — a broadcaster with a news
app and a streaming app, a retailer with a shopping app and a loyalty app — and it has
been done twice by hand. Both times the comparison was assembled inside the section that
displayed it, which put the same arithmetic in two report directories and made the two
reports capable of disagreeing with each other about the same pair of numbers.

**What this refuses to do is the point.** A cross-app table invites the reader to size a
gap, and most of the gaps are not there to be sized:

  different windows      Not a comparison at all. This exits 1 rather than emit a file.

  different verticals    Two apps of one brand can sit in different benchmark cohorts —
                         a news app against Media, a shopping app against Retail. Their
                         rates are then comparable to each other as numbers and NOT as
                         performance: neither is the other's benchmark, and "app A opens
                         at twice app B" says nothing about either being good.

  different audiences    A count is a fact, but reading two counts as effort requires
                         normalising by opt-ins. The size ratio travels with the row so
                         the section cannot forget it.

  measured on one side   A metric one app reports and the other does not is not a gap of
                         zero. It is marked not-comparable with the reason.

  disqualified figures   A value listed in either audit's `contaminated_fields` is
                         refused outright: a number too wrong to publish alone does not
                         become publishable by being placed beside another one.

The output is data, not prose. §3d reads `cross.json` and writes the sentences.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import build_facts as bf              # noqa: E402

# Below this the two audiences are close enough that a count reads as a count.
_SIZE_RATIO_FLAT = 1.25


def _audience_scaled(key, temporal, unit):
    """Does this count grow with the audience, so that a gap needs normalising?

    Period volumes do: twice the opt-ins, twice the sends for the same programme. A
    snapshot audience does not need the caveat — comparing audiences IS the size
    comparison, and telling the reader to divide it by itself is noise. Nor does a
    campaign count: how many messages a team writes is an editorial decision, and 383
    against 129 is a real difference in output whatever the two audiences weigh.
    """
    return (unit == "count" and temporal == "flow"
            and not key.startswith("campaigns"))


def _kpi_map(facts):
    return {k["key"]: k for k in (facts.get("kpis") or []) if k.get("key")}


def _window(facts):
    w = facts.get("window") or {}
    return f"{w.get('start')} to {w.get('end')}"


def _vertical(facts):
    """`vertical` resolves to a dict when the benchmark book matched, a string when the
    audit only carries the label it was given."""
    v = facts.get("vertical") or {}
    if isinstance(v, str):
        return v
    return v.get("book_key") or v.get("input")


def _blocked(audits) -> dict:
    out = {}
    for a in audits:
        for row in a.get("contaminated_fields") or []:
            v = row.get("value")
            if isinstance(v, (int, float)) and not isinstance(v, bool) \
                    and row.get("kind") != "tap_count":
                out.setdefault(float(v), row)
    return out


def compare(audits, labels=None) -> dict:
    """-> cross.json payload. Raises ValueError when the windows do not match."""
    facts = [bf.build_facts(a) for a in audits]
    labels = labels or [f.get("client") or f"app{i}" for i, f in enumerate(facts)]

    windows = {_window(f) for f in facts}
    if len(windows) > 1:
        raise ValueError(
            "the audits cover different windows (" + "; ".join(sorted(windows)) + ") — "
            "there is no comparison to make. Re-collect both on the same window.")

    verticals = {_vertical(f) for f in facts}
    shared_cohort = len(verticals) == 1
    blocked = _blocked(audits)

    apps = []
    for lab, f in zip(labels, facts):
        kp = _kpi_map(f)
        apps.append({
            "label": lab,
            "client": f.get("client"),
            "project": f.get("project"),
            "app_key": f.get("app_key"),
            "region": f.get("region"),
            "vertical": _vertical(f),
            "opted_in": (kp.get("app_optin") or {}).get("value"),
        })

    sizes = [a["opted_in"] for a in apps if a["opted_in"]]
    size_ratio = (max(sizes) / min(sizes)) if len(sizes) == len(apps) and min(sizes) \
        else None

    metrics, refused = [], []
    keys = []
    for f in facts:                      # union, in the order the first audit lists them
        for k in _kpi_map(f):
            if k not in keys:
                keys.append(k)

    for key in keys:
        rows = [_kpi_map(f).get(key) for f in facts]
        present = [r for r in rows if r and r.get("value") is not None]
        sample = present[0] if present else None
        unit = (sample or {}).get("unit")
        values = {lab: (r or {}).get("value") for lab, r in zip(labels, rows)}

        bad = [(lab, v) for lab, v in values.items()
               if isinstance(v, (int, float)) and not isinstance(v, bool)
               and any(b and abs(v - b) <= abs(b) * 0.0005 for b in blocked)]
        if bad:
            entry = next(iter(blocked.values()))
            refused.append({"metric": key, "values": values,
                            "why": f"{bad[0][0]} reports a value listed in "
                                   f"contaminated_fields ({entry.get('path')})"})
            continue

        missing = [lab for lab, r in zip(labels, rows)
                   if not r or r.get("value") is None]
        row = {
            "metric": key,
            "label_en": (sample or {}).get("label_en", key),
            "label_fr": (sample or {}).get("label_fr", key),
            "unit": unit,
            "temporal": (sample or {}).get("temporal"),
            "values": values,
        }
        if missing:
            row.update(comparable=False,
                       why=f"not measured on {', '.join(missing)} — an absent metric is "
                           f"not a gap of zero")
            metrics.append(row)
            continue

        nums = [v for v in values.values()]
        lo, hi = min(nums), max(nums)
        row["ratio"] = round(hi / lo, 3) if lo else None
        if unit == "pct":
            row["gap_pp"] = round(hi - lo, 2)

        if not any(nums):
            row.update(comparable=True, as_performance=False,
                       why="both report zero — an absence on both sides, not a tie")
        elif unit in ("pct", "rate") and not shared_cohort:
            row.update(comparable=True, as_performance=False,
                       why="the two apps sit in different benchmark cohorts "
                           f"({', '.join(sorted(str(v) for v in verticals))}), so this "
                           f"compares the numbers and not the performance — neither app "
                           f"is the other's benchmark")
        elif _audience_scaled(key, row["temporal"], unit) and size_ratio \
                and size_ratio >= _SIZE_RATIO_FLAT:
            row.update(comparable=True, as_performance=False,
                       why=f"the opted-in audiences differ by x{size_ratio:.1f}, so read "
                           f"this per opt-in before reading it as effort")
        else:
            row.update(comparable=True, as_performance=True, why=None)
        metrics.append(row)

    return {
        "window": sorted(windows)[0],
        "apps": apps,
        "shared_peer_cohort": shared_cohort,
        "audience_size_ratio": round(size_ratio, 3) if size_ratio else None,
        "metrics": metrics,
        "refused": refused,
        "basis": "aligned on build_facts KPI keys, so every figure is the one its own "
                 "report publishes; nothing is recomputed here",
        "note": ("Both apps share a benchmark cohort, so a rate gap can be read as "
                 "performance." if shared_cohort else
                 "The apps sit in different benchmark cohorts. Rate gaps are numeric "
                 "only; do not rank the apps against each other."),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audits", nargs="*", help="two or more audit.json paths")
    ap.add_argument("-o", "--out", default=None, help="where to write cross.json")
    ap.add_argument("--label", action="append", default=None,
                    help="display label per audit, in the same order")
    ap.add_argument("--freeze", action="store_true",
                    help="chmod a-w the output, like the rest of wave 2")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()
    if len(args.audits) < 2:
        ap.print_help()
        return 2

    audits = [json.load(open(p, encoding="utf-8")) for p in args.audits]
    try:
        payload = compare(audits, args.label)
    except ValueError as exc:
        print(f"FAIL: {exc}")
        return 1

    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        if os.path.exists(args.out):
            os.chmod(args.out, stat.S_IRUSR | stat.S_IWUSR)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        if args.freeze:
            os.chmod(args.out, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        print(f"wrote {args.out}" + (" (frozen)" if args.freeze else ""))
    else:
        print(text)

    n_cmp = sum(1 for m in payload["metrics"] if m.get("comparable"))
    n_perf = sum(1 for m in payload["metrics"] if m.get("as_performance"))
    print(f"  {len(payload['apps'])} apps over {payload['window']}; "
          f"{n_cmp}/{len(payload['metrics'])} metrics comparable, {n_perf} of those as "
          f"performance; {len(payload['refused'])} refused")
    return 0


# ---------------------------------------------------------------------------
# selftest
# ---------------------------------------------------------------------------
def _audit(client, window, vertical, optin, open_rate, sends, extra=None):
    a = {
        "meta": {"client": client, "project": f"{client} PROD", "app_key": "k" * 22,
                 "region": "eu", "period": window},
        "benchmarks": {"vertical": {"key": vertical, "label": vertical}},
        "devices": {"app_optin": optin, "total": optin * 2},
        "usage": {"current": {"push_sends": sends, "open_rate": open_rate}},
    }
    if extra:
        a.update(extra)
    return a


def _selftest() -> int:
    fails = []

    def ck(cond, label):
        if not cond:
            fails.append(label)

    w = "2026-08-11 to 2026-09-09"
    a = _audit("News App", w, "media", 176_618, 24.82, 48_316_323)
    b = _audit("Play App", w, "media", 236_237, 1.23, 381_080)

    out = compare([a, b], ["News", "Play"])
    ck(out["window"] == w, "the shared window is carried through")
    ck(out["shared_peer_cohort"] is True, "one cohort is recognised as shared")
    ck(round(out["audience_size_ratio"], 2) == 1.34, "the audience ratio is measured")
    by = {m["metric"]: m for m in out["metrics"]}

    ck(by["open_rate"]["as_performance"] is True,
       "inside one cohort a rate gap may be read as performance")
    ck(by["open_rate"]["gap_pp"] == 23.59, "the rate gap is stated in points")
    ck(by["push_sends"]["as_performance"] is False,
       "a volume gap between differently sized audiences is not performance")
    ck("per opt-in" in by["push_sends"]["why"], "and it says how to read it instead")
    ck("per opt-in" not in (by["app_optin"]["why"] or ""),
       "the audiences themselves do not carry an instruction to divide by themselves")

    # both sides at zero is an absence, not a tie
    z1 = _audit("A", w, "media", 100_000, 10.0, 0)
    z2 = _audit("B", w, "media", 100_000, 10.0, 0)
    m = {x["metric"]: x for x in compare([z1, z2], ["A", "B"])["metrics"]}
    ck(m["push_sends"]["as_performance"] is False
       and "absence on both sides" in m["push_sends"]["why"],
       "two zeros are reported as an absence rather than as agreement")

    # different cohorts: still comparable as numbers, never as performance
    c = _audit("Shop App", w, "retail", 200_000, 12.0, 900_000)
    out2 = compare([a, c], ["News", "Shop"])
    ck(out2["shared_peer_cohort"] is False, "two cohorts are recognised as different")
    m = {x["metric"]: x for x in out2["metrics"]}["open_rate"]
    ck(m["comparable"] and m["as_performance"] is False,
       "a cross-cohort rate gap is a number and not a ranking")
    ck("benchmark cohort" in m["why"], "and the reason names the cohorts")

    # a metric one side does not report is not a gap of zero
    d = _audit("Play App", w, "media", 236_237, None, 381_080)
    m = {x["metric"]: x for x in compare([a, d], ["News", "Play"])["metrics"]}
    ck(m["open_rate"]["comparable"] is False and "not measured" in m["open_rate"]["why"],
       "an unmeasured metric is refused with its reason")

    # a disqualified counter does not become publishable beside another one
    e = _audit("News App", w, "media", 176_618, 24.82, 65_690_965, extra={
        "contaminated_fields": [{"path": "inventory_stats.by_channel.push.sends",
                                 "value": 65_690_965, "kind": "responses_list"}]})
    out3 = compare([e, b], ["News", "Play"])
    ck(any(r["metric"] == "push_sends" for r in out3["refused"]),
       "a contaminated value is refused rather than compared")

    # different windows are not a comparison
    f = _audit("Play App", "2026-07-01 to 2026-07-30", "media", 236_237, 1.23, 381_080)
    try:
        compare([a, f], ["News", "Play"])
        fails.append("mismatched windows must raise")
    except ValueError as exc:
        ck("different windows" in str(exc), "and the error says why")

    print(f"cross_compare selftest: {'ok' if not fails else 'FAILED'} "
          f"({len(fails)} failure(s))")
    for x in fails:
        print(f"  - {x}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
