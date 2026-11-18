---
name: nodes
description: User-invoked. List the friday fleet registry and, on request, probe each node over ssh.
argument-hint: "[--check]"
disable-model-invocation: true
---

# /friday:nodes

Read-only. From the repo root, run:

```
${CLAUDE_PLUGIN_ROOT}/bin/friday nodes
```

If the user passed `--check`, run `${CLAUDE_PLUGIN_ROOT}/bin/friday nodes --check` instead.

Summarise in a few lines. Put nodes that need the user first (unreachable, friday missing from
PATH, setup incomplete), then the healthy ones. Do not change anything.
