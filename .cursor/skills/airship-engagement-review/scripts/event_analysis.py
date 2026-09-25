#!/usr/bin/env python3
"""Custom-event contextualisation for the engagement review (no network).

Turns the raw `/api/reports/events` array (custom `location`) into:
  - an aggregation per event name with the direct/indirect/unattributed split of BOTH
    `count` and `value` (attribution rates included);
  - a classification of each event against the vertical's best-practice catalog
    (`event_catalog.json`) with a confidence level (name tokens + bilingual aliases);
  - conversion-KPI detection (business / usage-consumption / loyalty);
  - a heuristic on whether `value` behaves like a monetary amount (vs a plain per-event
    counter) plus a probable currency for the brand, and — when monetary — the direct /
    indirect / unattributed AMOUNTS per event;
  - data-collection opportunities: catalog events the client does NOT send, and events
    the client DOES send but without the conversion value/currency they should carry.

`value` is a client-declared number, never guaranteed to be currency — every monetary
read carries that caveat and a confidence level. Per-campaign attribution of these KPIs
(events/summary/perpush|pergroup) lives in `event_attribution.py`.

CLI:
    python scripts/event_analysis.py <events.json|events.csv> --vertical retail \
        [--region eu] [--country FR] [--currency EUR] [--brand "Client Name"]
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Sequence

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
DEFAULT_CATALOG = os.path.join(SKILL_DIR, "event_catalog.json")

# --------------------------------------------------------------------------- #
# Standard email events surface in /events with location == "custom"; they are the
# email funnel (handled by channel_activity.email_funnel_from_events), NOT business
# custom events. Keep in sync with channel_activity.EMAIL_EVENT_FUNNEL.
# --------------------------------------------------------------------------- #
EMAIL_EVENT_NAMES = {
    "injection", "injected", "delivery", "delivered", "open", "initial_open",
    "click", "bounce", "bounced", "spam_complaint", "unsubscribe",
    "open_tracking_opt_out",
}

GENERIC_TOKENS = {
    "app", "went", "screen", "page", "view", "click", "clicked", "tap", "button",
    "user", "the", "and", "for", "with", "from", "web", "mobile", "ios", "android",
    "new", "old", "current", "previous", "custom", "event", "action", "status",
    "detail", "details", "info", "data", "id", "type", "step", "flow",
}

# Bilingual (EN/FR) + synonym concept groups. Two names sharing a group = a concept
# match. Adapted (self-contained) from the tagging-plan analyzer.
ALIAS_GROUPS = [
    {"order", "commande", "achat", "purchase", "purchased", "checkout", "transaction",
     "buy", "bought", "paid", "payment", "paiement", "pay"},
    {"cart", "panier", "basket", "bag", "addtocart"},
    {"add", "added", "ajout", "ajoute", "addto"},
    {"remove", "removed", "suppression", "supprime", "retrait"},
    {"wishlist", "wish", "favoris", "favori", "favourite", "favorite", "envie", "souhait"},
    {"loyalty", "fidelite", "fid", "reward", "recompense", "rewards"},
    {"points", "point", "couronnes", "crowns", "cagnotte", "solde", "balance"},
    {"redeem", "redeemed", "redemption", "spent", "spend", "burn", "utilise", "depense"},
    {"earn", "earned", "gagne", "credite", "accrual", "gained"},
    {"book", "booking", "reservation", "reserve", "reserver", "reservation"},
    {"bet", "bets", "wager", "stake", "pari", "parier", "mise"},
    {"subscribe", "subscription", "abonnement", "abonne", "activation", "activate", "souscription"},
    {"watch", "watched", "video", "stream", "streaming", "vod", "play", "played", "visionnage", "regarder"},
    {"read", "article", "lecture", "lire", "reading"},
    {"consume", "consumption", "consommation", "content", "contenu"},
    {"recipe", "recette", "cook", "cooked", "cuisine"},
    {"search", "recherche", "browse", "parcourir", "explore", "catalogue", "catalog", "rayon"},
    {"product", "produit", "item", "article", "sku", "fiche"},
    {"promo", "promotion", "promotions", "offre", "offer", "deal", "coupon", "coupons", "voucher", "bon"},
    {"store", "magasin", "shop", "boutique", "enseigne", "outlet"},
    {"account", "compte", "inscription", "signup", "registration", "register", "adhesion"},
    {"created", "creation", "create", "cree", "opened", "firstopen", "started"},
    {"login", "logged", "connexion", "signin", "auth", "authentication"},
    {"logout", "logoff", "deconnexion"},
    {"amount", "montant", "value", "revenue", "total", "price", "prix", "cost"},
    {"fuel", "carburant", "charge", "charging", "kwh", "recharge"},
    {"deposit", "depot", "withdraw", "withdrawal", "retrait", "winnings", "gains"},
    {"loyaltycard", "carte", "card"},
    {"ticket", "tickets", "billet", "seance"},
    {"game", "jeu", "gaming", "challenge"},
    {"survey", "sondage", "questionnaire", "review", "avis"},
]
_ALIAS_INDEX: Dict[str, int] = {}
for _i, _grp in enumerate(ALIAS_GROUPS):
    for _t in _grp:
        _ALIAS_INDEX[_t] = _i

# Name-token -> (category, kpi_kind) fallback when no catalog event matches but the name
# clearly denotes a conversion / consumption action.
CONVERSION_NAME_HINTS = [
    (("purchase", "purchased", "order", "checkout", "buy", "bought", "achat", "commande", "paiement", "payment"), "Purchase", "business"),
    (("addtocart", "add_to_cart", "added_to_cart", "cart", "panier", "basket"), "Add to cart", "business"),
    # Fuel / mobility payment. The catalogue's `ev_charging_fuel` vertical already treats
    # `fuel_purchase` as a business conversion, but names like `payinapp` share no token
    # with it, so they fell through to "usage" and the app's core monetised action went
    # uncounted. Tokens are kept narrow on purpose: bare "fuel" would swallow
    # `fuel_price_viewed`, and bare "pay" would swallow `paywall_shown`.
    (("payinapp", "pay_in_app", "fuel_purchase", "refuel", "fillup", "fill_up",
      "pay_at_pump", "payatpump"), "Purchase", "business"),
    (("booking", "book", "reservation", "reserve", "reserver"), "Reservation", "business"),
    (("bet", "wager", "stake", "pari", "mise"), "Purchase", "business"),
    (("subscribe", "subscription", "abonnement", "activation"), "Activation", "business"),
    (("loyalty", "fidelite", "points", "reward", "redeem", "cagnotte"), "Loyalty", "loyalty"),
    (("watch", "video", "stream", "vod", "play", "read_article", "recipe_cooked", "consume"), "Consume content/product", "usage"),
]

# Country/region -> probable currency for the value amount (heuristic).
COUNTRY_CURRENCY = {
    "FR": "EUR", "DE": "EUR", "ES": "EUR", "IT": "EUR", "PT": "EUR", "NL": "EUR",
    "BE": "EUR", "IE": "EUR", "AT": "EUR", "FI": "EUR", "GR": "EUR", "LU": "EUR",
    "MA": "MAD", "GB": "GBP", "UK": "GBP", "US": "USD", "CA": "CAD", "CH": "CHF",
    "SE": "SEK", "NO": "NOK", "DK": "DKK", "PL": "PLN", "BR": "BRL", "AU": "AUD",
}

# Monetary-value heuristic thresholds (value per event = total_value / total_count).
_MONEY_STRONG = 5.0    # >= -> High confidence monetary
_MONEY_MIN = 3.0       # >= -> monetary (Medium confidence)
_MONEY_AMBIG_HI = 3.0  # (1.5, 3) -> ambiguous small quantity
_COUNTER_HI = 1.5      # <= -> plain per-event counter (value ~= count)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _num(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _norm(s: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(s or "").lower())


def _tokens(s: Any) -> List[str]:
    raw = re.split(r"[^a-z0-9]+", str(s or "").lower())
    return [t for t in raw if t and len(t) > 2 and t not in GENERIC_TOKENS]


def _concepts(tokens: Sequence[str]) -> set:
    """Map tokens to concept ids (alias group id, or the token itself if ungrouped)."""
    out = set()
    for t in tokens:
        out.add(f"g{_ALIAS_INDEX[t]}" if t in _ALIAS_INDEX else t)
    return out


def _rate(num: float, den: float) -> Optional[float]:
    return (num / den) if den else None


# --------------------------------------------------------------------------- #
# 1. Aggregation
# --------------------------------------------------------------------------- #
def aggregate_custom_events(events: Sequence[dict], exclude_email: bool = True,
                            exclude_name_prefixes: Sequence[str] = ()) -> List[dict]:
    """Aggregate custom-location events by name with the attribution split of count+value.

    `exclude_name_prefixes` drops in-app CAMPAIGN impressions that also live under
    `location:custom` (e.g. ``banner - ...``) so the conversion/taxonomy stays purely
    BEHAVIOURAL. Those campaign rows are analysed as campaigns instead (see
    `campaign_inventory.split_events` / `extract_inapp_campaigns`).
    """
    prefixes = tuple(p.lower() for p in (exclude_name_prefixes or ()))
    agg: Dict[str, dict] = {}
    for e in events or []:
        if (e.get("location") or "").lower() != "custom":
            continue
        name = e.get("name") or ""
        if exclude_email and name.strip().lower() in EMAIL_EVENT_NAMES:
            continue
        if prefixes and name.strip().lower().startswith(prefixes):
            continue
        conv = (e.get("conversion") or "unattributed").lower()
        if conv not in ("direct", "indirect", "unattributed"):
            conv = "unattributed"
        cnt = _num(e.get("count"))
        val = _num(e.get("value"))
        row = agg.setdefault(name, {
            "name": name,
            "direct": {"count": 0.0, "value": 0.0},
            "indirect": {"count": 0.0, "value": 0.0},
            "unattributed": {"count": 0.0, "value": 0.0},
        })
        row[conv]["count"] += cnt
        row[conv]["value"] += val

    out = []
    for row in agg.values():
        tc = sum(row[k]["count"] for k in ("direct", "indirect", "unattributed"))
        tv = sum(row[k]["value"] for k in ("direct", "indirect", "unattributed"))
        attr_c = row["direct"]["count"] + row["indirect"]["count"]
        attr_v = row["direct"]["value"] + row["indirect"]["value"]
        row["total_count"] = int(tc)
        row["total_value"] = round(tv, 4)
        row["attributed_count"] = int(attr_c)
        row["attributed_value"] = round(attr_v, 4)
        row["attr_count_rate"] = _rate(attr_c, tc)
        row["attr_value_rate"] = _rate(attr_v, tv)
        row["value_per_event"] = _rate(tv, tc) or 0.0
        out.append(row)
    out.sort(key=lambda r: r["total_count"], reverse=True)
    return out


# --------------------------------------------------------------------------- #
# 2. Catalog resolution + classification
# --------------------------------------------------------------------------- #
def load_catalog(path: Optional[str] = None) -> dict:
    with open(path or DEFAULT_CATALOG, encoding="utf-8") as fh:
        return json.load(fh)


def resolve_vertical(catalog: dict, vertical: Optional[str]) -> dict:
    """Merge all_verticals + the client's vertical events (specific overrides generic)."""
    vmap = catalog.get("vertical_map", {})
    verts = catalog.get("verticals", {})
    key = None
    if vertical:
        v = vertical.strip().lower()
        if v in verts:
            key = v
        elif v in vmap:
            key = vmap[v]
    book_key = key or "all_verticals"
    merged: Dict[str, dict] = {}
    for ev in verts.get("all_verticals", {}).get("events", []):
        merged[ev["custom_name"].lower()] = ev
    if book_key != "all_verticals":
        for ev in verts.get(book_key, {}).get("events", []):
            merged[ev["custom_name"].lower()] = ev
    return {
        "book_key": book_key,
        "label": verts.get(book_key, {}).get("label", book_key),
        "events": list(merged.values()),
        "fallback": book_key == "all_verticals" and bool(vertical),
    }


def classify_event(name: str, catalog_events: Sequence[dict]) -> dict:
    """Match a client event name to the best catalog event with a confidence level."""
    ntok = _tokens(name)
    ncon = _concepts(ntok)
    nnorm = _norm(name)
    best = None
    best_score = 0.0
    for ce in catalog_events:
        cname = ce["custom_name"]
        if _norm(cname) == nnorm and nnorm:
            best, best_score = ce, 999.0
            break
        ccon = _concepts(_tokens(cname))
        if not ccon or not ncon:
            continue
        shared = ncon & ccon
        if not shared:
            continue
        score = len(shared) + len(shared) / max(len(ccon), 1)
        if score > best_score:
            best, best_score = ce, score

    if best is None:
        # name-token fallback to a conversion category (no catalog event)
        low = name.lower().replace(" ", "_")
        for toks, category, kind in CONVERSION_NAME_HINTS:
            if any(t in low for t in toks):
                return {
                    "matched": None, "category": category, "kpi_kind": kind,
                    "is_conversion": True, "catalog_value_property": None,
                    "has_currency_property": False, "confidence": "Low",
                    "basis": "name-token conversion hint",
                }
        return {
            "matched": None, "category": "Unknown", "kpi_kind": "usage",
            "is_conversion": False, "catalog_value_property": None,
            "has_currency_property": False, "confidence": None,
            "basis": "no catalog match",
        }

    if best_score >= 999.0:
        conf = "High"
    else:
        shared_n = len(_concepts(ntok) & _concepts(_tokens(best["custom_name"])))
        conf = "Medium" if shared_n >= 2 else "Low"
    return {
        "matched": best["custom_name"],
        "category": best["category"],
        "kpi_kind": best["kpi_kind"],
        "is_conversion": bool(best["is_conversion"]),
        "catalog_value_property": best.get("value_property"),
        "has_currency_property": bool(best.get("has_currency_property")),
        "confidence": conf,
        "basis": "exact name" if conf == "High" else "token/alias overlap",
    }


# --------------------------------------------------------------------------- #
# 3. Monetary value + currency
# --------------------------------------------------------------------------- #
def detect_monetary_value(row: dict) -> dict:
    """Decide whether an event's `value` behaves like a monetary amount vs a counter."""
    tc = row["total_count"]
    tv = row["total_value"]
    vpe = row["value_per_event"]
    if tv <= 0:
        return {"value_is_monetary": False, "confidence": "High",
                "value_per_event": round(vpe, 4), "reason": "no value reported"}
    if vpe >= _MONEY_MIN:
        conf = "High" if vpe >= _MONEY_STRONG else "Medium"
        return {"value_is_monetary": True, "confidence": conf,
                "value_per_event": round(vpe, 4),
                "reason": f"avg value/event {vpe:.2f} >> 1 (looks like an amount)"}
    if vpe > _COUNTER_HI:
        return {"value_is_monetary": False, "confidence": "Low",
                "value_per_event": round(vpe, 4),
                "reason": f"avg value/event {vpe:.2f} ambiguous (small quantity?)"}
    return {"value_is_monetary": False, "confidence": "High",
            "value_per_event": round(vpe, 4),
            "reason": f"value ~= count (avg {vpe:.2f}) -> per-event counter, not an amount"}


def currency_for_brand(brand: Optional[str] = None, region: Optional[str] = None,
                       country: Optional[str] = None,
                       override: Optional[str] = None) -> dict:
    """Probable currency for interpreting monetary values. Heuristic + overridable."""
    if override:
        return {"currency": override.upper(), "confidence": "High",
                "basis": "explicit config override"}
    if country:
        cur = COUNTRY_CURRENCY.get(country.strip().upper())
        if cur:
            return {"currency": cur, "confidence": "Medium",
                    "basis": f"brand country {country.upper()}"}
    if region:
        r = region.strip().lower()
        if r == "eu":
            return {"currency": "EUR", "confidence": "Low",
                    "basis": "region=eu (EUR assumed; confirm per market)"}
        if r == "us":
            return {"currency": "USD", "confidence": "Low",
                    "basis": "region=us (USD assumed)"}
    return {"currency": None, "confidence": None,
            "basis": "currency unknown — provide --currency or brand country"}


def _amounts(row: dict, currency: Optional[str]) -> dict:
    d, i, u = row["direct"], row["indirect"], row["unattributed"]
    attributed = d["value"] + i["value"]
    return {
        "currency": currency,
        "direct_amount": round(d["value"], 2),
        "indirect_amount": round(i["value"], 2),
        "attributed_amount": round(attributed, 2),
        "unattributed_amount": round(u["value"], 2),
        "total_amount": round(row["total_value"], 2),
        "caveat": "`value` is a client-declared number, not guaranteed currency.",
    }


# --------------------------------------------------------------------------- #
# 4. Conversion KPIs + taxonomy
# --------------------------------------------------------------------------- #
def _attr_block(row: dict) -> dict:
    return {
        "direct": {"count": int(row["direct"]["count"])},
        "indirect": {"count": int(row["indirect"]["count"])},
        "unattributed": {"count": int(row["unattributed"]["count"])},
        "attr_count_rate": row["attr_count_rate"],
    }


def build_events(agg: List[dict], catalog_events: Sequence[dict],
                 currency_info: dict) -> List[dict]:
    """Attach classification + monetary flags (+ amounts) to each aggregated event."""
    out = []
    cur = currency_info.get("currency")
    for row in agg:
        cls = classify_event(row["name"], catalog_events)
        money = detect_monetary_value(row)
        item = {
            "name": row["name"],
            "total_count": row["total_count"],
            "total_value": row["total_value"],
            "attribution": _attr_block(row),
            "attr_count_rate": row["attr_count_rate"],
            "attr_value_rate": row["attr_value_rate"],
            "classification": cls,
            "value_monetary": money,
        }
        if money["value_is_monetary"]:
            item["amounts"] = _amounts(row, cur)
        out.append(item)
    return out


def detect_conversion_kpis(events: List[dict]) -> List[dict]:
    """Return events flagged as conversion KPIs (business / usage-consumption / loyalty)."""
    kpis = []
    for ev in events:
        cls = ev["classification"]
        if not cls.get("is_conversion"):
            continue
        kpis.append({
            "name": ev["name"],
            "category": cls["category"],
            "kpi_kind": cls["kpi_kind"],
            "confidence": cls["confidence"],
            "matched_catalog_event": cls["matched"],
            "total_count": ev["total_count"],
            "attribution": ev["attribution"],
            "attr_count_rate": ev["attr_count_rate"],
            "value_is_monetary": ev["value_monetary"]["value_is_monetary"],
            "amounts": ev.get("amounts"),
            "should_carry_value": bool(cls.get("catalog_value_property")),
        })
    kpis.sort(key=lambda k: k["total_count"], reverse=True)
    return kpis


def taxonomy(events: List[dict]) -> dict:
    by_cat: Dict[str, dict] = {}
    by_kind: Dict[str, dict] = {}
    for ev in events:
        cls = ev["classification"]
        for bucket, key in ((by_cat, cls["category"]), (by_kind, cls["kpi_kind"])):
            b = bucket.setdefault(key, {"events": 0, "count": 0, "value": 0.0})
            b["events"] += 1
            b["count"] += ev["total_count"]
            b["value"] += ev["total_value"]
    for bucket in (by_cat, by_kind):
        for b in bucket.values():
            b["value"] = round(b["value"], 2)
    return {"by_category": by_cat, "by_kpi_kind": by_kind}


# --------------------------------------------------------------------------- #
# 5. Opportunities
# --------------------------------------------------------------------------- #
def opportunity_gaps(events: List[dict], vertical: dict,
                     audit_value_index: Optional[dict] = None) -> dict:
    """Catalog events not sent (send_more) + events sent without a conversion value.

    `audit_value_index` (optional) = a `{normalized_event_name: facts}` map from the
    data-collection audit (`data_foundation.value_index(audit)`). When present, the
    "enrich value" verdict becomes a FACT instead of a heuristic: an event is skipped
    when the tagging plan shows it already carries an amount/value property, and it is
    flagged (higher confidence, `audit_backed=True`) when the plan confirms no value.
    """
    audit_value_index = audit_value_index or {}

    def _anorm(s):
        return re.sub(r"[^a-z0-9]+", "", str(s or "").lower())
    covered = set()
    for ev in events:
        m = ev["classification"].get("matched")
        if m and ev["classification"]["confidence"] in ("High", "Medium"):
            covered.add(m.lower())

    send_more = []
    for ce in vertical["events"]:
        if ce["custom_name"].lower() in covered:
            continue
        send_more.append({
            "custom_name": ce["custom_name"],
            "category": ce["category"],
            "kpi_kind": ce["kpi_kind"],
            "is_conversion": bool(ce["is_conversion"]),
            "carries_value": bool(ce.get("value_property")),
            "description": ce.get("description"),
            "confidence": "Medium",
            "why": "recommended for this vertical but not detected in the period",
        })
    # conversion-bearing gaps first
    send_more.sort(key=lambda o: (not o["is_conversion"], o["kpi_kind"] != "business",
                                  o["custom_name"]))

    enrich_value = []
    for ev in events:
        cls = ev["classification"]
        if not cls.get("is_conversion"):
            continue
        should = bool(cls.get("catalog_value_property")) or cls["kpi_kind"] == "business"
        if not should:
            continue
        facts = audit_value_index.get(_anorm(ev["name"]))
        if facts is not None:
            # Tagging plan is authoritative: skip if it already carries a value/amount.
            if facts.get("has_value") or facts.get("carries_amount") or facts.get("value_property"):
                continue
        elif ev["value_monetary"]["value_is_monetary"]:
            continue  # heuristic: already carries an amount
        enrich_value.append({
            "name": ev["name"],
            "category": cls["category"],
            "matched_catalog_event": cls["matched"],
            "expected_value_property": cls.get("catalog_value_property"),
            "current_value_per_event": ev["value_monetary"]["value_per_event"],
            "confidence": ("Medium" if facts else (cls["confidence"] or "Low")),
            "audit_backed": bool(facts),
            "why": ("conversion event with no monetary value — send the purchase/transaction "
                    "amount (+ currency) so Airship can attribute revenue"
                    + (" (confirmed by the tagging plan)" if facts else "")),
        })
    enrich_value.sort(key=lambda o: -next(
        (e["total_count"] for e in events if e["name"] == o["name"]), 0))
    return {"send_more": send_more, "enrich_value": enrich_value}


# --------------------------------------------------------------------------- #
# 6. Orchestrator
# --------------------------------------------------------------------------- #
def value_measurability(events: List[dict], tagging_monetary: Optional[dict] = None) -> dict:
    """One graded verdict on whether this account's conversions can be valued at all.

    The counter-versus-amount heuristic already existed, and so did the tagging plan's
    declaration of monetary events and the list of conversions that ought to carry one —
    in three different places, none of them a verdict. So a report could describe an
    account's events in detail and never say the thing that decides what Airship can prove:
    that every conversion is a count, and no message can therefore be tied to an amount.

    Two sources, and they disagree in a way worth reporting:
      the FEED says what is arriving (`detect_monetary_value` on the observed `value`);
      the TAGGING PLAN says what was declared (`data_foundation.monetary_summary`).
    Declared but not arriving is a different problem from never declared — the first is a
    wiring bug someone can fix this sprint, the second is a product decision.

    Grades: `revenue` (amounts arriving, and they cover most conversion volume) ·
    `partial` (some arriving, conversions that should carry one do not) ·
    `declared_not_flowing` (the plan declares amounts, the feed carries none) ·
    `counters` (nothing anywhere carries an amount).
    """
    convs = [e for e in events or [] if (e.get("classification") or {}).get("is_conversion")]
    valued = [e for e in events or []
              if (e.get("value_monetary") or {}).get("value_is_monetary")]
    conv_total = sum(_num(e.get("total_count")) for e in convs)
    valued_conv = [e for e in valued if (e.get("classification") or {}).get("is_conversion")]
    valued_count = sum(_num(e.get("total_count")) for e in valued_conv)
    # Conversions the catalogue expects to carry an amount, and do not. `kpi_kind ==
    # "business"` is included on the same reasoning as `opportunity_gaps`: a purchase with
    # no amount is a gap whether or not the catalogue names the property.
    expected = [e for e in convs
                if ((e.get("classification") or {}).get("catalog_value_property")
                    or (e.get("classification") or {}).get("kpi_kind") == "business")
                and not (e.get("value_monetary") or {}).get("value_is_monetary")]
    declared = bool((tagging_monetary or {}).get("has_monetary"))
    share = (valued_count / conv_total) if conv_total else 0.0

    if valued_conv and share >= 0.5 and not expected:
        grade = "revenue"
    elif valued:
        grade = "partial"
    elif declared:
        grade = "declared_not_flowing"
    else:
        grade = "counters"
    return {
        "grade": grade,
        "revenue_attributable": grade in ("revenue", "partial"),
        "valued_events": len(valued),
        "valued_conversions": len(valued_conv),
        "conversion_events": len(convs),
        "conversion_volume": conv_total,
        "valued_volume": valued_count,
        "valued_share": round(share, 4),
        "declared_in_plan": declared,
        "declared_count": _num((tagging_monetary or {}).get("count")),
        # Named, so the report can say WHICH conversion is missing its amount instead of
        # how many are — a count is not an action.
        "missing_amount": [e["name"] for e in sorted(
            expected, key=lambda x: -_num(x.get("total_count")))][:10],
        "units": (tagging_monetary or {}).get("units") or [],
    }


def analyze(events: Sequence[dict], vertical: Optional[str] = None,
            brand: Optional[str] = None, region: Optional[str] = None,
            country: Optional[str] = None, currency: Optional[str] = None,
            catalog: Optional[dict] = None,
            exclude_name_prefixes: Sequence[str] = ("banner - ",),
            audit_value_index: Optional[dict] = None,
            tagging_monetary: Optional[dict] = None) -> dict:
    catalog = catalog or load_catalog()
    vinfo = resolve_vertical(catalog, vertical)
    currency_info = currency_for_brand(brand, region, country, currency)

    agg = aggregate_custom_events(events, exclude_name_prefixes=exclude_name_prefixes)
    ev_items = build_events(agg, vinfo["events"], currency_info)
    kpis = detect_conversion_kpis(ev_items)
    tax = taxonomy(ev_items)
    opps = opportunity_gaps(ev_items, vinfo, audit_value_index=audit_value_index)

    total_count = sum(e["total_count"] for e in ev_items)
    total_value = round(sum(e["total_value"] for e in ev_items), 2)
    monetary_events = [e for e in ev_items if e["value_monetary"]["value_is_monetary"]]
    looks_monetary = any(k["value_is_monetary"] for k in kpis)

    return {
        "vertical": {"input": vertical, "book_key": vinfo["book_key"],
                     "label": vinfo["label"], "fallback_all_verticals": vinfo["fallback"]},
        "currency": currency_info,
        "totals": {
            "distinct_events": len(ev_items),
            "total_count": total_count,
            "total_value": total_value,
            "monetary_event_count": len(monetary_events),
            "value_looks_monetary": looks_monetary,
            "value_note": ("At least one conversion KPI carries an amount-like value."
                           if looks_monetary else
                           "No event's value looks like a monetary amount (values behave as "
                           "per-event counters) — amounts not reported."),
        },
        "events": ev_items,
        "conversion_kpis": kpis,
        "taxonomy": tax,
        "opportunities": opps,
        # The graded verdict, computed here so every report carries the same one rather
        # than each re-deriving it from `totals` and `opportunities.enrich_value`.
        "value_measurability": value_measurability(ev_items, tagging_monetary),
    }


# --------------------------------------------------------------------------- #
# IO + CLI
# --------------------------------------------------------------------------- #
def _load_events(path: str) -> List[dict]:
    if path.lower().endswith(".csv"):
        import csv
        with open(path, newline="", encoding="utf-8") as fh:
            return [
                {"name": r.get("name"), "location": r.get("location"),
                 "conversion": r.get("conversion"), "count": r.get("count"),
                 "value": r.get("value")}
                for r in csv.DictReader(fh)
            ]
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        return data.get("events", [])
    return data


def _parse_args(argv):
    opts = {"vertical": None, "region": None, "country": None, "currency": None,
            "brand": None}
    pos = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            key = a[2:]
            val = argv[i + 1] if i + 1 < len(argv) else None
            opts[key] = val
            i += 2
        else:
            pos = a
            i += 1
    return pos, opts


def _selftest():
    """Cover the value-measurability grades, which decide what the report may claim."""
    def ev(name, count, monetary, conversion=True, kind="business", prop=None):
        return {"name": name, "total_count": count,
                "classification": {"is_conversion": conversion, "kpi_kind": kind,
                                   "catalog_value_property": prop},
                "value_monetary": {"value_is_monetary": monetary}}

    # A property-listings shape: millions of conversions, not one euro among them.
    counters = value_measurability([ev("lead_classified_form_submit", 2_407_801, False),
                                    ev("listing_view", 52_272_000, False, kind="usage")])
    assert counters["grade"] == "counters" and not counters["revenue_attributable"]
    assert counters["missing_amount"] == ["lead_classified_form_submit"], counters

    # Declared in the plan, absent from the feed — a wiring bug, not a product decision,
    # and it must not collapse into the same grade as "never declared".
    wired = value_measurability([ev("purchase", 100, False)],
                                {"has_monetary": True, "count": 3, "units": ["EUR"]})
    assert wired["grade"] == "declared_not_flowing" and wired["declared_in_plan"]

    # Amounts arriving on most of the volume, nothing expected-and-missing.
    rev = value_measurability([ev("purchase", 1_000, True),
                                ev("app_open", 50_000, False, conversion=False)])
    assert rev["grade"] == "revenue" and rev["revenue_attributable"]
    assert rev["valued_share"] == 1.0, rev["valued_share"]

    # Amounts on a minority of conversion volume is `partial`, never `revenue`.
    part = value_measurability([ev("purchase", 100, True),
                                ev("reservation", 9_900, False)])
    assert part["grade"] == "partial" and part["valued_share"] < 0.5, part
    print("event_analysis value-measurability self-test OK", file=sys.stderr)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    path, opts = _parse_args(sys.argv[1:])
    if "selftest" in opts:
        return _selftest()
    if not path:
        sys.exit("Provide an events.json/.csv path.")
    events = _load_events(path)
    result = analyze(events, vertical=opts.get("vertical"), brand=opts.get("brand"),
                     region=opts.get("region"), country=opts.get("country"),
                     currency=opts.get("currency"))
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
