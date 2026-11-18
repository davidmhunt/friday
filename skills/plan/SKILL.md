---
name: plan
description: Turn a goal into approved friday directives. Use when the user states a goal or asks to plan work in a repo that uses friday (it has docs/directives/ or .claude/friday.json), before any code changes.
argument-hint: "<goal>"
---

# Plan a goal into directives

You are the planning session: the user's single point of contact. Nothing is executed until the
user approves the plan.

1. **Understand the goal.** Read `CLAUDE.md`, the relevant code, and `friday status`. Then
   interview the user with AskUserQuestion about what you cannot settle from the repo: the hard
   parts, edge cases, what "done" means, what is out of scope, and whether hardware is involved.
   Skip obvious questions. Keep going until you could defend every step.
2. **Write the goal and its directives.** A goal is one planning run, one branch `friday/<goal>`
   and one PR. Write `docs/goals/<goal>.md` (format in the `directive` skill) with
   `Status: proposed`, then one file per independently shippable result in
   `docs/directives/<id>.md`, also `Status: proposed`, each with `Goal: <goal>`. Most goals are one
   to three directives. Get ids from `friday new <loop>` (a loop is a short workstream name like
   `core` or `sar`); list the directives in the goal's `## Directives` section in run order.
   - `Verify:` must be a command that exits 0 only when the directive's goal holds. Prefer the
     project's standard check plus a targeted test you name in the steps. A check that can only be
     done by a person at the bench is not a Verify command: set `Hardware:` and say so.
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
   - Set `Node:` when the work needs a particular machine (`tag:gpu`, `tag:<board>`), else `any`.
3. **Check the format.** Run `friday check --goal <goal>` and fix every error before asking for
   approval. Do not show the user files that do not pass.
4. **Ask for approval.** Show the goal and each directive's goal, steps, Verify and out-of-scope
   list in a few lines, and ask the user to approve, amend or drop each. On approval set the goal
   and its directives to `Status: approved`, re-run `friday check --goal <goal>`, run `friday init`
   (it merges the friday allow rules into `.claude/settings.json`; it does not commit), and commit
   the plan, adding `.claude/settings.json` when `friday init` changed it (message ends `Directive: <id>`; the plan commit may list several). If this machine does not
   satisfy the directives' `Node:` lines, offer to run the goal elsewhere with
   `friday dispatch --goal <goal>` (see docs/fleet.md) instead of `/friday:execute` here.
   Amending an approved goal later: make the change as a commit on its Base (not on `friday/<goal>`),
   check it with `friday check --goal <goal>`, and tell the user. A running goal picks it up at the
   next `friday start`, which merges Base into the goal branch; an amendment to the running
   directive takes effect when that directive restarts.
5. **Hand off.** Tell the user how it runs: `/friday:execute <id>` for each directive, in order
   (a workflow that implements, verifies and reviews on the goal branch; the goal lands as one PR
   with `friday land --goal <goal>`). Start the first if the user said to go ahead.

Rules
- Never start implementation in this skill. Planning changes only `docs/goals/` and `docs/directives/`.
- A directive is small enough when its Verify can be stated in one command and its steps fit on a
  screen. Split anything bigger.
- If the goal is a one-line fix, say so and offer to just do it instead of planning.
