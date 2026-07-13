#!/usr/bin/env python3
"""Offline tests for the DT71 settings codec (settings.py) - NO hardware/cloud.

Run: python test_dt71.py   (exit 0 = all pass)
"""
import sys

import settings as S

checks = []


def check(name, cond):
    checks.append((name, bool(cond)))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")


def main():
    # known vector: Output Ch1 ON=15000 (0x3A98) / OFF=10000 (0x2710) -> 47 05 00 06 98 3A 10 27
    ex = S.encode({0x06: S._u16le(15000) + S._u16le(10000)})
    check("known vector 47050006983A1027", ex == "47050006983A1027")
    check("decode output Ch1 == (15000,10000)", S.read_output(S.decode(ex), 1) == (15000, 10000))
    check("round-trip encode(decode(x))==x", S.encode(S.decode(ex)) == ex)

    # a fuller realistic frame: appCheckIn + level Ch1 + output Ch1 + siren Ch1 + sirenMode + extMem
    tlvs = {
        0x01: bytes([1, 4]),                                  # appCheckIn unit=1,val=4
        0x02: S._u16le(20000) + S._u16le(15000) + S._u16le(5000) + S._u16le(2000),  # level Ch1
        0x06: S._u16le(17000) + S._u16le(13000),              # output Ch1 ON>OFF (fill)
        0x0A: S._u16le(15000) + S._u16le(10000),              # siren Ch1
        0x0E: bytes([1]),                                     # sirenMode on
        0x0F: bytes([0]),                                     # extMem tail
    }
    frame = S.encode(tlvs)
    dec = S.decode(frame)
    check("full-frame round-trip", S.encode(dec) == frame)
    check("read_level Ch1", S.read_level(dec, 1) == {"HH": 20000, "H": 15000, "L": 5000, "LL": 2000})
    check("read_output Ch1 == (17000,13000)", S.read_output(dec, 1) == (17000, 13000))
    check("read_siren Ch1 == (15000,10000)", S.read_siren(dec, 1) == (15000, 10000))

    # patch only the target TLV; everything else (incl. the 0x0F tail) is preserved
    S.patch_output(dec, 1, 12000, 18000)                      # now ON<OFF (drain)
    check("patch_output changed only Ch1", S.read_output(dec, 1) == (12000, 18000))
    check("tail 0x0F preserved after patch", 0x0F in S.decode(S.encode(dec)))
    check("siren Ch1 untouched by output patch", S.read_siren(dec, 1) == (15000, 10000))

    # clamp to 0..20000 uA
    S.patch_output(dec, 1, 99999, -5)
    check("clamp high->20000, low->0", S.read_output(dec, 1) == (20000, 0))

    # disable = 0/0
    S.patch_siren(dec, 1, 0, 0)
    check("disable siren -> (0,0)", S.read_siren(dec, 1) == (0, 0))

    failed = [n for n, ok in checks if not ok]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
