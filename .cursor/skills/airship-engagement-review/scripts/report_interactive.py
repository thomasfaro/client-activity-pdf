#!/usr/bin/env python3
"""Interactive HTML report toolkit for the Airship engagement review.

The review is delivered as a SINGLE self-contained interactive HTML file (assets
embedded as base64) — the primary deliverable — with a downloadable PDF companion
produced by build_report.py from the same HTML.

This module provides the reusable building blocks the per-run report author uses:

  Deep-links (Flight Deck)
    - decode_pushbody(push_body)          -> dict (handles b64 string / api dict)
    - composer_id_from_pushbody(push_body)-> options.__ui_id  (the composer id)
    - flight_deck_url(app_key, ui_id, region)
    - flight_deck_button(url, label)

  Airship feature detection (for the adoption / best-practice scorecards)
    - push_features(pushbody_dict)        -> {rich, deeplink, personalization, ...}

  Interactive scaffold (screen web-app + paginated print in one HTML)
    - interactive_head(pdf_filename, layout="dashboard")
                                          -> (css_block, nav_block, js_block)
      screen = fixed sidebar (auto TOC + scroll-spy, Download-PDF, Expand/Collapse-all)
      + fluid `.ir-main` reading column; print = the unchanged paginated PDF.
    - INTERACTIVE_CSS / INTERACTIVE_JS    -> drop into <head>
    - tooltip(text, tip)                  -> hover definition/benchmark source
    - collapsible(summary, body, open_)   -> <details> (forced open in print)
    - gauge(value, p10, p50, p90, ...)    -> benchmark gauge (SVG, print-safe)
    - verdict_pill(tier, label)           -> Good/Average/Poor style pill
    - methodology(formula, inputs, ...)   -> "how it's computed" block for a KPI
    - kpi_card(value, label, formula=...) -> KPI number + methodology modal trigger
    - creative_push_preview(img, caption) -> push notification card
    - creative_mc_preview(img, caption)   -> Message Center in a phone viewport
    - pdf_download_button(pdf_filename)
    Tables: add class `ir-searchable` for a filter box, `ir-exportable` for a CSV button
    (both screen-only); `ir-sortable` keeps click-to-sort.

  Interactive charts (Chart.js, inlined -> single offline file)
    - chartjs_inline()                    -> <script> with the vendored Chart.js
    - interactive_chart(id, png, spec)    -> static PNG (print) + canvas (screen)
    Progressive enhancement: the PDF always uses the PNG; the canvas lights up on screen.

Print rules honoured: .no-print hidden, nav hidden, every <details> forced open,
tooltips inlined, charts fall back to their static PNG. Pairs with
@page{size:1240px 1754px} in the report's own CSS.

No third-party deps. Python 3.8+.
"""
from __future__ import annotations

import base64
import html
import json
import os
import re
from typing import Optional, Sequence, Union

_VENDOR_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor")
_CHARTJS_PATH = os.path.join(_VENDOR_DIR, "chart.umd.min.js")
_ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

# ---------------------------------------------------------------------------
# Airship 2026 brand kit (colors, fonts, logo) — sourced from the AIRSHIP 2026
# Master deck + airship.com. Use these so every report matches the corporate look.
# ---------------------------------------------------------------------------
BRAND = {
    "ink": "#000818",        # near-black navy (headings / dark surfaces)
    "blue": "#056DFF",       # primary accent
    "navy": "#030869",       # deep indigo (secondary)
    "teal": "#11DBC0",       # positive signal
    "lime": "#E6F55A",       # highlight
    "sky": "#7ABFFF",
    "lightblue": "#DCEAFF",
    "coral": "#E4626F",      # negative signal (opt-out / churn)
    "grey": "#717680",       # secondary text
    "grey2": "#414651",      # body text (dark grey)
    "panel": "#F7F8F8",      # off-white surface
    "line": "#E9EAEB",       # hairline borders
    "white": "#FFFFFF",
}
# Font stacks (families embedded by brand_fonts_css()).
FONT_SANS = "'Instrument Sans',-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
FONT_DISPLAY = "'Zalando Sans Expanded','Instrument Sans',-apple-system,'Segoe UI',Helvetica,Arial,sans-serif"
FONT_MONO = "'Geist Mono','SF Mono',ui-monospace,Menlo,Consolas,monospace"

_BRAND_FONTS_CSS_CACHE = None


def brand_fonts_css() -> str:
    """Return the @font-face rules embedding the Airship brand fonts (base64 woff2).

    Reads scripts/assets/brand_fonts.css (Instrument Sans, Zalando Sans Expanded,
    Geist Mono; latin + latin-ext). Returns "" if the asset is missing so reports
    still render with the system fallback stack.
    """
    global _BRAND_FONTS_CSS_CACHE
    if _BRAND_FONTS_CSS_CACHE is None:
        try:
            with open(os.path.join(_ASSETS_DIR, "brand_fonts.css"), "r", encoding="utf-8") as f:
                _BRAND_FONTS_CSS_CACHE = f.read()
        except OSError:
            _BRAND_FONTS_CSS_CACHE = ""
    return _BRAND_FONTS_CSS_CACHE


def brand_asset_datauri(name: str) -> str:
    """Return a data: URI for a brand asset PNG in scripts/assets (e.g. a logo)."""
    path = os.path.join(_ASSETS_DIR, name)
    try:
        with open(path, "rb") as fh:
            return "data:image/png;base64," + base64.b64encode(fh.read()).decode()
    except OSError:
        return ""


_LOGO_FILES = {
    "white": "airship_logo_white.png",   # full wordmark, white (dark backgrounds)
    "ink": "airship_logo_ink.png",       # full wordmark, ink (light backgrounds)
    "mark_blue": "airship_mark_blue.png",  # diamond mark only, Airship blue
    "mark_white": "airship_mark_white.png",  # diamond mark only, white
}


def brand_logo(variant: str = "white", height: int = 30, alt: str = "Airship",
               css_class: str = "") -> str:
    """An <img> of the Airship logo/mark (base64-embedded).

    variant: white | ink | mark_blue | mark_white. Returns "" if the asset is absent.
    """
    uri = brand_asset_datauri(_LOGO_FILES.get(variant, _LOGO_FILES["white"]))
    if not uri:
        return ""
    cls = f' class="{html.escape(css_class)}"' if css_class else ""
    return (f'<img{cls} src="{uri}" alt="{html.escape(alt)}" '
            f'style="height:{int(height)}px;width:auto;display:inline-block">')


# ---------------------------------------------------------------------------
# Brand pictograms (line-art icons borrowed from the Airship slides system)
# ---------------------------------------------------------------------------
_ICON_CACHE: dict = {}


def icon_datauri(name: str, dark: bool = False) -> str:
    """data: URI for a pictogram PNG in scripts/assets/icons/{light-bg|dark-bg}.

    ``dark=True`` returns the chartreuse-on-dark variant (for the navy sidebar);
    the default light variant (navy+blue line art) reads well on white/panel cards.
    Returns "" when the asset is absent so callers degrade gracefully.
    """
    key = (name, dark)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]
    sub = "dark-bg" if dark else "light-bg"
    path = os.path.join(_ASSETS_DIR, "icons", sub, f"{name}.png")
    try:
        with open(path, "rb") as fh:
            uri = "data:image/png;base64," + base64.b64encode(fh.read()).decode()
    except OSError:
        uri = ""
    _ICON_CACHE[key] = uri
    return uri


# keyword -> icon, first match wins (order matters: specific before generic)
_ICON_KEYWORDS = [
    ("email", "email-marketing"), ("mail", "email-marketing"),
    ("opt-out", "security-shield"), ("optout", "security-shield"),
    ("permission", "security-shield"), ("consent", "security-shield"),
    ("privacy", "security-shield"), ("unsub", "security-shield"),
    ("opt-in", "user-profile"), ("optin", "user-profile"),
    ("audience", "user-profile"), ("subscriber", "user-profile"),
    ("reachable", "user-profile"), ("recipient", "user-profile"),
    ("device", "cross-device"), ("platform", "cross-device"),
    ("install", "cross-device"), ("base", "cross-device"),
    ("web", "globe"), ("reach", "globe"),
    ("channel", "omnichannel-mobile"), ("cross-channel", "omnichannel-mobile"),
    ("broadcast", "megaphone"), ("campaign", "megaphone"), ("marquee", "megaphone"),
    ("creative", "creative-assets"),
    ("push", "lifecycle-notifications"), ("send", "lifecycle-notifications"),
    ("notification", "lifecycle-notifications"), ("delivered", "lifecycle-notifications"),
    ("volume", "lifecycle-notifications"), ("pressure", "lifecycle-notifications"),
    ("frequency", "lifecycle-notifications"), ("in-app", "lifecycle-notifications"),
    # section-title oriented keywords (for header / TOC pictograms)
    ("benchmark", "analytics-chart"),
    ("strateg", "insights-lightbulb"), ("priorit", "insights-lightbulb"),
    ("recommend", "insights-lightbulb"), ("summary", "insights-lightbulb"),
    ("playbook", "creative-assets"), ("experiment", "creative-assets"),
    ("typology", "megaphone"), ("detected", "megaphone"),
    ("foundation", "cross-device"),
    ("profile", "user-profile"),
    ("context", "globe"),
    ("best practice", "security-shield"), ("best-practice", "security-shield"),
    ("appendix", "analytics-chart"), ("methodology", "analytics-chart"),
    ("value", "insights-lightbulb"), ("conversion", "insights-lightbulb"),
    ("revenue", "insights-lightbulb"), ("vod", "insights-lightbulb"),
    ("view", "insights-lightbulb"), ("coupon", "insights-lightbulb"),
    ("goal", "insights-lightbulb"), ("insight", "insights-lightbulb"),
    ("app", "mobile-orbit"), ("mobile", "mobile-orbit"), ("session", "mobile-orbit"),
    ("open", "analytics-chart"), ("engagement", "analytics-chart"),
    ("click", "analytics-chart"), ("ctr", "analytics-chart"), ("rate", "analytics-chart"),
    ("active", "analytics-chart"), ("dau", "analytics-chart"), ("mau", "analytics-chart"),
]


def pick_icon(label: Optional[str]) -> str:
    """Best-effort keyword match of a KPI/card label to a pictogram name."""
    if not label:
        return "analytics-chart"
    low = str(label).lower()
    for kw, ico in _ICON_KEYWORDS:
        if kw in low:
            return ico
    return "analytics-chart"


def icon_img(name: Optional[str], *, label: Optional[str] = None,
             css_class: str = "ir-ico", dark: bool = False) -> str:
    """<img> pictogram tag; resolves ``name`` (or infers from ``label``).

    Returns "" when no asset can be resolved so cards stay clean if assets move.
    """
    n = name or pick_icon(label)
    uri = icon_datauri(n, dark=dark)
    if not uri:
        return ""
    return (f'<img class="{html.escape(css_class)}" src="{uri}" alt="" '
            f'aria-hidden="true" loading="lazy">')


def brand_report_css() -> str:
    """Shared base stylesheet for a report body, in the Airship 2026 brand.

    Covers page geometry, typography (Zalando Sans Expanded display + Instrument Sans
    body + Geist Mono code), tables (.grid), notes (.note / .note-up / .note-warn),
    tags, pills, small/source text and common layout helpers (.two-col). Include it in
    the report <head> BEFORE interactive_head()'s css_block. Per-report cover styles
    stay in the report (they vary), but should use the BRAND tokens / var(--*) below.
    """
    b = BRAND
    return f""":root{{
  --ink:{b['ink']};--text:{b['grey2']};--blue:{b['blue']};--accent:{b['blue']};
  --navy:{b['navy']};--teal:{b['teal']};--mint:{b['teal']};--indigo:{b['navy']};
  --lime:{b['lime']};--sky:{b['sky']};--lightblue:{b['lightblue']};--coral:{b['coral']};
  --grey:{b['grey']};--panel:{b['panel']};--line:{b['line']};
  --font-sans:{FONT_SANS};--font-display:{FONT_DISPLAY};--font-mono:{FONT_MONO};
}}
*{{box-sizing:border-box}}
body{{font-family:{FONT_SANS};color:{b['grey2']};line-height:1.55;-webkit-font-smoothing:antialiased;}}
@page{{size:1240px 1754px;margin:0}}
.page{{width:1240px;min-height:1754px;background:#fff;padding:64px 72px;position:relative;}}
/* Internal-use marking, on every page rather than only the cover: a page extracted
   from the PDF or a screenshot of one chart has to carry it too. Chrome's
   --print-to-pdf ignores CSS paged-media margin boxes, so an @page @bottom-center
   would render nothing — this is in flow instead, and prints exactly as it screens.
   The text arrives as a custom property set by assemble() (see report_framework),
   which keeps this sheet language-agnostic; unset, the rule renders nothing. The
   cover is excluded: it is dark-on-light and already carries the same wording. */
.page:not(.cover)::after{{content:var(--ir-internal,"");position:absolute;
  left:72px;right:72px;bottom:24px;text-align:right;pointer-events:none;
  font:500 9.5px/1 {FONT_SANS};letter-spacing:.09em;text-transform:uppercase;
  color:{b['grey']};}}
/* the print-only running counterpart (see @media print at the end of this sheet) */
.ir-internal-run{{display:none}}
h1,h2,h3,h4{{color:{b['ink']};line-height:1.18;font-family:{FONT_DISPLAY};font-weight:600;letter-spacing:-.01em;}}
h2{{font-size:27px;padding-bottom:10px;margin:0 0 20px;position:relative;border-bottom:1px solid {b['line']};}}
h2::after{{content:"";position:absolute;left:0;bottom:-1px;width:64px;height:3px;background:{b['blue']};border-radius:2px;}}
.ir-h2-ico{{width:30px;height:30px;vertical-align:-6px;margin-right:12px;opacity:1;display:inline-block;
  filter:drop-shadow(0 0 .5px {b['blue']});}}
.ir-row-ico{{width:22px;height:22px;vertical-align:-5px;margin-right:9px;opacity:1;display:inline-block;
  filter:drop-shadow(0 0 .4px {b['blue']});}}
h3{{font-size:18px;margin:24px 0 9px;font-weight:600;}}
h4{{font-size:15px;margin:0 0 6px;font-weight:600;}}
p{{margin:9px 0}}
a{{color:{b['blue']}}}
code{{background:{b['panel']};border:1px solid {b['line']};border-radius:5px;padding:1px 5px;font-family:{FONT_MONO};font-size:.85em;color:{b['navy']};}}
strong,b{{color:{b['ink']};font-weight:600;}}
.tag{{background:{b['lightblue']};color:{b['navy']};border-radius:6px;padding:1px 8px;font-size:11px;font-weight:600;white-space:nowrap;font-family:{FONT_MONO};}}
table.grid{{width:100%;border-collapse:collapse;margin:12px 0;font-size:13px}}
table.grid th{{background:{b['ink']};color:#fff;text-align:left;padding:9px 11px;font-size:12px;font-weight:600;}}
table.grid{{table-layout:auto;}}
table.grid td{{border-bottom:1px solid {b['line']};padding:8px 11px;vertical-align:top;overflow-wrap:break-word;}}
table.grid td .pill,table.grid td .tag{{white-space:nowrap;}}
table.grid td code{{white-space:normal;overflow-wrap:anywhere;word-break:break-word;}}
/* `wide`: for many-column tables (campaign inventory) whose long identifier cells
   would otherwise push the table past the page. Tighter type and padding buy most of
   the room; `td.brk` buys the rest. */
table.grid.wide{{font-size:12px;}}
table.grid.wide th{{padding:8px 8px;font-size:11px;}}
table.grid.wide td{{padding:7px 8px;}}
/* `brk`: a cell holding a machine identifier. `overflow-wrap:break-word` does not
   reduce a cell's min-content width, so an unbreakable token like
   `click_push_tabaski_callers_270526` keeps the table wide however narrow the column
   gets — only `anywhere` lets it shrink. Applied per cell, never table-wide, so
   ordinary prose still breaks on word boundaries. */
table.grid td.brk{{overflow-wrap:anywhere;}}
/* event/property identifier columns: give the name enough room that `added_to_cart`
   does not break into `added_to_` + `cart`. Only the leading key columns — the sample
   columns still need to wrap freely. */
table[data-csv-name="tracked_events"] td:first-child,
table[data-csv-name="event_property_values"] td:first-child,
table[data-csv-name="event_property_values"] td:nth-child(2){{min-width:142px;}}
table.grid tr:nth-child(even) td{{background:{b['panel']}}}
table.grid tr:hover td{{background:{b['lightblue']}}}
/* the analysed client's own row in a peer/competitor table */
table.grid tr.is-me td,table.grid tr.is-me:nth-child(even) td{{background:{b['lightblue']};
  font-weight:600;box-shadow:inset 3px 0 0 {b['blue']};}}
.note{{background:{b['panel']};border:1px solid {b['line']};border-left:4px solid {b['blue']};border-radius:12px;padding:13px 17px;margin:15px 0;font-size:13px}}
.note-up{{border-left-color:{b['teal']}}}
.note-warn{{border-left-color:{b['coral']}}}
.src,.small{{font-size:12px;color:{b['grey']}}}
.foot-note{{margin-top:26px;color:{b['grey']};font-size:11px;border-top:1px solid {b['line']};padding-top:10px}}
.two-col{{display:flex;gap:24px;flex-wrap:wrap}}
.two-col>div{{flex:1 1 340px}}
.pill{{border-radius:999px;padding:2px 10px;font-size:11px;font-weight:600;font-family:{FONT_SANS};white-space:nowrap;}}
.pill-good{{background:#e2f8f3;color:#0a7d6b}}
.pill-mid{{background:#fff4e0;color:#a76a00}}
.pill-low{{background:#fdeef0;color:#b3172c}}
@media print{{
  /* Each narrative section starts on a fresh sheet (1 .page = 1 sheet). Long
     data-appendix tables are allowed to flow across sheets; their <thead>
     repeats and rows are kept intact. Avoids packing + trailing blank pages. */
  .page{{break-before:page;break-inside:auto;min-height:0;}}
  .page:first-child{{break-before:auto;}}
  /* trailing whitespace on the very last sheet is enough to spill a blank page */
  .page:last-child{{padding-bottom:0;}}
  .page:last-child>*:last-child{{margin-bottom:0;}}
  table.grid{{break-inside:auto}}
  table.grid thead{{display:table-header-group}}
  table.grid tr{{break-inside:avoid}}
  /* `min-height:0` above is what lets a long section flow across sheets, and it also
     means the in-flow marking anchors to the content rather than to the sheet: an
     appendix spanning four sheets would mark only the last one. So in print the
     marking becomes a fixed element instead, which Chrome repeats on every sheet --
     the running footer that @page margin boxes would have given us if Chrome
     supported them. Screen keeps the in-flow one, where there are no sheets. */
  .page:not(.cover)::after{{content:none}}
  /* z-index because the cover fills its whole sheet and is positioned: without it
     the cover paints over the running footer and sheet 1 loses the marking. No
     `filter` or `mix-blend-mode` here, tempting as they are for contrast against the
     dark cover: either one promotes this to its own compositing layer, and Chrome
     then paints it once instead of repeating it -- which cost five of six sheets
     their marking when tried. Plain colour is what repeats. */
  .ir-internal-run{{display:block;position:fixed;bottom:18px;left:72px;right:72px;
    z-index:99;text-align:right;font:500 9.5px/1 {FONT_SANS};letter-spacing:.09em;
    text-transform:uppercase;color:{b['grey']};}}
  .ir-internal-run::after{{content:var(--ir-internal,"")}}
}}
"""

# ---------------------------------------------------------------------------
# Deep-links (Airship Flight Deck)
# ---------------------------------------------------------------------------

def decode_pushbody(push_body: Union[str, dict, None]) -> dict:
    """Return the decoded push body as a dict.

    Accepts:
      - the base64 string returned in perpush/pushbody -> response.push_body
      - the full API response dict (has a "push_body" or "response" key)
      - an already-decoded dict
    Returns {} when nothing decodable (e.g. empty UNICAST body).
    """
    if push_body is None:
        return {}
    if isinstance(push_body, dict):
        # full API envelope?
        if "response" in push_body and isinstance(push_body["response"], dict):
            return decode_pushbody(push_body["response"])
        if "push_body" in push_body:
            return decode_pushbody(push_body["push_body"])
        return push_body
    if isinstance(push_body, str):
        s = push_body.strip()
        if not s:
            return {}
        # tolerate url-safe / missing padding
        s2 = s.replace("-", "+").replace("_", "/")
        s2 += "=" * (-len(s2) % 4)
        try:
            raw = base64.b64decode(s2)
            return json.loads(raw.decode("utf-8"))
        except Exception:
            try:
                return json.loads(s)  # maybe it was raw JSON
            except Exception:
                return {}
    return {}


def composer_id_from_pushbody(push_body: Union[str, dict, None]) -> Optional[str]:
    """Extract the dashboard composer id (``options.__ui_id``).

    This is the id used in the Flight Deck URL .../messages/{composer_id}; it is a
    base64url-encoded UUID and is NOT the push_id. Present only for messages
    composed in the dashboard (broadcast / segments / A-B); UNICAST/API sends have
    an empty body and return None.
    """
    pb = decode_pushbody(push_body)
    ui = pb.get("options", {}).get("__ui_id")
    return ui or None


def flight_deck_url(app_key: str, ui_id: str, region: str = "eu") -> str:
    """Build the Flight Deck message URL.

    region: "eu" -> go-admin.airship.eu ; anything else -> go-admin.airship.com
    """
    tld = "eu" if str(region).lower() == "eu" else "com"
    return f"https://go-admin.airship.{tld}/admin/flight_deck/apps/{app_key}/messages/{ui_id}"


def flight_deck_button(url: Optional[str], label: str = "Open in Flight Deck",
                       unavailable: str = "No deep-link (UNICAST/API send)") -> str:
    """Anchor button linking to Flight Deck (kept clickable in the PDF too).

    When url is falsy, render a muted 'unavailable' pill instead of a dead link.
    """
    if not url:
        return f'<span class="fd-na">{html.escape(unavailable)}</span>'
    return (f'<a class="fd-btn" href="{html.escape(url)}" '
            f'target="_blank" rel="noopener">{html.escape(label)}</a>')


# ---------------------------------------------------------------------------
# Airship feature detection (adoption + best-practice scorecards)
# ---------------------------------------------------------------------------

def push_features(pushbody: Union[str, dict, None]) -> dict:
    """Detect which Airship features a message uses, from its decoded push body.

    Returns a dict of booleans/strings:
      rich, deeplink, personalization, message_center, frequency_bypass,
      is_test, message_name, has_image_url
    All best-effort; absent fields default False/None.
    """
    pb = decode_pushbody(pushbody)
    opts = pb.get("options", {}) if isinstance(pb.get("options"), dict) else {}
    notif = pb.get("notification", {}) if isinstance(pb.get("notification"), dict) else {}
    blob = json.dumps(pb, ensure_ascii=False)

    ios = notif.get("ios", {}) if isinstance(notif.get("ios"), dict) else {}
    android = notif.get("android", {}) if isinstance(notif.get("android"), dict) else {}
    android_style = android.get("style", {}) if isinstance(android.get("style"), dict) else {}
    image_url = (
        (ios.get("media_attachment", {}) or {}).get("url")
        or android_style.get("big_picture")
        or android.get("big_picture")
    )

    return {
        "rich": bool(image_url),
        "has_image_url": image_url or None,
        "deeplink": ("uairship://" in blob) or ("deep_link" in blob),
        "personalization": bool(opts.get("personalization")) or ("{{" in blob),
        "message_center": bool(pb.get("message")),
        "frequency_bypass": bool(opts.get("bypass_frequency_limits")),
        "is_test": bool(opts.get("is_test")),
        "message_name": opts.get("message_name"),
    }


# ---------------------------------------------------------------------------
# Interactive scaffold — CSS (screen + print in one stylesheet)
# ---------------------------------------------------------------------------

INTERACTIVE_CSS = """
:root{
  --ink:#000818;--text:#414651;--grey:#717680;--accent:#056DFF;
  --indigo:#030869;--navy:#030869;--blue:#056DFF;--mint:#11DBC0;--teal:#11DBC0;
  --lime:#E6F55A;--sky:#7ABFFF;--lightblue:#DCEAFF;--coral:#E4626F;
  --panel:#F7F8F8;--line:#E9EAEB;
  --font-sans:'Instrument Sans',-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
  --font-display:'Zalando Sans Expanded','Instrument Sans',-apple-system,'Segoe UI',Helvetica,Arial,sans-serif;
  --font-mono:'Geist Mono','SF Mono',ui-monospace,Menlo,Consolas,monospace;
}
html{scroll-behavior:smooth;}
body{margin:0;color:var(--text);}
/* ================= shared components (screen + print) ================= */
/* download-pdf + flight-deck buttons */
.pdf-btn,.fd-btn{display:inline-block;text-decoration:none;border-radius:8px;
  font:700 12px/1 var(--font-sans);}
.pdf-btn{background:var(--accent);color:#fff;padding:8px 14px;}
.fd-btn{background:#fff;color:var(--blue);border:1.5px solid var(--blue);
  padding:6px 12px;}
.fd-btn:hover{background:var(--blue);color:#fff;}
.fd-na{display:inline-block;color:var(--grey);font:600 11px/1 var(--font-sans);
  font-style:italic;padding:6px 10px;background:var(--panel);border-radius:8px;}
/* tooltip */
.ir-tip{position:relative;border-bottom:1px dotted var(--grey);cursor:help;}
.ir-tip .ir-tip-text{visibility:hidden;opacity:0;transition:opacity .15s;
  position:absolute;bottom:135%;left:50%;transform:translateX(-50%);z-index:1000;
  width:260px;background:var(--ink);color:#fff;text-align:left;border-radius:8px;
  padding:10px 12px;font:400 12px/1.45 var(--font-sans);box-shadow:0 6px 20px rgba(0,0,0,.25);}
.ir-tip:hover .ir-tip-text{visibility:visible;opacity:1;}
/* collapsibles */
details.ir-collapse{background:var(--panel);border:1px solid var(--line);
  border-radius:12px;padding:6px 16px;margin:12px 0;}
details.ir-collapse>summary{cursor:pointer;font:700 15px/1.3 var(--font-sans);
  color:var(--ink);padding:8px 0;list-style:none;}
details.ir-collapse>summary::-webkit-details-marker{display:none;}
details.ir-collapse>summary::before{content:"\\25B8";color:var(--accent);
  margin-right:8px;display:inline-block;transition:transform .15s;}
details.ir-collapse[open]>summary::before{transform:rotate(90deg);}
/* sortable tables */
table.ir-sortable th[data-sortable]{cursor:pointer;user-select:none;}
table.ir-sortable th[data-sortable]::after{content:"\\2195";opacity:.4;margin-left:6px;font-size:.8em;}
table.ir-sortable th.ir-asc::after{content:"\\2191";opacity:1;}
table.ir-sortable th.ir-desc::after{content:"\\2193";opacity:1;}
/* benchmark gauge */
.gauge-wrap{display:block;}
.gauge{font:400 11px/1.3 var(--font-sans);color:var(--text);}
.gauge .g-band{fill:var(--line);}
.gauge .g-p50{stroke:var(--grey);stroke-width:2;}
.gauge .g-val{fill:var(--accent);}
.gauge .g-lbl{fill:var(--grey);font-size:10px;}
/* verdict pills */
.pill{display:inline-block;border-radius:999px;padding:2px 10px;font:700 11px/1.4 var(--font-sans);white-space:nowrap;}
.pill-good{background:#e6f7f0;color:#0a7d57;}
.pill-mid{background:#fff3e0;color:#a15c00;}
.pill-low{background:#fdeaec;color:#b21e33;}
/* interactive charts (progressive enhancement over a static PNG fallback) */
.ir-chart{position:relative;margin:0;}
.ir-chart .ir-chart-static{display:block;max-width:100%;height:auto;}
.ir-chart .ir-chart-canvas{display:none;position:relative;width:100%;}
/* once JS mounts a Chart, the figure gets .ir-live: swap PNG -> canvas (screen only) */
.ir-chart.ir-live .ir-chart-static{display:none;}
.ir-chart.ir-live .ir-chart-canvas{display:block;}
/* KPI card + methodology modal (screen) / inline print block */
.ir-kpi{flex:1 1 220px;background:#fff;border:1px solid var(--line);
  border-radius:14px;padding:16px 18px;box-sizing:border-box;
  box-shadow:0 1px 2px rgba(3,8,105,.04);transition:box-shadow .15s,transform .15s;}
.ir-kpi-head{display:flex;align-items:flex-start;justify-content:space-between;gap:8px;}
.ir-kpi-val{font:800 30px/1 var(--font-sans);color:var(--ink);}
.ir-kpi-val.sm{font-size:23px;}
.ir-kpi-label{font:600 12.5px/1.3 var(--font-sans);
  color:var(--grey);margin-top:7px;}
.ir-kpi-info{flex-shrink:0;width:28px;height:28px;border-radius:50%;
  border:1.5px solid var(--blue);background:#fff;color:var(--blue);
  font:700 15px/1 var(--font-sans);cursor:pointer;padding:0;margin-top:2px;}
.ir-kpi-info:hover,.ir-kpi-info:focus{background:var(--blue);color:#fff;outline:none;}
.ir-kpi-info:focus-visible{box-shadow:0 0 0 3px rgba(0,102,204,.35);}
.ir-kpi-method-print{display:none;margin-top:10px;}
@media screen{.ir-kpi-method-print{display:none!important;}}
/* shared methodology modal (one per report) */
.ir-modal{position:fixed;inset:0;z-index:10000;display:flex;align-items:center;
  justify-content:center;padding:16px;box-sizing:border-box;}
.ir-modal[hidden]{display:none!important;}
.ir-modal-backdrop{position:absolute;inset:0;background:rgba(22,22,29,.55);}
.ir-modal-dialog{position:relative;background:#fff;border-radius:16px;max-width:520px;
  width:100%;max-height:min(85vh,640px);overflow-y:auto;padding:24px 28px 20px;
  box-shadow:0 12px 40px rgba(0,0,0,.2);}
.ir-modal-close{position:absolute;top:10px;right:12px;border:none;background:none;
  font:400 26px/1 var(--font-sans);cursor:pointer;color:var(--grey);padding:4px 8px;}
.ir-modal-close:hover{color:var(--ink);}
.ir-modal-title{margin:0 28px 12px 0;font:800 17px/1.25 var(--font-sans);
  color:var(--ink);}
.ir-modal-sub{font:600 12px/1.3 var(--font-sans);
  color:var(--grey);margin:-6px 0 12px;}
.ir-method{font:400 11.5px/1.5 var(--font-sans);color:var(--text);
  background:#fff;border:1px solid var(--line);border-radius:10px;padding:10px 12px;}
.ir-method-row{display:flex;gap:8px;padding:3px 0;border-bottom:1px dashed var(--line);}
.ir-method-row:last-child{border-bottom:none;}
.ir-method-k{flex:0 0 84px;font-weight:700;color:var(--grey);text-transform:uppercase;
  letter-spacing:.03em;font-size:10px;padding-top:1px;}
.ir-method-v{flex:1;}
.ir-method-v code{background:var(--panel);border-radius:4px;padding:1px 4px;font-size:11px;}
.ir-method ul{margin:2px 0;padding-left:16px;}
/* table tools (search + csv) and chart tools */
.ir-tbl-tools{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:10px 0 4px;}
.ir-search{flex:0 1 260px;border:1px solid var(--line);border-radius:8px;
  padding:6px 10px;font:400 12px/1.2 var(--font-sans);color:var(--text);}
.ir-csv{background:#fff;color:var(--blue);border:1.5px solid var(--blue);border-radius:8px;
  padding:5px 11px;font:700 11px/1 var(--font-sans);cursor:pointer;}
.ir-csv:hover{background:var(--blue);color:#fff;}
.ir-chart-tools{display:flex;justify-content:flex-end;gap:8px;margin:4px 0 2px;}
/* creative previews — push cards vs Message Center (phone viewport) */
.ir-creative{flex:1 1 280px;max-width:340px;border:1px solid var(--line);
  border-radius:14px;padding:12px;background:#fff;text-align:center;box-sizing:border-box;}
.ir-creative-push img{max-width:100%;height:auto;border-radius:8px;}
/* MC templates render very tall (full scroll); clip to a phone-sized viewport */
.ir-creative-mc .ir-mc-viewport{width:100%;max-width:280px;margin:0 auto;
  height:420px;max-height:min(420px,55vh);overflow:hidden;
  border-radius:22px;border:2px solid var(--ink);
  box-shadow:0 4px 18px rgba(0,0,0,.12);background:#fff;}
.ir-creative-mc .ir-mc-viewport img{display:block;width:100%;height:100%;
  object-fit:cover;object-position:top center;border-radius:20px;}
.ir-creatives-grid{display:flex;flex-wrap:wrap;gap:16px;align-items:flex-start;}
/* ===== strategy / playbook components (slides 2-8 of the strategic deck) ===== */
/* hero KPI band (audience + usage headline numbers with prior-period deltas) */
.ir-hero{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));
  gap:16px;margin:16px 0;}
.ir-hero-card{background:#fff;border:1px solid var(--line);border-radius:16px;
  padding:18px 20px;position:relative;box-sizing:border-box;
  box-shadow:0 1px 2px rgba(3,8,105,.04);transition:box-shadow .15s,transform .15s;}
.ir-hero-head{display:flex;align-items:flex-start;justify-content:space-between;gap:8px;}
.ir-hero-tools,.ir-kpi-tools{display:flex;align-items:center;gap:8px;flex:0 0 auto;}
/* pictograms */
.ir-ico{display:inline-block;object-fit:contain;vertical-align:middle;}
/* bolder pictograms: larger + full opacity + a hairline stroke-thickening shadow so the
   thin line-art reads clearly on light card backgrounds */
.ir-hero-ico,.ir-kpi-ico{width:32px;height:32px;opacity:1;flex:0 0 auto;
  filter:drop-shadow(0 0 .5px var(--blue));}
.ir-prio-ico{width:38px;height:38px;display:block;margin-bottom:10px;opacity:1;
  filter:drop-shadow(0 0 .5px var(--blue));}
@media (hover:hover){
  .ir-hero-card:hover,.ir-kpi:hover,.ir-prio-card:hover{
    box-shadow:0 8px 24px rgba(3,8,105,.10);transform:translateY(-2px);}
}
.ir-hero-val{font:800 33px/1 var(--font-sans);color:var(--ink);}
.ir-hero-label{font:600 12.5px/1.35 var(--font-sans);color:var(--grey);margin-top:7px;}
.ir-hero-delta{display:inline-block;font:700 11.5px/1.3 var(--font-sans);margin-top:9px;
  padding:2px 9px;border-radius:999px;}
.ir-hero-delta.good{background:#e6f7f0;color:#0a7d57;}
.ir-hero-delta.bad{background:#fdeaec;color:#b21e33;}
.ir-hero-delta.flat{background:var(--line);color:var(--grey2);}
.ir-hero-sub{font:400 11px/1.4 var(--font-sans);color:var(--grey);margin-top:6px;}
/* KPI-card prior-period comparison (mirrors the hero delta pill; content -> prints too) */
.ir-kpi-delta{margin-top:9px;}
.ir-kpi-delta .ir-hero-delta{margin-top:0;}
/* muted 'no prior-period baseline' note for un-windowable metrics (snapshot/aggregate) */
.ir-delta-na{display:inline-block;margin-top:9px;font:600 10.5px/1.3 var(--font-sans);
  color:var(--grey);font-style:italic;}
/* strategy / maturity matrix */
.ir-strat{width:100%;border-collapse:collapse;margin:12px 0;font:400 13px/1.5 var(--font-sans);}
.ir-strat th{background:var(--ink);color:#fff;text-align:left;padding:9px 12px;font-size:12px;}
.ir-strat td{border-bottom:1px solid var(--line);padding:10px 12px;vertical-align:top;}
.ir-strat tr:nth-child(even) td{background:var(--panel);}
.ir-strat .ir-strat-fig{font-weight:800;color:var(--ink);white-space:nowrap;}
.ir-matwrap{display:flex;align-items:center;gap:8px;min-width:150px;}
.ir-matbar{position:relative;height:10px;flex:1;border-radius:999px;background:var(--line);overflow:hidden;min-width:70px;}
.ir-matbar>span{position:absolute;left:0;top:0;bottom:0;border-radius:999px;
  background:linear-gradient(90deg,var(--indigo),var(--accent));}
.ir-mat-pct{font:700 12px/1 var(--font-sans);color:var(--ink);flex:0 0 auto;}
/* pillar coverage columns (already-done vs recommended levers) */
.ir-pillars{display:flex;flex-wrap:wrap;gap:14px;margin:12px 0;}
.ir-pillar{flex:1 1 210px;min-width:190px;background:var(--panel);border:1px solid var(--line);
  border-radius:14px;padding:14px 16px;box-sizing:border-box;}
.ir-pillar h4{margin:0 0 3px;font:800 13.5px/1.25 var(--font-sans);color:var(--ink);}
.ir-pillar-meta{font:700 10.5px/1.3 var(--font-sans);color:var(--grey);text-transform:uppercase;
  letter-spacing:.03em;margin-bottom:8px;}
.ir-lev{display:block;font:500 12px/1.55 var(--font-sans);margin:2px 0;}
.ir-lev.done::before{content:"\\2713 ";color:var(--mint);font-weight:800;}
.ir-lev.todo::before{content:"+ ";color:var(--accent);font-weight:800;}
.ir-lev.todo{color:var(--grey);}
.ir-lev-none{font:italic 400 11.5px/1.4 var(--font-sans);color:var(--grey);}
/* automation mix (one-shot vs automated, now vs target) */
.ir-mix{margin:12px 0;}
.ir-mix-row{display:flex;align-items:center;gap:10px;margin:8px 0;}
.ir-mix-name{flex:0 0 92px;font:700 12px/1.2 var(--font-sans);color:var(--grey);}
.ir-mix-bar{flex:1;display:flex;height:28px;border-radius:8px;overflow:hidden;border:1px solid var(--line);}
.ir-mix-seg{display:flex;align-items:center;justify-content:center;font:700 11px/1 var(--font-sans);
  color:#fff;white-space:nowrap;min-width:0;}
.ir-mix-auto{background:var(--mint);}
.ir-mix-one{background:var(--indigo);}
.ir-mix-legend{font:600 11px/1.4 var(--font-sans);color:var(--grey);margin-top:6px;}
.ir-swatch{display:inline-block;width:10px;height:10px;border-radius:3px;margin:0 4px 0 12px;vertical-align:middle;}
.ir-swatch:first-child{margin-left:0;}
/* personalization depth ladder */
.ir-ladder{display:flex;flex-wrap:wrap;gap:14px;margin:12px 0;}
.ir-ladder-col{flex:1 1 240px;min-width:210px;background:var(--panel);border:1px solid var(--line);
  border-radius:14px;padding:14px 16px;box-sizing:border-box;}
.ir-ladder-lvl{font:800 10.5px/1.3 var(--font-sans);letter-spacing:.08em;text-transform:uppercase;color:var(--accent);}
.ir-ladder-col h4{margin:2px 0 8px;font:800 13.5px/1.25 var(--font-sans);color:var(--ink);}
/* strategic priority cards */
.ir-prio{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));
  gap:16px;margin:14px 0;}
.ir-prio-card{background:#fff;border:1px solid var(--line);
  border-left:4px solid var(--accent);border-radius:12px;padding:18px 20px;box-sizing:border-box;
  box-shadow:0 1px 2px rgba(3,8,105,.04);transition:box-shadow .15s,transform .15s;}
.ir-prio-num{font:800 12px/1 var(--font-sans);color:var(--accent);letter-spacing:.06em;text-transform:uppercase;}
.ir-prio-card h4{margin:4px 0 8px;font:800 15px/1.25 var(--font-sans);color:var(--ink);}
.ir-prio-card p{margin:5px 0;font:400 12.5px/1.5 var(--font-sans);color:var(--text);}
.ir-prio-card .lbl{font-weight:800;color:var(--grey);text-transform:uppercase;font-size:10px;letter-spacing:.04em;}
/* ================= SCREEN web-app shell ================= */
@media screen{
  /* the fixed sidebar sits outside flow; clip any stray child overflow at the
     root so the page never scrolls horizontally behind the menu */
  html{overflow-x:hidden;}
  body{background:#eef0f4;overflow-x:hidden;}
  .ir-main{min-width:0;max-width:100%;overflow-x:clip;}
  .page table.grid{max-width:100%;}
  .ir-side{position:fixed;top:0;left:0;bottom:0;width:260px;box-sizing:border-box;
    overflow-y:auto;background:var(--ink);color:#fff;display:flex;flex-direction:column;
    padding:18px 14px;z-index:999;box-shadow:2px 0 14px rgba(0,0,0,.14);}
  .ir-side-head{display:flex;align-items:center;gap:10px;margin-bottom:12px;}
  .ir-brand{color:var(--accent);font:800 16px/1 var(--font-sans);
    letter-spacing:.02em;}
  .ir-side .pdf-btn{display:block;width:100%;text-align:center;box-sizing:border-box;margin-bottom:12px;}
  .ir-toc{display:flex;flex-direction:column;gap:2px;overflow-y:auto;flex:1;}
  .ir-toc a{color:#c9c9d6;text-decoration:none;padding:7px 10px;border-radius:8px;
    font:600 12.5px/1.25 var(--font-sans);
    border-left:2px solid transparent;display:flex;align-items:center;
    transition:background .18s ease,color .18s ease,border-color .18s ease;}
  .ir-toc a:hover{background:rgba(255,255,255,.08);color:#fff;}
  .ir-toc a.active{background:rgba(5,109,255,.16);color:#fff;border-left-color:var(--accent);}
  .ir-toc a.ir-sub{padding-left:22px;font-size:11.5px;color:#a6a6b8;}
  /* whiten the line-art for the dark sidebar; a hairline white glow thickens the
     thin strokes so the pictograms read clearly at sidebar size */
  .ir-toc-ico{width:21px;height:21px;margin-right:10px;flex:0 0 auto;
    filter:brightness(0) invert(1) drop-shadow(0 0 .6px rgba(255,255,255,.95));opacity:.9;}
  .ir-toc a.active .ir-toc-ico,.ir-toc a:hover .ir-toc-ico{opacity:1;}
  .ir-toc-lbl{overflow:hidden;text-overflow:ellipsis;}
  /* discreet, sidebar-only section numbering (muted; body <h2>/<h3> untouched) */
  .ir-toc-num{flex:0 0 auto;margin-right:8px;font:700 10px/1 var(--font-mono);
    color:#6f7086;min-width:15px;text-align:right;opacity:.85;letter-spacing:-.02em;}
  .ir-toc a.active .ir-toc-num,.ir-toc a.ir-trail .ir-toc-num{color:var(--sky);opacity:1;}
  .ir-toc a.ir-toc-h3 .ir-toc-num{min-width:24px;font-size:9px;}
  /* thematic cluster "eyebrow" labels (small uppercase group headers) */
  .ir-toc-eyebrow{font:800 9.5px/1.2 var(--font-sans);letter-spacing:.11em;
    text-transform:uppercase;color:#6f7086;padding:13px 10px 4px;user-select:none;}
  .ir-toc-eyebrow:first-child{padding-top:2px;}
  /* expand-all / collapse-all tree control at the top of the menu */
  .ir-toc-tools{display:flex;gap:6px;margin:0 0 4px;padding:0 2px;}
  .ir-toc-tools button{flex:1;background:rgba(255,255,255,.06);color:#a6a6b8;
    border:1px solid rgba(255,255,255,.12);border-radius:7px;padding:5px 6px;
    font:700 10px/1 var(--font-sans);letter-spacing:.02em;cursor:pointer;
    display:flex;align-items:center;justify-content:center;gap:5px;
    transition:background .15s ease,color .15s ease,border-color .15s ease;}
  .ir-toc-tools button:hover{background:rgba(255,255,255,.14);color:#fff;border-color:rgba(255,255,255,.25);}
  .ir-toc-tools button:focus-visible{outline:none;box-shadow:0 0 0 2px rgba(5,109,255,.5);}
  .ir-toc-tools button::before{content:"";width:9px;height:9px;flex:0 0 auto;
    background:currentColor;-webkit-mask:center/contain no-repeat;mask:center/contain no-repeat;}
  .ir-toc-tools button[data-ir-tree="expand"]::before{
    -webkit-mask-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath d='M8 3v10M3 8h10' stroke='black' stroke-width='2' stroke-linecap='round'/%3E%3C/svg%3E");
    mask-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath d='M8 3v10M3 8h10' stroke='black' stroke-width='2' stroke-linecap='round'/%3E%3C/svg%3E");}
  .ir-toc-tools button[data-ir-tree="collapse"]::before{
    -webkit-mask-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath d='M3 8h10' stroke='black' stroke-width='2' stroke-linecap='round'/%3E%3C/svg%3E");
    mask-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath d='M3 8h10' stroke='black' stroke-width='2' stroke-linecap='round'/%3E%3C/svg%3E");}
  /* collapsible sub-section groups in the TOC (auto-built from <h3> under a section) */
  .ir-toc-grp{display:flex;flex-direction:column;}
  .ir-toc-row{display:flex;align-items:stretch;gap:2px;}
  .ir-toc-row>a{flex:1 1 auto;min-width:0;}
  .ir-toc-chev{flex:0 0 auto;background:none;border:none;color:#8f90a6;cursor:pointer;
    padding:0 9px;font-size:10px;line-height:1;display:flex;align-items:center;border-radius:8px;
    transition:transform .2s ease,color .15s ease,background .15s ease;}
  .ir-toc-chev::before{content:"\\25B8";display:inline-block;}
  .ir-toc-chev:hover{color:#fff;background:rgba(255,255,255,.08);}
  .ir-toc-chev:focus-visible{outline:none;box-shadow:0 0 0 2px rgba(5,109,255,.5);}
  .ir-toc-grp.ir-open .ir-toc-chev{transform:rotate(90deg);color:#fff;}
  /* parent kept as the "active trail" while one of its children is active */
  .ir-toc a.ir-has-sub.ir-trail{color:#fff;border-left-color:var(--accent);
    background:rgba(5,109,255,.08);}
  /* tree children: indented, with a vertical rail + connector tick (arborescence) */
  .ir-toc-subs{position:relative;display:flex;flex-direction:column;gap:1px;
    margin:2px 0 6px 21px;padding-left:11px;}
  .ir-toc-subs::before{content:"";position:absolute;left:0;top:1px;bottom:7px;
    width:1px;background:rgba(255,255,255,.18);}
  .ir-toc-subs[hidden]{display:none;}
  .ir-toc a.ir-toc-h3{position:relative;padding:5px 8px 5px 11px;font-size:11.5px;
    color:#a6a6b8;line-height:1.3;border-radius:6px;}
  .ir-toc a.ir-toc-h3::before{content:"";position:absolute;left:-11px;top:50%;
    width:8px;height:1px;background:rgba(255,255,255,.18);}
  .ir-toc a.ir-toc-h3:hover{color:#fff;}
  .ir-toc a.ir-toc-h3.active{color:#fff;background:rgba(5,109,255,.12);}
  .ir-toc a.ir-toc-h3.active::before{background:var(--accent);width:9px;height:2px;}
  /* reading progress bar (screen only) — spans the content column, not the sidebar */
  .ir-progress{position:fixed;top:0;left:260px;right:0;height:3px;z-index:1200;
    background:transparent;pointer-events:none;}
  .ir-progress-fill{height:100%;width:0;background:var(--teal);
    box-shadow:0 0 6px rgba(17,219,192,.6);transition:width .08s linear;}
  /* back-to-top floating button (screen only) */
  .ir-top{position:fixed;right:24px;bottom:24px;width:44px;height:44px;border-radius:50%;
    border:none;background:var(--accent);color:#fff;font:700 20px/1 var(--font-sans);
    cursor:pointer;box-shadow:0 6px 20px rgba(3,8,105,.28);z-index:1200;
    opacity:0;visibility:hidden;transform:translateY(10px);
    transition:opacity .2s ease,transform .2s ease,visibility .2s ease,background .15s ease;}
  .ir-top.ir-show{opacity:1;visibility:visible;transform:none;}
  .ir-top:hover{background:var(--navy);}
  .ir-top:focus-visible{outline:none;box-shadow:0 0 0 3px rgba(5,109,255,.45);}
  .ir-side-foot{display:flex;gap:6px;margin-top:12px;flex-wrap:wrap;}
  .ir-mini{background:rgba(255,255,255,.1);color:#fff;border:none;border-radius:6px;
    padding:6px 9px;font:600 11px/1 var(--font-sans);cursor:pointer;}
  .ir-mini:hover{background:rgba(255,255,255,.2);}
  .ir-main{margin-left:260px;padding:0 clamp(14px,1.8vw,36px);}
  /* fluid reading cards: fill the width left of the sidebar (soft ultra-wide cap) */
  .page{width:auto !important;min-height:0 !important;height:auto !important;
    max-width:min(2100px,100%) !important;margin:22px auto !important;
    padding:clamp(30px,2.4vw,56px) !important;
    overflow:visible !important;box-shadow:0 4px 22px rgba(0,0,0,.08) !important;
    border-radius:16px;scroll-margin-top:20px;}
  .page h3{scroll-margin-top:24px;}
  /* EVERY block spans the full card width — prose included. Width is decided once,
     by the card (fluid, soft-capped above), so a paragraph, a callout and a table all
     share one left and one right edge. Capping prose to a narrower reading measure
     was worse in practice: it put two competing column widths on the same page and
     the eye had to re-find the left edge at every table. `--ir-measure` remains the
     single override point for a report that wants a narrow column back. */
  :root{--ir-measure:100%;}
  .page>p,.page>ul,.page>ol,.page>dl,
  .page>.note,.page>.verdict,.page>blockquote{max-width:var(--ir-measure);}
  .ir-fullbleed,.page>.ir-fullbleed{max-width:none !important;}
  /* cover heroes keep a min height so an absolutely-placed cover footer doesn't overlap */
  .page.cover{min-height:600px !important;padding:0 !important;}
  .foot{display:none !important;}   /* PDF page footer / page-number hidden on screen */
  /* readability */
  .page p,.page li,.page td,.page th{font-size:14.5px;}
  .ir-chart-canvas{min-height:340px;}
  .ir-creative-mc .ir-mc-viewport{height:min(360px,52vh);max-height:min(360px,52vh);}
  @media (max-width:960px){
    .ir-side{position:static;width:auto;height:auto;flex-direction:row;flex-wrap:wrap;
      align-items:center;padding:10px 12px;box-shadow:0 2px 10px rgba(0,0,0,.14);}
    .ir-side .pdf-btn{width:auto;margin:0;}
    .ir-toc{flex-direction:row;flex-wrap:wrap;overflow:visible;}
    .ir-toc a{border-left:none;}
    .ir-side-foot{margin:0 0 0 auto;}
    .ir-main{margin-left:0;}
    .page{padding:26px 20px !important;}
    /* sidebar is a static top bar here — progress bar spans the full width */
    .ir-progress{left:0;}
  }
}
/* ================= PRINT: unchanged paginated PDF ================= */
@media print{
  .no-print{display:none !important;}
  .ir-side{display:none !important;}
  .ir-main{margin:0 !important;}
  .ir-nav{display:none !important;}
  .page{scroll-margin-top:0;}
  /* charts: the PDF always uses the deterministic PNG, never the canvas.
     Cap it at the height the builder asked for: the PNG is otherwise scaled to
     the full column width at its own aspect ratio, so a tall figure silently
     renders 3-4x the requested height and busts the page in the PDF only. */
  .ir-chart .ir-chart-static{display:block !important;
    max-height:var(--ir-chart-h,440px);width:auto;max-width:100%;margin:0 auto;}
  .ir-chart .ir-chart-canvas{display:none !important;}
  /* force every collapsible fully open in the PDF */
  details.ir-collapse>*{display:block !important;}
  details.ir-collapse>summary::before{content:"";margin:0;}
  /* KPI methodology: modal on screen, optional compact inline block in PDF */
  .ir-kpi-info{display:none !important;}
  #ir-kpi-modal{display:none !important;}
  .ir-kpi-method-print{display:block !important;}
  /* inline tooltips become plain text (their tip is hidden) */
  .ir-tip{border-bottom:none;cursor:auto;}
  .ir-tip .ir-tip-text{display:none !important;}
  /* MC viewport height for print (fits one PDF page alongside push cards) */
  .ir-creative-mc .ir-mc-viewport{height:380px;max-height:380px;}
}
"""

# JS: build the sidebar TOC from [data-toc] sections (with scroll-spy), sortable +
# searchable tables, per-chart & per-table CSV export, expand/collapse-all, and force
# every <details> open before printing (belt-and-braces with the print CSS above).
INTERACTIVE_JS = r"""
(function(){
  /* ---- sidebar table of contents (auto) ---- */
  function slugify(t){
    return String(t||'').toLowerCase().replace(/[^a-z0-9]+/g,'-')
      .replace(/^-+|-+$/g,'').slice(0,48);
  }
  function sectionSubheads(s){
    /* top-level <h3> subheadings inside a section -> collapsible TOC children */
    var out=[]; if(!s.querySelectorAll) return out;
    Array.prototype.forEach.call(s.querySelectorAll('h3'),function(h){
      if((h.textContent||'').trim()) out.push(h);
    });
    return out;
  }
  /* split a canonical label ("8-10. Conversion & events") into a muted number
     badge + clean label ("8-10" / "Conversion & events"). Sidebar-only: the body
     <h2>/<h3> keep their own text. Bilingual (EN/FR share the numeric prefix). */
  function splitNum(text){
    var m=/^\s*([0-9][0-9A-Za-z\u2013\-]*)[.)]\s+([\s\S]+)$/.exec(text||'');
    if(m) return {num:m[1], label:m[2]};
    return {num:'', label:String(text||'').trim()};
  }
  window.__irSplitNum=splitNum;
  function hostLang(el){
    var h=el&&el.closest?el.closest('.ir-lang'):null;
    return (h&&h.getAttribute('data-lang'))||document.documentElement.lang||'en';
  }
  function clusterLabel(cid,lang){
    var C=window.IR_CLUSTERS; if(!C||!cid||!C[cid]) return '';
    return C[cid][lang]||C[cid].en||'';
  }
  var accordionCollapse=true;   /* expand-all disables auto-collapse until collapse-all */
  function setAllGroups(open){
    var nav=document.getElementById('ir-nav'); if(!nav) return;
    nav.querySelectorAll('.ir-toc-grp').forEach(function(g){ if(g._setOpen) g._setOpen(open); });
    accordionCollapse=!open;    /* expanded -> stop auto-collapsing; collapsed -> resume */
  }
  function localizeTree(l){
    document.querySelectorAll('#ir-nav .ir-toc-tools button').forEach(function(b){
      var t=(l==='fr'?b.getAttribute('data-fr'):b.getAttribute('data-en'))||'';
      var lb=b.querySelector('.ir-tt-lbl'); if(lb) lb.textContent=t; b.setAttribute('aria-label',t);
    });
  }
  window.__irTreeLocalize=localizeTree;
  function buildTOC(){
    var nav=document.getElementById('ir-nav'); if(!nav) return;
    var i18nA=(window.IR_I18N_ALL||{}); var EN=i18nA.en||{}, FR=i18nA.fr||{};

    /* expand-all / collapse-all tree control at the very top of the menu */
    var tools=document.createElement('div'); tools.className='ir-toc-tools no-print';
    function toolBtn(kind,en,fr){
      var b=document.createElement('button'); b.type='button';
      var init=(window.IR_LANG==='fr'?fr:en);
      b.setAttribute('data-ir-tree',kind);
      b.setAttribute('data-en',en); b.setAttribute('data-fr',fr); b.setAttribute('aria-label',init);
      var lb=document.createElement('span'); lb.className='ir-tt-lbl'; lb.textContent=init; b.appendChild(lb);
      b.addEventListener('click',function(){ setAllGroups(kind==='expand'); });
      return b;
    }
    tools.appendChild(toolBtn('expand', EN.expand_all||'Expand all', FR.expand_all||'Tout déplier'));
    tools.appendChild(toolBtn('collapse', EN.collapse_all||'Collapse all', FR.collapse_all||'Tout replier'));
    nav.appendChild(tools);

    var secs=document.querySelectorAll('[data-toc]');
    var prevEyebrow='';   /* "lang|cluster" of the last emitted eyebrow */
    secs.forEach(function(s){
      if(!s.id) return;
      var isSub=s.hasAttribute('data-toc-sub');
      var lang=hostLang(s);

      /* thematic cluster eyebrow when the (language, cluster) block changes */
      var cid=s.getAttribute('data-toc-cluster')||'';
      var key=lang+'|'+cid;
      if(cid && key!==prevEyebrow){
        var lblTxt=clusterLabel(cid,lang);
        if(lblTxt){
          var eb=document.createElement('div'); eb.className='ir-toc-eyebrow no-print';
          eb.setAttribute('data-lang',lang); eb.textContent=lblTxt; nav.appendChild(eb);
        }
        prevEyebrow=key;
      }

      /* raw sidebar label for THIS language, split into number badge + label */
      var raw=(lang==='fr'&&s.getAttribute('data-toc-fr'))?s.getAttribute('data-toc-fr'):s.getAttribute('data-toc');
      var parts=splitNum(raw);

      var a=document.createElement('a');
      a.href='#'+s.id;
      if(isSub) a.className='ir-sub';
      if(parts.num){ var n=document.createElement('span'); n.className='ir-toc-num'; n.textContent=parts.num; a.appendChild(n); }
      var ic=s.querySelector?s.querySelector('.ir-h2-ico'):null;
      if(ic && !isSub){
        var im=ic.cloneNode(true); im.className='ir-toc-ico'; im.removeAttribute('style'); a.appendChild(im);
      }
      var lbl=document.createElement('span'); lbl.className='ir-toc-lbl';
      lbl.textContent=parts.label; a.appendChild(lbl);

      /* no <h3> subheadings -> plain link */
      var subs=isSub?[]:sectionSubheads(s);
      if(!subs.length){ nav.appendChild(a); return; }

      /* collapsible group: parent row (link + chevron toggle) + indented sub-links */
      a.classList.add('ir-has-sub');
      var grp=document.createElement('div'); grp.className='ir-toc-grp';
      var row=document.createElement('div'); row.className='ir-toc-row';
      var chev=document.createElement('button');
      chev.type='button'; chev.className='ir-toc-chev';
      chev.setAttribute('aria-expanded','false');
      chev.setAttribute('aria-label',(window.IR_I18N&&window.IR_I18N.toggle_subsections)||'Toggle subsections');
      row.appendChild(a); row.appendChild(chev);
      grp.appendChild(row);
      var wrap=document.createElement('div'); wrap.className='ir-toc-subs'; wrap.hidden=true;
      subs.forEach(function(h,i){
        if(!h.id) h.id=s.id+'-s'+(i+1)+(slugify(h.textContent)?'-'+slugify(h.textContent):'');
        var sa=document.createElement('a'); sa.href='#'+h.id; sa.className='ir-toc-h3';
        var subNum=parts.num?(parts.num+'.'+(i+1)):String(i+1);
        var sn=document.createElement('span'); sn.className='ir-toc-num'; sn.textContent=subNum; sa.appendChild(sn);
        var sl=document.createElement('span'); sl.className='ir-toc-lbl';
        sl.textContent=(h.textContent||'').trim(); sa.appendChild(sl);
        wrap.appendChild(sa);
      });
      grp.appendChild(wrap);
      function setOpen(open){
        wrap.hidden=!open; chev.setAttribute('aria-expanded',open?'true':'false');
        grp.classList.toggle('ir-open',open);
      }
      chev.addEventListener('click',function(e){ e.preventDefault(); setOpen(wrap.hidden); });
      grp._setOpen=setOpen;
      nav.appendChild(grp);
    });
  }
  /* ---- scroll-spy: highlight the section (and <h3> sub-section) in view, and
     keep the parent <h2> marked as the active trail while a child is active ---- */
  function scrollSpy(){
    var nav=document.getElementById('ir-nav'); if(!nav) return;
    var links={};
    nav.querySelectorAll('a').forEach(function(a){
      var href=a.getAttribute('href'); if(href&&href.charAt(0)==='#') links[href.slice(1)]=a;
    });
    var targets=[];
    document.querySelectorAll('[data-toc]').forEach(function(s){ if(s.id) targets.push(s); });
    /* also observe the <h3> anchors referenced by sub-links */
    Object.keys(links).forEach(function(id){
      var el=document.getElementById(id);
      if(el && el.tagName==='H3') targets.push(el);
    });
    if(!targets.length || !('IntersectionObserver' in window)) return;
    function activate(a){
      Object.keys(links).forEach(function(k){links[k].classList.remove('active','ir-trail');});
      a.classList.add('active');
      var grp=a.closest('.ir-toc-grp');
      /* active trail: when a child <h3> is active, mark its parent <h2> as the trail */
      if(a.classList.contains('ir-toc-h3') && grp){
        var head=grp.querySelector('a.ir-has-sub'); if(head) head.classList.add('ir-trail');
      }
      /* accordion feel: keep only the active section's group expanded (unless the
         reader hit "Expand all", which suspends auto-collapse) */
      if(accordionCollapse){
        nav.querySelectorAll('.ir-toc-grp').forEach(function(g){
          if(g!==grp && g._setOpen) g._setOpen(false);
        });
      }
      if(grp && grp._setOpen) grp._setOpen(true);
      if(a.scrollIntoView) a.scrollIntoView({block:'nearest'});
    }
    var obs=new IntersectionObserver(function(entries){
      entries.forEach(function(e){
        if(!e.isIntersecting) return;
        var a=links[e.target.id]; if(!a) return;
        activate(a);
      });
    },{rootMargin:'-35% 0px -55% 0px'});
    targets.forEach(function(t){ obs.observe(t); });
  }
  /* ---- reading progress bar (screen only; spans the content column) ---- */
  function progressBar(){
    var bar=document.createElement('div'); bar.className='ir-progress no-print';
    bar.setAttribute('aria-hidden','true');
    var fill=document.createElement('div'); fill.className='ir-progress-fill';
    bar.appendChild(fill); document.body.appendChild(bar);
    var ticking=false;
    function upd(){
      ticking=false;
      var d=document.documentElement;
      var max=(d.scrollHeight-d.clientHeight);
      var y=window.pageYOffset||d.scrollTop||0;
      var p=max>0?Math.min(1,Math.max(0,y/max)):0;
      fill.style.width=(p*100).toFixed(2)+'%';
    }
    function onScroll(){ if(!ticking){ ticking=true; window.requestAnimationFrame(upd); } }
    window.addEventListener('scroll',onScroll,{passive:true});
    window.addEventListener('resize',onScroll);
    upd();
  }
  /* ---- back-to-top button (screen only; appears after ~600px) ---- */
  function backToTop(){
    var b=document.createElement('button'); b.type='button'; b.className='ir-top no-print';
    b.setAttribute('aria-label',(window.IR_I18N&&window.IR_I18N.back_to_top)||'Back to top');
    b.innerHTML='<span aria-hidden="true">\u2191</span>';
    document.body.appendChild(b);
    b.addEventListener('click',function(){
      try{ window.scrollTo({top:0,behavior:'smooth'}); }catch(e){ window.scrollTo(0,0); }
    });
    var ticking=false;
    function upd(){ ticking=false;
      b.classList.toggle('ir-show',(window.pageYOffset||document.documentElement.scrollTop||0)>600); }
    function onScroll(){ if(!ticking){ ticking=true; window.requestAnimationFrame(upd); } }
    window.addEventListener('scroll',onScroll,{passive:true});
    upd();
  }
  /* ---- sortable tables ---- */
  function sortable(){
    document.querySelectorAll('table.ir-sortable').forEach(function(t){
      t.querySelectorAll('th[data-sortable]').forEach(function(th,ci){
        th.addEventListener('click',function(){
          var body=t.tBodies[0]; if(!body) return;
          var rows=Array.prototype.slice.call(body.rows);
          var asc=!th.classList.contains('ir-asc');
          t.querySelectorAll('th').forEach(function(h){h.classList.remove('ir-asc','ir-desc');});
          th.classList.add(asc?'ir-asc':'ir-desc');
          rows.sort(function(a,b){
            var x=(a.cells[ci]||{}).innerText||'', y=(b.cells[ci]||{}).innerText||'';
            var nx=parseFloat(x.replace(/[^0-9.\-]/g,'')), ny=parseFloat(y.replace(/[^0-9.\-]/g,''));
            if(!isNaN(nx)&&!isNaN(ny)) return asc?nx-ny:ny-nx;
            return asc?x.localeCompare(y):y.localeCompare(x);
          });
          rows.forEach(function(r){body.appendChild(r);});
        });
      });
    });
  }
  /* ---- CSV helpers ---- */
  function csvCell(v){
    v=(v==null?'':String(v));
    return /[",\n]/.test(v) ? '"'+v.replace(/"/g,'""')+'"' : v;
  }
  function toCSV(rows){
    return rows.map(function(r){return r.map(csvCell).join(',');}).join('\r\n');
  }
  function downloadCSV(name, text){
    var blob=new Blob(['\ufeff'+text],{type:'text/csv;charset=utf-8;'});
    var url=URL.createObjectURL(blob);
    var a=document.createElement('a');
    a.href=url; a.download=name;
    document.body.appendChild(a); a.click();
    setTimeout(function(){document.body.removeChild(a);URL.revokeObjectURL(url);},0);
  }
  function chartCSV(id){
    var pre=document.getElementById('csv-'+id);          // explicit override
    if(pre) return pre.textContent.trim();
    var el=document.getElementById('spec-'+id); if(!el) return '';
    var spec; try{spec=JSON.parse(el.textContent);}catch(e){return '';}
    var data=spec.data||{}; var labels=data.labels||[]; var ds=data.datasets||[];
    var head=['label'].concat(ds.map(function(d,i){return d.label||('series '+(i+1));}));
    var rows=[head];
    for(var i=0;i<labels.length;i++){
      var r=[labels[i]];
      ds.forEach(function(d){var a=d.data||[]; var v=a[i]; r.push(v==null?'':(typeof v==='object'?JSON.stringify(v):v));});
      rows.push(r);
    }
    return toCSV(rows);
  }
  function tableCSV(t){
    var rows=[];
    Array.prototype.forEach.call(t.querySelectorAll('tr'),function(tr){
      var cells=Array.prototype.map.call(tr.querySelectorAll('th,td'),function(c){return c.innerText.trim();});
      if(cells.length) rows.push(cells);
    });
    return toCSV(rows);
  }
  /* ---- table tools: filter box (.ir-searchable) + CSV button (.ir-exportable) ---- */
  function tableTools(){
    document.querySelectorAll('table.ir-searchable, table.ir-exportable').forEach(function(t){
      var tools=document.createElement('div'); tools.className='ir-tbl-tools no-print';
      if(t.classList.contains('ir-searchable')){
        var inp=document.createElement('input');
        inp.type='search'; inp.className='ir-search';
        inp.placeholder=t.getAttribute('data-search-placeholder')||(window.IR_I18N&&window.IR_I18N.filter_rows)||'Filter rows…';
        inp.addEventListener('input',function(){
          var q=inp.value.toLowerCase(); var body=t.tBodies[0]; if(!body) return;
          Array.prototype.forEach.call(body.rows,function(r){
            r.style.display = (!q || r.innerText.toLowerCase().indexOf(q)>=0) ? '' : 'none';
          });
        });
        tools.appendChild(inp);
      }
      if(t.classList.contains('ir-exportable')){
        var b=document.createElement('button');
        b.type='button'; b.className='ir-csv'; b.textContent=(window.IR_I18N&&window.IR_I18N.download_csv)||'Download CSV';
        b.addEventListener('click',function(){
          downloadCSV((t.getAttribute('data-csv-name')||'table')+'.csv', tableCSV(t));
        });
        tools.appendChild(b);
      }
      t.parentNode.insertBefore(tools,t);
    });
  }
  /* ---- per-chart CSV buttons (rendered by interactive_chart) ---- */
  function chartCSVButtons(){
    document.querySelectorAll('[data-csv-chart]').forEach(function(b){
      b.addEventListener('click',function(){
        var id=b.getAttribute('data-csv-chart');
        var csv=chartCSV(id);
        if(csv) downloadCSV(id+'.csv', csv);
      });
    });
  }
  /* ---- expand / collapse all <details> ---- */
  function expandControls(){
    document.querySelectorAll('[data-ir-expand]').forEach(function(b){
      b.addEventListener('click',function(){
        var open=b.getAttribute('data-ir-expand')==='all';
        document.querySelectorAll('details.ir-collapse').forEach(function(d){d.open=open;});
      });
    });
  }
  function openAllDetails(){
    document.querySelectorAll('details.ir-collapse').forEach(function(d){d.open=true;});
  }
  /* ---- KPI methodology modal (one shared dialog) ---- */
  function kpiModals(){
    var modal=document.getElementById('ir-kpi-modal'); if(!modal) return;
    var body=modal.querySelector('#ir-kpi-modal-body');
    var title=modal.querySelector('#ir-kpi-modal-title');
    var sub=modal.querySelector('#ir-kpi-modal-sub');
    var lastFocus=null;
    function open(btn){
      var tid=btn.getAttribute('data-ir-kpi-method');
      var tpl=document.getElementById(tid); if(!tpl || !body) return;
      lastFocus=btn;
      title.textContent=(window.IR_I18N&&window.IR_I18N.how_computed)||"How it's computed";
      var lbl=btn.getAttribute('data-ir-kpi-label');
      if(sub){sub.textContent=lbl||''; sub.style.display=lbl?'':'none';}
      body.innerHTML=tpl.innerHTML;
      modal.hidden=false; modal.setAttribute('aria-hidden','false');
      document.body.style.overflow='hidden';
      var closeBtn=modal.querySelector('.ir-modal-close');
      if(closeBtn) closeBtn.focus();
    }
    function close(){
      modal.hidden=true; modal.setAttribute('aria-hidden','true');
      if(body) body.innerHTML='';
      document.body.style.overflow='';
      if(lastFocus) lastFocus.focus();
    }
    document.querySelectorAll('.ir-kpi-info').forEach(function(b){
      b.addEventListener('click',function(){open(b);});
    });
    modal.querySelectorAll('[data-ir-modal-close]').forEach(function(el){
      el.addEventListener('click',close);
    });
    document.addEventListener('keydown',function(e){
      if(e.key==='Escape'&&!modal.hidden) close();
    });
  }
  window.addEventListener('beforeprint',openAllDetails);
  if(window.matchMedia){var m=window.matchMedia('print');
    if(m.addListener){m.addListener(function(e){if(e.matches)openAllDetails();});}}
  document.addEventListener('DOMContentLoaded',function(){
    buildTOC(); scrollSpy(); sortable(); tableTools(); chartCSVButtons(); expandControls();
    kpiModals(); progressBar(); backToTop();
  });
})();
"""

# One shared modal shell — injected once per report by interactive_head().
KPI_MODAL_SHELL = (
    '<div class="ir-modal no-print" id="ir-kpi-modal" hidden aria-hidden="true">'
    '<div class="ir-modal-backdrop" data-ir-modal-close></div>'
    '<div class="ir-modal-dialog" role="dialog" aria-modal="true" '
    'aria-labelledby="ir-kpi-modal-title">'
    '<button type="button" class="ir-modal-close" data-ir-modal-close '
    'aria-label="Close">&times;</button>'
    '<h4 class="ir-modal-title" id="ir-kpi-modal-title">How it\'s computed</h4>'
    '<p class="ir-modal-sub" id="ir-kpi-modal-sub"></p>'
    '<div class="ir-modal-body" id="ir-kpi-modal-body"></div>'
    '</div></div>'
)

_kpi_method_seq = 0


def _next_kpi_method_id() -> str:
    global _kpi_method_seq
    _kpi_method_seq += 1
    return f"ir-kpi-method-{_kpi_method_seq}"


# Chart.js progressive enhancement: mount each <canvas data-chart> from its inline
# JSON spec, and reveal the canvas (hiding the static PNG) on screen only. The PDF
# path never depends on the canvas — the print stylesheet keeps the PNG.
CHART_JS = r"""
(function(){
  function applyDefaults(){
    if(!window.Chart) return;
    Chart.defaults.font.family="'Instrument Sans',var(--font-sans)";
    Chart.defaults.color="#414651";
    Chart.defaults.plugins.legend.labels.usePointStyle=true;
    // rich tooltips without JS in the JSON spec: datasets may carry a plain-array
    // `_extra` (one entry per data point, string or array of strings) appended here.
    Chart.defaults.plugins.tooltip.callbacks.afterLabel=function(ctx){
      var ds=ctx.dataset||{}; var ex=ds._extra;
      if(ex && ex[ctx.dataIndex]!=null){var v=ex[ctx.dataIndex];return Array.isArray(v)?v:[v];}
      return undefined;
    };
  }
  function mountCharts(){
    if(typeof window.Chart==='undefined') return;   // lib missing -> keep PNG fallback
    applyDefaults();
    document.querySelectorAll('canvas.ir-chart-live[data-chart]').forEach(function(cv){
      var id=cv.getAttribute('data-chart');
      var el=document.getElementById('spec-'+id); if(!el) return;
      var spec; try{spec=JSON.parse(el.textContent);}catch(e){return;}
      var fig=cv.closest('.ir-chart');
      // reveal the canvas container BEFORE creating the chart so Chart.js measures a
      // real (non-zero) height; otherwise it renders squished. Roll back on failure.
      if(fig) fig.classList.add('ir-live');
      try{ new Chart(cv, spec); }
      catch(e){ if(fig) fig.classList.remove('ir-live'); }
    });
  }
  if(document.readyState==='loading')
    document.addEventListener('DOMContentLoaded',mountCharts);
  else mountCharts();
})();
"""


def chartjs_inline() -> str:
    """Return a <script> tag with the vendored Chart.js library inlined (once).

    Reads scripts/vendor/chart.umd.min.js so the report stays a single offline file.
    Returns "" (with a console warning) if the vendored file is missing.
    """
    try:
        with open(_CHARTJS_PATH, "r", encoding="utf-8") as f:
            lib = f.read()
    except OSError:
        return ("<script>console.warn('Chart.js not vendored at scripts/vendor/"
                "chart.umd.min.js; interactive charts fall back to static PNGs.');</script>")
    return f"<script>{lib}</script>"


# ---------------------------------------------------------------------------
# i18n — default multi-language layer (EN default, FR supported)
# ---------------------------------------------------------------------------
# Every report can be rendered in a chosen language by threading `lang=` through
# interactive_head(...) and the components. `interactive_head` injects a
# `window.IR_I18N` object so the JS-driven chrome (search box, CSV button, KPI
# modal title) localizes too. Add a language by extending _UI_STRINGS.
_UI_STRINGS = {
    "en": {
        "pdf_download": "Download PDF",
        "expand_all": "Expand all",
        "collapse_all": "Collapse all",
        "how_computed": "How it's computed",
        "close": "Close",
        "filter_rows": "Filter rows…",
        "download_csv": "Download CSV",
        "back_to_top": "Back to top",
        "toggle_subsections": "Toggle subsections",
        "m_formula": "Formula",
        "m_inputs": "Inputs",
        "m_source": "Source",
        "m_coverage": "Coverage",
        "m_confidence": "Confidence",
        "m_notes": "Notes",
        "conf_high": "High",
        "conf_medium": "Medium",
        "conf_low": "Low",
    },
    "fr": {
        "pdf_download": "Télécharger le PDF",
        "expand_all": "Tout déplier",
        "collapse_all": "Tout replier",
        "how_computed": "Méthode de calcul",
        "close": "Fermer",
        "filter_rows": "Filtrer les lignes…",
        "download_csv": "Télécharger le CSV",
        "back_to_top": "Haut de page",
        "toggle_subsections": "Afficher/masquer les sous-sections",
        "m_formula": "Formule",
        "m_inputs": "Entrées",
        "m_source": "Source",
        "m_coverage": "Couverture",
        "m_confidence": "Confiance",
        "m_notes": "Notes",
        "conf_high": "Élevée",
        "conf_medium": "Moyenne",
        "conf_low": "Faible",
    },
}

_LANG_ALIASES = {
    "en": "en", "eng": "en", "english": "en", "anglais": "en",
    "fr": "fr", "fra": "fr", "fre": "fr", "french": "fr", "francais": "fr",
    "français": "fr", "fr-fr": "fr", "fr_fr": "fr",
}


def resolve_lang(lang: Optional[str]) -> str:
    """Normalise a language hint to a supported code ('en' default, 'fr')."""
    if not lang:
        return "en"
    return _LANG_ALIASES.get(str(lang).strip().lower(), "en")


def ui_string(key: str, lang: str = "en") -> str:
    """Localised UI chrome string with English fallback."""
    lang = resolve_lang(lang)
    return _UI_STRINGS.get(lang, {}).get(key) or _UI_STRINGS["en"].get(key, key)


def _conf_label(confidence: str, lang: str = "en") -> str:
    """Localise a High/Medium/Low confidence label; pass through anything else."""
    key = {"high": "conf_high", "medium": "conf_medium", "med": "conf_medium",
           "low": "conf_low"}.get(str(confidence).strip().lower())
    return ui_string(key, lang) if key else str(confidence).title()


def fmt_int(n, lang: str = "en") -> str:
    """Integer with locale thousands separator (',' en / no-break space fr).

    U+00A0 rather than the typographically-nicer U+202F: several of the brand's
    web fonts render U+202F at zero width, which silently glues the groups back
    together ("1234567" instead of "1 234 567").
    """
    try:
        v = int(round(float(n)))
    except (TypeError, ValueError):
        return str(n)
    s = f"{v:,}"
    return s.replace(",", "\u00a0") if resolve_lang(lang) == "fr" else s


def fmt_pct(x, lang: str = "en", dgt: int = 1) -> str:
    """Percentage from a 0-1 fraction; '.' en / ', ' + NBSP before '%' fr.

    French typography puts a space before the percent sign; it must be non-breaking
    so a figure never wraps away from its unit. None -> 'n/a'.
    """
    if x is None:
        return "n/a"
    if resolve_lang(lang) == "fr":
        return f"{x*100:.{dgt}f}".replace(".", ",") + "\u00a0%"
    return f"{x*100:.{dgt}f}%"


def fmt_delta(x, lang: str = "en", dgt: int = 1) -> str:
    """Signed percentage delta from a 0-1 fraction; '.' en / ',' fr. None -> 'n/a'."""
    if x is None:
        return "n/a"
    if resolve_lang(lang) == "fr":
        return (f"{'+' if x >= 0 else ''}{x*100:.{dgt}f}".replace(".", ",") + "\u00a0%")
    return f"{'+' if x >= 0 else ''}{x*100:.{dgt}f}%"


def fmt_num(n, lang: str = "en", dgt: int = 1) -> str:
    """Decimal number, with locale decimal mark AND thousands separators.

    The grouping is not cosmetic. Without it this returned an unseparated run of
    digits at every magnitude — an eight-figure send total rendering as
    "12345678.0" — and three independent section authors hit that on the same
    report, because the name promises a number formatter and nothing about the
    signature warns that large values come back unreadable. Grouping is a no-op
    below 1,000, so every existing caller passing a rate, a ratio or a points
    difference is unaffected.

    Counts still want `fmt_int`: this keeps the decimal place a count does not have.
    """
    try:
        s = f"{float(n):,.{dgt}f}"
    except (TypeError, ValueError):
        return str(n)
    if resolve_lang(lang) != "fr":
        return s
    # fr swaps both marks, so route through a placeholder: replacing "," with the
    # group separator first would then have "." collide into the same character.
    return s.replace(",", "\0").replace(".", ",").replace("\0", "\u00a0")


def _kpi_modal_shell(lang: str = "en") -> str:
    """One shared KPI methodology modal, localised."""
    return (
        '<div class="ir-modal no-print" id="ir-kpi-modal" hidden aria-hidden="true">'
        '<div class="ir-modal-backdrop" data-ir-modal-close></div>'
        '<div class="ir-modal-dialog" role="dialog" aria-modal="true" '
        'aria-labelledby="ir-kpi-modal-title">'
        f'<button type="button" class="ir-modal-close" data-ir-modal-close '
        f'aria-label="{html.escape(ui_string("close", lang))}">&times;</button>'
        f'<h4 class="ir-modal-title" id="ir-kpi-modal-title">'
        f'{html.escape(ui_string("how_computed", lang))}</h4>'
        '<p class="ir-modal-sub" id="ir-kpi-modal-sub"></p>'
        '<div class="ir-modal-body" id="ir-kpi-modal-body"></div>'
        '</div></div>'
    )


def _i18n_js(lang: str) -> str:
    """A tiny window.IR_I18N config so the static JS chrome localises too."""
    cfg = {k: ui_string(k, lang) for k in ("filter_rows", "download_csv", "how_computed",
                                           "back_to_top", "toggle_subsections")}
    # bilingual chrome labels for JS controls that must switch on the FR/EN toggle
    # (e.g. the sidebar tree Expand-all/Collapse-all) — keeps the i18n source of truth
    # in _UI_STRINGS rather than hard-coding strings in the client JS.
    _bi_keys = ("expand_all", "collapse_all", "back_to_top", "toggle_subsections")
    allcfg = {L: {k: ui_string(k, L) for k in _bi_keys} for L in ("en", "fr")}
    # the report's primary language: JS-built chrome seeds its labels from it, so a
    # monolingual report is localised even though no FR/EN toggle script is emitted
    return (f"<script>window.IR_I18N={json.dumps(cfg, ensure_ascii=False)};"
            f"window.IR_LANG={json.dumps(lang)};"
            f"window.IR_I18N_ALL={json.dumps(allcfg, ensure_ascii=False)};</script>")


def interactive_head(pdf_filename: Optional[str] = None,
                     brand: str = "Airship",
                     pdf_label: Optional[str] = None,
                     include_charts: bool = True,
                     layout: str = "dashboard",
                     lang: str = "en"):
    """Return the <style>, nav/shell container and <script> to put in <head>/top of <body>.

    Use like:
        <head> ... {css_block} </head>
        <body> {nav_block} ...pages... {js_block} </body>

    layout="dashboard" (default) makes the screen a web-app: a fixed left sidebar
    (brand, Download-PDF, auto-built section nav with scroll-spy, Expand/Collapse-all)
    and the report body wrapped in a fluid `.ir-main` column. `nav_block` opens the
    sidebar + `.ir-main`; `js_block` closes `.ir-main` before the scripts — so the
    3-tuple API and existing call sites (nav at top of <body>, js at the end) keep
    working, the content simply gets wrapped. `@media print` hides the sidebar and the
    paginated `.page`/`@page` rules stand, so the PDF is byte-for-byte unchanged.

    layout="bar" keeps the legacy sticky top-bar nav (no main wrapper) for back-compat.

    When include_charts is True (default), js_block also inlines the vendored Chart.js
    library and the chart-mounting script, so interactive_chart(...) figures light up on
    screen while keeping their static PNG for print. Set it False for a report with no
    interactive charts (skips the ~200 KB library).
    """
    lang = resolve_lang(lang)
    if pdf_label is None:
        pdf_label = ui_string("pdf_download", lang)
    css_block = f"<style>{brand_fonts_css()}</style>\n<style>{INTERACTIVE_CSS}</style>"
    pdf_btn = pdf_download_button(pdf_filename, pdf_label) if pdf_filename else ""
    js_parts = [_i18n_js(lang), f"<script>{INTERACTIVE_JS}</script>"]
    if include_charts:
        js_parts.append(chartjs_inline())
        js_parts.append(f"<script>{CHART_JS}</script>")
    js_scripts = "\n".join(js_parts)
    modal_shell = _kpi_modal_shell(lang)

    # brand lockup: real white wordmark on the dark sidebar, text fallback if missing
    logo_html = brand_logo("white", height=22, alt=brand) if brand.lower() == "airship" else ""
    brand_lockup = logo_html or f'<span class="ir-brand">{html.escape(brand)}</span>'

    if layout == "bar":
        nav_block = (f'<nav class="ir-nav no-print" id="ir-nav">'
                     f'{brand_lockup}{pdf_btn}</nav>')
        return css_block, nav_block, f"{modal_shell}\n{js_scripts}"

    # dashboard (default): sidebar shell + fluid main column. The Expand-all /
    # Collapse-all tree control lives once at the TOP of the TOC (built in JS,
    # class .ir-toc-tools); the old duplicate at the sidebar foot is removed.
    nav_block = (
        f'<aside class="ir-side no-print" id="ir-side">'
        f'<div class="ir-side-head">{brand_lockup}</div>'
        f'{pdf_btn}'
        f'<nav class="ir-toc" id="ir-nav"></nav>'
        f'</aside>'
        f'<div class="ir-main" id="ir-main">'
    )
    js_block = f"</div>\n{modal_shell}\n{js_scripts}"   # close .ir-main, modal, scripts
    return css_block, nav_block, js_block


def interactive_chart(chart_id: str, png_data_uri: str, spec: Union[dict, str],
                      alt: str = "", height: int = 460,
                      csv: Optional[str] = None, csv_label: str = "CSV",
                      show_csv: bool = True) -> str:
    """Emit a progressively-enhanced chart figure.

    Renders a static <img> (the matplotlib PNG — the print/fallback artifact) plus a
    <canvas> that JS upgrades to an interactive Chart.js chart on screen (see CHART_JS),
    and (on screen only) a small toolbar with a "CSV" button that downloads the chart's
    source data.

    Args:
      chart_id: unique id (also used for the spec <script> id) — keep it slug-like.
      png_data_uri: the fallback image src (usually a base64 data: URI).
      spec: a Chart.js config (dict, or a pre-serialized JSON string). For proper
            sizing set options.responsive=true and options.maintainAspectRatio=false.
      alt: alt text for the static image.
      height: on-screen canvas height in px (the print PNG keeps its own size).
      csv: optional explicit CSV text. When omitted, the CSV button auto-derives rows
           from the embedded spec (labels + each dataset's data) — zero extra payload.
      csv_label: label for the CSV button.
      show_csv: set False to hide the CSV toolbar for this chart.
    """
    if isinstance(spec, str):
        spec_json = spec
    else:
        spec_json = json.dumps(spec, ensure_ascii=False)
    # never let the spec break out of the <script> block
    spec_json = spec_json.replace("</", "<\\/")
    cid = html.escape(chart_id, quote=True)
    toolbar = ""
    if show_csv:
        toolbar = (f'<div class="ir-chart-tools no-print">'
                   f'<button type="button" class="ir-csv" data-csv-chart="{cid}">'
                   f'{html.escape(csv_label)}</button></div>')
    csv_block = ""
    if csv is not None:
        csv_safe = csv.replace("</", "<\\/")
        csv_block = (f'<script type="text/csv" id="csv-{cid}">{csv_safe}</script>')
    return (
        f'<figure class="ir-chart" id="fig-{cid}" '
        f'style="--ir-chart-h:{int(height)}px">'
        f'{toolbar}'
        f'<img class="ir-chart-static" src="{html.escape(png_data_uri, quote=True)}" '
        f'alt="{html.escape(alt, quote=True)}">'
        f'<div class="ir-chart-canvas no-print" style="height:{int(height)}px">'
        f'<canvas class="ir-chart-live" data-chart="{cid}"></canvas></div>'
        f'<script type="application/json" class="ir-chart-spec" id="spec-{cid}">'
        f'{spec_json}</script>'
        f'{csv_block}'
        f'</figure>'
    )


# ---------------------------------------------------------------------------
# Small HTML component helpers
# ---------------------------------------------------------------------------

def tooltip(text: str, tip: str) -> str:
    return (f'<span class="ir-tip">{html.escape(text)}'
            f'<span class="ir-tip-text">{html.escape(tip)}</span></span>')


def collapsible(summary: str, body_html: str, open_: bool = False) -> str:
    op = " open" if open_ else ""
    return (f'<details class="ir-collapse"{op}><summary>{html.escape(summary)}</summary>'
            f'<div>{body_html}</div></details>')


def pdf_download_button(pdf_filename: str, label: str = "Download PDF") -> str:
    return (f'<a class="pdf-btn no-print" href="{html.escape(pdf_filename)}" '
            f'download>{html.escape(label)}</a>')


def creative_push_preview(img_src: str, caption: str, alt: str = "") -> str:
    """Push notification preview card (natural height, real logo + optional hero)."""
    return (
        f'<div class="creative ir-creative ir-creative-push">'
        f'<img src="{html.escape(img_src, quote=True)}" alt="{html.escape(alt, quote=True)}">'
        f'<div class="small" style="margin-top:8px">{caption}</div></div>'
    )


def creative_mc_preview(img_src: str, caption: str, alt: str = "",
                        viewport_height: int = 420) -> str:
    """Message Center / in-app full-screen template preview in a phone-sized viewport.

    MC renders from render_email.py are often 2000+ px tall (full scroll). This clips
    the preview to ~one phone screen (hero + CTA) via a fixed-height viewport with
    object-fit:cover / object-position:top — never show the full scroll in the report.
    """
    vh = int(viewport_height)
    return (
        f'<div class="creative ir-creative ir-creative-mc">'
        f'<div class="ir-mc-viewport" style="height:{vh}px;max-height:{vh}px">'
        f'<img src="{html.escape(img_src, quote=True)}" alt="{html.escape(alt, quote=True)}">'
        f'</div><div class="small" style="margin-top:8px">{caption}</div></div>'
    )


def verdict_pill(tier: str, label: str) -> str:
    """tier in {good, mid, low}."""
    cls = {"good": "pill-good", "mid": "pill-mid", "low": "pill-low"}.get(tier, "pill-mid")
    return f'<span class="pill {cls}">{html.escape(label)}</span>'


def reliability_pill(score: Optional[float], lang: str = "en") -> str:
    """A reliability pill (0-1) for an uncertain mapping (e.g. campaign purpose).

    High >=0.70 (green), Medium >=0.45 (amber), else Low (grey). Shows the numeric
    score so a broad, recall-first association is transparently flagged.
    """
    lang = resolve_lang(lang)
    if score is None:
        lbl = "n/a"
        return f'<span class="pill pill-low">{lbl}</span>'
    tier = "good" if score >= 0.70 else ("mid" if score >= 0.45 else "low")
    word = _conf_label("high" if tier == "good" else "medium" if tier == "mid" else "low", lang)
    pct = f"{score*100:.0f}%"
    return verdict_pill(tier, f"{word} {pct}")


_CONF_TIER = {"high": "good", "medium": "mid", "med": "mid", "low": "low"}


_INLINE_TAG = re.compile(r"</?(?:code|b|i|em|strong|sup|sub|br)\s*/?>", re.I)


def plain_text(s):
    """Reduce a display string to plain text, for a field the caller will escape.

    Several components escape their own text so a builder can pass client data
    safely. That makes them hostile to the report's own idiom, where prose carries
    `<code>` spans and `&amp;`: escaping markup a second time renders a literal
    "<code>" or "&amp;amp;" to the reader. Routing the text-taking fields through
    here first keeps both properties — markup-tolerant input, escaped output — so a
    builder never has to know which components escape and which don't.
    """
    if not isinstance(s, str):
        return s
    s = _INLINE_TAG.sub("", s)
    return (s.replace("&amp;", "&").replace("&nbsp;", " ")
             .replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'")
             .replace("&quot;", '"'))


def _etext(s) -> str:
    """`plain_text` then escape: the safe rendering of a prose field."""
    return html.escape(plain_text("" if s is None else str(s)))


def methodology(formula: str,
                inputs: Union[dict, list, str, None] = None,
                source: Union[str, list, None] = None,
                confidence: Optional[str] = None,
                sample: Optional[str] = None,
                notes: Optional[str] = None,
                lang: str = "en") -> str:
    """Return a methodology block explaining how a KPI is computed.

    Rows: Formula, Inputs (name -> value), Source endpoint(s), Coverage/sample,
    Confidence pill, and optional caveats/notes. `formula` may contain a <code> span;
    `inputs` accepts a dict/list of (name, value) pairs or a pre-built HTML string.
    Rendered plainly so it reads fine in the on-screen modal and inline in print.
    Row labels + the confidence pill localise via `lang`.
    """
    lang = resolve_lang(lang)
    rows = []

    def row(k, v):
        rows.append(f'<div class="ir-method-row"><span class="ir-method-k">{html.escape(k)}</span>'
                    f'<span class="ir-method-v">{v}</span></div>')

    row(ui_string("m_formula", lang), f"<code>{_etext(formula)}</code>")
    if inputs:
        if isinstance(inputs, dict):
            items = "".join(f"<li>{_etext(k)} = <code>{_etext(v)}</code></li>"
                            for k, v in inputs.items())
            row(ui_string("m_inputs", lang), f"<ul>{items}</ul>")
        elif isinstance(inputs, (list, tuple)):
            items = "".join(f"<li>{_etext(k)} = <code>{_etext(v)}</code></li>"
                            for k, v in inputs)
            row(ui_string("m_inputs", lang), f"<ul>{items}</ul>")
        else:
            row(ui_string("m_inputs", lang), str(inputs))
    if source:
        if isinstance(source, (list, tuple)):
            src = ", ".join(f"<code>{_etext(s)}</code>" for s in source)
        else:
            src = f"<code>{_etext(source)}</code>"
        row(ui_string("m_source", lang), src)
    if sample:
        row(ui_string("m_coverage", lang), _etext(sample))
    if confidence:
        tier = _CONF_TIER.get(str(confidence).strip().lower(), "mid")
        row(ui_string("m_confidence", lang), verdict_pill(tier, _conf_label(confidence, lang)))
    if notes:
        row(ui_string("m_notes", lang), notes)
    return f'<div class="ir-method">{"".join(rows)}</div>'


def kpi_card(value: str, label: str, *,
             formula: str,
             inputs: Union[dict, list, str, None] = None,
             source: Union[str, list, None] = None,
             sample: Optional[str] = None,
             confidence: Optional[str] = None,
             notes: Optional[str] = None,
             tag: str = "",
             small: bool = False,
             icon: Union[str, bool, None] = None,
             print_methodology: bool = False,
             delta: Optional[float] = None,
             delta_good: Optional[bool] = True,
             delta_label: Optional[str] = None,
             no_baseline: bool = False,
             no_baseline_label: Optional[str] = None,
             lang: str = "en") -> str:
    """A KPI number + label with a "how it's computed" methodology modal.

    On screen, a compact ⓘ button opens a shared modal (does not expand the KPI grid).
    Methodology content lives in a hidden <template> per card. By default the block is
    screen-only — the PDF keeps its own methodology appendix. Set print_methodology=True
    to also render the methodology inline under the card in the PDF (for KPIs with room).

    Prior-period comparison (recommended on every card): pass ``delta`` (a fraction vs
    the prior window) with ``delta_good`` (True=up is good, False=up is bad e.g. opt-outs,
    None=neutral direction). When a metric genuinely can't be windowed, pass
    ``no_baseline=True`` for a muted "no prior-period baseline" note instead of a broken
    or misleading 0. The comparison is content, so it also appears in the PDF.

    Args mirror methodology(): formula/inputs/source/sample/confidence/notes.
    `tag` is an optional small pill/label appended after the KPI label. `lang` localises
    the methodology block + the accessible button label.
    """
    lang = resolve_lang(lang)
    method_html = methodology(formula, inputs=inputs, source=source,
                              confidence=confidence, sample=sample, notes=notes, lang=lang)
    mid = _next_kpi_method_id()
    cls_val = "ir-kpi-val sm" if small else "ir-kpi-val"
    tag_html = f" {tag}" if tag else ""
    lbl_esc = html.escape(label)
    aria = html.escape(f'{ui_string("how_computed", lang)}: {label}')
    print_block = (f'<div class="ir-kpi-method-print">{method_html}</div>'
                   if print_methodology else "")
    ico = "" if icon is False else icon_img(icon, label=label,
                                            css_class="ir-ico ir-kpi-ico")
    cmp_html = kpi_comparison({"delta": delta, "delta_good": delta_good,
                               "delta_label": delta_label, "no_baseline": no_baseline,
                               "no_baseline_label": no_baseline_label}, lang)
    cmp_block = f'<div class="ir-kpi-delta">{cmp_html}</div>' if cmp_html else ""
    return (
        f'<div class="card ir-kpi">'
        f'<div class="ir-kpi-head">'
        f'<div class="{cls_val}">{value}</div>'
        f'<div class="ir-kpi-tools">{ico}'
        f'<button type="button" class="ir-kpi-info no-print" aria-label="{aria}" '
        f'data-ir-kpi-method="{mid}" data-ir-kpi-label="{lbl_esc}">'
        f'&#9432;</button>'
        f'</div>'
        f'</div>'
        f'<div class="ir-kpi-label">{label}{tag_html}</div>'
        f'{cmp_block}'
        f'<template id="{mid}">{method_html}</template>'
        f'{print_block}'
        f'</div>'
    )


# Below this many observations, a percentile position is an anecdote rather than a
# position, and the verdict has to say so. Three is deliberately low: the point is not to
# demand statistical power, it is to stop a decile grade resting on one campaign — which is
# what shipped, top-decile off a single push.
GAUGE_SAMPLE_FLOOR = 3

_SAMPLE_N_RE = re.compile(r"(?:^|[^\d.,])(\d[\d\s\u202f\u00a0.,]*)")


def _sample_size(s: str) -> Optional[int]:
    """First integer in a sample description — "n=412 pushes" -> 412, "30 jours" -> 30."""
    m = _SAMPLE_N_RE.search(s or "")
    if not m:
        return None
    try:
        return int(re.sub(r"[^\d]", "", m.group(1)))
    except ValueError:
        return None


def gauge(value: float, p10: float, p50: float, p90: float,
          unit: str = "", width: int = 340, verdict: str = "",
          higher_is_better: bool = True, lang: str = "en",
          sample: Optional[Union[str, int]] = None) -> str:
    """Horizontal benchmark gauge (inline SVG).

    Shows the [p10-p90] peer band, the p50 median tick, and the client value marker.
    `verdict` is an optional worded label rendered under the gauge (caller decides
    the wording/language). `lang` only drives the decimal mark. Returns an HTML string.

    `sample` states what the graded value rests on — "n=412 pushes", "30 jours", 1 — and
    is printed under the gauge. It is mandatory whenever the verdict claims a percentile
    position, because a position is a claim about the account and one observation cannot
    support one: a delivered review graded a direct open rate top-decile off a single
    push. Below `GAUGE_SAMPLE_FLOOR` observations the verdict must say the comparison is
    inconclusive rather than name a decile. The gate enforces both.
    """
    vals = [v for v in (value, p10, p50, p90) if v is not None]
    lo = min(vals); hi = max(vals)
    span = (hi - lo) or 1.0
    lo -= span * 0.12
    hi += span * 0.12
    span = hi - lo

    def x(v):
        return 8 + (v - lo) / span * (width - 16)

    h = 46
    y = 16
    band_x1, band_x2 = x(p10), x(p90)
    fmt = (lambda v: f"{fmt_num(v, lang, 1)}{unit}")
    svg = [f'<svg class="gauge" width="{width}" height="{h+22}" viewBox="0 0 {width} {h+22}">']
    svg.append(f'<rect x="8" y="{y}" width="{width-16}" height="8" rx="4" fill="#eee"/>')
    svg.append(f'<rect class="g-band" x="{band_x1:.1f}" y="{y}" '
               f'width="{max(2,band_x2-band_x1):.1f}" height="8" rx="4"/>')
    svg.append(f'<line class="g-p50" x1="{x(p50):.1f}" y1="{y-4}" x2="{x(p50):.1f}" y2="{y+12}"/>')
    svg.append(f'<circle class="g-val" cx="{x(value):.1f}" cy="{y+4}" r="7"/>')
    svg.append(f'<text class="g-lbl" x="8" y="{y+26}">p10 {fmt(p10)}</text>')
    # p50 sits on the bottom axis with p10/p90: keeping it above the bar made it
    # collide with the client-value label whenever the client is near the median.
    p50_x = min(max(x(p50), 62), width - 62)
    svg.append(f'<text class="g-lbl" x="{p50_x:.1f}" y="{y+26}" text-anchor="middle">p50 {fmt(p50)}</text>')
    svg.append(f'<text class="g-lbl" x="{width-8}" y="{y+26}" text-anchor="end">p90 {fmt(p90)}</text>')
    svg.append(f'<text x="{x(value):.1f}" y="{y-8}" text-anchor="middle" '
               f'fill="{BRAND["blue"]}" font-weight="700" font-size="11">{fmt(value)}</text>')
    svg.append('</svg>')
    out = "".join(svg)
    sample_attr = ""
    if sample is not None and str(sample).strip():
        s_txt = plain_text(str(sample)).strip()
        n = _sample_size(s_txt)
        out += (f'<div class="muted" style="margin-top:2px;font-size:10px">'
                f'{"échantillon" if lang == "fr" else "sample"}&nbsp;: {html.escape(s_txt)}'
                f'</div>')
        sample_attr = f' data-g-sample="{html.escape(s_txt, quote=True)}"'
        if n is not None:
            sample_attr += f' data-g-n="{n}"'
    if verdict:
        out += f'<div style="margin-top:2px">{verdict}</div>'
    # The band and the value are carried as data attributes so the delivery gate can
    # check the worded verdict against the position it claims. A gauge is the one place
    # a section states "below the bottom decile" next to the numbers that refute it, and
    # nothing else in the report can catch that. `data-g-sample` extends the same idea to
    # the other way a verdict goes wrong: right about the position, wrong to claim one.
    hib = 1 if higher_is_better else 0
    return (f'<div class="gauge-wrap" data-g-value="{value}" data-g-p10="{p10}" '
            f'data-g-p50="{p50}" data-g-p90="{p90}" data-g-hib="{hib}"'
            f'{sample_attr}>{out}</div>')


def benchmark_source_note(bm, lang: str = "en") -> str:
    """The source line that must sit under every external benchmark table.

    Takes `audit.json`'s `benchmarks` block and prints source, vertical and basis
    (percentiles, published quarter, region) as one muted line.

    Why this is a component and not a sentence each section writes. Four delivered
    reviews cited three different benchmark vintages — one Q2 Travel, one Q1
    Finance & Insurance, two citing nothing at all — and a reader could not tell
    whether two accounts had been measured against the same ruler. The vintage lives
    in `benchmarks.json` meta and flows into the audit, so the only way it can drift
    is a section retyping it. This renders it from the data instead, and the gate
    looks for the marker below.
    """
    src = plain_text(str(bm.get("source") or "")).strip()
    basis = plain_text(str(bm.get("basis") or "")).strip()
    vset = plain_text(str(bm.get("set") or bm.get("vertical") or "")).strip()
    if not src:
        return ""
    fr = lang == "fr"
    bits = [f"<b>Source&nbsp;:</b> {src}" if fr else f"<b>Source:</b> {src}"]
    if vset:
        bits.append(f"échantillon {vset}" if fr else f"peer set {vset}")
    if basis:
        bits.append(basis)
    return (f'<p class="muted" data-ir-bench-source="1">'
            f'{" &middot; ".join(bits)}.</p>')


def unnamed_programme_note(ids, lang: str = "en") -> str:
    """Flag programmes shown by their raw identifier, and say who has to fix it.

    When `responses/list` gives a `group_id` and no composer name, the label falls back to
    the identifier, so a top-ranked automation reaches the report as
    `00000000-0000-0000-0000-000000000000`. Every number on that row is real and the row is
    unusable in front of a client — and nothing about it looks broken, which is why it ships.

    The composer name is not retrievable: `/api/schedules` is outside the `rpt` scope this
    review holds (SKILL.md), so there is no automated fix. What is left is to say so
    explicitly, on the page, addressed to whoever presents the deck.
    """
    ids = [str(i) for i in (ids or []) if i]
    if not ids:
        return ""
    fr = lang == "fr"
    shown = ", ".join(f"<code>{html.escape(i)}</code>" for i in ids[:3])
    more = (f" (+{len(ids) - 3})" if len(ids) > 3 else "")
    lab = ("\u00c0 compl\u00e9ter manuellement avant pr\u00e9sentation"
           if fr else "To complete manually before presenting")
    body = (f"{len(ids)} programme(s) apparaissent sous leur identifiant de groupe "
            f"({shown}{more}) faute de nom de campagne dans les donn\u00e9es de reporting. "
            f"Les chiffres de ces lignes sont exacts\u00a0; leur libell\u00e9 ne l'est pas. "
            f"Le nom du composer n'est pas r\u00e9cup\u00e9rable par l'API Reports "
            f"\u2014 retrouver chaque programme dans Flight Deck et remplacer "
            f"l'identifiant avant toute pr\u00e9sentation client."
            if fr else
            f"{len(ids)} programme(s) appear under their group identifier "
            f"({shown}{more}) because the reporting data carries no campaign name for them. "
            f"The figures on those rows are correct; their label is not. The composer name "
            f"is not retrievable through the Reports API \u2014 look each programme up in "
            f"Flight Deck and replace the identifier before presenting to the client.")
    return (f'<div class="note note-warn ir-unnamed-programme" '
            f'data-unnamed-programme="{len(ids)}">'
            f'<p><b>{lab}.</b> {body}</p></div>')


_VALUE_GRADE = {
    "revenue": ("Revenue attributable", "Revenu attribuable", "note-up"),
    "partial": ("Partly valued", "Partiellement valoris\u00e9", "note-warn"),
    "declared_not_flowing": ("Declared, not arriving", "D\u00e9clar\u00e9, non remont\u00e9",
                             "note-warn"),
    "counters": ("Counters only \u2014 no revenue attributable",
                 "Compteurs seuls \u2014 aucun revenu attribuable", "note-warn"),
    # Distinct from `counters`, which says the value field is populated but only ever
    # counts. `none` is the account that tracks no conversion at all: nothing in the
    # taxonomy names the outcome, so there is no event a Goal could even be built on.
    # It arrived as a KeyError that took a whole build down, because analyze.py graded an
    # account honestly and the block had no label for the honest answer.
    "none": ("None \u2014 no conversion tracked, no revenue attributable",
             "Aucune \u2014 aucune conversion suivie, aucun revenu attribuable", "note-warn"),
}


def value_measurability_block(vm: dict, lang: str = "en") -> str:
    """The graded verdict on whether conversions can be tied to an amount.

    Identical in every report by construction. This is the finding that decides what
    Airship can and cannot prove for an account, and left to prose it becomes a sentence
    somewhere in the events section that a reader skims past — "value behaves as a
    per-event counter" is true, unremarkable-looking, and means no message in the account
    can ever be tied to a euro.

    `declared_not_flowing` is deliberately its own grade: a plan that declares amounts and
    a feed that carries none is a wiring bug someone can fix this sprint, which is a very
    different conversation from an account that never declared any.
    """
    if not vm or not vm.get("grade"):
        return ""
    fr = lang == "fr"
    label_en, label_fr, kind = _VALUE_GRADE[vm["grade"]]
    head = (f"Mesurabilit\u00e9 de la valeur\u00a0: <b>{label_fr}</b>."
            if fr else f"Value measurability: <b>{label_en}</b>.")
    nconv = vm.get("conversion_events") or 0
    if vm["grade"] == "counters":
        body = (f"Aucun des {nconv} \u00e9v\u00e9nements de conversion suivis ne porte de "
                f"montant\u00a0: le champ <code>value</code> se comporte comme un compteur "
                f"(valeur \u2248 nombre). Les conversions sont donc compt\u00e9es et jamais "
                f"valoris\u00e9es, et aucun message ne peut \u00eatre rattach\u00e9 \u00e0 "
                f"un chiffre d'affaires."
                if fr else
                f"None of the {nconv} tracked conversion events carries an amount: the "
                f"<code>value</code> field behaves as a counter (value \u2248 count). "
                f"Conversions are therefore counted and never valued, and no message can be "
                f"tied to revenue.")
    elif vm["grade"] == "declared_not_flowing":
        body = (f"Le plan de taggage d\u00e9clare "
                f"{fmt_int(vm.get('declared_count') or 0, lang)} \u00e9v\u00e9nement(s) "
                f"porteur(s) de montant, mais aucun montant n'arrive dans le flux "
                f"d'\u00e9v\u00e9nements. L'instrumentation existe sur le papier\u00a0; "
                f"c'est le c\u00e2blage qui manque."
                if fr else
                f"The tagging plan declares "
                f"{fmt_int(vm.get('declared_count') or 0, lang)} amount-bearing event(s), "
                f"but no amount arrives in the event feed. The instrumentation exists on "
                f"paper; the wiring does not.")
    else:
        body = (f"{fmt_pct(vm.get('valued_share') or 0, lang)} du volume de conversion "
                f"porte un montant ({vm.get('valued_conversions') or 0} "
                f"\u00e9v\u00e9nement(s) sur {nconv})."
                if fr else
                f"{fmt_pct(vm.get('valued_share') or 0, lang)} of conversion volume carries "
                f"an amount ({vm.get('valued_conversions') or 0} of {nconv} events).")
    miss = vm.get("missing_amount") or []
    miss_html = ""
    if miss:
        lab = ("Conversions qui devraient porter un montant et n'en portent pas"
               if fr else "Conversions that should carry an amount and do not")
        miss_html = (f'<p>{lab}\u00a0: '
                     + ", ".join(f"<code>{html.escape(m)}</code>" for m in miss) + ".</p>")
    return (f'<div class="note {kind} ir-value-grade" '
            f'data-value-grade="{html.escape(vm["grade"], quote=True)}">'
            f'<p>{head} {body}</p>{miss_html}</div>')


def value_measurability_line(vm: dict, lang: str = "en") -> str:
    """The one-line version for the executive summary — or "" when there is revenue.

    Surfaced in the summary only when it changes what the reader should expect from the
    whole report: an account whose conversions are all counters cannot be given a revenue
    figure anywhere in it, and finding that out in \u00a710 is finding out too late.
    """
    if not vm or vm.get("revenue_attributable"):
        return ""
    fr = lang == "fr"
    if vm["grade"] == "declared_not_flowing":
        return ("Aucun montant n'arrive dans le flux d'\u00e9v\u00e9nements, bien que le "
                "plan de taggage en d\u00e9clare\u00a0: ce rapport compte les conversions "
                "sans pouvoir les valoriser." if fr else
                "No amount arrives in the event feed although the tagging plan declares "
                "some: this report counts conversions without being able to value them.")
    return (f"Aucun \u00e9v\u00e9nement suivi ne porte de montant\u00a0: ce rapport compte "
            f"les conversions et n'en valorise aucune. Aucun chiffre d'affaires n'est "
            f"attribuable en l'\u00e9tat." if fr else
            f"No tracked event carries an amount: this report counts conversions and values "
            f"none of them. No revenue is attributable as things stand.")


_SCENE_GRADE = {
    "instrumented": ("Instrumented", "Instrument\u00e9e", "note-up"),
    "partial": ("Partly instrumented", "Partiellement instrument\u00e9e", "note-warn"),
    "outcomes": ("Outcomes readable, path not", "R\u00e9sultat lisible, parcours non",
                 "note-warn"),
    "blind": ("Blind", "Aveugle", "note-warn"),
}


def scene_instrumentation_block(si: dict, lang: str = "en") -> str:
    """The graded verdict on how much of a Scene is measurable, plus what to fix.

    A description of in-app activity ("69% dismissed, 12 distinct CTAs") does not compare
    across quarters or across accounts; a grade does, which is the whole reason this is a
    grade and not a paragraph. Renders "" when the account shows no in-app at all, so \u00a78b
    stays a legitimate N/A.

    The remediation text comes from `campaign_inventory.SCENE_REMEDIATION` \u2014 written once
    and identical in every report, because the fix does not vary by client and a section
    writer re-arguing it each time is how three reports end up recommending three things.
    """
    if not si or not si.get("volume"):
        return ""
    import campaign_inventory as _ci
    fr = lang == "fr"
    label_en, label_fr, kind = _SCENE_GRADE.get(si.get("grade") or "blind",
                                                _SCENE_GRADE["blind"])
    dims = si.get("dimensions") or {}
    names = {
        "outcomes_named": ("named button identifiers", "identifiants de boutons explicites"),
        "screen_transitions": ("screen-to-screen movement", "passage d'un \u00e9cran \u00e0 "
                                                            "l'autre"),
        "custom_events": ("the app's own events on the flow",
                          "\u00e9v\u00e9nements propres \u00e0 l'app sur le parcours"),
    }
    yes, no = "\u2713", "\u2014"
    gap = " &mdash; absent" if fr else " &mdash; missing"
    rows = "".join(
        f'<li>{yes if dims.get(k) else no} {names[k][1 if fr else 0]}'
        f'{"" if dims.get(k) else gap}</li>'
        for k in ("outcomes_named", "screen_transitions", "custom_events"))
    head = (f"Instrumentation des Scenes\u00a0: <b>{label_fr}</b>."
            if fr else f"Scene instrumentation: <b>{label_en}</b>.")
    vol = f"{si['volume']:,.0f}".replace(",", "\u202f") if fr else f"{si['volume']:,.0f}"
    ctx = (f"Sur {vol} interactions in-app mesur\u00e9es, "
           f"{fmt_pct(si.get('named_share') or 0, lang)} des appuis de bouton portent un "
           f"identifiant explicite."
           if fr else
           f"Across {vol} measured in-app interactions, "
           f"{fmt_pct(si.get('named_share') or 0, lang)} of button presses carry an explicit "
           f"identifier.")
    fix = "".join(f'<li>{_ci.SCENE_REMEDIATION[k][1 if fr else 0]}</li>'
                  for k in (si.get("remediation") or [])
                  if k in _ci.SCENE_REMEDIATION)
    fix_html = ""
    if fix:
        lab = "\u00c0 corriger" if fr else "To fix"
        fix_html = f'<p><b>{lab}.</b></p><ol>{fix}</ol>'
    return (f'<div class="note {kind} ir-scene-grade" '
            f'data-scene-grade="{html.escape(str(si.get("grade")), quote=True)}">'
            f'<p>{head} {ctx}</p><ul>{rows}</ul>{fix_html}</div>')


def coverage_banner(cov: dict, lang: str = "en") -> str:
    """The page-1 statement of what this review rests on, and what it cannot claim.

    Placed on page 1 deliberately. A limitation buried in a methodology appendix is read by
    nobody who then goes on to quote the report, and the reader most likely to over-read a
    figure is the one who saw only the cover and the summary.

    Two kinds of gap, kept visibly apart because they call for different responses: a stage
    that failed or timed out is an accident of this run and a re-run may fix it; the
    structural lines are permanent consequences of the reporting scope and no re-run will
    move them. Renders on a clean run too — stating "12 of 12 stages complete" is what makes
    the same banner on a degraded run believable.
    """
    if not cov:
        return ""
    fr = lang == "fr"
    i = 1 if fr else 0
    grade = cov.get("grade") or "full"
    tone = {"full": "ok", "partial": "warn", "degraded": "bad"}.get(grade, "warn")
    ok, tot = cov.get("stages_ok") or 0, cov.get("stages_total") or 0
    head = {
        "full": (f"Collecte compl\u00e8te\u00a0: {ok} \u00e9tapes sur {tot}."
                 if fr else f"Collection complete: {ok} of {tot} stages."),
        "partial": (f"Collecte partielle\u00a0: {ok} \u00e9tapes sur {tot} compl\u00e8tes."
                    if fr else f"Collection partial: {ok} of {tot} stages complete."),
        "degraded": (f"Collecte d\u00e9grad\u00e9e\u00a0: {ok} \u00e9tapes sur {tot}."
                     if fr else f"Collection degraded: {ok} of {tot} stages."),
    }[grade]

    inc = []
    for f in cov.get("failed") or []:
        cost = (f.get("cost") or (None, None))[i] or f.get("stage")
        why = html.escape(str(f.get("why") or "")[:120])
        inc.append((f"\u00c9chec de l'\u00e9tape <b>{html.escape(f['stage'])}</b>\u00a0: "
                    f"ce rapport ne porte pas {cost}." if fr else
                    f"Stage <b>{html.escape(f['stage'])}</b> failed: this report does not "
                    f"carry {cost}.") + (f" <span class=\"muted\">({why})</span>" if why else ""))
    for p in cov.get("partial") or []:
        cost = (p.get("cost") or (None, None))[i] or p.get("stage")
        why = html.escape(str(p.get("why") or ""))
        # "couverture partielle de X" rather than "X n'est couvert que partiellement":
        # the costs differ in gender and number, and a frame that agrees with its object
        # would have to inflect for each one.
        inc.append(f"\u00c9tape <b>{html.escape(p['stage'])}</b> interrompue "
                   f"({why})\u00a0: couverture partielle de {cost} \u2014 tout "
                   f"classement qui s'y adosse porte sur un \u00e9chantillon tronqu\u00e9."
                   if fr else
                   f"Stage <b>{html.escape(p['stage'])}</b> cut short ({why}): {cost} is "
                   f"only partly covered \u2014 any ranking drawn from it rests on a "
                   f"truncated sample.")

    struct = [s[("fr" if fr else "en")] for s in (cov.get("structural") or [])]
    parts = [f'<p><b>{head}</b></p>']
    if inc:
        lab = "Cons\u00e9quences pour ce rapport" if fr else "What that costs this report"
        parts.append(f'<p><b>{lab}.</b></p><ul>'
                     + "".join(f"<li>{x}</li>" for x in inc) + "</ul>")
    if struct:
        lab = ("Hors de port\u00e9e de toute revue de ce type" if fr
               else "Beyond the reach of any review of this kind")
        why = ("\u2014 le p\u00e9rim\u00e8tre de reporting ne les expose pas, une "
               "nouvelle collecte n'y changerait rien" if fr
               else "\u2014 the reporting scope does not expose them, and re-running the "
                    "collection would not change that")
        colon = "\u00a0:" if fr else ":"
        parts.append(f'<p><b>{lab}</b> {why}{colon}</p><ul>'
                     + "".join(f"<li>{x}</li>" for x in struct) + "</ul>")
    # `.note` and `.note-up` / `.note-warn` are the framework's own callout classes; a
    # hand-invented `.callout` would render unstyled and the gate's dead-class scan lets
    # single-word classes through, so the mistake would ship silently.
    kind = {"ok": "note-up", "warn": "note-warn", "bad": "note-warn"}[tone]
    return (f'<div class="note {kind} ir-coverage" data-cov-grade="{grade}" '
            f'data-cov-structural="{len(struct)}">' + "".join(parts) + "</div>")


_PROOF_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "proof_points.json")
_PROOF_CACHE = None


def load_proof_points(path: Optional[str] = None) -> list:
    """The sourced-outcome library, or [] when the file is missing or unreadable.

    Returns only `confirmed` entries that actually carry a source and a date. Failing
    open here would be the whole risk of the feature: a proof point is a claim about
    another client, and the only thing separating it from a fabricated statistic is that
    a person put it in this file with its provenance.
    """
    global _PROOF_CACHE
    if _PROOF_CACHE is None or path:
        try:
            with open(path or _PROOF_PATH, encoding="utf-8") as fh:
                pts = (json.load(fh) or {}).get("points") or []
        except (OSError, ValueError):
            pts = []
        pts = [p for p in pts
               if p.get("status") == "confirmed" and p.get("source") and p.get("date")]
        if path:
            return pts
        _PROOF_CACHE = pts
    return _PROOF_CACHE


def proof_point(lever: str, lang: str = "en", pillar: Optional[str] = None) -> str:
    """A sourced outcome for this lever — or "" when the library has none.

    "Lifecycle & Retention: 0%, not started" tells a client what they are not doing and
    nothing about what doing it produces. This is the other half: one figure from a real
    account, with the document it came from printed next to it.

    **The empty string is the normal case and must stay comfortable.** A section writer
    who cannot get a proof point out of this function is not licensed to write one in
    prose — the figures a model recalls about other clients are exactly the ones nobody
    can source afterwards. Add the entry to `proof_points.json` with its document, or
    ship the recommendation without a proof point.
    """
    pts = load_proof_points()
    hit = next((p for p in pts if lever and lever in (p.get("levers") or [])), None)
    if hit is None and pillar:
        hit = next((p for p in pts if pillar in (p.get("pillars") or [])), None)
    if not hit:
        return ""
    fr = lang == "fr"
    claim = hit.get("claim_fr" if fr else "claim_en") or ""
    if not claim:
        return ""
    who = hit.get("client") or hit.get("client_note_fr" if fr else "client_note_en") or ""
    label = "Ailleurs" if fr else "Elsewhere"
    src = f'{"Source" if fr else "Source"}{"&nbsp;:" if fr else ":"} {hit["source"]}'
    who_html = f" <span class=\"muted\">({html.escape(str(who))})</span>" if who else ""
    return (f'<p class="note ir-proof" data-proof-id="{html.escape(hit["id"], quote=True)}" '
            f'data-proof-source="{html.escape(str(hit["source"]), quote=True)}">'
            f'<b>{label}.</b> {claim}{who_html} '
            f'<span class="muted">{src}.</span></p>')


# The horizons an action can sit in. A fixed vocabulary rather than free text, so that two
# accounts' plans can be read side by side — "next quarter" in one report and "T+1" in
# another describe the same slot and compare as if they did not.
ACTION_HORIZONS = {
    "now": ("Now (< 1 month)", "Immédiat (< 1 mois)"),
    "quarter": ("This quarter", "Ce trimestre"),
    "next": ("Next quarter", "Trimestre suivant"),
    "later": ("Later (2+ quarters)", "Plus tard (2 trimestres +)"),
}


def action_plan_table(rows: Sequence[dict], lang: str = "en") -> str:
    """The recommendations section's plan: Action / Horizon / Expected impact / Evidence.

    §16 was mandatory as a section and free-form as a format, so it shipped as prose
    lists that a reader could not turn into a plan: no sequencing, no sizing, and no way
    to tell which recommendation rested on a measurement and which on judgement. The
    table makes all four explicit and comparable between accounts.

    Each row: ``action``, ``horizon`` (an ACTION_HORIZONS key or free text), ``impact``,
    ``evidence``.

    **A row that states an impact must cite where the impact comes from** — a sized gap
    from `opportunity.py`, or a figure from the account. This is enforced rather than
    advised: a plausible number with no source is the most quotable thing in a review and
    the least defensible, so a row that has one raises here instead of shipping. An action
    whose value genuinely cannot be sized is honest — leave `impact` empty and it renders
    as "not sized".
    """
    fr = lang == "fr"
    body = []
    for i, r in enumerate(rows or []):
        action = str(r.get("action") or "").strip()
        if not action:
            continue
        impact = str(r.get("impact") or "").strip()
        evidence = str(r.get("evidence") or "").strip()
        if impact and not evidence:
            raise ValueError(
                f"action_plan_table row {i} ({plain_text(action)[:40]!r}) states an "
                f"expected impact with no evidence. Cite the sized gap or the account "
                f"metric it comes from, or leave `impact` empty.")
        h = str(r.get("horizon") or "").strip()
        horizon = ACTION_HORIZONS[h][1 if fr else 0] if h in ACTION_HORIZONS else h
        unsized = "non chiffré" if fr else "not sized"
        impact_cell = impact or f'<span class="fd-na">{unsized}</span>'
        body.append(f"<tr><td>{action}</td><td>{horizon}</td>"
                    f"<td>{impact_cell}</td>"
                    f'<td class="small">{evidence or "&mdash;"}</td></tr>')
    if not body:
        return ""
    heads = (["Action", "Horizon", "Impact attendu", "Preuve"] if fr else
             ["Action", "Horizon", "Expected impact", "Evidence"])
    th = "".join(f"<th data-sortable>{h}</th>" for h in heads)
    return (f'<table class="grid ir-exportable ir-sortable" data-ir-action-plan="1">'
            f'<thead><tr>{th}</tr></thead><tbody>{"".join(body)}</tbody></table>')


def email_reconcile_note(rec, lang: str = "en") -> str:
    """The two email counters, their gap, and which base each rate stands on.

    Built from `channel_activity.email_reconcile()` fields rather than from its English
    `verdict` string, so the analysis layer stays language-neutral.

    Why a report that mentions email must carry this. `/api/reports/sends` and the email
    event feed disagree — around 11% on a real account — and a review that printed one in
    the executive summary and the other in the funnel published an impossibility: more
    email delivered than sent. The open rate stood on the second figure without saying so,
    which made the headline rate depend on whichever counter was wrong.
    """
    if not rec or not rec.get("present"):
        return ""
    fr = lang == "fr"
    rs, inj, dlv = rec.get("reports_sends"), rec.get("injected"), rec.get("delivered")
    gp = rec.get("gap_pct")
    if gp is None:
        body = ("Un seul compteur d'envois email est disponible : aucune réconciliation "
                "n'est possible. Chaque taux ci-dessous nomme la base sur laquelle il "
                "repose."
                if fr else
                "Only one email send counter is available, so no reconciliation is "
                "possible. Each rate below names the base it stands on.")
    else:
        head = (f"Deux compteurs mesurent le volume email et ils ne coïncident pas. "
                f"<code>/api/reports/sends</code> en compte "
                f"{fmt_int(rs, lang)} sur la fenêtre ; le flux d'événements email en "
                f"injecte {fmt_int(inj, lang)} et en délivre {fmt_int(dlv, lang)}, soit "
                f"{fmt_pct(abs(gp), lang, 1)} "
                f"{'de plus' if gp > 0 else 'de moins'}."
                if fr else
                f"Two counters measure email volume and they do not agree. "
                f"<code>/api/reports/sends</code> counts {fmt_int(rs, lang)} over the "
                f"window; the email event feed injects {fmt_int(inj, lang)} and delivers "
                f"{fmt_int(dlv, lang)}, {fmt_pct(abs(gp), lang, 1)} "
                f"{'more' if gp > 0 else 'less'}.")
        if rec.get("funnel_internally_consistent"):
            mid = (" Le funnel est cohérent avec lui-même — injectés moins rejetés "
                   "redonnent les délivrés — donc l'écart se situe entre les deux "
                   "sources et non à l'intérieur du funnel."
                   if fr else
                   " The funnel is consistent with itself — injected less bounced returns "
                   "delivered — so the gap sits between the two sources rather than "
                   "inside the funnel.")
        else:
            mid = (" Le funnel ne se referme pas non plus sur lui-même : tous les taux "
                   "email ci-dessous sont à considérer comme provisoires."
                   if fr else
                   " The funnel does not close on itself either, so every email rate "
                   "below should be read as provisional.")
        tail = (" Les KPI de volume utilisent <code>/api/reports/sends</code> ; le taux "
                "d'ouverture est celui des ouvertures uniques sur les <b>délivrés</b>. "
                "Les deux compteurs ne sont jamais présentés comme un seul chiffre."
                if fr else
                " Volume KPIs use <code>/api/reports/sends</code>; the open rate is unique "
                "opens over <b>delivered</b>. The two counters are never presented as one "
                "figure.")
        body = head + mid + tail
    label = "Réconciliation des compteurs email" if fr else "Email counter reconciliation"
    return (f'<div class="note" data-ir-email-reconcile="1"><b>{label}.</b> {body}</div>')


# ---------------------------------------------------------------------------
# Strategy / campaign-playbook components (consumes campaign_purpose.py output)
# These render the consultative "strategic deck" views: a visual audience/usage KPI
# intro, strategic-priority cards, a typology-maturity matrix, a levers-by-pillar
# coverage grid, the one-shot-vs-automated industrialization mix, and a
# personalization-depth ladder. All print-safe HTML/CSS/SVG (no canvas dependency).
# ---------------------------------------------------------------------------
def _delta_html(delta: Optional[float], good: bool = True,
                label: Optional[str] = None, cls_base: str = "ir-hero-delta") -> str:
    """Prior-period delta pill with a coloured up/down arrow.

    delta: fraction (e.g. -0.049 for -4.9%). good=True => an increase is positive.
    good=None renders the pill neutral (no good/bad colour) for metrics whose
    direction isn't inherently positive or negative.
    """
    up = "\u25B2"; down = "\u25BC"; flat = "\u25AC"
    if delta is None:
        # A caller that supplied an explicit label without a numeric delta still means to
        # state a comparison — "attributed count flat vs prior period" is a comparison.
        # Returning "" here silently dropped it, and since the delivery gate counts
        # comparison markers rather than reading intent, the tile failed the check with no
        # hint as to why. Render the label as a neutral pill instead.
        return (f'<span class="{cls_base} flat">{flat} {html.escape(label)}</span>'
                if label else "")
    if delta == 0:
        arrow, cls = flat, "flat"
    elif good is None:
        arrow, cls = (up if delta > 0 else down), "flat"
    elif delta > 0:
        arrow, cls = up, ("good" if good else "bad")
    else:
        arrow, cls = down, ("bad" if good else "good")
    txt = label if label is not None else f"{'+' if delta > 0 else ''}{delta*100:.1f}% vs prior period"
    return f'<span class="{cls_base} {cls}">{arrow} {html.escape(txt)}</span>'


def _no_baseline_note(lang: str = "en", label: Optional[str] = None) -> str:
    """Muted 'no prior-period baseline' caption for a KPI whose prior value can't be
    windowed (e.g. a lifetime device snapshot or an un-windowable event series).

    Used instead of a broken/empty delta or a misleading 0, so every KPI card still
    carries an explicit vs-prior-period comparison state.
    """
    txt = label or ("pas de référence période précédente" if resolve_lang(lang) == "fr"
                    else "no prior-period baseline")
    return f'<span class="ir-delta-na">{html.escape(txt)}</span>'


def kpi_comparison(item: dict, lang: str = "en") -> str:
    """Render the vs-prior-period comparison for a KPI item (hero tile or KPI card).

    Recognised item keys:
      delta        -> fraction change vs the prior period (e.g. -0.049)
      delta_good   -> True (up is good), False (up is bad, e.g. opt-outs), or None (neutral)
      delta_label  -> explicit caption overriding the auto "±x% vs prior period"
      no_baseline  -> True to render the muted "no prior-period baseline" note
      no_baseline_label -> optional custom no-baseline caption

    Returns "" only when the item declares no comparison at all (back-compat).
    """
    lang = resolve_lang(lang)
    if item.get("no_baseline"):
        return _no_baseline_note(lang, item.get("no_baseline_label"))
    if item.get("delta") is None and item.get("delta_label") is None:
        return ""
    vs_prior = "vs période précédente" if lang == "fr" else "vs prior period"
    dlab = item.get("delta_label")
    if dlab is None and item.get("delta") is not None:
        dlab = f"{fmt_delta(item['delta'], lang)} {vs_prior}"
    return _delta_html(item.get("delta"), item.get("delta_good", True), dlab)


def hero_kpi_band(items: Sequence[dict], lang: str = "en") -> str:
    """Visual headline-KPI band (audience or usage) with prior-period deltas.

    Each item: {value, label, delta?, delta_good?=True, delta_label?, sub?} plus
    optional methodology fields (formula/inputs/source/sample/confidence/notes) which,
    when present, add a screen-only info button opening the shared methodology modal.

    Prior-period comparison (recommended on every tile): pass ``delta`` (a fraction vs
    the prior window) with ``delta_good`` (True=up is good, False=up is bad e.g. opt-outs,
    None=neutral direction). When a metric genuinely can't be windowed (a lifetime device
    snapshot, an un-windowable event series), pass ``no_baseline=True`` to render a muted
    "no prior-period baseline" note instead of a broken/empty delta or a misleading 0.
    """
    lang = resolve_lang(lang)
    how = ui_string("how_computed", lang)
    cards = []
    for it in items:
        info = ""
        method_fields = any(it.get(k) for k in ("formula", "inputs", "source", "sample", "notes"))
        if method_fields:
            m = methodology(it.get("formula", ""), inputs=it.get("inputs"),
                            source=it.get("source"), confidence=it.get("confidence"),
                            sample=it.get("sample"), notes=it.get("notes"), lang=lang)
            mid = _next_kpi_method_id()
            lbl_esc = html.escape(it.get("label", ""))
            info = (f'<button type="button" class="ir-kpi-info no-print" '
                    f'aria-label="{how}: {lbl_esc}" data-ir-kpi-method="{mid}" '
                    f'data-ir-kpi-label="{lbl_esc}">&#9432;</button>'
                    f'<template id="{mid}">{m}</template>')
        delta = kpi_comparison(it, lang)
        sub = f'<div class="ir-hero-sub">{it["sub"]}</div>' if it.get("sub") else ""
        if it.get("icon") is False:
            ico = ""
        else:
            ico = icon_img(it.get("icon"), label=it.get("label"),
                           css_class="ir-ico ir-hero-ico")
        tools = f'<div class="ir-hero-tools">{ico}{info}</div>' if (ico or info) else ""
        cards.append(
            f'<div class="ir-hero-card">'
            f'<div class="ir-hero-head"><div class="ir-hero-val">{it.get("value","")}</div>{tools}</div>'
            f'<div class="ir-hero-label">{it.get("label","")}</div>'
            f'{delta}{sub}</div>')
    return f'<div class="ir-hero">{"".join(cards)}</div>'


def _mat_tier(pct: float) -> str:
    if pct >= 70:
        return "good"
    if pct >= 45:
        return "mid"
    return "low"


def strategy_matrix(rows: Sequence[dict], lang: str = "en") -> str:
    """Typology x business stake x key figure x maturity table (deck slide 5).

    Each row: {label, stake:{stake,key_figure}, coverage_pct, maturity:{label},
    key_figure? (override), fig? (a headline number cell)}.
    """
    heads = (("Typologie de campagne", "Enjeu business", "Chiffre clé", "Maturité actuelle")
             if lang == "fr" else
             ("Campaign typology", "Business stake", "Key figure", "Current maturity"))
    trs = []
    for r in rows:
        stake = r.get("stake") or {}
        stake_txt = _etext(r.get("stake_text") or stake.get("stake", ""))
        keyfig = _etext(r.get("key_figure") or stake.get("key_figure", ""))
        pct = r.get("coverage_pct", 0)
        tier = _mat_tier(pct)
        mat = r.get("maturity") or {}
        mat_label = mat.get("label_fr" if lang == "fr" else "label") or mat.get("label", "")
        bar = (f'<div class="ir-matwrap"><div class="ir-matbar">'
               f'<span style="width:{max(0,min(100,pct))}%"></span></div>'
               f'<span class="ir-mat-pct">{pct}%</span></div>')
        pill = verdict_pill(tier, mat_label) if mat_label else ""
        trs.append(
            f'<tr><td><b>{_etext(r.get("label"))}</b></td>'
            f'<td>{stake_txt}</td><td>{keyfig}</td>'
            f'<td>{bar}<div style="margin-top:4px">{pill}</div></td></tr>')
    return (
        '<table class="ir-strat"><thead><tr>'
        f'<th>{heads[0]}</th><th>{heads[1]}</th><th>{heads[2]}</th>'
        f'<th>{heads[3]}</th></tr></thead><tbody>'
        + "".join(trs) + '</tbody></table>')


def pillar_coverage(pillars: Sequence[dict], lang: str = "en") -> str:
    """Levers-by-pillar grid: what's already done (check) vs recommended (+) (slide 6).

    Each pillar: {label, coverage_pct?, maturity?, done:[str,...], recommended:[str,...]}.
    """
    covered_lbl = "% couverts" if lang == "fr" else "% covered"
    none_lbl = "Aucun détecté" if lang == "fr" else "None detected yet"
    cols = []
    for p in pillars:
        meta = []
        if p.get("coverage_pct") is not None:
            meta.append(f"{p['coverage_pct']}{covered_lbl}")
        if p.get("maturity"):
            meta.append(str(p["maturity"]))
        meta_sep = " \u00b7 "
        meta_html = (f'<div class="ir-pillar-meta">{_etext(meta_sep.join(meta))}</div>'
                     if meta else "")
        done = "".join(f'<span class="ir-lev done">{_etext(x)}</span>'
                       for x in (p.get("done") or []))
        if not done:
            done = f'<span class="ir-lev-none">{none_lbl}</span>'
        todo = "".join(f'<span class="ir-lev todo">{_etext(x)}</span>'
                       for x in (p.get("recommended") or []))
        cols.append(
            f'<div class="ir-pillar"><h4>{_etext(p.get("label"))}</h4>{meta_html}'
            f'{done}{todo}</div>')
    return f'<div class="ir-pillars">{"".join(cols)}</div>'


def _mix_bar(name: str, automated_rate: float, one_shot_rate: Optional[float] = None,
             lang: str = "en") -> str:
    a = max(0.0, min(1.0, automated_rate or 0.0))
    o = one_shot_rate if one_shot_rate is not None else (1.0 - a)
    o = max(0.0, min(1.0, o))
    tot = (a + o) or 1.0
    aw, ow = a / tot * 100, o / tot * 100
    auto_w = "Automatisé " if lang == "fr" else "Automated "
    one_w = "One-shot " if lang == "fr" else "One-shot "
    aseg = (f'<div class="ir-mix-seg ir-mix-auto" style="width:{aw:.0f}%">'
            f'{(auto_w+format(a*100,".0f")+"%") if aw >= 14 else ""}</div>')
    oseg = (f'<div class="ir-mix-seg ir-mix-one" style="width:{ow:.0f}%">'
            f'{(one_w+format(o*100,".0f")+"%") if ow >= 14 else ""}</div>')
    return (f'<div class="ir-mix-row"><span class="ir-mix-name">{html.escape(name)}</span>'
            f'<div class="ir-mix-bar">{aseg}{oseg}</div></div>')


def automation_mix(current: dict, target: Optional[dict] = None,
                   current_label: str = "Today", target_label: str = "Target",
                   lang: str = "en") -> str:
    """One-shot vs automated split, now vs target (deck slide 7).

    current/target: {automated_rate, one_shot_rate?} as fractions (0-1).
    """
    rows = [_mix_bar(current_label, current.get("automated_rate", 0.0),
                     current.get("one_shot_rate"), lang=lang)]
    if target:
        rows.append(_mix_bar(target_label, target.get("automated_rate", 0.0),
                             target.get("one_shot_rate"), lang=lang))
    if lang == "fr":
        legend = ('<div class="ir-mix-legend">'
                  '<span class="ir-swatch" style="background:var(--mint)"></span>Automatisé / scénarios déclenchés'
                  '<span class="ir-swatch" style="background:var(--indigo)"></span>One-shot / campagnes manuelles'
                  '</div>')
    else:
        legend = ('<div class="ir-mix-legend">'
                  '<span class="ir-swatch" style="background:var(--mint)"></span>Automated / triggered scenarios'
                  '<span class="ir-swatch" style="background:var(--indigo)"></span>One-shot / manual campaigns'
                  '</div>')
    return f'<div class="ir-mix">{"".join(rows)}{legend}</div>'


def personalization_ladder(levels: Sequence[dict], lang: str = "en") -> str:
    """3-level personalization-depth ladder with what's-available marked (slide 8).

    Each level: {level, title, items:[{label, done(bool)}]}. All copy comes from the
    caller, so `lang` is accepted for signature parity with the other section
    components (a builder passes lang= uniformly) and is currently unused.
    """
    del lang
    cols = []
    for lv in levels:
        items = "".join(
            f'<span class="ir-lev {"done" if it.get("done") else "todo"}">{_etext(it.get("label"))}</span>'
            for it in (lv.get("items") or []))
        cols.append(
            f'<div class="ir-ladder-col"><div class="ir-ladder-lvl">{_etext(lv.get("level"))}</div>'
            f'<h4>{_etext(lv.get("title"))}</h4>{items}</div>')
    return f'<div class="ir-ladder">{"".join(cols)}</div>'


def _cov_tier(pct: Optional[float]) -> str:
    if pct is None:
        return "low"
    return "good" if pct >= 70 else ("mid" if pct >= 45 else "low")


def data_foundation_block(foundation: Optional[dict], lang: str = "en") -> str:
    """Compact 'Data foundation & tracking coverage' block (OPTIONAL audit).

    Consumes `data_foundation.build_foundation(audit)`. Returns "" when no audit, so
    the caller can conditionally include the section (graceful degradation). Reuses
    kpi_card + verdict_pill; no fabricated benchmark bands.
    """
    if not foundation:
        return ""
    lang = resolve_lang(lang)
    fr = lang == "fr"
    counts = foundation.get("counts") or {}
    src = foundation.get("source_split") or {}
    cov = foundation.get("coverage") or {}

    def L(en, f):
        return f if fr else en

    cards = []
    cards.append(kpi_card(
        fmt_int(counts.get("customEvents", 0), lang), L("Custom events tracked", "Events custom trackés"),
        formula=L("Distinct client custom events in the tagging plan (ua_* excluded).",
                  "Events custom client distincts dans le plan de taggage (ua_* exclus)."),
        source="Tagging plan audit", lang=lang, small=True))
    cards.append(kpi_card(
        fmt_int(counts.get("attributes", 0), lang), L("Attributes", "Attributs"),
        formula=L("Distinct client attributes (profile traits) collected.",
                  "Attributs client distincts (traits de profil) collectés."),
        source="Tagging plan audit", lang=lang, small=True))
    cards.append(kpi_card(
        fmt_int(counts.get("tags", 0), lang) + " / " + fmt_int(counts.get("subscriptionLists", 0), lang),
        L("Tags / subscription lists", "Tags / listes d'abonnement"),
        formula=L("Segmentation surface: tags and subscription lists available for targeting.",
                  "Surface de segmentation : tags et listes d'abonnement disponibles pour le ciblage."),
        source="Tagging plan audit", lang=lang, small=True))
    # foundation stores percentages on a 0-100 scale; fmt_pct expects a 0-1 fraction.
    def _fr(v):
        return (v / 100.0) if isinstance(v, (int, float)) else None
    sdk_pct = _fr(src.get("sdk_pct")); api_pct = _fr(src.get("api_pct"))
    cards.append(kpi_card(
        (f"{fmt_pct(sdk_pct, lang, 0)} / {fmt_pct(api_pct, lang, 0)}" if sdk_pct is not None else "n/a"),
        L("SDK / API events", "Events SDK / API"),
        formula=L("Share of custom events sourced from the on-device SDK vs server-side API.",
                  "Part des events custom issus du SDK on-device vs API server-side."),
        notes=foundation.get("storage_verdict"), source="Tagging plan audit", lang=lang, small=True))

    conv_n = foundation.get("conversion_events", 0)
    vi_pct = _fr(foundation.get("value_instrumentation_pct"))
    units = ", ".join(foundation.get("monetary_units") or []) or L("none detected", "aucune détectée")
    cards.append(kpi_card(
        (fmt_pct(vi_pct, lang, 0) if vi_pct is not None else "n/a"),
        L("Value-instrumented conversions", "Conversions instrumentées en valeur"),
        formula=L("Conversion-intent events carrying an amount or value property, over all conversion events.",
                  "Events à intention de conversion portant un montant/propriété de valeur, sur l'ensemble des events de conversion."),
        inputs={L("conversion events", "events de conversion"): conv_n,
                L("value-instrumented", "instrumentés valeur"): foundation.get("value_instrumented", 0),
                L("inferred units", "unités inférées"): units},
        notes=L("Value != currency: currency is inferred from the amount distribution.",
                "Valeur != devise : la devise est inférée depuis la distribution des montants."),
        source="Tagging plan audit", lang=lang, small=True,
        confidence="Medium"))

    grid = f'<div class="ir-hero" style="margin:8px 0">{"".join(cards)}</div>'

    # Vertical coverage verdicts (fact-based; no fabricated benchmark band).
    ae100 = cov.get("attributes_pct"); ee100 = cov.get("events_pct")
    ae = _fr(ae100); ee = _fr(ee100)
    cov_line = (
        f'<p style="margin:6px 0"><strong>{L("Coverage vs vertical best practice", "Couverture vs bonnes pratiques verticale")}'
        f' ({html.escape(str(foundation.get("vertical") or ""))})</strong> &nbsp;'
        f'{L("Attributes", "Attributs")}: {verdict_pill(_cov_tier(ae100), (fmt_pct(ae, lang, 0) if ae is not None else "n/a"))} &nbsp;'
        f'{L("Events", "Events")}: {verdict_pill(_cov_tier(ee100), (fmt_pct(ee, lang, 0) if ee is not None else "n/a"))}</p>')

    signals = foundation.get("storage_signals") or []
    cadence = foundation.get("cadence_verdict")
    notes = []
    for s in signals:
        notes.append(f"<li>{html.escape(str(s))}</li>")
    if cadence:
        notes.append(f"<li>{html.escape(str(cadence))}</li>")
    notes_html = (f'<ul class="ir-foundation-notes" style="margin:6px 0 0;font-size:12px;color:#555">'
                  f'{"".join(notes)}</ul>' if notes else "")

    return grid + cov_line + notes_html


def priority_cards(priorities: Sequence[dict], lang: str = "en") -> str:
    """Strategic-priority cards (deck slide 2).

    Each priority: {num, title, ambition, opportunity, ambition_label?, opportunity_label?}.
    The two row labels default to the `lang` wording; override per card if needed.
    """
    fr = resolve_lang(lang) == "fr"
    cards = []
    for p in priorities:
        al = _etext(p.get("ambition_label") or ("Ambition" if not fr else "Ambition"))
        ol = _etext(p.get("opportunity_label") or ("Opportunité" if fr else "Opportunity"))
        amb = (f'<p><span class="lbl">{al}:</span> {_etext(p["ambition"])}</p>'
               if p.get("ambition") else "")
        opp = (f'<p><span class="lbl">{ol}:</span> {_etext(p["opportunity"])}</p>'
               if p.get("opportunity") else "")
        num = _etext(p.get("num", ""))
        eyebrow = _etext(p.get("eyebrow", "")) or num
        ico = "" if p.get("icon") is False else icon_img(
            p.get("icon"), label=p.get("eyebrow") or p.get("title"), css_class="ir-ico ir-prio-ico")
        cards.append(
            f'<div class="ir-prio-card">{ico}<div class="ir-prio-num">{eyebrow}</div>'
            f'<h4>{_etext(p.get("title"))}</h4>{amb}{opp}</div>')
    return f'<div class="ir-prio">{"".join(cards)}</div>'


# ---------------------------------------------------------------------------
# Custom-event analysis rendering (consumes event_analysis.py / event_attribution.py)
# ---------------------------------------------------------------------------
_CURRENCY_SYMBOL = {"EUR": "\u20ac", "USD": "$", "GBP": "\u00a3", "MAD": "MAD ",
                    "CHF": "CHF ", "CAD": "CA$", "SEK": "SEK ", "NOK": "NOK ",
                    "DKK": "DKK ", "PLN": "PLN ", "BRL": "R$", "AUD": "A$"}
_DASH = "\u2014"  # em dash (avoids backslashes inside f-string expressions, py<3.12)


def _sym(currency: Optional[str]) -> str:
    if not currency:
        return ""
    return _CURRENCY_SYMBOL.get(currency.upper(), currency.upper() + " ")


def _compact_amount(v: Optional[float], currency: Optional[str] = None) -> str:
    """Human-compact money/number: 12,345,678 -> "\u20ac12.3M"."""
    if v is None:
        return "\u2014"
    s = _sym(currency)
    av = abs(v)
    if av >= 1e9:
        return f"{s}{v / 1e9:.1f}B"
    if av >= 1e6:
        return f"{s}{v / 1e6:.1f}M"
    if av >= 1e3:
        return f"{s}{v / 1e3:.0f}k"
    return f"{s}{v:,.0f}"


def _pct(x: Optional[float]) -> str:
    return "\u2014" if x is None else f"{x * 100:.1f}%"


_CONFIDENCE_FR = {"High": "Élevée", "Medium": "Moyenne", "Low": "Faible"}


def confidence_pill(conf: Optional[str], lang: str = "en") -> str:
    """High/Medium/Low (or None) -> a coloured pill."""
    tier = {"High": "good", "Medium": "mid", "Low": "low"}.get(conf or "", "low")
    if resolve_lang(lang) == "fr":
        return verdict_pill(tier, _CONFIDENCE_FR.get(conf or "", "n/d"))
    return verdict_pill(tier, conf or "n/a")


# event_analysis category / kpi_kind vocabularies, for the FR rendering of the
# conversion-KPI table. Anything unmapped prints as-is.
_EVENT_CATEGORY_FR = {
    "Purchase": "Achat",
    "Add to cart": "Ajout au panier",
    "Reservation": "Réservation",
    "Activation": "Activation",
    "Loyalty": "Fidélité",
    "Consume content/product": "Consommation de contenu / produit",
}
_KPI_KIND_FR = {"business": "business", "usage": "usage", "loyalty": "fidélité"}


def event_kpi_table(kpis: list, currency: Optional[str] = None,
                    top: Optional[int] = None, lang: str = "en") -> str:
    """Conversion-KPI table: attribution split (+ attributed amount when monetary).

    `kpis` = event_analysis result["conversion_kpis"]. Screen-interactive (searchable,
    sortable, CSV-exportable); prints as a plain table.
    """
    fr = resolve_lang(lang) == "fr"
    rows = kpis[:top] if top else kpis
    if not rows:
        return ('<p class="small">Aucun événement KPI de conversion détecté sur la période.</p>'
                if fr else
                '<p class="small">No conversion KPI events detected in the period.</p>')
    show_amount = any(k.get("value_is_monetary") and k.get("amounts") for k in rows)
    head = (["Événement", "Catégorie", "Type", "Occurrences", "Direct", "Indirect",
             "Non attribué", "% attribué"] if fr else
            ["Event", "Category", "Type", "Count", "Direct", "Indirect",
             "Unattributed", "Attributed %"])
    if show_amount:
        head.append("Montant attribué" if fr else "Attributed amount")
    th = "".join(f'<th data-sortable>{html.escape(h)}</th>' for h in head)
    body = []
    for k in rows:
        a = k["attribution"]
        cat = str(k.get("category") or "")
        kind = str(k.get("kpi_kind") or "")
        if fr:
            cat = _EVENT_CATEGORY_FR.get(cat, cat)
            kind = _KPI_KIND_FR.get(kind, kind)
        cells = [
            f'<td class="brk">{html.escape(k["name"])}</td>',
            f'<td>{html.escape(cat)} {confidence_pill(k.get("confidence"), lang)}</td>',
            f'<td>{html.escape(kind)}</td>',
            f'<td>{fmt_int(k["total_count"], lang)}</td>',
            f'<td>{fmt_int(a["direct"]["count"], lang)}</td>',
            f'<td>{fmt_int(a["indirect"]["count"], lang)}</td>',
            f'<td>{fmt_int(a["unattributed"]["count"], lang)}</td>',
            f'<td>{fmt_pct(k.get("attr_count_rate"), lang)}</td>',
        ]
        if show_amount:
            amt = k.get("amounts") or {}
            cur = amt.get("currency") or currency
            cell = (_compact_amount(amt.get("attributed_amount"), cur)
                    if k.get("value_is_monetary") and amt else "\u2014")
            cells.append(f'<td>{cell}</td>')
        body.append("<tr>" + "".join(cells) + "</tr>")
    return (
        '<table class="grid ir-searchable ir-exportable ir-sortable">'
        f'<thead><tr>{th}</tr></thead><tbody>{"".join(body)}</tbody></table>'
    )


def attribution_series(kpi: dict):
    """(labels, values) of Direct/Indirect/Unattributed counts for a donut spec.

    Feed into airship_charts.spec_donut(labels, values, center="Attribution").
    """
    a = kpi["attribution"]
    return (["Direct", "Indirect", "Unattributed"],
            [int(a["direct"]["count"]), int(a["indirect"]["count"]),
             int(a["unattributed"]["count"])])


def value_amounts_block(analysis: dict) -> str:
    """Amount table for events whose `value` reads as monetary (else "").

    Shows attributed (direct+indirect) vs unattributed amount per event, the currency
    assumption + confidence, and the not-currency caveat.
    """
    monetary = [e for e in analysis.get("events", [])
                if e.get("value_monetary", {}).get("value_is_monetary") and e.get("amounts")]
    if not monetary:
        return ""
    cinfo = analysis.get("currency", {}) or {}
    cur = cinfo.get("currency")
    rows = []
    for e in sorted(monetary, key=lambda x: -(x.get("amounts", {}).get("total_amount") or 0)):
        amt = e["amounts"]
        vm = e["value_monetary"]
        rows.append(
            "<tr>"
            f'<td>{html.escape(e["name"])}</td>'
            f'<td>{e["total_count"]:,}</td>'
            f'<td>{_compact_amount(amt.get("attributed_amount"), cur)}</td>'
            f'<td>{_compact_amount(amt.get("unattributed_amount"), cur)}</td>'
            f'<td>{_compact_amount(amt.get("total_amount"), cur)}</td>'
            f'<td>{vm.get("value_per_event", 0):.2f}</td>'
            "</tr>"
        )
    cur_note = (f"Currency assumed <b>{html.escape(cur)}</b> "
                f"({html.escape(str(cinfo.get('basis') or ''))}; "
                f"{html.escape(str(cinfo.get('confidence') or 'Low'))} confidence)."
                if cur else "Currency unknown — amounts shown as raw value.")
    return (
        '<table class="grid ir-searchable ir-exportable ir-sortable">'
        '<thead><tr>'
        '<th data-sortable>Event</th><th data-sortable>Occurrences</th>'
        '<th data-sortable>Attributed amount</th><th data-sortable>Unattributed amount</th>'
        '<th data-sortable>Total amount</th><th data-sortable>Avg / event</th>'
        f'</tr></thead><tbody>{"".join(rows)}</tbody></table>'
        f'<p class="small">{cur_note} <em>`value` is a client-declared number, not '
        'guaranteed to be currency — treat amounts as an order of magnitude.</em></p>'
    )


def opportunities_tables(opps: dict, top: Optional[int] = None) -> dict:
    """Render the two opportunity tables. Returns {send_more, enrich_value} HTML."""
    def _send_more(items):
        items = items[:top] if top else items
        if not items:
            return '<p class="small">No catalog gap detected for this vertical.</p>'
        body = []
        for o in items:
            body.append(
                "<tr>"
                f'<td>{html.escape(o["custom_name"])}</td>'
                f'<td>{html.escape(str(o.get("category") or ""))}</td>'
                f'<td>{html.escape(str(o.get("kpi_kind") or ""))}</td>'
                f'<td>{"yes" if o.get("is_conversion") else _DASH}</td>'
                f'<td>{"yes" if o.get("carries_value") else _DASH}</td>'
                f'<td>{confidence_pill(o.get("confidence"))}</td>'
                "</tr>"
            )
        return (
            '<table class="grid ir-searchable ir-exportable ir-sortable"><thead><tr>'
            '<th data-sortable>Recommended event</th><th data-sortable>Category</th>'
            '<th data-sortable>Type</th><th data-sortable>Conversion</th>'
            '<th data-sortable>Carries value</th><th data-sortable>Confidence</th>'
            f'</tr></thead><tbody>{"".join(body)}</tbody></table>'
        )

    def _enrich(items):
        items = items[:top] if top else items
        if not items:
            return '<p class="small">All detected conversion events already carry a value.</p>'
        body = []
        for o in items:
            body.append(
                "<tr>"
                f'<td>{html.escape(o["name"])}</td>'
                f'<td>{html.escape(str(o.get("category") or ""))}</td>'
                f'<td>{html.escape(str(o.get("expected_value_property") or "amount"))}</td>'
                f'<td>{o.get("current_value_per_event", 0):.2f}</td>'
                f'<td>{confidence_pill(o.get("confidence"))}</td>'
                "</tr>"
            )
        return (
            '<table class="grid ir-searchable ir-exportable ir-sortable"><thead><tr>'
            '<th data-sortable>Event sent</th><th data-sortable>Category</th>'
            '<th data-sortable>Expected value property</th>'
            '<th data-sortable>Current avg value/event</th><th data-sortable>Confidence</th>'
            f'</tr></thead><tbody>{"".join(body)}</tbody></table>'
        )

    return {"send_more": _send_more(opps.get("send_more", [])),
            "enrich_value": _enrich(opps.get("enrich_value", []))}


def attributed_conversions_cell(attr: Optional[dict],
                                currency: Optional[str] = None) -> str:
    """Compact cell for a campaign table: attributed conversions (+ amount) or n/a."""
    if not attr or not attr.get("available"):
        reason = (attr or {}).get("reason", "not available")
        return f'<span class="fd-na" title="{html.escape(str(reason))}">n/a</span>'
    conv = attr.get("total_attributed_conversions", 0)
    amt = attr.get("total_attributed_amount") or 0
    cur = attr.get("currency") or currency
    out = f'{int(conv):,} conv'
    if amt:
        out += f' \u00b7 {_compact_amount(amt, cur)}'
    return out


# ---------------------------------------------------------------------------
# Data appendix — raw, exhaustive tables of the underlying data so a reader can
# audit every analysis at the end of the report. Consumes the tagging-plan audit
# (inventory.json + analysis.json via data_foundation.load) and a normalised
# campaign list. All screen-interactive (searchable/sortable/CSV) + print-safe.
# ---------------------------------------------------------------------------
# Must cover every intent `analyze_tagging_plan.INTENT_KEYWORDS` can emit, or the
# event appendix silently labels real categories "uncategorised". The legacy
# commerce/purchase/cart/search/onboarding keys are kept as aliases so a plan
# analysed by an older script still renders.
_INTENT_LABELS = {
    "conversion": ("Conversion", "Conversion"),
    "consideration": ("Consideration", "Considération"),
    "account": ("Identity & account", "Identité & compte"),
    "lifecycle": ("Lifecycle", "Cycle de vie"),
    "browse": ("Browse & content", "Navigation & contenu"),
    "engagement": ("Engagement", "Engagement"),
    "location": ("Location", "Localisation"),
    "loyalty": ("Loyalty", "Fidélité"),
    "commerce": ("Commerce", "Commerce"),
    "purchase": ("Purchase", "Achat"),
    "cart": ("Cart / basket", "Panier"),
    "search": ("Search", "Recherche"),
    "onboarding": ("Onboarding", "Onboarding"),
    "other": ("Other / uncategorised", "Autre / non catégorisé"),
}


def _intent_label(intent: Optional[str], lang: str = "en") -> str:
    en, fr = _INTENT_LABELS.get((intent or "other").lower(), _INTENT_LABELS["other"])
    return fr if resolve_lang(lang) == "fr" else en


def _attr_category(key: str, lang: str = "en") -> str:
    """Light heuristic category for a client attribute, from its key tokens."""
    k = str(key or "").lower()
    fr = resolve_lang(lang) == "fr"

    def pick(en, f):
        return f if fr else en
    if any(t in k for t in ("consent", "optin", "opt_in", "opt-in", "gdpr", "rgpd", "subscrib", "rewards")):
        return pick("Consent & subscription", "Consentement & abonnement")
    if any(t in k for t in ("email", "msisdn", "phone", "uuid", "_id", "identifier", "adobe", "external")):
        return pick("Identifier", "Identifiant")
    if any(t in k for t in ("city", "country", "region", "location", "geo", "venue", "stadium", "timezone")):
        return pick("Location", "Localisation")
    if any(t in k for t in ("team", "favorite", "favourite", "fav", "follow", "pref", "interest", "language", "locale")):
        return pick("Preference", "Préférence")
    if any(t in k for t in ("last_", "_date", "date_", "time", "_at", "timestamp", "activity", "session", "recency", "seen")):
        return pick("Behavioural / temporal", "Comportemental / temporel")
    if any(t in k for t in ("name", "gender", "age", "birth", "dob", "member", "tier", "status", "segment")):
        return pick("Profile", "Profil")
    return pick("Other", "Autre")


def _yn_pill(v, lang: str = "en") -> str:
    fr = resolve_lang(lang) == "fr"
    if v == "partial":
        return f'<span class="pill pill-mid">{"Partiel" if fr else "Partial"}</span>'
    if v:
        return f'<span class="pill pill-good">{"Oui" if fr else "Yes"}</span>'
    return f'<span class="pill pill-low">{"Non" if fr else "No"}</span>'


# ---------------------------------------------------------------------------
# Account-profile & adoption components (canonical §2). These are REQUIRED in the
# report and enforced by the delivery gate — every account can build them from the
# Reports API (channels/devices) + decoded creatives, so they must never be dropped.
# ---------------------------------------------------------------------------
def channel_adoption_matrix(rows: Sequence[dict], lang: str = "en",
                            heading: bool = True, note: str = "") -> str:
    """Channel-by-channel adoption matrix (canonical §2).

    Each row: {channel, status(bool|"partial"|str), volume(str), optin(str)}.
    ``status`` as a bool/"partial" renders a Yes/No/Partial pill; a string prints
    as-is. ``heading`` prepends the localised <h3> (so the gate can detect it and
    callers don't duplicate it). ``note`` is optional small print under the table.
    """
    fr = resolve_lang(lang) == "fr"
    h = (f'<h3>{"Matrice d’adoption des canaux" if fr else "Channel adoption matrix"}</h3>'
         if heading else "")
    heads = (["Canal", "Statut", "Volume (30j)", "Base opt-in (snapshot)"] if fr else
             ["Channel", "Status", "Volume (30d)", "Opt-in base (snapshot)"])
    th = "".join(f"<th>{html.escape(x)}</th>" for x in heads)
    body = []
    for r in rows:
        st = r.get("status")
        st_cell = (_yn_pill(st, lang) if isinstance(st, bool) or st == "partial"
                   else html.escape(str(st) if st is not None else ""))
        cico = icon_img(None, label=str(r.get("channel", "")), css_class="ir-ico ir-row-ico")
        body.append(
            "<tr>"
            f'<td>{cico}{r.get("channel","")}</td>'
            f'<td>{st_cell}</td>'
            f'<td>{r.get("volume","") or _DASH}</td>'
            f'<td>{r.get("optin","") or _DASH}</td>'
            "</tr>")
    note_html = f'<p class="small">{note}</p>' if note else ""
    return (f'<div class="ir-adoption-matrix">{h}'
            f'<table class="grid"><thead><tr>{th}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table>{note_html}</div>')


def feature_adoption_table(rows: Sequence[dict], lang: str = "en",
                           heading: bool = True, upsell: str = "") -> str:
    """Airship feature-adoption scorecard (canonical §2).

    Each row: {feature, adopted(bool|"partial"|str), evidence}. ``upsell`` renders an
    optional highlighted "upsell opportunities" note under the table.
    """
    fr = resolve_lang(lang) == "fr"
    h = (f'<h3>{"Tableau d’adoption des fonctionnalités" if fr else "Feature-adoption scorecard"}</h3>'
         if heading else "")
    heads = (["Fonctionnalité Airship", "Adoption", "Preuve"] if fr else
             ["Airship feature", "Adoption", "Evidence"])
    th = "".join(f"<th>{html.escape(x)}</th>" for x in heads)
    body = []
    for r in rows:
        ad = r.get("adopted")
        ad_cell = (_yn_pill(ad, lang) if isinstance(ad, bool) or ad == "partial"
                   else html.escape(str(ad) if ad is not None else ""))
        fico = icon_img(None, label=str(r.get("feature", "")), css_class="ir-ico ir-row-ico")
        body.append(
            "<tr>"
            f'<td>{fico}{r.get("feature","")}</td>'
            f'<td>{ad_cell}</td>'
            f'<td>{r.get("evidence","") or _DASH}</td>'
            "</tr>")
    up = (f'<div class="note note-up"><b>'
          f'{"Opportunités d’upsell" if fr else "Upsell opportunities"} :</b> {upsell}</div>'
          if upsell else "")
    return (f'<div class="ir-feature-table">{h}'
            f'<table class="grid"><thead><tr>{th}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table>{up}</div>')


# Pillar keys are machine identifiers shared with campaign_playbook.json. Printing
# one in a reader-facing column gives "engagement_data"; de-underscoring it only gets
# as far as "engagement data".
_PILLAR_LABELS = {
    "editorial": ("Editorial", "Éditorial"),
    "onboarding_adoption": ("Onboarding & adoption", "Onboarding & adoption"),
    "service": ("Service", "Service"),
    "lifecycle": ("Lifecycle", "Cycle de vie"),
    "engagement_data": ("Engagement & data", "Engagement & data"),
    "commercial": ("Commercial", "Commercial"),
}


def pillar_label(pillar, lang: str = "en") -> str:
    """Reader-facing name for a strategic-pillar key."""
    key = str(pillar or "")
    en, fr = _PILLAR_LABELS.get(key, (key.replace("_", " "), key.replace("_", " ")))
    return fr if resolve_lang(lang) == "fr" else en


_DC_KIND = {
    "activate_goal": ("Activate goal", "Activer un goal"),
    "add_value": ("Add value/currency", "Ajouter valeur/devise"),
    "enrich_event": ("Enrich event", "Enrichir l’événement"),
    "track_event": ("Track event", "Suivre l’événement"),
    "collect_attribute": ("Collect attribute", "Collecter l’attribut"),
}
_DC_KIND_WHATFOR = {
    "activate_goal": ("Lets Airship measure conversion & optimise automatically.",
                      "Permet à Airship de mesurer la conversion & d’optimiser automatiquement."),
    "add_value": ("Enables revenue attribution (not just opens).",
                  "Permet l’attribution du chiffre d’affaires (pas seulement des ouvertures)."),
    "enrich_event": ("Adds properties needed for finer targeting & personalisation.",
                     "Ajoute les propriétés nécessaires à un ciblage & une perso plus fins."),
    "track_event": ("Unlocks new triggered journeys for this behaviour.",
                    "Débloque de nouveaux parcours déclenchés pour ce comportement."),
    "collect_attribute": ("New profile trait for segmentation.",
                          "Nouveau trait de profil pour la segmentation."),
}


def data_collection_table(recos: Sequence[dict], lang: str = "en",
                          heading: bool = True, top: Optional[int] = None) -> str:
    """Readable data-collection gaps & quick-wins TABLE (canonical §2b).

    Consumes ``data_foundation.data_collection_recos()`` (dicts with kind/pillar/
    target/title/detail/confidence). Renders a legend + a sortable table — replacing
    the old illegible bullet list — so each gap explains WHAT to do, WHY it matters,
    the target identifier, the pillar it unlocks and the priority.
    Returns "" when there are no recos.
    """
    if not recos:
        return ""
    fr = resolve_lang(lang) == "fr"
    rows = list(recos)[:top] if top else list(recos)
    h = (f'<h3>{"Lacunes de collecte & quick wins" if fr else "Data-collection gaps & quick wins"}</h3>'
         if heading else "")
    legend = (
        '<p class="small">'
        + ("Chaque ligne = une action de collecte à fort levier, triée par priorité. "
           "« Type » indique la nature de l’action, « À quoi ça sert » ce qu’elle débloque."
           if fr else
           "Each row = a high-leverage collection action, sorted by priority. "
           "“Type” is the kind of action, “What it unlocks” explains the payoff.")
        + "</p>")
    heads = (["Priorité", "Type", "Cible", "Action recommandée", "À quoi ça sert", "Pilier"] if fr else
             ["Priority", "Type", "Target", "Recommended action", "What it unlocks", "Pillar"])
    th = "".join(f'<th data-sortable>{html.escape(x)}</th>' for x in heads)
    body = []
    for r in rows:
        kind = r.get("kind", "")
        kind_lbl = _DC_KIND.get(kind, (kind, kind))[1 if fr else 0]
        whatfor = _DC_KIND_WHATFOR.get(kind, ("", ""))[1 if fr else 0]
        detail = r.get("detail") or whatfor
        body.append(
            "<tr>"
            f'<td>{confidence_pill(r.get("confidence"), lang)}</td>'
            f'<td>{_etext(kind_lbl)}</td>'
            f'<td><code>{_etext(r.get("target") or "")}</code></td>'
            f'<td>{_etext(r.get("title") or "")}</td>'
            f'<td class="small">{_etext(detail)}</td>'
            f'<td>{_etext(pillar_label(r.get("pillar"), lang))}</td>'
            "</tr>")
    return (f'<div class="ir-datacollect">{h}{legend}'
            '<table class="grid ir-searchable ir-exportable ir-sortable" data-csv-name="data_collection_gaps">'
            f'<thead><tr>{th}</tr></thead><tbody>{"".join(body)}</tbody></table></div>')


_PROP_KIND_LABELS = {
    "enum": ("Enum", "Énumération"), "number": ("Number", "Nombre"),
    "amount": ("Amount", "Montant"), "date": ("Date", "Date"),
    "boolean": ("Boolean", "Booléen"), "identifier": ("Identifier", "Identifiant"),
    "json": ("JSON", "JSON"), "text": ("Text", "Texte"), "empty": ("Empty", "Vide"),
}


def _verbatim(s) -> str:
    """Escape a RAW CLIENT VALUE for display, decoding any encoding it arrived with.

    Sample values come from the client's own export (RTDS / tagging-plan JSON), and
    those exports routinely carry text that was already HTML-encoded upstream — a
    streaming programme title exports as ``Concert à l&#039;Olympia`` because
    the value was captured from a web page. Escaping that a second time shows the
    reader a literal ``&#039;`` and trips the gate's double-escape check, so unescape
    first, then escape exactly once.
    """
    return html.escape(html.unescape(str(s)))


def _clip(s: str, n: int = 38) -> str:
    """Shorten one sample value. Free-text properties (timestamps, search queries,
    serialised blobs) routinely run 60+ chars and would otherwise triple the row
    height and blow the page in the PDF. The point of a sample is the SHAPE.

    Decodes entities first so the budget counts characters the reader actually sees
    (``&#039;`` is one apostrophe, not six characters)."""
    s = " ".join(html.unescape(str(s)).split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "\u2026"


def _prop_kind_label(kind: Optional[str], lang: str = "en") -> str:
    en, fr = _PROP_KIND_LABELS.get(str(kind or ""), (str(kind or _DASH), str(kind or _DASH)))
    return fr if resolve_lang(lang) == "fr" else en


def _value_field_cell(e: dict, lang: str = "en") -> str:
    """Render the state of Airship's reserved per-event `value` field.

    Three states the reader must be able to tell apart, because they mean very
    different things for attribution: a real amount (revenue can be attributed), a
    0/1 counter (only volume), or NOT POPULATED (nothing to attribute at all). The
    old rendering collapsed the last two into an em dash, hiding the gap.
    """
    fr = resolve_lang(lang) == "fr"
    vf = e.get("valueField") or {}
    if vf.get("carriesAmount"):
        pill = '<span class="pill pill-good">' + ("\u20ac Montant" if fr else "\u20ac Amount") + "</span>"
        lo, hi, mean = vf.get("min"), vf.get("max"), vf.get("mean")
        if lo is not None and hi is not None:
            rng = f"{fmt_num(lo, lang, 2)}\u2013{fmt_num(hi, lang, 2)}"
            if mean is not None:
                rng += (" \u00b7 moy. " if fr else " \u00b7 avg ") + fmt_num(mean, lang, 2)
            pill += f'<br><span class="small">{html.escape(rng)}</span>'
        return pill
    if vf.get("isCounter"):
        return ('<span class="tag">' + ("Compteur" if fr else "Counter") + "</span>"
                '<br><span class="small">value = 0/1</span>')
    return ('<span class="pill pill-low">'
            + ("Non renseigné" if fr else "Not populated") + "</span>")


def _props_cell(e: dict, lang: str = "en", show: int = 6) -> str:
    """Property NAMES, not just a count — the count alone is unactionable."""
    fr = resolve_lang(lang) == "fr"
    props = e.get("properties") or []
    if not props:
        return '<span class="pill pill-low">' + ("Aucune" if fr else "None") + "</span>"
    names = [str(p.get("name") or "") for p in props]
    chips = " ".join(f"<code>{html.escape(n)}</code>" for n in names[:show])
    if len(names) > show:
        chips += f' <span class="small">+{len(names) - show}</span>'
    return chips


def audit_events_table(audit: Optional[dict], lang: str = "en", top: Optional[int] = None) -> str:
    """Exhaustive table of tracked custom events with their categorisation.

    Columns: Event · Source (SDK/API) · Category (intent) · Occurrences · `value` field
    (Amount range / Counter / Not populated) · Properties (names).
    Sourced from analysis['eventProperties'], which lists EVERY tracked event — including
    those carrying no property and no value, since that absence is the finding.
    Pair with `audit_event_properties_table()` for the per-property sample values.
    Returns "" when no audit (graceful degradation).
    """
    if not audit or not audit.get("available"):
        return ""
    an = audit.get("analysis") or {}
    evs = list(an.get("eventProperties") or [])
    if not evs:
        return ""
    evs.sort(key=lambda e: -(e.get("total") or 0))
    if top:
        evs = evs[:top]
    fr = resolve_lang(lang) == "fr"
    heads = (["Événement", "Source", "Catégorie", "Occurrences", "Champ <code>value</code>",
              "Propriétés"] if fr else
             ["Event", "Source", "Category", "Occurrences", "<code>value</code> field",
              "Properties"])
    th = "".join(f"<th data-sortable>{h}</th>" for h in heads)
    rows = []
    for e in evs:
        rows.append(
            "<tr>"
            f'<td><code>{html.escape(str(e.get("name","")))}</code></td>'
            f'<td>{html.escape(str(e.get("source","")))}</td>'
            f'<td>{html.escape(_intent_label(e.get("intent"), lang))}</td>'
            f'<td>{fmt_int(e.get("total",0), lang)}</td>'
            f'<td>{_value_field_cell(e, lang)}</td>'
            f'<td class="small">{_props_cell(e, lang)}</td>'
            "</tr>")
    return (
        '<table class="grid ir-searchable ir-exportable ir-sortable" data-csv-name="tracked_events">'
        f'<thead><tr>{th}</tr></thead><tbody>{"".join(rows)}</tbody></table>')


def audit_event_properties_table(audit: Optional[dict], lang: str = "en",
                                 top: Optional[int] = None, samples: int = 5) -> str:
    """Per-property VALUE SAMPLES for every tracked custom event.

    Columns: Event · Property · Type · Distinct values · Sample values.
    One row per (event, property), plus one row for Airship's reserved `value` field
    whenever it is populated — so the reader can see, per event, what is actually
    collected and whether the values are usable (clean enum vs free text vs empty).

    This is the evidence layer behind every "your taxonomy is/isn't segmentable"
    claim: property names alone never prove a property is usable, the values do.
    Returns "" when no audit or no property anywhere (graceful degradation).
    """
    if not audit or not audit.get("available"):
        return ""
    an = audit.get("analysis") or {}
    evs = sorted((an.get("eventProperties") or []), key=lambda e: -(e.get("total") or 0))
    if top:
        evs = evs[:top]
    fr = resolve_lang(lang) == "fr"
    rows = []
    for e in evs:
        name = html.escape(str(e.get("name", "")))
        vf = e.get("valueField") or {}
        # the reserved `value` field first: it is the one that unlocks revenue attribution
        vsamples = [str(s.get("value")) for s in (e.get("valueSamples") or [])
                    if s.get("value") is not None]
        if vsamples:
            kind = ("Montant" if fr else "Amount") if vf.get("carriesAmount") else \
                   ("Compteur" if fr else "Counter")
            distinct = vf.get("distinctAmounts") if vf.get("carriesAmount") else len(set(vsamples))
            rows.append(
                "<tr>"
                f"<td><code>{name}</code></td>"
                f'<td><code>value</code> <span class="tag">'
                + ("réservé" if fr else "reserved") + "</span></td>"
                f"<td>{html.escape(kind)}</td>"
                f'<td>{fmt_int(distinct or 0, lang)}</td>'
                f'<td class="small" data-verbatim>{_verbatim(", ".join(vsamples[:samples]))}</td>'
                "</tr>")
        for p in (e.get("properties") or []):
            samp = [_clip(str(s)) for s in (p.get("samples") or [])][:samples]
            cell = _verbatim(", ".join(samp)) if samp else _DASH
            note = p.get("note")
            if note:
                cell += f'<br><span class="pill pill-low">{html.escape(str(note))}</span>'
            rows.append(
                "<tr>"
                f"<td><code>{name}</code></td>"
                f'<td><code>{html.escape(str(p.get("name","")))}</code></td>'
                f"<td>{html.escape(_prop_kind_label(p.get('kind'), lang))}</td>"
                f'<td>{fmt_int(p.get("distinctShown", 0) or 0, lang)}</td>'
                f'<td class="small" data-verbatim>{cell}</td>'
                "</tr>")
    if not rows:
        return ""
    heads = (["Événement", "Propriété", "Type", "Valeurs distinctes", "Exemples de valeurs"]
             if fr else ["Event", "Property", "Type", "Distinct values", "Sample values"])
    th = "".join(f"<th data-sortable>{html.escape(h)}</th>" for h in heads)
    return (
        '<table class="grid ir-searchable ir-exportable ir-sortable" '
        'data-csv-name="event_property_values">'
        f'<thead><tr>{th}</tr></thead><tbody>{"".join(rows)}</tbody></table>')


def audit_attributes_table(audit: Optional[dict], lang: str = "en", top: Optional[int] = None) -> str:
    """Exhaustive table of tracked attributes with a heuristic category.

    Columns: Attribute · Category · Source · Updates · Distinct values · Sample values.
    Sourced from inventory['attributes'].
    """
    if not audit or not audit.get("available"):
        return ""
    inv = audit.get("inventory") or {}
    attrs = list(inv.get("attributes") or [])
    if not attrs:
        return ""
    attrs.sort(key=lambda a: -(a.get("total") or 0))
    if top:
        attrs = attrs[:top]
    fr = resolve_lang(lang) == "fr"
    heads = (["Attribut", "Catégorie", "Source", "Mises à jour", "Valeurs distinctes", "Exemples de valeurs"]
             if fr else ["Attribute", "Category", "Source", "Updates", "Distinct values", "Sample values"])
    th = "".join(f'<th data-sortable>{html.escape(h)}</th>' for h in heads)
    rows = []
    for a in attrs:
        key = a.get("key") or a.get("normalized") or ""
        samples = a.get("sampleValues") or []
        samp = ", ".join(_verbatim(s) for s in samples[:3])
        rows.append(
            "<tr>"
            f'<td><code>{html.escape(str(key))}</code></td>'
            f'<td>{html.escape(_attr_category(key, lang))}</td>'
            f'<td>{html.escape(str(a.get("sources","")))}</td>'
            f'<td>{fmt_int(a.get("total",0), lang)}</td>'
            f'<td>{fmt_int(a.get("distinctValues",0), lang) if isinstance(a.get("distinctValues"),(int,float)) else html.escape(str(a.get("distinctValues","")))}</td>'
            f'<td class="small" data-verbatim>{samp}</td>'
            "</tr>")
    return (
        '<table class="grid ir-searchable ir-exportable ir-sortable" data-csv-name="tracked_attributes">'
        f'<thead><tr>{th}</tr></thead><tbody>{"".join(rows)}</tbody></table>')


def audit_tags_table(audit: Optional[dict], lang: str = "en", top: Optional[int] = None) -> str:
    """Table of tracked tag groups (key · group · net · source)."""
    if not audit or not audit.get("available"):
        return ""
    inv = audit.get("inventory") or {}
    tags = list(inv.get("tags") or [])
    if not tags:
        return ""
    tags.sort(key=lambda t: -abs(t.get("net") or 0))
    if top:
        tags = tags[:top]
    fr = resolve_lang(lang) == "fr"
    heads = (["Tag", "Groupe", "Ajoutés", "Retirés", "Net", "Source"] if fr
             else ["Tag", "Group", "Added", "Removed", "Net", "Source"])
    th = "".join(f'<th data-sortable>{html.escape(h)}</th>' for h in heads)
    rows = []
    for t in tags:
        vs = t.get("versionScope") or {}
        rows.append(
            "<tr>"
            f'<td><code>{html.escape(str(t.get("value") or t.get("key","")))}</code></td>'
            f'<td>{html.escape(str(t.get("group","")))}</td>'
            f'<td>{fmt_int(t.get("added",0), lang)}</td>'
            f'<td>{fmt_int(t.get("removed",0), lang)}</td>'
            f'<td>{fmt_int(t.get("net",0), lang)}</td>'
            f'<td class="small">{html.escape(str(vs.get("sourceScope","")))}</td>'
            "</tr>")
    return (
        '<table class="grid ir-searchable ir-exportable ir-sortable" data-csv-name="tracked_tags">'
        f'<thead><tr>{th}</tr></thead><tbody>{"".join(rows)}</tbody></table>')


def audit_subscriptions_table(audit: Optional[dict], lang: str = "en") -> str:
    """Table of subscription lists (id · net subscribers · source)."""
    if not audit or not audit.get("available"):
        return ""
    inv = audit.get("inventory") or {}
    subs = list(inv.get("subscriptionLists") or [])
    if not subs:
        return ""
    fr = resolve_lang(lang) == "fr"
    heads = (["Liste d’abonnement", "Abonnements", "Désabonnements", "Net", "Source"] if fr
             else ["Subscription list", "Subscribes", "Unsubscribes", "Net", "Source"])
    th = "".join(f'<th data-sortable>{html.escape(h)}</th>' for h in heads)
    rows = []
    for s in subs:
        rows.append(
            "<tr>"
            f'<td><code>{html.escape(str(s.get("listId","")))}</code></td>'
            f'<td>{fmt_int(s.get("subscribe",0), lang)}</td>'
            f'<td>{fmt_int(s.get("unsubscribe",0), lang)}</td>'
            f'<td>{fmt_int(s.get("net",0), lang)}</td>'
            f'<td class="small">{html.escape(str(s.get("source","")))}</td>'
            "</tr>")
    return (
        '<table class="grid ir-sortable" data-csv-name="subscription_lists">'
        f'<thead><tr>{th}</tr></thead><tbody>{"".join(rows)}</tbody></table>')


def audit_screens_table(audit: Optional[dict], lang: str = "en", top: Optional[int] = None) -> str:
    """Table of tracked screens (name · occurrences)."""
    if not audit or not audit.get("available"):
        return ""
    inv = audit.get("inventory") or {}
    screens = list(inv.get("screens") or [])
    if not screens:
        return ""
    screens.sort(key=lambda s: -(s.get("total") or 0))
    if top:
        screens = screens[:top]
    fr = resolve_lang(lang) == "fr"
    heads = (["Écran", "Occurrences", "iOS", "Android"] if fr else ["Screen", "Occurrences", "iOS", "Android"])
    th = "".join(f'<th data-sortable>{html.escape(h)}</th>' for h in heads)
    rows = []
    for s in screens:
        pf = s.get("platforms") or {}
        rows.append(
            "<tr>"
            f'<td><code>{html.escape(str(s.get("name","")))}</code></td>'
            f'<td>{fmt_int(s.get("total",0), lang)}</td>'
            f'<td>{fmt_int(pf.get("iOS",0), lang)}</td>'
            f'<td>{fmt_int(pf.get("Android",0), lang)}</td>'
            "</tr>")
    return (
        '<table class="grid ir-searchable ir-exportable ir-sortable" data-csv-name="tracked_screens">'
        f'<thead><tr>{th}</tr></thead><tbody>{"".join(rows)}</tbody></table>')


def campaign_inventory_table(rows: Sequence[dict], lang: str = "en") -> str:
    """Complete table of detected campaigns with their classification.

    Each row (all optional except name): {name, channel, typology, trigger, pillar,
    lever, personalized(bool), conversion(bool|str), sends(int|str), reliability(0-1|str),
    note}. reliability as a 0-1 float renders as a reliability pill; a string prints as-is.
    """
    if not rows:
        return ""
    fr = resolve_lang(lang) == "fr"
    heads = (["Campagne", "Canal", "Typologie", "Déclencheur", "Pilier", "Perso.",
              "Conversion", "Envois", "Fiabilité"] if fr else
             ["Campaign", "Channel", "Typology", "Trigger", "Pillar", "Pers.",
              "Conversion", "Sends", "Reliability"])
    th = "".join(f'<th data-sortable>{html.escape(h)}</th>' for h in heads)
    body = []
    for r in rows:
        rel = r.get("reliability")
        rel_cell = (reliability_pill(rel, lang) if isinstance(rel, (int, float))
                    else (html.escape(str(rel)) if rel else _DASH))
        conv = r.get("conversion")
        if isinstance(conv, bool):
            conv_cell = _yn_pill(conv, lang)
        else:
            conv_cell = html.escape(str(conv)) if conv else _DASH
        sends = r.get("sends")
        sends_cell = fmt_int(sends, lang) if isinstance(sends, (int, float)) else (html.escape(str(sends)) if sends else _DASH)
        body.append(
            "<tr>"
            f'<td class="brk">{_etext(r.get("name"))}</td>'
            f'<td>{_etext(r.get("channel") or _DASH)}</td>'
            f'<td>{_etext(r.get("typology") or _DASH)}</td>'
            f'<td>{_etext(r.get("trigger") or _DASH)}</td>'
            f'<td>{_etext(r.get("pillar") or _DASH)}</td>'
            f'<td>{_yn_pill(r.get("personalized"), lang)}</td>'
            f'<td class="brk">{conv_cell}</td>'
            f'<td>{sends_cell}</td>'
            f'<td>{rel_cell}</td>'
            "</tr>")
    return (
        '<table class="grid wide ir-searchable ir-exportable ir-sortable" '
        'data-csv-name="detected_campaigns">'
        f'<thead><tr>{th}</tr></thead><tbody>{"".join(body)}</tbody></table>')


# ---------------------------------------------------------------------------
# GOALS REVIEW (light mode) components
#
# Every one of these renders the output of `goal_candidates.py`. They keep the
# module's `lang=` signature so a builder can pass it uniformly, but the goals
# review is English-only by design and their copy is written in English.
# ---------------------------------------------------------------------------
_STAGE_LABEL = {
    "acquisition": "Acquisition", "activation": "Activation",
    "consideration": "Consideration", "conversion": "Conversion",
    "loyalty": "Loyalty", "retention": "Retention",
}
_STAGE_ORDER = ["acquisition", "activation", "consideration", "conversion",
                "loyalty", "retention"]
_KIND_LABEL = {
    "custom_event": "Custom event", "tag": "Tag group",
    "subscription_list": "Subscription list", "native_signal": "Native signal",
    "nps": "NPS survey",
}
_MODE_LABEL = {"count": "Count", "frequency": "Frequency", "numeric_property": "Threshold"}
_SETUP_LABEL = {
    "none": ("Ready", "pill-good"),
    "add_scene_survey": ("Scene survey", "pill-mid"),
    "add_event_to_project": ("Enable in project", "pill-mid"),
    "instrument_then_add": ("Instrument first", "pill-low"),
}

_TICKS_RE = re.compile(r"`([^`]{1,80})`")


def _ticks(s) -> str:
    """Escape engine prose, then turn its `identifiers` into real <code> spans.

    `goal_candidates.py` writes every event and property name in backticks, the way
    the rest of the skill's prose does. Escaping alone would show the reader a
    literal backtick, so the convention is honoured here rather than stripped out of
    the engine, where it keeps the strings readable in JSON and on the console.
    """
    return _TICKS_RE.sub(r"<code>\1</code>", html.escape(str(s or "")))


def _stage_label(stage: Optional[str]) -> str:
    return _STAGE_LABEL.get(stage or "", (stage or "—").replace("_", " ").title())


def _goal_source_cell(c: dict) -> str:
    """Name + what it actually is, so a tag never reads as an event."""
    name = html.escape(str(c.get("name") or ""))
    detail = c.get("source_detail")
    out = f"<code>{name}</code>"
    if detail and str(detail) != str(c.get("name")):
        out += f'<br><span class="small">{html.escape(str(detail))}</span>'
    return out


def _predefined_cell(c: dict) -> str:
    """How the candidate relates to an Airship predefined event.

    'how' matters more than the match itself: an exact match means the client is
    already on the standard, a fuzzy one means a rename would unlock the predefined
    property template, and no match means the event is theirs alone — which is fine,
    it just gets no template.
    """
    pm = c.get("predefined_match") or {}
    if not pm:
        return '<span class="small">—</span>'
    how = pm.get("how")
    cls = {"exact": "pill-good", "fuzzy": "pill-mid",
           "naming_standard": "pill-mid"}.get(how, "pill-low")
    label = {"exact": "exact", "fuzzy": "close name",
             "naming_standard": "recommended name"}.get(how, str(how or ""))
    return (f'<code>{html.escape(str(pm.get("name") or ""))}</code> '
            f'<span class="pill {cls}">{html.escape(label)}</span>')


def _modes_cell(c: dict) -> str:
    modes = c.get("config_modes") or []
    rec = (c.get("recommended_config") or {}).get("mode")
    out = []
    for mo in modes:
        lbl = _MODE_LABEL.get(mo, mo)
        out.append(f'<span class="pill pill-good">{html.escape(lbl)}</span>' if mo == rec
                   else f'<span class="tag">{html.escape(lbl)}</span>')
    return " ".join(out) or '<span class="small">—</span>'


def _value_cell(c: dict) -> str:
    """Whether the candidate can carry an amount, and whether it is safe to sum."""
    if c.get("carries_amount"):
        prop = c.get("value_property")
        cur = c.get("currency_property")
        out = '<span class="pill pill-good">Amount</span>'
        if prop:
            out += f' <code>{html.escape(str(prop))}</code>'
        out += ('<br><span class="small">currency: '
                + (f'<code>{html.escape(str(cur))}</code>' if cur
                   else '<b>not collected</b>') + '</span>')
        return out
    if c.get("has_value"):
        return '<span class="tag">Counter</span><br><span class="small">no amount</span>'
    return '<span class="pill pill-low">No value</span>'


def _props_chiplist(props: Sequence[dict], show: int = 5) -> str:
    if not props:
        return '<span class="small">—</span>'
    chips = " ".join(f'<code>{html.escape(str(p.get("name") or ""))}</code>'
                     for p in list(props)[:show])
    if len(props) > show:
        chips += f' <span class="small">+{len(props) - show}</span>'
    return chips


def _blockers_cell(c: dict) -> str:
    bl = c.get("blockers") or []
    if not bl:
        return '<span class="pill pill-good">None</span>'
    first = _ticks(bl[0])
    more = f' <span class="small">+{len(bl) - 1} more</span>' if len(bl) > 1 else ""
    return f'<span class="small">{first}</span>{more}'


def goal_candidates_table(cands: Sequence[dict], lang: str = "en",
                          kind: Optional[str] = None,
                          include_excluded: bool = False) -> str:
    """Every collected data point qualified as a goal candidate, one table per kind.

    ``kind`` filters to "custom_event" / "tag" / "subscription_list" so each source
    type gets its own table (their columns mean different things: a tag has no
    `value` field, a list has no properties). Excluded candidates are left out by
    default — they get their own anti-patterns table, where the reason is the point.
    """
    rows = [c for c in (cands or []) if c.get("family") == "collected"]
    if kind:
        rows = [c for c in rows if c.get("kind") == kind]
    if not include_excluded:
        rows = [c for c in rows if not c.get("exclude")]
    if not rows:
        return ""
    rows.sort(key=lambda c: (-(c.get("score") or 0), -(c.get("total") or 0)))
    # A per-kind table already states the type in its heading, so repeating it in a
    # column only steals width from the cells that carry the identifiers.
    typed = kind is None
    heads = (["Source"] + (["Type"] if typed else [])
             + ["Airship predefined", "Funnel stage", "Occurrences", "Config modes",
                "Value", "Usable properties", "Blockers"])
    th = "".join(f"<th data-sortable>{html.escape(h)}</th>" for h in heads)
    body = []
    for c in rows:
        total = c.get("total")
        type_td = (f'<td>{html.escape(_KIND_LABEL.get(c.get("kind"), str(c.get("kind") or "")))}</td>'
                   if typed else "")
        body.append(
            "<tr>"
            f'<td class="brk">{_goal_source_cell(c)}</td>'
            f"{type_td}"
            f'<td class="brk">{_predefined_cell(c)}</td>'
            f'<td>{html.escape(_stage_label(c.get("funnel_stage")))}</td>'
            f'<td>{fmt_int(total, lang) if total is not None else _DASH}</td>'
            f"<td>{_modes_cell(c)}</td>"
            f"<td>{_value_cell(c)}</td>"
            f'<td class="small brk">'
            f'{_props_chiplist(c.get("usable_properties") or [], show=4)}</td>'
            f'<td class="small">{_blockers_cell(c)}</td>'
            "</tr>")
    csv_name = f"goal_candidates_{kind}" if kind else "goal_candidates"
    return (
        '<table class="grid wide ir-searchable ir-exportable ir-sortable" '
        f'data-csv-name="{html.escape(csv_name)}">'
        f'<thead><tr>{th}</tr></thead><tbody>{"".join(body)}</tbody></table>')


def goal_config_table(cands: Sequence[dict], lang: str = "en") -> str:
    """The configuration dimension: HOW to set each candidate up, not whether to.

    Count, frequency over a period, or a threshold on a numeric property are three
    different goals on the same act, and picking the wrong one is the most common way
    a configured goal ends up measuring nothing (a frequency goal everybody meets).
    """
    rows = [c for c in (cands or [])
            if not c.get("exclude") and c.get("family") in ("collected", "native")]
    if not rows:
        return ""
    rows.sort(key=lambda c: -(c.get("score") or 0))
    heads = ["Source", "Recommended mode", "Period", "Threshold property",
             "Also available", "Why this mode"]
    th = "".join(f"<th data-sortable>{html.escape(h)}</th>" for h in heads)
    body = []
    for c in rows:
        rec = c.get("recommended_config") or {}
        mode = rec.get("mode") or "count"
        others = [_MODE_LABEL.get(m, m) for m in (c.get("config_modes") or [])
                  if m != mode]
        thr = rec.get("property") or c.get("threshold_property")
        why = c.get("rationale") or ""
        body.append(
            "<tr>"
            f'<td><code>{html.escape(str(c.get("name") or ""))}</code></td>'
            f'<td><span class="pill pill-good">'
            f'{html.escape(_MODE_LABEL.get(mode, mode))}</span></td>'
            f'<td>{html.escape(str(rec.get("period") or "")) or _DASH}</td>'
            f'<td>{f"<code>{html.escape(str(thr))}</code>" if thr else _DASH}</td>'
            f'<td class="small">{html.escape(", ".join(others)) or _DASH}</td>'
            f'<td class="small">{_ticks(why)}</td>'
            "</tr>")
    return (
        '<table class="grid wide ir-searchable ir-exportable ir-sortable" '
        'data-csv-name="goal_configuration">'
        f'<thead><tr>{th}</tr></thead><tbody>{"".join(body)}</tbody></table>')


def goal_priority_board(priorities: Optional[dict], lang: str = "en") -> str:
    """North star, primaries by funnel stage and diagnostics, at a glance.

    A flat ranked list makes every goal look like a variant of the one above it. The
    board says the opposite: one goal the brand is judged on, and a thin layer of
    stage-level primaries under it.
    """
    if not priorities:
        return ""
    cols = []
    ns = priorities.get("north_star")
    if ns:
        cols.append(
            '<div class="ir-ladder-col">'
            '<div class="ir-ladder-lvl">North star</div>'
            f'<h4><code>{html.escape(str(ns.get("name") or ""))}</code></h4>'
            f'<span class="ir-lev done">{html.escape(_stage_label(ns.get("funnel_stage")))}'
            f' \u00b7 {html.escape(_MODE_LABEL.get((ns.get("recommended_config") or {}).get("mode"), "Count"))}</span>'
            # An empty rationale still rendered its bullet, leaving a stray tick under
            # the most important tile on the page.
            + (f'<span class="ir-lev done">{_ticks(ns.get("rationale"))}</span>'
               if (ns.get("rationale") or "").strip() else "")
            + "</div>")
    prim = priorities.get("primary") or {}
    for stage in _STAGE_ORDER:
        items = prim.get(stage) or []
        if not items:
            continue
        levs = "".join(
            f'<span class="ir-lev done"><code>{html.escape(str(c.get("name") or ""))}</code>'
            f' \u00b7 {html.escape(_MODE_LABEL.get((c.get("recommended_config") or {}).get("mode"), "Count"))}</span>'
            for c in items)
        cols.append(
            '<div class="ir-ladder-col">'
            '<div class="ir-ladder-lvl">Primary</div>'
            f"<h4>{html.escape(_stage_label(stage))}</h4>{levs}</div>")
    diagnostics = priorities.get("secondary") or []
    if diagnostics:
        levs = "".join(
            f'<span class="ir-lev todo"><code>{html.escape(str(c.get("name") or ""))}</code>'
            + (f' \u00b7 {html.escape(_stage_label(c.get("funnel_stage")))}'
               if c.get("funnel_stage") else "")
            + "</span>"
            for c in diagnostics)
        cols.append(
            '<div class="ir-ladder-col">'
            '<div class="ir-ladder-lvl">Secondary</div>'
            f"<h4>Diagnostic</h4>{levs}</div>")
    if not cols:
        return ""
    return f'<div class="ir-ladder">{"".join(cols)}</div>'


def goal_antipatterns_table(excluded: Sequence[dict], lang: str = "en") -> str:
    """What NOT to configure as a goal, and why — the other half of the advice.

    Naming the exclusions is what stops the team spending a slot on a `screen_viewed`
    everybody triggers, or on a logout the brand wants less of.
    """
    rows = [c for c in (excluded or []) if c.get("exclude")]
    if not rows:
        return ""
    rows.sort(key=lambda c: (str(c.get("exclude_kind") or ""), -(c.get("total") or 0)))
    heads = ["Source", "Type", "Occurrences", "Why it is not a goal", "Reason"]
    th = "".join(f"<th data-sortable>{html.escape(h)}</th>" for h in heads)
    body = []
    for c in rows:
        total = c.get("total")
        body.append(
            "<tr>"
            f'<td><code>{html.escape(str(c.get("name") or ""))}</code></td>'
            f'<td>{html.escape(_KIND_LABEL.get(c.get("kind"), str(c.get("kind") or "")))}</td>'
            f"<td>{fmt_int(total, lang) if total is not None else _DASH}</td>"
            f'<td><span class="pill pill-low">'
            f'{html.escape(str(c.get("exclude_label") or "Excluded"))}</span></td>'
            f'<td class="small">{_ticks(c.get("exclude_reason"))}</td>'
            "</tr>")
    return (
        '<table class="grid wide ir-searchable ir-exportable ir-sortable" '
        'data-csv-name="goal_antipatterns">'
        f'<thead><tr>{th}</tr></thead><tbody>{"".join(body)}</tbody></table>')


def funnel_coverage_matrix(coverage: Optional[dict], lang: str = "en",
                           stages: Optional[Sequence[dict]] = None) -> str:
    """Funnel stage × covered by collected data / by a native signal / blind.

    The blind rows are the commercial argument: a stage nothing measures cannot be
    optimised, reported on, or attributed to a campaign.
    """
    if not coverage:
        return ""
    questions = {s.get("id"): s.get("question") for s in (stages or [])}
    heads = ["Funnel stage", "What it answers", "From collected data",
             "From native signals", "Not measurable today"]
    th = "".join(f"<th>{html.escape(h)}</th>" for h in heads)
    body = []
    for stage in _STAGE_ORDER:
        cov = coverage.get(stage)
        if cov is None:
            continue
        collected = cov.get("collected") or []
        native = cov.get("native") or []
        gaps = cov.get("gaps") or []
        blind = not collected and not native
        chips = lambda xs, cls: (" ".join(
            f'<span class="{cls}"><code>{html.escape(str(x))}</code></span>' for x in xs)
            or '<span class="small">—</span>')
        gap_cell = ('<span class="pill pill-low">Blind stage</span><br>' if blind else "")
        gap_cell += chips(gaps, "tag") if gaps else '<span class="small">—</span>'
        body.append(
            "<tr>"
            f'<td><b>{html.escape(_stage_label(stage))}</b></td>'
            f'<td class="small">{html.escape(str(questions.get(stage) or ""))}</td>'
            f'<td class="small">{chips(collected, "pill pill-good")}</td>'
            f'<td class="small">{chips(native, "pill pill-mid")}</td>'
            f'<td class="small">{gap_cell}</td>'
            "</tr>")
    if not body:
        return ""
    return ('<table class="grid wide ir-exportable" data-csv-name="funnel_coverage">'
            f'<thead><tr>{th}</tr></thead><tbody>{"".join(body)}</tbody></table>')


def discovery_questions(questions: Sequence[dict], lang: str = "en",
                        top: Optional[int] = None) -> str:
    """The questions to put to the client, grouped by the candidate that raised them.

    A tagging plan gives names and counts, never intent. Rather than assume what
    `validate_step` means, the report hands the team the question — which is also the
    part of the deliverable that turns the report into a conversation. The goals
    review passes only the questions on the goals its plan shows: the caller filters,
    this renders.
    """
    rows = [q for q in (questions or []) if q.get("questions")]
    if not rows:
        return ""
    if top:
        rows = rows[:top]
    cols = []
    for q in rows:
        items = "".join(f'<span class="ir-lev todo">{_ticks(t)}</span>'
                        for t in (q.get("questions") or []))
        total = q.get("total")
        meta = _KIND_LABEL.get(q.get("kind"), str(q.get("kind") or ""))
        if total is not None:
            meta += f" \u00b7 {fmt_int(total, lang)} occurrences"
        cols.append(
            '<div class="ir-pillar">'
            f'<h4><code>{html.escape(str(q.get("name") or ""))}</code></h4>'
            f'<div class="ir-pillar-meta">{html.escape(meta)}</div>{items}</div>')
    return f'<div class="ir-pillars">{"".join(cols)}</div>'


def goal_eligibility_matrix(lang: str = "en",
                            attributes_soon: bool = True) -> str:
    """What can be a goal in Airship today, and what it costs to get there.

    Static reference, but the one that settles the recurring misunderstanding: an
    Airship predefined event the client does not send is a measurement gap, not an
    available goal.
    """
    rows = [
        ("Tracked custom events", "Yes",
         "Already in the project — configure and go.", "pill-good"),
        ("Tags / tag groups", "Yes",
         "Goal on gaining the tag. Works for CRM-set tags too.", "pill-good"),
        ("Subscription lists", "Yes",
         "Goal on subscribing to the list.", "pill-good"),
        ("Channel registration, app open, first open", "Yes",
         "Native Airship signals — no instrumentation at all.", "pill-good"),
        ("Notification opt-in", "Yes",
         "Native signal; the permission moment itself.", "pill-good"),
        ("Named user association", "Yes",
         "Native signal; fires when a channel is tied to an account.", "pill-good"),
        ("NPS score", "Yes",
         "Needs an NPS survey published in Scene — no SDK work.", "pill-mid"),
        ("Airship predefined events the client does NOT send", "No",
         "Airship knowing the name does not make the data exist. "
         "Instrument it first; until then it is a gap, not a candidate.", "pill-low"),
        ("Attributes", "Soon" if attributes_soon else "No",
         "Attribute-based goals are on the roadmap. Worth shaping the "
         "attribute taxonomy now so the goals are available on day one.", "pill-mid"),
    ]
    th = "".join(f"<th>{html.escape(h)}</th>"
                 for h in ["Data source", "Usable as a goal", "What it takes"])
    body = "".join(
        "<tr>"
        f"<td><b>{html.escape(src)}</b></td>"
        f'<td><span class="pill {cls}">{html.escape(ok)}</span></td>'
        f'<td class="small">{html.escape(note)}</td>'
        "</tr>" for src, ok, note, cls in rows)
    return ('<table class="grid ir-exportable" data-csv-name="goal_eligibility">'
            f"<thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>")


def attribute_goal_candidates_table(rows: Sequence[dict], lang: str = "en") -> str:
    """Attributes proposed as future goals, with the goal shape each one would take.

    Attribute goals are not live yet, so this section is a proposal, not a plan: it
    says which of the client's attributes are already shaped like an outcome, and
    which would need work before they could carry one.
    """
    rows = list(rows or [])
    if not rows:
        return ""
    heads = ["Attribute", "Funnel stage", "Tracked today", "Updates", "Distinct values",
             "Sample values", "Goal shape", "Why it would matter"]
    th = "".join(f"<th data-sortable>{html.escape(h)}</th>" for h in heads)
    body = []
    for a in rows:
        total = a.get("total")
        distinct = a.get("distinct")
        samples = ", ".join(str(s) for s in (a.get("sample_values") or [])[:4])
        tracked = bool(a.get("tracked"))
        body.append(
            "<tr>"
            f'<td><code>{html.escape(str(a.get("name") or ""))}</code></td>'
            f'<td>{html.escape(_stage_label(a.get("funnel_stage")))}</td>'
            f'<td><span class="pill {"pill-good" if tracked else "pill-low"}">'
            f'{"Yes" if tracked else "Not yet"}</span></td>'
            f"<td>{fmt_int(total, lang) if total is not None else _DASH}</td>"
            f"<td>{fmt_int(distinct, lang) if distinct is not None else _DASH}</td>"
            f'<td class="small" data-verbatim>{_verbatim(samples) if samples else _DASH}</td>'
            f'<td>{html.escape(str(a.get("proposed_goal") or ""))}</td>'
            f'<td class="small">{_ticks(a.get("why"))}</td>'
            "</tr>")
    return (
        '<table class="grid wide ir-searchable ir-exportable ir-sortable" '
        'data-csv-name="attribute_goal_candidates">'
        f'<thead><tr>{th}</tr></thead><tbody>{"".join(body)}</tbody></table>')


if __name__ == "__main__":
    # tiny self-test
    demo_pb = {
        "notification": {"ios": {"media_attachment": {"url": "https://x/y.jpg"}}},
        "message": {"title": "hi"},
        "options": {"__ui_id": "78amsVlZQtGBylROYqHlmA", "personalization": True,
                     "bypass_frequency_limits": True, "message_name": "TEST",
                     "is_test": True},
    }
    assert composer_id_from_pushbody(demo_pb) == "78amsVlZQtGBylROYqHlmA"
    b64 = base64.b64encode(json.dumps(demo_pb).encode()).decode()
    assert composer_id_from_pushbody(b64) == "78amsVlZQtGBylROYqHlmA"
    assert composer_id_from_pushbody("") is None
    f = push_features(demo_pb)
    assert f["rich"] and f["personalization"] and f["message_center"] and f["frequency_bypass"]
    assert flight_deck_url("APPKEY", "UIID", "eu").endswith("airship.eu/admin/flight_deck/apps/APPKEY/messages/UIID")
    assert flight_deck_url("APPKEY", "UIID", "us").split("/")[2] == "go-admin.airship.com"
    print(gauge(42.0, 20, 35, 55, unit="%", verdict=verdict_pill("good", "Above median"))[:60], "...")
    # charts
    lib = chartjs_inline()
    assert lib.startswith("<script>") and ("Chart" in lib), "Chart.js not inlined"
    fig = interactive_chart("sends", "data:image/png;base64,AAAA",
                            {"type": "bar", "data": {"labels": ["a"], "datasets": []}},
                            alt="sends")
    assert 'data-chart="sends"' in fig and 'id="spec-sends"' in fig
    assert 'class="ir-chart-static"' in fig and 'canvas' in fig
    assert 'data-csv-chart="sends"' in fig      # CSV toolbar present by default
    # spec must not break out of the <script>
    bad = interactive_chart("x", "data:,", {"t": "</script><b>"})
    assert "</script><b>" not in bad.split('type="application/json"')[1]
    # explicit CSV override embeds a text/csv block
    fig2 = interactive_chart("y", "data:,", {"data": {}}, csv="a,b\n1,2")
    assert 'id="csv-y"' in fig2
    # dashboard head wraps the body in .ir-main and closes it in js_block
    css_b, nav_b, js_b = interactive_head("out.pdf", layout="dashboard")
    assert 'class="ir-side' in nav_b and nav_b.rstrip().endswith('<div class="ir-main" id="ir-main">')
    assert js_b.lstrip().startswith("</div>")
    # the Expand/Collapse-all control lives ONCE at the top of the TOC (built in JS);
    # the old duplicate at the sidebar foot must be gone from the nav shell
    assert 'data-ir-expand="all"' not in nav_b and 'ir-side-foot' not in nav_b
    assert 'data-ir-tree' in INTERACTIVE_JS  # tree Expand/Collapse-all is emitted by buildTOC()
    # legacy bar layout still available
    _, nav_bar, _ = interactive_head("out.pdf", layout="bar")
    assert 'class="ir-nav' in nav_bar
    # methodology + kpi_card
    m = methodology("A / B", inputs={"A": 10, "B": 20}, source="reports/opens",
                    confidence="High", sample="30 days")
    assert "ir-method" in m and "reports/opens" in m and "pill-good" in m
    k = kpi_card("50%", "Open rate", formula="opens / sends",
                 inputs={"opens": 5, "sends": 10}, source="reports/opens",
                 confidence="Medium", sample="n=10")
    assert "ir-kpi" in k and "ir-kpi-info" in k and "data-ir-kpi-method" in k and "<template" in k
    kp = kpi_card("50%", "Open rate", formula="o/s", print_methodology=True)
    assert "ir-kpi-method-print" in kp
    assert "ir-kpi-modal" in js_b
    mc = creative_mc_preview("data:,", "MC caption", alt="mc")
    assert "ir-creative-mc" in mc and "ir-mc-viewport" in mc
    push = creative_push_preview("data:,", "Push caption")
    assert "ir-creative-push" in push
    # event-analysis rendering helpers
    assert _compact_amount(12214923.89, "EUR") == "\u20ac12.2M"
    assert _compact_amount(0) == "\u20ac0".replace("\u20ac", "")  # no currency -> "0"
    demo_kpis = [{
        "name": "passage_commande", "category": "Purchase", "kpi_kind": "business",
        "confidence": "Low", "total_count": 835178, "attr_count_rate": 0.147,
        "attribution": {"direct": {"count": 749}, "indirect": {"count": 122124},
                        "unattributed": {"count": 712305}, "attr_count_rate": 0.147},
        "value_is_monetary": True,
        "amounts": {"currency": "EUR", "attributed_amount": 12214923.89},
    }]
    tbl = event_kpi_table(demo_kpis)
    assert "ir-sortable" in tbl and "passage_commande" in tbl and "\u20ac12.2M" in tbl
    labels, vals = attribution_series(demo_kpis[0])
    assert labels[0] == "Direct" and vals == [749, 122124, 712305]
    ana = {"currency": {"currency": "EUR", "basis": "brand country FR", "confidence": "Medium"},
           "events": [{"name": "passage_commande", "total_count": 835178,
                       "value_monetary": {"value_is_monetary": True, "value_per_event": 99.68},
                       "amounts": {"attributed_amount": 12214923.89,
                                   "unattributed_amount": 71033900.8,
                                   "total_amount": 83248824.68}}]}
    vb = value_amounts_block(ana)
    assert "Currency assumed" in vb and "EUR" in vb and "client-declared" in vb
    assert value_amounts_block({"events": []}) == ""
    opps = opportunities_tables({
        "send_more": [{"custom_name": "purchased", "category": "Purchase",
                       "kpi_kind": "business", "is_conversion": True,
                       "carries_value": True, "confidence": "Medium"}],
        "enrich_value": [{"name": "add_to_cart_web", "category": "Add to cart",
                          "expected_value_property": "total_amount",
                          "current_value_per_event": 1.0, "confidence": "Medium"}],
    })
    assert "purchased" in opps["send_more"] and "add_to_cart_web" in opps["enrich_value"]
    assert attributed_conversions_cell({"available": True,
                                        "total_attributed_conversions": 420,
                                        "total_attributed_amount": 42000.0,
                                        "currency": "EUR"}) == "420 conv \u00b7 \u20ac42k"
    assert "n/a" in attributed_conversions_cell({"available": False, "reason": "no id"})
    # data-appendix helpers
    demo_audit = {"available": True,
                  "analysis": {"eventProperties": [
                      {"name": "purchase", "source": "SDK", "total": 1200, "intent": "purchase",
                       "valueField": {"isCounter": False, "carriesAmount": True,
                                      "distinctAmounts": 3, "min": 4.5, "max": 90.0, "mean": 21.0},
                       "hasValueObject": True,
                       "valueSamples": [{"value": "9.99", "count": 40}, {"value": "4.50", "count": 12}],
                       "properties": [{"name": "amount", "kind": "amount", "distinctShown": 3,
                                       "samples": ["9.99", "4.50", "90.00"]}]},
                      {"name": "app_opened", "source": "SDK", "total": 40, "intent": "other",
                       "valueField": None, "hasValueObject": False, "valueSamples": [],
                       "properties": []}]},
                  "inventory": {"attributes": [
                      {"key": "favorite_team", "total": 5000, "sources": "SDK", "distinctValues": 32,
                       "sampleValues": ["FRA", "BRA"]}],
                      "tags": [{"value": "Do Not Allow", "group": "Rewards", "added": 10, "removed": 2, "net": 8,
                                "versionScope": {"sourceScope": "sdk"}}],
                      "subscriptionLists": [{"listId": "tickets", "subscribe": 100, "unsubscribe": 5, "net": 95, "source": "SDK"}],
                      "screens": [{"name": "home", "total": 900, "platforms": {"iOS": 500, "Android": 400}}]}}
    _et = audit_events_table(demo_audit)
    assert "purchase" in _et and "Amount" in _et
    # every tracked event is listed, and a bare event says so instead of showing an em dash
    assert "app_opened" in _et and "Not populated" in _et and ">None<" in _et
    assert "Non renseign\u00e9" in audit_events_table(demo_audit, lang="fr")
    _pt = audit_event_properties_table(demo_audit)
    assert "9.99" in _pt and "reserved" in _pt and "event_property_values" in _pt
    assert audit_event_properties_table({"available": False}) == ""
    assert "favorite_team" in audit_attributes_table(demo_audit) and "Preference" in audit_attributes_table(demo_audit)
    assert "Rewards" in audit_tags_table(demo_audit)
    assert "tickets" in audit_subscriptions_table(demo_audit)
    assert "home" in audit_screens_table(demo_audit)
    assert audit_events_table({"available": False}) == ""
    ci = campaign_inventory_table([{"name": "Kick-off", "channel": "Push", "typology": "one-shot",
                                    "pillar": "Editorial", "personalized": False, "conversion": True,
                                    "sends": 1107982, "reliability": 0.9}])
    assert "Kick-off" in ci and "pill" in ci

    # A component that escapes its own prose must still accept the report's idiom:
    # `<code>` and `&amp;` reach the reader as themselves, never as literal markup.
    assert plain_text("a <code>b</code> &amp; c") == "a b & c"
    _m = methodology("envois &amp; ouvertures / <code>base</code>",
                     inputs={"base &amp; scope": "1 000"}, sample="2 &amp; 3", lang="fr")
    assert "&amp;amp;" not in _m and "&lt;code&gt;" not in _m
    # Every section component takes lang=, so a builder can pass it uniformly without
    # having to know which ones happen to localise anything (a missing kwarg used to
    # raise TypeError mid-build).
    for _fn, _arg in ((priority_cards, [{"num": 1, "title": "T", "ambition": "a"}]),
                      (personalization_ladder, [{"level": "1", "title": "T", "items": []}]),
                      (strategy_matrix, [{"label": "L", "coverage_pct": 50}]),
                      (pillar_coverage, [{"label": "P", "done": ["x"]}]),
                      (hero_kpi_band, [{"value": "1", "label": "L"}])):
        _fn(_arg, lang="fr")
    # The tree control's labels are written by JS, so the HTML gate cannot see them:
    # they must be seeded from the document language or a monolingual FR report shows
    # "Expand all". Guarded here because nothing downstream can catch it.
    assert "window.IR_LANG==='fr'" in INTERACTIVE_JS

    # ---- goals-review components -------------------------------------------
    _gc = {"name": "purchased", "family": "collected", "kind": "custom_event",
           "predefined_match": {"name": "purchased", "how": "exact",
                                "category": "Purchase"},
           "funnel_stage": "conversion", "goal_tier": "primary", "total": 22613,
           "config_modes": ["count", "frequency", "numeric_property"],
           "recommended_config": {"mode": "count", "period": None, "property": None},
           "threshold_property": "total_order_value", "carries_amount": True,
           "value_property": "total_order_value", "currency_property": None,
           "usable_properties": [{"name": "category", "kind": "enum", "distinct": 12}],
           "blockers": [], "exclude": False, "score": 0.9,
           "rationale": "The act the business is paid for."}
    _gt = dict(_gc, name="device", kind="tag", exclude=True,
               exclude_label="Descriptive state", exclude_reason="Not an act.",
               predefined_match=None, carries_amount=False, total=399342)
    _t = goal_candidates_table([_gc, _gt], kind="custom_event")
    assert "purchased" in _t and "goal_candidates_custom_event" in _t
    assert "device" not in _t                      # excluded rows stay out by default
    # currency is the difference between an amount and a summable amount: say it
    assert "not collected" in _t
    _ct = goal_config_table([_gc])
    assert "Count" in _ct and "total_order_value" in _ct
    _prio = {"north_star": _gc, "primary": {"conversion": [_gc]},
             "secondary": [],
             "coverage": {"conversion": {"collected": ["purchased"], "native": [],
                                         "gaps": [], "status": "collected"},
                          "loyalty": {"collected": [], "native": [], "gaps": ["x"],
                                      "status": "blind"}}}
    _pb = goal_priority_board(_prio)
    assert "North star" in _pb
    # the plan proposes goals; it no longer keeps a reserve tier waiting behind them
    assert "Reserve" not in _pb
    _ap = goal_antipatterns_table([_gc, _gt])
    assert "device" in _ap and "purchased" not in _ap and "goal_antipatterns" in _ap
    _fc = funnel_coverage_matrix(_prio["coverage"],
                                 stages=[{"id": "loyalty", "question": "Do they return?"}])
    assert "Blind stage" in _fc and "Do they return?" in _fc
    _dq = discovery_questions([{"name": "validate_step", "kind": "custom_event",
                                "total": 5, "questions": ["What does it mean?"]}])
    assert "validate_step" in _dq and "What does it mean?" in _dq
    _em = goal_eligibility_matrix()
    # the recurring misunderstanding this table exists to settle
    assert "does NOT send" in _em and "gap, not a candidate" in _em
    _at = attribute_goal_candidates_table([{"name": "loyalty_tier", "funnel_stage": "loyalty",
                                            "tracked": True, "total": 10, "distinct": 4,
                                            "sample_values": ["gold"],
                                            "proposed_goal": "change to a target value",
                                            "why": "upsell outcome"}])
    assert "loyalty_tier" in _at and "attribute_goal_candidates" in _at
    # engine prose writes identifiers in backticks; they must reach the reader as
    # <code>, never as a literal tick
    assert _ticks("rename `a_b` to `c`") == "rename <code>a_b</code> to <code>c</code>"
    assert _ticks("<b> & `x`") == "&lt;b&gt; &amp; <code>x</code>"
    # graceful degradation: no data must yield no markup, never a broken shell
    for _fn, _empty in ((goal_candidates_table, []), (goal_config_table, []),
                        (goal_priority_board, None),
                        (goal_antipatterns_table, []), (funnel_coverage_matrix, None),
                        (discovery_questions, []),
                        (attribute_goal_candidates_table, [])):
        assert _fn(_empty, lang="en") == "", _fn.__name__
    print("report_interactive self-test OK")
