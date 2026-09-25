#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data-foundation enrichment for the engagement review (OPTIONAL, no network).

Cross-references the client's *data-collection audit* (tagging plan) with the
Reports-API engagement analysis, to deepen three areas: conversion measurement,
pillar maturity, and strategic recommendations.

The audit is produced by the data-collection tooling **vendored in this skill**
(`scripts/parse_tagging_plan.py` + `scripts/analyze_tagging_plan.py`, originally from
the `datacollection_audit` project):
  raw tagging-plan .json
    -> parse_tagging_plan.py  -> inventory.json   (client-only taxonomy, ua_* excluded)
    -> analyze_tagging_plan.py -> analysis.json    (intents, value-bearing, gaps, provenance)

This module CONSUMES those two JSONs (single source of truth for the schema — it
never re-implements the parser/analyzer). It is a **strictly optional** input:

  * With the audit  -> conversion/maturity/reco sections gain data-backed facts and a
    "Data foundation & tracking coverage" block.
  * Without it      -> every helper returns a neutral/empty result and the report is
    unchanged (graceful degradation). Callers gate on `audit["available"]`.

Exhaustiveness: helpers process EVERY tracked item (events / attributes / tags /
subscription lists) and EVERY Reports KPI — no silent top-N.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional, Sequence

# Location of the parse+analyze scripts (used only if a RAW .json is passed and we
# must run parse+analyze ourselves). The scripts are now VENDORED in this skill
# (self-contained); the legacy sibling-skill paths are kept as a back-compat fallback.
_LOCAL_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_SIBLING_DIR_CANDIDATES = [
    _LOCAL_SCRIPT_DIR,  # vendored in this skill (self-contained)
    os.path.expanduser("~/.cursor/skills/airship-tagging-plan-review/scripts"),  # legacy
    os.path.expanduser("~/.cursor/skills-cursor/airship-tagging-plan-review/scripts"),
]

# Engagement-review strategic pillars (must match campaign_playbook.json).
PILLARS = ("editorial", "onboarding_adoption", "service", "lifecycle",
           "engagement_data", "commercial")

# Audit event-intent -> engagement-review pillar.
_INTENT_TO_PILLAR = {
    "conversion": "commercial",
    "consideration": "commercial",
    "browse": "editorial",
    "account": "onboarding_adoption",
    "loyalty": "commercial",
    "engagement": "engagement_data",
    "location": "service",
    "lifecycle": "lifecycle",
    "other": "engagement_data",
}

# Airship goal opportunity (per audit intent) — engagement-review framing.
_GOAL_PILLAR = {
    "conversion": "commercial",
    "consideration": "lifecycle",   # cart-abandon recovery
}


# Reader-facing pillar wording. The pillar keys are machine identifiers, so
# interpolating one straight into a sentence prints "unlocks engagement_data
# journeys" to the client.
_PILLAR_LABEL = {
    "editorial": ("editorial", "éditoriaux"),
    "onboarding_adoption": ("onboarding & adoption", "d’onboarding & d’adoption"),
    "service": ("service", "de service"),
    "lifecycle": ("lifecycle", "de cycle de vie"),
    "engagement_data": ("engagement & data", "d’engagement & de data"),
    "commercial": ("commercial", "commerciaux"),
}


def _L(lang: str, en: str, fr: str) -> str:
    return fr if (lang or "en").lower().startswith("fr") else en


def _pillar_words(pillar: str, lang: str) -> str:
    en, fr = _PILLAR_LABEL.get(pillar, (pillar, pillar))
    return _L(lang, en, fr)


# --------------------------------------------------------------------------- #
# Concept matching (light, bilingual) — reused to detect what is tracked.
# --------------------------------------------------------------------------- #
def _norm(s: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(s or "").lower())


def _tokens(s: Any) -> set:
    return {t for t in re.split(r"[^a-z0-9]+", str(s or "").lower()) if len(t) >= 3}


# Concept -> the token variants (EN/FR) that signal it is collected.
_CONCEPTS = {
    "first_name": {"first", "firstname", "prenom", "given"},
    "last_name": {"last", "lastname", "surname", "nom", "familyname"},
    "email": {"email", "mail", "courriel"},
    "phone": {"phone", "telephone", "tel", "gsm", "msisdn", "mobile"},
    "birthdate": {"birthdate", "birthday", "dob", "naissance", "anniversaire", "birth"},
    "city": {"city", "ville", "town", "zipcode", "zip", "postal", "codepostal"},
    "country": {"country", "pays", "nation"},
    "gender": {"gender", "genre", "sexe", "civilite", "civility"},
    "language": {"language", "langue", "lang", "locale"},
    "loyalty_tier": {"tier", "palier", "niveau", "rank", "grade", "statut", "loyalty", "fidelite"},
    "loyalty_points": {"points", "point", "cagnotte", "solde", "crowns", "couronnes", "balance"},
    "consent": {"optin", "optout", "consent", "consentement", "subscription", "subscribe"},
    "identity_id": {"userid", "customerid", "accountid", "nameduser", "contact", "fid", "crmid", "memberid"},
    "cart": {"cart", "panier", "basket", "bag", "addtocart", "wishlist", "favorite", "favori"},
    "purchase": {"purchase", "order", "commande", "achat", "checkout", "transaction", "payment", "paiement", "buy"},
    "product": {"product", "produit", "article", "item", "sku", "ean"},
    "category": {"category", "categorie", "rayon", "department", "aisle", "genre"},
    "browse": {"view", "browse", "search", "read", "watch", "play", "stream", "listen", "content", "video"},
    "account": {"register", "registration", "signup", "login", "account", "compte", "inscription", "onboard"},
    "location": {"location", "geofence", "store", "magasin", "checkin", "geo", "proximity", "proximite"},
    "coupon": {"coupon", "voucher", "bon", "offer", "offre", "promo", "reward", "recompense"},
    "churn_score": {"score", "propensity", "propension", "rfm", "churn", "segment", "prediction", "predictive"},
    "sendtime": {"sendtime", "besttime", "sto", "optimaltime"},
}


def _tracked_token_pool(inventory: dict) -> set:
    """All tokens from tracked event names, property names, attribute keys, tags, screens."""
    pool: set = set()
    for e in inventory.get("customEvents", []):
        pool |= _tokens(e.get("name"))
        for p in e.get("properties", []) or []:
            pool |= _tokens(p.get("name"))
    for a in inventory.get("attributes", []):
        pool |= _tokens(a.get("key"))
        pool |= _tokens(a.get("normalized"))
    for t in inventory.get("tags", []):
        pool |= _tokens(t.get("key"))
        pool |= _tokens(t.get("group"))
        pool |= _tokens(t.get("value"))
    for s in inventory.get("screens", []):
        pool |= _tokens(s.get("name"))
    for lst in inventory.get("subscriptionLists", []):
        pool |= _tokens(lst.get("listId"))
    return pool


def _has_concept(pool: set, concept: str) -> bool:
    return bool(pool & _CONCEPTS.get(concept, set()))


def _concept_evidence(inventory: dict, concept: str) -> List[str]:
    """Return the tracked item labels that evidence a concept (exhaustive, deduped)."""
    toks = _CONCEPTS.get(concept, set())
    hits: List[str] = []
    seen: set = set()

    def add(label: Any):
        s = str(label or "").strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            hits.append(s)

    for a in inventory.get("attributes", []):
        if (_tokens(a.get("key")) | _tokens(a.get("normalized"))) & toks:
            add(a.get("key"))
    for e in inventory.get("customEvents", []):
        if _tokens(e.get("name")) & toks:
            add(e.get("name"))
        else:
            for p in e.get("properties", []) or []:
                if _tokens(p.get("name")) & toks:
                    add(f"{e.get('name')}.{p.get('name')}")
    for lst in inventory.get("subscriptionLists", []):
        if _tokens(lst.get("listId")) & toks:
            add(lst.get("listId"))
    for t in inventory.get("tags", []):
        if (_tokens(t.get("group")) | _tokens(t.get("value"))) & toks:
            add(t.get("key"))
    return hits


# --------------------------------------------------------------------------- #
# Load / assemble the audit
# --------------------------------------------------------------------------- #
def _neutral(reason: str, path_error: bool = False, tried: Optional[list] = None) -> dict:
    """The "no audit" answer.

    `path_error` separates the two absences a caller must not confuse: a client who has no
    tagging plan (fine, every consumer degrades) from a plan that was supplied and not
    found or not readable (a wiring bug). A review shipped its event appendix as "N/A — no
    tagging-plan audit" while three other sections analysed that same plan, because both
    cases returned the same sentence. `tried` lists the paths looked at, so the answer says
    where to put the file rather than only that it is missing.
    """
    return {"available": False, "reason": reason, "path_error": path_error,
            "tried": tried or [], "analysis": None, "inventory": None, "foundation": None}


def _has_scripts(d: Optional[str]) -> bool:
    return bool(d) and os.path.isfile(os.path.join(d, "parse_tagging_plan.py")) \
        and os.path.isfile(os.path.join(d, "analyze_tagging_plan.py"))


def _find_sibling_dir() -> Optional[str]:
    """Return the dir holding parse/analyze — the vendored in-skill copy first."""
    env = os.environ.get("TAGGING_PLAN_SKILL_DIR")
    if _has_scripts(env):
        return env
    for d in _SIBLING_DIR_CANDIDATES:
        if _has_scripts(d):
            return d
    return None


def _run_sibling(raw_path: str, sibling_dir: str,
                 vertical: Optional[str] = None) -> Optional[Dict[str, dict]]:
    """Run the vendored parse+analyze on a RAW tagging-plan .json -> {inventory, analysis}.

    When `vertical` is given it is passed to analyze_tagging_plan.py so the coverage /
    best-practice comparison uses the RIGHT vertical (else the analyzer auto-suggests one,
    which can be wrong — e.g. defaulting a grocery retailer to Restaurant & QSR).
    """
    parse = os.path.join(sibling_dir, "parse_tagging_plan.py")
    analyze = os.path.join(sibling_dir, "analyze_tagging_plan.py")
    if not (os.path.isfile(parse) and os.path.isfile(analyze)):
        return None
    tmp = tempfile.mkdtemp(prefix="df_audit_")
    inv_p = os.path.join(tmp, "inventory.json")
    ana_p = os.path.join(tmp, "analysis.json")
    analyze_cmd = [sys.executable, analyze, inv_p, "-o", ana_p]
    if vertical:
        analyze_cmd[3:3] = ["--vertical", vertical]
    try:
        subprocess.run([sys.executable, parse, raw_path, "-o", inv_p], check=True,
                       capture_output=True)
        subprocess.run(analyze_cmd, check=True, capture_output=True)
        with open(inv_p, encoding="utf-8") as fh:
            inventory = json.load(fh)
        with open(ana_p, encoding="utf-8") as fh:
            analysis = json.load(fh)
        return {"inventory": inventory, "analysis": analysis}
    except (subprocess.CalledProcessError, OSError, ValueError):
        return None


def load(analysis_path: Optional[str] = None, inventory_path: Optional[str] = None,
         raw_path: Optional[str] = None, sibling_dir: Optional[str] = None,
         vertical: Optional[str] = None) -> dict:
    """Load the audit into a normalized `audit` dict; never raises.

    Precedence: explicit analysis+inventory JSONs > raw tagging-plan .json (run the
    sibling parse+analyze) > nothing (available=False). Downstream code always checks
    `audit["available"]` before using any enrichment.
    """
    tried = [p for p in (inventory_path, analysis_path, raw_path) if p]
    inventory = analysis = None
    try:
        if inventory_path and os.path.isfile(inventory_path):
            with open(inventory_path, encoding="utf-8") as fh:
                inventory = json.load(fh)
        if analysis_path and os.path.isfile(analysis_path):
            with open(analysis_path, encoding="utf-8") as fh:
                analysis = json.load(fh)
    except (OSError, ValueError) as e:
        return _neutral(f"could not read audit JSON: {e}", path_error=True, tried=tried)

    if (inventory is None or analysis is None) and raw_path and os.path.isfile(raw_path):
        sib = sibling_dir or _find_sibling_dir()
        if not sib:
            return _neutral("raw tagging-plan .json given but the vendored parse/analyze "
                            "scripts were not found (set TAGGING_PLAN_SKILL_DIR to override)",
                            path_error=True, tried=tried)
        got = _run_sibling(raw_path, sib, vertical=vertical)
        if not got:
            return _neutral("failed to run the vendored parse+analyze on the raw .json",
                            path_error=True, tried=tried)
        inventory, analysis = got["inventory"], got["analysis"]

    if inventory is None or analysis is None:
        # Nothing was found anywhere. That is a legitimate state for a client with no
        # tagging plan, so it is NOT a path_error — but the reason names the paths tried,
        # because the other way to reach this line is a file sitting one directory away.
        where = ", ".join(tried) if tried else "no path given"
        return _neutral(f"no tagging-plan audit provided (optional input) — looked in: {where}",
                        tried=tried)

    audit = {"available": True, "reason": None, "path_error": False, "tried": tried,
             "analysis": analysis, "inventory": inventory}
    audit["foundation"] = build_foundation(audit)
    return audit


# --------------------------------------------------------------------------- #
# Foundation summary
# --------------------------------------------------------------------------- #
def _pct(n: float, d: float) -> Optional[float]:
    return round(100.0 * n / d, 1) if d else None


def build_foundation(audit: dict) -> Optional[dict]:
    """Compact, exhaustive summary of the client's data foundation."""
    if not audit.get("available"):
        return None
    an = audit["analysis"]
    inv = audit["inventory"]
    prov = an.get("provenance") or {}
    src = (prov.get("sourceSplit") or {}).get("events") or {}
    sdk = int(src.get("SDK", 0)); api = int(src.get("API", 0)); unk = int(src.get("Unknown", 0))
    total_ev = sdk + api + unk

    conv = an.get("conversionSignals") or []
    value_instrumented = sum(1 for c in conv if c.get("hasValue") or c.get("carriesAmount"))
    monetary = an.get("monetaryValue") or []

    gaps = an.get("gaps") or {}
    return {
        "profile": an.get("profile"),
        "vertical": an.get("chosenVertical"),
        "suggested_vertical": an.get("suggestedVertical"),
        "counts": an.get("counts") or {},
        "intents": {k: len(v) for k, v in (an.get("eventsByIntent") or {}).items()},
        "source_split": {"sdk": sdk, "api": api, "unknown": unk,
                         "sdk_pct": _pct(sdk, total_ev), "api_pct": _pct(api, total_ev)},
        # `*_fr` are the analyzer's French renderings of the same findings; they fall
        # back to English so a plan analysed by an older script still resolves.
        "storage_verdict": (prov.get("storageLevel") or {}).get("verdict"),
        "storage_verdict_fr": ((prov.get("storageLevel") or {}).get("verdictFr")
                               or (prov.get("storageLevel") or {}).get("verdict")),
        "storage_signals": (prov.get("storageLevel") or {}).get("signals") or [],
        "storage_signals_fr": ((prov.get("storageLevel") or {}).get("signalsFr")
                               or (prov.get("storageLevel") or {}).get("signals") or []),
        "cadence_verdict": (prov.get("cadence") or {}).get("verdict"),
        "cadence_verdict_fr": ((prov.get("cadence") or {}).get("verdictFr")
                               or (prov.get("cadence") or {}).get("verdict")),
        "coverage": {"attributes_pct": (gaps.get("attributeCoverage") or {}).get("pct"),
                     "events_pct": (gaps.get("eventCoverage") or {}).get("pct")},
        "conversion_events": len(conv),
        "value_instrumented": value_instrumented,
        "value_instrumentation_pct": _pct(value_instrumented, len(conv)),
        "monetary_events": len(monetary),
        "monetary_units": sorted({m.get("inferredUnit") for m in monetary if m.get("inferredUnit")}),
        "subscription_lists": len(inv.get("subscriptionLists", [])),
        "tags": len(inv.get("tags", [])),
        "screens": len(inv.get("screens", [])),
        "values_truncated": bool(inv.get("valuesTruncated")),
        "caveats": an.get("caveats") or [],
    }


# --------------------------------------------------------------------------- #
# 1. Conversion cross-reference (audit-backed value/currency)
# --------------------------------------------------------------------------- #
def _audit_event_index(analysis: dict) -> Dict[str, dict]:
    """Normalized-name -> merged audit facts (value-bearing + conversion signal)."""
    idx: Dict[str, dict] = {}
    for v in analysis.get("valueBearing") or []:
        idx.setdefault(_norm(v.get("name")), {}).update({
            "name": v.get("name"), "impliesValue": v.get("impliesValue"),
            "hasValue": v.get("hasValue"), "carriesAmount": v.get("carriesAmount"),
            "valueProperty": v.get("valueProperty"), "missingValue": v.get("missingValue"),
            "valueField": v.get("valueField"), "properties": v.get("properties"),
        })
    for c in analysis.get("conversionSignals") or []:
        row = idx.setdefault(_norm(c.get("name")), {})
        row.setdefault("name", c.get("name"))
        row["intent"] = c.get("intent")
        row["suggestedGoal"] = c.get("suggestedGoal")
        row.setdefault("hasValue", c.get("hasValue"))
        row.setdefault("carriesAmount", c.get("carriesAmount"))
        row.setdefault("valueField", c.get("valueField"))
    return idx


def value_index(audit: dict) -> Dict[str, dict]:
    """`{normalized_event_name: value facts}` for `event_analysis.opportunity_gaps`.

    Lets the Reports-only enrich-value verdict become a FACT (the tagging plan knows
    whether an event carries an amount/value property). Empty when no audit.
    """
    if not audit.get("available"):
        return {}
    out: Dict[str, dict] = {}
    for v in audit["analysis"].get("valueBearing") or []:
        out[_norm(v.get("name"))] = {
            "has_value": bool(v.get("hasValue")),
            "carries_amount": bool(v.get("carriesAmount")),
            "value_property": v.get("valueProperty"),
            "missing_value": bool(v.get("missingValue")),
        }
    return out


def cross_reference_conversion(reports_events: Sequence[dict], audit: dict) -> dict:
    """Attach audit facts to each Reports conversion KPI + list tracked-not-fired ones.

    `reports_events` = the `events` array from `event_analysis.analyze(...)` (each with
    `name`, `classification.is_conversion`, `value_monetary`, ...). Returns:
      - `kpis`: one row per Reports conversion KPI with audit-backed value/currency facts,
      - `tracked_not_fired`: conversion/value-bearing events tracked in the audit but with
        no Reports firing in the window (design intent vs actual firing).
    """
    if not audit.get("available"):
        return {"available": False, "kpis": [], "tracked_not_fired": []}
    idx = _audit_event_index(audit["analysis"])
    fired: set = set()
    kpis: List[dict] = []
    for ev in reports_events or []:
        cls = ev.get("classification") or {}
        if not cls.get("is_conversion"):
            continue
        nm = _norm(ev.get("name"))
        fired.add(nm)
        a = idx.get(nm) or {}
        vf = a.get("valueField") or {}
        reports_monetary = bool((ev.get("value_monetary") or {}).get("value_is_monetary"))
        carries_value = bool(a.get("carriesAmount") or a.get("valueProperty") or reports_monetary)
        kpis.append({
            "name": ev.get("name"),
            "tracked_in_audit": bool(a),
            "value_bearing_by_design": bool(a.get("impliesValue")),
            "carries_value": carries_value,
            "carries_currency": bool(a.get("valueProperty")
                                     and re.search(r"currency|devise", a.get("valueProperty") or "", re.I)),
            "value_property": a.get("valueProperty"),
            "inferred_unit": vf.get("inferredUnit"),
            "unit_confidence": vf.get("unitConfidence"),
            "missing_value": bool(a.get("missingValue")) and not reports_monetary,
            "audit_properties": a.get("properties") or [],
        })
    tracked_not_fired = []
    for nm, a in idx.items():
        if nm in fired:
            continue
        if a.get("intent") in ("conversion", "consideration") or a.get("impliesValue"):
            tracked_not_fired.append({
                "name": a.get("name"), "intent": a.get("intent"),
                "carries_value": bool(a.get("carriesAmount") or a.get("valueProperty")),
                "suggested_goal": a.get("suggestedGoal"),
            })
    tracked_not_fired.sort(key=lambda r: str(r.get("name")))
    return {"available": True, "kpis": kpis, "tracked_not_fired": tracked_not_fired}


# --------------------------------------------------------------------------- #
# 2. Data-driven personalization ladder
# --------------------------------------------------------------------------- #
def personalization_ladder_from_audit(audit: dict, lang: str = "en") -> Optional[List[dict]]:
    """Build the 3-level ladder from ACTUAL tracked attributes/events/lists/tags.

    Shape matches `report_interactive.personalization_ladder(levels)`:
      [{level, title, items:[{label, done}]}]. Returns None when no audit (caller keeps
    its own fallback).
    """
    if not audit.get("available"):
        return None
    inv = audit["inventory"]
    pool = _tracked_token_pool(inv)
    has_lists = bool(inv.get("subscriptionLists"))
    has_tags = bool(inv.get("tags"))

    def item(concept: str, en: str, fr: str, done: Optional[bool] = None) -> dict:
        return {"label": _L(lang, en, fr),
                "done": _has_concept(pool, concept) if done is None else done}

    lvl1 = {"level": _L(lang, "Level 1", "Niveau 1"),
            "title": _L(lang, "Identity & profile", "Identité & profil"),
            "items": [
                item("identity_id", "Named-user / contact ID", "ID contact / named-user"),
                {"label": _L(lang, "Name / email / phone", "Nom / email / téléphone"),
                 "done": _has_concept(pool, "first_name") or _has_concept(pool, "email")
                 or _has_concept(pool, "phone")},
                {"label": _L(lang, "Loyalty tier / points", "Palier / points fidélité"),
                 "done": _has_concept(pool, "loyalty_tier") or _has_concept(pool, "loyalty_points")},
                {"label": _L(lang, "Consent / subscription lists", "Consentement / listes d’abonnement"),
                 "done": has_lists or _has_concept(pool, "consent")},
            ]}
    lvl2 = {"level": _L(lang, "Level 2", "Niveau 2"),
            "title": _L(lang, "Behaviour & content", "Comportement & contenu"),
            "items": [
                item("browse", "Browse / content consumption", "Navigation / consommation de contenu"),
                item("cart", "Cart / wishlist signals", "Signaux panier / liste d’envies"),
                item("purchase", "Purchase / transaction", "Achat / transaction"),
                {"label": _L(lang, "Product / category affinity", "Affinité produit / catégorie"),
                 "done": _has_concept(pool, "product") or _has_concept(pool, "category")
                 or has_tags},
            ]}
    lvl3 = {"level": _L(lang, "Level 3", "Niveau 3"),
            "title": _L(lang, "Context & prediction", "Contexte & prédiction"),
            "items": [
                item("location", "Location / proximity", "Géolocalisation / proximité"),
                item("sendtime", "Send-time optimization", "Optimisation de l’heure d’envoi"),
                {"label": _L(lang, "Predictive reco / affinity model", "Reco prédictive / modèle d’affinité"),
                 "done": False},
                item("churn_score", "Churn / propensity score", "Score churn / propension"),
            ]}
    return [lvl1, lvl2, lvl3]


# --------------------------------------------------------------------------- #
# 3. Lever data-readiness (does the client already track what a lever needs?)
# --------------------------------------------------------------------------- #
# lever key -> the concept(s) whose presence makes the lever activatable now.
LEVER_DATA_REQUIREMENTS = {
    # editorial / content
    "new_content_alert": ["browse"],
    "trending_now": ["product", "browse"],
    "editorial_selection": ["browse", "category"],
    "personalized_reco": ["product", "category", "browse"],
    "newsletter_digest": ["browse"],
    "last_chance_content": ["browse"],
    "coming_soon_teaser": ["browse"],
    "live_companion": ["browse"],
    # onboarding & adoption
    "welcome_onboarding": ["account", "identity_id"],
    "optin_request": ["consent"],
    "reoptin_permission": ["consent"],
    "first_action_activation": ["purchase", "browse"],
    "feature_education": ["account", "browse"],
    "account_creation": ["account"],
    "cross_device_adoption": ["identity_id"],
    # service / transactional
    "order_status": ["purchase"],
    "transactional_confirm": ["purchase"],
    "reminder_service": ["purchase", "location"],
    "realtime_service_alert": ["location"],
    "balance_usage_info": ["loyalty_points"],
    # lifecycle & retention
    "inactive_reactivation": ["purchase", "browse"],
    "winback": ["purchase"],
    "anti_churn": ["churn_score", "purchase"],
    "renewal": ["purchase"],
    "birthday_anniversary": ["birthdate"],
    "abandonment_recovery": ["cart", "browse"],
    "milestone_retrospective": ["purchase", "loyalty_points"],
    # engagement & data
    "survey_nps": ["identity_id"],
    "progressive_profiling": ["identity_id"],
    "referral_engagement": ["identity_id"],
    # commercial / monetization
    "upsell_premium": ["purchase"],
    "free_trial": ["purchase"],
    "promotion_offer": ["coupon"],
    "cross_sell_product": ["purchase", "product"],
    "abandoned_cart_commercial": ["cart"],
    "coupon_couponing": ["coupon"],
    "loyalty_offer": ["loyalty_points", "loyalty_tier", "coupon"],
}


def lever_data_readiness(recos: Sequence[dict], audit: dict) -> Dict[str, dict]:
    """For each recommended lever, whether the required data is already tracked.

    Returns {lever_key: {data_ready: True|False|None, evidence: [...], requirement: [...]}}.
    `None` = no requirement mapped (do not claim readiness either way).
    """
    if not audit.get("available"):
        return {}
    inv = audit["inventory"]
    pool = _tracked_token_pool(inv)
    out: Dict[str, dict] = {}
    for r in recos or []:
        lever = r.get("lever")
        reqs = LEVER_DATA_REQUIREMENTS.get(lever)
        if not reqs:
            out[lever] = {"data_ready": None, "evidence": [], "requirement": []}
            continue
        evidence: List[str] = []
        ready = False
        for c in reqs:
            if _has_concept(pool, c):
                ready = True
                evidence.extend(_concept_evidence(inv, c)[:3])
        out[lever] = {"data_ready": ready, "evidence": sorted(set(evidence))[:5],
                      "requirement": reqs}
    return out


def annotate_recommendations(recos: Sequence[dict], audit: dict) -> List[dict]:
    """Attach `data_readiness` to each reco and surface activatable-now levers first.

    Returns a NEW list (originals untouched). When no audit, returns the recos as-is.
    Sort keeps data-ready levers ahead of data-gap ones WITHIN the existing relevance
    order, so "you already track the data — activate this now" rises to the top.
    """
    if not audit.get("available"):
        return list(recos or [])
    readiness = lever_data_readiness(recos, audit)
    out = []
    for i, r in enumerate(recos or []):
        rd = readiness.get(r.get("lever"), {"data_ready": None, "evidence": [], "requirement": []})
        nr = dict(r)
        nr["data_readiness"] = rd
        out.append((i, nr))
    rank = {True: 0, None: 1, False: 2}
    out.sort(key=lambda t: (rank.get(t[1]["data_readiness"]["data_ready"], 1), t[0]))
    return [nr for _i, nr in out]


# --------------------------------------------------------------------------- #
# 4. Data-collection & activation recommendations
# --------------------------------------------------------------------------- #
def _intent_of(name: str) -> str:
    n = str(name or "").lower()
    for concept, pillar in (("purchase", "conversion"), ("cart", "consideration"),
                            ("account", "account"), ("loyalty_points", "loyalty"),
                            ("browse", "browse"), ("location", "location")):
        if _tokens(name) & _CONCEPTS.get(concept, set()):
            return concept if concept in _INTENT_TO_PILLAR else "other"
    return "other"


def data_collection_recos(audit: dict, lang: str = "en") -> List[dict]:
    """Turn EVERY gap + conversion-signal + missing-value into a pillar-tagged reco.

    Kinds: `track_event`, `enrich_event`, `collect_attribute`, `add_value`, `activate_goal`.
    Contextual layer -> confidence capped at Medium.
    """
    if not audit.get("available"):
        return []
    an = audit["analysis"]
    gaps = an.get("gaps") or {}
    recos: List[dict] = []

    for ev in gaps.get("events", []):
        status = ev.get("status")
        name = ev.get("recommendedName")
        pillar = _INTENT_TO_PILLAR.get(_intent_of(name), "engagement_data")
        if status == "missing":
            recos.append({
                "kind": "track_event", "pillar": pillar, "confidence": "Medium",
                "tag": "[Data+Context]", "target": name,
                "title": _L(lang, f"Start tracking '{name}'", f"Commencer à tracker « {name} »"),
                "detail": _L(lang,
                             f"Recommended for the vertical but not collected — unlocks {_pillar_words(pillar, 'en')} journeys.",
                             f"Recommandé pour la verticale mais non collecté — débloque des parcours {_pillar_words(pillar, 'fr')}."),
            })
        elif status == "partial" and ev.get("missingProperties"):
            props = ", ".join(ev.get("missingProperties") or [])
            recos.append({
                "kind": "enrich_event", "pillar": pillar, "confidence": "Medium",
                "tag": "[Data+Context]", "target": ev.get("matchedName") or name,
                "title": _L(lang, f"Enrich '{ev.get('matchedName') or name}'",
                            f"Enrichir « {ev.get('matchedName') or name} »"),
                "detail": _L(lang, f"Add the recommended properties: {props}.",
                             f"Ajouter les propriétés recommandées : {props}."),
            })

    for at in gaps.get("attributes", []):
        if at.get("status") != "missing":
            continue
        name = at.get("recommendedName") or at.get("recommendedId")
        recos.append({
            "kind": "collect_attribute", "pillar": "engagement_data", "confidence": "Medium",
            "tag": "[Data+Context]", "target": at.get("recommendedId"),
            "title": _L(lang, f"Collect attribute '{name}'", f"Collecter l'attribut « {name} »"),
            "detail": _L(lang, "Recommended profile trait for segmentation & personalization.",
                         "Trait de profil recommandé pour la segmentation & la personnalisation."),
        })

    for v in an.get("valueBearing") or []:
        if not v.get("missingValue"):
            continue
        recos.append({
            "kind": "add_value", "pillar": "commercial", "confidence": "Medium",
            "tag": "[Data]", "target": v.get("name"),
            "title": _L(lang, f"Add value + currency to '{v.get('name')}'",
                        f"Ajouter valeur + devise à « {v.get('name')} »"),
            "detail": _L(lang,
                         "Conversion event with no amount — send the value (+ currency) so Airship can attribute revenue.",
                         "Événement de conversion sans montant — envoyer la valeur (+ devise) pour attribuer le revenu dans Airship."),
        })

    for c in an.get("conversionSignals") or []:
        pillar = _GOAL_PILLAR.get(c.get("intent"), "commercial")
        recos.append({
            "kind": "activate_goal", "pillar": pillar, "confidence": "Medium",
            "tag": "[Data+Context]", "target": c.get("name"),
            "title": _L(lang, f"Activate an Airship goal on '{c.get('name')}'",
                        f"Activer un goal Airship sur « {c.get('name')} »"),
            "detail": (_L(lang, c.get("suggestedGoal"), c.get("suggestedGoalFr"))
                       or c.get("suggestedGoal")
                       or _L(lang, "Conversion goal on push / email / in-app.",
                             "Goal de conversion sur push / email / in-app.")),
        })

    order = {p: i for i, p in enumerate(PILLARS)}
    kind_order = {"activate_goal": 0, "add_value": 1, "enrich_event": 2,
                  "track_event": 3, "collect_attribute": 4}
    recos.sort(key=lambda r: (order.get(r["pillar"], 9), kind_order.get(r["kind"], 9),
                              str(r.get("target"))))
    return recos


# --------------------------------------------------------------------------- #
# 5. Foundation scorecard (for the compact report block)
# --------------------------------------------------------------------------- #
def foundation_scorecard(audit: dict) -> Optional[dict]:
    """Alias for the precomputed foundation summary (kept for API symmetry)."""
    if not audit.get("available"):
        return None
    return audit.get("foundation") or build_foundation(audit)


def monetary_summary(audit: dict) -> dict:
    """Whether the client collects MONETARY (currency) values, and which events carry them.

    This is a high-value signal: monetary instrumentation lets Airship attribute *revenue*
    (not just opens/counters). Sources, in order: analysis `monetaryValue`, `valueBearing`
    (carriesAmount), and `eventProperties[].valueField.carriesAmount`. Returns a dict the
    report can use to (a) flag it in the events appendix, (b) surface it in the executive
    summary, and (c) valorise it in attribution / conversion-evolution. Graceful when absent:
    `{"available": False, "has_monetary": False, ...}` so callers can state the GAP instead.
    """
    out = {"available": False, "has_monetary": False, "amount_events": [],
           "count": 0, "units": [], "total_events": 0}
    if not audit or not audit.get("available"):
        return out
    an = audit.get("analysis") or {}
    out["available"] = True
    idx: Dict[str, dict] = {}
    for e in an.get("eventProperties") or []:
        vf = e.get("valueField") or {}
        if vf.get("carriesAmount"):
            idx[_norm(e.get("name"))] = {
                "name": e.get("name"), "total": e.get("total"),
                "distinct_amounts": vf.get("distinctAmounts"),
                "intent": e.get("intent"), "source": e.get("source")}
    for v in an.get("valueBearing") or []:
        if v.get("carriesAmount"):
            idx.setdefault(_norm(v.get("name")), {"name": v.get("name")})
    mon = an.get("monetaryValue") or []
    for m in mon:
        row = idx.setdefault(_norm(m.get("name")), {"name": m.get("name")})
        if m.get("inferredUnit"):
            row["unit"] = m.get("inferredUnit")
    out["amount_events"] = sorted(idx.values(), key=lambda r: -(r.get("total") or 0))
    out["count"] = len(idx)
    out["has_monetary"] = bool(idx)
    out["units"] = sorted({m.get("inferredUnit") for m in mon if m.get("inferredUnit")})
    out["total_events"] = len(an.get("eventProperties") or [])
    return out


# --------------------------------------------------------------------------- #
# self-test
# --------------------------------------------------------------------------- #
def _demo_audit() -> dict:
    inventory = {
        "meta": {"profile": "DEMO"},
        "platforms": ["iOS", "Android", "API"],
        "customEvents": [
            {"name": "purchase", "source": "SDK", "total": 1000,
             "platforms": {"iOS": 600, "Android": 400},
             "properties": [{"name": "amount", "samples": [{"value": "42.50", "count": 3}]}],
             "valueSamples": [{"value": "42.50", "count": 3}]},
            {"name": "add_to_cart", "source": "SDK", "total": 5000,
             "platforms": {"iOS": 3000}, "properties": [], "valueSamples": []},
            {"name": "product_view", "source": "SDK", "total": 20000,
             "platforms": {"iOS": 12000}, "properties": [{"name": "category", "samples": []}],
             "valueSamples": []},
        ],
        "attributes": [
            {"key": "first_name", "normalized": "first_name", "total": 100, "actions": "set:100",
             "sources": "API", "platforms": {"Email": 100}, "sampleValues": ["Anna"]},
            {"key": "loyalty_tier", "normalized": "loyalty_tier", "total": 80, "actions": "set:80",
             "sources": "API", "platforms": {"Email": 80}, "sampleValues": ["Gold"]},
        ],
        "tags": [{"key": "interest:sports", "group": "interest", "value": "sports", "net": 50}],
        "subscriptionLists": [{"listId": "newsletter", "subscribe": 500, "unsubscribe": 10, "net": 490}],
        "screens": [{"name": "home", "total": 9000}],
        "excludedAirship": {"attributes": [], "tags": []},
        "valuesTruncated": False,
    }
    sib = _find_sibling_dir()
    if sib and os.path.isfile(os.path.join(sib, "analyze_tagging_plan.py")):
        tmp = tempfile.mkdtemp(prefix="df_demo_")
        inv_p = os.path.join(tmp, "inventory.json")
        ana_p = os.path.join(tmp, "analysis.json")
        with open(inv_p, "w", encoding="utf-8") as fh:
            json.dump(inventory, fh)
        subprocess.run([sys.executable, os.path.join(sib, "analyze_tagging_plan.py"),
                        inv_p, "--vertical", "Retail", "-o", ana_p], check=True, capture_output=True)
        return load(analysis_path=ana_p, inventory_path=inv_p)
    return _neutral("vendored parse/analyze scripts not found for demo")


if __name__ == "__main__":
    # Graceful-degradation check
    absent = load()
    assert absent["available"] is False, absent
    assert cross_reference_conversion([], absent) == {"available": False, "kpis": [], "tracked_not_fired": []}
    assert personalization_ladder_from_audit(absent) is None
    assert data_collection_recos(absent) == []
    assert lever_data_readiness([{"lever": "loyalty_offer"}], absent) == {}
    assert monetary_summary(absent) == {"available": False, "has_monetary": False,
                                        "amount_events": [], "count": 0, "units": [], "total_events": 0}
    print("graceful-degradation OK")

    a = _demo_audit()
    if a.get("available"):
        f = a["foundation"]
        print("foundation:", {k: f[k] for k in ("counts", "source_split", "coverage",
                                                 "conversion_events", "value_instrumented")})
        xr = cross_reference_conversion([
            {"name": "purchase", "classification": {"is_conversion": True},
             "value_monetary": {"value_is_monetary": True}}], a)
        print("xref kpis:", xr["kpis"])
        lad = personalization_ladder_from_audit(a, lang="fr")
        print("ladder L1 done:", [(i["label"], i["done"]) for i in lad[0]["items"]])
        rd = lever_data_readiness([{"lever": "abandoned_cart_commercial"},
                                   {"lever": "loyalty_offer"}, {"lever": "birthday_anniversary"}], a)
        print("readiness:", rd)
        recos = data_collection_recos(a, lang="fr")
        print("data recos:", len(recos), "sample:", recos[0] if recos else None)
        ms = monetary_summary(a)
        print("monetary:", {"has_monetary": ms["has_monetary"], "count": ms["count"],
                            "sample": ms["amount_events"][0] if ms["amount_events"] else None})
        print("data_foundation self-test OK")
    else:
        print("demo skipped:", a.get("reason"))
