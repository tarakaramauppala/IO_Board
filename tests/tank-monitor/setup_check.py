#!/usr/bin/env python3
"""VX-0057 IO-board QA station - setup preflight wizard.

Verifies (and, from the CLI, auto-installs) everything the program-and-test station needs, ticking
each requirement like a pipeline. Safe to re-run. Built so the station can be brought up on ANY bench
machine: just run `python setup_check.py` (or double-click "Start-IOBoard-QA.bat").

Two entry points (mirrors the Siffron setup_check pattern):
  * CLI     - `python setup_check.py`  -> prints the checklist, AUTO-INSTALLS missing pip packages,
              and creates secrets/station.env from the example if missing.
  * Library - `run_checks(install=False)` -> returns the checklist as data (for a dashboard /preflight
              page). The library path NEVER installs or writes.

Output is ASCII-only (the Windows console is cp1252 and chokes on unicode ticks).
"""
from __future__ import annotations

import glob
import importlib
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(ROOT, "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# import-name -> pip-name for everything the station imports at runtime.
REQUIRED_PKGS = [
    ("serial", "pyserial"),          # PSU (GPD-3303S), meter (GDM-8251A), injector serial
    ("pylink", "pylink-square"),     # J-Link flash + RTT capture
    ("pymodbus", "pymodbus"),        # Waveshare Modbus AO current injector
    ("openpyxl", "openpyxl"),        # secrets/device_map.xlsx (multi-board VDUI list)
    ("requests", "requests"),        # ThingsBoard / VX Olympus cloud verify
    ("dotenv", "python-dotenv"),     # tb_client loads secrets/station.env
]

OK, FIXED, WARN, FAIL = "OK", "FIXED", "WARN", "FAIL"


def _item(category, name, status, detail="", fix=""):
    return {"category": category, "name": name, "status": status, "detail": detail, "fix": fix}


def _com_ports():
    try:
        from serial.tools import list_ports
        return [p.device for p in list_ports.comports()]
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Individual checks                                                            #
# --------------------------------------------------------------------------- #
def _check_python(out):
    v = sys.version_info
    # config.py / tankmon.py use PEP 604 `X | None` type hints -> need 3.10+.
    st = OK if v >= (3, 10) else FAIL
    out.append(_item("Runtime", "Python >= 3.10", st, "%d.%d.%d" % (v.major, v.minor, v.micro),
                     "" if st == OK else "Install Python 3.10+ and re-run"))


def _check_packages(out, install):
    for mod, pip_name in REQUIRED_PKGS:
        try:
            importlib.import_module(mod)
            out.append(_item("Python packages", pip_name, OK))
            continue
        except Exception:
            pass
        if not install:
            out.append(_item("Python packages", pip_name, FAIL, "not installed", "pip install %s" % pip_name))
            continue
        print("     installing %s ..." % pip_name, flush=True)
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", pip_name],
                           check=False, capture_output=True, text=True, timeout=300)
            importlib.invalidate_caches()
            importlib.import_module(mod)
            out.append(_item("Python packages", pip_name, FIXED, "installed"))
        except Exception as e:
            out.append(_item("Python packages", pip_name, FAIL, str(e)[:50], "pip install %s" % pip_name))


def _check_jlink_lib(out):
    try:
        import pylink
        pylink.JLink()  # loads the SEGGER JLinkARM DLL
        out.append(_item("Tools", "SEGGER J-Link library", OK))
    except Exception as e:
        out.append(_item("Tools", "SEGGER J-Link library", FAIL, str(e)[:50],
                         "Install SEGGER J-Link software (JLinkARM DLL)"))


def _check_nrfjprog(out):
    # Optional: the station flashes via pylink; nrfjprog is only handy for --recover / --ids.
    if not shutil.which("nrfjprog"):
        out.append(_item("Tools", "nrfjprog (optional)", WARN, "not on PATH",
                         "Optional - install nRF Command Line Tools for --recover / probe listing"))
        return
    try:
        r = subprocess.run(["nrfjprog", "--version"], capture_output=True, text=True, timeout=20)
        out.append(_item("Tools", "nrfjprog (optional)", OK, (r.stdout.strip().splitlines() or [""])[0][:50]))
    except Exception as e:
        out.append(_item("Tools", "nrfjprog (optional)", WARN, "present but not responding: %s" % str(e)[:40]))


def _check_config(out):
    """Import config.py and report the resolved ports/serials/firmware it will use."""
    try:
        import config as C
    except Exception as e:
        out.append(_item("Configuration", "config.py imports", FAIL, str(e)[:60],
                         "Fix the import error above"))
        return None
    out.append(_item("Configuration", "config.py imports", OK,
                     "J-Link %s | PSU %s | meter %s@%s | injector %s"
                     % (C.JLINK_SERIAL, C.PSU_PORT or "-", C.METER_PORT or "-",
                        getattr(C, "METER_BAUD", "?"), C.WAVESHARE_PORT or "-")))
    return C


def _check_secrets(out, install):
    envp = os.path.join(REPO, "secrets", "station.env")
    examp = os.path.join(REPO, "secrets", "station.env.example")
    if not os.path.exists(envp):
        if install and os.path.exists(examp):
            try:
                shutil.copy(examp, envp)
                out.append(_item("Secrets", "secrets/station.env", FIXED,
                                 "created from example - FILL IN cloud creds + device keys"))
            except Exception as e:
                out.append(_item("Secrets", "secrets/station.env", FAIL, str(e)[:50]))
        else:
            out.append(_item("Secrets", "secrets/station.env", WARN, "missing",
                             "copy secrets/station.env.example -> secrets/station.env and fill it in"))
        return
    out.append(_item("Secrets", "secrets/station.env", OK))


def _check_device_keys(out, C):
    if C is None:
        return
    # Placeholder defaults mean secrets/station.env wasn't filled -> flashing would burn wrong keys.
    if C.DEVICE_APP_KEY in ("", "00000000000000000000000000000000") or C.DEVICE_UUID.startswith("FFFF0000"):
        out.append(_item("Secrets", "device VDUI + LoRaWAN keys", WARN,
                         "placeholder (VDUI=%s)" % C.DEVICE_UUID,
                         "Set DEVICE_UUID/APP_EUI/APP_KEY/TB_DEVICE_ID in secrets/station.env"))
    else:
        out.append(_item("Secrets", "device VDUI + LoRaWAN keys", OK, "VDUI %s" % C.DEVICE_UUID))


def _check_firmware(out, C):
    if C is None:
        return
    for label, path, hint in (
        ("testbench fw (Stage A)", C.TESTBENCH_MERGED, "vendor rtu-test merged.hex"),
        ("production fw (Stage B)", C.TANK_IMAGE, "tank-monitor merged .hex"),
    ):
        if path and os.path.exists(path):
            out.append(_item("Firmware", label, OK, os.path.basename(path)))
        else:
            out.append(_item("Firmware", label, WARN, "not found: %s" % (path or "(unset)"),
                             "Provide %s (or set the env/path in config.py)" % hint))


def _check_serial_ports(out, C):
    if C is None:
        return
    avail = _com_ports()
    if avail is None:
        out.append(_item("Hardware", "serial ports", WARN, "pyserial missing; cannot list COM ports"))
        return
    out.append(_item("Hardware", "serial ports present", OK, ", ".join(avail) or "none"))
    for label, port, effect in (
        ("PSU (GPD-3303S)", C.PSU_PORT, "board power control -> manual power"),
        ("meter (GDM-8251A)", C.METER_PORT, "current/siren-V grading -> PSU IOUT / REVIEW"),
        ("injector (Waveshare AO)", C.WAVESHARE_PORT, "auto 4-20mA injection -> manual prompts"),
    ):
        if not port:
            out.append(_item("Hardware", label, WARN, "not configured (%s)" % effect,
                             "Set the port env var if this instrument is on the bench"))
        elif port in avail:
            out.append(_item("Hardware", label, OK, port))
        else:
            out.append(_item("Hardware", label, WARN, "%s not present" % port,
                             "Check the cable / COM number in Device Manager"))


def _check_probe(out, C):
    """List connected J-Link probes (via pylink) and confirm the pinned serial is among them."""
    try:
        import pylink
        emus = pylink.JLink().connected_emulators()
        serials = [str(e.SerialNumber) for e in emus]
    except Exception as e:
        out.append(_item("Hardware", "J-Link probe", WARN, "cannot enumerate: %s" % str(e)[:40],
                         "Plug in the J-Link; close JLink RTT Viewer if open"))
        return
    if not serials:
        out.append(_item("Hardware", "J-Link probe", WARN, "none detected",
                         "Plug in the J-Link probe (SWD to the board)"))
        return
    pinned = str(getattr(C, "JLINK_SERIAL", "") or "") if C else ""
    if pinned and pinned in serials:
        out.append(_item("Hardware", "J-Link probe", OK, "%s (pinned)" % pinned))
    elif pinned:
        out.append(_item("Hardware", "J-Link probe", WARN,
                         "pinned %s not among connected (%s)" % (pinned, ", ".join(serials)),
                         "Update JLINK_SERIAL or plug in the right probe"))
    else:
        out.append(_item("Hardware", "J-Link probe", OK, ", ".join(serials)))


def _check_cloud(out):
    import urllib.request
    url = os.environ.get("VX_TB_BASE_URL", "")   # config._load_env loads this from station.env
    if not url:
        out.append(_item("Cloud", "ThingsBoard URL", WARN, "VX_TB_BASE_URL not set",
                         "Set VX_TB_BASE_URL in secrets/station.env (cloud verify will SKIP)"))
        return
    try:
        urllib.request.urlopen(url, timeout=8)
        out.append(_item("Cloud", "ThingsBoard reachable", OK, url))
    except Exception as e:
        code = getattr(e, "code", None)
        if code:  # any HTTP response means the server is reachable
            out.append(_item("Cloud", "ThingsBoard reachable", OK, "%s (HTTP %s)" % (url, code)))
        else:
            out.append(_item("Cloud", "ThingsBoard reachable", WARN, "%s (%s)" % (url, str(e)[:40]),
                             "Check network / VPN to the portal"))


def run_checks(install=False):
    """Full checklist as a list of dicts. install=True (CLI only) auto-installs pip deps + creates
    secrets/station.env from the example. install=False (library/web) is strictly report-only."""
    out = []
    _check_python(out)
    _check_packages(out, install)
    _check_jlink_lib(out)
    _check_nrfjprog(out)
    C = _check_config(out)
    _check_secrets(out, install)
    _check_device_keys(out, C)
    _check_firmware(out, C)
    _check_serial_ports(out, C)
    _check_probe(out, C)
    _check_cloud(out)
    return out


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #
_ANSI = {OK: "\033[92m", FIXED: "\033[96m", WARN: "\033[93m", FAIL: "\033[91m"}
_RST = "\033[0m"


def main():
    try:
        os.system("")  # enable ANSI colours on Windows consoles
    except Exception:
        pass
    print("\n" + "=" * 70)
    print("  VX-0057 IO-BOARD QA STATION  -  SETUP PREFLIGHT")
    print("=" * 70)
    results = run_checks(install=True)
    cat = None
    for r in results:
        if r["category"] != cat:
            cat = r["category"]
            print("\n  %s" % cat)
        color = _ANSI.get(r["status"], "")
        line = "    %s[ %-5s ]%s  %s" % (color, r["status"], _RST, r["name"])
        if r["detail"]:
            line += "  -  %s" % r["detail"]
        print(line)
        if r["status"] in (FAIL, WARN) and r["fix"]:
            print("               -> %s" % r["fix"])
    nok = sum(1 for r in results if r["status"] in (OK, FIXED))
    nwarn = sum(1 for r in results if r["status"] == WARN)
    nfail = sum(1 for r in results if r["status"] == FAIL)
    print("\n" + "=" * 70)
    print("  RESULT:  %d OK   %d warning(s)   %d blocking" % (nok, nwarn, nfail))
    launch = "  Start the station:   python station.py 8792   (bench ports come from secrets/station.env)"
    if nfail == 0 and nwarn == 0:
        print("  All set.\n" + launch)
    elif nfail == 0:
        print("  Ready to start (review warnings for bench hardware / firmware / network).\n" + launch)
    else:
        print("  Fix the BLOCKING items above, then re-run:   python setup_check.py")
    print("=" * 70 + "\n")
    return 1 if nfail else 0


if __name__ == "__main__":
    raise SystemExit(main())
