#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Plausibility check on `audit.json`, BEFORE charts and sections consume it.

    python scripts/verify_audit.py work/<client>/audit.json
    python scripts/verify_audit.py --selftest

Run it between wave 2 and wave 3, next to `build_facts.py --verify`.

Why this exists, and why it is not the delivery gate. `verify_report.py` compares the
report to `facts.json`, and `build_facts.py --verify` compares `facts.json` to
`audit.json`. Both check *agreement*. Neither asks whether the audit is plausible in the
first place, so an audit that is internally consistent and wrong propagates all the way
to a delivered report with every check green.

On the run that motivated this file, three such defects were each found in wave 5, after
fifteen sections had been written against them. All three were detectable from
`audit.json` alone, in under a second, before a single chart existed. That is the whole
argument: these checks are cheap, and the thing they buy is not correctness at the end
but *not having to redo the middle*.

Each check is a real failure, not a hypothetical:

  bands       a benchmark transcribed by hand carried only the median, so every gauge
              could plot a point against a point. `analysis-spec.md` requires p10-p90
              gauges and the gate checks a verdict against its band -- but nothing
              checked the band existed.

  volume      a key-name mismatch (`sends` vs `total_sends`) zeroed every volume-weighted
              field at once. The account read 96.8% automated by campaign count and 6.8%
              by volume; with the volume side zeroed there was nothing to contradict the
              count, and the wrong figure is the plausible-looking one.

  pressure    marketing pressure computed from the all-channel send total rather than
              push alone. `/api/reports/sends` returns every platform including email,
              which is documented as a capability and reads as a total. On that account
              it overstated pressure by 29%.

  identity    a run identity kept under `meta` resolved to null, which silently disables
              every Flight Deck deep link and leaves the report with no window stated.

Exit code 1 if any REQUIRED check fails, else 0. Advisories never fail the run.
"""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# Rates in the benchmark book are fractions; an audit stores them in points. Only the
# SHAPE is checked here, never the magnitude, so no rescaling is needed.
_BAND_KEYS = ("p10", "p50", "p90")

# `benchmarks` also carries provenance and the matched vertical, which are not metrics.
_BENCH_META = {"vertical", "set", "basis", "disclose", "source", "note", "notes"}


def _num(v):
    """A real number, excluding bool (which is an int in Python and never a measurement)."""
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


# ---------------------------------------------------------------------------
# bands
# ---------------------------------------------------------------------------
def check_benchmark_bands(audit) -> list:
    """-> list of complaints. A benchmark destined for a gauge must be a band."""
    out = []
    bench = audit.get("benchmarks")
    if not isinstance(bench, dict):
        return ["benchmarks: absent — no metric can be positioned against its vertical"]

    for metric, val in bench.items():
        if metric in _BENCH_META or val is None:
            continue
        if not isinstance(val, dict):
            # A metric stated as a bare number cannot carry a peer band at all.
            if _num(val) is not None:
                out.append(f"benchmarks.{metric}: a bare number ({val}) where a "
                           f"p10/p50/p90 band belongs")
            continue
        for dev, band in val.items():
            if band is None:
                continue  # genuinely not published for that device family
            if _num(band) is not None:
                out.append(f"benchmarks.{metric}.{dev}: a bare number ({band}) where a "
                           f"p10/p50/p90 band belongs — a gauge can only plot a point "
                           f"against a point")
            elif isinstance(band, dict):
                missing = [k for k in _BAND_KEYS if _num(band.get(k)) is None]
                if missing and len(missing) < len(_BAND_KEYS):
                    out.append(f"benchmarks.{metric}.{dev}: band missing "
                               f"{', '.join(missing)} — the median alone draws no band")
    return out


# ---------------------------------------------------------------------------
# volume
# ---------------------------------------------------------------------------
def _all_zero(d) -> bool:
    """True when a dict holds at least one number and every number is zero."""
    nums = [_num(v) for v in d.values() if _num(v) is not None]
    return bool(nums) and not any(nums)


def _any_nonzero(d) -> bool:
    return any(_num(v) for v in d.values() if _num(v) is not None)


def check_volume_weighted(audit) -> list:
    """-> complaints where a volume-weighted block is zero beside a populated count.

    Generic on purpose. The bug it catches is a key-name mismatch between a producer and
    a consumer, which is not specific to one field and will not announce itself: there is
    no exception, only a zero that reads as "this account has no send volume".
    """
    out = []

    def walk(node, path):
        if isinstance(node, dict):
            # sibling by_count / by_sends, the shape automation_mix uses
            counts = [k for k in node if "by_count" in k]
            sends = [k for k in node if "by_sends" in k]
            for ck in counts:
                for sk in sends:
                    c, s = node.get(ck), node.get(sk)
                    if isinstance(c, dict) and isinstance(s, dict) \
                            and _all_zero(s) and _any_nonzero(c):
                        out.append(
                            f"{path}.{sk}: every value is zero while {ck} is populated "
                            f"— a volume-weighted mix of nothing, beside a count that "
                            f"reads as a finding")
            for k, v in node.items():
                walk(v, f"{path}.{k}" if path else k)
        elif isinstance(node, list):
            rows = [r for r in node if isinstance(r, dict)]
            if rows:
                # a table of rows carrying both a count and a send volume per row
                for cf in ("campaigns", "count", "messages"):
                    for sf in ("sends", "total_sends"):
                        if any(cf in r for r in rows) and any(sf in r for r in rows):
                            cvals = [_num(r.get(cf)) or 0 for r in rows]
                            svals = [_num(r.get(sf)) or 0 for r in rows]
                            if any(cvals) and not any(svals):
                                out.append(
                                    f"{path}[].{sf}: zero across all {len(rows)} rows "
                                    f"while {cf} is populated — the volume weighting is "
                                    f"not wired up")
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")

    walk(audit, "")
    # A generic walk can reach the same finding by two routes; keep the order stable.
    return sorted(set(out))


# ---------------------------------------------------------------------------
# pressure
# ---------------------------------------------------------------------------
def check_pressure_basis(audit) -> list:
    """-> complaints where marketing pressure was computed from all-channel volume.

    Arithmetic rather than trusting a label: recompute the monthly ratio from the
    push-only total and from the all-channel total, and see which one the stored value
    actually matches. A 29% overstatement is invisible in isolation and obvious here.
    """
    p = audit.get("pressure")
    if not isinstance(p, dict):
        return []
    stored = _num(p.get("per_optin_month"))
    optin = _num(p.get("opted_in_devices")) or _num((audit.get("devices") or {}).get("app_optin"))
    days = _num(p.get("window_days")) or 30
    push = (_num(p.get("push_sends_series_total")) or _num(p.get("alerting_sends"))
            or _num(((audit.get("series") or {}).get("sends") or {}).get("current_total")))
    allch = _num((audit.get("push_shape") or {}).get("all_channel_sends_window"))
    if not (stored and optin and push and allch and days):
        return []
    if allch <= push:
        return []  # single-channel account: the two totals coincide, nothing to confuse

    scale = 30.0 / days
    push_ratio = push / optin * scale
    all_ratio = allch / optin * scale
    if abs(stored - all_ratio) < abs(stored - push_ratio):
        return [f"pressure.per_optin_month = {stored:g} matches the ALL-CHANNEL total "
                f"({all_ratio:.2f}) rather than push-only ({push_ratio:.2f}) — "
                f"/api/reports/sends spans email too, so pressure is overstated by "
                f"{(all_ratio / push_ratio - 1) * 100:.0f}%"]
    return []


# ---------------------------------------------------------------------------
# silent zeros
# ---------------------------------------------------------------------------
def _collect_lists(audit, key) -> list:
    """Every list stored under `key`, flattened, wherever it sits in the audit."""
    out, stack = [], [audit]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            v = node.get(key)
            if isinstance(v, list):
                out.extend(r for r in v if isinstance(r, dict))
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return out


def check_suspect_zeros(audit) -> list:
    """-> complaints where a detail endpoint returned zeros the inventory contradicts.

    Collection flags these; this is the gate that stops one reaching a table. A zero here
    is not a small error, it is the difference between "this programme sent 6,968
    messages" and "this programme sent none", with nothing in the payload to tell them
    apart.
    """
    rows = _collect_lists(audit, "suspect_zero_details")
    if not rows:
        return []
    rows.sort(key=lambda r: -(_num(r.get("inventory_volume")) or 0))
    worst = rows[0]
    ids = ", ".join(str(r.get("id"))[:8] for r in rows[:4])
    return [f"{len(rows)} id(s) carry all-zero counters although the inventory saw them "
            f"deliver (largest: {_num(worst.get('inventory_volume')) or 0:,.0f} on "
            f"{worst.get('endpoint')}; {ids}) — the API returns 200 with zeros for an id "
            f"of a type the endpoint cannot serve, and for a window that has not settled. "
            f"Fix: resolve each on the endpoint matching its id type, or drop it from the "
            f"audit. Never publish the zero."]


# ---------------------------------------------------------------------------
# consolidation
# ---------------------------------------------------------------------------
def check_settling(audit) -> list:
    """-> complaints where the window runs past the point reporting data has settled.

    An unsettled window does not fail: the API answers `200` with zeros, and a section
    reads them as "this message reached nobody". Measured on three projects, the device
    snapshot closes at yesterday, so this fires only when the window includes today —
    which is a real mistake, not a false positive, and is fixed by moving `--end` back.
    """
    s, where = _find(audit, "settling")
    if not s or not s.get("ends_after_watermark"):
        return []
    days = _num(s.get("days_past_watermark")) or 0
    return [f"{where}: the window ends {s.get('window_end')} but reporting data is only "
            f"closed to {str(s.get('date_closed') or '')[:10]}"
            + (f" ({days:g}d past it)" if days else "")
            + " — the tail returns 200 with zeros that are not real zeros. Fix: re-run "
              "collection with --end at or before the watermark, or wait for the day to "
              "close. Do not deliver rates computed across an unsettled tail."]


# ---------------------------------------------------------------------------
# rich overlap
# ---------------------------------------------------------------------------
# Below this the interval is narrower than the rounding a section would apply anyway.
_RICH_TOL_PCT = 1.0


def _find(audit, key):
    """First value stored under `key` anywhere in the audit, with its path.

    The audit is assembled by hand from the collected stages, so the block can sit under
    `activity`, under `push_shape`, or at the root. Guarding on one path would make this
    check silently inapplicable the first time the shape moved.
    """
    stack = [(audit, "")]
    while stack:
        node, path = stack.pop(0)
        if isinstance(node, dict):
            if isinstance(node.get(key), dict):
                return node[key], (f"{path}.{key}" if path else key)
            for k, v in node.items():
                stack.append((v, f"{path}.{k}" if path else k))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                stack.append((v, f"{path}[{i}]"))
    return None, None


def _paths_holding(audit, target) -> list:
    """Every path whose value equals `target` — used to name the figure at risk.

    The registry is skipped, and that is not cosmetic. `main()` writes this function's
    own output back into `audit.contaminated_fields`, where each record stores the value
    it disqualifies so a reader recognises the figure. Scanning that back in makes every
    run report its own previous output as fresh stray copies: on one account three
    findings became twelve on the second invocation, and the count would keep climbing.
    A registry entry is a record OF the problem, never an instance of it.
    """
    out, stack = [], [(audit, "")]
    while stack:
        node, path = stack.pop(0)
        if isinstance(node, dict):
            for k, v in node.items():
                p = f"{path}.{k}" if path else k
                if p == "contaminated_fields":
                    continue
                if _num(v) == target:
                    out.append(p)
                else:
                    stack.append((v, p))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                p = f"{path}[{i}]"
                if _num(v) == target:
                    out.append(p)
                else:
                    stack.append((v, p))
    return out


def check_rich_overlap(audit) -> list:
    """-> advisory complaints where reach is stated as exact despite the `rich` overlap.

    `rich` is not a subset of `alerting` — 9 of 217 production activity rows carry
    `rich > alerting`, one of them at `alerting=0, silent=0, rich=6`. So summing the app
    delivery components double-counts every device that was both notified and given an
    inbox copy, and reach is an interval rather than a number. Airship has not yet
    confirmed whether the notified audience is contained in the inbox audience, so this
    reports the width of the interval instead of picking an end of it.
    """
    ov, where = _find(audit, "rich_overlap")
    if not ov:
        return []
    out = []
    pct = _num(ov.get("max_overstatement_pct"))
    additive = _num(ov.get("additive_total"))
    bound = _num(ov.get("reach_bound_total"))

    if None not in (pct, additive, bound) and pct >= _RICH_TOL_PCT:
        out.append(f"{where}: reach lies in [{bound:,.0f}, {additive:,.0f}] — the two "
                   f"defensible totals differ by {pct:g}% because `rich` overlaps "
                   f"`alerting` by an unknown amount "
                   f"({ov.get('rows_rich_gt_alerting')} of {ov.get('rows')} rows carry "
                   f"rich > alerting). State the interval, or state one end and say "
                   f"which.")
        published = [p for p in _paths_holding(audit, additive)
                     if not p.startswith(f"{where}.")]
        if published:
            out.append(f"{', '.join(published[:4])}: equal to the ADDITIVE total, which "
                       f"is the upper bound of that interval, not a measurement")

    # Reported independently of the overlap gap. On an account whose Message Center
    # drops never notify, `alerting` is zero on those rows so the two totals agree
    # exactly and the gap is 0 — while a large share of the inventory is still made of
    # messages that read as `sends: 0` everywhere else. Measured: 231 of 504 rows.
    inbox = _num(ov.get("rows_inbox_only"))
    if inbox:
        rows = _num(ov.get("rows")) or 0
        out.append(f"{where}.rows_inbox_only = {inbox:,.0f}"
                   + (f" of {rows:,.0f}" if rows else "")
                   + " — Message Center drops with no notification, whose entire reach "
                     "is in `rich`. Their `sends: 0` is correct; quote `rich_sends` for "
                     "their volume and do not count them as campaigns that reached "
                     "nobody")
    return out


# ---------------------------------------------------------------------------
# identity
# ---------------------------------------------------------------------------
# Split by consequence, not by tidiness. A missing client or window is a report that
# cannot state what it describes; a missing app_key is a report whose Flight Deck links
# are absent without an error anywhere.
_ID_REQUIRED = ("client", "window")
_ID_ADVISORY = ("project", "app_key", "region", "lang")


def check_identity(audit) -> tuple:
    """-> (required complaints, advisory complaints).

    Resolved through `build_facts` itself rather than a second list of candidate paths,
    so this cannot drift away from the resolver it is meant to guard.
    """
    try:
        import build_facts
        facts = build_facts.build_facts(audit)
    except Exception as exc:                                  # noqa: BLE001
        return ([f"identity: build_facts could not read this audit ({exc})"], [])

    req = [f"{f}: unresolved — the report cannot state what it describes"
           for f in _ID_REQUIRED if not facts.get(f)]
    adv = []
    for f in _ID_ADVISORY:
        if facts.get(f):
            continue
        why = ("every Flight Deck deep link will be silently absent"
               if f in ("app_key", "region") else "falls back to a default")
        adv.append(f"{f}: unresolved — {why}")
    return (req, adv)


# ---------------------------------------------------------------------------
# contaminated fields
# ---------------------------------------------------------------------------
# Two counters in every audit are larger than the account's push volume and look exactly
# like it. `responses/list` totals every enumerable message including the ones the
# window's send endpoint does not count that way, and the all-channel total adds email
# and SMS. Both are legitimate where they sit; both are wrong in a sentence about push.
#
# On the run that motivated this, five separate fields carried the responses/list total
# and each was found by hand, days apart, the last one while writing the final appendix.
# There is no reason for that to be manual: the values are equal, so they are findable.
# The registry below is written into the audit before the freeze, and the section
# checker and the chart writer both read it, so a field caught once is caught for good.
_CONTAM_TOL = 0.0005          # equal to within half of one tenth of a percent

# In-app campaigns report button presses under a key named `sends`. It is not a volume
# and no ratio will reveal that, so it is matched by path rather than by value. Only the
# `by_channel` leaf: the bare `inventory_stats.in_app` beside it is a campaign count.
_TAP_COUNT_SUFFIXES = ("by_channel.in_app.sends",)

_PUSH_VOLUME_PATHS = ("usage.current.sends_push",
                      "series.sends.current_total",
                      "pressure.push_sends_series_total")


def _dig(node, path):
    for part in path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def _authoritative_push_sends(audit):
    for p in _PUSH_VOLUME_PATHS:
        v = _num(_dig(audit, p))
        if v:
            return v, p
    return None, None


def contaminated_fields(audit) -> list:
    """-> registry of every field a section must not read as push volume.

    Each entry names the path, the value, how far it sits from the authoritative figure,
    and what to read instead. `canonical` marks the field where the number legitimately
    lives: it is still unpublishable as volume, but it is not a stray copy.
    """
    push, push_path = _authoritative_push_sends(audit)
    reconcile = audit.get("reconcile") or {}
    out, seen = [], set()

    sources = [
        (_num(reconcile.get("responses_list_sends")), "responses_list",
         "reconcile.responses_list_sends",
         "responses/list counts every enumerable message, including ones the window's "
         "send endpoint does not count as push"),
        (_num(reconcile.get("reports_sends")), "all_channel", "reconcile.reports_sends",
         "the send endpoint returns every platform, so this total is push plus email "
         "and SMS — a different denominator, not a larger push figure"),
    ]
    for value, kind, canonical, why in sources:
        if not value or (push and abs(value - push) <= push * _CONTAM_TOL):
            continue
        for path in _paths_holding(audit, value):
            if path in seen:
                continue
            seen.add(path)
            out.append({
                "path": path,
                "value": value,
                "kind": kind,
                # A `withheld` record holds the disqualified number on purpose, to say
                # what was refused. It is not a stray copy waiting to be published.
                "canonical": path == canonical or path.startswith("withheld."),
                "ratio_to_authoritative": (round(value / push, 4) if push else None),
                "use_instead": push_path,
                "why": why,
            })

    for path in _paths_holding_any_number(audit):
        if path in seen or not path.endswith(_TAP_COUNT_SUFFIXES):
            continue
        seen.add(path)
        out.append({
            "path": path,
            "value": _num(_dig(audit, path)),
            "kind": "tap_count",
            "canonical": True,
            "ratio_to_authoritative": None,
            "use_instead": None,
            "why": "in-app campaigns report button presses under this key, not "
                   "deliveries — it is neither a send count nor a reach figure",
        })

    out.sort(key=lambda r: (r["kind"], r["path"]))
    return out


def _paths_holding_any_number(audit) -> list:
    """Every path whose value is a number — used for the path-matched rules above."""
    out, stack = [], [(audit, "")]
    while stack:
        node, path = stack.pop(0)
        if isinstance(node, dict):
            items = [(f"{path}.{k}" if path else k, v) for k, v in node.items()
                     if k != "contaminated_fields" or path]
        elif isinstance(node, list):
            items = [(f"{path}[{i}]", v) for i, v in enumerate(node)]
        else:
            continue
        for p, v in items:
            if _num(v) is not None:
                out.append(p)
            else:
                stack.append((v, p))
    return out


# ---------------------------------------------------------------------------
# vertical resolution
# ---------------------------------------------------------------------------
# Three resolvers read a vertical, and until now only one of them said when it had not
# found what it was asked for. `resolve_vertical.resolve()` returns `proxy` + a disclose
# sentence, which is why the benchmark section discloses its proxy correctly on every
# account. The event catalogue computed a `fallback` flag that nothing read, and the
# campaign playbook returned the unmatched input verbatim, which reads like success.
_VERT_PATHS = (
    ("event catalogue (gap analysis, conversion detection)",
     ("events.analysis.vertical", "events.analysis.vertical.fallback_all_verticals"),
     "the recommended-event list comes from `all_verticals`, which is retail-shaped: a "
     "publisher gets told to track `added_to_cart`, `purchased` and loyalty tiers"),
    ("campaign playbook (lever relevance, pillar stakes, recommendations)",
     ("purpose.vertical",),
     "every lever scores on its `base` instead of its vertical relevance, so "
     "`recommend_campaigns` reorders, and `stake_for` returns no business stake for any "
     "pillar of the maturity matrix"),
)


def check_vertical_resolution(audit) -> list:
    """-> complaints where a catalogue or playbook silently fell back.

    This is a wrong-report check rather than a missing-data one, and that is why it
    blocks. Nothing raises, nothing empties, and the output looks complete: what changes
    is WHICH events are recommended and in WHAT ORDER the levers rank. A review shipped a
    retail gap list to an ad-funded news publisher because its vertical was written as a
    display label, and the only reason it was caught is that a human read the list and
    recognised `added_to_cart` as absurd for a newspaper.

    The fix is never to edit the label a report prints. It is to pass the BOOK KEY to the
    catalogue and the playbook, and keep the display label for the page.
    """
    out = []
    for what, paths, consequence in _VERT_PATHS:
        node = None
        for p in paths:
            node = _dig(audit, p)
            if isinstance(node, dict):
                break
        if not isinstance(node, dict):
            continue                         # this layer did not run on this account
        fell_back = bool(node.get("fallback") or node.get("fallback_all_verticals")) \
            or node.get("known") is False
        if not fell_back:
            continue
        # Asking FOR the cross-vertical book is a decision, not a fallback. The catalogue
        # raises its flag on `book_key == "all_verticals" and bool(vertical)`, which is
        # true for the literal input "all verticals" too — and an account with no close
        # peer set is entitled to say so. Only a request that MISSED is a finding.
        asked = str(node.get("input") or "").strip().lower().replace(" ", "_")
        if asked in ("", "all_verticals", "none"):
            continue
        out.append(
            f"{what}: asked for {node.get('input')!r}, resolved to "
            f"{node.get('book_key')!r} by falling back — {consequence}. Fix: pass the "
            f"book key (`resolve_vertical.resolve(...)['key']`, e.g. 'media') to "
            f"event_analysis.analyze / campaign_purpose.analyze / data_foundation.load, "
            f"and keep the display label for meta.vertical only")
    return out


# ---------------------------------------------------------------------------
# prior pairing
# ---------------------------------------------------------------------------
# Segments and prefixes that mark WHICH WINDOW a value describes rather than WHAT it
# measures. Stripping them leaves the metric's identity, which is what the current and
# the prior value have to agree on.
_WINDOW_WORDS = ("current", "prior", "previous", "baseline")


def _metric_identity(path):
    """`pressure.prior_app_month` -> ('pressure', 'app_month'). Window words removed.

    The point is to separate the two things a resolved path carries: the block it lives
    in, and the metric it names. A prior is allowed to live under a different key; it is
    not allowed to name a different metric.
    """
    if not path or path == "override":
        return None, None
    parts = [p for p in path.split(".") if p not in _WINDOW_WORDS]
    if not parts:
        return None, None
    leaf = parts[-1]
    for w in _WINDOW_WORDS:
        for form in (w + "_", "_" + w):
            leaf = leaf.replace(form, "")
    return parts[0], leaf.strip("_")


def check_prior_pairing(audit) -> list:
    """-> complaints where a KPI's prior measures something else than its current value.

    The gap between this and every other check in the pipeline is the reason it exists.
    `build_facts --verify` asks whether facts agree with the audit; the delivery gate asks
    whether the report agrees with facts. A KPI whose current and prior come from
    DIFFERENT BASES passes both, because each value is individually correct and correctly
    transcribed — and the delta between them, which is the only thing the reader sees, is
    meaningless.

    Measured: an account defined `pressure.app_month` (app sends over app opted-in
    devices) and, for the prior, only `pressure.prior_per_optin_month` (all push over all
    opted-in channels). `KPI_SPECS` resolves the current value first and then walks its
    own prior list until something answers, so it paired the two and published +9.4% on a
    hero tile. The right figure was +7.1%. Nothing in the audit was wrong; the pairing was.

    Deliberately narrow: only a mismatch INSIDE one audit block is reported. A prior
    resolving from another block (`usage.current.opens` against `baseline.open_tot`) is an
    intentional alias in `KPI_SPECS`, not a basis error.
    """
    try:
        import build_facts
        facts = build_facts.build_facts(audit)
    except Exception:                                                     # noqa: BLE001
        return []

    out = []
    for k in facts.get("kpis") or []:
        if k.get("prior") is None:
            continue
        cur_block, cur_metric = _metric_identity(k.get("source"))
        pri_block, pri_metric = _metric_identity(k.get("prior_source"))
        if not (cur_metric and pri_metric):
            continue
        if cur_block != pri_block:
            continue                       # a cross-block alias, intended by the spec
        if cur_metric == pri_metric:
            continue
        out.append(
            f"{k['key']}: current reads `{k.get('source')}` but its prior reads "
            f"`{k.get('prior_source')}` — same block, different metric, so the "
            f"{(k.get('delta_pct') or 0):+.1f}% delta compares two bases. Fix: define the "
            f"paired prior (`{pri_block}.prior_{cur_metric}`) in analyze.py, or pin it "
            f"with build_facts(..., overrides={{'{k['key']}': {{'prior': …}}}})")
    return out


def check_contamination_registry(audit) -> list:
    """-> advisory naming the stray copies, which are the ones that get published."""
    reg = audit.get("contaminated_fields") or contaminated_fields(audit)
    strays = [r for r in reg if not r["canonical"] and r["kind"] != "tap_count"]
    if not strays:
        return []
    worst = ", ".join(f"{r['path']} ({r['ratio_to_authoritative']}x)" for r in strays[:4])
    return [f"{len(strays)} field(s) repeat a counter that is not push volume: {worst}"
            + (f" — read {strays[0]['use_instead']} instead" if strays[0]["use_instead"]
               else "")]


# ---------------------------------------------------------------------------
# prose where a verdict belongs
# ---------------------------------------------------------------------------
# A sentence, as opposed to a label, an id or a client string. Long enough to be prose,
# and carrying the function words that make it a sentence rather than a name.
_PROSE_MIN_CHARS = 60
_PROSE_WORDS = re.compile(
    r"\b(?:the|and|with|that|from|are|were|this|these|those|which|their|because|"
    r"however|therefore|while|should|would|could|there|is|it|its|not|but|than|"
    r"then|when|where|has|have|had|does|did|of|to|in|on|for)\b", re.I)
_PROSE_MIN_WORDS = 6

# Keys whose whole job is to carry a sentence. `note`/`caveat`/`disclose` qualify a figure
# for the agent reading the audit; the `*_en` / `*_fr` twins are the sanctioned way to
# pre-write client copy. Neither is the failure this looks for.
_PROSE_OK_SUFFIXES = ("_en", "_fr")
_PROSE_OK_KEYS = {"note", "notes", "caveat", "disclose", "source", "basis", "why",
                  "description", "summary_en", "summary_fr", "methodology"}


def check_prose_verdicts(audit) -> list:
    """-> advisory naming audit fields that hold a sentence where a verdict belongs.

    Two failures, one cause. A sentence typed beside the number it describes drifts from
    it: one audit said "95 direct responses in total" in a block that computed 96, and the
    report carried both figures. And every string here is working English, so a section
    that quotes one ships English prose into a French report — twenty such fields in a
    single audit, each needing a translation nobody had budgeted for.

    ADVISORY, deliberately. Several of these fields are genuinely useful to the agent
    reading the audit, and turning a briefing note into a build failure would push people
    to delete the note rather than to derive the verdict. What this buys is that nobody
    discovers the twenty fields at wave 6.
    """
    hits = []

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}.{k}" if path else str(k))
        elif isinstance(node, list):
            for i, v in enumerate(node[:20]):
                walk(v, f"{path}[{i}]")
        elif isinstance(node, str):
            key = path.rsplit(".", 1)[-1].split("[")[0]
            if key in _PROSE_OK_KEYS or key.endswith(_PROSE_OK_SUFFIXES):
                return
            if len(node) >= _PROSE_MIN_CHARS and \
                    len(_PROSE_WORDS.findall(node)) >= _PROSE_MIN_WORDS:
                hits.append((path, node))

    walk(audit, "")
    if not hits:
        return []
    worst = "; ".join(f"{p} (\u201c{t[:60]}\u2026\u201d)" for p, t in hits[:4])
    return [f"{len(hits)} field(s) hold a sentence rather than a verdict: {worst}"]


def check_manifest(audit_path) -> list:
    """-> complaints about the collection manifest beside this audit.

    Run here, at analysis time, because this is the last wave where re-collecting is
    still a sane response. A manifest that claims a coverage its own status contradicts
    is how a truncated collection reaches the sections: nothing downstream re-reads the
    `truncated` block, and the coverage line is what a reader believes.
    """
    if not audit_path:
        return []
    path = os.path.join(os.path.dirname(os.path.abspath(audit_path)), "data",
                        "collect_manifest.json")
    if not os.path.isfile(path):
        return []                      # no manifest is not a finding; a lying one is
    try:
        manifest = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return []
    try:
        import coverage
    except ImportError:
        return []
    return coverage.contradictions(manifest)


def check_value_measurability(audit) -> list:
    """-> complaints when `events.value_measurability` is absent.

    The executive summary must state whether any conversion in this account can be given
    an amount, and the coverage banner reads the same key for its revenue blind spot.
    Absent it, a section recomputes the answer from `data/events.json` — a raw pull that
    is retired when the gate passes, leaving a report that cannot be rebuilt. That has
    happened; the key exists to make it unnecessary.
    """
    ev = audit.get("events")
    if not isinstance(ev, dict) or not ev:
        return []                    # an audit with no events block has none to grade
    vm = ev.get("value_measurability")
    if not isinstance(vm, dict) or not vm.get("grade"):
        return ["events.value_measurability is missing or carries no grade"]
    return []


# ---------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------
def verify(audit, audit_path=None) -> tuple:
    """-> (required, advisory) lists of (ok, label, detail)."""
    bands = check_benchmark_bands(audit)
    volume = check_volume_weighted(audit)
    pressure = check_pressure_basis(audit)
    settling = check_settling(audit)
    zeros = check_suspect_zeros(audit)
    rich = check_rich_overlap(audit)
    contam = check_contamination_registry(audit)
    id_req, id_adv = check_identity(audit)
    prose = check_prose_verdicts(audit)
    vmeas = check_value_measurability(audit)
    manifest = check_manifest(audit_path)
    pairing = check_prior_pairing(audit)
    vert = check_vertical_resolution(audit)

    required = [
        (not bands, "Benchmarks are bands, not points",
         f"{len(bands)} benchmark(s) cannot draw a peer band: " + "; ".join(bands[:4])
         + ". Fix: read the percentiles from benchmarks.json via "
           "resolve_vertical.metrics() rather than transcribing a median."),
        (not volume, "Volume-weighted fields are wired up",
         f"{len(volume)} block(s) weight by volume and got zero: " + "; ".join(volume[:4])
         + ". Fix: check the send-volume key name between producer and consumer — this "
           "fails silently and the count-weighted figure beside it can point the "
           "opposite way."),
        (not pressure, "Pressure is computed from push-only volume",
         "; ".join(pressure) + ". Fix: sum the push platforms of /api/reports/sends, "
         "not every platform it returns."),
        # Required, not advisory: what ships is the delta pill, and a delta between two
        # bases is wrong in a way the reader cannot see and no other check can reach.
        # The remedy is always available — name the paired prior — so a complaint here is
        # never a reason to fabricate a number.
        (not pairing, "Every KPI prior measures the same thing as its current value",
         "; ".join(pairing)),
        # Required: a silent fallback does not thin the output, it changes which events
        # are recommended and how the levers rank. Nothing downstream can tell.
        (not vert, "Catalogue and playbook resolved the vertical, not a fallback",
         "; ".join(vert)),
        (not settling, "Window does not run past the consolidation watermark",
         "; ".join(settling)),
        (not zeros, "No detail response contradicts the inventory with zeros",
         "; ".join(zeros)),
        (not id_req, "Run identity resolves",
         "; ".join(id_req) + ". Fix: state them at the audit root or under `meta`."),
        # Required rather than advisory: the summary and the coverage banner both read
        # this key, and the alternative a section reaches for when it is missing —
        # opening data/events.json — costs the report its rebuildability.
        (not vmeas, "Value measurability is graded in the audit",
         "; ".join(vmeas) + ". Fix: store event_analysis.value_measurability(events, "
         "tagging_monetary=…) at events.value_measurability."),
        # This wave is the last one where re-collecting is still a sane answer, which is
        # why it blocks here rather than being noted at the gate.
        (not manifest, "Collection manifest agrees with itself",
         "; ".join(manifest) + ". A stage that claims complete coverage and reports "
         "itself truncated is a truncation nobody will notice: the sample every later "
         "stage ranks was drawn from whatever landed before the cut. Fix: re-run that "
         "stage with a larger --stage-deadline, or accept the partial coverage and say "
         "so — but decide, rather than inheriting the claim."),
    ]
    advisory = [
        # Advisory rather than required on purpose: the additive total may yet turn out
        # to be right, and that is a question for Airship, not for the operator. What
        # must not happen silently is publishing one end of the interval as a fact.
        (not rich, "Reach is not stated as exact despite the `rich` overlap",
         "; ".join(rich)),
        # Advisory because the copies are not a defect in the audit — the API returns
        # them. What the registry buys is that no section has to rediscover them.
        (not contam, "No stray copy of a counter that is not push volume",
         "; ".join(contam) + ". They are listed in audit.contaminated_fields; "
         "check_section.py blocks their values automatically."),
        (not id_adv, "Optional run identity resolves", "; ".join(id_adv)),
        # Advisory: a briefing note is useful to the agent reading the audit, and making
        # it fail the build would get the note deleted rather than the verdict derived.
        (not prose, "Verdicts are enumerated, not written out",
         "; ".join(prose) + ". Every string here is internal working English: a section "
         "quoting one ships English into a translated report, and a sentence typed beside "
         "a number drifts from it. Fix: derive the verdict (a grade plus its inputs), or "
         "write the sentence as an *_en / *_fr pair."),
    ]
    return required, advisory


def main(argv) -> int:
    args = [a for a in argv if not a.startswith("--")]
    if "--selftest" in argv:
        return _selftest()
    if not args:
        print(__doc__.strip().splitlines()[0])
        print("usage: verify_audit.py work/<client>/audit.json")
        return 2
    path = args[0]
    with open(path, encoding="utf-8") as fh:
        audit = json.load(fh)

    # Written back before the freeze so that every downstream tool reads the same list.
    # This is the one place in the pipeline that sees the whole audit at once, which is
    # what finding a repeated value requires.
    registry = contaminated_fields(audit)
    if "--no-write" not in argv and registry != (audit.get("contaminated_fields") or []):
        audit["contaminated_fields"] = registry
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(audit, fh, ensure_ascii=False, indent=2)
        print(f"\n[registry] {len(registry)} contaminated field(s) written to "
              f"audit.contaminated_fields")

    required, advisory = verify(audit, path)
    print(f"\n{path}")
    ok_all = True
    for ok, label, detail in required:
        print(f"  [{'✓' if ok else '✗'}] {label}" + ("" if ok else f"  — {detail}"))
        ok_all = ok_all and ok
    for ok, label, detail in advisory:
        print(f"  [{'✓' if ok else '!'}] {label}" + ("" if ok else f"  — {detail}"))

    if ok_all:
        print("  => PASS — audit is plausible; freeze it and start wave 3")
    else:
        print("  => FAIL — fix analyze.py and re-run BEFORE writing charts or sections;\n"
              "     a section written against this audit has to be re-read line by line")
    return 0 if ok_all else 1


# ---------------------------------------------------------------------------
# selftest
# ---------------------------------------------------------------------------
def _base_audit() -> dict:
    """A minimal audit that passes every check, to mutate one field at a time."""
    return {
        "meta": {"client": "Example Retailer", "project": "Example PROD",
                 "app_key": "abcdef0123456789ABCDEF", "region": "eu", "lang": "en",
                 "period": "2026-07-26 to 2026-08-24"},
        "benchmarks": {
            "vertical": {"key": "food", "label": "Food & Drink"},
            "set": "Airship Food & Drink",
            "basis": "p10/p50/p90 by device family",
            "optin_rate": {"ios": {"p10": 40.0, "p50": 59.0, "p90": 78.0},
                           "android": {"p10": 38.0, "p50": 54.6, "p90": 72.0}},
        },
        "devices": {"app_optin": 1_000_000},
        "series": {"sends": {"current_total": 10_000_000}},
        "push_shape": {"all_channel_sends_window": 13_000_000},
        "pressure": {"window_days": 30, "opted_in_devices": 1_000_000,
                     "push_sends_series_total": 10_000_000, "per_optin_month": 10.0},
        "purpose": {"automation_mix": {
            "by_count": {"automated": 600, "one_shot": 20, "total": 620},
            "by_sends": {"automated": 3_000_000, "one_shot": 7_000_000,
                         "total": 10_000_000}}},
    }


def _selftest() -> int:
    fails = []

    def check(cond, label):
        if not cond:
            fails.append(label)

    # the happy path must be silent, or every real finding is noise
    req, adv = verify(_base_audit())
    check(all(ok for ok, _, _ in req), "a plausible audit passes every required check")
    check(all(ok for ok, _, _ in adv), "a plausible audit raises no advisory")

    # --- prior pairing: the delta that compared two bases ---
    # Reproduced from the account it shipped on: `app_month` current, and the only prior
    # available measuring all push over all channels. Both values right, delta wrong.
    mixed = _base_audit()
    mixed["pressure"].update({"app_month": 159.4, "prior_per_optin_month": 145.73})
    hits = check_prior_pairing(mixed)
    check(any(h.startswith("pressure:") for h in hits),
          "a prior naming a different metric in the same block is caught")
    check(any("prior_app_month" in h for h in hits),
          "the complaint names the paired prior that is missing")

    paired = _base_audit()
    paired["pressure"].update({"app_month": 159.4, "prior_app_month": 148.81})
    check(not check_prior_pairing(paired), "a correctly paired prior is silent")

    # A prior resolving from ANOTHER block is an intentional alias in KPI_SPECS, not a
    # basis error. Reported across 27 delivered audits this rule produced no finding at
    # all, which is what makes the narrow version worth having.
    aliased = _base_audit()
    aliased["usage"] = {"current": {"opens": 52_000_000}}
    aliased["baseline"] = {"open_tot": 51_000_000}
    check(not [h for h in check_prior_pairing(aliased) if h.startswith("opens:")],
          "a cross-block alias prior is not reported")

    # --- the registry must not scan itself ---
    # `main()` writes contaminated_fields back into the audit, and each record stores the
    # value it disqualifies. Scanning that back in made the second run report its own
    # output: four findings became twelve, and the count climbed on every invocation.
    rec = _base_audit()
    rec["reconcile"] = {"responses_list_sends": 13_500_000, "reports_sends": 13_000_000}
    first = contaminated_fields(rec)
    check(first, "a stray copy of a non-push counter is found on the first pass")
    rec["contaminated_fields"] = first
    check(len(contaminated_fields(rec)) == len(first),
          "writing the registry back does not grow it on the next pass")

    # --- vertical resolution: the fallback that changes the recommendations ---
    # Re-run over past accounts, this check found two reviews whose gap list and lever
    # ranking were computed on the cross-vertical book because the vertical was passed as
    # a display label. Both are pinned here by shape, not by name.
    vfall = _base_audit()
    vfall["events"] = {"analysis": {"vertical": {
        "input": "Restaurant & QSR", "book_key": "all_verticals",
        "fallback_all_verticals": True}}}
    hits = check_vertical_resolution(vfall)
    check(hits and "event catalogue" in hits[0],
          "a catalogue that fell back to all_verticals is caught")
    check(hits and "added_to_cart" in hits[0],
          "the complaint names the consequence, not just the fallback")

    vplay = _base_audit()
    vplay["purpose"]["vertical"] = {"input": "News & digital publishing",
                                    "book_key": "news & digital publishing",
                                    "known": False, "fallback": True}
    check(any("campaign playbook" in h for h in check_vertical_resolution(vplay)),
          "a playbook key the book does not know is caught")

    # Asking for the cross-vertical book is a decision. An account with no close peer set
    # is entitled to say so, and one delivered review does — it must not be reported.
    vasked = _base_audit()
    vasked["events"] = {"analysis": {"vertical": {
        "input": "all verticals", "book_key": "all_verticals",
        "fallback_all_verticals": True}}}
    check(not check_vertical_resolution(vasked),
          "explicitly asking for all_verticals is not reported as a fallback")

    vok = _base_audit()
    vok["events"] = {"analysis": {"vertical": {
        "input": "media", "book_key": "media", "fallback_all_verticals": False}}}
    vok["purpose"]["vertical"] = {"input": "media", "book_key": "media",
                                  "known": True, "fallback": False}
    check(not check_vertical_resolution(vok), "a resolved vertical is silent")

    # And the identity normaliser has to see through the two ways a window is named.
    check(_metric_identity("usage.current.push_sends")
          == _metric_identity("usage.prior.push_sends"),
          "a window named as a path segment normalises away")
    check(_metric_identity("series.sends.current_total")
          == _metric_identity("series.sends.prior_total"),
          "a window named as a leaf prefix normalises away")
    check(_metric_identity("pressure.app_month")
          != _metric_identity("pressure.prior_per_optin_month"),
          "two different metrics in one block stay different")

    # --- prose where a verdict belongs: the two shapes that reached a report ---
    a = _base_audit()
    a["programmes"] = {"populations": {"unnamed_reading":
        "42 of 142 programmes carry no resolvable name and account for most of the "
        "residual volume, so they cannot be attributed to a campaign."}}
    check(check_prose_verdicts(a), "a sentence in a `_reading` field is raised")
    check(not check_prose_verdicts(_base_audit()),
          "an audit of numbers and labels raises nothing")
    # A short label is not prose, whatever it is called.
    a = _base_audit()
    a["programmes"] = {"populations": {"unnamed_reading": "42 of 142 unnamed"}}
    check(not check_prose_verdicts(a), "a short label is not a sentence")
    # The sanctioned exception: a pre-written caveat as an *_en / *_fr pair.
    a = _base_audit()
    a["usage"] = {"open_rate_caveat_en":
        "The open rate is withheld because the endpoint counts every app open, not the "
        "ones that followed a notification.",
        "open_rate_caveat_fr":
        "Le taux d'ouverture est retir\u00e9 parce que l'endpoint compte toutes les "
        "ouvertures d'app, pas seulement celles qui suivent une notification."}
    check(not check_prose_verdicts(a), "an *_en / *_fr pair is the sanctioned exception")

    # --- value measurability: required once there is an events block to grade ---
    check(not check_value_measurability(_base_audit()),
          "an audit with no events block has nothing to grade")
    a = _base_audit()
    a["events"] = {"custom": [{"name": "purchase"}]}
    check(check_value_measurability(a),
          "an events block with no value_measurability is a finding")
    a["events"]["value_measurability"] = {"grade": "counters", "valued_events": 0}
    check(not check_value_measurability(a), "the graded verdict satisfies it")

    # bands: a transcribed median, which is the shape that actually shipped
    a = _base_audit()
    a["benchmarks"]["optin_rate"]["ios"] = 59.0
    check(check_benchmark_bands(a), "a bare number where a band belongs is caught")
    a = _base_audit()
    a["benchmarks"]["optin_rate"]["ios"] = {"p50": 59.0}
    check(check_benchmark_bands(a), "a band carrying only p50 is caught")
    # ...but a metric genuinely not published for a device family is not a defect
    a = _base_audit()
    a["benchmarks"]["optin_rate"]["ios"] = None
    check(not check_benchmark_bands(a), "an absent device family is not reported")

    # volume: the silent zero
    a = _base_audit()
    a["purpose"]["automation_mix"]["by_sends"] = {"automated": 0, "one_shot": 0,
                                                 "total": 0}
    check(check_volume_weighted(a), "an all-zero by_sends beside a populated by_count "
                                    "is caught")
    a = _base_audit()
    a["purpose"]["maturity"] = [{"pillar": "editorial", "campaigns": 2, "sends": 0},
                                {"pillar": "loyalty", "campaigns": 5, "sends": 0}]
    check(check_volume_weighted(a), "per-row send volumes that are all zero are caught")
    # a genuinely empty account must not trip it: no campaigns, no sends
    a = _base_audit()
    a["purpose"]["maturity"] = [{"pillar": "editorial", "campaigns": 0, "sends": 0}]
    check(not check_volume_weighted(a), "an account with no campaigns is not reported")

    # pressure: computed from the all-channel total
    a = _base_audit()
    a["pressure"]["per_optin_month"] = 13.0          # 13M / 1M, i.e. push + email
    check(check_pressure_basis(a), "pressure taken from the all-channel total is caught")
    a = _base_audit()
    a["push_shape"]["all_channel_sends_window"] = 10_000_000   # push-only account
    check(not check_pressure_basis(a), "a single-channel account is not reported")
    # a longer window still has to reconcile, per month
    a = _base_audit()
    a["pressure"].update({"window_days": 90, "per_optin_month": 10.0 / 3})
    check(not check_pressure_basis(a), "a 90-day window scales to a monthly rate")

    # silent zeros: the wrong endpoint for an id type, which returns 200 and zeros
    a = _base_audit()
    a["stages"] = {"programs": {"suspect_zero_details": [
        {"id": "27831766-98e0-4b7d-97b0-8b3a0250b6e5", "endpoint": "perpush/detail",
         "inventory_volume": 6968, "reason": "200 with every counter at zero"}]}}
    hits = check_suspect_zeros(a)
    check(hits and "6,968" in hits[0], "an all-zero detail beside real volume is caught")
    req, _ = verify(a)
    check(not all(ok for ok, _, _ in req), "a suspect zero fails the run")
    check(not check_suspect_zeros(_base_audit()), "a clean audit is not reported")
    a = _base_audit()
    a["stages"] = {"details": {"suspect_zero_details": []}}
    check(not check_suspect_zeros(a), "an empty flag list is not reported")

    # contamination: the same counter repeated where a section will reach for volume
    def _contam():
        a = _base_audit()
        a["usage"] = {"current": {"sends_push": 10_000_000}}
        a["reconcile"] = {"responses_list_sends": 13_600_000,
                          "reports_sends": 13_000_000}
        return a

    a = _contam()
    a["inventory_stats"] = {"by_channel": {"push": {"sends": 13_600_000},
                                           "in_app": {"sends": 238}}}
    reg = contaminated_fields(a)
    by_path = {r["path"]: r for r in reg}
    check("inventory_stats.by_channel.push.sends" in by_path,
          "a stray copy of the responses/list total is found by value")
    check(by_path["inventory_stats.by_channel.push.sends"]["ratio_to_authoritative"]
          == 1.36, "the stray copy states its distance from push volume")
    check(by_path["reconcile.responses_list_sends"]["canonical"],
          "the field the number legitimately lives in is marked canonical")
    check(by_path["reconcile.reports_sends"]["kind"] == "all_channel",
          "the all-channel total is registered as a different denominator, not a copy")
    check(by_path["inventory_stats.by_channel.in_app.sends"]["kind"] == "tap_count",
          "the in-app key named `sends` is registered as a tap count")
    check(check_contamination_registry(a), "the stray copy is raised as an advisory")
    check(not any("reconcile.responses_list_sends" in h
                  for h in check_contamination_registry(a)),
          "the canonical field is not raised as a stray")
    # an account whose enumerable inventory happens to match push volume has no copies
    a = _contam()
    a["reconcile"] = {"responses_list_sends": 10_000_000, "reports_sends": 10_000_000}
    check(not [r for r in contaminated_fields(a) if r["kind"] != "tap_count"],
          "a counter equal to push volume is not registered as contaminated")
    check(not contaminated_fields(_base_audit()),
          "an audit collected before reconcile existed is not reported")

    # consolidation: a window that includes today reads unsettled zeros as real
    a = _base_audit()
    a["window"] = {"settling": {"window_end": "2026-08-24",
                                "date_closed": "2026-08-24 00:00:00",
                                "ends_after_watermark": False}}
    check(not check_settling(a), "a window ending at the watermark is not reported")
    a["window"]["settling"].update({"window_end": "2026-08-25",
                                    "ends_after_watermark": True,
                                    "days_past_watermark": 1})
    check(check_settling(a), "a window running past the watermark is caught")
    req, _ = verify(a)
    check(not all(ok for ok, _, _ in req), "an unsettled window fails the run")
    check(not check_settling(_base_audit()),
          "an audit collected before this block existed is not reported")

    # rich overlap: the interval, and the figure that publishes the wrong end of it
    def _ov(additive, bound, **kw):
        a = _base_audit()
        pct = (additive - bound) / bound * 100.0 if bound else 0.0
        a["activity"] = {"rich_overlap": dict(
            {"rows": 217, "rows_rich_gt_alerting": 9, "rows_inbox_only": 0,
             "additive_total": additive, "reach_bound_total": bound,
             "gap": additive - bound, "max_overstatement_pct": round(pct, 2)}, **kw)}
        return a

    # the account this was measured on: 80,740 additive vs 72,350 bound
    check(check_rich_overlap(_ov(80_740, 72_350)), "a material rich overlap is reported")
    a = _ov(80_740, 72_350)
    a["reach"] = {"devices_touched": 80_740}
    hits = check_rich_overlap(a)
    check(any("reach.devices_touched" in h for h in hits),
          "a figure equal to the additive total is named as the upper bound")
    check(not any("rich_overlap.additive_total" in h for h in hits),
          "the block reporting the interval is not itself flagged as publishing it")
    a = _ov(80_740, 72_350)
    a["reach"] = {"devices_touched": 72_350}
    check(not any("reach.devices_touched" in h for h in check_rich_overlap(a)),
          "stating the lower bound is not flagged")
    # a push-only account has no overlap to worry about
    check(not check_rich_overlap(_ov(72_350, 72_350)),
          "an account with no rich sends is not reported")
    # ...nor is a gap thinner than the rounding a section applies anyway
    check(not check_rich_overlap(_ov(72_500, 72_350)), "a sub-1% gap is not reported")
    check(not check_rich_overlap(_base_audit()),
          "an audit collected before this block existed is not reported")
    check(any("rows_inbox_only" in h
              for h in check_rich_overlap(_ov(80_740, 72_350, rows_inbox_only=6))),
          "inbox-only Message Center drops are called out")
    # the measured shape that made this independent of the gap: when the drops never
    # notify, `alerting` is 0 on those rows, the two totals agree, and the gap is 0 —
    # while 231 of 504 rows are still invisible to anything reading `sends`
    quiet = check_rich_overlap(_ov(3_046, 3_046, rows=504, rows_inbox_only=231))
    check(any("rows_inbox_only" in h for h in quiet),
          "inbox-only drops are reported even when the overlap gap is zero")
    check(not any("reach lies in" in h for h in quiet),
          "...without claiming an interval that does not exist")
    # it must never fail a run
    req, _ = verify(_ov(80_740, 72_350))
    check(all(ok for ok, _, _ in req), "a rich overlap does not fail the run")

    # identity: the shape that silently dropped every Flight Deck link
    a = _base_audit()
    a["meta"].pop("app_key")
    req, adv = verify(a)
    check(all(ok for ok, _, _ in req), "a missing app_key does not block the run")
    check(not all(ok for ok, _, _ in adv), "a missing app_key is raised as an advisory")
    a = _base_audit()
    a["meta"].pop("client")
    id_req, _ = check_identity(a)
    check(id_req, "a missing client is a required failure")

    for f in fails:
        print(f"  ✗ {f}")
    print(f"verify_audit selftest: {'FAIL' if fails else 'ok'} "
          f"({len(fails)} failure(s))")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
