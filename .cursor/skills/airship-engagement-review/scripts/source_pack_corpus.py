#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tier 1 of the source pack — the semantics, without which the figures get read wrong.

Four of the seven tier-1 documents are **verbatim extracts** of the skill's own reference
books; two are generated from ``build_facts.KPI_SPECS``; the README is assembled last by
``source_pack_docs`` because it has to list what actually shipped.

**Why verbatim rather than summarised.** The whole corpus is ~30,000 words
(``reference.md`` 14,120 · ``analysis-spec.md`` 4,075 · ``data-collection-by-vertical.md``
3,734 · ``campaign_playbook.md`` 2,969 · ``event_catalog.md`` 2,146 · ``benchmarks.md``
1,613) against a 500,000-word-per-source ceiling. There is no budget reason to
paraphrase, and two reasons not to: a paraphrase drifts the first time the skill is
updated, and ``check_no_client_names.py`` already guarantees this material carries no
client name, which a freshly written summary would not.

**Why an allow-list rather than whole files.** ``reference.md`` also carries build
machinery — MCP setup, brand colours, the i18n contract, the PDF page rules — which
teaches a notebook nothing about the account and dilutes retrieval. ``EXCLUDED`` records
that these were considered and dropped, so the omission is a decision on the record
rather than an oversight.

**The extraction fails loudly.** A renamed H2 raises ``MissingSectionError`` instead of
quietly shipping a thinner referential — the same rule as ``MissingChartError`` in
``report_framework.chart()``. A context document that vanishes in silence is worse than
an error, because the notebook keeps answering confidently on an incomplete base.

Language: tier 1 stays in **English**, its source language. The account documents (tiers
2 and 3) follow ``--lang``. Half-translating a definitions corpus is the one outcome
worse than having it in a single language.
"""
from __future__ import annotations

import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)

from build_facts import KPI_SPECS  # noqa: E402
from source_pack_docs import T, provenance  # noqa: E402

TIER1_FILES = (
    "00_README_pack.md",
    "01_endpoints_reports_api.md",
    "02_definitions_et_perimetre.md",
    "03_fiches_metriques.md",
    "04_limites_et_inferences_interdites.md",
    "05_comment_lire_les_benchmarks.md",
    "06_referentiels_metier.md",
)


class MissingSectionError(RuntimeError):
    """An allow-listed section is no longer in its source file."""


# --------------------------------------------------------------------------- #
# Markdown section surgery
# --------------------------------------------------------------------------- #
def read_md(name):
    path = os.path.join(SKILL_ROOT, name)
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def split_h2(text):
    """``[(heading, block)]`` for every top-level ``## `` section, fences respected.

    Fence tracking is not decoration: ``reference.md`` embeds python and mermaid blocks,
    and a ``##`` comment inside one would otherwise start a phantom section and truncate
    the real one.
    """
    out, heading, buf, fenced = [], None, [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
        if not fenced and line.startswith("## "):
            if heading is not None:
                out.append((heading, "\n".join(buf).rstrip()))
            heading, buf = line[3:].strip(), []
            continue
        if heading is None:
            continue
        buf.append(line)
    if heading is not None:
        out.append((heading, "\n".join(buf).rstrip()))
    return out


def pick(sections, patterns, source):
    """Return the allow-listed sections, in the order asked. Raises on a miss."""
    blocks, taken = [], []
    for pat in patterns:
        rx = re.compile(pat, re.IGNORECASE)
        hit = next(((h, b) for h, b in sections if rx.match(h)), None)
        if hit is None:
            raise MissingSectionError(
                f"{source}: no '## ' heading matches /{pat}/. The allow-list in "
                f"source_pack_corpus.py is out of date — update it rather than letting "
                f"the pack ship without this material.")
        blocks.append(f"## {hit[0]}\n\n{hit[1]}")
        taken.append(hit[0])
    return "\n\n---\n\n".join(blocks), taken


# Allow-lists. Patterns are short and anchored at the start of the heading so a long
# parenthetical can change without breaking the build, while a rename still fails.
REFERENCE_ENDPOINTS = [
    r"Airship Reports API endpoints",
    r"Per-channel activity & typology",
    r"Campaign typology",
    r"Campaign analysis",
    r"Experiments \(A/B\) detection",
    r"Creative coverage",
    r"Unicast",
    # What the reporting data does and does not carry about a campaign's identity, and what
    # in-app events do and do not reveal — both are endpoint semantics, not report style.
    r"Programmes shown by their identifier",
    r"Scene instrumentation",
]
REFERENCE_DEFINITIONS = [
    r"Definitions",
    r"Channels",
    r"Scope of measurement",
    r"Verification & confidence",
    # Both bound what any figure in the pack may be read to mean: one says what the run
    # could not collect, the other whether a conversion can be tied to an amount at all.
    r"Coverage \u2014 say what the review cannot claim",
    r"Value measurability",
]
REFERENCE_BENCHMARKS = [
    r"Industry benchmarks",
    r"Internal baseline",
]
REFERENCE_VERTICAL = [
    r"Campaign purpose & pillar playbook",
    r"Custom-event contextualisation",
    r"Data-collection audit",
    r"Airship Goals",
]
BENCHMARKS_BOOK = [
    r"How the skill uses this file",
    r"Metric keys",
]

# Considered and deliberately dropped: build machinery, not account semantics. Kept here
# so "why is this not in the pack" has an answer, and so a new reference.md section shows
# up as unclassified rather than silently missing.
EXCLUDED = [
    r"MCP access",
    r"Airship branding",
    r"Multi-language",
    r"Deliverable",
    r"Shared framework",
    r"Flight Deck deep-links",
    r"Page / PDF rules",
    # Proof points are OTHER accounts' results. Shipping a library of third-party client
    # figures into a notebook built about this account would put them one question away from
    # being quoted back as if they were its own.
    r"Proof points",
    # The slice table tells a section agent which headings of this file to read. It is
    # orchestration addressed to the writer of the report, and means nothing to a reader
    # of the notebook.
    r"Read only your slice",
]


def unclassified_reference_sections():
    """H2s of reference.md that are in neither an allow-list nor EXCLUDED.

    Advisory. New reference material is not a build failure, but it is worth knowing
    that it exists and was not routed anywhere.
    """
    known = (REFERENCE_ENDPOINTS + REFERENCE_DEFINITIONS + REFERENCE_BENCHMARKS
             + REFERENCE_VERTICAL + EXCLUDED)
    rxs = [re.compile(p, re.IGNORECASE) for p in known]
    return [h for h, _ in split_h2(read_md("reference.md"))
            if not any(rx.match(h) for rx in rxs)]


# --------------------------------------------------------------------------- #
# 03 — the metric fiches
# --------------------------------------------------------------------------- #
# One entry per key in `build_facts.KPI_SPECS`. Content is derived from reference.md
# (`## Definitions`, `## Scope of measurement`, the endpoint table and its traps), not
# invented here — a fiche that guesses a denominator is worse than no fiche, because it
# reads exactly as authoritative as a correct one.
#
# `benchmark` names a key of benchmarks.json, or states that none applies. Saying "none"
# explicitly is the point: an unbenchmarked metric compared to a benchmark anyway is the
# failure this document exists to prevent.
FICHES = {
    "push_sends": dict(
        endpoint="`/api/reports/sends` (DAILY), push families only (ios/android/amazon/web)",
        denominator="none — a count",
        window="period",
        pitfall="`/api/reports/sends` is **not push-only**: it also carries `email` and "
                "`sms`. Totalling every platform and calling the result push overstated "
                "marketing pressure by 29% on a live account. `sends`/`alerting_sends` "
                "count the **alerting** notification, so a silent (data-only) push or an "
                "inbox-only Message Center is not in this figure.",
        benchmark="none directly; see `pressure` for `sends_per_user_month`"),
    "email_sends": dict(
        endpoint="`/api/reports/sends` (DAILY), `email` column",
        denominator="none — a count",
        window="period",
        pitfall="Email can be active with sends > 0 while `/api/reports/devices` shows 0 "
                "opted-in email addresses. Judge channel presence from both sources "
                "together, and never divide email sends by the push opted-in base.",
        benchmark="none — Airship's UA benchmarks cover push and Message Center only"),
    "opens": dict(
        endpoint="`/api/reports/opens` (DAILY)",
        denominator="none — a count",
        window="period",
        pitfall="These are app/notification opens **as counted by Airship, influenced "
                "included**. An app open is not an attributed push open: do not read this "
                "as a response to a message.",
        benchmark="none — the benchmarked rates are direct and influenced open rates"),
    "open_rate": dict(
        endpoint="derived in `analyze.py`; app/push open rate",
        denominator="the base the account's own analysis declares — read `audit.json` "
                    "rather than recomputing",
        window="period",
        pitfall="A bare \"open rate\" is ambiguous: some accounts label their **email** "
                "open rate exactly that. `build_facts` only matches a qualified label "
                "(app / push / mobile) for this reason. Check which one a figure is "
                "before comparing it to anything.",
        benchmark="none as such — compare direct and influenced open rates instead"),
    "direct_open_rate": dict(
        endpoint="`/api/reports/perpush/detail` · `pergroup/detail` · `responses/list` "
                 "(`direct_responses` / `sends`)",
        denominator="sends of the same messages",
        window="period",
        pitfall="**Direct** means the user tapped the push. **Influenced (indirect)** "
                "means the app was opened within the attribution window without a direct "
                "tap. They are different metrics and are benchmarked separately. On "
                "**email/SMS** the same field means something else entirely: "
                "`direct_responses` = **clicks** and `influenced_responses` = **opens**.",
        benchmark="`direct_open_rate`, split by device family (ios/android/web)"),
    "audience_total": dict(
        endpoint="`/api/reports/devices`",
        denominator="none — a count",
        window="**snapshot** at `date_closed`, not the period",
        pitfall="Never mix this with a period figure in the same KPI. This is the whole "
                "installed base at a point in time.",
        benchmark="none"),
    "app_optin": dict(
        endpoint="`/api/reports/devices`, `opted_in` summed over the app platforms",
        denominator="none — a count",
        window="**snapshot**",
        pitfall="Not the same thing as the period `optins` event flow, and the two will "
                "not reconcile.",
        benchmark="none as a count; see `optin_rate`"),
    "web_optin": dict(
        endpoint="`/api/reports/devices`, web `opted_in`",
        denominator="none — a count",
        window="**snapshot**",
        pitfall="Web push devices that are all opted out mean the channel was never "
                "activated, not that it performs badly.",
        benchmark="none as a count; see `optin_rate` (web split)"),
    "optin_rate": dict(
        endpoint="`/api/reports/devices` — the authoritative and only source",
        denominator="unique devices (snapshot)",
        window="**snapshot**",
        pitfall="Opt-in rate = `opted_in / unique_devices` from the snapshot. Computing "
                "it from the period opt-in events gives a different and meaningless "
                "number.",
        benchmark="`optin_rate`, split by device family (ios/android)"),
    "optins": dict(
        endpoint="`/api/reports/optins` (DAILY)",
        denominator="none — a count of events",
        window="period",
        pitfall="Daily opt-in **events**, including re-detections and reinstalls. The sum "
                "of opt-ins minus opt-outs describes activity flow only and must never be "
                "presented as \"the base grew by X\".",
        benchmark="none"),
    "optouts": dict(
        endpoint="`/api/reports/optouts` (DAILY)",
        denominator="none — a count of events",
        window="period",
        pitfall="Same as `optins`: an event flow, not a net change of the installed base.",
        benchmark="none"),
    "pressure": dict(
        endpoint="derived: channel sends / weeks / that channel's addressable base",
        denominator="**must match the channel** — push to push `opted_in`, email to the "
                    "email base, web to web `opted_in`",
        window="period",
        pitfall="Two views must both be reported: cross-platform (all sends over the "
                "total addressable base) and per-platform. Dividing email sends by the "
                "push opted-in base is the classic error. The benchmark is expressed "
                "**per month**, so a weekly figure must be multiplied by ~4.33 before "
                "any comparison.",
        benchmark="`sends_per_user_month`, split by device family — **per MONTH**"),
    "events_total": dict(
        endpoint="`/api/reports/events` (all pages), `location: custom`",
        denominator="none — a count",
        window="period",
        pitfall="Only `location:custom` behavioural events belong in the conversion "
                "taxonomy. In-app impressions that also sit under `custom` (names "
                "starting `banner - `) are campaign signals and are excluded from it. "
                "`in_app_message`, `in_app_pager` and `ua_mcrap` are campaign engagement, "
                "not behaviour.",
        benchmark="none"),
    "events_attributed": dict(
        endpoint="`/api/reports/events/summary/perpush/{id}` · `.../pergroup/{id}`",
        denominator="total events in the window, when expressed as a rate",
        window="period",
        pitfall="Push-attributed = direct + indirect. Unattributed events are not a "
                "failure of the programme — most app behaviour has no message behind it.",
        benchmark="none"),
    "campaigns_push": dict(
        endpoint="merged inventory: `responses/list` + `activity/details`, grouped by "
                 "`classify_campaigns.py`",
        denominator="none — a count",
        window="period",
        pitfall="A count of campaigns, not of sends. The typology (one-shot vs "
                "automated/recurring) is a **Reports-only heuristic** built from "
                "`group_id` and name cadence, because `/api/pipelines` and "
                "`/api/schedules` are out of scope. On a firehose account the inventory "
                "is a programme-level rollup with a stated coverage, not an enumeration.",
        benchmark="none"),
    "campaigns_email": dict(
        endpoint="per-message email rows when available; otherwise channel-level cadence",
        denominator="none — a count",
        window="period",
        pitfall="Email and SMS are **not listable** from the Reports API. When no "
                "per-message list exists, typology is inferred from daily send cadence at "
                "Low/Medium confidence, and this count may be absent entirely.",
        benchmark="none"),
    "silent_share": dict(
        endpoint="reconciliation of `activity/details` delivery counters against "
                 "`responses/list`",
        denominator="total push sends",
        window="period",
        pitfall="`sends`/`alerting_sends` count the alerting notification; "
                "`responses/list` `sends` also counts silent (data-only) pushes. A high "
                "silent share means much of the volume never appeared on a lock screen — "
                "read engagement rates against the alerting base, not the total.",
        benchmark="none"),
}


def emit_fiches(pack):
    """One fiche per KPI key, and a hard failure when a key has none."""
    missing = [s["key"] for s in KPI_SPECS if s["key"] not in FICHES]
    if missing:
        raise MissingSectionError(
            "KPI_SPECS has keys with no fiche in source_pack_corpus.FICHES: "
            f"{', '.join(missing)}. Add them — a metric the pack can publish without a "
            "definition is exactly what this document exists to prevent.")

    intro = T(pack.lang,
              fr="Une fiche par métrique que ce pack peut publier. Chaque fiche dit d'où "
                 "vient le chiffre, sur quel dénominateur il se calcule, s'il décrit un "
                 "instantané ou une période, ce qui le fait mal lire, et quel benchmark "
                 "lui est applicable — ou aucun. **Le contenu des fiches est en anglais, "
                 "comme le reste du référentiel** : ce sont les libellés de l'API.",
              en="One fiche per metric this pack can publish: where the figure comes "
                 "from, the denominator it is computed on, whether it describes a "
                 "snapshot or a period, what makes it misread, and which benchmark "
                 "applies to it — or none.")

    parts = [intro, ""]
    for spec in KPI_SPECS:
        key = spec["key"]
        f = FICHES[key]
        pack.document_metric(key)
        parts.append(
            f"## `{key}` — {spec['en']} / {spec['fr']}\n\n"
            f"- **Unit:** {spec['unit']}\n"
            f"- **Source:** {f['endpoint']}\n"
            f"- **Denominator:** {f['denominator']}\n"
            f"- **Scope:** {f['window']}\n"
            f"- **Benchmark:** {f['benchmark']}\n"
            f"- **How it gets misread:** {f['pitfall']}\n")

    pack.add("03_fiches_metriques.md",
             T(pack.lang, fr="Fiches métriques — définition, source, dénominateur",
               en="Metric fiches — definition, source, denominator"),
             1, "\n".join(parts),
             provenance("build_facts.KPI_SPECS + reference.md (Definitions, Scope of "
                        "measurement, endpoint table)"))


# --------------------------------------------------------------------------- #
# 04 — what the data does not allow
# --------------------------------------------------------------------------- #
# Each entry: (subject, the forbidden inference, why). Written as prohibitions because
# that is the form a retrieval engine can actually apply to a question it is asked.
LIMITS = [
    ("`/api/reports/sends`",
     "do not read it as push volume without filtering the platform columns",
     "it carries email and sms too; on a live account, summing everything overstated "
     "marketing pressure by 29%"),
    ("Alerting vs silent",
     "do not treat total push sends as messages that reached a lock screen",
     "`sends`/`alerting_sends` count alerting notifications, while `responses/list` "
     "`sends` also counts silent data-only pushes"),
    ("Message Center",
     "do not conclude a Message Center message was not delivered because `sends` is 0",
     "`responses/list` carries no `rich_sends`, so an inbox-only message correctly reads "
     "as `sends: 0` there; its real delivery is only visible on `perpush/detail`"),
    ("Snapshot vs period",
     "never compare `/devices` counts with `optins`/`optouts` totals, and never say the "
     "base grew or shrank by the difference",
     "`/devices` is a point-in-time state of the whole installed base; opt-in/opt-out are "
     "daily event flows including re-detections and reinstalls"),
    ("Opt-in rate",
     "do not compute it from period events",
     "it is `opted_in / unique_devices` from the devices snapshot, which is the only "
     "authoritative source"),
    ("Marketing pressure",
     "do not divide one channel's sends by another channel's base, and do not compare a "
     "weekly figure to the benchmark as-is",
     "the denominator must match the channel, and `sends_per_user_month` is per MONTH — "
     "multiply a weekly pressure by ~4.33"),
    ("Direct vs influenced",
     "do not add them or use one for the other",
     "direct means the push was tapped; influenced means the app opened within the "
     "attribution window without a tap. They are benchmarked separately"),
    ("Email and SMS response fields",
     "do not read `direct_responses` as taps on email",
     "on email/SMS the top-level fields mean `direct_responses` = clicks and "
     "`influenced_responses` = opens"),
    ("Custom event `value`",
     "never assert an amount of money",
     "`value` is a client-declared number that may be a per-event counter; when it reads "
     "as monetary the currency is an assumption carrying a confidence level"),
    ("Event taxonomy",
     "do not treat in-app or Message Center CTA names as behavioural conversion events",
     "only `location:custom` events (excluding names starting `banner - `) are "
     "behaviour; `in_app_message`, `in_app_pager` and `ua_mcrap` are campaign engagement "
     "signals at low reliability"),
    ("Campaign typology",
     "do not state that a campaign is an automation as an established fact",
     "`/api/pipelines` and `/api/schedules` are out of scope, so one-shot vs "
     "automated/recurring is a Reports-only heuristic from `group_id` and name cadence, "
     "and each mapping carries its own reliability score"),
    ("Email and SMS campaigns",
     "do not conclude there are no email campaigns because none are listed",
     "these channels are not listable from the Reports API; absence from the inventory "
     "is a limit of the source, not a fact about the account"),
    ("Benchmarks",
     "do not read a percentile as a target, and do not compare across regions",
     "the values are p10/p50/p90 bands on a global sample with no region or locale "
     "split, and any comparison to them is capped at Medium confidence"),
    ("Tagging-plan export",
     "do not derive a per-user frequency or a penetration rate from it",
     "the export counts **occurrences, not unique channels**"),
    ("Tracked but silent events",
     "do not read a tracked event with no occurrences as a broken implementation",
     "the plan expresses design intent; an event can be correctly instrumented and "
     "simply not have fired in the window"),
    ("Coverage",
     "do not treat any figure as complete without reading the coverage document",
     "on firehose-shaped accounts the per-message layer is a programme-level rollup with "
     "an explicitly quantified coverage, and the tail of a window that ends after the "
     "consolidation watermark can return zeros that are not real zeros"),
]


def emit_limits(pack, disc):
    intro = T(pack.lang,
              fr="Ce que la donnée de ce compte **ne permet pas** de conclure. À lire "
                 "avant toute comparaison ou tout calcul de ratio : chaque ligne "
                 "correspond à une erreur qui a déjà été commise sur un compte réel.",
              en="What this account's data **does not** allow you to conclude. Read this "
                 "before any comparison or derived ratio: each line corresponds to a "
                 "mistake already made on a real account.")

    rows = [f"## {subject}\n\n**Do not:** {dont}\n\n**Because:** {why}\n"
            for subject, dont, why in LIMITS]

    # The account's own shape decides whether the coverage caveat is theoretical.
    probe = disc["data"].get("probe") or {}
    shape = probe.get("shape")
    if shape and shape != "dashboard":
        rows.append(
            f"## This account in particular\n\n"
            f"Its shape is `{shape}`"
            + (f" ({probe['shape_reason']})" if probe.get("shape_reason") else "")
            + ". The per-message layer is therefore a rollup with a stated coverage "
              "rather than an enumeration: read `11_perimetre_et_couverture.md` before "
              "treating any per-campaign figure as exhaustive.\n")

    pack.add("04_limites_et_inferences_interdites.md",
             T(pack.lang, fr="Limites et inférences interdites",
               en="Limits and forbidden inferences"),
             1, intro + "\n\n" + "\n".join(rows),
             provenance("reference.md traps + mode-b.md + probe.json"))


# --------------------------------------------------------------------------- #
def _data_collection_block(vertical):
    """The data-collection book, whole.

    This used to keep only `## Event categories`, `## all verticals` and the one vertical
    matching the account, on a retrieval-dilution argument. That argument does not hold
    against Notebook Enterprise: the context window swallows the whole book, and the
    filtering removed the material needed to answer "what would a travel app track that
    we do not" — a question worth asking precisely because the account is not a travel
    app. The book is 4k words; shipping it whole costs nothing and the reader can
    deselect the source.
    """
    text = read_md("data-collection-by-vertical.md")
    label = None
    try:
        from event_analysis import load_catalog, resolve_vertical
        info = resolve_vertical(load_catalog(), vertical)
        label = None if info.get("fallback") else info.get("label")
    except Exception:  # noqa: BLE001 — an unresolvable vertical just gets no pointer
        label = None
    note = (f"> Shipped whole. **{label}** is the book vertical matching this account's "
            f"benchmark vertical `{vertical}`; the others are here so the account can be "
            f"read against a neighbouring sector on purpose.\n\n" if label else
            "> Shipped whole. This account's vertical does not map to a vertical of this "
            "book, so read every section as a reference rather than as its peer.\n\n")
    return note + text


# --------------------------------------------------------------------------- #
def emit_corpus(pack, disc, vertical=None):
    """Emit the six non-README tier-1 documents."""
    ref = split_h2(read_md("reference.md"))

    block, _ = pick(ref, REFERENCE_ENDPOINTS, "reference.md")
    pack.add("01_endpoints_reports_api.md",
             T(pack.lang, fr="Endpoints de la Reports API — ce qu'ils renvoient et leurs pièges",
               en="Reports API endpoints — what they return and their traps"),
             1, block, provenance("reference.md, verbatim (allow-listed sections)"),
             verbatim=True)

    block, _ = pick(ref, REFERENCE_DEFINITIONS, "reference.md")
    pack.add("02_definitions_et_perimetre.md",
             T(pack.lang, fr="Définitions, canaux et périmètre de mesure",
               en="Definitions, channels and scope of measurement"),
             1, block, provenance("reference.md, verbatim (allow-listed sections)"),
             verbatim=True)

    emit_fiches(pack)
    emit_limits(pack, disc)

    ref_bench, _ = pick(ref, REFERENCE_BENCHMARKS, "reference.md")
    book_bench, _ = pick(split_h2(read_md("benchmarks.md")), BENCHMARKS_BOOK,
                         "benchmarks.md")
    pack.add("05_comment_lire_les_benchmarks.md",
             T(pack.lang, fr="Comment lire les benchmarks sectoriels",
               en="How to read the industry benchmarks"),
             1, f"{book_bench}\n\n---\n\n{ref_bench}",
             provenance("benchmarks.md + reference.md, verbatim"), verbatim=True)

    ref_vert, _ = pick(ref, REFERENCE_VERTICAL, "reference.md")
    pack.add("06_referentiels_metier.md",
             T(pack.lang, fr="Référentiels sectoriels — événements, leviers, goals",
               en="Sector references — events, levers, goals"),
             1,
             "\n\n---\n\n".join([
                 ref_vert,
                 read_md("event_catalog.md"),
                 read_md("campaign_playbook.md"),
                 _data_collection_block(vertical),
             ]),
             provenance("reference.md + event_catalog.md + campaign_playbook.md + "
                        "data-collection-by-vertical.md, verbatim"),
             verbatim=True)

    extra = unclassified_reference_sections()
    if extra:
        pack.notes.append(
            "reference.md carries sections routed to no tier-1 document and not on the "
            f"exclusion list: {', '.join(extra)}. Not an error — decide whether the pack "
            "should carry them.")
