# Recipe: a KiCad PCB repo

A KiCad project (schematic sheets, a board, libraries, fabrication outputs), with the same model
as [getting-started.md](../getting-started.md): a goal, its directives, one `Verify:` each, one
PR. Read that page first. This one only adds what hardware design needs.

The split is simple. A machine can check rules (electrical rules, design rules) and can export
files. A person has to judge whether the design is right and do the interactive layout work.
Give the machine the first and keep the second for yourself.

## What Verify can prove

`kicad-cli` runs headless and has a flag that turns violations into a failing exit code, which is
what `Verify:` needs:

```text
kicad-cli sch erc --exit-code-violations -o reports/erc.rpt board/board.kicad_sch
kicad-cli pcb drc --exit-code-violations -o reports/drc.rpt board/board.kicad_pcb
```

With `--exit-code-violations` the command exits non-zero when the report holds violations, so
`&&` chains them into one `Verify:`:

```text
Verify: kicad-cli sch erc --exit-code-violations -o reports/erc.rpt board/board.kicad_sch && kicad-cli pcb drc --exit-code-violations -o reports/drc.rpt board/board.kicad_pcb
```

What this proves: the schematic has no electrical rule violations and the board has no design
rule violations, under the rules saved in the project. It does not prove that the circuit is the
right circuit, that a part is the right part, or that the board will work. Treat a green ERC and
DRC as "nothing the tools can see is wrong", not as "approved".

Run `kicad-cli sch erc --help` and `kicad-cli pcb drc --help` for the options of your KiCad
version (`--severity-error` and `--severity-warning` choose what counts). Keep the commands in
the repo's `Verify:` the same as the ones you run by hand, so a red Verify is reproducible.

## Layout changes are reviewed by you

A change to placement, routing or the schematic is `Accept: user`, with `## Review` naming the
sheets and layers to open. ERC and DRC passing is the machine's half; the directive then ends
`awaiting review` and you open KiCad and look at exactly what the review list names, then run
`friday accept <id>` yourself.

Be specific in `## Review`: the sheet names (not "the schematic"), the layers (`F.Cu`, `B.Cu`,
`F.Silkscreen`, `Edge.Cuts`), the refdes to inspect and the question for each. A reviewer who
must guess where to look will skip it.

## Fabrication outputs: generate once, record the files

Gerbers, drill files, a bill of materials and a pick-and-place file are generated, and a
directive can do that. Do not commit a hand-exported set. Have a step run `kicad-cli`, then
record the output with `friday result write --file`, which stores each file's `sha256` and size
in `results/<id>.json`:

```text
kicad-cli pcb export gerbers -o fab/gerbers/ board/board.kicad_pcb
kicad-cli pcb export drill -o fab/gerbers/ board/board.kicad_pcb
friday result write fab-01 --file fab/fab-01.zip --metric layers=4 --cmd "kicad-cli pcb export gerbers"
```

Verify it with `friday result check fab-01 --require 'layers == 4' --files`. `--files` fails
when a recorded file no longer matches its hash, so a Gerber changed after the record is caught,
and the check stays cheap enough to re-run at landing. Zip the fabrication set into one file
first if you want one hash for the whole package. The set is only as good as the board it was
exported from, so put the export in a directive that follows the layout directive, which you
accept first.

## What an agent should not attempt

- **Interactive routing.** Pushing tracks, tuning differential pairs, length matching, copper
  pours and placement for a dense board are judgement work done in the editor. An agent that
  edits `.kicad_pcb` text to move tracks produces a board that passes DRC and routes badly.
  Do the routing yourself and let a directive handle the checks and exports around it.
- **Choosing parts and footprints**, and anything that decides the electrical design. A directive
  can apply a decision you have written down ("replace R4 with 10k 0402"), not make it.
- **Sending a board to a fabricator**, ordering parts, or signing off a release. Those stay with
  you.
- **Editing the project files while KiCad has them open.** Close the project first, or the editor
  saves over the change.
- **Regenerating libraries or running a bulk update of symbols and footprints** without a
  directive that names the exact change and a review of the diff.

If a directive needs one of these, put "stop and report" in `## Steps` and do the step yourself,
then resume.

## Complete example: add a status LED and release fabrication files

One goal, two directives: a schematic and layout change that you review, then the generated
fabrication set. Put these under `docs/goals/` and `docs/directives/` and run `friday check`.

`docs/goals/status-led.md`:

```markdown
# status-led: Add a status LED to the board and export fabrication files
Status: proposed
Base: main
Land: pr

## Goal
The board has a status LED driven from the MCU, ERC and DRC are clean, a person has reviewed the
sheet and the layers, and the fabrication files are generated and recorded.

## Directives
1. led-01: Add the status LED to the schematic and place it
2. fab-01: Generate and record the fabrication files

## Log
```

`docs/directives/led-01.md`:

```markdown
# led-01: Add the status LED to the schematic and place it
Status: proposed
Goal: status-led
Node: any
Deliverable: code
Accept: user
Verify: kicad-cli sch erc --exit-code-violations -o reports/erc.rpt board/board.kicad_sch && kicad-cli pcb drc --exit-code-violations -o reports/drc.rpt board/board.kicad_pcb
Hardware: none

## Goal
Sheet `power_io` has LED D5 and its 1k resistor R12 on net `STATUS_LED`, the footprints are placed
inside the board outline near the edge connector, and ERC and DRC report no violations.

## Steps
1. In `board/power_io.kicad_sch` add D5 (green, 0603) and R12 (1k, 0402) from `STATUS_LED` to GND,
   using the symbols and footprints already in the project libraries.
2. In `board/board.kicad_pcb` add the two footprints at the positions given in `## Review`
   without moving any existing footprint. Leave D5 and R12 unrouted. If routing is needed,
   stop and report; the user routes it.
3. Run the Verify commands and fix any violation your change caused.

## Review
- Open sheet `power_io`: D5 and R12 sit between `STATUS_LED` and GND and the values are right.
- Open the board with layers `F.Cu` and `F.Silkscreen`: D5 and R12 are within 5 mm of J2 and
  inside `Edge.Cuts`, and the D5 silkscreen label is readable.
- Route `STATUS_LED` yourself on `F.Cu` and run DRC in the editor before you accept.

## Out of scope
- Routing, moving existing footprints, other sheets, and the fabrication files.

## Log
```

`docs/directives/fab-01.md`:

```markdown
# fab-01: Generate and record the fabrication files
Status: proposed
Goal: status-led
Node: any
Deliverable: code
Verify: friday result check fab-01 --require 'layers == 4' --files
Hardware: none

## Goal
`fab/fab-01.zip` holds the Gerber and drill files exported from the accepted board, and
`results/fab-01.json` records its hash.

## Steps
1. Run `kicad-cli pcb export gerbers -o fab/gerbers/ board/board.kicad_pcb`.
2. Run `kicad-cli pcb export drill -o fab/gerbers/ board/board.kicad_pcb`.
3. Zip `fab/gerbers/` into `fab/fab-01.zip`.
4. Record it with `friday result write fab-01 --file fab/fab-01.zip --metric layers=4 --cmd
   "kicad-cli pcb export gerbers"` and commit `fab/fab-01.zip` and `results/fab-01.json`.

## Out of scope
- Editing the schematic or the board, and sending anything to a fabricator.

## Log
```

Plan it with `/friday:plan`, approve it and push Base. Run `/friday:execute`: `led-01` places the
parts, runs ERC and DRC, and ends `awaiting review`. Open the sheet and layers it names, route
the net, run DRC in the editor, then `friday accept led-01` yourself. `fab-01` then exports the
files from the board you accepted; the goal lands as a PR, which you merge.
