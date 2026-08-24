# Setup — run this before the first real session

This is the entry point for configuring `friday` in a project. **Point
your coding agent (Claude Code, Antigravity, or any other) at this file**
and say *"walk me through `.friday/setup/SETUP.md`."* That's the intended
path — the interview needs judgment (recommending defaults, taking real
setup actions, adapting when an answer makes a question moot) that a
non-interactive script can't provide on its own. A human can also answer
these questions solo and hand-write `harness.config.env`, or run
`python3 .friday/setup/init_harness.py` directly for its own bare
`input()`-prompt interview — but the agent-led path is preferred.

**This interview is also how you reconfigure later.** Nothing here is
one-shot: re-open this file any time a project fact changes (switched
package managers, added a task tracker, want Docker now). If
`harness.config.env` already exists, treat its values as defaults —
confirm or change each one, don't force the user to re-answer everything
from scratch, and only touch the sections that actually need to change.

**How this interview ends:** every answer below maps to one key in
`harness.config.env` (a flat `KEY=value` file at the repo root — see the
exact key list in each section and `setup/harness.config.env.example`).
Once you have full answers for the sections in scope, **write
`harness.config.env` yourself** (Edit/Write tool, not the script's stdin
prompts), then run:

```bash
python3 .friday/setup/init_harness.py
```

Because `harness.config.env` already exists at that point, the script
skips its own interactive interview entirely and just does the mechanical
work: creates the symlink tree, materializes templated docs (substituting
every `[SET AT SETUP: ...]` token), wires the git hooks, and — if
`DOCKER_ENABLED=true` — writes `docker-compose.yml`'s volumes and offers to
build the image. That part is intentionally boring and deterministic; the
judgment belongs in the interview, not the script.

**Rules for the agent running this interview:**

- Ask about ONE topic at a time and wait for the answer. Don't batch every
  section into one wall of questions.
- **Assume nothing.** Not git, not GitHub/GitLab, not `uv`, not Docker, not
  that there's a task tracker at all. "We don't use one" is a valid, common
  answer (`TRACKER_KIND=none`) and must be recorded as such — not quietly
  worked around.
- **Take real setup actions when asked, never silently.** If the user says
  "we want `uv` but haven't set it up," offer to run `uv init` for them —
  but confirm before running anything that creates or changes state outside
  this interview (initializing a package manager, running `git init`,
  creating a remote issue-tracker project, etc.). Recording an answer and
  *acting* on it are different steps; don't blur them without asking.
- Where the user is unsure, offer the trade-off in one sentence and
  recommend a default — don't present a survey.
- If an answer makes a later question moot (e.g. "no external tracker"),
  skip it and say why, rather than asking anyway.
- At the end, re-read `harness.config.env` and confirm every key below has
  a real value (or a deliberate empty one, e.g. `VCS_REMOTE=` if there's
  genuinely no remote yet) before invoking `init_harness.py`.

---

## 1. Project identity

- What is this project called, and what is it trying to accomplish? (Two or
  three sentences — a new agent reads this first, cold.)
- What's the absolute path of the repo/working root?

→ `PROJECT_NAME`, `PROJECT_NAME_LOWER` (derived — lowercase, spaces to
hyphens, don't ask separately), `PROJECT_WORKING_ROOT`. Also feeds the
free-text `[SET AT SETUP: ...]` prose in `AGENTS.md` (Project Overview) and
`README.md` (Overview) once materialized — write that prose yourself from
the answer, `init_harness.py` only substitutes literal tokens.

## 2. Repository layout

- What are this project's top-level directories, and what lives in each
  (source, notebooks, data, docs, generated output)?
- Which paths are generated/large/excluded from version control — is
  `.gitignore` already correct, or does it need entries added?

→ No config key — this is free-text prose written directly into `AGENTS.md`
§Repository Layout once materialized (the `harness/` row is already filled
in by the template; add the project's own rows above it). If `.gitignore`
needs new entries, edit it directly as part of this step.

## 3. Running code

- What language(s), and how is the environment managed — `uv`, `pip`,
  `poetry`, `npm`, conda, a container, nothing at all? If it needs
  initializing (no `pyproject.toml`/`package.json` yet), offer to do that
  now.
- What are the sync/install, run, add-dependency, and test commands?
- What's the dependency manifest and lockfile (if any)?

→ `PACKAGE_MANAGER`, `PACKAGE_MANAGER_SYNC_CMD`, `PACKAGE_MANAGER_RUN_CMD`,
`PACKAGE_MANAGER_ADD_CMD`, `TEST_CMD`, `DEPENDENCY_MANIFEST`, `LOCKFILE`.

## 4. Hardware / accelerators

- Does this project use any GPU/accelerator hardware? "No" is the common
  case for most projects and is fine — just confirm before moving on.
- If yes: how many, what model/memory, and do the tools you use (e.g.
  `nvidia-smi`, your ML framework, a job scheduler) agree on device
  indexing? Is compute shared with other people or jobs, and if so, how is
  that coordinated?

→ `ACCELERATORS_ENABLED` (`true`/`false`). If `true`, `init_harness.py`
materializes `harness/rules/gpu.md` and turns on the accelerator-allocation
rule (10) and shared-compute-etiquette rule (14) in `harness/harness.md` —
write the device table and allocation policy into `gpu.md` yourself
afterward (free-text `[SET AT SETUP: ...]` prose, same pattern as Project
Overview). If `false`, both files stay in their default "no accelerator
hardware" state and nothing else is needed.

## 5. Detached background jobs

- Does this machine have a user systemd manager (survives a dropped
  SSH/tmux session)? If unsure, check: `systemctl --user status` succeeding
  is a yes.
- If not, is this running inside the project's own Docker container (see
  §8)? If neither, plain `setsid`/`nohup` is the fallback.

→ `LAUNCH_METHOD` — exactly one of `systemd-run-user`, `setsid-nohup`,
`setsid-nohup-container`.

## 6. Version control & task tracking

- What's the git remote (SSH URL)? If there isn't one yet, offer to help
  create it (`git init`, a new GitHub/GitLab repo) — confirm before acting.
- Is work also tracked in an external issue tracker (GitLab Issues, GitHub
  Issues, something else)? "No" is common and fine.
  - If yes: which host, and what's the project path (`org/repo`)? Is a
    token already available (`GITLAB_TOKEN`/`GITHUB_TOKEN` in `.env` —
    that's a secret, it does NOT go in `harness.config.env`)?

→ `VCS_REMOTE`, `TRACKER_KIND` (`none` | `gitlab-issues` | `github-issues`),
and if not `none`: `TRACKER_HOST`, `VCS_REMOTE_PROJECT_PATH`.

## 7. Agent tooling

- Which coding-agent adapters does this project need — Claude Code
  (`.claude/`), Antigravity (`.agents/`), both?
- What keyword(s) in a model name mark it "high tier" for `[heavy]`-tagged
  directive escalation (e.g. `opus`)?

→ `ADAPTERS_ENABLED` (comma-separated: `claude`, `antigravity`, or both),
`HIGH_TIER_MODEL_KEYWORDS`.

## 8. Docker (optional)

- Set up a Docker dev-container for this project? Most projects should say
  yes only if isolating agent tool calls from the host matters here.
- If yes: any additional host paths to mount as volumes, beyond the
  project directory itself (a datasets dir, a shared model cache)?
  `host_path:container_path[:ro]` — one per line, keep going until they say
  done.
- Build the image now, or leave that for later?

→ `DOCKER_ENABLED` (`true`/`false`); if `true`: `DOCKER_EXTRA_VOLUMES`
(semicolon-joined `host:container[:ro]` entries), `DOCKER_BUILD_NOW`
(`true`/`false`). To change ONLY the volume list later, edit
`DOCKER_EXTRA_VOLUMES` in `harness.config.env` directly and re-run
`init_harness.py` — no need to redo the whole interview.

## 9. Bibliography tooling (optional)

Only relevant if this project uses `harness/tools/*.py` (literature-review
workflow against `docs/references/references.bib`) — skip entirely if not.

- What contact email should the bibliography tools' outbound HTTP
  `User-Agent` header carry (Crossref/Unpaywall etc. expect a real
  contact)? Blank is fine, it just won't be included.
- What product token identifies these requests (default:
  `<project-name>-biblio-tools`)?

→ `BIBLIO_CONTACT_EMAIL`, `BIBLIO_USER_AGENT_TOKEN`.

Separately (independent of the above — the references/inbox workflow is
generic and always available): does this project want the **LaTeX/Beamer
drafting suite**? When enabled, the Researcher drafts formal theory/methods
content as a self-contained `latexmk` project under `docs/theory/`, and the
Author builds the final report + Beamer slide decks under `docs/report/`,
both citing the shared `docs/references/references.bib`. When disabled,
both roles keep their other duties (memos, references, `docs/RESULTS.md`)
but write any formal writeup as plain Markdown instead. Say yes only if
this project's output is genuinely LaTeX-typeset (a formal paper, a
report/slide deck built from `.tex`) — most projects should say no.

→ `LATEX_DRAFTING_ENABLED`.

---

## After writing `harness.config.env`

Run:

```bash
python3 .friday/setup/init_harness.py
```

Read its closing checklist. It will call out any `[SET AT SETUP: ...]`
markers still unfilled — those are free-text prose sections (project
overview, repository layout, accelerator device table, optional rule
sections) that only a human/agent can write, not something the script can
infer from `harness.config.env`. Fill those in by hand, in the materialized
files it lists. The checklist also reminds you to: run the markdown-hygiene
hook, confirm `harness/status.md` reflects reality, and open a first
directive from `harness/plans/directives/TEMPLATE.md`.

Finally, record anything surprising you learned during this setup in
`harness/log.md` — that file is the "why" behind your rules, and it starts
on day one. Then you're done.
