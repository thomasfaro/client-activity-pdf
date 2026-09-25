#!/usr/bin/env python3
"""Render a REAL email / Message Center creative (html_body) to a cropped PNG.

Use this when you have the actual HTML of a creative (e.g. Message Center / email HTML
decoded from `perpush/pushbody`) and want a faithful preview — NOT an illustrative
reconstruction.

Where the HTML comes from (see SKILL.md "Creative retrieval"):
  - Mass sends (BROADCAST / SEGMENTS / A-B): GET /api/reports/perpush/pushbody/{push_id}
  - UNICAST / template-driven: pushbody is usually empty — no Content API in this skill;
    use illustrative reconstruction unless pushbody happens to contain HTML.

API:
  render_email(html, out, width=700, inline_remote=True, max_height=None)
      html: full email/MC HTML string (or path to an .html file).
      max_height: crop to this many pixels from the top after render — use ~720 with
      width=375 for Message Center / full-screen mobile templates (one phone screen).
      Renders via Chrome headless and crops to content (background-aware).

Robustness notes (learned the hard way on real Airship email templates):
  - Airship email creatives are IMAGE-BASED: the layout is a stack of remote images
    hosted on dl.asnapieu.com (the same public CDN as push hero images). Headless
    Chrome does NOT reliably fetch/lay-out those remote images before the screenshot
    fires, so the page renders as a near-empty white strip. FIX: `inline_remote=True`
    pre-downloads every remote <img src="http..."> (urllib -> curl fallback, exactly
    like render_mocks.fetch_media) and rewrites the src to a local file:// path so the
    render is deterministic and offline.
  - Render at device-scale-factor 1. At scale 2 these fixed-width email tables collapse
    to an almost-empty page (observed repeatedly) — scale 1 renders the full creative.
  - Chrome headless often does NOT exit on these pages. We launch it, wait past the
    virtual-time budget for the screenshot to flush, then hard-kill it.
  - Cropping trims uniform top/bottom margins. If the crop would yield a near-empty
    sliver (a sign the render/crop failed), we keep the un-cropped image instead of
    returning a blank.

Deps: pillow, numpy. Requires Google Chrome.
"""
import os
import re
import subprocess
import sys
import tempfile
import time
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


def _download(url, out, timeout=20):
    """Fetch a URL to `out`. Tries urllib, then curl — the macOS system Python often
    fails TLS cert verification and some CDNs reject non-browser agents (same issue
    handled in render_mocks.fetch_media)."""
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


def _inline_remote_images(html, workdir):
    """Download every remote <img src="http(s)://..."> and rewrite to a local file://
    path so headless Chrome renders the creative offline/deterministically. Keeps the
    HTML small (base64 data URIs bloat it to megabytes and make Chrome time out).
    Failures are left as-is (Chrome just skips them)."""
    os.makedirs(workdir, exist_ok=True)
    urls = [m.group(1) for m in re.finditer(r'src\s*=\s*"(https?://[^"]+)"', html, re.I)]
    seen = {}
    for i, u in enumerate(dict.fromkeys(urls)):
        p = _download(u, os.path.join(workdir, f"img_{i}"))
        if p:
            seen[u] = "file://" + os.path.abspath(p)
    for u, local in seen.items():
        html = html.replace('"' + u + '"', '"' + local + '"')
    return html


def _has_content(path, white_tol=8, min_frac=0.004):
    """True if the screenshot has a meaningful fraction of non-white pixels (i.e. a real
    render landed, not a blank frame). Cheap: samples every 16th row."""
    try:
        import numpy as np
        from PIL import Image
        a = np.asarray(Image.open(path).convert("RGB")).astype(int)[::16]
        return float((np.abs(a - 255).max(axis=2) > white_tol).mean()) > min_frac
    except Exception:
        return False


def _kill_group(p):
    """Kill Chrome AND all its children. subprocess timeouts only kill the direct child;
    Chrome spawns renderer/gpu/zygote processes that otherwise LEAK. Leaked headless
    Chromes accumulate and starve later renders into blank screenshots — so we always
    kill the whole process group."""
    import signal
    try:
        os.killpg(os.getpgid(p.pid), signal.SIGKILL)
    except Exception:
        try:
            p.kill()
        except Exception:
            pass


def _shoot_once(html_path, out, width, height, scale, budget_ms, settle):
    """One headless render attempt. Launch Chrome, wait past the virtual-time budget for
    the screenshot to flush, then kill the whole process group. Returns True if a
    non-blank screenshot landed. (A fixed wait + single read proved far more reliable
    than polling the half-written file.)"""
    ud = tempfile.mkdtemp()
    if os.path.exists(out):
        try:
            os.remove(out)
        except Exception:
            pass
    cmd = [
        _chrome(), "--headless=new", "--disable-gpu", "--no-sandbox",
        f"--user-data-dir={ud}", f"--force-device-scale-factor={scale}",
        f"--window-size={width},{height}", "--hide-scrollbars",
        f"--virtual-time-budget={budget_ms}",
        f"--screenshot={out}", "file://" + os.path.abspath(html_path),
    ]
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    try:
        p.wait(timeout=budget_ms / 1000.0 + settle)
    except subprocess.TimeoutExpired:
        pass
    finally:
        _kill_group(p)      # reap ALL children -> no leaks that would blank later renders
    return _has_content(out)


def _shoot(html_path, out, width=700, height=2600, scale=1, budget_ms=10000,
           settle=4.0, attempts=3):
    """Render an image-based Airship email creative to `out`, robustly. Hard-won details:

      * `--headless=new` + `--virtual-time-budget` render the full creative; do NOT add
        `--run-all-compositor-stages-before-draw` (it tended to leave a blank frame).
      * Render at device-scale-factor 1 — at scale 2 these fixed-width email tables
        collapse to a near-empty page.
      * Chrome usually does NOT exit on these pages, so we wait past the virtual-time
        budget, then kill the whole process GROUP (not just the direct child) so
        renderer/gpu children can't leak and starve later renders into blanks.
      * Headless screenshot timing is genuinely non-deterministic under load, so we
        RETRY a blank render with a fresh Chrome and a larger budget before giving up."""
    for i in range(attempts):
        if _shoot_once(html_path, out, width, height, scale,
                       budget_ms + i * 5000, settle):
            return
    if not os.path.exists(out) or os.path.getsize(out) == 0:
        raise RuntimeError(f"screenshot not produced: {out}")
    raise RuntimeError(f"screenshot rendered blank after {attempts} attempts: {out}")


def _autocrop(path, pad=16, flat_tol=14, min_keep_px=120):
    """Trim uniform top/bottom margin BANDS only.

    Corner/median background detection is fooled by emails that open with a coloured
    header band (the sampled corners are then part of the artwork, so nothing gets
    trimmed). Instead we trim contiguous *flat* rows (near-uniform colour across the
    whole row) from the top and bottom — that removes white/solid page margins while
    keeping every row that contains real content (logo, text, images), and it works for
    white AND dark-themed emails. If trimming would leave an implausibly small sliver
    (render failure), keep the full image."""
    import numpy as np
    from PIL import Image

    im = Image.open(path).convert("RGB")
    a = np.asarray(im).astype(int)
    h, w, _ = a.shape
    # A row is "flat" if its pixel value range (per channel, across the row) is tiny.
    row_range = a.max(axis=1) - a.min(axis=1)          # (h, 3)
    flat = row_range.max(axis=1) <= flat_tol            # (h,) uniform-colour rows
    top = 0
    while top < h and flat[top]:
        top += 1
    bot = h - 1
    while bot > top and flat[bot]:
        bot -= 1
    top = max(0, top - pad)
    bot = min(h, bot + 1 + pad)
    if bot - top < min_keep_px or bot - top >= h:
        # Nothing meaningful trimmed, or suspiciously small -> keep the whole frame.
        return im.size
    im.crop((0, top, w, bot)).save(path)
    return Image.open(path).size


_FRAME = """<!doctype html><html><head><meta charset="utf-8">
<style>
  html,body{{margin:0;padding:0;background:#ffffff;}}
  .frame{{width:{width}px;margin:0 auto;}}
  img{{max-width:100%;height:auto;}}
</style></head><body><div class="frame">{body}</div></body></html>"""


def _looks_like_path(s):
    """True if `s` is a short string that names an existing file (a path to read), as
    opposed to raw HTML markup. Must handle bare relative names like "email.html" that
    contain no path separator."""
    return (
        isinstance(s, str)
        and len(s) < 1024
        and "\n" not in s
        and "<" not in s
        and os.path.exists(s)
    )


def _cap_height(path, max_h):
    """Keep only the top `max_h` pixels (phone above-the-fold for MC templates)."""
    if not max_h or max_h <= 0:
        return
    from PIL import Image
    im = Image.open(path)
    w, h = im.size
    if h > max_h:
        im.crop((0, 0, w, max_h)).save(path)


def render_email(html, out, width=700, inline_remote=True, max_height=None):
    """html: an HTML string OR a path to an .html file.

    inline_remote: pre-download remote images and inline them as file:// paths so the
    render is deterministic (strongly recommended for Airship image-based emails).
    max_height: when set, crop the PNG to this many pixels from the top after render.
    Use ~720 for Message Center / mobile full-screen templates (width=375) so the PNG
    matches one phone screen instead of the full scrollable page."""
    if _looks_like_path(html):
        html = open(html, encoding="utf-8").read()
    full = html if "<html" in html.lower() else _FRAME.format(width=width, body=html)
    workdir = tempfile.mkdtemp(prefix="email_render_")
    if inline_remote:
        full = _inline_remote_images(full, os.path.join(workdir, "imgs"))
    path = os.path.join(workdir, "email.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(full)
    shoot_h = min(2600, max_height + 200) if max_height else 2600
    try:
        _shoot(path, out, width=width, height=shoot_h)
        _autocrop(out)
        if max_height:
            _cap_height(out, max_height)
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass
    return out


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: render_email.py <input.html> <output.png> [width]")
        sys.exit(1)
    w = int(sys.argv[3]) if len(sys.argv) > 3 else 700
    render_email(sys.argv[1], sys.argv[2], width=w)
    print("rendered", sys.argv[2])
