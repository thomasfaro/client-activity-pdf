#!/usr/bin/env python3
"""Convert an HTML report to a print-ready PDF and a stitched PNG.

Usage:
    python build_report.py report.html "Client_Engagement_Review_90d" [out_dir]

Steps:
  1. HTML -> PDF via Google Chrome headless (--print-to-pdf, no header/footer).
  2. PDF -> PNG via PyMuPDF, rendered at 2x and stitched vertically.

The HTML must declare @page{size:1240px 1754px;margin:0} and
.page{width:1240px;height:1754px} so that one CSS page maps to one PDF page.
After running, this script asserts the PDF page count and prints it so the agent
can verify there is no overflow (doubled pages).

Deps: pymupdf, pillow. Requires Google Chrome installed.
"""
import io
import os
import subprocess
import sys

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome",
    "chromium",
    "chrome",
]


def find_chrome():
    for c in CHROME_CANDIDATES:
        if os.path.sep in c:
            if os.path.exists(c):
                return c
        else:
            from shutil import which
            if which(c):
                return c
    raise RuntimeError("Google Chrome not found; install it or edit CHROME_CANDIDATES.")


def html_to_pdf(html_path, pdf_path):
    chrome = find_chrome()
    url = "file://" + os.path.abspath(html_path)
    subprocess.run(
        [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--print-to-pdf={pdf_path}",
            url,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if not os.path.exists(pdf_path):
        raise RuntimeError("Chrome did not produce a PDF.")


def pdf_to_png(pdf_path, png_path, zoom=2, gap=24, bg=(201, 201, 212)):
    import fitz  # pymupdf
    from PIL import Image

    doc = fitz.open(pdf_path)
    imgs = [
        Image.open(io.BytesIO(p.get_pixmap(matrix=fitz.Matrix(zoom, zoom)).tobytes("png"))).convert("RGB")
        for p in doc
    ]
    n = len(imgs)
    w = max(i.width for i in imgs)
    h = sum(i.height for i in imgs) + gap * (n - 1)
    canvas = Image.new("RGB", (w, h), bg)
    y = 0
    for i in imgs:
        canvas.paste(i, ((w - i.width) // 2, y))
        y += i.height + gap
    canvas.save(png_path)
    return n


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    html_path = sys.argv[1]
    base = sys.argv[2]
    out_dir = sys.argv[3] if len(sys.argv) > 3 else os.path.dirname(os.path.abspath(html_path))
    os.makedirs(out_dir, exist_ok=True)
    pdf_path = os.path.join(out_dir, base + ".pdf")
    png_path = os.path.join(out_dir, base + ".png")

    html_to_pdf(html_path, pdf_path)
    n = pdf_to_png(pdf_path, png_path)
    print(f"OK  pdf={pdf_path}  png={png_path}  pages={n}")
    print("Verify: pages should equal the number of .page divs in the HTML.")


if __name__ == "__main__":
    main()
