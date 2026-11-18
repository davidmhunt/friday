---
name: directive
description: The friday goal and directive file formats (docs/goals/<goal>.md, docs/directives/<id>.md) exactly as `friday check` enforces them, the lifecycle on the goal branch, and the deliverable table (code, doc, slides, external). Use when reading, writing or updating a goal or directive.
user-invocable: false
---

# Goal and directive formats

A goal is one planning run: one branch `friday/<goal>` and one PR into its Base. It lists
directives, each one an independently verified chunk of work. Both are tracked in git and are the
record of why a change was made, so keep them accurate. `friday check [<id> | --goal <g> | --all]`
validates them (exit 1 on any error; warnings do not fail). Fix every error before asking for
approval.

## Directive: `docs/directives/<id>.md`

```markdown
# core-03: Reject cfgs whose chirp range exceeds the board limit
Status: proposed
Goal: board-limits
Node: any
Deliverable: code
Land: goal
Verify: ./run tools/check.sh && ./run uv run pytest tests/test_cfg_limits.py -q
Hardware: none

## Goal
One or two sentences: the result, and how a reader can tell it holds.

## Steps
1. ... (name files and interfaces)
2. [heavy] ... Heavy because: a new numerical method.

## Acceptance
- (required for doc, slides, external) a checkable statement about the deliverable.

## Review
- (required with `Accept: user`) what the user should open and what to look for.

## Out of scope
- ...

## Log
(execution appends here: commits, Verify results, verifier verdict, PR link, blockers)
```

First line: `# <id>: <title>`. The id must equal the filename stem, match
`^[a-z0-9][a-z0-9_-]*-\d{2,}$` (e.g. `core-03`), and the title must be non-empty. Error otherwise.

Header lines are `Key: value` lines between the title and the first `## `. Backticks around a
value are stripped. Each key once (a duplicate is an error); an unknown key is a **warning**.

| Key | Required | Allowed values (error otherwise) |
|---|---|---|
| Status | yes | `proposed`, `approved`, `running@<host>`, `done`, `awaiting review`, `blocked: <reason>` (non-empty reason) |
| Goal | yes | a goal name: `^[a-z0-9][a-z0-9-]*$` |
| Node | yes | `any`, `tag:<x>`, `host:<x>` |
| Deliverable | yes | `code`, `doc`, `slides`, `external` |
| Land | no (default `goal`) | `goal`, `pr`, `none` |
| Accept | no (default `auto`) | `auto`, `user`: with `user` the directive ends `awaiting review` and only the user's `friday accept <id>` makes it `done` |
| Verify | yes | one shell command, run from the repo root; must not be empty |
| Hardware | yes | any text: `none`, or the resources touched (hardware commands always ask the user) |

Rules that tie keys together (errors): for `Deliverable: external`, `Verify` must be `none` and
`Land` must be `none` (an omitted Land defaults to `goal` and so fails). `external` should use `Accept: user` (a warning
otherwise). `Accept: user` requires `## Review` with at least one `- ` bullet (an error otherwise).

Sections (`## `; fenced code blocks are not scanned): `Goal`, `Steps`, `Out of scope`, `Log` are
required, once each, in that order, and `## Log` must be last. Missing, duplicated, out of order, or
anything after `## Log` is an error. `## Acceptance` is optional for `code`, appears at most once,
and may go anywhere before `## Log`. For `doc`, `slides` and `external` it is required and needs at
least one `- ` bullet (a bullet may continue on indented lines); missing or empty is an error.
Other sections are allowed before `## Log`.

`## Allowed commands` is optional (at most once, before `## Log`): bullets, each holding one
backticked command pattern where `*` matches any text. While the directive is active in a
worktree, the PreToolUse hook allows a Bash command that is one simple command matching a
pattern, without a prompt. The list is read from the directive as committed on the goal's Base on
origin (`git show origin/<Base>:docs/directives/<id>.md`), the plan the user approved, so edits on
the goal branch never widen it. Base is trusted only when the goal file on `origin/<Base>` names the
same Base, and never when it is the goal branch or a `friday/*` branch. Deny rules, the commit guard, `friday accept <id>` and hardware leases still
win. `friday check` errors on a pattern that is only `*`, contains `&&`, `;`, `|` or a backtick
substitution, starts with `friday accept <id>`, or matches the hook's deny list. `friday parse --json`
returns it as `allowed`.

`## Steps` is a numbered list `1.`, `2.`, ... with no gaps, in order; indented lines continue an item.
Any other non-blank, unindented line in the section is an error, and so is an empty list. A step
needing deeper reasoning carries `[heavy]` (a `[heavy]` inside an inline code span is only a
mention) and must contain `Heavy because:` with the reason; a `[heavy]` step without it is an error.

Cross-checks against the goal file:
- error: the directive's `Goal:` file does not exist, or does not list this directive.
- warning: this directive is `done` while an earlier directive in its goal is not.
- warning: this directive is `approved` while its goal is still `proposed`.

## Goal: `docs/goals/<goal>.md`

```markdown
# board-limits: Enforce board limits in cfg validation
Status: proposed
Base: main
Land: pr

## Goal
What the goal delivers and how a reader can tell it holds.

## Directives
1. core-03: Reject cfgs whose chirp range exceeds the board limit
2. core-04: Document the limits

## Log
```

First line `# <goal>: <title>`: the goal name equals the filename stem, matches
`^[a-z0-9][a-z0-9-]*$`, has a non-empty title, and must not look like a directive id (it would
collide with the branch `friday/<id>`). Error otherwise.

| Key | Required | Allowed values (error otherwise) |
|---|---|---|
| Status | yes | `proposed`, `approved`, `running`, `done`, `blocked: <reason>` (a goal is not `running@<host>`) |
| Base | yes | the branch the PR targets; must not be empty |
| Land | yes | `pr`, `none` |

Each key once (duplicate is an error). Unknown goal headers are ignored, with no warning.

Sections: `Goal`, `Directives`, `Log` required, once each, in that order, `## Log` last. Other
sections are allowed between them or after `## Directives`; the validator does not restrict them
(including `## Acceptance`). `## Directives` is a numbered list `1.`, `2.`, ... with no gaps; each item starts
with a directive id, optionally followed by `: <text>`. An id listed twice, a bad id, a stray
unindented line, or an empty list is an error. List directives in run order.

Cross-check (error): every listed id must have `docs/directives/<id>.md`, and that file's `Goal:`
must name this goal.

## Lifecycle

- Status: `proposed` -> `approved` (only the user approves) -> `done`, or `blocked: <reason>`.
  While a directive runs its file keeps `Status: approved`; `friday start <id>` commits nothing
  and records id, host, start time and `base` (the HEAD after the branch switch) in the local
  marker, and `friday status` shows `running@<host>` from that marker. (Old files may still hold
  `running@<host>`; it validates.) The goal goes `proposed` -> `approved` -> `running` -> `done`;
  `start` makes the goal's first `approved -> running` edit uncommitted, and the finish commit
  carries it. Never edit a directive's Status or Log by hand.
- `friday finish <id> [--verify TEXT] [--review TEXT] [--base SHA] [--blocked REASON]` writes the
  record: one dated Log entry (`Commits:` from `git log <base>..HEAD`, `Notes:` from
  `runs/<id>/notes.md`, `Verify:` line, `Independent review:` line, `Blocked:` with `--blocked`),
  sets Status `done` or `blocked: <reason>`, and makes ONE commit `<id>: record results` (or
  `<id>: blocked`) with the directive and goal files. It refuses when other tracked files are
  uncommitted, and without a base (`--base`, else the marker's). It clears the marker.
- `Accept: user`: after Verify and the independent review `friday finish <id>` writes
  `Status: awaiting review`, prints the `## Review` bullets and the accept command, and the goal
  branch is pushed; later directives still run (`start` treats awaiting review as finished for order).
  `friday accept <id> [--note TEXT | --reject REASON]` (the user only; a hook denies it for agents)
  appends `Accepted by user: <date> <note>` and sets `done` (or `blocked: <reason>`) in one commit on
  the goal branch. It exits 8, changing nothing, while tracked files are uncommitted (it prints the
  `git commit -am` to run first). `friday land --goal` exits 7 naming directives still awaiting review.
- A directive adds exactly one bookkeeping commit: the finish record. Steps commit only when they
  changed tracked files (code, docs, data, configs); a step that only reproduces, measures or
  inspects appends findings to the untracked `runs/<id>/notes.md` and commits nothing.
- Directives run in listed order; `friday start <id>` refuses one while an earlier directive of its
  goal is not done.
- Work happens on the goal branch `friday/<goal>` (created from the goal's Base). A directive with
  `Land: goal` commits there. `Land: pr` puts that directive on its own branch `friday/<id>` and
  its own PR. `Land: none` (external) lands nothing.
- Every commit made for a directive ends with the line `Directive: <id>` (a hook checks this while
  it is active); `friday commits <id>` lists them, and any `untracked` line (a commit with no
  trailer that touches more than plan docs) is a review gap. Never commit to main.
- `friday land --goal <goal>` re-runs every directive's Verify on the goal branch, marks the goal
  done and opens the one PR into Base (exit 6 when a Verify fails; nothing is pushed).
- A Stop hook keeps the active directive from ending until its Verify passes; a PostToolUse hook
  runs the format check after edits to goal and directive files.
- Amending an approved goal: commit the change on its Base and check it with `friday check`. The
  next `friday start` merges Base into the goal branch (message `Merge <Base> into friday/<goal>
  before <id>`, trailer `Directive: <id>`; a conflict aborts the merge and start exits non-zero).
  An amendment to the running directive takes effect when it restarts. While a directive is active
  a `commit-msg` git hook installed by `friday init`/`friday start` refuses commits without
  `Directive: <id>` (`git commit --no-verify` overrides deliberately).
- Changing scope: anything that alters Goal, Steps, Verify, Acceptance or Out of scope goes back to
  the user, then gets a dated line in the Log.

## Deliverable types

| Deliverable | Source and output | Verify | Land | Log line |
|---|---|---|---|---|
| `code` | code and tests in the repo | build + tests | `goal` (or `pr`) | commits, Verify result |
| `doc` (LaTeX, markdown reports) | source in the repo; built PDF or rendered report | build with no undefined refs, bibliography resolves, figures regenerate from scripts | `goal` | commits, Verify result; the built file's path if you name it in a note |
| `slides` | prefer source in the repo: Beamer, Marp, or python-pptx built from results and figures; built PDF in `runs/<id>/` | build, no overflowing text, every figure produced in the repo | `goal` | commits, Verify result; the PDF is in `runs/<id>/` |
| `external` (Google Slides, Claude Docs) | lives outside the repo | `none` | `none` | the link, in a step note; the verifier grades `## Acceptance`, then the user reviews |

`doc`, `slides` and `external` need `## Acceptance` (see above): each bullet is a statement a
reviewer can grade against the deliverable (sections present, figures regenerate, claims sourced,
audience and length).
