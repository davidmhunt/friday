# Docker dev container

The whole optional Docker lifecycle: install, image layout, setup, build, entering the container, day-to-day use, GPU, volumes and conversation history. Back to the [User Guide](../USER_GUIDE.md).

Running the harness (and the coding agent itself) inside a Docker
container limits a misbehaving agent's blast radius to the container and
the project volume, not the host machine — the image doesn't even have
`sudo` installed, so a compromised or confused agent inside the container
can't escalate to root there either. This is optional — most projects can
skip it — but if isolation matters here, this page covers the whole
lifecycle: installing Docker, building the image, entering the container,
day-to-day use, and (optionally) GPU passthrough.

Whether this project already has a Docker dev container set up, and how
it's configured, is project-specific state — check the `Docker dev
container` row in `AGENTS.md` § Project facts, or `DOCKER_ENABLED` in
`harness.config.env` at the repo root.

## 1. Install Docker (one-time, per machine)

Skip this if `docker --version` and `docker compose version` already work.

- **Linux**: install Docker Engine + the Compose plugin via your distro's
  package manager, or the official convenience script:
  ```bash
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker "$USER"   # avoids needing sudo for every docker command
  ```
  Log out and back in (or `newgrp docker`) for the group change to apply.
- **macOS / Windows**: install Docker Desktop, which bundles Compose. Start
  it and make sure it's running before continuing.
- Verify: `docker run --rm hello-world` should pull and run successfully.

## 2. Two images and two compose files

The image is built in two stages, and the compose setup mirrors that split
exactly. Knowing which file does what matters before you touch any of the
commands below.

- **`docker/Dockerfile`'s `dev` stage** — base OS packages, the non-root
  `agent` user, the package manager this project uses, LaTeX (if enabled),
  and herdr — but **no agent CLI**. This is the project-owned stage: a
  teammate who cloned this repo *without* the `.friday/` submodule can
  still build and use it.
- **`docker/Dockerfile`'s `harness` stage**, `FROM dev`, layers Claude
  Code, the Antigravity CLI, and `entrypoint.sh` on top. This stage only
  matters to someone who actually has the submodule.
- **`docker/docker-compose.yml`** is project-owned and tracked in this
  repo's own git history — it builds `target: dev` and carries only the
  volumes a plain dev container needs (`herdr-config`, `agent-cache`, the
  bind mount, the SSH-agent forward). Nothing in it references anything
  harness-specific.
- **`docker/docker-compose.harness.yml`** is a gitignored Compose
  *override*, materialized whenever `DOCKER_ENABLED=true` — which, since
  it's `init_harness.py` that materializes it, only ever happens for
  someone who has the `.friday/` submodule checked out and ran setup
  through it in the first place. It stacks the `harness` build target on top,
  adds the agent-CLI config volumes (`claude-config`, `gemini-config`),
  and — when the Antigravity adapter is enabled — the
  `ANTIGRAVITY_CONTAINER`/`CONTAINER_AUTO_ALLOW` environment variables
  that put `command_guard.py` into container mode ([hooks.md](hooks.md)). Compose *merges*
  override files onto the base rather than replacing it, so this file is
  additive-only: build-target aside, it can only add keys the base file
  doesn't already declare.

`init_harness.py` also writes `COMPOSE_FILE=docker/docker-compose.yml:docker/docker-compose.harness.yml`
into the gitignored root `.env` whenever `DOCKER_ENABLED=true`, which is
what lets a plain `docker compose ...` (no `-f` flags) pick up both files
automatically for anyone who ran setup with the submodule present. A
teammate with no `.env` at all — never ran setup, or has no submodule —
gets *only* `docker/docker-compose.yml` and its agent-CLI-free `dev`
image, and needs the explicit `-f docker/docker-compose.yml` form for
exactly that reason: there is no `COMPOSE_FILE` telling their shell about
an override file that, for them, doesn't exist. Every command in the rest
of this section assumes the common case (`.env` present, `COMPOSE_FILE`
set) and is written as plain `docker compose ...`; if you're deliberately
working with the `dev` stage alone, add `-f docker/docker-compose.yml`
back to pin it.

## 3. Set up the project's Docker files

**Preferred path — through the setup interview:** point an agent at
`.friday/setup/SETUP.md` and go through [User Guide, Where things live](../USER_GUIDE.md#where-things-live) (Docker). It asks whether to set
up Docker, any extra host volumes to mount beyond the project directory
itself (a datasets dir, a shared model cache), and whether to build the
image right away. It renders `docker/Dockerfile`, `docker/entrypoint.sh`,
`docker/antigravity_settings.json` (if the Antigravity adapter is on), and
`docker/docker-compose.yml`, materializes the gitignored
`docker/docker-compose.harness.yml` override, creates the `docker/.env`
symlink (see below), and writes `COMPOSE_FILE` into the root `.env` (see
[section 2](#2-two-images-and-two-compose-files)) — all Docker inputs end up together under `docker/` at the repo
root.

**By hand instead:** render `.friday/templates/docker/.dockerignore.tmpl`
to `.dockerignore` at the repo root (Compose reads it from the
build-context root, not from `docker/`), and render every other
`.friday/templates/docker/*.tmpl` file to its matching path under `docker/` —
filling in setup-time placeholder tokens
and dropping the `<!-- SECTION -->` blocks that don't match this project's
`PACKAGE_MANAGER`, `ADAPTERS_ENABLED`, `LATEX_DRAFTING_ENABLED`, and
`ACCELERATORS_ENABLED` by hand. Also symlink `docker/.env` to `../.env`
(see the warning in [section 5](#5-build-the-image)) and write the `COMPOSE_FILE` line into the root
`.env` yourself — `init_harness.py` does both automatically on the
interview path. `docker/Dockerfile`, `docker/entrypoint.sh`, and
`docker/antigravity_settings.json` are materialized (real per-project
files, not symlinks) precisely so those choices can be baked in per
project — see [section 4](#4-what-the-image-is-built-from-and-reconfiguring-it).

Before starting the container for the first time, run `ssh-add` on the
**host** so the container's forwarded SSH agent can authenticate to your
git remote — the container doesn't get its own copy of your SSH key, it
forwards the host's running agent.

## 4. What the image is built from, and reconfiguring it

The whole image is driven by keys already in `harness.config.env` — no
extra Docker-specific setup questions get asked beyond what SETUP.md
already covers:

- **`PACKAGE_MANAGER`** installs the matching toolchain, **in the `dev`
  stage** (so it's present even for a teammate without the submodule):
  `uv` (official installer), `poetry` (via pipx), `pip` (apt `python3-pip`
  + `venv`), or `npm`/`pnpm`/`yarn` (NodeSource Node.js + corepack). `none`
  leaves a commented placeholder in `docker/Dockerfile` marking where to
  add one.
  > [!WARNING]
  > **conda is a deliberate manual edit, not an auto-generated option.**
  > If `PACKAGE_MANAGER` is conda (or anything else the template doesn't
  > recognize), the `none` branch of `docker/Dockerfile` carries a comment
  > with a ready-made Miniforge install snippet — copy it in and add its
  > `bin` directory to the image's `PATH` by hand.
- **`ADAPTERS_ENABLED`** selects the agent CLI(s) — installed in the
  **`harness` stage only**, and each adapter is gated symmetrically,
  contributing to both `docker/Dockerfile`'s `harness` stage and
  `docker/docker-compose.harness.yml` only when it's enabled. Both,
  either, or neither:

  | | `claude` | `antigravity` |
  |---|---|---|
  | CLI install | Node.js + `@anthropic-ai/claude-code` (lands at `/home/agent/.npm-global/bin/claude`) | official install script (lands at `/home/agent/.local/bin/agy` — the binary is `agy`, there is no `antigravity` binary) |
  | Config volume | `claude-config` → `/home/agent/.claude` | `gemini-config` → `/home/agent/.gemini` |
  | Pre-seeded config | none | `docker/antigravity_settings.json` → `~/.gemini/antigravity-cli/settings.json` |
  | Environment | none | `ANTIGRAVITY_CONTAINER=1`, `CONTAINER_AUTO_ALLOW=1` (see [hooks.md](hooks.md)) |

  All four rows above live in `docker/docker-compose.harness.yml` (the
  gitignored override), not the base file — a teammate building `dev`
  alone never sees any of them. The `agent-cache` volume
  (`/home/agent/.cache`) is different: it's declared in the base
  `docker/docker-compose.yml` and **not** adapter-gated — uv, pip and npm
  all write there, so every project gets it regardless of which agent CLI,
  if any, is installed.
- **`LATEX_DRAFTING_ENABLED`** gates the TeX Live install
  (`texlive-latex-extra`, fonts, `latexmk`) in the `dev` stage — several
  GB, only pulled in when this project's config asks for it.
- **`ACCELERATORS_ENABLED`** gates an NVIDIA GPU device reservation in the
  base `docker/docker-compose.yml` — see [section 8](#8-gpu-passthrough).
- **Herdr** (`herdr.dev`, a terminal workspace manager for AI coding
  agents) installs **unconditionally, in the `dev` stage** — unlike the
  adapter CLIs above it isn't gated on any `harness.config.env` key, since
  it wraps whichever agent CLI(s) happen to be on `PATH` rather than being
  tied to one, and it's useful even without the harness submodule. It gets
  its own `herdr-config` volume (`/home/agent/.config/herdr`, declared in
  the base compose file) so sessions and settings persist across
  `docker compose down`/`up`. It is not the container's default foreground
  process — run it by hand — see [section 6](#6-start-and-enter-the-container).

> [!WARNING]
> **Reconfiguring requires a rebuild — and a re-render first.** These
> choices are baked into `docker/Dockerfile` at *render* time, not chosen at
> `docker compose build` time. Changing `harness.config.env` alone does
> nothing to an already-rendered `docker/Dockerfile`. After changing config:
> ```bash
> python3 .friday/setup/init_harness.py --force-materialize=docker/Dockerfile
> docker compose build
> ```
> (`--force-materialize` is needed because `docker/Dockerfile` is a
> materialized, per-project file that may carry hand-edits — see [updating.md](updating.md) — so a
> plain re-run won't silently overwrite it.)

## 5. Build the image

From the repo root:

```bash
docker compose build
```

With `COMPOSE_FILE` set ([section 2](#2-two-images-and-two-compose-files)), this builds the `harness` stage/image —
`Dockerfile`'s `dev` stage plus whichever agent CLI(s) `ADAPTERS_ENABLED`
selected. It installs Ubuntu 24.04, git, build tooling, the package manager
from `PACKAGE_MANAGER` ([section 4](#4-what-the-image-is-built-from-and-reconfiguring-it)) and herdr, and creates a non-root `agent`
user matching your host UID/GID, so files the container writes come out
owned by your host user, not root (agent CLI locations are in [section 4](#4-what-the-image-is-built-from-and-reconfiguring-it)). Expect a
few minutes the first time; rebuilds are cached and fast unless
`docker/Dockerfile` itself changed. To build the agent-CLI-free `dev` image alone (e.g. to confirm it
still works standalone for a submodule-less teammate), pin the base file
explicitly: `docker compose -f docker/docker-compose.yml build`.

`docker compose config` works even with no `.env` file present and
`SSH_AUTH_SOCK` unset on the host — `.env` is loaded as `required: false`,
so a fresh checkout with neither doesn't block you from at least
validating the compose file before you set either up. (Without a `.env`
at all, that's `docker compose -f docker/docker-compose.yml config` — no
`COMPOSE_FILE` has been written yet either, so there's nothing for a plain
`docker compose config` to find.)

> [!WARNING]
> **`.env` lives at the repo root, but Compose looks for it next to the
> compose file.** All Docker inputs — `Dockerfile`, both compose files,
> `entrypoint.sh`, `antigravity_settings.json` — live together under
> `docker/`, and Compose resolves relative paths (and a bare `.env`)
> against that directory, not the repo root. Without `docker/.env`
> resolving to the real `.env` at the repo root, a project's `.env` would
> be silently ignored: `${USER_UID}` falls back to `1000`, breaking
> bind-mount file ownership for any host user whose UID isn't 1000. Setup
> handles this for you — `init_harness.py` creates `docker/.env` as a
> relative symlink to `../.env` whenever `DOCKER_ENABLED=true` — so this
> only matters if you're wiring the Docker files up by hand ([section 3](#3-set-up-the-projects-docker-files)) or the
> symlink has gone missing.

## 6. Start and enter the container

The container's default foreground process is a **plain shell**, not herdr:

```bash
docker compose up -d          # start the container, detached
docker compose attach harness # attach to the shell
```

Detach from `attach` with the usual Docker sequence (`Ctrl-p Ctrl-q`), or
just `exit`/`Ctrl-d` the shell — either way the container keeps running,
since a shell has no session state worth preserving. `docker compose attach`
requires a real terminal on the host — it refuses to attach when stdin isn't
a TTY (e.g. run from a script). Equivalently, from another terminal:

```bash
docker compose exec harness bash
```

Inside the container, the project directory is bind-mounted at
`/<project name>` (the same `PROJECT_NAME_LOWER` token that pins the
compose project name and image tags) and is writable — edits made on the
host appear instantly inside the container and vice versa, files written
from inside the container come out owned by your host user (not root),
and nothing is copied. From the shell:

```bash
claude                        # start Claude Code inside the container
# or:
agy                           # start Antigravity CLI inside the container
# or, non-interactively:
claude login                  # first time only, if not using ANTHROPIC_API_KEY
# or, to manage multiple agent panes in one session:
herdr
```

Herdr is installed but **not** the default foreground process, deliberately:
when it is the container's own PID-2 process, detaching from
`docker compose attach` (rather than backgrounding herdr from inside it)
kills herdr, and with it the whole container — there's no plain-shell
fallback to land back in. Run `herdr` by hand from the shell above instead;
if you background or exit it, the shell (and container) are still there.

**Auth persistence**: named volumes (`claude-config` at `/home/agent/.claude`,
`gemini-config` at `/home/agent/.gemini`, each present only when its adapter
is enabled) persist your `claude login` and `agy` credentials and sessions
across `docker compose down`/`up` cycles, so you only authenticate once per
machine. `herdr-config` at `/home/agent/.config/herdr` does the same for
herdr's own settings and session/workspace state, unconditionally. The image
pre-creates each of those paths, plus `/home/agent/.cache`,
owned by the `agent` user before the volumes ever mount — a named volume
mounted onto a path the image doesn't already own is otherwise created
root-owned by Docker, which the non-root `agent` user can't write, silently
breaking persistence. Claude Code's own main config file, `~/.claude.json`,
is a *sibling* of the `.claude/` directory `claude-config` mounts rather
than a member of it, so it's symlinked into the volume-backed directory at
build time — without that, it would live on the container's throwaway
layer and a recreated container would look logged-out (the OAuth token
survives in `.claude/.credentials.json`, but everything else
`.claude.json` tracks would silently fall back to a stale copy or a fresh
default). Alternatively, set `ANTHROPIC_API_KEY` (or relevant API keys) in
`.env` at the repo root for non-interactive auth.

**Volume names are per-project.** Compose prefixes every named volume with
the project name, which both compose files pin to `PROJECT_NAME_LOWER`
(`heimdall_claude-config`, and so on). Two projects on the same machine
never share auth or cache volumes, and you don't need to name them
uniquely yourself. The pin matters because Compose's *default* project
name is the directory basename — without it, two checkouts in directories
that happen to share a basename would silently share one set of volumes
and one container name.

> [!WARNING]
> **A named volume is initialized from image content only the first time it
> is created.** Rebuilding the image does *not* refresh files inside a volume
> that already exists — most visibly, a change to
> `docker/antigravity_settings.json` won't reach
> `~/.gemini/antigravity-cli/settings.json` in an existing `gemini-config`
> volume just by rebuilding the image. This is not the problem it sounds
> like in practice: `entrypoint.sh` re-syncs that one file from the
> bind-mounted repo on every container start, so a plain
> `docker compose up -d` (or a restart) is enough to pick up a change
> there — **do not reach for `down -v`** for this or any other "a volume
> isn't picking up a change" situation. `-v` discards the named volumes,
> and those volumes hold **all** Claude Code and Antigravity conversation
> history for this project, plus your stored logins — there is no undo.
> The one case that still legitimately needs it is a volume left
> **root-owned** from before this project's ownership fix ([section 6](#6-start-and-enter-the-container)) was in
> place, since nothing short of discarding it fixes that. If you're in
> that situation:
> ```bash
> docker compose down -v   # DESTROYS all conversation history and logins in these volumes — no undo
> docker compose up -d
> ```

## 7. Day-to-day workflow

- **Resume work**: `docker compose up -d && docker compose attach harness` — the container and its named volumes (auth, caches, herdr session state) persist between sessions; you're not rebuilding or re-authenticating each time. Run `herdr` from the shell this drops you into if you want it.
- **Detached background jobs** (training runs, long evals) inside the container use the same `setsid nohup ... & disown` pattern as a bare SSH box (see `.friday/active/harness/rules/environment.md`) — the container has no systemd user manager, but Compose's `init: true` runs tini as PID 1, which reaps zombies from detached jobs the same way systemd would on a bare host.
- **Stop the container**: `docker compose down` — the bind-mounted project directory is untouched (it's your host filesystem), and named volumes (auth, caches) survive; only the container itself is removed. Never add `-v` here out of habit — see the warning in [section 6](#6-start-and-enter-the-container).
- **Pick up a `docker/Dockerfile` or `docker/antigravity_settings.json` change**: for `antigravity_settings.json`, a plain `docker compose up -d` (or a restart) is enough — `entrypoint.sh` re-syncs it. For `Dockerfile`: `docker compose build && docker compose up -d`.
- **Multiple shells**: `docker compose exec harness bash` again from another terminal — you're not limited to one shell per running container.
- **Just the `dev` stage, no agent tooling** (e.g. reproducing what a submodule-less teammate gets): pin the base file explicitly throughout — `docker compose -f docker/docker-compose.yml up -d`, `... attach harness`, `... down`, and so on. Nothing above assumes you have the submodule; it's only the *default*, unqualified `docker compose` invocations that pick up the harness override, and only because `COMPOSE_FILE` is set in `.env`.

## 8. GPU passthrough

Gated on `ACCELERATORS_ENABLED` in `harness.config.env` ([section 4](#4-what-the-image-is-built-from-and-reconfiguring-it)) — when on,
the base `docker/docker-compose.yml` requests an NVIDIA GPU device
reservation for the container.

Requirements on the **host** (not inside the container): the [NVIDIA
Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
must be installed and configured.

Verify passthrough with:

```bash
docker run --rm --gpus all ubuntu:24.04 nvidia-smi -L
```

A correctly configured host prints the GPU list.

> [!WARNING]
> **`docker info` is a misleading test here.** A modern NVIDIA Container
> Toolkit works via CDI (Container Device Interface) rather than the older
> Docker runtime-registration mechanism, so `docker info` may show no
> `nvidia` entry under Runtimes even when GPU passthrough is fully working.
> Use the `docker run --gpus all ... nvidia-smi -L` command above to check
> — don't conclude anything from `docker info` either way.

## 9. Adding a volume later

A datasets directory, a shared model cache, anything outside the project
directory: either re-run the SETUP.md interview's Docker section, or edit
the `# --- user-added volumes (managed by init_harness.py) ---` block in
`docker/docker-compose.yml` directly — the same block `init_harness.py
--reconfigure` manages, so manual edits and future re-runs don't fight
each other.

## 10. Conversation history: host vs. container are separate

Claude Code and Antigravity both key their stored conversation history off
the current working directory, and inside the container that config lives
in the named volumes from [section 6](#6-start-and-enter-the-container) (`claude-config`, `gemini-config`) — not in
your host `~/.claude`/`~/.gemini`. A conversation started **inside** the
container is bucketed under the container's own path (`/<project name>`)
and stored in the container's volumes; a conversation started **on the
host** is bucketed under the host's path and stored in your host home
directory. The two are deliberately isolated: neither copy is lost, but
neither shows up in the other's `--resume`/`--continue` list, because the
bucket key (the working-directory path) differs even though it's "the same
project" to you.

Concretely: don't read an empty history on first entering a fresh container
as data loss. Your host-side history is still exactly where it was; the
container simply hasn't accumulated any of its own yet. Likewise, work done
inside the container stays there across `docker compose down`/`up` (the
volumes persist — see [section 6](#6-start-and-enter-the-container)) but won't appear if you run `claude --resume`
or `agy`'s equivalent from the host.
