---
name: dispatch
description: User-invoked. Dispatch a goal's directives to a fleet node, showing the dry-run plan first and asking before the real run.
argument-hint: "<goal>"
disable-model-invocation: true
---

# /friday:dispatch <goal>


The argument is the goal id; pass it as `--goal`. If it is missing, ask for it. From the repo root:

1. Run `friday dispatch --goal <goal> --dry-run`.
2. Show the plan (chosen node, directives) in a few lines.
3. Ask the user whether to go ahead. Stop unless they say yes in this session.
4. Only then run `friday dispatch --goal <goal>` and summarise the result.

If the CLI refuses (non-zero exit), show its one-line `fix:` and stop. Do not work around the refusal.

These run plain `friday` commands. If `friday` is not on PATH, tell the user to run friday install (from the plugin's `bin/friday`) and stop.
