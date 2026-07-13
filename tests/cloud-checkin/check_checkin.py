#!/usr/bin/env python3
"""Verify a VX-0057 device is checking in to ThingsBoard (VX Olympus). See plan.md.

Resolves the device, pulls its latest telemetry timeseries + attributes, and judges
freshness (is the newest data point within --max-age-min?). Read-only. Also empirically
answers whether device telemetry actually lands on ThingsBoard (vs AWS IoT).

Usage:
  python check_checkin.py --device-id <UUID>
  python check_checkin.py --device-name 104D15221152ED18        # name = VDUI hex
  python check_checkin.py --device-name <serial> --from-map     # via secrets/device_map.yaml
Options: --max-age-min 90  --keys k1,k2
Creds come from secrets/station.env (VX_TB_BASE_URL/USERNAME/PASSWORD).
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import tb_client as TB

REPO = Path(__file__).resolve().parents[2]


def _from_device_map(serial):
    p = REPO / "secrets" / "device_map.yaml"
    if not p.exists():
        raise SystemExit(f"--from-map: {p} not found (copy device_map.example.yaml).")
    try:
        import yaml
    except ImportError:
        raise SystemExit("--from-map needs PyYAML (pip install pyyaml).")
    dev = (yaml.safe_load(p.read_text()) or {}).get("devices", {}).get(serial)
    if not dev:
        raise SystemExit(f"serial {serial!r} not in device_map.yaml")
    return dev.get("device_id"), dev.get("device_name")


def main():
    ap = argparse.ArgumentParser(description="Verify VX-0057 cloud check-in on ThingsBoard")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--device-id", help="ThingsBoard device UUID (most robust)")
    g.add_argument("--device-name", help="device name = VDUI hex (e.g. 104D15221152ED18), or a serial with --from-map")
    ap.add_argument("--from-map", action="store_true", help="resolve --device-name as a serial via secrets/device_map.yaml")
    ap.add_argument("--max-age-min", type=float, default=90.0, help="STALE if newest telemetry older than this (APP check-in is ~hourly)")
    ap.add_argument("--keys", default=None, help="comma-separated telemetry keys to fetch (default: all)")
    args = ap.parse_args()

    tb = TB.ThingsBoard().login()
    print(f"Connected: {tb.base} as {tb.username}")

    dev_id, dev_name = args.device_id, None
    if not dev_id:
        if args.from_map:
            dev_id, dev_name = _from_device_map(args.device_name)
        if not dev_id:
            dev_name = dev_name or args.device_name
            dev_id = tb.device_id(dev_name)
    print(f"Device: id={dev_id}" + (f" name={dev_name}" if dev_name else ""))

    keys = args.keys.split(",") if args.keys else None
    ts = tb.latest_timeseries(dev_id, keys)
    try:
        attrs = tb.attributes(dev_id)
    except Exception:
        attrs = {}

    now_ms = time.time() * 1000.0
    rows, newest = [], None
    for k, v in ts.items():
        pt = v[0] if isinstance(v, list) and v else {}
        t, val = pt.get("ts"), pt.get("value")
        age = (now_ms - t) / 60000.0 if t else None
        rows.append((k, val, age))
        if t and (newest is None or t > newest):
            newest = t
    rows.sort(key=lambda r: (r[2] if r[2] is not None else 1e12))

    print(f"\nTelemetry keys: {len(ts)}")
    for k, val, age in rows[:50]:
        age_s = f"{age:6.1f} min ago" if age is not None else "  no ts"
        print(f"  {k:30} = {str(val)[:42]:42}  ({age_s})")
    if attrs:
        print(f"\nAttributes: {len(attrs)}")
        for a in attrs[:30]:
            print(f"  {a.get('key'):28} = {str(a.get('value'))[:50]}")

    if newest is None:
        verdict, reason = "FAIL", ("no telemetry on this device — either it hasn't checked in, "
                                   "or telemetry lands on AWS IoT (not ThingsBoard)")
    else:
        age = (now_ms - newest) / 60000.0
        verdict = "PASS" if age <= args.max_age_min else "STALE"
        reason = f"newest telemetry {age:.1f} min old (threshold {args.max_age_min:.0f} min)"
    print(f"\n[{verdict}] {reason}")

    # --- result artifact ---
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = REPO / "results" / run_id / "cloud-checkin"
    out.mkdir(parents=True, exist_ok=True)
    (out / "checkin.json").write_text(json.dumps({
        "utc": datetime.now(timezone.utc).isoformat(), "base": tb.base,
        "device_id": dev_id, "device_name": dev_name,
        "verdict": verdict, "reason": reason,
        "newest_ts": newest, "max_age_min": args.max_age_min,
        "timeseries": ts, "attributes": attrs,
    }, indent=2, default=str))
    print(f"  -> results/{run_id}/cloud-checkin/checkin.json")
    sys.exit(0 if verdict == "PASS" else 1)


if __name__ == "__main__":
    try:
        main()
    except TB.TBError as e:
        print(f"\nThingsBoard error: {e}", file=sys.stderr)
        print("Fill VX_TB_BASE_URL / VX_TB_USERNAME / VX_TB_PASSWORD in secrets/station.env "
              "(least-privilege VX Olympus user).", file=sys.stderr)
        sys.exit(2)
