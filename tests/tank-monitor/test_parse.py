#!/usr/bin/env python3
"""Offline self-test of the pure parsers — NO hardware needed.

Run: python test_parse.py   (exit 0 = all pass). Validates that the parsers match the real
firmware log strings against fixtures/boot_selftest_sample.log.
"""
import os
import sys

import tankmon as T

HERE = os.path.dirname(__file__)
FIXTURE = os.path.join(HERE, "fixtures", "boot_selftest_sample.log")

checks = []


def check(name, cond):
    checks.append((name, bool(cond)))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")


def main():
    text = open(FIXTURE, encoding="utf-8").read()

    print("parse_boot:")
    b = T.parse_boot(text)
    check("app_type == io_board_app_tank_monitor", b["app_type"] == "io_board_app_tank_monitor")
    check("version parsed", b["version"] == "v2.0.4-h-0097161")
    check("reached Viaanix APP Init", b["app_init"] is True)
    check("boot PASSED", b["passed"] is True)

    print("parse_selftest:")
    s = T.parse_selftest(text)
    check("brackets present", s["started"] and s["ended"])
    check("External Memory OK", s["ext_memory"] == "OK")
    check("Main Power ON", s["power"]["main"] == "ON")
    check("4 analog channels", len(s["analog"]) == 4)
    check("AN2 = 12000 uA", s["analog"].get(2, {}).get("ua") == 12000)
    check("RS232 + RS485 OK", s["rs232"] == "OK" and s["rs485"] == "OK")
    check("selftest core PASSED", s["passed_core"] is True)

    print("parse_relay_transitions:")
    tr = T.parse_relay_transitions(text)
    check("2 transitions on channel 0", len([t for t in tr if t["channel"] == 0]) == 2)
    check("ON then OFF edge", [t["edge"] for t in tr] == ["ON", "OFF"])

    print("parse_testbench:")
    tb = T.parse_testbench(text)
    names = {c["name"]: c["status"] for c in tb["components"]}
    check("tb started+ended", tb["started"] and tb["ended"])
    check("tb core_pass", tb["core_pass"] is True)
    check("External Memory PASS", names.get("External Memory") == "PASS")
    check("Main Power PASS", names.get("Main Power") == "PASS")
    check("RS232 PASS (fixture OK)", names.get("RS232") == "PASS")
    check("AN5 component present", "AN5" in names)       # 5 analog even if fixture lists 4
    check("DI1..DI4 present", all(("DI%d" % i) in names for i in (1, 2, 3, 4)))

    print("helpers:")
    check("classify_level(9.5mA)=HIGH", T.classify_level(T.ua_from_ma(9.5)) == "HIGH")
    check("classify_level(10.2mA)=HIGH_HIGH", T.classify_level(T.ua_from_ma(10.2)) == "HIGH_HIGH")
    check("classify_level(7.5mA)=LOW", T.classify_level(T.ua_from_ma(7.5)) == "LOW")
    check("classify_level(6.5mA)=LOW_LOW", T.classify_level(T.ua_from_ma(6.5)) == "LOW_LOW")
    check("classify_level(8.5mA)=NORMAL", T.classify_level(T.ua_from_ma(8.5)) == "NORMAL")

    failed = [n for n, ok in checks if not ok]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
