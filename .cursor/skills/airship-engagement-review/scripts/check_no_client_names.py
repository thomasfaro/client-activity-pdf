#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fail if a real account name appears in a tracked file.

The repository is meant to be installable by anyone without revealing anything about
the portfolio: benchmarks and general practice, no clients. That held at the top of
the tree twice before and drifted back both times, because naming the account is the
natural way to write a comment while tuning the skill -- "this account's silent share
moves 8.2% to 22.2%" is a genuinely useful note, and the version that names the
account is the one you write first.

This docstring is itself a data point: its first draft carried an account name in
that very example, and the check caught it on the commit that introduced the check.

So the check is shipped and **the list of names is not.** It reads the accounts out of
`~/.cursor/mcp.json`, where every project this machine can reach is declared as a server
named `<project> <ENV>` — the same list the skill is pointed at, outside the repository by
construction and never a file anyone could commit by accident. `probe_sweep.json` is read
too, for a machine that has swept accounts it has since removed from the MCP config.

    python .cursor/skills/airship-engagement-review/scripts/check_no_client_names.py
    python .cursor/skills/airship-engagement-review/scripts/check_no_client_names.py --selftest

Exit status is 1 on a finding, so it works as a pre-commit hook or a CI step.

The first version read only `probe_sweep.json` and searched bare names of four characters
or more. It passed a tree that named five accounts, because the swept file held 13 of the
31 projects and because two-character names were skipped outright. Both holes are closed
below, and they are the reason the name list comes from the MCP config now.

Two further holes were closed after the same leak class recurred a fourth time -- three
times in `git log`, once in a diff whose own self-test docstring records having made the
mistake before. Four occurrences is a mechanism problem, not a discipline problem:

  * **short initials inside an example value.** Two-character names cannot be searched in
    prose, and the qualifier list (`PROD`, `user-`, `+_`) does not include the one place
    they actually appear: a quoted sample value. `"name=XY Rennes|contact=..."` passed.
    Such names are now also searched inside lines that LOOK like a personal-data sample.
  * **real portfolio figures.** A committed example carrying a seven-digit send volume is
    portfolio data with no name attached, so no name list can see it. Non-round long
    integers in comments and docstrings are now reported, asking for a rounded or
    fictional magnitude. Dates, phone numbers, colours and round illustrative
    magnitudes are not figures and are left alone.

One hole stays open, and no list can close it: an abbreviation nobody registered. A
three-letter initialism for a long official name is not derivable from that name, so it
is not searched for. Reviewing a diff remains the only thing that catches it.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
import tokenize

HERE = os.path.dirname(os.path.abspath(__file__))
MCP = os.path.expanduser("~/.cursor/mcp.json")
SWEEP = os.path.join(HERE, "probe_sweep.json")
EXPECTED = os.path.join(HERE, "probe_sweep_expected.json")

# A bare name this short cannot be searched for on its own: two characters match inside
# base64 by coincidence. Such names are searched only where something around them says
# "account" -- see `_pattern`. Nothing is skipped outright.
MIN_LEN = 4

# One account is called after an ordinary English word, and searching for it bare put a
# finding in 45 of 92 tracked files. The system word list separates a brand from a word
# well enough for this: the distinctive names are absent from it, the ordinary ones are
# present. A machine without it falls back to the handful met so far.
WORDS = "/usr/share/dict/words"
_FALLBACK_WORDS = {"which", "orange", "olympic", "committee", "training", "anchor"}

# An Airship project server is named "<project> <ENV>". That shape is what separates a
# client from the other MCP servers on the machine, and it also gives a second, longer
# string to search for: a two-letter name cannot be searched, "<name> PROD" can.
_ENV = r"PROD|DEV|Test|Staging"
_ENV_SUFFIX = re.compile(r"\s+(" + _ENV + r")$", re.I)


def _mcp_servers(path=MCP):
    """Every MCP server name declared for this machine."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    servers = data.get("mcpServers") or data.get("servers") or {}
    return [str(k) for k in servers] if isinstance(servers, dict) else []


def account_names(mcp=MCP, sweep_paths=(SWEEP, EXPECTED)):
    """Account names, full and base, from whichever local source is present.

    Full form and base form are both returned, because both leak: the full one into an MCP
    setup example, the base one into a comment. Servers with no environment suffix are not
    accounts -- a docs server or a scratch project -- and are left out.
    """
    full = {s for s in _mcp_servers(mcp) if _ENV_SUFFIX.search(s)}
    for path in sweep_paths:
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        # the sweep output: {"window": [...], "rows": [{"project": ...}, ...]}
        for row in data.get("rows") or []:
            if isinstance(row, dict) and row.get("project"):
                full.add(str(row["project"]))
        # the expectation fixture: {"<project>": "<shape>", "_note": ...}
        for key in data:
            if key not in ("window", "rows") and not key.startswith("_"):
                full.add(str(key))
    full = {n.strip() for n in full if n.strip()}
    base = {_ENV_SUFFIX.sub("", n).strip() for n in full}
    # Nobody writes the registered name in a comment. A multi-word account is referred to
    # by its first word, so that word counts as a name too -- and the ambiguity rules
    # below then decide whether it can be searched bare, which is how a first word that
    # happens to be an ordinary one stays harmless.
    head = {b.split()[0] for b in base if " " in b}
    return sorted({n for n in full | base | head if n})


def _is_text(path: str) -> bool:
    """Skip binaries: a name matches inside a PNG by coincidence, not by leaking."""
    try:
        with open(path, "rb") as fh:
            return b"\0" not in fh.read(8192)
    except OSError:
        return False


def repo_root(start: str = HERE) -> str:
    """The repository root, discovered from the script's own location.

    `--root` used to default to the working directory, and `git ls-files` run inside a
    subdirectory lists only what sits under it. Invoked the way the README documents it —
    from the skill folder — the guard read 81 of this repository's 94 tracked files, and
    the thirteen it could not see were a `docs/` subtree and the README. A client
    name was then committed into a compliance document through exactly that gap, and the
    run printed `ok`.

    So the root is asked of git, from where this file lives, and the working directory is
    never consulted. A control whose reach depends on where the operator happens to be
    standing reports success for the part of the tree it did not look at.
    """
    out = subprocess.run(["git", "-C", start, "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True, check=False)
    top = out.stdout.strip()
    if top and os.path.isdir(top):
        return top
    # No git, or an exported tree with no history: walk up for a .git marker instead, and
    # fall back to `start` rather than to the working directory, which is the bug above.
    d = os.path.abspath(start)
    while True:
        if os.path.exists(os.path.join(d, ".git")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return os.path.abspath(start)
        d = parent


def tracked_files(root: str = None):
    root = root or repo_root()
    out = subprocess.run(["git", "-C", root, "ls-files"],
                         capture_output=True, text=True, check=False).stdout.split("\n")
    return [os.path.join(root, f) for f in out
            if f and os.path.isfile(os.path.join(root, f))]


def _words(path=WORDS):
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            return {line.strip().lower() for line in fh if line.strip()}
    except OSError:
        return set(_FALLBACK_WORDS)


def ambiguous(name, words):
    """Can this name be searched bare, or does it need an account-ish neighbour?

    Two reasons it cannot. Too short: two characters match inside base64 by coincidence.
    Or ordinary: one account is named after a common English word, and a bare search for
    it reported a finding in half the repository. A multi-word name is never ordinary,
    however ordinary its parts.
    """
    if len(name) < MIN_LEN:
        return "too short"
    if " " not in name and name.lower() in words:
        return "an ordinary word"
    return None


def _pattern(name, words):
    """The regex that finds `name` without finding anything else.

    An unambiguous name is searched on its own, between word boundaries. Those boundaries
    do more work than they look like they do: the embedded fonts are base64 inside a
    `.css`, which reads as text, and one account name appears twice in that stream by
    coincidence. Base64 is unbroken word characters, so `\\b` refuses the match — which is
    why the boundary is not just about "Retailer" vs "Retail".

    An ambiguous name is searched only where its neighbourhood says "account": an
    environment suffix, an MCP server prefix, or the `+`/`_` a campaign-name fixture puts
    after it. Skipping such names was the first version's mistake — four real mentions of
    a two-character account sat in tracked files while the check reported success.
    """
    # A two-word account name reaches code as one word. The MCP config declares
    # `Two Words PROD`, a comment calls the account `TwoWords`, and a search for the
    # declared spelling walks straight past it — which is how one such name sat in
    # five tracked files, once beside its own nine-digit send volumes, while this
    # check reported success. Whitespace in a name therefore matches nothing, an
    # underscore, a hyphen or a space.
    body = r"[\s_-]*".join(re.escape(w) for w in name.split())
    tail = r"\b" if name[-1].isalnum() else ""
    if not ambiguous(name, words):
        return re.compile(r"\b" + body + tail, re.I)
    qualifier = r"(?:\s+(?:" + _ENV + r")\b|[+_])"
    return re.compile(r"(?:user-" + body + tail + r"|\b" + body + qualifier + r")", re.I)


def scan(names, files, words=None):
    """Every (file, name, count) where an account name appears in a text file."""
    words = _words() if words is None else words
    patterns = [(n, _pattern(n, words)) for n in names if n]
    findings = []
    for path in files:
        if not _is_text(path):
            continue
        try:
            with open(path, encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
        except OSError:
            continue
        for name, rx in patterns:
            hits = rx.findall(text)
            if hits:
                findings.append((path, name, len(hits)))
    return findings


# --------------------------------------------------------------------------
# short initials inside an example value
# --------------------------------------------------------------------------
# What makes a line a personal-data sample rather than prose. Any one is enough: an
# address, an international number, or two or more `key=value` pairs packed into one
# value -- which is the shape a tagging plan uses for a store record, and the shape the
# leak took.
_SAMPLE_SIGNALS = (
    re.compile(r"[^\s@\"']+@[^\s@\"']+\.[A-Za-z]{2,}"),
    re.compile(r"\+\d[\d\s().-]{6,24}\d"),
    re.compile(r"\w+=[^|;=]*[|;]\s*\w+="),
)

# A sample value written into a comment or a fixture is one line of prose. An embedded
# base64 font is a single line of a hundred thousand characters containing thousands of
# `+` runs, and matching the phone pattern against it costs seconds per file through
# backtracking alone -- the first version of this pass took 29s on this tree, 19x the
# rest of the check. Nothing useful lives past this width.
_SAMPLE_MAX_LINE = 500


def _is_sample_line(line: str) -> bool:
    if len(line) > _SAMPLE_MAX_LINE:
        return False
    return any(rx.search(line) for rx in _SAMPLE_SIGNALS)


def scan_sample_initials(names, files, words=None):
    """Every (file, name, count) where a SHORT account name sits in an example value.

    Scoped to sample-looking lines on purpose. A two-character name cannot be searched in
    prose without matching inside every base64 blob and half the English language, which
    is why `_pattern` demands a qualifier. But a quoted sample value is not prose: a
    two-letter token next to a place name and a phone number in a `|`-packed record is a
    real signal, and it is precisely where the leak keeps happening, because writing a
    realistic example means reaching for a real account.
    """
    words = _words() if words is None else words
    short = [n for n in names if ambiguous(n, words) == "too short"]
    if not short:
        return []
    patterns = [(n, re.compile(r"\b" + re.escape(n) + r"\b")) for n in short]
    findings = []
    for path in files:
        if not _is_text(path):
            continue
        try:
            with open(path, encoding="utf-8", errors="ignore") as fh:
                lines = fh.readlines()
        except OSError:
            continue
        counts = {}
        for line in lines:
            if not _is_sample_line(line):
                continue
            for name, rx in patterns:
                # Case-SENSITIVE here: initials are written upper-case, and a
                # case-insensitive two-letter search inside a sample line reports every
                # ordinary syllable that happens to match.
                hits = len(rx.findall(line))
                if hits:
                    counts[name] = counts.get(name, 0) + hits
        findings.extend((path, n, c) for n, c in counts.items())
    return sorted(findings)


# --------------------------------------------------------------------------
# real portfolio figures in comments and docstrings
# --------------------------------------------------------------------------
# A bare run of digits. The lookbehind drops what is not a measurement: the fractional
# part of a decimal, a hex colour, a `+`-prefixed dialled number, a hex literal.
#
# There is deliberately NO trailing lookahead. A first draft rejected a match followed by
# "." so as not to read a decimal's integer part -- and that silently exempted the exact
# leak this exists for, a volume quoted as "12345678.0" straight out of the formatter that
# rendered it. The run is greedy, so a trailing digit is impossible anyway.
#
# The run also accepts group separators, because prose quotes a volume the way the report
# prints it. A grouped `123,456,789` is the same portfolio datum as `123456789`, and the
# digits-only pattern read it as three short runs, none of them long enough to report.
# Both thousands conventions count, comma and narrow no-break space, and the separators
# are stripped before the token is judged.
_BARE_FIGURE = re.compile(
    r"(?<![\d.,+#xX])\d{1,3}(?:[,\u202f\u00a0](?=\d{3}\b)\d{3}){2,}"   # 123,456,789
    r"|(?<![\d.,+#xX])\d{6,}")                                         # 123456789
_FIGURE_MIN = 6
_GROUP_SEP = re.compile(r"[,\u202f\u00a0]")

# A digit run inside a URL is an identifier -- a Confluence page, a Jira issue, a Google
# Doc -- and never a measurement. Left in, it makes the check cry wolf on every document
# that cites a source, which is every compliance document; the first one to link the AI
# Products inventory was rejected for its page id. Stripped before the scan rather than
# exempted after it, because the token itself is indistinguishable from a send volume.
_URL = re.compile(r"\bhttps?://\S+|\bwww\.\S+")

# `rgb(0,102,204)` and `rgba(255,255,255,.6)` are channels, not a nine-digit volume, and
# the grouped-figure run above reads them as one. Every chart palette in this tree is
# written that way, so the separator support arrived with seven false positives attached.
# Stripped before the scan for the same reason a URL is: the token is indistinguishable
# from a measurement once it is out of its parentheses.
_RGB = re.compile(r"\brgba?\([^)]*\)", re.I)


def _looks_like_date(tok: str) -> bool:
    """True for a compact date token: 070626, 07062026, 20260607.

    Campaign names carry these and the skill's regexes document them, so they appear in
    comments legitimately and often.
    """
    def ok(d, m, y):
        return 1 <= int(d) <= 31 and 1 <= int(m) <= 12 and (0 <= int(y) <= 99
                                                            or 2000 <= int(y) <= 2099)
    if len(tok) == 6:
        return ok(tok[0:2], tok[2:4], tok[4:6]) or ok(tok[4:6], tok[2:4], tok[0:2])
    if len(tok) == 8:
        return ok(tok[0:2], tok[2:4], tok[4:8]) or ok(tok[6:8], tok[4:6], tok[0:4])
    return False


def _is_illustrative(tok: str) -> bool:
    """A digit run nobody could mistake for a measurement: 1234567, 99999999.

    Worth exempting explicitly rather than leaving to judgement, because this is the
    replacement the check itself asks for. A guard that then reports its own recommended
    fix is a guard people learn to skip.
    """
    if len(set(tok)) == 1:
        return True
    return all((int(b) - int(a)) % 10 == 1 for a, b in zip(tok, tok[1:]))


def _is_portfolio_figure(tok: str) -> bool:
    """Is this long integer plausibly a measurement taken from a real account?"""
    if len(tok) < _FIGURE_MIN:
        return False
    # A round magnitude is an illustration, not a measurement: nobody's send total is
    # 12000000, which is exactly why a documenting author reaches for it.
    if tok.endswith("000"):
        return False
    if _is_illustrative(tok):
        return False
    return not _looks_like_date(tok)


def _py_prose(path):
    """-> [(lineno, text)] for every comment and triple-quoted string in a Python file."""
    out = []
    try:
        with open(path, "rb") as fh:
            for tok in tokenize.tokenize(fh.readline):
                if tok.type == tokenize.COMMENT:
                    out.append((tok.start[0], tok.string))
                elif tok.type == tokenize.STRING and tok.string[:3] in ('"""', "'''"):
                    out.append((tok.start[0], tok.string))
    except (OSError, tokenize.TokenError, SyntaxError, UnicodeDecodeError):
        # An unparseable file is a syntax problem for another tool to report, not a leak.
        pass
    return out


def _md_prose(path):
    """-> [(lineno, text)] for markdown outside fenced code blocks.

    Fenced blocks are excluded because they hold payloads, API responses and fixtures,
    where a long integer is the content rather than an aside.
    """
    out, fenced = [], False
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            for i, line in enumerate(fh, 1):
                if line.lstrip().startswith("```"):
                    fenced = not fenced
                    continue
                if not fenced:
                    out.append((i, line))
    except OSError:
        pass
    return out


def scan_bare_figures(files):
    """Every (file, lineno, figure) that looks like a real metric in an aside.

    Only comments, docstrings and markdown prose. Code is exempt: a long integer in a
    test fixture or a dict literal is doing work, and the fixtures in this tree are
    already fictional by convention.
    """
    findings = []
    for path in files:
        if path.endswith(".py"):
            chunks = _py_prose(path)
        elif path.endswith(".md"):
            chunks = _md_prose(path)
        else:
            continue
        for lineno, text in chunks:
            for m in _BARE_FIGURE.finditer(_RGB.sub(" ", _URL.sub(" ", text))):
                # Judge the digits, report what the author wrote: a grouped figure has to
                # be read as one measurement, and quoted back with its separators or the
                # author cannot find it on the line.
                if _is_portfolio_figure(_GROUP_SEP.sub("", m.group(0))):
                    findings.append((path, lineno, m.group(0)))
    return sorted(set(findings))


def _selftest() -> int:
    import tempfile
    fails = []

    def check(cond, label):
        if not cond:
            fails.append(label)

    words = {"anchor"}

    with tempfile.TemporaryDirectory() as tmp:
        mcp = os.path.join(tmp, "mcp.json")
        with open(mcp, "w", encoding="utf-8") as fh:
            json.dump({"mcpServers": {"Example Retail PROD": {}, "XY PROD": {},
                                      "Anchor PROD": {}, "docs-server": {},
                                      "scratch project": {}}}, fh)
        sweep = os.path.join(tmp, "probe_sweep.json")
        with open(sweep, "w", encoding="utf-8") as fh:
            json.dump({"window": ["2026-08-10", "2026-08-20"],
                       "rows": [{"project": "Example Retail PROD", "shape": "firehose"},
                                {"project": "Sample Broadcaster", "shape": "dashboard"}]},
                      fh)
        fixture = os.path.join(tmp, "expected.json")
        with open(fixture, "w", encoding="utf-8") as fh:
            json.dump({"_note": "ignored", "Third Account PROD": "firehose"}, fh)

        names = account_names(mcp, (sweep, fixture))
        check(names == ["Anchor", "Anchor PROD", "Example", "Example Retail",
                        "Example Retail PROD", "Sample", "Sample Broadcaster", "Third",
                        "Third Account", "Third Account PROD", "XY", "XY PROD"],
              f"full, base and first-word forms from both sources, got {names}")
        check("docs-server" not in names and "scratch project" not in names,
              "a server with no environment suffix is not an account")
        check(account_names(os.path.join(tmp, "absent.json"),
                            (os.path.join(tmp, "absent2.json"),)) == [],
              "no local source yields no names rather than an error")

        check(ambiguous("XY", words) == "too short", "two characters cannot be searched")
        check(ambiguous("Anchor", words) == "an ordinary word", "a common word cannot")
        check(ambiguous("Anchor Pharmacy", words) is None,
              "a multi-word name is searchable even when a part of it is a word")
        check(ambiguous("Example Retail", words) is None, "a distinctive name is")

        # a name in prose is a finding; the same name inside a binary is not
        doc = os.path.join(tmp, "notes.md")
        with open(doc, "w", encoding="utf-8") as fh:
            fh.write("Replayed on Example Retail and on sample broadcaster twice.\n")
        blob = os.path.join(tmp, "logo.png")
        with open(blob, "wb") as fh:
            fh.write(b"\x89PNG\r\n\x1a\n\x00Example Retail\x00")
        clean = os.path.join(tmp, "clean.py")
        with open(clean, "w", encoding="utf-8") as fh:
            fh.write("# validated against five archived audits\n")

        found = scan(names, [doc, blob, clean], words)
        by_name = {n: c for _p, n, c in found}
        check(set(by_name) == {"Example", "Example Retail", "Sample", "Sample Broadcaster"},
              f"prose findings only, got {sorted(by_name)}")
        check(by_name["Sample Broadcaster"] == 1, "the match is case-insensitive")
        check(all(p != blob for p, _n, _c in found),
              "a coincidental match inside a binary is not a finding")
        check(all(p != clean for p, _n, _c in found),
              "a comment that names no account passes")

        # the hole the first version shipped: four real mentions of a two-character
        # account passed, because a short name was skipped rather than qualified
        short = os.path.join(tmp, "setup.md")
        with open(short, "w", encoding="utf-8") as fh:
            fh.write("Duplicate the block for each client (`XY PROD`, …).\n"
                     "Cursor exposes it as `user-XY`, and the fixture names are\n"
                     "XY+_push_series_01062026. The word xylophone is not an account,\n"
                     "and neither is the base64 fragment m+sD13XY8MotV5.\n")
        hits = {n: c for p, n, c in scan(names, [short], words)}
        check(hits.get("XY PROD") == 1, f"the full form is found, got {hits}")
        # the base name qualifies three times: beside PROD, after user-, before +_.
        # "xylophone" and the base64 fragment "m+sD13XY8MotV5" are neither.
        check(hits.get("XY") == 3, f"a short name is found only qualified, got {hits}")

        # an ordinary word is found beside a qualifier and nowhere else
        word = os.path.join(tmp, "prose.md")
        with open(word, "w", encoding="utf-8") as fh:
            fh.write("Anchor the window to the caller, not to the report.\n"
                     "Reproduced on `Anchor PROD` with the same window.\n")
        hits = {n: c for p, n, c in scan(names, [word], words)}
        check(hits.get("Anchor PROD") == 1 and hits.get("Anchor") == 1,
              f"an ordinary word is found only when qualified, got {hits}")

        # a substring is not a name: "Example Retailer" must not match "Example Retail"
        sub = os.path.join(tmp, "sub.md")
        with open(sub, "w", encoding="utf-8") as fh:
            fh.write("Example Retailing is a different word.\n")
        check(scan(["Example Retail"], [sub], words) == [],
              "word boundaries hold, so a longer word is not a false finding")

        # base64 in a text file: the real case is an account name occurring twice
        # inside an embedded font. It reads as text, so only the boundary saves it.
        b64 = os.path.join(tmp, "fonts.css")
        with open(b64, "w", encoding="utf-8") as fh:
            fh.write("src:url(data:font/woff2;base64,m+sD13+C8MExampleRetail3dlpkRM2)\n")
        check(scan(["ExampleRetail"], [b64], words) == [],
              "a name inside a base64 stream is not a finding")

        # --- short initials inside an example value ---
        # The leak this closes: an illustrative composite sample, written by reaching for
        # a real account, in a comment two lines above a self-test that correctly used a
        # fictional one. Fictional here for the same reason.
        smp = os.path.join(tmp, "redact.py")
        with open(smp, "w", encoding="utf-8") as fh:
            fh.write('# a composite sample like\n'
                     '# "name=XY Rennes|contact=r.rennes@brand.fr|phone=+33 2 99 00 00 00"\n'
                     '# passed through untouched.\n'
                     'SAMPLE = "name=Store Rennes|contact=r@example.net"\n')
        hits = {n: c for _p, n, c in scan_sample_initials(names, [smp], words)}
        check(hits.get("XY") == 1, f"a short name in a sample value is found, got {hits}")
        # prose mentioning the same initials, with no sample on the line, stays clean:
        # that is `scan`'s job and it has the qualifier rules for it
        pro = os.path.join(tmp, "prose2.md")
        with open(pro, "w", encoding="utf-8") as fh:
            fh.write("The XY axis of the chart is the window.\n"
                     "Mail us at team@example.net about the xy scaling.\n")
        check(scan_sample_initials(names, [pro], words) == [],
              "a short token in prose, or lower-case beside an address, is not a finding")
        # a long name needs no help from this pass; `scan` already finds it bare
        check(all(n != "Example Retail"
                  for _p, n, _c in scan_sample_initials(names, [smp], words)),
              "this pass only handles the names scan cannot search bare")

        # --- real portfolio figures in comments and docstrings ---
        # Invented figures. Real ones are what this check exists to keep out, and the
        # docstring above records that a previous draft of this very file shipped one.
        check(_is_portfolio_figure("13571113"), "a non-round 8-digit figure is a finding")
        check(_is_portfolio_figure("4818244"), "a non-round 7-digit figure is a finding")
        check(not _is_portfolio_figure("12000000"), "a round magnitude is illustrative")
        check(not _is_portfolio_figure("2000000"), "so is a round 7-digit one")
        check(not _is_portfolio_figure("12345"), "under six digits is not checked")
        # the check must not report the very replacement it recommends
        check(not _is_portfolio_figure("1234567"), "a sequential run is illustrative")
        check(not _is_portfolio_figure("99999999"), "so is a repeated digit")
        check(_is_portfolio_figure("1234568"), "one digit off sequential is not")
        for date in ("070626", "07062026", "20260607"):
            check(_looks_like_date(date), f"{date} reads as a date")
            check(not _is_portfolio_figure(date), f"{date} is a date, not a measurement")
        check(not _looks_like_date("13571113"), "an implausible day/month is not a date")

        fig = os.path.join(tmp, "fmt.py")
        with open(fig, "w", encoding="utf-8") as fh:
            fh.write('def fmt():\n'
                     '    """Glues the groups together ("4818244").\n\n'
                     '    A headline "13571113.0" — the shape the leak actually took.\n'
                     '    Round magnitudes like 12000000 are fine, and so is 070626,\n'
                     '    and so is the fraction in 0.6743129.\n'
                     '    """\n'
                     '    # measured at 2468101 on one account\n'
                     '    return 9182736            # a literal is code, not an aside\n')
        got = {(l, t) for _p, l, t in scan_bare_figures([fig])}
        check(got == {(2, "4818244"), (2, "13571113"), (8, "2468101")},
              f"a docstring and a comment are checked; a code literal, a round "
              f"magnitude, a date and a fraction are not — got {sorted(got)}")

        md = os.path.join(tmp, "notes2.md")
        with open(md, "w", encoding="utf-8") as fh:
            fh.write("The account sent 13571113 pushes.\n\n"
                     "```json\n{\"sends\": 13571113}\n```\n"
                     "Palette `#000818` is a colour, not a volume.\n")
        got = {(l, t) for _p, l, t in scan_bare_figures([md])}
        check(got == {(1, "13571113")},
              f"markdown prose is checked, fenced code and colours are not, got {got}")

        # A cited source is not a measurement. Without this, every compliance document
        # that links its own evidence fails the check on the page id in the URL.
        cite = os.path.join(tmp, "cite.md")
        with open(cite, "w", encoding="utf-8") as fh:
            fh.write("Inventory: https://example.atlassian.net/wiki/pages/3473080347/AI\n"
                     "Ticket www.example.com/browse/4613406721 and a real 13571113.\n")
        got = {(l, t) for _p, l, t in scan_bare_figures([cite])}
        check(got == {(2, "13571113")},
              f"digits inside a URL are identifiers, prose beside them is still "
              f"checked — got {sorted(got)}")

    # Coverage. The regression this pins is not a missed pattern but a missed FILE: on
    # 2026-08-25 the guard ran from the skill folder, `git ls-files` listed only what sat
    # under it, and a client name committed to a compliance document one level up was
    # reported as `ok`. Everything above is about what the scan recognises; this is about
    # what it is even shown.
    have_git = subprocess.run(["git", "--version"], capture_output=True,
                              check=False).returncode == 0
    if have_git:
        with tempfile.TemporaryDirectory() as tmp:
            repo = os.path.realpath(tmp)          # macOS resolves /var -> /private/var
            deep = os.path.join(repo, "a", "b", "scripts")
            os.makedirs(deep)
            open(os.path.join(repo, "COMPLIANCE.md"), "w").close()
            open(os.path.join(deep, "tool.py"), "w").close()
            for cmd in (["init", "-q"], ["add", "-A"]):
                subprocess.run(["git", "-C", repo] + cmd, capture_output=True, check=False)

            found = repo_root(deep)
            check(os.path.realpath(found) == repo,
                  f"the root is discovered from a nested directory, got {found}")
            wide = [os.path.basename(p) for p in tracked_files(repo_root(deep))]
            check("COMPLIANCE.md" in wide,
                  f"a tracked file ABOVE the script's own directory is in scope, got {wide}")
            # And the narrow scan really does miss it, so the assertion above is not
            # vacuous and nobody can satisfy it by widening the wrong function.
            narrow = [os.path.basename(p) for p in tracked_files(deep)]
            check("COMPLIANCE.md" not in narrow,
                  "a subdirectory scan misses it — the reason the default no longer "
                  "comes from the working directory")

        # The checks above pass an explicit root, so they would survive a revert of the
        # default. This one exercises the DEFAULT from a subdirectory, which is the exact
        # shape of the failure: stand in `scripts/`, take the root from the working
        # directory, and every tracked file above `scripts/` silently leaves the scan.
        cwd = os.getcwd()
        try:
            os.chdir(HERE)
            outside = [p for p in tracked_files()
                       if not os.path.abspath(p).startswith(HERE + os.sep)]
            check(bool(outside),
                  "called with no root from a subdirectory, the scan still reaches "
                  f"tracked files outside it (found {len(outside)})")
        finally:
            os.chdir(cwd)

    for f in fails:
        print(f"  \u2717 {f}")
    print(f"client-name guard selftest: {'FAIL' if fails else 'ok'} "
          f"({len(fails)} failure(s))")
    return 1 if fails else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=None,
                    help="repository root (default: discovered from this script's "
                         "location, NOT the working directory)")
    ap.add_argument("--selftest", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.selftest:
        return _selftest()

    names = account_names()
    if not names:
        print("no local account list (~/.cursor/mcp.json declares no project server, "
              "and no probe_sweep.json) — nothing to check against. This is expected "
              "on a machine that has not been pointed at any project.")
        return 0

    words = _words()
    qualified = {n: why for n in names if (why := ambiguous(n, words))}
    root = args.root or repo_root()
    files = tracked_files(root)
    findings = scan(names, files, words)
    samples = scan_sample_initials(names, files, words)
    figures = scan_bare_figures(files)

    # The root is printed because the failure it replaces was invisible: a scan confined to
    # a subdirectory says `ok` in exactly the same words as one that covered everything.
    print(f"scanning {root}")
    print(f"{len(names)} local account name(s) vs {len(files)} tracked file(s)"
          + (f", {len(qualified)} searched only beside PROD/DEV or user- "
             f"({', '.join(f'{n}: {w}' for n, w in sorted(qualified.items()))})"
             if qualified else ""))
    if not (findings or samples or figures):
        print("ok — no account name, example initial or portfolio figure "
              "in a tracked file")
        return 0

    if findings:
        for path, name, count in sorted(findings):
            print(f"  \u2717 {path}: {name} x{count}")
        print(f"\n{len(findings)} name finding(s). Describe the phenomenon without the "
              f"account: what carries a comment like this is the number of accounts and "
              f"the result, not which ones.")
    if samples:
        for path, name, count in samples:
            print(f"  \u2717 {path}: {name} x{count} inside an example value")
        print(f"\n{len(samples)} initial(s) in an example value. A realistic sample does "
              f"not need a real account — keep the shape of the field and change the "
              f"name, as the redaction self-test in analyze_tagging_plan.py does.")
    if figures:
        for path, lineno, tok in figures:
            print(f"  \u2717 {path}:{lineno}: {tok} reads as a real measurement")
        print(f"\n{len(figures)} figure(s) in a comment or docstring. A send volume is "
              f"portfolio data even with no name attached. Round it, or use an obviously "
              f"illustrative magnitude — the point of the example survives either.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
