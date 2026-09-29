"""Run the shape probe across many projects at once — the routing acceptance test.

The routing decision is the single most expensive thing this skill gets wrong: a firehose
read as `dashboard` points the collector at ~190,000 pages, and a dashboard read as a
firehose skips the enumeration the whole report is built on. It is also the one decision
that cannot be checked from a single account, because the failure mode was *systematic* —
a fallback branch that could never conclude `firehose` misrouted four of thirteen projects
without ever looking wrong on any one of them.

So the check is a sweep, and it is cheap enough to rerun on every change: one probe per
project, a few hundred calls each, projects in parallel.

    python probe_sweep.py <start> <end> [project ...]
    python probe_sweep.py 2026-08-10 2026-08-20            # every credentialled project
    python probe_sweep.py 2026-08-10 2026-08-20 --expect expected.json

`end` is EXCLUSIVE. With `--expect`, a JSON mapping of project -> expected shape turns the
sweep into a pass/fail gate and the exit code follows it, so it can front a change.

The sweep reports `pushes_per_day` with its exactness, because "6,000 (floor)" and "6,000
(exact)" mean different things: the first is a firehose the oracle stopped counting, the
second is an account that genuinely emits that much. It also reports `sample_share`, the
weight of the probe's own sample in the account, which is what says whether the sample's
per-push statistics may be quoted at all.
"""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import push_firehose  # noqa: E402
from airship_api import Airship, list_projects  # noqa: E402

# Projects are probed concurrently, each probe already running its own pool of 14. Kept low
# on purpose: the point is a repeatable reading, and stacking 13 x 14 in-flight requests
# invites the 429 retries that would make the timings meaningless.
PROJECT_WORKERS = 4


def probe_one(project, start, end):
    t0 = time.time()
    try:
        api = Airship(project)
    except Exception as e:
        return {"project": project, "error": f"credentials: {e}"}
    try:
        out = push_firehose.probe(api, start, end)
    except Exception as e:
        return {"project": project, "error": f"{type(e).__name__}: {e}",
                "calls": api.calls, "elapsed_s": round(time.time() - t0, 1)}
    depth = out.get("pushes_per_day_basis")
    depth = depth if isinstance(depth, dict) else {}
    return {
        "project": project,
        "shape": out.get("shape"),
        "pushes_per_day": out.get("pushes_per_day_floor"),
        "exact": out.get("pushes_per_day_exact"),
        "per_day": [d["pushes"] for d in depth.get("per_day") or []],
        "saturated_windows": out.get("saturated_probe_windows"),
        "probe_windows": out.get("probe_windows"),
        "sample_share": out.get("sample_sends_share"),
        "per_push_ok": out.get("per_push_stats_reliable"),
        "mean_sends": out.get("mean_sends_per_push"),
        "group_share": out.get("group_id_share"),
        "program_sends": out.get("confirmed_program_sends"),
        "calls": api.calls,
        "elapsed_s": round(time.time() - t0, 1),
        "reason": out.get("shape_reason"),
    }


def sweep(projects, start, end, workers=PROJECT_WORKERS):
    with ThreadPoolExecutor(min(len(projects), workers)) as ex:
        return list(ex.map(lambda p: probe_one(p, start, end), projects))


def _fmt(rows, expect=None):
    hdr = (f"{'project':<34} {'shape':<19} {'pushes/day':>12} {'sat':>7} "
           f"{'sample':>8} {'calls':>6} {'s':>6}")
    out = [hdr, "-" * len(hdr)]
    bad = []
    for r in sorted(rows, key=lambda r: r["project"].lower()):
        if r.get("error"):
            out.append(f"{r['project']:<34} ERROR  {r['error'][:70]}")
            bad.append(r["project"])
            continue
        ppd = ("n/a" if r["pushes_per_day"] is None else
               f"{r['pushes_per_day']:,}" + ("" if r["exact"] else "+"))
        sat = f"{r['saturated_windows']}/{r['probe_windows']}"
        share = "n/a" if r["sample_share"] is None else f"{r['sample_share']:.3%}"
        flag = ""
        if expect and expect.get(r["project"]):
            want = expect[r["project"]]
            ok = r["shape"] == want or (want == "firehose"
                                        and str(r["shape"]).startswith("firehose"))
            flag = "  ok" if ok else f"  WANT {want}"
            if not ok:
                bad.append(r["project"])
        out.append(f"{r['project']:<34} {str(r['shape']):<19} {ppd:>12} {sat:>7} "
                   f"{share:>8} {r['calls']:>6} {r['elapsed_s']:>6}{flag}")
    return "\n".join(out), bad


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    start, end = sys.argv[1], sys.argv[2]
    rest = sys.argv[3:]
    expect = None
    if "--expect" in rest:
        i = rest.index("--expect")
        with open(rest[i + 1], encoding="utf-8") as fh:
            expect = json.load(fh)
        rest = rest[:i] + rest[i + 2:]
    projects = rest or list_projects()
    if not projects:
        print("no credentialled projects found in ~/.cursor/mcp.json")
        sys.exit(1)
    print(f"probing {len(projects)} project(s) over [{start}, {end})\n", flush=True)
    t0 = time.time()
    rows = sweep(projects, start, end)
    table, bad = _fmt(rows, expect)
    print(table)
    print(f"\n{sum(r.get('calls', 0) for r in rows):,} API calls · "
          f"{time.time() - t0:.0f}s wall")
    with open("probe_sweep.json", "w", encoding="utf-8") as fh:
        json.dump({"window": [start, end], "rows": rows}, fh, ensure_ascii=False, indent=1)
    print("wrote probe_sweep.json")
    if expect and bad:
        print(f"\nFAIL — {len(bad)} project(s) off expectation: {', '.join(bad)}")
        sys.exit(2)


if __name__ == "__main__":
    main()
