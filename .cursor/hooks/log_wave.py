"""Fill in the run manifest that every engagement review is supposed to have.

`orchestration.md` asks for a `work/<client>/run.md` recording, per wave, which model
ran it and how long it took — "what makes a parallel run reproducible and a failure
diagnosable". Across twelve completed accounts, not one exists. A manifest that depends
on the orchestrator remembering to write it during a two-hour run is a manifest that
does not get written, so this records the two things a hook can see on its own:

  subagentStop  how long each delegated wave took, and how many tool calls it burned
  preCompact    when the context window filled up, and how full it was
  stop          section files against delegated waves, so a run that delegated NOTHING
                says so instead of merely lacking rows

Those are the numbers that turn "the run felt slower and the report felt no better"
into something you can point at.

Wired from `.cursor/hooks.json`; Cursor runs project hooks from the repo root, so the
relative `work/` path below resolves. Reads the hook payload as JSON on stdin.

    python .cursor/hooks/log_wave.py subagentStop  < payload.json

Two properties matter more than what it logs. It **never fails the agent**: any error
is swallowed and the exit status is always 0, because a broken logger must not be able
to stop a review from being produced. And it **stays silent outside a review run**: with no
`work/<client>/` directory to write to it does nothing at all, so it does not litter
every other conversation in this project.
"""

import datetime
import json
import os
import sys

WORK = "work"
MANIFEST = "run.md"

# Written once, when a run.md is first created. The hand-kept part of the manifest
# (window, shape, language, deviations) stays the orchestrator's job — the template
# in orchestration.md covers it. Everything below the auto-log heading is ours.
_SCAFFOLD = """# Run manifest

Hand-fill the header and the Deviations section from the template in
`.cursor/skills/airship-engagement-review/orchestration.md`.

Reviewed-by:

The line above names the human who checked this analysis before it was used to
prepare a client conversation. It is optional — the report's provenance footer
quotes it once it is set.

## Auto-log

Appended by `.cursor/hooks/log_wave.py`. Durations are wall-clock for a delegated
wave, not for the whole run.

| when | event | detail | duration | tools |
|---|---|---|---|---|
"""


def _target_dir():
    """The account this run is about: the most recently touched `work/<client>/`.

    A hook is told nothing about the run it belongs to, so the directory has to be
    inferred. Most-recently-modified is right in practice because a review writes to
    its account directory constantly (sections, charts, audit.json) and two reviews
    are not run concurrently from one chat. When the guess would be meaningless —
    no `work/`, or nothing in it — we return None and log nothing, which is the
    behaviour that keeps this quiet in unrelated conversations.
    """
    if not os.path.isdir(WORK):
        return None
    best, best_mtime = None, -1.0
    for name in os.listdir(WORK):
        path = os.path.join(WORK, name)
        if not os.path.isdir(path) or name.startswith((".", "_")):
            continue
        # The directory's own mtime only moves when an entry is added or removed, so
        # a run that is rewriting existing sections would look stale. Take the most
        # recent mtime among the directory and its immediate children instead.
        mtimes = [os.path.getmtime(path)]
        try:
            mtimes += [os.path.getmtime(os.path.join(path, c))
                       for c in os.listdir(path)]
        except OSError:
            pass
        m = max(mtimes)
        if m > best_mtime:
            best, best_mtime = path, m
    return best


def _cell(value, limit=70):
    """One table cell: single-line, pipe-safe, bounded."""
    text = " ".join(str(value if value is not None else "").split())
    text = text.replace("|", "\\|")
    return text[:limit - 1] + "…" if len(text) > limit else text


def _pick(payload, *names):
    """First present value among `names`, snake_case or camelCase, at any nesting depth.

    Hook payload field names are not part of any contract this repo controls, and a logger
    that reads exactly one spelling silently logs nothing when the spelling changes.
    """
    for n in names:
        if n in payload and payload[n] not in (None, ""):
            return payload[n]
    for v in payload.values():
        if isinstance(v, dict):
            got = _pick(v, *names)
            if got is not None:
                return got
    return None


def _row(event, payload):
    """(detail, duration, tools) for the event, or None to log nothing."""
    if event == "subagentStop":
        kind = _pick(payload, "subagent_type", "subagentType", "agent_type", "type")
        what = _pick(payload, "description", "task", "prompt", "name", "title")
        status = _pick(payload, "status", "result", "outcome") or ""
        # Never drop the row for want of a recognised field name. The previous version
        # returned None when neither key was present, which is why four run manifests
        # recorded twelve compactions and not one delegated wave: the waves HAD been
        # delegated, and a payload whose keys were spelled differently looked exactly like
        # no delegation at all. Logging the keys instead makes the mismatch fixable.
        if not (kind or what):
            keys = ",".join(sorted(k for k in payload)) or "empty payload"
            what = f"unidentified subagent — payload keys: {keys}"
        # A subagent that errored or was aborted is the interesting case, so say so
        # rather than logging a duration that measures a failure.
        label = f"{kind or 'subagent'}: {what}"
        if status and status != "completed":
            label += f" [{status}]"
        ms = _pick(payload, "duration_ms", "durationMs", "elapsed_ms")
        dur = f"{ms / 1000:.0f}s" if isinstance(ms, (int, float)) else ""
        files = _pick(payload, "modified_files", "modifiedFiles", "files") or []
        tools = _pick(payload, "tool_call_count", "toolCallCount", "tool_calls")
        tools = "" if tools is None else str(tools)
        if files:
            tools = f"{tools} ({len(files)} files)" if tools else f"{len(files)} files"
        return label, dur, tools

    if event == "preCompact":
        pct = payload.get("context_usage_percent")
        size = payload.get("context_window_size")
        tokens = payload.get("context_tokens")
        first = " (first)" if payload.get("is_first_compaction") else ""
        detail = f"compaction {payload.get('trigger') or 'auto'}{first}"
        if isinstance(pct, (int, float)):
            detail += f" at {pct:.0f}%"
        if isinstance(tokens, (int, float)) and isinstance(size, (int, float)):
            detail += f" ({tokens:,.0f}/{size:,.0f} tok)"
        dropped = payload.get("messages_to_compact")
        return detail, "", ("" if dropped is None else f"-{dropped} msg")

    return None


def _delegation_audit(target):
    """At the end of a run, say whether wave 4 was actually delegated.

    The manifest already records delegated waves, but only the ones that happened, and an
    absent row is indistinguishable from a run nobody delegated. Across four completed
    accounts the auto-log held twelve compactions and no delegated wave at all: every
    section was written in the main context, which is what filled it. Counting section
    files against logged subagents turns that from something you notice afterwards into a
    line in the manifest.
    """
    sections = os.path.join(target, "sections")
    if not os.path.isdir(sections):
        return None
    n_sections = sum(1 for f in os.listdir(sections)
                     if f.endswith(".py") and not f.startswith("_"))
    if not n_sections:
        return None
    path = os.path.join(target, MANIFEST)
    log = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            log = fh.read()
    delegated = log.count("| subagentStop |")
    compactions = log.count("| preCompact |")
    verdict = (f"{n_sections} section file(s), {delegated} delegated wave(s), "
               f"{compactions} compaction(s)")
    if not delegated:
        verdict += " — WAVE 4 WAS NOT DELEGATED: every section was written in the main " \
                   "context, which is what fills it"
    elif compactions > delegated:
        verdict += " — more compactions than delegated waves; the main context is still " \
                   "carrying too much"
    return verdict, "", ""


def main():
    event = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except (ValueError, OSError):
        payload = {}

    target = _target_dir()
    row = _delegation_audit(target) if event == "stop" and target else _row(event, payload)
    if row and target:
        detail, duration, tools = row
        path = os.path.join(target, MANIFEST)
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(_SCAFFOLD)
        stamp = datetime.datetime.now().strftime("%H:%M:%S")
        # The end-of-run audit's detail IS its verdict, so it gets room; a wave label is a
        # name and stays short.
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"| {stamp} | {event} | {_cell(detail, 220)} | "
                     f"{_cell(duration, 16)} | {_cell(tools, 24)} |\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:                       # noqa: BLE001 - see module docstring
        pass                                # a logger may never break a run
    sys.exit(0)
