#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Turn a delivered engagement review into the pack's one conclusion-bearing source.

Every other document in a source pack is deliberately verdict-free: a notebook handed
the answers recites them instead of rebuilding them from the data, which is the whole
point of the exercise. But an account team discussing a recommendation needs the
recommendation in the conversation, and the alternative — pasting the report into the
notebook by hand — produces an unscrubbed, unnumbered source nobody can deselect.

So the report ships, as `99_rapport_engagement.md`, outside the tier scheme and
announced as the one source that concludes. `99` sorts last, reads as "not part of the
numbered library", and is a separate source, which is what makes deselecting it a
one-click operation rather than a decision taken at build time.

Two things survive the conversion that a generic HTML-to-text pass would drop, and
they are the reason this is not `pandoc`:

- **the method block behind every KPI.** It lives in a `<template>` the browser only
  reveals on click. Dropped, the figure arrives with no formula, no source and no
  confidence — exactly the shape the pack's autonomy gate exists to refuse.
- **the chart data.** Each figure carries its Chart.js spec as JSON. Re-emitted as a
  table the values become answerable; left as an image they leave a caption pointing at
  a curve that is not there.

The output goes through `Pack.add`, so it is scrubbed with everything else. That is not
a formality: the first account this ran on carried three real consumer email addresses
into the report through the tagging plan's sample values, and the pack's mask is what
stopped them reaching the notebook.
"""
from __future__ import annotations

import json
import os
import re
import sys

try:
    import lxml.html as LH
except ImportError:  # pragma: no cover - reported by the caller, never raised
    LH = None

# Chrome the reader never asked for: navigation, buttons, the static PNG of a chart
# whose numbers are re-emitted as a table, and the live canvas.
DROP = {"script", "style", "button", "canvas", "img", "svg", "nav", "aside", "noscript"}

CONFIDENCE = {"pill-good": ("élevée", "high"),
              "pill-warn": ("moyenne", "medium"),
              "pill-bad": ("faible", "low")}

# A daily series runs past a hundred rows and would drown the document; the full series
# already ships as `94_annexe_series_quotidiennes.md`.
CHART_ROW_CAP = 40

# Kept in step with `source_pack_docs.ROWS_PER_SEGMENT`, which the pack's gate enforces.
# Imported rather than duplicated so the two cannot drift apart.
try:
    from source_pack_docs import ROWS_PER_SEGMENT
except ImportError:  # pragma: no cover - standalone use, e.g. the CLI below
    ROWS_PER_SEGMENT = 50


class ReportUnavailable(Exception):
    """No report to convert, or no parser to convert it with."""


def _t(lang, fr, en):
    return en if lang == "en" else fr


def txt(el) -> str:
    """Inline text of an element, with code spans preserved."""
    out = []

    def walk(e, top=False):
        if not top:
            if e.tag in DROP or e.tag is LH.etree.Comment or e.tag == "template":
                if e.tail:
                    out.append(e.tail)
                return
            if e.tag == "code":
                out.append(f"`{''.join(e.itertext()).strip()}`")
                if e.tail:
                    out.append(e.tail)
                return
        if e.text:
            out.append(e.text)
        for c in e:
            walk(c)
        if not top and e.tail:
            out.append(e.tail)

    walk(el, top=True)
    return re.sub(r"\s+", " ", "".join(out)).strip()


def method_of(card, lang="fr"):
    """The formula / source / confidence a KPI hides behind its ⓘ button."""
    tpl = card.find(".//template")
    if tpl is None:
        return ""
    rows = tpl.xpath(".//div[@class='ir-method-row']")
    if not rows and (getattr(tpl, "text", None) or "").strip():
        rows = LH.fragment_fromstring(tpl.text, create_parent="div").xpath(
            ".//div[@class='ir-method-row']")
    bits = []
    for r in rows:
        k_el = r.find(".//span[@class='ir-method-k']")
        v_el = r.find(".//span[@class='ir-method-v']")
        k = txt(k_el) if k_el is not None else ""
        v = txt(v_el) if v_el is not None else ""
        pills = v_el.xpath(".//span[contains(@class,'pill')]") if v_el is not None else []
        for pill in pills[:1]:
            cls = pill.get("class", "")
            for key, labels in CONFIDENCE.items():
                if key in cls:
                    v = _t(lang, *labels)
                    break
        if k and v:
            bits.append(f"{k} : {v}")
    return " · ".join(bits)


def chart_table(fig, lang="fr") -> str:
    """A chart's Chart.js spec, re-emitted as the table it was drawn from."""
    spec_el = fig.find(".//script[@class='ir-chart-spec']")
    if spec_el is None or not (spec_el.text or "").strip():
        return ""
    try:
        spec = json.loads(spec_el.text)
    except ValueError:
        return ""
    data = spec.get("data") or {}
    labels = [str(x) for x in (data.get("labels") or [])]
    sets = [d for d in (data.get("datasets") or []) if isinstance(d, dict)]
    if not labels or not sets:
        return ""
    heads = [d.get("label") or _t(lang, f"série {i + 1}", f"series {i + 1}")
             for i, d in enumerate(sets)]
    lines = ["| | " + " | ".join(heads) + " |", "|---|" + "---|" * len(heads)]
    for i, lab in enumerate(labels[:CHART_ROW_CAP]):
        cells = []
        for d in sets:
            vals = d.get("data") or []
            v = vals[i] if i < len(vals) else None
            cells.append("" if v is None else str(v))
        lines.append(f"| {lab} | " + " | ".join(cells) + " |")
    if len(labels) > CHART_ROW_CAP:
        rest = len(labels) - CHART_ROW_CAP
        lines.append(f"| … | " + _t(
            lang,
            f"{rest} lignes suivantes non reprises — série complète dans "
            f"`94_annexe_series_quotidiennes.md`",
            f"{rest} further rows omitted — full series in "
            f"`94_annexe_series_quotidiennes.md`") + " |" + " |" * (len(heads) - 1))
    return "\n".join(lines)


def table_md(tbl, lang="fr") -> str:
    """One HTML table as markdown, segmented the way the rest of the pack segments.

    A report's campaign appendix runs to several hundred rows, and the pack's gate
    refuses a segment longer than `ROWS_PER_SEGMENT` — for the reason that gate exists:
    a chunk boundary landing mid-table leaves rows with no header above them. Same rule
    here, same caption, so a segment read in isolation still says how much it is not
    showing.
    """
    head, body = [], []
    for tr in tbl.xpath(".//tr"):
        cells = tr.xpath("./th|./td")
        if not cells:
            continue
        vals = [txt(c).replace("|", "\\|") or " " for c in cells]
        if not head:
            head = vals
        else:
            body.append(vals)
    if not head:
        return ""
    rule = "|" + "---|" * len(head)
    header = "| " + " | ".join(head) + " |"
    if not body:
        return header + "\n" + rule
    if len(body) <= ROWS_PER_SEGMENT:
        return "\n".join([header, rule] + ["| " + " | ".join(r) + " |" for r in body])

    parts, total = [], len(body)
    for start in range(0, total, ROWS_PER_SEGMENT):
        seg = body[start:start + ROWS_PER_SEGMENT]
        caption = _t(lang,
                     f"_Lignes {start + 1}–{start + len(seg)} sur {total}._",
                     f"_Rows {start + 1}-{start + len(seg)} of {total}._")
        rows = "\n".join("| " + " | ".join(r) + " |" for r in seg)
        parts.append(f"{caption}\n\n{header}\n{rule}\n{rows}")
    return "\n\n".join(parts)


def render(el, lang="fr") -> list:
    """Walk a section, emitting markdown blocks in document order."""
    blocks = []
    for e in el:
        if not isinstance(e.tag, str) or e.tag in DROP or e.tag == "template":
            continue
        cls = e.get("class") or ""
        if e.tag in ("h2", "h3", "h4", "h5"):
            t = txt(e)
            if t:
                blocks.append(
                    {"h2": "##", "h3": "###", "h4": "####", "h5": "#####"}[e.tag]
                    + f" {t}")
        elif e.tag == "table":
            md = table_md(e, lang)
            if md:
                blocks.append(md)
        elif e.tag == "figure":
            cap = e.find(".//figcaption")
            # The figures carry no caption; their id is the `specs.json` key, the same
            # name the builder and the annexes use for the series.
            title = txt(cap) if cap is not None else re.sub(
                r"^fig-|_(fr|en)$", "", e.get("id") or "")
            word = _t(lang, "Graphique", "Chart")
            label = f"**{word} `{title}`**" if title else f"**{word}**"
            tab = chart_table(e, lang)
            blocks.append(f"{label}\n\n{tab}" if tab else f"{label} *" + _t(
                lang, "(figure non transposable en texte ; voir le rapport HTML)",
                "(figure not transposable to text; see the HTML report)") + "*")
        elif "note" in cls.split():
            t = txt(e)
            if t:
                blocks.append("> " + t)
        elif "ir-hero-card" in cls:
            val_el = e.find(".//div[@class='ir-hero-val']")
            lab_el = e.find(".//div[@class='ir-hero-label']")
            delta = e.find(".//span[@class='ir-delta-na']")
            val = txt(val_el) if val_el is not None else ""
            lab = txt(lab_el) if lab_el is not None else ""
            line = f"- **{val}** — {lab}"
            if delta is not None:
                line += f" — {txt(delta)}"
            meth = method_of(e, lang)
            if meth:
                line += f"  \n  *{meth}*"
            blocks.append(line)
        elif e.tag in ("ul", "ol"):
            items = [f"- {txt(li)}" for li in e.xpath("./li") if txt(li)]
            if items:
                blocks.append("\n".join(items))
        elif e.tag == "p":
            t = txt(e)
            if t:
                blocks.append(t)
        elif e.tag in ("div", "section", "article", "details"):
            blocks.extend(render(e, lang))
        else:
            t = txt(e)
            if t and e.tag not in ("span", "a", "b", "i", "code"):
                blocks.append(t)
    return blocks


def _merge_hero(blocks):
    """Consecutive KPI bullets read as one list rather than as isolated lines."""
    out = []
    for b in blocks:
        if out and b.startswith("- **") and out[-1].startswith("- **"):
            out[-1] += "\n" + b
        else:
            out.append(b)
    return out


def convert(html_path, lang="fr"):
    """Report HTML -> markdown body. Raises `ReportUnavailable` if it cannot."""
    if LH is None:
        raise ReportUnavailable("lxml is not installed")
    if not html_path or not os.path.isfile(html_path):
        raise ReportUnavailable("no report.html in the work directory")
    root = LH.parse(html_path).getroot()
    try:
        main = root.get_element_by_id("ir-main")
    except KeyError:
        raise ReportUnavailable("report.html has no #ir-main — not an interactive "
                                "report built by this skill")
    parts = []
    for sec in main.xpath(".//section[contains(@class,'page')]"):
        toc = sec.get(f"data-toc-{lang}") or sec.get("data-toc") or ""
        body = _merge_hero([b for b in render(sec, lang) if b.strip()])
        if not body:
            continue
        # The section's own <h2> repeats the TOC label; keep one of the two.
        head = body.pop(0) if body[0].startswith("## ") else (
            f"## {toc}" if toc else "##")
        parts.append(head + "\n\n" + "\n\n".join(body))
    if not parts:
        raise ReportUnavailable("report.html carried no readable section")

    preamble = _t(
        lang,
        "**Cette source porte des verdicts et des recommandations. Les autres n'en "
        "portent aucun.**\n\n"
        "C'est le rapport d'engagement livré, converti en texte, ajouté au pack pour "
        "que l'on puisse en discuter les conclusions. Il ne remplace pas les documents "
        "`20` à `28` : ceux-ci portent la donnée et ses dénominateurs, celui-ci porte "
        "l'interprétation qui en a été faite un jour donné, par une personne, avec les "
        "limites énoncées dans `04_limites_et_inferences_interdites.md`.\n\n"
        "**Quand la décocher.** Pour toute question d'analyse — « quels leviers ne sont "
        "pas joués ? », « où est le volume ? », « ce chiffre est-il fiable ? » — "
        "décochez cette source. Un notebook à qui l'on donne les réponses les récite au "
        "lieu de les reconstruire, et c'est précisément le raisonnement que l'on "
        "cherche. Cochez-la pour challenger une recommandation, retrouver l'arbitrage "
        "derrière une préconisation, ou préparer une restitution.\n\n"
        "**Ce qui a été perdu à la conversion.** Les graphiques deviennent les tableaux "
        "de valeurs dont ils étaient tirés ; les créatives, les liens Flight Deck et la "
        "mise en forme interactive ne survivent pas. Le HTML reste la référence.",
        "**This source carries verdicts and recommendations. No other one does.**\n\n"
        "It is the delivered engagement report, converted to text, added so the pack's "
        "reader can argue with its conclusions. It does not replace documents `20` to "
        "`28`: those carry the data and its denominators, this one carries one "
        "person's reading of them on one day, within the limits stated in "
        "`04_limites_et_inferences_interdites.md`.\n\n"
        "**When to deselect it.** For any analytical question — which levers are not "
        "run, where the volume is, whether a figure is reliable — untick it. A notebook "
        "given the answers recites them instead of rebuilding them, and the rebuilding "
        "is the point. Tick it to challenge a recommendation or prepare a readout.\n\n"
        "**Lost in conversion.** Charts become the tables they were drawn from; "
        "creatives, Flight Deck links and the interactive layout do not survive. The "
        "HTML remains the reference.")

    return preamble + "\n\n---\n\n" + "\n\n".join(parts) + "\n"


def emit_report(pack, disc):
    """Add the delivered report to a pack as source `99`, if there is one.

    Absence is normal — a pack built straight after `collect.py` has no report yet — and
    it is recorded as a generation note rather than raised, the same contract as every
    other optional input.
    """
    path = disc["found"].get("report")
    try:
        body = convert(path, pack.lang)
    except ReportUnavailable as exc:
        pack.notes.append(f"99_rapport_engagement.md: not emitted ({exc})")
        return None
    return pack.add(
        "99_rapport_engagement.md",
        _t(pack.lang,
           "Rapport d'engagement livré — verdicts et recommandations",
           "Delivered engagement report - verdicts and recommendations"),
        9, body,
        provenance=_t(pack.lang,
                      "`report.html` · report_markdown.convert",
                      "`report.html` · report_markdown.convert"))


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "report.html"
    out = sys.argv[2] if len(sys.argv) > 2 else "99_rapport_engagement.md"
    md = convert(src, os.environ.get("PACK_LANG", "fr"))
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(md)
    print(f"wrote {out} ({len(md.split()):,} words)")
