# field-fixes: Fixes from the first real use: execute order, notes, hardware approval, batches, dispatch
Status: running
Base: v1
Land: pr

## Goal
Issues #14, #15, #17 and #18 from using friday in the console repo, plus two dispatch problems
found the same day. `/friday:execute` reads a directive only after Base is merged in, so
amendments are seen; `friday finish` can no longer break a directive file with headings from notes; hardware
prompts say what they mean, a resource can be approved once per session, and agents are told to
write one simple command per hardware query, and a batch is pre-approved when every command in
it is; a dispatched session loads friday once on a node
where it is installed, and `friday nodes --check` reports the outside-reads prompt setting.
Approved by the user on 2026-11-18, exec-02 and pre-01 added the same day (#13, the push timer in a container, is a later goal).

Folded into the 1.1.0 release at the user's request: it lands on v1 and reaches main with PR #19,
so CHANGELOG entries go in the `1.1.0` section (not yet tagged), not `Unreleased`.

review-03 (#21) and scope-01 (goal size, from the PR history) were added the same day under the
new rule: related work extends the open goal (approved by the user).

## Directives
1. exec-02: `/friday:execute` merges Base before it parses, so amendments and new directives are seen (fixes #18)
2. notes-01: `friday finish` keeps notes from breaking the Log (fixes #14)
3. hw-01: Hardware prompts say they are per command, and a resource can be approved once per session (fixes #15)
4. pre-01: A chained or multi-line command is pre-approved when every command in it is (fixes #17)
5. disp-01: A dispatched session loads friday once, and `nodes --check` reports the outside-reads setting
6. review-03: Upstream commits merged in by `friday start` never count against a directive (fixes #21)
7. scope-01: Goals cover a whole capability, and related work extends the open goal instead of opening a new PR

## Log
