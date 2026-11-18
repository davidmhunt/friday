---
name: clean
description: User-invoked. Remove finished goals' worktrees on a fleet node, showing the dry-run first and asking before the real run.
argument-hint: "<node>"
disable-model-invocation: true
---

# /friday:clean <node>

The argument is the node name. If it is missing, ask for it. From the repo root:

1. Run `${CLAUDE_PLUGIN_ROOT}/bin/friday nodes --clean <node> --dry-run`.
2. Show what would be removed in a few lines.
3. Ask the user whether to go ahead. Stop unless they say yes in this session.
4. Only then run `${CLAUDE_PLUGIN_ROOT}/bin/friday nodes --clean <node>` and summarise the result.

If the CLI refuses (non-zero exit), show its one-line `fix:` and stop. Do not work around the refusal.
