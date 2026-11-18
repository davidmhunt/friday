# review-range: A directive's review covers exactly its own commits, however often it restarts
Status: approved
Base: v1
Land: pr

## Goal
The review and the Log's commit list of a directive are its own commits on the goal branch,
found by their `Directive: <id>` line, not every commit since `friday start` last ran. Found when
v1-final's fix-02 blocked twice: once its restart after `friday unblock` moved the review base past
all of fix-02's work, and once a plan amendment committed mid-run (other directives' files only)
failed the "every commit carries `Directive: fix-02`" check. Fixed on v1 first so the running
v1-final goal picks it up. review-02 (approved by the user) makes the rule deterministic: the plan
changes only on Base, and git refuses stray commits while a directive is active.

## Directives
1. review-01: `friday commits <id>` is the directive's change set; review and finish use it
2. review-02: The plan changes only on Base, `friday start` merges Base in, and git refuses stray commits during a directive

## Log
