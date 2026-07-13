# VX-0057 — Customer Product & Safety Guide

Customer-facing hardware information + UL/ANSI-style safety document for the
**Viaanix VX-0057 "RTU Board"**. Distilled from the internal review in
[../main-board.md](../main-board.md) with all internal engineering detail removed
(no part numbers, net names, GPIO/pin assignments, jumper/connector reference
designators, schematic revision, bench config, or "items to verify").

## Deliverables
- **[VX-0057-Product-Safety-Guide.pdf](VX-0057-Product-Safety-Guide.pdf)** — 6-page print-ready guide (US Letter).
- **[VX-0057-Product-Safety-Guide.docx](VX-0057-Product-Safety-Guide.docx)** — editable Word version (same content).

Layout: pages 1–2 are the customer product overview + specifications; pages 3–6
are the safety section — ANSI Z535 hazard panels (DANGER / WARNING / CAUTION /
NOTICE), a safety-symbol legend, and handling / installation / disposal guidance.

## How it's built (single source of truth)
| File | Role |
|---|---|
| `content.py` | All text, specs, hazards, handling — **edit here**; both outputs read it |
| `icons.py` | Safety/info pictograms as SVG (ISO-style hazard triangles + line glyphs) |
| `rasterize.py` | Renders each SVG → transparent PNG via Chrome headless (for the DOCX) |
| `build_html.py` | Builds the styled HTML and prints the PDF via Chrome headless |
| `build_docx.py` | Builds the editable DOCX (shaded hazard tables, icons, header/footer, page numbers) |
| `assets/` | `board.png` (product image) + `icons/*.png` (rasterized icons) |

### Regenerate
```bash
python rasterize.py      # only if icons.py changed
python build_html.py     # -> .html + .pdf
python build_docx.py     # -> .docx
```
Requires `python-docx` and a Chrome/Edge install. The PDF uses a fixed-sheet
layout (one `.sheet` div per page) so pagination is fully controlled.

> Content accuracy and "no internal-info leakage" were checked by an adversarial
> multi-reviewer pass against `../main-board.md`. No regulatory certification
> (UL/FCC/CE) is asserted — the compliance note defers to the product label.
