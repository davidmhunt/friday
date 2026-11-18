# disp-01: A dispatched session loads friday once, and `nodes --check` reports the outside-reads setting
Status: approved
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
