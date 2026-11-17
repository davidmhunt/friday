# The friday workflow

You approve once per goal; every directive finishes only when its `Verify:` command passes and an
independent verifier finds no gaps. You review PRs, not steps.

1. **Plan.** `/friday:plan <goal>` in a session on Fable or Opus. It reads the repo, interviews
   you, and writes directives to `docs/directives/<loop>-<NN>.md` with `Status: proposed`.
2. **Approve.** Read each directive's goal, steps, Verify and out-of-scope list; approve, amend or
   drop. Approved directives are committed with `Status: approved`.
3. **Execute.** `/friday:execute <id>` runs a workflow in the background (watch it with
   `/workflows`):
   - **Prepare**: switch to branch `friday/<id>`, `friday start <id>`.
   - **Implement**: one `implementer` per step, in order; `[heavy]` steps run on Opus.
   - **Verify**: the `runner` runs the Verify command; on failure an implementer fixes the root
     cause and it runs again, up to 4 rounds or until the same failure repeats twice.
   - **Review**: the `verifier` (Opus, read-only, fresh context) checks the diff against the
     directive; real gaps get one fix round, then Verify and review again.
   - **Land**: Log entry, `friday finish <id>`, push the branch, open a PR with `gh` if it is
     signed in.
4. **Review the PR** and merge it yourself.

## When it stops for you

- A hardware command (prompt from the hardware hook).
- A step needs a decision the directive doesn't settle.
- Verify keeps failing, or review gaps remain after a fix round.

In each case the directive gets `Status: blocked: <reason>` and a Log entry. Fix or answer, set it
back to `approved`, and run `/friday:execute <id>` again; work already committed on the branch stays.

## Without the workflow

For hands-on work (a bench session), run a directive in the session itself:
`friday start <id>`, work, `friday finish <id>`. While a directive is active in a worktree, the Stop
hook runs its Verify command whenever Claude tries to end a turn and sends it back to work if it
fails (up to 3 times, then it stops for you). `friday start <id> --no-gate` turns that off.

## Hooks

| Hook | Event | Effect |
|---|---|---|
| Deny list | PreToolUse, Bash | Refuses sudo, unscoped `rm -rf`, force-push, push to main, `git remote add`, `curl \| sh`, raw disk writes |
| `./run` | PreToolUse, Bash | With `.claude/friday.json`, refuses bare `python`, `uv`, `cmake`, ... and names the `./run` form |
| Commits | PreToolUse, Bash | While a directive is active: commits need a `Directive: <id>` line and never land on main |
| Hardware | PreToolUse, Bash | Commands matching `hardware` patterns ask you and take a lease; another session's lease refuses |
| Verify gate | Stop | Described above |
| Leases | SessionEnd | Releases the session's hardware leases |

The rules are carried over from v0.20's guards and incident-driven rules (tag `v0.20.0`). A hook bug
fails open and prints an error rather than blocking a session.

## Roadmap

- **Fleet**: `friday dispatch <id>` starts `/friday:execute` in a fresh Remote Control session on
  the machine that fits the directive's `Node:` line, over Tailscale SSH; sessions report back
  with cross-session messages. Robots stay SSH targets.
- **Status page**: `friday status --html` collected from every node, served on the tailnet.
