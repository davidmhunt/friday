# thin-targets: Targets stay thin: pre-approved tag pushes, target scope checks, cheap worker setup
Status: done
Base: main
Land: pr

## Goal
Issues #24 and #23 from console's fleet onboarding. A push the approved plan lists (a robot's
known-good tag) runs instead of blocking, and `friday check` catches a listed push the guard would
always refuse. Target directives stay a small, fixed set of things: `friday check` warns on raw
remote globs and builds over ssh, the plan skill routes iterative robot work to a worker goal
(`Node: host:<robot>`), and `friday nodes --setup <node>` reports every prerequisite a worker needs
with its fix command, including for a node that is a target today. docs/fleet.md explains target
vs worker and gives a reusable read-only probe recipe.

Asked for by the user on 2026-11-18 ("A few more issues came up. Go ahead and address them
overnight"); the design follows the proposals in the two issues. The issue's fallback (classifying
remote commands, a per-robot deny list) is out of scope. #13 and #20 stay later goals.

tt-04 added and approved by the user on 2026-11-19 ("I like the default of agents always
working in a branch so that this can work more smoothly and also to protect the main branches").
tt-05 (#25) and tt-06/tt-07 (#27) added on 2026-11-19 at the user's request ("I also just filed
another issue with the harness that I'd like to get addressed, can you handle that as well"); #25
was hit by this goal itself (tt-04 had to be merged in by hand).

## Directives
1. tt-01: A pre-approved tag push runs while a directive is active; `friday check` errors on a listed push the guard always denies (fixes #24)
2. tt-02: Target directives stay thin: `friday check` warns on raw remote globs and remote builds; the plan skill routes iterative robot work to workers
3. tt-03: `friday nodes --setup <node>` reports each worker prerequisite with its fix, also for a target being promoted (fixes #23)
4. tt-04: Plans live on the goal branch; pre-approval trusts a plan ref only the user's `friday approve` pushes
5. tt-05: `friday start` merges Base first when the directive is only there, and keeps the goal branch's Status lines (fixes #25)
6. tt-06: Rules for the whole directive reach every agent: a `## Rules` section on directives and goals (fixes #27)
7. tt-07: Opt-in `bash_file_io: "deny"` hook rule sends file reads and writes to the file tools; `run_only` ignores quoted text (fixes #27)

## Log
- 2026-11-19: Landed: 3 directive(s) reverified on friday/thin-targets; PR into main.
- 2026-11-19: Landed: 4 directive(s) reverified on friday/thin-targets; PR into main.
- 2026-11-19: Landed: 7 directive(s) reverified on friday/thin-targets; PR into main.
