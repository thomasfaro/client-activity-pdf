#!/usr/bin/env python3
"""Campaign PURPOSE / pillar classification for the engagement review (no network).

Complements `classify_campaigns.py` (which tags one-shot vs automated/recurring) by
answering *what a campaign is for*: it maps each campaign to a strategic **pillar**
(Editorial, Onboarding & Adoption, Service, Lifecycle, Engagement & Data, Commercial)
and a standard **lever** from `campaign_playbook.json`, then computes per-pillar
**maturity** (coverage of the levers recommended for the client's vertical + the
automation share within the pillar) and **recommends** the missing levers as concrete
new campaigns to run.

Detection is **name-first** (bilingual EN/FR token/alias overlap on the message name),
with an optional **content fallback** that reads decoded `perpush/pushbody` notif text /
Message Center HTML when the name is ambiguous. Reports API only — the content used here
comes from decoded pushbodies, never the Content API.

`value` / revenue is out of scope for this module (see `event_analysis.py`).

CLI:
    python scripts/campaign_purpose.py <classified.json> --vertical retail \
        [--reachable 12000000]
  where <classified.json> is the output of classify_campaigns.py (a dict with a
  "campaigns" list) OR {"campaigns": [...], "bodies": {push_uuid: "notif text"}}.
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Sequence

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
DEFAULT_PLAYBOOK = os.path.join(SKILL_DIR, "campaign_playbook.json")

# Tokens that never help identify a campaign's purpose.
GENERIC_TOKENS = {
    "app", "push", "notif", "notification", "message", "msg", "campaign", "campagne",
    "test", "copy", "final", "prod", "the", "and", "for", "with", "from", "your", "votre",
    "les", "des", "une", "not", "new", "old", "web", "mobile", "ios", "android", "fr",
    "en", "es", "it", "de", "all", "user", "users", "client", "clients", "send", "envoi",
    "auto", "automation", "trigger", "batch", "generic", "default", "temp", "draft",
}

# Coverage thresholds.
_RELEVANCE_RECOMMENDED = 3       # relevance >= this => "recommended for the vertical"
_COVER_CONF = {"High", "Medium"}  # a lever counts as covered only at these confidences
_COVER_RELIABILITY = 0.45       # ...and only at/above this reliability (>=Medium). Keeps
                                # very-weak (Low) broad matches visible without letting them
                                # inflate pillar maturity; Medium CTA-only detections count.

# Pillar specificity/priority (higher = more specific intent, wins ties over generic
# levers). Disambiguates collisions such as "Je cree ma Carte Club": account_creation
# (onboarding) should beat loyalty_offer (commercial). Overridable per lever via a
# "priority" field in campaign_playbook.json. Used as a TIE-BREAK + a mild score weight,
# never a hard override, so a strong generic match still beats a weak specific one.
_PILLAR_PRIORITY = {
    "service": 6,
    "onboarding_adoption": 5,
    "lifecycle": 5,
    "engagement_data": 4,
    "editorial": 3,
    "commercial": 2,
}

# Reliability ceiling by detection basis / source. cta_only = in-app CTA name only
# (no full message) -> deliberately capped low; message name up to High.
_BASIS_CAP = {"name": 0.95, "content": 0.60, "cta_only": 0.45}

# Maturity tiers from pillar coverage (share of recommended levers detected).
_MATURITY_TIERS = [
    (0.70, "Mastered", "Pilier maitrise"),
    (0.45, "In consolidation", "En consolidation"),
    (0.20, "Emerging", "Fort potentiel"),
    (0.0, "Untapped", "Axe de developpement"),
]


# --------------------------------------------------------------------------- #
# Text helpers
# --------------------------------------------------------------------------- #
def _strip_accents(s: str) -> str:
    repl = (("à", "a"), ("â", "a"), ("ä", "a"), ("é", "e"), ("è", "e"), ("ê", "e"),
            ("ë", "e"), ("î", "i"), ("ï", "i"), ("ô", "o"), ("ö", "o"), ("ù", "u"),
            ("û", "u"), ("ü", "u"), ("ç", "c"), ("œ", "oe"), ("’", ""), ("'", ""))
    for a, b in repl:
        s = s.replace(a, b)
    return s


def _collapse(s: Any) -> str:
    """Lowercase, drop accents, keep alnum only (for substring alias matching)."""
    return re.sub(r"[^a-z0-9]+", "", _strip_accents(str(s or "").lower()))


def _tokens(s: Any) -> List[str]:
    raw = re.split(r"[^a-z0-9]+", _strip_accents(str(s or "").lower()))
    return [t for t in raw if t and len(t) > 2 and t not in GENERIC_TOKENS]


# Light FR/EN inflectional suffixes, longest-first; stripped iteratively down to a
# 4-char stem so "decouvrez"~"decouvre", "inscris"~"inscri", "creez"~"cree", EN
# "booking"~"book". Deliberately crude — we favour recall, not linguistic accuracy.
_SUFFIXES = ("issions", "issons", "ations", "ateurs", "ements", "ional", "ation",
             "ement", " tions", "tions", "ption", "ings", "ing", "ers", "ez", "es",
             "er", "ent", "ons", "ais", "ait", "iez", "tion", "eur", "ed", "s", "x", "z", "e")


def _stem(tok: str) -> str:
    """Iteratively strip common FR/EN suffixes down to a >=4-char stem."""
    t = _collapse(tok)
    changed = True
    while changed and len(t) > 4:
        changed = False
        for suf in _SUFFIXES:
            suf = suf.strip()
            if suf and len(t) - len(suf) >= 4 and t.endswith(suf):
                t = t[: -len(suf)]
                changed = True
                break
    return t


_FR_MARKERS = {"je", "vous", "votre", "vos", "mon", "ma", "mes", "les", "des", "une",
               "pour", "avec", "sur", "tente", "cree", "creer", "inscris", "rejoins",
               "decouvre", "profite", "participe", "veux", "bon", "carte", "club",
               "fidelite", "bienvenue", "livraison", "jeudi", "rdv", "essentiels"}
_ACCENTED = set("àâäéèêëîïôöùûüç")


def detect_lang(text: Any) -> str:
    """Very light FR/EN detector for a label/identifier ('fr' or 'en').

    Returns 'en' for anything that is not recognisably French, INCLUDING text in a third
    language. That is fine for a label, where the value is only used for reporting — but
    it is not a licence to run the English lever vocabulary over the text. See
    `covered_by_vocabulary` below, which is the guard the content fallback uses.
    """
    s = str(text or "").lower()
    if any(ch in _ACCENTED for ch in s):
        return "fr"
    toks = set(re.split(r"[^a-z0-9]+", s))
    return "fr" if (toks & _FR_MARKERS) else "en"


# Function words that any substantial run of French or English prose will contain. This is
# a coverage test, not a language identifier: the question is only "is the vocabulary we
# are about to match in the same language as this text".
#
# The short ones are deliberately absent. `du` is French *and* German, `de` is French,
# Dutch, Spanish and Portuguese, `la`/`le`/`un` are also Spanish and Italian, `in`/`an`/
# `all` are also German — and one such token is enough to wave a whole foreign body
# through. Dropping them costs nothing, because no real French sentence gets by without
# les/des/une/votre/pour/avec/est either.
_FR_EN_FUNCTION_WORDS = {
    # EN
    "the", "your", "you", "we", "our", "for", "with", "and", "are", "this", "that",
    "now", "new", "get", "save", "off", "out", "more", "just", "today", "here", "from",
    "have", "can", "what", "about", "back", "only", "make", "need", "want", "don", "my",
    # FR
    "les", "des", "une", "votre", "vos", "vous", "nous", "pour", "avec", "sur", "dans",
    "et", "ou", "est", "sont", "ce", "cette", "maintenant", "nouveau", "nouvelle",
    "plus", "tout", "tous", "chez", "mon", "mes",
}
# Below this many tokens there is not enough text to conclude anything, and a short label
# like "Coupons" or a bare "Black Friday deals" is not evidence of a foreign language.
_COVERAGE_MIN_TOKENS = 5


def covered_by_vocabulary(text: Any) -> bool:
    """Is `text` in a language the FR/EN lever vocabulary can actually read?

    The content fallback exists so a campaign with an opaque name can still be classified
    from its creative. On an account whose creative is not French or English, that fallback
    silently becomes pattern noise: a German review matched 30 campaigns from content and
    got 28 of them wrong in one direction, returning partner coupon pushes as
    `welcome_onboarding` — which would have shown the client running the onboarding
    programme the review concluded they were missing.

    A wrong answer with a confidence score attached is worse than no answer, because only
    somebody who reads German would ever catch it. So when a body carries no French or
    English function word at all, the classifier declines rather than guesses.
    """
    toks = [t for t in re.split(r"[^a-zA-Zà-ÿ0-9]+", str(text or "").lower()) if t]
    if len(toks) < _COVERAGE_MIN_TOKENS:
        return True          # too short to judge; the name-first path already ran
    return bool(set(toks) & _FR_EN_FUNCTION_WORDS)


# --------------------------------------------------------------------------- #
# Playbook loading / vertical resolution
# --------------------------------------------------------------------------- #
def load_playbook(path: Optional[str] = None) -> dict:
    with open(path or DEFAULT_PLAYBOOK, encoding="utf-8") as fh:
        return json.load(fh)


def resolve_vertical(playbook: dict, vertical: Optional[str]) -> str:
    """Return the playbook book key for a vertical input (alias-aware)."""
    return resolve_vertical_info(playbook, vertical)["key"]


def resolve_vertical_info(playbook: dict, vertical: Optional[str]) -> dict:
    """-> {key, known, fallback, input}. The flag is the point.

    `resolve_vertical` returns the input verbatim when nothing matches, which reads like a
    successful resolution and is not one. An unrecognised key does not raise and does not
    empty the output — it degrades it twice over, silently:

      * `relevance(lever, key)` finds no entry under `verticals[key]` and returns the
        lever's `base` instead, so EVERY lever's score shifts and `recommend_campaigns`
        reorders. Measured on a news account: every lever dropped from 5 to 3.
      * `stake_for(playbook, key, pillar)` finds no stakes block, so the business stake
        and key figure behind each pillar of the maturity matrix come back empty.

    Both are invisible in the output. A review shipped a recommendation ranking computed
    on base scores because its vertical was written as a display label
    ("News & digital publishing") rather than as a book key ("media"). `known` is False in
    exactly that case, and `verify_audit.check_vertical_resolution` fails on it.
    """
    stakes = playbook.get("vertical_stakes", {})
    vmap = playbook.get("vertical_map", {})
    if not vertical:
        return {"key": "all_verticals", "known": True, "fallback": False, "input": None}
    v = vertical.strip().lower()
    if v in stakes:
        return {"key": v, "known": True, "fallback": False, "input": vertical}
    mapped = vmap.get(v)
    if mapped:
        return {"key": mapped, "known": mapped in stakes, "fallback": False,
                "input": vertical}
    # Nothing matched. The key is returned so callers keep working, but it names no
    # vertical the playbook knows, and saying so is the whole reason this exists.
    return {"key": v, "known": False, "fallback": True, "input": vertical}


def relevance(lever: dict, vertical_key: str) -> int:
    return int(lever.get("verticals", {}).get(vertical_key, lever.get("base", 0)))


def stake_for(playbook: dict, vertical_key: str, pillar_key: str) -> dict:
    """Pillar stake for a vertical, falling back to the cross-vertical wording.

    The returned block carries `stake_fr` / `key_figure_fr` alongside the English
    pair. A French deliverable renders this text verbatim in the strategy matrix, so
    an English-only block is a localisation leak the delivery gate will (rightly)
    fail — the two languages have to travel together from the playbook.
    """
    stakes = playbook.get("vertical_stakes", {})
    block = stakes.get(vertical_key) or {}
    if pillar_key in block:
        return block[pillar_key]
    return stakes.get("all_verticals", {}).get(
        pillar_key, {"stake": "", "key_figure": "", "stake_fr": "", "key_figure_fr": ""})


# --------------------------------------------------------------------------- #
# Purpose (pillar + lever) classification
# --------------------------------------------------------------------------- #
def _lever_priority(lv: dict) -> int:
    return int(lv.get("priority", _PILLAR_PRIORITY.get(lv.get("pillar"), 3)))


def _match_levers(text: str, levers: Sequence[dict]) -> List[dict]:
    """Score each lever against a text (name/body/CTA). High-recall, language-aware.

    Alias hits are graded: exact token 1.0, stem-equal 0.85, substring>=5 0.7, shared
    4-char prefix 0.5 (the broad, recall-first tier). Candidates are ranked by a
    priority-weighted score (specific intents edge out generic ones on ties) but the
    raw score is kept for reliability scoring.
    """
    toks = set(_tokens(text))
    stems = {_stem(t) for t in toks}
    collapsed = _collapse(text)
    prefixes = {t[:4] for t in toks if len(t) >= 4}
    if not toks and not collapsed:
        return []
    out = []
    for lv in levers:
        hits = []
        score = 0.0
        for a in lv.get("aliases", []):
            an = _collapse(a)
            if not an:
                continue
            if an in toks:                              # exact token
                score += 1.0; hits.append(a); continue
            astem = _stem(a)
            if len(astem) >= 4 and astem in stems:      # inflection / stem match
                score += 0.85; hits.append(a); continue
            if len(an) >= 5 and an in collapsed:        # compound / substring alias
                score += 0.7; hits.append(a); continue
            if len(an) >= 4 and an[:4] in prefixes:     # broad shared-prefix (recall)
                score += 0.5; hits.append(a); continue
        if score > 0:
            weighted = score * (1.0 + 0.06 * _lever_priority(lv))
            out.append({"lever": lv, "score": score, "weighted": weighted, "hits": hits})
    out.sort(key=lambda c: c["weighted"], reverse=True)
    return out


def _reliability(score: float, basis: str, source: str) -> float:
    """Numeric reliability 0-1 = basis/source ceiling x match quality."""
    cap = _BASIS_CAP["cta_only"] if source == "cta_only" else _BASIS_CAP.get(basis, 0.6)
    quality = 1.0 if score >= 2.0 else (0.8 if score >= 1.0 else 0.55)
    return round(cap * quality, 2)


def _confidence(reliability: float) -> str:
    if reliability >= 0.70:
        return "High"
    if reliability >= 0.45:
        return "Medium"
    return "Low"


def classify_one(name: str, body_text: Optional[str], levers: Sequence[dict],
                 vertical_key: str, source: str = "message") -> dict:
    """Classify a single campaign by name first, content second (language-aware)."""
    cands = _match_levers(name or "", levers)
    basis = "name"
    if not cands and body_text:
        # The name told us nothing, so the creative is all that is left — but only if the
        # lever vocabulary speaks its language. On German copy it does not, and matching
        # anyway produces confident nonsense rather than a blank. Decline instead.
        if not covered_by_vocabulary(body_text):
            return {"pillar": None, "lever": None, "lever_label": None,
                    "confidence": None, "reliability": 0.0,
                    "basis": "unsupported language",
                    "source": source, "lang": detect_lang(name), "matched_tokens": []}
        cands = _match_levers(body_text, levers)
        basis = "content"
    if not cands:
        return {"pillar": None, "lever": None, "lever_label": None,
                "confidence": None, "reliability": 0.0, "basis": "no match",
                "source": source, "lang": detect_lang(name), "matched_tokens": []}

    # Tie-break near-equal weighted scores by vertical relevance then priority.
    top = cands[0]["weighted"]
    tied = [c for c in cands if c["weighted"] >= top - 1e-9]
    tied.sort(key=lambda c: (relevance(c["lever"], vertical_key),
                             _lever_priority(c["lever"])), reverse=True)
    best = tied[0]
    lv = best["lever"]
    rel = _reliability(best["score"], basis, source)
    return {
        "pillar": lv["pillar"],
        "lever": lv["key"],
        "lever_label": lv["label"],
        "lever_label_fr": lv.get("label_fr"),
        "default_typology": lv.get("typology"),
        "reliability": rel,
        "confidence": _confidence(rel),
        "basis": basis,
        "source": source,
        "lang": detect_lang(name),
        "matched_tokens": best["hits"],
        "score": round(best["score"], 2),
    }


def classify_purpose(campaigns: Sequence[dict], playbook: Optional[dict] = None,
                     vertical: Optional[str] = None,
                     bodies: Optional[Dict[str, str]] = None) -> List[dict]:
    """Attach pillar/lever/confidence to each campaign (name-first, content-fallback).

    campaigns: list from classify_campaigns.classify()["campaigns"] (need `label`;
      optional `type`, `total_sends`, `push_uuids`). `label` is the campaign name.
    bodies: optional {push_uuid: notif_text_or_MC_html} for the content fallback.
    """
    playbook = playbook or load_playbook()
    levers = playbook["levers"]
    vkey = resolve_vertical(playbook, vertical)
    bodies = bodies or {}
    out = []
    for c in campaigns:
        name = c.get("label") or c.get("name") or ""
        body_text = None
        uuids = c.get("push_uuids") or []
        texts = [bodies.get(u) for u in uuids if bodies.get(u)]
        if not texts and c.get("key") in bodies:
            texts = [bodies[c["key"]]]
        if texts:
            body_text = " ".join(t for t in texts if t)[:2000]
        cls = classify_one(name, body_text, levers, vkey,
                           source=c.get("source", "message"))
        row = dict(c)
        row["purpose"] = cls
        out.append(row)
    return out


# --------------------------------------------------------------------------- #
# Pillar maturity
# --------------------------------------------------------------------------- #
def _tier(coverage: float) -> dict:
    for thr, en, fr in _MATURITY_TIERS:
        if coverage >= thr:
            return {"label": en, "label_fr": fr}
    return {"label": "Untapped", "label_fr": "Axe de developpement"}


def pillar_maturity(classified: Sequence[dict], playbook: Optional[dict] = None,
                    vertical: Optional[str] = None) -> List[dict]:
    """Per-pillar coverage of recommended levers + automation/volume share + stake."""
    playbook = playbook or load_playbook()
    levers = playbook["levers"]
    vkey = resolve_vertical(playbook, vertical)
    pillars = sorted(playbook["pillars"], key=lambda p: p["order"])

    total_sends = sum(_sends(c) for c in classified) or 0

    # levers detected (covered) per pillar at High/Medium confidence
    covered_by_pillar: Dict[str, set] = {}
    all_detected_by_pillar: Dict[str, set] = {}
    camps_by_pillar: Dict[str, list] = {}
    for c in classified:
        pr = c.get("purpose") or {}
        pk = pr.get("pillar")
        if not pk:
            continue
        camps_by_pillar.setdefault(pk, []).append(c)
        all_detected_by_pillar.setdefault(pk, set()).add(pr.get("lever"))
        if (pr.get("reliability") or 0) >= _COVER_RELIABILITY:
            covered_by_pillar.setdefault(pk, set()).add(pr.get("lever"))

    rows = []
    for p in pillars:
        pk = p["key"]
        recommended = [lv for lv in levers
                       if lv["pillar"] == pk and relevance(lv, vkey) >= _RELEVANCE_RECOMMENDED]
        rec_keys = {lv["key"] for lv in recommended}
        covered = covered_by_pillar.get(pk, set()) & rec_keys
        camps = camps_by_pillar.get(pk, [])
        coverage = (len(covered) / len(rec_keys)) if rec_keys else 0.0

        auto = sum(1 for c in camps if c.get("type") == "automated_recurring")
        one = sum(1 for c in camps if c.get("type") == "one_shot")
        auto_sends = sum(_sends(c) for c in camps
                         if c.get("type") == "automated_recurring")
        p_sends = sum(_sends(c) for c in camps)

        rows.append({
            "pillar": pk,
            "label": p["label"],
            "label_fr": p["label_fr"],
            "goal": p["goal"],
            "order": p["order"],
            "stake": stake_for(playbook, vkey, pk),
            "recommended_levers": sorted(rec_keys),
            "covered_levers": sorted(covered),
            "missing_levers": sorted(rec_keys - covered),
            "coverage": round(coverage, 4),
            "coverage_pct": round(coverage * 100),
            "maturity": _tier(coverage),
            "campaigns": len(camps),
            "automated": auto,
            "one_shot": one,
            "automation_rate": round(auto / len(camps), 4) if camps else None,
            "sends": p_sends,
            "automated_sends": auto_sends,
            "automation_rate_sends": round(auto_sends / p_sends, 4) if p_sends else None,
            "volume_share": round(p_sends / total_sends, 4) if total_sends else None,
        })
    return rows


def _sends(c: dict) -> int:
    """Send volume for a campaign row, under either accepted key.

    The documented input key is `total_sends`, but `sends` is what the Reports API calls
    the same field and what most callers naturally build. Accepting only one of them made
    every volume-weighted output silently ZERO — automation_mix.by_sends, and the per-pillar
    sends / automated_sends / automation_rate_sends / volume_share — which reads as "this
    account has no send volume" rather than as a wiring error. A silent zero on a
    volume-weighted mix is the worst failure mode available here, because the count-weighted
    mix next to it can point the opposite way and still look plausible.
    """
    for k in ("total_sends", "sends"):
        v = c.get(k)
        if v:
            return int(v)
    return 0


def automation_mix(classified: Sequence[dict]) -> dict:
    """Global one-shot vs automated mix (by campaign count AND by sends)."""
    auto = one = amb = 0
    auto_s = one_s = amb_s = 0
    for c in classified:
        t = c.get("type")
        s = _sends(c)
        if t == "automated_recurring":
            auto += 1; auto_s += s
        elif t == "one_shot":
            one += 1; one_s += s
        else:
            amb += 1; amb_s += s
    n = auto + one + amb
    ns = auto_s + one_s + amb_s
    return {
        "by_count": {"automated": auto, "one_shot": one, "ambiguous": amb, "total": n,
                     "automated_rate": round(auto / n, 4) if n else None,
                     "one_shot_rate": round(one / n, 4) if n else None},
        "by_sends": {"automated": auto_s, "one_shot": one_s, "ambiguous": amb_s, "total": ns,
                     "automated_rate": round(auto_s / ns, 4) if ns else None,
                     "one_shot_rate": round(one_s / ns, 4) if ns else None},
    }


# --------------------------------------------------------------------------- #
# Recommendations (missing levers -> new campaigns)
# --------------------------------------------------------------------------- #
def recommend_campaigns(classified: Sequence[dict], playbook: Optional[dict] = None,
                        vertical: Optional[str] = None,
                        reachable: Optional[int] = None,
                        top: Optional[int] = None) -> List[dict]:
    """Recommend the levers recommended-for-vertical that the client does NOT run yet."""
    playbook = playbook or load_playbook()
    levers = playbook["levers"]
    vkey = resolve_vertical(playbook, vertical)
    pillar_order = {p["key"]: p["order"] for p in playbook["pillars"]}
    pillar_label = {p["key"]: p["label"] for p in playbook["pillars"]}

    covered = set()
    for c in classified:
        pr = c.get("purpose") or {}
        if pr.get("lever") and (pr.get("reliability") or 0) >= _COVER_RELIABILITY:
            covered.add(pr["lever"])

    recs = []
    for lv in levers:
        rel = relevance(lv, vkey)
        if rel < _RELEVANCE_RECOMMENDED or lv["key"] in covered:
            continue
        recs.append({
            "lever": lv["key"],
            "label": lv["label"],
            "label_fr": lv["label_fr"],
            "pillar": lv["pillar"],
            "pillar_label": pillar_label.get(lv["pillar"], lv["pillar"]),
            "typology": lv.get("typology"),
            "channels": lv.get("channels", []),
            "description": lv.get("description"),
            "relevance": rel,
            "stake": stake_for(playbook, vkey, lv["pillar"]),
            "priority": "High" if rel >= 5 else ("Medium" if rel >= 4 else "Standard"),
            "why": f"Recommended for {vkey.replace('_', ' ')}; not detected in the period.",
        })
    recs.sort(key=lambda r: (-r["relevance"], pillar_order.get(r["pillar"], 9)))
    if top:
        recs = recs[:top]
    return recs


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #
def analyze(campaigns: Sequence[dict], vertical: Optional[str] = None,
            bodies: Optional[Dict[str, str]] = None, reachable: Optional[int] = None,
            playbook: Optional[dict] = None) -> dict:
    playbook = playbook or load_playbook()
    vkey = resolve_vertical(playbook, vertical)
    classified = classify_purpose(campaigns, playbook, vertical, bodies)
    maturity = pillar_maturity(classified, playbook, vertical)
    mix = automation_mix(classified)
    recs = recommend_campaigns(classified, playbook, vertical, reachable)

    matched = sum(1 for c in classified if (c.get("purpose") or {}).get("pillar"))
    by_basis = {"name": 0, "content": 0, "no match": 0}
    by_reliability = {"high": 0, "medium": 0, "low": 0, "none": 0}
    by_source = {"message": 0, "cta_only": 0}
    for c in classified:
        pr = c.get("purpose") or {}
        b = pr.get("basis", "no match")
        by_basis[b] = by_basis.get(b, 0) + 1
        by_source[pr.get("source", "message")] = by_source.get(pr.get("source", "message"), 0) + 1
        rel = pr.get("reliability") or 0
        tier = "none" if not pr.get("pillar") else (
            "high" if rel >= 0.70 else "medium" if rel >= 0.45 else "low")
        by_reliability[tier] += 1

    # The resolution is reported, not just used: `known: False` means every lever score
    # below is a base score and every pillar stake is empty. `verify_audit` reads this.
    vinfo = resolve_vertical_info(playbook, vertical)
    return {
        "vertical": {"input": vertical, "book_key": vkey,
                     "known": vinfo["known"], "fallback": vinfo["fallback"]},
        "summary": {
            "campaigns": len(classified),
            "classified": matched,
            "unclassified": len(classified) - matched,
            "by_basis": by_basis,
            "by_source": by_source,
            "by_reliability": by_reliability,
            "pillars_covered": sum(1 for m in maturity if m["covered_levers"]),
            "avg_coverage": round(
                sum(m["coverage"] for m in maturity) / len(maturity), 4) if maturity else 0,
            "recommendations": len(recs),
        },
        "automation_mix": mix,
        "classified": classified,
        "maturity": maturity,
        "recommendations": recs,
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _parse_args(argv):
    pos, opts = None, {"vertical": None, "reachable": None}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            opts[a[2:]] = argv[i + 1] if i + 1 < len(argv) else None
            i += 2
        else:
            pos = a
            i += 1
    return pos, opts


def main():
    if len(sys.argv) < 2:
        # tiny self-demo
        camps = [
            {"key": "g:1", "label": "Welcome onboarding J0", "type": "automated_recurring", "total_sends": 40000},
            {"key": "g:2", "label": "Soldes ete flash sale -30%", "type": "one_shot", "total_sends": 900000},
            {"key": "g:3", "label": "Relance panier abandonne", "type": "automated_recurring", "total_sends": 120000},
            {"key": "g:4", "label": "Newsletter hebdo", "type": "automated_recurring", "total_sends": 500000},
        ]
        print(json.dumps(analyze(camps, vertical="retail"), indent=2, ensure_ascii=False))
        return
    path, opts = _parse_args(sys.argv[1:])
    data = json.load(open(path, encoding="utf-8"))
    camps = data.get("campaigns", data) if isinstance(data, dict) else data
    bodies = data.get("bodies") if isinstance(data, dict) else None
    reach = int(opts["reachable"]) if opts.get("reachable") else None
    print(json.dumps(analyze(camps, vertical=opts.get("vertical"), bodies=bodies,
                             reachable=reach), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
