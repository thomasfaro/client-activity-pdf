# Client data handling and checking the skill itself

Part of the [airship-engagement-review skill](SKILL.md). Read it when retention, provenance or a change to the skill itself is in question.

## Handling client data

A review pulls a client's real send history onto a laptop and turns it into a document whose
commentary a model drafted. **The report is for internal Airship use**: it prepares the
account team for a conversation and is not sent to the client. That makes the exposure
indirect rather than absent — a figure repeated in a meeting travels just as far — so four
rules follow, and all four are enforced rather than advised.

**The report says how it was produced.** `write_report` injects a provenance footer naming
where the figures came from and which model actually wrote the prose — read from the `stop`
row of `work/<client>/run.md`, so it reports what ran rather than what was asked for.
`verify_report.py` blocks a report that lacks it. This is Airship's own commitment that AI
involvement is marked, and it applies to an internal reader too: the footer is what tells the
account manager which sentences to verify before repeating them.

**Every page is marked internal use.** `assemble()` declares the marking and a `.page` rule
prints it on each page, with a print-only running variant so a sheet pulled out of the PDF
still carries it. The gate blocks a report without it. Page 1 alone was not enough — a chart
pasted into a deck is exactly the page that travels.

**Naming a reviewer is optional.** `Reviewed-by: <name>` in `work/<client>/run.md` is
quoted by the provenance footer when set, but it no longer holds back the copy to
`~/Downloads` — a passing gate is enough to deliver.

**Raw pulls are dropped at delivery; the window is only a net.**

```bash
python scripts/purge_work.py                  # what is past the window (dry run)
python scripts/purge_work.py --apply          # reduce those accounts
python scripts/purge_work.py --purge-all --apply   # drop accounts idle for the whole window
python work/<client>/build_report.py --keep-raw    # keep data/ while investigating
```

A successful build now retires `work/<client>/data/` itself, once the gate has passed and the
signed-off copy is in `~/Downloads`: the pull existed to produce the brief and is dead weight
afterwards. The 30-day window stays for accounts whose build never finished. What survives is
what a rebuild opens — `audit.json`, `facts.json`, `specs.json`, `run.md`, `brand.json`, the
tagging plan, `build_report.py`, and `sections/`, `charts/`, `creatives/` — so the report can
be rebuilt in the other language or after a framework fix without calling the API again. Age
is measured **per file**, deliberately: a probe sweep that writes into thirteen accounts must
not extend the retention of the push history underneath it.

**Except when a NotebookLM pack is also a deliverable.** The pack reads the same pulls, and
it is built *after* the report and rebuilt again whenever the report changes — so the builder
stands down whenever `source_pack/` exists or a `.source-pack-pending` marker is present, and
says so. Touch that marker in wave 0 when the pack is on the list. Retirement is then the
explicit last step of the run: `build_source_pack.py --retire-raw`.

## Checking the skill itself (not a client report)

Two tools, and they answer different questions — running one is not a substitute for the
other:

```bash
python scripts/run_selftests.py            # offline, deterministic, ~0.2s, no credentials
python scripts/check_no_client_names.py    # no real account name in a tracked file
python scripts/probe_sweep.py <start> <end> "PROJ A" "PROJ B" … --expect probe_sweep_expected.json
```

- **`run_selftests.py`** — "does the logic still do what it did?" It runs every module's
  `--selftest` (`push_firehose.py` uses a positional `selftest`) over fixtures: the routing
  oracle's `is_floor`, the sends-weighted sample, the per-push call cap, the calendar
  contamination detector, the audit-vs-facts coherence check, and the data-handling rules
  above (what the provenance footer may claim, what the retention window nominates, what
  redaction masks out of a tagging plan). Every case pins a bug that shipped, so a failure
  names a known error returning. Run it after **any** change to `collect.py`,
  `push_firehose.py` or `build_facts.py`.
- **`check_no_client_names.py`** — "is the repository still neutral?" The skill ships
  benchmarks and general practice, never a client. It reads the account list out of
  `~/.cursor/mcp.json`, where every project this machine can reach is declared as
  `<project> <ENV>`, and fails if one of those names appears in a tracked file — so **the
  check is shipped and the names are not**. Run it before committing: naming the account is
  the natural way to write a comment while tuning, and it has drifted back twice. Describe
  the phenomenon instead; the number of accounts and the result are what carry the argument,
  not which ones. Two kinds of name are searched only beside `PROD`/`DEV` or `user-`: ones
  of two or three characters, which match inside base64 by coincidence, and ones that are
  ordinary English words. Both are listed in the output, so the narrower search is visible
  rather than assumed.
- **`probe_sweep.py`** — "do real accounts still route the way we expect?" It calls the live
  Reports API across a dozen projects (~1,000 calls, minutes, needs MCP credentials). No
  fixture can answer this, because the accounts change on their own. Run it after changing a
  routing threshold. Both its files stay local: the sweep output records volumes per named
  account and the expectation file pairs an account with its regime. Copy
  `probe_sweep_expected.example.json` and fill in your own projects.

`facts.json` also gets checked against the audit it came from, which is the one link the
delivery gate used to take on trust:

```bash
python scripts/build_facts.py work/<client>/audit.json --verify
```

`verify_report.py` runs this itself. A contradicted number (`value`, `path`, `dead_source`,
`stale_derived`) **fails** the gate; a merely absent derived block (`missing_derived`,
`resolvable_now`) is an advisory asking for a `build_facts.py` re-run. Watch for
`missing_derived window_contamination` in particular: with no contamination block, the gate's
"contaminated deltas name their cause" check has nothing to enforce and passes vacuously.

Both of those compare two artefacts and ask whether they **agree**. Neither asks whether the
audit is **plausible**, so run the pre-flight too — before charts, sections or the freeze:

```bash
python scripts/verify_audit.py work/<client>/audit.json
```

It costs under a second and catches the class of defect that agreement checks structurally
cannot: a benchmark stored as a median with no band, a volume-weighted block silently zeroed
by a key-name mismatch, marketing pressure computed from all-channel rather than push-only
volume, a run identity that leaves every Flight Deck link absent. Each of those has shipped
to wave 5 at least once. It also writes `audit.contaminated_fields`, the registry of counters
no section may publish as volume, which is why it must run **before** the freeze rather than
beside it. A FAIL is a **stop** — see
[orchestration.md](orchestration.md#the-pre-flight).
