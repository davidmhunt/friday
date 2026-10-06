# Monitoring & Numerical Guards (harness rules 7, 11, 18 — full detail)

Read before launching, checking on, or trusting any long-running job or
monitor.

## Long runs go to a Runner (rule 18 — full text)

**Why.** The prompt cache expires after ~5 min idle. An agent that sits
through a 20-min build re-writes its whole context (often 300k+ tokens) on
the next turn — every wait costs a full context rewrite. A Runner's context
is small and light tier, so it waits cheaply.

**Threshold.** A command expected to take **> ~4 min** — full or
integration test suites, release/clean builds, Docker image or firmware
builds, benchmarks, hardware/bench runs, training, eval sweeps — is a long
run. A worker (Coder, specialist, Reviewer) does not launch-and-wait on it.
Short checks (one test file, an incremental build, a lint, a dry-run) stay
with the worker. Unsure? Time a short slice or assume long.

**Handoff.**
1. **Worker:** commits, then appends a `Run request` to the directive Log —
   exact command, commit hash, expected duration, pass criterion, numbers
   or lines to extract — and ends its turn reporting `handoff: Runner`. It
   does not wait, poll, or `sleep`.
2. **Controller:** spawns a Runner (light tier) on the request.
3. **Runner:** launches detached (rule 15), arms a zero-token monitor (below)
   as a background task, and reports on completion: pass/fail, key numbers,
   log path, first error excerpt (≤ 20 lines) — into the directive Log.
4. **Controller:** on pass, dispatch the next Step or the Reviewer (which
   may cite the Runner's logged run for that commit instead of re-running
   it); on fail, spawn a **fresh** worker pointed at the Log entry and the
   log path — not a resume of the old big-context one.

**If a worker must wait anyway** (no Runner can take it, or the result is
due within a few minutes), each blocking wait is ≤ ~4 min per turn, so the
cache stays warm; past that, hand off.

## Rule 7 — Monitor heartbeat (full text)

Any automated/periodic monitor must stamp a last-checked timestamp into its
tracking file (`.friday/active/harness/running/*.md`, `.friday/active/harness/status.md` entries) on EVERY check,
including no-change checks. Consumers treat a timestamp older than ~2× the
stated cadence as "the monitor is dead — verify job state directly," never
as "nothing happened."

**Re-arm ownership.** The monitor process is part of the job. Any role
checking on a run (status read, check-in, wakeup) verifies the monitor
process is alive alongside the job process; a dead or safety-cap-expired
monitor next to a live job is re-armed immediately by whoever found it
(Runner-class action — Controller dispatches, never substitutes ad-hoc
unstamped loops) and noted in `.friday/active/harness/status.md`. A run is "monitored" only while a
live monitor stamps heartbeats.

## Rule 11 — Fail-loud numerical guards (full text)

A guard that skips a bad batch/step on non-finite loss or grad-norm (instead
of crashing) MUST also detect the case where the underlying state is
*permanently* corrupted and abort loudly — skip is licensed only for an
ISOLATED bad batch, never as an indefinite response to total collapse. Two
hard requirements: (a) a "no valid batches this epoch" (or any
no-usable-data) condition must resolve to a value that reads as FAILURE
(`+inf`, an explicit sentinel, a propagated NaN) and NEVER to one that reads
as SUCCESS — a zero/near-zero average out of `sum / max(n, 1)` is a fake
perfect score that poisons LR schedulers, "beats" best-val, and overwrites
the canonical checkpoint with corrupted weights; (b) N consecutive
fully-dead epochs/steps (unambiguous total collapse) hard-abort the run —
they do not skip forever. Any health monitor watching such a run keys on
the failure sentinel or a suspiciously-static/unchanged metric, not only the
literal strings `nan`/`inf` (a collapsed run can print a benign-looking
`0.0000`, never the word "nan"). Rule 7 protects against a *dead monitor*;
this protects against a *live guard/monitor that silently masks total
failure as success*.

## The zero-token monitor

Routine "is this run still healthy" polling (grep for NaN/Traceback, track
step number, check the process is alive) needs zero LLM judgment. Do NOT
run an agent poll loop for it — launch a plain background OS process
(a small Python/shell script) that does the regex/process checks,
self-adjusts its sleep interval, and stamps a timestamped heartbeat into its
tracking file on EVERY check (rule 7). On a real state-change event (NaN,
unexpected process death, completion) it writes a short report and exits,
giving whoever launched it a natural background-task-completion signal.
This costs zero agent tokens for the entire monitoring lifetime.

A live agent loop / blocking wait is still right for what the script can't
do: a fast-changing event in the next few minutes where a coarse polling
floor is too coarse, or anything needing real interpretation — held by a
Runner, never by a big-context worker (rule 18 above). What still
needs an actual Runner: launching a run with the right flags and confirming
it started healthy, summarizing the result, deciding what to do about an
escalation, and running/summarizing multi-item eval sweeps.

## Hard MUSTs when monitoring

**Verify a live process's real log path before trusting it.** A running
process's actual stdout target frequently differs from the path implied by
its launch command, an earlier session's notes, or `.friday/active/harness/status.md` (relaunches
rename logs). Before you grep, tail, or declare a "stall" on a live process,
confirm the real target directly (e.g. inspect its open file descriptors)
and use THAT path.

**Health regexes must not rely on literal `nan`/`inf` alone.** A collapsed
run can print a numeric artifact (e.g. a metric stuck at exactly `0.0000`,
or unchanged for many steps) and never emit the string "nan" on the line a
monitor greps. When arming a monitor: (a) match the script's OWN explicit
collapse-signal strings (e.g. "zero usable batches", "ABORT:", a traceback
marker, an out-of-memory marker, a disk-quota marker, "Killed"), not a
guessed generic pattern; (b) treat a metric stuck at exactly zero or
unchanged across N consecutive steps as escalation-worthy, since the
fail-loud sentinel (rule 11) is what a healthy monitor keys on. Also verify
your monitor's default regexes actually match your script's real log
format before trusting it — a mismatched default can silently false-negative
for an entire run.

**Resume/report only on a genuine new event.** An agent holding a blocking
wait must NOT wake, resume, and report just to restate "nothing changed" —
"no new information since the last report" is never a reason to surface.
Resume/report only for a real event: an escalation, a process exit, a
crossed milestone, or a completion. And after any blocking wait RETURNS,
verify the job's actual state and either re-arm the wait or report a real
transition — never let the wait silently end with the agent going idle
without notifying.
