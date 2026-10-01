# Hardware

Board designs for <project>, and the notes that go with
them. This file is the Hardware role's source of project facts
(`.friday/active/harness/roles/hardware.md`): keep it current.

## Boards

| Path | Board | Repo / branch | Owner | Status |
|------|-------|---------------|-------|--------|
| `<dir>/` | <what it is> | <in-repo, or submodule URL + working branch> | <person> | <state; link to its spec if any> |

**Ownership rule:** a board owned by someone else gets analysis, summaries
and proposed changes; edits to it need that owner's agreement (for harness
agents: a directive that says so explicitly). Submodules are separate repos
— commit inside the submodule on its current branch, then bump the pointer
here in a separate commit.

## Notes and figures

| Path | What |
|------|------|

## Tools

| Tool | Where | Notes |
|------|-------|-------|
| KiCad | host install; `kicad-cli` on `PATH` (<version>) | GUI for layout and schematic edits; `kicad-cli` for ERC/DRC, exports, fab outputs. |
| Vivado (optional) | `source <path>/settings64.sh` (<version>) | Batch mode only for agents. |
| FPGA boards (optional) | <USB/JTAG, or network address> | Single-user: claim in `status.md` before use. |

## Conventions

- **Check with the CLI.** Run `kicad-cli sch erc` / `kicad-cli pcb drc`
  before and after a change; a change should add no new violations.
- **Don't edit a project that's open.** `~*.lck` files next to a project
  mean KiCad has it open (or crashed with it open). Close KiCad first; don't
  just delete the lock.
- **Exports for analysis go to a scratch location**, not into the board
  directory. Fab outputs go <where>.
- **Cite the source** for every pin, voltage, timing or part claim: the
  datasheet page or the schematic sheet.
