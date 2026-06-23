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

## Install in Cursor

Skills are discovered automatically from `.cursor/skills/` (project) or
`~/.cursor/skills/` (global). There is no separate Skills settings page — installed
skills appear under **Cursor Settings → Rules → Agent Decides**.

### Option A — Open this repo as your workspace (recommended)

Best for running reviews from a dedicated project. No extra install step.

1. In Cursor, open the Command Palette (`Cmd+Shift+P` / `Ctrl+Shift+P`).
2. Run **Git: Clone** and paste:
   ```
   https://github.com/thomasfaro/client-activity-pdf
   ```
3. When prompted, **Open** the cloned folder in Cursor.
4. Verify the skill loaded: **Cursor Settings** (`Cmd+Shift+J` / `Ctrl+Shift+J`) →
   **Rules** → look for `airship-engagement-review` under **Agent Decides**.
5. In Agent chat, ask e.g. *"generate an Airship engagement review for user-XX PROD"*.

The skill auto-loads because this repo already contains `.cursor/skills/airship-engagement-review/`.

### Option B — Use the skill in any existing project (global install)

Keeps the skill available across all your workspaces.

1. Clone this repo anywhere on your machine (Command Palette → **Git: Clone**, or
   Cursor's integrated terminal):
   ```bash
   git clone https://github.com/thomasfaro/client-activity-pdf.git
   cd client-activity-pdf
   ```
2. Run the install script from Cursor's terminal (`Terminal → New Terminal`):
   ```bash
   ./install.sh            # symlink → ~/.cursor/skills/ (live updates on git pull)
   ./install.sh --copy     # copy instead of symlink
   ```
3. Reload Cursor: Command Palette → **Developer: Reload Window**.
4. Verify: **Cursor Settings → Rules → Agent Decides** → `airship-engagement-review`.
5. Open any project and ask the Agent to run a review (you still need the target
   project's Airship MCP server configured locally).

To remove: `./install.sh --uninstall`

### Option C — Add to a specific project only

If you want the skill inside one client repo without a global install:

1. Clone this repo (or add it as a submodule).
2. Copy the skill folder into your project's `.cursor/skills/`:
   ```bash
   mkdir -p .cursor/skills
   cp -R /path/to/client-activity-pdf/.cursor/skills/airship-engagement-review .cursor/skills/
   ```
3. Reload Cursor (**Developer: Reload Window**).
4. Commit `.cursor/skills/airship-engagement-review/` if you want teammates to get it
   when they open that project.

### GitHub import via Settings (experimental)

Cursor documents a GitHub import under **Cursor Settings → Rules → Project Rules →
Add Rule → Remote Rule (GitHub)**. Paste the repo URL:

```
https://github.com/thomasfaro/client-activity-pdf
```

This flow is designed for `.mdc` rules; skill-only repos may not always register
under **Agent Decides**. If the skill does not appear after a reload, use Option A, B,
or C instead.

## Use it

Once installed, invoke the skill from Agent chat:

- Ask naturally: *"generate an Airship engagement review for user-XX PROD"*
- Or reference it with `@airship-engagement-review` (if shown in the `@` menu)
- Or type `/airship-engagement-review` in the chat input

The Agent will pull data from the project's Airship MCP server, generate charts and
mockups, and output a PDF + PNG on your Desktop.

## Configure client projects as MCP servers in Cursor

The skill does **not** embed Airship credentials. Each client Airship project must be
wired as a separate MCP server on your machine.

### Step 1 — OAuth in the Airship dashboard (once per project)

1. Open the client's project in Airship Go.
2. **Settings → Project settings → OAuth** → create or edit a client.
3. Enable **Allow Basic Auth** (required for Client Secret).
4. Enable scopes:
   - **`rpt`** (Reports) — **required** for sends, opens, devices, events, etc.
   - **`tpl`** (Content) — **required** for template/creative inventory.
   - Optional: **`pln`**, **`sch`**, experiments — deeper automation / schedule / A/B sections.
5. Copy **App Key** (Settings → General), **Client ID**, and **Client Secret**.
6. Note the region: **`eu`** or **`us`**.

### Step 2 — Airship MCP runtime

Install the Airship MCP server (`airship-mcp` from the agent-tools package). You need
[`uv`](https://docs.astral.sh/uv/) on your PATH and a local clone of the agent-tools
repo (path used in the config below).

### Step 3 — Cursor MCP config

**Cursor Settings → MCP** (or edit `~/.cursor/mcp.json`). Add **one entry per client**:

```json
{
  "mcpServers": {
    "Carrefour PROD": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/agent-tools", "airship-mcp"],
      "env": {
        "AIRSHIP_APP_KEY": "<app_key>",
        "AIRSHIP_CLIENT_ID": "<oauth_client_id>",
        "AIRSHIP_CLIENT_SECRET": "<oauth_client_secret>",
        "AIRSHIP_REGION": "eu"
      }
    }
  }
}
```

Replace `/path/to/agent-tools` with your local install path. Duplicate the block for
each client (`GMF PROD`, `M6 PROD`, …) with that project's credentials.

Reload Cursor (**Developer: Reload Window**) or restart the MCP row in Settings.

When you ask the Agent for a review, name the server as configured (e.g.
*"engagement review for **Carrefour PROD**"*). Internally Cursor addresses it as
`user-Carrefour PROD`.

### Step 4 — Smoke test

Ask the Agent to call `GET /api/reports/devices` on that MCP server. Expect HTTP 200
with platform opt-in counts. If you see **401 Expired token**, restart the MCP server.
If **401 Missing required scope**, add the scope in Airship OAuth settings and restart
the MCP server.

**Security:** keep `mcp.json` local; never commit credentials to git.

## Requirements

- Python: `matplotlib`, `numpy`, `pillow`, `pymupdf`
- Google Chrome (headless) for HTML→PDF and mockup rendering
- [`uv`](https://docs.astral.sh/uv/) + Airship MCP (`airship-mcp` / agent-tools)
- One Cursor MCP entry per client project (see above)

## Sharing internally

Clone this repo and follow one of the install options above. Pull to get updates.
For team-wide use inside a client project, prefer **Option C** (commit the skill
folder into that repo's `.cursor/skills/`).
