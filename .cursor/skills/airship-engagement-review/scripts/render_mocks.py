#!/usr/bin/env python3
"""Render creative mockups (iOS lock-screen push + Message Center / in-app cards)
to auto-cropped PNGs via Chrome headless.

Use the CLIENT's app branding INSIDE the mockup (it depicts their message); keep the
surrounding report Airship-branded. When perpush/pushbody is 404/unavailable, label
the output as an illustrative reconstruction in the report.

API:
  render_push(notifs, out, accent="#E7233E", icon_svg=None, app_name="App")
      notifs: list of (time, title, body, tag) tuples (top = newest).
  render_card(inner_html, out, width=460, accent="#E7233E")
      inner_html: body of a phone-framed card (Message Center / in-app modal).

Both screenshot the HTML then crop to content using a brightness scan (numpy).

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
  <div class="tag">{tag}</div>
</div>
"""


def render_push(notifs, out, accent="#E7233E", icon_svg=None, app_name="App"):
    if icon_svg is None:
        icon_svg = (f'<svg viewBox="0 0 48 48" width="38" height="38">'
                    f'<rect width="48" height="48" rx="11" fill="{accent}"/></svg>')
    cards = "".join(
        _PUSH_CARD.format(icon=icon_svg, app=app_name, time=t, title=ti, body=b, tag=tag)
        for (t, ti, b, tag) in notifs
    )
    html = f"""<html><head><meta charset="utf-8"><style>
    body{{margin:0;background:transparent;font-family:'Helvetica Neue',Arial,sans-serif;}}
    .wrap{{width:460px;padding:20px;}}
    .card{{background:rgba(250,250,252,0.96);border-radius:22px;padding:16px 18px;
      margin-bottom:14px;box-shadow:0 10px 30px rgba(0,0,0,.18);}}
    .row{{display:flex;align-items:center;gap:10px;margin-bottom:8px;}}
    .ic{{width:38px;height:38px;border-radius:11px;overflow:hidden;}}
    .meta{{display:flex;flex-direction:column;}}
    .app{{font-size:13px;font-weight:700;color:#16161D;text-transform:uppercase;letter-spacing:.4px;}}
    .time{{font-size:12px;color:#8a8a99;}}
    .title{{font-size:17px;font-weight:700;color:#16161D;margin-bottom:3px;}}
    .body{{font-size:15px;color:#2a2a35;line-height:1.35;}}
    .tag{{margin-top:10px;font-size:11px;font-weight:700;color:{accent};letter-spacing:.5px;}}
    </style></head><body><div class="wrap">{cards}</div></body></html>"""
    _shoot(html, out, width=520, height=260 * len(notifs) + 120)
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
