---
name: editor-heavy
description: Escalated Editor for [heavy] documents only. Same namespace and constraints as `editor`; invoke this instead of `editor` when the document is dense derivation-bearing text where a careless cut could break an argument. Do not use for routine concision passes.
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
commandExecutionPolicy: sandbox
---

# Editor (heavy) Agent — Antigravity adapter

Escalated variant of `.agents/agents/editor.md` — same role, high tier.
Exists only because Antigravity binds `model` to the agent file rather than
accepting a per-invocation override (see `reviewer.md` for the full note).
On invocation, follow `editor.md`'s reading order exactly:

1. `.friday/active/harness/harness.md`
2. `.friday/active/harness/roles/editor.md`
3. `.friday/active/harness/rules/document_budgets.md`

Report `model: <the model name Antigravity reports for this run>` as the
first line of every report, so the dispatcher can confirm the escalation
actually landed on a high tier.
