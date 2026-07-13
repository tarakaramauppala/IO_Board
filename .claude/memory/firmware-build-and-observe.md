---
name: firmware-build-and-observe
description: vx_ioboard_fw — three images are one repo's build variants; how to build/flash/observe and the built-in boot self-test hook
metadata:
  type: project
---

`tank-monitor`, `callbox`, `rtu` are **build-time variants of ONE repo** (`vx_ioboard_fw`,
Zephyr/nRF Connect SDK, nRF5340). Reviewed at v2.0.4 / commit `0097161`.

**Selecting the variant** (`tools/make/config.mk`, then `make build`):
`WITH_APPLICATION_IO_BOARD_TYPE` = **0 tank / 1 callbox / 2 rtu** / 3 turnstile. ⚠️ **Default is
3 (turnstile)** — always set 0/1/2 explicitly for our images. Boot RTT prints `Application type
io_tank_monitor|io_call_box|io_rtu` to confirm which image is running.

**Observe over RTT** (J-Link). Logging is **RTT-only** (`CONFIG_LOG_BACKEND_UART=n`), default level
INFO. Matches the bench (no serial). Boot-success anchor: `Firmware version %s` + `vx_app: Viaanix
APP Init`.

**⭐ Built-in boot self-test** — set `WITH_TESTBENCH=y` (`CONFIG_FULL_TESTBENCH`, sleep window
`SLEEP_TEST_TIME_S`=5s). At boot `VxAppTestbench_Run()` prints bracketed pass/fail over RTT for
power rails, ext-memory, DI1-4, analog AN channels (µA), RS-232/RS-485 echo, and (full) LoRaWAN
join + cell serial/SIM. Banners: `***IO BOARD TEST STARTED***` … `***IO BOARD TEST ENDED***`.
This is the primary hook for `/build-test-plan` IO/power/comms checks.

**APPROTECT on provisioned units (confirmed on bench 2026-06-12, J-Link S/N 822000970):** a
programmed/provisioned VX-0057 has **readback protection (APPROTECT) ENABLED** — `nrfjprog`
reads fail with "Secure access protection is enabled… readback protection… use --recover", and
**RTT/SWD debug is BLOCKED (RTT capture comes back empty)**. So: a locked production unit **cannot
be observed over RTT** — verify it **cloud-side** instead. To use the RTT-based bench tests you must
flash a **debug build with APPROTECT disabled** via `nrfjprog --recover` (full chip-erase) — which
**ERASES the provisioned image + its certs/provisioning state** (re-provisions on next boot via claim
certs). Never `--recover` a provisioned unit without explicit confirmation.

**Gotchas:** (1) **chip-erase flash required** for K3/K4 relays — see [[nrf5340-nfc-relay-pins]].
(2) Watchdog (120s, RESET_SOC) runs while halted under the debugger → breakpoints reset the board
(`wdt_setup` options=0). (3) Default build doesn't sleep (sleep FSM `#if 0`'d) — see
[[bench-power-and-observe]]. (4) Board DTS/pinctrl is in the out-of-tree `zephyr_boards` repo,
not in vx_ioboard_fw.

Full reference: `docs/firmware/vx_ioboard_fw-common.md`. Cloud side: [[cloud-telemetry-path]].
