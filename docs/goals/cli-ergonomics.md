# cli-ergonomics: `friday` on PATH everywhere, and slash commands in Claude
Status: done
Base: v1
Land: pr

## Goal
Running friday no longer depends on knowing where a plugin checkout lives: `friday install`
puts `friday` on PATH on the master and, through `friday nodes --setup`, on every node, and any
Claude session that loads the plugin (including over Remote Control) offers `/friday:status`,
`/friday:nodes`, `/friday:dispatch <goal>` and `/friday:clean <node>`. Asked for by the user after
finding the CLI hard to locate and call.

## Directives
1. cli-01: `friday install` puts `friday` on PATH, on the master and on every node
2. cli-02: Slash commands `/friday:nodes`, `/friday:status`, `/friday:dispatch`, `/friday:clean`
3. cli-03: `friday init` adds the friday allow rules to a repo; dispatch refuses a repo without them

## Log
- 2026-11-17: Landed: 3 directive(s) reverified on friday/cli-ergonomics; PR into v1.
