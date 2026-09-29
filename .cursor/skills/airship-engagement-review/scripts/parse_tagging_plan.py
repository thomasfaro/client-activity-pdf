#!/usr/bin/env python3
"""Normalize an exported tagging-plan .json into a clean, client-only inventory.

Primary input: the payload produced by the app's "Export tagging plan (.json)"
button (`kind: airship-rtds-tagging-plan`, with `model.dataSheets` + `values`).
A raw `*.audit-report.json` is also accepted as a fallback.

Airship auto-managed data (attribute keys / tag groups prefixed `ua_`) is
excluded from the client inventory and listed separately under `excludedAirship`.

Usage:
    python scripts/parse_tagging_plan.py input.json            # prints normalized JSON
    python scripts/parse_tagging_plan.py input.json -o out.json
"""
import argparse
import json
import sys

AIRSHIP_PREFIX = "ua_"


def _is_airship_key(key):
    return str(key or "").strip().lower().startswith(AIRSHIP_PREFIX)


def _is_airship_tag_group(group, key):
    g = str(group or "").strip().lower()
    if g:
        return g.startswith(AIRSHIP_PREFIX)
    # Fall back to the "group:value" key when the group column is empty.
    return str(key or "").strip().lower().startswith(AIRSHIP_PREFIX)


def _sheet_by_name(model):
    return {s.get("name"): s for s in (model or {}).get("dataSheets", [])}


def _platform_cells(row):
    return {
        k[len("plat_"):]: v
        for k, v in row.items()
        if k.startswith("plat_") and v
    }


def _version_scope(row):
    vs = row.get("__versionScope")
    if not vs:
        return {"label": row.get("versionScope") or "", "sourceScope": None}
    return {
        "label": vs.get("label") or "",
        "sourceScope": vs.get("sourceScope"),
        "maxAppVersion": vs.get("maxAppVersion"),
        "hasSdk": vs.get("hasSdk"),
        "hasApi": vs.get("hasApi"),
    }


def _value_lookups(values):
    """Group value histograms by (source, event, property) and by attribute key."""
    custom = {}
    for v in (values or {}).get("customValues", []) or []:
        key = (v.get("source") or "", v.get("event") or "", v.get("property") or "")
        custom.setdefault(key, []).append({"value": v.get("value"), "count": v.get("count")})
    attrs = {}
    for v in (values or {}).get("attributeValues", []) or []:
        attrs.setdefault(v.get("key") or "", []).append({"value": v.get("value"), "count": v.get("count")})
    return custom, attrs


def _split_props(properties_str):
    if not properties_str:
        return []
    # The model joins property names with ", " (and may add a "(+N)" overflow tag).
    parts = [p.strip() for p in str(properties_str).split(",")]
    return [p for p in parts if p and not p.startswith("(+")]


def parse_export(payload):
    model = payload.get("model") or {}
    values = payload.get("values") or {}
    meta = payload.get("meta") or {}
    sheets = _sheet_by_name(model)
    custom_vals, attr_vals = _value_lookups(values)

    inv = {
        "meta": meta,
        "platforms": model.get("platforms") or meta.get("platforms") or [],
        "customEvents": [],
        "attributes": [],
        "tags": [],
        "subscriptionLists": [],
        "screens": [],
        "excludedAirship": {"attributes": [], "tags": []},
        "valuesAvailable": bool(values.get("available")),
        "valuesTruncated": bool(values.get("truncated")),
    }

    # Custom events
    for row in (sheets.get("Custom Events") or {}).get("rows", []):
        if row.get("__section") or not row.get("name"):
            continue
        source = row.get("source") or ""
        name = row.get("name")
        prop_names = _split_props(row.get("properties"))
        properties = []
        for prop in prop_names:
            samples = custom_vals.get((source, name, prop), [])
            properties.append({"name": prop, "samples": samples})
        event_value_samples = custom_vals.get((source, name, "value"), [])
        inv["customEvents"].append({
            "name": name,
            "source": source,
            "total": row.get("total") or 0,
            "platforms": _platform_cells(row),
            "properties": properties,
            "valueSamples": event_value_samples,
            "present": row.get("present") or "",
            "missing": row.get("missing") or "",
            "versionScope": _version_scope(row),
        })

    # Attributes (exclude ua_*)
    for row in (sheets.get("Attributes") or {}).get("rows", []):
        if row.get("__section") or not (row.get("key") or row.get("normalized")):
            continue
        key = row.get("key") or row.get("normalized")
        normalized = row.get("normalized") or key
        entry = {
            "key": key,
            "normalized": normalized,
            "total": row.get("total") or 0,
            "actions": row.get("actions") or "",
            "sources": row.get("sources") or "",
            "distinctValues": row.get("distinctValues") or 0,
            "platforms": _platform_cells(row),
            "sampleValues": [s["value"] for s in attr_vals.get(key, [])],
            "versionScope": _version_scope(row),
        }
        if _is_airship_key(normalized) or _is_airship_key(key):
            inv["excludedAirship"]["attributes"].append(entry)
        else:
            inv["attributes"].append(entry)

    # Tags (exclude ua_* groups)
    for row in (sheets.get("Tags") or {}).get("rows", []):
        if row.get("__section") or not row.get("key"):
            continue
        entry = {
            "key": row.get("key"),
            "group": row.get("group") or "",
            "value": row.get("value") or "",
            "added": row.get("added") or 0,
            "removed": row.get("removed") or 0,
            "net": row.get("net") or 0,
            "versionScope": _version_scope(row),
        }
        if _is_airship_tag_group(entry["group"], entry["key"]):
            inv["excludedAirship"]["tags"].append(entry)
        else:
            inv["tags"].append(entry)

    # Subscription lists
    for row in (sheets.get("Subscription Lists") or {}).get("rows", []):
        if row.get("__section") or not row.get("listId"):
            continue
        inv["subscriptionLists"].append({
            "listId": row.get("listId"),
            "subscribe": row.get("subscribe") or 0,
            "unsubscribe": row.get("unsubscribe") or 0,
            "net": row.get("net") or 0,
            "scopes": row.get("scopes") or "",
            "source": row.get("source") or "",
            "platforms": _platform_cells(row),
            "versionScope": _version_scope(row),
        })

    # Screens
    for row in (sheets.get("Screens") or {}).get("rows", []):
        if row.get("__section") or not row.get("name"):
            continue
        inv["screens"].append({
            "name": row.get("name"),
            "total": row.get("total") or 0,
            "platforms": _platform_cells(row),
            "versionScope": _version_scope(row),
        })

    return inv


def _raw_scope(item):
    vs = item.get("versionScope") or {}
    return {"label": vs.get("label") or "", "sourceScope": vs.get("sourceScope")}


def parse_raw_report(report):
    """Fallback: build the inventory from a raw *.audit-report.json structure."""
    inv = {
        "meta": report.get("meta") or {},
        "platforms": (report.get("meta") or {}).get("platforms") or [],
        "customEvents": [],
        "attributes": [],
        "tags": [],
        "subscriptionLists": [],
        "screens": [],
        "excludedAirship": {"attributes": [], "tags": []},
        "valuesAvailable": False,
        "valuesTruncated": False,
    }
    ce = report.get("customEvents") or {}
    for src in ("sdk", "api", "unknown"):
        for r in (ce.get(src) or {}).get("top", []) or []:
            inv["customEvents"].append({
                "name": r.get("name"),
                "source": (r.get("source") or src).upper(),
                "total": r.get("count") or 0,
                "platforms": {},
                "properties": [{"name": p, "samples": []} for p in (r.get("properties") or [])],
                "valueSamples": [{"value": v, "count": None} for v in (r.get("sampleValues") or [])],
                "present": "",
                "missing": "",
                "versionScope": _raw_scope(r),
            })
    for r in (report.get("attributes") or {}).get("topKeys", []) or []:
        key = r.get("key") or r.get("normalized")
        entry = {
            "key": key,
            "normalized": r.get("normalized") or key,
            "total": r.get("count") or 0,
            "actions": "",
            "sources": "",
            "distinctValues": r.get("trackedValueCount") or 0,
            "platforms": {},
            "sampleValues": [],
            "versionScope": _raw_scope(r),
        }
        if _is_airship_key(entry["normalized"]) or _is_airship_key(key):
            inv["excludedAirship"]["attributes"].append(entry)
        else:
            inv["attributes"].append(entry)
    tags = report.get("tags") or {}
    seen = {}
    for field, r_list in (("added", tags.get("topAdded")), ("removed", tags.get("topRemoved"))):
        for r in r_list or []:
            k = r.get("key")
            row = seen.setdefault(k, {"key": k, "group": r.get("group") or "", "value": r.get("value") or "",
                                      "added": 0, "removed": 0, "versionScope": _raw_scope(r)})
            row[field] = r.get("count") or 0
    for row in seen.values():
        row["net"] = row["added"] - row["removed"]
        if _is_airship_tag_group(row["group"], row["key"]):
            inv["excludedAirship"]["tags"].append(row)
        else:
            inv["tags"].append(row)
    for r in (report.get("subscriptionLists") or {}).get("byList", []) or []:
        inv["subscriptionLists"].append({
            "listId": r.get("listId"),
            "subscribe": r.get("subscribe") or 0,
            "unsubscribe": r.get("unsubscribe") or 0,
            "net": r.get("net") or 0,
            "scopes": "",
            "source": r.get("source") or "",
            "platforms": {},
            "versionScope": _raw_scope(r),
        })
    for r in (report.get("screenViewed") or {}).get("top", []) or []:
        inv["screens"].append({
            "name": r.get("name"),
            "total": r.get("count") or 0,
            "platforms": {},
            "versionScope": _raw_scope(r),
        })
    return inv


def parse(payload):
    if payload.get("kind") == "airship-rtds-tagging-plan" or "model" in payload:
        return parse_export(payload)
    if "customEvents" in payload or "attributes" in payload:
        return parse_raw_report(payload)
    raise ValueError("Unrecognized JSON: expected a tagging-plan export or an audit report.")


def main(argv):
    ap = argparse.ArgumentParser(description="Normalize a tagging-plan export into a client-only inventory.")
    ap.add_argument("input", help="Path to the tagging-plan .json (or a raw audit-report.json).")
    ap.add_argument("-o", "--output", help="Write normalized JSON here (default: stdout).")
    args = ap.parse_args(argv[1:])

    with open(args.input, encoding="utf-8") as fh:
        payload = json.load(fh)
    inv = parse(payload)

    out = json.dumps(inv, indent=2, ensure_ascii=False)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(out)
    else:
        print(out)

    ex = inv["excludedAirship"]
    print(
        f"[parse] events={len(inv['customEvents'])} attributes={len(inv['attributes'])} "
        f"tags={len(inv['tags'])} lists={len(inv['subscriptionLists'])} screens={len(inv['screens'])} "
        f"| excluded ua_*: attrs={len(ex['attributes'])} tags={len(ex['tags'])}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
