#!/usr/bin/env python3
"""Headless flash of the Tank Monitor (VX-0057, nRF5340).

Mirrors Siffron's siffron_qa/hil/program_board.py and the vendor vx_programmer
IOBoard recipe (vendor/vx_programmer/devices/jlink/IOBoard.py). ONE pylink session,
probe PINNED by serial (3 J-Links share this bench, so an unpinned open could hit
another board):

  nrfjprog --recover (unlock APPROTECT) -> preflight -> pylink open(serial_no) ->
  connect nRF5340_xxAA_APP -> [optional TRIGGER_FLEET_PROV over RTT ch2] -> reset ->
  erase -> write settings block @0xFC000 (magic + UUID + magic + AppKey + AppEUI,
  little-endian words) -> UICR APPROTECT + SECUREAPPROTECT = 0x50FA50FA ->
  flash_file(merged) -> flash_file(factory_data) -> reset.

Design (same hard rules as Siffron's program_board / the rest of the harness):
  * Flash via the J-Link flashloader (flash_file), NOT `nrfjprog --program --chiperase`.
  * Write APPROTECT + SECUREAPPROTECT so the debug port / RTT stay OPEN across resets
    (skipping this is why a plain flash leaves the board RTT-locked).
  * DEFENSIVE: every step wrapped; returns a result dict; NEVER raises; always closes
    the J-Link.
  * The key-word math REUSES the vendor NRF52.little_endian_word (single source of
    truth); the word ORDER is copied verbatim from IOBoard.try_flash.

CLI:
  python flash_board.py --verify-live   # READ-ONLY: read 0xFC000, compare to computed keys
  python flash_board.py --dry-run       # compute + print; touch no hardware
  python flash_board.py                 # full flash (merged + factory), then reset
  python flash_board.py --no-flash      # write keys + APPROTECT only (no hex)
  python flash_board.py --fleet-prov    # also trigger fleet re-provisioning first
Reads image paths / keys / probe serial from config.py (override via env or flags).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from typing import Optional

import config as C

# --- nRF5340 memory map (settings block + UICR) -----------------------------
UUID_BASE = 0x000FC000          # settings block: 10 words (magic+uuid+magic+key+eui)
KEY_WORD_COUNT = 10
MAGIC = 0xA55A5AA5              # NRF52.magic_number (written raw, NOT byte-swapped)
APPROTECT_ADDR = 0x00FF8000     # UICR.APPROTECT
SECUREAPPROTECT_ADDR = 0x00FF801C  # UICR.SECUREAPPROTECT
APPROTECT_DISABLE = 0x50FA50FA  # value that keeps the debug port open (nRF5340)

_VENDOR_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "vendor", "vx_programmer"))


# ---------------------------------------------------------------------------
# key layout -- REUSES the vendor little_endian_word (single source of truth)
# ---------------------------------------------------------------------------
def _le(word32: int) -> int:
    """Byte-swap a 32-bit word via the vendor NRF52.little_endian_word (same math the
    vx_programmer uses), so our on-flash layout is identical to the proven programmer."""
    if _VENDOR_DIR not in sys.path:
        sys.path.insert(0, _VENDOR_DIR)
    from devices.jlink.NRF52 import NRF52   # noqa: E402
    return int(NRF52.little_endian_word("0x%08X" % (word32 & 0xFFFFFFFF)), 16)


def build_key_words(uuid: str, app_eui: str, app_key: str) -> list[int]:
    """The 10 words written at 0xFC000, in the exact order of IOBoard.try_flash:
        [magic, uuid_msb, uuid_lsb, magic, key3, key2, key1, key0, eui_msb, eui_lsb]
    magic is raw; UUID/AppKey/AppEUI words are little-endian byte-swapped."""
    u = int(uuid, 16)
    k = int(app_key, 16)
    e = int(app_eui, 16)
    uuid_msb = _le((u >> 32) & 0xFFFFFFFF)
    uuid_lsb = _le(u & 0xFFFFFFFF)
    key3 = _le((k >> 96) & 0xFFFFFFFF)
    key2 = _le((k >> 64) & 0xFFFFFFFF)
    key1 = _le((k >> 32) & 0xFFFFFFFF)
    key0 = _le(k & 0xFFFFFFFF)
    eui_msb = _le((e >> 32) & 0xFFFFFFFF)
    eui_lsb = _le(e & 0xFFFFFFFF)
    return [MAGIC, uuid_msb, uuid_lsb, MAGIC, key3, key2, key1, key0, eui_msb, eui_lsb]


# ---------------------------------------------------------------------------
# nrfjprog helpers (defensive; return (rc, out, err), never raise)
# ---------------------------------------------------------------------------
def _nrfjprog(args: list[str]) -> tuple[int, str, str]:
    if not shutil.which("nrfjprog"):
        return (127, "", "nrfjprog not on PATH")
    try:
        r = subprocess.run(["nrfjprog", *args], capture_output=True, text=True, timeout=120)
        return (r.returncode, r.stdout, r.stderr)
    except Exception as e:
        return (1, "", str(e))


def recover(snr: int) -> tuple[bool, str]:
    """nrfjprog --recover (unlock APPROTECT on a locked board). Best-effort."""
    rc, out, err = _nrfjprog(["--recover", "-f", C.NRFJPROG_FAMILY, "-s", str(snr)])
    return (rc == 0, (out or err).strip().replace("\n", " ")[:120])


def preflight(snr: int) -> dict:
    """Debugger present (this serial in --ids) + target reachable (read APPROTECT)."""
    rc, out, _ = _nrfjprog(["--ids"])
    ids = [l.strip() for l in out.splitlines() if l.strip()]
    debugger = str(snr) in ids
    rc2, out2, err2 = _nrfjprog(["-f", C.NRFJPROG_FAMILY, "-s", str(snr),
                                 "--memrd", "0x00FF8000", "--n", "4"])
    target_ok = rc2 == 0
    detail = (f"ids={ids}" if debugger else f"serial {snr} NOT in --ids {ids}")
    if not target_ok:
        detail += f"; memrd failed: {(err2 or out2).strip()[:80]}"
    return {"debugger": debugger, "target_ok": target_ok, "ids": ids, "detail": detail}


# ---------------------------------------------------------------------------
# read-only: read the settings block currently on the board (the oracle)
# ---------------------------------------------------------------------------
def read_settings_block(snr: int, device: str) -> dict:
    """READ-ONLY: open, connect, read 10 words @0xFC000 + APPROTECT regs, close.
    No erase/write/reset. Used by --verify-live to validate probe + key math first."""
    res = {"ok": False, "serial": int(snr), "words": None,
           "approtect": None, "secureapprotect": None, "error": None}
    import pylink
    jlink = None
    try:
        jlink = pylink.JLink()
        jlink.open(serial_no=int(snr))
        jlink.set_tif(pylink.enums.JLinkInterfaces.SWD)
        jlink.connect(device, verbose=False)
        res["words"] = list(jlink.memory_read32(UUID_BASE, KEY_WORD_COUNT))
        try:
            res["approtect"] = jlink.memory_read32(APPROTECT_ADDR, 1)[0]
            res["secureapprotect"] = jlink.memory_read32(SECUREAPPROTECT_ADDR, 1)[0]
        except Exception:
            pass
        res["ok"] = True
    except Exception as e:
        res["error"] = f"read failed: {e}"
    finally:
        if jlink is not None:
            try:
                jlink.close()
            except Exception:
                pass
    return res


# ---------------------------------------------------------------------------
# fleet-provisioning trigger over RTT (mirrors vendor IOBoard.send_data_over_rtt)
# ---------------------------------------------------------------------------
def _trigger_fleet_prov(jlink) -> None:
    try:
        status = jlink.rtt_get_status()
        if getattr(status, "IsRunning", 0) == 0:
            jlink.rtt_start()
        for _ in range(10):
            try:
                if jlink.rtt_get_num_up_buffers() > 0:
                    break
            except Exception:
                pass
            time.sleep(0.2)
        data = list(bytearray("TRIGGER_FLEET_PROV", "utf-8")) + [0x0]
        for _ in range(5):
            if jlink.rtt_write(2, data):   # RTT channel 2
                break
            time.sleep(0.5)
        time.sleep(1)
    except Exception:
        pass   # best-effort; never blocks the flash


# ---------------------------------------------------------------------------
# the flash session (mirrors Siffron _write_keys_via_pylink + vendor order)
# ---------------------------------------------------------------------------
def _flash_via_pylink(snr: int, device: str, words: list[int],
                      merged: Optional[str], factory: Optional[str],
                      fleet_prov: bool) -> dict:
    res = {"ok": False, "before": None, "after_keys": None, "after_flash": None,
           "flashed_merged": False, "flashed_factory": False, "error": None}
    import pylink
    jlink = None
    try:
        jlink = pylink.JLink()
        jlink.open(serial_no=int(snr))
        jlink.set_tif(pylink.enums.JLinkInterfaces.SWD)
        jlink.connect(device, verbose=False)

        if fleet_prov:
            _trigger_fleet_prov(jlink)
            jlink.reset()

        try:
            res["before"] = list(jlink.memory_read32(UUID_BASE, KEY_WORD_COUNT))
        except Exception:
            res["before"] = None

        jlink.erase()                                            # full mass-erase
        jlink.memory_write32(UUID_BASE, list(words))             # settings block @0xFC000
        jlink.memory_write32(APPROTECT_ADDR, [APPROTECT_DISABLE])       # keep debug open
        jlink.memory_write32(SECUREAPPROTECT_ADDR, [APPROTECT_DISABLE])

        try:
            res["after_keys"] = list(jlink.memory_read32(UUID_BASE, KEY_WORD_COUNT))
        except Exception:
            res["after_keys"] = None
        if res["after_keys"] != list(words):
            res["error"] = ("settings-block write-back mismatch (0xFC000) — "
                            f"wrote {[hex(w) for w in words]} read {res['after_keys']}")
            return res

        if merged:
            jlink.flash_file(merged, 0x0)
            res["flashed_merged"] = True
        if factory:
            jlink.flash_file(factory, 0x0)
            res["flashed_factory"] = True

        try:
            res["after_flash"] = list(jlink.memory_read32(UUID_BASE, KEY_WORD_COUNT))
        except Exception:
            res["after_flash"] = None
        # not fatal if a hex legitimately rewrote 0xFC000, but surface it
        if res["after_flash"] is not None and res["after_flash"] != list(words):
            res["warn"] = "0xFC000 changed after flash_file (a hex wrote that region)"

        res["ok"] = True
        return res
    except Exception as e:
        res["error"] = f"pylink flash failed: {e}"
        return res
    finally:
        if jlink is not None:
            try:
                jlink.reset()   # boot the app; debug stays open (APPROTECT written)
            except Exception:
                pass
            try:
                jlink.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------
def program(*, jlink_serial: Optional[int] = None, device: Optional[str] = None,
            uuid: Optional[str] = None, app_eui: Optional[str] = None,
            app_key: Optional[str] = None, merged: Optional[str] = None,
            factory: Optional[str] = None, flash: bool = True,
            fleet_prov: bool = False, do_recover: bool = True,
            verify_live: bool = False, dry_run: bool = False) -> dict:
    """Flash the tank board (or --verify-live / --dry-run). NEVER raises."""
    snr = int(jlink_serial if jlink_serial is not None else C.JLINK_SERIAL)
    device = device or C.JLINK_DEVICE
    uuid = uuid or C.DEVICE_UUID
    app_eui = app_eui or C.DEVICE_APP_EUI
    app_key = app_key or C.DEVICE_APP_KEY
    merged = merged if merged is not None else C.TANK_IMAGE
    factory = factory if factory is not None else C.FACTORY_DATA_IMAGE

    result = {"ok": False, "serial": snr, "device": device, "uuid": uuid.upper(),
              "merged": merged, "factory": factory, "flashed": False,
              "steps": [], "error": None}

    def step(name, ok, detail=""):
        result["steps"].append({"name": name, "ok": ok, "detail": detail})
        print(f"  [{'OK ' if ok else 'ERR'}] {name}: {detail}")

    print("=" * 64)
    print(f"  TANK MONITOR FLASH  ->  VDUI {uuid.upper()}  (probe {snr}, {device})")
    print("=" * 64)

    if not (uuid and app_eui and app_key):
        result["error"] = "uuid, app_eui and app_key are all required"
        step("validate", False, result["error"])
        return result

    try:
        words = build_key_words(uuid, app_eui, app_key)
    except Exception as e:
        result["error"] = f"could not build key words: {e}"
        step("build_keys", False, result["error"])
        return result
    result["key_words"] = [f"0x{w:08X}" for w in words]
    step("build_keys", True, f"{len(words)} words @0x{UUID_BASE:08X}")
    for i, w in enumerate(words):
        print(f"        0x{UUID_BASE + i*4:08X} = 0x{w:08X}")

    if flash:
        for label, p in (("merged", merged), ("factory", factory)):
            if not p or not os.path.isfile(p):
                result["error"] = f"{label} hex not found: {p!r}"
                step("resolve_hex", False, result["error"])
                return result
        step("resolve_hex", True, f"merged+factory present")

    # --- READ-ONLY verify against the live board (the oracle) ---
    if verify_live:
        rb = read_settings_block(snr, device)
        if not rb["ok"]:
            result["error"] = rb["error"]
            step("verify_live", False, rb["error"])
            return result
        on_board = rb["words"]
        match = on_board == words
        step("verify_live", match,
             "0xFC000 on board MATCHES computed keys" if match
             else "MISMATCH (see below) — probe wrong OR keys differ; do NOT flash blindly")
        print("        on-board 0xFC000:", " ".join(f"{x:08X}" for x in on_board))
        print("        computed  0xFC000:", " ".join(f"{x:08X}" for x in words))
        if rb.get("approtect") is not None:
            print(f"        APPROTECT=0x{rb['approtect']:08X} "
                  f"SECUREAPPROTECT=0x{rb['secureapprotect']:08X} "
                  f"(0x{APPROTECT_DISABLE:08X}=open)")
        result["on_board_words"] = [f"0x{x:08X}" for x in on_board]
        result["ok"] = match
        return result

    if dry_run:
        step("dry_run", True, "no hardware touched")
        result["ok"] = True
        return result

    # --- unlock (best-effort) + preflight ---
    if do_recover:
        ok, detail = recover(snr)
        step("recover", ok, detail if ok else f"recover skipped/failed: {detail}")
        if ok:
            time.sleep(0.5)
    pf = preflight(snr)
    step("preflight", pf["target_ok"], pf["detail"])
    if not pf["debugger"]:
        result["error"] = f"probe {snr} not connected ({pf['detail']})"
        return result
    if not pf["target_ok"]:
        result["error"] = f"target not reachable via probe {snr} ({pf['detail']})"
        return result

    # --- the flash session ---
    kw = _flash_via_pylink(snr, device, words,
                           merged if flash else None,
                           factory if flash else None, fleet_prov)
    if kw.get("before") is not None:
        print("        before 0xFC000:", " ".join(f"{x:08X}" for x in kw["before"]))
    if kw.get("after_keys") is not None:
        print("        after  0xFC000:", " ".join(f"{x:08X}" for x in kw["after_keys"]))
    step("write_keys", kw.get("after_keys") == words, kw.get("error") or "settings block verified")
    if flash:
        result["flashed"] = kw.get("flashed_merged") and kw.get("flashed_factory")
        step("flash", result["flashed"],
             "flash_file merged+factory + APPROTECT/SECUREAPPROTECT" if result["flashed"]
             else str(kw.get("error")))
    if kw.get("warn"):
        step("post_flash_check", True, "WARN: " + kw["warn"])
    if not kw.get("ok"):
        result["error"] = kw.get("error") or "flash failed"
        return result

    print(f"\nVDUI {uuid.upper()} flashed + verified; board reset (debug/RTT open).")
    result["ok"] = True
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _cli(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    opts = {"flash": True, "fleet_prov": False, "verify_live": False,
            "dry_run": False, "do_recover": True}
    for a in argv:
        if a in ("-h", "--help"):
            print(__doc__)
            return 0
        elif a == "--no-flash":
            opts["flash"] = False
        elif a == "--fleet-prov":
            opts["fleet_prov"] = True
        elif a == "--verify-live":
            opts["verify_live"] = True
        elif a == "--dry-run":
            opts["dry_run"] = True
        elif a == "--no-recover":
            opts["do_recover"] = False
        else:
            print(f"error: unknown argument {a!r}", file=sys.stderr)
            return 2
    res = program(**opts)
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
