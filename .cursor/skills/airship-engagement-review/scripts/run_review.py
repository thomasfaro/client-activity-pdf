#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The engagement review as a program — waves, parallelism and gates in code.

    python .cursor/skills/airship-engagement-review/scripts/run_review.py \\
        --project "<MCP project>" --client <client> --start 2026-08-01 --end 2026-08-30 \\
        --lang en --orchestration-external unknown --source-pack no

    ... --client <client> --from build          # resume an existing run from a wave
    ... --client <client> --stop-after freeze   # stop at a wave boundary
    ... --mode goals --client <c> --tagging-plan plan.json --vertical "Retail"
    ... --dry-run                               # print the plan, run nothing
    ... --model 'section=<id>[effort=medium]'   # trial a model for one role, one run
    python scripts/run_review.py --check-sdk    # live: models resolve, web search works
    python scripts/run_review.py --selftest     # offline, fake agents

Hooks: .cursor/hooks.json fires on subagentStart/subagentStop, and an SDK agent is a
top-level conversation, not a subagent — so guard_model.py and log_wave.py are not
relied on here. The model pinning they enforce is done in SdkRunner.start (against
Cursor.models.list()) and the wave log is written by Review.row.

orchestration.md describes a run as waves with rules between them: freeze before wave 4, at
most three agents at once, pilots before the fan-out, exec_summary last, a gate that loops
at most three times, a coherence pass that is never skipped. Written as prose, each rule
held as long as the main context remembered it. Here each one is a line of code: the model
does the judgement inside a wave, this file decides what runs, in what order, with which
inputs, and whether the result is allowed to go forward.

Agents run on the Cursor SDK (`pip install cursor-sdk`, `CURSOR_API_KEY`), local runtime,
cwd = the repository, so they see the same files, rules and skills as the IDE. Each role's
model is the `model:` line of its `.cursor/agents/<role>.md`, checked against
`Cursor.models.list()` before anything starts; `--model role=spec` overrides one role for
one run, and the resolved models are kept in run_state.json so a resume uses the same
ones. Tokens and duration per session go to run_state.json → usage. Deterministic waves
are plain subprocesses.

Client data stays under work/<client>/ (git-ignored): run_state.json, .freeze/ and the
run.md rows are written there, never in the skill.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import sys
import time
import types

HERE = os.path.dirname(os.path.realpath(__file__))
SKILL = os.path.dirname(HERE)
REPO = os.path.abspath(os.path.join(SKILL, "..", "..", ".."))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import canonical_sections as cs  # noqa: E402
import verdict_ledger as vl      # noqa: E402
import focus_brief as fb         # noqa: E402
import focus_plan as fp          # noqa: E402

PROMPTS = os.path.join(HERE, "prompts")
AGENTS_DIR = os.path.join(REPO, ".cursor", "agents")
SCRIPTS_REL = os.path.relpath(HERE, REPO)

# Role → agent definition. "frontier" is the main-context writer of the manual path: the
# analysis, the pilots' consultative section, wave 5, the brief amendment, the coherence
# pass. It borrows airship-section's model, the prose model, unless --frontier-model says
# otherwise; nothing that writes client prose is ever routed to a fast model.
ROLE_AGENT = {"brand": "airship-brand-research", "section": "airship-section",
              "appendix": "airship-appendix", "gate_fix": "airship-gate-fix",
              "frontier": "airship-section"}

MAX_PARALLEL = 3        # orchestration.md, "two or three, not ten — in EVERY wave"
CHECK_RETRIES = 2       # check_section fix attempts per section
PREFLIGHT_RETRIES = 2   # analysis fix attempts when verify_audit / build_facts fail
GATE_FIX_ROUNDS = 3     # delivery-gate fix rounds

WAVES = {
    "full": ["brand", "collect", "analysis", "freeze", "assets", "pilots", "factual",
             "consultative", "build", "coherence", "deliver"],
    "goals": ["brand", "goals_prep", "goals_prose", "deliver"],
}
WAVE_DESC = {
    "brand": "wave 0 · one brand-research agent, in the background beside the collection",
    "collect": "wave 1 · collect.py (subprocess, resumable)",
    "analysis": "wave 2a · client categories read by the frontier model (skipped when too "
                "sparse), validated in code; wave 2 · analyst agent → audit.json + "
                "analysis_brief.md; pre-flight (verify_audit, build_facts --verify), ≤2 fix turns",
    "freeze": "FREEZE audit.json · facts.json · analysis_brief.md → checkpoint",
    "assets": "wave 3 · analyst's scaffold turn, then make_charts ∥ make_creatives; "
              "section_slices.json checked; specs/creatives/brand frozen",
    "pilots": "wave 3b · 2 factual pilots in parallel + 1 consultative; brief amended, "
              "re-frozen; PILOT_FIX errors sent back to the pilots → checkpoint",
    "factual": f"wave 4 · the rest of the factual pool, ≤{MAX_PARALLEL} agents, pairs share "
               "one agent; verdict ledger must be contradiction-free",
    "consultative": "wave 5 · one conversation, WAVE5_ORDER, exec_summary last; ledger again",
    "build": f"wave 6 · builder + delivery gate, ≤{GATE_FIX_ROUNDS} gate-fix rounds",
    "coherence": "wave 6 · coherence pass (mandatory); any SUSPECT line blocks delivery",
    "deliver": "wave 7 · source pack if asked, final build + gate, delivery, raw purge",
    "goals_prep": "mode B · parse + analyse the tagging plan, goal_candidates, goals_charts",
    "goals_prose": "mode B · one prose agent fills the builder TODOs, gate --profile goals",
}
FROZEN_AT_FREEZE = ["audit.json", "facts.json", "analysis_brief.md"]
FROZEN_AT_ASSETS = ["specs.json", "creatives.json", "section_slices.json", "brand.json"]
FROZEN_BY_WAVE = {"freeze": FROZEN_AT_FREEZE + ["focus_plan.json"],
                  "assets": FROZEN_AT_ASSETS,
                  "goals_prep": ["goals/goals.json", "goals/brand.json"]}

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_PLACEHOLDER = re.compile(r"{{(\w+)}}")


class Stop(Exception):
    """The run cannot go forward without a human. State is saved; the message says why."""


class PromptError(Stop):
    pass


# ---------------------------------------------------------------------------
# prompts and models
# ---------------------------------------------------------------------------
def render_prompt(name, **values):
    """scripts/prompts/<name>.md with every {{placeholder}} filled — or a PromptError.

    An unfilled placeholder reaching an agent reads as an instruction ("write
    {{key}}.py") and gets obeyed literally. Refusing it here is cheaper than finding
    a section file called `{{key}}.py`.
    """
    with open(os.path.join(PROMPTS, name + ".md"), encoding="utf-8") as fh:
        text = fh.read()
    wanted = set(_PLACEHOLDER.findall(text))
    missing = sorted(w for w in wanted if values.get(w) in (None, ""))
    if missing:
        raise PromptError(f"prompt {name}.md: no value for {', '.join(missing)}")
    return _PLACEHOLDER.sub(lambda m: str(values[m.group(1)]), text)


def parse_model(spec):
    """'claude-opus-5[effort=high]' → ('claude-opus-5', {'effort': 'high'})."""
    m = re.fullmatch(r"\s*([\w.\-]+)\s*(?:\[(.*)\])?\s*", spec or "")
    if not m:
        raise Stop(f"unreadable model spec {spec!r}")
    params = {}
    for part in filter(None, (p.strip() for p in (m.group(2) or "").split(","))):
        k, _, v = part.partition("=")
        params[k.strip()] = v.strip()
    return m.group(1), params


def agent_definition(role, overrides=None):
    """-> (model spec, instructions body) from .cursor/agents/<agent>.md.

    `overrides` maps a role to a model spec (`--model role=spec`). `frontier` borrows
    airship-section's *frontmatter* model, not its override, so a trial on the sections
    alone leaves the analysis and the coherence pass where they were.
    """
    path = os.path.join(AGENTS_DIR, ROLE_AGENT[role] + ".md")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    fm = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not fm:
        raise Stop(f"{path}: no frontmatter")
    model = re.search(r"^model:\s*(.+)$", fm.group(1), re.M)
    if not model:
        raise Stop(f"{path}: frontmatter carries no model:")
    spec = (overrides or {}).get(role) or model.group(1).strip()
    body = text[fm.end():].strip() if role != "frontier" else ""
    return spec, body


def resolve_models(overrides=None):
    """{role: spec} for every role: frontmatter, then the overrides on top."""
    unknown = sorted(set(overrides or {}) - set(ROLE_AGENT))
    if unknown:
        raise Stop(f"--model: unknown role {', '.join(unknown)} "
                   f"(roles: {', '.join(sorted(ROLE_AGENT))})")
    models = {role: agent_definition(role, overrides)[0] for role in ROLE_AGENT}
    for spec in models.values():
        parse_model(spec)
    return models


def parse_overrides(pairs):
    """['section=claude-opus-5-5[effort=medium]'] → {'section': '...'}."""
    out = {}
    for pair in pairs or []:
        role, sep, spec = pair.partition("=")
        if not sep or not spec.strip():
            raise SystemExit(f"--model expects role=spec, got {pair!r}")
        out[role.strip()] = spec.strip()
    return out


def check_model(role, spec, available):
    """Refuse a model, a parameter or a parameter VALUE the account does not offer."""
    mid, params = parse_model(spec)
    if mid not in available:
        raise Stop(f"model {mid!r} (role {role}) is not available to this account; "
                   f"available: {', '.join(sorted(available))}")
    defs = {p.id: [getattr(v, "value", v) for v in p.values]
            for p in available[mid].parameters}
    for k, v in params.items():
        if k not in defs:
            raise Stop(f"model {mid!r} (role {role}) has no parameter {k!r} "
                       f"(it has: {', '.join(sorted(defs)) or 'none'})")
        if defs[k] and v not in defs[k]:
            raise Stop(f"model {mid!r} (role {role}): {k}={v!r} is not offered "
                       f"(values: {', '.join(defs[k])})")
    return mid, params


# ---------------------------------------------------------------------------
# agent runners
# ---------------------------------------------------------------------------
class Session:
    """One agent conversation. Turns keep context; that is what pairs and wave 5 rely on."""

    label = ""

    async def send(self, prompt: str) -> str:
        raise NotImplementedError

    async def close(self):
        pass


class AgentRunner:
    # Called as meter(label, role, duration_ms, TokenUsage-like) after every turn.
    meter = None

    async def start(self, roles, models):
        pass

    async def session(self, role: str, label: str) -> Session:
        raise NotImplementedError

    async def close(self):
        pass


class SdkRunner(AgentRunner):
    """Cursor SDK, local runtime, cwd = repo, project + user settings (rules, skills, MCP)."""

    def __init__(self, log=print):
        self.log = log
        self.client = None
        self.models = {}

    async def start(self, roles, models):
        try:
            import cursor_sdk  # noqa: F401
        except ImportError:
            raise Stop("cursor-sdk is not installed: pip install cursor-sdk")
        if not os.environ.get("CURSOR_API_KEY", "").strip():
            raise Stop("CURSOR_API_KEY is not set (Cursor Dashboard → Integrations)")
        from cursor_sdk import AsyncClient
        self.client = await AsyncClient.launch_bridge(workspace=REPO)
        available = {m.id: m for m in await self.client.list_models(
            api_key=os.environ["CURSOR_API_KEY"])}
        for role in sorted(set(roles)):
            self.models[role] = check_model(role, models[role], available)

    async def session(self, role, label):
        from cursor_sdk import LocalAgentOptions, ModelParameterValue, ModelSelection
        mid, params = self.models[role]
        model = ModelSelection(id=mid, params=[ModelParameterValue(id=k, value=v)
                                               for k, v in params.items()])
        agent = await self.client.agents.create(
            model=model, name=label, api_key=os.environ["CURSOR_API_KEY"],
            local=LocalAgentOptions(cwd=REPO, setting_sources=["project", "user"]))
        _, body = agent_definition(role)
        return _SdkSession(agent, label, role, body, self.log, self.meter)

    async def close(self):
        if self.client is not None:
            # The SDK's bridge runs with stderr=PIPE and waits for the process but never
            # closes the pipe transport; left to the GC, it closes after asyncio.run has
            # closed the loop and prints "Event loop is closed" at exit. Private
            # attributes, hence the getattr chain: a changed SDK only loses the tidy-up.
            proc = getattr(getattr(self.client, "_owned_bridge", None), "process", None)
            await self.client.aclose()
            self.client = None
            transport = getattr(proc, "_transport", None)
            if transport is not None:
                transport.close()
                await asyncio.sleep(0)


class _SdkSession(Session):
    def __init__(self, agent, label, role, instructions, log, meter=None):
        self.agent, self.label, self.role, self.log = agent, label, role, log
        self.instructions = instructions
        self.meter = meter
        self.turns = 0

    async def send(self, prompt):
        # An SDK agent is a conversation, not a subagent: the agent file's instructions
        # ride on the first turn instead of a system prompt.
        if self.turns == 0 and self.instructions:
            prompt = self.instructions + "\n\n---\n\n" + prompt
        self.turns += 1
        run = await self.agent.send(prompt)
        self.log(f"    [{self.label}] agent {getattr(self.agent, 'agent_id', '?')} "
                 f"run {getattr(run, 'id', '?')}")
        result = await run.wait()
        if self.meter is not None:
            self.meter(self.label, self.role, result.duration_ms or 0, result.usage)
        if result.status != "finished":
            raise Stop(f"agent {self.label}: run {result.id} ended {result.status}")
        return result.result or ""

    async def close(self):
        await self.agent.close()


class FakeRunner(AgentRunner):
    """Offline runner for --selftest: `script(role, label, prompt, turn)` plays the agent."""

    def __init__(self, script):
        self.script = script
        self.calls = []
        self.active = 0
        self.peak = 0

    async def session(self, role, label):
        return _FakeSession(self, role, label)


class _FakeUsage:
    input_tokens, output_tokens, cache_read_tokens, cache_write_tokens = 60, 40, 0, 0
    total_tokens = 100


class _FakeSession(Session):
    def __init__(self, runner, role, label):
        self.runner, self.role, self.label, self.turn = runner, role, label, 0

    async def send(self, prompt):
        r = self.runner
        r.active += 1
        r.peak = max(r.peak, r.active)
        try:
            await asyncio.sleep(0.01)
            r.calls.append((self.role, self.label, self.turn, prompt))
            out = r.script(self.role, self.label, prompt, self.turn)
        finally:
            r.active -= 1
        if r.meter is not None:
            r.meter(self.label, self.role, 10, _FakeUsage())
        self.turn += 1
        return out or ""


class Shell:
    async def run(self, argv, cwd=REPO):
        proc = await asyncio.create_subprocess_exec(
            *argv, cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        out, _ = await proc.communicate()
        return proc.returncode, out.decode("utf-8", "replace")


class FakeShell(Shell):
    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    async def run(self, argv, cwd=REPO):
        self.calls.append(list(argv))
        return self.handler(list(argv))


# ---------------------------------------------------------------------------
# file-scope guard and freeze
# ---------------------------------------------------------------------------
_GUARD_SKIP = ("data", "charts", "creatives", "source_pack", "__pycache__", ".freeze",
               "goals")
_GUARD_KEEP = ("run.md", "run.log", "run_state.json", "report.html", "verdicts.json",
               ".run_review.lock")
# Read by .cursor/hooks/log_wave.py and guard_model.py: while it names a live pid, the
# work dir belongs to this script, and a chat turn's `stop` must not write into its run.md.
LOCK = ".run_review.lock"


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        h.update(fh.read())
    return h.hexdigest()


def snapshot(work):
    """{relpath: bytes} for everything an agent could damage (not raw pulls or renders)."""
    snap = {}
    for root, dirs, files in os.walk(work):
        rel_root = os.path.relpath(root, work)
        if rel_root == ".":
            dirs[:] = [d for d in dirs if d not in _GUARD_SKIP]
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            rel = os.path.normpath(os.path.join(rel_root, f))
            if rel in _GUARD_KEEP or f.endswith((".pyc", ".html", ".pdf", ".png")):
                continue
            with open(os.path.join(root, f), "rb") as fh:
                snap[rel] = fh.read()
    return snap


def enforce_scope(work, before, allowed, denied=()):
    """Revert every change outside `allowed`, or inside `denied` (relpaths, fnmatch-style).
    -> reverted list."""
    import fnmatch
    after = snapshot(work)
    reverted = []

    def ok(rel):
        return (any(fnmatch.fnmatch(rel, pat) for pat in allowed)
                and not any(fnmatch.fnmatch(rel, pat) for pat in denied))

    for rel in sorted(set(before) | set(after)):
        if before.get(rel) == after.get(rel) or ok(rel):
            continue
        path = os.path.join(work, rel)
        if rel in before:
            with open(path, "wb") as fh:
                fh.write(before[rel])
        else:
            os.remove(path)
        reverted.append(rel)
    return reverted


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------
class Review:
    def __init__(self, args, runner: AgentRunner, shell: Shell, log=print):
        self.a = args
        self.runner = runner
        self.shell = shell
        self.log = log
        self.work = os.path.join(REPO, "work", args.client)
        self.rel = os.path.relpath(self.work, REPO)
        self.state_path = os.path.join(self.work, "run_state.json")
        self.state = {"inputs": {}, "done": [], "hashes": {}, "deviations": []}
        self.sem = asyncio.Semaphore(MAX_PARALLEL)
        self.brand_task = None
        self.analyst = None      # the wave-2 conversation, reused for the scaffold turn
        self.wave5 = None        # the single wave-5 conversation
        self.concurrent = False  # True while several writers run at once
        self.models = {}         # {role: spec}, fixed for the whole run
        runner.meter = self.meter

    # ---- models and usage -------------------------------------------------
    def setup_models(self, overrides, record=True):
        """Resolve {role: spec}. A resumed run keeps the models it started with: a
        section written by one model and its neighbour by another is a mixed report, so
        a new --model on resume is allowed but logged as a deviation."""
        fresh = resolve_models(overrides)
        saved = self.state.get("models") or {}
        if saved and self.state["done"]:
            models = {**fresh, **saved}
            for role, spec in sorted(overrides.items()):
                if saved.get(role) != spec:
                    note = f"model for {role} changed on resume: {saved.get(role)} → {spec}"
                    self.deviation(note) if record else self.log(f"  {note}")
                    models[role] = spec
            drift = sorted(r for r in saved if r not in overrides and fresh[r] != saved[r])
            if drift:
                self.log(f"  note: .cursor/agents changed since this run started "
                         f"({', '.join(drift)}); keeping the run's models")
        else:
            models = fresh
        self.models = models
        if record:
            self.state["models"] = models
            self.save_state()
            self._run_md_block("## Orchestrator models",
                               "\n".join(f"- {r}: `{models[r]}`" for r in sorted(models)))

    def meter(self, label, role, ms, usage):
        u = self.state.setdefault("usage", {}).setdefault(label, {
            "role": role, "model": self.models.get(role, ""), "turns": 0, "ms": 0,
            "input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "total": 0})
        u["turns"] += 1
        u["ms"] += int(ms or 0)
        for key, attr in (("input", "input_tokens"), ("output", "output_tokens"),
                          ("cache_read", "cache_read_tokens"),
                          ("cache_write", "cache_write_tokens"), ("total", "total_tokens")):
            u[key] += int(getattr(usage, attr, 0) or 0)
        self.save_state()

    def _tokens_since(self, labels):
        """Tokens spent by these sessions ('x*' = prefix) since their last log row."""
        seen = self.state.setdefault("usage_reported", {})
        n = 0
        for label, u in self.state.get("usage", {}).items():
            if any(label == p or (p.endswith("*") and label.startswith(p[:-1]))
                   for p in labels):
                n += u["total"] - seen.get(label, 0)
                seen[label] = u["total"]
        return n

    # ---- state ------------------------------------------------------------
    def load_state(self):
        if os.path.isfile(self.state_path):
            with open(self.state_path, encoding="utf-8") as fh:
                self.state.update(json.load(fh))

    def save_state(self):
        os.makedirs(self.work, exist_ok=True)
        with open(self.state_path, "w", encoding="utf-8") as fh:
            json.dump(self.state, fh, indent=1, ensure_ascii=False)

    def deviation(self, text):
        self.log(f"  deviation: {text}")
        self.state["deviations"].append(text)
        self._run_md_append(f"- {text}", section="## Orchestrator deviations")
        self.save_state()

    def row(self, wave, task, role, started, notes="", usage=()):
        """`usage`: session labels whose tokens this row accounts for ('x*' = prefix)."""
        model = self.models.get(role, "") if role else ""
        n = self._tokens_since(usage) if usage else 0
        tokens = f"{n / 1000:.1f}k" if n else ""
        done = time.strftime("%H:%M")
        self._run_md_append(
            f"| {wave} | {task} | {model} | {started} | {done} | {tokens} | {notes} |",
            section="## Orchestrator log",
            header="| wave | task | model | started | done | tokens | notes |\n"
                   "|---|---|---|---|---|---|---|")

    def _run_md_block(self, section, body):
        """Replace the whole body of `section` (appended if absent)."""
        path = os.path.join(self.work, "run.md")
        os.makedirs(self.work, exist_ok=True)
        text = open(path, encoding="utf-8").read() if os.path.isfile(path) else (
            f"# {self.a.client} — run {dt.date.today().isoformat()}\n\nReviewed-by:\n")
        if section not in text:
            text = text.rstrip("\n") + f"\n\n{section}\n"
        head, _, tail = text.partition(section)
        nxt = tail.find("\n## ")
        rest = "" if nxt < 0 else tail[nxt:]
        text = head + section + "\n\n" + body.rstrip("\n") + "\n" + rest
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def _run_md_append(self, line, section, header=None):
        path = os.path.join(self.work, "run.md")
        os.makedirs(self.work, exist_ok=True)
        text = open(path, encoding="utf-8").read() if os.path.isfile(path) else (
            f"# {self.a.client} — run {dt.date.today().isoformat()}\n\nReviewed-by:\n")
        if section not in text:
            text = text.rstrip("\n") + f"\n\n{section}\n\n" + (header + "\n" if header else "")
        head, _, tail = text.partition(section)
        nxt = tail.find("\n## ")
        block, rest = (tail, "") if nxt < 0 else (tail[:nxt], tail[nxt:])
        text = head + section + block.rstrip("\n") + "\n" + line + "\n" + rest
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    # ---- freeze -----------------------------------------------------------
    def freeze(self, names):
        store = os.path.join(self.work, ".freeze")
        os.makedirs(store, exist_ok=True)
        for n in names:
            p = os.path.join(self.work, n)
            if not os.path.isfile(p):
                continue
            self.state["hashes"][n] = _sha(p)
            shutil.copy2(p, os.path.join(store, n.replace("/", "__")))
        self.save_state()

    def check_frozen(self, wave):
        """A frozen file changed → restore it and stop: every section quoting it is stale."""
        broken = []
        for n, h in self.state["hashes"].items():
            p = os.path.join(self.work, n)
            if os.path.isfile(p) and _sha(p) == h:
                continue
            shutil.copy2(os.path.join(self.work, ".freeze", n.replace("/", "__")), p)
            broken.append(n)
        if broken:
            raise Stop(f"frozen {', '.join(broken)} changed during {wave} — restored; "
                       f"find which agent edited it before resuming")

    def scope(self, before, allowed, who, denied=()):
        """Revert what `who` touched outside `allowed`; a frozen file among them stops."""
        reverted = enforce_scope(self.work, before, allowed, denied)
        for r in reverted:
            self.deviation(f"{who} edited {r} outside its scope — reverted")
        frozen = [r for r in reverted if r in self.state["hashes"]]
        if frozen:
            raise Stop(f"{who} edited frozen {', '.join(frozen)} — restored; every section "
                       f"quoting it would be stale. Find why before resuming")
        self.check_frozen(who)

    def writer_scope(self, key):
        # Concurrent writers land files while another agent's snapshot is open, so in
        # waves 3b and 4 the snapshot cannot tell whose file is whose: the scope there is
        # the sections tree, and check_section on each key catches a cross-write.
        if self.concurrent:
            return ["sections/*.py", "verdicts/*.json"]
        if key == fp.ANSWERS_KEY:
            return [f"sections/{key}.py", "answers.json"]
        return [f"sections/{key}.py", f"verdicts/{key}.json"]

    # ---- helpers ----------------------------------------------------------
    def py(self, script, *args):
        return [sys.executable, os.path.join(SCRIPTS_REL, script), *args]

    async def sh(self, argv, what):
        self.log(f"  $ {' '.join(argv)}")
        code, out = await self.shell.run(argv)
        lines = out.strip().splitlines()
        # The gate prints its ✗ where the check sits, often far above the last lines.
        early = [l for l in lines[:-12] if l.strip().startswith("[✗]")]
        if early:
            self.log("    (failures above the tail)\n    " + "\n    ".join(early))
        tail = "\n".join(lines[-12:])
        if tail:
            self.log("    " + tail.replace("\n", "\n    "))
        return code, out

    def checkpoint(self, name, next_wave, summary):
        if self.a.unattended:
            self.deviation(f"checkpoint '{name}' passed unattended")
            return
        self.log(f"\n== CHECKPOINT {name} ==\n{summary}")
        if not sys.stdin.isatty():
            raise Stop(f"checkpoint {name}: review, then resume with --from {next_wave}")
        if input("Continue? [y/N] ").strip().lower() not in ("y", "yes", "o", "oui"):
            raise Stop(f"stopped at checkpoint {name}; resume with --from {next_wave}")

    def refs(self, key):
        files = cs.reference_files_for(key)
        return "\n".join(f"      .cursor/skills/airship-engagement-review/reference/{f}.md"
                         for f in files) or "      (none routed)"

    def slices(self):
        p = os.path.join(self.work, "section_slices.json")
        return json.load(open(p, encoding="utf-8")) if os.path.isfile(p) else {}

    def title(self, key):
        return cs.BY_KEY[key].get("title_en") or key

    def has_tagging_plan(self):
        i = self.state["inputs"]
        return bool(i.get("tagging_plan")) or os.path.isfile(
            os.path.join(self.work, "tagging_plan.json"))

    def questions(self):
        """The brief's questions; non-empty means a focused review."""
        return self.state["inputs"].get("questions") or []

    def focus(self):
        """focus_plan.json once the analyst wrote it (focused mode), else {}."""
        return fp.load_plan(self.work) if self.questions() else {}

    def context_ref(self):
        """Where the account team's brief sits, for the prompts; copied in by run()."""
        if os.path.isfile(os.path.join(self.work, "client_context.md")):
            return (f"work/{self.a.client}/client_context.md — the account team's brief: "
                    f"the questions this review must answer, and context the API cannot show")
        return "none supplied"

    def section_values(self, key):
        i = self.state["inputs"]
        sl = self.slices().get(key, {})
        return dict(client=self.a.client, key=key, title=self.title(key), lang=i["lang"],
                    orchestration_external=i["orchestration_external"],
                    reference_files=self.refs(key), client_context=self.context_ref(),
                    audit_keys=", ".join(sl.get("audit_keys") or []) or "(none listed)",
                    chart_ids=", ".join(sl.get("chart_ids") or []) or "(none)",
                    depth_rule=fp.depth_rule(self.focus(), key),
                    focus_rule=fp.consultative_rule(self.a.client, key, self.focus()))

    # ---- per-section check with bounded retries ----------------------------
    async def check_section(self, key):
        code, out = await self.sh(self.py("check_section.py", self.rel, key,
                                          "--lang", self.state["inputs"]["lang"]),
                                  f"check {key}")
        return code == 0, out

    async def settle_section(self, sess, key, needs_verdict):
        """check_section until OK; ≤ CHECK_RETRIES fixes; the same failure twice stops."""
        ok, out = await self.check_section(key)
        if ok and needs_verdict and not os.path.isfile(
                os.path.join(self.work, "verdicts", key + ".json")):
            ok, out = False, f"no verdict record at verdicts/{key}.json"
        last = None
        for attempt in range(CHECK_RETRIES):
            if ok:
                return out
            failure = "\n".join(l for l in out.splitlines()
                                if l.strip().startswith(("!", "✗", "FAIL", "no verdict")))
            failure = failure or out.strip()[-2000:]
            if failure == last:
                raise Stop(f"section {key}: the same failure twice —\n{failure}")
            last = failure
            own = [f"sections/{key}.py", f"verdicts/{key}.json"]
            before = snapshot(self.work)
            await sess.send(render_prompt("fix_section", client=self.a.client, key=key,
                                          failure=failure, allowed_files=", ".join(own)))
            self.scope(before, self.writer_scope(key), f"fix of {key}")
            ok, out = await self.check_section(key)
            if ok and needs_verdict and not os.path.isfile(
                    os.path.join(self.work, "verdicts", key + ".json")):
                ok, out = False, f"no verdict record at verdicts/{key}.json"
        if not ok:
            raise Stop(f"section {key} still fails check_section after {CHECK_RETRIES} fixes")
        return out

    async def write_unit(self, keys, wave="4"):
        """One agent writes `keys` in successive turns (a pair shares one conversation)."""
        async with self.sem:
            appendix = all(k in cs.APPENDIX_POOL for k in keys)
            role = "appendix" if appendix else "section"
            sess = await self.runner.session(role, "+".join(keys))
            reports = []
            try:
                for key in keys:
                    started = time.strftime("%H:%M")
                    before = snapshot(self.work)
                    await sess.send(render_prompt("appendix" if appendix else "section",
                                                  **self.section_values(key)))
                    self.scope(before, self.writer_scope(key), f"writer of {key}")
                    reports.append(await self.settle_section(sess, key, not appendix))
                    self.row(wave, key, role, started, usage=["+".join(keys)])
            finally:
                await sess.close()
            return reports

    def units(self, pool):
        """Pool → writing units, the WAVE4_PAIRS kept in one conversation."""
        left, out = list(pool), []
        for a, b in cs.WAVE4_PAIRS:
            if a in left and b in left:
                out.append([a, b])
                left.remove(a)
                left.remove(b)
        return out + [[k] for k in left]

    # ---- waves ------------------------------------------------------------
    async def w_brand(self):
        i = self.state["inputs"]
        started = time.strftime("%H:%M")
        sess = await self.runner.session("brand", "brand")
        try:
            await sess.send(render_prompt("brand", client=self.a.client,
                                          brand=i.get("brand") or self.a.client,
                                          country=i.get("country") or "unspecified",
                                          client_context=self.context_ref()))
        finally:
            await sess.close()
        code, out = await self.sh(self.py("check_brand.py",
                                          os.path.join(self.rel, "brand.json")), "brand")
        if code != 0:
            raise Stop("brand.json fails check_brand.py. If web search is not available to "
                       "SDK agents on this machine, run wave 0 in the IDE (prompts/brand.md) "
                       "and resume with --from analysis.\n" + out[-1500:])
        self.row("0", "brand research", "brand", started, usage=["brand"])

    async def w_collect(self):
        i = self.state["inputs"]
        started = time.strftime("%H:%M")
        if i.get("source_pack") == "yes":
            open(os.path.join(self.work, ".source-pack-pending"), "w").close()
        code, _ = await self.sh(self.py("collect.py", i["project"], "--start", i["start"],
                                        "--end", i["end"], "--out",
                                        os.path.join(self.rel, "data")), "collect")
        if code != 0:
            raise Stop("collect.py failed — it is resumable: fix the cause and "
                       "resume with --from collect")
        self.row("1", "collect.py", None, started)

    async def preflight(self):
        audit = os.path.join(self.rel, "audit.json")
        c1, o1 = await self.sh(self.py("verify_audit.py", audit), "verify_audit")
        c2, o2 = await self.sh(self.py("build_facts.py", audit, "--verify"), "build_facts")
        if not self.questions():
            return (c1 == 0 and c2 == 0), (o1 + "\n" + o2)
        c3, o3 = await self.sh(self.py("focus_plan.py", "--check", self.rel), "focus_plan")
        return (c1 == 0 and c2 == 0 and c3 == 0), (o1 + "\n" + o2 + "\n" + o3)

    async def w_categories(self):
        """Wave 2a: the frontier model reads the client's category scheme; code tests it.

        Skipped when the account tags too little to read (prepare says available=False) or
        when a valid category_hypotheses.json is already there (a resume). A reading that
        still fails validation after the fixes is dropped, not a stop: analyze.py then runs
        on the lexicon alone, and the deviation says so.
        """
        started = time.strftime("%H:%M")
        code, out = await self.sh(self.py("campaign_categories.py", "prepare", self.rel),
                                  "categories prepare")
        if code != 0:
            self.deviation("campaign_categories prepare failed — categories not read")
            return
        verdict = next((l.strip() for l in out.splitlines() if "available=" in l), "")
        self._run_md_block("## Client categories (wave 2a)",
                           f"- prepare: `{verdict or out.strip()[-300:]}`")
        if "available=True" not in out:
            why = re.search(r"reason=(.*?) scheme=", out)
            self.row("2a", "client categories", None, started,
                     "skipped: " + (why.group(1) if why else "unreadable"))
            return
        hp = os.path.join(self.work, "category_hypotheses.json")
        validate = self.py("campaign_categories.py", "validate", self.rel)
        if os.path.isfile(hp) and (await self.sh(validate, "categories validate"))[0] == 0:
            self.row("2a", "client categories", None, started, "kept existing hypotheses")
            return
        allowed = ["category_hypotheses.json"]
        sess = await self.runner.session("frontier", "categories")
        try:
            before = snapshot(self.work)
            await sess.send(render_prompt("categories", client=self.a.client))
            self.scope(before, allowed, "categories reader")
            for attempt in range(PREFLIGHT_RETRIES + 1):
                code, out = await self.sh(validate, "categories validate")
                if code == 0:
                    break
                if attempt == PREFLIGHT_RETRIES:
                    if os.path.isfile(hp):
                        os.remove(hp)
                    fail = next((l.strip() for l in out.splitlines()
                                 if l.strip().startswith("FAIL")), out.strip()[-200:])
                    self.deviation("category_hypotheses.json still invalid after "
                                   f"{PREFLIGHT_RETRIES} fixes — dropped, lexicon only "
                                   f"(last: {fail})")
                    break
                before = snapshot(self.work)
                await sess.send("campaign_categories.py validate failed. Fix "
                                "category_hypotheses.json only, then re-run it.\n\n"
                                + out[-3000:])
                self.scope(before, allowed, "categories reader")
        finally:
            await sess.close()
        self.row("2a", "client categories", "frontier", started,
                 "hypotheses validated" if os.path.isfile(hp) else "lexicon only",
                 usage=["categories"])

    async def w_analysis(self):
        i = self.state["inputs"]
        await self.w_categories()
        started = time.strftime("%H:%M")
        self.analyst = await self.runner.session("frontier", "analysis")
        await self.analyst.send(render_prompt(
            "analysis", client=self.a.client, project=i.get("project") or "-",
            start=i["start"], end=i["end"], lang=i["lang"],
            orchestration_external=i["orchestration_external"],
            tagging_plan=i.get("tagging_plan") or "none supplied",
            client_context=self.context_ref(),
            focus_rule=fp.analysis_rule(self.a.client, self.questions())))
        for attempt in range(PREFLIGHT_RETRIES + 1):
            ok, out = await self.preflight()
            if ok:
                break
            if attempt == PREFLIGHT_RETRIES:
                raise Stop("pre-flight still fails after "
                           f"{PREFLIGHT_RETRIES} fixes:\n{out[-2500:]}")
            await self.analyst.send("The pre-flight failed. A FAIL is a stop, not a note: fix "
                                    "analyze.py (never audit.json by hand), re-run it, then "
                                    "re-run the checks. A focus plan FAIL is fixed in "
                                    "focus_plan.json.\n\n" + out[-4000:])
        brief = os.path.join(self.work, "analysis_brief.md")
        if not os.path.isfile(brief):
            raise Stop("wave 2 wrote no analysis_brief.md")
        missing = [h for h in ("Key findings", "Conflicts settled", "Withheld metrics",
                               "External orchestration", "House style", "Terminology lock")
                   if f"## {h}" not in open(brief, encoding="utf-8").read()]
        if missing:
            raise Stop(f"analysis_brief.md lacks: {', '.join(missing)}")
        self.row("2", "analysis + pre-flight", "frontier", started, "pre-flight PASS",
                 usage=["analysis"])

    async def w_freeze(self):
        if self.brand_task is not None:
            await self.brand_task
        frozen = FROZEN_AT_FREEZE + (["focus_plan.json"] if self.questions() else [])
        self.freeze(frozen)
        self.row("—", "FREEZE", None, time.strftime("%H:%M"), " · ".join(frozen))
        brief = open(os.path.join(self.work, "analysis_brief.md"), encoding="utf-8").read()
        findings = brief.split("## Key findings", 1)[-1].split("\n## ", 1)[0].strip()
        plan = self.focus()
        focus = f"\n\nFocus plan (what answers each question):\n{fp.summary(plan)}" if plan else ""
        self.checkpoint("pre-flight", "assets",
                        f"Pre-flight passed. Key findings the report will argue:\n{findings}"
                        + focus)

    def section_keys(self):
        keys = [s["key"] for s in cs.CANONICAL_SECTIONS if s["key"] != "cover"]
        if not self.questions():
            keys = [k for k in keys if k != fp.ANSWERS_KEY]
        if not self.has_tagging_plan():
            keys = [k for k in keys if k != "data_foundation" and k not in cs.APPENDIX_POOL]
        if not self.has_categories():
            keys = [k for k in keys if k != "client_categories"]
        return keys

    def has_categories(self):
        """audit.categories says the client's categories were readable (wave 2a)."""
        p = os.path.join(self.work, "audit.json")
        try:
            cats = json.load(open(p, encoding="utf-8")).get("categories")
        except (OSError, ValueError, AttributeError):
            return False
        return isinstance(cats, dict) and bool(cats.get("available"))

    async def w_assets(self):
        started = time.strftime("%H:%M")
        if self.analyst is None:
            self.analyst = await self.runner.session("frontier", "analysis")
        before = snapshot(self.work)
        await self.analyst.send(render_prompt("scaffold", client=self.a.client,
                                              lang=self.state["inputs"]["lang"],
                                              section_keys=", ".join(self.section_keys())))
        await self.analyst.close()
        self.analyst = None
        self.scope(before, ["build_report.py", "sections/_shared.py", "make_charts.py",
                            "make_creatives.py", "section_slices.json"], "scaffold turn")
        slices = self.slices()
        missing = [k for k in self.section_keys() if k not in slices]
        if missing:
            raise Stop(f"section_slices.json has no entry for {', '.join(missing)}: "
                       f"those sections would be written blind")
        (c1, o1), (c2, o2) = await asyncio.gather(
            self.sh([sys.executable, os.path.join(self.rel, "make_charts.py")], "charts"),
            self.sh([sys.executable, os.path.join(self.rel, "make_creatives.py")], "creatives"))
        if c1 or c2:
            raise Stop("wave 3 failed — no section may render before both finish:\n"
                       + (o1 if c1 else o2)[-2000:])
        specs = json.load(open(os.path.join(self.work, "specs.json"), encoding="utf-8"))
        ids = set(specs) if isinstance(specs, dict) else {s.get("id") for s in specs}
        dangling = sorted({f"{k}:{c}" for k, v in slices.items()
                           for c in v.get("chart_ids") or [] if c not in ids})
        if dangling:
            raise Stop(f"section_slices.json names charts make_charts.py did not emit: "
                       f"{', '.join(dangling)}")
        self.freeze(FROZEN_AT_ASSETS)
        self.row("3", "scaffold + charts ∥ creatives", "frontier", started, usage=["analysis"])

    async def w_pilots(self):
        started = time.strftime("%H:%M")
        pool = [k for k in cs.PILOT_FACTUAL if k in self.section_keys()]
        self.concurrent = True
        try:
            factual = await asyncio.gather(*(self.write_unit([k], "3b") for k in pool))
        finally:
            self.concurrent = False
        cons = await self.write_consultative([cs.PILOT_CONSULTATIVE], label="pilot")
        report = "\n\n".join(r for rs in factual for r in rs) + "\n\n" + "\n\n".join(cons)
        amend = await self.runner.session("frontier", "brief-amend")
        brief = "analysis_brief.md"
        # The one sanctioned edit to a frozen file: thawed for this turn, re-frozen after.
        self.state["hashes"].pop(brief, None)
        try:
            before = snapshot(self.work)
            reply = await amend.send(render_prompt(
                "brief_amend", client=self.a.client,
                pilot_keys=", ".join(pool + [cs.PILOT_CONSULTATIVE]),
                pilot_report=report[-6000:]))
            self.scope(before, [brief], "brief amendment")
        finally:
            await amend.close()
            self.freeze([brief])
        self.row("3b", "pilots + brief re-frozen", "frontier", started, usage=["brief-amend"])
        fixes = self.pilot_fixes(reply, pool + [cs.PILOT_CONSULTATIVE])
        for key, errors in fixes.items():
            await self.fix_pilot(key, errors)
        self.checkpoint("pilots", "factual",
                        f"Pilots written and checked. The brief now also carries:\n{reply}")

    def pilot_fixes(self, reply, keys):
        """`PILOT_FIX: key · error · fix` lines of the brief amendment → {key: [error]}."""
        fixes = {}
        for line in (reply or "").splitlines():
            m = re.match(r"\s*`?PILOT_FIX:\s*(.+?)`?\s*$", line)
            if not m or m.group(1).strip().lower() in ("none", "none."):
                continue
            key, _, rest = m.group(1).partition("·")
            key = key.strip().strip("`")
            if key not in keys:
                self.deviation(f"brief amendment sent a fix to '{key}', not a pilot — ignored")
                continue
            fixes.setdefault(key, []).append(rest.strip() or m.group(1).strip())
        return fixes

    async def fix_pilot(self, key, errors):
        """Send the amendment's errors back to the pilot's writer, then re-check it."""
        started = time.strftime("%H:%M")
        role = "frontier" if key == cs.PILOT_CONSULTATIVE else "section"
        label = f"pilot-fix-{key}"
        failure = "\n".join(f"! {e}" for e in errors)
        own = [f"sections/{key}.py", f"verdicts/{key}.json"]
        sess = await self.runner.session(role, label)
        try:
            before = snapshot(self.work)
            await sess.send(render_prompt("fix_section", client=self.a.client, key=key,
                                          failure="The brief amendment found, after the "
                                          "pilots were written:\n" + failure,
                                          allowed_files=", ".join(own)))
            self.scope(before, own, f"pilot fix of {key}")
            await self.settle_section(sess, key, True)
        finally:
            await sess.close()
        for e in errors:
            self._run_md_append(f"- {key}: {e}", section="## Pilot fixes")
        self.row("3b", f"pilot fix {key}", role, started,
                 f"{len(errors)} error(s) sent back", usage=[label])

    async def w_factual(self):
        started = time.strftime("%H:%M")
        keys = set(self.section_keys())
        pool = [k for k in cs.FACTUAL_POOL + cs.APPENDIX_POOL
                if k in keys and k not in cs.PILOT_FACTUAL]
        self.concurrent = True
        try:
            await asyncio.gather(*(self.write_unit(u) for u in self.units(pool)))
        finally:
            self.concurrent = False
        self.ledger("before wave 5")
        self.row("4", f"{len(pool)} factual sections, ≤{MAX_PARALLEL} at once", "section",
                 started)

    def ledger(self, when):
        led = vl.merge(self.work)
        for p in led["problems"]:
            self.deviation(f"verdict record: {p}")
        if led["conflicts"]:
            raise Stop(f"verdict ledger {when}: sections contradict each other —\n"
                       + "\n".join("  " + c["detail"] for c in led["conflicts"])
                       + "\nsettle it in the sections (or the brief), then resume")
        self.log(f"  ledger {when}: {len(led['records'])} verdicts, no contradiction")

    async def write_consultative(self, keys, label="wave5"):
        """Wave 5 in ONE conversation, one key per turn, exec_summary last."""
        if self.wave5 is None:
            self.wave5 = await self.runner.session("frontier", label)
        reports = []
        for n, key in enumerate(keys):
            started = time.strftime("%H:%M")
            vl.merge(self.work)
            vals = self.section_values(key)
            vals["remaining"] = ", ".join(keys[n + 1:]) or "none — this is the last one"
            before = snapshot(self.work)
            await self.wave5.send(render_prompt("consultative", **vals))
            self.scope(before, self.writer_scope(key), f"writer of {key}")
            needs = key not in ("appendix", fp.ANSWERS_KEY)
            reports.append(await self.settle_section(self.wave5, key, needs))
            if key == fp.ANSWERS_KEY:
                code, out = await self.sh(self.py("focus_plan.py", "--check-answers",
                                                  self.rel), "answers")
                if code != 0:
                    raise Stop("answers.json does not answer every question of the brief "
                               "— a question dropped here ships unanswered:\n"
                               + out[-2000:] + "\nfix it, then resume with --from consultative")
            self.row("5" if label == "wave5" else "3b", key, "frontier", started, usage=[label])
        if label != "wave5":
            await self.wave5.close()
            self.wave5 = None
        return reports

    async def w_consultative(self):
        keys = [k for k in cs.WAVE5_ORDER if k in self.section_keys()
                and k != cs.PILOT_CONSULTATIVE]
        try:
            await self.write_consultative(keys)
        finally:
            if self.wave5 is not None:
                await self.wave5.close()
                self.wave5 = None
        self.ledger("after wave 5")

    def builder_argv(self, final=False):
        i = self.state["inputs"]
        argv = [sys.executable, os.path.join(self.rel, "build_report.py")]
        if not final or self.a.keep_raw:
            argv.append("--keep-raw")
        if i.get("bilingual"):
            argv.append("--bilingual")
        if final and i.get("pdf"):
            argv.append("--pdf")
        return argv

    @staticmethod
    def gate_failures(out):
        return [l.strip() for l in out.splitlines() if l.strip().startswith("[✗]")]

    def log_gate(self, when, fails):
        for f in fails:
            self._run_md_append(f"- {when}: {f}", section="## Gate failures")

    async def w_build(self):
        started = time.strftime("%H:%M")
        code, out = await self.sh(self.builder_argv(), "build")
        last = None
        for rnd in range(GATE_FIX_ROUNDS):
            if code == 0:
                break
            fails = self.gate_failures(out) or [out.strip()[-1500:]]
            self.log_gate(f"build, round {rnd + 1}", fails)
            if fails == last:
                raise Stop("the gate-fix loop made no progress:\n" + "\n".join(fails))
            last = fails
            allowed = ["sections/*.py"]
            denied = ["sections/_shared.py"]
            sess = await self.runner.session("gate_fix", f"gate-fix-{rnd + 1}")
            before = snapshot(self.work)
            try:
                reply = await sess.send(render_prompt(
                    "gate_fix", client=self.a.client, failures="\n".join(fails),
                    allowed_files=", ".join(allowed) + " (not sections/_shared.py)"))
            finally:
                await sess.close()
            self.scope(before, allowed, "gate-fix", denied)
            if re.search(r"\b(hand(ing)? (it )?back|structural|content problem)\b",
                         reply, re.I):
                raise Stop("the gate-fix agent handed back a content failure — the "
                           "section(s) need rewriting:\n" + reply[-2000:])
            code, out = await self.sh(self.builder_argv(), "build")
        if code != 0:
            self.log_gate("build, after the fix rounds", self.gate_failures(out))
            raise Stop(f"delivery gate still fails after {GATE_FIX_ROUNDS} rounds:\n"
                       + "\n".join(self.gate_failures(out)))
        self.row("6", "build + gate", "gate_fix", started, "gate PASS", usage=["gate-fix-*"])

    async def w_coherence(self):
        started = time.strftime("%H:%M")
        if self.a.skip_coherence:
            self.deviation("coherence pass SKIPPED by --skip-coherence: nobody read the "
                           "report end to end before delivery")
            return
        vl.merge(self.work)
        sess = await self.runner.session("frontier", "coherence")
        before = snapshot(self.work)
        try:
            reply = await sess.send(render_prompt(
                "coherence", client=self.a.client,
                focus_rule=fp.coherence_rule(self.a.client, self.focus())))
        finally:
            await sess.close()
        self.scope(before, ["sections/*.py"], "coherence pass")
        suspects = [l.strip() for l in reply.splitlines()
                    if l.strip().startswith("SUSPECT:") and "none" not in l.lower()]
        code, out = await self.sh(self.builder_argv(), "rebuild")
        if code != 0:
            self.log_gate("rebuild after coherence", self.gate_failures(out))
            raise Stop("the coherence pass broke the gate:\n"
                       + "\n".join(self.gate_failures(out)))
        self.ledger("after coherence")
        if suspects:
            for s in suspects:
                self._run_md_append(f"- {s}", section="## Suspect figures (block delivery)")
            raise Stop("coherence pass raised suspect figures — a human decides each, then "
                       "resume with --from deliver:\n" + "\n".join(suspects))
        self.row("6", "coherence pass", "frontier", started, "no suspect figure",
                 usage=["coherence"])

    async def w_deliver(self):
        started = time.strftime("%H:%M")
        i = self.state["inputs"]
        if i.get("mode") == "goals":
            code, out = await self.sh(self.py(
                "verify_report.py", "--profile", "goals",
                os.path.join(self.rel, "goals", "goals_review.html")), "gate")
            if code != 0:
                raise Stop("goals gate fails:\n" + "\n".join(self.gate_failures(out)))
            self.row("4", "goals gate", None, started, "PASS")
            return
        if i.get("source_pack") == "yes":
            code, out = await self.sh(self.py("build_source_pack.py", self.rel,
                                              "--client", i.get("brand") or self.a.client,
                                              "--lang", i["lang"]), "source pack")
            if code != 0:
                raise Stop("build_source_pack.py failed:\n" + out[-1500:])
        code, out = await self.sh(self.builder_argv(final=True), "final build")
        if code != 0:
            self.log_gate("final build", self.gate_failures(out))
            raise Stop("final build fails the gate:\n" + "\n".join(self.gate_failures(out)))
        self.row("7", "deliver", None, started, "gate PASS · delivered")

    # ---- mode B -------------------------------------------------------------
    async def w_goals_prep(self):
        i = self.state["inputs"]
        started = time.strftime("%H:%M")
        rel_data = os.path.join(self.rel, "data")
        rel_goals = os.path.join(self.rel, "goals")
        os.makedirs(os.path.join(REPO, rel_data), exist_ok=True)
        os.makedirs(os.path.join(REPO, rel_goals), exist_ok=True)
        tp = os.path.join(rel_data, "tagging_plan.json")
        if not os.path.isfile(os.path.join(REPO, tp)):
            shutil.copy2(i["tagging_plan"], os.path.join(REPO, tp))
        inv, ana = os.path.join(rel_data, "inventory.json"), os.path.join(rel_data, "analysis.json")
        steps = [self.py("parse_tagging_plan.py", tp, "-o", inv),
                 self.py("analyze_tagging_plan.py", inv, "--vertical", i["vertical"], "-o", ana)]
        for argv in steps:
            code, out = await self.sh(argv, "goals prep")
            if code != 0:
                raise Stop(f"{os.path.basename(argv[1])} failed:\n{out[-1500:]}")
        if self.brand_task is not None:
            await self.brand_task
        brand_src = os.path.join(self.work, "brand.json")
        brand_dst = os.path.join(self.work, "goals", "brand.json")
        if os.path.isfile(brand_src) and not os.path.isfile(brand_dst):
            shutil.copy2(brand_src, brand_dst)
        goals = os.path.join(rel_goals, "goals.json")
        for argv in (self.py("goal_candidates.py", inv, ana,
                             os.path.join(rel_goals, "brand.json"),
                             "--vertical", i["vertical"], "-o", goals),
                     self.py("goals_charts.py", goals)):
            code, out = await self.sh(argv, "goals prep")
            if code != 0:
                raise Stop(f"{os.path.basename(argv[1])} failed:\n{out[-1500:]}")
        g = json.load(open(os.path.join(REPO, goals), encoding="utf-8"))
        if not (g.get("context") or {}).get("brand_sources"):
            raise Stop("goals.json carries no context.brand_sources: brand.json was not read")
        builder = os.path.join(self.work, "goals", "build_report.py")
        if not os.path.isfile(builder):
            shutil.copy2(os.path.join(HERE, "build_goals_template.py"), builder)
        self.freeze(["goals/goals.json", "goals/brand.json"])
        self.row("1-2", "tagging plan → goals.json + charts", None, started)

    async def w_goals_prose(self):
        started = time.strftime("%H:%M")
        sess = await self.runner.session("frontier", "goals")
        try:
            before = snapshot(self.work)
            reply = await sess.send(render_prompt("goals", client=self.a.client))
            last = None
            for attempt in range(CHECK_RETRIES + 1):
                code, out = await self.sh([sys.executable, os.path.join(
                    self.rel, "goals", "build_report.py")], "goals build")
                if code == 0:
                    break
                fails = self.gate_failures(out) or [out.strip()[-1500:]]
                if fails == last or attempt == CHECK_RETRIES:
                    raise Stop("goals build fails the gate:\n" + "\n".join(fails))
                last = fails
                reply = await sess.send("The build failed the gate. Fix only these:\n"
                                        + "\n".join(fails))
        finally:
            await sess.close()
        # enforce_scope skips goals/ (it holds renders); the frozen hashes guard the inputs
        self.check_frozen("goals prose")
        del before, reply
        self.row("3", "goals prose", "frontier", started, usage=["goals"])

    # ---- driver -------------------------------------------------------------
    def roles_needed(self, waves):
        roles = set()
        for w in waves:
            roles |= {"brand": {"brand"}, "analysis": {"frontier"}, "assets": {"frontier"},
                      "pilots": {"section", "frontier"}, "factual": {"section", "appendix"},
                      "consultative": {"frontier"}, "build": {"gate_fix"},
                      "coherence": {"frontier"}, "goals_prose": {"frontier"}}.get(w, set())
        return roles

    def plan(self):
        order = WAVES[self.state["inputs"]["mode"]]
        if self.a.from_wave:
            if self.a.from_wave not in order:
                raise Stop(f"--from {self.a.from_wave}: not a wave of this mode "
                           f"({', '.join(order)})")
            order = order[order.index(self.a.from_wave):]
            self.state["done"] = [w for w in self.state["done"] if w not in order]
            # A wave that will run again re-freezes its files; until then they are not
            # frozen, or rewriting them is taken for tampering and the old copy restored.
            for wave, names in FROZEN_BY_WAVE.items():
                if wave in order:
                    for n in names:
                        self.state["hashes"].pop(n, None)
        else:
            order = [w for w in order if w not in self.state["done"]]
        if self.a.stop_after:
            if self.a.stop_after not in order:
                raise Stop(f"--stop-after {self.a.stop_after}: not in the waves left "
                           f"({', '.join(order)})")
            order = order[:order.index(self.a.stop_after) + 1]
        return order

    async def run(self):
        order = self.plan()
        self.log(f"waves: {' → '.join(order) or '(nothing left)'}")
        qs = self.questions()
        self.log(f"mode: {'focused — ' + str(len(qs)) + ' question(s)' if qs else 'global'}")
        for q in qs:
            self.log(f"  {q['id']}: {q['text']}")
        if self.a.dry_run:
            for w in order:
                self.log(f"  {w:<13} {WAVE_DESC.get(w, '')}")
            self.log("models:")
            for role in sorted(self.roles_needed(order)):
                self.log(f"  {role:<13} {self.models[role]}"
                         f"  (.cursor/agents/{ROLE_AGENT[role]}.md)")
            return 0
        ctx = self.state["inputs"].get("context")
        if ctx:
            os.makedirs(self.work, exist_ok=True)
            shutil.copy2(ctx, os.path.join(self.work, "client_context.md"))
        self.write_lock()
        await self.runner.start(self.roles_needed(order), self.models)
        try:
            for w in order:
                self.log(f"\n== wave {w} ==")
                if w == "brand" and ("collect" in order or "goals_prep" in order):
                    # Wave 0 gates nothing until the freeze: run it beside the collection.
                    self.brand_task = asyncio.ensure_future(self._bg("brand", self.w_brand))
                    continue
                await getattr(self, "w_" + w)()
                self.check_frozen(w)
                self.state["done"].append(w)
                self.save_state()
            if self.brand_task is not None:
                await self.brand_task
        finally:
            # A stop elsewhere must not close the client under the background brand agent:
            # let it finish, so its brand.json counts on resume instead of being lost.
            if self.brand_task is not None and not self.brand_task.done():
                self.log("  waiting for the background brand research before closing")
                try:
                    await self.brand_task
                except Exception as exc:  # noqa: BLE001 — the first stop is the one reported
                    self.log(f"  brand research did not finish: {exc}")
            for s in (self.analyst, self.wave5):
                if s is not None:
                    await s.close()
            await self.runner.close()
            self.remove_lock()
        return 0

    # ---- lock: tells the project hooks a scripted run owns this work dir ----
    def write_lock(self):
        os.makedirs(self.work, exist_ok=True)
        with open(os.path.join(self.work, LOCK), "w", encoding="utf-8") as fh:
            json.dump({"pid": os.getpid(), "started": time.strftime("%Y-%m-%d %H:%M:%S"),
                       "models": sorted(set(self.models.values()))}, fh)

    def remove_lock(self):
        try:
            os.remove(os.path.join(self.work, LOCK))
        except OSError:
            pass

    async def _bg(self, name, fn):
        await fn()
        self.state["done"].append(name)
        self.save_state()


# ---------------------------------------------------------------------------
# inputs
# ---------------------------------------------------------------------------
INPUT_KEYS = ("mode", "project", "start", "end", "lang", "bilingual", "orchestration_external",
              "source_pack", "tagging_plan", "pdf", "brand", "country", "vertical", "context")


def resolve_inputs(args, saved):
    """CLI over saved state; validated before anything runs. -> dict or SystemExit(2)."""
    inp = {}
    for k in INPUT_KEYS:
        v = getattr(args, k, None)
        inp[k] = v if v not in (None, False) else saved.get(k, v)
    inp["mode"] = inp["mode"] or "full"
    errs = []
    if not _SLUG.match(args.client or ""):
        errs.append("--client must be a lowercase slug (it names work/<client>/)")
    if inp["mode"] == "full":
        for k in ("project", "start", "end", "lang", "orchestration_external", "source_pack"):
            if not inp.get(k):
                errs.append(f"--{k.replace('_', '-')} is required")
        for k in ("start", "end"):
            if inp.get(k) and not _ISO.match(inp[k]):
                errs.append(f"--{k} must be YYYY-MM-DD")
        if inp.get("start") and inp.get("end") and _ISO.match(inp["start"]) \
                and _ISO.match(inp["end"]) and inp["start"] > inp["end"]:
            errs.append("--start is after --end")
    else:
        inp["lang"] = "en"
        inp["orchestration_external"] = inp.get("orchestration_external") or "unknown"
        for k in ("tagging_plan", "vertical"):
            if not inp.get(k):
                errs.append(f"--{k.replace('_', '-')} is required in goals mode")
        inp["start"] = inp.get("start") or "-"
        inp["end"] = inp.get("end") or "-"
    if inp.get("lang") and inp["lang"] not in ("en", "fr"):
        errs.append("--lang is en or fr")
    if inp.get("orchestration_external") and inp["orchestration_external"] not in (
            "yes", "no", "unknown"):
        errs.append("--orchestration-external is yes, no or unknown")
    if inp.get("source_pack") and inp["source_pack"] not in ("yes", "no"):
        errs.append("--source-pack is yes or no")
    for k in ("tagging_plan", "context"):
        if inp.get(k):
            inp[k] = os.path.abspath(inp[k])
            if not os.path.isfile(inp[k]):
                errs.append(f"--{k.replace('_', '-')} {inp[k]}: no such file")
    # Questions in the brief make the review a focused one; none keeps it global.
    inp["questions"] = (fb.parse(inp["context"])["questions"]
                        if inp.get("context") and os.path.isfile(inp["context"]) else [])
    if errs:
        raise SystemExit("input error:\n  " + "\n  ".join(errs))
    return inp


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=("full", "goals"))
    ap.add_argument("--client", help="slug naming work/<client>/")
    ap.add_argument("--project", help="MCP server name of the Airship project")
    ap.add_argument("--start")
    ap.add_argument("--end", help="last day, inclusive")
    ap.add_argument("--lang", choices=("en", "fr"))
    ap.add_argument("--bilingual", action="store_true")
    ap.add_argument("--orchestration-external", dest="orchestration_external",
                    choices=("yes", "no", "unknown"))
    ap.add_argument("--source-pack", dest="source_pack", choices=("yes", "no"))
    ap.add_argument("--tagging-plan", dest="tagging_plan")
    ap.add_argument("--vertical", help="benchmark vertical (required in goals mode)")
    ap.add_argument("--brand", help="brand / site for wave 0 (default: the client slug)")
    ap.add_argument("--country")
    ap.add_argument("--context", help="the account team's brief (text/markdown): the "
                    "questions the review must answer, context the API cannot show")
    ap.add_argument("--pdf", action="store_true")
    ap.add_argument("--from", dest="from_wave", help="resume from this wave")
    ap.add_argument("--stop-after", dest="stop_after")
    ap.add_argument("--unattended", action="store_true",
                    help="pass the two human checkpoints (logged as deviations)")
    ap.add_argument("--skip-coherence", action="store_true",
                    help="skip the coherence pass (logged as a deviation)")
    ap.add_argument("--keep-raw", action="store_true", help="keep data/ after delivery")
    ap.add_argument("--model", action="append", default=[], metavar="ROLE=SPEC",
                    help="override one role's model for this run, repeatable "
                         f"(roles: {', '.join(sorted(ROLE_AGENT))}); e.g. "
                         "--model 'section=<id>[effort=medium]'")
    ap.add_argument("--frontier-model", help="alias of --model frontier=SPEC")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check-sdk", action="store_true",
                    help="live check: models resolve and an SDK agent has web search")
    ap.add_argument("--selftest", action="store_true")
    return ap


def cli_overrides(args):
    """--model pairs, with --frontier-model folded in as frontier=SPEC."""
    out = parse_overrides(args.model)
    if args.frontier_model:
        out.setdefault("frontier", args.frontier_model)
    return out


async def check_sdk(overrides=None):
    """Live smoke test: every role's model resolves, and an agent can search the web.

    Web access is what wave 0 needs and the one capability the local runtime might not
    grant; better to learn it here than forty minutes into a collection.
    """
    runner = SdkRunner()
    await runner.start(set(ROLE_AGENT), resolve_models(overrides))
    for role, (mid, params) in sorted(runner.models.items()):
        print(f"  model ok  {role:<9} {mid} {params or ''}")
    # On the brand role: it is the one that needs the web, on the model it will run.
    sess = await runner.session("brand", "sdk-check")
    sess.instructions = ""   # a probe, not a brand study: no brand.json to write
    try:
        reply = await sess.send(
            "Ignore any other instructions for this turn. Use web search once to find the "
            "title of https://www.airship.com/ and reply with ONLY that title, or with "
            "exactly NO-WEB if you have no web search tool.")
    finally:
        await sess.close()
        await runner.close()
    web = bool(reply.strip()) and "NO-WEB" not in reply
    print(f"  web search: {'ok — ' + reply.strip()[:80] if web else 'NOT available'}")
    if not web:
        print("  → run wave 0 in the IDE (prompts/brand.md), then resume with --from collect")
    return 0 if web else 1


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.selftest:
        return selftest()
    if args.check_sdk:
        try:
            return asyncio.run(check_sdk(cli_overrides(args)))
        except Stop as exc:
            print(f"SDK check failed: {exc}", file=sys.stderr)
            return 3
    if not args.client:
        raise SystemExit("--client is required")
    review = Review(args, SdkRunner(), Shell())
    review.load_state()
    review.state["inputs"] = resolve_inputs(args, review.state.get("inputs") or {})
    try:
        review.setup_models(cli_overrides(args), record=not args.dry_run)
    except Stop as exc:
        raise SystemExit(f"input error:\n  {exc}")
    if not args.dry_run:
        review.save_state()
    try:
        return asyncio.run(review.run())
    except Stop as exc:
        review.save_state()
        print(f"\nSTOPPED: {exc}", file=sys.stderr)
        return 3


# ---------------------------------------------------------------------------
# selftest — the whole wave logic against fake agents and a fake shell
# ---------------------------------------------------------------------------
def selftest():
    import tempfile
    fails = []

    def ck(cond, label):
        if not cond:
            fails.append(label)

    # --- prompts render, and refuse a hole ---
    try:
        render_prompt("section", key="x")
        ck(False, "an unfilled placeholder must raise")
    except PromptError as exc:
        ck("client" in str(exc), "the error names the missing placeholder")
    for f in sorted(os.listdir(PROMPTS)):
        text = open(os.path.join(PROMPTS, f), encoding="utf-8").read()
        vals = {k: "v" for k in _PLACEHOLDER.findall(text)}
        ck("{{" not in render_prompt(f[:-3], **vals), f"{f} renders fully")

    # --- orchestration.md keeps its templates out of the prose ---
    orch = open(os.path.join(SKILL, "orchestration.md"), encoding="utf-8").read()
    sect = orch.split("## Prompt templates", 1)[-1].split("\n## ", 1)[0]
    ck("```" not in sect, "orchestration.md § Prompt templates holds no fenced template")

    # --- models come from the agent files, parse, and never downgrade the prose ---
    ck(parse_model("claude-opus-5[effort=high]") == ("claude-opus-5", {"effort": "high"}),
       "model spec with params parses")
    ck(parse_model("gpt-5.6-sol") == ("gpt-5.6-sol", {}), "bare model spec parses")
    for role in ROLE_AGENT:
        spec, _ = agent_definition(role)
        ck(bool(parse_model(spec)[0]), f"{role} has a model")
    ck(agent_definition("frontier")[0] == agent_definition("section")[0],
       "the frontier writer uses the section (prose) model")
    ck("composer" not in agent_definition("section")[0], "prose is not routed to a fast model")
    for doc in ("SKILL.md", "orchestration.md"):
        text = open(os.path.join(SKILL, doc), encoding="utf-8").read()
        stale = sorted({parse_model(agent_definition(r)[0])[0] for r in ROLE_AGENT
                        if parse_model(agent_definition(r)[0])[0] in text})
        ck(not stale, f"{doc} restates no model id — the agent files own them ({stale})")

    # --- --model overrides one role; the frontier keeps the section FRONTMATTER model ---
    ov = parse_overrides(["section=trial-model[effort=medium]"])
    ck(agent_definition("section", ov)[0] == "trial-model[effort=medium]",
       "--model section=… overrides the section writers")
    ck(agent_definition("frontier", ov)[0] == agent_definition("section")[0],
       "a section trial leaves the frontier writer on the frontmatter model")
    ck(resolve_models({"frontier": "x"})["frontier"] == "x", "--model frontier=… applies")
    try:
        resolve_models({"writer": "x"})
        ck(False, "an unknown role must be refused")
    except Stop as exc:
        ck("unknown role writer" in str(exc), "the unknown role is named")
    fake_models = {"m": types.SimpleNamespace(parameters=[types.SimpleNamespace(
        id="effort", values=[types.SimpleNamespace(value="low"),
                             types.SimpleNamespace(value="high")])])}
    ck(check_model("section", "m[effort=high]", fake_models) == ("m", {"effort": "high"}),
       "an offered parameter value passes")
    for bad, why in (("m[effort=turbo]", "not offered"), ("m[speed=1]", "no parameter"),
                     ("n", "not available")):
        try:
            check_model("section", bad, fake_models)
            ck(False, f"{bad} must be refused")
        except Stop as exc:
            ck(why in str(exc), f"{bad}: refused as '{why}' ({exc})")

    # --- the pools cover the canonical spine exactly once ---
    # Pilots are drawn FROM the pools (and skipped there at run time), so the pools
    # alone must partition the full-profile spine.
    pools = cs.FACTUAL_POOL + cs.APPENDIX_POOL + cs.WAVE5_ORDER
    body = [s["key"] for s in cs.CANONICAL_SECTIONS if s["key"] != "cover"]
    ck(sorted(pools) == sorted(body), "the wave pools partition the section spine")
    ck(set(cs.PILOT_FACTUAL) <= set(cs.FACTUAL_POOL)
       and cs.PILOT_CONSULTATIVE in cs.WAVE5_ORDER, "pilots are drawn from the pools")
    ck(cs.WAVE5_ORDER[-1] == "exec_summary", "exec_summary is written last")
    ck(cs.WAVE5_ORDER.index("recommendations") > cs.WAVE5_ORDER.index("benchmarks"),
       "recommendations after benchmarks")
    ck({"push_program", "email_program", "channels_exp", "cross_app"} <= set(cs.FACTUAL_POOL)
       and "client_categories" in cs.FACTUAL_POOL,
       "the descriptive programme sections are written in the parallel wave")
    ck({"playbook", "best_practices"} <= set(cs.WAVE5_ORDER),
       "playbook and best_practices grade one campaign list in one conversation")
    ck(not cs.reference_routing_problems(SKILL), "reference routing agrees with the index")
    import build_facts as bf
    spec_keys = {s["key"] for s in bf.KPI_SPECS}
    ck(spec_keys <= set(bf.KPI_DEFINITIONS),
       f"every KPI has a definition home (missing: {sorted(spec_keys - set(bf.KPI_DEFINITIONS))})")
    for kpi, homes in bf.KPI_DEFINITIONS.items():
        for stem, heading in homes:
            p = os.path.join(SKILL, "reference", stem + ".md")
            ok = os.path.isfile(p) and re.search(r"^## .*" + heading, open(
                p, encoding="utf-8").read(), re.M)
            ck(bool(ok), f"{kpi}: '{heading}' is a heading of reference/{stem}.md")

    # --- inputs are validated before anything runs ---
    ap = build_parser()
    try:
        resolve_inputs(ap.parse_args(["--client", "Bad Name", "--start", "2026-13"]), {})
        ck(False, "bad inputs must be refused")
    except SystemExit as exc:
        ck("slug" in str(exc) and "YYYY-MM-DD" in str(exc), "input errors are all listed")

    # --- a full run against fakes, in a throwaway work dir ---
    tmp = tempfile.mkdtemp()
    client = "selftest-" + os.path.basename(tmp).lower().replace("_", "-")
    work = os.path.join(REPO, "work", client)
    try:
        _selftest_run(ck, ap, client, work)
    finally:
        shutil.rmtree(work, ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"run_review selftest: {'ok' if not fails else 'FAILED'} ({len(fails)} failure(s))")
    for f in fails:
        print(f"  - {f}")
    return 1 if fails else 0


def _selftest_focused(ck, make, base, client):
    """A brief with questions: plan at pre-flight, depth in the prompts, answers before
    the summary, and a dropped answer stops the run."""
    fclient = client + "-focus"
    work = os.path.join(REPO, "work", fclient)
    ctx = os.path.join(REPO, "work", fclient + "-brief.md")
    shutil.rmtree(work, ignore_errors=True)
    with open(ctx, "w", encoding="utf-8") as fh:
        fh.write("## Questions\nQ1: Why do so few opted-in devices receive pushes?\n"
                 "Q2: Did the SDK release fix the iOS registrations?\n")

    def put(rel, content):
        p = os.path.join(work, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(content if isinstance(content, str) else json.dumps(content))

    brief = "\n".join(f"## {h}\n- x" for h in (
        "Key findings", "Conflicts settled", "Withheld metrics", "External orchestration",
        "House style", "Terminology lock"))
    depth = {s["key"]: "standard" for s in cs.CANONICAL_SECTIONS if s.get("gate_required")}
    depth.update(permission="lead", typology="condensed")
    plan = {"questions": [
        {"id": "Q1", "sections": ["permission"], "facts": ["app_optin"], "answerable": True},
        {"id": "Q2", "sections": [], "facts": [], "answerable": False,
         "reason": "no per-version registration series"}], "depth": depth}
    full = {"Q1": {"answer": "a.", "confidence": "medium", "facts": ["app_optin"],
                   "sections": ["permission"]},
            "Q2": {"answer": "b.", "confidence": "not_measurable", "reason": "r"}}
    answers = {"v": full}
    # The first plan leans on client_categories, which this run will not write.
    on_categories = json.loads(json.dumps(plan))
    on_categories["questions"][0]["sections"].append("client_categories")
    on_categories["depth"]["client_categories"] = "lead"
    fixes = []

    def agent(role, label, prompt, turn):
        if prompt.startswith("You are the analyst"):
            put("audit.json", {"a": 1})
            put("facts.json", {"kpis": [{"key": "app_optin"}]})
            put("analysis_brief.md", brief)
        elif prompt.startswith("The pre-flight failed"):
            fixes.append(prompt)
            put("focus_plan.json", on_categories if len(fixes) == 1 else plan)
        elif "Prepare everything the section writers" in prompt:
            keys = re.search(r"list:\n\s+(.+)\n", prompt).group(1).split(", ")
            put("section_slices.json", {k: {"audit_keys": ["a"], "chart_ids": ["c1"]}
                                        for k in keys})
            for f in ("make_charts.py", "make_creatives.py", "build_report.py"):
                put(f, "")
        elif role == "brand":
            put("brand.json", {"ok": True})
        m = re.search(r"sections/(\w+)\.py", prompt)
        if m and ("Write ONE section" in prompt or "consultative" in prompt
                  or "data appendix" in prompt):
            key = m.group(1)
            put(f"sections/{key}.py", "def render(ctx, lang): return ''")
            if key == fp.ANSWERS_KEY:
                put("answers.json", answers["v"])
            elif role != "appendix":
                put(f"verdicts/{key}.json", {"key": key, "verdict": "v.",
                                             "directions": {"pressure": "hold"}})
        if "last reader before the client" in prompt:
            return "no change\nSUSPECT: none"
        return "done"

    def shell(argv):
        name = os.path.basename(argv[1]) if len(argv) > 1 else ""
        if name == "make_charts.py":
            put("specs.json", {"c1": {}})
        if name == "make_creatives.py":
            put("creatives.json", [])
        if name == "focus_plan.py":
            probs = fp.run_check(os.path.join(REPO, argv[3]),
                                 answers=argv[2] == "--check-answers")
            return (1, "FAIL\n" + "\n".join(probs)) if probs else (0, "ok")
        if name == "campaign_categories.py" and argv[2] == "prepare":
            return 0, ("available=False reason=no decoded push body scheme=none terms=0")
        return 0, "ok"

    argv = ["--client", fclient] + base[2:] + ["--context", ctx]
    try:
        r, runner, fshell = make(argv, script=agent, sh=shell)
        ck(r.questions() and [q["id"] for q in r.questions()] == ["Q1", "Q2"],
           "the brief's questions make the review focused")
        try:
            asyncio.run(r.run())
        except Stop as exc:
            ck(False, f"a focused run stopped: {exc}")
        calls = runner.calls
        ck(any(c[3].startswith("The pre-flight failed") and "focus_plan" in c[3]
               for c in calls), "no focus_plan.json fails the pre-flight, back to the analyst")
        ck(any("FOCUSED REVIEW" in c[3] and "Q2: Did the SDK" in c[3]
               for c in calls if c[1] == "analysis"), "the analyst is given the questions")
        ck("focus_plan.json" in r.state["hashes"], "focus_plan.json is frozen")

        def prompt_of(key):
            return next((c[3] for c in calls if f"sections/{key}.py" in c[3]
                         and ("Write ONE section" in c[3] or "This turn:" in c[3])), "")
        ck("DEPTH: lead" in prompt_of("permission") and "Q1" in prompt_of("permission"),
           "the lead section is told which question it answers")
        ck("DEPTH: condensed" in prompt_of("typology"), "an off-focus section is condensed")
        ck("DEPTH: standard" in prompt_of("engagement"), "the others stay standard")
        w5 = [re.search(r"This turn: `(\w+)`", c[3]).group(1) for c in calls
              if c[1] == "wave5" and "This turn:" in c[3]]
        ck(w5[-2:] == [fp.ANSWERS_KEY, "exec_summary"],
           f"the answers come just before the executive summary ({w5[-3:]})")
        ck("open on the answers" in prompt_of("exec_summary"),
           "the executive summary opens on the answers")
        ck(any("also check the answers" in c[3] for c in calls if c[1] == "coherence"),
           "the coherence pass checks the answers")
        ck("deliver" in r.state["done"], "a focused run reaches delivery")
        run_md = open(os.path.join(work, "run.md"), encoding="utf-8").read()
        ck("| 2a | client categories |" in run_md and "skipped: no decoded push body" in run_md,
           "unreadable categories: the 2a row says the step was skipped, and why")
        ck("## Client categories (wave 2a)" in run_md and "available=False" in run_md,
           "...and the prepare verdict is kept in run.md")
        ck(not any(c[1] == "categories" for c in calls), "no category reader is started")
        ck(not any("sections/client_categories.py" in c[3] for c in calls),
           "client_categories is not written")
        ck(len(fixes) >= 2 and "'client_categories' will not be written" in fixes[1],
           "a focus plan resting on client_categories is refused at the pre-flight")

        answers["v"] = {"Q1": full["Q1"]}
        r2, _, _ = make(["--client", fclient, "--from", "consultative", "--unattended"],
                        script=agent, sh=shell)
        try:
            asyncio.run(r2.run())
            ck(False, "a dropped answer must stop the run")
        except Stop as exc:
            ck("Q2: no answer" in str(exc), f"a dropped answer stops the run ({exc})")
    finally:
        shutil.rmtree(work, ignore_errors=True)
        os.remove(ctx)


def _selftest_run(ck, ap, client, work):
    os.makedirs(work)

    def put(rel, content):
        p = os.path.join(work, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(content if isinstance(content, str) else json.dumps(content))

    brief = "\n".join(f"## {h}\n- x" for h in (
        "Key findings", "Conflicts settled", "Withheld metrics", "External orchestration",
        "House style", "Terminology lock"))
    tamper = {"on": None}
    lock_seen = []

    def agent(role, label, prompt, turn):
        if prompt.startswith("You are the analyst"):
            lock = os.path.join(work, LOCK)
            if os.path.isfile(lock):
                lock_seen.append(json.load(open(lock)))
            put("audit.json", {"a": 1})
            put("facts.json", {"kpis": []})
            put("analysis_brief.md", brief)
        elif prompt.startswith("You read the client's own campaign categories"):
            put("category_hypotheses.json", {"hypotheses": []})
            put("audit.json", {"early": 1})     # out of scope: reverted
        elif "Prepare everything the section writers" in prompt:
            keys = re.search(r"list:\n\s+(.+)\n", prompt).group(1).split(", ")
            put("section_slices.json", {k: {"audit_keys": ["a"], "chart_ids": ["c1"]}
                                        for k in keys})
            put("make_charts.py", "")
            put("make_creatives.py", "")
            put("build_report.py", "")
        elif role == "brand":
            put("brand.json", {"ok": True})
        m = re.search(r"sections/(\w+)\.py", prompt)
        if m and ("Write ONE section" in prompt or "consultative" in prompt
                  or "data appendix" in prompt):
            key = m.group(1)
            put(f"sections/{key}.py", "def render(ctx, lang): return ''")
            if role != "appendix":
                d = "down" if key == "volume_pressure" else "hold"
                put(f"verdicts/{key}.json", {"key": key, "verdict": "v.",
                                             "directions": {"pressure": d}})
            if tamper["on"] == key:
                put("facts.json", {"kpis": ["tampered"]})
        if "Update work/" in prompt and "analysis_brief.md" in prompt:
            put("analysis_brief.md", brief + "\n- pilot item")
            put("analyze.py", "# rewritten")     # out of scope, not frozen: reverted
            return ("added one item\n"
                    "PILOT_FIX: permission · 30.44-day month · use the calendar month\n"
                    "PILOT_FIX: engagement · not a pilot · ignored")
        if "last reader before the client" in prompt:
            return "no change\nSUSPECT: none"
        return "done"

    def shell(argv):
        name = os.path.basename(argv[1]) if len(argv) > 1 else ""
        if name == "make_charts.py":
            put("specs.json", {"c1": {}})
        if name == "make_creatives.py":
            put("creatives.json", [])
        if name == "campaign_categories.py" and argv[2] == "prepare":
            return 0, "available=True reason=None scheme=facets terms=3"
        if name == "campaign_categories.py" and argv[2] == "validate":
            ok = os.path.isfile(os.path.join(work, "category_hypotheses.json"))
            return (0, "OK") if ok else (1, "FAIL: no category_hypotheses.json")
        return 0, "ok"

    base = ["--client", client, "--project", "P", "--start", "2026-08-01", "--end",
            "2026-08-30", "--lang", "en", "--orchestration-external", "unknown",
            "--source-pack", "no", "--unattended"]

    def make(argv, script=agent, sh=shell):
        a = ap.parse_args(argv)
        runner, fshell = FakeRunner(script), FakeShell(sh)
        r = Review(a, runner, fshell, log=lambda *_: None)
        r.load_state()
        r.state["inputs"] = resolve_inputs(a, r.state.get("inputs") or {})
        r.setup_models(cli_overrides(a))
        return r, runner, fshell

    trial = "trial-model[effort=medium]"
    r, runner, fshell = make(base + ["--model", f"section={trial}"])
    try:
        asyncio.run(r.run())
    except Stop as exc:
        ck(False, f"a clean run (pressure down vs hold is compatible) stopped: {exc}")
    ck(r.state["done"] and r.state["done"][-1] in ("deliver", "brand"),
       f"a clean run reaches delivery (done: {r.state['done']})")
    ck("deliver" in r.state["done"], "deliver ran")
    ck(lock_seen and lock_seen[0]["pid"] == os.getpid() and trial in lock_seen[0]["models"],
       "the run holds .run_review.lock (pid + models) for the hooks")
    ck(not os.path.exists(os.path.join(work, LOCK)), "...and removes it when it ends")
    ck(2 <= runner.peak <= MAX_PARALLEL, f"parallel, but never more than {MAX_PARALLEL} "
       f"agents at once (peak {runner.peak})")
    ck(not os.path.exists(os.path.join(work, "analyze.py")),
       "the brief amendment's out-of-scope file was reverted")
    ck(any("analyze.py" in d for d in r.state["deviations"]), "...and logged as a deviation")
    ck("pilot item" in open(os.path.join(work, "analysis_brief.md")).read(),
       "the amended brief is kept and re-frozen")
    labels = [c[1] for c in runner.calls]
    fix = [c for c in runner.calls if c[1] == "pilot-fix-permission"]
    ck(fix and fix[0][0] == "section" and "30.44-day month" in fix[0][3]
       and "failed a check" in fix[0][3],
       "a PILOT_FIX line sends the error back to the pilot's writer")
    ck(labels.index("pilot-fix-permission") < labels.index("engagement"),
       "...before the factual wave reads the pilots")
    ck("## Pilot fixes" in open(os.path.join(work, "run.md")).read(),
       "the pilot fix is logged in run.md")
    ck(any("'engagement', not a pilot" in d for d in r.state["deviations"]),
       "a fix aimed at a non-pilot section is ignored, as a deviation")
    ck(labels.count("categories") == 1 and labels.index("categories") < labels.index("analysis"),
       "the category reader runs once, before the analyst")
    ck(next(c[0] for c in runner.calls if c[1] == "categories") == "frontier",
       "the category reader is on the frontier model")
    ck(any("categories reader edited audit.json" in d for d in r.state["deviations"]),
       "the category reader is scoped to category_hypotheses.json")
    ck("| 2a | client categories |" in open(os.path.join(work, "run.md")).read(),
       "the category step gets its run.md row")
    pair = "data_foundation+detected"
    ck(pair not in labels, "no tagging plan → data_foundation is not written")
    ck(sum(1 for c in runner.calls if c[1] == "detected") == 1, "detected written alone")
    w5 = [re.search(r"This turn: `(\w+)`", c[3]).group(1) for c in runner.calls
          if c[1] == "wave5" and "This turn:" in c[3]]
    ck(w5 and w5[-1] == "exec_summary", f"wave 5 ends on exec_summary ({w5[-3:]})")
    ck(len({c[1] for c in runner.calls if c[1] == "wave5"}) == 1,
       "wave 5 is one conversation")
    run_md = open(os.path.join(work, "run.md")).read()
    ck("## Orchestrator log" in run_md and "| FREEZE |" in run_md, "run.md gets its rows")
    ck(os.path.isfile(os.path.join(work, "verdicts.json")), "verdicts.json is written")
    ck(any("checkpoint" in d for d in r.state["deviations"]),
       "unattended checkpoints are logged as deviations")

    # --- the models of the run are recorded; usage is metered per session ---
    ck(r.state["models"]["section"] == trial
       and r.state["models"]["frontier"] == agent_definition("frontier")[0],
       "run_state.json records the resolved models")
    ck(f"## Orchestrator models" in run_md and f"- section: `{trial}`" in run_md,
       "run.md carries the models of the run")
    ck(run_md.count("## Orchestrator models") == 1, "the models block is written once")
    ck(re.search(r"\| engagement \| " + re.escape(trial) + r" \|.*\| 0\.1k \|", run_md),
       "a section row names the trial model and its tokens")
    usage = r.state.get("usage") or {}
    ck(usage.get("wave5", {}).get("turns", 0) >= 2
       and usage["wave5"]["total"] == 100 * usage["wave5"]["turns"]
       and usage["wave5"]["role"] == "frontier", "usage accumulates per session and turn")
    ck(usage.get("engagement", {}).get("model") == trial, "usage carries the model")

    # --- a failed collection waits for the background brand agent, and keeps its work ---
    def failing_collect(argv):
        if os.path.basename(argv[1]) == "collect.py":
            return 1, "probe FAILED"
        return shell(argv)
    tmp_client = client + "-bg"
    tmp_work = os.path.join(REPO, "work", tmp_client)
    try:
        rb, _, _ = make(["--client", tmp_client] + base[2:], sh=failing_collect)
        try:
            asyncio.run(rb.run())
            ck(False, "a failed collection must stop")
        except Stop:
            pass
        ck("brand" in rb.state["done"], "the background brand research finished despite the stop")
    finally:
        shutil.rmtree(tmp_work, ignore_errors=True)

    # --- a global run: no answers section, every writer at standard depth ---
    ck("focus_answers" not in w5, "a global review writes no answers section")
    ck(all("DEPTH: standard" in c[3] for c in runner.calls if "Write ONE section" in c[3]),
       "a global review gives every writer the standard depth")
    ck(any("GLOBAL REVIEW" in c[3] for c in runner.calls if c[1] == "analysis"),
       "the analyst is told the review is global")

    _selftest_focused(ck, make, base, client)

    # --- resume: nothing left, then --from build re-runs only the tail ---
    r2, runner2, shell2 = make(["--client", client, "--unattended"])
    ck(r2.plan() == [], "a finished run has nothing left")
    ck(r2.models["section"] == trial, "a resumed run keeps the models it started with")
    ck(not any("changed on resume" in d for d in r2.state["deviations"]),
       "resuming without --model is no deviation")
    r9, _, _ = make(["--client", client, "--from", "analysis", "--unattended"])
    r9.plan()
    ck(not {"audit.json", "facts.json", "specs.json"} & set(r9.state["hashes"]),
       "--from a wave before the freeze thaws what that wave will freeze again")
    r9b, _, _ = make(["--client", client, "--from", "factual", "--unattended"])
    r9b.plan()
    ck({"audit.json", "specs.json"} <= set(r9b.state["hashes"]),
       "--from a wave after the freeze keeps it")
    r3, runner3, shell3 = make(["--client", client, "--from", "build", "--unattended",
                                "--model", "gate_fix=other-model"])
    ck(any("gate_fix changed on resume" in d for d in r3.state["deviations"]),
       "a new --model on resume is logged as a deviation")
    ck(r3.models["section"] == trial and r3.models["gate_fix"] == "other-model",
       "...and applies on top of the saved models")
    asyncio.run(r3.run())
    ran = [os.path.basename(c[1]) for c in shell3.calls if len(c) > 1]
    ck(ran and "collect.py" not in ran and "build_report.py" in ran,
       "--from build skips collection and rebuilds")

    # --- the gate-fix loop is bounded and a repeat failure stops it ---
    def failing_gate(argv):
        if os.path.basename(argv[1]) == "build_report.py":
            return 1, "  [✓] sections present\n  [✗] missing grid class\n  => FAIL"
        return shell(argv)
    r4, runner4, _ = make(["--client", client, "--from", "build", "--stop-after", "build",
                           "--unattended"], sh=failing_gate)
    try:
        asyncio.run(r4.run())
        ck(False, "a gate that never passes must stop")
    except Stop as exc:
        ck("no progress" in str(exc), f"same gate failure twice stops ({exc})")
    ck(sum(1 for c in runner4.calls if c[0] == "gate_fix") == 1,
       "one fix round, then the repeat is caught")

    # --- a ✗ far above the tail still reaches the log and run.md; the builder side is
    # out of the gate-fix agent's reach ---
    def long_gate(argv):
        if os.path.basename(argv[1]) == "build_report.py":
            return 1, ("  [✗] missing grid class\n"
                       + "\n".join(f"  [✓] check {i}" for i in range(40)) + "\n  => FAIL")
        return shell(argv)

    def shared_editor(role, label, prompt, turn):
        if role == "gate_fix":
            put("sections/_shared.py", "# patched by the gate-fix agent")
        return agent(role, label, prompt, turn)
    logged = []
    r10, _, _ = make(["--client", client, "--from", "build", "--stop-after", "build",
                      "--unattended"], script=shared_editor, sh=long_gate)
    r10.log = logged.append
    try:
        asyncio.run(r10.run())
        ck(False, "a gate that never passes must stop")
    except Stop:
        pass
    ck(any("[✗] missing grid class" in l for l in logged),
       "a ✗ at the head of a 40-line output is logged")
    ck("## Gate failures" in open(os.path.join(work, "run.md")).read()
       and "missing grid class" in open(os.path.join(work, "run.md")).read(),
       "the gate failures are written to run.md")
    ck(not os.path.exists(os.path.join(work, "sections", "_shared.py"))
       and any("gate-fix edited sections/_shared.py" in d for d in r10.state["deviations"]),
       "the gate-fix agent cannot edit sections/_shared.py")

    # --- a SUSPECT line blocks delivery ---
    def suspicious(role, label, prompt, turn):
        if "last reader before the client" in prompt:
            return "SUSPECT: engagement · 3.4% · off by ten"
        return agent(role, label, prompt, turn)
    r5, _, _ = make(["--client", client, "--from", "coherence", "--unattended"],
                    script=suspicious)
    try:
        asyncio.run(r5.run())
        ck(False, "a SUSPECT line must block delivery")
    except Stop as exc:
        ck("suspect" in str(exc).lower(), "SUSPECT lines stop before deliver")
    ck("deliver" not in r5.state["done"], "deliver did not run")

    # --- a writer that edits a frozen file stops the run, and the file is restored ---
    tamper["on"] = "engagement"
    r6, _, _ = make(["--client", client, "--from", "factual", "--stop-after", "factual",
                     "--unattended"])
    try:
        asyncio.run(r6.run())
        ck(False, "editing facts.json mid-wave must stop")
    except Stop as exc:
        ck("frozen facts.json" in str(exc), f"frozen edit stops the run ({exc})")
    ck(json.load(open(os.path.join(work, "facts.json"))) == {"kpis": []},
       "facts.json is restored")
    tamper["on"] = None

    # --- opposite directions stop the run before wave 5 ---
    put("verdicts/permission.json", {"key": "permission", "verdict": "v.",
                                     "directions": {"pressure": "up"}})
    r7, _, _ = make(["--client", client, "--from", "consultative", "--unattended"])
    try:
        r7.ledger("before wave 5")
        ck(False, "up vs down must stop")
    except Stop as exc:
        ck("pressure" in str(exc), "the contradiction is named")

    # --- mode B: deterministic prep, one prose agent, the goals gate ---
    shutil.rmtree(work)
    plan = os.path.join(os.path.dirname(work), client + "-plan.json")
    with open(plan, "w") as fh:
        fh.write("{}")

    def goals_shell(argv):
        name = os.path.basename(argv[1]) if len(argv) > 1 else ""
        if name == "goal_candidates.py":
            put("goals/goals.json", {"context": {"brand_sources": ["https://x"]}})
        return 0, "ok"
    try:
        r8, runner8, shell8 = make(["--mode", "goals", "--client", client, "--tagging-plan",
                                    plan, "--vertical", "Retail", "--unattended"],
                                   sh=goals_shell)
        asyncio.run(r8.run())
        ran = [os.path.basename(c[1]) for c in shell8.calls if len(c) > 1]
        ck("collect.py" not in ran, "goals mode calls no API")
        ck(ran.index("goal_candidates.py") < ran.index("goals_charts.py"),
           "candidates before charts")
        ck([c[0] for c in runner8.calls] == ["brand", "frontier"],
           f"goals mode: one brand agent, one prose agent ({[c[0] for c in runner8.calls]})")
        ck(r8.state["done"][-1] in ("deliver", "brand") and "deliver" in r8.state["done"],
           "goals mode reaches its gate")
        cand = next(c for c in shell8.calls if c[1].endswith("goal_candidates.py"))
        ck(cand[4].endswith("brand.json"), "goal_candidates gets the PATH to brand.json")
    except Stop as exc:
        ck(False, f"goals mode stopped: {exc}")
    finally:
        os.remove(plan)


if __name__ == "__main__":
    sys.exit(main())
