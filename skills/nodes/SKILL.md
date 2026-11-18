---
name: nodes
description: User-invoked. List the friday fleet registry and, on request, probe each node over ssh.
argument-hint: "[--check]"
disable-model-invocation: true
---

# /friday:nodes

These run plain `friday` commands. If `friday` is not on PATH, tell the user to run friday install (from the plugin's `bin/friday`) and stop.

Read-only. From the repo root, run:

```
friday nodes
```

If the user passed `--check`, run `friday nodes --check` instead.

Summarise in a few lines. Put nodes that need the user first (unreachable, friday missing from
PATH, setup incomplete), then the healthy ones. Do not change anything.
