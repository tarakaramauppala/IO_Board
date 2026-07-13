# Tank Monitor QA — Progress Summary (2026-07-07)

Status write-up for the **Viaanix Tank Monitor (VX-0057 / nRF5340)** HIL + cloud QA automation.
Covers **what we did**, **where we are**, and **what's next**. Safe to share — no keys/passwords inlined
(secrets live in `secrets/` and `config.py`).

Companion docs: [PROJECT-STATUS.md](PROJECT-STATUS.md) (lifecycle log) · [HANDOFF.md](HANDOFF.md)
(single source of truth) · [docs/](docs/) (hardware/firmware/software reviews).

---

## TL;DR

We took the project from "tooling built, never run" to a **real board flashed, booting, and reporting to
the cloud**, fixed several genuine test-bench bugs, and built a **multi-board program-and-test dashboard**
modeled on the Siffron testbench. We then reviewed Viaanix's **official VX-0057 testbench** and the
**VX-0057 hardware repo**, and integrated the vendor testbench into our dashboard as a
**Hardware → Reprogram → Functional (A→B→C) pipeline** with per-component pass/fail lamps.

DUT `104D1526064B6130`: flashed **v2.0.4 dev (`d4ca9f20`)**, alive at 12 V / ~98 mA, **online**, **S1 boot
PASS**, cloud check-in fresh.

---

## What we did

### 1. First real bench run (was never done before)
- **`flash_board.py --verify-live`** (read-only) → on-chip identity at `0xFC000` matches computed keys →
  **board survived the earlier 24 V over-voltage incident**; probe + MCU reachable.
- **Full flash** of v2.0.4 dev (recover → erase → settings + APPROTECT → merged + factory → reset).
- **S1 boot/identity over RTT → PASS**: `io_board_app_tank_monitor`, `v2.0.4-h-d4ca9f20`, reached
  `Viaanix APP Init`.
- **Cloud verified**: device came back **online** after the reflash (was STALE ~23.5 h — the fw#311
  supercap→MQTT issue); ThingsBoard check-in fresh, confirming the full **device → cellular → AWS →
  ThingsBoard** path (settles the long-open "does telemetry reach TB?" question).

### 2. Real bugs found & fixed (all in this test repo)
- **`app_type` mismatch** — the runner expected `io_tank_monitor` but firmware emits
  `io_board_app_tank_monitor` (the `Firmware title` vs `Application type` strings). Fixed in `config.py`,
  the fixture, and `test_parse.py` → S1 went FAIL→PASS.
- **S3/S4 sweep bands** — the runner hardcoded the 7–10 mA compile defaults; now reads the **live
  cloud-configured thresholds** via new `thresholds.py` (falls back to config).
- **`DT113` correction reversed** — an earlier note wrongly claimed "no DT113"; live RTT shows the
  firmware logs **both** `DT113` (threshold events) and `DATA_TYPE_61` (check-in). Docs corrected.

### 3. Multi-board program-and-test **station dashboard** (new)
Modeled on the SiffronAutomation `control_dashboard.py`. New files under `tests/tank-monitor/`:
- **`station.py`** — stdlib `http.server` dashboard: VDUI combobox (from Excel), firmware dropdowns,
  J-Link picker, stage buttons, PSU control, live `/status`, `RUN_LOCK`/`PROBE_LOCK`, batch tally + CSV.
- **`device_map.py`** — loads `VDUI → AppEUI/AppKey` from `secrets/device_map.xlsx` (openpyxl), falls
  back to the single `config.py` device.
- **`psu.py`** — GW-Instek **GPD-3303S** driver with the global-output-enable safety (both channels
  ≤ 12 V before enabling) + `read_current()`.

### 4. Reviewed the vendor testbench + VX-0057 hardware (cloned into `refs/`)
- **`Viaanix/vx-testbench-releases`** (release `ioboard-1.0.0`): the official VX-0057 testbench — a Java
  tool driven by `rtu-test/test.js`, a VDUI Excel, a **WITH-TESTBENCH firmware**, publishing results to
  ThingsBoard. It's a **manufacturing hardware test** (self-test over serial/RTT + GDM8251 current meter);
  it does **not** verify cloud events.
- **`Viaanix/VX-0057`** (Altium hardware): nRF5340; **5 analog inputs** (4× 4-20 mA + 1× 0-10 V/24 V);
  4× opto DI; 4× relays K1–K4; 2× siren/light; RS-232 + RS-485; Quectel cell + SX1262 LoRa; QSPI flash.

### 5. Integrated the vendor testbench into the station (A→B→C pipeline)
- **A · Hardware Test** — flashes the vendor testbench fw → `tankmon.parse_testbench` grades each
  component (power, flash, DI1-4, AN1-5, RS232/485, LoRaWAN, Cell) + **Current** (0.5 A limit).
- **B · Reprogram** — flashes the normal v2.0.4 release.
- **C · Functional** — boot/identity (RTT) + ThingsBoard check-in.
- **Full (A→C)** one-click + **Batch** (one board/click, tally + CSV); results as per-component lamps.
- New **`meter.py`** — GW-Instek **GDM-8251A** SCPI driver (mode set per test). Current source order:
  GDM-8251A (if `METER_PORT` set) → PSU `IOUT?` → SKIP.
- Cloud-write to **change device settings** is authorized **only** for the test device (thresholds/siren
  mode etc. for Tests 4/5 & siren scenarios); all other cloud use stays read-only.

---

## Where we are

| Item | State |
|---|---|
| DUT `104D1526064B6130` | Flashed v2.0.4 dev, 12 V / ~98 mA, **online**, **S1 PASS** |
| Bench | J-Link probe `822006519`; PSU GPD-3303S on **COM4** (CH2 = 12 V); GDM-8251A meter present (not yet on a COM port) |
| Station dashboard | **http://127.0.0.1:8792/** — A/B/C pipeline, PSU live, current via PSU IOUT |
| Offline tests | `test_parse.py` **25/25** |
| Cloud | Read-only verified on ThingsBoard (VX Olympus); settings-write authorized for the test device only |
| Reference repos | `refs/VX-0057`, `refs/vx-testbench-releases`, `refs/vx_ioboard_fw`, `refs/715-unitedRentals-Cloud` |

**How to run**
```bash
pip install -r tests/tank-monitor/requirements.txt        # pymodbus, pyserial, openpyxl
# Multi-board station (PSU on COM4; add METER_PORT once the meter enumerates):
PSU_PORT=COM4 python tests/tank-monitor/station.py 8792    # -> http://127.0.0.1:8792/
# Single-purpose CLIs:
python tests/tank-monitor/flash_board.py --verify-live     # read-only identity check
python tests/tank-monitor/run.py boot --no-flash           # S1 boot over RTT
python tests/tank-monitor/thresholds.py                    # live cloud thresholds + sweep plan
python tests/cloud-checkin/check_checkin.py --device-id <UUID>
python tests/tank-monitor/test_parse.py                    # offline parser tests
```

---

## What's next

**Immediate (on the bench):**
- [ ] Run **A · Hardware Test** on the real board and confirm the vendor testbench firmware emits the
      self-test **over RTT** (our bench is RTT-only). *If it's UART-only, add a serial reader.*
- [ ] Get the **GDM-8251A** onto a COM port (USB + GW-Instek driver + enable remote interface), then set
      `METER_PORT` so the current check uses the meter (vendor-exact) instead of the PSU readout.
- [ ] Note: on a bare board, **DI/AN/RS232-485** read "needs harness/stimulus" (amber) — not real fails;
      they only PASS with the vendor's testbench-harness fixture.

**IO behavior tests (need the 4-20 mA injector + settings):**
- [ ] Push **operational thresholds** on the portal (e.g. HH18/H16/L14/LL12 mA) — the current factory
      defaults put **HIGH_HIGH at the 20 mA ceiling** (untestable by injection) and LOW_LOW below 4 mA.
- [ ] Run **Tests 1–5 + siren scenarios** (manual 4-20 mA injection over RTT + cloud), or automate with
      the Waveshare Modbus injector (`waveshare.py`, set `WAVESHARE_PORT`).

**Multi-board:**
- [ ] Drop the **VDUI Excel** at `secrets/device_map.xlsx` (columns: VDUI/DevEUI, AppEUI, AppKey) → the
      dashboard VDUI dropdown fills with every board; use **Batch** for the line.

**Lifecycle / deeper:**
- [ ] **`/understand-software`** on `715-unitedRentals-Cloud` → resolve the exact AWS→ThingsBoard path +
      the DT71 settings encoding, then build a **verified settings-writer** (so the station can push
      Tests 4/5 / siren-mode settings itself) and grade cloud **events** authoritatively.
- [ ] Build **callbox** + **rtu** test plans; review the out-of-tree `zephyr_boards` board repo (pin↔relay
      mapping).

**Known bugs to watch (from issue mining):**
- **fw#311** — supercap → "mqtt connect failed" (reflash recovers; likely the offline cause).
- **cloud#536** — out-of-range (<4 / >20 mA) analog handling unverified.
- **cloud#538 / #534** — dashboard→device downlinks can silently fail (fw version-string format + missing
  `powered=true`) → **verify comms device-side, not just cloud**.

---

## Bench / safety rules (carry-over)
- **12 V DC only** into the board (24 V damages it). PSU **output-enable is GLOBAL** — verify both
  channels ≤ 12 V before enabling.
- **Pin the J-Link serial** every op (3 probes on the bench). One J-Link op at a time; close the RTT
  Viewer GUI so the station's pylink access is free.
- **APPROTECT** must be written during flash or RTT locks out.
- **ASCII-only** console/log output (cp1252 bench crashes on unicode).
- **Source repos** (`refs/`) are **read-only** — a bug becomes a GitHub issue routed to the owning repo,
  never a code change. Cloud is read-only **except** authorized settings writes to the test device.
