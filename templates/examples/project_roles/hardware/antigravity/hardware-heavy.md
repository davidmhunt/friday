---
name: hardware-heavy
description: Escalated Hardware agent for [heavy] directives only (board-level architecture, a new interface design). Same namespace and constraints as `hardware`; invoke this instead of `hardware` when the directive is tagged [heavy].
tools:
  - view_file
  - list_dir
  - find_by_name
  - grep_search
  - write_to_file
  - replace_file_content
  - run_command
subagent: true
mainAgent: false
model: pro  # High tier
commandExecutionPolicy: auto
---

# Hardware (heavy) Agent — Antigravity adapter

Escalated variant of `.agents/agents/hardware.md` — same role, high tier.
Exists only because Antigravity binds `model` to the agent file rather than
accepting a per-invocation override (see `hardware.md` for the full note). On
invocation, follow `hardware.md`'s reading order exactly:

1. `.friday/active/harness/harness.md`
2. `.friday/active/harness/roles/hardware.md`

Report `model: <the model name Antigravity reports for this run>` as the
first line of every report, so the dispatcher can confirm the escalation
actually landed on a high tier.
