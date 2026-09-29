#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared assembly framework for the Airship engagement review.

This module removes the per-client boilerplate that used to be copy-pasted into
every ``work/<client>/build_report.py`` (cover, bilingual assembly, language
toggle, chart wiring, N/A blocks) and makes report structure a *guarantee* rather
than a convention:

  * ``render_report(...)`` iterates the CANONICAL section spine
    (``canonical_sections.CANONICAL_SECTIONS``). Non-optional sections are ALWAYS
    emitted; if a renderer returns nothing (or raises ``NoData``) the section is
    auto-filled with a standard "N/A (reason)" block instead of vanishing.
  * ``load_sections(dir)`` builds that renderer map from one file per section
    (``sections/<canonical_key>.py`` exposing ``render(ctx, lang)``), so sections can
    be authored concurrently without touching a shared file. Filenames are validated
    against the spine: a typo raises ``SectionLoadError`` instead of quietly becoming
    an N/A block, which is the failure mode of a mistyped key in a hand-written dict.
  * ``chart(...)`` fails LOUDLY (``MissingChartError``) when a chart id is absent
    from specs.json or its PNG is missing — a chart can no longer silently drop.
  * ``write_report(...)`` runs the delivery gate (verify_report) at build time and
    raises ``BuildGateError`` on FAIL, so an incomplete report can't be written
    unnoticed. Pass ``gate=False`` (or ``--no-gate`` in a builder) to bypass. Once
    the gate passes it also drops a client-named copy in ``~/Downloads`` — the
    finished review lives outside the git-ignored ``work/`` tree, where the account
    team can find it.
  * ``aget(...)`` reads nested audit.json keys defensively: a missing/stale key
    degrades the section to N/A rather than crashing the whole build.

Pairs with report_interactive.py (brand + interactive scaffold) and
canonical_sections.py (the section registry / gate contract).
"""
from __future__ import annotations

import base64
import datetime as _dt
import os
import re
import shutil
import sys
from typing import Callable, Dict, List, Optional, Sequence

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import report_interactive as ri  # noqa: E402
import canonical_sections as cs  # noqa: E402

NBSP = "\u202f"   # narrow no-break space (FR number grouping)
EM = "\u2014"     # em dash


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
class NoData(Exception):
    """Raise inside a section renderer to force a standard N/A block.

    Optionally carry bilingual reason/how-to-enable overrides:
        raise NoData("Email inactive", "Email inactif")
    """
    def __init__(self, reason_en: str = "", reason_fr: str = "",
                 how_en: str = "", how_fr: str = ""):
        super().__init__(reason_en or "no data")
        self.reason_en, self.reason_fr = reason_en, reason_fr
        self.how_en, self.how_fr = how_en, how_fr


class SectionLoadError(RuntimeError):
    """A file in a ``sections/`` directory does not honour the section contract.

    Raised for a filename that is not a canonical section key, or a module without a
    callable ``render(ctx, lang)`` — both fail loudly so a mis-named section can never
    silently disappear into an N/A block.
    """


def _rename_hint(key):
    """Name the file this was probably meant to be, or "" if there is no good guess.

    Two mistakes account for nearly every rejected filename. An author is handed the
    section's HTML anchor (`pressure`, `bench`, `method`) and names the file after it,
    though the contract is the canonical key (`volume_pressure`, `benchmarks`,
    `appendix`). Or they abbreviate (`appx_events` for `appendix_events`). Both are one
    rename away from correct, so the error should name that rename — a bare list of
    thirty valid keys leaves the reader to hunt for it.
    """
    by_anchor, by_squashed = {}, {}
    for s in cs.CANONICAL_SECTIONS:
        if s.get("id") and s["id"] != s["key"]:
            by_anchor[s["id"]] = s["key"]
        by_squashed[s["key"].replace("_", "")] = s["key"]
    if key in by_anchor:
        return (f"'{key}' is that section's HTML anchor, not its key — "
                f"rename the file to '{by_anchor[key]}.py'. ")
    squashed = key.replace("_", "")
    for cand, real in by_squashed.items():
        if cand.startswith(squashed) or squashed.startswith(cand):
            return f"Did you mean '{real}.py'? "
    return ""


class MissingChartError(RuntimeError):
    """A section asked for a chart that was never generated (spec or PNG missing)."""


class BuildGateError(RuntimeError):
    """verify_report failed the report at build time."""


# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------
def datauri(path: str) -> str:
    """base64 data: URI for an image on disk (png/jpg/svg…)."""
    ext = os.path.splitext(path)[1].lstrip(".").lower() or "png"
    mime = "jpeg" if ext in ("jpg", "jpeg") else ("svg+xml" if ext == "svg" else ext)
    with open(path, "rb") as fh:
        return f"data:image/{mime};base64," + base64.b64encode(fh.read()).decode()


_MISSING = object()


def aget(data, dotted: str, default=None):
    """Safely read a nested value from the audit dict with a dotted path.

    ``aget(A, "devices.families.ios.optin_rate")`` returns the value or ``default``
    (None) if any hop is absent — so a stale/partial audit.json degrades a section
    to N/A instead of raising ``KeyError`` and killing the whole build. List indices
    are supported as integer path parts: ``aget(A, "events.events.0.name")``.
    """
    cur = data
    for part in dotted.split("."):
        if isinstance(cur, dict):
            if part in cur:
                cur = cur[part]
            else:
                return default
        elif isinstance(cur, (list, tuple)):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return default
        else:
            return default
    return cur


# ---------------------------------------------------------------------------
# PDF companion — opt-in: the HTML is the deliverable
# ---------------------------------------------------------------------------
_PDF = False


def set_pdf(enabled: bool) -> bool:
    """Turn the PDF companion on for this build. Default OFF.

    The HTML is the deliverable; the PDF is an optional companion. This switch decides
    only whether one is *produced*: with it off, ``assemble()`` drops the sidebar
    download button and the Chrome print step is skipped. The report's content and
    payload are identical either way — every chart keeps its print PNG, so turning the
    companion back on needs no rebuild of the charts.

    Call it once, before assembling.
    """
    global _PDF
    _PDF = bool(enabled)
    return _PDF


def pdf_enabled() -> bool:
    """Whether this build ships a PDF companion (see :func:`set_pdf`)."""
    return _PDF


# ---------------------------------------------------------------------------
# Charts — loud on failure
# ---------------------------------------------------------------------------
def chart(cid: str, charts_dir: str, specs: Optional[dict], lang: str = "en",
          alt: str = "", height: int = 440, csv_label: str = "CSV") -> str:
    """Emit an interactive chart figure, failing LOUDLY if it wasn't generated.

    ``specs`` is the parsed specs.json (chart_id -> Chart.js config). For FR the
    canvas id is suffixed ``_fr`` so EN/FR canvases don't collide. Raises
    ``MissingChartError`` if the spec key or the PNG is missing — this is what
    stops charts from silently disappearing from a report.
    """
    if not specs or cid not in specs:
        raise MissingChartError(
            f"chart '{cid}' is not in specs.json — run make_charts.py, or remove the "
            f"chart() call. (charts present: {sorted((specs or {}).keys())})")
    png = os.path.join(charts_dir, cid + ".png")
    if not os.path.isfile(png):
        raise MissingChartError(
            f"chart PNG missing for '{cid}': {png} — run make_charts.py.")
    cidl = cid if lang == "en" else cid + "_fr"
    return ri.interactive_chart(cidl, datauri(png), specs[cid], alt=alt,
                                height=height, csv_label=csv_label)


def charts_row(*figs: str) -> str:
    """Wrap 1..n chart() outputs in the responsive two-up chart row."""
    inner = "".join(f for f in figs if f)
    return f'<div class="ir-charts-2">{inner}</div>' if inner else ""


# ---------------------------------------------------------------------------
# Section rendering
# ---------------------------------------------------------------------------
def _toc_attrs(spec: dict, lang: str) -> str:
    sub = ' data-toc-sub="1"' if spec.get("sub") else ''
    # sidebar-only thematic cluster (screen tree eyebrows); never affects print
    cluster = cs.cluster_of(spec.get("key", ""))
    return (f'data-toc="{ri.html.escape(spec["toc_en"])}" '
            f'data-toc-fr="{ri.html.escape(spec["toc_fr"])}" '
            f'data-toc-cluster="{ri.html.escape(cluster)}"{sub}')


def section(spec: dict, body_html: str, lang: str = "en") -> str:
    """Wrap a section body in the canonical <section> shell (page + h2 + toc)."""
    en = lang == "en"
    num = spec.get("num", "")
    title = spec["title_en"] if en else spec["title_fr"]
    heading = f"{num}. {title}" if num else title
    # section-header pictogram, keyed off the stable English title
    ico = ri.icon_img(spec.get("icon"), label=spec.get("title_en") or title,
                      css_class="ir-ico ir-h2-ico") if title else ""
    h2 = f"<h2>{ico}{heading}</h2>" if title else ""
    return (f'<section class="page" {_toc_attrs(spec, lang)} id="{spec["id"]}">'
            f'{h2}{body_html}</section>')


def na_block(reason_en: str, reason_fr: str = "",
             how_en: str = "", how_fr: str = "", lang: str = "en") -> str:
    """Standard 'N/A (reason)' panel used when a section has no data on this account."""
    en = lang == "en"
    na = "N/A" if en else "N/A"
    reason = reason_en if en else (reason_fr or reason_en)
    how = how_en if en else (how_fr or how_en)
    how_html = f' {how}' if how else ""
    label = "Not available on this account" if en else "Non disponible sur ce compte"
    return (f'<div class="note note-warn na-block"><b>{na} {EM} {label}.</b> '
            f'{reason}{how_html}</div>')


def cover_period_html(window: dict, lang: str = "en", source: str = "Airship Reports API") -> str:
    """The cover's analysis-window line, rendered from `audit.json`'s `meta.window`.

    Every client builder used to assemble this sentence itself, and a delivered review
    carried a cover window that did not match the window the report was computed over —
    the one line on page one a reader takes entirely on trust, because nothing else in the
    document repeats it. Rendering it from the same dict the analysis used removes the
    retyping step, and the machine-readable copy in `data-ir-window` lets the gate compare
    the printed dates to the audit.
    """
    start, end = str(window.get("start") or ""), str(window.get("end") or "")
    days = window.get("days")
    fr = lang == "fr"
    span = f"{start} au {end}" if fr else f"{start} {EM} {end}"
    day_txt = f" ({days} {'jours' if fr else 'days'})" if days else ""
    head = "Fenêtre d’analyse&nbsp;: " if fr else "Analysis window: "
    src = f" &middot; {'Source :' if fr else 'Source:'} {source}"
    return (f'<span data-ir-window="{start}/{end}">{head}<b>{span}</b>'
            f'{day_txt}{src}</span>')


def cover_section(*, brand_logo_html: str, mark_uri: str, badge_en: str, badge_fr: str,
                  title_en: str, title_fr: str, sub_html_en: str, sub_html_fr: str,
                  period_html_en: str, period_html_fr: str,
                  kpis: Sequence[dict], lang: str = "en",
                  foot_en: str = "Internal Airship usage only — prepared for the account team",
                  foot_fr: str = "Usage interne Airship uniquement — préparé pour l’équipe compte") -> str:
    """Build the branded cover page (full <section>, marked raw in the registry).

    ``kpis`` is a list of ``{"value": str, "label_en": str, "label_fr": str}``.
    """
    en = lang == "en"
    spec = cs.BY_KEY["cover"]
    badge = badge_en if en else badge_fr
    title = title_en if en else title_fr
    sub = sub_html_en if en else sub_html_fr
    period = period_html_en if en else period_html_fr
    foot = foot_en if en else foot_fr
    kpi_html = "".join(
        f'<div><b>{k["value"]}</b><span>{k["label_en"] if en else k["label_fr"]}</span></div>'
        for k in kpis)
    return (
        f'<section class="page cover" {_toc_attrs(spec, lang)} id="cover">'
        f'<img class="cover-mark" src="{mark_uri}" alt="">'
        f'<div class="cover-wrap">'
        f'<div class="cover-top">{brand_logo_html}'
        f'<span class="cover-badge">{badge}</span></div>'
        f'<h1 class="cover-title">{title}</h1>'
        f'<p class="cover-sub">{sub}</p>'
        f'<p class="cover-period">{period}</p>'
        f'<div class="cover-kpis">{kpi_html}</div>'
        f'<p class="cover-foot">{foot}</p>'
        f'</div></section>')


def load_sections(directory: str, renderers: Optional[Dict[str, Callable]] = None,
                  quiet: bool = False,
                  sections: Optional[Sequence[dict]] = None) -> Dict[str, Callable]:
    """Build the renderer map from a ``sections/`` directory, one file per section.

    ``sections/volume_pressure.py`` exposing ``render(ctx, lang) -> html`` becomes
    ``renderers["volume_pressure"]``. One file per canonical key means several agents
    (or people) can author sections concurrently without ever touching a shared file.

    The file NAME is the contract, so it is validated against the canonical spine and
    a typo raises ``SectionLoadError`` instead of silently degrading the section to an
    N/A block — which is what a mistyped key in a hand-written ``RENDERERS`` dict does
    today. Files starting with ``_`` are treated as private helpers and skipped, so a
    ``sections/_shared.py`` can hold copy or formatting used by several sections.

    ``renderers`` pre-seeds the map (an explicitly passed renderer WINS over a file of
    the same name), letting a builder keep one section inline while the rest live in
    files. Returns the merged map; a missing directory is not an error.

    ``sections`` is the spine this build renders (``cs.GOALS_SECTIONS`` for the goals
    profile). It only narrows the "will render as N/A" notice: a filename is accepted
    when it names a section in EITHER spine, so a directory shared between a full run
    and a goals run of the same client does not fail on the other mode's files.
    """
    out: Dict[str, Callable] = dict(renderers or {})
    directory = os.path.abspath(directory)
    if not os.path.isdir(directory):
        if not quiet:
            print(f"[sections] no directory at {directory} — "
                  f"{len(out)} inline renderer(s) only")
        return out

    import importlib.util

    spine = list(sections or cs.CANONICAL_SECTIONS)
    valid = set(getattr(cs, "ALL_KEYS", None) or {s["key"] for s in cs.CANONICAL_SECTIONS})
    if directory not in sys.path:      # let a section import sections/_shared.py
        sys.path.insert(0, directory)

    loaded, overridden = [], []
    for fname in sorted(os.listdir(directory)):
        if not fname.endswith(".py") or fname.startswith("_"):
            continue
        key = fname[:-3]
        if key not in valid:
            raise SectionLoadError(
                f"{os.path.join(directory, fname)}: '{key}' is not a canonical section. "
                f"{_rename_hint(key)}"
                f"Valid names: {', '.join(sorted(valid))}. "
                f"(Add or rename a section in canonical_sections.py, not here.)")
        spec = importlib.util.spec_from_file_location(
            f"_section_{abs(hash(directory))}_{key}", os.path.join(directory, fname))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        fn = getattr(mod, "render", None)
        if not callable(fn):
            raise SectionLoadError(
                f"{os.path.join(directory, fname)}: no callable render(ctx, lang). "
                f"Every section module must expose render(ctx, lang) -> html.")
        # An explicit renderer wins over the file — UNLESS it is a placeholder. The
        # builder scaffold pre-seeds every section it wants written with a `_todo`
        # stub, so without this a wave of agents can author a dozen real sections and
        # the build still ships a dozen N/A blocks, reporting success. A placeholder
        # exists to be replaced; losing to the real thing is the whole point.
        if key in out and not getattr(out[key], "is_placeholder", False):
            overridden.append(key)
            continue
        out[key] = fn
        loaded.append(key)

    if not quiet:
        required = [s["key"] for s in spine
                    if not s.get("optional") and s["key"] not in out]
        print(f"[sections] {len(loaded)} loaded from {os.path.basename(directory)}/: "
              f"{', '.join(loaded) or 'none'}")
        if overridden:
            print(f"[sections] kept inline (file ignored): {', '.join(overridden)}")
        if required:
            print(f"[sections] will render as N/A (no renderer): {', '.join(required)}")
    return out


def render_report(renderers: Dict[str, Callable], ctx, lang: str,
                  na_reasons: Optional[Dict[str, tuple]] = None,
                  sections: Optional[Sequence[dict]] = None) -> List[str]:
    """Render the full canonical spine into a list of <section> strings.

    ``renderers`` maps a canonical section key -> ``fn(ctx, lang) -> html``. A
    renderer may return the section BODY (wrapped automatically) or, for a spec
    flagged ``raw`` (the cover), the full <section>. Returning a falsy value or
    raising ``NoData`` yields a standard N/A block for non-optional sections.

    Guarantee: every non-optional canonical section is present in the output.
    Optional sections (data_foundation, appendices, detected, in-app, email…) are
    only emitted when a renderer is supplied for them.

    ``na_reasons`` optionally overrides a section's default N/A copy:
    ``{"push_program": ("reason EN", "reason FR", "how EN", "how FR")}``.
    """
    na_reasons = na_reasons or {}
    specs = sections or cs.CANONICAL_SECTIONS
    out: List[str] = []
    for spec in specs:
        key = spec["key"]
        fn = renderers.get(key)
        if fn is None:
            if spec.get("optional"):
                continue  # optional + not provided -> legitimately omitted
            body = na_block(*_na_copy(spec, na_reasons, lang, None), lang=lang)
            out.append(section(spec, body, lang))
            continue
        try:
            rendered = fn(ctx, lang)
        except NoData as nd:
            rendered = None
            body = na_block(*_na_copy(spec, na_reasons, lang, nd), lang=lang)
            out.append(section(spec, body, lang) if not spec.get("raw") else body)
            continue
        if not rendered:
            if spec.get("optional"):
                continue
            body = na_block(*_na_copy(spec, na_reasons, lang, None), lang=lang)
            out.append(section(spec, body, lang))
            continue
        out.append(rendered if spec.get("raw") else section(spec, rendered, lang))
    return out


def _na_copy(spec, na_reasons, lang, nd):
    """Resolve (reason_en, reason_fr, how_en, how_fr) for an N/A block."""
    if nd is not None and (nd.reason_en or nd.reason_fr):
        return (nd.reason_en or nd.reason_fr, nd.reason_fr or nd.reason_en,
                nd.how_en, nd.how_fr)
    if spec["key"] in na_reasons:
        t = list(na_reasons[spec["key"]]) + ["", "", "", ""]
        return (t[0], t[1] or t[0], t[2], t[3])
    return (spec.get("na_en", "No data for this section."),
            spec.get("na_fr", spec.get("na_en", "Pas de données pour cette section.")),
            "", "")


# ---------------------------------------------------------------------------
# CSS + JS boilerplate (was duplicated per client)
# ---------------------------------------------------------------------------
FRAMEWORK_CSS = """
/* ---- shared engagement-review layout (base typography/tables/notes from brand) ---- */
.ir-charts-2{display:flex;flex-wrap:wrap;gap:16px}
.ir-charts-2>*{flex:1 1 360px;min-width:0}
.ir-cre-push{display:flex;flex-wrap:wrap;gap:16px}
.ir-cre-push>*{flex:1 1 320px;min-width:0}
.ir-cre-mc{display:flex;flex-wrap:wrap;gap:24px;justify-content:center;margin-top:8px}
.ir-cre-mc>*{flex:0 1 300px}
/* Safety net: a data table that forgot class="grid" still reads as a table rather
   than as raw browser default. The gate still flags it, but the reader never sees
   an unstyled dump. Scoped to .page so it can't touch layout tables. */
.page table{width:100%;border-collapse:collapse;margin:12px 0;font-size:13px}
.page table th{background:var(--ink);color:#fff;text-align:left;padding:9px 11px;font-size:12px;font-weight:600}
.page table td{border-bottom:1px solid var(--line);padding:8px 11px;vertical-align:top}
.page table tr:nth-child(even) td{background:var(--panel)}
/* secondary KPI cards under a hero band: same rhythm as .ir-hero */
.kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px;margin:14px 0}
.gauge-grid{display:flex;flex-wrap:wrap;gap:18px}
.gauge-card{flex:1 1 300px;background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px}
.verdict{background:var(--panel);border:1px solid var(--line);border-left:4px solid var(--teal);border-radius:12px;padding:14px 16px 14px 18px;margin:12px 0 4px;font-size:14px;line-height:1.9}
.na-block{margin:14px 0}
ul.key li,ol.reco li{margin:7px 0}
ol.reco li{font-size:13px;line-height:1.5}
.ir-langsw{display:flex;gap:6px;margin:10px 14px 4px}
.ir-langsw button{flex:1;background:rgba(255,255,255,.10);color:#c9c9d6;border:1px solid rgba(255,255,255,.20);border-radius:8px;padding:5px 0;font-weight:600;font-size:12px;cursor:pointer;font-family:var(--font-sans)}
.ir-langsw button.active{background:var(--accent);color:#fff;border-color:var(--accent)}
/* cover — Airship 2026 brand */
.page.cover{position:relative;overflow:hidden;color:#fff;padding:0;
  background:radial-gradient(120% 80% at 88% -12%,rgba(5,109,255,.55) 0%,rgba(5,109,255,0) 55%),
  linear-gradient(158deg,#000818 0%,#030869 68%,#056DFF 205%);}
.cover-mark{position:absolute;right:-150px;bottom:-165px;width:660px;height:auto;opacity:.14;pointer-events:none}
.cover-wrap{position:relative;z-index:1;padding:92px 84px;min-height:1754px;display:flex;flex-direction:column}
.cover-top{display:flex;align-items:center;gap:18px;margin-bottom:84px}
.cover-badge{border:1px solid rgba(255,255,255,.45);border-radius:999px;padding:6px 15px;font-size:12px;letter-spacing:.02em;color:#dfe7ff}
.cover-title{font-family:var(--font-display);font-weight:600;font-size:54px;line-height:1.08;margin:0 0 8px;color:#fff;letter-spacing:-.015em;max-width:15ch}
.cover-title::after{content:"";display:block;width:88px;height:4px;background:var(--teal);border-radius:2px;margin-top:24px}
.cover-sub{font-size:19px;color:#e9edff;margin:22px 0 40px;font-weight:500}
.cover-period{font-size:15px;color:#b8c4e8;line-height:1.85}
/* brand css paints strong/b in ink, which is invisible on the dark cover */
.page.cover b,.page.cover strong{color:#fff}
.cover-kpis{display:flex;gap:30px;margin-top:auto;margin-bottom:44px;flex-wrap:wrap}
.cover-kpis>div{display:flex;flex-direction:column;min-width:150px}
.cover-kpis b{font-size:34px;color:#fff;font-family:var(--font-display);font-weight:600;line-height:1}
.cover-kpis span{font-size:12px;color:#b8c4e8;margin-top:8px;max-width:180px}
.cover-foot{color:#8f9ecb;font-size:12px}
.cover-kpis code,.cover-period code{background:rgba(255,255,255,.14);color:#fff;border:none}
@media screen{.page.cover .cover-wrap{min-height:660px}}
"""


def _lang_toggle(primary: str) -> str:
    """EN/FR switch, with the report's primary language pre-selected."""
    btn = ('<button type="button" data-setlang="{c}"{a}>{u}</button>')
    return ('<div class="ir-langsw no-print" id="ir-langsw">'
            + "".join(btn.format(c=c, u=c.upper(),
                                 a=' class="active"' if c == primary else "")
                      for c in ("en", "fr"))
            + '</div>')


_LANG_JS = """
<script>
(function(){
  function apply(l){
    document.documentElement.lang=l;
    document.querySelectorAll('.ir-lang').forEach(function(d){ d.hidden = (d.getAttribute('data-lang')!==l); });
    document.querySelectorAll('#ir-langsw button').forEach(function(btn){
      btn.classList.toggle('active', btn.getAttribute('data-setlang')===l);
    });
    document.querySelectorAll('#ir-nav a').forEach(function(a){
      var id=a.getAttribute('href'); if(!id||id[0]!=='#')return;
      var sec=document.getElementById(id.slice(1)); if(!sec){a.style.display='none';return;}
      var host=sec.closest('.ir-lang');
      a.style.display=(host&&host.getAttribute('data-lang')!==l)?'none':'';
      /* a section with <h3> subheadings is wrapped in a collapsible .ir-toc-grp:
         hide/show the whole group (row + chevron + sub-links) with its parent link */
      if(a.classList.contains('ir-has-sub')){
        var grp=a.closest('.ir-toc-grp'); if(grp) grp.style.display=a.style.display;
      }
      /* relabel the parent link, preserving the muted sidebar number badge */
      var fr=sec.getAttribute('data-toc-fr');
      if(fr){
        var raw=(l==='fr'? fr : (sec.getAttribute('data-toc')||''));
        var parts=window.__irSplitNum? window.__irSplitNum(raw) : {num:'',label:raw};
        var lbl=a.querySelector('.ir-toc-lbl'); var numEl=a.querySelector('.ir-toc-num');
        if(lbl) lbl.textContent = parts.label || raw;
        if(numEl && parts.num) numEl.textContent = parts.num;
      }
    });
    /* thematic eyebrow labels are per-language: show only the active language's */
    document.querySelectorAll('#ir-nav .ir-toc-eyebrow').forEach(function(e){
      var el=e.getAttribute('data-lang'); e.style.display=(el && el!==l)?'none':'';
    });
    /* localise the sidebar tree Expand-all / Collapse-all control */
    if(window.__irTreeLocalize) window.__irTreeLocalize(l);
    var pdf=document.querySelector('.pdf-btn'); if(pdf) pdf.textContent = (l==='fr'?'Télécharger le PDF':'Download PDF');
    var ea=document.querySelector('[data-ir-expand="all"]'); if(ea) ea.textContent=(l==='fr'?'Tout déplier':'Expand all');
    var ec=document.querySelector('[data-ir-expand="none"]'); if(ec) ec.textContent=(l==='fr'?'Tout replier':'Collapse all');
  }
  function wire(){
    document.querySelectorAll('#ir-langsw button').forEach(function(btn){
      btn.addEventListener('click',function(){ apply(btn.getAttribute('data-setlang')); });
    });
    apply('en');
  }
  if(document.readyState!=='loading'){ setTimeout(wire,60); }
  else document.addEventListener('DOMContentLoaded', function(){ setTimeout(wire,60); });
})();
</script>
""".replace("apply('en')", "apply('__PRIMARY__')")

_SECTION_ID = re.compile(r'(<section\b[^>]*?\bid=")([^"]+)(")')


def _suffix_ids(pages: List[str], suffix: str) -> List[str]:
    return [_SECTION_ID.sub(lambda m: f'{m.group(1)}{m.group(2)}{suffix}{m.group(3)}', p)
            for p in pages]


def assemble(en_pages: List[str], fr_pages: Optional[List[str]] = None, *,
             title: str, pdf_filename: Optional[str] = None, brand: str = "Airship",
             css_extra: str = "", include_charts: bool = True,
             lang: str = "en", pdf_button: Optional[bool] = None) -> str:
    """Assemble the final self-contained HTML document.

    Bilingual when ``fr_pages`` is supplied: both languages ship, ``lang`` picks
    which one opens by default and which one the PDF prints (the other is
    screen-only, behind the toggle). The non-primary language's section ids get a
    ``-fr``/``-en`` suffix so the sidebar TOC resolves each menu link to its own
    language block.

    **Monolingual when ``fr_pages`` is None** — the default for a mode-A review. In
    that case the first argument carries the pages of whatever the single language
    is, and ``lang`` is what declares it: a French-only report is
    ``assemble(fr_pages, None, lang="fr")``, not a French payload smuggled through a
    parameter named ``en_pages``. The name is historical; ``lang`` is authoritative
    for the ``<html lang>`` attribute, the nav chrome and the number formatting.

    The sidebar download control follows :func:`set_pdf` — a report is not offered a
    PDF it does not ship, since a button pointing at a file nobody produced is worse
    than no button. Pass ``pdf_button`` explicitly to override.
    """
    if pdf_button is None:
        pdf_button = _PDF and bool(pdf_filename)
    bilingual = fr_pages is not None
    primary = ri.resolve_lang(lang)
    other = "fr" if primary == "en" else "en"
    css_block, nav_block, js_block = ri.interactive_head(
        pdf_filename=pdf_filename if pdf_button else None, brand=brand,
        include_charts=include_charts, layout="dashboard", lang=primary)

    # print the primary language only; the other stays available on screen
    print_css = (f'@media print{{ .ir-lang[data-lang="{other}"]{{display:none!important}} }}'
                 if bilingual else "")
    report_css = (ri.brand_report_css() + FRAMEWORK_CSS + print_css
                  + internal_css(primary, bilingual) + (css_extra or ""))
    # bilingual cluster labels for the sidebar tree eyebrows (screen only)
    clusters_js = (f'<script>window.IR_CLUSTERS='
                   f'{ri.json.dumps(cs.clusters_i18n(), ensure_ascii=False)};</script>')
    lang_js = ""
    if bilingual:
        nav_block = nav_block.replace('</div>', _lang_toggle(primary) + '</div>', 1)
        pages = {"en": en_pages, "fr": _suffix_ids(fr_pages, "-fr")}
        body = "".join(
            f'<div class="ir-lang" data-lang="{lg}"{"" if lg == primary else " hidden"}>'
            f'{"".join(pages[lg])}</div>' for lg in ("en", "fr"))
        lang_js = _LANG_JS.replace("__PRIMARY__", primary)
    else:
        body = "".join(en_pages)

    return f"""<!DOCTYPE html>
<html lang="{primary}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{ri.html.escape(title)}</title>
<style>{report_css}</style>
{css_block}
</head><body>
{nav_block}
<div class="ir-internal-run" aria-hidden="true"></div>
{body}
{clusters_js}
{js_block}
{lang_js}
</body></html>"""


# ---------------------------------------------------------------------------
# Provenance: what produced this report, stated on the report itself
# ---------------------------------------------------------------------------
# An account manager reads verdicts about a client's business that a model drafted,
# and will repeat some of them out loud in a meeting. Airship's own commitment is that
# AI involvement is marked so the reader knows, and it matters as much internally: the
# footer is what tells the reader which sentences to check before repeating them. The
# run hook already records which model actually ran, so this costs nothing but had to
# be asked for. The class name is the gate's hook: verify_report requires it.
PROVENANCE_CLASS = "ir-provenance"

# ---------------------------------------------------------------------------
# Internal-use marking
# ---------------------------------------------------------------------------
# The review is written for the Airship account team, not for the client: it is the
# preparation for a conversation, not a document that gets sent. The cover said so
# from the start, but page 1 is the one page that never travels — a chart pasted into
# a deck or a single page pulled out of the PDF carried nothing. So the marking goes
# on every page, and the gate refuses a report without it. The text rides in as a
# custom property so the stylesheet stays language-agnostic; `INTERNAL_VAR` is the
# gate's hook.
INTERNAL_VAR = "--ir-internal"
INTERNAL_LABEL = {"en": "Internal Airship usage only",
                  "fr": "Usage interne Airship uniquement"}


def internal_css(primary: str, bilingual: bool = False) -> str:
    """Declare the per-page marking text, scoped so each language gets its own.

    Custom properties inherit, so setting them on the language wrappers is enough for
    a bilingual document: every `.page` inside picks up the right string without the
    rule that draws it knowing anything about language.
    """
    out = f':root{{{INTERNAL_VAR}:"{INTERNAL_LABEL[primary]}"}}'
    if bilingual:
        out += "".join(f'.ir-lang[data-lang="{lg}"]{{{INTERNAL_VAR}:"{txt}"}}'
                       for lg, txt in INTERNAL_LABEL.items())
    return out

_MODEL_RE = re.compile(r"model actually used:\s*([A-Za-z0-9][\w.\-]*)")
# `[ \t]` rather than `\s`: `\s` crosses newlines, so an empty `Reviewed-by:` line
# followed by prose captured the next paragraph as the reviewer's name — an unfilled
# scaffold read as signed off, which is the one failure this check exists to prevent.
_REVIEWER_RE = re.compile(r"^[ \t]*Reviewed-by:[ \t]*(.+?)[ \t]*$", re.MULTILINE)


def _manifest_text(out_dir: str) -> str:
    """`run.md` beside the build, or "" when the hook never wrote one."""
    try:
        with open(os.path.join(out_dir, "run.md"), encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def manifest_models(text: str) -> List[str]:
    """Model slugs the run hook saw actually running, in first-seen order.

    The declared model is not the model you get — Cursor falls back under load —
    so the footer names what ran, not what was asked for. Bare slug only: the
    bracketed thinking/context flags are run detail, not provenance.
    """
    seen: List[str] = []
    for slug in _MODEL_RE.findall(text or ""):
        if slug not in seen:
            seen.append(slug)
    return seen


def manifest_reviewer(text: str) -> str:
    """The human recorded as having checked the report, or "".

    A placeholder left in the scaffold (``<!-- ... -->``, ``TBD``, ``TODO``) is not
    a reviewer: an unfilled line must read as unreviewed rather than satisfy the
    check by existing.
    """
    m = _REVIEWER_RE.search(text or "")
    if not m:
        return ""
    name = m.group(1).strip()
    if name.startswith("<!--") or name.upper() in {"TBD", "TODO", "N/A", "-"}:
        return ""
    return name


def provenance_block(out_dir: str, lang: str = "en") -> str:
    """The provenance footer: where the figures come from, what drafted the prose."""
    text = _manifest_text(out_dir)
    models = manifest_models(text)
    reviewer = manifest_reviewer(text)
    named = ", ".join(models)
    fr = str(lang).lower().startswith("fr")
    if fr:
        parts = ["Document \u00e0 usage interne Airship, destin\u00e9 \u00e0 l\u2019\u00e9quipe compte "
                 "et non au client."]
        parts.append("Les chiffres proviennent de l\u2019API Reports d\u2019Airship.")
        parts.append(f"Les commentaires ont \u00e9t\u00e9 r\u00e9dig\u00e9s avec l\u2019assistance d\u2019une IA"
                     f"{f' ({named})' if named else ''}.")
        if reviewer:
            parts.append(f"Relu par {reviewer} avant diffusion interne.")
        label = "Provenance"
    else:
        parts = ["Internal Airship document, written for the account team rather "
                 "than for the client."]
        parts.append("Figures are pulled from the Airship Reports API.")
        parts.append(f"The commentary was drafted with AI assistance"
                     f"{f' ({named})' if named else ''}.")
        if reviewer:
            parts.append(f"Reviewed by {reviewer} before circulation.")
        label = "Provenance"
    body = " ".join(parts)
    return (f'<div class="{PROVENANCE_CLASS}" style="max-width:62rem;margin:2.5rem auto 1.5rem;'
            f'padding:.9rem 1.1rem;border-top:1px solid rgba(0,0,0,.12);'
            f'font:400 12px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;'
            f'color:#5b6470">'
            f'<strong>{label}</strong> \u2014 {ri.html.escape(body)}</div>')


def with_provenance(html_doc: str, out_dir: str) -> str:
    """Insert the provenance footer before `</body>`, once.

    The language is read back off `<html lang>` rather than passed in: assemble()
    already decided it, and a second parameter is a second thing to keep in sync.
    """
    if PROVENANCE_CLASS in html_doc:
        return html_doc
    m = re.search(r'<html[^>]*\blang="([A-Za-z-]+)"', html_doc)
    block = provenance_block(out_dir, m.group(1) if m else "en")
    if "</body>" in html_doc:
        return html_doc.replace("</body>", block + "</body>", 1)
    return html_doc + block


# ---------------------------------------------------------------------------
# Delivery: a client-named copy outside the working tree
# ---------------------------------------------------------------------------
_DOWNLOADS = os.path.join(os.path.expanduser("~"), "Downloads")

_PROFILE_LABEL = {"full": "Engagement_Review", "goals": "Goals_Review"}


def delivery_filename(client: str, profile: str = "full",
                      day: Optional[str] = None) -> str:
    """`<Client>_<Review>_<YYYY-MM-DD>.html` — safe on every filesystem.

    The client name is what makes a downloaded file findable weeks later, and the
    date keeps successive runs from overwriting a version already sent.
    """
    # `\w` keeps accented letters: a name ending in "é" survives instead of being
    # truncated at the accent.
    slug = re.sub(r"\W+", "_", str(client or "Client"), flags=re.UNICODE).strip("_") or "Client"
    label = _PROFILE_LABEL.get(profile, "Review")
    return f"{slug}_{label}_{day or _dt.date.today().isoformat()}.html"


def deliver(out_path: str, client: str, *, profile: str = "full",
            dest_dir: str = _DOWNLOADS) -> Optional[str]:
    """Copy a built report to ``~/Downloads`` under a client-named filename.

    Never raises: a missing or unwritable Downloads folder must not fail a report
    that already passed the gate — the build output stays authoritative.
    """
    try:
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, delivery_filename(client, profile))
        shutil.copyfile(out_path, dest)
        print(f"[deliver] {dest}")
        return dest
    except OSError as exc:
        print(f"[deliver] WARNING: could not copy to {dest_dir} ({exc})")
        return None


# ---------------------------------------------------------------------------
# Build-time delivery gate
# ---------------------------------------------------------------------------
def write_report(html_doc: str, out_path: str, *, gate: bool = True,
                 charts_min: int = 5, creatives_min: int = 3,
                 allow_no_creatives: bool = False, sections_min: int = 16,
                 en_pages: Optional[List[str]] = None,
                 fr_pages: Optional[List[str]] = None,
                 profile: str = "full",
                 strict: bool = False,
                 client: Optional[str] = None,
                 downloads: bool = True,
                 keep_raw: bool = False,
                 sections: Optional[Sequence[dict]] = None) -> str:
    """Write the report to disk and (by default) run the blocking delivery gate.

    Raises ``BuildGateError`` if verify_report marks the report FAIL, so an
    incomplete report cannot be produced silently. Pass ``gate=False`` (wire a
    builder's ``--no-gate`` flag to it) to write without gating.

    ``profile`` selects which spine the gate enforces ("full" or "goals"). Under a
    non-default profile the gate defaults derive from that spine — a caller that
    passes only ``profile="goals"`` gets its section count and chart floor without
    having to restate them.

    Pass ``client`` to get a dated, client-named copy in ``~/Downloads`` once the
    gate passes (``downloads=False`` opts out). A gated-FAIL report is never copied,
    so what lands in Downloads has always cleared the gate and been signed off.

    ``strict`` promotes the gate's volume floors (section depth, recommendation /
    insight / chart / creative counts) from advisories back to blocking checks. The
    default reports them so a human decides whether a short report is thin or simply
    has less to say; set it for a flagship deliverable.

    On a delivered report the raw API pulls under ``work/<client>/data/`` are dropped:
    they were needed to produce the brief and are dead weight afterwards, and a
    client's send history should not outlive the run that asked for it. Everything the
    build path reads survives, so the report stays rebuildable. Pass ``keep_raw=True``
    (wire a builder's ``--keep-raw``) while still investigating an account.
    """
    if profile and profile != "full":
        bundle = cs.profile(profile)
        spine = list(sections or bundle["sections"])
        if sections_min == 16:
            sections_min = len(spine)
        if charts_min == 5:
            charts_min = min(3, len(bundle["charts"]))
        if creatives_min == 3:
            creatives_min, allow_no_creatives = 0, True
    out_dir = os.path.dirname(os.path.abspath(out_path))
    html_doc = with_provenance(html_doc, out_dir)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html_doc)
    # `en_pages`/`fr_pages` are primary/secondary, not English/French: a monolingual
    # French review passes its pages as the first and nothing as the second.
    n_primary = len(en_pages) if en_pages is not None else "?"
    n_second = len(fr_pages) if fr_pages is not None else "-"
    print(f"wrote {out_path} ({len(html_doc)//1024} KB), pages: {n_primary}, "
          f"second language: {n_second}")

    def _deliver():
        """Copy to Downloads once the gate passes. Returns the copy, or None."""
        if not (downloads and client):
            return None
        return deliver(out_path, client, profile=profile)

    def _drop_raw(delivered):
        """Retire the raw pulls, but only once the run has demonstrably finished.

        Four conditions, and each rules out a case where the data is still needed: a
        passing gate (the report is complete), an actual copy in Downloads (the
        artefact exists outside `work/`), no `--keep-raw`, and **no NotebookLM source
        pack in the picture**. A failed gate means the run is coming back.

        The pack condition is the one learned the hard way. The report is not the last
        deliverable when a source pack is also being produced, and the pack reads the
        same raw pulls; a rebuild of the report after the pack — to fix a section, say —
        would take the pack's inputs away underneath it, and the next `--refresh` would
        produce a thinner pack with no error. So the report builder never retires the
        pulls on a pack run: `build_source_pack.py` does it when the pack is written,
        which is genuinely the end.
        """
        if keep_raw or not delivered:
            return
        try:
            import purge_work as pwk
            if pwk.source_pack_involved(out_dir):
                print("[retention] raw pulls kept: a NotebookLM source pack reads them. "
                      "Retire them with build_source_pack.py --retire-raw when the run "
                      "is finished")
                return
            freed = pwk.reduce_raw(out_dir)
        except Exception as exc:  # noqa: BLE001 — never fail a delivered report
            print(f"[retention] WARNING: could not reduce raw pulls ({exc})")
            return
        if freed:
            print(f"[retention] dropped {freed / 1048576:.1f} MB of raw pulls; "
                  f"the report stays rebuildable (keep them with --keep-raw)")

    if not gate:
        print("[gate] skipped (gate=False)")
        _deliver()   # an ungated report is not a finished one: the pulls stay
        return out_path

    try:
        import verify_report as vr
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[gate] WARNING: could not import verify_report ({exc}); skipping gate")
        return out_path

    ok = vr.run(out_path, charts_min=charts_min, creatives_min=creatives_min,
                allow_no_creatives=allow_no_creatives, sections_min=sections_min,
                profile=profile, strict=strict)
    if not ok:
        raise BuildGateError(
            f"delivery gate FAILED for {out_path}. Fix the missing charts / creatives / "
            f"canonical sections above, or re-run the builder with --no-gate to override.")
    _drop_raw(_deliver())
    return out_path


# ---------------------------------------------------------------------------
# Self-test: the provenance footer and the delivery reviewer
# ---------------------------------------------------------------------------
def _selftest() -> int:
    """Pin what the footer is allowed to claim, and what withholds delivery."""
    import tempfile
    fails = []

    def check(cond, label):
        if not cond:
            fails.append(label)

    log = ("| 19:40:52 | stop | model actually used: "
           "claude-opus-5[thinking=true,context=300k] | | |\n")
    check(manifest_models(log) == ["claude-opus-5"],
          "the bracketed run flags are stripped from the model slug")
    check(manifest_models(log * 3) == ["claude-opus-5"],
          "a model recorded on every wave is named once")
    check(manifest_models("") == [], "no manifest means no model claim")
    check(manifest_models("| stop | model actually used: composer-2.5-fast |") ==
          ["composer-2.5-fast"], "a fallback model is reported as what ran")

    check(manifest_reviewer("Reviewed-by: Thomas Faro") == "Thomas Faro",
          "a named reviewer is read back")
    for empty in ("Reviewed-by:", "Reviewed-by: TBD", "Reviewed-by:   ",
                  "Reviewed-by: <!-- name -->", "",
                  # the scaffold shape: an empty line with prose under it
                  "Reviewed-by:\n\nThe line above names the human who checked this.\n"):
        check(manifest_reviewer(empty) == "",
              f"an unfilled reviewer line is not a reviewer ({empty!r})")

    with tempfile.TemporaryDirectory() as tmp:
        doc = '<!DOCTYPE html>\n<html lang="fr"><head></head><body><p>x</p></body></html>'
        # no manifest at all: the footer still ships, without naming a model
        out = with_provenance(doc, tmp)
        check(PROVENANCE_CLASS in out, "the footer ships even with no manifest")
        check("API Reports" in out, "the French footer states where figures come from")
        check("claude" not in out, "no model is named when none was recorded")

        with open(os.path.join(tmp, "run.md"), "w", encoding="utf-8") as fh:
            fh.write(log + "Reviewed-by: Thomas Faro\n")
        out = with_provenance(doc, tmp)
        check("claude-opus-5" in out, "the model that ran is named")
        check("Thomas Faro" in out, "the reviewer is named")
        check(out.count(PROVENANCE_CLASS) == 1, "the footer is injected once")
        check(with_provenance(out, tmp) == out, "re-injection is a no-op")
        check(out.index(PROVENANCE_CLASS) < out.index("</body>"),
              "the footer sits inside the body")

        en = with_provenance(doc.replace('lang="fr"', 'lang="en"'), tmp)
        check("drafted with AI assistance" in en, "an English report gets English text")
        check("Reviewed by Thomas Faro" in en, "the English footer names the reviewer")

        # a document with no </body> must still carry provenance
        check(PROVENANCE_CLASS in with_provenance("<html lang='en'>x", tmp),
              "a bodyless document still gets the footer")

        # the footer states the audience, because that is what makes the rest of it
        # readable: a model-drafted verdict is different information depending on
        # whether the client is holding the page
        check("Internal Airship document" in en, "the English footer states the audience")
        fr_foot = with_provenance(doc, tmp)
        check("usage interne Airship" in fr_foot, "the French footer states the audience")

    # ---- the per-page internal-use marking ----
    # Page 1 already said it; every other page did not, and those are the pages that
    # travel. The gate looks for the custom property, so that is what must be emitted.
    css = internal_css("en")
    check(f'{INTERNAL_VAR}:"Internal Airship usage only"' in css,
          "the English marking is declared on :root")
    check(internal_css("fr").count(INTERNAL_VAR) == 1,
          "a monolingual report declares the marking once")
    bi = internal_css("en", bilingual=True)
    check(bi.count(INTERNAL_VAR) == 3,
          f"a bilingual report scopes the marking per language, got {bi}")
    for lg, txt in INTERNAL_LABEL.items():
        check(f'.ir-lang[data-lang="{lg}"]{{{INTERNAL_VAR}:"{txt}"}}' in bi,
              f"the {lg} pages carry the {lg} marking")

    pages = ['<section class="page cover">c</section>', '<section class="page">p</section>']
    for lg, txt in INTERNAL_LABEL.items():
        doc = assemble(list(pages), None, title="T", lang=lg)
        check(INTERNAL_VAR in doc, f"an assembled {lg} report declares the marking")
        check(txt in doc, f"an assembled {lg} report carries the {lg} wording")
        # the rule that draws it has to be in the same document as the value
        check(f"var({INTERNAL_VAR}" in doc,
              f"the {lg} report ships the rule that prints the marking")
        check(".page:not(.cover)::after" in doc,
              "the cover is excluded — it is dark, and already carries the wording")
    en_doc = assemble(list(pages), None, title="T", lang="en")
    check(INTERNAL_LABEL["fr"] not in en_doc,
          "a monolingual English report does not smuggle in the French wording")
    # In print `.page` collapses to content height so a long section can flow across
    # sheets, which also means the in-flow marking would land mid-sheet and mark only
    # the last one. The running element is what makes it per-sheet; verified on a
    # six-sheet PDF, all six marked at the page foot.
    check('class="ir-internal-run"' in en_doc,
          "the print-only running marking is in the document")
    check(".ir-internal-run{display:none}" in en_doc,
          "the running marking is hidden on screen, where there are no sheets")
    check(en_doc.index('class="ir-internal-run"') < en_doc.index('class="page'),
          "the running element precedes the pages, so z-index is what lifts it")

    for f in fails:
        print(f"  \u2717 {f}")
    print(f"provenance selftest: {'FAIL' if fails else 'ok'} ({len(fails)} failure(s))")
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    print(__doc__)
