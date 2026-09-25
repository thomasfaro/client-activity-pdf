#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate a `brand.json` against `brand_schema.json`, and say what to fix.

Wave 0 is a background agent whose output nothing blocks on, which is exactly why a bad
`brand.json` is expensive: it surfaces in wave 4, inside a section that quotes it, long
after the agent that wrote it is gone. The one thing that catches it early is a check the
agent runs on itself before replying.

The check is deliberately narrow. It verifies the *shape* — the keys the report and
`goal_candidates.resolve_context()` read, the caps the layout imposes, and that sources
exist. It cannot verify that a claim is true; only citing it can, which is why every
claim-bearing field carries a source and why a field nobody could fill belongs in
`not_found` rather than being absent.

    python3 check_brand.py work/<client>/brand.json

Exit status is 1 on a finding, so the agent can gate its own reply on it.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA = os.path.join(HERE, "brand_schema.json")

# Fields that carry a claim about the business rather than a fact about the app or the
# file. These are the ones a client will hear read aloud, so an empty `sources` ledger
# alongside any of them is a finding.
_CLAIM_FIELDS = ("business_model", "description", "app_role", "conversion_meaning",
                 "loyalty", "seasonality", "priorities", "news", "competitors")


def _words(v) -> int:
    return len(str(v or "").split())


def check(brand: dict, schema: dict) -> list:
    """Return a list of human-readable findings; empty means the file is good."""
    fails = []
    fields = schema["fields"]

    unknown = sorted(set(brand) - set(fields))
    if unknown:
        # A key the schema does not know is either a typo on a key something reads, or a
        # widened brief. Both are worth a line: nothing downstream will ever look at it.
        fails.append(f"unknown key(s) {', '.join(unknown)}: nothing reads them. Either "
                     f"correct the spelling or drop the content — the orchestrator "
                     f"decides whether the schema grows, not the researcher.")

    for key in schema["required"]:
        val = brand.get(key)
        if val is None or (isinstance(val, (str, list)) and not val):
            fails.append(f"{key}: required and empty. If you looked and could not find it, "
                         f"say so in `not_found` rather than leaving it blank.")

    for key, spec in fields.items():
        if key not in brand or brand[key] is None:
            continue
        val = brand[key]
        typ = spec.get("type")

        if typ == "str":
            if not isinstance(val, str):
                fails.append(f"{key}: expected a string, got {type(val).__name__}.")
                continue
            if spec.get("max_len") and len(val) > spec["max_len"]:
                fails.append(f"{key}: {len(val)} characters, cap is {spec['max_len']} "
                             f"({spec.get('_', '')}).")
            if spec.get("max_words") and _words(val) > spec["max_words"]:
                fails.append(f"{key}: {_words(val)} words, cap is {spec['max_words']}. "
                             f"The layout truncates past that, so the extra words have "
                             f"no reader.")
            if spec.get("enum") and val not in spec["enum"]:
                fails.append(f"{key}: {val!r} is not one of {', '.join(spec['enum'])}.")

        elif typ == "list":
            if not isinstance(val, list):
                fails.append(f"{key}: expected a list, got {type(val).__name__}.")
                continue
            if spec.get("max_items") and len(val) > spec["max_items"]:
                fails.append(f"{key}: {len(val)} items, cap is {spec['max_items']}. The "
                             f"report renders the first {spec['max_items']} and drops "
                             f"the rest silently.")
            if spec.get("items") == "obj":
                for n, it in enumerate(val, 1):
                    missing = [k for k in spec.get("item_keys", []) if not (it or {}).get(k)]
                    if missing:
                        fails.append(f"{key}[{n}]: missing {', '.join(missing)}.")
            else:
                cap = spec.get("max_words_each")
                for n, it in enumerate(val, 1):
                    if not isinstance(it, str):
                        fails.append(f"{key}[{n}]: expected a string.")
                    elif cap and _words(it) > cap:
                        fails.append(f"{key}[{n}]: {_words(it)} words, cap is {cap}.")

    # Sourcing. One ledger for the whole file rather than a source per key: the budget is
    # twelve sources for the whole run, so demanding one per field would demand a research
    # pass the budget does not fund.
    claims = [k for k in _CLAIM_FIELDS if brand.get(k)]
    if claims and not brand.get("sources"):
        fails.append(f"sources: empty, while {', '.join(claims)} make claims about the "
                     f"business. An unsourced claim about a client's strategy is worse "
                     f"than no claim — it will be read out loud in a client meeting.")

    if len(brand.get("sources") or []) > schema["budget"]["max_sources"]:
        fails.append(f"sources: {len(brand['sources'])} kept, budget is "
                     f"{schema['budget']['max_sources']}. Past that you were researching "
                     f"the brand rather than the review.")

    return fails


def main(argv) -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        print("usage: check_brand.py work/<client>/brand.json", file=sys.stderr)
        return 2
    path = argv[1]
    try:
        with open(path, encoding="utf-8") as fh:
            brand = json.load(fh)
    except FileNotFoundError:
        print(f"[brand] no file at {path}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"[brand] {path} is not valid JSON: {exc}", file=sys.stderr)
        return 1

    with open(SCHEMA, encoding="utf-8") as fh:
        schema = json.load(fh)

    fails = check(brand, schema)
    if fails:
        for f in fails:
            print(f"  \u2717 {f}", file=sys.stderr)
        print(f"\n{len(fails)} finding(s) in {path}.", file=sys.stderr)
        return 1

    filled = sum(1 for k in schema["fields"] if brand.get(k))
    print(f"[brand] ok \u2014 {filled}/{len(schema['fields'])} fields filled, "
          f"{len(brand.get('sources') or [])} source(s), "
          f"{len(brand.get('not_found') or [])} in not_found")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
