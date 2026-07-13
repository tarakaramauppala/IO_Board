# -*- coding: utf-8 -*-
"""Generate the UL/ANSI-style HTML for the VX-0057 guide and render it to PDF.

Fixed-sheet layout: each .sheet is exactly one US-Letter page with its own
header and footer, so pagination is fully controlled and nothing reflows or
clips. Content is distributed across sheets by hand.
"""
import os
import subprocess
import html

import content as C
import icons as ic

HERE = os.path.dirname(os.path.abspath(__file__))
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
HTML_PATH = os.path.join(HERE, "VX-0057-Product-Safety-Guide.html")
PDF_PATH = os.path.join(HERE, "VX-0057-Product-Safety-Guide.pdf")

M = C.META
esc = lambda s: html.escape(str(s))
TOTAL = 6


def feature_cols():
    cols = []
    for title, items in C.FEATURES:
        lis = "".join(f"<li>{esc(x)}</li>" for x in items)
        cols.append(f'<div class="fcol"><h4>{esc(title)}</h4><ul>{lis}</ul></div>')
    return "".join(cols)


def spec_rows():
    return "".join(f'<tr><th>{esc(k)}</th><td>{esc(v)}</td></tr>' for k, v in C.SPECS)


def io_rows():
    return "".join(
        f'<tr><td class="io-fn">{esc(fn)}</td><td class="io-qty">{esc(q)}</td><td>{esc(n)}</td></tr>'
        for fn, q, n in C.IO_TABLE
    )


def symbol_cards():
    out = ""
    for name, term, meaning in C.SYMBOLS:
        out += (
            f'<div class="sym"><div class="sym-ico">{ic.svg(name, 46)}</div>'
            f'<div class="sym-txt"><b>{esc(term)}</b><span>{esc(meaning)}</span></div></div>'
        )
    return out


def hazard_panel(h):
    lvl = h["level"]
    c = C.HAZARD_COLORS[lvl]
    # ANSI Z535: NOTICE carries no safety-alert symbol — signal word only.
    icon = "" if lvl == "NOTICE" else f'<span class="haz-ico">{ic.svg(h["icon"], 30)}</span>'
    return (
        f'<div class="hazard" style="border-color:{c["bg"]}">'
        f'<div class="haz-head" style="background:{c["bg"]};color:{c["fg"]}">'
        f'{icon}<span class="haz-word">{lvl}</span></div>'
        f'<div class="haz-body"><div class="haz-title">{esc(h["title"])}</div>'
        f'<p>{esc(h["text"])}</p></div></div>'
    )


def handling_blocks():
    out = ""
    for name, head, paras in C.HANDLING:
        ps = "".join(f"<p>{esc(p)}</p>" for p in paras)
        out += (
            f'<div class="hb"><div class="hb-ico">{ic.svg(name, 38)}</div>'
            f'<div class="hb-txt"><h4>{esc(head)}</h4>{ps}</div></div>'
        )
    return out


def footer(page):
    return (
        f'<div class="foot">'
        f'<span>{esc(M["manufacturer"])} {esc(M["model"])} — {esc(M["product"])}</span>'
        f'<span>{esc(M["doc_no"])} Rev {esc(M["revision"])} · {esc(M["date"])}</span>'
        f'<span>Page {page} of {TOTAL}</span></div>'
    )


def brand_header(tag):
    return (
        f'<div class="brandbar">{ic.svg("logo", 34, "logo")}'
        f'<div class="bh-name"><b>{esc(M["manufacturer"])}</b>'
        f'<span>{esc(M["subtitle"])}</span></div>'
        f'<span class="bh-tag">{esc(tag)}</span></div>'
    )


def build_html():
    P = [hazard_panel(h) for h in C.HAZARDS]   # 9 panels, severity-ordered

    s1 = f"""
    <section class="sheet">
      {brand_header("Product Information")}
      <div class="titleblock">
        <div class="tb-model">{esc(M['model'])}</div>
        <div class="tb-name">{esc(M['product'])}</div>
        <div class="tb-sub">{esc(M['subtitle'])}</div>
        <div class="tb-tag">{esc(M['tagline'])}</div>
      </div>
      <div class="herorow">
        <div class="hero"><img src="assets/board.png" alt="VX-0057 board"></div>
        <div class="overview"><h3>Product Overview</h3><p>{esc(C.OVERVIEW)}</p>
          <div class="badges">
            <span>LTE Cat-1 + GPS</span><span>LoRaWAN 915 MHz</span>
            <span>Bluetooth LE</span><span>Universal I/O</span>
          </div>
        </div>
      </div>
      <h3 class="kf">Key Features</h3>
      <div class="features">{feature_cols()}</div>
      {footer(1)}
    </section>"""

    s2 = f"""
    <section class="sheet">
      {brand_header("Specifications")}
      <h3 class="top">Technical Specifications</h3>
      <table class="spec">{spec_rows()}</table>
      <h3>Field Interfaces at a Glance</h3>
      <table class="io"><thead><tr><th>Interface</th><th>Qty</th><th>Notes</th></tr></thead>
        <tbody>{io_rows()}</tbody></table>
      <p class="note">Note: the VX-0057 ships in Tank Monitor, Callbox, or RTU
      configurations. The interfaces exercised depend on the configuration ordered.
      Mechanical and environmental ratings are provided on the product label and in
      the deployment datasheet available from Viaanix.</p>
      {footer(2)}
    </section>"""

    s3 = f"""
    <section class="sheet">
      {brand_header("Safety Information")}
      <h2 class="safety-h">Important Safety Information</h2>
      <div class="readfirst"><div class="rf-ico">{ic.svg('alert', 44)}</div>
        <p>{esc(C.READ_FIRST)}</p></div>
      <h3>Safety Symbols Used in This Document</h3>
      <div class="symbols">{symbol_cards()}</div>
      <h3>Hazard Notices</h3>
      {''.join(P[0:2])}
      {footer(3)}
    </section>"""

    s4 = f"""
    <section class="sheet">
      {brand_header("Safety Information")}
      <h3 class="top">Hazard Notices (continued)</h3>
      {''.join(P[2:6])}
      {footer(4)}
    </section>"""

    s5 = f"""
    <section class="sheet">
      {brand_header("Safety Information")}
      <h3 class="top">Hazard Notices (continued)</h3>
      {''.join(P[6:9])}
      {footer(5)}
    </section>"""

    s6 = f"""
    <section class="sheet">
      {brand_header("Handling & Installation")}
      <h2 class="safety-h">Handling, Installation &amp; Disposal</h2>
      <div class="handling">{handling_blocks()}</div>
      <div class="compliance"><div class="cmp-ico">{ic.svg('book', 34)}</div>
        <div><h4>Compliance &amp; Certification</h4><p>{esc(C.COMPLIANCE)}</p></div></div>
      <div class="endnote">{esc(M['copyright'])}</div>
      {footer(6)}
    </section>"""

    doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{esc(M['manufacturer'])} {esc(M['model'])} — Product &amp; Safety Guide</title>
<style>{CSS}</style></head>
<body>{s1}{s2}{s3}{s4}{s5}{s6}</body></html>"""

    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(doc)
    return HTML_PATH


CSS = """
* { box-sizing: border-box; }
:root{ --ink:#1b2430; --muted:#5b6675; --line:#d9dee6; --navy:#0E2A47;
  --teal:#0f6fa3; --soft:#f4f6f9; }
@page { size: Letter; margin: 0; }
html,body{ margin:0; padding:0; }
body{ font-family:"Segoe UI",Arial,Helvetica,sans-serif; color:var(--ink);
  font-size:10.5pt; line-height:1.42; -webkit-print-color-adjust:exact; print-color-adjust:exact; }
.sheet{ position:relative; width:8.5in; height:11in; padding:0.55in 0.62in 0.72in;
  page-break-after:always; overflow:hidden; background:#fff; }
.sheet:last-child{ page-break-after:auto; }

/* brand header */
.brandbar{ display:flex; align-items:center; gap:10px; border-bottom:3px solid var(--navy);
  padding-bottom:8px; margin-bottom:14px; }
.brandbar .logo{ width:34px; height:34px; flex:0 0 auto; }
.bh-name{ display:flex; flex-direction:column; line-height:1.1; }
.bh-name b{ font-size:15pt; letter-spacing:2px; color:var(--navy); }
.bh-name span{ font-size:7.7pt; color:var(--muted); letter-spacing:.3px; }
.bh-tag{ margin-left:auto; font-size:8pt; font-weight:700; letter-spacing:1.5px;
  text-transform:uppercase; color:#fff; background:var(--navy); padding:4px 10px; border-radius:3px; }

/* title block */
.titleblock{ margin:6px 0 14px; }
.tb-model{ font-size:11pt; font-weight:700; color:var(--teal); letter-spacing:3px; }
.tb-name{ font-size:30pt; font-weight:800; color:var(--navy); line-height:1; margin-top:2px; }
.tb-sub{ font-size:12pt; color:var(--ink); margin-top:4px; }
.tb-tag{ font-size:10pt; color:var(--muted); font-style:italic; margin-top:3px; }

/* hero + overview */
.herorow{ display:flex; gap:18px; margin-bottom:8px; }
.hero{ flex:0 0 2.5in; background:linear-gradient(160deg,#0E2A47,#15436e);
  border-radius:8px; padding:12px; display:flex; align-items:center; justify-content:center; }
.hero img{ max-width:100%; max-height:3.5in; border-radius:4px; }
.overview{ flex:1; }
.overview h3, .kf{ margin:0 0 6px; }
.overview p{ margin:0 0 10px; text-align:justify; }
.badges{ display:flex; flex-wrap:wrap; gap:6px; }
.badges span{ font-size:8pt; font-weight:600; color:var(--navy); background:#e6eef6;
  border:1px solid #c7d6e6; border-radius:20px; padding:3px 11px; }

h2,h3,h4{ color:var(--navy); }
h3{ font-size:12.5pt; border-bottom:1.5px solid var(--line); padding-bottom:3px; margin:14px 0 8px; }
h3.top{ margin-top:2px; }
h4{ margin:0 0 4px; font-size:10.5pt; }

/* features */
.features{ display:flex; gap:16px; }
.fcol{ flex:1; }
.fcol h4{ color:var(--teal); border-left:3px solid var(--teal); padding-left:7px; }
.fcol ul{ margin:6px 0 0; padding-left:16px; }
.fcol li{ margin-bottom:4px; }

/* tables */
table{ width:100%; border-collapse:collapse; margin-bottom:6px; }
table.spec th{ width:38%; text-align:left; background:var(--soft); color:var(--navy);
  font-weight:700; padding:5px 9px; border:1px solid var(--line); vertical-align:top; }
table.spec td{ padding:5px 9px; border:1px solid var(--line); }
table.spec tr:nth-child(even) td{ background:#fbfcfd; }
table.io thead th{ background:var(--navy); color:#fff; text-align:left; padding:6px 9px; border:1px solid var(--navy); }
table.io td{ padding:5px 9px; border:1px solid var(--line); }
table.io tr:nth-child(even) td{ background:#fbfcfd; }
.io-fn{ font-weight:600; color:var(--navy); width:26%; }
.io-qty{ text-align:center; width:8%; font-weight:700; }
.note{ font-size:9pt; color:var(--muted); font-style:italic; margin-top:6px; }

/* safety */
.safety-h{ font-size:18pt; margin:2px 0 12px; border-bottom:3px solid var(--navy); padding-bottom:6px; }
.readfirst{ display:flex; gap:12px; align-items:center; background:#fff8e1;
  border:2px solid #F7C600; border-radius:6px; padding:10px 14px; margin-bottom:14px; }
.readfirst p{ margin:0; font-weight:600; }
.rf-ico{ flex:0 0 auto; }
.symbols{ display:grid; grid-template-columns:1fr 1fr; gap:9px 18px; margin-bottom:6px; }
.sym{ display:flex; gap:10px; align-items:center; }
.sym-ico{ flex:0 0 46px; }
.sym-txt{ display:flex; flex-direction:column; line-height:1.25; }
.sym-txt b{ color:var(--navy); }
.sym-txt span{ font-size:8.6pt; color:var(--muted); }

/* hazard panels (ANSI Z535.4) */
.hazard{ border:2px solid; border-radius:5px; overflow:hidden; margin:11px 0; }
.haz-head{ display:flex; align-items:center; gap:9px; padding:6px 12px; }
.haz-ico{ flex:0 0 auto; display:flex; }
.haz-word{ font-size:14pt; font-weight:800; letter-spacing:3px; }
.haz-body{ background:#fff; padding:9px 14px 11px; }
.haz-title{ font-weight:700; color:var(--navy); margin-bottom:2px; }
.haz-body p{ margin:0; }

/* handling */
.hb{ display:flex; gap:12px; margin-bottom:11px; }
.hb-ico{ flex:0 0 38px; padding-top:2px; }
.hb-txt h4{ color:var(--teal); margin-bottom:2px; }
.hb-txt p{ margin:0; }
.compliance{ display:flex; gap:12px; background:var(--soft); border:1px solid var(--line);
  border-left:4px solid var(--teal); border-radius:5px; padding:10px 14px; margin-top:6px; }
.compliance p{ margin:0; font-size:9.4pt; }
.cmp-ico{ flex:0 0 auto; }
.endnote{ font-size:8.2pt; color:var(--muted); text-align:center; margin-top:14px; }

/* footer */
.foot{ position:absolute; left:0.62in; right:0.62in; bottom:0.34in;
  display:flex; justify-content:space-between; font-size:7.6pt; color:var(--muted);
  border-top:1px solid var(--line); padding-top:5px; }
"""


def render_pdf():
    subprocess.run(
        [
            CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
            f"--print-to-pdf={PDF_PATH}", "file:///" + HTML_PATH.replace("\\", "/"),
        ],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


if __name__ == "__main__":
    build_html()
    render_pdf()
    print("HTML:", HTML_PATH)
    print("PDF :", PDF_PATH, "exists" if os.path.exists(PDF_PATH) else "MISSING")
