#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Enforce the retention rule on `work/`, instead of just stating it.

A review pulls a client's real send history, creatives and taxonomy onto a laptop
and leaves it there. Nothing in the skill ever removed it, so the tree grew to
several hundred megabytes across a dozen named accounts, the oldest dating back
weeks. Airship stores Customer Data in the region the client picked on their order
form; a working copy on a laptop is outside that, which makes "how long does it
stay" a real question rather than housekeeping.

The rule this implements: **raw pulls live 30 days, everything needed to rebuild
lives on.** After the window a directory keeps what the build path actually reads --
the numbers (`audit.json`, `facts.json`), the layout (`specs.json`, `sections/`,
`build_report.py`), the rendered figures (`charts/`, `creatives/`) and the record of
who produced it (`run.md`) -- and the raw pulls go. The report itself was copied to
`~/Downloads` when the gate passed, so nothing unique is lost either way.

The first version of this list held three filenames, and that was a bug with a cost:
it read "what would a later review want to read" when the question is "what does
`build_report.py` open". Rebuilding a report -- after a framework fix, a wording
change, or to produce the other language -- needs the whole set above, and five
accounts lost that capability before the list was corrected. What survives is small:
the bulk of a pull is `activity.json` and the per-push details, which no builder
reads.

Dry run by default, because a tool that deletes client data on its first invocation
is the wrong default:

    python .cursor/skills/airship-engagement-review/scripts/purge_work.py
    python .cursor/skills/airship-engagement-review/scripts/purge_work.py --apply
    python .cursor/skills/airship-engagement-review/scripts/purge_work.py --days 7 --apply
    python .cursor/skills/airship-engagement-review/scripts/purge_work.py --purge-all --apply
    python .cursor/skills/airship-engagement-review/scripts/purge_work.py --selftest
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import time

# What `build_report.py` and the section files open, established by reading them
# rather than by guessing. Top-level files: the numbers, the layout, the brand, the
# optional tagging plan, and the builder itself.
KEEP = ("audit.json", "facts.json", "specs.json", "run.md", "brand.json",
        "audit_tagging.json", "tagging_plan.json", "build_report.py")

# Top-level directories kept whole. `creatives/` carries its own `manifest.json`, and
# `charts/` the rendered PNGs a rebuild would otherwise have to regenerate from data
# that is no longer there.
KEEP_DIRS = ("sections", "charts", "creatives")

# Derived files that live *inside* the raw-pull tree but are read at build time. Kept
# at any depth, because the same file appears as `data/analysis.json` on one account
# and `data/audit/analysis.json` on another, and one builder reads `data_new/`. Small
# next to what surrounds them: the 133 MB in a dense account's `data/` is
# `activity.json`, which nothing downstream opens.
KEEP_ANYWHERE = ("analysis.json", "inventory.json", "reconcile.json",
                 "audit_parsed.json", "pushbodies.json", "collect_manifest.json",
                 "perpush_sample.json", "sends.json")

DEFAULT_DAYS = 30


def _newest(path: str) -> float:
    """Most recent mtime anywhere under `path`.

    A directory's own mtime only moves when an entry is added or removed, so an
    account whose sections were rewritten in place would otherwise look stale and
    get purged while still in use.
    """
    newest = 0.0
    try:
        newest = os.path.getmtime(path)
    except OSError:
        return 0.0
    for root, _dirs, files in os.walk(path):
        for name in (root, *(os.path.join(root, f) for f in files)):
            try:
                newest = max(newest, os.path.getmtime(name))
            except OSError:
                pass
    return newest


def _size(path: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}GB"


def victims(account_dir: str, cutoff: float):
    """The files in one account past the window.

    Age is per file, not per directory, and that distinction is the whole point.
    A directory's timestamp moves whenever anything touches it -- a probe sweep
    across thirteen accounts reset every one of them to "modified today" while the
    push history underneath was three weeks old. Ageing the files themselves means
    an unrelated write cannot silently extend the retention of client data.

    Keepsakes survive at the top level only, and nothing survives inside a `_archive_*`
    or dot-prefixed snapshot: an `audit.json` in there is a copy of a copy.
    """
    out = []
    base = os.path.abspath(account_dir)
    for root, _dirs, files in os.walk(account_dir):
        rel = os.path.relpath(os.path.abspath(root), base)
        parts = [] if rel == "." else rel.split(os.sep)
        # A snapshot directory is spared no file: it is already a duplicate of the
        # account beside it, so keeping "the important files" out of it keeps nothing.
        snapshot = bool(parts) and parts[0].startswith((".", "_"))
        protected_dir = bool(parts) and parts[0] in KEEP_DIRS and not snapshot
        for name in files:
            if not parts and name in KEEP:
                continue
            if protected_dir:
                continue
            if not snapshot and name in KEEP_ANYWHERE:
                continue
            path = os.path.join(root, name)
            try:
                if os.path.getmtime(path) < cutoff:
                    out.append(path)
            except OSError:
                pass
    return sorted(out)


def raw_pulls(account_dir: str):
    """Files under the raw-pull tree that nothing downstream opens.

    Narrower than `victims` on purpose. This is what runs the moment a report is
    built, when the question is not "has this aged out" but "is this still needed" --
    so it touches only the pull directories (`data`, `data_new`, ...) and leaves every
    top-level artefact alone. Deleting `report.html` seconds after writing it would be
    absurd even though the 30-day rule eventually does exactly that.
    """
    out = []
    try:
        entries = sorted(os.listdir(account_dir))
    except OSError:
        return out
    for name in entries:
        top = os.path.join(account_dir, name)
        if not os.path.isdir(top) or not name.startswith("data"):
            continue
        for root, _dirs, files in os.walk(top):
            for f in files:
                if f in KEEP_ANYWHERE:
                    continue
                out.append(os.path.join(root, f))
    return sorted(out)


def source_pack_involved(account_dir: str) -> bool:
    """Is a NotebookLM source pack part of this run's deliverables?

    The report is not the last artefact when a pack is also produced, and the pack reads
    the same raw pulls the report builder would otherwise retire. Two signals: the pack
    directory itself, and a `.source-pack-pending` marker for the window between the pack
    being decided on and being built — touch it in wave 0 when the pack is a deliverable.
    """
    return (os.path.isdir(os.path.join(account_dir, "source_pack"))
            or os.path.exists(os.path.join(account_dir, ".source-pack-pending")))


def reduce_raw(account_dir: str, *, dry_run: bool = False) -> int:
    """Drop the raw pulls for one account. Returns bytes freed (or nominated).

    Called at the end of a successful build, so a pull lives for the length of the run
    that needed it rather than for a month. The 30-day window stays as the net for
    accounts whose build never completed.
    """
    freed = 0
    for f in raw_pulls(account_dir):
        try:
            size = os.path.getsize(f)
        except OSError:
            continue
        freed += size
        if dry_run:
            continue
        try:
            os.remove(f)
        except OSError as exc:
            print(f"  ! {f}: {exc}")
            freed -= size
    if not dry_run and freed:
        _prune_empty(account_dir)
    return freed


def _oldest(path: str) -> float:
    """Oldest mtime under `path` — how long the stalest data here has sat."""
    oldest = float("inf")
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                oldest = min(oldest, os.path.getmtime(os.path.join(root, f)))
            except OSError:
                pass
    return 0.0 if oldest == float("inf") else oldest


def plan(root: str, days: int, purge_all: bool):
    """Which accounts hold data past the window, and what each would give back."""
    now = time.time()
    cutoff = now - days * 86400
    rows = []
    if not os.path.isdir(root):
        return rows
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        if not os.path.isdir(path) or name.startswith((".", "_")):
            continue
        # `--purge-all` is an account-level judgement: nothing here has been touched
        # for the whole window, so the account itself is done with.
        idle = bool(_newest(path)) and _newest(path) < cutoff
        if purge_all:
            files, dirs = [], ([path] if idle else [])
        else:
            files, dirs = victims(path, cutoff), []
        freed = sum(_size(d) for d in dirs)
        for f in files:
            try:
                freed += os.path.getsize(f)
            except OSError:
                pass
        oldest = _oldest(path)
        rows.append({"dir": path, "name": name,
                     "oldest_days": (now - oldest) / 86400 if oldest else 0.0,
                     "stale": bool(files or dirs), "files": files, "dirs": dirs,
                     "size": _size(path), "freed": freed})
    return rows


def _prune_empty(account_dir: str) -> None:
    """Drop directories left empty by the purge, deepest first."""
    for root, dirs, _files in os.walk(account_dir, topdown=False):
        for d in dirs:
            path = os.path.join(root, d)
            try:
                if not os.listdir(path):
                    os.rmdir(path)
            except OSError:
                pass


def apply(rows) -> int:
    freed = 0
    for r in rows:
        for f in r["files"]:
            try:
                freed += os.path.getsize(f)
                os.remove(f)
            except OSError as exc:
                print(f"  ! {f}: {exc}")
        for d in r["dirs"]:
            try:
                freed += _size(d)
                shutil.rmtree(d)
            except OSError as exc:
                print(f"  ! {d}: {exc}")
        if r["files"] and os.path.isdir(r["dir"]):
            _prune_empty(r["dir"])
    return freed


def _selftest() -> int:
    import tempfile
    fails = []

    def check(cond, label):
        if not cond:
            fails.append(label)

    stale_t = time.time() - 40 * 86400

    def age(path):
        for r, _d, fs in os.walk(path):
            for n in (r, *(os.path.join(r, f) for f in fs)):
                os.utime(n, (stale_t, stale_t))
        os.utime(path, (stale_t, stale_t))

    def account(root, name):
        """A directory shaped like a real account: keepsakes, build inputs, raw pulls."""
        d = os.path.join(root, name)
        for sub in ("data", "data/audit", "charts", "creatives", "sections"):
            os.makedirs(os.path.join(d, sub), exist_ok=True)
        for n in ("audit.json", "facts.json", "specs.json", "run.md", "brand.json",
                  "build_report.py", "report.html"):
            open(os.path.join(d, n), "w").write("x" * 10)
        # rendered figures and section sources: a rebuild has no way to regenerate
        # these once the data they came from is gone
        open(os.path.join(d, "charts", "volume.png"), "w").write("p" * 50)
        open(os.path.join(d, "creatives", "manifest.json"), "w").write("m" * 20)
        open(os.path.join(d, "creatives", "push_a.png"), "w").write("c" * 50)
        open(os.path.join(d, "sections", "exec_summary.py"), "w").write("s" * 30)
        # raw pulls: the bulk, and nothing downstream opens them
        open(os.path.join(d, "data", "activity.json"), "w").write("y" * 400)
        open(os.path.join(d, "data", "responses.json"), "w").write("y" * 100)
        # derived files read at build time, one of them nested a level deeper
        open(os.path.join(d, "data", "reconcile.json"), "w").write("r" * 10)
        open(os.path.join(d, "data", "audit", "analysis.json"), "w").write("a" * 10)
        return d

    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "work")
        old, fresh, mixed = (account(root, "old"), account(root, "fresh"),
                             account(root, "mixed"))
        age(old)
        age(mixed)
        # the regression a real dry run caught: an unrelated write (a probe sweep
        # across every account) must not extend the retention of the old pulls
        open(os.path.join(mixed, "probe.json"), "w").write("z")

        # A pack reads the same raw pulls the report builder would retire, and the pack
        # is rebuilt after the report — so the report build must leave them alone.
        check(not source_pack_involved(fresh), "no pack, nothing to protect")
        open(os.path.join(fresh, ".source-pack-pending"), "w").write("")
        check(source_pack_involved(fresh), "a declared pack protects the pulls")
        os.remove(os.path.join(fresh, ".source-pack-pending"))
        os.makedirs(os.path.join(fresh, "source_pack"))
        check(source_pack_involved(fresh), "a built pack protects them too")
        os.rmdir(os.path.join(fresh, "source_pack"))

        rows = {r["name"]: r for r in plan(root, DEFAULT_DAYS, purge_all=False)}
        check(rows["old"]["stale"], "a 40-day-old account is past a 30-day window")
        check(not rows["fresh"]["stale"], "a fresh account is left alone")
        check(rows["fresh"]["files"] == [], "a fresh account nominates nothing")
        # The regression that cost five accounts their rebuildability: only the raw
        # pulls may be nominated. Anything the build path opens has to survive.
        names = {os.path.basename(f) for f in rows["old"]["files"]}
        check(names == {"report.html", "activity.json", "responses.json"},
              f"only raw pulls are nominated, got {names}")
        check(rows["old"]["oldest_days"] > 39, "age is reported from the oldest file")
        mixed_names = {os.path.basename(f) for f in rows["mixed"]["files"]}
        check(mixed_names == {"report.html", "activity.json", "responses.json"},
              f"one fresh write does not protect old pulls, got {mixed_names}")

        apply(list(rows.values()))
        check(sorted(os.listdir(old)) == ["audit.json", "brand.json", "build_report.py",
                                          "charts", "creatives", "data", "facts.json",
                                          "run.md", "sections", "specs.json"],
              f"after purge: {sorted(os.listdir(old))}")
        # each of these is a rebuild input, and each was lost by the first version
        check(os.path.isfile(os.path.join(old, "charts", "volume.png")),
              "a rendered chart survives the window")
        check(os.path.isfile(os.path.join(old, "creatives", "manifest.json")),
              "the creatives manifest survives")
        check(os.path.isfile(os.path.join(old, "creatives", "push_a.png")),
              "a rendered creative preview survives")
        check(os.path.isfile(os.path.join(old, "sections", "exec_summary.py")),
              "a section source survives")
        check(os.path.isfile(os.path.join(old, "data", "reconcile.json")),
              "a derived file inside data/ survives")
        check(os.path.isfile(os.path.join(old, "data", "audit", "analysis.json")),
              "a derived file nested deeper inside data/ survives")
        check(not os.path.exists(os.path.join(old, "data", "activity.json")),
              "the bulky pull is gone")
        check(sorted(os.listdir(fresh)) == ["audit.json", "brand.json",
                                            "build_report.py", "charts", "creatives",
                                            "data", "facts.json", "report.html",
                                            "run.md", "sections", "specs.json"],
              "the fresh account is untouched")
        check("probe.json" in os.listdir(mixed), "the fresh file itself survives")

        # a snapshot directory is spared nothing, keepsake names included
        snap = os.path.join(root, "snapshot")
        os.makedirs(os.path.join(snap, "_archive_2026"))
        open(os.path.join(snap, "audit.json"), "w").write("x")
        open(os.path.join(snap, "_archive_2026", "audit.json"), "w").write("x")
        open(os.path.join(snap, "_archive_2026", "analysis.json"), "w").write("x")
        age(snap)
        snap_row = {r["name"]: r for r in plan(root, DEFAULT_DAYS, False)}["snapshot"]
        snap_paths = {os.path.relpath(f, snap) for f in snap_row["files"]}
        check(snap_paths == {os.path.join("_archive_2026", "audit.json"),
                             os.path.join("_archive_2026", "analysis.json")},
              f"a snapshot keeps nothing, the account keeps its keepsake, got {snap_paths}")

        # reduce_raw runs at build time, so it is age-blind and must spare every
        # top-level artefact: dropping report.html seconds after writing it, or the
        # charts a rebuild needs, is the failure this pins.
        built = account(root, "built")
        nominated = {os.path.relpath(f, built) for f in raw_pulls(built)}
        check(nominated == {os.path.join("data", "activity.json"),
                            os.path.join("data", "responses.json")},
              f"only the raw pulls are nominated at build time, got {nominated}")
        freed = reduce_raw(built, dry_run=True)
        check(freed == 500, f"a dry run reports the bytes without deleting, got {freed}")
        check(os.path.isfile(os.path.join(built, "data", "activity.json")),
              "a dry run deletes nothing")
        check(reduce_raw(built) == 500, "the deletion reports the same size")
        check(os.path.isfile(os.path.join(built, "report.html")),
              "the freshly built report survives its own retention step")
        check(os.path.isfile(os.path.join(built, "charts", "volume.png")),
              "the charts a rebuild needs survive")
        check(os.path.isfile(os.path.join(built, "data", "reconcile.json")),
              "a derived file inside data/ survives")
        check(os.path.isfile(os.path.join(built, "data", "audit", "analysis.json")),
              "a nested derived file survives")
        check(not os.path.exists(os.path.join(built, "data", "activity.json")),
              "the pull itself is gone")
        check(reduce_raw(built) == 0, "a second pass has nothing left to do")

        # --purge-all is account-level: only an account idle for the whole window
        idle = account(root, "idle")
        age(idle)
        apply(plan(root, DEFAULT_DAYS, purge_all=True))
        check(not os.path.isdir(idle), "--purge-all removes an idle account entirely")
        check(os.path.isdir(fresh), "--purge-all still respects the window")

    for f in fails:
        print(f"  \u2717 {f}")
    print(f"purge_work selftest: {'FAIL' if fails else 'ok'} ({len(fails)} failure(s))")
    return 1 if fails else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default="work", help="working tree (default: work)")
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS,
                    help=f"retention window in days (default: {DEFAULT_DAYS})")
    ap.add_argument("--purge-all", action="store_true",
                    help="remove the whole account directory, keepsakes included")
    ap.add_argument("--apply", action="store_true",
                    help="actually delete (default: report only)")
    ap.add_argument("--selftest", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.selftest:
        return _selftest()

    rows = plan(args.root, args.days, args.purge_all)
    if not rows:
        print(f"nothing under {args.root}/")
        return 0

    stale = [r for r in rows if r["stale"]]
    kept = ("purge-all (idle accounts)" if args.purge_all else
            f"keep what rebuilds a report ({len(KEEP)} files, "
            f"{'/'.join(KEEP_DIRS)}, {len(KEEP_ANYWHERE)} derived)")
    print(f"{args.root}/ — retention {args.days}d, {kept}\n")
    print(f"  {'':<6}{'account':<20}{'oldest':>8}{'size':>10}   past the window")
    for r in rows:
        mark = "purge" if r["stale"] else "keep "
        print(f"  {mark} {r['name']:<20} {r['oldest_days']:>6.0f}d "
              f"{_human(r['size']):>9}   " +
              (f"{_human(r['freed'])} in {len(r['files']) or len(r['dirs'])} item(s)"
               if r["stale"] else "-"))
    total = sum(r["freed"] for r in stale)
    print(f"\n{len(stale)} of {len(rows)} account(s) hold data past the window, "
          f"{_human(total)} recoverable")

    if not args.apply:
        print("dry run — re-run with --apply to delete")
        return 0
    freed = apply(stale)
    print(f"freed {_human(freed)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
