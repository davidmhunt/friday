# exec-commands: The execute workflow runs friday commands so the allow rules match
Status: approved
Base: v1
Land: pr

## Goal
Every friday CLI call the `/friday:execute` workflow asks an agent to make (`parse`, `start`,
`finish`, `land`, `land --goal`) is a single Bash call with nothing chained, so the repo's
`Bash(friday …)` allow rules match it and the auto-mode classifier is never consulted. Found when
cli-ergonomics' `friday land cli-01; echo "exit $?"` was refused on Alfred: Claude Code checks each
part of a chained command, and the trailing `echo` matched no rule. Approved by the user
("put the real and correct fix in").

## Directives
1. exec-01: Workflow prompts run each friday command alone, with no `cd`, chaining or `echo $?`

## Log
