---
description: Full-depth review of each software repo → docs/software/<name>.md (read-only; cloud/backend/app)
---

Run the **understand-software** skill at [.claude/skills/understand-software/SKILL.md](../skills/understand-software/SKILL.md) and follow it exactly.

Software repos (cloud/backend/app/API/dashboards) are READ-ONLY references — clone shallow into `.refs/`, read, produce docs; never modify them. Skip cleanly if `project.yaml` has no `software:` entries. Use a fan-out workflow for full depth if your session supports it.

$ARGUMENTS
