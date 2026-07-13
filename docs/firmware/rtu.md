# Firmware: rtu (`CONFIG_APPLICATION_TYPE_RTU`)

> One of three build variants of **`vx_ioboard_fw`** on the VX-0057. **Read the shared
> reference first:** [vx_ioboard_fw-common.md](vx_ioboard_fw-common.md). This file = the
> **RTU differences** only. HW: [main-board.md](../hardware/main-board.md). Use case:
> [USE-CASES.md](../../USE-CASES.md#rtu).

| | |
|---|---|
| **Image** | `rtu` → build type **2** (`WITH_APPLICATION_IO_BOARD_TYPE=2`, `application-2.conf`) |
| **App-type string** | `io_rtu` (RTT boot line `Application type io_rtu`) |
| **Source** | `src/app/vx_app_rtu.c` / `.h`; log tag `vx_rtu` |
| **Reviewed commit** | `0097161` (firmware v2.0.4) |

## What it does
The **most configurable / general-purpose** image — a true remote terminal unit. Uses **all**
field IO: **4 digital inputs + 4 analog (4-20 mA) inputs** feeding **4 relay outputs**, where
each output has independently configurable **on-trigger and off-trigger** rules, plus two
configurable sirens. Behaves as a programmable I/O→telemetry/control node.

## IO usage (vs. the board's full set)
| Resource | rtu use |
|---|---|
| Digital inputs (DI1-4) | **All 4** — usable as output triggers |
| 4-20 mA analog (AIN0-3) | **All 4** — usable as output triggers (over/under min/max) |
| Relay outputs (K1-4) | **All 4** — each via `vx_app_set_digital_output_state` → `io_handler_set_output` |
| Siren / Light | **2 configurable sirens** (digital + analog trigger bitmaps, `check_siren_state`) |

## Control logic
- Each of the **4 outputs** has independent **on-trigger** and **off-trigger** controls; each
  trigger is **NONE / DIGITAL / ANALOG**, decoded from packed setting nibbles
  (`update_settings:471-550`).
- **Analog logic**: over/under min/max (`enum app_io_control_analog_logic:151-158`).
- **Resets all output/siren states on power loss** (`reset_states:1127`).
- IO sampling tick **100 ms** (gated on main power). Note: RTU drives outputs through
  `vx_app_set_digital_output_state` (a different path than tank/callbox' direct `io_handler_set_output`).

## Telemetry specifics
- **DT104** analog: `number_channels = 4` (`dt104_handler.c:27`) — four 4-20 mA currents in µA.
- **DT90** IO/power bits — digital-in 1-4, digital-out 1-4, power rails (RTU exercises the full
  bitfield).
- App **events** `ANALOG_1..4_LOW/NORMAL/HIGH` (DT61).

## Test focus
- **Full IO matrix:** drive each **DI1-4** and inject each **AIN0-3** current; configure
  on/off-trigger rules and verify the mapped **relay output** actuates per DIGITAL/ANALOG logic
  and min/max thresholds.
- Verify **state reset on power loss** (toggle main power, confirm outputs/sirens clear).
- Verify the **two sirens** fire per their digital+analog trigger bitmaps.
- Confirm `DT90` (in+out bits) and `DT104` (4 analog channels) on the cloud check-in.
- **K3/K4 relays require a chip-erase flash** (UICR NFCPINS — common §10) — the RTU's full
  4-relay use makes this the variant most likely to expose the issue if missed.
- Boot signature includes `Application type io_rtu`.
