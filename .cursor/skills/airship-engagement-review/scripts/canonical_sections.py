#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Single source of truth for the engagement-review CANONICAL SECTION SPINE.

Both the report builder (via ``report_framework.render_report``) and the delivery
gate (``verify_report.py``) import this module, so the structure a report ships and
the structure the gate enforces can never drift apart.

Each entry in ``CANONICAL_SECTIONS`` is an ordered section spec:

  key            stable identifier (used to look up a renderer + N/A reason)
  num            canonical number/label prefix shown in the <h2> ("3b", "8-10", …);
                 "" for the cover
  id             HTML anchor id (FR copies get a "-fr" suffix at assembly time)
  toc_en/toc_fr  sidebar label (goes in data-toc / data-toc-fr)
  title_en/fr    the <h2> title (without the number prefix)
  optional       True  -> scaffold MAY skip it when no renderer is supplied
                 False -> ALWAYS emitted; if a renderer returns no body the
                          framework auto-emits a standard "N/A (reason)" block
  gate_required  True  -> counted by verify_report's canonical-structure check
                          (the sections that make a report "complete"; the gate's
                          default floor derives from how many there are, so
                          demoting one relaxes the count automatically)
  sub            True  -> a sub-section (data-toc-sub="1"): indented in the TOC
  raw            True  -> the renderer returns a full <section> (only the cover)
  match          regex list the gate uses to detect the section from data-toc
  na_en/na_fr    default N/A reason when the section has no data on this account
  std_charts     chart ids this section usually embeds (hints for make_charts +
                 the gate's generated-vs-embedded cross-check)

Adding/removing/renumbering a canonical section is a one-line edit HERE — every
builder and the gate follow automatically.

**Which sections are mandatory is a judgement, and it is recorded here.** A section
earns `gate_required` by measuring *this* account: its pressure, its engagement, its
permissions, its events, its recommendations. A section that would read the same for
any client in the vertical does not, however useful it is to have available — it
becomes optional, and an account with nothing to say simply omits it rather than
shipping an N/A block wearing a section number. `strategy` and `playbook` stay
mandatory despite drawing on shared material, because what they publish is the
account's own reading of it; see the comments on each.
"""
from __future__ import annotations

# The standard interactive chart set. make_charts.py should generate all of these
# (a client with an inactive channel simply omits that one, e.g. email_funnel).
STD_CHARTS = [
    "sends_daily", "opens_daily", "pressure_fatigue", "permission_flow",
    "base_platform", "channel_mix", "email_funnel", "top_events",
]

CANONICAL_SECTIONS = [
    dict(key="cover", num="", id="cover", raw=True, optional=False, gate_required=False,
         toc_en="Cover", toc_fr="Couverture", title_en="", title_fr="", match=[]),

    dict(key="brand_context", num="1", id="context", optional=False, gate_required=True,
         toc_en="1. Brand & context", toc_fr="1. Marque & contexte",
         title_en="Brand & business context", title_fr="Contexte marque & business",
         match=[r"context|contexte|brand|marque"],
         na_en="Brand context not supplied.", na_fr="Contexte marque non fourni."),

    dict(key="account_profile", num="2", id="adoption", optional=False, gate_required=True,
         toc_en="2. Account profile", toc_fr="2. Profil de compte",
         title_en="Account profile & Airship adoption",
         title_fr="Profil de compte & adoption Airship",
         match=[r"account profile|profil de compte|adoption"],
         na_en="Account/adoption data unavailable.",
         na_fr="Données de compte/adoption indisponibles."),

    dict(key="data_foundation", num="2b", id="foundation", optional=True, gate_required=False,
         toc_en="2b. Data foundation", toc_fr="2b. Socle de données",
         title_en="Data foundation & tracking coverage",
         title_fr="Fondation data & couverture de tracking",
         match=[r"data foundation|socle de donn|fondation data"],
         na_en="No tagging-plan audit supplied.",
         na_fr="Aucun audit de plan de taggage fourni."),

    dict(key="exec_summary", num="3", id="summary", optional=False, gate_required=True,
         toc_en="3. Executive summary", toc_fr="3. Synthèse exécutive",
         title_en="Executive summary", title_fr="Synthèse exécutive",
         match=[r"executive summary|synth[eè]se"],
         na_en="Executive summary not generated.", na_fr="Synthèse non générée."),

    dict(key="benchmarks", num="3b", id="bench", optional=False, gate_required=True,
         toc_en="3b. Benchmarks & reach", toc_fr="3b. Benchmarks & portée",
         title_en="Benchmark scorecard & reachability",
         title_fr="Scorecard benchmarks & reachabilité",
         match=[r"benchmark|reach|port[eé]e"],
         na_en="Benchmark / reachability data unavailable.",
         na_fr="Données benchmarks / portée indisponibles."),

    # Stays mandatory. It draws on the shared maturity model, which makes it look like
    # a candidate for demotion alongside best_practices — it is not. This is where the
    # benchmark reading becomes an argument about *this* account, and it is what the
    # exec summary and the recommendations both build on. Cutting it leaves a report
    # that measures without concluding.
    dict(key="strategy", num="3c", id="strategy", optional=False, gate_required=True,
         toc_en="3c. Strategy & maturity", toc_fr="3c. Stratégie & maturité",
         title_en="Strategic priorities & maturity matrix",
         title_fr="Priorités stratégiques & matrice de maturité",
         match=[r"strateg|strat[eé]g|maturit|priorit"],
         na_en="Strategy layer not generated.", na_fr="Couche stratégie non générée."),

    # Optional, and only for an account reviewed alongside a sibling app of the same
    # brand. It exists because the comparison has to live somewhere the reader can cite,
    # and because the honest version of it is mostly a statement of what may NOT be
    # compared: two apps rarely share a peer cohort, so their rates are not each other's
    # benchmark. Sizing a gap between two apps is the failure mode this section prevents.
    dict(key="cross_app", num="3d", id="cross", optional=True, gate_required=False,
         toc_en="3d. Cross-app comparison", toc_fr="3d. Comparaison inter-apps",
         title_en="Cross-app comparison", title_fr="Comparaison inter-apps",
         match=[r"cross.?app|comparaison inter|inter.?apps?"],
         na_en="No sibling app reviewed alongside this one.",
         na_fr="Aucune app sœur analysée en parallèle."),

    dict(key="volume_pressure", num="4", id="pressure", optional=False, gate_required=True,
         toc_en="4. Volume & pressure", toc_fr="4. Volume & pression",
         title_en="Volume & marketing pressure", title_fr="Volume & pression marketing",
         match=[r"volume|pressure|pression"],
         na_en="Send-volume / pressure data unavailable.",
         na_fr="Données volume d’envoi / pression indisponibles.",
         std_charts=["sends_daily", "pressure_fatigue", "channel_mix"]),

    # Optional spill-over for §4: accounts whose sends arrive in bursts rather than
    # on a cadence need a whole page for the delivery-shape analysis (burst table,
    # hour-of-day profile). Omit it and §4 keeps everything, as before.
    dict(key="delivery_shape", num="4b", id="shape", sub=True, optional=True,
         gate_required=False,
         toc_en="4b. Delivery shape", toc_fr="4b. Forme de la diffusion",
         title_en="Delivery shape — when sends actually happen",
         title_fr="Forme de la diffusion — quand les envois ont vraiment lieu",
         match=[r"burst|rafale|delivery shape|forme de la diffusion|hour|horaire"],
         na_en="Delivery-shape data unavailable.",
         na_fr="Données de forme de diffusion indisponibles."),

    dict(key="engagement", num="5", id="engagement", optional=False, gate_required=True,
         toc_en="5. Engagement (opens)", toc_fr="5. Engagement (ouvertures)",
         title_en="Engagement — app opens", title_fr="Engagement — ouvertures app",
         match=[r"engagement|opens|ouvertures"],
         na_en="Opens/engagement data unavailable.",
         na_fr="Données d’ouvertures/engagement indisponibles.",
         std_charts=["opens_daily"]),

    dict(key="permission", num="6", id="permission", optional=False, gate_required=True,
         toc_en="6. Permission & base", toc_fr="6. Permission & base",
         title_en="Permission & installed base", title_fr="Permission & parc installé",
         match=[r"permission|base"],
         na_en="Permission / installed-base data unavailable.",
         na_fr="Données permission / parc installé indisponibles.",
         std_charts=["permission_flow", "base_platform"]),

    dict(key="typology", num="7", id="typology", optional=False, gate_required=True,
         toc_en="7. Campaign typology", toc_fr="7. Typologie des campagnes",
         title_en="Campaign typology (per channel)",
         title_fr="Typologie des campagnes (par canal)",
         match=[r"typolog"],
         na_en="Campaign inventory unavailable — typology cannot be reconstructed.",
         na_fr="Inventaire de campagnes indisponible — typologie non reconstructible."),

    dict(key="playbook", num="7b", id="playbook", optional=False, gate_required=True,
         toc_en="7b. Playbook & personalization", toc_fr="7b. Playbook & personnalisation",
         title_en="Campaign playbook & personalization depth",
         title_fr="Playbook campagnes & profondeur de personnalisation",
         match=[r"playbook|coverage|couverture|personaliz|personnalis"],
         na_en="Playbook coverage unavailable.", na_fr="Couverture playbook indisponible."),

    dict(key="detected", num="7c", id="detected", sub=True, optional=True, gate_required=False,
         toc_en="7c. Detected campaigns", toc_fr="7c. Campagnes détectées",
         title_en="Detected campaigns & mapping reliability",
         title_fr="Campagnes détectées & fiabilité du mapping",
         match=[r"detected campaign|campagnes d[eé]tect"],
         na_en="No detected-campaign table.", na_fr="Pas de table de campagnes détectées."),

    dict(key="events", num="8-10", id="events", optional=False, gate_required=True,
         toc_en="8-10. Conversion & events", toc_fr="8-10. Conversion & événements",
         title_en="Conversion, events & attribution",
         title_fr="Conversion, événements & attribution",
         match=[r"conversion|events|[eé]v[eé]nements"],
         na_en="Custom-event / conversion data unavailable.",
         na_fr="Données événements custom / conversion indisponibles.",
         std_charts=["top_events"]),

    # `optional` only because plenty of accounts run no in-app at all. As soon as the audit
    # records in-app volume the gate makes this section required, and requires a Scene
    # instrumentation grade in it — see reference.md, "Scene instrumentation".
    dict(key="inapp", num="8b", id="inapp", sub=True, optional=True, gate_required=False,
         toc_en="8b. In-app & Message Center", toc_fr="8b. In-app & Message Center",
         title_en="In-app & Message Center messages",
         title_fr="Messages in-app & Message Center",
         match=[r"in-app|message center|messagerie"],
         na_en="No in-app / Message Center activity.",
         na_fr="Aucune activité in-app / Message Center."),

    dict(key="push_program", num="13", id="push", optional=False, gate_required=True,
         toc_en="13. Push program", toc_fr="13. Programme push",
         title_en="Push program (iOS / Android / web)",
         title_fr="Programme push (iOS / Android / web)",
         match=[r"push program|programme push"],
         na_en="Push-program metrics unavailable.",
         na_fr="Métriques du programme push indisponibles."),

    dict(key="email_program", num="14", id="email", optional=True, gate_required=False,
         toc_en="14. Email program", toc_fr="14. Programme email",
         title_en="Email program", title_fr="Programme email",
         match=[r"email program|programme email"],
         na_en="Email is inactive on this project (0 sends).",
         na_fr="L’email est inactif sur ce projet (0 envoi)."),

    # Demoted to optional: what this section carries is largely generic — a creative
    # coverage note and a list of channels the account does not use. On an account
    # with no experiments and one channel it is an N/A block wearing a section
    # number. Ship it when there is something to compare; omit it otherwise.
    dict(key="channels_exp", num="11-12", id="exp", optional=True, gate_required=False,
         toc_en="11-12. Experiments & channels", toc_fr="11-12. Expériences & canaux",
         title_en="Experiments, creative coverage & other channels",
         title_fr="Expériences, créas & autres canaux",
         match=[r"experiment|exp[eé]rience|channel|canaux|creativ|cr[eé]a"],
         na_en="No experiments / creatives / other-channel data.",
         na_fr="Aucune donnée expériences / créas / autres canaux."),

    # Demoted to optional: a best-practice scorecard is the same scorecard for every
    # account, and the account-specific reading of it already lives in `strategy` and
    # `recommendations`. Kept available because it is a useful artefact to hand a
    # client team — just not something a report FAILS for lacking.
    dict(key="best_practices", num="15b", id="bp", optional=True, gate_required=False,
         toc_en="15b. Best-practices", toc_fr="15b. Bonnes pratiques",
         title_en="Engagement best-practices scorecard",
         title_fr="Tableau des bonnes pratiques",
         match=[r"best.?practice|bonnes pratiques"],
         na_en="Best-practices scorecard not generated.",
         na_fr="Tableau des bonnes pratiques non généré."),

    dict(key="recommendations", num="16", id="reco", optional=False, gate_required=True,
         toc_en="16. Recommendations", toc_fr="16. Recommandations",
         title_en="Recommendations", title_fr="Recommandations",
         match=[r"recommend|recommand"],
         na_en="Recommendations not generated.", na_fr="Recommandations non générées."),

    dict(key="appendix", num="17", id="method", optional=False, gate_required=True,
         toc_en="17. Appendix", toc_fr="17. Annexe",
         title_en="Appendix — sources, methodology & glossary",
         title_fr="Annexe — sources, méthodologie & glossaire",
         match=[r"appendix|annexe|method|m[eé]thod"],
         na_en="Methodology appendix not generated.",
         na_fr="Annexe méthodologie non générée."),

    dict(key="appendix_events", num="18", id="appx_events", optional=True, gate_required=False,
         toc_en="18. Data appendix — events", toc_fr="18. Annexe data — événements",
         title_en="Data appendix — tracked custom events",
         title_fr="Annexe data — événements custom trackés",
         match=[r"appendix.*event|annexe.*[eé]v[eé]nement"],
         na_en="No tagging-plan audit — event appendix omitted.",
         na_fr="Pas d’audit — annexe événements omise."),

    dict(key="appendix_attrs", num="19", id="appx_attrs", optional=True, gate_required=False,
         toc_en="19. Data appendix — attributes & more",
         toc_fr="19. Annexe data — attributs & +",
         title_en="Data appendix — attributes, tags & screens",
         title_fr="Annexe data — attributs, tags & écrans",
         match=[r"appendix.*attribut|annexe.*attribut"],
         na_en="No tagging-plan audit — attribute appendix omitted.",
         na_fr="Pas d’audit — annexe attributs omise."),

    dict(key="appendix_campaigns", num="20", id="appx_camps", optional=True, gate_required=False,
         toc_en="20. Data appendix — campaigns", toc_fr="20. Annexe data — campagnes",
         title_en="Data appendix — detected campaigns & classification",
         title_fr="Annexe data — campagnes détectées & classification",
         match=[r"appendix.*campaign|annexe.*campagne"],
         na_en="Campaign inventory unavailable.", na_fr="Inventaire de campagnes indisponible."),
]

# Fast lookup by key.
BY_KEY = {s["key"]: s for s in CANONICAL_SECTIONS}


# ---------------------------------------------------------------------------
# SECOND SPINE — "Goals review" (light mode).
#
# A conversion-only review built from the tagging-plan audit alone: no Reports
# API, no campaign inventory, no creatives. Its reader is an Airship client team
# preparing a conversation with the client, so the report answers one question —
# what to configure as a Goal now — and shows, stage by stage, what the account
# cannot measure at all.
#
# This mode renders in ENGLISH ONLY. The spec schema still requires the *_fr
# fields (the framework reads them unconditionally), so they mirror the English:
# nothing ever renders them, and no French pages are assembled.
GOALS_SECTIONS = [
    dict(key="cover", num="", id="cover", raw=True, optional=False, gate_required=False,
         toc_en="Cover", toc_fr="Cover", title_en="", title_fr="", match=[]),

    dict(key="brand_context", num="1", id="context", optional=False, gate_required=True,
         toc_en="1. Brand & conversion context", toc_fr="1. Brand & conversion context",
         title_en="Brand, vertical & what conversion means here",
         title_fr="Brand, vertical & what conversion means here",
         match=[r"brand|context"],
         na_en="Brand context not supplied.", na_fr="Brand context not supplied."),

    dict(key="data_foundation", num="2", id="foundation", optional=False, gate_required=True,
         toc_en="2. Data foundation", toc_fr="2. Data foundation",
         title_en="Data foundation — what the client actually collects",
         title_fr="Data foundation — what the client actually collects",
         match=[r"data foundation"],
         na_en="No tagging-plan audit supplied.", na_fr="No tagging-plan audit supplied."),

    dict(key="exec_summary", num="3", id="summary", optional=False, gate_required=True,
         toc_en="3. Executive summary", toc_fr="3. Executive summary",
         title_en="Executive summary", title_fr="Executive summary",
         match=[r"executive summary"],
         na_en="Executive summary not generated.", na_fr="Executive summary not generated."),

    dict(key="goal_candidates", num="4", id="candidates", optional=False, gate_required=True,
         toc_en="4. Goal candidates", toc_fr="4. Goal candidates",
         title_en="Goal candidates — what the client already collects",
         title_fr="Goal candidates — what the client already collects",
         match=[r"goal candidates"],
         na_en="No collected data qualifies as a goal candidate.",
         na_fr="No collected data qualifies as a goal candidate."),

    dict(key="goal_qualification", num="5", id="qualification", optional=False,
         gate_required=True,
         toc_en="5. How to configure each goal",
         toc_fr="5. How to configure each goal",
         title_en="Goal qualification — count, frequency or numeric threshold",
         title_fr="Goal qualification — count, frequency or numeric threshold",
         match=[r"how to configure|qualification"],
         na_en="Qualification layer not generated.",
         na_fr="Qualification layer not generated.",
         std_charts=["goal_config_modes", "goal_value_instrumentation"]),

    dict(key="goal_plan", num="6", id="plan", optional=False, gate_required=True,
         toc_en="6. The goal plan", toc_fr="6. The goal plan",
         title_en="The goal plan — north star, primaries & blind spots",
         title_fr="The goal plan — north star, primaries & blind spots",
         match=[r"goal plan"],
         na_en="Goal plan not generated.", na_fr="Goal plan not generated.",
         std_charts=["goal_funnel_coverage"]),

    dict(key="goal_attributes", num="7", id="attr_goals", optional=False, gate_required=True,
         toc_en="7. Attributes as future goals", toc_fr="7. Attributes as future goals",
         title_en="Attributes as goals — preparing for attribute-based goals",
         title_fr="Attributes as goals — preparing for attribute-based goals",
         match=[r"attributes as (future )?goal"],
         na_en="No attribute qualifies as a future goal.",
         na_fr="No attribute qualifies as a future goal."),

    dict(key="recommendations", num="8", id="reco", optional=False, gate_required=True,
         toc_en="8. Recommendations & questions",
         toc_fr="8. Recommendations & questions",
         title_en="Recommendations, naming hygiene & questions for the client",
         title_fr="Recommendations, naming hygiene & questions for the client",
         match=[r"recommend"],
         na_en="Recommendations not generated.", na_fr="Recommendations not generated."),

    dict(key="appendix", num="9", id="method", optional=False, gate_required=True,
         toc_en="9. Appendix — method & goal mechanics",
         toc_fr="9. Appendix — method & goal mechanics",
         title_en="Appendix — Airship goal mechanics, method, limits & sources",
         title_fr="Appendix — Airship goal mechanics, method, limits & sources",
         match=[r"appendix.*(method|goal mechanic)"],
         na_en="Methodology appendix not generated.",
         na_fr="Methodology appendix not generated."),

    dict(key="appendix_events", num="10", id="appx_events", optional=False, gate_required=True,
         toc_en="10. Data appendix — events", toc_fr="10. Data appendix — events",
         title_en="Data appendix — tracked custom events",
         title_fr="Data appendix — tracked custom events",
         match=[r"appendix.*event"],
         na_en="No tracked custom events in the audit.",
         na_fr="No tracked custom events in the audit."),

    dict(key="appendix_attrs", num="11", id="appx_attrs", optional=False, gate_required=True,
         toc_en="11. Data appendix — attributes, tags & lists",
         toc_fr="11. Data appendix — attributes, tags & lists",
         title_en="Data appendix — attributes, tags, subscription lists & screens",
         title_fr="Data appendix — attributes, tags, subscription lists & screens",
         match=[r"appendix.*attribut"],
         na_en="No attributes, tags or lists in the audit.",
         na_fr="No attributes, tags or lists in the audit."),
]

GOALS_BY_KEY = {s["key"]: s for s in GOALS_SECTIONS}

# The chart set the goals mode generates (goals_charts.py). Same role as STD_CHARTS.
GOALS_CHARTS = [
    "goal_funnel_coverage", "goal_value_instrumentation", "goal_config_modes",
]

# ---------------------------------------------------------------------------
# Sidebar-only thematic clusters ("arborescence" eyebrow groups). SCREEN ONLY —
# these never touch the report body or the PDF. Data-driven so future clients can
# re-cluster with a one-line edit:
#   * CLUSTERS       ordered list of clusters, each with a bilingual eyebrow label
#   * CLUSTER_OF     maps a canonical section key -> cluster id
#   * DEFAULT_CLUSTER fallback so an unknown/new section still shows up in the tree
# Clusters follow the canonical section ORDER (each cluster is a contiguous run),
# so every cluster yields exactly one eyebrow in the sidebar. To add a section to a
# cluster, add one CLUSTER_OF entry; to add a cluster, append to CLUSTERS + point
# the relevant keys at it. The client JS reads window.IR_CLUSTERS (emitted at
# assembly time) and window's data-toc-cluster attribute on each section.
CLUSTERS = [
    dict(id="overview",   label_en="Overview",              label_fr="Vue d’ensemble"),
    dict(id="engagement", label_en="Engagement & pressure", label_fr="Engagement & pression"),
    dict(id="conversion", label_en="Campaigns & conversion", label_fr="Campagnes & conversion"),
    dict(id="reco",       label_en="Playbook & reco",       label_fr="Playbook & reco"),
    dict(id="appendix",   label_en="Appendix",              label_fr="Annexe"),
]

CLUSTER_OF = {
    # Overview: who they are, how they've adopted Airship, the headline read
    "cover": "overview", "brand_context": "overview", "account_profile": "overview",
    "data_foundation": "overview", "exec_summary": "overview",
    "benchmarks": "overview", "strategy": "overview", "cross_app": "overview",
    # Engagement & pressure: how much they send and how it lands
    "volume_pressure": "engagement", "delivery_shape": "engagement",
    "engagement": "engagement", "permission": "engagement",
    # Campaigns & conversion: what they send and what it drives
    "typology": "conversion", "playbook": "conversion", "detected": "conversion",
    "events": "conversion", "inapp": "conversion", "push_program": "conversion",
    "email_program": "conversion", "channels_exp": "conversion",
    # Goals-review sections (light mode) — same clusters, so the sidebar tree
    # behaves identically under either spine.
    "goal_candidates": "conversion", "goal_qualification": "conversion",
    "goal_plan": "conversion", "goal_attributes": "reco",
    # Best-practice scorecard + recommendations
    "best_practices": "reco", "recommendations": "reco",
    # Data appendices / methodology
    "appendix": "appendix", "appendix_events": "appendix",
    "appendix_attrs": "appendix", "appendix_campaigns": "appendix",
}

DEFAULT_CLUSTER = "overview"


def cluster_of(key: str) -> str:
    """Cluster id for a section key (falls back to DEFAULT_CLUSTER)."""
    return CLUSTER_OF.get(key, DEFAULT_CLUSTER)


def clusters_i18n() -> dict:
    """{cluster_id: {"en": label, "fr": label}} — emitted as window.IR_CLUSTERS."""
    return {c["id"]: {"en": c["label_en"], "fr": c["label_fr"]} for c in CLUSTERS}

# The subset the delivery gate enforces (the "complete report" contract). Kept as
# (key, [patterns]) tuples so verify_report's canonical_check stays byte-identical.
GATE_SECTIONS = [(s["key"], s["match"]) for s in CANONICAL_SECTIONS if s.get("gate_required")]

# Same contract for the goals spine, selected by `verify_report.py --profile goals`.
GOALS_GATE_SECTIONS = [(s["key"], s["match"]) for s in GOALS_SECTIONS
                       if s.get("gate_required")]

# Spine + gate set by profile name, so callers pass a string instead of importing
# the right pair of module globals.
PROFILES = {
    "full": {"sections": CANONICAL_SECTIONS, "by_key": BY_KEY,
             "gate": GATE_SECTIONS, "charts": STD_CHARTS, "bilingual": True},
    "goals": {"sections": GOALS_SECTIONS, "by_key": GOALS_BY_KEY,
              "gate": GOALS_GATE_SECTIONS, "charts": GOALS_CHARTS, "bilingual": False},
}


def profile(name: str = "full") -> dict:
    """Spine bundle for a report profile ("full" or "goals")."""
    return PROFILES.get(name or "full", PROFILES["full"])


# Every section key either spine can legitimately emit — used by the framework to
# validate section filenames without hard-coding which mode is running.
ALL_KEYS = {s["key"] for s in CANONICAL_SECTIONS} | {s["key"] for s in GOALS_SECTIONS}


if __name__ == "__main__":  # pragma: no cover - structural self-check
    import re as _re
    seen = set()
    for spine, label in ((CANONICAL_SECTIONS, "full"), (GOALS_SECTIONS, "goals")):
        keys = [s["key"] for s in spine]
        assert len(keys) == len(set(keys)), f"{label}: duplicate section key"
        for s in spine:
            for f in ("key", "num", "id", "toc_en", "toc_fr", "title_en", "title_fr"):
                assert f in s, f"{label}/{s.get('key')}: missing {f}"
            assert s.get("raw") or ("na_en" in s and "na_fr" in s), \
                f"{label}/{s['key']}: missing N/A copy"
    # Every gate pattern must match its own TOC label, or the gate reports a
    # section missing from a report that ships it.
    for spine, gate in ((CANONICAL_SECTIONS, GATE_SECTIONS),
                        (GOALS_SECTIONS, GOALS_GATE_SECTIONS)):
        by_key = {s["key"]: s for s in spine}
        for key, pats in gate:
            lbl = by_key[key]["toc_en"]
            assert any(_re.search(p, lbl, _re.I) for p in pats), \
                f"{key}: no pattern matches its own label {lbl!r}"
        seen.add(len(gate))
    for k in ("goal_candidates", "goal_qualification", "goal_plan",
              "goal_attributes"):
        assert k in CLUSTER_OF, f"{k} missing from CLUSTER_OF"
    print(f"canonical spine OK — full: {len(CANONICAL_SECTIONS)} sections / "
          f"{len(GATE_SECTIONS)} gated; goals: {len(GOALS_SECTIONS)} sections / "
          f"{len(GOALS_GATE_SECTIONS)} gated")
