# attn-01: A session waiting on a prompt shows as needing the user on the dash and to the planner
Status: approved
Goal: attention
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_waiting.py && node --test dash/static/render.test.mjs && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
When a dispatched session stops on a permission prompt, a dialog or a question, friday records it
the moment it happens (a Claude Code `Notification` hook) and clears it when the session moves on.
`friday status` and the dash show it as needing the user, with the prompt text and the attach
command; `friday nodes --waiting` lets the planner session's check find it. Nothing answers the
prompt. tests/test_waiting.py and dash/static/render.test.mjs prove it.

## Steps
1. Read the Claude Code hooks documentation for the `Notification` event (fields, which prompts
   fire it, idle notices) and record the payload in `runs/attn-01/notes.md`; register the event in
   hooks/hooks.json for `friday_hook.py notification`.
2. hooks/friday_hook.py `notification`: in a friday worktree (a marker, or `FRIDAY_DISPATCHED_FROM`
   set), write `~/.local/state/friday/waiting/<goal>.json` with goal, directive, message, kind,
   tmux session and time, then start `friday status --push` detached with a timeout (never block
   the session). PreToolUse, PostToolUse, UserPromptSubmit and Stop remove the file when present.
3. lib/friday_status.py: sessions carry `waiting` (message, age) from that file, falling back to
   the existing tmux prompt detection for a session with no record; `friday status` prints it;
   dash/static/render.mjs adds a needs-you item `<node> <goal>: waiting on "<message>"` with
   `ssh <node> -t tmux attach -t '=friday-<goal>'`, counted with awaiting review and blocked.
4. `friday nodes --waiting`: one line per waiting session across the registry (node, goal,
   directive, age, message); exit 0 when none, 10 when any, 2 when a node is unreachable. Help
   text, spec, docs/fleet.md and docs/dashboard.md; add `Bash(friday nodes --waiting)` to the allow
   rules.
5. tests/test_waiting.py: the hook writes the record and status shows it; the next tool call
   clears it; outside a friday worktree it writes nothing; `nodes --waiting` with a fake ssh gives
   0, 10 and 2; render.test.mjs shows the item. CHANGELOG under Unreleased/Added.

## Out of scope
- Answering, dismissing or auto-approving any prompt.
- Push notifications to a phone.

## Log
