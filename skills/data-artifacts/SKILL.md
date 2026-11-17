---
name: data-artifacts
description: Rules for shared data artifacts (recordings, ground truth, configs other runs depend on, result files): new names instead of overwrites, provenance sidecars, snapshots before mutation. Use before writing, regenerating or deleting any data another run or result depends on.
---

# Data artifacts

These rules exist because a plausible number from the wrong file is worse than no number.

1. **Never overwrite an artifact something else consumes** (recordings, ground truth, calibration,
   result files, shipped configs). New runs write new, run-specific names. Replacing a canonical
   file needs a directive that says so, approved by the user.
2. **Provenance sidecar for every result.** Next to each result file, a same-basename JSON with at
   least: input files, code commit, config, command and args, timestamp. Before reporting a result,
   read its sidecar and confirm it matches the run you claim. A mismatch is a failed run, not a result.
3. **Snapshot before mutating canonical data.** Copy or snapshot the data first (filesystem
   snapshot, versioned bucket, dated copy) and name the snapshot in the directive Log. Restore by
   copying out of the snapshot, never by rolling back in place.
4. **A root-cause claim needs a controlled reproduction:** the failure reproduced, the fix applied,
   the failure gone, with everything else held fixed. Otherwise call it a hypothesis.
