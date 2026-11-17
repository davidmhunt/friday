---
name: directive
description: The friday directive format and lifecycle (docs/directives/<id>.md): header fields, statuses, the Verify contract, the commit trailer. Use when reading, writing or updating a directive.
user-invocable: false
---

# Directive format

A directive is one approved unit of work, tracked in git at `docs/directives/<loop>-<NN>.md`.
It is the record of why a change was made, so keep it accurate.

```markdown
# core-03: Reject cfgs whose chirp range exceeds the board limit
Status: proposed
Node: any
Verify: ./run tools/check.sh && ./run uv run pytest tests/test_cfg_limits.py -q
Hardware: none

## Goal
One or two sentences: the result, and how a reader can tell it holds.

## Steps
1. ... (name files and interfaces; tag `[heavy]` with "Heavy because: ..." when needed)
2. ...

## Out of scope
- ...

## Log
(execution appends here: commits, Verify results, verifier verdict, PR link, blockers)
```

Header fields (before the first `##`):
- **Status**: `proposed` → `approved` (only the user approves) → `running@<host>` → `done`, or
  `blocked: <reason>`. Change it with `friday start` / `friday finish`, not by hand, during execution.
- **Node**: `any`, `tag:<capability>` (e.g. `tag:gpu`, `tag:radar-iwr1843`) or `host:<name>`.
- **Verify**: one shell command, run from the repo root, exit 0 only when the goal holds. The
  directive is not done until it passes; a Stop hook enforces this while the directive is active.
- **Hardware**: `none`, or the resources it touches. Hardware commands always ask the user.

Commits made for a directive end with the line `Directive: <id>` (a hook checks this while it is
active) and land on the branch `friday/<id>`, never on main.

Changing scope: anything that alters Goal, Steps, Verify or Out of scope goes back to the user,
then gets a dated line in the Log.
