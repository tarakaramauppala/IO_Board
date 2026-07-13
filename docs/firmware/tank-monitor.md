# Firmware: tank-monitor (`CONFIG_APPLICATION_TYPE_TANK`)

> One of three build variants of **`vx_ioboard_fw`** on the VX-0057. **Read the shared
> reference first:** [vx_ioboard_fw-common.md](vx_ioboard_fw-common.md) (boot, RTT/log
> signatures, comms, cloud, provisioning, build, issues). This file = the **tank-monitor
> differences** only. HW: [main-board.md](../hardware/main-board.md). Use case:
> [USE-CASES.md](../../USE-CASES.md#tank-monitor).

| | |
|---|---|
| **Image** | `tank-monitor` → build type **0** (`WITH_APPLICATION_IO_BOARD_TYPE=0`, `application-0.conf`) |
| **App-type string** | `io_tank_monitor` (RTT boot line `Application type io_tank_monitor`) |
| **Source** | `src/app/vx_app_tank.c` / `.h`; log tag `vx_tank` |
| **Reviewed commit** | `0097161` (firmware v2.0.4) |

## What it does
Monitors tank level via the **four 4-20 mA analog inputs** and drives the **four relay
outputs** as fill/drain pump/valve controls, with an optional **siren + light** on threshold.
No digital inputs are used. Telemetry goes out on the common OS/APP check-ins (cellular→AWS).

## IO usage (vs. the board's full set)
| Resource | tank-monitor use |
|---|---|
| 4-20 mA analog (AIN0-3) | **All 4 used** — tank level/pressure per channel (`IO_HDL_4_20mA_1..4`, `analog_measurement[]`) |
| Digital inputs (DI1-4) | **Not used** |
| Relay outputs (K1-4 / `do1..do4`) | **All 4** — driven by per-channel fill/drain FSMs via `io_handler_set_output` |
| Siren / Light | Optional, gated by `siren_mode_enabled` setting (`update_siren`) |
| 0-10 V analog, RS-232/485 | not used by the app (RS lines still covered by the boot self-test) |

## Control logic
- **Per-channel level FSM** with **5 profile bands** — LOW_LOW / LOW / NORMAL / HIGH / HIGH_HIGH
  — with **250 µA hysteresis** (`update_profile`, `vx_app_tank.c:439-510`).
- **Fill/drain edge FSMs** (`handle_tank_fill_state` / `handle_tank_drain_state`) turn the relay
  outputs on/off as level crosses configured bands.
- IO sampling tick **100 ms** (gated on main power present).

## Telemetry specifics
- **DT104** analog: `number_channels = 4` (`dt104_handler.c:18-20`) — four 4-20 mA currents in µA.
- **DT90** IO/power bits as usual (relay out states, power rails).
- **DT113** threshold-crossing events (`tank_number`, `threshold_level`, `current_value_ua`).
- App **events** `VX_APP_EVENT_TANK_LEVEL_*` (DT61).
- **App commands** (cloud→device): `SIREN_LIGHT_ON`, `SIREN_SOUND_ON`, `OUTPUT_CONFIGURATION`
  (`data_types.h:277-280`).

## Test focus
- Inject known **4-20 mA currents** into channels 1-4; expect `AN%d: … (%d uA)` in the boot
  self-test and `DT104` (4 channels) on the cloud check-in; verify band classification + the
  relay output that each band drives.
- Verify **threshold events** (DT113) at band boundaries (mind the 250 µA hysteresis).
- Verify **siren/light** when `siren_mode_enabled` and a HIGH_HIGH/threshold condition.
- Confirm the four relays actuate — **K3/K4 require a chip-erase flash** (UICR NFCPINS, see
  common §10).
- Boot signature includes `Application type io_tank_monitor`.
