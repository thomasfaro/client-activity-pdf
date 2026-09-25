#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tiers 2 and 3 of the source pack — the account's context and its data.

Tier 2 says what was measured and how completely; tier 3 is the data itself. Both
follow ``--lang``; the tier-1 semantic corpus stays in its source language (English).

Two rules run through every emitter here.

**Field selection is the privacy control.** Individual identifiers — channel ids, named
users, device tokens, email addresses — are never emitted because no emitter reads them.
The document-level scrub in ``build_source_pack`` is a backstop for personal data
embedded in free text (a push body that quotes a contact address), not the mechanism.

**One metric, one derivation.** ``metric()`` reads a canonical KPI from ``facts.json``
first, then ``audit.json`` through the same candidate paths ``build_facts`` uses, and
only computes locally when neither exists — always naming which happened. Re-deriving a
figure the run already derived is how one report publishes a frequency twice with two
values. ``facts.json``'s ``withheld`` list is honoured: a metric the collection
disqualified is reported as withheld, never as a number.
"""
from __future__ import annotations

import os
import re
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))

from build_facts import KPI_SPECS, first  # noqa: E402

# Rows per table segment. Purely insurance against a chunk boundary landing between a
# header and its rows — Notebook Enterprise reads long markdown tables fine, so the
# table is never converted into something else, only cut into header-bearing slices.
ROWS_PER_SEGMENT = 50

# Rows beyond which an inventory leaves its analysis document for a companion annex.
# The annex is a separate notebook source, so it can be DESELECTED: a strategy question
# ("which levers is this account not running") is answered better without three thousand
# rows of inventory competing for attention, and a debugging question ("list the
# mistyped attributes") is answered only with them. Same notebook, two selections.
ANNEX_THRESHOLD = 40

PUSH_FAMILIES = ("ios", "android", "amazon", "web")
CHANNELS = ("ios", "android", "amazon", "web", "email", "sms")


# --------------------------------------------------------------------------- #
# Formatting helpers
# --------------------------------------------------------------------------- #
def T(lang, fr, en):
    return en if lang == "en" else fr


def provenance(text):
    return text


# --------------------------------------------------------------------------- #
# Structural labels
# --------------------------------------------------------------------------- #
# Section titles and column headers, keyed by the French literal that appears in the
# code. Prose is localised inline with `T()`; these are the strings that repeat across
# emitters and would each need a `T()` at every call site.
#
# The point of the table is that `--lang en` produces an English document rather than
# English paragraphs under French headings — a half-translated definitions pack is worse
# than a single-language one. A missing key is recorded in `LABEL_MISSES` and the
# self-test fails on it, so the flag cannot quietly start lying again.
LABEL_MISSES = set()
_LANG = "fr"

_EN = {
    # headings
    "Canaux": "Channels",
    "Ce que la forme `{shape}` implique": "What the `{shape}` shape implies",
    "Ce qui n'est pas dans ce pack": "What is not in this pack",
    "Consolidation (watermark)": "Consolidation (watermark)",
    "Contexte marque": "Brand context",
    "Deltas qui sont des artefacts de calendrier": "Deltas that are calendar artefacts",
    "Définitions décodées des programmes": "Decoded programme definitions",
    "Entrées absentes de ce pack": "Inputs absent from this pack",
    "Instantané de la base (par plateforme)": "Installed-base snapshot (per platform)",
    "Inventaire détaillé": "Detailed inventory",
    "KPI de conversion détectés": "Detected conversion KPIs",
    "Métriques canoniques": "Canonical metrics",
    "Métriques disqualifiées par la collecte":
        "Metrics disqualified by the collection",
    "Métriques non résolues dans l'audit": "Metrics unresolved in the audit",
    "Notes de génération": "Generation notes",
    "Ordre de lecture": "Reading order",
    "Où chercher selon la question": "Where to look, by question",
    "Par canal": "By channel",
    "Par catégorie d'événement": "By event category",
    "Par type de KPI": "By KPI kind",
    "Par événement": "By event",
    "Part dans le volume de la fenêtre": "Share of the window's volume",
    "Part des programmes dans le volume": "Programmes' share of volume",
    "Pression marketing": "Marketing pressure",
    "Pression marketing par canal": "Marketing pressure per channel",
    "Questions de départ": "Opening questions",
    "Réconciliation alertant / silencieux": "Alerting vs silent reconciliation",
    "Signal de vertical (données)": "Vertical signal (from the data)",
    "Synthèse de l'analyse": "Analysis summary",
    "Série quotidienne des envois": "Daily send series",
    "Série quotidienne des ouvertures": "Daily open series",
    "Totaux par canal sur la période": "Per-channel totals over the period",
    "Traitement des données personnelles": "Personal-data handling",
    "Taxonomie": "Taxonomy",
    "Valeurs du compte pour les métriques benchmarkées":
        "The account's values for the benchmarked metrics",
    "Vue d'ensemble": "Overview",
    "Événements de permission — {kind} (période)":
        "Permission events — {kind} (period)",
    # tagging-plan blocks
    "Événements suivis": "Tracked events",
    "Attributs": "Attributes",
    "Tags et groupes de tags": "Tags and tag groups",
    "Listes d'abonnement": "Subscription lists",
    "Écrans": "Screens",
    "Données Airship exclues de l'inventaire client":
        "Airship-owned data excluded from the client inventory",
    "Événements porteurs de valeur": "Value-bearing events",
    "Écarts vs le référentiel du vertical": "Gaps against the vertical reference",
    "Signaux de conversion": "Conversion signals",
    "Événements recommandés pour le vertical et non détectés":
        "Events recommended for the vertical and not detected",
    "Événements détectés qui devraient porter une valeur":
        "Detected events that should carry a value",
    "Annexes (pas des sources)": "Annexes (not sources)",
    "Tier 1 — sémantique et référentiels": "Tier 1 - semantics and references",
    "Tier 2 — contexte du compte": "Tier 2 - the account's context",
    "Tier 3 — l'analyse du compte": "Tier 3 - the account's analysis",
    "Annexes 90+ — inventaires exhaustifs, à décocher":
        "90+ annexes - exhaustive inventories, deselectable",
    "Hors tier — le rapport livré, à cocher pour en discuter":
        "Outside the tiers - the delivered report, select it to argue with it",
    "Quelles sources cocher": "Which sources to select",
    "Créatives": "Creatives",
    "Série quotidienne — {kind}": "Daily series - {kind}",
    "Programmes": "Programmes",
    "Plateformes": "Platforms",
    "Propriétés par événement": "Per-event properties",
    "Attributs JSON": "JSON attributes",
    "Répartition des événements par intention": "Events by intent",
    "Intention": "Intent",
    "événements": "events",
    "occurrences": "occurrences",
    "événement le plus volumique": "highest-volume event",
    # column headers
    "Appareils uniques": "Unique devices",
    "Base joignable (snapshot)": "Reachable base (snapshot)",
    "Cadence": "Cadence",
    "Campagne": "Campaign",
    "Campagnes": "Campaigns",
    "Canal": "Channel",
    "Champ": "Field",
    "Clé": "Key",
    "Couverture / note": "Coverage / note",
    "Date": "Date",
    "Documents": "Documents",
    "Dénominateur (opt-in, snapshot)": "Denominator (opted-in, snapshot)",
    "Désinstallés": "Uninstalled",
    "Envois": "Sends",
    "Envois (période)": "Sends (period)",
    "Erreurs": "Errors",
    "Indicateur": "Indicator",
    "Lignes": "Rows",
    "Message": "Message",
    "Msg / opt-in / mois": "Msg / opted-in / month",
    "Métrique": "Metric",
    "Métrique benchmark": "Benchmark metric",
    "Opt-in": "Opted in",
    "Opt-out": "Opted out",
    "Ouvertures": "Opens",
    "Pages": "Pages",
    "Plateforme": "Platform",
    "Programme": "Programme",
    "Programme (group_id)": "Programme (group_id)",
    "Sonde": "Probe",
    "Sujet": "Subject",
    "Taux d'opt-in": "Opt-in rate",
    "Total sur la période": "Total over the period",
    "Valeur": "Value",
    "Valeurs": "Values",
    "Vertical": "Vertical",
    "app_key": "app_key",
    "cadence": "cadence",
    "canal": "channel",
    "catégorie": "category",
    "chemin dans audit.json": "path in audit.json",
    "clé du run": "the run's key",
    "confiance": "confidence",
    "contourne les limites de fréquence": "bypasses frequency limits",
    "corps": "body",
    "deep-link": "deep link",
    "dernière vue": "last seen",
    "direct": "direct",
    "déclencheurs": "triggers",
    "envois": "sends",
    "famille": "family",
    "famille d'appareils": "device family",
    "fiabilité": "reliability",
    "image": "image",
    "indirect": "indirect",
    "langues": "languages",
    "levier": "lever",
    "libellé": "label",
    "message center": "message center",
    "nature": "kind",
    "nom / titre": "name / title",
    "non attribué": "unattributed",
    "occurrences": "occurrences",
    "p10 (bas)": "p10 (low)",
    "p50 (médiane)": "p50 (median)",
    "p90 (haut)": "p90 (high)",
    "personnalisation": "personalisation",
    "pilier": "pillar",
    "première vue": "first seen",
    "période antérieure": "prior period",
    "raison": "reason",
    "réponses directes": "direct responses",
    "réponses influencées": "influenced responses",
    "score": "score",
    "somme value": "value sum",
    "source": "source",
    "taux d'attribution": "attribution rate",
    "titre": "title",
    "type d'audience": "audience kind",
    "type de KPI": "KPI kind",
    "typologie": "typology",
    "unité": "unit",
    "valeur": "value",
    "valeur du compte": "the account's value",
    "value / occurrence": "value / occurrence",
    "value monétaire": "monetary value",
    "variation %": "change %",
    "événements": "events",
    "Élément": "Item",
    # key/value row labels
    'Compte / marque': 'Account / brand',
    'Projet Airship': 'Airship project',
    'Région': 'Region',
    'Fenêtre analysée': 'Analysed window',
    'Fenêtre antérieure (comparaison)': 'Prior window (comparison)',
    'Jours': 'Days',
    'Vertical benchmark': 'Benchmark vertical',
    'Forme du compte': 'Account shape',
    'Pushs échantillonnés par la sonde': 'Pushes sampled by the probe',
    'Envois moyens par push': 'Mean sends per push',
    'Envois médians par push': 'Median sends per push',
    'Pushs par jour (plancher)': 'Pushes per day (floor)',
    'Volume/jour dimensionnable exactement': 'Volume/day exactly sizeable',
    'Envois programmes confirmés': 'Confirmed programme sends',
    'Campagnes au total': 'Campaigns in total',
    'Fondées sur un message': 'Message-based',
    'Signal CTA seul (in-app / Message Center)': 'CTA-only signal (in-app / Message Center)',
    'One-shot': 'One-shot',
    'Automatisées / récurrentes': 'Automated / recurring',
    'Ambiguës': 'Ambiguous',
    'Événements distincts': 'Distinct events',
    'Occurrences totales': 'Total occurrences',
    'Somme des `value`': 'Sum of `value`',
    'Événements dont `value` ressemble à un montant': 'Events whose `value` looks like an amount',
    '`value` lue comme monétaire': '`value` read as monetary',
    'Devise supposée': 'Assumed currency',
    'Confiance sur la devise': 'Currency confidence',
    'Source': 'Source',
    'Fichier': 'File',
    'Publié': 'Published',
    'Importé': 'Imported',
    'Vertical du compte': "The account's vertical",
    "Étape": "Stage",
    "État": "State",
    "Événement": "Event",
}


def set_lang(lang):
    """Set the language structural labels render in, for one build."""
    global _LANG  # noqa: PLW0603 — one pack per process; the alternative is threading
    _LANG = lang  # `lang` through forty call sites that only ever carry one value
    LABEL_MISSES.clear()


# A bare identifier: a channel name (`android`), or a key discovered in the data
# (`custom_name`, `carries_value`). Those are names, not prose, and translating them
# would break the link between a column and the field it came from.
_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def L(label):
    """Translate a structural label. Records a miss rather than silently returning FR.

    The dictionary is consulted first, so the few authored labels that happen to look
    like identifiers (`occurrences`, `direct`, `source`) still translate. Only what is
    neither translatable nor an identifier counts as a miss — which is how a heading
    added without an English form fails the self-test instead of shipping in French.
    """
    if _LANG != "en":
        return label
    if label in _EN:
        return _EN[label]
    if not _IDENTIFIER_RE.match(label):
        LABEL_MISSES.add(label)
    return label


def H(template, **kw):
    """An H2 heading, translated then formatted."""
    text = L(template)
    return "## " + (text.format(**kw) if kw else text)


def yn(lang, flag):
    return T(lang, fr="oui" if flag else "non", en="yes" if flag else "no")


def fmt_int(n):
    if n is None:
        return "n/a"
    return f"{int(round(float(n))):,}".replace(",", "\u202f")


def fmt_num(x, digits=2):
    if x is None:
        return "n/a"
    return f"{float(x):.{digits}f}".rstrip("0").rstrip(".")


def fmt_pct(x, digits=1):
    """`x` is a share (0-1) or already a percentage above 1.5 — states the unit either way."""
    if x is None:
        return "n/a"
    v = float(x)
    v = v * 100.0 if -1.5 <= v <= 1.5 else v
    return f"{v:.{digits}f}%"


def table(headers, rows):
    # Headers are translated here rather than at every call site: they are the same
    # forty-odd labels everywhere, and `data_table` renders every segment through here,
    # so each repeated header is localised without the segmenter knowing about language.
    headers = [L(str(h)) for h in headers]
    out = ["| " + " | ".join(str(h) for h in headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join("" if c is None else str(c) for c in r) + " |")
    return "\n".join(out)


def data_table(headers, rows, per_segment=ROWS_PER_SEGMENT):
    """A markdown table, split into header-repeating segments once it gets long.

    An earlier version turned any table over 30 rows into one self-describing bullet per
    record, on the assumption that the target was a small-chunk retrieval engine that
    would cut a long table away from its header. Notebook Enterprise is not that: it
    reads markdown tables well and has the context window to hold them, and the bullet
    form both triples the token count and destroys the tabular structure that makes
    "the ten events with the most volume" an easy question.

    So the table stays a table. Segmenting it every `per_segment` rows keeps the header
    within reach of any chunk boundary at no cost to the structure, and each segment
    states which slice of the whole it is — so a segment read in isolation still says
    how much it is not showing.
    """
    if not rows:
        return T(_LANG, fr="_(aucune ligne)_", en="_(no rows)_")
    if len(rows) <= per_segment:
        return table(headers, rows)

    parts = []
    total = len(rows)
    for start in range(0, total, per_segment):
        seg = rows[start:start + per_segment]
        caption = T(_LANG,
                    fr=f"_Lignes {start + 1}–{start + len(seg)} sur {total}._",
                    en=f"_Rows {start + 1}-{start + len(seg)} of {total}._")
        parts.append(f"{caption}\n\n{table(headers, seg)}")
    return "\n\n".join(parts)


def kv_rows(payload, skip=()):
    """Scalar fields of a JSON blob as (label, formatted value), prose split out.

    Returns (rows, prose). Two things the raw dump got wrong: a bare `1234567890` and
    `0.10306406685236769` shipped unformatted next to figures the rest of the pack prints
    as `1 234 567 890` and `10,3 %`, and a 300-character `verdict` string stretched a
    two-column table across the page. Long strings come back separately, to be rendered
    as blockquotes under the table.
    """
    rows, prose = [], []
    for k, v in (payload or {}).items():
        if k in skip or not isinstance(v, (str, int, float, bool)):
            continue
        if isinstance(v, str):
            if len(v) > 120:
                prose.append((k, v))
            else:
                rows.append((k, v))
        elif isinstance(v, bool):
            rows.append((k, v))
        elif isinstance(v, int):
            rows.append((k, fmt_int(v)))
        else:
            # A share reads as a share; anything else keeps enough precision to be
            # recognised without printing seventeen digits of float noise.
            rows.append((k, fmt_pct(v, 2) if 0 < abs(v) < 1 and (
                "share" in k or "rate" in k or "ratio" in k) else fmt_num(v, 4)))
    return rows, prose


class Annex:
    """Bulk tables of one tier-3 document, held until we know whether to split them out.

    Inline while the inventory is small enough not to drown the surrounding analysis; a
    separate 9x source once it is not. The calling emitter does not decide — it declares
    its sections and asks for either the tables or a pointer to them, so the split
    threshold lives in one place and every heavy document behaves the same way.
    """

    def __init__(self, name, title, provenance_text, note=None):
        self.name = name
        self.title = title
        self.provenance = provenance_text
        self.note = note
        self.sections = []

    def section(self, heading, headers, rows, note=None):
        self.sections.append((heading, headers, list(rows), note))
        return self

    @property
    def rows(self):
        return sum(len(rows) for _h, _hd, rows, _n in self.sections)

    @property
    def split(self):
        return self.rows > ANNEX_THRESHOLD

    def _render(self):
        out = []
        for heading, headers, rows, note in self.sections:
            out += [heading, ""]
            if note:
                out += [note, ""]
            out += [data_table(headers, rows), ""]
        return out

    def emit(self, pack):
        """-> the lines to put in the analysis document (tables, or a pointer)."""
        if not self.sections or not self.rows:
            return []
        if not self.split:
            return self._render()

        body = []
        if self.note:
            body += [self.note, ""]
        body += self._render()
        pack.add(self.name, self.title, 4, "\n".join(body), self.provenance)

        counts = " · ".join(
            f"{heading.lstrip('# ')} ({len(rows)})"
            for heading, _hd, rows, _n in self.sections if rows)
        return [T(pack.lang,
                  fr=f"> **Le détail exhaustif est dans `{self.name}`**, une source "
                     f"distincte du notebook — {counts}. Décochez-la pour une question "
                     f"de stratégie, cochez-la pour une question de dénombrement ou de "
                     f"débogage.",
                  en=f"> **The exhaustive detail is in `{self.name}`**, a separate "
                     f"notebook source — {counts}. Deselect it for a strategy question, "
                     f"select it for a counting or debugging question."),
                ""]


def day(value):
    """The calendar day of a collector timestamp, as `YYYY-MM-DD`.

    The series carry `2026-09-07 00:00:00` on some accounts and `2026-09-07` on others.
    Comparing the two forms as strings put the timestamped last day of the window *after*
    the plain-date bound, so the window's final day was dropped from every local total —
    a 1-in-30 undercount, small enough to look like rounding against the audit.
    """
    return str(value)[:10]


def series_rows(payload, key):
    """The daily rows of a `{key: [...]}` collector file, unsliced."""
    if isinstance(payload, dict):
        rows = payload.get(key)
        if isinstance(rows, list):
            return rows
    return []


def window_series(pack, disc, name, key):
    """The daily rows of a collector file, **sliced to the analysed window**.

    The slice is not optional. `collect.py` pulls the current and the prior window in one
    doubled request and lets `analyze.py` cut them apart, so `sends.json` on a 30-day
    review holds 60 rows. Summing the file returned roughly twice the period's volume —
    on one property-listings account, 510 M iOS sends against the 257 M the audit reports
    for the same window — and that doubled figure then fed the pressure table, which read
    twice the true messages per opted-in device per month. Every local aggregate went
    through the unsliced read, so every one of them was wrong on an account collected
    this way, and each was wrong quietly: the figures were plausible.
    """
    rows = series_rows(disc["data"].get(name), key)
    win = getattr(pack, "window_range", None)
    if not rows or not win or not win[0] or not win[1]:
        return rows
    start, end = day(win[0]), day(win[1])
    kept = [r for r in rows if isinstance(r, dict) and r.get("date")
            and start <= day(r["date"]) <= end]
    if not kept:
        pack.notes.append(
            f"{name}.json: no row falls inside {win[0]}..{win[1]}, so its "
            f"{len(rows)} row(s) were summed unsliced — treat its local totals as "
            f"covering an unknown period")
        return rows
    return kept


def channel_totals(rows):
    """`{channel: total}` over a daily series, only for columns that are present."""
    out = {}
    for row in rows or []:
        for c in CHANNELS:
            if c in row:
                try:
                    out[c] = out.get(c, 0) + float(row[c] or 0)
                except (TypeError, ValueError):
                    continue
    return out


# --------------------------------------------------------------------------- #
# Metric resolution
# --------------------------------------------------------------------------- #
_SPEC = {s["key"]: s for s in KPI_SPECS}


def metric(disc, key, local=None):
    """Resolve one canonical KPI. Returns a dict, never raises.

    ``{"value", "prior", "delta_pct", "source", "withheld"}``. ``value`` is None when
    nothing resolved, which the emitters print as an explicit absence rather than hiding.
    """
    facts = disc["data"].get("facts") or {}
    audit = disc["data"].get("audit") or {}

    withheld = facts.get("withheld") or {}
    if isinstance(withheld, dict) and key in withheld:
        return {"value": None, "prior": None, "delta_pct": None, "withheld": True,
                "source": f"withheld by the collection ({withheld[key]})"}
    if isinstance(withheld, list) and key in withheld:
        return {"value": None, "prior": None, "delta_pct": None, "withheld": True,
                "source": "withheld by the collection"}

    for kpi in facts.get("kpis") or []:
        if kpi.get("key") == key and kpi.get("value") is not None:
            return {"value": kpi["value"], "prior": kpi.get("prior"),
                    "delta_pct": kpi.get("delta_pct"), "withheld": False,
                    "source": f"facts.json (from audit.json `{kpi.get('source')}`)"}

    spec = _SPEC.get(key)
    if spec and audit:
        cur, path = first(audit, spec["cur"])
        if cur is not None:
            pri, _ = first(audit, spec["pri"])
            return {"value": cur, "prior": pri, "delta_pct": None, "withheld": False,
                    "source": f"audit.json `{path}`"}

    if local is not None:
        return {"value": local, "prior": None, "delta_pct": None, "withheld": False,
                "source": "computed by build_source_pack.py from data/*.json"}

    return {"value": None, "prior": None, "delta_pct": None, "withheld": False,
            "source": "not available in this pack"}


def metric_bullet(pack, disc, key, local=None):
    """A one-line report of a canonical KPI, publishing it so `verify` demands a fiche."""
    spec = _SPEC[key]
    m = metric(disc, key, local=local)
    label = spec["fr"] if pack.lang != "en" else spec["en"]
    if m["value"] is None:
        return f"- **{label}** (`{key}`) : n/a — {m['source']}"
    pack.publish_metric(key)
    shown = fmt_pct(m["value"]) if spec["unit"] == "pct" else (
        fmt_num(m["value"]) if spec["unit"] == "rate" else fmt_int(m["value"]))
    bits = [f"- **{label}** (`{key}`) : **{shown}**"]
    if m["prior"] is not None:
        prior = fmt_pct(m["prior"]) if spec["unit"] == "pct" else (
            fmt_num(m["prior"]) if spec["unit"] == "rate" else fmt_int(m["prior"]))
        bits.append(T(pack.lang, fr=f"période antérieure {prior}",
                      en=f"prior period {prior}"))
    if m["delta_pct"] is not None:
        bits.append(T(pack.lang, fr=f"variation {fmt_num(m['delta_pct'], 1)}%",
                      en=f"change {fmt_num(m['delta_pct'], 1)}%"))
    bits.append(T(pack.lang, fr=f"source : {m['source']}", en=f"source: {m['source']}"))
    return " · ".join(bits)


# --------------------------------------------------------------------------- #
# Vertical
# --------------------------------------------------------------------------- #
def resolve_account_vertical(disc):
    """The benchmark vertical the run already settled on, if any."""
    facts = disc["data"].get("facts") or {}
    if facts.get("vertical"):
        v = facts["vertical"]
        return v.get("key") if isinstance(v, dict) else v
    audit = disc["data"].get("audit") or {}
    for path in ("purpose.vertical", "vertical", "benchmarks.vertical"):
        val, _ = first(audit, [path])
        if val:
            return val.get("key") if isinstance(val, dict) else val
    analysis = disc["data"].get("analysis") or {}
    return analysis.get("suggestedVertical") or None


# --------------------------------------------------------------------------- #
# Shape
# --------------------------------------------------------------------------- #
SHAPE_MEANING = {
    "dashboard": (
        "Les messages sont énumérables un par un : l'inventaire de campagnes est "
        "exhaustif et chaque chiffre par message est direct.",
        "Messages are enumerable one by one: the campaign inventory is exhaustive and "
        "every per-message figure is direct."),
    "firehose_grouped": (
        "Le compte envoie un volume unitaire trop dense pour être énuméré, mais les "
        "programmes portent un `group_id` : le volume et les taux viennent de l'agrégat "
        "par programme (`pergroup/detail`), pas d'une somme de messages. Un chiffre par "
        "message n'existe que pour les messages effectivement résolus.",
        "The account sends a unitary volume too dense to enumerate, but programmes carry "
        "a `group_id`: volume and rates come from the per-programme aggregate "
        "(`pergroup/detail`), not from a sum of messages."),
    "firehose_groupless": (
        "Volume unitaire dense sans couche de programme : l'inventaire est reconstruit "
        "par énumération partitionnée dans le temps, avec une couverture chiffrée. Ne "
        "lisez aucun inventaire comme complet sans lire cette couverture.",
        "Dense unitary volume with no programme layer: the inventory is rebuilt by "
        "time-partitioned enumeration with a quantified coverage."),
    "firehose_unattributed": (
        "Compte dense qu'aucune énumération ne peut dimensionner. Le volume vient de "
        "`/api/reports/sends`, l'inventaire du journal d'activité tuilé par heure, et la "
        "typologie d'un échantillon pondéré par les envois. Aucun chiffre par message "
        "n'est exhaustif.",
        "A dense account no enumeration can size. Volume comes from "
        "`/api/reports/sends`, the inventory from the hour-tiled activity log, and "
        "typology from a sends-weighted sample. No per-message figure is exhaustive."),
}


# --------------------------------------------------------------------------- #
# Tier 2
# --------------------------------------------------------------------------- #
def emit_context(pack, disc):
    d = disc["data"]
    man = d.get("collect_manifest") or {}
    probe = d.get("probe") or {}
    win = man.get("window") or {}

    rows = [
        (L("Compte / marque"), pack.client),
        (L("Projet Airship"), man.get("project")),
        (L("Région"), man.get("region")),
        (L("Fenêtre analysée"), " → ".join(str(x) for x in (win.get("current") or []))
         or pack.window),
        (L("Fenêtre antérieure (comparaison)"),
         " → ".join(str(x) for x in (win.get("prior") or [])) or "non collectée"),
        (L("Jours"), win.get("days")),
        (L("Vertical benchmark"), pack.vertical or "non résolu"),
        (L("Forme du compte"), man.get("shape") or probe.get("shape") or "inconnue"),
    ]
    body = [T(pack.lang,
              fr="Identité du run et ce que la forme du compte implique sur la lecture "
                 "de tous les chiffres du pack.",
              en="Run identity, and what the account's shape implies for reading every "
                 "figure in this pack."),
            "",
            table(["Élément", "Valeur"], [(k, v) for k, v in rows if v is not None]),
            ""]

    shape = man.get("shape") or probe.get("shape")
    if shape:
        fr, en = SHAPE_MEANING.get(
            shape, ("Forme non répertoriée — lisez la couverture avant toute lecture "
                    "exhaustive.",
                    "Unlisted shape — read the coverage document first."))
        body += [H("Ce que la forme `{shape}` implique", shape=shape), "", T(pack.lang, fr, en), ""]
        if probe.get("shape_reason"):
            body += [T(pack.lang,
                      fr=f"> Raison retenue par la sonde : {probe['shape_reason']}",
                      en=f"> Shape reason recorded by the probe: {probe['shape_reason']}"), ""]
        probe_rows = [
            (L("Pushs échantillonnés par la sonde"), fmt_int(probe.get("sampled_pushes"))),
            (L("Volume/jour dimensionnable exactement"),
             probe.get("pushes_per_day_exact")),
            (L("Pushs par jour (plancher)"), fmt_int(probe.get("pushes_per_day_floor"))),
            (L("Envois programmes confirmés"),
             fmt_int(probe.get("confirmed_program_sends"))),
        ]

        # The probe disqualifies its own per-push statistics when the sample is too thin
        # to describe the account, and `per_push_stats_note` says so in as many words. An
        # earlier version printed "mean sends per push: 0.185" next to a run reporting
        # 734 million sends, which is not a small figure but a meaningless one — the
        # sample carried 0.002% of the period. A disqualified statistic is not published.
        if probe.get("per_push_stats_reliable"):
            probe_rows.insert(1, (L("Envois moyens par push"),
                                  fmt_num(probe.get("mean_sends_per_push"), 2)))
            probe_rows.insert(2, (L("Envois médians par push"),
                                  fmt_num(probe.get("median_sends_per_push"), 2)))
            per_push_note = None
        elif probe.get("mean_sends_per_push") is not None:
            per_push_note = T(pack.lang,
                              fr="> **Les envois par push ne sont pas publiés** : la "
                                 "sonde a marqué sa propre statistique comme non fiable. "
                                 + (str(probe.get("per_push_stats_note") or "")),
                              en="> **Sends per push are not published**: the probe "
                                 "marked its own statistic unreliable. "
                                 + (str(probe.get("per_push_stats_note") or "")))
        else:
            per_push_note = None

        probe_rows = [(k, v) for k, v in probe_rows if v not in (None, "")]
        if probe_rows:
            body += [table(["Sonde", "Valeur"], probe_rows), ""]
        if per_push_note:
            body += [per_push_note, ""]

    # Channel presence, from sends volume rather than from devices alone: a channel can
    # be active with sends > 0 and zero opted-in devices, and email is where that happens.
    sends = window_series(pack, disc, "sends", "sends")
    devices = d.get("devices") or {}
    if sends or devices:
        try:
            from channel_activity import channel_summary
            summary = channel_summary(sends, devices,
                                      series_rows(d.get("events"), "events"))
            crows = []
            for name, info in (summary.get("channels") or {}).items():
                if not info.get("active") and not info.get("reachable_opted_in"):
                    continue
                crows.append((name, T(pack.lang, fr="actif" if info.get("active") else "inactif",
                               en="active" if info.get("active") else "inactive"),
                              fmt_int(info.get("period_sends")),
                              fmt_int(info.get("reachable_opted_in")),
                              (info.get("cadence") or {}).get("classification") or ""))
            if crows:
                body += [H("Canaux"), "",
                         table(["Canal", "État", "Envois (période)",
                                "Base joignable (snapshot)", "Cadence"], crows),
                         "",
                         T(pack.lang,
                           fr="Les envois sont une mesure de période, la base joignable "
                              "un instantané : les deux colonnes ne se rapportent pas au "
                              "même objet et ne doivent pas être combinées en un ratio "
                              "sans passer par la fiche `pressure`.",
                           en="Sends are a period measure and the reachable base is a "
                              "snapshot: the two columns do not describe the same thing."),
                         ""]
        except Exception as exc:  # noqa: BLE001 — one degraded block, not a failed pack
            pack.notes.append(f"10_profil_du_compte: channel summary unavailable ({exc})")

    brand = d.get("brand")
    if isinstance(brand, dict) and brand:
        keep = {k: v for k, v in brand.items()
                if isinstance(v, (str, int, float)) and str(v).strip()}
        if keep:
            body += [H("Contexte marque"), "",
                     T(pack.lang,
                       fr="Recherche menée pendant la revue, **non dérivée de l'API** : à "
                          "traiter comme du contexte à vérifier, pas comme de la mesure.",
                       en="Research authored during the review, **not derived from the "
                          "API**: treat as context to verify, not as measurement."),
                     "",
                     table(["Champ", "Valeur"], sorted(keep.items())), ""]

    pack.add("10_profil_du_compte.md",
             T(pack.lang, fr="Profil du compte et forme de la donnée",
               en="Account profile and data shape"),
             2, "\n".join(body),
             provenance("collect_manifest.json · probe.json · devices.json · sends.json"))

    emit_coverage(pack, disc)


def emit_coverage(pack, disc):
    d = disc["data"]
    man = d.get("collect_manifest") or {}
    stages = man.get("stages") or {}

    body = [T(pack.lang,
              fr="Ce qui a été lu, sur combien de pages et d'appels, et ce qui n'a pas "
                 "pu l'être. **À lire avant de traiter un chiffre du pack comme "
                 "complet.** La couverture est mesurée par le collecteur, pas estimée "
                 "ici.",
              en="What was read, over how many pages and calls, and what could not be. "
                 "**Read this before treating any figure in the pack as complete.**"),
           ""]

    if stages:
        rows, silent = [], []
        for name, info in stages.items():
            if not isinstance(info, dict):
                continue
            got = info.get("rows")
            if isinstance(got, dict):
                got = " · ".join(f"{k}={fmt_int(v)}" for k, v in got.items())
            elif got is not None:
                got = fmt_int(got)
            cells = (got, info.get("pages"),
                     info.get("coverage") or info.get("note") or "",
                     info.get("errors") or "")
            # A stage that recorded no counter at all is a row of four empty cells, which
            # reads as missing data rather than as "it ran and had nothing to count".
            if not any(c not in (None, "") for c in cells):
                silent.append(name)
                continue
            rows.append((name, *cells))
        body += [data_table(
            ["Étape", "Lignes", "Pages", "Couverture / note", "Erreurs"], rows), ""]
        if silent:
            body += [T(pack.lang,
                       fr=f"Étapes exécutées sans compteur enregistré : "
                          f"{', '.join(silent)}.",
                       en=f"Stages that ran without recording a counter: "
                          f"{', '.join(silent)}."), ""]

    totals = man.get("totals") or {}
    if totals:
        body += [T(pack.lang,
                   fr=f"Total : **{fmt_int(totals.get('api_calls'))} appels API** en "
                      f"{fmt_num(totals.get('elapsed_s'), 1)} s.",
                   en=f"Total: **{fmt_int(totals.get('api_calls'))} API calls** in "
                      f"{fmt_num(totals.get('elapsed_s'), 1)} s."), ""]

    settling = (man.get("window") or {}).get("settling") or {}
    if settling:
        body += [H("Consolidation (watermark)"), ""]
        if settling.get("ends_after_watermark"):
            body += [T(pack.lang,
                       fr=f"**La fenêtre se termine après le watermark de consolidation "
                          f"({settling.get('days_past_watermark')} jour(s) au-delà).** "
                          f"La fin de fenêtre peut renvoyer des zéros qui ne sont pas de "
                          f"vrais zéros : traitez-la comme provisoire.",
                       en=f"**The window ends past the consolidation watermark "
                          f"({settling.get('days_past_watermark')} day(s) beyond).** The "
                          f"tail can return zeros that are not real zeros."), ""]
        else:
            body += [T(pack.lang,
                       fr="La fenêtre se termine avant le watermark : les données sont "
                          "consolidées.",
                       en="The window ends before the watermark: the data is settled."),
                     ""]
        srows, sprose = kv_rows(settling)
        body += [table(["Champ", "Valeur"], srows), ""]
        body += [f"> **{k}** — {v}\n" for k, v in sprose]

    prog = d.get("program_volume") or {}
    if prog:
        prows, pprose = kv_rows(prog)
        body += [H("Part des programmes dans le volume"), "",
                 table(["Champ", "Valeur"], prows), ""]
        body += [f"> **{k}** — {v}\n" for k, v in pprose]

    rec = d.get("reconcile") or {}
    if rec:
        rrows, rprose = kv_rows(rec)
        body += [H("Réconciliation alertant / silencieux"), "",
                 table(["Champ", "Valeur"], rrows), ""]
        body += [f"> **{k}** — {v}\n" for k, v in rprose]

    if disc["missing"]:
        body += [H("Entrées absentes de ce pack"), "",
                 T(pack.lang,
                   fr="Ces fichiers n'existaient pas dans le répertoire de travail au "
                      "moment de la génération. Les documents qui en dépendaient sont "
                      "absents ou réduits — ce n'est pas une donnée à zéro.",
                   en="These files did not exist in the work directory when the pack was "
                      "generated. Documents depending on them are absent or reduced — "
                      "this is not data at zero."),
                 "",
                 "\n".join(f"- `{name}`" for name in sorted(disc["missing"])), ""]

    pack.add("11_perimetre_et_couverture.md",
             T(pack.lang, fr="Périmètre, couverture et fiabilité de la collecte",
               en="Scope, coverage and collection reliability"),
             2, "\n".join(body),
             provenance("collect_manifest.json · program_volume.json · reconcile.json"))


# --------------------------------------------------------------------------- #
# Tier 3 — activity
# --------------------------------------------------------------------------- #
def emit_activity(pack, disc):
    emit_audience(pack, disc)
    emit_volume(pack, disc)
    emit_campaigns(pack, disc)
    emit_programs(pack, disc)
    emit_creatives(pack, disc)


def emit_audience(pack, disc):
    d = disc["data"]
    devices = d.get("devices") or {}
    counts = devices.get("counts") or {}
    if not counts and not d.get("optins"):
        return

    body = [T(pack.lang,
              fr="Deux familles de mesures que ce document garde **séparées** : "
                 "l'instantané de la base installée (`/api/reports/devices`) et les "
                 "flux d'événements de permission de la période "
                 "(`/optins`, `/optouts`). Elles ne se réconcilient pas et leur "
                 "différence ne décrit pas une croissance de base.",
              en="Two families of measurement, kept **separate**: the installed-base "
                 "snapshot and the period permission event flows. They do not reconcile "
                 "and their difference does not describe base growth."),
           ""]

    if counts:
        rows, total_unique, total_optin = [], 0, 0
        for plat, info in counts.items():
            if not isinstance(info, dict):
                continue
            oi = info.get("opted_in")
            oo = info.get("opted_out")
            un = info.get("uninstalled")
            uniq = info.get("unique_devices") or info.get("unique")
            rate = (float(oi) / float(uniq)) if (oi is not None and uniq) else None
            rows.append((plat, fmt_int(oi), fmt_int(oo), fmt_int(un),
                         fmt_int(uniq) if uniq else "n/a",
                         fmt_pct(rate) if rate is not None else "n/a"))
            total_optin += float(oi or 0)
            total_unique += float(uniq or 0)
        body += [H("Instantané de la base (par plateforme)"), "",
                 table(["Plateforme", "Opt-in", "Opt-out", "Désinstallés",
                        "Appareils uniques", "Taux d'opt-in"], rows), "",
                 T(pack.lang,
                   fr="Le taux d'opt-in n'est calculé que là où la charge utile porte le "
                      "nombre d'appareils uniques. Ailleurs il est `n/a` : additionner "
                      "opt-in, opt-out et désinstallés ne donne pas un dénominateur "
                      "d'appareils uniques.",
                   en="The opt-in rate is computed only where the payload carries the "
                      "unique-devices count. Elsewhere it is `n/a`: summing the states "
                      "does not give a unique-devices denominator."),
                 ""]

        app_optin = sum(float((counts.get(p) or {}).get("opted_in") or 0)
                        for p in ("ios", "android", "amazon"))
        web_optin = float((counts.get("web") or {}).get("opted_in") or 0)
        total_dev = devices.get("total_unique_devices") or (total_unique or None)
        body += [H("Métriques canoniques"), "",
                 metric_bullet(pack, disc, "audience_total", local=total_dev),
                 metric_bullet(pack, disc, "app_optin", local=app_optin or None),
                 metric_bullet(pack, disc, "web_optin", local=web_optin or None),
                 metric_bullet(pack, disc, "optin_rate",
                               local=(total_optin / total_unique)
                               if total_unique else None),
                 ""]

    annex = Annex("97_annexe_permission_quotidienne.md",
                  T(pack.lang, fr="Annexe — opt-ins et opt-outs, jour par jour",
                    en="Annex - opt-ins and opt-outs, day by day"),
                  provenance("optins.json · optouts.json"))
    for kind, key in (("optins", "optins"), ("optouts", "optouts")):
        rows = window_series(pack, disc, kind, kind)
        if not rows:
            continue
        tot = channel_totals(rows)
        body += [H("Événements de permission — {kind} (période)", kind=kind), "",
                 table(["Canal", "Total sur la période"],
                       [(c, fmt_int(v)) for c, v in sorted(tot.items())]), "",
                 metric_bullet(pack, disc, key,
                               local=sum(tot.values()) or None), ""]
        # Columns are fixed from the whole series, not per row: a day missing a channel
        # key would otherwise shift every later cell one column left.
        cols = [c for c in CHANNELS if any(c in r for r in rows)]
        annex.section(H("Série quotidienne — {kind}", kind=kind), ["Date"] + cols,
                      [(day(r.get("date")), *(fmt_int(r.get(c)) for c in cols))
                       for r in rows])
    body += annex.emit(pack)

    pack.add("20_audience_et_permission.md",
             T(pack.lang, fr="Audience et permission", en="Audience and permission"),
             3, "\n".join(body),
             provenance("devices.json (snapshot) · optins.json · optouts.json (période)"))


def emit_volume(pack, disc):
    d = disc["data"]
    sends = window_series(pack, disc, "sends", "sends")
    opens = window_series(pack, disc, "opens", "opens")
    if not sends and not opens:
        return

    st = channel_totals(sends)
    ot = channel_totals(opens)
    push_sends = sum(v for c, v in st.items() if c in PUSH_FAMILIES)
    days = ((d.get("collect_manifest") or {}).get("window") or {}).get("days")

    body = [T(pack.lang,
              fr="Volume d'envoi et pression marketing. **`/api/reports/sends` n'est pas "
                 "push-only** : le tableau ci-dessous sépare les colonnes, et le total "
                 "push ne somme que les familles d'appareils.",
              en="Send volume and marketing pressure. **`/api/reports/sends` is not "
                 "push-only**: the table below separates the columns."),
           "",
           H("Totaux par canal sur la période"), "",
           table(["Canal", "Envois", "Ouvertures"],
                 [(c, fmt_int(st.get(c)), fmt_int(ot.get(c)))
                  for c in CHANNELS if c in st or c in ot]), "",
           T(pack.lang,
             fr=f"Total push (familles {', '.join(PUSH_FAMILIES)}) : "
                f"**{fmt_int(push_sends)}** envois.",
             en=f"Total push ({', '.join(PUSH_FAMILIES)} families): "
                f"**{fmt_int(push_sends)}** sends."), "",
           H("Métriques canoniques"), "",
           metric_bullet(pack, disc, "push_sends", local=push_sends or None),
           metric_bullet(pack, disc, "email_sends", local=st.get("email") or None),
           metric_bullet(pack, disc, "opens", local=sum(ot.values()) or None),
           metric_bullet(pack, disc, "open_rate"),
           metric_bullet(pack, disc, "direct_open_rate"),
           metric_bullet(pack, disc, "silent_share"),
           ""]

    # Pressure. Always with the denominator named — dividing one channel's sends by
    # another channel's base is the error `04_limites_et_inferences_interdites.md`
    # spends a paragraph on.
    #
    # And nothing at all when the run disqualified the metric. `facts.json`'s contract is
    # that a withheld figure must not be published, and a per-channel table that ends in
    # a blended row publishes exactly the figure that was withheld — the fact that this
    # module recomputed it from raw data rather than reading it does not make it
    # publishable.
    counts = (d.get("devices") or {}).get("counts") or {}
    # Months, not weeks. The month is the only pressure unit the skill publishes, because it
    # is the unit of the UA benchmark (`sends_per_user_month`) — a weekly column invites the
    # reader to compare it to a monthly band, and publishing both side by side is how two
    # reviews of two accounts ended up a factor of ten apart.
    months = (float(days) / 30.44) if days else None
    pressure = metric(disc, "pressure")
    prows = []
    if pressure["withheld"]:
        body += [H("Pression marketing"), "",
                 T(pack.lang,
                   fr=f"**La collecte a disqualifié cette métrique et le pack ne la "
                      f"publie donc pas** : {pressure['source']}. Les volumes par canal "
                      f"et les bases joignables restent lisibles ci-dessus et dans "
                      f"`10_profil_du_compte.md` ; les recombiner en une fréquence "
                      f"reviendrait à republier le chiffre écarté.",
                   en=f"**The collection disqualified this metric, so the pack does not "
                      f"publish it**: {pressure['source']}."),
                 ""]
    elif months:
        for c in CHANNELS:
            vol = st.get(c)
            if not vol:
                continue
            base = float((counts.get(c) or {}).get("opted_in") or 0)
            if base:
                prows.append((c, fmt_int(vol), fmt_int(base),
                              fmt_num(vol / months / base, 2)))
            else:
                prows.append((c, fmt_int(vol), "n/a",
                              fmt_num(vol / months, 1) + T(pack.lang, fr=" envois/mois",
                                                           en=" sends/month")))
        # No blended row. It used to sum every push family, including web, and land next
        # to the canonical `pressure` — which the audit derives over the APP families
        # alone (`pressure.app_month`). Two figures, both labelled as the account's
        # pressure, differing by a quarter because one of them silently changed the
        # population. The canonical metric is published on its own line below; the table
        # stays per-channel, where the denominator is unambiguous.
    if prows:
        body += [H("Pression marketing par canal"), "",
                 table(["Canal", "Envois (période)", "Dénominateur (opt-in, snapshot)",
                        "Msg / opt-in / mois"], prows), "",
                 T(pack.lang,
                   fr="Le dénominateur est **celui du canal lui-même**. Quand il vaut "
                      "`n/a`, seule la cadence brute est publiée et aucune comparaison au "
                      "benchmark n'est légitime. L'unité est le mois, celle de "
                      "`sends_per_user_month` : elle se compare directement à la bande. "
                      "Deux canaux ne se comparent pas entre eux lorsque leurs mécaniques "
                      "diffèrent — un navigateur opt-in et un appareil opt-in ne sont pas "
                      "sur la même échelle.",
                   en="The denominator is **the channel's own**. Where it is `n/a`, only "
                      "the raw cadence is published and no benchmark comparison is "
                      "legitimate. The unit is the month, the unit of "
                      "`sends_per_user_month`, so it compares straight to the band. Two "
                      "channels do not compare to each other when their mechanics differ "
                      "— an opted-in browser and an opted-in device are not on one scale."),
                 "",
                 T(pack.lang,
                   fr="**Aucune ligne « tous canaux » ici.** La pression du compte est "
                      "publiée ci-dessous comme métrique canonique, sur la population "
                      "que l'audit a retenue ; recombiner les lignes du tableau donnerait "
                      "un second chiffre, sur une autre population, portant le même nom.",
                   en="**No all-channel row here.** The account's pressure is published "
                      "below as the canonical metric, over the population the audit "
                      "retained; recombining the rows would give a second figure, over a "
                      "different population, under the same name."),
                 "",
                 metric_bullet(pack, disc, "pressure"), ""]
    elif not pressure["withheld"]:
        body += [metric_bullet(pack, disc, "pressure"), ""]

    annex = Annex("94_annexe_series_quotidiennes.md",
                  T(pack.lang, fr="Annexe — séries quotidiennes, jour par jour",
                    en="Annex - daily series, day by day"),
                  provenance("sends.json · opens.json"),
                  note=T(pack.lang,
                         fr="Les mêmes séries sont aussi dans `series_daily.csv`, à "
                            "ouvrir dans un tableur plutôt qu'à charger dans le notebook.",
                         en="The same series are also in `series_daily.csv`, for a "
                            "spreadsheet rather than the notebook."))
    annex.section(H("Série quotidienne des envois"),
                  ["Date"] + [c for c in CHANNELS if c in st],
                  [(day(r.get("date")),
                    *(fmt_int(r.get(c)) for c in CHANNELS if c in st))
                   for r in sends])
    if opens:
        annex.section(H("Série quotidienne des ouvertures"),
                      ["Date"] + [c for c in CHANNELS if c in ot],
                      [(day(r.get("date")),
                        *(fmt_int(r.get(c)) for c in CHANNELS if c in ot))
                       for r in opens])
    body += annex.emit(pack)

    pack.add("21_volume_et_pression.md",
             T(pack.lang, fr="Volume d'envoi et pression marketing",
               en="Send volume and marketing pressure"),
             3, "\n".join(body),
             provenance("sends.json · opens.json · devices.json · collect_manifest.json"))

    _write_series_csv(pack, sends, opens)


def _write_series_csv(pack, sends, opens):
    """The daily series as CSV — an annex for a spreadsheet, not a notebook source."""
    if not sends and not opens:
        return
    cols = [c for c in CHANNELS if any(c in r for r in sends)]
    ocols = [c for c in CHANNELS if any(c in r for r in opens)]
    lines = ["date," + ",".join([f"sends_{c}" for c in cols]
                                + [f"opens_{c}" for c in ocols])]
    by_date = {}
    for r in sends:
        by_date.setdefault(day(r.get("date")), {})["s"] = r
    for r in opens:
        by_date.setdefault(day(r.get("date")), {})["o"] = r
    for date in sorted(k for k in by_date if k):
        s = by_date[date].get("s") or {}
        o = by_date[date].get("o") or {}
        vals = [str(s.get(c) or 0) for c in cols] + [str(o.get(c) or 0) for c in ocols]
        lines.append(f"{date}," + ",".join(vals))
    pack.add_raw("series_daily.csv", "\n".join(lines) + "\n",
                 "annexe tableur — CSV n'est pas un type de source accepté par Gemini "
                 "Notebook Enterprise ; à importer via Sheets si nécessaire")


def _campaign_inventory(disc, vertical):
    """The canonical multi-channel inventory, enriched with the rich per-campaign fields.

    `campaign_inventory` normalises a campaign down to a common shape and drops
    `occurrences` / `cadence` / `first_seen`, which is right for its own purpose and
    wrong for a document whose job is to let someone dig. The two are joined on `key`.
    """
    from activity_log import merge_push_inventories
    from campaign_inventory import build_inventory
    from campaign_purpose import classify_purpose
    from classify_campaigns import classify

    d = disc["data"]
    pushes = (d.get("responses") or {}).get("pushes") or []
    activities = (d.get("activity") or {}).get("activity") or []
    events = series_rows(d.get("events"), "events")
    decoded = d.get("decoded") or {}

    names = {pid: rec.get("message_name") for pid, rec in decoded.items()
             if isinstance(rec, dict) and rec.get("message_name")}
    bodies = {}
    for pid, rec in decoded.items():
        if not isinstance(rec, dict):
            continue
        txt = " ".join(str(rec.get(k) or "") for k in ("title", "body")).strip()
        if txt:
            bodies[pid] = txt

    merged = merge_push_inventories(pushes, activities)["merged"] if pushes or activities else []
    cls = classify(merged, names) if merged else {"campaigns": [], "groups": []}
    inv = build_inventory(push_campaigns=cls["campaigns"], events=events)
    rich = {c.get("key"): c for c in cls["campaigns"]}
    classified = classify_purpose(inv["campaigns"], vertical=vertical, bodies=bodies)
    return inv, classified, rich, cls


def emit_campaigns(pack, disc):
    try:
        inv, classified, rich, cls = _campaign_inventory(disc, pack.vertical)
    except Exception as exc:  # noqa: BLE001
        pack.notes.append(f"22_inventaire_campagnes: not emitted ({exc})")
        return
    if not classified:
        return

    stats = inv.get("stats") or {}

    # Typology counted over the campaigns this document actually lists. `classify`
    # returns its own `summary`, but it only sees push: on an account with in-app
    # CTA-only campaigns its three counts do not add up to the inventory total, and an
    # overview whose parts contradict its own total is read as a data error.
    typology = {}
    for c in classified:
        t = (rich.get(c.get("key")) or {}).get("type") or c.get("type") or "ambiguous"
        typology[t] = typology.get(t, 0) + 1

    body = [T(pack.lang,
              fr="Inventaire canonique des campagnes, tous canaux. La typologie "
                 "(one-shot vs automatisé/récurrent) est une **heuristique Reports-only** "
                 "reconstruite depuis `group_id` et la cadence des noms : "
                 "`/api/pipelines` et `/api/schedules` sont hors périmètre. Chaque "
                 "rattachement à un pilier porte sa propre fiabilité.",
              en="Canonical multi-channel campaign inventory. Typology is a "
                 "**Reports-only heuristic** from `group_id` and name cadence."),
           "",
           H("Vue d'ensemble"), "",
           table(["Indicateur", "Valeur"],
                 [(L("Campagnes au total"), stats.get("total")),
                  (L("Fondées sur un message"), stats.get("message_based")),
                  (L("Signal CTA seul (in-app / Message Center)"), stats.get("cta_only")),
                  (L("One-shot"), typology.get("one_shot", 0)),
                  (L("Automatisées / récurrentes"),
                   typology.get("automated_recurring", 0)),
                  (L("Ambiguës"), typology.get("ambiguous", 0))]), ""]

    # The heuristic reads occurrences of a message name inside the window. On a grouped
    # firehose it therefore finds almost no "automated" campaign, while `pergroup` shows
    # a programme layer carrying the entire volume. Both are true of different objects —
    # a resolved message seen once, and a programme aggregating billions of sends — but
    # side by side and unexplained they read as one of the two being broken.
    n_programs = len([g for g in (disc["data"].get("pergroup") or {}) if g])
    if n_programs and not typology.get("automated_recurring"):
        body += [T(pack.lang,
                   fr=f"> **Zéro campagne classée « automatisée » ne veut pas dire zéro "
                      f"automatisation.** Le compte porte {n_programs} programmes "
                      f"(`23_programmes_automatises.md`), qui portent l'essentiel du "
                      f"volume. La typologie ci-dessus compte les **occurrences d'un nom "
                      f"de message résolu dans la fenêtre** ; un programme dont les "
                      f"messages ne sont pas résolus individuellement n'y apparaît pas. "
                      f"Pour juger l'automatisation, lisez `23`, pas ce tableau.",
                   en=f"> **Zero campaigns classified as automated does not mean zero "
                      f"automation.** The account carries {n_programs} programmes "
                      f"(`23_programmes_automatises.md`), which carry most of the volume. "
                      f"The typology above counts **occurrences of a resolved message "
                      f"name inside the window**; a programme whose messages are not "
                      f"individually resolved does not appear in it."),
                 ""]

    by_channel = stats.get("by_channel") or {}
    if by_channel:
        body += [H("Par canal"), "",
                 table(["Canal", "Campagnes", "Envois"],
                       [(c, v.get("campaigns"), fmt_int(v.get("sends")))
                        for c, v in sorted(by_channel.items())]), ""]

    body += [H("Métriques canoniques"), "",
             metric_bullet(pack, disc, "campaigns_push",
                           local=(by_channel.get("push") or {}).get("campaigns")),
             metric_bullet(pack, disc, "campaigns_email",
                           local=(by_channel.get("email") or {}).get("campaigns")),
             ""]

    rows = []
    for c in classified:
        r = rich.get(c.get("key")) or {}
        p = c.get("purpose") or {}
        rows.append((
            c.get("label") or T(pack.lang, fr="(sans nom)", en="(unnamed)"),
            c.get("channel"),
            c.get("source"),
            r.get("type") or c.get("type"),
            r.get("occurrences"),
            r.get("cadence"),
            fmt_int(c.get("total_sends")),
            fmt_int(r.get("total_direct_responses")),
            r.get("first_seen"),
            r.get("last_seen"),
            p.get("pillar"),
            p.get("lever"),
            p.get("confidence"),
            p.get("reliability"),
        ))
    annex = Annex("90_annexe_inventaire_campagnes.md",
                  T(pack.lang, fr="Annexe — inventaire complet des campagnes",
                    en="Annex - full campaign inventory"),
                  provenance("responses.json + activity.json fusionnés · "
                             "classify_campaigns · campaign_inventory · "
                             "campaign_purpose · events.json"))
    annex.section(H("Inventaire détaillé"),
                  ["Campagne", "canal", "source", "typologie", "occurrences",
                   "cadence", "envois", "réponses directes", "première vue",
                   "dernière vue", "pilier", "levier", "confiance", "fiabilité"],
                  rows)
    body += annex.emit(pack)

    pack.add("22_inventaire_campagnes.md",
             T(pack.lang, fr="Inventaire des campagnes", en="Campaign inventory"),
             3, "\n".join(body),
             provenance("responses.json + activity.json fusionnés · classify_campaigns "
                        "· campaign_inventory · campaign_purpose · events.json"))


def emit_programs(pack, disc):
    d = disc["data"]
    pergroup = d.get("pergroup") or {}
    if not isinstance(pergroup, dict) or not pergroup:
        return

    rows = []
    for gid, info in pergroup.items():
        if not isinstance(info, dict):
            continue
        rows.append((gid, fmt_int(info.get("sends")),
                     fmt_int(info.get("direct_responses")),
                     fmt_int(info.get("influenced_responses")),
                     info.get("app_key") or ""))
    if not rows:
        return

    sends = [float((i or {}).get("sends") or 0) for i in pergroup.values()
             if isinstance(i, dict)]
    med = statistics.median(sends) if sends else 0

    body = [T(pack.lang,
              fr="Agrégats **par programme** (`pergroup/detail`). Sur un compte dense, "
                 "c'est ici que vit le volume réel des automatisations : un `group_id` "
                 "agrège tout le programme, et sommer ses pushs individuels donnerait un "
                 "autre chiffre. Les totaux d'un programme sont **cumulés sur sa vie**, "
                 "pas bornés à la fenêtre — voir `11_perimetre_et_couverture.md`.",
              en="**Per-programme** aggregates. A `group_id` aggregates the whole "
                 "programme; its totals are lifetime, not window-bounded."),
           "",
           T(pack.lang,
             fr=f"{len(rows)} programme(s) · envois médians par programme : "
                f"{fmt_int(med)}.",
             en=f"{len(rows)} programme(s) · median sends per programme: "
                f"{fmt_int(med)}."),
           "",
           ]

    prog = d.get("program_volume") or {}
    if prog:
        prows, pprose = kv_rows(prog)
        body += [H("Part dans le volume de la fenêtre"), "",
                 table(["Champ", "Valeur"], prows), ""]
        body += [f"> **{k}** — {v}\n" for k, v in pprose]

    annex = Annex("95_annexe_programmes.md",
                  T(pack.lang, fr="Annexe — tous les programmes, un par ligne",
                    en="Annex - every programme, one per row"),
                  provenance("pergroup.json · groups_decoded.json"))
    annex.section(H("Programmes"),
                  ["Programme (group_id)", "envois", "réponses directes",
                   "réponses influencées", "app_key"], rows)

    groups_decoded = d.get("groups_decoded") or {}
    if isinstance(groups_decoded, dict) and groups_decoded:
        grows = []
        for gid, rec in groups_decoded.items():
            if not isinstance(rec, dict):
                continue
            grows.append((gid, rec.get("kind") or rec.get("type") or "",
                          ", ".join(rec.get("triggers") or []) or "",
                          rec.get("message_name") or rec.get("title") or ""))
        if grows:
            annex.section(H("Définitions décodées des programmes"),
                          ["Programme", "nature", "déclencheurs", "nom / titre"], grows)
    body += annex.emit(pack)

    pack.add("23_programmes_automatises.md",
             T(pack.lang, fr="Programmes automatisés et récurrents",
               en="Automated and recurring programmes"),
             3, "\n".join(body),
             provenance("pergroup.json · program_volume.json · groups_decoded.json"))


def emit_creatives(pack, disc):
    decoded = disc["data"].get("decoded") or {}
    if not isinstance(decoded, dict) or not decoded:
        return

    rows, undecodable = [], 0
    for pid, rec in decoded.items():
        if not isinstance(rec, dict):
            continue
        if not rec.get("decodable"):
            undecodable += 1
            continue
        rows.append((
            rec.get("message_name") or rec.get("title") or pid,
            rec.get("title"),
            (rec.get("body") or "").replace("\n", " ")[:400],
            yn(pack.lang, rec.get("media")),
            rec.get("deeplink") or "",
            yn(pack.lang, rec.get("personalization")),
            yn(pack.lang, rec.get("has_message_center")),
            yn(pack.lang, rec.get("bypass_frequency_limits")),
            ", ".join(rec.get("languages") or []),
            rec.get("audience_kind") or "",
        ))
    if not rows:
        return

    body = [T(pack.lang,
              fr="Créatives décodées depuis `perpush/pushbody`, **exhaustives** ici : la "
                 "curation à quelques aperçus est une règle du rapport, pas du pack. Le "
                 "corps est tronqué à 400 caractères pour rester lisible en récupération. "
                 "Une créative vide est normale sur un envoi UNICAST / Create-and-Send : "
                 "le payload ne porte alors que des métadonnées.",
              en="Creatives decoded from `perpush/pushbody`, exhaustive here. Bodies are "
                 "truncated to 400 characters. An empty creative is normal on a UNICAST "
                 "/ Create-and-Send message."),
           "",
           T(pack.lang,
             fr=f"{len(rows)} message(s) décodé(s)"
                + (f", {undecodable} non décodable(s)." if undecodable else "."),
             en=f"{len(rows)} message(s) decoded"
                + (f", {undecodable} undecodable." if undecodable else ".")),
           ""]

    annex = Annex("91_annexe_creatives.md",
                  T(pack.lang, fr="Annexe — créatives décodées, exhaustif",
                    en="Annex - decoded creatives, exhaustive"),
                  provenance("decoded.json (perpush/pushbody décodé)"))
    annex.section(H("Créatives"),
                  ["Message", "titre", "corps", "image", "deep-link",
                   "personnalisation", "message center",
                   "contourne les limites de fréquence", "langues",
                   "type d'audience"], rows)
    body += annex.emit(pack)

    pack.add("24_creatives_decodees.md",
             T(pack.lang, fr="Créatives décodées", en="Decoded creatives"),
             3, "\n".join(body), provenance("decoded.json (perpush/pushbody décodé)"))


# --------------------------------------------------------------------------- #
# Tier 3 — data
# --------------------------------------------------------------------------- #
def emit_data(pack, disc):
    emit_events(pack, disc)
    emit_tagging_plan(pack, disc)
    emit_benchmarks(pack, disc)
    emit_facts(pack, disc)


def emit_events(pack, disc):
    d = disc["data"]
    events = series_rows(d.get("events"), "events")
    if not events:
        return

    try:
        from campaign_inventory import split_events
        from event_analysis import analyze
        behavioural, _inapp = split_events(events)
        res = analyze(behavioural, vertical=pack.vertical, brand=pack.client)
    except Exception as exc:  # noqa: BLE001
        pack.notes.append(f"25_evenements_custom: analysis unavailable ({exc})")
        return

    totals = res.get("totals") or {}
    cur = res.get("currency") or {}
    body = [T(pack.lang,
              fr="Événements comportementaux `location:custom` uniquement — les "
                 "impressions in-app (`banner - …`), `in_app_message`, `in_app_pager` et "
                 "`ua_mcrap` sont des signaux de campagne et vivent dans "
                 "`22_inventaire_campagnes.md`. **`value` est un nombre déclaré par le "
                 "client, pas une devise garantie.**",
              en="Behavioural `location:custom` events only. **`value` is a "
                 "client-declared number, not a guaranteed currency.**"),
           "",
           H("Vue d'ensemble"), "",
           table(["Indicateur", "Valeur"],
                 [(k, v) for k, v in
                  [(L("Événements distincts"), fmt_int(totals.get("distinct_events"))),
                   (L("Occurrences totales"), fmt_int(totals.get("total_count"))),
                   (L("Somme des `value`"), fmt_int(totals.get("total_value"))),
                   (L("Événements dont `value` ressemble à un montant"),
                    fmt_int(totals.get("monetary_event_count"))),
                   (L("`value` lue comme monétaire"),
                    totals.get("value_looks_monetary")),
                   (L("Devise supposée"), cur.get("currency")),
                   (L("Confiance sur la devise"), cur.get("confidence"))]
                  # An empty right-hand cell reads as a field that failed to populate.
                  # `False` is a real answer and stays; `None` and `""` are not.
                  if v not in (None, "", "n/a")]), "",
           f"> {totals.get('value_note')}", "",
           H("Métriques canoniques"), "",
           metric_bullet(pack, disc, "events_total",
                         local=totals.get("total_count") or None),
           metric_bullet(pack, disc, "events_attributed"),
           ""]

    rows = []
    for e in res.get("events") or []:
        attr = e.get("attribution") or {}
        cls = e.get("classification") or {}
        rows.append((
            e.get("name"),
            fmt_int(e.get("total_count")),
            fmt_int((attr.get("direct") or {}).get("count")),
            fmt_int((attr.get("indirect") or {}).get("count")),
            fmt_int((attr.get("unattributed") or {}).get("count")),
            fmt_pct(e.get("attr_count_rate")) if e.get("attr_count_rate") is not None
            else "",
            fmt_num(e.get("total_value")),
            fmt_num((e.get("value_monetary") or {}).get("value_per_event")),
            cls.get("category") or "",
            cls.get("kpi_kind") or "",
            cls.get("confidence") or "",
            yn(pack.lang, (e.get("value_monetary") or {}).get("value_is_monetary")),
        ))
    annex = Annex("92_annexe_evenements.md",
                  T(pack.lang, fr="Annexe — tous les événements custom",
                    en="Annex - every custom event"),
                  provenance("events.json (location:custom) · event_analysis.analyze"))
    annex.section(H("Par événement"),
                  ["Événement", "occurrences", "direct", "indirect",
                   "non attribué", "taux d'attribution", "somme value",
                   "value / occurrence", "catégorie", "type de KPI",
                   "confiance", "value monétaire"], rows)
    body += annex.emit(pack)
    body += [T(pack.lang,
               fr="`direct` + `indirect` = attribué au push ; `non attribué` est le "
                  "comportement sans message derrière, ce qui est le cas de la majorité "
                  "de l'activité d'une app et n'est pas un échec de programme. "
                  "`value / occurrence` est ce sur quoi l'heuristique monétaire se "
                  "prononce.",
               en="`direct` + `indirect` = push-attributed; `unattributed` is behaviour "
                  "with no message behind it, which is most app activity and not a "
                  "programme failure."),
             ""]

    kpis = res.get("conversion_kpis") or []
    if kpis:
        body += [H("KPI de conversion détectés"), "",
                 data_table(["Événement", "famille", "occurrences",
                                 "value monétaire"],
                                [(k.get("name"), k.get("kpi_kind") or k.get("kind"),
                                  fmt_int(k.get("total_count")),
                                  yn(pack.lang, k.get("value_is_monetary")))
                                 for k in kpis]), ""]

    tax = res.get("taxonomy") or {}
    for bucket, label in (("by_category", "Par catégorie d'événement"),
                          ("by_kpi_kind", "Par type de KPI")):
        buckets = tax.get(bucket) or {}
        if not buckets:
            continue
        body += ["## " + L(label), "",
                 data_table(["Clé", "événements", "occurrences", "somme value"],
                                [(k, v.get("events"), fmt_int(v.get("count")),
                                  fmt_num(v.get("value")))
                                 for k, v in buckets.items() if isinstance(v, dict)]),
                 ""]

    opps = res.get("opportunities") or {}
    for name, label, cols in (
            ("send_more", "Événements recommandés pour le vertical et non détectés",
             ["custom_name", "category", "kpi_kind", "is_conversion", "carries_value",
              "description", "why"]),
            ("enrich_value", "Événements détectés qui devraient porter une valeur",
             ["name", "category", "kpi_kind", "total_count", "why"])):
        items = [i for i in (opps.get(name) or []) if isinstance(i, dict)]
        if not items:
            continue
        present = [c for c in cols if any(i.get(c) is not None for i in items)]
        body += ["## " + L(label), "",
                 data_table(present,
                                [tuple(i.get(c) for c in present) for i in items]), ""]

    pack.add("25_evenements_custom.md",
             T(pack.lang, fr="Événements custom, attribution et conversion",
               en="Custom events, attribution and conversion"),
             3, "\n".join(body),
             provenance("events.json (location:custom) · event_analysis.analyze · "
                        "event_catalog.json"))


def emit_tagging_plan(pack, disc):
    d = disc["data"]
    inventory, analysis = d.get("inventory"), d.get("analysis")
    if not inventory and not analysis:
        return

    body = [T(pack.lang,
              fr="Plan de taggage du client (audit RTDS de collecte de données), "
                 "exhaustif. **L'export compte des occurrences, pas des canaux uniques** "
                 "— aucune fréquence par utilisateur ni taux de pénétration ne peut en "
                 "être déduit. Un événement suivi sans occurrence exprime une intention "
                 "de conception, pas forcément une implémentation cassée.",
              en="The client's tagging plan (RTDS data-collection audit), exhaustive. "
                 "**The export counts occurrences, not unique channels.**"),
           "",
           T(pack.lang,
             fr="Les **valeurs d'exemple** des attributs sont publiées telles quelles "
                "(y compris les données personnelles) : le pack est destiné à un "
                "notebook interne privé, et sans échantillons la taxonomie n'est pas "
                "analysable. `--no-samples` les retire et masque e-mails et téléphones."
                if pack.include_samples else
                "Les **valeurs d'exemple** des attributs sont volontairement absentes : "
                "c'est là que vivent les données personnelles du client (adresses, "
                "numéros). Seule la forme du champ — sa nature et son nombre de valeurs "
                "distinctes — est publiée.",
             en="Attribute **sample values** are published as collected, including "
                "personal data: this pack is for a private internal notebook, and "
                "without samples the taxonomy cannot be analysed. `--no-samples` "
                "drops them and redacts emails and phones."
                if pack.include_samples else
                "Attribute **sample values** are deliberately omitted: that is where the "
                "client's personal data lives. Only the field's shape is published."),
           ""]

    if isinstance(analysis, dict):
        head, head_prose = kv_rows(analysis)
        if head:
            body += [H("Synthèse de l'analyse"), "",
                     table(["Champ", "Valeur"], head), ""]
            body += [f"> **{k}** — {v}\n" for k, v in head_prose]
        scores = analysis.get("verticalScores")
        if isinstance(scores, dict) and scores:
            body += [H("Signal de vertical (données)"), "",
                     data_table(["Vertical", "score"],
                                sorted(scores.items(), key=lambda kv: -float(kv[1] or 0))),
                     ""]

        # Intent distribution stays in the ANALYSIS document rather than the annex: it is
        # the one view of the plan that answers a strategy question ("is this taxonomy
        # built to measure conversion or only browsing"), it is six rows, and the annex
        # already carries the intent per event — so this summarises rather than duplicates.
        by_intent = analysis.get("eventsByIntent")
        if isinstance(by_intent, dict) and by_intent:
            irows = []
            for intent, items in by_intent.items():
                if not isinstance(items, list) or not items:
                    continue
                vol = sum(float((it or {}).get("total") or 0) for it in items
                          if isinstance(it, dict))
                top = max((it for it in items if isinstance(it, dict)),
                          key=lambda it: float(it.get("total") or 0), default={})
                irows.append((intent, len(items), fmt_int(vol), top.get("name") or ""))
            irows.sort(key=lambda r: -int(str(r[1])))
            total_evt = sum(int(str(r[1])) for r in irows)
            body += [H("Répartition des événements par intention"), "",
                     data_table(["Intention", "événements", "occurrences",
                                 "événement le plus volumique"], irows), "",
                     T(pack.lang,
                       fr=f"{total_evt} événements classés. L'intention est **inférée du "
                          f"nom et des propriétés**, pas déclarée par le client : elle "
                          f"situe la maturité du plan, elle ne la démontre pas. Le détail "
                          f"événement par événement, avec son intention, est dans "
                          f"`93_annexe_plan_de_taggage.md`.",
                       en=f"{total_evt} events classified. Intent is **inferred from the "
                          f"name and properties**, not declared by the client: it places "
                          f"the plan's maturity, it does not prove it. The per-event "
                          f"detail is in `93_annexe_plan_de_taggage.md`."),
                     ""]

    annex = Annex("93_annexe_plan_de_taggage.md",
                  T(pack.lang, fr="Annexe — plan de taggage, taxonomie exhaustive",
                    en="Annex - tagging plan, exhaustive taxonomy"),
                  provenance("inventory.json + analysis.json"),
                  note=T(pack.lang,
                         fr="Nomenclature technique brute. C'est la source à cocher pour "
                            "dénombrer ou déboguer (« quels attributs sont mal typés »), "
                            "et à décocher pour tout le reste — y compris pour un Audio "
                            "Overview, qu'elle rendrait illisible.",
                         en="Raw technical nomenclature. Select this source to count or "
                            "debug, deselect it for everything else — including an Audio "
                            "Overview, which it would make unlistenable."))

    # Sample values are lists, so `block` used to drop them by keeping only scalars.
    # For an internal notebook they are load-bearing (including personal data).
    sample_keys = {"sampleValues", "valueSamples", "samples", "examples"}
    keep_samples = pack.include_samples
    consumed = {"inventory": set(), "analysis": set()}

    def block(title, payload, key, preferred):
        """Declare a list of records, with columns discovered rather than assumed.

        The tagging-plan schema moves. Hard-coding column names produced a table of empty
        cells that looked like an account tracking nothing, so the preferred order is
        applied to the keys that are actually there and the rest are appended.

        A dict of lists is flattened one level: `excludedAirship` and `gaps` are keyed by
        category rather than being flat lists, and reading them as lists dropped them in
        silence.
        """
        which = "inventory" if payload is inventory else "analysis"
        consumed[which].add(key)
        items = (payload or {}).get(key)

        if isinstance(items, dict):
            for sub, sub_items in items.items():
                if isinstance(sub_items, list) and sub_items:
                    emit_rows(f"{title} — {sub}", sub_items, preferred)
            return
        emit_rows(title, items, preferred)

    def _sample_cell(value):
        """Flatten a sample list or dict into a table cell."""
        if isinstance(value, list):
            parts = []
            for item in value[:8]:
                if isinstance(item, dict):
                    parts.append(str(item.get("value", item)))
                else:
                    parts.append(str(item))
            return ", ".join(parts)
        if isinstance(value, dict):
            return str(value.get("value", value))
        return value

    def emit_rows(title, items, preferred):
        if not isinstance(items, list) or not items:
            return
        if not any(isinstance(it, dict) for it in items):
            annex.section("## " + L(title), ["Valeur"], [(it,) for it in items])
            return

        present = []
        for it in items:
            if not isinstance(it, dict):
                continue
            for k, v in it.items():
                if k in present:
                    continue
                if k in sample_keys:
                    if keep_samples:
                        present.append(k)
                    continue
                if isinstance(v, (str, int, float, bool)):
                    present.append(k)
        cols = ([c for c in preferred if c in present]
                + [c for c in present if c not in preferred])[:12]
        if not cols:
            return
        rows = []
        for it in items:
            if not isinstance(it, dict):
                continue
            rows.append(tuple(_sample_cell(it.get(c)) if c in sample_keys
                              else it.get(c) for c in cols))
        annex.section("## " + L(title), cols, rows)

    if isinstance(inventory, dict):
        block("Événements suivis", inventory, "customEvents",
              ["name", "total", "source", "properties", "present", "missing"])
        block("Attributs", inventory, "attributes",
              ["key", "normalized", "total", "distinctValues", "sampleValues",
               "actions", "sources"])
        block("Tags et groupes de tags", inventory, "tags",
              ["group", "key", "value", "added", "removed", "net"])
        block("Listes d'abonnement", inventory, "subscriptionLists",
              ["name", "total", "added", "removed"])
        block("Écrans", inventory, "screens", ["name", "total", "platforms"])
        block("Plateformes", inventory, "platforms", ["name", "total"])
        block("Données Airship exclues de l'inventaire client", inventory,
              "excludedAirship", ["key", "group", "total"])

    if isinstance(analysis, dict):
        block("Événements porteurs de valeur", analysis, "valueBearing",
              ["name", "total", "hasValue", "carriesAmount", "valueField",
               "missingValue"])
        block("Propriétés par événement", analysis, "eventProperties",
              ["name", "total", "intent", "valueField", "hasValueObject"])
        block("Écarts vs le référentiel du vertical", analysis, "gaps",
              ["name", "status", "category", "why"])
        block("Signaux de conversion", analysis, "conversionSignals",
              ["name", "intent", "total", "suggestedGoal", "suggestedGoalFr"])
        block("Attributs JSON", analysis, "jsonAttributes", ["key", "total"])

    # Anything the tagging plan carries that no block above claimed. A renamed key used
    # to vanish without trace — one account shipped a 78-event plan whose events were all
    # dropped because the emitter asked for `events` and the file said `customEvents`,
    # and the pack passed its gate looking complete. A note is not a failure, because a
    # new key is legitimately new; it is the difference between a gap you can see and a
    # gap you cannot.
    for which, payload in (("inventory", inventory), ("analysis", analysis)):
        if not isinstance(payload, dict):
            continue
        missed = sorted(k for k, v in payload.items()
                        if k not in consumed[which] and k not in sample_keys
                        and isinstance(v, (list, dict)) and v
                        and k not in ("meta", "provenance", "counts", "profile",
                                      "verticalScores", "caveats", "monetaryValue",
                                      "eventsByIntent"))
        if missed:
            pack.notes.append(
                f"26_plan_de_taggage: {which}.json carries {', '.join(missed)}, which no "
                f"block claims — a renamed key or a new one")

    body += annex.emit(pack)

    pack.add("26_plan_de_taggage.md",
             T(pack.lang, fr="Plan de taggage — taxonomie suivie",
               en="Tagging plan — tracked taxonomy"),
             3, "\n".join(body),
             provenance("inventory.json + analysis.json (parse_tagging_plan + "
                        "analyze_tagging_plan)"))


def emit_benchmarks(pack, disc):
    import json
    path = os.path.join(os.path.dirname(HERE), "benchmarks.json")
    try:
        with open(path, encoding="utf-8") as fh:
            book = json.load(fh)
    except (OSError, ValueError) as exc:
        pack.notes.append(f"27_benchmarks_secteur: benchmarks.json unreadable ({exc})")
        return

    meta = book.get("meta") or {}
    verticals = book.get("verticals") or {}
    key = None
    if pack.vertical:
        try:
            from resolve_vertical import resolve
            key = (resolve(pack.vertical) or {}).get("key")
        except Exception:  # noqa: BLE001
            key = pack.vertical if pack.vertical in verticals else None

    # The account's vertical first, then the cross-vertical baseline, then EVERY other
    # vertical in the book. An earlier version shipped only the first two, which silently
    # forbade the most useful question the notebook can answer with this material —
    # "how would this account read against media, or against travel" — since a rate is
    # only interpretable against the band of the sector it is being judged by.
    lead = [k for k in (key, "all_verticals") if k and k in verticals]
    others = [k for k in sorted(verticals) if k not in lead]
    if not lead and not others:
        return

    body = [T(pack.lang,
              fr="Bandes de percentiles du secteur. **Ce sont des bandes, pas des "
                 "objectifs**, sur un échantillon global sans découpage régional, et "
                 "toute comparaison est plafonnée à une confiance Moyenne. "
                 "`sends_per_user_month` est **par mois**.",
              en="Sector percentile bands. **Bands, not targets**, on a global sample "
                 "with no regional split. `sends_per_user_month` is **per month**."),
           "",
           T(pack.lang,
             fr=f"Le livre entier est fourni — le vertical du compte et la base "
                f"tous-verticaux ci-dessous, les {len(others)} autres verticaux en "
                f"annexe. Comparer le compte à un vertical qui n'est pas le sien est "
                f"légitime **à condition de nommer lequel** : la question « et face aux "
                f"médias ? » a une réponse, la phrase « le compte est sous la médiane » "
                f"n'en a pas sans son secteur.",
             en=f"The whole book ships — the account's vertical and the cross-vertical "
                f"baseline below, the other {len(others)} verticals in the annex. "
                f"Comparing the account to a vertical that is not its own is legitimate "
                f"**as long as which one is named**."),
           "",
           table(["Champ", "Valeur"],
                 [(L("Source"), meta.get("source")), (L("Fichier"), meta.get("file")),
                  (L("Publié"), meta.get("published")), (L("Région"), meta.get("region")),
                  (L("Importé"), meta.get("imported")),
                  (L("Vertical du compte"), key or "non résolu")]), ""]
    if meta.get("notes"):
        body += [f"> {meta['notes']}", ""]

    # Bands are stored as shares (0.475), and a `_rate` metric read next to an account
    # figure printed as "47.5%" invites a factor-100 comparison. Rendering both sides in
    # the same unit is the whole reason this document is generated rather than linked.
    def band_cell(mkey, x):
        return fmt_pct(x, 1) if mkey.endswith("_rate") else fmt_num(x, 2)

    band_heads = ["Métrique", "famille d'appareils", "p10 (bas)", "p50 (médiane)",
                  "p90 (haut)"]

    def band_rows(vkey):
        rows = []
        for mkey, split in ((verticals[vkey].get("metrics")) or {}).items():
            if not isinstance(split, dict):
                continue
            for family, band in split.items():
                if not isinstance(band, dict):
                    continue
                rows.append((mkey, family,
                             band_cell(mkey, band.get("p10")),
                             band_cell(mkey, band.get("p50")),
                             band_cell(mkey, band.get("p90"))))
        return rows

    for vkey in lead:
        label = verticals[vkey].get("label") or vkey
        body += [f"## {label} (`{vkey}`)", "",
                 data_table(band_heads, band_rows(vkey)), ""]

    annex = Annex("96_annexe_benchmarks_tous_verticaux.md",
                  T(pack.lang, fr="Annexe — bandes de benchmark, tous les verticaux",
                    en="Annex - benchmark bands, every vertical"),
                  provenance(f"benchmarks.json · {meta.get('source') or 'Airship'}"),
                  note=T(pack.lang,
                         fr="Les autres verticaux du livre, pour situer le compte face à "
                            "un secteur voisin. Les mêmes réserves qu'en tête de "
                            "`27_benchmarks_secteur.md` s'appliquent : des bandes, "
                            "pas des objectifs.",
                         en="The book's other verticals, to place the account against a "
                            "neighbouring sector. The same caveats apply: bands, not "
                            "targets."))
    for vkey in others:
        rows = band_rows(vkey)
        if rows:
            annex.section(f"## {verticals[vkey].get('label') or vkey} (`{vkey}`)",
                          band_heads, rows)
    body += annex.emit(pack)

    # The account's own figures sit in a SEPARATE table rather than in a column of the
    # bands. `facts.json` carries one blended figure per metric while the bands are split
    # by device family, so a side-by-side column would put an all-devices rate opposite
    # an iOS band and read as a comparison that has not been made.
    facts_kpi = {k.get("key"): k for k in
                 ((disc["data"].get("facts") or {}).get("kpis") or [])}
    bench_to_kpi = {"optin_rate": "optin_rate",
                    "direct_open_rate": "direct_open_rate",
                    "influenced_open_rate": "direct_open_rate",
                    "sends_per_user_month": "pressure"}
    if key and facts_kpi:
        crows = []
        for mkey, kpi_key in bench_to_kpi.items():
            kpi = facts_kpi.get(kpi_key)
            if not kpi or kpi.get("value") is None:
                continue
            val = (fmt_pct(kpi["value"]) if kpi.get("unit") == "pct"
                   else fmt_num(kpi["value"]))
            crows.append((mkey, kpi_key, val, kpi.get("source") or ""))
        if crows:
            body += [H("Valeurs du compte pour les métriques benchmarkées"), "",
                     table(["Métrique benchmark", "clé du run", "valeur du compte",
                            "chemin dans audit.json"], crows), "",
                     T(pack.lang,
                       fr="**Ces valeurs ne sont pas alignées sur les bandes ci-dessus.** "
                          "Le run publie un chiffre mélangé toutes plateformes, les bandes "
                          "sont découpées par famille d'appareils, et une comparaison "
                          "n'est légitime qu'à définition, famille et dénominateur "
                          "identiques. `sends_per_user_month` se compare à une pression "
                          "**mensuelle**. Aucun verdict n'est écrit ici : situer une "
                          "valeur dans sa bande est une lecture, pas une donnée.",
                       en="**These values are not aligned to the bands above.** The run "
                          "publishes one all-platform figure while the bands are split by "
                          "device family; a comparison is only legitimate at identical "
                          "definition, family and denominator."),
                     ""]

    pack.add("27_benchmarks_secteur.md",
             T(pack.lang, fr="Benchmarks sectoriels et position du compte",
               en="Sector benchmarks and the account's position"),
             3, "\n".join(body),
             provenance(f"benchmarks.json ({meta.get('source')}, {meta.get('published')})"
                        " + facts.json"))


def emit_facts(pack, disc):
    facts = disc["data"].get("facts")
    if not isinstance(facts, dict) or not facts.get("kpis"):
        return

    rows = []
    for k in facts["kpis"]:
        unit = k.get("unit")
        shown = (fmt_pct(k.get("value")) if unit == "pct"
                 else fmt_num(k.get("value")) if unit == "rate"
                 else fmt_int(k.get("value")))
        prior = (fmt_pct(k.get("prior")) if unit == "pct"
                 else fmt_num(k.get("prior")) if unit == "rate"
                 else fmt_int(k.get("prior"))) if k.get("prior") is not None else ""
        label = T(pack.lang, fr=k.get("label_fr") or k.get("label_en"),
                  en=k.get("label_en") or k.get("label_fr"))
        rows.append((k.get("key"), label, unit, shown,
                     prior,
                     fmt_num(k.get("delta_pct"), 1) if k.get("delta_pct") is not None
                     else "",
                     k.get("source")))
        pack.publish_metric(k.get("key"))

    body = [T(pack.lang,
              fr="Le brief numérique figé du run (`facts.json`) : les valeurs que les "
                 "sections du rapport ont citées et que sa porte de livraison a "
                 "vérifiées. **C'est la source autoritative** quand elle diverge d'un "
                 "chiffre recalculé ailleurs dans ce pack.",
              en="The run's frozen numeric brief (`facts.json`) — the authoritative "
                 "source when it disagrees with a figure recomputed elsewhere here."),
           "",
           data_table(["Clé", "libellé", "unité", "valeur", "période antérieure",
                           "variation %", "chemin dans audit.json"], rows), ""]

    withheld = facts.get("withheld") or {}
    if withheld:
        body += [H("Métriques disqualifiées par la collecte"), "",
                 T(pack.lang,
                   fr="**Ne publiez aucune de ces valeurs comme un chiffre.** La "
                      "collecte les a jugées inutilisables ; chaque entrée dit pourquoi.",
                   en="**Do not publish any of these as a figure.**"),
                 "",
                 data_table(["Métrique", "raison"],
                                list(withheld.items())
                                if isinstance(withheld, dict)
                                else [(w, "") for w in withheld]), ""]

    contamination = facts.get("window_contamination")
    if contamination:
        body += [H("Deltas qui sont des artefacts de calendrier"), "",
                 T(pack.lang,
                   fr="Une variation période-sur-période listée ici est un effet de "
                      "calendrier, pas une évolution du compte.",
                   en="A period-over-period delta listed here is a calendar artefact."),
                 "", f"```\n{contamination}\n```", ""]

    unresolved = facts.get("unresolved_kpis") or []
    if unresolved:
        body += [H("Métriques non résolues dans l'audit"), "",
                 ", ".join(f"`{u}`" for u in unresolved), ""]

    pack.add("28_kpis_consolides.md",
             T(pack.lang, fr="KPI consolidés du run", en="The run's consolidated KPIs"),
             3, "\n".join(body), provenance("facts.json (build_facts.py)"))


# --------------------------------------------------------------------------- #
# 00 — the README, written last because it lists what shipped
# --------------------------------------------------------------------------- #
ROUTING = [
    (("pression marketing, cadence, fatigue",
      "marketing pressure, cadence, fatigue"),
     "03_fiches_metriques · 21_volume_et_pression · 27_benchmarks_secteur "
     "· 94_annexe_series_quotidiennes"),
    (("permission, opt-in, taille de base",
      "permission, opt-in, base size"),
     "02_definitions_et_perimetre · 20_audience_et_permission"),
    (("quelles campagnes, one-shot ou automatisé",
      "which campaigns, one-shot or automated"),
     "01_endpoints_reports_api · 22_inventaire_campagnes · 23_programmes_automatises "
     "· 90_annexe_inventaire_campagnes · 95_annexe_programmes"),
    (("contenu et forme des messages", "message content and form"),
     "24_creatives_decodees · 91_annexe_creatives"),
    (("conversion, événements, valeur", "conversion, events, value"),
     "02_definitions_et_perimetre · 25_evenements_custom · 26_plan_de_taggage "
     "· 92_annexe_evenements"),
    (("ce que le client suit ou ne suit pas",
      "what the client does and does not track"),
     "06_referentiels_metier · 26_plan_de_taggage · 93_annexe_plan_de_taggage"),
    (("pourquoi cette recommandation, quel arbitrage a été fait",
      "why this recommendation, what trade-off was made"),
     "99_rapport_engagement"),
    (("comparaison au secteur", "comparison to the sector"),
     "05_comment_lire_les_benchmarks · 27_benchmarks_secteur "
     "· 96_annexe_benchmarks_tous_verticaux"),
    (("comparaison à un AUTRE vertical (médias, voyage, retail…)",
      "comparison to ANOTHER vertical (media, travel, retail...)"),
     "05_comment_lire_les_benchmarks · 96_annexe_benchmarks_tous_verticaux "
     "· 06_referentiels_metier"),
    (("est-ce que ce chiffre est fiable / complet",
      "is this figure reliable / complete"),
     "04_limites_et_inferences_interdites · 11_perimetre_et_couverture"),
    (("dénombrer ou lister exhaustivement", "counting or listing exhaustively"),
     "90_annexe_inventaire_campagnes · 91_annexe_creatives · 92_annexe_evenements "
     "· 93_annexe_plan_de_taggage · 94_annexe_series_quotidiennes "
     "· 95_annexe_programmes"),
]

QUESTIONS = [
    ("Quelle est la pression marketing par canal, et comment se situe-t-elle dans la "
     "bande du secteur ?",
     "What is marketing pressure per channel, and where does it sit in the sector band?"),
    ("Quels programmes automatisés portent le volume, et lesquels dérivent par rapport "
     "à leur médiane ?",
     "Which automated programmes carry the volume, and which drift against their own "
     "median?"),
    ("Quels événements de conversion sont suivis mais n'ont jamais déclenché sur la "
     "fenêtre ?",
     "Which conversion events are tracked but never fired in the window?"),
    ("Quels événements portent une valeur, et laquelle ressemble vraiment à un montant ?",
     "Which events carry a value, and which of those really looks like an amount?"),
    ("Quels leviers du référentiel sectoriel ce compte ne fait pas du tout ? En "
     "t'appuyant sur `06_referentiels_metier.md`, propose des campagnes qui les "
     "couvriraient, à taxonomie réellement suivie (`26_plan_de_taggage.md`).",
     "Which levers of the sector playbook does this account not run at all? Using "
     "`06_referentiels_metier.md`, propose campaigns that would cover them, within the "
     "taxonomy actually tracked (`26_plan_de_taggage.md`)."),
    ("Comment ce compte se lirait-il contre les bandes d'un autre vertical — médias, "
     "voyage — et qu'est-ce que cet écart dit, sachant qu'il ne s'agit pas de son "
     "secteur ?",
     "How would this account read against another vertical's bands - media, travel - "
     "and what does that gap mean, given it is not its own sector?"),
    ("Sur quels chiffres la couverture de collecte interdit-elle une conclusion ?",
     "On which figures does the collection's coverage forbid a conclusion?"),
    ("Quels canaux sont actifs sans base joignable connue ?",
     "Which channels are active with no known reachable base?"),
    ("Quelles campagnes performent le mieux par rapport à la moyenne du compte, à "
     "typologie comparable ?",
     "Which campaigns outperform the account average at comparable typology?"),
]


def _selection_guide(pack, annexes):
    """Which sources to tick for which job.

    Every document is a source that can be selected or not, and the pack is designed so
    that this is the main control the reader has. Left implicit, the default behaviour is
    "everything ticked", which is right for a counting question and wrong for the two
    others: a strategy question competes with thousands of inventory rows, and an Audio
    Overview fed raw nomenclature reads event keys aloud for ten minutes.
    """
    if not annexes:
        return []
    names = " · ".join(f"`{d.name}`" for d in sorted(annexes, key=lambda d: d.name))
    return [H("Quelles sources cocher"), "",
            T(pack.lang,
              fr=f"Les annexes 90+ ({names}) sont des sources **distinctes** exprès. "
                 f"Elles portent les inventaires exhaustifs et rien d'autre, ce qui rend "
                 f"leur sélection utile plutôt que subie :\n\n"
                 f"- **Question de stratégie** (« quels leviers ne sont pas joués ? », "
                 f"« où est le volume ? ») → **décochez les 90+**. Les documents 20-28 "
                 f"gardent la vue d'ensemble et les métriques canoniques ; les milliers "
                 f"de lignes d'inventaire ne feraient que concurrencer le raisonnement.\n"
                 f"- **Question de dénombrement ou de débogage** (« les 10 événements "
                 f"les plus volumiques », « quels attributs sont mal typés », « liste "
                 f"toutes les campagnes du pilier X ») → **cochez les 90+**. C'est la "
                 f"seule sélection qui contient les enregistrements un par un, et la "
                 f"seule qui permette une réponse exhaustive.\n"
                 f"- **Discussion des recommandations** → cochez `99` en plus. "
                 f"C'est la seule source qui conclut ; sur toute autre question elle "
                 f"court-circuite le raisonnement.\n"
                 f"- **Audio Overview / podcast** → **tier 1, 2 et 20-28 seulement**, et "
                 f"plutôt `00`, `10`, `11` et les vues d'ensemble si le résumé doit "
                 f"rester tenable. La nomenclature technique des annexes est ce qui fait "
                 f"dérailler les voix.",
              en=f"The 90+ annexes ({names}) are **separate** sources on purpose. They "
                 f"carry the exhaustive inventories and nothing else:\n\n"
                 f"- **Strategy question** → **deselect the 90+**. Documents 20-28 keep "
                 f"the overview and the canonical metrics; thousands of inventory rows "
                 f"would only compete with the reasoning.\n"
                 f"- **Counting or debugging question** (the ten events with the most "
                 f"volume, which attributes are mistyped) → **select the 90+**. It is "
                 f"the only selection holding the records one by one.\n"
                 f"- **Discussing the recommendations** → also tick `99`, the only "
                 f"source that concludes.\n"
                 f"- **Audio Overview / podcast** → **tiers 1, 2 and 20-28 only**. The "
                 f"annexes' technical nomenclature is what derails the voices."),
            ""]


def emit_readme(pack, disc):
    tiers = {1: [], 2: [], 3: [], 4: []}
    for doc in pack.docs:
        tiers.setdefault(doc.tier, []).append(doc)

    body = [T(pack.lang,
              fr=f"Bibliothèque de sources pour **{pack.client}**"
                 + (f", fenêtre {pack.window}" if pack.window else "") + ". "
                 "Elle est faite pour **creuser la donnée** du compte plutôt que pour "
                 "relire les conclusions du rapport : aucune des sources numérotées "
                 "`00` à `97` ne porte de verdict. Le rapport livré est joint à part, "
                 "en `99`, précisément pour rester décochable.",
              en=f"Source library for **{pack.client}**"
                 + (f", window {pack.window}" if pack.window else "") + ". "
                 "Built to interrogate the account's data, not to re-read the "
                 "engagement report's conclusions: none of the sources numbered `00` "
                 "to `97` carries a verdict. The delivered report ships separately, as "
                 "`99`, so that it stays deselectable."),
           "",
           T(pack.lang,
             fr="Elle est **autoportante** : elle embarque la donnée du compte, les "
                "définitions et dénominateurs qui la rendent interprétable, et les "
                "référentiels sectoriels qui rendent un écart jugeable. Il n'est pas "
                "nécessaire de connaître Airship pour l'utiliser — mais il est "
                "nécessaire de lire le tier 1 avant de conclure quoi que ce soit.",
             en="It is **self-contained**: the account's data, the definitions and "
                "denominators that make it interpretable, and the sector references that "
                "make a gap judgeable."),
           "",
           H("Ordre de lecture"), "",
           T(pack.lang,
             fr="Les numéros portent le tier. **00-06 : la sémantique** (identique d'un "
                "compte à l'autre, en anglais, langue d'origine du référentiel). "
                "**10-11 : ce qui a été mesuré et avec quelle couverture.** "
                "**20-28 : l'analyse du compte**, un document par thème. "
                "**90+ : les annexes**, les inventaires exhaustifs seuls. "
                "**99 : le rapport livré**, hors tier, la seule source qui conclut. "
                "Commencez par 02, 03 et 04 : ils évitent la quasi-totalité des erreurs "
                "de lecture.",
             en="Numbers carry the tier. **00-06: the semantics** (identical across "
                "accounts, in English). **10-11: what was measured, and how "
                "completely.** **20-28: the account's analysis**, one document per "
                "theme. **90+: the annexes**, exhaustive inventories only. "
                "**99: the delivered report**, outside the tiers, the only source that "
                "concludes. Start with 02, 03 and 04."),
           ""]

    for tier, label in ((1, "Tier 1 — sémantique et référentiels"),
                        (2, "Tier 2 — contexte du compte"),
                        (3, "Tier 3 — l'analyse du compte"),
                        (4, "Annexes 90+ — inventaires exhaustifs, à décocher"),
                        (9, "Hors tier — le rapport livré, à cocher pour en discuter")):
        docs = sorted(tiers.get(tier) or [], key=lambda d: d.name)
        if not docs:
            continue
        body += ["### " + L(label), ""]
        body += [f"- `{d.name}` — {d.title} ({fmt_int(d.words)} mots)" for d in docs]
        body += [""]
        if tier == 9:
            body += [T(pack.lang,
                       fr="C'est **la seule source du pack qui porte des conclusions**. "
                          "Elle est là pour que l'on puisse challenger une "
                          "recommandation ou retrouver l'arbitrage derrière une "
                          "préconisation. Pour toute question d'analyse, décochez-la : "
                          "un notebook à qui l'on donne les réponses les récite au lieu "
                          "de les reconstruire depuis la donnée, et c'est le "
                          "raisonnement que l'on cherche. La version de référence reste "
                          "le rapport HTML interactif.",
                       en="This is **the only source in the pack that concludes**. It is "
                          "here so a recommendation can be argued with. For any "
                          "analytical question, deselect it: a notebook given the "
                          "answers recites them instead of rebuilding them from the "
                          "data, and the rebuilding is the point. The interactive HTML "
                          "report remains the reference."),
                     ""]

    if pack.extras:
        body += ["### Annexes (pas des sources)", ""]
        body += [f"- `{name}` — {note}" for name, _text, note in pack.extras]
        body += [""]

    # Routing is filtered to what actually shipped. A table pointing at a document the
    # pack does not contain sends the notebook looking for context that is not there,
    # and it will answer from whatever it finds instead of saying so.
    stems = {d.name.rsplit(".", 1)[0] for d in pack.docs}
    routing = []
    for (fr, en), refs in ROUTING:
        candidates = [
            pack.source_name(r + ".md").rsplit(".", 1)[0]
            for r in (x.strip() for x in refs.split("·"))
        ]
        kept = [r for r in candidates if r in stems]
        if kept:
            routing.append((T(pack.lang, fr, en), " · ".join(kept)))

    body += _selection_guide(pack, tiers.get(4) or [])

    questions = []
    for fr, en in QUESTIONS:
        question = T(pack.lang, fr, en)
        refs = re.findall(r"`([^`]+\.md)`", question)
        final_refs = {pack.source_name(ref).rsplit(".", 1)[0] for ref in refs}
        # A prompt that tells the notebook to use an absent source is worse than omitting
        # the prompt: it answers from the nearest document instead of saying the required
        # taxonomy is not in this pack.
        if final_refs <= stems:
            questions.append(question)

    body += [H("Où chercher selon la question"), "",
             table(["Sujet", "Documents"], routing), "",
             H("Questions de départ"), "",
             "\n".join(f"{i}. {question}"
                       for i, question in enumerate(questions, 1)), ""]

    if pack.include_samples:
        missing = T(pack.lang,
                    fr="- **Aucune ligne d'API brute.** Le pack publie des agrégats, des "
                       "inventaires et les valeurs d'exemple du plan de taggage, pas "
                       "`data/*.json`.\n"
                       "- **Aucun verdict, aucune recommandation** dans les sources "
                       "`00` à `97`. C'est le travail du rapport d'engagement, joint à "
                       "part en `99` pour qu'il reste décochable.\n"
                       "- **Aucune donnée hors fenêtre**, sauf les agrégats par "
                       "programme, cumulés sur la vie du programme et signalés comme "
                       "tels.",
                    en="- **No raw API rows.** Aggregates, inventories and tagging-plan "
                       "sample values ship; `data/*.json` does not.\n"
                       "- **No verdict, no recommendation** in sources `00` to `97`. "
                       "That is the engagement report's job; it ships separately as "
                       "`99` so it stays deselectable.")
        privacy = T(pack.lang,
                    fr="Les valeurs d'exemple du plan de taggage (y compris e-mails et "
                       "téléphones) sont **publiées sans masquage** : le pack est "
                       "destiné à un notebook interne privé. Usage interne Airship.",
                    en="Tagging-plan sample values, including emails and phones, ship "
                       "**unredacted**: this pack is for a private internal notebook. "
                       "Internal Airship use.")
    else:
        missing = T(pack.lang,
                    fr="- **Aucun identifiant individuel** : ni `channel_id`, ni named "
                       "user, ni token d'appareil, ni adresse. Ils ne sont pas masqués, "
                       "ils ne sont pas lus — aucun émetteur ne les sélectionne.\n"
                       "- **Aucune ligne d'API brute.** Le pack publie des agrégats et "
                       "des inventaires, pas `data/*.json`.\n"
                       "- **Aucun verdict, aucune recommandation** dans les sources "
                       "`00` à `97`. C'est le travail du rapport d'engagement, joint à "
                       "part en `99` pour qu'il reste décochable.\n"
                       "- **Aucune donnée hors fenêtre**, sauf les agrégats par "
                       "programme, cumulés sur la vie du programme et signalés comme "
                       "tels.",
                    en="- **No individual identifier**: no `channel_id`, named user, "
                       "device token or address. They are not masked, they are not "
                       "read.\n"
                       "- **No raw API rows.**\n"
                       "- **No verdict, no recommendation** in sources `00` to `97`. "
                       "That is the engagement report's job; it ships separately as "
                       "`99` so it stays deselectable.")
        privacy = T(pack.lang,
                    fr=f"Le texte libre (corps de message, échantillons de valeurs) "
                       f"traverse un masquage des adresses e-mail et des numéros de "
                       f"téléphone, avec les mêmes motifs que l'audit de plan de "
                       f"taggage. Sur ce pack, "
                       f"**{sum(d.masked for d in pack.docs)} valeur(s) personnelle(s)** "
                       f"ont été masquées ; le détail par fichier est dans "
                       f"`manifest.json`. Usage interne Airship.",
                    en=f"Free text passes through an email/phone mask using the same "
                       f"patterns as the tagging-plan audit. "
                       f"**{sum(d.masked for d in pack.docs)}** personal value(s) were "
                       f"masked on this pack; see `manifest.json`. Internal Airship use.")

    body += [H("Ce qui n'est pas dans ce pack"), "",
             missing, "",
             H("Traitement des données personnelles"), "",
             privacy, ""]

    if pack.notes:
        body += [H("Notes de génération"), "",
                 "\n".join(f"- {n}" for n in pack.notes), ""]

    pack.add("00_README_pack.md",
             T(pack.lang, fr="Comment utiliser cette bibliothèque de sources",
               en="How to use this source library"),
             1, "\n".join(body), provenance("assemblé depuis le pack lui-même"))
