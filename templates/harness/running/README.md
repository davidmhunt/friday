# Running (Runner namespace)

Runner-owned working state: launch notes, watchdog/monitor configs, logs,
and alert files for in-flight or recently-finished background jobs. Treated
as historical/write-once by other roles — the Planner in particular does
not rely on this directory for current state (see `.friday/active/harness/roles/
planner.md`); `.friday/active/harness/status.md` is the live dashboard.

Typical contents once the harness is in use (none checked in yet — this is
an empty template):

- `<job>_state.json` — a monitor's heartbeat/state file (rule 7).
- `watchdog_config/` — per-job monitor configs; archive a config (e.g. to
  `watchdog_config/archive/`) once its job is confirmed complete, so a
  monitor doesn't keep alerting on a finished run.
- `logs/` — job stdout/stderr for detached background launches (see
  `.friday/active/harness/rules/environment.md` §Detached launches).
- `alerts/` — dated alert files a monitor writes on a real escalation.
