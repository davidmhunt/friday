# Runtime: ./run and the dev container

Claude Code runs on the host. Builds, tests and scripts go through a project's `./run`, which sends
them into a dev container or runs them natively, per machine. This keeps environments identical
across machines without running Claude inside a container (and without Docker-in-Docker).

The reference implementation is in CPSL_TI_Radar: `run`, `docker/dev/Dockerfile`,
`docker/dev/compose.yaml`, `tools/check.sh`. Copy them and change the image's packages.

| Choice | Why |
|---|---|
| One long-lived container per checkout, exec into it | About 0.2 s per command once warm; a worktree gets its own container and venv |
| Runs as the checkout owner's uid/gid | Files the container writes are yours; tests that check ownership pass |
| Repo mounted at the same absolute path | Paths in errors, logs and the CMake cache read the same on both sides |
| venv and uv cache in volumes | The host's `.venv` and the container's never overwrite each other; `uv run` syncs from `uv.lock` |
| `docker/dev/compose.override.yaml` (gitignored) | Per-machine devices, host networking, a proxy CA |
| `FRIDAY_RUNTIME=native` or `~/.config/friday/runtime` | Machines without Docker run the same commands directly |

In `.claude/friday.json`, `run_only` lists the tools that must go through `./run`; the hook
refuses the bare form and names the wrapped one.
