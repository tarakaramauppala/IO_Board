---
name: bench-power-and-observe
description: How to power and observe the VX-0057 DUT on this bench (12V at J36, J-Link SWD/RTT, no serial/PPK2)
metadata:
  type: project
---

On this bench (`project.yaml` bench: `jlink:true, ppk2:false, serial:false`):

- **Power the DUT from 12 V DC into the external 12 V battery input J36** (fused 2.5 A,
  Adam 2604-3102). The board accepts 5-32 V, but the main 12 V buck-boost won't start
  below ~8 V, so use ~12-13.8 V. **Never energize the AC mains inputs (J22/J29/PSC-60A-C
  path) on the bench.**
- **Flash/attach via J-Link** over SWD — either the populated SWD header or the
  Tag-Connect pads (signals SWDIO/SWCLK/NRST). The nRF5340 is **dual-core**: program both
  the application and network-core images.
- **Observe via RTT** (J-Link). There is **no UART debug console wired** — all three MCU
  UARTs are committed to peripherals (UART0=cellular, UART1=RS-485, UART2=RS-232). With
  `serial:false`, RTT is the primary log path for `/run-test`.
- **No current/power measurement** is possible here (no PPK2); per-mode current envelopes
  are unmeasurable until a PPK2 is added.

Full hardware reference: `docs/hardware/main-board.md`. See also [[nrf5340-nfc-relay-pins]].
