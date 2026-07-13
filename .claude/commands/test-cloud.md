---
description: Verify a VX-0057 is checking in to ThingsBoard (VX Olympus) — tests/cloud-checkin/
argument-hint: "<device-uuid> | --device-name <VDUI-hex> | --device-name <serial> --from-map"
---

Run the **cloud check-in** verifier in `tests/cloud-checkin/` (read `plan.md` first). It reads the
device's latest telemetry from ThingsBoard over REST (read-only) and judges freshness — the way to
confirm a (possibly APPROTECT-locked) board is communicating to the cloud.

Steps:
1. Check `secrets/station.env` has `VX_TB_BASE_URL` + `VX_TB_USERNAME` + `VX_TB_PASSWORD` (a
   least-privilege VX Olympus user). If missing, tell the user to fill them — don't guess.
2. Determine the device: a ThingsBoard **device UUID** (most robust), or its **name = VDUI hex**
   (16 hex chars), or a serial mapped in `secrets/device_map.yaml` (`--from-map`). `$ARGUMENTS`
   carries what the user passed.
3. From `tests/cloud-checkin/`, run `python check_checkin.py <args>`.
4. Report the verdict: **PASS** (fresh telemetry → checking in), **STALE** (old data), or **FAIL**
   (no TB telemetry → it likely publishes to AWS IoT, not ThingsBoard — note this resolves the
   AWS-vs-TB question). Summarize the telemetry keys/ages + attributes from
   `results/<run-id>/cloud-checkin/checkin.json`.
5. If FAIL/empty, suggest next steps: confirm the device id/VDUI, check account scope (tenant vs
   customer), or verify on AWS IoT instead.
