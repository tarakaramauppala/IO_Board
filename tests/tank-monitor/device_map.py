#!/usr/bin/env python3
"""Per-board device map for the multi-board station dashboard.

Loads {VDUI -> {app_eui, app_key}} from an Excel workbook (the operator pastes an Excel of VDUIs at
secrets/device_map.xlsx). VDUI == DevEUI == the ThingsBoard device name (VX-0057 / Siffron convention).
Mirrors Siffron's control_dashboard.load_vduis(). READ-ONLY, never raises: a missing/garbled Excel
falls back to the single device configured in config.py so the dashboard always boots.

NOTE: this module is intentionally named device_map (NOT devices) so it never shadows the vendor
`devices` package (vendor/vx_programmer/devices) that flash_board.py imports for the nRF key math.

Expected columns (header row, case/space/'/'-insensitive; positional 0/1/2 if headers unrecognized):
  VDUI / DevEUI | AppEUI (JoinEUI) | AppKey
"""
import os

import config as C

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEVICE_MAP_XLSX = os.environ.get("DEVICE_MAP_XLSX", os.path.join(REPO, "secrets", "device_map.xlsx"))

_VDUI_KEYS = ("vdui", "deveui", "dev eui")
_APPEUI_KEYS = ("appeui", "app eui", "joineui", "join eui")
_APPKEY_KEYS = ("appkey", "app key")


def _norm(h):
    return (str(h) if h is not None else "").strip().lower().replace("/", " ").replace("_", " ")


def _match(header, keys):
    h = _norm(header)
    return any(k in h for k in keys)


def load_devices(path=None):
    """Return {VDUI_UPPER: {"app_eui", "app_key"}} from the Excel; {} on any problem (never raises)."""
    path = path or DEVICE_MAP_XLSX
    if not os.path.exists(path):
        return {}
    try:
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return {}
        hdr = list(rows[0])
        has_header = any(_match(h, _VDUI_KEYS + _APPEUI_KEYS + _APPKEY_KEYS) for h in hdr)
        ci_v = ci_e = ci_k = None
        if has_header:
            for i, h in enumerate(hdr):
                if ci_v is None and _match(h, _VDUI_KEYS):
                    ci_v = i
                elif ci_e is None and _match(h, _APPEUI_KEYS):
                    ci_e = i
                elif ci_k is None and _match(h, _APPKEY_KEYS):
                    ci_k = i
        ci_v = 0 if ci_v is None else ci_v
        ci_e = 1 if ci_e is None else ci_e
        ci_k = 2 if ci_k is None else ci_k
        data = rows[1:] if has_header else rows
        out = {}
        for row in data:
            if not row or ci_v >= len(row) or row[ci_v] in (None, ""):
                continue
            vdui = str(row[ci_v]).strip().upper()
            app_eui = str(row[ci_e]).strip() if ci_e < len(row) and row[ci_e] else ""
            app_key = str(row[ci_k]).strip() if ci_k < len(row) and row[ci_k] else ""
            if vdui:
                out[vdui] = {"app_eui": app_eui, "app_key": app_key}
        return out
    except Exception:
        return {}


def devices_with_fallback(path=None):
    """(devices_dict, source_note). Excel if present+parseable, else the single config.py device."""
    d = load_devices(path)
    if d:
        return d, "excel:%s (%d devices)" % (os.path.basename(path or DEVICE_MAP_XLSX), len(d))
    if C.DEVICE_UUID and C.DEVICE_APP_EUI and C.DEVICE_APP_KEY:
        return ({C.DEVICE_UUID.upper(): {"app_eui": C.DEVICE_APP_EUI, "app_key": C.DEVICE_APP_KEY}},
                "config.py single device (drop secrets/device_map.xlsx for the full list)")
    return {}, "NONE - no secrets/device_map.xlsx and no device in config.py"


if __name__ == "__main__":
    devs, src = devices_with_fallback()
    print("source:", src)
    for v in sorted(devs):
        e = devs[v]
        print("  %s  app_eui=%s  app_key=%s" % (
            v, "set" if e.get("app_eui") else "MISSING", "set" if e.get("app_key") else "MISSING"))
