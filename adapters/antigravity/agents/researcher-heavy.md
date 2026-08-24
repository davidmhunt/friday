---
name: researcher-heavy
description: Escalated Researcher for [heavy] or clearly proof-bearing directives only (deriving/verifying a formal proof/method, load-bearing methodology judgment). Same namespace and constraints as `researcher`; invoke this instead of `researcher` when the directive is tagged [heavy]. Do not use for routine literature synthesis or memo-writing.
tools:
  - view_file
  - list_dir
  - find_by_name
  - grep_search
  - write_to_file
  - replace_file_content
  - run_command
  - search_web
  - read_url_content
subagent: true
mainAgent: false
model: pro  # High tier
commandExecutionPolicy: sandbox
---

# Researcher (heavy) Agent — Antigravity adapter

Escalated variant of `.agents/agents/researcher.md` — same role, high tier
instead of mid. Exists only because Antigravity binds `model` to the agent
file rather than accepting a per-invocation override (see `researcher.md`
for the full note). On invocation, follow `researcher.md`'s reading order
exactly:

1. `harness/harness.md`
2. `harness/roles/researcher.md`

Use this only for a directive tagged `[heavy]` or otherwise clearly
proof-bearing (see `harness/harness.md` for the exact definition) — not as
a default for "important-sounding" research. Report `model: <the model
name Antigravity reports for this run>` as the first line of every report.
