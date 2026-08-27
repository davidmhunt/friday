---
name: runner-judgment
description: Escalated Runner for jobs that need real judgment (interpreting ambiguous failures, deciding whether to re-launch, distinguishing a real escalation from noise) rather than routine launch-and-poll. Same namespace and constraints as `runner`; invoke this instead of `runner` when the situation calls for it. Do not use for routine job launches.
tools:
  - view_file
  - list_dir
  - find_by_name
  - grep_search
  - write_to_file
  - replace_file_content
  - run_command
  - manage_task
subagent: true
mainAgent: false
model: inherit  # Mid tier stand-in — see the note in .agents/agents/controller.md
commandExecutionPolicy: auto
---

# Runner (judgment) Agent — Antigravity adapter

Escalated variant of `.agents/agents/runner.md` — same role, mid tier
instead of light. Exists only because Antigravity binds `model` to the
agent file rather than accepting a per-invocation override (see
`runner.md` for the full note). On invocation, follow `runner.md`'s
reading order exactly:

1. `.friday/active/harness/harness.md`
2. `.friday/active/harness/roles/runner.md`

Report `model: <the model name Antigravity reports for this run>` as the
first line of every report, so the dispatcher can confirm the escalation
actually landed on the intended tier.
