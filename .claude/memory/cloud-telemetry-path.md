---
name: cloud-telemetry-path
description: vx_ioboard_fw uplinks telemetry over cellular to AWS IoT (not directly ThingsBoard); LoRaWAN is runtime-disabled; key DataTypes DT90/DT104
metadata:
  type: project
---

**EMPIRICAL UPDATE (2026-06-12, verified on live device `104D1526064B6130`):** device telemetry
**DOES surface on ThingsBoard (VX Olympus), fully decoded** — the cloud parses the payload (TB topic
`vx_parsed/dev/715/103/Viaanix/...`) into named telemetry keys. So the test harness reads everything
from ThingsBoard via REST; no RTT/AWS subscriber needed. Likely flow: device→AWS (cellular) → VX
Olympus parser → ThingsBoard. The "telemetry only on AWS, TB=OTA" conclusion below was code-based and
is superseded by this observation (confirm the exact AWS→TB hop in `/understand-software`).

- **Bench tank-monitor device:** name/VDUI `104D1526064B6130`, TB id `022297c0-5d7e-11f1-8c71-25a5120ce367`,
  type `io_board_app_tank_monitor`, fw `io_tank_monitor v2.0.0`, APPROTECT-locked, check-in every 5 min.
- **TB telemetry key names (for tank tests):** `analogInput{1..4}current` (µA), `digitalOutput{1..4}`,
  `digitalInput{1..4}`, `tankNumber`+`thresholdLevelType` (e.g. `LOW_LOW_EVENT`), `...appLogic` (e.g.
  `['HEARTBEAT']`), `mainPower`/`extBattDc`/`powerSupply*`, `latitude`/`longitude`/`satellites` (GNSS),
  `cit`/`sn`/`ut`/`rt`/`payloadHex`. Settings echoed as `sh_*` / `tankLevelThresholds*` attributes.
- **→ Field-IO (S3/S4/S5) can be verified CLOUD-SIDE** (Riiai injects current → read TB keys), so the
  locked board needs no RTT and no chip-erase. See `tests/cloud-checkin/`.

---
Code-based view (firmware v2.0.4): the IO board's **telemetry path is cellular → AWS IoT MQTT/TLS:8883**.
`init_comm_mode()` has a hot-fix forcing `COMM_MODE_CELLULAR_ONLY` (`com_handler.c:1653`) and
`CONFIG_VX_ENABLE_LORAWAN` defaults n — so **LoRaWAN exists but is disabled at runtime**.
**ThingsBoard** is used only for **OTA + device attributes**, not the main telemetry.

**Endpoints** (baked into factory-data flash; dev/prod chosen by `CONFIG_USE_VIAANIX_DEV_ENDPOINT`):
- AWS telemetry: dev `mqtt.dev.viaanix.io` · prod `mqtt.iot.vxolympus.com`
- ThingsBoard (OTA): dev `mqtt.dev.vxolympus.com` · prod `ota.vxolympus.com`
- AWS upload topic: `vx_upload/<env>/715/103/Viaanix/<thing>`; thing-name = **VDUI hex string**
  (TB thing-name buffer = 16 hex / 8 bytes, e.g. `104D15221152ED18`; an earlier pass read 12-hex/6-byte — verify exact length against the device's registered name).

**Connecting OUR test harness to ThingsBoard (REST):** `requests` + `python-dotenv`. Creds in
`secrets/station.env` (`VX_TB_BASE_URL`/`VX_TB_USERNAME`/`VX_TB_PASSWORD`, least-privilege user);
device mapping in `secrets/device_map.yaml` (DUT serial → TB device UUID + name). Flow: `POST
/api/auth/login` → JWT (`X-Authorization: Bearer`); resolve device `GET /api/tenant/devices?deviceName=`;
read `GET /api/plugins/telemetry/DEVICE/{id}/values/timeseries`. **But TB only holds OTA/firmware
attributes + an OTA-status telemetry ({fw_title,fw_version,fw_state}) — NOT the DT90/DT104 sensor
telemetry (that's on AWS).** So a TB connection verifies device presence + firmware/OTA, not IO check-ins,
unless VX Olympus ingests AWS→TB (resolve in `/understand-software`).

⚠️ **Discrepancy to resolve:** `project.yaml` names the cloud as VX Olympus ThingsBoard
(`portal.dev.vxolympus.com`), but device telemetry actually publishes to **AWS IoT** (dev
`mqtt.dev.viaanix.io`). Likely AWS → ingested into VX Olympus. **Confirm during
`/understand-software`** (repo `715-unitedRentals-Cloud`) which broker/portal surfaces telemetry
for cloud check-in tests.

**Payload:** JSON with `ph` = hex blob of `[dt_id][fields]` records. Device-type IO_BOARD=0x0C.
Primary DataTypes: **DT90** (IO + power bitfield: dig in/out 1-4, main/ext/PSC power), **DT104**
(4-20mA analog in µA — channels: tank=4, callbox=20 w/ min/max/avg, rtu=4). Also DT88 (IMEI/SIM),
DT108 (rssi/operator), DT61 (events), DT89/66/109 (reset/FW). Cadence: OS check-in ~24h (+boot),
APP check-in ~1h + event-triggered.

Provisioning: **AWS Fleet Provisioning by claim** (template `UrIoBoard`); per-device certs in NVS.
Related: [[firmware-build-and-observe]]. Full reference: `docs/firmware/vx_ioboard_fw-common.md` §4-5.
