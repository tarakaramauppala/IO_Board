#!/usr/bin/env python3
"""Tank-monitor results dashboard (static HTML generator).

Reads the per-scope result files the harness writes under
  results/<run_id>/tank-monitor/<scope>.json      (envelope: {scope, run_id, utc, result})
and renders a single self-contained page at dashboard/index.html:
  - a runs table (one row per run_id, columns S1..S5, colored by verdict)
  - a drill-in per run with the detail of each scope + links to the .rtt.log sidecars

Read-only: it never touches the board, the J-Link, or the source repos. Run it any
time after a `python tests/tank-monitor/run.py ...` and refresh the page.

Usage:
    python dashboard/build.py            # writes dashboard/index.html
    python dashboard/build.py --open     # also opens it in the browser

ASCII-only output (Windows cp1252 console safe).
"""
from __future__ import annotations
import argparse
import glob
import html
import json
import os
import sys
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
RESULTS = os.path.join(REPO, "results")

# scope prefix -> (short column label, long title)
SCOPE_COLS = [
    ("S1", "Boot & identity"),
    ("S2", "IO/power self-test"),
    ("S3", "Threshold events"),
    ("S4", "Relay hysteresis"),
    ("S5", "Siren / light"),
]
SCOPE_KEYS = [c[0] for c in SCOPE_COLS]


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
def _verdict(result: dict) -> str:
    """Mirror tankmon.write_result: prefer result.overall, else passed/passed_core, else REVIEW."""
    ov = (result or {}).get("overall")
    if isinstance(ov, str) and ov:
        head = ov.strip().upper()
        if head.startswith("PASS"):
            return "PASS"
        if head.startswith("FAIL"):
            return "FAIL"
        if head.startswith("REVIEW"):
            return "REVIEW"
    if (result or {}).get("passed") or (result or {}).get("passed_core"):
        return "PASS"
    return "REVIEW"


def _scope_prefix(scope: str) -> str:
    """'S3-thresholds' -> 'S3'; tolerate anything unexpected."""
    return (scope or "").split("-", 1)[0].upper()


def load_runs() -> dict:
    """Return {run_id: {"utc": str, "scopes": {S1..S5: {envelope + verdict + rtt_log}}}}."""
    runs: dict = {}
    for path in glob.glob(os.path.join(RESULTS, "*", "tank-monitor", "*.json")):
        try:
            with open(path, encoding="utf-8") as f:
                env = json.load(f)
        except Exception as e:
            print(f"  [skip] {os.path.relpath(path, REPO)}: {e}")
            continue
        run_id = env.get("run_id") or os.path.basename(os.path.dirname(os.path.dirname(path)))
        scope = env.get("scope") or os.path.splitext(os.path.basename(path))[0]
        key = _scope_prefix(scope)
        rtt = os.path.splitext(path)[0] + ".rtt.log"
        entry = runs.setdefault(run_id, {"utc": env.get("utc", ""), "scopes": {}})
        if env.get("utc") and env["utc"] > entry["utc"]:
            entry["utc"] = env["utc"]
        entry["scopes"][key] = {
            "scope": scope,
            "utc": env.get("utc", ""),
            "result": env.get("result", {}) or {},
            "verdict": _verdict(env.get("result", {}) or {}),
            "rtt_log": os.path.relpath(rtt, HERE).replace("\\", "/") if os.path.isfile(rtt) else None,
        }
    return runs


# ---------------------------------------------------------------------------
# Render helpers
# ---------------------------------------------------------------------------
def esc(x) -> str:
    return html.escape("" if x is None else str(x))


def cell(verdict: str) -> str:
    cls = {"PASS": "pass", "FAIL": "fail", "REVIEW": "review"}.get(verdict, "none")
    return f'<td class="v {cls}">{esc(verdict)}</td>'


def kv_table(pairs) -> str:
    rows = "".join(f"<tr><th>{esc(k)}</th><td>{esc(v)}</td></tr>" for k, v in pairs)
    return f'<table class="kv">{rows}</table>'


def steps_table(steps, cols) -> str:
    if not steps:
        return '<p class="muted">no steps recorded</p>'
    head = "".join(f"<th>{esc(h)}</th>" for _, h in cols)
    body = []
    for s in steps:
        tds = []
        for key, _ in cols:
            v = s.get(key)
            if isinstance(v, (list, dict)):
                v = json.dumps(v, ensure_ascii=True)
            tds.append(f"<td>{esc(v)}</td>")
        body.append("<tr>" + "".join(tds) + "</tr>")
    return f'<table class="steps"><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>'


def render_scope_detail(key: str, sc: dict) -> str:
    r = sc["result"]
    parts = [f'<div class="scope"><h4>{esc(key)} - {esc(sc["scope"])} '
             f'<span class="badge {sc["verdict"].lower()}">{esc(sc["verdict"])}</span></h4>']
    if sc.get("rtt_log"):
        parts.append(f'<p><a href="{esc(sc["rtt_log"])}">RTT log</a></p>')

    if key == "S1":
        parts.append(kv_table([
            ("app_type", r.get("app_type")), ("version", r.get("version")),
            ("title", r.get("title")), ("compile_time", r.get("compile_time")),
            ("app_init", r.get("app_init")),
        ]))
        if r.get("reasons"):
            parts.append(f'<p class="reasons">reasons: {esc("; ".join(r["reasons"]))}</p>')

    elif key == "S2":
        p = r.get("power", {}) or {}
        parts.append(kv_table([
            ("brackets", f'started={r.get("started")} ended={r.get("ended")}'),
            ("ext_memory", r.get("ext_memory")),
            ("power main", p.get("main")), ("ext12v", p.get("ext12v")),
            ("psc_ac", p.get("psc_ac")), ("psc_pwr", p.get("psc_pwr")), ("psc_batt", p.get("psc_batt")),
            ("rs232", r.get("rs232")), ("rs485", r.get("rs485")),
        ]))
        an = r.get("analog", {}) or {}
        if an:
            rows = "".join(
                f"<tr><td>AN{esc(ch)}</td><td>{esc(v.get('result'))}</td><td>{esc(v.get('ua'))}</td></tr>"
                for ch, v in sorted(an.items(), key=lambda kv: str(kv[0])))
            parts.append('<table class="steps"><thead><tr><th>chan</th><th>result</th>'
                         f'<th>uA</th></tr></thead><tbody>{rows}</tbody></table>')
        if r.get("reasons"):
            parts.append(f'<p class="reasons">core reasons: {esc("; ".join(r["reasons"]))}</p>')

    elif key == "S3":
        parts.append(f'<p class="muted">injector: {esc(r.get("injector", "?"))} '
                     f'&middot; {esc(r.get("deferred_cloud", ""))}</p>')
        parts.append(steps_table(r.get("steps"), [
            ("ai", "AI"), ("ao", "AO"), ("label", "band"), ("applied_ma", "mA"),
            ("expected_band", "expected"), ("relay_transitions", "relay xitions")]))

    elif key == "S4":
        parts.append(f'<p class="muted">injector: {esc(r.get("injector", "?"))} '
                     f'&middot; {esc(r.get("note", ""))}</p>')
        parts.append(steps_table(r.get("steps"), [
            ("ai", "AI"), ("relay", "relay"), ("ao", "AO"), ("label", "step"),
            ("applied_ma", "mA"), ("relay_transitions", "relay xitions"),
            ("continuity", "continuity")]))

    elif key == "S5":
        parts.append(f'<p class="muted">expected: {esc(r.get("expected", ""))} '
                     f'&middot; {esc(r.get("deferred_cloud", ""))}</p>')
        parts.append(steps_table(r.get("steps"), [
            ("ai", "AI"), ("label", "step"), ("applied_ma", "mA"),
            ("siren_volts", "V"), ("siren_on", "siren on")]))

    else:
        parts.append(f"<pre>{esc(json.dumps(r, indent=2, ensure_ascii=True))}</pre>")

    parts.append("</div>")
    return "".join(parts)


CSS = """
:root{--bg:#f6f7f9;--card:#fff;--fg:#1a1d21;--muted:#6b7280;--line:#e4e7eb;
--pass:#137a3f;--pass-bg:#e6f4ea;--fail:#b3261e;--fail-bg:#fce8e6;
--review:#8a6100;--review-bg:#fdf3d7;--none:#9aa0a6;--accent:#1f6feb;}
@media (prefers-color-scheme:dark){:root{--bg:#0f1216;--card:#171b21;--fg:#e6e8eb;
--muted:#9aa0a6;--line:#2a2f37;--pass:#7ee2a8;--pass-bg:#10331f;--fail:#f5a6a0;
--fail-bg:#3a1512;--review:#f0cf6b;--review-bg:#33280a;--none:#5b616b;--accent:#589bff;}}
*{box-sizing:border-box}
body{margin:0;padding:24px;background:var(--bg);color:var(--fg);
font:14px/1.5 system-ui,Segoe UI,Roboto,Arial,sans-serif}
h1{font-size:20px;margin:0 0 2px} h2{font-size:16px;margin:28px 0 10px}
.sub{color:var(--muted);margin:0 0 18px}
.wrap{max-width:1100px;margin:0 auto}
table{border-collapse:collapse;width:100%;background:var(--card);
border:1px solid var(--line);border-radius:8px;overflow:hidden}
th,td{padding:8px 10px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
thead th{background:transparent;color:var(--muted);font-weight:600;font-size:12px;
text-transform:uppercase;letter-spacing:.03em}
tr:last-child td{border-bottom:none}
td.v{font-weight:700;text-align:center;white-space:nowrap}
.v.pass{color:var(--pass);background:var(--pass-bg)}
.v.fail{color:var(--fail);background:var(--fail-bg)}
.v.review{color:var(--review);background:var(--review-bg)}
.v.none{color:var(--none)}
.runcol a{color:var(--accent);text-decoration:none;font-weight:600}
.runcol a:hover{text-decoration:underline}
.badge{font-size:11px;font-weight:700;padding:2px 8px;border-radius:999px;vertical-align:middle}
.badge.pass{color:var(--pass);background:var(--pass-bg)}
.badge.fail{color:var(--fail);background:var(--fail-bg)}
.badge.review{color:var(--review);background:var(--review-bg)}
.run{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:16px 18px;margin:14px 0}
.run>summary{cursor:pointer;font-weight:700;font-size:15px;list-style:none}
.run>summary::-webkit-details-marker{display:none}
.run>summary .when{color:var(--muted);font-weight:400;font-size:12px;margin-left:8px}
.scope{margin:14px 0;padding-top:12px;border-top:1px dashed var(--line)}
.scope h4{margin:0 0 8px;font-size:14px}
table.kv{width:auto;min-width:340px}
table.kv th{width:150px;color:var(--muted);font-weight:600;text-transform:none;
letter-spacing:0;font-size:13px}
.steps{margin-top:8px}
.muted{color:var(--muted);font-size:13px;margin:6px 0}
.reasons{color:var(--fail);font-size:13px}
a{color:var(--accent)}
pre{background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:10px;
overflow-x:auto;font-size:12px}
.empty{background:var(--card);border:1px dashed var(--line);border-radius:10px;
padding:40px;text-align:center;color:var(--muted)}
footer{color:var(--muted);font-size:12px;margin-top:28px;border-top:1px solid var(--line);
padding-top:12px}
"""


def render(runs: dict, generated_utc: str) -> str:
    order = sorted(runs.keys(), reverse=True)  # run_id is an ISO-ish stamp -> lexical = chrono
    # summary table
    if order:
        head = "".join(f'<th title="{esc(t)}">{esc(k)}</th>' for k, t in SCOPE_COLS)
        rows = []
        for rid in order:
            sc = runs[rid]["scopes"]
            cells = []
            for key in SCOPE_KEYS:
                if key in sc:
                    cells.append(cell(sc[key]["verdict"]))
                else:
                    cells.append('<td class="v none">-</td>')
            when = esc(runs[rid]["utc"])
            rows.append(f'<tr><td class="runcol"><a href="#run-{esc(rid)}">{esc(rid)}</a>'
                        f'<div class="muted">{when}</div></td>{"".join(cells)}</tr>')
        summary = ('<table><thead><tr><th>Run</th>' + head + '</tr></thead><tbody>'
                   + "".join(rows) + '</tbody></table>')
    else:
        summary = ('<div class="empty">No runs yet. Run '
                   '<code>python tests/tank-monitor/run.py all</code> '
                   'then re-run <code>python dashboard/build.py</code>.</div>')

    # per-run detail
    details = []
    for rid in order:
        blocks = []
        for key in SCOPE_KEYS:
            if key in runs[rid]["scopes"]:
                blocks.append(render_scope_detail(key, runs[rid]["scopes"][key]))
        details.append(
            f'<details class="run" id="run-{esc(rid)}" open><summary>{esc(rid)}'
            f'<span class="when">{esc(runs[rid]["utc"])}</span></summary>'
            + "".join(blocks) + '</details>')

    legend = ('<p class="sub">Verdict: '
              '<span class="badge pass">PASS</span> automatic checks passed &middot; '
              '<span class="badge fail">FAIL</span> a core check failed &middot; '
              '<span class="badge review">REVIEW</span> needs a human / cloud-deferred '
              '(S3/S4/S5 events are verified cloud-side once the AWS/ThingsBoard path is wired).</p>')

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tank Monitor - QA results</title>
<style>{CSS}</style></head>
<body><div class="wrap">
<h1>Tank Monitor (VX-0057) - QA results</h1>
<p class="sub">Static view over <code>results/*/tank-monitor/</code>. Read-only; it does not
touch the board or the J-Link. Generated {esc(generated_utc)}.</p>
{legend}
<h2>Runs</h2>
{summary}
<h2>Details</h2>
{"".join(details) if details else ""}
<footer>io-board-testing &middot; Tank Monitor test plan S1-S5 &middot;
regenerate with <code>python dashboard/build.py</code></footer>
</div></body></html>"""


def main():
    ap = argparse.ArgumentParser(description="Build the tank-monitor results dashboard")
    ap.add_argument("--open", action="store_true", help="open index.html in the browser after building")
    args = ap.parse_args()

    runs = load_runs()
    # generated timestamp: read-only, no wall clock needed for determinism; use file scan count
    generated = f"from {len(runs)} run(s)"
    out = os.path.join(HERE, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(render(runs, generated))
    print(f"  wrote {os.path.relpath(out, REPO)}  ({len(runs)} run(s), "
          f"{sum(len(r['scopes']) for r in runs.values())} scope file(s))")
    if not runs:
        print("  (no results yet - run tests/tank-monitor/run.py first)")
    if args.open:
        webbrowser.open("file://" + out.replace("\\", "/"))


if __name__ == "__main__":
    main()
