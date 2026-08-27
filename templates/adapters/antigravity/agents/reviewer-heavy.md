---
name: reviewer-heavy
description: Escalated Reviewer for [heavy] review passes only. Same namespace and constraints as `reviewer`; invoke this instead of `reviewer` when the pass is tagged [heavy]. Do not use for routine reviews.
tools:
  - view_file
  - list_dir
  - find_by_name
  - grep_search
  - write_to_file
  - replace_file_content
  - run_command
  - read_url_content
subagent: true
mainAgent: false
model: pro  # High tier
commandExecutionPolicy: sandbox
---

# Reviewer (heavy) Agent — Antigravity adapter

Escalated variant of `.agents/agents/reviewer.md` — same role, high tier.
Exists only because Antigravity binds `model` to the agent file rather than
accepting a per-invocation override (see `reviewer.md` for the full note).
On invocation, follow `reviewer.md`'s reading order exactly:

1. `.friday/active/harness/harness.md`
2. `.friday/active/harness/roles/reviewer.md`

Report `model: <the model name Antigravity reports for this run>` as the
first line of every report, so the dispatcher can confirm the escalation
actually landed on a high tier.
