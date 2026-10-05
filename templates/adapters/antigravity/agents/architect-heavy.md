---
name: architect-heavy
description: Escalated Architect for project-level specs only. Same namespace and constraints as `architect`; invoke this instead of `architect` when the spec is project-level. Do not use for small specs.
tools:
  - view_file
  - list_dir
  - find_by_name
  - grep_search
  - write_to_file
  - replace_file_content
  - run_command
subagent: true
mainAgent: true
model: pro  # High tier
commandExecutionPolicy: sandbox
---

# Architect (heavy) Agent — Antigravity adapter

Escalated variant of `.agents/agents/architect.md` — same role, high tier.
Exists only because Antigravity binds `model` to the agent file rather than
accepting a per-invocation override (see `reviewer.md` for the full note).
On invocation, follow `architect.md`'s reading order exactly:

1. `.friday/active/harness/harness.md`
2. `.friday/active/harness/roles/architect.md`
3. `.friday/active/harness/templates/spec_template.md`

Report `model: <the model name Antigravity reports for this run>` as the
first line of every report, so the dispatcher can confirm the escalation
actually landed on a high tier.

Steering tags (`User-Feedback:` / `Controller-Update:`) and "questions go up" (a user-only decision goes in your report with a recommendation, never a guess) apply exactly as in `architect.md`.
