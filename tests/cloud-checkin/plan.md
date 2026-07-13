# Test plan — Cloud check-in (C5, common to all images)

> Verifies a VX-0057 is **communicating to the cloud** by reading its check-ins from **ThingsBoard
> (VX Olympus)** over the REST API — read-only, no device debug access needed. Works on an
> **APPROTECT-locked / provisioned** board (where bench RTT is blocked). Grounded in
> [USE-CASES.md C5](../../USE-CASES.md#c5--cloud-check-in-visible-deferred--tailscalethingsboard)
> and [cloud-telemetry-path](../../.claude/memory/cloud-telemetry-path.md).

## Why this exists / what it also settles
The bench board is APPROTECT-locked, so we can't watch it over RTT — the only way to confirm it's
talking to the cloud is **cloud-side**. This check also **empirically resolves the open AWS-vs-
ThingsBoard question**: the firmware publishes telemetry to **AWS IoT** and uses ThingsBoard for
OTA only ([firmware doc §4](../../docs/firmware/vx_ioboard_fw-common.md)). So:
- **Telemetry present + fresh on ThingsBoard** → VX Olympus is ingesting the device data (AWS→TB
  forward, or this build points TB) → cloud check-in confirmed.
- **No / only-OTA data on ThingsBoard** → telemetry is on AWS, not TB → we must verify on AWS
  instead (or stand up the AWS→TB/Tailscale forward).

## Mechanism
`POST /api/auth/login` → JWT → resolve device (by UUID, or by name = **VDUI hex**, e.g.
`104D15221152ED18`) → `GET /api/plugins/telemetry/DEVICE/{id}/values/timeseries` (+ attributes).
Creds from `secrets/station.env` (`VX_TB_BASE_URL/USERNAME/PASSWORD`, least-privilege user).

```mermaid
flowchart LR
  ENV[secrets/station.env] --> LOGIN[POST /api/auth/login → JWT]
  LOGIN --> DEV{resolve device}
  DEV -->|--device-id UUID| TS
  DEV -->|--device-name VDUI / --from-map| LOOKUP[/api/tenant/devices] --> TS[GET latest timeseries + attributes]
  TS --> JUDGE{newest point ≤ max-age?}
  JUDGE -->|yes| PASS[PASS: checking in]
  JUDGE -->|stale| STALE[STALE]
  JUDGE -->|none| FAIL[FAIL: no TB telemetry → likely on AWS]
```

## Steps / pass-fail
1. Fill `secrets/station.env` with a least-privilege VX Olympus user + base URL (gitignored).
2. Know the device's **VDUI / ThingsBoard device name** (16-hex; from provisioning / the TB portal)
   or its device UUID. Optionally map serial→device in `secrets/device_map.yaml`.
3. Run (see below). **PASS** = device resolves and its **newest telemetry is within `--max-age-min`**
   (default 90 min; APP check-in is ~hourly). **STALE** = data exists but old. **FAIL** = no
   telemetry (hasn't checked in, or telemetry isn't on ThingsBoard).
4. Result → `results/<run-id>/cloud-checkin/checkin.json` (keys, values, ages, attributes, verdict).

## How to run
```
# fill secrets/station.env first (VX_TB_USERNAME / VX_TB_PASSWORD)
python check_checkin.py --device-id <UUID>                 # most robust
python check_checkin.py --device-name 104D15221152ED18     # name = VDUI hex
python check_checkin.py --device-name SN-000001 --from-map # via secrets/device_map.yaml
python check_checkin.py --device-id <UUID> --max-age-min 70
```
Repo verb: **`/test-cloud`**.

## Caveats
- **Read-only**, least-privilege user — never an admin token. A *customer* (not tenant) account may
  not see `/api/tenant/devices`; pass `--device-id` directly in that case.
- ThingsBoard **telemetry key names** depend on how VX Olympus decodes the payload — this check is
  key-agnostic (judges on freshness of any telemetry). Mapping keys → DataTypes (DT90/DT104) is for
  `/understand-software`.
- This does **not** prove which radio carried it (cellular vs LoRaWAN) — only that data reached TB.
- JWT expires (~2.5 h); the client re-logs in automatically.
