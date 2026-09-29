#!/usr/bin/env python3
"""Convert the interactive HTML report to a print-ready PDF.

Usage:
    python build_report.py report.html "Client_Engagement_Review_30d" [out_dir]

The report is authored as a single self-contained interactive HTML file (the
primary deliverable). This script produces the downloadable PDF companion from
that same HTML via Google Chrome headless (--print-to-pdf, no header/footer).

The HTML must declare @page{size:1240px 1754px;margin:0} and
.page{width:1240px;height:1754px} so that one CSS page maps to one PDF page,
and its print stylesheet must force every <details> open and hide screen-only
chrome (.no-print) — see scripts/report_interactive.py (INTERACTIVE_CSS +
INTERACTIVE_JS, wired in via interactive_head). After running, this script asserts the PDF exists and prints
the page count so the agent can verify there is no overflow (doubled pages).

No PNG is produced anymore (the interactive HTML replaces the stitched PNG).

Deps: Google Chrome installed. (pymupdf only needed for the optional page count.)
"""
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


def pdf_page_count(pdf_path):
    """Best-effort page count for the overflow sanity check (needs pymupdf)."""
    try:
        import fitz  # pymupdf
    except Exception:
        return None
    with fitz.open(pdf_path) as doc:
        return doc.page_count


def expected_page_count(html_path):
    """How many sheets the HTML should print to: the .page divs that actually print.

    A bilingual report ships both languages but prints only the primary one (the
    other is hidden by an @media print rule), so counting every .page div would
    double the expectation. The primary language is the <html lang> attribute.
    """
    import re
    try:
        html = open(html_path, encoding="utf-8").read()
    except OSError:
        return None
    body = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.I | re.S)
    marks = [(m.group(1), m.start())
             for m in re.finditer(r'<div class="ir-lang" data-lang="([a-z]{2})"', body)]
    if len(marks) < 2:
        return len(re.findall(r'class="[^"]*\bpage\b', body))
    m = re.search(r"<html[^>]*\blang=\"([a-z]{2})\"", html, re.I)
    primary = m.group(1) if m else marks[0][0]
    for i, (lang, start) in enumerate(marks):
        if lang != primary:
            continue
        end = marks[i + 1][1] if i + 1 < len(marks) else len(body)
        return len(re.findall(r'class="[^"]*\bpage\b', body[start:end]))
    return None


def check_pagination(html_path, pages):
    """Compare actual PDF sheets to the printable .page divs. Returns True if sane.

    Fewer sheets than pages means content collapsed or was hidden — always a bug.
    More sheets means overflow; a little is normal (long appendix tables are allowed
    to flow, with repeating headers), a lot means sections are busting their sheet.
    """
    expected = expected_page_count(html_path)
    if expected is None or pages is None:
        return True
    if pages == expected:
        print(f"    pagination OK — {pages} sheets == {expected} printable .page divs")
        return True
    if pages < expected:
        print(f"    ✗ pagination — {pages} sheets < {expected} printable .page divs: "
              f"content was dropped or hidden in print. Check @media print rules.")
        return False
    over = pages - expected
    tol = max(2, round(expected * 0.15))
    flag = "!" if over <= tol else "✗"
    print(f"    [{flag}] pagination — {pages} sheets for {expected} .page divs "
          f"({over} overflow). Expected only for long appendix tables; if a narrative "
          f"section is spilling, trim it or split it. A blank trailing sheet means the "
          f"last page's bottom padding/margin overflows.")
    return over <= tol


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    html_path = sys.argv[1]
    base = sys.argv[2]
    out_dir = sys.argv[3] if len(sys.argv) > 3 else os.path.dirname(os.path.abspath(html_path))
    os.makedirs(out_dir, exist_ok=True)
    pdf_path = os.path.join(out_dir, base + ".pdf")

    html_to_pdf(html_path, pdf_path)
    n = pdf_page_count(pdf_path)
    if n is None:
        print(f"OK  pdf={pdf_path}  (install pymupdf to verify page count)")
        return
    print(f"OK  pdf={pdf_path}  pages={n}")
    if not check_pagination(html_path, n):
        sys.exit(2)


if __name__ == "__main__":
    main()
