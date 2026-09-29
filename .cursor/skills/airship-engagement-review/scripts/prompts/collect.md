Run, from the repo root, and report the tail of the output plus the contents of
work/{{client}}/data/collect_manifest.json:

python .cursor/skills/airship-engagement-review/scripts/collect.py "{{project}}" \
  --start {{start}} --end {{end}} --out work/{{client}}/data {{shape_arg}}

Do not edit any file. If a stage reports status FAILED, say which and stop.
If a stage reports status `partial`, report its `truncated` list verbatim — it hit the
soft per-stage deadline and wrote what it had rather than being killed. Do NOT re-run it
with a bigger deadline on your own initiative; partial-but-stated is a valid outcome.
Also report `probe.json`'s `shape_reason`: on a firehose it says whether the grouped/
groupless call was made on push share, sends share or confirmed programme volume, and
that call is the difference between ~2 000 and ~76 000 API calls.

(The orchestrator runs this step itself as a subprocess; this prompt is for the manual path,
delegated to the `airship-shell` agent.)
