# Memory index — <project> testing

This product's hard-won test knowledge: board gotchas, locked test decisions, cloud
mappings, bench caveats. One fact per file; this is the index loaded each session.
`/understand-*`, `/define-use-cases`, and `/build-test-plan` seed facts here; add to them as you learn.

Format per file: frontmatter (`name`, `description`, `metadata.type: project|reference|feedback`)
then the fact. Link related facts with `[[name]]`.

<!-- Add one line per memory: - [Title](file.md) — hook -->
- [Bench power & observe](bench-power-and-observe.md) — power 12V at J36, J-Link SWD/RTT, no serial/PPK2
- [nRF5340 NFC relay pins](nrf5340-nfc-relay-pins.md) — relays K3/K4 on NFC pins; firmware sets NFCT_PINS_AS_GPIOS but needs chip-erase flash
- [Firmware build & observe](firmware-build-and-observe.md) — 3 images = 1 repo's variants; build flags, RTT, boot self-test hook
- [Cloud telemetry path](cloud-telemetry-path.md) — telemetry → AWS IoT (cellular); LoRaWAN disabled; DT90/DT104; vs project.yaml ThingsBoard
- [Test scope decisions](test-scope-decisions.md) — cloud via RTT→Tailscale→TB; radio prereqs present; sleep deferred; IO rig TBD
- [Doc generation toolchain](doc-generation-toolchain.md) — Word+PDF deliverables: python-docx, Chrome headless PDF, SVG→PNG via Chrome, Word COM for QA
