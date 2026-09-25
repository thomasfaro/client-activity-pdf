#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared Reports-API collector for the engagement review — one script, every account.

Replaces the per-client `collect*.py` that each review used to re-author (176 L on one
account, 518 L across four files on another, plus a firehose pass on a third). It
drives `airship_api.Airship` (thread-safe, OAuth from `~/.cursor/mcp.json`) and writes
the canonical `data/*.json` set every `analyze.py` already expects.

    python scripts/collect.py "CLIENT PROD" \
        --start 2026-06-28 --end 2026-07-27 --out work/<client>/data
    python scripts/collect.py --selftest        # offline, no project, no API

Design rules this file encodes (they are review-correctness rules, not style):

  * **One doubled-window pull, sliced in code.** `sends`/`opens`/`optins`/`optouts` are
    requested ONCE over `[prior_start, current_end]` at DAILY precision — 4 calls, not 8
    — so every KPI can carry a period-over-period delta. `/devices` stays a point-in-time
    snapshot with no window (label it "(snapshot)").
  * **`end` is INCLUSIVE.** Windows are tiled as [t, t+span-1]; adjacent windows overlap
    by one second, so every push list is de-duplicated on `push_uuid`.
  * **Decode once.** `perpush/pushbody` results are cached in `pushbodies.json` and reused
    by every downstream step; a re-run never re-decodes what is already on disk.
  * **Shape first.** `push_firehose.probe` classifies the account before any push
    collection; `firehose_*` accounts switch to exhaustive time-partitioned enumeration
    plus program-level rollup instead of naive per-push pagination.
  * **Coverage is measured, not claimed.** Every stage records pages, rows, API calls and
    wall time in `collect_manifest.json`, which the report's methodology section cites.

Stages run in dependency order and are individually resumable: a stage whose output
files all exist is skipped unless `--force`. Run a subset with `--stages core,events`.

Per-account extras belong in a `collect_hook.py` next to the output directory (see
`--hook`); this collector stays the shared 90 %.

Scope: `rpt` (Reports) only. Read-only.
"""

import argparse
import atexit
import concurrent.futures as cf
import json
import os
import sys
import threading
import time
from collections import Counter
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from airship_api import Airship  # noqa: E402
import activity_log  # noqa: E402
import channel_activity  # noqa: E402
import push_firehose  # noqa: E402

DAY = "%Y-%m-%d"


def _acquire_lock(out_dir):
    """Fail fast if another collector already owns `out_dir`.

    Two collectors on one output directory interleave writes to the same `data/*.json`
    and double the API spend against a single project's rate limit. The failure is silent
    — files look plausible — so this refuses to start rather than warn. A lock whose
    owner is gone (crash, kill) is stale and gets reclaimed.
    """
    lock = os.path.join(out_dir, ".collect.lock")
    for attempt in (1, 2):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                owner = int(open(lock).read().split()[0])
            except (ValueError, IndexError, OSError):
                owner = None
            alive = False
            if owner:
                try:
                    os.kill(owner, 0)
                    alive = True
                except (ProcessLookupError, PermissionError) as exc:
                    alive = isinstance(exc, PermissionError)
            if alive:
                sys.exit(
                    f"collect.py: {out_dir} is already being collected by pid {owner}.\n"
                    f"  Wait for it, or stop it and re-run. Concurrent collectors corrupt\n"
                    f"  data/*.json and burn the project's shared rate limit.\n"
                    f"  If you are certain pid {owner} is gone: rm {lock}")
            if attempt == 1:
                os.unlink(lock)  # stale: reclaim and retry once
                continue
            raise
        else:
            os.write(fd, f"{os.getpid()} {datetime.now().isoformat()}\n".encode())
            os.close(fd)
            atexit.register(lambda: os.path.exists(lock) and os.unlink(lock))
            return

# Activity-log reads, budgeted PER HOUR rather than per day. The cursor descends in time, so
# a per-day page cap keeps the newest rows of the day and nothing else: measured on a sports
# account, 10 pages/day returned 1,000 rows all stamped between 23:55 and 23:59:58 — 0.1% of
# the day, always the same slice before midnight, and the stage still described itself as
# reading the "first" pages. A push sent at 15:00 could not appear at all, which matters
# because these rows are what rank the messages `details` and `bodies` enrich.
#
# Budgeting by hour costs a little more and buys 24 evenly spread samples instead of one.
# Depth is MEASURED, not assumed: the same endpoint holds 9 rows a day on a grocery retailer
# and ~13,000 an HOUR on the sports account, so no constant serves both — a shallow log is
# drained whole and only a deep one is budgeted.
ACTIVITY_PAGES_PER_HOUR = 5
ACTIVITY_PROBE_HOURS = (2, 10, 15, 21)

# How much of the window's delivered volume the per-message stages must cover, and the
# hard cap that backs it up. This one list sets the fan-out of BOTH `details` and `bodies`,
# so its length is the single biggest lever on run time: measured on a sports account the
# two stages spent 1,616 s of a 2,139 s run resolving 31,929 ids each, and 95.7% of those
# messages delivered to nobody.
#
# A share, not a constant, because volume concentration differs by an order of magnitude
# between accounts and a constant is wrong on one side or the other. Measured: the top 500
# messages carry 99.15% of delivered volume on a streaming account and 99.93% on a sports
# one, but only 71.04% on a grocery retailer, which needs ~1,400 to reach the same place.
# Going from 500 to 10,000 buys 0.05 points on the first — 20x the calls for nothing.
DETAIL_VOLUME_SHARE = 0.99
DETAIL_HARD_CAP = 4000
# Floor for accounts where almost nothing delivered, so a 99% share would resolve a handful
# of ids and leave the creative sections with nothing to show.
DETAIL_MIN_IDS = 300
# `responses/list` carries `sends` but NOT `rich_sends` (verified keys: direct_responses,
# group_id, open_channels_sends, push_time, push_type, push_uuid, sends). A Message Center
# sent without a notification therefore enters the inventory at `sends: 0` — correctly, it
# emitted no alerting notification — and its real delivery is only visible on
# `perpush/detail` as `rich_sends`. Ranking on `sends` alone makes that class of message
# permanently invisible, so a small evenly-spread sample of zero-send rows is resolved for
# the sole purpose of finding them. Cheap: tens of calls against a budget of hundreds.
DETAIL_INBOX_PROBE = 25
# `/api/reports/events` rejects `page_size >= 100`, so 99 is the largest page it will
# serve. Stated rather than left to the default: this endpoint is latency-bound at ~3.5s
# a call, the default is small, and an unstated page size is a silent multiplier on the
# slowest stage in the run.
EVENTS_PAGE_SIZE = 99

# endpoint -> the response keys that may carry the row array (Airship is inconsistent)
ROW_KEYS = {
    "/api/reports/sends": ("sends",),
    "/api/reports/opens": ("opens",),
    "/api/reports/optins": ("optins",),
    "/api/reports/optouts": ("optouts",),
    "/api/reports/events": ("events",),
    "/api/reports/responses/list": ("pushes",),
    "/api/reports/activity/details": ("activity", "activities", "details", "results"),
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def ts(day, end=False):
    """A day string -> an inclusive-bound Reports API timestamp."""
    return f"{day}T23:59:59" if end else f"{day}T00:00:00"


def shift(day, days):
    return (datetime.strptime(day, DAY) + timedelta(days=days)).strftime(DAY)


def _partial_coverage(claimed, cuts):
    """The coverage line a stage is entitled to once it has been cut short.

    A stage composes its `coverage` string before it knows whether it will be allowed to
    finish, so the claim is a hardcoded intention rather than a measurement. Beside a
    `partial` status it reads as a contradiction at best and is believed at worst — one
    run trusted "100% of 30d window (every next_page followed)" on a stage the deadline
    had stopped at 9% of the window, and only noticed a pass later.

    The original claim is kept, marked as unearned, because it still says what the stage
    was trying to do and dropping it would make two manifests harder to compare.
    """
    why = "; ".join(sorted({str(c.get("why") or "cut short") for c in cuts}))
    got = ", ".join(f"{c.get('what')} stopped at {c.get('collected')}" for c in cuts[:3])
    note = f"INCOMPLETE — {got} ({why})"
    if claimed:
        note += f"; the stage's own target was \u201c{claimed}\u201d and was not reached"
    return note


def _activity_delivered(row):
    """Devices an activity-log row reached, for ranking.

    This used to drop `rich` on the grounds that it was a subset of `alerting`. It is
    not: measured on 217 production activity rows, 9 carry `rich > alerting`, and one
    carries `alerting=0, silent=0, rich=6` — a Message Center drop with no notification.
    Under the old arithmetic that row ranked at zero, so an entire class of message fell
    out of the detail set and could not appear in the report at all.

    Ranking wants the lower bound, not the additive total: it decides which messages are
    worth a `perpush/detail` call, and over-counting a notified message would push a
    genuinely larger one out of the budget.
    """
    return activity_log.reach_bound(row.get("details"))


def span_days(start, end):
    """Inclusive day count of [start, end]."""
    return (datetime.strptime(end, DAY) - datetime.strptime(start, DAY)).days + 1


def _inbox_probe_ids(groupless, vol, limit):
    """Zero-send `responses/list` rows to resolve, looking for inbox-only deliveries.

    A message at `sends: 0` is usually exactly that — a push to an empty segment, or one
    that reached nobody. But it is also how a Message Center sent without a notification
    appears, because `responses/list` does not carry `rich_sends`. There is no signal in
    the inventory to tell the two apart, so the sample is spread evenly across the window
    by send time rather than taken from its head: a run of zero-send rows is usually
    contiguous in time, and the first N would all come from the same incident.
    """
    if limit <= 0:
        return []
    rows = [p for p in groupless
            if p.get("push_uuid") and not vol.get(p["push_uuid"])]
    if not rows:
        return []
    rows.sort(key=lambda p: (str(p.get("push_time") or ""), p["push_uuid"]))
    seen, out = set(), []
    step = max(1, len(rows) // limit)
    for p in rows[::step]:
        if p["push_uuid"] not in seen:
            seen.add(p["push_uuid"])
            out.append(p["push_uuid"])
        if len(out) >= limit:
            break
    return out


# Every counter a detail response can carry. All of them zero, on an id the inventory
# saw deliver, is the signature of the API's worst failure mode — see
# `suspect_zero_details`.
_DETAIL_COUNTERS = ("sends", "alerting_sends", "silent_sends", "rich_sends",
                    "direct_responses", "influenced_responses", "rich_responses")


# `perpush/detail` returns 200 with every counter at zero — including `created: 0` — for a
# Create-and-Send message, even when `responses/list` reports real sends for it. Measured on
# an internal project: 15 of 15 `CREATE_AND_SEND_PUSH` rows behaved this way, and the same
# family is already documented as returning an empty `pushbody`. This is the endpoint not
# covering a message class, not an id of the wrong type, so it is classified rather than
# flagged — otherwise the gate fires on every account that uses Create-and-Send.
PERPUSH_UNCOVERED_TYPES = ("CREATE_AND_SEND_PUSH",)


def suspect_zero_details(details, expected, endpoint, not_covered=()):
    """Ids answered with every counter at zero although the inventory saw volume.

    The Reports API does not reject an identifier of a type an endpoint cannot serve. It
    answers `200` with a well-formed payload and every counter at zero, which reads as
    "this message reached nobody" and is indistinguishable from the truth. Measured in
    both directions on live projects: a Sequence group id returns 6,968 sends on
    `pergroup/detail` and `sends: 0` on `perpush/detail`, while a push id returns
    `rich_sends: 2` on `perpush/detail` and `rich_sends: 0` on `pergroup/detail`.

    Nothing in the response distinguishes the two cases, so the check has to come from
    outside it: the inventory already told us this id delivered, and the detail endpoint
    says it delivered nothing. One of them is wrong, and it is never the inventory.

    Also fires on a window that has not finished consolidating, which has the same shape
    and the same remedy — do not publish the zero.

    `not_covered` are ids of a message class this endpoint is known not to serve. They
    produce the identical payload and are separated out, because a gate that fires on a
    known limitation of the API teaches its reader to ignore it.
    """
    out, known = [], []
    skip = set(not_covered or ())
    for mid, exp in (expected or {}).items():
        if not activity_log.nonneg(exp):
            continue                        # the inventory saw nothing either: agreed
        d = (details or {}).get(mid)
        if not isinstance(d, dict) or d.get("_error"):
            continue                        # a failure is loud already
        if any(activity_log.nonneg(d.get(k)) for k in _DETAIL_COUNTERS):
            continue
        row = {"id": mid, "endpoint": endpoint,
               "inventory_volume": activity_log.nonneg(exp),
               "reason": "200 with every counter at zero"}
        if mid in skip:
            row["reason"] = f"{endpoint} does not cover this message class"
            known.append(row)
        else:
            out.append(row)
    out.sort(key=lambda r: -r["inventory_volume"])
    known.sort(key=lambda r: -r["inventory_volume"])
    return {"suspect": out, "not_covered": known}


def inbox_only_messages(details):
    """Messages from `perpush/detail` whose whole delivery is in `rich_sends`.

    A Message Center sent without a notification. `sends: 0` and `alerting_sends: 0` are
    the CORRECT figures for it — it emitted no alerting notification — so this is not an
    error to repair but a message whose volume has to be read from a different field.
    Reported so a section quotes `rich_sends` and labels the message, instead of showing
    a campaign that reached N people as a campaign that reached nobody.

    `rich_sends` also reaches devices opted OUT of push, which is why it can exceed
    `sends` on a message that did notify; that case is not inbox-only and not listed here.
    """
    out = []
    for mid, d in (details or {}).items():
        if not isinstance(d, dict) or d.get("_error"):
            continue
        if activity_log.nonneg(d.get("sends")):
            continue
        rich = activity_log.nonneg(d.get("rich_sends"))
        if not rich:
            continue
        out.append({"push_id": mid, "rich_sends": rich,
                    "rich_responses": activity_log.nonneg(d.get("rich_responses")),
                    "alerting_sends": activity_log.nonneg(d.get("alerting_sends")),
                    "kind": "message_center_no_notification",
                    "volume_field": "rich_sends",
                    "note": "sends: 0 is correct — no alerting notification was emitted"})
    out.sort(key=lambda r: -r["rich_sends"])
    return out


def rank_detail_ids(groupless, activity, reps=(), share=DETAIL_VOLUME_SHARE,
                    hard_cap=DETAIL_HARD_CAP, min_ids=DETAIL_MIN_IDS,
                    inbox_probe=DETAIL_INBOX_PROBE):
    """Rank every candidate message by delivered volume and take `share` of the total.

    Kept a module-level pure function so the cap can be re-measured against a cached
    account without credentials, a lock, or a live API — which is the only way the
    "does the cap retain the right messages" question gets an answer that is not an
    assertion.

    `reps` are programme representatives and bypass the ranking entirely: they are the
    identity of the programme layer, one row each, and a programme with no representative
    cannot be named in the report.

    `inbox_probe` adds a small sample of zero-send messages, which the ranking would
    otherwise never reach — see `_inbox_probe_ids`.
    """
    vol = {}
    for p in groupless:
        u = p.get("push_uuid")
        if u:
            vol[u] = max(vol.get(u, 0), int(p.get("sends") or 0))
    # An activity-log row of type GROUP carries a GROUP id in its `push_id` field, and
    # `perpush/detail` answers a group id with 200 and every counter at zero. Mixing them
    # into the per-push pool sent 18 group ids down the per-push endpoint on an internal
    # project, spent the calls, and would have stored zeros for programmes that had in
    # fact delivered. They belong to `pergroup/detail`, which `s_programs` already covers.
    group_ids = []
    for a in activity:
        i = a.get("push_id")
        if not i:
            continue
        if (a.get("type") or "").upper() == "GROUP":
            group_ids.append(i)
            continue
        vol[i] = max(vol.get(i, 0), _activity_delivered(a))
    group_ids = list(dict.fromkeys(group_ids))

    ranked = sorted(vol.items(), key=lambda kv: -kv[1])
    total = sum(v for _, v in ranked)
    target = total * share
    picked, run = [], 0
    for i, v in ranked:
        if run >= target and len(picked) >= min_ids:
            break
        if len(picked) >= hard_cap:
            break
        picked.append(i)
        run += v

    zeros = sum(1 for _, v in ranked if not v)
    reps = [r for r in reps if r]
    probe = [i for i in _inbox_probe_ids(groupless, vol, inbox_probe)
             if i not in set(picked) | set(reps)]

    def head(n):
        return (sum(v for _, v in ranked[:n]) / total) if total else None

    ids = list(dict.fromkeys(reps + picked + probe))
    return {
        "ids": ids,
        # What the inventory says each resolved id delivered, so `suspect_zero_details`
        # can catch an endpoint that answers 200-with-zeros for one of them. Only the
        # resolved ids, not the whole ranking, which runs to tens of thousands.
        "expected_volume": {i: vol.get(i, 0) for i in ids},
        # Group ids the activity log knows about, kept OUT of the per-push ranking. The
        # activity log can name a programme `responses/list` never showed a row for, so
        # `s_programs` compares this against its own set rather than assuming they match.
        "activity_group_ids": group_ids,
        "program_representatives": len(reps),
        # Resolved to find Message Center drops with no notification, not because the
        # ranking selected them. Never treat these as top messages.
        "inbox_probe_ids": probe,
        "ranked_candidates": len(ranked),
        "ranked_resolved": len(picked),
        "delivered_total": total,
        "delivered_covered": run,
        "delivered_share": round(run / total, 5) if total else None,
        "hit_hard_cap": len(picked) >= hard_cap,
        # Delivery concentration, published because it separates two pathologies the account
        # shape confuses: a targeting problem (a sports account where 95.7% of pushes
        # reached nobody) from an external orchestrator calling /api/push per recipient (a
        # streaming account at 1.5% zero-delivery but one send per push).
        "zero_delivery_pushes": zeros,
        "zero_delivery_share": (round(zeros / len(ranked), 4) if ranked else None),
        "top_100_share": round(head(100), 5) if total else None,
        "top_500_share": round(head(500), 5) if total else None,
        "basis": (f"{len(reps)} programme representatives (identity, always kept) + "
                  f"{len(picked)} of {len(ranked)} messages ranked by delivered volume, "
                  f"taken to {share:.0%} of the delivered total "
                  f"(hard cap {hard_cap:,}, floor {min_ids})"
                  + (f" + {len(probe)} zero-send messages probed for inbox-only "
                     f"delivery (rich_sends)" if probe else "")),
    }


class _GatedApi:
    """Airship with a ceiling on CONCURRENT requests, shared by every stage.

    Stage pools are sized to the full worker budget so a stage left alone in its wave runs
    at full speed, and the ceiling lives here instead — the only place that knows how many
    calls are actually in flight.

    Dividing the budget at dispatch was the alternative, and it cost nine minutes on one
    account: `activity` was handed a quarter of the threads because three siblings started
    beside it, then kept that quarter for the eight minutes it ran alone after they
    finished. A permit released the moment a call returns cannot make that mistake.
    """

    def __init__(self, api, permits):
        self._api = api
        self._sem = threading.BoundedSemaphore(max(1, permits))

    def __getattr__(self, name):
        return getattr(self._api, name)

    def get(self, *a, **k):
        with self._sem:
            return self._api.get(*a, **k)

    def paginate(self, *a, **k):
        # The permit covers fetching a page, not consuming it: a caller that walks 600 pages
        # must not hold a slot while it processes rows.
        it = self._api.paginate(*a, **k)
        while True:
            with self._sem:
                try:
                    page = next(it)
                except StopIteration:
                    return
            yield page


class Stage:
    """One collection step: what it writes, what it needs, what it measured."""

    def __init__(self, name, files, fn, needs=()):
        self.name = name
        self.files = list(files)
        self.fn = fn
        self.needs = tuple(needs)


# ---------------------------------------------------------------------------
# collector
# ---------------------------------------------------------------------------
class Collector:
    def __init__(self, project, start, end, out_dir, workers=16, shape=None,
                 prior=True, body_floor=500, body_cap=800, firehose_days=0,
                 stage_deadline=0):
        self.api = _GatedApi(Airship(project), workers)
        self.project = project
        self.stage_deadline = stage_deadline
        self._local = threading.local()
        self._lock = threading.Lock()
        self.cur = (start, end)
        self.days = span_days(start, end)
        self.prior = (shift(start, -self.days), shift(start, -1)) if prior else None
        self.doubled = ((self.prior[0] if self.prior else start), end)
        self.out = os.path.abspath(out_dir)
        self._workers_max = workers
        self.shape = shape
        self.body_floor = body_floor
        self.body_cap = body_cap
        self.firehose_days = firehose_days
        os.makedirs(self.out, exist_ok=True)
        _acquire_lock(self.out)
        self.manifest = {
            "project": project,
            "region": self.api.region,
            "generated": datetime.now().astimezone().isoformat(timespec="seconds"),
            "window": {
                "current": list(self.cur),
                "prior": list(self.prior) if self.prior else None,
                "doubled": list(self.doubled),
                "days": self.days,
            },
            "shape": shape,
            "stages": {},
        }
        self._cache = {}
        # `details` and `bodies` both fan out from the same ranked plan; computing it twice
        # would re-read and re-sort the whole activity log for nothing.
        self._dplan = None

    # -- io ----------------------------------------------------------------
    def path(self, name):
        return os.path.join(self.out, name)

    def save(self, name, obj):
        with open(self.path(name), "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False)
        size = os.path.getsize(self.path(name))
        print(f"    wrote {name} ({size:,} bytes)", flush=True)
        return {"file": name, "bytes": size}

    def load(self, name):
        """Read a previously collected file (cached in-process)."""
        with self._lock:
            if name not in self._cache:
                with open(self.path(name), encoding="utf-8") as fh:
                    self._cache[name] = json.load(fh)
            return self._cache[name]

    def has(self, *names):
        return all(os.path.isfile(self.path(n)) for n in names)

    @property
    def workers(self):
        """The full thread budget. Concurrency is capped per CALL, in `_GatedApi`."""
        return self._workers_max

    # -- deadlines ---------------------------------------------------------
    # Per-stage, and THREAD-LOCAL because independent stages run concurrently. Held on the
    # collector before that, one stage's truncation record would be attributed to whichever
    # stage happened to finish next, and one stage's deadline would silently cut another's
    # pagination short.
    def _arm(self, seconds):
        """Open a soft deadline for the calling stage. Falsy `seconds` disarms it."""
        self._local.deadline = (time.time() + seconds) if seconds else None
        self._local.truncated = []

    def expired(self):
        dl = getattr(self._local, "deadline", None)
        return dl is not None and time.time() > dl

    @property
    def _truncated(self):
        return getattr(self._local, "truncated", None) or []

    def _truncate(self, what, got, why="stage deadline"):
        """Record that `what` returned early, so the manifest can say so."""
        if getattr(self._local, "truncated", None) is None:
            self._local.truncated = []
        self._local.truncated.append({"what": what, "collected": got, "why": why})
        print(f"    [cut] {what} at {got} — {why}; continuing", flush=True)

    # -- network -----------------------------------------------------------
    def drain(self, path, params, label=None, max_pages=None):
        """Follow every next_page cursor. Returns (rows, pages).

        `max_pages` is a DECLARED sampling bound, not a failure: the caller asked for at
        most that many pages and is responsible for reporting the coverage it bought. It is
        deliberately not recorded as a truncation, unlike a deadline or a dead cursor.

        A cursor that dies mid-walk must truncate the pass, never discard the pages that
        already landed — the same rule `par` applies to a single failed push. A 30-day
        activity log on a sports account returned HTTP 500 on a deep `resume_id` and threw
        away 16,000 collected rows before this was symmetrical.
        """
        keys = ROW_KEYS.get(path, ("results",))
        out, pages, page = [], 0, self.api.get(path, params)
        while True:
            rows = next((page[k] for k in keys if isinstance(page.get(k), list)), [])
            out.extend(rows)
            pages += 1
            if pages % 10 == 0:
                print(f"    {label or path}: {pages} pages, {len(out):,} rows", flush=True)
            nxt = page.get("next_page")
            if not nxt or not rows:
                break
            if max_pages and pages >= max_pages:
                break
            if self.expired():
                self._truncate(f"{label or path} pagination", f"{pages} pages")
                break
            try:
                page = self.api.get(nxt)
            except Exception as e:  # noqa: BLE001
                self._truncate(f"{label or path} pagination", f"{pages} pages",
                               why=f"cursor died: {type(e).__name__}: {e}")
                break
        return out, pages

    def drain_summary(self, path, label=None, max_pages=None):
        """Fully drain one `events/summary/...` call into a single payload.

        Kept separate from `drain` because the caller needs the envelope, not just the
        rows: `group_id` and the totals are what the attribution analysis joins on.

        Two traps specific to this endpoint, both of which made an incomplete read look
        complete. Its page is **25 event names**, not the 100 its neighbours use, and it
        orders names alphabetically rather than by volume — so the cut falls in the
        middle of the taxonomy and lands hardest on the programmes with the richest one.
        And `total_count` / `total_value` are **page-scoped**: they match the rows in
        hand whatever page you stopped on, so they cannot be used to detect the loss and
        have to be summed across pages. `next_page` is the only signal there is.
        """
        first = self.api.get(path)
        out = {k: v for k, v in first.items() if k not in ("events", "next_page")}
        events = list(first.get("events") or [])
        count = first.get("total_count") or 0
        value = first.get("total_value") or 0.0
        page, pages = first, 1
        while True:
            nxt = page.get("next_page")
            if not nxt or not (page.get("events") or []):
                break
            if max_pages and pages >= max_pages:
                break
            if self.expired():
                self._truncate(f"{label or path} pagination", f"{pages} pages")
                break
            try:
                page = self.api.get(nxt)
            except Exception as e:  # noqa: BLE001
                self._truncate(f"{label or path} pagination", f"{pages} pages",
                               why=f"cursor died: {type(e).__name__}: {e}")
                break
            events.extend(page.get("events") or [])
            count += page.get("total_count") or 0
            value += page.get("total_value") or 0.0
            pages += 1
        out["events"] = events
        out["total_count"] = count
        out["total_value"] = value
        out["_pages"] = pages
        return out

    def par(self, fn, items, label=""):
        """Run `fn` over `items` in the thread pool; errors are captured, not raised.

        A single 404/403 on one push must never abort a collection that is otherwise
        complete — the failure is recorded under `_error` so the analysis can see it.
        """
        out, done, total = {}, 0, len(items)
        if not total:
            return out
        with cf.ThreadPoolExecutor(max_workers=self.workers) as ex:
            futs = {ex.submit(fn, i): i for i in items}
            for f in cf.as_completed(futs):
                key = futs[f]
                done += 1
                try:
                    out[key] = f.result()
                except Exception as e:  # noqa: BLE001
                    out[key] = {"_error": f"{type(e).__name__}: {e}"}
                if done % 100 == 0 or done == total:
                    print(f"    {label} {done}/{total}", flush=True)
                if self.expired() and done < total:
                    # Cancel what has not started, then HARVEST everything that already
                    # finished. Breaking straight out of `as_completed` discards results
                    # that are sitting there complete: on a sports account 14 activity-log
                    # day-walks each finished 600+ pages and all but one were thrown away.
                    for pending in futs:
                        pending.cancel()
                    for fut, k in futs.items():
                        if k in out or not fut.done() or fut.cancelled():
                            continue
                        try:
                            out[k] = fut.result()
                        except Exception as e:  # noqa: BLE001
                            out[k] = {"_error": f"{type(e).__name__}: {e}"}
                        done += 1
                    self._truncate(label or "parallel fan-out", f"{done}/{total}")
                    break
        return out

    # -- derived inventories ----------------------------------------------
    def pushes(self):
        """De-duplicated push rows for the current window (responses/list or firehose)."""
        rows = self.load("responses.json")["pushes"]
        seen, out = set(), []
        for p in rows:
            u = p.get("push_uuid")
            if u and u not in seen:
                seen.add(u)
                out.append(p)
        return out

    def groups(self):
        """group_id -> window aggregates, ordered by window sends (largest first)."""
        agg = {}
        for p in self.pushes():
            gid = p.get("group_id")
            if not gid:
                continue
            g = agg.setdefault(gid, {"sends": 0, "occurrences": 0,
                                     "first": None, "last": None, "rep": None})
            g["sends"] += p.get("sends") or 0
            g["occurrences"] += 1
            t = p.get("push_time")
            if t:
                g["first"] = min(g["first"] or t, t)
                g["last"] = max(g["last"] or t, t)
            if not g["rep"] or (p.get("sends") or 0) > (g["rep"].get("sends") or 0):
                g["rep"] = p
        return dict(sorted(agg.items(), key=lambda kv: -kv[1]["sends"]))

    def groupless(self):
        """Pushes with no group_id — the marquee broadcasts, largest first."""
        return sorted((p for p in self.pushes() if not p.get("group_id")),
                      key=lambda p: -(p.get("sends") or 0))

    def reports_sends_by_day(self):
        """`/api/reports/sends` ALL-CHANNEL totals per day, over the DOUBLED window.

        `sends.json` deliberately spans current + prior so trends can show a before/after,
        so any consumer wanting "the window" has to slice it. Returning the mapping rather
        than a total keeps that choice explicit at each call site.

        Every numeric column is summed, and that endpoint returns `email` and `sms`
        alongside the push platforms. So this is a messaging total, NOT push volume — the
        two differed by 29% on one account and the mistake is invisible in isolation. For
        push, use `_window_push_sends()`, which sums `channel_activity.PUSH_FAMILIES`.
        """
        out = {}
        for r in self.load("sends.json")["sends"]:
            if not isinstance(r, dict):
                continue
            day = str(r.get("date", ""))[:10]
            out[day] = out.get(day, 0) + sum(
                v for k, v in r.items() if k != "date" and isinstance(v, (int, float)))
        return out

    def window_reports_sends(self):
        """ALL-CHANNEL sends `/api/reports/sends` attributes to the CURRENT window.

        Named without a channel qualifier and previously described as alerting sends,
        which it is not: see `reports_sends_by_day`. Kept all-channel because that is what
        its callers have always measured against; anything published as push volume must
        come from `_window_push_sends()` instead.
        """
        return sum(v for k, v in self.reports_sends_by_day().items() if k >= self.cur[0])

    # ======================= stages ======================================
    def s_probe(self):
        info = push_firehose.probe(self.api, *self.cur)
        self.shape = self.shape or info["shape"]
        self.manifest["shape"] = self.shape
        print(f"    shape={info['shape']} · {info['sampled_pushes']} sampled · "
              f"mean sends/push={info['mean_sends_per_push']}", flush=True)
        self.save("probe.json", info)
        return {"shape": info["shape"], "sampled": info["sampled_pushes"]}

    def s_core(self):
        """devices snapshot + the four daily series over the DOUBLED window."""
        files, rows = [], {}
        files.append(self.save("devices.json", self.api.get("/api/reports/devices")))
        a, b = self.doubled

        def one(ep):
            got, pages = self.drain(f"/api/reports/{ep}",
                                    {"start": ts(a), "end": ts(b, True),
                                     "precision": "DAILY"}, label=ep)
            return ep, got, pages

        pages = 0
        with cf.ThreadPoolExecutor(max_workers=4) as ex:
            for ep, got, pg in ex.map(one, ("sends", "opens", "optins", "optouts")):
                files.append(self.save(f"{ep}.json", {ep: got}))
                rows[ep] = len(got)
                pages += pg
        return {"files": files, "rows": rows, "pages": pages,
                "window": list(self.doubled),
                "note": "one doubled-window pull, sliced current vs prior in analyze"}

    def s_events(self):
        """The custom-event taxonomy, bounded to the actual review window.

        `/events` returns a flat aggregate (event name x conversion x location -> count,
        value) with no date column; `precision` decides how the API buckets the window
        BEFORE aggregating, and MONTHLY snaps it out to whole months. Measured on a
        streaming account: a 28/06->27/07 request at MONTHLY answers for June+July and returns
        **11 event names that never fired inside the window** (`later_survey_preference`,
        `swipe-2-3`, …), which would inflate the conversion taxonomy and the "tracked but
        not fired" cross-reference. DAILY honours the exact window and reproduces the
        event set the shipped reviews actually quoted, so it is what `events.json` holds.
        The MONTHLY superset is still saved, clearly labelled, for month-level questions.
        """
        files, rows, pages = [], {}, 0
        jobs = [("events.json", self.cur, "DAILY"),
                ("events_monthly.json", self.cur, "MONTHLY")]
        if self.prior:
            jobs += [("events_prior.json", self.prior, "DAILY"),
                     ("events_monthly_prior.json", self.prior, "MONTHLY")]
        # `/events` is latency-bound, not volume-bound: measured at 3.5s per call for 117
        # calls, so the four jobs sequentially cost ~6.8 minutes of pure waiting. They
        # target distinct files and windows, so they parallelise like s_core just above.
        def one(job):
            name, win, prec = job
            got, pg = self.drain("/api/reports/events",
                                 {"start": ts(win[0]), "end": ts(win[1], True),
                                  "precision": prec, "page_size": EVENTS_PAGE_SIZE},
                                 label=name)
            return name, win, prec, got, pg

        with cf.ThreadPoolExecutor(max_workers=4) as ex:
            for name, win, prec, got, pg in ex.map(one, jobs):
                files.append(self.save(name, {"events": got, "pages": pg,
                                              "precision": prec, "window": list(win)}))
                rows[name] = len(got)
                pages += pg
        return {"files": files, "rows": rows, "pages": pages,
                "authoritative": "events.json (DAILY = exact window)",
                "caveat": "events_monthly.json covers WHOLE MONTHS, not the window — "
                          "do not feed it to the conversion taxonomy"}

    def s_activity(self):
        """The Flight Deck-aligned inventory of non-unicast sends, tiled one day at a time.

        A single 30-day cursor is both fragile and biased when it breaks: on a sports
        account it returned HTTP 500 on a deep `resume_id` at page 164, and a cursor that
        stops mid-walk loses a CONTIGUOUS block of the window (whichever end it was walking
        towards), not a thin slice of every day. Day tiles keep each walk a few pages deep,
        cost the same number of calls, run concurrently, and downgrade a cursor failure to
        one named missing day the report can disclose. Tiles are [00:00:00, 23:59:59] so the
        INCLUSIVE `end` bound cannot make two tiles share a row.
        """
        days = [shift(self.cur[0], i) for i in range(span_days(*self.cur))]
        depth = self._activity_depth(days[len(days) // 2])
        print(f"    activity depth: {depth['verdict']}", flush=True)

        if depth["deep"]:
            # Budget by hour. Every hour of every day gets read, so a 15:00 send is as
            # visible as a 23:59 one; the pages within an hour still come newest-first, so
            # each sample is the tail of its own hour rather than of the whole day.
            jobs = [(d, h) for d in days for h in range(24)]
            got = self.par(
                lambda j: self.drain("/api/reports/activity/details",
                                     {"start": f"{j[0]}T{j[1]:02d}:00:00",
                                      "end": f"{j[0]}T{j[1]:02d}:59:59", "limit": 100},
                                     max_pages=ACTIVITY_PAGES_PER_HOUR),
                jobs, label="activity hours")
            units, unit_of_day = jobs, (lambda u: u[0])
        else:
            got = self.par(lambda d: self.drain("/api/reports/activity/details",
                                                {"start": ts(d), "end": ts(d, True),
                                                 "limit": 100}),
                           days, label="activity days")
            units, unit_of_day = days, (lambda u: u)

        rows, pages, budgeted = [], 0, 0
        failed = {}
        for u in units:
            res = got.get(u)
            if res is None:                     # never ran: the stage was cut short
                failed.setdefault(unit_of_day(u), []).append("not collected")
            elif isinstance(res, dict):         # par() captured a hard failure
                failed.setdefault(unit_of_day(u), []).append(res.get("_error"))
            else:
                rows.extend(res[0])
                pages += res[1]
                if depth["deep"] and res[1] >= ACTIVITY_PAGES_PER_HOUR:
                    budgeted += 1

        by_hour = Counter(str(r.get("timestamp") or "")[11:13] for r in rows)
        missing = [{"day": d, "errors": e[:3], "units_failed": len(e)}
                   for d, e in sorted(failed.items())]
        info = {"files": [self.save("activity.json", {"activity": rows})],
                "rows": len(rows), "pages": pages,
                "days": len(days) - len(missing),
                "depth_probe": depth,
                # The one check that answers "did we miss the afternoon": how many distinct
                # hours of the day the retained rows actually fall in. 24 is the target; 1
                # is what a per-day page cap produced.
                "hours_covered": len(by_hour),
                "rows_by_hour": dict(sorted(by_hour.items())),
                # This endpoint carries push_id, timestamp, type and delivery counters — no
                # name, no group_id, on every account tested. It is an inventory of message
                # IDS and their delivery, never a campaign inventory, so a campaign COUNT
                # must never be taken from it.
                "carries_campaign_identity": False,
                # How far apart the two defensible reach totals are on THIS account, so a
                # section states an interval rather than an exact number it cannot support.
                "rich_overlap": activity_log.rich_overlap(rows)}
        if depth["deep"]:
            info["pages_per_hour_budget"] = ACTIVITY_PAGES_PER_HOUR
            info["hours_at_budget"] = budgeted
            info["coverage"] = (
                f"the newest {ACTIVITY_PAGES_PER_HOUR} pages of EACH of the 24 hours of "
                f"each day ({budgeted} of {len(units)} hour-walks exhausted their budget). "
                f"Rows land in {len(by_hour)} distinct hours, so the sample spans the day "
                f"rather than the minutes before midnight — but it is a SAMPLE: this log "
                f"holds ~{depth['rows_per_hour_estimate']:,} rows per hour on this account, "
                f"so it cannot be used as a send count, only to rank and identify messages")
        else:
            info["coverage"] = (
                f"complete — every day drained to exhaustion ({pages} pages for "
                f"{len(rows):,} rows), rows landing in {len(by_hour)} distinct hours")
        if missing:
            info["missing_days"] = missing
            print(f"    activity: {len(missing)} day(s) incomplete — "
                  f"{', '.join(m['day'] for m in missing)}", flush=True)
        return info

    def _activity_depth(self, day):
        """Is this account's activity log a handful of rows or a per-push ledger?

        Four spread hours, one page each. `next_page` on any of them means the log is deeper
        than a page an hour, which is the only thing the budgeting decision needs — and it
        costs four calls instead of the guess it replaces. Measured spread on real accounts:
        9 rows/day on a grocery retailer, 24 on a broadcaster, ~13,000 per HOUR on a sports
        account. A per-day constant is wrong by four orders of magnitude somewhere.
        """
        keys = ROW_KEYS["/api/reports/activity/details"]

        def peek(h):
            p = self.api.get("/api/reports/activity/details",
                             {"start": f"{day}T{h:02d}:00:00",
                              "end": f"{day}T{h:02d}:59:59", "limit": 100})
            rows = next((p[k] for k in keys if isinstance(p.get(k), list)), [])
            return len(rows), bool(p.get("next_page"))

        with cf.ThreadPoolExecutor(len(ACTIVITY_PROBE_HOURS)) as ex:
            got = list(ex.map(peek, ACTIVITY_PROBE_HOURS))
        deep = any(more for _, more in got)
        seen = [n for n, _ in got]
        # A probed hour that still has a cursor holds at least a page; the only honest
        # summary is a floor, and it is used for disclosure, never as a count.
        est = max(seen) * (100 if deep else 1)
        return {
            "probed_day": day,
            "probed_hours": list(ACTIVITY_PROBE_HOURS),
            "rows_per_probed_hour": seen,
            "any_hour_paginates": deep,
            "deep": deep,
            "rows_per_hour_estimate": est,
            "verdict": (f"deep — {sum(1 for _, m in got if m)} of "
                        f"{len(ACTIVITY_PROBE_HOURS)} probed hours still had a cursor after "
                        f"one page, so the log is budgeted per hour"
                        if deep else
                        f"shallow — {sum(seen)} rows across {len(ACTIVITY_PROBE_HOURS)} "
                        f"probed hours with no cursor left, so every day is drained whole"),
        }

    # Pages per second observed on a cursor-paginated `responses/list` walk. Measured at
    # 3.2 on the account that made this necessary — 11,401 calls for 11,401 pages, one
    # for one, which is the signature of a walk that cannot be parallelised: every
    # `next_page` token comes out of the response before it.
    SERIAL_PAGES_PER_SECOND = 3.2

    def _quote_enumeration(self):
        """Price the pagination before walking it, and say so out loud.

        `responses/list` is a cursor walk, so it is serial by construction and no worker
        count will help. On a groupless firehose the window holds one push per contact,
        and the walk runs into the hour — which is fine if it was chosen and expensive if
        it was not. One run met this blind: the stage deadline cut it at 9% of the window,
        the cut went unnoticed because the manifest claimed 100%, and the collection ended
        up taking 88 minutes across three passes.

        So the estimate is printed before the walk starts, next to the deadline that will
        stop it. Either the operator raises the deadline having seen the price, or they
        accept partial coverage and the report says which — both are defensible, and the
        point is that it becomes a decision instead of an outcome.
        """
        probe = self.load("probe.json") or {}
        per_day = probe.get("pushes_per_day_floor") or 0
        if not per_day:
            return None
        pushes = per_day * self.days
        pages = max(1, round(pushes / 100))
        seconds = pages / self.SERIAL_PAGES_PER_SECOND
        quote = {"projected_pushes": pushes, "projected_pages": pages,
                 "projected_seconds": round(seconds),
                 "exact": bool(probe.get("pushes_per_day_exact")),
                 "basis": "serial cursor walk at "
                          f"{self.SERIAL_PAGES_PER_SECOND} pages/s",
                 "stage_deadline_s": self.stage_deadline}
        note = ("" if quote["exact"] else " at least")
        print(f"    [quote]{note} ~{pushes:,} pushes over {self.days}d "
              f"= ~{pages:,} pages, ~{seconds / 60:.0f} min serial "
              f"(deadline {self.stage_deadline / 60:.0f} min)", flush=True)
        if seconds > self.stage_deadline:
            quote["exceeds_deadline"] = True
            print(f"    [quote] this WILL be cut short. Either re-run with "
                  f"--stage-deadline {int(seconds * 1.3)} for full coverage, or accept "
                  f"partial coverage and state it in the report — but decide now, not "
                  f"after the fact.", flush=True)
        return quote

    def s_responses(self):
        """Push inventory: straight pagination, or firehose enumeration by shape."""
        if self.shape == "firehose_grouped":
            return self._responses_programs()
        if self.shape == "firehose_unattributed":
            return self._responses_unattributed()
        if self.shape == "firehose_groupless":
            return self._responses_firehose()
        quote = self._quote_enumeration()
        got, pages = self.drain("/api/reports/responses/list",
                                {"start": ts(self.cur[0]), "end": ts(self.cur[1], True),
                                 "limit": 100}, label="responses")
        uniq = {p.get("push_uuid"): p for p in got if p.get("push_uuid")}
        dupes = len(got) - len(uniq)
        files = [self.save("responses.json",
                           {"pushes": list(uniq.values()), "pages": pages})]
        if self.prior:
            prior, ppg = self.drain("/api/reports/responses/list",
                                    {"start": ts(self.prior[0]),
                                     "end": ts(self.prior[1], True), "limit": 100},
                                    label="responses_prior")
            pu = {p.get("push_uuid"): p for p in prior if p.get("push_uuid")}
            files.append(self.save("responses_prior.json", {"pushes": list(pu.values())}))
            pages += ppg
        return {"files": files, "rows": len(uniq), "pages": pages,
                "deduplicated": dupes, "quote": quote,
                "coverage": f"{self.days}d window, every next_page followed"}

    def _responses_programs(self):
        """Grouped firehose: notice every programme, enumerate none of them.

        The two halves of such an account have opposite economics. A programme's volume
        and rates come from ONE `pergroup/detail` call that aggregates the whole
        programme, so seeing more of its pushes buys nothing — only its *identity* has to
        be found. The unitary stream around it is ~1M pushes/day whose median push
        delivers 0 sends; enumerating it bought a 27.4% coverage that the reconciler then
        declared unusable as a denominator, for 88.5% of the collection's runtime.

        So this stage scans spread windows on EVERY day of the window instead of
        exhausting three of them. `discover_groups` explains why the windows are spread
        rather than a capped prefix, and returns the discovery curve so `coverage` states
        what was reached instead of implying completeness.
        """
        disc = push_firehose.discover_groups(self.api, self.cur[0], shift(self.cur[1], 1),
                                             should_stop=self.expired)
        if disc.get("stopped_before"):
            self._truncate("group discovery",
                           f"{disc['days_scanned']}/{disc['days_in_window']} days")
        reps = disc["representatives"]
        files = [self.save("responses.json",
                           {"pushes": reps,
                            "source": "firehose_discover (one representative per group)",
                            "sample_basis": (f"largest-sending occurrence of each of the "
                                             f"{len(reps)} programmes found")}),
                 self.save("discovery.json", disc)]
        return {"files": files, "rows": len(reps),
                "groups_found": len(disc["group_ids"]),
                "days_scanned": disc["days_scanned"],
                "saturated": disc["saturated"],
                "api_calls": disc["api_calls"],
                "coverage": disc["coverage"]}

    def _window_push_sends(self):
        """Authoritative PUSH sends for the current window, from /api/reports/sends.

        `sends.json` spans the prior window too, so the rows have to be filtered by date —
        summing the file would compare a 30-day sample against 60 days of volume.

        The platform columns come from `channel_activity.PUSH_FAMILIES` rather than a list
        written out here. This function used to name `ios`, `android` and `web` inline and
        silently drop `amazon`, disagreeing with the other push-only total in the same
        skill; `/api/reports/sends` also returns `email` and `sms`, so the set of columns
        that means "push" is exactly the kind of thing that must be declared once.
        """
        if not self.has("sends.json"):
            return 0
        lo, hi = self.cur
        total = 0
        for r in (self.load("sends.json").get("sends") or []):
            day = str(r.get("date") or "")[:10]
            if lo <= day <= hi:
                total += sum(activity_log.nonneg(r.get(c))
                             for c in channel_activity.PUSH_FAMILIES)
        return total

    def _responses_unattributed(self):
        """Dense, nothing to roll up to, too dense to walk: sample and say so.

        This is the third case, and it exists because the first two are not exhaustive. A
        programme roll-up needs a programme layer; exhaustive enumeration needs a countable
        number of pushes. An account can lack both — a sports account whose 8 programmes
        carry 0.9% of a 3.37bn-send window while the other 99% arrives as ~16,000+ unitary
        pushes a day, each delivering a handful of subscribers.

        Sending that account down the groupless path was not a slow choice, it was an
        impossible one: 16 minutes into the adaptive descent of its FIRST day, nothing had
        been written. The full pass was hours away and would have added nothing the review
        used — the delivered report took volume from `/api/reports/sends`, the inventory from
        the activity log and typology from the weighted sample, and passed every gate.

        So: one scan of spread windows across every day, which yields both halves at once —
        each programme's identity, and the heaviest unitary rows as the typology sample.
        Volume is NOT taken from here. `coverage` states the sample's weight against
        `/api/reports/sends` so no downstream reader can mistake it for an inventory.
        """
        disc = push_firehose.discover_groups(
            self.api, self.cur[0], shift(self.cur[1], 1),
            workers=self.workers, should_stop=self.expired,
            keep_groupless=push_firehose.KEEP_PER_DAY)
        if disc.get("stopped_before"):
            self._truncate("unattributed scan",
                           f"{disc['days_scanned']}/{disc['days_in_window']} days")
        reps, solo = disc["representatives"], disc["groupless_sample"]
        window_sends = self._window_push_sends()
        share = (disc["groupless_sample_sends"] / window_sends) if window_sends else None
        files = [self.save("responses.json",
                           {"pushes": reps + solo,
                            "source": "firehose_unattributed (programme representatives + "
                                      "sends-ranked sample of the unitary stream)",
                            "sample_basis": (
                                f"{len(reps)} programme representative(s) and the "
                                f"{len(solo)} heaviest of {disc['groupless_seen']:,} "
                                f"ungrouped pushes seen while scanning")}),
                 self.save("discovery.json", disc)]
        return {"files": files, "rows": len(reps) + len(solo),
                "groups_found": len(disc["group_ids"]),
                "groupless_sampled": len(solo),
                "groupless_seen": disc["groupless_seen"],
                "days_scanned": disc["days_scanned"],
                "api_calls": disc["api_calls"],
                # The number that stops this sample being read as an inventory.
                "sample_sends_share_of_window": round(share, 6) if share else None,
                "enumerated": False,
                "coverage": (
                    f"NOT an inventory and not enumerable. {disc['coverage']} The unitary "
                    f"stream is represented by its {len(solo)} heaviest pushes, carrying "
                    + (f"{share:.3%} of the window's authoritative sends"
                       if share else "an unmeasured share of the window's sends")
                    + ". Volume comes from /api/reports/sends; this file carries push_uuids "
                      "for the per-push endpoints and nothing else.")}

    def _responses_firehose(self):
        """Time-partitioned enumeration, aggregated per day and sampled per day.

        `enumerate_window` writes one record per day: the day's true totals plus a
        bounded sample of the rows themselves (`push_firehose.KEEP_PER_DAY`). Both
        halves are needed and they answer different questions — the aggregate is the
        volume/shape truth, the sample is the only thing carrying `push_uuid`s for the
        per-push endpoints (`perpush/detail` rates, `pushbody` creatives).

        Two things this must not do, both learned the hard way on a grocery-retail
        firehose:

          * **Treat a day aggregate as a push row.** Filtering the day records on
            `push_uuid` — which no aggregate has — yields an empty inventory after
            hours of pagination, and every dependent stage (programs, details, bodies,
            split, attribution) then silently collects nothing.
          * **Pass an inclusive end to `_days`.** `_days` is half-open, so a 30-day
            window enumerated only 29 days.

        `--firehose-days N` caps how many days are enumerated. Exhaustive enumeration
        is ~2.9M pushes/day on that account (measured: ~1,500 pushes and 15 pages for a
        single peak MINUTE), i.e. tens of hours for a 30-day window. Capping is a
        TECHNICAL limit, so it is reported as measured coverage — days enumerated and
        the share of window sends they carry — never as a silent shortcut. The window
        volume KPI keeps coming from `/api/reports/sends`, which is authoritative.
        """
        pushes_dir = os.path.join(self.out, "pushes")
        days = list(push_firehose._days(self.cur[0], shift(self.cur[1], 1)))
        if self.firehose_days and self.firehose_days < len(days):
            step = max(1, len(days) // self.firehose_days)
            picked = days[::step][:self.firehose_days]
        else:
            picked = days
        push_firehose.enumerate_days(self.api, picked, pushes_dir, workers=self.workers,
                                     should_stop=self.expired)

        recs = push_firehose.load_days(pushes_dir)
        if len(recs) < len(picked):
            self._truncate("firehose enumeration",
                           f"{len(recs)}/{len(picked)} days")
        uniq, dupes = {}, 0
        for rec in recs:
            for p in rec.get("sample") or []:
                u = p.get("push_uuid")
                if not u:
                    continue
                if u in uniq:
                    dupes += 1
                else:
                    uniq[u] = p
        enumerated_sends = sum(r.get("sends") or 0 for r in recs)
        enumerated_pushes = sum(r.get("pushes") or 0 for r in recs)
        files = [self.save("responses.json",
                           {"pushes": list(uniq.values()),
                            "source": "firehose_enumerate (per-day sample)",
                            "sample_basis": (recs[0].get("sample_basis")
                                             if recs else None)}),
                 self.save("pushes_daily.json",
                           {"days": [{k: v for k, v in r.items() if k != "sample"}
                                     for r in recs]})]
        return {
            "files": files,
            "rows": len(uniq),
            "deduplicated": dupes,
            "days_enumerated": len(recs),
            "days_in_window": len(days),
            "enumerated_pushes": enumerated_pushes,
            "enumerated_sends": enumerated_sends,
            "coverage": (f"{len(recs)} of {len(days)} days enumerated exhaustively; "
                         f"{enumerated_pushes:,} pushes / {enumerated_sends:,} sends "
                         f"aggregated losslessly, {len(uniq):,} push_uuids retained "
                         f"for the per-push endpoints"),
        }

    def s_programs(self):
        """pergroup/detail per automation group — the whole-program aggregates."""
        groups = self.groups()
        if not groups:
            return {"skipped": "no group_id in the push inventory", "rows": 0}
        got = self.par(lambda g: self.api.get(f"/api/reports/pergroup/detail/{g}"),
                       list(groups), label="pergroup")
        merged = {g: dict(got.get(g) or {},
                          _sends_responses=meta["sends"],
                          _occurrences=meta["occurrences"],
                          _first=meta["first"], _last=meta["last"])
                  for g, meta in groups.items()}
        errs = sum(1 for v in got.values() if isinstance(v, dict) and v.get("_error"))
        # Same guard as `s_details`, and the direction the defect was first measured in:
        # a Sequence group id resolves on `pergroup/detail` and reads as zero on
        # `perpush/detail`. Here the inventory volume comes from the group aggregate.
        suspect = suspect_zero_details(
            got, {g: meta["sends"] for g, meta in groups.items()},
            "pergroup/detail")["suspect"]
        files = [self.save("pergroup.json", merged)]

        # What the programmes weigh against the window. Written here because this is the
        # only point holding both sides, and because a section author left to do the
        # subtraction alone reliably mixes alerting with silent and lifetime with window.
        #
        # The denominator is the PUSH-only total. It used to be `window_reports_sends()`,
        # which sums every column `/api/reports/sends` returns including email and sms —
        # fed into a parameter named `window_alerting_sends`, against programme
        # `alerting_sends` in the numerator. On a multi-channel account that inflated the
        # denominator and understated the share, which is the same defect
        # `verify_audit.check_pressure_basis` exists to catch one layer down.
        split = push_firehose.program_volume_split(
            merged, self._window_push_sends(), window_days=self.days)
        files.append(self.save("program_volume.json", split))
        print("    " + split["verdict"], flush=True)
        info = {"files": files, "rows": len(merged), "errors": errs,
                "program_share_ceiling": split["program_share_ceiling"]}
        # The activity log names programmes directly, via its GROUP rows. Compared rather
        # than merged: fetching them would change the programme inventory and every figure
        # weighted by it, which is not something to do silently.
        if self.has("activity.json"):
            unknown = [g for g in self._detail_plan().get("activity_group_ids", ())
                       if g not in groups]
            if unknown:
                info["groups_only_in_activity_log"] = unknown[:50]
                info["groups_only_in_activity_log_count"] = len(unknown)
                print(f"    [warn] {len(unknown)} programme(s) appear as GROUP rows in "
                      f"the activity log but have no group_id in responses/list, so they "
                      f"are absent from pergroup.json and from the programme inventory.",
                      flush=True)
        if suspect:
            info["suspect_zero_details"] = suspect[:50]
            info["suspect_zero_count"] = len(suspect)
            print(f"    [warn] {len(suspect)} group id(s) answered 200 with every "
                  f"counter at zero although the inventory saw them deliver — do not "
                  f"publish these zeros.", flush=True)
        return info

    def _detail_plan(self):
        """The set of push ids the per-message stages resolve, ranked and volume-capped.

        Two kinds of id go in, and conflating them is what made this expensive:

        * **Programme representatives are identity.** One row per programme, kept whatever
          it delivered, because a programme with no representative cannot be named in the
          report at all. Their count is bounded by the number of programmes.
        * **Everything else competes on delivered volume.** Broadcasts from
          `responses/list` and rows from the activity log are merged into one ranking and
          taken until they cover `DETAIL_VOLUME_SHARE` of the delivered total. Previously
          the broadcast half was taken *whole* — unbounded — and only the activity half was
          capped, which on a firehose meant ~32,000 ids and 27 minutes of calls against
          messages that reached nobody and could not appear in any section.

        The achieved coverage is returned, not assumed: an account whose volume is spread
        thin hits `DETAIL_HARD_CAP` before 99% and must say so rather than imply the set is
        near-complete.
        """
        if self._dplan is not None:
            return self._dplan
        reps = [m["rep"]["push_uuid"] for m in self.groups().values()
                if m.get("rep", {}).get("push_uuid")]
        self._dplan = rank_detail_ids(
            self.groupless(), self.load("activity.json")["activity"], reps)
        return self._dplan

    def _detail_ids(self):
        return self._detail_plan()["ids"]

    def s_details(self):
        """perpush/detail — the authoritative per-message rates."""
        plan = self._detail_plan()
        ids = plan["ids"]
        print("    " + plan["basis"], flush=True)
        got = self.par(lambda i: self.api.get(f"/api/reports/perpush/detail/{i}"),
                       ids, label="perpush")
        errs = sum(1 for v in got.values() if isinstance(v, dict) and v.get("_error"))
        inbox = inbox_only_messages(got)
        uncovered = {p["push_uuid"] for p in self.pushes()
                     if p.get("push_uuid")
                     and p.get("push_type") in PERPUSH_UNCOVERED_TYPES}
        zc = suspect_zero_details(got, plan.get("expected_volume"),
                                  "perpush/detail", not_covered=uncovered)
        suspect = zc["suspect"]
        files = [self.save("perpush_detail.json", got),
                 self.save("detail_plan.json", plan)]
        info = {"files": files, "rows": len(got), "errors": errs,
                "delivered_share": plan["delivered_share"],
                "zero_delivery_share": plan["zero_delivery_share"]}
        if suspect:
            info["suspect_zero_details"] = suspect[:50]
            info["suspect_zero_count"] = len(suspect)
            print(f"    [warn] {len(suspect)} id(s) answered 200 with every counter at "
                  f"zero although the inventory saw them deliver (largest: "
                  f"{suspect[0]['inventory_volume']:,}). Wrong endpoint for the id type, "
                  f"or an unsettled window — do not publish these zeros.", flush=True)
        if zc["not_covered"]:
            # Not a defect: stated so a section knows these messages have an inventory
            # volume and no rates, rather than reading them as a zero.
            info["perpush_not_covered"] = zc["not_covered"][:50]
            info["perpush_not_covered_count"] = len(zc["not_covered"])
            print(f"    {len(zc['not_covered'])} message(s) of a class perpush/detail "
                  f"does not cover ({', '.join(PERPUSH_UNCOVERED_TYPES)}): volume from "
                  f"the inventory, no rates available", flush=True)
        if inbox:
            # Bounded by construction: the probe resolves DETAIL_INBOX_PROBE ids at most.
            info["inbox_only_messages"] = inbox
            info["inbox_only_note"] = (
                f"{len(inbox)} message(s) delivered only to the Message Center inbox, "
                f"with no notification. Their volume is `rich_sends`, not `sends`; "
                f"`sends: 0` is correct for them and must not be reported as reach.")
        return info

    def s_bodies(self):
        """perpush/pushbody — the decode-once cache; never re-fetch a cached id."""
        ids = list(self._detail_ids())
        # Top up with the heaviest sends the ranking did not already carry. Sorted before
        # capping: `self.pushes()` comes back in enumeration order, so slicing it kept an
        # arbitrary prefix of whatever the descent happened to reach first rather than the
        # creatives a report would show.
        extra = sorted((p for p in self.pushes()
                        if (p.get("sends") or 0) >= self.body_floor
                        and p.get("push_uuid")),
                       key=lambda p: -(p.get("sends") or 0))
        ids += [p["push_uuid"] for p in extra[:self.body_cap]]
        ids = list(dict.fromkeys(ids))
        cached = {}
        if os.path.isfile(self.path("pushbodies.json")):
            cached = self.load("pushbodies.json")
        todo = [i for i in ids if i not in cached]
        print(f"    {len(cached)} cached · {len(todo)} to fetch", flush=True)
        got = self.par(lambda i: self.api.get(f"/api/reports/perpush/pushbody/{i}"),
                       todo, label="pushbody")
        cached.update(got)
        self._cache["pushbodies.json"] = cached
        return {"files": [self.save("pushbodies.json", cached)],
                "rows": len(cached), "fetched": len(todo),
                "reused_from_cache": len(ids) - len(todo)}

    def s_groupbodies(self):
        """Group payloads: automation/journey definitions and scheduled broadcasts.

        Airship exposes these under `pergroup/pushbody`; some projects only answer on
        the `perpush/pushbody` path with a group id, so try both before giving up.
        """
        groups = list(self.groups())
        if not groups:
            return {"skipped": "no groups", "rows": 0}

        def fetch(g):
            try:
                return self.api.get(f"/api/reports/pergroup/pushbody/{g}")
            except Exception:
                return self.api.get(f"/api/reports/perpush/pushbody/{g}")

        got = self.par(fetch, groups, label="groupbody")
        errs = sum(1 for v in got.values() if isinstance(v, dict) and v.get("_error"))
        return {"files": [self.save("groupbodies.json", got)],
                "rows": len(got), "errors": errs}

    def s_split(self):
        """Alerting vs silent split + temporal drift — reconciles the two send counters.

        `/api/reports/sends` counts ALERTING pushes only; `responses/list` also counts
        silent data-only ones. Quoting both without this measurement makes the report
        contradict itself.
        """
        by_day = self.reports_sends_by_day()
        # Handed the authoritative day totals so the sample can state its own weight in the
        # account rather than only its size.
        sample = push_firehose.sample_split(self.api, *self.cur, sends_by_day=by_day,
                                            workers=self.workers)
        print("    " + sample["coverage"], flush=True)
        files = [self.save("split_sample.json", sample)]
        window_sends = self.window_reports_sends()

        # A firehose account enumerates a CAPPED set of days, and responses.json holds
        # only the per-day sample. Comparing that sample's sends to the whole window's
        # sends yields a meaningless -99.9% "gap". Compare like with like: enumerated
        # day totals against /api/reports/sends restricted to those same days.
        daily = os.path.join(self.out, "pushes_daily.json")
        if self.shape.startswith("firehose") and os.path.exists(daily):
            recs = json.load(open(daily)).get("days") or []
            days = [r.get("date") or r.get("day") for r in recs]
            enumerated = sum(r.get("sends") or 0 for r in recs)
            basis_sends = sum(by_day.get(d, 0) for d in days)
            basis = {
                "mode": "enumerated_days",
                "days": days,
                "day_count": len(days),
                "window_days": self.days,
                "window_reports_sends": window_sends,
                # Named attribution, not fidelity: a low ratio here was a property of
                # what responses/list attributes to rows, not a gap in the descent. The
                # sends-per-push column is what separates the two — see reconcile().
                "day_attribution": {
                    (r.get("date") or r.get("day")): {
                        "enumerated": r.get("sends") or 0,
                        "pushes": r.get("pushes") or 0,
                        "sends_per_push": round((r.get("sends") or 0)
                                                / (r.get("pushes") or 1), 4),
                        "reports_sends": by_day.get(r.get("date") or r.get("day"), 0),
                        "attributed_share": round((r.get("sends") or 0)
                                                  / by_day[r.get("date") or r.get("day")], 4)
                        if by_day.get(r.get("date") or r.get("day")) else None,
                    } for r in recs},
            }
        elif self.shape in ("firehose_grouped", "firehose_unattributed"):
            # Nothing was enumerated by design: responses.json holds representatives chosen
            # for their push_uuid, not as a volume sample. Reconciling it against the window
            # would invent a ~-100% gap and read as data loss, when the volume it stands for
            # lives in pergroup/detail (grouped) or only in /api/reports/sends
            # (unattributed). Here only the split is measured.
            enumerated = basis_sends = None
            grouped = self.shape == "firehose_grouped"
            basis = {"mode": "program_layer" if grouped else "sampled_no_enumeration",
                     "window_days": self.days,
                     "window_reports_sends": window_sends,
                     "note": ("no per-push enumeration on a grouped firehose — see "
                              "program_volume.json for the volume reconciliation") if grouped
                     else ("no per-push enumeration and no programme layer to roll up to: "
                           "/api/reports/sends is the ONLY volume source for this account, "
                           "and responses.json is a sample carrying push_uuids")}
        else:
            enumerated = sum(p.get("sends") or 0 for p in self.pushes())
            basis_sends = window_sends
            basis = {"mode": "full_window", "window_days": self.days}
        if enumerated is None:
            rec = {"basis": basis, "sampled_silent_share": (sample.get("total") or {})
                   .get("silent_share"), "silent_drift": sample.get("silent_drift"),
                   "authoritative_for_volume": "/api/reports/sends",
                   "verdict": "volume is not reconciled against an enumeration on a "
                              "grouped firehose; see program_volume.json"}
        else:
            rec = push_firehose.reconcile(enumerated, basis_sends, split=sample,
                                          basis=basis)
        files.append(self.save("reconcile.json", rec))
        return {"files": files, "alerting_share": sample.get("alerting_share"),
                "drift": bool(sample.get("drift", {}).get("unstable"))}

    def s_attribution(self):
        """events/summary per program and per broadcast — conversion attribution."""
        groups = list(self.groups())
        bcast = [p["push_uuid"] for p in self.groupless()[:400] if p.get("push_uuid")]
        files = []
        deep = 0
        if groups:
            eg = self.par(
                lambda g: self.drain_summary(
                    f"/api/reports/events/summary/pergroup/{g}", label="events/pergroup"),
                groups, label="events/pergroup")
            deep = sum(v.get("_pages", 1) for v in eg.values() if isinstance(v, dict))
            files.append(self.save("events_pergroup.json", eg))
        if bcast:
            ep = self.par(
                lambda i: self.drain_summary(
                    f"/api/reports/events/summary/perpush/{i}", label="events/perpush"),
                bcast, label="events/perpush")
            files.append(self.save("events_perpush.json", ep))
        return {"files": files, "groups": len(groups), "broadcasts": len(bcast),
                "pergroup_pages": deep}

    def s_decode(self):
        """Decode the body caches once -> decoded.json + groups_decoded.json."""
        import decode_bodies
        out = decode_bodies.decode_pushbodies(self.load("pushbodies.json"))
        files = [self.save("decoded.json", out)]
        stats = decode_bodies.summarise(out)
        print("    " + " · ".join(f"{k}={v}" for k, v in stats.items()), flush=True)
        if self.has("groupbodies.json"):
            pg = self.load("pergroup.json") if self.has("pergroup.json") else {}
            gd = decode_bodies.decode_groupbodies(self.load("groupbodies.json"), pg)
            files.append(self.save("groups_decoded.json", gd))
            kinds = {}
            for v in gd.values():
                kinds[v.get("kind")] = kinds.get(v.get("kind"), 0) + 1
            stats["group_kinds"] = kinds
        return {"files": files, **stats}

    # -- driver ------------------------------------------------------------
    def stages(self):
        return [
            Stage("probe", ["probe.json"], self.s_probe),
            Stage("core", ["devices.json", "sends.json", "opens.json",
                           "optins.json", "optouts.json"], self.s_core),
            Stage("events", ["events.json"], self.s_events),
            Stage("activity", ["activity.json"], self.s_activity),
            # `probe` is a real dependency, not an ordering convention: `s_responses` routes
            # on self.shape and takes the per-push path when it is None. It was implicit
            # while stages ran in declaration order, and had to be written down before any
            # of them could overlap.
            Stage("responses", ["responses.json"], self.s_responses, ["probe"]),
            # `core` is a real dependency: the volume split reads sends.json for the
            # push-only denominator. It held only because the wave scheduler happened to
            # finish `core` first.
            Stage("programs", ["pergroup.json"], self.s_programs, ["responses", "core"]),
            Stage("details", ["perpush_detail.json"], self.s_details,
                  ["responses", "activity"]),
            Stage("bodies", ["pushbodies.json"], self.s_bodies,
                  ["responses", "activity"]),
            Stage("groupbodies", ["groupbodies.json"], self.s_groupbodies, ["responses"]),
            Stage("split", ["split_sample.json", "reconcile.json"], self.s_split,
                  ["responses", "core", "probe"]),
            Stage("attribution", ["events_pergroup.json", "events_perpush.json"],
                  self.s_attribution, ["responses"]),
            Stage("decode", ["decoded.json"], self.s_decode, ["bodies"]),
        ]

    @staticmethod
    def _waves(stages):
        """Group stages into successive waves of mutually independent ones.

        The dependency lists were declared from the start and then ignored: `run` walked
        them in declaration order, so `events` (127 s of its own pagination) waited behind
        `probe` (51 s) although neither reads the other's output. Scheduling from the
        declared graph turns the metadata into the thing that actually orders the run, which
        also means an undeclared dependency now fails loudly instead of working by accident.
        """
        pending, done, waves = list(stages), set(), []
        names = {st.name for st in stages}
        while pending:
            # a dependency outside this run (a cached or --only subset) cannot be waited for
            ready = [st for st in pending
                     if all(n in done or n not in names for n in st.needs)]
            if not ready:
                raise RuntimeError(
                    "circular stage dependency among "
                    + ", ".join(f"{st.name} needs {st.needs}" for st in pending))
            waves.append(ready)
            done.update(st.name for st in ready)
            pending = [st for st in pending if st not in ready]
        return waves

    def _run_stage(self, st, force, shared=False):
        """Execute one stage and return its manifest entry. Never raises."""
        if not force and st.files and self.has(*st.files):
            print(f"[skip] {st.name} (cached)", flush=True)
            return {"status": "skipped (cached)"}
        print(f"[run ] {st.name}", flush=True)
        t0, c0 = time.time(), self.api.calls
        # A soft deadline, not a kill. A stage that overruns writes what it has and says
        # what is missing; the run continues. Two `responses` stages were killed from
        # outside on a grocery firehose, discarding ~20 minutes of completed work each time
        # and leaving no record of how far they got.
        self._arm(self.stage_deadline)
        try:
            info = st.fn() or {}
            info.update({"status": "partial" if self._truncated else "ok",
                         "elapsed_s": round(time.time() - t0, 1),
                         "api_calls": self.api.calls - c0})
            if self._truncated:
                info["truncated"] = list(self._truncated)
                info["deadline_s"] = self.stage_deadline
                # A stage states its own coverage, and it composes that line before it
                # knows whether it will be allowed to finish. So a stage cut on the
                # deadline shipped `"coverage": "100% of 30d window (every next_page
                # followed)"` sitting beside `"status": "partial"` and a `truncated`
                # block saying the pagination had been stopped. The claim is hardcoded,
                # not measured, and it is what let a truncation go unnoticed for a whole
                # collection pass — 62 minutes of re-run. Correct it here, centrally,
                # rather than trusting a dozen stages to each remember.
                info["coverage"] = _partial_coverage(info.get("coverage"),
                                                     self._truncated)
            info["complete"] = not self._truncated
        except Exception as e:  # noqa: BLE001
            info = {"status": "FAILED", "error": f"{type(e).__name__}: {e}",
                    "elapsed_s": round(time.time() - t0, 1),
                    "api_calls": self.api.calls - c0}
            print(f"[FAIL] {st.name}: {info['error']}", flush=True)
        finally:
            self._arm(0)
        if shared:
            # The API counter is per-collector, so a delta taken around a stage that ran
            # beside siblings counts theirs too. Withheld rather than misattributed; the
            # run total in `totals` is unaffected.
            info["api_calls_wave"] = info.pop("api_calls")
            info["api_calls"] = None
            info["api_calls_note"] = "ran concurrently; calls not attributable per stage"
        print(f"[done] {st.name} · {info['elapsed_s']}s · "
              f"{info.get('api_calls') if info.get('api_calls') is not None else 'shared'} "
              f"calls", flush=True)
        return info

    def _check_settling(self):
        """Record how settled the window is, and say so before anything is collected.

        The Reports API answers a not-yet-consolidated window with `200` and zeros, so
        an unsettled tail does not fail — it produces a quietly low number. Stated up
        front rather than discovered in wave 5, and recorded in the manifest so a section
        written against this data can say what it was standing on.
        """
        try:
            wm = self.api.watermark()
        except Exception as exc:                              # noqa: BLE001
            wm = {"error": str(exc)}
        closed = (wm.get("date_closed") or "")[:10]
        settling = dict(wm, window_end=self.cur[1])
        if closed:
            settling["ends_after_watermark"] = self.cur[1] > closed
            settling["days_past_watermark"] = max(
                0, span_days(closed, self.cur[1]) - 1) if self.cur[1] > closed else 0
        self.manifest["window"]["settling"] = settling

        if settling.get("ends_after_watermark"):
            print(f"[warn] window ends {self.cur[1]} but reporting data is only closed "
                  f"to {closed} ({settling['days_past_watermark']}d past the watermark). "
                  f"Recent messages can return 200 with zeros that are not real zeros — "
                  f"treat the tail of the window as provisional, or re-run tomorrow.",
                  flush=True)
        elif wm.get("error"):
            print(f"[warn] could not read the consolidation watermark ({wm['error']}); "
                  f"proceeding without it", flush=True)
        return settling

    def run(self, only=None, force=False):
        t_all = time.time()
        self._check_settling()
        # A CACHED probe stage still has to set the shape. Without this a re-run reads
        # `None`, silently takes the per-push path on a firehose, and crashes in s_split on
        # `None.startswith`. The shape is the one piece of state every later stage routes on.
        if not self.shape and self.has("probe.json"):
            self.shape = (self.load("probe.json") or {}).get("shape")
            if self.shape:
                self.manifest["shape"] = self.shape
                print(f"[info] shape={self.shape} (from cached probe.json)", flush=True)
        todo = [st for st in self.stages() if not only or st.name in only]
        for wave in self._waves(todo):
            names = [st.name for st in wave]
            if len(wave) > 1:
                print(f"[wave] {' | '.join(names)} · {self._workers_max} calls in flight "
                      f"shared", flush=True)
            with cf.ThreadPoolExecutor(max_workers=len(wave)) as ex:
                futs = {ex.submit(self._run_stage, st, force, len(wave) > 1): st
                        for st in wave}
                for f in cf.as_completed(futs):
                    st = futs[f]
                    info = f.result()
                    with self._lock:
                        self.manifest["stages"][st.name] = info
        self.manifest["totals"] = {"api_calls": self.api.calls,
                                   "elapsed_s": round(time.time() - t_all, 1)}
        self.save("collect_manifest.json", self.manifest)
        return self.manifest


# ---------------------------------------------------------------------------
def _act(push_id, alerting, rich=0):
    """One activity-log row, shaped the way `_activity_delivered` reads it."""
    return {"push_id": push_id,
            "details": {"delivery": {"app": {"alerting": alerting, "silent": 0,
                                             "rich": rich}}}}


def _selftest():
    """Pin `rank_detail_ids`, the cap that turned 31,929 per-push calls into 300.

    A pure function on purpose, so the question "does the cap keep the right messages"
    gets measured rather than asserted.
    """
    # a real long tail: one giant, a few large, a long thin middle, and a mass that
    # reached nobody at all (95.7% of pushes on the account that motivated this)
    rows = ([{"push_uuid": "giant", "sends": 1_000_000}]
            + [{"push_uuid": f"big{i}", "sends": 100_000} for i in range(9)]
            + [{"push_uuid": f"mid{i}", "sends": 100} for i in range(990)]
            + [{"push_uuid": f"zero{i}", "sends": 0} for i in range(30_000)])
    r = rank_detail_ids(rows, [], share=0.99, hard_cap=4000, min_ids=300)
    assert r["ranked_candidates"] == 31_000, r["ranked_candidates"]
    assert r["delivered_total"] == 1_999_000, r["delivered_total"]
    assert r["delivered_share"] >= 0.99, r["delivered_share"]
    # the whole point: 99% of the delivered volume lives in under 3% of the messages
    assert r["ranked_resolved"] == 801, r["ranked_resolved"]
    assert r["hit_hard_cap"] is False, r
    assert r["zero_delivery_pushes"] == 30_000, r
    assert r["zero_delivery_share"] == round(30_000 / 31_000, 4), r["zero_delivery_share"]
    assert r["top_100_share"] > 0.95, r["top_100_share"]

    # same shape under the shipped constants, as properties rather than arithmetic, so
    # tuning DETAIL_VOLUME_SHARE cannot make this file lie about what it verified
    d = rank_detail_ids(rows, [])
    assert d["delivered_share"] >= DETAIL_VOLUME_SHARE, d["delivered_share"]
    assert len(d["ids"]) < d["ranked_candidates"] / 30, len(d["ids"])

    # programme representatives are identity, not volume: a programme with zero delivery
    # still has to be nameable in the report, so it bypasses the ranking
    reps = rank_detail_ids([{"push_uuid": "solo", "sends": 5}], [],
                           reps=["prog_silent", "prog_b", None])
    assert reps["program_representatives"] == 2, reps
    assert reps["ids"][:2] == ["prog_silent", "prog_b"], reps["ids"]
    # a representative that also wins on volume must appear once, not twice
    dedup = rank_detail_ids([{"push_uuid": "shared", "sends": 500}], [], reps=["shared"])
    assert dedup["ids"] == ["shared"], dedup["ids"]

    # honesty at the cap: a flat distribution cannot reach 99% within 50 ids, and the
    # result says so instead of reporting the share it was asked for
    flat = rank_detail_ids([{"push_uuid": f"p{i}", "sends": 100} for i in range(1000)], [],
                           share=0.99, hard_cap=50, min_ids=10)
    assert flat["hit_hard_cap"] is True, flat
    assert flat["ranked_resolved"] == 50 and flat["delivered_share"] == 0.05, flat

    # activity rows rank by DELIVERED volume alongside pushes, not by arrival order — the
    # bug that let an arbitrary slice of the log crowd out the messages that mattered
    mixed = rank_detail_ids([{"push_uuid": "small_push", "sends": 1}],
                            [_act("big_activity", 10_000)], share=0.5, min_ids=1)
    assert mixed["ids"] == ["big_activity"], mixed["ids"]
    assert mixed["delivered_total"] == 10_001, mixed

    # a Message Center drop with no notification has its whole reach in `rich`. It used
    # to rank at zero and drop out of the detail set entirely; it must now rank on it.
    inbox = rank_detail_ids([], [_act("inbox_only", 0, rich=6)], share=0.5, min_ids=1)
    assert inbox["ids"] == ["inbox_only"], inbox["ids"]
    assert inbox["delivered_total"] == 6, inbox
    assert inbox["zero_delivery_pushes"] == 0, inbox
    # ...and a notified message is not double-counted by the ranking, so it cannot
    # displace a genuinely larger one from the budget
    notified = rank_detail_ids([], [_act("notified", 4, rich=6),
                                    _act("larger", 9, rich=0)], share=0.5, min_ids=1)
    assert notified["delivered_total"] == 15, notified
    assert notified["ids"][0] == "larger", notified["ids"]

    empty = rank_detail_ids([], [])
    assert empty["ids"] == [] and empty["delivered_share"] is None, empty

    # The inbox probe: `responses/list` has no `rich_sends`, so a Message Center sent
    # without a notification sits at `sends: 0` and the ranking can never reach it. A
    # bounded sample of zero-send rows is resolved anyway, spread across the window
    # rather than taken from its head.
    zero_rows = [{"push_uuid": f"z{i:03d}", "sends": 0,
                  "push_time": f"2026-08-{1 + i // 40:02d} 0{i % 8}:00:00"}
                 for i in range(200)]
    pr = rank_detail_ids([{"push_uuid": "real", "sends": 500}] + zero_rows, [],
                         share=0.99, min_ids=1, inbox_probe=10)
    assert len(pr["inbox_probe_ids"]) == 10, pr["inbox_probe_ids"]
    assert "real" not in pr["inbox_probe_ids"], pr["inbox_probe_ids"]
    assert set(pr["inbox_probe_ids"]) <= {r["push_uuid"] for r in zero_rows}
    assert pr["ids"][0] == "real", pr["ids"][:3]
    # spread, not the first N: the sample must not sit inside one day
    assert len({i[:2] for i in pr["inbox_probe_ids"]}) > 1 or len(zero_rows) < 10
    assert len({p["push_time"][:10] for p in zero_rows
                if p["push_uuid"] in pr["inbox_probe_ids"]}) > 1, pr["inbox_probe_ids"]
    # a message the ranking already picked is not probed twice
    dupe = rank_detail_ids([{"push_uuid": "solo", "sends": 0}], [], inbox_probe=5)
    assert dupe["ids"] == ["solo"], dupe["ids"]
    assert dupe["inbox_probe_ids"] == [], dupe["inbox_probe_ids"]
    # opting out of the probe restores the previous behaviour exactly
    assert rank_detail_ids(zero_rows, [], inbox_probe=0)["inbox_probe_ids"] == []

    # ...and what the probe is for: reading volume off `rich_sends` when `sends` is 0
    io = inbox_only_messages({
        "mc_no_notif": {"sends": 0, "alerting_sends": 0, "rich_sends": 2,
                        "rich_responses": 1},
        "big_mc_no_notif": {"sends": 0, "rich_sends": 40, "rich_responses": 9},
        "push_and_mc": {"sends": 4, "alerting_sends": 4, "rich_sends": 6},
        "reached_nobody": {"sends": 0, "rich_sends": 0},
        "failed": {"_error": "404"},
        "sentinel": {"sends": 0, "rich_sends": -1},
    })
    assert [r["push_id"] for r in io] == ["big_mc_no_notif", "mc_no_notif"], io
    assert io[1]["volume_field"] == "rich_sends" and io[1]["rich_sends"] == 2
    assert inbox_only_messages({}) == [] and inbox_only_messages(None) == []

    # The id-type guard. Measured in both directions: a Sequence group id resolves on
    # pergroup/detail and reads as zero on perpush/detail, and a push id does the
    # reverse. Nothing in either payload says which one is the real number.
    zc = suspect_zero_details(
        {"wrong_endpoint": {"sends": 0, "direct_responses": 0, "rich_sends": 0},
         "bigger_wrong": {"sends": 0},
         "reached_nobody": {"sends": 0},
         "healthy": {"sends": 500, "direct_responses": 10},
         "inbox_only": {"sends": 0, "rich_sends": 2},
         "create_and_send": {"sends": 0, "created": 0},
         "failed": {"_error": "404"}},
        {"wrong_endpoint": 6_968, "bigger_wrong": 99_000, "reached_nobody": 0,
         "healthy": 500, "inbox_only": 0, "create_and_send": 3, "failed": 1_000},
        "perpush/detail", not_covered={"create_and_send"})
    sz = zc["suspect"]
    assert [r["id"] for r in sz] == ["bigger_wrong", "wrong_endpoint"], sz
    assert sz[1]["inventory_volume"] == 6_968 and sz[1]["endpoint"] == "perpush/detail"
    # a class the endpoint does not serve is classified, never flagged: otherwise the gate
    # fires on every account that uses Create-and-Send and stops being read
    assert [r["id"] for r in zc["not_covered"]] == ["create_and_send"], zc
    assert "does not cover" in zc["not_covered"][0]["reason"]
    # a message the inventory also saw as empty is agreement, not a defect; an
    # inbox-only Message Center is real delivery; a hard failure is loud already
    assert not suspect_zero_details({"x": {"sends": 0}}, {"x": 0},
                                    "perpush/detail")["suspect"]
    assert not suspect_zero_details({}, {}, "perpush/detail")["suspect"]
    assert not suspect_zero_details(None, None, "perpush/detail")["suspect"]
    # the plan carries the expected volumes the guard needs
    pl = rank_detail_ids([{"push_uuid": "a", "sends": 7}], [], reps=["r1"])
    assert pl["expected_volume"] == {"r1": 0, "a": 7}, pl["expected_volume"]

    # A GROUP row's push_id is a GROUP id, and perpush/detail answers a group id with 200
    # and zeros. It must never enter the per-push pool — measured: 18 did, on a project
    # where all 18 were programmes that had really delivered.
    gplan = rank_detail_ids(
        [{"push_uuid": "push_a", "sends": 10}],
        [{"push_id": "grp_1", "type": "GROUP",
          "details": {"delivery": {"app": {"alerting": 99_999}}}},
         _act("push_b", 20)], share=0.99, min_ids=1, inbox_probe=0)
    assert "grp_1" not in gplan["ids"], gplan["ids"]
    assert gplan["activity_group_ids"] == ["grp_1"], gplan["activity_group_ids"]
    assert set(gplan["ids"]) == {"push_a", "push_b"}, gplan["ids"]
    assert gplan["delivered_total"] == 30, gplan["delivered_total"]

    print("collect self-test OK")
    return 0


def main():
    # Before argparse: `project` is a required positional, so a flag alone would be
    # rejected before it could be read.
    if "--selftest" in sys.argv[1:]:
        return _selftest()
    ap = argparse.ArgumentParser(
        description="Collect an Airship project's Reports API data for the engagement review.")
    ap.add_argument("project", help="MCP server name, e.g. 'CLIENT PROD'")
    ap.add_argument("--start", required=True, help="first day of the window (YYYY-MM-DD)")
    ap.add_argument("--end", required=True, help="last day, INCLUSIVE (YYYY-MM-DD)")
    ap.add_argument("--out", required=True, help="output directory (work/<client>/data)")
    ap.add_argument("--shape", choices=["auto", "dashboard", "firehose_grouped",
                                        "firehose_groupless",
                                        "firehose_unattributed"], default="auto",
                    help="skip the probe by declaring the account shape")
    ap.add_argument("--stages", help="comma-separated subset, e.g. core,events")
    ap.add_argument("--force", action="store_true", help="re-run stages that are cached")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--no-prior", action="store_true",
                    help="skip the prior window (KPI deltas will be unavailable)")
    ap.add_argument("--firehose-days", type=int, default=0, metavar="N",
                    help="on a firehose account, enumerate only N evenly-spaced days "
                         "(0 = every day). Exhaustive enumeration costs tens of hours "
                         "at ~3M pushes/day; the cap is reported as measured coverage")
    ap.add_argument("--stage-deadline", type=int, default=600, metavar="SECONDS",
                    help="soft per-stage budget (0 = unlimited). On expiry the stage "
                         "writes what it has, is marked `partial` with what is missing, "
                         "and the run continues instead of being killed from outside")
    ap.add_argument("--hook", help="python file with extra_stages(collector) -> [Stage]")
    a = ap.parse_args()

    c = Collector(a.project, a.start, a.end, a.out, workers=a.workers,
                  shape=None if a.shape == "auto" else a.shape,
                  prior=not a.no_prior, firehose_days=a.firehose_days,
                  stage_deadline=a.stage_deadline)
    print(f"{a.project} · region={c.api.region} · current={c.cur} · prior={c.prior}",
          flush=True)

    if a.hook:
        import importlib.util
        spec = importlib.util.spec_from_file_location("collect_hook", a.hook)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        base = c.stages
        c.stages = lambda: base() + list(mod.extra_stages(c))

    only = set(a.stages.split(",")) if a.stages else None
    m = c.run(only=only, force=a.force)
    bad = [k for k, v in m["stages"].items() if v.get("status") == "FAILED"]
    print(f"\n{m['totals']['api_calls']} API calls · {m['totals']['elapsed_s']}s"
          + (f" · FAILED: {', '.join(bad)}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
