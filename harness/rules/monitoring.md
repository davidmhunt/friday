# Monitoring & Numerical Guards (harness rules 7 + 11 — full detail)

Read before launching, checking on, or trusting any long-running job or
monitor.

## Rule 7 — Monitor heartbeat (full text)

Any automated/periodic monitor must stamp a last-checked timestamp into its
tracking file (`harness/running/*.md`, `harness/status.md` entries) on EVERY check,
including no-change checks. Consumers treat a timestamp older than ~2× the
stated cadence as "the monitor is dead — verify job state directly," never
as "nothing happened."

**Re-arm ownership.** The monitor process is part of the job. Any role
checking on a run (status read, check-in, wakeup) verifies the monitor
process is alive alongside the job process; a dead or safety-cap-expired
monitor next to a live job is re-armed immediately by whoever found it
(Runner-class action — Controller dispatches, never substitutes ad-hoc
unstamped loops) and noted in `harness/status.md`. A run is "monitored" only while a
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
floor is too coarse, or anything needing real interpretation. What still
needs an actual Runner: launching a run with the right flags and confirming
it started healthy, deciding what to do about an escalation, and
running/summarizing multi-item eval sweeps.

## Hard MUSTs when monitoring

**Verify a live process's real log path before trusting it.** A running
process's actual stdout target frequently differs from the path implied by
its launch command, an earlier session's notes, or `harness/status.md` (relaunches
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
