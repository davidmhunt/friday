---
name: status
description: User-invoked. Show this repo's friday directives, the active one, and hardware leases in a few lines.
disable-model-invocation: true
---

# /friday:status

Read-only. From the repo root, run:

```
${CLAUDE_PLUGIN_ROOT}/bin/friday status
```

Summarise the output in a few lines. Put items that need the user first (blocked directives,
directives awaiting approval, held hardware leases), then the active directive, then the rest.
Do not change anything.
