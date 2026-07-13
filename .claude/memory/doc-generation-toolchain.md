---
name: doc-generation-toolchain
description: How to produce polished Word + PDF deliverables on this bench (icons, hazard panels, QA rendering)
metadata:
  type: reference
---

This Windows bench can produce **publication-quality Word + PDF** documents without
LibreOffice/pandoc/wkhtmltopdf (none installed). Toolchain that works here:

- **PDF from HTML:** Chrome headless prints HTML→PDF.
  `"C:\Program Files\Google\Chrome\Application\chrome.exe" --headless=new --disable-gpu --no-pdf-header-footer --print-to-pdf=out.pdf file:///abs/path.html`
  (Edge at `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe` works too.)
  Chrome's `position:fixed` header/footer for print is **unreliable** (offset interpretation
  varies) — use **fixed-height `.sheet` divs** (8.5in×11in, `@page{margin:0}`,
  `page-break-after:always`) with per-sheet header/footer for fully controlled pagination.
- **Word (.docx):** `python-docx` (pip-install it; not preinstalled). Shaded cells via
  `w:shd`, table borders via `w:tblBorders`, page numbers via `PAGE`/`NUMPAGES` field codes,
  `w:cantSplit`+`w:keepNext` to stop panels splitting across pages.
- **Icons:** `cairosvg` **cannot load on Windows** (no libcairo DLL). Instead rasterize
  SVG→transparent PNG with Chrome: `--headless=new --default-background-color=00000000
  --force-device-scale-factor=4 --screenshot=icon.png file:///wrapper.html` (SVG in a
  margin:0 HTML wrapper). PNGs embed into both HTML and DOCX.
- **QA rendering (can't view .docx/.pdf directly):** the Read tool lacks `pdftoppm`/poppler.
  Render PDF→PNG with **PyMuPDF** (`pip install pymupdf`; `fitz.open(pdf).get_pixmap(dpi=110)`)
  then Read the PNG. **Microsoft Word IS installed** and scriptable via PowerShell COM —
  `New-Object -ComObject Word.Application`, `Documents.Open`, `Fields.Update`, `SaveAs(ref,17)`
  — to convert DOCX→PDF for visual QA and to compute page count (`ComputeStatistics(2)`).

Single-source pattern that worked: one `content.py` data module imported by both
`build_html.py` and `build_docx.py`, so the two formats never diverge. Example deliverable:
`docs/hardware/customer/` (VX-0057 customer Product & Safety Guide, UL/ANSI Z535 styling).
Customer docs must scrub internal detail (MPNs, net names, GPIO/pins, ref-designators,
flagged-items) and must NOT assert UL/FCC/CE certification — defer to the product label.
See [[bench-power-and-observe]].
