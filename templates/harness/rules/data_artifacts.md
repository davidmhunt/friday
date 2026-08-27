# Data Artifacts: Namespacing, Provenance, Snapshots (rules 1 + 5 + 6)

Read before writing/overwriting shared artifacts, writing a new eval script,
or mutating any canonical data.

## Rule 1 — Shared-artifact namespacing (full text)

Never mutate a data artifact an existing eval or training run consumes
(precomputed priors/features, result CSVs, model checkpoints, ground
truth). Every new experiment writes under new, experiment-specific
filenames; canonical filenames are append-only history — replacing one
requires an explicit directive in `.friday/active/harness/plans/next_steps.md`.

**Re-run clause:** a crash-forced restart may overwrite its OWN
directive-assigned artifact filename only if the prior checkpoint + result
artifact + provenance sidecar were already fully recorded (the superseded
state is safely held elsewhere — the work record, object storage, a
backup), AND the directive's eval MUST be re-run against the restart's
actual final artifact before close-out. A result artifact whose sidecar
checkpoint-reference no longer matches the on-disk file is STALE — never
cite it; flag it.

## Rule 5 — Eval provenance sidecars (full text)

Every result artifact gets a same-basename provenance record (JSON, or
whatever your project's convention is) recording at minimum: checkpoint/run
path + mtime, input artifact filename(s), code version, data directory
mtimes, eval script + args, timestamp. Use a shared
`write_provenance()`-style helper. Mandatory for new eval scripts; existing
ones adopt it as next touched.

**Eval-completion self-check (addendum):** before ANY agent reports an eval
as complete (task entry, `.friday/active/harness/status.md`, or report to its spawner), it MUST:

1. Read the new artifact's provenance sidecar.
2. Confirm the recorded checkpoint/run matches the intended one for the
   claimed result (and, where applicable, that other recorded args agree).
3. Paste the verified checkpoint/run path verbatim into the task entry
   alongside the completion claim.

A sidecar-vs-claim mismatch is reported **FAILED**, never complete — the
eval is re-run against the correct checkpoint under a correct namespace.
The failure mode this catches is an agent reporting a result it never
produced — a fabricated provenance call, or a prior run's output relabelled
as a new one. Nothing else in the loop detects it, because the number looks
perfectly plausible. Mechanical backstop if you can build one: a script
flagging identical-content artifacts that claim different run tags, run by
the Reviewer at pass start alongside the other checkers.

## Rule 6 — Pre-mutation snapshots for canonical data (full text + procedure)

Before ANY operation that mutates canonical data (re-generation, GT
changes, destructive re-processing), take a snapshot/backup first. The
mechanism depends on your storage:

- Filesystem with copy-on-write snapshots (ZFS, Btrfs, LVM thin, etc.):
  `[your snapshot command, e.g. zfs snapshot <pool>@pre-<desc>-<date>]`
- Object storage: enable/verify versioning, or copy the prefix.
- Database: a dated backup/dump.

Recovery is read-only copy-out from the snapshot — never roll back the live
volume in place unless you're certain nothing else depends on it. If your
project has one standing "precious" backup, name it here and note it must
never be destroyed. Automate retention if your platform supports it (e.g.
`sanoid` for ZFS); until that's configured, the manual snapshot discipline
above is the only safety net — treat it as load-bearing, not optional.
