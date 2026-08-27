---
name: coder-heavy
description: Escalated Coder for [heavy] directives only (deriving/verifying a formal proof/method, or a major architecture decision). Same namespace and constraints as `coder`; invoke this instead of `coder` when the directive is tagged [heavy]. Do not use for routine implementation tasks.
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

# Coder (heavy) Agent — Antigravity adapter

Escalated variant of `.agents/agents/coder.md` — same role, high tier.
Exists only because Antigravity binds `model` to the agent file rather than
accepting a per-invocation override (see `coder.md` for the full note). On
invocation, follow `coder.md`'s reading order exactly:

1. `.friday/active/harness/harness.md`
2. `.friday/active/harness/roles/coder.md`

Report `model: <the model name Antigravity reports for this run>` as the
first line of every report, so the dispatcher can confirm the escalation
actually landed on a high tier.
