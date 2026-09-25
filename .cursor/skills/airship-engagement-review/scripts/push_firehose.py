"""Firehose push accounts: shape probe, exhaustive enumeration, send reconciliation.

The skill's standard firehose recipe is "don't page the firehose, aggregate it by
PROGRAM via distinct `group_id`s + `pergroup/detail`". That works for automation-driven
firehoses. It does **not** work for the other flavour, first hit on a telecom account:
an external orchestrator (Salesforce Marketing Cloud, Braze, a homegrown CRM…) calls
`/api/push` once per recipient, so every push is a standalone `SEGMENTS_PUSH` with
**no `group_id` at all**. There is no program layer to roll up to, and the campaign
taxonomy does not live in Airship — it lives in the tag namespace the orchestrator
writes (see `parse_tagging_plan.py`).

This module covers that case end to end:

  probe        Is this a firehose? Grouped or groupless? -> decides the whole approach.
  discover     Find the PROGRAM layer across every day of the window, at bounded cost.
  enumerate    Exhaustive, de-duplicated pass over `responses/list` for a date range.
  sample       Alerting / silent / rich split via `perpush/detail`, WITH drift detection.
  reconcile    Explain the gap between `responses/list` and `/api/reports/sends`.

A real account is rarely purely one flavour, and treating the two as exclusive is what
made this expensive. A grocery retailer carried a `group_id` on only 8.3% of its pushes —
read as "groupless", so it paid 76 086 calls to enumerate 3 of 30 days — while those
pushes' 25 programmes aggregated 46.6M sends, essentially the whole account. Both halves
exist on such an account and want opposite treatments: `discover` + `pergroup/detail` for
the programmes (their identity is cheap, their volume is one call each), and a sample for
the unitary stream, whose interest is typology rather than tonnage.

Two API quirks drive the window arithmetic (also documented in reference.md):
  * `end` is **INCLUSIVE** — windows must tile as [t, t+span-1], not [t, t+span).
    Tiling half-open double-counts every boundary row; always de-dup on `push_uuid`.
  * `start == end` returns HTTP 500 — the smallest usable leaf is 2 seconds.

CLI:
    python push_firehose.py probe     "<MCP project>" <start> <end>
    python push_firehose.py discover  "<MCP project>" <start> <end> [out_json]
    python push_firehose.py enumerate "<MCP project>" <start> <end> [out_dir]
    python push_firehose.py sample    "<MCP project>" <start> <end> [out_json]
    python push_firehose.py reconcile <pushes_dir> <sends.json> <sample.json>
    python push_firehose.py selftest                       # offline, no project, no API

Dates are YYYY-MM-DD; <end> is EXCLUSIVE (a normal half-open day range).
"""

import heapq
import json
import os
import random
import statistics
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from activity_log import nonneg  # noqa: E402
from airship_api import Airship  # noqa: E402

F = "%Y-%m-%d %H:%M:%S"
LIST_PATH = "/api/reports/responses/list"
DETAIL_PATH = "/api/reports/perpush/detail/"

WORKERS = 14
LEAF_SECONDS = 2          # `start == end` is rejected by the API
PAGE_LIMIT = 100
# Raw push rows retained per enumerated day, on top of the day's aggregate. Bounded so
# a 30-day firehose window stays a few tens of thousands of rows instead of ~87M.
KEEP_PER_DAY = 500

# A push is a "micro-send" when it reaches roughly one device: the signature of an
# external orchestrator resolving the audience itself and calling Airship per contact.
# This is diagnostic colour — it explains WHY a day holds so many pushes — and must never
# gate the cost decision. Enumeration cost is driven by the NUMBER of pushes alone: a
# football account emitting ~640k narrowly-targeted match alerts a day averages 1,011
# sends/push (nothing micro about it, because a few broadcasts are enormous while the
# median alert reaches nobody), yet enumerating it is as hopeless as any orchestrator
# firehose. Requiring both signals classified it as `dashboard` and pointed the collector
# at ~190,000 pages.
MICRO_SEND_CEILING = 2.0
FIREHOSE_MIN_PUSHES_PER_DAY = 5000

# A threshold on a quantity that moves 40% between two days of the same account cannot be
# a clean line, and the oracle counting exactly does not change that: measured on a
# streaming account, three consecutive days held 4,399, 3,966 and 5,045 pushes, so which
# days got probed decided the entire collection strategy. The band below the threshold is
# therefore resolved towards the intractable side whenever any probed day crosses it,
# because the two mistakes are not symmetric. Reading a firehose as `dashboard` aims the
# collector at ~190,000 pages and the run dies or truncates silently; reading a borderline
# account as a firehose rolls it up by programme and still produces a correct report, at
# the cost of a per-push sample instead of an enumeration.
FIREHOSE_BORDERLINE_FLOOR = 0.8

# Below this share of the probed days' authoritative sends, the probe sample describes too
# little of the account to carry a per-push statistic. Measured on a streaming account, the
# probe's 0.988 sends/push mean was drawn from 0.282% of the volume — it read as an external
# orchestrator calling /api/push per recipient, which is a very different account from the
# one the sends counter describes.
SAMPLE_SHARE_FLOOR = 0.02

# The routing oracle. Counting a day by fully paginating a tiling of it replaces the rate
# extrapolation that used to decide this: measured on the same football account on two runs,
# extrapolating short windows returned 379,056 then 726,672 pushes/day, a factor of 1.9,
# because the 5-minute push rate swings 130x between a quiet morning and kick-off.
#
# The tile is 30 minutes because a cap is a SEQUENTIAL chain — a cursor cannot be walked in
# parallel — so the tile width, not the total page budget, sets the wall time. Measured on a
# retail firehose, hour tiles capped at 60 pages put 5 chains of 60 round-trips on the
# critical path and the probe took 47s; half-hour tiles at 30 pages halve that for the same
# ceiling per unit time. 3,000 pushes inside 30 minutes is already firehose-grade, so the
# cap never truncates a day this oracle is meant to count exactly.
#
# `ORACLE_STOP_AT` is what keeps a firehose cheap: once a day's running total passes it, the
# answer is settled and the day's remaining tiles are abandoned. It sits at 3x the routing
# threshold rather than at it, because a day that stops early contributes its floor to the
# mean — stopping at the threshold itself would let two quiet days drag a genuinely dense
# account back under it.
ORACLE_DAYS = 3
ORACLE_WINDOW_SECONDS = 1800
ORACLE_WINDOW_PAGE_CAP = 30
ORACLE_STOP_AT = 3 * FIREHOSE_MIN_PUSHES_PER_DAY

# Reads spread across a probed day, instead of a contiguous prefix of it. A firehose
# emits ~1M pushes/day, so the first 400 rows are a sample of its first *minutes*, not
# of the day. Measured on a grocery-retail account: automation groups first fired
# anywhere between 00:01 and 18:27, so a prefix sees the overnight programmes and
# concludes the afternoon ones do not exist.
PROBE_SLICES = 12

# Does a program layer worth rolling up exist? Judged as a SHARE of the window, because the
# quantity available here is a LIFETIME aggregate and an absolute floor on it means
# different things on different accounts: 31.5M lifetime sends read as "a real program
# layer" on a sports account whose 1,929 programmes turned out to weigh at most 5.3% of the
# window, while the same 31.5M is the entire account on a smaller one. The absolute floor
# survives only as a fallback for when the window total cannot be read.
PROGRAM_LAYER_MIN_SHARE = 0.2
PROGRAM_LAYER_MIN_SENDS = 1_000_000
GROUPED_SHARE_FLOOR = 0.2

# Above this many pushes a day, exhaustive enumeration stops being a strategy: the adaptive
# descent has to split hours into minutes and minutes into seconds, and one day costs tens of
# thousands of calls. Set from measurement on both sides — a streaming account at 4,470/day
# enumerated its window fine, a sports account at 16,366+/day spent 16 minutes on day one and
# wrote nothing.
ENUMERABLE_PUSHES_PER_DAY = 8_000


# ---------------------------------------------------------------------------
# window arithmetic
# ---------------------------------------------------------------------------
def tile(t0, t1, span):
    """Inclusive-end windows tiling the half-open range [t0, t1) with `span`-s steps."""
    out, t = [], t0
    while t < t1:
        end = min(t + timedelta(seconds=span), t1) - timedelta(seconds=1)
        out.append((t, end))
        t += timedelta(seconds=span)
    return out


def _params(w, limit=PAGE_LIMIT):
    return {"start": w[0].strftime(F), "end": w[1].strftime(F), "limit": limit}


def _days(start, end):
    d, last = datetime.strptime(start, "%Y-%m-%d"), datetime.strptime(end, "%Y-%m-%d")
    while d < last:
        yield d.strftime("%Y-%m-%d")
        d += timedelta(days=1)


# ---------------------------------------------------------------------------
# 1. probe — which firehose flavour is this?
# ---------------------------------------------------------------------------
def _spread_windows(day, slices=PROBE_SLICES):
    """`slices` evenly spaced, inclusive-end windows tiling one day."""
    d0 = datetime.strptime(day + " 00:00:00", F)
    step = 86400 // slices
    return [(d0 + timedelta(seconds=i * step),
             d0 + timedelta(seconds=i * step + step - 1)) for i in range(slices)]


class _Budget:
    """A day's shared row counter with a stop flag, so parallel hours quit together.

    The oracle only has to place a day on one side of a threshold. Once the running total
    passes `stop_at`, every hour still queued is pointless work, and on a firehose that
    "pointless" is thousands of pages.
    """

    def __init__(self, stop_at):
        self.stop_at = stop_at
        self.rows = 0
        self.pages = 0
        self.lock = threading.Lock()
        self.done = threading.Event()

    def add(self, rows, pages=1):
        """Bank a page. Returns True when the day is settled and workers should stop."""
        with self.lock:
            self.rows += rows
            self.pages += pages
            if self.stop_at and self.rows >= self.stop_at:
                self.done.set()
        return self.done.is_set()


def oracle_pushes_per_day(api, days, window_s=ORACLE_WINDOW_SECONDS,
                          page_cap=ORACLE_WINDOW_PAGE_CAP, stop_at=ORACLE_STOP_AT,
                          workers=WORKERS):
    """Count the pushes of each day in `days` by fully paginating a tiling of it.

    This is the routing oracle, and it answers a yes/no question — is enumeration
    affordable — rather than producing a client-facing volume. Its guarantee is what
    matters: **below `stop_at` the count is exact**, above it the count is a floor that
    already clears the threshold. Both readings decide, so the routing never rests on an
    extrapolation.

    Three properties are deliberate:

    * **A tiling, not sampled slices.** Every window of the day is walked, each cheap to
      drain when the account is quiet (one page) and each abandonable when it is not.
      Sampling short windows and scaling to 24h is what produced a 1.9x swing between two
      runs of the same account, since the push rate is not stationary across a day.
    * **More than one day.** A streaming account read 3,966 pushes on one day against a
      5,222 window average: a single day straddling the threshold decides the whole
      collection strategy, so the oracle averages `ORACLE_DAYS` spread days.
    * **Shared budget across the whole pool.** Windows from every probed day are submitted
      to one pool and interleave, so a dense day's stop flag fires while its other windows
      are still queued rather than after they have all run.
    """
    days = list(days)
    if not days:
        return None
    budgets = {d: _Budget(stop_at) for d in days}
    jobs = []
    for d in days:
        d0 = datetime.strptime(d + " 00:00:00", F)
        jobs += [(d, w) for w in tile(d0, d0 + timedelta(days=1), window_s)]

    def one(job):
        day, w = job
        b = budgets[day]
        if b.done.is_set():
            return day, False
        pages = 0
        for page in api.paginate(LIST_PATH, _params(w)):
            pages += 1
            if b.add(len(page)):
                return day, False
            if pages >= page_cap:
                return day, True
        return day, False

    capped = Counter()
    with ThreadPoolExecutor(min(len(jobs), workers)) as ex:
        for day, hit_cap in ex.map(one, jobs):
            if hit_cap:
                capped[day] += 1

    per_day = []
    for d in days:
        b = budgets[d]
        per_day.append({
            "day": d,
            "pushes": b.rows,
            "pages": b.pages,
            "windows_capped": capped.get(d, 0),
            "stopped_at_budget": b.done.is_set(),
            # exact only when nothing truncated the walk: no window hit its page cap and
            # the day never crossed the budget that abandons its remaining windows
            "exact": not b.done.is_set() and not capped.get(d, 0),
        })
    counts = [p["pushes"] for p in per_day]
    return {
        "estimate": int(statistics.fmean(counts)),
        "is_floor": any(not p["exact"] for p in per_day),
        "per_day": per_day,
        "days": days,
        "min_day": min(counts),
        "max_day": max(counts),
        "pages": sum(p["pages"] for p in per_day),
        "basis": (f"{len(days)} spread days, each tiled into {window_s // 60}-minute "
                  f"windows paginated in full (cap {page_cap} pages/window, day abandoned "
                  f"past {stop_at:,} pushes); routing on the mean"),
    }


def reports_sends_by_day(api, start, end):
    """Alerting sends per day from `/api/reports/sends` over [start, end]. One call.

    The authoritative counter, fetched once and used for two different jobs: it turns the
    probe sample's mean sends/push from an assertion into a measured share of the account,
    and it gives the programme layer's lifetime aggregate a denominator so "is there a
    program layer" is answered as a share of the window rather than against a constant.
    """
    out = {}
    try:
        for page in api.paginate("/api/reports/sends",
                                 {"start": f"{start} 00:00:00", "end": f"{end} 23:59:59",
                                  "precision": "DAILY"}, key="sends"):
            for r in page:
                day = str(r.get("date") or "")[:10]
                if day:
                    out[day] = out.get(day, 0) + sum(
                        v for k, v in r.items()
                        if k != "date" and isinstance(v, (int, float)))
    except Exception:
        return {}
    return out


def _oracle_days(probe_days, sends_by_day, want=ORACLE_DAYS):
    """Which days the routing oracle should count, chosen by volume rather than position.

    The oracle answers "is enumeration affordable", so it has to see the day that would
    make it unaffordable. Taking an evenly-spaced slice of the probe days does not: on a
    bimodal account — quiet most days, a blast on a handful — an even slice lands on quiet
    days with high probability and reports the quiet rate as the account's rate.

    That happened. A cinema chain was classified `dashboard` on "~469 pushes/day" drawn
    from three of its calmest days, while its blast days ran to 600,000 sends and the
    window held 1.35M pushes. Nothing downstream was sized for that, the enumeration was
    cut by the stage deadline twice, and the collection took 88 minutes across three
    passes instead of one.

    So: always the busiest day, then the median day, then the quietest — the spread is
    what shows bimodality, and the busiest is what bounds the cost. Falls back to the old
    positional slice when `/api/reports/sends` did not answer, because a worse sample is
    better than no routing.
    """
    ranked = sorted((d for d in probe_days if sends_by_day.get(d)),
                    key=lambda d: sends_by_day[d])
    if len(ranked) < want:
        return probe_days[:: max(1, len(probe_days) // want)][:want]
    picks, n = [], len(ranked)
    for i in range(want):
        # want=3 -> quietest, median, busiest; larger `want` spreads evenly between them.
        picks.append(ranked[round(i * (n - 1) / (want - 1))] if want > 1 else ranked[-1])
    # Order restored so the oracle's own day-by-day output stays chronological.
    return sorted(set(picks), key=probe_days.index)


def probe(api, start, end, slices=PROBE_SLICES, confirm_groups=8):
    """Classify the account's push shape from a cheap sample. Returns a dict.

    `shape` is one of:
      dashboard            normal account — enumerate per push, the standard path
      firehose_grouped     dense, carrying group_ids — roll up via pergroup/detail
      firehose_groupless   dense, no programme layer, but COUNTED and modest enough that
                           exhaustive enumeration still terminates
      firehose_unattributed dense, no programme layer, and too dense (or of unknown
                           density) to enumerate — sample and declare coverage instead

    Three questions, deliberately not conflated. The first two decide the shape jointly; the
    third is what distinguishes the two groupless shapes:

    1. Is the account dense? (cost of walking the pushes)
    2. Is there a programme layer to roll up to? (structure)
    3. Is a full pass sizeable at all? (`pushes_per_day_exact` — a floor is not a size)

    Collapsing 1 and 3 is what produced a 16-minute stall on a single day: an account with no
    programme layer was sent to exhaustive enumeration precisely because it was too dense to
    have one.

    On the first two:

    1. **Is enumeration affordable?** Decided on the counted daily push volume ALONE
       (`oracle_pushes_per_day`, run unconditionally). Whether each push reaches one device
       or a million says nothing about the cost of walking them. Gating this on micro-sends
       as well classified a football account at ~640k pushes/day as `dashboard` and aimed
       the collector at ~190,000 pages, because a few huge broadcasts lifted its mean to
       1,011 sends/push.
    2. **Is there a program layer to roll up to?** Decided on what the discovered
       programmes actually weigh (`confirm_groups` calls to `pergroup/detail`), not on how
       many rows mention a `group_id`. Counting the *share of pushes* carrying one — the
       original single test — misreads an account whose median push delivers 0 sends: on a
       grocery retailer 8.3% of pushes carried an id, which read as "no program layer
       exists", while those pushes' 25 programmes aggregated 46.6M sends, i.e. essentially
       the entire account.

    Every signal behind both calls is returned for audit.
    """
    days = list(_days(start, end))
    probe_days = days[:: max(1, len(days) // 6)][:6] or days[:1]

    # One page per spread window, every (day, window) pair submitted to a single pool. Run
    # in series these same 72 calls cost 50.8s of pure round-trip on every run, and the
    # windows are independent by construction.
    jobs = [(day, w) for day in probe_days for w in _spread_windows(day, slices)]

    def one_window(job):
        day, w = job
        return day, (api.get(LIST_PATH, _params(w)).get("pushes") or [])

    rows, per_day_counts = [], {d: 0 for d in probe_days}
    # Saturation is a property of a WINDOW, not of a day's total. Judging it on the total
    # let a day of 12 windows pass for unsaturated because its quiet windows diluted its
    # busy ones: a retail account whose activity concentrates in a few hours flipped from
    # firehose to dashboard the day spread windows replaced a contiguous prefix.
    saturated_windows = 0
    with ThreadPoolExecutor(min(len(jobs), WORKERS)) as ex:
        for day, got in ex.map(one_window, jobs):
            per_day_counts[day] += len(got)
            if len(got) >= PAGE_LIMIT:
                saturated_windows += 1
            rows.extend(got)

    if not rows:
        # Carry the same keys as a full probe. A silent account is a legitimate reading, not
        # a missing one, and a caller that has to special-case its absence will eventually
        # forget to.
        return {"shape": "dashboard", "sampled_pushes": 0,
                "probe_days": probe_days,
                "saturated_probe_windows": 0, "probe_windows": len(jobs),
                "pushes_per_day_floor": 0, "pushes_per_day_exact": True,
                "pushes_per_day_basis": "no pushes in any probed window",
                "sample_sends": 0, "sample_sends_share": None,
                "per_push_stats_reliable": False,
                "per_push_stats_note": "no pushes sampled, so there is no per-push "
                                       "statistic to report",
                "shape_reason": "responses/list returned no push in any probed window — "
                                "enumeration is trivially affordable",
                "note": "no pushes returned by responses/list in the probe window"}

    sends = [int(r.get("sends") or 0) for r in rows]
    grouped = sum(1 for r in rows if r.get("group_id"))
    group_ids = sorted({r["group_id"] for r in rows if r.get("group_id")})
    total_sends = sum(sends)
    group_sends = sum(int(r.get("sends") or 0) for r in rows if r.get("group_id"))
    types = Counter(r.get("push_type") or "?" for r in rows)
    mean_sends = statistics.fmean(sends) if sends else 0.0
    micro = mean_sends <= MICRO_SEND_CEILING

    # The authoritative per-day counter, fetched BEFORE the oracle because it is what
    # decides which days the oracle should look at. One call either way.
    sends_by_day = reports_sends_by_day(api, days[0], days[-1])

    # The oracle runs UNCONDITIONALLY. Gating it on a saturated probe is what misrouted
    # four of thirteen surveyed projects: unsaturated days fell back to the probe's own row
    # count, which `slices * PAGE_LIMIT` caps at 1,200 by construction, and that fallback
    # was then compared against a 5,000 threshold — a branch that can never conclude
    # firehose. Those four accounts reported 200, 715, 1,086 and 1,167 pushes/day against a
    # true rate of 6,000+.
    oracle_days = _oracle_days(probe_days, sends_by_day)
    depth = oracle_pushes_per_day(api, oracle_days)
    per_day = (depth or {}).get("estimate", 0)
    busiest = (depth or {}).get("max_day", 0)
    borderline = (per_day < FIREHOSE_MIN_PUSHES_PER_DAY
                  and busiest >= FIREHOSE_MIN_PUSHES_PER_DAY
                  and per_day >= FIREHOSE_BORDERLINE_FLOOR * FIREHOSE_MIN_PUSHES_PER_DAY)
    dense = per_day >= FIREHOSE_MIN_PUSHES_PER_DAY or borderline

    # What share of the account the probe sample actually saw, against the authoritative
    # counter for the same days. Without it, a mean of 0.988 sends/push reads as an external
    # orchestrator pushing per recipient when it is really 0.282% of the volume.
    probed_reports_sends = sum(sends_by_day.get(d, 0) for d in probe_days) or None
    window_reports_sends = sum(sends_by_day.values()) or None
    sample_share = ((total_sends / probed_reports_sends)
                    if probed_reports_sends else None)
    per_push_reliable = bool(sample_share is not None
                             and sample_share >= SAMPLE_SHARE_FLOOR)

    push_share = grouped / len(rows)
    sends_share = (group_sends / total_sends) if total_sends else 0.0

    # What the discovered programmes actually weigh. `pergroup/detail` aggregates the
    # WHOLE programme (no date parameters), so this is a lifetime figure and a ceiling on
    # the window — ample to answer "is there a program layer", never a window volume.
    program_sends, confirmed = 0, []
    if group_ids and confirm_groups:
        by_freq = Counter(r["group_id"] for r in rows if r.get("group_id"))
        for gid, _ in by_freq.most_common(confirm_groups):
            try:
                d = api.get(f"/api/reports/pergroup/detail/{gid}") or {}
            except Exception:
                continue
            s = int(d.get("sends") or 0)
            program_sends += s
            confirmed.append({"group_id": gid, "sends": s})

    # The programme layer weighed against the window, not against a constant. Lifetime over
    # window is a CEILING on the layer's window contribution — `pergroup/detail` has no date
    # parameters — which is exactly the right side to err on for "does a layer exist".
    program_share_ceiling = ((program_sends / window_reports_sends)
                             if window_reports_sends else None)
    if program_share_ceiling is not None:
        program_layer = program_share_ceiling >= PROGRAM_LAYER_MIN_SHARE
    else:
        program_layer = program_sends >= PROGRAM_LAYER_MIN_SENDS

    # Can the window be enumerated at all? Only when the density is KNOWN and modest.
    # `firehose_groupless` used to be the fallback for any dense account without a programme
    # layer, and it means "enumerate exhaustively" — which is a contradiction on an account
    # dense enough to be a firehose in the first place. Measured: a sports account at 16,366+
    # pushes/day spent 16 minutes on its FIRST day's adaptive descent and wrote nothing, so
    # the full pass was hours away. A floor is not a size, and a strategy cannot be chosen
    # against a number that has no upper bound.
    exact = bool(depth and not depth.get("is_floor"))
    enumerable = bool(exact and per_day and per_day <= ENUMERABLE_PUSHES_PER_DAY)
    if dense:
        grouped_enough = (push_share >= GROUPED_SHARE_FLOOR
                          or sends_share >= GROUPED_SHARE_FLOOR
                          or program_layer)
        if grouped_enough:
            shape = "firehose_grouped"
        elif enumerable:
            shape = "firehose_groupless"
        else:
            shape = "firehose_unattributed"
    else:
        shape = "dashboard"

    out = {
        "shape": shape,
        "sampled_pushes": len(rows),
        "probe_days": probe_days,
        "sample_basis": f"{slices} windows spread across each probed day, one page each",
        "mean_sends_per_push": round(mean_sends, 3),
        "median_sends_per_push": statistics.median(sends) if sends else 0,
        "pushes_with_group_id": grouped,
        "group_id_share": round(push_share, 4),
        "group_sends_share": round(sends_share, 4),
        "distinct_group_ids": len(group_ids),
        "group_ids": group_ids,
        "confirmed_program_sends": program_sends,
        "confirmed_programs": confirmed,
        "window_reports_sends": window_reports_sends,
        # A CEILING: pergroup/detail aggregates the whole programme for all time, so this
        # bounds the layer's window contribution and never states it.
        "program_share_ceiling": (round(program_share_ceiling, 5)
                                  if program_share_ceiling is not None else None),
        "program_layer_exists": program_layer,
        "push_types": dict(types.most_common(8)),
        "saturated_probe_windows": saturated_windows,
        "probe_windows": len(jobs),
        "micro_sends": micro,
        # A FLOOR for the cost decision, not a client-facing count. Volume KPIs come from
        # /api/reports/sends; nothing downstream should quote this as "pushes sent".
        "pushes_per_day_floor": per_day,
        "pushes_per_day_exact": bool(depth and not depth.get("is_floor")),
        "pushes_per_day_basis": depth or "oracle returned nothing",
        # Which days the routing was decided on, and what they weigh. A shape read off
        # three of the month's quietest days is a shape read off the wrong account, and
        # without this the mistake is invisible afterwards.
        "oracle_days": oracle_days,
        "oracle_days_sends": {d: sends_by_day.get(d, 0) for d in oracle_days},
        "window_busiest_day_sends": max(sends_by_day.values()) if sends_by_day else None,
        "borderline_density": borderline,
        # The probe sample's own weight in the account, and whether it can carry a per-push
        # statistic at all. Sections must not quote mean/median sends per push when this is
        # False — the sample describes too little of the volume to characterise it.
        "probed_days_reports_sends": probed_reports_sends,
        "sample_sends": total_sends,
        "sample_sends_share": (round(sample_share, 5)
                               if sample_share is not None else None),
        "per_push_stats_reliable": per_push_reliable,
        "per_push_stats_note": (
            f"the probe sample carries {sample_share:.3%} of the alerting sends "
            f"/api/reports/sends reports for the same {len(probe_days)} day(s), below the "
            f"{SAMPLE_SHARE_FLOOR:.0%} floor — mean/median sends per push describe the "
            f"sample, not the account, and must not be published"
            if sample_share is not None and not per_push_reliable else
            f"the probe sample carries {sample_share:.1%} of the probed days' alerting "
            f"sends, enough to characterise sends per push"
            + (" — above 100% because responses/list counts silent pushes while "
               "/api/reports/sends counts alerting ones only"
               if sample_share > 1.0 else "")
            if sample_share is not None else
            "/api/reports/sends did not answer for the probed days, so the sample's weight "
            "in the account is unknown — treat per-push statistics as unverified"),
    }
    floor = " (floor)" if (depth or {}).get("is_floor") else " (exact)"
    per_push = (f"mean {mean_sends:.0f} sends/push, median "
                f"{out['median_sends_per_push']:.0f}"
                if per_push_reliable else
                "sends per push withheld (probe sample too thin, see "
                "per_push_stats_note)")
    cost = (f"~{per_day:,} pushes/day{floor} vs a {FIREHOSE_MIN_PUSHES_PER_DAY:,} "
            f"threshold; {per_push}")
    if borderline:
        cost += (f". The mean sits under the threshold but the busiest probed day held "
                 f"{busiest:,}, so this account straddles it and is treated as dense: "
                 f"under-reading a firehose costs the whole collection, over-reading a "
                 f"dashboard costs a per-push sample")
    out["enumerable"] = enumerable
    verdict = ("enumeration is affordable" if not dense else
               "a full pass still terminates at this density" if enumerable else
               "enumeration is intractable")
    out["shape_reason"] = (
        f"{cost} — {verdict}. Group share {push_share:.1%} of pushes / "
        f"{sends_share:.1%} of sends; {len(confirmed)} confirmed programme(s) aggregate "
        f"{program_sends:,} sends (lifetime), at most "
        + (f"{program_share_ceiling:.1%} of the window"
           if program_share_ceiling is not None else "an unknown share of the window")
        if dense else
        f"{cost} — {verdict}")
    out["guidance"] = {
        "dashboard": "Standard path: enumerate pushes and decode pushbodies per message.",
        "firehose_grouped": "Roll up by PROGRAM: run `discover` to collect distinct "
                            "group_ids across the window, then pergroup/detail per group "
                            "(see reference.md 1b). Do NOT enumerate per push.",
        "firehose_groupless": "No program layer exists, but the daily count is known and "
                              "modest. Run `enumerate` for exhaustive volume/response data, "
                              "and rebuild the campaign taxonomy from the orchestrator's tag "
                              "namespace (parse_tagging_plan).",
        "firehose_unattributed": "Neither strategy applies: nothing to roll up to, and too "
                                 "dense to enumerate. Do NOT enumerate. Take volume from "
                                 "/api/reports/sends (authoritative), the message inventory "
                                 "from the hour-tiled activity log, and typology from a "
                                 "sends-weighted sample — then state the coverage of each. "
                                 "The campaign taxonomy lives in the orchestrator's tag "
                                 "namespace (parse_tagging_plan), not in Airship.",
    }[shape]
    return out


# ---------------------------------------------------------------------------
# 2. discover — find the PROGRAM layer across the whole window, cheaply
# ---------------------------------------------------------------------------
def discover_groups(api, start, end, slices=24, pages_per_slice=2, workers=WORKERS,
                    should_stop=None, keep_groupless=0):
    """Collect distinct `group_id`s across EVERY day of [start, end), at bounded cost.

    This is the grouped half of a firehose. It exists because the two things a review
    needs from the program layer have very different prices: the *identity* of each
    programme is a handful of rows, while its *volume* is one `pergroup/detail` call that
    aggregates the whole programme regardless of how many rows you saw. So there is no
    reason to enumerate a programme — only to notice it.

    Why spread windows rather than a capped prefix of each day: on the account this was
    measured against, the 19 programmes of a single day first fired between 00:32 and
    16:05. Capping pagination at the first N pages of a day would therefore drop the
    afternoon programmes systematically — a silent, structural loss, not a sampling error.

    Discovery is a lower bound and says so: `by_day` is the curve of newly-seen ids, and a
    curve still climbing on the last day means the window was not saturated. A programme
    that fires once, in one minute, among ~1 000 pushes/minute can be missed; one that
    recurs cannot. Report `coverage`, never "all programmes".

    `keep_groupless` additionally retains the N heaviest UNGROUPED rows of the same scan.
    They cost nothing — already fetched, and previously discarded — and they are the only
    sample of the unitary stream available on an account where neither the programme roll-up
    nor exhaustive enumeration applies.
    """
    days = list(_days(start, end))
    seen, rep, by_day = {}, {}, []
    # A bounded heap, not a dict: only the `keep_groupless` heaviest rows are ever returned,
    # and holding all of them to sort at the end cost 880 MB on a 30-day scan of an account
    # with ~110,000 distinct ungrouped pushes. The id set stays, because `groupless_seen` is
    # a figure the report discloses.
    solo, solo_seen, solo_rows, solo_tie = [], set(), 0, 0
    calls0 = getattr(api, "calls", 0)

    def slice_rows(w):
        rows, pages = [], 0
        for page in api.paginate(LIST_PATH, _params(w)):
            rows.extend(page)
            pages += 1
            if pages >= pages_per_slice:
                break
        return rows

    stopped = None
    with ThreadPoolExecutor(workers) as ex:
        for day in days:
            if should_stop and should_stop():
                stopped = day
                print(f"[stop] deadline reached before {day} — "
                      f"{len(by_day)}/{len(days)} days scanned", flush=True)
                break
            fresh = 0
            for rows in ex.map(slice_rows, _spread_windows(day, slices)):
                for r in rows:
                    gid = r.get("group_id")
                    if not gid:
                        if keep_groupless:
                            u = r.get("push_uuid")
                            solo_rows += 1
                            if u and u not in solo_seen:
                                solo_seen.add(u)
                                # counter breaks ties so heapq never compares two row dicts
                                solo_tie += 1
                                item = (r.get("sends") or 0, solo_tie, r)
                                if len(solo) < keep_groupless:
                                    heapq.heappush(solo, item)
                                else:
                                    heapq.heappushpop(solo, item)
                        continue
                    if gid not in seen:
                        seen[gid] = day
                        fresh += 1
                    # keep the largest-sending occurrence: the per-push endpoints need a
                    # push_uuid, and the biggest one is the most representative creative
                    cur = rep.get(gid)
                    if not cur or (r.get("sends") or 0) > (cur.get("sends") or 0):
                        rep[gid] = r
            by_day.append({"day": day, "new_groups": fresh, "total_groups": len(seen)})
            print(f"  {day}: +{fresh} new · {len(seen)} groups", flush=True)

    tail = [d["new_groups"] for d in by_day[-3:]]
    saturated = bool(by_day) and sum(tail) == 0 and not stopped
    solo_kept = [r for _, _, r in sorted(solo, key=lambda it: -it[0])]
    return {
        "group_ids": sorted(seen),
        "first_seen": seen,
        "representatives": list(rep.values()),
        # Ranked by sends, so what is kept is the part of the unitary stream a report could
        # show, not whichever rows the cursor reached first.
        "groupless_sample": solo_kept,
        "groupless_seen": len(solo_seen),
        "groupless_rows_scanned": solo_rows,
        "groupless_sample_sends": sum(r.get("sends") or 0 for r in solo_kept),
        "by_day": by_day,
        "stopped_before": stopped,
        "days_scanned": len(by_day),
        "days_in_window": len(days),
        "slices_per_day": slices,
        "pages_per_slice": pages_per_slice,
        "api_calls": getattr(api, "calls", 0) - calls0,
        "saturated": saturated,
        "coverage": (
            f"{len(seen)} programmes found by scanning {slices} spread windows on each of "
            f"{len(by_day)} of {len(days)} days "
            f"({getattr(api, 'calls', 0) - calls0} API calls). "
            + (f"The scan stopped at its deadline before {stopped}, so the later days of "
               f"the window were not scanned at all — this is a PARTIAL inventory. "
               if stopped else "")
            + ("No new programme appeared on the last 3 days, so the set is saturated for "
               "recurring programmes; a one-off that fired in a single unscanned minute "
               "could still be absent."
               if saturated else
               "New programmes were still appearing at the end of the window — treat this "
               "as a LOWER BOUND and widen `slices` or `pages_per_slice` before implying "
               "completeness.")),
    }


# ---------------------------------------------------------------------------
# 3. enumerate — exhaustive, de-duplicated pass over responses/list
# ---------------------------------------------------------------------------
class _Progress:
    def __init__(self, every=1000):
        self.lock = threading.Lock()
        self.pages = 0
        self.rows = 0
        self.every = every
        self.t0 = time.time()

    def tick(self, pages, rows):
        with self.lock:
            self.pages += pages
            self.rows += rows
            if self.pages % self.every < pages:
                el = time.time() - self.t0
                print(f"    … {self.pages} pages · {self.rows:,} rows · {el:.0f}s · "
                      f"{self.pages / max(el, 1):.1f} pg/s", flush=True)


def _collect_day(api, day, ex, prog):
    """Adaptive hour -> minute -> 2s descent, paginating only what is actually dense."""
    d0 = datetime.strptime(day + " 00:00:00", F)
    seen, kept = set(), []

    def keep(rows):
        for r in rows:
            u = r.get("push_uuid")
            # inclusive `end` makes adjacent windows overlap by one second
            if u not in seen:
                seen.add(u)
                kept.append(r)

    def peek(w):
        r = api.get(LIST_PATH, _params(w))
        return w, (r.get("pushes") or []), bool(r.get("next_page"))

    def drain(w):
        rows, pages = [], 0
        for page in api.paginate(LIST_PATH, _params(w)):
            rows.extend(page)
            pages += 1
        prog.tick(pages, len(rows))
        return rows

    for w, rows, more in ex.map(peek, tile(d0, d0 + timedelta(days=1), 3600)):
        if not rows:
            continue
        if not more:                       # whole hour fit in one page
            keep(rows)
            prog.tick(1, len(rows))
            continue
        dense = []
        for mw, mrows, mmore in ex.map(peek, tile(w[0], w[1] + timedelta(seconds=1), 60)):
            if not mrows:
                continue
            if not mmore:                  # whole minute fit in one page
                keep(mrows)
                prog.tick(1, len(mrows))
            else:
                dense.append(mw)
        leaves = [lf for mw in dense
                  for lf in tile(mw[0], mw[1] + timedelta(seconds=1), LEAF_SECONDS)]
        for chunk in ex.map(drain, leaves):
            keep(chunk)

    return _summarise_day(day, kept)


def _summarise_day(day, rows, keep=KEEP_PER_DAY):
    """Aggregate a day losslessly, and keep a bounded sample of the rows themselves.

    The aggregate carries the day's true totals, so no volume is lost. But a review
    also needs actual `push_uuid`s — `perpush/detail` for per-message rates and
    `perpush/pushbody` for creatives are per-push endpoints, and a day summary has no
    id to call them with. Keeping every row is not an option (this is a firehose:
    ~2.9M pushes/day on the account this was measured against), so the sample is
    chosen rather than truncated:

      * the largest sends of the day — the marquee broadcasts a report showcases, and
        on a groupless firehose where the median push delivers 0, the only ones that
        delivered at volume at all;
      * rows carrying a `group_id` — the program layer, when the account has one.

    `sampled_of` records what the sample is a sample of, so coverage can be stated
    rather than assumed.
    """
    by_min, types, hist = {}, Counter(), Counter()
    sends = direct = influenced = 0
    groups = set()
    for r in rows:
        # `nonneg`, not `int`: several Reports API counters use `-1` for "not applicable"
        # rather than null, and a sentinel that is also a number subtracts from a total
        # instead of being skipped.
        s = nonneg(r.get("sends"))
        dr = nonneg(r.get("direct_responses"))
        ir = nonneg(r.get("influenced_responses"))
        sends += s
        direct += dr
        influenced += ir
        types[r.get("push_type") or "?"] += 1
        hist[min(s, 10)] += 1
        if r.get("group_id"):
            groups.add(r["group_id"])
        b = by_min.setdefault((r.get("push_time") or "")[:16], [0, 0, 0])
        b[0] += 1
        b[1] += s
        b[2] += dr

    top = sorted(rows, key=lambda r: -int(r.get("sends") or 0))[:keep]
    grouped = [r for r in rows if r.get("group_id")][:keep]
    sample, seen_u = [], set()
    for r in top + grouped:
        u = r.get("push_uuid")
        if u and u not in seen_u:
            seen_u.add(u)
            sample.append(r)

    return {
        "date": day,
        "pushes": len(rows),
        "sends": sends,
        "direct_responses": direct,
        "influenced_responses": influenced,
        "push_types": dict(types),
        "distinct_group_ids": len(groups),
        "sends_per_push_hist": {str(k): v for k, v in sorted(hist.items())},
        "by_minute": by_min,
        "sample": sample,
        "sampled_of": len(rows),
        "sample_basis": f"top {keep} by sends + up to {keep} carrying a group_id",
    }


def enumerate_days(api, days, out_dir, workers=WORKERS, resume=True, should_stop=None):
    """Exhaustively enumerate an explicit list of days, one JSON file per day.

    Taking the days as a list rather than a range is what lets a caller enumerate a
    *stated subset* of a window when the full pass is intractable, and then report the
    subset as measured coverage.

    `should_stop()` is consulted BETWEEN days, which is where stopping is free: each day
    is written as it completes, so an interrupted run keeps every finished day instead of
    losing the lot to an external kill.
    """
    os.makedirs(out_dir, exist_ok=True)
    prog = _Progress()
    written = []
    with ThreadPoolExecutor(workers) as ex:
        for day in days:
            if should_stop and should_stop():
                print(f"[stop] deadline reached before {day} — "
                      f"{len(written)}/{len(days)} days enumerated", flush=True)
                break
            dest = os.path.join(out_dir, day + ".json")
            if resume and os.path.exists(dest):
                print(f"[skip] {day}", flush=True)
                written.append(dest)
                continue
            t0 = time.time()
            rec = _collect_day(api, day, ex, prog)
            rec["elapsed_s"] = round(time.time() - t0, 1)
            with open(dest, "w", encoding="utf-8") as fh:
                json.dump(rec, fh, ensure_ascii=False)
            written.append(dest)
            print(f"[done] {day}  pushes={rec['pushes']:,}  sends={rec['sends']:,}  "
                  f"direct={rec['direct_responses']:,}  kept={len(rec['sample'])}  "
                  f"{rec['elapsed_s']}s", flush=True)
    print(f"ALL DONE — {api.calls} API calls, {prog.pages} paginated pages")
    return written


def enumerate_window(api, start, end, out_dir, workers=WORKERS, resume=True):
    """Exhaustively enumerate the half-open range [start, end), a day at a time.

    `end` is EXCLUSIVE here, matching `_days`. Callers holding an INCLUSIVE end (the
    Reports API convention this skill uses everywhere else) must add a day first.
    """
    return enumerate_days(api, list(_days(start, end)), out_dir,
                          workers=workers, resume=resume)


def load_days(pushes_dir):
    """Load the per-day records written by enumerate_window, sorted by date."""
    out = []
    for name in sorted(os.listdir(pushes_dir)):
        if name.endswith(".json"):
            with open(os.path.join(pushes_dir, name), encoding="utf-8") as fh:
                out.append(json.load(fh))
    return out


# ---------------------------------------------------------------------------
# 4. sample — alerting / silent / rich split, with drift detection
# ---------------------------------------------------------------------------
_SPLIT_KEYS = ("sends", "alerting_sends", "silent_sends", "rich_sends",
               "direct_responses", "influenced_responses")


def _drift(per_day, key="silent_share"):
    """Is a sampled rate stable enough to be reported as one number?

    A blended rate hides a regime change: on one account the silent-push share sat at
    2-4% until mid-July then jumped to 17-23%, and the 13.7% average described no
    actual day. Callers must surface the trend instead of the mean when this fires.
    """
    vals = [(d["day"], d[key]) for d in per_day if d.get(key) is not None]
    if len(vals) < 3:
        return {"drifting": False, "reason": "not enough sampled days to judge"}
    rates = [v for _, v in vals]
    lo, hi = min(rates), max(rates)
    half = len(rates) // 2
    first, second = statistics.fmean(rates[:half]), statistics.fmean(rates[-half:])
    spread = hi - lo
    ratio = (hi / lo) if lo > 0 else float("inf")
    drifting = spread >= 0.05 and ratio >= 2.0
    return {
        "drifting": drifting,
        "min": round(lo, 4), "max": round(hi, 4), "spread": round(spread, 4),
        "first_half_mean": round(first, 4), "second_half_mean": round(second, 4),
        "direction": "rising" if second > first else "falling",
        "by_day": [(d, round(v, 4)) for d, v in vals],
        "reason": ("rate is NOT stable across the window — report the trend and the "
                   "breakpoint, not the blended mean"
                   if drifting else "rate is stable enough to report blended"),
    }


def _weighted_pick(rows, k, rng, weight=lambda r: int(r.get("sends") or 0)):
    """`k` rows sampled without replacement, with probability proportional to `weight`.

    Exponential-key selection: key = U^(1/w), keep the k largest. Rows of weight 0 are
    excluded, and that is the point — the statistic being estimated is a share of SENDS, so
    a push that sent to nobody carries none of it and a call spent on it buys nothing.

    Uniform sampling over push ids is what made this misleading: on a sports account whose
    median push delivers 0, 200 uniformly drawn pushes carried 68 sends between them and
    were used to describe 3.56 billion.
    """
    keyed = []
    for r in rows:
        w = weight(r)
        if w > 0:
            keyed.append((rng.random() ** (1.0 / w), r))
    keyed.sort(key=lambda kv: -kv[0])
    return [r for _, r in keyed[:k]]


def sample_split(api, start, end, per_day=200, pool=1200, max_days=8, seed=42,
                 workers=8, sends_by_day=None):
    """Sample pushes per day and resolve `perpush/detail` for the alerting/silent/rich split.

    `/api/reports/sends` counts ALERTING notifications only; `responses/list` `sends`
    also counts silent data-only pushes. `perpush/detail` is the only endpoint that
    separates them, and it is per-push — hence sampling, reported with its sample size.

    The draw is WEIGHTED BY SENDS, because the quantity being estimated is a share of
    volume: an unweighted draw over ids estimates the split of the median push, which on a
    firehose is a push that reached nobody. `sends_by_day` (from `/api/reports/sends`) turns
    the sample's weight into a stated share of the account instead of a sample size alone.
    """
    days = list(_days(start, end))
    step = max(1, len(days) // max_days)
    picked = days[::step][:max_days]
    rng = random.Random(seed)

    def one_day(day):
        rows_in = []
        for page in api.paginate(LIST_PATH, {"start": f"{day} 00:00:00",
                                             "end": f"{day} 23:59:59",
                                             "limit": PAGE_LIMIT}):
            rows_in.extend(r for r in page if r.get("push_uuid"))
            if len(rows_in) >= pool:
                break
        if not rows_in:
            return None
        pool_sends = sum(int(r.get("sends") or 0) for r in rows_in)
        chosen_rows = _weighted_pick(rows_in, per_day, rng)
        weighted = bool(chosen_rows)
        if not weighted:
            # every candidate sent to nobody: there is no volume to weight by, so fall back
            # to uniform and let the coverage figures say the sample carries no volume
            chosen_rows = rng.sample(rows_in, min(per_day, len(rows_in)))
        chosen = [r["push_uuid"] for r in chosen_rows]
        chosen_sends = sum(int(r.get("sends") or 0) for r in chosen_rows)

        def detail(u):
            try:
                return api.get(DETAIL_PATH + u)
            except Exception:
                return None

        with ThreadPoolExecutor(workers) as ex:
            rows = [r for r in ex.map(detail, chosen) if r]
        day_sends = (sends_by_day or {}).get(day)
        agg = {"day": day, "n_pushes": len(rows), "pool": len(rows_in),
               "weighted": weighted,
               "pool_sends": pool_sends,
               "sampled_sends_of_pool": chosen_sends,
               "pool_share_sampled": (round(chosen_sends / pool_sends, 4)
                                      if pool_sends else None),
               "reports_sends_day": day_sends,
               # The number that decides whether the split may be published at all: what
               # share of the day the sampled pushes actually carry.
               "day_share_sampled": (round(chosen_sends / day_sends, 5)
                                     if day_sends else None)}
        # `nonneg` on every counter: `perpush/detail` returns `-1` for a metric that does
        # not apply to a message (`rich_read` on a plain push), and summing that sentinel
        # silently subtracts from the day's total rather than skipping the row.
        for k in _SPLIT_KEYS:
            agg[k] = sum(nonneg(r.get(k)) for r in rows)
        for plat in ("ios", "android"):
            agg[f"{plat}_sends"] = sum(
                nonneg((r.get("platforms", {}).get(plat) or {}).get("sends"))
                for r in rows)
        agg["silent_share"] = agg["silent_sends"] / agg["sends"] if agg["sends"] else None
        agg["rich_share"] = agg["rich_sends"] / agg["sends"] if agg["sends"] else None
        print(f"  {day}: n={agg['n_pushes']} sends={agg['sends']} "
              f"silent={agg['silent_sends']} ({(agg['silent_share'] or 0):.1%}) "
              f"rich={agg['rich_sends']}", flush=True)
        return agg

    per = [a for a in (one_day(d) for d in picked) if a]
    tot = {k: sum(a[k] for a in per) for k in _SPLIT_KEYS}
    tot["n_pushes"] = sum(a["n_pushes"] for a in per)
    tot["silent_share"] = tot["silent_sends"] / tot["sends"] if tot["sends"] else None
    tot["rich_share"] = tot["rich_sends"] / tot["sends"] if tot["sends"] else None
    tot["sampled_sends"] = sum(a["sampled_sends_of_pool"] for a in per)
    day_totals = sum(a["reports_sends_day"] or 0 for a in per)
    tot["reports_sends_sampled_days"] = day_totals or None
    tot["day_share_sampled"] = (round(tot["sampled_sends"] / day_totals, 5)
                                if day_totals else None)
    tot["weighted_days"] = sum(1 for a in per if a["weighted"])
    share = tot["day_share_sampled"]
    return {
        "days": per,
        "total": tot,
        # Whether the split may be published as an account-level rate. A sample carrying a
        # thousandth of the volume describes itself, and the alternative to saying so is a
        # number that reads as a measurement of the account.
        "publishable": bool(share is not None and share >= SAMPLE_SHARE_FLOOR),
        "coverage": (
            f"{tot['n_pushes']} pushes sampled across {len(per)} day(s), drawn with "
            f"probability proportional to sends, carrying {tot['sampled_sends']:,} of the "
            f"{day_totals:,} sends /api/reports/sends reports for those days"
            + (f" ({share:.3%}) — below the {SAMPLE_SHARE_FLOOR:.0%} floor, so the "
               f"alerting/silent/rich split describes the sample and must NOT be published "
               f"as an account rate"
               if share is not None and share < SAMPLE_SHARE_FLOOR else
               f" ({share:.1%}) — enough volume to report the split as an account rate"
               + (". Above 100% because responses/list counts silent pushes and "
                  "/api/reports/sends counts alerting ones only" if share > 1.0 else "")
               if share is not None else
               "; the authoritative day totals were not supplied, so the sample's weight "
               "in the account is unknown")),
        "silent_drift": _drift(per, "silent_share"),
        "rich_drift": _drift(per, "rich_share"),
        "note": "Random sample of pushes per day from responses/list, resolved with "
                "perpush/detail. Characterises the alerting/silent/rich split ONLY; "
                "volume KPIs must come from /api/reports/sends.",
    }


# ---------------------------------------------------------------------------
# 5. volume split — how much of the window is programmes vs the unitary stream
# ---------------------------------------------------------------------------
# A programme group in `pergroup/detail` does not say which channel it sends on, and an
# email programme lands in the same list as a push one. On the account that made this
# necessary, two groups fired at 06:31 and 15:05 every single day and carried about 1.5 M
# sends between them, which read as 3.1% push automation. It was not push: the two sums
# to 99.97% of the window's EMAIL volume, and both rows returned zero lifetime sends,
# direct and influenced, unlike every genuinely push-shaped group beside them. Real push
# automation on that account was 125 sends in thirty days — a difference of four hundred
# times, and six sections were written against the wrong one before it was caught.
#
# The detector below is deliberately conservative. Daily cadence and missing lifetime
# data only make a row a candidate; what decides is the arithmetic — the candidates have
# to account for essentially the whole email volume. Nothing is reclassified: the API
# cannot tell us the channel, so the output is a flag and a question for the account
# team.
_EMAIL_SHAPE_TOL = 0.02          # candidates must explain the email volume this closely
_EMAIL_SHAPE_MIN_PER_RUN = 100   # below this a daily group is a monitoring ping


def channel_ambiguous_programmes(rows, window_days, email_window_sends,
                                 tol=_EMAIL_SHAPE_TOL):
    """-> (flagged rows, diagnostic). Programme groups shaped like a daily email send.

    `rows` must carry `window_sends` and `occurrences`; lifetime response fields are read
    where present. Returns an empty list unless the candidates explain the window's email
    volume, so an account with no email, or with email that does not run daily, is never
    touched.
    """
    if not email_window_sends or not window_days:
        return [], {"checked": False, "reason": "no email volume in the window"}

    candidates = []
    for r in rows or []:
        occ = nonneg(r.get("occurrences"))
        win = nonneg(r.get("window_sends"))
        if occ < window_days - 1 or win < _EMAIL_SHAPE_MIN_PER_RUN * occ:
            continue
        if any(nonneg(r.get(k)) for k in
               ("lifetime_sends", "sends", "lifetime_direct", "lifetime_influenced",
                "direct_responses", "influenced_responses")):
            continue
        candidates.append(r)

    total = sum(nonneg(r.get("window_sends")) for r in candidates)
    match = total / email_window_sends if email_window_sends else 0.0
    diag = {
        "checked": True,
        "candidates": len(candidates),
        "candidate_window_sends": total,
        "email_window_sends": email_window_sends,
        "share_of_email_volume": round(match, 4),
        "tolerance": tol,
    }
    if not candidates or abs(match - 1.0) > tol:
        diag["verdict"] = (
            f"{len(candidates)} group(s) fire daily with no lifetime response data, "
            f"carrying {total:,} sends against {email_window_sends:,} of email — "
            f"{match:.1%} of it, which does not account for the email programme, so "
            f"they are read as push")
        return [], diag

    diag["verdict"] = (
        f"{len(candidates)} group(s) fire daily with no lifetime response data and carry "
        f"{total:,} sends between them — {match:.2%} of the window's email volume "
        f"({email_window_sends:,}). pergroup/detail does not report a group's channel, "
        f"so these are flagged channel-ambiguous and excluded from push automation. "
        f"Confirm the channel with the account team before publishing either reading.")
    return candidates, diag


def program_volume_split(pergroup, window_alerting_sends, window_days=None,
                         program_window_sends=None, email_window_sends=None):
    """Weigh the program layer against the window, alerting against alerting.

    Two traps make the obvious subtraction wrong, and both are handled here rather than
    left to a section author:

    **Mixed bases.** `/api/reports/sends` counts ALERTING notifications; a programme's
    `sends` also counts silent data-only pushes. Subtracting one from the other charges
    the silent share to the unitary stream — which matters, because on the account this
    was written for the silent share was itself drifting (8.2% -> 22.2%). So the split is
    computed on `alerting_sends`, which `pergroup/detail` reports separately.

    **`pergroup/detail` has no date parameters.** It aggregates the WHOLE programme, for
    all time. So the programme total is a CEILING on the programme's window contribution,
    never its value, and the residual is a FLOOR on the unitary stream. This returns that
    interval and refuses to name a point estimate: a ratio above 1 means the programmes'
    lifetime exceeds the window, which is expected and is not an error.

    `window_alerting_sends` must be the PUSH-only total. `/api/reports/sends` also returns
    `email` and `sms`, and passing its full row sum here inflates the denominator against
    an `alerting_sends` numerator — which is not a rounding difference: the same confusion
    one layer down overstated marketing pressure by 29% on one account. Callers should sum
    `channel_activity.PUSH_FAMILIES`.

    **The ceiling is only a ceiling when the endpoint answers.** It bounds the window
    because a programme's lifetime contains its window — unless the endpoint returns no
    lifetime total for the rows that actually sent, which happens. On one account all
    seven rows with window sends came back `sends: 0` and the entire lifetime total sat
    in three rows that had sent nothing for months, so the "ceiling" (2.3%) fell BELOW
    the measured window share (4.3%) and the audit asserted a bound that its own rows
    contradicted. Pass `program_window_sends`, or rows carrying `window_sends`, and the
    claim is checked before it is made: `bound_valid` says whether "at most" is true.
    """
    rows = list(pergroup.values()) if isinstance(pergroup, dict) else list(pergroup)
    life_alerting = sum(nonneg(g.get("alerting_sends")) for g in rows)
    life_sends = sum(nonneg(g.get("sends")) for g in rows)
    life_silent = sum(nonneg(g.get("silent_sends")) for g in rows)
    ratio = (life_alerting / window_alerting_sends) if window_alerting_sends else None
    capped = min(life_alerting, window_alerting_sends or 0)
    residual = max((window_alerting_sends or 0) - life_alerting, 0)

    # An email programme in this list would be counted as push automation, so it comes
    # out of the measured share before the share is computed, not after it is published.
    ambiguous, channel_diag = channel_ambiguous_programmes(
        rows, window_days, email_window_sends)
    ambiguous_ids = {id(r) for r in ambiguous}
    ambiguous_sends = sum(nonneg(r.get("window_sends")) for r in ambiguous)

    measured = program_window_sends
    if measured is None and any("window_sends" in (g or {}) for g in rows):
        measured = sum(nonneg(g.get("window_sends")) for g in rows
                       if id(g) not in ambiguous_ids)
    measured_share = ((measured / window_alerting_sends)
                      if measured is not None and window_alerting_sends else None)
    # Rounding alone must not invalidate a bound that holds; only a real inversion does.
    bound_valid = measured is None or measured <= capped * 1.001
    return {
        "programs": len(rows),
        "program_alerting_sends_lifetime": life_alerting,
        "program_sends_lifetime": life_sends,
        "program_silent_sends_lifetime": life_silent,
        "window_alerting_sends": window_alerting_sends,
        "window_days": window_days,
        "lifetime_to_window_ratio": round(ratio, 4) if ratio is not None else None,
        "program_share_ceiling": (round(capped / window_alerting_sends, 4)
                                  if window_alerting_sends else None),
        "program_window_sends_measured": measured,
        "program_share_measured": (round(measured_share, 4)
                                   if measured_share is not None else None),
        "bound_valid": bound_valid,
        "channel_ambiguous_programs": len(ambiguous),
        "channel_ambiguous_window_sends": ambiguous_sends,
        "channel_ambiguous_basis": channel_diag,
        "unitary_alerting_sends_floor": residual,
        "basis": "pergroup/detail alerting_sends (LIFETIME) vs /api/reports/sends "
                 "alerting sends (window) — different periods, deliberately",
        "publish_instead": ("the measured window share; the lifetime total does not "
                            "bound it on this account"
                            if not bound_valid else
                            "the window_sends column, and the share ceiling as a bound"),
        "verdict": (
            f"{len(rows)} programmes aggregate {life_alerting:,} alerting sends over their "
            f"lifetime against {window_alerting_sends:,} in the window"
            + (f" (x{ratio:.2f}); the programme layer alone exceeds the window, so it "
               f"carries essentially all of the account's volume and the unitary stream "
               f"is a rounding error on volume — its interest is typology, not tonnage."
               if ratio and ratio >= 1 else
               # The inversion, stated as the finding it is: the endpoint returned no
               # lifetime total for the rows that sent, so nothing here bounds anything.
               f"; the rows that sent this window carry {measured:,} sends "
               f"({measured_share:.1%} of it) while the lifetime total sits at "
               f"{life_alerting:,}, so pergroup/detail returned NO lifetime figure for "
               f"the programmes that ran and {capped / window_alerting_sends:.1%} is not "
               f"a bound. Publish the measured share."
               if not bound_valid and window_alerting_sends else
               f"; programmes account for AT MOST {capped / window_alerting_sends:.1%} of "
               f"the window and the unitary stream for AT LEAST "
               f"{residual / window_alerting_sends:.1%}."
               if window_alerting_sends else "")
            + (f" {len(ambiguous)} group(s) carrying {ambiguous_sends:,} sends are "
               f"excluded as channel-ambiguous: {channel_diag.get('verdict', '')}"
               if ambiguous else "")),
    }


# ---------------------------------------------------------------------------
# 6. reconcile — responses/list vs /api/reports/sends
# ---------------------------------------------------------------------------
def reconcile(enumerated_sends, reports_sends, split=None, basis=None):
    """Explain the gap between the two send counters. Returns a report-ready dict.

    `responses/list` counts every push Airship accepted (including silent data-only
    ones); `/api/reports/sends` counts alerting notifications. A report that quotes
    both without reconciling them contradicts itself.

    `basis` says WHAT was compared. Both sides must cover the same days: on a firehose
    account only a capped subset is enumerated, so passing window-wide `reports_sends`
    against those few days manufactures a ~-100% gap that no silent share can explain.

    When `basis["mode"] == "enumerated_days"` the ratio is the share of the day's sends
    that `responses/list` ATTRIBUTES to individual pushes — deliberately not called
    fidelity or coverage, which both read as a defect of the descent. Measured on a
    grocery firehose, the descent enumerated 0.476, 0.477 and 0.468 sends per push on
    three days whose reported sends varied fourfold: it was finding every push, but the
    volume of the account's 25 automation programmes is not attributed to any row and
    surfaces only through `pergroup/detail`. So a low ratio on such an account is a
    statement about the endpoint, and the residual is the programme layer's own volume.
    """
    gap = enumerated_sends - reports_sends
    gap_pct = (gap / reports_sends) if reports_sends else None
    silent_share = ((split or {}).get("total", {}) or {}).get("silent_share")
    out = {
        "responses_list_sends": enumerated_sends,
        "reports_sends": reports_sends,
        "gap": gap,
        "gap_pct": round(gap_pct, 4) if gap_pct is not None else None,
        "sampled_silent_share": round(silent_share, 4) if silent_share else None,
        "authoritative_for_volume": "/api/reports/sends",
    }
    if basis:
        out["basis"] = basis
    if (basis or {}).get("mode") == "enumerated_days" and reports_sends:
        cov = enumerated_sends / reports_sends
        out["attributed_share"] = round(cov, 4)
        out["unattributed_sends"] = reports_sends - enumerated_sends
        out["explained"] = cov >= 0.95
        out["verdict"] = (
            f"responses/list attributes {cov:.1%} of the alerting sends that "
            f"/api/reports/sends reports for the same {basis.get('day_count')} day(s)"
            + ("; per-push rows account for the day, so the enumerated set can carry "
               "volume."
               if cov >= 0.95 else
               f"; the remaining {reports_sends - enumerated_sends:,} sends are attributed "
               f"to no individual row. On a firehose that is the PROGRAMME layer, which "
               f"only pergroup/detail reports — check the sends-per-push ratio across "
               f"days: if it is stable while reported sends move, the descent is complete "
               f"and the gap is structural. Either way, never use the enumerated set as a "
               f"volume or rate denominator; volume comes from /api/reports/*."))
        drift = (split or {}).get("silent_drift") or {}
        if drift.get("drifting"):
            out["warning"] = (
                f"the silent share is {drift['direction']} across the window "
                f"({drift['min']:.1%} -> {drift['max']:.1%}); report the trend and its "
                f"breakpoint, not the blended mean")
        return out
    if silent_share is None:
        out["verdict"] = ("unexplained — run sample_split() to measure the silent share "
                          "before quoting either number")
        out["explained"] = False
        return out
    # silent pushes are the expected cause: they inflate responses/list but not /sends
    residual = abs((gap_pct or 0) - silent_share)
    out["residual_pct"] = round(residual, 4)
    out["explained"] = residual <= 0.05
    out["verdict"] = (
        f"gap of {gap_pct:.1%} is consistent with the sampled {silent_share:.1%} "
        f"silent (data-only) share — /sends excludes them"
        if out["explained"] else
        f"gap of {gap_pct:.1%} vs a sampled silent share of {silent_share:.1%} leaves "
        f"{residual:.1%} unexplained — check window alignment, de-duplication on "
        f"push_uuid, and whether the sample is representative")
    drift = (split or {}).get("silent_drift") or {}
    if drift.get("drifting"):
        out["warning"] = (
            f"the silent share is {drift['direction']} across the window "
            f"({drift['min']:.1%} -> {drift['max']:.1%}); report the trend and its "
            f"breakpoint, not the blended mean")
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
class _FakeApi:
    """Only what the oracle touches: `.paginate(path, params)` yielding pages of rows.

    Per-day behaviour is keyed off the window's own start date, which is what lets one fake
    stand in for a quiet day and a saturated one in the same call — the case that matters,
    since a single day straddling the threshold decides the whole collection strategy.
    """

    def __init__(self, by_day, default=(1, 10)):
        self.by_day = by_day
        self.default = default
        self.pages_served = 0

    def paginate(self, path, params):
        pages, rows = self.by_day.get(params["start"][:10], self.default)
        for _ in range(pages):
            self.pages_served += 1
            yield [{"push_uuid": f"u{i}"} for i in range(rows)]


def _selftest():
    """Pin the three behaviours that decide how an account gets collected."""
    rng = random.Random(42)

    # --- _weighted_pick: the sample estimates a share of SENDS, so a push that reached
    # nobody carries none of it. 200 uniform draws once carried 68 sends between them and
    # were used to describe 3.56 billion.
    rows = [{"push_uuid": "heavy", "sends": 1000}] + \
           [{"push_uuid": f"z{i}", "sends": 0} for i in range(99)]
    got = _weighted_pick(rows, 5, rng)
    assert len(got) == 1 and got[0]["push_uuid"] == "heavy", got
    # all-zero pool returns nothing, which is the signal sample_split needs to fall back to
    # uniform AND to declare the sample carries no volume
    assert _weighted_pick([{"sends": 0}] * 20, 5, rng) == []
    # weight actually biases the draw rather than merely filtering zeros
    pool = [{"push_uuid": "heavy", "sends": 1000}] + \
           [{"push_uuid": f"l{i}", "sends": 1} for i in range(99)]
    wins = sum(_weighted_pick(pool, 1, rng)[0]["push_uuid"] == "heavy" for _ in range(200))
    assert wins > 180, f"heavy row won only {wins}/200 draws"

    # --- _drift: a blended rate hides a regime change. One account sat at 2-4% until
    # mid-July then jumped to 17-23%, and its 13.7% average described no actual day.
    stable = _drift([{"day": f"d{i}", "silent_share": v}
                     for i, v in enumerate([0.10, 0.11, 0.10, 0.12])])
    assert stable["drifting"] is False and "stable" in stable["reason"], stable
    regime = _drift([{"day": f"d{i}", "silent_share": v}
                     for i, v in enumerate([0.02, 0.03, 0.04, 0.20, 0.22, 0.23])])
    assert regime["drifting"] is True and regime["direction"] == "rising", regime
    thin = _drift([{"day": "d0", "silent_share": 0.1}, {"day": "d1", "silent_share": 0.9}])
    # the early return, not a verdict invented from two points: no min/max to quote
    assert thin["drifting"] is False and "min" not in thin, thin

    # --- _oracle_days: the routing oracle must see the day that would make enumeration
    # unaffordable, and an evenly-spaced slice does not on a bimodal account. A cinema
    # chain was read as `dashboard` on ~469 pushes/day drawn from three of its calmest
    # days while its blast days ran to 600k sends.
    pdays = ["2026-09-01", "2026-09-06", "2026-09-11", "2026-09-16", "2026-09-21",
             "2026-09-26"]
    positional = pdays[:: max(1, len(pdays) // ORACLE_DAYS)][:ORACLE_DAYS]
    missed = 0
    for blast in pdays:
        vol = dict.fromkeys(pdays, 400)
        vol[blast] = 600_000
        picked = _oracle_days(pdays, vol)
        assert blast in picked, (blast, picked)
        assert len(picked) == ORACLE_DAYS, picked
        assert picked == sorted(picked), f"days stay chronological: {picked}"
        missed += blast not in positional
    assert missed == 3, f"the positional slice missed {missed}/6, expected 3"
    # No /api/reports/sends answer: fall back rather than not route at all.
    assert _oracle_days(pdays, {}) == positional
    assert _oracle_days(["2026-09-01"], {"2026-09-01": 5}) == ["2026-09-01"]

    # --- oracle_pushes_per_day: `is_floor` is the whole routing decision. False means the
    # count is exact and enumeration can be sized; True means it is a lower bound that
    # already clears the threshold, which is what separates firehose_groupless from
    # firehose_unattributed.
    day, day2 = "2026-07-01", "2026-07-02"
    quiet = _FakeApi({day: (1, 10)})
    r = oracle_pushes_per_day(quiet, [day], workers=4)
    assert r["is_floor"] is False and r["per_day"][0]["exact"] is True, r
    assert r["estimate"] == 480, r  # 48 half-hour windows x 1 page x 10 rows

    # a window that never runs out of pages is truncated at ORACLE_WINDOW_PAGE_CAP, and the
    # count must confess it even though the row total stays far below the budget
    capped = oracle_pushes_per_day(_FakeApi({day: (ORACLE_WINDOW_PAGE_CAP + 10, 1)}),
                                   [day], workers=4)
    assert capped["is_floor"] is True, capped
    assert capped["per_day"][0]["windows_capped"] == 48, capped
    assert capped["estimate"] == 48 * ORACLE_WINDOW_PAGE_CAP, capped

    # crossing the budget abandons the day's remaining windows: also a floor
    budget = oracle_pushes_per_day(_FakeApi({day: (1, ORACLE_STOP_AT + 1)}), [day],
                                   workers=4)
    assert budget["is_floor"] is True, budget
    assert budget["per_day"][0]["stopped_at_budget"] is True, budget

    # one exact day and one truncated day: the mean is a floor, and min/max expose the swing
    # a single-day probe would have hidden
    mixed = oracle_pushes_per_day(
        _FakeApi({day: (1, 10), day2: (ORACLE_WINDOW_PAGE_CAP + 5, 1)}), [day, day2],
        workers=4)
    assert mixed["is_floor"] is True, mixed
    assert mixed["min_day"] == 480 and mixed["max_day"] == 1440, mixed
    assert mixed["estimate"] == 960, mixed
    assert [p["exact"] for p in mixed["per_day"]] == [True, False], mixed["per_day"]

    # --- program_volume_split: the ceiling is a claim, and it can be false. Measured on
    # an account whose seven active groups all returned `sends: 0` while three dormant
    # ones carried the whole lifetime total.
    inverted = [{"alerting_sends": 0, "sends": 0, "window_sends": 2349}] * 7 + \
               [{"alerting_sends": 2879, "sends": 2879, "window_sends": 0}] * 3
    r = program_volume_split(inverted, 381_080)
    assert r["bound_valid"] is False, r
    assert r["program_share_measured"] > r["program_share_ceiling"], r
    assert "not a bound" in r["verdict"], r["verdict"]
    assert "measured window share" in r["publish_instead"], r
    # the ordinary shape, where lifetime does contain the window, is untouched
    ok = [{"alerting_sends": 50_000, "sends": 50_000, "window_sends": 12_000}] * 4
    r = program_volume_split(ok, 381_080)
    assert r["bound_valid"] is True and "AT MOST" in r["verdict"], r
    # rows collected before window_sends existed cannot invalidate anything
    assert program_volume_split([{"alerting_sends": 5000}], 381_080)["bound_valid"]

    # --- channel_ambiguous_programmes: two daily groups that were an email programme.
    # Nearly all of the window's email sends, against roughly 48 M push.
    email_rows = [{"occurrences": 30, "window_sends": 769_046, "lifetime_sends": 0},
                  {"occurrences": 29, "window_sends": 743_195, "lifetime_sends": 0}]
    push_rows = [{"occurrences": 4, "window_sends": 125, "lifetime_sends": 644_603},
                 # a daily monitoring ping: two sends a run, and not the email programme
                 {"occurrences": 30, "window_sends": 60, "lifetime_sends": 0}]
    flagged, diag = channel_ambiguous_programmes(email_rows + push_rows, 30, 1_512_633)
    assert len(flagged) == 2 and diag["share_of_email_volume"] == 0.9997, diag
    r = program_volume_split(email_rows + push_rows, 48_316_323, window_days=30,
                             email_window_sends=1_512_633)
    assert r["program_window_sends_measured"] == 185, r    # 125 + the 60-send ping
    assert r["channel_ambiguous_window_sends"] == 1_512_241, r
    # a daily group that does NOT account for the email volume stays push
    flagged, diag = channel_ambiguous_programmes(
        [{"occurrences": 30, "window_sends": 12_777, "lifetime_sends": 0}], 30, 266_898)
    assert flagged == [] and "read as push" in diag["verdict"], diag
    # an account with no email is never touched
    assert channel_ambiguous_programmes(email_rows, 30, 0)[0] == []

    print("push_firehose self-test OK")
    return 0


def _dump(obj, path=None):
    text = json.dumps(obj, ensure_ascii=False, indent=1)
    if path:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"wrote {path}")
    else:
        print(text)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]

    if cmd == "selftest":
        sys.exit(_selftest())
    elif cmd == "probe":
        api = Airship(sys.argv[2])
        _dump(probe(api, sys.argv[3], sys.argv[4]))
    elif cmd == "discover":
        api = Airship(sys.argv[2])
        out = sys.argv[5] if len(sys.argv) > 5 else None
        _dump(discover_groups(api, sys.argv[3], sys.argv[4]), out)
    elif cmd == "enumerate":
        api = Airship(sys.argv[2])
        out_dir = sys.argv[5] if len(sys.argv) > 5 else "data/pushes"
        enumerate_window(api, sys.argv[3], sys.argv[4], out_dir)
    elif cmd == "sample":
        api = Airship(sys.argv[2])
        out = sys.argv[5] if len(sys.argv) > 5 else None
        _dump(sample_split(api, sys.argv[3], sys.argv[4]), out)
    elif cmd == "reconcile":
        days = load_days(sys.argv[2])
        enumerated = sum(d["sends"] for d in days)
        with open(sys.argv[3], encoding="utf-8") as fh:
            sends_doc = json.load(fh)
        reports_sends = (sends_doc if isinstance(sends_doc, int)
                         else sends_doc.get("sends") or sends_doc.get("total"))
        split = None
        if len(sys.argv) > 4:
            with open(sys.argv[4], encoding="utf-8") as fh:
                split = json.load(fh)
        _dump(reconcile(enumerated, int(reports_sends), split))
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
