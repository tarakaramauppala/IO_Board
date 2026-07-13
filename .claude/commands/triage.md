---
description: Turn a run's failures into issues — classified, routed to the respective repo, deduped, mirrored locally
---

Run the **triage** skill at [.claude/skills/triage/SKILL.md](../skills/triage/SKILL.md) and follow it exactly.

Classify each failure (hardware/firmware/software/test-bench/flaky), route the GitHub issue to the respective repo (hardware→hardware, firmware→firmware, software→software), dedup against issues/* by signature, and keep the local mirror. Confirm before creating GitHub issues. Never push code to the hardware/firmware/software repos.

$ARGUMENTS
