#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic Airship *Goal* qualification engine — the core of the light "Goals review".

Pure functions over two inputs and nothing else (no network, no Reports API):

  * ``audit``  — the tagging-plan audit dict from ``data_foundation.load(...)``
                 (``inventory`` + ``analysis`` produced by parse/analyze_tagging_plan).
  * ``context``— brand/vertical facts, from ``brand.json`` (web research) merged with
                 what the analyzer already inferred (``analysis.chosenVertical``).

and two bundled catalogues:

  * ``airship_goal_sources.json`` — Airship-side goal sources: native signals (no client
    instrumentation), predefined-event archetypes (a MATCHER and a naming standard, never
    a source of activatable candidates), native numeric properties, configuration modes,
    anti-pattern rules and product limits.
  * ``goals-by-vertical.json``    — which archetypes matter, and in what order, per
    vertical and business model. This is the contextualisation lever.

THE STRUCTURING RULE — three families, never mixed:

  A ``collected``  the client already sends it (custom events, tags, subscription
                   lists) -> can be configured as a Goal now.
  B ``native``     Airship emits it with zero client instrumentation (channel
                   registration, app open, notification opt-in, named-user
                   association, NPS...) -> can be configured now too.
  C ``gap``        an archetype that matters for this brand but is NOT tracked ->
                   a measurement recommendation, never a goal shortlist entry.

An Airship predefined event (``purchased``, ``added_to_cart``, ...) is NOT available just
because Airship knows the name: the client has to send it. Absent from the tagging plan,
under its Airship name or a near name, it is family C.

Known limit, stated rather than hidden: the inventory counts **occurrences**, not unique
channels. Nothing here can compute a per-user frequency or a penetration rate; the report
says so and points at the "Channels per goal" / "Goal frequency per channel" reports that
only exist once the goal is configured.

Output (``build()`` -> ``goals.json``) is English-only; the French strings in the catalogue
are aliases used to match French event names, never to write prose.

CLI:
    python goal_candidates.py <inventory.json> <analysis.json> [brand.json] [-o goals.json]
    python goal_candidates.py --self-test
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from typing import Any, Dict, List, Optional, Sequence

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import analyze_tagging_plan as atp  # noqa: E402  (alias groups, intent taxonomy)

GOAL_SOURCES_PATH = os.path.join(_HERE, "airship_goal_sources.json")
GOALS_BY_VERTICAL_PATH = os.path.join(_HERE, "goals-by-vertical.json")

# A goal only produces a usable Goal-attribution read once it fires often enough for a
# per-message split to mean anything. Stated in the report's methodology, not hidden.
ATTRIBUTION_READY_MIN = 1000
# Below this many occurrences an event is not thin, it is noise: a shortlist that offers
# `later_survey_preference` (2 occurrences in the window) next to a 58k play event spends
# the reader's trust for nothing. Such events stay visible in the candidate tables,
# never in the recommended tiers.
GOAL_VIABLE_MIN = 50
# Below this many occurrences a frequency-over-a-period goal cannot separate users.
FREQUENCY_MIN_OCCURRENCES = 5000
# An event firing on more than this share of all tracked occurrences is close to
# universal: as a plain count it ranks nobody.
UNIVERSAL_SHARE = 0.40
# Floor for a fuzzy predefined match. A wrong archetype is worse than none: it puts the
# event in the wrong funnel stage and recommends renaming to a standard it does not
# belong to. Set so a shared root still matches (`commande_validee` -> `purchased`, 0.85)
# but a single shared token does not (`item_to_bag` -> `browsed`, 0.57).
FUZZY_MATCH_MIN = 0.60

_STAGES = ("acquisition", "activation", "consideration", "conversion", "loyalty", "retention")

# Audit event intent -> funnel stage. `other` stays unmapped on purpose: an event whose
# intent the analyzer could not read is exactly the case where the report must ask the
# client rather than guess a stage.
_STAGE_OF_INTENT = {
    "conversion": "conversion",
    "consideration": "consideration",
    "browse": "consideration",
    "account": "activation",
    "loyalty": "loyalty",
    "engagement": "loyalty",
    "location": "consideration",
    "lifecycle": "retention",
}

_INTENT_WEIGHT = {
    "conversion": 1.00, "consideration": 0.78, "loyalty": 0.66, "account": 0.62,
    "browse": 0.44, "engagement": 0.40, "location": 0.34, "lifecycle": 0.32,
    "other": 0.25,
}

_NUMERIC_KINDS = {"number", "amount"}
_CURRENCY_RE = re.compile(r"(currency|devise|iso_?code|curr)", re.I)
_AMOUNT_RE = re.compile(r"(amount|montant|value|valeur|price|prix|revenue|total|cost)", re.I)
# A property being numeric is not enough to make it a threshold goal: `offer_id` and
# `priority` are numbers nobody wants a goal on. A threshold only means something on a
# property that measures a MAGNITUDE the business cares about.
_MAGNITUDE_RE = re.compile(
    r"(amount|montant|value|valeur|price|prix|revenue|total|cost|spend|basket|panier|"
    r"duration|duree|elapsed|watch|read_?time|progress|percent|completion|"
    r"quantity|qty|nombre|items?_?count|points?|solde|balance|credit|score|"
    r"time_?in_?app|seconds|minutes)", re.I)


# --------------------------------------------------------------------------- #
# Catalogue loading
# --------------------------------------------------------------------------- #
def _read_json(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


_CATALOG: Optional[dict] = None
_VERTICALS: Optional[dict] = None


def catalog(path: Optional[str] = None) -> dict:
    """The Airship goal-source catalogue (memoised)."""
    global _CATALOG
    if path:
        return _read_json(path)
    if _CATALOG is None:
        _CATALOG = _read_json(GOAL_SOURCES_PATH)
    return _CATALOG


def verticals(path: Optional[str] = None) -> dict:
    """The per-vertical goal-archetype funnel (memoised)."""
    global _VERTICALS
    if path:
        return _read_json(path)
    if _VERTICALS is None:
        _VERTICALS = _read_json(GOALS_BY_VERTICAL_PATH)
    return _VERTICALS


def _archetypes() -> List[dict]:
    return catalog().get("predefinedArchetypes") or []


def _archetype(name: str) -> Optional[dict]:
    return next((a for a in _archetypes() if a.get("name") == name), None)


def _native_signals() -> List[dict]:
    return catalog().get("nativeSignals") or []


def _config_mode(mode_id: str) -> dict:
    return next((m for m in catalog().get("configModes") or [] if m.get("id") == mode_id), {})


# --------------------------------------------------------------------------- #
# Context: brand, vertical, business model, instrumentation reality
# --------------------------------------------------------------------------- #
def _slug(s: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s or "").lower()).strip("_")


def resolve_vertical_key(raw: Any) -> str:
    """Map anything (analyzer vertical, benchmarks key, free text) to a goals vertical key."""
    v = verticals()
    keys = v.get("verticals") or {}
    s = str(raw or "").strip()
    if s in keys:
        return s
    aliases = v.get("aliases") or {}
    sl = _slug(s)
    if sl in aliases:
        return aliases[sl]
    # tolerate "Sport & Gaming" -> "sport_gaming", "Restaurant & QSR" -> "restaurant_qsr"
    for k in keys:
        if _slug(k) == sl:
            return k
    for alias, target in aliases.items():
        if alias and (alias in sl or sl in alias) and len(alias) >= 4:
            return target
    return "all verticals"


def resolve_context(audit: dict, brand: Optional[dict] = None) -> dict:
    """Build the `ctx` every candidate function takes.

    `brand` is the optional ``brand.json`` written from web research:
        {"name", "vertical", "business_model", "description", "markets",
         "conversion_meaning", "notes", "sources": [{"title", "url"}]}
    Anything absent falls back to what the tagging-plan analyzer inferred, so the engine
    runs with no brand file at all.
    """
    brand = dict(brand or {})
    an = (audit or {}).get("analysis") or {}
    vkey = resolve_vertical_key(brand.get("vertical") or an.get("chosenVertical")
                                or an.get("suggestedVertical"))
    vdoc = verticals()
    vert = (vdoc.get("verticals") or {}).get(vkey) or {}
    bm_id = brand.get("business_model") or vert.get("businessModel") \
        or vdoc.get("defaultBusinessModel")
    bm = next((b for b in vdoc.get("businessModels") or [] if b.get("id") == bm_id), {})

    prov = an.get("provenance") or {}
    src = (prov.get("sourceSplit") or {}).get("events") or {}
    sdk, api = int(src.get("SDK", 0)), int(src.get("API", 0))
    tot = sdk + api + int(src.get("Unknown", 0))

    return {
        "brand": brand.get("name") or (an.get("profile") or "the brand"),
        "vertical_key": vkey,
        "vertical": vert,
        "vertical_label": vert.get("label") or vkey,
        "vertical_source": ("brand.json" if brand.get("vertical")
                            else "tagging-plan analyzer (chosenVertical)"),
        "business_model": bm,
        "business_model_id": bm_id,
        "conversion_meaning": (brand.get("conversion_meaning")
                               or vert.get("conversionMeaning")
                               or (bm.get("conversionMeaning") if bm else None)),
        "brand_description": brand.get("description"),
        "markets": brand.get("markets"),
        # Archetypes the vertical recommends but this particular business cannot have.
        # A vertical is a coarse instrument: "Media" spans hybrid SVOD players and
        # entirely free public broadcasters, so its funnel lists `purchased`. Telling a
        # free, ad-free service to instrument a purchase is not a gap, it is a wrong
        # answer — the brand research is what knows, so it is what declares it.
        "excluded_archetypes": sorted({atp._norm(a) for a
                                       in (brand.get("not_applicable_archetypes") or [])}),
        "excluded_attributes": sorted({atp._norm(a) for a
                                       in (brand.get("not_applicable_attributes") or [])}),
        "brand_sources": brand.get("sources") or [],
        "source_split": {"sdk": sdk, "api": api, "total": tot,
                         "api_share": (api / tot) if tot else None,
                         "sdk_share": (sdk / tot) if tot else None},
        "storage_verdict": (prov.get("storageLevel") or {}).get("verdict"),
        "has_subscription_lists": bool(((audit or {}).get("inventory") or {})
                                       .get("subscriptionLists")),
        "has_tags": bool(((audit or {}).get("inventory") or {}).get("tags")),
    }


# --------------------------------------------------------------------------- #
# Predefined-archetype matching (exact, then alias, then concept overlap)
# --------------------------------------------------------------------------- #
def _alias_pool(arch: dict) -> List[str]:
    al = arch.get("aliases") or {}
    return [arch.get("name", "")] + list(al.get("en") or []) + list(al.get("fr") or [])


def match_predefined(name: str) -> Optional[dict]:
    """Match a tracked event name against the Airship predefined-event archetypes.

    Three passes, most-confident first: exact normalised name, a declared EN/FR alias, then
    a concept overlap computed with the analyzer's own bilingual alias groups (so
    ``commande_validee`` reaches ``purchased``). Returns
    ``{"name", "how", "score", "funnel_stage", "category"}`` or None.
    """
    n = atp._norm(name)
    if not n:
        return None
    for arch in _archetypes():
        if n == atp._norm(arch["name"]):
            return {"name": arch["name"], "how": "exact", "score": 1.0,
                    "funnel_stage": arch.get("funnelStage"), "category": arch.get("category")}
    for arch in _archetypes():
        if any(n == atp._norm(a) for a in _alias_pool(arch)):
            return {"name": arch["name"], "how": "alias", "score": 0.9,
                    "funnel_stage": arch.get("funnelStage"), "category": arch.get("category")}

    cand = atp._concepts(name)
    if not cand:
        return None
    best, best_score = None, 0.0
    for arch in _archetypes():
        for alias in _alias_pool(arch):
            ac = atp._concepts(alias)
            if not ac:
                continue
            overlap = cand & ac
            if not overlap:
                continue
            # Symmetric (F1) overlap, NOT coverage-of-the-alias. Scoring on the alias
            # side alone lets a one-concept alias claim anything that shares that single
            # concept: `item_to_bag` matched `browsed` via `product_view` on "item"
            # alone, beating the add-to-cart archetype it obviously belongs to. Requiring
            # the event name to be mostly explained by the alias too kills that class.
            score = 0.85 * 2 * len(overlap) / (len(cand) + len(ac))
            if score > best_score:
                best, best_score = arch, score
    if best and best_score >= FUZZY_MATCH_MIN:
        return {"name": best["name"], "how": "fuzzy", "score": round(best_score, 2),
                "funnel_stage": best.get("funnelStage"), "category": best.get("category")}
    return None


# --------------------------------------------------------------------------- #
# Instrumentation route & effort — read off the client's REAL source split
# --------------------------------------------------------------------------- #
def instrumentation_route(item: dict, audit: dict, ctx: Optional[dict] = None) -> dict:
    """Recommend SDK vs Custom Events API for a candidate, from the client's own split.

    A client already sending most events server-side has a CRM that can emit one more
    metric without an app release; a client who is SDK-only is better served by the SDK
    templates for the predefined events. That is what turns a generic recommendation into
    a founded one. Returns ``{"route", "effort", "why"}``.
    """
    ctx = ctx or resolve_context(audit)
    if item.get("family") in ("collected", "native"):
        return {"route": "already_tracked", "effort": "low",
                "why": ("Already available on the project — configuring the goal is a "
                        "dashboard action, not a development one.")}

    split = ctx.get("source_split") or {}
    api_share = split.get("api_share")
    verdict = ctx.get("storage_verdict") or ""
    if api_share is not None and api_share >= 0.5:
        return {
            "route": "custom_events_api", "effort": "medium",
            "why": (f"{api_share*100:.0f}% of the events already tracked arrive through the "
                    f"server-side API, so this metric can be emitted from the same back end "
                    f"with no app release."),
        }
    if api_share is not None and api_share > 0:
        return {
            "route": "custom_events_api", "effort": "medium",
            "why": (f"A server-side pipe already exists ({api_share*100:.0f}% of tracked "
                    f"events arrive by API) — extending it avoids waiting for a release "
                    f"train, and lands the data at contact level rather than per device."),
        }
    hint = (" Today every event is SDK-sourced and stored at channel level"
            f"{' (' + verdict + ')' if verdict else ''}, so this one will be too unless the "
            f"client opens a server-side route.") if verdict else ""
    return {"route": "sdk", "effort": "high",
            "why": ("No server-side event pipe exists yet, so this goes through the mobile "
                    "SDK and therefore through an app release." + hint)}


# --------------------------------------------------------------------------- #
# Candidate construction helpers
# --------------------------------------------------------------------------- #
def _blank(**kw) -> dict:
    c = {
        "name": None, "family": "collected", "kind": "custom_event",
        "predefined_match": None, "setup_required": "none", "funnel_stage": None,
        "goal_tier": "diagnostic", "total": None, "share_of_occurrences": None,
        "config_modes": ["count"], "recommended_config": {"mode": "count", "period": None,
                                                          "property": None},
        "numeric_properties": [], "threshold_property": None,
        "has_value": False, "carries_amount": False,
        "inferred_unit": None, "unit_confidence": None, "value_property": None,
        "currency_property": None, "usable_properties": [], "properties_to_add": [],
        "blockers": [], "exclude": False, "exclude_reason": None,
        "attribution_ready": None, "instrumentation_route": "already_tracked",
        "effort": "low", "route_why": None, "questions": [], "question_to_client": None,
        "score": 0.0, "rationale": None, "source_detail": None,
    }
    c.update(kw)
    return c


def _vertical_priority(archetype: Optional[str], stage: Optional[str], ctx: dict) -> float:
    vert = ctx.get("vertical") or {}
    prio = vert.get("priorityArchetypes") or []
    if archetype and archetype in prio:
        # earlier in the list = more central to the vertical
        return 1.0 - 0.08 * prio.index(archetype)
    funnel = vert.get("funnel") or {}
    if archetype and any(archetype in (funnel.get(s) or []) for s in funnel):
        return 0.72
    if stage and (funnel.get(stage) or []):
        return 0.5
    return 0.42


def _stage_boost(stage: Optional[str], ctx: dict) -> float:
    bm = ctx.get("business_model") or {}
    return float((bm.get("boostStages") or {}).get(stage or "", 1.0))


def _volume_score(total: Optional[int], vmax: int) -> float:
    if not total or total <= 0 or vmax <= 0:
        return 0.15
    return min(1.0, math.log10(total + 1) / math.log10(vmax + 1))


def _score(cand: dict, ctx: dict, vmax: int) -> float:
    intent_w = _INTENT_WEIGHT.get(cand.get("_intent") or "other", 0.25)
    arche = (cand.get("predefined_match") or {}).get("name")
    vert_w = _vertical_priority(arche, cand.get("funnel_stage"), ctx)
    if cand.get("carries_amount"):
        value_w = 1.0
    elif cand.get("has_value") or cand.get("value_property"):
        value_w = 0.7
    else:
        value_w = 0.3
    props = cand.get("usable_properties") or []
    if any(p.get("kind") in _NUMERIC_KINDS for p in props):
        prop_w = 1.0
    elif any(p.get("kind") == "enum" for p in props):
        prop_w = 0.72
    elif props:
        prop_w = 0.5
    else:
        prop_w = 0.22
    vol_w = _volume_score(cand.get("total"), vmax) if cand.get("total") is not None else 0.6

    raw = (0.30 * intent_w + 0.25 * vert_w + 0.15 * value_w
           + 0.10 * prop_w + 0.20 * vol_w)
    return round(min(1.0, raw * _stage_boost(cand.get("funnel_stage"), ctx)), 3)


def _tier(score: float) -> str:
    if score >= 0.62:
        return "primary"
    if score >= 0.42:
        return "secondary"
    return "diagnostic"


def _period_for(total: Optional[int], vmax: int, ctx: dict) -> str:
    default = (ctx.get("business_model") or {}).get("defaultPeriod") or "weekly"
    if not total or vmax <= 0:
        return default
    share = total / float(vmax)
    if share >= 0.40:
        return "daily"
    if share <= 0.05:
        return "monthly"
    return default


def _config(cand: dict, ctx: dict, vmax: int) -> dict:
    """Which configuration modes are open, and which one to recommend."""
    modes = ["count"]
    total = cand.get("total")
    once_per_life = cand.get("_once_per_lifetime")
    if not once_per_life and (total is None or total >= FREQUENCY_MIN_OCCURRENCES):
        modes.append("frequency")
    numeric = cand.get("numeric_properties") or []
    magnitude = (next((p for p in numeric if p.get("kind") == "amount"), None)
                 or next((p for p in numeric
                          if p.get("name") == cand.get("value_property")), None)
                 or next((p for p in numeric
                          if _MAGNITUDE_RE.search(str(p.get("name") or ""))), None))
    if magnitude:
        modes.append("numeric_property")
    cand["config_modes"] = modes
    cand["threshold_property"] = magnitude.get("name") if magnitude else None
    if numeric and not magnitude:
        cand["blockers"].append(
            "The numeric properties collected here (" +
            ", ".join(str(p.get("name")) for p in numeric[:4]) +
            ") are identifiers or codes, not magnitudes — there is nothing to set a "
            "threshold on. Only a count or a frequency goal is available.")

    intent = cand.get("_intent")
    if intent in ("conversion", "consideration"):
        rec = {"mode": "count", "period": None, "property": None}
    elif magnitude:
        rec = {"mode": "numeric_property", "period": None, "property": magnitude.get("name")}
    elif "frequency" in modes and intent in ("browse", "engagement", "loyalty", None, "other"):
        rec = {"mode": "frequency", "period": _period_for(total, vmax, ctx), "property": None}
    else:
        rec = {"mode": "count", "period": None, "property": None}
    cand["recommended_config"] = rec
    return rec


def _questions(cand: dict) -> List[str]:
    """What to ask the client about an ambiguous candidate. Names are not evidence."""
    qs: List[str] = []
    name = cand.get("name") or ""
    if cand.get("kind") == "custom_event":
        if not cand.get("predefined_match") and cand.get("_intent") in (None, "other"):
            qs.append(f"What business act does `{name}` represent, and where in the "
                      f"journey does it fire?")
        if re.search(r"(step|etape|validate|valid|complete|complet|success|confirm|submit|"
                     r"finish|done|next)", name, re.I):
            qs.append(f"Which journey does `{name}` close — purchase, onboarding, or "
                      f"something else? A step event only becomes a goal once we know "
                      f"which funnel it ends.")
        if cand.get("unit_confidence") in ("Low", "low"):
            qs.append(f"Is the `value` sent on `{name}` an amount in a major currency unit, "
                      f"in cents, or a quantity? The collected samples do not settle it.")
        if cand.get("carries_amount") and not cand.get("currency_property"):
            qs.append(f"Which currency do the `{name}` amounts use, and is the app ever "
                      f"multi-currency? Without a currency property the amounts cannot be "
                      f"summed safely across markets.")
        if (cand.get("predefined_match") or {}).get("how") == "fuzzy":
            qs.append(f"Is `{name}` the same act as the Airship predefined event "
                      f"`{cand['predefined_match']['name']}`? If so, renaming it to the "
                      f"standard unlocks the predefined property template.")
    if cand.get("kind") == "tag":
        qs.append(f"Is the tag group `{cand.get('source_detail') or name}` set by the app "
                  f"or by the CRM, and does gaining this tag mean the user progressed?")
    if cand.get("kind") == "subscription_list":
        qs.append(f"Is subscribing to `{name}` a business outcome the brand chases, or "
                  f"a preference the user manages?")
    return qs


# --------------------------------------------------------------------------- #
# Family A — collected: custom events
# --------------------------------------------------------------------------- #
def _value_facts(an_event: dict, value_row: Optional[dict]) -> dict:
    """Merge the analyzer's value signals for one event into flat candidate fields."""
    vf = (an_event or {}).get("valueField") or {}
    props = (an_event or {}).get("properties") or []
    numeric = [{"name": p.get("name"), "kind": p.get("kind"), "source": "client_property",
                "min": p.get("min"), "max": p.get("max")}
               for p in props if p.get("kind") in _NUMERIC_KINDS]
    currency = next((p.get("name") for p in props
                     if _CURRENCY_RE.search(str(p.get("name") or ""))), None)
    # A property the analyzer already typed as an amount beats every other guess: on a
    # purchase carrying `points_earned`, `order_id` and `total_order_value`, only the last
    # one is the money, and a name-regex alone happily picks the loyalty points.
    value_prop = (next((p.get("name") for p in props if p.get("kind") == "amount"), None)
                  or (value_row or {}).get("valueProperty")
                  or next((p.get("name") for p in props
                           if _AMOUNT_RE.search(str(p.get("name") or ""))), None))
    return {
        "has_value": bool(vf.get("carriesAmount") or vf.get("isCounter") or value_prop),
        "carries_amount": bool(vf.get("carriesAmount")),
        "value_is_counter": bool(vf.get("isCounter")),
        "inferred_unit": vf.get("inferredUnit"),
        "unit_confidence": vf.get("unitConfidence"),
        "value_property": value_prop,
        "currency_property": currency,
        "numeric_properties": numeric,
        "usable_properties": [{"name": p.get("name"), "kind": p.get("kind"),
                               "distinct": p.get("distinctShown")} for p in props],
        "missing_value": bool((value_row or {}).get("missingValue")),
    }


def _all_events(audit: dict) -> List[dict]:
    """EVERY tracked custom event, in the analyzer's `eventProperties` shape.

    The current analyzer emits one row per tracked event, but an analysis.json produced by
    an older build only carried the events that had properties. Exhaustiveness is a
    contract of this skill, so anything the inventory knows and the analysis missed is
    reconstructed here rather than silently dropped.
    """
    an = (audit or {}).get("analysis") or {}
    inv = (audit or {}).get("inventory") or {}
    rows = list(an.get("eventProperties") or [])
    known = {atp._norm(r.get("name")) for r in rows}
    for ev in inv.get("customEvents") or []:
        if atp._norm(ev.get("name")) in known:
            continue
        rows.append({
            "name": ev.get("name"), "source": ev.get("source"), "total": ev.get("total"),
            "intent": atp._intent_of(ev.get("name")),
            "valueField": atp.value_field_stats(ev),
            "properties": atp.analyze_event_properties(ev),
        })
    return rows


def event_candidates(audit: dict, ctx: dict) -> List[dict]:
    """Family A — every tracked custom event, qualified as a goal candidate.

    Exhaustive by contract: EVERY event in the analysis is returned, including the ones
    the anti-pattern pass will later exclude, because "do not put this in a goal" is half
    the advice.
    """
    if not (audit or {}).get("available"):
        return []
    an = audit["analysis"]
    events = _all_events(audit)
    # NB. `_collected_rationale` below fills the "why this one" every card shows. The
    # analyzer only supplies one for events it recognised as conversion signals, which
    # on a French streaming plan was none of them — leaving the north-star card, the
    # most consequential tile in the report, silent about its own choice.
    if not events:
        return []
    value_by_name = {atp._norm(v.get("name")): v for v in an.get("valueBearing") or []}
    conv_by_name = {atp._norm(c.get("name")): c for c in an.get("conversionSignals") or []}
    vmax = max((e.get("total") or 0) for e in events) or 1
    grand = sum((e.get("total") or 0) for e in events) or 1

    out: List[dict] = []
    for e in events:
        name = e.get("name")
        nk = atp._norm(name)
        pm = match_predefined(name)
        intent = e.get("intent") or atp._intent_of(name)
        stage = (pm or {}).get("funnel_stage") or _STAGE_OF_INTENT.get(intent)
        vfacts = _value_facts(e, value_by_name.get(nk))
        total = e.get("total") or 0

        cand = _blank(
            name=name, family="collected", kind="custom_event",
            predefined_match=pm, setup_required="none",
            funnel_stage=stage, total=total,
            share_of_occurrences=round(total / grand, 4),
            source_detail=e.get("source") or "",
            attribution_ready=total >= ATTRIBUTION_READY_MIN,
            instrumentation_route="already_tracked", effort="low",
        )
        cand["_intent"] = intent
        cand["_concepts"] = atp._concepts(name)
        for k in ("has_value", "carries_amount", "inferred_unit", "unit_confidence",
                  "value_property", "currency_property", "numeric_properties",
                  "usable_properties"):
            cand[k] = vfacts[k]
        cand["_value_is_counter"] = vfacts["value_is_counter"]

        # blockers & the properties that would lift them
        if intent in ("conversion", "consideration"):
            if vfacts["value_is_counter"]:
                cand["blockers"].append(
                    "The reserved `value` field only ever holds 0 or 1 — a counter, not an "
                    "amount. The goal will count acts; it will not attribute revenue.")
                cand["properties_to_add"].append("value (the real amount)")
            elif not vfacts["carries_amount"] and not vfacts["value_property"]:
                cand["blockers"].append(
                    "No amount is sent with this conversion, so no revenue can be attributed "
                    "to the messages that drive it.")
                cand["properties_to_add"].append("value")
        if vfacts["carries_amount"] and not vfacts["currency_property"]:
            cand["blockers"].append(
                "Amounts arrive with no currency property — Airship strips currency symbols, "
                "so multi-market totals cannot be summed safely.")
            cand["properties_to_add"].append("currency")
        if vfacts["inferred_unit"] == "integer_ambiguous":
            cand["blockers"].append(
                "The collected amounts are whole integers, so they could be major units, "
                "cents or a quantity — confirm with the brand before reporting revenue.")
        if not vfacts["usable_properties"]:
            cand["blockers"].append(
                "No properties at all: the goal can be counted but never segmented "
                "(by category, store, plan...).")

        conv = conv_by_name.get(nk)
        cand["rationale"] = ((conv or {}).get("suggestedGoal")
                             or _collected_rationale(cand, grand))

        _config(cand, ctx, vmax)
        cand["score"] = _score(cand, ctx, vmax)
        cand["goal_tier"] = _tier(cand["score"])
        cand["questions"] = _questions(cand)
        cand["question_to_client"] = cand["questions"][0] if cand["questions"] else None
        out.append(cand)

    out.sort(key=lambda c: (-c["score"], -(c["total"] or 0), str(c["name"])))
    return out


# --------------------------------------------------------------------------- #
# Family A — collected: tags and subscription lists
# --------------------------------------------------------------------------- #
def tag_candidates(audit: dict, ctx: dict) -> List[dict]:
    """Family A — tags, grouped by tag group (a goal fires on gaining a tag).

    Individual tag VALUES are usually too granular to be a goal on their own, so the
    candidate is the group; the values it carries travel as evidence.
    """
    if not (audit or {}).get("available"):
        return []
    tags = ((audit.get("inventory") or {}).get("tags")) or []
    if not tags:
        return []
    groups: Dict[str, dict] = {}
    for t in tags:
        g = str(t.get("group") or "").strip() or "(ungrouped)"
        row = groups.setdefault(g, {"group": g, "values": [], "added": 0, "removed": 0, "net": 0})
        row["values"].append(str(t.get("value") or t.get("key") or ""))
        row["added"] += int(t.get("added") or 0)
        row["removed"] += int(t.get("removed") or 0)
        row["net"] += int(t.get("net") or 0)
    vmax = max((g["added"] or g["net"] or 0) for g in groups.values()) or 1

    out: List[dict] = []
    for g in sorted(groups.values(), key=lambda r: -(r["added"] or r["net"] or 0)):
        total = g["added"] or g["net"] or 0
        pm = match_predefined(g["group"])
        intent = atp._intent_of(g["group"])
        stage = (pm or {}).get("funnel_stage") or _STAGE_OF_INTENT.get(intent) or "loyalty"
        cand = _blank(
            name=g["group"], family="collected", kind="tag",
            predefined_match=pm, setup_required="none", funnel_stage=stage,
            total=total, source_detail=g["group"],
            attribution_ready=total >= ATTRIBUTION_READY_MIN,
            instrumentation_route="already_tracked", effort="low",
            usable_properties=[{"name": "tag value", "kind": "enum",
                                "distinct": len(set(g["values"]))}],
        )
        cand["_intent"] = intent
        cand["_concepts"] = atp._concepts(g["group"])
        cand["_once_per_lifetime"] = False
        cand["rationale"] = (f"Goal on gaining a tag in the `{g['group']}` group "
                             f"({len(set(g['values']))} distinct values, "
                             f"{g['added']:,} additions / {g['removed']:,} removals).")
        if g["removed"] > g["added"]:
            cand["blockers"].append(
                "More removals than additions on this group — as a goal it would count a "
                "state the audience is leaving.")
        _config(cand, ctx, vmax)
        cand["score"] = _score(cand, ctx, vmax)
        cand["goal_tier"] = _tier(cand["score"])
        cand["questions"] = _questions(cand)
        cand["question_to_client"] = cand["questions"][0]
        out.append(cand)
    return out


def subscription_candidates(audit: dict, ctx: dict) -> List[dict]:
    """Family A — subscription lists (a goal fires on subscribing to a list)."""
    if not (audit or {}).get("available"):
        return []
    lists = ((audit.get("inventory") or {}).get("subscriptionLists")) or []
    if not lists:
        return []
    vmax = max(int(l.get("subscribe") or 0) for l in lists) or 1
    out: List[dict] = []
    for l in sorted(lists, key=lambda r: -(int(r.get("subscribe") or 0))):
        sub = int(l.get("subscribe") or 0)
        unsub = int(l.get("unsubscribe") or 0)
        cand = _blank(
            name=l.get("listId"), family="collected", kind="subscription_list",
            setup_required="none", funnel_stage="activation", total=sub,
            source_detail=l.get("source") or l.get("scopes") or "",
            attribution_ready=sub >= ATTRIBUTION_READY_MIN,
            instrumentation_route="already_tracked", effort="low",
        )
        cand["_intent"] = "account"
        cand["_concepts"] = atp._concepts(str(l.get("listId")))
        cand["_once_per_lifetime"] = True
        cand["rationale"] = (f"Goal on subscribing to `{l.get('listId')}` "
                             f"({sub:,} subscribes / {unsub:,} unsubscribes) — the cleanest "
                             f"way to measure a permission or preference capture campaign.")
        if unsub and sub and unsub / sub > 0.3:
            cand["blockers"].append(
                f"Churn on this list is high ({unsub:,} unsubscribes for {sub:,} subscribes) "
                f"— read the goal alongside the unsubscribes, not on its own.")
        _config(cand, ctx, vmax)
        cand["score"] = _score(cand, ctx, vmax)
        cand["goal_tier"] = _tier(cand["score"])
        cand["questions"] = _questions(cand)
        cand["question_to_client"] = cand["questions"][0]
        out.append(cand)
    return out


# --------------------------------------------------------------------------- #
# Family B — native Airship signals (zero client instrumentation)
# --------------------------------------------------------------------------- #
def native_candidates(ctx: dict) -> List[dict]:
    """Family B — everything Airship can already count on this project.

    No volume is available offline (these never appear in a tagging plan), so `total`
    stays None and the report says so rather than inventing a number.
    """
    natives = catalog().get("nativeNumericProperties") or []
    out: List[dict] = []
    for s in _native_signals():
        stage = s.get("funnelStage")
        modes = list(s.get("configModes") or ["count"])
        cand = _blank(
            name=s.get("name"), family="native", kind=("nps" if s["id"] == "nps_score"
                                                       else "native_signal"),
            setup_required=s.get("setupRequired") or "none",
            funnel_stage=stage, total=None, config_modes=modes,
            instrumentation_route="already_tracked",
            effort="low" if (s.get("setupRequired") or "none") == "none" else "medium",
            source_detail=", ".join(s.get("alsoKnownAs") or []) or s.get("id"),
            attribution_ready=None,
            rationale=s.get("whyItMatters"),
        )
        cand["_intent"] = ("conversion" if stage == "conversion"
                           else "account" if stage == "activation"
                           else "loyalty" if stage == "loyalty"
                           else "engagement")
        cand["_native_id"] = s.get("id")
        cand["_concepts"] = atp._concepts(s.get("name"), *(s.get("alsoKnownAs") or []))
        cand["_once_per_lifetime"] = s["id"] in ("first_open", "first_opt_in",
                                                 "channel_registration",
                                                 "named_user_association")
        if s.get("negativeSignal"):
            cand["exclude"] = True
            cand["exclude_kind"] = "negative_signal"
            cand["exclude_label"] = "Negative signal"
            cand["exclude_reason"] = s.get("caveat") or "Negative signal — guardrail, not a goal."
        if s.get("caveat"):
            cand["blockers"].append(s["caveat"])
        if "numeric_property" in modes:
            cand["numeric_properties"] = [
                {"name": n["name"], "kind": "number", "source": "airship_native",
                 "unit": n.get("unit")} for n in natives]
        rec = s.get("recommendedConfig")
        cand["recommended_config"] = (dict(rec) if rec else
                                      {"mode": modes[0], "period": None, "property": None})
        cand["recommended_config"].setdefault("period", None)
        cand["recommended_config"].setdefault("property", None)
        # native signals carry no volume, so the score leans on intent + vertical fit
        cand["score"] = round(min(1.0, (0.45 * _INTENT_WEIGHT.get(cand["_intent"], 0.3)
                                        + 0.40 * _vertical_priority(None, stage, ctx)
                                        + 0.15)
                                  * _stage_boost(stage, ctx)), 3)
        if cand["setup_required"] != "none":
            cand["score"] = round(cand["score"] * 0.85, 3)
        cand["goal_tier"] = _tier(cand["score"])
        out.append(cand)
    out.sort(key=lambda c: (-c["score"], str(c["name"])))
    return out


# --------------------------------------------------------------------------- #
# Family C — gaps: the metrics to propose the client starts tracking
# --------------------------------------------------------------------------- #
def roadmap(audit: dict, ctx: dict, collected: Optional[Sequence[dict]] = None) -> List[dict]:
    """Family C — archetypes that matter for this vertical and are NOT tracked.

    These are recommendations, never shortlist entries. Each carries the Airship naming
    standard, the properties to send, the instrumentation route deduced from the client's
    real source split, the effort, and the goal it would unlock.
    """
    vert = ctx.get("vertical") or {}
    funnel = vert.get("funnel") or {}
    hints = {h.get("archetype"): h for h in (vert.get("roadmapHints") or [])}
    tracked_concepts = [c.get("_concepts") or set() for c in (collected or [])]
    tracked_arch = {(c.get("predefined_match") or {}).get("name")
                    for c in (collected or []) if c.get("predefined_match")}

    ordered: List[str] = []
    for stage in _STAGES:
        for a in funnel.get(stage) or []:
            if a not in ordered:
                ordered.append(a)
    for a in vert.get("priorityArchetypes") or []:
        if a not in ordered:
            ordered.append(a)

    native_ids = {s["id"] for s in _native_signals()}
    out: List[dict] = []
    excluded = ctx.get("excluded_archetypes") or set()
    for aname in ordered:
        if aname in native_ids:
            continue                      # family B already covers it, free of charge
        if aname in tracked_arch:
            continue                      # already collected -> family A
        if atp._norm(aname) in excluded:
            continue                      # the business model rules it out entirely
        arch = _archetype(aname)
        if not arch:
            continue
        ac = atp._concepts(*_alias_pool(arch))
        if any(ac & tc and len(ac & tc) >= 2 for tc in tracked_concepts):
            continue                      # something close enough is already tracked
        hint = hints.get(aname) or {}
        item = _blank(
            name=aname, family="gap", kind="custom_event",
            predefined_match={"name": aname, "how": "naming_standard", "score": 1.0,
                              "funnel_stage": arch.get("funnelStage"),
                              "category": arch.get("category")},
            setup_required="instrument_then_add",
            funnel_stage=arch.get("funnelStage"),
            total=None, attribution_ready=None,
            usable_properties=[{"name": p, "kind": "recommended", "distinct": None}
                               for p in (hint.get("properties")
                                         or arch.get("nativeProperties") or [])],
            rationale=(hint.get("why")
                       or f"Airship predefined event for the "
                          f"{arch.get('category','').lower() or aname} step, missing from the "
                          f"{ctx.get('vertical_label')} funnel as currently tracked."),
        )
        item["_intent"] = ("conversion" if arch.get("funnelStage") == "conversion"
                           else "consideration" if arch.get("funnelStage") == "consideration"
                           else "account" if arch.get("funnelStage") == "activation"
                           else "loyalty")
        item["_concepts"] = ac
        route = instrumentation_route(item, audit, ctx)
        item["instrumentation_route"] = route["route"]
        item["effort"] = route["effort"]
        item["route_why"] = route["why"]
        if arch.get("valueBearing"):
            item["properties_to_add"] = ["value", "currency"] + [
                p for p in (arch.get("nativeProperties") or []) if p != "currency"]
        else:
            item["properties_to_add"] = list(arch.get("nativeProperties") or [])
        item["config_modes"] = ["count", "frequency"] if not arch.get("valueBearing") \
            else ["count", "numeric_property"]
        item["recommended_config"] = {"mode": "count", "period": None, "property": None}
        item["score"] = round(min(1.0, (0.5 * _INTENT_WEIGHT.get(item["_intent"], 0.3)
                                        + 0.5 * _vertical_priority(aname, item["funnel_stage"],
                                                                   ctx))
                                  * _stage_boost(item["funnel_stage"], ctx)), 3)
        item["goal_tier"] = _tier(item["score"])
        item["unlocks_goal"] = (f"A {arch.get('funnelStage')}-stage goal on `{aname}`"
                                + (" with revenue attribution" if arch.get("valueBearing") else ""))
        out.append(item)
    out.sort(key=lambda r: -r["score"])
    return out


# --------------------------------------------------------------------------- #
# Attributes as goals — Airship's announced extension
# --------------------------------------------------------------------------- #
_ATTR_GOAL_HINTS = [
    (re.compile(r"(tier|palier|niveau|grade|status|statut|segment|rank)", re.I),
     "loyalty", "Tier progression is a goal the moment attributes become goal sources: "
                "'user moved up a tier' is the outcome loyalty campaigns actually chase."),
    (re.compile(r"(point|solde|balance|credit|cagnotte|wallet|score)", re.I),
     "loyalty", "A numeric balance supports a threshold goal — 'crossed N points' — which "
                "is what a points-accrual campaign is optimised toward."),
    (re.compile(r"(last_?order|last_?purchase|derniere_?commande|last_?visit|last_?seen|"
                r"recency|last_?activity)", re.I),
     "retention", "A recency attribute becomes a reactivation goal: 'was inactive, is "
                  "active again'."),
    (re.compile(r"(subscri|abonn|plan|forfait|contract|contrat|offer|offre)", re.I),
     "conversion", "Plan or contract level is the commercial outcome of an upsell "
                   "campaign — as an attribute goal it needs no new event."),
    (re.compile(r"(optin|opt_in|consent|consentement|notif)", re.I),
     "activation", "A consent attribute measures permission recovery without adding a "
                   "single event."),
    (re.compile(r"(favorite|favori|preferred|prefere|interest|team|equipe|store|magasin)", re.I),
     "activation", "Filling a preference is a profile-completion goal, and the precondition "
                   "for any real personalisation."),
    (re.compile(r"(complete|completion|profile|profil)", re.I),
     "activation", "Profile completion is the classic progressive-profiling goal."),
]


def attribute_candidates(audit: dict, ctx: dict) -> List[dict]:
    """Attributes worth proposing as goals once Airship supports attribute-based goals.

    Not activatable today — the report is explicit about that — but the point of naming
    them now is that the client can start collecting the missing ones in the same sprint.
    """
    if not (audit or {}).get("available"):
        return []
    attrs = ((audit.get("inventory") or {}).get("attributes")) or []
    out: List[dict] = []
    for a in attrs:
        key = a.get("key") or a.get("normalized")
        if not key:
            continue
        hit = next(((stage, why) for rx, stage, why in _ATTR_GOAL_HINTS if rx.search(str(key))),
                   None)
        if not hit:
            continue
        stage, why = hit
        samples = [str(s) for s in (a.get("sampleValues") or [])][:6]
        numeric = all(re.fullmatch(r"-?\d+([.,]\d+)?", s.strip()) for s in samples) if samples \
            else False
        out.append({
            "name": key,
            "funnel_stage": stage,
            "why": why,
            "total": a.get("total") or 0,
            "distinct": a.get("distinctValues") or 0,
            "sources": a.get("sources") or "",
            "sample_values": samples,
            "proposed_goal": ("threshold on the value" if numeric else "change to a target value"),
            "kind": "numeric" if numeric else "categorical",
            "tracked": True,
        })
    # attributes the vertical recommends but the client does not collect
    tracked = {atp._norm(a.get("key")) for a in attrs} | {atp._norm(a.get("normalized"))
                                                          for a in attrs}
    excluded = ctx.get("excluded_attributes") or set()
    for rec in _vertical_recommended_attributes(ctx):
        if atp._norm(rec["id"]) in tracked or atp._norm(rec["name"]) in tracked:
            continue
        if atp._norm(rec["id"]) in excluded or atp._norm(rec["name"]) in excluded:
            continue                      # the business model rules it out entirely
        hit = next(((stage, why) for rx, stage, why in _ATTR_GOAL_HINTS
                    if rx.search(rec["id"]) or rx.search(rec["name"])), None)
        if not hit:
            continue
        stage, why = hit
        out.append({
            "name": rec["id"], "funnel_stage": stage, "why": why,
            "total": None, "distinct": None, "sources": "",
            "sample_values": [], "kind": "recommended",
            "proposed_goal": "collect it first, then use it as an attribute goal",
            "tracked": False, "label": rec["name"], "type": rec.get("type"),
        })
    out.sort(key=lambda r: (0 if r["tracked"] else 1, -(r.get("total") or 0), r["name"]))
    return out


def _vertical_recommended_attributes(ctx: dict) -> List[dict]:
    """Attributes the data-collection reference recommends for this vertical."""
    ref = os.path.join(_HERE, "..", "data-collection-by-vertical.json")
    if not os.path.isfile(ref):
        return []
    try:
        doc = _read_json(ref)
    except (OSError, ValueError):
        return []
    label = (ctx.get("vertical") or {}).get("label") or ctx.get("vertical_key")
    v = (doc.get("verticals") or {}).get(label) or (doc.get("verticals") or {}).get(
        ctx.get("vertical_key") or "")
    return [{"id": a.get("id") or a.get("name"), "name": a.get("name") or a.get("id"),
             "type": a.get("type")} for a in ((v or {}).get("attributes") or [])]


# --------------------------------------------------------------------------- #
# Decision layer 1 — anti-patterns
# --------------------------------------------------------------------------- #
def _collected_rationale(cand: dict, grand: int) -> str:
    """One sentence saying why a tracked event is worth configuring, or is not.

    Composed from what the engine already established — the archetype match, the funnel
    stage, the volume, the instrumentation — so it never asserts more than it knows.
    """
    pm = cand.get("predefined_match") or {}
    stage = next((s.get("label") for s in catalog().get("funnelStages") or []
                  if s.get("id") == cand.get("funnel_stage")), "")
    total = cand.get("total") or 0
    share = (total / grand) if grand else 0
    bits: List[str] = []

    how = pm.get("how")
    if how == "exact":
        bits.append(f"Already carries the exact Airship predefined name "
                    f"`{pm['name']}`, so it inherits the standard property template")
    elif how in ("alias", "fuzzy"):
        bits.append(f"Reads as the Airship predefined event `{pm['name']}`"
                    + (" — renaming to the standard would make that explicit"
                       if how == "fuzzy" else ""))
    elif stage:
        bits.append(f"A {stage.lower()}-stage act with no Airship predefined equivalent, "
                    f"so it stays a custom-event goal under its own name")
    else:
        bits.append("No Airship predefined equivalent and no funnel stage could be "
                    "inferred from the name alone")

    if total >= ATTRIBUTION_READY_MIN:
        bits.append(f"{total:,} occurrences ({share:.0%} of everything tracked) is "
                    f"enough for a per-message read")
    elif total >= GOAL_VIABLE_MIN:
        bits.append(f"{total:,} occurrences is too thin to split across a campaign "
                    f"calendar, so treat it as a diagnostic rather than a target")
    else:
        bits.append(f"{total:,} occurrences in the window is not a measurement")

    props = cand.get("usable_properties") or []
    if props:
        bits.append(f"{len(props)} usable propert{'y' if len(props) == 1 else 'ies'} "
                    f"to break the goal down by")
    return ". ".join(bits) + "."


def _keeper_rank(c: dict):
    """Order two names for the same act by which makes the BETTER goal.

    Volume is the LAST tie-break, not the first. On a retail app the loudest
    name was `checkout` (1,566, one property) and the quietest was `purchased` (1,425,
    the exact Airship predefined name, carrying `transactionId` and an order value) —
    ranking on volume benched the only event that can attribute revenue. What decides is
    whether Airship already knows the name, whether money rides on it, and how richly it
    is instrumented.
    """
    how = (c.get("predefined_match") or {}).get("how")
    return (
        0 if c.get("attribution_ready") else 1,             # a goal nobody reaches loses
        {"exact": 0, "alias": 1, "fuzzy": 2}.get(how, 3),   # Airship knows this name
        0 if c.get("carries_amount") else 1,                # money rides on it
        0 if c.get("value_property") else 1,                # a value property at least
        0 if c.get("_intent") == "conversion" else 1,
        -len(c.get("usable_properties") or []),             # richer instrumentation
        -(c.get("total") or 0),                             # only then, volume
        str(c.get("name")),
    )


def _keeper_why(keeper: dict, loser: dict) -> str:
    """One clause explaining why the keeper won — never just 'it is bigger'."""
    kh = (keeper.get("predefined_match") or {}).get("how")
    lh = (loser.get("predefined_match") or {}).get("how")
    if keeper.get("attribution_ready") and not loser.get("attribution_ready"):
        return (f"`{loser['name']}` fires only {loser.get('total') or 0:,} times, too "
                f"rarely to carry a per-message read")
    if kh == "exact" and lh != "exact":
        return f"`{keeper['name']}` is the exact Airship predefined name"
    if keeper.get("carries_amount") and not loser.get("carries_amount"):
        return "it is the one carrying the amount"
    if keeper.get("value_property") and not loser.get("value_property"):
        return f"it carries a value property (`{keeper['value_property']}`)"
    nk, nl = len(keeper.get("usable_properties") or []), len(loser.get("usable_properties") or [])
    if nk > nl:
        return f"it is the more richly instrumented ({nk} usable properties vs {nl})"
    return (f"{keeper.get('total') or 0:,} occurrences vs {loser.get('total') or 0:,}")


def antipatterns(cands: Sequence[dict], ctx: dict) -> List[dict]:
    """Mark, with a reason, everything that should NOT be configured as a goal.

    Mutates the candidates in place (``exclude`` / ``exclude_reason``) and returns the
    excluded subset. Four grounds, in order of precedence: technical/debug plumbing,
    non-discriminating volume, duplicate concept, negative signal.
    """
    rules = catalog().get("antipatternRules") or []
    by_id = {r["id"]: r for r in rules}
    grand = sum((c.get("total") or 0) for c in cands
                if c.get("kind") == "custom_event" and c.get("family") == "collected") or 1

    def flag(c: dict, rule_id: str, extra: str = ""):
        if c.get("exclude"):
            return
        r = by_id.get(rule_id, {})
        c["exclude"] = True
        c["exclude_kind"] = rule_id
        c["exclude_label"] = r.get("label", rule_id)
        c["exclude_reason"] = (r.get("reason", "") + (" " + extra if extra else "")).strip()

    # Negative signals are tested FIRST: `applogout` is a logout before it is anything
    # else, and a rule ordered on token breadth would file it under "technical".
    for c in cands:
        if c.get("family") == "gap":
            continue
        name = str(c.get("name") or "")
        low = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        for rid in ("negative_signal", "technical_or_debug", "descriptive_state",
                    "screen_or_impression_noise", "consent_plumbing"):
            r = by_id.get(rid) or {}
            if low in (r.get("exactNames") or []) or any(tok in low
                                                         for tok in r.get("tokens") or []):
                flag(c, rid)
                break

    # non-discriminating volume: a collected event carrying most of the occurrences
    for c in cands:
        if c.get("exclude") or c.get("family") != "collected" or c.get("kind") != "custom_event":
            continue
        total = c.get("total") or 0
        if total / grand >= UNIVERSAL_SHARE and c.get("_intent") in (
                "browse", "engagement", "other", "location"):
            c["exclude"] = True
            c["exclude_kind"] = "non_discriminating"
            c["exclude_label"] = "Non-discriminating volume"
            c["exclude_reason"] = (
                f"Carries {total/grand*100:.0f}% of all tracked occurrences and marks no "
                f"commitment — nearly every active user meets it, so as a goal it ranks "
                f"nobody. Keep it as a frequency threshold at most.")

    # Duplicate concepts: two names for the same act. Compared on the ALIAS-GROUP part of
    # the signature only — `commande_validee` and `purchase` share the order/purchase group
    # while their leftover tokens differ, and it is the shared group that says they name the
    # same business act. Keep the loudest, exclude the rest (and ask the client to confirm).
    seen: Dict[frozenset, dict] = {}
    for c in sorted([x for x in cands if x.get("family") == "collected"
                     and x.get("kind") == "custom_event" and not x.get("exclude")],
                    key=_keeper_rank):
        sig = frozenset(t for t in (c.get("_concepts") or set()) if t[0] == "g")
        if not sig:
            continue
        keeper = seen.get(sig)
        if keeper is None:
            seen[sig] = c
            continue
        c["exclude"] = True
        c["exclude_kind"] = "duplicate_concept"
        c["exclude_label"] = "Duplicate concept"
        c["exclude_reason"] = (
            f"Names the same business act as `{keeper['name']}`, which is the better goal "
            f"of the two ({_keeper_why(keeper, c)}). Two goals on one act split the "
            f"measurement; confirm with the client, then keep one and align the naming.")
        c["questions"] = list(c.get("questions") or []) + [
            f"Are `{c['name']}` and `{keeper['name']}` the same act, or two genuinely "
            f"different steps that happen to share a vocabulary?"]
        c["question_to_client"] = c["questions"][0]

    return [c for c in cands if c.get("exclude")]


# --------------------------------------------------------------------------- #
# Decision layer 2 — prioritisation (a hierarchy, not a quota)
# --------------------------------------------------------------------------- #
def prioritise(cands: Sequence[dict], ctx: dict) -> dict:
    """Turn a scored candidate list into a decision.

    Returns ``{north_star, primary: {stage: [...]}, secondary, blind_stages,
    covered_stages}``. There is deliberately NO numeric cap: a per-project goal limit
    exists in Airship but the figure moves, so the report ships a ranked hierarchy the
    team can cut wherever the dashboard says to.
    """
    pool = [c for c in cands if not c.get("exclude") and c.get("family") in ("collected", "native")]
    pool.sort(key=lambda c: (-c.get("score", 0), -(c.get("total") or 0), str(c.get("name"))))

    bm = ctx.get("business_model") or {}
    prefs = list(bm.get("northStarPreference") or [])

    def arch_of(c):
        return (c.get("predefined_match") or {}).get("name") or c.get("_native_id")

    north = None
    for want in prefs:
        north = next((c for c in pool if arch_of(c) == want), None)
        if north:
            break
    if north is None:
        north = next((c for c in pool if c.get("funnel_stage") == "conversion"), None)
    if north is None:
        north = pool[0] if pool else None
    if north is not None:
        north = dict(north, is_north_star=True)

    north_name = north["name"] if north else None
    rest = [c for c in pool if c.get("name") != north_name]

    # A primary goal has to be able to carry a per-message read. An event firing a few
    # hundred times cannot: split across a campaign calendar it produces noise, and
    # promoting it hides a stage that is genuinely thin. Candidates below the
    # attribution floor stay available, one tier down, rather than being dressed up as
    # the stage's answer — unless the stage has nothing else, in which case showing the
    # weak candidate is more honest than showing an empty stage.
    # Native signals carry no count (Airship emits them), so `total is None` must never be
    # read as "too rare"; only a measured count below the floor disqualifies.
    def viable(c):
        t = c.get("total")
        return t is None or t >= GOAL_VIABLE_MIN

    primary: Dict[str, List[dict]] = {}
    used: set = set()
    for stage in _STAGES:
        at_stage = [c for c in rest if c.get("funnel_stage") == stage
                    and c.get("goal_tier") == "primary" and viable(c)]
        ready = [c for c in at_stage if c.get("attribution_ready")]
        take = (ready or at_stage)[:2]
        if take:
            primary[stage] = take
            used |= {c["name"] for c in take}

    secondary = [c for c in rest if c["name"] not in used and viable(c)
                 and c.get("goal_tier") in ("primary", "secondary")][:8]

    covered: Dict[str, dict] = {}
    for stage in _STAGES:
        col = [c for c in cands if c.get("funnel_stage") == stage
               and c.get("family") == "collected" and not c.get("exclude")]
        nat = [c for c in cands if c.get("funnel_stage") == stage
               and c.get("family") == "native" and not c.get("exclude")]
        gap = [c for c in cands if c.get("funnel_stage") == stage and c.get("family") == "gap"]
        covered[stage] = {
            "collected": [c["name"] for c in col],
            "native": [c["name"] for c in nat],
            "gaps": [c["name"] for c in gap],
            "status": ("collected" if col else "native" if nat else "blind"),
        }

    vert = ctx.get("vertical") or {}
    pitches = vert.get("blindStagePitch") or {}
    blind = [{"stage": s,
              "pitch": pitches.get(s) or (
                  f"No collected event and no native Airship signal covers the {s} stage, "
                  f"so nothing can be measured or optimised there today."),
              "gaps": covered[s]["gaps"]}
             for s in _STAGES if covered[s]["status"] == "blind"]

    return {"north_star": north, "primary": primary, "secondary": secondary,
            "blind_stages": blind, "coverage": covered}


def discovery_questions(cands: Sequence[dict]) -> List[dict]:
    """Every open question, grouped by the candidate that raises it."""
    out = []
    for c in cands:
        qs = c.get("questions") or []
        if not qs:
            continue
        out.append({"name": c.get("name"), "kind": c.get("kind"),
                    "family": c.get("family"), "total": c.get("total"),
                    "questions": qs})
    out.sort(key=lambda r: (-(r.get("total") or 0), str(r["name"])))
    return out


# --------------------------------------------------------------------------- #
# Numeric brief (facts.json schema, so the gate's coherence check keeps working)
# --------------------------------------------------------------------------- #
def _kpi(key, label, unit, value, patterns):
    return {"key": key, "label_en": label, "label_fr": label, "unit": unit,
            "value": value, "prior": None, "delta_pct": None,
            "source": "goals.json", "prior_source": None, "label_patterns": patterns}


def facts(doc: dict, audit: dict, ctx: Optional[dict] = None) -> dict:
    """The shared numeric brief for the light report, in the facts.json schema."""
    ctx = ctx or doc.get("context") or {}
    cands = doc.get("candidates") or []
    collected = [c for c in cands if c.get("family") == "collected"]
    native = [c for c in cands if c.get("family") == "native"]
    activatable = [c for c in cands if c.get("family") in ("collected", "native")
                   and not c.get("exclude")]
    excluded = [c for c in cands if c.get("exclude")]
    conv = [c for c in collected if c.get("funnel_stage") in ("conversion", "consideration")]
    valued = [c for c in conv if c.get("carries_amount")]
    an = (audit or {}).get("analysis") or {}
    counts = an.get("counts") or {}

    kpis = [
        _kpi("goal_candidates_activatable", "Activatable goal candidates", "count",
             len(activatable), [r"activatable goal candidates?", r"goal candidates? \(activatable\)"]),
        _kpi("goal_candidates_collected", "Collected goal candidates", "count",
             len(collected), [r"collected goal candidates?", r"candidates? from collected data"]),
        _kpi("goal_candidates_native", "Native Airship goal candidates", "count",
             len(native), [r"native (airship )?goal candidates?", r"native signals?"]),
        _kpi("goal_antipatterns", "Goals to avoid", "count", len(excluded),
             [r"goals? to avoid", r"anti-?patterns?"]),
        _kpi("value_instrumentation_pct", "Value instrumentation on conversion candidates",
             "pct", round(100.0 * len(valued) / len(conv), 1) if conv else 0.0,
             [r"value instrumentation.*", r"conversion candidates? carrying an amount"]),
        _kpi("blind_funnel_stages", "Blind funnel stages", "count",
             len(doc.get("priorities", {}).get("blind_stages") or []),
             [r"blind funnel stages?", r"uncovered funnel stages?"]),
        _kpi("tracked_custom_events", "Tracked custom events", "count",
             int(counts.get("customEvents") or 0),
             [r"tracked custom events?", r"custom events? tracked"]),
        _kpi("roadmap_metrics", "Metrics to add", "count", len(doc.get("roadmap") or []),
             [r"metrics? to add", r"recommended new metrics?"]),
    ]
    return {
        "client": ctx.get("brand"),
        "project": doc.get("project"),
        "app_key": doc.get("app_key"),
        "region": doc.get("region"),
        "window": None,
        "lang": "en",
        "vertical": ctx.get("vertical_key"),
        "benchmark_set": None,
        "vocabulary": None,
        "kpis": kpis,
        "sections_na": doc.get("sections_na") or {},
        "unresolved_kpis": [],
        "note": "Shared numeric brief for the light Goals review. Every figure is derived "
                "from the tagging-plan audit only — no Reports API call. Occurrences are "
                "not unique channels.",
    }


# --------------------------------------------------------------------------- #
# Top-level build
# --------------------------------------------------------------------------- #
def _strip_private(c: dict) -> dict:
    return {k: (sorted(v) if isinstance(v, (set, frozenset)) else v)
            for k, v in c.items() if not k.startswith("_")}


def build(audit: dict, brand: Optional[dict] = None, *, project: Optional[str] = None,
          app_key: Optional[str] = None, region: Optional[str] = None) -> dict:
    """Run the whole engine -> the `goals.json` document the light report consumes."""
    ctx = resolve_context(audit, brand)
    events = event_candidates(audit, ctx)
    tags = tag_candidates(audit, ctx)
    subs = subscription_candidates(audit, ctx)
    natives = native_candidates(ctx)
    collected = events + tags + subs
    gaps = roadmap(audit, ctx, collected)

    cands = collected + natives + gaps
    excluded = antipatterns(cands, ctx)
    prio = prioritise(cands, ctx)
    attrs = attribute_candidates(audit, ctx)
    questions = discovery_questions(cands)

    doc = {
        "kind": "airship-goal-candidates",
        "version": 1,
        "language": "en",
        "project": project, "app_key": app_key, "region": region,
        "context": ctx,
        "candidates": [_strip_private(c) for c in cands],
        "collected": [_strip_private(c) for c in collected],
        "native": [_strip_private(c) for c in natives],
        "roadmap": [_strip_private(c) for c in gaps],
        "excluded": [_strip_private(c) for c in excluded],
        "priorities": _strip_priorities(prio),
        "attributes": attrs,
        "questions": questions,
        "config_modes": catalog().get("configModes") or [],
        "funnel_stages": catalog().get("funnelStages") or [],
        "product_limits": catalog().get("productLimits") or {},
        "goal_reports": catalog().get("goalReports") or [],
        "caveats": [
            "The tagging-plan export counts OCCURRENCES, not unique channels: no per-user "
            "frequency and no penetration rate can be computed offline. Configuring the "
            "goal is what unlocks the Channels-per-goal and Goal-frequency-per-channel "
            "reports.",
            "Event names are not evidence of intent. Every ambiguous candidate carries a "
            "question to put to the client rather than an assumed meaning.",
            "The reserved `value` field is a client-declared number, never a currency by "
            "itself — currency has to travel as its own property.",
            "An Airship predefined event the client does not send is a measurement gap, "
            "not an available goal.",
        ],
    }
    doc["facts"] = facts(doc, audit, ctx)
    return doc


def _strip_priorities(prio: dict) -> dict:
    return {
        "north_star": _strip_private(prio["north_star"]) if prio.get("north_star") else None,
        "primary": {s: [_strip_private(c) for c in v] for s, v in (prio.get("primary") or {}).items()},
        "secondary": [_strip_private(c) for c in prio.get("secondary") or []],
        "blind_stages": prio.get("blind_stages") or [],
        "coverage": prio.get("coverage") or {},
    }


# --------------------------------------------------------------------------- #
# CLI + self-test
# --------------------------------------------------------------------------- #
def _demo_audit() -> dict:
    """A small synthetic audit so the engine can be exercised with no client file."""
    import data_foundation as df
    inventory = {
        "meta": {"profile": "DEMO"},
        "platforms": ["iOS", "Android", "API"],
        "customEvents": [
            {"name": "commande_validee", "source": "SDK", "total": 42000,
             "platforms": {"iOS": 25000},
             "properties": [{"name": "montant", "samples": [{"value": "42.50", "count": 3},
                                                            {"value": "17.90", "count": 2}]},
                            {"name": "categorie", "samples": [{"value": "beaute", "count": 4}]}],
             "valueSamples": [{"value": "42.50", "count": 3}, {"value": "17.90", "count": 2}]},
            {"name": "ajout_panier", "source": "SDK", "total": 210000,
             "platforms": {"iOS": 120000},
             "properties": [{"name": "sku", "samples": [{"value": "A123", "count": 2}]}],
             "valueSamples": []},
            {"name": "screen_viewed", "source": "SDK", "total": 3000000,
             "platforms": {"iOS": 2000000}, "properties": [], "valueSamples": []},
            {"name": "sdk_debug_ping", "source": "SDK", "total": 900,
             "platforms": {"iOS": 900}, "properties": [], "valueSamples": []},
            {"name": "validate_step", "source": "API", "total": 55000,
             "platforms": {"iOS": 30000},
             "properties": [{"name": "step", "samples": [{"value": "3", "count": 9}]}],
             "valueSamples": []},
            {"name": "purchase", "source": "API", "total": 4000,
             "platforms": {"iOS": 2000}, "properties": [], "valueSamples": []},
        ],
        "attributes": [
            {"key": "loyalty_tier", "normalized": "loyalty_tier", "total": 800,
             "actions": "set:800", "sources": "API", "distinctValues": 4,
             "platforms": {"Email": 800}, "sampleValues": ["Gold", "Silver"]},
            {"key": "points_balance", "normalized": "points_balance", "total": 700,
             "actions": "set:700", "sources": "API", "distinctValues": 300,
             "platforms": {"Email": 700}, "sampleValues": ["120", "480"]},
        ],
        "tags": [{"key": "interest:sports", "group": "interest", "value": "sports",
                  "added": 9000, "removed": 200, "net": 8800},
                 {"key": "interest:beauty", "group": "interest", "value": "beauty",
                  "added": 4000, "removed": 100, "net": 3900}],
        "subscriptionLists": [{"listId": "newsletter", "subscribe": 12000,
                               "unsubscribe": 400, "net": 11600, "source": "API"}],
        "screens": [], "excludedAirship": {"attributes": [], "tags": []},
        "valuesTruncated": False,
    }
    import subprocess
    import tempfile
    tmp = tempfile.mkdtemp(prefix="goals_demo_")
    inv_p, ana_p = os.path.join(tmp, "inventory.json"), os.path.join(tmp, "analysis.json")
    with open(inv_p, "w", encoding="utf-8") as fh:
        json.dump(inventory, fh)
    subprocess.run([sys.executable, os.path.join(_HERE, "analyze_tagging_plan.py"),
                    inv_p, "--vertical", "Retail", "-o", ana_p], check=True,
                   capture_output=True)
    return df.load(analysis_path=ana_p, inventory_path=inv_p)


def _self_test() -> int:
    # graceful degradation: no audit at all
    empty = {"available": False}
    ctx0 = resolve_context(empty)
    assert event_candidates(empty, ctx0) == []
    assert tag_candidates(empty, ctx0) == []
    assert subscription_candidates(empty, ctx0) == []
    assert attribute_candidates(empty, ctx0) == []
    assert native_candidates(ctx0), "native signals must exist with no audit at all"
    print("graceful degradation OK")

    # matcher
    assert match_predefined("purchased")["how"] == "exact"
    assert match_predefined("commande_validee")["name"] == "purchased", \
        match_predefined("commande_validee")
    assert match_predefined("ajout_panier")["name"] == "added_to_cart", \
        match_predefined("ajout_panier")
    assert match_predefined("zzz_qqq_unmatchable") is None
    print("match_predefined OK")

    assert resolve_vertical_key("Retail") == "Retail"
    assert resolve_vertical_key("retail") == "Retail"
    assert resolve_vertical_key("telecom") == "all verticals"
    assert resolve_vertical_key("Sport & Gaming") == "Sport & Gaming"
    print("vertical resolution OK")

    audit = _demo_audit()
    assert audit.get("available"), audit.get("reason")
    doc = build(audit, {"name": "Demo Retail", "vertical": "Retail",
                        "business_model": "transactional"})
    json.dumps(doc)  # must be serialisable

    names = {c["name"]: c for c in doc["candidates"]}
    assert names["screen_viewed"]["exclude"], "screen_viewed must be an anti-pattern"
    assert names["sdk_debug_ping"]["exclude"], "debug event must be an anti-pattern"
    assert names["commande_validee"]["predefined_match"]["name"] == "purchased"
    assert names["commande_validee"]["carries_amount"] is True
    assert "currency" in " ".join(names["commande_validee"]["properties_to_add"])
    assert names["ajout_panier"]["funnel_stage"] == "consideration"
    assert names["validate_step"]["question_to_client"], "ambiguous event must ask a question"
    # `purchase` and `commande_validee` are the same concept -> one of them excluded
    dupes = [c for c in doc["candidates"] if c.get("exclude_kind") == "duplicate_concept"]
    assert dupes, "duplicate concepts must be detected"
    print(f"candidates OK ({len(doc['candidates'])} total, "
          f"{len(doc['excluded'])} excluded, {len(dupes)} duplicate)")

    prio = doc["priorities"]
    assert prio["north_star"], "a north star must be picked"
    assert prio["north_star"]["family"] in ("collected", "native")
    assert isinstance(prio["primary"], dict)
    assert set(prio["coverage"]) == set(_STAGES)
    print(f"priorities OK (north star = {prio['north_star']['name']}, "
          f"{len(prio['blind_stages'])} blind stage(s))")

    assert doc["roadmap"], "a retail plan with no search event must yield roadmap items"
    for r in doc["roadmap"]:
        assert r["family"] == "gap" and r["setup_required"] == "instrument_then_add"
        assert r["instrumentation_route"] in ("sdk", "custom_events_api")
    print(f"roadmap OK ({len(doc['roadmap'])} metrics to add)")

    assert any(a["name"] == "loyalty_tier" for a in doc["attributes"])
    assert any(a["kind"] == "numeric" for a in doc["attributes"])
    print(f"attribute goals OK ({len(doc['attributes'])})")

    f = doc["facts"]
    assert {k["key"] for k in f["kpis"]} >= {"goal_candidates_activatable",
                                             "value_instrumentation_pct",
                                             "blind_funnel_stages"}
    assert f["lang"] == "en"
    print(f"facts OK ({len(f['kpis'])} KPIs)")

    # English-only contract: no *_fr key anywhere in the emitted document
    blob = json.dumps(doc, ensure_ascii=False)
    assert '"label_fr"' in blob, "facts.json schema keeps label_fr (mirrors English here)"
    for k in doc["candidates"][0]:
        assert not k.endswith("_fr"), k
    print("English-only contract OK")

    # every non-excluded candidate has at least the count mode
    for c in doc["candidates"]:
        assert "count" in c["config_modes"], c["name"]
        assert c["recommended_config"]["mode"] in ("count", "frequency", "numeric_property")
    print("config modes OK")
    print("\ngoal_candidates self-test OK")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inventory", nargs="?", help="inventory.json from parse_tagging_plan.py")
    ap.add_argument("analysis", nargs="?", help="analysis.json from analyze_tagging_plan.py")
    ap.add_argument("brand", nargs="?", help="optional brand.json (web research)")
    ap.add_argument("--raw", help="raw tagging-plan .json (runs parse+analyze itself)")
    ap.add_argument("--vertical", help="override the vertical")
    ap.add_argument("-o", "--out", help="output goals.json path")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return _self_test()

    import data_foundation as df
    if args.raw:
        audit = df.load(raw_path=args.raw, vertical=args.vertical)
    elif args.inventory and args.analysis:
        audit = df.load(analysis_path=args.analysis, inventory_path=args.inventory)
    else:
        ap.print_help()
        return 1
    if not audit.get("available"):
        print(f"audit unavailable: {audit.get('reason')}", file=sys.stderr)
        return 1

    brand = _read_json(args.brand) if args.brand and os.path.isfile(args.brand) else None
    if args.vertical:
        brand = dict(brand or {})
        brand["vertical"] = args.vertical
    doc = build(audit, brand)
    out = args.out or "goals.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
    prio = doc["priorities"]
    print(f"{out} — {len(doc['candidates'])} candidates "
          f"({len(doc['collected'])} collected, {len(doc['native'])} native, "
          f"{len(doc['roadmap'])} gaps), {len(doc['excluded'])} to avoid")
    print(f"  north star: {(prio['north_star'] or {}).get('name')}")
    print(f"  blind stages: {', '.join(b['stage'] for b in prio['blind_stages']) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
