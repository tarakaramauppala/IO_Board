#!/usr/bin/env python3
"""Tank-monitor test runner. See plan.md.

Usage:
  python run.py boot                 # S1 flash + boot/identity (RTT, auto)
  python run.py selftest             # S2 IO/power self-test (RTT, auto core)
  python run.py thresholds           # S3 level events (guided AI sweep)
  python run.py relay                # S4 relay hysteresis (guided)
  python run.py siren                # S5 siren/light (guided, multimeter)
  python run.py all                  # S1..S5
  python run.py --capture-only 30    # dump 30s RTT (debug)
Options: --no-flash, --image PATH, --net-image PATH, --duration S
"""
import argparse
import sys
import time
from datetime import datetime, timezone

import config as C
import tankmon as T
import thresholds as TH

LINE = "-" * 70


def _say(msg): print(msg, flush=True)
def _ask(msg): return input(msg).strip()
def _ask_float(msg):
    while True:
        v = _ask(msg)
        if v == "":
            return None
        try:
            return float(v)
        except ValueError:
            _say("  (enter a number, or blank to skip)")


_INJECTOR = None
_INJECTOR_TRIED = False


def _injector():
    """Lazily open the Waveshare injector once. Returns driver, or None for manual fallback."""
    global _INJECTOR, _INJECTOR_TRIED
    if _INJECTOR_TRIED:
        return _INJECTOR
    _INJECTOR_TRIED = True
    if not C.WAVESHARE_PORT:
        return None
    try:
        import waveshare
        _INJECTOR = waveshare.WaveshareAO().open(C.WAVESHARE_PORT, C.WAVESHARE_BAUD, C.WAVESHARE_ADDR)
        _INJECTOR.all_off()
        _say(f"  [injector] Waveshare AO on {C.WAVESHARE_PORT} @ {C.WAVESHARE_BAUD} "
             f"addr {C.WAVESHARE_ADDR} (fw v{_INJECTOR.version()/100:.2f})")
    except Exception as e:
        _say(f"  [injector] unavailable ({e}) - falling back to manual prompts")
        _INJECTOR = None
    return _INJECTOR


def _flash(args):
    """Flash via the proven vendor/Siffron pylink recipe (keys @0xFC000 + APPROTECT +
    merged + factory), probe pinned by serial. Returns True on success."""
    import flash_board
    _say("Flashing (vendor recipe: settings block + APPROTECT + merged + factory)...")
    r = flash_board.program(merged=args.image or None)   # None -> config defaults
    if not r.get("ok"):
        _say("  FLASH FAILED: " + str(r.get("error")))
    return bool(r.get("ok"))


def scope_boot(args, run_id):
    _say(f"{LINE}\nS1 - Boot & identity")
    if not args.no_flash:
        if not _flash(args):
            return False
    rtt = T.capture_rtt(args.duration or C.DEFAULT_BOOT_CAPTURE_S,
                        reset_first=True, stop_on=C.SIG_APP_INIT)
    res = T.parse_boot(rtt)
    res["overall"] = "PASS" if res["passed"] else "FAIL"
    _say(f"  app_type={res['app_type']} version={res['version']} init={res['app_init']}")
    if res["reasons"]:
        _say("  reasons: " + "; ".join(res["reasons"]))
    T.write_result("S1-boot", res, rtt, run_id)
    return res["passed"]


def scope_selftest(args, run_id):
    _say(f"{LINE}\nS2 - IO/power self-test  (needs WITH_TESTBENCH=y build)")
    _say("  NOTE: the v2.0.x RELEASE hex is the final app (no WITH_TESTBENCH) - the "
         "'***IO BOARD TEST...***' brackets will NOT appear. Power/analog/IO are read cloud-side.")
    if not args.no_flash:
        if not _flash(args):
            return False
    rtt = T.capture_rtt(args.duration or C.DEFAULT_SELFTEST_CAPTURE_S,
                        reset_first=True, stop_on=C.SIG_TEST_END)
    res = T.parse_selftest(rtt)
    res["overall"] = "PASS" if res["passed_core"] else "FAIL"
    _say(f"  ext_mem={res['ext_memory']} power={res['power']} "
         f"analog={res['analog']} rs232={res['rs232']} rs485={res['rs485']}")
    if res["reasons"]:
        _say("  core reasons: " + "; ".join(res["reasons"]))
    _say("  NOTE: DI/AN/RS232/RS485 lines are only meaningful WITH the field-IO rig; "
         "un-stimulated = 'not stimulated', not a fail.")
    T.write_result("S2-selftest", res, rtt, run_id)
    return res["passed_core"]


def _guided_ai_step(ai, label="", target_ma=None):
    """Set current on AI<ai> (auto via Waveshare if configured, else prompt),
    capture RTT, return (ma, rtt, transitions)."""
    inj = _injector()
    ao = C.AI_TO_AO.get(ai, ai)
    if inj is not None and target_ma is not None:
        try:
            inj.set_current_ma(ao, target_ma)
            ma = target_ma
            _say(f"  AI{ai}: injected {ma:.2f} mA on AO{ao} [{label}]")
            time.sleep(C.WAVESHARE_SETTLE_S)
        except Exception as e:
            _say(f"    [injector] set failed ({e}); prompting")
            inj = None
    if inj is None or target_ma is None:
        suffix = f" [{label}]" if label else ""
        hint = f" (suggest {target_ma:g})" if target_ma is not None else ""
        ma = _ask_float(f"  AI{ai}: set injected current in mA and press Enter "
                        f"(blank=skip){suffix}{hint}: ")
        if ma is None:
            return None, "", []
    rtt = T.capture_rtt(4.0, reset_first=False)
    tr = [t for t in T.parse_relay_transitions(rtt) if t["channel"] in (ai - 1, ai)]
    if tr:
        _say(f"    relay xition(s): {tr}")
    return ma, rtt, tr


def scope_thresholds(args, run_id):
    _say(f"{LINE}\nS3 - Threshold (level) events  [Tests 1/2/5]")
    thr = TH.resolve()          # live per-channel thresholds from cloud, else config fallback
    _say(f"  threshold source: {thr.source} (live cloud, else config fallback). Tank level events "
         "are DT61 (100..104: HIGH_HIGH=100 .. LOW_LOW=104); cloud derives level/percent from "
         "analogInputNcurrent. On RTT we confirm the mapped relay transitions + AN current.")
    steps = []
    for ai in range(1, 5):
        if _ask(f"  test AI{ai}? [y/N]: ").lower() != "y":
            continue
        lv = thr.level(ai)
        _say(f"    Ch{ai} level(uA): HH={lv.get('HH')} H={lv.get('H')} L={lv.get('L')} LL={lv.get('LL')}")
        for label, tgt in thr.s3_steps(ai):
            ma, rtt, tr = _guided_ai_step(ai, label, tgt)
            if ma is None:
                continue
            expect = T.classify_level(T.ua_from_ma(ma), thr.for_classify(ai))
            _say(f"    applied {ma} mA -> expected band {expect}")
            steps.append({"ai": ai, "ao": C.AI_TO_AO.get(ai, ai), "label": label,
                          "applied_ma": ma, "expected_band": expect,
                          "relay_transitions": tr})
    res = {"steps": steps,
           "injector": ("waveshare" if _injector() else "manual"),
           "threshold_source": thr.source,
           "thresholds_ua": {ai: thr.level(ai) for ai in (1, 2, 3, 4)},
           "auto_signal": "relay state transitions (RTT)",
           "deferred_cloud": "RTT logs bands ('Channel: n profile state: APP_IO_<BAND>') + DT113 marker live; cloud gives decoded tankNumber/thresholdLevelType/AI-value. DATA_TYPE_61 = check-in. Cross-check ThingsBoard.",
           "overall": "REVIEW (auto/manual stimulus + cloud-deferred events)"}
    T.write_result("S3-thresholds", res, None, run_id)
    return True


def scope_relay(args, run_id):
    _say(f"{LINE}\nS4 - Relay hysteresis  [Tests 3/4]")
    thr = TH.resolve()          # live per-channel relay thresholds from cloud, else config fallback
    _say(f"  threshold source: {thr.source} (live cloud, else config fallback). Drive AI across the "
         "relay on/off both ways; confirm continuity COM<->NO and watch RTT 'Channel: n, state transition'.")
    steps = []
    for ai in range(1, 5):
        if _ask(f"  test Relay{ai} (AI{ai})? [y/N]: ").lower() != "y":
            continue
        rl = thr.relay(ai)
        _say(f"    Ch{ai} relay(uA): on={rl.get('on')} off={rl.get('off')}")
        for label, tgt in thr.s4_steps(ai):
            ma, rtt, tr = _guided_ai_step(ai, label, tgt)
            if ma is None:
                continue
            cont = _ask("    relay continuity COM<->NO now? [on/off/skip]: ").lower()
            steps.append({"ai": ai, "relay": ai, "ao": C.AI_TO_AO.get(ai, ai),
                          "label": label, "applied_ma": ma,
                          "relay_transitions": tr, "continuity": cont})
        if ai in (3, 4):
            _say(f"    (Relay {ai} is on an NFC pin - if it never actuates, confirm the flash wrote NFCPINS.)")
    res = {"steps": steps, "injector": ("waveshare" if _injector() else "manual"),
           "threshold_source": thr.source,
           "thresholds_ua": {ai: thr.relay(ai) for ai in (1, 2, 3, 4)},
           "note": "RISING_EDGE~ON-side, FALLING_EDGE~OFF-side; continuity/DT90 authoritative.",
           "overall": "REVIEW (auto/manual stimulus + continuity)"}
    T.write_result("S4-relay", res, None, run_id)
    return True


def scope_siren(args, run_id):
    _say(f"{LINE}\nS5 - Siren / light + LED-buzzer  [Scenarios 6/7/8]")
    _say("Siren transitions are DBG-only (not on INFO RTT) - VERIFY WITH A MULTIMETER: "
         "12V ON / 0V OFF. Siren-mode & per-output disable need cloud settings (deferred).")
    steps = []
    for ai in range(1, 5):
        if _ask(f"  test Siren on AI{ai}? [y/N]: ").lower() != "y":
            continue
        for label in ("above SirenThresholdOn", "below SirenThresholdOff"):
            ma = _ask_float(f"    AI{ai} [{label}] applied mA (blank=skip): ")
            if ma is None:
                continue
            volts = _ask_float("      multimeter at siren output (V): ")
            steps.append({"ai": ai, "label": label, "applied_ma": ma, "siren_volts": volts,
                          "siren_on": (volts is not None and volts > 6.0)})
    res = {"steps": steps,
           "deferred_cloud": "SIREN_ON/SIREN_OFF (DT61); siren-mode button + individual disable (ON=0,OFF=0) need cloud config",
           "expected": "12V when ON, 0V when OFF",
           "overall": "REVIEW (multimeter + cloud-deferred)"}
    T.write_result("S5-siren", res, None, run_id)
    return True


def scope_watch(args, run_id):
    """Live RTT watch for manual injection: set/adjust the current by hand, then read back
    the per-channel sample, band, relay edges, siren state, and DataType markers. Repeat as
    you sweep. No stimulus automation - you turn the knob, this reports what the firmware did."""
    secs = args.duration or 15.0
    _say(f"{LINE}\nWATCH - live RTT for {secs:g}s. Set/adjust the injected current NOW.")
    rtt = T.capture_rtt(secs, reset_first=False)
    ev = T.parse_tank_events(rtt)
    if ev["siren_mode"] is not None:
        _say(f"  siren mode: {ev['siren_mode']} ({'ON' if ev['siren_mode'] else 'OFF/disabled'})")
    for s in ev["samples"]:
        _say(f"  ch{s['channel']}: sample {s['sample_ua']} uA (state {s['state']})")
    for p in ev["profiles"]:
        _say(f"  ch{p['channel']}: band APP_IO_{p['band']}")
    for e in ev["relay_edges"]:
        _say(f"  ch{e['channel']}: relay {e['edge']}  ({e['from']} -> {e['to']})")
    if ev["siren_events"]:
        _say(f"  siren events: {ev['siren_events']}")
    if ev["dt_markers"]:
        _say(f"  uplink DataType markers: {ev['dt_markers']}")
    if not any((ev["samples"], ev["profiles"], ev["relay_edges"], ev["siren_events"])):
        _say("  (no tank events this window - change the current more, or use --duration to widen)")
    T.write_result("watch", {"capture_s": secs, "events": ev}, rtt, run_id)
    return True


SCOPES = {"boot": scope_boot, "selftest": scope_selftest, "thresholds": scope_thresholds,
          "relay": scope_relay, "siren": scope_siren, "watch": scope_watch}


def main():
    ap = argparse.ArgumentParser(description="Tank-monitor test runner (see plan.md)")
    ap.add_argument("scope", nargs="?", choices=list(SCOPES) + ["all"], help="which scope to run")
    ap.add_argument("--no-flash", action="store_true", help="skip flashing (board already programmed)")
    ap.add_argument("--image", default=None, help="override tank merged hex (else TANK_IMAGE)")
    ap.add_argument("--net-image", default=None, help="optional net-core hex")
    ap.add_argument("--duration", type=float, default=None, help="RTT capture seconds")
    ap.add_argument("--capture-only", type=float, metavar="S", help="just dump S seconds of RTT")
    args = ap.parse_args()

    if args.capture_only:
        print(T.capture_rtt(args.capture_only, reset_first=False))
        return

    if not args.scope:
        ap.print_help()
        sys.exit(2)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    try:
        if args.scope == "all":
            order = ["boot", "selftest", "thresholds", "relay", "siren"]
            for i, s in enumerate(order):
                a = argparse.Namespace(**vars(args))
                if i > 0:
                    a.no_flash = True          # flash once, in boot
                SCOPES[s](a, run_id)
        else:
            SCOPES[args.scope](args, run_id)
    finally:
        if _INJECTOR is not None:
            _INJECTOR.close()
    print(f"{LINE}\nResults under results/{run_id}/tank-monitor/")


if __name__ == "__main__":
    main()
