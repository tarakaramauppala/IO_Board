#!/usr/bin/env python3
"""VX-0057 Tank Monitor - multi-board program + test STATION dashboard.

Siffron-style pipeline, adapted to this repo's proven modules + the vendor testbench:
  A. HARDWARE TEST  - flash the vendor WITH-TESTBENCH firmware, run its self-test over RTT, grade each
                      component (power/flash/DI/AN/RS232-485/radios) + board CURRENT (meter or PSU).
  B. REPROGRAM      - flash the normal production firmware (v2.0.4 dev; station's selected images).
  C. FUNCTIONAL     - boot/identity over RTT + ThingsBoard cloud check-in.
  Full (A->C) one-click; Batch = one board per click with tally + CSV. Results = per-component lamps.

Reuses flash_board.program, tankmon (capture_rtt/parse_boot/parse_testbench), cloud-checkin/tb_client,
psu.py (GPD-3303S), meter.py (GDM-8251A). Stdlib http.server + threading; binds 127.0.0.1; ASCII-only.

Run:  python station.py [port]     (default 8792)   then open http://127.0.0.1:8792/
"""
import copy
import csv
import glob
import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "tests", "cloud-checkin"))   # tb_client

import config as C
import tankmon as T
import flash_board
import device_map as DEV
import psu as PSU
import meter as METER
import thresholds as TH
import functest as FT

# --- firmware hex enumeration (normal-firmware dropdowns for stage B) --------
_RELEASE_DIR = os.path.dirname(C.TANK_IMAGE)
_VENDOR_FW_DIR = os.path.join(REPO, "vendor", "vx_programmer", "firmware", "Viaanix_IO_Board_(VX-003E)")
HEX_DIRS = [d for d in (os.environ.get("HEX_DIR"), _RELEASE_DIR, _VENDOR_FW_DIR) if d and os.path.isdir(d)]


def _list_hex(kind):
    found = {}
    for d in HEX_DIRS:
        for p in glob.glob(os.path.join(d, "*.hex")):
            b = os.path.basename(p)
            is_factory = "factory_data" in b.lower() or "factory-data" in b.lower()
            if (kind == "factory") == is_factory:
                found.setdefault(b, p)
    return dict(sorted(found.items(), key=lambda kv: os.path.getmtime(kv[1]), reverse=True))


MERGED_HEXES = _list_hex("merged")
FACTORY_HEXES = _list_hex("factory")
DEFAULT_MERGED = os.path.basename(C.TANK_IMAGE) if os.path.basename(C.TANK_IMAGE) in MERGED_HEXES else next(iter(MERGED_HEXES), "")
DEFAULT_FACTORY = os.path.basename(C.FACTORY_DATA_IMAGE) if os.path.basename(C.FACTORY_DATA_IMAGE) in FACTORY_HEXES else next(iter(FACTORY_HEXES), "")

DEVICES, DEV_SOURCE = DEV.devices_with_fallback()
VDUI_LIST = sorted(DEVICES)

_psu = PSU.PSU(C.PSU_PORT, channel=C.PSU_CHANNEL, ceiling_v=12.0, current_a=1.5) if C.PSU_PORT else None
_meter = METER.Meter(C.METER_PORT, C.METER_BAUD) if C.METER_PORT else None
_ws = None            # Waveshare AO injector (lazy-opened on first inject)
_ws_tried = False

CLOUD_WAIT_S = float(os.environ.get("CLOUD_WAIT_S", "300"))
LOGS_DIR = os.path.join(REPO, "results", "station")
os.makedirs(LOGS_DIR, exist_ok=True)

# --- shared state + locks ---------------------------------------------------
STATE = {
    "vdui": None, "stage": None, "running": False, "detail": "idle", "prompt": "",
    "results": {"hardware": None, "reprogram": None, "functional": None},
    "func_results": {}, "awaiting": False,
    "batch": [], "batch_msg": "",
    "psu": {"enabled": bool(_psu), "detail": "manual" if not _psu else "ready"},
    "meter": ("GDM-8251A @ " + C.METER_PORT) if _meter else ("PSU IOUT" if _psu else "none"),
    "injector": ("Waveshare AO @ " + C.WAVESHARE_PORT) if C.WAVESHARE_PORT else "manual",
    "started_at": None, "finished_at": None, "error": None, "seq": 0, "log": [],
}
STATE_LOCK = threading.Lock()
RUN_LOCK = threading.Lock()
PROBE_LOCK = threading.RLock()
CANCEL = threading.Event()
CONTINUE = threading.Event()          # operator "Continue" in guided functional tests
_CONT_VALUE = {"v": None}


class StopRequested(Exception):
    pass


def _ckpt():
    if CANCEL.is_set():
        raise StopRequested()


def _bump():
    STATE["seq"] += 1


def log(line):
    ts = datetime.now().strftime("%H:%M:%S")
    with STATE_LOCK:
        STATE["log"].append("[%s] %s" % (ts, str(line)))
        STATE["log"] = STATE["log"][-250:]
        _bump()


def set_detail(txt):
    with STATE_LOCK:
        STATE["detail"] = str(txt)
        _bump()
    log(txt)


def set_result(stage, value):
    with STATE_LOCK:
        STATE["results"][stage] = value
        _bump()


def set_state(**kw):
    with STATE_LOCK:
        STATE.update(kw)
        _bump()


def list_jlinks():
    try:
        out = subprocess.run(["nrfjprog", "--ids"], capture_output=True, text=True, timeout=20)
        return [ln.strip() for ln in out.stdout.splitlines() if ln.strip().isdigit()]
    except Exception:
        return []


def _use_probe(serial):
    if serial:
        C.JLINK_SERIAL = str(serial)


def _save_rtt(scope, rtt, run_id):
    try:
        d = os.path.join(LOGS_DIR, run_id)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "%s.rtt.log" % scope), "w", encoding="utf-8") as f:
            f.write(rtt or "")
    except Exception:
        pass


def _stage_overall(comps, core_ok=True):
    if any(c["status"] == "FAIL" for c in comps):
        return "FAIL"
    return "PASS" if core_ok else "FAIL"


# --- current: meter (if configured) -> PSU IOUT -> SKIP ----------------------
def _current_component():
    limit = C.CURRENT_LIMIT_A
    if _meter is not None:
        a = _meter.read_dc_current()
        if a is not None:
            return {"name": "Current", "status": "PASS" if a < limit else "FAIL",
                    "detail": "%.4f A (limit %.2f, GDM-8251A)" % (a, limit)}
    if _psu is not None:
        a = _psu.read_current()
        if a is not None:
            return {"name": "Current", "status": "PASS" if a < limit else "FAIL",
                    "detail": "%.4f A (limit %.2f, PSU IOUT)" % (a, limit)}
    return {"name": "Current", "status": "SKIP",
            "detail": "no meter (set METER_PORT) and PSU current unavailable"}


# --- cloud check-in (poll ThingsBoard until fresh) --------------------------
def _cloud_checkin(vdui):
    try:
        import tb_client
        tb = tb_client.ThingsBoard().login()
    except Exception as e:
        return {"ok": False, "error": "TB login failed: %s" % e}
    dev_id = C.TB_DEVICE_ID if (C.DEVICE_UUID and vdui.upper() == C.DEVICE_UUID.upper()) else None
    if not dev_id:
        try:
            dev_id = tb.device_id(vdui)
        except Exception as e:
            return {"ok": False, "error": "device %s not on TB: %s" % (vdui, e)}
    baseline = time.time() * 1000.0
    deadline = time.time() + CLOUD_WAIT_S
    while True:
        _ckpt()
        try:
            ts = tb.latest_timeseries(dev_id)
        except Exception as e:
            log("cloud poll error: %s" % e)
            ts = {}

        def val(k):
            v = ts.get(k)
            return v[0]["value"] if isinstance(v, list) and v else None

        newest = None
        for v in ts.values():
            pt = v[0] if isinstance(v, list) and v else {}
            t = pt.get("ts")
            if t and (newest is None or t > newest):
                newest = t
        age = (time.time() * 1000.0 - newest) / 60000.0 if newest else None
        fresh = newest is not None and (newest > baseline or (age is not None and age <= 6))
        if fresh:
            return {"ok": True, "age_min": round(age, 1) if age is not None else None,
                    "fw": val("fwVersion") or val("current_fw_version"),
                    "analog_ua": [val("analogInput%dcurrent" % n) for n in (1, 2, 3, 4)]}
        set_detail("C: FUNCTIONAL - cloud: no fresh check-in yet (age %s min); polling..."
                   % (round(age, 1) if age is not None else "n/a"))
        if time.time() >= deadline:
            return {"ok": False, "age_min": round(age, 1) if age is not None else None,
                    "error": "no fresh check-in within %ds (still joining? fw#311?)" % int(CLOUD_WAIT_S)}
        for _ in range(15):
            _ckpt()
            time.sleep(1)


# --- stages -----------------------------------------------------------------
def stage_hardware(vdui, dev, serial, run_id, ac_test=False):
    """A: flash the vendor testbench fw, run the self-test, grade components + current.
    ac_test=True adds the interactive AC power test (operator switches DC->AC; station toggles the PSU).
    Returns flash_ok (True if the TB firmware flashed) so Full can decide whether to continue."""
    set_detail("A: HARDWARE - flashing testbench fw (%s)" % os.path.basename(C.TESTBENCH_MERGED))
    _use_probe(serial)
    # Identity-agnostic HW test: flash with the vendor DUMMY VDUI (matches rtu-test/dummy-id.xlsx); the
    # real per-unit VDUI is programmed in Stage B. `vdui`/`dev` are unused here by design.
    with PROBE_LOCK:
        r = flash_board.program(uuid=C.TESTBENCH_DUMMY_VDUI, app_eui=C.TESTBENCH_DUMMY_APP_EUI,
                                app_key=C.TESTBENCH_DUMMY_APP_KEY,
                                merged=C.TESTBENCH_MERGED, factory=C.TESTBENCH_FACTORY,
                                jlink_serial=int(serial) if serial else None)
    comps = [{"name": "Program (TB fw)", "status": "PASS" if r.get("ok") else "FAIL",
              "detail": r.get("error") or ("testbench fw flashed (dummy VDUI %s)" % C.TESTBENCH_DUMMY_VDUI)}]
    if not r.get("ok"):
        set_result("hardware", {"components": comps, "overall": "FAIL"})
        return False
    set_detail("A: HARDWARE - capturing self-test over RTT (%ds; allow supercap start)" % int(C.HW_TEST_CAPTURE_S))
    with PROBE_LOCK:
        rtt = T.capture_rtt(C.HW_TEST_CAPTURE_S, reset_first=True, stop_on=C.SIG_TEST_END,
                            cb_address=getattr(C, "TESTBENCH_RTT_CB", None))
    _save_rtt("A-hardware", rtt, run_id)
    tb = T.parse_testbench(rtt)
    comps += tb["components"]
    comps.append(_current_component())
    set_result("hardware", {"components": comps, "overall": _stage_overall(comps, core_ok=tb["core_pass"])})
    log("A: HARDWARE self-test %s (started=%s ended=%s)" % (
        "core-PASS" if tb["core_pass"] else "core-FAIL", tb["started"], tb["ended"]))
    if ac_test:
        try:
            _hardware_ac_step(comps, serial, run_id)
        except StopRequested:
            log("A: AC TEST stopped - PSU DC left OFF; disconnect AC, then use Power ON to re-energize DC")
            raise
        set_result("hardware", {"components": comps, "overall": _stage_overall(comps, core_ok=tb["core_pass"])})
    return True


def _hardware_ac_step(comps, serial, run_id):
    """Interactive AC power test (mirrors the vendor 'Switch to AC power' stage). SAFE sequence: drop the
    PSU DC first (no dual source), operator brings up AC via the PSC-60/DPDT path, re-capture the self-test
    on AC, then operator drops AC and we restore DC. On a stop/timeout the DC is left OFF (never
    auto-re-energized while AC might still be connected). Updates the PSC-60 lines IN PLACE (so the
    DC-read REVIEW lines turn green) rather than adding duplicate rows."""
    if _psu is not None:
        _psu.power_off()
    log("A: AC TEST - PSU DC output OFF (safe: no dual source)")
    _await_operator("AC POWER TEST: connect AC via the PSC-60/DPDT path only (NEVER mains onto the 12V "
                    "terminal). Confirm the board runs on AC, then Continue.")
    set_detail("A: AC TEST - capturing self-test on AC")
    _use_probe(serial)
    with PROBE_LOCK:
        rtt = T.capture_rtt(C.HW_TEST_CAPTURE_S, reset_first=True, stop_on=C.SIG_TEST_END,
                            cb_address=getattr(C, "TESTBENCH_RTT_CB", None))
    _save_rtt("A-hardware-AC", rtt, run_id)

    def _find(sig):
        m = re.search(sig, rtt)
        return m.group(1) if m else None

    def _set(name, val, want):       # update the existing component in place (or append if new)
        st = "REVIEW" if val is None else ("PASS" if val == want else "FAIL")
        detail = "%s on AC (expect %s)" % (val, want)
        for c in comps:
            if c["name"] == name:
                c["status"], c["detail"] = st, detail
                return
        comps.append({"name": name, "status": st, "detail": detail})

    # On AC the board's 12V DC input reads OFF and the PSC-60 AC + 13.8V rails read ON.
    _set("PSC 60 AC", _find(C.SIG_PSC_AC), "ON")
    _set("PSC 60 Power", _find(C.SIG_PSC_PWR), "ON")
    _set("PSC 60 Battery", _find(C.SIG_PSC_BATT), "OK")
    _set("AC: External Power 12v off", _find(C.SIG_EXT_POWER), "OFF")   # distinct from the DC "ON" line
    _await_operator("Disconnect AC now, then Continue to return to DC power.")
    if _psu is not None:
        _psu.safe_power_on()
    log("A: AC TEST - PSU DC output back ON")


def stage_reprogram(vdui, dev, merged_path, factory_path, serial, run_id=None):
    set_detail("B: REPROGRAM normal fw (%s)" % os.path.basename(merged_path or "?"))
    _use_probe(serial)
    with PROBE_LOCK:
        r = flash_board.program(uuid=vdui, app_eui=dev.get("app_eui"), app_key=dev.get("app_key"),
                                merged=merged_path, factory=factory_path,
                                jlink_serial=int(serial) if serial else None)
    ok = bool(r.get("ok"))
    comps = [{"name": "Program (normal)", "status": "PASS" if ok else "FAIL",
              "detail": r.get("error") or ("merged+factory flashed: " + os.path.basename(merged_path or ""))}]
    set_result("reprogram", {"components": comps, "overall": "PASS" if ok else "FAIL"})
    log("B: REPROGRAM %s" % ("OK" if ok else "FAILED: " + str(r.get("error"))))
    return ok


def stage_functional(vdui, serial, run_id):
    comps = []
    set_detail("C: FUNCTIONAL - boot / identity over RTT")
    _use_probe(serial)
    with PROBE_LOCK:
        rtt = T.capture_rtt(C.DEFAULT_BOOT_CAPTURE_S, reset_first=True, stop_on=C.SIG_APP_INIT)
    _save_rtt("C-functional-boot", rtt, run_id)
    res = T.parse_boot(rtt)
    comps.append({"name": "Boot / Identity", "status": "PASS" if res["passed"] else "FAIL",
                  "detail": "%s %s%s" % (res["app_type"] or "?", res["version"] or "?",
                                         (" | " + "; ".join(res["reasons"])) if res["reasons"] else "")})
    set_result("functional", {"components": list(comps), "overall": "PASS" if res["passed"] else "FAIL"})
    cl = _cloud_checkin(vdui)
    comps.append({"name": "Cloud Check-in", "status": "PASS" if cl.get("ok") else "FAIL",
                  "detail": cl.get("error") or ("fw=%s age=%s min analog=%s"
                                                % (cl.get("fw"), cl.get("age_min"), cl.get("analog_ua")))})
    set_result("functional", {"components": comps, "overall": _stage_overall(comps)})
    return _stage_overall(comps) != "FAIL"


def stage_full(vdui, dev, merged_path, factory_path, serial, run_id, power_cycle=True):
    if _psu and power_cycle:
        ok, msg = _psu.safe_power_on()
        set_state(psu={"enabled": True, "detail": msg})
        log("PSU: " + msg)
        if not ok:
            set_result("hardware", {"components": [{"name": "PSU", "status": "FAIL", "detail": msg}], "overall": "FAIL"})
            return
        time.sleep(3)
    if not stage_hardware(vdui, dev, serial, run_id):
        return
    _ckpt()
    stage_reprogram(vdui, dev, merged_path, factory_path, serial, run_id)
    _ckpt()
    stage_functional(vdui, serial, run_id)


def _phase_pass():
    r = STATE["results"]
    def ov(s):
        return (r.get(s) or {}).get("overall")
    hw, rp, fn = ov("hardware"), ov("reprogram"), ov("functional")
    overall = "PASS" if (hw == "PASS" and rp == "PASS" and fn == "PASS") else "FAIL"
    return {"hardware": hw or "-", "reprogram": rp or "-", "functional": fn or "-", "overall": overall}


def stage_batch(vdui, dev, merged_path, factory_path, serial, run_id):
    try:
        stage_full(vdui, dev, merged_path, factory_path, serial, run_id, power_cycle=True)
    finally:
        red = _phase_pass()
        rec = {"vdui": vdui, "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), **red}
        with STATE_LOCK:
            STATE["batch"].append(rec)
            _bump()
        _save_batch_csv()
        if _psu:
            ok, msg = _psu.power_off()
            set_state(psu={"enabled": True, "detail": msg})
        n = len(STATE["batch"])
        set_state(batch_msg="DEVICE %s DONE: %s (#%d). %sDisconnect it, connect the NEXT board, "
                            "enter its VDUI, and click Batch." % (vdui, red["overall"], n,
                                                                  "POWER IS OFF. " if _psu else ""))


def _save_batch_csv():
    path = os.path.join(LOGS_DIR, "batch_%s.csv" % datetime.now().strftime("%Y%m%d"))
    try:
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["idx", "vdui", "hardware", "reprogram", "functional", "overall", "time"])
            for i, r in enumerate(STATE["batch"], 1):
                w.writerow([i, r["vdui"], r["hardware"], r["reprogram"], r["functional"], r["overall"], r["time"]])
    except Exception as e:
        log("batch CSV write failed: %s" % e)


# --- worker -----------------------------------------------------------------
def worker(stage, vdui, dev, merged_path, factory_path, serial, ac_test=False):
    CANCEL.clear()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    set_state(running=True, stage=stage, vdui=vdui, error=None, prompt="",
              started_at=datetime.now().isoformat(), finished_at=None)
    if stage != "batch":
        set_state(results={"hardware": None, "reprogram": None, "functional": None})
    else:
        set_state(results={"hardware": None, "reprogram": None, "functional": None})
    try:
        if stage == "full":
            stage_full(vdui, dev, merged_path, factory_path, serial, run_id)
        elif stage == "batch":
            stage_batch(vdui, dev, merged_path, factory_path, serial, run_id)
        elif stage == "hardware":
            stage_hardware(vdui, dev, serial, run_id, ac_test=ac_test)
        elif stage == "reprogram":
            stage_reprogram(vdui, dev, merged_path, factory_path, serial, run_id)
        elif stage == "functional":
            stage_functional(vdui, serial, run_id)
        set_detail("done")
    except StopRequested:
        set_state(error="STOPPED by operator")
        set_detail("STOPPED")
    except Exception as e:
        set_state(error=str(e))
        set_detail("ERROR: %s" % e)
    finally:
        set_state(running=False, finished_at=datetime.now().isoformat(), prompt="")
        CANCEL.clear()
        try:
            RUN_LOCK.release()
        except Exception:
            pass


# --- functional tests (guided; manual simulator injection) ------------------
def _await_operator(prompt, timeout=900):
    """Show prompt, block until POST /continue. Returns operator value (float volts) or None."""
    _CONT_VALUE["v"] = None
    CONTINUE.clear()
    set_state(prompt=prompt, awaiting=True)
    t0 = time.time()
    while not CONTINUE.is_set():
        _ckpt()
        if time.time() - t0 > timeout:
            raise TimeoutError("operator did not Continue within %ds" % timeout)
        time.sleep(0.4)
    set_state(prompt="", awaiting=False)
    v = _CONT_VALUE["v"]
    try:
        return float(v) if v not in (None, "") else None
    except (ValueError, TypeError):
        return None


def _injector():
    """Lazily open the Waveshare AO injector once (if WAVESHARE_PORT set). None => manual injection."""
    global _ws, _ws_tried
    if _ws_tried:
        return _ws
    _ws_tried = True
    if not C.WAVESHARE_PORT:
        return None
    try:
        import waveshare
        _ws = waveshare.WaveshareAO().open(C.WAVESHARE_PORT, C.WAVESHARE_BAUD, C.WAVESHARE_ADDR)
        _ws.all_off()
        log("injector: Waveshare AO on %s @ %d addr %d" % (C.WAVESHARE_PORT, C.WAVESHARE_BAUD, C.WAVESHARE_ADDR))
    except Exception as e:
        log("injector unavailable (%s) - manual injection" % e)
        _ws = None
    return _ws


def _injector_off():
    if _ws is not None:
        try:
            _ws.all_off()
        except Exception:
            pass


def _injector_reset():
    """Drop the cached injector so the next _injector() reopens a FRESH client. RS-485/CH340 links drop
    occasionally; once pymodbus closes the connection the cached handle is dead until we rebuild it."""
    global _ws, _ws_tried
    if _ws is not None:
        try:
            _ws.close()
        except Exception:
            pass
    _ws = None
    _ws_tried = False


def _tb_client():
    import tb_client
    return tb_client.ThingsBoard().login()


def _meter_volts():
    """Read the bench DMM (GDM-8251A) in DC-volts - used to auto-read the siren/light output voltage so the
    S6-S8 steps grade PASS/FAIL instead of REVIEW. Wire the meter's V input to the ALARM (or LIGHT) WAGO
    terminal and its COM to board GND, set METER_PORT. None if no meter is configured or the read fails."""
    if _meter is None:
        return None
    try:
        return _meter.read_dc_volt()
    except Exception as e:
        log("meter read failed: %s" % e)
        return None


def _capture(secs=6):
    time.sleep(1.5)   # let the app sample + log the newly-injected current before we read
    with PROBE_LOCK:
        rtt = T.capture_rtt(secs, reset_first=False)
    return T.parse_tank_events(rtt)


def _cloud_snapshot(vdui):
    try:
        tb = _tb_client()
        dev_id = C.TB_DEVICE_ID if (C.DEVICE_UUID and vdui.upper() == C.DEVICE_UUID.upper()) else tb.device_id(vdui)
        ts = tb.latest_timeseries(dev_id)
        return {k: (v[0]["value"] if isinstance(v, list) and v else None) for k, v in ts.items()}
    except Exception as e:
        log("cloud snapshot failed: %s" % e)
        return {}


class _Ctx:
    def __init__(self, vdui, serial, ai, test_id, test_name, auto=False, thr=None):
        self.vdui, self.serial, self.ai = vdui, serial, ai
        self.test_id, self.test_name = test_id, test_name
        self.auto = auto                       # batch/all-tests mode: never block on an operator prompt
        self.thr = thr or TH.resolve()
        self.components = []
        _use_probe(serial)

    def ask(self, prompt, want_volts=False):
        if want_volts and _meter is not None:  # auto-read the bench DMM (siren/light output volts)
            v = _meter_volts()
            self.log("  meter read: %s V" % ("%.3f" % v if v is not None else "None"))
            if v is not None:
                return v                       # real reading -> the siren step grades PASS/FAIL on it
        if self.auto:                          # hands-off run: skip remaining manual prompts
            self.log("  (auto) skipped manual step: %s" % prompt[:70])
            return None
        return _await_operator(prompt + (" [enter Volts]" if want_volts else ""))

    def inject(self, ma, label=""):
        """Set the injected current on this AI: AUTO via the Waveshare AO if configured, else prompt
        the operator to set it manually and click Continue. Returns 'auto' or 'manual'.
        On a Modbus/serial error, rebuild the injector client ONCE and retry so a transient RS-485 drop
        self-heals instead of wedging the rest of the battery."""
        ao = C.AI_TO_AO.get(self.ai, self.ai)
        for attempt in (1, 2):
            inj = _injector()
            if inj is None:
                break
            try:
                inj.set_current_ma(ao, ma)
                self.log("  inject AI%d = %.2f mA (auto via AO%d) %s" % (self.ai, ma, ao, label))
                time.sleep(C.WAVESHARE_SETTLE_S)
                return "auto"
            except Exception as e:
                if attempt == 1:
                    self.log("  auto-inject error (%s) - reconnecting injector..." % e)
                    _injector_reset()
                else:
                    self.log("  auto-inject failed after reconnect (%s) - prompting operator" % e)
        self.ask("Inject %.2f mA on AI%d %s, then Continue" % (ma, self.ai, label))
        return "manual"

    def capture(self, secs=6):
        return _capture(secs)

    def cloud(self):
        return _cloud_snapshot(self.vdui)

    def add(self, name, status, detail=""):
        self.components.append({"name": name, "status": status, "detail": detail})
        self._flush()

    def apply(self, desc, result):
        ok = bool(result.get("ok"))
        self.add("Settings: " + desc, "PASS" if ok else "REVIEW",
                 result.get("detail") or ("applied" if ok else "not confirmed - push on portal"))
        return ok

    def log(self, msg):
        log(msg)

    def _flush(self):
        ov = "FAIL" if any(c["status"] == "FAIL" for c in self.components) else \
             ("REVIEW" if any(c["status"] == "REVIEW" for c in self.components) else "PASS")
        with STATE_LOCK:
            STATE["func_results"][self.test_id] = {"name": self.test_name,
                                                   "components": list(self.components), "overall": ov}
            _bump()


def func_worker(test_id, vdui, serial, ai):
    CANCEL.clear()
    name, fn = FT.TESTS[test_id]
    set_state(running=True, stage="func:" + test_id, vdui=vdui, error=None, prompt="",
              started_at=datetime.now().isoformat(), finished_at=None)
    ctx = _Ctx(vdui, serial, ai, test_id, name)
    ctx._flush()
    try:
        fn(ctx)
        set_detail("%s done" % test_id)
    except StopRequested:
        ctx.add("(stopped)", "REVIEW", "stopped by operator")
        set_detail("STOPPED")
    except Exception as e:
        ctx.add("(error)", "FAIL", str(e))
        set_state(error=str(e))
        set_detail("ERROR: %s" % e)
    finally:
        _injector_off()
        set_state(running=False, awaiting=False, prompt="", finished_at=datetime.now().isoformat())
        CANCEL.clear()
        CONTINUE.clear()
        try:
            RUN_LOCK.release()
        except Exception:
            pass


def func_all_worker(vdui, serial, channels=(1, 2, 3, 4), order=None, label="ALL"):
    """Functional battery: run the given tests on each channel, hands-off, via the auto-injector.
    `order` defaults to the full FT.ALL_ORDER (T1-T5, S6-S8); pass a subset (FT.SMOKE_ORDER) on one
    channel for a quick go/no-go. Settings-dependent tests use the DT71 writer (verified up-front)."""
    import settings as SET
    order = tuple(order) if order else tuple(FT.ALL_ORDER)
    CANCEL.clear()
    set_state(running=True, stage="func:" + label, vdui=vdui, error=None, prompt="",
              started_at=datetime.now().isoformat(), finished_at=None, func_results={})
    try:
        set_detail("Functional (%s): verifying the DT71 settings-writer..." % label)
        try:
            usable = SET.verify_writer(vdui, log=log)
            SET.set_echo_timeout(45)
            log("settings-writer: %s" % ("USABLE" if usable else "unavailable -> settings steps say 'push on portal'"))
        except Exception as e:
            log("settings-writer verify error: %s" % e)
        thr = TH.resolve()
        try:
            _capture(3)          # warm-up: drain the RTT cold-start backlog so the first step's capture
        except Exception:        # isn't polluted by stale idle-state bands (was a benign AI1:T1 REVIEW)
            pass
        for ai in channels:
            for tid in order:
                _ckpt()
                name, fn = FT.TESTS[tid]
                key = "AI%d:%s" % (ai, tid)
                ctx = _Ctx(vdui, serial, ai, key, "AI%d - %s" % (ai, name), auto=True, thr=thr)
                ctx._flush()
                set_detail("running %s" % key)
                try:
                    fn(ctx)
                except StopRequested:
                    raise
                except Exception as e:
                    ctx.add("(error)", "FAIL", str(e))
        set_detail("functional %s done (%d channels x %d tests)" % (label, len(channels), len(order)))
    except StopRequested:
        set_state(error="STOPPED by operator")
        set_detail("STOPPED")
    except Exception as e:
        set_state(error=str(e))
        set_detail("ERROR: %s" % e)
    finally:
        _injector_off()
        set_state(running=False, awaiting=False, prompt="", finished_at=datetime.now().isoformat())
        CANCEL.clear()
        CONTINUE.clear()
        try:
            RUN_LOCK.release()
        except Exception:
            pass


# --- HTTP -------------------------------------------------------------------
def _resolve_hex(name, table):
    return table.get(name) if name else None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode("utf-8", "replace")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        p = self.path.split("?")[0]
        if p in ("/", "/index.html"):
            return self._send(200, PAGE, "text/html")
        if p == "/status":
            with STATE_LOCK:
                snap = copy.deepcopy(STATE)
            return self._send(200, json.dumps(snap))
        if p == "/devices":
            return self._send(200, json.dumps({"vduis": VDUI_LIST, "source": DEV_SOURCE}))
        if p == "/jlinks":
            return self._send(200, json.dumps({"jlinks": list_jlinks(), "default": C.JLINK_SERIAL}))
        if p == "/hexes":
            return self._send(200, json.dumps({"merged": list(MERGED_HEXES), "factory": list(FACTORY_HEXES),
                                               "default_merged": DEFAULT_MERGED, "default_factory": DEFAULT_FACTORY}))
        return self._send(404, json.dumps({"error": "not found"}))

    def _body(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return {}

    def do_POST(self):
        p = self.path.split("?")[0]
        b = self._body()
        if p == "/stop":
            CANCEL.set()
            return self._send(200, json.dumps({"ok": True}))
        if p == "/reset":
            if STATE["running"]:
                return self._send(409, json.dumps({"error": "a run is active"}))
            set_state(results={"hardware": None, "reprogram": None, "functional": None},
                      batch=[], batch_msg="", error=None, detail="idle", log=[])
            return self._send(200, json.dumps({"ok": True}))
        if p in ("/power_on", "/power_off"):
            if not _psu:
                return self._send(400, json.dumps({"error": "no PSU configured (set PSU_PORT)"}))
            if STATE["running"]:
                return self._send(409, json.dumps({"error": "refused while a run is active"}))
            ok, msg = _psu.safe_power_on() if p == "/power_on" else _psu.power_off()
            set_state(psu={"enabled": True, "detail": msg})
            log("PSU: " + msg)
            return self._send(200 if ok else 400, json.dumps({"ok": ok, "detail": msg}))
        if p == "/run":
            stage = b.get("stage")
            if stage not in ("hardware", "reprogram", "functional", "full", "batch"):
                return self._send(400, json.dumps({"error": "bad stage %r" % stage}))
            vdui = str(b.get("vdui", "")).strip().upper()
            dev = DEVICES.get(vdui)
            if not dev:
                return self._send(400, json.dumps({"error": "VDUI %r not in device map (%s)" % (vdui, DEV_SOURCE)}))
            serial = str(b.get("jlink", "") or C.JLINK_SERIAL)
            merged_path = _resolve_hex(b.get("merged", DEFAULT_MERGED), MERGED_HEXES)
            factory_path = _resolve_hex(b.get("factory", DEFAULT_FACTORY), FACTORY_HEXES)
            if not (dev.get("app_eui") and dev.get("app_key")):
                return self._send(400, json.dumps({"error": "VDUI %s missing AppEUI/AppKey" % vdui}))
            if stage in ("reprogram", "full", "batch") and not merged_path:
                return self._send(400, json.dumps({"error": "no normal merged hex selected (stage B)"}))
            if stage in ("hardware", "full", "batch") and not os.path.exists(C.TESTBENCH_MERGED):
                return self._send(400, json.dumps({"error": "testbench fw not found: %s" % C.TESTBENCH_MERGED}))
            ac_test = bool(b.get("ac_test"))
            if ac_test and stage != "hardware":
                return self._send(400, json.dumps({"error": "ac_test only applies to the hardware stage"}))
            if not RUN_LOCK.acquire(blocking=False):
                return self._send(409, json.dumps({"error": "a run is already active"}))
            threading.Thread(target=worker,
                             args=(stage, vdui, dev, merged_path, factory_path, serial),
                             kwargs={"ac_test": ac_test}, daemon=True).start()
            return self._send(200, json.dumps({"ok": True, "stage": stage, "vdui": vdui, "ac_test": ac_test}))
        if p == "/continue":
            _CONT_VALUE["v"] = b.get("value")
            CONTINUE.set()
            return self._send(200, json.dumps({"ok": True}))
        if p == "/func_run":
            test = b.get("test")
            if test not in FT.TESTS:
                return self._send(400, json.dumps({"error": "unknown test %r" % test}))
            vdui = str(b.get("vdui", "")).strip().upper()
            if vdui not in DEVICES:
                return self._send(400, json.dumps({"error": "VDUI %r not in device map" % vdui}))
            serial = str(b.get("jlink", "") or C.JLINK_SERIAL)
            try:
                ai = int(b.get("ai", 1))
            except (ValueError, TypeError):
                ai = 1
            if not RUN_LOCK.acquire(blocking=False):
                return self._send(409, json.dumps({"error": "a run is already active"}))
            threading.Thread(target=func_worker, args=(test, vdui, serial, ai), daemon=True).start()
            return self._send(200, json.dumps({"ok": True, "test": test}))
        if p in ("/func_all", "/func_smoke"):
            vdui = str(b.get("vdui", "")).strip().upper()
            if vdui not in DEVICES:
                return self._send(400, json.dumps({"error": "VDUI %r not in device map" % vdui}))
            serial = str(b.get("jlink", "") or C.JLINK_SERIAL)
            if not RUN_LOCK.acquire(blocking=False):
                return self._send(409, json.dumps({"error": "a run is already active"}))
            if p == "/func_smoke":       # quick go/no-go: subset on AI1 only
                kw = {"channels": (1,), "order": FT.SMOKE_ORDER, "label": "SMOKE"}
            else:
                kw = {}
            threading.Thread(target=func_all_worker, args=(vdui, serial), kwargs=kw, daemon=True).start()
            return self._send(200, json.dumps({"ok": True, "stage": "func:" + kw.get("label", "ALL")}))
        return self._send(404, json.dumps({"error": "not found"}))


# --- page -------------------------------------------------------------------
PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>VX-0057 Station</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{color-scheme:dark}
body{background:#0e1116;color:#e6edf3;font:14px system-ui,Segoe UI,Arial;margin:0;padding:16px}
h1{font-size:18px;margin:0 0 4px}.sub{color:#8b949e;font-size:12px;margin-bottom:14px}
.bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px;margin-bottom:12px}
label{color:#8b949e;font-size:12px;margin-right:4px}
select,input,button{background:#0d1117;color:#e6edf3;border:1px solid #30363d;border-radius:6px;padding:7px 9px;font-size:13px}
button{cursor:pointer;font-weight:600}button:hover{border-color:#58a6ff}button:disabled{opacity:.4;cursor:not-allowed}
.prim{background:#1f6feb;border-color:#1f6feb}.warn{background:#9e6a03;border-color:#9e6a03}.dang{background:#8b1a1a;border-color:#8b1a1a}
.combo{position:relative;display:inline-block}.matches{position:absolute;z-index:9;background:#161b22;border:1px solid #30363d;border-radius:6px;max-height:240px;overflow:auto;min-width:220px;display:none}
.matches div{padding:6px 9px;cursor:pointer}.matches div:hover{background:#1f6feb}
.status{display:flex;align-items:center;gap:8px;margin:10px 0;font-size:14px}
.dot{width:10px;height:10px;border-radius:50%;background:#3fb950}.dot.run{background:#d29922;animation:pulse 1s infinite}
@keyframes pulse{50%{opacity:.3}}
.banner{background:#8b1a1a;border-radius:8px;padding:14px;font-size:18px;font-weight:700;text-align:center;margin:10px 0;animation:pulse 1s infinite;display:none}
.msg{background:#12341a;border:1px solid #238636;border-radius:8px;padding:10px;margin:8px 0;display:none}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:12px 0}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px}
.card h3{margin:0 0 6px;font-size:13px;color:#8b949e;text-transform:uppercase;letter-spacing:.5px}
.ovr{font-size:15px;font-weight:700;margin-bottom:8px}
.ok{color:#3fb950}.bad{color:#f85149}.pend{color:#8b949e}.rev{color:#d29922}
.lamp{display:flex;align-items:center;gap:8px;padding:3px 0;font-size:12px}
.l{width:9px;height:9px;border-radius:50%;flex:none}
.l.PASS{background:#3fb950}.l.FAIL{background:#f85149}.l.SKIP{background:#484f58}.l.REVIEW{background:#d29922}
.lname{min-width:120px}.ldet{color:#8b949e}
table{width:100%;border-collapse:collapse;font-size:12px;margin-top:6px}th,td{border:1px solid #30363d;padding:5px 8px;text-align:left}th{color:#8b949e}
pre{background:#0d1117;border:1px solid #30363d;border-radius:8px;padding:10px;max-height:240px;overflow:auto;font-size:12px}
.mov{position:fixed;inset:0;background:rgba(1,4,9,.72);display:none;z-index:50;align-items:center;justify-content:center;padding:16px}
.mcard{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:18px 20px;max-width:600px;width:100%;box-shadow:0 12px 48px rgba(0,0,0,.55)}
.mcard h3{margin:0 0 10px;font-size:16px;color:#58a6ff}
.mcard ol{margin:8px 0 4px;padding-left:22px}.mcard li{margin:8px 0;line-height:1.45}
.mcard code{background:#0d1117;border:1px solid #30363d;border-radius:4px;padding:1px 6px;font-size:12px;color:#79c0ff}
.mcard .wr{background:#3a2a08;border:1px solid #9e6a03;border-radius:6px;padding:9px 11px;color:#f0c674;margin:2px 0 10px;font-size:13px}
.mcard .hint{color:#8b949e;font-size:12px}
.mrow{display:flex;gap:8px;justify-content:flex-end;margin-top:14px}
</style></head><body>
<h1>VX-0057 Tank Monitor - Program &amp; Test Station</h1>
<div class="sub">devices: <span id="devsrc"></span> &middot; A hardware self-test (vendor testbench fw) &rarr; B reprogram normal &rarr; C functional &middot; meter: <span id="metersrc"></span></div>

<div class="bar">
  <div class="combo"><label>VDUI</label><input id="vtext" placeholder="type / pick VDUI" autocomplete="off" size="20"><div id="vmatches" class="matches"></div></div>
  <span><label>normal merged</label><select id="mergedsel"></select></span>
  <span><label>normal factory</label><select id="factorysel"></select></span>
  <span><label>J-Link</label><select id="jlink"></select><button onclick="loadJlinks()" title="rescan">&#8635;</button></span>
</div>
<div class="bar">
  <button class="prim" onclick="run('full')">Full (A&rarr;C)</button>
  <button onclick="run('hardware')">A: Hardware Test</button>
  <button onclick="runAc()" title="Hardware test + interactive AC power test (prompts DC&rarr;AC; station toggles the PSU)">A + AC Power</button>
  <button onclick="run('reprogram')">B: Reprogram (normal)</button>
  <button onclick="run('functional')">C: Functional</button>
  <button class="warn" onclick="run('batch')">Batch (A board)</button>
  <button id="stopbtn" class="dang" onclick="stop()" disabled>&#9632; Stop</button>
  <span style="flex:1"></span>
  <button class="prim" onclick="pwr('power_on')">&#9889; Power ON</button>
  <button onclick="pwr('power_off')">&#9098; Power OFF</button>
  <button class="dang" onclick="if(confirm('Clear results + batch?'))reset()">&#10227; Reset</button>
</div>
<div class="bar">
  <span style="color:#8b949e;font-size:12px">Functional &mdash; auto-injected. <b>Quick</b> = go/no-go (level+relay, AI1, ~2-3 min); <b>Full</b> = T1-S8 &times; 4 ch (~18 min):</span>
  <button class="prim" onclick="frunSmoke()">&#9889; Quick Functional (AI1: level+relay)</button>
  <button class="prim" onclick="frunAll()">&#9654; Full Functional (T1-S8 &times; 4 ch)</button>
</div>

<div id="fwire" class="mov">
  <div class="mcard">
    <h3 id="fwtitle">Functional test &mdash; bench wiring</h3>
    <div class="wr">&#9888; Coming from the hardware test? <b>Take the meter OUT of series with the +12 V first.</b> Functional uses a different setup (auto-injection into the analog inputs).</div>
    <ol>
      <li><b>PSU (GPD-3303S)</b> &rarr; <b>12 V DC direct</b> to the board's 12 V input (<i>not</i> through the meter).</li>
      <li><b>Waveshare RTU (AO injector)</b> &rarr; analog inputs, sharing a common GND:
        <div style="margin:6px 0"><code>AO1 &rarr; AI1</code>&nbsp;&nbsp;<code>AO2 &rarr; AI2</code>&nbsp;&nbsp;<code>AO3 &rarr; AI3</code>&nbsp;&nbsp;<code>AO4 &rarr; AI4</code></div>
        <span class="hint">each: AO current-out into that input's <code>IN</code> pin, return to its <code>GND/AGND</code>. (Quick uses AI1 only.)</span></li>
      <li id="fwmeter"><b>Meter (GDM-8251A)</b> &rarr; <b>across the siren ALARM output</b> (red&rarr;ALARM, black&rarr;GND), set DC-volts &mdash; needed for the siren steps (S6&ndash;S8).</li>
    </ol>
    <div class="mrow">
      <button onclick="fwCancel()">Cancel</button>
      <button class="prim" onclick="fwStart()">Wiring done &mdash; Start</button>
    </div>
  </div>
</div>

<div id="cont" class="msg" style="background:#12233f;border-color:#1f6feb;display:none">
  <b>ACTION:</b> <span id="contmsg"></span>
  <input id="contvolts" placeholder="Volts (siren only)" size="12" style="margin:0 8px">
  <button class="prim" onclick="cont()">Continue &rarr;</button>
</div>
<div id="banner" class="banner"></div>
<div id="batchmsg" class="msg"></div>
<div class="status"><span id="dot" class="dot"></span><span id="stxt">idle</span></div>

<div class="grid">
  <div class="card"><h3>A &middot; Hardware Test</h3><div id="ov_hardware" class="ovr pend">-</div><div id="c_hardware"></div></div>
  <div class="card"><h3>B &middot; Reprogram</h3><div id="ov_reprogram" class="ovr pend">-</div><div id="c_reprogram"></div></div>
  <div class="card"><h3>C &middot; Functional</h3><div id="ov_functional" class="ovr pend">-</div><div id="c_functional"></div></div>
</div>

<div id="funcpanels"></div>

<div class="card" id="batchpanel" style="display:none"><h3>Batch tally</h3><div id="batchtbl"></div></div>
<h3 style="color:#8b949e;font-size:13px">Log</h3><pre id="log"></pre>

<script>
var VDUIS=__VDUIS__, MERGED=__MERGED__, FACTORY=__FACTORY__, DEFM="__DEFM__", DEFF="__DEFF__", DEVSRC="__DEVSRC__", METERSRC="__METERSRC__";
document.getElementById('devsrc').textContent=DEVSRC;document.getElementById('metersrc').textContent=METERSRC;
function opt(v){var o=document.createElement('option');o.value=v;o.textContent=v;return o}
function fill(sel,arr,def){var s=document.getElementById(sel);arr.forEach(function(v){s.appendChild(opt(v))});if(def)s.value=def}
fill('mergedsel',MERGED,DEFM);fill('factorysel',FACTORY,DEFF);
var vt=document.getElementById('vtext'),vm=document.getElementById('vmatches');
function showMatches(){var q=vt.value.trim().toUpperCase();vm.innerHTML='';var m=VDUIS.filter(function(v){return !q||v.indexOf(q)>=0}).slice(0,50);
 if(!m.length){vm.style.display='none';return}m.forEach(function(v){var d=document.createElement('div');d.textContent=v;d.onclick=function(){vt.value=v;vm.style.display='none'};vm.appendChild(d)});vm.style.display='block'}
vt.onfocus=showMatches;vt.oninput=showMatches;document.addEventListener('click',function(e){if(e.target!=vt)vm.style.display='none'});
function loadJlinks(){fetch('/jlinks').then(function(r){return r.json()}).then(function(d){var s=document.getElementById('jlink');s.innerHTML='';(d.jlinks||[]).forEach(function(v){s.appendChild(opt(v))});if(d.default)s.value=d.default})}
loadJlinks();
function chosen(){return {vdui:vt.value.trim(),jlink:document.getElementById('jlink').value,merged:document.getElementById('mergedsel').value,factory:document.getElementById('factorysel').value}}
function run(stage){var b=chosen();b.stage=stage;fetch('/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)}).then(function(r){return r.json()}).then(function(d){if(d.error)alert(d.error)})}
function runAc(){var b=chosen();b.stage='hardware';b.ac_test=true;fetch('/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)}).then(function(r){return r.json()}).then(function(d){if(d.error)alert(d.error)})}
function stop(){fetch('/stop',{method:'POST'})}
function reset(){fetch('/reset',{method:'POST'})}
function frunFunc(ep){fetch(ep,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({vdui:vt.value.trim(),jlink:document.getElementById('jlink').value})}).then(function(r){return r.json()}).then(function(d){if(d.error)alert(d.error)})}
var _fwEp=null;
function frunAll(){fwOpen('/func_all','Full Functional — T1-S8 × 4 channels',true)}
function frunSmoke(){fwOpen('/func_smoke','Quick Functional — AI1: level + relay',false)}
function fwOpen(ep,title,needMeter){_fwEp=ep;document.getElementById('fwtitle').textContent=title;document.getElementById('fwmeter').style.display=needMeter?'list-item':'none';document.getElementById('fwire').style.display='flex'}
function fwCancel(){document.getElementById('fwire').style.display='none';_fwEp=null}
function fwStart(){document.getElementById('fwire').style.display='none';if(_fwEp)frunFunc(_fwEp);_fwEp=null}
function cont(){var v=document.getElementById('contvolts').value;fetch('/continue',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({value:v})}).then(function(){document.getElementById('contvolts').value=''})}
function pwr(a){fetch('/'+a,{method:'POST'}).then(function(r){return r.json()}).then(function(d){if(d.error)alert(d.error)})}
function ovClass(v){return v=='PASS'?'ok':v=='FAIL'?'bad':'pend'}
function renderStage(key,st){var ov=document.getElementById('ov_'+key),box=document.getElementById('c_'+key);
 if(!st){ov.textContent='-';ov.className='ovr pend';box.innerHTML='';return}
 ov.textContent=st.overall||'-';ov.className='ovr '+ovClass(st.overall);
 var h='';(st.components||[]).forEach(function(c){h+='<div class="lamp"><span class="l '+c.status+'"></span><span class="lname">'+c.name+'</span><span class="ldet">'+(c.detail||'')+'</span></div>'});
 box.innerHTML=h}
function render(s){
 var dot=document.getElementById('dot');dot.className='dot'+(s.running?' run':'');
 document.getElementById('stxt').textContent='['+(s.stage||'-')+'] '+s.detail+(s.vdui?(' - VDUI '+s.vdui):'')+(s.error?(' - '+s.error):'');
 var bn=document.getElementById('banner');if(s.running&&s.prompt){bn.style.display='block';bn.textContent=s.prompt}else bn.style.display='none';
 var bm=document.getElementById('batchmsg');if(s.batch_msg){bm.style.display='block';bm.textContent=s.batch_msg}else bm.style.display='none';
 renderStage('hardware',s.results.hardware);renderStage('reprogram',s.results.reprogram);renderStage('functional',s.results.functional);
 var ct=document.getElementById('cont');if(s.awaiting&&s.prompt){ct.style.display='block';document.getElementById('contmsg').textContent=s.prompt}else ct.style.display='none';
 var fp=document.getElementById('funcpanels'),fr=s.func_results||{},fk=Object.keys(fr);
 if(fk.length){var fh='<div class="grid">';fk.forEach(function(k){var st=fr[k];fh+='<div class="card"><h3>'+st.name+'</h3><div class="ovr '+ovClass(st.overall)+'">'+(st.overall||'-')+'</div>';(st.components||[]).forEach(function(c){fh+='<div class="lamp"><span class="l '+c.status+'"></span><span class="lname">'+c.name+'</span><span class="ldet">'+(c.detail||'')+'</span></div>'});fh+='</div>'});fp.innerHTML=fh+'</div>'}else fp.innerHTML='';
 var btns=document.querySelectorAll('.bar button');btns.forEach(function(x){if(x.id!='stopbtn'&&!/rescan|Power|Reset/.test(x.title+x.textContent))x.disabled=!!s.running});
 document.getElementById('stopbtn').disabled=!s.running;
 if(s.batch&&s.batch.length){document.getElementById('batchpanel').style.display='block';
  var h='<table><tr><th>#</th><th>VDUI</th><th>A hw</th><th>B reprog</th><th>C func</th><th>overall</th><th>time</th></tr>';
  s.batch.forEach(function(r,i){h+='<tr><td>'+(i+1)+'</td><td>'+r.vdui+'</td><td>'+r.hardware+'</td><td>'+r.reprogram+'</td><td>'+r.functional+'</td><td class="'+(r.overall=='PASS'?'ok':'bad')+'">'+r.overall+'</td><td>'+r.time+'</td></tr>'});
  document.getElementById('batchtbl').innerHTML=h+'</table>'}
 document.getElementById('log').textContent=(s.log||[]).join('\n');
}
function poll(){fetch('/status').then(function(r){return r.json()}).then(render).catch(function(){})}
setInterval(poll,1500);poll();
</script></body></html>"""


def _page():
    return (PAGE.replace("__VDUIS__", json.dumps(VDUI_LIST))
                .replace("__MERGED__", json.dumps(list(MERGED_HEXES)))
                .replace("__FACTORY__", json.dumps(list(FACTORY_HEXES)))
                .replace("__DEFM__", DEFAULT_MERGED).replace("__DEFF__", DEFAULT_FACTORY)
                .replace("__DEVSRC__", DEV_SOURCE.replace('"', "'"))
                .replace("__METERSRC__", STATE["meter"]))


def main():
    global PAGE
    PAGE = _page()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8792
    print("VX-0057 Station: %d devices (%s) | %d merged / %d factory hexes | PSU=%s | meter=%s | injector=%s"
          % (len(VDUI_LIST), DEV_SOURCE, len(MERGED_HEXES), len(FACTORY_HEXES),
             C.PSU_PORT or "manual", STATE["meter"], STATE["injector"]))
    print("Testbench fw: %s (%s)" % (os.path.basename(C.TESTBENCH_MERGED),
                                     "found" if os.path.exists(C.TESTBENCH_MERGED) else "MISSING"))
    print("Open http://127.0.0.1:%d/" % port)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
