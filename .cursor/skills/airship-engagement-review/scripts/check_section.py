#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render ONE section in isolation, and judge it by the rules the gate will apply.

    python scripts/check_section.py work/<client> volume_pressure
    python scripts/check_section.py work/<client> volume_pressure --lang fr
    python scripts/check_section.py --selftest

Why not just run `build_report.py`. A dozen section agents work in parallel in the same
directory, so at any moment somebody else's file is half-written; a full build imports
every section, which means agent A's build fails on agent B's syntax error and agent A
starts debugging a file it does not own. This loads exactly one module and renders it,
so a failure here is always yours.

Why it lives in the skill. Two consecutive engagement reviews wrote this file from
scratch, and both versions had false positives that cost more time than the checks
saved: one read the base64 payload of an embedded chart as a stray `nan`, the other
flagged a chart that a comment merely named, and framework tables whose class attribute
carries more than one token. Those corrections are in here, so the next run inherits
them instead of rediscovering them.

Nothing in this file is client-specific or run-specific. The values it refuses come from
`audit.contaminated_fields` (written by `verify_audit.py`) and from `facts.withheld`, so
a counter disqualified once is refused everywhere afterwards with no editing.

Exit code 0 means the module imports, `render(ctx, lang)` returns non-empty HTML, and
the house rules hold. It does not replace the delivery gate, which also judges the
report as a whole: coverage, chart embedding, cross-section coherence.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import canonical_sections as cs        # noqa: E402
import report_framework as fw          # noqa: E402
import report_interactive as ri        # noqa: E402
import verify_report as vr             # noqa: E402

# A base64 image payload is a long unbroken run of alphanumerics, and it will contain
# "nan" and "n/a" by chance. Excluding it is the difference between this check being
# useful and being ignored.
_B64 = re.compile(r"data:image/[a-z+]+;base64,[A-Za-z0-9+/=]+")
# Case carries the distinction. `None` with a capital N is Python's null reaching the
# page; `none` in lower case is the English answer to "what ran on this channel", and a
# table that says so is doing its job. The rest have no lower-case reading in a value.
_MISSING = r"nan|n/?a|undefined|\[object Object\]"
_MISSING_EXACT = r"None"

# `n/a` and `none` are legitimate in a sentence about something that does not apply, and
# `<b>none</b>` mid-sentence is emphasis, not a value. What is never legitimate is a
# whole cell or a KPI value holding one, so the scan is confined to those two slots.
_VALUE_SLOTS = (r'<td[^>]*>\s*({m})\s*</td>',
                r'class="[^"]*\bkpi-value\b[^"]*"[^>]*>\s*({m})\s*<')

# Files under data/ that survive `purge_work.py` (its KEEP_ANYWHERE). A section may read
# these; everything else under data/ is a raw pull, dropped the moment the gate passes.
_DATA_SURVIVES = ("analysis.json", "inventory.json", "reconcile.json", "audit_parsed.json",
                  "pushbodies.json", "collect_manifest.json", "perpush_sample.json",
                  "sends.json")
# The account's own top-level artefacts, kept forever and read freely.
_TOP_LEVEL = ("audit.json", "facts.json", "specs.json", "brand.json", "creatives.json",
              "tagging_plan.json", "audit_tagging.json", "audit_tagging_plan.json")
# `"data/events.json"` written out in one literal.
_DATA_PATH = re.compile(r"""["'](data\w*)[/\\]([\w./\\-]+\.json)["']""")
# The directory assembled separately — `os.path.join(HERE, "data")`, then read through a
# helper: `_DATA = os.path.join(..., "data")` / `_load("events.json")`. The literal path
# never appears, so the shape has to be recognised in two halves.
_DATA_DIR = re.compile(r"""["'](data\w*)["']\s*[,)]""")
_JSON_NAME = re.compile(r"""["']([\w.-]+\.json)["']""")

# The tolerance the delivery gate uses when comparing a rendered figure to facts.json.
_VALUE_TOL = 0.0005


class Ctx:
    """Mirrors the builder's context object: the two things a section may rely on."""

    def __init__(self, lang):
        self.lang = lang
        self.EN = lang == "en"

    def L(self, en, fr):
        return en if self.EN else fr


# ---------------------------------------------------------------------------
# the values a section may not print
# ---------------------------------------------------------------------------
# The methodology appendix exists to name the counters the review refused and print the
# distance between them and the authoritative figure. Refusing them there would forbid
# the one section whose job is to be explicit about them — and an appendix that cannot
# say which number it rejected is not an appendix.
_MAY_QUOTE_REFUSED = {"appendix"}


def refused_values(audit) -> list:
    """-> [(value, why)] from the audit's contamination registry.

    The registry is produced by the pipeline, so this grows by itself: the run that finds
    a sixth copy of a disqualified counter does not have to edit this file.
    """
    out = []
    for row in (audit or {}).get("contaminated_fields") or []:
        # A tap count is a small integer and matching it would fire on real figures. The
        # all-channel total is not a wrong number either — it is the right number for a
        # sentence about every channel, and §2 says so legitimately. Only the
        # responses/list family has no publishable reading at all.
        if row.get("kind") in ("tap_count", "all_channel"):
            continue
        v = row.get("value")
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            use = row.get("use_instead")
            out.append((float(v),
                        f"{row.get('path')} — {row.get('why') or 'not authoritative'}"
                        + (f". Use {use}" if use else "")))
    return out


def advisory_registry_rows(facts):
    """The withheld record, whichever shape the pipeline wrote it in."""
    withheld = (facts or {}).get("withheld") or []
    return (withheld if isinstance(withheld, list)
            else [dict(v or {}, metric=k) for k, v in withheld.items()])


def withheld_values(facts) -> list:
    """-> [(value, why)] from the withheld record. ADVISORY, and deliberately so.

    A withheld figure is usually withheld *as a particular reading* rather than banned
    outright: a programme's lifetime total must not be divided by the window, but a
    section explaining why the ceiling is not a bound has to print it. Making this a
    failure would flag the sections doing the most careful work, which is how a checker
    stops being read. It is reported so the author can confirm the caveat is beside it.
    """
    out = []
    rows = list(advisory_registry_rows(facts))
    for row in rows:
        v = row.get("value")
        # A withheld share is a small float a section may legitimately print for another
        # metric; only counts are unambiguous enough to look for by value.
        if isinstance(v, (int, float)) and not isinstance(v, bool) and abs(v) >= 1000:
            instead = row.get("instead") or row.get("publish_instead")
            out.append((float(v),
                        f"withheld: {row.get('metric')} — "
                        f"{row.get('reason') or 'withheld by the audit'}"
                        + (f". Publish {instead}" if instead else "")))
    return out


def _printed_numbers(html) -> set:
    """Every number the rendered HTML shows, with thousands separators normalised."""
    text = _B64.sub(" ", html)
    text = re.sub(r"<[^>]+>", " ", text)
    out = set()
    for m in re.findall(r"\d[\d  \u202f,\.]*\d|\d", text):
        cleaned = re.sub(r"[  \u202f,]", "", m)
        # A decimal comma survives the strip above as a dot; both forms are tried.
        for form in {cleaned, cleaned.replace(".", "")}:
            try:
                out.add(float(form))
            except ValueError:
                pass
    return out


def check_refused(html, refused) -> list:
    printed = _printed_numbers(html)
    hits = []
    for value, why in refused:
        if any(abs(p - value) <= abs(value) * _VALUE_TOL for p in printed):
            hits.append(f"prints {value:,.0f}, which is {why}")
    return hits


def check_missing_markers(html) -> list:
    body = _B64.sub(" ", html)
    hits = []
    for pattern in _VALUE_SLOTS:
        for expr, flags in ((_MISSING, re.I), (_MISSING_EXACT, 0)):
            for m in re.findall(pattern.format(m=expr), body, flags):
                token = m if isinstance(m, str) else m[0]
                hits.append(f"a value slot rendering `{token.strip()}` — render the "
                            f"figure, or say in words why it is absent")
    return hits


def check_source(src) -> list:
    """House rules that are cheaper to catch in the file than in the render."""
    hits = []
    # A reading tool's line numbers pasted into the file. Caught here so the author sees
    # what happened rather than an IndentationError forty lines away.
    if re.search(r"(?m)^ {0,6}\d+\|", src):
        hits.append("line-number prefixes such as `    20|` — those belong to the "
                    "reading tool, never to the file")
    hits += check_data_reads(src)
    return hits


def check_data_reads(src) -> list:
    """A section reading a raw pull under `data/` — which will not be there next time.

    `purge_work.py` retires the raw pulls the moment the gate passes, and the 30-day
    sweep finishes the job. A section that opens `data/events.json` therefore works
    exactly once: the report cannot be rebuilt after a framework fix, a wording change,
    or to produce the other language. One review had its `data/` removed mid-build by a
    concurrent purge and lost the section outright; a second shipped the same read
    undetected and is now un-rebuildable.

    The fix is never to protect the file. It is to put the figure in `audit.json`, where
    every other number in the report already lives. A handful of derived files inside
    `data/` ARE kept (`_DATA_SURVIVES`) and reading those is fine.
    """
    names = {m.group(2) for m in _DATA_PATH.finditer(src)}
    # A module that builds the pull directory once and then reads through a helper never
    # writes the joined path, so every .json name it mentions is a candidate. Confined to
    # modules that DO reference such a directory, which keeps it off sections that only
    # ever open the top-level artefacts.
    if _DATA_DIR.search(src):
        names |= set(_JSON_NAME.findall(src))
    hits = []
    for ref in sorted(names):
        name = os.path.basename(ref.replace("\\", "/"))
        if name in _DATA_SURVIVES or name in _TOP_LEVEL:
            continue
        hits.append(f"reads `{ref}` from the raw-pull directory — those files are "
                    f"retired when the gate passes, so this section cannot be "
                    f"re-rendered afterwards. Fix: have analyze.py put the figure in "
                    f"audit.json and read it there")
    return hits


# ---------------------------------------------------------------------------
# the gate's own section-scoped checks
# ---------------------------------------------------------------------------
# Running the authoritative implementations beats approximating them: these are the exact
# functions that judge the report at wave 6, so a section that passes them now does not
# come back in the gate-fix loop.
def _gate_checks(facts):
    return (
        ("KPI card with no methodology", vr._kpi_methodology_audit, None),
        ("orphan methodology block", vr._orphan_methodology, None),
        ("table without class=\"grid\"", vr._unstyled_tables, None),
        ("double-escaped entity", vr._double_escaped, None),
        ("illegible KPI", vr._illegible_kpis, None),
        ("gauge verdict contradicting its band", vr._gauge_verdicts, None),
        ("gauge verdict with no sample", vr._ungrounded_gauge_verdicts, None),
        ("weekly pressure unit", vr._weekly_pressure, None),
        ("mixed-basis column", vr._mixed_basis_columns, None),
        ("identifier-labelled row", vr._identifier_labelled_rows, None),
        ("figure disagreeing with facts.json", vr._facts_coherence, facts),
        ("contaminated delta with no caveat",
         vr._unqualified_contaminated_deltas, facts),
    )


def client_css(work_dir) -> str:
    """The builder's own `CSS_EXTRA`, read without importing it.

    A report may define layout classes its sections need (`reco-head`, `prio-verdict`)
    in `build_report.py` and pass them to `fw.assemble(css_extra=...)`. Judging a section
    against the framework stylesheet alone then reports every one of them as undefined —
    five false positives on a section that is perfectly correct, which is how a checker
    stops being read.

    Parsed rather than imported: importing the builder executes the whole report build,
    including a dozen sibling sections that may be half-written at this moment, which is
    the exact failure this script exists to avoid.
    """
    path = os.path.join(work_dir, "build_report.py")
    try:
        import ast
        tree = ast.parse(open(path, encoding="utf-8").read())
    except (OSError, SyntaxError, ValueError):
        return ""
    out = []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        names = {t.id for t in node.targets if isinstance(t, ast.Name)}
        if not names & {"CSS_EXTRA", "EXTRA_CSS", "CSS"}:
            continue
        try:
            val = ast.literal_eval(node.value)
        except ValueError:
            continue
        if isinstance(val, str):
            out.append(val)
    return "\n".join(out)


def _css_document(body, css_extra=""):
    """The section wrapped in the stylesheets it will actually be rendered against.

    `_undefined_css_classes` needs the <style> blocks to know what is defined. Building
    them from the framework constants plus the builder's own `css_extra` mirrors what
    `fw.assemble` will hand the browser — a class defined in neither is genuinely dead.
    """
    return (f"<style>{fw.FRAMEWORK_CSS}\n{ri.brand_report_css()}\n{ri.INTERACTIVE_CSS}"
            f"\n{css_extra}</style><body>{body}</body>")


def _as_list(found):
    """Gate helpers report either a count or the offending items; accept both."""
    if isinstance(found, bool):
        return ["found"] if found else []
    if isinstance(found, int):
        return [f"{found} occurrence(s)"] if found else []
    if isinstance(found, str):
        return [found]
    return list(found or [])


def check_localisation(html, lang) -> list:
    """Run the gate's own localisation lint on this one section.

    The lint already existed, already handled monolingual reports, and was simply not
    wired into the section check — so twelve agents in a row validated their file, saw
    OK, and shipped English prose into a French report that only the wave-6 gate caught.
    Every one of those was a round trip that did not need to happen.

    `_lang_blocks` keys a single-language document on its ``<html lang>``, so the
    fragment has to be wrapped in one: unwrapped, the lint finds no language and returns
    nothing, which reads as a pass.
    """
    if lang == "en":                      # nothing non-English to inspect
        return []
    doc = f'<html lang="{lang}"><body>{html}</body></html>'
    hits = []
    for lg, f in sorted(vr._localisation_lint(doc).items()):
        if f["leaks"]:
            hits.append(f"[{lg}] English strings: {', '.join(f['leaks'][:6])} — pass "
                        f"lang= to every component instead of relying on its English "
                        f"default, and rewrite anything quoted from audit.json (its "
                        f"prose is internal working English, never client copy)")
        if f["decimals"]:
            hits.append(f"[{lg}] English decimal marks: {', '.join(f['decimals'][:6])} "
                        f"— route numbers through ri.fmt_num/fmt_int/fmt_pct with lang=")
        if f.get("accents"):
            hits.append(f"[{lg}] French words missing accents: "
                        f"{', '.join(f['accents'][:6])}")
    return hits


def check_template_text(html) -> list:
    """Scaffold leftovers and f-strings that lost their `f`.

    Delegates to the gate's own implementation, so the two can never drift into
    disagreeing about what counts — the reason this file runs `vr` functions rather
    than approximating them.
    """
    return [f"{h} — scaffold text and unrendered expressions reach the reader verbatim"
            for h in vr._template_text(_B64.sub(" ", html))]


def check_html(html, facts, lang="en", css_extra="") -> list:
    hits = []
    for cls in vr._undefined_css_classes(_css_document(html, css_extra), html):
        hits.append(f"undefined CSS class `{cls}` — it is used in markup and styled "
                    f"nowhere, so the layout it asks for silently does not happen")
    if re.search(r'<img[^>]+src=""', html):
        hits.append("an <img> with an empty src")
    hits += check_template_text(html)
    hits += check_localisation(html, lang)
    for name, fn, arg in _gate_checks(facts):
        try:
            found = fn(html) if arg is None else fn(html, arg)
        except Exception as exc:              # a check that cannot run is not a pass
            hits.append(f"could not run the '{name}' gate check: {exc}")
            continue
        for h in _as_list(found)[:4]:
            hits.append(f"{name}: {h}")
    return hits


# ---------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------
def check(work_dir, key, lang="en") -> tuple:
    """-> (exit code, lines to print)."""
    out = []
    if key not in cs.ALL_KEYS:
        return 2, [f"FAIL: '{key}' is not a canonical section. "
                   f"See canonical_sections.ALL_KEYS."]

    # Absolute before anything else: the module is imported with the work directory as
    # the process cwd, so a relative path here would resolve inside it.
    work_dir = os.path.abspath(work_dir)
    sect_dir = os.path.join(work_dir, "sections")
    path = os.path.join(sect_dir, f"{key}.py")
    if not os.path.isfile(path):
        return 2, [f"FAIL: {path} does not exist."]

    src = open(path, encoding="utf-8").read()
    problems = check_source(src)
    if problems:
        return 2, ["FAIL: " + problems[0]]

    if sect_dir not in sys.path:
        sys.path.insert(0, sect_dir)
    cwd = os.getcwd()
    try:
        # Section modules read audit.json and facts.json relative to the work directory,
        # exactly as the builder runs them.
        os.chdir(work_dir)
        spec = importlib.util.spec_from_file_location(f"_check_{key}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        if not callable(getattr(mod, "render", None)):
            return 2, ["FAIL: no callable render(ctx, lang)."]
        try:
            html = mod.render(Ctx(lang), lang)
        except fw.NoData as nd:
            return 0, [f"OK (NoData): the section deliberately renders an N/A block "
                       f"— {nd.reason_en or nd.reason_fr}"]
    finally:
        os.chdir(cwd)

    if not html or not html.strip():
        return 2, ["FAIL: render() returned nothing. Return HTML, or raise NoData(...) "
                   "with a reason."]

    audit = _load(work_dir, "audit.json")
    facts = _load(work_dir, "facts.json")
    exempt = key in _MAY_QUOTE_REFUSED
    problems = (check_refused(html, [] if exempt else refused_values(audit))
                + check_missing_markers(html)
                + check_html(html, facts, lang, client_css(work_dir)))
    notes = [] if exempt else check_refused(html, withheld_values(facts))

    out.append(f"rendered {len(html):,} chars of HTML for {key} [{lang}]")
    out.extend(f"  ? {n} — legitimate if the caveat is beside it" for n in notes)
    if problems:
        out.extend(f"  ! {p}" for p in problems)
        return 1, out
    out.append("OK")
    return 0, out


def _load(work_dir, name):
    try:
        with open(os.path.join(work_dir, name), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("work_dir", nargs="?", help="work/<client>")
    ap.add_argument("key", nargs="?", help="canonical section key")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()
    if not args.work_dir or not args.key:
        ap.print_help()
        return 2
    code, lines = check(args.work_dir, args.key, args.lang)
    print("\n".join(lines))
    return code


# ---------------------------------------------------------------------------
# selftest
# ---------------------------------------------------------------------------
def _selftest() -> int:
    import tempfile
    fails = []

    def ck(cond, label):
        if not cond:
            fails.append(label)

    audit = {"contaminated_fields": [
        {"path": "inventory_stats.by_channel.push.sends", "value": 65_690_965,
         "kind": "responses_list", "use_instead": "usage.current.sends_push",
         "why": "responses/list counts every enumerable message"},
        {"path": "inventory_stats.by_channel.in_app.sends", "value": 238,
         "kind": "tap_count", "why": "button presses"}]}
    facts = {"withheld": [{"metric": "programme_lifetime_volume", "value": 6_568_661,
                           "reason": "pergroup/detail reports a whole history"}]}
    refused = refused_values(audit)
    ck(len(refused) == 1, "the registry is read and the tap count is skipped")
    ck(len(withheld_values(facts)) == 1, "the withheld record is read separately")
    ck(all(v != 238 for v, _ in refused),
       "a tap count is not refused by value — it would fire on real figures")
    ck(all(v != 49_828_956 for v, _ in refused),
       "the all-channel total is not refused — it is publishable, labelled as such")

    # the number as a section would actually render it, with a thousands separator
    ck(check_refused("<p>The account sent 65,690,965 pushes.</p>", refused),
       "a disqualified counter is caught through its formatting")
    ck(check_refused("<p>65 690 965</p>", refused),
       "the French thousands separator is caught too")
    ck(not check_refused("<p>The account sent 48,316,323 pushes.</p>", refused),
       "the authoritative figure is not refused")
    ck(check_refused("<p>6,568,661 lifetime sends</p>", withheld_values(facts)),
       "a withheld count is found, to be reported as an advisory")
    # the two false positives that cost the previous runs time
    ck(not check_refused('<!-- push_type_mix was dropped, see the appendix -->', refused),
       "naming a dropped chart in a comment is not an embed")
    ck(not check_missing_markers(
        '<td><img src="data:image/png;base64,iVBORnanA0KGgoAAAANa"></td>'),
       "a base64 payload containing `nan` is not a missing value")
    ck(not check_html('<table class="grid ir-exportable ir-sortable"><tr><td>1</td></tr>'
                      '</table>', {}),
       "a framework table carrying several class tokens is styled")

    ck(check_missing_markers("<td>nan</td>"), "a value slot holding `nan` is caught")
    ck(not check_missing_markers("<p>Attribution is n/a on this project.</p>"),
       "`n/a` in a sentence is legitimate")
    ck(not check_missing_markers("<td>The plan declares <b>none</b>. So this is</td>"),
       "`<b>none</b>` mid-sentence is emphasis, not an unrendered value")
    ck(not check_missing_markers("<td>none</td>"),
       "lower-case `none` is the English answer, not a leaked null")
    ck(check_missing_markers("<td>None</td>"), "Python's `None` on the page is caught")
    ck(check_html('<table><tr><td>1</td></tr></table>', {}),
       "a table with no class at all is caught")
    ck(any("undefined CSS class" in h
           for h in check_html('<div class="note-ok">x</div>', {})),
       "a class the framework does not define is caught")
    # ...unless the builder defines it in css_extra, which fw.assemble will ship.
    ck(not any("undefined CSS class" in h
               for h in check_html('<div class="reco-head">x</div>', {},
                                   css_extra=".reco-head{font-weight:700}")),
       "a class defined in the builder's css_extra is not reported undefined")

    with tempfile.TemporaryDirectory() as tmp:
        ck(client_css(tmp) == "", "no builder, no extra CSS, and no crash")
        open(os.path.join(tmp, "build_report.py"), "w").write(
            'X = 1\nCSS_EXTRA = ".reco-head{font-weight:700}"\n')
        ck(".reco-head" in client_css(tmp), "CSS_EXTRA is read without importing")
        open(os.path.join(tmp, "build_report.py"), "w").write("def broken(:\n")
        ck(client_css(tmp) == "", "a half-written builder degrades to no extra CSS")
    ck(check_source("    20|    x = 1"), "pasted line numbers are caught")
    ck(not check_source("x = 1  # 20|not a prefix"), "a pipe inside a line is not")

    # --- the leak that shipped: a sentence copied verbatim out of audit.json ---
    fr_leak = ('<p>The 2024 vintage runs below p10 of the panel, and the programme has '
               'not been retuned since it was launched.</p>')
    ck(any("English strings" in h for h in check_localisation(fr_leak, "fr")),
       "English prose in a French section is caught")
    ck(not check_localisation(fr_leak, "en"),
       "the same sentence in an English section is not a finding")
    ck(any("decimal" in h for h in check_localisation("<p>Le taux est de 3.72%.</p>", "fr")),
       "an English decimal mark is caught in French")
    ck(not check_localisation("<p>Le taux est de 3,72 %, en hausse nette.</p>", "fr"),
       "correct French prose passes")
    # The wrapper is the whole reason this works: unwrapped, the lint finds no language
    # and returns nothing, which reads as a pass.
    ck(not vr._localisation_lint(fr_leak),
       "an unwrapped fragment yields nothing — hence the <html lang> wrapper")

    # --- the f-string that lost its prefix, and scaffold text ---
    ck(check_template_text("<h3>De quoi sont faites les {n(inter, lang)} interactions</h3>"),
       "an unformatted f-string on the page is caught")
    ck(check_template_text('<td>{POPS["unnamed"]}</td>'),
       "a subscript expression printed verbatim is caught too")
    ck(not check_template_text("<p>Une progression de 12 % {sur un mois}.</p>"),
       "braces around plain prose are not a call expression")
    ck(not check_template_text("<p>The set {a, b} is unchanged.</p>"),
       "a set literal in prose is not an unformatted f-string")
    ck(check_template_text("<td>TODO</td>"), "scaffold TODO text is caught")
    ck(not check_template_text("<p>Sa todo list est vide.</p>"),
       "lower-case 'todo' in prose is not scaffold text")

    # --- a section reading a raw pull it will not have next time ---
    ck(check_data_reads('_EV = json.load(open("data/events.json"))'),
       "reading a raw pull under data/ is caught")
    ck(check_data_reads('open(os.path.join(HERE, "data", "events.json"))'),
       "the os.path.join spelling is caught too")
    # The shape that actually shipped: the directory is built once, the file is opened
    # through a helper, and the joined path is never written down anywhere.
    ck(check_data_reads('_DATA = os.path.join(HERE, "data")\n'
                        'def _load(name):\n    return json.load(open(f"{_DATA}/{name}"))\n'
                        '_EV = _load("events.json")'),
       "a pull read through a helper is caught")
    ck(not check_data_reads('json.load(open("data/collect_manifest.json"))'),
       "a file purge_work keeps is fine to read")
    ck(not check_data_reads('_DATA = os.path.join(HERE, "data")\n'
                            'M = _load("collect_manifest.json")'),
       "...through a helper too")
    ck(not check_data_reads('A = json.load(open("audit.json"))\n'
                            'F = json.load(open("facts.json"))'),
       "the top-level artefacts are not under data/")

    print(f"check_section selftest: {'ok' if not fails else 'FAILED'} "
          f"({len(fails)} failure(s))")
    for f in fails:
        print(f"  - {f}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
