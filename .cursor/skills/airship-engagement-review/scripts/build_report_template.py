#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CANONICAL engagement-review builder scaffold — copy me for a new client.

    cp .cursor/skills/airship-engagement-review/scripts/build_report_template.py \
       work/<client>/build_report.py

This scaffold guarantees a COMPLETE report from the first run: every canonical
section is already wired, so an un-filled section renders a labelled "N/A (reason)"
block instead of silently disappearing. You then replace each `renderers[...]`
stub with real content, section by section, re-running until the delivery gate
(auto-run at write time) passes.

Why a scaffold (not a from-scratch build_report.py):
  * structure is driven by canonical_sections.CANONICAL_SECTIONS (single source of
    truth, shared with the gate) — you cannot forget a section;
  * charts go through report_framework.chart(), which FAILS LOUDLY on a missing
    spec/PNG (no more silently-dropped charts);
  * report_framework.write_report() runs verify_report as a BLOCKING step, so an
    incomplete report can't be produced unnoticed (use --no-gate to override);
  * audit access via report_framework.aget() degrades to N/A on a stale/partial
    audit.json rather than crashing the whole build.

Usage:
    python work/<client>/build_report.py             # build + gate (HTML only)
    python work/<client>/build_report.py --pdf       # ...and offer the PDF companion
    python work/<client>/build_report.py --no-gate   # build without gating
    python work/<client>/build_report.py --bilingual # ship BOTH languages (see below)
    python work/<client>/build_report.py --keep-raw  # keep data/ after delivery

ONE LANGUAGE BY DEFAULT. A review ships the language its reader reads, set by ``LANG``
below. The bilingual build is real work, not a formatting option: every section is
written twice, and across thirteen delivered accounts the localisation checks were the
single largest source of gate failures. Pass ``--bilingual`` when a client genuinely
reads both columns, and expect the run to cost roughly twice as much prose.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# When copied to work/<client>/, the skill lives two levels up under .cursor/.
SKILL = os.path.join(HERE, "..", "..", ".cursor", "skills", "airship-engagement-review")
if not os.path.isdir(SKILL):
    # fallback: running the template in-place from the scripts/ dir
    SKILL = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(SKILL, "scripts"))

import report_interactive as ri          # noqa: E402
import report_framework as fw            # noqa: E402
import data_foundation as _df            # noqa: E402  (optional tagging-plan audit)
import campaign_inventory as ci          # noqa: E402  (scene instrumentation)
import coverage as cov                   # noqa: E402  (page-1 coverage banner)
from report_framework import NoData      # noqa: E402  (raise to force N/A)

# --------------------------------------------------------------------------
# Inputs — point these at the client's fetched data
# --------------------------------------------------------------------------
CLIENT = "CLIENT_NAME"                    # the client's display name
PROJECT = "CLIENT PROD"                   # Airship project name
REGION = "EU"
VERTICAL = "Retail"
# The language of the deliverable. Being asked for the review in French is a reason to
# set this to "fr" — not a reason to ship two languages. Under --bilingual this stays
# the primary: the one that opens on load and the one the PDF prints.
LANG = "en"
PDF_FILENAME = f"{CLIENT}_Engagement_Review.pdf"

AUDIT_PATH = os.path.join(HERE, "audit.json")
SPECS_PATH = os.path.join(HERE, "specs.json")
CH = os.path.join(HERE, "charts")         # matplotlib PNGs + used by fw.chart()
CR = os.path.join(HERE, "creatives")      # rendered push/MC previews

A = json.load(open(AUDIT_PATH, encoding="utf-8")) if os.path.isfile(AUDIT_PATH) else {}
SPECS = json.load(open(SPECS_PATH, encoding="utf-8")) if os.path.isfile(SPECS_PATH) else {}

# OPTIONAL RTDS tagging-plan / data-collection audit. Supplied by the user; unlocks the
# data-foundation section and the events/attributes data appendices. `load` never raises —
# it returns {"available": False} when the file is absent, and every consumer degrades
# gracefully, so this line is safe to keep even for clients with no tagging plan.
#
# The parsed pair comes first and the raw export is the fallback, because wave 1c has
# already run parse+analyze and written them here. Pointing only at the raw export means
# guessing where the user's file landed, and a wrong guess is indistinguishable from "no
# plan supplied": one review shipped §18 as "N/A — no tagging-plan audit" while §2b, §17
# and §19 analysed that same plan at length, because the path said `data/` and the file
# sat at the work-dir root.
AUDIT = _df.load(analysis_path=os.path.join(HERE, "analysis.json"),
                 inventory_path=os.path.join(HERE, "inventory.json"),
                 raw_path=os.path.join(HERE, "tagging_plan.json"), vertical=VERTICAL)
if not AUDIT.get("available") and AUDIT.get("path_error"):
    raise SystemExit(f"[audit] {AUDIT['reason']}")

# The collection manifest, read HERE and passed down, so no section has to open data/.
# It is one of the few files purge_work.py keeps at any depth (KEEP_ANYWHERE), which is
# what makes this read survive the retention step a section's own read would not.
_MANIFEST_PATH = os.path.join(HERE, "data", "collect_manifest.json")
MANIFEST = (json.load(open(_MANIFEST_PATH, encoding="utf-8"))
            if os.path.isfile(_MANIFEST_PATH) else {})
# What this review rests on and what it cannot claim, graded from the manifest. Rendered
# on page 1 by r_exec_summary below; `assess` degrades to an empty banner with no manifest.
COVERAGE = cov.assess(MANIFEST, A)


# --------------------------------------------------------------------------
# Per-run context shared by every renderer (add whatever you need)
# --------------------------------------------------------------------------
class Ctx:
    def __init__(self, lang):
        self.lang = lang
        self.EN = lang == "en"

    def L(self, en, fr):
        return en if self.EN else fr


# --------------------------------------------------------------------------
# Section renderers. Each returns BODY html (the <section>/<h2> shell is added
# by the framework) — or raises NoData(...) / returns "" to emit an N/A block.
#
# Fill these in ONE BY ONE. Everything you leave as a NoData stub still SHIPS as
# a labelled N/A section, so the report is always structurally complete.
# --------------------------------------------------------------------------
def r_cover(ctx, lang):
    # The cover is `raw`: return the FULL <section> via fw.cover_section().
    logo = ri.brand_logo("white", height=34, alt="Airship")
    mark = ri.brand_asset_datauri("airship_mark_blue.png")
    return fw.cover_section(
        brand_logo_html=logo, mark_uri=mark,
        badge_en="Mobile Activity &amp; Engagement Review",
        badge_fr="Revue d’activité &amp; d’engagement mobile",
        title_en=f"{CLIENT} {fw.EM} Mobile app",
        title_fr=f"{CLIENT} {fw.EM} Application mobile",
        sub_html_en=f"{PROJECT} &middot; {REGION} region",
        sub_html_fr=f"{PROJECT} &middot; Région {REGION}",
        period_html_en="Analysis window: <b>TODO</b> &middot; Source: Airship Reports API",
        period_html_fr="Fenêtre d’analyse : <b>TODO</b> &middot; Source : Airship Reports API",
        kpis=[
            {"value": "TODO", "label_en": "push opt-in devices", "label_fr": "appareils opt-in push"},
            {"value": "TODO", "label_en": "blended opt-in rate", "label_fr": "taux d’opt-in blended"},
            {"value": "TODO", "label_en": "push sent (30d)", "label_fr": "push envoyés (30j)"},
        ],
        lang=lang)


def _todo(ctx, lang):
    """Placeholder renderer: forces the standard N/A block for a section."""
    raise NoData()


# Marks this as a stub to be replaced, so `sections/<key>.py` overrides it instead of
# being ignored. Without the flag, an inline entry wins over the file and a section
# someone actually wrote never reaches the report.
_todo.is_placeholder = True


# --- MANDATORY rich components (enforced by the delivery gate) -----------------
# The gate now REQUIRES these in every report, because they were silently thinned
# out on a leaner build. Fill the rows/KPIs from audit.json — do NOT leave as N/A.
#
# Each renderer below already CALLS the component the gate looks for — the coverage
# banner, the value-measurability line, the Scene instrumentation grade, the action
# plan table. That is the point of the scaffold: on two consecutive reviews all four
# were discovered at the gate-fix stage and wired by hand, half an hour a run, for a
# one-line call each. What is left to you is the content, never the wiring.
def r_account_profile(ctx, lang):
    """Canonical §2 — MUST include the channel-adoption matrix + feature scorecard."""
    L = ctx.L
    # TODO: build rows from audit.json (devices/channels + decoded features).
    matrix = ri.channel_adoption_matrix([
        {"channel": "Push \u2014 iOS", "status": True, "volume": "TODO", "optin": "TODO"},
        {"channel": "Push \u2014 Android", "status": True, "volume": "TODO", "optin": "TODO"},
        {"channel": "Email", "status": False, "volume": L("0 (inactive)", "0 (inactif)"), "optin": None},
    ], lang=lang)
    features = ri.feature_adoption_table([
        {"feature": L("Rich & personalised push", "Push riche & personnalisé"), "adopted": True, "evidence": "TODO"},
        {"feature": L("Automation / Journeys", "Automation / Journeys"), "adopted": False, "evidence": "TODO"},
        {"feature": "A/B testing", "adopted": False, "evidence": "TODO"},
    ], lang=lang, upsell=L("TODO upsell opportunities.", "TODO opportunités d’upsell."))
    return matrix + features


def r_exec_summary(ctx, lang):
    """Canonical §3 — MUST carry >=3 KPI hero bands (audience / usage-vs-prior / value).

    STANDARD: every KPI tile carries a vs-prior-period comparison. Pass ``delta``
    (fraction vs the prior window) + ``delta_good`` (True=up good, False=up bad e.g.
    opt-outs, None=neutral). For a metric that genuinely can't be windowed (a lifetime
    device snapshot, an aggregate event series), pass ``no_baseline=True`` for a muted
    "no prior-period baseline" note — never leave a KPI card with no comparison state.

    The two blocks above the KPIs are wired already and are not decoration. The coverage
    banner states what the run collected and what it therefore cannot claim; the value
    line says whether any conversion in this account can be given an amount. Both are
    page-1 statements on purpose — a limitation a reader meets in an appendix is a
    limitation they have already quoted past.
    """
    L = ctx.L
    # Both render "" when there is nothing to declare (clean run / revenue is attributable),
    # so leaving them in costs nothing on an account that needs neither.
    banner = ri.coverage_banner(COVERAGE, lang=lang)
    vline = ri.value_measurability_line((A.get("events") or {}).get("value_measurability"),
                                        lang=lang)
    # TODO: fill values + prior-period deltas from audit.json.
    # Device counts are a lifetime snapshot -> no_baseline (no windowed prior).
    #
    # METHODOLOGY (gate-enforced): every tile needs formula= (the calculation) AND
    # source= (the exact endpoint). hero_kpi_band renders NO info button when they
    # are missing, so an un-annotated tile fails silently rather than looking broken.
    audience = ri.hero_kpi_band([
        {"value": "TODO", "label": L("Push opt-in devices", "Appareils opt-in push"),
         "no_baseline": True,
         "formula": L("iOS opted_in + Android opted_in", "opt-in iOS + opt-in Android"),
         "source": "GET /api/reports/devices", "confidence": "high"},
        {"value": "TODO", "label": L("Blended opt-in rate", "Taux d’opt-in blended"),
         "no_baseline": True,
         "formula": L("opted-in devices / unique devices, both platforms",
                      "appareils opt-in / appareils uniques, deux plateformes"),
         "source": "GET /api/reports/devices", "confidence": "high"},
    ], lang=lang)
    usage = ri.hero_kpi_band([
        {"value": "TODO", "label": L("Push sent (30d)", "Push envoyés (30j)"),
         "delta": None, "delta_good": True,
         "formula": L("sum of daily iOS + Android sends over the window",
                      "somme des envois quotidiens iOS + Android sur la fenêtre"),
         "source": "GET /api/reports/sends (precision=DAILY)", "confidence": "high"},
        {"value": "TODO", "label": L("App opens (30d)", "Ouvertures app (30j)"),
         "delta": None, "delta_good": True,
         "formula": L("sum of daily app opens, all origins",
                      "somme des ouvertures d’app quotidiennes, toutes origines"),
         "source": "GET /api/reports/opens (precision=DAILY)", "confidence": "high"},
    ], lang=lang)
    value = ri.hero_kpi_band([
        {"value": "TODO", "label": L("Push pressure (sent/opt-in/mo)", "Pression push (envois/opt-in/mois)"),
         "delta": None, "delta_good": None,
         "formula": L("window sends / opted-in devices",
                      "envois sur la fenêtre / appareils opt-in"),
         "source": "GET /api/reports/sends + /api/reports/devices", "confidence": "high"},
        {"value": "TODO", "label": L("Conversions / value (30d)", "Conversions / valeur (30j)"),
         "no_baseline": True,
         "formula": L("TODO — state the custom events counted",
                      "TODO — préciser les événements custom comptés"),
         "source": "GET /api/reports/events", "confidence": "high"},
    ], lang=lang)
    vline_html = f'<p>{vline}</p>' if vline else ""
    return (banner
            + f'<div class="verdict"><b>{L("Verdict","Verdict")}.</b> TODO</div>'
            f'<div class="note note-up"><b>{L("Key signal","Signal clé")}.</b> TODO</div>'
            + vline_html
            + f'<h3>{L("Key KPIs","KPIs clés")} \u2014 {L("audience","audience")}</h3>{audience}'
            f'<h3>{L("Key KPIs","KPIs clés")} \u2014 {L("usage &amp; permissions (vs prior 30 days)","usage &amp; permissions (vs 30j précédents)")}</h3>{usage}'
            f'<h3>{L("Key KPIs","KPIs clés")} \u2014 {L("value &amp; pressure","valeur &amp; pression")}</h3>{value}')


def r_inapp(ctx, lang):
    """8b. In-app / Scenes — MUST open on the instrumentation grade (gate-enforced).

    A paragraph describing in-app activity ("69% dismissed, 12 distinct CTAs") compares
    with nothing: not with last quarter, not with another account. The grade does, which
    is why it leads the section rather than closing it. Renders "" when the account shows
    no in-app at all, so the section stays a legitimate N/A.
    """
    L = ctx.L
    grade = ri.scene_instrumentation_block(ci.scene_instrumentation_from_audit(A), lang=lang)
    if not grade:
        raise NoData()
    # TODO: add the in-app KPIs and the outcome breakdown under the grade.
    return grade + f"<p>{L('TODO', 'TODO')}</p>"


def r_recommendations(ctx, lang):
    """16. Recommendations — MUST carry the action plan table (gate-enforced).

    §16 was mandatory as a section and free-form as a format, so it shipped as prose
    lists a reader could not turn into a plan. The table forces the four things that
    make one: what to do, by when, what it is worth, and what that estimate rests on.

    `action_plan_table` RAISES on a row that states an impact with no evidence, which is
    deliberate — a plausible number with no source is the most quotable line in a review
    and the least defensible. An action whose value genuinely cannot be sized is honest:
    leave `impact` empty and it renders as "not sized".
    """
    L = ctx.L
    # TODO: replace with the account's real plan (6+ rows). `horizon` takes an
    # ri.ACTION_HORIZONS key ("now", "quarter", "half") or free text.
    plan = ri.action_plan_table([
        {"action": L("TODO — the first thing to change", "TODO — le premier changement"),
         "horizon": "now",
         "impact": "",          # leave empty until it is sized; see the docstring
         "evidence": L("TODO — the figure this rests on", "TODO — le chiffre qui l’appuie")},
    ], lang=lang)
    return f"<h3>{L('The plan in one table', 'Le plan en un tableau')}</h3>{plan}"


def r_appx_events(ctx, lang):
    """18. Data appendix — tracked custom events (needs a tagging-plan audit).

    The two tables go TOGETHER and the gate enforces it: the first lists every event
    with the state of its reserved `value` field, the second shows what the properties
    actually contain. "11 properties" is not a finding — a clean 7-value enum is
    segmentable, a 200-distinct free-text blob is not, and only the values say which.
    """
    if not AUDIT.get("available"):
        # Carry `reason` rather than a bare N/A: it names the paths that were looked at, so
        # a plan sitting one directory away reads as a wiring bug on the page instead of as
        # "the client supplied nothing" — which is how one review shipped this page blank
        # while three other sections analysed that same plan.
        raise NoData(AUDIT.get("reason", ""), AUDIT.get("reason", ""))
    L = ctx.L
    return f"""
    <p>{L("Every custom event in the data-collection audit (Airship-managed ua_* events "
          "excluded), with its source, behavioural category, occurrences, the state of the "
          "reserved <code>value</code> field and its properties.",
          "Tous les événements custom de l’audit de collecte (événements ua_* gérés par "
          "Airship exclus), avec leur source, catégorie comportementale, occurrences, l’état "
          "du champ réservé <code>value</code> et leurs propriétés.")}</p>
    {ri.audit_events_table(AUDIT, lang=lang)}
    <h3>{L("Collected property values", "Valeurs collectées par propriété")}</h3>
    <p>{L("What each property actually contains, and whether the reserved <code>value</code> "
          "field is populated — which is what decides if a conversion can be attributed an "
          "amount.",
          "Ce que contient réellement chaque propriété, et si le champ réservé "
          "<code>value</code> est rempli — ce qui détermine si une conversion peut se voir "
          "attribuer un montant.")}</p>
    {ri.audit_event_properties_table(AUDIT, lang=lang)}
    """


# Every renderer above is a STUB carrying the blocks the gate requires, not a finished
# section — so `sections/<key>.py` must win over it. Without the flag an inline entry
# beats the file, and a section someone actually wrote never reaches the report: the
# gate ticked "exec summary present" on a build whose §2 still read TODO, because the
# scaffold's own stub was what it found. `r_cover` is exempt — it is meant to be filled
# in place, and there is no cover file to override it.
for _stub in (r_account_profile, r_exec_summary, r_inapp, r_recommendations, r_appx_events):
    _stub.is_placeholder = True


# Map every canonical key -> a renderer. Optional sections you don't need can be
# omitted entirely (they'll be skipped); non-optional sections left as `_todo`
# ship as N/A until you replace them.
#
# PRIOR-PERIOD COMPARISON (gate-enforced): every KPI hero tile / kpi_card in the
# exec summary and §4 volume, §5 engagement, §6 permission, §8b in-app and §14 email
# MUST carry a vs-prior-period comparison — a delta pill (delta + delta_good) or an
# explicit no_baseline=True note for un-windowable snapshots/aggregates. verify_report
# checks this; wire real prior values from audit.json (usage.prior / usage.deltas).
#
# KPI METHODOLOGY (gate-enforced): every tile in EVERY section also needs formula= +
# source=. Define shared tiles (sends, pressure, open rates) once as a factory function
# and reuse them, so a value and its stated method can never diverge across sections.
#
# TABLES (gate-enforced): every data table is <table class="grid"> — `ir-searchable` /
# `ir-sortable` / `ir-exportable` are behaviour hooks and must be paired with `grid`.
# Put figure-heavy prose into a `Signal | Value | Reading` table instead.
#
# ESCAPING (gate-enforced): components that escape their own input take PLAIN TEXT
# ("Service & transactional"); only note()/verdict()/sub_html_*/section bodies take
# raw HTML entities. Double-escaping renders a literal "&amp;" to the reader.
#
# EVENTS APPENDIX (gate-enforced): ri.audit_events_table must be accompanied by
# ri.audit_event_properties_table — see r_appx_events above. Names alone never show
# whether a taxonomy is usable; the collected values do.
#
# TWO WAYS TO SUPPLY A SECTION, and you can mix them freely:
#   1. inline here, as `"key": r_something` — best for short sections and for anything
#      that shares state with the rest of this file;
#   2. as `sections/<canonical_key>.py` exposing `render(ctx, lang)` — picked up
#      automatically by fw.load_sections() below. One file per section means several
#      authors (or parallel agents) never touch the same file, and a big builder stays
#      navigable. Helpers shared between sections go in `sections/_shared.py`.
# An inline renderer WINS over a file of the same name, so you can pin one section here
# while the rest live in files. A file named after a non-canonical key is a hard error.
INLINE = {
    "cover": r_cover,
    "brand_context": _todo,
    "account_profile": r_account_profile,   # MANDATORY: channel matrix + feature scorecard (gate-enforced)
    # "data_foundation": r_data_foundation,   # optional: enable if a tagging-plan audit is supplied
    #   -> when enabled, render ri.data_collection_table(FND["data_collection_recos"], lang)
    #      for a READABLE gaps/quick-wins table (never a raw bullet dump).
    "exec_summary": r_exec_summary,         # MANDATORY: >=2 KPI hero bands w/ prior-period deltas (gate-enforced)
    "benchmarks": _todo,
    "strategy": _todo,
    "volume_pressure": _todo,
    "engagement": _todo,
    "permission": _todo,
    "typology": _todo,
    "playbook": _todo,
    # "detected": r_detected,                 # optional sub-section
    "events": _todo,
    "inapp": r_inapp,                       # optional, but MUST open on the instrumentation grade
    "push_program": _todo,
    # "email_program": r_email,               # optional: only if email is active
    # "channels_exp": r_channels,             # optional: only with experiments or a 2nd channel
    # "best_practices": r_best_practices,     # optional: the shared scorecard, if wanted
    "recommendations": r_recommendations,    # MANDATORY: the action plan table (gate-enforced)
    "appendix": _todo,
    # "appendix_events": r_appx_events,        # optional data appendices (need audit)
    #   -> renders BOTH audit_events_table and audit_event_properties_table (gate-enforced)
    # "appendix_attrs": r_appx_attrs,
    # "appendix_campaigns": r_appx_camps,
}

RENDERERS = fw.load_sections(os.path.join(HERE, "sections"), INLINE)


def build(gate=True, pdf=False, bilingual=False, keep_raw=False):
    fw.set_pdf(pdf)                       # HTML is the deliverable; PDF on request
    # The primary language is rendered first whatever it is; assemble() takes the
    # primary pages positionally and reads `lang` for everything language-dependent.
    pages = fw.render_report(RENDERERS, Ctx(LANG), LANG)
    other = "fr" if LANG == "en" else "en"
    other_pages = (fw.render_report(RENDERERS, Ctx(other), other)
                   if bilingual else None)
    title = (f"{CLIENT} \u2014 Mobile Engagement Review (Airship)" if LANG == "en"
             else f"{CLIENT} \u2014 Revue d\u2019engagement mobile (Airship)")
    html_doc = fw.assemble(
        pages, other_pages,
        title=title,
        pdf_filename=PDF_FILENAME,
        lang=LANG)
    out = os.path.join(HERE, "report.html")
    # The canonical spine and the structural checks (charts render, a creative is
    # decoded, exec KPI bands, KPI methodology) BLOCK. The counts below — 6 charts,
    # 4 creatives — are targets reported as advisories, because a floor that mandates
    # a number gets satisfied with padding. Read the `!` lines; pass strict=True to
    # gate on them for a flagship deliverable.
    # `client=` also drops a dated, client-named copy in ~/Downloads once the
    # gate passes, so the report never has to be dug out of work/. That same step
    # retires the raw pulls under data/ — pass --keep-raw while still digging.
    fw.write_report(html_doc, out, gate=gate, en_pages=pages, fr_pages=other_pages,
                    charts_min=6, creatives_min=4, sections_min=16, client=CLIENT,
                    keep_raw=keep_raw)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-gate", action="store_true",
                    help="write the report without running the blocking delivery gate")
    ap.add_argument("--pdf", action="store_true",
                    help="also offer the PDF companion (sidebar download button); "
                         "then run scripts/build_report.py to produce the file")
    ap.add_argument("--bilingual", action="store_true",
                    help="ship both languages behind a toggle (LANG stays primary). "
                         "Doubles the section prose — only when both are read")
    ap.add_argument("--keep-raw", action="store_true",
                    help="keep the raw API pulls under data/ after a successful "
                         "build (they are dropped by default once the report is "
                         "delivered); use while still investigating the account")
    args = ap.parse_args()
    build(gate=not args.no_gate, pdf=args.pdf, bilingual=args.bilingual,
          keep_raw=args.keep_raw)
