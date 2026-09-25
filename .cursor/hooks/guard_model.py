"""Enforce the engagement review's model-routing rule, instead of just stating it.

`SKILL.md` says it plainly: never route a section that carries interpretation to a fast
model — if it has a verdict, a benchmark reading or a recommendation, it is frontier
work. That rule has never been enforceable. A subagent gets spawned with whatever model
the orchestrator picked, the layout comes out fine, and the only symptom is a report
that reads thin two hours later when it is too late to redo.

`subagentStart` is the one place that can refuse. It receives the subagent type and the
model that would run it, and it can answer `deny`.

Two events, two jobs:

  subagentStart  refuse a section writer running on a fast model
  stop           record which model actually ran, in work/<client>/run.md

The `stop` half exists because the declared model is not the model you get. Cursor falls
back to a compatible one when an admin has blocked it, when the plan does not include
it, or — on a legacy request-based plan without Max Mode — silently for every subagent.
A skill that calls the frontier model non-negotiable owes the reader a note saying which
model actually wrote the report, rather than claiming a standard it may not have met.

Wired from `.cursor/hooks.json`. Reads the payload as JSON on stdin, writes a JSON
decision on stdout.

    python .cursor/hooks/guard_model.py subagentStart  < payload.json
"""

import datetime
import json
import os
import sys

# Subagent types whose output is prose a client reads, and which therefore may not run
# on a fast model. `airship-appendix` is deliberately absent: its tables come from
# audit.json, so a fast model there is a routing decision, not a downgrade.
_VERDICT_AGENTS = {"airship-section"}

# Fast/small model families. Matched as a substring of the model id, because the id
# carries parameters (`composer-2.5[fast=true]`) and versions move.
_FAST_MODELS = ("composer",)

WORK = "work"
MANIFEST = "run.md"


def _reply(payload):
    sys.stdout.write(json.dumps(payload))


def _model(payload):
    """The model id as a lowercase string, however the payload spells it."""
    for key in ("subagent_model", "model_id", "model"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value.lower()
    return ""


def _guard(payload):
    kind = payload.get("subagent_type") or ""
    model = _model(payload)
    if kind in _VERDICT_AGENTS and any(f in model for f in _FAST_MODELS):
        return {
            "permission": "deny",
            "user_message": (
                f"Refused: `{kind}` would run on `{model}`. A review section carries a "
                f"verdict a client reads, and the skill routes that to a frontier model "
                f"(claude-opus-5[effort=high]). Re-launch it on one, or use "
                f"`airship-appendix` if this is really just a table."),
        }
    return {"permission": "allow"}


def _note_model(payload):
    """Append the model that actually ran to the run manifest.

    Silent when there is no review directory to write to, so this does nothing in
    unrelated conversations.
    """
    if not os.path.isdir(WORK):
        return
    best, best_mtime = None, -1.0
    for name in os.listdir(WORK):
        path = os.path.join(WORK, name)
        if not os.path.isdir(path) or name.startswith((".", "_")):
            continue
        mtimes = [os.path.getmtime(path)]
        try:
            mtimes += [os.path.getmtime(os.path.join(path, c))
                       for c in os.listdir(path)]
        except OSError:
            pass
        m = max(mtimes)
        if m > best_mtime:
            best, best_mtime = path, m
    if not best:
        return

    model = _model(payload) or "unknown"
    params = payload.get("model_params") or []
    if params:
        try:
            model += "[" + ",".join(f"{p['id']}={p['value']}" for p in params) + "]"
        except (KeyError, TypeError):
            pass
    path = os.path.join(best, MANIFEST)
    line = (f"| {datetime.datetime.now().strftime('%H:%M:%S')} | stop | "
            f"model actually used: {model} |  |  |\n")
    # Only append to a manifest that already exists: a `stop` fires on every turn in
    # this project, and creating a manifest for a conversation that is not a review
    # would litter the account directory.
    if os.path.exists(path):
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line)


def main():
    event = sys.argv[1] if len(sys.argv) > 1 else ""
    raw = sys.stdin.read()
    payload = json.loads(raw) if raw.strip() else {}

    if event == "subagentStart":
        _reply(_guard(payload))
    elif event == "stop":
        _note_model(payload)


if __name__ == "__main__":
    try:
        main()
    except Exception:                       # noqa: BLE001
        # Fail OPEN. A crashed guard must not be able to block a delivery; the routing
        # rule is still written down in SKILL.md, and `failClosed` is deliberately not
        # set in hooks.json. Wrong report beats no report at all here.
        _reply({"permission": "allow"})
    sys.exit(0)
