#!/usr/bin/env python3
"""Airship-branded matplotlib chart helpers.

Import these from a per-report script. They encode the Airship palette, a k/M tick
formatter, clean spines, and dated x-axes for TIME SERIES ONLY (applying a date
locator to a bar/category chart raises "too many ticks" — so `dateaxis` is opt-in).
Do not put emoji in labels (missing-glyph warnings / blank boxes).

Palette (see reference.md): INK #16161D, RED #E7233E, INDIGO #3D2CE0,
BLUE #2A5BD7, MINT #12B886, GREY #6A6A82, LIGHT #F5F5F7, GRID #E5E5EC.

Functions (each saves a PNG and returns the path):
  timeseries_stacked(dates, series:dict, out, title=...)   # daily stacked bars (e.g. ios/android)
  area_with_mean(dates, values, out, title=...)            # area + mean line
  donut(labels, values, out, colors=None, center=None)     # composition
  hbar(labels, values, out, title=..., color=RED)          # ranked horizontal bars
  grouped_bars(groups, series:dict, out, title=...)         # clustered category bars

Deps: matplotlib, numpy.
"""
import datetime as _dt

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

INK = "#16161D"
RED = "#E7233E"
INDIGO = "#3D2CE0"
BLUE = "#2A5BD7"
MINT = "#12B886"
GREY = "#6A6A82"
LIGHT = "#F5F5F7"
GRID = "#E5E5EC"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
    "text.color": INK,
    "axes.edgecolor": GREY,
    "axes.labelcolor": INK,
    "xtick.color": GREY,
    "ytick.color": GREY,
    "axes.titlesize": 15,
    "axes.titleweight": "bold",
    "figure.dpi": 160,
})


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


_CYCLE = [RED, INDIGO, BLUE, MINT, GREY, "#E8B53A"]


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


def hbar(labels, values, out, title="", color=RED, figsize=(11, None)):
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
    ax.legend(frameon=False, ncol=k, loc="upper right", fontsize=9)
    return _save(fig, out)


if __name__ == "__main__":
    import tempfile
    d = [(_dt.date(2026, 3, 21) + _dt.timedelta(days=i)).isoformat() for i in range(30)]
    tmp = tempfile.mkdtemp()
    timeseries_stacked(d, {"iOS": np.random.randint(1, 9, 30), "Android": np.random.randint(2, 12, 30)},
                       f"{tmp}/ts.png", title="Daily sends")
    donut(["Direct", "Indirect", "Unattributed"], [40, 25, 35], f"{tmp}/donut.png", center="Attribution")
    hbar(["A", "B", "C", "D"], [120, 340, 90, 510], f"{tmp}/hbar.png", title="Top behaviours")
    print("demo charts in", tmp)
