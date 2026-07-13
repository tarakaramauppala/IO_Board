"""Tank-monitor test library: flash (nrfjprog), observe (pylink RTT), parse, report.

Pure parsers (parse_*) take captured RTT text and return structured results — they need no
hardware and are exercised by test_parse.py against fixtures/. The flash/RTT helpers wrap the
real tools (nrfjprog, pylink) and fail loudly with actionable messages.
"""
from __future__ import annotations
import os
import re
import json
import shutil
import subprocess
import time
from datetime import datetime, timezone

import config as C

ANSI = re.compile(r"\x1b\[[0-9;]*m")          # RTT logging has color on (prj.conf)


def strip_ansi(text: str) -> str:
    return ANSI.sub("", text)


# ---------------------------------------------------------------------------
# Flash (nrfjprog) — chip-erase so UICR NFCPINS=GPIO is written (K3/K4 relays!)
# ---------------------------------------------------------------------------
def flash_chiperase(image: str | None = None, net_image: str | None = None) -> None:
    image = image or C.TANK_IMAGE
    if not image:
        raise SystemExit("TANK_IMAGE not set — point it at a built/release tank-monitor merged hex.")
    if not os.path.isfile(image):
        raise SystemExit(f"Image not found: {image!r}")
    if not shutil.which("nrfjprog"):
        raise SystemExit("nrfjprog not on PATH (install nRF Command Line Tools).")
    fam = ["-f", C.NRFJPROG_FAMILY]
    # 1) full erase of both cores + unlock -> guarantees UICR (NFCPINS) is clean
    _run(["nrfjprog", *fam, "--recover"])
    # 2) program (writes app + UICR/NFCPINS from the hex), verify
    _run(["nrfjprog", *fam, "--program", image, "--verify"])
    if net_image:
        _run(["nrfjprog", *fam, "--coprocessor", "CP_NETWORK", "--program", net_image, "--verify"])
    # 3) reset to run
    _run(["nrfjprog", *fam, "--reset"])


def reset_target() -> None:
    _run(["nrfjprog", "-f", C.NRFJPROG_FAMILY, "--reset"])


def _run(cmd: list[str]) -> None:
    print("  $", " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.stdout.strip():
        print("   ", r.stdout.strip().replace("\n", "\n    "))
    if r.returncode != 0:
        raise SystemExit(f"command failed ({r.returncode}): {' '.join(cmd)}\n{r.stderr.strip()}")


# ---------------------------------------------------------------------------
# Observe (pylink RTT)
# ---------------------------------------------------------------------------
def capture_rtt(duration_s: float, reset_first: bool = True,
                stop_on: str | None = None, cb_address: int | None = None) -> str:
    """Capture RTT for up to duration_s. Optionally stop early when `stop_on` regex matches.

    cb_address: if given, attach RTT at that fixed control-block address BEFORE the reset, so the
    firmware's opening lines (printed within ~1s of boot) aren't lost to auto-detect latency + the
    small RTT ring overrunning. Leave None to auto-detect (correct for the production firmware, whose
    CB address differs from the testbench build's).

    Returns the captured (ANSI-stripped) text. Raises SystemExit with guidance if the SEGGER
    J-Link DLL / pylink isn't usable.
    """
    try:
        import pylink
    except Exception as e:  # pragma: no cover
        raise SystemExit(f"pylink not importable: {e}")
    try:
        jlink = pylink.JLink()
        if getattr(C, "JLINK_SERIAL", ""):
            jlink.open(serial_no=int(C.JLINK_SERIAL))   # pin the DUT probe (multi-probe bench)
        else:
            jlink.open()
        jlink.set_tif(pylink.enums.JLinkInterfaces.SWD)
        jlink.connect(C.JLINK_DEVICE, speed=C.JLINK_IFACE_SPEED_KHZ)
    except Exception as e:
        raise SystemExit(
            f"Could not open J-Link {getattr(C, 'JLINK_SERIAL', '') or '(default)'} / "
            f"connect to {C.JLINK_DEVICE}: {e}\n"
            "Check: SEGGER J-Link software installed, correct probe serial (JLINK_SERIAL), "
            "board powered (12V@J36), and no other tool (vx_programmer GUI / RTT Viewer) holding the probe."
        )
    def _start_rtt():
        try:
            jlink.rtt_start(cb_address) if cb_address else jlink.rtt_start()
        except Exception:
            try:
                jlink.rtt_start()
            except Exception:
                pass

    if reset_first and cb_address:
        # Known CB: attach FIRST (instant, no scan), then reset -> we are already draining when the
        # board reboots, so the opening self-test lines survive.
        _start_rtt()
        try:
            jlink.reset(halt=False)
        except Exception:
            pass
    else:
        if reset_first:
            try:
                jlink.reset(halt=False)
            except Exception:
                pass
        _start_rtt()
    buf, deadline = [], time.time() + duration_s
    stop_re = re.compile(stop_on) if stop_on else None
    # give the RTT control block a moment to come up
    time.sleep(0.1 if cb_address else 0.3)
    try:
        while time.time() < deadline:
            try:
                data = jlink.rtt_read(C.RTT_UP_BUFFER, 1024)
            except Exception:
                data = []
            if data:
                chunk = bytes(data).decode("utf-8", errors="replace")
                buf.append(chunk)
                if stop_re and stop_re.search(strip_ansi("".join(buf))):
                    break
            else:
                time.sleep(0.02)
    finally:
        try:
            jlink.rtt_stop()
            jlink.close()
        except Exception:
            pass
    return strip_ansi("".join(buf))


# ---------------------------------------------------------------------------
# Pure parsers (no hardware) — exercised by test_parse.py
# ---------------------------------------------------------------------------
def parse_boot(text: str) -> dict:
    def find(pat):
        m = re.search(pat, text)
        return m.group(1).strip() if m else None
    app_type = find(C.SIG_APP_TYPE)
    res = {
        "title": find(C.SIG_FW_TITLE),
        "version": find(C.SIG_FW_VERSION),
        "app_type": app_type,
        "compile_time": find(C.SIG_COMPILE_TIME),
        "app_init": bool(re.search(C.SIG_APP_INIT, text)),
    }
    reasons = []
    if not res["version"]:
        reasons.append("missing 'Firmware version' line")
    if app_type != C.APP_TYPE:
        reasons.append(f"app type {app_type!r} != expected {C.APP_TYPE!r}")
    if not res["app_init"]:
        reasons.append("did not reach 'Viaanix APP Init'")
    res["passed"] = not reasons
    res["reasons"] = reasons
    return res


def parse_testbench(text: str) -> dict:
    """Grade the WITH-TESTBENCH self-test as a per-component list matching the vendor test.js set.
    Returns {"components": [{name, status, detail}], "core_pass": bool, "started", "ended"}.
    status in PASS/FAIL/SKIP/REVIEW. Grading follows the vendor testbench: DI/AN/RS232/485/LoRa/Cell
    PASS on the firmware's own self-test result (OK), FAIL on a bad value, REVIEW only if a line wasn't
    captured. (DI is internally looped via the Light/Buzzer relays; AN reads the applied current.)"""
    def find(pat):
        m = re.search(pat, text)
        return m.group(1) if m else None

    started = bool(re.search(C.SIG_TEST_START, text))
    ended = bool(re.search(C.SIG_TEST_END, text))
    comps = []

    def add(name, status, detail=""):
        comps.append({"name": name, "status": status, "detail": detail})

    def ok_line(name, val, good=("OK", "ON")):
        if val is None:
            add(name, "REVIEW", "no line (not printed / not read)")
        else:
            add(name, "PASS" if val in good else "FAIL", str(val))

    add("Test Started", "PASS" if started else "FAIL")
    ok_line("External Memory", find(C.SIG_EXT_MEM))
    ok_line("Main Power", find(C.SIG_MAIN_POWER))
    ok_line("External Power 12v", find(C.SIG_EXT_POWER))
    for sig, name in ((C.SIG_PSC_AC, "PSC 60 AC"), (C.SIG_PSC_PWR, "PSC 60 Power"),
                      (C.SIG_PSC_BATT, "PSC 60 Battery")):
        v = find(sig)
        add(name, "REVIEW", (v if v is not None else "not read") + " (power-source dependent)")

    # DI: trust the firmware self-test result like the vendor testbench does (DI is internally looped
    # via the Light/Buzzer outputs through relays 1&2). PASS if all captured states report OK.
    di_all = {}
    for m in re.finditer(C.SIG_DI, text):
        di_all.setdefault(int(m.group(1)), []).append((m.group(2), m.group(3)))
    for i in range(1, C.DIGITAL_IN_COUNT + 1):
        entries = di_all.get(i)
        if entries:
            bad = [e for e in entries if e[1] != "OK"]
            add("DI%d" % i, "FAIL" if bad else "PASS", " ".join("%s=%s" % e for e in entries))
        else:
            add("DI%d" % i, "REVIEW", "not read")

    # AN: PASS on the firmware's OK (the ADC/front-end read a valid value), FAIL on a bad result.
    an = {int(m.group(1)): (m.group(2), m.group(3)) for m in re.finditer(C.SIG_AN, text)}
    for i in range(1, C.ANALOG_IN_COUNT + 1):
        if i in an:
            res, ua = an[i]
            add("AN%d" % i, "PASS" if res == "OK" else "FAIL",
                "%s%s" % (res, (" %suA" % ua) if ua else ""))
        else:
            add("AN%d" % i, "REVIEW", "not read")

    for sig, name in ((C.SIG_RS232, "RS232"), (C.SIG_RS485, "RS485")):
        v = find(sig)
        add(name, "PASS" if v == "OK" else "REVIEW", (v if v is not None else "not read") + " (needs loopback)")

    # LoRaWAN: apply the vendor test.js predicate instead of the firmware's blunt "ERROR" token.
    # Tx timeout = chip could not transmit -> FAIL; Rx timeout = transmitted OK, no join-accept
    # (chip healthy, no gateway/LNS in range) -> REVIEW (doesn't fail the stage); joined/OK -> PASS.
    lora_tok = find(C.SIG_TB_LORA)
    if lora_tok == "OK" or re.search(C.SIG_TB_LORA_JOINED, text):
        add("LoRaWAN", "PASS", "joined network")
    elif re.search(C.SIG_TB_LORA_TX_TIMEOUT, text):
        add("LoRaWAN", "FAIL", "Tx timeout - LoRa chip could not transmit (suspect)")
    elif re.search(C.SIG_TB_LORA_RX_TIMEOUT, text):
        # Vendor "LoRaWAN Comm." passes this: Tx succeeded, only the downlink timed out (no gateway).
        add("LoRaWAN", "PASS", "comm OK - Tx sent, Rx timeout (no downlink/gateway in range)")
    elif lora_tok is not None:
        add("LoRaWAN", "REVIEW", "%s - no join (check gateway/provisioning)" % lora_tok)
    else:
        add("LoRaWAN", "REVIEW", "no LoRaWAN line")
    ok_line("Cell Serial", find(C.SIG_TB_CELL_SERIAL))
    ok_line("Cell SIM", find(C.SIG_TB_CELL_SIM))
    add("Test Ended", "PASS" if ended else "FAIL")

    core_pass = (started and ended
                 and find(C.SIG_EXT_MEM) == "OK"
                 and find(C.SIG_MAIN_POWER) in ("ON", "OK"))
    return {"components": comps, "core_pass": core_pass, "started": started, "ended": ended}


def parse_selftest(text: str) -> dict:
    def find(pat):
        m = re.search(pat, text)
        return m.group(1) if m else None
    started = bool(re.search(C.SIG_TEST_START, text))
    ended = bool(re.search(C.SIG_TEST_END, text))
    analog = {int(m.group(1)): {"result": m.group(2),
                                "ua": int(m.group(3)) if m.group(3) else None}
              for m in re.finditer(C.SIG_AN, text)}
    di = {int(m.group(1)): {"state": m.group(2), "result": m.group(3)}
          for m in re.finditer(C.SIG_DI, text)}
    res = {
        "started": started, "ended": ended,
        "ext_memory": find(C.SIG_EXT_MEM),
        "power": {
            "main": find(C.SIG_MAIN_POWER), "ext12v": find(C.SIG_EXT_POWER),
            "psc_ac": find(C.SIG_PSC_AC), "psc_pwr": find(C.SIG_PSC_PWR),
            "psc_batt": find(C.SIG_PSC_BATT),
        },
        "analog": analog, "di": di,
        "rs232": find(C.SIG_RS232), "rs485": find(C.SIG_RS485),
    }
    # Bare-board pass: brackets + ext-mem OK + main power ON. DI/AN/RS need the rig (caller decides).
    reasons = []
    if not (started and ended):
        reasons.append("self-test brackets not both present")
    if res["ext_memory"] != "OK":
        reasons.append(f"External Memory = {res['ext_memory']!r} (expected OK)")
    if res["power"]["main"] not in ("ON", "OK"):
        reasons.append(f"Main Power = {res['power']['main']!r} (expected ON; check 12V@J36)")
    res["passed_core"] = not reasons          # bare-board core checks
    res["reasons"] = reasons
    return res


def parse_relay_transitions(text: str) -> list[dict]:
    """Relay/dig-out transitions seen on RTT (INFO). RISING_EDGE≈ON-side, FALLING_EDGE≈OFF-side.
    Continuity/DT90 is the authoritative ON/OFF — these are the on-bench indicator."""
    out = []
    for m in re.finditer(C.SIG_RELAY_XITION, text):
        dst = m.group(3)
        out.append({"channel": int(m.group(1)), "from": m.group(2), "to": dst,
                    "edge": "ON" if dst == C.RELAY_STATE_ON else
                            "OFF" if dst == C.RELAY_STATE_OFF else "?"})
    return out


def parse_tank_events(text: str) -> dict:
    """Extract per-channel raw samples/bands, relay edges, siren state, and uplink DataType
    markers from an RTT window. Grounds the manual-injection tests (Tests 1-5, Siren 6-8):
    Test 1/2 -> profiles (APP_IO_HIGH_HIGH/HIGH/NORMAL/LOW/LOW_LOW) + dt_markers (DT113);
    Test 3/4 -> relay_edges; Siren 6-8 -> siren_events + siren_mode."""
    samples = [{"channel": int(c), "state": int(s), "sample_ua": int(ua)}
               for c, s, ua in re.findall(C.SIG_TANK_SAMPLE, text)]
    profiles = [{"channel": int(c), "band": b} for c, b in re.findall(C.SIG_TANK_PROFILE, text)]
    sirens = [m if isinstance(m, str) else m[0] for m in re.findall(C.SIG_SIREN_EVENT, text)]
    mode = re.findall(C.SIG_SIREN_MODE, text)
    dts = sorted(set(re.findall(C.SIG_DT_MARKER, text)))
    return {"samples": samples, "profiles": profiles,
            "relay_edges": parse_relay_transitions(text),
            "siren_events": sirens,
            "siren_mode": (int(mode[-1]) if mode else None),
            "dt_markers": dts}


def ua_from_ma(ma: float) -> int:
    return int(round(ma * 1000))


def classify_level(ua: float, thr=None) -> str:
    """Map a measured uA to the firmware default profile band (>=HH/H, <=L/LL else NORMAL)."""
    t = (thr or C.DEFAULT_THRESHOLDS_UA)["level"]
    if ua >= t["HH"]:
        return "HIGH_HIGH"
    if ua >= t["H"]:
        return "HIGH"
    if ua <= t["LL"]:
        return "LOW_LOW"
    if ua <= t["L"]:
        return "LOW"
    return "NORMAL"


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def write_result(scope: str, result: dict, rtt: str | None = None, run_id: str | None = None) -> str:
    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = os.path.join(os.path.dirname(__file__), "..", "..", "results", run_id, "tank-monitor")
    root = os.path.abspath(root)
    os.makedirs(root, exist_ok=True)
    payload = {"scope": scope, "run_id": run_id,
               "utc": datetime.now(timezone.utc).isoformat(), "result": result}
    with open(os.path.join(root, f"{scope}.json"), "w") as f:
        json.dump(payload, f, indent=2)
    if rtt is not None:
        with open(os.path.join(root, f"{scope}.rtt.log"), "w", encoding="utf-8") as f:
            f.write(rtt)
    verdict = result.get("overall") or ("PASS" if result.get("passed") or result.get("passed_core") else "REVIEW")
    print(f"  -> results/{run_id}/tank-monitor/{scope}.json   [{verdict}]")
    return run_id
