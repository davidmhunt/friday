---
name: planner-heavy
description: Escalated Planner for [heavy] planning passes only (architecture decisions, major task-breakdown calls). Same namespace and constraints as `planner`; invoke this instead of `planner` when the pass is tagged [heavy]. Do not use for routine planning cycles.
tools:
  - view_file
  - list_dir
  - find_by_name
  - grep_search
  - write_to_file
  - replace_file_content
  - run_command
  - invoke_subagent
subagent: true
mainAgent: false
model: pro  # High tier
commandExecutionPolicy: sandbox
---

# Planner (heavy) Agent — Antigravity adapter

Escalated variant of `.agents/agents/planner.md` — same role, high tier.
Exists only because Antigravity binds `model` to the agent file rather than
accepting a per-invocation override (see `planner.md` for the full note).
On invocation, follow `planner.md`'s reading order exactly:

1. `.friday/active/harness/harness.md`
2. `.friday/active/harness/roles/planner.md`

Report `model: <the model name Antigravity reports for this run>` as the
first line of every report, so the dispatcher can confirm the escalation
actually landed on a high tier.
