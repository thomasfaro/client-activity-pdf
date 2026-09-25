#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run every offline self-test in this directory. No credentials, no network, no project.

    python scripts/run_selftests.py            # all suites
    python scripts/run_selftests.py firehose   # only suites whose name contains this

These tests pin the functions that decide what a report is ALLOWED to claim — the routing
oracle's `is_floor`, the sends-weighted sample, the per-push call cap, the calendar
contamination detector, and the audit-vs-facts coherence check — plus two that decide what
it is allowed to *carry*: the redaction of personal sample values out of a client's tagging
plan, and the guard against a real account name reaching a tracked file. Each case in them
is a bug that actually shipped, so a failure here means a specific known error has come
back, not that a style rule was broken.

Note that `client_names` only self-tests its logic here. Run the script itself, without
`--selftest`, to check the working tree — it needs the local account list, which by design
this repository does not contain.

Deliberately distinct from `probe_sweep.py`, and the two are not interchangeable:

    run_selftests.py   offline, deterministic, seconds, safe on every commit. Answers
                       "does the logic still do what it did?"
    probe_sweep.py     calls the real Reports API across a dozen projects, costs ~1,000
                       calls and minutes, needs MCP credentials. Answers "do real accounts
                       still route the way we expect?" — which no fixture can answer,
                       because the accounts change on their own.

Run this one before shipping a change to the collection or facts logic; run the sweep after
changing the routing thresholds.

One subprocess per module rather than importing them here: these scripts adjust `sys.path`
and share module names, and a crash or a stray `sys.exit` in one must not decide the fate of
the others.
"""

import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))

# `push_firehose` dispatches on a positional command, the others take a flag. The runner
# absorbs that so a caller never has to remember which is which.
SUITES = [
    # `activity_log` runs its self-test when given no file at all; it pins the reading of
    # `rich`, which two callers of this module previously disagreed about.
    ("activity_log", ["activity_log.py"]),
    ("build_facts", ["build_facts.py", "--selftest"]),
    ("collect", ["collect.py", "--selftest"]),
    # Pins the two properties of the NotebookLM source pack that cannot be eyeballed:
    # that an account with almost no inputs still produces a valid pack, and that an
    # address embedded in a push body does not reach a persistent, shareable notebook.
    ("source_pack", ["build_source_pack.py", "--selftest"]),
    # Draws the demo charts AND pins the two refusals: a funnel with false leading zeros,
    # and a series whose total is a counter the registry disqualified.
    ("charts", ["airship_charts.py"]),
    ("event_attribution", ["event_attribution.py", "--selftest"]),
    ("push_firehose", ["push_firehose.py", "selftest"]),
    ("provenance", ["report_framework.py", "--selftest"]),
    ("purge_work", ["purge_work.py", "--selftest"]),
    ("tagging_redaction", ["analyze_tagging_plan.py", "--selftest"]),
    ("client_names", ["check_no_client_names.py", "--selftest"]),
    # Pins the false positives that made two hand-written predecessors of this checker
    # unusable: a base64 payload read as `nan`, prose emphasis read as a null, a dropped
    # chart named in a comment, and a framework table carrying several class tokens.
    ("check_section", ["check_section.py", "--selftest"]),
    ("verify_audit", ["verify_audit.py", "--selftest"]),
    ("verify_report", ["verify_report.py", "--selftest"]),
]


def run(name, argv):
    """-> (ok, seconds, combined output)."""
    t0 = time.time()
    p = subprocess.run([sys.executable] + argv, cwd=HERE, capture_output=True, text=True)
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode == 0, time.time() - t0, out.strip()


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    suites = [s for s in SUITES if not only or only in s[0]]
    if not suites:
        print(f"no suite matching '{only}' — have: "
              f"{', '.join(n for n, _ in SUITES)}")
        return 2

    failed = []
    for name, argv in suites:
        ok, secs, out = run(name, argv)
        print(f"[{'ok  ' if ok else 'FAIL'}] {name:<20} {secs:5.2f}s")
        if not ok:
            failed.append(name)
            for line in out.splitlines():
                print(f"         {line}")

    print(f"\n{len(suites) - len(failed)}/{len(suites)} suite(s) passed"
          + (f" — FAILED: {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
