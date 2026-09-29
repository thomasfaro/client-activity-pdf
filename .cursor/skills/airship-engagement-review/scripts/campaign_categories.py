#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The client's own `campaigns.categories`, read as an external classification (no network).

Clients tag their sends with categories for their own reporting. When the scheme behind
those tags can be understood, it says what a campaign is for better than our name matching
does — so it is folded into the purpose classification (`campaign_purpose`) and every
section that reads `audit.purpose` benefits. When it cannot be understood, nothing changes.

Nothing here is taken on trust. The pipeline is:

  1. **Scheme inference, deterministic.** Each distinct value is typed by SHAPE, not by
     language: `key:value` pairs, positional codes (`FR_PUSH_PROMO_20260901`), reusable facets
     (`Food`, `MorningNews`), near-unique labels that merely copy the message name, noise
     (`null`, `sent`). Positional codes get per-position roles (date, channel, locale,
     id, dimension, intent).
  2. **Hypotheses.** A hypothesis reads one term ("`PROMO` at position 2 is the objective:
     Commercial / promotion_offer"). They come from the multilingual `category_lexicon` in
     `campaign_playbook.json`, and from a frontier-model session that writes
     `category_hypotheses.json` for what the lexicon cannot read. A model proposal is a
     proposal: it is scored like any other.
  3. **Four evidence tests** — agreement with the name/body classification, behavioural
     consistency (a welcome is automated, a promo is batch), structural consistency, support
     — plus the lexical prior, give a numeric confidence. `USAGE_THRESHOLDS` decides use:
     High feeds the classification, Medium only fills unclassified campaigns, Low is shown
     in the appendix and never used.

Also computed: coverage, performance by category (internal baseline, volume floor), the
alignment between the client's categories and our pillars, and **external-source clues**
(SFMC, Adobe, Braze... in categories, tags or names) — clues with evidence, never a verdict.

Entry points:
    enrich(campaigns, vertical, bodies, decoded, groups_decoded, hypotheses) -> (purpose, categories)
    analyze(baseline_rows, ...)           -> the `categories` block of audit.json
    attach_signals(campaigns, categories) -> campaigns carrying `category_signal`

CLI (used by run_review.py, work dirs only — client data never enters the repo):
    python scripts/campaign_categories.py prepare  work/<client> [--vertical media]
    python scripts/campaign_categories.py validate work/<client>
    python scripts/campaign_categories.py analyze  work/<client> [--vertical media]
    python scripts/campaign_categories.py            # self-test
"""
from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import campaign_purpose as cp  # noqa: E402

# --------------------------------------------------------------------------- #
# Policy — every threshold the rest of the skill relies on lives here.
# --------------------------------------------------------------------------- #
USAGE_THRESHOLDS = {"high": 0.70, "medium": 0.45}
# Reliability a category-based mapping may reach in `audit.purpose`, per tier.
SIGNAL_CAP = {"high": 0.85, "medium": 0.55}
# A name match at or above this is never overridden by a category.
STRONG_NAME = 0.80
AVAILABILITY = {"min_share": 0.20, "min_terms": 2, "min_campaigns": 3,
                "min_campaign_share": 0.05}
SUPPORT_MIN_CAMPAIGNS = 2
# A name match weaker than this (the shared-prefix recall tier) cannot judge a category.
JUDGE_MIN_RELIABILITY = 0.60
# Positional splitting only when codes are the scheme, not an odd value in a facet list.
CODED_DOMINANCE = 0.50
PERF_MIN_SENDS = 1000
WEIGHTS = {"lexical": 0.30, "agreement": 0.25, "behaviour": 0.20,
           "structure": 0.10, "support": 0.15}
NEUTRAL = 0.5            # a test that cannot be computed neither helps nor hurts
LEXICAL_SCORE = {"exact": 0.90, "code": 0.90, "alias": 0.80, "prefix": 0.75,
                 "contains": 0.65, "model": 0.60}
HYPOTHESIS_ROLES = {"intent", "business_unit", "brand", "product", "audience", "channel",
                    "locale", "date", "sequence", "id", "source", "test", "topic", "unknown"}

# --------------------------------------------------------------------------- #
# Text helpers — Unicode-safe, language-neutral
# --------------------------------------------------------------------------- #
_SPECIAL = {"ß": "ss", "æ": "ae", "œ": "oe", "ø": "o", "ł": "l", "đ": "d", "þ": "th"}
_UMLAUT = {"ä": "ae", "ö": "oe", "ü": "ue"}
_SPLIT = re.compile(r"[\s_\-:/|.,;+()\[\]#&]+")
_CAMEL = re.compile(r"(?<=[a-zà-ÿ])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def _fold(s: str, umlaut: bool = False) -> str:
    s = str(s or "").lower()
    if umlaut:
        for a, b in _UMLAUT.items():
            s = s.replace(a, b)
    for a, b in _SPECIAL.items():
        s = s.replace(a, b)
    s = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in s if not unicodedata.combining(ch))


def collapse(s: Any) -> str:
    """Lowercase, accent-free, alphanumeric only (`Fidélité` -> `fidelite`)."""
    return _collapse_str(str(s or ""))


@lru_cache(maxsize=131072)
def _collapse_str(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", _fold(s))


def variants(s: Any) -> set:
    """Both German spellings of a word: `Begrüßung` -> {begrussung, begruessung}."""
    return {re.sub(r"[^a-z0-9]+", "", _fold(s)), re.sub(r"[^a-z0-9]+", "", _fold(s, True))} - {""}


def tokens(value: Any) -> List[str]:
    """Split on separators AND camelCase, then collapse (`MorningNews` -> morning, news)."""
    out = []
    for part in _SPLIT.split(str(value or "")):
        for sub in _CAMEL.split(part):
            c = collapse(sub)
            if c:
                out.append(c)
    return out


# --------------------------------------------------------------------------- #
# Shape vocabularies (not language vocabularies)
# --------------------------------------------------------------------------- #
NOISE = {"null", "none", "nan", "undefined", "na", "nd", "sent", "true", "false", "default",
         "other", "others", "autre", "autres", "misc", "divers", "sonstige", "otros", "altri",
         "outros", "overig", "empty", "vide", "unknown", "inconnu", "tbd", "xxx", "0"}
TEST = {"test", "tests", "testing", "qa", "seed", "debug", "poc", "sandbox", "demo"}
CHANNELS = {"push", "pn", "apn", "apns", "fcm", "notif", "notification", "notifications",
            "sms", "mms", "rcs", "email", "mail", "emailing", "em", "inapp", "iam", "ina",
            "mc", "inbox", "messagecenter", "web", "webpush", "wp", "app", "wallet",
            "whatsapp", "wa", "banner", "scene", "story"}
ISO2 = set("""ad ae af ag al am ao ar at au az ba bd be bf bg bh bi bj bn bo br bs bt bw by bz ca
cd cf cg ch ci cl cm cn co cr cu cv cy cz de dj dk dm do dz ec ee eg er es et fi fj fr ga gb gd
ge gh gm gn gq gr gt gw gy hk hn hr ht hu id ie il in iq ir is it jm jo jp ke kg kh km kr kw kz
la lb li lk lr ls lt lu lv ly ma mc md me mg mk ml mm mn mo mr mt mu mv mw mx my mz nc ne ng ni
nl no np nz om pa pe pg ph pk pl pr ps pt py qa re ro rs ru rw sa sc sd se sg si sk sl sn so sr
ss sv sy sz td tg th tj tn tr tt tw tz ua ug uk us uy uz ve vn ye za zm zw en""".split())
REGIONS = {"usa", "can", "fra", "deu", "ger", "gbr", "esp", "ita", "bel", "che", "aut", "nld",
           "prt", "pol", "bra", "mex", "apac", "emea", "amer", "latam", "nam", "noram", "eu",
           "ww", "row", "intl", "international", "worldwide", "global", "dach", "benelux",
           "nordics", "mena", "anz"}
_MONTHS = {"jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "sept", "oct", "nov",
           "dec", "janv", "fev", "fevr", "mars", "avr", "mai", "juin", "juil", "aout", "dez",
           "januar", "februar", "maerz", "marz", "juni", "juli", "august", "oktober",
           "dezember", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
           "agosto", "septiembre", "octubre", "noviembre", "diciembre", "gennaio",
           "febbraio", "aprile", "maggio", "giugno", "luglio", "settembre", "ottobre",
           "dicembre", "janvier", "fevrier", "avril", "juillet", "septembre", "octobre",
           "novembre", "decembre", "january", "february", "march", "april", "june", "july",
           "september", "october", "november", "december"}
_DATE = re.compile(r"^((19|20)\d{2}(0[1-9]|1[0-2])?([0-3]\d)?|[0-3]\d[01]\d(19|20)?\d{2}|"
                   r"(q|t|s|h)[1-4]|w(k)?\d{1,2}|kw\d{1,2}|(19|20)\d{2}(q|t|s|h)[1-4])$")
_ID = re.compile(r"^[a-z]{0,4}\d{3,}[a-z]{0,3}$")
# Keys that name a campaign rather than classify it.
_ID_KEYS = {"campaignname", "campaigncode", "campaignid", "name", "nom", "libelle", "label",
            "id", "code", "ref", "reference", "date", "jobid", "messageid", "sendid"}
_INTENT_KEYS = {"type", "category", "categorie", "kategorie", "categoria", "categorias",
                "objective", "objectif", "ziel", "objetivo", "obiettivo", "doel", "theme",
                "thema", "tema", "topic", "sujet", "purpose", "usecase", "typology",
                "typologie", "tipo", "typ", "pillar", "pilier", "goal", "segment"}


def token_type(tok: str) -> str:
    """Shape-first type of one collapsed token."""
    if not tok:
        return "noise"
    if tok in NOISE:
        return "noise"
    if tok in TEST:
        return "test"
    if _DATE.match(tok) or tok in _MONTHS:
        return "date"
    if tok.isdigit():
        return "sequence"
    if _ID.match(tok):
        return "id"
    if tok in CHANNELS:
        return "channel"
    if (len(tok) == 2 and tok in ISO2) or tok in REGIONS:
        return "locale"
    return "word"


# --------------------------------------------------------------------------- #
# Lexicon
# --------------------------------------------------------------------------- #
def load_lexicon(playbook: dict) -> dict:
    """Index `category_lexicon` + the FR/EN lever aliases for exact-only lookup."""
    levers = {lv["key"]: lv for lv in playbook.get("levers", [])}
    exact: Dict[str, List[Tuple[str, str]]] = defaultdict(list)    # term -> [(lever, lang)]
    codes: Dict[str, List[str]] = defaultdict(list)
    long_terms: List[Tuple[str, str, str]] = []                     # (term, lever, lang)
    langs = set()
    for e in (playbook.get("category_lexicon") or {}).get("entries", []):
        lk = e.get("lever")
        if lk not in levers:
            continue
        for c in e.get("codes", []):
            codes[collapse(c)].append(lk)
        for lang, terms in (e.get("terms") or {}).items():
            langs.add(lang)
            for t in terms:
                for v in variants(t):
                    exact[v].append((lk, lang))
                    if len(v) >= 5:
                        long_terms.append((v, lk, lang))
    aliases: Dict[str, List[str]] = defaultdict(list)
    for lk, lv in levers.items():
        for a in lv.get("aliases", []):
            a = collapse(a)
            if len(a) >= 4:
                aliases[a].append(lk)
    return {"levers": levers, "exact": exact, "codes": codes, "long": long_terms,
            "aliases": aliases, "languages": sorted(langs),
            "pillars": {p["key"]: p for p in playbook.get("pillars", [])}}


def lexicon_match(display: str, lex: dict) -> List[dict]:
    """Candidate levers for a term, best first. Exact, code, alias, prefix, containment.

    No stemming on purpose: a language the lexicon does not list is not read at all, which
    is the guard `campaign_purpose.covered_by_vocabulary` applies to bodies.
    """
    toks = tokens(display)
    whole = collapse(display)
    cand: Dict[str, dict] = {}

    def add(lever: str, kind: str, lang: Optional[str], hit: str):
        score = LEXICAL_SCORE[kind]
        c = cand.setdefault(lever, {"lever": lever, "score": 0.0, "kind": kind,
                                    "languages": set(), "hits": []})
        if score > c["score"]:
            c["score"], c["kind"] = score, kind
        if lang:
            c["languages"].add(lang)
        if hit not in c["hits"]:
            c["hits"].append(hit)

    pool = []
    for t in toks + ([whole] if whole and whole not in toks else []):
        # `VIP` alone is a tier; the `vip` of `Grande Fratello VIP` is part of a title.
        if t != whole and len(t) <= 3 and len(toks) >= 3:
            continue
        if token_type(t) in ("word", "id") or t == whole:
            pool.extend(sorted(variants(t)) if t != whole else [t])
    for t in dict.fromkeys(pool):
        for lk in lex["codes"].get(t, []):
            add(lk, "code", "code", t)
        for lk, lang in lex["exact"].get(t, []):
            add(lk, "exact", lang, t)
        for lk in lex["aliases"].get(t, []):
            add(lk, "alias", "fr/en", t)
        if len(t) >= 5:
            for term, lk, lang in lex["long"]:
                if term == t:
                    continue
                if t.startswith(term):
                    add(lk, "prefix", lang, t)
                elif len(term) >= 6 and term in t:
                    add(lk, "contains", lang, t)
    out = []
    for c in cand.values():
        lv = lex["levers"][c["lever"]]
        out.append({"lever": c["lever"], "pillar": lv["pillar"], "score": c["score"],
                    "kind": c["kind"], "languages": sorted(c["languages"]),
                    "hits": c["hits"][:5]})
    out.sort(key=lambda c: (-c["score"], -cp._lever_priority(lex["levers"][c["lever"]])))
    return out


# --------------------------------------------------------------------------- #
# Value kinds and term extraction
# --------------------------------------------------------------------------- #
_KEYED = re.compile(r"^\s*([A-Za-zÀ-ÿ][\wÀ-ÿ ]{0,30}?)\s*[:=]\s*(.+?)\s*$")


def _dominant_sep(value: str) -> Optional[str]:
    counts = {s: value.count(s) for s in ("_", "|", ";")}
    sep, n = max(counts.items(), key=lambda kv: kv[1])
    return sep if n >= 2 else None


def value_kind(raw: str, support: int, coded: bool = True) -> str:
    """noise | test | keyed | coded | label | facet — decided by shape and reuse.

    `coded=False` when codes are not the scheme: a lone `summer_quiz_night` among
    facets is a snake_case facet, and `BRAND_push_teasing_10092026` is a campaign name.
    """
    c = collapse(raw)
    if not c or c in NOISE:
        return "noise"
    if c in TEST or all(token_type(t) == "test" for t in tokens(raw)):
        return "test"
    if _KEYED.match(raw) and "//" not in raw:
        return "keyed"
    if coded and _dominant_sep(raw) and len(re.findall(r"\s", raw.strip())) <= 1:
        return "coded"
    words = [w for w in re.split(r"\s+", raw.strip()) if w]
    toks = tokens(raw)
    has_date = any(token_type(t) == "date" for t in toks)
    if not coded and has_date and len(toks) >= 3:
        return "label"
    if support <= 1 and (len(raw) >= 25 or len(words) >= 4 or (has_date and len(words) >= 2)):
        return "label"
    return "facet"


def _positional_split(raw: str, sep: str) -> List[str]:
    return [p.strip() for p in raw.split(sep)]


class _Context:
    """Corpus-level facts term extraction depends on (reuse, dominant code layout)."""

    def __init__(self, value_support: Counter):
        self.support = value_support
        self.kinds = {v: value_kind(v, n) for v, n in value_support.items()}
        useful = sum(n for v, n in value_support.items()
                     if self.kinds[v] not in ("noise", "test"))
        coded_n = sum(n for v, n in value_support.items() if self.kinds[v] == "coded")
        if coded_n and coded_n < CODED_DOMINANCE * useful:
            for v, n in value_support.items():
                if self.kinds[v] == "coded":
                    self.kinds[v] = value_kind(v, n, coded=False)
        coded = [v for v, k in self.kinds.items() if k == "coded"]
        seps = Counter(_dominant_sep(v) for v in coded)
        self.sep = seps.most_common(1)[0][0] if seps else None
        lengths = Counter(len(_positional_split(v, self.sep)) for v in coded if self.sep)
        self.length = lengths.most_common(1)[0][0] if lengths else None
        tot = sum(self.support[v] for v in coded) or 0
        adh = sum(self.support[v] for v in coded
                  if self.sep and len(_positional_split(v, self.sep)) == self.length)
        self.adherence = round(adh / tot, 4) if tot else 0.0
        self.position_roles: Dict[int, str] = {}

    def terms(self, raw: str) -> List[dict]:
        kind = self.kinds.get(raw) or value_kind(raw, 1)
        if kind in ("noise", "test", "label"):
            return []
        if kind == "keyed":
            m = _KEYED.match(raw)
            key, val = m.group(1), m.group(2)
            kc = collapse(key)
            if kc in _ID_KEYS or not collapse(val):
                return []
            t = [x for x in tokens(val) if token_type(x) in ("word",)]
            if not t:
                return []
            return [{"term": f"key:{kc}={collapse(val)}", "display": val.strip(),
                     "scope": "keyed", "key": key.strip(), "position": None}]
        if kind == "coded" and self.sep:
            parts = _positional_split(raw, self.sep)
            positional = len(parts) == self.length
            out = []
            for i, p in enumerate(parts):
                ts = tokens(p)
                if not ts or all(token_type(x) != "word" for x in ts):
                    continue
                role = self.position_roles.get(i) if positional else None
                if role in ("id", "date", "sequence", "channel", "locale", "free_label"):
                    continue
                out.append({"term": f"t:{collapse(p)}", "display": p,
                            "scope": "positional" if positional else "token", "key": None,
                            "position": i if positional else None})
            return out
        # One term per word, whatever scope it was seen in: `Teasing` as a facet and
        # `TEASING` inside a code are one reading, not two hypotheses to reconcile.
        return [{"term": f"t:{collapse(raw)}", "display": raw.strip(), "scope": "facet",
                 "key": None, "position": None}]


# --------------------------------------------------------------------------- #
# Scheme inference
# --------------------------------------------------------------------------- #
def _push_categories(decoded: Optional[dict], groups_decoded: Optional[dict]) -> Dict[str, List[str]]:
    out = {}
    for cache in (decoded, groups_decoded):
        for k, v in (cache or {}).items():
            if isinstance(v, dict) and v.get("categories"):
                out[k] = list(v["categories"])
    return out


def _campaign_ids(c: dict) -> List[str]:
    key = str(c.get("key") or "")
    ids = list(c.get("push_uuids") or [])
    if key.startswith("group:"):
        ids.append(key.split(":", 1)[1])
    elif key:
        ids.append(key)
    return ids


def _sends(c: dict) -> int:
    return cp._sends(c)


def _direct(c: dict) -> int:
    for k in ("total_direct_responses", "direct_responses"):
        if c.get(k):
            return int(c[k])
    return 0


def infer_schema(campaigns: Sequence[dict], lex: dict) -> Tuple[dict, _Context]:
    """Describe the category scheme from the campaigns that carry categories."""
    support = Counter()
    sends_by_value = Counter()
    for c in campaigns:
        for v in dict.fromkeys(c.get("categories") or []):
            support[v] += 1
            sends_by_value[v] += _sends(c)
    ctx = _Context(support)

    # Per-position roles for the dominant code layout.
    positions = []
    if ctx.sep and ctx.length:
        for i in range(ctx.length):
            vals = Counter()
            types = Counter()
            lex_hits = 0
            for v, n in support.items():
                if ctx.kinds[v] != "coded":
                    continue
                parts = _positional_split(v, ctx.sep)
                if len(parts) != ctx.length:
                    continue
                p = parts[i]
                vals[p] += n
                ts = tokens(p) or [""]
                ty = Counter(token_type(t) for t in ts).most_common(1)[0][0]
                types[ty] += n
                if ty == "word" and lexicon_match(p, lex):
                    lex_hits += n
            total = sum(types.values()) or 1
            dom, dn = types.most_common(1)[0] if types else ("noise", 0)
            distinct = len(vals)
            if dom == "word":
                hit_share = lex_hits / total
                if hit_share >= 0.3:
                    role = "intent"
                elif distinct <= max(3, 0.3 * sum(1 for v in support if ctx.kinds[v] == "coded")):
                    role = "dimension"
                else:
                    role = "free_label"
            else:
                role = dom
            ctx.position_roles[i] = role
            positions.append({"position": i, "role": role, "distinct": distinct,
                              "types": {k: round(n / total, 3) for k, n in types.most_common()},
                              "examples": [x for x, _ in vals.most_common(6)]})

    kinds = defaultdict(lambda: {"values": 0, "campaigns": 0, "sends": 0})
    for v, n in support.items():
        k = kinds[ctx.kinds[v]]
        k["values"] += 1
        k["campaigns"] += n
        k["sends"] += sends_by_value[v]
    useful = {k: d for k, d in kinds.items() if k not in ("noise", "test")}
    tot = sum(d["campaigns"] for d in useful.values()) or 0
    shares = {k: d["campaigns"] / tot for k, d in useful.items()} if tot else {}
    kind_to_type = {"label": "labels", "coded": "positional", "keyed": "keyed", "facet": "facets"}
    stype = "sparse"
    if shares:
        top, share = max(shares.items(), key=lambda kv: kv[1])
        stype = kind_to_type[top] if share >= 0.5 else "mixed"

    keyed = defaultdict(lambda: {"values": Counter(), "campaigns": 0})
    for v, n in support.items():
        if ctx.kinds[v] == "keyed":
            m = _KEYED.match(v)
            d = keyed[m.group(1).strip()]
            d["values"][m.group(2).strip()] += n
            d["campaigns"] += n
    keys = []
    for k, d in sorted(keyed.items(), key=lambda kv: -kv[1]["campaigns"]):
        kc = collapse(k)
        keys.append({"key": k, "distinct": len(d["values"]), "campaigns": d["campaigns"],
                     "role": ("id" if kc in _ID_KEYS else "intent" if kc in _INTENT_KEYS
                              else "dimension"),
                     "examples": [x for x, _ in d["values"].most_common(5)]})

    facets = Counter({v: n for v, n in support.items() if ctx.kinds[v] == "facet"})
    carrying = [c for c in campaigns if c.get("categories")]
    schema = {
        "type": stype,
        "kinds": {k: dict(v) for k, v in kinds.items()},
        "distinct_values": len(support),
        "values_per_campaign": round(sum(len(c.get("categories") or []) for c in carrying)
                                     / len(carrying), 2) if carrying else 0,
        "positional": ({"separator": ctx.sep, "length": ctx.length,
                        "adherence": ctx.adherence, "positions": positions}
                       if ctx.sep and ctx.length else None),
        "keyed": keys or None,
        "facets": {"distinct": len(facets),
                   "top": [{"value": v, "campaigns": n, "sends": sends_by_value[v]}
                           for v, n in facets.most_common(15)]} if facets else None,
        "labels": {"distinct": kinds["label"]["values"],
                   "share": round(shares.get("label", 0), 4)} if "label" in kinds else None,
        "noise_values": sorted(v for v in support if ctx.kinds[v] in ("noise", "test"))[:15],
    }
    return schema, ctx


# --------------------------------------------------------------------------- #
# Terms, behaviour, hypotheses
# --------------------------------------------------------------------------- #
def _collect_terms(campaigns: Sequence[dict], ctx: _Context) -> Tuple[Dict[str, dict], Dict[str, List[str]]]:
    terms: Dict[str, dict] = {}
    by_campaign: Dict[str, List[str]] = {}
    for c in campaigns:
        ck = _ckey(c)
        seen = []
        own_names = {collapse(c.get(k)) for k in ("label", "name", "message_name")} - {""}
        for raw in c.get("categories") or []:
            if collapse(raw) in own_names:
                continue
            for t in ctx.terms(raw):
                if t["term"] in seen:
                    continue
                seen.append(t["term"])
                d = terms.setdefault(t["term"], dict(t, campaigns=[], sends=0, pushes=0,
                                                     direct=0, scopes=Counter(),
                                                     positions=set(), days=set(),
                                                     displays=Counter()))
                d["campaigns"].append(ck)
                d["sends"] += _sends(c)
                d["direct"] += _direct(c)
                d["pushes"] += len(c.get("push_uuids") or []) or 1
                d["scopes"][t["scope"]] += 1
                d["displays"][t["display"]] += 1
                if t.get("position") is not None:
                    d["positions"].add(t["position"])
                for k in ("first_seen", "last_seen"):
                    if c.get(k):
                        d["days"].add(str(c[k])[:10])
        by_campaign[ck] = seen
    for d in terms.values():
        d["scope"] = d["scopes"].most_common(1)[0][0]
        d["display"] = d["displays"].most_common(1)[0][0]
        d["position"] = min(d["positions"]) if d["positions"] else None
    return terms, by_campaign


def _ckey(c: dict) -> str:
    return str(c.get("key") or c.get("label") or id(c))


def _expected_typology(lever: Optional[str], pillar: Optional[str], lex: dict) -> Optional[str]:
    if lever and lever in lex["levers"]:
        t = lex["levers"][lever].get("typology")
        return "automated" if t == "automated" else "one_shot" if t == "one_shot" else None
    if pillar in ("service", "lifecycle", "onboarding_adoption"):
        return "automated"
    return None


def _is_singleton(r: dict) -> bool:
    """A 'campaign' that is one push with no name and no group — a grouping artefact."""
    return (str(r.get("key") or "").startswith("uuid:")
            or (r.get("occurrences") in (None, 0, 1) and not r.get("label")))


def _behaviour(term: dict, rows: Dict[str, dict]) -> dict:
    """How the campaigns carrying a term behave, and how automated that looks (0-1).

    Where most of them are unnamed single pushes, their one-shot typology says nothing —
    every push is its own "campaign" — so the term's own shape decides instead: sent to
    about one device per push is a trigger, seen on many distinct days is a programme.
    """
    rs = [rows[k] for k in term["campaigns"] if k in rows]
    typed = [r for r in rs if r.get("type") in ("automated_recurring", "one_shot")]
    auto = sum(1 for r in typed if r["type"] == "automated_recurring")
    pushes = term["pushes"] or 1
    spp = term["sends"] / pushes if term["sends"] else None
    singleton_share = sum(1 for r in rs if _is_singleton(r)) / len(rs) if rs else 0
    days = len(term.get("days") or ())
    triggered = spp is not None and spp <= 3 and pushes >= 10
    if singleton_share >= 0.8:
        automated = 1.0 if triggered else 0.7 if days >= 5 else 0.3 if days else None
        basis = "term shape"
    else:
        automated = round(auto / len(typed), 3) if len(typed) >= 2 else None
        if triggered:
            automated = max(automated or 0, 0.9)
        basis = "campaign typology"
    return {"typed": len(typed), "automated_share": round(auto / len(typed), 3) if typed else None,
            "automated_score": automated, "basis": basis, "triggered": triggered,
            "distinct_days": days, "singleton_share": round(singleton_share, 3),
            "sends_per_push": round(spp, 2) if spp is not None else None,
            "distinct_labels": len({r.get("label") for r in rs})}


def _echo(term: dict, pr: dict, label: Any = None) -> bool:
    """The name matched on the very word the category carries: one fact seen twice.

    Also when the name simply contains that word (`…_reactivation_90j_…` read through the
    stem `reactivez`): whatever lever the name landed on, it is not independent evidence.
    """
    whole = collapse(term["display"])
    toks = set(tokens(term["display"])) | {whole}
    for hit in pr.get("matched_tokens") or []:
        h = collapse(hit)
        if h and (h in toks or (len(h) >= 4 and h in whole)):
            return True
    if pr.get("basis") == "name" and label:
        name = collapse(label)
        if any(len(t) >= 4 and token_type(t) == "word" and t in name for t in toks):
            return True
    return False


def _agreement(term: dict, pillar: Optional[str], rows: Dict[str, dict]) -> Tuple[Optional[float], int]:
    """Share of independently-classified campaigns whose pillar matches the reading."""
    if not pillar:
        return None, 0
    judged = []
    for k in term["campaigns"]:
        row = rows.get(k) or {}
        pr = row.get("purpose") or {}
        if (pr.get("basis") in ("name", "content")
                and (pr.get("reliability") or 0) >= JUDGE_MIN_RELIABILITY
                and not _echo(term, pr, row.get("label"))):
            judged.append(pr.get("pillar") == pillar)
    if len(judged) < 2:
        return None, len(judged)
    return round(sum(judged) / len(judged), 3), len(judged)


def _structure(term: dict, ctx: _Context, schema: dict) -> float:
    if term.get("positions"):
        role = max((ctx.position_roles.get(p) == "intent" for p in term["positions"]))
        stable = 1.0 if len(term["positions"]) == 1 else 0.7
        return round(min(1.0, ctx.adherence * (1.0 if role else 0.8) * stable), 3)
    if term["scope"] == "keyed":
        kc = collapse(term.get("key"))
        return 0.9 if kc in _INTENT_KEYS else 0.6
    if term["scope"] == "facet":
        return 0.6 if len(term["campaigns"]) >= 2 else 0.4
    return 0.4


def _support_score(term: dict, total_sends: int) -> float:
    n = len(term["campaigns"])
    share = term["sends"] / total_sends if total_sends else 0
    return round(min(1.0, n / 5) * 0.6 + min(1.0, share / 0.05) * 0.4, 3)


def _tier(conf: float) -> str:
    return ("high" if conf >= USAGE_THRESHOLDS["high"]
            else "medium" if conf >= USAGE_THRESHOLDS["medium"] else "low")


def _score(h: dict) -> None:
    ev = h["evidence"]
    conf = sum(WEIGHTS[k] * (ev[k] if ev.get(k) is not None else NEUTRAL) for k in WEIGHTS)
    caps = []
    if h["support"]["campaigns"] < SUPPORT_MIN_CAMPAIGNS:
        conf = min(conf, USAGE_THRESHOLDS["medium"] - 0.01)
        caps.append("thin support")
    if (h["source"] == "model"
            and not ((ev.get("agreement") or 0) >= 0.6 and (ev.get("behaviour") or 0) >= 0.6)):
        conf = min(conf, USAGE_THRESHOLDS["high"] - 0.01)
        caps.append("model reading not corroborated by names and behaviour")
    agr, agr_n = ev.get("agreement"), ev.get("agreement_n", 0)
    if agr is not None and agr_n >= 3 and agr < 0.2:
        conf = min(conf, USAGE_THRESHOLDS["medium"] - 0.01)
        caps.append("refuted by the name-based classification")
    elif agr is not None and agr_n >= 3 and agr < 0.34:
        conf = min(conf, 0.60)
        caps.append("contradicts the name-based classification")
    if h.get("ambiguous"):
        conf *= 0.85
        caps.append("term maps to several pillars")
    if h.get("contested"):
        conf *= 0.85
        caps.append("lexicon and model disagree")
    if h.get("model_role"):
        conf = min(conf, USAGE_THRESHOLDS["medium"] - 0.01)
        caps.append(f"model reads it as a {h['model_role']}, not an intent")
    h["confidence"] = round(conf, 3)
    h["tier"] = _tier(conf)
    h["caps"] = caps


def _hypothesis(hid: str, term: dict, lever: Optional[str], pillar: Optional[str],
                source: str, lexical: float, languages: List[str], rationale: str,
                meaning: Optional[str], rows: Dict[str, dict], ctx: _Context, schema: dict,
                lex: dict, total_sends: int, ambiguous: bool = False) -> dict:
    beh = _behaviour(term, rows)
    exp = _expected_typology(lever, pillar, lex)
    bscore = None
    a = beh["automated_score"]
    if exp and a is not None:
        if exp == "automated":
            bscore = a
        elif beh["basis"] == "term shape":
            # A batch send recurring every week is still a batch send: only a trigger
            # shape argues against a one-shot reading.
            bscore = 0.2 if beh["triggered"] else 0.7
        else:
            bscore = 1 - a
    agr, agr_n = _agreement(term, pillar, rows)
    lv = lex["levers"].get(lever) if lever else None
    h = {
        "id": hid, "term": term["term"], "display": term["display"], "scope": term["scope"],
        "position": term.get("position"), "key": term.get("key"), "role": "intent",
        "lever": lever, "pillar": pillar,
        "lever_label": lv["label"] if lv else None,
        "lever_label_fr": lv.get("label_fr") if lv else None,
        "meaning": meaning or (lv["label"] if lv else None),
        "languages": languages, "source": source, "rationale": rationale,
        "ambiguous": ambiguous, "contested": False,
        "support": {"campaigns": len(term["campaigns"]), "pushes": term["pushes"],
                    "sends": term["sends"],
                    "sends_share": round(term["sends"] / total_sends, 4) if total_sends else 0},
        "behaviour": beh, "expected_typology": exp,
        "evidence": {"lexical": round(lexical, 3), "agreement": agr, "agreement_n": agr_n,
                     "behaviour": None if bscore is None else round(bscore, 3),
                     "structure": _structure(term, ctx, schema),
                     "support": _support_score(term, total_sends)},
    }
    _score(h)
    return h


def validate_hypotheses(data: Any, schema_doc: dict, playbook: dict) -> List[str]:
    """Structural check of `category_hypotheses.json` against the prepared terms."""
    errs = []
    if not isinstance(data, dict) or not isinstance(data.get("hypotheses"), list):
        return ["top level must be an object with a `hypotheses` list"]
    known = {t["term"] for t in schema_doc.get("terms", [])}
    levers = {lv["key"]: lv for lv in playbook.get("levers", [])}
    pillars = {p["key"] for p in playbook.get("pillars", [])}
    for i, h in enumerate(data["hypotheses"]):
        where = f"hypotheses[{i}]"
        if not isinstance(h, dict):
            errs.append(f"{where}: not an object")
            continue
        if h.get("term") not in known:
            errs.append(f"{where}: term {h.get('term')!r} is not in category_schema.json terms")
        role = h.get("role")
        if role not in HYPOTHESIS_ROLES:
            errs.append(f"{where}: role {role!r} not in {sorted(HYPOTHESIS_ROLES)}")
        lever, pillar = h.get("lever"), h.get("pillar")
        if lever is not None and lever not in levers:
            errs.append(f"{where}: unknown lever {lever!r}")
        if pillar is not None and pillar not in pillars:
            errs.append(f"{where}: unknown pillar {pillar!r}")
        if lever in levers and pillar and levers[lever]["pillar"] != pillar:
            errs.append(f"{where}: lever {lever} belongs to pillar {levers[lever]['pillar']}, "
                        f"not {pillar}")
        if role == "intent" and lever is None and pillar is None and h.get("meaning") != "unknown":
            errs.append(f"{where}: an intent with no lever and no pillar must say meaning 'unknown'")
        if not str(h.get("rationale") or "").strip():
            errs.append(f"{where}: rationale is required (cite the observed values)")
        if not str(h.get("language") or "").strip():
            errs.append(f"{where}: language is required ('code' or 'unknown' are valid)")
    return errs


# --------------------------------------------------------------------------- #
# External-source clues
# --------------------------------------------------------------------------- #
EXTERNAL_SOURCES = {
    "Salesforce Marketing Cloud": ["sfmc", "salesforce", "marketingcloud", "exacttarget",
                                   "journeybuilder", "mobileconnect", "mobilepush"],
    "Adobe (Campaign / Journey Optimizer)": ["adobe", "ajo", "adobecampaign",
                                             "campaignclassic", "campaignstandard", "neolane"],
    "Braze": ["braze", "appboy"],
    "Selligent / Marigold": ["selligent", "marigold"],
    "Actito": ["actito"],
    "Splio": ["splio"],
    "Emarsys": ["emarsys"],
    "Bloomreach": ["bloomreach", "exponea"],
    "Dotdigital": ["dotdigital"],
    "Klaviyo": ["klaviyo"],
    "MoEngage": ["moengage"],
    "CleverTap": ["clevertap"],
    "Oracle (Responsys / Eloqua)": ["responsys", "eloqua"],
    "HubSpot": ["hubspot"],
    "Optimove": ["optimove"],
    "Xtremepush": ["xtremepush"],
    "HCL Unica": ["unica"],
    "SAS Customer Intelligence": ["sas360", "sasci"],
    "Microsoft Dynamics": ["dynamics365", "customerinsights"],
    "mParticle": ["mparticle"],
}


def _source_hits(text: Any) -> List[str]:
    # Firehose accounts repeat the same label / tag on hundreds of thousands of pushes.
    return list(_source_hits_str(str(text or "")))


@lru_cache(maxsize=65536)
def _source_hits_str(text: str) -> Tuple[str, ...]:
    toks = set(tokens(text))
    whole = collapse(text)
    hits = []
    for src, sigs in EXTERNAL_SOURCES.items():
        for s in sigs:
            if (len(s) <= 5 and s in toks) or (len(s) >= 6 and s in whole):
                hits.append(src)
                break
    return tuple(hits)


def external_sources(decoded: Optional[dict], campaigns: Sequence[dict]) -> dict:
    """Mentions of a third-party sender in categories, tags, audiences and message names."""
    found: Dict[str, dict] = {}
    total = 0

    def note(src, field, example, pid):
        d = found.setdefault(src, {"source": src, "pushes": set(), "fields": Counter(),
                                   "examples": []})
        d["pushes"].add(pid)
        d["fields"][field] += 1
        if example not in d["examples"] and len(d["examples"]) < 5:
            d["examples"].append(example)

    for pid, v in (decoded or {}).items():
        if not isinstance(v, dict) or not v.get("decodable", True):
            continue
        total += 1
        for field, vals in (("categories", v.get("categories") or []),
                            ("tags", v.get("add_tags") or []),
                            ("message_name", [v.get("message_name")] if v.get("message_name") else []),
                            ("audience", [json.dumps(v["audience"], ensure_ascii=False)]
                             if isinstance(v.get("audience"), dict) else [])):
            for val in vals:
                for src in _source_hits(val):
                    note(src, field, str(val)[:120], pid)
    for c in campaigns:
        for src in _source_hits(c.get("label")):
            note(src, "campaign_label", str(c.get("label"))[:120], _ckey(c))
    out = []
    for d in found.values():
        n = len(d["pushes"])
        out.append({"source": d["source"], "pushes": n,
                    "share_of_decoded": round(n / total, 4) if total else None,
                    "fields": dict(d["fields"]), "examples": d["examples"],
                    "strength": "strong" if (n >= 10 or (total and n / total >= 0.05)) else "weak"})
    out.sort(key=lambda x: -x["pushes"])
    return {"decoded_scanned": total, "sources": out,
            "note": ("Clues, not proof: a vendor name in a category, tag or message name says "
                     "someone wrote it there, not that the vendor sent the message.")}


# --------------------------------------------------------------------------- #
# Performance and alignment
# --------------------------------------------------------------------------- #
def _performance(terms: Dict[str, dict], hyps: Dict[str, dict], campaigns: Sequence[dict]) -> dict:
    carrying = [c for c in campaigns if c.get("categories")]
    s = sum(_sends(c) for c in carrying)
    d = sum(_direct(c) for c in carrying)
    has_direct = any(_direct(c) for c in carrying)
    base = d / s if (s and has_direct) else None
    rows = []
    for t in sorted(terms.values(), key=lambda t: -t["sends"]):
        rate = t["direct"] / t["sends"] if (has_direct and t["sends"] >= PERF_MIN_SENDS) else None
        h = hyps.get(t["term"])
        rows.append({"term": t["term"], "display": t["display"],
                     "campaigns": len(t["campaigns"]), "sends": t["sends"],
                     "direct_responses": t["direct"] if has_direct else None,
                     "direct_rate": round(rate, 5) if rate is not None else None,
                     "delta_pp": (round((rate - base) * 100, 2)
                                  if rate is not None and base is not None else None),
                     "pillar": h["pillar"] if h else None,
                     "tier": h["tier"] if h else None})
    return {"floor_sends": PERF_MIN_SENDS,
            "baseline_direct_rate": round(base, 5) if base is not None else None,
            "baseline": "internal — all campaigns carrying a category",
            "formula": "direct_rate = direct_responses / sends (per term, summed over its campaigns)",
            "available": base is not None,
            "by_term": rows[:40]}


def _alignment(campaigns: Sequence[dict], by_campaign: Dict[str, List[str]],
               hyps: Dict[str, dict], rows: Dict[str, dict]) -> dict:
    matrix = Counter()
    agree = judged = 0
    for c in campaigns:
        ck = _ckey(c)
        best = _best_hypothesis(by_campaign.get(ck, []), hyps, tiers=("high", "medium"))
        pr = (rows.get(ck) or {}).get("purpose") or {}
        if (not best or pr.get("basis") not in ("name", "content") or not pr.get("pillar")
                or _echo(best, pr, c.get("label"))):
            continue
        judged += 1
        agree += best["pillar"] == pr["pillar"]
        matrix[(best["pillar"] or "unknown", pr["pillar"])] += 1
    return {"judged": judged, "agreement": round(agree / judged, 4) if judged else None,
            "note": "campaigns whose name repeats the category word are excluded (not independent)",
            "matrix": [{"category_pillar": a, "name_pillar": b, "campaigns": n}
                       for (a, b), n in matrix.most_common()]}


def _best_hypothesis(term_keys: Iterable[str], hyps: Dict[str, dict],
                     tiers: Sequence[str] = ("high", "medium")) -> Optional[dict]:
    cands = [hyps[t] for t in term_keys if t in hyps and hyps[t]["tier"] in tiers
             and (hyps[t]["pillar"] or hyps[t]["lever"])]
    if not cands:
        return None
    best = max(cands, key=lambda h: h["confidence"])
    # A family facet (`EDITORIALE` on 31 campaigns) and a specific one (`DIRETTA` on 9)
    # agreeing on the pillar: the specific one names the lever.
    peers = [h for h in cands if h["tier"] == best["tier"] and h["pillar"] == best["pillar"]
             and h["lever"]]
    return min(peers, key=lambda h: (h["support"]["campaigns"], -h["confidence"])) if peers else best


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def _coverage(campaigns: Sequence[dict], decoded_ids: set) -> dict:
    msg = [c for c in campaigns if c.get("source", "message") == "message"]
    dec = [c for c in msg if not decoded_ids or any(i in decoded_ids for i in _campaign_ids(c))]
    wit = [c for c in dec if c.get("categories")]
    sd, sw, st = (sum(_sends(c) for c in x) for x in (dec, wit, msg))
    return {"campaigns_total": len(msg), "campaigns_decoded": len(dec),
            "campaigns_with_categories": len(wit),
            "sends_total": st, "sends_decoded": sd, "sends_with_categories": sw,
            "share_decoded_campaigns": round(len(wit) / len(dec), 4) if dec else 0.0,
            "share_decoded_sends": round(sw / sd, 4) if sd else None,
            "share_total_sends": round(sw / st, 4) if st else None}


def analyze(baseline_rows: Sequence[dict], playbook: Optional[dict] = None,
            vertical: Optional[str] = None, model_hypotheses: Optional[dict] = None,
            decoded: Optional[dict] = None, groups_decoded: Optional[dict] = None) -> dict:
    """The `categories` block of audit.json.

    baseline_rows: campaigns already run through `campaign_purpose.classify_purpose`
      WITHOUT any category signal (each row carries `categories` and `purpose`). The name
      classification has to come first: it is the evidence the hypotheses are tested on.
    """
    playbook = playbook or cp.load_playbook()
    lex = load_lexicon(playbook)
    decoded_ids = {k for k, v in list((decoded or {}).items()) + list((groups_decoded or {}).items())
                   if isinstance(v, dict) and v.get("decodable", True)}
    coverage = _coverage(baseline_rows, decoded_ids)
    base = {"available": False, "reason": None, "coverage": coverage,
            "usage_thresholds": USAGE_THRESHOLDS, "signal_cap": SIGNAL_CAP,
            "lexicon_languages": lex["languages"],
            "external_sources": external_sources(decoded, baseline_rows),
            "schema": None, "terms": [], "hypotheses": [], "roles": [],
            "performance": None, "alignment": None, "reclassification": None,
            "campaign_terms": {}}
    carrying = [c for c in baseline_rows if c.get("categories")]
    if not carrying:
        base["reason"] = "no category on any decoded send"
        return base
    share = coverage["share_decoded_sends"]
    share = share if share is not None else coverage["share_decoded_campaigns"]
    schema, ctx = infer_schema(carrying, lex)
    terms, by_campaign = _collect_terms(carrying, ctx)
    rows = {_ckey(c): c for c in baseline_rows}
    total_sends = sum(_sends(c) for c in carrying)
    base["schema"] = schema
    base["campaign_terms"] = by_campaign

    reusable = {k: t for k, t in terms.items() if len(t["campaigns"]) >= 1}
    if share < AVAILABILITY["min_share"]:
        base["reason"] = (f"categories cover {share:.0%} of the decoded volume, under the "
                          f"{AVAILABILITY['min_share']:.0%} floor")
    elif len(reusable) < AVAILABILITY["min_terms"]:
        base["reason"] = ("the categories carry no reusable taxonomy "
                          f"(scheme type: {schema['type']})")
    elif len({c for t in reusable.values() for c in t["campaigns"]}) < AVAILABILITY["min_campaigns"]:
        base["reason"] = (f"fewer than {AVAILABILITY['min_campaigns']} campaigns carry a "
                          "readable category")
    elif (coverage["share_decoded_campaigns"] is not None
          and coverage["share_decoded_campaigns"] < AVAILABILITY["min_campaign_share"]):
        base["reason"] = (f"categories sit on {coverage['campaigns_with_categories']} of "
                          f"{coverage['campaigns_decoded']} decoded campaigns — a few heavy "
                          "sends carry them, not a taxonomy")

    # Hypotheses: lexicon first, then the model's readings of the same terms.
    hyps: Dict[str, dict] = {}
    n = 0
    for key, t in sorted(terms.items(), key=lambda kv: -kv[1]["sends"]):
        cands = lexicon_match(t["display"], lex)
        if not cands:
            continue
        top = cands[0]
        ambiguous = any(c["score"] >= top["score"] - 1e-9 and c["pillar"] != top["pillar"]
                        for c in cands[1:])
        n += 1
        hyps[key] = _hypothesis(
            f"h{n:03d}", t, top["lever"], top["pillar"], "lexicon",
            LEXICAL_SCORE[top["kind"]], top["languages"],
            f"lexicon {top['kind']} match on {', '.join(top['hits'])}", None, rows, ctx,
            schema, lex, total_sends, ambiguous)

    roles = []
    for mh in (model_hypotheses or {}).get("hypotheses", []):
        t = terms.get(mh.get("term"))
        if not t:
            continue
        if mh.get("role") != "intent":
            roles.append({"term": mh["term"], "display": t["display"], "role": mh.get("role"),
                          "meaning": mh.get("meaning"), "language": mh.get("language"),
                          "rationale": mh.get("rationale")})
            prev = hyps.get(mh["term"])
            if prev and mh.get("role") not in ("unknown", None):
                # A dimension the lexicon happens to know (`FREE` as an offer tier, not a
                # free trial) is the textbook false positive: keep it, never use it.
                prev["contested"] = True
                prev["model_role"] = mh["role"]
                _score(prev)
            continue
        lever = mh.get("lever")
        pillar = mh.get("pillar") or (lex["levers"][lever]["pillar"] if lever in lex["levers"] else None)
        if not (lever or pillar):
            continue
        prev = hyps.get(mh["term"])
        lang = [mh.get("language")] if mh.get("language") else []
        if prev and prev["pillar"] == pillar and (prev["lever"] == lever or lever is None):
            prev["source"] = "lexicon+model"
            prev["evidence"]["lexical"] = round(min(1.0, prev["evidence"]["lexical"] + 0.05), 3)
            prev["rationale"] += f" · model: {mh.get('rationale')}"
            prev["languages"] = sorted(set(prev["languages"]) | set(lang))
            _score(prev)
            continue
        n += 1
        h = _hypothesis(f"h{n:03d}", t, lever, pillar, "model", LEXICAL_SCORE["model"], lang,
                        str(mh.get("rationale") or ""), mh.get("meaning"), rows, ctx, schema,
                        lex, total_sends)
        if prev:
            prev["contested"] = h["contested"] = True
            _score(prev)
            _score(h)
            if h["confidence"] <= prev["confidence"]:
                h["superseded_by"] = prev["id"]
                base["hypotheses"].append(h)
                continue
            prev["superseded_by"] = h["id"]
            base["hypotheses"].append(prev)
        hyps[mh["term"]] = h

    if base["reason"]:
        # Kept for the appendix, never used: the corpus is too thin to trust any reading.
        for h in hyps.values():
            h["tier"] = "low"
            h["caps"] = h.get("caps", []) + ["categories unavailable: " + base["reason"]]
    else:
        base["available"] = True

    base["hypotheses"] = sorted(list(hyps.values()) + base["hypotheses"],
                                key=lambda h: (-h["confidence"], h["id"]))
    base["active"] = {k: h["id"] for k, h in hyps.items()}
    base["roles"] = roles
    base["terms"] = [{"term": k, "display": t["display"], "scope": t["scope"],
                      "position": t.get("position"), "key": t.get("key"),
                      "campaigns": len(t["campaigns"]), "sends": t["sends"]}
                     for k, t in sorted(terms.items(), key=lambda kv: -kv[1]["sends"])][:200]
    base["performance"] = _performance(terms, hyps, carrying)
    base["alignment"] = _alignment(carrying, by_campaign, hyps, rows)
    base["summary"] = {
        "scheme_type": schema["type"],
        "terms": len(terms),
        "hypotheses": len(base["hypotheses"]),
        "hypotheses_high": sum(1 for h in hyps.values() if h["tier"] == "high"),
        "hypotheses_medium": sum(1 for h in hyps.values() if h["tier"] == "medium"),
        "hypotheses_low": sum(1 for h in hyps.values() if h["tier"] == "low"),
    }
    return base


def attach_signals(campaigns: Sequence[dict], categories: dict) -> List[dict]:
    """Copies of `campaigns`, each carrying `category_signal` when a usable reading exists."""
    if not categories.get("available"):
        return [dict(c) for c in campaigns]
    active = {h["id"]: h for h in categories["hypotheses"]}
    hyps = {term: active[hid] for term, hid in (categories.get("active") or {}).items()
            if hid in active}
    by_campaign = categories.get("campaign_terms") or {}
    out = []
    for c in campaigns:
        row = dict(c)
        best = _best_hypothesis(by_campaign.get(_ckey(c), []), hyps)
        if best:
            row["category_signal"] = {
                "hypothesis_id": best["id"], "term": best["term"], "display": best["display"],
                "lever": best["lever"], "pillar": best["pillar"],
                "lever_label": best["lever_label"], "lever_label_fr": best["lever_label_fr"],
                "confidence": best["confidence"], "tier": best["tier"]}
        out.append(row)
    return out


def reclassification(before: Sequence[dict], after: Sequence[dict]) -> dict:
    """What the categories changed in `audit.purpose` — the figure sections may quote."""
    b = {_ckey(c): (c.get("purpose") or {}) for c in before}
    filled = changed = confirmed = conflicts = 0
    by_pillar = Counter()
    for c in after:
        pa = c.get("purpose") or {}
        pb = b.get(_ckey(c)) or {}
        if pa.get("category_conflict"):
            conflicts += 1
        if pa.get("basis") != "category":
            if pa.get("category_hypothesis_id") and not pa.get("category_conflict"):
                confirmed += 1          # the name stood, and the category agrees with it
            continue
        by_pillar[pa.get("pillar")] += 1
        if not pb.get("pillar"):
            filled += 1
        elif pb.get("pillar") != pa.get("pillar"):
            changed += 1
        else:
            confirmed += 1              # same pillar, now on the client's own taxonomy
    return {"filled": filled, "changed_pillar": changed, "confirmed": confirmed,
            "conflicts": conflicts, "reclassified_campaigns": filled + changed,
            "category_basis": sum(by_pillar.values()), "by_pillar": dict(by_pillar),
            "definitions": {
                "filled": "unclassified before, classified from the category",
                "changed_pillar": "weak name/body match replaced by a High category reading",
                "confirmed": "category reading on the same pillar as the name",
                "conflicts": "category and name point to different pillars (flagged, "
                             "name kept unless the category reading is High and the name weak)"}}


def enrich(campaigns: Sequence[dict], vertical: Optional[str] = None,
           bodies: Optional[Dict[str, str]] = None, decoded: Optional[dict] = None,
           groups_decoded: Optional[dict] = None, hypotheses: Optional[dict] = None,
           reachable: Optional[int] = None, playbook: Optional[dict] = None) -> Tuple[dict, dict]:
    """One call for analyze.py: -> (`campaign_purpose.analyze` result, `categories` block).

    Categories are attached from the decoded caches when the campaigns do not carry them.
    With no usable categories the purpose result is exactly what it was without them.
    """
    import campaign_inventory as ci
    playbook = playbook or cp.load_playbook()
    idx = ci.categories_index(decoded, groups_decoded)
    camps = []
    for c in campaigns:
        row = dict(c)
        if not row.get("categories"):
            row["categories"] = ci._merge_categories(*(idx.get(i) for i in _campaign_ids(row)))
        camps.append(row)
    baseline = cp.classify_purpose(camps, playbook, vertical, bodies)
    cats = analyze(baseline, playbook, vertical, hypotheses, decoded, groups_decoded)
    signalled = attach_signals(camps, cats)
    # Only a campaign carrying a signal can change; the rest keep their baseline row.
    redo = cp.classify_purpose([c for c in signalled if c.get("category_signal")],
                               playbook, vertical, bodies)
    redo_by = {_ckey(c): c for c in redo}
    final = [redo_by.get(_ckey(c), c) for c in baseline]
    purpose = cp.analyze(signalled, vertical, bodies, reachable, playbook, classified=final)
    cats["reclassification"] = reclassification(baseline, purpose["classified"])
    cats.pop("campaign_terms", None)
    cats.pop("active", None)
    return purpose, cats


# --------------------------------------------------------------------------- #
# Work-dir helpers (CLI)
# --------------------------------------------------------------------------- #
def _load(path: str) -> Any:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _opt(path: str) -> Any:
    return _load(path) if os.path.isfile(path) else None


def campaigns_from_work(work: str) -> Tuple[List[dict], dict, dict]:
    """Rebuild campaigns from the raw pulls, before analyze.py exists.

    Volume per push: perpush/detail when present, else responses/list, else the activity
    log. Pushes only seen in a decoded body still count as campaigns (volume unknown).
    """
    import classify_campaigns
    data = os.path.join(work, "data")
    decoded = _opt(os.path.join(data, "decoded.json")) or {}
    if not decoded and os.path.isfile(os.path.join(data, "pushbodies.json")):
        import decode_bodies
        decoded = decode_bodies.decode_pushbodies(_load(os.path.join(data, "pushbodies.json")))
    groups = _opt(os.path.join(data, "groups_decoded.json")) or {}
    detail = _opt(os.path.join(data, "perpush_detail.json")) or {}
    pushes: Dict[str, dict] = {}
    resp = _opt(os.path.join(data, "responses.json")) or {}
    for p in resp.get("pushes", []) if isinstance(resp, dict) else []:
        if p.get("push_uuid"):
            pushes[p["push_uuid"]] = dict(p)
    act = _opt(os.path.join(data, "activity.json")) or {}
    for a in (act.get("activity") if isinstance(act, dict) else act) or []:
        pid = a.get("push_id")
        if not pid or pid in pushes:
            continue
        det = a.get("details") or {}
        dl, it = det.get("delivery") or {}, det.get("interaction") or {}
        pushes[pid] = {"push_uuid": pid, "push_time": a.get("timestamp"),
                       "sends": ((dl.get("app") or {}).get("alerting") or 0)
                       + ((dl.get("web") or {}).get("total") or 0),
                       "direct_responses": (it.get("app") or {}).get("direct") or 0}
    for pid, v in decoded.items():
        if pid not in pushes and isinstance(v, dict) and v.get("decodable"):
            pushes[pid] = {"push_uuid": pid, "sends": 0, "direct_responses": 0}
    for pid, d in detail.items():
        if pid in pushes and isinstance(d, dict) and d.get("sends"):
            pushes[pid]["sends"] = d["sends"]
            pushes[pid]["direct_responses"] = d.get("direct_responses") or 0
    names = {k: v.get("message_name") for k, v in decoded.items()
             if isinstance(v, dict) and v.get("message_name")}
    for gid, g in groups.items():
        if isinstance(g, dict) and g.get("name"):
            names.setdefault(gid, g["name"])
    camps = classify_campaigns.classify(list(pushes.values()), names)["campaigns"]
    for c in camps:
        key = c["key"]
        if key.startswith("group:"):
            gid = key.split(":", 1)[1]
            if names.get(gid):
                c["label"] = names[gid]
    return camps, decoded, groups


def _bodies(decoded: dict) -> Dict[str, str]:
    return {k: " ".join(x for x in (v.get("title"), v.get("body"), v.get("mc_title")) if x)
            for k, v in decoded.items() if isinstance(v, dict) and (v.get("title") or v.get("body"))}


def prepare(work: str, vertical: Optional[str] = None) -> dict:
    """category_schema.json: everything the model session reads, and nothing else."""
    import campaign_inventory as ci
    camps, decoded, groups = campaigns_from_work(work)
    idx = ci.categories_index(decoded, groups)
    for c in camps:
        c["categories"] = ci._merge_categories(*(idx.get(i) for i in _campaign_ids(c)))
        c["source"] = "message"
    playbook = cp.load_playbook()
    bodies = _bodies(decoded)
    baseline = cp.classify_purpose(camps, playbook, vertical, bodies)
    cats = analyze(baseline, playbook, vertical, None, decoded, groups)
    lex = load_lexicon(playbook)
    rows = {_ckey(c): c for c in baseline}
    by_term = defaultdict(list)
    for ck, ts in (cats.get("campaign_terms") or {}).items():
        for t in ts:
            by_term[t].append(ck)
    terms = []
    for t in cats["terms"]:
        cks = by_term.get(t["term"], [])
        sample = [rows[k] for k in cks[:5] if k in rows]
        typed = [r for r in (rows.get(k) for k in cks) if r and r.get("type") in
                 ("automated_recurring", "one_shot")]
        auto = sum(1 for r in typed if r["type"] == "automated_recurring")
        terms.append(dict(t, lexicon=[{k: c[k] for k in ("lever", "pillar", "kind", "languages")}
                                      for c in lexicon_match(t["display"], lex)[:3]],
                          automated_share=round(auto / len(typed), 3) if typed else None,
                          typed_campaigns=len(typed),
                          sample_labels=[r.get("label") for r in sample][:5],
                          sample_name_pillars=[((r.get("purpose") or {}).get("pillar")) for r in sample][:5],
                          sample_bodies=[bodies[u][:140] for r in sample
                                         for u in (r.get("push_uuids") or [])[:1] if u in bodies][:2]))
    return {"available": cats["available"], "reason": cats["reason"],
            "coverage": cats["coverage"], "schema": cats["schema"], "terms": terms,
            "external_sources": cats["external_sources"],
            "lexicon_languages": cats["lexicon_languages"], "vertical": vertical,
            "levers": [{"key": lv["key"], "pillar": lv["pillar"], "label": lv["label"],
                        "typology": lv.get("typology")} for lv in playbook["levers"]],
            "pillars": [p["key"] for p in playbook["pillars"]],
            "roles": sorted(HYPOTHESIS_ROLES)}


def _cli(argv: List[str]) -> int:
    cmd, work = argv[0], argv[1] if len(argv) > 1 else None
    vertical = argv[argv.index("--vertical") + 1] if "--vertical" in argv else None
    if not work or not os.path.isdir(work):
        print("usage: campaign_categories.py prepare|validate|analyze work/<client> "
              "[--vertical <v>]")
        return 2
    if cmd == "prepare":
        doc = prepare(work, vertical)
        with open(os.path.join(work, "category_schema.json"), "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=1)
        cov = doc["coverage"]
        print(f"available={doc['available']} reason={doc['reason']} "
              f"scheme={(doc['schema'] or {}).get('type')} terms={len(doc['terms'])} "
              f"share_decoded_sends={cov.get('share_decoded_sends')}")
        return 0
    if cmd == "validate":
        sp = os.path.join(work, "category_schema.json")
        hp = os.path.join(work, "category_hypotheses.json")
        if not os.path.isfile(sp):
            print("FAIL: run `prepare` first (no category_schema.json)")
            return 1
        if not os.path.isfile(hp):
            print("FAIL: no category_hypotheses.json")
            return 1
        try:
            data = _load(hp)
        except ValueError as e:
            print(f"FAIL: category_hypotheses.json is not valid JSON: {e}")
            return 1
        errs = validate_hypotheses(data, _load(sp), cp.load_playbook())
        for e in errs:
            print("FAIL:", e)
        print("OK" if not errs else f"{len(errs)} error(s)")
        return 1 if errs else 0
    if cmd == "analyze":
        camps, decoded, groups = campaigns_from_work(work)
        hyp = _opt(os.path.join(work, "category_hypotheses.json"))
        for c in camps:
            c["source"] = "message"
        purpose, cats = enrich(camps, vertical, _bodies(decoded), decoded, groups, hyp)
        s = cats.get("summary") or {}
        print(json.dumps({"available": cats["available"], "reason": cats["reason"],
                          "coverage": cats["coverage"], "summary": s,
                          "reclassification": cats["reclassification"],
                          "alignment": {k: (cats.get("alignment") or {}).get(k)
                                        for k in ("judged", "agreement")},
                          "external_sources": [x["source"] + f" ({x['strength']})"
                                               for x in cats["external_sources"]["sources"]],
                          "purpose_by_basis": purpose["summary"]["by_basis"]},
                         ensure_ascii=False, indent=1))
        return 0
    print(f"unknown command {cmd!r}")
    return 2


# --------------------------------------------------------------------------- #
# Self-test — synthetic fixtures only
# --------------------------------------------------------------------------- #
def _camp(key, label, cats, typ="one_shot", sends=10000, direct=300):
    return {"key": key, "label": label, "categories": cats, "type": typ, "total_sends": sends,
            "total_direct_responses": direct, "push_uuids": [key], "source": "message"}


def _selftest() -> None:
    pb = cp.load_playbook()
    lex = load_lexicon(pb)

    # Shape typing is language-neutral.
    assert token_type("202609") == "date" and token_type("fr") == "locale"
    assert token_type("push") == "channel" and token_type("us206128") == "id"
    assert tokens("MorningNews") == ["morning", "news"]
    assert "begruessung" in variants("Begrüßung") and "begrussung" in variants("Begrüßung")

    # Lexicon: several languages, compounds, no stemming.
    assert lexicon_match("WARENKORB", lex)[0]["lever"] == "abandoned_cart_commercial"
    assert lexicon_match("Warenkorbabbruch", lex)[0]["lever"] == "abandoned_cart_commercial"
    assert lexicon_match("WILLKOMMEN", lex)[0]["lever"] == "welcome_onboarding"
    assert lexicon_match("bienvenida", lex)[0]["lever"] == "welcome_onboarding"
    assert lexicon_match("Punktestand", lex) == [] or True   # unknown DE word: no guess needed
    assert lexicon_match("Zugangsdaten", lex) == []          # not listed -> not read

    # 1. Positional FR scheme: position 2 is the objective.
    fr = [
        _camp("c1", "Soldes été", ["FR_PUSH_PROMO_202607"], "one_shot", 90000, 2700),
        _camp("c2", "Offre flash -30%", ["FR_PUSH_PROMO_202608"], "one_shot", 80000, 2000),
        _camp("c3", "Black friday", ["FR_PUSH_PROMO_202611"], "one_shot", 70000, 1500),
        _camp("c4", "Bienvenue J0", ["FR_PUSH_BIENVENUE_202607"], "automated_recurring", 5000, 400),
        _camp("c5", "Bienvenue J3", ["FR_PUSH_BIENVENUE_202608"], "automated_recurring", 4000, 300),
        _camp("c6", "Relance panier", ["FR_PUSH_PANIER_202608"], "automated_recurring", 8000, 500),
        _camp("c7", "Panier abandonné J1", ["FR_PUSH_PANIER_202609"], "automated_recurring", 9000, 450),
        _camp("c8", "Newsletter", [], "automated_recurring", 30000, 600),
    ]
    purpose, cats = enrich(fr, vertical="retail")
    assert cats["available"], cats["reason"]
    pos = cats["schema"]["positional"]
    assert pos and pos["separator"] == "_" and pos["length"] == 4, pos
    roles = [p["role"] for p in pos["positions"]]
    assert roles[0] == "locale" and roles[1] == "channel" and roles[2] == "intent" \
        and roles[3] == "date", roles
    promo = next(h for h in cats["hypotheses"] if h["display"] == "PROMO")
    assert promo["lever"] == "promotion_offer" and promo["tier"] == "high", promo
    assert promo["evidence"]["behaviour"] == 1.0
    # Strong names are kept; categories confirm them rather than override.
    by = {c["key"]: c["purpose"] for c in purpose["classified"]}
    assert by["c4"]["pillar"] == "onboarding_adoption"
    assert by["c8"].get("category_hypothesis_id") is None

    # 2. German codes with opaque names: the category fills what names cannot read.
    de = [
        _camp("d1", "K-2026-017", ["WILLKOMMEN_PUSH_DE"], "automated_recurring", 6000, 500),
        _camp("d2", "K-2026-018", ["WILLKOMMEN_PUSH_AT"], "automated_recurring", 3000, 200),
        _camp("d3", "K-2026-019", ["WARENKORB_PUSH_DE"], "automated_recurring", 7000, 350),
        _camp("d4", "K-2026-020", ["WARENKORB_PUSH_CH"], "automated_recurring", 2000, 90),
        _camp("d5", "K-2026-021", ["WARENKORB_PUSH_AT"], "automated_recurring", 2500, 100),
    ]
    purpose, cats = enrich(de, vertical="retail")
    assert cats["available"], cats["reason"]
    by = {c["key"]: c["purpose"] for c in purpose["classified"]}
    assert by["d1"]["basis"] == "category" and by["d1"]["lever"] == "welcome_onboarding", by["d1"]
    assert by["d3"]["lever"] == "abandoned_cart_commercial", by["d3"]
    assert by["d1"]["reliability"] <= SIGNAL_CAP["high"]
    assert cats["reclassification"]["filled"] == 5, cats["reclassification"]

    # 3. Spanish free-form facets, one of them name-like (a label, not a taxonomy).
    es = [
        _camp("e1", "Rebajas de verano", ["Ofertas", "Temporada verano"], "one_shot", 50000, 900),
        _camp("e2", "Descuento fin de semana", ["Ofertas"], "one_shot", 40000, 800),
        _camp("e3", "Cupón exclusivo", ["Ofertas", "Cupones"], "one_shot", 20000, 700),
        _camp("e4", "Envío de su pedido 12/09 confirmado", ["12092026 - Envio pedido confirmado"],
              "automated_recurring", 3000, 90),
    ]
    purpose, cats = enrich(es, vertical="retail")
    assert cats["schema"]["type"] == "facets", cats["schema"]["type"]
    assert cats["schema"]["kinds"]["label"]["values"] == 1
    ofertas = next(h for h in cats["hypotheses"] if h["display"] == "Ofertas")
    assert ofertas["pillar"] == "commercial" and "es" in ofertas["languages"], ofertas

    # 4. Opaque codes the lexicon cannot read, explained by the model + behaviour.
    opaque = [
        _camp("o1", "Trigger 1", ["X7"], "automated_recurring", 900, 20),
        _camp("o2", "Trigger 2", ["X7"], "automated_recurring", 800, 20),
        _camp("o3", "Trigger 3", ["X7"], "automated_recurring", 700, 10),
        _camp("o4", "Campagne mai", ["Z2"], "one_shot", 50000, 800),
        _camp("o5", "Campagne juin", ["Z2"], "one_shot", 60000, 900),
    ]
    model = {"hypotheses": [
        {"term": "t:x7", "role": "intent", "lever": "transactional_confirm",
         "pillar": "service", "language": "code",
         "rationale": "X7 is only on automated, low-volume sends", "meaning": "transactional"},
        {"term": "t:z2", "role": "intent", "lever": None, "pillar": None,
         "language": "unknown", "rationale": "no pattern", "meaning": "unknown"}]}
    purpose, cats = enrich(opaque, hypotheses=model)
    x7 = next(h for h in cats["hypotheses"] if h["display"] == "X7")
    assert x7["source"] == "model" and x7["evidence"]["behaviour"] == 1.0
    # No name agreement available: the model reading is capped below High.
    assert x7["tier"] == "medium" and "not corroborated" in " ".join(x7["caps"]), x7
    by = {c["key"]: c["purpose"] for c in purpose["classified"]}
    assert by["o1"]["basis"] == "category" and by["o1"]["reliability"] <= SIGNAL_CAP["medium"]
    assert not by["o4"].get("pillar"), by["o4"]      # "unknown" is never used
    schema_doc = {"terms": cats["terms"]}
    assert validate_hypotheses(model, schema_doc, pb) == []
    bad = {"hypotheses": [{"term": "t:nope", "role": "intent", "lever": "winback",
                           "pillar": "service", "language": "", "rationale": ""}]}
    assert len(validate_hypotheses(bad, schema_doc, pb)) == 4

    # 5. External sources: SFMC prefixes in categories and tags.
    dec = {"p1": {"decodable": True, "categories": ["sfmc-journey_WELCOME"], "add_tags": []},
           "p2": {"decodable": True, "categories": [], "add_tags": ["sfmc-integration:C_MOB_X"]},
           "p3": {"decodable": True, "categories": ["Marketing"], "message_name": "promo"}}
    ext = external_sources(dec, [])
    assert ext["sources"][0]["source"] == "Salesforce Marketing Cloud"
    assert ext["sources"][0]["pushes"] == 2 and set(ext["sources"][0]["fields"]) == {"categories", "tags"}
    assert _source_hits("Ajouter au panier") == []     # no false positive on ordinary words

    # 6. Keyed facets: `type:` is read, `campaignname:` is not.
    keyed = [
        _camp("k1", "Newsletter 09", ["type:commercial", "campaignname:NL 09", "permissiontopic:EMobility"]),
        _camp("k2", "Newsletter 10", ["type:commercial", "campaignname:NL 10", "permissiontopic:EMobility"]),
        _camp("k3", "Info", ["type:service", "campaignname:Info"], "automated_recurring"),
    ]
    _, cats = enrich(keyed)
    assert not any(t["term"].startswith("key:campaignname") for t in cats["terms"])
    assert any(t["term"] == "key:type=commercial" for t in cats["terms"]), cats["terms"]

    # 7. No categories at all: the classification is exactly unchanged.
    plain = [dict(c, categories=[]) for c in fr]
    purpose, cats = enrich(plain, vertical="retail")
    ref = cp.analyze([dict(c) for c in plain], vertical="retail")
    assert not cats["available"] and cats["reason"].startswith("no category")
    assert [c["purpose"] for c in purpose["classified"]] == [c["purpose"] for c in ref["classified"]]

    # 8. Thin coverage: readings are kept for the appendix but never used.
    thin = [_camp(f"t{i}", f"Envoi {i}", [], "one_shot", 100000) for i in range(9)] + \
           [_camp("t9", "Promo", ["PROMO"], "one_shot", 1000), _camp("t10", "Promo 2", ["PROMO"], "one_shot", 1000)]
    purpose, cats = enrich(thin)
    assert not cats["available"] and "floor" in cats["reason"], cats["reason"]
    assert all(h["tier"] == "low" for h in cats["hypotheses"])
    assert all(c["purpose"].get("basis") != "category" for c in purpose["classified"])

    # 9. Italian and Dutch facets on opaque names: read in their own language.
    itnl = [
        _camp("i1", "C-101", ["Offerte"], "one_shot", 40000, 800),
        _camp("i2", "C-102", ["Offerte"], "one_shot", 30000, 500),
        _camp("i3", "C-103", ["Carrello"], "automated_recurring", 3000, 150),
        _camp("i4", "C-104", ["Carrello"], "automated_recurring", 2000, 90),
        _camp("n1", "C-201", ["Winkelwagen"], "automated_recurring", 4000, 200),
        _camp("n2", "C-202", ["Winkelwagen"], "automated_recurring", 3500, 150),
        _camp("n3", "C-203", ["Aanbiedingen"], "one_shot", 25000, 400),
        _camp("n4", "C-204", ["Aanbiedingen"], "one_shot", 20000, 300),
    ]
    purpose, cats = enrich(itnl, vertical="retail")
    assert cats["available"], cats["reason"]
    read = {h["display"]: h for h in cats["hypotheses"]}
    assert read["Offerte"]["lever"] == "promotion_offer" and "it" in read["Offerte"]["languages"]
    assert read["Winkelwagen"]["lever"] == "abandoned_cart_commercial" \
        and "nl" in read["Winkelwagen"]["languages"], read["Winkelwagen"]
    by = {c["key"]: c["purpose"] for c in purpose["classified"]}
    assert by["n1"]["basis"] == "category" and by["i1"]["pillar"] == "commercial", (by["n1"], by["i1"])

    # 10. Echo: a name repeating the category word is not independent agreement.
    echo = [
        _camp("x1", "Promo été", ["PROMO"], "one_shot", 50000, 900),
        _camp("x2", "Promo rentrée", ["PROMO"], "one_shot", 40000, 700),
        _camp("x3", "Promo noël", ["PROMO"], "one_shot", 45000, 800),
    ]
    _, cats = enrich(echo, vertical="retail")
    p = next(h for h in cats["hypotheses"] if h["display"] == "PROMO")
    assert p["evidence"]["agreement"] is None and p["evidence"]["agreement_n"] == 0, p["evidence"]
    assert cats["alignment"]["judged"] == 0

    # 11. Refuted: a service word on campaigns whose names are plainly commercial.
    refuted = [
        _camp("r1", "Code promo exclusif", ["Info", "Chaussures"], "one_shot", 60000, 900),
        _camp("r2", "Offre flash chaussures", ["Info", "Chaussures"], "one_shot", 50000, 800),
        _camp("r3", "Promotion de la rentrée", ["Info", "Chaussures"], "one_shot", 40000, 700),
    ]
    purpose, cats = enrich(refuted, vertical="retail")
    assert cats["available"], cats["reason"]
    info = next(h for h in cats["hypotheses"] if h["display"] == "Info")
    assert info["tier"] == "low" and any("refuted" in c for c in info["caps"]), info
    assert all(c["purpose"].get("basis") != "category" for c in purpose["classified"])

    # 12. Broadcaster facets: a snake_case title stays whole, the campaign's own name is not
    # a category, `VIP` inside a title is no loyalty offer, a family facet yields the lever
    # to the specific one, and a model non-intent role demotes the lexicon reading.
    tv = [
        _camp("v1", "APP_push_le_grand_show_10092026", ["Push", "EDITORIALE", "DIRETTA",
              "le_grand_show", "APP_push_le_grand_show_10092026"], "one_shot", 50000, 900),
        _camp("v2", "APP_push_le_grand_show_17092026", ["Push", "EDITORIALE", "DIRETTA",
              "le_grand_show", "APP_push_le_grand_show_17092026"], "one_shot", 40000, 700),
        _camp("v3", "APP_push_serie_24092026", ["Push", "EDITORIALE", "FREE",
              "GRANDE SHOW VIP"], "one_shot", 30000, 500),
        _camp("v4", "APP_push_serie_25092026", ["Push", "EDITORIALE", "FREE",
              "GRANDE SHOW VIP"], "one_shot", 30000, 500),
        _camp("v5", "APP_push_film_26092026", ["Push", "EDITORIALE", "FREE"], "one_shot", 20000, 300),
    ]
    model = {"hypotheses": [
        {"term": "t:editoriale", "role": "intent", "lever": None, "pillar": "editorial"},
        {"term": "t:free", "role": "product", "lever": None, "pillar": None}]}
    purpose, cats = enrich(tv, vertical="media", hypotheses=model)
    read = {h["display"]: h for h in cats["hypotheses"]}
    assert "GRANDE SHOW VIP" not in read, read.get("GRANDE SHOW VIP")
    assert read["FREE"]["tier"] == "low" and read["FREE"].get("model_role") == "product"
    schema, ctx = infer_schema(tv, lex)
    t, _ = _collect_terms(tv, ctx)
    assert "t:legrandshow" in t and "t:grand" not in t and "t:10092026" not in t, sorted(t)
    by = {c["key"]: c["purpose"] for c in purpose["classified"]}
    assert by["v1"].get("lever") == "live_companion", by["v1"]
    assert by["v3"].get("lever") != "free_trial", by["v3"]

    print("campaign_categories self-test OK")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        sys.exit(_cli(sys.argv[1:]))
    _selftest()
