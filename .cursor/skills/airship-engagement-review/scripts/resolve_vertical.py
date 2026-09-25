"""Resolve a client's industry to a benchmark vertical — reproducibly.

`benchmarks.json` carries an `aliases` list per vertical, but nothing read it: the
vertical was picked by hand each time. Two analysts could benchmark the same telecom
against different peer sets and neither choice would be written down. This module
makes the mapping mechanical and, crucially, makes it **state when it is a proxy**
so the report can disclose it.

    from resolve_vertical import resolve
    r = resolve("telecom operator")
    r["key"]      -> "utility_productivity"
    r["proxy"]    -> True         (matched an alias, not the vertical's own label)
    r["disclose"] -> "Benchmarked against Utility & Productivity (closest available
                      peer set for telecom; Airship publishes no telecom vertical)."

CLI:  python resolve_vertical.py "telecom"
"""

import json
import os
import re
import sys
import unicodedata

_HERE = os.path.dirname(os.path.abspath(__file__))
BENCHMARKS = os.path.join(_HERE, "..", "benchmarks.json")

# Industries with no vertical of their own, and the peer set that stands in for
# them. Kept explicit (rather than buried in an alias list) so the report can say
# "this is a proxy, and here is why" instead of implying an exact match.
PROXY_NOTES = {
    "utility_productivity": (
        "Airship publishes no telecom/operator vertical; Utility & Productivity is "
        "the closest peer set (account-management apps with a large installed base, "
        "high transactional share and low promotional pressure)."),
}


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _load(path=None):
    with open(path or BENCHMARKS, encoding="utf-8") as fh:
        return json.load(fh)


def resolve(industry, path=None, default="all_verticals"):
    """Map a free-text industry to a benchmark vertical key.

    Returns a dict: key, label, matched_on, proxy (bool), disclose (str), confidence.
    Never raises on an unknown industry — falls back to `all_verticals` and says so.
    """
    doc = _load(path)
    verticals = doc.get("verticals", {})
    q = _norm(industry)
    if not q:
        v = verticals.get(default, {})
        return {"key": default, "label": v.get("label", default), "matched_on": None,
                "proxy": True, "confidence": "none",
                "disclose": "No industry supplied — benchmarked against the all-verticals "
                            "sample. Confirm the client's vertical and re-run."}

    exact_label, alias_hit, partial = None, None, None
    for key, v in verticals.items():
        if key == "all_verticals":
            continue
        label_n, key_n = _norm(v.get("label", "")), _norm(key)
        if q in (label_n, key_n):
            exact_label = (key, v, v.get("label"))
            break
        for a in v.get("aliases", []):
            an = _norm(a)
            if not an:
                continue
            if q == an:
                alias_hit = alias_hit or (key, v, a)
            elif (an in q or q in an) and len(an) >= 4:
                partial = partial or (key, v, a)

    hit = exact_label or alias_hit or partial
    if not hit:
        v = verticals.get(default, {})
        return {"key": default, "label": v.get("label", default), "matched_on": None,
                "proxy": True, "confidence": "none",
                "disclose": f"No vertical matched {industry!r} — benchmarked against the "
                            f"all-verticals sample. Pick a vertical explicitly if a "
                            f"closer peer set exists."}

    key, v, matched = hit
    is_proxy = exact_label is None
    conf = "exact" if exact_label else ("alias" if alias_hit else "partial")
    label = v.get("label", key)
    if is_proxy:
        why = PROXY_NOTES.get(key, f"matched on the alias {matched!r}")
        disclose = f"Benchmarked against {label} — {why}"
    else:
        disclose = f"Benchmarked against {label}."
    return {"key": key, "label": label, "matched_on": matched, "proxy": is_proxy,
            "confidence": conf, "disclose": disclose}


def metrics(key, path=None):
    """The metrics block for a resolved vertical key."""
    return _load(path).get("verticals", {}).get(key, {}).get("metrics", {})


if __name__ == "__main__":
    if len(sys.argv) < 2:
        doc = _load()
        print(__doc__)
        print("Verticals:")
        for k, v in doc.get("verticals", {}).items():
            al = ", ".join(v.get("aliases", [])[:6])
            print(f"  {k:42} {v.get('label','')}" + (f"   [{al}]" if al else ""))
        sys.exit(1)
    print(json.dumps(resolve(" ".join(sys.argv[1:])), ensure_ascii=False, indent=1))
