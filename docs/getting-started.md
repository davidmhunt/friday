# Getting started

This page takes you from a fresh machine and an existing git repo to a landed goal. It needs no
other document. The model in one line: you plan a **goal** with Claude and approve it once, friday
executes its **directives** on a branch `friday/<goal>`, each finishing only when its `Verify:`
command passes and an independent reviewer agrees, and you review and merge one pull request.

## 1. Requirements

| Need | Why |
|---|---|
| Claude Code v2.1.154 or newer (`claude --version`) | friday's execute step is a Claude Code workflow |
| `uv` ([install](https://docs.astral.sh/uv/getting-started/installation/)) | friday runs its CLI and hooks on a uv-managed Python 3.12, so an old system Python does not matter; `friday install` fetches it |
| `git` | friday works on branches and commits in your repo |
| `gh`, signed in (`gh auth login`, check with `gh auth status`) | `friday land --goal` opens the pull request; without it the push still works and friday prints a compare URL |
| an `origin` remote on the repo, pushed to GitHub | the goal branch is pushed to it and the PR targets a branch on it |

Run Claude on a model such as Fable or Opus for the planning session.

## 2. Install the plugin

Clone the repo, add the clone as a local marketplace, install the plugin from it, then put
`friday` on your PATH:

```bash
git clone https://github.com/davidmhunt/friday ~/src/friday
```

```text
/plugin marketplace add ~/src/friday
/plugin install friday@friday
```

```bash
python3 ~/src/friday/bin/friday install      # once per machine: installs Python 3.12 into friday's private directory (not on PATH), records it, writes the ~/.local/bin/friday shim
friday --help                                # make sure ~/.local/bin is on PATH
```

To update, run `git pull` in the clone, then
`/plugin marketplace update friday`. `friday uninstall` removes the shim, the recorded Python and the private Python directory again.

If you installed a 1.2 pre-release, `friday install` had put uv's Python 3.12 on PATH and made other projects' `uv run` pick it. Undo that: remove `~/.local/bin/python3.12` if it links into uv's directory, run `uv python uninstall 3.12` if nothing else uses it, then run `friday install`.

Do not edit files in the clone while a session uses it; its hooks run from there.

## 3. Set up your repo

In the repo you want to work on, on its default branch with a clean tree:

```bash
friday init
```

`friday init` commits nothing. It writes:

- `.claude/settings.json` (tracked): merges in the allow rules for the `friday` commands, so an
  unattended `friday start` or `friday land` is not stopped by a permission prompt. A plugin
  cannot grant permissions, so these live in your repo. It never touches `settings.local.json`.
- `.git/hooks/commit-msg`: a git hook that, while a directive is active, refuses a commit whose
  message lacks a final `Directive: <id>` line. An existing hook of yours is kept as
  `commit-msg.local` and still runs first. `git commit --no-verify` bypasses it on purpose.

Then add, and commit, the project's own files:

- `CLAUDE.md`: facts about the project the model cannot infer from the code (how to build and
  test, layout, conventions), under about 60 lines. Plans are only as good as this file.
- `.claude/friday.json` (optional): the run wrapper, which tools must go through it, and
  `hardware` patterns for commands that touch a device. Without it friday applies only its deny
  list and guards. See [spec.md section 11](spec.md#11-project-config-claudefriday-json).
  ```json
  { "run_wrapper": "./run", "run_only": ["python", "uv", "pytest"] }
  ```
- `runs/` in `.gitignore`: a step that only measures or inspects writes its findings to the
  untracked `runs/<id>/notes.md`.

```bash
echo "runs/" >> .gitignore
git add .gitignore CLAUDE.md .claude && git commit -m "Set up friday"
git push origin HEAD
```

Make squash-merge the repo's default merge method, so each goal becomes one commit on your main
branch while the goal branch keeps its detail. friday never changes repo settings; you do:

```bash
gh repo edit --enable-squash-merge --enable-merge-commit=false --enable-rebase-merge=false
```

(or GitHub, Settings, General, Pull Requests).

## 4. Plan a goal

Start Claude Code in the repo with the plugin loaded and say what you want:

```text
/friday:plan add range-limit checks for chirp configs
```

The model reads the repo, interviews you about what it cannot settle (hard parts, what "done"
means, what is out of scope, whether hardware is involved), then writes `docs/goals/<goal>.md` and
one `docs/directives/<id>.md` per result, each `Status: proposed`, and runs `friday check` on them.
You never edit `Status:` yourself; commands write it.

A goal looks like this:

```markdown
# hello-notes: Add a notes file with a check
Status: proposed
Base: main
Land: pr

## Goal
The repo has NOTES.md and a check script that fails without it.

## Directives
1. note-01: Add NOTES.md and its check

## Log
```

and a directive like this:

```markdown
# note-01: Add NOTES.md and its check
Status: proposed
Goal: hello-notes
Node: any
Deliverable: code
Verify: test -f NOTES.md
Hardware: none

## Goal
NOTES.md exists at the repo root and says what the repo is for.

## Steps
1. Create NOTES.md with a one-paragraph description of the repo.

## Out of scope
- Any other file.

## Log
```

`Base` is the branch the goal's pull request targets. `Verify` is one shell command, run from the
repo root, that exits 0 only when the directive's goal holds. `Deliverable` is `code`, `doc`,
`slides` or `external`. Every field is in [spec.md section 2](spec.md#2-formats).

### Pre-approve commands before you approve

Some commands always prompt you: `friday dispatch`, `friday nodes --clean`, `friday release`, and
any command matching a `hardware` pattern. If nobody is at the prompt (a dispatched session, or a
run you walk away from) the session waits there. A directive lists the ones it needs, one command
per bullet in backticks with `*` matching any text, in an `## Allowed commands` section before
`## Log`:

```markdown
## Allowed commands
- `./run tools/bench.sh *`
- `ssh rover ./run ros2 topic list`
```

Without that list these commands prompt. The list applies only to that directive while it is
active, only to a single simple command (no `&`, `;`, `|`, backticks or `$(`), and never overrides
the deny list (privilege escalation, force-push, push to main) or `friday accept`. Keep each
pattern narrow. Decide this now: it is read from the plan as you publish it with `friday approve --goal <g>` (below).

### Approve

The model shows each directive's goal, steps, Verify and out-of-scope list, and shows each
`## Allowed commands` list verbatim. Check that list. Approving the plan approves those commands to
run without a prompt while the directive is active. Then approve, amend or drop each directive.
On approval the model sets the files to `Status: approved`, runs `friday check` and `friday init`
again, and commits the plan.

### Where the plan commit lands

The plan commit goes on the goal branch `friday/<goal>` (created from Base by the plan skill), never
on Base: agents do not commit to `main`. The model pushes the branch. When any directive has
`## Allowed commands`, **you publish the plan for pre-approval**:

```bash
friday approve --goal <g>
```

It runs `friday check --goal <g>`, refuses on errors or uncommitted tracked files, and pushes the
goal branch's current plan commit to `friday-plan/<g>` on origin (no force) and lists what is now
pre-approved. Execution reads `## Allowed commands` only from `origin/friday-plan/<g>`; agents
cannot push that ref or run `friday approve`. Without it, those commands prompt as usual.

Later amendments go on the goal branch too. To change an approved goal (a step, the Verify command,
an `## Allowed commands` list, a new directive), commit the change on `friday/<goal>`, run
`friday check`, push the branch, and run `friday approve --goal <g>` again if the allowed commands
changed. The same route extends a goal with related work while its PR is open: a goal is a
capability that can span several planning runs, and `/friday:plan` offers to add to an open goal (see
`friday status`) before opening a new one. `friday start` still merges Base into the goal branch for
upstream changes, and an amendment to the directive that is running takes effect when it restarts.
`friday land` needs Base on origin to open the PR.

## 5. Execute

```text
/friday:execute note-01
```

This runs a workflow in the background (watch it with `/workflows`). For each directive:

1. **Prepare**: `friday start` switches to `friday/<goal>` (created from Base the first time),
   merges Base in, and commits nothing.
2. **Implement**: one agent per step, in order; each step that changes tracked files is one commit
   ending in `Directive: <id>`.
3. **Verify**: the `Verify:` command runs; on failure an agent fixes the root cause and it runs
   again, up to 4 rounds.
4. **Review**: a read-only verifier on a stronger model checks the directive's commits against the
   directive, and real gaps get one fix round.
5. **Land**: `friday finish` writes the record (Status `done` and a Log entry, one commit), and the
   goal branch is pushed.

A goal with several directives runs them in order on the same branch: run `/friday:execute` for
each in turn. When the last directive is done (and all earlier ones are), friday opens the goal's
one pull request into Base by itself.

You can see where things stand with `friday status` (in a shell, or ask Claude to run it).

### A directive that needs your eyes

A directive with `Accept: user` (and a `## Review` section listing what to open and what to look
for) does not finish on its own. It ends `awaiting review`: the branch is pushed and later
directives continue. Open what `## Review` names, then type the command yourself (an agent cannot
run it). If you changed tracked files during the review (a fix, a re-route), accept refuses with
exit 8 and changes nothing: it lists the files and prints the
`git commit -am "<id>: review changes" -m "Directive: <id>"` to run first, which makes your work
part of the directive. Untracked files do not block it.

```bash
friday accept note-01                    # or: friday accept note-01 --reject "why"
friday land --goal hello-notes           # once every directive is done, to open the PR
```

## 6. Review and merge the PR

`friday land --goal <goal>` reruns every directive's Verify on the goal branch, marks the goal
`done`, pushes `friday/<goal>` and opens (or updates) the one PR into Base. It opens by itself at
the end of the last directive when that directive is `Accept: auto`; you run it yourself after
`friday accept`, or when a landing step stopped. Its output says which. If `gh` is missing or
signed out it prints a compare URL (exit 5) and you open the PR there.

Read the PR and merge it yourself. With squash-merge as the default, Base gets one commit for the
goal. Then `git switch main && git pull`.

## 7. When it stops

| It stops because | What you do |
|---|---|
| `Status: blocked: <reason>`: a hardware prompt, a decision the directive does not settle, or Verify still failing after the fix rounds | read the reason in the directive's Log, fix or answer it, run `friday unblock <id>` (back to `approved`, one commit), then `/friday:execute <id>` again. Work already committed stays. Never edit `Status:` by hand |
| `awaiting review` | open the `## Review` items, run `friday accept <id>` or `friday accept <id> --reject REASON`, then `friday land --goal <goal>` if the PR has not opened |
| `friday land --goal` exits non-zero | 3 push failed, 4 Base is not on origin (push it), 5 no PR was opened (open the printed compare URL), 6 a Verify failed, 7 a directive is not done; the output names it |
| a command waits at a prompt | that command is not in `.claude/settings.json` or the directive's `## Allowed commands`; answer it, or amend the plan on the goal branch to list it and run `friday approve --goal <g>` |

## 8. Where next

- Several machines, or a GPU or robot host: [fleet.md](fleet.md) (`friday dispatch --goal`).
- A page that shows every machine and goal: [dashboard.md](dashboard.md) (`friday dash`).
- Every command, field and exit code: [spec.md](spec.md). The shorter walkthrough:
  [workflow.md](workflow.md).
