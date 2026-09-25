"""Direct Reports-API client — for the exhaustive passes the MCP cannot serve.

The Airship MCP server is the right tool for exploratory calls, but it costs one
round-trip per page. A firehose account needs tens of thousands of pages, so the
enumeration has to run in-process. This client reuses the **same OAuth
client-credentials flow** as the MCP server (`agent-tools/tools/auth.py`) and reads
its credentials from the local Cursor MCP config, so it never introduces a second
source of truth for secrets and never writes them to disk.

    from airship_api import Airship
    api = Airship("CLIENT PROD")            # MCP server entry name
    api.get("/api/reports/devices")
    for rows in api.paginate("/api/reports/responses/list", {...}):
        ...

Scope used: `rpt` (Reports) only. Read-only.

API quirks this client and its callers must respect (see reference.md):
  * time-window `end` is **INCLUSIVE** — tile windows as [t, t+span-1], never
    [t, t+span), or boundary rows are counted twice;
  * `start == end` returns HTTP 500 — the smallest usable window is 2 seconds;
  * no endpoint states whether its window has finished consolidating, so a recent
    window returns `200` with zeros that read as real — see `Airship.watermark()`.
"""

import base64
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

MCP_CONFIG = os.path.expanduser("~/.cursor/mcp.json")

_BASE = {"eu": "https://api.asnapieu.com", "us": "https://api.asnapius.com"}
_OAUTH = {"eu": "https://oauth2.asnapieu.com", "us": "https://oauth2.asnapius.com"}

RETRY_STATUS = (429, 500, 502, 503, 504)


def list_projects(config_path=MCP_CONFIG):
    """MCP server entries that carry Airship credentials, for error messages."""
    try:
        with open(config_path, encoding="utf-8") as fh:
            servers = json.load(fh).get("mcpServers", {})
    except OSError:
        return []
    return sorted(name for name, s in servers.items()
                  if (s.get("env") or {}).get("AIRSHIP_APP_KEY"))


def _env(server, config_path):
    with open(config_path, encoding="utf-8") as fh:
        servers = json.load(fh).get("mcpServers", {})
    if server not in servers:
        raise KeyError(f"no MCP server named {server!r} in {config_path}. "
                       f"Available: {', '.join(list_projects(config_path)) or '(none)'}")
    env = servers[server].get("env") or {}
    missing = [k for k in ("AIRSHIP_APP_KEY", "AIRSHIP_CLIENT_ID", "AIRSHIP_CLIENT_SECRET")
               if not env.get(k)]
    if missing:
        raise KeyError(f"MCP server {server!r} is missing {', '.join(missing)}")
    return env


class Airship:
    """Thread-safe read-only Reports API client for one project."""

    def __init__(self, server, config_path=MCP_CONFIG):
        env = _env(server, config_path)
        self.server = server
        self.app_key = env["AIRSHIP_APP_KEY"]
        self.client_id = env["AIRSHIP_CLIENT_ID"]
        self.client_secret = env["AIRSHIP_CLIENT_SECRET"]
        self.region = (env.get("AIRSHIP_REGION") or "us").lower()
        if self.region not in _BASE:
            raise ValueError(f"unknown AIRSHIP_REGION {self.region!r} (expected eu/us)")
        self.base = _BASE[self.region]
        self._token = None
        self._exp = 0.0
        self._token_lock = threading.Lock()
        self._call_lock = threading.Lock()
        self._watermark = None
        self.calls = 0

    # -- auth ---------------------------------------------------------------
    def _fetch_token(self):
        creds = base64.b64encode(
            f"{urllib.parse.quote_plus(self.client_id)}:"
            f"{urllib.parse.quote_plus(self.client_secret)}".encode()
        ).decode()
        data = urllib.parse.urlencode(
            {"grant_type": "client_credentials", "sub": f"app:{self.app_key}"}
        ).encode()
        req = urllib.request.Request(
            _OAUTH[self.region] + "/token", data=data,
            headers={"Authorization": "Basic " + creds,
                     "Content-Type": "application/x-www-form-urlencoded",
                     "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            body = json.load(r)
        self._token = body["access_token"]
        self._exp = time.time() + float(body.get("expires_in", 3300)) - 120

    def _auth(self):
        # double-checked: refreshing under the lock keeps a 14-thread pool from
        # stampeding the token endpoint when the token expires mid-enumeration
        if self._token and time.time() < self._exp:
            return self._token
        with self._token_lock:
            if not self._token or time.time() >= self._exp:
                self._fetch_token()
            return self._token

    # -- requests -----------------------------------------------------------
    def get(self, path, params=None, retries=4):
        """GET a Reports API path (or a full `next_page` URL). Returns parsed JSON."""
        url = path if path.startswith("http") else self.base + path
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        last = None
        for attempt in range(retries):
            req = urllib.request.Request(url, headers={
                "Authorization": "Bearer " + self._auth(),
                "Accept": "application/vnd.urbanairship+json; version=3",
                "X-UA-Appkey": self.app_key})
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    payload = json.load(r)
                with self._call_lock:
                    self.calls += 1
                return payload
            except urllib.error.HTTPError as e:
                last = e
                if e.code == 401:
                    self._token = None
                    continue
                if e.code in RETRY_STATUS:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise RuntimeError(f"HTTP {e.code} on {url}: {e.read()[:300]!r}") from e
            except (urllib.error.URLError, TimeoutError) as e:
                last = e
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"giving up on {url}: {last}")

    def paginate(self, path, params=None, key="pushes", max_pages=None, on_page=None):
        """Follow `next_page` cursors, yielding each page's rows."""
        page = self.get(path, params)
        n = 0
        while True:
            rows = page.get(key) or []
            n += 1
            if on_page:
                on_page(n, rows, page)
            yield rows
            nxt = page.get("next_page")
            if not nxt or not rows or (max_pages and n >= max_pages):
                return
            page = self.get(nxt)

    def collect(self, path, params=None, key="pushes", max_pages=None):
        """Fully drain a paginated endpoint into one list."""
        out = []
        for rows in self.paginate(path, params, key=key, max_pages=max_pages):
            out.extend(rows)
        return out

    # -- consolidation ------------------------------------------------------
    def watermark(self):
        """How far the account's reporting data has settled: `/api/reports/devices`.

        The Reports API publishes no consolidation watermark on its windowed or
        per-message endpoints, so there is no way to tell "this message sent nothing"
        from "the data has not landed yet". A message read too early returns HTTP 200
        with `sends: 0` and honest-looking zeros, and two hours later returns real
        numbers. That failure mode has cost real analysis time: three findings written up
        as API defects turned out to be nothing but an unsettled window.

        `/api/reports/devices` is the one endpoint that does state it, via `date_closed`
        and `date_computed`. It describes the device snapshot rather than the message
        endpoints, so it is a proxy, not a guarantee — but it is the only signal the API
        offers, and an account whose device snapshot closed three days ago is not an
        account whose sends settled this morning.

        Cached: one call, and every stage can ask.
        """
        if getattr(self, "_watermark", None) is None:
            d = self.get("/api/reports/devices")
            self._watermark = {"date_closed": d.get("date_closed"),
                               "date_computed": d.get("date_computed"),
                               "source": "/api/reports/devices",
                               "proxy": True,
                               "note": ("device-snapshot dates; the Reports API exposes "
                                        "no watermark on windowed or per-message "
                                        "endpoints, so this is the closest signal")}
        return self._watermark


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print(__doc__)
        print("Projects with credentials:")
        for p in list_projects():
            print("  -", p)
        sys.exit(1)
    a = Airship(sys.argv[1])
    d = a.get("/api/reports/devices")
    print(f"OK  {a.server}  region={a.region}  "
          f"devices={d.get('total_unique_devices'):,}  closed={d.get('date_closed')}")
