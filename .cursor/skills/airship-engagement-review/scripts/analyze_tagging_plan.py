#!/usr/bin/env python3
"""Deterministic analysis of a normalized tagging-plan inventory.

Consumes the output of `parse_tagging_plan.py` plus the bundled
`data-collection-by-vertical.json`, and produces an analysis JSON:
  - verticalScores / suggestedVertical (data-driven signal to cross-check the brand)
  - event intent taxonomy (browse / consideration / conversion / loyalty / ...)
  - value-bearing detection (conversion events missing a value / amount / currency)
  - conversion goal opportunities (event -> suggested Airship goal channel)
  - gap analysis vs the vertical's recommended attributes + events

All figures are computed from the inventory; nothing is fabricated. The custom
event `value` param is a client-declared counter, NEVER a currency amount.

Usage:
    python scripts/analyze_tagging_plan.py inventory.json \
        [--vertical Media] [--reference data-collection-by-vertical.json] [-o analysis.json]
"""
import argparse
import json
import re
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REFERENCE = SKILL_ROOT / "data-collection-by-vertical.json"
AIRSHIP_PREFIX = "ua_"

# Event intent taxonomy: intent -> substrings matched against the event name.
INTENT_KEYWORDS = {
    "conversion": [
        "purchase", "order", "checkout", "payment", "pay", "buy", "transaction",
        "subscribe", "subscription", "renewal", "renew", "upgrade", "booking",
        "book", "reservation", "reserve", "deposit", "donate", "bet", "wager",
        "activation", "activate", "trial",
    ],
    "consideration": [
        "add_to_cart", "addtocart", "cart", "wishlist", "favorite", "favourite",
        "save", "compare", "quote", "basket", "add_to_bag",
    ],
    "browse": [
        "view", "browse", "search", "read", "watch", "play", "stream", "listen",
        "article", "video", "content", "product", "impression", "screen", "consume",
    ],
    "account": [
        "register", "registration", "signup", "sign_up", "login", "logout",
        "account", "profile", "onboard", "verify", "verification",
    ],
    "loyalty": [
        "loyalty", "points", "reward", "tier", "referral", "refer", "redeem",
        "coupon", "offer", "promo", "voucher",
    ],
    "engagement": [
        "follow", "share", "like", "comment", "rate", "review", "notification",
        "click", "feedback", "complete", "completed", "topic", "genre", "habit",
    ],
    "location": ["location", "geofence", "store_locator", "checkin", "check_in"],
    "lifecycle": ["cancel", "cancellation", "suspend", "expire", "expiration", "delete"],
}

# Names implying a measurable quantity / revenue / duration.
VALUE_BEARING_KEYWORDS = [
    "purchase", "order", "checkout", "payment", "buy", "transaction", "revenue",
    "sale", "spend", "deposit", "subscription", "renewal", "booking", "reservation",
    "watch", "read", "duration", "donate", "bet", "wager", "cart", "basket",
]
# Property names that count as a monetary / quantity value.
VALUE_PROPERTY_RE = re.compile(
    r"(value|amount|price|revenue|total|currency|cost|quantity|qty|duration|points|balance)",
    re.I,
)

# Suggested Airship goal channel per conversion-ish intent.
GOAL_HINTS = {
    "conversion": "Conversion goal on push / email / in-app (attribute revenue where available)",
    "consideration": "Retargeting / cart-abandon journey (push + in-app)",
    "browse": "Content re-engagement / recommendation (in-app, push)",
    "loyalty": "Loyalty nudges & tier progression (push, message center)",
    "account": "Onboarding / activation journey (push, in-app)",
    "lifecycle": "Win-back / retention journey (email, push)",
}

# Emitted alongside GOAL_HINTS as `suggestedGoalFr`: this string is printed verbatim
# in the report's recommendation table, so an English-only hint puts an English
# sentence in the middle of a French deliverable.
GOAL_HINTS_FR = {
    "conversion": "Goal de conversion sur push / email / in-app (attribution du revenu si disponible)",
    "consideration": "Parcours de retargeting / relance panier (push + in-app)",
    "browse": "Ré-engagement éditorial / recommandation (in-app, push)",
    "loyalty": "Incitations fidélité & progression de palier (push, message center)",
    "account": "Parcours d’onboarding / activation (push, in-app)",
    "lifecycle": "Parcours de reconquête / rétention (email, push)",
}

GENERIC_TOKENS = {
    "value", "id", "date", "type", "name", "user", "event", "completed", "started",
    "status", "updated", "count", "total", "the", "of", "on", "to", "a", "current",
    "new", "previous", "custom", "level", "code", "number", "time", "screen",
}


def _norm(s):
    return re.sub(r"[^a-z0-9]+", "", str(s or "").lower())


def _tokens(s):
    return [t for t in re.split(r"[^a-z0-9]+", str(s or "").lower()) if t and t not in GENERIC_TOKENS and len(t) > 2]


def _intent_of(name):
    n = str(name or "").lower()
    for intent, kws in INTENT_KEYWORDS.items():
        if any(kw in n for kw in kws):
            return intent
    return "other"


def _to_float(s):
    try:
        return float(str(s).replace(",", "."))
    except (TypeError, ValueError):
        return None


# Values that are pure on/off counters rather than measured amounts.
_COUNTER_VALUES = {0.0, 1.0}


def value_field_stats(event):
    """Analyze the event-level ``value`` histogram (``valueSamples``).

    Distinguishes a plain counter (value in {0,1}) from a repurposed monetary /
    quantity amount, and infers the unit from the value distribution. Currency is
    never transmitted by RTDS, but decimals vs integers strongly signal the unit:
    two-decimal amounts are major currency units (e.g. euros), not cents.
    """
    pairs = []
    for s in event.get("valueSamples") or []:
        x = _to_float(s.get("value"))
        if x is not None:
            pairs.append((x, s.get("count") or 0))
    if not pairs:
        return None
    amounts = [(x, c) for x, c in pairs if x not in _COUNTER_VALUES]
    if not amounts:
        return {"isCounter": True, "carriesAmount": False, "distinctAmounts": 0}
    vals = [x for x, _ in amounts]
    wn = sum(c for _, c in amounts)
    wmean = sum(x * c for x, c in amounts) / wn if wn else sum(vals) / len(vals)
    has_dec = any(abs(x - round(x)) > 1e-9 for x in vals)
    mn, mx = min(vals), max(vals)
    if has_dec:
        unit, uconf = "major_currency_unit", "High"
        note = ("Two-decimal amounts imply a major currency unit (e.g. euros), not "
                "cents — cents would appear as x100 integers.")
    elif mx <= 20:
        unit, uconf = "count_or_quantity", "Medium"
        note = "Small integers — likely a quantity/counter, not a monetary amount."
    else:
        unit, uconf = "integer_ambiguous", "Low"
        note = ("Integers with no decimals — could be whole currency units, minor "
                "units (cents), or a quantity; confirm with the brand.")
    return {
        "isCounter": False,
        "carriesAmount": True,
        "distinctAmounts": len(amounts),
        "occurrences": wn,
        "min": round(mn, 2),
        "max": round(mx, 2),
        "mean": round(wmean, 2),
        "hasDecimals": has_dec,
        "inferredUnit": unit,
        "unitConfidence": uconf,
        "note": note,
        "sampleAmounts": [x for x, _ in sorted(amounts, key=lambda t: -t[1])[:8]],
    }


def _value_property(event):
    """A dedicated value/amount/currency *property* (separate from the value field)."""
    for p in event.get("properties", []) or []:
        if VALUE_PROPERTY_RE.search(p.get("name", "")):
            return p.get("name")
    return None


# --------------------------------------------------------------------------- #
# Broader (bilingual EN/FR + synonym) matching for gap analysis.               #
# Each group is a set of equivalent tokens; sharing a group = a concept match. #
# --------------------------------------------------------------------------- #
ALIAS_GROUPS = [
    {"first", "firstname", "prenom", "given"},
    {"lastname", "surname", "nom", "name", "familyname"},
    {"birthdate", "birthday", "dob", "naissance", "ddn", "anniversaire", "birth"},
    {"zipcode", "zip", "postal", "postcode", "codepostal", "cp"},
    {"city", "ville", "town"},
    {"country", "pays", "nation"},
    {"gender", "genre", "sexe", "civility", "civilite"},
    {"email", "mail", "courriel"},
    {"phone", "telephone", "tel", "gsm", "msisdn", "mobilephone"},
    {"language", "langue", "lang", "locale"},
    {"tier", "palier", "niveau", "rank", "grade", "statut"},
    {"points", "point", "couronnes", "couronne", "crowns", "cagnotte", "solde"},
    {"coupon", "coupons", "voucher", "bon", "bons"},
    {"account", "compte", "inscription", "signup", "registration", "adhesion", "adherent"},
    {"created", "creation", "create", "cree", "creee", "opened", "firstopen"},
    {"login", "logged", "connexion", "connect", "signin", "authentication", "auth"},
    {"logout", "logoff", "deconnexion", "disconnect"},
    {"favorite", "favori", "favourite", "preferred", "prefere", "fav"},
    {"store", "magasin", "shop", "boutique", "enseigne", "outlet"},
    {"order", "commande", "achat", "purchase", "purchased", "checkout", "transaction", "passage", "buy"},
    {"cart", "panier", "basket", "bag"},
    {"add", "added", "ajout", "ajoute", "addto"},
    {"remove", "removed", "suppression", "supprime", "delete", "retrait"},
    {"payment", "paiement", "paye"},
    {"loyalty", "fidelite", "fid"},
    {"reward", "recompense", "gain"},
    {"redeem", "redeemed", "redemption", "utilise", "spent", "spend", "burn"},
    {"earn", "earned", "gagne", "credite", "accrual"},
    {"delivery", "livraison", "livre", "shipping", "expedition"},
    {"drive", "clickandcollect", "clickcollect", "cc", "retrait", "pickup"},
    {"catalog", "catalogue", "cata"},
    {"promo", "promotion", "promotions", "offre", "offer", "deal"},
    {"optin", "optout", "consent", "consentement", "notify", "subscription", "subscribe"},
    {"amount", "montant", "value", "revenue", "total", "price", "prix", "cost"},
    {"quantity", "qty", "nombre", "count", "number", "nb"},
    {"product", "produit", "article", "item", "sku", "ean"},
    {"category", "categorie", "rayon", "department", "aisle"},
]
TOKEN2GROUP = {}
for _i, _grp in enumerate(ALIAS_GROUPS):
    for _t in _grp:
        TOKEN2GROUP[_t] = _i

# Tokens too generic to match on their own (only matched via an alias group).
MATCH_STOP = {
    "app", "went", "go", "goes", "screen", "view", "viewed", "visit", "page", "date",
    "datetime", "time", "id", "ids", "code", "codes", "type", "types", "status", "num",
    "new", "current", "previous", "web", "mobile", "sdk", "api", "client", "user", "info",
    "data", "my", "the", "of", "to", "on", "in", "and", "for", "pass", "went", "last",
    "wlec", "meti", "one", "auto", "chosen", "num",
}


def _raw_tokens(s):
    return [t for t in re.split(r"[^a-z0-9]+", str(s or "").lower()) if len(t) >= 2]


def _concepts(*names):
    """Concept signature = alias-group ids + distinctive raw tokens (non-stop)."""
    out = set()
    for name in names:
        for t in _raw_tokens(name):
            gid = TOKEN2GROUP.get(t)
            if gid is not None:
                out.add(("g", gid))
            elif t not in MATCH_STOP:
                out.add(("t", t))
    return out


def _best_match(rec_concepts, candidates):
    """Pick the tracked item whose concepts overlap the recommendation the most.

    Returns (item, overlap_set) or (None, set()). Ties break toward the candidate
    with the fewest surplus concepts (most specific match).
    """
    best, best_key = None, None
    for item, cand_concepts in candidates:
        overlap = rec_concepts & cand_concepts
        if not overlap:
            continue
        key = (len(overlap), -len(cand_concepts - overlap))
        if best_key is None or key > best_key:
            best_key, best = key, (item, overlap)
    return best if best else (None, set())


# --------------------------------------------------------------------------- #
# Fine-grained analysis of custom-event properties and their sample values.    #
# --------------------------------------------------------------------------- #
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]|^\d{2}/\d{2}/\d{4}")
_BOOL_TOKENS = {"true", "false", "oui", "non", "yes", "no", "o", "n", "0", "1"}
_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{10,}$")

# --------------------------------------------------------------------------- #
# Redaction of personal sample values                                         #
# --------------------------------------------------------------------------- #
# A data-collection audit records real production values next to each property, and
# they are the reason samples are useful: "is this a locale code or free text" is a
# question only a value answers. But some of those values are people. One plan carried
# four hundred consumer email addresses under `attributes[].sampleValues`, and another
# carried dialled numbers as `tel:+…` event properties — and up to eight samples per
# property flow into `audit_tagging.json`, which the report builder reads.
#
# So the shape is kept and the person is not. Classification still runs on the raw
# values, because that is what makes it accurate; only what gets written out is
# masked, and the mask names the kind so the reader loses nothing they were using.
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[A-Za-z]{2,}$")
# `+` or a `tel:` scheme required: a bare digit run is indistinguishable from an
# order id or an amount, and over-masking would blind the analysis it feeds.
_PHONE_RE = re.compile(r"^(?:tel:)?\+\d[\d\s().-]{7,}\d$")
_REDACTED = {"email": "<email redacted>", "phone": "<phone redacted>"}
# Unanchored twins of the two patterns above, for PII embedded in a composite value.
# The phone form requires an explicit "+" country prefix so it cannot eat an order id,
# a price or a timestamp out of a structured string.
_EMAIL_IN_RE = re.compile(r"[^\s@,;|=]+@[^\s@,;|=]+\.[A-Za-z]{2,}")
_PHONE_IN_RE = re.compile(r"(?:tel:)?\+\d[\d\s().-]{7,}\d")


def redact_sample(value):
    """Mask one sample value that identifies a person. Returns it unchanged otherwise."""
    s = str(value).strip()
    if _EMAIL_RE.match(s):
        return _REDACTED["email"]
    if _PHONE_RE.match(s):
        return _REDACTED["phone"]
    # a delimited list of addresses: one plan stored them comma-joined in one cell
    parts = [p.strip() for p in re.split(r"[;,]\s*", s) if p.strip()]
    if len(parts) > 1 and sum(1 for p in parts if _EMAIL_RE.match(p)) >= len(parts) / 2:
        return f'{_REDACTED["email"]} x{len(parts)}'
    # An address or number EMBEDDED in a larger string. The checks above are anchored to
    # the whole value, so a composite sample like
    # "name=Store Rennes|contact=r.rennes@example.net|phone=+15550100123"
    # passed through untouched, carrying real contact data into the delivered appendix.
    # That is a privacy control failing silently, and it made correctness depend on every
    # downstream consumer remembering to re-scrub. Redact at source instead, keeping the
    # non-identifying structure so the sample still shows the shape of the field.
    scrubbed = _EMAIL_IN_RE.sub(_REDACTED["email"], s)
    scrubbed = _PHONE_IN_RE.sub(_REDACTED["phone"], scrubbed)
    return scrubbed if scrubbed != s else value


def redact_samples(values):
    """Mask personal values across a sample list, preserving order and length."""
    return [redact_sample(v) for v in values]


def classify_values(name, values):
    """Infer a property/value kind and surface the collected sample data."""
    vals = [str(v).strip() for v in values if v is not None and str(v).strip() != ""]
    if not vals:
        return {"kind": "empty", "distinctShown": 0, "samples": []}
    distinct = sorted(set(vals), key=lambda x: -vals.count(x))
    low = [v.lower() for v in vals]
    nums = [_to_float(v) for v in vals]
    numeric = all(n is not None for n in nums)
    is_json = all(v[:1] in "{[" for v in vals)
    casing_note = None
    if len({v.lower() for v in vals}) < len(set(vals)):
        casing_note = "inconsistent casing across values"

    if is_json:
        kind = "json"
    elif set(low) <= _BOOL_TOKENS and len(set(low)) <= 3:
        kind = "boolean"
    elif _DATE_RE.match(vals[0]) or str(name).lower().endswith("date"):
        kind = "date"
    elif numeric:
        real = [n for n in nums if n not in _COUNTER_VALUES]
        has_dec = any(abs(n - round(n)) > 1e-9 for n in nums)
        if real and (has_dec or max(nums) > 20):
            kind = "amount" if has_dec else "number"
        else:
            kind = "number"
    elif len(set(low)) <= 12 and max(len(v) for v in vals) <= 24:
        kind = "enum"
    elif sum(1 for v in vals if _ID_RE.match(v)) >= max(1, len(vals) // 2):
        kind = "identifier"
    else:
        kind = "text"

    info = {"kind": kind, "distinctShown": len(set(vals)),
            "samples": redact_samples(distinct[:8])}
    if casing_note:
        info["note"] = casing_note
    if kind in ("amount", "number") and numeric:
        real = [n for n in nums if n is not None]
        info["min"], info["max"] = round(min(real), 2), round(max(real), 2)
    return info


def analyze_event_properties(event):
    """Per-property kind + sample values for one custom event (skips date-only counters)."""
    out = []
    for p in event.get("properties", []) or []:
        samples = [s.get("value") for s in (p.get("samples") or [])]
        info = classify_values(p.get("name"), samples)
        out.append({"name": p.get("name"), **info})
    return out


# --------------------------------------------------------------------------- #
# Fine-grained analysis of JSON-typed attributes (parse keys & sub-values).    #
# --------------------------------------------------------------------------- #
def analyze_json_attribute(attr):
    """If an attribute's sample values are JSON, summarize its structure/fields."""
    samples = attr.get("sampleValues") or []
    parsed = []
    for v in samples:
        s = str(v).strip()
        if s[:1] not in "{[":
            continue
        try:
            parsed.append(json.loads(s))
        except (ValueError, TypeError):
            continue
    if not parsed:
        return None
    shape = "array" if isinstance(parsed[0], list) else "object" if isinstance(parsed[0], dict) else "scalar"
    fields = {}
    if shape == "object":
        for obj in parsed:
            if not isinstance(obj, dict):
                continue
            for k, val in obj.items():
                f = fields.setdefault(k, {"types": set(), "samples": []})
                f["types"].add(type(val).__name__)
                if len(f["samples"]) < 5 and val not in f["samples"]:
                    f["samples"].append(val if not isinstance(val, (dict, list)) else json.dumps(val)[:60])
    elif shape == "array":
        for arr in parsed:
            for el in (arr or [])[:20]:
                f = fields.setdefault("[]", {"types": set(), "samples": []})
                f["types"].add(type(el).__name__)
                if len(f["samples"]) < 8 and el not in f["samples"]:
                    f["samples"].append(el if not isinstance(el, (dict, list)) else json.dumps(el)[:60])
    return {
        "key": attr.get("key"),
        "shape": shape,
        "parsedSamples": len(parsed),
        "fields": [
            {"field": k, "types": sorted(v["types"]),
             "samples": redact_samples(v["samples"])}
            for k, v in fields.items()
        ],
    }


# --------------------------------------------------------------------------- #
# Data provenance: source (SDK app / web / API), storage granularity           #
# (named-user/contact vs channel/device), and real-time vs batch cadence.      #
# --------------------------------------------------------------------------- #
_MOBILE_PLATFORMS = {"iOS", "Android", "Amazon"}
# Channels a device SDK cannot hold a *device-level* attribute on; their presence
# means the attribute is stored on the CONTACT (named-user) and shared cross-channel.
_CONTACT_CHANNELS = {"Email", "SMS", "Open"}
_BATCH_NAME_RE = re.compile(r"(reception|date_recept|import|feed|batch|sync|_ba$|cible|segment|projet)", re.I)


def _attr_source(attr):
    """Coarse source of an attribute op: API (server-side) vs SDK (on-device)."""
    src = str(attr.get("sources") or "")
    scope = (attr.get("versionScope") or {}).get("sourceScope") or ""
    if "api" in src.lower() or scope == "api":
        return "API"
    if src or scope == "sdk":
        return "SDK"
    return "Unknown"


def _parse_actions(attr):
    sets = removes = 0
    for part in str(attr.get("actions") or "").split(","):
        seg = part.strip().lower()
        m = re.search(r"(set|remove)\s*:\s*([\d]+)", seg)
        if m:
            if m.group(1) == "set":
                sets = int(m.group(2))
            else:
                removes = int(m.group(2))
    return sets, removes


def analyze_provenance(inventory):
    events = inventory.get("customEvents", [])
    attrs = inventory.get("attributes", [])

    ev_src, ev_pf = {}, {}
    api_events = []
    for e in events:
        s = (e.get("source") or "Unknown")
        ev_src[s] = ev_src.get(s, 0) + 1
        for p in (e.get("platforms") or {}):
            ev_pf[p] = ev_pf.get(p, 0) + 1
        if s == "API" or "API" in (e.get("platforms") or {}):
            api_events.append(e.get("name"))

    at_src, at_pf = {}, {}
    api_attrs, multi_channel, contact_channel = [], 0, 0
    churn, reception = [], []
    for a in attrs:
        s = _attr_source(a)
        at_src[s] = at_src.get(s, 0) + 1
        plats = set((a.get("platforms") or {}).keys())
        for p in plats:
            at_pf[p] = at_pf.get(p, 0) + 1
        if s == "API":
            api_attrs.append(a.get("key"))
        # Duplication across app/web *device* channels only (device-level smell).
        if len(plats & (_MOBILE_PLATFORMS | {"Web"})) >= 2 and not (plats & _CONTACT_CHANNELS):
            multi_channel += 1
        # Spanning email/SMS/open channels => the attribute lives on the CONTACT
        # (named-user), because a device SDK can't hold an attribute on those channels.
        if plats & _CONTACT_CHANNELS:
            contact_channel += 1
        sets, removes = _parse_actions(a)
        if sets and removes and removes >= 0.25 * sets:
            churn.append(a.get("key"))
        if _BATCH_NAME_RE.search(a.get("key") or ""):
            reception.append(a.get("key"))

    # Storage-level verdict.
    total_attr = len(attrs) or 1
    dup_ratio = multi_channel / total_attr
    contact_ratio = contact_channel / total_attr
    named_user_signal = any(
        any(t in (p.get("name") or "").lower() for t in ("named_user", "nameduser", "contact", "customer_id", "user_fid", "user_id", "accountid"))
        for e in events for p in (e.get("properties") or [])
    )
    # Every prose finding below is emitted in both languages (`*` / `*Fr`): a French
    # report renders these strings verbatim, so an English-only analyzer would leave
    # English paragraphs in the middle of a translated section.
    if at_src.get("API", 0) > at_src.get("SDK", 0) or contact_ratio >= 0.5:
        level = "contact/named-user-level (attributes span the contact's app/email/SMS channels)"
        level_fr = ("niveau contact / named-user (les attributs couvrent les canaux "
                    "app/email/SMS du contact)")
    elif dup_ratio >= 0.5:
        level = "channel/device-level (SDK, duplicated across a user's device channels)"
        level_fr = ("niveau canal / appareil (SDK, dupliqué sur les canaux appareil "
                    "d’un même utilisateur)")
    else:
        level = "mixed"
        level_fr = "mixte"
    storage_signals = [
        f"{at_src.get('SDK', 0)}/{total_attr} attributes are SDK-sourced, {at_src.get('API', 0)} API/server-side.",
    ]
    storage_signals_fr = [
        f"{at_src.get('SDK', 0)}/{total_attr} attributs proviennent du SDK, "
        f"{at_src.get('API', 0)} de l’API/serveur.",
    ]
    if contact_channel:
        storage_signals.append(
            f"{contact_channel}/{total_attr} attributes ({round(100*contact_ratio)}%) also appear on the user's "
            "Email/SMS channels — i.e. they are stored on the CONTACT (named-user) and shared across all channels "
            "(contact-level, the recommended pattern).")
        storage_signals_fr.append(
            f"{contact_channel}/{total_attr} attributs ({round(100*contact_ratio)} %) apparaissent aussi sur "
            "les canaux Email/SMS de l’utilisateur : ils sont donc stockés sur le CONTACT (named-user) et "
            "partagés entre tous les canaux — c’est le schéma recommandé.")
    if multi_channel:
        storage_signals.append(
            f"{multi_channel}/{total_attr} attributes are duplicated across app/web device channels only "
            f"({round(100*dup_ratio)}%) — a device-level smell a contact store would remove.")
        storage_signals_fr.append(
            f"{multi_channel}/{total_attr} attributs sont dupliqués uniquement sur les canaux appareil "
            f"app/web ({round(100*dup_ratio)} %) — un stockage au niveau contact supprimerait cette duplication.")
    if named_user_signal:
        storage_signals.append("Named-user / contact identifiers are present on events (e.g. user_id / AccountId).")
        storage_signals_fr.append(
            "Des identifiants named-user / contact sont présents sur les événements "
            "(p. ex. user_id / AccountId).")

    # Cadence verdict.
    sdk_events = [e.get("name") for e in events if (e.get("source") or "") == "SDK"]
    batch_signals, batch_signals_fr = [], []
    if churn:
        batch_signals.append(f"{len(churn)} attributes show set+remove overwrite churn (bulk re-sync pattern).")
        batch_signals_fr.append(
            f"{len(churn)} attributs montrent un cycle set+remove d’écrasement "
            "(signature d’une re-synchronisation en masse).")
    if reception:
        batch_signals.append(f"{len(reception)} attributes look like dated CRM feeds (e.g. {', '.join(reception[:3])}).")
        batch_signals_fr.append(
            f"{len(reception)} attributs ressemblent à des flux CRM datés "
            f"(p. ex. {', '.join(reception[:3])}).")
    rt_signals = ([f"{len(sdk_events)} SDK custom events are emitted per user action (real-time)."]
                  if sdk_events else [])
    rt_signals_fr = ([f"{len(sdk_events)} événements custom SDK sont émis à chaque action "
                      "utilisateur (temps réel)."] if sdk_events else [])
    batchy = len(set(churn + reception)) >= 0.2 * total_attr and batch_signals
    if batchy:
        cadence_verdict = "Events: real-time (SDK/API). Attributes: largely batch-synced (CRM feeds / bulk overwrite)."
        cadence_verdict_fr = ("Événements : temps réel (SDK/API). Attributs : très largement synchronisés "
                              "par lots (flux CRM / écrasement en masse).")
    elif batch_signals:
        cadence_verdict = "Events: real-time (SDK/API). Attributes: mostly incremental, with a few bulk-synced fields."
        cadence_verdict_fr = ("Événements : temps réel (SDK/API). Attributs : essentiellement incrémentaux, "
                              "avec quelques champs synchronisés par lots.")
    else:
        cadence_verdict = "Events: real-time (SDK/API). Attribute cadence looks incremental/real-time from this capture."
        cadence_verdict_fr = ("Événements : temps réel (SDK/API). La cadence des attributs paraît "
                              "incrémentale / temps réel sur cette capture.")
    cadence = {
        "realTime": {"items": sdk_events, "signals": rt_signals, "signalsFr": rt_signals_fr},
        "batch": {"items": sorted(set(churn + reception))[:40],
                  "signals": batch_signals, "signalsFr": batch_signals_fr},
        "verdict": cadence_verdict, "verdictFr": cadence_verdict_fr,
    }

    return {
        "sourceSplit": {
            "events": ev_src, "eventsByPlatform": ev_pf,
            "attributes": at_src, "attributesByPlatform": at_pf,
        },
        "storageLevel": {"verdict": level, "verdictFr": level_fr,
                         "multiChannelAttributes": multi_channel,
                         "totalAttributes": len(attrs), "signals": storage_signals,
                         "signalsFr": storage_signals_fr},
        "apiCrossPlatform": {
            "events": api_events, "attributes": api_attrs,
            "note": ("API / server-side data is set at the contact (named-user) level and is therefore "
                     "cross-platform by nature — the most reusable, channel-agnostic data."),
            "noteFr": ("Les données API / serveur sont posées au niveau du contact (named-user) et sont donc "
                       "cross-canal par nature — la donnée la plus réutilisable, indépendante du canal."),
        },
        "cadence": cadence,
    }


def score_verticals(inventory, reference):
    verticals = reference.get("verticals", {})
    specific = {k: v for k, v in verticals.items() if _norm(k) not in ("allverticals", "eventcategories")}

    corpus = {}
    for key, v in specific.items():
        toks = set()
        for ev in v.get("events", []):
            toks.update(_tokens(ev.get("name")))
            for p in ev.get("properties", []):
                toks.update(_tokens(p.get("name")))
        for a in v.get("attributes", []):
            toks.update(_tokens(a.get("id")))
            toks.update(_tokens(a.get("name")))
        corpus[key] = toks

    # Document frequency across verticals (distinctive tokens weigh more).
    df = {}
    for toks in corpus.values():
        for t in toks:
            df[t] = df.get(t, 0) + 1

    tracked = set()
    for ev in inventory.get("customEvents", []):
        tracked.update(_tokens(ev.get("name")))
        for p in ev.get("properties", []):
            tracked.update(_tokens(p.get("name")))
    for a in inventory.get("attributes", []):
        tracked.update(_tokens(a.get("key")))

    scores = []
    for key, toks in corpus.items():
        matched = tracked & toks
        score = sum(1.0 / df[t] for t in matched)
        scores.append({
            "vertical": key,
            "score": round(score, 3),
            "matchedTokens": sorted(matched),
        })
    scores.sort(key=lambda s: s["score"], reverse=True)
    suggested = scores[0]["vertical"] if scores and scores[0]["score"] > 0 else "all verticals"
    return scores, suggested


def resolve_vertical(reference, requested):
    verticals = reference.get("verticals", {})
    if not requested:
        return None
    want = _norm(requested)
    for key in verticals:
        if _norm(key) == want:
            return key
    for key in verticals:  # loose contains match
        if want and (want in _norm(key) or _norm(key) in want):
            return key
    return None


def analyze_events(inventory):
    by_intent = {}
    value_bearing = []
    conversion_signals = []
    for ev in inventory.get("customEvents", []):
        intent = _intent_of(ev.get("name"))
        by_intent.setdefault(intent, []).append({
            "name": ev.get("name"),
            "source": ev.get("source"),
            "total": ev.get("total"),
        })
        implies_value = any(kw in str(ev.get("name", "")).lower() for kw in VALUE_BEARING_KEYWORDS)
        vstats = value_field_stats(ev)
        carries_amount = bool(vstats and vstats.get("carriesAmount"))
        value_prop = _value_property(ev)
        # A genuine value signal = an amount on the value field OR a dedicated
        # value/amount property. A bare `value=1` counter does NOT count.
        has_value = carries_amount or bool(value_prop)
        if implies_value or has_value:
            value_bearing.append({
                "name": ev.get("name"),
                "source": ev.get("source"),
                "total": ev.get("total"),
                "hasValue": has_value,
                "impliesValue": implies_value,
                "carriesAmount": carries_amount,
                "valueProperty": value_prop,
                "valueField": vstats,
                "missingValue": implies_value and not has_value,
                "properties": [p.get("name") for p in ev.get("properties", [])],
            })
        if intent in ("conversion", "consideration"):
            conversion_signals.append({
                "name": ev.get("name"),
                "intent": intent,
                "total": ev.get("total"),
                "hasValue": has_value,
                "carriesAmount": carries_amount,
                "valueField": vstats,
                "suggestedGoal": GOAL_HINTS.get(intent),
                "suggestedGoalFr": GOAL_HINTS_FR.get(intent),
            })
    return by_intent, value_bearing, conversion_signals


def analyze_gaps(inventory, reference, vertical_key):
    tracked_events = {_norm(ev.get("name")): ev for ev in inventory.get("customEvents", [])}
    tracked_attrs = {}
    for a in inventory.get("attributes", []):
        tracked_attrs[_norm(a.get("normalized") or a.get("key"))] = a
        tracked_attrs[_norm(a.get("key"))] = a

    attr_candidates = [(a, _concepts(a.get("key"), a.get("normalized")))
                       for a in inventory.get("attributes", [])]
    event_candidates = [(ev, _concepts(ev.get("name")))
                        for ev in inventory.get("customEvents", [])]
    value_gid = TOKEN2GROUP.get("amount")

    def match_attr(rec_id, rec_name):
        for cand in (_norm(rec_id), _norm(rec_name)):  # exact / substring first (high precision)
            if cand and cand in tracked_attrs:
                return tracked_attrs[cand], "exact"
        m, ov = _best_match(_concepts(rec_id, rec_name), attr_candidates)
        return (m, "concept") if m else (None, None)

    def match_event(rec_name):
        rn = _norm(rec_name)
        if rn in tracked_events:
            return tracked_events[rn], "exact"
        m, ov = _best_match(_concepts(rec_name), event_candidates)
        return (m, "concept") if m else (None, None)

    def event_prop_concepts(ev):
        cset = set()
        for p in ev.get("properties", []) or []:
            cset |= _concepts(p.get("name"))
        if (value_field_stats(ev) or {}).get("carriesAmount") or _value_property(ev):
            cset.add(("g", value_gid))
        return cset

    def missing_recommended_props(rec_props, ev):
        tracked = event_prop_concepts(ev)
        miss = []
        for rp in rec_props:
            rc = _concepts(rp)
            if rc and not (rc & tracked):  # generic-only names are treated as satisfied
                miss.append(rp)
        return miss

    verticals = reference.get("verticals", {})
    ref_keys = []
    for k in verticals:
        nk = _norm(k)
        if nk == "allverticals" or nk == _norm(vertical_key):
            ref_keys.append(k)

    attr_rows, event_rows = [], []
    seen_attr, seen_event = set(), set()
    for k in ref_keys:
        v = verticals[k]
        for a in v.get("attributes", []):
            sig = _norm(a.get("id"))
            if sig in seen_attr:
                continue
            seen_attr.add(sig)
            m, via = match_attr(a.get("id"), a.get("name"))
            attr_rows.append({
                "recommendedId": a.get("id"),
                "recommendedName": a.get("name"),
                "type": a.get("type"),
                "fromVertical": k,
                "status": "present" if m else "missing",
                "matchedKey": (m or {}).get("key"),
                "matchedVia": via,
            })
        for ev in v.get("events", []):
            sig = _norm(ev.get("name"))
            if sig in seen_event:
                continue
            seen_event.add(sig)
            m, via = match_event(ev.get("name"))
            rec_props = [p.get("name") for p in ev.get("properties", [])]
            missing_props = missing_recommended_props(rec_props, m) if m else []
            event_rows.append({
                "recommendedName": ev.get("name"),
                "category": ev.get("category"),
                "fromVertical": k,
                "recommendedProperties": rec_props,
                "status": ("present" if m and not missing_props else "partial" if m else "missing"),
                "matchedName": (m or {}).get("name"),
                "matchedVia": via,
                "missingProperties": missing_props,
            })

    def coverage(rows, present_states):
        total = len(rows)
        present = sum(1 for r in rows if r["status"] in present_states)
        return {"present": present, "total": total, "pct": round(100 * present / total, 1) if total else 0}

    return {
        "vertical": vertical_key,
        "referenceVerticals": ref_keys,
        "attributes": attr_rows,
        "events": event_rows,
        "attributeCoverage": coverage(attr_rows, ("present",)),
        "eventCoverage": coverage(event_rows, ("present", "partial")),
    }


def main(argv):
    ap = argparse.ArgumentParser(description="Analyze a normalized tagging-plan inventory.")
    ap.add_argument("inventory", help="Path to parse_tagging_plan.py output.")
    ap.add_argument("--vertical", help="Vertical to compare against (default: data-suggested).")
    ap.add_argument("--reference", default=str(DEFAULT_REFERENCE), help="data-collection-by-vertical.json path.")
    ap.add_argument("-o", "--output", help="Write analysis JSON here (default: stdout).")
    args = ap.parse_args(argv[1:])

    with open(args.inventory, encoding="utf-8") as fh:
        inventory = json.load(fh)
    with open(args.reference, encoding="utf-8") as fh:
        reference = json.load(fh)

    scores, suggested = score_verticals(inventory, reference)
    chosen = resolve_vertical(reference, args.vertical) or resolve_vertical(reference, suggested) or "all verticals"
    by_intent, value_bearing, conversion_signals = analyze_events(inventory)
    gaps = analyze_gaps(inventory, reference, chosen)

    # Events that repurpose the `value` field to carry a real amount (with unit inference).
    monetary_value = []
    for v in value_bearing:
        vf = v.get("valueField") or {}
        if vf.get("carriesAmount"):
            monetary_value.append({
                "name": v["name"], "source": v.get("source"), "total": v.get("total"),
                "min": vf["min"], "max": vf["max"], "mean": vf["mean"],
                "distinctAmounts": vf["distinctAmounts"], "occurrences": vf["occurrences"],
                "hasDecimals": vf["hasDecimals"], "inferredUnit": vf["inferredUnit"],
                "unitConfidence": vf["unitConfidence"], "note": vf["note"],
                "sampleAmounts": vf["sampleAmounts"],
            })

    caveats = ["Custom event `value` is a client-declared counter, not a currency amount."]
    if monetary_value:
        units = sorted({m["inferredUnit"] for m in monetary_value})
        caveats.append(
            f"Exception: {len(monetary_value)} event(s) repurpose the `value` field to carry an "
            f"amount ({', '.join(units)}). Currency is not transmitted; the unit is inferred from "
            "the value distribution (decimals => major currency unit, e.g. euros; integers are ambiguous)."
        )

    # Fine-grained property/value analysis per custom event — feeds the depth of the
    # conversion / value / goal / best-practice sections (properties + collected values).
    # EVERY tracked event is emitted, including those with no property and no `value`:
    # "this event carries nothing" is itself a finding (the event is a bare counter and
    # cannot qualify a conversion), and dropping those rows silently under-reports the
    # catalogue in the data appendix and in `monetary_summary().total_events`.
    event_properties = []
    for ev in inventory.get("customEvents", []):
        value_samples = ev.get("valueSamples") or []
        event_properties.append({
            "name": ev.get("name"),
            "source": ev.get("source"),
            "total": ev.get("total"),
            "intent": _intent_of(ev.get("name")),
            "valueField": value_field_stats(ev),
            # `value` is Airship's reserved per-event numeric field. Absent samples mean
            # the SDK never populated it, which is what blocks value-based attribution.
            "hasValueObject": bool(value_samples),
            "valueSamples": redact_samples(value_samples[:8]),
            "properties": analyze_event_properties(ev),
        })

    # JSON-typed attributes: parse and summarize the collected structure/fields.
    json_attributes = []
    for a in inventory.get("attributes", []):
        ja = analyze_json_attribute(a)
        if ja:
            json_attributes.append(ja)

    analysis = {
        "kind": "airship-tagging-plan-analysis",
        "profile": (inventory.get("meta") or {}).get("profile"),
        "verticalScores": scores,
        "suggestedVertical": suggested,
        "chosenVertical": chosen,
        "counts": {
            "customEvents": len(inventory.get("customEvents", [])),
            "attributes": len(inventory.get("attributes", [])),
            "tags": len(inventory.get("tags", [])),
            "subscriptionLists": len(inventory.get("subscriptionLists", [])),
            "screens": len(inventory.get("screens", [])),
            "excludedAirshipAttributes": len(inventory.get("excludedAirship", {}).get("attributes", [])),
            "excludedAirshipTags": len(inventory.get("excludedAirship", {}).get("tags", [])),
        },
        "eventsByIntent": by_intent,
        "valueBearing": value_bearing,
        "conversionSignals": conversion_signals,
        "monetaryValue": monetary_value,
        "eventProperties": event_properties,
        "jsonAttributes": json_attributes,
        "provenance": analyze_provenance(inventory),
        "gaps": gaps,
        "caveats": caveats,
    }

    out = json.dumps(analysis, indent=2, ensure_ascii=False)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(out)
    else:
        print(out)

    missing_val = sum(1 for v in value_bearing if v["missingValue"])
    print(
        f"[analyze] suggested={suggested} chosen={chosen} | conv_signals={len(conversion_signals)} "
        f"value_bearing={len(value_bearing)} (missing value={missing_val}) | "
        f"monetary_value_events={len(monetary_value)} | "
        f"attr_cov={gaps['attributeCoverage']['pct']}% event_cov={gaps['eventCoverage']['pct']}%",
        file=sys.stderr,
    )
    return 0


def _selftest() -> int:
    """Pin what redaction masks and, as importantly, what it leaves alone."""
    fails = []

    def check(cond, label):
        if not cond:
            fails.append(label)

    # The two shapes actually found in delivered tagging plans, written out with a
    # fictional address and a number from the range reserved for fiction. The first
    # draft of this test used a real consumer address and a real dialled number, copied
    # from the plan that motivated the feature -- which put two people's details in the
    # repository in the course of adding the code that keeps them out of the report.
    check(redact_sample("marie.dupont1978@example.net") == "<email redacted>",
          "a consumer email address is masked")
    check(redact_sample("tel:+15550100123") == "<phone redacted>",
          "a dialled number carried as a tel: URI is masked")
    check(redact_sample("+33 6 12 34 56 78") == "<phone redacted>",
          "a spaced international number is masked")
    check(redact_sample("a@b.com, c@d.com, e@f.com") == "<email redacted> x3",
          "a comma-joined address list is masked and counted")

    # Every address here is masked, brand-looking ones included: a `noreply@` prefix is
    # too weak to bet a consumer's address on, and nothing in a tagging plan's sample
    # values needs the exact address to be legible. The one brand sender the review does
    # print -- `email_broadcasts[].sender` in the push inventory -- comes from a
    # different path and is deliberately untouched.
    check(redact_sample("noreply@mailing.example.com") == "<email redacted>",
          "an address is masked without trying to guess whether it is a person")

    # PII embedded in a composite value, which the anchored checks above cannot see. This
    # shipped: a delivered plan carried the store contact as one packed `contact` string,
    # every check here passed, and the address still reached the appendix -- caught by a
    # section author adding their own second scrub. The field names must survive, or the
    # sample stops showing the reader the shape of the property.
    packed = redact_sample(
        "name=Store Rennes|contact=r.rennes@example.net|phone=+33 2 99 00 00 00")
    check(packed == "name=Store Rennes|contact=<email redacted>|phone=<phone redacted>",
          f"PII embedded in a composite value is masked in place, got {packed!r}")
    check(redact_sample("contact=+15550100123") == "contact=<phone redacted>",
          "a number embedded behind a field name is masked")

    # and the values samples exist for: masking these would blind the analysis
    for keep in ("fr-FR", "en-us", "true", "1250.40", "42", "2026-08-25",
                 "ORD-99231847", "checkout_complete",
                 '{"target":1,"functional":1}', "0612345678"):
        check(redact_sample(keep) == keep, f"a non-personal sample survives ({keep!r})")

    # the funnel: classification runs on raw values, output is masked
    info = classify_values("email", ["a@b.com", "c@d.com"])
    check(info["samples"] == ["<email redacted>", "<email redacted>"],
          f"classify_values masks what it emits, got {info['samples']}")
    check(info["distinctShown"] == 2,
          "the distinct count is still computed from the real values")
    amounts = classify_values("revenue", ["12.50", "99.00", "1250.40"])
    check(amounts["kind"] == "amount" and amounts["min"] == 12.5,
          f"a monetary property is unaffected, got {amounts}")

    for f in fails:
        print(f"  \u2717 {f}")
    print(f"tagging redaction selftest: {'FAIL' if fails else 'ok'} "
          f"({len(fails)} failure(s))")
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    raise SystemExit(main(sys.argv))
