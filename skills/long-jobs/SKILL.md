---
name: long-jobs
description: How to launch, watch and trust long runs (builds, full test suites, benchmarks, recordings, training, sweeps) under friday. Use before starting anything expected to take more than about 4 minutes.
---

# Long jobs

Waiting is expensive for a large agent: a long idle wait lets the prompt cache expire and the next
turn re-reads the whole context. Long runs go to the `runner` agent, which is small and cheap.

- **Threshold:** more than about 4 minutes (full suites, release or Docker or firmware builds,
  benchmarks, hardware runs, training, sweeps). Short checks stay with the implementer.
- **Verify is never detached.** A directive's Verify command is one plain foreground call (600000
  ms timeout, no `setsid`, `nohup`, `&` or `run_in_background`). Detaching is only for long runs a
  step names, never for Verify.
- **Detached launch:** the run must survive the session. Output to `runs/<id>/<name>.log`, exit
  code to `runs/<id>/<name>.exit` (see the `runner` agent for the exact form). Never `sleep` for
  more than a few minutes in one turn.
- **Finished means the exit file exists.** A log that stopped growing is not a result.
- **Watchers stamp a heartbeat.** Any periodic monitor writes a last-checked time on every check,
  even when nothing changed. A heartbeat older than twice its interval means the monitor is dead:
  check the job directly and re-arm it.
- **Fail loud.** A guard that skips a bad batch or frame must also abort when every batch or frame
  is bad. Skipping is for isolated faults only.
- **Report numbers with their source:** the log path and the exact command and commit that
  produced them.

## Run once, record, check cheaply

A training run, sweep or bench test should run once, as its own step, not inside Verify (Verify is
re-run at every fix round and at landing). After it finishes, record it:

    friday result write <id> --metric acc=0.91 --file runs/<id>/model.pt --cmd "<exact command>"

This writes the tracked `results/<id>.json` (metrics, file hashes, commit, node, time). The
directive's Verify is then the seconds-long `friday result check <id> --require 'acc >= 0.9' --files`.

This is advice. These two skills (long-jobs, data-artifacts) are guidance only; no hook enforces
them, and nothing stops a Verify from re-running the whole job.
