#!/usr/bin/env python3
"""Classify Airship campaigns as one-shot vs automated/recurring from reports data.

The Reports API does not label a push as "automated" or "recurring". This skill uses
**only the Reports + Content APIs** (it never calls `/api/pipelines` or `/api/schedules`),
so this module reconstructs the typology from `responses/list` alone by:
  1. normalizing each push's message name (stripping date/version/id tokens),
  2. grouping pushes by `group_id` first, else by normalized name,
  3. detecting a regular cadence (daily / weekly / monthly) across occurrences.

A group seen on a regular cadence (or with many occurrences) is tagged
`automated_recurring`; a unique, single-occurrence send is tagged `one_shot`.

This is the reports-only HEURISTIC for typology (pipelines/schedules are out of scope).
No network / MCP.

API:
  normalize_name(name) -> str
  classify(pushes, message_names=None) -> {"groups": [...], "campaigns": [...]}
      pushes: list of dicts from responses/list (need push_uuid, push_time;
              optional group_id, sends, direct_responses).
      message_names: optional {push_uuid: message_name} from decoded pushbodies.

Each returned campaign carries: key, label, type (one_shot|automated_recurring|
ambiguous), occurrences, cadence, total_sends, total_direct, first/last seen, and the
member push_uuids — ready to drive the two top rankings in the report.
"""
import re
import statistics
from collections import defaultdict
from datetime import datetime

# Tokens stripped from message names to collapse recurring variants to a stable key.
_DATE_PATTERNS = [
    r"\d{4}[-_/]\d{2}[-_/]\d{2}",          # 2026-06-07 / 2026_06_07
    r"\d{2}[-_/]\d{2}[-_/]\d{4}",          # 07-06-2026
    r"\b\d{8}\b",                           # 07062026 / 20260607
    r"\b\d{6}\b",                           # 070626
    r"\b\d{4}\b",                           # bare year/MMDD
]
_NOISE_PATTERNS = [
    r"\bv\d+\b",                            # v2, v10
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",  # uuid
    r"\b[0-9a-f]{12,}\b",                  # long hex/hash
    r"#\d+",                                # #123
]
_MONTHS = (r"jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|"
           r"janv|fevr|f\u00e9vr|mars|avr|mai|juin|juil|aout|ao\u00fbt|sept|oct|nov|dec|d\u00e9c")


def normalize_name(name):
    """Collapse a message name to a stable key by removing date/version/id tokens."""
    if not name:
        return ""
    s = name.lower()
    # Separators -> spaces FIRST so \b boundaries apply to underscore-delimited tokens
    # (e.g. "series_01062026" -> "series 01062026", letting the date pattern match).
    s = re.sub(r"[\W_]+", " ", s)
    for pat in _DATE_PATTERNS + _NOISE_PATTERNS:
        s = re.sub(pat, " ", s)
    s = re.sub(rf"\b({_MONTHS})\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _parse_time(t):
    if not t:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(t[:19], fmt)
        except ValueError:
            continue
    return None


def _cadence(times):
    """Infer cadence from sorted datetimes. Returns (label, median_gap_days)."""
    ds = sorted(t for t in times if t)
    if len(ds) < 2:
        return ("single", None)
    gaps = [(b - a).total_seconds() / 86400.0 for a, b in zip(ds, ds[1:])]
    gaps = [g for g in gaps if g > 0]
    if not gaps:
        return ("same-day burst", 0.0)
    med = statistics.median(gaps)
    if med <= 0.5:
        label = "intra-day"
    elif med <= 1.5:
        label = "daily"
    elif med <= 3.5:
        label = "every few days"
    elif med <= 10:
        label = "weekly"
    elif med <= 45:
        label = "monthly"
    else:
        label = "irregular"
    return (label, round(med, 1))


def classify(pushes, message_names=None):
    """Group pushes and tag each campaign one_shot / automated_recurring / ambiguous."""
    message_names = message_names or {}
    groups = defaultdict(list)
    for p in pushes:
        uuid = p.get("push_uuid") or p.get("push_id")
        gid = p.get("group_id")
        name = message_names.get(uuid)
        if gid:
            key = ("group", gid)
            label = name or gid
        elif name:
            norm = normalize_name(name)
            key = ("name", norm or name.lower())
            label = norm or name
        else:
            key = ("uuid", uuid)            # unknown name & no group -> standalone
            label = uuid
        groups[key].append((p, label))

    campaigns = []
    for key, members in groups.items():
        times = [_parse_time(p.get("push_time")) for p, _ in members]
        cad_label, med_gap = _cadence(times)
        occ = len(members)
        total_sends = sum(int(p.get("sends") or 0) for p, _ in members)
        total_direct = sum(int(p.get("direct_responses") or 0) for p, _ in members)
        ts = sorted(t for t in times if t)
        label = members[0][1]

        # Typology: recurring if multiple occurrences on a non-burst cadence,
        # or many occurrences even if cadence is loose.
        regular = cad_label in {"daily", "every few days", "weekly", "monthly"}
        if occ >= 3 and (regular or occ >= 5):
            ctype = "automated_recurring"
        elif occ == 1:
            ctype = "one_shot"
        elif occ == 2 and regular:
            ctype = "automated_recurring"
        else:
            ctype = "ambiguous"            # e.g. 2x same-day burst (likely a split send)

        campaigns.append({
            "key": "%s:%s" % key,
            "label": label,
            "type": ctype,
            "occurrences": occ,
            "cadence": cad_label,
            "median_gap_days": med_gap,
            "total_sends": total_sends,
            "total_direct_responses": total_direct,
            "first_seen": ts[0].isoformat() if ts else None,
            "last_seen": ts[-1].isoformat() if ts else None,
            "push_uuids": [(p.get("push_uuid") or p.get("push_id")) for p, _ in members],
        })

    campaigns.sort(key=lambda c: c["total_sends"], reverse=True)
    summary = {
        "one_shot": sum(1 for c in campaigns if c["type"] == "one_shot"),
        "automated_recurring": sum(1 for c in campaigns if c["type"] == "automated_recurring"),
        "ambiguous": sum(1 for c in campaigns if c["type"] == "ambiguous"),
    }
    return {"summary": summary, "campaigns": campaigns}


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) > 1:
        data = json.load(open(sys.argv[1], encoding="utf-8"))
        pushes = data.get("pushes", data) if isinstance(data, dict) else data
        names = data.get("message_names") if isinstance(data, dict) else None
    else:  # tiny self-demo
        pushes = [
            {"push_uuid": "a", "push_time": "2026-06-01 17:00:00", "sends": 500000,
             "group_id": None, "direct_responses": 1200},
            {"push_uuid": "b", "push_time": "2026-06-02 17:00:00", "sends": 510000,
             "direct_responses": 1100},
            {"push_uuid": "c", "push_time": "2026-06-03 17:00:00", "sends": 505000,
             "direct_responses": 1150},
            {"push_uuid": "z", "push_time": "2026-06-04 09:00:00", "sends": 900000,
             "direct_responses": 5000},
        ]
        names = {"a": "M6+_push_series_01062026", "b": "M6+_push_series_02062026",
                 "c": "M6+_push_series_03062026", "z": "Soldes_ete_lancement"}
    print(json.dumps(classify(pushes, names), indent=2, ensure_ascii=False))
