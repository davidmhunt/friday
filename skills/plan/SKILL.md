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
2. **Write directives.** One directive per independently shippable result; most goals are one to
   three. Get ids from `friday new <loop>` (a loop is a short workstream name like `core` or
   `sar`). Write each to `docs/directives/<id>.md` in the format of the `directive` skill, with
   `Status: proposed`.
   - `Verify:` must be a command that exits 0 only when the directive's goal holds. Prefer the
     project's standard check plus a targeted test you name in the steps. A check that can only be
     done by a person at the bench is not a Verify command: set `Hardware:` and say so.
   - Tag a step `[heavy]` only when it needs deeper reasoning (a new algorithm, a numerical method,
     an architecture decision), with one line saying why.
   - Set `Node:` when the work needs a particular machine (`tag:gpu`, `tag:<board>`), else `any`.
3. **Ask for approval.** Show each directive's goal, steps, Verify and out-of-scope list in a few
   lines, and ask the user to approve, amend or drop each. On approval set `Status: approved` and
   commit the directive files (message ends `Directive: <id>`; plan commits may list several).
4. **Hand off.** For each approved directive, tell the user how it will run: in this repo,
   `/friday:execute <id>` (a workflow that implements, verifies, reviews and prepares a PR). Start
   it if the user said to go ahead.

Rules
- Never start implementation in this skill. Planning changes only `docs/directives/`.
- A directive is small enough when its Verify can be stated in one command and its steps fit on a
  screen. Split anything bigger.
- If the goal is a one-line fix, say so and offer to just do it instead of planning.
