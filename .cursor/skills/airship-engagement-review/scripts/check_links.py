#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Every relative markdown link in the skill resolves, anchor included.

    python scripts/check_links.py              # the skill + .cursor/agents
    python scripts/check_links.py --selftest

The skill is read by progressive disclosure: a short SKILL.md routes to files that are
opened only when they apply. That only works while the routes are live. A moved heading or
a renamed file turns a link into a dead end, and an agent that hits one either stops or
reads everything — the failure progressive disclosure exists to prevent. Links are checked
against GitHub's anchor slugs, which is what Cursor renders too.

External links (http, mailto) are not fetched. Links inside fenced code are ignored.
"""

import argparse
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
AGENTS = os.path.normpath(os.path.join(SKILL, "..", "..", "agents"))

LINK = re.compile(r"(?<!\!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def slug(heading):
    """GitHub's anchor for a heading."""
    h = heading.strip().lower()
    h = re.sub(r"`", "", h)
    h = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", h)
    out = []
    for ch in h:
        if ch in " -_" or ch.isalnum():
            out.append(ch)
        elif unicodedata.category(ch).startswith("M"):
            out.append(ch)
    return "".join(out).replace(" ", "-")


def strip_fences(text):
    kept, fence = [], False
    for ln in text.split("\n"):
        if ln.lstrip().startswith("```"):
            fence = not fence
            kept.append("")
            continue
        kept.append("" if fence else ln)
    return kept


def anchors(path, _cache={}):
    if path not in _cache:
        seen, found = {}, set()
        with open(path, encoding="utf-8") as fh:
            for ln in strip_fences(fh.read()):
                m = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", ln)
                if not m:
                    continue
                s = slug(m.group(2))
                n = seen.get(s, 0)
                found.add(s if n == 0 else f"{s}-{n}")
                seen[s] = n + 1
        _cache[path] = found
    return _cache[path]


def check_file(path):
    """-> list of (line, target, reason)."""
    bad = []
    with open(path, encoding="utf-8") as fh:
        lines = strip_fences(fh.read())
    for i, ln in enumerate(lines, 1):
        for m in LINK.finditer(re.sub(r"`[^`]*`", "", ln)):
            target = m.group(1)
            if re.match(r"^[a-z]+:", target) or target.startswith("<"):
                continue
            file_part, _, frag = target.partition("#")
            dest = path if not file_part else os.path.normpath(
                os.path.join(os.path.dirname(path), file_part))
            if not os.path.exists(dest):
                bad.append((i, target, "missing file"))
                continue
            if frag and dest.endswith(".md") and frag not in anchors(dest):
                bad.append((i, target, "missing anchor"))
    return bad


def md_files(roots):
    for root in roots:
        for dp, dns, fns in os.walk(root):
            dns[:] = [d for d in dns if d not in ("__pycache__", "vendor")]
            for fn in sorted(fns):
                if fn.endswith(".md"):
                    yield os.path.join(dp, fn)


def run(roots):
    problems = []
    for p in md_files(roots):
        for line, target, why in check_file(p):
            problems.append(f"{os.path.relpath(p, SKILL)}:{line}: {why}: {target}")
    return problems


def selftest():
    import tempfile
    assert slug("Scope of measurement — snapshot (whole base) vs period") == \
        "scope-of-measurement--snapshot-whole-base-vs-period"
    assert slug("TRAP: the sends endpoint is not push-only") == \
        "trap-the-sends-endpoint-is-not-push-only"
    assert slug("`rich` is NOT a subset of `alerting` — reach is an interval") == \
        "rich-is-not-a-subset-of-alerting--reach-is-an-interval"
    assert slug("Mode B — Goals review (light)") == "mode-b--goals-review-light"
    with tempfile.TemporaryDirectory() as d:
        a, b = os.path.join(d, "a.md"), os.path.join(d, "b.md")
        with open(b, "w") as fh:
            fh.write("# Top\n\n## Same\n\n## Same\n\n```\n## Fenced\n```\n")
        with open(a, "w") as fh:
            fh.write("[ok](b.md) [ok](b.md#same-1) [x](b.md#fenced) [y](c.md) "
                     "`[code](nope.md)` [web](https://x.y/z.md) [self](#local)\n\n## Local\n")
        got = [(t, why) for _, t, why in check_file(a)]
        assert got == [("b.md#fenced", "missing anchor"), ("c.md", "missing file")], got
    print("check_links selftest: ok")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    problems = run([SKILL, AGENTS])
    for p in problems:
        print(p)
    print(f"{len(problems)} dead link(s)" if problems else "links: ok")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
