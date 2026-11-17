# status-03: Dashboard UI modelled on Jarvis OS: Overview, Machines, Projects, Sessions
Status: blocked: step 1: Where is the Jarvis OS checkout, or its 'tokens.css'? Please give me the path, or copy it to '/home/david/Documents/claude_temp/jarvis/jarvis_os/static/tokens.css'. My recommendation is to wait for the real file, because the step requires it to be vendored with a source header. The alternative is for me to write my own 'tokens.css' with the variables the step names ('--warn' and the dark and light palettes), labelled 'modelled on Jarvis OS, not vendored'. That departs from the step's wording, so I won't do it unless you say so.
Goal: status-page
Node: any
Deliverable: code
Land: goal
Verify: uv run --with pytest pytest -q tests/test_dash_ui.py && uv run --with pytest pytest -q && claude plugin validate .
Hardware: none

## Goal
`friday dash` serves a read-only dashboard in the Jarvis OS style (`../jarvis/jarvis_os/static`):
an Overview with a "needs you" strip, one summary card per machine and one card per project, plus
Machines, Projects and Sessions tabs for detail, in dark and light, usable on a phone. It is
vanilla JS with no build step, polls `/api/state` every 15 s, and shows staleness.
tests/test_dash_ui.py proves the page renders every section from a fixture state.

## Steps
1. Vendor `tokens.css` from Jarvis OS into `dash/static/` with a header naming its source file
   and commit, and write `dash/static/app.css` on those tokens (no colour literals). Take the
   patterns, not the code: card with a liveness dot and one state icon (spinner working, `!`
   needs you, `✓` landed with an open PR, `z` idle), top bar with tabs, `--warn` for needs-you.
2. `dash/static/index.html` + `app.js` (ES modules, no framework): Overview = needs-you strip
   (sessions waiting for input with the matched line, blocked directives, stale or missing nodes,
   held leases, open PRs), machine cards (role, dot from last seen, load, RAM, disk, GPU util and
   memory, session count, leases), project cards (active goal, done/total, state icon, PR link).
   Machines tab: per machine its health, GPUs with processes, sessions and recent runs. Projects
   tab: per project its goals with every directive's id, title, status and deliverable, and where
   each running directive runs. Sessions tab: every running session with machine, goal,
   directive, phase/step, age, waiting flag and an expandable pane snippet.
3. Render all text with `textContent` (never `innerHTML` from state); show "updated Ns ago" and
   grey out stale data; tab and the expanded rows are kept in `localStorage` (wrapped in
   try/catch); `prefers-color-scheme` picks the theme.
4. Add `tests/test_dash_ui.py`: serve the static files and a fixture `/api/state` (two machines,
   one stale; two projects; a waiting session with a snippet; an open PR); assert with a
   stdlib HTML parser that index.html loads app.js and both CSS files, that app.js has no
   `innerHTML` assignment and no external URLs, and run `node --test dash/static/render.test.mjs`
   when node exists (skipped otherwise) for the render functions on the fixture.

## Out of scope
- Acting from the page (approve, retry, dispatch): a later goal.
- Jarvis OS features beyond these four views (timeline, proposals, devices, settings, palette).
- Authentication in the page (the tailnet bind and whois check in status-02 are the boundary).

## Log

### 2026-11-17
Commits:
- (none)
Notes:
2026-11-17: Dispatched from thinkpadP15v3 to cpsl-homebase
Verify: not run
Independent review: not recorded
Blocked: step 1: Where is the Jarvis OS checkout, or its 'tokens.css'? Please give me the path, or copy it to '/home/david/Documents/claude_temp/jarvis/jarvis_os/static/tokens.css'. My recommendation is to wait for the real file, because the step requires it to be vendored with a source header. The alternative is for me to write my own 'tokens.css' with the variables the step names ('--warn' and the dark and light palettes), labelled 'modelled on Jarvis OS, not vendored'. That departs from the step's wording, so I won't do it unless you say so.
