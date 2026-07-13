# Tank Monitor QA — "What This Project Is" Briefing

*Citation shorthand:* `fw#` = **Viaanix/vx_ioboard_fw** (firmware), `cloud#` = **Viaanix/715-unitedRentals-Cloud** (ThingsBoard tenant config), `hw#` = **Viaanix/VX-0057** (Altium hardware). Cross-repo links appear where the issues themselves link (e.g. `hw#23 → fw#184`).

---

## 1. What the project is

The product is the **Viaanix Tank Monitor**, a mains/battery-powered industrial **RTU / IO board** (hardware **VX-0057**, rev a and rev b) built around a **Nordic nRF5340** on a **Minew module** (`hw#33`, `hw#23`). It reads tank sensors (**4-20 mA current loops, an analog input, and optocoupler digital inputs**), drives a **relay bank + a 12 V siren/beacon light**, and reports over **two radios** — a **cellular LTE modem** and **LoRaWAN (SX1262, class C)** — with a **supercapacitor "last-gasp" circuit** that lets it send a final NO POWER event on AC loss (`hw#2`, `hw#18/#29`).

One firmware image implements **four selectable "personalities"** plus test builds — **Tank Monitor, RTU, Call Box, Turnstile**, and IO-signal-test / FCC-test — sharing a common IO/event/settings framework chosen at build time (`fw#88/#105/#56/#252`). Turnstile (RS485 keypad access control) is the newest (`fw#252`).

**The three repos fit together as EE → firmware → cloud:**

| Repo | Role | Not |
|---|---|---|
| **VX-0057** (`hw#`) | Altium schematics/PCB/BOM/variants for the board. Sensor front-ends, relays, siren, dual-radio, supercap power tree. | Contains **no firmware**; explicitly points firmware questions to `vx_ioboard_fw` (`hw#23 → fw#184`). |
| **vx_ioboard_fw** (`fw#`) | Zephyr / nRF Connect SDK **2.7.0** firmware; the four personalities, comms, provisioning, OTA, offline buffering, testbench self-test. | — |
| **715-unitedRentals-Cloud** (`cloud#`) | **Cloud/tenant config** for the "715 - United Rentals" tenant on **VX Olympus** (ThingsBoard-based). Rule chains, dashboards, **payload decoders, settings-hex construction, threshold/4-20 mA conversions**, and the QA/acceptance log. | **Not a firmware repo.** Also tracks the **SmartProBox (SPB / VX-0056 lockbox)** — a *different product on the same tenant*; don't confuse SPB issues with Tank Monitor. Low-level decoders actually live in a **separate "sensor data decoders" repo / ChirpStack** (`cloud#517/#518`). |

---

## 2. Architecture & data flow

**Device compute:** nRF5340 **dual-core**. App core builds as `vx_0057_b_cpuapp_no_tfm` (**no TF-M / non-secure split**) per `fw#301`; the **net core runs the radio**. External **QSPI flash on P0.13–P0.18** (IO0-3/SCK/CSN) after the pin remap in `hw#23` — which consumed **all remaining GPIO** (zero free pins unless the crystal-less Minew variant is ordered).

**Two uplinks:**
- **Cellular LTE** (Quectel modem + SIM) → **AWS IoT + ThingsBoard over MQTT** (`fw#97` context, `fw#236`).
- **LoRaWAN SX1262 class C** → gateway → **ChirpStack → sensor-data-decoders** → ThingsBoard (`cloud#517/#518`).
- **Automatic mode switching** via `SET_COMM_MODE` with SPB2-style hysteresis/quality factor (`fw#290`); **default mode at ship is still undecided** (`fw#315`, OPEN).

**Cloud topic contract:** `vx_upload/{env}/{account}/…/{client}/io_board_app_{apptype}/{serial}` — e.g. `vx_upload/dev/2012/100/Humboldt/io_board_app_rtu/104D152603DC8142` (`fw#325`). The app-logic key is `io_board_app_<rtu|tank|call_box|turnstile>`.

**Offline buffering:** on connectivity loss the board writes to **external SPI flash** — redesigned from a single `/lfs/NotSent.txt` to indexed `/lfs/cell/not_sent_X.txt` files with read/write indices (`fw#300`), gated by a per-app "external memory save" setting (`fw#301`) after a reconnect flooded **~1200 queued retransmissions** (`fw#298`).

**Power path:** on AC loss, supercaps hold 3.3 V for **~8 s**, giving firmware time to transmit a NO POWER / power-down event over **cellular** (`hw#18/#26/#29`; cloud side `cloud#476/#453`, `fw#189`).

**Provisioning:** fleet provisioning **by claim** — claim certs baked in, device requests unique per-device certs over MQTT and stores them in external flash; **dev vs prod endpoint is chosen by the programmed `vx_factory` image** (`fw#231/#276/#312`). Cloud "claim" (renamed **"Receive"**, `cloud#280`) creates the asset, relates device↔asset↔UR user, and stamps default config (`cloud#335`).

---

## 3. Active workstreams

- **Multi-client factory data / provisioning** — per-client AWS/ThingsBoard endpoints, certs, and client-scoped topics (Humboldt) (`fw#325`, OPEN); **dev/prod topic unification** unresolved (`fw#329/#321`, OPEN).
- **Comm-mode auto-switching + default selection** (`fw#290`; `fw#315` OPEN).
- **Offline-buffering redesign** (`fw#300/#301`, closing out `fw#298`).
- **OTA / MCUboot** signing — v2.0.0 release work (`fw#216/#225/#237/#299`).
- **Testbench / HIL self-test** of ADC 4-20 mA, RS232/RS485, relays, LoRaWAN join (`fw#154/#209/#232/#286/#292`); **automated Tank & RTU test scripts still OPEN** (`fw#327/#328`).
- **Cloud settings-payload correctness & downlink routing** — threshold conversions, siren/relay config, and fixing dashboard→IO-board command delivery (`cloud#534`; `cloud#538/#536` OPEN).
- **Asset lifecycle hygiene** — off-rent relation cleanup, married/divorce (`cloud#497/#543/#317`).
- **Hardware close-out** — equivalent-fuse sourcing (`hw#37` OPEN) and **FCC/regulatory paperwork** (`hw#21/#22` OPEN).

---

## 4. Known bugs & risks

**Highest-impact OPEN:**
- **`fw#311` (OPEN) — supercap "mqtt connect failed":** after running off the supercap during power loss and re-powering, the board frequently **fails to reconnect to AWS MQTT without a reflash or SIM swap**. Workaround: repeatedly press power to fully discharge before re-powering. **Primary field-reliability risk.**
- **`cloud#536` (OPEN) — out-of-range 4-20 mA handling** unverified in `io_board_app_tank_monitor Handler`; out-of-range currents can yield bad level/percent conversions. **Directly in Tank QA scope.**
- **`cloud#538` + `cloud#534` (OPEN) — downlink routing broken:** `GEN_SEND_DOWNLINK_MSG` parses firmware version as `715.4.0` but IO boards report `v2.0.4 hash: …`, and IO boards lack the `powered=true` attribute — so **dashboard/immediate commands can silently fail to reach Tank Monitors**. Gates any LoRaWAN command test.
- **`fw#315` (OPEN) — default comm mode after assembly undecided;** boards may ship in the wrong mode.
- **`fw#226` (OPEN) — firmware does not notify ThingsBoard on CRC failure;** silent corruption goes unreported (⇒ cloud silence ≠ healthy device).
- **`fw#305` (OPEN) — no consolidated version history** for data types / events / commands / settings; payload decoding is error-prone.
- **`hw#37/#21/#22` (OPEN)** — no qualified equivalent **fuse**; **FCC paperwork** incomplete (shipment-gating).

**Notable CLOSED (recurring failure modes to regression-test):**
- **`cloud#476/#453` — MAIN_POWER_OFF last-gasp is power-marginal:** a single 5.5 V/1 F (or high-ESR) supercap can't power cellular TX long enough; **dual ~1 F needed**. Under-spec field units silently miss power-loss alerts.
- **`cloud#490` — stale settings:** per-tank string was built from the device-echoed `sharedSettings`, so a rejected/delayed downlink leaves stale settings for other tanks; the `0F` "save-not-send" byte **position differs between fw v2.0.4 and v2.0.5** — a version mismatch corrupts the ~81-byte payload.
- **`cloud#505/#367` — stale siren trigger bytes** retained (e.g. `0AFF01` instead of `0A0001`) when config moves away from digital triggers.
- **`cloud#408/#316` — threshold conversion errors** when current > 20 mA or user enters out-of-range values (now range-validated).
- **`fw#309` — LoRaWAN length-wrap:** stale `lorawan_data_packet` buffer after a port-5 probe shipped truncated/zero-padded uplinks.
- **`hw#19` — PSC-60 supply has reverse-polarity protection by fuse only;** a backwards battery permanently blows the internal 5 A fuse and bricks the supply.
- **`hw#11` — crystal + external flash interaction** flagged during bring-up; confirm resolved on Rev B before relying on QSPI.

**Compatibility / production landmines:**
- **v2.0.0 changed MCUboot signing keys** ⇒ **OTA from any pre-2.0.0 build is impossible;** field 1.x units must be **re-flashed by wire** (`fw` CHANGELOG, `fw#276`).
- Bring-up hardware faults that **silently kill connectivity:** SIM-holder pins shorted by solder paste (`fw#276`), SX1262 antenna switch left unsoldered + wrong spi3 DTS mapping (`fw#97`).
- **NO POWER hold-up fix began as hand rework** (trace cuts, added Schottky diodes, 1 F cap across pads, MOSFET gate resistor) — verify it's **integrated into Rev B fab, not bodged on samples** (`hw#18/#29`). Must use a **single 1 F FG0H105ZF/FT0H105ZF, not parallel gold caps** (excessive ripple) (`hw#29/#26`).

**Security note (be precise):** the provided summaries surface **no committed-secret / leaked-key / secret-scan issue** in any of the three repos — do **not** assume one exists. What *is* documented is that **MCUboot signing keys changed at v2.0.0** and that **fleet-provisioning claim certs are stored in external flash** (`fw#231`). **Readback/`APPROTECT` protection is not discussed in any issue in any repo** and must be confirmed separately (see §6). SPB (same tenant) has a safety-class access bug — **`cloud#542` (OPEN), random unlock on rapid RFID swipes** — but that is the lockbox, **not** the Tank Monitor.

---

## 5. Tank Monitor QA implications

**Thresholds & settings model (`src/app/vx_app_tank.h`):** `profile_channels` with `high_high / high / low / low_low` thresholds **in microamps**, output on/off thresholds (µA), siren on/off thresholds (µA), and a `siren_mode` byte, pushed from cloud via **DT71 settings frames** (`fw#42/#54/#301`). RTU/Tank moved from separate ON/OFF thresholds to a **single analog threshold** (`fw#163/#174/#234`).

**4-20 mA:** analog inputs are current loops **measured in microamps** (logs show e.g. `AN_1: 89 uA, State: UNDER_MIN_THRESHOLD`). Cloud conversion lives in the **`io_board_app_tank_monitor Handler` / `io_board_app_call_box Handler` "conversions" script nodes**. Edge cases: **> 20 mA** was a bug (`cloud#316`), out-of-configured-range entries were a bug (`cloud#408`), and **out-of-range handling is still OPEN** (`cloud#536`).

**⚠️ Tank-level events — DT61, NOT DT113 (correct the task's schema):** In **both** the firmware and cloud repos, **there is NO DT113 anywhere.** Tank level events live in **DT61**, renumbered to start at 100: `TANK_LEVEL_HIGH_HIGH=100, HIGH=101, NORMAL=102, LOW=103, LOW_LOW=104` (`fw#318`). Separately, the cloud repo uses **DT61 = AC_POWER_OFF** and **DT90 = PSC_60_AC (AC_OK)** for the backup-power alarm contract (`cloud#288`), and tank level/percent actually flows through the **analog-conversion script nodes**, not a dedicated tank-level DT event. Treat any "DT61/DT113 tank level" phrasing in the task as incorrect.

**Siren / relay / pump:** a large bug cluster — device stuck with siren on (`fw#136`), `ON=0/OFF=0` wrongly disabling siren+output (`fw#281`), output3 won't turn off at thresholds=0 (`fw#227`), siren-mode edge cases (`fw#240/#246`), siren relay activate/off events (`fw#159/#120`), toggle/trigger logic (`fw#192/#196`). Call Box has **4 relays**; `SIREN RELAY ACTIVATE` takes **0 (disable/none) or 0xFF (all outputs)** (`cloud#277`). Cloud form labels: Siren Threshold → "Siren/Light Function (Percentage Full)" (`cloud#286`); Output Thresholds → "Pump Control if Applicable (Percentage Full)", default 0/0 (`cloud#285`).

**Settings payload format:** a **hex TLV string** (prefix `4753…`/`4731…`), one tag+value block per port/setting index (`02..0E`, plus new `0F`). Tank Monitor **combines all 4 tank ports into one ~81-byte string**; thresholds are **float32** (`409CE0AB` → 40000/44000). Per-app `EXT_MEM_SAVE` setting-byte offsets: **RTU 0x0C / Tank 0x0F / CallBox 0x08 / Turnstile 0x04** (`fw#301`); the `0F` byte **position differs v2.0.4 vs v2.0.5** (`cloud#490`). Construction bugs live in `Construct ioboard settings payload`, `Tank Asset Handler`, `Downlink Queue Handler (Settings)` (`cloud#490/#505/#408/#367`). A digital-input High/Low index swap bug was also fixed (`cloud#384`).

**Provisioning / fleet-prov:** claim ("Receive") pulls unique certs into external flash; **re-runs only via vx_programmer "Restart Fleet Provisioning."** Dev vs prod is chosen by the programmed `vx_factory` image (`fw#231/#276/#312`; `cloud#335/#280`). Test fleet: 18 tank-monitor VDUIs (`104D1526…`) + SIM fleet (`89883070…`) in `cloud#528`.

**APPROTECT / readback:** **not discussed in any issue in any of the three repos.** The firmware repo explicitly flags it as unconfirmed — must verify separately before/after flashing.

**Testbench self-test (authoritative bench procedure in `cloud#528`, from dcampbell):**
- AC Power Test (DC off, PSC-60 AC-OK); DC Power Test with short-circuit check limited to **0.5 A @ 12 V**; Flash Memory.
- Digital In 0-4 driven by Light & Buzzer outputs through relays 1 & 2 (a failing input pattern localizes the fault).
- **Analog In 1-4 = 4-20 mA: In1&3 expect 16 mA @ 24 V (verifies 24 V rail); In2&4 expect 8 mA @ 12 V (verifies 12 V rail); Analog In 5 = 5 V rail.**
- **RS232 and RS485 loopback (RS485 needs full-duplex config, `hw#35`).** LoRa comm-chip test, Cell Serial, Cell SIM.
- **The bench ONLY checks connections and does NOT flash the final app firmware.** **LoRa Join is verified only when flashing the FINAL app firmware, not on the bench; LoRa RSSI is skipped.**
- Firmware-side pass criteria: analog channels read **5000 mV** (`testbench: AN5: OK`), RS232↔RS485 half-duplex echo (`fw#232/#209`); the watchdog reset during the LoRaWAN-join testbench was fixed (`fw#292`). **Automated Tank/RTU scripts remain OPEN (`fw#327/#328`).**

**What changes how we flash / verify (RTT vs cloud):**
1. **Two-stage programming:** bench connection-test firmware ≠ final app. You **must flash the final app image** to exercise LoRa Join and real tank/siren logic (`cloud#528`). Grade Join only after final-app flash.
2. **Bench PSU:** inrush/testbench current peaks **~1.37 A** → set the **PSU limit to 1.5 A** (`hw#26`). Supercaps cause a **30-40 s delayed cold start** before data flows — **do not grade startup too early** (`hw#26`, and consistent with the supercap cold-rejoin behavior noted in project memory).
3. **Cloud command delivery is currently unreliable to IO boards** (`cloud#534/#538` — version-string format + missing `powered=true`). Until `cloud#538` is resolved, **verify downlinks/commands via RTT/serial rather than trusting the dashboard**, and confirm the LoRa path explicitly.
4. **Cloud silence ≠ healthy:** CRC failures aren't reported to ThingsBoard (`fw#226`), so **cross-check RTT/serial telemetry against cloud**, not cloud alone.
5. **No canonical DT/settings map exists** (`fw#305`) — decode payloads against `fw#318` (events start at 100) and the `fw#301` offsets, and pin the **exact firmware version** since the `0F` byte moves between v2.0.4/v2.0.5 (`cloud#490`).
6. **v2.0.0 key break:** any 1.x field/bench unit must be **re-flashed by wire**, not OTA.

---

## 6. Open questions the issues did NOT answer

- **APPROTECT / readback protection state** — **not discussed in any repo.** Is the nRF5340 shipped locked? What does chiperase/recover require on VX-0057? Must confirm before building a flash step. *(Relevant given prior UICR/chiperase pain on the sibling VX-0056 project — see project memory — but that lesson is not documented for VX-0057.)*
- **Is `fw#311` (supercap → MQTT reconnect) root-caused or just characterized?** It remains OPEN with only a manual discharge workaround; no fix is recorded.
- **Default comm mode at assembly** (`fw#315`) — unresolved; we don't know what mode boards will actually ship in.
- **Is the LoRa downlink routing fix live?** `cloud#538` is OPEN — does a dashboard command reach a Tank Monitor over LoRa yet, and is the version-string/`powered=true` mismatch fixed?
- **Final out-of-range 4-20 mA behavior** (`cloud#536`, OPEN) — what should the device/cloud do below 4 mA or above 20 mA (clamp? error event? which DT?) is unspecified.
- **Exact `0F` "save-not-send" byte offset per firmware version** — the summaries say it *differs* between v2.0.4 and v2.0.5 but don't give both offsets; need the concrete layout for whichever version we test.
- **Are the NO-POWER hold-up reworks integrated into the Rev B fab** (`hw#18/#29`) vs bodged on samples, and is **crystal + external flash** (`hw#11`) confirmed resolved on Rev B?
- **Automated Tank/RTU regression coverage** (`fw#327/#328`, plus RS232 `fw#288`) — unfinished; no existing script to build QA automation on top of.
- **Secret hygiene** — no committed-key/secret-scan issue appears in these summaries, but whether MCUboot signing keys or claim certs live in any repo is **not stated**; confirm out-of-band.