#!/usr/bin/env python3
"""Render creative mockups (iOS lock-screen push + Message Center / in-app cards)
to auto-cropped PNGs via Chrome headless.

Use the CLIENT's app branding INSIDE the mockup (it depicts their message); keep the
surrounding report Airship-branded. When perpush/pushbody is 404/unavailable, label
the output as an illustrative reconstruction in the report.

API:
  fetch_media(url, out, timeout=20)
      Download a push hero image (media_attachment / big_picture URL) to `out`.
      Returns `out` on success, None on failure (caller falls back to a text-only card).
  fetch_app_icon(query, out, country="us")
      Best-effort download of the REAL app icon (iTunes Search API for iOS; Google Play
      og:image when `query` is a package id) for realistic push previews. Returns `out`
      or None (caller keeps the colored initials tile).
  render_push(notifs, out, accent="#E7233E", icon_svg=None, app_name="App", app_icon=None)
      notifs: list of (time, title, body, tag) OR (time, title, body, tag, image_path)
      tuples (top = newest). When an image_path is given, the notification renders WITH
      the real hero image (rich/expanded push) — a faithful preview, not a text-only mock.
      When `app_icon` (a local path) is given, the real app logo is used as the
      notification icon instead of the colored `accent` tile.
  render_card(inner_html, out, width=460, accent="#E7233E")
      inner_html: body of a phone-framed card (Message Center / in-app modal).

Prefer real creatives: for a rich push, decode the pushbody, take the image URL from
`notification.ios.media_attachment.url` / `notification.android.style.big_picture`,
`fetch_media()` it, then pass the local path to `render_push()`. For the icon, resolve the
real app logo once via `fetch_app_icon()` during brand research and pass `app_icon=`.

Both screenshot the HTML then crop to content using a brightness scan (numpy).

Deps: pillow, numpy. Requires Google Chrome.
"""
import os
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome", "chromium", "chrome",
]


def _chrome():
    from shutil import which
    for c in CHROME_CANDIDATES:
        if os.path.sep in c:
            if os.path.exists(c):
                return c
        elif which(c):
            return c
    raise RuntimeError("Google Chrome not found.")


def fetch_media(url, out, timeout=20):
    """Download a push hero image (media_attachment / big_picture URL) to `out`.

    Returns `out` on success, or None on any failure so the caller can fall back to a
    text-only card. The image lives at a public binary URL in the decoded pushbody
    (`notification.ios.media_attachment.url` / `notification.android.style.big_picture`).

    Tries urllib first, then falls back to `curl` — some CDNs (e.g. Airship's
    dl.asnapieu.com) reject urllib's default TLS/UA on macOS but serve curl fine."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
        if data:
            with open(out, "wb") as f:
                f.write(data)
            return out
    except Exception:
        pass
    # Fallback: curl (handles CDNs that reject urllib TLS/UA).
    try:
        rc = subprocess.run(
            ["curl", "-fsSL", "--max-time", str(timeout), "-A", "Mozilla/5.0", "-o", out, url],
            capture_output=True,
        )
        if rc.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 0:
            return out
    except Exception:
        pass
    return None


def _http_text(url, timeout=15):
    """GET a URL and return decoded text. Tries urllib, then curl — the macOS system
    Python often fails TLS cert verification, exactly as with fetch_media()."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        pass
    try:
        rc = subprocess.run(
            ["curl", "-fsSL", "--max-time", str(timeout), "-A", "Mozilla/5.0", url],
            capture_output=True,
        )
        if rc.returncode == 0 and rc.stdout:
            return rc.stdout.decode("utf-8", "replace")
    except Exception:
        pass
    return None


def fetch_app_icon(query, out, country="us", timeout=15):
    """Best-effort download of a real app icon for realistic push previews.

    Resolution order:
      1. iTunes Search API (iOS App Store) — public, no auth; returns
         `artworkUrl512`/`artworkUrl100` for the best name match.
      2. Google Play store-page `og:image` — used ONLY when `query` looks like a package
         id (e.g. `com.example.app`); the app-details og:image IS the real icon.
         Play *search* is skipped because its og:image is a generic Play logo.
    `query`: brand/app name (e.g. "Acme") or an Android package id. `country`: 2-letter
    store code (e.g. "fr"). Returns `out` on success, else None (keep the initials tile)."""
    import json as _json
    import re as _re
    try:
        api = ("https://itunes.apple.com/search?term=" + urllib.parse.quote(query) +
               "&entity=software&limit=1&country=" + country)
        txt = _http_text(api, timeout=timeout)
        if txt:
            results = (_json.loads(txt).get("results") or [])
            if results:
                icon = results[0].get("artworkUrl512") or results[0].get("artworkUrl100")
                if icon and fetch_media(icon, out, timeout=timeout):
                    return out
    except Exception:
        pass
    if "." in query and " " not in query:  # looks like an Android package id
        try:
            page = ("https://play.google.com/store/apps/details?id=" +
                    urllib.parse.quote(query) + "&hl=en")
            html = _http_text(page, timeout=timeout)
            m = _re.search(r'<meta property="og:image" content="([^"]+)"', html) if html else None
            if m and fetch_media(m.group(1), out, timeout=timeout):
                return out
        except Exception:
            pass
    return None


def _shoot(html, out, width=520, height=1400):
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
        f.write(html)
        path = f.name
    subprocess.run(
        [_chrome(), "--headless=new", "--disable-gpu", "--hide-scrollbars",
         f"--window-size={width},{height}", f"--screenshot={out}",
         "--default-background-color=00000000", "file://" + path],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    os.unlink(path)


def _autocrop(path, pad=16, thresh=150):
    """Crop transparent/empty margins by scanning row/col content brightness."""
    import numpy as np
    from PIL import Image

    im = Image.open(path).convert("RGBA")
    a = np.asarray(im)
    rgb = a[:, :, :3].max(axis=2)
    alpha = a[:, :, 3]
    content = (alpha > 10) & (rgb < 250)  # non-transparent, non-pure-white
    if not content.any():
        return path
    rows = np.where(content.any(axis=1))[0]
    cols = np.where(content.any(axis=0))[0]
    top, bot = max(0, rows[0] - pad), min(a.shape[0], rows[-1] + pad)
    left, right = max(0, cols[0] - pad), min(a.shape[1], cols[-1] + pad)
    im.crop((left, top, right, bot)).save(path)
    return path


_PUSH_CARD = """
<div class="card">
  <div class="row">
    <div class="ic">{icon}</div>
    <div class="meta"><span class="app">{app}</span><span class="time">{time}</span></div>
  </div>
  <div class="title">{title}</div>
  <div class="body">{body}</div>
  {image}
  <div class="tag">{tag}</div>
</div>
"""


def render_push(notifs, out, accent="#E7233E", icon_svg=None, app_name="App", app_icon=None):
    """notifs: list of (time, title, body, tag) or (time, title, body, tag, image_path).
    When image_path is set, the notification renders WITH the real hero image.
    When app_icon (a local path, e.g. from fetch_app_icon) is set, the real app logo is
    used as the notification icon instead of the colored accent tile."""
    if app_icon and os.path.exists(app_icon):
        icon_html = (f'<img src="file://{os.path.abspath(app_icon)}" '
                     f'style="width:38px;height:38px;border-radius:11px;display:block;object-fit:cover;">')
    else:
        if icon_svg is None:
            icon_svg = (f'<svg viewBox="0 0 48 48" width="38" height="38">'
                        f'<rect width="48" height="48" rx="11" fill="{accent}"/></svg>')
        icon_html = icon_svg

    def _img(n):
        img = n[4] if len(n) > 4 else None
        if not img:
            return ""
        return f'<img class="hero" src="file://{os.path.abspath(img)}">'

    cards = "".join(
        _PUSH_CARD.format(icon=icon_html, app=app_name, time=n[0], title=n[1],
                          body=n[2], tag=n[3], image=_img(n))
        for n in notifs
    )
    has_img = any(len(n) > 4 and n[4] for n in notifs)
    html = f"""<html><head><meta charset="utf-8"><style>
    body{{margin:0;background:transparent;font-family:'Helvetica Neue',Arial,sans-serif;}}
    .wrap{{width:560px;padding:20px;}}
    .card{{background:rgba(250,250,252,0.96);border-radius:22px;padding:16px 18px;
      margin-bottom:14px;box-shadow:0 10px 30px rgba(0,0,0,.18);overflow:hidden;}}
    .row{{display:flex;align-items:center;gap:10px;margin-bottom:8px;}}
    .ic{{width:38px;height:38px;border-radius:11px;overflow:hidden;}}
    .meta{{display:flex;flex-direction:column;}}
    .app{{font-size:13px;font-weight:700;color:#16161D;text-transform:uppercase;letter-spacing:.4px;}}
    .time{{font-size:12px;color:#8a8a99;}}
    .title{{font-size:17px;font-weight:700;color:#16161D;margin-bottom:3px;}}
    .body{{font-size:15px;color:#2a2a35;line-height:1.35;}}
    .hero{{width:100%;border-radius:14px;margin-top:12px;display:block;}}
    .tag{{margin-top:10px;font-size:11px;font-weight:700;color:{accent};letter-spacing:.5px;}}
    </style></head><body><div class="wrap">{cards}</div></body></html>"""
    _shoot(html, out, width=600, height=(560 if has_img else 260) * len(notifs) + 140)
    return _autocrop(out)


def render_card(inner_html, out, width=460, accent="#E7233E"):
    html = f"""<html><head><meta charset="utf-8"><style>
    body{{margin:0;background:transparent;font-family:'Helvetica Neue',Arial,sans-serif;}}
    .phone{{width:{width}px;background:#fff;border-radius:26px;overflow:hidden;
      box-shadow:0 16px 44px rgba(0,0,0,.20);}}
    .bar{{height:8px;background:{accent};}}
    .pad{{padding:22px;}}
    h1,h2,h3{{color:#16161D;}} p{{color:#33333f;line-height:1.45;}}
    .btn{{display:inline-block;background:{accent};color:#fff;font-weight:700;
      padding:12px 20px;border-radius:10px;text-decoration:none;margin-top:8px;}}
    img{{max-width:100%;border-radius:10px;}}
    </style></head><body><div class="phone"><div class="bar"></div>
    <div class="pad">{inner_html}</div></div></body></html>"""
    _shoot(html, out, width=width + 80, height=1500)
    return _autocrop(out)


if __name__ == "__main__":
    out_dir = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp()
    os.makedirs(out_dir, exist_ok=True)
    render_push(
        [("09:12", "Sample title", "Sample push body for the mockup.", "BROADCAST")],
        os.path.join(out_dir, "push.png"),
    )
    render_card("<h2>Message Center</h2><p>Rich content body.</p><a class='btn'>Shop now</a>",
                os.path.join(out_dir, "card.png"))
    print("demo mockups in", out_dir)
