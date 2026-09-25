#!/usr/bin/env python3
"""Turn a measured gap into a sized opportunity — with its formula and its caveat.

A review that says "iOS converts less well than Android" leaves the reader to work out
whether that is worth a sprint. The same finding sized — "closing it would return about
1.4M opens a month" — is the sentence an account team can act on, and it is arithmetic
the report already has every input for.

The whole risk here is that a projection reads like a measurement. So every function
returns the number, **the formula that produced it**, and **the assumption that has to
hold** — and callers render all three. Nothing in this module reaches outside its
arguments: there is no benchmark lookup, no default volume, no "typical uplift". A figure
this module cannot compute from what it was handed, it declines to compute.

API:
  size_rate_gap(...)          -> dict   # a rate gap, in units of the thing being missed
  size_pressure_headroom(...) -> dict   # distance to the peer median, in sends
  format_sized(op, lang)      -> str    # one plain sentence + its formula and caveat
"""
from __future__ import annotations

from typing import Optional


def _round_sig(x: float, sig: int = 2) -> float:
    """Round to `sig` significant figures — a projection printed to the unit lies."""
    if not x:
        return 0.0
    from math import floor, log10
    return round(x, -int(floor(log10(abs(x)))) + (sig - 1))


def size_rate_gap(*, lagging_label: str, lagging_rate: float, lagging_volume: float,
                  leading_label: str, leading_rate: float,
                  outcome: str = "opens", per: str = "month",
                  months: float = 1.0) -> dict:
    """What the lagging side would gain at the leading side's rate, at its own volume.

    The comparison only means something when the two sides differ in performance and not
    in kind — two platforms of one push programme, two families of one channel. Do not
    use it across mechanics that differ (web against app permission, email against push):
    see the comparability rule in reference.md.

    `lagging_volume` is the lagging side's own volume over the window; `months` converts
    it to a monthly figure. Returns `opportunity: False` when the lagging side is already
    at or above the leading rate — a negative gap is not an opportunity, and a report that
    prints one has inverted its own comparison.
    """
    gap = float(leading_rate) - float(lagging_rate)
    per_window = gap * float(lagging_volume)
    per_month = (per_window / months) if months else None
    ok = gap > 0 and lagging_volume > 0
    return {
        "kind": "rate_gap",
        "opportunity": bool(ok),
        "gap": gap,
        "value": _round_sig(per_month) if (ok and per_month is not None) else None,
        "value_window": _round_sig(per_window) if ok else None,
        "outcome": outcome,
        "per": per,
        "lagging": lagging_label,
        "leading": leading_label,
        "formula": (f"({leading_label} {leading_rate:.1%} \u2212 {lagging_label} "
                    f"{lagging_rate:.1%}) \u00d7 {lagging_volume:,.0f} "
                    f"{lagging_label} sends"
                    + (f" \u00f7 {months:g} months" if months and months != 1 else "")),
        "caveat_en": (f"Assumes the {lagging_label} audience would respond like the "
                      f"{leading_label} one at equal volume. It is a size, not a "
                      f"forecast: it says what the gap is worth, not that closing it "
                      f"is free."),
        "caveat_fr": (f"Suppose que l\u2019audience {lagging_label} r\u00e9agirait comme "
                      f"l\u2019audience {leading_label} \u00e0 volume \u00e9gal. C\u2019est "
                      f"un ordre de grandeur, pas une pr\u00e9vision\u00a0: il dit ce que "
                      f"vaut l\u2019\u00e9cart, pas que le combler soit gratuit."),
    }


def size_pressure_headroom(*, per_month: float, p50: float, opted_in: float,
                           label: str = "push") -> dict:
    """The distance between the account's cadence and the peer median, in sends/month.

    Reads both ways, and the direction decides which sentence is honest. Below the
    median, the gap is unused capacity — sends the account could add before its cadence
    even looks typical. Above it, the same arithmetic is the volume being sent beyond what
    peers send, which is a pressure question, not an opportunity.

    The median is emphatically not a target. It is where half the vertical sits, and an
    account has reasons to sit anywhere in the band — an alerting product belongs high in
    it. Never render this as "should send X more".
    """
    gap = float(p50) - float(per_month)
    sends = abs(gap) * float(opted_in)
    below = gap > 0
    return {
        "kind": "pressure_headroom",
        "below_median": bool(below),
        "gap_per_user_month": gap,
        "value": _round_sig(sends) if opted_in else None,
        "label": label,
        "formula": (f"|{p50:g} (p50) \u2212 {per_month:g} (account)| \u00d7 "
                    f"{opted_in:,.0f} opted-in \u2192 sends/month"),
        "caveat_en": ("The median is where half the vertical sits, not a target. This "
                      "sizes the distance to it" + (
                          "; whether that capacity is worth using depends on having "
                          "something worth sending."
                          if below else
                          ", which is a question about pressure rather than an "
                          "opportunity.")),
        "caveat_fr": ("La m\u00e9diane est le point o\u00f9 se situe la moiti\u00e9 de la "
                      "verticale, pas un objectif. Ceci mesure la distance qui l\u2019en "
                      "s\u00e9pare" + (
                          "\u00a0; reste \u00e0 savoir s\u2019il y a de quoi remplir "
                          "cette capacit\u00e9."
                          if below else
                          ", ce qui est une question de pression et non une "
                          "opportunit\u00e9.")),
    }


# `per` and `outcome` are caller-supplied and end up in the sentence verbatim, so the
# common values are translated here rather than leaking "per month" into a French report.
# An outcome this table does not know is printed as given — pass it already localised.
_UNIT_FR = {"month": "mois", "week": "semaine", "day": "jour", "year": "an",
            "opens": "ouvertures", "clicks": "clics", "conversions": "conversions",
            "leads": "leads", "sends": "envois"}


def format_sized(op: dict, lang: str = "en") -> Optional[str]:
    """One sentence carrying the figure, its formula and its caveat — or None.

    Returns None rather than a hedge when there is no opportunity to state, so a caller
    can drop the line entirely instead of printing "0 additional opens".
    """
    if not op:
        return None
    fr = lang == "fr"
    if fr:
        op = dict(op)
        for k in ("outcome", "per"):
            if op.get(k):
                op[k] = _UNIT_FR.get(str(op[k]).lower(), op[k])
    if op["kind"] == "rate_gap":
        if not op["opportunity"]:
            return None
        v = f"{op['value']:,.0f}".replace(",", "\u202f") if fr else f"{op['value']:,.0f}"
        head = (f"Au taux {op['leading']}, {op['lagging']} rendrait environ "
                f"<b>{v} {op['outcome']} de plus par {op['per']}</b>."
                if fr else
                f"At the {op['leading']} rate, {op['lagging']} would return roughly "
                f"<b>{v} more {op['outcome']} per {op['per']}</b>.")
    elif op["kind"] == "pressure_headroom":
        if not op.get("value"):
            return None
        v = f"{op['value']:,.0f}".replace(",", "\u202f") if fr else f"{op['value']:,.0f}"
        if op["below_median"]:
            head = (f"\u00c0 la cadence m\u00e9diane du secteur, le compte enverrait "
                    f"environ <b>{v} messages {op['label']} de plus par mois</b>."
                    if fr else
                    f"At the vertical's median cadence, the account would send about "
                    f"<b>{v} more {op['label']} messages per month</b>.")
        else:
            head = (f"Le compte envoie environ <b>{v} messages {op['label']} par mois "
                    f"au-del\u00e0 de la cadence m\u00e9diane du secteur</b>."
                    if fr else
                    f"The account sends about <b>{v} {op['label']} messages per month "
                    f"beyond the vertical's median cadence</b>.")
    else:
        return None
    formula = ("Calcul&nbsp;: " if fr else "Formula: ") + op["formula"]
    caveat = op["caveat_fr" if fr else "caveat_en"]
    return f"{head} <span class=\"muted\">{formula}. {caveat}</span>"


if __name__ == "__main__":
    # iOS lagging Android on direct open rate, sized over the iOS send volume.
    g = size_rate_gap(lagging_label="iOS", lagging_rate=0.0797, lagging_volume=257_321_075,
                      leading_label="Android", leading_rate=0.1089, outcome="opens")
    assert g["opportunity"] and g["value"] > 7_000_000
    assert "Android 10.9%" in g["formula"] and "iOS 8.0%" in g["formula"]
    fr_line = format_sized(g, "fr")
    assert "par mois" in fr_line and "ouvertures" in fr_line, "English unit leaked into FR"
    print(fr_line)

    # Already ahead — not an opportunity, and it must not print as a negative one.
    back = size_rate_gap(lagging_label="Android", lagging_rate=0.1089,
                         lagging_volume=1_000, leading_label="iOS", leading_rate=0.0797)
    assert back["opportunity"] is False and format_sized(back, "fr") is None

    # An account far ABOVE the Retail median: the same arithmetic, the other sentence.
    h = size_pressure_headroom(per_month=212.0, p50=8.6, opted_in=1_765_735)
    assert h["below_median"] is False and h["value"] > 3e8
    print(format_sized(h, "fr"))

    # A quiet account, below the median: unused capacity.
    q = size_pressure_headroom(per_month=2.0, p50=8.6, opted_in=100_000, label="push")
    assert q["below_median"] is True
    print(format_sized(q, "en"))
    print("opportunity self-test OK")
