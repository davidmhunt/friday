// Pure render functions: state -> element trees {tag, cls, attrs, kids}. app.js turns the trees
// into DOM with textContent only, so no state text is ever parsed as HTML.

export const TABS = ["overview", "machines", "projects", "sessions"];

export function h(tag, props, ...kids) {
  const p = props || {};
  const { cls, ...attrs } = p;
  return { tag, cls: cls || "", attrs, kids: kids.flat(Infinity).filter((k) => k !== null && k !== undefined && k !== false) };
}

const pct = (u, t) => (u == null || !t ? null : Math.round((100 * u) / t));
const gib = (b) => (b == null ? "?" : (b / 2 ** 30).toFixed(1) + " GiB");
const mib = (m) => (m == null ? "?" : (m / 1024).toFixed(1) + " GiB");

export function ago(secs) {
  if (secs == null) return "never";
  const s = Math.max(0, Math.round(secs));
  if (s < 90) return s + "s";
  if (s < 5400) return Math.round(s / 60) + "m";
  if (s < 129600) return Math.round(s / 3600) + "h";
  return Math.round(s / 86400) + "d";
}

export function repoName(path) {
  return String(path || "").split("/").filter(Boolean).pop() || "?";
}

export function directiveKind(status) {
  const s = String(status || "");
  if (s.startsWith("running")) return "running";
  if (s.startsWith("blocked")) return "blocked";
  if (s === "awaiting review") return "review";
  return s || "unknown";
}
export function runningHost(status) {
  const m = /^running@(\S+)/.exec(String(status || ""));
  return m ? m[1] : null;
}

// ------------------------------------------------------------------ derived data
export function reports(state) {
  return Object.entries((state && state.nodes) || {}).map(([name, n]) => ({ name, ...n, rep: n.report || {} }));
}

export function allSessions(state) {
  const out = [];
  for (const n of reports(state))
    for (const s of n.rep.sessions || []) out.push({ ...s, node: n.name, nodeStatus: n.status, age: n.rep.time && s.created ? n.rep.time - s.created : null });
  return out;
}

export function projects(state) {
  const map = new Map();
  for (const n of reports(state)) {
    for (const r of n.rep.repos || []) {
      const key = r.origin || r.path;
      if (!map.has(key)) map.set(key, { key, name: repoName(r.origin || r.path).replace(/\.git$/, ""), origin: r.origin, nodes: [], goals: [] });
      const p = map.get(key);
      p.nodes.push(n.name);
      for (const g of r.goals || []) if (!p.goals.some((x) => x.id === g.id)) p.goals.push(g);
    }
  }
  return [...map.values()];
}

export function prsFor(state, project) {
  return ((state && state.prs) || []).filter((pr) => project.origin && String(project.origin).includes(pr.repo));
}

export function needsYou(state) {
  const items = [];
  for (const s of allSessions(state))
    if (s.waiting) items.push({ kind: "waiting", where: s.node + " / " + s.name, text: s.waiting_line || "waiting for input" });
  for (const p of projects(state))
    for (const g of p.goals)
      for (const d of g.directives || [])
        if (directiveKind(d.status) === "blocked") items.push({ kind: "blocked", where: d.id, text: d.status.replace(/^blocked:\s*/, "") });
        else if (directiveKind(d.status) === "review") items.push({ kind: "review", where: d.id, text: "awaiting review: run `friday accept " + d.id + "`" });
  for (const n of reports(state)) {
    if (n.status === "missing") items.push({ kind: "missing", where: n.name, text: "never reported" });
    else if (n.status === "stale") items.push({ kind: "stale", where: n.name, text: "last seen " + ago(n.age_s) + " ago" });
    for (const l of n.rep.leases || []) items.push({ kind: "lease", where: n.name, text: l.resource + " held by " + l.session + (l.note ? " (" + l.note + ")" : "") });
  }
  for (const pr of (state && state.prs) || []) items.push({ kind: "PR", where: pr.repo + " #" + pr.number, text: pr.title, href: pr.url });
  return items;
}

function dotClass(n) {
  return n.status === "ok" ? "live" : n.status === "stale" ? "stale" : "down";
}

// ------------------------------------------------------------------ views
export function renderNeeds(state) {
  const items = needsYou(state);
  if (!items.length) return h("div", { cls: "needs clear" }, h("h2", {}, "Nothing needs you"));
  return h("div", { cls: "needs" }, h("h2", {}, "Needs you (" + items.length + ")"),
    h("ul", {}, items.map((i) => h("li", { cls: "need " + i.kind },
      h("span", { cls: "kind" }, i.kind), h("strong", {}, i.where),
      i.href ? h("a", { href: i.href, rel: "noopener" }, i.text) : h("span", { cls: "line" }, i.text)))));
}

export function machineCard(n) {
  const r = n.rep, hl = r.health || {}, load = hl.load || [];
  const sess = r.sessions || [], waiting = sess.some((s) => s.waiting);
  const mem = pct(hl.mem && hl.mem.used, hl.mem && hl.mem.total), disk = pct(hl.disk && hl.disk.used, hl.disk && hl.disk.total);
  const kv = [
    ["load", load.length ? load.map((x) => x.toFixed(2)).join(" ") : "?"],
    ["RAM", mem == null ? "?" : mem + "% of " + gib(hl.mem.total)],
    ["disk", disk == null ? "?" : disk + "% of " + gib(hl.disk.total)],
  ];
  for (const [i, g] of (r.gpus || []).entries())
    kv.push(["GPU " + i, (g.util == null ? "?" : g.util + "%") + " " + mib(g.mem && g.mem.used) + "/" + mib(g.mem && g.mem.total)]);
  kv.push(["sessions", String(sess.length)], ["leases", String((r.leases || []).length)]);
  return h("div", { cls: "card machine" + (n.status !== "ok" ? " stale" : "") + (waiting ? " needs-you" : "") },
    h("div", { cls: "card-head" }, h("span", { cls: "dot " + dotClass(n), title: n.status }),
      h("span", { cls: "card-title" }, n.name), h("span", { cls: "badge" }, n.role || "node")),
    h("div", { cls: "card-sub" }, n.status === "missing" ? "never reported: run `friday nodes --setup " + n.name + "` on the master" : n.status + ", seen " + ago(n.age_s) + " ago"),
    h("dl", { cls: "kv" }, kv.map(([k, v]) => [h("dt", {}, k), h("dd", {}, v)])));
}

export function projectState(p, state) {
  const sess = allSessions(state).filter((s) => p.goals.some((g) => (g.directives || []).some((d) => d.id === s.directive)));
  if (sess.some((s) => s.waiting) || p.goals.some((g) => (g.directives || []).some((d) => ["blocked", "review"].includes(directiveKind(d.status))))) return "needs";
  if (p.goals.some((g) => (g.directives || []).some((d) => directiveKind(d.status) === "running"))) return "working";
  if (prsFor(state, p).length) return "landed";
  return "idle";
}
const ICON = { working: "", needs: "!", landed: "✓", idle: "z" };

export function activeGoal(p) {
  return p.goals.find((g) => (g.directives || []).some((d) => directiveKind(d.status) === "running"))
    || p.goals.find((g) => g.status !== "done") || p.goals[0] || null;
}

export function projectCard(p, state) {
  const g = activeGoal(p), st = projectState(p, state), prs = prsFor(state, p);
  const ds = g ? g.directives || [] : [], done = ds.filter((d) => d.status === "done").length;
  return h("div", { cls: "card project" + (st === "needs" ? " needs-you" : "") },
    h("div", { cls: "card-head" }, h("span", { cls: "state " + st, title: st }, ICON[st]), h("span", { cls: "card-title" }, p.name)),
    h("div", { cls: "card-sub" }, g ? "goal " + (g.id || "(none)") + ": " + g.title : "no goals"),
    h("dl", { cls: "kv" }, h("dt", {}, "directives"), h("dd", {}, done + "/" + ds.length),
      h("dt", {}, "open PRs"), h("dd", {}, prs.length ? prs.map((pr) => h("a", { href: pr.url, rel: "noopener" }, "#" + pr.number + " ")) : "none")));
}

export function renderOverview(state) {
  const ms = reports(state), ps = projects(state);
  return h("section", { cls: "view", id: "view-overview" }, renderNeeds(state),
    h("h2", {}, "Machines"), ms.length ? h("div", { cls: "grid" }, ms.map(machineCard)) : h("p", { cls: "empty" }, "No machines."),
    h("h2", {}, "Projects"), ps.length ? h("div", { cls: "grid" }, ps.map((p) => projectCard(p, state))) : h("p", { cls: "empty" }, "No projects reported yet."));
}

export function renderMachines(state) {
  const ms = reports(state);
  return h("section", { cls: "view", id: "view-machines" }, h("h2", {}, "Machines"),
    ms.map((n) => {
      const r = n.rep;
      return h("div", { cls: "machine-detail" }, machineCard(n),
        (r.errors || []).length ? h("p", { cls: "badge warn" }, (r.errors || []).length + " read errors: " + r.errors.map((e) => e.where).join(", ")) : null,
        h("h3", {}, "GPUs"),
        (r.gpus || []).length ? h("div", { cls: "table-wrap" }, h("table", {}, h("thead", {}, h("tr", {}, ["GPU", "util", "memory", "processes"].map((x) => h("th", {}, x)))),
          h("tbody", {}, r.gpus.map((g, i) => h("tr", {}, h("td", {}, i + " " + g.name), h("td", {}, g.util == null ? "?" : g.util + "%"),
            h("td", {}, mib(g.mem && g.mem.used) + " / " + mib(g.mem && g.mem.total)),
            h("td", { cls: "mono" }, (g.processes || []).length ? g.processes.map((p) => p.name + " (" + p.pid + ", " + (p.mem == null ? "?" : p.mem + " MiB") + ")").join(", ") : "none")))))) : h("p", { cls: "empty" }, "No GPUs."),
        h("h3", {}, "Sessions"),
        (r.sessions || []).length ? h("ul", {}, r.sessions.map((s) => h("li", {}, s.name + (s.directive ? " - " + s.directive : "") + (s.waiting ? " (waiting)" : "")))) : h("p", { cls: "empty" }, "No sessions."),
        h("h3", {}, "Recent runs"),
        (r.runs || []).length ? h("div", { cls: "table-wrap" }, h("table", {}, h("tbody", {}, r.runs.map((x) => h("tr", {}, h("td", {}, repoName(x.repo)), h("td", { cls: "mono" }, x.id), h("td", {}, x.name),
          h("td", {}, h("span", { cls: "badge " + (x.exit === 0 ? "ok" : x.exit == null ? "" : "danger") }, x.exit == null ? "running" : "exit " + x.exit))))))) : h("p", { cls: "empty" }, "No runs."));
    }));
}

export function renderProjects(state) {
  const ps = projects(state), sess = allSessions(state);
  return h("section", { cls: "view", id: "view-projects" }, h("h2", {}, "Projects"),
    ps.length ? ps.map((p) => h("div", { cls: "project-detail" }, projectCard(p, state),
      p.goals.map((g) => [h("h3", {}, "Goal " + (g.id || "(no goal)") + ": " + g.title + " [" + g.status + "]"),
        h("div", { cls: "table-wrap" }, h("table", {}, h("thead", {}, h("tr", {}, ["directive", "title", "status", "deliverable", "runs on"].map((x) => h("th", {}, x)))),
          h("tbody", {}, (g.directives || []).map((d) => {
            const host = runningHost(d.status), s = sess.find((x) => x.directive === d.id);
            const where = directiveKind(d.status) === "running" ? (host || "?") + (s ? " (" + s.node + ")" : "") : "";
            return h("tr", {}, h("td", { cls: "mono" }, d.id), h("td", {}, d.title),
              h("td", {}, h("span", { cls: "badge " + (d.status === "done" ? "ok" : ["blocked", "review"].includes(directiveKind(d.status)) ? "warn" : "") }, d.status)),
              h("td", {}, d.deliverable), h("td", {}, where));
          }))))]))) : h("p", { cls: "empty" }, "No projects reported yet."));
}

export function renderSessions(state, expanded) {
  const ss = allSessions(state), open = new Set(expanded || []);
  const rows = [];
  for (const s of ss) {
    const key = s.node + "/" + s.name, isOpen = open.has(key);
    rows.push(h("tr", { cls: "row", "data-key": key, tabindex: "0", "aria-expanded": String(isOpen) },
      h("td", {}, s.node), h("td", { cls: "mono" }, s.goal || ""), h("td", { cls: "mono" }, s.directive || ""),
      h("td", {}, [s.phase, s.step].filter(Boolean).join(" / ")), h("td", {}, s.age == null ? "" : ago(s.age)),
      h("td", {}, s.waiting ? h("span", { cls: "badge warn" }, "waiting") : "")));
    if (isOpen) rows.push(h("tr", { cls: "detail" }, h("td", { colspan: "6" },
      s.waiting_line ? h("p", { cls: "line" }, s.waiting_line) : null,
      h("pre", { cls: "snippet" }, (s.snippet || []).join("\n") || "(no output)"))));
  }
  return h("section", { cls: "view", id: "view-sessions" }, h("h2", {}, "Sessions"),
    ss.length ? h("div", { cls: "table-wrap" }, h("table", {}, h("thead", {}, h("tr", {}, ["machine", "goal", "directive", "phase / step", "age", ""].map((x) => h("th", {}, x)))), h("tbody", {}, rows)))
      : h("p", { cls: "empty" }, "No running sessions."));
}

export const VIEWS = { overview: renderOverview, machines: renderMachines, projects: renderProjects, sessions: renderSessions };
