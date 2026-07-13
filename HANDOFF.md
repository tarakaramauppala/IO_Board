# Tank Monitor QA — Complete Handoff / Single Source of Truth

> One self-contained brief with everything known + built for the **Viaanix Tank Monitor
> (VX-0057 / nRF5340)** QA automation. Snapshot date: **2026-07-07**. Repo:
> `C:\claude\ioboard\io-board-testing`. Pairs with
> [docs/PROJECT-UNDERSTANDING-from-issues.md](docs/PROJECT-UNDERSTANDING-from-issues.md) (deep dive
> from 223 GitHub issues) and [PROJECT-STATUS.md](PROJECT-STATUS.md) (lifecycle status).
>
> **Safe to share:** no secrets are inlined here (keys/passwords live in `config.py` / `secrets/`).

---

## 0. TL;DR

We are building Siffron-style HIL + cloud QA automation for the **Tank Monitor** personality of the
Viaanix IO board. The board reads 4x **4-20 mA** tank inputs, drives **4 relays + a siren/light**, and
uplinks over **cellular (AWS IoT -> ThingsBoard)** and **LoRaWAN**. We flash it with a headless
Python flasher (mirrors the vendor programmer + the Siffron approach), stimulate the analog inputs
with a **Waveshare** injector, and verify behaviour **two ways**: over **RTT** (on-bench) and over
the **ThingsBoard cloud** (which reports full IO state). The connected DUT is device
**104D1526064B6130**, currently powered at 12 V on the bench.

---

## 1. Product & repos

**Product:** mains/battery industrial RTU on **VX-0057**, MCU **Nordic nRF5340** (dual-core, Minew
module), Zephyr / nRF Connect SDK 2.7.0. One firmware, four selectable personalities:
**Tank Monitor / RTU / Call Box / Turnstile**. We test **Tank Monitor only**.

| Repo | Role |
|---|---|
| `Viaanix/vx_ioboard_fw` | Firmware (the four personalities, comms, provisioning, testbench self-test) |
| `Viaanix/715-unitedRentals-Cloud` | **Cloud/tenant config** on VX Olympus (ThingsBoard) — rule chains, decoders, settings-hex + 4-20 mA/threshold conversions |
| `Viaanix/VX-0057` | Altium hardware (schematics/PCB/BOM) |
| `Viaanix/io-board-testing` | **This QA project** (on Viaanix's vx-station framework) |

Read-only clones of the first three are under `C:\claude\ioboard\refs\`. **Never modify/commit them.**

**Data flow:** device -> cellular LTE -> AWS IoT (`vx_upload/...`) -> AWS hex->JSON parser (external) ->
`vx_parsed/dev/715/103/Viaanix/io_board_app...` -> ThingsBoard native MQTT integration -> TB timeseries.
LoRaWAN path: SX1262 -> gateway -> ChirpStack -> sensor-data-decoders -> ThingsBoard.

---

## 2. Hardware facts (bench-critical)

- **POWER: 12 V DC ONLY** into the board (**24 V damages it** — do NOT reuse the Siffron/VX-0056 24 V
  assumption). Current limit ~1.5 A (inrush peaks ~1.37 A). Supercaps cause a **30-40 s delayed cold
  start** — don't grade boot too early.
- The "24 V" in the testbench doc is an internal on-board rail for 4-20 mA loop excitation, **not** the
  supply input.
- **PSU:** GW-Instek **GPD-3303S on COM4** (FTDI 0403:6001, SN EL855085), 9600 8N1. **Board is on
  CHANNEL 2.** OUTPUT-ENABLE IS GLOBAL (OUT1 powers both channels) — always set the *connected* channel
  (CH2) to 12 V and verify BOTH channels <=12 V before enabling output.
- **J-Links (3 on this bench):** EDU `261011253`, **Compact Base `822006519` = the tank-board DUT**,
  DK OB-SAM3U `683301942` (also shows as COM3 CDC UART). Always PIN the probe serial; an unpinned
  `open()` could hit another board.
- 4 DI (opto), 4x 4-20 mA, 1x 0-10 V analog, 4 relays (K3/K4 on NFC pins), 2 siren/light, RS-232/485.
  QSPI external flash on P0.13-P0.18; after that remap there are **zero free GPIO**.

---

## 3. Firmware facts

- Live device runs **v2.0.4 (hash d4ca9f20)**. Build variants: type 0 = tank (`io_tank_monitor`).
- App core = `vx_0057_b_cpuapp_no_tfm` (no TF-M). Net core runs the radio. Only the **APP core** is
  flashed (`nRF5340_xxAA_APP`).
- **Tank level events = DT61, renumbered to 100-104:** `TANK_LEVEL_HIGH_HIGH=100, HIGH=101,
  NORMAL=102, LOW=103, LOW_LOW=104`. **DT113 IS real** (a prior "no DT113" note was wrong — reversed
  after live RTT 2026-07-07: `vx_app: DT113` for threshold events + `vx_app: DATA_TYPE_61` for
  check-in both appear). Cloud also derives level/percent from `analogInputNcurrent` in a
  ThingsBoard Handler script node and exposes decoded `tankNumber`/`thresholdLevelType`/value.
- Settings pushed from cloud as **DT71** hex-TLV frames; thresholds are float32; Tank combines 4 ports
  into one ~81-byte string. The `0F` "save-not-send" byte position **differs between fw v2.0.4 and
  v2.0.5** — pin the exact version when decoding.
- Analog inputs measured in **microamps**. Firmware compile-default thresholds (uA): HH 10000 / H 9000
  / L 8000 / LL 7000; relay on 5000 / off 10000. **These are overridden by cloud settings (below).**
- **Testbench self-test** (`***IO BOARD TEST STARTED/ENDED***`, RTT) only exists in a **WITH_TESTBENCH**
  build. The v2.0.x RELEASE hex is the final app -> those brackets will NOT appear (verify power/analog
  cloud-side instead).

---

## 4. Cloud facts (ThingsBoard / VX Olympus)

- **Portal:** `https://portal.dev.vxolympus.com` (DEV). Tenant "United Rentals Customer". Login is a
  **tenant admin** account. Credentials live in `secrets/station.env` (gitignored) — NOT in this doc.
- **CLOUD-WRITE AUTHORIZATION (2026-07-07, granted by tenant admin / the engineer):** changing DEVICE
  SETTINGS via the portal is **AUTHORIZED for the QA test device `104D1526064B6130` ONLY**, and only for
  testing (thresholds, output/siren mapping, siren mode, check-in cadence — Tests 4/5, Siren 6-8). All
  OTHER data and **every other device remain strictly READ-ONLY** — never write/downlink to another
  customer device. After any settings change, **verify the device actually applied it** (RTT `Prof/Out/
  Siren chnl` lines + cloud "Settings Received From Device" advancing) — cloud#538/#534 mean a downlink
  can silently fail. Prefer the portal UI or a *verified* settings-writer; do NOT blind-push a
  hand-encoded DT71 blob (the `0F` save-not-send byte + float32 layout are fw-version-fragile).
- **Device under test:** name/VDUI **`104D1526064B6130`**, TB UUID
  **`022297c0-5d7e-11f1-8c71-25a5120ce367`**. IMEI 864395064041840, SIM 89883070000058075969.
- **Verified working:** `python tests/cloud-checkin/check_checkin.py --device-id 022297c0-5d7e-11f1-8c71-25a5120ce367`.
- **The device reports full IO state to cloud** (so S2/S3/S4/S5 are verifiable cloud-side, no RTT):
  - `analogInput1..4current` (uA), `digitalOutput1..4` (relays 0/1), `digitalInput1..4`
  - `mainPower / powerSupplyPower / powerSupplyAc / powerSupplyBattery / extBattDc`
  - `io_board_app_tank_monitor_appLogic` (e.g. `['HEARTBEAT']`; tank level events show here)
  - `payloadHex`, `pins`, `channelsNo`, GPS, `cellRssi/cellBer`
- **REAL configured thresholds (from cloud, all channels):** **HH=18000 / H=16000 / L=14000 /
  LL=12000 uA**; `outputThresholdsCh1Off=13000`. S3/S4 sweeps must target THESE bands (12-18 mA), not
  the compile defaults. Read them live before a run in case they changed.
- **State (2026-07-07):** device was OFFLINE ~23 h (last check-in 7/6 ~11:59) — likely fw#311 (supercap
  -> MQTT reconnect). A reflash fixes it. Cellular is connected on the bench per the engineer.

---

## 5. Flash recipe (the exact sequence)

Reverse-engineered from `vendor/vx_programmer/devices/jlink/IOBoard.py`; re-implemented headlessly in
`tests/tank-monitor/flash_board.py` (mirrors Siffron `program_board.py`). ONE pylink session, probe
pinned:

```
nrfjprog --recover (unlock APPROTECT)  ->  preflight
open(serial_no=822006519) -> connect nRF5340_xxAA_APP
[optional: TRIGGER_FLEET_PROV over RTT ch2 on running fw] -> reset
erase (full)
memory_write32(0x000FC000, [magic, uuid_msb, uuid_lsb, magic, key3, key2, key1, key0, eui_msb, eui_lsb])
memory_write32(0x00FF8000, 0x50FA50FA)   # UICR.APPROTECT       (keep debug/RTT open)
memory_write32(0x00FF801C, 0x50FA50FA)   # UICR.SECUREAPPROTECT
flash_file(merged.hex, 0x0)              # J-Link flashloader, NOT nrfjprog --chiperase
flash_file(factory_data.hex, 0x0)
reset (core) + close
```

- magic = **0xA55A5AA5** (written raw). UUID/AppKey/AppEUI words are byte-swapped (little-endian).
  Our `build_key_words()` was cross-checked byte-for-byte against the vendor IOBoard arithmetic.
- **Writing APPROTECT is what keeps RTT open** across resets; skipping it leaves the board RTT-locked.
- Flash via `flash_file`, NOT `nrfjprog --chiperase` (chiperase risks a LOCKUP hard-fault).
- Certs/provisioning live in **external SPI flash** and survive the internal-flash erase, so a plain
  reflash usually restores connectivity WITHOUT re-provisioning (fleet-prov optional).

---

## 6. Device identity / keys  (values NOT inlined — this doc is shareable)

The flasher writes a settings block at 0xFC000 built from the device's DevEUI/AppEUI/AppKey. Those
values are **secrets** and are deliberately kept out of this file:

- They live in `tests/tank-monitor/config.py` (`DEVICE_UUID`, `DEVICE_APP_EUI`, `DEVICE_APP_KEY`),
  overridable via the same-named environment variables.
- The DevEUI == the device VDUI == the ThingsBoard device name (`104D1526064B6130`) — that identifier
  is used throughout; the **AppEUI and AppKey are secret** and must not be shared/committed publicly.
- ThingsBoard portal credentials are in `secrets/station.env` (gitignored), never in a doc.

To flash a different device, set the three `DEVICE_*` env vars (or edit `config.py`) — do not paste
keys into shared chats/docs.

---

## 7. The QA tooling built (how to run each)

All under `tests/tank-monitor/` unless noted. Deps: `pip install -r tests/tank-monitor/requirements.txt`
(pymodbus, pyserial) plus the bench base (pylink, nrfjprog, requests, python-dotenv).

| Tool | Command | Purpose |
|---|---|---|
| **Flasher** | `python flash_board.py --verify-live` | READ-ONLY: read 0xFC000, compare to computed keys, prove probe + identity + MCU alive |
| | `python flash_board.py --dry-run` | compute/print keys, no hardware |
| | `python flash_board.py` | full flash: recover+preflight+erase+keys+APPROTECT+merged+factory+reset |
| **Runner** | `python run.py boot --no-flash` | S1 boot/identity over RTT |
| | `python run.py all` | S1..S5 (flashes once via flash_board, then runs) |
| | `python run.py thresholds` / `relay` / `siren` | S3 / S4 / S5 (auto-injects if `WAVESHARE_PORT` set) |
| **Injector** | (driven by run.py) | `waveshare.py` — Waveshare Modbus RTU Analog Output 8CH, 4-20 mA, set `WAVESHARE_PORT` |
| **Cloud** | `python tests/cloud-checkin/check_checkin.py --device-id <UUID>` | read-only TB telemetry freshness + dump |
| **Dashboard** | `python dashboard/build.py` -> open `dashboard/index.html` | S1-S5 results view over `results/` |
| **Parser tests** | `python test_parse.py` | 18/18 offline (no hardware) |

Config is centralized in `tests/tank-monitor/config.py`: image paths (v2.0.4 dev), keys, thresholds
(compile + cloud-configured), `JLINK_SERIAL=822006519`, `JLINK_DEVICE=nRF5340_xxAA_APP`, TB device id,
Waveshare + AI->AO map, TB telemetry key names.

---

## 8. Test plan S1-S5 (RTT vs cloud)

| Scope | What | On-bench (RTT) | Cloud (ThingsBoard) |
|---|---|---|---|
| S1 Boot/identity | app_type, version, APP Init | YES (release hex logs boot) | current_fw_version |
| S2 IO/power self-test | ext-mem, power rails, analog, RS232/485 | only with WITH_TESTBENCH build | power/analog telemetry keys |
| S3 Threshold events | inject 4-20 mA -> level band | relay transitions + AN current | analogInputNcurrent + appLogic DT61 (100-104) |
| S4 Relay hysteresis | ON/OFF crossing | `Channel: n, state transition` | digitalOutputN |
| S5 Siren/light | siren on/off | DBG-only (multimeter) | appLogic + power/output |

Cloud-side is often the better verifier (real production firmware, full path). RTT is the on-bench
cross-check. Cross-check both — cloud silence != healthy (fw#226: CRC failures aren't reported).

---

## 9. Current bench state (2026-07-07)

- **PSU:** GPD-3303S, CH2 = ~12.0 V, board drawing ~69 mA (alive). Both channels set to 12 V/1.5 A.
- **INCIDENT:** the board briefly saw **24 V** (~1-2 min): output-enable is global, CH1 was set to 12 V
  but CH2 (the board) was still 24 V when output was enabled. Fixed; board draws current at 12 V, but
  its health after the overvoltage should be confirmed (`--verify-live` + a boot/cloud check).
- **J-Link:** free (vx_programmer GUI closed). Probe 822006519 = DUT.
- **Not yet done:** `--verify-live`, the actual flash, S1 RTT, cloud re-verify after it comes online.

---

## 10. Known bugs / risks (from issues; repo#num)

- **fw#311 (OPEN)** supercap -> "mqtt connect failed": after power loss + supercap, board often can't
  reconnect to AWS without a reflash/SIM swap. Likely why the DUT went offline.
- **cloud#536 (OPEN)** out-of-range (<4 / >20 mA) 4-20 mA handling unverified.
- **cloud#538/#534 (OPEN)** dashboard->IO-board downlinks broken (fw version-string format + missing
  `powered=true`) — commands may silently not reach the device; verify comms via RTT, not just cloud.
- **fw#315 (OPEN)** default comm mode (cell/LoRa) at assembly undecided.
- **v2.0.0 changed MCUboot keys** -> no OTA from pre-2.0; 1.x units must be re-flashed by wire.
- Bring-up faults that silently kill comms: SIM-holder solder short, SX1262 antenna switch unsoldered.

---

## 11. Operational gotchas

- **cp1252 console** — keep all console/log output ASCII-only (unicode arrows/checks crash a run).
- **Pin the J-Link serial** for every probe op (3 probes on this bench).
- **PSU output-enable is global** + board on CH2 (see incident) — set/verify the connected channel first.
- **RTT stays open only if APPROTECT is written** during flash.
- Never run two J-Link operations at once; close the vx_programmer GUI / RTT Viewer before driving the
  probe; a wedged probe needs a USB replug.
- Cloud access is a live customer tenant — **read-only**, EXCEPT settings changes are authorized on the
  **QA test device `104D1526064B6130` only** (see section 4). Never write to any other device; verify
  every settings change device-side.

---

## 12. Open questions / next steps

**Next actions (in order):** (1) `flash_board.py --verify-live` (read-only, confirms 24 V survival +
probe + identity) -> (2) `flash_board.py` (flash v2.0.4 dev) -> (3) `run.py boot --no-flash` (S1 RTT)
-> (4) poll cloud for the device coming back online -> (5) Waveshare injection + cloud/RTT S3/S4/S5.

**Open questions:** exact AWS hex->JSON key/enum names (parser external to repo); is fw#311 root-caused
or just characterized; is the cloud downlink-routing fix (cloud#538) live; exact `0F` byte offset per
fw version; board health after the 24 V exposure.
