#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CANONICAL section-helpers scaffold — copy me for a new client.

    mkdir -p work/<client>/sections
    cp .cursor/skills/airship-engagement-review/scripts/sections_shared_template.py \
       work/<client>/sections/_shared.py

Every section then starts with one import and inherits the house rules:

    from _shared import KPI, chart, i, kpi, note, signal_table, flight_deck

Why a scaffold. All the discipline that protects a report — where a number may come
from, which deltas must carry a caveat, what gets escaped, how a missing Flight Deck id
renders — used to live in a file rewritten from scratch every run. It is the wrong thing
to rewrite: it is not where the account's judgement lives, it is where the rules live,
and a rule re-derived from memory in wave 4 is a rule that holds by luck. Worse, the cost
of getting it wrong is paid by ten parallel subagents at once.

So this file is deliberately boring, and the per-run work is the CONFIGURE block below.

What it buys, concretely:
  * a number quoted twice in two sections comes from one place, so it cannot drift;
  * `kpi()` raises on an unknown key instead of returning a silent zero — a section that
    quotes a KPI which is not in the brief fails at build time, not at proofreading time;
  * `contamination_note()` renders the mandatory calendar caveat from the detector's own
    evidence, so no section has to reword it and the gate's matching check cannot be
    satisfied by an approximate paraphrase;
  * `signal_table()` escapes its own cells, which is the single commonest source of the
    double-escaping the gate rejects;
  * `flight_deck()` renders a missing composer id as a muted, explained pill rather than
    a dead button or a dropped link.

Both languages are wired where the text is fixed. Prose stays in the sections.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Copied to work/<client>/sections/, the skill lives three levels up under .cursor/.
SKILL = os.path.join(HERE, "..", "..", ".cursor", "skills", "airship-engagement-review")
if not os.path.isdir(SKILL):
    SKILL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(SKILL, "scripts"))

import canonical_sections as cs          # noqa: E402
import report_interactive as ri          # noqa: E402
import report_framework as fw            # noqa: E402

# ==========================================================================
# CONFIGURE — the only part that should change between runs
# ==========================================================================
# Why a send may legitimately have no Flight Deck link. On a firehose/API-driven account
# this is the NORMAL case, not an error, and saying so stops a reader reading absence as
# a data gap. Set to None on an account where every message is composer-built, so that a
# missing id shows up as the anomaly it would then be.
NO_DEEPLINK_REASON = {"en": "No deep-link (API send)", "fr": "Pas de lien (envoi API)"}

# Fallback when the audit states no currency. Only used for `money()`.
CURRENCY_FALLBACK = "€"
# ==========================================================================

_p = lambda *a: os.path.join(HERE, *a)            # noqa: E731


def _load(name, required=True):
    """Read a frozen artefact. Absent-but-optional -> None; absent-but-required -> raise.

    Explicit rather than a blanket try/except: a missing `creatives.json` is ordinary (a
    goals review has no creatives), while a missing `facts.json` means the freeze never
    happened and every number below would be invented.
    """
    path = _p(name)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    if required:
        raise FileNotFoundError(
            f"{path} is missing — run analyze.py and build_facts.py before any section")
    return None


A = _load("audit.json")
FACTS = _load("facts.json")
SPECS = _load("specs.json")
CREATIVES = _load("creatives.json", required=False) or {"previews": {}}
CH = _p("charts")
CR = _p("creatives")

KPI = {k["key"]: k for k in FACTS["kpis"]}
CONTAMINATED = {c["kpi_key"]: c for c in
                ((FACTS.get("window_contamination") or {}).get("contaminated") or [])}
WITHHELD = {w["metric"]: w for w in (FACTS.get("withheld") or [])}
WINDOW = FACTS.get("window") or {}
CUR = ((A.get("conversion") or {}).get("currency")) or CURRENCY_FALLBACK

APP_KEY = FACTS.get("app_key")
REGION = (FACTS.get("region") or "eu").lower()


# --------------------------------------------------------------------------
# frozen artefacts
# --------------------------------------------------------------------------
def chart(cid, lang, alt="", height=440):
    """A frozen chart. Raises if the spec or PNG is absent, by design.

    A section that silently drops a chart is worse than one that fails to build: the
    report ships looking complete.
    """
    return fw.chart(cid, CH, SPECS, lang=lang, alt=alt, height=height)


def creative(cid, caption, alt=""):
    """A rendered push preview, inlined as a data URI."""
    prev = (CREATIVES.get("previews") or {}).get(cid)
    if not prev:
        raise KeyError(f"{cid} is not in creatives.json — run render_pushes.py, or drop "
                       f"the preview rather than shipping an empty <img>")
    return ri.creative_push_preview(fw.datauri(prev["file"]), caption, alt=alt)


def kpi(key):
    """The frozen KPI record. Raises rather than returning a silent zero.

    The raise is the point. A KPI absent from the brief means either the analysis did not
    produce it — in which case the section must not state it — or `build_facts` could not
    resolve its path, in which case widen the path. Both are fixable; a zero rendered as
    a measurement is not, because nothing downstream can tell it from a real zero.
    """
    if key not in KPI:
        raise KeyError(f"{key} is not in facts.json — add it to build_facts "
                       f"(or stop quoting it). Available: {', '.join(sorted(KPI))}")
    return KPI[key]


def withheld(metric):
    """-> the withheld record for a metric, or None.

    Check this BEFORE quoting anything the collection may have disqualified. The record
    carries the value it disqualifies and what to publish instead, so the honest sentence
    is already written; the failure mode is not knowing to look.
    """
    return WITHHELD.get(metric)


# --------------------------------------------------------------------------
# formatting
# --------------------------------------------------------------------------
def i(n, lang="en"):
    """A COUNT: thousands-separated, no decimal place. Use this for anything countable."""
    return ri.fmt_int(n, lang)


def n(v, lang="en", dgt=1):
    """A RATE, ratio or points difference. Keeps one decimal; do not use it for counts."""
    return ri.fmt_num(v, lang, dgt)


def money(v, lang="en"):
    """Amounts in the account's inferred currency, abbreviated above a million."""
    if v is None:
        return "—"
    if abs(v) >= 1e6:
        return f"{CUR} {v / 1e6:.2f}M"
    return f"{CUR} {ri.fmt_int(round(v), lang)}"


def esc(s):
    """Escape anything quoted verbatim from the client account.

    A section body is raw HTML — that is what makes `<b>` and `&mdash;` work, and it is
    also what silently eats the angle brackets in a naming convention like
    `MobilePush_<Theme>_KW<week>`, which the browser reads as two unknown tags and drops.
    It shipped that way once, rendering as `MobilePush_ _KW _` in a delivered report.

    So the rule is not "escape text going into `note()`". It is: anything copied out of
    the account — a campaign name, a template token, a payload key, an event property —
    goes through here, wherever it lands.
    """
    return ri.html.escape(str(s))


_NUM_BY_KEY = {s["key"]: s.get("num", "") for s in cs.CANONICAL_SECTIONS}


def ref(key):
    """Cross-reference another section by its CANONICAL KEY, never by a number you typed.

    `ref("strategy")` -> "§3c". The numbering is static and lives in `canonical_sections`,
    so this is always right; a hand-written `§5` is right only if the author happened to
    know which canonical slot the lifecycle section occupies. In one review, sections
    written in parallel by different agents produced 31 wrong cross-references — 22 saying
    `§5` for the section that ships as `§3c`, and nine pointing at `§9`/`§10`/`§11`/`§12`,
    numbers no canonical section carries (the set has `8-10` and `11-12` instead).

    Raises on an unknown key rather than rendering a plausible `§None`: a section author
    who misremembers a key should find out at build time, not in the coherence pass.
    """
    if key not in _NUM_BY_KEY:
        raise KeyError(f"ref(): no canonical section keyed {key!r}. "
                       f"Known keys: {', '.join(sorted(_NUM_BY_KEY))}")
    num = _NUM_BY_KEY[key]
    if not num:
        raise KeyError(f"ref(): section {key!r} carries no number and cannot be cited.")
    return f"\u00a7{num}"


# --------------------------------------------------------------------------
# blocks
# --------------------------------------------------------------------------
def flight_deck(ui_id, label=None, lang="en"):
    """Deep link to a message in Flight Deck, or a muted pill when there is no `ui_id`.

    Renders the unavailable state rather than omitting the button: a reader who sees no
    link cannot tell "not linkable" from "we forgot". See NO_DEEPLINK_REASON.
    """
    url = ri.flight_deck_url(APP_KEY, ui_id, region=REGION) if (APP_KEY and ui_id) else None
    default = "Open in Flight Deck" if lang == "en" else "Ouvrir dans Flight Deck"
    reason = (NO_DEEPLINK_REASON or {}).get(lang) if NO_DEEPLINK_REASON else None
    return ri.flight_deck_button(url, label=label or default, unavailable=reason)


def signal_table(rows, lang="en", head=None):
    """The `Signal | Value | Reading` table the skill prefers over figure-heavy prose.

    Cells are escaped HERE, so callers pass plain text — apart from `reading`, which is
    allowed inline emphasis because a reading often needs to mark one word. Escaping at
    this boundary rather than in the caller is what keeps `&` out of the gate's
    double-escaping check: a section that escapes first and passes the result in gets
    `&amp;amp;`, and that has happened on more than one run.
    """
    head = head or (("Signal", "Value", "Reading") if lang == "en"
                    else ("Signal", "Valeur", "Lecture"))
    th = "".join(f"<th>{esc(h)}</th>" for h in head)
    body = []
    for sig, val, reading in rows:
        body.append(f"<tr><td>{esc(sig)}</td>"
                    f"<td><b>{esc(val)}</b></td>"
                    f"<td>{reading}</td></tr>")
    return (f'<table class="grid"><thead><tr>{th}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table>')


def note(html_body, kind=""):
    """A callout. Takes RAW HTML — entities must already be encoded (see `esc`)."""
    cls = f"note {kind}".strip()
    return f'<div class="{cls}">{html_body}</div>'


def contamination_note(kpi_key, lang="en"):
    """The mandatory caveat when a published delta is a calendar artefact.

    `build_facts` decides which deltas are contaminated; the gate then refuses any of them
    published under a bare "vs prior period". Rendered once here, from the detector's own
    evidence, so no section has to reword it — and so the disclosure cannot quietly weaken
    into a hedge that satisfies the check without warning the reader.

    Returns "" when the KPI is not contaminated, so it is safe to call unconditionally.
    """
    c = CONTAMINATED.get(kpi_key)
    if not c:
        return ""
    causes = "; ".join(c.get("causes") or [])
    brk, bound = c.get("boundary_break_at"), c.get("boundary_at")
    if lang == "en":
        return note(f"<b>Read this delta as a calendar difference, not a trend.</b> "
                    f"The level of this metric shifts on <b>{esc(brk)}</b>, close to the "
                    f"window boundary of {esc(bound)} — {esc(causes)}. The comparison is "
                    f"reported for completeness; the decomposition below is what it "
                    f"actually means.", "note-warn")
    return note(f"<b>À lire comme un écart de calendrier, pas comme une tendance.</b> "
                f"Le niveau change le <b>{esc(brk)}</b>, près de la frontière du "
                f"{esc(bound)} — {esc(causes)}. La comparaison est donnée pour "
                f"information ; c'est la décomposition ci-dessous qui l'explique.",
                "note-warn")
