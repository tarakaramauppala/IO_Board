---
name: test-scope-decisions
description: Engineer-agreed test scope for VX-0057 (cloud via RTT→Tailscale→ThingsBoard, radio prereqs present, sleep deferred, IO rig TBD)
metadata:
  type: project
---

Scope decisions from `/define-use-cases` (2026-06-12), to carry into `/build-test-plan` and
`/build-dashboard`:

- **Cloud check-in:** verify via **RTT** for now (`CELL PUBLISH SUCCESS`, `Lorawan join SUCCESS`,
  `cell: registered to network`). Plan is to **forward check-in data over Tailscale to the
  ThingsBoard platform** for cloud-side viewing (built in `/build-dashboard`). Full cloud-side
  assertion is blocked on `/understand-software` resolving the AWS↔ThingsBoard flow. See
  [[cloud-telemetry-path]].
- **Radio prerequisites are available** on the bench: activated SIM + cellular antenna, LoRaWAN
  gateway/US915 coverage, RF antennas fitted → cellular registration/publish and LoRaWAN OTAA join
  are genuinely testable (C3, C4).
- **First-round scopes:** boot + IO/power self-test (RTT), field-IO functional, radio connectivity.
- **Sleep current: DEFERRED** — no PPK2 on this bench and firmware doesn't autonomously sleep.
- **Field-IO stimulus rig (decided 2026-06-12):** a **Riiai DC 0-10V 0/4-20mA signal generator**
  (Amazon B099DZVG9F) — **manual, single-channel, NO PC control** (micro-USB = power only; knob +
  9 presets). So 4-20mA injection is **operator-driven, one AI at a time**; the runner auto-captures
  + auto-judges the RTT response. Can't drive all 4 AIs at once (global LED/buzzer logic needs 4
  sources). It **sources only — reads nothing**, so relay/siren **output sensing** needs a multimeter
  (manual) or firmware RTT relay-transition + DT90 bit, or a relay→DI loopback. *Future robust path
  for full automation:* PC-controllable source (Yoctopuce Yocto-4-20mA-Tx / USB DAQ) + USB DAQ relay
  readback. Without any stimulus, the self-test DI/analog/RS-echo lines read OFF/ERROR = "not
  stimulated," NOT a failure.
- **Thresholds to ratify** (proposed defaults in USE-CASES.md, not yet authoritative): 4-20 mA/analog
  accuracy ±2% / ±0.1 mA; boot-to-ready 15 s; cell registration 90 s / first publish 120 s; LoRaWAN
  join 30 s.

Build/flash reminders for every test image: [[firmware-build-and-observe]] (variant select,
`WITH_TESTBENCH=y`, RTT) and [[nrf5340-nfc-relay-pins]] (chip-erase for K3/K4).
