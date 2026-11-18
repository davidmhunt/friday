# review-01: `friday commits <id>` is the directive's change set; review and finish use it
Status: approved
Goal: review-range
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_directive_commits.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
`friday commits <id>` lists the directive's own commits: commits on the goal branch since it left
its Base (`git merge-base <Base> HEAD`), not merges, whose message has the line `Directive: <id>`.
It survives restarts, `friday unblock` and merging Base into the goal branch. Plan-only commits
(touching only `docs/goals/` and `docs/directives/`) and other directives' commits are never
counted against it; a commit with no `Directive:` line that touches anything else is listed as
untracked so the review can flag it. `friday finish` and both review prompts in
workflows/execute.js use it. tests/test_directive_commits.py proves each case.

## Steps
1. lib/friday_core.py: `directive_commits(root, id)` returning `{"base", "commits": [(sha,
   subject)], "untracked": [(sha, subject, files)]}`. Base is the merge-base of the goal's Base
   (local branch, else `origin/<Base>`) and HEAD; for `Land: pr` directives, the same with
   `friday/<id>`. Exclude merge commits and friday's own record commits (`<id>: blocked`,
   `<id>: unblock`, `<id>: record results`, `<id>: accepted`) from `commits`. `untracked` holds
   non-merge commits in the range with no `Directive:` line whose files are not all under
   `docs/goals/` or `docs/directives/`.
2. `friday commits <id> [--json]` in bin/friday: prints `base <sha>`, then one line per commit,
   then `untracked <sha> <subject>` lines; exits 0 with commits, 3 when the directive has none,
   2 on a git or parse error. Add it to the help text, the parser, and `FRIDAY_ALLOW`
   (`Bash(friday commits *)`), and to this repo's `.claude/settings.json`.
3. `friday finish <id>`: the Log's `Commits:` list comes from `directive_commits` (keep `--base`
   as an override). `friday start` still prints `base <sha>`, now the merge-base, so the Stop gate
   and old callers keep working.
4. workflows/execute.js: both review prompts run `friday commits ${id}` (alone, per `ALONE`) and
   review each listed commit with `git show <sha>` plus the current state of the files they
   touch. Replace the "every commit message must contain `Directive:`" rule with: any `untracked`
   line is a gap. Drop `review_base` from the start step's schema if nothing else reads it.
   agents/verifier.md and skills/directive/SKILL.md say the same.
5. tests/test_directive_commits.py, on a temp repo with a goal branch: commits interleaved with
   another directive's are split correctly; a plan-only commit with no trailer is excluded and not
   untracked; an untagged code commit is untracked; `finish --blocked`, `unblock`, then more
   commits keep the earlier ones; merging Base into the goal branch keeps them and adds no
   untracked line; finish's Log lists only the directive's commits; exit codes 0, 3, 2;
   tests/test_execute_prompts.py still passes and no prompt mentions `reviewBase`. CHANGELOG entry
   under Unreleased/Fixed naming the fix-02 symptom.

## Out of scope
- Rewriting history on any branch.
- The v1-final directives themselves; v1-final takes this by merging v1 into its goal branch.

## Log
