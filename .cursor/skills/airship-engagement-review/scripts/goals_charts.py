#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Charts for the GOALS REVIEW (light mode), derived from goals.json alone.

The full report copies `make_charts.py` per client because every account needs its
own figures. The goals review does not: it always draws the same three pictures of
the same three facts, so this ships as a REUSABLE module rather than a template to
copy. A builder calls ``build(goals, outdir)``; the CLI does the same thing from
the command line.

Three figures, each answering a question the tables can only answer slowly:

  goal_funnel_coverage       Which stages of the funnel can be measured at all —
                             from collected data, from a native signal, or not at
                             all. The blind bars ARE the commercial argument.
  goal_value_instrumentation Of the candidates that mark an intent, how many can
                             carry an amount, and how many an amount you can sum.
  goal_config_modes          How many candidates are stuck on a plain count versus
                             those that can support a frequency or a threshold.

Every figure is written twice: a PNG (print) and a Chart.js spec in specs.json
(screen), which is the pairing `report_interactive.interactive_chart` expects.

English only — the goals review is monolingual by design.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List, Optional, Sequence

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import matplotlib                                              # noqa: E402
matplotlib.use("Agg")

import airship_charts as ac                                    # noqa: E402

STAGES = ["acquisition", "activation", "consideration", "conversion",
          "loyalty", "retention"]
STAGE_LABEL = {s: s.title() for s in STAGES}

CHART_IDS = ["goal_funnel_coverage", "goal_value_instrumentation",
             "goal_config_modes"]


def _activatable(goals: dict) -> List[dict]:
    """Candidates a team could switch on today: collected or native, not excluded."""
    return [c for c in (goals.get("candidates") or [])
            if c.get("family") in ("collected", "native") and not c.get("exclude")]


# --------------------------------------------------------------------------- #
# 1. Funnel coverage — the figure that carries the argument
# --------------------------------------------------------------------------- #
def funnel_coverage(goals: dict, png: str) -> Optional[dict]:
    """Stacked bars per funnel stage: collected · native · not measurable.

    A stage with a zero bar on both measurable series is one no goal can watch, so
    the gap count is drawn alongside rather than in a footnote: the reader sees the
    hole and its size in the same glance.
    """
    cov = (goals.get("priorities") or {}).get("coverage") or {}
    stages = [s for s in STAGES if s in cov]
    if not stages:
        return None
    labels = [STAGE_LABEL[s] for s in stages]
    collected = [len((cov[s] or {}).get("collected") or []) for s in stages]
    native = [len((cov[s] or {}).get("native") or []) for s in stages]
    gaps = [len((cov[s] or {}).get("gaps") or []) for s in stages]
    series = {"Collected by the client": collected,
              "Native Airship signal": native,
              "Not tracked (gap)": gaps}
    colors = [ac.BLUE, ac.MINT, ac.GREY]
    ac.stacked_bars(labels, series, png, title="Goal coverage by funnel stage",
                    colors=colors, figsize=(11, 3.8))
    spec = ac.spec_grouped_bars(labels, series, colors=colors, stacked=True)
    spec["options"]["plugins"]["legend"]["position"] = "top"
    return spec


# --------------------------------------------------------------------------- #
# 2. Value instrumentation on the candidates that mark intent
# --------------------------------------------------------------------------- #
def value_instrumentation(goals: dict, png: str) -> Optional[dict]:
    """How far each intent-bearing stage is from a goal that can carry revenue.

    Four states, and the distance between the top two is the whole point: an amount
    without a currency property cannot be summed across markets, so it is counted
    separately rather than folded into "has an amount".
    """
    rows = [c for c in _activatable(goals)
            if c.get("kind") == "custom_event"
            and c.get("funnel_stage") in ("consideration", "conversion", "loyalty")]
    if not rows:
        return None
    stages = [s for s in ("consideration", "conversion", "loyalty")
              if any(c.get("funnel_stage") == s for c in rows)]
    labels = [STAGE_LABEL[s] for s in stages]

    def _bucket(c: dict) -> str:
        if c.get("carries_amount") and c.get("currency_property"):
            return "Amount + currency"
        if c.get("carries_amount"):
            return "Amount, no currency"
        if c.get("has_value"):
            return "Counter only"
        return "No value at all"

    order = ["Amount + currency", "Amount, no currency", "Counter only", "No value at all"]
    series: Dict[str, List[int]] = {k: [] for k in order}
    for s in stages:
        here = [c for c in rows if c.get("funnel_stage") == s]
        for k in order:
            series[k].append(sum(1 for c in here if _bucket(c) == k))
    colors = [ac.MINT, ac.SKY, ac.GREY, ac.RED]
    ac.stacked_bars(labels, series, png, colors=colors,
                    title="Value instrumentation on intent-bearing events",
                    figsize=(11, 3.4), legend_ncol=2)
    return ac.spec_grouped_bars(labels, series, colors=colors, stacked=True)


# --------------------------------------------------------------------------- #
# 3. Which configuration modes are actually open
# --------------------------------------------------------------------------- #
def config_modes(goals: dict, png: str) -> Optional[dict]:
    """Candidates by the RICHEST mode they support, not by every mode they allow.

    Counting each candidate once, at its ceiling, is what makes the slices mean
    something: "how many goals could express a threshold" rather than "how many
    times the word count appears".
    """
    rows = _activatable(goals)
    if not rows:
        return None
    buckets = {"Threshold on a number": 0, "Frequency over a period": 0,
               "Count only": 0}
    for c in rows:
        modes = c.get("config_modes") or ["count"]
        if "numeric_property" in modes:
            buckets["Threshold on a number"] += 1
        elif "frequency" in modes:
            buckets["Frequency over a period"] += 1
        else:
            buckets["Count only"] += 1
    labels = [k for k, v in buckets.items() if v]
    values = [buckets[k] for k in labels]
    colors = [ac.INDIGO, ac.BLUE, ac.LIGHTBLUE][:len(labels)]
    ac.donut(labels, values, png, colors=colors, center=str(sum(values)),
             title="Configuration modes available across candidates")
    return ac.spec_donut(labels, values, colors=colors,
                         center=f"{sum(values)} candidates")


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def build(goals: dict, outdir: str, quiet: bool = False) -> dict:
    """Write every figure into ``outdir/charts`` and return the specs dict.

    A figure with nothing to draw is skipped rather than emitted empty — an axis with
    no bars reads as "the value is zero", which is a different claim from "this
    account has no data of that kind".
    """
    charts = os.path.join(outdir, "charts")
    os.makedirs(charts, exist_ok=True)
    specs: Dict[str, dict] = {}
    builders = (
        ("goal_funnel_coverage", funnel_coverage),
        ("goal_value_instrumentation", value_instrumentation),
        ("goal_config_modes", config_modes),
    )
    for cid, fn in builders:
        spec = fn(goals, os.path.join(charts, f"{cid}.png"))
        if spec:
            specs[cid] = spec
        elif not quiet:
            print(f"[charts] {cid}: nothing to draw — skipped")
    with open(os.path.join(outdir, "specs.json"), "w", encoding="utf-8") as fh:
        json.dump(specs, fh, ensure_ascii=False, indent=1)
    if not quiet:
        print(f"[charts] {len(specs)} figure(s) -> {charts} + specs.json")
    return specs


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("goals", help="path to goals.json (output of goal_candidates.py)")
    ap.add_argument("-o", "--outdir", default=None,
                    help="output directory (default: the goals.json directory)")
    args = ap.parse_args(argv)
    goals = json.load(open(args.goals, encoding="utf-8"))
    outdir = args.outdir or os.path.dirname(os.path.abspath(args.goals))
    build(goals, outdir)
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        import tempfile
        demo = {
            "candidates": [
                {"name": "purchased", "family": "collected", "kind": "custom_event",
                 "funnel_stage": "conversion", "total": 22613, "carries_amount": True,
                 "currency_property": None, "has_value": True,
                 "config_modes": ["count", "frequency", "numeric_property"],
                 "recommended_config": {"mode": "count"}},
                {"name": "added_to_cart", "family": "collected", "kind": "custom_event",
                 "funnel_stage": "consideration", "total": 221193, "carries_amount": True,
                 "currency_property": "currency", "has_value": True,
                 "config_modes": ["count", "frequency"],
                 "recommended_config": {"mode": "count"}},
                {"name": "App open", "family": "native", "kind": "native_signal",
                 "funnel_stage": "retention", "total": None,
                 "config_modes": ["count", "frequency"],
                 "recommended_config": {"mode": "frequency", "period": "daily"}},
                {"name": "device", "family": "collected", "kind": "tag",
                 "funnel_stage": "loyalty", "total": 9, "exclude": True,
                 "config_modes": ["count"], "recommended_config": {"mode": "count"}},
            ],
            "priorities": {"coverage": {
                "acquisition": {"collected": [], "native": ["Channel registration"], "gaps": []},
                "conversion": {"collected": ["purchased"], "native": [], "gaps": []},
                "loyalty": {"collected": [], "native": [], "gaps": ["starred_product"]},
            }},
        }
        tmp = tempfile.mkdtemp()
        out = build(demo, tmp, quiet=True)
        assert set(out) == set(CHART_IDS), sorted(out)
        for cid in CHART_IDS:
            p = os.path.join(tmp, "charts", f"{cid}.png")
            assert os.path.getsize(p) > 1000, cid
        # the excluded tag must not be counted anywhere
        modes = out["goal_config_modes"]["data"]["datasets"][0]["data"]
        assert sum(modes) == 3, modes
        # the blind loyalty stage still gets a row, with its gap drawn
        cov = out["goal_funnel_coverage"]["data"]
        assert "Loyalty" in cov["labels"]
        gi = cov["labels"].index("Loyalty")
        assert cov["datasets"][2]["data"][gi] == 1
        # graceful degradation: an audit with nothing activatable draws nothing
        empty = build({"candidates": [], "priorities": {}}, tempfile.mkdtemp(), quiet=True)
        assert empty == {}, empty
        print("goals_charts self-test OK")
        sys.exit(0)
    sys.exit(main())
