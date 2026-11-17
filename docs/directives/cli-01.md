# cli-01: `friday install` puts `friday` on PATH, on the master and on every node
Status: approved
Goal: cli-ergonomics
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_install.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
`friday` runs from any terminal on every machine without knowing where the plugin lives:
`friday install` (or `python3 <plugin>/bin/friday install` the first time) links
`~/.local/bin/friday` to the plugin checkout it was run from, and `friday nodes --setup <node>`
does the same on that node for its `plugin_dir`; `friday uninstall` removes the link. `friday nodes --check` reports a node where
`friday` is missing from PATH or points at a different checkout. tests/test_install.py proves
install, repair and refusal cases.

## Steps
1. Add `friday install [--bin-dir DIR]` (default `~/.local/bin`): create the symlink to this
   checkout's `bin/friday`; leave a correct link alone; replace a link that points at another
   friday checkout, printing old and new targets; refuse to overwrite a regular file or a link to
   something that is not friday. Print whether DIR is on PATH and, if not, the one line to add to
   `~/.profile`. Add `friday uninstall [--bin-dir DIR]`: remove the link only when it points at a
   friday checkout (any), print what it removed, and do nothing (exit 0, one line) when there is
   no link; it never removes a regular file or a foreign link.
2. `friday nodes --setup <node>`: after the settings step and under the same confirmation, run
   `<plugin_dir>/bin/friday install` on the node over `friday_fleet.ssh_cmd` (PATH with
   `$HOME/.local/bin` as remote commands already use).
3. `friday nodes --check`: per master and worker node, report `friday on PATH: ok`, `missing` or
   `points at <path>` (when it is not `plugin_dir`), each with the fix `friday nodes --setup <node>`.
4. README "Install" and docs/fleet.md one-time node setup: `python3 <checkout>/bin/friday install`
   once per machine, after that just `friday`; `friday uninstall` to remove it (on a node:
   `ssh <node> friday uninstall`); `uv run` and `python3` forms still work. CHANGELOG entry.
5. Add `tests/test_install.py` with a temp HOME and bin dir: fresh install, idempotent re-run,
   repoint from another checkout, refusal on a regular file and on a foreign link, PATH hint;
   uninstall removes a friday link, is a no-op without one, and refuses a regular file or foreign link;
   `--setup` runs the remote install after confirmation (fake `ssh`); `--check` reports ok,
   missing and wrong-target.

## Out of scope
- Packaging friday for pip or `uv tool install`.
- Short-form aliases for existing commands (not needed: the commands are fine, finding them was not).
- Slash commands (cli-02).

## Log
