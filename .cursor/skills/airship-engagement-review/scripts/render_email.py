#!/usr/bin/env python3
"""Render a REAL email / Message Center creative (html_body) to a cropped PNG.

Use this when you have the actual HTML of a creative (e.g. the `content.html_body`
of a Content Template, or the decoded Message Center HTML from a per-push body) and
want a faithful preview — NOT an illustrative reconstruction.

Where the HTML comes from (see SKILL.md "Creative retrieval"):
  - Mass sends (BROADCAST / SEGMENTS / A-B): GET /api/reports/perpush/pushbody/{push_id}
  - 1:1 / template-driven sends (UNICAST / Create-and-Send): the per-push body is EMPTY,
    so the creative lives in GET /api/content/templates (scope `tpl`) -> content.html_body.

API:
  render_email(html, out, width=680)
      html: full email/MC HTML string (or path to an .html file).
      Renders via Chrome headless and crops to content (background-aware).

Notes:
  - Emails load remote images; Chrome headless often does not exit cleanly. We use a
    subprocess timeout and proceed as long as the screenshot file was written.
  - Cropping detects the dominant background colour (works for white AND dark emails)
    and trims uniform top/bottom margins.

Deps: pillow, numpy. Requires Google Chrome.
"""
import os
import subprocess
import sys
import tempfile

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


def _shoot(html_path, out, width=680, height=3000, scale=2, timeout=45):
    with tempfile.TemporaryDirectory() as ud:
        cmd = [
            _chrome(), "--headless=new", "--disable-gpu", "--no-sandbox",
            f"--user-data-dir={ud}", f"--force-device-scale-factor={scale}",
            f"--window-size={width},{height}", "--hide-scrollbars",
            "--virtual-time-budget=8000", f"--screenshot={out}",
            "file://" + os.path.abspath(html_path),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            pass  # Chrome may not exit; the screenshot is usually already written.
        except subprocess.CalledProcessError:
            pass
    if not os.path.exists(out) or os.path.getsize(out) == 0:
        raise RuntimeError(f"screenshot not produced: {out}")


def _autocrop(path, pad=20, tol=18, min_frac=0.012):
    """Trim uniform top/bottom margins. Background colour is inferred from the corners,
    so this works for white emails and dark-themed emails alike."""
    import numpy as np
    from PIL import Image

    im = Image.open(path).convert("RGB")
    a = np.asarray(im).astype(int)
    h, w, _ = a.shape
    corners = np.concatenate([a[0, :8], a[-1, :8], a[0, -8:], a[-1, -8:]], axis=0)
    bg = np.median(corners, axis=0)
    diff = np.abs(a - bg).max(axis=2)              # per-pixel distance from bg
    content = diff > tol
    row_has = content.mean(axis=1) > min_frac      # row counts if enough non-bg pixels
    rows = np.where(row_has)[0]
    if len(rows) == 0:
        return path
    top, bot = max(0, rows[0] - pad), min(h, rows[-1] + pad)
    im.crop((0, top, w, bot)).save(path)
    return path


_FRAME = """<!doctype html><html><head><meta charset="utf-8">
<style>
  html,body{{margin:0;padding:0;background:#ffffff;}}
  .frame{{width:{width}px;margin:0 auto;}}
  img{{max-width:100%;height:auto;}}
</style></head><body><div class="frame">{body}</div></body></html>"""


def render_email(html, out, width=680, timeout=45):
    """html: an HTML string OR a path to an .html file."""
    if os.path.sep in str(html) and os.path.exists(html) and len(str(html)) < 1024:
        html = open(html, encoding="utf-8").read()
    full = html if "<html" in html.lower() else _FRAME.format(width=width, body=html)
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(full)
        path = f.name
    try:
        _shoot(path, out, width=width, timeout=timeout)
        _autocrop(out)
    finally:
        os.unlink(path)
    return out


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: render_email.py <input.html> <output.png> [width]")
        sys.exit(1)
    w = int(sys.argv[3]) if len(sys.argv) > 3 else 680
    render_email(sys.argv[1], sys.argv[2], width=w)
    print("rendered", sys.argv[2])
