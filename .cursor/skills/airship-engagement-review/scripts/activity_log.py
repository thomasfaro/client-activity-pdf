#!/usr/bin/env python3
"""Normalize and merge Airship Activity Log rows with responses/list push inventory.

The Activity Log (`GET /api/reports/activity/details`, scope `rpt`) is the dashboard-aligned
list of **non-unicast** messaging activity (broadcasts, segments, A/B, group sends). It
**excludes** unicast / automation micro-stream rows — the noise that makes full
`responses/list` pagination intractable on firehose accounts.

Use it alongside `responses/list`:
  - **Activity log** → canonical inventory of **one-shot / dashboard broadcasts** and
    program-level `GROUP` rows; fast to paginate; surfaces marquee sends the response
    listing may miss when sampling.
  - **responses/list** → full push stream incl. UNICAST; `push_type`, `group_id`, cadence
    for automated/recurring typology (`classify_campaigns.py`).

Performance rates for report tables still come from `perpush/detail` / `pergroup/detail`
(activity delivery totals are useful for discovery/ranking shortlists, not final KPIs).

No network / MCP — pure helpers for the audit JSON aggregate step.

API:
  nonneg(v) -> int                               # shared guard on `-1` sentinels
  delivery_parts(details) -> (alerting, silent, rich, web)
  delivery_sends(details) -> int                 # additive, upper bound
  reach_bound(details) -> int                    # max(alerting, rich) + silent + web
  rich_overlap(activities) -> dict               # size of the gap between the two
  interaction_metrics(details) -> {"direct", "influenced", "web_clicks"}
  normalize_activity(entry) -> dict
  activity_to_push_row(entry) -> dict          # classify_campaigns-compatible
  merge_push_inventories(responses, activities) -> dict
  one_shot_broadcast_candidates(activities, min_sends=1000) -> list
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Union


def nonneg(v: Any) -> int:
    """An int that is never negative, for counters that use `-1` as "not applicable".

    Several Reports API fields carry `-1` rather than `null` when a metric does not apply
    (`rich_read`, `influenced`). A sentinel that is also a number gets summed sooner or
    later, and subtracts from a total instead of being skipped, so every counter read
    from the API goes through here.
    """
    try:
        n = int(v or 0)
    except (TypeError, ValueError):
        return 0
    return n if n >= 0 else 0


_int_nonneg = nonneg          # the name this module used before it was shared


def delivery_parts(details: Optional[dict]) -> tuple:
    """One activity row's delivery components: (alerting, silent, rich, web).

    Single reader for the block, because the two consumers of it disagreed on `rich` and
    one of them was demonstrably wrong.

    **`rich` is not a subset of `alerting`.** Measured read-only on 217 activity rows of a
    production account: 9 rows carry `rich > alerting`, including one at
    `alerting=8039 / rich=16729` and one at `alerting=0, silent=0, rich=6` — a Message
    Center drop with no notification, whose reach is entirely in `rich`. So the three
    components cannot be summed without double-counting whatever overlap exists between
    the notification and the inbox drop, nor can `rich` be dropped as redundant. See
    `rich_overlap()` for the size of the gap, and `reach_bound()` for the lower bound.
    """
    if not details:
        return (0, 0, 0, 0)
    d = details.get("delivery") or {}
    app = d.get("app") or {}
    # `app.in_app.impressions*` is present on every row and zero on every row (verified
    # on 354,604 rows across 11 projects); it is a dead field, and in-app impressions
    # would not be push sends anyway.
    return (_int_nonneg(app.get("alerting")), _int_nonneg(app.get("silent")),
            _int_nonneg(app.get("rich")),
            _int_nonneg((d.get("web") or {}).get("total")))


def delivery_sends(details: Optional[dict]) -> int:
    """Estimate total sends from an activity `details.delivery` block.

    Sums all three app components. This is the upper bound, not a measurement: where a
    message both notified and dropped to the inbox, the same device is counted twice.
    Deliberately left as-is pending confirmation from Airship on whether the `alerting`
    audience is contained in the `rich` audience; `reach_bound()` is the other end of the
    interval and `rich_overlap()` reports the distance between them.
    """
    alerting, silent, rich, web = delivery_parts(details)
    return alerting + silent + rich + web


def reach_bound(details: Optional[dict]) -> int:
    """Devices reached by one activity row, lower bound.

    Takes `max(alerting, rich)` on the reading that a notified device also receives the
    inbox drop, so the larger of the two already covers the smaller. Adds `silent` and
    `web`, which address different surfaces. Use this for ranking and for the low end of
    a stated reach interval — never as a published exact figure.
    """
    alerting, silent, rich, web = delivery_parts(details)
    return max(alerting, rich) + silent + web


def rich_overlap(activities: Sequence[dict]) -> dict:
    """Size the uncertainty that `rich` introduces in an account's reach total.

    Returns the additive total (`delivery_sends`), the lower bound (`reach_bound`), and
    the gap between them, so a section can state reach as an interval instead of a false
    exact number. `inbox_only` counts rows whose entire reach is in `rich`: those are
    Message Center drops without a notification, which rank at zero on `sends` and drop
    out of the inventory unless ranking uses `reach_bound`.
    """
    rows = rich_rows = rich_gt_alerting = inbox_only = 0
    additive = bound = 0
    worst = None
    for entry in activities or ():
        details = entry.get("details") if isinstance(entry, dict) else None
        alerting, silent, rich, web = delivery_parts(details)
        rows += 1
        additive += alerting + silent + rich + web
        bound += max(alerting, rich) + silent + web
        if rich:
            rich_rows += 1
        if rich > alerting:
            rich_gt_alerting += 1
            if worst is None or rich - alerting > worst["excess"]:
                worst = {"push_id": entry.get("push_id"), "alerting": alerting,
                         "silent": silent, "rich": rich, "excess": rich - alerting}
        if rich and not (alerting or silent or web):
            inbox_only += 1

    gap = additive - bound
    pct = (gap / bound * 100.0) if bound else 0.0
    return {
        "rows": rows,
        "rows_with_rich": rich_rows,
        "rows_rich_gt_alerting": rich_gt_alerting,
        "rows_inbox_only": inbox_only,
        "additive_total": additive,
        "reach_bound_total": bound,
        "gap": gap,
        "max_overstatement_pct": round(pct, 2),
        "worst_row": worst,
        "note": ("`rich` overlaps `alerting` by an unknown amount, so reach lies in "
                 "[reach_bound_total, additive_total]. State the interval, or state the "
                 "bound and say it is a bound."),
    }


def interaction_metrics(details: Optional[dict]) -> dict:
    """Extract direct/influenced opens and web clicks from activity interaction block."""
    if not details:
        return {"direct": 0, "influenced": 0, "web_clicks": 0}
    i = details.get("interaction") or {}
    app = i.get("app") or {}
    web = i.get("web") or {}
    direct = _int_nonneg(app.get("direct"))
    influenced = _int_nonneg(app.get("influenced"))
    return {
        "direct": direct,
        "influenced": influenced,
        "web_clicks": _int_nonneg(web.get("clicks")),
    }


def normalize_activity(entry: dict) -> dict:
    """Return a stable dict for one activity log row."""
    details = entry.get("details") or {}
    metrics = interaction_metrics(details)
    sends = delivery_sends(details)
    pid = entry.get("push_id")
    return {
        "push_id": pid,
        "push_uuid": pid,
        "timestamp": entry.get("timestamp"),
        "push_time": entry.get("timestamp"),
        "type": (entry.get("type") or "").upper(),          # PUSH | GROUP
        "experiment": bool(entry.get("experiment")),
        "sends": sends,
        "direct_responses": metrics["direct"],
        "influenced_responses": metrics["influenced"],
        "web_clicks": metrics["web_clicks"],
        "source": "activity_log",
    }


def activity_to_push_row(entry: dict) -> dict:
    """Shape one activity row for `classify_campaigns.classify(pushes=...)`."""
    row = normalize_activity(entry)
    # classify_campaigns keys
    return {
        "push_uuid": row["push_id"],
        "push_id": row["push_id"],
        "push_time": row["timestamp"],
        "sends": row["sends"],
        "direct_responses": row["direct_responses"],
        "influenced_responses": row["influenced_responses"],
        "group_id": entry.get("group_id"),                  # present on some GROUP rows
        "_activity_type": row["type"],
        "_experiment": row["experiment"],
        "_source": "activity_log",
    }


def _push_key(p: dict) -> Optional[str]:
    return p.get("push_uuid") or p.get("push_id")


def merge_push_inventories(
    responses_pushes: Sequence[dict],
    activities: Sequence[dict],
) -> dict:
    """Union responses/list and activity log inventories by push_id.

    Returns:
      merged: list of push-shaped dicts (responses row preferred; activity fills gaps)
      activity_only: activity rows whose push_id was absent from responses/list
      responses_only: responses rows absent from activity log
      group_entries: activity rows with type GROUP (program-level activity log lines)
      stats: coverage counters for the report appendix
    """
    by_id: Dict[str, dict] = {}
    sources: Dict[str, set] = {}

    for p in responses_pushes:
        k = _push_key(p)
        if not k:
            continue
        row = dict(p)
        row.setdefault("_source", "responses_list")
        by_id[k] = row
        sources.setdefault(k, set()).add("responses_list")

    activity_only: List[dict] = []
    group_entries: List[dict] = []

    for raw in activities:
        norm = normalize_activity(raw)
        if norm["type"] == "GROUP":
            group_entries.append(norm)
            continue
        k = norm["push_id"]
        if not k:
            continue
        if k in by_id:
            sources.setdefault(k, set()).add("activity_log")
            # Enrich responses row with activity-only flags when useful
            existing = by_id[k]
            if not existing.get("push_time") and norm.get("timestamp"):
                existing["push_time"] = norm["timestamp"]
            existing["_activity_sends"] = norm["sends"]
            existing["_in_activity_log"] = True
        else:
            row = activity_to_push_row(raw)
            by_id[k] = row
            sources[k] = {"activity_log"}
            activity_only.append(norm)

    responses_only = [
        by_id[k] for k, src in sources.items()
        if src == {"responses_list"}
    ]
    merged = list(by_id.values())
    merged.sort(key=lambda r: int(r.get("sends") or 0), reverse=True)

    return {
        "merged": merged,
        "activity_only": activity_only,
        "responses_only": responses_only,
        "group_entries": group_entries,
        "stats": {
            "responses_count": len(responses_pushes),
            "activity_count": len(activities),
            "merged_unique": len(merged),
            "activity_only_count": len(activity_only),
            "responses_only_count": len(responses_only),
            "group_entries_count": len(group_entries),
        },
    }


def one_shot_broadcast_candidates(
    activities: Sequence[dict],
    *,
    min_sends: int = 1000,
    push_types: Optional[Iterable[str]] = None,
) -> List[dict]:
    """Return activity-log PUSH rows that look like one-shot broadcasts.

    Filters to `type=PUSH` (not GROUP), optional min delivery-based sends, sorted by sends.
    These are the dashboard sends most often missing from a sampled responses/list pull.
    """
    allowed = {t.upper() for t in push_types} if push_types else None
    out: List[dict] = []
    for raw in activities:
        norm = normalize_activity(raw)
        if norm["type"] != "PUSH":
            continue
        if allowed and norm["type"] not in allowed:
            continue
        if norm["sends"] < min_sends:
            continue
        out.append(norm)
    out.sort(key=lambda r: r["sends"], reverse=True)
    return out


if __name__ == "__main__":
    import json
    import sys

    sample_activities = [
        {
            "push_id": "broadcast-1",
            "timestamp": "2026-06-16 10:00:00",
            "type": "PUSH",
            "experiment": False,
            "details": {
                "delivery": {"app": {"silent": 100, "alerting": 1_000_000, "rich": 500_000},
                             "web": {"total": 0}},
                "interaction": {"app": {"direct": 5000, "influenced": 50000}},
            },
        },
        {
            "push_id": "micro-unicast-not-in-log",
            "timestamp": "2026-06-16 10:01:00",
            "type": "PUSH",
            "experiment": False,
            "details": {
                "delivery": {"app": {"silent": 0, "alerting": 3, "rich": 3}, "web": {"total": 0}},
                "interaction": {"app": {"direct": 1, "influenced": 2}},
            },
        },
        {
            "push_id": "group-program-1",
            "timestamp": "2026-06-15 08:00:00",
            "type": "GROUP",
            "experiment": False,
            "details": {
                "delivery": {"app": {"silent": 0, "alerting": 50_000, "rich": 0}, "web": {"total": 0}},
                "interaction": {"app": {"direct": 100, "influenced": 900}},
            },
        },
    ]
    sample_responses = [
        {"push_uuid": "micro-from-responses", "push_time": "2026-06-16 09:00:00",
         "sends": 4, "direct_responses": 1, "group_id": "g-automation"},
        {"push_uuid": "broadcast-1", "push_time": "2026-06-16 10:00:00",
         "sends": 1_500_000, "direct_responses": 4800, "push_type": "BROADCAST"},
    ]

    if len(sys.argv) > 1:
        data = json.load(open(sys.argv[1], encoding="utf-8"))
        merged = merge_push_inventories(
            data.get("responses_pushes", data.get("responses", [])),
            data.get("activities", data.get("activity_log", [])),
        )
        merged["one_shot_candidates"] = one_shot_broadcast_candidates(
            data.get("activities", data.get("activity_log", [])),
            min_sends=int(data.get("min_broadcast_sends", 1000)),
        )
        print(json.dumps(merged, indent=2, ensure_ascii=False))
    else:
        m = merge_push_inventories(sample_responses, sample_activities)
        assert m["stats"]["activity_only_count"] == 1
        assert m["stats"]["responses_only_count"] == 1
        assert m["stats"]["merged_unique"] == 3
        assert len(m["group_entries"]) == 1
        cands = one_shot_broadcast_candidates(sample_activities, min_sends=1000)
        assert len(cands) == 1 and cands[0]["push_id"] == "broadcast-1"
        assert delivery_sends(sample_activities[0]["details"]) == 1_500_100

        # `rich` is not a subset of `alerting`: a Message Center drop with no
        # notification has its whole reach in `rich`, and must not rank at zero.
        inbox_only = {"delivery": {"app": {"silent": 0, "alerting": 0, "rich": 6}}}
        assert delivery_parts(inbox_only) == (0, 0, 6, 0)
        assert reach_bound(inbox_only) == 6, "an inbox-only drop must not read as zero"
        # ...while a notified message is not counted twice by the bound.
        both = {"delivery": {"app": {"silent": 0, "alerting": 4, "rich": 6}}}
        assert delivery_sends(both) == 10 and reach_bound(both) == 6

        ov = rich_overlap([{"push_id": "a", "details": both},
                           {"push_id": "b", "details": inbox_only}])
        assert ov["rows"] == 2 and ov["rows_rich_gt_alerting"] == 2
        assert ov["rows_inbox_only"] == 1
        assert ov["additive_total"] == 16 and ov["reach_bound_total"] == 12
        assert ov["gap"] == 4 and ov["worst_row"]["push_id"] == "b"
        assert rich_overlap([])["max_overstatement_pct"] == 0.0
        print("activity_log self-test OK")
