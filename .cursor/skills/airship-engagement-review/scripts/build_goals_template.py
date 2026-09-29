#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GOALS REVIEW builder scaffold (light mode) — copy me for a new client.

    cp .cursor/skills/airship-engagement-review/scripts/build_goals_template.py \
       work/<client>/goals/build_report.py

Unlike the full-review scaffold, most sections here arrive already wired: the goals
review is deterministic on top of `goals.json`, so the tables, cards and charts are
built for you. What you replace is the PROSE — the verdicts, the brand reading, the
sequencing — which is the part a model writes and a template cannot.

Two things this deliverable must do, and every section should be written to serve
one of them:
  1. decide what to configure as a Goal now (\u00a74-\u00a76);
  2. name what the account cannot measure at all, and what to shape next (\u00a76-\u00a77).

The audience is an AIRSHIP client team about to run a conversation with the client,
not the client. Write for someone who will be asked "why that one?" in the meeting.

Differences from the full mode, all deliberate:
  * ENGLISH ONLY — no FR pages, no language toggle, no `-fr` section ids;
  * NO PDF — the HTML is the deliverable, so the download button is suppressed;
  * NO Reports API — every number comes from the tagging-plan audit, which counts
    OCCURRENCES and not unique channels. Say so; do not imply per-user rates.

Usage:
    python work/<client>/goals/build_report.py            # build + gate
    python work/<client>/goals/build_report.py --no-gate  # build without gating
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# When copied to work/<client>/goals/, the skill lives three levels up under .cursor/.
SKILL = os.path.join(HERE, "..", "..", "..", ".cursor", "skills",
                     "airship-engagement-review")
if not os.path.isdir(SKILL):
    SKILL = os.path.join(HERE, "..")          # running in-place from scripts/
sys.path.insert(0, os.path.join(SKILL, "scripts"))

import canonical_sections as cs             # noqa: E402
import report_interactive as ri             # noqa: E402
import report_framework as fw               # noqa: E402
import data_foundation as _df               # noqa: E402
from report_framework import NoData         # noqa: E402

# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------
CLIENT = "CLIENT_NAME"
PROJECT = "CLIENT PROD"
REGION = "EU"
VERTICAL = "Retail"                          # free text; resolved against the catalogue

TAGGING_PLAN = os.path.join(HERE, "..", "data", "tagging_plan.json")
GOALS_PATH = os.path.join(HERE, "goals.json")
SPECS_PATH = os.path.join(HERE, "specs.json")
BRAND_PATH = os.path.join(HERE, "brand.json")
CH = os.path.join(HERE, "charts")

AUDIT = _df.load(raw_path=TAGGING_PLAN, vertical=VERTICAL)
G = json.load(open(GOALS_PATH, encoding="utf-8")) if os.path.isfile(GOALS_PATH) else {}
SPECS = json.load(open(SPECS_PATH, encoding="utf-8")) if os.path.isfile(SPECS_PATH) else {}
BRAND = json.load(open(BRAND_PATH, encoding="utf-8")) if os.path.isfile(BRAND_PATH) else {}

CANDS = G.get("candidates") or []
PRIOR = G.get("priorities") or {}
FACTS = G.get("facts") or {}
CTX_V = (G.get("context") or {}).get("vertical") or {}


def kpi(key, default="\u2014"):
    """A number from goals.json's facts brief, so no section invents its own.

    Raises on an unknown key. A KPI card silently rendering an em dash because the
    builder asked for `goal_metrics_to_add` when the brief emits `roadmap_metrics` is
    exactly the failure the gate cannot see: the card is present, formatted and empty.
    """
    for k in FACTS.get("kpis") or []:
        if k.get("key") == key:
            v = k.get("value")
            if v is None:
                return default
            if k.get("unit") == "pct":
                return f"{v:g}%"
            return ri.fmt_int(v, "en") if isinstance(v, int) else str(v)
    if FACTS.get("kpis"):
        raise KeyError(
            f"unknown facts KPI {key!r} \u2014 goals.json emits: "
            + ", ".join(sorted(str(k.get('key')) for k in FACTS['kpis'])))
    return default


def chart(cid, alt=""):
    """Embed a goals chart; fails loudly if the spec or PNG is missing."""
    return fw.chart(cid, CH, SPECS, lang="en", alt=alt or cid)


class Ctx:
    """No bilingual switch here — the goals review is English-only."""
    lang = "en"
    EN = True

    def L(self, en, fr=None):
        return en


# --------------------------------------------------------------------------
# Sections
# --------------------------------------------------------------------------
def r_cover(ctx, lang):
    return fw.cover_section(
        brand_logo_html=ri.brand_logo("white", height=34, alt="Airship"),
        mark_uri=ri.brand_asset_datauri("airship_mark_blue.png"),
        badge_en="Conversion Goals Review", badge_fr="Conversion Goals Review",
        title_en=f"{CLIENT} {fw.EM} What to measure as a Goal",
        title_fr=f"{CLIENT} {fw.EM} What to measure as a Goal",
        sub_html_en=f"{PROJECT} &middot; {REGION} region",
        sub_html_fr=f"{PROJECT} &middot; {REGION} region",
        period_html_en="Source: <b>data-collection audit</b> (tagging plan) "
                       "&middot; no Reports API data in this review",
        period_html_fr="Source: <b>data-collection audit</b> (tagging plan) "
                       "&middot; no Reports API data in this review",
        kpis=[
            {"value": kpi("goal_candidates_activatable"),
             "label_en": "activatable goal candidates",
             "label_fr": "activatable goal candidates"},
            {"value": kpi("goal_candidates_native"),
             "label_en": "native Airship signals",
             "label_fr": "native Airship signals"},
            {"value": kpi("roadmap_metrics"),
             "label_en": "metrics worth adding",
             "label_fr": "metrics worth adding"},
        ],
        lang="en")


def r_brand_context(ctx, lang):
    """1 — the brand, its vertical, and what 'conversion' actually means here.

    TODO: replace the placeholder prose with the web research on the brand. Keep the
    north-star claim: everything downstream is ordered against it.
    """
    meaning = CTX_V.get("conversionMeaning") or "TODO"
    ns = (PRIOR.get("north_star") or {}).get("name")
    ns_html = (f'<div class="verdict"><b>Proposed north star.</b> '
               f'<code>{ri.html.escape(str(ns))}</code> \u2014 TODO: one sentence on why '
               f'this is the act {CLIENT} is judged on.</div>') if ns else ""
    return (
        f"<p>TODO: what {CLIENT} sells, to whom, and through which app journeys. "
        f"This is the paragraph that makes every recommendation below specific to "
        f"this brand rather than to its vertical in general.</p>"
        f'<p><b>Vertical:</b> {ri.html.escape(str(CTX_V.get("label") or VERTICAL))} '
        f'&middot; <b>Business model:</b> '
        f'{ri.html.escape(str(CTX_V.get("businessModel") or "TODO"))}</p>'
        f'<p><b>What conversion means here:</b> {ri.html.escape(str(meaning))}</p>'
        f"{ns_html}"
        + ri.goal_eligibility_matrix())


def r_data_foundation(ctx, lang):
    """2 — what the client actually collects (reuses the full mode's block)."""
    if not AUDIT.get("available"):
        raise NoData()
    fnd = _df.build_foundation(AUDIT)
    return (
        "<p>Everything in this review is derived from the client's data-collection "
        "audit. It records what is tracked and how often, which is enough to decide "
        "what could be a goal \u2014 and not enough to say how many people reach it.</p>"
        + ri.data_foundation_block(fnd, lang="en"))


def r_exec_summary(ctx, lang):
    """3 — the hero band, straight from facts.json so nothing drifts."""
    band = ri.hero_kpi_band([
        {"value": kpi("goal_candidates_activatable"),
         "label": "Activatable goal candidates", "no_baseline": True,
         "formula": "collected candidates + native Airship signals, excluding "
                    "anti-patterns",
         "source": "goals.json (data-collection audit)", "confidence": "high"},
        {"value": kpi("value_instrumentation_pct"),
         "label": "Conversion candidates carrying an amount", "no_baseline": True,
         "formula": "conversion-intent events with a populated monetary value / all "
                    "conversion-intent events",
         "source": "goals.json (data-collection audit)", "confidence": "medium"},
        {"value": kpi("blind_funnel_stages"),
         "label": "Funnel stages nothing can measure", "no_baseline": True,
         "formula": "funnel stages with no collected event and no native signal",
         "source": "goals.json (data-collection audit)", "confidence": "high"},
        {"value": kpi("roadmap_metrics"),
         "label": "Metrics worth adding", "no_baseline": True,
         "formula": "vertical archetypes with no matching tracked event",
         "source": "goals.json (data-collection audit)", "confidence": "medium"},
    ], lang="en")
    return (
        '<div class="verdict"><b>Verdict.</b> TODO \u2014 in two sentences, what this '
        'account can measure today and what it cannot.</div>'
        f"{band}"
        '<div class="note"><b>Read this number carefully.</b> The audit counts '
        'occurrences, not people. Nothing here is a per-user rate, and no penetration '
        'figure can be computed offline \u2014 configuring the goal is precisely what '
        'unlocks the Channels-per-goal and Goal-frequency-per-channel reports.</div>')


def r_goal_candidates(ctx, lang):
    """4 — family A: everything the client already collects, qualified."""
    if not CANDS:
        raise NoData()
    out = ['<div class="verdict"><b>What this taxonomy can already measure.</b> '
           "TODO \u2014 one paragraph reading the tables below: what the taxonomy covers "
           "well, and where it thins out.</div>"]
    for kind, title, blurb in (
            ("custom_event", "Custom events",
             "Every tracked custom event, whether or not it matches an Airship "
             "predefined name. A close name match is worth acting on: renaming to the "
             "standard unlocks the predefined property template."),
            ("tag", "Tag groups",
             "A goal can fire on GAINING a tag, which makes CRM-set tags usable as "
             "outcomes without any app work."),
            ("subscription_list", "Subscription lists",
             "Subscribing to a list is an act, and therefore a goal.")):
        tbl = ri.goal_candidates_table(CANDS, lang="en", kind=kind)
        if tbl:
            out.append(f"<h3>{title}</h3><p>{blurb}</p>{tbl}")
    return "".join(out)


def r_goal_qualification(ctx, lang):
    """5 — how to configure each one, and what must never be a goal."""
    if not CANDS:
        raise NoData()
    excluded = [c for c in CANDS if c.get("exclude")]
    anti = ri.goal_antipatterns_table(excluded, lang="en")
    anti_block = (f"<h3>What not to configure as a goal</h3>"
                  f"<p>Half the value of a shortlist is the list it excludes. "
                  f"A goal every user reaches ranks nobody; a goal on an act the brand "
                  f"wants LESS of optimises the wrong direction.</p>{anti}") if anti else ""
    return (
        "<p>Eligibility and configuration are different questions. The same act can be "
        "a count, a frequency over a period, or a threshold on a numeric property, and "
        "those are three different goals \u2014 picking the wrong one is the usual reason "
        "a configured goal ends up measuring nothing.</p>"
        + chart("goal_config_modes", "Configuration modes available")
        + ri.goal_config_table(CANDS, lang="en")
        + chart("goal_value_instrumentation", "Value instrumentation")
        + '<div class="note"><b>Amounts are not currencies.</b> Airship\u2019s reserved '
          '<code>value</code> field holds one number and strips symbols, so an amount '
          'without a companion currency property cannot be summed across markets.</div>'
        + anti_block)


def r_goal_plan(ctx, lang):
    """6 — the centre of the deliverable."""
    if not PRIOR:
        raise NoData()
    blind = PRIOR.get("blind_stages") or []
    blind_note = ""
    if blind:
        pitches = CTX_V.get("blindStagePitch") or {}
        items = "".join(
            f"<li><b>{ri.html.escape(ri._stage_label(s))}.</b> "
            f"{ri.html.escape(str(pitches.get(s) or 'Nothing tracked here, so no goal can watch this stage.'))}</li>"
            for s in blind)
        blind_note = (f'<div class="note note-warn"><b>Stages no goal can watch.</b>'
                      f"<ul>{items}</ul></div>")
    return (
        "<p>One goal the brand is judged on, and a thin layer of stage-level primaries "
        "beneath it. There is no fixed number of goals to hit \u2014 check the project\u2019s "
        "current ceiling in <i>Reports &gt; Goals</i> before promising a shortlist "
        "size.</p>"
        + ri.goal_priority_board(PRIOR, lang="en")
        + '<div class="verdict"><b>What to configure first, and why.</b> TODO \u2014 the '
          "north star in one sentence the client team can defend in the meeting, then "
          "the primary to switch on alongside it.</div>"
        + "<h3>Funnel coverage</h3>"
        + chart("goal_funnel_coverage", "Goal coverage by funnel stage")
        + ri.funnel_coverage_matrix(PRIOR.get("coverage"), lang="en",
                                    stages=G.get("funnel_stages"))
        + blind_note)


def r_goal_attributes(ctx, lang):
    """7 — attributes as goals, ahead of the feature landing."""
    attrs = G.get("attributes") or []
    if not attrs:
        raise NoData()
    return (
        "<p>Attribute-based goals are on the Airship roadmap. That makes the attribute "
        "taxonomy worth shaping now: an attribute that already reads as an outcome "
        "becomes a goal on day one, while one that stores a raw identifier never will."
        "</p>"
        + ri.attribute_goal_candidates_table(attrs, lang="en")
        + '<div class="note"><b>TODO.</b> Which of these the brand should prioritise, '
          'and what it would change in the messaging programme.</div>')


def r_recommendations(ctx, lang):
    """8 — sequencing, naming hygiene, and the questions to ask.

    The gate wants >= 6 <li> items here. They should be concrete and brand-specific:
    "configure X as the north star this week" beats "consider configuring goals".

    The questions are deliberately narrowed to THE GOALS THE PLAN SHOWS — the north
    star, the stage primaries and the diagnostics. Every ambiguous candidate raises
    one, and printing all of them turned the close of the report into a questionnaire
    the client team never gets through. The narrowing cannot be tighter than the
    board, though: the north star and the primaries are filled by the clearest acts
    an account has, so on a real plan they carry almost no open question, and the
    ambiguity that matters sits one tier down. Everything off the board stays in
    `goals.json`.
    """
    planned = {(PRIOR.get("north_star") or {}).get("name")}
    for picks in (PRIOR.get("primary") or {}).values():
        planned |= {c.get("name") for c in picks or []}
    planned |= {c.get("name") for c in PRIOR.get("secondary") or []}
    planned.discard(None)
    qs = ri.discovery_questions([q for q in (G.get("questions") or [])
                                 if q.get("name") in planned], lang="en")
    q_block = (f"<h3>Questions to put to the client</h3>"
               f"<p>A tagging plan gives names and counts, never intent. These are the "
               f"ambiguities on the goals the plan above puts forward \u2014 the ones to "
               f"settle before they are switched on. Every other open question the "
               f"review raised stays in <code>goals.json</code>.</p>{qs}") if qs else ""
    return (
        "<h3>Sequencing</h3>"
        "<ul>"
        "<li>TODO \u2014 configure the north star and what it unlocks immediately.</li>"
        "<li>TODO \u2014 the primary goals to add alongside it, by funnel stage.</li>"
        "<li>TODO \u2014 the property to add that lifts a blocker (currency, amount).</li>"
        "<li>TODO \u2014 the naming inconsistency to fix, and which name wins.</li>"
        "<li>TODO \u2014 the blind funnel stage to close first, and what it unlocks.</li>"
        "<li>TODO \u2014 what to review once the first goals have run for a month.</li>"
        "</ul>"
        + q_block)


def r_appendix(ctx, lang):
    """9 — how Airship goals work, how this was produced, and what it cannot say."""
    limits = G.get("product_limits") or {}
    reports = G.get("goal_reports") or []
    caveats = G.get("caveats") or []
    rep_rows = "".join(
        f'<tr><td><b>{ri.html.escape(str(r.get("name") or ""))}</b></td>'
        f'<td class="small">{ri.html.escape(str(r.get("gives") or ""))}</td></tr>'
        for r in reports)
    lim_rows = "".join(
        "<tr><td><b>" + ri.html.escape(k) + "</b></td><td>"
        + (ri.fmt_int(v.get("value"), "en") if isinstance(v.get("value"), int)
           else "\u2014")
        + '</td><td class="small">' + ri.html.escape(str(v.get("note") or ""))
        + "</td></tr>"
        for k, v in limits.items())
    cav = "".join(f"<li>{ri.html.escape(str(c))}</li>" for c in caveats)
    return (
        "<h3>What the Goals reports give you once a goal is configured</h3>"
        '<table class="grid"><thead><tr><th>Report</th><th>What it answers</th></tr>'
        f"</thead><tbody>{rep_rows}</tbody></table>"
        "<h3>Product limits worth knowing</h3>"
        '<table class="grid"><thead><tr><th>Limit</th><th>Value</th><th>Why it matters</th>'
        f"</tr></thead><tbody>{lim_rows}</tbody></table>"
        "<h3>Method &amp; limits of this review</h3>"
        "<p>Produced offline from the client's data-collection audit plus public "
        "research on the brand and its vertical. No Airship Reports API call was made, "
        "so this report says nothing about sends, opens or campaign performance.</p>"
        f"<ul>{cav}</ul>")


def r_appx_events(ctx, lang):
    """10 — the exhaustive event appendix (both tables; the gate pairs them)."""
    if not AUDIT.get("available"):
        raise NoData()
    return (
        "<p>Every tracked custom event, with its source, category, occurrences and the "
        "state of the reserved <code>value</code> field.</p>"
        + ri.audit_events_table(AUDIT, lang="en")
        + "<h3>Collected property values</h3>"
        "<p>Property names never prove a taxonomy is usable; the values do. A clean "
        "enum can drive a goal breakdown, a 200-distinct free-text blob cannot.</p>"
        + ri.audit_event_properties_table(AUDIT, lang="en"))


def r_appx_attrs(ctx, lang):
    """11 — attributes, tags, subscription lists, screens."""
    if not AUDIT.get("available"):
        raise NoData()
    out = ["<p>The rest of the collected taxonomy, in full. Tags and subscription "
           "lists are goal sources in their own right; attributes are the material for "
           "the attribute-based goals covered in \u00a77.</p>"]
    for title, tbl in (("Attributes", ri.audit_attributes_table(AUDIT, lang="en")),
                       ("Tags", ri.audit_tags_table(AUDIT, lang="en")),
                       ("Subscription lists", ri.audit_subscriptions_table(AUDIT, lang="en")),
                       ("Screens", ri.audit_screens_table(AUDIT, lang="en"))):
        if tbl:
            out.append(f"<h3>{title}</h3>{tbl}")
    return "".join(out)


INLINE = {
    "cover": r_cover,
    "brand_context": r_brand_context,
    "data_foundation": r_data_foundation,
    "exec_summary": r_exec_summary,
    "goal_candidates": r_goal_candidates,
    "goal_qualification": r_goal_qualification,
    "goal_plan": r_goal_plan,
    "goal_attributes": r_goal_attributes,
    "recommendations": r_recommendations,
    "appendix": r_appendix,
    "appendix_events": r_appx_events,
    "appendix_attrs": r_appx_attrs,
}

RENDERERS = fw.load_sections(os.path.join(HERE, "sections"), INLINE,
                             sections=cs.GOALS_SECTIONS)


def build(gate=True, keep_raw=False):
    pages = fw.render_report(RENDERERS, Ctx(), "en", sections=cs.GOALS_SECTIONS)
    html_doc = fw.assemble(
        pages, None,                                   # monolingual: no FR pages
        title=f"{CLIENT} \u2014 Conversion Goals Review (Airship)",
        pdf_filename=None, pdf_button=False,           # HTML is the deliverable
        lang="en")
    out = os.path.join(HERE, "goals_review.html")
    # `client=` also drops a dated, client-named copy in ~/Downloads once the
    # gate passes, so the report never has to be dug out of work/. Mode B reads the
    # parsed tagging plan, which the retention rule keeps; there is rarely a raw pull
    # here to retire, and --keep-raw is wired for symmetry with the full review.
    fw.write_report(html_doc, out, gate=gate, en_pages=pages,
                    profile="goals", sections=cs.GOALS_SECTIONS, client=CLIENT,
                    keep_raw=keep_raw)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-gate", action="store_true",
                    help="write the report without running the blocking delivery gate")
    ap.add_argument("--keep-raw", action="store_true",
                    help="keep any raw API pulls under data/ after a successful build")
    args = ap.parse_args()
    build(gate=not args.no_gate, keep_raw=args.keep_raw)
