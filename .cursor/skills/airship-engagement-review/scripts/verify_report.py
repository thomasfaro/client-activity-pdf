#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Delivery gate for an Airship engagement-review report.

Scans a generated ``report.html`` and FAILS when the mandatory visuals are
missing — the two things that have silently gone missing in the past:

  1. Interactive charts    (Chart.js canvas + matplotlib PNG fallback)
  2. Message creatives      (decoded push / Message Center previews)
  3. Full canonical section set (no condensed / merged-away report — a report
     that ships only the strategic layer, as an early retail draft did, FAILS)

...plus a set of advisory checks. Run it before every delivery:

    python scripts/verify_report.py work/<client>/report.html

**Two tiers.** ``✗`` blocks: the report is wrong — a section is missing, a KPI has
no methodology or disagrees with ``facts.json``, a chart did not render, a CSS class
is dead. ``!`` advises: the report may be thin — how many recommendations, callouts,
charts or creatives it carries, and whether any section is short. The counts advise
rather than block because a floor that mandates a number gets satisfied by padding,
and a passing count says nothing about whether the sixth recommendation was worth
reading. Read the ``!`` lines and decide; ``--strict`` gates on them too.

Exit code is non-zero if any REQUIRED check fails, so it can be wired into a
build step. Pass ``--charts-min N`` / ``--creatives-min N`` to tune the advisory
targets, ``--sections-min N`` to tune the canonical-structure floor (blocking), or
``--allow-no-creatives`` for the rare account with genuinely nothing to decode
(a labelled illustrative/limitation creatives block is still expected).
"""
import argparse
import json
import os
import re
import sys
import unicodedata
from html import unescape as html_unescape

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


def _count(pattern, html):
    return len(re.findall(pattern, html, re.I))


# Canonical section set every full-account report must carry. Sourced from the
# single source of truth (canonical_sections.GATE_SECTIONS) so the structure a
# report ships and the structure the gate enforces never drift apart. Each entry
# is a (key, [EN/FR keyword regexes]) pair; a section is "present" if any of its
# regexes matches a `data-toc` label. Sections with genuinely unavailable data
# are still KEPT and marked N/A (so they still match here) — the gate fails only
# when a section is *missing entirely* (i.e. the report was condensed/merged).
try:
    from canonical_sections import GATE_SECTIONS as CANONICAL_SECTIONS
    from canonical_sections import CANONICAL_SECTIONS as _SPINE
    from canonical_sections import GOALS_GATE_SECTIONS as _GOALS_GATE
    from canonical_sections import GOALS_SECTIONS as _GOALS_SPINE
except Exception:  # pragma: no cover - defensive fallback if the module moves
    _SPINE = []
    _GOALS_GATE = []
    _GOALS_SPINE = []
    CANONICAL_SECTIONS = [
        ("brand_context",   [r"context|contexte|brand|marque"]),
        ("account_profile", [r"account profile|profil de compte|adoption"]),
        ("exec_summary",    [r"executive summary|synth[eè]se"]),
        ("benchmarks",      [r"benchmark|reach|port[eé]e"]),
        ("strategy",        [r"strateg|strat[eé]g|maturit|priorit"]),
        ("volume_pressure", [r"volume|pressure|pression"]),
        ("engagement",      [r"engagement|opens|ouvertures"]),
        ("permission",      [r"permission|base"]),
        ("typology",        [r"typolog"]),
        ("playbook",        [r"playbook|coverage|couverture|personaliz|personnalis"]),
        ("events",          [r"conversion|events|[eé]v[eé]nements"]),
        ("push_program",    [r"push program|programme push"]),
        ("channels_exp",    [r"experiment|exp[eé]rience|channel|canaux|creativ|cr[eé]a"]),
        ("best_practices",  [r"best.?practice|bonnes pratiques"]),
        ("recommendations", [r"recommend|recommand"]),
        ("appendix",        [r"appendix|annexe|method|m[eé]thod"]),
    ]


def canonical_check(toc_labels, gate=None):
    """Return (present_keys, missing_keys) over a gate section set."""
    present, missing = [], []
    for key, pats in (gate if gate is not None else CANONICAL_SECTIONS):
        hit = any(re.search(p, lbl, re.I) for lbl in toc_labels for p in pats)
        (present if hit else missing).append(key)
    return present, missing


def _section_html(body, id_base):
    """Concatenate the HTML of every <section id="id_base"...> (EN + FR "-fr").

    Returns "" when no such section exists. Used to run content checks scoped to a
    single canonical section (e.g. the exec summary must carry KPI bands).
    """
    out = []
    for m in re.finditer(r'<section\b[^>]*\bid="' + re.escape(id_base) + r'(?:-fr)?"',
                         body, re.I):
        start = m.start()
        end = body.find("</section>", start)
        out.append(body[start:end if end != -1 else len(body)])
    return "".join(out)


def _one_section(body, id_base):
    """Return the single EN <section id="id_base"> (not the "-fr" copy), or ""."""
    m = re.search(r'<section\b[^>]*\bid="' + re.escape(id_base) + r'"', body, re.I)
    if not m:
        return ""
    start = m.start()
    end = body.find("</section>", start)
    return body[start:end if end != -1 else len(body)]


# Minimum body words for a narrative section to not be "thin" (a section that is
# mostly a visual — table/chart/gauge/KPI band — is rich even with little prose).
_MIN_SECTION_WORDS = 45

# Canonical sections whose KPI cards / hero tiles must carry a vs-prior-period
# comparison (a coloured delta pill OR an explicit "no prior-period baseline" note).
# Keyed by HTML anchor id (see canonical_sections.py).
_KPI_CMP_SECTIONS = [
    ("summary", "Executive summary"),
    ("pressure", "Volume & pressure (\u00a74)"),
    ("engagement", "Engagement / opens (\u00a75)"),
    ("permission", "Permission & base (\u00a76)"),
    ("inapp", "In-app & Message Center (\u00a78b)"),
    ("email", "Email program (\u00a714)"),
]


def _kpi_comparison_audit(body):
    """Ensure every KPI hero tile in the KPI-comparison sections carries a
    vs-prior-period comparison. Returns a list of "id (found/cards)" shortfalls.

    A comparison marker is a delta pill (.ir-hero-delta / .ir-kpi-delta) or an explicit
    "no prior-period baseline" note (.ir-delta-na). N/A or absent sections are skipped.
    """
    short = []
    for sid, _label in _KPI_CMP_SECTIONS:
        sec = _section_html(body, sid)
        if not sec or "na-block" in sec:
            continue
        cards = _count(r"ir-hero-card", sec)
        if not cards:
            continue
        cmps = (_count(r"ir-hero-delta", sec) + _count(r"ir-delta-na", sec)
                + _count(r"ir-kpi-delta", sec))
        if cmps < cards:
            short.append(f"{sid} ({cmps}/{cards})")
    return short


def _kpi_methodology_audit(body):
    """Every computed KPI tile must expose HOW it was computed (API + formula).

    `hero_kpi_band` only renders the ⓘ methodology button when the item carries
    formula/inputs/source, so a builder that omits them ships a whole report of
    unexplained numbers and nothing complains — 90 hero tiles with zero methodology
    shipped on a telecom account before this check existed. `kpi_card` takes `formula` as a
    required kwarg, so its tiles are safe by construction; the hero band is not.

    Returns a list of "id (with/total)" shortfalls over the KPI-bearing sections.
    """
    short = []
    for m in re.finditer(r'<section[^>]*id="([^"]+)"[^>]*>', body):
        sid = m.group(1)
        sec = body[m.start():body.find("</section>", m.start())]
        if "na-block" in sec:
            continue
        tiles = _count(r'class="ir-hero-card"', sec) + _count(r'class="card ir-kpi"', sec)
        if not tiles:
            continue
        with_method = _count(r"data-ir-kpi-method=", sec)
        if with_method < tiles:
            short.append(f"{sid} ({with_method}/{tiles})")
    return short


def _orphan_methodology(body):
    """ⓘ buttons whose <template> is missing — the modal would open empty."""
    wanted = set(re.findall(r'data-ir-kpi-method="([^"]+)"', body))
    have = set(re.findall(r'<template id="([^"]+)"', body))
    return sorted(wanted - have)


# Table classes that carry the report's table STYLING. Note `ir-searchable`,
# `ir-sortable` and `ir-exportable` are behaviour hooks, not styling — the built-in
# components always pair them with `grid`, and a table carrying only those renders
# unstyled. A bare <table> has no borders, header band or zebra: the "data dumped
# outside a laid-out table" readability complaint. FRAMEWORK_CSS also ships a
# bare-<table> fallback, so this check enforces intent rather than raw output.
_TABLE_CLASSES = ("grid", "ir-strat", "ir-adoption", "ir-feature",
                  "ir-campaign-inv", "ir-matrix")


def _unstyled_tables(body):
    """Count <table> tags carrying none of the known styling classes."""
    n = 0
    for tag in re.findall(r"<table[^>]*>", body):
        m = re.search(r'class="([^"]*)"', tag)
        classes = (m.group(1).split() if m else [])
        if not any(c in _TABLE_CLASSES for c in classes):
            n += 1
    return n


def _dangling_section_refs(body, spine=None):
    """`§9` in the prose when no section is numbered 9.

    Sections are written in parallel by agents that cannot see the assembled numbering, so
    they reach for the canonical number they remember. One review shipped 31 wrong
    cross-references: nine pointed at `§9`, `§10`, `§11` and `§12`, which no section
    carries (the spine has the merged `8-10` and `11-12` instead), and the reader following
    them landed nowhere.

    Only the *impossible* references are caught here. A `§5` that should have been `§3c`
    points at a real section and is invisible to any mechanical check — `_shared.ref()`
    exists to stop that one at the source.

    Returns a sorted list of the bad numbers, or [] when the spine is unavailable (the
    fallback in this file has no numbers, and a check with no ground truth must not fail
    a report).
    """
    valid = {str(s.get("num") or "") for s in (spine or _SPINE)}
    valid.discard("")
    if not valid:
        return []
    # `§8-10` must match before `§8`, so the range alternative comes first.
    found = set(re.findall(r"\u00a7\s?(\d+(?:-\d+)?[a-z]?)", _plain(body)))
    return sorted(n for n in found if n not in valid)


def _double_escaped(body):
    """`&amp;amp;` / `&amp;euro;` — a pre-escaped string passed to a helper that escapes.

    Most report_interactive helpers take PLAIN TEXT and escape it themselves
    (`strategy_matrix`, `kpi_card`, table builders); a few take raw HTML (`note`,
    `sub_html_*`, `section(body=…)`). Feeding `&amp;` to a text-taking helper renders
    a literal "&amp;" to the reader.

    ANY named entity, not a list of five. The check used to match
    `amp|lt|gt|quot|nbsp|#\\d+`, which is the set an English report reaches for — and it
    is the wrong set to guard, because the accounts that need entities are the ones whose
    copy is not English. A German review shipped `&amp;euro;2.99/month` and
    `Str&amp;ouml;er blog` past this check, both green, and they were found by reading a
    screenshot. The failure is identical in every case (escaped twice, rendered
    literally), so the pattern is now the shape of an entity rather than an enumeration
    of the ones already seen.

    Code samples are exempt: a methodology appendix that documents the escaping contract
    has every right to print `&amp;amp;` inside `<code>`, and so does a table cell marked
    `data-verbatim`, which holds a client payload quoted exactly as stored.
    """
    prose = body
    for pat in _LINT_STRIP:
        prose = re.sub(pat, " ", prose, flags=re.I | re.S)
    return sorted(set(re.findall(
        r"&amp;(?:[A-Za-z][A-Za-z0-9]{1,31}|#\d{1,7}|#[xX][0-9A-Fa-f]{1,6});", prose)))


def _events_without_values(body):
    """A custom-events appendix that lists event NAMES but never their VALUES.

    "Event `added_to_cart` has 11 properties" is not a finding — it says nothing
    about whether the taxonomy is usable. The reader needs the collected values
    (clean enum vs free text vs empty) and whether Airship's reserved `value`
    field is populated, because that is what decides if a conversion can be
    attributed an amount. `ri.audit_event_properties_table()` renders exactly this.
    """
    # match the TABLE, not the string: the stylesheet also names both tables in its
    # column-width selectors, which would otherwise satisfy the gate on its own.
    def has(name):
        return re.search(r'<table[^>]*data-csv-name="%s"' % name, body) is not None

    return has("tracked_events") and not has("event_property_values")


# --- localisation lint ------------------------------------------------------
# Strings that have leaked into non-English reports because a shared helper had
# them hardcoded (chart legends, axis titles, tooltip suffixes, delta captions).
# Each fix landed in a shared script, so a re-leak is a regression, not a typo.
_EN_LEAKS = [
    r"\bSends\b", r"\bOpen rate\b", r"\bOpt-out rate\b", r"\bRate %",
    r"% of total", r"\bvs prior period\b", r"\bno prior-period baseline\b",
    r"\bDownload PDF\b", r"\bExpand all\b", r"\bCollapse all\b",
    # component headers/labels that shipped English because the helper took no lang=
    r"\bUnattributed\b", r"\bAttributed %", r"\bAttributed amount\b",
    r"\bOther / uncategorised\b", r"\bNo conversion KPI events\b",
    # cover footer default (cover_section called without lang=)
    r"\bprepared for the Airship account team\b",
    # tagging-plan analyzer prose (provenance storage / cadence findings)
    r"\battributes are SDK-sourced\b", r"\bNamed-user / contact identifiers\b",
    r"\bEvents: real-time\b", r"\brecommended pattern\b",
]

# Generic English-prose detector, for leaks no explicit pattern anticipated (a whole
# table rendered by a helper that took no lang=, a hand-written English label). A
# sentence of English prose is dense in these function words; French prose contains
# none of them, and short machine identifiers are excluded by the length floor.
_EN_FUNCTION_WORDS = re.compile(
    r"\b(?:the|and|with|that|from|are|were|this|these|those|which|their|between|"
    r"across|through|should|would|could|because|however|therefore|while|about|into|"
    r"over|under|also|been|being|only|such|than|then|when|where|what|does|did|has|"
    # Excluded despite being common English: "in" (matches "in-app", used verbatim in
    # French reports), "on" (a French pronoun), "point"/"note"/"plus"/"pour" (French).
    r"have|had|not|but|for|per|its|they|will|each|both|more|most|other|of|to|at|by|"
    r"available|journey|instead|every|any)\b", re.I)
_EN_PROSE_MIN_WORDS = 3     # function-word hits needed to call a fragment English
_EN_PROSE_MIN_CHARS = 40    # ignore short fragments (labels, ids, sample values)


# French words shipped without their accents, because a helper's translation was
# typed ASCII-only. They read as typos to the client, and no spellcheck runs on a
# generated report. Listed rather than derived: only words whose unaccented form is
# not itself valid French qualify, so a match is unambiguous.
# Excluded on purpose, because the unaccented spelling is a real French word and a
# match would be a false positive: collecte (la collecte), recommande (il
# recommande), integre (il integre), complete, entree, tache, interne.
_FR_MISSING_ACCENT = re.compile(
    r"\b(?:telephone|fidelite|recommandees?|debloque|proprietes|identite|"
    r"affinite|categorie|prediction|predictive|geolocalisation|proximite|"
    r"modele|frequence|periode|donnees|evenement|deja|apres|tres|reussi|"
    r"activite|derniere|generees?|reguliere|verticale mais non collecte)\b")


def _english_prose(text):
    """Sentence-ish fragments of `text` that read as English prose."""
    out = []
    for frag in re.split(r"(?<=[.!?;:])\s+|\n{2,}|\s{4,}", text):
        frag = " ".join(frag.split())
        if len(frag) < _EN_PROSE_MIN_CHARS:
            continue
        if len(_EN_FUNCTION_WORDS.findall(frag)) >= _EN_PROSE_MIN_WORDS:
            out.append(frag[:110])
    return out

# Visible-text containers whose contents are not prose and must not be linted:
# code samples, machine ids, embedded chart JSON, hidden methodology templates.
# `data-verbatim` marks any element holding raw client data — an event or attribute
# sample value, or the decoded copy of a message. Those are quoted exactly as the
# client's payload stored them: rewriting a sampled "14.00" into "14,00" would
# misreport it, and a campaign targeted at language=en is legitimately English inside
# a French report. Exempt by construction, not by accident.
_LINT_STRIP = [
    r"<script\b[^>]*>.*?</script>",
    r"<style\b[^>]*>.*?</style>",
    r"<template\b[^>]*>.*?</template>",
    r"<code\b[^>]*>.*?</code>",
    r"<pre\b[^>]*>.*?</pre>",
    r"<(\w+)\b[^>]*\sdata-verbatim[^>]*>.*?</\1>",
]


def _visible_text(chunk):
    """Strip non-prose containers, then all tags/attributes, leaving visible text."""
    for pat in _LINT_STRIP:
        chunk = re.sub(pat, " ", chunk, flags=re.I | re.S)
    chunk = re.sub(r"<[^>]+>", " ", chunk)
    chunk = re.sub(r"&[a-z#0-9]+;", " ", chunk)
    return chunk


def _lang_blocks(body):
    """Split a report into {lang: html}.

    Bilingual reports carry one ``.ir-lang`` wrapper per language. A monolingual
    report has none, so it is keyed on the document language instead — otherwise the
    whole localisation lint silently no-ops on exactly the reports that need it most
    (a monolingual FR report has no English column to fall back on, so a leak there
    ships to the client).
    """
    marks = [(m.group(1), m.start())
             for m in re.finditer(r'<div class="ir-lang" data-lang="([a-z]{2})"', body)]
    if len(marks) >= 2:
        out = {}
        for i, (lang, start) in enumerate(marks):
            end = marks[i + 1][1] if i + 1 < len(marks) else len(body)
            out[lang] = body[start:end]
        return out
    doc = re.search(r"<html[^>]*\blang=\"([a-z]{2})\"", body, re.I)
    return {doc.group(1).lower(): body} if doc else {}


def _localisation_lint(body):
    """Find English leaks, English decimal marks and unaccented French, per language.

    Returns {lang: {"leaks": [...], "decimals": [...], "accents": [...]}} for
    offending languages only; an English-only report yields nothing at all.

    All three families matter on a **monolingual** non-English report, which is now
    the default shape. It is tempting to think a leak is only meaningful next to an
    English column — it is not: an English string in a French-only report is a
    component that fell back to its English default, and there is no twin block to
    make it obvious. Never gate this on the number of languages present; ``lang`` is
    what decides, and ``_lang_blocks`` already keys a single-language document on its
    ``<html lang>``.
    """
    findings = {}
    for lang, chunk in _lang_blocks(body).items():
        if lang == "en":
            continue
        text = _visible_text(chunk)
        leaks = sorted({m.group(0) for pat in _EN_LEAKS
                        for m in re.finditer(pat, text)})
        leaks += sorted(set(_english_prose(text)) - set(leaks))[:6]
        # "3.72%" where the locale wants "3,72 %". Excluded: version/build triples
        # (17.2.1 -> trailing dot) and digits glued to letters (v3.5, ids -> leading \w).
        decimals = sorted({m.group(0) for m in re.finditer(
            r"(?<![\w.])\d{1,3}\.\d{1,2}(?![\d.])", text)})[:12]
        accents = (sorted({m.group(0) for m in _FR_MISSING_ACCENT.finditer(text)})[:8]
                   if lang == "fr" else [])
        if leaks or decimals or accents:
            findings[lang] = {"leaks": leaks, "decimals": decimals, "accents": accents}
    return findings


def _undefined_css_classes(html, body):
    """Report-builder classes used in markup but defined in no <style> block.

    An undefined layout class fails silently: `<div class="kpi-grid">` with no
    `.kpi-grid` rule simply stacks its children, and nothing warns — the bug only
    shows up if someone eyeballs the right PDF page. Likewise `note(kind="note")`
    quietly emitting a dead `.note-note`.

    Scoped to the builder's own namespace: `ir-*` belongs to the framework, which
    deliberately ships unstyled semantic hooks (`ir-adoption-matrix` for the gate,
    `ir-chart-spec` for the JSON payload, `ir-searchable` for the table JS).
    Hyphen/underscore-only, so state and single-letter utility classes stay out.
    """
    defined = set()
    for style in re.findall(r"<style[^>]*>(.*?)</style>", html, re.I | re.S):
        defined |= set(re.findall(r"\.(-?[A-Za-z_][\w-]*)", style))
    used = set()
    for attr in re.findall(r'class="([^"]*)"', body):
        used |= {c for c in attr.split() if c}
    suspicious = {c for c in used - defined
                  if ("-" in c or "_" in c) and not c.startswith("ir-")}
    return sorted(suspicious)


# A quoted string that looks like an f-string and is not one: the `f` prefix was dropped,
# so the expression prints verbatim. One reached this gate as "De quoi sont faites les
# {n(inter, lang)} interactions". Matches a call or a subscript inside braces, which no
# legitimate copy contains.
_UNFORMATTED_FSTRING = re.compile(r"\{[A-Za-z_][\w.]*\s*[(\[][^{}]*[)\]][^{}]*\}")
_TODO_WORD = re.compile(r"\bTODO\b")


def _template_text(body):
    """Scaffold text and unformatted f-strings that reached the reader.

    The scaffold ships every section wired and labelled TODO precisely so that nothing is
    forgotten — which only works if TODO arriving in the report is a failure. It was not:
    a build shipped with its §2 reading TODO and the gate reported success, because the
    checks asked whether the section was *present*, never what it said.

    Upper case and standalone, so "todo list" in English prose is not a finding.
    """
    text = _visible_text(body)
    hits = [f"an unformatted f-string: `{m}`"
            for m in sorted({m.group(0) for m in _UNFORMATTED_FSTRING.finditer(text)})[:6]]
    todos = len(_TODO_WORD.findall(text))
    if todos:
        hits.append(f"the word TODO reaches the reader, {todos} time(s)")
    return hits


# Tokens shorter than this are too common to match on: a withheld `open_rate` would fire
# on every chart mentioning "rate". Only a distinctive word earns a finding.
_WITHHELD_TOKEN_MIN = 6


def _withheld_in_chart_labels(body, facts):
    """Charts that put a withheld metric back on screen under a different name.

    A metric is withheld because the review decided it cannot be published — usually a
    counter that means something other than what its name suggests. The prose then avoids
    it, the appendix explains the refusal, and a chart re-publishes it anyway in a dataset
    label, because the chart was built from a different function that still accepted the
    argument. That shipped: a programme ranking labelled "Influenced X%" carrying exactly
    the `influenced_rate` the same report had refused two sections earlier.

    Read from the spec JSON rather than the rendered page, because that is where a chart's
    chrome lives; `_localisation_lint` strips <script> blocks and never sees any of it.
    """
    rows = (facts or {}).get("withheld") or []
    if isinstance(rows, dict):
        rows = [dict(v or {}, metric=k) for k, v in rows.items()]
    # EVERY distinctive word of the metric key has to appear, not just one of them. A
    # single shared word is not a match: `residual_identity` withholds what the residual
    # messages ARE, while the chart series "Residual (never returned per message)" plots
    # how MUCH residual there is — a publishable figure whose label states the very
    # limitation the entry records. Matching on "residual" alone failed that chart.
    wanted = []
    for row in rows:
        toks = {t for t in re.split(r"[^a-z]+", str(row.get("metric") or "").lower())
                if len(t) >= _WITHHELD_TOKEN_MIN}
        if toks:
            wanted.append((toks, row.get("metric")))
    if not wanted:
        return []

    hits = []
    for cid, payload in re.findall(
            r'<script[^>]*\bclass="[^"]*\bir-chart-spec\b[^"]*"[^>]*\bid="spec-([^"]+)"'
            r'[^>]*>(.*?)</script>', body, re.S):
        try:
            spec = json.loads(payload.strip())
        except ValueError:
            continue
        chrome = []
        for ds in (spec.get("data") or {}).get("datasets") or []:
            chrome.append(ds.get("label"))
        opts = spec.get("options") or {}
        for sc in (opts.get("scales") or {}).values():
            chrome.append(((sc or {}).get("title") or {}).get("text"))
        for pl in (opts.get("plugins") or {}).values():
            if isinstance(pl, dict):
                chrome.append((pl.get("title") or {}).get("text"))
        for label in [c for c in chrome if isinstance(c, str)]:
            words = set(re.split(r"[^a-z]+", label.lower()))
            for toks, metric in wanted:
                if toks <= words:
                    hits.append((re.sub(r"_fr$", "", cid), label, metric))
    # One finding per chart/metric pair; the FR twin of a chart is the same chart.
    return sorted(set(hits))


def _reco_items(reco_sec):
    """How many recommendations §16 actually carries, whatever shape it was built in.

    This counted `<li>` and nothing else, which measured the markup rather than the work:
    a §16 built as the action-plan table plus one card per recommendation — the richest
    shape the skill offers, and the one it now ships by default — scored zero and failed
    the floor, while a section of six one-line bullets passed. Two reviews spent the
    gate-fix loop arguing with that.

    The three shapes are counted and the largest wins, rather than summed: a plan table
    that restates the cards above it is one set of recommendations presented twice.
    """
    plan_rows = 0
    for tbl in re.findall(r'<table[^>]*\bdata-ir-action-plan="1"[^>]*>(.*?)</table>',
                          reco_sec, re.S):
        plan_rows = max(plan_rows, _count(r"<tr\b", re.sub(r"<thead.*?</thead>", "",
                                                           tbl, flags=re.S)))
    cards = _count(r'class="[^"]*\breco-head\b|class="[^"]*\breco-card\b', reco_sec)
    return max(_count(r"<li\b", reco_sec), plan_rows, cards)


def _density(body, spine=None):
    """Per-section depth audit over the EN copies of non-optional canonical sections.

    Returns (thin_keys, reco_items, insight_blocks). A section is "thin" only when it
    carries < _MIN_SECTION_WORDS words AND no visual (table/chart/creative/gauge/KPI
    band/strategy grid). Legit N/A sections (with a .na-block) are never thin.

    ``spine`` is the section list the report was built from. It has to follow the
    profile: walking the full spine over a goals report would check the handful of
    ids the two modes share and let the six goals-only sections through unexamined.
    """
    thin = []
    for spec in (spine if spine is not None else _SPINE):
        if spec.get("optional") or spec.get("key") == "cover":
            continue
        sec = _one_section(body, spec.get("id", ""))
        if not sec or "na-block" in sec:
            continue
        txt = re.sub(r"<[^>]+>", " ", sec)
        txt = re.sub(r"&[a-z#0-9]+;", " ", txt)
        words = len([w for w in txt.split() if len(w) > 1])
        visuals = (_count(r'table[^>]*\bgrid\b', sec) + _count(r"\bir-chart\b", sec)
                   + _count(r"\bir-creative\b", sec) + _count(r'class="gauge"', sec)
                   + _count(r'class="ir-hero"', sec)
                   + _count(r"ir-pillars|ir-strat|ir-prio|ir-matwrap", sec))
        if words < _MIN_SECTION_WORDS and visuals == 0:
            thin.append(spec.get("key"))
    reco_sec = _one_section(body, "reco")
    reco_items = 99 if ("na-block" in reco_sec) else _reco_items(reco_sec)
    insight_blocks = _count(r'class="(?:verdict|note)\b', body)
    return thin, reco_items, insight_blocks


def analyze(html, spine=None):
    """Return a dict of metrics extracted from the report HTML."""
    # strip the <style> blocks so CSS selectors (e.g. ``.ir-chart{...}``) are
    # not counted as content occurrences.
    body = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.I | re.S)
    langs = _count(r'class="ir-lang"', body) or 1
    acct = _section_html(body, "adoption")
    summ = _section_html(body, "summary")
    thin, reco_items, insight_blocks = _density(body, spine)
    return {
        "langs": langs,
        "kpi_cmp_short": _kpi_comparison_audit(body),
        "kpi_method_short": _kpi_methodology_audit(body),
        "orphan_method": _orphan_methodology(body),
        "unstyled_tables": _unstyled_tables(body),
        "double_escaped": _double_escaped(body),
        "dangling_refs": _dangling_section_refs(body, spine),
        "events_no_values": _events_without_values(body),
        "l10n": _localisation_lint(body),
        "template_text": _template_text(body),
        "undefined_css": _undefined_css_classes(html, body),
        "thin_sections": thin,
        "reco_items": reco_items,
        "insight_blocks": insight_blocks,
        # canonical §2 richness (channel adoption matrix + feature-adoption scorecard)
        "adoption_matrix": _count(r"ir-adoption-matrix|channel adoption matrix|matrice d.?adoption",
                                  acct),
        "feature_table": _count(r"ir-feature-table|feature.?adoption|adoption des fonctionnalit",
                                acct),
        # canonical §3 richness (executive summary KPI hero bands)
        "exec_hero": _count(r'class="ir-hero"', summ),
        # charts: an interactive_chart() figure wraps a <canvas> + PNG <img>
        "chart_figures": _count(r'class="[^"]*\bir-chart\b', body),
        "chart_canvas": _count(r"<canvas", body),
        "chart_runtime": ("new Chart(" in html) or ("Chart(" in html and "chartjs" in html.lower())
        or _count(r"data-ir-chart", body) > 0,
        # creatives: push cards + Message Center / mobile previews
        "creative_push": _count(r"ir-creative-push", body),
        "creative_mc": _count(r"ir-creative-mc", body),
        "creative_any": _count(r"\bir-creative\b", body) + _count(r"camp-creative", body),
        # recommended extras
        "csv_buttons": _count(r"(ir-csv|Download CSV|data-ir-csv|ir-exportable)", body),
        "flightdeck": _count(r"(go\.airship|Flight Deck|flight-deck|flightdeck)", body),
        "data_appendix": _count(r"(Data appendix|Annexe data|campaign_inventory|ir-campaign-inv)", body),
        "images": _count(r"<img\b", body),
        "empty_img": _count(r'<img[^>]*src=""', body) + _count(r"<img[^>]*src=''", body),
        # canonical structure: unique EN section labels (data-toc is the EN label;
        # both the EN and FR copies of a section carry the same data-toc value).
        "toc_labels": sorted(set(re.findall(r'data-toc="([^"]+)"', body))),
        # distinct chart ids actually embedded (EN + FR canvases; FR is "<id>_fr")
        "embedded_charts": sorted({re.sub(r"_fr$", "", c)
                                   for c in re.findall(r'data-chart="([^"]+)"', body)}),
        "chart_lang": _chart_language_drift(body),
    }


# Chart chrome is English in EVERY render, so a report carries ONE chart set that both
# language columns reuse. Two failure modes are worth naming, because both shipped:
# a builder that emits a per-language spec set (the FR canvas then disagrees with the EN
# one on the same chart), and a builder that hands French strings to the spec_* label
# arguments (the FR legend then reaches an English reader). The localisation lint cannot
# see either: it strips <script> blocks, which is where the spec JSON lives.
_CHART_FR_CHROME = re.compile(
    r"\bEnvois?\b|\bOuvertures?\b|\bTaux\b|\bdestinataires?\b|\bDélivrés?\b|"
    r"\bInjectés?\b|\bClics\b|\bNon attribué|\bInfluencé|\bNombre de\b|\bPart de\b|"
    r"\bdu total\b|\bdes push\b|\bpar (?:jour|plateforme|canal|heure)\b", re.I)


def _chart_language_drift(body):
    """Charts that break the one-English-set rule: {"drift": [ids], "fr": [ids]}.

    ``drift`` are ids whose FR canvas embeds a different spec than its EN twin — the
    signature of a per-language chart build. ``fr`` are ids whose spec carries French
    chrome. Series names taken from client data (event names, CTA copy) can be French
    legitimately, so only the *chrome* keys are read: titles, axis labels, dataset
    labels and tooltip suffixes.
    """
    specs = {}
    for cid, payload in re.findall(
            r'<script[^>]*\bclass="[^"]*\bir-chart-spec\b[^"]*"[^>]*\bid="spec-([^"]+)"'
            r'[^>]*>(.*?)</script>', body, re.S):
        specs[cid] = payload.strip()
    if not specs:                       # older/other embedding shape: nothing to judge
        return {"drift": [], "fr": []}

    drift = sorted({cid[:-3] for cid in specs
                    if cid.endswith("_fr") and cid[:-3] in specs
                    and specs[cid] != specs[cid[:-3]]})

    fr = set()
    for cid, payload in specs.items():
        try:
            spec = json.loads(payload)
        except ValueError:
            continue
        chrome = []
        for ds in (spec.get("data") or {}).get("datasets") or []:
            chrome.append(ds.get("label"))
            # _extra is a flat list of tooltip suffixes on a donut, one list per point
            # on a ranking chart. Flatten either shape.
            for row in ds.get("_extra") or []:
                chrome += [row] if isinstance(row, str) else list(row or [])
        opts = spec.get("options") or {}
        for sc in (opts.get("scales") or {}).values():
            chrome.append(((sc or {}).get("title") or {}).get("text"))
        for pl in (opts.get("plugins") or {}).values():
            chrome.append(((pl or {}).get("title") or {}).get("text")
                          if isinstance(pl, dict) else None)
        if any(isinstance(c, str) and _CHART_FR_CHROME.search(c) for c in chrome):
            fr.add(re.sub(r"_fr$", "", cid))
    return {"drift": drift, "fr": sorted(fr)}


# A KPI card is `<div class="ir-kpi-val">value</div> … <div class="ir-kpi-label">label</div>`
# (and the hero band's `ir-hero-*` equivalent). Scoping the numeric check to these two
# shapes is what keeps it honest: it compares a number the report PRESENTS as a KPI, never
# a figure quoted inside prose, where a different basis is legitimate.
_KPI_CARD_RE = [
    re.compile(r'ir-kpi-val[^"]*">(?P<val>.*?)</div>.*?ir-kpi-label">(?P<label>.*?)</div>',
               re.S),
    re.compile(r'ir-hero-val">(?P<val>.*?)</div>.*?ir-hero-label">(?P<label>.*?)</div>', re.S),
]
_NUM_RE = re.compile(r"-?\d[\d\s.,\u00a0\u202f\u2009]*")
_SUFFIX = {"k": 1e3, "m": 1e6, "md": 1e9, "b": 1e9, "bn": 1e9, "g": 1e9}

# An unseparated integer that also carries a decimal place: the signature of a decimal
# formatter applied to a count. Four digits is enough to be unambiguous, because no rate,
# ratio or points difference reaches four digits before the separator.
_UNSEP_DECIMAL_RE = re.compile(r"\d{4,}[.,]\d")
# Five or more consecutive digits with nothing breaking them up. Five rather than four so
# a year is not reported, and so this never argues with a caller over "1234".
_UNSEP_RUN_RE = re.compile(r"\d{5,}")


def _illegible_kpis(body):
    """-> [(label, shown)] for KPI values a reader cannot parse at a glance.

    The gate checked at length that a KPI equals what facts.json says, and not once that
    it is READABLE. Those are different properties, and a report shipped with its single
    most-read figure rendered "12345678.0" -- the correct number, formatted by a decimal
    formatter that grouped nothing. Every value check passed, because the value was right.

    Scoped to KPI cards through the same patterns as the facts-coherence check, so a
    figure quoted inside prose (where an author may legitimately write a bare id, a year
    or a raw count) is never touched.
    """
    out = []
    for rx in _KPI_CARD_RE:
        for m in rx.finditer(body):
            shown = _plain(m.group("val"))
            label = _plain(m.group("label"))
            if not shown:
                continue
            # A ratio or a multiple is not a count and has no thousands to group.
            if "\u00d7" in shown or shown.endswith("x"):
                continue
            digits_only = re.sub(r"[^\d]", "", shown)
            if _UNSEP_DECIMAL_RE.search(shown):
                out.append((label, shown))
            elif _UNSEP_RUN_RE.search(shown) and len(digits_only) >= 5:
                out.append((label, shown))
    return out


def _plain(s):
    """Visible text of a markup fragment."""
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html_unescape(s)).strip()


def _parse_shown(text):
    """Parse a displayed KPI value -> float, or None if it isn't a number.

    Handles what the report actually prints: `1,234,567`, `1 234 567` (narrow no-break
    space, FR), `3,3 M`, `67.4%`, `67,4 %`, `€1.2M`. Ambiguity between a decimal comma
    and a thousands comma is resolved by group shape (`3,304` is thousands, `3,3` is a
    decimal), which is why this is stricter than a naive strip of separators.
    """
    if not text:
        return None
    t = text.replace("\u2212", "-")
    mult = 1.0
    tail = re.search(r"(?i)\b(md|bn|[kmgb])\b\s*$", t.strip()) or \
        re.search(r"(?i)(md|bn|[kmgb])\s*$", t.strip())
    if tail:
        mult = _SUFFIX.get(tail.group(1).lower(), 1.0)
    m = _NUM_RE.search(t)
    if not m:
        return None
    raw = re.sub(r"[\s\u00a0\u202f\u2009]", "", m.group(0)).strip(".,")
    if not raw or raw in "-":
        return None
    # decide the decimal mark from the LAST separator's group length
    last = max(raw.rfind(","), raw.rfind("."))
    if last >= 0 and len(raw) - last - 1 != 3:
        dec, raw = raw[last], raw[:last] + "." + raw[last + 1:]
        raw = raw.replace(",", "") if dec == "." else raw
        raw = re.sub(r"[.,](?=.*\.)", "", raw)
    else:
        raw = raw.replace(",", "").replace(".", "")
    try:
        return float(raw) * mult
    except ValueError:
        return None


# A trailing temporal marker, matched while its brackets are still there. Executive-summary
# count tiles are REQUIRED to carry one (see _untagged_temporal_tiles), so the label matcher
# has to see past it — otherwise adding "(période)" to a tile would silently stop
# `_facts_coherence` from checking that tile's value, trading one defect for a worse one.
#
# Only a PARENTHESISED marker is stripped. Matching the bare words would eat the tail of a
# real label: "Custom events" would fold to "custom", and the events KPI would stop matching
# its own card.
_TEMPORAL_PAREN_RE = re.compile(
    r"\s*\((?:\d+\s*(?:d|j|days?|jours?|mo|months?|mois)"
    r"|periode|period|events?|evenements?|instantanee?|snapshot"
    r"|fenetre|window|a date|aujourd'hui|today)\)\s*$")


def _norm_label(s):
    """Fold a card label to the same normal form build_facts.fold() uses."""
    s = unicodedata.normalize("NFKD", _plain(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("\u2019", "'").replace("\u2018", "'")
    s = _TEMPORAL_PAREN_RE.sub("", s).strip()
    s = re.sub(r"[^a-z0-9'/%\s-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    # drop the trailing window marker: "alerting push sent (30d)" -> "alerting push sent"
    return re.sub(r"\s*\d+\s*(d|j|days|jours|mo|months|mois)$", "", s).strip()


def _shown_tolerance(text, value):
    """How far the printed number may sit from the true one, given how it was printed.

    A card showing ``1.2M`` for 1,234,567 is correct, not wrong: it is that number to
    the precision displayed. So the tolerance is half of the last printed digit's place
    (0.05 x 1e6 = 50,000 here), not a flat percentage — which would either reject honest
    rounding or wave through a real error on a large KPI.
    """
    t = (text or "").strip()
    mult = 1.0
    tail = re.search(r"(?i)(md|bn|[kmgb])\s*%?\s*$", t)
    if tail:
        mult = _SUFFIX.get(tail.group(1).lower(), 1.0)
    m = _NUM_RE.search(t)
    decimals = 0
    if m:
        raw = re.sub(r"[\s\u00a0\u202f\u2009]", "", m.group(0))
        last = max(raw.rfind(","), raw.rfind("."))
        if last >= 0 and len(raw) - last - 1 != 3:
            decimals = len(raw) - last - 1
    return 0.5 * (10 ** -decimals) * mult * 1.02


def _facts_coherence(body, facts):
    """Every KPI card whose label names a facts.json KPI must show that KPI's number.

    This is the one cross-section check the gate has: `_kpi_methodology_audit` and friends
    verify presence and form, never that the figure in §16 is the figure from §4. It
    matters most when sections are written concurrently, but it also catches the stale
    copy-paste a sequential build produces.

    Deliberately conservative — it only complains when a card's label matches a KPI label
    EXACTLY and the displayed number matches neither the current nor the prior value.
    Returns a list of (label, shown, expected) mismatches.
    """
    matchers = []
    for k in (facts or {}).get("kpis") or []:
        for pat in k.get("label_patterns") or []:
            try:
                matchers.append((re.compile(pat), k))
            except re.error:
                continue
    if not matchers:
        return []

    bad, seen = [], set()
    for rx in _KPI_CARD_RE:
        for mt in rx.finditer(body):
            label = _norm_label(mt.group("label"))
            kpi = next((k for pat, k in matchers if pat.fullmatch(label)), None)
            if not kpi:
                continue
            text = _plain(mt.group("val"))
            shown = _parse_shown(text)
            if shown is None:
                continue
            tol = _shown_tolerance(text, shown)
            if kpi.get("unit") == "pct":
                tol = max(tol, 0.06)     # facts.json rounds rates to 2 decimals
            targets = [v for v in (kpi.get("value"), kpi.get("prior")) if v is not None]
            if any(abs(shown - t) <= tol for t in targets):
                continue
            sig = (kpi["key"], round(shown, 4))
            if sig in seen:
                continue
            seen.add(sig)
            bad.append((_plain(mt.group("label")), shown, kpi.get("value")))
    return bad


# A KPI card with its delta pill still attached. Wider than _KPI_CARD_RE on purpose: the
# pill sits AFTER the label, so the contamination check needs the tail of the card too.
_CARD_WITH_DELTA_RE = re.compile(
    r'ir-(?:kpi|hero)-label">(?P<label>.*?)</div>\s*'
    r'(?P<tail>(?:<div class="ir-kpi-delta">)?\s*<span class="ir-hero-delta[^"]*">'
    r'(?P<pill>.*?)</span>)', re.S)

# The default caption `_delta_html` writes when the caller passes no `label`. A metric whose
# level changed at the window boundary must not be published under it: "-20.7% vs prior
# period" reads as a fall in activity when the prior period contains a World Cup.
_GENERIC_DELTA_RE = re.compile(
    r"^[\u25b2\u25bc\u25ac]?\s*[+-]?[\d.,]+\s*%\s*"
    r"(vs (the )?prior period|vs p[eé]riode pr[eé]c[eé]dente|"
    r"vs la p[eé]riode pr[eé]c[eé]dente)\.?$", re.I)


def _unqualified_contaminated_deltas(body, facts):
    """Contaminated metrics published under the generic 'vs prior period' caption.

    `build_facts.detect_window_contamination` decides WHICH deltas measure a calendar
    change rather than a change in practice; this is what stops the report shipping one
    anyway. It fires only on the default caption, so any custom label — which is how an
    author names the cause — passes. Returns (label, pill, verdict) triples.
    """
    flagged = ((facts or {}).get("window_contamination") or {}).get("contaminated") or []
    matchers = []
    for rec in flagged:
        for pat in rec.get("label_patterns") or []:
            try:
                matchers.append((re.compile(pat), rec))
            except re.error:
                continue
    if not matchers:
        return []
    bad, seen = [], set()
    for mt in _CARD_WITH_DELTA_RE.finditer(body):
        label = _norm_label(mt.group("label"))
        rec = next((r for pat, r in matchers if pat.fullmatch(label)), None)
        if not rec:
            continue
        pill = _plain(mt.group("pill"))
        if not _GENERIC_DELTA_RE.match(pill):
            continue
        if rec["metric"] in seen:
            continue
        seen.add(rec["metric"])
        bad.append((_plain(mt.group("label")), pill, rec["verdict"]))
    return bad


# A gauge's worded verdict makes a claim about where the value sits in the peer band.
# Each entry is (regex over the normalised verdict text, predicate(value, p10, p50, p90)).
# Only unambiguous positional claims are listed: "healthy", "room to grow" and the like
# are judgements, not positions, and are none of the gate's business.
_BAND_CLAIMS = [
    (r"below .*(bottom|lowest) (decile|tenth)|under the (bottom|lowest) decile"
     r"|(sous|en dessous d[eu]).*d[eé]cile (bas|inf[eé]rieur)"
     r"|dans le d[eé]cile le plus (bas|faible)",
     lambda v, a, b, c: v < a, "below p10"),
    (r"(top|highest) decile|above (the )?p90|dans le d[eé]cile (haut|sup[eé]rieur)"
     r"|au-dessus d[eu] p90",
     lambda v, a, b, c: v > c, "above p90"),
    (r"above (the )?median|au-dessus de la m[eé]diane",
     lambda v, a, b, c: v > b, "above p50"),
    (r"(below|under) (the )?median|sous la m[eé]diane|en dessous de la m[eé]diane",
     lambda v, a, b, c: v < b, "below p50"),
]

_GAUGE_RE = re.compile(
    r'<div class="gauge-wrap"\s+data-g-value="(?P<v>[-\d.eE]+)"\s+'
    r'data-g-p10="(?P<p10>[-\d.eE]+)"\s+data-g-p50="(?P<p50>[-\d.eE]+)"\s+'
    r'data-g-p90="(?P<p90>[-\d.eE]+)"\s+data-g-hib="(?P<hib>[01])"'
    r'(?:\s+data-g-sample="(?P<sample>[^"]*)")?'
    r'(?:\s+data-g-n="(?P<n>\d+)")?\s*>')
_PILL_RE = re.compile(r'<span class="pill[^"]*">(.*?)</span>', re.S)

# See report_interactive.GAUGE_SAMPLE_FLOOR — kept here as a literal so the gate does not
# depend on importing the renderer.
_GAUGE_SAMPLE_FLOOR = 3


def _gauge_verdicts(body):
    """Gauge verdicts that contradict the band the same gauge draws.

    `_facts_coherence` compares KPI cards to the brief; nothing compared a *worded*
    claim to the numbers printed beside it. This is where "well below the bottom decile"
    ships directly above a row reading `2.3` against `p10 2.3`.

    Returns (verdict_text, value, p10, p50, p90, claim) for each contradiction.
    """
    bad = []
    opens = list(_GAUGE_RE.finditer(body))
    for i, mt in enumerate(opens):
        try:
            v, p10 = float(mt.group("v")), float(mt.group("p10"))
            p50, p90 = float(mt.group("p50")), float(mt.group("p90"))
        except (TypeError, ValueError):
            continue
        # Bound the search by the NEXT gauge rather than by div nesting: a gauge with no
        # verdict closes one div, one with a verdict closes two, and counting them would
        # let a verdict-less gauge borrow its neighbour's pill.
        end = opens[i + 1].start() if i + 1 < len(opens) else len(body)
        pill = _PILL_RE.search(body, mt.end(), end)
        if not pill:
            continue
        text = _norm_label(pill.group(1))
        if not text:
            continue
        for rx, holds, claim in _BAND_CLAIMS:
            if not re.search(rx, text):
                continue
            if not holds(v, p10, p50, p90):
                bad.append((_plain(pill.group(1)), v, p10, p50, p90, claim))
            break
    return bad


def _ungrounded_gauge_verdicts(body):
    """Percentile verdicts with no sample behind them, or too small a one.

    `_gauge_verdicts` catches a verdict that contradicts its own band. This catches the
    other way the same pill goes wrong: right about where the value sits, wrong to call it
    a position at all. A delivered review graded a direct open rate as top-decile off ONE
    push — the arithmetic was fine and the conclusion was about a single campaign, not
    about the account.

    Returns (verdict_text, claim, reason) per offending gauge.
    """
    bad = []
    opens = list(_GAUGE_RE.finditer(body))
    for i, mt in enumerate(opens):
        end = opens[i + 1].start() if i + 1 < len(opens) else len(body)
        pill = _PILL_RE.search(body, mt.end(), end)
        if not pill:
            continue
        text = _norm_label(pill.group(1))
        claim = next((c for rx, _h, c in _BAND_CLAIMS if re.search(rx, text)), None)
        if not claim:
            continue                      # not a positional claim — nothing to ground
        sample = mt.group("sample")
        if not sample:
            bad.append((_plain(pill.group(1))[:50], claim, "no sample stated"))
            continue
        n = mt.group("n")
        if n is not None and int(n) < _GAUGE_SAMPLE_FLOOR:
            bad.append((_plain(pill.group(1))[:50], claim,
                        f"sample of {n} (floor is {_GAUGE_SAMPLE_FLOOR})"))
    return bad


def _fmt(v):
    if v is None:
        return "—"
    return f"{v:,.0f}" if abs(v) >= 1000 and float(v).is_integer() else f"{v:,.4g}"


# Marketing pressure must be published per MONTH, the unit of the UA benchmark
# (`sends_per_user_month`). Two delivered reviews published the metric per week and per month
# respectively, concluded "pressure under control" and "far below median", and sat a factor
# of ten apart with nothing in either letting a reader bridge them.
#
# What this blocks is a sub-monthly figure published *instead of* the monthly one, not
# alongside it. On a firehose account "7 sends per opted-in device per day" is far easier to
# feel than "212 per month", and banning it outright would make the report worse to read
# while doing nothing for comparability. The requirement is that the monthly figure is
# always there to be compared — so a per-day or per-week framing is a reading aid, never the
# only statement of pressure.
#
# The send/denominator/unit shape is deliberately narrow: a campaign described as weekly
# ("push hebdo du vendredi") is a cadence, not a pressure, and tripping on it would train
# whoever runs the gate to ignore the check.
def _pressure_unit_re(units):
    return re.compile(
        r"(?:message|msg|envoi|send|push|notification)[^.<>]{0,60}?"
        r"(?:opt-?in|opted-?in|utilisateur|user|appareil|device|navigateur|browser)"
        r"[^.<>]{0,30}?(?:/|\bpar\b|\bper\b)\s*(?:" + units + r")", re.I)


_PRESSURE_SUB_MONTH_RE = _pressure_unit_re(r"semaine|week|jour\b|day\b")
_PRESSURE_MONTH_RE = _pressure_unit_re(r"mois|month")


def _weekly_pressure(body):
    """Sub-monthly pressure figures published with no monthly figure beside them."""
    txt = _plain(body)
    if _PRESSURE_MONTH_RE.search(txt):
        return []
    seen, out = set(), []
    for m in _PRESSURE_SUB_MONTH_RE.finditer(txt):
        frag = re.sub(r"\s+", " ", m.group(0)).strip()[:90]
        if frag.lower() not in seen:
            seen.add(frag.lower())
            out.append(frag)
    return out


# Markers that state which of the two a count is. Accepted in either language, and a bare
# window like "(30 j)" counts as a flow marker because it says the same thing.
_FLOW_MARK_RE = re.compile(
    r"\(\s*(?:p[ée]riode|period|events?|[ée]v[ée]nements?|window|fen[êe]tre"
    r"|\d+\s*(?:j|jours?|d|days?|mois|months?))\s*\)"
    r"|sur la p[ée]riode|over the (?:period|window)", re.I)
_SNAP_MARK_RE = re.compile(
    r"\(\s*(?:instantan[ée]e?|snapshot|[àa] date|aujourd'hui|today"
    r"|au\s+[\d./-]+)\s*\)|[àa] date du|as of\b", re.I)


def _untagged_temporal_tiles(body, facts):
    """Executive-summary count tiles that do not say whether they are a flow or a snapshot.

    The confusion this prevents is concrete. A delivered summary put "Opt-ins app
    1,234,567" three tiles above "Opt-outs 2,345,678", and read straight down it says the
    base is collapsing. It is not: the first is the opted-in base as it stands, the second
    is a count of permission events over thirty days. Two different kinds of quantity,
    nothing on either tile saying so.

    Only `count` KPIs carry a temporal class (see build_facts.KPI_TEMPORAL) and only the
    executive summary is checked — that is where tiles sit side by side with no surrounding
    prose to disambiguate them. Returns (label, expected_class) per offending tile.
    """
    matchers = []
    for k in (facts or {}).get("kpis") or []:
        if k.get("unit") != "count" or not k.get("temporal"):
            continue
        for pat in k.get("label_patterns") or []:
            try:
                matchers.append((re.compile(pat), k, k["temporal"]))
            except re.error:
                continue
    sec = _one_section(body, "summary")
    if not matchers or not sec:
        return []

    bad, seen = [], set()
    for rx in _KPI_CARD_RE:
        for mt in rx.finditer(sec):
            raw = _plain(mt.group("label"))
            label = _norm_label(mt.group("label"))
            hit = next(((k, t) for pat, k, t in matchers if pat.fullmatch(label)), None)
            if not hit:
                continue
            kpi, temporal = hit
            want = _FLOW_MARK_RE if temporal == "flow" else _SNAP_MARK_RE
            wrong = _SNAP_MARK_RE if temporal == "flow" else _FLOW_MARK_RE
            if want.search(raw) and not wrong.search(raw):
                continue
            if kpi["key"] in seen:
                continue
            seen.add(kpi["key"])
            bad.append((raw[:44], temporal))
    return bad


_TABLE_RE = re.compile(r"<table\b[^>]*>(.*?)</table>", re.I | re.S)
_TR_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.I | re.S)
_CELL_RE = re.compile(r"<t([dh])\b[^>]*>(.*?)</t\1>", re.I | re.S)
_PCT_RE = re.compile(r"\d[\d\s\u202f\u00a0.,]*\s*%")
# A basis stated inside the cell rather than in the header: "2.0% (direct)".
_BASIS_QUALIFIER_RE = re.compile(r"\(\s*(?:direct|influenc|indirect)", re.I)


def _mixed_basis_columns(body):
    """Table columns whose rate cells do not all share one attribution basis.

    A delivered review shipped a column headed "push-attributed rate" holding
    (direct+influenced)/sends on the rows where both terms existed and direct/sends on
    the rows where the influenced term was missing, marking only the latter "(direct)".
    The prose then ranked 39.6% against 18.0% as if the column were homogeneous. Both
    numbers were arithmetically right; the ranking was meaningless.

    The signature is narrow and reliable: within one column, some percentage cells carry
    a basis qualifier and others do not. A column where *every* cell is qualified is
    fine — that is a consistently labelled column — and so is one where none is, because
    then the header alone defines the basis. Returns (header, n_qualified, n_bare).
    """
    bad = []
    for tbl in _TABLE_RE.findall(body):
        rows = [_CELL_RE.findall(r) for r in _TR_RE.findall(tbl)]
        if len(rows) < 3:
            continue
        headers = [_plain(txt) for tag, txt in rows[0]] if rows else []
        width = max((len(r) for r in rows), default=0)
        for col in range(width):
            qual = bare = 0
            for cells in rows[1:]:
                if col >= len(cells):
                    continue
                txt = _plain(cells[col][1])
                if not _PCT_RE.search(txt):
                    continue
                if _BASIS_QUALIFIER_RE.search(txt):
                    qual += 1
                else:
                    bare += 1
            if qual and bare:
                head = headers[col] if col < len(headers) else f"column {col + 1}"
                bad.append((head[:60] or f"column {col + 1}", qual, bare))
    return bad


def _stale_sections(report_path):
    """Sections written before the last edit to the frozen numeric base.

    orchestration.md freezes `audit.json` before the section wave for one reason: a
    section quotes numbers, and if the base moves afterwards nobody can tell which
    quotes went stale. Mtimes make that visible for free — a section older than
    `audit.json` was written against numbers that no longer exist.

    Advisory, not blocking: a legitimate re-run of `analyze.py` that changes nothing
    still touches the file. It tells you *where to look*, which is the part that costs
    hours to work out by hand.
    """
    d = os.path.dirname(os.path.abspath(report_path))
    audit = os.path.join(d, "audit.json")
    sec_dir = os.path.join(d, "sections")
    if not (os.path.isfile(audit) and os.path.isdir(sec_dir)):
        return []
    t_audit = os.path.getmtime(audit)
    out = []
    for fn in sorted(os.listdir(sec_dir)):
        if not fn.endswith(".py") or fn.startswith("_"):
            continue
        p = os.path.join(sec_dir, fn)
        if os.path.getmtime(p) < t_audit:
            out.append((fn[:-3], (t_audit - os.path.getmtime(p)) / 60.0))
    return out


def _sibling_facts(report_path):
    """facts.json next to the report, if the build emitted one."""
    p = os.path.join(os.path.dirname(os.path.abspath(report_path)), "facts.json")
    if not os.path.isfile(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:  # noqa: BLE001 — a broken brief must not block the gate
        return None


# Kinds from `build_facts.verify_facts_against_audit` that mean the report is WRONG, as
# opposed to incompletely briefed. Replayed against five archived audits, these produced
# no findings at all, which is what makes them safe to block on rather than advise.
_FACTS_HARD_KINDS = {"value", "dead_source", "path", "stale_derived", "unknown_kpi"}


def _facts_bits(diffs, n=4):
    return "; ".join(f"[{d['kind']}] {d['key']}: {d['detail']}" for d in diffs[:n])


_COVER_WINDOW_RE = re.compile(r'data-ir-window="([^"/]*)/([^"]*)"')


def _cover_window_drift(body, report_path):
    """The window printed on the cover against the window the audit was computed over.

    Page one states the analysis period once, and nothing later in the report repeats it,
    so a reader has no way to catch it being wrong — a delivered review carried a cover
    window that did not match its own numbers. `fw.cover_period_html` emits the dates
    machine-readably for exactly this comparison.

    Returns (printed, expected) or None when there is nothing to compare — no marker (an
    older cover, hand-assembled) or no sibling audit.
    """
    m = _COVER_WINDOW_RE.search(body)
    if not m:
        return None
    ap = os.path.join(os.path.dirname(os.path.abspath(report_path)), "audit.json")
    if not os.path.isfile(ap):
        return None
    try:
        w = (json.load(open(ap, encoding="utf-8")).get("meta") or {}).get("window") or {}
    except (ValueError, OSError):
        return None
    want = (str(w.get("start") or ""), str(w.get("end") or ""))
    got = (m.group(1), m.group(2))
    if not all(want) or got == want:
        return None
    return ("\u2013".join(got), "\u2013".join(want))


_BARE_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def _identifier_labelled_rows(body):
    """Table rows whose label cell is a raw identifier -> [(uuid, rank), ...].

    A `group_id` with no composer name behind it reaches the report as its own label, so a
    top-ranked automation is presented as `1c49d054-…`. Scanned on CELL TEXT only: the same
    UUIDs appear legitimately in every Flight Deck `href`, and matching attributes would
    flag every report ever written.

    `rank` is the row's 1-based position in its table, so the caller can say whether the
    defect is in the part of the ranking anyone actually reads.

    Cells marked `data-verbatim` are skipped. That attribute means the cell holds a raw
    collected value shown exactly as the client's own data records it — a property sample
    in the data appendix, typically. Those are legitimately opaque: an `entity_id` or
    `vehicle_Id` sample IS a UUID, and telling the reader to go and rename it as though it
    were a campaign would be worse than the defect this check exists to catch.
    """
    out = []
    for tbl in re.findall(r"<table.*?</table>", body, re.S):
        # Data rows only: counting the header row would report every first-place defect as
        # sitting at rank 2.
        data_rows = [r for r in re.findall(r"<tr.*?</tr>", tbl, re.S) if "<td" in r]
        for i, row in enumerate(data_rows, start=1):
            for attrs, cell in re.findall(r"<td([^>]*)>(.*?)</td>", row, re.S):
                if "data-verbatim" in attrs:
                    continue
                txt = html_unescape(re.sub(r"<[^>]+>", "", cell)).strip()
                if _BARE_UUID_RE.match(txt):
                    out.append((txt, i))
    return out


def _inapp_volume(report_path):
    """In-app / Scene interaction volume from the sibling audit.json, or None.

    None means "cannot tell" — no audit next to the report — and the caller then leaves
    §8b optional. A zero is different from a None and says the section is a legitimate N/A.
    """
    ap = os.path.join(os.path.dirname(os.path.abspath(report_path)), "audit.json")
    if not os.path.isfile(ap):
        return None
    try:
        a = json.load(open(ap, encoding="utf-8"))
    except (ValueError, OSError):
        return None
    def num(x):
        return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None

    n = num((a.get("inapp") or {}).get("interactions"))
    if n is None:
        by_loc = ((a.get("events") or {}).get("by_location") or {})
        n = sum(num(by_loc.get(k)) or 0
                for k in ("in_app_message", "in_app_pager", "ua_mcrap"))
    return n


def _facts_vs_audit(report_path):
    """Discrepancies between the sibling facts.json and audit.json -> list, or None.

    None means "not checkable here" (a file missing, or this script running without
    `build_facts` importable) and must not be read as a pass: the gate skips the check
    rather than inventing a verdict for it.
    """
    d = os.path.dirname(os.path.abspath(report_path))
    fp, ap = os.path.join(d, "facts.json"), os.path.join(d, "audit.json")
    if not (os.path.isfile(fp) and os.path.isfile(ap)):
        return None
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from build_facts import verify_facts_against_audit
        return verify_facts_against_audit(json.load(open(ap, encoding="utf-8")),
                                          json.load(open(fp, encoding="utf-8")))
    except Exception:  # noqa: BLE001 — a broken brief must not block the gate
        return None


def _sibling_specs_ids(report_path):
    """Chart ids declared in a specs.json next to the report (base ids, no _fr).

    specs.json doubles as a small numeric store: make_charts.py writes plain
    fact entries there too (an abandonment count, a ratio) for sections to quote
    in prose. Only a `type` + `data` pair is something that can be *drawn*, so
    only that is something the report can be faulted for not embedding.
    """
    specs_path = os.path.join(os.path.dirname(os.path.abspath(report_path)), "specs.json")
    if not os.path.isfile(specs_path):
        return None
    try:
        specs = json.load(open(specs_path, encoding="utf-8"))
    except Exception:
        return None
    return sorted({re.sub(r"_fr$", "", k) for k, v in specs.items()
                   if isinstance(v, dict) and "type" in v and "data" in v})


# Aggregated specs whose dataset should total a window KPI, mapped to the facts.json key(s)
# they must agree with. Only single-dataset composition charts qualify: a trend chart
# legitimately spans the doubled window, and a ranking is a subset by design.
#
# A tuple means the spec spans several channels and must total their SUM. Without that,
# an account with a live second channel failed the check for being correct: a push-versus-
# email donut totals push + email by construction, and pinning it to push alone reported a
# x1.29 drift that was the email programme.
_SPEC_TOTAL_KPIS = {
    "channel_mix": "push_sends",                       # push composition (by platform)
    "channel_split": ("push_sends", "email_sends"),    # push vs email, when email is live
}

# Which KPI a slice of a channel chart is made of, matched against the slice's own label.
# The fixed map above assumes `channel_mix` is push-only, which is true only when the
# account sends push alone. On an account with a live email programme the builder adds an
# Email slice, and the total then legitimately exceeds `push_sends` — measured once at
# x1.70, which the check reported as a doubled period. Reading the labels costs nothing
# and cannot go stale the way a hardcoded map does.
_SLICE_KPIS = (
    (re.compile(r"\bemail\b|courriel", re.I), "email_sends"),
    (re.compile(r"\bsms\b", re.I), "sms_sends"),
    (re.compile(r"in.?app", re.I), "inapp_displays"),
    (re.compile(r"push|notification", re.I), "push_sends"),
)


def _expected_from_labels(spec, kpis):
    """The KPIs a spec's slices actually name, or None if the labels don't resolve.

    Returns a (total, key_description) pair. Falls back to None so the caller keeps the
    hardcoded expectation rather than skipping the check.
    """
    labels = [str(x) for x in ((spec.get("data") or {}).get("labels") or [])]
    if not labels:
        return None
    keys = []
    for lab in labels:
        for rx, key in _SLICE_KPIS:
            if rx.search(lab):
                if key not in keys:
                    keys.append(key)
                break
        else:
            return None                    # an unrecognised slice: don't guess a total
    parts = [(kpis.get(k) or {}).get("value") for k in keys]
    if not keys or not all(isinstance(p, (int, float)) for p in parts):
        return None
    return sum(parts), " + ".join(keys)


def _spec_total_drift(report_path, facts, tol=0.02):
    """Aggregated specs whose total contradicts facts.json. Returns a list of strings.

    The daily series are pulled over `current + prior`, so a spec that collapses one to a
    single total and forgets to slice silently doubles the period. It is invisible to every
    other check: the chart renders, its shape is right, and no label is wrong — only the
    magnitude is, by almost exactly 2x. Measured once: a channel-mix donut totalling 86.25M
    under a "(30d)" title against 39.1M on every KPI of the same report.
    """
    specs_path = os.path.join(os.path.dirname(os.path.abspath(report_path)), "specs.json")
    if not (facts and os.path.isfile(specs_path)):
        return []
    try:
        specs = json.load(open(specs_path, encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    kpis = {k["key"]: k for k in (facts.get("kpis") or []) if isinstance(k, dict)}
    out = []
    for spec_id, kpi_key in _SPEC_TOTAL_KPIS.items():
        spec = specs.get(spec_id)
        keys = (kpi_key,) if isinstance(kpi_key, str) else tuple(kpi_key)
        parts = [(kpis.get(k) or {}).get("value") for k in keys]
        expected = (sum(p for p in parts if isinstance(p, (int, float)))
                    if all(isinstance(p, (int, float)) for p in parts) else None)
        kpi_key = " + ".join(keys)
        if not isinstance(spec, dict):
            continue
        from_labels = _expected_from_labels(spec, kpis)
        if from_labels:
            expected, kpi_key = from_labels
        if not isinstance(expected, (int, float)) or not expected:
            continue
        datasets = ((spec.get("data") or {}).get("datasets") or [])
        if len(datasets) != 1:
            continue
        vals = [v for v in (datasets[0].get("data") or []) if isinstance(v, (int, float))]
        if not vals:
            continue
        total = sum(vals)
        if abs(total - expected) / expected > tol:
            ratio = total / expected
            out.append(
                f"spec '{spec_id}' totals {total:,.0f} but facts.json '{kpi_key}' is "
                f"{expected:,.0f} (x{ratio:.2f})"
                + (" — that is the doubled window: slice the current period before "
                   "summing" if 1.7 <= ratio <= 2.3 else ""))
    return out


def run(path, charts_min, creatives_min, allow_no_creatives, sections_min,
        profile="full", strict=False):
    """Gate one report. ``profile`` picks which contract applies.

    "goals" is the light conversion review: one language, no Reports API, no
    campaign inventory, no PDF. The checks that presuppose those inputs — channel
    adoption, feature scorecard, prior-period deltas, creatives, the translation
    lint — are not relaxed standards, they are questions the mode cannot be asked.
    Everything that measures whether the report is *readable and auditable* still
    applies unchanged.

    Two tiers, and the split is deliberate. **Blocking** means the report is wrong:
    a missing section, a KPI with no methodology, a KPI that disagrees with
    `facts.json`, a chart or creative that did not render, a dead CSS class. Those
    are facts about the artefact and no human judgement improves them.
    **Advisory** (``!``) means the report may be thin: the volume floors — how many
    recommendations, how many callouts, how many charts, how long a section is.

    Why the floors advise rather than block. Re-running this gate over 13 delivered
    accounts, they almost never fired: recommendations depth once, insight density
    once, thin sections not at all. A check that never blocks costs no wall-clock,
    so demoting it saves no time — the reason is the other direction. A floor that
    mandates a count shapes the output *before* it runs: six recommendations get
    written because six are required, and a passing gate then says nothing about
    whether the sixth was worth reading. That judgement belongs to whoever signs the
    report off. ``strict=True`` puts them back in the blocking tier, which is what a
    flagship deliverable should be gated on.
    """
    goals = (profile == "goals")
    try:
        html = open(path, encoding="utf-8").read()
    except OSError as e:
        print(f"  ✗ cannot read {path}: {e}")
        return False

    m = analyze(html, spine=_GOALS_SPINE if goals else None)
    per_lang_charts = m["chart_figures"] / max(m["langs"], 1)
    per_lang_creatives = m["creative_any"] / max(m["langs"], 1)
    n_sections = len(m["toc_labels"])
    present, missing = canonical_check(m["toc_labels"], _GOALS_GATE if goals else None)

    required = []   # (ok, label, detail) — the report is wrong; blocks delivery
    recommended = []  # the report may be thin; printed as `!`, never blocks
    # Where the volume floors land. See the docstring: they advise by default so the
    # gate stops manufacturing padding, and block under --strict.
    floor = required if strict else recommended

    # ---- REQUIRED: the report says how it was produced ----
    # A document whose commentary was drafted by a model has to say so, even circulating
    # internally: it is Airship's own commitment that AI involvement is marked, and the
    # footer is generated for free from the run manifest. Absent means the builder
    # bypassed write_report, which is also worth knowing.
    required.append(("ir-provenance" in html, "Provenance footer",
                     "the report does not state how it was produced. "
                     "Fix: build through rf.write_report(), which injects the footer "
                     "from work/<client>/run.md (rf.with_provenance)."))

    # ---- REQUIRED: every page is marked internal-use ----
    # The marking is what makes a page safe to detach: this report is preparation for
    # the account team, and a chart pasted into a deck should still say so. The cover
    # carried it alone until a per-page rule was added, so the check looks for the
    # custom property assemble() declares rather than for the cover text.
    required.append(("--ir-internal" in html, "Internal-use marking",
                     "no per-page internal-use marking. "
                     "Fix: assemble through rf.assemble(), which declares "
                     "--ir-internal (rf.internal_css) for the .page rule to print."))

    # ---- REQUIRED: full canonical structure (not a condensed report) ----
    # No tolerance. This used to allow one missing gated section, and that slack had no
    # justification to protect: a section whose data is genuinely unavailable is KEPT and
    # marked N/A, so it still matches here (see the CANONICAL_SECTIONS note above). One
    # section of slack therefore only ever licensed a condensed report — and a reviewer
    # comparing four accounts found four different documents, which is the cost. Two
    # accounts have to answer the same questions in the same order to be comparable at all.
    structure_ok = (n_sections >= sections_min) and not missing
    required.append((structure_ok, "Full canonical section set",
                     f"{n_sections} sections (need >= {sections_min}); "
                     f"missing canonical: {', '.join(missing) or 'none'}. "
                     f"Fix: keep the FULL structure (mirror the reference builders) — "
                     f"do NOT condense/merge; keep unavailable sections and mark them N/A "
                     f"(an N/A section still counts as present)."))

    # ---- REQUIRED: canonical §2 adoption components (never drop these) ----
    if not goals:
        required.append((m["adoption_matrix"] > 0, "Channel adoption matrix (\u00a72)",
                         "no channel-adoption matrix found in the account-profile section. "
                         "Fix: render ri.channel_adoption_matrix(rows, lang) in the account_profile renderer."))
        required.append((m["feature_table"] > 0, "Feature-adoption scorecard (\u00a72)",
                         "no feature-adoption scorecard found in the account-profile section. "
                         "Fix: render ri.feature_adoption_table(rows, lang) in the account_profile renderer."))

    # ---- REQUIRED: exec summary carries KPI hero bands (not a thin summary) ----
    exec_min = (1 if goals else 3) * max(m["langs"], 1)
    required.append((m["exec_hero"] >= exec_min, "Executive summary KPI bands",
                     f"{m['exec_hero']} hero KPI band(s) in the exec summary — need >= {exec_min} "
                     f"(3 per language: audience / usage-vs-prior / value-&-pressure). "
                     f"Fix: add 3 ri.hero_kpi_band(...) blocks (with prior-period deltas) to exec_summary."))

    # ---- REQUIRED: prior-period comparison on KPI cards (additive) ----
    # Not asked of the goals profile: a tagging-plan audit is a single snapshot,
    # so there is no earlier period to compare a card against.
    if not goals:
        required.append((not m["kpi_cmp_short"], "Prior-period comparison on KPI cards",
                     f"KPI cards missing a vs-prior-period comparison in: "
                         f"{', '.join(m['kpi_cmp_short'])}. Every hero/KPI tile in the exec "
                         f"summary and \u00a74/5/6/8b/14 must carry a delta pill or an explicit "
                         f"'no prior-period baseline' note. Fix: pass delta/delta_good (or "
                         f"no_baseline=True) to each ri.hero_kpi_band(...) / ri.kpi_card(...) item."))

    # ---- REQUIRED: every computed KPI explains itself ----
    required.append((not m["kpi_method_short"], "KPI methodology on every computed KPI",
                     f"KPI tiles with no 'how it's computed' methodology in: "
                     f"{', '.join(m['kpi_method_short'])}. A reader cannot audit a number "
                     f"they can't trace. Fix: give every ri.hero_kpi_band(...) item and "
                     f"ri.kpi_card(...) a formula= (the calculation) AND source= (the "
                     f"Reports API endpoint it came from); add inputs=/sample=/confidence= "
                     f"where they clarify."))
    required.append((not m["orphan_method"], "No orphan methodology buttons",
                     f"{len(m['orphan_method'])} \u24d8 button(s) reference a missing "
                     f"<template>: {', '.join(m['orphan_method'][:5])} — the modal opens empty."))

    # ---- REQUIRED: tabular data uses the report's table styling ----
    required.append((m["unstyled_tables"] == 0, "All tables use the report table styling",
                     f"{m['unstyled_tables']} bare <table> tag(s) with none of "
                     f"{'/'.join(_TABLE_CLASSES[:3])}…: they render with no header band, "
                     f"borders or zebra, which is the 'data shown outside a laid-out table' "
                     f"readability problem. Fix: use <table class=\"grid\"> (or a component "
                     f"helper) for every data table."))

    # ---- REQUIRED: no double-escaped HTML entities ----
    required.append((not m["double_escaped"], "No double-escaped HTML entities",
                     f"found {', '.join(m['double_escaped'][:5])} — a pre-escaped string was "
                     f"passed to a helper that escapes its own input, so the reader sees a "
                     f"literal '&amp;'. Fix: pass PLAIN TEXT ('Service & transactional') to "
                     f"text-taking helpers (strategy_matrix, kpi_card, hero_kpi_band labels, "
                     f"table cells); reserve entities for the raw-HTML ones (note(), "
                     f"sub_html_*, section(body=…))."))

    # ---- REQUIRED: every §n cross-reference points at a section that exists ----
    required.append((not m["dangling_refs"],
                     "Cross-references point at real sections",
                     "the prose cites "
                     + ", ".join("\u00a7" + n for n in m["dangling_refs"][:6])
                     + ", and no section carries that number — the reader following the "
                     "reference lands nowhere. Sections are written in parallel by agents "
                     "that cannot see the assembled numbering, so a hand-typed number is a "
                     "guess. Fix: use _shared.ref('<canonical_key>') instead, which "
                     "resolves the number from canonical_sections and raises on a bad key."))

    # ---- REQUIRED: the events appendix shows collected VALUES, not just names ----
    required.append((not m["events_no_values"],
                     "Custom-events appendix carries value samples",
                     "the report lists tracked custom events but never their collected "
                     "values: no event_property_values table. Property NAMES alone cannot "
                     "show whether a taxonomy is usable (clean enum vs free text), nor "
                     "whether the reserved `value` field is populated — which is what "
                     "decides if a conversion can be attributed an amount. Fix: add "
                     "ri.audit_event_properties_table(AUDIT, lang=lang) next to "
                     "ri.audit_events_table(...) in the data appendix."))

    # ---- FLOOR: section depth (no thin narrative sections) ----
    floor.append((not m["thin_sections"], "Section depth (no thin sections)",
                  f"thin sections: {', '.join(m['thin_sections'])} — each has < {_MIN_SECTION_WORDS} "
                  f"words and no table/chart/creative/gauge/KPI band. Fix: add real analysis "
                  f"(prose + a verdict/note + a visual), or mark the section N/A with a reason."))

    # ---- FLOOR: recommendations depth ----
    floor.append((m["reco_items"] >= 6, "Recommendations depth",
                  f"{m['reco_items']} recommendation items — 6+ concrete, brand-tailored "
                  f"recommendations (grouped by pillar) is the target. Six thin ones are "
                  f"worse than three that land: expand the renderer only if there is "
                  f"something to say."))

    # ---- FLOOR: insight density (verdicts / callout notes across the report) ----
    insight_min = 6
    floor.append((m["insight_blocks"] >= insight_min, "Insight density (verdicts / notes)",
                  f"{m['insight_blocks']} verdict/note callouts — {insight_min}+ is the target. "
                  f"Fix: give each major section a <div class=\"verdict\"> takeaway or a note."))

    # ---- REQUIRED: charts actually rendered (a chart that did not render is a bug) ----
    # How MANY charts a report carries is a judgement (see the Chart count floor
    # below); that it carries none, or carries figures that never became canvases,
    # is not — both mean the reader sees no chart where the builder intended one.
    required.append((m["chart_canvas"] > 0, "Interactive charts render",
                     (f"{m['chart_figures']} chart figures but no canvas — the charts "
                      f"did not render. Fix: pass include_charts=True to "
                      f"interactive_head()." if m["chart_figures"] else
                      "no charts at all. Fix: run make_charts.py, then embed them with "
                      "fw.chart(); a full review without a single chart is not one.")))

    # ---- FLOOR: how many charts ----
    floor.append((m["chart_figures"] >= charts_min, "Chart count",
                  f"{m['chart_figures']} chart figures ({per_lang_charts:.0f}/lang) — "
                  f"{charts_min}+ is the target for a full review."))
    if m["chart_figures"]:
        required.append((m["chart_runtime"], "Chart.js runtime inlined",
                         "no Chart.js mount found — pass include_charts=True to interactive_head()."))

    # ---- REQUIRED: one English chart set, reused by both language renders ----
    cl = m["chart_lang"]
    bits = []
    if cl["drift"]:
        bits.append(f"{len(cl['drift'])} chart(s) embed a different spec in the FR "
                    f"column than in the EN one: {', '.join(cl['drift'][:6])} — the "
                    f"signature of a per-language chart build")
    if cl["fr"]:
        bits.append(f"{len(cl['fr'])} chart(s) carry French chrome: "
                    f"{', '.join(cl['fr'][:6])}")
    required.append((not bits, "Charts are one English set",
                     ". ".join(bits) + ". Charts are English in every render, French "
                     "included: emit ONE charts/ + specs.json (no charts/en, no "
                     "specs.en.json, no language loop in make_charts.py) and leave the "
                     "spec_* label arguments on their English defaults. Localise the "
                     "caption and the prose around the chart instead." if bits else ""))

    # ---- creatives: "none at all" is a bug, "not many" is a judgement ----
    if goals or creatives_min <= 0:
        pass          # the goals mode reads a tagging plan; it never sees a message
    elif allow_no_creatives and m["creative_any"] == 0:
        recommended.append((False, "Message creatives",
                            "none found; --allow-no-creatives set — include a labelled "
                            "illustrative/limitation creatives block instead."))
    else:
        # An account with messages and zero decoded creatives means the decode or
        # the render step silently failed — that is the failure this check was
        # installed for, and it stays blocking.
        required.append((m["creative_any"] > 0, "Message creatives present",
                         "no push or Message Center previews rendered at all. "
                         "Fix: decode perpush/pushbody + render_mocks/render_email, or add a "
                         "labelled illustrative block (then use --allow-no-creatives)."))
        floor.append((m["creative_any"] >= creatives_min, "Creative count",
                      f"{m['creative_push']} push + {m['creative_mc']} MC previews "
                      f"({per_lang_creatives:.0f}/lang) — {creatives_min}+ is the target."))

    # ---- REQUIRED: no broken images ----
    required.append((m["empty_img"] == 0, "No empty <img> sources",
                     f"{m['empty_img']} images have an empty src (missing datauri)."))

    # ---- REQUIRED: localisation (a non-English report reads as one) ----
    # Driven by the report's language, never by its profile or its language count.
    # An English-only report — a goals review, or a mode-A review built with the
    # default LANG="en" — yields no findings on its own, because `_localisation_lint`
    # has nothing non-English to inspect. Special-casing the profile here used to say
    # "mode B is English" and would have gone quiet on a French one.
    l10n = m["l10n"]
    if l10n:
        bits = []
        for lang, f in sorted(l10n.items()):
            if f["leaks"]:
                bits.append(f"[{lang}] English strings: {', '.join(f['leaks'][:6])}")
            if f["decimals"]:
                bits.append(f"[{lang}] English decimal marks: {', '.join(f['decimals'][:6])}")
            if f.get("accents"):
                bits.append(f"[{lang}] French words missing accents: "
                            f"{', '.join(f['accents'][:6])}")
        # One hint per finding kind present, so the message names the actual fix
        # instead of a generic list the reader has to filter.
        any_kind = lambda k: any(f.get(k) for f in l10n.values())
        fixes = []
        if any_kind("leaks"):
            fixes.append("pass lang= to every component (event_kpi_table, cover_section, "
                         "gauge) instead of relying on its English default, and read the "
                         "analyzer's *_fr fields where it emits both. Chart chrome is NOT "
                         "in scope — charts are English in every render — so a leak here is "
                         "prose, a caption, or a table header you own")
        if any_kind("decimals"):
            fixes.append("route every number through "
                         "ri.fmt_num/fmt_int/fmt_pct/fmt_delta with lang=")
        if any_kind("accents"):
            fixes.append("spell the French strings with their accents "
                         "(these are literals in the skill scripts, not data)")
        detail = "; ".join(bits) + ". Fix: " + "; ".join(fixes) + "."
    else:
        detail = ""
    if not goals:
        required.append((not l10n,
                         "Localisation (no English leftovers in translated blocks)", detail))

    # ---- REQUIRED: no scaffold text survives into the deliverable ----
    # The scaffold labels every un-filled block TODO so that none is forgotten; that only
    # works if TODO arriving here fails. It did not, and a report shipped with its §2
    # reading TODO while this gate reported success — the checks asked whether the section
    # was present, never what it said.
    tmpl = m["template_text"]
    required.append((not tmpl, "No template text",
                     "; ".join(tmpl[:6]) + ". Fix: replace the scaffold stub with the "
                     "section's real content, and check that any string interpolating a "
                     "value carries its `f` prefix." if tmpl else ""))

    # ---- REQUIRED: no silently-unstyled layout classes ----
    undef = m["undefined_css"]
    required.append((not undef, "No undefined layout CSS classes",
                     f"{len(undef)} class(es) used in markup but defined in no <style> "
                     f"block: {', '.join(undef[:8])}. These fail silently (the element "
                     f"just loses its layout). Fix: define them in FRAMEWORK_CSS / "
                     f"css_extra, or use an existing class."))

    # ---- REQUIRED: a KPI a reader cannot parse ----
    # Deliberately OUTSIDE the facts.json branch below. Legibility is a property of the
    # rendered figure alone, and gating it on a sibling brief would silently skip it for
    # exactly the reports most likely to be hand-assembled.
    body_kpi = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.I | re.S)
    illegible = _illegible_kpis(body_kpi)
    required.append((not illegible, "KPI values are legible",
                     f"{len(illegible)} KPI value(s) print as an unbroken run of digits: "
                     + "; ".join(f"'{lab}' shows {shown}"
                                 for lab, shown in illegible[:4])
                     + ". Fix: a count goes through ri.fmt_int (thousands separated, no "
                       "decimal place); ri.fmt_num is for rates, ratios and points "
                       "differences. The number is probably correct — it is unreadable."))

    # ---- REQUIRED (only when the build emitted a facts.json): numeric coherence ----
    facts = _sibling_facts(path)
    if facts:
        body = body_kpi
        drift = _facts_coherence(body, facts)
        bits = "; ".join(f"'{lab}' shows {_fmt(shown)} but facts.json says {_fmt(exp)}"
                         for lab, shown, exp in drift[:4])
        required.append((not drift, "KPI values agree with facts.json",
                         f"{len(drift)} KPI card(s) disagree with the shared brief: {bits}. "
                         f"Fix: quote facts.json in every section (that is what it is for). "
                         f"If the card is deliberately on another basis — a per-day rate, a "
                         f"single platform, a sub-population — say so IN THE LABEL so it no "
                         f"longer collides with the KPI name."))

        cont = _unqualified_contaminated_deltas(body, facts)
        cbits = "; ".join(f"'{lab}' shows '{pill}'" for lab, pill, _ in cont[:3])
        required.append((not cont, "Calendar-contaminated deltas name their cause",
                         f"{len(cont)} KPI card(s) publish a bare vs-prior-period delta for a "
                         f"metric whose level changed at the window boundary: {cbits}. "
                         + (cont[0][2] if cont else "") +
                         " Fix: pass an explicit delta_label naming the cause (and "
                         "delta_good=None where the direction is not a judgement), or mark "
                         "the comparison unavailable. See window_contamination in facts.json."))

        # A metric withheld in the prose and re-published in a chart legend is still
        # published. The prose avoids it, the appendix explains the refusal, and the
        # chart puts it back on screen under another name because the spec function
        # still accepted the argument.
        wch = _withheld_in_chart_labels(body, facts)
        required.append((not wch, "Charts do not re-publish a withheld metric",
                         f"{len(wch)} chart label(s) carry a metric the review withheld: "
                         + "; ".join(f"chart '{cid}' labels a series '{lab}' ({metric})"
                                     for cid, lab, metric in wch[:4])
                         + ". Fix: drop the argument from the spec_* call, or relabel the "
                           "series onto the metric the report does publish — see "
                           "facts.withheld for what to use instead." if wch else ""))

        spec_drift = _spec_total_drift(path, facts)
        required.append((not spec_drift, "Aggregated chart totals agree with facts.json",
                         f"{len(spec_drift)} aggregated spec(s) total a different period "
                         f"than the KPIs: {'; '.join(spec_drift[:3])}. Fix: in make_charts, "
                         f"slice the doubled series to the current window before summing "
                         f"(see the DOUBLED WINDOW note in airship_charts.py)."))

    # ---- REQUIRED: a worded verdict may not contradict the band it sits on ----
    body_nc = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.I | re.S)
    gv = _gauge_verdicts(body_nc)
    gbits = "; ".join(f"'{t}' claims {claim} but value {_fmt(v)} sits in "
                      f"[p10 {_fmt(a)}, p50 {_fmt(b)}, p90 {_fmt(c)}]"
                      for t, v, a, b, c, claim in gv[:3])
    required.append((not gv, "Gauge verdicts match their own band",
                     f"{len(gv)} gauge verdict(s) contradict the numbers drawn beside "
                     f"them: {gbits}. Fix: reword the verdict to the position the value "
                     f"actually holds, or gauge the value the verdict is about."))

    # ---- REQUIRED: the vertical benchmark is actually there ----
    # §3b was gate-checked for existence, never for content, so a report could ship it
    # holding only internal-baseline comparisons — or nothing — and still pass. Two of four
    # reviewed accounts cited no vertical band at all, and positioning the client against
    # its peers is the part of this deliverable the client cannot produce alone.
    #
    # Satisfied by a gauge (which carries p10/p50/p90 as data attributes) plus the source
    # line, so the reader can see both the band and its vintage. A vertical genuinely absent
    # from `benchmarks.json` is a legitimate outcome — declare it with an `na-block` and the
    # check accepts it, because a stated absence is comparable across accounts and a silent
    # one is not.
    if not goals:
        bench_sec = _one_section(body_nc, "bench")
        bench_na = "na-block" in bench_sec
        n_gauge = len(_GAUGE_RE.findall(bench_sec))
        has_src = 'data-ir-bench-source="1"' in bench_sec
        required.append((bench_na or (n_gauge > 0 and has_src),
                         "Vertical benchmark present with its source",
                         f"\u00a73b carries {n_gauge} benchmark gauge(s) and "
                         f"{'a' if has_src else 'NO'} source line. A report has to position "
                         f"the account against its vertical band and say which vintage the "
                         f"band comes from. Fix: render ri.gauge(value, p10, p50, p90, ...) "
                         f"from audit.json's `benchmarks` block and close the table with "
                         f"ri.benchmark_source_note(A['benchmarks'], lang) \u2014 or, if the "
                         f"vertical has no published band, say so in an na_block()."))

    # ---- REQUIRED: a programme shown by its identifier says so ----
    # `/api/schedules` would give the composer name and is outside the `rpt` scope this
    # review holds, so there is no automated fix — the only honest option is to say on the
    # page that the label is not presentable, addressed to whoever presents the deck. The
    # row is dangerous precisely because nothing about it looks broken: every figure on it
    # is correct.
    unnamed = _identifier_labelled_rows(body_nc)
    if unnamed:
        flagged = "data-unnamed-programme=" in body_nc
        top = sorted({r for _, r in unnamed})[:1]
        required.append((flagged, "Identifier-labelled programmes flagged for renaming",
                         "" if flagged else
                         f"{len({u for u, _ in unnamed})} programme(s) are presented under a "
                         f"raw group identifier"
                         + (f", the first at row {top[0]} of its ranking" if top else "")
                         + f". Fix: render ri.unnamed_programme_note(ids, lang) \u2014 the "
                         f"composer name is not reachable from the Reports API, so the "
                         f"report has to hand the rename to a human instead of shipping a "
                         f"UUID as a campaign name."))

    # ---- REQUIRED: value measurability is graded, and surfaced when it is nil ----
    # Whether a conversion can be tied to an amount decides what Airship is able to prove
    # for the account, and it is the finding most easily lost in prose: "value behaves as a
    # per-event counter" is accurate, unremarkable-looking, and means no message in the
    # account can ever be attached to a euro. Graded in the events section, and repeated in
    # the summary when the answer is "none" — learning that in §10 is learning it too late.
    val_m = re.search(r'class="[^"]*\bir-value-grade\b[^"]*"([^>]*)>', body_nc)
    val_grade = (re.search(r'data-value-grade="([a-z_]+)"', val_m.group(1))
                 if val_m else None)
    val_grade = val_grade.group(1) if val_grade else None
    ev_sec = re.search(r'id="events".*?</section>', body_nc, re.S)
    ev_na = bool(ev_sec) and 'class="na-block' in ev_sec.group(0)
    if ev_sec and not ev_na:
        if not val_m:
            val_why = ("the events section carries no value-measurability grade. Fix: "
                       "render ri.value_measurability_block(A['events']"
                       "['value_measurability'], lang) \u2014 whether a conversion can be "
                       "tied to an amount is the finding that bounds every revenue claim "
                       "in the report.")
        elif not (ev_sec.start() < val_m.start() < ev_sec.end()):
            val_why = ("the value-measurability grade sits outside the events section, "
                       "where a reader looking for it will not find it.")
        elif val_grade in ("counters", "declared_not_flowing"):
            # It has to be repeated where the reader starts, not only where it is derived.
            sid = next((s.get("id") for s in _SPINE
                        if isinstance(s, dict) and s.get("key") == "exec_summary"),
                       "summary")
            sm = re.search(rf'id="{re.escape(sid)}".*?</section>', body_nc, re.S)
            said = bool(sm) and bool(re.search(
                r"(no tracked event carries an amount|values none of them|"
                r"no revenue is attributable|aucun \S+ suivi ne porte de montant|"
                r"n\S*en valorise aucune|aucun chiffre d\S+affaires n\S+est attribuable|"
                r"aucun montant n\S*arrive)", sm.group(0), re.I))
            val_why = ("" if said else
                       f"value measurability grades '{val_grade}' but the executive summary "
                       f"does not say so. Fix: add ri.value_measurability_line(vm, lang) to "
                       f"the summary \u2014 a reader who learns in \u00a710 that no "
                       f"conversion carries an amount has read nine sections expecting a "
                       f"revenue figure.")
        else:
            val_why = ""
        required.append((not val_why, "Value measurability graded and surfaced", val_why))

    # ---- REQUIRED: in-app volume earns §8b, with a Scene instrumentation grade ----
    # §8b is optional in the spine because plenty of accounts run no in-app at all. But an
    # account that shows Scenes and cannot see inside them is precisely the case worth
    # reporting, and that is also the case where the section is easiest to skip: the
    # dismissal count looks like data, so nothing feels missing. Volume in the audit
    # therefore makes the section mandatory, and it has to carry a grade rather than a
    # description, so the same account reads the same way next quarter.
    ia_vol = _inapp_volume(path)
    if ia_vol:
        sec = re.search(r'id="inapp".*?</section>', body_nc, re.S)
        sec_html = sec.group(0) if sec else ""
        na = 'class="na-block' in sec_html
        graded = "data-scene-grade=" in sec_html
        if not sec_html or na:
            ia_why = (f"the audit records {ia_vol:,.0f} in-app interactions but \u00a78b is "
                      f"{'absent' if not sec_html else 'an N/A block'}. Fix: write the "
                      f"section and grade it with "
                      f"campaign_inventory.scene_instrumentation(events).")
        elif not graded:
            ia_why = ("\u00a78b describes in-app activity without grading its Scene "
                      "instrumentation. Fix: render "
                      "ri.scene_instrumentation_block(campaign_inventory."
                      "scene_instrumentation(events), lang) \u2014 a description does not "
                      "compare across quarters, a grade does.")
        else:
            # "En t\u00eate": ahead of the tables. A reader who stops after the first
            # dismissal table has to have been told what the table cannot show.
            # Icons are not visuals: every <h2> opens with one, so counting them would
            # put the "first visual" at character 15 of every section.
            probe = re.sub(r'<img[^>]*\bir-ico\b[^>]*>', "", sec_html)
            g_at = probe.index("data-scene-grade=")
            first_visual = min([p for p in (probe.find("<table"), probe.find("<img"))
                                if p >= 0] or [len(probe)])
            ia_why = ("" if g_at < first_visual else
                      "the Scene instrumentation grade sits after \u00a78b's first table or "
                      "chart. Open the section with it \u2014 a reader who stops at the "
                      "dismissal table needs to know first what it cannot show.")
        required.append((not ia_why, "In-app volume graded in \u00a78b", ia_why))

    # ---- REQUIRED: the report states its own coverage up front ----
    # A limitation that lives in a methodology appendix is read by nobody who then goes on
    # to quote the report. The banner has to sit in the executive summary, and it has to
    # carry the permanent blind spots too — a run where every stage succeeded is still a run
    # that never saw journey steps, A/B declarations or Scene funnels, and a banner that
    # only appears when something broke teaches readers to read its absence as completeness.
    cov_m = re.search(r'class="[^"]*\bir-coverage\b[^"]*"([^>]*)>', body_nc)
    cov_attrs = cov_m.group(1) if cov_m else ""
    cov_struct = int((re.search(r'data-cov-structural="(\d+)"', cov_attrs) or ["", "0"])[1])
    cov_in_summary = False
    if cov_m:
        # The HTML anchor is the spec's `id` ("summary"), not its key ("exec_summary"), and
        # the two differ — read it from the spine so mode B keeps working too.
        sid = next((s.get("id") for s in _SPINE
                    if isinstance(s, dict) and s.get("key") == "exec_summary"), "summary")
        sm = re.search(rf'id="{re.escape(sid)}".*?</section>', body_nc, re.S)
        cov_in_summary = bool(sm and sm.start() < cov_m.start() < sm.end())
    if not cov_m:
        cov_why = ("no coverage banner in the executive summary. Fix: open it with "
                   "ri.coverage_banner(coverage.assess(manifest, audit), lang), reading "
                   "data/collect_manifest.json.")
    elif not cov_in_summary:
        cov_why = ("the coverage banner sits outside the executive summary \u2014 a reader "
                   "who goes on to quote the report has read the summary, not the appendix.")
    elif cov_struct == 0:
        cov_why = ("the coverage banner names no structural blind spot, so it reads as "
                   "'nothing is missing'. Journeys, A/B declarations and Scene funnels are "
                   "out of reporting scope on every run, clean or not.")
    else:
        cov_why = ""
    required.append((not cov_why, "Coverage stated in the executive summary", cov_why))

    # ---- REQUIRED: an outcome claimed for another account cites its document ----
    # A proof point is the one figure in the review that does not come from this account's
    # own data, which makes it the one figure nobody can check afterwards — and the one a
    # model is most able to produce from memory. `ri.proof_point()` renders only what
    # `proof_points.json` holds, with its source attached; a hand-rolled `ir-proof` block
    # without a source is the failure mode this catches.
    unsourced = [m for m in re.finditer(r'class="[^"]*\bir-proof\b[^"]*"([^>]*)>', body_nc)
                 if "data-proof-source=" not in m.group(1)]
    required.append((not unsourced, "Proof points cite their source",
                     f"{len(unsourced)} proof point(s) claim a result for another account "
                     f"with no source attached. Fix: render them with "
                     f"ri.proof_point(lever, lang), which prints only entries held in "
                     f"proof_points.json \u2014 never write one in prose."))

    # ---- REQUIRED: §16 ends on a plan, not on prose ----
    # The section was mandatory and its format was not, so it shipped as lists of
    # paragraphs — no sequencing, no sizing, and no way to see which recommendation rested
    # on a measurement. A reader could not turn it into anything.
    if not goals:
        reco_sec = _one_section(body_nc, "reco")
        if reco_sec:
            required.append(('data-ir-action-plan="1"' in reco_sec,
                             "Recommendations carry an action plan table",
                             "\u00a716 has no Action / Horizon / Expected impact / "
                             "Evidence table. Prose recommendations do not sequence and "
                             "do not say what each is worth. Fix: render "
                             "ri.action_plan_table(rows, lang) \u2014 size the impact with "
                             "opportunity.py and cite it in the evidence column."))

    # ---- REQUIRED: the cover states the window the numbers were computed over ----
    cw = _cover_window_drift(html, path)
    required.append((cw is None, "Cover window matches the audit",
                     f"the cover announces {cw[0] if cw else ''} but the audit was "
                     f"computed over {cw[1] if cw else ''}. Page one is the only place "
                     f"the period appears, so a reader cannot catch this. Fix: build the "
                     f"cover line with fw.cover_period_html(A['meta']['window'], lang)."))

    # ---- REQUIRED: a percentile verdict names the sample it rests on ----
    ug = _ungrounded_gauge_verdicts(body_nc)
    ubits = "; ".join(f"'{t}' claims {c} — {r}" for t, c, r in ug[:3])
    required.append((not ug, "Percentile verdicts state their sample",
                     f"{len(ug)} gauge verdict(s) claim a percentile position without "
                     f"enough behind them: {ubits}. A position is a claim about the "
                     f"account, and one campaign cannot support one. Fix: pass "
                     f"sample= to ri.gauge() (\"n=412 pushes\", \"30 jours\"), and below "
                     f"{_GAUGE_SAMPLE_FLOOR} observations word the verdict as "
                     f"inconclusive instead of naming a decile."))

    # ---- REQUIRED: summary count tiles say whether they are a flow or a snapshot ----
    tt = _untagged_temporal_tiles(body_nc, facts)
    tbits = "; ".join(f"'{lbl}' is a {cls}" for lbl, cls in tt[:4])
    required.append((not tt, "Summary tiles state flow vs snapshot",
                     f"{len(tt)} executive-summary count tile(s) do not say which kind of "
                     f"quantity they are: {tbits}. Side by side, a base snapshot and a "
                     f"count of events over the window read as the same thing \u2014 which "
                     f"is how opt-ins and opt-outs come to look like a collapsing base. "
                     f"Fix: suffix the label \u2014 '(p\u00e9riode)' or '(events)' for a "
                     f"flow, '(instantan\u00e9)' for a snapshot."))

    # ---- REQUIRED: an active email programme reconciles its two counters ----
    # `/api/reports/sends` and the email event feed disagree by around 11% on a real
    # account, and a review that put one in the executive summary and the other in the
    # funnel published more email delivered than sent — with its headline open rate
    # standing on the second figure without saying so. Push has had a mandatory reconcile
    # for a while; email never did. Only required when §14 actually reports on email: an
    # N/A section (email inactive) has nothing to reconcile.
    if not goals:
        email_sec = _one_section(body_nc, "email")
        if email_sec and "na-block" not in email_sec:
            required.append(('data-ir-email-reconcile="1"' in email_sec,
                             "Email send counters reconciled",
                             "\u00a714 reports on email without reconciling "
                             "/api/reports/sends against the email event feed. The two "
                             "disagree, and the open rate stands on `delivered`, not on "
                             "sends \u2014 unreconciled, the headline rate depends on "
                             "whichever counter is wrong. Fix: render "
                             "ri.email_reconcile_note("
                             "channel_activity.email_reconcile(sends, funnel), lang)."))

    # ---- REQUIRED: one column, one attribution basis ----
    mb = _mixed_basis_columns(body_nc)
    mbits = "; ".join(f"'{h}' ({q} cell(s) qualified, {b} bare)" for h, q, b in mb[:3])
    required.append((not mb, "One attribution basis per table column",
                     f"{len(mb)} column(s) mix two bases under one header: {mbits}. Rows "
                     f"in such a column cannot be ranked or compared, even though each "
                     f"cell is right on its own. Fix: keep the header's basis for every "
                     f"row and put the missing term's rows at "
                     f"ri.attributed_conversions_cell(None) / an explicit n/a, or split "
                     f"the column in two (direct, influenced)."))

    # ---- REQUIRED: pressure is published per month, the unit of the benchmark ----
    wp = _weekly_pressure(body_nc)
    required.append((not wp, "Marketing pressure published per month",
                     f"pressure appears only in a weekly or daily unit "
                     f"({'; '.join(repr(x) for x in wp[:3])}) with no per-month figure "
                     f"anywhere. The UA benchmark is `sends_per_user_month`, so as it "
                     f"stands the figure cannot be positioned against its band nor "
                     f"compared to another account. Fix: publish sends / (period days / "
                     f"30.44) / opted-in base as the headline; keep the per-day framing "
                     f"beside it if it reads better (see reference.md, Marketing "
                     f"pressure)."))

    # facts.json against audit.json — the one link in the chain nothing checked. Every other
    # facts check compares the REPORT to facts.json, so a facts file left behind by an
    # earlier collection was certified rather than caught.
    #
    # Split by severity, from what a replay on five real accounts showed. The hard kinds
    # produced zero findings there, so they block without adding noise; the soft ones fired
    # twice, both times on a facts file predating a block rather than contradicting one, and
    # they ask for a rebuild rather than assert an error.
    fa = _facts_vs_audit(path)
    if fa is not None:
        hard = [d for d in fa if d["kind"] in _FACTS_HARD_KINDS]
        soft = [d for d in fa if d["kind"] not in _FACTS_HARD_KINDS]
        required.append((not hard, "facts.json agrees with audit.json",
                         f"{len(hard)} fact(s) contradict the audit they cite: "
                         + _facts_bits(hard) +
                         ". Every other facts check compares the report to facts.json, so "
                         "this makes them all agree on a stale number. Fix: re-run "
                         "build_facts.py on the current audit.json, then re-read any "
                         "section quoting the affected KPI."))

    # ---- RECOMMENDED ----
    if fa is not None and soft:
        recommended.append((not soft, "facts.json carries every derived block",
                            f"{len(soft)} block(s) or KPI(s) the audit can answer are "
                            f"absent from facts.json: " + _facts_bits(soft) +
                            ". This is not a wrong number, it is a missing one — and an "
                            "absent block makes the gate check that reads it pass "
                            "vacuously. Fix: re-run build_facts.py."))
    recommended.append((m["csv_buttons"] > 0, "CSV export on charts/tables",
                        "no CSV export buttons found."))
    # A goals review analyses a tagging plan, not messages: there is nothing to
    # deep-link to Flight Deck, so the check would only ever fire as noise.
    if not goals:
        recommended.append((m["flightdeck"] > 0, "Flight Deck deep-links",
                            "no Airship Flight Deck links found."))
    recommended.append((m["data_appendix"] > 0, "Data appendix / campaign inventory",
                        "no data appendix or campaign-inventory table found."))

    stale = _stale_sections(path)
    recommended.append((not stale, "Sections newer than the frozen audit.json",
                        f"{len(stale)} section(s) were last written BEFORE the last edit "
                        f"to audit.json, so any number they quote may be stale: "
                        + ", ".join(f"{k} ({age:.0f} min older)" for k, age in stale[:6])
                        + ". Either they were re-verified against the new base, or the "
                          "freeze was broken mid-wave — re-read them before shipping."))

    # generated-vs-embedded charts: if a sibling specs.json declares charts the
    # report never embeds, they were generated but silently dropped (recommended,
    # not blocking — some specs are intentionally unused).
    spec_ids = _sibling_specs_ids(path)
    if spec_ids:
        unused = [c for c in spec_ids if c not in m["embedded_charts"]]
        recommended.append((not unused, "All generated charts embedded",
                            f"{len(unused)} chart(s) in specs.json not embedded: "
                            f"{', '.join(unused)} — add a chart() call or drop the spec."))

    print(f"\n{path}")
    print(f"  profile={profile}  langs={m['langs']}  images={m['images']}  "
          f"sections={n_sections}" + ("  strict" if strict else ""))
    all_req_ok = True
    for ok, label, detail in required:
        mark = "✓" if ok else "✗"
        print(f"  [{mark}] {label}" + ("" if ok else f"  — {detail}"))
        all_req_ok = all_req_ok and ok
    advisories = 0
    for ok, label, detail in recommended:
        mark = "✓" if ok else "!"
        print(f"  [{mark}] {label}" + ("" if ok else f"  — {detail}"))
        advisories += 0 if ok else 1
    verdict = "PASS" if all_req_ok else "FAIL (required visuals missing)"
    # An advisory that scrolls past unread is an advisory that does nothing. Name the
    # count on the verdict line so a thin-but-valid report still asks for a decision.
    if all_req_ok and advisories:
        verdict += (f" with {advisories} advisory note(s) — read them before sending; "
                    f"re-run with --strict to gate on them")
    print("  => " + verdict)
    return all_req_ok


def _kpi_card(label, value, hero=False):
    """The markup the KPI checks actually read, for use in the selftest."""
    if hero:
        return (f'<div class="ir-hero-val">{value}</div>'
                f'<div class="ir-hero-label">{label}</div>')
    return (f'<div class="ir-kpi-val">{value}</div>'
            f'<div class="ir-kpi-label">{label}</div>')


def _selftest():
    """Pin the pure text checks. This file gates every delivery and had no test at all.

    Deliberately limited to the helpers that take markup and return findings: they are
    where the bugs have actually been, and they need no report on disk.
    """
    fails = []

    def check(cond, label):
        if not cond:
            fails.append(label)

    # --- legibility: the shape that shipped, and the shapes that must not be reported ---
    # Figures here are invented. The real ones are portfolio data, and a test written to
    # guard a leak is a poor place to commit one.
    bad = _kpi_card("Push sends", "13571113.0")
    check(_illegible_kpis(bad), "an unseparated count with a decimal is caught")
    check(_illegible_kpis(_kpi_card("Events", "246813579.0", hero=True)),
          "the same, in a hero tile")
    check(_illegible_kpis(_kpi_card("Opens", "48151623")),
          "an unseparated count without a decimal is caught")

    for good, why in (
        ("13,571,113", "a grouped count"),
        ("13\u00a0571\u00a0113", "a French grouped count (no-break space)"),
        ("52.71%", "a percentage"),
        ("11.38", "a pressure ratio"),
        ("1.54\u00d7", "a multiple"),
        ("\u20ac15.79M", "an abbreviated currency amount"),
        ("2026-08-24", "a date"),
        ("9", "a single digit"),
        ("n/a", "a non-numeric value"),
    ):
        check(not _illegible_kpis(_kpi_card("x", good)), f"{why} is not reported ({good})")

    # A number in prose is none of this check's business: an author may legitimately
    # quote a raw id or a bare count in a sentence.
    check(not _illegible_kpis("<p>the orchestrator sent 13571113 pushes</p>"),
          "a bare number in prose is not reported")

    # --- double-escaping: ANY named entity, not the five an English report reaches for ---
    # Both of the first two shipped past this check on a German review, green, and were
    # found by reading a screenshot. They are pinned by name because the enumeration is
    # exactly what failed.
    for ent, why in (
        ("&amp;euro;2.99", "a currency entity"),
        ("Str&amp;ouml;er", "a German umlaut entity"),
        ("A &amp;amp; B", "the ampersand the old pattern already caught"),
        ("&amp;sect;4", "a section sign"),
        ("&amp;#8364;", "a decimal numeric reference"),
        ("&amp;#x20AC;", "a hexadecimal numeric reference"),
    ):
        check(_double_escaped(f"<p>{ent}</p>"), f"{why} is caught ({ent})")

    # Documenting the escaping contract is not violating it: a methodology appendix may
    # print the entity inside <code>, and a data-verbatim cell holds a client payload
    # quoted exactly as stored.
    for exempt, why in (
        ("<p>pass <code>&amp;amp;</code> to raw-HTML helpers only</p>", "inside <code>"),
        ("<pre>&amp;euro;</pre>", "inside <pre>"),
        ('<td data-verbatim>&amp;euro;14.00</td>', "in a data-verbatim cell"),
    ):
        check(not _double_escaped(exempt), f"an entity {why} is not reported")

    # --- _parse_shown: the reader every value check depends on ---
    for text, want in (("1,234,567", 1234567.0), ("1\u202f234\u202f567", 1234567.0),
                       ("67.4%", 67.4), ("67,4 %", 67.4), ("3,3 M", 3300000.0),
                       ("\u20ac1.2M", 1200000.0), ("-30.9", -30.9)):
        got = _parse_shown(text)
        check(got is not None and abs(got - want) < 0.01,
              f"_parse_shown({text!r}) -> {got}, want {want}")

    # --- template text: the scaffold leftover that shipped past this gate ---
    check(_template_text("<td>TODO</td>"), "scaffold TODO text is caught")
    check(not _template_text("<p>Sa todo list est vide.</p>"),
          "lower-case 'todo' in prose is not scaffold text")
    check(_template_text("<h3>les {n(inter, lang)} interactions</h3>"),
          "an f-string that lost its prefix is caught")
    check(not _template_text("<p>The set {a, b} is unchanged.</p>"),
          "a set literal in prose is not an unformatted f-string")

    # --- recommendations depth: the three shapes §16 ships in ---
    bullets = "".join("<li>do a thing</li>" for _ in range(6))
    check(_reco_items(f"<ul>{bullets}</ul>") == 6, "bullets are counted")
    plan = ('<table class="grid" data-ir-action-plan="1"><thead><tr><th>Action</th></tr>'
            '</thead><tbody>' + "".join("<tr><td>x</td></tr>" for _ in range(7))
            + "</tbody></table>")
    check(_reco_items(plan) == 7,
          "an action-plan table is counted, header row excluded")
    cards = "".join('<div class="reco-head">x</div>' for _ in range(6))
    check(_reco_items(cards) == 6, "recommendation cards are counted")
    # The regression this fixes: the richest shape scored zero and failed the floor.
    check(_reco_items(plan + cards) == 7,
          "the shapes are not summed — a plan restating its cards is one set")

    # --- a withheld metric re-published in a chart legend ---
    def spec(cid, label):
        return (f'<script class="ir-chart-spec" id="spec-{cid}">'
                f'{{"data":{{"datasets":[{{"label":"{label}"}}]}}}}</script>')

    wfacts = {"withheld": [{"metric": "influenced_rate", "value": 0.21,
                            "reason": "attribution window not comparable"}]}
    check(_withheld_in_chart_labels(spec("prog", "Influenced %"), wfacts),
          "a withheld metric back in a chart legend is caught")
    check(not _withheld_in_chart_labels(spec("prog", "Direct opens"), wfacts),
          "an unrelated legend is not")
    check(not _withheld_in_chart_labels(spec("prog", "Influenced %"), {}),
          "with nothing withheld there is nothing to catch")
    # Short tokens are too common to match on: `open_rate` must not fire on every
    # chart that says "rate".
    check(not _withheld_in_chart_labels(
        spec("p", "Open rate"), {"withheld": [{"metric": "open_rate"}]}),
        "a short token does not fire")
    # The false positive this check produced on its first real report: `residual_identity`
    # withholds what the residual messages ARE; the chart plots how MUCH residual there
    # is, and says so in the label. One shared word is not the same metric.
    check(not _withheld_in_chart_labels(
        spec("cov", "Residual (never returned per message)"),
        {"withheld": [{"metric": "residual_identity"}]}),
        "one shared word is not a match — every distinctive word must appear")
    check(_withheld_in_chart_labels(
        spec("cov", "Residual identity by day"),
        {"withheld": [{"metric": "residual_identity"}]}),
        "...and when they all do, it is")

    for f in fails:
        print(f"  \u2717 {f}")
    print(f"verify_report selftest: {'FAIL' if fails else 'ok'} "
          f"({len(fails)} failure(s))")
    return 1 if fails else 0


def main():
    if "--selftest" in sys.argv[1:]:
        sys.exit(_selftest())
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("reports", nargs="+", help="path(s) to report.html")
    ap.add_argument("--charts-min", type=int, default=5,
                    help="minimum chart figures required (default 5)")
    ap.add_argument("--creatives-min", type=int, default=3,
                    help="minimum creative previews required (default 3)")
    ap.add_argument("--allow-no-creatives", action="store_true",
                    help="downgrade the creatives check to a warning")
    ap.add_argument("--sections-min", type=int, default=None,
                    help="minimum distinct canonical sections required "
                         "(default 16, or the size of the profile's spine)")
    ap.add_argument("--profile", choices=("full", "goals"), default="full",
                    help="which report contract to enforce: 'full' (default) or "
                         "'goals' (the light conversion review: one language, no "
                         "Reports API, no creatives, no PDF)")
    ap.add_argument("--strict", action="store_true",
                    help="gate on the volume floors too (section depth, "
                         "recommendation/insight/chart/creative counts) instead of "
                         "reporting them as advisories")
    args = ap.parse_args()

    charts_min, creatives_min = args.charts_min, args.creatives_min
    allow_no_creatives, sections_min = args.allow_no_creatives, args.sections_min
    if args.profile == "goals":
        if sections_min is None:
            sections_min = len(_GOALS_GATE) + 1        # + the cover
        if charts_min == 5:
            charts_min = 3
        creatives_min, allow_no_creatives = 0, True
    elif sections_min is None:
        # Derived, not a magic number: the floor is "every gated section, plus the
        # cover". Demoting a section to optional therefore relaxes the count in the
        # same edit, instead of leaving a stale 16 that still demands the section
        # under a different name.
        sections_min = len(CANONICAL_SECTIONS) + 1

    ok = True
    for p in args.reports:
        ok = run(p, charts_min, creatives_min, allow_no_creatives,
                 sections_min, profile=args.profile, strict=args.strict) and ok
    print()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
