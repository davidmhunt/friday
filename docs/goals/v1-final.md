# v1-final: A finished spec, a from-zero tutorial and a 1.0 release that fits research, robot and PCB repos
Status: running
Base: v1
Land: pr

## Goal
friday 1.0.0: the defects found by the 2026-11-17 docs-versus-code audit are fixed; a directive can
wait for the user's sign-off (`Accept: user`, `friday accept`); expensive runs are recorded once
and checked cheaply (`friday result`); `docs/spec.md` is the one reference for the model, formats,
commands and hooks and tests keep it in step with the code; `docs/getting-started.md` takes a new
repo from nothing to a landed goal, with recipes for a research repo, a robot software repo
(console) and a KiCad repo. The full suite and `claude plugin validate .` pass.

Decided, not built here: v1 merges into main by a separate PR the user merges; CPSL_TI_Radar and
console adopt 1.0 in their own repos afterwards; known limits (deny list matches inside `ssh`,
hardware prompts in a dispatched session, GitHub-only landing) are documented in the spec.

## Directives
1. fix-01: Landing, Verify and status rules do what the docs say
2. fix-02: Every command and flag is real, documented in `--help` and allowed without a prompt
3. gate-01: A directive with `Accept: user` waits for `friday accept` before its goal can land
4. gate-02: `friday result` records an expensive run once so Verify stays cheap
5. spec-01: `docs/spec.md` is the single reference, kept in step with the code by tests
6. spec-02: A from-zero tutorial and recipes for research, robot and PCB repos
7. rel-01: Release 1.0.0

## Log
