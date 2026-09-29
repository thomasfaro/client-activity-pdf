#!/usr/bin/env python3
"""Per-channel activity + typology from the Airship Reports API (no Content API).

Robustly answers "what is active on each channel, how much, and is it automated or
one-shot" using ONLY Reports endpoints:
  - /api/reports/sends   (per-channel daily volume — the authoritative channel detector)
  - /api/reports/devices (reachable base per channel)
  - /api/reports/events  (email engagement funnel + in-app/MC locations)

Why this matters: push campaigns are enumerable (activity log + responses/list), but
**email/SMS are NOT listable** from Reports. However their VOLUME is in /sends and their
ENGAGEMENT is in /events via Airship's standard email events (injection, delivery, open,
click, bounce, spam_complaint, unsubscribe). So per-channel analysis is:
  - Push   -> full campaign enumeration + typology (see activity_log.py + classify_campaigns.py)
  - Email  -> aggregate funnel from /sends + standard email events (this module); per-message
              only when the user supplies push_id/group_id
  - SMS    -> /sends volume (+ events if present); per-message only with IDs
  - In-app/MC -> /events by `location`

Typology (automated vs one-shot) per channel:
  - Push: per-campaign (classify_campaigns on the merged inventory).
  - Email/SMS with no per-message list: inferred at CHANNEL level from the daily send
    cadence (continuous/near-daily => automated program; sparse spikes => one-shot heavy).
    This is a Low/Medium-confidence signal — label it as such.

No network / MCP — pure aggregation helpers for the audit JSON step.

API:
  email_funnel_from_events(events) -> dict
  channel_summary(sends_rows, devices, events=None) -> dict
  daily_cadence(series) -> dict            # series: list of (date, count) or list of counts
"""
from __future__ import annotations

import statistics
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

# SDK push families that appear in /sends and /devices.
PUSH_FAMILIES = ("ios", "android", "amazon", "web")

# Airship standard EMAIL engagement events (location == "custom"). Map each canonical
# event name (and common aliases) to a funnel stage. Values are summed from /events `count`.
EMAIL_EVENT_FUNNEL = {
    "injection": "injected",          # accepted/queued by Airship
    "injected": "injected",
    "delivery": "delivered",          # accepted by the receiving MTA
    "delivered": "delivered",
    "open": "opens",                  # all opens (incl. repeats)
    "initial_open": "unique_opens",   # first open per recipient
    "click": "clicks",
    "bounce": "bounces",
    "bounced": "bounces",
    "spam_complaint": "spam_complaints",
    "unsubscribe": "unsubscribes",
    "open_tracking_opt_out": "open_tracking_opt_outs",
}

# In-app / Message Center / Scene locations seen in /events.
INAPP_LOCATIONS = {
    "in_app_message": "in_app",
    "in_app_pager": "scene",          # Scenes / pager
    "ua_mcrap": "message_center",     # Message Center read/dismiss
    "ua_interactive_notification": "interactive_notification",
}


def _num(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _rate(num: float, den: float) -> Optional[float]:
    return (num / den) if den else None


def email_funnel_from_events(events: Sequence[dict]) -> dict:
    """Aggregate the standard Airship email events into a funnel with rates.

    `events` = the `events` array from /api/reports/events (all pages merged).
    Returns stage totals plus delivery/open/click/bounce/spam/unsub rates. Rates are None
    when the denominator is absent (never fabricate a rate without its base).
    """
    stages: Dict[str, float] = {v: 0.0 for v in set(EMAIL_EVENT_FUNNEL.values())}
    for e in events or []:
        if (e.get("location") or "").lower() != "custom":
            continue
        stage = EMAIL_EVENT_FUNNEL.get((e.get("name") or "").lower())
        if stage:
            stages[stage] += _num(e.get("count"))

    injected = stages.get("injected", 0.0)
    delivered = stages.get("delivered", 0.0) or injected
    opens = stages.get("opens", 0.0)
    unique_opens = stages.get("unique_opens", 0.0) or opens
    clicks = stages.get("clicks", 0.0)
    bounces = stages.get("bounces", 0.0)
    spam = stages.get("spam_complaints", 0.0)
    unsub = stages.get("unsubscribes", 0.0)

    return {
        "present": bool(injected or delivered or opens or clicks),
        "injected": int(injected),
        "delivered": int(stages.get("delivered", 0.0)),
        "opens": int(opens),
        "unique_opens": int(stages.get("unique_opens", 0.0)),
        "clicks": int(clicks),
        "bounces": int(bounces),
        "spam_complaints": int(spam),
        "unsubscribes": int(unsub),
        "rates": {
            # delivery rate off injected; engagement off delivered (email best practice)
            "delivery_rate": _rate(stages.get("delivered", 0.0), injected),
            "open_rate": _rate(unique_opens, delivered),
            "click_rate": _rate(clicks, delivered),          # CTR
            "click_to_open_rate": _rate(clicks, unique_opens),  # CTOR
            "bounce_rate": _rate(bounces, injected),
            "spam_rate": _rate(spam, delivered),
            "unsubscribe_rate": _rate(unsub, delivered),
        },
        "note": ("Email is not listable from the Reports API; this funnel is the aggregate "
                 "of Airship standard email events (injection/delivery/open/click/bounce/"
                 "spam_complaint/unsubscribe). Per-message email needs supplied push_id/group_id."),
    }


def email_reconcile(reports_sends: float, funnel: dict) -> dict:
    """Explain the gap between the two email volume counters. Report-ready dict.

    Email has the same two-counter problem as push, and no equivalent of
    `push_firehose.reconcile` ever existed for it. `/api/reports/sends` counts email
    sends over the window; `injection`/`delivery` come from the email event feed. They
    do not agree, and a report that prints one in the executive summary and the other in
    the funnel says something impossible.

    This is not hypothetical. A delivered review announced 58.5M sent and 67.4M
    delivered, and its 52.8% open rate was computed on the 67.4M — so the headline rate
    depended on whichever figure was wrong, and nothing in the report said which.
    A later window on the same account reproduces the shape exactly: roughly 77 M from
    `/sends` against 86 M delivered, +10.9%. The funnel there is internally consistent
    — injected less bounced returns the delivered figure — which locates the
    discrepancy at the junction between the two
    sources rather than inside the funnel.

    So the point of this function is not to pick a winner. It is to publish the gap, and
    to name the base each rate actually stands on: the open rate is unique opens over
    **delivered**, never over `/sends`.
    """
    inj = float((funnel or {}).get("injected") or 0)
    dlv = float((funnel or {}).get("delivered") or 0)
    bounced = float((funnel or {}).get("bounces") or 0)
    rs = float(reports_sends or 0)

    gap = inj - rs if (inj and rs) else None
    gap_pct = (gap / rs) if (gap is not None and rs) else None
    # Does the funnel hold together on its own? injected - bounced should land on
    # delivered, give or take the other soft failures the feed does not itemise.
    drift = abs(inj - bounced - dlv) / inj if inj else None
    consistent = (drift is not None and drift <= 0.02)

    out = {
        "present": bool(rs or inj or dlv),
        "reports_sends": int(rs),
        "injected": int(inj),
        "delivered": int(dlv),
        "gap": int(gap) if gap is not None else None,
        "gap_pct": round(gap_pct, 4) if gap_pct is not None else None,
        "funnel_internally_consistent": consistent,
        "funnel_drift": round(drift, 4) if drift is not None else None,
        "authoritative_for_volume": "/api/reports/sends",
        "open_rate_denominator": "delivered (email event feed), NOT /api/reports/sends",
    }
    if gap_pct is None:
        out["verdict"] = ("only one email counter is available, so no reconciliation is "
                          "possible; state which one every rate stands on.")
        return out
    direction = "above" if gap > 0 else "below"
    out["verdict"] = (
        f"the email event feed injects {inj:,.0f} messages, {abs(gap_pct):.1%} "
        f"{direction} the {rs:,.0f} that /api/reports/sends counts for the same window. "
        + ("The funnel is internally consistent (injected - bounced = delivered), so the "
           "gap sits between the two sources, not inside the funnel. "
           if consistent else
           "The funnel does not close on itself either (injected - bounced does not "
           "reach delivered), so treat every email rate as provisional. ")
        + "Volume KPIs use /api/reports/sends; the open rate is unique opens over "
          "delivered. Do not present the two counters as one figure.")
    return out


def _coerce_series(series: Sequence[Union[float, int, Tuple[Any, Any], dict]],
                   key: Optional[str] = None) -> List[float]:
    out: List[float] = []
    for item in series or []:
        if isinstance(item, dict):
            out.append(_num(item.get(key)))
        elif isinstance(item, (tuple, list)):
            out.append(_num(item[-1]))
        else:
            out.append(_num(item))
    return out


def daily_cadence(series: Sequence[Any], key: Optional[str] = None) -> dict:
    """Classify a daily count series as a continuous/automated vs one-shot-heavy channel.

    `series` may be a list of counts, (date, count) tuples, or dicts (pass `key`).
    Heuristic (Low/Medium confidence — a channel-level signal, not per-campaign):
      - active_day_ratio high (>=0.7) and coefficient of variation modest -> automated program
      - few active days with large spikes -> one-shot heavy
    Returns metrics + a worded classification + a confidence hint.
    """
    counts = _coerce_series(series, key)
    n = len(counts)
    active = [c for c in counts if c > 0]
    active_days = len(active)
    total = sum(counts)
    mean = statistics.mean(active) if active else 0.0
    cv = (statistics.pstdev(active) / mean) if (active and mean) else 0.0
    active_ratio = (active_days / n) if n else 0.0
    peak = max(counts) if counts else 0.0
    peak_share = _rate(peak, total) or 0.0

    if active_ratio >= 0.7 and cv <= 1.2:
        cls = "continuous / automated-heavy"
        conf = "Medium"
    elif active_ratio >= 0.7:
        cls = "continuous but bursty (mixed automated + broadcasts)"
        conf = "Medium"
    elif active_ratio <= 0.35 and peak_share >= 0.4:
        cls = "one-shot heavy (sparse spikes)"
        conf = "Medium"
    else:
        cls = "mixed"
        conf = "Low"

    return {
        "days": n,
        "active_days": active_days,
        "active_day_ratio": round(active_ratio, 3),
        "total": int(total),
        "mean_active_day": int(mean),
        "coefficient_of_variation": round(cv, 3),
        "peak": int(peak),
        "peak_share": round(peak_share, 3),
        "classification": cls,
        "confidence": conf,
    }


def channel_summary(sends_rows: Sequence[dict],
                    devices: Optional[dict] = None,
                    events: Optional[Sequence[dict]] = None) -> dict:
    """Build a per-channel activity summary from /sends (+ /devices, /events).

    - Detects EVERY active channel from /sends volume (catches email even when /devices
      shows 0 opted_in — a common trap).
    - Adds reachable base (opted_in) per channel from /devices.
    - Adds the email engagement funnel from /events.
    - Adds a per-channel cadence signal (automated vs one-shot heavy) from the daily series.

    `sends_rows` = /api/reports/sends `sends` array (DAILY precision recommended).
    """
    channels = ["ios", "android", "amazon", "web", "email", "sms"]
    # accumulate daily series per channel
    series: Dict[str, List[Tuple[str, float]]] = {c: [] for c in channels}
    for row in sends_rows or []:
        d = row.get("date")
        for c in channels:
            if c in row:
                series[c].append((d, _num(row.get(c))))

    dev_counts = ((devices or {}).get("counts") or {})
    email_funnel = email_funnel_from_events(events or []) if events is not None else None

    out_channels: Dict[str, dict] = {}
    for c in channels:
        totals = sum(v for _, v in series[c])
        active = totals > 0
        opted_in = _num((dev_counts.get(c) or {}).get("opted_in"))
        entry: Dict[str, Any] = {
            "active": bool(active),
            "period_sends": int(totals),
            "reachable_opted_in": int(opted_in),
            "family": "push" if c in PUSH_FAMILIES else c,
        }
        if active and series[c]:
            entry["cadence"] = daily_cadence(series[c])
        if c == "email" and email_funnel is not None and email_funnel["present"]:
            entry["funnel"] = email_funnel
            # Computed here rather than left to each client's analyze step, so that no
            # report can quote the two counters without holding their difference. Push
            # has had a mandatory reconcile for a while; email shipping without one is
            # how a review announced more email delivered than sent.
            entry["reconcile"] = email_reconcile(totals, email_funnel)
        out_channels[c] = entry

    # push blended (SDK families)
    push_sends = sum(out_channels[c]["period_sends"] for c in PUSH_FAMILIES)
    push_optin = sum(out_channels[c]["reachable_opted_in"] for c in PUSH_FAMILIES)

    active_list = [c for c in channels if out_channels[c]["active"]]
    return {
        "channels": out_channels,
        "push_blended": {"period_sends": push_sends, "reachable_opted_in": push_optin},
        "active_channels": active_list,
        "inactive_channels": [c for c in channels if not out_channels[c]["active"]],
        "email_active_but_zero_optin": bool(
            out_channels["email"]["active"] and out_channels["email"]["reachable_opted_in"] == 0
        ),
    }


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) > 1:
        data = json.load(open(sys.argv[1], encoding="utf-8"))
        summary = channel_summary(
            data.get("sends", []),
            data.get("devices"),
            data.get("events"),
        )
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        # self-test on a tiny sample fixture
        sends = [
            {"date": "2026-06-01", "ios": 100, "android": 200, "sms": 0, "email": 400, "web": 0},
            {"date": "2026-06-02", "ios": 0, "android": 0, "sms": 0, "email": 500, "web": 0},
            {"date": "2026-06-03", "ios": 5000, "android": 6000, "sms": 0, "email": 450, "web": 0},
        ]
        devices = {"counts": {"ios": {"opted_in": 1000}, "android": {"opted_in": 1500},
                              "email": {"opted_in": 0}, "sms": {"opted_in": 0}}}
        events = [
            {"name": "injection", "location": "custom", "count": 1000},
            {"name": "delivery", "location": "custom", "count": 990},
            {"name": "initial_open", "location": "custom", "count": 500},
            {"name": "open", "location": "custom", "count": 700},
            {"name": "click", "location": "custom", "count": 50},
            {"name": "bounce", "location": "custom", "count": 10},
            {"name": "unsubscribe", "location": "custom", "count": 5},
            {"name": "user-dismissed", "location": "in_app_message", "count": 999},
        ]
        s = channel_summary(sends, devices, events)
        assert "email" in s["active_channels"] and "sms" not in s["active_channels"]
        assert s["email_active_but_zero_optin"] is True
        f = s["channels"]["email"]["funnel"]
        assert f["injected"] == 1000 and f["delivered"] == 990 and f["unique_opens"] == 500
        assert abs(f["rates"]["open_rate"] - (500 / 990)) < 1e-9
        assert abs(f["rates"]["click_to_open_rate"] - (50 / 500)) < 1e-9
        assert s["channels"]["email"]["cadence"]["active_day_ratio"] == 1.0
        assert s["channels"]["ios"]["active"] and s["channels"]["web"]["active"] is False

        # The two email counters disagree here on purpose: /sends totals 1350 over the
        # three days while the event feed injects 1000. That is the shape of the real
        # defect — a report quoting both without the gap contradicts itself.
        rec = s["channels"]["email"]["reconcile"]
        assert rec["reports_sends"] == 1350 and rec["injected"] == 1000
        assert abs(rec["gap_pct"] - (-350 / 1350)) < 1e-4   # stored rounded to 4 dp
        assert rec["funnel_internally_consistent"] is True   # 1000 - 10 = 990
        assert "delivered" in rec["open_rate_denominator"]
        assert channel_summary(sends, devices, [])["channels"]["email"].get("reconcile") is None
        print("channel_activity self-test OK")
