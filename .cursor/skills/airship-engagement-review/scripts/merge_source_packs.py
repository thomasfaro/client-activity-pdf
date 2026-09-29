#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Merge several NotebookLM source packs into one library.

Usage:
    python merge_source_packs.py [--out OUT] [--no-deliver] pack_dir [pack_dir ...]

A brand that runs two or more apps gets one engagement review per app, and therefore
one source pack per app. Uploading them as separate notebooks makes the cross-app
question — the one the brand actually asks — impossible to put to the model. This
script folds them into a single library.

Two rules do the work:

* The tier-1 semantic sources (endpoints, definitions, metric reference, traps,
  benchmark reading, business reference) are account-independent: `build_source_pack.py`
  emits them identically apart from one header line naming the account. Uploading the
  same 80,000-word reference twice would halve retrieval precision for no gain, so a
  file whose content matches across every pack once that header is normalised is
  emitted **once**, with the header rewritten to name all the accounts. A file that
  genuinely differs is kept per account, like everything else.

* Every account-specific source keeps its numeric prefix and gains the account name:
  `21_volume_and_pressure.md` becomes `21_volume_and_pressure_<Account>.md`. The prefix
  survives so the same theme from each account sorts adjacently in the source list,
  which is what makes a comparison prompt cheap to write.

The merged `manifest.json` records which account each source belongs to and keeps every
per-pack manifest verbatim under `packs`, so nothing is lost in the fold.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import shutil
import sys

# Line 4 of every generated source, e.g. "> **account:** Foo · **window:** a → b".
HEADER_RE = re.compile(r"^> \*\*account:\*\* .*$", re.M)
SHARED_TIER = 1


def slug(name: str) -> str:
    """Filename-safe account token that stays readable in a source list."""
    return re.sub(r"[^\w.-]+", "_", name.strip()).strip("_")


def read_pack(d: pathlib.Path) -> dict:
    man = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    man["_dir"] = d
    return man


def merge(packs: list[pathlib.Path], out: pathlib.Path) -> dict:
    mans = [read_pack(p) for p in packs]
    clients = [m.get("client") or m["_dir"].name for m in mans]
    if len(set(clients)) != len(clients):
        sys.exit(f"[merge] two packs report the same account: {clients}")

    joint = " \u00b7 ".join(clients)
    header = f"> **accounts:** {joint} \u00b7 "
    # Rebuild the window clause from the first pack; every pack in a brand review runs
    # the same window, and a merged library that claims otherwise would be misleading.
    windows = {m.get("window") for m in mans}
    if len(windows) > 1:
        print(f"[merge] ! packs cover different windows: {sorted(windows)}")
    header += f"**window:** {mans[0].get('window')}  "

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    # ---- decide which files are genuinely shared -------------------------
    by_file: dict[str, list[tuple[dict, dict]]] = {}
    for m in mans:
        for src in m["sources"]:
            by_file.setdefault(src["file"], []).append((m, src))

    shared, per_account = [], []
    for fname, entries in by_file.items():
        tiers = {e[1].get("tier") for e in entries}
        if len(entries) == len(mans) and tiers == {SHARED_TIER}:
            bodies = {HEADER_RE.sub("", (m["_dir"] / fname).read_text(encoding="utf-8"))
                      for m, _ in entries}
            # The README names its account in prose, so it never matches byte for byte.
            # Two copies of the reading instructions would be worse than one rewritten.
            if len(bodies) == 1 or fname.startswith("00_"):
                shared.append((fname, entries))
                continue
        per_account.extend(entries and [(fname, m, s) for m, s in entries])

    sources: list[dict] = []

    for fname, entries in sorted(shared):
        m, src = entries[0]
        body = (m["_dir"] / fname).read_text(encoding="utf-8")
        body = HEADER_RE.sub(header.rstrip() + "  ", body, count=1)
        if fname.startswith("00_"):
            body = rewrite_readme(body, clients)
        (out / fname).write_text(body, encoding="utf-8")
        row = dict(src)
        row["accounts"] = clients
        sources.append(row)

    for fname, m, src in sorted(per_account, key=lambda t: (t[0], t[1].get("client"))):
        client = m.get("client") or m["_dir"].name
        stem, dot, ext = fname.rpartition(".")
        target = f"{stem}_{slug(client)}{dot}{ext}"
        shutil.copy2(m["_dir"] / fname, out / target)
        row = dict(src)
        row["file"], row["account"] = target, client
        row["title"] = f"{src.get('title', stem)} \u2014 {client}"
        sources.append(row)

    # ---- non-source companions (series CSVs and the like) ----------------
    listed = {f for f in by_file}
    for m in mans:
        client = m.get("client") or m["_dir"].name
        for f in sorted(m["_dir"].iterdir()):
            if f.name in listed or f.name == "manifest.json" or f.is_dir():
                continue
            stem, dot, ext = f.name.rpartition(".")
            shutil.copy2(f, out / f"{stem}_{slug(client)}{dot}{ext}")

    manifest = {
        "generated": mans[0].get("generated"),
        "clients": clients,
        "window": mans[0].get("window"),
        "lang": mans[0].get("lang"),
        "target": mans[0].get("target"),
        "merged_from": [str(m["_dir"]) for m in mans],
        "tiers": mans[0].get("tiers"),
        "shared_sources": [f for f, _ in sorted(shared)],
        "sources": sources,
        "packs": [{k: v for k, v in m.items() if k != "_dir"} for m in mans],
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def rewrite_readme(body: str, clients: list[str]) -> str:
    """Say, in the one source a reader opens first, that this library holds two accounts."""
    names = " and ".join(f"**{c}**" for c in clients)
    body = re.sub(r"Source library for \*\*[^*]+\*\*", f"Source library for {names}",
                  body, count=1)
    if len(clients) > 1:
        body = body.replace("the account\u2019s data", "each account\u2019s data", 1)
        body = body.replace("the account's data", "each account's data", 1)
    note = (
        f"\n## {len(clients)} accounts in one library\n\n"
        f"This library merges the source packs of {names}, so that a single notebook can "
        f"answer a question about either account and, more usefully, about the "
        f"difference between them.\n\n"
        f"- Sources numbered `00` to `06` are **shared**: they define the API, the "
        f"metrics and the traps, and say the same thing whichever account is being read. "
        f"There is one copy of each.\n"
        f"- Every other source is **per account** and carries the account name at the end "
        f"of its filename, after the numeric prefix it had in the single-account pack. "
        f"The prefix is preserved so the same theme from each account sits next to its "
        f"counterpart in the source list: to compare volume across the two apps, select "
        f"the two `21_` sources and nothing else.\n"
        f"- The rule about verdicts is unchanged and now applies twice over: only the "
        f"`99` sources carry conclusions, one per account. Deselect both to interrogate "
        f"the data without being led by the report's reading of it.\n\n"
        f"When a question is about one account, say which one in the prompt: the sources "
        f"are explicit about their account in their header, but a question that names "
        f"neither will be answered from both.\n")
    marker = "\n## What is not in this pack"
    return body.replace(marker, note + marker, 1) if marker in body else body + note


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("packs", nargs="+", type=pathlib.Path)
    ap.add_argument("--out", type=pathlib.Path,
                    help="output directory (default: alongside the first pack)")
    ap.add_argument("--label", help="name of the merged directory when --out is omitted")
    args = ap.parse_args()

    for p in args.packs:
        if not (p / "manifest.json").exists():
            sys.exit(f"[merge] not a source pack: {p}")
    if len(args.packs) < 2:
        sys.exit("[merge] give at least two packs")

    out = args.out or args.packs[0].parent / (args.label or "Merged_Source_Pack")
    man = merge([p.resolve() for p in args.packs], out.resolve())
    n_shared = len(man["shared_sources"])
    print(f"[merge] {len(man['clients'])} accounts, {len(man['sources'])} sources "
          f"({n_shared} shared, {len(man['sources']) - n_shared} per account)")
    print(f"[merge] {out}")


if __name__ == "__main__":
    main()
