# disp-01: A dispatched session loads friday once, and `nodes --check` reports the outside-reads setting
Status: done
Goal: field-fixes
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_dispatch_plugin.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
On a node where the friday plugin is installed for the user (`claude plugin list` shows
`friday@...` enabled), `friday dispatch` and `--resume` launch the session without
`--plugin-dir`, so hooks and skills load once; on a node without it, they keep passing
`--plugin-dir <plugin_dir>`. `friday nodes --check` reports whether the node will prompt for
reads outside the working directories, next to the workflow and auto-mode prompts.
tests/test_dispatch_plugin.py proves both.

## Steps
1. Check first, and record in `runs/disp-01/notes.md`: does Claude Code load a plugin twice when
   it is both installed and passed with `--plugin-dir` (same directory)? If it de-duplicates,
   keep step 2 but say in the notes that it is a tidy-up, not a bug fix.
2. lib/friday_fleet.py: the node probe (used by `nodes --check` and the dispatch prepare script)
   reports whether `friday@` is installed and enabled, and from which directory. `launch_line`
   omits `--plugin-dir` when it is and that directory is the node's `plugin_dir`; when installed
   from a different directory, keep `--plugin-dir` and warn in `nodes --check` that two copies
   exist.
3. `friday nodes --check`: a line for the outside-reads prompt (the user setting
   `permissions.blockReadsOutsideWorkingDirectories` or its current equivalent: confirm the key in
   the Claude Code settings docs) and for the plugin install state. docs/fleet.md says how a
   directive that needs another repo should handle it (copy what it needs into the goal branch, or
   the user allows the read).
4. tests/test_dispatch_plugin.py with a fake ssh: installed from plugin_dir gives a launch line
   without `--plugin-dir`; not installed keeps it; installed elsewhere keeps it and warns;
   `nodes --check` prints the outside-reads and plugin lines. CHANGELOG (1.1.0 section).

## Out of scope
- Installing or updating the plugin on a node; the user does that.
- Changing any Claude Code setting on a node.

## Log

### 2026-11-18
Commits:
- 20d893b fleet: probe friday@ install state; omit --plugin-dir when installed from plugin_dir, warn on two copies
- 9a168f6 nodes --check: report the outside-reads prompt setting and plugin install state
- ea8e961 disp-01: test nodes --check plugin install states; CHANGELOG
Notes:
- step 1 (Claude Code 2.1.327): friday@friday is installed (user scope, read from /home/david/friday). `claude -p --output-format stream-json --verbose` init message, same directory passed both ways.
- Installed only: plugins lists friday once (source friday@friday); 9 friday:* skills, 3 friday:* agents.
- Installed AND `--plugin-dir /home/david/friday`: plugins still lists friday once, source becomes friday@inline (the inline copy replaces the installed one); the same 9 skills and 3 agents, no duplicates.
- Conclusion: Claude Code de-duplicates when the directory is the same, so loading twice is not a bug here. Step 2 (omit --plugin-dir when installed from plugin_dir) is a tidy-up, not a bug fix. Not tested: installed from a different directory (two distinct copies would plausibly both load; step 2 keeps --plugin-dir and warns there).
Verify: Verify passed: uv run --with pytest pytest -q tests/test_dispatch_plugin.py && uv run --with pytest pytest -q && claude plugin validate .
Independent review: no gaps
