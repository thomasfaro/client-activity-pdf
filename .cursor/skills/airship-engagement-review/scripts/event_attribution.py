#!/usr/bin/env python3
"""Per-campaign attribution of conversion KPIs (events/summary/perpush|pergroup).

Once `event_analysis.detect_conversion_kpis()` has identified conversion-KPI events,
this module pulls their **attributed** occurrences per campaign so the report can show,
next to each message's engagement rates, how many conversions (and — when the value is
monetary — how much amount) that message drove.

Endpoints (Reports API, scope `rpt`, same shape as /api/reports/events):
  - GET /api/reports/events/summary/perpush/{push_id}   -> events attributed to one push
  - GET /api/reports/events/summary/pergroup/{group_id}  -> events attributed to a program

Network-agnostic: pass an `api_get(path, params=None) -> dict` callable (e.g. wrapping
`call_airship_api`). This keeps the module unit-testable and lets the skill reuse the
existing MCP client. Only called when conversion KPIs exist (see SKILL workflow).

CLI self-test:
    python scripts/event_attribution.py --selftest
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence

ApiGet = Callable[..., dict]


def _num(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def extract_events(body: Any) -> List[dict]:
    """Pull the events array from a raw endpoint body (tolerates MCP wrapping)."""
    if body is None:
        return []
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        if isinstance(body.get("events"), list):
            return body["events"]
        resp = body.get("response")
        if isinstance(resp, dict) and isinstance(resp.get("events"), list):
            return resp["events"]
    return []


def summarize_attribution(events: Sequence[dict], kpi_names: set,
                          monetary_names: Optional[set] = None,
                          currency: Optional[str] = None) -> dict:
    """Aggregate attributed conversions for the requested KPI events.

    Returns per-event direct/indirect counts (+ amounts when the event is monetary) and
    campaign-level totals. `location == "custom"` only (business events, not in-app/MC).
    """
    monetary_names = monetary_names or set()
    per_event: Dict[str, dict] = {}
    for e in events or []:
        if (e.get("location") or "").lower() != "custom":
            continue
        name = e.get("name") or ""
        if name not in kpi_names:
            continue
        conv = (e.get("conversion") or "unattributed").lower()
        if conv not in ("direct", "indirect"):
            continue  # attribution view: only push-attributed conversions
        row = per_event.setdefault(name, {
            "direct_count": 0, "indirect_count": 0,
            "direct_amount": 0.0, "indirect_amount": 0.0,
            "is_monetary": name in monetary_names,
        })
        row[f"{conv}_count"] += int(_num(e.get("count")))
        if name in monetary_names:
            row[f"{conv}_amount"] += _num(e.get("value"))

    tot_conv = sum(r["direct_count"] + r["indirect_count"] for r in per_event.values())
    tot_amt = sum(r["direct_amount"] + r["indirect_amount"] for r in per_event.values())
    for r in per_event.values():
        r["direct_amount"] = round(r["direct_amount"], 2)
        r["indirect_amount"] = round(r["indirect_amount"], 2)
    return {
        "available": bool(per_event),
        "currency": currency,
        "events": per_event,
        "total_attributed_conversions": int(tot_conv),
        "total_attributed_amount": round(tot_amt, 2) if tot_amt else 0.0,
    }


def _fetch(api_get: ApiGet, path: str) -> dict:
    """Call api_get(path) tolerating errors; returns {ok, body|error}."""
    try:
        body = api_get(path)
        return {"ok": True, "body": body}
    except Exception as exc:  # noqa: BLE001 - surface as degraded, never crash the report
        return {"ok": False, "error": str(exc)}


def attributed_for_push(api_get: ApiGet, push_id: str, kpi_names: set,
                        monetary_names: Optional[set] = None,
                        currency: Optional[str] = None) -> dict:
    res = _fetch(api_get, f"/api/reports/events/summary/perpush/{push_id}")
    if not res["ok"]:
        return {"available": False, "reason": f"perpush unavailable: {res['error']}"}
    return summarize_attribution(extract_events(res["body"]), kpi_names,
                                 monetary_names, currency)


def attributed_for_group(api_get: ApiGet, group_id: str, kpi_names: set,
                         monetary_names: Optional[set] = None,
                         currency: Optional[str] = None) -> dict:
    res = _fetch(api_get, f"/api/reports/events/summary/pergroup/{group_id}")
    if not res["ok"]:
        return {"available": False, "reason": f"pergroup unavailable: {res['error']}"}
    return summarize_attribution(extract_events(res["body"]), kpi_names,
                                 monetary_names, currency)


def conversion_kpi_selectors(analysis: dict) -> dict:
    """Build the KPI name set + monetary subset + currency from an event_analysis result."""
    kpis = analysis.get("conversion_kpis", [])
    names = {k["name"] for k in kpis}
    monetary = {k["name"] for k in kpis if k.get("value_is_monetary")}
    currency = (analysis.get("currency") or {}).get("currency")
    return {"kpi_names": names, "monetary_names": monetary, "currency": currency}


def attribute_campaigns(api_get: ApiGet, campaigns: Sequence[dict], analysis: dict,
                        min_sends: int = 0) -> List[dict]:
    """Attach `attributed_conversions` to each campaign row.

    campaigns: list of dicts each carrying at least a `name` and one of `push_id` /
    `group_id` (+ optional `sends` for the min-volume floor). Only campaigns above
    `min_sends` are queried, to avoid noisy low-volume calls. If no conversion KPI was
    detected, returns the campaigns unchanged (no network calls).
    """
    sel = conversion_kpi_selectors(analysis)
    if not sel["kpi_names"]:
        return list(campaigns)
    out = []
    for camp in campaigns:
        row = dict(camp)
        has_id = bool(camp.get("push_id") or camp.get("group_id"))
        if not has_id:
            row["attributed_conversions"] = {"available": False,
                                             "reason": "no push_id/group_id"}
        elif min_sends and _num(camp.get("sends")) < min_sends:
            row["attributed_conversions"] = {"available": False,
                                             "reason": "below min-volume floor"}
        elif camp.get("push_id"):
            row["attributed_conversions"] = attributed_for_push(
                api_get, camp["push_id"], sel["kpi_names"], sel["monetary_names"],
                sel["currency"])
        else:
            row["attributed_conversions"] = attributed_for_group(
                api_get, camp["group_id"], sel["kpi_names"], sel["monetary_names"],
                sel["currency"])
        out.append(row)
    return out


def _selftest():
    fake = {
        "p-1": {"events": [
            {"name": "passage_commande", "location": "custom", "conversion": "direct",
             "count": 120, "value": 12000.0},
            {"name": "passage_commande", "location": "custom", "conversion": "indirect",
             "count": 300, "value": 30000.0},
            {"name": "passage_commande", "location": "custom", "conversion": "unattributed",
             "count": 5000, "value": 500000.0},
            {"name": "app_went_fidelite", "location": "custom", "conversion": "direct",
             "count": 45, "value": 0.0},
            {"name": "noise_event", "location": "custom", "conversion": "direct",
             "count": 9, "value": 0.0},
        ]},
        "g-1": {"response": {"events": [
            {"name": "passage_commande", "location": "custom", "conversion": "indirect",
             "count": 80, "value": 8000.0},
        ]}},
    }

    def api_get(path, params=None):
        if "perpush/p-1" in path:
            return fake["p-1"]
        if "pergroup/g-1" in path:
            return fake["g-1"]
        if "perpush/p-403" in path:
            raise RuntimeError("403 Missing required scope")
        return {"events": []}

    analysis = {
        "currency": {"currency": "EUR"},
        "conversion_kpis": [
            {"name": "passage_commande", "value_is_monetary": True},
            {"name": "app_went_fidelite", "value_is_monetary": False},
        ],
    }
    camps = [
        {"name": "Push A", "push_id": "p-1", "sends": 1_000_000},
        {"name": "Program B", "group_id": "g-1", "sends": 5_000_000},
        {"name": "Push C", "push_id": "p-403", "sends": 200_000},
        {"name": "Push D low", "push_id": "p-1", "sends": 10},
        {"name": "Push E noid", "sends": 500},
    ]
    res = attribute_campaigns(api_get, camps, analysis, min_sends=1000)

    a = res[0]["attributed_conversions"]
    assert a["available"] and a["total_attributed_conversions"] == 120 + 300 + 45, a
    pc = a["events"]["passage_commande"]
    assert pc["direct_count"] == 120 and pc["indirect_count"] == 300
    assert pc["direct_amount"] == 12000.0 and pc["indirect_amount"] == 30000.0
    assert a["events"]["app_went_fidelite"]["is_monetary"] is False
    assert "noise_event" not in a["events"]
    assert abs(a["total_attributed_amount"] - 42000.0) < 1e-6

    b = res[1]["attributed_conversions"]
    assert b["available"] and b["events"]["passage_commande"]["indirect_count"] == 80

    c = res[2]["attributed_conversions"]
    assert c["available"] is False and "unavailable" in c["reason"]

    d = res[3]["attributed_conversions"]
    assert d["available"] is False and "min-volume" in d["reason"]

    e = res[4]["attributed_conversions"]
    assert e["available"] is False and "no push_id" in e["reason"]

    # no KPIs -> no network, campaigns unchanged
    untouched = attribute_campaigns(api_get, camps, {"conversion_kpis": []})
    assert "attributed_conversions" not in untouched[0]
    print("event_attribution self-test OK")


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        _selftest()
    else:
        print(__doc__)
