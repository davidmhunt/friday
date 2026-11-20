# field-fixes-3: Pre-approval, hardware matching and Verify behave as the user expects in real projects
Status: blocked: hw-02
Base: main
Land: pr

## Goal
Three issues the user filed from the console and fmcw3-ckflight sessions on 2026-11-20, all on
friday 1.1/1.2. #31: a goal with `## Allowed commands` but no published plan ref runs with nothing
pre-approved and nothing says why (the user got prompted constantly). #32: hardware patterns match
any mention of a path, so `git add`, `git diff` and commit messages naming a robot script take the
lease and prompt. #33: with `bash_file_io: "deny"`, the execute workflow's own Verify run is denied
when the Verify line reads files, and the block says "no reason given". The user asked to address
them now (2026-11-20: "go ahead and address them now"); the user approved all three directives the same day. #13 and #20 (feature requests) stay later.

## Directives
1. pa-01: A goal whose Allowed commands are not pre-approved says so, in start, status, the workflow and the prompt itself (fixes #31)
2. hw-02: Hardware patterns match only commands that can run something, and `friday check` warns on a verb-less pattern (fixes #32)
3. vf-01: The active directive's own Verify line is exempt from bash_file_io, and a Verify not run says why (fixes #33)

## Log
