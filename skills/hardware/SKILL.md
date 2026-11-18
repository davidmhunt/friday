---
name: hardware
description: How to work with single-user physical hardware (radar boards, serial ports, capture cards, robots over SSH) under friday: leases, approval prompts, and what never to automate. Use before any command that touches a device.
---

# Hardware

Physical devices are single-user, and a wrong command can cost hours at the bench.

- **Every hardware command asks the user.** The project's `.claude/friday.json` lists device
  patterns under `hardware`; a hook turns any matching command into a permission prompt and takes
  a lease on that resource for this session. Expect the prompt; never rephrase a command to dodge it.
- **Pre-approved is still leased.** A directive may list a hardware command under
  `## Allowed commands` (read from its Base); the hook then answers `allow` instead of asking,
  but still takes the lease, and still denies while another session holds it.
- **One session per device.** If the hook says a resource is held by another session, stop and
  report it. Do not wait in a loop. The user frees a stale lease with `friday release <resource>`.
  Leases also end when the session ends.
- **Power cycles, cable changes, flashing switches and anything physical** are the user's. Write
  the exact action you need in your report and stop.
- **Robots and remote targets** are plain SSH hosts. Run commands as `ssh <host> './run <cmd>'`
  (or the project's documented form) from the session that holds the lease.
- **Record what you ran.** In the directive Log: command, board/port, firmware, config file and
  result, so the run can be repeated.
- A check that needs a person at the bench is not a Verify command. Say so; the directive's
  `Hardware:` line covers it.
