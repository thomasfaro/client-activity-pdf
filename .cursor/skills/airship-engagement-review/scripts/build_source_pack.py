#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a NotebookLM source library for one account — deterministic, no model, no API.

Turns whatever a run has already produced under ``work/<client>/`` into a folder of
markdown documents meant to be uploaded to Gemini Notebook Enterprise, so an account
team can interrogate the DATA rather than re-read the report's conclusions.

    python scripts/build_source_pack.py work/<client> --client "Brand" \
        --vertical retail --lang fr
    python scripts/build_source_pack.py --selftest      # offline, no work dir needed

**The pack must make the notebook autonomous, and that is a content requirement rather
than a packaging one.** A pack carrying only figures produces a notebook that invents
definitions: it adds opens to direct opens, compares a device snapshot to period
opt-ins, reads a benchmark as a point instead of a band, and takes a custom event's
`value` for an amount in euros. So the pack ships three things — the account's data
(tiers 2 and 3), the semantics that define it, and the sector references that make a
gap judgeable (tier 1, from ``source_pack_corpus``).

Design rules this file encodes:

  * **Nothing is mandatory beyond ``data/``.** ``discover()`` reports what it found and
    what it did not; ``audit.json``/``facts.json`` and the tagging-plan pair each add
    documents when present. A pack built minutes after ``collect.py`` is valid, smaller,
    and says so in its own manifest.
  * **Every emitted string is scrubbed, including what comes from ``audit.json``.** The
    risk assessment of 2026-08-28 carries R9 (open, High): unredacted consumer email
    addresses reach ``audit.json`` on every run that ingests a tagging plan. This does
    not fix R9 upstream — it stops it propagating into a notebook that retains and
    shares what it is given.
  * **Tables stay tables, and the heavy ones become their own source.** Notebook
    Enterprise reads long markdown tables well and has the context window to hold them,
    so an inventory is never reshaped into prose; it is cut into header-bearing segments
    (``data_table``) and, past ``ANNEX_THRESHOLD`` rows, moved into a companion ``9x``
    document. That last part is the point: an annex is a separate notebook source, so it
    can be deselected for a strategy question and selected for a counting one.
  * **A number without its definition in the same pack is a number read wrong**, so
    ``verify`` fails a pack that publishes a metric with no matching fiche.

Pure stdlib. Read-only with respect to everything it reads.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# The two unanchored PII patterns are IMPORTED rather than re-declared. A second copy
# would drift from the ones the tagging-plan analyser is tested against, and the whole
# point of a privacy control is that there is one of it.
from analyze_tagging_plan import _EMAIL_IN_RE, _PHONE_IN_RE, _REDACTED  # noqa: E402

# Gemini Notebook Enterprise limits, as published 2026-09: 300 sources per notebook,
# 500,000 words or 200 MB per source. The pack lands around 25 documents, so the source
# count is checked for form rather than because it is close.
WORD_CAP = 500_000
BYTE_CAP = 200 * 1024 * 1024
SOURCE_CAP = 300

# Field names that identify one person or one device. They never appear in a generated
# document because no emitter selects them; this list is what makes that a checked
# property instead of a habit. Not applied to the verbatim tier-1 corpus, which is API
# documentation and legitimately names the fields it documents.
IDENTIFIER_KEYS = ("named_user", "named_user_id", "channel_id", "channel_ids",
                   "device_token", "apid", "email_address")

# Body rows one table segment may carry. Kept in step with
# source_pack_docs.ROWS_PER_SEGMENT: that module decides the shape, this one refuses a
# pack that got it wrong — an unsegmented long table means an emitter built its markdown
# by hand instead of going through `data_table`.
ROWS_PER_SEGMENT = 50

DOWNLOADS = os.path.join(os.path.expanduser("~"), "Downloads")


# --------------------------------------------------------------------------- #
# Scrub
# --------------------------------------------------------------------------- #
def redact_text(text):
    """Mask embedded emails/phones anywhere in a document. Returns (text, n_masked).

    Document-level twin of ``analyze_tagging_plan.redact_sample``, which is anchored to
    a single sample value and cannot be pointed at a whole markdown file. Same patterns,
    so the two cannot disagree about what counts as personal.
    """
    s = str(text)
    out, n_email = _EMAIL_IN_RE.subn(_REDACTED["email"], s)
    out, n_phone = _PHONE_IN_RE.subn(_REDACTED["phone"], out)
    return out, n_email + n_phone


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
# logical name -> candidate relative paths, in preference order. The doubled candidates
# are not defensiveness for its own sake: `analysis.json`/`inventory.json` sit under
# `data/` on one account and `data/audit/` on another, which is the same reason
# purge_work.py keeps them by name at any depth.
LAYOUT = {
    "collect_manifest": ["data/collect_manifest.json", "collect_manifest.json"],
    "probe": ["data/probe.json", "probe.json"],
    "devices": ["data/devices.json"],
    "sends": ["data/sends.json"],
    "opens": ["data/opens.json"],
    "optins": ["data/optins.json"],
    "optouts": ["data/optouts.json"],
    "events": ["data/events.json"],
    "activity": ["data/activity.json"],
    "responses": ["data/responses.json"],
    "pergroup": ["data/pergroup.json"],
    "program_volume": ["data/program_volume.json"],
    "perpush_detail": ["data/perpush_detail.json"],
    "decoded": ["data/decoded.json"],
    "groups_decoded": ["data/groups_decoded.json"],
    "reconcile": ["data/reconcile.json"],
    "audit": ["audit.json"],
    "facts": ["facts.json"],
    "inventory": ["data/inventory.json", "data/audit/inventory.json",
                  "goals/inventory.json", "inventory.json"],
    "analysis": ["data/analysis.json", "data/audit/analysis.json",
                 "goals/analysis.json", "analysis.json"],
    "brand": ["brand.json", "goals/brand.json"],
    # The delivered review. Optional like everything else: a pack built straight after
    # `collect.py` has no report yet, and says so rather than failing.
    "report": ["report.html"],
}

# Inputs `discover` locates but must not parse as JSON. Without this the loader warned
# "report.html unreadable", which reads like a broken pull rather than a file that was
# never JSON to begin with.
NOT_JSON = {"report"}


def load_json(path):
    """Read a JSON file, or return None. A missing input degrades one document."""
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"[warn] {path} unreadable ({exc}) — the documents that needed it will "
              f"say so", flush=True)
        return None


def discover(work_dir):
    """Locate every optional input under one account directory.

    Returns ``{"root", "found": {name: path}, "missing": [name], "data": {name: obj}}``.
    Nothing raises and nothing is required: the manifest publishes the absences, which
    is what lets a pack built straight after ``collect.py`` be honest rather than thin.
    """
    root = os.path.abspath(work_dir)
    found, missing = {}, []
    for name, candidates in LAYOUT.items():
        hit = next((os.path.join(root, c) for c in candidates
                    if os.path.isfile(os.path.join(root, c))), None)
        if hit:
            found[name] = hit
        else:
            missing.append(name)
    return {"root": root, "found": found, "missing": missing,
            "data": {name: load_json(path) for name, path in found.items()
                     if name not in NOT_JSON}}


# --------------------------------------------------------------------------- #
# The pack
# --------------------------------------------------------------------------- #
class Doc:
    """One emitted source document."""

    def __init__(self, name, title, tier, body, provenance=None, verbatim=False):
        self.name = name
        self.title = title
        self.tier = tier
        self.body = body
        self.provenance = provenance or "generated by build_source_pack.py"
        self.verbatim = verbatim
        self.masked = 0

    @property
    def words(self):
        return len(self.body.split())


# Canonical source names are authored once in French inside the emitters. English packs
# translate the filename at the Pack boundary so every writer, the manifest and the
# generated README see the same final name. The numeric prefixes stay stable because they
# carry the source tier and are part of the NotebookLM selection workflow.
EN_SOURCE_NAMES = {
    "00_README_pack.md": "00_README_pack.md",
    "01_endpoints_reports_api.md": "01_reports_api_endpoints.md",
    "02_definitions_et_perimetre.md": "02_definitions_and_scope.md",
    "03_fiches_metriques.md": "03_metric_reference.md",
    "04_limites_et_inferences_interdites.md": "04_limits_and_forbidden_inferences.md",
    "05_comment_lire_les_benchmarks.md": "05_how_to_read_benchmarks.md",
    "06_referentiels_metier.md": "06_business_reference_material.md",
    "10_profil_du_compte.md": "10_account_profile.md",
    "11_perimetre_et_couverture.md": "11_scope_and_coverage.md",
    "20_audience_et_permission.md": "20_audience_and_permission.md",
    "21_volume_et_pression.md": "21_volume_and_pressure.md",
    "22_inventaire_campagnes.md": "22_campaign_inventory.md",
    "23_programmes_automatises.md": "23_automated_programs.md",
    "24_creatives_decodees.md": "24_decoded_creatives.md",
    "25_evenements_custom.md": "25_custom_events.md",
    "26_plan_de_taggage.md": "26_tagging_plan.md",
    "27_benchmarks_secteur.md": "27_sector_benchmarks.md",
    "28_kpis_consolides.md": "28_consolidated_kpis.md",
    "90_annexe_inventaire_campagnes.md": "90_campaign_inventory_annex.md",
    "91_annexe_creatives.md": "91_creatives_annex.md",
    "92_annexe_evenements.md": "92_events_annex.md",
    "93_annexe_plan_de_taggage.md": "93_tagging_plan_annex.md",
    "94_annexe_series_quotidiennes.md": "94_daily_series_annex.md",
    "95_annexe_programmes.md": "95_programs_annex.md",
    "96_annexe_benchmarks_tous_verticaux.md": "96_all_vertical_benchmarks_annex.md",
    "97_annexe_permission_quotidienne.md": "97_daily_permission_annex.md",
    "99_rapport_engagement.md": "99_engagement_report.md",
}


def source_name(name, lang):
    """Return the on-disk source filename for the requested pack language."""
    return EN_SOURCE_NAMES.get(name, name) if lang == "en" else name


class Pack:
    """Collects documents, scrubs them, writes them, and refuses to ship a bad one."""

    def __init__(self, out_dir, client, lang="fr", window=None, vertical=None,
                 window_range=None, include_samples=True):
        self.out_dir = os.path.abspath(out_dir)
        self.client = client
        self.lang = lang
        self.window = window
        # `(start, end)`, used by `source_pack_docs.window_series` to slice the daily
        # files. The collector pulls current and prior together; without this every local
        # total covers two periods and silently doubles.
        self.window_range = window_range
        self.vertical = vertical
        # Internal private notebooks need tagging-plan sample values, including personal
        # data. `--no-samples` restores the redacted, sample-free pack.
        self.include_samples = include_samples
        self.docs = []
        self.extras = []
        self.metrics_published = set()
        self.metrics_documented = set()
        self.notes = []

    # -- collection ------------------------------------------------------
    def source_name(self, name):
        """Translate a canonical emitter filename to this pack's output language."""
        return source_name(name, self.lang)

    def localize_source_references(self, text):
        """Keep filenames mentioned inside English documents aligned with the disk."""
        if self.lang != "en":
            return text
        # Longest first: `93_annexe_plan_de_taggage` contains
        # `26_plan_de_taggage`'s descriptive tail. Replacing the short form first
        # produces the invalid hybrid `93_annexe_tagging_plan`.
        for canonical, english in sorted(
                EN_SOURCE_NAMES.items(), key=lambda item: len(item[0]), reverse=True):
            text = text.replace(canonical, english)
            text = text.replace(canonical.rsplit(".", 1)[0],
                                english.rsplit(".", 1)[0])
        return text

    def add(self, name, title, tier, body, provenance=None, verbatim=False):
        """Register a document, scrubbed on the spot. Empty bodies are dropped.

        A zero-byte source in a notebook is worse than an absent one: it occupies a
        slot in the source list and answers questions with nothing.

        Scrubbing happens here rather than at write time so that every later step —
        ``verify``, and the README that reports the masking count — sees the text that
        will actually ship.
        """
        if not (body or "").strip():
            self.notes.append(f"{name}: not emitted (no data for it on this account)")
            return None
        name = self.source_name(name)
        body = self.localize_source_references(body)
        doc = Doc(name, title, tier, body, provenance, verbatim)
        if self.include_samples:
            doc.masked = 0
        else:
            doc.body, doc.masked = redact_text(doc.body)
        self.docs.append(doc)
        return doc

    def add_raw(self, name, text, note):
        """Register an annex that is NOT a notebook source (a spreadsheet export)."""
        self.extras.append((name, text, note))

    def publish_metric(self, key):
        """Declare that a tier-3 document prints this metric. `verify` needs a fiche."""
        self.metrics_published.add(key)

    def document_metric(self, key):
        """Declare that tier 1 carries a fiche for this metric."""
        self.metrics_documented.add(key)

    # -- output ----------------------------------------------------------
    def _header(self, doc):
        # The provenance block follows --lang like the rest of the document. It used to be
        # hardcoded French, which put an English pack's prose under a French stamp — the
        # one outcome the language contract in source-pack.md explicitly rules out.
        # Filenames follow the same language through `source_name()`.
        en = self.lang == "en"
        account = "account" if en else "compte"
        window = "window" if en else "fenêtre"
        notice = ("**Airship internal use** — this document is part of a source library "
                  "generated on " if en else
                  "**usage interne Airship** — ce document fait partie d'une "
                  "bibliothèque de sources générée le ")
        return (f"# {doc.title}\n\n"
                f"> **provenance:** {doc.provenance}  \n"
                f"> **{account}:** {self.client}"
                + (f" · **{window}:** {self.window}" if self.window else "")
                + (f" · **vertical:** {self.vertical}" if self.vertical else "")
                + "  \n"
                f"> {notice}{_dt.date.today().isoformat()}.\n\n")

    def write(self):
        os.makedirs(self.out_dir, exist_ok=True)
        written = []
        for doc in self.docs:
            path = os.path.join(self.out_dir, doc.name)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self._header(doc) + doc.body.rstrip() + "\n")
            written.append(path)
        for name, text, _note in self.extras:
            payload = text if self.include_samples else redact_text(text)[0]
            with open(os.path.join(self.out_dir, name), "w", encoding="utf-8") as fh:
                fh.write(payload)
        self._write_manifest()
        return written

    def _write_manifest(self):
        manifest = {
            "generated": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "client": self.client,
            "window": self.window,
            "vertical": self.vertical,
            "lang": self.lang,
            "include_samples": self.include_samples,
            "target": "Gemini Notebook Enterprise",
            "tiers": {
                "1": "semantics — definitions, endpoints, traps, sector references. "
                     "Always selected.",
                "2": "account context — profile, scope, coverage, reliability. "
                     "Always selected.",
                "3": "account analysis — one document per theme, overview and canonical "
                     "metrics. Always selected.",
                "4": "bulk annex (9x) — inventories only, no analysis. Select for "
                     "counting and debugging, deselect for strategy and for the Audio "
                     "Overview.",
                "9": "outside the tiers — the delivered report, converted to markdown. "
                     "The only source carrying verdicts and recommendations. Deselect "
                     "for analytical questions.",
            },
            "sources": [
                {"file": d.name, "title": d.title, "tier": d.tier,
                 "words": d.words, "verbatim": d.verbatim,
                 "pii_masked": d.masked}
                for d in self.docs
            ],
            "scrub": {
                "patterns": ["email (embedded)", "phone (E.164-prefixed)"],
                "shared_with": "analyze_tagging_plan.redact_sample",
                "total_masked": sum(d.masked for d in self.docs),
                "identifier_keys_excluded": list(IDENTIFIER_KEYS),
                "note": ("Individual identifiers are excluded by field selection, not "
                         "by masking: no emitter reads them. Masking is the backstop "
                         "for personal data embedded in free text, notably the "
                         "unredacted addresses R9 leaves in audit.json."),
            },
            "annexes_not_sources": [
                {"file": name, "note": note} for name, _text, note in self.extras
            ],
            "metrics_published": sorted(self.metrics_published),
            "metrics_documented": sorted(self.metrics_documented),
            "notes": self.notes,
        }
        with open(os.path.join(self.out_dir, "manifest.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(manifest, fh, ensure_ascii=False, indent=2)
        return manifest


# --------------------------------------------------------------------------- #
# Verification
# --------------------------------------------------------------------------- #
def longest_table(body):
    """Body rows of the longest uninterrupted markdown table segment in a document.

    Long tables are fine; long tables whose header is 400 rows behind the row being read
    are not. `data_table` cuts them into header-bearing segments, and this counts what
    actually shipped rather than trusting the emitter to have gone through it.
    """
    longest = run = 0
    for line in body.splitlines():
        if line.startswith("|"):
            run += 1
            longest = max(longest, run)
        else:
            run = 0
    # header + separator are not data rows
    return max(0, longest - 2)


def verify(pack, expected_tier1=()):
    """Block delivery on anything that would mislead the notebook. Returns failures."""
    fails, warns = [], []

    if not pack.docs:
        return ["no document was emitted at all"], warns
    if len(pack.docs) > SOURCE_CAP:
        fails.append(f"{len(pack.docs)} documents exceeds the {SOURCE_CAP}-source cap")

    for doc in pack.docs:
        path = os.path.join(pack.out_dir, doc.name)
        size = os.path.getsize(path) if os.path.isfile(path) else 0
        if size == 0:
            fails.append(f"{doc.name}: written empty")
        if doc.words > WORD_CAP:
            fails.append(f"{doc.name}: {doc.words:,} words exceeds the {WORD_CAP:,} cap")
        if size > BYTE_CAP:
            fails.append(f"{doc.name}: {size} bytes exceeds the 200 MB cap")

        # Residual PII. When samples are included the pack is for a private internal
        # notebook and personal values are load-bearing, so this check is skipped.
        # With `--no-samples`, a hit after `redact_text` means a pattern the shared
        # regexes do not cover.
        if not pack.include_samples:
            for rx, what in ((_EMAIL_IN_RE, "an email address"),
                             (_PHONE_IN_RE, "a phone number")):
                if rx.search(doc.body):
                    fails.append(f"{doc.name}: {what} survived the scrub")

        # Individual identifiers, on generated documents only: tier-1 verbatim material
        # is API documentation and names these fields on purpose. Skipped when samples
        # are in, because a sample column or an attribute key can legitimately name them.
        if not pack.include_samples and doc.tier in (2, 3, 4):
            for key in IDENTIFIER_KEYS:
                if re.search(rf"\b{re.escape(key)}\b", doc.body):
                    fails.append(f"{doc.name}: emits the identifier field '{key}'")

        # Segmentation, on generated documents only: the vendored reference books carry
        # long tables of their own and are shipped as their authors wrote them.
        if not doc.verbatim:
            rows = longest_table(doc.body)
            if rows > ROWS_PER_SEGMENT:
                fails.append(f"{doc.name}: a table segment carries {rows} rows (> "
                             f"{ROWS_PER_SEGMENT}); build it with data_table so the "
                             f"header repeats")

    # An annex that shipped inside its analysis document instead of beside it would
    # silently remove the deselect-for-strategy affordance the split exists for.
    heavy = [d for d in pack.docs
             if d.tier == 3 and longest_table(d.body) > 0 and d.words > 12_000]
    for doc in heavy:
        warns.append(f"{doc.name}: {doc.words:,} words in a tier-3 analysis document; "
                     f"its bulk tables were expected to move to a 9x annex")

    names = {d.name for d in pack.docs}
    for want in expected_tier1:
        if want not in names:
            fails.append(f"tier 1 incomplete: {want} is missing")

    orphans = pack.metrics_published - pack.metrics_documented
    if orphans:
        fails.append("metrics published with no fiche in tier 1 (a figure without its "
                     f"definition is a figure read wrong): {', '.join(sorted(orphans))}")

    manifest = load_json(os.path.join(pack.out_dir, "manifest.json")) or {}
    listed = {s["file"] for s in manifest.get("sources", [])}
    if listed != names:
        fails.append(f"manifest and disk disagree: {sorted(names ^ listed)}")

    return fails, warns


# --------------------------------------------------------------------------- #
# Delivery
# --------------------------------------------------------------------------- #
def delivery_dirname(client, day=None):
    """``<Client>_Source_Pack_<YYYY-MM-DD>`` — the report's convention, as a folder."""
    slug = re.sub(r"\W+", "_", str(client or "Client"), flags=re.UNICODE).strip("_")
    return f"{slug or 'Client'}_Source_Pack_{day or _dt.date.today().isoformat()}"


def deliver(pack, dest_dir=DOWNLOADS):
    """Copy the whole pack next to the reports. Never raises: `work/` stays canonical."""
    try:
        dest = os.path.join(dest_dir, delivery_dirname(pack.client))
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        shutil.copytree(pack.out_dir, dest)
        print(f"[deliver] {dest}")
        return dest
    except OSError as exc:
        print(f"[deliver] WARNING: could not copy to {dest_dir} ({exc})")
        return None


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #
def window_range(found_data):
    """The analysed window as `(start, end)`, or None.

    Used to slice the daily series: the collector pulls current and prior in one request,
    so a file read whole covers twice the period the pack claims to describe.
    """
    man = found_data.get("collect_manifest") or {}
    win = (man.get("window") or {}).get("current")
    if isinstance(win, (list, tuple)) and len(win) >= 2 and win[0] and win[1]:
        return (str(win[0]), str(win[1]))
    fw = (found_data.get("facts") or {}).get("window") or {}
    if fw.get("start") and fw.get("end"):
        return (str(fw["start"]), str(fw["end"]))
    return None


def window_label(found_data):
    """State the window the way the account's own manifest states it."""
    rng = window_range(found_data)
    return f"{rng[0]} → {rng[1]}" if rng else None


def build(work_dir, client, vertical=None, lang="fr", out_dir=None, deliver_copy=True,
          include_samples=True, retire_raw=False):
    """Discover, emit, scrub, verify, deliver. Returns (pack, failures)."""
    import report_markdown
    import source_pack_corpus as corpus
    import source_pack_docs as docs

    docs.set_lang(lang)
    disc = discover(work_dir)
    out_dir = out_dir or os.path.join(disc["root"], "source_pack")
    vertical = vertical or docs.resolve_account_vertical(disc)
    pack = Pack(out_dir, client, lang=lang,
                window=window_label(disc["data"]),
                window_range=window_range(disc["data"]), vertical=vertical,
                include_samples=include_samples)

    print(f"[pack] {len(disc['found'])} inputs found, {len(disc['missing'])} absent")

    # Tier 3 first: it decides which metrics need a fiche, and tier 1 has to cover them.
    docs.emit_context(pack, disc)
    docs.emit_activity(pack, disc)
    docs.emit_data(pack, disc)
    corpus.emit_corpus(pack, disc, vertical=vertical)
    # Last, and outside the tier scheme: the only source that concludes. It goes through
    # `pack.add` like the rest, which is what scrubs it — the first account this ran on
    # carried consumer email addresses into the report via the tagging plan's samples.
    report_markdown.emit_report(pack, disc)
    docs.emit_readme(pack, disc)

    pack.docs.sort(key=lambda d: d.name)
    pack.write()
    fails, warns = verify(
        pack,
        expected_tier1=tuple(pack.source_name(name) for name in corpus.TIER1_FILES),
    )

    for w in warns:
        print(f"[warn] {w}")
    if fails:
        print(f"\n[gate] FAIL — {len(fails)} problem(s):")
        for f in fails:
            print(f"  - {f}")
        return pack, fails

    print(f"\n[gate] PASS — {len(pack.docs)} sources, "
          f"{sum(d.words for d in pack.docs):,} words, "
          f"{sum(d.masked for d in pack.docs)} personal value(s) masked")
    print(f"[pack] {pack.out_dir}")
    if deliver_copy:
        deliver(pack)
    _retire_raw(disc["root"], retire_raw)
    return pack, []


def _retire_raw(root, retire):
    """Retire the raw pulls, on request only.

    The report builder will not touch them once a pack is in the picture, because the
    pack reads them. But retiring them here by default is wrong too: a pack gets rebuilt
    more often than a report does — after the report markdown is added to it, after a
    `--refresh`, to produce a second language — and each rebuild reads the same pulls.
    Two builds of the same pack in one run is the normal case, not the exception. So
    retirement is an explicit end-of-run step, and `purge_work.py`'s 30-day net remains
    the backstop for a run that never announced it was finished.
    """
    if not retire:
        print("[retention] raw pulls kept: a pack is often rebuilt (report markdown "
              "added, --refresh, second language). Retire them with --retire-raw when "
              "the run is finished")
        return
    pending = os.path.join(root, ".source-pack-pending")
    if os.path.exists(pending):
        try:
            os.remove(pending)
        except OSError:
            pass
    try:
        import purge_work as pwk
        freed = pwk.reduce_raw(root)
    except Exception as exc:                  # noqa: BLE001 — never fail a written pack
        print(f"[retention] WARNING: could not reduce raw pulls ({exc})")
        return
    if freed:
        print(f"[retention] dropped {freed / 1048576:.1f} MB of raw pulls now the run "
              f"is finished")


# --------------------------------------------------------------------------- #
# Self-test
# --------------------------------------------------------------------------- #
def _selftest():
    """Build a whole pack from a fabricated account, offline.

    Pins the two properties that cannot be eyeballed on a real run: that a pack with
    almost no inputs still builds and passes, and that personal data embedded in a
    message body does not reach the output.
    """
    import tempfile

    def check(cond, label):
        print(f"  {'ok  ' if cond else 'FAIL'} {label}")
        if not cond:
            raise AssertionError(label)

    root = tempfile.mkdtemp(prefix="sourcepack_")
    data = os.path.join(root, "data")
    os.makedirs(data)

    def put(name, obj, sub=True):
        with open(os.path.join(data if sub else root, name), "w",
                  encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False)

    put("collect_manifest.json", {
        "project": "DEMO PROD", "region": "eu",
        "window": {"current": ["2026-06-01", "2026-06-30"],
                   "prior": ["2026-05-02", "2026-05-31"], "days": 30},
        "shape": "dashboard",
        "stages": {"core": {"rows": {"sends": 30}, "pages": 2},
                   "events": {"rows": 12, "pages": 1}},
        "totals": {"api_calls": 41, "elapsed_s": 12.5}})
    put("probe.json", {"shape": "dashboard", "sampled_pushes": 20,
                       "mean_sends_per_push": 1200.0, "pushes_per_day_exact": True,
                       "shape_reason": "responses/list is enumerable"})
    put("devices.json", {"counts": {
        "ios": {"opted_in": 1000, "opted_out": 400, "uninstalled": 20},
        "android": {"opted_in": 2000, "opted_out": 900, "uninstalled": 50},
        "email": {"opted_in": 0}}, "total_unique_devices": 4370})
    # Current AND prior in one file, which is what `collect.py` actually writes: it pulls
    # a doubled window and lets `analyze.py` slice it. Reading the file whole made every
    # local total cover two periods, so the fixture carries both windows on purpose.
    put("sends.json", {"sends": [
        {"date": f"2026-05-{d:02d}", "ios": 999 * d, "android": 999 * d, "email": 99}
        for d in range(2, 32)] + [
        {"date": f"2026-06-{d:02d}", "ios": 100 * d, "android": 200 * d, "email": 10}
        for d in range(1, 31)]})
    put("opens.json", {"opens": [
        {"date": f"2026-05-{d:02d}", "ios": 999 * d, "android": 999 * d}
        for d in range(2, 32)] + [
        {"date": f"2026-06-{d:02d}", "ios": 10 * d, "android": 20 * d}
        for d in range(1, 31)]})
    put("optins.json", {"optins": [{"date": "2026-06-01", "ios": 12, "android": 30}]})
    put("optouts.json", {"optouts": [{"date": "2026-06-01", "ios": 3, "android": 9}]})
    # `/api/reports/events` is a FLAT aggregate: one row per
    # (name x conversion x location), `conversion` being a scalar label. An earlier
    # version of this fixture nested the split in a dict, `event_analysis` raised on it,
    # and the events document silently degraded to a note — which is why the assertions
    # below check the document exists rather than only that the build passed.
    put("events.json", {"events": [
        {"name": "purchase_confirmed", "location": "custom", "conversion": "direct",
         "count": 100, "value": 5200.0},
        {"name": "purchase_confirmed", "location": "custom", "conversion": "indirect",
         "count": 200, "value": 9800.0},
        {"name": "purchase_confirmed", "location": "custom",
         "conversion": "unattributed", "count": 600, "value": 30000.0},
        {"name": "add_to_cart", "location": "custom", "conversion": "unattributed",
         "count": 4000, "value": 0},
        {"name": "banner - promo", "location": "custom", "conversion": "unattributed",
         "count": 8000, "value": 0},
        {"name": "button-click-Je m'inscris", "location": "in_app_message",
         "conversion": "unattributed", "count": 64, "value": 0}]})
    put("responses.json", {"pushes": [
        {"push_uuid": "u1", "push_time": "2026-06-03T10:00:00", "sends": 300000,
         "direct_responses": 6000, "group_id": None},
        {"push_uuid": "u2", "push_time": "2026-06-10T10:00:00", "sends": 120000,
         "direct_responses": 1500, "group_id": "g1"},
        {"push_uuid": "u3", "push_time": "2026-06-17T10:00:00", "sends": 118000,
         "direct_responses": 1400, "group_id": "g1"}]})
    put("activity.json", {"activity": []})
    # A body carrying a real-looking address: the scrub has to catch it.
    put("decoded.json", {
        "u1": {"decodable": True, "message_name": "Soldes -30%",
               "title": "Soldes", "body": "Contactez nous a jean.dupont@example.net",
               "media": "https://img.example/x.jpg", "deeplink": "uairship://deep",
               "personalization": True, "has_message_center": False},
        "u2": {"decodable": True, "message_name": "Panier abandonne",
               "title": "Votre panier", "body": "Il vous attend",
               "personalization": False, "has_message_center": True}})

    # A minimal interactive report: one section, one KPI with the method block the
    # browser hides in a <template>, one chart carrying its spec, and an address in an
    # appendix cell. The address is the point — it is how the leak happened on the first
    # real account, through the tagging plan's sample values rather than a push body,
    # and `pack.add` is what has to catch it.
    with open(os.path.join(root, "report.html"), "w", encoding="utf-8") as fh:
        fh.write("""<!doctype html><html><body><div id="ir-main">
<section class="page" data-toc="3. Executive summary" data-toc-fr="3. Synthèse"
         id="summary"><h2>3. Synthèse</h2>
<div class="note">Verdict. La pression a doublé sans gain d'engagement.</div>
<div class="ir-hero-card"><div class="ir-hero-head"><div class="ir-hero-val">26,8 %</div>
<button class="ir-kpi-info">i</button>
<template id="m1"><div class="ir-method"><div class="ir-method-row">
<span class="ir-method-k">Formule</span><span class="ir-method-v"><code>a / b</code>
</span></div><div class="ir-method-row"><span class="ir-method-k">Confiance</span>
<span class="ir-method-v"><span class="pill pill-good">Élevée</span></span></div>
</div></template></div>
<div class="ir-hero-label">Taux d'opt-in</div></div>
<figure class="ir-chart" id="fig-sends_daily_fr"><img class="ir-chart-static" src="x">
<canvas class="ir-chart-live"></canvas>
<script type="application/json" class="ir-chart-spec">{"type":"bar","data":
{"labels":["iOS","Android"],"datasets":[{"label":"Sends","data":[10,20]}]}}</script>
</figure>
<table class="grid"><thead><tr><th>Attribut</th><th>Exemples</th></tr></thead>
<tbody><tr><td><code>email</code></td><td>marie.martin@example.org</td></tr></tbody>
</table></section></div></body></html>""")

    pack, fails = build(root, "Demo Brand", vertical="retail", lang="fr",
                        deliver_copy=False)
    check(not fails, "a fabricated account builds and passes the gate")
    check(not pack.notes, f"no emitter degraded silently ({pack.notes})")

    # Named explicitly, because an emitter that raises is caught and demoted to a note:
    # only naming the documents turns a broken reuse into a failing test.
    names = {d.name for d in pack.docs}
    for want in ("10_profil_du_compte.md", "11_perimetre_et_couverture.md",
                 "20_audience_et_permission.md", "21_volume_et_pression.md",
                 "22_inventaire_campagnes.md", "24_creatives_decodees.md",
                 "25_evenements_custom.md", "27_benchmarks_secteur.md"):
        check(want in names, f"{want} was emitted")
    check("series_daily.csv" in {n for n, _t, _note in pack.extras},
          "the spreadsheet annex was written and declared a non-source")

    # The report is a source like any other in how it is produced, and unlike any other
    # in what it carries. Both halves are pinned: that it converts at all, and that it
    # arrives outside the tier scheme so the reader can drop it in one click.
    report = next((d for d in pack.docs if d.name == "99_rapport_engagement.md"), None)
    check(report is not None, "the delivered report was emitted as source 99")
    check(report.tier == 9, f"the report sits outside the tiers (tier={report.tier})")
    check("Verdict." in report.body, "the report's verdicts survived the conversion")
    check("`a / b`" in report.body,
          "a KPI's method block, hidden in a <template>, survived")
    check("| iOS | 10 |" in report.body,
          "a chart became the table of values it was drawn from")

    blob = "\n".join(d.body for d in pack.docs)
    check("jean.dupont@example.net" in blob,
          "an internal pack keeps a personal sample from a push body")
    check("marie.martin@example.org" in blob,
          "an internal pack keeps a personal sample from the report appendix")

    redacted, redacted_fails = build(
        root, "Demo Brand", vertical="retail", lang="fr",
        out_dir=os.path.join(root, "source_pack_redacted"),
        deliver_copy=False, include_samples=False)
    check(not redacted_fails, "a redacted pack still builds")
    redacted_blob = "\n".join(d.body for d in redacted.docs)
    check("jean.dupont@example.net" not in redacted_blob,
          "`--no-samples` still strips an address inside a push body")
    check("marie.martin@example.org" not in redacted_blob,
          "`--no-samples` still strips an address inside the report appendix")
    check(_REDACTED["email"] in redacted_blob, "the mask names what it removed")
    check(sum(d.masked for d in redacted.docs) >= 1, "the manifest counts the masking")

    tiers = {d.tier for d in pack.docs}
    check(tiers >= {1, 2, 3, 4, 9},
          f"the tier structure is complete ({sorted(tiers)})")
    check(not (pack.metrics_published - pack.metrics_documented),
          "every published metric carries a fiche")


    # The window slice. `sends.json` holds both windows, so the June-only iOS total is
    # 100 x (1+...+30) = 46,500 and the unsliced read gives 542,985. The wrong figure is
    # not absurd on its face — that is the point of pinning it: it shipped for a while,
    # and it poisoned the pressure table downstream, where it read as a plausible-looking
    # cadence that happened to be double the truth.
    by_name = {d.name: d for d in pack.docs}
    # Compared on digits alone: the emitters group thousands with a narrow no-break space,
    # and asserting on the rendered form would pin the typography rather than the figure.
    volume_digits = re.sub(r"\D", "", by_name["21_volume_et_pression.md"].body)
    check("46500" in volume_digits,
          "daily series are summed over the analysed window only")
    check("542985" not in volume_digits,
          "and the prior window is not folded into the period's total")

    # The A/B split. A bulk inventory has to leave its analysis document for a 9x source,
    # because being a SEPARATE source is the whole affordance: it is what lets the reader
    # deselect three thousand inventory rows when asking a strategy question. If the
    # tables silently came back inline the pack would still build and still be correct,
    # and the affordance would be gone — so it is asserted rather than observed.
    series = by_name.get("94_annexe_series_quotidiennes.md")
    check(series is not None and series.tier == 4,
          "60 rows of daily series moved to a tier-4 annex")
    volume = by_name["21_volume_et_pression.md"]
    check("94_annexe_series_quotidiennes.md" in volume.body,
          "the analysis document points at its annex")
    check("2026-06-17 " not in volume.body and "| 2026-06-17 |" not in volume.body,
          "and no longer carries the rows itself")

    # The mirror case: a short inventory must NOT be exiled. Three campaigns split into
    # their own source would cost a click and buy nothing.
    check("90_annexe_inventaire_campagnes.md" not in by_name,
          "a three-row inventory stays inline")
    check("soldes 30" in by_name["22_inventaire_campagnes.md"].body,
          "and its rows are in the analysis document")

    # Every vertical of the benchmark book ships, not only the account's. Comparing the
    # account to a neighbouring sector is a question the pack should be able to answer.
    bench = by_name.get("96_annexe_benchmarks_tous_verticaux.md")
    check(bench is not None, "the other benchmark verticals ship as an annex")
    check("`retail`" in by_name["27_benchmarks_secteur.md"].body,
          "with the account's own vertical kept in the analysis document")
    check("media" in bench.body,
          "and a vertical that is not the account's is available to compare against")

    check(max(longest_table(d.body) for d in pack.docs if not d.verbatim)
          <= ROWS_PER_SEGMENT,
          "no generated table segment runs past its header")

    # `--lang en` has to produce an English document, not English paragraphs under
    # French headings: a half-translated definitions pack is worse than a single-language
    # one. Every structural label goes through `source_pack_docs.L`, which records what
    # it could not translate, so the flag cannot quietly start lying again.
    import source_pack_docs as docs
    en_pack, en_fails = build(root, "Demo Brand", vertical="retail", lang="en",
                              out_dir=os.path.join(root, "source_pack_en"),
                              deliver_copy=False)
    check(not en_fails, "the same account builds in English")
    check(not docs.LABEL_MISSES,
          f"every structural label has an English form (missing: "
          f"{sorted(docs.LABEL_MISSES)[:6]})")
    en_names = {d.name for d in en_pack.docs}
    for canonical, english in EN_SOURCE_NAMES.items():
        if canonical == english:
            continue
        if canonical in names:
            check(english in en_names,
                  f"the English pack translated {canonical} to {english}")
            check(canonical not in en_names,
                  f"the English pack did not retain the French filename {canonical}")
    en_blob = "\n".join(d.body for d in en_pack.docs if not d.verbatim)
    for canonical, english in EN_SOURCE_NAMES.items():
        if canonical != english:
            check(canonical not in en_blob,
                  f"English documents do not link to the French filename {canonical}")
    for hybrid in ("_annexe_", "_rapport_", "_profil_du_", "_perimetre_",
                   "_evenements_", "_campagnes_", "_quotidiennes"):
        check(hybrid not in en_blob,
              f"English documents contain no partially translated filename ({hybrid})")
    en_readme = next(d for d in en_pack.docs if d.name == "00_README_pack.md")
    readme_refs = set(re.findall(r"`([^`*]+\.md)`", en_readme.body))
    check(not (readme_refs - en_names),
          f"every exact .md reference in the English README exists "
          f"({sorted(readme_refs - en_names)})")
    for stray in ("## Canaux", "| Plateforme |", "| Envois |", " oui |"):
        check(stray not in en_blob, f"no French label left in the English pack ({stray})")

    # A pack with nothing but a device snapshot: the honest-degradation path.
    bare = tempfile.mkdtemp(prefix="sourcepack_bare_")
    os.makedirs(os.path.join(bare, "data"))
    with open(os.path.join(bare, "data", "devices.json"), "w", encoding="utf-8") as fh:
        json.dump({"counts": {"ios": {"opted_in": 5}}}, fh)
    bare_pack, bare_fails = build(bare, "Bare", lang="fr", deliver_copy=False)
    check(not bare_fails, "an almost-empty account still produces a valid pack")
    check(any(d.tier == 1 for d in bare_pack.docs),
          "tier 1 ships even when the account data does not")

    shutil.rmtree(root, ignore_errors=True)
    shutil.rmtree(bare, ignore_errors=True)
    print("build_source_pack self-test OK")
    return 0


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(
        description="Build a NotebookLM source library for one Airship account.")
    ap.add_argument("work_dir", nargs="?", help="work/<client> directory")
    ap.add_argument("--client", help="brand name, as it should read in the documents")
    ap.add_argument("--vertical", help="benchmark vertical (resolved from the run "
                                       "when omitted)")
    ap.add_argument("--lang", choices=("fr", "en"), default="fr",
                    help="language of generated documents and source filenames; the "
                         "tier-1 corpus body is vendored verbatim and stays in English")
    ap.add_argument("--out", help="output directory (default work/<client>/source_pack)")
    ap.add_argument("--no-deliver", action="store_true",
                    help="skip the copy to ~/Downloads")
    ap.add_argument("--no-samples", action="store_true",
                    help="omit tagging-plan sample values and redact emails/phones "
                         "(default is to keep them: the pack is for a private "
                         "internal notebook)")
    ap.add_argument("--retire-raw", action="store_true",
                    help="drop the raw API pulls under data/ once the pack is written. "
                         "The report builder will not do it while a pack exists, since "
                         "the pack reads them; pass this on the LAST build of the run")
    ap.add_argument("--selftest", action="store_true", help="offline self-test")
    args = ap.parse_args()

    if args.selftest:
        return _selftest()
    if not args.work_dir:
        ap.error("work_dir is required (or use --selftest)")
    if not os.path.isdir(args.work_dir):
        ap.error(f"{args.work_dir} is not a directory")

    client = args.client or os.path.basename(os.path.abspath(args.work_dir))
    _pack, fails = build(args.work_dir, client, vertical=args.vertical,
                         lang=args.lang, out_dir=args.out,
                         deliver_copy=not args.no_deliver,
                         include_samples=not args.no_samples,
                         retire_raw=args.retire_raw)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
