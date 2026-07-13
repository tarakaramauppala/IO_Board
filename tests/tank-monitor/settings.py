#!/usr/bin/env python3
"""VX-0057 Tank Monitor DT71 settings writer (TEST DEVICE ONLY).

Authoritative DT71 encoding (from firmware source; see refs/vx_ioboard_fw settings_handler.c /
data_types.c / vx_app_tank.c):
  frame = 0x47  LEN_lo LEN_hi  TLV...        (LEN = number of TLV bytes, uint16 LE)
  TLV   = [type:1][data:N]                   (N is fixed per type; NO length byte)
  all thresholds are uint16 LE MICROAMPS (0..20000)  -- NOT float32.

Type table (TANK build):
  0x01 appCheckIn (2: unit,val) | 0x02-05 tankLevel Ch1-4 (8: HH,H,L,LL) |
  0x06-09 output Ch1-4 (4: ON,OFF) | 0x0A-0D siren Ch1-4 (4: ON,OFF) |
  0x0E sirenMode (1) | 0x0F extMemSave (1) | 0x10/0x11 OS-checkin HH/MM.
Relay/siren mode is implicit: ON>OFF = FILL, ON<OFF = DRAIN, ON==OFF==0 = DISABLED.

SAFE write = read the device's CURRENT frame, patch only the target TLVs, re-encode (preserving the
fw-version-specific tail), write server attrs settingsServer + settingsQueued=true, then poll the DT71
echo (settingsShared / decoded telemetry) until it reflects the change. Writes go ONLY to the authorized
test device; degrade to operator-push if the echo can't be confirmed.
"""
import time

import config as C

# --- pure DT71 codec (offline-testable; no cloud deps) ----------------------
DT71_TYPE = 0x47
TYPE_LEN = {0x01: 2, 0x02: 8, 0x03: 8, 0x04: 8, 0x05: 8, 0x06: 4, 0x07: 4, 0x08: 4, 0x09: 4,
            0x0A: 4, 0x0B: 4, 0x0C: 4, 0x0D: 4, 0x0E: 1, 0x0F: 1, 0x10: 1, 0x11: 1}
UA_MIN, UA_MAX = 0, 20000
OUTPUT_BASE, SIREN_BASE, LEVEL_BASE = 0x06, 0x0A, 0x02
SIREN_MODE = 0x0E


def _hex_to_bytes(s):
    return bytes.fromhex("".join(str(s).split()).replace("0x", ""))


def decode(frame_hex):
    """DT71 hex string -> ordered dict {type_int: bytes}. Stops at an unknown type (implicit tail)."""
    b = _hex_to_bytes(frame_hex)
    if not b or b[0] != DT71_TYPE:
        raise ValueError("not a DT71 frame (first byte %s)" % (b[:1].hex() if b else "empty"))
    length = b[1] | (b[2] << 8)
    tlv = b[3:3 + length]
    out = {}
    i = 0
    while i < len(tlv):
        t = tlv[i]
        n = TYPE_LEN.get(t)
        if n is None:
            break
        out[t] = tlv[i + 1:i + 1 + n]
        i += 1 + n
    return out


def encode(tlvs):
    """ordered dict {type_int: bytes} -> DT71 hex string (upper)."""
    body = bytearray()
    for t, data in tlvs.items():
        n = TYPE_LEN.get(t)
        if n is None or len(data) != n:
            raise ValueError("bad TLV type=0x%02X len=%d (expected %s)" % (t, len(data), n))
        body.append(t)
        body += bytes(data)
    frame = bytes([DT71_TYPE]) + len(body).to_bytes(2, "little") + bytes(body)
    return frame.hex().upper()


def _u16le(v):
    return int(max(UA_MIN, min(UA_MAX, round(v)))).to_bytes(2, "little")


def _read_u16le(data, off):
    return data[off] | (data[off + 1] << 8)


# --- TLV patch helpers (operate on a decoded dict; type must already exist) -
def _set(tlvs, t, data):
    if t not in tlvs:
        raise KeyError("type 0x%02X not in the device's current frame - refusing to invent it" % t)
    tlvs[t] = bytes(data)


def patch_output(tlvs, ch, on_ua, off_ua):
    _set(tlvs, OUTPUT_BASE + (ch - 1), _u16le(on_ua) + _u16le(off_ua))


def patch_siren(tlvs, ch, on_ua, off_ua):
    _set(tlvs, SIREN_BASE + (ch - 1), _u16le(on_ua) + _u16le(off_ua))


def patch_level(tlvs, ch, hh, h, l, ll):
    _set(tlvs, LEVEL_BASE + (ch - 1), _u16le(hh) + _u16le(h) + _u16le(l) + _u16le(ll))


def patch_siren_mode(tlvs, on):
    _set(tlvs, SIREN_MODE, bytes([1 if on else 0]))


def read_output(tlvs, ch):
    d = tlvs.get(OUTPUT_BASE + (ch - 1))
    return (_read_u16le(d, 0), _read_u16le(d, 2)) if d else None


def read_siren(tlvs, ch):
    d = tlvs.get(SIREN_BASE + (ch - 1))
    return (_read_u16le(d, 0), _read_u16le(d, 2)) if d else None


def read_level(tlvs, ch):
    d = tlvs.get(LEVEL_BASE + (ch - 1))
    return {"HH": _read_u16le(d, 0), "H": _read_u16le(d, 2),
            "L": _read_u16le(d, 4), "LL": _read_u16le(d, 6)} if d else None


# --- cloud writer (TEST DEVICE ONLY) ----------------------------------------
def _allowed():
    return {str(C.DEVICE_UUID).upper(), str(C.TB_DEVICE_ID)}


def _tb_and_id(vdui=None):
    import tb_client
    tb = tb_client.ThingsBoard().login()
    vdui = (vdui or C.DEVICE_UUID)
    if str(vdui).upper() == str(C.DEVICE_UUID).upper():
        dev_id = C.TB_DEVICE_ID
    else:
        dev_id = tb.device_id(vdui)
    if dev_id not in _allowed() and str(vdui).upper() not in _allowed():
        raise PermissionError("settings write refused: %r is not the authorized test device" % vdui)
    return tb, dev_id


def _attr(tb, dev_id, key):
    """Return the value of a device attribute (any scope), or None."""
    try:
        for a in tb.attributes(dev_id):
            if a.get("key") == key:
                return a.get("value")
    except Exception:
        pass
    return None


def current_frame(tb, dev_id):
    """The device's current settings frame hex (server preferred, else the device echo)."""
    return _attr(tb, dev_id, "settingsServer") or _attr(tb, dev_id, "settingsShared")


# Battery/orchestrator state: verify_writer() sets WRITER_OK; when False, apply() fast-fails instead of
# hanging on an echo that won't come. _DEFAULT_TIMEOUT is the echo-wait when a caller doesn't specify one.
WRITER_OK = None
_DEFAULT_TIMEOUT = 120


def set_echo_timeout(s):
    global _DEFAULT_TIMEOUT
    _DEFAULT_TIMEOUT = float(s)


def apply(vdui, patch_fn, checks=None, timeout=None, log=print):
    """Read current frame -> patch_fn(tlvs) -> write settingsServer+settingsQueued -> poll echo.
    Returns {ok, before, after, echo_ok, detail}. Fast-fails if verify_writer() found the path unusable."""
    if WRITER_OK is False:
        return {"ok": False, "echo_ok": False,
                "detail": "settings-writer disabled (echo path unconfirmed) - push this setting on the portal"}
    timeout = _DEFAULT_TIMEOUT if timeout is None else timeout
    tb, dev_id = _tb_and_id(vdui)
    cur = current_frame(tb, dev_id)
    if not cur:
        return {"ok": False, "detail": "no settingsServer/settingsShared attribute (can't patch safely)"}
    orig = decode(cur)
    tlvs = decode(cur)
    patch_fn(tlvs)
    new_hex = encode(tlvs)
    changed = {t for t in tlvs if tlvs.get(t) != orig.get(t)}
    if not changed:
        return {"ok": True, "before": cur, "after": new_hex, "echo_ok": True, "detail": "already at target"}
    tb.save_server_attributes(dev_id, {"settingsServer": new_hex, "settingsQueued": True})
    log("settings queued (changed %s); waiting for device echo (<=%ds)..."
        % (["0x%02X" % t for t in sorted(changed)], int(timeout)))
    deadline = time.time() + timeout
    while time.time() < deadline:
        shared = _attr(tb, dev_id, "settingsShared")
        if shared:
            try:
                sd = decode(shared)
                if all(sd.get(t) == tlvs[t] for t in changed):   # only the changed TLVs need match
                    return {"ok": True, "before": cur, "after": new_hex, "echo_ok": True,
                            "detail": "device echoed the changed settings"}
            except Exception:
                pass
        time.sleep(5)
    return {"ok": False, "before": cur, "after": new_hex, "echo_ok": False,
            "detail": "no confirming echo in %ds (downlink may not have reached device - cloud#538; push on portal)" % int(timeout)}


def verify_writer(vdui=None, timeout=90, log=print):
    """Probe the write path once, BEFORE the battery: re-write current settings UNCHANGED and watch
    settingsQueued clear (the Downlink Queue Handler rule chain processed it). Sets module WRITER_OK so
    apply() fast-skips instead of hanging if the path is unusable. Returns True if usable."""
    global WRITER_OK
    try:
        tb, dev_id = _tb_and_id(vdui)
        cur = current_frame(tb, dev_id)
        if not cur:
            WRITER_OK = False
            log("verify_writer: no settings frame -> writer unavailable (operator-push)")
            return False
        tb.save_server_attributes(dev_id, {"settingsServer": encode(decode(cur)), "settingsQueued": True})
        log("verify_writer: wrote current settings; watching settingsQueued clear...")
        deadline = time.time() + timeout
        while time.time() < deadline:
            q = _attr(tb, dev_id, "settingsQueued")
            if q is False or str(q).strip().lower() in ("false", "0", "none", ""):
                WRITER_OK = True
                log("verify_writer: OK - queue processed by rule chain; writer usable")
                return True
            time.sleep(5)
        WRITER_OK = False
        log("verify_writer: settingsQueued didn't clear in %ds -> writer unconfirmed (operator-push)" % timeout)
        return False
    except Exception as e:
        WRITER_OK = False
        log("verify_writer: error %s -> writer unavailable (operator-push)" % e)
        return False


# convenience wrappers used by station functional tests
def set_output(vdui, ch, on_ua, off_ua, **kw):
    return apply(vdui, lambda t: patch_output(t, ch, on_ua, off_ua), **kw)


def set_siren(vdui, ch, on_ua, off_ua, **kw):
    return apply(vdui, lambda t: patch_siren(t, ch, on_ua, off_ua), **kw)


def set_level(vdui, ch, hh, h, l, ll, **kw):
    return apply(vdui, lambda t: patch_level(t, ch, hh, h, l, ll), **kw)


def set_siren_mode(vdui, on, **kw):
    return apply(vdui, lambda t: patch_siren_mode(t, on), **kw)


def disable_output(vdui, ch, **kw):
    return apply(vdui, lambda t: patch_output(t, ch, 0, 0), **kw)


def disable_siren(vdui, ch, **kw):
    return apply(vdui, lambda t: patch_siren(t, ch, 0, 0), **kw)


if __name__ == "__main__":
    # offline self-check (no cloud): Output Ch1 ON=15000 / OFF=10000 => 47 05 00 06 98 3A 10 27
    ex = encode({0x06: _u16le(15000) + _u16le(10000)})
    expected = "47050006983A1027"
    print("known-vector:", ex, "==", expected, "->", ex == expected)
    d = decode(ex)
    print("decoded output Ch1 (on,off):", read_output(d, 1))
    assert ex == expected and read_output(d, 1) == (15000, 10000)
    assert encode(decode(ex)) == ex, "round-trip mismatch"
    print("round-trip OK")
