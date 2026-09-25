#!/usr/bin/env python3
"""Airship-branded matplotlib chart helpers.

Import these from a per-report script. They encode the Airship palette, a k/M tick
formatter, clean spines, and dated x-axes for TIME SERIES ONLY (applying a date
locator to a bar/category chart raises "too many ticks" — so `dateaxis` is opt-in).
Do not put emoji in labels (missing-glyph warnings / blank boxes).

LANGUAGE: chart chrome is **English in every report, including a French one**. Titles, axis
labels, series names and tooltip suffixes stay English and the `*_label` arguments keep their
English defaults; a report ships ONE chart set that both language renders reuse. This is the
single carve-out from the skill's no-mixed-languages rule, taken because two chart sets double
the authoring surface for words like "Sends" and "Open rate %" that need no translation. What
frames the chart — caption, prose, table headers — is localised normally. Axis *values* coming
from client data (event names, CTA copy) are reproduced verbatim, whatever language they are in.

Palette (Airship 2026 brand): INK #000818, BLUE #056DFF (primary), INDIGO/NAVY
#030869, MINT/TEAL #11DBC0, SKY #7ABFFF, LIME #E6F55A, CORAL #E4626F (RED alias,
negative signal), GREY #717680, LIGHT #F7F8F8, GRID #E9EAEB.

Functions (each saves a PNG and returns the path):
  timeseries_stacked(dates, series:dict, out, title=...)   # daily stacked bars (e.g. ios/android)
  area_with_mean(dates, values, out, title=...)            # area + mean line
  donut(labels, values, out, colors=None, center=None)     # composition
  hbar(labels, values, out, title=..., color=RED)          # ranked horizontal bars
  grouped_bars(groups, series:dict, out, title=...)         # clustered category bars

Interactive Chart.js spec emitters (return a JSON-safe config dict; feed the SAME data
as the matching PNG to report_interactive.interactive_chart(id, png, spec) so the on-screen
canvas and the print PNG stay consistent). JSON only -> no JS callbacks; attach a plain
`_extra` array to a dataset for rich tooltips (report_interactive's mount script reads it):
  spec_timeseries_stacked(dates, series)                   # stacked daily sends by platform
  spec_pressure_fatigue(dates, sends, optout_rate, open_rate)  # dual-axis pressure vs fatigue
  spec_funnel(steps, values, attributed=None)              # conversion funnel (h-bars)
  spec_program_ranking(labels, sends, direct_rate, influenced_rate, platform_note, top)
  spec_donut(labels, values, colors, center)               # composition (mirrors donut)
  spec_grouped_bars(groups, series, horizontal, stacked)   # clustered/stacked (mirrors grouped_bars)
  spec_hbar(labels, values, color, label, extra)           # ranked h-bars (mirrors hbar)

Refusing a chart. `spec_funnel` raises `UnpublishableSpec` when a step reads zero above a
step that does not, and `check_series(name, values, blocked_values(audit))` raises when a
series — or its total, which is what the tooltip shows — is a counter listed in
`audit.contaminated_fields`. Catch it in the chart script, drop the spec, and say in the
appendix which chart was refused: the delivery gate requires every generated chart to be
embedded, so a spec that cannot be published honestly must not be generated at all.

THE DOUBLED WINDOW. The collector pulls the daily series over `current + prior` so trend
lines can show a before/after, so `sends.json` and friends hold ~2x the review period. Any
chart that collapses such a series to a SINGLE total — a donut, a ranked bar, a KPI-shaped
figure — has to slice the current window first, and its title has to name the window it
totalled. Skipping the slice is silent: a "(30d)" channel-mix donut totalled 86.25M against
39.1M on every KPI of the same report, which reads as plausible because it is the right
shape and the wrong period. The idiom is a `cur()` helper next to the series:

    CUR = [i for i, d in enumerate(dates) if d >= A["period"]["start"]]
    def cur(series): return [series[i] for i in CUR]

Trend charts want the whole doubled span; totals want `cur(...)`. `verify_report.py`
cross-checks aggregated specs against `facts.json`, so a missed slice fails the gate.

Deps: matplotlib, numpy.
"""
import datetime as _dt

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

# Airship 2026 brand palette (from the AIRSHIP 2026 Master deck theme):
#   INK #000818 · BLUE #056DFF (primary) · NAVY/INDIGO #030869 · TEAL/MINT #11DBC0
#   SKY #7ABFFF · LIGHTBLUE #DCEAFF · LIME #E6F55A · CORAL #E4626F (negative signal)
#   GREY #717680 · LIGHT #F7F8F8 · GRID #E9EAEB
INK = "#000818"
BLUE = "#056DFF"          # primary accent
INDIGO = "#030869"        # deep navy (secondary series)
MINT = "#11DBC0"          # teal (positive signal: opt-in / opens)
SKY = "#7ABFFF"
LIGHTBLUE = "#DCEAFF"
LIME = "#E6F55A"
RED = "#E4626F"           # coral — reserved for negative signals (opt-out / churn)
GREY = "#717680"
LIGHT = "#F7F8F8"
GRID = "#E9EAEB"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Instrument Sans", "Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
    "text.color": INK,
    "axes.edgecolor": GREY,
    "axes.labelcolor": INK,
    "xtick.color": GREY,
    "ytick.color": GREY,
    "axes.titlesize": 15,
    "axes.titleweight": "bold",
    "figure.dpi": 160,
})


# ---------------------------------------------------------------------------
# refusing a chart
# ---------------------------------------------------------------------------
# A chart carries its numbers further than a sentence does. The tooltip and the CSV
# export ship every value whether or not the prose quotes it, and the delivery gate
# requires that every generated chart be embedded — so a spec built on a figure the
# report may not publish becomes either a blocker or a published falsehood. Two shipped
# on the same run before this existed: a funnel whose first two bars read zero while the
# event feed carried 1.55M injected and 1.54M delivered, and a type-mix donut totalling a
# counter disqualified four sections earlier.
#
# The refusal is an exception rather than a silently dropped spec, because a chart that
# vanishes without a word is how a section ends up describing a canvas that is not there.
# The caller catches it, drops the spec, and says in the appendix which chart was refused
# and why — which is a better appendix than one that does not mention it.
class UnpublishableSpec(ValueError):
    """A chart that cannot be drawn honestly from the values supplied."""

    def __init__(self, name, reason):
        super().__init__(f"{name}: {reason}")
        self.name, self.reason = name, reason


def blocked_values(audit):
    """-> {value: entry} from `audit.contaminated_fields`, for `check_series`.

    Empty when the audit predates the registry, so this is safe to call unconditionally.
    """
    out = {}
    for row in (audit or {}).get("contaminated_fields") or []:
        v = row.get("value")
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out.setdefault(float(v), row)
    return out


def check_series(name, values, blocked, tol=0.0005):
    """Raise if any value, or their total, is a counter the report may not publish.

    The total matters as much as the parts: a composition chart whose slices are fine can
    still sum to the disqualified figure, and that sum is what the tooltip shows.
    """
    nums = [float(v) for v in (values or [])
            if isinstance(v, (int, float)) and not isinstance(v, bool)]
    for candidate, label in [(sum(nums), "total")] + [(v, "value") for v in nums]:
        for bad, entry in (blocked or {}).items():
            if bad and abs(candidate - bad) <= abs(bad) * tol:
                raise UnpublishableSpec(
                    name, f"its {label} is {bad:,.0f}, which is {entry.get('path')} — "
                          f"{entry.get('why') or 'not the authoritative figure'}"
                          + (f". Use {entry['use_instead']}" if entry.get("use_instead")
                             else ""))
    return values


def _kfmt(v, _pos=None):
    v = float(v)
    if abs(v) >= 1_000_000:
        return f"{v/1_000_000:.1f}M".replace(".0M", "M")
    if abs(v) >= 1_000:
        return f"{v/1_000:.0f}k"
    return f"{v:.0f}"


def _style(ax, dateaxis=False, kfmt_y=True):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(length=0)
    ax.set_axisbelow(True)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    if kfmt_y:
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(_kfmt))
    if dateaxis:
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))


def _as_dates(dates):
    if dates and isinstance(dates[0], str):
        return [_dt.date.fromisoformat(d) for d in dates]
    return dates


def _save(fig, out):
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


_CYCLE = [BLUE, INDIGO, MINT, SKY, GREY, LIME]


def timeseries_stacked(dates, series, out, title="", figsize=(11, 3.6), colors=None):
    d = _as_dates(dates)
    colors = colors or _CYCLE
    fig, ax = plt.subplots(figsize=figsize)
    bottom = np.zeros(len(d))
    for i, (name, vals) in enumerate(series.items()):
        vals = np.array(vals, dtype=float)
        ax.bar(d, vals, bottom=bottom, width=0.9, label=name, color=colors[i % len(colors)])
        bottom += vals
    _style(ax, dateaxis=True)
    if title:
        ax.set_title(title, loc="left", pad=12)
    ax.legend(frameon=False, ncol=len(series), loc="upper left", fontsize=9)
    return _save(fig, out)


def area_with_mean(dates, values, out, title="", figsize=(11, 3.6), color=BLUE):
    d = _as_dates(dates)
    v = np.array(values, dtype=float)
    fig, ax = plt.subplots(figsize=figsize)
    ax.fill_between(d, v, color=color, alpha=0.16)
    ax.plot(d, v, color=color, linewidth=2)
    m = float(np.mean(v))
    ax.axhline(m, color=RED, linewidth=1.2, linestyle="--")
    ax.text(d[-1], m, f"  avg {_kfmt(m)}", color=RED, va="center", fontsize=9)
    _style(ax, dateaxis=True)
    if title:
        ax.set_title(title, loc="left", pad=12)
    return _save(fig, out)


def donut(labels, values, out, colors=None, center=None, title="", figsize=(5.2, 5.2)):
    colors = colors or _CYCLE
    fig, ax = plt.subplots(figsize=figsize)
    wedges, _ = ax.pie(values, colors=colors[: len(values)], startangle=90,
                       wedgeprops=dict(width=0.42, edgecolor="white"))
    if center:
        ax.text(0, 0, center, ha="center", va="center", fontsize=18, fontweight="bold", color=INK)
    total = float(sum(values))
    leg = [f"{l}  ({v/total*100:.0f}%)" for l, v in zip(labels, values)]
    ax.legend(wedges, leg, frameon=False, loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize=10)
    if title:
        ax.set_title(title, loc="left", pad=12)
    return _save(fig, out)


def hbar(labels, values, out, title="", color=BLUE, figsize=(11, None)):
    n = len(labels)
    if figsize[1] is None:
        figsize = (figsize[0], max(2.4, 0.5 * n + 1))
    order = np.argsort(values)
    labels = [labels[i] for i in order]
    values = [values[i] for i in order]
    fig, ax = plt.subplots(figsize=figsize)
    ax.barh(range(n), values, color=color, height=0.62)
    ax.set_yticks(range(n))
    ax.set_yticklabels(labels)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(_kfmt))
    for i, v in enumerate(values):
        ax.text(v, i, f" {_kfmt(v)}", va="center", fontsize=9, color=INK)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.tick_params(length=0)
    ax.set_axisbelow(True)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    if title:
        ax.set_title(title, loc="left", pad=12)
    return _save(fig, out)


def grouped_bars(groups, series, out, title="", figsize=(11, 3.8), colors=None):
    colors = colors or _CYCLE
    x = np.arange(len(groups))
    k = len(series)
    w = 0.8 / k
    fig, ax = plt.subplots(figsize=figsize)
    for i, (name, vals) in enumerate(series.items()):
        ax.bar(x + i * w - 0.4 + w / 2, vals, width=w, label=name, color=colors[i % len(colors)])
    ax.set_xticks(x)
    ax.set_xticklabels(groups, rotation=0, fontsize=9)
    _style(ax)
    if title:
        ax.set_title(title, loc="left", pad=12)
    # The legend sits inside the axes, so the tallest bar has to be kept out of its
    # band — otherwise a series label ends up printed over a bar and the chart reads as
    # a rendering fault. Only applied to all-positive series, where "top" is the only
    # edge the legend occupies.
    flat = [float(v) for vals in series.values() for v in vals if v is not None]
    if flat and min(flat) >= 0 and max(flat) > 0:
        ax.set_ylim(0, max(flat) * 1.18)
    ax.legend(frameon=False, ncol=k, loc="upper right", fontsize=9)
    return _save(fig, out)


# ---------------------------------------------------------------------------
# Chart.js spec emitters (JSON-safe dicts; pair each with its matching PNG via
# report_interactive.interactive_chart). Palette matches the matplotlib helpers.
# ---------------------------------------------------------------------------

def stacked_bars(groups, series, out, title="", figsize=(11, 3.8), colors=None,
                 legend_ncol=None):
    """Stacked category bars — the PNG twin of ``spec_grouped_bars(stacked=True)``.

    ``grouped_bars`` puts the series side by side, which answers "which series is
    biggest here"; stacking answers "what is this category made of", and a report
    that shows one on screen and the other in print is telling two stories.
    """
    colors = colors or _CYCLE
    x = np.arange(len(groups))
    fig, ax = plt.subplots(figsize=figsize)
    bottom = np.zeros(len(groups), dtype=float)
    for i, (name, vals) in enumerate(series.items()):
        v = np.array([0.0 if q is None else float(q) for q in vals])
        ax.bar(x, v, width=0.62, bottom=bottom, label=name, color=colors[i % len(colors)])
        bottom += v
    ax.set_xticks(x)
    ax.set_xticklabels(groups, rotation=0, fontsize=9)
    _style(ax)
    if title:
        ax.set_title(title, loc="left", pad=12)
    ax.legend(frameon=False, ncol=legend_ncol or len(series), loc="upper right",
              fontsize=9)
    return _save(fig, out)


def _rgba(hex_color, a):
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{a})"


def _num(seq):
    return [None if v is None else float(v) for v in seq]


def spec_timeseries_stacked(dates, series, colors=None):
    """Stacked daily bars by platform (mirrors timeseries_stacked)."""
    colors = colors or _CYCLE
    datasets = []
    for i, (name, vals) in enumerate(series.items()):
        datasets.append({
            "label": name, "data": _num(vals), "stack": "s", "borderWidth": 0,
            "backgroundColor": colors[i % len(colors)],
        })
    return {
        "type": "bar",
        "data": {"labels": list(dates), "datasets": datasets},
        "options": {
            "responsive": True, "maintainAspectRatio": False,
            "interaction": {"mode": "index", "intersect": False},
            "scales": {"x": {"stacked": True, "grid": {"display": False}},
                       "y": {"stacked": True, "beginAtZero": True}},
            "plugins": {"legend": {"position": "top"}},
        },
    }


def spec_pressure_fatigue(dates, sends, optout_rate=None, open_rate=None,
                          sends_label="Sends", open_rate_label="Open rate %",
                          optout_rate_label="Opt-out rate %", rate_axis_label="Rate %"):
    """Dual-axis: sends (bars, left) vs opt-out & open rates in % (lines, right).

    Highlights the fatigue signal (does pressure erode opens / lift opt-out?).
    Series/axis labels are parameters so a non-English report can localise them.
    """
    datasets = [{
        "type": "bar", "label": sends_label, "data": _num(sends),
        "backgroundColor": _rgba(BLUE, 0.5), "borderWidth": 0,
        "yAxisID": "y", "order": 3,
    }]
    if open_rate is not None:
        datasets.append({"type": "line", "label": open_rate_label, "data": _num(open_rate),
                         "borderColor": MINT, "backgroundColor": MINT, "yAxisID": "y1",
                         "tension": 0.3, "pointRadius": 2, "borderWidth": 2, "order": 1})
    if optout_rate is not None:
        datasets.append({"type": "line", "label": optout_rate_label, "data": _num(optout_rate),
                         "borderColor": RED, "backgroundColor": RED, "yAxisID": "y1",
                         "tension": 0.3, "pointRadius": 2, "borderWidth": 2, "order": 0})
    return {
        "type": "bar",
        "data": {"labels": list(dates), "datasets": datasets},
        "options": {
            "responsive": True, "maintainAspectRatio": False,
            "interaction": {"mode": "index", "intersect": False},
            "scales": {
                "x": {"grid": {"display": False}},
                "y": {"beginAtZero": True, "position": "left",
                      "title": {"display": True, "text": sends_label}},
                "y1": {"beginAtZero": True, "position": "right",
                       "grid": {"display": False},
                       "title": {"display": True, "text": rate_axis_label}},
            },
            "plugins": {"legend": {"position": "top"}},
        },
    }


def spec_funnel(steps, values, attributed=None, total_label="Total",
                attributed_label="Push-attributed", allow_zero_steps=False):
    """Conversion funnel as horizontal bars (view -> cart -> purchase).

    Optionally overlay the push-attributed share per step.

    A funnel step cannot be zero when a step below it is not: nobody opens a message that
    was never delivered. Where that shape appears the endpoint did not answer for the top
    of the funnel, and the chart says the programme delivers nothing and is opened
    840,419 times — which is what shipped once. Such a spec is refused; render the funnel
    as a table from the source that does have the figures. `allow_zero_steps` exists for
    a funnel whose leading step is genuinely unmeasured AND labelled as such in the step
    name, which is a different chart from one that quietly plots zero.
    """
    nums = [float(v or 0) for v in values]
    if not allow_zero_steps:
        last_real = max((i for i, v in enumerate(nums) if v), default=-1)
        empty = [i for i, v in enumerate(nums[:last_real]) if not v]
        if empty:
            names = ", ".join(str(list(steps)[i]) for i in empty)
            raise UnpublishableSpec(
                "funnel", f"step(s) {names} read zero while a later step does not — the "
                          f"source did not answer for the top of the funnel. Render it "
                          f"as a table, or pass allow_zero_steps=True and label the step "
                          f"unmeasured")
    datasets = [{"label": total_label, "data": _num(values),
                 "backgroundColor": _rgba(SKY, 0.9), "borderWidth": 0}]
    if attributed is not None:
        datasets.append({"label": attributed_label, "data": _num(attributed),
                         "backgroundColor": BLUE, "borderWidth": 0})
    return {
        "type": "bar",
        "data": {"labels": list(steps), "datasets": datasets},
        "options": {
            "indexAxis": "y", "responsive": True, "maintainAspectRatio": False,
            "interaction": {"mode": "index", "intersect": False},
            "scales": {"x": {"beginAtZero": True},
                       "y": {"grid": {"display": False}}},
            "plugins": {"legend": {"position": "top"}},
        },
    }


def spec_program_ranking(labels, sends, direct_rate=None, influenced_rate=None,
                         platform_note=None, top=None):
    """Ranked horizontal bars of sends per program/campaign (firehose group ranking).

    direct_rate / influenced_rate (percent) and platform_note (str per bar) are surfaced
    in the hover tooltip via the dataset `_extra` array (no JS in the spec).
    """
    idx = sorted(range(len(labels)), key=lambda i: (sends[i] if sends[i] is not None else 0),
                 reverse=True)
    if top:
        idx = idx[:top]
    labels = [labels[i] for i in idx]
    data = [float(sends[i]) for i in idx]
    extra = []
    for i in idx:
        parts = []
        if direct_rate is not None and direct_rate[i] is not None:
            parts.append(f"Direct {float(direct_rate[i]):.1f}%")
        if influenced_rate is not None and influenced_rate[i] is not None:
            parts.append(f"Influenced {float(influenced_rate[i]):.1f}%")
        if platform_note is not None and platform_note[i]:
            parts.append(str(platform_note[i]))
        extra.append(parts)
    dataset = {"label": "Sends", "data": data, "backgroundColor": _rgba(BLUE, 0.85),
               "borderWidth": 0}
    if any(extra):
        dataset["_extra"] = extra
    return {
        "type": "bar",
        "data": {"labels": labels, "datasets": [dataset]},
        "options": {
            "indexAxis": "y", "responsive": True, "maintainAspectRatio": False,
            "scales": {"x": {"beginAtZero": True},
                       "y": {"grid": {"display": False}}},
            "plugins": {"legend": {"display": False}},
        },
    }


def spec_donut(labels, values, colors=None, center=None, percent=True,
               percent_label="% of total"):
    """Composition donut (mirrors donut()). Legend shows share; tooltip shows value.

    center (str) is shown via the legend title so the whole thing stays JSON-only.
    ``percent_label`` is the tooltip suffix, so a non-English report can localise it.
    """
    colors = colors or _CYCLE
    data = _num(values)
    bg = [colors[i % len(colors)] for i in range(len(data))]
    total = sum(v for v in data if v) or 1.0
    extra = ([f"{(v or 0)/total*100:.1f}{percent_label}" for v in data]
             if percent else None)
    dataset = {"data": data, "backgroundColor": bg, "borderColor": "#fff", "borderWidth": 2}
    if extra:
        dataset["_extra"] = extra
    plugins = {"legend": {"position": "right"}}
    if center:
        plugins["title"] = {"display": True, "text": center, "position": "top"}
    return {
        "type": "doughnut",
        "data": {"labels": list(labels), "datasets": [dataset]},
        "options": {
            "responsive": True, "maintainAspectRatio": False,
            "cutout": "58%",
            "plugins": plugins,
        },
    }


def spec_grouped_bars(groups, series, colors=None, horizontal=False, stacked=False):
    """Clustered (or stacked) category bars (mirrors grouped_bars())."""
    colors = colors or _CYCLE
    datasets = []
    for i, (name, vals) in enumerate(series.items()):
        datasets.append({
            "label": name, "data": _num(vals), "borderWidth": 0,
            "backgroundColor": colors[i % len(colors)],
            **({"stack": "s"} if stacked else {}),
        })
    xy = ({"x": {"stacked": True, "grid": {"display": False}}, "y": {"stacked": True, "beginAtZero": True}}
          if stacked else {"x": {"grid": {"display": False}}, "y": {"beginAtZero": True}})
    return {
        "type": "bar",
        "data": {"labels": list(groups), "datasets": datasets},
        "options": {
            "indexAxis": "y" if horizontal else "x",
            "responsive": True, "maintainAspectRatio": False,
            "interaction": {"mode": "index", "intersect": False},
            "scales": xy,
            "plugins": {"legend": {"position": "top"}},
        },
    }


def spec_hbar(labels, values, color=BLUE, label="Value", extra=None, sort=True):
    """Ranked horizontal bars (mirrors hbar()). `extra` -> per-bar tooltip lines."""
    idx = list(range(len(labels)))
    if sort:
        idx = sorted(idx, key=lambda i: (values[i] if values[i] is not None else 0))
    labs = [labels[i] for i in idx]
    data = _num([values[i] for i in idx])
    dataset = {"label": label, "data": data, "backgroundColor": _rgba(color, 0.85),
               "borderWidth": 0}
    if extra is not None:
        dataset["_extra"] = [extra[i] for i in idx]
    return {
        "type": "bar",
        "data": {"labels": labs, "datasets": [dataset]},
        "options": {
            "indexAxis": "y", "responsive": True, "maintainAspectRatio": False,
            "scales": {"x": {"beginAtZero": True}, "y": {"grid": {"display": False}}},
            "plugins": {"legend": {"display": False}},
        },
    }


if __name__ == "__main__":
    import json as _json
    import tempfile
    d = [(_dt.date(2026, 3, 21) + _dt.timedelta(days=i)).isoformat() for i in range(30)]
    tmp = tempfile.mkdtemp()
    timeseries_stacked(d, {"iOS": np.random.randint(1, 9, 30), "Android": np.random.randint(2, 12, 30)},
                       f"{tmp}/ts.png", title="Daily sends")
    donut(["Direct", "Indirect", "Unattributed"], [40, 25, 35], f"{tmp}/donut.png", center="Attribution")
    hbar(["A", "B", "C", "D"], [120, 340, 90, 510], f"{tmp}/hbar.png", title="Top behaviours")
    # spec emitters must be JSON-serializable
    for spec in (
        spec_timeseries_stacked(d, {"iOS": [1] * 30, "Android": [2] * 30}),
        spec_pressure_fatigue(d, [10] * 30, optout_rate=[0.2] * 30, open_rate=[3.1] * 30),
        spec_funnel(["View", "Cart", "Purchase"], [1000, 400, 120], attributed=[600, 250, 90]),
        spec_program_ranking(["Loyalty", "Drive", "Winback"], [2.3e7, 8e5, 3.5e5],
                             direct_rate=[1.4, 0.6, 2.8], influenced_rate=[8.3, 0.9, 13.1],
                             platform_note=["iOS 9.8M / Android 13.1M", "web", "web"]),
        spec_donut(["Direct", "Indirect", "Unattributed"], [40, 25, 35], center="Attribution"),
        spec_grouped_bars(["Q1", "Q2", "Q3"], {"iOS": [3, 5, 4], "Android": [6, 7, 5]}),
        spec_hbar(["A", "B", "C"], [120, 340, 90], label="Events",
                  extra=["seen 1x", "seen 2x", "seen 3x"]),
    ):
        _json.dumps(spec)

    # --- the two refusals, pinned against the specs that shipped before them
    # the email funnel: 0 injected, 0 delivered, 840,419 opens, 154,451 clicks
    try:
        spec_funnel(["Injected", "Delivered", "Opens", "Clicks"], [0, 0, 840419, 154451])
        raise AssertionError("a funnel with false leading zeros was accepted")
    except UnpublishableSpec as exc:
        assert "Injected, Delivered" in exc.reason, exc.reason
    # a funnel that genuinely tails off to zero is fine, and so is an declared gap
    spec_funnel(["View", "Cart", "Purchase"], [1000, 400, 0])
    spec_funnel(["Injected (unmeasured)", "Opens"], [0, 840419], allow_zero_steps=True)

    # the type-mix donut: slices are innocent, the total is the disqualified counter
    _audit = {"contaminated_fields": [
        {"path": "inventory_stats.by_channel.push.sends", "value": 65_690_965,
         "use_instead": "usage.current.sends_push",
         "why": "responses/list counts every enumerable message"}]}
    _blocked = blocked_values(_audit)
    try:
        check_series("push_type_mix", [40_000_000, 25_690_965], _blocked)
        raise AssertionError("a series totalling a blocked counter was accepted")
    except UnpublishableSpec as exc:
        assert "65,690,965" in exc.reason and "usage.current.sends_push" in exc.reason
    check_series("daily_sends", [40_000_000, 8_316_323], _blocked)
    assert blocked_values({}) == {}, "an audit without the registry blocks nothing"

    print("airship_charts demo + spec emitters OK ->", tmp)
