# v1-final: A finished spec, a from-zero tutorial and a 1.0 release that fits research, robot and PCB repos
Status: done
Base: v1
Land: pr

## Goal
friday 1.0.0: the defects found by the 2026-11-17 docs-versus-code audit are fixed; a directive can
wait for the user's sign-off (`Accept: user`, `friday accept`); expensive runs are recorded once
and checked cheaply (`friday result`); commands the user pre-approves in a directive run unattended
(`## Allowed commands`); `docs/spec.md` is the one reference for the model, formats,
commands and hooks and tests keep it in step with the code; `docs/getting-started.md` takes a new
repo from nothing to a landed goal, with recipes for a research repo, a robot software repo
(console) and a KiCad repo. Goal review-range (on v1, merged in before fix-02 resumes) supplies
`friday commits`, plan amendments on Base, `friday start` merging Base, and the commit-msg guard;
the spec and tutorial document them. The full suite and `claude plugin validate .` pass.

Decided, not built here: v1 merges into main by a separate PR the user merges; CPSL_TI_Radar and
console adopt 1.0 in their own repos afterwards; known limits (deny list matches inside `ssh`,
hardware commands in a dispatched session run only when pre-approved, GitHub-only landing) are documented in the spec.

## Directives
1. fix-01: Landing, Verify and status rules do what the docs say
2. fix-02: Every command and flag is real, documented in `--help` and allowed without a prompt
3. gate-01: A directive with `Accept: user` waits for `friday accept` before its goal can land
4. gate-02: `friday result` records an expensive run once so Verify stays cheap
5. gate-03: Commands the user pre-approves in a directive run without a prompt during that directive
6. spec-01: `docs/spec.md` is the single reference, kept in step with the code by tests
7. spec-02: A from-zero tutorial and recipes for research, robot and PCB repos
8. rel-01: Release 1.0.0

## Log
- 2026-11-18: Landed: 8 directive(s) reverified on friday/v1-final; PR into v1.
