# Recipe: a robot software repo

A ROS 2 workspace with component submodules and a hardware test checklist per platform, with the same model as [getting-started.md](../getting-started.md): a goal, its
directives, one `Verify:` each, one PR. Read that page first. This one only adds what robot work
needs. It is shaped on cpsl-research/console: a ROS 2 repo whose `run.sh` only starts the
console container (`docker compose up --build console`), whose tests are `uv run pytest -q` (no ROS
or hardware needed), whose components are git submodules (`components/CPSL_ROS2_Create3`,
`_Sensors`, `_ArduPilot`, `_Nav`, `_Rover`, `_PX4`), and whose `docs/HARDWARE_TESTS.md` is a
hardware test checklist ticked per platform (Create 3, Rover Pro, Aurelia X6) and per version.

## The shape of a robot goal

Three kinds of work, three kinds of directive:

- **Software, verified by the test suite.** Code in a component or the workspace is
  `Deliverable: code` with `Accept: auto` and a `Verify:` that runs the repo's test suite, for example
  `uv run pytest -q`. These run anywhere, with no robot. Do not use `run.sh` as Verify in
  console: it starts the GUI container.
- **A hardware test you attend.** Whether the robot behaves is a judgement a test suite cannot
  make. Make it `Accept: user`, set `Hardware:` to the robot, and put the checklist in `## Review`
  (in console, point at the platform's section of `docs/HARDWARE_TESTS.md`).
  The directive ends `awaiting review`; you run the checklist and `friday accept` it.
- **A dispatched robot step.** Deploying to the robot (ssh, flashing) can run with nobody at a
  prompt when its exact commands are pre-approved under `## Allowed commands`.

**A hardware directive runs attended unless its commands are pre-approved under
`## Allowed commands`.** A command that matches a `hardware` pattern asks you before it runs.
With you at the session you answer it. In a dispatched session nobody can, so the session waits
until you resume it. Pre-approve only the exact commands a directive needs.

## Configure `.claude/friday.json`

Name the commands that touch the robot, so they take a lease and ask:

```json
{
  "hardware": {
    "rover": ["\\bssh\\b.*\\brover\\b", "\\bscp\\b.*\\brover\\b", "\\brsync\\b.*\\brover\\b"],
    "rover-flash": ["\\bopenocd\\b", "\\bdfu-util\\b", "\\bst-flash\\b", "/dev/ttyACM\\d", "\\./flash\\.sh\\b"]
  }
}
```

Each key is a resource and each value is a list of regular expressions matched against a Bash
command. Use one resource per physical thing: one session holds a resource's lease at a time
(see [spec.md](../spec.md) section 9.3), so a second session cannot drive the same robot. A
lease lasts 4 hours, or until the session ends or you run `friday release rover`.

Adjust the names (`rover`, the flashing tools) to your platform and keep the patterns narrow.
The `ssh` pattern matches the host name as it appears in the command.

## Software directives

Use the repo's own test command as `Verify:`. It stays cheap and repeatable, because friday
re-runs it in fix rounds and again at landing:

```text
Verify: uv run pytest -q tests/test_limiter.py
```

Do not make `Verify:` something that matches a `hardware` pattern. `friday check` warns when it
does, because Verify is re-run unattended and skips the hardware prompt. Run the device step
once, record it with `friday result write`, and verify with `friday result check`.

## Submodules: the component's own repo first

A component submodule is another repo. A change to its code is a commit in that repo, and the
workspace only records which commit it points at. So:

1. Make the component change in the component's own repo, on its own branch and PR, and merge it
   there. A directive in the workspace repo does not push to another repo.
2. Then a directive in the workspace repo bumps the submodule pointer (`git add components/CPSL_ROS2_Nav`)
   and verifies against the pointed-to commit.

A step that edits files inside a submodule and commits in the workspace repo records nothing
useful: the workspace commit holds only a new pointer, to a commit nobody pushed. Put the
component work in the component's own repo (a friday goal there, or by hand) and merge it first,
and let the workspace directive's `## Goal` name the component commit it expects. Name the
pointer in `## Out of scope` of directives that must not move it.

## Allowed commands for the robot

`## Allowed commands` lists the commands that run without a prompt while that directive is
active. Each bullet has one backticked pattern in which `*` matches any text; the whole command
must match, and it must be one simple command (no `&`, `;`, `|`, backticks or `$(`). The list is
read from the plan as committed on `origin/<Base>`, so decide it before you approve and push, and
check it in the approval summary.

```markdown
## Allowed commands
- `ssh rover ros2 topic list`
- `ssh rover ros2 topic echo --once /rover/status`
- `./flash.sh rover firmware/rover.bin`
```

A pre-approved hardware command still takes the lease and is still denied while another session
holds it.

Keep a target directive thin: `friday check` warns on `ssh rover *`, a remote `bash -c *` and remote
builds. Pre-approve a reviewed script instead, such as the read-only `tools/probe.sh *`, and give
iterative robot work to a worker goal. See [fleet.md](../fleet.md) "Targets and workers" for the rule
and the probe recipe.

## What the deny list refuses even when pre-approved

The deny list wins over `## Allowed commands`. These are refused even if a directive lists them:

- Privilege escalation (`sudo`, `su`, `doas`), including after `ssh`: a service restart or a
  reboot of the robot through `ssh rover` with `sudo` in front is refused.
- `chmod 777`, an unscoped `rm -rf`, `dd if=` and `mkfs`, which are the commands people reach for
  on a robot that will not boot.
- `git push` to `main`, force-pushes, and `git remote add`.
- `friday accept`, always, also through `ssh`.

Do those steps yourself. Run them in your own terminal, outside the session, then tell the
session. Put "stop and report if the robot needs a service restart" in `## Steps`, restart it
yourself, and resume. Better, remove the need for the privileged step: set up the serial port
rule and the service once during robot setup, so the directive's own commands need no privilege.

## Complete example: bring up a new nav package on the rover

One goal, three directives: a software change verified by the tests, a deployment that runs
unattended, and an attended hardware test. Put these under `docs/goals/` and `docs/directives/`
and run `friday check`.

`docs/goals/rover-nav.md`:

```markdown
# rover-nav: Ship the rover_nav speed limit and test it on the rover
Status: proposed
Base: main
Land: pr

## Goal
`rover_nav` limits commanded speed to 1.0 m/s, the firmware that reports speed is flashed to the
rover, and a person has run the rover hardware test checklist.

## Directives
1. nav-01: Limit commanded speed in rover_nav
2. flash-01: Flash the rover and record the deployed firmware
3. hwtest-01: Run the rover hardware test checklist

## Log
```

`docs/directives/nav-01.md`:

```markdown
# nav-01: Limit commanded speed in rover_nav
Status: proposed
Goal: rover-nav
Node: any
Deliverable: code
Verify: uv run pytest -q tests/test_limiter.py
Hardware: none

## Goal
`rover_nav` clamps the linear speed of every `cmd_vel` it publishes to 1.0 m/s, and a unit test
shows a 2.0 m/s request leaving as 1.0.

## Steps
1. Add the clamp in `rover_nav/limiter.py` and a parameter `max_speed` defaulting to 1.0.
2. Add `tests/test_limiter.py` covering below, at and above the limit.

## Out of scope
- Any submodule pointer, the firmware, and the real robot.

## Log
```

`docs/directives/flash-01.md`:

```markdown
# flash-01: Flash the rover and record the deployed firmware
Status: proposed
Goal: rover-nav
Node: tag:robot
Deliverable: code
Verify: friday result check flash-01 --require 'flashed == 1' --files
Hardware: rover, rover-flash

## Goal
`results/flash-01.json` records that `firmware/rover.bin` was flashed to the rover once and the
rover reported the firmware it runs, and the recorded firmware file is unchanged.

## Steps
1. Flash once: `./flash.sh rover firmware/rover.bin`. Stop and report if it exits non-zero.
2. Read back the status: `ssh rover ros2 topic echo --once /rover/status`. The
   `firmware` field must match `firmware/VERSION`.
3. Record it with `friday result write flash-01 --metric flashed=1 --file firmware/rover.bin
   --cmd "./flash.sh rover firmware/rover.bin"` and commit `results/flash-01.json`.

## Out of scope
- Changing firmware sources, and any command that needs elevated privileges on the rover. If one
  is needed, stop and report it; the user runs it.

## Allowed commands
- `./flash.sh rover firmware/rover.bin`
- `ssh rover ros2 topic echo --once /rover/status`

## Log
```

`docs/directives/hwtest-01.md`:

```markdown
# hwtest-01: Run the rover hardware test checklist
Status: proposed
Goal: rover-nav
Node: tag:robot
Deliverable: code
Accept: user
Verify: friday result check hwtest-01 --require 'topics_checked == 1' --files
Hardware: rover

## Goal
The rover, flashed by `flash-01`, has its topics listed and its status read on the robot, and
`results/hwtest-01.json` records the log, so a person can review the checklist against it.

## Steps
1. Run `ssh rover ros2 topic list` and save the output to `logs/hwtest-01-topics.txt`.
2. Run `ssh rover ros2 topic echo --once /rover/status` and append it to
   `logs/hwtest-01-topics.txt`.
3. Record it with `friday result write hwtest-01 --metric topics_checked=1 --file
   logs/hwtest-01-topics.txt` and commit `results/hwtest-01.json` and the log. The metric means
   the topic checks ran; the drive itself is the user's review below.

## Review
- Platform checklist for the rover: the Rover Pro section of `docs/HARDWARE_TESTS.md`, ticked for this version. At least: robot on blocks, e-stop reachable, battery above 80 percent.
- Open `logs/hwtest-01-topics.txt`: `/rover/status` reports the firmware from `firmware/VERSION`.
- Drive the rover at full stick: the speed stays at or below 1.0 m/s.
- Press the e-stop: the wheels stop within one second.

## Out of scope
- Firmware, `rover_nav` code, and any privileged or service command on the rover.

## Log
```

Plan it with `/friday:plan` and approve it; check the `## Allowed commands` of `flash-01` in the
approval summary, then push Base. Run the goal with `/friday:execute` for each directive in turn.
`nav-01` needs no robot. `flash-01` runs its pre-approved commands without a prompt. `hwtest-01`
asks before each `ssh` (they are not pre-approved) because you attend it, and ends
`awaiting review`. Work through the checklist under `## Review` at the robot, then run
`friday accept hwtest-01` yourself. Accepting does not land the goal: then run
`friday land --goal rover-nav` yourself to open the PR, which you merge.

To run the unattended directives on a robot host, put them in a goal of their own and
`friday dispatch --goal <goal>` it. A dispatched goal runs on one node, and a directive that would
prompt waits, so keep the attended checklist in a separate goal that you run yourself.
