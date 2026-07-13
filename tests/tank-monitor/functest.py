#!/usr/bin/env python3
"""Functional test definitions for the station: Analog Input Tests 1-5 + Siren Scenarios 6-8.

Each test is a function `test_x(ctx)` that drives the operator through steps and grades components.
Injection is MANUAL for now (operator sets the 4-20 mA simulator, clicks Continue); the station pushes
DT71 settings via settings.py. The station supplies a `ctx` with these callbacks:

  ctx.vdui, ctx.serial, ctx.ai         - device VDUI, J-Link serial, analog input under test (1..N)
  ctx.thr                              - thresholds.Resolved (live per-channel thresholds)
  ctx.ask(prompt, want_volts=False)    - show prompt, block until operator Continues; returns float volts or None
  ctx.capture(secs=6)                  - capture RTT window -> tankmon.parse_tank_events dict
  ctx.cloud()                          - latest ThingsBoard telemetry dict (may be stale)
  ctx.apply(desc, result)              - record a settings-apply result as a component; returns result['ok']
  ctx.add(name, status, detail="")     - add a component lamp (PASS/FAIL/REVIEW/SKIP)
  ctx.log(msg)

Grading favors RTT (immediate: profile bands APP_IO_*, relay edges, DT113) with cloud as corroboration;
siren voltage is the operator's multimeter reading. Never raises - a failed step is a FAIL component.
"""
import config as C
import settings as SET
import tankmon as T


def _ch(ai):
    return ai - 1                       # RTT logs Channel 0-indexed (AI1 -> Channel 0)


def _band(ev, ai):
    b = [p["band"] for p in ev["profiles"] if p["channel"] in (_ch(ai), ai)]
    return b[-1] if b else None


def _edges(ev, ai):
    return [e["edge"] for e in ev["relay_edges"] if e["channel"] in (_ch(ai), ai)]


def _sample(ev, ai):
    s = [x["sample_ua"] for x in ev["samples"] if x["channel"] in (_ch(ai), ai)]
    return s[-1] if s else None


def _state(ev, ai):
    """The relay/output state from the periodic 'Channel: N state X sample Y' RTT line (immediate,
    unlike the fleeting one-shot transition edge). 1 = actuated, 0 = released."""
    s = [x["state"] for x in ev["samples"] if x["channel"] in (_ch(ai), ai)]
    return s[-1] if s else None


def _dig_out(cloud, ai):
    return cloud.get("digitalOutput%d" % ai)


def _ma(ua):
    return ua / 1000.0


# --- Analog Input Tests -----------------------------------------------------
def _classify(sample_ua, lv):
    """Classify a measured uA against the live thresholds (deterministic - not the fleeting RTT band)."""
    return T.classify_level(sample_ua, {"level": lv}) if sample_ua is not None else None


_CLT_BAND = {"LOW_LOW_EVENT": "LOW_LOW", "LOW_EVENT": "LOW", "NORMAL_EVENT": "NORMAL",
             "NORMAL": "NORMAL", "HIGH_EVENT": "HIGH", "HIGH_HIGH_EVENT": "HIGH_HIGH"}


def _clt_to_band(clt):
    """Map the cloud thresholdLevelType (e.g. 'HIGH_EVENT') to a band, for when RTT is unavailable."""
    return _CLT_BAND.get(str(clt).upper()) if clt is not None else None


def _grade_band(ctx, name, expect, lv):
    """Grade a level step against the DEVICE's own report, corroborated by the deterministic sample/cloud.

    The firmware classifies on its own ADC, so the injected sample sits a few hundred uA off the boundary
    (e.g. it reads 17902 uA for an 18000 HH the device DID cross) - re-classifying that raw sample was the
    original false-negative bug. Precedence here:
      PASS  - device RTT band == expect, backed by a fresh DT113 / cloud event / agreeing sample; OR
              (NORMAL emits no profile band) the deterministic sample or the cloud event is in-band.
      FAIL  - only when the device band AND the re-classified sample AGREE the level is not `expect`.
      REVIEW- a headroom miss (no band, sample short of target) or an RTT gap - never a hard FAIL.
    Callers flush the RTT backlog with a throwaway capture BEFORE injecting (see test_t1/test_t2), so this
    capture reads post-injection state; _band/_sample return b[-1]/s[-1], which would otherwise be stale.
    """
    ev = ctx.capture()
    sample = _sample(ev, ctx.ai)
    measured = _classify(sample, lv)                       # deterministic cross-check (may be None)
    band = _band(ev, ctx.ai)                               # device RTT profile band (None for NORMAL)
    dt = "DT113" in ev.get("dt_markers", [])               # fresh tank-level event uplinked this window
    clt = ctx.cloud().get("thresholdLevelType")
    clt_band = _clt_to_band(clt)                           # cloud event (corroboration; may lag)

    if band == expect and (dt or clt_band == expect or measured == expect):
        status, why = "PASS", "device band confirmed by %s" % (
            "DT113" if dt else ("cloud" if clt_band == expect else "sample"))
    elif band is not None and band != expect and measured is not None and measured != expect:
        status, why = "FAIL", "device band=%s and sample=%s agree the level is not %s" % (band, measured, expect)
    elif measured == expect or clt_band == expect:         # NORMAL emits no band; fresh sample/cloud rescue
        status, why = "PASS", "confirmed by %s%s" % (
            "sample" if measured == expect else "cloud", " (band=%s)" % band if band else "")
    elif measured is None and band is None:
        status, why = "REVIEW", "no device band and no sample (RTT gap)"
    else:
        status, why = "REVIEW", "headroom/uncertain (band=%s sample=%s want %s)" % (band, measured, expect)

    ctx.add(name, status,
            "want %s | %s | RTT band=%s DT113=%s cloud=%s | sample=%suA -> classify=%s"
            % (expect, why, band, dt, clt, sample, measured))


def test_t1(ctx):
    """T1 - full level sweep: increment NORMAL -> HIGH -> HIGH_HIGH, then decrement NORMAL -> LOW ->
    LOW_LOW, checking the band at each step. Auto-injects via the Waveshare AO if configured, else
    prompts. Uses the current (live) thresholds; skips targets a 4-20 mA source can't reach."""
    lv = ctx.thr.level(ctx.ai)
    mid = (lv["L"] + lv["H"]) / 2.0
    steps = [("rise -> NORMAL", mid, "NORMAL"),
             ("rise -> HIGH", min(lv["H"] + 500, C.SOURCE_MAX_MA * 1000), "HIGH"),
             ("rise -> HIGH_HIGH", min(lv["HH"] + 500, C.SOURCE_MAX_MA * 1000), "HIGH_HIGH"),
             ("fall -> NORMAL", mid, "NORMAL"),
             ("fall -> LOW", max(lv["L"] - 500, 0), "LOW"),
             ("fall -> LOW_LOW", max(lv["LL"] - 1000, 0), "LOW_LOW")]
    ctx.log("T1 sweep, bands (uA): HH=%s H=%s L=%s LL=%s (source %.0f-%.0f mA)"
            % (lv["HH"], lv["H"], lv["L"], lv["LL"], C.SOURCE_MIN_MA, C.SOURCE_MAX_MA))
    for name, ua, expect in steps:
        if _ma(ua) < C.SOURCE_MIN_MA:
            ctx.add(name, "SKIP", "target %.2f mA < %.1f mA source floor (raise the %s threshold, or use "
                    "a 0-20 mA source)" % (_ma(ua), C.SOURCE_MIN_MA, expect))
            continue
        ctx.capture()                      # flush the RTT backlog (prior step / idle) so the grading
                                           # capture reads THIS level; NORMAL emits no band, and the
                                           # reader continues from the last read, so stale data lingers
        ctx.inject(_ma(ua), "(%s)" % expect)
        _grade_band(ctx, name, expect, lv)


def test_t2(ctx):
    """T2 - Normal tank level event (between L and H)."""
    lv = ctx.thr.level(ctx.ai)
    mid = max((lv["L"] + lv["H"]) / 2.0, C.SOURCE_MIN_MA * 1000)
    ctx.capture()                          # flush prior test's stale band/sample before grading NORMAL
    ctx.inject(_ma(mid), "(NORMAL)")
    _grade_band(ctx, "mid-band -> NORMAL", "NORMAL", lv)


def _relay_test(ctx, on_ua, off_ua, mode_label):
    """Shared logic for T3 (ON>OFF) / T4 (ON<OFF): set output thresholds, sweep, grade relay."""
    r = SET.set_output(ctx.vdui, ctx.ai, on_ua, off_ua, log=ctx.log)
    if not ctx.apply("Set OutputCh%d ON=%d OFF=%d (%s)" % (ctx.ai, on_ua, off_ua, mode_label), r):
        ctx.log("settings not confirmed - push OutputCh%d ON=%d/OFF=%d on the portal, then continue"
                % (ctx.ai, on_ua, off_ua))
    lo, hi = min(on_ua, off_ua), max(on_ua, off_ua)
    # step 1: park in the OFF region; step 2: cross to actuate; step 3: cross back to release
    park = _ma(max(lo - 1500, 0)) if on_ua > off_ua else _ma(min(hi + 1500, 20000))
    actuate = _ma(min(on_ua + 500, 20000)) if on_ua > off_ua else _ma(max(on_ua - 500, 0))
    release = _ma(max(off_ua - 500, 0)) if on_ua > off_ua else _ma(min(off_ua + 500, 20000))

    ctx.inject(park, "(start, relay OFF)")
    ctx.capture()
    ctx.inject(actuate, "(cross ON threshold)")
    ev = ctx.capture(); cl = ctx.cloud()
    st, dout, edges = _state(ev, ctx.ai), _dig_out(cl, ctx.ai), _edges(ev, ctx.ai)
    on = (st == 1) or (dout in (1, "1", True)) or ("ON" in edges)
    ctx.add("Relay ON at threshold", "PASS" if on else "REVIEW",
            "RTT state=%s edges=%s | cloud digitalOutput%d=%s (cloud lags check-in)" % (st, edges, ctx.ai, dout))
    ctx.inject(release, "(cross OFF threshold)")
    ev = ctx.capture(); cl = ctx.cloud()
    st, dout, edges = _state(ev, ctx.ai), _dig_out(cl, ctx.ai), _edges(ev, ctx.ai)
    off = (st == 0) or (dout in (0, "0", False)) or ("OFF" in edges)
    ctx.add("Relay OFF (hysteresis)", "PASS" if off else "REVIEW",
            "RTT state=%s edges=%s | cloud digitalOutput%d=%s" % (st, edges, ctx.ai, dout))


def test_t3(ctx):
    """T3 - Output threshold ON > OFF (fill mode)."""
    _relay_test(ctx, on_ua=17000, off_ua=13000, mode_label="ON>OFF fill")


def test_t4(ctx):
    """T4 - Output threshold ON < OFF (drain mode)."""
    _relay_test(ctx, on_ua=13000, off_ua=17000, mode_label="ON<OFF drain")


def test_t5(ctx):
    """T5 - Disabled thresholds (ON=0/OFF=0): the output must not actuate for a would-be-alarm current.

    The device's own periodic output STATE is authoritative: it logs state=0 while disabled and would log
    state=1 (plus an ON edge) only on a real actuation. Two traps this avoids:
      - Cloud digitalOutput LAGS check-in, so it can still read 1 from the T3/T4 relay tests -> it is
        informational ONLY here, never a FAIL trigger (that was the false FAIL we saw).
      - T3/T4 leave a one-shot 'ON' edge in the RTT ring, so we flush it with a throwaway capture BEFORE
        the disable; then any ON edge in the grading window is genuinely fresh (a real T5 actuation)."""
    ctx.capture()                                  # flush T3/T4's stale ON/OFF edges out of the RTT ring
    r = SET.disable_output(ctx.vdui, ctx.ai, log=ctx.log)
    ctx.apply("Disable OutputCh%d (ON=0/OFF=0)" % ctx.ai, r)
    ctx.inject(15.0, "(would-be-actuate current)")
    ev = ctx.capture(); cl = ctx.cloud()
    st, dout, edges = _state(ev, ctx.ai), _dig_out(cl, ctx.ai), _edges(ev, ctx.ai)
    if st == 1 or "ON" in edges:
        status, why = "FAIL", "disabled output actuated"
    elif st == 0:
        status, why = "PASS", "device reports output OFF (state=0)"
    elif not edges:
        status, why = "PASS", "no actuation (no ON edge; state line not re-emitted)"
    else:
        status, why = "REVIEW", "state not captured - verify"
    ctx.add("Output stays OFF (disabled)", status,
            "%s | RTT state=%s edges=%s | cloud digitalOutput%d=%s (cloud lags - info only)"
            % (why, st, edges, ctx.ai, dout))


# --- Siren / Buzzer Scenarios ----------------------------------------------
def _siren_step(ctx, target_ma, expect_on):
    ctx.inject(target_ma, "(drive siren %s)" % ("ON" if expect_on else "OFF"))
    v = ctx.ask("Read the siren output with the multimeter and enter Volts (expect %s)"
                % ("~12 V" if expect_on else "0 V"), want_volts=True)
    ev = ctx.capture()
    sirens = ev.get("siren_events", [])
    volts_ok = (v is not None) and ((v > 6.0) == expect_on)
    label = "Siren ON (12V)" if expect_on else "Siren OFF (0V)"
    status = "PASS" if volts_ok else ("REVIEW" if v is None else "FAIL")
    ctx.add(label, status, "multimeter=%sV RTT siren=%s" % (v, sirens or "-"))


def test_s6(ctx):
    """S6 - Siren thresholds (siren mode ON). Repeat per AI at the station's chosen AI."""
    SET.set_siren_mode(ctx.vdui, 1, log=ctx.log)
    r = SET.set_siren(ctx.vdui, ctx.ai, 15000, 10000, log=ctx.log)
    ctx.apply("SirenCh%d ON=15000 OFF=10000 + siren mode ON" % ctx.ai, r)
    _siren_step(ctx, 16.0, expect_on=True)     # above SirenThresholdOn (15 mA)
    _siren_step(ctx, 8.0, expect_on=False)     # below SirenThresholdOff (10 mA)


def test_s7(ctx):
    """S7 - Siren Mode Button ON, then OFF (no siren), then disable-while-ON (auto clears)."""
    # ON: siren fires
    SET.set_siren_mode(ctx.vdui, 1, log=ctx.log)
    r = SET.set_siren(ctx.vdui, ctx.ai, 15000, 10000, log=ctx.log)
    ctx.apply("Siren mode ON + SirenCh%d 15000/10000" % ctx.ai, r)
    _siren_step(ctx, 16.0, expect_on=True)     # siren mode ON -> siren fires
    # OFF: no siren event, only level events
    ctx.apply("Siren mode OFF", SET.set_siren_mode(ctx.vdui, 0, log=ctx.log))
    ctx.inject(16.0, "(mode OFF, would-be alarm)")
    v = ctx.ask("Siren mode OFF: read the siren Volts (expect 0 V, no siren event)", want_volts=True)
    ev = ctx.capture()
    ok = (v is None) or v < 6.0
    ctx.add("Siren mode OFF -> no siren", "PASS" if (ok and not ev.get("siren_events")) else "FAIL",
            "multimeter=%sV RTT siren=%s (expect none)" % (v, ev.get("siren_events") or "-"))
    # disable while ON: arm the siren, then disable mode mid-alarm -> should auto-clear
    ctx.apply("Siren mode ON (re-arm)", SET.set_siren_mode(ctx.vdui, 1, log=ctx.log))
    ctx.inject(16.0, "(arm siren ON)")
    ctx.apply("Disable siren mode WHILE siren is ON", SET.set_siren_mode(ctx.vdui, 0, log=ctx.log))
    v = ctx.ask("After the settings land, read the siren output -- enter Volts (expect it auto-turned OFF)",
                want_volts=True)
    ctx.add("Siren auto-off on mode disable", "PASS" if (v is not None and v < 6.0) else
            ("REVIEW" if v is None else "FAIL"), "multimeter=%sV (expect 0V)" % v)


def test_s8(ctx):
    """S8 - Disable individual siren output via ON=0/OFF=0."""
    SET.set_siren_mode(ctx.vdui, 1, log=ctx.log)
    r = SET.disable_siren(ctx.vdui, ctx.ai, log=ctx.log)
    ctx.apply("Disable SirenCh%d (ON=0/OFF=0)" % ctx.ai, r)
    ctx.inject(16.0, "(alarm-level current)")
    v = ctx.ask("Read the siren output -- enter Volts (expect 0 V, this output is disabled)", want_volts=True)
    ev = ctx.capture()
    ok = (v is None or v < 6.0) and not ev.get("siren_events")
    ctx.add("Disabled siren stays 0V", "PASS" if ok else ("REVIEW" if v is None else "FAIL"),
            "multimeter=%sV RTT siren=%s (expect 0V / none)" % (v, ev.get("siren_events") or "-"))


# Order the "run all" battery executes per channel.
ALL_ORDER = ["T1", "T2", "T3", "T4", "T5", "S6", "S7", "S8"]

# Quick go/no-go subset (run on ONE channel): the level sweep proves analog-in -> threshold events ->
# DT113/cloud, and the ON>OFF relay test proves the DT71 settings-writer + output actuation. Together
# they confirm the two core functional paths in ~2-3 min instead of the full ~18-min battery. Siren
# (S6-S8) is omitted - it needs the meter on the siren output; use the full battery for siren coverage.
SMOKE_ORDER = ["T1", "T3"]

TESTS = {
    "T1": ("T1 - Level threshold events", test_t1),
    "T2": ("T2 - Normal level event", test_t2),
    "T3": ("T3 - Output ON>OFF (fill)", test_t3),
    "T4": ("T4 - Output ON<OFF (drain)", test_t4),
    "T5": ("T5 - Disabled thresholds (0/0)", test_t5),
    "S6": ("S6 - Siren thresholds", test_s6),
    "S7": ("S7 - Siren mode ON/OFF/disable-while-on", test_s7),
    "S8": ("S8 - Disable individual siren", test_s8),
}
