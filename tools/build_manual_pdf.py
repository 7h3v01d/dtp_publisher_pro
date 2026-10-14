# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Leon Priest (GitHub: 7h3v01d)
"""Print the user manual (src/dtp_publisher/help/manual.html) to "User Manual.pdf".

Developer tool: needs Playwright and its Chromium (pip install playwright;
python -m playwright install chromium).  The finished PDF is part of the
source, so building the program doesn't need this.

    python tools/build_manual_pdf.py
"""

from __future__ import annotations

import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
HTML = ROOT / "src" / "dtp_publisher" / "help" / "manual.html"
OUT = ROOT / "User Manual.pdf"

FOOTER = ("<div style='width:100%;font-size:8pt;color:#666;padding:0 15mm;"
          "font-family:Segoe UI,Calibri,Carlito,Arial,sans-serif;display:flex;"
          "justify-content:space-between'><span>DTP Publisher Pro · User manual</span>"
          "<span>Page <span class='pageNumber'></span> of <span class='totalPages'></span>"
          "</span></div>")


def main() -> int:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        exe = os.environ.get("CHROMIUM_PATH")
        browser = pw.chromium.launch(**({"executable_path": exe} if exe else {}))
        page = browser.new_page()
        page.emulate_media(media="print", color_scheme="light")
        page.goto(HTML.as_uri(), wait_until="load")
        page.pdf(path=str(OUT), format="A4", print_background=True,
                 display_header_footer=True, header_template="<span></span>",
                 footer_template=FOOTER,
                 margin={"top": "16mm", "bottom": "18mm", "left": "15mm", "right": "15mm"},
                 prefer_css_page_size=False)
        browser.close()
    print(OUT, f"{OUT.stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
