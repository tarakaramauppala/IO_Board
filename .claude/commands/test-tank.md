---
description: Run the Tank Monitor test plan (flash + RTT scopes) — tests/tank-monitor/
argument-hint: "[boot|selftest|thresholds|relay|siren|all]  (default: all)"
---

Run the **Tank Monitor** test plan in `tests/tank-monitor/` (read `tests/tank-monitor/plan.md` first
for scope details and caveats). The argument selects the scope; default `all`.

Steps:
1. Confirm a flashable image: `TANK_IMAGE` env var (or `--image`) must point to a built/release
   **tank-monitor** merged hex (`WITH_APPLICATION_IO_BOARD_TYPE=0`, `WITH_TESTBENCH=y` for `selftest`).
   If unset, tell the user — don't guess a path.
2. Remind: flashing uses **`nrfjprog --recover`/chip-erase** so UICR `NFCPINS=GPIO` is written (or
   relays K3/K4 won't switch); observe is **RTT over J-Link** (no serial); power the DUT at **12 V (J36)**.
3. From `tests/tank-monitor/`, run `python run.py <scope>` (scope = `$ARGUMENTS` or `all`). The
   `thresholds`/`relay`/`siren` scopes are **interactive** (prompt for injected mA / multimeter V) —
   relay the prompts to the user.
4. Read `results/<run-id>/tank-monitor/*.json` and summarize per-scope PASS/FAIL/REVIEW. Note which
   results are **cloud-deferred** (TANK_LEVEL_*/DT113/SIREN — need the AWS→Tailscale→ThingsBoard path).
5. If any scope FAILs, offer to route it via `/triage` (HW vs FW vs test-bench).

No hardware? Run `python test_parse.py` to validate the parsers offline against fixtures.
