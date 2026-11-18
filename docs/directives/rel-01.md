# rel-01: Release 1.0.0
Status: done
Goal: v1-final
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_release.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
The plugin says 1.0.0 everywhere and can be installed from a marketplace entry: version,
changelog, licence and install instructions agree, proved by tests/test_release.py.

## Steps
1. .claude-plugin/plugin.json: version `1.0.0`. CHANGELOG.md: turn `Unreleased` into
   `1.0.0 - <date>` with a short summary on top, add an empty `Unreleased`, remove the lines about
   the `VERSION` file.
2. Add `LICENSE` (MIT, the user as holder) and `.claude-plugin/marketplace.json` listing this
   plugin, so `/plugin marketplace add` works on a clone.
3. README.md: drop "alpha"; Status says 1.0 and links the spec, tutorial and changelog. One
   install path, stated the same way in README.md and docs/getting-started.md, with no "if you
   cloned" branch: clone the repo (`-b v1` until 1.0 is on main), `/plugin marketplace add
   <clone>`, install the plugin from that marketplace, then `python3 <clone>/bin/friday install`
   once per machine; updating is `git pull` in the clone plus the marketplace update. (Amended by
   the user 2026-11-18: the clone plus local marketplace is the one supported install.)
4. tests/test_release.py: plugin.json version equals the top released CHANGELOG heading;
   marketplace.json parses and names the plugin; LICENSE exists; README has no "alpha"; README.md and docs/getting-started.md give the same install commands in
   the same order, and neither makes the PATH step conditional.

## Out of scope
- Tagging, merging v1 into main, and changing the GitHub default branch: the user does these after merging the goal PR.

## Log

### 2026-11-18
Commits:
- 05fe765 rel-01: version 1.0.0, changelog release entry
- b10e545 rel-01: add MIT LICENSE and marketplace.json
- e7836e7 rel-01: README drops alpha, installs from the marketplace, Status links spec, tutorial, changelog
- b10f8e1 rel-01: tests/test_release.py checks version, changelog, marketplace, LICENSE, README
- e21551e rel-01: tutorial installs from the marketplace, matching the README
Notes:
2026-11-18: Dispatched from thinkpadP15v3 to cpsl-homebase
Verify: Verify passed: uv run --with pytest pytest -q tests/test_release.py && uv run --with pytest pytest -q && claude plugin validate .
Independent review: not recorded
Blocked: review gaps remain: /home/david/Documents/claude_temp/friday.friday/v1-final/docs/getting-started.md:38-52 and /home/david/Documents/claude_temp/friday.friday/v1-final/README.md:29-34: The earlier contradiction is fixed, but the two documents still give different install steps for getting the 'friday' CLI. The tutorial runs the PATH step only for clone users ('If you cloned it, put 'friday' on your PATH'). After that, someone who installed from the marketplace has no 'friday' in their terminal, yet step 3 tells them to run 'friday init' in a bash block. The README tells every user to run the PATH step 'once per machine', with 'python3 ~/src/friday/bin/friday install', which only works with a clone. That fails the Goal's requirement that the install instructions agree, and the tutorial's marketplace route does not work end to end in a shell.

### 2026-11-18
Unblocked: was blocked: review gaps remain: /home/david/Documents/claude_temp/friday.friday/v1-final/docs/getting-started.md:38-52 and /home/david/Documents/claude_temp/friday.friday/v1-final/README.md:29-34: The earlier contradiction is fixed, but the two documents still give different install steps for getting the 'friday' CLI. The tutorial runs the PATH step only for clone users ('If you cloned it, put 'friday' on your PATH'). After that, someone who installed from the marketplace has no 'friday' in their terminal, yet step 3 tells them to run 'friday init' in a bash block. The README tells every user to run the PATH step 'once per machine', with 'python3 ~/src/friday/bin/friday install', which only works with a clone. That fails the Goal's requirement that the install instructions agree, and the tutorial's marketplace route does not work end to end in a shell.

### 2026-11-18
Commits:
- 05fe765 rel-01: version 1.0.0, changelog release entry
- b10e545 rel-01: add MIT LICENSE and marketplace.json
- e7836e7 rel-01: README drops alpha, installs from the marketplace, Status links spec, tutorial, changelog
- b10f8e1 rel-01: tests/test_release.py checks version, changelog, marketplace, LICENSE, README
- e21551e rel-01: tutorial installs from the marketplace, matching the README
- 0caf382 rel-01: README and tutorial share one install path, clone plus local marketplace
- 61c231b rel-01: test that README and tutorial share the install commands, PATH step unconditional
Notes:
2026-11-18: Dispatched from thinkpadP15v3 to cpsl-homebase
2026-11-18: Dispatched from thinkpadP15v3 to cpsl-homebase
Step 1 check: already done in 05fe765 (plugin.json 1.0.0; CHANGELOG '## 1.0.0 - 2026-11-18' under empty '## Unreleased'; no VERSION file). Only remaining VERSION mention is the historical v0.12.1 entry, left as history.
step 2: LICENSE (MIT, David Hunt) and .claude-plugin/marketplace.json already present from b10e545; claude plugin validate . passed. No change.
Verify: Verify passed: uv run --with pytest pytest -q tests/test_release.py && uv run --with pytest pytest -q && claude plugin validate .
Independent review: no gaps
