# attn-01: A session waiting on a prompt shows as needing the user on the dash and to the planner
Status: done
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

### 2026-11-18
Commits:
- 9e3a873 attn-01: register the Notification hook for friday_hook.py notification
- 78b9fb4 attn-01: the notification hook records a waiting session; tool calls, prompts and stop clear it
- ded4ce5 attn-01: status and the dash show a session waiting on a prompt, from the hook record or the pane
- 1b74430 attn-01: friday nodes --waiting lists sessions waiting on a prompt across the registry
- f68a47a attn-01: tests for the waiting hook, clear and outside-worktree cases; CHANGELOG entry
Notes:
# attn-01 step 1: Notification hook payload (from https://code.claude.com/docs/en/hooks.md, read 2026-11-18)

Payload (stdin JSON): common fields (session_id, transcript_path, cwd, hook_event_name="Notification")
plus `message` (text), optional `title`, `notification_type`.
Example: {"hook_event_name":"Notification","message":"Claude needs your permission","notification_type":"permission_prompt", ...}

Matcher = notification_type. Types and when they fire:
- permission_prompt: tool-use or sandbox network permission prompt, after ~6s waiting (each keystroke defers it
  in terminal sessions). PermissionRequest fires immediately instead, but is a different event.
- elicitation_dialog / elicitation_url_dialog: MCP form / browser-URL request, after ~6s without typing.
- agent_needs_input: background session waiting on input while agent view is open; also teammate setup
  question and auto-mode classifier charge notice (~6s).
- idle_prompt: ~60s after Claude finished responding with no typing and no background agent running. This is
  an idle notice, NOT a prompt: friday should not record it as waiting (it would make every finished session
  look blocked).
- auth_success, auth_storage_failure, elicitation_complete, elicitation_response, agent_completed,
  quota_auto_resume_fired/_stale/_disabled, plugin_notification: informational; not waiting on a prompt.

Behaviour: observational; exit code, stderr, systemMessage and continue are ignored (only terminalSequence is
honoured). It cannot block or answer a prompt. It fires even with desktop notifications disabled.
Consequence: an unknown `friday_hook.py notification` subcommand fails open harmlessly until step 2 lands.

Registration choice: matcher "permission_prompt|elicitation_dialog|elicitation_url_dialog|agent_needs_input"
so idle_prompt and informational types never reach the hook. Step 2 should still check notification_type.
Verify: Verify passed: uv run --with pytest pytest -q tests/test_waiting.py && node --test dash/static/render.test.mjs && uv run --with pytest pytest -q && claude plugin validate .
Independent review: no gaps
