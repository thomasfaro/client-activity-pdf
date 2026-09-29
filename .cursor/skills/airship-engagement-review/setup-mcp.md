# Prerequisite — configure the client project as an MCP server in Cursor

One-time setup per client project. Done once, it is done for every future review of
that account, so this is not part of the review workflow itself.

## Prerequisite — configure the client project as an MCP server in Cursor

Each Airship client project needs its **own MCP entry** in Cursor so the Agent can call
`call_airship_api` against that project's data. Credentials stay **local only**
(`~/.cursor/mcp.json` or Cursor Settings → MCP) — never commit them to this repo.

Two things that bite later if missed: the server is **local** — cloud subagents and
Automations read MCP from the team configuration, so collection cannot run there —
and the credentials are per project, so a review pointed at the wrong server
produces a plausible report about the wrong account.

The orchestrator (`scripts/run_review.py`) additionally needs a Cursor API key, because it
launches its agents through the Cursor SDK: `pip install cursor-sdk`, then
`export CURSOR_API_KEY=…` (Cursor Dashboard → Integrations). The collection itself does not
go through the SDK: `collect.py` reads the Airship credentials from `~/.cursor/mcp.json`.

### 1. Create OAuth credentials in Airship (per project)

In the Airship dashboard for the target project:

1. Project dropdown → **Settings** → **Project settings** → **OAuth**.
2. Create (or edit) an OAuth client. Enable **Allow Basic Auth** so a Client Secret is
   generated.
3. Enable scope — **only the one this skill uses**: **`rpt` (Reports)**.
   Do **not** require `tpl` (Content) — this skill never calls the Content API.
   Do **not** rely on `pln`/`sch`/experiment scopes — this skill never calls those APIs either.
4. Note three values from the dashboard:
   - **App Key** (`AIRSHIP_APP_KEY`) — also under Project settings → **General**.
   - **Client ID** (`AIRSHIP_CLIENT_ID`)
   - **Client Secret** (`AIRSHIP_CLIENT_SECRET`)
5. Set **region**: `eu` for `go.airship.eu` / `api.asnapieu.com`, `us` otherwise.

### 2. Add the MCP server in Cursor

**UI:** Cursor Settings (`Cmd+Shift+J`) → **MCP** → **Add new MCP server** (or edit
`~/.cursor/mcp.json` directly).

Add one block **per client project**. Use a clear name — this is what you pass to the
Agent (e.g. *"generate a review for **Client A PROD**"*). Cursor exposes it to the
Agent as `user-<name>` (e.g. `user-Client A PROD`).

```json
{
  "mcpServers": {
    "Client A PROD": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/agent-tools",
        "airship-mcp"
      ],
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

- **`/path/to/agent-tools`**: directory containing the `airship-mcp` package (clone or
  install the Airship MCP / agent-tools repo; requires `uv` on PATH).
- Duplicate the block for each client (`Client B PROD`, `Client C PROD`, …) with **that project's**
  app key and OAuth credentials.
- Optional env vars: `AIRSHIP_RTDS_BEARER_TOKEN` (RTDS), `AIRSHIP_API_URL` (staging).

After saving: **reload Cursor** (Command Palette → **Developer: Reload Window**) or use
the **Restart** button on the MCP server row in Settings.

### 3. Verify connectivity (before running a review)

In Agent chat, or by probing from the skill workflow:

```
GET /api/reports/devices   → 200 + ios/android opted_in counts (needs scope rpt)
```

Do **not** probe `/api/content/templates` — the Content API is out of scope for this skill.

If **401 `Expired token`**: restart / re-authenticate the MCP server in Cursor Settings,
then retry (OAuth tokens are short-lived; the MCP client refreshes on restart).

If **401 `Missing required scope`**: add the scope on the OAuth client in Airship, then
**restart the MCP server** so a new token is issued.

### 4. Naming convention (recommended)

| MCP config key | Agent invocation | Example |
|---|---|---|
| `"Client A PROD"` | `user-Client A PROD` | Production retail |
| `"Client B PROD"` | `user-Client B PROD` | Production finance |
| `"Client D DEV"` | `user-Client D DEV` | Non-prod sandbox |

Use **`PROD` / `DEV` suffixes** when the same brand has multiple Airship projects.

---

## Auth token & scopes (do this FIRST)

Before any data collection, the project's MCP server must authenticate with an Airship
auth token (OAuth client) that carries the **`rpt` (Reports) scope**. This skill calls
**only the Reports API** (`/api/reports/*`), so create the token in the Airship dashboard
(Settings → OAuth) with **exactly this scope**:
- **`rpt`** — Reports API (`/api/reports/*`): sends, opens, optins, optouts, devices,
  events, activity log, responses/list, perpush/pergroup, experiments (report endpoints).
  **Required** — the review cannot run without it.

**Do NOT call** the Content API (`/api/content/templates`, scope `tpl`), Pipelines
(`/api/pipelines`), Schedules (`/api/schedules`), or Experiments management
(`/api/experiments`). They are out of scope. Derive campaign typology and experiment
presence from the Reports API only (see Analysis).

If a call returns **401 `Expired token`**, ask the user to re-authenticate the MCP server
in Cursor settings, then retry. If it returns **401 `Missing required scope`**, add **`rpt`**
on the OAuth client and reconnect.
