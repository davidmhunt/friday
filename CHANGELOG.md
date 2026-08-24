# Changelog

## v0.1.0

Initial extraction from the Heimdall project's harness. Portable core
(`harness.md`, role contracts, generic rules, both adapters' hooks/agent
definitions), templated project-specific docs (`environment.md`,
`task_tracking.md`, `version_control.md`, `USER_GUIDE.md`, `AGENTS.md`,
`README.md`, bibliography-tool template), config-driven bibliography
tooling, consolidated hook implementations (fixes the `.claude/` vs.
`.agents/` hook drift), `init_harness.py` setup/sync script, and a Docker
dev-container setup (Ubuntu base, Claude Code CLI inside the container).
