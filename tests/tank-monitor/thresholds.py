#!/usr/bin/env python3
"""Read the device's LIVE per-channel thresholds from ThingsBoard and derive S3/S4
sweep plans. READ-ONLY (reuses tests/cloud-checkin/tb_client.py). Falls back to the
static CONFIGURED_THRESHOLDS_UA in config.py if the cloud can't be reached.

Why: cloud-pushed thresholds change (e.g. a reflash resets them to factory defaults), so
run.py reads them live before S3/S4/S5 instead of trusting a hardcoded band. This module
also flags sweep points a 4-20 mA source physically can't hit (>= ceiling / < 4 mA floor).

Run standalone for a report:  python thresholds.py
"""
import os
import sys

import config as C

_CLOUD_DIR = os.path.join(os.path.dirname(__file__), "..", "cloud-checkin")

# Device-reported telemetry keys (per channel n = 1..4).
LEVEL_KEYS = {"HH": "tankLevelThresholdsCh{n}HighHigh", "H": "tankLevelThresholdsCh{n}High",
              "L": "tankLevelThresholdsCh{n}Low", "LL": "tankLevelThresholdsCh{n}LowLow"}
RELAY_KEYS = {"on": "outputThresholdsCh{n}On", "off": "outputThresholdsCh{n}Off"}
SIREN_KEYS = {"on": "sirenThresholdsCh{n}On", "off": "sirenThresholdsCh{n}Off"}


def _ma(ua):
    return None if ua is None else ua / 1000.0


def _g(ma):
    return "n/a" if ma is None else f"{ma:g}mA"


def _ge_target(thr):
    """Target to satisfy sample >= thr (drive just above, clamp to ceiling). Returns (ma, note).
    thr AT the ceiling is still reachable (== thr triggers a >= band); only thr strictly above is not."""
    hi = C.INJECTOR_MAX_MA
    tgt = round(min(thr + 0.5, hi), 2)
    if tgt >= thr:
        return tgt, ""
    return tgt, " [UNREACHABLE: threshold above 20mA ceiling]"


def _le_target(thr):
    """Target to satisfy sample <= thr (drive just below, clamp to floor). Returns (ma, note)."""
    lo = C.INJECTOR_MIN_MA
    tgt = round(max(thr - 0.5, lo), 2)
    note = ""
    if tgt > thr:
        note = " [UNREACHABLE: threshold below injector floor]"
    elif thr < C.LOOP_VALID_MIN_MA:
        note = " [sub-4mA: out-of-range-low, 0-20 mode]"
    return tgt, note


def derive_level_bands(level):
    """level = {HH,H,L,LL} in uA -> [(label, target_ma), ...] bracketing each boundary, with
    reachability baked into the label. HIGH/HIGH_HIGH are '>=' bands (reachable at full-scale
    even when the threshold sits at the 20 mA ceiling); LOW/LOW_LOW are '<=' bands."""
    HH, H, L, LL = (_ma(level.get(k)) for k in ("HH", "H", "L", "LL"))
    out = []
    if L is not None and H is not None:
        out.append(("rise->NORMAL", round((L + H) / 2, 2)))
    for lab, thr in ((f"rise->HIGH (>={_g(H)})", H), (f"rise->HIGH_HIGH (>={_g(HH)})", HH)):
        if thr is not None:
            ma, note = _ge_target(thr)
            out.append((lab + note, ma))
    if L is not None and H is not None:
        out.append(("fall->NORMAL", round((L + H) / 2, 2)))
    for lab, thr in ((f"fall->LOW (<={_g(L)})", L), (f"fall->LOW_LOW (<={_g(LL)})", LL)):
        if thr is not None:
            ma, note = _le_target(thr)
            out.append((lab + note, ma))
    return out


def derive_relay_steps(relay):
    """relay = {on,off} in uA -> [(label, target_ma), ...] crossing both edges. Handles both
    ON>OFF (Test 3) and ON<OFF (Test 4) since it just brackets the low and high thresholds."""
    on, off = _ma(relay.get("on")), _ma(relay.get("off"))
    pts = sorted(v for v in (on, off) if v is not None)
    if not pts:
        return []
    lo_thr, hi_thr = pts[0], pts[-1]
    out = [(f"below {_g(lo_thr)} (start)", round(max(lo_thr - 1.5, C.INJECTOR_MIN_MA), 2))]
    ma, note = _ge_target(lo_thr)
    out.append((f"cross {_g(lo_thr)}" + note, ma))
    out.append(("between (hold)", round((lo_thr + hi_thr) / 2, 2)))
    ma, note = _ge_target(hi_thr)
    out.append((f"cross {_g(hi_thr)}" + note, ma))
    return out


class Resolved:
    def __init__(self, source, per_channel):
        self.source = source                 # "cloud" | "config"
        self.per_channel = per_channel        # {ai: {"level":{}, "relay":{}, "siren":{}}}

    def level(self, ai):
        return self.per_channel.get(ai, {}).get("level") or C.CONFIGURED_THRESHOLDS_UA["level"]

    def relay(self, ai):
        return self.per_channel.get(ai, {}).get("relay") or C.CONFIGURED_THRESHOLDS_UA["relay"]

    def for_classify(self, ai):
        return {"level": self.level(ai)}

    def s3_steps(self, ai):
        return derive_level_bands(self.level(ai))

    def s4_steps(self, ai):
        return derive_relay_steps(self.relay(ai))


def read_live(device_id=None, channels=(1, 2, 3, 4)):
    device_id = device_id or C.TB_DEVICE_ID
    sys.path.insert(0, os.path.abspath(_CLOUD_DIR))
    import tb_client
    tb = tb_client.ThingsBoard().login()
    keys = [k.format(n=n) for n in channels
            for grp in (LEVEL_KEYS, RELAY_KEYS, SIREN_KEYS) for k in grp.values()]
    ts = tb.latest_timeseries(device_id, keys)

    def val(key):
        v = ts.get(key)
        if isinstance(v, list) and v:
            try:
                return int(float(v[0]["value"]))
            except (ValueError, TypeError, KeyError):
                return None
        return None

    per = {}
    for n in channels:
        per[n] = {grp_name: {k: val(t.format(n=n)) for k, t in grp.items()}
                  for grp_name, grp in (("level", LEVEL_KEYS), ("relay", RELAY_KEYS),
                                        ("siren", SIREN_KEYS))}
    return per


def resolve(device_id=None):
    """Live thresholds if the cloud is reachable, else config fallback (all channels)."""
    try:
        per = read_live(device_id)
        if per.get(1, {}).get("level", {}).get("HH") is not None:
            return Resolved("cloud", per)
        print("  [thresholds] cloud returned no level thresholds; using config fallback")
    except Exception as e:                    # cloud unreachable / creds missing / import
        print(f"  [thresholds] live read failed ({e}); using config CONFIGURED_THRESHOLDS_UA")
    fb = {n: {"level": C.CONFIGURED_THRESHOLDS_UA["level"],
              "relay": C.CONFIGURED_THRESHOLDS_UA["relay"], "siren": {}}
          for n in (1, 2, 3, 4)}
    return Resolved("config", fb)


def _report():
    r = resolve()
    print(f"Threshold source: {r.source.upper()}"
          + ("  (live from ThingsBoard)" if r.source == "cloud" else "  (config fallback)"))
    for ai in (1, 2, 3, 4):
        lv, rl = r.level(ai), r.relay(ai)
        print(f"\nCh{ai}  level(uA): HH={lv.get('HH')} H={lv.get('H')} "
              f"L={lv.get('L')} LL={lv.get('LL')}   relay(uA): on={rl.get('on')} off={rl.get('off')}")
        print("  S3 level sweep:")
        for lab, ma in r.s3_steps(ai):
            print(f"    {ma:5.2f} mA  {lab}")
        print("  S4 relay sweep:")
        for lab, ma in r.s4_steps(ai):
            print(f"    {ma:5.2f} mA  {lab}")
    print("\nNote: [UNREACHABLE]/[sub-4mA] bands can't be crossed by a 4-20 mA source at these "
          "thresholds. Push operational thresholds (bands well inside 4-20 mA) for full coverage.")


if __name__ == "__main__":
    _report()
