# Recipe: a research repo

Experiments, long GPU runs, datasets and a paper, with the same model as
[getting-started.md](../getting-started.md): a goal, its directives, one `Verify:` each, one PR.
Read that page first. This one only adds what research work needs.

## The shape of a research goal

Three things make research different from code: a run is expensive, its output is data that must
be traceable, and the last deliverable is a document a person judges.

- **Run once, check cheaply.** A training run or sweep takes hours. `Verify:` is re-run in fix
  rounds and again at landing, so it must not repeat the run. A step runs the experiment once and
  records it with `friday result write`; `Verify:` is `friday result check`, which only reads the
  record.
- **Provenance.** `friday result write` stores `results/<id>.json`, tracked in git: the metrics,
  the command, the commit, whether the tree was dirty, the node and each recorded file's `sha256`
  and size. `friday result check <id> --files` fails if a recorded file has changed since.
- **A GPU node.** `Node: tag:gpu` routes the directive to a node whose tags in the fleet registry
  include `gpu`; `friday dispatch --goal <goal>` starts the goal there. See
  [fleet.md](../fleet.md) for adding the node.
- **A paper is a deliverable.** `Deliverable: doc` with `Accept: user` ends `awaiting review` for
  you to read; an agent never accepts it.

## Recording a run

Inside a step, after the run finishes:

```bash
friday result write train-01 \
  --metric accuracy=0.912 --metric loss=0.31 \
  --file outputs/model.pt --file outputs/metrics.json \
  --cmd "./run python train.py --config configs/base.yaml" \
  --note "seed 0, 40 epochs"
git add results/train-01.json && git commit -m "Record train-01 run

Directive: train-01"
```

Large files do not belong in git: record the file (its hash proves it), keep it in your artifact
store, and list its location in the directive's `## Goal` or the note. Then:

```bash
friday result check train-01 --require 'accuracy >= 0.9' --files
```

exits 0 when the record exists, its commit is an ancestor of HEAD, the accuracy holds and every
recorded file still hashes the same. `--require` takes `>= > <= < == !=`; give it several times.
The metric value must come from the run, not from the step: the step writes the numbers the
script printed, and the reviewer compares them with the log.

## Datasets

A dataset is an input, so pin it. Either commit a small manifest (`data/MANIFEST.sha256`) or record
the dataset files in the result with `--file`, so the same record that proves the accuracy also
names the exact data. A directive that prepares data (`data-01`) records the prepared files; the
training directive's `## Steps` starts with `sha256sum -c data/MANIFEST.sha256`, so a changed
dataset stops the run instead of producing an unexplained number.

## A long run on a GPU node

Put the run in its own directive with `Node: tag:gpu`. Dispatch the goal from the master:

```bash
friday dispatch --goal sweep-lr --dry-run     # shows the node, changes nothing
friday dispatch --goal sweep-lr
```

`friday dispatch` always prompts you, because it starts a session on another machine. Directives
that must run without anybody at a prompt list what they need under `## Allowed commands`
(see getting-started, "Pre-approve commands before you approve"). The commands the training step
runs on the node (`./run python train.py ...`) are ordinary commands and need no entry unless your
`.claude/friday.json` marks them as `hardware`. If a long command does match a `hardware` pattern,
pre-approve that exact command. The session messages your master session when the goal lands or a
directive blocks; `friday status` shows where it is.

A dispatched goal runs on one node and cannot move to another. Put every directive that needs
the GPU in the same goal.

## The paper

Write the paper as a directive after the experiments, so it cites recorded numbers:

- `Deliverable: doc`, `Accept: user`, `Verify:` a command that builds it (`make -C paper`).
- `## Acceptance` lists checkable statements the verifier grades: every number in a table matches
  a `results/*.json` metric, every figure has a script, the bibliography builds with no
  undefined citations.
- `## Review` lists what you open: the built PDF, the sections that carry claims, the tables to
  compare with the result records. You judge the writing; friday only checks that it builds.

## Complete example: a learning-rate study with a report

The goal has two directives: one run on the GPU node, then the report. Put these under
`docs/goals/` and `docs/directives/` and run `friday check`.

`docs/goals/lr-study.md`:

```markdown
# lr-study: Does a lower learning rate reach 90 percent accuracy?
Status: proposed
Base: main
Land: pr

## Goal
One recorded training run of the baseline model with learning rate 1e-4 reaches at least 0.90
validation accuracy, and a short report states the result with the recorded numbers.

## Directives
1. train-01: Train the baseline at learning rate 1e-4 and record the run
2. report-01: Write the report from the recorded run

## Log
```

`docs/directives/train-01.md`:

```markdown
# train-01: Train the baseline at learning rate 1e-4 and record the run
Status: proposed
Goal: lr-study
Node: tag:gpu
Deliverable: code
Verify: friday result check train-01 --require 'accuracy >= 0.90' --files
Hardware: none

## Goal
`results/train-01.json` records one run of `train.py` at learning rate 1e-4 on the pinned
dataset, with accuracy at least 0.90, and the recorded model and metrics files are unchanged.

## Steps
1. Check the dataset: `sha256sum -c data/MANIFEST.sha256`. Stop and report if it fails.
2. Run `./run python train.py --config configs/lr1e-4.yaml` once. It writes
   `outputs/model.pt` and `outputs/metrics.json`.
3. Record it with `friday result write train-01 --metric accuracy=<value> --file outputs/model.pt
   --file outputs/metrics.json --cmd "./run python train.py --config configs/lr1e-4.yaml"`, using
   the accuracy that `outputs/metrics.json` reports, and commit `results/train-01.json`.

## Out of scope
- Changing `train.py`, the dataset or any other config.
- Running the training a second time to improve the number.

## Log
```

`docs/directives/report-01.md`:

```markdown
# report-01: Write the report from the recorded run
Status: proposed
Goal: lr-study
Node: any
Deliverable: doc
Accept: user
Verify: make -C paper
Hardware: none

## Goal
`paper/report.tex` states the learning-rate result with numbers taken from
`results/train-01.json`, and `make -C paper` builds `paper/report.pdf`.

## Steps
1. Write `paper/report.tex`: setup, the result table, a short discussion.
2. Take every number from `results/train-01.json`; do not retype it from memory.
3. Run `make -C paper` and fix any LaTeX or citation errors.

## Acceptance
- The accuracy in the report equals the `accuracy` metric in `results/train-01.json`.
- The report names the command and the commit recorded in that file.
- `make -C paper` finishes with no undefined references or citations.

## Review
- Open `paper/report.pdf`: read the discussion and decide whether the claim is worded as strongly
  as one run allows.
- Compare the result table with `results/train-01.json`.

## Out of scope
- New experiments, and any file outside `paper/`.

## Log
```

Plan it with `/friday:plan`, approve, push Base, then `friday dispatch --goal lr-study` from the
master. When `report-01` reaches `awaiting review`, open the items under `## Review` and run
`friday accept report-01` yourself, then `friday land --goal lr-study` if the PR did not open.
