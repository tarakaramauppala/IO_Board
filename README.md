# VX-0057 IO-Board QA Station

Hardware-in-the-loop **+ cloud** QA automation for the **Viaanix VX-0057 tank monitor** (nRF5340).
A one-click, web-driven **program-and-test station**: flash → self-test → reprogram → run the full
behavioral battery, grading every result against **both** the device's RTT log **and** the cloud.

> One board at a time or a multi-board batch. Bench instruments are auto-driven; results are per-board
> component lamps with a raw capture saved for audit.

---

## The pipeline

| Stage | What it does |
|-------|--------------|
| **A · Hardware self-test** | Flashes the **vendor testbench firmware** (identity-agnostic — a dummy VDUI) and grades the board's built-in self-test over RTT: flash memory, 12 V rails, digital in, analog in, RS-232/485, LoRa/cell, and board **current** (via the DMM). Optional **A + AC Power** step drives the DC→AC switch (PSC-60) with the PSU toggled in sync. |
| **B · Reprogram** | Flashes the **production tank-monitor firmware** and writes the **real per-device VDUI + LoRaWAN keys** into the settings block. |
| **C · Functional** | The behavioral battery, hands-off: auto **4–20 mA injection** (Waveshare Modbus AO), **DT71 settings-writer** over the cloud, and **siren-voltage** auto-read (GDM-8251A). **Quick** = go/no-go (level + relay on one channel, ~2–3 min); **Full** = T1–T5 + S6–S8 across all 4 channels. |

**Functional tests:** `T1` level thresholds · `T2` normal · `T3` relay ON>OFF · `T4` relay ON<OFF ·
`T5` disabled output · `S6`–`S8` siren mode / per-channel disable. Grading favors the firmware's own
band + DT113 event, corroborated by the injected sample and the cloud telemetry.

---

## Quick start (any bench machine)

1. **Configure the bench** — copy the example env and fill it in:
   ```
   copy secrets\station.env.example secrets\station.env
   ```
   Set your COM ports, the device VDUI + LoRaWAN keys, and the cloud credentials (see below).
2. **Run the preflight wizard** (auto-installs Python deps; checks the probe / instruments / firmware / cloud):
   ```
   python tests\tank-monitor\setup_check.py
   ```
3. **Start the station** and open the dashboard:
   ```
   python tests\tank-monitor\station.py 8792     ->  http://127.0.0.1:8792
   ```

Or just double-click **`Start-IOBoard-QA.bat`** — it runs the preflight, then launches the station.

---

## Bench setup

| Instrument | Interface | Role |
|------------|-----------|------|
| **SEGGER J-Link** | SWD + RTT (`pylink`) | flash + read the device log |
| **GW-Instek GPD-3303S** PSU | serial | 12 V board power (software-clamped) |
| **GW-Instek GDM-8251A** DMM | serial | board current (in series) / siren-output voltage (across ALARM) |
| **Waveshare Modbus RTU Analog Output 8CH** | RS-485 | 0–20 mA current injection into the analog inputs |

**Wiring for functional tests:** `AO1→AI1, AO2→AI2, AO3→AI3, AO4→AI4` (shared GND); meter **across the
siren ALARM output** (DC-volts) for the siren steps; PSU **12 V direct** to the board. For the Stage A
current check the meter goes **in series** with the +12 V feed. The dashboard shows a wiring pre-flight
popup before each functional run.

> ⚠️ **12 V only** into the board (24 V damages it). The GPD-3303S output-enable is global — both
> channels are verified ≤ 12 V before enabling. AC mains (PSC-60 test) is a shock hazard: only via the
> proper PSC-60 / DPDT / IEC harness, never onto the 12 V terminal.

---

## Configuration — `secrets/station.env` (gitignored)

```ini
# Cloud (ThingsBoard / VX Olympus) — read-only verification
VX_TB_BASE_URL=https://your-portal
VX_TB_USERNAME=readonly-user@example.com
VX_TB_PASSWORD=

# Device under test — identity + LoRaWAN keys (written to the 0xFC000 settings block on flash)
DEVICE_UUID=FFFF0000FFFF0000
DEVICE_APP_EUI=0000000000000000
DEVICE_APP_KEY=00000000000000000000000000000000
TB_DEVICE_ID=

# Bench instrument COM ports on this machine (blank = instrument absent)
PSU_PORT=
METER_PORT=
METER_BAUD=115200
WAVESHARE_PORT=
```

No credentials live in tracked files — `config.py` loads them from `station.env` and falls back to
safe placeholders.

---

## Layout

```
tests/tank-monitor/    station.py (dashboard) · functest.py · tankmon.py · settings.py (DT71)
                       thresholds.py · psu.py · meter.py · waveshare.py · flash_board.py
                       config.py · setup_check.py (preflight wizard) · test_*.py
tests/cloud-checkin/   tb_client.py + cloud telemetry verification
docs/                  hardware / firmware / software understanding
secrets/               *.example only (real station.env is gitignored)
results/               run summaries (raw captures gitignored)
Start-IOBoard-QA.bat   one-click: preflight -> station
```

---

## Notes

- **Firmware is not in this repo** — provide the vendor testbench + production `.hex` locally (paths in
  `config.py`, overridable by env). `*.hex` and the vendor programmer are gitignored.
- **Cloud writes** are limited to DT71 settings on the authorized test device; everything else is read-only.
- Requires **Python ≥ 3.10** and the SEGGER J-Link software; the wizard installs the pip deps
  (`pyserial`, `pylink-square`, `pymodbus`, `openpyxl`, `requests`, `python-dotenv`).
