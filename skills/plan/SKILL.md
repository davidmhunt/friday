---
name: plan
description: Turn a goal into approved friday directives. Use when the user states a goal or asks to plan work in a repo that uses friday (it has docs/directives/ or .claude/friday.json), before any code changes.
argument-hint: "<goal>"
---

# Plan a goal into directives

You are the planning session: the user's single point of contact. Nothing is executed until the
user approves the plan.

1. **Find open goals.** Run `friday status --json` and list the goals that are not `done`, plus
   `done` goals whose PR is still open (`pr: open`). Those are the open goals. Related work,
   follow-ups, hardening and small fixes extend one of them: add directives to that goal as an amendment
   on its goal branch (see step 5) instead of opening a new goal and PR. Propose a new goal only for
   unrelated work, and say why no open goal fits. A small fix with no open goal: offer to just do
   it (one-line fixes), or to start a goal broad enough to take more related work.
2. **Understand the goal.** Read `CLAUDE.md`, the relevant code, and `friday status`. Then
   interview the user with AskUserQuestion about what you cannot settle from the repo: the hard
   parts, edge cases, what "done" means, what is out of scope, and whether hardware is involved.
   Skip obvious questions. Keep going until you could defend every step.
3. **Write the goal and its directives.** A goal is one user-visible capability, typically 3 to
   10 directives, with one branch `friday/<goal>` and one PR; directives are its reviewable units,
   landing as commits on the goal branch. A goal may span several planning runs. For a new goal
   write `docs/goals/<goal>.md` (format in the `directive` skill) with `Status: proposed`; for an
   extension, add the new ids to the existing goal's `## Directives` section. Then write one file
   per independently shippable result in `docs/directives/<id>.md`, also `Status: proposed`, each
   with `Goal: <goal>`. Get ids from `friday new <loop>` (a loop is a short workstream name like
   `core` or `sar`); list the directives in the goal's `## Directives` section in run order.
   - `Verify:` must be a command that exits 0 only when the directive's goal holds. Prefer the
     project's standard check plus a targeted test you name in the steps. A check that can only be
     done by a person at the bench is not a Verify command: set `Hardware:` and say so.
   - For an expensive or hardware run (training, sweep, bench test), do not put the run in `Verify:`:
     it is re-run unattended at every fix round and at landing, without the hardware prompt, and
     `friday check` warns when it matches a `hardware` pattern. Make the run a step that ends with
     `friday result write <id> ...`, and set `Verify:` to `friday result check <id> --require 'K OP V' --files`
     plus the project's cheap tests.
   - Pick `Deliverable:` per directive: `code` (build + tests), `doc` (LaTeX or markdown report),
     `slides` (source in the repo, built PDF) or `external` (Google Slides, Claude Docs: use
     `Verify: none` and `Land: none`).
   - For `doc`, `slides` and `external`, write `## Acceptance`: bullets, each a checkable statement
     a reviewer can grade against the deliverable (sections present, figures regenerate, claims
     sourced, audience and length). It is required for those types and needs at least one `- ` bullet.
   - `Accept: user` (default `auto`) makes the goal wait for the user: the directive ends
     `awaiting review` and only the user's `friday accept <id>` marks it `done`. Use it where a person
     must look at the result, always for `external`. It requires `## Review`: bullets saying what to
     open and what to look for.
   - Tag a step `[heavy]` only when it needs deeper reasoning (a new algorithm, a numerical method,
     an architecture decision), with one line saying why.
   - `## Rules` (optional section, before `## Log`): `- ` bullets for constraints that hold for the
     whole directive. Never bury one in a single step's text, since other steps' implementers would
     not see it. Rules for every directive of the goal go in the goal file's `## Rules`; repo-wide
     ones in `.claude/friday.json` `"rules": [...]`. Every agent of the run gets them, and the
     reviewer treats a broken rule as a gap.
   - `## Allowed commands` (optional section, before `## Log`): list every command the directive
     needs that would otherwise prompt and nobody will be there to answer: `friday dispatch --goal *`,
     `friday nodes --clean *`, `friday release *`, hardware commands, `ssh <robot> ...`. One bullet
     per command, the command in backticks, `*` matching any text, e.g. ``- `friday dispatch --goal *` ``.
     Also list the read-only helpers the directive's batches need (`grep *`, `cat runs/*`): a
     batch of lines is pre-approved only when every command in it matches a listed pattern, and
     nothing is treated as harmless unless listed. Keep each pattern as narrow as possible. No chained commands (`&&`, `;`, `|`), never
     `friday accept <id>`; `friday check` rejects those. Omit the section if nothing is needed.
   - Set `Node:` when the work needs a particular machine (`tag:gpu`, `tag:<board>`), else `any`.
   - Keep a target directive thin. One that drives a device over ssh from the node running it
     runs named, reviewed project scripts (a read-only probe, one smoke test) and single-purpose
     writes the user approves one by one (a tag, a file copy). Never list `ssh <robot> *`, a
     remote `bash -c *` or a remote build or install under `## Allowed commands`; `friday check`
     warns on them. When steps need iteration on a robot (debugging, building, editing its
     checkout, hardware tests), propose a worker goal with `Node: host:<robot>` instead, run by
     the robot's own session (the user sets the robot up as a worker first if it is not one yet, per
     "Targets and workers" in docs/fleet.md), and say so in the approval summary.
4. **Check the format.** Run `friday check --goal <goal>` and fix every error before asking for
   approval. Do not show the user files that do not pass.
5. **Ask for approval.** State which open goal is extended, or why a new one is needed. Show the goal and each directive's goal, steps, Verify and out-of-scope
   list in a few lines. Show each directive's `## Allowed commands` verbatim (helpers such as `grep *` included), since approving the
   plan approves those commands to run without a prompt while that directive is active; say so
   explicitly. If robot work was routed to a worker goal (`Node: host:<robot>`) instead of a target directive, say so. Then ask the user to approve, amend or drop each. On approval set the goal
   and its directives to `Status: approved`, re-run `friday check --goal <goal>`, run `friday init`
   (it merges the friday allow rules into `.claude/settings.json`; it does not commit), and commit
   the plan **on the goal branch `friday/<goal>`, never on Base** (create it from Base with
   `git switch -c friday/<goal>` when it does not exist; main stays protected), adding `.claude/settings.json` when `friday init` changed it (message ends `Directive: <id>`; the plan commit may list several), and push the branch
   (`git push -u origin friday/<goal>`). When any directive has `## Allowed commands`, tell the user to
   run `! friday approve --goal <goal>`: only the user's command publishes the plan to
   `origin/friday-plan/<goal>`, the copy pre-approval trusts; until then those commands prompt (`friday start` and `friday status` say so). If this machine does not
   satisfy the directives' `Node:` lines, offer to run the goal elsewhere with
   `friday dispatch --goal <goal>` (see docs/fleet.md) instead of `/friday:execute` here.
   Extending or amending an approved goal later: make the change as a commit on `friday/<goal>` (never on Base),
   check it with `friday check --goal <goal>`, push the branch, and tell the user. When the change
   touches `## Allowed commands`, ask the user to run `! friday approve --goal <goal>` again, since
   the published copy does not follow the branch. An amendment to the running directive takes
   effect when that directive restarts.
6. **Hand off.** Tell the user how it runs: `/friday:execute <id>` for each directive, in order
   (a workflow that implements, verifies and reviews on the goal branch; the goal lands as one PR
   with `friday land --goal <goal>`). Start the first if the user said to go ahead.

Rules
- Never start implementation in this skill. Planning commits only on `friday/<goal>`, never on Base, and changes only `docs/goals/`, `docs/directives/` and, through `friday init`, `.claude/settings.json`.
- A directive is small enough when its Verify can be stated in one command and its steps fit on a
  screen. Split anything bigger.
- If the goal is a one-line fix, say so and offer to just do it instead of planning.
