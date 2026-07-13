# Firmware: callbox (`CONFIG_APPLICATION_TYPE_CALL_BOX`)

> One of three build variants of **`vx_ioboard_fw`** on the VX-0057. **Read the shared
> reference first:** [vx_ioboard_fw-common.md](vx_ioboard_fw-common.md). This file = the
> **callbox differences** only. HW: [main-board.md](../hardware/main-board.md). Use case:
> [USE-CASES.md](../../USE-CASES.md#callbox).

| | |
|---|---|
| **Image** | `callbox` → build type **1** (`WITH_APPLICATION_IO_BOARD_TYPE=1`, `application-1.conf`) |
| **App-type string** | `io_call_box` (RTT boot line `Application type io_call_box`) |
| **Source** | `src/app/vx_app_call_box.c` / `.h`; log tag `vx_call_box` |
| **Reviewed commit** | `0097161` (firmware v2.0.4) |

## What it does
A **mixed digital + analog** monitor: two **digital inputs** (bottom/top level sensors) plus two
**4-20 mA analog inputs** (flow rate, level), with computed **differential pressure**, two-sensor
tank fill logic + **sensor-fail detection**, and siren/light outputs. Event-driven uplinks on
top of the common periodic check-ins.

## IO usage (vs. the board's full set)
| Resource | callbox use |
|---|---|
| Digital inputs (DI1-4) | **Instances 1-2** — bottom/top tank-level sensors (`IO_HDL_IN_1..4`) |
| 4-20 mA analog | **Instances 3-4** — flow rate, level |
| Derived | **Differential pressure** = \|P1 − P2\| (`update_analog_measurements:745-749`) |
| Relay outputs (K1-4) | tank fill control + siren (via relay-activation bitmap settings) |
| Siren / Light | driven from `check_siren_input_state` per settings bitmap |

## Control logic
- **5 logical analog measurements** incl. the differential-pressure channel; per-channel
  **min/max thresholds**, **peak/average accumulation**, and a **3 s periodic analog log**
  (`vx_app_call_box.c:810-840`).
- **Two-sensor tank fill** logic with **sensor-fail detection** (`check_tank_output_states:458-495`).
- IO sampling tick **100 ms** (gated on main power).

## Telemetry specifics
- **DT104** analog: `number_channels = 20` (`dt104_handler.c:23`) — note callbox uploads the
  **expanded analog record** (per-channel current **plus min/max/avg** arrays), so DT104 is much
  larger than tank/RTU. Decode accordingly on the cloud side.
- **DT90** IO/power bits (digital-in 1-2 states, relay outputs, power).
- App **events** `PRESSURE_*`, `FLOW_RATE_*`, `LEVEL_*`, `SENSOR_FAILS` (DT61, `data_types.h:210-229`)
  — event-triggered check-ins.

## Test focus
- Drive **DI1/DI2** (level sensors) — verify `DI%d…` in the self-test and `DT90` bits + the
  fill-control relay response; verify **SENSOR_FAILS** event when sensor states are inconsistent.
- Inject **4-20 mA** on the analog instances — verify flow/level readings, **differential
  pressure**, min/max/avg accumulation, and the **PRESSURE/FLOW/LEVEL events**.
- Confirm **DT104 with 20 channels** is parsed correctly end-to-end (this is the callbox-specific
  cloud gotcha).
- Verify siren/light per the relay-activation bitmap settings.
- Boot signature includes `Application type io_call_box`.
