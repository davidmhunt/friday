# Changelog

<!-- Maintainer reminder: bump VERSION in the same commit as the entry
     below it documents. VERSION drifted for several releases (stuck at
     0.10.0 through v0.10.1/v0.11.0/v0.12.0) because this wasn't a single
     atomic step. -->

## v0.13.0

The harness no longer installs itself into the project it serves. Everything
it generates now lives inside `.friday/`, and a consumer project root keeps
only what agent tooling genuinely requires to be there: `.claude/`, `.agents/`,
`docker/`, `.dockerignore`, `AGENTS.md`, `README.md`, `harness.config.env`, and
`docs/`.

v0.12.0 attacked the same clutter by *hiding* generated files from git — the
`HARNESS_TRACKING` tiers, a managed `.git/info/exclude` block, and
`--untrack-harness`. That worked, but it committed the harness to permanently
managing a boundary between two repos, and the tier machinery was the price.
This release moves the boundary instead, so most of that machinery stops
having anything to do.

**`.friday/` splits into `templates/` and `active/`.** All template sources
(`harness/`, `adapters/`, `docker/`, `docs/`, `AGENTS.md.tmpl`,
`README.md.tmpl`) moved under `templates/`, tracked as before. The per-project
live tree is materialized into `active/`, which `.friday/.gitignore` excludes —
so harness state is invisible to both repos and never rides along on a
`harness.sh sync push`. `MANIFEST.json` gains `MANIFEST_VERSION: 2` plus two
per-entry keys: `dest_root` (`repo` or `active`) and `src_root` (`templates` or
`submodule`). Neither the `src` nor the `dest` strings changed — only the roots
they resolve against, which keeps the manifest diff small and reviewable.

`src_root` exists because exactly one entry, `USER_GUIDE.md`, names a file that
deliberately stayed at the submodule root. That was first handled with a
try-templates-then-fall-back probe, which worked but would silently resolve a
typo'd `src` at the wrong root; an explicit key is the version that fails
loudly.

**Every symlink now points inside the submodule.** `active/harness/roles/coder.md`
→ `../../../templates/harness/roles/coder.md`: both ends in the same repo, so
it cannot dangle. Combined with `.claude/` and `.agents/` being git-excluded,
a clone made without `--recurse-submodules` now has **zero** dangling symlinks,
where before it had roughly 55 — including the ones that silently broke the
git hooks and the Docker build.

**`docs/` deliberately did not move.** The LaTeX documents must keep compiling
with the harness deleted, so `docs/RESULTS.md`, `docs/ARCHITECTURE.md`,
`docs/theory/`, `docs/report/` and `docs/references/` stay in the project repo,
tracked, with git-LFS unchanged. Research memos moved *to* `docs/research/` for
the same reason and in the same direction: they are project content that feeds
`docs/theory/`, and leaving them in gitignored harness state would have made
the LaTeX depend on files that vanish with the harness. `harness/research/`
no longer exists anywhere — the biblio tools scan `docs/research/` instead,
crossing the repo boundary deliberately.

**Two latent bugs surfaced by the move, both fixed.**

`harness/tools/_config.py`'s `find_repo_root()` returned the first ancestor
holding `harness.config.env` *or* `.git`. Inside a submodule `.git` is a FILE,
and `Path.exists()` is true for files — so with a cwd anywhere under
`.friday/`, it stopped there and every bibliography tool computed
`REFS_DIR = .friday/docs/references`: no error, no exception, just silently
wrong paths and empty results. Dormant while nothing gave you a reason to `cd
.friday`; load-bearing now that the whole harness lives there. It now walks the
full ancestor chain for `harness.config.env` first and only falls back to
`.git`. `command_guard.py` had already hit and documented this exact trap.

`install_git_hooks()` anchored at `.claude/hooks`, so a project with
`ADAPTERS_ENABLED=antigravity` got `.git/hooks/pre-commit ->
../../.claude/hooks/pre-commit` pointing at a file that never existed. The
anchor is now `.friday/templates/adapters/hooks`, which is adapter-independent.

**`compute_excluded_paths()` only considers repo-rooted entries.** An
active-rooted dest is not a consumer-repo path, so emitting it into
`.git/info/exclude` would write entries that can never match anything. The
generated block drops from 68 paths to 41.

The `HARNESS_TRACKING` tier system still exists and still works; it is deleted
in v0.14.0, once a real project has completed the migration and no longer needs
the old `--untrack-harness` as a cross-check alongside `--untrack-legacy`.

**Consumers migrating from v0.12.x** should run `--untrack-legacy` (added in
v0.12.1) to drop the relocated `harness/**` files from their index. Note it is
manifest-derived and so cannot reach files the manifest never generated —
`harness/research/*.md` move to `docs/research/` with `git mv` to preserve
history, and `harness/running/logs/.gitkeep` needs an explicit
`git rm --cached`.

## v0.12.1

Groundwork for the v0.13.0 restructure, which moves every harness-generated
file out of the consumer project and into `.friday/` itself. None of that
happens here. What lands here is the safety net that makes the move
verifiable, deliberately shipped *before* the move rather than alongside it —
a rewrite that touches several hundred path references should not be the same
release as the checks that prove it was done completely.

**`check_md_hygiene.py` no longer fails silently.** A `FILE_CAPS` path that
doesn't exist was skipped with a bare `continue`, so a relocated or mistyped
path quietly stopped being enforced — and since `pre-commit` always exits 0,
that was invisible in every channel. It now prints `WARN | hygiene |
configured path not found: <path>`, for `PER_ENTRY_FILE` as well. The exit
code is deliberately untouched: the hook is advisory by design, and a project
midway through a migration must not have its commits blocked by it. The test
fixture now stubs out every configured path (otherwise the new WARN would
pollute the existing tests' output assertions) and imports `FILE_CAPS` from
the hook, so it stays in sync if the table changes.

**Setup fails loudly when a hardcoded path table drifts from the manifest.**
Two modules carry path tables that must agree with `MANIFEST.json` and that
fail silently when they don't: `check_md_hygiene.py`'s `FILE_CAPS` /
`PER_ENTRY_FILE`, and `check_unavailable_sources.py`'s `SCAN_GLOBS`.
`preflight()` now parses both and exits with an error naming the offending
constant and path if an entry is neither a manifest dest nor under a directory
the harness always generates. The constants are read with `ast.parse` +
`literal_eval` rather than by importing the modules, since both execute
repo-root resolution at import time. This turns "a path table drifted" from a
silent runtime no-op into a setup-time failure.

**`--untrack-legacy`, because `--untrack-harness` is about to stop working.**
`untrack_harness()` intersects `git ls-files` with `compute_excluded_paths()`.
After v0.13.0 no manifest entry has a `harness/…` dest at all, so that
intersection goes empty and the command reports "Nothing to untrack" for
precisely the migration it exists to perform. `MANIFEST.json` gains a
top-level `legacy_dests` listing the 40 pre-v0.13.0 `harness/**` dests, and
`--untrack-legacy` intersects `git ls-files` with that instead. The two
commands are complementary and both are needed during migration:
`--untrack-legacy` handles what *moves out* of the project, `--untrack-harness`
handles what *stays* at the root but should stop being tracked (`.claude/`,
`.agents/`, the harness-only Docker files). The shared "intersect, then
`git rm --cached` an explicit file list" logic is factored into one helper,
preserving every safety property: an explicit list, never `-r`, never a glob,
never a commit, idempotent.

Note that `legacy_dests` is manifest-derived and therefore structurally cannot
reach files the manifest never generated — `harness/research/*.md` and
`harness/running/logs/.gitkeep` among them. Those are handled by hand during
migration, which is the correct tradeoff: the same property that makes this
command safe to run unattended is what limits its reach.

**`seed_once` on `README.md`.** The project's own README is now materialized
only when absent, and left alone thereafter with no output — a diverging
README is the expected steady state, not drift, so the `SKIP (already
materialized, differs from fresh render…)` line was noise.

**`.friday/active/` is gitignored ahead of existing, and `harness_sync.sh`
asserts it.** `cmd_push()` runs `git -C .friday add -A` and pushes to the
shared harness remote; once v0.13.0 puts per-project live state at
`.friday/active/`, that ignore rule is the only thing standing between a
routine `sync push` and leaking one project's state to every other consumer.
That is too much weight for a single unremarked line, so the rule lands now
and `cmd_push()` refuses to proceed unless `git check-ignore` confirms it is
in effect. The probe path is `active/` with a trailing slash, matching the
dir-only pattern: bare `active` returns "not ignored" while the directory
doesn't exist and "ignored" once it does, which would have made the guard
silently vacuous until the very release it exists to protect. The check runs
as a precondition, before the commit-message prompt.

`git clean -xfd` inside `.friday/` now destroys all harness state, since
gitignored files are exactly what `-x` sweeps up. Documented in the
`harness_sync.sh` header.

**`VERSION` was stale at 0.10.0** — it was last bumped in the v0.10.0 commit
and drifted through v0.10.1, v0.11.0 and v0.12.0. Set to 0.12.1, with a
maintainer reminder at the top of this file to bump it in the same commit as
the entry it documents.

## v0.12.0 (in progress — code landed, docs pending)

Two related changes toward a harness that can be dropped into a project
without committing itself to that project's repo. **The documentation pass
for both is not written yet**, and no project has been untracked yet — see
"Remaining" below.

**HARNESS_TRACKING: the harness can exclude its own files from git.**
Tracking harness output as symlinks into an optional submodule was already
a latent bug: anyone cloning a consumer repo without `--recurse-submodules`
got dangling symlinks — silently broken git hooks, and a broken Docker
build via `.dockerignore`. Every `MANIFEST.json` materialize entry now
carries a `tier` (`tooling` / `state` / `durable` / `project`); symlink
entries are implicitly `tooling`. A new `HARNESS_TRACKING` config key picks
how much to exclude, written to `.git/info/exclude` rather than
`.gitignore` so the harness leaves nothing in the repo's history.

The default is `tooling`: generated role/rule docs, hooks, adapter configs
and every symlink are excluded, while `status.md`, `log.md`, `plans/*` and
`tasks_*` stay tracked. Excluding derived tooling is pure upside; excluding
harness *state* trades away cross-machine continuity, so that's opt-in
(`state`) rather than default. A project with no task tracker configured
falls back to `full` instead — with no external durable record, excluding
state would leave in-flight work with no copy surviving a fresh clone. An
explicit value is always honoured; the interview warns when you choose
`state`/`none` without a tracker.

`--untrack-harness` runs `git rm --cached` over exactly the files that are
both in the manifest-derived exclude set and currently tracked. It never
touches anything outside that set, never commits, and is idempotent.

One sharp edge worth knowing: `.gitignore` beats `.git/info/exclude`, so a
`!path` negation defeats the exclusion for that path. `init_harness.py`
drops such negations from its own managed block automatically, but it will
not rewrite content a project wrote by hand outside that block — deleting
someone's line silently is worse than leaving it. It prints a WARN naming
the file and line instead.

**Docker splits into a `dev` stage and a `harness` stage.** `Dockerfile` is
now `FROM ubuntu AS dev` (base packages, the `agent` user, LaTeX, the
package manager, herdr, `CMD bash`, no ENTRYPOINT) and `FROM dev AS
harness` (Claude Code, Antigravity, `entrypoint.sh`). `docker-compose.yml`
is project-owned and tracked, builds `target: dev`, and carries only the
volumes a plain dev container needs; `docker-compose.harness.yml` is a
gitignored Compose override adding `target: harness`, the agent config
volumes and the Antigravity env vars. A teammate without the submodule runs
`docker compose -f docker/docker-compose.yml up -d` and gets a working
container with no agent tooling on it.

`init_harness.py` writes `COMPOSE_FILE` into the gitignored root `.env`, so
harness users get plain `docker compose up -d` back — the explicit
`-f docker/docker-compose.yml` that v0.11.0 required is no longer needed.

Node needed splitting to make this work: it was one section pulled in by
either a Node package manager or Claude Code. It's now two mutually
exclusive gates, `docker_node_runtime_dev` and `docker_node_runtime_harness`,
so exactly one ever emits and a non-Node project's clean image doesn't
carry a Node runtime it will never use. `.dockerignore` is now materialized
rather than symlinked, since as a symlink it dangled without the submodule
and broke the build itself.

**Remaining for v0.12.0:** the documentation pass (USER_GUIDE section on
the tiers, §12 rewrite for the dev/harness split, README tables, SETUP.md,
`version_control.md`, a `HARNESS.md` pointer doc, and making `harness.sh`
explain itself when the submodule is missing), then running
`--untrack-harness` on a real project and verifying a fresh clone made
without `--recurse-submodules` is fully functional.

## v0.11.0

Container layout change: all Docker inputs now live in `docker/`, and the
repo is mounted at a path named for the project rather than `/workspace`.

**`Dockerfile` and `docker-compose.yml` moved into `docker/`.** The
templates already sat together in `.friday/docker/`, but the materializer
scattered two of them to the repo root while leaving the other two in
`docker/`. `MANIFEST.json` now materializes all four to `docker/`, so the
generated layout mirrors the template layout and the whole container
surface is one directory. Compose commands become
`docker compose -f docker/docker-compose.yml ...`.

Two consequences are handled in the compose file itself. Relative paths now
resolve against `docker/`, so the build context is `..` (it must stay the
repo root — the Dockerfile does `COPY docker/entrypoint.sh`) and the bind
mount is `..:/<project>`. `.dockerignore` stays at the repo root, because
Docker reads it from the context root.

**New `docker/.env` symlink.** Compose resolves `.env` against the compose
file's own directory, which is now `docker/` rather than the repo root — so
a root-only `.env` would have been silently ignored, `${USER_UID}` would
have fallen back to `1000`, and bind-mounted files would come out owned by
the wrong UID on any host where the user isn't 1000. `init_harness.py` now
symlinks `docker/.env -> ../.env`, which makes the root `.env` reachable
whether you run Compose from the repo root or from inside `docker/`. The
symlink is safe to leave dangling: Compose treats a missing `.env` as "no
overrides".

**The workspace path is derived from `PROJECT_NAME_LOWER`.** `/workspace`
was a hardcoded literal in all three templates; it is now the same
`[SET AT SETUP: PROJECT_NAME_LOWER]` token that already pinned the Compose
project name and image tag, so the repo mounts at `/<project name>` and the
in-container path matches the project it holds. `entrypoint.sh`'s two
hardcoded settings-sync paths move in lockstep — had they not, the
Antigravity settings re-sync added in v0.10.1 would have silently no-opped
on every container start.

Note that agent CLIs key conversation history on the current working
directory, so this change starts a fresh history bucket. Existing
container-side conversations remain on disk in the volume under the old
bucket name; migrating them means renaming the bucket directory *and*
rewriting the `cwd` field recorded inside each session file, since the CLI
filters sessions by that field rather than by directory name.

**`docker compose down -v` guidance removed.** It was both obsolete and
dangerous: obsolete because v0.10.1's entrypoint re-sync means a plain
restart picks up `antigravity_settings.json` changes, and dangerous because
`-v` destroys the named volumes — which hold every stored login *and* all
Claude Code and Antigravity conversation history. The remaining legitimate
use (discarding volumes left root-owned by a pre-ownership-fix setup) now
carries an explicit warning.

`USER_GUIDE.md` and `README.md` updated throughout; the `/workspace`
references in `command_guard.py`'s comments were prose-only and its
deny-list regexes are path-agnostic, so guard behaviour is unchanged.

## v0.10.1

Four persistence/permission bugs found running the v0.10.0 dev container
in practice, all fixed.

**Antigravity settings re-sync on every start.** `Dockerfile`'s `COPY
docker/antigravity_settings.json ...` only seeds the `gemini-config` volume
the *first* time it's created — Docker never re-copies into an existing
named volume, so a rebuilt image alone never updated a running project's
settings. `entrypoint.sh` now re-syncs that one file from the bind-mounted
repo on every container start, so a plain restart is enough.

**Claude Code installs into a per-user npm prefix.** `npm install -g` at
build time landed the CLI under the root-owned default location
(`/usr/lib/node_modules`), so its self-updater failed at runtime as the
non-root `agent` user with "npm global folder isn't writable." Now
installed as `agent` into `~/.npm-global`, on `PATH` via `ENV`.

**Herdr is no longer the container's default foreground process.**
Reverted the v0.10.0 change: with herdr as the container's own PID-2
process, detaching from `docker compose attach` (rather than backgrounding
herdr from inside it) killed herdr, and with it the whole container — no
plain-shell fallback to land back in. `CMD` is `bash` again; run `herdr` by
hand when you want it.

**`~/.claude.json` now persists.** Claude Code's main config file is a
*sibling* of the `.claude/` directory the `claude-config` volume mounts,
not a member of it, so it lived on the container's throwaway layer and was
lost on every recreate — while `~/.claude/.credentials.json` (inside the
volume) survived. That split made a recreated container look logged-out:
the OAuth token was still there, but Claude fell back to a stale backup or
a fresh default for everything else `.claude.json` tracks. `~/.claude.json`
is now a symlink into the volume-backed directory.

`USER_GUIDE.md` §12.3, §12.5, and §12.6 updated to match.

## v0.10.0

The dev container now installs and launches
[herdr](https://herdr.dev), a terminal workspace manager for AI coding
agents.

**Herdr installs unconditionally.** Unlike the `claude`/`antigravity`
adapter CLIs, herdr isn't gated on any `harness.config.env` key — it wraps
whichever agent CLI(s) happen to be on `PATH` rather than being tied to
one, so every project with `DOCKER_ENABLED=true` gets it. It gets its own
`herdr-config` volume (`/home/agent/.config/herdr`), pre-created and
owned by the `agent` user the same way `claude-config`/`gemini-config` are,
so session and settings state survives `docker compose down`/`up`.

**Herdr is the container's default foreground process.** `Dockerfile`'s
`CMD` changed from `bash` to `herdr`; the day-to-day workflow is now
`docker compose up -d && docker compose attach harness`. A plain shell (to
launch `claude`/`agy` directly without herdr managing them, or just to poke
around) is still one `docker compose exec harness bash` away.
`USER_GUIDE.md` §12 and the project `README.md.tmpl` Docker quickstart are
updated accordingly.

## v0.9.0

Adapters are now gated symmetrically in the dev container, the Antigravity
CLI gets a real permission policy, and `command_guard.py`'s container mode
is documented and considerably harder to walk around.

**Symmetric adapter gating.** `claude` previously contributed to
`docker-compose.yml` unconditionally: an `ADAPTERS_ENABLED=antigravity`
project still got a `claude-config` volume it could never use, while
`gemini-config` was correctly gated. Both adapters now sit behind matching
gates — `docker_agent_claude_compose` and `docker_agent_antigravity_compose`
(renamed from `docker_agent_antigravity_volumes`, since it now covers
environment variables too) — each controlling that adapter's config volume,
its `~/.claude` or `~/.gemini` mount point in `Dockerfile`, and for
antigravity the `ANTIGRAVITY_CONTAINER`/`CONTAINER_AUTO_ALLOW` variables.
The Dockerfile's config-directory pre-creation moved into the per-adapter
blocks alongside each CLI install.

**`claude-cache` is now `agent-cache`.** It mounts `/home/agent/.cache`,
which uv, pip and npm all write — the name was misleading, and it is
deliberately ungated, which also guarantees the top-level `volumes:` map is
never empty on a project with no adapters enabled.

**The compose project name is pinned.** `docker-compose.yml` now sets
`name:` from `PROJECT_NAME_LOWER`. Compose otherwise derives it from the
directory basename, so two checkouts in same-named directories would share
one set of auth/cache volumes and one container name. This also makes the
volume prefix agree with the `image:` tag, which already used that key.

**`command_guard.py` container mode: same posture, fewer holes.** Container
mode (introduced alongside the container work) reduces the policy to its
deny list, skipping force-ask so an agent can run unattended. That is
intentional and unchanged — but the deny list was carrying more weight than
it was built for, and several commands were silently allowed inside a
container whose `/workspace` is a bind mount of the host repo and whose
`ssh-agent` socket is the host's. Now denied, in both modes:

- `rm -rf` aimed at `..`, a bare `*`, `.`, `./`, `~`, or an absolute path,
  including with interposed flags such as `--no-preserve-root`. `rm -rf ..`
  from a subdirectory of `/workspace` deletes host files.
- `git push origin +main` — a force-push in refspec notation, matching
  neither `--force` nor `-f`.
- `git remote add`, which combined with an ordinary `git push` exfiltrates
  the repo under the host's forwarded git identity.
- `curl … && sh …` and `eval "$(curl …)"`. Only the literal `curl … | bash`
  pipe was caught before; `split_compound_commands` evaluates the halves of
  a chained form separately, and neither half is suspicious alone, so these
  are checked against the raw command line before splitting.

Also fixed a long-standing false positive: `rm -rf ./build` was denied by an
over-broad `./` alternative. `./` and `./*` are still denied.

**Container detection no longer keys on `/.dockerenv`.** That file exists in
*any* container — a VS Code devcontainer, a Docker-based CI job, a nested
`docker run` — each of which would have silently dropped the guard to
deny-list-only somewhere the operator never opted in. Detection is now the
two environment variables `docker-compose.yml` sets deliberately.

**The test suite is hermetic against its own feature.** Host-mode
assertions relied on ambient detection, so `ANTIGRAVITY_CONTAINER=1 pytest`
— i.e. running the suite inside the very container this targets, or in any
Docker-based CI — failed 7 pre-existing regression tests. Every host-mode
call now pins `in_container=False`, and the subprocess-based helper scrubs
both variables from the child environment. 24 tests pass identically with
neither variable set, with `ANTIGRAVITY_CONTAINER=1`, and with
`CONTAINER_AUTO_ALLOW=1`.

**`docker/antigravity_settings.json` is a new materialized file** (gated on
`DOCKER_ENABLED` **and** the `antigravity` adapter), copied into the image
at `~/.gemini/antigravity-cli/settings.json`. It carries the CLI's own
permission policy: flat `permissions.allow`/`.ask`/`.deny` arrays of
`command(...)`, `read_file(...)`, `write_file(...)`, `read_url(...)` and
`mcp(...)` rules. This is a **second, independent layer** from
`command_guard.py`, covering what the hook cannot see — reads of
`~/.ssh/**`, `~/.aws/**`, `**/.env*` and `**/*.pem`, writes to `.git/**` and
shell rc files, and URL fetches. Build/test commands render from
`TEST_CMD`/`PACKAGE_MANAGER_*_CMD` rather than being hardcoded.

### Upgrading

Re-render, then rebuild:

```bash
python3 .friday/setup/init_harness.py \
  --force-materialize=docker-compose.yml \
  --force-materialize=Dockerfile
docker compose down -v && docker compose build && docker compose up -d
```

`down -v` is required, not optional, for two reasons: `claude-cache` is
renamed (the old volume is orphaned, not migrated — no data loss, just a
cold cache), and a named volume is initialized from image content **only on
first creation**, so a pre-existing `gemini-config` volume will shadow the
new `settings.json` no matter how many times you rebuild. It also discards
stored logins, so expect to re-authenticate once.

If your project directory basename differs from `PROJECT_NAME_LOWER`, the
new `name:` pin changes your volume prefix; the old volumes are left in
place, orphaned, and can be removed with `docker volume rm` once you're
satisfied the new ones work.

## v0.8.1

Antigravity is now a fully wired adapter inside the dev container: its
credentials persist, and `AUTO_LAUNCH_AGENT` can actually launch it.

**Antigravity config persistence.** A `gemini-config` named volume is
mounted at `/home/agent/.gemini`, gated on a new
`docker_agent_antigravity_volumes` section so it appears in both the
service mount list and the top-level `volumes:` key only when
`ADAPTERS_ENABLED` includes `antigravity`. (A mount naming an undeclared
top-level volume is a hard `docker compose config` error, so the two must
be gated together.) `Dockerfile.tmpl` pre-creates `/home/agent/.gemini`
owned by `agent` for the same reason it already pre-creates `.claude` and
`.cache`: a named volume mounted onto a path the image doesn't own is
created root-owned by Docker and the non-root `agent` user can never
write it. `~/.gemini` is confirmed as the CLI's config root — the `agy`
binary carries hardcoded `/.gemini/antigravity-cli/settings.json` paths.

**Fixed: `AUTO_LAUNCH_AGENT=1` could never launch Antigravity.**
`docker/entrypoint.sh.tmpl` probed `PATH` for a binary named
`antigravity`, but the official installer creates exactly one binary and
names it **`agy`** (at `/home/agent/.local/bin/agy`); nothing named
`antigravity` is ever installed. On an antigravity-only project the probe
therefore always fell through to "no agent CLI found on PATH" and dropped
to a plain shell, with a working `agy` sitting on `PATH`. The probe list
is now `claude agy`, with a comment noting these are binary names rather
than adapter names. Projects with both adapters never saw this — `claude`
matches first and masks it.

`README.md`'s materialized-files table carried the same wrong binary
name and has been corrected.

**`--force-materialize` now accepts a repo-root-relative path**, not only
an absolute one, and **warns when an entry matches nothing**. Previously a
relative path — the form used in `USER_GUIDE.md` §12 and the v0.8.0 upgrade
note — was compared against an absolute `dest` and so never matched, and
the mismatch was reported in total silence: the run looked exactly like a
successful re-render while the file was left untouched. A typo behaved the
same way.

**Existing Docker-enabled projects** need `docker compose down` and a
re-render (`python3 .friday/setup/init_harness.py`) to pick up the new
entrypoint and volume; add `--force-materialize=docker/entrypoint.sh` if
a copy already exists, since materialized files are never overwritten in
place. No rebuild is required for the entrypoint alone, but adding the
`.gemini` pre-creation does need `docker compose build`.

## v0.8.0

Docker setup is now config-driven instead of one-size-fits-all, plus a
`USER_GUIDE.md` expansion landing in the same release.

**`Dockerfile` and `docker/entrypoint.sh` move from `symlinks` to
`materialize` in `MANIFEST.json`** — they're now rendered per-project
from `docker/Dockerfile.tmpl`/`docker/entrypoint.sh.tmpl`, not shared
byte-identical files. No new interview questions were added; the image
is driven entirely by existing `harness.config.env` keys:

- `PACKAGE_MANAGER` selects one package-manager install branch: `uv`,
  `poetry` (via pipx), `pip` (apt `python3-pip`+venv), or
  `npm`/`pnpm`/`yarn` (NodeSource + corepack). Anything else falls
  through to a "none" branch carrying a comment on where to hand-add
  conda/Miniforge.
- `ADAPTERS_ENABLED` selects agent CLI installs: `claude` pulls in
  NodeSource Node + `npm install -g @anthropic-ai/claude-code`;
  `antigravity` pulls in its official install script. Both, either, or
  neither.
- `LATEX_DRAFTING_ENABLED` now gates the TeX Live install, which used to
  default on via a host env var — several GB nobody outside the LaTeX
  suite wanted.
- `ACCELERATORS_ENABLED` gates the compose NVIDIA GPU device
  reservation.
- `docker-compose.yml`'s `.env` is now an optional `env_file`
  (`required: false`) and `SSH_AUTH_SOCK` tolerates being unset, so
  `docker compose config` succeeds on a fresh project with neither
  present.

Two real bugs were caught during verification and fixed:

- **Ubuntu 24.04 ships a default `ubuntu` user/group already at
  UID/GID 1000** — the default `USER_UID`/`USER_GID` here, and the UID/
  GID of most Linux desktop users. The old bare `groupadd -g 1000`
  build step collided with it and failed with exit 4. The Dockerfile
  now renames the incumbent user/group onto `agent` when the slot is
  taken, and only creates a fresh one when it's free.
- **The entrypoint's agent-CLI launch was render-time gated on
  `ADAPTERS_ENABLED`**, which produced an empty `if ...; then fi` — a
  bash syntax error that broke the container's entrypoint outright —
  whenever no adapter was enabled. It now probes `PATH` at runtime
  instead (`AUTO_LAUNCH_AGENT=1` tries `claude` then `antigravity`),
  which also means a CLI installed later is picked up without
  re-rendering.

- **Named volumes mounted root-owned.** `claude-config` and
  `claude-cache` mount at `/home/agent/.claude` and `/home/agent/.cache`,
  but neither path existed in the image — so Docker created both volumes
  owned by `root`, and the non-root `agent` user could never write them.
  `claude login` persistence, the documented reason the volume exists,
  had never actually worked. The image now pre-creates both directories
  owned by `agent` so the volume inherits that ownership on first mount.
  A project with pre-existing root-owned volumes needs one
  `docker compose down -v` to discard them.

**Existing Docker-enabled projects**: because `Dockerfile` and
`docker/entrypoint.sh` move from symlinked to materialized, pulling
this release alone does not update them in a project that already has
Docker enabled — `init_harness.py` never overwrites a materialized file
that already exists. Run `--force-materialize=Dockerfile
--force-materialize=docker/entrypoint.sh` (or reconfigure) to pick up
the new, parameterized versions, then `docker compose build` again.

`README.md`, `README.md.tmpl`, and `AGENTS.md.tmpl` updated to describe
the new materialized Docker files and their gating; `harness/
USER_GUIDE.md` gained a corresponding operator-facing expansion in this
same release, covering day-to-day use of the now-configurable image.

## v0.7.0

Alignment pass closing the gap between a freshly generated friday harness
and heimdall's own, live one.

**The three missing harness state files now exist.** `harness/status.md`,
`harness/status_history.md`, and `harness/log.md` were referenced 52 times
across `harness.md.tmpl`, all seven role contracts, five rules docs,
`README.md.tmpl`, `AGENTS.md.tmpl`, `check_md_hygiene.py`'s `FILE_CAPS`, and
`init_harness.py`'s own closing checklist — but were absent from
`MANIFEST.json` entirely, so a fresh project's central rule-3 invariant
pointed at a file that did not exist. All three are now `materialize`
entries seeded from heimdall's live files, with project bodies emptied to
`_(none)_`/`(none yet)` and tracker/accelerator wording gated the same way
as everywhere else.

**Fixed `check_md_hygiene.py` silently no-op'ing in every consumer
project.** Its `REPO_ROOT` was computed as
`Path(__file__).resolve().parents[2]`; reached through the `.claude/hooks/`
symlink, `.resolve()` followed the link into `.friday/adapters/hooks/`,
landing `REPO_ROOT` on `.friday/` itself instead of the consumer repo. Every
capped path then missed `path.exists()` and was silently skipped — the
pre-commit hook and the Planner/Reviewer pass-start hygiene check both
looked healthy while checking nothing. Confirmed live in heimdall before
the fix. Replaced with an upward search for the consumer repo root (a
directory containing `harness.config.env`, or failing that `.gitmodules` +
`.friday/`), matching the convention `harness/tools/_config.py` already
documents. **This is a behavioral change for every existing consumer
project**: the checker was silently passing before and will now actually
report files over their line cap. Added
`adapters/hooks/test_check_md_hygiene.py` as a regression guard for the
exact symlink-resolution failure that shipped silently.

**`command_guard.py` is no longer hardcoded to `uv`/`latexmk`.** Its
allow-list and force-ask patterns now derive from `harness.config.env`
(`PACKAGE_MANAGER_SYNC_CMD`, `PACKAGE_MANAGER_RUN_CMD`, `TEST_CMD`,
`PACKAGE_MANAGER_ADD_CMD`, and LaTeX patterns only when
`LATEX_DRAFTING_ENABLED=true`) instead of literal `uv`/`latexmk` strings, so
a poetry/npm project gets a real allow-list instead of everything degrading
to `force_ask`. Falls back to today's `uv`+LaTeX literals if
`harness.config.env` is missing or unparseable, so behavior never regresses
before setup writes a config.

Two follow-on defects in that derivation were caught in review and fixed:

- The upward search stopped at the first directory containing a `.git`
  entry. In a submodule `.friday/.git` is a *file*, so any invocation whose
  cwd sat inside `.friday/` hit that boundary, found no config, and fell
  through to the `uv`+LaTeX fallback — auto-allowing `uv sync` and `latexmk`
  on a project that uses neither, while pushing that project's own commands
  to `force_ask`. A guardrail silently enforcing a *different* project's
  policy is worse than one that is merely absent. The boundary break is
  gone, and the search now tries cwd first and then the *unresolved*
  `Path(__file__).parent` (the symlink's own directory), matching
  `check_md_hygiene.py`'s `find_repo_root()`. Regression test added.
- Deriving purely from config was narrower than the hardcoded list it
  replaced: `uv lock` and a bare `pytest` (the old pattern matched
  `^(uv\s+run\s+)?pytest`) both silently lost their auto-allow. Safe
  lockfile/refresh verbs are now derived per package manager, and when
  `TEST_CMD` is `RUN_CMD` plus a runner, the bare runner is allowed too.
  This gap was invisible to the original test suite because the `.git`
  boundary above meant those tests never found a config and only ever
  exercised the fallback path.

**`init_harness.py`/`MANIFEST.json`**: `docker_quickstart` and
`lfs_policy` SECTION axes are now gated (`DOCKER_ENABLED`,
`LATEX_DRAFTING_ENABLED`) instead of shipping into every project
regardless of whether Docker or the LaTeX suite are in use;
`harness/running/logs/` is now created at sync (the directory
`environment.md.tmpl` already documents launches redirecting into);
`closing_checklist()`'s marker scan now covers `docs/**/*.md`, not just
`harness/**/*.md` + `AGENTS.md` + `README.md`; ships
`setup/gitignore.fragment` and `setup/gitattributes.fragment`, applied by
appending missing lines idempotently — never rewriting a consumer's
existing file — covering secrets, gitignoring
`harness/plans/directives/*.md` (with `!TEMPLATE.md` kept tracked), and
LaTeX/reference artifacts when those axes are enabled.

**Template prose**: `README.md.tmpl` gained the LaTeX build section
(`latexmk` commands under `docs/{theory,report}/<content-slug>/`) that
every other doc already gated on the LaTeX axis but this one had lost;
`environment.md.tmpl` no longer leaves a blank gap when the non-matching
launch-method section is dropped, and keeps a two-line cross-reference to
the other launch patterns so a systemd project doesn't lose the
`setsid`/`nohup` fallback knowledge entirely; `AGENTS.md.tmpl`'s
command-guard bullets now render the real `PACKAGE_MANAGER_*` tokens
instead of `[SET AT SETUP: ...]` placeholders, matching what B2's
config-driven `command_guard.py` actually does; `docs/ARCHITECTURE.md.tmpl`'s
source-dir marker is now a single clean `[SET AT SETUP: ...]` the closing
checklist's `docs/**/*.md` scan will surface; removed heimdall-specific
text (`JAX`, "David") from `USER_GUIDE.md` and the bibliography tool
docstrings, which are symlinked unmodified into every project.

**`setup/SETUP.md`**: fixed heading numbering after the "Detached
background jobs" topic moved later in the interview order; replaced the
`.gitignore`-correctness hand-wave with a description of the new
fragment-based mechanical behavior; the closing description of what setup
produces now accounts for the three new state files, `harness/running/
logs/`, and the `.gitignore`/`.gitattributes` step.

**Also caught in review**: the `docker_quickstart` block in
`README.md.tmpl` carried a comment claiming `init_harness.py` fills in the
compose commands, which it never did — gating it on `DOCKER_ENABLED` fixed
the non-Docker case but left the false claim shipping to every *Docker*
project, so the block now holds the real `docker compose`
build/up/exec/down commands. Two more blank-gap bugs of the same shape as
`environment.md.tmpl`'s were fixed in `task_tracking.md.tmpl` (between the
gated tracker sections) and `author.md.tmpl` (between the gated LaTeX
sections). Remaining heimdall-specific text was genericized in
`harness/roles/researcher.md.tmpl` ("David" → "the operator", three
places) and `version_control.md.tmpl`'s commit-message examples, both of
which are shared across every consumer project.

## v0.6.0

Consumer projects now get a templated `docs/` and `harness/{coding,plans}/`
scaffold instead of inventing that shape from scratch on first use — the
same "make it a real template axis, not implicit convention" move already
applied to the LaTeX suite (v0.5.0) and GPU support (v0.3.0).

New materialized starters (each rendered once at setup, never re-synced —
hand-edit freely afterward): `docs/RESULTS.md`, `docs/ARCHITECTURE.md`,
`docs/references/needs_pdf.md` (its "do not cite" wording is `latex_on`/
`latex_off`-gated, same mechanism as the role files), and blank-skeleton
`harness/coding/{tasks_working,tasks_finished,history}.md` +
`harness/plans/{next_steps,suggestions,goals,long_term,history}.md`. New
symlinked (pure generic, zero project content) namespace READMEs:
`harness/{research,review,running}/README.md` and `docs/references/
inbox/README.md`. New `LATEX_DRAFTING_ENABLED`-gated materialized files:
`docs/theory/README.md` and `docs/report/README.md`, documenting the
self-contained-latexmk-project convention on disk instead of only in role
prose. `materialize_files()` gained a `"latex"` manifest-entry gate
(mirrors the existing `"accelerators"`/`"docker"` gates); `AGENTS.md.tmpl`
gained a `latex_on`-gated "LaTeX/Beamer drafting suite" project-facts row;
`closing_checklist()`'s LaTeX reminder is now a real presence check instead
of an unconditional TODO line.

`docs/AGENTS.md.tmpl` and `docs/README.md.tmpl` move to this repo's root
(`AGENTS.md.tmpl`, `README.md.tmpl`) — `docs/` was only ever holding those
two unrelated files, and freeing it up lets it literally mirror a consumer
project's real `docs/` tree instead of colliding with it.

## v0.5.0

Makes the LaTeX/Beamer drafting suite (`docs/theory/` for the Researcher,
`docs/report/` for the Author, self-contained `latexmk` projects citing the
shared `docs/references/references.bib`) an optional, config-gated axis
instead of content hardcoded into files that were supposed to be
byte-identical across every project — the same bug class already fixed
once for GPU support. New `LATEX_DRAFTING_ENABLED` key (SETUP.md §9,
alongside the bibliography-tooling questions, which stay unconditional —
the references/inbox/`.bib` workflow was already generic and needed no
change).

`harness/roles/researcher.md`, `author.md`, and `reviewer.md` move from
plain `symlinks` entries to `materialize`/`.tmpl` entries in
`MANIFEST.json`, each gaining `<!-- SECTION:latex_on/latex_off:start/end
-->` variants (mirrors `harness.md`'s `accel_none`/`accel_present` split).
With the suite off, Researcher and Author keep every other duty (memos,
citations, `docs/RESULTS.md`) — their "formal writeup" output is just a
Markdown doc instead of a separate LaTeX project. `init_harness.py` gained
`LATEX_SECTIONS` + a `sections_to_drop()` branch, an interview question,
and a closing-checklist reminder (LFS/`docs/theory,report` setup) when
enabled. The Claude/Antigravity adapter `description:` frontmatter for
these two roles was reworded to be true either way, rather than templated
— those files stay symlink-source.

## v0.4.1

Documentation only. Replaced README's terse "see MANIFEST.json" pointer
with an actual inline breakdown of every symlinked and materialized path,
grouped by directory, generated from and cross-checked against
`MANIFEST.json` — plus a "real project data" section listing what friday
never touches. Points back to `sync_symlinks()`/`materialize_files()` in
`setup/init_harness.py` as the code that implements it.

## v0.4.0

`USER_GUIDE.md` is now a generic, non-templated file living at this repo's
root — symlinked into every consumer project as `harness/USER_GUIDE.md`
instead of being materialized from a per-project `.tmpl`. It's readable
natively on GitHub, updates automatically the moment a project's `.friday/`
checkout advances (no re-materialize step), and never drifts per project.
Project-specific operational content that used to live in it (results doc
path, tracker specifics, project layout) moved to `AGENTS.md`, which already
carries per-project facts — added a `Docker dev container` row there too.
Expanded the guide's Docker section into a full lifecycle walkthrough:
installing Docker, building the image, entering the container, day-to-day
workflow, and adding volumes later. Removed `init_harness.py`'s
`write_user_guide_docker_section()` (the per-project auto-refreshed Docker
blurb it maintained no longer applies to a shared, symlinked file).

`README.md` expanded with a full getting-started walkthrough and a new
"Updating the harness" section documenting both the plain git-submodule
update sequence and the `harness_sync.sh` convenience wrapper, including
the exact one-liner to add the project-owned `harness.sh` entry point that
was previously only mentioned, never actually explained.

Fixed a false positive in `closing_checklist()`: it was scanning symlinked
(shared, generic) `.md` files for leftover `[SET AT SETUP: ...]` markers,
which would flag `USER_GUIDE.md` forever since its Docker section
legitimately mentions that placeholder syntax in prose. Symlinked files are
now skipped — only materialized per-project files can have a genuine
unfilled placeholder.

## v0.3.0

Restores functionality dropped during the original `SETUP.md` migration
(caught by diffing against the pre-migration interview):

- GPU/accelerator support as a real template axis again: `harness/rules/gpu.md.tmpl`
  (device table + allocation policy), `harness/harness.md` now templated
  (`harness.md.tmpl`) with `accel_none`/`accel_present` section variants for
  rules 10/14, and `environment.md.tmpl`'s accelerator note now
  auto-drops/keeps with the same `ACCELERATORS_ENABLED` key. New SETUP.md §4.
- `check_agent_spawn.py`'s `HIGH_TIER_KEYWORDS` now reads
  `HIGH_TIER_MODEL_KEYWORDS` from `harness.config.env` at hook run time
  instead of a hardcoded tuple the interview's answer never reached.
- SETUP.md §2 (repository layout) restored — writes into `AGENTS.md`
  §Repository Layout and reviews `.gitignore`.
- `closing_checklist()` restored to parity with the original: fixed a bug
  where the leftover-marker scan only matched ALL-CAPS token placeholders
  and silently missed free-text `[SET AT SETUP: ...]` prose markers; added
  reminders for the md-hygiene hook, `status.md` accuracy, opening a first
  directive, and recording surprises in `harness/log.md`.

## v0.2.0

Restores `setup/SETUP.md` as the full agent-led conversational interview
(judgment, adaptive questioning, real setup actions) that writes
`harness.config.env` and hands off to `init_harness.py` for the mechanical
work — this was referenced in docs from v0.1.0 but never actually written.

## v0.1.1

Fixes a `REPO_ROOT` symlink-resolution bug: `Path(__file__).resolve()`-based
root-finding in the bibliography tools followed symlinks into `.friday/`
instead of resolving to the consumer project. Replaced with an
upward-search-from-`cwd()` `find_repo_root()` in `harness/tools/_config.py`.

## v0.1.0

Initial extraction from the Heimdall project's harness. Portable core
(`harness.md`, role contracts, generic rules, both adapters' hooks/agent
definitions), templated project-specific docs (`environment.md`,
`task_tracking.md`, `version_control.md`, `USER_GUIDE.md`, `AGENTS.md`,
`README.md`, bibliography-tool template), config-driven bibliography
tooling, consolidated hook implementations (fixes the `.claude/` vs.
`.agents/` hook drift), `init_harness.py` setup/sync script, and a Docker
dev-container setup (Ubuntu base, Claude Code CLI inside the container).
