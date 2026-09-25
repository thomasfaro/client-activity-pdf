#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Emit `facts.json` — the small shared numeric brief every section writer must agree with.

`audit.json` is large (466 KB on a recent account) and deliberately shaped by each account:
one carries an alerting/silent reconcile, another carries firehose windows, a third
carries a decoded campaign inventory. That variation is a feature — it is how the review
stays exhaustive — so this script does NOT canonicalise it. It reads it.

What it produces is the opposite: a **tiny, flat, stable** file (a few KB) holding the
handful of numbers the whole report must say the same way — headline KPIs with their
prior-period deltas, the window, the language, the vertical/benchmark set, the brand
vocabulary, and which sections are N/A and why. Two uses:

  * **A brief for section writers.** A section author (human or agent) reads `facts.json`
    plus its own slice of `audit.json` — never `data/*.json`. When several sections are
    written concurrently, this is what stops §4 and §16 quoting the same KPI differently.
  * **A target for the delivery gate.** `verify_report.py` re-reads it and checks that a
    number printed next to a known KPI label really is that KPI's value, which catches a
    class of error the sequential build already produces today.

Because audits differ, every KPI is resolved through a LIST of candidate paths and the
first that yields a number wins; anything unresolved is reported, not silently dropped,
so the caller can pass an override. Nothing here mutates `audit.json`.

    python scripts/build_facts.py work/<client>/audit.json          # writes facts.json
    python scripts/build_facts.py work/<client>/audit.json --verify  # checks an existing one
    python scripts/build_facts.py --selftest
    from build_facts import build_facts; build_facts(AUDIT, na={...})

`--verify` closes the one step the delivery gate never checked. `verify_report.py` compares
the report against `facts.json`; nothing compared `facts.json` against `audit.json`, so a
facts file left behind by an earlier collection was certified rather than caught. Since every
KPI records the audit path it came from, that check costs one dotted lookup per KPI and no
API call at all — see `verify_facts_against_audit`.
"""

import json
import os
import re
import statistics
import sys
import unicodedata

# Each KPI: canonical key, bilingual label, unit, and candidate paths in audit.json.
# Order matters — the first path that resolves to a number wins. Add a path here when a
# new account shapes its audit differently; do not rename an existing key (the gate and
# the section briefs refer to these keys).
KPI_SPECS = [
    {"key": "push_sends", "en": "Push sends (period)", "fr": "Envois push (période)", "unit": "count",
     "alias": [r"(alerting )?push (sent|sends)", r"envois? push", r"push (alertants? )?envoyes?"],
     "cur": ["usage.current.push_sends", "usage.current.sends", "series.sends.current_total",
             "usage.push_sends", "totals.push_sends", "channels.push_blended.period_sends",
             "kpis.push_sends", "wc.send_push"],
     "pri": ["usage.prior.push_sends", "usage.prior.sends", "series.sends.prior_total",
             "prior_period.push_sends", "usage.previous.push_sends", "totals_prior.push_sends",
             "baseline.send_push"]},
    {"key": "email_sends", "en": "Email sends (period)", "fr": "Envois email (période)", "unit": "count",
     "alias": [r"emails? (sent|sends)", r"emails? envoyes?", r"envois? email"],
     "cur": ["usage.current.sends_email", "usage.current.email_sends", "usage.email_sends",
             "channels.channels.email.period_sends", "totals.email_sends", "wc.send_email"],
     "pri": ["usage.prior.sends_email", "usage.prior.email_sends", "prior_period.email_sends",
             "baseline.send_email"]},
    {"key": "opens", "en": "Opens (period)", "fr": "Ouvertures (période)", "unit": "count",
     "alias": [r"(app )?opens", r"ouvertures( d'app)?"],
     "cur": ["usage.current.opens", "usage.current.app_opens",
             "series.opens.current_total", "usage.opens",
             "totals.opens", "kpis.opens", "wc.open_tot"],
     "pri": ["usage.prior.opens", "usage.prior.app_opens",
             "series.opens.prior_total", "prior_period.opens",
             "usage.previous.opens", "baseline.open_tot"]},
    # `usage.*.open_rate` is the APP/PUSH open rate. A bare "open rate" label is not
    # enough to claim it — some accounts label their EMAIL open rate exactly that — so this
    # KPI only matches a qualified label (strict_alias skips the plain-label patterns).
    {"key": "open_rate", "en": "App open rate", "fr": "Taux d'ouverture app", "unit": "pct",
     "alias": [r"(app|push|mobile) open rate", r"open rate \(?(app|push|mobile)\)?",
               r"taux d'ouverture (app|push|mobile)"],
     "strict_alias": True,
     "cur": ["usage.current.open_rate", "rates.open_rate", "usage.open_rate"],
     "pri": ["usage.prior.open_rate", "prior_period.open_rate"]},
    {"key": "direct_open_rate", "en": "Direct open rate", "fr": "Taux d'ouverture direct",
     "unit": "pct",
     "alias": [r"direct open rate( alerting)?", r"taux d'ouverture direct( alertant)?"],
     "cur": ["usage.current.direct_rate", "rates.direct_open_rate", "usage.direct_rate",
             "platform_rates.all.direct_rate", "kpis.direct_open_rate"],
     "pri": ["usage.prior.direct_rate", "prior_period.direct_open_rate"]},
    {"key": "audience_total", "en": "Unique devices (snapshot)", "fr": "Appareils uniques (instantané)",
     "unit": "count",
     "alias": [r"unique (addressable channels|devices)", r"canaux uniques adressables", r"appareils uniques"],
     "cur": ["devices.total_unique_devices", "devices.total_unique", "base.total_unique",
             "base_totals.unique", "devices.push_unique", "audience.total_unique"],
     "pri": []},
    {"key": "app_optin", "en": "App opt-ins (snapshot)", "fr": "Opt-ins app (instantané)", "unit": "count",
     "alias": [r"opted-?in app devices", r"appareils app opt-?in", r"app opt-?ins?"],
     "cur": ["devices.app_optin", "devices.push_optin", "base_totals.opted_in",
             "devices.current.app_optin", "audience.app_optin", "usage.current.app_optin"],
     "pri": ["devices.prior.app_optin", "prior_period.app_optin"]},
    {"key": "web_optin", "en": "Web opt-ins (snapshot)", "fr": "Opt-ins web (instantané)", "unit": "count",
     "alias": [r"opted-?in web browsers", r"navigateurs web opt-?in", r"web opt-?ins?"],
     "cur": ["devices.web_optin", "devices.current.web_optin", "audience.web_optin"],
     "pri": ["devices.prior.web_optin", "prior_period.web_optin"]},
    {"key": "optin_rate", "en": "Opt-in rate", "fr": "Taux d'opt-in", "unit": "pct",
     "alias": [r"opt-?in rate", r"taux d'opt-?in"],
     "cur": ["devices.optin_rate", "devices.push_optin_rate", "devices.optin_blended_mobile",
             "base.optin_rate_blended", "base_totals.optin_rate_blended",
             "rates.optin_rate", "usage.current.optin_rate"],
     "pri": ["devices.prior.optin_rate", "prior_period.optin_rate"]},
    {"key": "optins", "en": "Opt-ins (period)", "fr": "Opt-ins (période)", "unit": "count",
     "alias": [r"opt-?ins", r"opt-?ins periode"],
     "cur": ["usage.current.optins", "usage.current.optin_events",
             "series.optins.current_total", "totals.optins",
             "wc.optin_tot"],
     "pri": ["usage.prior.optins", "usage.prior.optin_events",
             "series.optins.prior_total", "prior_period.optins",
             "baseline.optin_tot"]},
    {"key": "optouts", "en": "Opt-outs (period)", "fr": "Opt-outs (période)", "unit": "count",
     "alias": [r"opt-?outs", r"desabonnements"],
     "cur": ["usage.current.optouts", "usage.current.optout_events",
             "series.optouts.current_total", "usage.optouts",
             "totals.optouts"],
     "pri": ["usage.prior.optouts", "usage.prior.optout_events",
             "series.optouts.prior_total", "prior_period.optouts"]},
    {"key": "pressure", "en": "Messages per opt-in per month",
     "fr": "Messages par opt-in et par mois", "unit": "rate",
     "alias": [r"(alerting )?push / opt-?in( app)? device / month", r"push alertants? / (appareil )?opt-?in( app)? / mois", r"messages? (par|per) opt-?in.*(month|mois)"],
     "cur": ["pressure.app_month", "usage.pressure_per_optin_month", "pressure.per_optin_month",
             "pressure.blended", "pressure.alerting_per_optin_month",
             "pressure.messages_per_optin_month", "pressure_blended"],
     "pri": ["pressure.prior_app_month", "pressure.prior_blended",
             "pressure.prior_per_optin_month", "baseline_pressure_blended"]},
    {"key": "events_total", "en": "Custom events (period)", "fr": "Événements custom (période)", "unit": "count",
     "alias": [r"behaviou?ral events", r"evenements comportementaux", r"custom events"],
     "cur": ["usage.current.events_total", "attribution.total_events_window",
             "events.total", "events.totals.total_count",
             "usage.events_total", "audit_counts.events", "events_total"],
     "pri": ["usage.prior.events_total", "prior_period.events_total", "events.total_prior"]},
    {"key": "events_attributed", "en": "Attributed events (period)", "fr": "Événements attribués (période)",
     "unit": "count",
     "alias": [r"events attributed to a message", r"evenements attribues( a un message)?"],
     "cur": ["attribution.attributed", "attribution.attributed_events",
             "usage.current.events_attributed"],
     "pri": ["attribution.attributed_prior", "prior_period.events_attributed"]},
    {"key": "campaigns_push", "en": "Push campaigns (period)", "fr": "Campagnes push (période)", "unit": "count",
     "alias": [r"push campaigns", r"campagnes push"],
     "cur": ["inventory_stats.push", "inventory_stats.by_channel.push.campaigns",
             "campaigns_push.count", "inventory.push_campaigns",
             "usage.current.campaigns_push", "programs.n_groups"],
     "pri": []},
    {"key": "campaigns_email", "en": "Email campaigns (period)", "fr": "Campagnes email (période)", "unit": "count",
     "alias": [r"email campaigns", r"campagnes email"],
     "cur": ["inventory_stats.email", "inventory_stats.by_channel.email.campaigns",
             "campaigns_email.count", "inventory.email_campaigns"],
     "pri": []},
    {"key": "silent_share", "en": "Silent share", "fr": "Part de push silencieux",
     "unit": "pct",
     "alias": [r"silent share", r"part de push silencieux"],
     "cur": ["alerting_rates.silent_share", "reconciliation.silent_share",
             "reconcile.silent_share", "usage.current.silent_share"],
     "pri": []},
]

# Whether a KPI is COUNTED OVER the window or OBSERVED AT one instant. The distinction is
# invisible in the number and decisive in a tile: a reader who sees "Opt-ins 1,214,000" next
# to "Opted-in devices 3,304,000" reads the first as growth in the second, and it is not —
# one is a flow of permission events over 30 days, the other the base as it stands today. A
# delivered review shipped exactly that pair with neither labelled, and the doctrine against
# it (reference.md, "must never be presented as the base grew by X") had nothing enforcing
# it.
#
# Only `count` KPIs are classified, and only those are gate-checked. A rate is not
# confusable with a base — nobody reads "direct open rate 24%" as a headcount — so tagging
# rates would add noise to every tile without preventing an error, and a check that fires on
# things that are fine is a check people learn to skip.
KPI_TEMPORAL = {
    # flows — counted over the window
    "push_sends": "flow", "email_sends": "flow", "opens": "flow",
    "optins": "flow", "optouts": "flow",
    "events_total": "flow", "events_attributed": "flow",
    "campaigns_push": "flow", "campaigns_email": "flow",
    # snapshots — observed at one instant, from /devices
    "audience_total": "snapshot", "app_optin": "snapshot", "web_optin": "snapshot",
}

# Where the window / language / vertical usually live, in preference order.
_WINDOW = ["period", "meta.period", "window", "meta.window"]
_VERTICAL = ["purpose.vertical", "vertical", "benchmarks.vertical", "audit.vertical"]
_BRAND = ["brand", "meta.brand"]


def dig(obj, path):
    """Resolve a dotted path, returning None on any miss (never raises)."""
    cur = obj
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


_ISO_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


def _as_window(v):
    """Normalise however an audit states its window into ``{"start", "end"}``.

    Accepted: a dict already carrying start/end (under any of the usual key names), a
    ``["2026-07-26", "2026-08-24"]`` pair, or a free-text period such as
    ``"2026-07-26 to 2026-08-24"``. Only requiring a dict — as this did — meant the two
    commonest shapes resolved to None and the report shipped with no window stated
    anywhere, which no check downstream could catch.
    """
    if isinstance(v, dict):
        start = v.get("start") or v.get("from") or v.get("begin")
        end = v.get("end") or v.get("to") or v.get("finish")
        if start and end:
            return {"start": str(start), "end": str(end)}
        return v or None
    if isinstance(v, (list, tuple)) and len(v) >= 2:
        return {"start": str(v[0]), "end": str(v[1])}
    if isinstance(v, str):
        days = _ISO_DAY.findall(v)
        if len(days) >= 2:
            return {"start": days[0], "end": days[-1]}
    return None


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def first(obj, paths):
    """First path resolving to a number -> (value, path); else (None, None)."""
    for p in paths or []:
        v = _num(dig(obj, p))
        if v is not None:
            return v, p
    return None, None


def _delta_pct(cur, pri):
    if cur is None or pri in (None, 0):
        return None
    return round((cur - pri) / abs(pri) * 100, 1)


def _as_pct(v):
    """Normalise a rate to PERCENTAGE POINTS.

    Audits are split on this: some store `open_rate` as 0.674 while other accounts
    store the same idea as 67.4. Reports print percentages, so facts.json always holds
    percentage points and a consumer never has to guess which convention it got. A value
    in [-1, 1] is read as a fraction — a genuine rate above 100 % (influenced responses
    can exceed it) is already in points and passes through.
    """
    if v is None:
        return None
    return round(v * 100, 2) if -1.0 <= v <= 1.0 else round(v, 2)


# A trailing temporal marker, matched while its brackets are still there. Count labels carry
# one so the reader can tell a flow from a snapshot, and the label matcher has to see past it
# — otherwise "Envois push (période)" would stop matching its own KPI card. Kept in step with
# verify_report._TEMPORAL_PAREN_RE.
#
# Only a PARENTHESISED marker is stripped: matching the bare words would fold "Custom events"
# to "custom" and break the events KPI against its own card.
_TEMPORAL_PAREN_RE = re.compile(
    r"\s*\((?:\d+\s*(?:d|j|days?|jours?|mo|months?|mois)"
    r"|periode|period|events?|evenements?|instantanee?|snapshot"
    r"|fenetre|window|a date|aujourd'hui|today)\)\s*$")


def fold(s):
    """Lowercase, strip accents and punctuation — the shared normal form for labels.

    Accents are folded rather than removed so ``Événements`` becomes ``evenements``
    and one ASCII pattern matches both spellings. A trailing ``(période)`` /
    ``(instantané)`` marker is dropped, so a label and its marked variant fold alike.
    """
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("\u2019", "'").replace("\u2018", "'")
    s = _TEMPORAL_PAREN_RE.sub("", s).strip()
    s = re.sub(r"[^a-z0-9'/%\s-]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# How close a regime change has to sit to the window boundary before the period-over-period
# delta stops measuring behaviour and starts measuring the calendar, and how big a step has
# to be to count as a regime change at all (a fraction of the series' own level).
CONTAMINATION_TOLERANCE_DAYS = 7
CONTAMINATION_MIN_STEP = 0.25
# Daily-series key -> the KPI whose card carries its delta. Resolved here rather than in the
# gate so the gate needs no vocabulary of its own: it receives the affected KPI's own label
# patterns and matches cards the same way every other facts check does.
_CONTAMINATION_KEYS = {"send_push": "push_sends", "send_email": "email_sends",
                       "app_opens": "opens", "optout": "optouts", "optin": "optins"}


def _best_split(values, lo, hi):
    """Strongest level change among splits in [lo, hi) -> (index, step).

    `step` is scale-free — the level difference over the two sides' own mean — so one
    threshold serves a series of 158 million and a series of 40.
    """
    best_i, best = None, 0.0
    for i in range(max(1, lo), min(len(values) - 1, hi)):
        ml = statistics.fmean(values[:i])
        mr = statistics.fmean(values[i:])
        scale = (abs(ml) + abs(mr)) / 2 or 1.0
        step = abs(ml - mr) / scale
        if step > best:
            best_i, best = i, step
    return best_i, best


def _deseasonalise(values, period=7):
    """Centred rolling mean over one week, to strip weekly seasonality before splitting.

    Without this, `_best_split` locates the first weekend on any account with a weekday
    rhythm and reports it as a regime change. It is not a marginal effect: on a fleet-card
    account measured here, weekend app opens ran at 2.3k against 9.0k on weekdays, so the
    first Saturday two days into the prior window was the largest level change in the
    series and all four metrics were flagged as "the prior window blends two regimes". The
    delta was fine; the detector was reading the calendar.

    A centred mean of exactly one period cancels a weekly cycle while leaving a genuine
    step almost intact (it spreads it over seven days, which the tolerance already
    absorbs). Series shorter than two periods are returned unchanged — there is no cycle
    to remove and smoothing would only blur the little signal there is.
    """
    n = len(values)
    if n < 2 * period:
        return list(values)
    half = period // 2
    out = []
    for i in range(n):
        a, b = max(0, i - half), min(n, i + half + 1)
        out.append(statistics.fmean(values[a:b]))
    return out


def detect_window_contamination(audit, tolerance=CONTAMINATION_TOLERANCE_DAYS,
                                min_step=CONTAMINATION_MIN_STEP):
    """Flag metrics whose period-over-period delta is really a calendar artefact.

    A review compares a window against the one before it, which only means something if
    the prior window is a stable baseline. Two ways it stops being one, and both are
    tested here because they fail differently:

    * **A break at the boundary.** The level shifts within `tolerance` days of where the
      two windows meet, so the delta measures the shift.
    * **A heterogeneous baseline.** The prior window contains a strong break of its own, so
      its mean is a blend of two regimes and the delta compares the current window against
      an average of things that never coexisted. This is the one that matters in practice
      and the one a global changepoint search misses: on a football account the World Cup
      ended six days before the window opened, and the strongest break in the push series
      sat on 8 July, mid-tournament — so searching for the series' single biggest break
      located a real regime change and answered the wrong question, while the -20.7% push
      and -97.7% email deltas went unflagged.

    Returns one entry per affected metric, so a section qualifies exactly the deltas that
    need it instead of disclaiming the whole report.
    """
    prior = audit.get("daily_prior") or []
    cur = audit.get("daily") or []
    series = list(prior) + list(cur)
    if not prior or not cur or len(series) < 10:
        return {"checked": False,
                "reason": "needs both daily_prior and daily to locate a break"}
    boundary = len(prior)
    dates = [str(r.get("date") or "")[:10] for r in series]
    flagged, clean = [], []
    for key, kpi_key in _CONTAMINATION_KEYS.items():
        vals = [float(r.get(key) or 0) for r in series]
        if not any(vals):
            continue
        # Split on the deseasonalised series; report the raw means, which are what a
        # reader would reconstruct from the report's own daily chart.
        sm = _deseasonalise(vals)
        b_i, b_step = _best_split(sm, boundary - tolerance, boundary + tolerance + 1)
        # inside the prior window only, edges excluded so a boundary break is not counted twice
        p_i, p_step = _best_split(sm, 2, max(3, boundary - tolerance))
        causes = []
        if b_step >= min_step:
            causes.append(f"its level shifts on {dates[b_i]}, "
                          f"{abs(b_i - boundary)} day(s) "
                          f"{'before' if b_i < boundary else 'after'} the boundary")
        if p_step >= min_step:
            causes.append(f"the prior window is not homogeneous — it breaks on "
                          f"{dates[p_i]}, so its mean blends two regimes")
        spec = next((s for s in KPI_SPECS if s["key"] == kpi_key), None)
        rec = {
            "metric": key,
            "kpi_key": kpi_key,
            "label_patterns": _patterns(spec) if spec else [],
            "boundary_at": dates[boundary],
            "boundary_break_at": dates[b_i] if b_i else None,
            "boundary_step": round(b_step, 3),
            "prior_break_at": dates[p_i] if p_i else None,
            "prior_step": round(p_step, 3),
            "prior_window_mean": round(statistics.fmean(vals[:boundary]), 1),
            "current_window_mean": round(statistics.fmean(vals[boundary:]), 1),
        }
        if causes:
            rec["causes"] = causes
            rec["verdict"] = (
                f"`{key}`: " + "; and ".join(causes) +
                ". Its period-over-period delta measures that, so publish it with the "
                "cause named and never as a bare percentage.")
            flagged.append(rec)
        else:
            clean.append(rec)
    return {
        "checked": True,
        "boundary_at": dates[boundary],
        "tolerance_days": tolerance,
        "min_step": min_step,
        "contaminated": flagged,
        "clean": clean,
        "contaminated_metrics": [r["metric"] for r in flagged],
        "verdict": (f"{len(flagged)} metric(s) cannot carry a bare period-over-period "
                    f"delta: {', '.join(r['metric'] for r in flagged)}"
                    if flagged else
                    "the prior window is a homogeneous baseline and no metric breaks near "
                    "the boundary; deltas compare like with like"),
    }


_ZERO_DELIVERY = ["detail_plan.zero_delivery_share", "push_shape.zero_delivery_share",
                  "inventory_stats.zero_delivery_share", "delivery.zero_delivery_share"]
_TOP_500 = ["detail_plan.top_500_share", "push_shape.top_500_share",
            "inventory_stats.top_500_share"]
_TOP_100 = ["detail_plan.top_100_share", "push_shape.top_100_share",
            "inventory_stats.top_100_share"]


def _delivery_concentration(audit):
    """Zero-delivery share and volume concentration, if the audit carries them.

    Read from wherever the account's analyze step put them rather than recomputed here:
    the collector already measures this while ranking messages for enrichment, and a second
    computation on a different row set would produce a second, contradictory number.
    """
    zero, zero_path = first(audit, _ZERO_DELIVERY)
    t500, _ = first(audit, _TOP_500)
    t100, _ = first(audit, _TOP_100)
    if zero is None and t500 is None:
        return {"available": False,
                "reason": "the audit carries no delivery concentration; see "
                          "data/detail_plan.json from the collector"}
    return {
        "available": True,
        "zero_delivery_share": _as_pct(zero) if zero is not None else None,
        "top_100_share": _as_pct(t100) if t100 is not None else None,
        "top_500_share": _as_pct(t500) if t500 is not None else None,
        "source": zero_path,
        "reading": ("a high zero-delivery share with a high mean sends/push is a TARGETING "
                    "problem (messages aimed at nobody); a low one with ~1 send/push is an "
                    "external orchestrator calling the API per recipient. The volume KPI "
                    "looks the same either way."),
    }


# Where each reliability verdict sits. Every account's `analyze.py` is written fresh and
# nests the probe slightly differently — one promotes `mean_sends_per_push` to `push_shape`,
# another leaves it under `push_shape.probe` — so these are candidate lists resolved in
# order, exactly like KPI_SPECS.
_R_PER_PUSH_OK = ["push_shape.probe.per_push_stats_reliable",
                  "push_shape.per_push_stats_reliable", "probe.per_push_stats_reliable"]
_R_PER_PUSH_NOTE = ["push_shape.probe.per_push_stats_note",
                    "push_shape.per_push_stats_note", "probe.per_push_stats_note"]
_R_PER_PUSH_VAL = ["push_shape.probe.mean_sends_per_push", "push_shape.mean_sends_per_push",
                   "probe.mean_sends_per_push"]
_R_SPLIT_OK = ["push_shape.split_sample.publishable", "split_sample.publishable",
               "push_shape.probe.split_sample.publishable"]
_R_SPLIT_COVERAGE = ["push_shape.split_sample.coverage", "split_sample.coverage"]
_R_ACTIVITY_CAVEAT = ["push_shape.activity.caveat", "activity.caveat"]
# rate -> (its drift verdict, its blended value). The drift verdict does not disqualify the
# metric, it disqualifies the MEAN of it: the trend stays publishable and is the answer.
_R_DRIFT = {
    "silent_share": (["push_shape.split_sample.silent_drift",
                      "push_shape.reconcile.silent_drift", "split_sample.silent_drift"],
                     ["push_shape.split_sample.total.silent_share",
                      "push_shape.reconcile.sampled_silent_share",
                      "split_sample.total.silent_share"]),
    "rich_share": (["push_shape.split_sample.rich_drift",
                    "push_shape.reconcile.rich_drift", "split_sample.rich_drift"],
                   ["push_shape.split_sample.total.rich_share",
                    "split_sample.total.rich_share"]),
}
_R_DECLARED = ["unreliable", "withheld", "push_shape.unreliable"]
# What to publish instead. Per metric, because the alternative differs: rich media is
# OBSERVABLE in the decoded bodies, so it has a real substitute, while a silent share drawn
# from too thin a sample has none and the honest move is to say so.
_R_INSTEAD = {
    "silent_share": "nothing — state the sample's coverage and withhold the share, or "
                    "publish the trend if a drift verdict gives one",
    "rich_share": "rich media from the decoded bodies, where it is counted rather than "
                  "sampled",
}


def _firstv(obj, paths):
    """First path resolving to anything at all -> (value, path). `first` wants a number."""
    for p in paths or []:
        v = dig(obj, p)
        if v is not None:
            return v, p
    return None, None


def withheld_metrics(audit):
    """Metrics the collection disqualified itself -> the brief's do-not-publish list.

    The collector already decides this and writes the verdict down: `per_push_stats_reliable`,
    `split_sample.publishable`, a drift verdict saying "report the trend, not the blended
    mean", an activity-log caveat saying the inventory can name campaigns but not count them.
    Until now nothing carried those verdicts forward, so `probe.json` shipped a precise,
    quotable `mean_sends_per_push = 1010.872` sitting one key away from the flag saying it
    describes 1.1% of the account.

    Two accounts got this right anyway, and both prove the point rather than refuting it: a
    human read the raw JSON and hand-wrote a bespoke `unreliable` block. Wave 4 dispatches
    section writers in parallel against a FROZEN BRIEF, and a writer who never sees
    `probe.json` cannot notice a flag that is not in the brief.

    So this publishes the verdict next to the number it disqualifies. A `value` is included
    deliberately: it is how a reader recognises the figure they were about to quote.

    `unreliable` (or `withheld`) in the audit is merged in, so an analyst can disqualify
    something no flag detects without inventing another key nothing reads.
    """
    audit = audit or {}
    out = {}

    def add(metric, value, reason, source, instead=None):
        rec = out.setdefault(metric, {"metric": metric, "value": None, "publish": False,
                                      "reasons": [], "sources": [], "instead": None})
        if value is not None and rec["value"] is None:
            rec["value"] = value
        if reason and reason not in rec["reasons"]:
            rec["reasons"].append(reason)
        if source and source not in rec["sources"]:
            rec["sources"].append(source)
        rec["instead"] = rec["instead"] or instead

    ok, src = _firstv(audit, _R_PER_PUSH_OK)
    if ok is False:
        note, _ = _firstv(audit, _R_PER_PUSH_NOTE)
        val, _ = _firstv(audit, _R_PER_PUSH_VAL)
        add("sends_per_push", val,
            note or "the probe sample is too thin a share of the authoritative sends for a "
                    "per-push statistic to describe the account",
            src, "total volume from /api/reports/sends, and the sample's own coverage")

    ok, src = _firstv(audit, _R_SPLIT_OK)
    if ok is False:
        cov, _ = _firstv(audit, _R_SPLIT_COVERAGE)
        for metric in ("silent_share", "rich_share"):
            val, _ = _firstv(audit, _R_DRIFT[metric][1])
            add(metric, _as_pct(val) if val is not None else None,
                cov or "the sampled pushes carry too small a share of the period's sends "
                       "for their split to describe the account",
                src, _R_INSTEAD.get(metric))

    for metric, (drift_paths, val_paths) in _R_DRIFT.items():
        d, src = _firstv(audit, drift_paths)
        if not (isinstance(d, dict) and d.get("drifting")):
            continue
        val, _ = _firstv(audit, val_paths)
        lo, hi = d.get("min"), d.get("max")
        span = (f" ({_as_pct(lo)}% to {_as_pct(hi)}%, {d.get('direction') or 'moving'})"
                if lo is not None and hi is not None else "")
        add(metric, _as_pct(val) if val is not None else None,
            (d.get("reason") or "the rate is not stable across the window") + span, src,
            "the trend and its breakpoint, not one blended figure")

    caveat, src = _firstv(audit, _R_ACTIVITY_CAVEAT)
    if isinstance(caveat, str) and caveat.strip():
        add("activity_campaign_count", None, caveat, src,
            "the activity log names campaigns; count them from the enumeration or the "
            "programme layer")

    declared, dsrc = _firstv(audit, _R_DECLARED)
    if isinstance(declared, dict):
        for metric, rec in declared.items():
            if not isinstance(rec, dict) or rec.get("publish") not in (False, None):
                continue
            add(metric, rec.get("sampled_value", rec.get("value")),
                rec.get("reason_en") or rec.get("reason") or "declared unreliable by the "
                                                             "analyst",
                f"{dsrc}.{metric}", rec.get("instead"))

    for rec in out.values():
        rec["reason"] = " Also: ".join(rec.pop("reasons"))
        rec["source"] = rec["sources"][0] if rec["sources"] else None
        rec["sources"] = rec["sources"]
    return sorted(out.values(), key=lambda r: r["metric"])


def _patterns(spec):
    """Alias regexes, plus the KPI's own two labels unless the spec is strict.

    ``strict_alias`` exists for KPIs whose plain name is ambiguous in a real report:
    matching a card on a name that could mean another channel's metric would make the
    gate fail an accurate report, which is worse than not checking that KPI at all.
    """
    pats = list(spec.get("alias") or [])
    if not spec.get("strict_alias"):
        pats += [re.escape(fold(spec[k])) for k in ("en", "fr") if spec.get(k)]
    return sorted(set(pats))


def build_facts(audit, na=None, overrides=None, lang=None, client=None, project=None):
    """Reduce an audit.json to the shared numeric brief.

    ``overrides`` pins a KPI the auto-resolution missed or got wrong:
        {"push_sends": {"value": 1234567, "prior": 1000000}}
    ``na`` records sections deliberately marked N/A: {"email_program": "no email traffic"}.
    """
    audit = audit or {}
    overrides = overrides or {}
    kpis, unresolved = [], []

    for spec in KPI_SPECS:
        ov = overrides.get(spec["key"], {})
        if "value" in ov:
            cur, cur_path = ov["value"], "override"
        else:
            cur, cur_path = first(audit, spec["cur"])
        if "prior" in ov:
            pri, pri_path = ov["prior"], "override"
        else:
            pri, pri_path = first(audit, spec["pri"])
        if cur is None:
            unresolved.append(spec["key"])
            continue
        raw_cur, raw_pri = cur, pri
        if spec["unit"] == "pct":
            cur, pri = _as_pct(cur), _as_pct(pri)
        kpis.append({
            "key": spec["key"],
            "label_en": spec["en"], "label_fr": spec["fr"],
            "unit": spec["unit"],
            "temporal": KPI_TEMPORAL.get(spec["key"]),
            "value": cur,
            "prior": pri,
            "delta_pct": _delta_pct(raw_cur, raw_pri),
            "source": cur_path,
            "prior_source": pri_path,
            # Reports label KPIs descriptively ("alerting push sent (30d)"), not by
            # canonical name, so the gate matches on these patterns. They travel INSIDE
            # facts.json: a bespoke label only needs an alias added here, and the gate
            # needs no knowledge of the account.
            "label_patterns": _patterns(spec),
        })

    window = next((_as_window(dig(audit, p)) for p in _WINDOW
                   if _as_window(dig(audit, p))), None)
    vertical = next((dig(audit, p) for p in _VERTICAL if dig(audit, p)), None)
    # `brand` is a bare display name on some accounts and a dict of copy on others
    raw_brand = next((dig(audit, p) for p in _BRAND if dig(audit, p)), None)
    brand = raw_brand if isinstance(raw_brand, dict) else {}
    brand_name = brand.get("name") if brand else (raw_brand if isinstance(raw_brand, str) else None)

    # The audit is deliberately NOT canonicalised, and most accounts group their run
    # identity under `meta` rather than at the root. Reading the root only meant a report
    # shipped with a null project / region / language while the audit stated all three.
    meta = audit.get("meta") if isinstance(audit.get("meta"), dict) else {}

    def _id(field):
        return audit.get(field) or meta.get(field)

    return {
        "client": client or brand_name or _id("client"),
        "project": project or _id("project"),
        "app_key": _id("app_key"),
        "region": _id("region"),
        "window": window,
        "lang": lang or brand.get("lang") or _id("lang"),
        "vertical": vertical if not isinstance(vertical, dict) else vertical.get("key") or vertical,
        "benchmark_set": dig(audit, "benchmarks.vertical") or dig(audit, "benchmarks.set"),
        "vocabulary": {k: v for k, v in brand.items() if isinstance(v, str)} or None,
        "kpis": kpis,
        # Which deltas are calendar artefacts. Carried in the brief because a section author
        # cannot see it in a KPI value, and a bare "-20.7% vs prior period" is wrong in a way
        # no gate on the number itself can catch.
        "window_contamination": detect_window_contamination(audit),
        # Delivery concentration: it separates a targeting problem from an external
        # orchestrator, and both look identical in a volume KPI.
        "delivery_concentration": _delivery_concentration(audit),
        # Figures the collection disqualified itself. In the brief because a section writer
        # working from it never opens probe.json, where the verdict lives next to the number.
        "withheld": withheld_metrics(audit),
        "sections_na": na or {},
        "unresolved_kpis": unresolved,
        "note": "Shared numeric brief. Section writers quote THESE values; the delivery "
                "gate checks the report against them. Anything in `withheld` must NOT be "
                "published as a figure — each entry carries the number it disqualifies and "
                "what to say instead. Pin anything mis-resolved with "
                "build_facts(..., overrides={...}) rather than editing this file by hand.",
    }


def _close(a, b, tol=1e-6):
    """Same number, allowing only float round-trip noise. None matches None alone."""
    if a is None or b is None:
        return a is None and b is None
    scale = max(abs(a), abs(b), 1.0)
    return abs(a - b) <= tol * scale


def verify_facts_against_audit(audit, facts, tol=1e-6):
    """Does every fact still say what the audit says? -> list of discrepancies.

    `verify_report.py` already checks the report against `facts.json`, which leaves the
    step before it unchecked: if `facts.json` is wrong, the gate certifies agreement with
    a wrong source. Every truthiness failure found by hand on the two real accounts was of
    that kind, and each was found *after* twenty minutes of collection.

    Cheap because it re-reads rather than recomputes: `facts.json` records the audit path
    each KPI came from (`source` / `prior_source`), so the check is one `dig` per KPI.

    Five kinds, each a bug class seen for real:

      value           the number at `source` is no longer the number facts publishes —
                      the audit was re-collected and facts was not rebuilt
      dead_source     `source` resolves to nothing at all: the audit's shape changed
      path            `source` is not the FIRST resolving candidate any more. The value can
                      still be right today while the KPI's *definition* has silently moved,
                      which is the failure that survives a value check
      resolvable_now  a KPI facts gave up on, or left without a source, that the audit can
                      answer — facts predates a field the audit gained
      stale_derived   a block facts DERIVES from the audit (contamination, delivery
                      concentration) no longer matches a fresh computation
      missing_derived that block is absent entirely, and a fresh run has something to put in
                      it. Kept apart from `stale_derived` because the consequence differs: an
                      absent contamination block means the gate check that reads it passes
                      vacuously, which is how a report ships unqualified deltas while showing
                      a green gate

    Compared exactly, not within a tolerance. `_facts_coherence` needs slack because the
    HTML shows a rounded value; here both sides pass through the same normaliser, so any
    slack could only hide a real drift. `tol` absorbs float round-trip, nothing more.
    """
    audit, facts = audit or {}, facts or {}
    specs = {s["key"]: s for s in KPI_SPECS}
    out = []

    def add(kind, key, detail):
        out.append({"kind": kind, "key": key, "detail": detail})

    for k in facts.get("kpis") or []:
        key = k.get("key")
        spec = specs.get(key)
        if spec is None:
            add("unknown_kpi", key,
                f"facts publishes '{key}', which is not in KPI_SPECS — facts.json was "
                f"built by another version of this script")
            continue
        pct = spec.get("unit") == "pct"
        for field, src_field, cand in (("value", "source", "cur"),
                                       ("prior", "prior_source", "pri")):
            claimed, path = k.get(field), k.get(src_field)
            if path == "override":
                continue
            if not path:
                got, got_path = first(audit, spec[cand])
                if got is not None:
                    add("resolvable_now", key,
                        f"{field} has no source but the audit answers it at "
                        f"'{got_path}' ({got:,.4g})")
                continue
            raw = _num(dig(audit, path))
            if raw is None:
                add("dead_source", key,
                    f"{field} claims '{path}', which resolves to nothing in this audit")
                continue
            expect = _as_pct(raw) if pct else raw
            if not _close(claimed, expect, tol):
                add("value", key,
                    f"{field} is {claimed!r} but '{path}' holds {expect!r}"
                    + (" (percentage points)" if pct else ""))
            _, best_path = first(audit, spec[cand])
            if best_path and best_path != path:
                add("path", key,
                    f"{field} reads '{path}' but the first resolving candidate is now "
                    f"'{best_path}' — the KPI's definition moved, whatever its value says")

    for key in facts.get("unresolved_kpis") or []:
        spec = specs.get(key)
        if not spec:
            continue
        got, got_path = first(audit, spec["cur"])
        if got is not None:
            add("resolvable_now", key,
                f"listed unresolved, but the audit answers it at '{got_path}' ({got:,.4g})")

    # A derived block can be ABSENT or WRONG, and conflating the two makes the check useless
    # on its first outing: replayed on five real accounts it reported "disagrees" five times
    # when every one of those facts files simply predated the block. Absent is only worth
    # raising when a fresh run has something material to offer, and then the fix is a
    # rebuild, not a contradiction to resolve.
    fresh_c = detect_window_contamination(audit)
    if "window_contamination" not in facts:
        if fresh_c.get("contaminated_metrics"):
            add("missing_derived", "window_contamination",
                f"facts carries no contamination block, so the gate's "
                f"'contaminated deltas name their cause' check has nothing to enforce and "
                f"passes vacuously — while this audit flags "
                f"{sorted(fresh_c['contaminated_metrics'])}. Rebuild facts.json")
    else:
        was_c = facts.get("window_contamination") or {}
        if fresh_c.get("checked"):
            a = set(fresh_c.get("contaminated_metrics") or [])
            b = set(was_c.get("contaminated_metrics") or [])
            if a != b:
                add("stale_derived", "window_contamination",
                    f"a fresh run flags {sorted(a) or 'nothing'} but facts records "
                    f"{sorted(b) or 'nothing'}")
        elif was_c.get("checked"):
            add("stale_derived", "window_contamination",
                "facts records a completed check but this audit no longer carries the daily "
                "series it needs")

    fresh_d = _delivery_concentration(audit)
    if "delivery_concentration" not in facts:
        if fresh_d.get("available"):
            add("missing_derived", "delivery_concentration",
                f"facts carries no concentration block but the audit measures one "
                f"(zero-delivery {fresh_d.get('zero_delivery_share')}%). Rebuild facts.json")
    else:
        was_d = facts.get("delivery_concentration") or {}
        if bool(fresh_d.get("available")) != bool(was_d.get("available")):
            add("stale_derived", "delivery_concentration",
                f"fresh run says available={fresh_d.get('available')}, facts says "
                f"{was_d.get('available')}")
        elif fresh_d.get("available") and not _close(fresh_d.get("zero_delivery_share"),
                                                    was_d.get("zero_delivery_share"), tol):
            add("stale_derived", "delivery_concentration",
                f"zero-delivery share is {fresh_d.get('zero_delivery_share')} in the audit "
                f"but {was_d.get('zero_delivery_share')} in facts")
    return out


def _days(vals, start_day=1):
    """A daily series from a list of values, as audit.json shapes it."""
    return [{"date": f"2026-07-{start_day + i:02d}", "send_push": v}
            for i, v in enumerate(vals)]


def _kpi(source, value, key="push_sends", **kw):
    """One facts.json KPI entry, minimal but shaped like the real thing."""
    return dict({"key": key, "value": value, "prior": None,
                 "source": source, "prior_source": None}, **kw)


def _kinds(diffs):
    return sorted(d["kind"] for d in diffs)


def _selftest():
    """Pin the behaviours that decide what a report is allowed to claim.

    Each case here is a bug that shipped, not a property invented for coverage.
    """
    # --- _best_split: finds the level change, and stays silent when there is none ---
    i, step = _best_split([10] * 10 + [50] * 10, 1, 19)
    assert i == 10 and step > 1.0, (i, step)
    i, step = _best_split([10] * 20, 1, 19)
    assert i is None and step == 0.0, (i, step)

    # --- detect_window_contamination: a break INSIDE the prior window is the one that
    # matters, and it is what a global changepoint search misses. Here the boundary itself is
    # quiet (step 0.23, under the 0.25 floor) while the prior window breaks on day 3.
    het = detect_window_contamination(
        {"daily_prior": _days([400, 400] + [100] * 28),
         "daily": _days([100] * 20, start_day=1)})
    assert het["checked"] and het["contaminated_metrics"] == ["send_push"], het
    rec = het["contaminated"][0]
    assert rec["prior_step"] >= CONTAMINATION_MIN_STEP > rec["boundary_step"], rec
    assert any("not homogeneous" in c for c in rec["causes"]), rec["causes"]

    flat = detect_window_contamination({"daily_prior": _days([100] * 30),
                                        "daily": _days([100] * 20)})
    assert flat["checked"] and not flat["contaminated"], flat
    assert not detect_window_contamination({"daily": _days([100] * 20)})["checked"]

    # --- _delivery_concentration: read from the collector's own measurement, and say so
    # when there is none rather than reporting a silent zero ---
    dc = _delivery_concentration({"detail_plan": {"zero_delivery_share": 0.9405,
                                                  "top_100_share": 0.85,
                                                  "top_500_share": 0.95}})
    assert dc["available"] and dc["zero_delivery_share"] == 94.05, dc
    assert dc["source"] == "detail_plan.zero_delivery_share", dc
    none = _delivery_concentration({})
    assert none["available"] is False and none["reason"], none

    # --- verify_facts_against_audit, one fabricated pair per family ---
    audit = {"usage": {"current": {"push_sends": 100}}}
    assert _kinds(verify_facts_against_audit(
        audit, {"kpis": [_kpi("usage.current.push_sends", 999)]})) == ["value"]
    assert _kinds(verify_facts_against_audit(
        {}, {"kpis": [_kpi("usage.current.push_sends", 100)]})) == ["dead_source"]
    # value right, definition moved: `source` is a later candidate than the one that now
    # resolves first. A value check alone cannot see this.
    both = {"usage": {"current": {"push_sends": 100, "sends": 100}}}
    assert _kinds(verify_facts_against_audit(
        both, {"kpis": [_kpi("usage.current.sends", 100)]})) == ["path"]
    assert _kinds(verify_facts_against_audit(
        audit, {"kpis": [], "unresolved_kpis": ["push_sends"]})) == ["resolvable_now"]
    # an override is the operator overruling resolution on purpose, never a discrepancy
    assert verify_facts_against_audit(
        {}, {"kpis": [_kpi("override", 12345)]}) == []
    # a rate is compared through the same normaliser, so 0.674 in the audit IS 67.4 in facts
    pct_audit = {"engagement": {"open_rate": 0.674}}
    pct_facts = {"kpis": [_kpi("engagement.open_rate", 67.4, key="open_rate")]}
    assert verify_facts_against_audit(pct_audit, pct_facts) == [], \
        verify_facts_against_audit(pct_audit, pct_facts)

    # absent block vs wrong block: the distinction the first replay on real accounts forced.
    # Absent said "disagrees" on five clean files until the two were separated.
    contaminating = {"daily_prior": _days([400, 400] + [100] * 28),
                     "daily": _days([100] * 20)}
    assert _kinds(verify_facts_against_audit(contaminating, {"kpis": []})) \
        == ["missing_derived"]
    stale = {"kpis": [], "window_contamination": {"checked": True,
                                                  "contaminated_metrics": []}}
    assert _kinds(verify_facts_against_audit(contaminating, stale)) == ["stale_derived"]

    # --- withheld_metrics: the verdict has to travel WITH the number it disqualifies ---
    # the real shape from the validation run: 1.1% sample coverage next to a precise
    # 1,010.872 sends/push, which is what a section writer would otherwise have quoted
    thin = {"push_shape": {"probe": {"per_push_stats_reliable": False,
                                     "per_push_stats_note": "sample carries 1.143%",
                                     "mean_sends_per_push": 1010.872}}}
    w = {r["metric"]: r for r in withheld_metrics(thin)}
    assert list(w) == ["sends_per_push"], list(w)
    assert w["sends_per_push"]["value"] == 1010.872, w
    assert w["sends_per_push"]["publish"] is False, w
    assert "1.143%" in w["sends_per_push"]["reason"], w

    # A drift verdict disqualifies the MEAN, not the metric. Figures taken from a real
    # window where the silent share moved 8.2% -> 22.2%: the 15.66% average describes no
    # single day of it, which is exactly the number a section would otherwise quote.
    drift = {"push_shape": {"split_sample": {
        "total": {"silent_share": 0.1566},
        "silent_drift": {"drifting": True, "min": 0.0816, "max": 0.2222,
                         "direction": "rising", "reason": "rate is NOT stable"}}}}
    w = {r["metric"]: r for r in withheld_metrics(drift)}
    assert w["silent_share"]["value"] == 15.66, w
    assert "8.16% to 22.22%" in w["silent_share"]["reason"], w["silent_share"]["reason"]
    assert "trend" in w["silent_share"]["instead"], w
    # a stable rate is not withheld — a registry that flags everything is ignored
    steady = {"push_shape": {"split_sample": {
        "total": {"silent_share": 0.1},
        "silent_drift": {"drifting": False, "min": 0.09, "max": 0.11}}}}
    assert withheld_metrics(steady) == [], withheld_metrics(steady)
    assert withheld_metrics({}) == []

    # an analyst's hand-written block merges with the machine verdict instead of competing
    # with it: this is the bespoke `unreliable` key one account invented, now readable
    merged = dict(drift, unreliable={
        "silent_share": {"sampled_value": 0.1566, "publish": False,
                         "reason_en": "the sample delivered 301 sends in total"},
        "rich_share": {"publish": False, "reason_en": "same denominator"},
        "opens": {"publish": True, "reason_en": "fine, keep it"}})
    w = {r["metric"]: r for r in withheld_metrics(merged)}
    assert sorted(w) == ["rich_share", "silent_share"], sorted(w)
    assert "Also:" in w["silent_share"]["reason"], w["silent_share"]["reason"]
    assert "301 sends" in w["silent_share"]["reason"], w["silent_share"]["reason"]
    assert len(w["silent_share"]["sources"]) == 2, w["silent_share"]["sources"]

    # the activity-log caveat is written only when there IS one, so its presence is the flag
    cav = {"push_shape": {"activity": {"caveat": "page-capped and newest-first"}}}
    assert [r["metric"] for r in withheld_metrics(cav)] == ["activity_campaign_count"]

    # and it reaches the brief, which is the only place a section writer looks
    assert "withheld" in build_facts(thin), sorted(build_facts(thin))
    assert build_facts(thin)["withheld"][0]["value"] == 1010.872

    # --- the invariant build_facts itself must keep: what it just wrote agrees with what it
    # read. Empty by construction today, which is exactly why it catches an edit that
    # stores a value on a different basis than the path it records.
    real = {"usage": {"current": {"push_sends": 1234567}, "prior": {"push_sends": 1000000}},
            "engagement": {"open_rate": 0.0231},
            "daily_prior": _days([100] * 30), "daily": _days([100] * 20)}
    built = build_facts(real)
    assert built["kpis"], "fixture resolved no KPI at all"
    assert verify_facts_against_audit(real, built) == [], \
        verify_facts_against_audit(real, built)

    print("build_facts self-test OK")
    return 0


def _print_diffs(diffs, where):
    """Print what `verify_facts_against_audit` found -> how many it found."""
    if not diffs:
        print(f"  audit coherence OK — {where}")
        return 0
    print(f"  audit coherence: {len(diffs)} discrepancy(ies) — {where}")
    for d in diffs:
        print(f"    [{d['kind']}] {d['key']}: {d['detail']}")
    return len(diffs)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if "--selftest" in flags:
        return _selftest()
    if not args:
        print(__doc__)
        return 1
    src = args[0]
    audit = json.load(open(src, encoding="utf-8"))
    here = os.path.dirname(os.path.abspath(src))

    if "--verify" in flags:
        fp = args[1] if len(args) > 1 else os.path.join(here, "facts.json")
        facts = json.load(open(fp, encoding="utf-8"))
        return 1 if _print_diffs(verify_facts_against_audit(audit, facts),
                                 f"{os.path.basename(fp)} against "
                                 f"{os.path.basename(src)}") else 0

    facts = build_facts(audit)
    out = args[1] if len(args) > 1 else os.path.join(here, "facts.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(facts, fh, ensure_ascii=False, indent=1)
    print(f"{out} — {len(facts['kpis'])} KPI resolved, "
          f"{len(facts['unresolved_kpis'])} unresolved"
          + (f" ({', '.join(facts['unresolved_kpis'])})" if facts["unresolved_kpis"] else ""))
    for k in facts["kpis"]:
        d = f"{k['delta_pct']:+.1f}%" if k["delta_pct"] is not None else "—"
        print(f"  {k['key']:<20} {k['value']:>14,.2f}  {d:>8}   <- {k['source']}")
    # On a pair this script just produced, this is empty BY CONSTRUCTION — which is the
    # point: it fires when an edit to build_facts breaks that construction (storing a
    # rounded value while `source` still points at the raw one, reordering a candidate
    # list). The check earns its keep against a facts.json built EARLIER, via --verify.
    _print_diffs(verify_facts_against_audit(audit, facts), "freshly built pair")
    return 0


if __name__ == "__main__":
    sys.exit(main())
