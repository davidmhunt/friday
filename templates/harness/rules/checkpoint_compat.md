# Checkpoint / Model Compatibility (harness rule 4 — full text)

Read before any change to shared model-definition code.

Any forward-pass-altering (or equivalently, output-altering) change to a
shared model-definition file — a backbone/module class, anything whose
saved checkpoints multiple directives load — MUST:

(a) state in the work record (rule 12) which checkpoints it may silently
    invalidate and how to score them (e.g. a `--legacy-*` flag);
(b) gate the new behavior behind a constructor/config flag defaulting to the
    new behavior, so old checkpoints stay scoreable — precedent pattern:
    add a boolean flag whose default matches the new code path but whose
    `False`/legacy setting reproduces the old forward pass exactly;
(c) bump a compatibility version field in the saved checkpoint at save time
    so a mismatched load fails loudly, naming the legacy flag needed (stamp
    + assert live in shared train/eval utilities).

Rule 1 protects shared *data*; this protects shared *code* whose changes
load cleanly but score wrong — the dangerous case is a change that doesn't
error, just silently produces different numbers from an old checkpoint
(e.g. a normalization-layer change that has no learnable parameters, so it
loads without any shape mismatch, but shifts the computed statistics enough
to produce a large systematic bias that looks like a real regression rather
than a compatibility break). Record any such incident in `.friday/active/harness/log.md`
so the rule's cost stays visible.
