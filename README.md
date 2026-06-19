# Airship Engagement Review — Cursor Skill

A Cursor Agent Skill that generates an exhaustive, client-ready **mobile activity &
engagement review** from an Airship project's Reports API data, output as a shareable
**PDF + PNG**. Default branding is Airship; report language defaults to English (French
on request).

The skill lives in [`.cursor/skills/airship-engagement-review/`](.cursor/skills/airship-engagement-review/):

- `SKILL.md` — the method (workflow, report structure, quality gate).
- `reference.md` — Airship Reports API endpoints, definitions, branding, page rules.
- `scripts/` — reusable helpers:
  - `airship_charts.py` — branded matplotlib chart functions.
  - `render_mocks.py` — push / Message Center / in-app creative mockups (Chrome headless).
  - `build_report.py` — HTML → PDF (Chrome) → stitched PNG (PyMuPDF), with page-count check.

## Use it

Two ways:

1. **Open this repo as your Cursor workspace.** The skill auto-loads from `.cursor/skills/`.
   No install needed. Then ask, e.g. *"generate an Airship engagement review for HM PROD"*.

2. **Install globally** (available in all your projects) by symlinking it into
   `~/.cursor/skills/`:

   ```bash
   ./install.sh            # symlink (live updates from this repo)
   ./install.sh --copy     # copy instead of symlink
   ./install.sh --uninstall
   ```

   Restart/reload Cursor so it picks up `~/.cursor/skills/`.

## Requirements

- Python: `matplotlib`, `numpy`, `pillow`, `pymupdf`
- Google Chrome (headless) for HTML→PDF and mockup rendering
- Access to the target project's Airship Reports API via its MCP server

## Sharing internally

Skills are just files, distributed via git — there is no separate org-level skill
registry. Clone this repo and use either method above. Pull to get updates.
