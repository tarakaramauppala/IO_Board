---
name: nrf5340-nfc-relay-pins
description: VX-0057 relays K3/K4 sit on nRF5340 NFC pins — firmware must set UICR.NFCPINS=GPIO or they won't switch
metadata:
  type: reference
---

On the VX-0057, **relay triggers K3_TRIG and K4_TRIG are wired to nRF5340 P0.02/NFC1 and
P0.03/NFC2** — the SoC's NFC antenna pins, which are NFC-function by default.

**Implication:** firmware must configure these as normal GPIO via **`UICR.NFCPINS = GPIO`**.
Otherwise **relays 3 and 4 will not actuate**. K1/K2 are on ordinary GPIO and are unaffected.

**Firmware status (confirmed in vx_ioboard_fw v2.0.4):** `CONFIG_NFCT_PINS_AS_GPIOS=y` **is set**
(`prj.conf:146`) — so the intent is handled. BUT UICR is OTP-style: this only takes effect when
the UICR is actually written, i.e. on a **full chip-erase + program**. A device flashed
incrementally (or whose UICR was left as NFC) keeps NFC behaviour and **K3/K4 won't switch**.
→ **Test gate: always flash test images with a chip erase, then confirm K3/K4 toggle.** The exact
pin↔relay mapping lives in the out-of-tree `zephyr_boards` board repo, not in vx_ioboard_fw.

Source: VX-0057 Rev B schematic (MCU sheet) + vx_ioboard_fw `prj.conf`. See
`docs/hardware/main-board.md` §10 and `docs/firmware/vx_ioboard_fw-common.md` §9-10.
Related: [[bench-power-and-observe]], [[firmware-build-and-observe]].
